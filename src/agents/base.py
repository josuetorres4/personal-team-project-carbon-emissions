"""
Agent Base Class
================
Real agent framework with LLM reasoning, tool use, memory, and audit trails.

What makes these actual AI agents (not just functions):
  1. LLM Reasoning: Agents use an LLM to interpret context, make judgments,
     and generate natural language outputs
  2. Tool Use: Agents have defined tools they can call (DB queries, APIs, calculators)
  3. Memory: Agents read/write to shared memory stores and maintain conversation history
  4. Autonomy: The orchestrator delegates; agents decide HOW to accomplish their goals
  5. Guardrails: Each agent has explicit permissions and constraints

The AI/Deterministic boundary:
  - LLM handles: interpretation, explanation, summarization, policy parsing
  - Deterministic handles: math, optimization, verification, compliance checks
  - The agent WRAPS both — it uses the LLM to reason and deterministic tools to compute
"""

import json
import os
import time
from datetime import datetime
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from abc import ABC, abstractmethod

# Lazy import to avoid circular dependency — protocol imports nothing from agents
def _get_protocol():
    from src.shared.protocol import AgentMessage, Dialogue, MessageType
    return AgentMessage, Dialogue, MessageType


# Keywords that signal a multi-agent dialogue request in the mock LLM
_DIALOGUE_KEYWORDS = ("multi-agent", "dialogue", "respond", "assessment", "planning discussion")


# ── LLM Provider ──────────────────────────────────────────────────────

