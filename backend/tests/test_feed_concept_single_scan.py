"""LAT-P094 — the concept tier scans 50,749 open markets three times to read 315.

WHY THIS FILE EXISTS, measured rather than guessed.

`/api/admin/latency-slow-events` (#1459) is a Redis ring holding every request
over 5s with its `X-Feed-Stages` breakdown. Read 2026-08-26 at 500/500 used,
**166 `/api/feed` cache MISSES**, total p50 7,314ms. With LAT-P093's
`futures.canonical_counts` fix in flight, the per-stage p50 table reads:

    futures                  162   3947.7ms   (parent)
    concepts                 161   1447.2ms   <-- the largest remaining stage
    futures.canonical_counts 144   1338.4ms   (killed by LAT-P093, unmerged)
    events                   165   1212.9ms
    futures.market_load      155   1032.2ms

`concepts` is the next biggest, and it is 18 misses' OWN dominant stage with a
6,012ms worst query and a 12,628ms total — so it owns the tail as well as the
p50.

WHERE THE 1,447ms GOES. The concept tier has three sources and each one reads
its own open markets:

    llm_sport_category = 'mma'          -> 168 rows
    llm_sport_category = 'motorsports'  -> 144 rows
    llm_sport_category = 'cycling'      ->   3 rows

`futures_markets` has no index on `llm_sport_category` for the general case, so
every one of those three runs the SAME plan — `EXPLAIN (ANALYZE, BUFFERS)` on
production 2026-08-26:

    Index Scan using ix_futures_markets_status  (Filter: llm_sport_category = 'mma')
      Actual Rows 168 · Rows Removed by Filter 50,581 · Shared Hit 27,839 · 523.9ms

**50,749 rows visited to emit 168, three times over, for 315 rows total.** Six
interleaved A/B round trips against production: three separate reads 1,109.5ms
p50, one combined read 453.4ms p50.

The shape is the same defect LAT-P093 killed one stage over: the work tracks a
quantity that grows without bound (open markets) while the answer is bounded by
the concept tier's own size. The difference is that here the fix is not a better
query — the single scan is the SAME query — it is doing it ONCE for every source
instead of once PER source.

WHAT THIS FILE PINS
  1. The concept tier issues exactly ONE `futures_markets` read, not one per
     source.
  2. The category set on that read is DERIVED from `CONCEPT_SOURCES`, never a
     hardcoded list — a fourth source must be scanned the day it is registered,
     not the day someone remembers (gotcha #53: a silent omission looks exactly
     like a zero).
  3. A `sport_filter` that selects one source narrows the scan to that source's
     category — the consolidation must not widen the read.
  4. The consolidated path returns exactly what the per-source path returned.
     This is a latency change and nothing else.
  5. If the prefetch fails, every source falls back to its own read and the tier
     survives (gotcha #42 — one bad read must never empty the tier, which is how
     #1091 emptied the entire Sports tab).
  6. Each lister still works standalone. The `/event` adapters, the warmer and
     four existing suites call them directly; the prefetch is an accelerator
     passed in, never a requirement.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.utils import event_concept_population as population

NOW = datetime.now(timezone.utc)
SOON = NOW + timedelta(days=2)

#: LAT-P181. The cycling arm needs one more thing than the other two, and it is
#: not a date — it is an EDITION. `list_cycling_concepts` only counts a market
#: whose `resolution_date.year` equals the year in its config slug
#: (`event_cycling.CYCLING_RACES`, currently `vuelta-2026` and friends), and only
#: surfaces the concept if that resolution is still ahead of `now`.
#:
#: Those two conditions are jointly unsatisfiable once the configured year is
#: over, so NO date this test can pick keeps the arm alive past 2026-12-31.
#:
#: That is a PRODUCT fact, not a test fact: cycling concepts disappear from
#: Discover on 2027-01-01 for users too, until the next editions are added to
#: `CYCLING_RACES`. It is filed on its own account. It is emphatically not this
#: file's subject — this file counts how many reads the scan makes — and a test
#: about read-counting must not be the thing that reports a stale product config,
#: because the only way it can report it is by taking `deploy` down on 01-01.
#:
#: So the specimen carries a clock-derived resolution, and `cycling_edition`
#: below gives the lister an edition for whatever year that lands in. The arm
#: stays fully exercised forever and the calendar is left out of it.
CYCLING_RESOLUTION = NOW + timedelta(days=13)


@pytest.fixture(autouse=True)
def cycling_edition(monkeypatch):
    """Give the lister a Vuelta edition for the specimen's own year.

    LAT-P181. `CYCLING_RACES` is a hand-maintained calendar and the specimen has
    to name an edition it holds. Rather than pin the specimen to the calendar —
    which is the bomb — this pins the calendar to the specimen, for the duration
    of this file only.

    It ADDS an edition; it never removes or rewrites one, so every real config
    entry is still in play and a regression in the matching itself still shows up
    here. What it removes is this file's ability to fail on 01-01 for a reason
    that has nothing to do with counting reads.
    """
    import re

    from app.utils import event_cycling as ec

    year = CYCLING_RESOLUTION.year
    slug = f"vuelta-{year}"
    if slug in ec.CYCLING_RACES:
        return
    monkeypatch.setitem(
        ec.CYCLING_RACES,
        slug,
        ec.CyclingRaceConfig(
            slug=slug,
            display=f"Vuelta a España {year}",
            name_re=re.compile(r"vuelta(\s+a\s+espa)?", re.IGNORECASE),
            aliases=(f"vuelta-a-espana-{year}", "vuelta"),
        ),
    )


# ---------------------------------------------------------------------------
# The specimen population — production-shaped, not invented
# ---------------------------------------------------------------------------

#: Open markets across the three concept categories, shaped like the rows the
#: listers actually consume. Tickers are real Kalshi formats so `card_token`
#: and `is_gp_winner_market` do their real work rather than being stubbed.
MARKETS: tuple[dict, ...] = (
    # --- mma: one UFC card, three fights ---------------------------------
    {
        "llm_sport_category": "mma",
        "id": 101,
        "external_id": "kalshi:KXUFCFIGHT-26AUG30DUPUSM",
        "name": "Du Plessis vs Usman",
        "status": "open",
        "commence_time": SOON,
        "resolution_date": SOON,
        "market_metadata": {"event_title": "UFC 329"},
    },
    {
        "llm_sport_category": "mma",
        "id": 102,
        "external_id": "kalshi:KXUFCFIGHT-26AUG30ANKPER",
        "name": "Ankalaev vs Pereira",
        "status": "open",
        "commence_time": SOON - timedelta(hours=1),
        "resolution_date": SOON,
        "market_metadata": {"event_title": "UFC 329"},
    },
    {
        "llm_sport_category": "mma",
        "id": 103,
        "external_id": "kalshi:KXUFCFIGHT-26AUG30SHEROZ",
        "name": "Shevchenko vs Rozenstruik",
        "status": "open",
        "commence_time": SOON - timedelta(hours=2),
        "resolution_date": SOON,
        "market_metadata": {"event_title": "UFC 329"},
    },
    # --- motorsports: one Grand Prix, winner + a sub-market ---------------
    {
        "llm_sport_category": "motorsports",
        "id": 201,
        "external_id": "kalshi:KXF1-26AUG30",
        "name": "Italian Grand Prix: Driver Winner",
        "status": "open",
        "commence_time": SOON,
        "resolution_date": SOON,
        "market_metadata": {},
    },
    {
        "llm_sport_category": "motorsports",
        "id": 202,
        "external_id": "kalshi:KXF1POLE-26AUG30",
        "name": "Italian Grand Prix: Driver Pole Position",
        "status": "open",
        "commence_time": SOON,
        "resolution_date": SOON,
        "market_metadata": {},
    },
    # --- cycling: one grand tour ------------------------------------------
    {
        "llm_sport_category": "cycling",
        "id": 301,
        "external_id": "polymarket:0xvuelta",
        "name": "Vuelta a Espana 2026 Winner",
        "status": "open",
        "commence_time": SOON,
        # LAT-P181 — this was `datetime(2026, 9, 14, tzinfo=timezone.utc)` and it
        # was measured to take this file red on **2026-09-14**. The anchor above
        # is honestly clock-derived; this ONE field was not, and one field is
        # enough. The lister only surfaces a concept whose resolution is ahead of
        # `now`, so the cycling specimen would have vanished from its own test on
        # a date nobody chose, and two tests about read-counting would have
        # started failing about something else entirely.
        "resolution_date": CYCLING_RESOLUTION,
        "market_metadata": {},
    },
)


class _Result:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return self._rows

    def scalars(self):
        return self

    def unique(self):
        return self


class _RecordingDB:
    """An `AsyncSession` stand-in that records every statement it is handed.

    It answers from `MARKETS` by reading the statement's OWN selected columns,
    so it cannot quietly disagree with a projection change: whatever the caller
    asks for is what it gets back, in that order.
    """

    def __init__(self, *, fail_on_multi_category: bool = False):
        self.statements: list[str] = []
        self._fail_on_multi_category = fail_on_multi_category

    @property
    def market_reads(self) -> list[str]:
        return [s for s in self.statements if "futures_markets" in s]

    @property
    def per_source_reads(self) -> list[str]:
        """Market reads naming exactly one category — i.e. a source's own read.

        A prefetch that fails is still an attempted read and is still recorded,
        so counting fallbacks means counting the single-category ones.
        """
        return [s for s in self.market_reads if len(_categories_named(s)) == 1]

    async def execute(self, stmt, *_a, **_k):
        sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        self.statements.append(sql)

        # The combat lister's schedule source reads `events`; not this test's
        # subject, and an empty schedule is a legitimate production state.
        if "futures_markets" not in sql:
            return _Result([])

        categories = _categories_named(sql)
        if self._fail_on_multi_category and len(categories) > 1:
            raise RuntimeError("prefetch is down")

        names = list(stmt.selected_columns.keys())
        rows = [
            tuple(m[n] for n in names)
            for m in MARKETS
            if m["llm_sport_category"] in categories and m["status"] == "open"
        ]
        return _Result(rows)


def _categories_named(sql: str) -> set[str]:
    return {c for c in ("mma", "motorsports", "cycling") if f"'{c}'" in sql}


# ---------------------------------------------------------------------------
# 1 + 2. One scan, and its category set is derived
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_concept_tier_reads_futures_markets_exactly_once():
    """THE FIX. Three sources, three identical 50,749-row scans, 315 rows.

    Production 2026-08-26: 1,109.5ms p50 for the three, 453.4ms for the one.
    """
    db = _RecordingDB()
    await population.list_all_concepts(db)

    assert len(db.market_reads) == 1, (
        f"the concept tier read futures_markets {len(db.market_reads)} times; "
        "each read is an index scan over every open market (50,749 rows on "
        "production, 27,839 buffers, ~520ms) to answer for one category"
    )


@pytest.mark.asyncio
async def test_the_single_scan_names_every_registered_source_category():
    """Derived from `CONCEPT_SOURCES`, never a hardcoded list.

    A fourth source registered tomorrow must be inside the scan the same day.
    A hardcoded list would leave it silently unfetched, and an unfetched source
    returns [] — indistinguishable from "this sport has nothing on" (gotcha #53).
    """
    db = _RecordingDB()
    await population.list_all_concepts(db)

    registered = {s.category for s in population.CONCEPT_SOURCES}
    covered_by_the_specimen = {"mma", "motorsports", "cycling"}
    assert registered == covered_by_the_specimen, "specimen drift: a source moved"
    assert _categories_named(db.market_reads[0]) == registered


@pytest.mark.asyncio
async def test_the_scan_is_still_bounded_to_open_markets():
    """`status = 'open'` is what makes the scan 50,749 rows and not 871,381."""
    db = _RecordingDB()
    await population.list_all_concepts(db)

    assert "'open'" in db.market_reads[0]


# ---------------------------------------------------------------------------
# 3. A sport filter narrows the scan
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_sport_filter_narrows_the_scan_to_that_source():
    """Consolidating must not widen the read.

    `/api/feed?sport=cycling` asks one source a question. Scanning mma and
    motorsports for it would make the shared path SLOWER than the three
    separate reads it replaces, for every filtered request.
    """
    db = _RecordingDB()
    await population.list_all_concepts(db, sport_filter="cycling")

    assert len(db.market_reads) == 1
    assert _categories_named(db.market_reads[0]) == {"cycling"}


@pytest.mark.asyncio
async def test_a_sport_filter_matching_no_source_reads_nothing():
    db = _RecordingDB()
    concepts = await population.list_all_concepts(db, sport_filter="basketball")

    assert concepts == []
    assert db.market_reads == []


# ---------------------------------------------------------------------------
# 4. The answer is unchanged. This is a latency change and nothing else.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_consolidated_path_returns_what_the_per_source_path_returned():
    """The equivalence that makes this shippable.

    The per-source path is driven by making the prefetch fail, which is the
    same fallback production takes — so this compares the two paths that both
    really run, not the new path against a reimplementation of the old one.
    """
    shared_db = _RecordingDB()
    shared = await population.list_all_concepts(shared_db)

    per_source_db = _RecordingDB(fail_on_multi_category=True)
    per_source = await population.list_all_concepts(per_source_db)

    assert len(shared_db.market_reads) == 1
    assert len(per_source_db.per_source_reads) == 3

    assert shared == per_source, "the consolidation changed the answer"
    assert shared, "the specimen produced no concepts — the comparison is vacuous"
    assert {c["domain"] for c in shared} == {"ufc", "f1", "cycling"}


# ---------------------------------------------------------------------------
# 5. Failure of the prefetch never empties the tier (gotcha #42)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_failed_prefetch_falls_back_per_source_and_the_tier_survives():
    """#1091's lesson: one throw inside `_score_events` emptied the Sports tab.

    The prefetch is now a single point every source depends on, so it gets the
    same treatment the per-source listers already have — best-effort, and the
    healthy path underneath still runs.
    """
    db = _RecordingDB(fail_on_multi_category=True)
    concepts = await population.list_all_concepts(db)

    fell_back = len(db.per_source_reads)
    assert fell_back == 3, f"only {fell_back} sources fell back to their own read"
    assert {c["domain"] for c in concepts} == {"ufc", "f1", "cycling"}


# ---------------------------------------------------------------------------
# 6. The listers still stand alone
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_each_lister_still_runs_its_own_read_when_handed_no_rows():
    """The `/event` adapters, the warmer and four suites call these directly."""
    from app.utils.event_cycling import list_cycling_concepts
    from app.utils.event_f1 import list_f1_gp_concepts
    from app.utils.event_ufc import list_ufc_card_concepts

    for lister, category in (
        (list_ufc_card_concepts, "mma"),
        (list_f1_gp_concepts, "motorsports"),
        (list_cycling_concepts, "cycling"),
    ):
        db = _RecordingDB()
        got = await lister(db, statuses=("upcoming", "live"), limit=12)
        assert len(db.market_reads) == 1, f"{lister.__name__} read nothing"
        assert _categories_named(db.market_reads[0]) == {category}
        assert got, f"{lister.__name__} returned nothing for its own specimen"


@pytest.mark.asyncio
async def test_prefetched_rows_are_consumed_without_a_second_read():
    """The seam itself: rows in, no query out."""
    from app.utils.event_cycling import list_cycling_concepts

    prefetch_db = _RecordingDB()
    prefetched = await population.prefetch_open_markets(prefetch_db, ("cycling",))

    db = _RecordingDB()
    got = await list_cycling_concepts(
        db, statuses=("upcoming", "live"), limit=6, rows=prefetched["cycling"]
    )
    assert db.market_reads == []
    assert got and got[0]["domain"] == "cycling"
