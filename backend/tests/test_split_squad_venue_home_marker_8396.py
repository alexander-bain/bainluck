"""A split-squad market goes to the game the VENUE says it prices (#8396).

**SHIP: Saturday's Ottawa @ Montreal split-squad card and page show
Polymarket's price, not "No price yet".** (Pillar: MATCHING.)

Measured on production 2026-09-24 ~16:00Z. NHL preseason plays the same two
clubs in both cities at the same minute:

    real 15315787  icehockey_nhl  Montreal Canadiens (home) v Ottawa Senators
    real 15315788  icehockey_nhl  Ottawa Senators (home) v Montreal Canadiens
    shadow 15298006 icehockey_other "Senators"/"Canadiens"  voided
         holds Polymarket 936779's legs 59844801 / 62068185

Polymarket lists ONE of the two games — Gamma event 936779, "Split Squad:
Senators (A) vs. Canadiens (H)", ``teams[].ordering`` Canadiens=home,
Senators=away. #7904's retired-row relink goes through #5544's venue-confirmed
finder, which refused because it saw two fixtures. The venue had already said
which one: its home marker. Never the title's word order.

WHAT EACH TEST DEFENDS:

* the ship, both orientations, so "picked the first row" cannot pass
  (``test_the_venue_home_marker_moves_the_market_to_its_game``);
* no marker, no move — absent teams, a failed fetch, no stored event id
  (``test_a_missing_marker_still_refuses`` / ``..._fetch_failure_...`` /
  ``..._no_event_id_...``);
* a marker that fits neither row still refuses — a third club at home, or
  a third club away (``test_a_wrong_side_marker_still_refuses`` /
  ``test_a_marker_whose_away_club_is_on_neither_row_still_refuses``);
* a marker that fits BOTH rows (two rows for one game) still refuses
  (``test_a_marker_fitting_both_rows_still_refuses``);
* a non-split single fixture is unchanged and makes no venue call
  (``test_a_single_fixture_is_unchanged_and_fetches_nothing``).
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "TEXT"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "TEXT"


# The production specimen, verbatim (read 2026-09-24).
MONTREAL = "Montreal Canadiens"
OTTAWA = "Ottawa Senators"
PM_NAME = "Senators vs. Canadiens"
PM_EVENT_ID = "936779"
PUCK_DROP = datetime(2026, 9, 26, 23, 0, tzinfo=timezone.utc)
NOW = datetime(2026, 9, 24, 16, 0, tzinfo=timezone.utc)


def _gamma(home="Canadiens", away="Senators"):
    """Gamma's event payload, trimmed to the keys the arm reads (shape verbatim)."""
    teams = []
    if away is not None:
        teams.append({"id": 100633, "name": away, "abbreviation": "ott", "ordering": "away"})
    if home is not None:
        teams.append({"id": 100628, "name": home, "abbreviation": "mon", "ordering": "home"})
    return {
        "id": PM_EVENT_ID,
        "slug": "nhl-ott-mon-2026-09-26",
        "title": "Split Squad: Senators (A) vs. Canadiens (H)",
        "teams": teams,
    }


class _AsyncShim:
    """Async surface over a real sync session (no aiosqlite in this sandbox)."""

    def __init__(self, session):
        self._s = session

    async def execute(self, statement, *a, **k):
        return self._s.execute(statement, *a, **k)

    def add(self, obj):
        self._s.add(obj)

    async def commit(self):
        self._s.commit()

    async def flush(self):
        self._s.flush()


def _new_rail():
    """A real engine holding NHL + the `_other` catch-all, and the two clubs.

    `teams` carries the production alternates ("Senators", "Canadiens") so
    `covered_league_for_matchup` resolves Polymarket's nicknames — without them
    every refusal here would pass for the wrong reason.
    """
    from sqlalchemy import create_engine
    from sqlalchemy import event as sa_event
    from sqlalchemy.orm import Session

    from app.models.models import (
        Base, Event, FuturesMarket, Sport, Team, WinProbSnapshot,
    )

    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[
            Sport.__table__, Event.__table__, Team.__table__,
            FuturesMarket.__table__, WinProbSnapshot.__table__,
        ],
    )
    session = Session(engine, expire_on_commit=False)

    @sa_event.listens_for(session, "loaded_as_persistent")
    def _reattach_utc(_sess, instance):  # pragma: no cover - test rail
        for attr, value in list(instance.__dict__.items()):
            if isinstance(value, datetime) and value.tzinfo is None:
                instance.__dict__[attr] = value.replace(tzinfo=timezone.utc)

    nhl = Sport(key="icehockey_nhl", name="NHL")
    other = Sport(key="icehockey_other", name="Ice Hockey (other)")
    session.add_all([nhl, other])
    session.flush()
    session.add_all([
        Team(name=MONTREAL, sport_id=nhl.id, alternate_names=["Canadiens"]),
        Team(name=OTTAWA, sport_id=nhl.id, alternate_names=["Senators"]),
    ])
    session.flush()
    return session, nhl, other


