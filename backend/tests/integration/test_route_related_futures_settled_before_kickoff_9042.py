"""#9042 — a market settled before this game started is not its season context.

`/events/15315689` (Lightning–Panthers, Sep 26, final) printed "Andrei
Vasilevskiy · Hart Trophy 1%" from market 344, the 2025-26 Hart, `resolved` on
Jun 30. `rf_status_filter` admits resolved/closed markets for a finished game
with no date bound. #9012 (the #9008 fix) made it visible: it drops the current
Hart's refused leg before the dedup that used to hide the resolved sibling.

The bound is `_settled_before_the_game`, applied per event at the rail's row
loop and at the series cards. It isn't in the SQL filter because season
discovery is cached per sport and shared by every finished game.

SYNTHETIC ROWS, LABELLED: a football fixture so the harness's sport net
applies unchanged (the #9008 file's shape); every id and price is invented.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routes.events import _settled_before_the_game
from tests.integration.test_route_related_futures import _make_market, _MockResult
from tests.integration.test_route_related_futures_cfl_7851 import (
    _football_event,
    _get,
    _outcome,
)

AWARD, SERIES = 90420001, 90420002
DUKE_AWARD, STAN_AWARD = 90421001, 90421002
DUKE_SERIES, STAN_SERIES = 90422001, 90422002
_EVENT_IDS = iter(range(9042001, 9042100))


def _market(id, name):
    m = _make_market(id=id, name=name, source="polymarket")
    m.event_id = None
    m.group_id = None
    m.external_id = f"0x{id}"
    m.market_metadata = {}
    m.mutually_exclusive = False
    return m


def _session(event, boards, candidates, series_outcomes):
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()

    async def mock_execute(stmt, *args, **kwargs):
        s = str(stmt).lower()
        if "from events" in s:
            return _MockResult(scalar=event)
        if "select sports.id" in s:
            return _MockResult(rows=[SimpleNamespace(id=11)])
        if "from teams" in s:
            return _MockResult(rows=[], first=None)
        if "order by futures_outcomes.market_id" in s:
            return _MockResult(scalar_rows=list(series_outcomes))
        if "from futures_outcomes" in s:
            return _MockResult(scalar_rows=list(candidates))
        if "from futures_odds_snapshots" in s:
            return _MockResult(rows=[])
        if "from line_movement_analyses" in s:
            return _MockResult(scalar=None)
        if "futures_markets.mutually_exclusive" in s and "from futures_markets" in s:
            return _MockResult(scalar_rows=list(boards))
        if "select futures_markets.id" in s:
            if "order by futures_markets.market_tier" in s:
                return _MockResult(rows=[SimpleNamespace(id=AWARD, market_tier=1)])
            if "limit" in s:  # the series detection read
                return _MockResult(rows=[SimpleNamespace(id=SERIES)])
            return _MockResult(rows=[])
        return _MockResult()

    session.execute = AsyncMock(side_effect=mock_execute)
    return session


async def _body(monkeypatch, *, event_status, award=None, series=None):
    """`award` / `series` = (status, resolution_date offset from kickoff, or None)."""
    event_id = next(_EVENT_IDS)
    event = _football_event(
        event_id, "Duke Blue Devils", "Stanford Cardinal", sport_key="americanfootball_ncaaf"
    )
    event.status = event_status
    award_m = _market(AWARD, "College Football Playoff Champion")
    series_m = _market(SERIES, "Duke vs Stanford Series Winner")
    for m, spec in ((award_m, award), (series_m, series)):
        if spec is not None:
            m.status = spec[0]
            m.resolution_date = None if spec[1] is None else event.commence_time + spec[1]
    candidates = [
        _outcome(DUKE_AWARD, award_m, "Duke Blue Devils", 0.21),
        _outcome(STAN_AWARD, award_m, "Stanford Cardinal", 0.09),
    ]
    series_outcomes = [
        _outcome(DUKE_SERIES, series_m, "Duke Blue Devils", 0.70),
        _outcome(STAN_SERIES, series_m, "Stanford Cardinal", 0.30),
    ]

    async def no_refusal(db, board):
        return set()

    monkeypatch.setattr("app.routes.league_futures._page_withheld_outcome_ids", no_refusal)
    return await _get(
        monkeypatch, _session(event, [award_m, series_m], candidates, series_outcomes), event_id
    )


def _rail_ids(body):
    return {r["outcome_id"] for r in body["home_team_futures"] + body["away_team_futures"]}


def _series_ids(body):
    return {m["market_id"] for m in body["series_markets"]}


LAST_SEASON = timedelta(days=-88)  # 344: resolved Jun 30, game Sep 26
AFTER_KICKOFF = timedelta(hours=3)  # a market this game settled


@pytest.mark.asyncio
@pytest.mark.parametrize("event_status", ["completed", "scheduled"])
async def test_control_open_markets_serve_both_rail_rows_and_the_series_card(monkeypatch, event_status):
    """Without this, every refusal below could pass on a rail that is never built."""
    body = await _body(monkeypatch, event_status=event_status)
    assert _rail_ids(body) == {DUKE_AWARD, STAN_AWARD}
    assert _series_ids(body) == {SERIES}


@pytest.mark.asyncio
async def test_last_seasons_resolved_award_leaves_a_finished_games_rail(monkeypatch):
    body = await _body(monkeypatch, event_status="completed", award=("resolved", LAST_SEASON))
    assert _rail_ids(body) == set()
    assert body["total_count"] == 0
    # The series card was not settled before the game, so it stays.
    assert _series_ids(body) == {SERIES}


@pytest.mark.asyncio
async def test_a_closed_market_settled_before_kickoff_leaves_too(monkeypatch):
    body = await _body(monkeypatch, event_status="completed", award=("closed", LAST_SEASON))
    assert _rail_ids(body) == set()


@pytest.mark.asyncio
async def test_a_market_this_game_settled_still_shows_on_the_finished_game(monkeypatch):
    """The reason `rf_status_filter` admits resolved markets at all: a clinching game."""
    body = await _body(monkeypatch, event_status="completed", award=("resolved", AFTER_KICKOFF))
    assert _rail_ids(body) == {DUKE_AWARD, STAN_AWARD}


@pytest.mark.asyncio
async def test_a_resolved_market_with_no_resolution_date_is_kept(monkeypatch):
    body = await _body(monkeypatch, event_status="completed", award=("resolved", None))
    assert _rail_ids(body) == {DUKE_AWARD, STAN_AWARD}


@pytest.mark.asyncio
async def test_an_open_market_past_its_resolution_date_is_not_this_rules_to_refuse(monkeypatch):
    """Stale-open (#1113) is a different defect; this bound reads `status` first."""
    body = await _body(monkeypatch, event_status="completed", award=("open", LAST_SEASON))
    assert _rail_ids(body) == {DUKE_AWARD, STAN_AWARD}


@pytest.mark.asyncio
async def test_a_series_settled_before_kickoff_leaves_the_series_cards(monkeypatch):
    body = await _body(monkeypatch, event_status="completed", series=("resolved", LAST_SEASON))
    assert _series_ids(body) == set()
    assert _rail_ids(body) == {DUKE_AWARD, STAN_AWARD}


# ── the predicate, at its edges ─────────────────────────────────────────────

KICKOFF = datetime(2026, 9, 26, 23, 0, tzinfo=timezone.utc)


def _m(status, resolution_date):
    return SimpleNamespace(status=status, resolution_date=resolution_date)


def test_the_specimen_344_is_settled_before_the_game():
    assert _settled_before_the_game(
        _m("resolved", datetime(2026, 6, 30, 14, 0, tzinfo=timezone.utc)), KICKOFF
    )


def test_resolving_exactly_at_kickoff_is_not_before_it():
    assert not _settled_before_the_game(_m("resolved", KICKOFF), KICKOFF)


def test_naive_timestamps_are_read_as_utc_on_either_side():
    naive_june = datetime(2026, 6, 30, 14, 0)
    assert _settled_before_the_game(_m("resolved", naive_june), KICKOFF)
    assert _settled_before_the_game(
        _m("closed", naive_june.replace(tzinfo=timezone.utc)), KICKOFF.replace(tzinfo=None)
    )


@pytest.mark.parametrize("status", ["open", None, "suspended"])
def test_only_resolved_and_closed_are_asked(status):
    assert not _settled_before_the_game(
        _m(status, datetime(2026, 6, 30, tzinfo=timezone.utc)), KICKOFF
    )


def test_an_unknown_kickoff_keeps_the_row():
    assert not _settled_before_the_game(
        _m("resolved", datetime(2026, 6, 30, tzinfo=timezone.utc)), None
    )
