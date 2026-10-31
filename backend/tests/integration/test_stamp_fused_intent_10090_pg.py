"""#10090 — a stamp's publication intent written by the stamping statement.

`LIVE_STAMP_FUSED_INTENT=1` folds the `<source>_price_publish` INSERT into the
stamp UPDATE as a data-modifying CTE (`stamp_with_publication_intent`), saving
one round trip per stamp. These controls hold it to the separate path on real
Postgres: the same returned bag and revision, the same intent row, nothing
owed when the UPDATE matches nothing or the admits guard refuses, nothing left
behind by a rollback or a statement-timeout cancel, and — under a concurrent
writer — the intent names the revision the trigger assigned AFTER the row
wait, never the snapshot's. Order and coherence on one machine, not timing.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import insert, select, text, update

from app.models.models import Event, OwedChartPoint, Sport
from app.tasks.live_blend_refresh import (
    atomic_stamp_expression,
    observation_admits_clause,
    stamp_with_publication_intent,
)
from tests.integration.test_live_blend_grouped_commit_8129_pg import (  # noqa: F401
    DB_URL,
    rig,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL, reason="requires disposable SEARCH_TEST_DATABASE_URL"
    ),
]

SOURCE = "polymarket"
INTENT = "polymarket_price_publish"

#: Prior bags: empty, a sibling source only, this source with a basis older and
#: newer than the reading's, and two malformed shapes the stamp repairs.
PRIOR_BAGS = {
    "empty": {},
    "sibling_only": {"kalshi": {"value": 0.4, "updated_at": "2026-10-31T12:00:00+00:00"}},
    "own_older_basis": {SOURCE: {"value": 0.55, "observed_value": 0.55,
                                 "observed_basis": {"r1": 100.0},
                                 "updated_at": "2026-10-31T12:00:00+00:00"}},
    "own_newer_basis": {SOURCE: {"value": 0.55, "observed_value": 0.55,
                                 "observed_basis": {"r1": 900.0},
                                 "updated_at": "2026-10-31T12:00:00+00:00"}},
    "own_not_object": {SOURCE: "0.5"},
    "null_bag": None,
}
BASIS = {"r1": 500.0}


async def _seed(rig, bags):
    """One live event per bag, ids 1..n, in `bags` order."""
    now = datetime.now(timezone.utc)
    async with rig.maker() as session:
        sport = Sport(key="baseball_mlb", name="MLB")
        session.add(sport)
        await session.flush()
        for eid, bag in enumerate(bags, start=1):
            session.add(Event(
                id=eid, sport_id=sport.id, home_team_name="Chicago Cubs",
                away_team_name="Miami Marlins", commence_time=now - timedelta(minutes=30),
                status="live", win_probability_sources=bag,
                opening_home_probability=0.5,
            ))
        await session.commit()


def _stamp(event_id, value, basis):
    """The stamp UPDATE exactly as `_refresh_batch` builds it."""
    stamp = (
        update(Event).where(Event.id == event_id)
        .execution_options(synchronize_session=False)
    )
    admits = observation_admits_clause(SOURCE, basis)
    if admits is not None:
        stamp = stamp.where(admits)
    return stamp.values(
        win_probability_sources=atomic_stamp_expression(
            SOURCE, value, eligibility=None, observed_basis=basis,
        )
    ).returning(Event.win_probability_sources, Event.win_probability_sources_rev)


async def _separate(session, event_id, value, basis):
    """Today's path: the UPDATE, then the INSERT under its Python condition."""
    row = (await session.execute(_stamp(event_id, value, basis))).first()
    new_sources, new_rev = (None, None) if row is None else row
    if new_sources is None:
        return None
    stamped_at = new_sources[SOURCE]["updated_at"]
    if isinstance(new_rev, int) and not isinstance(new_rev, bool):
        await session.execute(insert(OwedChartPoint).values(
            source=INTENT, event_id=event_id, value=value,
            reading={"rev": new_rev, "updated_at": stamped_at},
        ))
    return row


async def _fused(session, event_id, value, basis, stamp=None):
    statement = stamp_with_publication_intent(
        stamp if stamp is not None else _stamp(event_id, value, basis),
        source=SOURCE, intent_source=INTENT, event_id=event_id, value=value,
    )
    return (await session.execute(statement)).first()


async def _intents(rig):
    async with rig.maker() as session:
        rows = (await session.execute(
            select(OwedChartPoint.source, OwedChartPoint.event_id,
                   OwedChartPoint.value, OwedChartPoint.reading)
            .order_by(OwedChartPoint.id)
        )).all()
    return [tuple(r) for r in rows]


async def _event(rig, event_id):
    async with rig.maker() as session:
        return tuple((await session.execute(
            select(Event.win_probability_sources, Event.win_probability_sources_rev)
            .where(Event.id == event_id)
        )).one())


def _without_clock(bag):
    if not isinstance(bag, dict):
        return bag
    out = dict(bag)
    if isinstance(out.get(SOURCE), dict):
        out[SOURCE] = {k: v for k, v in out[SOURCE].items() if k != "updated_at"}
    return out


