# Safety & Privacy

## Personally Identifiable Information (PII)

- **No real user data is processed.** The system uses either synthetic team/job data or Azure VM traces with hashed identifiers (subscriptionId, deploymentId, vmId are anonymized in the Azure dataset).
- Team IDs are organizational labels (e.g., "platform", "ml-team"), not individual names.
- No email addresses, user names, or personal data flows through the pipeline.

## API Key Security

- All secrets (GROQ_API_KEY, EIA_API_KEY, ENTSOE_API_TOKEN) are stored in `.env` which is gitignored.
- `.env.example` contains only placeholder values, never real keys.
- On Streamlit Cloud, secrets are stored in the platform's encrypted secrets manager.
- No API keys are logged, printed, or included in pipeline outputs.

## LLM Safety Guardrails

### The LLM Never Computes Numbers

The core safety design: **LLMs explain, deterministic code computes.**

- All emissions calculations (`kgCO2e = vcpus * duration * PUE * grid_intensity`) are deterministic
- All cost calculations use fixed pricing formulas
- All verification uses deterministic counterfactual math
- The LLM generates rationales, ticket text, summaries, and negotiation dialogue
- An auditor can verify any number without running the LLM

### Agent Permissions and Restrictions

Each agent has explicit permissions and restrictions defined at initialization:
- **Planner**: Can recommend changes, cannot execute them
- **Governance**: Can approve/reject, cannot modify recommendations
- **Executor**: Can apply approved changes, cannot bypass governance
- **Verifier**: Read-only — computes verification math, cannot change any config

### Jailbreak / Prompt Injection Mitigation

- System prompts are hardcoded in agent source files, not user-editable
- The "Ask the Agent" chat interface has a fixed system prompt with pipeline context
- LLM outputs are used as text strings only — never parsed as code or executed
- Rate limiting prevents excessive LLM calls (token budget: 100K total, configurable)
- If any LLM call fails or returns unexpected content, the agent falls back to deterministic behavior

## Rate Limiting

### Token Budget

- `MAX_TOTAL_LLM_TOKENS` (default: 100,000) caps total token usage per pipeline run
- Before each LLM call, estimated token cost is checked against remaining budget
- When budget is exceeded, agents fall back to deterministic template responses
- This prevents runaway costs and Groq's daily token limit

### API Rate Limits

- Exponential backoff: 5 retries with 2/4/8/16/32 second delays on 429 errors
- Final fallback: 300-second wait before last attempt
- If all retries fail, agent returns deterministic response (pipeline continues)
- EIA and ENTSO-E responses are cached locally (`data/.cache/`) to reduce API calls

## Audit Trail

Every pipeline run produces:
- `data/agent_traces.json` — Full reasoning trace for every agent (LLM inputs/outputs, tool calls)
- `data/agent_dialogues.json` — Complete negotiation transcripts between agents
- `data/evidence_chains.json` — Machine-readable verification proof for every claimed saving
- `data/pipeline_summary.json` — Pipeline metadata, metrics, and configuration snapshot

These files enable post-hoc auditing of any decision or claim made by the system.
