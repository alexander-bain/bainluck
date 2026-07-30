"""Queue 283 Item 2 — lifecycle time-ordering invariant at the REAL classifiers.

C81 ``real-world-lifecycle/v1`` says a card may be labeled ``live`` only once its
authoritative start/commence time has passed; unknown/future start never
establishes live. These tests wire that contract to the real code paths (the
shared ``app.utils.lifecycle`` helper, the game-card classifier
``highlights.compute_highlight``, the golf live-flip guard, and the Flow Sentinel
detector) rather than a pure re-validation of the fixture — and cover the
synthetic TdF / Belgian GP / AIG future-start counterexamples. No source-string
assertions.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.utils.lifecycle import enforce_live_requires_start, live_start_satisfied

NOW = datetime(2026, 7, 29, 18, 0, tzinfo=timezone.utc)

LIFECYCLE_FIXTURES = (
    Path(__file__).parents[1]
    / "scripts"
    / "evals"
    / "real_world_lifecycle_fixtures.json"
)


def _fixture() -> dict:
    return json.loads(LIFECYCLE_FIXTURES.read_text())


# --- shared helper (the canonical seam) ------------------------------------
def test_live_start_satisfied_requires_known_past_start():
    assert live_start_satisfied(NOW - timedelta(hours=1), NOW) is True
    assert live_start_satisfied(NOW, NOW) is True
    assert live_start_satisfied(NOW + timedelta(hours=1), NOW) is False
    # Unknown / non-comparable authority never establishes live.
    assert live_start_satisfied(None, NOW) is False
    assert live_start_satisfied("not-a-datetime", NOW) is False


def test_enforce_only_downgrades_live_before_start():
    # live before start -> upcoming; live after start stays live.
    assert enforce_live_requires_start("live", NOW + timedelta(hours=2), NOW) == "upcoming"
    assert enforce_live_requires_start("live", NOW - timedelta(hours=2), NOW) == "live"
    assert enforce_live_requires_start("live", None, NOW) == "upcoming"
    # Non-live states pass through untouched (never invents settled).
    for state in ("upcoming", "settled", "unmeasured", None):
        assert enforce_live_requires_start(state, NOW + timedelta(days=5), NOW) == state


# --- real game-card classifier --------------------------------------------
def test_compute_highlight_never_live_before_commence():
    from app.utils.highlights import compute_highlight

    future = compute_highlight(
        status="live", commence_time=NOW + timedelta(hours=3), now=NOW
    )
    assert future.flags.is_live is False
    started = compute_highlight(
        status="live", commence_time=NOW - timedelta(hours=1), now=NOW
    )
    assert started.flags.is_live is True


# --- golf live-flip start guard (covers AIG) -------------------------------
def test_golf_start_in_future_blocks_pre_start_live():
    from app.utils.event_concept import _golf_start_in_future

    # Known future start -> blocked (AIG: movement/fresh board may not establish
    # live before commence).
    assert _golf_start_in_future("2026-08-05", NOW) is True
    # Started / missing / unparseable -> not blocked (freshness fallback #144).
    assert _golf_start_in_future("2026-07-29", NOW) is False
    assert _golf_start_in_future(None, NOW) is False
    assert _golf_start_in_future("garbage", NOW) is False


# --- Flow Sentinel detector -----------------------------------------------
def test_flow_sentinel_flags_live_before_commence():
    from app.tasks.flow_sentinel import live_before_commence_events

    events = [
        {"id": 1, "status": "live", "sport": "s",
         "commence_time": (NOW + timedelta(hours=4)).isoformat()},   # future -> flagged
        {"id": 2, "status": "live", "sport": "s",
         "commence_time": (NOW - timedelta(hours=1)).isoformat()},   # started -> ok
        {"id": 3, "status": "completed", "sport": "s",
         "commence_time": (NOW + timedelta(hours=4)).isoformat()},   # not live -> ignored
    ]
    flagged = live_before_commence_events(events, NOW)
    assert [e["event_id"] for e in flagged] == [1]
    assert flagged[0]["starts_in_hours"] == 4.0


# --- cover the synthetic TdF / Belgian GP / AIG rows via the shared seam ----
def test_future_start_counterexamples_never_resolve_live():
    """The C81 reject rows (TdF/Belgian GP/AIG) declare live with a FUTURE start.
    Routed through the shared invariant they can never remain live."""
    corpus = _fixture()
    future_live_rejects = [
        r
        for r in corpus["rejected_counterexamples"]
        if "live_before_start" in r.get("expected_violations", [])
    ]
    # tdf + belgian gp + aig
    assert len(future_live_rejects) >= 3
    for row in future_live_rejects:
        assert row["declared_state"] == "live"
        assert row["start_relation"] == "future"
        # A future start_relation maps to a start strictly after now.
        resolved = enforce_live_requires_start(
            "live", NOW + timedelta(days=1), NOW
        )
        assert resolved == "upcoming"


def test_accepted_active_started_row_stays_live():
    corpus = _fixture()
    active = next(r for r in corpus["scenarios"] if r["id"] == "active_started_live")
    assert active["declared_state"] == "live"
    # start_relation past -> start before now -> live preserved.
    assert enforce_live_requires_start("live", NOW - timedelta(hours=1), NOW) == "live"
