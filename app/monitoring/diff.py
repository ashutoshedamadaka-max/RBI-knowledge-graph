import re

from app.models.monitoring import StructuredDiff


def normalize_regulatory_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def deterministic_diff(previous: str, current: str) -> StructuredDiff:
    old_lines = {line.strip() for line in previous.splitlines() if line.strip()}
    new_lines = {line.strip() for line in current.splitlines() if line.strip()}
    added = sorted(new_lines - old_lines)
    removed = sorted(old_lines - new_lines)
    old_numbers = set(re.findall(r"\b\d+(?:\.\d+)?%?\b", previous))
    new_numbers = set(re.findall(r"\b\d+(?:\.\d+)?%?\b", current))
    old_dates = set(re.findall(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|\b\w+ \d{1,2},? \d{4}\b", previous))
    new_dates = set(re.findall(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|\b\w+ \d{1,2},? \d{4}\b", current))
    return StructuredDiff(
        added=added,
        removed=removed,
        changed_numbers=sorted(old_numbers ^ new_numbers),
        changed_dates=sorted(old_dates ^ new_dates),
    )
