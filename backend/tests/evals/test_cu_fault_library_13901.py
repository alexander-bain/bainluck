"""Content Understanding fault library CI gate (#13901).

Every fault caught in #1809 grading becomes a frozen deterministic case running
offline with zero model or network calls.
"""

from __future__ import annotations

import ast
import json
import socket
from datetime import datetime
from pathlib import Path

import pytest

from app.tasks.enrich_markets import _compute_liveness
from app.utils.cu_event_facts import (
    cu_event_facts,
    cu_model_geography,
    cu_unlinked_event_date,
)
from app.utils.cu_frame import ground_subjects, sanitize_cu_frame
from app.utils.cu_junk_flags import cu_junk_flags

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "cu_fault_library_13901.json"


def _load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def _block_network(monkeypatch):
    def offline(*args, **kwargs):
        raise AssertionError("CU fault library tests must not touch the network")

    monkeypatch.setattr(socket, "socket", offline)


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


def test_fault_library_file_has_all_six_district_races_and_canonical_sections():
    data = _load_fixture()
    assert len(data["district_races"]) == 6
    assert len(data["europa_league_geography"]) >= 2
    assert len(data["ladders_and_buckets"]) >= 4
    assert len(data["settlement_day_echo"]) >= 4
    assert len(data["linked_schedule_boundaries"]) >= 3
    assert len(data["frame_sanitizers"]) >= 4


@pytest.mark.parametrize("case", _load_fixture()["district_races"], ids=lambda c: c["id"])
def test_six_state_legislative_district_races(case):
    facts = cu_event_facts(case["title"])
    for key, expected_val in case["expected"].items():
        assert facts[key] == expected_val, f"{case['id']}: {key}"


@pytest.mark.parametrize("case", _load_fixture()["europa_league_geography"], ids=lambda c: c["id"])
def test_europa_league_never_keeps_single_country_tag(case):
    sanitized = cu_model_geography(
        case["bad_model_geography"],
        linked_league=case["linked_league"],
        home_team_league=case["home_team_league"],
        away_team_league=case["away_team_league"],
    )
    assert sanitized == case["expected_sanitized_geography"]

    facts = cu_event_facts(
        case["title"],
        linked_game_id=case["linked_game_id"],
        linked_start=_parse_iso(case["linked_start"]),
        start_source=case["start_source"],
        linked_league=case["linked_league"],
        home_team_league=case["home_team_league"],
        away_team_league=case["away_team_league"],
    )
    for key, expected_val in case["expected_event_facts"].items():
        assert facts[key] == expected_val


@pytest.mark.parametrize("case", _load_fixture()["ladders_and_buckets"], ids=lambda c: c["id"])
def test_ladders_and_dated_buckets_caught_even_when_model_misses_them(case):
    flags = cu_junk_flags(case["outcome_names"], case["model_flags"])
    assert sorted(flags) == sorted(case["expected_flags"])


@pytest.mark.parametrize("case", _load_fixture()["settlement_day_echo"], ids=lambda c: c["id"])
def test_settlement_day_copied_as_event_day_is_cleared(case):
    out = cu_unlinked_event_date(case["model_date"], _parse_iso(case["settlement_at"]))
    assert out == case["expected_event_date"]


@pytest.mark.parametrize("case", _load_fixture()["linked_schedule_boundaries"], ids=lambda c: c["id"])
def test_linked_schedule_day_and_polymarket_venue_provenance(case):
    facts = cu_event_facts(
        case["title"],
        linked_game_id=case["linked_game_id"],
        linked_start=_parse_iso(case["linked_start"]),
        start_source=case["start_source"],
        linked_league=case["linked_league"],
    )
    assert facts["event_date"] == case["expected_event_date"]


@pytest.mark.parametrize("case", _load_fixture()["frame_sanitizers"], ids=lambda c: c["id"])
def test_frame_sanitizer_enforces_literal_title_grounding(case):
    frame, drop_reason = sanitize_cu_frame(case["raw_frame"], title=case["title"])
    if "expected_drop_reason" in case:
        assert frame is None
        assert drop_reason == case["expected_drop_reason"]
    else:
        assert drop_reason is None
        assert frame == case["expected_frame"]


def test_grounded_subject_and_bundled_liveness():
    data = _load_fixture()
    sub_case, live_case = data["subject_and_liveness"]
    _, subject_ref, subject_entity_id, subject_resolved = ground_subjects(
        sub_case["mentions"], sub_case["resolved"]
    )
    assert subject_ref == sub_case["expected_subject_ref"]
    assert subject_entity_id is None
    assert subject_resolved is sub_case["expected_subject_resolved"]
    assert _compute_liveness(live_case["probs"], live_case["status"]) == live_case["expected_liveness"]


def test_negative_control_fault_library_contains_zero_model_clients():
    src = Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module.split(".")[0])
    assert {"openai", "httpx", "requests"}.isdisjoint(imported_modules)
