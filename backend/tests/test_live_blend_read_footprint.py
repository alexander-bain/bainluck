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
        from app.utils.content_understanding import (
            CONTENT_UNDERSTANDING_KEY, CONTENT_UNDERSTANDING_VERSION,
            venue_label_refutes_full_contest_winner,
        )

        columns = list(getattr(statement, "selected_columns", ()))
        column = columns[len(PREPARED_MARKET_FIELDS) + PREPARED_EVENT_FIELDS.index(
            "win_probability_sources"
        )] if columns else None
        source = column.element.right.value if hasattr(column, "element") else None

        def field(obj, key):
            raw = getattr(obj, key, None)
            if key == "win_probability_sources" and source is not None:
                return raw.get(source) if isinstance(raw, dict) else None
            return raw

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
            if market.source == "polymarket":
                metadata = market.market_metadata
                understanding = (
                    metadata.get(CONTENT_UNDERSTANDING_KEY)
                    if isinstance(metadata, dict)
                    else None
                )
                # The read is conservative: only known current-version records
                # use the existing authoritative refusal; all other rows hydrate.
                current = (
                    isinstance(understanding, dict)
                    and type(understanding.get("v")) is int
                    and (understanding["v"] == CONTENT_UNDERSTANDING_VERSION)
                )
                eligible = not (
                    current and venue_label_refutes_full_contest_winner(market)
                )
            if eligible:
                self.outcome_ids.append(market.id)
            outcomes = [
                o for o in self.outcomes if o.market_id == market.id
            ] if eligible else []
            for outcome in outcomes or [None]:
                rows.append(tuple(
                    field(obj, key)
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
    columns = list(session.statements[0].selected_columns)
    source_position = len(PREPARED_MARKET_FIELDS) + PREPARED_EVENT_FIELDS.index(
        "win_probability_sources"
    )
    assert [str(column) for i, column in enumerate(columns) if i != source_position] == [
        f"{table}.{key}"
        for table, fields in (
            ("futures_markets", PREPARED_MARKET_FIELDS),
            ("events", PREPARED_EVENT_FIELDS),
            ("futures_outcomes", PREPARED_OUTCOME_FIELDS),
        ) for key in fields if key != "win_probability_sources"
    ]
    assert columns[source_position].element.right.value == "kalshi"
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
    e.win_probability_sources["kalshi"] = {"value": 0.67}

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
    assert set(context.win_probability_sources) == {"kalshi"}
    context.win_probability_sources["kalshi"]["value"] = 0.1
    assert e.win_probability_sources["kalshi"]["value"] == 0.67
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "shape, skipped",
    [
        ({"v": 1, "semantic_type": "moneyline", "venue_type": "child_moneyline"}, True),
        (
            {
                "v": 1,
                "semantic_type": "moneyline",
                "venue_type": "tennis_completed_match",
            },
            True,
        ),
        ({"v": 1, "semantic_type": "totals", "venue_type": "totals"}, True),
        ({"v": 1, "semantic_type": "moneyline", "venue_type": "moneyline"}, False),
        ({"v": 1, "semantic_type": "moneyline"}, False),
        ({"v": 1, "semantic_type": "moneyline", "venue_type": None}, False),
        ({"v": 1, "semantic_type": "moneyline", "venue_type": ""}, False),
        ({"v": 1, "semantic_type": "moneyline", "venue_type": ["totals"]}, False),
        ({"v": 1, "venue_type": "totals"}, False),
        ({"v": 1, "semantic_type": "", "venue_type": "totals"}, False),
        ({"v": 1, "semantic_type": 4, "venue_type": "totals"}, False),
        ({"v": True, "semantic_type": "moneyline", "venue_type": "totals"}, False),
        ({"v": "1", "semantic_type": "moneyline", "venue_type": "totals"}, False),
        ({"v": 1.0, "semantic_type": "moneyline", "venue_type": "totals"}, False),
        ({"v": 2, "semantic_type": "moneyline", "venue_type": "totals"}, False),
        ({"v": 0, "semantic_type": "moneyline", "venue_type": "totals"}, False),
        (None, False),
        ([], False),
    ],
)
async def test_pm_outcome_read_omits_only_known_refusals_and_keeps_full_reading(
    shape, skipped
):
    from sqlalchemy.dialects import postgresql
    from app.utils.content_understanding import CONTENT_UNDERSTANDING_KEY

    e = event()
    candidate = market(1, source="polymarket")
    winner = market(2, source="polymarket")
    candidate.market_metadata = {CONTENT_UNDERSTANDING_KEY: shape}
    quotes = outcomes(candidate, home=0.2) + outcomes(winner, home=0.67)
    baseline = [
        MarketOutcomes(m, [o for o in quotes if o.market_id == m.id])
        for m in [candidate, winner]
    ]
    session = ReadSession([e], [candidate, winner], quotes)
    grouped = await LiveBlendRefresher("polymarket")._read_groups(session, [1])
    graph = grouped[1][1]
    assert [g.market.id for g in graph] == [1, 2]
    assert len(graph[0].outcomes) == (0 if skipped else 2)
    assert len(graph[1].outcomes) == 2
    assert reading_signature(graph) == reading_signature(baseline)
    # Assert the ACTUAL generated predicate is on the outcome OUTER JOIN,
    # with type/version/absence guards, never on market selection.
    statement = session.statements[0]
    sql = str(
        statement.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    join, where = sql.split("\nWHERE ")
    assert (
        "LEFT OUTER JOIN futures_outcomes ON futures_outcomes.market_id = futures_markets.id AND NOT coalesce("
        in join
    )
    assert "jsonb_typeof" not in where
    assert "jsonb_typeof(futures_markets.market_metadata) = 'object'" in join
    assert " ->> 'v') = '1'" in join
    assert " ->> 'venue_type') NOT IN ('moneyline')" in join
    assert "false)" in join
    assert len(session.statements) == 1


@pytest.mark.asyncio
async def test_pm_many_refused_outcomes_keep_shell_count_devig_and_retirement():
    from app.utils.content_understanding import CONTENT_UNDERSTANDING_KEY

    e = event()
    prop = market(1, source="polymarket")
    prop.market_metadata = {
        CONTENT_UNDERSTANDING_KEY: {
            "v": 1,
            "semantic_type": "moneyline",
            "venue_type": "child_moneyline",
        }
    }
    home = market(2, source="polymarket")
    away = market(3, source="polymarket")
    props = [
        FuturesOutcome(
            id=1000 + i,
            market_id=1,
            name="Boston Celtics",
            rank=i,
            current_probability=0.2,
        )
        for i in range(128)
    ]
    quotes = props + outcomes(home, home=0.67) + outcomes(away, home=0.61)
    baseline = [
        MarketOutcomes(m, [o for o in quotes if o.market_id == m.id])
        for m in [prop, home, away]
    ]
    session = ReadSession([e], [prop, home, away], quotes)
    refresher = LiveBlendRefresher("polymarket")
    graph = (await refresher._read_groups(session, [1]))[1][1]
    assert [g.market.id for g in graph] == [1, 2, 3]
    assert sum(len(g.outcomes) for g in graph) == 4  # Full graph hydrated132.
    assert reading_signature(graph) == reading_signature(baseline)
    assert (
        reading_signature(graph)[2] is False
    )  # Shell keeps3, never a false devig pair.
    session.markets = [prop]
    assert reading_signature((await refresher._read_groups(session, [1]))[1][1]) is None
    session.markets = [prop, home, away]
    for q in quotes:
        q.current_probability = None
    assert reading_signature((await refresher._read_groups(session, [1]))[1][1]) is None
