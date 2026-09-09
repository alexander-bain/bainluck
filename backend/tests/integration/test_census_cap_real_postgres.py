"""The density + success-cohort census caps, executed against a REAL PostgreSQL.

## what is being replaced, and why the old form was expensive

Both tiles of `precompute_backfill_progress` scored each sampled outcome's
history from an uncorrelated-per-row `COUNT(*)` over `futures_odds_snapshots`
(205M rows / 53 GB), with **no cap**. Measured on `pg_stat_statements`,
2026-08-31 18:50Z -> 2026-09-09 21:18Z (9.1 d):

    statement                     calls   GB read   GB/call
    density   (WITH ro AS ...)      227     566.0     2.493
    cohort    (WITH ro AS ...)      226     448.9     1.986
    chart_density (WITH uv AS ...)  225      91.9     0.409   <- already capped

1,015 GB of the window's 7,940 GB database-wide -- the two largest disk readers
in the database, and 8x the accuracy rebuild they share the 2-slot `heavy` queue
with. #4444; ship #4456.

## why this gate needs a real server

`tests/test_backfill_progress_census_bounds_4444.py` asserts the caps are in the
SQL text. That is not the claim. The claim is that the caps **do not change the
numbers the tile reports**, and three of the four things it rests on cannot be
graded by reading:

1. **A window function's output filtered in the CTE that consumes it.**
   `WHERE ro.rn <= :percap` is what stops the correlated probe from ever being
   evaluated for a row outside the sample; if PostgreSQL evaluated the target
   list before that qual, the fix would save nothing while every text assertion
   stayed green. Only an executing planner can settle it.
2. **`snaps >= DENSE_POINTS` surviving a cap of `DENSE_POINTS + 1` EXACTLY.**
   The whole safety argument is that the cap is invisible to both surviving
   predicates. An off-by-one is a silently wrong dense rate on every source.
3. **The cap actually binding.** `avg_snapshots_capped` is asserted against a
   value that is only reachable if the 40-snapshot outcome was counted as 16.
4. **The statements parse at all.** They are the module's only two raw-SQL
   constants and no unit test executes them.

There is no local PostgreSQL in the agent sandbox, so CI is the environment that
runs this. The `search-recall` job provides the container, and its skip-detection
step is what stops a skipped gate from reading as a passing one.

## the controls, and what each one can actually fail on

* **a cap at or below the dense threshold** — an outcome with EXACTLY
  `DENSE_POINTS` snapshots must still read dense.
* **an off-by-one the other way** — an outcome with `DENSE_POINTS - 1` must NOT.
* **a cap that never binds** — an outcome with 40 snapshots pins
  `avg_snapshots_capped` to a value only a binding cap produces.
* **`snaps >= 1` broken by the cap** — an outcome with exactly 1 snapshot must
  count as "any", and one with 0 must not.
* **the month-starvation trap (the reason this fix is not a flat `LIMIT`)** — a
  group with more rows than the cap and a group with fewer are seeded together,
  and the small one must come back WHOLE. A global `LIMIT :percap` returns
  `percap` rows in scan order and would drop the small group entirely; every
  text assertion in the unit file would still pass.
* **a within-group pick that is not random** — repeated runs over an over-cap
  group must not choose the same rows every time.

`test_the_seeded_corpus_can_distinguish_the_wrong_answers` asserts those shapes
are present, so a future edit to the seed cannot quietly make the rest vacuous.
"""

from __future__ import annotations

import importlib
import os
from datetime import date

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [pytest.mark.asyncio]

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres census-cap "
        "contract (CI job `search-recall` provides one)"
    ),
)

pbp = importlib.import_module("app.tasks.precompute_backfill_progress")

