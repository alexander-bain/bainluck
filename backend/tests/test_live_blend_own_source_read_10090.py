"""Own-source prepared JSON keeps graph and restamp semantics intact."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import String
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB

from app.models.models import Event
from app.tasks.live_blend_refresh import (
    LiveBlendRefresher,
    PREPARED_EVENT_FIELDS,
    PREPARED_MARKET_FIELDS,
    PREPARED_OUTCOME_FIELDS,
    restamp_records_no_observation,
)
from tests.test_live_blend_read_footprint import ReadSession, event, market, outcomes


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["kalshi", "polymarket"])
async def test_actual_select_narrows_only_source_json_and_preserves_joined_graph(source):
    e = event()
    entry = {"value": 0.67, "updated_at": "2026-10-08T00:00:00+00:00"}
    e.win_probability_sources = {
        source: entry,
        "betting": {"value": 0.4, "unused": "sibling payload"},
    }
    prop = market(9, source=source, ticker="KXNBAPOINTS-26OCT08-TATUM")
    winner = market(3, source=source)
    empty = market(2, source=source, ticker=None)
    quotes = list(reversed(outcomes(winner)))
    session = ReadSession([e], [prop, winner, empty], quotes)
    grouped = await LiveBlendRefresher(source)._read_groups(session, [1])
    context, graph = grouped[1]
    assert context.win_probability_sources == {source: entry}
    assert [g.market.id for g in graph] == [9, 3, 2]
    assert graph[0].outcomes == graph[2].outcomes == []
    assert [o.id for o in graph[1].outcomes] == [o.id for o in quotes]
    assert len(session.statements) == 1
    statement = session.statements[0]
    columns = list(statement.selected_columns)
    position = len(PREPARED_MARKET_FIELDS) + PREPARED_EVENT_FIELDS.index(
        "win_probability_sources"
    )
    projection = columns[position]
    assert projection.name == "win_probability_sources"
    assert projection.element.left.shares_lineage(Event.win_probability_sources)
    assert projection.element.right.value == source
    assert isinstance(projection.element.right.type, String)
    assert isinstance(projection.element.type, JSONB)
    compiled = projection.compile(dialect=postgresql.dialect())
    assert list(compiled.params.values()) == [source]
    assert "events.win_probability_sources -> " in str(compiled)
    assert "::JSONB" not in str(compiled)
    expected = [
        f"{table}.{key}"
        for table, fields in (
            ("futures_markets", PREPARED_MARKET_FIELDS),
            ("events", PREPARED_EVENT_FIELDS),
            ("futures_outcomes", PREPARED_OUTCOME_FIELDS),
        ) for key in fields if key != "win_probability_sources"
    ]
    assert [str(c) for i, c in enumerate(columns) if i != position] == expected
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "JOIN events" in sql and "LEFT OUTER JOIN futures_outcomes" in sql
    assert not statement._order_by_clauses and not statement._group_by_clauses
    assert "OVER (" not in sql and not statement._distinct


STAMP = datetime(2026, 10, 8, tzinfo=timezone.utc)


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["kalshi", "polymarket"])
@pytest.mark.parametrize(
    "stored, container",
    [
        ({"value": 0.67, "updated_at": STAMP.isoformat()}, "object"),
        ({"value": 0.67, "updated_at": STAMP.isoformat(), "weight": 0.8,
          "observed_basis": {"301": STAMP.isoformat()}}, "object"),
        ({"value": 0.67}, "object"),
        ({"value": 0.67, "updated_at": "bad clock"}, "object"),
        ({"value": "0.67", "updated_at": STAMP.isoformat()}, "object"),
        ({"value": True, "updated_at": STAMP.isoformat()}, "object"),
        (0.67, "object"),
        (True, "object"),
        (None, "object"),
        ([], "object"),
        (None, "missing"),
        (None, "null"),
        ([{"value": 0.67, "updated_at": STAMP.isoformat()}], "nonobject"),
        ("malformed bag", "nonobject"),
    ],
)
async def test_restamp_decisions_match_full_bag_for_all_supported_and_abstaining_shapes(
    source, stored, container,
):
    if container == "object":
        full = {source: stored, "betting": {"value": 0.9, "updated_at": STAMP.isoformat()}}
    elif container == "missing":
        full = {"betting": {"value": 0.9, "updated_at": STAMP.isoformat()}}
    elif container == "null":
        full = None
    else:
        full = stored
    e = event()
    e.win_probability_sources = full
    session = ReadSession([e], [market(1, source=source)], [])
    grouped = await LiveBlendRefresher(source)._read_groups(session, [1])
    projected = grouped[1][0].win_probability_sources
    assert set(projected) == {source}
    for value in (0.67, 0.72):
        for observed in (STAMP - timedelta(seconds=1), STAMP, STAMP + timedelta(seconds=1), None):
            assert restamp_records_no_observation(value, observed, projected, source) == (
                restamp_records_no_observation(value, observed, full, source)
            )