@pytest.mark.parametrize("basis", [None, BASIS], ids=["unguarded", "guarded"])
async def test_fused_matches_separate_for_every_prior_bag(rig, basis):
    names = list(PRIOR_BAGS)
    await _seed(rig, [PRIOR_BAGS[n] for n in names] * 2)
    n = len(names)
    returned = {}
    async with rig.maker() as session:
        for i in range(n):
            returned[("separate", i)] = await _separate(session, i + 1, 0.6123, basis)
            returned[("fused", i)] = await _fused(session, n + i + 1, 0.6123, basis)
        await session.commit()
    intents = await _intents(rig)
    by_event = {}
    for row in intents:
        assert row[0] == INTENT
        assert row[1] not in by_event, "one intent per stamp, never two"
        by_event[row[1]] = row
    for i, name in enumerate(names):
        sep, fus = returned[("separate", i)], returned[("fused", i)]
        assert (sep is None) == (fus is None), name
        sep_after, fus_after = await _event(rig, i + 1), await _event(rig, n + i + 1)
        assert _without_clock(sep_after[0]) == _without_clock(fus_after[0]), name
        assert sep_after[1] == fus_after[1], name
        if sep is None:
            # Refused by the admits guard: no stamp, nothing owed, both ways.
            assert name == "own_newer_basis" and basis is not None
            assert i + 1 not in by_event and n + i + 1 not in by_event
            continue
        assert _without_clock(sep[0]) == _without_clock(fus[0]), name
        assert sep[1] == fus[1], name
        for eid, ret in ((i + 1, sep), (n + i + 1, fus)):
            _src, _eid, value, reading = by_event[eid]
            assert value == 0.6123
            # Each intent names exactly the write its own statement returned.
            assert reading == {"rev": ret[1], "updated_at": ret[0][SOURCE]["updated_at"]}
            assert (await _event(rig, eid)) == (ret[0], ret[1])


async def test_no_row_and_no_bag_owe_nothing(rig):
    await _seed(rig, [{}])
    async with rig.maker() as session:
        # The row went away: the UPDATE matches nothing.
        assert await _fused(session, 99, 0.5, None) is None
        # A RETURNING row whose bag decodes to None — JSON null (what the ORM
        # binds for None) or SQL NULL: the separate path's `new_sources is
        # None` skip owes no intent; neither does this.
        for null in (None, text("NULL")):
            nulling = (
                update(Event).where(Event.id == 1)
                .execution_options(synchronize_session=False)
                .values(win_probability_sources=null)
                .returning(Event.win_probability_sources, Event.win_probability_sources_rev)
            )
            row = await _fused(session, 1, 0.5, None, stamp=nulling)
            assert row is not None and row[0] is None
        await session.commit()
    assert await _intents(rig) == []


async def test_rollback_leaves_neither_stamp_nor_intent(rig):
    await _seed(rig, [{}])
    before = await _event(rig, 1)
    async with rig.maker() as session:
        assert await _fused(session, 1, 0.7, None) is not None
        await session.rollback()
    assert await _intents(rig) == []
    assert await _event(rig, 1) == before


async def test_statement_timeout_cancel_rolls_back_both(rig):
    """The stamp's whole-statement bound (#11138) cancels the fused statement
    while it waits on a held row; nothing of it survives the rollback."""
    await _seed(rig, [{}])
    before = await _event(rig, 1)
    async with rig.maker() as holder, rig.maker() as stamper:
        await holder.execute(text("SELECT 1 FROM events WHERE id = 1 FOR UPDATE"))
        await stamper.execute(text("SET LOCAL statement_timeout = '150ms'"))
        with pytest.raises(Exception) as caught:
            await _fused(stamper, 1, 0.7, None)
        assert "statement timeout" in str(caught.value) or "57014" in str(caught.value)
        await stamper.rollback()
        await holder.rollback()
    assert await _intents(rig) == []
    assert await _event(rig, 1) == before


@pytest.mark.parametrize("holder_basis, admitted", [(100.0, True), (900.0, False)],
                         ids=["holder_older_admits", "holder_newer_refuses"])
async def test_concurrent_writer_intent_names_the_post_wait_revision(rig, holder_basis, admitted):
    """A stamp that waits on another writer's row lock re-reads the committed
    row (READ COMMITTED), so the trigger's revision and the admits guard both
    see the holder's write. The intent must carry THAT revision — the one the
    statement returned — and a refused stamp must owe nothing."""
    await _seed(rig, [{}])
    _bag0, rev0 = await _event(rig, 1)
    async with rig.maker() as holder, rig.maker() as stamper:
        await holder.execute(
            update(Event).where(Event.id == 1).values(win_probability_sources={
                SOURCE: {"value": 0.5, "observed_value": 0.5,
                         "observed_basis": {"r1": holder_basis},
                         "updated_at": "2026-10-31T12:00:00+00:00"},
            })
        )
        waiting = asyncio.create_task(_fused(stamper, 1, 0.66, BASIS))
        await asyncio.sleep(0.3)
        assert not waiting.done(), "the stamp must be waiting on the holder's row lock"
        await holder.commit()
        row = await waiting
        await stamper.commit()
    intents = await _intents(rig)
    if not admitted:
        assert row is None
        assert intents == []
        assert (await _event(rig, 1))[1] == rev0 + 1  # the holder's write only
        return
    assert row is not None
    assert row[1] == rev0 + 2  # holder's bump, then the stamp's
    assert intents == [(INTENT, 1, 0.66, {"rev": rev0 + 2,
                                          "updated_at": row[0][SOURCE]["updated_at"]})]
