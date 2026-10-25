"""Preview reads preserve own-source semantics while decoding each source only once."""
import pytest
from sqlalchemy import literal, null, update

from app.models.models import Event, FuturesMarket
from app.tasks.live_blend_refresh import LiveBlendRefresher, PREPARED_EVENT_FIELDS, PREPARED_MARKET_FIELDS
from tests.integration.test_live_blend_grouped_commit_8129_pg import DB_URL, rig as _rig, seed
from tests.integration.test_dnpl_reservations_10090_pg import actors as _actors, redis_kwargs as _redis_kwargs

rig, actors, redis_kwargs = _rig, _actors, _redis_kwargs

pytestmark = [pytest.mark.asyncio, pytest.mark.skipif(not DB_URL, reason="disposable PostgreSQL required")]


class SourceExtractionOracle:
    """Retain the old SQL extraction as an independent, same-snapshot oracle."""
    def __init__(self, session, source):
        self.session = session
        self.source = source
        self.extracted = []

    async def execute(self, statement):
        columns = list(statement.selected_columns)
        slot = len(PREPARED_MARKET_FIELDS) + PREPARED_EVENT_FIELDS.index(
            "win_probability_sources"
        )
        columns[slot] = Event.win_probability_sources.op("->")(literal(self.source))
        result = await self.session.execute(
            statement.with_only_columns(*columns, maintain_column_froms=True)
        )
        rows = result.all()
        self.extracted = [row[slot] for row in rows]

        class Rows:
            def all(self):
                return rows

        return Rows()


@pytest.mark.parametrize("source", ["polymarket", "kalshi"])
async def test_preview_source_reconstruction_matches_postgres_extraction(rig, source, monkeypatch):
    await seed(rig, count=2)
    async with rig.engine.begin() as conn:
        await conn.execute(update(FuturesMarket).values(event_id=1, source=source))
    refresher = LiveBlendRefresher(source)
    refresher.preview_events = frozenset({1})
    ticket = object()

    async def admission():
        return ticket

    monkeypatch.setattr(refresher, "_preview_admission_read", admission)
    shapes = [
        {source: {"value": 0.6, "nested": [{"items": [1, 2]}]},
         "betting": {"value": 0.4}},
        *[{source: value} for value in (None, [], "bad entry", 0.6, True)],
        {}, None, [], "bad root", 0.6, True, null(),
    ]
    for stored in shapes:
        async with rig.engine.begin() as conn:
            await conn.execute(update(Event).where(Event.id == 1).values(
                win_probability_sources=stored,
            ))
        async with rig.maker() as session:
            oracle = SourceExtractionOracle(session, source)
            context, graph = (await refresher._read_groups(oracle, [1]))[1]
            actual, actual_graph = (await refresher._read_groups(session, [1]))[1]
        assert oracle.extracted
        assert all(context.win_probability_sources == {source: value}
                   for value in oracle.extracted)
        assert actual.win_probability_sources == context.win_probability_sources
        assert actual.preview_sources == context.preview_sources
        assert actual.preview_rev == context.preview_rev
        assert [(g.market.id, [o.id for o in g.outcomes]) for g in actual_graph] == [
            (g.market.id, [o.id for o in g.outcomes]) for g in graph
        ]
        assert context.preview_read_ticket is ticket
        assert actual.preview_read_ticket is ticket
        assert len(graph) == 2
        own = context.win_probability_sources[source]
        if isinstance(own, dict):
            assert own is not context.preview_sources[source]
            own["nested"][0]["items"].append(3)
            assert context.preview_sources[source]["nested"][0]["items"] == [1, 2]
            context.preview_sources[source]["nested"][0]["items"].append(4)
            assert own["nested"][0]["items"] == [1, 2, 3]


@pytest.mark.parametrize("source", ["polymarket", "kalshi"])
@pytest.mark.parametrize("sport_key,bucket", [("basketball_nba", "0"), ("basketball_wnba", "2")])
@pytest.mark.parametrize("stored", [null(), None, {}], ids=["sql-null", "json-null", "empty-object"])
async def test_first_covered_quote_previews_before_empty_baseline_commits(
    rig, actors, source, sport_key, bucket, stored,
):
    from datetime import datetime, timezone
    from sqlalchemy import select, text
    from app.utils import blend_preview as bp

    worker, registry, client = actors
    worker.source = source
    await seed(rig, 1)
    async with rig.engine.begin() as conn:
        await conn.execute(text("UPDATE sports SET key=:key"), {"key": sport_key})
        await conn.execute(update(FuturesMarket).values(source=source))
        await conn.execute(update(Event).values(win_probability_sources=stored))
    async with rig.maker() as held:
        # A preview must not need the first normal event UPDATE to finish.
        baseline_before = (await held.execute(select(
            Event.win_probability_sources, Event.win_probability_sources_rev,
        ).where(Event.id == 1).with_for_update())).one()
        async with rig.maker() as session:
            event, _ = (await worker._read_groups(session, [1]))[1]
        ops = registry.propose(
            1, source, value=.7, event=event,
            row_sources=event.preview_sources, row_rev=event.preview_rev,
            stamped_at=datetime.now(timezone.utc),
        )
        frames = await registry.prepare(ops, client.execute_command, worker.preview_stats)
        assert len(frames) == 1, "first source quote must not wait for a baseline commit"
        assert frames[0]["p"] == .7
        assert frames[0]["preview"]["pending"] == {source: .7}
        assert frames[0]["preview"]["base_rev"] == event.preview_rev == baseline_before[1]
        assert await client.hget(bp.LEDGER_KEY, "e:1:r_bucket") == bucket.encode()
        assert worker.preview_stats.get("ledger_refused", 0) == 0
        assert event.preview_sources == {}
        await registry.execute(
            frames, client.execute_command, lambda eid: f"test:empty-baseline:{eid}",
            worker.preview_stats,
        )
        assert worker.preview_stats["published"] == 1
        # Reading a null baseline does not rewrite stored data or revisions.
        unchanged = (await held.execute(select(
            Event.win_probability_sources, Event.win_probability_sources_rev,
        ))).one()
        assert unchanged[0] == ({} if isinstance(stored, dict) else None)
        assert unchanged == baseline_before
        await held.rollback()


@pytest.mark.parametrize("source", ["polymarket", "kalshi"])
@pytest.mark.parametrize("stored", [[], "bad-root", .6, True])
async def test_malformed_baseline_is_not_reinterpreted_as_empty(rig, actors, source, stored):
    from datetime import datetime, timezone
    from app.utils import blend_preview as bp

    worker, registry, client = actors
    worker.source = source
    await seed(rig, 1)
    async with rig.engine.begin() as conn:
        await conn.execute(update(FuturesMarket).values(source=source))
        await conn.execute(update(Event).values(win_probability_sources=stored))
    async with rig.maker() as session:
        event, _ = (await worker._read_groups(session, [1]))[1]
    assert event.preview_sources == stored
    ops = registry.propose(
        1, source, value=.7, event=event,
        row_sources=event.preview_sources, row_rev=event.preview_rev,
        stamped_at=datetime.now(timezone.utc),
    )
    assert await registry.prepare(ops, client.execute_command, worker.preview_stats) == []
    assert worker.preview_stats["ledger_refused"] == 1
    assert await client.hget(bp.LEDGER_KEY, "e:1:gen") is None
