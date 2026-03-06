"""
Tests for LLM rate limit handling: retry with backoff, and LLM call caps
in Executor and Governance agents.
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from src.agents.base import LLMProvider
from src.agents.executor import ExecutorAgent, MAX_LLM_TICKETS
from src.agents.governance import GovernanceAgent, MAX_LLM_RISK_ASSESSMENTS
from src.shared.models import Recommendation, Job, WorkloadCategory


def _make_rec(job_id: str = "j1", risk_level: str = "low",
              cost_delta: float = 0.0, confidence: float = 0.85) -> Recommendation:
    """Helper to create a Recommendation."""
    return Recommendation(
        job_id=job_id,
        action_type="region_shift",
        current_region="us-east-1",
        proposed_region="eu-north-1",
        current_time=datetime(2025, 1, 1),
        proposed_time=datetime(2025, 1, 1),
        est_carbon_delta_kg=-0.01,
        est_cost_delta_usd=cost_delta,
        confidence=confidence,
        rationale="test",
        status="approved",
        risk_level=risk_level,
    )


def _make_job(job_id: str = "j1") -> Job:
    """Helper to create a Job."""
    return Job(
        job_id=job_id,
        name="test-job",
        team_id="team-a",
        region="us-east-1",
        vcpus=4,
        gpu_count=0,
        duration_hours=1.0,
        category=WorkloadCategory.BALANCED,
        started_at=datetime(2025, 1, 1),
        ended_at=datetime(2025, 1, 1, 1, 0),
    )


class TestLLMRetryLogic:
    """Test the retry with backoff in LLMProvider._chat_openai."""

    def test_retry_on_rate_limit_error(self):
        """_chat_openai retries on rate limit errors."""
        provider = LLMProvider("mock")
        provider.provider = "openai"  # Force openai path

        mock_client = MagicMock()
        # First call raises rate limit, second succeeds
        rate_limit_error = Exception("Error code: 429 - rate_limit_exceeded")
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="success"))]
        mock_client.chat.completions.create.side_effect = [
            rate_limit_error,
            mock_response,
        ]
        provider._client = mock_client

        with patch("src.agents.base.time.sleep"):  # Don't actually sleep
            result = provider._chat_openai("system", "user", 0.3)

        assert result == "success"
        assert mock_client.chat.completions.create.call_count == 2

    def test_retry_exhausted_returns_fallback(self):
        """After max retries, a fallback response is returned instead of raising."""
        provider = LLMProvider("mock")
        provider.provider = "openai"

        mock_client = MagicMock()
        rate_limit_error = Exception("429 Too Many Requests")
        mock_client.chat.completions.create.side_effect = rate_limit_error
        provider._client = mock_client

        with patch("src.agents.base.time.sleep"):
            result = provider._chat_openai("system", "user", 0.3)

        assert result == LLMProvider.RATE_LIMIT_RESPONSE
        assert mock_client.chat.completions.create.call_count == 5  # max_retries

    def test_non_rate_limit_error_not_retried(self):
        """Non-rate-limit errors are raised immediately."""
        provider = LLMProvider("mock")
        provider.provider = "openai"

        mock_client = MagicMock()
        auth_error = Exception("Invalid API key")
        mock_client.chat.completions.create.side_effect = auth_error
        provider._client = mock_client

        with pytest.raises(Exception, match="Invalid API key"):
            provider._chat_openai("system", "user", 0.3)

        assert mock_client.chat.completions.create.call_count == 1


class TestExecutorLLMCap:
    """Test that the Executor caps LLM ticket generation calls."""

    def test_default_cap_value(self):
        assert MAX_LLM_TICKETS == 10

    def test_config_exists(self):
        from config import Config
        assert hasattr(Config, "MAX_LLM_TICKETS")
        assert Config.MAX_LLM_TICKETS == 10

    def test_small_batch_all_get_llm_tickets(self):
        """When approved recs < MAX_LLM_TICKETS, all get LLM tickets."""
        agent = ExecutorAgent()
        recs = [_make_rec(f"j{i}") for i in range(3)]
        jobs = [_make_job(f"j{i}") for i in range(3)]

        result = agent.run({"approved_recs": recs, "jobs": jobs})

        for record in result["execution_records"]:
            assert record.ticket_body != ""
            # LLM-generated tickets should NOT contain template markers
            assert "**Carbon delta**" not in record.ticket_body

    def test_large_batch_caps_llm_tickets(self):
        """When approved recs > MAX_LLM_TICKETS, excess get template tickets."""
        n = MAX_LLM_TICKETS + 10
        agent = ExecutorAgent()
        recs = [_make_rec(f"j{i}") for i in range(n)]
        jobs = [_make_job(f"j{i}") for i in range(n)]

        result = agent.run({"approved_recs": recs, "jobs": jobs})

        all_records = result["execution_records"]
        assert len(all_records) == n

        # All should have ticket bodies
        for record in all_records:
            assert record.ticket_body != ""

        # Template tickets contain "Carbon delta" (from _generate_template_ticket)
        template_count = sum(1 for r in all_records if "**Carbon delta**" in r.ticket_body)
        assert template_count == 10

    def test_template_ticket_contains_useful_info(self):
        """Template tickets should include action, regions, and carbon info."""
        agent = ExecutorAgent()
        n = MAX_LLM_TICKETS + 1
        recs = [_make_rec(f"j{i}") for i in range(n)]
        jobs = [_make_job(f"j{i}") for i in range(n)]

        result = agent.run({"approved_recs": recs, "jobs": jobs})

        # The last record should have a template ticket
        template_records = [r for r in result["execution_records"]
                           if "**Carbon delta**" in r.ticket_body]
        assert len(template_records) == 1
        ticket = template_records[0].ticket_body
        assert "Sustainability Optimization" in ticket
        assert "Rollback" in ticket


class TestGovernanceLLMCap:
    """Test that the Governance agent caps LLM risk assessment calls."""

    def test_default_cap_value(self):
        assert MAX_LLM_RISK_ASSESSMENTS == 10

    def test_config_exists(self):
        from config import Config
        assert hasattr(Config, "MAX_LLM_RISK_ASSESSMENTS")
        assert Config.MAX_LLM_RISK_ASSESSMENTS == 10

    def test_low_risk_no_llm_calls(self):
        """Low-risk recommendations don't use LLM risk assessment."""
        agent = GovernanceAgent()
        recs = [_make_rec(f"j{i}", risk_level="low") for i in range(5)]

        result = agent.run({"recommendations": recs, "seed": 42})

        for decision in result["decisions"]:
            assert decision.llm_reasoning == ""

    def test_medium_risk_get_llm_up_to_cap(self):
        """Medium-risk recommendations get LLM assessment up to the cap."""
        agent = GovernanceAgent()
        # Create recommendations that will be assessed as medium risk
        # (cost_delta > 1.0 makes them medium)
        n = MAX_LLM_RISK_ASSESSMENTS + 10
        recs = [_make_rec(f"j{i}", risk_level="low", cost_delta=2.0) for i in range(n)]

        result = agent.run({"recommendations": recs, "seed": 42})

        llm_count = sum(1 for d in result["decisions"] if d.llm_reasoning != "")
        assert llm_count == MAX_LLM_RISK_ASSESSMENTS
