"""#10090 — a tagged-twin event page can verify the exact source-removal floor
against the detail it actually receives, on real PostgreSQL.

## the ship

Tagged-twin pages can prove that the served detail covers the actual removal
floor: the event stream's ``removal_rev`` keys and the detail's
``blend_fold_revision`` keys are the SAME row set, before and after a real
committed removal on the twin.

## where these cases come from

* attempt131 ``test_twin_pair.py`` (frozen packet under
  ``artifacts/live-iteration-goal-20261011/local-blended-web-20261016/``),
  accepted by Lane1 as the 125 D3 paired gate: the two cases below keep its
  assertions; its result files became assertion messages.
* The reversed-slot case is NEW in this port, as Lane1's 131 review
  suggested: a third row tagged ``provenance:duplicate-of`` the canonical but
  with home/away SWAPPED. Stream membership and detail both filter tagged rows
  through the same ``orientation_agrees``; this pins that the reversed row's
  key appears in NEITHER vector and is not subscribed, while the agreeing
  twin's still does.

## the rig

#9051's full-schema fixture (``test_fold_revision_9051_pg.pg``): the real
trigger-maintained revision. The public stream handler runs its own
membership query; the full detail builder runs ``get_event`` with the cache
bypassed. Nothing in the fold, membership, revision or detail is mocked. Only
the retained-frame transport (``latest_frames`` returns nothing) and the
shared fanout (#837's in-process mailbox ``Hub``) are fixtures, and the
removal control's custody id is fixture data: this is the route/detail
contract boundary, not the Polymarket publisher, a page or a timing.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text

from app.routes import event_stream as route
from app.routes import events
from app.utils import live_fanout
from tests.integration.test_fold_revision_9051_pg import (  # noqa: F401
    CANON,
    DB_URL,
    TWIN,
    _drop_source,
    _reading,
    pg,
)
from tests.test_folded_event_stream_invalidation_837 import Hub, Request, frame

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL, reason="requires disposable SEARCH_TEST_DATABASE_URL"
    ),
]

#: A tagged duplicate of the canonical whose home/away are the canonical's
#: away/home: a reversed-slot row, excluded from both vectors.
REVERSED = 905103


def data(chunks, kind):
    return [
        json.loads(c.split("data: ", 1)[1])
        for c in chunks
        if c.startswith("event: " + kind + "\n")
    ]


async def until(predicate):
    async with asyncio.timeout(2):
        while not predicate():
            await asyncio.sleep(0.003)


async def freshen(engine):
    # Keep source observations current; revisions still come from the trigger.
    async with engine.begin() as db:
        await db.execute(
            text(
                "UPDATE events SET win_probability_sources=(SELECT jsonb_object_agg("
                "key,value || jsonb_build_object('updated_at',clock_timestamp())) "
                "FROM jsonb_each(win_probability_sources))"
            )
        )


def mount(monkeypatch, Session):
    hub = Hub()
    monkeypatch.setattr(live_fanout, "fanout", lambda: hub)
    monkeypatch.setattr(route, "async_session_maker", Session)
    monkeypatch.setattr(route, "latest_frames", AsyncMock(return_value=[]))
    monkeypatch.setattr(route, "FRAME_WAIT_S", 0.01)
    monkeypatch.setattr(route, "HEARTBEAT_INTERVAL_S", 0.02)
    return hub


async def removal_floor_pairing(pg, monkeypatch, detail_id):
    """attempt131's case body, assertions unchanged."""
    engine, Session = pg
    await freshen(engine)
    hub = mount(monkeypatch, Session)
    async with Session() as db:
        before = await events.build_event_detail_uncoalesced(db, detail_id)
    response = await route.stream_event(CANON, Request())
    chunks = []

    async def collect():
        async for chunk in response.body_iterator:
            chunks.append(chunk)

    task = asyncio.create_task(collect())
    try:
        await until(lambda: bool(data(chunks, "reconcile")))
        initial = data(chunks, "reconcile")[0]
        assert initial["removal_rev"] == before["blend_fold_revision"]
        assert set(initial["removal_rev"]) == {str(CANON), str(TWIN)}
        assert set(hub.subscriptions) == {f"live:event:{CANON}", f"live:event:{TWIN}"}
        removed_rev = await _drop_source(Session, TWIN, "kalshi")
        control = {
            "event_id": TWIN,
            "custody_id": "pm-withdrawal:9051",
            "removal_rev": {str(TWIN): removed_rev},
        }
        outgoing = frame(
            TWIN,
            p=None,
            source=None,
            source_value=None,
            invalidation=True,
            rev={str(TWIN): removed_rev},
            reconcile=control,
        )
        hub.subscriptions[f"live:event:{TWIN}"].offer(json.dumps(outgoing))
        await until(
            lambda: any(
                x["custody_id"] == control["custody_id"]
                for x in data(chunks, "reconcile")
            )
        )
        emitted = next(
            x
            for x in data(chunks, "reconcile")
            if x["custody_id"] == control["custody_id"]
        )
        async with Session() as db:
            after = await events.build_event_detail_uncoalesced(db, detail_id)
            stored = dict(
                (
                    await db.execute(
                        text(
                            "SELECT id,win_probability_sources_rev FROM events "
                            "WHERE id IN (:c,:t)"
                        ),
                        {"c": CANON, "t": TWIN},
                    )
                ).all()
            )
        result = {
            "requested_detail_id": detail_id,
            "stream_page_id": CANON,
            "initial": initial,
            "emitted": emitted,
            "before_detail_revision": before["blend_fold_revision"],
            "after_detail_revision": after["blend_fold_revision"],
            "stored_revision": {str(k): v for k, v in stored.items()},
            "before_probability": before.get("hero_probability"),
            "after_probability": after.get("hero_probability"),
            "after_sources": list((after.get("win_probability_sources") or {}).keys()),
        }
        assert emitted["event_id"] == CANON and emitted["removal_rev"] == {
            str(TWIN): removed_rev
        }, result
        assert after["blend_fold_revision"] == {
            str(k): v for k, v in stored.items()
        }, result
        assert (
            after["blend_fold_revision"][str(TWIN)]
            == removed_rev
            > before["blend_fold_revision"][str(TWIN)]
        ), result
        assert "kalshi" not in after["win_probability_sources"], result
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        assert route._open_connections == 0
        assert set(hub.released) == {f"live:event:{CANON}", f"live:event:{TWIN}"}


