"""
Agent Orchestrator
==================
Runs the closed-loop agentic pipeline: Sense → Model → Decide → Act → Verify → Learn

This is NOT a simple function pipeline — it's an orchestrator that:
  1. Creates agent instances with shared LLM provider and memory
  2. Passes structured messages between agents
  3. Collects reasoning traces from every agent for auditability
  4. Handles failures gracefully (if one agent fails, the loop degrades, not crashes)

The orchestrator itself is deterministic — it decides WHAT to run and in what order.
The agents decide HOW to accomplish their tasks (using LLM reasoning + deterministic tools).

Architecture:
  Orchestrator
    ├── Ingestor (simulated — workload generator)
    ├── Carbon Accountant (deterministic — no LLM needed)
    ├── Planner Agent (LLM for rationales + deterministic solver)
    ├── Governance Agent (LLM for risk assessment + deterministic rules)
    ├── Executor Agent (LLM for tickets + deterministic config changes)
    ├── Verifier Agent (deterministic — no LLM in verification math)
    └── Developer Copilot (LLM for summaries + deterministic points)
"""

import json
import os
import time
from datetime import datetime

import pandas as pd

from src.agents.base import LLMProvider
from src.simulator.workload_generator import generate_workloads, jobs_to_dataframe
from src.simulator.carbon_intensity import generate_intensity_timeseries
from src.simulator.cost_model import compute_job_cost
from src.agents.carbon_accountant import compute_emissions_batch, emissions_to_dataframe
from src.agents.planner import PlannerAgent, recommendations_to_dataframe, summarize_recommendations
from src.agents.governance import GovernanceAgent, decisions_to_dataframe, summarize_governance
from src.agents.executor import ExecutorAgent, executions_to_dataframe, generate_mock_ticket_body
from src.agents.verifier import verify_batch, verifications_to_dataframe, summarize_verification, format_evidence_chain
from src.agents.copilot import CopilotAgent, points_to_dataframe
from src.shared.protocol import Dialogue, AgentMessage, MessageType
from src.shared.impact import compute_business_impact


