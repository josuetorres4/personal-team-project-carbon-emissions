# Telemetry & Observability

## What Gets Logged

### Agent Reasoning Traces (`data/agent_traces.json`)

Every agent maintains a working memory with:
- **Reasoning steps**: Each LLM call is logged with input prompt, output text, and timestamp
- **Tool calls**: Every tool invocation is logged with inputs, output (truncated to 500 chars), and timestamp
- **Context keys**: What shared data the agent had access to

Example trace entry:
```json
{
  "agent": "Planner Agent",
  "purpose": "Generate carbon optimization recommendations",
  "memory": {
    "reasoning_trace": [
      {
        "step": "llm_reasoning",
        "content": "Moving this workload from Virginia to Stockholm...",
        "timestamp": "2025-01-01T12:00:00"
      }
    ],
    "actions_taken": [
      {
        "tool": "compute_carbon_delta",
        "inputs": {"job_id": "abc123", "target_region": "eu-north-1"},
        "output": "-0.045 kgCO2e",
        "timestamp": "2025-01-01T12:00:01"
      }
    ]
  }
}
```

### Agent Dialogues (`data/agent_dialogues.json`)

Full multi-agent negotiation transcripts:
- Topic, participating agents, max rounds
- Each message: sender, recipient, message type (PROPOSAL/CHALLENGE/APPROVAL/REJECTION), content, structured data
- Outcome: consensus, rejected, or max_rounds_reached

### Evidence Chains (`data/evidence_chains.json`)

Machine-readable verification proof for every claimed saving:
- verification_id, recommendation_id
- Counterfactual emissions (what would have happened)
- Actual emissions (what did happen)
- Verified savings with 90% confidence interval
- Step-by-step evidence chain with data at each step

### Pipeline Summary (`data/pipeline_summary.json`)

High-level metrics:
- Timestamp, LLM provider, simulation parameters
- Baseline vs optimized emissions and cost
- Pipeline stats: recommendations generated/approved/executed/verified
- Gamification: total points, team standings
- Agent activity: reasoning steps and tool calls per agent

## CSV Outputs

| File | Description |
|---|---|
| `jobs_baseline.csv` | All jobs with baseline emissions |
| `jobs_optimized.csv` | All jobs after optimization |
| `carbon_intensity.csv` | Hourly grid intensity per region |
| `recommendations.csv` | All planner recommendations |
| `governance_decisions.csv` | Approval/rejection decisions with reasoning |
| `executions.csv` | Executed changes with old/new configs |
| `verifications.csv` | Verification results with confidence intervals |
| `points.csv` | Points awarded per verification |
| `leaderboard.csv` | Team rankings |

## Debugging

### Common Debug Scenarios

1. **"Why was this recommendation rejected?"**
   - Check `governance_decisions.csv` for `decision` and `reason` columns
   - Check `agent_traces.json` > governance agent > reasoning_trace for LLM assessment
   - Dashboard: "Agent Reasoning" page > Governance Agent

2. **"Are the savings real?"**
   - Check `verifications.csv` for `verification_status` and `ci_lower`/`ci_upper`
   - Check `evidence_chains.json` for step-by-step proof
   - Dashboard: "Evidence Explorer" page

3. **"What did the agents say to each other?"**
   - Check `agent_dialogues.json` for full transcripts
   - Dashboard: "The Debate" page with color-coded messages

4. **"Is the LLM being used or mock?"**
   - Check `pipeline_summary.json` > `llm_provider` field
   - Dashboard: sidebar shows "Data Sources" with LLM indicator
   - Agent Reasoning page shows mock/live banner

### Dashboard Observability Pages

- **Agent Reasoning**: Browse every reasoning step and tool call per agent
- **Evidence Explorer**: Drill into any verification with its evidence chain
- **The Debate**: Read full Planner-Governance negotiation transcripts
- **Ask the Agent**: Interactive Q&A about pipeline results
