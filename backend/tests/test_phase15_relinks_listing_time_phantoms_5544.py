"""A market sitting on a listing-time phantom walks to its real game (#5544).

CERT-2708's BLOCK, and the half the minting refusal cannot reach. Declining to
mint stops the NEXT phantom; the ones already standing keep their markets, and
Phase 1.5 walks past them every fifteen minutes. Measured on production
2026-09-12 — four real MLB fixtures five days out serving **0 markets** while a
phantom holds each one's Polymarket price, twins to the minute:

    15310210 Brewers/Pirates  09-11 13:00:30Z  <->  15310673 @ 09-17 16:35Z
    15310206 Dodgers/Reds     09-11 13:00:31Z  <->  15310674 @ 09-17 16:40Z
    15310214 Athletics/Rays   09-11 13:00:32Z  <->  15310675 @ 09-17 17:10Z
    15310212 Padres/Rockies   09-11 13:00:35Z  <->  15310676 @ 09-17 19:10Z

WHY IT WALKED PAST THEM. The grader reproduced the scorer on the exact sha: it
selects phantom 15310210 at **30.5729** over the real 15310673. So
`_find_matching_event` hands back the row Phase 1.5 is already on, the pass reads
that as "no improvement", and the `is_auto_created` arm falls through to `pass`.
"No better match" and "this link is right" are not the same sentence, and the
code could not tell them apart.

WHAT MAKES IT DECIDABLE. The phantom is already known-bad by a guard shipped in
#4965: its `commence_time` is Gamma's `startDate` — the LISTING stamp — so
`_check_polymarket_fixture_reason` puts it ~147h from the venue's own fixture
instant and refuses the link outright. That guard was only ever asked about a
PROPOSED link. Asking it about the CURRENT one is the entry condition.

🔴 THIS IS NOT RULING 048 ABSORPTION (gotcha #32). No event absorbs another,
nothing is deleted, and the phantom row stays exactly where it is for #1946's
id-keyed drain. Only `futures_markets.event_id` moves — off a row the venue
refuses, onto the row the venue names.

WHAT EACH TEST DEFENDS:

* the ship — the real MLB page gets the price
  (`test_phase15_relinks_a_polymarket_market_from_listing_time_phantom_to_real_covered_fixture_5544`);
* the phantom SURVIVING the move, because deleting it is the ruling-048 breach
  this is carefully not (`test_the_phantom_event_row_itself_is_left_standing`);
* the entry condition being real, not decorative — a phantom whose venue instant
  AGREES is left alone (`test_a_phantom_whose_venue_instant_agrees_is_not_moved`);
* the four leagues the minting half measured and deliberately spared — an NPB
  pair must not be dragged into MLB
  (`test_an_npb_pair_is_never_walked_into_a_covered_league`);
* no signal, no move (`test_a_market_with_no_venue_instant_is_left_alone`);
* ambiguity is #1946's, not ours
  (`test_two_real_fixtures_inside_the_window_are_refused_as_ambiguous`);
* never phantom-to-phantom (`test_the_destination_is_never_another_auto_created_row`);
* a real link is never disturbed (`test_a_market_on_a_real_event_is_untouched`).
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles


# `Event`/`Team` carry Postgres JSONB/ARRAY columns sqlite cannot render as DDL.
@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "TEXT"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "TEXT"


# The production specimen, verbatim (read 2026-09-12).
BREWERS = "Milwaukee Brewers"
PIRATES = "Pittsburgh Pirates"
PM_NAME = f"{BREWERS} vs. {PIRATES}"
PM_CONDITION_ID = "964211"

#: Gamma's `startDate` — the LISTING stamp the phantom was minted from.
LISTING_STAMP = datetime(2026, 9, 11, 13, 0, 30, tzinfo=timezone.utc)
#: Gamma's `startTime` — the fixture instant the venue actually publishes.
FIRST_PITCH = datetime(2026, 9, 17, 16, 35, tzinfo=timezone.utc)

NOW = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)


class _AsyncShim:
    """Async surface over a real sync session (no aiosqlite in this sandbox).

    The statements executed are production's own; nothing is reimplemented.
    """

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
    """A real engine holding MLB + the `_other` catch-all + NPB, and the clubs.

    `teams` is populated because `covered_league_for_matchup` — the SAME resolver
    the minting refusal calls — is what decides whether a matchup belongs to a
    covered league at all. An empty `teams` table would make every test here pass
    for the wrong reason: the resolver would return None and nothing would ever
    move, including the ship.
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

    mlb = Sport(key="baseball_mlb", name="MLB")
    other = Sport(key="baseball_other", name="Baseball (other)")
    npb = Sport(key="baseball_npb", name="NPB")
    session.add_all([mlb, other, npb])
    session.flush()

    session.add_all([
        Team(name=BREWERS, sport_id=mlb.id),
        Team(name=PIRATES, sport_id=mlb.id),
        # The measured control population: NPB clubs live in `teams` too, under
        # a league the Odds API does not carry.
        Team(name="Hanshin Tigers", sport_id=npb.id),
        Team(name="Yomiuri Giants", sport_id=npb.id),
    ])
    session.flush()
    return session, mlb, other, npb


