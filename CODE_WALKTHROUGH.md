# Code Walkthrough — sust-AI-naible

A guided tour of the implementation for readers who want to understand the code
without running it. Start here after reading the README.

---

## Table of Contents

1. [Where to start reading](#1-where-to-start-reading)
2. [Complete data flow at a glance](#2-complete-data-flow-at-a-glance)
3. [Module-by-module reference](#3-module-by-module-reference)
4. [Key algorithms explained](#4-key-algorithms-explained)
5. [The AI / determinism boundary](#5-the-ai--determinism-boundary)
6. [How agents communicate](#6-how-agents-communicate)
7. [Configuration and extension points](#7-configuration-and-extension-points)
8. [Common patterns across the codebase](#8-common-patterns-across-the-codebase)

---

## 1. Where to start reading

There are two practical entry points depending on what you want to understand.

### Option A — follow the orchestrator

Open `run_pipeline.py` first. It is six lines:

```python
orchestrator = Orchestrator(llm_provider="auto", verbose=True)
summary = orchestrator.run(sim_start=datetime(2025, 1, 1), sim_days=30, seed=42, ...)
```

Then open `src/orchestrator.py`. The `run()` method (starting at line 75) is a
sequential script that calls each agent in order and is easy to read top-to-bottom.
Every comment block is prefixed with the pipeline stage name:

```
# ── SENSE   ─── step 1
# ── MODEL   ─── step 2
# ── DECIDE  ─── step 3 (planner + governance)
# ── ACT     ─── step 4
# ── VERIFY  ─── step 5
# ── LEARN   ─── step 6
```

Reading these six blocks gives you the complete picture of what the system does.

### Option B — follow the data models

Open `src/shared/models.py`. It is short and defines every data structure the
system uses. Reading it top-to-bottom answers "what are the nouns?":

| Class | What it represents |
|---|---|
| `Job` | A single cloud workload (one CI build, one training run, etc.) |
| `EmissionsRecord` | Carbon attributed to one Job, with uncertainty bounds |
| `Recommendation` | A Planner suggestion to change a Job's region or schedule time |
| `VerificationRecord` | Proof that a Recommendation's claimed savings actually happened |
| `WorkloadCategory` | Enum: URGENT (can't move), BALANCED (≤4 hr flex), SUSTAINABLE (≤24 hr flex) |

Once you know these five types, the rest of the code reads naturally.

---

## 2. Complete data flow at a glance

```
run_pipeline.py
    └── Orchestrator.run()
            │
            ├─[SENSE]──── workload_generator.generate_workloads()
            │               → list[Job]  (≈24,000 jobs for 30 days)
            │             carbon_intensity.generate_intensity_timeseries()
            │               → DataFrame  (hourly gCO₂/kWh per region)
            │
            ├─[MODEL]──── carbon_accountant.compute_emissions_batch(jobs, intensity_df)
            │               → list[EmissionsRecord]  (one per job)
            │
            ├─[DECIDE]─── PlannerAgent.run({jobs, intensity_df})
            │               → list[Recommendation]  (region/time shifts)
            │             Orchestrator._negotiate_plan()
            │               → Dialogue  (Planner ↔ Governance multi-round chat)
            │             GovernanceAgent.run({recommendations})
            │               → list[GovernanceDecision]  (approved / rejected)
            │
            ├─[ACT]────── ExecutorAgent.run({approved_recs, jobs})
            │               → list[Job]  optimized_jobs  (new region/time)
            │               → list[ExecutionRecord]  (Jira tickets, audit trail)
            │
            ├─[VERIFY]─── verify_batch(approved_recs, original_jobs, optimized_jobs, ...)
            │               → list[VerificationRecord]  (savings with 90% CI)
            │
            └─[LEARN]──── CopilotAgent.run({verifications, team_emissions, ...})
                            → list[PointsEntry]  (100 pts / kgCO₂e verified)
                            → leaderboard  (ranked teams)
```

Data flows **forward only**. No agent reads or modifies the output of a later stage.

---

## 3. Module-by-module reference

### `config.py`

One class, `Config`, with class-level attributes. Every magic number in the
codebase is defined here and can be overridden via an environment variable or
`.env` file. Agents import it at module load time with a graceful fallback:

```python
try:
    from config import Config as _Config
    _CARBON_PRICE_PER_TON = _Config.CARBON_PRICE_PER_TON
except Exception:
    _CARBON_PRICE_PER_TON = 75.0   # hard-coded default
```

### `src/shared/models.py`

Pure data classes (Python `dataclass`). No logic, no imports from other project
files. Every `job_id`, `recommendation_id`, etc. is auto-generated via
`uuid.uuid4()[:8]` to stay short but unique within a run.

### `src/shared/protocol.py`

Three classes:
- `MessageType` — enum of conversation acts: PROPOSAL, CHALLENGE, REVISION,
  APPROVAL, REJECTION, CONSENSUS, ESCALATION
- `AgentMessage` — one message, carries a `content` string (LLM text) plus
  `structured_data` dict (machine-readable facts)
- `Dialogue` — ordered collection of `DialogueRound` objects; `to_audit_record()`
  serialises the full conversation to a plain dict for JSON export

### `src/shared/impact.py`

Two pure functions, no state:
- `compute_equivalencies(kg_co2e)` — divides the savings by EPA conversion
  factors (miles/tree/smartphone) and returns the top-N most meaningful ones
- `compute_business_impact(...)` — builds a report across four carbon pricing
  scenarios ($15–$204/ton) with annualised projections

### `src/simulator/workload_generator.py`

`generate_workloads(start, num_days, seed)` creates `Job` objects using NumPy
random draws. The distributions are documented in the module docstring. Key
design choice: every `Job` is tagged with `category` (URGENT/BALANCED/SUSTAINABLE)
at creation time; the Planner reads this field to decide which jobs it is
allowed to touch.

### `src/simulator/carbon_intensity.py`

`generate_intensity_timeseries(start, num_days, seed)` returns a DataFrame with
columns `[timestamp, region, intensity_gco2_kwh, intensity_lower, intensity_upper]`.
Five hard-coded regions (us-east-1 ≈ 350, eu-north-1 ≈ 30, ap-south-1 ≈ 700).
Intensity follows a sine wave + noise. The ±20% uncertainty bands become the
confidence intervals that flow all the way to the Verifier.

`get_intensity_at(df, region, timestamp)` is the lookup helper used by the
Carbon Accountant and Verifier.

### `src/simulator/cost_model.py`

`compute_total_cost(region, vcpus, gpu_count, duration_hours)` is a lookup table
plus a cross-region egress surcharge. Used by the Planner when scoring
(region, time) candidates.

### `src/agents/base.py`

Two classes:

**`LLMProvider`** — thin wrapper. `chat(system_prompt, user_message)` routes to
OpenAI or the built-in mock. The mock matches keywords in `system_prompt` to
return a contextually appropriate canned response (rationale, ticket body,
team summary, risk assessment, or dialogue turn). This makes the whole system
runnable offline.

**`BaseAgent`** — abstract base class for all agents. Provides:
- `self.memory` — `AgentMemory` object with `add_reasoning(key, text)` and
  a list of `actions_taken`
- `self.tools` — dict of registered callable tools (see `add_tool()`)
- `reason(system_prompt, user_message)` — calls the LLM and records the call
  in the trace
- `get_trace()` — returns a serialisable dict for `agent_traces.json`

Every concrete agent calls `super().__init__(name, purpose, llm, permissions,
restrictions)` and overrides `run(task)`.

### `src/agents/carbon_accountant.py`

No class, just functions. `compute_emissions_batch()` is vectorised via pandas
merge. `compute_emissions_for_config()` is the what-if variant used by the
Planner during candidate scoring.

### `src/agents/planner.py`

`PlannerAgent.run()` loops over all jobs, skips URGENT and already-clean-region
jobs, and calls `_plan_single_job()` for each candidate. After the deterministic
scoring pass, `_enrich_with_llm_rationales()` asks the LLM to write a two- or
three-sentence explanation for each recommendation.

`propose_batch_strategy()` is a separate method used only during negotiation: it
groups recommendations by target region, summarises totals, and returns an
`AgentMessage` of type PROPOSAL.

### `src/agents/governance.py`

`GovernanceAgent.run()` loops over recommendations and applies risk thresholds:

| Condition | Risk level assigned |
|---|---|
| `est_cost_delta_usd > 5% of job cost` | HIGH |
| `est_cost_delta_usd > 1% of job cost` | MEDIUM |
| otherwise | LOW |

HIGH-risk recommendations are not auto-approved (held for human review in a real
deployment; in the simulation they are approved at a configurable rate for demo
purposes). A batch-level circuit breaker rejects the entire batch if the total
cost increase exceeds `MAX_BATCH_COST_INCREASE` or a single region receives more
than `MAX_JOBS_PER_REGION_PER_BATCH` reassignments.

### `src/agents/executor.py`

`ExecutorAgent.run()` applies each approved `Recommendation` to the matching
`Job`, producing a new `Job` with updated `region` and `started_at`. For each
change it also calls the LLM to generate a mock Jira ticket body. Returns the
modified jobs and a list of `ExecutionRecord` objects used by the Verifier.

### `src/agents/verifier.py`

`verify_single()` is the core function. See [§4](#4-key-algorithms-explained)
for a step-by-step breakdown.

`verify_batch()` is a thin loop; `format_evidence_chain()` pretty-prints any
`VerificationRecord`'s evidence chain for human review.

### `src/agents/copilot.py`

`CopilotAgent.run()` awards points only for *verified* savings (`points =
verified_savings_kgco2e × 100`), subtracts a penalty for SLA violations, and
calls the LLM to write a per-team "carbon receipt" narrative. Returns a sorted
leaderboard dict.

### `src/orchestrator.py`

`_negotiate_plan()` drives the Planner↔Governance multi-round dialogue. It calls
`planner.propose_batch_strategy()` to get a `PROPOSAL` message, calls
`governance.evaluate_proposal()` to get back an `APPROVAL`, `CHALLENGE`, or
`REJECTION`, and repeats up to `MAX_NEGOTIATION_ROUNDS` rounds. The full
`Dialogue` object is saved to `data/agent_dialogues.json`.

---

## 4. Key algorithms explained

### 4a. Emissions calculation

**File:** `src/agents/carbon_accountant.py`, function `compute_emissions_batch()`

The formula is:

```
power_kW    = (vCPUs × 0.005 + GPUs × 0.300) × PUE(1.1)
energy_kWh  = power_kW × duration_hours
kgCO₂e      = energy_kWh × (grid_intensity_gCO₂_kWh / 1000)
```

Constants (all marked "Assumption" in the source):
- `0.005 kW/vCPU` — assumes a 200 W server split across 40 vCPUs
- `0.300 kW/GPU` — NVIDIA A100 class
- `PUE = 1.1` — hyperscaler average per Google/AWS sustainability reports

Uncertainty is propagated by running the same formula with the lower and upper
bounds of grid intensity. The result is three numbers: `kgco2e`, `kgco2e_lower`,
`kgco2e_upper`. These bounds flow forward into the Verifier's confidence intervals.

### 4b. Planner scoring

**File:** `src/agents/planner.py`, function `_plan_single_job()`

For each non-urgent job, the Planner evaluates every feasible (region, time) pair
and picks the one with the lowest *effective cost*:

```
effective_cost = cloud_cost_usd + (kgCO₂e × carbon_price_per_kg)
```

where `carbon_price_per_kg = CARBON_PRICE_PER_TON / 1000` (default $0.075/kg).

A recommendation is only emitted if the new effective cost is lower than the
current one **and** the carbon reduction is at least `MIN_CARBON_REDUCTION_PCT`
(default 10%). This prevents trivially small wins from flooding the output.

Deferral windows (the allowed time range) come from the `WorkloadCategory`:

| Category | Max deferral |
|---|---|
| URGENT | 0 hours (skipped entirely) |
| BALANCED | 4 hours |
| SUSTAINABLE | 24 hours |

### 4c. Counterfactual verification

**File:** `src/agents/verifier.py`, function `verify_single()`

This is the system's core differentiator. The key question is: *what would
emissions have been if we had NOT moved the job?*

Step 1 — compute **actual** emissions using the job's new (post-move) region and
the grid intensity at execution time.

Step 2 — compute **counterfactual** emissions using the same energy consumption
(`energy_kWh = power × duration`) but the grid intensity of the *original* region
at the *actual execution time*. We reuse the actual execution time (not the
planned original time) to isolate the spatial effect of the move.

```
actual       = energy_kWh × intensity(new_region, actual_time)
counterfactual = energy_kWh × intensity(old_region, actual_time)
savings      = counterfactual - actual
```

Step 3 — compute a 90% confidence interval via interval arithmetic:

```
ci_lower = counterfactual_lower - actual_upper   # most conservative
ci_upper = counterfactual_upper - actual_lower   # most optimistic
```

Step 4 — classify the result:
- `ci_lower > 0` → **confirmed** (even the worst-case shows savings)
- `savings > 0` but `ci_lower ≤ 0` → **partial** (likely savings, CI spans zero)
- `savings ≤ 0` → **refuted**

Step 5 — build the evidence chain: a list of dicts recording every input value,
the formula applied, the intermediate results, and a SHA-256 hash of the inputs
for tamper detection.

---

## 5. The AI / determinism boundary

A deliberate design principle runs throughout the codebase: **LLMs explain and
communicate; they never calculate**.

| Task | Who does it | Why |
|---|---|---|
| kgCO₂e formula | Deterministic (`carbon_accountant.py`) | Must be auditable |
| Planner candidate scoring | Deterministic (`planner.py`) | Reproducible + verifiable |
| Governance threshold checks | Deterministic (`governance.py`) | No hallucination risk |
| Counterfactual savings math | Deterministic (`verifier.py`) | Evidence chain integrity |
| Points awarded | Deterministic (`copilot.py`) | Prevent gaming |
| Recommendation rationale text | LLM (`planner.py`) | Natural language only |
| Risk assessment narrative | LLM (`governance.py`) | Contextual interpretation |
| Jira ticket body | LLM (`executor.py`) | Formatting, not logic |
| Team summary "carbon receipt" | LLM (`copilot.py`) | Communication, not accounting |
| Negotiation dialogue | LLM (both sides via `base.py`) | Multi-round reasoning |

The `BaseAgent.reason()` method (in `src/agents/base.py`) is the single
controlled entry point for all LLM calls. Every call is logged in the agent's
trace so the reasoning is inspectable in `data/agent_traces.json`.

---

## 6. How agents communicate

The Planner and Governance agents hold a structured dialogue before individual
recommendations are evaluated. The protocol is in `src/shared/protocol.py`.

### Message types

```
PROPOSAL   — Planner sends a batch plan
CHALLENGE  — Governance asks for changes ("reduce regional concentration")
REVISION   — Planner responds to a challenge
APPROVAL   — Governance accepts the current plan
REJECTION  — Governance rejects (escalates to human)
CONSENSUS  — Both sides agree; loop ends
```

### Dialogue lifecycle

```python
dialogue = Dialogue(topic="Carbon optimisation batch", max_rounds=4)

# Round 0
msg_proposal = planner.propose_batch_strategy(recommendations, intensity_df)
dialogue.add_message(msg_proposal)   # MessageType.PROPOSAL

# Round 1
msg_response = governance.evaluate_proposal(msg_proposal, dialogue)
dialogue.add_message(msg_response)   # MessageType.APPROVAL or CHALLENGE

# Rounds 2–N (if governance challenged)
while not consensus and rounds < max_rounds:
    msg_revision = planner.respond_to_challenge(msg_response, dialogue)
    dialogue.add_message(msg_revision)
    msg_response = governance.evaluate_proposal(msg_revision, dialogue)
    dialogue.add_message(msg_response)

dialogue.outcome = "consensus" / "max_rounds_reached" / "rejected"
```

Each `AgentMessage` carries:
- `content` — LLM-generated reasoning text (human-readable)
- `structured_data` — machine-readable dict (region counts, cost totals, etc.)
- `round_number` — which round this belongs to
- `in_reply_to` — message_id of the message this is responding to

The full transcript is exported by `dialogue.to_audit_record()` and saved to
`data/agent_dialogues.json`.

---

## 7. Configuration and extension points

### Changing numeric parameters

Edit `config.py` or create a `.env` file (see `.env.example`). Every parameter
is described inline in `config.py`. No code changes needed.

### Adding a new region

1. Add an entry to `REGIONS` in `src/shared/models.py`.
2. Add a corresponding profile to `REGION_PROFILES` in
   `src/simulator/carbon_intensity.py` (base intensity, amplitude, phase).
3. Add a cost entry in `src/simulator/cost_model.py`.

### Replacing the mock LLM with a real one

Set `OPENAI_API_KEY` in your environment or `.env` file. The `LLMProvider` in
`src/agents/base.py` auto-detects the key and switches to `gpt-4o-mini`. The
`provider` attribute is logged at startup so you can verify which path is active.

### Replacing the synthetic workloads with real data

The Orchestrator expects `jobs: list[Job]` and `intensity_df: pd.DataFrame`.
Both are constructed by the simulator functions at the start of
`Orchestrator.run()`. Replace those two calls with your own data loading code
and the rest of the pipeline runs unchanged.

---

## 8. Common patterns across the codebase

### Every agent method returns a dict with a `trace` key

```python
return {
    "recommendations": recommendations,   # the actual output
    "stats": {...},                        # summary numbers for logging
    "trace": self.get_trace(),             # full reasoning log
}
```

The orchestrator collects these traces in `self.agent_traces` and writes them to
`data/agent_traces.json`.

### Vectorised batch operations with per-record fallback

`compute_emissions_batch()` uses a pandas merge for speed. If the merge misses a
timestamp (e.g., for a job outside the simulated date range), it falls back to the
region's average intensity. The same pattern appears in the Planner and Executor.

### Config import with graceful fallback

Every module that reads from `config.py` wraps the import in `try/except`:

```python
try:
    from config import Config as _Config
    _CARBON_PRICE_PER_TON = _Config.CARBON_PRICE_PER_TON
except Exception:
    _CARBON_PRICE_PER_TON = 75.0
```

This means the module works even if `config.py` is absent or broken.

### Append-only evidence chains

`VerificationRecord.evidence_chain` is a list of dicts. Each dict describes one
step of the verification computation (inputs, formula, outputs, hash). Steps are
appended; none are modified. This mirrors real-world MRV audit logs.

### Uncertainty propagated as interval pairs

Instead of a single number, carbon quantities almost always travel as a triple:
`(kgco2e, kgco2e_lower, kgco2e_upper)`. The lower/upper bounds originate from
the ±20% uncertainty in grid intensity data and flow through every stage
unchanged. The Verifier then uses them to compute confidence intervals via simple
interval arithmetic rather than Monte Carlo simulation (much faster for ~24K jobs).