@pytest.mark.parametrize("detail_id", [CANON, TWIN])
async def test_real_tagged_twin_removal_is_covered_by_actual_detail(
    pg, monkeypatch, detail_id
):
    await removal_floor_pairing(pg, monkeypatch, detail_id)


async def absorbed_ids(Session):
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models.models import Event
    from app.utils.serve_fold_absorbed import serve_fold_absorbed_rows

    async with Session() as db:
        canonical = (
            await db.execute(
                select(Event)
                .options(selectinload(Event.sport))
                .where(Event.id == CANON)
            )
        ).scalar_one()
        return [row.id for row in await serve_fold_absorbed_rows(db, canonical)]


@pytest.mark.parametrize(
    "path,detail_id",
    [("tagged-only", CANON), ("tagged-only", TWIN), ("absorbed-only", CANON)],
)
async def test_each_fold_path_alone_keeps_the_twin_in_both_vectors(
    pg, monkeypatch, path, detail_id
):
    """#9051's twin reaches BOTH vectors by TWO paths at once: it is tagged
    ``provenance:duplicate-of`` with agreeing slots, AND the serve-time fold
    (#3391) absorbs it (same names, same kickoff). So attempt131's cases stay
    green when either path alone drops it (measured: a stream-only or
    detail-only drop of the tagged arm survives them). Each arm here isolates
    one path, proves the isolation from the real serve fold first, then runs
    the same paired assertions.

    * tagged-only: the twin's kickoff moves one hour, outside the serve fold's
      30-minute and 2.5-4.5-hour candidate windows; the tag still folds it.
    * absorbed-only: the tag is removed; the serve fold still absorbs it.
      Canonical detail only: an UNTAGGED row's own detail id serves that row
      alone (measured ``{TWIN: 1}``), so the canonical-stream / twin-detail
      pairing exists only for a tagged twin, and its page streams its own id.
    """
    engine, Session = pg
    async with engine.begin() as db:
        if path == "tagged-only":
            await db.execute(
                text(
                    "UPDATE events SET commence_time = commence_time + "
                    "interval '1 hour' WHERE id = :id"
                ),
                {"id": TWIN},
            )
        else:
            await db.execute(
                text("UPDATE events SET event_tags = '[]'::jsonb WHERE id = :id"),
                {"id": TWIN},
            )
    assert await absorbed_ids(Session) == ([] if path == "tagged-only" else [TWIN])
    await removal_floor_pairing(pg, monkeypatch, detail_id)


