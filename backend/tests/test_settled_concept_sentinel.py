"""Tests for the Settled-Concept Sentinel (Queue #226 Item 1).

Covers the four settled-contract checks (champion hero, field membership,
evolution resolves, round resolution), the REAL-vs-EXPLAINED verdict (name
variants are EXPLAINED, out-of-field names are REAL), and the run-level
scorecard + dry-run filing (no network — fetchers are monkeypatched).
"""

import asyncio
import importlib
from datetime import date

import pytest

# The Celery task registered as ``app.tasks.settled_concept_sentinel`` shadows the
# submodule attribute on ``app.tasks``, so import the module explicitly.
scs = importlib.import_module("app.tasks.settled_concept_sentinel")


@pytest.fixture(autouse=True)
def _durable_substrate(monkeypatch):
    """Stub the durable substrate these detection tests do not provide.

    Queue 298 made the sentinel's evidence write REQUIRED: a run whose scorecard
    was not persisted may no longer report success. These tests exercise
    detection/scorecard/filing with no Postgres, so the substrate is stubbed
    here — the real persistence contract (durable-first ordering, and the run
    failing when the durable write fails) is pinned in
    ``tests/test_durable_state_298.py`` and ``tests/test_sentinel_durable_evidence_298.py``.
    """
    import app.services.durable_snapshots as dsnap

    async def _ok(envelope):
        return {"status": "ok", "identity": envelope.identity,
                "generation": envelope.generation}

    monkeypatch.setattr(dsnap, "publish_snapshot_standalone", _ok)


# ---------------------------------------------------------------------------
# Fixtures — a GREEN settled winner-field payload, mutated per test.
# ---------------------------------------------------------------------------
def _competitor(name, prob, won=False):
    return {"name": name, "probability": prob, "won": won}


def green_payload():
    """A settled golf concept that satisfies the whole contract."""
    return {
        "event": {"status": "settled", "name": "The Open Championship"},
        "primary": {
            "kind": "winner_field",
            "label": "Winner",
            "evolution_market_id": 999,
            "competitors": [
                _competitor("Ryan Fox", 0.999, won=True),
                _competitor("Doug Ghim", 0.007),
                _competitor("Jordan Smith", 0.005),
                _competitor("Matt McCarty", 0.004),  # in-field, name-variant target
                _competitor("Haotong Li", 0.003),
                _competitor("Scottie Scheffler", 0.002),
            ],
        },
        "children": [
            {
                "market_name": "Round 1 Leader",
                "outcomes": [
                    {"name": "Ryan Fox", "probability": 0.999},
                    {"name": "Jordan Smith", "probability": 0.01},
                ],
            },
            {
                "market_name": "Round 1: Top 5 Finishers",
                "outcomes": [
                    # A name-spelling variant of an in-field competitor — EXPLAINED.
                    {"name": "Matthew McCarty", "probability": 0.6},
                    {"name": "Hao-Tong Li", "probability": 0.5},
                    {"name": "Scottie Scheffler", "probability": 0.4},
                ],
            },
            {
                # Structural (non-competitor) outcomes must never be flagged.
                "market_name": "Round 2 Leader",
                "outcomes": [
                    {"name": "Ryan Fox", "probability": 0.99},
                    {"name": "The Field", "probability": 0.4},
                ],
            },
        ],
    }


def green_chart():
    """Evolution series: one resolving winner line, everyone else low."""
    return {
        "outcomes": [
            {"name": "Ryan Fox", "history": [{"probability": 0.2}, {"probability": 0.999}]},
            {"name": "Doug Ghim", "history": [{"probability": 0.05}, {"probability": 0.002}]},
            {"name": "Jordan Smith", "history": [{"probability": 0.03}, {"probability": 0.001}]},
        ]
    }


# ---------------------------------------------------------------------------
# GREEN baseline
# ---------------------------------------------------------------------------
def test_green_payload_has_no_real_findings():
    findings = scs.run_all_checks(green_payload(), green_chart())
    real = [f for f in findings if f["verdict"] == "REAL"]
    assert real == [], f"expected GREEN, got REAL: {[f['detail'] for f in real]}"


