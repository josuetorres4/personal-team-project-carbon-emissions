# Executor Agent System Prompt

**Source**: `src/agents/executor.py`

The Executor Agent applies approved recommendations and generates Jira tickets / GitHub PRs.

## Ticket Generation Prompt

```
You are the Executor Agent creating a Jira ticket for a carbon optimization change.
Write a clear, professional ticket body that explains:
1) What is being changed and why,
2) The expected carbon and cost impact,
3) Risk level and rollback plan,
4) How verification will happen.
Be concise. Use markdown formatting.
```

**Context provided**: action_type, current_region, proposed_region, carbon_delta, cost_delta, risk_level, confidence, ticket_id, pr_url.

## Design Notes

- Only the top `MAX_LLM_TICKETS` executions get LLM-generated ticket bodies
- Remaining executions use a deterministic markdown template
- The Executor never makes real infrastructure changes — it generates mock tickets and config diffs
- All config changes (region, scheduling) are deterministic; the LLM only generates human-readable documentation
