"""
Developer Copilot Agent
=======================
Surfaces carbon/cost insights to developers and manages gamification.

This is a REAL AI agent: it uses an LLM to:
  - Generate natural-language team summaries ("carbon receipts")
  - Craft contextual nudges that are helpful, not annoying
  - Explain verification results in plain English

The POINTS MATH is deterministic:
  - Points per kgCO₂e saved: fixed formula
  - Only awarded after verification (not estimates)
  - SLA violation penalty: deterministic deduction

What this agent CANNOT do:
  - Block PRs or deployments (advisory only)
  - Award points for unverified savings
  - Share individual developer data publicly
  - Nag more than 2x/week per team
"""

from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional
import uuid

import pandas as pd

from src.agents.base import BaseAgent, LLMProvider
from src.shared.models import Recommendation, VerificationRecord


# ── Points configuration ──────────────────────────────────────────────
POINTS_PER_KG_CO2E_SAVED = 100
PARTIAL_MULTIPLIER = 0.5
SLA_VIOLATION_PENALTY = -50


@dataclass
class PointsEntry:
    entry_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    team_id: str = ""
    recommendation_id: str = ""
    verification_id: str = ""
    points: int = 0
    kgco2e_saved: float = 0.0
    reason: str = ""
    awarded_at: Optional[datetime] = None


