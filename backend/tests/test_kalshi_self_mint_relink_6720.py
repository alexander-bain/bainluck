"""A soccer match's page carries Kalshi's price — #6720, the Kalshi self-mint.

**SHIP: Leganés v Castellón (and every game like it) shows Kalshi in its number,
instead of Kalshi's markets sitting on a second, hidden copy of the game.**
(Pillar: MATCHING.)

When a Kalshi game market finds no row, ruling 048 mints one from the market's
own label and Kalshi's close time. Every later Kalshi market of that game then
lands on the mint, and the real fixture shows no Kalshi at all. Production
2026-09-28 17:20Z:

    15318965  Leganes v Castellon      21:30Z  kalshi-minted, no ids   4 Kalshi markets
    15316746  Leganés v CD Castellón   18:30Z  Odds API + StatPal      0 Kalshi markets

The Phase 1.5 arm that used to revalidate market-born rows reads
``external_id LIKE 'pm_%'`` — a shape the registry has not written since
2026-08-17 — so nothing ever moved them. The new arm names the mint by its
provenance and moves the market onto the ONE scheduled row of the game.

WHAT EACH TEST DEFENDS:

* the ship — the market moves, the receipt says why, the mint stays standing
  and stops blending Kalshi;
* 🔴 no scheduled row yet, two scheduled rows, a destination that is itself a
  mint, a retired row, another sport, outside the ticker's window → no move;
* 🔴 a row somebody scheduled, a Polymarket market, a tennis mint → not this arm;
* the predicate reads provenance only.
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


# The production specimen, verbatim (read 2026-09-28 17:2xZ).
TICKER = "KXLALIGA2GAME-26SEP28LEGCAS"
KALSHI_NAME = "Leganes vs Castellon"
KICKOFF = datetime(2026, 9, 28, 18, 30, tzinfo=timezone.utc)
KALSHI_CLOCK = KICKOFF + timedelta(hours=3)  # the contract's close, gotcha #14
NOW = datetime(2026, 9, 28, 17, 30, tzinfo=timezone.utc)
MINT_TAGS = ["provenance:source:kalshi", "provenance:unanchored"]


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

    segunda = Sport(key="soccer_spain_segunda_division", name="Segunda")
    la_liga = Sport(key="soccer_spain_la_liga", name="La Liga")
    tennis = Sport(key="tennis_atp", name="ATP")
    session.add_all([segunda, la_liga, tennis])
    session.flush()
    return session, segunda, la_liga, tennis


def _mint(session, sport, *, home="Leganes", away="Castellon", status="scheduled",
          tags=MINT_TAGS, sources=None, **ids):
    """The Kalshi market's own row: its label, Kalshi's clock, no id."""
    from app.models.models import Event

    e = Event(
        sport_id=sport.id, home_team_name=home, away_team_name=away,
        commence_time=KALSHI_CLOCK, status=status, commence_time_source="kalshi",
        event_tags=list(tags), win_probability_sources=sources, **ids,
    )
    session.add(e)
    session.flush()
    return e


def _scheduled(session, sport, *, home="Leganés", away="CD Castellón", at=KICKOFF,
               status="scheduled", external_id="52ddb81b6601824c1444b86aac5f8902",
               tags=("provenance:source:odds_api", "provenance:unanchored"), **ids):
    """The row the sportsbooks scheduled — the game's real page."""
    from app.models.models import Event

    e = Event(
        sport_id=sport.id, home_team_name=home, away_team_name=away,
        commence_time=at, status=status, external_id=external_id,
        commence_time_source="odds_api", event_tags=list(tags), **ids,
    )
    session.add(e)
    session.flush()
    return e