#: `key -> (source, resolution_date, snapshot count, resolution_source, has_cal)`.
#:
#: The two `source` values are also the two GROUPs: `kalshi` is the over-cap
#: group (5 outcomes) and `polymarket` the under-cap one (2). Both resolve
#: inside one month each, so the density tile's (source, month) groups and the
#: cohort tile's (source) groups are the same partition here -- which is what
#: lets one seed grade both statements.
_SEED: dict[str, tuple[str, str, int, str, bool]] = {
    # far over the cap: pins avg_snapshots_capped, and must still read dense.
    "over":       ("kalshi",     "2026-08-10", 40, "api_settlement", True),
    # EXACTLY the threshold: the off-by-one that a cap of DENSE_POINTS breaks.
    "exact":      ("kalshi",     "2026-08-11", pbp.DENSE_POINTS, "game_score", True),
    # one below: must NOT read dense, or the cap is rounding the wrong way.
    "just_under": ("kalshi",     "2026-08-12", pbp.DENSE_POINTS - 1, "box_score", False),
    # exactly 1: `snaps >= 1` must survive the cap.
    "one":        ("kalshi",     "2026-08-13", 1, "manual", False),
    # none at all: must not count as "any".
    "none":       ("kalshi",     "2026-08-14", 0, "manual", False),
    # the SMALL group. A flat LIMIT would drop it; it must come back whole.
    "small_a":    ("polymarket", "2026-09-01", 20, "api_settlement", True),
    "small_b":    ("polymarket", "2026-09-02", 2, "manual", False),
}

_BIG_GROUP = "kalshi"
_SMALL_GROUP = "polymarket"
_BIG_N = sum(1 for v in _SEED.values() if v[0] == _BIG_GROUP)
_SMALL_N = sum(1 for v in _SEED.values() if v[0] == _SMALL_GROUP)

#: Large enough that every seeded row is sampled, so the exactness assertions are
#: deterministic. The per-group cap is exercised separately at `_TIGHT_PERCAP`.
_WIDE_PERCAP = 1000
#: Smaller than the big group and smaller than the small group is NOT -- that
#: asymmetry is the whole point of the month-starvation control.
_TIGHT_PERCAP = 3

#: `random() < :frac` must admit everything, or the seed size is a coin flip.
_ALL = 1.0


@pytest.fixture
async def pg_engine():
    """Real Postgres with the real schema.

    Function-scoped for the reason `test_tag_counts_real_postgres.py` records:
    `pytest.ini` leaves `asyncio_default_fixture_loop_scope` unset, so a
    module-scoped async fixture would outlive the loop that made its engine.
    """
    from sqlalchemy.ext.asyncio import create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


async def _seed(conn) -> None:
    """Insert the corpus.

    🔴 EVERY NOT NULL COLUMN IS SPELLED OUT, INCLUDING THE ONES THAT LOOK
    OPTIONAL. `futures_markets.category` / `.mutually_exclusive` / `.status` and
    `futures_odds_snapshots.reading_count` are NOT NULL carrying a **client-side
    `default=`**, applied by the ORM and invisible to a raw INSERT — omitting one
    raises `NotNullViolation` rather than silently taking the default.
    `tests/test_pg_gate_seed_completeness.py` parses these INSERTs against the
    live ORM metadata; this file is registered in its `COVERED` tuple.
    """
    for key, (source, res_date, snaps, res_source, has_cal) in _SEED.items():
        market_id = (
            await conn.execute(
                text(
                    "INSERT INTO futures_markets "
                    "(source, external_id, name, category, mutually_exclusive, status, resolution_date) "
                    "VALUES (:s, :x, :n, 'championship', true, 'resolved', :d) "
                    "RETURNING id"
                ),
                {
                    "s": source,
                    "x": f"cal-1075-{key}",
                    "n": f"cap gate {key}",
                    # a `date`, not the ISO string — see `_params`.
                    "d": date.fromisoformat(res_date),
                },
            )
        ).scalar_one()
        outcome_id = (
            await conn.execute(
                text(
                    "INSERT INTO futures_outcomes "
                    "(market_id, external_id, name, calibration_probability, resolution_source) "
                    "VALUES (:m, :x, :n, :cp, :rs) RETURNING id"
                ),
                {
                    "m": market_id,
                    "x": f"cal-1075-o-{key}",
                    "n": key,
                    "cp": 0.42 if has_cal else None,
                    "rs": res_source,
                },
            )
        ).scalar_one()
        for _ in range(snaps):
            await conn.execute(
                text(
                    "INSERT INTO futures_odds_snapshots "
                    "(outcome_id, bookmaker, probability, reading_count) "
                    "VALUES (:o, 'kalshi', 0.5, 1)"
                ),
                {"o": outcome_id},
            )


