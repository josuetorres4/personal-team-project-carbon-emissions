# sust-AI-naible 🌍

> **Multi-agent cloud carbon optimization** — a system that watches cloud workloads, calculates their carbon footprint, recommends cheaper+greener scheduling, executes those changes, and *proves* the savings were real using counterfactual analysis.

---

## Why This Project?

### The problem is real and growing

Data centers now consume roughly **1% of global electricity** (~205 TWh/year) and that share is accelerating with AI workloads ([Masanet et al., *Science* 2020](https://www.science.org/doi/10.1126/science.aba3758)). Under the EU's Corporate Sustainability Reporting Directive (CSRD), ~50,000 companies are now **legally required** to disclose Scope 1/2/3 emissions — including cloud use. Carbon reporting has shifted from "nice to have" to "legally required."

### The gap in existing tools

Every major cloud provider ships a carbon dashboard. None of them close the loop:

| Tool | Measures | Recommends | **Executes** | **Verifies savings** |
|------|----------|-----------|-------------|---------------------|
| AWS Carbon Footprint Tool | ✅ | ❌ | ❌ | ❌ |
| Google Cloud Carbon Footprint | ✅ | ✅ | ❌ | ❌ |
| Cloud Carbon Footprint (Thoughtworks) | ✅ | ✅ | ❌ | ❌ |
| **sust-AI-naible** | ✅ | ✅ | ✅ | ✅ |

Existing tools tell you what happened last month. This system closes the loop: it *acts*, then *proves the action worked* using counterfactual reasoning (what would emissions have been if we hadn't intervened?).

### The results are meaningful

Google's own research ([Radovanović et al., *IEEE Trans. Power Systems* 2022](https://arxiv.org/abs/2106.11750)) showed **10–40% carbon reduction** by shifting flexible workloads temporally and spatially. CarbonScaler ([Hanafy et al., SIGMETRICS 2023](https://arxiv.org/abs/2302.08681)) demonstrated **51% carbon savings** over carbon-agnostic execution. This project implements those same strategies and shows you the numbers on your own simulated workload.

### What makes this technically interesting

1. **Closed-loop control** — Sense → Model → Decide → Act → Verify → Learn, not a one-shot script
2. **Multi-agent architecture** — Specialized agents with role separation and checks: a Governance agent must approve every batch the Planner proposes before the Executor runs it
3. **Multi-objective optimization** — Balances carbon, cost, and latency together (carbon-only optimization can cause 2–3× cost spikes, per CarbonScaler)
4. **Verifiable claims** — Every "we saved X kg" statement has a traceable evidence chain with confidence intervals; this is Measurement, Reporting, and Verification (MRV), the same framework carbon markets use
5. **AI + determinism boundary** — LLM agents handle reasoning, rationale, and communication; all numbers are computed deterministically; the two never mix

### What you learn building and using it

- How to structure a multi-agent system with clear role boundaries and a message-passing protocol
- How carbon accounting actually works (GHG Protocol, Scope 2, location-based vs market-based methods)
- How to use counterfactual reasoning to verify that an intervention worked
- How to balance competing objectives (cost vs carbon vs latency) rather than optimizing a single metric
- How to integrate an LLM into a pipeline where correctness matters — as a communicator, not a calculator

---

## Quick Start (no API key required)

```bash
# 1. Clone and install
git clone <repo-url>
cd team-project-carbon-emissions
pip install -r requirements.txt

# 2. Run the pipeline (mock LLM — works without an OpenAI key)
python run_pipeline.py

# 3. Open the dashboard
streamlit run dashboard.py
```

That's it. The pipeline generates synthetic data, runs all agents, and saves results to `data/`. The dashboard reads those files and visualises everything.

---

## Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.11+ | Required for `list[str]` type hints |
| pip | any recent | Comes with Python |
| OpenAI API key | optional | Without it the system uses a built-in mock LLM |

---

## Installation

```bash
pip install -r requirements.txt
```

Dependencies installed:

| Package | Purpose |
|---------|---------|
| `numpy`, `pandas` | Data processing |
| `openai` | LLM calls (optional — falls back to mock) |
| `streamlit` | Interactive dashboard |
| `plotly` | Charts in the dashboard |
| `pytest` | Running tests |
| `python-dotenv` | Loading `.env` files |

---

## Configuration (optional)

Copy `.env.example` to `.env` and edit as needed:

```bash
cp .env.example .env
```

```
# .env.example
OPENAI_API_KEY=your-key-here   # Remove this line to use mock LLM
LLM_PROVIDER=auto              # "auto" | "openai" | "mock"
LLM_MODEL=gpt-4o-mini

SIM_DAYS=30                    # Days of synthetic workloads to simulate
SEED=42                        # Random seed for reproducibility
CARBON_PRICE_PER_TON=75        # USD/ton CO₂e used in scoring
MAX_NEGOTIATION_ROUNDS=4       # Agent dialogue rounds
```

All values have sensible defaults — the `.env` file is entirely optional.

---

## How to Run

### Option 1 — Hello world (no agents, fastest)

Generates workloads, computes emissions, prints a summary table. Good for verifying the install.

```bash
python run_baseline.py
```

Expected output (abridged):

```
======================================================================
  sust-AI-naible — Baseline Analysis
======================================================================

[1/4] Generating 30 days of synthetic workloads...
  Generated 24,274 jobs
...
  Total cloud spend:    $8,591.19
  Total emissions:      373.80 kgCO₂e
  Carbon cost (@$75/t): $28.03
======================================================================
  NEXT STEP: Build the Planner agent to optimize flexible workloads
======================================================================
```

Saves `data/baseline_results.csv` and `data/carbon_intensity.csv`.

---

### Option 2 — Full multi-agent pipeline

Runs all 6 agents end-to-end and produces every output file the dashboard needs.

```bash
# Without an OpenAI key — uses built-in mock LLM
python run_pipeline.py

# With an OpenAI key — uses real GPT-4o-mini
OPENAI_API_KEY=sk-... python run_pipeline.py
```

The pipeline runs these stages in order:

```
SENSE   → Ingestor        (generates 30 days of synthetic cloud workloads)
MODEL   → Carbon Accountant (calculates kgCO₂e per job)
DECIDE  → Planner Agent   (generates region/time-shift recommendations)
          ↕ negotiation ↕  (Planner ↔ Governance multi-round dialogue)
        → Governance Agent (approves / rejects / challenges recommendations)
ACT     → Executor Agent  (applies changes, generates tickets)
VERIFY  → Verifier        (counterfactual MRV: did we actually save carbon?)
LEARN   → Developer Copilot (team summaries, points, leaderboard)
```

Expected output (abridged):

```
======================================================================
  Step 3: DECIDE — Planner Agent
======================================================================
  Planning complete: 12,895 considered, 11,379 skipped, 5,478 recommendations
  Starting negotiation: up to 4 rounds
  Round 0: Planner proposed batch (5478 recs)
  Round 1: Governance → approval
  Negotiation complete: 2 rounds, outcome: consensus

...
  Emissions: 373.8 → 311.8 kgCO₂e (-62.0, 16.6%)
  Dashboard: streamlit run dashboard.py
```

**Output files** written to `data/`:

| File | Contents |
|------|----------|
| `jobs_baseline.csv` | All simulated jobs before optimization |
| `jobs_optimized.csv` | Jobs after recommended changes applied |
| `recommendations.csv` | Every Planner recommendation with rationale |
| `governance_decisions.csv` | Approval/rejection decision per recommendation |
| `executions.csv` | Executor change records and ticket IDs |
| `verifications.csv` | MRV results with confidence intervals |
| `points.csv` | Gamification points per team |
| `leaderboard.csv` | Team sustainability leaderboard |
| `pipeline_summary.json` | Aggregated metrics + environmental impact |
| `agent_dialogues.json` | Full Planner↔Governance negotiation transcript |
| `agent_traces.json` | LLM reasoning trace for every agent |
| `evidence_chains.json` | Counterfactual evidence for every verification |

---

### Option 3 — Dashboard

Requires the pipeline to have been run at least once (so `data/` files exist).

```bash
streamlit run dashboard.py
```

Then open **http://localhost:8501** in your browser.

Dashboard pages:

| Page | What it shows |
|------|---------------|
| Overview | Pipeline summary, key metrics |
| Carbon Analysis | Emissions by region/team/hour |
| Optimization Results | Recommendations, risk breakdown, cost vs carbon trade-off |
| Verification (MRV) | Counterfactual savings with confidence intervals |
| Team Leaderboard | Gamification points by team |
| Evidence Explorer | Click any verification to see its full evidence chain |
| Trade-off Analysis | Cost vs carbon Pareto frontier |
| Agent Reasoning | LLM reasoning traces from every agent |
| 🤖 The Debate | Chat-style view of the Planner↔Governance negotiation |
| 🌍 The Impact | Carbon savings as real-world equivalencies + business value |
| 💬 Ask the Agent | **Interactive chat** — ask questions and get answers about your pipeline results |

---

## Running Tests

```bash
pytest tests/ -v
```

All 50 tests should pass without any API key or network access.

---

## Project Structure

```
.
├── run_pipeline.py          # Entry point: full multi-agent pipeline
├── run_baseline.py          # Entry point: baseline analysis only
├── dashboard.py             # Streamlit dashboard
├── config.py                # Centralized configuration (env var overrides)
├── requirements.txt
├── .env.example             # Environment variable template
│
├── src/
│   ├── orchestrator.py      # Manages agent lifecycle and message passing
│   ├── agents/
│   │   ├── base.py          # BaseAgent class + LLMProvider (with mock)
│   │   ├── planner.py       # Generates carbon-optimal recommendations
│   │   ├── governance.py    # Enforces approval policies and risk rules
│   │   ├── executor.py      # Applies changes, generates tickets/PRs
│   │   ├── verifier.py      # Counterfactual MRV verification
│   │   ├── copilot.py       # Team summaries and gamification
│   │   └── carbon_accountant.py  # kgCO₂e calculation
│   ├── simulator/
│   │   ├── workload_generator.py  # Synthetic cloud workloads
│   │   ├── carbon_intensity.py    # Synthetic grid intensity time series
│   │   └── cost_model.py          # Cloud pricing model
│   └── shared/
│       ├── models.py         # Core data classes (Job, Recommendation, …)
│       ├── protocol.py       # Agent message-passing protocol
│       └── impact.py         # Environmental equivalency calculator
│
├── tests/
│   ├── test_protocol.py      # Agent communication protocol tests
│   ├── test_impact.py        # Impact calculator tests
│   └── test_config.py        # Configuration tests
│
└── data/                     # Generated output files (created on first run)
```

---

## How the LLM is Used

The system works **fully without an API key** — the mock LLM generates contextually appropriate responses for all agent tasks. When `OPENAI_API_KEY` is set, it switches to real GPT-4o-mini calls automatically.

The LLM handles:
- Generating human-readable rationales for recommendations
- Multi-round negotiation between Planner and Governance agents
- Risk assessment narratives for medium/high-risk changes
- Team summary messages and developer nudges
- Ticket/PR body generation

All *numbers* (emissions, costs, savings) are computed deterministically — the LLM only explains and communicates, never calculates.
