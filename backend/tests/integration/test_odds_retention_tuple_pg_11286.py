"""Odds retention keeps a book's spread/total moves under a flat moneyline. #11286, real Postgres.

The reader defect (#11286): the projected-final-points chart draws one point
per `odds_snapshots` row and reads the row's projected pair (from spread +
total). The 48-hour `collapse-odds-snapshots-daily` pass ran the generic
equal-value collapse with `value_col = home_win_probability`, so two
consecutive rows from one book whose spread, total or projected pair moved
while the home price stayed flat were one "run": it kept `MIN(id)` and
DELETED the rest — the projection change was gone for good. It also merged a
pair row with a following row that never asked for a pair (an h2h-only poll),
stretching the keeper's `valid_until` across the not-collected stretch.

The correction makes the odds run boundary the whole observed row (every value
column the writer stores). Two rows merge only when nothing differs; every
other rule of the generic pass is unchanged — per-book runs inside one event,
chronological order, `MIN(id)` keeper, summed `reading_count`, the 48 h cutoff.
Win-probability retention (#7878) has its own pass and is not touched.

## why Postgres

The rule is two statements of window functions; `test_retention_sql.py` can
only read their text. Every case seeds real `odds_snapshots` rows in its own
event, runs the real `_collapse_partition_sql` through the odds config, and
reads back what survived.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

#: A database of its own, for the reason the #7878 file gives: this file drops
#: and creates the handful of tables it touches. CI provisions a disposable
#: one in the `isolated` group. No fallback URL.
DB_URL = os.environ.get("ODDS_RETENTION_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set ODDS_RETENTION_DATABASE_URL to run the real-Postgres #11286 odds "
            "retention contract (CI's isolated group provisions a disposable one)"
        ),
    ),
]

#: Every seeded row is 72h old, past the 48h cutoff, unless a case places it after.
AGE = timedelta(hours=72)
CUTOFF_AGE = timedelta(hours=48)


def _row(t, book="draftkings", **over):
    """A full NFL observation `t` minutes after the case's base instant."""
    values = dict(
        home_moneyline=-150,
        away_moneyline=130,
        home_spread=-3.0,
        home_spread_odds=-110,
        away_spread_odds=-110,
        over_under=44.5,
        over_odds=-110,
        under_odds=-110,
        home_win_probability=0.5800,
        away_win_probability=0.4200,
        projected_home_score=23.8,
        projected_away_score=20.8,
    )
    values.update(over)
    return {"t": t, "book": book, **values}


#: The pair columns an h2h-only poll leaves NULL (it did not ask for them).
H2H_ONLY = dict(
    home_spread=None,
    home_spread_odds=None,
    away_spread_odds=None,
    over_under=None,
    over_odds=None,
    under_odds=None,
    projected_home_score=None,
    projected_away_score=None,
)


@pytest.fixture
async def db():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    wanted = [
        Base.metadata.tables[name]
        for name in ("sports", "teams", "venues", "events", "odds_snapshots")
    ]
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all, tables=wanted, checkfirst=True)
        await conn.run_sync(Base.metadata.create_all, tables=wanted)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    yield maker
    await engine.dispose()


async def _event(maker, name, base):
    from app.models.models import Event, Sport

    async with maker() as session:
        sport = Sport(key=f"americanfootball_nfl_{name}", name=f"NFL {name}")
        session.add(sport)
        await session.flush()
        event = Event(
            sport_id=sport.id,
            home_team_name=f"Home {name}",
            away_team_name=f"Away {name}",
            commence_time=base + timedelta(days=1),
            status="completed",
        )
        session.add(event)
        await session.commit()
        return event.id


async def _seed(maker, rows, *, name, event_id=None, age=AGE):
    """Rows inserted in the order given (insert order == id order).

    Returns (event_id, base, [row ids in the given order]).
    """
    from app.models.models import OddsSnapshot

    base = datetime.now(timezone.utc).replace(microsecond=0) - age
    if event_id is None:
        event_id = await _event(maker, name, base)
    ids = []
    async with maker() as session:
        for r in rows:
            values = {k: v for k, v in r.items() if k not in ("t", "book", "count", "valid_until")}
            snap = OddsSnapshot(
                event_id=event_id,
                bookmaker=r["book"],
                captured_at=base + timedelta(minutes=r["t"]),
                reading_count=r.get("count", 1),
                valid_until=(
                    base + timedelta(minutes=r["valid_until"]) if "valid_until" in r else None
                ),
                **values,
            )
            session.add(snap)
            await session.flush()  # one INSERT per row: insert order == id order
            ids.append(snap.id)
        await session.commit()
    return event_id, base, ids


async def _collapse(maker, event_id):
    from app.tasks.retention import _TABLE_CONFIG, _collapse_partition_sql

    cutoff = datetime.now(timezone.utc) - CUTOFF_AGE
    async with maker() as session:
        out = await _collapse_partition_sql(session, _TABLE_CONFIG["odds"], event_id, cutoff)
        await session.commit()
    return out


async def _rows(maker, event_id):
    from sqlalchemy import select

    from app.models.models import OddsSnapshot

    async with maker() as session:
        res = await session.execute(
            select(OddsSnapshot)
            .where(OddsSnapshot.event_id == event_id)
            .order_by(OddsSnapshot.bookmaker, OddsSnapshot.captured_at, OddsSnapshot.id)
        )
        return res.scalars().all()


def _pair(row):
    if row.projected_home_score is None:
        return None
    return (float(row.projected_home_score), float(row.projected_away_score))


