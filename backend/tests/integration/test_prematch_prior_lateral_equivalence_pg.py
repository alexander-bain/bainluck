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
    PREMATCH_PRIOR_TOP1_SQL,
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


async def test_the_cached_read_returns_the_statements_rows_cold_warm_and_mixed(
    seeded_db, monkeypatch
):
    """#10090 — the per-game cache is the statement's output, on a real server.

    Cold (nothing held), warm (everything held, no read) and mixed (one game
    held, the others re-bound beside their own cutoffs) must all equal the
    statement run directly — real `Row`s, real `Decimal`s, real positional
    pairing in the miss read.
    """
    import app.utils.prematch_reading as pr

    monkeypatch.delenv("PREMATCH_READING_CACHE", raising=False)
    # gotcha #44: a fixed clock every seeded kickoff is behind.
    monkeypatch.setattr(pr, "_utcnow", lambda: _T0 + timedelta(days=30))
    pr._reset_prematch_cache_for_tests()
    session, candidates = seeded_db
    binds = prematch_prior_binds(candidates)
    direct = _key(await _live(session, candidates))

    reads = []
    real_execute = session.execute

    async def counting_execute(stmt, params=None, *a, **k):
        reads.append(params)
        return await real_execute(stmt, params, *a, **k)

    monkeypatch.setattr(session, "execute", counting_execute)

    def cached_key(rows):
        return _key(
            [
                (r.event_id, r.source, r.home_win_probability, r.away_win_probability)
                for r in rows
            ]
        )

    # cold
    assert cached_key(await pr.fetch_prematch_prior_rows(session, binds)) == direct
    assert len(reads) == 1 and len(pr._prematch_cache) == len(binds["ids"])
    # warm: no read at all
    assert cached_key(await pr.fetch_prematch_prior_rows(session, binds)) == direct
    assert len(reads) == 1

    # mixed: one game held, the rest read beside their own kickoffs
    pr._reset_prematch_cache_for_tests()
    await pr.fetch_prematch_prior_rows(session, prematch_prior_binds(candidates[1:2]))
    assert cached_key(await pr.fetch_prematch_prior_rows(session, binds)) == direct
    miss = reads[-1]
    pairs = dict(zip(binds["ids"], binds["cutoffs"]))
    assert candidates[1].id not in miss["ids"]
    assert miss["cutoffs"] == [pairs[i] for i in miss["ids"]]


# ── #10090: the per-source top-1 returns the walk's rows, in the walk's order ──
#
# `PREMATCH_PRIOR_TOP1_SQL` replaces the lateral `DISTINCT ON (s.source)` walk
# with one backward index seek per (game, source). Each case below runs BOTH
# statements directly and diffs the raw rows IN ORDER, then runs the callers
# (`fetch_prematch_prior_rows`, `read_prematch_priors`,
# `settled_prematch_odds_by_event`) with `PREMATCH_PRIOR_TOP1` on and off, cold,
# warm and mixed, and diffs what they hand back. The one place the two may
# differ — a timestamp tie — has its own fixture: the walk keeps either row, the
# top-1 keeps the later-inserted one.

_TOP1_UNBOUNDED_SQL = PREMATCH_PRIOR_TOP1_SQL.replace(
    "AND s.captured_at <= t.cutoff", ""
)


def _ordered(rows):
    """Every column, in the order the server returned them."""
    return [
        (
            int(r[0]),
            str(r[1]),
            None if r[2] is None else Decimal(r[2]),
            None if r[3] is None else Decimal(r[3]),
            None if r[4] is None else Decimal(r[4]),
        )
        for r in rows
    ]


