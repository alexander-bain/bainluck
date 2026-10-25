"""The MLB postseason's proven-duplicate read, against a real server. #9886.

**SHIP: an MLB postseason hub includes the questions attached to already-proven
duplicate game rows under their authoritative canonical member, without
admitting unproven matches.** (Pillars: MATCHING / TRUTH.)

The rule is graded in `tests/test_container_mlb_proven_duplicates_9886.py`
through a session double. That double agrees with whatever SQL the adapter
built, so only a server can say:

* that `event_tags @> jsonb_build_array(CAST(:tag AS text))` matches the exact
  ELEMENT — a label naming a prefix of a member's id (`duplicate-of:1532070`
  beside member 15320701) is not that member's duplicate;
* that a row matching two arms comes back ONCE, so a row naming two games is
  refused as such rather than read twice;
* that the in-span report's `NOT (e.id = ANY(:admitted_ids))` binds through
  asyncpg both full and EMPTY, and keeps an untagged row in the report;
* that the member read's new `event_tags` column and the LEFT JOIN to `sports`
  map to the right fields;
* that `ix_events_event_tags` (the migration's own `jsonb_path_ops` GIN) serves
  the duplicate read in its custom AND its generic plan — a statement it cannot
  serve is a sequential scan of `events` (`proven_duplicates`, 4 orders of
  magnitude, measured).

Event ids are the v3 suite's real ones; every row here is a test double.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from app.tasks.container_mlb_playoffs_assembly import (
    DUPLICATE_READ_LIMIT,
    duplicates_of_members_sql,
    gather_mlb_postseason_candidates,
    run_mlb_postseason_assembly,
)
from app.utils.container_mlb_playoffs import (
    EXCLUDED_DUPLICATE_LABEL_REFUSED,
    INCOMPLETE_STRANDED_QUESTIONS,
    REFUSED_CONFLICTING_LABELS,
    REFUSED_OTHER_SPORT,
)
from tests import test_container_mlb_playoffs_v3 as _v3
from tests.test_container_mlb_playoffs_v3 import (
    CWS_HOU_G2_ESPN,
    CWS_HOU_G2_EVENT,
    G1_ESPN,
    G1_EVENT,
    G2_ESPN,
    G2_EVENT,
    POST_2026,
    _boards,
)

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "needs a real PostgreSQL: set SEARCH_TEST_DATABASE_URL (the "
        "search-recall job's service container)"
    ),
)

corpus = _v3.corpus
g2 = _v3.g2

GHOST, PREFIX_ROW, NFL_ROW, TWO_LABELS, UNTAGGED = 15330001, 15330002, 15330003, 15330004, 15330005


@pytest.fixture
async def pg_session():
    """Real Postgres with the real schema, plus the migration's GIN index."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS container_corrections"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        # `add_taxonomy_tags`' own DDL, without CONCURRENTLY (a transaction).
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_events_event_tags "
                "ON events USING gin (event_tags jsonb_path_ops)"
            )
        )

    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        yield session

    await engine.dispose()


def _at(day, hour):
    return datetime(2026, 9, day, hour, 0, tzinfo=timezone.utc)


def _label(event_id):
    return f"provenance:duplicate-of:{event_id}"


async def _seed(session, *, labelled=True):
    from app.models.models import Event, FuturesMarket, Sport

    mlb = Sport(key="baseball_mlb", name="MLB", active=True)
    nfl = Sport(key="americanfootball_nfl", name="NFL", active=True)
    session.add_all([mlb, nfl])
    await session.flush()

    def event(id, sport, espn_id, start, tags=None, home="Atlanta Braves", away="Philadelphia Phillies"):
        return Event(id=id, sport_id=sport.id, espn_id=espn_id, status="scheduled", commence_time=start,
                     home_team_name=home, away_team_name=away, event_tags=tags)

    rows = [
        event(G1_EVENT, mlb, G1_ESPN, _at(29, 18)),
        event(G2_EVENT, mlb, G2_ESPN, _at(30, 18), tags=["tier:1"]),
        event(CWS_HOU_G2_EVENT, mlb, CWS_HOU_G2_ESPN, _at(30, 21), home="Houston Astros", away="Chicago White Sox"),
        # The write side's proof, naming Game 2 directly.
        event(GHOST, mlb, None, _at(30, 18), tags=["source:statpal", _label(G2_EVENT)] if labelled else None),
        # A PREFIX of Game 2's id: not Game 2's duplicate.
        event(PREFIX_ROW, mlb, None, _at(30, 19), tags=[_label(str(G2_EVENT)[:-1])] if labelled else None),
        event(NFL_ROW, nfl, None, _at(30, 17), tags=[_label(G2_EVENT)] if labelled else None,
              home="Atlanta Falcons", away="Philadelphia Eagles"),
        event(TWO_LABELS, mlb, None, _at(29, 18), tags=[_label(G1_EVENT), _label(G2_EVENT)] if labelled else None),
        event(UNTAGGED, mlb, None, _at(30, 21), home="Houston Astros", away="Chicago White Sox"),
    ]
    session.add_all(rows)
    await session.flush()

    markets = {}
    for event_id, n in ((G1_EVENT, 1), (G2_EVENT, 1), (CWS_HOU_G2_EVENT, 1), (GHOST, 2), (PREFIX_ROW, 1),
                        (NFL_ROW, 1), (TWO_LABELS, 1), (UNTAGGED, 1)):
        for i in range(n):
            m = FuturesMarket(source="kalshi", external_id=f"KXMLBQ-{event_id}-{i}", name=f"Q {event_id} {i}",
                              event_id=event_id, sport_id=mlb.id, category="sports", status="open",
                              market_type="binary")
            session.add(m)
            markets.setdefault(event_id, []).append(m)
    await session.flush()
    return {k: [m.id for m in v] for k, v in markets.items()}


