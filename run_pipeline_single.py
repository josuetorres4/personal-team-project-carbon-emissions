"""
Single-Model Pipeline Runner
============================
Runs the architecture A/B baseline: one LLM call per batch handles
Planner + Governance + Executor + Copilot duties.

Usage:
  python run_pipeline_single.py                        # Groq small (default)
  python run_pipeline_single.py --model frontier       # Anthropic Claude
  python run_pipeline_single.py --sim-days 7           # short run
"""

import argparse
from datetime import datetime

from config import Config
from src.single_model_orchestrator import SingleModelOrchestrator


def main():
    parser = argparse.ArgumentParser(description="Single-model pipeline runner")
    parser.add_argument("--model", choices=["groq", "frontier"], default="groq",
                        help="Which LLM to use (default: groq small)")
    parser.add_argument("--sim-days", type=int, default=Config.DEFAULT_SIM_DAYS,
                        help="Simulation days (default: from SIM_DAYS env)")
    parser.add_argument("--seed", type=int, default=Config.DEFAULT_SEED,
                        help="Random seed (default: from SEED env)")
    parser.add_argument("--output-dir", default=None,
                        help="Override output directory")
    parser.add_argument("--batch-size", type=int, default=50,
                        help="Recommendations per LLM call (default: 50)")
    args = parser.parse_args()

    if args.model == "frontier":
        provider = Config.FRONTIER_PROVIDER
        model = Config.FRONTIER_MODEL
        default_dir = "data/single_model_frontier"
    else:
        provider = "groq"
        model = Config.GROQ_MODEL
        default_dir = "data/single_model_small"

    output_dir = args.output_dir or default_dir

    orchestrator = SingleModelOrchestrator(
        provider=provider,
        model=model,
        verbose=True,
        output_dir=output_dir,
        batch_size=args.batch_size,
    )
    summary = orchestrator.run(
        sim_start=datetime(2025, 1, 1),
        sim_days=args.sim_days,
        seed=args.seed,
    )

    print("\n" + "=" * 70)
    print(f"  Single-model run complete — {output_dir}")
    print("=" * 70)
    usage = summary["llm_usage"]
    print(f"  Provider: {usage['provider']}")
    print(f"  Model:    {usage['model']}")
    print(f"  LLM calls: {usage['llm_calls']}")
    print(f"  Tokens:   prompt={usage['prompt_tokens']:,}  "
          f"completion={usage['completion_tokens']:,}  "
          f"total={usage['total_tokens']:,}")
    print(f"  Wall clock: {usage['wall_clock_seconds']}s")
    pl = summary["pipeline"]
    print(f"  Recs: {pl['recommendations_generated']} → "
          f"approved {pl['recommendations_approved']} → "
          f"executed {pl['recommendations_executed']}")
    print(f"  Verified savings: "
          f"{summary['improvement']['emissions_reduction_kgco2e']} kgCO2e "
          f"({summary['improvement']['emissions_reduction_pct']}%)")


if __name__ == "__main__":
    main()