# ---------------------------------------------------------------------------
# #1177 close discipline: green-streak advances on GREEN, resets on RED, and a
# concept is only closeable after GREEN_STREAK_TO_CLOSE consecutive GREEN runs.
# ---------------------------------------------------------------------------
def test_next_green_streak_advances_and_resets():
    assert scs.next_green_streak(None, is_green=True) == 1
    assert scs.next_green_streak(1, is_green=True) == 2
    assert scs.next_green_streak(5, is_green=True) == 6
    assert scs.next_green_streak(3, is_green=False) == 0
    assert scs.next_green_streak(None, is_green=False) == 0


def test_green_streak_close_gate():
    # Not closeable until the streak reaches the threshold (2).
    assert (scs.next_green_streak(None, True) >= scs.GREEN_STREAK_TO_CLOSE) is False
    assert (scs.next_green_streak(1, True) >= scs.GREEN_STREAK_TO_CLOSE) is True


# ---------------------------------------------------------------------------
# A. Champion hero
# ---------------------------------------------------------------------------
def test_champion_hero_null_winner_is_real():
    p = green_payload()
    for c in p["primary"]["competitors"]:
        c["won"] = False
    real = [f for f in scs.check_champion_hero(p) if f["verdict"] == "REAL"]
    assert len(real) == 1
    assert "NO champion" in real[0]["detail"]


def test_champion_hero_multiple_winners_is_real():
    p = green_payload()
    p["primary"]["competitors"][1]["won"] = True  # a co-winner (squash class)
    real = [f for f in scs.check_champion_hero(p) if f["verdict"] == "REAL"]
    assert len(real) == 1
    assert "champions" in real[0]["detail"]


def test_champion_hero_wrong_crown_when_field_frozen():
    # #229 facet A: the field IS frozen (leader Ryan Fox at 0.999) but the crown
    # sits on a different, low competitor — a genuinely mis-graded hero (WORST).
    p = green_payload()
    p["primary"]["competitors"][0]["won"] = False
    p["primary"]["competitors"][3]["won"] = True  # Matt McCarty @ 0.004
    real = [f for f in scs.check_champion_hero(p) if f["verdict"] == "REAL"]
    assert len(real) == 1
    assert real[0]["facet"] == "wrong-crown"
    assert "WRONG CROWN" in real[0]["detail"]


def test_champion_hero_stale_probs_when_field_unfrozen():
    # #229 facet B (the Open case): the crown is CORRECT (won:true) but the settled
    # field was never frozen — nobody near 100%, so the graded champion shows a
    # stale longshot price BELOW the live field (gotcha #33 re-pollution).
    p = green_payload()
    p["primary"]["competitors"][0]["probability"] = 0.004  # Ryan Fox — graded, stale price
    p["primary"]["competitors"][5]["probability"] = 0.089  # a live favorite tops the field
    real = [f for f in scs.check_champion_hero(p) if f["verdict"] == "REAL"]
    assert len(real) == 1
    assert real[0]["facet"] == "correct-crown-stale-probs"
    assert "STALE PROBS" in real[0]["detail"]


def test_champion_hero_non_winner_kind_is_real():
    p = green_payload()
    p["primary"]["kind"] = "prop"  # not a winner class
    real = [f for f in scs.check_champion_hero(p) if f["verdict"] == "REAL"]
    assert len(real) == 1
    assert "not a winner class" in real[0]["detail"]


# ---------------------------------------------------------------------------
# B. Field membership — the REAL vs EXPLAINED heart of the sentinel
# ---------------------------------------------------------------------------
def test_field_membership_out_of_field_is_real():
    p = green_payload()
    # Tiger Woods is NOT in the field — the contamination class (#225 forensic).
    p["children"][0]["outcomes"].append({"name": "Tiger Woods", "probability": 0.3})
    real = [f for f in scs.check_field_membership(p) if f["verdict"] == "REAL"]
    assert len(real) == 1
    assert "Tiger Woods" in real[0]["detail"]


