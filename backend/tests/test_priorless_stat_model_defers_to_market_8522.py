"""#8522 — a priorless stat model must not outvote the only market on the game.

At puck drop on 2026-09-25 02:09Z, `/events/15314368` (Anaheim Ducks at San
Jose Sharks, NHL preseason) fell from Kalshi's 73% to a flat 50% and then
followed the stat model while Kalshi read 0.70–0.91. No sportsbook prices
preseason, so the row has neither `opening_home_probability` nor
`opening_home_spread`: the model has no prior and centres on a pick'em. With
two sources — Kalshi (0.8) and the model (1.0) — the weighted median returns
the heavier one verbatim.

The fix: both stat-model writers skip the reading while the model has no prior
and the row already holds a market price. Guarded here in both directions:
the specimen stops writing, and the two twins that must keep writing (a game
with no market at all; a game whose model has a prior) still do.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event as sa_event
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles

from app.services.espn_api import ESPNEvent, ESPNTeam
from app.utils.win_probability import (
    MARKET_PRICE_SOURCES,
    priorless_model_defers_to_market,
)


@compiles(JSONB, "sqlite")
def _jsonb_sqlite(type_, compiler, **kw):  # pragma: no cover - test rail
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_sqlite(type_, compiler, **kw):  # pragma: no cover - test rail
    return "JSON"


KALSHI_JUST_BEFORE = 0.74  # the specimen's Kalshi reading at 02:08:48Z
STAMP = "2026-09-25T02:09:30+00:00"


# ---------------------------------------------------------------------------
# 1. The rule
# ---------------------------------------------------------------------------


def test_priorless_with_a_kalshi_reading_defers_8522():
    """THE SPECIMEN'S SHAPE: no spread, no opening, Kalshi on the row."""
    sources = {"kalshi": {"value": KALSHI_JUST_BEFORE, "updated_at": STAMP}}
    assert priorless_model_defers_to_market(None, None, sources) is True


@pytest.mark.parametrize("source", MARKET_PRICE_SOURCES)
def test_every_market_source_counts_in_either_stored_shape_8522(source):
    """The column holds bare floats AND stamped dicts; both are a price."""
    assert priorless_model_defers_to_market(None, None, {source: 0.6}) is True
    assert (
        priorless_model_defers_to_market(
            None, None, {source: {"value": 0.6, "updated_at": STAMP}}
        )
        is True
    )


def test_a_game_with_no_market_keeps_its_model_8522():
    """The model is the only number there is — deferring would blank it."""
    assert priorless_model_defers_to_market(None, None, {}) is False
    assert priorless_model_defers_to_market(None, None, None) is False
    assert (
        priorless_model_defers_to_market(
            None, None, {"stat_model": 0.5, "espn": 0.61, "mlb": 0.55}
        )
        is False
    )


def test_a_market_key_without_a_number_is_not_a_price_8522():
    assert (
        priorless_model_defers_to_market(
            None, None, {"kalshi": {"value": None}, "polymarket": True}
        )
        is False
    )


def test_a_model_with_a_prior_never_defers_8522():
    """An opening price or a spread is a prior; that model keeps its vote."""
    sources = {"kalshi": KALSHI_JUST_BEFORE}
    assert priorless_model_defers_to_market(None, 0.74, sources) is False
    assert priorless_model_defers_to_market(-1.5, None, sources) is False
    # 0.0 is a pick'em spread, a real prior — not "absent".
    assert priorless_model_defers_to_market(0.0, None, sources) is False


# ---------------------------------------------------------------------------
# 2. The ESPN-sync writer, on a real row
# ---------------------------------------------------------------------------

SHARKS = ESPNTeam(
    espn_id="18",
    name="Sharks",
    abbreviation="SJ",
    display_name="San Jose Sharks",
    short_name="Sharks",
    nickname="San Jose",
    primary_color=None,
    secondary_color=None,
    logo_url=None,
    logo_url_dark=None,
    record=None,
    location="San Jose",
)
DUCKS = ESPNTeam(
    espn_id="25",
    name="Ducks",
    abbreviation="ANA",
    display_name="Anaheim Ducks",
    short_name="Ducks",
    nickname="Anaheim",
    primary_color=None,
    secondary_color=None,
    logo_url=None,
    logo_url_dark=None,
    record=None,
    location="Anaheim",
)


def _puck_drop_board_row():
    """ESPN's board row at 0–0 in the 1st, as `_parse_event` returns it."""
    return ESPNEvent(
        espn_id="401803915",
        name="Anaheim Ducks at San Jose Sharks",
        short_name="ANA @ SJ",
        date=None,
        status="in",
        status_detail="1st Period",
        period=1,
        clock="19:12",
        home_team=SHARKS,
        away_team=DUCKS,
        home_score=0,
        away_score=0,
        venue=None,
        broadcasts=[],
        home_win_probability=None,
    )


class _AsyncShim:
    """The writer is async and this engine is not; nothing else is shimmed."""

    def __init__(self, inner):
        self._s = inner

    async def execute(self, statement):
        return self._s.execute(statement)

    def add(self, obj):
        self._s.add(obj)

    async def flush(self):
        self._s.flush()

    async def commit(self):
        self._s.commit()


