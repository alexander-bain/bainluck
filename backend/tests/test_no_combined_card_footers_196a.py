"""Ruling 196-A guard: no switched-on card prints a combined-across-markets chance or 'Combined' footer."""

from __future__ import annotations

import json
import re
from pathlib import Path

CONTAINERS_DIR = Path(__file__).resolve().parents[1] / "data" / "containers"
COMBINED_RE = re.compile(r"\bcombined\b", re.IGNORECASE)
SYNTHETIC_PARLAY_RE = re.compile(
    r"\b(?:chance\s+all\s+\d+|all\s+\d+\s+survive|sum\s+to\s+\d+%)\b",
    re.IGNORECASE,
)


def test_no_switched_on_container_prints_combined_footer_or_parlay_number():
    checked = 0
    for path in sorted(CONTAINERS_DIR.glob("*.json")):
        if path.name.endswith("-rows.json"):
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        if doc.get("enabled") is False:
            continue
        checked += 1
        for field in ("name", "description", "footer", "section_title"):
            val = str(doc.get(field) or "")
            assert not COMBINED_RE.search(val), (
                f"{path.name} field {field!r} still contains 'combined': {val!r}"
            )
            assert not SYNTHETIC_PARLAY_RE.search(val), (
                f"{path.name} field {field!r} contains combined-market figure: {val!r}"
            )
    assert checked >= 20
