"""Tests for the daily grid-register drift sentinel (Queue 295, Item 2).

The properties under test are the safety ones: ambiguity is never applied, one
poison league cannot starve or contaminate its siblings, a malformed generation
never replaces a good register, and publication is atomic.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from app.tasks.grid_register_sentinel import (
    build_drift_issue_body,
    drift_fingerprint,
    propose_transition,
    publish_register,
    register_age_hours,
)
from app.utils.grid_register import (
    build_contract,
    classify,
    diff_against_inventory,
    register_filename,
    validate_transition,
)


@pytest.fixture(autouse=True)
def _durable_substrate(monkeypatch):
    """Stub the durable substrate these tests do not provide.

    Queue 298 made the sentinel's evidence write REQUIRED: a run whose scorecard
    was not persisted may no longer report success. These tests have no Postgres,
    so the substrate is stubbed; the persistence contract itself is pinned in
    ``tests/test_sentinel_durable_evidence_298.py``.
    """
    import app.services.durable_snapshots as dsnap

    async def _ok(envelope):
        return {"status": "ok", "identity": envelope.identity,
                "generation": envelope.generation}

    monkeypatch.setattr(dsnap, "publish_snapshot_standalone", _ok)

NOW = "2026-08-01T00:00:00+00:00"
SPECS = {"nba": {"season": "2026-27", "entity_kind": "team",
                 "stages": ["make_playoffs", "division", "conference", "championship"]}}
CONTRACT = build_contract(SPECS)


def _entry(**over) -> dict:
    base = {
        "stage": "championship",
        "entity_key": "oklahoma city thunder",
        "entity_name": "Oklahoma City Thunder",
        "source": "kalshi",
        "status": "live",
        "market_id": 101,
        "outcome_id": 5001,
        "external_id": "KXNBA-27",
        "evidence": {"kind": "ticker_exact", "observed_at": NOW},
    }
    base.update(over)
    return base


def _register(entries=None, **over) -> dict:
    base = {
        "schema_version": "grid-register/v1",
        "league": "nba",
        "season": "2026-27",
        "version": 1,
        "generated_at": NOW,
        "entries": entries if entries is not None else [_entry()],
    }
    base.update(over)
    return base


def _candidate(**over) -> dict:
    base = {
        "stage": "championship",
        "entity_key": "oklahoma city thunder",
        "entity_name": "Oklahoma City Thunder",
        "source": "kalshi",
        "season": "2026-27",
        "market_id": 101,
        "outcome_id": 5001,
        "external_id": "KXNBA-27",
        "market_name": "Pro Basketball Champion",
        "status": "live",
        "terminal_result": None,
    }
    base.update(over)
    return base


# ---------------------------------------------------------------------------
# Transition proposal — the deterministic rule, and only that rule
# ---------------------------------------------------------------------------

def test_no_drift_proposes_nothing():
    reg = _register()
    cands = [_candidate()]
    assert propose_transition(reg, cands, diff_against_inventory(reg, cands)) is None


def test_rename_proposes_a_valid_next_version():
    reg = _register()
    cands = [_candidate(external_id="KXNBACHAMP-27")]
    findings = diff_against_inventory(reg, cands)
    proposed = propose_transition(reg, cands, findings, observed_at=NOW)

    assert proposed is not None
    assert proposed["version"] == 2
    assert proposed["supersedes_version"] == 1
    assert proposed["entries"][0]["external_id"] == "KXNBACHAMP-27"
    assert proposed["entries"][0]["evidence"]["kind"] == "exact_identity_rename"
    assert proposed["entries"][0]["evidence"]["previous_external_id"] == "KXNBA-27"
    # The pinned identity itself is untouched — only its label moved.
    assert proposed["entries"][0]["market_id"] == 101
    assert proposed["entries"][0]["outcome_id"] == 5001
    assert validate_transition(reg, proposed, CONTRACT) == []


def test_settlement_proposes_a_terminal_entry():
    reg = _register()
    cands = [_candidate(status="settled", terminal_result="won")]
    findings = diff_against_inventory(reg, cands)
    proposed = propose_transition(reg, cands, findings, observed_at=NOW)

    assert proposed["entries"][0]["status"] == "settled"
    assert proposed["entries"][0]["terminal_result"] == "won"
    assert proposed["entries"][0]["evidence"]["kind"] == "authoritative_settlement"
    assert validate_transition(reg, proposed, CONTRACT) == []


def test_ambiguous_identity_drift_never_proposes():
    """A different market backing the cell is a human call."""
    reg = _register()
    cands = [_candidate(market_id=999, outcome_id=8888)]
    findings = diff_against_inventory(reg, cands)
    assert propose_transition(reg, cands, findings) is None
    assert classify(findings)["action"] == "file_p2_needs_triage"


def test_vanished_identity_never_proposes():
    reg = _register()
    findings = diff_against_inventory(reg, [])
    assert propose_transition(reg, [], findings) is None


def test_next_season_never_proposes():
    reg = _register()
    cands = [_candidate(), _candidate(season="2027-28", market_id=222, outcome_id=7777)]
    findings = diff_against_inventory(reg, cands)
    assert propose_transition(reg, cands, findings) is None


def test_mixed_drift_is_all_or_nothing():
    """One ambiguous cell disqualifies the league — never a partial publish."""
    reg = _register([
        _entry(),
        _entry(stage="conference", market_id=102, outcome_id=5002, external_id="KXNBAWEST-27"),
    ])
    cands = [
        _candidate(external_id="KXNBACHAMP-27"),                    # unambiguous rename
        _candidate(stage="conference", market_id=777, outcome_id=9999),  # ambiguous
    ]
    findings = diff_against_inventory(reg, cands)
    assert "UNAMBIGUOUS_RENAME_DRIFT" in findings
    assert "IDENTITY_DRIFT_AMBIGUOUS" in findings
    assert propose_transition(reg, cands, findings) is None
    assert classify(findings)["publish"] is False


def test_settlement_without_result_never_proposes():
    reg = _register()
    cands = [_candidate(status="settled", terminal_result=None)]
    findings = diff_against_inventory(reg, cands)
    assert "SETTLEMENT_WITHOUT_RESULT" in findings
    assert propose_transition(reg, cands, findings) is None


# ---------------------------------------------------------------------------
# Publication safety
# ---------------------------------------------------------------------------

def test_publish_is_atomic_and_leaves_no_temp(tmp_path):
    proposed = _register(version=2, supersedes_version=1)
    result = publish_register(proposed, tmp_path)

    assert result["published"] is True
    path = tmp_path / register_filename("nba", "2026-27")
    assert json.loads(path.read_text())["version"] == 2
    assert list(tmp_path.glob("*.tmp")) == []


def test_publish_failure_retains_last_good(tmp_path):
    """An unwritable target must leave the previous register fully intact."""
    path = tmp_path / register_filename("nba", "2026-27")
    path.write_text(json.dumps(_register()) + "\n")
    tmp_path.chmod(0o500)  # read + execute only
    try:
        result = publish_register(_register(version=2, supersedes_version=1), tmp_path)
    finally:
        tmp_path.chmod(0o700)

    assert result["published"] is False
    assert "write_failed" in result["reason"]
    assert json.loads(path.read_text())["version"] == 1  # last-good survived


def test_invalid_proposal_is_rejected_before_publish():
    reg = _register()
    bad = _register(version=2, supersedes_version=1, entries=[_entry(status="settled")])
    findings = validate_transition(reg, bad, CONTRACT)
    assert "SETTLED_WITHOUT_RESULT" in findings


# ---------------------------------------------------------------------------
# Fingerprinting + issue body
# ---------------------------------------------------------------------------

def test_fingerprint_is_stable_per_league_and_shape():
    a = drift_fingerprint("nba", ["IDENTITY_DRIFT_AMBIGUOUS"])
    b = drift_fingerprint("nba", ["IDENTITY_DRIFT_AMBIGUOUS"])
    c = drift_fingerprint("nhl", ["IDENTITY_DRIFT_AMBIGUOUS"])
    d = drift_fingerprint("nba", ["AMBIGUOUS_CANDIDATES"])
    assert a == b
    assert a != c and a != d


def test_fingerprint_ignores_finding_order():
    a = drift_fingerprint("nba", ["A", "B"])
    b = drift_fingerprint("nba", ["B", "A", "B"])
    assert a == b


def test_issue_body_carries_the_question_and_options():
    body = build_drift_issue_body({
        "league": "nba",
        "version": 1,
        "season": "2026-27",
        "findings": ["AMBIGUOUS_CANDIDATES"],
        "counters": {"live": 30},
        "candidate_count": 31,
        "age_hours": 12.0,
        "fingerprint": "abc123",
        "ambiguities": [{
            "reason": "multiple_candidates",
            "stage": "championship",
            "entity_key": "denver nuggets",
            "source": "kalshi",
            "candidates": [
                {"market_id": 1, "market_name": "Pro Basketball Champion", "external_id": "KXNBA-27"},
                {"market_id": 2, "market_name": "NBA Finals Winner", "external_id": "KXNBAF-27"},
            ],
        }],
    })
    assert "NBA" in body
    assert "Question for Alex" in body
    assert "2 markets claim this cell" in body
    assert "Options" in body
    assert "fingerprint: abc123" in body
    # It must say plainly that nothing was changed.
    assert "register is unchanged" in body.lower()


# ---------------------------------------------------------------------------
# Age
# ---------------------------------------------------------------------------

def test_register_age_hours():
    now = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
    reg = _register(generated_at=(now - timedelta(hours=6)).isoformat())
    assert register_age_hours(reg, now) == 6.0


def test_register_age_handles_junk():
    assert register_age_hours({"generated_at": "soon"}) is None
    assert register_age_hours({}) is None


# ---------------------------------------------------------------------------
# Per-league isolation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_one_poison_league_does_not_starve_siblings(monkeypatch, tmp_path):
    """A crash in one league must not stop the others or read as clean."""
    import app.tasks.grid_register_sentinel as sentinel

    (tmp_path / register_filename("nba", "2025-26")).write_text(json.dumps(_register()))

    async def fake_run_league(session, league, *, apply, directory):
        if league == "mlb":
            raise RuntimeError("poisoned inventory")
        return {"league": league, "status": "ok", "classification": "clean",
                "action": "no_change", "published": False, "counters": {"live": 1}}

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(sentinel, "_run_league", fake_run_league)
    monkeypatch.setattr("app.services.database.async_session_maker", lambda: _Session())

    stats = await sentinel._run_grid_register_sentinel(file_issues=False, directory=tmp_path)

    leagues = {lg["league"]: lg for lg in stats["leagues"]}
    assert set(leagues) == set(sentinel.REGISTER_LEAGUES)
    assert leagues["mlb"]["status"] == "crashed"
    assert leagues["mlb"]["published"] is False
    assert "poisoned inventory" in leagues["mlb"]["failure_cause"]
    # Siblings still ran and are still reported clean.
    assert leagues["nba"]["classification"] == "clean"
    assert leagues["nhl"]["classification"] == "clean"
    assert stats["errors"]
    # The crashed league is NOT counted as clean.
    assert stats["scorecard"]["leagues_clean"] == len(sentinel.REGISTER_LEAGUES) - 1


@pytest.mark.asyncio
async def test_missing_register_is_reported_not_an_error(monkeypatch, tmp_path):
    import app.tasks.grid_register_sentinel as sentinel

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr("app.services.database.async_session_maker", lambda: _Session())
    stats = await sentinel._run_grid_register_sentinel(file_issues=False, directory=tmp_path)

    assert all(lg["status"] == "no_register" for lg in stats["leagues"])
    assert stats["errors"] == []
    assert stats["scorecard"]["leagues_with_register"] == 0