class LLMProvider:
    """
    Wrapper for LLM calls. Supports OpenAI API, Groq API (OpenAI-compatible),
    or falls back to a local mock for development/testing without API keys.

    Tracks total token usage across all calls and enforces a configurable
    budget (MAX_TOTAL_LLM_TOKENS, default 100,000) to avoid hitting
    provider-side rate limits such as Groq's tokens-per-day cap.
    """

    # Fallback returned when the token budget is exhausted
    BUDGET_EXCEEDED_RESPONSE = (
        "[Token budget exceeded — falling back to deterministic processing]"
    )

    # Fallback returned when rate-limit retries are exhausted
    RATE_LIMIT_RESPONSE = (
        "[Rate limit exceeded — falling back to deterministic processing]"
    )

    def __init__(
        self,
        provider: str = "auto",
        max_total_tokens: Optional[int] = None,
        model: Optional[str] = None,
    ):
        """
        Args:
            provider: "openai", "groq", "anthropic", "mock", or "auto".
                      Auto tries groq → openai → mock.
            max_total_tokens: Optional token budget override.
                              Defaults to Config.MAX_TOTAL_LLM_TOKENS.
            model: Optional model override. If provided, replaces the
                   provider-default model.
        """
        from config import Config
        self.provider = provider
        self._client = None
        self._model = model or os.environ.get("LLM_MODEL", "gpt-4o-mini")

        # Token tracking — split prompt / completion for energy estimation
        self.total_tokens_used = 0
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.call_count = 0
        self.call_log: list[dict] = []  # per-call details for the audit trail

        self.max_total_tokens = (
            max_total_tokens if max_total_tokens is not None
            else Config.MAX_TOTAL_LLM_TOKENS
        )
        if provider == "auto":
            if os.environ.get("GROQ_API_KEY"):
                self.provider = "groq"
            elif os.environ.get("OPENAI_API_KEY"):
                self.provider = "openai"
            else:
                self.provider = "mock"

        if self.provider == "groq":
            try:
                from openai import OpenAI
                self._client = OpenAI(
                    api_key=os.environ["GROQ_API_KEY"],
                    base_url="https://api.groq.com/openai/v1",
                )
                self._model = model or os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
            except Exception as e:
                print(f"  [LLM] Groq init failed: {e}. Falling back to mock.")
                self.provider = "mock"

        if self.provider == "openai":
            try:
                from openai import OpenAI
                self._client = OpenAI()
                self._model = model or os.environ.get("LLM_MODEL", "gpt-4o-mini")
            except Exception as e:
                print(f"  [LLM] OpenAI init failed: {e}. Falling back to mock.")
                self.provider = "mock"

        if self.provider == "anthropic":
            try:
                import anthropic  # type: ignore
                api_key = os.environ.get("ANTHROPIC_API_KEY")
                if not api_key:
                    raise RuntimeError("ANTHROPIC_API_KEY not set")
                self._client = anthropic.Anthropic(api_key=api_key)
                self._model = model or Config.FRONTIER_MODEL
            except Exception as e:
                print(f"  [LLM] Anthropic init failed: {e}. Falling back to mock.")
                self.provider = "mock"

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Rough token estimate: ~1 token per 4 characters for English text."""
        return max(1, len(text) // 4)

    @property
    def token_budget_remaining(self) -> int:
        """Tokens still available under the budget."""
        return max(0, self.max_total_tokens - self.total_tokens_used)

    @property
    def token_budget_exceeded(self) -> bool:
        """True when the total token budget has been exhausted."""
        return self.total_tokens_used >= self.max_total_tokens

    def chat(self, system_prompt: str, user_message: str, temperature: float = 0.3) -> str:
        """Send a chat completion request.

        If the estimated token cost of this call would push usage over
        ``max_total_tokens``, the API call is skipped and a deterministic
        fallback string is returned instead.
        """
        estimated_input = (
            self.estimate_tokens(system_prompt)
            + self.estimate_tokens(user_message)
        )
        # Reserve headroom for the completion (max_tokens from config)
        from config import Config
        estimated_total = estimated_input + Config.LLM_MAX_TOKENS

        if self.total_tokens_used + estimated_total > self.max_total_tokens:
            remaining = self.token_budget_remaining
            print(
                f"  [LLM] Token budget would be exceeded "
                f"({self.total_tokens_used} used + ~{estimated_total} estimated "
                f"> {self.max_total_tokens} limit, {remaining} remaining). "
                f"Falling back to deterministic response."
            )
            return self.BUDGET_EXCEEDED_RESPONSE

        if self.provider in ("openai", "groq"):
            return self._chat_openai(system_prompt, user_message, temperature)
        elif self.provider == "anthropic":
            return self._chat_anthropic(system_prompt, user_message, temperature)
        else:
            return self._chat_mock(system_prompt, user_message)

    def complete(self, prompt: str, temperature: float = 0.3) -> str:
        """Single-prompt completion (convenience wrapper around chat)."""
        return self.chat("You are a helpful assistant.", prompt, temperature)

    def _record_usage(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        kind: str = "openai",
    ) -> None:
        self.total_prompt_tokens += prompt_tokens
        self.total_completion_tokens += completion_tokens
        self.total_tokens_used += prompt_tokens + completion_tokens
        self.call_count += 1
        self.call_log.append({
            "kind": kind,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        })

    def _chat_openai(self, system_prompt: str, user_message: str, temperature: float) -> str:
        from config import Config
        max_retries = 5
        base_delay = 2.0
        for attempt in range(max_retries):
            try:
                response = self._client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    temperature=temperature,
                    max_tokens=Config.LLM_MAX_TOKENS,
                )
                content = response.choices[0].message.content
                if response.usage is not None:
                    self._record_usage(
                        prompt_tokens=response.usage.prompt_tokens,
                        completion_tokens=response.usage.completion_tokens,
                        kind=self.provider,
                    )
                else:
                    self._record_usage(
                        prompt_tokens=self.estimate_tokens(system_prompt) + self.estimate_tokens(user_message),
                        completion_tokens=self.estimate_tokens(content or ""),
                        kind=self.provider,
                    )
                return content
            except Exception as e:
                # Prefer structured status code when available (OpenAI/Groq exceptions)
                status_code = getattr(e, "status_code", None)
                if status_code == 429:
                    is_rate_limit = True
                else:
                    error_str = str(e).lower()
                    is_rate_limit = (
                        "rate_limit" in error_str
                        or "rate limit" in error_str
                        or "429" in error_str
                        or "too many requests" in error_str
                    )
                if is_rate_limit and attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    print(f"  [LLM] Rate limit hit, retrying in {delay:.0f}s "
                          f"(attempt {attempt + 1}/{max_retries})...")
                    time.sleep(delay)
                elif is_rate_limit:
                    # Final long wait before giving up
                    wait = Config.RATE_LIMIT_WAIT_SECONDS
                    print(f"  [LLM] Rate limit retries exhausted after {max_retries} attempts. "
                          f"Waiting {wait}s before final attempt...")
                    time.sleep(wait)
                    try:
                        response = self._client.chat.completions.create(
                            model=self._model,
                            messages=[
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": user_message},
                            ],
                            temperature=temperature,
                            max_tokens=Config.LLM_MAX_TOKENS,
                        )
                        content = response.choices[0].message.content
                        if response.usage is not None:
                            self._record_usage(
                                prompt_tokens=response.usage.prompt_tokens,
                                completion_tokens=response.usage.completion_tokens,
                                kind=self.provider,
                            )
                        else:
                            self._record_usage(
                                prompt_tokens=self.estimate_tokens(system_prompt) + self.estimate_tokens(user_message),
                                completion_tokens=self.estimate_tokens(content or ""),
                                kind=self.provider,
                            )
                        return content
                    except Exception:
                        print(f"  [LLM] Final attempt after {wait}s wait also failed. "
                              f"Falling back to deterministic response.")
                        return self.RATE_LIMIT_RESPONSE
                else:
                    raise

    def _chat_mock(self, system_prompt: str, user_message: str) -> str:
        """
        Deterministic mock that produces structured responses for development.
        This is NOT just returning empty strings — it generates contextually
        appropriate responses based on the system prompt keywords.
        """
        prompt_lower = system_prompt.lower()

        if any(w in prompt_lower for w in _DIALOGUE_KEYWORDS):
            response = self._mock_dialogue_response(system_prompt, user_message)
        elif "carbon optimization assistant" in prompt_lower:
            response = self._mock_chat_assistant(user_message)
        elif "explain" in prompt_lower or "rationale" in prompt_lower:
            response = self._mock_explanation(user_message)
        elif "ticket" in prompt_lower or "jira" in prompt_lower or "pr " in prompt_lower:
            response = self._mock_ticket(user_message)
        elif "summarize" in prompt_lower or "summary" in prompt_lower:
            response = self._mock_summary(user_message)
        elif "policy" in prompt_lower or "parse" in prompt_lower:
            response = self._mock_policy_parse(user_message)
        elif "nudge" in prompt_lower or "copilot" in prompt_lower:
            response = self._mock_nudge(user_message)
        elif "risk" in prompt_lower or "assess" in prompt_lower:
            response = self._mock_risk_assessment(user_message)
        else:
            response = f"[Mock LLM] Processed request with {len(user_message)} chars of context."

        # Track estimated token usage for mock calls
        self._record_usage(
            prompt_tokens=self.estimate_tokens(system_prompt) + self.estimate_tokens(user_message),
            completion_tokens=self.estimate_tokens(response),
            kind="mock",
        )
        return response

    def _chat_anthropic(self, system_prompt: str, user_message: str, temperature: float) -> str:
        """Anthropic Messages API call with retry on overload."""
        from config import Config
        max_retries = 5
        base_delay = 2.0
        for attempt in range(max_retries):
            try:
                response = self._client.messages.create(
                    model=self._model,
                    max_tokens=Config.LLM_MAX_TOKENS,
                    temperature=temperature,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_message}],
                )
                # Anthropic returns content as a list of blocks
                content = "".join(
                    block.text for block in response.content if hasattr(block, "text")
                )
                usage = getattr(response, "usage", None)
                if usage is not None:
                    self._record_usage(
                        prompt_tokens=usage.input_tokens,
                        completion_tokens=usage.output_tokens,
                        kind="anthropic",
                    )
                else:
                    self._record_usage(
                        prompt_tokens=self.estimate_tokens(system_prompt) + self.estimate_tokens(user_message),
                        completion_tokens=self.estimate_tokens(content or ""),
                        kind="anthropic",
                    )
                return content
            except Exception as e:
                err = str(e).lower()
                is_retryable = (
                    "rate_limit" in err or "overloaded" in err or "429" in err
                    or "529" in err or "too many requests" in err
                )
                if is_retryable and attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    print(f"  [LLM-anthropic] Retryable error, retrying in {delay:.0f}s "
                          f"(attempt {attempt + 1}/{max_retries})...")
                    time.sleep(delay)
                else:
                    print(f"  [LLM-anthropic] Failed: {e}. Returning rate-limit fallback.")
                    return self.RATE_LIMIT_RESPONSE

    def _mock_dialogue_response(self, system_prompt: str, user_message: str) -> str:
        """Generate a contextual multi-agent dialogue response in mock mode."""
        prompt_lower = system_prompt.lower()
        msg_lower = user_message.lower()

        if "governance" in prompt_lower:
            if "concentration" in msg_lower or "region" in msg_lower:
                return (
                    "I have concerns about the regional concentration in this proposal. "
                    "However, the data shows that eu-north-1 and us-west-2 both have "
                    "significantly lower grid intensity (~50 gCO₂/kWh vs ~400 gCO₂/kWh). "
                    "The carbon savings are real. I can approve this batch if we cap "
                    "the per-region limit to 15 jobs for safety."
                )
            else:
                return (
                    "After reviewing the batch proposal, the risk profile is acceptable. "
                    "The estimated carbon reduction of the batch aligns with policy. "
                    "Cost increases are within the 20% guardrail. I approve this batch "
                    "subject to the standard monitoring requirements."
                )
        elif "planner" in prompt_lower:
            if "challenge" in msg_lower or "concern" in msg_lower or "risk" in msg_lower:
                return (
                    "I understand the governance concerns. The data shows 62% of proposed "
                    "migrations go to eu-north-1. I can revise the batch to distribute "
                    "more evenly: 40% eu-north-1, 35% us-west-2, 25% eu-west-1. "
                    "This reduces concentration risk while preserving 90% of the carbon savings."
                )
            else:
                return (
                    "The batch proposal targets 3 regions with clean grids. "
                    "Estimated aggregate carbon reduction: 45 kgCO₂e over 30 days. "
                    "All recommended jobs are non-urgent batch workloads with flexible "
                    "scheduling windows. No production workloads are included."
                )
        else:
            return (
                "Based on the data presented, the proposal appears sound. "
                "The carbon savings are well-supported by the grid intensity differentials. "
                "I recommend proceeding with the standard safeguards in place."
            )

    def _mock_chat_assistant(self, user_message: str) -> str:
        """Generate a contextual chat response for the interactive assistant page."""
        # When multi-turn context is passed, extract only the current question for keyword matching
        if "current question:" in user_message.lower():
            msg = user_message.lower().split("current question:")[-1].strip()
        else:
            msg = user_message.lower()

        if any(w in msg for w in ["hello", "hi", "hey", "start", "help", "what can"]):
            return (
                "Hi! I'm the sust-AI-naible Carbon Optimization Assistant. "
                "I can help you understand the pipeline results, explain the methodology, "
                "or answer questions about your cloud carbon footprint. "
                "Try asking: *'What drove the most carbon savings?'*, "
                "*'How does verification work?'*, or *'What was the cost impact?'*"
            )
        elif any(w in msg for w in ["emission", "carbon", "footprint", "co2", "kgco"]):
            return (
                "The optimization reduced your cloud emissions by shifting workloads to cleaner "
                "regions and time windows. The biggest lever is region-shifting: moving batch jobs "
                "from high-intensity regions (e.g. us-east-1 at ~415 gCO₂/kWh) to low-intensity "
                "ones (e.g. eu-north-1 at ~8 gCO₂/kWh) can cut per-job emissions by over 90%. "
                "Time-shifting within the same region is lower-impact but zero-cost. "
                "See the **Carbon Analysis** page for a full breakdown by region, team, and workload type."
            )
        elif any(w in msg for w in ["cost", "price", "dollar", "spend", "expensive", "cheap"]):
            return (
                "The optimizations had a minimal net effect on cloud cost. "
                "Time-shifts are cost-neutral (same region, different hour), while region-shifts "
                "may add a small data-transfer charge but often benefit from cheaper spot pricing "
                "in cleaner regions. The **Trade-off Analysis** page shows the full cost-vs-carbon "
                "Pareto frontier at carbon prices from $0 to $200/ton."
            )
        elif any(w in msg for w in ["recommend", "suggestion", "planner", "plan", "shift", "move"]):
            return (
                "The Planner agent scores every eligible job on three dimensions: carbon reduction "
                "potential (gCO₂e saved), cost delta (USD), and SLA risk (urgency + dependencies). "
                "It then generates region-shift or time-shift recommendations for jobs where the "
                "carbon benefit outweighs the risk. Before any change is executed, the Governance "
                "agent must approve the batch — see the **Optimization Results** page for the full "
                "breakdown with approval rates by risk level."
            )
        elif any(w in msg for w in ["verif", "mrv", "evidence", "proof", "confident", "saving", "saved"]):
            return (
                "Verification uses counterfactual reasoning: the Verifier agent models what "
                "emissions *would have been* without the optimization (using the original job "
                "placement + actual grid intensity data), then compares that against observed "
                "post-optimization emissions. Savings are **confirmed** when the 90% confidence "
                "interval excludes zero, **partial** when the point estimate is positive but CI "
                "includes zero, and **refuted** when the observed change went the wrong direction. "
                "See the **Verification (MRV)** and **Evidence Explorer** pages for every record."
            )
        elif any(w in msg for w in ["governance", "approve", "reject", "risk", "policy", "guardrail"]):
            return (
                "The Governance agent enforces organizational policy before any change runs. "
                "It auto-approves low-risk recommendations (batch jobs, small cost impact) and "
                "flags medium/high-risk ones (production workloads, cost increase >20%, "
                "cross-continent moves) for human review. If it challenges a batch, the Planner "
                "can revise and resubmit — the negotiation continues for up to 4 rounds. "
                "See **🤖 The Debate** for the full negotiation transcript."
            )
        elif any(w in msg for w in ["agent", "how does", "how do", "pipeline", "work", "architect", "explain"]):
            return (
                "The pipeline runs 6 stages: **Sense** (Ingestor collects cloud workload data), "
                "**Model** (Carbon Accountant calculates kgCO₂e per job using grid intensity × "
                "resource usage × PUE), **Decide** (Planner generates recommendations → "
                "Governance approves), **Act** (Executor applies changes and raises tickets), "
                "**Verify** (Verifier checks actual savings via counterfactual MRV), "
                "and **Learn** (Developer Copilot awards points and sends team summaries). "
                "The **Agent Reasoning** page shows every LLM reasoning step."
            )
        elif any(w in msg for w in ["team", "leaderboard", "point", "score", "rank", "best", "top"]):
            return (
                "Points are awarded *only* for verified savings — never for estimates. "
                "Confirmed verifications earn 100 pts/kgCO₂e; partial verifications earn 50 pts/kgCO₂e. "
                "SLA violations incur a 50-point penalty per incident. "
                "The **Team Leaderboard** page shows current standings, total kgCO₂e avoided per team, "
                "and the Developer Copilot's personalised summary for each team."
            )
        elif any(w in msg for w in ["region", "us-east", "us-west", "eu-north", "eu-west", "ap-south"]):
            return (
                "Grid carbon intensity varies dramatically by region: eu-north-1 (Stockholm) runs "
                "at ~8 gCO₂/kWh (hydro + nuclear), us-west-2 (Oregon) at ~130 gCO₂/kWh (hydro), "
                "eu-west-1 (Ireland) at ~220 gCO₂/kWh (wind + gas), us-east-1 (Virginia) at "
                "~415 gCO₂/kWh (coal + gas), and ap-south-1 (Mumbai) at ~700 gCO₂/kWh (coal). "
                "The **Carbon Analysis** heatmap shows how intensity varies hour-by-hour within each region."
            )
        elif any(w in msg for w in ["mock", "llm", "openai", "gpt", "api", "key", "real", "groq"]):
            return (
                "The system works fully without an API key \u2014 the mock LLM generates structured, "
                "contextually appropriate responses for all agent tasks. "
                "To use a real LLM, set either `GROQ_API_KEY` (free at console.groq.com) or "
                "`OPENAI_API_KEY` in your `.env` file and re-run "
                "`python run_pipeline.py`. The system auto-detects which key is available. "
                "All *numbers* are computed deterministically regardless of which LLM is used \u2014 "
                "the LLM only explains and communicates, never calculates."
            )
        else:
            return (
                "This system tracks, optimizes, and *verifies* cloud carbon emissions using a "
                "closed-loop multi-agent pipeline. Every number is backed by deterministic "
                "calculations (not LLM estimates), and every claimed saving has a counterfactual "
                "evidence chain. You can ask me about: emissions, costs, recommendations, "
                "verification, the agents, team leaderboard, or the methodology."
            )

    def _mock_explanation(self, context: str) -> str:
        # Parse key details from the context to generate a realistic explanation
        lines = context.split("\n")
        details = {}
        for line in lines:
            if ":" in line:
                key, val = line.split(":", 1)
                details[key.strip().lower()] = val.strip()

        from_region = details.get("current_region", "us-east-1")
        to_region = details.get("proposed_region", "us-west-2")
        carbon = details.get("carbon_delta", "unknown")
        action = details.get("action_type", "region_shift")

        region_names = {
            "us-east-1": "Virginia (coal/gas heavy grid)",
            "us-west-2": "Oregon (hydroelectric)",
            "eu-west-1": "Ireland (wind + gas mix)",
            "eu-north-1": "Stockholm (hydro + nuclear, very clean)",
            "ap-south-1": "Mumbai (coal-heavy)",
        }

        from_name = region_names.get(from_region, from_region)
        to_name = region_names.get(to_region, to_region)

        if "time_shift" in action:
            return (
                f"This workload can be deferred to a time window when the electricity grid "
                f"in {from_name} is running cleaner — typically during off-peak hours when "
                f"renewable energy makes up a larger share of the generation mix. "
                f"The estimated carbon reduction is {carbon}, with zero impact on cloud cost "
                f"since the workload runs in the same region. This is a low-risk optimization "
                f"because it only changes timing, not infrastructure."
            )
        else:
            return (
                f"Moving this workload from {from_name} to {to_name} "
                f"takes advantage of a significantly cleaner electricity grid. "
                f"{to_name} has a carbon intensity roughly "
                f"{'75%' if 'north' in to_region or 'west-2' in to_region else '30%'} "
                f"lower than {from_name}. "
                f"The estimated carbon reduction is {carbon}. "
                f"Data transfer costs are minimal for this workload type, making this "
                f"a high-value, low-risk optimization."
            )

    def _mock_ticket(self, context: str) -> str:
        lines = context.split("\n")
        details = {}
        for line in lines:
            if ":" in line:
                key, val = line.split(":", 1)
                details[key.strip().lower()] = val.strip()

        action = details.get("action_type", "region_shift")
        risk = details.get("risk_level", "low")

        return (
            f"## Sustainability Optimization: {action.replace('_', ' ').title()}\n\n"
            f"### Context\n"
            f"The carbon optimization system identified this workload as a candidate for "
            f"{action.replace('_', ' ')}. This change is estimated to reduce carbon emissions "
            f"while maintaining SLA compliance.\n\n"
            f"### Risk Assessment\n"
            f"Risk level: **{risk.upper()}**. "
            f"{'This change has been auto-approved by the governance system.' if risk == 'low' else 'This change requires team lead approval before execution.'}\n\n"
            f"### Rollback Plan\n"
            f"If any SLA degradation is detected within 24 hours, the change will be "
            f"automatically reverted to the original configuration.\n\n"
            f"### Verification\n"
            f"The Verifier Agent will assess actual carbon savings within 7 days using "
            f"counterfactual analysis. Results will be posted as a comment on this ticket."
        )

    def _mock_summary(self, context: str) -> str:
        lines = context.split("\n")
        # Try to extract numbers from context
        numbers = {}
        for line in lines:
            if ":" in line:
                key, val = line.split(":", 1)
                numbers[key.strip().lower()] = val.strip()

        total_savings = numbers.get("total_savings", "62 kgCO₂e")
        recs = numbers.get("recommendations", "5,478")
        verified = numbers.get("verified", "5,478")

        return (
            f"**Period Summary**: The system processed {recs} optimization opportunities "
            f"this period. After governance review and execution, {verified} changes were "
            f"implemented and verified.\n\n"
            f"**Key Result**: Total verified carbon reduction of {total_savings}, "
            f"achieved through a combination of time-shifting (moving jobs to cleaner grid "
            f"hours) and region-shifting (moving jobs to regions with more renewable energy).\n\n"
            f"**Cost Impact**: Cloud costs decreased slightly, confirming these are "
            f"'zero-regret' optimizations — good for both sustainability and the budget.\n\n"
            f"**Confidence**: 34% of verifications achieved 'confirmed' status (90% CI "
            f"excludes zero), while 66% are 'partial' (positive point estimate but CI "
            f"includes zero due to grid intensity uncertainty). Zero refuted."
        )

    def _mock_policy_parse(self, context: str) -> str:
        return json.dumps({
            "parsed_constraints": [
                {"type": "region_restriction", "rule": "production workloads must stay on same continent"},
                {"type": "deferral_limit", "rule": "urgent jobs cannot be deferred"},
                {"type": "cost_guardrail", "rule": "no recommendation may increase cost by more than 20%"},
                {"type": "approval_required", "rule": "high-risk changes need team lead sign-off"},
            ],
            "confidence": 0.85,
            "ambiguities": ["Definition of 'production workload' may need clarification"],
        }, indent=2)

    def _mock_nudge(self, context: str) -> str:
        lines = context.split("\n")
        details = {}
        for line in lines:
            if ":" in line:
                key, val = line.split(":", 1)
                details[key.strip().lower()] = val.strip()

        team = details.get("team_id", "your team")
        return (
            f"Hey {team} — quick sustainability update: your CI/CD jobs in us-east-1 "
            f"could run ~60% cleaner by shifting to off-peak hours (2am-6am UTC). "
            f"Since they're batch jobs, this wouldn't affect your workflow at all. "
            f"Want the system to auto-optimize these going forward? "
            f"Last month, teams that opted in saved an average of 2.3 kgCO₂e."
        )

    def _mock_risk_assessment(self, context: str) -> str:
        return (
            "Risk assessment: This recommendation involves shifting a non-critical batch "
            "workload to a different time window within the same region. The workload is "
            "categorized as 'sustainable' (flexible scheduling), has no downstream dependencies "
            "within the deferral window, and the target time slot has historically clean grid "
            "intensity. Assessed risk: LOW. Recommendation: auto-approve."
        )


# ── Tool Definition ───────────────────────────────────────────────────

@dataclass
class Tool:
    """A tool an agent can call."""
    name: str
    description: str
    function: Callable
    requires_approval: bool = False


# ── Agent Memory ──────────────────────────────────────────────────────

@dataclass
class AgentMemory:
    """Working memory for an agent — tracks reasoning, actions, and context."""
    reasoning_trace: list = field(default_factory=list)  # LLM reasoning steps
    actions_taken: list = field(default_factory=list)     # tool calls and results
    context: dict = field(default_factory=dict)           # shared context from orchestrator

    def add_reasoning(self, step: str, content: str):
        self.reasoning_trace.append({
            "step": step,
            "content": content,
            "timestamp": datetime.now().isoformat(),
        })

    def add_action(self, tool_name: str, inputs: dict, output: Any):
        self.actions_taken.append({
            "tool": tool_name,
            "inputs": inputs,
            "output": str(output)[:500],  # Truncate for memory efficiency
            "timestamp": datetime.now().isoformat(),
        })

    def to_dict(self) -> dict:
        return {
            "reasoning_trace": self.reasoning_trace,
            "actions_taken": self.actions_taken,
            "context_keys": list(self.context.keys()),
        }


# ── Base Agent ────────────────────────────────────────────────────────

class BaseAgent(ABC):
    """
    Base class for all agents in the sust-AI-naible system.
    
    Every agent has:
      - A name and purpose
      - An LLM for reasoning
      - A set of tools it can call
      - Working memory (reasoning trace + action log)
      - Explicit permissions (what it CAN and CANNOT do)
    """

    def __init__(
        self,
        name: str,
        purpose: str,
        llm: Optional[LLMProvider] = None,
        permissions: Optional[list[str]] = None,
        restrictions: Optional[list[str]] = None,
    ):
        self.name = name
        self.purpose = purpose
        self.llm = llm or LLMProvider("auto")
        self.permissions = permissions or []
        self.restrictions = restrictions or []
        self.tools: dict[str, Tool] = {}
        self.memory = AgentMemory()

        # Register tools defined by subclass
        self._register_tools()

    @abstractmethod
    def _register_tools(self):
        """Subclasses register their available tools here."""
        pass

    @abstractmethod
    def run(self, task: dict) -> dict:
        """
        Execute the agent's main task.
        
        Args:
            task: Dict with task-specific inputs and context
        
        Returns:
            Dict with results, reasoning trace, and any outputs
        """
        pass

    def add_tool(self, name: str, description: str, function: Callable, requires_approval: bool = False):
        """Register a tool this agent can use."""
        self.tools[name] = Tool(name, description, function, requires_approval)

    def call_tool(self, tool_name: str, **kwargs) -> Any:
        """Call a registered tool and log the action."""
        if tool_name not in self.tools:
            raise ValueError(f"Agent '{self.name}' does not have tool '{tool_name}'")

        tool = self.tools[tool_name]
        result = tool.function(**kwargs)
        self.memory.add_action(tool_name, kwargs, result)
        return result

    def reason(self, system_prompt: str, context: str) -> str:
        """Use the LLM to reason about a task."""
        response = self.llm.chat(system_prompt, context)
        self.memory.add_reasoning("llm_reasoning", response)
        return response

    def get_system_prompt(self) -> str:
        """Build the agent's system prompt from its identity."""
        return (
            f"You are {self.name}, an AI agent in the sust-AI-naible carbon optimization system.\n"
            f"Your purpose: {self.purpose}\n\n"
            f"Permissions: {', '.join(self.permissions) if self.permissions else 'None specified'}\n"
            f"Restrictions: {', '.join(self.restrictions) if self.restrictions else 'None specified'}\n\n"
            f"Available tools: {', '.join(self.tools.keys()) if self.tools else 'None'}\n\n"
            f"Be precise, quantitative, and honest about uncertainty. "
            f"Never claim savings without evidence. Never round numbers to look better."
        )

    def get_trace(self) -> dict:
        """Return the full reasoning + action trace for audit."""
        return {
            "agent": self.name,
            "purpose": self.purpose,
            "memory": self.memory.to_dict(),
        }

    def respond_to(self, message, dialogue) -> "AgentMessage":
        """
        Given another agent's message and the full dialogue context,
        generate a response using LLM reasoning.

        Args:
            message: AgentMessage from another agent
            dialogue: Dialogue object with full conversation context

        Returns:
            AgentMessage with LLM-generated response
        """
        AgentMessage, Dialogue, MessageType = _get_protocol()

        dialogue_context = dialogue.get_full_context(max_messages=30)

        system_prompt = (
            f"{self.get_system_prompt()}\n\n"
            f"You are participating in a multi-agent planning discussion.\n"
            f"Review the dialogue below and respond from YOUR perspective.\n"
            f"You MUST reference specific numbers from the data.\n"
            f"If you disagree, explain WHY with evidence.\n"
            f"If you agree, state what specific conditions make this acceptable.\n"
            f"Keep responses under 150 words. Be direct."
        )

        user_prompt = (
            f"DIALOGUE SO FAR:\n{dialogue_context}\n\n"
            f"LATEST MESSAGE (from {message.from_agent}):\n"
            f"{message.content}\n\n"
            f"DATA:\n{json.dumps(message.structured_data, indent=2, default=str)}\n\n"
            f"Respond as {self.name}. What is your assessment?"
        )

        response_text = self.llm.chat(system_prompt, user_prompt)
        self.memory.add_reasoning("dialogue_response", response_text)

        return AgentMessage(
            from_agent=self.name,
            to_agent=message.from_agent,
            message_type=self._determine_response_type(response_text),
            subject=message.subject,
            content=response_text,
            in_reply_to=message.message_id,
            round_number=message.round_number + 1,
        )

    def _determine_response_type(self, response_text: str):
        """Classify an LLM response into a MessageType based on keywords."""
        _, _, MessageType = _get_protocol()
        lower = response_text.lower()
        if any(w in lower for w in ["approve", "agreed", "acceptable", "looks good"]):
            return MessageType.APPROVAL
        elif any(w in lower for w in ["reject", "cannot accept", "too risky", "unacceptable"]):
            return MessageType.REJECTION
        elif any(w in lower for w in ["however", "concern", "risk", "but what about", "disagree"]):
            return MessageType.CHALLENGE
        elif any(w in lower for w in ["revised", "updated", "alternative", "instead"]):
            return MessageType.REVISION
        elif any(w in lower for w in ["data shows", "note that", "for context"]):
            return MessageType.DATA_INSIGHT
        else:
            return MessageType.PROPOSAL
