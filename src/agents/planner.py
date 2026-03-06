"""
Planner Agent
=============
Generates cost+carbon-optimal workload placement recommendations.

This is a REAL AI agent: it uses an LLM to:
  - Interpret workload context and generate human-readable rationales
  - Assess which recommendations are most impactful to surface first
  - Explain trade-offs in natural language

But the MATH is deterministic:
  - Scoring: effective_cost = cloud_cost + (kgCO₂e × carbon_price)
  - Constraints: hard limits on carbon increase, cost increase, SLA
  - Candidate evaluation: exhaustive search over feasible (region, time) pairs

This separation is deliberate: the LLM reasons and explains, the solver computes.
An auditor can verify every number without trusting the LLM.
"""

import pandas as pd
from datetime import datetime, timedelta
from typing import Optional

from src.agents.base import BaseAgent, LLMProvider
from src.shared.models import (
    Job, Recommendation, WorkloadCategory, REGIONS,
)
from src.agents.carbon_accountant import compute_emissions_for_config
from src.simulator.cost_model import compute_total_cost

# Import Config for centralized settings, fall back to local defaults if unavailable
try:
    from config import Config as _Config
    _CARBON_PRICE_PER_TON = _Config.CARBON_PRICE_PER_TON
    _MIN_CARBON_REDUCTION_PCT = _Config.MIN_CARBON_REDUCTION_PCT
    _MAX_COST_INCREASE_PCT = _Config.MAX_COST_INCREASE_PCT
    _MAX_LLM_RATIONALES = _Config.MAX_LLM_RATIONALES
except Exception:
    _CARBON_PRICE_PER_TON = 75.0
    _MIN_CARBON_REDUCTION_PCT = 10.0
    _MAX_COST_INCREASE_PCT = 20.0
    _MAX_LLM_RATIONALES = 10


# ── Planner configuration ────────────────────────────────────────────
CARBON_PRICE_PER_TON = _CARBON_PRICE_PER_TON
CARBON_PRICE_PER_KG = CARBON_PRICE_PER_TON / 1000

REQUIRE_CARBON_REDUCTION = True
MIN_CARBON_REDUCTION_PCT = _MIN_CARBON_REDUCTION_PCT
MAX_COST_INCREASE_PCT = _MAX_COST_INCREASE_PCT
MAX_LLM_RATIONALES = _MAX_LLM_RATIONALES

DEFERRAL_WINDOWS = {
    WorkloadCategory.URGENT: timedelta(hours=0),
    WorkloadCategory.BALANCED: timedelta(hours=4),
    WorkloadCategory.SUSTAINABLE: timedelta(hours=24),
}


