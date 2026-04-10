# Use Cases

## UC1: Region-Shift Batch Jobs to Cleaner Grids

**Actor**: Planner Agent + Governance Agent

**Flow**:
1. Carbon Accountant identifies jobs in high-intensity regions (e.g., us-east-1 at ~350 gCO2/kWh)
2. Planner scores eligible jobs (SUSTAINABLE/BALANCED category) for region shift
3. Planner recommends shifting to cleaner regions (e.g., eu-north-1 at ~30 gCO2/kWh)
4. Governance reviews: auto-approves low-risk, challenges/rejects high-risk (cross-continent, production)
5. Executor applies change and generates Jira ticket with rationale
6. Verifier measures actual savings via counterfactual comparison

**Expected Outcome**: 50-90% reduction in per-job emissions for eligible workloads. Region shifts are the highest-impact optimization lever.

## UC2: Time-Shift CI/CD to Off-Peak Renewable Hours

**Actor**: Planner Agent

**Flow**:
1. Planner identifies CI/CD and batch jobs with flexible scheduling windows
2. Analyzes hourly grid intensity patterns (e.g., solar-heavy grids are cleaner midday)
3. Recommends deferral to cleaner time windows within the same region
4. Zero cost impact (same region, same infrastructure)
5. Verifier confirms savings based on actual grid intensity at execution time

**Expected Outcome**: 10-30% per-job reduction, zero cost. Low-risk optimization suitable for auto-approval.

## UC3: Governance Negotiation Blocking Risky Changes

**Actor**: Governance Agent + Planner Agent

**Flow**:
1. Planner proposes a batch of recommendations including some high-risk items (production workloads, cross-continent moves)
2. Governance reviews batch: identifies policy violations (e.g., regional concentration risk, cost > 20% increase)
3. Governance issues CHALLENGE with specific concerns referencing data
4. Planner responds with revised proposal (reduced scope, better distribution)
5. Negotiation continues up to MAX_NEGOTIATION_ROUNDS
6. Outcome: consensus (approved with modifications), rejected, or max rounds reached

**Expected Outcome**: Organizational policy is enforced before any change executes. High-risk changes are caught and negotiated down.

## UC4: Counterfactual Verification of Savings Claims

**Actor**: Verifier Agent

**Flow**:
1. After execution, Verifier retrieves: original job config, new job config, actual grid intensity at both times/regions
2. Computes counterfactual: "What would emissions have been without the change?"
3. Computes actual: "What were emissions after the change?"
4. Calculates verified savings = counterfactual - actual
5. Applies 90% confidence interval accounting for grid intensity uncertainty
6. Classifies: CONFIRMED (CI excludes zero), PARTIAL (positive but CI includes zero), REFUTED (wrong direction)
7. Generates machine-readable evidence chain for audit

**Expected Outcome**: Every claimed carbon saving has a traceable, auditable proof chain. No estimates — only verified outcomes.

## UC5: Team Leaderboard and Developer Nudges

**Actor**: Developer Copilot

**Flow**:
1. Copilot receives verified savings mapped to teams
2. Awards points: 100 pts/kgCO2e (confirmed), 50 pts/kgCO2e (partial), -50 pts (SLA violation)
3. Generates team rankings (leaderboard)
4. Creates personalized team summaries with specific numbers and actionable tips
5. Dashboard displays leaderboard, points log, and team narratives

**Expected Outcome**: Teams are incentivized to adopt carbon-efficient practices through gamification. Only verified savings earn points — no gaming the system.