def _event(session, sport, *, home, away, status="scheduled"):
    from app.models.models import Event

    e = Event(
        sport_id=sport.id, home_team_name=home, away_team_name=away,
        commence_time=PUCK_DROP, status=status, external_id=None,
    )
    session.add(e)
    session.flush()
    return e


def _split_pair(session, nhl, other):
    """The specimen: voided shadow + both real games of the split squad."""
    shadow = _event(session, other, home="Senators", away="Canadiens", status="voided")
    at_montreal = _event(session, nhl, home=MONTREAL, away=OTTAWA)
    at_ottawa = _event(session, nhl, home=OTTAWA, away=MONTREAL)
    return shadow, at_montreal, at_ottawa


def _market(session, event, *, pm_event_id=PM_EVENT_ID):
    from app.models.models import FuturesMarket

    meta = {"venue_game_start": PUCK_DROP.isoformat().replace("+00:00", "Z")}
    if pm_event_id is not None:
        meta["polymarket_event_id"] = pm_event_id
    m = FuturesMarket(
        source="polymarket",
        external_id="0xd551d2682cc0fde1a09e54cd0079f3789924022f7d4663c686017ed8bec69659",
        name=PM_NAME, category="sports", status="open", event_id=event.id,
        sport_id=event.sport_id, llm_sport_category="hockey",
        market_metadata=meta,
    )
    session.add(m)
    session.commit()
    return m


async def _run_phase15(session, *, gamma=None, gamma_error=None):
    """Run the ACTUAL Phase 1.5 entry point with Gamma answered by a fake."""
    from app.services.polymarket_api import PolymarketAPIService
    from app.tasks import prediction_market_matching as task_mod

    stats = {
        "orphaned_snapshots_deleted": 0,
        "funnel": {"stale_relinked": 0, "mislink_fixed": 0},
    }
    fetch = AsyncMock(return_value=gamma, side_effect=gamma_error)
    with patch.object(task_mod, "_find_matching_event", new=AsyncMock(return_value=None)), \
         patch.object(PolymarketAPIService, "get_event_by_id", new=fetch), \
         patch.object(PolymarketAPIService, "close", new=AsyncMock()):
        await task_mod._phase15_revalidate(
            _AsyncShim(session), stats, NOW, lambda: 600.0, [],
        )
    session.commit()
    return stats, fetch


@pytest.mark.asyncio
@pytest.mark.parametrize("venue_home,expect_home", [
    ("Canadiens", MONTREAL),  # the specimen: 936779 marks Canadiens home
    ("Senators", OTTAWA),     # the mirror: same rows, the other game
])
async def test_the_venue_home_marker_moves_the_market_to_its_game(venue_home, expect_home):
    """🔴 THE SHIP. The marker picks the game whose HOME club it names."""
    session, nhl, other = _new_rail()
    shadow, at_montreal, at_ottawa = _split_pair(session, nhl, other)
    market = _market(session, shadow)
    venue_away = "Senators" if venue_home == "Canadiens" else "Canadiens"

    stats, fetch = await _run_phase15(
        session, gamma=_gamma(home=venue_home, away=venue_away),
    )

    expected = at_montreal if expect_home == MONTREAL else at_ottawa
    session.refresh(market)
    assert market.event_id == expected.id, (
        f"venue home={venue_home}: market on {market.event_id}, expected "
        f"{expected.id} ({expect_home} home); shadow={shadow.id}"
    )
    assert market.sport_id == nhl.id
    assert stats["funnel"]["phase15_retired_venue_relinked"] == 1
    fetch.assert_awaited_with(PM_EVENT_ID)


async def _assert_refused(session, shadow, market, stats):
    session.refresh(market)
    assert market.event_id == shadow.id, (
        f"the pass picked one game of a split-squad pair (event {market.event_id})"
    )
    assert stats["funnel"].get("phase15_retired_venue_relinked", 0) == 0
    assert stats["funnel"]["phase15_retired_left_alone"] == 1


