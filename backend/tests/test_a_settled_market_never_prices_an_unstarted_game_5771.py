"""#5771 — a market our own row says is SETTLED may not price a game that has not started.

## The specimen, read on production 2026-09-13 16:4xZ

`/api/events/15298125/game-markets` served three legs off market 60482102 —
`Sevilla 0.99 · Tie 0.01 · Valencia 0.01`, `observed_at` stamped one minute before
the read, `is_winner True/False/False`, `resolution_source 'api_settlement'`. That
market's own row:

    id 60482102 · kalshi · KXLALIGAGAME-26SEP13SEVVCF
    status   = 'resolved'
    settled_at = 2026-09-11 22:49:23Z
    event 15298125 · commence_time 2026-09-13 19:00Z · status 'scheduled' · completed_at NULL

The page (`artifacts/AFTER-5771-sevilla-valencia-390-1642Z.png`, 390px) read
**"Starts in 2h 17m"** over an **Additional Markets** card saying **"Sevilla 99%"**.
A settlement stamped two days BEFORE kickoff cannot be that fixture's live price,
and saying so needs neither the venue nor a score — the two rows refute each other.

## Why this file exists beside a fix that is already live

#5820's clause in `admissible_as_blend_speaker` refuses exactly this market as the
BLEND's speaker, and it works: both specimens' heroes now read honestly (`No price`
on 15310861, `59% – 41%` here). It never touched the `/game-markets` rail, so the
identical settlement price went on being served as a current market row one card
below the hero that had refused it. Same predicate, same direction, second rail.

## The scope is "has not started", and the two directions it does NOT move

Measured over the 7-day linked window (2026-09-13 16:5xZ), events holding a
`status='resolved'` market:

    not started          ->    36 events /    57 markets   <- this fix
    started, no result   -> 2,080 events / 8,867 markets   <- deliberately untouched
    completed            ->   550 events / 10,953 markets  <- must not move (gotcha #43)

The middle bucket is mostly a live game's genuinely-settled sub-market — a first
set that finished while the match plays on. That is real information; it wants
GRADING, not hiding, and a withdrawal there would destroy it. The last bucket is
"settled means settled": a completed event's rows keep both their prices and their
verdicts, which is the direction this file pins hardest, because a gate that
over-reaches into it silently deletes every settled page on the site.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.routes.events import (
    _event_is_really_finished,
    _settled_market_prices_an_unstarted_game,
)
from app.services.database import get_db, get_db_rw
from tests.integration.test_route_events_seeded import (
    _make_event,
    _make_event_detail_session,
    _make_futures_market,
    _make_outcome,
)

NOW = datetime(2026, 9, 13, 16, 45, tzinfo=timezone.utc)


def _event(*, commence, status="scheduled", completed_at=None):
    event = MagicMock()
    event.commence_time = commence
    event.status = status
    event.completed_at = completed_at
    return event


def _market(status="resolved"):
    market = MagicMock()
    market.status = status
    return market


def _outcome(is_winner=False):
    outcome = MagicMock()
    outcome.is_winner = is_winner
    return outcome


# ── The specimen ────────────────────────────────────────────────────────────


def test_the_sevilla_specimen_is_withheld():
    """status='resolved', kickoff 2h15m away, no result — the row refutes itself."""
    assert _settled_market_prices_an_unstarted_game(
        _event(commence=NOW + timedelta(hours=2, minutes=15)),
        _market("resolved"),
        [_outcome(True), _outcome(False), _outcome(False)],
        NOW,
    )


def test_a_settled_but_still_open_kalshi_row_is_withheld_too():
    """Gotcha #33: Kalshi leaves settled markets `status='open'`.

    The grade is the second arm of `market_assigned_settled`, which is the whole
    reason this delegates to that predicate instead of testing `status` here.
    """
    assert _settled_market_prices_an_unstarted_game(
        _event(commence=NOW + timedelta(hours=2)),
        _market("open"),
        [_outcome(True), _outcome(False)],
        NOW,
    )


# ── The three directions it must not move ───────────────────────────────────


def test_a_completed_events_settled_market_is_kept():
    """Settled means settled. 10,953 markets on 550 completed events live here."""
    assert not _settled_market_prices_an_unstarted_game(
        _event(
            commence=NOW - timedelta(hours=3),
            status="completed",
            completed_at=NOW - timedelta(hours=1),
        ),
        _market("resolved"),
        [_outcome(True), _outcome(False)],
        NOW,
    )


def test_a_started_event_with_no_result_is_out_of_scope_and_unchanged():
    """The 2,080-event bucket: a live game's settled first set stays on the page."""
    assert not _settled_market_prices_an_unstarted_game(
        _event(commence=NOW - timedelta(minutes=40), status="live"),
        _market("resolved"),
        [_outcome(True), _outcome(False)],
        NOW,
    )


def test_an_ordinary_pre_kickoff_market_is_kept():
    """The population this gate must never touch: an open, ungraded, future fixture."""
    assert not _settled_market_prices_an_unstarted_game(
        _event(commence=NOW + timedelta(hours=2)),
        _market("open"),
        [_outcome(False), _outcome(False)],
        NOW,
    )


