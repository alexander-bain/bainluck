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


async def _seed(maker, readings, *, name, tail_after_cutoff=True):
    """One event, one `kalshi` series, rows inserted in the order given.

    Insert order is id order, so a case can make id order disagree with time
    order. ``tail_after_cutoff`` appends a fresh reading so the series' LAST row
    is not among the aged ones — the terminal-row exclusion is its own case.
    Returns (event_id, base, {t: row_id}).
    """
    from app.models.models import Event, Sport, WinProbSnapshot

    now = datetime.now(timezone.utc).replace(microsecond=0)
    base = now - AGE
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
            rows.append(_obs(int((AGE - CUTOFF_AGE).total_seconds() // 60) + 60, home=0.99, away=0.01))
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
