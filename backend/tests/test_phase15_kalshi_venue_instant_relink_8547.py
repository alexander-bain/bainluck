"""A doubleheader's Kalshi game market goes to the game its TICKER times (#8547).

**SHIP: Friday's Orioles @ Yankees game 1 stops using game 2's Kalshi market.**
(Pillars: MATCHING / TRUTH.)

Measured on production 2026-09-25 ~12:15Z:

    15318575  baseball_mlb  game 1  20:05Z  ESPN 401817088
              Kalshi KXMLBGAME-26SEP251905BALNYY (fm 62013568) ✗
              win_probability_sources.kalshi = 0.575, market_id 62013568
    15318665  baseball_mlb  game 2  23:05Z  StatPal 366768   no Kalshi market

At 11:32Z the twin step merged the old game 2 row into game 1 and carried the
ticker with it. 19:05 ET is 23:05Z, exactly 3.0h from game 1, which
``_ticker_date_conflicts_with_event``'s strict ``>`` keeps. #8560's
venue-instant arm was Polymarket only, so nothing moved it, and game 1 blended
game 2's Kalshi price.

WHAT EACH TEST DEFENDS:

* the ship: the ticker moves to game 2 AND game 1 stops carrying a ``kalshi``
  reading (``test_the_ticker_instant_moves_the_market_and_game_1_stops_blending_it``);
* game 1 keeps its ``kalshi`` key when a Kalshi market of its own is still
  linked (``test_game_1_keeps_its_kalshi_reading_when_its_own_ticker_remains``);
* the entry bound, both sides of 90 minutes, and no finder query below it;
* the destination bound: 15 minutes is in, 20 is out, two rows is no pick;
* a retired row at the ticker's minute is never a destination;
* only a ``WRONG_GAME_PREFIXES`` ticker with HHMM in a covered league enters:
  a prop, a date-only ticker and an esports ticker are left alone;
* the #5544 phantom/retired callers still never move a Kalshi market
  (``test_the_finder_refuses_kalshi_without_the_venue_instant_flag``).
"""

from datetime import timedelta
from types import SimpleNamespace

import pytest

from tests.test_phase15_venue_instant_relink_8547 import (
    GAME_1,
    GAME_2,
    _AsyncShim,
    _event,
    _new_rail,
    _on,
    _run_phase15,
)

TICKER = "KXMLBGAME-26SEP251905BALNYY"  # 19:05 ET = 23:05Z = GAME_2
KALSHI_NAME = "Baltimore vs New York Y"


def _kalshi(session, event, *, external_id=TICKER, sport_id=None):
    from app.models.models import FuturesMarket

    m = FuturesMarket(
        source="kalshi", external_id=external_id, name=KALSHI_NAME,
        category="championship", status="open", event_id=event.id,
        sport_id=sport_id or event.sport_id, llm_sport_category="baseball",
    )
    session.add(m)
    session.flush()
    return m


def _wps(session, event):
    from app.models.models import Event

    session.expire_all()
    return session.get(Event, event.id).win_probability_sources or {}


def _specimen(session, mlb, *, game_2_at=GAME_2, game_2_status="scheduled"):
    """Game 1 carrying game 2's ticker and its `kalshi` reading; game 2 bare."""
    game_1 = _event(session, mlb, GAME_1, espn_id="401817088")
    game_1.win_probability_sources = {
        "kalshi": {"value": 0.575, "market_id": None, "source_market_id": TICKER},
        "betting": {"value": 0.56},
    }
    game_2 = _event(session, mlb, game_2_at, status=game_2_status)
    k = _kalshi(session, game_1)
    game_1.win_probability_sources["kalshi"]["market_id"] = k.id
    session.commit()
    return game_1, game_2, k


@pytest.mark.asyncio
async def test_the_ticker_instant_moves_the_market_and_game_1_stops_blending_it():
    """🔴 THE SHIP. 62013568 moves to game 2; game 1's `kalshi` key is gone."""
    session, mlb = _new_rail()
    game_1, game_2, k = _specimen(session, mlb)

    stats, _ = await _run_phase15(session)

    assert _on(session, k) == [game_2.id], (
        f"game 1 = {game_1.id}, game 2 = {game_2.id}: {TICKER} (23:05Z) is game 2's"
    )
    wps = _wps(session, game_1)
    assert "kalshi" not in wps, f"game 1 still blends game 2's Kalshi price: {wps}"
    assert wps.get("betting") == {"value": 0.56}, "only the Kalshi key may go"
    assert stats["funnel"]["phase15_venue_instant_relinked"] == 1
    assert stats["phantom_blend_sources_pruned"] == 1
    # A same-teams move is not a mislink and deletes no curve.
    assert stats["funnel"]["mislink_fixed"] == 0
    assert stats["orphaned_snapshots_deleted"] == 0


@pytest.mark.asyncio
async def test_game_1_keeps_its_kalshi_reading_when_its_own_ticker_remains():
    """Game 1's own 16:05 ET ticker stays, so its `kalshi` key is not an orphan."""
    session, mlb = _new_rail()
    game_1, game_2, k = _specimen(session, mlb)
    own = _kalshi(session, game_1, external_id="KXMLBGAME-26SEP251605BALNYY")
    session.commit()

    stats, _ = await _run_phase15(session)

    assert _on(session, k, own) == [game_2.id, game_1.id]
    assert "kalshi" in _wps(session, game_1)
    assert stats.get("phantom_blend_sources_pruned", 0) == 0