def _live_row_on_disk(*, sources, opening_home_probability=None):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.models.models import Base, Event, Sport, WinProbSnapshot

    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[Event.__table__, Sport.__table__, WinProbSnapshot.__table__],
    )
    session = Session(engine, expire_on_commit=False)

    @sa_event.listens_for(session, "loaded_as_persistent")
    def _reattach_utc(_sess, instance):  # pragma: no cover - test rail
        for attr, value in list(instance.__dict__.items()):
            if isinstance(value, datetime) and value.tzinfo is None:
                instance.__dict__[attr] = value.replace(tzinfo=timezone.utc)

    sport = Sport(key="icehockey_nhl", name="NHL")
    session.add(sport)
    session.flush()

    event = Event(
        sport_id=sport.id,
        home_team_name="San Jose Sharks",
        away_team_name="Anaheim Ducks",
        commence_time=datetime.now(timezone.utc) - timedelta(minutes=2),
        status="live",
        espn_id="401803915",
        commence_time_source="espn",
        opening_home_probability=opening_home_probability,
        opening_home_spread=None,
        win_probability_sources=sources,
    )
    session.add(event)
    session.commit()
    return session, event


async def _run_writer(session, event):
    from app.utils.espn_helpers import compute_and_write_stat_model

    stats: dict = {}
    wrote = await compute_and_write_stat_model(
        _AsyncShim(session),
        event,
        _puck_drop_board_row(),
        "icehockey_nhl",
        stats,
    )
    session.commit()
    session.expire_all()
    return wrote, stats


def _stored(session):
    from sqlalchemy import select

    from app.models.models import Event, WinProbSnapshot

    row = session.execute(select(Event)).scalar_one()
    snaps = (
        session.execute(
            select(WinProbSnapshot).where(WinProbSnapshot.source == "stat_model")
        )
        .scalars()
        .all()
    )
    return row, snaps


@pytest.mark.asyncio
async def test_the_specimen_writes_no_coin_flip_and_the_headline_is_kalshi_8522():
    """THE GUARD. Ducks at Sharks at puck drop: Kalshi 0.74, no prior."""
    from app.utils.aggregation import compute_aggregate_probability

    session, event = _live_row_on_disk(
        sources={"kalshi": {"value": KALSHI_JUST_BEFORE, "updated_at": STAMP}},
    )
    wrote, stats = await _run_writer(session, event)
    row, snaps = _stored(session)

    assert wrote is False
    assert stats.get("stat_model_priorless_deferred") == 1
    assert "stat_model" not in row.win_probability_sources, (
        "a priorless model reading 0.5 at 0–0 outweighs the lone Kalshi price "
        "and becomes the headline (#8522)"
    )
    assert snaps == [], "the chart's stat_model line would still carry the 50%"
    assert compute_aggregate_probability(row, row.status) == pytest.approx(
        KALSHI_JUST_BEFORE
    )


@pytest.mark.asyncio
async def test_a_game_with_no_market_still_gets_its_model_8522():
    """TWIN 1 — also proves the rig reaches the model at all."""
    session, event = _live_row_on_disk(sources={})
    wrote, stats = await _run_writer(session, event)
    row, snaps = _stored(session)

    assert wrote is True
    assert "stat_model_priorless_deferred" not in stats
    assert row.win_probability_sources["stat_model"]["value"] == pytest.approx(
        0.5, abs=0.02
    )
    assert len(snaps) == 1


@pytest.mark.asyncio
async def test_a_model_with_an_opening_price_still_votes_beside_kalshi_8522():
    """TWIN 2 — a prior restores the model's vote, and it starts from it."""
    session, event = _live_row_on_disk(
        sources={"kalshi": {"value": KALSHI_JUST_BEFORE, "updated_at": STAMP}},
        opening_home_probability=0.74,
    )
    wrote, stats = await _run_writer(session, event)
    row, _ = _stored(session)

    assert wrote is True
    assert "stat_model_priorless_deferred" not in stats
    assert row.win_probability_sources["stat_model"]["value"] > 0.6


# ---------------------------------------------------------------------------
# 3. The odds-poll writer (events without an ESPN link)
# ---------------------------------------------------------------------------


def test_the_odds_poll_writer_asks_the_same_rule_before_the_model_8522():
    """The second writer of `stat_model` (#1829) must defer the same way.

    Its loop is a live HTTP poll with no seam to drive a single game through,
    so this reads the source: the deferral check has to sit between the spread
    it reads and the model call, and has to be handed that spread, the opening
    price and the row's sources.
    """
    from app.tasks import odds_polling

    src = inspect.getsource(odds_polling)
    ask = src.index("if priorless_model_defers_to_market(")
    model = src.index("stat_wp = compute_statistical_win_prob(")
    spread = src.rindex("pregame_spread = float(event_obj.opening_home_spread)", 0, ask)
    assert spread < ask < model
    call = src[ask:model]
    assert "pregame_spread" in call
    assert "event_obj.opening_home_probability" in call
    assert "event_obj.win_probability_sources" in call
    assert "stat_model_priorless_deferred += 1" in call