def _params(percap: int) -> dict:
    """The tile's real binds, with only the sample bounds relaxed for the seed.

    `snapcap` and `dense` are the REAL module constants — the point of the gate
    is that those two, together, are exact.

    🔴 `since` is a `date`, never the ISO string it reads as. `resolution_date`
    is `timestamptz` and asyncpg REFUSES a str bound to it (the module's own
    call sites do `date.fromisoformat` for exactly this reason).
    """
    return {
        "since": date(2026, 6, 1),
        "frac": _ALL,
        "dense": pbp.DENSE_POINTS,
        "snapcap": pbp.CENSUS_SNAP_CAP,
        "percap": percap,
    }


async def test_the_seeded_corpus_can_distinguish_the_wrong_answers():
    # Deliberately NOT gated on the server: this grades the FIXTURE, so a future
    # edit to _SEED cannot quietly make every assertion below vacuous — and it
    # should say so wherever the file is collected, not only where a DB exists.
    counts = sorted(v[2] for v in _SEED.values())
    assert pbp.DENSE_POINTS in counts, "no outcome sits EXACTLY on the threshold"
    assert pbp.DENSE_POINTS - 1 in counts, "no outcome sits just below it"
    assert 1 in counts and 0 in counts, "the `snaps >= 1` boundary is unseeded"
    assert max(counts) > pbp.CENSUS_SNAP_CAP, "nothing exceeds the cap, so the cap never binds"
    assert _BIG_N > _TIGHT_PERCAP, "the big group does not exceed the per-group cap"
    assert _SMALL_N <= _TIGHT_PERCAP, "the small group is not small enough to prove the trap"
    assert _BIG_N + _SMALL_N > _TIGHT_PERCAP, (
        "a flat LIMIT would not even be distinguishable from the partitioned cap"
    )


@needs_postgres
async def test_density_rates_are_exact_under_the_cap(pg_engine):
    async with pg_engine.begin() as conn:
        await _seed(conn)
        rows = (await conn.execute(text(pbp.DENSITY_SQL), _params(_WIDE_PERCAP))).all()

    # Every kalshi market in the seed resolves in 2026-08, so they form ONE
    # (source, month) group; polymarket forms one in 2026-09.
    big = {r.mon: r for r in rows if r.source == _BIG_GROUP}
    assert set(big) == {"2026-08"}, f"kalshi seed must form one month group, got {sorted(big)}"

    g = big["2026-08"]
    assert g.sampled == _BIG_N
    # `snaps >= DENSE_POINTS` is EXACT under a cap of DENSE_POINTS + 1:
    # `over` (40 -> counted as 16) and `exact` (15) are dense; `just_under` (14)
    # is not. This is the assertion the whole cap rests on.
    assert g.ge_dense == 2, f"dense count wrong: {g.ge_dense}"
    # `snaps >= 1` is exact too: over, exact, just_under, one — but NOT `none`.
    assert g.any_snap == 4, f"any-snapshot count wrong: {g.any_snap}"
    assert g.has_cal == 2

    small = {r.mon: r for r in rows if r.source == _SMALL_GROUP}
    assert set(small) == {"2026-09"}
    assert small["2026-09"].sampled == _SMALL_N


