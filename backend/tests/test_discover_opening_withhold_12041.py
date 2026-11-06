"""#12041 — Ruling 23-A: Discover must never go blank because one card cannot be seated.

When ``seat_opening`` refuses:
1. Hold back only the card(s) the refusal names (``refused_positions``), fill the
   first ten from the next-best eligible cards, and serve the rest.
2. Log the offender by identity with the §5 fields, at most one warning per
   process per offender per minute.
3. The pre-warm reports the held-back card (``opening: {withheld, class, detail,
   since}``) and escalates (warn on change, error once after 15 minutes; no
   "keeping last-good" log for seated shapes when nothing can be shown).
4. No reader notice while cards remain; ``unavailable`` stays only when nothing
   is left to show (or time-budget refusals).
"""

from __future__ import annotations

import copy
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from importlib import import_module
from unittest.mock import MagicMock, patch

import pytest

from app.utils.discover_opening_edition import (
    COMPOSED,
    SEATING_EXPIRY_OPENING_ORDER,
    UNSUPPORTED,
    compose_opening_edition,
)
from app.utils.discover_opening_seating import (
    OPENING_SEATS,
    REFUSAL_INVALID_IDENTITY,
    REFUSAL_LIFECYCLE_CONFLICT,
    REFUSAL_MALFORMED_GROUP,
    REFUSAL_UNKNOWN_KIND,
    UNSUPPORTED as SEATING_UNSUPPORTED,
    seat_opening,
)
from app.utils.feed_cache import (
    FEED_PREWARM_KEY_SCOPE_KEY,
    FEED_PREWARM_OPENING_SCOPE_KEY,
    FEED_PREWARM_SCOPE_KEY,
    feed_edition_member,
)
from app.utils.feed_editions import (
    EDITION_STATUS_EXPIRED,
    EDITION_STATUS_UNPINNED,
    edition_policy_fingerprint,
)
from tests.integration.conftest import (  # noqa: F401
    _bypass_rate_limits,
    client,
    mock_db,
)
from tests.integration.test_route_feed_opening_seating_5105 import (
    _DictRedis,
    _drain,
    _get,
    _harness,  # noqa: F401
    _ids,
    _install,
    _plant,
    seated,  # noqa: F401
)

feed_module = import_module("app.routes.feed")
pcp = import_module("app.tasks.precompute_category_pages")

NOW = datetime(2026, 11, 5, 1, 0, 0, tzinfo=timezone.utc)
POLICY = edition_policy_fingerprint(limit=20, event_pct=0.15, opening_seating=True)


def _futures(i: int, score: float = 80.0) -> dict:
    return {
        "type": "futures",
        "score": score,
        "_rank_score": float(score),
        "headline": "Market",
        "reason": f"why {i}",
        "data": {
            "id": i,
            "name": f"Market {i}",
            "top_outcomes": [{"name": "Yes", "probability": 0.45}],
            "sources": ["kalshi"],
        },
    }


def _event(
    i: int,
    *,
    status: str = "live",
    start: datetime | None = None,
    score: float = 90.0,
    **data,
) -> dict:
    commence = (start or (NOW - timedelta(hours=1))).isoformat()
    return {
        "type": "event",
        "score": score,
        "_rank_score": float(score),
        "data": {
            "id": i,
            "status": status,
            "commence_time": commence,
            "event_tags": [],
            "hero_probability": 0.55,
            **data,
        },
    }


def _conflicted_schwab_tournament() -> dict:
    """The Nov 4 incident card: schedule_status='in_progress' while start_date
    is Nov 12–15 (future window at Nov 5)."""
    return {
        "type": "tournament",
        "score": 92.0,
        "_rank_score": 92.0,
        "headline": "Live",
        "reason": "Tournament",
        "data": {
            "key": "pgachamp_charles_schwab_cup_championship",
            "name": "Charles Schwab Cup Championship",
            "schedule_status": "in_progress",
            "start_date": "2026-11-12T00:00:00+00:00",
            "end_date": "2026-11-15T00:00:00+00:00",
            "champion": None,
            "is_major": False,
            "is_marquee": False,
        },
    }


