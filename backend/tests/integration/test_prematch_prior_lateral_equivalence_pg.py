"""LAT-P222 — the pre-match read returns the SAME ROWS without the join, on real Postgres.

Why this file exists
--------------------
The ux/1036 read asks: *for each settled card, what did each prediction market
say at or before kickoff?* Its first shape got the kickoff by joining
``win_prob_snapshots`` back to ``events``. Postgres cannot evaluate a bound it
has to fetch, so it drove from the snapshot side and probed ``events_pkey``
**24,528 times to return 53 rows** — 747,190 of 753,087 buffer hits — which
measured **86.0% of the entire `events` stage** of a cold Discover build
(935.9 ms of 1,088.2 ms, production dyno, 2026-09-04).

The replacement takes the cutoffs from the caller, which is already holding
them, and reads one table: ``unnest(:ids, :cutoffs)`` cross-joined laterally to
a per-event ``DISTINCT ON (source)``. Measured on the same id list, same probe,
four reps each: **98.8 ms / 19,747 buffers** against 878.8–1,278.5 ms.

That trade is only safe if the OUTPUT is identical, and identity is not
something a source assertion can establish — the sibling
``tests/test_prematch_prior_binds.py`` pins the shape and the binds, and a shape
can be right while the rows are wrong. So this file EXECUTES both statements
against a real database over rows built to straddle kickoff, and diffs them.

What could go wrong here that nothing else can see
--------------------------------------------------
* **The kickoff bound could quietly stop applying.** The same table holds the
  in-play and post-settlement readings, and a settled market prices the winner
  at ~100%. Drop the bound and every finished card renders its own result back
  as a forecast — a wrong number, printed confidently, on the surface the whole
  ship is about. ``test_the_fixture_can_tell_a_dropped_bound_apart`` proves this
  seed is actually able to catch that, rather than assuming it.
* **The two arrays are positional.** ``unnest(a, b)`` pairs by index, so a
  misalignment attributes one game's kickoff to another game's prices. It is a
  wrong answer no latency measurement notices;
  ``test_a_misaligned_cutoff_array_changes_the_answer`` shows the seed is
  sensitive to it.
* **``DISTINCT ON`` moved.** It was ``(event_id, source)`` over the whole result
  and is now ``(source)`` inside a per-event lateral. Those are the same
  selection only because the lateral is already scoped to one event.

Real Postgres is mandatory, not preferred: ``unnest`` of two arrays, ``CROSS
JOIN LATERAL`` and ``DISTINCT ON`` are Postgres constructs with no SQLite
equivalent worth having, and the subject is what the server returns. Opt-in on
``SEARCH_TEST_DATABASE_URL``, following its neighbours in this directory. **This
file is named by a step in the ``search-recall`` CI job** — a real-Postgres test
no job runs is a test that never runs, and pytest exits 0 when everything skips.

SCOPE LIMIT — read before quoting a green run
---------------------------------------------
This proves EQUIVALENCE on a few dozen seeded rows, not the speedup. Both shapes
are fast over a seed this size and a wall-clock assertion here would prove
nothing and flake on CI hardware besides. The 9x is a production measurement,
recorded in the call-site comment and in the queue report.

One case this gate CANNOT hold: a settled event with no ``commence_time``.
``events.commence_time`` is NOT NULL, so no database will store that row — the
old shape excluded such an event through three-valued logic and the new one
excludes it on purpose, and that difference is pinned in the unit sibling.
"""

import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.models import Event, Sport, WinProbSnapshot
from app.utils.prematch_reading import (
    PREDICTION_MARKET_SOURCES,
    PREMATCH_PRIOR_SQL,
    prematch_prior_binds,
)

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres pre-match "
            "prior equivalence gate (the search-recall CI job provides one)"
        ),
    ),
]

# A fixed instant. gotcha #44 — offset from an anchor, never branch on the clock.
_T0 = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)

#: The shape LAT-P222 removed. Kept HERE, in the test, as the oracle the live
#: statement is diffed against — and deliberately unreachable from production
#: code, so nothing can drift back onto it.
_REPLACED_JOIN_SQL = """
    SELECT DISTINCT ON (s.event_id, s.source)
           s.event_id, s.source,
           s.home_win_probability, s.away_win_probability
    FROM win_prob_snapshots s
    JOIN events e ON e.id = s.event_id
    WHERE s.event_id = ANY(:ids)
      AND s.source = ANY(:sources)
      AND s.home_win_probability IS NOT NULL
      AND s.captured_at <= e.commence_time
    ORDER BY s.event_id, s.source, s.captured_at DESC
"""

