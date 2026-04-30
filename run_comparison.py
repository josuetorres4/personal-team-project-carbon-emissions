"""
Architecture Comparison Runner
==============================
Runs three pipelines on identical inputs and produces apples-to-apples
comparison artifacts:

  A. Multi-agent (small)        → data/multi_agent/
  B. Single-model (small)       → data/single_model_small/
  C. Single-model (frontier)    → data/single_model_frontier/

Then computes:
  - data/comparison_summary.json — decision quality + verified savings
  - data/architecture_comparison.json — tokens, energy, calls, wall-clock

Usage:
  python run_comparison.py                       # all three runs
  python run_comparison.py --skip-frontier       # A + B only
  python run_comparison.py --sim-days 7          # short run
  python run_comparison.py --skip-multi-agent    # B + C only (re-use earlier multi-agent run)
"""

import argparse
import json
import os
import shutil
from datetime import datetime
from pathlib import Path

from config import Config
from src.orchestrator import Orchestrator
from src.single_model_orchestrator import SingleModelOrchestrator


def _copy_data_dir(src: str, dst: str) -> None:
    """Move/copy the standard run output (data/*) to a labelled output dir."""
    Path(dst).mkdir(parents=True, exist_ok=True)
    standard = [
        "jobs_baseline.csv", "jobs_optimized.csv", "carbon_intensity.csv",
        "baseline_emissions.csv", "recommendations.csv", "governance_decisions.csv",
        "executions.csv", "verifications.csv", "points.csv", "leaderboard.csv",
        "evidence_chains.json", "agent_traces.json", "agent_dialogues.json",
        "pipeline_summary.json", "sample_ticket.md", "sample_team_narrative.md",
        "sample_evidence_chain.txt",
    ]
    for f in standard:
        src_path = Path(src) / f
        if src_path.exists():
            shutil.copy(src_path, Path(dst) / f)


def run_multi_agent(sim_days: int, seed: int, output_dir: str) -> dict:
    print("\n" + "#" * 70)
    print(f"# Multi-agent pipeline → {output_dir}")
    print("#" * 70)
    orch = Orchestrator(llm_provider="auto", verbose=True, output_dir=output_dir)
    summary = orch.run(
        sim_start=datetime(2025, 1, 1),
        sim_days=sim_days,
        seed=seed,
    )
    return summary


def run_single_model(model_choice: str, sim_days: int, seed: int, output_dir: str) -> dict:
    print("\n" + "#" * 70)
    print(f"# Single-model ({model_choice}) → {output_dir}")
    print("#" * 70)
    if model_choice == "frontier":
        provider = Config.FRONTIER_PROVIDER
        model = Config.FRONTIER_MODEL
    else:
        provider = "groq"
        model = Config.GROQ_MODEL

    orch = SingleModelOrchestrator(
        provider=provider,
        model=model,
        verbose=True,
        output_dir=output_dir,
        batch_size=50,
    )
    return orch.run(sim_start=datetime(2025, 1, 1), sim_days=sim_days, seed=seed)


def compute_comparison(summaries: dict[str, dict]) -> tuple[dict, dict]:
    """
    Build apples-to-apples comparison JSON.

    summaries: {label → pipeline_summary.json dict}

    Returns (comparison_summary, architecture_comparison).
    """
    energy_per_1k_prompt = Config.ENERGY_WH_PER_1K_PROMPT_TOKENS
    energy_per_1k_completion = Config.ENERGY_WH_PER_1K_COMPLETION_TOKENS
    grid_g_per_kwh = Config.LLM_GRID_INTENSITY_GCO2_KWH

    arch_rows = {}
    decision_rows = {}

    for label, summary in summaries.items():
        usage = summary.get("llm_usage", {})
        prompt = usage.get("prompt_tokens", 0)
        completion = usage.get("completion_tokens", 0)
        total = usage.get("total_tokens", prompt + completion)
        calls = usage.get("llm_calls", 0)
        wall = usage.get("wall_clock_seconds", 0)

        energy_wh = (
            prompt * energy_per_1k_prompt / 1000.0
            + completion * energy_per_1k_completion / 1000.0
        )
        # Convert Wh to kWh, multiply by grid intensity (g/kWh) → g CO2 → kg
        emissions_kg = (energy_wh / 1000.0) * grid_g_per_kwh / 1000.0

        arch_rows[label] = {
            "architecture": summary.get("architecture", "unknown"),
            "provider": usage.get("provider", "unknown"),
            "model": usage.get("model", "unknown"),
            "llm_calls": calls,
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": total,
            "wall_clock_seconds": wall,
            "estimated_energy_wh": round(energy_wh, 4),
            "estimated_emissions_kgco2e": round(emissions_kg, 6),
            "energy_method": (
                f"prompt={energy_per_1k_prompt} Wh/1k tok, "
                f"completion={energy_per_1k_completion} Wh/1k tok "
                f"(Patterson 2021 / Luccioni 2023); "
                f"grid={grid_g_per_kwh} gCO2/kWh (EPA eGRID 2023 US avg)"
            ),
        }

        improvement = summary.get("improvement", {})
        pipeline = summary.get("pipeline", {})
        verify = pipeline.get("verification_summary", {})
        by_status = verify.get("by_status", {})

        decision_rows[label] = {
            "verified_savings_kgco2e": improvement.get("emissions_reduction_kgco2e", 0),
            "emissions_reduction_pct": improvement.get("emissions_reduction_pct", 0),
            "cost_change_usd": improvement.get("cost_change_usd", 0),
            "recommendations_generated": pipeline.get("recommendations_generated", 0),
            "recommendations_approved": pipeline.get("recommendations_approved", 0),
            "recommendations_executed": pipeline.get("recommendations_executed", 0),
            "approval_rate": (
                pipeline.get("recommendations_approved", 0)
                / max(pipeline.get("recommendations_generated", 1), 1)
            ),
            "significance_ratio": pipeline.get("final_significance_ratio", 0),
            "verification_status_counts": {
                "confirmed": by_status.get("confirmed", 0),
                "partial": by_status.get("partial", 0),
                "refuted": by_status.get("refuted", 0),
            },
            "negotiation_dialogues": pipeline.get("negotiation_dialogues", 0),
            "replan_cycles": pipeline.get("replan_cycles", 0),
            "total_points_awarded": summary.get("gamification", {}).get("total_points_awarded", 0),
        }

    # Pick a "winner" headline — net of LLM emissions
    headline = _build_headline(decision_rows, arch_rows)

    comparison_summary = {
        "generated_at": datetime.now().isoformat(),
        "runs": list(summaries.keys()),
        "decisions": decision_rows,
        "headline": headline,
    }

    architecture_comparison = {
        "generated_at": datetime.now().isoformat(),
        "runs": list(summaries.keys()),
        "by_run": arch_rows,
        "headline": headline,
    }

    return comparison_summary, architecture_comparison