@pytest.fixture(autouse=True)
def _reset_12041_state():
    feed_module._reset_opening_offender_log_for_tests()
    pcp._reset_prewarm_opening_withheld_for_tests()
    yield
    feed_module._reset_opening_offender_log_for_tests()
    pcp._reset_prewarm_opening_withheld_for_tests()


# ---------------------------------------------------------------------------
# 1. seat_opening names refused_positions and refusal_class on all 4 branches
# ---------------------------------------------------------------------------


def test_seat_opening_names_refused_positions_across_all_four_refusal_classes():
    # (a) unknown_kind at index 3
    deck_unknown = [_futures(i) for i in range(5)]
    deck_unknown.insert(3, {"type": "mystery_kind", "data": {"id": 99}})
    out_unknown = seat_opening(deck_unknown, now=NOW)
    assert out_unknown.status == SEATING_UNSUPPORTED
    assert out_unknown.refused_positions == [3]
    assert out_unknown.refusal_class == REFUSAL_UNKNOWN_KIND

    # (b) invalid_identity (duplicate at index 4)
    deck_dup = [_futures(i) for i in range(5)]
    deck_dup.insert(4, copy.deepcopy(deck_dup[1]))
    out_dup = seat_opening(deck_dup, now=NOW)
    assert out_dup.status == SEATING_UNSUPPORTED
    assert out_dup.refused_positions == [4]
    assert out_dup.refusal_class == REFUSAL_INVALID_IDENTITY

    # (c) malformed_group at index 2
    deck_group = [_futures(i) for i in range(5)]
    deck_group.insert(
        2,
        {
            "type": "bundle",
            "data": {"id": "bad-bundle", "items": [{"type": "mystery", "data": {"id": 1}}]},
        },
    )
    out_group = seat_opening(deck_group, now=NOW)
    assert out_group.status == SEATING_UNSUPPORTED
    assert out_group.refused_positions == [2]
    assert out_group.refusal_class == REFUSAL_MALFORMED_GROUP

    # (d) lifecycle_conflict at index 7 (1-based seat 8)
    deck_conflict = [_futures(i) for i in range(12)]
    deck_conflict.insert(7, _conflicted_schwab_tournament())
    out_conflict = seat_opening(deck_conflict, now=NOW)
    assert out_conflict.status == SEATING_UNSUPPORTED
    assert out_conflict.refused_positions == [7]
    assert out_conflict.refusal_class == REFUSAL_LIFECYCLE_CONFLICT
    assert out_conflict.refused_conflicts == [
        "tournament:pgachamp_charles_schwab_cup_championship"
    ]


# ---------------------------------------------------------------------------
# 2. One unseatable card in the first ten withholds only that card & serves rest
# ---------------------------------------------------------------------------


def test_incident_131_card_deck_with_conflict_at_seat_8_serves_130_cards():
    """The Nov 4 incident shape: 131 cards with Charles Schwab Cup Championship
    in lifecycle conflict at seat 8 (0-based index 7). Holds back only that card,
    fills seat 10 from the next eligible card (futures:9), and serves all 130
    remaining cards."""
    deck = [_futures(i, score=200 - i) for i in range(130)]
    deck.insert(7, _conflicted_schwab_tournament())
    assert len(deck) == 131

    out = compose_opening_edition(
        deck, None, requested_token=None, requested_policy=POLICY, now=NOW
    )
    assert out.status == COMPOSED and out.usable
    assert out.edition_status == EDITION_STATUS_UNPINNED
    assert len(out.items) == 130
    served_ids = [feed_edition_member(c) for c in out.items]
    assert "tournament:pgachamp_charles_schwab_cup_championship" not in served_ids
    assert served_ids[:OPENING_SEATS] == [f"futures:{i}" for i in range(OPENING_SEATS)]
    assert len(out.withheld) == 1
    offender = out.withheld[0]
    assert offender["identity"] == "tournament:pgachamp_charles_schwab_cup_championship"
    assert offender["seat"] == 8
    assert offender["kind"] == "tournament"
    assert offender["refusal_class"] == REFUSAL_LIFECYCLE_CONFLICT
    assert offender["fields"]["schedule_status"] == "in_progress"
    assert offender["fields"]["start_date"] == "2026-11-12T00:00:00+00:00"
    assert offender["fields"]["end_date"] == "2026-11-15T00:00:00+00:00"