#: The live statement with its kickoff bound deleted — never executed as an
#: oracle, only to show the seed can tell the difference.
_UNBOUNDED_SQL = PREMATCH_PRIOR_SQL.replace("AND s.captured_at <= t.cutoff", "")


def _key(rows):
    """Order-independent comparison over every column the caller consumes.

    Value tuples, not a row count: a rewrite that returned FEWER rows would
    otherwise pass a cardinality check the moment the oracle was also empty, and
    `Numeric(5,4)` arrives as `Decimal`, so the values are normalised rather
    than compared across two float paths.
    """
    return sorted(
        (
            int(r[0]),
            str(r[1]),
            None if r[2] is None else Decimal(r[2]).quantize(Decimal("0.0001")),
            None if r[3] is None else Decimal(r[3]).quantize(Decimal("0.0001")),
        )
        for r in rows
    )


class _Candidate:
    """What the statement's caller passes: whatever `_score_events` has hydrated.

    A plain holder rather than an ORM instance — `prematch_prior_binds` reads
    `id`, `status` and `commence_time` and nothing else, and the seeded rows'
    real values are what get put in it.
    """

    def __init__(self, event):
        self.id = event.id
        self.status = event.status
        self.commence_time = event.commence_time


async def _seed(session):
    """Four events, each carrying a case where the two shapes could disagree."""
    sport = Sport(key="baseball_mlb_p222", name="LAT-P222 MLB", active=True)
    session.add(sport)
    await session.flush()

    events = []
    for i, status in enumerate(["completed", "closed", "completed", "scheduled"]):
        ev = Event(
            sport_id=sport.id,
            home_team_name=f"P222 Home {i}",
            away_team_name=f"P222 Away {i}",
            commence_time=_T0 + timedelta(days=i),
            status=status,
        )
        session.add(ev)
        events.append(ev)
    await session.flush()

    def snap(event, source, minutes, home, away=None):
        session.add(
            WinProbSnapshot(
                event_id=event.id,
                source=source,
                captured_at=event.commence_time + timedelta(minutes=minutes),
                home_win_probability=home,
                away_win_probability=away,
            )
        )

    # E0 — the ordinary settled card, and the whole point of the bound: two
    # sources, each with readings on BOTH sides of kickoff. The answer is the
    # last one at or before it, per source. The post-kickoff rows climb towards
    # the settled 0.99 that must never reach a card as a "prior".
    snap(events[0], "kalshi", -180, 0.5500, 0.4500)
    snap(events[0], "kalshi", -5, 0.6100, 0.3900)  # <- kalshi's answer
    snap(events[0], "kalshi", 30, 0.9200, 0.0800)
    snap(events[0], "kalshi", 200, 0.9900, 0.0100)
    snap(events[0], "polymarket", -240, 0.4800, 0.5200)
    snap(events[0], "polymarket", 0, 0.5900, 0.4100)  # <- exactly AT kickoff, included
    snap(events[0], "polymarket", 90, 0.1500, 0.8500)

    # E1 — settled, but every reading arrived after the first ball. There is no
    # prior, so the card must get NOTHING rather than the in-play number. This
    # is the row that separates a working bound from a missing one.
    snap(events[1], "kalshi", 1, 0.7700, 0.2300)
    snap(events[1], "polymarket", 45, 0.8800, 0.1200)

    # E2 — two filters that are easy to lose in a rewrite:
    #   * the NEWEST pre-kickoff kalshi row has a NULL home probability, so the
    #     answer is the older one, not "no reading";
    #   * `espn` writes to this same table constantly and is NOT on the ladder.
    snap(events[2], "kalshi", -300, 0.4200, 0.5800)  # <- kalshi's answer
    snap(events[2], "kalshi", -10, None, 0.3000)
    snap(events[2], "espn", -20, 0.6600, 0.3400)

    # E3 — scheduled. Its snapshots are pre-kickoff and would match every
    # predicate; it must never be ASKED about, because its card prints no
    # pre-match reading. The filter lives in the caller, so this is the only
    # place the gate can observe it.
    snap(events[3], "kalshi", -60, 0.7000, 0.3000)

    await session.commit()
    return events


