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
    LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "512"))
    MAX_TOTAL_LLM_TOKENS = int(os.getenv("MAX_TOTAL_LLM_TOKENS", "100000"))
    RATE_LIMIT_WAIT_SECONDS = int(os.getenv("RATE_LIMIT_WAIT_SECONDS", "300"))
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    # Multi-agent negotiation
    MAX_NEGOTIATION_ROUNDS = int(os.getenv("MAX_NEGOTIATION_ROUNDS", "2"))

    # Carbon pricing (USD per ton CO₂e)
    CARBON_PRICE_PER_TON = float(os.getenv("CARBON_PRICE_PER_TON", "75"))

    # Planner constraints
    MIN_CARBON_REDUCTION_PCT = float(os.getenv("MIN_CARBON_REDUCTION_PCT", "10.0"))
    MAX_COST_INCREASE_PCT = float(os.getenv("MAX_COST_INCREASE_PCT", "20.0"))
    MAX_LLM_RATIONALES = int(os.getenv("MAX_LLM_RATIONALES", "10"))
    MAX_LLM_TICKETS = int(os.getenv("MAX_LLM_TICKETS", "10"))
    MAX_LLM_RISK_ASSESSMENTS = int(os.getenv("MAX_LLM_RISK_ASSESSMENTS", "10"))

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

    # Carbon Market
    WEEKLY_CARBON_BUDGET_KG = float(os.getenv("WEEKLY_CARBON_BUDGET_KG", "500"))
    INTERNAL_CARBON_PRICE_USD_PER_TON = float(os.getenv("CARBON_PRICE_PER_TON", "75"))
    MAX_REPLAN_CYCLES = int(os.getenv("MAX_REPLAN_CYCLES", "2"))
    MIN_CARBON_SAVING_PCT = float(os.getenv("MIN_CARBON_SAVING_PCT", "5"))

    # Real data
    USE_REAL_CARBON_DATA = os.getenv("USE_REAL_CARBON_DATA", "true").lower() == "true"
    CARBON_DATA_CACHE_HOURS = int(os.getenv("CARBON_DATA_CACHE_HOURS", "6"))
    ELECTRICITY_MAPS_API_TOKEN = os.getenv("ELECTRICITY_MAPS_API_TOKEN", "")
