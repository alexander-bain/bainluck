"""A market left on a RETIRED row walks to its real game (#7904).

**SHIP: tonight's NHL preseason games show Polymarket's price on their page
beside Kalshi's.** (Pillar: MATCHING.)

Measured on production 2026-09-24 14:0xZ. All eleven NHL games that night carry
Kalshi only. Each one's Polymarket markets (2-6 per game, open and priced —
Devils vs. Rangers at Rangers 56.5%) sit on an ``icehockey_other`` row Polymarket's
ingest minted from Gamma's LISTING clock:

    shadow 15294185  icehockey_other  "Rangers @ Devils"   voided   3 markets
    real   15314264  icehockey_nhl    "New Jersey Devils @ New York Rangers"
                                                            scheduled, Kalshi only

#5532's arm voided the shadows on 09-13 while that listing clock made them look
past their start (``backup_unreachable_suspended_5532`` records it); the venue
clock later moved them onto the real game instant. #7260's revival refuses a row
with a living counterpart and names that population lane1's.

WHY PHASE 1.5 WALKED PAST THEM. Its skip reads ``teams_match and not finished and
not auto_created and not sport_mismatch`` — and a voided shadow passes all four:
the nicknames match, ``voided`` is not ``completed``, the modern mint carries a
NULL ``external_id`` rather than ``pm_``, and ``icehockey_other`` is the same
family as the market. So the one link no page can render was the one link the
pass treated as settled. 145 open markets on production sat like this, 116 on
games not yet played.

🔴 THIS IS NOT RULING 048 ABSORPTION (gotcha #32). Nothing is absorbed, merged or
deleted, and the retired row stays exactly as it is. Only the market's
``event_id`` moves, and only onto the ONE real covered-league fixture its own
venue instant names — :func:`_venue_confirmed_covered_fixture`, #5544's finder,
never the scorer.

WHAT EACH TEST DEFENDS:

* the ship (``test_a_market_on_a_voided_shadow_moves_to_the_real_nhl_game``);
* the destination comes from the venue-confirmed finder, never the scorer
  (``test_the_scorer_is_not_consulted_for_a_retired_link``);
* the retired row survives untouched
  (``test_the_retired_row_itself_is_left_standing``);
* the split-squad control — #7942: NHL preseason plays the same two clubs in
  both cities at the same minute; two real games means no pick
  (``test_a_split_squad_pair_is_refused``);
* no venue instant, no move (``test_a_market_with_no_venue_instant_stays``);
* the gate is the retirement, not the shadow — a LIVE shadow is untouched here
  (``test_a_market_on_a_live_shadow_is_untouched_by_this_arm``);
* retired links lead the scan queue, ahead of the finished class that
  outnumbers the cap (``test_retired_links_lead_the_fresh_slice``).
"""

from datetime import datetime, timedelta, timezone
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
RANGERS = "New York Rangers"
DEVILS = "New Jersey Devils"
PM_NAME = "Devils vs. Rangers"
PM_EVENT_ID = "926250"
PUCK_DROP = datetime(2026, 9, 24, 23, 0, tzinfo=timezone.utc)
NOW = datetime(2026, 9, 24, 14, 30, tzinfo=timezone.utc)


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

    `teams` carries the clubs' production alternates ("Devils", "Rangers")
    because `covered_league_for_matchup` resolves Polymarket's nicknames through
    them. An empty `teams` table would make every refusal here pass for the
    wrong reason: the resolver would return None and nothing would ever move,
    including the ship.
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
        Team(name=RANGERS, sport_id=nhl.id, alternate_names=["Rangers"]),
        Team(name=DEVILS, sport_id=nhl.id, alternate_names=["Devils"]),
    ])
    session.flush()
    return session, nhl, other