def _phantom(session, sport_other, *, home=BREWERS, away=PIRATES):
    """The minted row: `_other`, unbound, stamped with the LISTING time."""
    from app.models.models import Event

    e = Event(
        sport_id=sport_other.id, home_team_name=home, away_team_name=away,
        commence_time=LISTING_STAMP, status="scheduled",
        external_id=f"pm_{PM_CONDITION_ID}",
    )
    session.add(e)
    session.flush()
    return e


def _real_fixture(session, sport, *, commence=FIRST_PITCH, home=BREWERS, away=PIRATES):
    """StatPal's row — the one that arrived fifteen hours after the mint."""
    from app.models.models import Event

    e = Event(
        sport_id=sport.id, home_team_name=home, away_team_name=away,
        commence_time=commence, status="scheduled", external_id=None,
    )
    session.add(e)
    session.flush()
    return e


def _market(session, event, *, venue_start=FIRST_PITCH, name=PM_NAME):
    from app.models.models import FuturesMarket

    meta = {}
    if venue_start is not None:
        meta["venue_game_start"] = venue_start.isoformat().replace("+00:00", "Z")
    m = FuturesMarket(
        source="polymarket", external_id=PM_CONDITION_ID, name=name,
        category="sports", status="open", event_id=event.id,
        sport_id=event.sport_id, llm_sport_category="baseball",
        market_metadata=meta,
    )
    session.add(m)
    session.commit()
    return m


async def _run_phase15(session, *, scorer_returns):
    """Run the ACTUAL entry point.

    `_find_matching_event` is pinned to the answer the grader MEASURED on the
    exact sha — the phantom, at 30.5729, beating the real row. That is the
    premise of the whole defect, and pinning it is what keeps this test about the
    repair rather than about how sqlite happens to score a two-row corpus.
    """
    from app.tasks import prediction_market_matching as task_mod

    stats = {
        "orphaned_snapshots_deleted": 0,
        "funnel": {"stale_relinked": 0, "mislink_fixed": 0},
    }
    link_changes = []
    with patch.object(
        task_mod, "_find_matching_event",
        new=AsyncMock(return_value=scorer_returns),
    ):
        await task_mod._phase15_revalidate(
            _AsyncShim(session), stats, NOW, lambda: 600.0, link_changes,
        )
    session.commit()
    return stats, link_changes


def _as_linked(event):
    return {"event_id": event.id, "sport_id": event.sport_id}


@pytest.mark.asyncio
async def test_phase15_relinks_a_polymarket_market_from_listing_time_phantom_to_real_covered_fixture_5544():
    """🔴 THE SHIP (CERT-2708's required repair).

    The real Brewers/Pirates page stops serving zero markets.
    """
    session, mlb, other, _npb = _new_rail()
    phantom = _phantom(session, other)
    real = _real_fixture(session, mlb)
    market = _market(session, phantom)

    stats, link_changes = await _run_phase15(
        session, scorer_returns=_as_linked(phantom),
    )

    session.refresh(market)
    assert market.event_id == real.id, (
        "the market stayed on the listing-time phantom — the real MLB fixture "
        f"still serves no Polymarket price (event_id={market.event_id}, "
        f"phantom={phantom.id}, real={real.id})"
    )
    # It moved for the stated reason, and the move is counted rather than silent.
    assert stats["funnel"]["phase15_phantom_venue_relinked"] == 1
    # And the market's sport travels with it — off the catch-all onto MLB.
    assert market.sport_id == mlb.id
    # A moved link that cannot say where it came from is LINKLOSS-02's shape.
    assert link_changes, "the relink published no receipt"


@pytest.mark.asyncio
async def test_the_phantom_event_row_itself_is_left_standing():
    """🔴 Ruling 048 / gotcha #32: this moves a POINTER, it does not absorb.

    The phantom must survive the pass intact, with its own id, for #1946's
    id-keyed drain to reach. A fix that tidied it away here would be the
    name-and-time absorption the ruling forbids, wearing a relink's counters.
    """
    from app.models.models import Event

    session, mlb, other, _npb = _new_rail()
    phantom = _phantom(session, other)
    _real_fixture(session, mlb)
    _market(session, phantom)

    await _run_phase15(session, scorer_returns=_as_linked(phantom))

    still_there = session.get(Event, phantom.id)
    assert still_there is not None, "the phantom event row was deleted"
    assert still_there.commence_time == LISTING_STAMP, (
        "the phantom's own stamp was rewritten — that is absorption, not a relink"
    )


