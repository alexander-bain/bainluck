"""#11579 — Games This Week stops printing a leg the market's own page refuses.

WHAT A READER SAW (shopper, 390px, 2026-10-24 05:30Z), after #11579's first fix
went live: `/futures/412` — KXNBAMIMP-26, last season's Most Improved Player —
read "No current prices for this market" under All Outcomes
(`prices_withheld: 59` of 59), while Games This Week on the SAME screen printed

    Tomorrow 5:30 PM · Houston Rockets at Atlanta Hawks ·
    Reed Sheppa… 1% · Nickeil Alexander-Walk… >99%

`GET /api/futures/412/related-events` served the Hawks row as outcome 4664,
probability 0.995, american_odds -19900. `get_related_events` built its
`team_outcome_map` from the raw column and asked no refusal at all.

═══ THE ARMS ═══

  * **SPECIMEN, END TO END**: production's shape (legs written 182 days ago, the
    venue's "over" marker 48 days ago, a Discover LLM write 1 hour ago, the fleet
    observed now) through the REAL `_page_withheld_outcome_ids`. Second half
    (v5913, shopper): nulling the number left last season's names under "Each
    team's leading player", so the strip serves NO events and the page renders
    no section.
  * **ONE TEAM REFUSED**: that team leaves the game row and the event read; the
    shown team keeps its row.
  * **CONTROL**: the identical board with no venue marker is acquitted by the
    parent clause and keeps its prices, so the arm above is the stopped-board
    rule firing, not a route that blanks everything.
  * **LEADER ON THE SERVED VALUE**: a refused 0.995 never takes a team's row from
    a teammate whose price is shown.
  * **FAILS OPEN**: a refusal that raises keeps the strip and its prices, loudly.

Dates are offsets from one anchor, never branches on the clock (gotcha #44).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import pytest

from app.models import Event, FuturesMarket, FuturesOutcome, Sport, Team
from app.routes import league_futures
from app.routes.futures import get_related_events
from app.utils.futures_liveness import VENUE_SETTLED_KEY

NOW = datetime.now(timezone.utc).replace(microsecond=0)
TOUCHED = NOW - timedelta(hours=1)
VENUE_OVER = NOW - timedelta(days=48)
LEGS = NOW - timedelta(days=182)
TIPOFF = NOW + timedelta(days=1)

NBA = Sport(id=4, key="basketball_nba", name="NBA")
HAWKS = Team(id=7101, sport_id=NBA.id, name="Atlanta Hawks")
ROCKETS = Team(id=7102, sport_id=NBA.id, name="Houston Rockets")


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _Session:
    """Answers each statement by what it selects, and records anything else.

    The market read, the fleet's newest observation (the one read the stopped
    board rule makes), the team-name read and the event read. A statement none
    of those is recorded in `unexpected` and answered empty, so an arm that
    grows a new query shows up in the assertion rather than in a misread row.
    """

    def __init__(self, market, events):
        self._market = market
        self._events = events
        self.unexpected = []
        self.event_statements = []

    async def execute(self, statement):
        cols = getattr(statement, "column_descriptions", None) or []
        entities = {c.get("entity") for c in cols}
        names = [c.get("name") for c in cols]
        if entities == {FuturesMarket}:
            return _Result([self._market])
        if entities == {Event}:
            self.event_statements.append(statement)
            return _Result(self._events)
        if entities == {Team}:
            return _Result([(t.id, t.name) for t in (HAWKS, ROCKETS)])
        if len(cols) == 1 and names[0] == "max":
            return _Result([NOW])
        self.unexpected.append(str(statement))
        return _Result([])


def _outcome(oid, name, team, p, odds, *, rank):
    return FuturesOutcome(
        id=oid, market_id=412, name=name, team_id=team.id,
        current_probability=p, current_american_odds=odds, rank=rank,
        last_updated=LEGS, is_winner=None,
    )


def _mip(*, marker: bool, outcomes=None) -> FuturesMarket:
    """Market 412 as production stored it (db-query 2026-10-24), two legs."""
    market = FuturesMarket(
        id=412, source="kalshi", external_id="KXNBAMIMP-26",
        name="Most Improved Player Winner", category="championship",
        llm_sport_category="basketball", status="open", updated_at=TOUCHED,
        market_metadata=(
            {VENUE_SETTLED_KEY: VENUE_OVER.strftime("%Y-%m-%dT%H:%M:%S")}
            if marker else {}
        ),
    )
    market.outcomes = outcomes or [
        _outcome(4664, "Nickeil Alexander-Walker", HAWKS, 0.995, -19900, rank=1),
        _outcome(4665, "Reed Sheppard", ROCKETS, 0.01, 9900, rank=2),
    ]
    return market


def _rockets_at_hawks() -> list[Event]:
    game = Event(
        id=15334920, sport_id=NBA.id,
        home_team_id=HAWKS.id, away_team_id=ROCKETS.id,
        home_team_name="Atlanta Hawks", away_team_name="Houston Rockets",
        status="scheduled", commence_time=TIPOFF,
    )
    game.sport = NBA
    return [game]


async def _linked(market):
    session = _Session(market, _rockets_at_hawks())
    payload = await get_related_events(412, db=session)
    (event,) = payload["events"]
    return {lt["side"]: lt for lt in event["linked_teams"]}, session


@pytest.mark.asyncio
async def test_the_specimen_serves_no_strip_for_a_board_its_page_refuses():
    session = _Session(_mip(marker=True), _rockets_at_hawks())
    payload = await get_related_events(412, db=session)

    assert payload["events"] == [], (
        f"Games This Week serves {payload['events']} on a board /api/futures/412 "
        "withholds: the strip printed last season's 'leading player' names under "
        "'No current prices' (#11579)"
    )
    assert payload["total_count"] == 0
    assert session.event_statements == [], "no shown team, so no event read"
    assert session.unexpected == []


@pytest.mark.asyncio
async def test_a_team_whose_every_leg_is_refused_drops_out_of_the_game_row(monkeypatch):
    async def _refuse_the_hawks(db, market):
        return {4664}

    monkeypatch.setattr(league_futures, "_page_withheld_outcome_ids", _refuse_the_hawks)

    rows, session = await _linked(_mip(marker=False))

    assert set(rows) == {"away"}, (
        f"the Hawks row is still served as {rows.get('home')} with every Hawks leg refused"
    )
    assert rows["away"]["outcome_name"] == "Reed Sheppard"
    assert rows["away"]["probability"] == pytest.approx(0.01)
    (statement,) = session.event_statements
    sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert str(ROCKETS.id) in sql
    assert str(HAWKS.id) not in sql, (
        "the event read is still keyed by a team with nothing shown, so a game only "
        "that team plays can take a card slot"
    )


@pytest.mark.asyncio
async def test_control_the_same_board_without_the_venue_marker_keeps_its_prices():
    rows, session = await _linked(_mip(marker=False))

    assert rows["home"]["probability"] == pytest.approx(0.995)
    assert rows["home"]["american_odds"] == -19900
    assert rows["away"]["probability"] == pytest.approx(0.01)
    assert session.unexpected == []


@pytest.mark.asyncio
async def test_a_refused_leader_never_takes_the_row_from_a_shown_teammate(monkeypatch):
    field = [
        _outcome(4664, "Nickeil Alexander-Walker", HAWKS, 0.995, -19900, rank=1),
        _outcome(4666, "Onyeka Okongwu", HAWKS, 0.01, 9900, rank=3),
        _outcome(4665, "Reed Sheppard", ROCKETS, 0.01, 9900, rank=2),
    ]

    async def _refuse_the_favourite(db, market):
        return {4664}

    monkeypatch.setattr(league_futures, "_page_withheld_outcome_ids", _refuse_the_favourite)

    rows, _ = await _linked(_mip(marker=False, outcomes=field))

    hawks = rows["home"]
    assert hawks["outcome_name"] == "Onyeka Okongwu", (
        "the refused 0.995 still leads the Hawks row; it serves null where a "
        "shown teammate has a price"
    )
    assert hawks["probability"] == pytest.approx(0.01)


@pytest.mark.asyncio
async def test_a_refusal_that_raises_keeps_the_strip_and_says_so(monkeypatch, caplog):
    async def _broken(db, market):
        raise RuntimeError("refusal unavailable")

    monkeypatch.setattr(league_futures, "_page_withheld_outcome_ids", _broken)

    with caplog.at_level(logging.WARNING, logger="app.routes.futures"):
        rows, _ = await _linked(_mip(marker=True))

    assert rows["home"]["probability"] == pytest.approx(0.995)
    assert "could not evaluate the price refusal for market 412" in caplog.text
