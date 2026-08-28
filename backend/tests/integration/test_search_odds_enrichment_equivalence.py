"""LAT-P030 / #1494 — the odds-enrichment rewrite returns the SAME ROWS, on real Postgres.

Why this file exists
--------------------
``search_events`` used to read the full snapshot history of every event on the results
page in order to keep one row per bookmaker. Measured against production 2026-08-10 on
the 25 events a ``red sox`` search actually returns: **78,800 rows read to return 299,
6,724ms** — and ``?debug_timing=1`` put ``event_odds_query`` at 84-95% of every slow
team query. One measured Red Sox event carries 13,522 snapshots across 19 bookmakers.

The replacement enumerates bookmakers with a recursive loose index scan and fetches
exactly one row per ``(event, bookmaker)``: **947 rows, 185ms**, a 36x cut on the
dominant stage.

That trade is only safe if the OUTPUT is identical, and identity is not something a
source-shape assertion can establish — ``test_search_latency_contract.py`` pins the
shape, and a shape can be right while the rows are wrong. So this file EXECUTES both
statements — the live helper and the shape it replaced — against a real database and
diffs the rows.

Real Postgres is mandatory, not preferred
-----------------------------------------
``LATERAL``, ``DISTINCT ON`` and ``WITH RECURSIVE`` are Postgres constructs and the
whole subject is the planner's behaviour, so there is no SQLite fallback worth having.
Opt-in on ``SEARCH_TEST_DATABASE_URL``, following
``tests/integration/test_search_recall_contract.py`` and the
``search-recall`` CI job that supplies one. **This file is added to that job's pytest
invocation** — a real-Postgres test that no job runs is a test that never runs, and
pytest exits 0 when everything skips.

SCOPE LIMIT — read before quoting a green run
---------------------------------------------
This proves EQUIVALENCE on seeded data, not the speedup. The seed is a few hundred rows,
so both shapes are fast here and a wall-clock assertion would prove nothing (and would
be flaky on CI hardware besides). The 36x is a production measurement, recorded in the
call-site comment and the queue report; this gate's job is to ensure the fast shape
never starts returning different rows than the slow one it replaced.
"""

import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import and_, func, select, true
from sqlalchemy.orm import aliased

from app.models.models import Event, OddsSnapshot, Sport
from app.routes.events import latest_odds_per_bookmaker_query

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres odds-enrichment "
            "equivalence gate (the search-recall CI job provides one)"
        ),
    ),
]

# A fixed instant. Never seed relative to `datetime.now()` across a date boundary —
# gotcha #44 red-blocked two deploys exactly that way.
_T0 = datetime(2026, 3, 2, 12, 0, tzinfo=timezone.utc)

# Seed constants, referenced as LITERALS in the assertions below. LAT-P026 shipped a
# guard that read the same constant it checked and therefore pinned nothing.
_DEEP_HISTORY_STEPS = 40
_DEEP_BOOKMAKERS = ("zenith", "acme", "meridian")  # alphabetical != insertion order


def _replaced_shape_query(event_ids):
    """The shape LAT-P030 removed: a per-event LATERAL ``DISTINCT ON (bookmaker)``.

    Kept HERE, in the test, rather than in the route: this is the oracle the new query
    is diffed against, and it must not be reachable from production code.
    """
    latest = (
        select(OddsSnapshot)
        .where(OddsSnapshot.event_id == Event.id)
        .distinct(OddsSnapshot.bookmaker)
        .order_by(
            OddsSnapshot.bookmaker,
            OddsSnapshot.captured_at.desc(),
            OddsSnapshot.id.desc(),
        )
        .lateral("legacy_latest_snap")
    )
    snap = aliased(OddsSnapshot, latest)
    return (
        select(snap)
        .select_from(Event)
        .join(latest, true())
        .where(Event.id.in_(event_ids))
    )


def _key(rows):
    """Order-independent comparison across every column that reaches the response."""
    return sorted(
        (
            s.id,
            s.event_id,
            s.bookmaker,
            s.captured_at,
            s.home_moneyline,
            s.away_moneyline,
            s.home_spread,
            s.over_under,
            s.home_win_probability,
        )
        for s in rows
    )


