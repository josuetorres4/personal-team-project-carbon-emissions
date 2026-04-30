"""
Single-Model Orchestrator
=========================
Runs the same SENSE → MODEL → DECIDE → ACT → VERIFY → LEARN pipeline as the
multi-agent orchestrator, but DECIDE+ACT is collapsed into one LLM call per
batch via SingleModelAgent. Used for the architecture A/B comparison.

This module shares all deterministic components (Carbon Accountant, Verifier,
points math) with src/orchestrator.py. The only difference is which LLM
machinery sits between candidate generation and verification.
"""

import json
import os
import time
from datetime import datetime

import pandas as pd

from src.agents.base import LLMProvider
from src.agents.carbon_accountant import compute_emissions_batch, emissions_to_dataframe
from src.agents.copilot import (
    CopilotAgent, points_to_dataframe,
    POINTS_PER_KG_CO2E_SAVED, PARTIAL_MULTIPLIER, PointsEntry,
)
from src.agents.executor import executions_to_dataframe
from src.agents.governance import decisions_to_dataframe
from src.agents.planner import recommendations_to_dataframe
from src.agents.single_model import SingleModelAgent
from src.agents.verifier import (
    verify_batch, verifications_to_dataframe, summarize_verification,
    format_evidence_chain,
)
from src.data.azure_traces import get_workload_data
from src.data.carbon_intensity_real import get_carbon_intensity_data
from src.orchestrator import Orchestrator
from src.shared.impact import compute_business_impact
from src.simulator.cost_model import compute_job_cost
from src.simulator.workload_generator import jobs_to_dataframe


