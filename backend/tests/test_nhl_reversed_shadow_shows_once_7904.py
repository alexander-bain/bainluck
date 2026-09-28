"""NHL opening week shows each game once, as its NHL card — #7904, the reversed shadow.

**SHIP: NHL opening week (Oct 5–9) shows each game ONCE, as its NHL card, with
Polymarket's price on it.** (Pillar: MATCHING.)

Polymarket's venue ingest filed a row per NHL game in ``icehockey_other`` weeks
before StatPal or ESPN scheduled it: bare nicknames, no id of any kind, its start
taken from the venue (``commence_time_source = 'polymarket_venue'``). Production
2026-09-28 07:3xZ: 29 upcoming, Oct 5 → Oct 25. When the NHL row arrives, the
serve-time fold joins the pair only in the SAME orientation, because it copies
home/away numbers onto the survivor. The minter reads "Sharks vs. Blues"
home-first, so a share of the shadows sit reversed against ESPN — 4 of the 10
Oct 8 games (ESPN SJ @ STL, UTA @ BOS, MIN @ TB, NSH @ MTL):

    15310317  icehockey_other  Blues @ Sharks                    polymarket 0.465
    15169788  icehockey_nhl    San Jose Sharks @ St Louis Blues  ESPN 401891825

Two cards, one venue each, and the reversed one prints its own orientation.

TWO HALVES:

1. **Phase 1.5** — a Polymarket market on its own id-less, scheduled,
   venue-clocked ``<sport>_other`` mint moves to the ONE covered-league row the
   #5544 finder names at the venue's minute. The matcher orients it by outcome
   name (production 2026-09-28: reversed shadow 15304618 → 15168042, Polymarket
   0.625 beside Kalshi 0.64). The shadow row is left standing (ruling 048).
2. **The fold** — a REVERSED catch-all folds only when its group carries no
   oriented reading (#9304's rule): the state the move leaves behind.

WHAT EACH TEST DEFENDS:

* the ship, reversed and same-orientation (both halves);
* the shadow row survives, and its Polymarket blend key goes with the market;
* 🔴 no NHL row yet → the market stays (the opening-week window before StatPal);
* 🔴 a row somebody scheduled (any provider id), a live row, a row not on the
  venue's clock, a Kalshi market → untouched by this arm;
* 🔴 `within_sport` — "Bruins"/"Utah" field an NHL club AND college programs, so
  without the shadow's sport the resolver refuses; with it, only the NHL answers,
  and it never widens (a pair outside the sport still resolves to nothing);
* 🔴 a PRICED reversed shadow still stays two cards (the #9304 lesson).
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles

from app.utils.event_twin_fold import fold_twin_events


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "TEXT"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "TEXT"


# The production specimen, verbatim (read 2026-09-28 07:4xZ).
BLUES = "St Louis Blues"
SHARKS = "San Jose Sharks"
PM_NAME = "Sharks vs. Blues"
PM_EVENT_ID = "1005034"
PUCK_DROP = datetime(2026, 10, 9, 0, 0, tzinfo=timezone.utc)
NOW = datetime(2026, 9, 28, 8, 0, tzinfo=timezone.utc)
VENUE = "polymarket_venue"


# --------------------------------------------------------------------------
# Half 1 — Phase 1.5 moves the shadow's market onto the NHL row
# --------------------------------------------------------------------------


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
    """A real engine with NHL, the catch-all, a college key and production's clubs.

    `teams` carries the production alternates, because the finder resolves
    Polymarket's nicknames through them; an empty table would make every
    refusal here pass for the wrong reason (nothing would ever move).
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
    ncaaf = Sport(key="americanfootball_ncaaf", name="NCAAF")
    session.add_all([nhl, other, ncaaf])
    session.flush()
    session.add_all([
        Team(name=BLUES, sport_id=nhl.id, alternate_names=["Blues"]),
        Team(name=SHARKS, sport_id=nhl.id, alternate_names=["Sharks"]),
        Team(name="Boston Bruins", sport_id=nhl.id, alternate_names=["Bruins"]),
        Team(name="Utah Mammoth", sport_id=nhl.id, alternate_names=["Mammoth", "Utah"]),
        # Production: both nicknames also name college programs (teams read
        # 2026-09-28), which is what makes the bare resolver ambiguous.
        Team(name="UCLA Bruins", sport_id=ncaaf.id, alternate_names=["Bruins"]),
        Team(name="Utah Utes", sport_id=ncaaf.id, alternate_names=["Utah"]),
    ])
    session.flush()
    return session, nhl, other


