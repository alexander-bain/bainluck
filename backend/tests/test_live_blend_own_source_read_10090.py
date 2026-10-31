"""Own-source prepared JSON keeps graph and restamp semantics intact."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import String
from sqlalchemy.sql.elements import Cast, Null
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
from tests.test_live_blend_read_footprint import ReadSession, event, market, outcomes, projected


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["kalshi", "polymarket"])
@pytest.mark.parametrize("preview", [False, True])
async def test_actual_select_narrows_only_source_json_and_preserves_joined_graph(source, preview):
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
    refresher = LiveBlendRefresher(source)
    refresher.preview_events = frozenset({1}) if preview else frozenset()
    grouped = await refresher._read_groups(session, [1])
    context, graph = grouped[1]
    assert context.win_probability_sources == {source: entry}
    assert [g.market.id for g in graph] == [9, 3, 2]
    assert graph[0].outcomes == graph[2].outcomes == []
    assert [o.id for o in graph[1].outcomes] == [o.id for o in quotes]
    assert len(session.statements) == 1
    statement = session.statements[0]
    columns = projected(statement.selected_columns)
    position = len(PREPARED_MARKET_FIELDS) + PREPARED_EVENT_FIELDS.index(
        "win_probability_sources"
    )
    projection = columns[position]
    assert projection.name == "win_probability_sources"
    if preview:
        assert isinstance(projection.element, Cast)
        assert isinstance(projection.element.clause, Null)
        assert isinstance(projection.element.type, JSONB)
        assert str(projection.compile(dialect=postgresql.dialect())) == "CAST(NULL AS JSONB)"
    else:
        assert projection.element.left.shares_lineage(Event.win_probability_sources)
        assert projection.element.right.value == source
        assert isinstance(projection.element.right.type, String)
        assert isinstance(projection.element.type, JSONB)
        compiled = projection.compile(dialect=postgresql.dialect())
        assert list(compiled.params.values()) == [source]
        assert "events.win_probability_sources -> " in str(compiled)
        assert "::JSONB" not in str(compiled)
    expected = [
        "sports.key" if key == "sport_key" else f"{table}.{key}"
        for table, fields in (
            ("futures_markets", PREPARED_MARKET_FIELDS),
            ("events", PREPARED_EVENT_FIELDS),
            ("futures_outcomes", PREPARED_OUTCOME_FIELDS),
        ) for key in fields if key not in ("win_probability_sources", "market_metadata")
    ]
    metadata_position = PREPARED_MARKET_FIELDS.index("market_metadata")
    assert [str(c) for i, c in enumerate(columns) if i not in (position, metadata_position)] == expected + ([
        "events.win_probability_sources", "events.win_probability_sources_rev", "statement_timestamp()",
    ] if preview else [])
    metadata_projection = columns[metadata_position]
    assert metadata_projection.name == "market_metadata"
    assert metadata_projection.element.name == "jsonb_build_object"
    assert list(metadata_projection.element.clauses)[0].value == "content_understanding_v1"
    if preview:
        assert [c.name for c in columns[-3:]] == [
            "preview_sources", "preview_rev", "preview_context_at",
        ]
        assert context.preview_sources == e.win_probability_sources
        assert context.preview_rev == e.win_probability_sources_rev
        assert context.preview_context_at == session.read_at
    else:
        assert not hasattr(context, "preview_sources")
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "JOIN events" in sql and "LEFT OUTER JOIN futures_outcomes" in sql
    assert "LEFT OUTER JOIN sports ON sports.id = events.sport_id" in sql
    assert context.sport_key == "basketball_nba"
    assert not statement._order_by_clauses and not statement._group_by_clauses
    # #10090 `STAMP_READ_JSON_ONCE`: its two `row_number()` flags, each in one
    # JSON column's CASE and in its own column, are the only window functions.
    from app.tasks.live_blend_refresh import stamp_read_json_once
    assert sql.count("OVER (") == (4 if stamp_read_json_once() else 0)
    assert not statement._distinct


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


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["kalshi", "polymarket"])
async def test_projected_source_retains_independent_nested_ownership(source):
    e = event()
    e.win_probability_sources = {source: {"value": .6, "nested": [{"x": [1, 2]}]}}
    winner = market(1, source=source)
    session = ReadSession([e], [winner], outcomes(winner))
    r = LiveBlendRefresher(source)
    r.preview_events = frozenset({1})
    context, _ = (await r._read_groups(session, [1]))[1]
    own = context.win_probability_sources[source]
    full = context.preview_sources[source]
    assert own == full and own is not full
    own["nested"][0]["x"].append(3)
    assert full["nested"][0]["x"] == [1, 2]
    full["nested"][0]["x"].append(4)
    assert own["nested"][0]["x"] == [1, 2, 3]
    assert e.win_probability_sources[source]["nested"][0]["x"] == [1, 2]