@needs_postgres
async def test_the_cap_actually_binds_and_the_mean_says_so(pg_engine):
    async with pg_engine.begin() as conn:
        await _seed(conn)
        rows = (await conn.execute(text(pbp.DENSITY_SQL), _params(_WIDE_PERCAP))).all()

    g = next(r for r in rows if r.source == _BIG_GROUP)
    cap = pbp.CENSUS_SNAP_CAP
    expected = round(
        (min(40, cap) + min(pbp.DENSE_POINTS, cap) + min(pbp.DENSE_POINTS - 1, cap) + 1 + 0)
        / float(_BIG_N),
        1,
    )
    assert float(g.avg_snaps) == expected, (
        f"mean {g.avg_snaps} != {expected}; an UNCAPPED mean would read "
        f"{round((40 + pbp.DENSE_POINTS + pbp.DENSE_POINTS - 1 + 1 + 0) / float(_BIG_N), 1)}"
    )
    # And the two must differ, or the assertion above proves nothing.
    assert expected != round((40 + pbp.DENSE_POINTS + pbp.DENSE_POINTS - 1 + 1) / float(_BIG_N), 1)


@needs_postgres
async def test_a_small_group_survives_the_per_group_cap(pg_engine):
    """THE month-starvation control. A flat `LIMIT :percap` returns `percap` rows
    in scan order and would drop the small group entirely."""
    async with pg_engine.begin() as conn:
        await _seed(conn)
        rows = (await conn.execute(text(pbp.DENSITY_SQL), _params(_TIGHT_PERCAP))).all()

    by_source: dict[str, int] = {}
    for r in rows:
        by_source[r.source] = by_source.get(r.source, 0) + r.sampled

    assert _SMALL_GROUP in by_source, (
        "the small group VANISHED — this is the flat-LIMIT regression the "
        "PARTITION exists to prevent"
    )
    assert by_source[_SMALL_GROUP] == _SMALL_N, "the small group must come back WHOLE"
    assert by_source[_BIG_GROUP] == _TIGHT_PERCAP, "the big group must be capped"
    assert sum(by_source.values()) > _TIGHT_PERCAP, (
        "total rows equal to the cap is the signature of a GLOBAL limit"
    )


@needs_postgres
async def test_cohort_rates_are_exact_under_the_cap(pg_engine):
    async with pg_engine.begin() as conn:
        await _seed(conn)
        rows = (await conn.execute(text(pbp.SUCCESS_COHORT_SQL), _params(_WIDE_PERCAP))).all()

    g = next(r for r in rows if r.source == _BIG_GROUP)
    assert g.sampled == _BIG_N
    assert g.ge_dense == 2, "40-snapshot and exactly-threshold outcomes must read dense"
    assert g.has_cal == 2
    assert g.cal_and_dense == 2
    # `just_under` carries box_score, so all three of the authoritative sources
    # are represented and `manual` is excluded.
    assert g.authoritative == 3

    small = next(r for r in rows if r.source == _SMALL_GROUP)
    assert small.sampled == _SMALL_N


@needs_postgres
async def test_cohort_small_group_survives_the_per_group_cap(pg_engine):
    async with pg_engine.begin() as conn:
        await _seed(conn)
        rows = (await conn.execute(text(pbp.SUCCESS_COHORT_SQL), _params(_TIGHT_PERCAP))).all()

    by_source = {r.source: r.sampled for r in rows}
    assert by_source.get(_SMALL_GROUP) == _SMALL_N
    assert by_source.get(_BIG_GROUP) == _TIGHT_PERCAP


@needs_postgres
async def test_the_within_group_pick_is_random_not_physical(pg_engine):
    """`ORDER BY random()` inside the window. Ordering by id instead would make
    the tile report the same `percap` rows of a group forever — a stable,
    plausible, wrong sample.

    Probabilistic, and deliberately so: choosing 2 of 5 the same way 12 times
    running has probability (1/C(5,2))^11 ≈ 1e-11 under a real random pick, so a
    failure here is a real regression, not flake.
    """
    async with pg_engine.begin() as conn:
        await _seed(conn)
        seen = set()
        for _ in range(12):
            rows = (
                await conn.execute(
                    text(pbp.DENSITY_SQL), _params(2)
                )
            ).all()
            g = next(r for r in rows if r.source == _BIG_GROUP)
            # The dense count of a 2-row sample varies with WHICH 2 were picked.
            seen.add((g.sampled, g.ge_dense, g.any_snap, float(g.avg_snaps)))

    assert len(seen) > 1, (
        "12 runs produced an identical sample every time — the per-group pick is "
        "not random"
    )
