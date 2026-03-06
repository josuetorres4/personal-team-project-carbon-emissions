"""
Tests for LLM token budget enforcement.

Verifies that LLMProvider tracks token usage and falls back to a
deterministic response when the configurable budget (MAX_TOTAL_LLM_TOKENS,
default 100 000) would be exceeded — preventing Groq / OpenAI TPD errors.
"""

import pytest
from unittest.mock import MagicMock, patch

from src.agents.base import LLMProvider


# ── Token estimation ────────────────────────────────────────────────────

class TestEstimateTokens:
    def test_empty_string(self):
        assert LLMProvider.estimate_tokens("") == 1  # minimum 1

    def test_short_text(self):
        assert LLMProvider.estimate_tokens("hi") == 1  # 2 chars / 4 = 0 → clamped to 1

    def test_known_length(self):
        # 400 chars → ~100 tokens
        text = "a" * 400
        assert LLMProvider.estimate_tokens(text) == 100

    def test_realistic_prompt(self):
        prompt = "Explain the carbon savings of shifting job j-42 from us-east-1 to eu-north-1."
        tokens = LLMProvider.estimate_tokens(prompt)
        assert 10 < tokens < 50  # sanity check


# ── Budget properties ───────────────────────────────────────────────────

class TestTokenBudgetProperties:
    def test_default_budget_from_config(self):
        llm = LLMProvider("mock")
        assert llm.max_total_tokens == 100_000

    def test_custom_budget_override(self):
        llm = LLMProvider("mock", max_total_tokens=5000)
        assert llm.max_total_tokens == 5000

    def test_initial_tokens_used_is_zero(self):
        llm = LLMProvider("mock")
        assert llm.total_tokens_used == 0

    def test_budget_remaining(self):
        llm = LLMProvider("mock", max_total_tokens=1000)
        llm.total_tokens_used = 300
        assert llm.token_budget_remaining == 700

    def test_budget_exceeded_false(self):
        llm = LLMProvider("mock", max_total_tokens=1000)
        llm.total_tokens_used = 999
        assert not llm.token_budget_exceeded

    def test_budget_exceeded_true(self):
        llm = LLMProvider("mock", max_total_tokens=1000)
        llm.total_tokens_used = 1000
        assert llm.token_budget_exceeded

    def test_budget_remaining_never_negative(self):
        llm = LLMProvider("mock", max_total_tokens=100)
        llm.total_tokens_used = 200
        assert llm.token_budget_remaining == 0


# ── Budget enforcement in chat() ────────────────────────────────────────

class TestTokenBudgetEnforcement:
    def test_mock_call_tracks_tokens(self):
        """A successful mock call should increase total_tokens_used."""
        llm = LLMProvider("mock", max_total_tokens=100_000)
        llm.chat("Explain rationale", "Some context about a job shift")
        assert llm.total_tokens_used > 0

    def test_multiple_calls_accumulate(self):
        """Token counts accumulate across calls."""
        llm = LLMProvider("mock", max_total_tokens=100_000)
        llm.chat("Explain rationale", "context 1")
        first = llm.total_tokens_used
        llm.chat("Explain rationale", "context 2")
        assert llm.total_tokens_used > first

    def test_budget_exceeded_returns_fallback(self):
        """When budget is nearly exhausted, chat() returns the fallback."""
        llm = LLMProvider("mock", max_total_tokens=100)
        # Simulate having used most of the budget already
        llm.total_tokens_used = 99
        result = llm.chat("system prompt", "user message")
        assert result == LLMProvider.BUDGET_EXCEEDED_RESPONSE

    def test_budget_exceeded_does_not_increase_tokens(self):
        """Fallback response should not add to the token counter."""
        llm = LLMProvider("mock", max_total_tokens=100)
        llm.total_tokens_used = 99
        before = llm.total_tokens_used
        llm.chat("system", "user")
        assert llm.total_tokens_used == before

    def test_complete_also_respects_budget(self):
        """complete() delegates to chat(), so budget applies there too."""
        llm = LLMProvider("mock", max_total_tokens=100)
        llm.total_tokens_used = 99
        result = llm.complete("some prompt")
        assert result == LLMProvider.BUDGET_EXCEEDED_RESPONSE

    def test_calls_succeed_under_budget(self):
        """Normal calls go through when budget has room."""
        llm = LLMProvider("mock", max_total_tokens=100_000)
        result = llm.chat("Explain rationale", "shift job from us-east-1 to eu-north-1")
        assert result != LLMProvider.BUDGET_EXCEEDED_RESPONSE
        assert len(result) > 0