def test_ten_eligible_plus_one_unseatable_in_first_ten_serves_ten_cards():
    deck = [_futures(i, score=100 - i) for i in range(10)]
    deck.insert(3, _conflicted_schwab_tournament())
    assert len(deck) == 11

    out = compose_opening_edition(
        deck, None, requested_token=None, requested_policy=POLICY, now=NOW
    )
    assert out.status == COMPOSED and out.usable
    assert len(out.items) == 10
    assert [feed_edition_member(c) for c in out.items] == [
        f"futures:{i}" for i in range(10)
    ]
    assert [w["identity"] for w in out.withheld] == [
        "tournament:pgachamp_charles_schwab_cup_championship"
    ]


# ---------------------------------------------------------------------------
# 3. A deck with no offender is unchanged byte-for-byte
# ---------------------------------------------------------------------------


def test_deck_with_no_offender_is_byte_for_byte_unchanged():
    deck = [_futures(0), _event(100, status="live")] + [
        _futures(i) for i in range(1, 15)
    ]
    out = compose_opening_edition(
        deck, None, requested_token=None, requested_policy=POLICY, now=NOW
    )
    assert out.status == COMPOSED and out.usable
    assert out.withheld == []
    assert out.refusals == []
    assert out.pin_withheld == []
    assert out.detail == "composed: 1 restricted card(s) left the opening"
    assert [feed_edition_member(c) for c in out.items] == (
        [f"futures:{i}" for i in range(10)]
        + ["event:100"]
        + [f"futures:{i}" for i in range(10, 15)]
    )


# ---------------------------------------------------------------------------
# 4. Duplicate keeps first copy; bad bundle member holds back bundle;
#    refused held deck expires & restarts; holding back every card -> unavailable
# ---------------------------------------------------------------------------


def test_duplicate_identity_keeps_first_copy_and_withholds_second():
    first = _futures(42, score=99.0)
    second = _futures(42, score=50.0)
    deck = [first, _futures(1), _futures(2), second, _futures(3)]
    out = compose_opening_edition(
        deck, None, requested_token=None, requested_policy=POLICY, now=NOW
    )
    assert out.status == COMPOSED and out.usable
    assert [feed_edition_member(c) for c in out.items] == [
        "futures:42",
        "futures:1",
        "futures:2",
        "futures:3",
    ]
    assert out.items[0] is first
    assert len(out.withheld) == 1
    assert out.withheld[0]["identity"] == "futures:42"
    assert out.withheld[0]["seat"] == 4
    assert out.withheld[0]["refusal_class"] == REFUSAL_INVALID_IDENTITY


def test_bad_bundle_member_withholds_the_bundle_and_serves_remaining_cards():
    bad_bundle = {
        "type": "bundle",
        "score": 95.0,
        "data": {
            "id": "broken-bundle",
            "items": [{"type": "unsupported_child", "data": {"id": 1}}],
        },
    }
    deck = [_futures(0), bad_bundle] + [_futures(i) for i in range(1, 12)]
    out = compose_opening_edition(
        deck, None, requested_token=None, requested_policy=POLICY, now=NOW
    )
    assert out.status == COMPOSED and out.usable
    assert [feed_edition_member(c) for c in out.items] == [
        f"futures:{i}" for i in range(12)
    ]
    assert len(out.withheld) == 1
    assert out.withheld[0]["identity"] == "bundle:broken-bundle"
    assert out.withheld[0]["seat"] == 2
    assert out.withheld[0]["refusal_class"] == REFUSAL_MALFORMED_GROUP