def _bind_matrix(candidates):
    """Every bind shape the truth gate names, built from the seeded rows."""
    e0, e1, e2 = candidates[0], candidates[1], candidates[2]
    c0, c1, c2 = e0.commence_time, e1.commence_time, e2.commence_time
    ladder = list(PREDICTION_MARKET_SOURCES)
    return {
        "base": prematch_prior_binds(candidates),
        "repeated_same_cutoff": {
            "ids": [e0.id, e2.id, e0.id],
            "cutoffs": [c0, c2, c0],
            "sources": ladder,
        },
        "repeated_different_cutoffs": {
            "ids": [e0.id, e0.id, e2.id],
            "cutoffs": [c0, c0 + timedelta(minutes=60), c2],
            "sources": ladder,
        },
        "duplicate_and_null_sources": {
            "ids": [e0.id, e2.id],
            "cutoffs": [c0, c2],
            "sources": ["polymarket", "kalshi", None, "kalshi", "polymarket"],
        },
        "only_null_sources": {
            "ids": [e0.id],
            "cutoffs": [c0],
            "sources": [None],
        },
        "no_sources": {"ids": [e0.id], "cutoffs": [c0], "sources": []},
        "off_ladder_source": {
            "ids": [e0.id, e2.id],
            "cutoffs": [c0, c2],
            "sources": ["espn", "kalshi"],
        },
        "ids_longer_null_padded": {
            "ids": [e0.id, e1.id, e2.id],
            "cutoffs": [c0],
            "sources": ladder,
        },
        "cutoffs_longer_null_padded": {
            "ids": [e2.id],
            "cutoffs": [c2, c0, c1],
            "sources": ladder,
        },
        "future_cutoff": {
            "ids": [e0.id, e1.id],
            "cutoffs": [_T0 + timedelta(days=3650), _T0 + timedelta(days=3650)],
            "sources": ladder,
        },
        # Exactly on a post-kickoff row's timestamp: inclusive means kalshi's
        # +30 min 0.92 is the answer, and polymarket's +90 is not.
        "inclusive_on_a_row": {
            "ids": [e0.id],
            "cutoffs": [c0 + timedelta(minutes=30)],
            "sources": ladder,
        },
        "unknown_event": {
            "ids": [987654321, e0.id],
            "cutoffs": [c0, c0],
            "sources": ladder,
        },
    }


async def _run(session, sql, binds):
    return _ordered((await session.execute(text(sql), binds)).all())


@pytest.mark.parametrize(
    "case",
    [
        "base",
        "repeated_same_cutoff",
        "repeated_different_cutoffs",
        "duplicate_and_null_sources",
        "only_null_sources",
        "no_sources",
        "off_ladder_source",
        "ids_longer_null_padded",
        "cutoffs_longer_null_padded",
        "future_cutoff",
        "inclusive_on_a_row",
        "unknown_event",
    ],
)
async def test_the_top1_returns_the_walks_rows_in_the_walks_order(seeded_db, case):
    session, candidates = seeded_db
    binds = _bind_matrix(candidates)[case]

    walk = await _run(session, PREMATCH_PRIOR_SQL, binds)
    top1 = await _run(session, PREMATCH_PRIOR_TOP1_SQL, binds)

    assert top1 == walk, f"{case}: top-1 {top1} != walk {walk}"


async def test_the_matrix_answers_are_pinned_as_literals(seeded_db):
    """Two statements that agree on nothing-returned also agree. The cases that
    carry a semantic are pinned independently of either statement."""
    session, candidates = seeded_db
    e0, e1, e2 = (c.id for c in candidates[:3])
    m = _bind_matrix(candidates)
    D = Decimal

    async def top1(case):
        return [r[:3] for r in await _run(session, PREMATCH_PRIOR_TOP1_SQL, m[case])]

    # NULL home newer than the last real one: the older real reading, not nothing.
    assert (e2, "kalshi", D("0.4200")) in await top1("base")
    # duplicate sources collapse; a NULL source matches nothing; order is source.
    assert await top1("duplicate_and_null_sources") == [
        (e0, "kalshi", D("0.6100")),
        (e0, "polymarket", D("0.5900")),
        (e2, "kalshi", D("0.4200")),
    ]
    assert await top1("only_null_sources") == []
    assert await top1("no_sources") == []
    assert await top1("off_ladder_source") == [
        (e0, "kalshi", D("0.6100")),
        (e2, "espn", D("0.6600")),
        (e2, "kalshi", D("0.4200")),
    ]
    # repeated id, two cutoffs: each position gets its own cutoff's answer.
    assert await top1("repeated_different_cutoffs") == [
        (e0, "kalshi", D("0.6100")),
        (e0, "polymarket", D("0.5900")),
        (e0, "kalshi", D("0.9200")),
        (e0, "polymarket", D("0.5900")),
        (e2, "kalshi", D("0.4200")),
    ]
    # NULL padding: a NULL id or a NULL cutoff yields no rows for that position.
    assert await top1("ids_longer_null_padded") == [
        (e0, "kalshi", D("0.6100")),
        (e0, "polymarket", D("0.5900")),
    ]
    assert await top1("cutoffs_longer_null_padded") == [(e2, "kalshi", D("0.4200"))]
    # a cutoff past every row reads the latest; inclusive takes the row ON it.
    assert await top1("future_cutoff") == [
        (e0, "kalshi", D("0.9900")),
        (e0, "polymarket", D("0.1500")),
        (e1, "kalshi", D("0.7700")),
        (e1, "polymarket", D("0.8800")),
    ]
    assert await top1("inclusive_on_a_row") == [
        (e0, "kalshi", D("0.9200")),
        (e0, "polymarket", D("0.5900")),
    ]
    assert await top1("unknown_event") == [
        (e0, "kalshi", D("0.6100")),
        (e0, "polymarket", D("0.5900")),
    ]


