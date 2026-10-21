"""Find and normalise the reference numbers RBI prints on its documents.

RBI circulars carry two numbers, for example ``RBI/2025-26/36`` and the department
reference ``DOR.STR.REC.19/21.07.001/2025-26``. Other documents cite them with
inconsistent spacing and an optional ``No.`` (``DOR.CRE.REC .66/...``,
``DOR.CRE.REC.No.13/...``), so every number is reduced to one comparable key.

Department references are found by their unambiguous tail (``/file-code/year``)
and only then by looking a short, fixed distance back for the department prefix.
This keeps scanning linear in the length of the document.
"""

from dataclasses import dataclass
from datetime import date, datetime
import re

RBI_NUMBER = re.compile(r"\bRBI\s*/\s*(?:([A-Z]{2,6})\s*/\s*)?(\d{4}-(?:\d{4}|\d{2}))\s*/\s*(\d+)\b")
_DEPARTMENT_TAIL = re.compile(r"\s*/\s*(\d{2}[.-]\d{2}[.-]\d{2,3}(?:[.-]\d{1,3})?)\s*/\s*(\d{4}-(?:\d{4}|\d{2}))\b")
_PREFIX_START = re.compile(r"(?:[A-Z]{2,6}|Do[A-Z])(?=[.(\s])")
_PREFIX_BODY = re.compile(r"[A-Za-z0-9.()&\s/-]*(?:S-?)?\d+")
_PREFIX_WINDOW = 45
FEMA_NOTIFICATION = re.compile(r"\bNotification\s+No\.\s*(FEMA\s*[\w()]+/\d{4}-RB)\b")
AP_DIR_CIRCULAR = re.compile(r"\bA\.P\.\s*\(DIR Series\)\s*Circular\s*No\.\s*(\d+)\b", re.IGNORECASE)

_MONTH_DATE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+(\d{1,2}),?\s+(\d{4})\b"
)
_NUMERIC_DATE = re.compile(r"\b(\d{2})[./](\d{2})[./](\d{4})\b")


@dataclass(frozen=True)
class Reference:
    """One printed reference number, as written and as a comparable key."""

    text: str
    key: str
    kind: str  # "rbi", "department", "fema_notification" or "ap_dir_circular"
    start: int
    end: int

    @property
    def department(self) -> str | None:
        if self.kind == "department":
            return re.match(r"[A-Za-z]+", self.key).group(0).upper()
        if self.kind == "rbi":
            infix = re.match(r"RBI/([A-Z]+)/", self.key)
            return infix.group(1) if infix else None
        return "FED" if self.kind in {"fema_notification", "ap_dir_circular"} else None


def short_year(value: str) -> str:
    """RBI writes financial years as 2024-25 or 2024-2025; keys use 2024-25."""
    return re.sub(r"\b(\d{4})-\d{2}(\d{2})\b", r"\1-\2", value)


def normalise_department_reference(value: str) -> str:
    """``DOR.CRE.REC .No. 66 / 21.07.001 / 2022-23`` -> ``DOR.CRE.REC.66/21.07.001/2022-23``."""
    # A "No." segment may follow a dot, a bracket or a space ("RPCD No.Plan.BC92").
    without_no = re.sub(r"[.\s]*\bNo\.\s*", ".", value, flags=re.IGNORECASE)
    compact = re.sub(r"\s+", "", without_no).upper()
    return short_year(re.sub(r"\.{2,}", ".", compact))


def find_references(text: str) -> list[Reference]:
    """All reference numbers in reading order; overlapping finds keep the first."""
    found: list[Reference] = []
    for match in RBI_NUMBER.finditer(text):
        department, year, serial = match.groups()
        year = short_year(year)
        key = f"RBI/{department}/{year}/{serial}" if department else f"RBI/{year}/{serial}"
        found.append(Reference(match.group(0), key, "rbi", match.start(), match.end()))
    for tail in _DEPARTMENT_TAIL.finditer(text):
        prefix_start = _department_prefix_start(text, tail.start())
        if prefix_start is None:
            continue
        raw = text[prefix_start:tail.end()]
        found.append(Reference(raw, normalise_department_reference(raw), "department", prefix_start, tail.end()))
    for match in FEMA_NOTIFICATION.finditer(text):
        key = re.sub(r"\s+", " ", match.group(1)).upper()
        found.append(Reference(match.group(0), key, "fema_notification", match.start(), match.end()))
    for match in AP_DIR_CIRCULAR.finditer(text):
        found.append(Reference(match.group(0), f"A.P. (DIR SERIES) CIRCULAR NO. {match.group(1)}",
                               "ap_dir_circular", match.start(), match.end()))
    found.sort(key=lambda item: item.start)
    unique: list[Reference] = []
    for reference in found:
        if not unique or reference.start >= unique[-1].end:
            unique.append(reference)
    return unique


def _department_prefix_start(text: str, tail_start: int) -> int | None:
    """Leftmost plausible department code within a short window before the file code."""
    window_start = max(0, tail_start - _PREFIX_WINDOW)
    window = text[window_start:tail_start]
    for start in _PREFIX_START.finditer(window):
        candidate = window[start.start():]
        if "\n" in candidate.rstrip():
            continue
        if not _PREFIX_BODY.fullmatch(candidate):
            continue
        # Codes use short title-case segments (DoS, Leg, Plan, No); a lowercase-initial
        # or longer word ("circular", "Master") means the code starts later.
        words = re.findall(r"[A-Za-z]*[a-z][A-Za-z]*", candidate)
        if all(word[0].isupper() and len(word) <= 4 for word in words):
            return window_start + start.start()
    return None


def parse_date(value: str) -> date | None:
    """First date in ``May 8, 2025`` or ``24.06.2020`` (day first) form."""
    month = _MONTH_DATE.search(value)
    if month:
        return datetime.strptime(f"{month.group(1)} {month.group(2)} {month.group(3)}", "%B %d %Y").date()
    numeric = _NUMERIC_DATE.search(value)
    if numeric:
        day, month_number, year = map(int, numeric.groups())
        try:
            return date(year, month_number, day)
        except ValueError:
            return None
    return None