def _shadow(session, sport_other, *, status="voided"):
    """Polymarket's mint: `_other`, nicknames, NO external id, home/away as
    the ingest read the title (inverted against ESPN's)."""
    from app.models.models import Event

    e = Event(
        sport_id=sport_other.id, home_team_name="Devils",
        away_team_name="Rangers", commence_time=PUCK_DROP, status=status,
        external_id=None,
    )
    session.add(e)
    session.flush()
    return e


def _real_game(session, nhl, *, home=RANGERS, away=DEVILS, status="scheduled"):
    from app.models.models import Event

    e = Event(
        sport_id=nhl.id, home_team_name=home, away_team_name=away,
        commence_time=PUCK_DROP, status=status, external_id=None,
    )
    session.add(e)
    session.flush()
    return e


def _market(session, event, *, venue_start=PUCK_DROP, external_id=PM_EVENT_ID):
    from app.models.models import FuturesMarket

    meta = {}
    if venue_start is not None:
        meta["venue_game_start"] = venue_start.isoformat().replace("+00:00", "Z")
    m = FuturesMarket(
        source="polymarket", external_id=external_id, name=PM_NAME,
        category="sports", status="open", event_id=event.id,
        sport_id=event.sport_id, llm_sport_category="hockey",
        market_metadata=meta,
    )
    session.add(m)
    session.commit()
    return m


async def _run_phase15(session, *, scorer_returns=None):
    """Run the ACTUAL entry point, with the scorer pinned and observable."""
    from app.tasks import prediction_market_matching as task_mod

    stats = {
        "orphaned_snapshots_deleted": 0,
        "funnel": {"stale_relinked": 0, "mislink_fixed": 0},
    }
    link_changes = []
    scorer = AsyncMock(return_value=scorer_returns)
    with patch.object(task_mod, "_find_matching_event", new=scorer):
        await task_mod._phase15_revalidate(
            _AsyncShim(session), stats, NOW, lambda: 600.0, link_changes,
        )
    session.commit()
    return stats, link_changes, scorer


@pytest.mark.asyncio
async def test_a_market_on_a_voided_shadow_moves_to_the_real_nhl_game():
    """🔴 THE SHIP. The real Devils-Rangers page gets Polymarket's market."""
    session, nhl, other = _new_rail()
    shadow = _shadow(session, other)
    real = _real_game(session, nhl)
    market = _market(session, shadow)

    stats, link_changes, _ = await _run_phase15(session)

    session.refresh(market)
    assert market.event_id == real.id, (
        "the market stayed on the voided shadow — the real NHL page still "
        f"shows Kalshi alone (event_id={market.event_id}, shadow={shadow.id}, "
        f"real={real.id})"
    )
    assert market.sport_id == nhl.id, "the market kept the catch-all's sport"
    assert stats["funnel"]["phase15_retired_venue_relinked"] == 1
    assert link_changes, "the relink published no receipt (LINKLOSS-02)"


@pytest.mark.asyncio
async def test_the_scorer_is_not_consulted_for_a_retired_link():
    """🔴 The destination is the venue-confirmed finder's, never the scorer's.

    The scorer is pinned to a DECOY — a different real row — so a mutation that
    routes the retired arm back through `_find_matching_event` puts the market
    on the decoy and reddens here, not just the call assertion.
    """
    session, nhl, other = _new_rail()
    shadow = _shadow(session, other)
    real = _real_game(session, nhl)
    decoy = _real_game(
        session, nhl, home="Boston Bruins", away="Philadelphia Flyers",
    )
    market = _market(session, shadow)

    _stats, _receipts, scorer = await _run_phase15(
        session, scorer_returns={"event_id": decoy.id, "sport_id": nhl.id},
    )

    session.refresh(market)
    assert market.event_id == real.id, (
        f"the market went where the scorer pointed (event {market.event_id})"
    )
    scorer.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_retired_row_itself_is_left_standing():
    """🔴 Ruling 048: a POINTER moves; the shadow is not absorbed or revived."""
    from app.models.models import Event

    session, nhl, other = _new_rail()
    shadow = _shadow(session, other)
    _real_game(session, nhl)
    _market(session, shadow)

    await _run_phase15(session)

    still_there = session.get(Event, shadow.id)
    assert still_there is not None, "the shadow event row was deleted"
    assert still_there.status == "voided", (
        f"the shadow's status was rewritten to {still_there.status!r}"
    )
    assert still_there.home_team_name == "Devils"


