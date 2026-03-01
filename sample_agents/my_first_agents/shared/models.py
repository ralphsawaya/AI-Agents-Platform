"""Shared data models used across agents."""

from dataclasses import dataclass


@dataclass
class TaskInput:
    text: str
    metadata: dict | None = None


@dataclass
class SummaryOutput:
    summary: str
    word_count: int


@dataclass
class ReportOutput:
    report: str
    title: str
