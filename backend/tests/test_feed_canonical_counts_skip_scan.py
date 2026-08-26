"""RED-FIRST GATE for LAT-P093 — the feed's cache-miss build stops paying 1.4s
to count four things.

Fable directive 2026-08-25, pasted and reviewed by Alex:

    SHIP: the feed loads fast even on a cache miss — the 4,502ms cold build
    dies. Break down where the 4,502ms goes on a feed cache miss using your
    existing instrumentation, and BUILD the biggest reduction.

## The measurement that chose this target

`GET /api/admin/latency-slow-events?limit=300` on 2026-08-26 (the #1459 ring:
every request over 5s, with its `X-Feed-Stages` breakdown, 7-day TTL). 145
`/api/feed` `miss` events, total p50 7,243ms. Per-stage p50 across those misses:

    futures                       3934.0 ms   (parent — contains the below)
    concepts                      1441.6 ms
    futures.canonical_counts      1428.4 ms   <-- this file
    events                        1203.2 ms
    futures.market_load            997.9 ms
    futures.scoring_loop           288.1 ms
    personalization                193.5 ms
    team_enrichment                184.1 ms
    golf                            59.4 ms

`futures.canonical_counts` is the largest *leaf* term on the build path and the
only one whose cost is pure waste rather than work.

## What the waste actually is

`_query_canonical_source_counts` answers one question per candidate key: *which
of our sources carry this canonical market?* Production shape, measured
2026-08-26:

    futures_markets rows with a canonical_market_key : 345,334
    DISTINCT canonical_market_key                    :       747
    DISTINCT source                                  :         4
                                                       (kalshi, polymarket,
                                                        datagolf, odds_api)

So the answer for one key is at most four short strings, and the average key
has ~462 rows behind it. `EXPLAIN (ANALYZE, BUFFERS)` on production over a real
150-key candidate set:

    Aggregate (Sorted)  actual rows=150  time=1522.3ms  shared hit=70,779
      -> Index Only Scan ix_fm_canonical_source_count
           actual rows=302,027  time=977.9ms

**302,027 index rows read to emit 150.** The aggregate is correct and the index
is the right one; the SHAPE is wrong. `count(DISTINCT source)` has to visit
every duplicate to learn it is a duplicate.

The right shape is a skip scan: probe `(canonical_market_key, source)` once per
(key, source) pair and stop at the first hit. 150 keys x 4 sources = 600
`LIMIT 1` index probes. Same production data, same 150 keys:

    Aggregate  actual rows=150  time=27.7ms  shared hit=2,118
      -> Index Only Scan ix_fm_canonical_source_count  loops=600  rows=0

    1,522ms -> 27.7ms   ·   70,779 buffers -> 2,118

and the two queries returned **byte-identical results over all 150 keys**
(counts and sorted source names, zero diffs) when both were run against
production.

## Why the source list is DERIVED and not written down

Four sources is a fact about today, not a contract. A hardcoded list would make
this function silently under-count the day a fifth source ships — and an
under-count here does not crash, it just quietly stops awarding the
cross-source bonus that ranks a market. That is gotcha #53's shape: the wrong
answer and the right answer have the same type.

So the universe comes from a loose index scan (recursive CTE) over
`ix_futures_markets_source`, measured at 24.7ms / 135 buffers for its four
rows, folded into the same statement — one round trip, and a new source is
picked up the first time a row carrying it exists.

## What this file pins

1. The keyed path emits a SEMI-JOIN, not a grouped DISTINCT aggregate.
2. The source universe is read from the table, not from a literal in the SQL.
3. The (counts, names) return contract is unchanged — same dict shapes, same
   sorted name lists, keys with no rows absent from both.
4. The UNKEYED path (admin trace/debug) is deliberately untouched.
"""

from __future__ import annotations

import re
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.dialects import postgresql

from app.routes import feed as feed_module


# --------------------------------------------------------------------------
# harness
# --------------------------------------------------------------------------


class _RecordingSession:
    """An AsyncSession stand-in that records the statement and replays rows.

    The rows it serves are the (key, source) PAIRS the skip scan returns. That
    is the point of the harness rather than an accident of it: the pre-LAT-P093
    implementation reads ``row.source_count`` / ``row.sources`` off its grouped
    aggregate, so it cannot consume a pair stream at all. This fixture is red
    against it by construction.
    """

    def __init__(self, pairs: list[tuple[str, str]]):
        self._pairs = pairs
        self.statements: list = []

    async def execute(self, statement, *args, **kwargs):
        self.statements.append(statement)
        rows = [
            SimpleNamespace(canonical_market_key=key, source=source)
            for key, source in self._pairs
        ]
        return SimpleNamespace(all=lambda: rows, scalars=lambda: SimpleNamespace(all=lambda: rows))


def _compiled(statement) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


# The production source universe as measured 2026-08-26. Used ONLY to assert
# these names do NOT appear in the emitted SQL — never as an input.
_MEASURED_SOURCES = ("kalshi", "polymarket", "datagolf", "odds_api")


# --------------------------------------------------------------------------
# 1. the shape: a semi-join, not a grouped DISTINCT aggregate
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_keyed_path_probes_instead_of_aggregating():
    """The keyed branch must not read every duplicate row to find the distinct
    ones. 302,027 index rows for 150 answers is the defect; an EXISTS probe per
    (key, source) pair is the fix."""
    db = _RecordingSession([("soccer::championship:2026", "kalshi")])

    await feed_module._query_canonical_source_counts(
        db, {"soccer::championship:2026"}
    )

    assert db.statements, "the keyed branch issued no statement at all"
    sql = _compiled(db.statements[-1]).lower()

    assert "exists" in sql, (
        "the keyed candidate-source lookup must be a semi-join. Without EXISTS "
        "the planner has to read every row behind a key to learn its distinct "
        "sources — 302,027 index rows for 150 answers on production."
    )
    assert "count(distinct" not in sql and "array_agg(distinct" not in sql, (
        "a DISTINCT aggregate over futures_markets is exactly the 1,522ms shape "
        "this gate exists to keep out of the cold build path"
    )


