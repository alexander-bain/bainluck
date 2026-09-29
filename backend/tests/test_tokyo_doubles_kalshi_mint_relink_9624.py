"""A Tokyo doubles match carries its Kalshi price on its real row — #9624.

**SHIP: a Tokyo doubles match played Thursday shows up as Thursday's match with
its Kalshi price, not as a "No result reported · Sep 28" card on the ATP page.**
(Pillar: MATCHING.)

Production 2026-09-29 13:30Z, seven matches each stored twice:

    15320492  Bolelli / Vavassori v Mochizuki / Watanabe  tennis_atp    09-29 05:00Z
              suspended, Kalshi-minted, no ids             KXATPDOUBLES-26SEP28BOLVAVMOCWAT
    15321376  Bolelli/Vavassori v Mochizuki/Watanabe      tennis_other  10-01 01:00Z
              scheduled, StatPal 2638079                   0 Kalshi markets

The #6720 self-mint relink skipped tennis at its call site, and even if it had
run it would have missed twice: it searched the mint's OWN sport (the real row
is ``tennis_other``) and the date-only window, which ends 09-29 06:00Z — the
ticker's ``SEP28`` is the day Kalshi listed the draw, not the day of play. Then
the linkage guard's date-only rule (2 Eastern days) would have refused the move.

WHAT EACH TEST DEFENDS:

* the ship — the market moves, the receipt says why, a second pass keeps it;
* all six anchored specimens are named by the finder, verbatim;
* 🔴 the seventh (Galloway, real row carries no id) stays — NO_ANCHOR_CHANNEL;
* 🔴 a singles market, a singles row, a partner mismatch, a WTA row, two rows,
  outside the listing window → no move;
* 🔴 the guard: the listing window only for the tennis arm and only for a tennis
  segment ticker; everyone else keeps the 2-day rule.
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


# The production specimen, verbatim (read 2026-09-29 16:2xZ).
TICKER = "KXATPDOUBLES-26SEP28BOLVAVMOCWAT"
KALSHI_NAME = "Bolelli / Vavassori vs Mochizuki / Watanabe"
MINT_CLOCK = datetime(2026, 9, 29, 5, 0, tzinfo=timezone.utc)
MATCH_START = datetime(2026, 10, 1, 1, 0, tzinfo=timezone.utc)
TICKER_DAY = datetime(2026, 9, 28, tzinfo=timezone.utc)
NOW = datetime(2026, 9, 29, 16, 30, tzinfo=timezone.utc)
MINT_TAGS = ["provenance:source:kalshi", "provenance:unanchored"]

#: (ticker, Kalshi's name, the StatPal row's home, away, statpal id) — all six
#: anchored specimens of the issue's table, as production stores them.
SPECIMENS = [
    ("KXATPDOUBLES-26SEP28BOLVAVMOCWAT", "Bolelli / Vavassori vs Mochizuki / Watanabe",
     "Bolelli/Vavassori", "Mochizuki/Watanabe", "2638079"),
    ("KXATPDOUBLES-26SEP28JOHRIKPOLZIE", "Johnson / Rikl vs Polmans / Zielinski",
     "Johnson/Rikl", "Polmans/Zielinski", "2638078"),
    ("KXATPDOUBLES-26SEP28DARETCHIJUES", "Darderi / Etcheverry T vs Hijikata / Uesugi",
     "Darderi/Etcheverry", "Hijikata/Uesugi", "2638073"),
    ("KXATPDOUBLES-26SEP28KINNAKARROLI", "King / Nakashima vs Arribage / Olivetti",
     "King/Nakashima", "Arribage/Olivetti", "2638076"),
    ("KXATPDOUBLES-26SEP28MIEOBEBLOMIC", "Miedler / Oberleitner vs Blockx / Michelsen",
     "Miedler/Oberleitner", "Blockx/Michelsen", "2638077"),
    ("KXATPDOUBLES-26SEP28KRAMEKNOUVEN", "Krajicek / Mektic vs Nouza / Venus",
     "Krajicek/Mektic", "Nouza/Venus", "2638075"),
]


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

    sports = {
        key: Sport(key=key, name=key)
        for key in ("tennis_atp", "tennis_other", "tennis_wta")
    }
    session.add_all(sports.values())
    session.flush()
    return session, sports


def _mint(session, sport, *, home="Bolelli / Vavassori", away="Mochizuki / Watanabe",
          sources=None):
    """The Kalshi market's own row: its label, the ticker's clock, no id."""
    from app.models.models import Event

    e = Event(
        sport_id=sport.id, home_team_name=home, away_team_name=away,
        commence_time=MINT_CLOCK, status="suspended", commence_time_source="kalshi",
        event_tags=list(MINT_TAGS), win_probability_sources=sources,
    )
    session.add(e)
    session.flush()
    return e


def _real(session, sport, *, home="Bolelli/Vavassori", away="Mochizuki/Watanabe",
          at=MATCH_START, statpal_fixture_id="2638079", status="scheduled"):
    """The row StatPal scheduled — the match's real page."""
    from app.models.models import Event

    e = Event(
        sport_id=sport.id, home_team_name=home, away_team_name=away,
        commence_time=at, status=status, statpal_fixture_id=statpal_fixture_id,
        commence_time_source="polymarket_venue",
        event_tags=["provenance:source:polymarket", "provenance:unanchored"],
    )
    session.add(e)
    session.flush()
    return e