def _market_ids(harvest):
    return {c.child_id for c in harvest.members.candidates if c.child_type == "market"}


async def test_only_the_exact_direct_label_on_an_mlb_row_is_admitted(pg_session, corpus):
    markets = await _seed(pg_session)
    harvest = await gather_mlb_postseason_candidates(pg_session, _boards(corpus), POST_2026)

    assert {d["event_id"]: d["duplicate_of"] for d in harvest.members.proven_duplicates} == {GHOST: G2_EVENT}
    assert set(markets[GHOST]) <= _market_ids(harvest)
    for other in (PREFIX_ROW, NFL_ROW, TWO_LABELS, UNTAGGED):
        assert not set(markets[other]) & _market_ids(harvest)

    refused = {r["event_id"]: r["refusal"] for r in harvest.members.excluded[EXCLUDED_DUPLICATE_LABEL_REFUSED]}
    # The prefix row matched no arm; the two-label row came back ONCE.
    assert refused == {NFL_ROW: REFUSED_OTHER_SPORT, TWO_LABELS: REFUSED_CONFLICTING_LABELS}

    # The admitted row leaves the report; the refused, prefix and untagged
    # MLB rows stay in it with their questions, and the pass is partial.
    assert sorted(u["event_id"] for u in harvest.unidentified_in_span) == [PREFIX_ROW, TWO_LABELS, UNTAGGED]
    assert harvest.stranded_questions == 3
    assert INCOMPLETE_STRANDED_QUESTIONS in harvest.incomplete


async def test_with_nothing_admitted_the_report_is_unchanged(pg_session, corpus):
    await _seed(pg_session, labelled=False)
    harvest = await gather_mlb_postseason_candidates(pg_session, _boards(corpus), POST_2026)
    assert harvest.members.proven_duplicates == []
    assert EXCLUDED_DUPLICATE_LABEL_REFUSED not in harvest.members.excluded
    # `admitted_ids = []` binds, and excludes nothing.
    assert sorted(u["event_id"] for u in harvest.unidentified_in_span) == [GHOST, PREFIX_ROW, TWO_LABELS, UNTAGGED]


async def test_assembly_edges_the_admitted_questions_and_moves_nothing(pg_session, corpus):
    from app.models.models import Container

    markets = await _seed(pg_session)
    mlb_id = (await pg_session.execute(text("SELECT id FROM sports WHERE key = 'baseball_mlb'"))).scalar()
    container = Container(kind="tournament", name=POST_2026.display_name, slug=POST_2026.slug,
                          sport_id=mlb_id, status="live")
    pg_session.add(container)
    await pg_session.flush()

    report = await run_mlb_postseason_assembly(pg_session, container, _boards(corpus), POST_2026, apply=True)
    await pg_session.commit()

    edged = {
        r[0]
        for r in (
            await pg_session.execute(
                text("SELECT child_id FROM event_edges WHERE parent_type = 'container' AND parent_id = :id "
                     "AND child_type = 'market'"),
                {"id": container.id},
            )
        ).fetchall()
    }
    assert set(markets[GHOST]) <= edged
    assert not set(markets[TWO_LABELS] + markets[UNTAGGED] + markets[PREFIX_ROW]) & edged
    # Each question still hangs off the row it was matched to.
    owners = dict(
        (await pg_session.execute(
            text("SELECT id, event_id FROM futures_markets WHERE id = ANY(:ids)"), {"ids": markets[GHOST]}
        )).fetchall()
    )
    assert set(owners.values()) == {GHOST}
    assert report["terminal"] == "partial" and report["proven_duplicates"][0]["event_id"] == GHOST