def test_field_membership_name_variant_is_not_flagged():
    # green_payload already puts "Matthew McCarty"/"Hao-Tong Li" in round markets
    # against in-field "Matt McCarty"/"Haotong Li" — these are EXPLAINED variants.
    real = [f for f in scs.check_field_membership(green_payload()) if f["verdict"] == "REAL"]
    assert real == [], f"name variants must not be flagged: {[f['detail'] for f in real]}"


def test_field_membership_ignores_structural_outcomes():
    p = green_payload()
    # "Region to Win" style roll-ups / yes-no must never count as strays.
    p["children"].append(
        {
            "market_name": "Round 3 Leader",
            "outcomes": [
                {"name": "Ryan Fox", "probability": 0.99},
                {"name": "United States", "probability": 0.3},
                {"name": "No Leader", "probability": 0.1},
            ],
        }
    )
    real = [f for f in scs.check_field_membership(p) if f["verdict"] == "REAL"]
    assert real == []


# ---------------------------------------------------------------------------
# C. Evolution resolves
# ---------------------------------------------------------------------------
def test_evolution_fizzled_winner_is_real():
    p = green_payload()
    chart = {
        "outcomes": [
            {"name": "Ryan Fox", "history": [{"probability": 0.2}, {"probability": 0.18}]},
            {"name": "Doug Ghim", "history": [{"probability": 0.05}, {"probability": 0.02}]},
        ]
    }
    real = [f for f in scs.check_evolution_resolves(p, chart) if f["verdict"] == "REAL"]
    assert len(real) == 1
    assert "fizzled" in real[0]["detail"]


def test_evolution_wall_is_real():
    p = green_payload()
    chart = {
        "outcomes": [
            {"name": f"g{i}", "history": [{"probability": 0.99}]} for i in range(scs.WALL_MAX + 2)
        ]
    }
    real = [f for f in scs.check_evolution_resolves(p, chart) if f["verdict"] == "REAL"]
    assert len(real) == 1
    assert "0.99-wall" in real[0]["detail"]


def test_evolution_missing_market_id_is_real():
    p = green_payload()
    p["primary"]["evolution_market_id"] = None
    real = [f for f in scs.check_evolution_resolves(p, None) if f["verdict"] == "REAL"]
    assert len(real) == 1
    assert "no `evolution_market_id`" in real[0]["detail"]


def test_evolution_missing_chart_is_explained_not_real():
    p = green_payload()  # has evolution_market_id but chart fetch failed
    findings = scs.check_evolution_resolves(p, None)
    assert all(f["verdict"] == "EXPLAINED" for f in findings)
    assert not any(f["verdict"] == "REAL" for f in findings)


# ---------------------------------------------------------------------------
# D. Round resolution
# ---------------------------------------------------------------------------
def test_round_resolution_double_graded_is_real():
    p = green_payload()
    p["children"][0]["outcomes"] = [
        {"name": "Ryan Fox", "probability": 0.99},
        {"name": "Jordan Smith", "probability": 0.985},  # a second "leader" — impossible
    ]
    real = [f for f in scs.check_round_resolution(p) if f["verdict"] == "REAL"]
    assert len(real) == 1
    assert "double-graded" in real[0]["detail"]


def test_round_resolution_ungraded_round_is_not_real():
    # A round leader market with no high outcome = deferred grading (#887) = EXPLAINED.
    p = green_payload()
    p["children"][0]["outcomes"] = [
        {"name": "Ryan Fox", "probability": 0.4},
        {"name": "Jordan Smith", "probability": 0.3},
    ]
    real = [f for f in scs.check_round_resolution(p) if f["verdict"] == "REAL"]
    assert real == []


# ---------------------------------------------------------------------------
# Target selection
# ---------------------------------------------------------------------------
def test_recently_settled_targets_windows_by_end_date(monkeypatch):
    cal = [
        {"concept_key": "event:golf:a", "end": "2026-07-19"},  # 2 days ago
        {"concept_key": "event:golf:b", "end": "2026-07-01"},  # 20 days ago (out)
        {"concept_key": "event:golf:c", "end": "2026-07-25"},  # future (out)
        {"concept_key": None, "end": "2026-07-20"},            # no concept_key (out)
    ]
    monkeypatch.setattr(
        "app.utils.majors_calendar.load_calendar", lambda *a, **k: cal
    )
    got = scs.recently_settled_targets(date(2026, 7, 21), window_days=3)
    keys = {e["concept_key"] for e in got}
    assert keys == {"event:golf:a"}