def test_refused_held_deck_expires_and_restarts_reader_at_page_one():
    initial_deck = [_futures(0), _event(500, status="scheduled", start=NOW + timedelta(hours=2))] + [
        _futures(i) for i in range(1, 12)
    ]
    minted = compose_opening_edition(
        initial_deck, None, requested_token=None, requested_policy=POLICY, now=NOW
    )
    assert minted.status == COMPOSED and minted.usable

    # On the next request, event:500 has conflicting typed fields (live while
    # commence_time is still in the future).
    current_deck = copy.deepcopy(initial_deck)
    current_deck[1]["data"]["status"] = "live"
    current_deck[1]["data"]["commence_time"] = (NOW + timedelta(hours=2)).isoformat()

    recomposed = compose_opening_edition(
        current_deck,
        minted.manifest,
        requested_token=minted.token,
        requested_policy=POLICY,
        now=NOW + timedelta(minutes=1),
    )
    assert recomposed.status == COMPOSED and recomposed.usable
    assert recomposed.edition_status == EDITION_STATUS_EXPIRED
    assert recomposed.seating_expiry == SEATING_EXPIRY_OPENING_ORDER
    assert recomposed.retire_requested is True
    assert recomposed.restart_at_page_one is True
    assert recomposed.token != minted.token
    assert "event:500" not in [feed_edition_member(c) for c in recomposed.items]
    assert [w["identity"] for w in recomposed.withheld] == ["event:500"]
    assert [w["identity"] for w in recomposed.pin_withheld] == ["event:500"]


def test_holding_back_every_card_returns_unavailable():
    bad1 = _conflicted_schwab_tournament()
    bad2 = _event(777, status="live", start=NOW + timedelta(hours=3))
    out = compose_opening_edition(
        [bad1, bad2], None, requested_token=None, requested_policy=POLICY, now=NOW
    )
    assert out.status == UNSUPPORTED and not out.usable
    assert out.token is None and out.manifest is None
    assert [w["identity"] for w in out.withheld] == [
        "tournament:pgachamp_charles_schwab_cup_championship",
        "event:777",
    ]


# ---------------------------------------------------------------------------
# 5. Route serves & logs with §5 fields and 1-per-minute-per-offender rate limit
# ---------------------------------------------------------------------------


async def test_route_serves_deck_when_one_card_withheld_and_logs_offender_with_section5_fields(
    client, monkeypatch, seated, caplog
):
    _install(monkeypatch, _DictRedis())
    seated.now = NOW
    deck = [_futures(i, score=100 - i) for i in range(12)]
    deck.insert(7, _conflicted_schwab_tournament())
    _plant(monkeypatch, deck)

    with caplog.at_level(logging.WARNING, logger="app.routes.feed"):
        resp, body = await _get(client, offset=0)
        await _drain()

    assert resp.status_code == 200
    assert body["cache"]["status"] == "miss"
    assert body["total"] == 12
    assert _ids(body["items"])[:OPENING_SEATS] == [
        f"futures:{i}" for i in range(OPENING_SEATS)
    ]
    assert "tournament:pgachamp_charles_schwab_cup_championship" not in _ids(
        body["items"]
    )

    warnings = [
        r
        for r in caplog.records
        if getattr(r, "opening_outcome", None) is not None
    ]
    assert len(warnings) == 1
    rec = warnings[0].opening_outcome
    assert rec["reason"] == "opening_card_withheld"
    assert rec["path"] == "fresh_build"
    assert rec["deck_kind"] == "current"
    assert rec["reader_kind"] == "anonymous"
    assert rec["refusal_class"] == REFUSAL_LIFECYCLE_CONFLICT
    assert (
        rec["offender_identity"]
        == "tournament:pgachamp_charles_schwab_cup_championship"
    )
    assert rec["offender_seat"] == 8
    assert rec["offender_kind"] == "tournament"
    assert rec["offender_fields"]["schedule_status"] == "in_progress"
    assert rec["offender_fields"]["start_date"] == "2026-11-12T00:00:00+00:00"
    assert rec["offender_fields"]["end_date"] == "2026-11-15T00:00:00+00:00"
    assert rec["request_clock"] == NOW.isoformat()
    assert rec["resolution"] == "withheld_and_seated"
    assert rec["input_count"] == 13
    assert rec["withheld_count"] == 1
    assert rec["served_count"] == 12
    assert 0 < len(rec["detail"]) <= 500
    assert "tournament:pgachamp_charles_schwab_cup_championship" in warnings[0].getMessage()


