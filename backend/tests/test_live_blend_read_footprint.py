"""Fresh card probabilities: smaller reads must keep the same blend reading."""

from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime, timedelta, timezone

import pytest

from app.models.models import Event, FuturesMarket, FuturesOutcome
from app.tasks.live_blend_refresh import (
    LiveBlendRefresher,
    PREPARED_EVENT_FIELDS,
    PREPARED_MARKET_FIELDS,
    PREPARED_OUTCOME_FIELDS,
)
from app.utils.live_blend import MarketOutcomes, compute_source_home_probability


class Result:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class ReadSession:
    def __init__(self, events, markets, outcomes):
        self.events, self.markets, self.outcomes = events, markets, outcomes
        self.statements = []
        self.outcome_ids = None

    async def execute(self, statement):
        self.statements.append(statement)
        from app.utils.live_blend import is_game_winner_market

        self.outcome_ids = []
        rows = []
        for market in self.markets:
            event = next((e for e in self.events if e.id == market.event_id), None)
            if event is None:
                continue
            eligible = (
                market.source != "kalshi" or not market.external_id
                or is_game_winner_market(market)
            )
            if eligible:
                self.outcome_ids.append(market.id)
            outcomes = [
                o for o in self.outcomes if o.market_id == market.id
            ] if eligible else []
            for outcome in outcomes or [None]:
                rows.append(tuple(
                    getattr(obj, key, None)
                    for obj, keys in (
                        (market, PREPARED_MARKET_FIELDS),
                        (event, PREPARED_EVENT_FIELDS),
                        (outcome, PREPARED_OUTCOME_FIELDS),
                    ) for key in keys
                ))
        return Result(rows)


def event():
    return Event(
        id=1,
        home_team_name="Boston Celtics",
        away_team_name="Golden State Warriors",
        status="live",
        completed_at=None,
        commence_time=None,
        win_probability_sources={"espn": {"value": 0.7}},
        espn_win_prob_home=0.7,
        opening_home_probability=0.6,
        box_score_data={"players": ["unrelated large payload"]},
    )


def market(
    id,
    *,
    source="kalshi",
    ticker="KXNBAGAME-26OCT08BOSGSW-BOS",
    name="Celtics vs. Warriors",
    event_id=1,
):
    return FuturesMarket(
        id=id,
        event_id=event_id,
        source=source,
        external_id=ticker,
        name=name,
        status="open",
    )


def outcomes(market, *, home=0.67, seen=None):
    return [
        FuturesOutcome(
            id=market.id * 10,
            market_id=market.id,
            name="Boston Celtics",
            rank=1,
            current_probability=home,
            last_updated=seen,
        ),
        FuturesOutcome(
            id=market.id * 10 + 1,
            market_id=market.id,
            name="Golden State Warriors",
            rank=2,
            current_probability=1 - home,
            last_updated=seen,
        ),
    ]


def reading_signature(group):
    reading = compute_source_home_probability(
        group, "Boston Celtics", "Golden State Warriors"
    )
    if reading is None:
        return None
    return (
        reading.home_probability,
        reading.yes_probability,
        reading.devigged,
        reading.away_probability,
        reading.draw_probability,
        reading.named_home_quote,
        reading.named_two_way_devig,
        reading.market.id,
        reading.outcome.id,
        tuple(outcome.id for outcome in reading.contributing_outcomes),
        asdict(reading.eligibility) if reading.eligibility is not None else None,
    )


