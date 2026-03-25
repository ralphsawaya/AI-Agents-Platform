"""Shared data models used across StrategyGPT agents."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Lead:
    place_id: str
    business_name: str
    phone: str
    address: str
    category: str
    review_count: int
    rating: float
    city: str
    status: str = "new"
    call_script: str = ""
    business_hours: dict | None = None
    created_at: datetime | None = None


@dataclass
class CallOutcome:
    lead_place_id: str
    call_id: str
    outcome: str  # interested, not_interested, voicemail, callback_requested, no_answer
    duration_seconds: float = 0.0
    transcript_summary: str = ""
    called_at: datetime | None = None