@pytest.mark.asyncio
async def test_drift_under_ninety_minutes_is_left_alone_without_a_query():
    """Linked 89 minutes off the ticker's instant: no move, no finder call."""
    session, mlb = _new_rail()
    near = _event(session, mlb, GAME_2 - timedelta(minutes=89))
    _event(session, mlb, GAME_2)
    k = _kalshi(session, near)
    session.commit()

    stats, spy = await _run_phase15(session)

    assert _on(session, k) == [near.id]
    spy.assert_not_awaited()
    assert stats["funnel"].get("phase15_venue_instant_relinked", 0) == 0


@pytest.mark.asyncio
async def test_the_entry_bound_is_inclusive_at_ninety_minutes():
    """Linked exactly 90 minutes off: the arm enters and the ticker's row wins."""
    session, mlb = _new_rail()
    off = _event(session, mlb, GAME_2 - timedelta(minutes=90))
    at_ticker = _event(session, mlb, GAME_2)
    k = _kalshi(session, off)
    session.commit()

    await _run_phase15(session)

    assert _on(session, k) == [at_ticker.id]


@pytest.mark.asyncio
async def test_a_row_fifteen_minutes_from_the_ticker_is_a_destination():
    """The destination bound is inclusive at 15 minutes."""
    session, mlb = _new_rail()
    game_1, game_2, k = _specimen(
        session, mlb, game_2_at=GAME_2 + timedelta(minutes=15),
    )

    await _run_phase15(session)

    assert _on(session, k) == [game_2.id]


@pytest.mark.asyncio
async def test_no_row_at_the_ticker_minute_leaves_the_link():
    """Game 2 held 20 minutes off the ticker: outside 15, nothing moves or prunes."""
    session, mlb = _new_rail()
    game_1, _g2, k = _specimen(session, mlb, game_2_at=GAME_2 + timedelta(minutes=20))

    stats, spy = await _run_phase15(session)

    assert _on(session, k) == [game_1.id]
    spy.assert_awaited()
    assert stats["funnel"]["phase15_venue_instant_left_alone"] == 1
    assert "kalshi" in _wps(session, game_1)


@pytest.mark.asyncio
async def test_two_rows_at_the_ticker_minute_leave_the_link():
    """Two rows for game 2 (a twin pair): the finder cannot pick, so it does not."""
    session, mlb = _new_rail()
    game_1, _g2, k = _specimen(session, mlb)
    _event(session, mlb, GAME_2 + timedelta(minutes=1))
    session.commit()

    stats, _ = await _run_phase15(session)

    assert _on(session, k) == [game_1.id]
    assert stats["funnel"].get("phase15_venue_instant_relinked", 0) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("retired", ["voided", "merged"])
async def test_a_retired_row_at_the_ticker_minute_is_not_a_destination(retired):
    """Only a retired row sits at 23:05Z: it is off every page, so nothing moves."""
    session, mlb = _new_rail()
    game_1, _g2, k = _specimen(session, mlb, game_2_status=retired)

    stats, _ = await _run_phase15(session)

    assert _on(session, k) == [game_1.id]
    assert stats["funnel"].get("phase15_venue_instant_relinked", 0) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("ticker", [
    "KXMLBTOTAL-26SEP251905BALNYY-8",  # a prop: not a WRONG_GAME_PREFIXES series
    "KXMLBGAME-26SEP25BALNYY",  # date-only: no minute to compare
])
async def test_a_ticker_without_a_game_minute_never_enters(ticker):
    session, mlb = _new_rail()
    game_1 = _event(session, mlb, GAME_1, espn_id="401817088")
    _event(session, mlb, GAME_2)
    k = _kalshi(session, game_1, external_id=ticker)
    session.commit()

    stats, spy = await _run_phase15(session)

    assert _on(session, k) == [game_1.id]
    spy.assert_not_awaited()


def test_kalshi_ticker_helpers():
    from app.tasks.prediction_market_matching import (
        _kalshi_game_ticker_instant,
        _kalshi_game_ticker_league,
        _market_venue_instant,
        _venue_instant_disowns_link,
    )

    def k(ticker, source="kalshi"):
        return SimpleNamespace(source=source, external_id=ticker, market_metadata={})

    assert _kalshi_game_ticker_instant(k(TICKER)) == GAME_2
    assert _market_venue_instant(k(TICKER)) == GAME_2
    assert _kalshi_game_ticker_league(k(TICKER)) == "baseball_mlb"
    # Esports game tickers carry HHMM but no covered league: no destination.
    assert _kalshi_game_ticker_league(k("KXCS2GAME-26SEP251905NAVFAZ")) is None
    # The ticker only speaks for Kalshi rows.
    assert _kalshi_game_ticker_instant(k(TICKER, source="polymarket")) is None
    assert _kalshi_game_ticker_instant(k(None)) is None

    assert _venue_instant_disowns_link(
        k(TICKER), SimpleNamespace(commence_time=GAME_1),
    ) is True
    assert _venue_instant_disowns_link(
        k(TICKER), SimpleNamespace(commence_time=GAME_2),
    ) is False


@pytest.mark.asyncio
async def test_the_finder_refuses_kalshi_without_the_venue_instant_flag():
    """The #5544 phantom and retired-row callers stay Polymarket only."""
    from app.tasks.prediction_market_matching import (
        _venue_confirmed_covered_fixture,
        extract_matchup_with_ticker_fallback,
    )

    session, mlb = _new_rail()
    game_1, game_2, k = _specimen(session, mlb)
    matchup = extract_matchup_with_ticker_fallback(KALSHI_NAME, external_id=TICKER)
    shim = _AsyncShim(session)

    assert await _venue_confirmed_covered_fixture(shim, matchup, k, game_1) is None
    assert await _venue_confirmed_covered_fixture(
        shim, matchup, k, game_1,
        window=timedelta(minutes=15), exclude_retired=True, allow_kalshi_ticker=True,
    ) == {"event_id": game_2.id, "sport_id": mlb.id}
