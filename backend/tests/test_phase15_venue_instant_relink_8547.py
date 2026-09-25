"""A doubleheader's Polymarket market goes to the game the VENUE times (#8547).

**SHIP: Friday's Orioles @ Yankees game 1 shows its Polymarket price, and game
2 stops blending game 1's Polymarket market into its number.** (Pillar:
MATCHING.)

Measured on production 2026-09-25 ~06:20Z. Saturday's game was moved into a
Friday split doubleheader:

    15318575  baseball_mlb  game 1  20:05Z  ESPN 401817088   0 PM markets
    15316328  baseball_mlb  game 2  23:05Z  StatPal 366746   PM 1047825 (23:05) ✓
                                                            PM 1053347 (20:05) ✗
    Gamma 1053347, slug `mlb-bal-nyy-2026-09-26`, startTime 2026-09-25T20:05Z

1053347 linked at ~02:37Z, when game 2 was the only Friday row — 3.0h from the
venue's instant, which the ±3h guard's strict ``>`` admits. Game 1's row
arrived at 04:29Z and Phase 1.5 walked past the link every 15 minutes because
the teams agreed. The new arm asks the venue's instant about the CURRENT link.

WHAT EACH TEST DEFENDS:

* the ship: both markets of group 1053347 move to game 1, 1047825 stays on
  game 2 (``test_the_venue_instant_moves_the_doubleheader_market_to_its_game``);
* the entry bound, both sides of 90 minutes, and no finder query below it
  (``test_drift_under_ninety_minutes_is_left_alone_without_a_query`` /
  ``test_the_entry_bound_is_inclusive_at_ninety_minutes``);
* the destination bound: no row inside 15 minutes, or two, and nothing moves
  (``test_no_row_at_the_venue_minute_leaves_the_link`` /
  ``test_two_rows_at_the_venue_minute_leave_the_link``);
* a retired row at the venue's minute is never a destination
  (``test_a_retired_row_at_the_venue_minute_is_not_a_destination``);
* a Kalshi ticker already on the game its HHMM names stays put — the Kalshi
  twin of this arm has its own file,
  ``test_phase15_kalshi_venue_instant_relink_8547.py``
  (``test_a_kalshi_market_is_never_moved_by_this_arm``);
* the pure entry predicate
  (``test_venue_instant_disowns_link_predicate``).
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
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


# The production specimen, verbatim (read 2026-09-25).
YANKEES = "New York Yankees"
ORIOLES = "Baltimore Orioles"
PM_NAME = "Baltimore Orioles vs. New York Yankees"
GAME_1 = datetime(2026, 9, 25, 20, 5, tzinfo=timezone.utc)
GAME_2 = datetime(2026, 9, 25, 23, 5, tzinfo=timezone.utc)
MOVED_GAME_EVENT = "1053347"  # slug mlb-bal-nyy-2026-09-26, startTime = GAME_1
FRIDAY_GAME_EVENT = "1047825"  # slug mlb-bal-nyy-2026-09-25, startTime = GAME_2
NOW = datetime(2026, 9, 25, 6, 20, tzinfo=timezone.utc)


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
    """A real engine holding MLB and the two clubs `covered_league_for_matchup` resolves."""
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

    mlb = Sport(key="baseball_mlb", name="MLB")
    session.add(mlb)
    session.flush()
    session.add_all([
        Team(name=YANKEES, sport_id=mlb.id, alternate_names=["Yankees"]),
        Team(name=ORIOLES, sport_id=mlb.id, alternate_names=["Orioles"]),
    ])
    session.flush()
    return session, mlb


def _event(session, sport, commence, *, status="scheduled", espn_id=None):
    from app.models.models import Event

    e = Event(
        sport_id=sport.id, home_team_name=YANKEES, away_team_name=ORIOLES,
        commence_time=commence, status=status, external_id=None, espn_id=espn_id,
    )
    session.add(e)
    session.flush()
    return e


def _pm(session, event, *, pm_event_id, venue_start, external_id, group_type):
    from app.models.models import FuturesMarket

    m = FuturesMarket(
        source="polymarket", external_id=external_id, name=PM_NAME,
        category="sports", status="open", event_id=event.id,
        sport_id=event.sport_id, llm_sport_category="baseball",
        group_id=f"polymarket:{pm_event_id}", group_type=group_type,
        market_metadata={
            "venue_game_start": venue_start.isoformat().replace("+00:00", "Z"),
            "polymarket_event_id": pm_event_id,
        },
    )
    session.add(m)
    session.flush()
    return m


def _specimen(session, mlb, *, game_1_at=GAME_1, game_1_status="scheduled"):
    """Game 1 (ESPN row), game 2 (StatPal row) and the three PM rows on game 2."""
    game_1 = _event(session, mlb, game_1_at, status=game_1_status, espn_id="401817088")
    game_2 = _event(session, mlb, GAME_2)
    moved = _pm(
        session, game_2, pm_event_id=MOVED_GAME_EVENT, venue_start=GAME_1,
        external_id=MOVED_GAME_EVENT, group_type="polymarket_event",
    )
    moved_sib = _pm(
        session, game_2, pm_event_id=MOVED_GAME_EVENT, venue_start=GAME_1,
        external_id="0xe7cbc320665f2e0978f6864bec1c26b315d63a71593f94cfaeab933c5732b87f",
        group_type="polymarket_sub_market",
    )
    friday = _pm(
        session, game_2, pm_event_id=FRIDAY_GAME_EVENT, venue_start=GAME_2,
        external_id=FRIDAY_GAME_EVENT, group_type="polymarket_event",
    )
    session.commit()
    return game_1, game_2, moved, moved_sib, friday


async def _run_phase15(session, *, finder_spy=False):
    """Run the ACTUAL Phase 1.5 entry point; the scorer and Gamma are inert."""
    from app.services.polymarket_api import PolymarketAPIService
    from app.tasks import prediction_market_matching as task_mod

    stats = {
        "orphaned_snapshots_deleted": 0,
        "funnel": {"stale_relinked": 0, "mislink_fixed": 0},
    }
    real_finder = task_mod._venue_confirmed_covered_fixture
    spy = AsyncMock(side_effect=real_finder)
    with patch.object(task_mod, "_find_matching_event", new=AsyncMock(return_value=None)), \
         patch.object(task_mod, "_venue_confirmed_covered_fixture", new=spy), \
         patch.object(PolymarketAPIService, "get_event_by_id", new=AsyncMock(return_value=None)), \
         patch.object(PolymarketAPIService, "close", new=AsyncMock()):
        await task_mod._phase15_revalidate(
            _AsyncShim(session), stats, NOW, lambda: 600.0, [],
        )
    session.commit()
    return stats, spy


def _on(session, *markets):
    for m in markets:
        session.refresh(m)
    return [m.event_id for m in markets]


@pytest.mark.asyncio
async def test_the_venue_instant_moves_the_doubleheader_market_to_its_game():
    """🔴 THE SHIP. Group 1053347 moves to game 1; Friday's 1047825 stays."""
    session, mlb = _new_rail()
    game_1, game_2, moved, moved_sib, friday = _specimen(session, mlb)

    stats, _ = await _run_phase15(session)

    assert _on(session, moved, moved_sib) == [game_1.id, game_1.id], (
        f"game 1 = {game_1.id}, game 2 = {game_2.id}: 1053347 (venue 20:05Z) "
        f"must sit on game 1"
    )
    assert _on(session, friday) == [game_2.id], "1047825 (venue 23:05Z) is game 2's"
    assert stats["funnel"]["phase15_venue_instant_relinked"] >= 1
    # A same-teams move is not a mislink, and must not delete game 2's curve.
    assert stats["funnel"]["mislink_fixed"] == 0
    assert stats["orphaned_snapshots_deleted"] == 0