async def test_rate_limit_logs_at_most_once_per_minute_per_offender_identity(
    client, monkeypatch, seated, caplog
):
    fake_mono = {"t": 1000.0}
    monkeypatch.setattr(feed_module, "_opening_offender_log_clock", lambda: fake_mono["t"])
    _install(monkeypatch, _DictRedis())
    seated.now = NOW

    deck_a = [_conflicted_schwab_tournament()] + [_futures(i) for i in range(12)]
    holder = _plant(monkeypatch, deck_a)

    with caplog.at_level(logging.WARNING, logger="app.routes.feed"):
        # Request 1 at t=1000s: logs offender A
        await _get(client, offset=0)
        # Request 2 at t=1030s (within 60s): cached_deck path for same offender A -> suppressed
        fake_mono["t"] = 1030.0
        await _get(client, offset=2, limit=20)
        # Request 3 at t=1040s with a DIFFERENT offender B: logs immediately
        other_conflict = _event(888, status="live", start=NOW + timedelta(hours=4))
        holder["deck"] = [other_conflict] + [_futures(i) for i in range(12)]
        await _get(client, offset=0, limit=10)
        # Request 4 at t=1061s (after 60s window for offender A): logs offender A again
        fake_mono["t"] = 1061.0
        holder["deck"] = deck_a
        await _get(client, offset=0, limit=5)

    logged = [
        (r.opening_outcome["offender_identity"], r.opening_outcome["path"])
        for r in caplog.records
        if getattr(r, "opening_outcome", None) is not None
    ]
    assert logged == [
        ("tournament:pgachamp_charles_schwab_cup_championship", "fresh_build"),
        ("event:888", "fresh_build"),
        ("tournament:pgachamp_charles_schwab_cup_championship", "fresh_build"),
    ]


# ---------------------------------------------------------------------------
# 6. Pre-warm reports held-back cards and escalates (warn on change, error once
#    after 15m, no "keeping last-good" on empty seated shape)
# ---------------------------------------------------------------------------