def test_an_event_with_no_commence_time_gets_no_opinion():
    """`commence_time IS NULL` is "unknown", not "in the future" — abstain."""
    assert not _settled_market_prices_an_unstarted_game(
        _event(commence=None),
        _market("resolved"),
        [_outcome(True)],
        NOW,
    )


def test_a_naive_commence_time_is_read_as_utc_and_never_raises():
    """The gate is asked of EVERY market on EVERY event, so it meets naive rows.

    CI caught this and the unit tests above did not, because they all build
    aware datetimes. Six tests across `test_proven_duplicate_2263.py` and
    `test_runs_map_is_made_of_runs_3995.py` raised `can't compare offset-naive
    and offset-aware datetimes` from inside a page build. Both directions are
    pinned here so the coercion cannot quietly become an abstention.
    """
    naive_past = _event(commence=NOW.replace(tzinfo=None) - timedelta(hours=3))
    assert not _settled_market_prices_an_unstarted_game(
        naive_past, _market("resolved"), [_outcome(True)], NOW
    )
    naive_future = _event(commence=NOW.replace(tzinfo=None) + timedelta(hours=3))
    assert _settled_market_prices_an_unstarted_game(
        naive_future, _market("resolved"), [_outcome(True)], NOW
    )


def test_the_corrupt_completed_with_future_commence_shape_is_withheld():
    """A row claiming `completed` while its kickoff is in the FUTURE (#46 / gotcha #32).

    `_event_is_really_finished` already refuses to read that shape as settled — it
    requires the start time to have passed — so the gate sees an unstarted event
    and withholds. Pinned because it is the one input where the two clauses could
    be read as disagreeing, and the safe direction is the one taken.
    """
    corrupt = _event(
        commence=NOW + timedelta(hours=5),
        status="completed",
        completed_at=NOW - timedelta(hours=1),
    )
    assert not _event_is_really_finished(corrupt, NOW)
    assert _settled_market_prices_an_unstarted_game(
        corrupt, _market("resolved"), [_outcome(True)], NOW
    )


# ── The route actually asks it (a correct helper nobody calls changes nothing) ──


def _sevilla_seed(*, market_status, is_winner):
    """The Sevilla shape: one Kalshi market, three legs, all landing in `other`."""
    event = _make_event(
        id=15298125,
        home_team="Sevilla",
        away_team="Valencia",
        status="scheduled",
        sport_key="soccer_spain_la_liga",
        home_score=None,
        away_score=None,
    )
    # Two hours out, read from the clock at call time so the fixture can never
    # expire into the past (gotcha #44 — offset first, never a literal date).
    event.commence_time = datetime.now(timezone.utc) + timedelta(hours=2)
    event.completed_at = None

    market = _make_futures_market(
        id=60482102, name="Sevilla vs Valencia", source="kalshi"
    )
    market.status = market_status
    market.event_id = event.id

    outcomes = [
        _make_outcome(
            id=1,
            market_id=market.id,
            name="Sevilla",
            probability=0.99,
            is_winner=is_winner,
            resolution_source="api_settlement" if is_winner else None,
        ),
        _make_outcome(
            id=2,
            market_id=market.id,
            name="Valencia",
            probability=0.01,
            is_winner=False,
            resolution_source="api_settlement" if is_winner else None,
        ),
        _make_outcome(
            id=3,
            market_id=market.id,
            name="Tie",
            probability=0.01,
            is_winner=False,
            resolution_source="api_settlement" if is_winner else None,
        ),
    ]
    return event, market, outcomes


async def _served_other(*, market_status, is_winner):
    """`GET /api/events/15298125/game-markets` over the seeded specimen."""
    from app.main import app
    from app.routes.events import _game_markets_cache

    _game_markets_cache.clear()
    event, market, outcomes = _sevilla_seed(
        market_status=market_status, is_winner=is_winner
    )
    mock_session = _make_event_detail_session(
        event=event, futures=[market], outcomes=outcomes
    )

    async def _mock_get_db():
        yield mock_session

    async def _mock_get_optional_user():
        return None

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_db_rw] = _mock_get_db
    app.dependency_overrides[get_optional_user] = _mock_get_optional_user
    try:
        with patch("app.main.init_db", new_callable=AsyncMock):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                resp = await ac.get("/api/events/15298125/game-markets")
        assert resp.status_code == 200, resp.text
        return resp.json().get("other") or []
    finally:
        _game_markets_cache.clear()
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_the_route_withholds_the_settled_pre_kickoff_legs():
    rows = await _served_other(market_status="resolved", is_winner=True)
    assert rows == [], (
        "a market our own row says is resolved is still priced on a fixture that "
        f"has not kicked off — the reader sees Sevilla 99% again: {rows}"
    )


@pytest.mark.asyncio
async def test_the_route_still_serves_the_same_legs_when_the_market_is_open():
    """The control that makes the assertion above non-vacuous.

    The same fixture, differing only in the thing under test: `status='open'`, no
    grade. Three rows reach `other`. If this one ever goes empty the test above is
    passing because the builder dropped the card for some unrelated reason — a
    classifier, the empty-book filter, the placeholder regex — and not because of
    this gate at all.
    """
    rows = await _served_other(market_status="open", is_winner=False)
    names = sorted(r["outcome_name"] for r in rows)
    assert names == ["Sevilla", "Tie", "Valencia"], rows