class CopilotAgent(BaseAgent):
    """
    AI agent that interfaces with developer teams.
    
    LLM role: Generate summaries, nudges, explanations tailored to each team.
    Deterministic role: Points calculation, leaderboard ranking, carbon brokerage.
    """

    BROKER_PROMPT = """
You are a carbon market broker for an engineering organization.

Current carbon budget status across teams:
{budget_status_json}

Teams in SURPLUS (could sell/give carbon budget):
{surplus_teams}

Teams in DEFICIT (need more carbon budget):
{deficit_teams}

This week's verified savings by team:
{savings_by_team}

Your job:
1. Identify 1-3 fair trades that would help deficit teams without
   penalizing surplus teams unfairly
2. Write a short, motivating weekly summary for each team (2-3 sentences,
   conversational tone — like a coach, not a report)
3. Highlight the team that improved most this week

Return ONLY this JSON:
{{
  "proposed_trades": [
    {{
      "from_team": "...",
      "to_team": "...",
      "kg": 0.0,
      "rationale": "one sentence"
    }}
  ],
  "team_summaries": {{
    "TeamName": "2-3 sentence motivating message mentioning their specific numbers"
  }},
  "team_of_the_week": "TeamName",
  "team_of_the_week_reason": "one sentence"
}}
"""

    def __init__(self, llm: Optional[LLMProvider] = None):
        super().__init__(
            name="Developer Copilot",
            purpose="Surface contextual carbon/cost insights to developers, manage "
                    "gamification with verified-only points, and generate team reports.",
            llm=llm,
            permissions=[
                "Read verification results",
                "Read team activity data",
                "Write points to ledger",
                "Send notifications (advisory only)",
            ],
            restrictions=[
                "CANNOT block PRs or deployments",
                "CANNOT award points for unverified savings",
                "CANNOT share individual developer data publicly",
                "CANNOT send more than 2 notifications per team per week",
            ],
        )

    def _register_tools(self):
        self.add_tool(
            "calculate_points",
            "Calculate points for a verified carbon reduction",
            self._calculate_points,
        )
        self.add_tool(
            "generate_team_summary",
            "Generate a natural-language team carbon report",
            self._generate_team_summary_llm,
        )

    def run(self, task: dict) -> dict:
        """
        Process verifications → award points → generate summaries.
        
        task keys:
            verifications: list[VerificationRecord]
            rec_to_team: dict (recommendation_id → team_id)
            team_emissions: dict (team_id → total kgCO₂e)
            team_costs: dict (team_id → total cost USD)
        """
        verifications = task["verifications"]
        rec_to_team = task["rec_to_team"]
        team_emissions = task.get("team_emissions", {})
        team_costs = task.get("team_costs", {})

        self.memory.add_reasoning("task_received",
            f"Processing {len(verifications)} verifications for points and summaries.")

        # Step 1: Deterministic — calculate points
        points_entries = []
        for v in verifications:
            team_id = rec_to_team.get(v.recommendation_id, "unknown")
            entry = self._calculate_points(v, team_id)
            if entry:
                points_entries.append(entry)

        # Step 2: Deterministic — compute leaderboard
        leaderboard = self._compute_leaderboard(points_entries)

        # Step 3: LLM — generate team narratives
        narratives = {}
        for entry in leaderboard:
            team_id = entry["team_id"]
            narrative = self._generate_team_summary_llm(
                team_id=team_id,
                total_emissions=team_emissions.get(team_id, 0),
                avoided_kg=entry["total_kgco2e_saved"],
                points=entry["total_points"],
                rank=entry["rank"],
                total_teams=len(leaderboard),
            )
            narratives[team_id] = narrative

        total_points = sum(e.points for e in points_entries)
        self.memory.add_reasoning("copilot_complete",
            f"Awarded {total_points} points to {len(leaderboard)} teams. "
            f"Generated {len(narratives)} team summaries.")

        return {
            "points_entries": points_entries,
            "leaderboard": leaderboard,
            "narratives": narratives,
            "trace": self.get_trace(),
        }

    def run_as_broker(self, market) -> dict:
        """
        Run as a carbon market broker: analyze budgets and propose trades.
        
        Args:
            market: CarbonMarket instance
        
        Returns:
            dict with proposed_trades, team_summaries, team_of_the_week
        """
        import json as _json

        budget_status = market.to_dict()
        surplus_teams = market.find_surplus_teams()
        deficit_teams = market.find_deficit_teams()

        # Compute savings by team
        savings_by_team = {
            team: budget.saved_kg
            for team, budget in market.budgets.items()
        }

        prompt = self.BROKER_PROMPT.format(
            budget_status_json=_json.dumps(budget_status.get("budgets", {}), indent=2),
            surplus_teams=surplus_teams,
            deficit_teams=deficit_teams,
            savings_by_team=savings_by_team,
        )

        raw = self.llm.complete(prompt)

        # Try to parse LLM response as JSON
        try:
            import re
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                return _json.loads(match.group())
        except Exception:
            pass

        # Fallback: return empty structure
        self.memory.add_reasoning("broker_fallback",
            "LLM broker response could not be parsed. Returning empty trades.")
        return {
            "proposed_trades": [],
            "team_summaries": {},
            "team_of_the_week": None,
            "team_of_the_week_reason": "No trades proposed this week.",
        }

    def _calculate_points(self, verification: VerificationRecord, team_id: str) -> Optional[PointsEntry]:
        """Deterministic: calculate points from verified savings."""
        if verification.verification_status == "confirmed":
            points = int(verification.verified_savings_kgco2e * POINTS_PER_KG_CO2E_SAVED)
            reason = f"Verified savings: {verification.verified_savings_kgco2e * 1000:.1f} gCO₂e (confirmed)"
        elif verification.verification_status == "partial":
            points = int(verification.verified_savings_kgco2e * POINTS_PER_KG_CO2E_SAVED * PARTIAL_MULTIPLIER)
            reason = f"Partial savings: {verification.verified_savings_kgco2e * 1000:.1f} gCO₂e (50% credit)"
        else:
            return None

        if not verification.sla_compliant:
            points += SLA_VIOLATION_PENALTY
            reason += f" [SLA penalty: {SLA_VIOLATION_PENALTY}]"

        if points <= 0:
            return None

        return PointsEntry(
            team_id=team_id,
            recommendation_id=verification.recommendation_id,
            verification_id=verification.verification_id,
            points=points,
            kgco2e_saved=verification.verified_savings_kgco2e,
            reason=reason,
            awarded_at=datetime.now(),
        )

    def _compute_leaderboard(self, entries: list[PointsEntry]) -> list[dict]:
        """Deterministic: rank teams by points."""
        team_points = {}
        for e in entries:
            if e.team_id not in team_points:
                team_points[e.team_id] = {"points": 0, "kgco2e_saved": 0.0, "actions": 0}
            team_points[e.team_id]["points"] += e.points
            team_points[e.team_id]["kgco2e_saved"] += e.kgco2e_saved
            team_points[e.team_id]["actions"] += 1

        leaderboard = []
        for team_id, data in sorted(team_points.items(), key=lambda x: -x[1]["points"]):
            leaderboard.append({
                "team_id": team_id, "total_points": data["points"],
                "total_kgco2e_saved": round(data["kgco2e_saved"], 4),
                "total_actions": data["actions"],
            })
        for i, entry in enumerate(leaderboard):
            entry["rank"] = i + 1
        return leaderboard

    def _generate_team_summary_llm(
        self, team_id: str, total_emissions: float, avoided_kg: float,
        points: int, rank: int, total_teams: int,
    ) -> str:
        """LLM: generate a contextual, human-friendly team summary."""
        system_prompt = (
            "You are the Developer Copilot, a friendly AI that helps engineering teams "
            "understand their carbon footprint. Generate a brief, encouraging team summary. "
            "Be specific with numbers. If savings are small, be honest but positive. "
            "Include one actionable tip. Keep it under 5 sentences."
        )
        context = (
            f"team_id: {team_id}\n"
            f"total_emissions: {total_emissions:.1f} kgCO₂e\n"
            f"avoided_emissions: {avoided_kg * 1000:.0f} gCO₂e\n"
            f"reduction_pct: {(avoided_kg / total_emissions * 100) if total_emissions > 0 else 0:.1f}%\n"
            f"points: {points}\n"
            f"rank: #{rank} of {total_teams}\n"
        )
        return self.reason(system_prompt, context)


# ── Convenience functions for pipeline compatibility ──────────────────

def award_points_batch(verifications, rec_to_team):
    agent = CopilotAgent()
    # Simplified: just calculate points without full run
    entries = []
    for v in verifications:
        team_id = rec_to_team.get(v.recommendation_id, "unknown")
        entry = agent._calculate_points(v, team_id)
        if entry:
            entries.append(entry)
    return entries


def compute_leaderboard(points_entries):
    agent = CopilotAgent()
    return agent._compute_leaderboard(points_entries)


def generate_team_narrative(team_id, total_emissions_kg, avoided_kg, total_cost, cost_change, points, rank, total_teams):
    agent = CopilotAgent()
    return agent._generate_team_summary_llm(
        team_id=team_id, total_emissions=total_emissions_kg,
        avoided_kg=avoided_kg, points=points, rank=rank, total_teams=total_teams,
    )


def points_to_dataframe(entries):
    rows = []
    for e in entries:
        rows.append({
            "entry_id": e.entry_id, "team_id": e.team_id,
            "recommendation_id": e.recommendation_id, "verification_id": e.verification_id,
            "points": e.points, "kgco2e_saved": e.kgco2e_saved,
            "reason": e.reason, "awarded_at": e.awarded_at,
        })
    return pd.DataFrame(rows)
