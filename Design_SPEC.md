# Design Spec — sust-AI-naible Carbon Optimization System

## 1. Product Overview

The sust-AI-naible system is a multi-agent platform designed to reduce cloud computing carbon emissions while balancing cost, latency, and service reliability.

Unlike traditional sustainability dashboards that only report emissions, this system operates as a **closed-loop optimization system** that continuously:

1. Collects cloud activity data
2. Calculates carbon emissions
3. Generates optimization recommendations
4. Executes approved changes
5. Verifies real-world outcomes

This loop enables organizations to actively reduce their carbon footprint while maintaining operational constraints such as cost and performance.

---

## 2. Target Users

### Platform Engineers
Responsible for managing cloud infrastructure and reviewing system recommendations.

### Developers
Receive insights through a developer copilot interface that highlights carbon and cost impacts of their workloads.

### Sustainability / Operations Teams
Use dashboards and reports to monitor emissions trends and verify carbon reduction outcomes.

---

## 3. Core System Workflow

The system operates through a continuous **agentic optimization loop**.

### Step 1 — Data Ingestion
The **Ingestor Agent** collects cloud usage data from multiple sources:

- Cloud billing APIs (AWS, GCP, Azure)
- Kubernetes metrics
- CI/CD pipelines
- job schedulers

This data is normalized into a canonical **activity ledger**.

---

### Step 2 — Carbon Accounting
The **Carbon Accountant Agent** calculates emissions for each activity record using deterministic formulas based on:

- grid carbon intensity
- power usage effectiveness (PUE)
- workload resource consumption

Each calculation includes uncertainty bounds and traceable emission factors.

---

### Step 3 — Optimization Planning
The **Planner Agent** analyzes workload patterns and produces optimization recommendations such as:

- shifting workloads to lower-carbon regions
- rescheduling jobs to cleaner time windows
- right-sizing infrastructure resources
- converting workloads to spot instances

Each recommendation includes estimated changes in:

- carbon emissions
- infrastructure cost
- system latency

---

### Step 4 — Execution
The **Executor Agent** translates approved recommendations into real infrastructure changes such as:

- GitHub pull requests modifying Terraform or Kubernetes configurations
- scheduler updates for batch workloads
- infrastructure provisioning changes

High-risk changes require human approval through the **Governance Agent**.

---

### Step 5 — Verification
The **Verifier Agent** measures the real-world outcomes of executed changes by comparing:

- actual emissions
- estimated emissions
- counterfactual emissions (what would have happened without the change)

Verified savings are stored with a full evidence chain to support auditability.

---

### Step 6 — Learning
Verification results are fed back into the system to improve future recommendations and update confidence levels.

---

## 4. Key User Interfaces

### Carbon Optimization Dashboard

Displays:

- total cloud emissions
- emissions by region
- emissions by team or workload
- recommended optimization actions

---

### Recommendation Review Interface

Platform engineers can review proposed changes before approval.

Each recommendation includes:

- estimated carbon savings
- estimated cost impact
- SLA risk assessment
- explanation of the recommendation

---

### Developer Copilot Interface

Integrated into developer workflows through tools like GitHub or Slack.

Features include:

- carbon impact notifications during pull requests
- suggestions for lower-carbon infrastructure configurations
- team-level carbon savings leaderboards

---

## 5. Design Principles

### Transparency
All emissions calculations are fully traceable and reproducible.

### Safety
Optimization recommendations must respect SLA constraints and governance rules.

### Auditability
Every carbon reduction claim includes a verifiable evidence chain.

### Human Oversight
High-impact system changes require human approval.

---

## 6. Key System Features

- Multi-agent carbon optimization architecture
- deterministic emissions calculations
- optimization solver for workload scheduling
- counterfactual verification of carbon savings
- uncertainty-aware decision making
- developer-facing sustainability insights

---

## 7. Prototype Scope (Checkpoint 2)

For the prototype stage, the system will demonstrate:

- ingestion of simulated workload data
- emissions calculation using regional carbon intensity
- generation of optimization recommendations
- simulated verification of carbon savings
- visualization of emissions and recommendations through a dashboard

The prototype will focus on demonstrating the closed-loop optimization concept rather than full infrastructure automation.