@pytest.fixture
async def seeded_db():
    """Real Postgres, real schema, real rows.

    Function-scoped deliberately: `pytest.ini` leaves
    `asyncio_default_fixture_loop_scope` unset, so a module-scoped async fixture
    would outlive the function-scoped event loop that created its engine.
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
        events = await _seed(session)

    candidates = [_Candidate(e) for e in events]
    async with maker() as session:
        yield session, candidates

    await engine.dispose()


async def _live(session, candidates):
    binds = prematch_prior_binds(candidates)
    assert binds is not None, "the seed contains settled events; binds must be built"
    return (await session.execute(text(PREMATCH_PRIOR_SQL), binds)).all()


async def _oracle(session, candidates):
    binds = prematch_prior_binds(candidates)
    return (
        await session.execute(
            text(_REPLACED_JOIN_SQL),
            {"ids": binds["ids"], "sources": binds["sources"]},
        )
    ).all()


async def test_the_rewrite_returns_the_same_rows_as_the_join_it_replaced(seeded_db):
    session, candidates = seeded_db

    assert _key(await _live(session, candidates)) == _key(
        await _oracle(session, candidates)
    ), (
        "the caller-supplied-cutoff rewrite returned different rows than the "
        "`JOIN events` shape it replaced — a correctness regression, not a "
        "latency change"
    )


async def test_each_source_gets_its_last_reading_at_or_before_kickoff(seeded_db):
    """The cardinality and the VALUES as literals.

    Two agreeing statements that both return nothing also agree, so the answer
    is pinned independently of the oracle.
    """
    session, candidates = seeded_db
    rows = await _live(session, candidates)

    assert _key(rows) == [
        (
            candidates[0].id,
            "kalshi",
            Decimal("0.6100"),
            Decimal("0.3900"),
        ),
        (
            candidates[0].id,
            "polymarket",
            Decimal("0.5900"),
            Decimal("0.4100"),
        ),
        (
            candidates[2].id,
            "kalshi",
            Decimal("0.4200"),
            Decimal("0.5800"),
        ),
    ]


async def test_a_settled_card_with_only_in_play_readings_gets_nothing(seeded_db):
    """E1's earliest reading is one minute after the first ball. A card that
    printed it would be showing an in-play number under the word "before"."""
    session, candidates = seeded_db
    rows = await _live(session, candidates)

    assert not [r for r in rows if r[0] == candidates[1].id]


async def test_the_scheduled_card_is_never_asked_about(seeded_db):
    """It holds a pre-kickoff reading that satisfies every SQL predicate; only
    the caller's settled filter keeps it out."""
    session, candidates = seeded_db
    binds = prematch_prior_binds(candidates)

    assert candidates[3].id not in binds["ids"]
    assert not [r for r in await _live(session, candidates) if r[0] == candidates[3].id]


async def test_a_source_off_the_ladder_is_not_returned(seeded_db):
    """`espn` writes to this table on every live poll and is not a venue the
    card may quote as a market's opinion."""
    session, candidates = seeded_db
    rows = await _live(session, candidates)

    assert {r[1] for r in rows} <= set(PREDICTION_MARKET_SOURCES)
    assert "espn" not in {r[1] for r in rows}


async def test_the_fixture_can_tell_a_dropped_bound_apart(seeded_db):
    """The gate's own sensitivity, executed rather than assumed.

    A seed on which the bounded and unbounded statements agree would let the
    equivalence test above pass with the bound deleted. This runs the unbounded
    variant and asserts it returns the settled ~100% prices the live one refuses
    — so a green above is a statement about the bound, not about the seed.
    """
    session, candidates = seeded_db
    binds = prematch_prior_binds(candidates)
    unbounded = (await session.execute(text(_UNBOUNDED_SQL), binds)).all()

    live = _key(await _live(session, candidates))
    assert _key(unbounded) != live

    settled_price = [
        r for r in unbounded if r[0] == candidates[0].id and r[1] == "kalshi"
    ]
    assert len(settled_price) == 1
    assert Decimal(settled_price[0][2]) == Decimal(
        "0.9900"
    ), "without the bound the card would print the RESULT as the forecast"
    assert [
        r for r in unbounded if r[0] == candidates[1].id
    ], "E1 exists so that a dropped bound also invents a prior where there is none"


async def test_a_misaligned_cutoff_array_changes_the_answer(seeded_db):
    """`unnest(a, b)` pairs by index — so prove the seed is sensitive to it.

    This is the hazard `settled_prematch_cutoffs` exists to make unreachable:
    the response stays well-formed and fast while the numbers become another
    game's. If rotating the cutoffs left the rows unchanged, nothing in this
    file would be guarding the pairing.
    """
    session, candidates = seeded_db
    binds = prematch_prior_binds(candidates)
    rotated = dict(binds, cutoffs=binds["cutoffs"][1:] + binds["cutoffs"][:1])

    assert len(rotated["cutoffs"]) == len(rotated["ids"]) >= 3
    assert _key(
        (await session.execute(text(PREMATCH_PRIOR_SQL), rotated)).all()
    ) != _key(await _live(session, candidates))