@pytest.mark.asyncio
async def test_read_projects_one_event_context_and_omits_only_impossible_kalshi_outcomes():
    e = event()
    winner = market(2)
    prop = market(1, ticker="KXNBAPOINTS-26OCT08-TATUM", name="Tatum points")
    missing_ticker = market(3, ticker=None)
    orphan = market(4, event_id=999)
    session = ReadSession(
        [e],
        [prop, winner, missing_ticker, orphan],
        sum((outcomes(m) for m in [prop, winner, missing_ticker, orphan]), []),
    )
    grouped = await LiveBlendRefresher("kalshi")._read_groups(session, [1, 999])
    assert list(grouped) == [1]
    assert [entry.market.id for entry in grouped[1][1]] == [1, 2, 3]
    assert session.outcome_ids == [
        2,
        3,
    ]  # A missing ticker is not a structural refusal.
    assert grouped[1][1][0].outcomes == []
    assert grouped[1][1][2].outcomes
    assert len(session.statements) == 1
    sql = str(session.statements[0].compile())
    assert "JOIN events" in sql
    assert "LEFT OUTER JOIN futures_outcomes" in sql
    assert "split_part(lower(futures_markets.external_id)" in sql
    assert "box_score_data" not in sql
    assert "calibration_probability" not in sql
    # Scalar columns only: no ORM hydration or unprojected payload columns.
    assert [str(column) for column in session.statements[0].selected_columns] == [
        f"{table}.{key}"
        for table, fields in (
            ("futures_markets", PREPARED_MARKET_FIELDS),
            ("events", PREPARED_EVENT_FIELDS),
            ("futures_outcomes", PREPARED_OUTCOME_FIELDS),
        ) for key in fields
    ]
    assert session.statements[0].compile().params["event_id_1"] == [1, 999]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        "single",
        "pair",
        "pair_plus_prop",
        "prop_only",
        "missing_ticker",
        "polymarket_fallback",
        "settled",
        "pre_kickoff",
    ],
)
async def test_smaller_read_retains_resolver_value_and_fallback(case):
    e = event()
    first = market(2)
    second = market(3, ticker="KXNBAGAME-26OCT08BOSGSW-GSW")
    prop = market(1, ticker="KXNBAPOINTS-26OCT08-TATUM", name="Tatum points")
    markets = [first]
    if case == "pair":
        markets = [second, first]
    elif case == "pair_plus_prop":
        markets = [prop, second, first]
    elif case == "prop_only":
        markets = [prop]
    elif case == "missing_ticker":
        first.external_id = None
    elif case == "polymarket_fallback":
        first.source = prop.source = "polymarket"
        markets = [prop, first]
    elif case == "settled":
        first.status = "closed"
    elif case == "pre_kickoff":
        e.commence_time = datetime.now(timezone.utc)
    seen = e.commence_time - timedelta(hours=1) if e.commence_time else None
    rows = sum(
        (outcomes(m, home=0.67 if m.id == 2 else 0.62, seen=seen) for m in markets), []
    )
    baseline = [
        MarketOutcomes(
            m,
            [o for o in rows if o.market_id == m.id],
            event_commence_time=e.commence_time,
            event_has_result=False,
        )
        for m in markets
    ]
    session = ReadSession([e], markets, rows)
    grouped = await LiveBlendRefresher(markets[0].source)._read_groups(session, [1])
    assert reading_signature(grouped[1][1]) == reading_signature(baseline)
    assert len(grouped[1][1]) == len(baseline)
    if case in {
        "single",
        "pair",
        "pair_plus_prop",
        "missing_ticker",
        "polymarket_fallback",
    }:
        assert reading_signature(baseline) is not None
    if case == "pair_plus_prop":
        assert (
            reading_signature(baseline)[2] is False
        )  # Dropping the prop would incorrectly devig.
    if case == "polymarket_fallback":
        assert session.outcome_ids == [1, 2]
    if case == "prop_only":
        assert len(session.statements) == 1  # Empty prop retained by outer join.

    @asynccontextmanager
    async def factory():
        yield session

    prepared = await LiveBlendRefresher(
        markets[0].source, session_factory=factory
    )._prepare_groups([1])
    assert reading_signature(prepared[1][1]) == reading_signature(baseline)
    assert len(prepared[1][1]) == len(baseline)


@pytest.mark.asyncio
async def test_prepared_context_keeps_fallbacks_and_detaches_json_without_copying_unused_event_fields():
    e = event()

    class GuardedEvent:
        def __getattr__(self, key):
            if key not in PREPARED_EVENT_FIELDS:
                raise AssertionError(f"unprojected Event field: {key}")
            return getattr(e, key)

    session = ReadSession([GuardedEvent()], [], [])
    m = market(2)
    session.markets = [m]
    session.outcomes = outcomes(m)

    @asynccontextmanager
    async def factory():
        yield session

    prepared = await LiveBlendRefresher(
        "kalshi", session_factory=factory
    )._prepare_groups([1])
    context = prepared[1][0]
    assert set(vars(context)) == set(PREPARED_EVENT_FIELDS)
    assert context.espn_win_prob_home == 0.7
    assert context.opening_home_probability == 0.6
    assert set(vars(prepared[1][1][0].market)) == set(PREPARED_MARKET_FIELDS)
    assert set(vars(prepared[1][1][0].outcomes[0])) == set(PREPARED_OUTCOME_FIELDS)
    context.win_probability_sources["espn"]["value"] = 0.1
    assert e.win_probability_sources["espn"]["value"] == 0.7


@pytest.mark.asyncio
async def test_one_read_replays_latest_quote_withdrawal_and_settlement():
    e = event()
    m = market(2)
    rows = outcomes(m)
    session = ReadSession([e], [m], rows)
    refresher = LiveBlendRefresher("kalshi")

    first = await refresher._read_groups(session, [1])
    original = reading_signature(first[1][1])
    assert original is not None
    rows[0].current_probability = 0.81
    rows[1].current_probability = 0.19
    rows[0].last_updated = rows[1].last_updated = datetime.now(timezone.utc)
    moved = await refresher._read_groups(session, [1])
    assert reading_signature(moved[1][1])[0] == pytest.approx(0.81)
    assert reading_signature(first[1][1]) == original

    rows[0].current_probability = rows[1].current_probability = None
    withdrawn = await refresher._read_groups(session, [1])
    assert reading_signature(withdrawn[1][1]) is None
    rows[0].current_probability = 0.81
    rows[1].current_probability = 0.19
    m.status = "closed"
    settled = await refresher._read_groups(session, [1])
    assert reading_signature(settled[1][1]) is None
    assert len(session.statements) == 4