@pytest.mark.asyncio
async def test_a_phantom_whose_venue_instant_agrees_is_not_moved():
    """🔴 THE ENTRY CONDITION. The refusal is the trigger, not decoration.

    An auto-created row whose `commence_time` matches the venue instant is not
    the listing-time defect — it is a correctly-timed market-born row, and the
    scorer preferring it is the right answer. Moving it would make this a general
    "walk every auto-created market into the nearest covered fixture", which is a
    different and much larger claim than the one measured.
    """
    session, mlb, other, _npb = _new_rail()
    # Minted with the FIXTURE instant, not the listing stamp.
    phantom = _phantom(session, other)
    phantom.commence_time = FIRST_PITCH
    session.flush()
    real = _real_fixture(session, mlb)
    market = _market(session, phantom)

    stats, _ = await _run_phase15(session, scorer_returns=_as_linked(phantom))

    session.refresh(market)
    assert market.event_id == phantom.id, (
        f"a correctly-timed auto-created link was moved to {real.id} anyway"
    )
    assert stats["funnel"].get("phase15_phantom_venue_relinked", 0) == 0


@pytest.mark.asyncio
async def test_an_npb_pair_is_never_walked_into_a_covered_league():
    """🔴 THE CONTROL THE MINTING HALF MEASURED. `_other` is genuinely mixed.

    9 MLB + 6 NPB/CPBL on `baseball_other`. The discriminator is
    `covered_league_for_matchup`, the same resolver the refusal calls, so an NPB
    matchup resolves to `baseball_npb` — not covered — and this arm does not act
    on it at all.

    WHAT ACTUALLY HOLDS THE LINE HERE, stated honestly because the obvious
    reading is wrong. The load-bearing row is the REAL NPB fixture below: it
    matches both clubs exactly and sits on the venue instant, so dropping the
    league restriction walks the market straight onto it, and that is the
    mutation this test kills. The MLB decoy is a SECOND belt and is inert on its
    own — measured, not assumed: `_fuzzy_team_match("Yomiuri Giants", "San
    Francisco Giants")` is False, as is `("Hanshin Tigers", "Detroit Tigers")`,
    so the nickname collision that makes this pair the right control for the
    resolver's own substring mutation (#5544) never reaches the team test here.
    It is kept because it costs nothing and it fails loudly if that ever changes;
    it is not what makes this test pass.
    """
    session, mlb, other, npb = _new_rail()
    phantom = _phantom(
        session, other, home="Yomiuri Giants", away="Hanshin Tigers",
    )
    # A real MLB row sits inside the window, so the ONLY thing keeping this
    # market where it belongs is the league resolution.
    _real_fixture(
        session, mlb, home="San Francisco Giants", away="Detroit Tigers",
    )
    npb_real = _real_fixture(
        session, npb, home="Yomiuri Giants", away="Hanshin Tigers",
    )
    market = _market(
        session, phantom, name="Yomiuri Giants vs. Hanshin Tigers",
    )

    await _run_phase15(session, scorer_returns=_as_linked(phantom))

    session.refresh(market)
    assert market.event_id == phantom.id, (
        "an NPB market was walked into a covered league — it landed on "
        f"{market.event_id} (MLB decoy or {npb_real.id})"
    )


@pytest.mark.asyncio
async def test_a_market_with_no_venue_instant_is_left_alone():
    """No signal, no move.

    A row ingested before the stamp existed, or one the venue gives no fixture
    time for, is indistinguishable here from a row not yet re-polled. Everywhere
    else in this module that means fail OPEN (link anyway); here the action is a
    MOVE, so the same absence must mean do nothing.
    """
    session, mlb, other, _npb = _new_rail()
    phantom = _phantom(session, other)
    _real_fixture(session, mlb)
    market = _market(session, phantom, venue_start=None)

    await _run_phase15(session, scorer_returns=_as_linked(phantom))

    session.refresh(market)
    assert market.event_id == phantom.id


