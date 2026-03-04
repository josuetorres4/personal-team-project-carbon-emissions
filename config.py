"""
Configuration Management
========================
Centralizes all magic numbers from across the codebase into a single Config
class with environment variable overrides.

Usage:
    from config import Config
    print(Config.CARBON_PRICE_PER_TON)

All values can be overridden via environment variables (see .env.example).
"""

import os

# Load .env file if present (requires python-dotenv)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class Config:
    # LLM settings
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "auto")
    LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
    LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.3"))
    LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "1024"))

    # Multi-agent negotiation
    MAX_NEGOTIATION_ROUNDS = int(os.getenv("MAX_NEGOTIATION_ROUNDS", "4"))

    # Carbon pricing (USD per ton CO₂e)
    CARBON_PRICE_PER_TON = float(os.getenv("CARBON_PRICE_PER_TON", "75"))

    # Planner constraints
    MIN_CARBON_REDUCTION_PCT = float(os.getenv("MIN_CARBON_REDUCTION_PCT", "10.0"))
    MAX_COST_INCREASE_PCT = float(os.getenv("MAX_COST_INCREASE_PCT", "20.0"))

    # Governance circuit breakers
    MAX_RECOMMENDATIONS_PER_BATCH = int(os.getenv("MAX_RECS_PER_BATCH", "6000"))
    MAX_BATCH_COST_INCREASE = float(os.getenv("MAX_BATCH_COST_INCREASE", "500.0"))
    MAX_JOBS_PER_REGION_PER_BATCH = int(os.getenv("MAX_JOBS_PER_REGION", "15"))

    # Gamification
    POINTS_PER_KG_CO2E = int(os.getenv("POINTS_PER_KG_CO2E", "100"))
    SLA_VIOLATION_PENALTY = int(os.getenv("SLA_PENALTY", "-50"))

    # Simulation defaults
    DEFAULT_SIM_DAYS = int(os.getenv("SIM_DAYS", "30"))
    DEFAULT_SEED = int(os.getenv("SEED", "42"))