def _build_headline(decisions: dict, arch: dict) -> dict:
    """Compute the winner card: who saved more carbon NET of LLM energy?"""
    rows = []
    for label in decisions:
        gross_savings_kg = decisions[label]["verified_savings_kgco2e"]
        llm_emissions_kg = arch[label]["estimated_emissions_kgco2e"]
        net = gross_savings_kg - llm_emissions_kg
        rows.append({
            "label": label,
            "gross_kgco2e_saved": round(gross_savings_kg, 4),
            "llm_emissions_kgco2e": round(llm_emissions_kg, 6),
            "net_kgco2e_saved": round(net, 4),
            "tokens": arch[label]["total_tokens"],
            "llm_calls": arch[label]["llm_calls"],
            "significance_ratio": decisions[label]["significance_ratio"],
        })
    rows.sort(key=lambda r: -r["net_kgco2e_saved"])
    return {
        "winner_by_net_savings": rows[0]["label"] if rows else None,
        "ranking": rows,
    }


def main():
    parser = argparse.ArgumentParser(description="Run architecture A/B/C comparison")
    parser.add_argument("--sim-days", type=int, default=Config.DEFAULT_SIM_DAYS)
    parser.add_argument("--seed", type=int, default=Config.DEFAULT_SEED)
    parser.add_argument("--skip-multi-agent", action="store_true",
                        help="Skip the multi-agent run (re-use existing data/multi_agent/)")
    parser.add_argument("--skip-small", action="store_true",
                        help="Skip the single-model small run")
    parser.add_argument("--skip-frontier", action="store_true",
                        help="Skip the frontier run (no Anthropic key)")
    args = parser.parse_args()

    summaries: dict[str, dict] = {}

    if not args.skip_multi_agent:
        s = run_multi_agent(args.sim_days, args.seed, output_dir="data/multi_agent")
        summaries["multi_agent"] = s
    else:
        path = Path("data/multi_agent/pipeline_summary.json")
        if path.exists():
            summaries["multi_agent"] = json.loads(path.read_text())

    if not args.skip_small:
        s = run_single_model("groq", args.sim_days, args.seed,
                             output_dir="data/single_model_small")
        summaries["single_model_small"] = s
    else:
        path = Path("data/single_model_small/pipeline_summary.json")
        if path.exists():
            summaries["single_model_small"] = json.loads(path.read_text())

    if not args.skip_frontier:
        if not Config.ANTHROPIC_API_KEY:
            print("\n[Comparison] ANTHROPIC_API_KEY not set — skipping frontier run.")
        else:
            s = run_single_model("frontier", args.sim_days, args.seed,
                                 output_dir="data/single_model_frontier")
            summaries["single_model_frontier"] = s
    else:
        path = Path("data/single_model_frontier/pipeline_summary.json")
        if path.exists():
            summaries["single_model_frontier"] = json.loads(path.read_text())

    if not summaries:
        print("\n[Comparison] No runs available — nothing to compare.")
        return

    comparison_summary, arch_comparison = compute_comparison(summaries)
    Path("data").mkdir(exist_ok=True)
    with open("data/comparison_summary.json", "w") as f:
        json.dump(comparison_summary, f, indent=2, default=str)
    with open("data/architecture_comparison.json", "w") as f:
        json.dump(arch_comparison, f, indent=2, default=str)

    print("\n" + "=" * 70)
    print("  ARCHITECTURE COMPARISON")
    print("=" * 70)
    for row in arch_comparison["headline"]["ranking"]:
        print(
            f"  {row['label']:30s} "
            f"net={row['net_kgco2e_saved']:>+10.4f} kgCO2e "
            f"(gross {row['gross_kgco2e_saved']:>+8.3f}, "
            f"LLM cost {row['llm_emissions_kgco2e']:>.6f})  "
            f"tokens={row['tokens']:>7,}  calls={row['llm_calls']:>3}"
        )
    print(f"\n  Winner by net savings: {comparison_summary['headline']['winner_by_net_savings']}")
    print("\n  Wrote: data/comparison_summary.json, data/architecture_comparison.json")


if __name__ == "__main__":
    main()
