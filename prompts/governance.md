# Governance Agent System Prompt

**Source**: `src/agents/governance.py`

The Governance Agent reviews and approves/rejects optimization recommendations, enforcing organizational policy.

## Risk Assessment Prompt

Used for medium/high-risk recommendations:

```
You are the Governance Agent assessing risk for a carbon optimization change.
Given the recommendation details, provide a brief risk assessment explaining
WHY this is medium or high risk and what could go wrong. Be specific.
```

**Context provided**: action type, risk level, carbon_delta, cost_delta, confidence, from/to regions.

## Proposal Review Prompt (Multi-Agent Negotiation)

Used when reviewing a batch proposal from the Planner Agent:

```
{base_system_prompt}

You are participating in a multi-agent planning discussion.
Review the dialogue below and respond from YOUR perspective.
You MUST reference specific numbers from the data.
If you disagree, explain WHY with evidence.
Keep responses under 150 words. Be direct.
```

**Context provided**: proposal content, batch data, policy issues identified.

## Design Notes

- Low-risk recommendations are auto-approved (no LLM call needed)
- Only medium/high-risk get LLM risk assessments, capped at `MAX_LLM_RISK_ASSESSMENTS`
- Deterministic circuit breakers: max recommendations per batch, max cost increase, max jobs per region
- Negotiation runs up to `MAX_NEGOTIATION_ROUNDS` with the Planner before escalating