def _market(session, event, *, name=KALSHI_NAME, source="kalshi", external_id=TICKER):
    from app.models.models import FuturesMarket

    m = FuturesMarket(
        source=source, external_id=external_id, name=name,
        category="sports", status="open", event_id=event.id,
        sport_id=event.sport_id, llm_sport_category="soccer",
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


async def _moved(session, market) -> int:
    session.refresh(market)
    return market.event_id


# --------------------------------------------------------------------------
# The ship
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_kalshi_market_moves_to_the_scheduled_row():
    """🔴 THE SHIP. Leganés v Castellón's page gets Kalshi's market."""
    session, segunda, _, _ = _new_rail()
    mint = _mint(session, segunda)
    real = _scheduled(session, segunda, statpal_fixture_id="9589325")
    market = _market(session, mint)

    stats, link_changes = await _run_phase15(session)

    assert await _moved(session, market) == real.id, (
        f"the market stayed on the mint {mint.id} — the real page shows no Kalshi"
    )
    assert market.sport_id == segunda.id
    assert stats["funnel"]["phase15_kalshi_self_mint_named"] == 1
    assert stats["funnel"]["phase15_kalshi_self_mint_relinked"] == 1
    assert stats["funnel"].get("phase15_venue_instant_relinked") is None
    assert link_changes, "the move published no receipt (LINKLOSS-02)"


@pytest.mark.asyncio
async def test_a_liga_mx_evening_game_on_the_next_utc_day_moves_too():
    """Puebla v León 10-10 01:00Z is the 10-09 ticker's game (production 15319204 →
    15320914, ESPN 401876954): the date-only window reaches the next UTC day."""
    session, segunda, _, _ = _new_rail()
    mint = _mint(session, segunda, home="Puebla", away="Leon")
    real = _scheduled(
        session, segunda, home="Puebla", away="León",
        at=datetime(2026, 10, 10, 1, 0, tzinfo=timezone.utc),
        espn_id="401876954",
    )
    market = _market(
        session, mint, name="Puebla vs Leon",
        external_id="KXLIGAMXGAME-26OCT09PUELEO",
    )

    await _run_phase15(session)

    assert await _moved(session, market) == real.id


@pytest.mark.asyncio
async def test_the_mint_is_left_standing_and_stops_blending_kalshi():
    """Ruling 048: a POINTER moves; nothing is absorbed. And the mint must stop
    speaking for a market it no longer holds."""
    from app.models.models import Event

    session, segunda, _, _ = _new_rail()
    mint = _mint(session, segunda, sources={"kalshi": {"value": 0.47}})
    _scheduled(session, segunda)
    _market(session, mint)

    stats, _ = await _run_phase15(session)

    session.expire_all()
    still = session.get(Event, mint.id)
    assert still is not None and still.status == "scheduled"
    assert (still.home_team_name, still.away_team_name) == ("Leganes", "Castellon")
    assert "kalshi" not in (still.win_probability_sources or {})
    assert stats.get("phantom_blend_sources_pruned") == 1


# --------------------------------------------------------------------------
# The destination must be the ONE scheduled row of the game
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_scheduled_row_yet_leaves_the_market_on_the_mint():
    session, segunda, _, _ = _new_rail()
    mint = _mint(session, segunda)
    market = _market(session, mint)

    stats, _ = await _run_phase15(session)

    assert await _moved(session, market) == mint.id
    assert stats["funnel"].get("phase15_kalshi_self_mint_named") is None


@pytest.mark.asyncio
async def test_two_scheduled_rows_is_ambiguous_and_nothing_moves():
    """A twin pair (or a doubleheader) is #1946's to tell apart, not this pass's."""
    session, segunda, _, _ = _new_rail()
    mint = _mint(session, segunda)
    _scheduled(session, segunda)
    _scheduled(session, segunda, home="Leganes", away="Castellon",
               external_id="other-ingest-hash")
    market = _market(session, mint)

    await _run_phase15(session)

    assert await _moved(session, market) == mint.id


@pytest.mark.asyncio
async def test_a_destination_that_is_itself_a_mint_is_never_chosen():
    """São Paulo v Santos (production 15314945 / 15315619): the other row is
    Polymarket's own mint with no id. Moving between two mints is churn."""
    session, segunda, _, _ = _new_rail()
    mint = _mint(session, segunda)
    _scheduled(session, segunda, external_id=None,
               tags=("provenance:source:polymarket", "provenance:unanchored"))
    market = _market(session, mint)

    await _run_phase15(session)

    assert await _moved(session, market) == mint.id


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["voided", "merged"])
async def test_a_retired_row_is_never_chosen(status):
    session, segunda, _, _ = _new_rail()
    mint = _mint(session, segunda)
    _scheduled(session, segunda, status=status)
    market = _market(session, mint)

    await _run_phase15(session)

    assert await _moved(session, market) == mint.id


@pytest.mark.asyncio
async def test_a_row_in_another_sport_is_never_chosen():
    session, segunda, la_liga, _ = _new_rail()
    mint = _mint(session, segunda)
    _scheduled(session, la_liga)
    market = _market(session, mint)

    await _run_phase15(session)

    assert await _moved(session, market) == mint.id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "offset",
    [timedelta(hours=-6, minutes=-1), timedelta(hours=30, minutes=1)],
    ids=["before-the-window", "after-the-window"],
)
async def test_a_row_outside_the_tickers_window_is_never_chosen(offset):
    session, segunda, _, _ = _new_rail()
    mint = _mint(session, segunda)
    ticker_date = datetime(2026, 9, 28, tzinfo=timezone.utc)
    _scheduled(session, segunda, at=ticker_date + offset)
    market = _market(session, mint)

    await _run_phase15(session)

    assert await _moved(session, market) == mint.id