class PlannerAgent(BaseAgent):
    """
    AI agent that plans carbon-optimal workload placement.
    
    LLM role: Generate explanations, interpret context, prioritize recommendations.
    Deterministic role: Score candidates, enforce constraints, compute deltas.
    """

    PLANNER_PROMPT = """
You are a carbon futures trader optimizing cloud workload scheduling.

You have a 72-hour carbon intensity forecast:
{forecast_json}

Current unscheduled flexible jobs:
{jobs_json}

Your job is to find the OPTIMAL window for each flexible job — not just
the cheapest current slot, but the best slot in the next 72 hours
given forecast uncertainty.

For each job, reason like a trader:
1. What is the current carbon cost if we run now?
2. What is the forecasted minimum carbon window in 72 hours?
3. What is the risk of waiting? (SLA, cost of delay, forecast uncertainty)
4. Is the saving worth the wait?

Return ONLY a JSON array:
[{{
  "job_id": "...",
  "action": "shift_time|shift_region|run_now",
  "target_window_utc": "ISO timestamp or null",
  "target_region": "region or null",
  "estimated_carbon_saving_kg": 0.0,
  "estimated_cost_delta_usd": 0.0,
  "confidence": "HIGH|MEDIUM|LOW",
  "trader_rationale": "one sentence: why this window beats running now"
}}]

Only recommend shifts with HIGH or MEDIUM confidence.
Do NOT recommend shifts that save less than 5% carbon.
"""

    def __init__(self, llm: Optional[LLMProvider] = None):
        super().__init__(
            name="Planner Agent",
            purpose="Generate cost+carbon-optimal workload placement recommendations "
                    "that respect SLA constraints and workload flexibility.",
            llm=llm,
            permissions=[
                "Read activity ledger",
                "Read emissions factors",
                "Read cost model",
                "Write recommendations to decision log",
            ],
            restrictions=[
                "CANNOT execute any changes",
                "CANNOT override SLA constraints",
                "CANNOT recommend changes that increase emissions",
                "CANNOT make recommendations without both cost AND carbon estimates",
            ],
        )

    def _register_tools(self):
        self.add_tool(
            "compute_emissions",
            "Compute kgCO₂e for a hypothetical (region, time) config",
            compute_emissions_for_config,
        )
        self.add_tool(
            "compute_cost",
            "Compute cloud cost for a (region, instance, duration) config",
            compute_total_cost,
        )

    def run(self, task: dict) -> dict:
        """
        Main agent loop: analyze jobs, generate recommendations with LLM rationales.
        
        task keys:
            jobs: list[Job]
            intensity_df: pd.DataFrame
            time_resolution_hours: int (default 4)
            verbose: bool
        """
        jobs = task["jobs"]
        intensity_df = task["intensity_df"]
        time_resolution = task.get("time_resolution_hours", 4)
        verbose = task.get("verbose", False)

        # Step 1: Agent reasons about the task
        self.memory.add_reasoning("task_received",
            f"Planning optimization for {len(jobs)} jobs. "
            f"Carbon price: ${CARBON_PRICE_PER_TON}/ton. "
            f"Constraints: must reduce carbon, max {MAX_COST_INCREASE_PCT}% cost increase.")

        # Step 2: Deterministic planning (scoring all candidates)
        recommendations = []
        skipped = 0
        considered = 0
        clean_regions = {"eu-north-1", "us-west-2"}

        for i, job in enumerate(jobs):
            if job.category == WorkloadCategory.URGENT:
                skipped += 1
                continue
            if job.region in clean_regions:
                skipped += 1
                continue

            considered += 1
            rec = self._plan_single_job(job, intensity_df, time_resolution)
            if rec is not None:
                recommendations.append(rec)

            if verbose and (i + 1) % 2000 == 0:
                print(f"  Planned {i + 1:,} / {len(jobs):,} jobs "
                      f"({len(recommendations)} recommendations so far)...")

        if verbose:
            print(f"  Planning complete: {considered:,} considered, "
                  f"{skipped:,} skipped, "
                  f"{len(recommendations):,} recommendations generated")

        self.memory.add_reasoning("planning_complete",
            f"Generated {len(recommendations)} recommendations from {considered} candidates. "
            f"Skipped {skipped} (urgent or already in clean regions).")

        # Step 3: LLM generates rationales for top recommendations
        self._enrich_with_llm_rationales(recommendations, verbose=verbose)

        self.memory.add_reasoning("rationales_generated",
            f"LLM generated explanations for top {min(MAX_LLM_RATIONALES, len(recommendations))} recommendations. "
            f"Remaining {max(0, len(recommendations) - MAX_LLM_RATIONALES)} used deterministic rationales.")

        return {
            "recommendations": recommendations,
            "stats": {
                "total_jobs": len(jobs),
                "considered": considered,
                "skipped": skipped,
                "recommendations": len(recommendations),
            },
            "trace": self.get_trace(),
        }

    def _enrich_with_llm_rationales(self, recommendations: list[Recommendation], verbose: bool = False):
        """Use LLM to generate human-readable rationales for top recommendations.
        
        To avoid blocking for a long time on thousands of individual LLM calls,
        only the top MAX_LLM_RATIONALES recommendations (by carbon impact) get
        individual LLM rationales.  The rest receive a fast deterministic template.
        """
        if not recommendations:
            return

        system_prompt = (
            "You are the Planner Agent in a carbon optimization system. "
            "Given the details of a workload optimization recommendation, "
            "explain WHY this change reduces carbon emissions in 2-3 clear sentences. "
            "Be specific about grid differences. Mention cost impact. "
            "Never exaggerate. If the savings are small, say so honestly."
        )

        # Sort by carbon impact (most negative = biggest reduction first)
        sorted_recs = sorted(recommendations, key=lambda r: r.est_carbon_delta_kg)
        llm_limit = min(MAX_LLM_RATIONALES, len(sorted_recs))
        llm_recs = sorted_recs[:llm_limit]
        template_recs = sorted_recs[llm_limit:]

        if verbose:
            print(f"  Generating LLM rationales for top {llm_limit} recommendations "
                  f"({len(template_recs)} will use deterministic rationale)...")

        # LLM rationales for top recommendations
        for i, rec in enumerate(llm_recs):
            context = (
                f"action_type: {rec.action_type}\n"
                f"current_region: {rec.current_region}\n"
                f"proposed_region: {rec.proposed_region}\n"
                f"carbon_delta: {rec.est_carbon_delta_kg * 1000:.1f} gCO₂e\n"
                f"cost_delta: ${rec.est_cost_delta_usd:+.4f}\n"
                f"risk_level: {rec.risk_level}\n"
                f"confidence: {rec.confidence:.0%}\n"
            )
            try:
                rationale = self.reason(system_prompt, context)
            except Exception:
                rationale = None

            # Fall back to deterministic rationale if LLM failed or returned a fallback marker
            if rationale is None or rationale.startswith("["):
                rationale = (
                    f"Shifting {rec.action_type.replace('_', ' ')} from {rec.current_region} "
                    f"to {rec.proposed_region} saves {abs(rec.est_carbon_delta_kg * 1000):.1f} gCO₂e "
                    f"(cost delta: ${rec.est_cost_delta_usd:+.4f}, confidence: {rec.confidence:.0%})."
                )
            rec.rationale = rationale

            if verbose and (i + 1) % 10 == 0:
                print(f"  LLM rationales: {i + 1} / {llm_limit} complete...")

        # Deterministic rationales for remaining recommendations
        for rec in template_recs:
            rec.rationale = (
                f"Shifting {rec.action_type.replace('_', ' ')} from {rec.current_region} "
                f"to {rec.proposed_region} saves {abs(rec.est_carbon_delta_kg * 1000):.1f} gCO₂e "
                f"(cost delta: ${rec.est_cost_delta_usd:+.4f}, confidence: {rec.confidence:.0%})."
            )

        if verbose:
            print(f"  Rationale enrichment complete: {llm_limit} LLM + {len(template_recs)} deterministic")

    def propose_batch_strategy(self, batch_proposals: list, intensity_df) -> "AgentMessage":
        """
        Create a batch-level proposal that the Governance agent can review.

        Groups recommendations by target region, summarizes totals.
        Uses LLM to generate a strategic rationale for the batch.
        Returns an AgentMessage of type PROPOSAL.

        Args:
            batch_proposals: list of Recommendation objects
            intensity_df: carbon intensity DataFrame

        Returns:
            AgentMessage with structured_data containing aggregate stats
        """
        from src.shared.protocol import AgentMessage, MessageType

        # Group by proposed region
        by_region: dict = {}
        for rec in batch_proposals:
            region = rec.proposed_region
            if region not in by_region:
                by_region[region] = {
                    "count": 0,
                    "total_carbon_delta_kg": 0.0,
                    "total_cost_delta_usd": 0.0,
                }
            by_region[region]["count"] += 1
            by_region[region]["total_carbon_delta_kg"] += rec.est_carbon_delta_kg
            by_region[region]["total_cost_delta_usd"] += rec.est_cost_delta_usd

        total_carbon_delta = sum(r.est_carbon_delta_kg for r in batch_proposals)
        total_cost_delta = sum(r.est_cost_delta_usd for r in batch_proposals)
        by_risk = {}
        for r in batch_proposals:
            by_risk[r.risk_level] = by_risk.get(r.risk_level, 0) + 1

        structured_data = {
            "total_recommendations": len(batch_proposals),
            "total_carbon_delta_kg": round(total_carbon_delta, 4),
            "total_cost_delta_usd": round(total_cost_delta, 4),
            "by_region": {k: {
                "count": v["count"],
                "total_carbon_delta_kg": round(v["total_carbon_delta_kg"], 4),
                "total_cost_delta_usd": round(v["total_cost_delta_usd"], 4),
            } for k, v in by_region.items()},
            "by_risk_level": by_risk,
        }

        # LLM generates strategic rationale
        system_prompt = (
            f"{self.get_system_prompt()}\n\n"
            f"You are participating in a multi-agent planning discussion.\n"
            f"Review the dialogue below and respond from YOUR perspective.\n"
            f"You MUST reference specific numbers from the data.\n"
            f"Keep responses under 150 words. Be direct."
        )
        user_prompt = (
            f"Summarize this batch strategy for governance review:\n"
            f"Total recommendations: {len(batch_proposals)}\n"
            f"Total carbon reduction: {total_carbon_delta*1000:.1f} gCO₂e\n"
            f"Total cost change: ${total_cost_delta:+.2f}\n"
            f"By region: {by_region}\n"
            f"By risk: {by_risk}\n\n"
            f"Why is this batch a sound optimization strategy?"
        )
        rationale = self.llm.chat(system_prompt, user_prompt)
        self.memory.add_reasoning("batch_proposal", rationale)

        return AgentMessage(
            from_agent=self.name,
            to_agent="Governance Agent",
            message_type=MessageType.PROPOSAL,
            subject="Batch Optimization Strategy Proposal",
            content=rationale,
            structured_data=structured_data,
            round_number=0,
        )

    def _plan_single_job(
        self, job: Job, intensity_df: pd.DataFrame, time_resolution: int,
    ) -> Optional[Recommendation]:
        """Deterministic scoring + constraint checking for a single job."""
        current = _score_config(job, job.region, job.started_at, intensity_df)

        candidate_regions = _get_candidate_regions(job)
        candidate_times = _get_candidate_times(job, time_resolution)

        feasible = []
        for region in candidate_regions:
            for start_time in candidate_times:
                if region == job.region and start_time == job.started_at:
                    continue

                candidate = _score_config(job, region, start_time, intensity_df)
                carbon_delta = candidate["kgco2e"] - current["kgco2e"]
                cost_delta = candidate["total_cloud_cost"] - current["total_cloud_cost"]

                if REQUIRE_CARBON_REDUCTION and carbon_delta >= 0:
                    continue
                if current["total_cloud_cost"] > 0:
                    if (cost_delta / current["total_cloud_cost"]) * 100 > MAX_COST_INCREASE_PCT:
                        continue

                feasible.append((candidate, region, start_time, carbon_delta, cost_delta))

        if not feasible:
            return None

        best_tuple = min(feasible, key=lambda t: t[0]["effective_cost"])
        best, best_region, best_time, carbon_delta, cost_delta = best_tuple

        carbon_reduction_pct = (abs(carbon_delta) / current["kgco2e"] * 100) if current["kgco2e"] > 0 else 0
        if carbon_reduction_pct < MIN_CARBON_REDUCTION_PCT:
            return None

        if best_region != job.region and best_time != job.started_at:
            action_type = "region_shift+time_shift"
        elif best_region != job.region:
            action_type = "region_shift"
        else:
            action_type = "time_shift"

        if job.category == WorkloadCategory.URGENT:
            risk_level = "high"
        elif abs(cost_delta) > 5.0 or job.workload_type == "production":
            risk_level = "high"
        elif abs(cost_delta) > 1.0:
            risk_level = "medium"
        else:
            risk_level = "low"

        if current["kgco2e"] > 0:
            uncertainty_ratio = (best["kgco2e_upper"] - best["kgco2e_lower"]) / current["kgco2e"]
            confidence = max(0.3, min(0.95, 1.0 - uncertainty_ratio))
        else:
            confidence = 0.5

        return Recommendation(
            job_id=job.job_id,
            action_type=action_type,
            current_region=job.region,
            proposed_region=best_region,
            current_time=job.started_at,
            proposed_time=best_time,
            est_carbon_delta_kg=round(carbon_delta, 6),
            est_cost_delta_usd=round(cost_delta, 4),
            confidence=round(confidence, 3),
            rationale="",  # Filled by LLM later
            status="proposed",
            risk_level=risk_level,
        )


