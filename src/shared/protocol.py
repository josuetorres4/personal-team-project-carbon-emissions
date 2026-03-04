"""
Agent Communication Protocol
==============================
Message-passing protocol that enables multi-agent dialogue.

Agents exchange typed messages (proposals, challenges, revisions, etc.)
through structured AgentMessage objects. Dialogue tracks all rounds
and provides full audit trails.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Any
import uuid
import json


class MessageType(Enum):
    PROPOSAL = "proposal"
    CHALLENGE = "challenge"
    REVISION = "revision"
    DATA_INSIGHT = "data_insight"
    APPROVAL = "approval"
    REJECTION = "rejection"
    CONSENSUS = "consensus"
    ESCALATION = "escalation"


@dataclass
class AgentMessage:
    """A single message in the agent dialogue."""
    message_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    from_agent: str = ""
    to_agent: str = "all"
    message_type: MessageType = MessageType.PROPOSAL
    subject: str = ""
    content: str = ""  # LLM-generated reasoning text
    structured_data: dict = field(default_factory=dict)
    in_reply_to: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    round_number: int = 0

    def to_context_string(self) -> str:
        return (
            f"[{self.from_agent}] ({self.message_type.value}) "
            f"Round {self.round_number}: {self.content}"
        )


@dataclass
class DialogueRound:
    round_number: int = 0
    messages: list = field(default_factory=list)
    consensus_reached: bool = False


@dataclass
class Dialogue:
    dialogue_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    topic: str = ""
    rounds: list = field(default_factory=list)
    participating_agents: list = field(default_factory=list)
    max_rounds: int = 5
    outcome: str = ""
    final_plan: dict = field(default_factory=dict)

    @property
    def all_messages(self) -> list:
        msgs = []
        for r in self.rounds:
            msgs.extend(r.messages)
        return msgs

    @property
    def total_rounds(self) -> int:
        return len(self.rounds)

    def get_full_context(self, max_messages: int = 50) -> str:
        all_msgs = self.all_messages[-max_messages:]
        return "\n\n".join(m.to_context_string() for m in all_msgs)

    def add_message(self, message: AgentMessage):
        if not self.rounds or self.rounds[-1].round_number != message.round_number:
            self.rounds.append(DialogueRound(round_number=message.round_number))
        self.rounds[-1].messages.append(message)

    def to_audit_record(self) -> dict:
        return {
            "dialogue_id": self.dialogue_id,
            "topic": self.topic,
            "participating_agents": self.participating_agents,
            "total_rounds": self.total_rounds,
            "total_messages": len(self.all_messages),
            "outcome": self.outcome,
            "messages": [
                {
                    "message_id": m.message_id,
                    "from": m.from_agent,
                    "to": m.to_agent,
                    "type": m.message_type.value,
                    "content": m.content,
                    "data": m.structured_data,
                    "round": m.round_number,
                    "timestamp": m.timestamp.isoformat(),
                }
                for m in self.all_messages
            ],
        }