@pytest.mark.asyncio
async def test_a_split_squad_pair_is_refused():
    """🔴 THE #7942 CONTROL. Two real games, same clubs, same minute: no pick.

    NHL preseason plays split-squad doubleheaders — Toronto at Ottawa AND Ottawa
    at Toronto at 23:00Z on 2026-09-23 (ESPN 401879650 / 401886441). Both are
    real. A market that cannot say which one it prices must stay put.
    """
    session, nhl, other = _new_rail()
    shadow = _shadow(session, other)
    _real_game(session, nhl, home=RANGERS, away=DEVILS)
    _real_game(session, nhl, home=DEVILS, away=RANGERS)
    market = _market(session, shadow)

    stats, _, _ = await _run_phase15(session)

    session.refresh(market)
    assert market.event_id == shadow.id, (
        "the pass picked one game of a split-squad pair"
    )
    assert stats["funnel"].get("phase15_retired_venue_relinked", 0) == 0
    assert stats["funnel"]["phase15_retired_left_alone"] == 1


@pytest.mark.asyncio
async def test_a_market_with_no_venue_instant_stays():
    """No venue instant, no move — the action is a MOVE, so absence is a no."""
    session, nhl, other = _new_rail()
    shadow = _shadow(session, other)
    _real_game(session, nhl)
    market = _market(session, shadow, venue_start=None)

    stats, _, _ = await _run_phase15(session)

    session.refresh(market)
    assert market.event_id == shadow.id
    assert stats["funnel"]["phase15_retired_left_alone"] == 1


@pytest.mark.asyncio
async def test_a_market_on_a_live_shadow_is_untouched_by_this_arm():
    """CONTROL: the trigger is the RETIREMENT. A scheduled shadow is not it.

    A live `_other` row whose names match is a different question — whether a
    servable id-less row should give up its markets — and it is #2693's
    anchor work, not this arm's. Same rows as the ship, one word different.
    """
    session, nhl, other = _new_rail()
    shadow = _shadow(session, other, status="scheduled")
    real = _real_game(session, nhl)
    market = _market(session, shadow)

    stats, _, scorer = await _run_phase15(
        session, scorer_returns={"event_id": real.id, "sport_id": nhl.id},
    )

    session.refresh(market)
    assert market.event_id == shadow.id, (
        f"a market on a servable row was moved to {real.id}"
    )
    assert stats["funnel"].get("phase15_retired_venue_relinked", 0) == 0
    scorer.assert_not_awaited()


def test_retired_links_lead_the_fresh_slice():
    """🔴 A retired link is checked THIS beat, ahead of the finished class.

    The finished class outnumbers the whole scan cap ~6x, so a retired link
    ranked behind it never reaches the fresh slice. One market on a completed
    game, one on a voided shadow, a one-row slice: the shadow's market wins —
    even though the finished one was touched more recently.
    """
    from app.tasks.prediction_market_matching import _phase15_fresh_query

    session, nhl, other = _new_rail()
    finished = _real_game(session, nhl, status="completed")
    shadow = _shadow(session, other)
    on_shadow = _market(session, shadow, external_id="926250-a")
    on_finished = _market(session, finished, external_id="926250-b")
    on_finished.updated_at = NOW
    on_shadow.updated_at = NOW - timedelta(days=3)
    session.commit()

    rows = session.execute(_phase15_fresh_query(limit=1)).all()

    assert [m.id for m, _e in rows] == [on_shadow.id], (
        "the voided shadow's market did not lead the fresh slice"
    )