class SingleModelOrchestrator:
    """
    Same input/output contract as Orchestrator, but uses SingleModelAgent in
    place of the Planner / Governance / Executor / Copilot quartet.
    """

    def __init__(
        self,
        provider: str = "groq",
        model: str = None,
        verbose: bool = True,
        output_dir: str = "data/single_model_small",
        batch_size: int = 50,
    ):
        self.verbose = verbose
        self.output_dir = output_dir
        self.llm = LLMProvider(provider=provider, model=model)
        self.agent = SingleModelAgent(llm=self.llm, batch_size=batch_size)
        self.architecture = "single_model"

        self._log(f"SingleModelOrchestrator: provider={self.llm.provider}, "
                  f"model={getattr(self.llm, '_model', 'unknown')}, "
                  f"output_dir={output_dir}")

    def _log(self, msg: str):
        if self.verbose:
            print(f"  [SingleModel] {msg}")

    def _section(self, title):
        if self.verbose:
            print(f"\n{'=' * 70}")
            print(f"  {title}")
            print(f"{'=' * 70}")

    def run(
        self,
        sim_start: datetime = datetime(2025, 1, 1),
        sim_days: int = 30,
        seed: int = 42,
        time_resolution_hours: int = 4,
    ) -> dict:
        Orchestrator.preflight_real_data_check()

        start_time = time.time()
        os.makedirs(self.output_dir, exist_ok=True)

        # ── SENSE ─────────────────────────────────────────────────────
        self._section("Step 1: SENSE — Ingestor (real data)")
        jobs = get_workload_data(sim_start, sim_days=sim_days, seed=seed)
        jobs_df = jobs_to_dataframe(jobs)
        intensity_df = get_carbon_intensity_data(sim_start, num_days=sim_days, seed=seed)

        jobs_df["cost_usd"] = jobs_df.apply(
            lambda r: compute_job_cost(r["region"], r["vcpus"], r["gpu_count"], r["duration_hours"]),
            axis=1,
        )
        for j in jobs:
            j.cost_usd = compute_job_cost(j.region, j.vcpus, j.gpu_count, j.duration_hours)

        # ── MODEL ─────────────────────────────────────────────────────
        self._section("Step 2: MODEL — Carbon Accountant (deterministic)")
        baseline_emissions = compute_emissions_batch(jobs, intensity_df, verbose=self.verbose)
        baseline_emissions_df = emissions_to_dataframe(baseline_emissions)
        jobs_df["kgco2e"] = baseline_emissions_df["kgco2e"].values
        jobs_df["kgco2e_lower"] = baseline_emissions_df["kgco2e_lower"].values
        jobs_df["kgco2e_upper"] = baseline_emissions_df["kgco2e_upper"].values

        total_baseline_kgco2e = jobs_df["kgco2e"].sum()
        total_baseline_cost = jobs_df["cost_usd"].sum()
        self._log(f"Baseline: {total_baseline_kgco2e:.2f} kgCO2e, ${total_baseline_cost:,.2f}")

        # ── DECIDE + ACT (single LLM call per batch) ──────────────────
        self._section("Step 3: DECIDE + ACT — Single Model")
        agent_result = self.agent.run(
            jobs=jobs,
            intensity_df=intensity_df,
            time_resolution_hours=time_resolution_hours,
            verbose=self.verbose,
        )
        recommendations = agent_result["recommendations"]
        approved_recs = agent_result["approved_recs"]
        decisions = agent_result["decisions"]
        execution_records = agent_result["execution_records"]
        optimized_jobs = agent_result["optimized_jobs"]
        team_summary = agent_result["team_summary"]

        self._log(
            f"Single-model judged {len(recommendations)} candidates → "
            f"{len(approved_recs)} approved → {len(execution_records)} executed "
            f"in {self.llm.call_count} LLM call(s), {self.llm.total_tokens_used} tokens."
        )

        # Originals stay un-mutated in `jobs` so the Verifier can compute
        # counterfactual emissions; `optimized_jobs` are deepcopies with the
        # changes applied.
        approved_job_ids = {r.job_id for r in approved_recs}
        unchanged_jobs = [j for j in jobs if j.job_id not in approved_job_ids]
        all_final_jobs = optimized_jobs + unchanged_jobs

        # ── VERIFY (deterministic) ────────────────────────────────────
        self._section("Step 4: VERIFY — Verifier (deterministic)")
        post_emissions = compute_emissions_batch(all_final_jobs, intensity_df, verbose=self.verbose)
        post_emissions_df = emissions_to_dataframe(post_emissions)
        total_post_kgco2e = post_emissions_df["kgco2e"].sum()
        actual_reduction = total_baseline_kgco2e - total_post_kgco2e

        original_for_verify = [j for j in jobs if j.job_id in approved_job_ids]
        verifications = verify_batch(
            approved_recs, original_for_verify, optimized_jobs,
            intensity_df, verbose=self.verbose,
        )
        verify_summary = summarize_verification(verifications)
        self._log(
            f"Verified {verify_summary['count']} records, "
            f"{verify_summary.get('total_verified_savings_kgco2e', 0)*1000:.0f} gCO2e savings."
        )

        # ── LEARN (deterministic points; LLM team summary already done) ──
        self._section("Step 5: LEARN — deterministic points + single-model summary")
        rec_to_team = {r.recommendation_id: next(
            (j.team_id for j in jobs if j.job_id == r.job_id), "unknown"
        ) for r in approved_recs}

        points_entries = []
        for v in verifications:
            team_id = rec_to_team.get(v.recommendation_id, "unknown")
            multiplier = (
                1.0 if v.verification_status == "confirmed"
                else PARTIAL_MULTIPLIER if v.verification_status == "partial"
                else 0.0
            )
            if multiplier == 0 or v.verified_savings_kgco2e <= 0:
                continue
            points = int(v.verified_savings_kgco2e * POINTS_PER_KG_CO2E_SAVED * multiplier)
            if points <= 0:
                continue
            points_entries.append(PointsEntry(
                team_id=team_id,
                recommendation_id=v.recommendation_id,
                verification_id=v.verification_id,
                points=points,
                kgco2e_saved=v.verified_savings_kgco2e,
                reason=f"single_model:{v.verification_status}",
                awarded_at=datetime.now(),
            ))

        leaderboard = self._compute_leaderboard(points_entries)
        narratives = {"_aggregate": team_summary}

        # ── Save outputs ─────────────────────────────────────────────
        self._section("Saving Outputs")
        recs_df = recommendations_to_dataframe(recommendations)
        gov_df = decisions_to_dataframe(decisions)
        exec_df = executions_to_dataframe(execution_records)
        verify_df = verifications_to_dataframe(verifications)
        points_df = points_to_dataframe(points_entries)
        leaderboard_df = pd.DataFrame(leaderboard) if leaderboard else pd.DataFrame()

        post_jobs_df = jobs_to_dataframe(all_final_jobs)
        post_jobs_df["kgco2e"] = post_emissions_df["kgco2e"].values
        post_jobs_df["cost_usd"] = post_jobs_df.apply(
            lambda r: compute_job_cost(r["region"], r["vcpus"], r["gpu_count"], r["duration_hours"]), axis=1,
        )
        post_cost = post_jobs_df["cost_usd"].sum()
        cost_change = round(post_cost - total_baseline_cost, 2)

        outputs = {
            f"{self.output_dir}/jobs_baseline.csv": jobs_df,
            f"{self.output_dir}/carbon_intensity.csv": intensity_df,
            f"{self.output_dir}/baseline_emissions.csv": baseline_emissions_df,
            f"{self.output_dir}/recommendations.csv": recs_df,
            f"{self.output_dir}/governance_decisions.csv": gov_df,
            f"{self.output_dir}/executions.csv": exec_df,
            f"{self.output_dir}/verifications.csv": verify_df,
            f"{self.output_dir}/points.csv": points_df,
            f"{self.output_dir}/leaderboard.csv": leaderboard_df,
            f"{self.output_dir}/jobs_optimized.csv": post_jobs_df,
        }
        for path, df in outputs.items():
            df.to_csv(path, index=False)
            self._log(f"  {path} ({len(df):,} rows)")

        # Evidence chains
        evidence_data = [{
            "verification_id": v.verification_id,
            "recommendation_id": v.recommendation_id,
            "verified_savings_kgco2e": v.verified_savings_kgco2e,
            "ci_lower": v.ci_lower, "ci_upper": v.ci_upper,
            "verification_status": v.verification_status,
            "sla_compliant": v.sla_compliant,
            "evidence_chain": v.evidence_chain,
        } for v in verifications]
        with open(f"{self.output_dir}/evidence_chains.json", "w") as f:
            json.dump(evidence_data, f, indent=2, default=str)

        # Trace
        agent_traces = {"single_model": agent_result["trace"]}
        with open(f"{self.output_dir}/agent_traces.json", "w") as f:
            json.dump(agent_traces, f, indent=2, default=str)

        # No multi-round dialogues in single-model mode
        with open(f"{self.output_dir}/agent_dialogues.json", "w") as f:
            json.dump([], f)

        # Pipeline summary — same shape as multi-agent + arch tag
        from config import Config
        carbon_price = Config.CARBON_PRICE_PER_TON
        impact = compute_business_impact(
            kg_co2e_saved=actual_reduction,
            cost_change_usd=cost_change,
            total_cloud_spend=total_baseline_cost,
        )
        elapsed = round(time.time() - start_time, 2)

        summary = {
            "timestamp": datetime.now().isoformat(),
            "llm_provider": self.llm.provider,
            "simulation_days": sim_days,
            "total_jobs": len(jobs),
            "baseline": {
                "total_emissions_kgco2e": round(total_baseline_kgco2e, 4),
                "total_cost_usd": round(total_baseline_cost, 2),
                "effective_cost_usd": round(total_baseline_cost + total_baseline_kgco2e / 1000 * carbon_price, 2),
            },
            "optimized": {
                "total_emissions_kgco2e": round(total_post_kgco2e, 4),
                "total_cost_usd": round(post_cost, 2),
                "effective_cost_usd": round(post_cost + total_post_kgco2e / 1000 * carbon_price, 2),
            },
            "improvement": {
                "emissions_reduction_kgco2e": round(actual_reduction, 4),
                "emissions_reduction_pct": round(actual_reduction / max(total_baseline_kgco2e, 1e-9) * 100, 1),
                "cost_change_usd": cost_change,
            },
            "impact": impact,
            "pipeline": {
                "recommendations_generated": len(recommendations),
                "recommendations_approved": len(approved_recs),
                "recommendations_executed": len(execution_records),
                "verifications_completed": len(verifications),
                "verification_summary": verify_summary,
                "negotiation_dialogues": 0,
                "replan_cycles": 0,
                "final_significance_ratio": (
                    sum(1 for v in verifications if v.ci_lower > 0 and v.verified_savings_kgco2e > 0)
                    / max(len(verifications), 1)
                ),
            },
            "gamification": {
                "total_points_awarded": sum(e.points for e in points_entries),
                "teams_with_points": len(set(e.team_id for e in points_entries)),
                "leaderboard_top3": leaderboard[:3] if leaderboard else [],
            },
            "agents": {
                "single_model": {
                    "reasoning_steps": len(self.agent.reasoning_trace),
                    "actions_taken": len(self.agent.action_log),
                },
            },
            "architecture": "single_model",
            "llm_usage": {
                "provider": self.llm.provider,
                "model": getattr(self.llm, "_model", "unknown"),
                "total_tokens": self.llm.total_tokens_used,
                "prompt_tokens": self.llm.total_prompt_tokens,
                "completion_tokens": self.llm.total_completion_tokens,
                "llm_calls": self.llm.call_count,
                "wall_clock_seconds": elapsed,
            },
        }
        with open(f"{self.output_dir}/pipeline_summary.json", "w") as f:
            json.dump(summary, f, indent=2, default=str)

        if team_summary:
            with open(f"{self.output_dir}/sample_team_narrative.md", "w") as f:
                f.write(team_summary)
        if execution_records:
            with open(f"{self.output_dir}/sample_ticket.md", "w") as f:
                f.write(execution_records[0].ticket_body)
        if verifications:
            with open(f"{self.output_dir}/sample_evidence_chain.txt", "w") as f:
                f.write(format_evidence_chain(verifications[0]))

        self._section("COMPLETE — Single Model")
        self._log(f"Total runtime: {elapsed}s")
        self._log(
            f"Emissions: {total_baseline_kgco2e:.1f} → {total_post_kgco2e:.1f} kgCO2e "
            f"(-{actual_reduction:.1f}, {actual_reduction/max(total_baseline_kgco2e, 1e-9)*100:.1f}%)"
        )
        return summary

    @staticmethod
    def _compute_leaderboard(points_entries) -> list[dict]:
        teams = {}
        for e in points_entries:
            t = teams.setdefault(e.team_id, {"team_id": e.team_id, "total_points": 0, "total_kgco2e_saved": 0.0})
            t["total_points"] += e.points
            t["total_kgco2e_saved"] += e.kgco2e_saved
        ordered = sorted(teams.values(), key=lambda t: -t["total_points"])
        for i, row in enumerate(ordered):
            row["rank"] = i + 1
        return ordered
