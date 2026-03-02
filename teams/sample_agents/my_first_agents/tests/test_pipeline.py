"""Basic tests for the agent pipeline."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_shared_utils():
    from shared.utils import word_count
    assert word_count("hello world") == 2
    assert word_count("") == 1  # "".split() gives ['']


def test_alpha_state():
    from agent_alpha.state import AlphaState
    state: AlphaState = {
        "input_text": "test",
        "summary": "",
        "word_count": 0,
        "status": "pending",
    }
    assert state["status"] == "pending"


def test_beta_state():
    from agent_beta.state import BetaState
    state: BetaState = {
        "summary": "test summary",
        "report": "",
        "title": "",
        "status": "pending",
    }
    assert state["summary"] == "test summary"


if __name__ == "__main__":
    test_shared_utils()
    test_alpha_state()
    test_beta_state()
    print("All tests passed.")
