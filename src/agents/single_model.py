"""
Single-Model Agent
==================
A "one big LLM" alternative to the multi-agent (Planner + Governance + Executor
+ Copilot) pipeline. Used by run_pipeline_single.py for the architecture A/B
comparison.

Design contract (kept identical to multi-agent so the comparison is fair):

  - Carbon Accountant runs deterministically BEFORE this agent (computes
    baseline kgCO2e for every job).
  - Candidate optimizations are generated deterministically by the same
    PlannerAgent scoring loop. The LLM does not "discover" which jobs to
    target — that's a deterministic floor in both architectures.
  - Verifier runs deterministically AFTER this agent (counterfactual MRV).
  - Copilot points math is deterministic (POINTS_PER_KG_CO2E_SAVED).

The ONLY thing this agent changes vs multi-agent: the LLM-facing reasoning
that produces rationale + approve/reject + risk_assessment + ticket_body +
team_summary collapses from FOUR specialist prompts (planner / governance /
executor / copilot) into ONE mega-prompt per batch.

Output schema matches the multi-agent pipeline's so the dashboard can read
either run transparently.
"""

import copy
import json
import re
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Optional

from config import Config
from src.agents.base import LLMProvider
from src.agents.governance import GovernanceDecision
from src.agents.executor import ExecutionRecord
from src.agents.planner import PlannerAgent
from src.shared.models import Job, Recommendation


# How many recommendations to send in one LLM call. The merged JSON output for
# 50 candidates with full ticket bodies stays under typical 4k-token caps even
# on the small Groq model.
DEFAULT_BATCH_SIZE = 50


