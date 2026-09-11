"""#4057: the Kalshi settlement selection's two WHERE clauses, against a REAL PostgreSQL.

## why this gate needs a real server

`_select_kalshi_settlement_tickers()` decides WHICH settled Kalshi markets a
cycle asks the venue about. Everything the ship claims is in those two WHERE
clauses:

    -- band 1, new in #4057, grade test corrected in #5146
    COALESCE(fm.settled_at, fm.resolution_date) BETWEEN NOW() - :floor AND NOW()
    AND NOT EXISTS (an outcome with is_winner IS TRUE)
    AND EXISTS (an outcome that is neither authoritative nor ungradeable_result)
    ORDER BY MAX(COALESCE(fm.settled_at, fm.resolution_date)) DESC LIMIT :fresh

    -- band 2, the pre-existing alphabetical sweep
    fm.external_id > :cursor ... ORDER BY fm.external_id ASC LIMIT :tail

A fake session that answers "any statement mentioning `futures_markets`" with a
canned list agrees with itself: delete the floor, the blank test, the
`ungradeable_result` exclusion or the upper bound and every unit test in
`tests/test_kalshi_settlement_recency_band_4057.py` still passes, because a row
is absent from that list only because the test author left it out.

There is no local PostgreSQL in the agent sandbox, so CI is where this runs; the
`search-recall` job's "Verify the gate is actually armed" step is what stops a
skipped gate reading as a passing one.

## what production says, so the corpus is not invented

Measured through `/api/admin/db-query` on 2026-09-10 11:05–11:40Z:

* the tail band's own population is **71,389 distinct event tickers** — at 2,000
  a cycle, 4 cycles a day, one wrap is **~8.9 days**, and a market that settles
  below the cursor waits for it;
* **37,190** Kalshi markets were observed settling in the last 3 days and
  **29,556 of them (79%)** carry a `resolution_date` older than 3 days or none —
  which is why the recency signal is `COALESCE(settled_at, resolution_date)` and
  not the schedule alone;
* the recency band's population was **2,886** tickers over 3 days, **180** per
  6-hour cycle against a 400-ticker band — 2.2x headroom, so the band could not
  be outrun by ordinary inflow. **That claim is retired; see below.**

### the headroom claim above is DEAD, and it was never the right question (#5152)

Re-measured 2026-09-11 10:45–10:55Z, after #5146 corrected the grade test, running
the shipped band-1 statement itself rather than a paraphrase of it. The 2,886 was
a count of the population the OLD clause could see; under `IS TRUE` the same
window holds **7,625** distinct tickers, so the "2.2x headroom" is not merely
smaller — it is measuring a pool that no longer exists.

But replacing 2.2x with a worse ratio would repeat the original mistake, because
the population is not uniform and a ratio assumes it is. Distinct eligible
tickers by 6-hour cycle-age:

    cycle  -0    73     -6    243
    cycle  -1   282     -7   1523
    cycle  -2    31     -8   1153
    cycle  -3   259     -9   1671
    cycle  -4    58    -10   2074
    cycle  -5   109    -11    149

Two facts follow, and they point opposite ways:

* **Ordinary inflow does not outrun the band.** The two newest cycles hold 355
  tickers against 400 slots. Nothing that settled in the last 12 hours is being
  crowded out, which is what "last night's game is graded by morning" actually
  depends on.
* **84% of the pool is unreachable by construction, not by capacity.** 6,421
  tickers sit in the single 24-hour block at cycles -7..-10. The band is
  newest-first with a hard `LIMIT 400`, and the cumulative count from cycle -0
  crosses 400 inside cycle -3 — so the band reaches back roughly 18–24 hours and
  can never see that block at all. It ages out of `_FRESH_SETTLEMENT_FLOOR_DAYS`
  and falls to band 2's ~11-day alphabetical wrap.

That block is not the cohort the venue has nothing to say about. Bucketing it by
whether a cycle has ever received a venue answer for the ticker: **1,911 never
touched, 4,478 carrying only a non-authoritative source, 180 asked-partial** — so
6,389 of 6,569 have never had an authoritative answer, and 97% have never been
asked at all.

Two consequences a later reader should not have to re-derive:

* `_FRESH_SETTLEMENT_FLOOR_DAYS = 3` is currently **inert**. The `LIMIT` binds at
  ~24 hours, so the 72-hour floor never decides anything. Widening the floor
  would change nothing; only the ordering or the limit can.
* Raising `_FRESH_SETTLEMENT_MAX_SHARE` — #5152's candidate fix — does not
  address this. Doubling the band to 800 would still cover ~12% of that block,
  and it takes the budget from band 2, which is the only thing that ever drains
  it. The defect is a starvation shape, not a capacity shape.

The 400 slots the band does take are healthy and should not be re-aimed on
suspicion: they spread over **197 distinct series** with no series above 4%, and
only 50 of 400 are high-frequency (15-minute / hourly) tickers.

## what this corpus got WRONG for its first day, and why the shape matters (#5146)

Every "blank" row below used to be seeded `is_winner = NULL`, and the graded arm
`is_winner = true`. Production has almost none of the first shape:
`futures_outcomes.is_winner` is `nullable=True, default=False,
server_default=text("false")`, so a leg no grader has touched stores **FALSE**.
NULL is the *rare* state — mostly #1852's retraction.

So the shipped clause `NOT EXISTS (is_winner IS NOT NULL)` read the column's own
DEFAULT as a grade, and one untouched leg hid the whole market from this band.
Measured 2026-09-11 07:30–07:55Z inside the band's own 3-day window: the old
clause made **2,416** tickers eligible, `IS TRUE` makes **7,927** — 5,511 (70%)
of freshly-settled tickers could never enter the fast lane, and waited on band
2's ~11-day wrap. `KXNFLPASSTDS-26SEP10SFLAR` (SF–LA Rams, 2026-09-10) was 9/9
`finalized` at Kalshi with three `yes` results while every stored leg sat at
`is_winner=false, resolution_source=NULL`.

`default_false` and `mixed_default` below are that shape. Both are seeded with
EXPLICIT `False` rather than by omitting the column, so the arm tests the clause
and not the seeding path.

## the corpus, and what each row can fail on

Ten markets. Each one is the ONLY row that fails if a particular clause is
deleted, and the two "mutated shape" arms at the bottom execute the deleted
shapes against the same seeded server so a green run cannot mean "the corpus had
nothing discriminating in it".

* **`settled_low`** — settled half an hour ago, ticker `AAA-…` sorts BELOW the
  cursor. The ship: the tail band can never offer it, the recency band must.
* **`settled_high`** — settled two hours ago, `ZZZ-…`, above the cursor. Proves
  the recency band is ordered by TIME, not by the alphabet: it comes LAST here
  while sorting last alphabetically too, which is why `observed_only` below is
  the row that actually separates the two orderings.
* **`schedule_only`** — `settled_at` NULL, `resolution_date` an hour ago. The
  COALESCE's second arm; the pre-column rows.
* **`observed_only`** — `settled_at` 45 minutes ago, `resolution_date` NINE DAYS
  old. The COALESCE's first arm, and 79% of production by measurement. An
  `fm.resolution_date`-only window drops it, and a `resolution_date` ORDERING
  sends it to the back.
* **`stale`** — settled nine days ago. Outside the floor; the tail's job.
* **`future_dated`** — `settled_at` NULL, `resolution_date` twenty days out.
  Excluded by the upper bound. Without it, newest-first ordering parks this row
  at the head of the band forever and the band never grades anything.
* **`already_graded`** — settled an hour ago, one outcome carries
  `is_winner = true`. Not blank, so not this band's work.
* **`ungradeable`** — settled an hour ago, every leg carries
  `ungradeable_result` (#1852's retraction of a fabricated loss). A decision,
  not a gap; in the band it would clog it for three days.
* **`authoritative`** — settled an hour ago, every leg already carries
  `api_settlement`. The pre-existing authority clause.
* **`polymarket`** / **`still_open`** — the source and status clauses.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres Kalshi settlement "
        "recency band gate (CI job `search-recall` provides one)"
    ),
)

UTC = timezone.utc

#: The cursor the corpus is read against: past everything but `ZZZ-…`, which is
#: exactly the production state the ship is about — the sweep is mid-alphabet and
#: tonight's settlements are behind it.
CURSOR = "M"


def _now() -> datetime:
    return datetime.now(UTC)


#: (key, source, status, external_id, settled_at, resolution_date, outcomes)
#: where each outcome is (external_id, is_winner, resolution_source).
def _corpus() -> list[tuple]:
    now = _now()
    # Distinct to the minute on purpose: the ordering arm below asserts an exact
    # list, and two rows sharing a timestamp would make it a coin toss.
    half_hour = now - timedelta(minutes=30)
    forty = now - timedelta(minutes=40)
    three_quarters = now - timedelta(minutes=45)
    fifty = now - timedelta(minutes=50)
    hour = now - timedelta(hours=1)
    two_hours = now - timedelta(hours=2)
    nine_days = now - timedelta(days=9)
    future = now + timedelta(days=20)
    blank = [("leg-a", None, None), ("leg-b", None, None)]
    return [
        ("settled_low", "kalshi", "resolved", "AAA-26SEP10", half_hour, half_hour, blank),
        ("settled_high", "kalshi", "resolved", "ZZZ-26SEP10", two_hours, two_hours, blank),
        ("schedule_only", "kalshi", "resolved", "BBB-26SEP10", None, hour, blank),
        ("observed_only", "kalshi", "resolved", "CCC-26SEP10", three_quarters, nine_days, blank),
        ("stale", "kalshi", "resolved", "DDD-26SEP01", nine_days, nine_days, blank),
        ("future_dated", "kalshi", "resolved", "EEE-26DEC31", None, future, blank),
        (
            "already_graded", "kalshi", "resolved", "FFF-26SEP10", hour, hour,
            [("leg-a", True, "api_settlement"), ("leg-b", None, None)],
        ),
        (
            "ungradeable", "kalshi", "resolved", "GGG-26SEP10", hour, hour,
            [("leg-a", None, "ungradeable_result"), ("leg-b", None, "ungradeable_result")],
        ),
        (
            "authoritative", "kalshi", "resolved", "HHH-26SEP10", hour, hour,
            [("leg-a", None, "api_settlement"), ("leg-b", None, "api_settlement")],
        ),
        ("polymarket", "polymarket", "resolved", "III-26SEP10", hour, hour, blank),
        ("still_open", "kalshi", "open", "JJJ-26SEP10", hour, hour, blank),
        # #5146 — the shape 70% of production is actually in. Every leg carries
        # the server default FALSE and no grader has ever spoken. Under the old
        # `is_winner IS NOT NULL` clause this row is invisible to the band, and
        # `KKK` sorts below the cursor so the tail cannot reach it either: it is
        # the row that waits ~11 days while the venue holds the answer.
        (
            "default_false", "kalshi", "resolved", "KKK-26SEP10", forty, forty,
            [("leg-a", False, None), ("leg-b", False, None)],
        ),
        # ONE untouched leg was enough to hide a market — the SF–LA Rams shape,
        # where some legs were retracted and the rest still hold the default.
        # `all_losers` is the dominant source on this cohort in production
        # (11,636 in-window legs) and is non-authoritative, so the second clause
        # still passes and only the grade test decides this row.
        (
            "mixed_default", "kalshi", "resolved", "LLL-26SEP10", fifty, fifty,
            [("leg-a", None, None), ("leg-b", False, "all_losers")],
        ),
    ]


#: What the recency band must return, newest first, when nothing caps it.
EXPECTED_FRESH = [
    "AAA-26SEP10",
    "KKK-26SEP10",
    "CCC-26SEP10",
    "LLL-26SEP10",
    "BBB-26SEP10",
    "ZZZ-26SEP10",
]


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
        await _seed(conn)

    yield engine

    await engine.dispose()


async def _seed(conn) -> dict[str, int]:
    """Insert the corpus. Returns `{key: futures_markets.id}`.

    🔴 EVERY NOT NULL COLUMN IS SPELLED OUT, INCLUDING THE ONES THAT LOOK
    OPTIONAL. `futures_markets.category` / `.mutually_exclusive` / `.status`
    carry a **client-side `default=`** applied by the ORM and invisible to a raw
    INSERT — omitting one raises `NotNullViolation` rather than taking the
    default. `tests/test_pg_gate_seed_completeness.py` parses these statements
    against live ORM metadata and this file is in its `COVERED` tuple.
    """
    ids: dict[str, int] = {}
    for key, source, status, ext, settled_at, resolution_date, outcomes in _corpus():
        market_id = (
            await conn.execute(
                text(
                    "INSERT INTO futures_markets "
                    "(source, external_id, name, category, mutually_exclusive, "
                    " status, settled_at, resolution_date) "
                    "VALUES (:source, :ext, :name, 'championship', true, "
                    "        :status, :settled_at, :resolution_date) RETURNING id"
                ),
                {
                    "source": source,
                    "ext": ext,
                    "name": f"{key} market",
                    "status": status,
                    "settled_at": settled_at,
                    "resolution_date": resolution_date,
                },
            )
        ).scalar_one()
        ids[key] = market_id

        for leg_ext, is_winner, resolution_source in outcomes:
            await conn.execute(
                text(
                    "INSERT INTO futures_outcomes "
                    "(market_id, external_id, name, is_winner, resolution_source) "
                    "VALUES (:mid, :ext, :name, :w, :src)"
                ),
                {
                    "mid": market_id,
                    "ext": f"{ext}-{leg_ext}",
                    "name": f"{key} {leg_ext}",
                    "w": is_winner,
                    "src": resolution_source,
                },
            )
    return ids


async def _select(engine, limit: int, cursor: str = CURSOR):
    from app.tasks.backfill_winners import _select_kalshi_settlement_tickers

    async with engine.connect() as conn:
        return await _select_kalshi_settlement_tickers(conn, limit, cursor)


# ---------------------------------------------------------------------------
# the ship
# ---------------------------------------------------------------------------

@needs_postgres
@pytest.mark.asyncio
async def test_a_market_that_settled_below_the_cursor_is_selected_this_cycle(pg_engine):
    """`AAA-…` settled an hour ago and sorts below the cursor.

    The tail band cannot reach it until the cursor wraps — ~8.9 days on the
    measured production population. The recency band must return it now, and
    this is the whole user-visible ship: a settled market stops showing no
    result while the venue has one.
    """
    fresh, tail = await _select(pg_engine, limit=2000)

    assert "AAA-26SEP10" in fresh
    assert "AAA-26SEP10" not in tail, (
        "the tail band is cursor-bound; if it can see AAA the corpus no longer "
        "reproduces the defect and every assertion here is vacuous"
    )


@needs_postgres
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ticker,shape",
    [
        ("KKK-26SEP10", "every leg carries the server default FALSE"),
        ("LLL-26SEP10", "one leg NULL, one leg the default FALSE + all_losers"),
    ],
)
async def test_an_ungraded_market_whose_legs_hold_the_default_false_is_selected(
    pg_engine, ticker, shape
):
    """#5146 — the ship. `is_winner` defaults to FALSE, so this IS "no result".

    `futures_outcomes.is_winner` is `default=False, server_default=text("false")`,
    so a leg no grader has touched reads FALSE, not NULL. Under the shipped-then
    clause `NOT EXISTS (is_winner IS NOT NULL)` both of these rows were excluded
    from the fast lane — 70% of freshly-settled production tickers — and fell to
    the tail band's ~11-day wrap while the venue already held the answer.

    Both tickers sort BELOW the cursor, so the tail cannot cover for the band;
    without that, a green here would not distinguish the two paths.
    """
    fresh, tail = await _select(pg_engine, limit=2000)

    assert ticker in fresh, shape
    assert ticker not in tail, (
        "the tail band is cursor-bound; if it can reach this ticker the arm no "
        "longer proves the recency band is what selects it"
    )


@needs_postgres
@pytest.mark.asyncio
async def test_the_recency_band_is_ordered_by_settlement_time_not_by_ticker(pg_engine):
    """Newest first, and by the COALESCE — not by the alphabet, not by schedule.

    `CCC` (observed an hour ago, scheduled nine days ago) must outrank `ZZZ`
    (two hours ago). Under `ORDER BY external_id` or `ORDER BY resolution_date`
    this list comes back in a different order.
    """
    fresh, _tail = await _select(pg_engine, limit=2000)
    assert fresh == EXPECTED_FRESH


@needs_postgres
@pytest.mark.asyncio
async def test_a_capped_band_spends_its_budget_on_the_newest(pg_engine):
    """limit=5 -> a 1-ticker band (`_fresh_settlement_budget`), and it takes the newest.

    This is the arm that makes the ordering load-bearing rather than cosmetic:
    with a cap, order decides who is graded tonight and who waits.
    """
    fresh, tail = await _select(pg_engine, limit=5)
    assert fresh == ["AAA-26SEP10"]
    assert len(tail) <= 4


@needs_postgres
@pytest.mark.asyncio
async def test_the_two_bands_never_exceed_the_cycle_budget(pg_engine):
    """Cost neutrality, proven against the server rather than argued from the split."""
    fresh, tail = await _select(pg_engine, limit=5)
    assert len(fresh) + len(tail) <= 5


# ---------------------------------------------------------------------------
# every exclusion, one row each
# ---------------------------------------------------------------------------

@needs_postgres
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ticker,why",
    [
        ("DDD-26SEP01", "settled nine days ago — outside the floor, the tail's job"),
        ("EEE-26DEC31", "future-dated schedule — would park at the head forever"),
        ("FFF-26SEP10", "already carries a grade — not a blank market"),
        ("GGG-26SEP10", "every leg is ungradeable_result — a retraction, not a gap"),
        ("HHH-26SEP10", "every leg is already authoritative"),
        ("III-26SEP10", "polymarket, not kalshi"),
        ("JJJ-26SEP10", "still open"),
    ],
)
async def test_the_recency_band_refuses(pg_engine, ticker, why):
    fresh, _tail = await _select(pg_engine, limit=2000)
    assert ticker not in fresh, why


# ---------------------------------------------------------------------------
# two-armed: the deleted clauses, executed
# ---------------------------------------------------------------------------

_MUTATED_BASE = """
    SELECT fm.external_id
    FROM futures_markets fm
    WHERE fm.source = 'kalshi'
      AND fm.status = 'resolved'
      {window}
      {blank}
      {gradeable}
    GROUP BY fm.external_id
    ORDER BY MAX(COALESCE(fm.settled_at, fm.resolution_date)) DESC
    LIMIT 2000