@pytest.mark.asyncio
async def test_a_row_with_one_side_only_is_never_chosen():
    session, segunda, _, _ = _new_rail()
    mint = _mint(session, segunda)
    _scheduled(session, segunda, away="Eldense")
    market = _market(session, mint)

    await _run_phase15(session)

    assert await _moved(session, market) == mint.id


# --------------------------------------------------------------------------
# Who this arm is for
# --------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mint_kwargs",
    [
        {"external_id": "52ddb81b-scheduled"},
        {"espn_id": "401800001"},
        {"statpal_fixture_id": "9589325"},
        {"tags": ["provenance:source:polymarket", "provenance:unanchored"]},
    ],
    ids=["has-external-id", "has-espn-id", "has-statpal-id", "polymarket-mint"],
)
async def test_a_row_that_is_not_a_kalshi_self_mint_is_untouched(mint_kwargs):
    session, segunda, _, _ = _new_rail()
    row = _mint(session, segunda, **mint_kwargs)
    _scheduled(session, segunda)
    market = _market(session, row)

    stats, _ = await _run_phase15(session)

    assert await _moved(session, market) == row.id
    assert stats["funnel"].get("phase15_kalshi_self_mint_named") is None


@pytest.mark.asyncio
async def test_a_polymarket_market_on_a_kalshi_mint_is_not_this_arms():
    session, segunda, _, _ = _new_rail()
    mint = _mint(session, segunda)
    _scheduled(session, segunda)
    market = _market(session, mint, name="Leganés vs. Castellón",
                     source="polymarket", external_id="1097999")

    stats, _ = await _run_phase15(session)

    assert await _moved(session, market) == mint.id
    assert stats["funnel"].get("phase15_kalshi_self_mint_named") is None


@pytest.mark.asyncio
async def test_a_tennis_mint_is_left_to_the_tennis_pairing():
    session, _, _, tennis = _new_rail()
    mint = _mint(session, tennis, home="Alcaraz", away="Michelsen")
    _scheduled(session, tennis, home="Carlos Alcaraz", away="Alex Michelsen")
    market = _market(session, mint, name="Alcaraz vs Michelsen",
                     external_id="KXATPMATCH-26SEP28ALCMIC")

    stats, _ = await _run_phase15(session)

    assert await _moved(session, market) == mint.id
    assert stats["funnel"].get("phase15_kalshi_self_mint_named") is None


def test_the_self_mint_predicate_reads_provenance_only():
    from types import SimpleNamespace

    from app.tasks.prediction_market_matching import _is_kalshi_self_mint

    def row(**kw):
        base = dict(event_tags=list(MINT_TAGS), external_id=None, espn_id=None,
                    statpal_fixture_id=None)
        base.update(kw)
        return SimpleNamespace(**base)

    assert _is_kalshi_self_mint(row())
    assert not _is_kalshi_self_mint(row(event_tags=None))
    assert not _is_kalshi_self_mint(row(event_tags=["provenance:unanchored"]))
    assert not _is_kalshi_self_mint(row(external_id="x"))
    assert not _is_kalshi_self_mint(row(espn_id="1"))
    assert not _is_kalshi_self_mint(row(statpal_fixture_id="1"))


# --------------------------------------------------------------------------
# The forward half: the windowed search folds accents on Postgres
# --------------------------------------------------------------------------


def test_the_folded_arm_renders_translate_on_postgres_and_plain_lower_on_sqlite():
    """The behaviour is proven on real Postgres (the #8440 PG gate); this pins
    WHICH expression each dialect gets, so the SQLite replay rendering can never
    leak into production."""
    from sqlalchemy.dialects import postgresql, sqlite

    from app.tasks.prediction_market_matching import _folded_name_contains_conditions

    home, _away = _folded_name_contains_conditions("Leganés")
    pg = str(home.compile(dialect=postgresql.dialect(),
                          compile_kwargs={"literal_binds": True}))
    lite = str(home.compile(dialect=sqlite.dialect(),
                            compile_kwargs={"literal_binds": True}))
    assert "translate(lower(events.home_team_name)" in pg and "leganes%" in pg, pg
    assert "translate" not in lite and "lower(events.home_team_name)" in lite, lite
    assert _folded_name_contains_conditions("") == []