@pytest.mark.parametrize("detail_id", [CANON, TWIN])
async def test_a_reversed_slot_tagged_twin_is_in_neither_vector(
    pg, monkeypatch, detail_id
):
    """Lane1 131 review: the reversed-slot arm, paired. The reversed row is
    tagged to the canonical and carries its own source, yet its home/away
    disagree with the canonical's, so neither the stream nor the detail may
    fold it — while the agreeing twin's key still appears in both, and still
    tracks its own real removal."""
    from app.models.models import Event

    engine, Session = pg
    async with Session() as db:
        canonical = await db.get(Event, CANON)
        db.add(
            Event(
                id=REVERSED,
                sport_id=canonical.sport_id,
                home_team_name=canonical.away_team_name,
                away_team_name=canonical.home_team_name,
                commence_time=datetime.now(timezone.utc) - timedelta(minutes=30),
                status="live",
                event_tags=[f"provenance:duplicate-of:{CANON}"],
                win_probability_sources={"espn": _reading(0.1)},
            )
        )
        await db.commit()
    await freshen(engine)
    hub = mount(monkeypatch, Session)
    async with Session() as db:
        before = await events.build_event_detail_uncoalesced(db, detail_id)
    response = await route.stream_event(CANON, Request())
    chunks = []

    async def collect():
        async for chunk in response.body_iterator:
            chunks.append(chunk)

    task = asyncio.create_task(collect())
    try:
        await until(lambda: bool(data(chunks, "reconcile")))
        initial = data(chunks, "reconcile")[0]
        result = {
            "requested_detail_id": detail_id,
            "initial": initial,
            "before_detail_revision": before["blend_fold_revision"],
            "subscriptions": sorted(hub.subscriptions),
        }
        assert set(initial["removal_rev"]) == {str(CANON), str(TWIN)}, result
        assert initial["removal_rev"] == before["blend_fold_revision"], result
        assert set(hub.subscriptions) == {
            f"live:event:{CANON}",
            f"live:event:{TWIN}",
        }, result
        # The reversed row moves its own revision; neither vector follows it.
        reversed_rev = await _drop_source(Session, REVERSED, "espn")
        removed_rev = await _drop_source(Session, TWIN, "kalshi")
        async with Session() as db:
            after = await events.build_event_detail_uncoalesced(db, detail_id)
        result.update(
            reversed_rev=reversed_rev,
            removed_rev=removed_rev,
            after_detail_revision=after["blend_fold_revision"],
        )
        assert reversed_rev >= 1, result
        assert str(REVERSED) not in after["blend_fold_revision"], result
        assert set(after["blend_fold_revision"]) == {str(CANON), str(TWIN)}, result
        assert (
            after["blend_fold_revision"][str(TWIN)]
            == removed_rev
            > before["blend_fold_revision"][str(TWIN)]
        ), result
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        assert route._open_connections == 0
        assert set(hub.released) == {f"live:event:{CANON}", f"live:event:{TWIN}"}
