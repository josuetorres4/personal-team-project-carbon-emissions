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
    Wrapper for LLM calls. Supports OpenAI API or falls back to a
    local mock for development/testing without API keys.
    """

    def __init__(self, provider: str = "auto"):
        """
        Args:
            provider: "openai", "mock", or "auto" (try openai, fall back to mock)
        """
        self.provider = provider
        self._client = None
        self._model = "gpt-4o-mini"
        if provider == "auto":
            if os.environ.get("OPENAI_API_KEY"):
                self.provider = "openai"
            else:
                self.provider = "mock"

        if self.provider == "openai":
            try:
                from openai import OpenAI
                self._client = OpenAI()
            except Exception:
                print("  [LLM] OpenAI not available, falling back to mock")
                self.provider = "mock"

    def chat(self, system_prompt: str, user_message: str, temperature: float = 0.3) -> str:
        """Send a chat completion request."""
        if self.provider == "openai":
            return self._chat_openai(system_prompt, user_message, temperature)
        else:
            return self._chat_mock(system_prompt, user_message)

    def _chat_openai(self, system_prompt: str, user_message: str, temperature: float) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=temperature,
            max_tokens=1024,
        )
        return response.choices[0].message.content

    def _chat_mock(self, system_prompt: str, user_message: str) -> str:
        """
        Deterministic mock that produces structured responses for development.
        This is NOT just returning empty strings — it generates contextually
        appropriate responses based on the system prompt keywords.
        """
        prompt_lower = system_prompt.lower()

        if any(w in prompt_lower for w in _DIALOGUE_KEYWORDS):
            return self._mock_dialogue_response(system_prompt, user_message)
        elif "explain" in prompt_lower or "rationale" in prompt_lower:
            return self._mock_explanation(user_message)
        elif "ticket" in prompt_lower or "jira" in prompt_lower or "pr " in prompt_lower:
            return self._mock_ticket(user_message)
        elif "summarize" in prompt_lower or "summary" in prompt_lower:
            return self._mock_summary(user_message)
        elif "policy" in prompt_lower or "parse" in prompt_lower:
            return self._mock_policy_parse(user_message)
        elif "nudge" in prompt_lower or "copilot" in prompt_lower:
            return self._mock_nudge(user_message)
        elif "risk" in prompt_lower or "assess" in prompt_lower:
            return self._mock_risk_assessment(user_message)
        else:
            return f"[Mock LLM] Processed request with {len(user_message)} chars of context."

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