def test_prewarm_reports_withheld_card_warns_on_change_and_errors_once_after_15_minutes(
    monkeypatch, caplog
):
    fake_clock = {"t": 2_000_000.0}
    monkeypatch.setattr(pcp, "_prewarm_opening_clock", lambda: fake_clock["t"])

    @asynccontextmanager
    async def _fake_session():
        yield MagicMock()

    current_opening_scope = {
        "withheld": ["tournament:pgachamp_charles_schwab_cup_championship"],
        "class": REFUSAL_LIFECYCLE_CONFLICT,
        "detail": "unexempt lifecycle conflict(s) in the candidate opening",
        "usable": True,
    }

    async def _fake_get_feed(**kwargs):
        req = kwargs["request"]
        assert req.scope.get(FEED_PREWARM_SCOPE_KEY) is True
        req.scope[FEED_PREWARM_KEY_SCOPE_KEY] = "feed_cache:discover_test"
        req.scope[FEED_PREWARM_OPENING_SCOPE_KEY] = dict(current_opening_scope)
        return {
            "items": [_futures(i) for i in range(10)],
            "total": 10,
            "cache": {"status": "miss", "built_at": fake_clock["t"]},
        }

    shape = dict(pcp.FEED_PREWARM_SHAPES[0])
    rc = MagicMock()

    import asyncio

    with patch("app.tasks.base.get_task_session", _fake_session), patch(
        "app.routes.feed.get_feed", _fake_get_feed
    ), caplog.at_level(logging.WARNING, logger="app.tasks.precompute_category_pages"):
        # Pass 1 at t=0: held-back set appears -> 1 warning, 0 errors
        res1 = asyncio.run(pcp._prewarm_feed_shape(shape, rc))
        assert res1["outcome"] == "ok"
        assert res1["opening"] == {
            "withheld": ["tournament:pgachamp_charles_schwab_cup_championship"],
            "class": REFUSAL_LIFECYCLE_CONFLICT,
            "detail": "unexempt lifecycle conflict(s) in the candidate opening",
            "since": datetime.fromtimestamp(2_000_000.0, tz=timezone.utc).isoformat(),
        }
        warns = [r for r in caplog.records if r.levelno == logging.WARNING]
        errs = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert len(warns) == 1 and len(errs) == 0

        # Pass 2 at t=+5m (300s): same held-back set -> no new warning, no error yet
        caplog.clear()
        fake_clock["t"] += 300.0
        res2 = asyncio.run(pcp._prewarm_feed_shape(shape, rc))
        assert res2["opening"]["since"] == res1["opening"]["since"]
        assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []

        # Pass 3 at t=+15m (900s): same held-back set -> 1 ERROR logged
        caplog.clear()
        fake_clock["t"] += 600.0
        res3 = asyncio.run(pcp._prewarm_feed_shape(shape, rc))
        assert res3["opening"]["since"] == res1["opening"]["since"]
        errs = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert len(errs) == 1
        assert "still held back after 900s" in errs[0].getMessage()

        # Pass 4 at t=+20m (1200s): same held-back set -> error NOT repeated
        caplog.clear()
        fake_clock["t"] += 300.0
        asyncio.run(pcp._prewarm_feed_shape(shape, rc))
        assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []

        # Pass 5 at t=+21m: held-back set clears -> 1 warning on change, opening.withheld == []
        caplog.clear()
        fake_clock["t"] += 60.0
        current_opening_scope = {
            "withheld": [],
            "class": None,
            "detail": None,
            "usable": True,
        }
        res5 = asyncio.run(pcp._prewarm_feed_shape(shape, rc))
        assert res5["opening"] == {
            "withheld": [],
            "class": None,
            "detail": None,
            "since": None,
        }
        warns = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warns) == 1
        assert "cleared" in warns[0].getMessage()


def test_prewarm_empty_opening_unsupported_does_not_claim_keeping_last_good(caplog):
    @asynccontextmanager
    async def _fake_session():
        yield MagicMock()

    async def _refused_get_feed(**kwargs):
        req = kwargs["request"]
        req.scope[FEED_PREWARM_OPENING_SCOPE_KEY] = {
            "withheld": ["event:999"],
            "class": REFUSAL_LIFECYCLE_CONFLICT,
            "detail": "all cards withheld",
            "usable": False,
        }
        return {
            "items": [],
            "total": 0,
            "cache": {
                "status": "unavailable",
                "reason": "opening_unsupported",
                "ttl_seconds": 0,
                "stale_ttl_seconds": 0,
            },
        }

    import asyncio

    with patch("app.tasks.base.get_task_session", _fake_session), patch(
        "app.routes.feed.get_feed", _refused_get_feed
    ), caplog.at_level(logging.WARNING, logger="app.tasks.precompute_category_pages"):
        res = asyncio.run(
            pcp._prewarm_feed_shape(dict(pcp.FEED_PREWARM_SHAPES[0]), MagicMock())
        )

    assert res["outcome"] == "empty"
    assert res["empty_reason"] == "opening_unsupported"
    assert res["opening"]["withheld"] == ["event:999"]
    empty_logs = [
        r.getMessage()
        for r in caplog.records
        if "produced an EMPTY feed" in r.getMessage()
    ]
    assert len(empty_logs) == 1
    assert "keeping last-good" not in empty_logs[0]
    assert "seated shape has no last-good fallback" in empty_logs[0]