async def test_1_causal_total_moved_under_a_flat_home_price_survives(db):
    """The defect: equal home probability, the total moved 44.5 → 47.5.

    The home-price-only pass deletes the second row, and the chart loses the
    projection move 23.8–20.8 → 25.3–22.3. Both rows must survive unchanged.
    """
    eid, _, ids = await _seed(
        db,
        [
            _row(0),
            _row(60, over_under=47.5, projected_home_score=25.3, projected_away_score=22.3),
        ],
        name="c1",
    )
    assert await _collapse(db, eid) == (0, 0)
    rows = await _rows(db, eid)
    assert [r.id for r in rows] == ids
    assert [_pair(r) for r in rows] == [(23.8, 20.8), (25.3, 22.3)]
    assert [r.reading_count for r in rows] == [1, 1]


@pytest.mark.parametrize(
    "moved",
    [
        pytest.param(
            dict(home_spread=-6.5, projected_home_score=25.5, projected_away_score=19.0),
            id="spread-and-pair-moved",
        ),
        pytest.param(dict(projected_home_score=24.0, projected_away_score=20.5), id="pair-only-moved"),
        pytest.param(dict(away_moneyline=125, away_win_probability=0.4300), id="away-side-moved"),
        pytest.param(dict(home_moneyline=-155), id="home-moneyline-moved"),
        pytest.param(dict(over_odds=-120, under_odds=100), id="total-prices-moved"),
        pytest.param(H2H_ONLY, id="pair-to-not-collected"),
    ],
)
async def test_2_equal_home_price_is_not_the_same_observation(db, moved):
    eid, _, ids = await _seed(db, [_row(0), _row(30, **moved)], name="c2")
    assert await _collapse(db, eid) == (0, 0)
    assert [r.id for r in await _rows(db, eid)] == ids


async def test_3_not_collected_then_pair_survives(db):
    """A NULL-pair (h2h-only) row followed by the first real pair: both stay."""
    eid, _, ids = await _seed(db, [_row(0, **H2H_ONLY), _row(30)], name="c3")
    assert await _collapse(db, eid) == (0, 0)
    rows = await _rows(db, eid)
    assert [r.id for r in rows] == ids
    assert [_pair(r) for r in rows] == [None, (23.8, 20.8)]


async def test_4_keeper_is_not_stretched_across_a_not_collected_row(db):
    """pair, h2h-only, same pair: three rows, and the first keeper's closure
    ends at the not-collected row — never across it to the later pair."""
    eid, base, ids = await _seed(
        db, [_row(0), _row(60, **H2H_ONLY), _row(120)], name="c4"
    )
    assert await _collapse(db, eid) == (0, 0)
    rows = await _rows(db, eid)
    assert [r.id for r in rows] == ids
    assert rows[0].valid_until == base + timedelta(minutes=60)
    assert rows[1].valid_until == base + timedelta(minutes=120)


async def test_5_whole_tuple_repeats_still_merge(db):
    """Genuinely identical observations still collapse exactly as before:
    MIN(id) keeper, summed readings, closure to the run's latest instant."""
    eid, base, ids = await _seed(
        db,
        [_row(0, count=2), _row(5), _row(10, valid_until=12), _row(20, over_under=47.5)],
        name="c5",
    )
    assert await _collapse(db, eid) == (2, 1)
    rows = await _rows(db, eid)
    assert [r.id for r in rows] == [ids[0], ids[3]]
    keeper = rows[0]
    assert keeper.reading_count == 4
    assert keeper.valid_until == base + timedelta(minutes=12)


async def test_6_identical_not_collected_rows_still_merge(db):
    """Two identical h2h-only rows are one non-observation of the pair: merge."""
    eid, _, ids = await _seed(db, [_row(0, **H2H_ONLY), _row(5, **H2H_ONLY)], name="c6")
    assert await _collapse(db, eid) == (1, 1)
    assert [r.id for r in await _rows(db, eid)] == [ids[0]]


async def test_7_runs_are_chronological(db):
    """A, A, B, A: the returning A is its own run, never folded into the first."""
    b = dict(over_under=47.5, projected_home_score=25.3, projected_away_score=22.3)
    eid, _, ids = await _seed(db, [_row(0), _row(5), _row(10, **b), _row(15)], name="c7")
    assert await _collapse(db, eid) == (1, 1)
    assert [r.id for r in await _rows(db, eid)] == [ids[0], ids[2], ids[3]]


async def test_8_books_and_events_are_their_own_series(db):
    """Identical values in two books never merge across books, and a pass on one
    event never touches another event's identical rows."""
    eid, base, ids = await _seed(
        db,
        [_row(0, book="draftkings"), _row(1, book="fanduel"), _row(2, book="draftkings")],
        name="c8",
    )
    other, _, other_ids = await _seed(db, [_row(0), _row(1)], name="c8b")
    assert await _collapse(db, eid) == (1, 1)
    kept = await _rows(db, eid)
    assert sorted(r.id for r in kept) == sorted([ids[0], ids[1]])
    assert {r.bookmaker for r in kept} == {"draftkings", "fanduel"}
    assert [r.id for r in await _rows(db, other)] == other_ids


async def test_9_rows_after_the_cutoff_are_untouched(db):
    """Only aged rows are collapsed; a fresh identical row keeps its own row."""
    eid, _, aged = await _seed(db, [_row(0), _row(5)], name="c9")
    _, _, fresh = await _seed(
        db, [_row(0), _row(5)], name="c9", event_id=eid, age=timedelta(hours=1)
    )
    assert await _collapse(db, eid) == (1, 1)
    assert sorted(r.id for r in await _rows(db, eid)) == sorted([aged[0], *fresh])