@pytest.mark.asyncio
async def test_drift_under_ninety_minutes_is_left_alone_without_a_query():
    """89 minutes off the row is inside the entry bound: no move, no finder call."""
    session, mlb = _new_rail()
    game_2 = _event(session, mlb, GAME_2)
    _event(session, mlb, GAME_2 - timedelta(minutes=89), espn_id="401817088")
    m = _pm(
        session, game_2, pm_event_id=MOVED_GAME_EVENT,
        venue_start=GAME_2 - timedelta(minutes=89),
        external_id=MOVED_GAME_EVENT, group_type="polymarket_event",
    )
    session.commit()

    stats, spy = await _run_phase15(session)

    assert _on(session, m) == [game_2.id]
    spy.assert_not_awaited()
    assert stats["funnel"].get("phase15_venue_instant_relinked", 0) == 0


@pytest.mark.asyncio
async def test_the_entry_bound_is_inclusive_at_ninety_minutes():
    """Exactly 90 minutes enters the arm, and the row at the venue minute wins."""
    session, mlb = _new_rail()
    game_2 = _event(session, mlb, GAME_2)
    at_venue = _event(session, mlb, GAME_2 - timedelta(minutes=90), espn_id="401817088")
    m = _pm(
        session, game_2, pm_event_id=MOVED_GAME_EVENT,
        venue_start=GAME_2 - timedelta(minutes=90),
        external_id=MOVED_GAME_EVENT, group_type="polymarket_event",
    )
    session.commit()

    await _run_phase15(session)

    assert _on(session, m) == [at_venue.id]