class SingleModelAgent:
    """
    One-LLM-call-per-batch alternative to the multi-agent pipeline.

    Args:
        llm: LLMProvider configured with the desired model (Groq small or
             Anthropic frontier). The architecture is what we're comparing,
             so the same LLMProvider class is used both ways.
        batch_size: Recommendations per LLM call.
    """

    SYSTEM_PROMPT = (
        "You are the Carbon Optimization Co-Pilot for a cloud platform team. "
        "You play FOUR roles in one pass: PLANNER (justify recommendations), "
        "GOVERNANCE (approve/reject + risk), EXECUTOR (write ticket bodies), "
        "and COPILOT (write a team summary).\n\n"
        "Hard rules:\n"
        "  1. Output ONLY valid JSON matching the requested schema. No prose "
        "outside the JSON.\n"
        "  2. All numbers (carbon_delta_kg, cost_delta_usd, confidence) are "
        "PROVIDED. Do not change them. You justify; you do not recompute.\n"
        "  3. Reject when cost_delta_pct exceeds the policy guardrail or when "
        "a high-risk production workload would be moved without rollback.\n"
        "  4. No multi-round dialogue. One pass, one decision per "
        "recommendation.\n"
        "  5. Be honest — if savings are small, say so. Never claim savings "
        "that aren't verified yet.\n"
    )

    def __init__(self, llm: LLMProvider, batch_size: int = DEFAULT_BATCH_SIZE):
        self.llm = llm
        self.batch_size = batch_size
        self.name = "Single-Model Agent"
        self.purpose = (
            "One LLM call per batch — combine planner / governance / executor "
            "/ copilot duties into a single prompt for an architecture A/B."
        )
        self.reasoning_trace: list[dict] = []
        self.action_log: list[dict] = []

    # ── Public entry point ────────────────────────────────────────────

    def run(
        self,
        jobs: list[Job],
        intensity_df,
        time_resolution_hours: int = 4,
        verbose: bool = True,
    ) -> dict:
        """
        Generate candidate optimizations deterministically (using the existing
        Planner scoring), then make one LLM call per batch to produce all the
        downstream artifacts the multi-agent pipeline produces.

        Returns the same keys as the multi-agent pipeline so the orchestrator
        can write the same CSVs.
        """
        # Step 1: deterministic candidate generation (shared with multi-agent)
        candidates = self._generate_candidates(jobs, intensity_df, time_resolution_hours, verbose)

        if verbose:
            print(f"  [SingleModel] {len(candidates)} candidate recommendations to judge")

        # Track jobs that get mutated copies; the orchestrator picks these up
        # alongside unchanged_jobs to assemble the post-optimization workload.
        self._optimized_jobs: list[Job] = []

        if not candidates:
            return {
                "recommendations": [],
                "approved_recs": [],
                "decisions": [],
                "execution_records": [],
                "optimized_jobs": [],
                "team_summary": "",
                "narratives": {},
                "trace": self._build_trace(),
            }

        # Step 2: chunked single-LLM-call decision-making
        all_decisions: dict[str, dict] = {}
        team_summaries: list[str] = []

        for batch_idx, batch in enumerate(self._chunk(candidates, self.batch_size)):
            if verbose:
                print(f"  [SingleModel] LLM call {batch_idx + 1} ({len(batch)} candidates)")
            llm_output = self._call_llm_for_batch(batch)
            for decision in llm_output.get("decisions", []):
                rid = decision.get("recommendation_id")
                if rid:
                    all_decisions[rid] = decision
            ts = llm_output.get("team_summary", "").strip()
            if ts:
                team_summaries.append(ts)

        # Step 3: assemble output objects in the same shapes the multi-agent
        # pipeline produces, so the orchestrator can serialize them uniformly.
        approved_recs: list[Recommendation] = []
        decisions: list[GovernanceDecision] = []
        execution_records: list[ExecutionRecord] = []

        job_map = {j.job_id: j for j in jobs}

        for rec in candidates:
            judgement = all_decisions.get(rec.recommendation_id, {})
            approved = bool(judgement.get("approve", False))
            rationale = judgement.get("rationale") or rec.rationale or ""
            risk_text = judgement.get("risk_assessment", "")
            ticket = judgement.get("ticket_body", "")

            rec.rationale = rationale or rec.rationale
            rec.status = "approved" if approved else "rejected"

            decisions.append(GovernanceDecision(
                recommendation_id=rec.recommendation_id,
                original_risk_level=rec.risk_level,
                final_risk_level=rec.risk_level,
                decision="approved" if approved else "rejected",
                reason=risk_text or ("Single-model approval" if approved
                                     else "Single-model rejection — see risk_assessment"),
                llm_reasoning=risk_text,
                decided_at=datetime.now(),
                decided_by="single_model",
            ))

            if approved:
                rec.status = "approved"
                approved_recs.append(rec)
                original_job = job_map.get(rec.job_id)
                if original_job is None:
                    continue
                # Mirror ExecutorAgent: deepcopy → mutate the copy, leave original untouched
                # so the Verifier can compute counterfactual emissions correctly.
                new_job = copy.deepcopy(original_job)
                old_config = {"region": original_job.region,
                              "started_at": str(original_job.started_at)}
                if rec.proposed_region and rec.proposed_region != original_job.region:
                    new_job.region = rec.proposed_region
                if rec.proposed_time and rec.proposed_time != original_job.started_at:
                    new_job.started_at = rec.proposed_time
                    new_job.ended_at = rec.proposed_time + timedelta(
                        hours=original_job.duration_hours
                    )
                new_config = {"region": new_job.region,
                              "started_at": str(new_job.started_at)}
                self._optimized_jobs.append(new_job)
                # Verifier requires status == "executed"
                rec.status = "executed"

                execution_records.append(ExecutionRecord(
                    execution_id=str(uuid.uuid4())[:8],
                    recommendation_id=rec.recommendation_id,
                    job_id=rec.job_id,
                    action_taken=rec.action_type,
                    old_config=old_config,
                    new_config=new_config,
                    execution_status="success",
                    mock_ticket_id=f"SUST-{rec.recommendation_id[:6].upper()}",
                    mock_pr_url=f"https://github.com/example/repo/pull/{rec.recommendation_id[:4]}",
                    ticket_body=ticket or self._template_ticket(rec),
                    executed_at=datetime.now(),
                    executed_by="single_model",
                ))

        team_summary = "\n\n".join(team_summaries) if team_summaries else ""

        self.reasoning_trace.append({
            "step": "single_model_complete",
            "content": (
                f"{len(candidates)} candidates → {len(approved_recs)} approved "
                f"in {self.llm.call_count} LLM calls "
                f"({self.llm.total_tokens_used} tokens)."
            ),
            "timestamp": datetime.now().isoformat(),
        })

        return {
            "recommendations": candidates,
            "approved_recs": approved_recs,
            "decisions": decisions,
            "execution_records": execution_records,
            "optimized_jobs": self._optimized_jobs,
            "team_summary": team_summary,
            "narratives": {"_aggregate": team_summary} if team_summary else {},
            "trace": self._build_trace(),
        }

    # ── Internals ─────────────────────────────────────────────────────

    def _generate_candidates(
        self,
        jobs: list[Job],
        intensity_df,
        time_resolution_hours: int,
        verbose: bool,
    ) -> list[Recommendation]:
        """Reuse the Planner's deterministic candidate generation.

        We instantiate a fresh PlannerAgent but bypass its LLM enrichment by
        using a mock LLM — we want only the deterministic scoring output.
        """
        # Build a temporary Planner with a mock LLM so its rationale enrichment
        # doesn't touch our real LLM provider's token budget.
        scoring_llm = LLMProvider(provider="mock")
        planner = PlannerAgent(llm=scoring_llm)
        result = planner.run({
            "jobs": jobs,
            "intensity_df": intensity_df,
            "time_resolution_hours": time_resolution_hours,
            "verbose": verbose,
        })
        return result["recommendations"]

    def _call_llm_for_batch(self, batch: list[Recommendation]) -> dict:
        user_payload = {
            "policy": {
                "MIN_CARBON_REDUCTION_PCT": Config.MIN_CARBON_REDUCTION_PCT,
                "MAX_COST_INCREASE_PCT": Config.MAX_COST_INCREASE_PCT,
                "CARBON_PRICE_PER_TON": Config.CARBON_PRICE_PER_TON,
            },
            "candidates": [self._rec_to_dict(r) for r in batch],
            "schema": {
                "decisions": [
                    {"recommendation_id": "str", "approve": "bool",
                     "rationale": "str (2-3 sentences)",
                     "risk_assessment": "str (1-2 sentences)",
                     "ticket_body": "str (markdown, only when approve=true)"}
                ],
                "team_summary": "str (one paragraph aggregate)",
            },
        }
        prompt = json.dumps(user_payload, default=str)

        raw = self.llm.chat(self.SYSTEM_PROMPT, prompt, temperature=0.2)
        self.action_log.append({
            "tool": "llm_batch_call",
            "inputs": {"batch_size": len(batch)},
            "output_preview": (raw or "")[:200],
            "timestamp": datetime.now().isoformat(),
        })

        parsed = self._parse_json_response(raw, fallback_batch=batch)
        return parsed

    def _parse_json_response(self, raw: str, fallback_batch: list[Recommendation]) -> dict:
        if not raw:
            return self._deterministic_fallback(fallback_batch)
        # Strip code fences if present
        cleaned = raw.strip()
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.MULTILINE).strip()
        # Find the outermost JSON object
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return self._deterministic_fallback(fallback_batch)
        try:
            return json.loads(cleaned[start:end + 1])
        except json.JSONDecodeError:
            return self._deterministic_fallback(fallback_batch)

    def _deterministic_fallback(self, batch: list[Recommendation]) -> dict:
        """If the LLM returns nothing parseable, mirror multi-agent's
        deterministic behavior: approve everything that meets policy
        thresholds, with template rationales. Keeps the comparison honest —
        a parse failure isn't an architecture failure, it's a model failure."""
        decisions = []
        for rec in batch:
            cost_pct = (rec.est_cost_delta_usd / max(abs(rec.est_carbon_delta_kg) * 1000, 0.01))
            approve = (
                rec.est_carbon_delta_kg < 0
                and cost_pct <= Config.MAX_COST_INCREASE_PCT
            )
            decisions.append({
                "recommendation_id": rec.recommendation_id,
                "approve": approve,
                "rationale": (
                    f"[fallback] {rec.action_type}: estimated "
                    f"{abs(rec.est_carbon_delta_kg)*1000:.1f} gCO2e reduction at "
                    f"${rec.est_cost_delta_usd:.4f} cost delta."
                ),
                "risk_assessment": "Auto-classified by deterministic fallback (LLM output unparseable).",
                "ticket_body": self._template_ticket(rec) if approve else "",
            })
        return {"decisions": decisions, "team_summary": ""}

    @staticmethod
    def _rec_to_dict(rec: Recommendation) -> dict:
        return {
            "recommendation_id": rec.recommendation_id,
            "job_id": rec.job_id,
            "action_type": rec.action_type,
            "current_region": rec.current_region,
            "proposed_region": rec.proposed_region,
            "current_time": rec.current_time.isoformat() if rec.current_time else None,
            "proposed_time": rec.proposed_time.isoformat() if rec.proposed_time else None,
            "est_carbon_delta_kg": round(rec.est_carbon_delta_kg, 6),
            "est_cost_delta_usd": round(rec.est_cost_delta_usd, 6),
            "confidence": round(rec.confidence, 3),
            "risk_level": rec.risk_level,
        }

    @staticmethod
    def _template_ticket(rec: Recommendation) -> str:
        delta_g = abs(rec.est_carbon_delta_kg) * 1000
        return (
            f"## Sustainability Optimization: {rec.action_type.replace('_', ' ').title()}\n\n"
            f"### Change\n"
            f"Move job `{rec.job_id}` from `{rec.current_region}` to `{rec.proposed_region}`.\n\n"
            f"### Estimated Impact\n"
            f"- Carbon reduction: ~{delta_g:.1f} gCO2e\n"
            f"- Cost delta: ${rec.est_cost_delta_usd:.4f}\n"
            f"- Risk level: {rec.risk_level}\n\n"
            f"### Verification\n"
            f"The deterministic Verifier will compute counterfactual savings post-execution.\n"
        )

    @staticmethod
    def _chunk(lst, size):
        for i in range(0, len(lst), size):
            yield lst[i:i + size]

    def _build_trace(self) -> dict:
        return {
            "agent": self.name,
            "purpose": self.purpose,
            "memory": {
                "reasoning_trace": self.reasoning_trace,
                "actions_taken": self.action_log,
            },
        }
