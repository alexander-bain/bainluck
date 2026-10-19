"""#10090: `source_snapshot` comes from the same committed stamp as `p` and `rev`.

The actual refresher, real Postgres and its revision trigger. Every published
frame is checked against an independent read made AFTER commit: the snapshot is
the public map of exactly the committed bag, under the committed revision, and
the frame's `p` is that bag's aggregate. A sibling source present, then removed,
then re-added between stamps must follow in the map. A failed or cancelled
commit publishes nothing. Building the snapshot issues no statement.

Ported from Speed's attempt119 deciding case (frozen local evidence); that run
proved serialization only, not reader adoption, delivery or speed. Neither
does this file.
"""

import asyncio
import contextvars
import dataclasses

import pytest
from datetime import datetime, timezone
from sqlalchemy import event as sa_event, update

from app.models.models import Event, FuturesOutcome
from app.utils import live_blend, live_push
from app.utils.aggregation import compute_aggregate_probability
from app.utils.price_evidence import NOT_EVALUATED
from app.utils.probability_eligibility import ineligible_record
from app.utils.probability_source_format import format_probability_sources
from tests.integration.test_live_blend_grouped_commit_8129_pg import (  # noqa: F401
    DB_URL,
    refresher,
    rig,
    seed,
    stage,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL, reason="requires disposable SEARCH_TEST_DATABASE_URL"
    ),
]

_OBSERVING = contextvars.ContextVar("srcsnap_observing", default=False)


def _expected(event):
    public = format_probability_sources(event.win_probability_sources)
    if "polymarket" in public:
        public["polymarket"]["price_evidence"] = NOT_EVALUATED
    return {
        "event_id": event.id,
        "rev": {str(event.id): event.win_probability_sources_rev},
        "win_probability_sources": public,
    }


def _observe(rig, r, monkeypatch):
    """Readback after commit; count refresher SQL and SQL inside the builder."""
    published, sql, inside = [], [], []

    def before(conn, cursor, statement, parameters, context, executemany):
        if not _OBSERVING.get():
            sql.append(statement.split()[0])

    sa_event.listen(rig.engine.sync_engine, "before_cursor_execute", before)
    real_build = live_push.build_source_snapshot

    def counted(*args, **kwargs):
        start = len(sql)
        try:
            return real_build(*args, **kwargs)
        finally:
            inside.append(len(sql) - start)

    monkeypatch.setattr(live_push, "build_source_snapshot", counted)

    async def publish(batch):
        token = _OBSERVING.set(True)
        try:
            async with rig.maker() as observer:
                for frame in batch:
                    event = await observer.get(Event, frame["event_id"])
                    published.append({
                        "frame": frame,
                        "expected": _expected(event),
                        "p": compute_aggregate_probability(event, event.status),
                    })
        finally:
            _OBSERVING.reset(token)

    r._publish = publish

    def detach():
        sa_event.remove(rig.engine.sync_engine, "before_cursor_execute", before)

    return published, sql, inside, detach


async def test_snapshot_tracks_committed_removal_and_readdition(rig, monkeypatch):
    await seed(rig, 1)
    r, *_ = refresher(rig)
    published, sql, inside, detach = _observe(rig, r, monkeypatch)
    try:
        for value, sibling in [(0.7, 0.4), (0.73, None), (0.67, 0.55)]:
            now = datetime.now(timezone.utc)
            async with rig.maker() as session:
                event = await session.get(Event, 1)
                sources = dict(event.win_probability_sources)
                if sibling is None:
                    sources.pop("kalshi", None)
                else:
                    sources["kalshi"] = {"value": sibling, "updated_at": now.isoformat()}
                await session.execute(
                    update(Event).where(Event.id == 1)
                    .values(win_probability_sources=sources)
                )
                await session.execute(
                    update(FuturesOutcome).where(FuturesOutcome.id == 1)
                    .values(current_probability=value, last_updated=now)
                )
                await session.commit()
            stage(r, [1])
            await r.refresh([1])
            await r.drain_history()
    finally:
        await r.drain_history()
        detach()

    assert len(published) == 3, published
    for item in published:
        frame = item["frame"]
        assert frame["source_snapshot"] == item["expected"], item
        assert frame["p"] == item["p"]
        assert frame["source_snapshot"]["rev"] == frame["rev"]
    maps = [x["frame"]["source_snapshot"]["win_probability_sources"] for x in published]
    assert maps[0]["kalshi"]["value"] == 0.4
    assert "kalshi" not in maps[1]
    assert maps[2]["kalshi"]["value"] == 0.55
    assert all(m["polymarket"]["price_evidence"] == NOT_EVALUATED for m in maps)
    revs = [x["frame"]["rev"]["1"] for x in published]
    assert revs == sorted(set(revs)), revs
    # The snapshot adds no statement and is built once per published frame.
    assert inside == [0, 0, 0], inside
    assert r.stats["source_snapshot_omitted"] == 0


async def test_refused_stamp_publishes_a_complete_empty_map_and_no_price(rig, monkeypatch):
    await seed(rig, 1)
    async with rig.maker() as session:
        await session.execute(
            update(Event).where(Event.id == 1).values(opening_home_probability=None)
        )
        await session.commit()
    real_reading = live_blend.compute_source_home_probability

    def refused(*args, **kwargs):
        reading = real_reading(*args, **kwargs)
        if reading is None:
            return None
        return dataclasses.replace(
            reading, eligibility=ineligible_record(rule="test#10090"),
        )

    monkeypatch.setattr(live_blend, "compute_source_home_probability", refused)
    r, *_ = refresher(rig)
    published, _sql, inside, detach = _observe(rig, r, monkeypatch)
    try:
        stage(r, [1])
        await r.refresh([1])
    finally:
        await r.drain_history()
        detach()

    assert len(published) == 1, published
    item = published[0]
    frame = item["frame"]
    assert frame["source_snapshot"] == item["expected"]
    assert frame["source_snapshot"]["win_probability_sources"] == {}
    # No fabricated number: the aggregate of an all-refused bag is no price.
    assert frame["p"] is None and item["p"] is None
    assert inside == [0]


@pytest.mark.parametrize("cancel", [False, True])
async def test_failed_commit_publishes_no_provisional_snapshot(rig, cancel):
    await seed(rig, 1)
    kwargs = {"cancel_commit_event": 1} if cancel else {"fail_commit_event": 1}
    r, frames, *_ = refresher(rig, **kwargs)
    stage(r, [1])
    try:
        await r.refresh([1])
    except asyncio.CancelledError:
        assert cancel
    await r.drain_history()
    assert frames == []
    async with rig.maker() as session:
        event = await session.get(Event, 1)
        assert "polymarket" not in event.win_probability_sources