async def _seed(session):
    """Four events chosen for the cases where the two shapes could disagree."""
    sport = Sport(key="baseball_mlb_p030", name="LAT-P030 MLB", active=True)
    session.add(sport)
    await session.flush()

    events = []
    for i in range(4):
        ev = Event(
            sport_id=sport.id,
            home_team_name=f"P030 Home {i}",
            away_team_name=f"P030 Away {i}",
            commence_time=_T0 + timedelta(days=i),
            status="scheduled",
        )
        session.add(ev)
        events.append(ev)
    await session.flush()

    # Event 0 — deep history over several bookmakers, the case that made the old shape
    # slow. Alphabetical order deliberately differs from insertion order, so a walk
    # that follows insertion rather than the index ordering is caught.
    for depth in range(_DEEP_HISTORY_STEPS):
        for bk in _DEEP_BOOKMAKERS:
            session.add(
                OddsSnapshot(
                    event_id=events[0].id,
                    bookmaker=bk,
                    captured_at=_T0 + timedelta(minutes=depth),
                    home_moneyline=-110 - depth,
                    away_moneyline=100 + depth,
                )
            )

    # Event 1 — exactly one bookmaker: the walk must terminate after a single step.
    for depth in range(5):
        session.add(
            OddsSnapshot(
                event_id=events[1].id,
                bookmaker="solo",
                captured_at=_T0 + timedelta(minutes=depth),
                home_moneyline=-200 + depth,
            )
        )

    # Event 2 — two rows TIED on captured_at. Only the `id DESC` tiebreak decides, and
    # both shapes must decide it the same way.
    for _ in range(2):
        session.add(
            OddsSnapshot(
                event_id=events[2].id,
                bookmaker="tied",
                captured_at=_T0,
                home_moneyline=-150,
            )
        )

    # Event 3 — no snapshots at all: the walk's first min() is NULL immediately, so the
    # event must contribute ZERO rows, not a NULL-bookmaker terminator row.

    await session.commit()
    return [e.id for e in events]


