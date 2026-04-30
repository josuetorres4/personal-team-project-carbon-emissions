# Architecture

## Pipeline: Sense -> Model -> Decide -> Act -> Verify -> Learn

```
┌─────────────────────────────────────────────────────────────────────┐
│                        GOVERNANCE AGENT                             │
│              (approval gates, policy enforcement)                    │
│─────────────────────────────────────────────────────────────────────│
│                                                                     │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐        │
│  │ INGESTOR │──>│ CARBON   │──>│ PLANNER  │──>│ EXECUTOR │        │
│  │          │   │ ACCNTANT │   │ AGENT    │   │ AGENT    │        │
│  └──────────┘   └──────────┘   └──────────┘   └──────────┘        │
│       │              │              │              │                 │
│       │              v              │              v                 │
│       │     ┌──────────────┐       │     ┌──────────────┐          │
│       │     │  EMISSIONS   │       │     │  VERIFIER    │          │
│       │     │  FACTOR DB   │       │     │  AGENT       │<──┐     │
│       │     └──────────────┘       │     └──────────────┘   │     │
│       │                            │              │          │     │
│       v                            v              v          │     │
│  ┌─────────────────────────────────────────────────────┐    │     │
│  │            SHARED MEMORY (World Model)              │────┘     │
│  │  Activity Ledger | Decision Log | Outcome Log       │          │
│  └─────────────────────────────────────────────────────┘          │
│                            │                                       │
│                            v                                       │
│                    ┌──────────────┐                                │
│                    │  DEV COPILOT │                                │
│                    │  (summaries) │                                │
│                    └──────────────┘                                │
└─────────────────────────────────────────────────────────────────────┘
```

## Agent Roster

| Agent | Type | LLM? | Purpose |
|---|---|---|---|
| **Ingestor** | Data connector | No | Loads workload data (synthetic or Azure VM traces) and carbon intensity (EIA/ENTSO-E/Ember or synthetic) |
| **Carbon Accountant** | Deterministic | No | Calculates kgCO2e per job: `vcpus * duration * 0.005 kW/vCPU * 1.1 PUE * grid_intensity` |
| **Planner Agent** | LLM + solver | Yes | Scores jobs, generates region/time-shift recommendations, explains rationale |
| **Governance Agent** | LLM + rules | Yes | Multi-round negotiation, risk assessment, approve/reject decisions |
| **Executor Agent** | LLM + config | Yes | Applies changes, generates Jira tickets and GitHub PR descriptions |
| **Verifier** | Deterministic | No | Counterfactual MRV: compares actual vs "what would have happened" |
| **Developer Copilot** | LLM + gamification | Yes | Team summaries, points, leaderboard, actionable nudges |

## LLM vs Deterministic Boundary

**LLM handles**: interpretation, explanation, summarization, negotiation, policy parsing, ticket generation

**Deterministic handles**: emissions math, optimization scoring, cost calculations, counterfactual verification, points computation, SLA compliance

This separation ensures every number is auditable and reproducible. An auditor never encounters "the LLM said 42.7 kgCO2e."

## Data Sources

| Data | Synthetic (default) | Real |
|---|---|---|
| **Workloads** | Simulated ~100-dev org (~30K jobs/month) | Azure VM Traces 2019 (2.6M VMs) |
| **Carbon intensity (US)** | Sinusoidal + noise from EPA eGRID baselines | EIA API hourly fuel mix -> gCO2/kWh |
| **Carbon intensity (EU)** | Sinusoidal + noise from grid averages | ENTSO-E Transparency hourly generation |
| **Carbon intensity (India)** | Sinusoidal from ~700 gCO2/kWh baseline | Ember Climate annual average + variation |

## Key Files

- `src/orchestrator.py` — Pipeline orchestrator, agent lifecycle management
- `src/agents/base.py` — LLMProvider, BaseAgent class, mock LLM
- `src/agents/planner.py` — Optimization recommendations
- `src/agents/governance.py` — Policy enforcement, negotiation
- `src/agents/executor.py` — Change execution, ticket generation
- `src/agents/verifier.py` — Counterfactual verification
- `src/agents/copilot.py` — Team gamification
- `src/data/carbon_intensity_real.py` — EIA + ENTSO-E + Ember data connector
- `src/data/electricity_maps.py` — Electricity Maps connector (primary, all 5 regions)
- `src/data/azure_traces.py` — Azure VM traces loader
- `src/data/aws_pricing.py` — Stub for live AWS Pricing API (not yet wired up)
- `dashboard.py` — Streamlit dashboard (interactive pages)

## Real-Data-Only Mode

When `REAL_DATA_ONLY=true` (default), the orchestrator's `preflight_real_data_check()`
runs before any agent and aborts with a clear message if any of the following
are missing:

- `USE_REAL_CARBON_DATA=true`
- `ELECTRICITYMAPS_API_TOKEN` (preferred), OR both `EIA_API_KEY` + `ENTSOE_API_TOKEN`
- `USE_REAL_WORKLOAD_DATA=true` and `data/azure_traces/vmtable.csv` present

Setting `REAL_DATA_ONLY=false` restores legacy fallback-to-synthetic behavior
(useful for offline development; not recommended for any reported numbers).

## Cost Model Scaling Path

Today `src/simulator/cost_model.py` uses a cited static snapshot of AWS
On-Demand pricing (m5.large / g4dn.xlarge, 2025-01-15). To go live:

1. Implement `fetch_vcpu_price()` / `fetch_gpu_price()` / `fetch_egress_price()`
   in `src/data/aws_pricing.py` against the AWS Pricing List API
   (`https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonEC2/...`).
2. Replace the static lookups in `cost_model.py` with calls to those functions,
   cached per `(region, instance_family)` for the lifetime of one pipeline run.
3. Update `PRICING_SOURCE` to reflect the live source — the `pricing_source`
   column on `recommendations.csv` and `executions.csv` is forward-compatible,
   so no schema changes are needed.
