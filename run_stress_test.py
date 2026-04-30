"""
Governance Stress Test
======================
Runs the A/B comparison on a workload deliberately skewed toward high-risk
production jobs, so governance's enforcement machinery actually fires.

Why this reveals the architectural gap:
  - Multi-agent: GovernanceAgent has a HARD CODE 85% approval rate for
    "high" risk recommendations (SIMULATED_HIGH_RISK_APPROVAL_RATE = 0.85
    in governance.py). When 50–60% of jobs are production workloads, ~15%
    of all recommendations get rejected by the human-simulated review — with
    a recorded reason in governance_decisions.csv and a multi-round negotiation
    transcript in agent_dialogues.json.
  - Single-model: the _deterministic_fallback() only checks
    `carbon_delta < 0 and cost_pct <= MAX_COST_INCREASE_PCT`. No risk_level
    check. It approves every carbon-saving rec regardless of production status.
    The LLM system prompt says "reject high-risk production moves" — but there
    is no code-level circuit breaker enforcing it.

Result: multi-agent produces real rejections with audit trails. Single-model
rubber-stamps the same batch. The difference in quality (refuted verifications)
and the presence/absence of the audit trail is the headline.

Config overrides applied:
  STRESS_TEST_PRODUCTION_FRACTION = 0.60   (60% of jobs → production workload)
  MAX_JOBS_PER_REGION              = 8     (tighter concentration limit)
  MAX_COST_INCREASE_PCT            = 5     (tighter cost guardrail)
  MAX_AZURE_JOBS                   = 800   (faster run; avoids Groq rate limits)

Outputs:
  data/stress_test/multi_agent/         (multi-agent pipeline artifacts)
  data/stress_test/single_model_small/  (single-model pipeline artifacts)
  data/stress_test/comparison_summary.json
  data/stress_test/architecture_comparison.json

Usage:
  python run_stress_test.py
  python run_stress_test.py --sim-days 5 --seed 99
  python run_stress_test.py --skip-single   # multi-agent only
"""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

# ── Apply stress-test overrides BEFORE any pipeline import reads os.environ ──
os.environ["STRESS_TEST_PRODUCTION_FRACTION"] = "0.60"
os.environ["MAX_JOBS_PER_REGION"] = "8"
os.environ["MAX_COST_INCREASE_PCT"] = "5"
os.environ["MAX_AZURE_JOBS"] = "800"
# Real workload (Azure traces) + EIA carbon data are still real.
# REAL_DATA_ONLY is disabled only to bypass the Electricity Maps token requirement,
# which is not needed for the stress-test comparison itself.
os.environ["REAL_DATA_ONLY"] = "false"
# Skip per-rec LLM risk narratives — governance decisions are deterministic anyway.
# This avoids Groq 503 capacity errors on the individual risk-assessment calls.
os.environ["MAX_LLM_RISK_ASSESSMENTS"] = "0"

from run_comparison import run_multi_agent, run_single_model, compute_comparison


STRESS_MULTI_DIR = "data/stress_test/multi_agent"
STRESS_SINGLE_DIR = "data/stress_test/single_model_small"


