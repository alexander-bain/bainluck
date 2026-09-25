"""Win-probability retention stops inventing observed history. #7878, real Postgres.

The reader defect (#7878): a live chart drew a flat line straight across a
3h17m stretch nobody observed (`/events/15316479`). Codex's card-B decision
(2026-09-24, `artifacts/chart-sprint-coordinator/20260924T190720Z/7878-decision.md`)
makes consecutive `captured_at` spacing the only coverage evidence, at a display
resolution G of 5 minutes, and chose producer option (b): the 48-hour retention
collapse must stop destroying that evidence. Before this change
`collapse-winprob-snapshots-daily` merged runs of equal HOME price with no gap
bound and kept `MIN(id)` — Codex's offline replay showed it losing away/draw and
period changes, picking an out-of-time keeper, and turning 10:00/10:01/12:00
into one row. Once merged, the 12:00 gap is gone for good and no consumer can
draw it honestly.

## why Postgres

The whole rule is one SQL statement of window functions over a JSONB tuple;
`test_retention_sql.py` simulates the OLD statement in Python and can only
check the new one's text. Every case here seeds real `win_prob_snapshots` rows
in its own event, runs the real `_collapse_partition_sql` through the winprob
config, and reads back what survived. Each case is one of the guards the
decision names in its section 6, in its order.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

#: A database of its own, for the reason `test_a_delay_is_not_silence_pg_7617.py`
#: gives: this file drops and creates the handful of tables it touches, and the
#: shared recall database carries inbound foreign keys that make that drop fail.
#: CI's `search-recall` job provisions a disposable one. No fallback URL.
DB_URL = os.environ.get("EVIDENCE_COLLAPSE_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set EVIDENCE_COLLAPSE_DATABASE_URL to run the real-Postgres #7878 "
            "collapse contract (CI job `search-recall` provisions a disposable one)"
        ),
    ),
]

#: Every seeded reading is 72h old, so all of it is past the 48h collapse cutoff
#: except rows a case deliberately places after the cutoff.
AGE = timedelta(hours=72)
CUTOFF_AGE = timedelta(hours=48)


def _obs(t, home=0.60, away=0.40, draw=None, **state):
    """A raw observed reading `t` minutes after the case's base instant."""
    gs = {"market_id": 555, "outcome_name": "Home", "poll_type": "live_fast", **state}
    return {"t": t, "home": home, "away": away, "draw": draw, "gs": gs}


@pytest.fixture
async def db():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    wanted = [
        Base.metadata.tables[name]
        for name in ("sports", "teams", "venues", "events", "win_prob_snapshots")
    ]
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all, tables=wanted, checkfirst=True)
        await conn.run_sync(Base.metadata.create_all, tables=wanted)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    yield maker
    await engine.dispose()


