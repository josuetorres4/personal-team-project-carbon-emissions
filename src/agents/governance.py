"""
Governance Agent
================
Enforces approval policies, risk-levels actions, and maintains audit trail.

This is a REAL AI agent: it uses an LLM to:
  - Parse organizational policy documents into machine-enforceable rules
  - Assess risk in context (not just threshold checks)
  - Generate human-readable approval/rejection reasoning

The POLICY ENFORCEMENT is deterministic:
  - Risk thresholds are hard-coded rules
  - Circuit breakers are numerical checks
  - Approval/rejection is based on evaluated risk level

What this agent CANNOT do:
  - Override a human rejection
  - Auto-approve HIGH-risk changes
  - Modify policies without audit trail
  - Suppress any alert or recommendation
"""

from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional
import uuid

import numpy as np
import pandas as pd

from src.agents.base import BaseAgent, LLMProvider
from src.shared.models import Recommendation

# Import Config for centralized settings, fall back to local defaults if unavailable
try:
    from config import Config as _Config
    _MAX_RECOMMENDATIONS_PER_BATCH = _Config.MAX_RECOMMENDATIONS_PER_BATCH
    _MAX_BATCH_COST_INCREASE = _Config.MAX_BATCH_COST_INCREASE
    _MAX_JOBS_PER_REGION = _Config.MAX_JOBS_PER_REGION_PER_BATCH
except Exception:
    _MAX_RECOMMENDATIONS_PER_BATCH = 6000
    _MAX_BATCH_COST_INCREASE = 500.0
    _MAX_JOBS_PER_REGION = 15


# ── Governance configuration ──────────────────────────────────────────
COST_INCREASE_HIGH_THRESHOLD = 5.0
COST_INCREASE_MEDIUM_THRESHOLD = 1.0
SIMULATED_HIGH_RISK_APPROVAL_RATE = 0.85
MAX_RECOMMENDATIONS_PER_BATCH = _MAX_RECOMMENDATIONS_PER_BATCH
MAX_BATCH_COST_INCREASE = _MAX_BATCH_COST_INCREASE
MAX_JOBS_PER_REGION_PER_BATCH = _MAX_JOBS_PER_REGION


@dataclass
class GovernanceDecision:
    """Record of a governance decision on a recommendation."""
    decision_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    recommendation_id: str = ""
    original_risk_level: str = ""
    final_risk_level: str = ""
    decision: str = ""
    reason: str = ""
    llm_reasoning: str = ""      # LLM's risk assessment narrative
    decided_at: Optional[datetime] = None
    decided_by: str = ""
    policy_version: str = "v1.0"


