"""
Tests for config.py

Covers that Config loads defaults correctly and respects env overrides.
"""

import os
import pytest


class TestConfigDefaults:
    def test_llm_provider_default(self):
        from config import Config
        # May be overridden by env; just check it's a string
        assert isinstance(Config.LLM_PROVIDER, str)

    def test_llm_model_default(self):
        from config import Config
        assert Config.LLM_MODEL == os.getenv("LLM_MODEL", "gpt-4o-mini")

    def test_llm_temperature_type(self):
        from config import Config
        assert isinstance(Config.LLM_TEMPERATURE, float)

    def test_llm_max_tokens_type(self):
        from config import Config
        assert isinstance(Config.LLM_MAX_TOKENS, int)

    def test_max_negotiation_rounds_default(self):
        from config import Config
        # Default is 4 unless env overrides
        expected = int(os.getenv("MAX_NEGOTIATION_ROUNDS", "4"))
        assert Config.MAX_NEGOTIATION_ROUNDS == expected

    def test_carbon_price_default(self):
        from config import Config
        expected = float(os.getenv("CARBON_PRICE_PER_TON", "75"))
        assert Config.CARBON_PRICE_PER_TON == expected

    def test_min_carbon_reduction_pct(self):
        from config import Config
        expected = float(os.getenv("MIN_CARBON_REDUCTION_PCT", "10.0"))
        assert Config.MIN_CARBON_REDUCTION_PCT == expected

    def test_max_cost_increase_pct(self):
        from config import Config
        expected = float(os.getenv("MAX_COST_INCREASE_PCT", "20.0"))
        assert Config.MAX_COST_INCREASE_PCT == expected

    def test_max_recommendations_per_batch(self):
        from config import Config
        expected = int(os.getenv("MAX_RECS_PER_BATCH", "6000"))
        assert Config.MAX_RECOMMENDATIONS_PER_BATCH == expected

    def test_max_batch_cost_increase(self):
        from config import Config
        expected = float(os.getenv("MAX_BATCH_COST_INCREASE", "500.0"))
        assert Config.MAX_BATCH_COST_INCREASE == expected

    def test_max_jobs_per_region(self):
        from config import Config
        expected = int(os.getenv("MAX_JOBS_PER_REGION", "15"))
        assert Config.MAX_JOBS_PER_REGION_PER_BATCH == expected

    def test_points_per_kg_co2e(self):
        from config import Config
        expected = int(os.getenv("POINTS_PER_KG_CO2E", "100"))
        assert Config.POINTS_PER_KG_CO2E == expected

    def test_sla_violation_penalty(self):
        from config import Config
        expected = int(os.getenv("SLA_PENALTY", "-50"))
        assert Config.SLA_VIOLATION_PENALTY == expected

    def test_default_sim_days(self):
        from config import Config
        expected = int(os.getenv("SIM_DAYS", "30"))
        assert Config.DEFAULT_SIM_DAYS == expected

    def test_default_seed(self):
        from config import Config
        expected = int(os.getenv("SEED", "42"))
        assert Config.DEFAULT_SEED == expected


class TestConfigEnvOverrides:
    def test_carbon_price_env_override(self, monkeypatch):
        monkeypatch.setenv("CARBON_PRICE_PER_TON", "150")
        # Must reload module to pick up env change
        import importlib
        import config
        importlib.reload(config)
        assert config.Config.CARBON_PRICE_PER_TON == 150.0
        # Restore
        monkeypatch.delenv("CARBON_PRICE_PER_TON", raising=False)
        importlib.reload(config)

    def test_max_negotiation_rounds_env_override(self, monkeypatch):
        monkeypatch.setenv("MAX_NEGOTIATION_ROUNDS", "8")
        import importlib
        import config
        importlib.reload(config)
        assert config.Config.MAX_NEGOTIATION_ROUNDS == 8
        monkeypatch.delenv("MAX_NEGOTIATION_ROUNDS", raising=False)
        importlib.reload(config)

    def test_sim_days_env_override(self, monkeypatch):
        monkeypatch.setenv("SIM_DAYS", "7")
        import importlib
        import config
        importlib.reload(config)
        assert config.Config.DEFAULT_SIM_DAYS == 7
        monkeypatch.delenv("SIM_DAYS", raising=False)
        importlib.reload(config)