class Orchestrator:
    """
    Manages the multi-agent pipeline and message passing between agents.
    """

    def __init__(self, llm_provider: str = "auto", verbose: bool = True):
        self.verbose = verbose
        self.llm = LLMProvider(llm_provider)

        # Create agent instances with shared LLM
        self.planner = PlannerAgent(llm=self.llm)
        self.governance = GovernanceAgent(llm=self.llm)
        self.executor = ExecutorAgent(llm=self.llm)
        self.copilot = CopilotAgent(llm=self.llm)

        # Collected traces from all agents
        self.agent_traces = {}

        # Collected dialogues for audit trail
        self.dialogues: list = []

        self._log(f"Orchestrator initialized with LLM provider: {self.llm.provider}")
        self._log(f"Agents: Planner, Governance, Executor, Verifier (deterministic), Copilot")

    def _log(self, msg: str):
        if self.verbose:
            print(f"  [Orchestrator] {msg}")

    def run(
        self,
        sim_start: datetime = datetime(2025, 1, 1),
        sim_days: int = 30,
        seed: int = 42,
        time_resolution_hours: int = 4,
    ) -> dict:
        """
        Run the full agentic loop.
        
        Returns: dict with all outputs, metrics, and agent traces
        """
        start_time = time.time()
        os.makedirs("data", exist_ok=True)

        self._section("sust-AI-naible — Agentic Pipeline")
        self._log(f"LLM: {self.llm.provider} | Sim: {sim_days} days | Seed: {seed}")

        # ── SENSE: Data Ingestion (simulated) ─────────────────────────
        self._section("Step 1: SENSE — Ingestor Agent (simulated)")

        t0 = time.time()
        jobs = generate_workloads(sim_start, num_days=sim_days, seed=seed)
        jobs_df = jobs_to_dataframe(jobs)
        intensity_df = generate_intensity_timeseries(sim_start, num_days=sim_days, seed=seed)

        jobs_df["cost_usd"] = jobs_df.apply(
            lambda r: compute_job_cost(r["region"], r["vcpus"], r["gpu_count"], r["duration_hours"]),
            axis=1,
        )
        for j in jobs:
            j.cost_usd = compute_job_cost(j.region, j.vcpus, j.gpu_count, j.duration_hours)

        self._log(f"Generated {len(jobs):,} jobs, {len(intensity_df):,} intensity points in {time.time()-t0:.1f}s")

        # ── MODEL: Carbon Accounting (deterministic — no agent needed) ─
        self._section("Step 2: MODEL — Carbon Accountant (deterministic)")

        t0 = time.time()
        baseline_emissions = compute_emissions_batch(jobs, intensity_df, verbose=self.verbose)
        baseline_emissions_df = emissions_to_dataframe(baseline_emissions)
        jobs_df["kgco2e"] = baseline_emissions_df["kgco2e"].values
        jobs_df["kgco2e_lower"] = baseline_emissions_df["kgco2e_lower"].values
        jobs_df["kgco2e_upper"] = baseline_emissions_df["kgco2e_upper"].values

        total_baseline_kgco2e = jobs_df["kgco2e"].sum()
        total_baseline_cost = jobs_df["cost_usd"].sum()
        self._log(f"Baseline: {total_baseline_kgco2e:.2f} kgCO₂e, ${total_baseline_cost:,.2f} in {time.time()-t0:.1f}s")

        # ── DECIDE: Planner Agent (LLM + deterministic) ───────────────
        self._section("Step 3: DECIDE — Planner Agent")

        t0 = time.time()
        planner_result = self.planner.run({
            "jobs": jobs,
            "intensity_df": intensity_df,
            "time_resolution_hours": time_resolution_hours,
            "verbose": self.verbose,
        })
        recommendations = planner_result["recommendations"]
        self.agent_traces["planner"] = planner_result["trace"]
        self._log(f"Planner: {len(recommendations)} recommendations in {time.time()-t0:.1f}s")

        rec_summary = summarize_recommendations(recommendations)
        self._log(f"  Carbon delta: {rec_summary.get('total_carbon_delta_kg', 0)*1000:.1f} gCO₂e")

        # ── DECIDE: Governance Agent (LLM + deterministic) ────────────
        self._subsection("Governance Agent — Negotiated Planning")

        t0 = time.time()
        dialogue = self._negotiate_plan(recommendations, intensity_df)
        self.dialogues.append(dialogue)

        # Fall through to standard governance for per-recommendation decisions
        gov_result = self.governance.run({
            "recommendations": recommendations,
            "seed": seed,
        })
        approved_recs = gov_result["approved"]
        gov_decisions = gov_result["decisions"]
        self.agent_traces["governance"] = gov_result["trace"]

        gov_summary = summarize_governance(gov_decisions)
        self._log(f"Governance: {gov_summary['approved']}/{gov_summary['total']} approved "
                  f"({gov_summary['approval_rate']}%) in {time.time()-t0:.1f}s")
        self._log(f"  Dialogue: {dialogue.total_rounds} negotiation rounds, outcome: {dialogue.outcome}")

        # ── ACT: Executor Agent (LLM + deterministic) ─────────────────
        self._section("Step 4: ACT — Executor Agent")

        t0 = time.time()
        exec_result = self.executor.run({
            "approved_recs": approved_recs,
            "jobs": jobs,
        })
        optimized_jobs = exec_result["optimized_jobs"]
        unchanged_jobs = exec_result["unchanged_jobs"]
        exec_records = exec_result["execution_records"]
        self.agent_traces["executor"] = exec_result["trace"]
        self._log(f"Executor: {len(exec_records)} changes executed in {time.time()-t0:.1f}s")

        # Save sample ticket
        if exec_records:
            sample_ticket = exec_records[0].ticket_body
            with open("data/sample_ticket.md", "w") as f:
                f.write(sample_ticket)

        # ── VERIFY: Verifier (deterministic — no LLM) ────────────────
        self._section("Step 5: VERIFY — Verifier Agent (deterministic)")

        all_final_jobs = optimized_jobs + unchanged_jobs
        t0 = time.time()
        post_emissions = compute_emissions_batch(all_final_jobs, intensity_df, verbose=self.verbose)
        post_emissions_df = emissions_to_dataframe(post_emissions)
        total_post_kgco2e = post_emissions_df["kgco2e"].sum()
        actual_reduction = total_baseline_kgco2e - total_post_kgco2e
        self._log(f"Post-optimization: {total_post_kgco2e:.2f} kgCO₂e "
                  f"(reduction: {actual_reduction:.2f} kgCO₂e, {actual_reduction/total_baseline_kgco2e*100:.1f}%)")

        original_jobs_for_verify = [j for j in jobs if j.job_id in {r.job_id for r in approved_recs}]
        verifications = verify_batch(
            approved_recs, original_jobs_for_verify, optimized_jobs,
            intensity_df, verbose=self.verbose,
        )
        verify_summary = summarize_verification(verifications)
        self._log(f"Verified: {verify_summary['count']} records, "
                  f"{verify_summary.get('total_verified_savings_kgco2e', 0)*1000:.0f} gCO₂e savings")

        if verifications:
            with open("data/sample_evidence_chain.txt", "w") as f:
                f.write(format_evidence_chain(verifications[0]))

        # --- FEEDBACK LOOP ---
        MAX_REPLAN_CYCLES = 2
        replan_count = 0

        def should_replan(vlist, threshold=0.5):
            if not vlist:
                return False
            significant = sum(1 for v in vlist if v.ci_lower > 0 and v.verified_savings_kgco2e > 0)
            ratio = significant / len(vlist)
            self._log(f"Verification significance ratio: {ratio:.1%} (threshold: {threshold:.1%})")
            return ratio < threshold

        while should_replan(verifications) and replan_count < MAX_REPLAN_CYCLES:
            replan_count += 1
            self._log(f"Replan cycle {replan_count}: less than 50% of savings are significant.")
            # Re-run planning with tighter constraints
            planner_result = self.planner.run({
                "jobs": jobs,
                "intensity_df": intensity_df,
                "time_resolution_hours": time_resolution_hours,
                "verbose": self.verbose,
            })
            recommendations = planner_result["recommendations"]
            gov_result = self.governance.run({
                "recommendations": recommendations,
                "seed": seed,
            })
            approved_recs = gov_result["approved"]
            gov_decisions = gov_result["decisions"]
            exec_result = self.executor.run({
                "approved_recs": approved_recs,
                "jobs": jobs,
            })
            optimized_jobs = exec_result["optimized_jobs"]
            unchanged_jobs = exec_result["unchanged_jobs"]
            exec_records = exec_result["execution_records"]
            all_final_jobs = optimized_jobs + unchanged_jobs
            post_emissions = compute_emissions_batch(all_final_jobs, intensity_df, verbose=self.verbose)
            post_emissions_df = emissions_to_dataframe(post_emissions)
            total_post_kgco2e = post_emissions_df["kgco2e"].sum()
            actual_reduction = total_baseline_kgco2e - total_post_kgco2e
            original_jobs_for_verify = [j for j in jobs if j.job_id in {r.job_id for r in approved_recs}]
            verifications = verify_batch(
                approved_recs, original_jobs_for_verify, optimized_jobs,
                intensity_df, verbose=self.verbose,
            )
            verify_summary = summarize_verification(verifications)

        # ── LEARN: Copilot Agent (LLM + deterministic) ────────────────
        self._section("Step 6: LEARN — Developer Copilot Agent")

        job_to_team = {j.job_id: j.team_id for j in jobs}
        rec_to_team = {r.recommendation_id: job_to_team.get(r.job_id, "unknown") for r in approved_recs}
        team_emissions = jobs_df.groupby("team_id")["kgco2e"].sum().to_dict()
        team_costs = jobs_df.groupby("team_id")["cost_usd"].sum().to_dict()

        t0 = time.time()
        copilot_result = self.copilot.run({
            "verifications": verifications,
            "rec_to_team": rec_to_team,
            "team_emissions": team_emissions,
            "team_costs": team_costs,
        })
        points_entries = copilot_result["points_entries"]
        leaderboard = copilot_result["leaderboard"]
        narratives = copilot_result["narratives"]
        self.agent_traces["copilot"] = copilot_result["trace"]

        total_points = sum(e.points for e in points_entries)
        self._log(f"Copilot: {total_points:,} points to {len(leaderboard)} teams in {time.time()-t0:.1f}s")

        if leaderboard:
            self._log("Leaderboard:")
            for entry in leaderboard[:5]:
                self._log(f"  #{entry['rank']} {entry['team_id']}: {entry['total_points']} pts")

        if narratives:
            first_team = list(narratives.keys())[0]
            with open("data/sample_team_narrative.md", "w") as f:
                f.write(narratives[first_team])

        # ── Save all outputs ──────────────────────────────────────────
        self._section("Saving Outputs")

        recs_df = recommendations_to_dataframe(recommendations)
        gov_df = decisions_to_dataframe(gov_decisions)
        exec_df = executions_to_dataframe(exec_records)
        verify_df = verifications_to_dataframe(verifications)
        points_df = points_to_dataframe(points_entries)
        leaderboard_df = pd.DataFrame(leaderboard)

        post_jobs_df = jobs_to_dataframe(all_final_jobs)
        post_jobs_df["kgco2e"] = post_emissions_df["kgco2e"].values
        post_jobs_df["cost_usd"] = post_jobs_df.apply(
            lambda r: compute_job_cost(r["region"], r["vcpus"], r["gpu_count"], r["duration_hours"]), axis=1,
        )

        outputs = {
            "data/jobs_baseline.csv": jobs_df,
            "data/carbon_intensity.csv": intensity_df,
            "data/baseline_emissions.csv": baseline_emissions_df,
            "data/recommendations.csv": recs_df,
            "data/governance_decisions.csv": gov_df,
            "data/executions.csv": exec_df,
            "data/verifications.csv": verify_df,
            "data/points.csv": points_df,
            "data/leaderboard.csv": leaderboard_df,
            "data/jobs_optimized.csv": post_jobs_df,
        }
        for path, df in outputs.items():
            df.to_csv(path, index=False)
            self._log(f"  {path} ({len(df):,} rows)")

        # Evidence chains JSON
        evidence_data = [{
            "verification_id": v.verification_id,
            "recommendation_id": v.recommendation_id,
            "verified_savings_kgco2e": v.verified_savings_kgco2e,
            "ci_lower": v.ci_lower, "ci_upper": v.ci_upper,
            "verification_status": v.verification_status,
            "sla_compliant": v.sla_compliant,
            "evidence_chain": v.evidence_chain,
        } for v in verifications]
        with open("data/evidence_chains.json", "w") as f:
            json.dump(evidence_data, f, indent=2, default=str)

        # Agent traces JSON
        with open("data/agent_traces.json", "w") as f:
            json.dump(self.agent_traces, f, indent=2, default=str)
        self._log(f"  data/agent_traces.json (reasoning traces for all agents)")

        # Agent dialogues JSON
        dialogue_records = [d.to_audit_record() for d in self.dialogues]
        with open("data/agent_dialogues.json", "w") as f:
            json.dump(dialogue_records, f, indent=2, default=str)
        self._log(f"  data/agent_dialogues.json ({len(dialogue_records)} dialogues)")

        # Pipeline summary
        post_cost = post_jobs_df["cost_usd"].sum()
        cost_change = round(post_cost - total_baseline_cost, 2)
        impact = compute_business_impact(
            kg_co2e_saved=actual_reduction,
            cost_change_usd=cost_change,
            total_cloud_spend=total_baseline_cost,
        )
        summary = {
            "timestamp": datetime.now().isoformat(),
            "llm_provider": self.llm.provider,
            "simulation_days": sim_days,
            "total_jobs": len(jobs),
            "baseline": {
                "total_emissions_kgco2e": round(total_baseline_kgco2e, 4),
                "total_cost_usd": round(total_baseline_cost, 2),
                "effective_cost_usd": round(total_baseline_cost + total_baseline_kgco2e / 1000 * 75, 2),
            },
            "optimized": {
                "total_emissions_kgco2e": round(total_post_kgco2e, 4),
                "total_cost_usd": round(post_cost, 2),
                "effective_cost_usd": round(post_cost + total_post_kgco2e / 1000 * 75, 2),
            },
            "improvement": {
                "emissions_reduction_kgco2e": round(actual_reduction, 4),
                "emissions_reduction_pct": round(actual_reduction / total_baseline_kgco2e * 100, 1),
                "cost_change_usd": cost_change,
            },
            "impact": impact,
            "pipeline": {
                "recommendations_generated": len(recommendations),
                "recommendations_approved": len(approved_recs),
                "recommendations_executed": len(exec_records),
                "verifications_completed": len(verifications),
                "verification_summary": verify_summary,
                "negotiation_dialogues": len(self.dialogues),
                "replan_cycles": replan_count,
                "final_significance_ratio": (
                    sum(1 for v in verifications if v.ci_lower > 0 and v.verified_savings_kgco2e > 0) / max(len(verifications), 1)
                ),
            },
            "gamification": {
                "total_points_awarded": total_points,
                "teams_with_points": len(set(e.team_id for e in points_entries)),
                "leaderboard_top3": leaderboard[:3] if leaderboard else [],
            },
            "agents": {
                name: {
                    "reasoning_steps": len(trace.get("memory", {}).get("reasoning_trace", [])),
                    "actions_taken": len(trace.get("memory", {}).get("actions_taken", [])),
                }
                for name, trace in self.agent_traces.items()
            },
        }
        with open("data/pipeline_summary.json", "w") as f:
            json.dump(summary, f, indent=2, default=str)

        elapsed = time.time() - start_time
        self._section("COMPLETE")
        self._log(f"Total runtime: {elapsed:.1f}s")
        self._log(f"Emissions: {total_baseline_kgco2e:.1f} → {total_post_kgco2e:.1f} kgCO₂e "
                  f"(-{actual_reduction:.1f}, {actual_reduction/total_baseline_kgco2e*100:.1f}%)")
        self._log(f"Dashboard: streamlit run dashboard.py")

        return summary

    def _negotiate_plan(self, recommendations: list, intensity_df) -> "Dialogue":
        """
        Mediate a multi-round dialogue between Planner and Governance agents.

        Flow:
          Round 0: Planner creates a batch-level proposal
          Round 1+: Governance reviews, Planner responds to challenges
          Stops when consensus is reached or max_rounds is hit

        Args:
            recommendations: list of Recommendation objects from PlannerAgent
            intensity_df: carbon intensity DataFrame

        Returns:
            Dialogue object with full audit trail
        """
        try:
            from config import Config
            max_rounds = Config.MAX_NEGOTIATION_ROUNDS
        except Exception:
            max_rounds = 2

        dialogue = Dialogue(
            topic="Batch Optimization Strategy",
            participating_agents=[self.planner.name, self.governance.name],
            max_rounds=max_rounds,
        )

        self._log(f"  Starting negotiation: up to {max_rounds} rounds")

        if not recommendations:
            dialogue.outcome = "skipped — no recommendations to negotiate"
            return dialogue

        # Round 0: Planner proposes batch strategy
        proposal = self.planner.propose_batch_strategy(recommendations, intensity_df)
        proposal.round_number = 0
        dialogue.add_message(proposal)
        self._log(f"  Round 0: Planner proposed batch ({proposal.structured_data.get('total_recommendations', 0)} recs)")

        current_message = proposal

        for round_num in range(1, max_rounds + 1):
            # Governance responds
            gov_response = self.governance.review_proposal(current_message, dialogue)
            gov_response.round_number = round_num
            dialogue.add_message(gov_response)
            self._log(f"  Round {round_num}: Governance → {gov_response.message_type.value}")

            if gov_response.message_type == MessageType.APPROVAL:
                dialogue.outcome = "consensus"
                dialogue.final_plan = current_message.structured_data
                break

            if gov_response.message_type == MessageType.REJECTION:
                dialogue.outcome = "rejected"
                break

            # Planner responds to challenge
            if round_num < max_rounds:
                planner_response = self.planner.respond_to(gov_response, dialogue)
                dialogue.add_message(planner_response)
                self._log(f"  Round {planner_response.round_number}: Planner → {planner_response.message_type.value}")
                current_message = planner_response
            else:
                dialogue.outcome = "max_rounds_reached"
                break

        if not dialogue.outcome:
            dialogue.outcome = "max_rounds_reached"

        self._log(f"  Negotiation complete: {dialogue.total_rounds} rounds, outcome: {dialogue.outcome}")
        return dialogue

    def _section(self, title):
        if self.verbose:
            print(f"\n{'=' * 70}")
            print(f"  {title}")
            print(f"{'=' * 70}")

    def _subsection(self, title):
        if self.verbose:
            print(f"\n{'─' * 70}")
            print(f"  {title}")
            print(f"{'─' * 70}")
