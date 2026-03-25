"""Basic smoke tests for the StrategyGPT pipeline."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_shared_imports():
    """Verify shared modules import without errors."""
    from shared.config import GOOGLE_MAPS_API_KEY, VOICE_API_KEY, LLM_PROVIDER
    from shared.logger import get_logger
    from shared.utils import load_args, parse_categories, format_phone_us
    from shared.models import Lead, CallOutcome

    assert LLM_PROVIDER is not None
    logger = get_logger("test")
    assert logger is not None


def test_parse_categories():
    from shared.utils import parse_categories

    assert parse_categories("restaurant, plumber, dentist") == ["restaurant", "plumber", "dentist"]
    assert parse_categories("") == []
    assert parse_categories("salon") == ["salon"]


def test_format_phone_us():
    from shared.utils import format_phone_us

    assert format_phone_us("(512) 555-1234") == "+15125551234"
    assert format_phone_us("512-555-1234") == "+15125551234"
    assert format_phone_us("15125551234") == "+15125551234"
    assert format_phone_us("+15125551234") == "+15125551234"
    assert format_phone_us("123") == ""


def test_agent_graphs_build():
    """Verify that all agent graphs compile without errors."""
    from agent_lead_sourcer.agent import build_lead_sourcer_graph
    from agent_lead_qualifier.agent import build_lead_qualifier_graph
    from agent_voice_caller.agent import build_voice_caller_graph

    g1 = build_lead_sourcer_graph()
    g2 = build_lead_qualifier_graph()
    g3 = build_voice_caller_graph()

    assert g1 is not None
    assert g2 is not None
    assert g3 is not None


def test_orchestrator_graphs_build():
    """Verify that orchestrator graphs compile without errors."""
    from orchestrator.graph import build_sourcing_graph, build_outreach_graph, build_full_graph

    g1 = build_sourcing_graph()
    g2 = build_outreach_graph()
    g3 = build_full_graph()

    assert g1 is not None
    assert g2 is not None
    assert g3 is not None


def test_voice_tools_dispatcher():
    """Verify the voice tools dispatcher recognises all providers."""
    from agent_voice_caller.tools.voice_tools import _PROVIDERS

    assert "bland" in _PROVIDERS
    assert "vapi" in _PROVIDERS
    assert "twilio" in _PROVIDERS


if __name__ == "__main__":
    test_shared_imports()
    test_parse_categories()
    test_format_phone_us()
    test_agent_graphs_build()
    test_orchestrator_graphs_build()
    test_voice_tools_dispatcher()
    print("All tests passed.")
