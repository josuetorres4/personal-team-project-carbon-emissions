"""
sust-AI-naible — Full Pipeline Runner
======================================
Runs the multi-agent system via the Orchestrator.

The Orchestrator manages 5 AI agents + 2 deterministic services:
  - Planner Agent       (LLM reasoning + deterministic solver)
  - Governance Agent    (LLM risk assessment + deterministic rules)
  - Executor Agent      (LLM ticket generation + deterministic execution)
  - Developer Copilot   (LLM summaries + deterministic points)
  - Verifier            (deterministic counterfactual verification)
  - Carbon Accountant   (deterministic emissions math)
  - Ingestor            (simulated data generation)

Usage:
  python run_pipeline.py              # Mock LLM (no API key needed)
  GROQ_API_KEY=gsk_... python run_pipeline.py   # Groq LLM (free)
  OPENAI_API_KEY=sk-... python run_pipeline.py   # OpenAI LLM
"""

import json
from datetime import datetime
from pathlib import Path

from src.orchestrator import Orchestrator
from src.shared.carbon_market import CarbonMarket
from src.shared.proof_of_impact import ProofOfImpactCard


def main():
    orchestrator = Orchestrator(
        llm_provider="auto",  # Uses Groq/OpenAI if API key is set, else mock
        verbose=True,
    )

    summary = orchestrator.run(
        sim_start=datetime(2025, 1, 1),
        sim_days=30,
        seed=42,
        time_resolution_hours=4,
    )

    # Print which LLM was used
    print(f"\n  LLM Provider: {summary.get('llm_provider', 'unknown')}")
    print(f"  Agent reasoning steps:")
    for agent, stats in summary.get("agents", {}).items():
        print(f"    {agent}: {stats['reasoning_steps']} reasoning steps, "
              f"{stats['actions_taken']} tool calls")

    # --- Carbon Market & Proof-of-Impact Integration ---
    # Load optimized jobs data to extract teams
    import pandas as pd
    try:
        jobs_df = pd.read_csv("data/jobs_optimized.csv")
        verifications_df = pd.read_csv("data/verifications.csv")
    except FileNotFoundError:
        print("  Skipping carbon market integration — data files not found.")
        return

    # Extract unique teams
    team_col = "team_id" if "team_id" in jobs_df.columns else "team"
    teams = list(jobs_df[team_col].unique()) if team_col in jobs_df.columns else ["default"]

    # Initialize carbon market
    market = CarbonMarket(teams=teams, weekly_budget_kg=500.0)

    # Generate proof-of-impact evidence cards
    print("\n" + "=" * 70)
    print("  Generating Proof-of-Impact evidence cards...")
    print("=" * 70)

    poi_records = []
    Path("data/evidence_cards").mkdir(parents=True, exist_ok=True)

    for _, v in verifications_df.iterrows():
        v_dict = v.to_dict()
        # Map verification fields to expected keys
        v_mapped = {
            "job_id": v_dict.get("job_id", v_dict.get("recommendation_id", "unknown")),
            "point_estimate_kg": v_dict.get("verified_savings_kgco2e", 0),
            "ci_lower_kg": v_dict.get("ci_lower", 0),
            "ci_upper_kg": v_dict.get("ci_upper", 0),
            "saving_is_significant": v_dict.get("ci_lower", 0) > 0 and v_dict.get("verified_savings_kgco2e", 0) > 0,
            "action": v_dict.get("action_type", "optimization"),
            "counterfactual_kg": v_dict.get("verified_savings_kgco2e", 0) * 2,
            "actual_kg": v_dict.get("verified_savings_kgco2e", 0),
            "method": "bootstrap",
            "carbon_data_source": "simulated",
            "is_real": False,
        }

        # Find matching job
        job_id = v_dict.get("job_id", v_dict.get("recommendation_id", "unknown"))
        matching_jobs = jobs_df[jobs_df["job_id"] == job_id] if "job_id" in jobs_df.columns else pd.DataFrame()
        job_dict = {}
        if not matching_jobs.empty:
            row = matching_jobs.iloc[0]
            job_dict = {
                "job_id": row.get("job_id", job_id),
                "team": row.get(team_col, "unknown"),
            }
        else:
            job_dict = {"job_id": job_id, "team": "unknown"}

        card = ProofOfImpactCard(verification=v_mapped, job=job_dict, market=market.to_dict())
        poi_records.append(card.to_dict())

        # Generate PDF for significant savings only
        if v_mapped.get("saving_is_significant"):
            safe_id = str(job_id).replace("/", "_").replace("\\", "_")
            card.to_pdf(f"data/evidence_cards/{safe_id}_evidence.pdf")

        # Record in market
        team = job_dict.get("team", "unknown")
        if team and team in market.budgets:
            market.record_saving(team, v_mapped.get("point_estimate_kg", 0),
                               verified=v_mapped.get("saving_is_significant", False))

    # Run copilot as carbon broker
    broker_result = orchestrator.copilot.run_as_broker(market)

    # Approve broker-proposed trades through governance
    for trade_proposal in broker_result.get("proposed_trades", []):
        try:
            from_team = trade_proposal.get("from_team", "")
            to_team = trade_proposal.get("to_team", "")
            kg = trade_proposal.get("kg", 0)
            if from_team in market.budgets and to_team in market.budgets and kg > 0:
                trade = market.propose_trade(
                    from_team=from_team,
                    to_team=to_team,
                    kg=kg
                )
                market.approve_trade(trade.trade_id)
        except (ValueError, KeyError):
            pass

    # Save everything
    market.save("data/carbon_market.json")
    with open("data/proof_of_impact.json", "w") as f:
        json.dump(poi_records, f, indent=2)

    significant_count = sum(1 for p in poi_records if p.get("saving_is_significant"))
    print(f"  {len(poi_records)} evidence cards generated")
    print(f"  {significant_count} PDF evidence cards written")
    print(f"  Carbon market: {len(market.trades)} trades proposed")


if __name__ == "__main__":
    main()