# ── Budget enforcement with OpenAI path ─────────────────────────────────

class TestTokenBudgetOpenAI:
    def test_budget_blocks_openai_call(self):
        """When budget is exhausted, _chat_openai is never called."""
        llm = LLMProvider("mock")
        llm.provider = "openai"  # Force openai path
        llm.max_total_tokens = 50
        llm.total_tokens_used = 50

        mock_client = MagicMock()
        llm._client = mock_client

        result = llm.chat("system", "user")
        assert result == LLMProvider.BUDGET_EXCEEDED_RESPONSE
        mock_client.chat.completions.create.assert_not_called()

    def test_openai_tracks_usage_from_response(self):
        """After a successful OpenAI call, tokens are tracked from response.usage."""
        llm = LLMProvider("mock")
        llm.provider = "openai"
        llm.max_total_tokens = 100_000

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="response text"))]
        mock_response.usage = MagicMock(total_tokens=150)

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        llm._client = mock_client

        llm._chat_openai("system", "user", 0.3)
        assert llm.total_tokens_used == 150

    def test_openai_estimates_when_usage_is_none(self):
        """Falls back to estimation when response.usage is None."""
        llm = LLMProvider("mock")
        llm.provider = "openai"
        llm.max_total_tokens = 100_000

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="a" * 100))]
        mock_response.usage = None

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        llm._client = mock_client

        llm._chat_openai("sys", "usr", 0.3)
        assert llm.total_tokens_used > 0


# ── Config integration ──────────────────────────────────────────────────

class TestTokenBudgetConfig:
    def test_config_has_max_total_llm_tokens(self):
        from config import Config
        assert hasattr(Config, "MAX_TOTAL_LLM_TOKENS")
        assert Config.MAX_TOTAL_LLM_TOKENS == 100_000

    def test_config_env_override(self, monkeypatch):
        monkeypatch.setenv("MAX_TOTAL_LLM_TOKENS", "50000")
        import importlib
        import config
        importlib.reload(config)
        assert config.Config.MAX_TOTAL_LLM_TOKENS == 50_000
        monkeypatch.delenv("MAX_TOTAL_LLM_TOKENS", raising=False)
        importlib.reload(config)

    def test_provider_picks_up_config_default(self):
        """LLMProvider should use Config.MAX_TOTAL_LLM_TOKENS when no override."""
        from config import Config
        llm = LLMProvider("mock")
        assert llm.max_total_tokens == Config.MAX_TOTAL_LLM_TOKENS


# ── Integration: shared provider across agents ──────────────────────────

class TestSharedProviderBudget:
    def test_shared_llm_accumulates_across_agents(self):
        """When agents share one LLMProvider, tokens accumulate correctly."""
        from src.agents.executor import ExecutorAgent
        from src.agents.governance import GovernanceAgent

        llm = LLMProvider("mock", max_total_tokens=100_000)
        executor = ExecutorAgent(llm=llm)
        governance = GovernanceAgent(llm=llm)

        # Both agents point to the same provider
        assert executor.llm is governance.llm
        assert executor.llm.total_tokens_used == 0

        # Make a call through one agent's LLM
        llm.chat("Explain rationale", "some context")
        tokens_after_first = llm.total_tokens_used
        assert tokens_after_first > 0

        # The other agent sees the same counter
        assert governance.llm.total_tokens_used == tokens_after_first
