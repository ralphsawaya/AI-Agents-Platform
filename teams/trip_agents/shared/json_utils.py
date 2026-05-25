"""Brace-aware JSON extraction from LLM output."""

import json


def extract_json(text: str) -> dict:
    """Extract the first complete JSON object from text."""
    text = text.strip()
    start = text.find("{")
    if start == -1:
        return {}
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\" and in_string:
            escape = True
            continue
        if ch == '"' and not escape:
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    parsed = json.loads(text[start:i + 1])
                    return parsed if isinstance(parsed, dict) else {}
                except json.JSONDecodeError:
                    return {}
    return {}


def extract_json_array(text: str) -> list:
    """Extract the first complete JSON array from text."""
    text = text.strip()
    start = text.find("[")
    if start == -1:
        return []
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\" and in_string:
            escape = True
            continue
        if ch == '"' and not escape:
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                try:
                    parsed = json.loads(text[start:i + 1])
                    return parsed if isinstance(parsed, list) else []
                except json.JSONDecodeError:
                    return []
    return []


# Backward-compatible aliases
_extract_json = extract_json
_extract_json_array = extract_json_array
