"""
Executor Agent
==============
Translates approved recommendations into infrastructure changes.

This is a REAL AI agent: it uses an LLM to:
  - Generate contextual ticket descriptions (not string templates)
  - Assess execution risks and suggest rollback plans
  - Craft PR descriptions that explain the carbon rationale to developers

The EXECUTION itself is deterministic:
  - Apply region/time changes to job configs
  - Record execution status
  - Snapshot pre-action state for verification

What this agent CANNOT do:
  - Execute without governance approval
  - Self-approve recommendations
  - Modify production routing without canary flag
"""

from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional
import uuid
import copy

import pandas as pd

from src.agents.base import BaseAgent, LLMProvider
from src.shared.models import Job, Recommendation

# Import Config for centralized settings, fall back to local defaults if unavailable
try:
    from config import Config as _Config
    _MAX_LLM_TICKETS = _Config.MAX_LLM_TICKETS
except Exception:
    _MAX_LLM_TICKETS = 50

MAX_LLM_TICKETS = _MAX_LLM_TICKETS


@dataclass
class ExecutionRecord:
    """Record of an executed change."""
    execution_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    recommendation_id: str = ""
    job_id: str = ""
    action_taken: str = ""
    old_config: dict = field(default_factory=dict)
    new_config: dict = field(default_factory=dict)
    execution_status: str = "success"
    mock_ticket_id: str = ""
    mock_pr_url: str = ""
    ticket_body: str = ""       # LLM-generated ticket content
    executed_at: Optional[datetime] = None
    executed_by: str = "executor_agent"