@pytest.mark.asyncio
async def test_a_missing_marker_still_refuses():
    """Gamma answers, but with no home/away ordering: no marker, no move."""
    session, nhl, other = _new_rail()
    shadow, _mtl, _ott = _split_pair(session, nhl, other)
    market = _market(session, shadow)

    stats, fetch = await _run_phase15(session, gamma=_gamma(home=None))

    await _assert_refused(session, shadow, market, stats)
    fetch.assert_awaited()


@pytest.mark.asyncio
async def test_a_fetch_failure_still_refuses():
    """A venue error is "no marker", never a guess."""
    session, nhl, other = _new_rail()
    shadow, _mtl, _ott = _split_pair(session, nhl, other)
    market = _market(session, shadow)

    stats, _ = await _run_phase15(session, gamma_error=RuntimeError("429"))

    await _assert_refused(session, shadow, market, stats)


@pytest.mark.asyncio
async def test_a_market_with_no_event_id_refuses_without_a_venue_call():
    """No stored Gamma event id: nothing to ask, so refuse and ask nothing."""
    session, nhl, other = _new_rail()
    shadow, _mtl, _ott = _split_pair(session, nhl, other)
    market = _market(session, shadow, pm_event_id=None)

    stats, fetch = await _run_phase15(session, gamma=_gamma())

    await _assert_refused(session, shadow, market, stats)
    fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_wrong_side_marker_still_refuses():
    """A marker naming a club that is on neither row fits neither: refuse."""
    session, nhl, other = _new_rail()
    shadow, _mtl, _ott = _split_pair(session, nhl, other)
    market = _market(session, shadow)

    stats, _ = await _run_phase15(
        session, gamma=_gamma(home="Bruins", away="Senators"),
    )

    await _assert_refused(session, shadow, market, stats)


@pytest.mark.asyncio
async def test_a_marker_whose_away_club_is_on_neither_row_still_refuses():
    """The home club matches one row, but the venue's AWAY club is a third
    club: that marker describes some other game, so it picks nothing."""
    session, nhl, other = _new_rail()
    shadow, _mtl, _ott = _split_pair(session, nhl, other)
    market = _market(session, shadow)

    stats, _ = await _run_phase15(
        session, gamma=_gamma(home="Canadiens", away="Bruins"),
    )

    await _assert_refused(session, shadow, market, stats)


@pytest.mark.asyncio
async def test_a_marker_fitting_both_rows_still_refuses():
    """Two rows for ONE game (same home, same away): the marker fits both."""
    session, nhl, other = _new_rail()
    shadow = _event(session, other, home="Senators", away="Canadiens", status="voided")
    _event(session, nhl, home=MONTREAL, away=OTTAWA)
    _event(session, nhl, home=MONTREAL, away=OTTAWA)
    market = _market(session, shadow)

    stats, _ = await _run_phase15(session, gamma=_gamma())

    await _assert_refused(session, shadow, market, stats)


@pytest.mark.asyncio
async def test_a_single_fixture_is_unchanged_and_fetches_nothing():
    """CONTROL: one real game moves exactly as #7904 shipped, no venue call."""
    session, nhl, other = _new_rail()
    shadow = _event(session, other, home="Senators", away="Canadiens", status="voided")
    at_ottawa = _event(session, nhl, home=OTTAWA, away=MONTREAL)
    market = _market(session, shadow)

    # Gamma would say Canadiens home — the single-fixture path must not ask.
    stats, fetch = await _run_phase15(session, gamma=_gamma())

    session.refresh(market)
    assert market.event_id == at_ottawa.id
    assert stats["funnel"]["phase15_retired_venue_relinked"] == 1
    fetch.assert_not_awaited()


def test_venue_home_away_parses_gamma_ordering():
    """The parse: exactly one home and one away, else None."""
    from app.tasks.prediction_market_matching import _venue_home_away

    assert _venue_home_away(_gamma()) == ("Canadiens", "Senators")
    assert _venue_home_away(_gamma(home=None)) is None
    assert _venue_home_away({"teams": [
        {"name": "Canadiens", "ordering": "home"},
        {"name": "Senators", "ordering": "home"},
    ]}) is None
    # Two homes is no marker even when an away is present.
    assert _venue_home_away({"teams": [
        {"name": "Canadiens", "ordering": "home"},
        {"name": "Senators", "ordering": "home"},
        {"name": "Senators", "ordering": "away"},
    ]}) is None
    assert _venue_home_away(None) is None
    assert _venue_home_away({"teams": "x"}) is None
