"""Dependency-free oracle for deadline parsing and expired-rung disposition."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


FIXTURES = Path(__file__).resolve().parents[2] / "tests/evals/fixtures/deadline_parser_boundary_contract.json"
MONTHS = {name: i for i, names in enumerate((
    (), ("jan", "january"), ("feb", "february"), ("mar", "march"),
    ("apr", "april"), ("may",), ("jun", "june"), ("jul", "july"),
    ("aug", "august"), ("sep", "sept", "september"), ("oct", "october"),
    ("nov", "november"), ("dec", "december"),
)) for name in names}
MONTH = r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
EXPLICIT = re.compile(rf"\b({MONTH})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s*(20\d{{2}}))?\b", re.I)
MONTH_YEAR = re.compile(rf"\b({MONTH})\.?\s+(20\d{{2}})\b", re.I)
BARE_MONTH = re.compile(rf"\b({MONTH})\b\.?(?!\s*,?\s*\d)", re.I)
BARE_YEAR = re.compile(r"\b(20\d{2})\b")
PREFIX = re.compile(r"(?:^|[\s(\[,–—-])(before|by|prior\s+to|earlier\s+than|no\s+later\s+than|on\s+or\s+before|through|thru|until|til|till)\s+(?:the\s+)?$", re.I)
EXCLUSIVE = {"before", "prior to", "earlier than"}


def _aware(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("naive_now")
    return dt.astimezone(timezone.utc)


def _context(label: str, match: re.Match) -> bool | None:
    prefix = PREFIX.search(label[:match.start()])
    if prefix:
        word = re.sub(r"\s+", " ", prefix.group(1).lower())
        if word == "before" and re.search(r"\bnot\s+before\s*$", label[:match.start()], re.I):
            return None
        return word in EXCLUSIVE
    if match.group(0).strip().rstrip(".") == label.strip().rstrip("."):
        return False
    return None


def _month_end(year: int, month: int, exclusive: bool) -> datetime:
    if exclusive:
        return datetime(year, month, 1, tzinfo=timezone.utc) - timedelta(seconds=1)
    if month == 12:
        return datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
    return datetime(year, month + 1, 1, tzinfo=timezone.utc) - timedelta(seconds=1)


def parse_deadline(label: str, now: datetime) -> tuple[datetime, bool] | None:
    """Parse only a whole-label date or one introduced by an unambiguous deadline prefix."""
    for pattern, kind in ((EXPLICIT, "day"), (MONTH_YEAR, "month_year"), (BARE_MONTH, "month"), (BARE_YEAR, "year")):
        chosen = None
        for match in pattern.finditer(label):
            exclusive = _context(label, match)
            if exclusive is not None:
                chosen = (match, exclusive)
        if chosen is None:
            continue
        match, exclusive = chosen
        if kind == "day":
            year = int(match.group(3)) if match.group(3) else now.year
            return datetime(year, MONTHS[match.group(1).lower().rstrip(".")], int(match.group(2)), 23, 59, 59, tzinfo=timezone.utc), bool(match.group(3))
        if kind == "month_year":
            return _month_end(int(match.group(2)), MONTHS[match.group(1).lower().rstrip(".")], exclusive), True
        if kind == "month":
            return _month_end(now.year, MONTHS[match.group(1).lower().rstrip(".")], exclusive), False
        year = int(match.group(1)) - (1 if exclusive else 0)
        return datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc), True
    return None


def decide(case: dict[str, Any]) -> dict[str, Any]:
    if case["kind"] == "parity":
        same = case["diagnostic_action"] == case["serving_action"]
        return {"verdict": "shared" if same else "drifted", "reason": "same_authority" if same else "diagnostic_serving_mismatch"}
    try:
        now = _aware(case["now"])
        parsed = parse_deadline(case["label"], now)
    except (TypeError, ValueError):
        return {"verdict": "refuse", "reason": "invalid_input"}
    if parsed is None:
        return {"verdict": "keep", "reason": "no_authoritative_deadline"}
    deadline, explicit_year = parsed
    expired = now > deadline + timedelta(days=case.get("grace_days", 1))
    if not explicit_year and expired and now - deadline > timedelta(days=180):
        expired = False
    if not expired:
        return {"verdict": "keep", "reason": "deadline_live"}
    probability = case.get("probability")
    if probability is not None and (isinstance(probability, bool) or not isinstance(probability, (int, float)) or not 0 <= probability <= 1):
        return {"verdict": "refuse", "reason": "invalid_probability"}
    if probability is not None and probability >= 0.5:
        authority = case.get("lifecycle_authority", "unknown")
        if authority == "resolved_yes":
            return {"verdict": "keep", "reason": "authoritative_answer"}
        if authority == "still_possible":
            return {"verdict": "keep", "reason": "authoritative_live"}
        return {"verdict": "needs_authority", "reason": "price_cannot_decide_lifecycle"}
    return {"verdict": "drop", "reason": "expired_deadline"}


def load() -> dict[str, Any]:
    return json.loads(FIXTURES.read_text())


def evaluate(pack: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for case in pack["cases"]:
        actual = decide(case)
        rows.append({"id": case["id"], "passed": actual == case["expected"], "actual": actual})
    return {"total": len(rows), "passed": sum(row["passed"] for row in rows), "cases": rows}


if __name__ == "__main__":
    print(json.dumps(evaluate(load()), indent=2, sort_keys=True))
