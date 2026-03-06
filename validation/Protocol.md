# Complex Prompt Experiment — Prototype Generation

As part of our validation process, we tested whether modern LLM tools could generate the architecture for a full carbon-aware platform. This experiment evaluated the ability of LLM tools to reason about system architecture, multi-agent orchestration, and sustainability-focused infrastructure.

The goal was to determine whether LLMs could help bootstrap a prototype system capable of supporting carbon-aware workload scheduling and internal carbon budgeting.

## Tool Used

- GitHub Copilot
- Claude Opus 4.6
- NotebookLM to brainstorm

Copilot was used because it integrates directly with development workflows and can assist in generating system architecture, scaffolding code, and agent logic.

---

# Prompt Used

The following prompt was provided to Copilot to generate a prototype architecture for the system:



sust-AI-naible → Carbon Currency Platform (Greenfield System Spec)

Vision
A carbon-native operating system for engineering teams: carbon becomes an internal currency, budgets become constraints, trades become incentives, and every claim produces auditable evidence (CSRD-ready).

System Boundaries & Core Objects

Core entities (the platform’s “ledger”)

Workload: a unit of compute with team ownership, SLA, cost envelope, flexibility window.

CarbonIntensityFeed: time-series intensity by region (real + provenance).

CarbonEstimate: projected emissions for workload under a candidate plan.

Decision: governance approval/reject/challenge with rationale + constraints checked.

Verification: counterfactual vs actual emissions + statistical significance.

CarbonBudget: weekly allocation per team (kgCO2e).

CarbonTrade: transfer of budget between teams (brokered, approved).

ProofOfImpactCard: one-page evidence artifact per verified saving.

Everything else is a service that produces/consumes these objects.

Platform Architecture (New System)

Services

Carbon Data Service
Pulls real carbon intensity + caches + provenance.

Workload Intake Service
Receives jobs from synthetic generator or scheduler export.

Planner Service (Carbon Futures Trader)
Inputs workloads + 72h intensity forecast + cost model.

Governance Service (Constitution Engine)
Validates recommendations against SLA/cost constraints.

Execution Service
Triggers scheduling decisions.

Verification Service
Computes counterfactual vs actual emissions + confidence interval.

Carbon Market Service
Manages carbon budgets and trades.

Proof-of-Impact Service
Generates evidence cards.

Dashboard
Displays weekly carbon impact and budget leaderboard.

(remaining architecture specification omitted for brevity)




---

# Observed Results

Copilot successfully generated a **structured system architecture** including:

- service separation
- data contracts
- repository layout
- prototype pipeline structure.

However, several issues were observed:

- The system specification was **very complex**, which made it difficult for the model to generate fully working code automatically.
- In some cases the agent orchestration logic entered **reasoning loops**, which caused the system to hit **token and rate limits**.
- Additional manual intervention was required to refine prompts and enforce termination conditions.

---

# Key Insights

This experiment demonstrated that LLM tools can:

- generate high-level system architecture
- assist with scaffolding complex agent-based systems
- support debugging and orchestration logic.

However, they struggle with:

- maintaining stability in multi-agent workflows
- handling long reasoning chains
- managing token limits in complex simulations.
- THEY BUILD TOO MUCH TOO SOON AND IT IS DIFFICULT TO TONE IT DOWN. I would rather have something that walks hand in hand with me and helpes me build the system with too much planning.
- It is difficult to change the output once it is generated since the LLMs become more biased and bent towards a certain kind of output. 

---

# Design Implications

These findings influenced the design of our system by motivating:

- clearer service boundaries between agents
- structured data contracts between system components
- safeguards to prevent recursive agent loops
- modular architecture for easier debugging and scaling.

