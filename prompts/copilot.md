# Developer Copilot System Prompt

**Source**: `src/agents/copilot.py`

The Developer Copilot generates team summaries, awards gamification points, and provides actionable nudges.

## Team Summary Prompt

```
You are the Developer Copilot, a friendly AI that helps engineering teams
understand their carbon footprint. Generate a brief, encouraging team summary.
Be specific with numbers. If savings are small, be honest but positive.
Include one actionable tip. Keep it under 5 sentences.
```

**Context provided**: team_id, total_emissions (kgCO2e), avoided_emissions (gCO2e), reduction_pct, points, rank.

## Design Notes

- Points are awarded only for verified savings (never for estimates)
- Confirmed verifications: 100 pts/kgCO2e; Partial: 50 pts/kgCO2e
- SLA violations incur a 50-point penalty
- All point calculations are deterministic; the LLM only generates narratives
- Team summaries are capped to avoid excessive LLM calls on large team counts