# ── Pure functions (deterministic, no agent state) ────────────────────

def _get_candidate_regions(job: Job) -> list[str]:
    home_continent = REGIONS.get(job.region, {}).get("continent", "NA")
    if job.category == WorkloadCategory.URGENT:
        return [r for r, info in REGIONS.items() if info["continent"] == home_continent]
    else:
        return list(REGIONS.keys())


def _get_candidate_times(job: Job, resolution_hours: int = 2) -> list[datetime]:
    window = DEFERRAL_WINDOWS.get(job.category, timedelta(hours=0))
    if window.total_seconds() == 0:
        return [job.started_at]
    candidates = []
    t = job.started_at
    end = job.started_at + window
    while t <= end:
        candidates.append(t)
        t += timedelta(hours=resolution_hours)
    return candidates


def _score_config(job: Job, region: str, start_time: datetime, intensity_df: pd.DataFrame) -> dict:
    emissions = compute_emissions_for_config(
        vcpus=job.vcpus, gpu_count=job.gpu_count, duration_hours=job.duration_hours,
        region=region, timestamp=start_time, intensity_df=intensity_df,
    )
    cost = compute_total_cost(
        region=region, vcpus=job.vcpus, gpu_count=job.gpu_count,
        duration_hours=job.duration_hours, original_region=job.region,
        workload_type=job.workload_type,
    )
    carbon_cost = emissions["kgco2e"] * CARBON_PRICE_PER_KG
    effective_cost = cost["total_cost"] + carbon_cost
    return {
        "region": region, "start_time": start_time,
        "kgco2e": emissions["kgco2e"], "kgco2e_lower": emissions["kgco2e_lower"],
        "kgco2e_upper": emissions["kgco2e_upper"], "grid_intensity": emissions["grid_intensity"],
        "compute_cost": cost["compute_cost"], "egress_cost": cost["egress_cost"],
        "total_cloud_cost": cost["total_cost"],
        "carbon_cost": round(carbon_cost, 6), "effective_cost": round(effective_cost, 6),
    }


