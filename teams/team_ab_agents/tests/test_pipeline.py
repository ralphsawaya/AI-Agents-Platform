"""Basic tests for the TeamAB agent pipeline."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_shared_utils():
    from shared.utils import word_count
    assert word_count("hello world") == 2
    assert word_count("one two three four five") == 5


def test_agent_a_state():
    from agent_a.state import AgentAState
    state: AgentAState = {
        "input_text": "test",
        "summary": "",
        "text_id": 0,
        "word_count": 0,
        "status": "pending",
    }
    assert state["status"] == "pending"


def test_agent_b_state():
    from agent_b.state import AgentBState
    state: AgentBState = {
        "summary": "test summary",
        "title": "",
        "text_id": 0,
        "status": "pending",
    }
    assert state["summary"] == "test summary"


def test_input_validation():
    from agent_a.nodes.input_node import input_node
    result = input_node({"input_text": "", "word_count": 0, "status": "pending"})
    assert result["status"] == "error"

    result = input_node({
        "input_text": "Hello world test",
        "word_count": 0,
        "status": "pending",
    })
    assert result["status"] == "processing"
    assert result["word_count"] == 3


if __name__ == "__main__":
    test_shared_utils()
    test_agent_a_state()
    test_agent_b_state()
    test_input_validation()
    print("All tests passed.")
