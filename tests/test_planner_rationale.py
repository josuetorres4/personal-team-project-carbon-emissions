"""
Tests for Planner Agent LLM rationale enrichment.

Covers the batched rationale generation that limits individual LLM calls
to the top MAX_LLM_RATIONALES recommendations by carbon impact.
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from src.shared.models import Recommendation
from src.agents.planner import PlannerAgent, MAX_LLM_RATIONALES


def _make_rec(carbon_delta: float, job_id: str = "j1") -> Recommendation:
    """Helper to create a Recommendation with a given carbon delta."""
    return Recommendation(
        job_id=job_id,
        action_type="region_shift",
        current_region="us-east-1",
        proposed_region="eu-north-1",
        current_time=datetime(2025, 1, 1),
        proposed_time=datetime(2025, 1, 1),
        est_carbon_delta_kg=carbon_delta,
        est_cost_delta_usd=-0.01,
        confidence=0.85,
        rationale="",
        status="proposed",
        risk_level="low",
    )


class TestEnrichWithLLMRationales:
    """Test the _enrich_with_llm_rationales batching logic."""

    def test_empty_list_does_nothing(self):
        agent = PlannerAgent()
        agent.verbose = False
        agent._enrich_with_llm_rationales([])
        # No error, no LLM calls

    def test_small_batch_all_get_llm_rationales(self):
        """When recommendations < MAX_LLM_RATIONALES, all get LLM rationales."""
        agent = PlannerAgent()
        agent.verbose = False
        recs = [_make_rec(-0.01, f"j{i}") for i in range(5)]

        agent._enrich_with_llm_rationales(recs)

        for rec in recs:
            assert rec.rationale != ""
            # LLM mock produces "[Mock LLM]" or structured content
            # Template rationales start with "Shifting"
            assert not rec.rationale.startswith("Shifting"), (
                "Small batch should use LLM rationales, not templates"
            )

    def test_large_batch_caps_llm_calls(self):
        """When recommendations > MAX_LLM_RATIONALES, excess get template rationales."""
        n = MAX_LLM_RATIONALES + 20
        agent = PlannerAgent()
        agent.verbose = False

        # Create recs with varying carbon deltas so sorting is meaningful
        recs = [_make_rec(-0.001 * (i + 1), f"j{i}") for i in range(n)]

        agent._enrich_with_llm_rationales(recs)

        # All recs should have rationales
        for rec in recs:
            assert rec.rationale != ""

        # Count how many got template vs LLM rationales
        template_count = sum(1 for r in recs if r.rationale.startswith("Shifting"))
        llm_count = n - template_count

        assert llm_count == MAX_LLM_RATIONALES
        assert template_count == 20

    def test_top_impact_recs_get_llm_rationales(self):
        """The most impactful recommendations (most negative carbon delta) get LLM rationales."""
        agent = PlannerAgent()
        agent.verbose = False

        # 3 high-impact + many low-impact, with MAX_LLM_RATIONALES = 50
        recs = []
        recs.append(_make_rec(-10.0, "high_impact_1"))
        recs.append(_make_rec(-5.0, "high_impact_2"))
        recs.append(_make_rec(-1.0, "high_impact_3"))
        # Add more than MAX_LLM_RATIONALES low-impact recs
        for i in range(MAX_LLM_RATIONALES):
            recs.append(_make_rec(-0.0001, f"low_{i}"))

        agent._enrich_with_llm_rationales(recs)

        # High-impact recs should get LLM rationales (not templates)
        high_impact_recs = [r for r in recs if r.job_id.startswith("high_impact")]
        for rec in high_impact_recs:
            assert not rec.rationale.startswith("Shifting"), (
                f"High-impact rec {rec.job_id} should get LLM rationale"
            )

    def test_template_rationale_contains_useful_info(self):
        """Template rationales should include action type, regions, and savings."""
        agent = PlannerAgent()
        agent.verbose = False

        n = MAX_LLM_RATIONALES + 5
        recs = [_make_rec(-0.001, f"j{i}") for i in range(n)]

        agent._enrich_with_llm_rationales(recs)

        template_recs = [r for r in recs if r.rationale.startswith("Shifting")]
        assert len(template_recs) == 5

        for rec in template_recs:
            assert "us-east-1" in rec.rationale or "eu-north-1" in rec.rationale
            assert "gCO" in rec.rationale  # Contains carbon info
            assert "cost delta" in rec.rationale

    def test_verbose_progress_output(self, capsys):
        """When verbose=True, progress messages are printed."""
        agent = PlannerAgent()
        agent.verbose = True

        n = MAX_LLM_RATIONALES + 10
        recs = [_make_rec(-0.001 * (i + 1), f"j{i}") for i in range(n)]

        agent._enrich_with_llm_rationales(recs)

        captured = capsys.readouterr()
        assert "Generating LLM rationales" in captured.out
        assert "deterministic rationale" in captured.out
        assert "Rationale enrichment complete" in captured.out


class TestMaxLLMRationalesConfig:
    """Test the MAX_LLM_RATIONALES configuration."""

    def test_default_value(self):
        assert MAX_LLM_RATIONALES == 50

    def test_config_exists(self):
        from config import Config
        assert hasattr(Config, "MAX_LLM_RATIONALES")
        assert Config.MAX_LLM_RATIONALES == 50