def _shadow(session, other, *, away="Blues", home="Sharks", status="scheduled",
            source=VENUE, sources=None, **ids):
    """Polymarket's mint: `_other`, nicknames, no id, home-first as read."""
    from app.models.models import Event

    e = Event(
        sport_id=other.id, home_team_name=home, away_team_name=away,
        commence_time=PUCK_DROP, status=status, commence_time_source=source,
        win_probability_sources=sources, **ids,
    )
    session.add(e)
    session.flush()
    return e


def _nhl_row(session, nhl, *, away=SHARKS, home=BLUES, espn_id="401891825"):
    from app.models.models import Event

    e = Event(
        sport_id=nhl.id, home_team_name=home, away_team_name=away,
        commence_time=PUCK_DROP, status="scheduled", espn_id=espn_id,
        commence_time_source="espn",
    )
    session.add(e)
    session.flush()
    return e


def _market(session, event, *, name=PM_NAME, source="polymarket",
            external_id=PM_EVENT_ID):
    from app.models.models import FuturesMarket

    m = FuturesMarket(
        source=source, external_id=external_id, name=name,
        category="sports", status="open", event_id=event.id,
        sport_id=event.sport_id, llm_sport_category="hockey",
        market_metadata={
            "venue_game_start": PUCK_DROP.isoformat().replace("+00:00", "Z"),
        },
    )
    session.add(m)
    session.commit()
    return m


async def _run_phase15(session):
    """Run the ACTUAL entry point; the scorer is pinned so it cannot be the mover."""
    from app.tasks import prediction_market_matching as task_mod

    stats = {
        "orphaned_snapshots_deleted": 0,
        "funnel": {"stale_relinked": 0, "mislink_fixed": 0},
    }
    link_changes = []
    scorer = AsyncMock(return_value=None)
    with patch.object(task_mod, "_find_matching_event", new=scorer):
        await task_mod._phase15_revalidate(
            _AsyncShim(session), stats, NOW, lambda: 600.0, link_changes,
        )
    session.commit()
    return stats, link_changes


@pytest.mark.asyncio
async def test_a_reversed_shadows_market_moves_to_the_nhl_row():
    """🔴 THE SHIP. The Blues–Sharks NHL page gets Polymarket's market."""
    session, nhl, other = _new_rail()
    shadow = _shadow(session, other)
    real = _nhl_row(session, nhl)
    market = _market(session, shadow)

    stats, link_changes = await _run_phase15(session)

    session.refresh(market)
    assert market.event_id == real.id, (
        f"the market stayed on the shadow (event_id={market.event_id}, "
        f"shadow={shadow.id}, real={real.id}) — two cards, one venue each"
    )
    assert market.sport_id == nhl.id
    assert stats["funnel"]["phase15_catchall_shadow_named"] == 1
    assert link_changes, "the move published no receipt (LINKLOSS-02)"


@pytest.mark.asyncio
async def test_a_same_orientation_shadow_moves_too():
    """The rule is the row's provenance, not its orientation."""
    session, nhl, other = _new_rail()
    shadow = _shadow(session, other, away="Sharks", home="Blues")
    real = _nhl_row(session, nhl)
    market = _market(session, shadow)

    await _run_phase15(session)

    session.refresh(market)
    assert market.event_id == real.id


@pytest.mark.asyncio
async def test_the_shadow_row_is_left_standing():
    """Ruling 048: a POINTER moves; nothing is absorbed, retired or rewritten."""
    from app.models.models import Event

    session, nhl, other = _new_rail()
    shadow = _shadow(session, other)
    _nhl_row(session, nhl)
    _market(session, shadow)

    await _run_phase15(session)

    still = session.get(Event, shadow.id)
    assert still is not None
    assert still.status == "scheduled"
    assert (still.away_team_name, still.home_team_name) == ("Blues", "Sharks")


