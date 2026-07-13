"""Regression test for ``audit_resolution_engine._md`` (#1021).

The admin ``db-query`` endpoint serializes JSONB columns as a Python ``repr``
(single-quoted), not JSON. Before the fix, ``_md`` only tried ``json.loads`` and
silently returned ``{}`` for every row — so the shadow audit could never read
``matchup_title`` and reported a phantom 0/N derivative coverage, falsely gating
the Polymarket ``market_event`` cutover on an under-measured number.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.audit_resolution_engine import _md


def test_md_passthrough_dict():
    assert _md({"matchup_title": "A vs. B"}) == {"matchup_title": "A vs. B"}


def test_md_parses_json_string():
    assert _md('{"matchup_title": "A vs. B"}') == {"matchup_title": "A vs. B"}


def test_md_parses_python_repr_from_db_query():
    # This is the exact shape the admin db-query endpoint returns for JSONB.
    raw = "{'matchup_title': 'Athletics vs. Chicago White Sox - Player Props'}"
    parsed = _md(raw)
    assert parsed.get("matchup_title") == (
        "Athletics vs. Chicago White Sox - Player Props"
    )


def test_md_bad_input_returns_empty_dict():
    assert _md(None) == {}
    assert _md("not a dict") == {}
    assert _md("[1, 2, 3]") == {}  # valid literal but not a dict