@pytest.fixture
async def seeded_db():
    """Real Postgres, real schema, real rows.

    Function-scoped deliberately: ``pytest.ini`` leaves
    ``asyncio_default_fixture_loop_scope`` unset, so a module-scoped async fixture would
    outlive the function-scoped event loop that created its engine.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        event_ids = await _seed(session)

    async with maker() as session:
        yield session, event_ids

    await engine.dispose()


async def test_rewrite_returns_the_same_rows_as_the_shape_it_replaced(seeded_db):
    session, event_ids = seeded_db

    new_rows = (
        await session.execute(latest_odds_per_bookmaker_query(event_ids))
    ).scalars().all()
    old_rows = (await session.execute(_replaced_shape_query(event_ids))).scalars().all()

    assert _key(new_rows) == _key(old_rows), (
        "the loose-index-scan rewrite returned different rows than the DISTINCT ON "
        "shape it replaced — a correctness regression, not a latency change"
    )
    # Pin the cardinality as a literal too: a query returning nothing at all would
    # otherwise "agree" with an oracle that also returned nothing.
    assert len(new_rows) == 5, (
        f"expected 3 bookmakers + 1 + 1 = 5 latest snapshots, got {len(new_rows)}"
    )


async def test_the_walk_returns_one_row_per_bookmaker_not_per_snapshot(seeded_db):
    """The reason the rewrite exists: event 0 carries 120 snapshots over 3 bookmakers
    and the answer is 3 rows. Deep history must not change the result."""
    session, event_ids = seeded_db

    rows = (
        await session.execute(latest_odds_per_bookmaker_query([event_ids[0]]))
    ).scalars().all()

    assert sorted(r.bookmaker for r in rows) == ["acme", "meridian", "zenith"]
    # the LATEST per bookmaker is the last depth seeded — asserted as a literal
    assert {r.home_moneyline for r in rows} == {-149}
    assert all(r.captured_at == _T0 + timedelta(minutes=39) for r in rows)


async def test_an_event_with_no_snapshots_contributes_no_terminator_row(seeded_db):
    """The recursive walk emits a NULL-bookmaker row per event when its bookmakers run
    out. If that terminator escaped the final filter it would arrive as a snapshot with
    no bookmaker and poison the aggregation downstream."""
    session, event_ids = seeded_db

    rows = (
        await session.execute(latest_odds_per_bookmaker_query([event_ids[3]]))
    ).scalars().all()

    assert rows == [], "an event with no odds must contribute zero rows"


async def test_the_captured_at_tie_is_broken_identically_by_both_shapes(seeded_db):
    """``row_number()`` left this arbitrary; both surviving shapes must agree."""
    session, event_ids = seeded_db
    tied_event = event_ids[2]

    new_rows = (
        await session.execute(latest_odds_per_bookmaker_query([tied_event]))
    ).scalars().all()
    old_rows = (await session.execute(_replaced_shape_query([tied_event]))).scalars().all()

    assert len(new_rows) == 1 and len(old_rows) == 1
    assert new_rows[0].id == old_rows[0].id

    all_tied = (
        await session.execute(
            select(OddsSnapshot.id).where(OddsSnapshot.event_id == tied_event)
        )
    ).scalars().all()
    assert new_rows[0].id == max(all_tied), "the tie must resolve to the HIGHER id"


async def test_the_walk_covers_every_bookmaker_present(seeded_db):
    """A skip-scan that advances wrongly drops a bookmaker's odds silently — the
    response still renders, just with a book missing. Assert full coverage against the
    distinct set actually in the table."""
    session, event_ids = seeded_db

    present = set(
        (
            await session.execute(
                select(OddsSnapshot.bookmaker).where(
                    OddsSnapshot.event_id.in_(event_ids)
                ).distinct()
            )
        ).scalars().all()
    )
    returned = {
        r.bookmaker
        for r in (
            await session.execute(latest_odds_per_bookmaker_query(event_ids))
        ).scalars().all()
    }

    assert returned == present, f"bookmakers dropped by the walk: {present - returned}"


# ---------------------------------------------------------------------------
# LAT-P107 / #1605 — the OTHER two call sites, against the shape THEY replaced
# ---------------------------------------------------------------------------
#
# The oracle above (`_replaced_shape_query`) is the DISTINCT ON form, which is what
# LAT-P030 replaced on the search route. `GET /api/events` and `GET /api/events/{id}`
# never had that intermediate form — they still carried the ORIGINAL `row_number()`
# window, and the two windows are not even the same window: the page one partitions
# by `(event_id, bookmaker)` and joins back by id, the detail one partitions by
# `bookmaker` alone under a `WHERE event_id = :id` and projects ids for a second
# round trip.
#
# So diffing against the DISTINCT ON oracle would prove the new query agrees with a
# shape those routes never ran. Both originals are reconstructed here instead.


def _row_number_page_shape_query(event_ids):
    """`list_events` as it stood before LAT-P107.

    `id DESC` is added to the ordering, which production did NOT have. That is
    deliberate and it is the ONE accepted behavioural difference of the rewrite,
    already ratified: `row_number()` left the choice among equal `captured_at`
    arbitrary, so an oracle without the tiebreak would make a coin flip look like a
    disagreement and this test would be asking a question that has no answer. The
    tie is asserted on its own terms in
    `test_both_replaced_windows_agree_on_cardinality_even_where_the_tie_was_arbitrary`.
    """
    ranked = (
        select(
            OddsSnapshot.id,
            OddsSnapshot.event_id,
            func.row_number()
            .over(
                partition_by=[OddsSnapshot.event_id, OddsSnapshot.bookmaker],
                order_by=[OddsSnapshot.captured_at.desc(), OddsSnapshot.id.desc()],
            )
            .label("rn"),
        )
        .where(OddsSnapshot.event_id.in_(event_ids))
        .subquery()
    )
    return select(OddsSnapshot).join(
        ranked,
        and_(OddsSnapshot.id == ranked.c.id, ranked.c.rn == 1),
    )


def _row_number_detail_shape_query(event_id):
    """`get_event` as it stood before LAT-P107: partition by bookmaker alone, one
    event, ids projected for a second fetch. Same `id DESC` note as above."""
    ranked = (
        select(
            OddsSnapshot.id,
            func.row_number()
            .over(
                partition_by=OddsSnapshot.bookmaker,
                order_by=[OddsSnapshot.captured_at.desc(), OddsSnapshot.id.desc()],
            )
            .label("rn"),
        )
        .where(OddsSnapshot.event_id == event_id)
        .subquery()
    )
    return select(OddsSnapshot).join(
        ranked,
        and_(OddsSnapshot.id == ranked.c.id, ranked.c.rn == 1),
    )


async def test_the_page_rewrite_matches_the_window_shape_list_events_replaced(seeded_db):
    """`GET /api/events`. Set identity across all four seeded events at once."""
    session, event_ids = seeded_db

    new_rows = (
        await session.execute(latest_odds_per_bookmaker_query(event_ids))
    ).scalars().all()
    old_rows = (
        await session.execute(_row_number_page_shape_query(event_ids))
    ).scalars().all()

    assert _key(new_rows) == _key(old_rows), (
        "list_events' rewrite returned different rows than the row_number() window "
        "it replaced — a correctness regression, not a latency change"
    )
    assert len(new_rows) == 5, (
        f"expected 3 bookmakers + 1 + 1 = 5 latest snapshots, got {len(new_rows)}"
    )


async def test_the_detail_rewrite_matches_the_window_shape_get_event_replaced(seeded_db):
    """`GET /api/events/{event_id}`. Driven on the DEEP event — 120 snapshots over 3
    bookmakers — because a single-event call is the case where the old window read
    the most and the new walk reads the least, and it is the one a reader waits on."""
    session, event_ids = seeded_db
    deep = event_ids[0]

    new_rows = (
        await session.execute(latest_odds_per_bookmaker_query([deep]))
    ).scalars().all()
    old_rows = (
        await session.execute(_row_number_detail_shape_query(deep))
    ).scalars().all()

    assert _key(new_rows) == _key(old_rows)
    assert len(new_rows) == len(_DEEP_BOOKMAKERS) == 3, (
        f"one row per bookmaker, not per snapshot: got {len(new_rows)} from "
        f"{_DEEP_HISTORY_STEPS * len(_DEEP_BOOKMAKERS)} seeded rows"
    )


async def test_the_detail_rewrite_returns_nothing_for_an_event_with_no_snapshots(
    seeded_db,
):
    """Event 3 has no snapshots. The old detail path produced an empty id list and
    skipped its second query entirely; the walk's first `min()` is NULL immediately.
    Both must yield zero rows — NOT one NULL-bookmaker terminator row, which would
    reach `_format_event` as a snapshot that does not exist."""
    session, event_ids = seeded_db

    rows = (
        await session.execute(latest_odds_per_bookmaker_query([event_ids[3]]))
    ).scalars().all()

    assert rows == []


async def test_both_replaced_windows_agree_on_cardinality_even_where_the_tie_was_arbitrary(
    seeded_db,
):
    """Event 2 holds two rows tied on `captured_at`. Production's `row_number()` had
    no tiebreak, so WHICH row it returned was arbitrary — that is precisely the
    behaviour the rewrite makes deterministic, and it is why the oracles above are
    given an `id DESC` they never had.

    What must hold regardless of the coin flip is that exactly ONE row comes back for
    that bookmaker. A rewrite that returned two would double a book's odds in the
    aggregate; one that returned zero would drop it. Asserted against the untiebroken
    window, which is what production actually ran."""
    session, event_ids = seeded_db
    tied_event = event_ids[2]

    untiebroken = (
        select(
            OddsSnapshot.id,
            func.row_number()
            .over(
                partition_by=OddsSnapshot.bookmaker,
                order_by=OddsSnapshot.captured_at.desc(),
            )
            .label("rn"),
        )
        .where(OddsSnapshot.event_id == tied_event)
        .subquery()
    )
    old_n = len(
        (
            await session.execute(select(untiebroken.c.id).where(untiebroken.c.rn == 1))
        ).scalars().all()
    )
    new_rows = (
        await session.execute(latest_odds_per_bookmaker_query([tied_event]))
    ).scalars().all()

    assert old_n == len(new_rows) == 1