# ---------------------------------------------------------------------------
# Run-level: scorecard + dry-run filing (no network)
# ---------------------------------------------------------------------------
def _patch_fetch(monkeypatch, payload, chart):
    async def fake_concept(client, key):
        return payload

    async def fake_chart(client, mid, champion=None):
        return chart

    monkeypatch.setattr(scs, "_fetch_concept", fake_concept)
    monkeypatch.setattr(scs, "_fetch_evolution_chart", fake_chart)


def test_run_reports_green_for_clean_concept(monkeypatch):
    _patch_fetch(monkeypatch, green_payload(), green_chart())
    filed = []
    monkeypatch.setattr(scs, "file_settled_issue", lambda *a, **k: filed.append(a) or {"action": "filed"})
    r = asyncio.run(
        scs._run_settled_concept_sentinel(file_issues=True, concept_keys=["event:golf:the-open-championship"])
    )
    assert r["checked_settled"] == 1
    assert r["green"] == 1 and r["red"] == 0
    assert filed == [], "GREEN concept must not file an issue"


def test_run_files_on_seeded_regression(monkeypatch):
    bad = green_payload()
    bad["children"][0]["outcomes"].append({"name": "Tiger Woods", "probability": 0.5})  # contamination
    _patch_fetch(monkeypatch, bad, green_chart())
    calls = []

    def fake_file(concept_key, name, real, explained):
        calls.append({"concept_key": concept_key, "n_real": len(real)})
        return {"concept_key": concept_key, "action": "filed", "issue": 1234}

    monkeypatch.setattr(scs, "file_settled_issue", fake_file)
    r = asyncio.run(
        scs._run_settled_concept_sentinel(file_issues=True, concept_keys=["event:golf:the-open-championship"])
    )
    assert r["red"] == 1
    assert len(calls) == 1
    assert calls[0]["n_real"] >= 1
    assert r["concepts"][0]["verdict"] == "RED"
    assert r["concepts"][0]["checks"]["Field membership"] == "RED"


def test_run_detect_only_does_not_file(monkeypatch):
    bad = green_payload()
    bad["primary"]["evolution_market_id"] = None  # a REAL defect
    _patch_fetch(monkeypatch, bad, None)
    calls = []
    monkeypatch.setattr(scs, "file_settled_issue", lambda *a, **k: calls.append(a))
    r = asyncio.run(
        scs._run_settled_concept_sentinel(file_issues=False, concept_keys=["event:golf:x"])
    )
    assert r["red"] == 1
    assert calls == [], "detect_only must never file"


def test_run_skips_unsettled_concept(monkeypatch):
    live = green_payload()
    live["event"]["status"] = "live"
    _patch_fetch(monkeypatch, live, green_chart())
    r = asyncio.run(
        scs._run_settled_concept_sentinel(file_issues=False, concept_keys=["event:golf:x"])
    )
    assert r["checked_settled"] == 0
    assert r["concepts"][0]["status"] == "live"


# ---------------------------------------------------------------------------
# Filing rail degrades safely with no token
# ---------------------------------------------------------------------------
def test_file_settled_issue_skips_without_token(monkeypatch):
    import app.tasks.bug_report_github as brg

    monkeypatch.setattr(brg, "GITHUB_TOKEN", None)
    res = scs.file_settled_issue(
        "event:golf:x", "X", [{"check": "champion_hero", "verdict": "REAL", "detail": "d"}], []
    )
    assert res["action"] == "skipped_no_token"


def test_issue_body_carries_fingerprint_and_evidence():
    real = [{"check": "field_membership", "verdict": "REAL", "detail": "Tiger Woods not in field"}]
    body = scs.build_issue_body("event:golf:the-open-championship", "The Open", real, [])
    assert "settled-concept-fingerprint:" in body
    assert "Tiger Woods" in body
    assert scs.settled_fingerprint("event:golf:the-open-championship") in body
