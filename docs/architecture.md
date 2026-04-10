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
- `src/data/azure_traces.py` — Azure VM traces loader
- `dashboard.py` — Streamlit dashboard (12 interactive pages)