"""

_WINDOW = (
    "AND COALESCE(fm.settled_at, fm.resolution_date) >= NOW() - INTERVAL '3 days' "
    "AND COALESCE(fm.settled_at, fm.resolution_date) <= NOW()"
)
_FLOOR_ONLY = "AND COALESCE(fm.settled_at, fm.resolution_date) <= NOW()"
_CEILING_ONLY = (
    "AND COALESCE(fm.settled_at, fm.resolution_date) >= NOW() - INTERVAL '3 days'"
)
_SCHEDULE_ONLY_WINDOW = (
    "AND fm.resolution_date >= NOW() - INTERVAL '3 days' "
    "AND fm.resolution_date <= NOW()"
)
_BLANK = (
    "AND NOT EXISTS (SELECT 1 FROM futures_outcomes fo "
    "WHERE fo.market_id = fm.id AND fo.is_winner IS TRUE)"
)
#: The clause as it shipped from #4057 until #5146 — kept so the regression is
#: EXECUTED against this server rather than described in a comment.
_BLANK_IS_NOT_NULL = (
    "AND NOT EXISTS (SELECT 1 FROM futures_outcomes fo "
    "WHERE fo.market_id = fm.id AND fo.is_winner IS NOT NULL)"
)
_GRADEABLE = (
    "AND EXISTS (SELECT 1 FROM futures_outcomes fo WHERE fo.market_id = fm.id "
    "AND COALESCE(fo.resolution_source, '') NOT IN "
    "('api_settlement','clob_authoritative','clob_field_repair','clob_never_graded',"
    "'clob_ordinal','datagolf_settlement','settlement_sync') "
    "AND COALESCE(fo.resolution_source, '') <> 'ungradeable_result')"
)
_GRADEABLE_WITHOUT_RETRACTION = (
    "AND EXISTS (SELECT 1 FROM futures_outcomes fo WHERE fo.market_id = fm.id "
    "AND COALESCE(fo.resolution_source, '') NOT IN "
    "('api_settlement','clob_authoritative','clob_field_repair','clob_never_graded',"
    "'clob_ordinal','datagolf_settlement','settlement_sync'))"
)


async def _mutated(engine, *, window=_WINDOW, blank=_BLANK, gradeable=_GRADEABLE):
    sql = _MUTATED_BASE.format(window=window, blank=blank, gradeable=gradeable)
    async with engine.connect() as conn:
        rows = await conn.execute(text(sql))
    return [r[0] for r in rows.all()]


@needs_postgres
@pytest.mark.asyncio
async def test_the_authoritative_clauses_reproduce_the_shipped_band(pg_engine):
    """The mutation harness is calibrated on the unmutated shape first.

    Without this, a mutated arm that returns the same list as the ship could
    mean either "the clause does nothing" or "the harness is not running the
    query I think it is".
    """
    assert await _mutated(pg_engine) == EXPECTED_FRESH


@needs_postgres
@pytest.mark.asyncio
async def test_dropping_the_floor_sweeps_in_a_nine_day_old_settlement(pg_engine):
    assert "DDD-26SEP01" in await _mutated(pg_engine, window=_FLOOR_ONLY)


@needs_postgres
@pytest.mark.asyncio
async def test_dropping_the_upper_bound_parks_a_future_date_at_the_head(pg_engine):
    """Not merely "included" — FIRST, which is the clog.

    Newest-first ordering hands the head of a capped band to the row with the
    furthest-future schedule, every cycle, forever.
    """
    got = await _mutated(pg_engine, window=_CEILING_ONLY)
    assert got[0] == "EEE-26DEC31"


@needs_postgres
@pytest.mark.asyncio
async def test_a_schedule_only_window_drops_the_row_production_is_made_of(pg_engine):
    """79% of production, in one row: observed an hour ago, scheduled nine days ago."""
    got = await _mutated(pg_engine, window=_SCHEDULE_ONLY_WINDOW)
    assert "CCC-26SEP10" not in got
    assert "AAA-26SEP10" in got, "the schedule-only window is not broken outright"


@needs_postgres
@pytest.mark.asyncio
async def test_dropping_the_blank_test_sweeps_in_an_already_graded_market(pg_engine):
    assert "FFF-26SEP10" in await _mutated(pg_engine, blank="")


@needs_postgres
@pytest.mark.asyncio
async def test_the_pre_5146_grade_test_hides_the_default_false_rows(pg_engine):
    """The regression, executed — not asserted about.

    Running the OLD clause against this same seeded server must drop exactly the
    two default-FALSE rows and keep everything else. If a later edit reverts the
    grade test, the ship arm above goes red and this arm explains why in one
    line: the column's default was read as a grade.
    """
    got = await _mutated(pg_engine, blank=_BLANK_IS_NOT_NULL)

    assert "KKK-26SEP10" not in got
    assert "LLL-26SEP10" not in got
    assert got == [t for t in EXPECTED_FRESH if t not in {"KKK-26SEP10", "LLL-26SEP10"}], (
        "the old clause must differ from the shipped one on the default-FALSE "
        "rows and on NOTHING else — otherwise this arm is measuring some other "
        "change and the 2,416-vs-7,927 production split is not what it explains"
    )


@needs_postgres
@pytest.mark.asyncio
async def test_dropping_the_retraction_exclusion_lets_ungradeable_rows_clog_the_band(
    pg_engine,
):
    got = await _mutated(pg_engine, gradeable=_GRADEABLE_WITHOUT_RETRACTION)
    assert "GGG-26SEP10" in got


# ---------------------------------------------------------------------------
# the tail band is untouched
# ---------------------------------------------------------------------------

@needs_postgres
@pytest.mark.asyncio
async def test_the_tail_band_still_walks_the_alphabet_from_the_cursor(pg_engine):
    """The pre-existing sweep keeps its shape, its cursor and its own budget.

    `ZZZ` is the only corpus ticker above the cursor that carries a
    non-authoritative outcome, so this also proves the recency band did not
    quietly become the whole selection.
    """
    _fresh, tail = await _select(pg_engine, limit=2000)
    assert tail == ["ZZZ-26SEP10"]


@needs_postgres
@pytest.mark.asyncio
async def test_the_tail_band_ignores_recency_entirely(pg_engine):
    """From the start of the alphabet it returns the stale and the future-dated too.

    The two bands answer different questions; this is the row that proves the
    recency clauses did not leak into the sweep that must keep the whole
    population moving.
    """
    _fresh, tail = await _select(pg_engine, limit=2000, cursor="")
    assert "DDD-26SEP01" in tail
    assert "EEE-26DEC31" in tail