def _as_prepared(sql: str, arms: int) -> str:
    """The statement with positional parameters, for a SQL-level PREPARE."""
    for n in reversed(range(arms)):
        sql = sql.replace(f":tag_{n}", f"${n + 1}")
    return sql.replace(":limit", f"${arms + 1}")


async def _plan(session, statement, params=None) -> set:
    """Every ``(node type, relation, index)`` in the plan's tree."""
    raw = (await session.execute(text(statement), params or {})).scalar()
    nodes, stack = set(), [(raw if isinstance(raw, list) else json.loads(raw))[0]["Plan"]]
    while stack:
        node = stack.pop()
        nodes.add((node["Node Type"], node.get("Relation Name"), node.get("Index Name")))
        stack.extend(node.get("Plans", ()))
    return nodes


def _reads_events_by_the_gin_index_only(nodes: set) -> bool:
    on_events = {(kind, index) for kind, relation, index in nodes if relation == "events" or index == "ix_events_event_tags"}
    return ("Bitmap Index Scan", "ix_events_event_tags") in on_events and not {
        kind for kind, index in on_events if index != "ix_events_event_tags" and kind != "Bitmap Heap Scan"
    }


#: A postseason's members: Wild Card to the World Series is ~45 games.
ARMS = 45


async def test_the_gin_index_serves_the_duplicate_read_custom_and_generic(pg_session, corpus):
    await _seed(pg_session)
    # A population the planner has to choose over, analysed so the costs are
    # real; every planner setting is left at its default. Production's `events`
    # is ~240k WIDE rows (a sequential scan read 105,540 blocks, measured in
    # `proven_duplicates`), so these rows are padded: narrow rows make a
    # sequential scan look cheaper than it ever is there. The index is rebuilt
    # after the load, as production's is settled: a GIN index holding a fresh
    # pending list costs itself out of every plan.
    await pg_session.execute(
        text(
            "INSERT INTO events (id, sport_id, status, commence_time, home_team_name, away_team_name, event_tags) "
            "SELECT 20000000 + g, (SELECT id FROM sports WHERE key = 'baseball_mlb'), 'final', "
            "       now() - g * interval '1 hour', repeat('h', 180) || g, repeat('a', 180) || g, "
            "       CASE WHEN g % 50 = 0 THEN jsonb_build_array('tier:1') "
            "            WHEN g % 7 = 0 THEN jsonb_build_array('provenance:duplicate-of:' || (19000000 + g)) "
            "            ELSE '[]'::jsonb END "
            "FROM generate_series(1, 240000) AS g"
        )
    )
    await pg_session.execute(text("DROP INDEX ix_events_event_tags"))
    await pg_session.execute(
        text("CREATE INDEX ix_events_event_tags ON events USING gin (event_tags jsonb_path_ops)")
    )
    await pg_session.execute(text("ANALYZE events"))

    ids = [G1_EVENT, G2_EVENT, CWS_HOU_G2_EVENT] + [15340000 + n for n in range(ARMS - 3)]
    sql = duplicates_of_members_sql(ARMS)
    params = {f"tag_{n}": _label(cid) for n, cid in enumerate(ids)}
    params["limit"] = DUPLICATE_READ_LIMIT + 1

    custom = await _plan(pg_session, "EXPLAIN (FORMAT JSON) " + sql, params)
    assert _reads_events_by_the_gin_index_only(custom), custom

    # asyncpg caches the statement per connection, so Postgres may plan it
    # generically. Automatic plan caching kept the custom plan for every form
    # measured, but a LIMIT on the scan made the GENERIC plan a full scan of
    # `events` (ORDER BY e.id: a primary-key walk). Forced here so the shape
    # cannot depend on how a generic plan happens to be costed.
    await pg_session.execute(text("SET LOCAL plan_cache_mode = force_generic_plan"))
    await pg_session.execute(
        text(f"PREPARE dup9886 ({', '.join(['text'] * ARMS)}, int) AS {_as_prepared(sql, ARMS)}")
    )
    args = ", ".join([f"'{_label(cid)}'" for cid in ids] + [str(DUPLICATE_READ_LIMIT + 1)])
    generic = await _plan(pg_session, f"EXPLAIN (FORMAT JSON) EXECUTE dup9886({args})")
    assert _reads_events_by_the_gin_index_only(generic), generic