def _market(session, event, *, name=KALSHI_NAME, external_id=TICKER):
    from app.models.models import FuturesMarket

    m = FuturesMarket(
        source="kalshi", external_id=external_id, name=name,
        category="sports", status="open", event_id=event.id,
        sport_id=event.sport_id, llm_sport_category="tennis",
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


async def _event_of(session, market) -> int:
    session.refresh(market)
    return market.event_id


async def _find(session, market, mint):
    from app.tasks import prediction_market_matching as pmm
    from app.utils.prediction_market_matching import extract_matchup_with_ticker_fallback

    matchup = extract_matchup_with_ticker_fallback(market.name, external_id=market.external_id)
    return await pmm._kalshi_self_mint_real_fixture(
        _AsyncShim(session), matchup, market, mint, mint_sport_key="tennis_atp",
    )


# --------------------------------------------------------------------------
# The ship
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_kalshi_market_moves_onto_thursdays_row():
    """🔴 THE SHIP. Bolelli / Vavassori's Oct 1 row gets Kalshi's market."""
    session, sports = _new_rail()
    mint = _mint(session, sports["tennis_atp"], sources={"kalshi": {"home_prob": 0.6}})
    real = _real(session, sports["tennis_other"])
    market = _market(session, mint)

    stats, link_changes = await _run_phase15(session)

    assert await _event_of(session, market) == real.id, (
        f"the market stayed on the mint {mint.id} — Thursday's row has no Kalshi"
    )
    assert market.sport_id == sports["tennis_other"].id
    assert stats["funnel"]["phase15_kalshi_self_mint_named"] == 1
    assert stats["funnel"]["phase15_kalshi_self_mint_relinked"] == 1
    assert stats["funnel"].get("phase15_event_date_blocked") is None
    assert link_changes, "the move published no receipt (LINKLOSS-02)"
    session.refresh(mint)
    assert "kalshi" not in (mint.win_probability_sources or {}), (
        "the mint still blends the market it no longer holds"
    )


@pytest.mark.asyncio
async def test_a_second_pass_keeps_the_market_on_thursdays_row():
    """The next 15-minute pass must not undo the move (the #9504 flap shape)."""
    session, sports = _new_rail()
    mint = _mint(session, sports["tennis_atp"])
    real = _real(session, sports["tennis_other"])
    market = _market(session, mint)

    await _run_phase15(session)
    stats, _ = await _run_phase15(session)

    assert await _event_of(session, market) == real.id
    assert stats["funnel"].get("phase15_kalshi_self_mint_named") is None


def test_the_phase2_date_unlinks_leave_a_tennis_segment_ticker_alone():
    """Phase 2's two date-unlink arms are the other way back off the row."""
    from app.tasks.prediction_market_matching import WRONG_GAME_PREFIXES
    from app.utils.prediction_market_matching import is_kalshi_match_segment_ticker

    assert is_kalshi_match_segment_ticker(TICKER)
    assert TICKER.split("-")[0].lower() not in WRONG_GAME_PREFIXES


@pytest.mark.asyncio
@pytest.mark.parametrize("ticker,name,home,away,statpal", SPECIMENS)
async def test_every_anchored_specimen_is_named(ticker, name, home, away, statpal):
    session, sports = _new_rail()
    left, right = name.split(" vs ")
    mint = _mint(session, sports["tennis_atp"], home=left, away=right)
    real = _real(session, sports["tennis_other"], home=home, away=away,
                 statpal_fixture_id=statpal)
    market = _market(session, mint, name=name, external_id=ticker)

    found = await _find(session, market, mint)

    assert found == {"event_id": real.id, "sport_id": sports["tennis_other"].id}


@pytest.mark.asyncio
async def test_the_reversed_orientation_is_named_too():
    session, sports = _new_rail()
    mint = _mint(session, sports["tennis_atp"])
    real = _real(session, sports["tennis_other"],
                 home="Mochizuki/Watanabe", away="Bolelli/Vavassori")
    market = _market(session, mint)

    assert (await _find(session, market, mint))["event_id"] == real.id


# --------------------------------------------------------------------------
# 🔴 Refusals — every one leaves the market on the mint
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_galloway_whose_real_row_has_no_id_stays():
    """The issue's seventh row: 15321373 carries no provider id (NO_ANCHOR_CHANNEL)."""
    session, sports = _new_rail()
    name = "Galloway / Goransson vs Tabilo / van Assche"
    mint = _mint(session, sports["tennis_atp"],
                 home="Galloway / Goransson", away="Tabilo / van Assche")
    _real(session, sports["tennis_other"], home="Galloway/Goransson",
          away="Tabilo/Assche", statpal_fixture_id=None)
    market = _market(session, mint, name=name,
                     external_id="KXATPDOUBLES-26SEP28GALGORTABVAN")

    stats, _ = await _run_phase15(session)

    assert await _event_of(session, market) == mint.id
    assert stats["funnel"].get("phase15_kalshi_self_mint_named") is None


@pytest.mark.asyncio
async def test_a_singles_mint_is_still_left_to_the_twin_sweeps():
    session, sports = _new_rail()
    mint = _mint(session, sports["tennis_atp"], home="Bolelli", away="Mochizuki")
    _real(session, sports["tennis_other"], home="Simone Bolelli", away="Mochizuki")
    market = _market(session, mint, name="Bolelli vs Mochizuki",
                     external_id="KXATPMATCH-26SEP28BOLMOC")

    stats, _ = await _run_phase15(session)

    assert await _event_of(session, market) == mint.id
    assert stats["funnel"].get("phase15_kalshi_self_mint_named") is None


@pytest.mark.asyncio
async def test_a_singles_row_is_never_a_doubles_markets_destination():
    """#9600's shape, the other way round: two of the four players, as singles."""
    session, sports = _new_rail()
    mint = _mint(session, sports["tennis_atp"])
    _real(session, sports["tennis_other"], home="Bolelli", away="Mochizuki")
    market = _market(session, mint)

    assert await _find(session, market, mint) is None


@pytest.mark.asyncio
async def test_one_partner_different_is_another_pair():
    session, sports = _new_rail()
    mint = _mint(session, sports["tennis_atp"])
    _real(session, sports["tennis_other"], home="Bolelli/Fognini", away="Mochizuki/Watanabe")
    market = _market(session, mint)

    assert await _find(session, market, mint) is None


@pytest.mark.asyncio
async def test_a_wta_row_is_never_an_atp_markets_destination():
    session, sports = _new_rail()
    mint = _mint(session, sports["tennis_atp"])
    _real(session, sports["tennis_wta"])
    market = _market(session, mint)

    assert await _find(session, market, mint) is None


@pytest.mark.asyncio
async def test_the_mints_own_sport_is_still_searched():
    session, sports = _new_rail()
    mint = _mint(session, sports["tennis_atp"])
    real = _real(session, sports["tennis_atp"])
    market = _market(session, mint)

    assert (await _find(session, market, mint))["event_id"] == real.id


@pytest.mark.asyncio
async def test_two_anchored_rows_is_ambiguous_and_nothing_moves():
    session, sports = _new_rail()
    mint = _mint(session, sports["tennis_atp"])
    _real(session, sports["tennis_other"])
    _real(session, sports["tennis_atp"], statpal_fixture_id="2638999")
    market = _market(session, mint)

    stats, _ = await _run_phase15(session)

    assert await _event_of(session, market) == mint.id
    assert stats["funnel"].get("phase15_kalshi_self_mint_named") is None


@pytest.mark.asyncio
async def test_a_retired_row_is_never_chosen():
    session, sports = _new_rail()
    mint = _mint(session, sports["tennis_atp"])
    _real(session, sports["tennis_other"], status="voided")
    market = _market(session, mint)

    assert await _find(session, market, mint) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("at,named", [
    (TICKER_DAY - timedelta(hours=6), True),
    (TICKER_DAY - timedelta(hours=7), False),
    (TICKER_DAY + timedelta(hours=96), True),
    (TICKER_DAY + timedelta(hours=97), False),
])
async def test_the_listing_window_bounds(at, named):
    session, sports = _new_rail()
    mint = _mint(session, sports["tennis_atp"])
    real = _real(session, sports["tennis_other"], at=at)
    market = _market(session, mint)

    found = await _find(session, market, mint)

    assert (found == {"event_id": real.id, "sport_id": sports["tennis_other"].id}) is named


@pytest.mark.asyncio
async def test_the_non_tennis_arm_keeps_the_date_only_window():
    """Without a tennis sport key the same market sees the #6720 window, and misses."""
    from app.tasks import prediction_market_matching as pmm
    from app.utils.prediction_market_matching import extract_matchup_with_ticker_fallback

    session, sports = _new_rail()
    mint = _mint(session, sports["tennis_atp"])
    _real(session, sports["tennis_atp"])
    market = _market(session, mint)
    matchup = extract_matchup_with_ticker_fallback(market.name, external_id=market.external_id)

    assert await pmm._kalshi_self_mint_real_fixture(
        _AsyncShim(session), matchup, market, mint,
    ) is None


# --------------------------------------------------------------------------
# 🔴 The linkage guard
# --------------------------------------------------------------------------


async def _guard(session, event_id, external_id, *, tennis_listing_date):
    from types import SimpleNamespace

    from app.tasks import prediction_market_matching as pmm
    from app.utils.prediction_market_matching import extract_game_date_from_ticker

    market = SimpleNamespace(id=-1, source="kalshi", external_id=external_id)
    return await pmm._check_duplicate_kalshi_linkage_reason(
        _AsyncShim(session), event_id, market,
        extract_game_date_from_ticker(external_id),
        tennis_listing_date=tennis_listing_date,
    )


@pytest.mark.asyncio
async def test_the_date_only_rule_is_what_refused_the_move():
    """The mechanism: without the tennis window, arm (a) refuses Thursday's row."""
    from app.tasks.prediction_market_matching import _REFUSAL_EVENT_DATE

    session, sports = _new_rail()
    real = _real(session, sports["tennis_other"])

    assert await _guard(session, real.id, TICKER, tennis_listing_date=False) == _REFUSAL_EVENT_DATE
    assert await _guard(session, real.id, TICKER, tennis_listing_date=True) is None


@pytest.mark.asyncio
async def test_the_tennis_window_still_refuses_outside_itself():
    from app.tasks.prediction_market_matching import _REFUSAL_EVENT_DATE

    session, sports = _new_rail()
    late = _real(session, sports["tennis_other"], at=TICKER_DAY + timedelta(hours=100))

    assert await _guard(session, late.id, TICKER, tennis_listing_date=True) == _REFUSAL_EVENT_DATE


@pytest.mark.asyncio
async def test_a_non_tennis_ticker_never_gets_the_tennis_window():
    from app.tasks.prediction_market_matching import _REFUSAL_EVENT_DATE

    session, sports = _new_rail()
    real = _real(session, sports["tennis_other"])

    assert await _guard(
        session, real.id, "KXLALIGA2GAME-26SEP28LEGCAS", tennis_listing_date=True,
    ) == _REFUSAL_EVENT_DATE