@pytest.mark.asyncio
async def test_two_real_fixtures_inside_the_window_are_refused_as_ambiguous():
    """A pass that cannot tell a doubleheader from a twin pair must not pick.

    Two real covered rows inside ±3h of the venue instant is either a
    doubleheader or the twin population #1946 owns. Choosing one would be this
    pass inventing an answer it has no evidence for.
    """
    session, mlb, other, _npb = _new_rail()
    phantom = _phantom(session, other)
    _real_fixture(session, mlb)
    _real_fixture(session, mlb, commence=FIRST_PITCH + timedelta(hours=2))
    market = _market(session, phantom)

    stats, _ = await _run_phase15(session, scorer_returns=_as_linked(phantom))

    session.refresh(market)
    assert market.event_id == phantom.id, (
        "the pass picked one of two equally-qualified fixtures"
    )
    assert stats["funnel"].get("phase15_phantom_venue_relinked", 0) == 0


@pytest.mark.asyncio
async def test_a_fixture_matching_only_one_side_is_not_a_confirmation():
    """🔴 BOTH clubs, or it is a different game.

    The Brewers do play at this hour — against someone else. One matching side
    plus a time inside the window is exactly the shape that reads as a
    confirmation and is not one, and it is what a relaxed team test would take.
    """
    session, mlb, other, _npb = _new_rail()
    phantom = _phantom(session, other)
    wrong_opponent = _real_fixture(
        session, mlb, home=BREWERS, away="Chicago Cubs",
    )
    market = _market(session, phantom)

    stats, _ = await _run_phase15(session, scorer_returns=_as_linked(phantom))

    session.refresh(market)
    assert market.event_id == phantom.id, (
        "a Brewers/Pirates market landed on Brewers/Cubs "
        f"(event {wrong_opponent.id})"
    )
    assert stats["funnel"].get("phase15_phantom_venue_relinked", 0) == 0


@pytest.mark.asyncio
async def test_a_real_fixture_outside_the_window_is_not_close_enough():
    """🔴 The window is the whole claim, so a NEAR-MISS must be refused.

    These clubs play each other again. When the venue names a fixture the
    schedule has not carried yet, the next series' game is a real covered row
    with both team names matching — and it is not this game. Zero candidates
    means WAIT: the forward path links it when the schedule arrives, which is the
    minting half's entire argument. A widened tolerance turns "wait" into "put it
    on the wrong game", and this is the test that says so.
    """
    session, mlb, other, _npb = _new_rail()
    phantom = _phantom(session, other)
    next_series = _real_fixture(
        session, mlb, commence=FIRST_PITCH + timedelta(days=7),
    )
    market = _market(session, phantom)

    stats, _ = await _run_phase15(session, scorer_returns=_as_linked(phantom))

    session.refresh(market)
    assert market.event_id == phantom.id, (
        "the market was walked onto next week's meeting of the same two clubs "
        f"(event {next_series.id})"
    )
    assert stats["funnel"].get("phase15_phantom_venue_relinked", 0) == 0


@pytest.mark.asyncio
async def test_the_destination_is_never_another_auto_created_row():
    """Moving a market between two phantoms is churn wearing a fix's clothes.

    A second `pm_` row carrying the right time is still market-born, still
    unbound, and still not the game's page. With no real row present the market
    stays where it is.
    """
    from app.models.models import Event

    session, mlb, other, _npb = _new_rail()
    phantom = _phantom(session, other)
    correctly_timed_phantom = Event(
        sport_id=mlb.id, home_team_name=BREWERS, away_team_name=PIRATES,
        commence_time=FIRST_PITCH, status="scheduled",
        external_id=f"pm_{PM_CONDITION_ID}_2",
    )
    session.add(correctly_timed_phantom)
    session.flush()
    market = _market(session, phantom)

    await _run_phase15(session, scorer_returns=_as_linked(phantom))

    session.refresh(market)
    assert market.event_id == phantom.id, (
        f"the market hopped to another auto-created row "
        f"({correctly_timed_phantom.id})"
    )


@pytest.mark.asyncio
async def test_a_market_on_a_real_event_is_untouched():
    """CONTROL: the arm is gated on `is_auto_created` and must stay there.

    A market already on a real schedule row whose time happens to disagree is
    #4965's business and the ordinary relink path's, never this one's.
    """
    session, mlb, other, _npb = _new_rail()
    # Linked to a REAL row that carries the listing stamp — wrong time, right
    # provenance. Nothing here may act on it.
    wrongly_timed_real = _real_fixture(session, mlb, commence=LISTING_STAMP)
    _real_fixture(session, mlb)
    market = _market(session, wrongly_timed_real)

    stats, _ = await _run_phase15(
        session, scorer_returns=_as_linked(wrongly_timed_real),
    )

    session.refresh(market)
    assert market.event_id == wrongly_timed_real.id
    assert stats["funnel"].get("phase15_phantom_venue_relinked", 0) == 0