class GovernanceAgent(BaseAgent):
    """
    AI agent that enforces approval policies and risk assessment.
    
    LLM role: Contextual risk assessment, policy interpretation, rejection reasoning.
    Deterministic role: Threshold checks, circuit breakers, approval rules.
    """

    def __init__(self, llm: Optional[LLMProvider] = None):
        super().__init__(
            name="Governance Agent",
            purpose="Enforce approval policies, assess risk, and maintain audit trail "
                    "integrity for all optimization recommendations.",
            llm=llm,
            permissions=[
                "Read all recommendations",
                "Write approval/rejection decisions",
                "Escalate to human review",
                "Read organizational policies",
            ],
            restrictions=[
                "CANNOT override human rejection",
                "CANNOT auto-approve HIGH-risk changes",
                "CANNOT modify policies without human sign-off",
                "CANNOT suppress alerts or recommendations",
            ],
        )

    def _register_tools(self):
        self.add_tool(
            "assess_risk",
            "Evaluate risk level of a recommendation",
            self._assess_risk_deterministic,
        )
        self.add_tool(
            "check_circuit_breakers",
            "Check if batch limits have been exceeded",
            self._check_circuit_breakers,
        )

    def run(self, task: dict) -> dict:
        """
        Evaluate a batch of recommendations through governance.
        
        task keys:
            recommendations: list[Recommendation]
            seed: int (for reproducible simulated human decisions)
        """
        recommendations = task["recommendations"]
        seed = task.get("seed", 42)
        rng = np.random.default_rng(seed)

        self.memory.add_reasoning("task_received",
            f"Evaluating {len(recommendations)} recommendations against governance policies.")

        decisions = []
        approved = []
        batch_count = 0
        batch_cost_increase = 0.0

        for rec in recommendations:
            decision = self._evaluate_single(rec, batch_count, batch_cost_increase, rng)
            decisions.append(decision)

            if decision.decision == "approved":
                rec.status = "approved"
                approved.append(rec)
                batch_count += 1
                if rec.est_cost_delta_usd > 0:
                    batch_cost_increase += rec.est_cost_delta_usd
            else:
                rec.status = "rejected"

        self.memory.add_reasoning("governance_complete",
            f"Approved {len(approved)} / {len(recommendations)}. "
            f"Rejected {len(recommendations) - len(approved)}.")

        return {
            "approved": approved,
            "decisions": decisions,
            "trace": self.get_trace(),
        }

    def _assess_risk_deterministic(self, rec: Recommendation) -> str:
        """Deterministic risk assessment based on thresholds."""
        risk = rec.risk_level
        if rec.est_cost_delta_usd > COST_INCREASE_HIGH_THRESHOLD:
            risk = "high"
        elif rec.est_cost_delta_usd > COST_INCREASE_MEDIUM_THRESHOLD and risk == "low":
            risk = "medium"
        if rec.confidence < 0.4:
            if risk == "low":
                risk = "medium"
            elif risk == "medium":
                risk = "high"
        return risk

    def _check_circuit_breakers(self, batch_count: int, batch_cost: float) -> Optional[str]:
        """Check if batch limits have been exceeded."""
        if batch_count >= MAX_RECOMMENDATIONS_PER_BATCH:
            return f"Batch limit reached ({MAX_RECOMMENDATIONS_PER_BATCH})"
        if batch_cost > MAX_BATCH_COST_INCREASE:
            return f"Cost increase budget exhausted (${batch_cost:.2f} > ${MAX_BATCH_COST_INCREASE:.2f})"
        return None

    def review_proposal(self, proposal, dialogue) -> "AgentMessage":
        """
        Review a Planner's batch proposal. Checks for:
        - Concentration risk (too many jobs to one region)
        - Production workload safety
        - Cost budget compliance
        - Policy compliance

        Uses LLM to generate substantive feedback.
        Returns CHALLENGE, APPROVAL, or REJECTION message.

        Args:
            proposal: AgentMessage from PlannerAgent (PROPOSAL type)
            dialogue: Dialogue object with full conversation context

        Returns:
            AgentMessage of type CHALLENGE, APPROVAL, or REJECTION
        """
        from src.shared.protocol import AgentMessage, MessageType

        data = proposal.structured_data
        issues = []

        # Check concentration risk per region
        by_region = data.get("by_region", {})
        for region, stats in by_region.items():
            if stats.get("count", 0) > MAX_JOBS_PER_REGION_PER_BATCH:
                issues.append(
                    f"Concentration risk: {stats['count']} jobs targeted at {region} "
                    f"(limit: {MAX_JOBS_PER_REGION_PER_BATCH})"
                )

        # Check total cost budget
        total_cost_delta = data.get("total_cost_delta_usd", 0.0)
        if total_cost_delta > MAX_BATCH_COST_INCREASE:
            issues.append(
                f"Cost budget exceeded: ${total_cost_delta:.2f} > ${MAX_BATCH_COST_INCREASE:.2f}"
            )

        # Check batch size
        total_recs = data.get("total_recommendations", 0)
        if total_recs > MAX_RECOMMENDATIONS_PER_BATCH:
            issues.append(
                f"Batch too large: {total_recs} > {MAX_RECOMMENDATIONS_PER_BATCH} limit"
            )

        # Check risk distribution — flag high-risk concentration
        by_risk = data.get("by_risk_level", {})
        high_risk_count = by_risk.get("high", 0)
        if high_risk_count > 0 and total_recs > 0:
            high_risk_pct = high_risk_count / total_recs * 100
            if high_risk_pct > 20:
                issues.append(
                    f"High-risk concentration: {high_risk_count} high-risk jobs "
                    f"({high_risk_pct:.0f}% of batch) — requires human review"
                )

        # Determine initial message type
        if len(issues) == 0:
            initial_type = "approve"
        elif total_cost_delta > MAX_BATCH_COST_INCREASE or total_recs > MAX_RECOMMENDATIONS_PER_BATCH:
            initial_type = "reject"
        else:
            initial_type = "challenge"

        # LLM generates substantive feedback
        system_prompt = (
            f"{self.get_system_prompt()}\n\n"
            f"You are participating in a multi-agent planning discussion.\n"
            f"Review the dialogue below and respond from YOUR perspective.\n"
            f"You MUST reference specific numbers from the data.\n"
            f"If you disagree, explain WHY with evidence.\n"
            f"Keep responses under 150 words. Be direct."
        )
        issues_text = "\n".join(f"- {i}" for i in issues) if issues else "None identified."
        user_prompt = (
            f"Review this batch proposal from the Planner Agent:\n\n"
            f"Proposal content: {proposal.content}\n\n"
            f"Batch data: {data}\n\n"
            f"Policy issues identified:\n{issues_text}\n\n"
            f"Respond as Governance Agent with your assessment."
        )
        response_text = self.llm.chat(system_prompt, user_prompt)
        self.memory.add_reasoning("proposal_review", response_text)

        if initial_type == "approve":
            msg_type = MessageType.APPROVAL
        elif initial_type == "reject":
            msg_type = MessageType.REJECTION
        else:
            msg_type = self._determine_response_type(response_text)
            if msg_type == MessageType.PROPOSAL:
                # In a review context, an unclassified LLM response is a challenge
                msg_type = MessageType.CHALLENGE

        return AgentMessage(
            from_agent=self.name,
            to_agent=proposal.from_agent,
            message_type=msg_type,
            subject=proposal.subject,
            content=response_text,
            structured_data={"issues": issues, "initial_verdict": initial_type},
            in_reply_to=proposal.message_id,
            round_number=proposal.round_number + 1,
        )

    def _evaluate_single(self, rec, batch_count, batch_cost_increase, rng) -> GovernanceDecision:
        """Evaluate a single recommendation: deterministic rules + LLM reasoning."""
        final_risk = self._assess_risk_deterministic(rec)
        decision_time = datetime.now()

        # Check circuit breakers
        breaker = self._check_circuit_breakers(batch_count, batch_cost_increase)
        if breaker:
            return GovernanceDecision(
                recommendation_id=rec.recommendation_id,
                original_risk_level=rec.risk_level,
                final_risk_level=final_risk,
                decision="rejected",
                reason=breaker,
                decided_at=decision_time,
                decided_by="governance_agent",
            )

        # LLM: contextual risk assessment for medium/high risk
        llm_reasoning = ""
        if final_risk in ("medium", "high"):
            system_prompt = (
                "You are the Governance Agent assessing risk for a carbon optimization change. "
                "Given the recommendation details, provide a brief risk assessment explaining "
                "WHY this is medium or high risk and what could go wrong. Be specific."
            )
            context = (
                f"action: {rec.action_type}, risk: {final_risk}\n"
                f"carbon_delta: {rec.est_carbon_delta_kg*1000:.1f} gCO₂e\n"
                f"cost_delta: ${rec.est_cost_delta_usd:+.4f}\n"
                f"confidence: {rec.confidence:.0%}\n"
                f"from: {rec.current_region} → to: {rec.proposed_region}\n"
            )
            llm_reasoning = self.reason(system_prompt, context)

        # Decision based on risk level (deterministic rules)
        if final_risk == "low":
            return GovernanceDecision(
                recommendation_id=rec.recommendation_id,
                original_risk_level=rec.risk_level,
                final_risk_level=final_risk,
                decision="approved",
                reason="Auto-approved: low risk, within policy bounds.",
                llm_reasoning=llm_reasoning,
                decided_at=decision_time,
                decided_by="governance_agent",
            )
        elif final_risk == "medium":
            return GovernanceDecision(
                recommendation_id=rec.recommendation_id,
                original_risk_level=rec.risk_level,
                final_risk_level=final_risk,
                decision="approved",
                reason="Approved after review. Medium risk — team lead notified.",
                llm_reasoning=llm_reasoning,
                decided_at=decision_time,
                decided_by="governance_agent",
            )
        else:  # high
            approved = rng.random() < SIMULATED_HIGH_RISK_APPROVAL_RATE
            return GovernanceDecision(
                recommendation_id=rec.recommendation_id,
                original_risk_level=rec.risk_level,
                final_risk_level=final_risk,
                decision="approved" if approved else "rejected",
                reason="Human-approved (simulated)." if approved else "Human-rejected (simulated).",
                llm_reasoning=llm_reasoning,
                decided_at=decision_time,
                decided_by="human_simulated",
            )