@pytest.mark.asyncio
async def test_no_nhl_row_yet_leaves_the_market_where_it_is():
    """🔴 The window before StatPal schedules the game: the shadow is the only row."""
    session, nhl, other = _new_rail()
    shadow = _shadow(session, other)
    market = _market(session, shadow)

    stats, _ = await _run_phase15(session)

    session.refresh(market)
    assert market.event_id == shadow.id
    assert stats["funnel"]["phase15_catchall_shadow_left_alone"] == 1


@pytest.mark.parametrize(
    "shadow_kwargs",
    [
        {"external_id": "4b675b1d1c46d02ad5a8887c956e93cf"},
        {"espn_id": "401891825"},
        {"statpal_fixture_id": "652999"},
        {"status": "live"},
        {"source": "odds_api"},
    ],
    ids=["external_id", "espn_id", "statpal_fixture_id", "live", "not_venue_clock"],
)
@pytest.mark.asyncio
async def test_a_row_that_is_not_a_venue_mint_is_untouched(shadow_kwargs):
    """🔴 Somebody's scheduled fixture, a live game, or a row on another clock."""
    session, nhl, other = _new_rail()
    shadow = _shadow(session, other, **shadow_kwargs)
    _nhl_row(session, nhl, espn_id="401891826")
    market = _market(session, shadow)

    stats, _ = await _run_phase15(session)

    session.refresh(market)
    assert market.event_id == shadow.id, (
        f"a {shadow_kwargs} row lost its market to the shadow arm"
    )
    assert "phase15_catchall_shadow_named" not in stats["funnel"]


@pytest.mark.asyncio
async def test_bruins_utah_is_resolved_inside_hockey():
    """🔴 ESPN UTA @ BOS, Oct 8: both nicknames also name college programs.

    Without the shadow's sport the resolver shares four leagues and refuses; the
    `icehockey_other` row says the game is hockey, and inside hockey the pair
    fields one league.
    """
    session, nhl, other = _new_rail()
    shadow = _shadow(session, other, away="Bruins", home="Utah")
    real = _nhl_row(session, nhl, away="Utah Mammoth", home="Boston Bruins",
                    espn_id="401892457")
    market = _market(session, shadow, name="Utah vs. Bruins", external_id="1005100")

    await _run_phase15(session)

    session.refresh(market)
    assert market.event_id == real.id


@pytest.mark.asyncio
async def test_within_sport_narrows_and_never_widens():
    from app.tasks.prediction_market_matching import covered_league_for_matchup

    session, _nhl, _other = _new_rail()
    shim = _AsyncShim(session)

    assert await covered_league_for_matchup(
        shim, "Bruins", "Utah", unambiguous_only=True,
    ) is None, "the control: without the sport, four shared leagues refuse"
    assert await covered_league_for_matchup(
        shim, "Bruins", "Utah", unambiguous_only=True, within_sport="icehockey",
    ) == "icehockey_nhl"
    assert await covered_league_for_matchup(
        shim, "Bruins", "Utah", unambiguous_only=True, within_sport="basketball",
    ) is None, "a sport the pair does not share must resolve to nothing"


@pytest.mark.asyncio
async def test_a_kalshi_market_on_a_shadow_is_not_this_arms():
    session, nhl, other = _new_rail()
    shadow = _shadow(session, other)
    _nhl_row(session, nhl)
    _market(session, shadow, source="kalshi", external_id="KXNHLGAME-26OCT08SJSTL-STL")

    stats, _ = await _run_phase15(session)

    assert "phase15_catchall_shadow_named" not in stats["funnel"]


def test_the_shadow_predicate_reads_provenance_only():
    from types import SimpleNamespace

    from app.tasks.prediction_market_matching import _is_polymarket_catchall_shadow

    base = dict(
        commence_time_source=VENUE, external_id=None, espn_id=None,
        statpal_fixture_id=None, status="scheduled",
    )
    assert _is_polymarket_catchall_shadow(SimpleNamespace(**base))
    for field, value in (
        ("commence_time_source", "espn"), ("external_id", "x"), ("espn_id", "1"),
        ("statpal_fixture_id", "1"), ("status", "live"), ("status", "voided"),
    ):
        row = SimpleNamespace(**{**base, field: value})
        assert not _is_polymarket_catchall_shadow(row), field