@pytest.mark.asyncio
async def test_no_row_at_the_venue_minute_leaves_the_link():
    """Game 1 held 20 minutes off the venue's instant: outside 15, nothing moves."""
    session, mlb = _new_rail()
    _g1, game_2, moved, moved_sib, _f = _specimen(
        session, mlb, game_1_at=GAME_1 + timedelta(minutes=20),
    )

    stats, spy = await _run_phase15(session)

    assert _on(session, moved, moved_sib) == [game_2.id, game_2.id]
    spy.assert_awaited()
    assert stats["funnel"]["phase15_venue_instant_left_alone"] >= 1
    assert stats["funnel"].get("phase15_venue_instant_relinked", 0) == 0


@pytest.mark.asyncio
async def test_two_rows_at_the_venue_minute_leave_the_link():
    """Two rows for game 1 (a twin pair): the finder cannot pick, so it does not."""
    session, mlb = _new_rail()
    _g1, game_2, moved, moved_sib, _f = _specimen(session, mlb)
    _event(session, mlb, GAME_1 + timedelta(minutes=1))
    session.commit()

    stats, _ = await _run_phase15(session)

    assert _on(session, moved, moved_sib) == [game_2.id, game_2.id]
    assert stats["funnel"].get("phase15_venue_instant_relinked", 0) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("retired", ["voided", "merged"])
async def test_a_retired_row_at_the_venue_minute_is_not_a_destination(retired):
    """Only a retired row sits at 20:05Z: it is off every page, so nothing moves."""
    session, mlb = _new_rail()
    _g1, game_2, moved, moved_sib, _f = _specimen(
        session, mlb, game_1_status=retired,
    )

    stats, _ = await _run_phase15(session)

    assert _on(session, moved, moved_sib) == [game_2.id, game_2.id]
    assert stats["funnel"].get("phase15_venue_instant_relinked", 0) == 0


@pytest.mark.asyncio
async def test_a_kalshi_market_is_never_moved_by_this_arm():
    """A Kalshi ticker whose HHMM (19:05 ET = 23:05Z) is game 2 stays on game 2.

    A stray ``venue_game_start`` on a Kalshi row is not read: the Kalshi
    instant is the ticker's, and this ticker names the row it is on.
    """
    from app.models.models import FuturesMarket

    session, mlb = _new_rail()
    _event(session, mlb, GAME_1, espn_id="401817088")
    game_2 = _event(session, mlb, GAME_2)
    k = FuturesMarket(
        source="kalshi", external_id="KXMLBGAME-26SEP251905BALNYY",
        name="Baltimore vs New York Y", category="sports", status="open",
        event_id=game_2.id, sport_id=mlb.id, llm_sport_category="baseball",
        market_metadata={"venue_game_start": GAME_1.isoformat()},
    )
    session.add(k)
    session.commit()

    stats, _ = await _run_phase15(session)

    assert _on(session, k) == [game_2.id]
    assert stats["funnel"].get("phase15_venue_instant_relinked", 0) == 0


def test_venue_instant_disowns_link_predicate():
    from app.tasks.prediction_market_matching import _venue_instant_disowns_link

    def pm(start, source="polymarket"):
        meta = {} if start is None else {"venue_game_start": start}
        return SimpleNamespace(source=source, market_metadata=meta)

    row = SimpleNamespace(commence_time=GAME_2)
    assert _venue_instant_disowns_link(pm("2026-09-25T20:05:00Z"), row) is True
    assert _venue_instant_disowns_link(pm("2026-09-25T21:36:00Z"), row) is False
    assert _venue_instant_disowns_link(pm("2026-09-25T21:35:00Z"), row) is True
    # Symmetric: a venue instant AFTER the row counts the same.
    assert _venue_instant_disowns_link(pm("2026-09-26T00:35:00Z"), row) is True
    # No signal is never a refusal-to-trust.
    assert _venue_instant_disowns_link(pm(None), row) is False
    assert _venue_instant_disowns_link(pm("garbage"), row) is False
    assert _venue_instant_disowns_link(
        pm("2026-09-25T20:05:00Z"), SimpleNamespace(commence_time=None),
    ) is False
    assert _venue_instant_disowns_link(
        pm("2026-09-25T20:05:00Z", source="kalshi"), row,
    ) is False
    # A naive commence is read as UTC, not refused.
    naive = SimpleNamespace(commence_time=GAME_2.replace(tzinfo=None))
    assert _venue_instant_disowns_link(pm("2026-09-25T20:05:00Z"), naive) is True