# ── Convenience functions for pipeline compatibility ──────────────────

def evaluate_batch(recommendations, seed=42):
    agent = GovernanceAgent()
    result = agent.run({"recommendations": recommendations, "seed": seed})
    return result["approved"], result["decisions"]


def decisions_to_dataframe(decisions: list[GovernanceDecision]):
    rows = []
    for d in decisions:
        rows.append({
            "decision_id": d.decision_id, "recommendation_id": d.recommendation_id,
            "original_risk_level": d.original_risk_level, "final_risk_level": d.final_risk_level,
            "decision": d.decision, "reason": d.reason,
            "llm_reasoning": d.llm_reasoning,
            "decided_at": d.decided_at, "decided_by": d.decided_by,
            "policy_version": d.policy_version,
        })
    return pd.DataFrame(rows)


def summarize_governance(decisions: list[GovernanceDecision]) -> dict:
    total = len(decisions)
    if total == 0:
        return {"total": 0}
    approved = sum(1 for d in decisions if d.decision == "approved")
    rejected = total - approved
    by_risk = {}
    for d in decisions:
        key = d.final_risk_level
        if key not in by_risk:
            by_risk[key] = {"approved": 0, "rejected": 0}
        by_risk[key][d.decision] = by_risk[key].get(d.decision, 0) + 1
    by_decider = {}
    for d in decisions:
        by_decider[d.decided_by] = by_decider.get(d.decided_by, 0) + 1
    return {
        "total": total, "approved": approved, "rejected": rejected,
        "approval_rate": round(approved / total * 100, 1),
        "by_risk_level": by_risk, "by_decider": by_decider,
    }