async def _seed(maker, readings, *, name, tail_after_cutoff=True, age=AGE):
    """One event, one `kalshi` series, rows inserted in the order given.

    Insert order is id order, so a case can make id order disagree with time
    order. ``tail_after_cutoff`` appends a fresh reading so the series' LAST row
    is not among the aged ones — the terminal-row exclusion is its own case.
    Returns (event_id, base, {t: row_id}).
    """
    from app.models.models import Event, Sport, WinProbSnapshot

    now = datetime.now(timezone.utc).replace(microsecond=0)
    base = now - age
    async with maker() as session:
        sport = Sport(key=f"americanfootball_nfl_{name}", name=f"NFL {name}")
        session.add(sport)
        await session.flush()
        event = Event(
            sport_id=sport.id,
            home_team_name=f"Home {name}",
            away_team_name=f"Away {name}",
            commence_time=base,
            status="completed",
        )
        session.add(event)
        await session.flush()
        ids = {}
        rows = list(readings)
        if tail_after_cutoff:
            rows.append(_obs(int((age - CUTOFF_AGE).total_seconds() // 60) + 60, home=0.99, away=0.01))
        for r in rows:
            snap = WinProbSnapshot(
                event_id=event.id,
                source="kalshi",
                captured_at=base + timedelta(minutes=r["t"]),
                home_win_probability=r["home"],
                away_win_probability=r["away"],
                draw_probability=r["draw"],
                game_state=r["gs"],
                reading_count=r.get("count", 1),
                valid_until=(
                    base + timedelta(minutes=r["valid_until"]) if "valid_until" in r else None
                ),
            )
            session.add(snap)
            await session.flush()  # one INSERT per row: insert order == id order
            ids[r["t"]] = snap.id
        await session.commit()
    return event.id, base, ids


async def _collapse(maker, event_id):
    from app.tasks.retention import _TABLE_CONFIG, _collapse_partition_sql

    cutoff = datetime.now(timezone.utc) - CUTOFF_AGE
    async with maker() as session:
        out = await _collapse_partition_sql(session, _TABLE_CONFIG["winprob"], event_id, cutoff)
        await session.commit()
    return out


async def _rows(maker, event_id):
    from sqlalchemy import select

    from app.models.models import WinProbSnapshot

    async with maker() as session:
        res = await session.execute(
            select(WinProbSnapshot)
            .where(WinProbSnapshot.event_id == event_id)
            .order_by(WinProbSnapshot.captured_at, WinProbSnapshot.id)
        )
        return res.scalars().all()


def _span(row):
    return (row.game_state or {}).get("evidence_span")


def _through(row):
    span = _span(row)
    return datetime.fromisoformat(span["covered_through"].replace("Z", "+00:00")) if span else None


async def test_1_counterexample_10_00_10_01_then_12_00(db):
    """The decision's own counterexample: the 12:00 reading keeps its own row."""
    eid, base, ids = await _seed(db, [_obs(0), _obs(1), _obs(120)], name="c1")
    deleted, stamped = await _collapse(db, eid)
    rows = await _rows(db, eid)
    kept = [r.id for r in rows]
    assert (deleted, stamped) == (1, 1)
    assert ids[0] in kept and ids[1] not in kept and ids[120] in kept
    keeper = next(r for r in rows if r.id == ids[0])
    span = _span(keeper)
    assert span["contract"] == "7878.v1" and span["resolution_s"] == 300
    assert _through(keeper) == base + timedelta(minutes=1)
    # The 12:00 row stays a point: nothing claims the two hours before it.
    assert _span(next(r for r in rows if r.id == ids[120])) is None


@pytest.mark.parametrize(
    "second",
    [
        pytest.param(dict(away=0.35, draw=0.05), id="away-and-draw-moved"),
        pytest.param(dict(draw=0.10, away=0.30), id="draw-appeared"),
        pytest.param(dict(period="2nd Quarter"), id="period-changed"),
        pytest.param(dict(home_score=7), id="score-changed"),
        pytest.param(dict(market_id=777), id="different-market"),
    ],
)
async def test_2_equal_home_is_not_the_same_reading(db, second):
    first = _obs(0, period="1st Quarter", home_score=0)
    gs = {k: v for k, v in second.items() if k not in ("away", "draw")}
    other = _obs(
        1,
        away=second.get("away", 0.40),
        draw=second.get("draw"),
        **{"period": "1st Quarter", "home_score": 0, **gs},
    )
    eid, _, ids = await _seed(db, [first, other], name="c2")
    assert await _collapse(db, eid) == (0, 0)
    assert {r.id for r in await _rows(db, eid)} >= {ids[0], ids[1]}


async def test_3_out_of_order_backfill_ids_keep_the_earliest_capture(db):
    """The 10:02 reading is inserted first (lower id); 10:00 arrives later."""
    eid, base, ids = await _seed(db, [_obs(2), _obs(0)], name="c3")
    assert ids[2] < ids[0]
    assert await _collapse(db, eid) == (1, 1)
    kept = {r.id for r in await _rows(db, eid)}
    assert ids[0] in kept and ids[2] not in kept, "keeper must be earliest captured_at, not MIN(id)"
    keeper = next(r for r in await _rows(db, eid) if r.id == ids[0])
    assert keeper.captured_at == base
    assert _through(keeper) == base + timedelta(minutes=2)


async def test_4_exactly_g_merges_and_one_second_more_does_not(db):
    eid, base, ids = await _seed(db, [_obs(0), _obs(5)], name="c4a")
    assert await _collapse(db, eid) == (1, 1)

    eid2, base2, ids2 = await _seed(db, [_obs(0), _obs(5)], name="c4b")
    # Push the second reading one second past G.
    from sqlalchemy import update

    from app.models.models import WinProbSnapshot as W

    async with db() as session:
        await session.execute(
            update(W).where(W.id == ids2[5]).values(captured_at=base2 + timedelta(minutes=5, seconds=1))
        )
        await session.commit()
    assert await _collapse(db, eid2) == (0, 0)


async def test_5_repeat_collapse_is_idempotent_and_composes(db):
    eid, base, ids = await _seed(db, [_obs(0), _obs(3), _obs(6)], name="c5")
    assert await _collapse(db, eid) == (2, 1)
    before = [(r.id, r.game_state, r.valid_until, r.reading_count) for r in await _rows(db, eid)]
    assert await _collapse(db, eid) == (0, 0), "a second pass over collapsed rows must change nothing"
    assert [(r.id, r.game_state, r.valid_until, r.reading_count) for r in await _rows(db, eid)] == before

    # A new aged reading within G of the stamped span's end joins it: the span
    # composes to the new capture, the keeper stays the earliest row.
    from app.models.models import WinProbSnapshot

    async with db() as session:
        session.add(
            WinProbSnapshot(
                event_id=eid, source="kalshi", captured_at=base + timedelta(minutes=10),
                home_win_probability=0.60, away_win_probability=0.40,
                game_state=_obs(10)["gs"], reading_count=1,
            )
        )
        await session.commit()
    assert await _collapse(db, eid) == (1, 1)
    keeper = next(r for r in await _rows(db, eid) if r.id == ids[0])
    assert _through(keeper) == base + timedelta(minutes=10)


async def test_6_legacy_compacted_row_gets_no_fabricated_coverage(db):
    """A row compacted before this contract: huge count, valid_until 2h on, no stamp."""
    legacy = dict(_obs(0), count=120, valid_until=120)
    foreign = dict(
        _obs(200),
        gs={**_obs(200)["gs"], "evidence_span": {
            "contract": "7878.v0", "resolution_s": 300,
            "covered_through": "2099-01-01T00:00:00.000000Z",
        }},
    )
    eid, _, ids = await _seed(db, [legacy, _obs(120), foreign, _obs(320)], name="c6")
    assert await _collapse(db, eid) == (0, 0)
    assert {ids[0], ids[120], ids[200], ids[320]} <= {r.id for r in await _rows(db, eid)}


async def test_7_completed_terminal_row_is_not_evidence(db):
    """The series' last row is rewritten in place on a completed game (#922)."""
    eid, base, ids = await _seed(
        db, [_obs(0), _obs(2), _obs(4)], name="c7", tail_after_cutoff=False
    )
    assert await _collapse(db, eid) == (1, 1)
    rows = await _rows(db, eid)
    assert ids[4] in {r.id for r in rows}, "terminal row must survive, unmerged"
    keeper = next(r for r in rows if r.id == ids[0])
    assert _through(keeper) == base + timedelta(minutes=2), "coverage must stop before the terminal row"


async def test_8_live_edge_cannot_manufacture_an_observed_point(db):
    """The span ends at the last genuine capture, never at the cutoff or a later row."""
    eid, base, ids = await _seed(db, [_obs(0), _obs(4), _obs(8)], name="c8")
    await _collapse(db, eid)
    rows = await _rows(db, eid)
    keeper = next(r for r in rows if r.id == ids[0])
    assert _through(keeper) == base + timedelta(minutes=8)
    # Nothing was created: every surviving timestamp is one we captured.
    captured = {base + timedelta(minutes=t) for t in (0, 4, 8)}
    assert all(r.captured_at in captured or r.captured_at > base + timedelta(hours=20) for r in rows)


async def test_9_candle_derived_rows_keep_their_provenance(db):
    candle = lambda t: dict(  # noqa: E731
        _obs(t), gs={"market_id": 555, "outcome_name": "Home",
                     "poll_type": "history_backfill", "backfill_source": "kalshi_candlesticks"},
    )
    clob = lambda t: dict(_obs(t), gs={"market_id": 555, "backfill": True})  # noqa: E731
    eid, _, ids = await _seed(
        db, [candle(0), candle(1), clob(2), clob(3), _obs(10), candle(11), _obs(12)], name="c9"
    )
    assert await _collapse(db, eid) == (0, 0)
    rows = await _rows(db, eid)
    assert set(ids.values()) <= {r.id for r in rows}
    assert all(_span(r) is None for r in rows), "no backfill row may carry an observation span"


async def test_5b_a_later_stamped_span_composes_into_the_earlier_keeper(db):
    """Two runs stamped by one pass, joined by readings that land between them later.

    The second pass must carry the LATER keeper's validated span end (23), not
    stop at the latest raw capture in the run (20): that is what "compose existing
    validated spans" means, and it is the only case where the two differ.
    """
    eid, base, ids = await _seed(db, [_obs(0), _obs(3), _obs(20), _obs(23)], name="c5b")
    assert await _collapse(db, eid) == (2, 2)
    later = next(r for r in await _rows(db, eid) if r.id == ids[20])
    assert _through(later) == base + timedelta(minutes=23)

    from app.models.models import WinProbSnapshot

    async with db() as session:
        for t in (7, 11, 15):
            session.add(
                WinProbSnapshot(
                    event_id=eid, source="kalshi", captured_at=base + timedelta(minutes=t),
                    home_win_probability=0.60, away_win_probability=0.40,
                    game_state=_obs(t)["gs"], reading_count=1,
                )
            )
        await session.commit()
    assert await _collapse(db, eid) == (4, 1)
    rows = await _rows(db, eid)
    keeper = next(r for r in rows if r.id == ids[0])
    assert ids[20] not in {r.id for r in rows}
    assert _through(keeper) == base + timedelta(minutes=23)


async def test_10_espn_play_by_play_backfill_never_merges_8514(db):
    """#8514: ESPN's win-probability backfill writes `backfilled`, not `backfill`.

    Its pre-#8514 rows sit 200 s apart at estimated instants, so equal neighbours
    passed every clause above and came back stamped as observed coverage of a
    stretch nobody watched. Its #8514 rows are at true play times but are still
    written after the fact. Neither kind may merge or carry a span; a raw reading
    beside them still merges as before (the control arm).
    """
    estimate = lambda t: dict(  # noqa: E731
        _obs(t), gs={"seconds_left": None, "backfilled": True},
    )
    evidenced = lambda t: dict(  # noqa: E731
        _obs(t), gs={"seconds_left": None, "backfilled": True,
                     "time_basis": "play_wallclock", "play_id": f"p{t}"},
    )
    eid, base, ids = await _seed(
        db,
        [estimate(0), estimate(3), estimate(6), evidenced(10), evidenced(12),
         _obs(20), _obs(22)],
        name="c10",
    )
    assert await _collapse(db, eid) == (1, 1), "only the two raw readings may merge"
    rows = await _rows(db, eid)
    survivors = {r.id for r in rows}
    for t in (0, 3, 6, 10, 12):
        assert ids[t] in survivors, t
    assert ids[22] not in survivors
    backfilled = [r for r in rows if (r.game_state or {}).get("backfilled") is True]
    assert len(backfilled) == 5
    assert all(_span(r) is None for r in backfilled)
    keeper = next(r for r in rows if r.id == ids[20])
    assert _through(keeper) == base + timedelta(minutes=22)


# ---------------------------------------------------------------------------
# Which partitions a pass reaches (#7878 retention-selection blocker)
# ---------------------------------------------------------------------------
#
# Codex, 2026-09-25 15:45Z: the released selector was `SELECT DISTINCT event_id
# WHERE captured_at < cutoff LIMIT 500` with no order and no cursor. A collapse
# leaves keepers behind, so a processed partition stays eligible and the same
# 500 came back every day; production's selection was ids 1..5,225,589 and
# neither September specimen. These cases run the real task body
# (`_collapse_snapshots_impl(table="winprob")`) against real Postgres with a
# dict standing in for Redis, and read which events it collapsed.


class _FakeRedis:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value):
        self.store[key] = value.encode() if isinstance(value, str) else value
        return True


@pytest.fixture
def rig(db, monkeypatch):
    from contextlib import asynccontextmanager

    import app.tasks.redis_state as redis_state
    import app.tasks.retention as retention

    fake = _FakeRedis()
    monkeypatch.setattr(redis_state, "get_redis_client", lambda *a, **k: fake)

    @asynccontextmanager
    async def session_cm(**_kw):
        async with db() as session:
            try:
                yield session
                await session.commit()
            except BaseException:
                await session.rollback()
                raise

    monkeypatch.setattr(retention, "get_task_session", session_cm)
    return fake


async def _pass(limit):
    from app.tasks.retention import _collapse_snapshots_impl

    return await _collapse_snapshots_impl(min_age_hours=48, table="winprob", limit=limit)


def _pair():
    """A mergeable pair and a lone point: collapsing it is (1 deleted, 1 stamped)."""
    return [_obs(0), _obs(1), _obs(120)]


async def _collapsed(maker, event_id):
    return any(_span(r) for r in await _rows(maker, event_id))


async def test_11_a_processed_partition_is_not_selected_again_and_the_walk_moves_on(db, rig):
    e1, *_ = await _seed(db, _pair(), name="w1", age=timedelta(hours=100))
    e2, *_ = await _seed(db, _pair(), name="w2", age=timedelta(hours=90))
    e3, *_ = await _seed(db, _pair(), name="w3", age=timedelta(hours=80))

    first = await _pass(limit=2)
    assert (first["partitions_selected"], first["partitions_processed"]) == (2, 2)
    assert first["resumed_from"] == "floor:absent"
    assert first["caught_up"] is False
    assert [await _collapsed(db, e) for e in (e1, e2, e3)] == [True, True, False]
    assert first["watermark"]["event_id"] == e2

    second = await _pass(limit=2)
    assert second["resumed_from"] == "redis"
    assert (second["partitions_selected"], second["rows_deleted"]) == (1, 1), (
        "only the partition the first pass did not reach may be selected"
    )
    assert await _collapsed(db, e3)
    assert second["caught_up"] is True

    third = await _pass(limit=2)
    assert third["partitions_selected"] == 0

    # The control: the released predicate still matches all three processed
    # partitions — a collapse leaves keepers behind, which is the whole defect.
    from sqlalchemy import text

    cutoff = datetime.now(timezone.utc) - CUTOFF_AGE
    async with db() as session:
        res = await session.execute(
            text("SELECT DISTINCT event_id FROM win_prob_snapshots WHERE captured_at < :c"),
            {"c": cutoff},
        )
        assert {r[0] for r in res} == {e1, e2, e3}


async def test_12_a_partition_still_being_written_comes_back_for_its_newly_aged_rows(db, rig):
    from app.models.models import WinProbSnapshot

    done, *_ = await _seed(db, _pair(), name="w12a", age=timedelta(hours=90))
    live, base, _ = await _seed(db, _pair(), name="w12b", age=timedelta(hours=80))
    assert (await _pass(limit=10))["partitions_processed"] == 2

    # Two equal readings that aged after the first pass's watermark, still
    # before the series' fresh tail row.
    now = datetime.now(timezone.utc).replace(microsecond=0)
    async with db() as session:
        for at in (now - timedelta(hours=49), now - timedelta(hours=49) + timedelta(minutes=2)):
            session.add(
                WinProbSnapshot(
                    event_id=live, source="kalshi", captured_at=at,
                    home_win_probability=0.55, away_win_probability=0.45,
                    game_state=_obs(0, home=0.55, away=0.45)["gs"], reading_count=1,
                )
            )
        await session.commit()

    again = await _pass(limit=10)
    assert again["partitions_selected"] == 1, "the finished partition must not come back"
    assert again["watermark"]["event_id"] == live
    assert (again["rows_deleted"], again["keepers_updated"]) == (1, 1)


@pytest.mark.parametrize(
    "stored, source",
    [
        pytest.param(None, "floor:absent", id="absent"),
        pytest.param(b"not json", "floor:malformed", id="malformed"),
        pytest.param("behind", "floor:behind", id="behind-the-floor"),
    ],
)
async def test_13_an_unusable_watermark_resumes_at_the_floor_not_the_ancient_tail(
    db, rig, stored, source
):
    import json

    from app.tasks.retention import WINPROB_SELECTOR_FLOOR_HOURS, WINPROB_WATERMARK_KEY

    beyond = CUTOFF_AGE + timedelta(hours=WINPROB_SELECTOR_FLOOR_HOURS + 30)
    ancient, *_ = await _seed(db, _pair(), name="w13a", age=beyond)
    recent, *_ = await _seed(db, _pair(), name="w13b", age=timedelta(hours=80))
    if stored == "behind":
        stored = json.dumps({
            "last_aged": (datetime.now(timezone.utc) - beyond - timedelta(days=30)).isoformat(),
            "event_id": 1,
        }).encode()
    if stored is not None:
        rig.store[WINPROB_WATERMARK_KEY] = stored

    out = await _pass(limit=10)
    assert out["resumed_from"] == source
    assert out["partitions_selected"] == 1
    assert await _collapsed(db, recent)
    assert not await _collapsed(db, ancient)


async def test_14_one_failing_partition_is_passed_and_a_failure_streak_stops_on_the_last_success(
    db, rig, monkeypatch
):
    import app.tasks.retention as retention

    ids = []
    for n, hours in enumerate((100, 95, 90, 85)):
        eid, *_ = await _seed(db, _pair(), name=f"w14{n}", age=timedelta(hours=hours))
        ids.append(eid)
    real = retention._collapse_partition_sql
    poison = set()

    async def flaky(session, cfg, part_id, cutoff):
        if part_id in poison:
            raise RuntimeError(f"boom {part_id}")
        return await real(session, cfg, part_id, cutoff)

    monkeypatch.setattr(retention, "_collapse_partition_sql", flaky)

    # A streak of three stops the pass; the watermark stays on the last success,
    # so the three are retried next time rather than walked past.
    poison.update(ids[1:])
    out = await _pass(limit=10)
    assert out["stopped_on_failures"] is True
    assert (out["partitions_processed"], out["partitions_failed"]) == (1, 3)
    assert out["watermark"]["event_id"] == ids[0]

    poison.clear()
    poison.add(ids[2])
    out = await _pass(limit=10)
    assert out["stopped_on_failures"] is False
    assert out["failed_event_ids"] == [ids[2]]
    assert [await _collapsed(db, e) for e in ids] == [True, True, False, True]
    assert out["watermark"]["event_id"] == ids[3]


async def test_15_the_soft_time_limit_is_not_swallowed(db, rig, monkeypatch):
    from celery.exceptions import SoftTimeLimitExceeded

    import app.tasks.retention as retention

    e1, *_ = await _seed(db, _pair(), name="w15a", age=timedelta(hours=100))
    e2, *_ = await _seed(db, _pair(), name="w15b", age=timedelta(hours=90))
    real = retention._collapse_partition_sql

    async def expires(session, cfg, part_id, cutoff):
        if part_id == e2:
            raise SoftTimeLimitExceeded()
        return await real(session, cfg, part_id, cutoff)

    monkeypatch.setattr(retention, "_collapse_partition_sql", expires)
    with pytest.raises(SoftTimeLimitExceeded):
        await _pass(limit=10)
    import json

    assert json.loads(rig.store[retention.WINPROB_WATERMARK_KEY])["event_id"] == e1