class ExecutorAgent(BaseAgent):
    """
    AI agent that translates approved recommendations into changes.
    
    LLM role: Generate ticket content, PR descriptions, rollback plans.
    Deterministic role: Apply config changes, record execution state.
    """

    def __init__(self, llm: Optional[LLMProvider] = None):
        super().__init__(
            name="Executor Agent",
            purpose="Translate approved recommendations into concrete infrastructure "
                    "changes (tickets, PRs, scheduler configs) and track execution.",
            llm=llm,
            permissions=[
                "Read approved recommendations",
                "Create Jira tickets",
                "Create GitHub PRs",
                "Modify scheduler configs",
                "Write execution status to decision log",
            ],
            restrictions=[
                "CANNOT execute without governance approval",
                "CANNOT self-approve recommendations",
                "CANNOT modify production routing without canary",
                "CANNOT make changes outside approved recommendation scope",
            ],
        )

    def _register_tools(self):
        self.add_tool(
            "apply_config_change",
            "Apply a region or time change to a job configuration",
            self._apply_change,
        )
        self.add_tool(
            "generate_ticket",
            "Generate a Jira/Linear ticket for a change",
            self._generate_ticket,
        )

    def run(self, task: dict) -> dict:
        """
        Execute all approved recommendations.
        
        task keys:
            approved_recs: list[Recommendation]
            jobs: list[Job]
        """
        approved_recs = task["approved_recs"]
        jobs = task["jobs"]

        self.memory.add_reasoning("task_received",
            f"Executing {len(approved_recs)} approved recommendations.")

        job_map = {j.job_id: j for j in jobs}
        rec_job_ids = {r.job_id for r in approved_recs}

        optimized_jobs = []
        execution_records = []
        llm_ticket_count = 0

        for rec in approved_recs:
            original_job = job_map.get(rec.job_id)
            if original_job is None:
                continue

            # Deterministic: apply the change
            new_job, record = self._apply_change(rec, original_job)

            # LLM: generate ticket content (capped to avoid token limit)
            if llm_ticket_count < MAX_LLM_TICKETS:
                record.ticket_body = self._generate_ticket(rec, record)
                llm_ticket_count += 1
            else:
                record.ticket_body = self._generate_template_ticket(rec, record)

            optimized_jobs.append(new_job)
            execution_records.append(record)
            rec.status = "executed"

        unchanged_jobs = [j for j in jobs if j.job_id not in rec_job_ids]

        self.memory.add_reasoning("execution_complete",
            f"Executed {len(execution_records)} changes "
            f"({llm_ticket_count} LLM tickets, "
            f"{len(execution_records) - llm_ticket_count} template tickets). "
            f"{len(unchanged_jobs)} jobs unchanged.")

        return {
            "optimized_jobs": optimized_jobs,
            "unchanged_jobs": unchanged_jobs,
            "execution_records": execution_records,
            "trace": self.get_trace(),
        }

    def _apply_change(self, rec: Recommendation, original_job: Job) -> tuple:
        """Deterministic: apply config change to a job."""
        if rec.status != "approved":
            raise ValueError(f"Cannot execute non-approved recommendation: {rec.status}")

        new_job = copy.deepcopy(original_job)
        old_config = {"region": original_job.region, "started_at": str(original_job.started_at)}

        if rec.proposed_region and rec.proposed_region != original_job.region:
            new_job.region = rec.proposed_region
        if rec.proposed_time and rec.proposed_time != original_job.started_at:
            new_job.started_at = rec.proposed_time
            new_job.ended_at = rec.proposed_time + timedelta(hours=original_job.duration_hours)

        new_config = {"region": new_job.region, "started_at": str(new_job.started_at)}
        ticket_id = f"SUST-{hash(rec.recommendation_id) % 10000:04d}"
        pr_url = f"https://github.com/org/infra/pull/{hash(rec.recommendation_id) % 1000}"

        record = ExecutionRecord(
            recommendation_id=rec.recommendation_id,
            job_id=rec.job_id,
            action_taken=rec.action_type,
            old_config=old_config,
            new_config=new_config,
            execution_status="success",
            mock_ticket_id=ticket_id,
            mock_pr_url=pr_url,
            executed_at=datetime.now(),
        )
        return new_job, record

    def _generate_ticket(self, rec: Recommendation, execution: ExecutionRecord) -> str:
        """LLM: generate contextual ticket content."""
        system_prompt = (
            "You are the Executor Agent creating a Jira ticket for a carbon optimization change. "
            "Write a clear, professional ticket body that explains: "
            "1) What is being changed and why, "
            "2) The expected carbon and cost impact, "
            "3) Risk level and rollback plan, "
            "4) How verification will happen. "
            "Be concise. Use markdown formatting."
        )
        context = (
            f"action_type: {rec.action_type}\n"
            f"current_region: {execution.old_config.get('region', '?')}\n"
            f"proposed_region: {execution.new_config.get('region', '?')}\n"
            f"carbon_delta: {rec.est_carbon_delta_kg * 1000:.1f} gCO₂e\n"
            f"cost_delta: ${rec.est_cost_delta_usd:+.4f}\n"
            f"risk_level: {rec.risk_level}\n"
            f"confidence: {rec.confidence:.0%}\n"
            f"ticket_id: {execution.mock_ticket_id}\n"
            f"pr_url: {execution.mock_pr_url}\n"
        )
        return self.reason(system_prompt, context)

    def _generate_template_ticket(self, rec: Recommendation, execution: ExecutionRecord) -> str:
        """Deterministic: generate a template ticket when LLM call budget is exhausted."""
        action = rec.action_type.replace("_", " ").title()
        old_region = execution.old_config.get("region", "?")
        new_region = execution.new_config.get("region", "?")
        return (
            f"## Sustainability Optimization: {action}\n\n"
            f"**Change**: {old_region} -> {new_region}\n"
            f"**Carbon delta**: {rec.est_carbon_delta_kg * 1000:.1f} gCO₂e\n"
            f"**Cost delta**: ${rec.est_cost_delta_usd:+.4f}\n"
            f"**Risk level**: {rec.risk_level.upper()}\n"
            f"**Confidence**: {rec.confidence:.0%}\n\n"
            f"Rollback: revert to original configuration if SLA degradation detected within 24h.\n"
            f"Verification: Verifier Agent will assess actual savings via counterfactual analysis."
        )


# ── Convenience functions for pipeline compatibility ──────────────────

def execute_batch(approved_recs, jobs):
    agent = ExecutorAgent()
    result = agent.run({"approved_recs": approved_recs, "jobs": jobs})
    return result["optimized_jobs"], result["unchanged_jobs"], result["execution_records"]


def generate_mock_ticket_body(rec, execution):
    """Return the LLM-generated ticket body from the execution record."""
    return execution.ticket_body if hasattr(execution, 'ticket_body') and execution.ticket_body else "No ticket body generated."


def executions_to_dataframe(records: list[ExecutionRecord]):
    rows = []
    for r in records:
        rows.append({
            "execution_id": r.execution_id, "recommendation_id": r.recommendation_id,
            "job_id": r.job_id, "action_taken": r.action_taken,
            "old_region": r.old_config.get("region", ""),
            "new_region": r.new_config.get("region", ""),
            "execution_status": r.execution_status,
            "mock_ticket_id": r.mock_ticket_id, "mock_pr_url": r.mock_pr_url,
            "executed_at": r.executed_at,
        })
    return pd.DataFrame(rows)