# --------------------------------------------------------------------------
# Half 2 — the fold joins a reversed shadow once it carries nothing to union
# --------------------------------------------------------------------------


class _Sport:
    def __init__(self, id, key):
        self.id = id
        self.key = key


_SPORT_IDS = {"icehockey_nhl": 41, "icehockey_other": 42, "baseball_ncaa": 43,
              "baseball_other": 44}


class _Row:
    """The subset of `Event` the fold reads (not a MagicMock: truthy ids are the licence)."""

    def __init__(self, id, *, away, home, sport_key, sources=None, espn_id=None,
                 statpal_fixture_id=None, external_id=None, status="scheduled",
                 opening_home_probability=None):
        self.id = id
        self.sport_id = _SPORT_IDS[sport_key]
        self.sport = _Sport(self.sport_id, sport_key)
        self.away_team_name = away
        self.home_team_name = home
        self.commence_time = PUCK_DROP
        self.external_id = external_id
        self.espn_id = espn_id
        self.statpal_fixture_id = statpal_fixture_id
        self.win_probability_sources = sources
        self.status = status
        self.home_score = None
        self.away_score = None
        self.opening_home_probability = opening_home_probability
        self.opening_away_probability = None


def _nhl(**kw):
    fields = dict(away=SHARKS, home=BLUES, sport_key="icehockey_nhl",
                  espn_id="401891825", sources={"kalshi": 0.53})
    fields.update(kw)
    return _Row(15169788, **fields)


def _reversed_shadow(**kw):
    fields = dict(away="Blues", home="Sharks", sport_key="icehockey_other")
    fields.update(kw)
    return _Row(15310317, **fields)


def test_an_unpriced_reversed_shadow_folds_onto_the_nhl_row():
    """🔴 THE SHIP's second half: after the move, one card — the NHL row's."""
    result = fold_twin_events([_nhl(), _reversed_shadow()])

    assert [row.id for row in result.events] == [15169788]
    assert result.survivor_of == {15310317: 15169788}


def test_a_priced_reversed_shadow_still_stays_two_cards():
    """🔴 #9304: its home number would land on the other club."""
    result = fold_twin_events([_nhl(), _reversed_shadow(sources={"polymarket": 0.465})])

    assert sorted(row.id for row in result.events) == [15169788, 15310317]


def test_a_reversed_shadow_with_an_opening_line_stays_two_cards():
    result = fold_twin_events([_nhl(), _reversed_shadow(opening_home_probability=0.45)])

    assert sorted(row.id for row in result.events) == [15169788, 15310317]


def test_an_unpriced_reversed_shadow_must_still_name_both_clubs():
    result = fold_twin_events([_nhl(), _reversed_shadow(away="Kings")])

    assert sorted(row.id for row in result.events) == [15169788, 15310317]


def test_an_unpriced_reversed_college_pair_still_refuses():
    """The measured college false fold, reversed: `_both_sides_may_differ` still gates."""
    league = _Row(14707767, away="West Georgia", home="North Florida",
                  sport_key="baseball_ncaa", external_id="odds-west-georgia")
    claim = _Row(14706238, away="Florida", home="Georgia", sport_key="baseball_other")

    result = fold_twin_events([league, claim])

    assert sorted(row.id for row in result.events) == [14706238, 14707767]


@pytest.mark.asyncio
async def test_the_shadows_polymarket_blend_key_leaves_with_the_market():
    """The shadow must stop speaking for a market it no longer holds — that
    unpriced state is what licenses the fold's second half."""
    from app.models.models import Event

    session, nhl, other = _new_rail()
    shadow = _shadow(session, other, sources={"polymarket": {"value": 0.465}})
    _nhl_row(session, nhl)
    _market(session, shadow)

    stats, _ = await _run_phase15(session)

    session.expire_all()
    left = session.get(Event, shadow.id).win_probability_sources or {}
    assert "polymarket" not in left, f"the shadow still carries {left}"
    assert stats.get("phantom_blend_sources_pruned") == 1
