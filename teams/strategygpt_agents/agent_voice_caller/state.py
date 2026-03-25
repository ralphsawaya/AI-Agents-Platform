"""TypedDict state schema for the Voice Caller agent."""

from typing import TypedDict


class VoiceCallerState(TypedDict):
    batch_size: int
    leads_to_call: list[dict]
    call_results: list[dict]
    interested_count: int
    not_interested_count: int
    no_answer_count: int
    status: str