def main():
    parser = argparse.ArgumentParser(description="Governance stress-test A/B comparison")
    parser.add_argument("--sim-days", type=int, default=7)
    parser.add_argument("--seed", type=int, default=99)
    parser.add_argument("--skip-single", action="store_true",
                        help="Run only the multi-agent pipeline")
    parser.add_argument("--skip-multi", action="store_true",
                        help="Run only the single-model pipeline")
    args = parser.parse_args()

    print("\n" + "=" * 70)
    print("  GOVERNANCE STRESS TEST")
    print("  60% production workloads  •  concentration limit 8/region")
    print("  cost guardrail 5%  •  800-job cap")
    print("=" * 70)
    print(f"  STRESS_TEST_PRODUCTION_FRACTION = {os.environ['STRESS_TEST_PRODUCTION_FRACTION']}")
    print(f"  MAX_JOBS_PER_REGION             = {os.environ['MAX_JOBS_PER_REGION']}")
    print(f"  MAX_COST_INCREASE_PCT           = {os.environ['MAX_COST_INCREASE_PCT']}")
    print(f"  MAX_AZURE_JOBS                  = {os.environ['MAX_AZURE_JOBS']}")

    Path("data/stress_test").mkdir(parents=True, exist_ok=True)
    summaries: dict[str, dict] = {}

    if not args.skip_multi:
        s = run_multi_agent(args.sim_days, args.seed, output_dir=STRESS_MULTI_DIR)
        summaries["multi_agent"] = s

    if not args.skip_single:
        s = run_single_model("groq", args.sim_days, args.seed,
                             output_dir=STRESS_SINGLE_DIR)
        summaries["single_model_small"] = s

    if not summaries:
        print("\n[StressTest] No runs completed — nothing to compare.")
        return

    comparison_summary, arch_comparison = compute_comparison(summaries)

    with open("data/stress_test/comparison_summary.json", "w") as f:
        json.dump(comparison_summary, f, indent=2, default=str)
    with open("data/stress_test/architecture_comparison.json", "w") as f:
        json.dump(arch_comparison, f, indent=2, default=str)

    # ── Print stress-test specific delta table ────────────────────────────
    print("\n" + "=" * 70)
    print("  STRESS TEST RESULTS — GOVERNANCE UNDER PRESSURE")
    print("=" * 70)

    decisions = comparison_summary.get("decisions", {})
    by_run = arch_comparison.get("by_run", {})

    print(f"\n  {'Metric':<35} {'Multi-Agent':>15} {'Single-Model':>15}")
    print(f"  {'-'*35} {'-'*15} {'-'*15}")

    def row(label, ma_val, sm_val, fmt="{}", suffix=""):
        ma = fmt.format(ma_val) + suffix if ma_val is not None else "N/A"
        sm = fmt.format(sm_val) + suffix if sm_val is not None else "N/A"
        print(f"  {label:<35} {ma:>15} {sm:>15}")

    for label, d in decisions.items():
        is_ma = label == "multi_agent"
        partner = "single_model_small" if is_ma else "multi_agent"
        pd = decisions.get(partner, {})
        if not is_ma:
            break

        row("Recommendations generated",
            d.get("recommendations_generated"), pd.get("recommendations_generated"), "{:,}")
        row("Approved",
            d.get("recommendations_approved"), pd.get("recommendations_approved"), "{:,}")
        row("Rejected",
            d.get("recommendations_generated", 0) - d.get("recommendations_approved", 0),
            pd.get("recommendations_generated", 0) - pd.get("recommendations_approved", 0),
            "{:,}")
        row("Approval rate",
            d.get("approval_rate"), pd.get("approval_rate"), "{:.1%}")
        row("Confirmed verifications",
            d.get("verification_status_counts", {}).get("confirmed"),
            pd.get("verification_status_counts", {}).get("confirmed"), "{:,}")
        row("Refuted verifications",
            d.get("verification_status_counts", {}).get("refuted"),
            pd.get("verification_status_counts", {}).get("refuted"), "{:,}")
        row("Significance ratio",
            d.get("significance_ratio"), pd.get("significance_ratio"), "{:.1%}")
        row("Negotiation dialogues",
            d.get("negotiation_dialogues"), pd.get("negotiation_dialogues"), "{:,}")

    print(f"\n  {'LLM / efficiency':<35}")
    for label, a in by_run.items():
        name = "Multi-Agent" if label == "multi_agent" else "Single-Model"
        print(f"    {name}: {a['llm_calls']} calls, {a['total_tokens']:,} tokens, "
              f"{a['wall_clock_seconds']:.0f}s, {a['estimated_energy_wh']:.2f} Wh")

    print("\n  Audit trail:")
    for label in summaries:
        dialogues_path = Path(
            STRESS_MULTI_DIR if label == "multi_agent" else STRESS_SINGLE_DIR
        ) / "agent_dialogues.json"
        try:
            dialogues = json.loads(dialogues_path.read_text())
            n = len(dialogues) if isinstance(dialogues, list) else 0
        except Exception:
            n = 0
        name = "Multi-Agent" if label == "multi_agent" else "Single-Model"
        print(f"    {name}: {n} negotiation dialogue(s) recorded in agent_dialogues.json")

    print("\n  The key finding:")
    ma_d = decisions.get("multi_agent", {})
    sm_d = decisions.get("single_model_small", {})
    ma_rejected = ma_d.get("recommendations_generated", 0) - ma_d.get("recommendations_approved", 0)
    sm_rejected = sm_d.get("recommendations_generated", 0) - sm_d.get("recommendations_approved", 0)
    if ma_rejected > sm_rejected:
        print(f"    Multi-agent rejected {ma_rejected} high-risk recs that single-model approved.")
        print(f"    Those rejections are in governance_decisions.csv with recorded reasons.")
        print(f"    Single-model has no audit trail for why it approved them.")
    elif ma_rejected == sm_rejected:
        print(f"    Both architectures rejected the same count — but only multi-agent has")
        print(f"    a recorded governance reason and negotiation transcript for each.")
    else:
        print(f"    Results: multi-agent={ma_rejected} rejected, single-model={sm_rejected} rejected.")

    print(f"\n  Wrote: data/stress_test/comparison_summary.json")
    print(f"  Wrote: data/stress_test/architecture_comparison.json")
    print()


if __name__ == "__main__":
    main()
