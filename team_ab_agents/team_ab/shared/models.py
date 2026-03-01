"""Shared data models used across TeamAB agents."""

from dataclasses import dataclass


@dataclass
class TextInput:
    text: str
    metadata: dict | None = None


@dataclass
class SummaryOutput:
    text_id: int
    initial_text: str
    summary_text: str


@dataclass
class TitleOutput:
    text_id: int
    title: str
