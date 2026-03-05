"""
Tests for LLMProvider in src/agents/base.py

Covers provider selection (auto, openai, groq, mock), the complete() method,
and Groq-specific configuration.
"""

import os
import pytest


class TestLLMProviderAutoDetection:
    """Test that auto-detection picks the right provider based on env vars."""

    def test_auto_defaults_to_mock_when_no_keys(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        from src.agents.base import LLMProvider
        llm = LLMProvider("auto")
        assert llm.provider == "mock"

    def test_auto_selects_groq_when_groq_key_set(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "gsk_test_fake_key")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        from src.agents.base import LLMProvider
        llm = LLMProvider("auto")
        assert llm.provider == "groq"

    def test_auto_selects_openai_when_openai_key_set(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake-key")
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        from src.agents.base import LLMProvider
        llm = LLMProvider("auto")
        assert llm.provider == "openai"

    def test_auto_prefers_groq_over_openai(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "gsk_test_fake_key")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake-key")
        from src.agents.base import LLMProvider
        llm = LLMProvider("auto")
        assert llm.provider == "groq"

    def test_explicit_mock_provider(self):
        from src.agents.base import LLMProvider
        llm = LLMProvider("mock")
        assert llm.provider == "mock"


class TestLLMProviderComplete:
    """Test the complete() convenience method."""

    def test_complete_returns_string(self):
        from src.agents.base import LLMProvider
        llm = LLMProvider("mock")
        result = llm.complete("Hello, world!")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_complete_delegates_to_chat(self):
        from src.agents.base import LLMProvider
        llm = LLMProvider("mock")
        result = llm.complete("Explain carbon optimization.")
        assert isinstance(result, str)


class TestLLMProviderGroqConfig:
    """Test Groq-specific configuration."""

    def test_groq_uses_default_model(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "gsk_test_fake_key")
        monkeypatch.delenv("GROQ_MODEL", raising=False)
        from src.agents.base import LLMProvider
        llm = LLMProvider("groq")
        assert llm._model == "llama-3.3-70b-versatile"

    def test_groq_respects_model_env_override(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "gsk_test_fake_key")
        monkeypatch.setenv("GROQ_MODEL", "mixtral-8x7b-32768")
        from src.agents.base import LLMProvider
        llm = LLMProvider("groq")
        assert llm._model == "mixtral-8x7b-32768"

    def test_groq_chat_uses_openai_path(self, monkeypatch):
        """Groq provider should use the _chat_openai method (OpenAI-compatible API)."""
        monkeypatch.setenv("GROQ_API_KEY", "gsk_test_fake_key")
        from src.agents.base import LLMProvider
        llm = LLMProvider("groq")
        # The client should be set (OpenAI client with groq base_url)
        assert llm._client is not None


class TestConfigGroqSettings:
    """Test that config.py includes Groq settings."""

    def test_groq_api_key_config_exists(self):
        from config import Config
        assert hasattr(Config, "GROQ_API_KEY")
        assert isinstance(Config.GROQ_API_KEY, str)

    def test_groq_model_config_exists(self):
        from config import Config
        assert hasattr(Config, "GROQ_MODEL")
        assert isinstance(Config.GROQ_MODEL, str)

    def test_groq_model_default(self):
        from config import Config
        expected = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        assert Config.GROQ_MODEL == expected