@pytest.mark.asyncio
async def test_probe_count_is_bounded_by_keys_times_sources():
    """The emitted statement must enumerate the key set explicitly, so the work
    is O(keys x sources) probes and not O(rows behind those keys).

    This is the property that makes the fix scale: `futures_markets` grows
    without bound (871,381 rows on 2026-08-26 and rising), the number of
    canonical keys does not (747), and the number of sources really does not
    (4)."""
    keys = {f"sport::championship:20{n:02d}" for n in range(12)}
    db = _RecordingSession([])

    await feed_module._query_canonical_source_counts(db, keys)

    sql = _compiled(db.statements[-1])
    for key in keys:
        assert key in sql, (
            f"candidate key {key!r} is not enumerated in the statement — the "
            "query is scanning for keys rather than probing for them"
        )


# --------------------------------------------------------------------------
# 2. the source universe is derived, never written down
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_source_universe_is_read_from_the_table():
    """A hardcoded source list under-counts silently the day a fifth source
    ships — the market simply stops earning its cross-source bonus and nothing
    reports it (gotcha #53: the wrong answer has the right type)."""
    db = _RecordingSession([])

    await feed_module._query_canonical_source_counts(db, {"politics::championship:2026"})

    sql = _compiled(db.statements[-1]).lower()
    for source in _MEASURED_SOURCES:
        assert f"'{source}'" not in sql, (
            f"source name {source!r} is baked into the SQL. The universe must "
            "come from futures_markets so a new source is picked up by the "
            "first row that carries it."
        )
    assert re.search(r"futures_markets\.source", sql), (
        "the statement never reads futures_markets.source — the universe is "
        "coming from somewhere other than the table"
    )
    assert "recursive" in sql, (
        "deriving the universe with a plain DISTINCT would scan all 871,381 "
        "rows and cost more than the aggregate this change removes; it must be "
        "a loose index scan (recursive CTE), measured at 24.7ms for 4 rows"
    )


# --------------------------------------------------------------------------
# 3. the return contract is unchanged
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_counts_and_names_match_the_aggregate_they_replace():
    """Same answers as `count(DISTINCT source)` / `sorted(array_agg(DISTINCT
    source))` — verified against production over 150 real candidate keys with
    zero diffs, and pinned here on the assembly itself."""
    pairs = [
        ("soccer::championship:2026", "kalshi"),
        ("soccer::championship:2026", "polymarket"),
        ("politics:US:championship:2028", "polymarket"),
        ("golf::championship:2026", "datagolf"),
        ("golf::championship:2026", "kalshi"),
        ("golf::championship:2026", "odds_api"),
    ]
    db = _RecordingSession(pairs)

    counts, names = await feed_module._query_canonical_source_counts(
        db,
        {
            "soccer::championship:2026",
            "politics:US:championship:2028",
            "golf::championship:2026",
            "nothing::championship:2026",
        },
    )

    assert counts == {
        "soccer::championship:2026": 2,
        "politics:US:championship:2028": 1,
        "golf::championship:2026": 3,
    }, "source_count must equal the number of DISTINCT sources behind the key"
    assert names == {
        "soccer::championship:2026": ["kalshi", "polymarket"],
        "politics:US:championship:2028": ["polymarket"],
        "golf::championship:2026": ["datagolf", "kalshi", "odds_api"],
    }, "names must stay a SORTED list per key, as the aggregate produced"

    assert "nothing::championship:2026" not in counts, (
        "a key with no rows was absent from the aggregate's output and must "
        "stay absent — a 0 here would be a new value the scoring path has "
        "never seen"
    )


@pytest.mark.asyncio
async def test_empty_key_set_still_short_circuits_without_a_query():
    """An empty candidate set means "nothing to ask", not "ask about
    everything" — the unkeyed branch groups the whole table."""
    db = _RecordingSession([])

    counts, names = await feed_module._query_canonical_source_counts(db, set())

    assert counts == {} and names == {}
    assert db.statements == [], (
        "an empty key set must cost zero round trips; falling through to the "
        "unkeyed branch would group all 345,334 keyed rows"
    )


# --------------------------------------------------------------------------
# 4. the unkeyed (admin trace) path is deliberately untouched
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unkeyed_path_keeps_the_full_group_by():
    """`keys=None` serves the admin trace/debug callers and must return the
    WHOLE map. It is off the request path (the feed always passes candidate
    keys), so it keeps the aggregate rather than inheriting a rewrite nothing
    measured it needing."""
    rows = [
        SimpleNamespace(
            canonical_market_key="soccer::championship:2026",
            source_count=2,
            sources=["polymarket", "kalshi"],
        )
    ]
    db = AsyncMock()
    db.execute.return_value = SimpleNamespace(all=lambda: rows)

    counts, names = await feed_module._query_canonical_source_counts(db, None)

    assert counts == {"soccer::championship:2026": 2}
    assert names == {"soccer::championship:2026": ["kalshi", "polymarket"]}

    sql = _compiled(db.execute.call_args.args[0]).lower()
    assert "count(distinct" in sql, (
        "the unkeyed branch is the admin trace and is intentionally unchanged; "
        "if this fails the rewrite leaked onto a path it was never measured on"
    )