async def test_the_top1_fixture_can_tell_its_own_mutants_apart(seeded_db):
    """The matrix above is only a gate if it sees the top-1's own failure modes:
    a dropped kickoff bound, the NULL-home guard moved out of the top-1, the
    source dedupe dropped, and a misaligned cutoff array."""
    session, candidates = seeded_db
    m = _bind_matrix(candidates)
    base = m["base"]
    live = await _run(session, PREMATCH_PRIOR_TOP1_SQL, base)

    assert _TOP1_UNBOUNDED_SQL != PREMATCH_PRIOR_TOP1_SQL, "the bound moved"
    assert await _run(session, _TOP1_UNBOUNDED_SQL, base) != live

    null_guard_dropped = PREMATCH_PRIOR_TOP1_SQL.replace(
        "AND s.home_win_probability IS NOT NULL", ""
    )
    assert null_guard_dropped != PREMATCH_PRIOR_TOP1_SQL
    assert await _run(session, null_guard_dropped, base) != live

    no_dedupe = PREMATCH_PRIOR_TOP1_SQL.replace("SELECT DISTINCT u.src", "SELECT u.src")
    assert no_dedupe != PREMATCH_PRIOR_TOP1_SQL
    dup = m["duplicate_and_null_sources"]
    assert await _run(session, no_dedupe, dup) != await _run(
        session, PREMATCH_PRIOR_TOP1_SQL, dup
    )

    rotated = dict(base, cutoffs=base["cutoffs"][1:] + base["cutoffs"][:1])
    assert await _run(session, PREMATCH_PRIOR_TOP1_SQL, rotated) != live