# ── Convenience functions for pipeline compatibility ──────────────────

def plan_batch(jobs, intensity_df, verbose=False, time_resolution_hours=4):
    """Convenience wrapper — creates agent and runs it."""
    agent = PlannerAgent()
    result = agent.run({
        "jobs": jobs,
        "intensity_df": intensity_df,
        "time_resolution_hours": time_resolution_hours,
        "verbose": verbose,
    })
    return result["recommendations"]


def recommendations_to_dataframe(recs: list[Recommendation]) -> pd.DataFrame:
    rows = []
    for r in recs:
        rows.append({
            "recommendation_id": r.recommendation_id, "job_id": r.job_id,
            "action_type": r.action_type, "current_region": r.current_region,
            "proposed_region": r.proposed_region, "current_time": r.current_time,
            "proposed_time": r.proposed_time, "est_carbon_delta_kg": r.est_carbon_delta_kg,
            "est_cost_delta_usd": r.est_cost_delta_usd, "confidence": r.confidence,
            "rationale": r.rationale, "status": r.status, "risk_level": r.risk_level,
        })
    return pd.DataFrame(rows)


def summarize_recommendations(recs: list[Recommendation]) -> dict:
    if not recs:
        return {"count": 0, "message": "No recommendations generated."}
    total_carbon = sum(r.est_carbon_delta_kg for r in recs)
    total_cost = sum(r.est_cost_delta_usd for r in recs)
    avg_conf = sum(r.confidence for r in recs) / len(recs)
    by_risk = {"low": 0, "medium": 0, "high": 0}
    by_action = {}
    for r in recs:
        by_risk[r.risk_level] = by_risk.get(r.risk_level, 0) + 1
        by_action[r.action_type] = by_action.get(r.action_type, 0) + 1
    return {
        "count": len(recs), "total_carbon_delta_kg": round(total_carbon, 4),
        "total_cost_delta_usd": round(total_cost, 4), "avg_confidence": round(avg_conf, 3),
        "by_risk_level": by_risk, "by_action_type": by_action,
    }
