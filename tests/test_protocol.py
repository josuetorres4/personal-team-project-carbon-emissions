"""
Tests for src/shared/protocol.py

Covers AgentMessage creation, Dialogue message tracking,
context window generation, and audit record export.
"""

import pytest
from src.shared.protocol import (
    AgentMessage,
    Dialogue,
    DialogueRound,
    MessageType,
)


class TestAgentMessage:
    def test_default_creation(self):
        msg = AgentMessage()
        assert msg.message_id
        assert len(msg.message_id) == 12
        assert msg.from_agent == ""
        assert msg.to_agent == "all"
        assert msg.message_type == MessageType.PROPOSAL
        assert msg.round_number == 0

    def test_custom_fields(self):
        msg = AgentMessage(
            from_agent="Planner Agent",
            to_agent="Governance Agent",
            message_type=MessageType.CHALLENGE,
            subject="Batch Review",
            content="This batch has 3 regions",
            structured_data={"count": 10},
            round_number=2,
        )
        assert msg.from_agent == "Planner Agent"
        assert msg.message_type == MessageType.CHALLENGE
        assert msg.structured_data["count"] == 10
        assert msg.round_number == 2

    def test_to_context_string(self):
        msg = AgentMessage(
            from_agent="Planner Agent",
            message_type=MessageType.PROPOSAL,
            content="I propose moving 5 jobs to eu-north-1",
            round_number=0,
        )
        ctx = msg.to_context_string()
        assert "Planner Agent" in ctx
        assert "proposal" in ctx
        assert "Round 0" in ctx
        assert "eu-north-1" in ctx

    def test_unique_ids(self):
        ids = {AgentMessage().message_id for _ in range(100)}
        assert len(ids) == 100


class TestDialogue:
    def _make_dialogue(self):
        d = Dialogue(
            topic="Test Negotiation",
            participating_agents=["Planner Agent", "Governance Agent"],
        )
        return d

    def test_empty_dialogue(self):
        d = self._make_dialogue()
        assert d.total_rounds == 0
        assert d.all_messages == []
        assert d.get_full_context() == ""

    def test_add_message_creates_rounds(self):
        d = self._make_dialogue()
        msg0 = AgentMessage(from_agent="Planner Agent", round_number=0, content="Hello")
        msg1 = AgentMessage(from_agent="Governance Agent", round_number=1, content="World")
        d.add_message(msg0)
        d.add_message(msg1)
        assert d.total_rounds == 2
        assert len(d.all_messages) == 2

    def test_messages_same_round_grouped(self):
        d = self._make_dialogue()
        msg_a = AgentMessage(from_agent="A", round_number=0, content="a")
        msg_b = AgentMessage(from_agent="B", round_number=0, content="b")
        d.add_message(msg_a)
        d.add_message(msg_b)
        assert d.total_rounds == 1
        assert len(d.rounds[0].messages) == 2

    def test_get_full_context(self):
        d = self._make_dialogue()
        d.add_message(AgentMessage(
            from_agent="Planner Agent",
            message_type=MessageType.PROPOSAL,
            content="Proposal content",
            round_number=0,
        ))
        d.add_message(AgentMessage(
            from_agent="Governance Agent",
            message_type=MessageType.CHALLENGE,
            content="Challenge content",
            round_number=1,
        ))
        ctx = d.get_full_context()
        assert "Planner Agent" in ctx
        assert "Governance Agent" in ctx
        assert "Proposal content" in ctx
        assert "Challenge content" in ctx

    def test_get_full_context_max_messages(self):
        d = self._make_dialogue()
        for i in range(20):
            d.add_message(AgentMessage(from_agent="A", content=f"msg{i}", round_number=i))
        ctx = d.get_full_context(max_messages=5)
        # Should only contain last 5 messages (15-19)
        assert "msg19" in ctx
        assert "msg15" in ctx
        assert "msg0" not in ctx
        assert "msg14" not in ctx

    def test_to_audit_record(self):
        d = self._make_dialogue()
        d.add_message(AgentMessage(
            from_agent="Planner Agent",
            to_agent="Governance Agent",
            message_type=MessageType.PROPOSAL,
            subject="Test",
            content="Test content",
            structured_data={"key": "val"},
            round_number=0,
        ))
        d.outcome = "consensus"

        record = d.to_audit_record()
        assert "dialogue_id" in record
        assert record["topic"] == "Test Negotiation"
        assert record["total_rounds"] == 1
        assert record["total_messages"] == 1
        assert record["outcome"] == "consensus"
        assert len(record["messages"]) == 1

        m = record["messages"][0]
        assert m["from"] == "Planner Agent"
        assert m["to"] == "Governance Agent"
        assert m["type"] == "proposal"
        assert m["content"] == "Test content"
        assert m["data"] == {"key": "val"}
        assert "timestamp" in m

    def test_unique_dialogue_ids(self):
        ids = {Dialogue().dialogue_id for _ in range(50)}
        assert len(ids) == 50


class TestMessageType:
    def test_all_values(self):
        expected = {
            "proposal", "challenge", "revision", "data_insight",
            "approval", "rejection", "consensus", "escalation",
        }
        actual = {mt.value for mt in MessageType}
        assert actual == expected