async def test_the_callers_hand_back_the_same_output_with_the_switch_on_and_off(
    seeded_db, monkeypatch
):
    """The caller's view, both arms, cold → warm → mixed, over the whole matrix.

    The cache is reset between arms: its keys do not name the statement (on
    purpose — flipping the switch must not empty it), so a warm cache would
    otherwise serve the other arm's rows and prove nothing.
    """
    import app.utils.prematch_reading as pr
    from app.utils.settled_prematch_batch import settled_prematch_odds_by_event

    monkeypatch.setattr(pr, "_utcnow", lambda: _T0 + timedelta(days=30))
    monkeypatch.delenv("PREMATCH_READING_CACHE", raising=False)
    monkeypatch.setenv("PREMATCH_READING_CACHE_SHARED", "0")
    session, candidates = seeded_db

    def fetched(rows):
        return _ordered(
            [
                (
                    r.event_id,
                    r.source,
                    r.home_win_probability,
                    r.away_win_probability,
                    r.draw_probability,
                )
                for r in rows
            ]
        )

    def nested_items(d):
        return [(k, list(v.items())) for k, v in d.items()]

    async def outcome(call):
        # The cache sorts `sources` into its key, so a NULL source raises there,
        # before either statement runs — in both arms alike. Unreachable from
        # production (the binds carry the ladder constant); recorded, not hidden.
        try:
            return await call()
        except TypeError as exc:
            return ("raised", type(exc).__name__)

    async def one_arm(flag):
        monkeypatch.setenv("PREMATCH_PRIOR_TOP1", flag)
        out = {}
        for case, binds in _bind_matrix(candidates).items():
            monkeypatch.delenv("PREMATCH_READING_CACHE", raising=False)
            pr._reset_prematch_cache_for_tests()

            async def fetch(b=binds):
                return fetched(await pr.fetch_prematch_prior_rows(session, b))

            cold = await outcome(fetch)
            warm = await outcome(fetch)
            pr._reset_prematch_cache_for_tests()
            # mixed: hold the first position's game, read the rest.
            first = {
                "ids": binds["ids"][:1],
                "cutoffs": binds["cutoffs"][:1],
                "sources": binds["sources"],
            }
            await outcome(lambda: pr.fetch_prematch_prior_rows(session, first))
            mixed = await outcome(fetch)
            pr._reset_prematch_cache_for_tests()

            async def priors(b=binds):
                return nested_items(await pr.read_prematch_priors(session, b))

            held = await outcome(priors)
            # cache off: every shape reaches the statement, NULL sources included.
            monkeypatch.setenv("PREMATCH_READING_CACHE", "0")
            uncached = await outcome(fetch)
            uncached_priors = await outcome(priors)
            out[case] = (cold, warm, mixed, held, uncached, uncached_priors)
        monkeypatch.delenv("PREMATCH_READING_CACHE", raising=False)
        pr._reset_prematch_cache_for_tests()
        out["batch"] = list(
            (
                await settled_prematch_odds_by_event(
                    session, candidates, opening=lambda e: (None, None)
                )
            ).items()
        )
        return out

    off = await one_arm("0")
    on = await one_arm("1")

    assert on == off
    raised = ("raised", "TypeError")
    for case, binds in _bind_matrix(candidates).items():
        cold, warm, mixed, _, uncached, _ = on[case]
        direct = await _run(session, PREMATCH_PRIOR_SQL, binds)
        assert uncached == direct, case
        if None in binds["sources"] and set(binds["sources"]) - {None}:
            # sorting the key compares a str with None
            assert cold == warm == mixed == raised, case
        else:
            assert cold == warm == mixed == direct, case
    assert on["batch"], "the settled batch must answer the seeded settled cards"


async def test_a_timestamp_tie_goes_to_the_later_inserted_row(seeded_db):
    """Two rows for one game and source at the same `captured_at`.

    The walk's `DISTINCT ON` keeps an arbitrary one — so it is only asserted to
    return ONE OF them. The top-1 says which: `s.id DESC`, the later insert.
    Seeded in both insertion orders so a value-ordering coincidence cannot pass
    it, and once with the later insert's home NULL, where the guard inside the
    top-1 hands the tie to the earlier row.
    """
    session, candidates = seeded_db
    sport_id = (
        await session.execute(
            text("SELECT id FROM sports WHERE key = 'baseball_mlb_p222'")
        )
    ).scalar_one()
    kick = _T0 + timedelta(days=10)

    async def tied_game(*homes):
        ev = Event(
            sport_id=sport_id,
            home_team_name="P222 Tie Home",
            away_team_name="P222 Tie Away",
            commence_time=kick,
            status="completed",
        )
        session.add(ev)
        await session.flush()
        for home in homes:  # one flush each, so ids follow this order
            session.add(
                WinProbSnapshot(
                    event_id=ev.id,
                    source="kalshi",
                    captured_at=kick - timedelta(minutes=30),
                    home_win_probability=home,
                    away_win_probability=None if home is None else 1 - home,
                )
            )
            await session.flush()
        await session.commit()
        return ev.id

    rising = await tied_game(0.4000, 0.4500)
    falling = await tied_game(0.4500, 0.4000)
    null_last = await tied_game(0.4000, None)
    binds = {
        "ids": [rising, falling, null_last],
        "cutoffs": [kick, kick, kick],
        "sources": list(PREDICTION_MARKET_SOURCES),
    }

    top1 = [r[:3] for r in await _run(session, PREMATCH_PRIOR_TOP1_SQL, binds)]
    assert top1 == [
        (rising, "kalshi", Decimal("0.4500")),
        (falling, "kalshi", Decimal("0.4000")),
        (null_last, "kalshi", Decimal("0.4000")),
    ]

    walk = [r[:3] for r in await _run(session, PREMATCH_PRIOR_SQL, binds)]
    assert [r[:2] for r in walk] == [r[:2] for r in top1]
    assert {r[2] for r in walk[:2]} <= {Decimal("0.4000"), Decimal("0.4500")}
    assert walk[2] == (null_last, "kalshi", Decimal("0.4000"))
