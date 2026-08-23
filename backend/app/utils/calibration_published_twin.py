"""CAL-P078 (#2007, #1912, #1544) — the DB-direct twin of the PUBLISHED curve.

**Gate 0's last blocker, by the R3 pack's own accounting.**

What Gate 0 needs, and what it did not have
--------------------------------------------
Gate 0 asks whether ``/api/calibration`` agrees with the database. Its restated
form is **BOUNDED AGREEMENT within the bank's own instrumented drift** —
equivalence-to-equality was retired, because the published futures half IS a
staged bank and a bank is a census of a slightly older population by design.

CAL-P076 closed three of its four blockers:

* the bound is publishable and published (``staged`` on every payload);
* "no read rail can reach the population" is REFUTED — 462,367 markets and
  821,558 outcomes walked in 96 s at 4,805 markets/s;
* two independent derivations agree to 0.00 pp on 49 cells.

All three are over the **#1912 cohort** population (polymarket / resolved /
quantity + container_member). Gate 0's subject is the **published calibration
curve**, whose population is a different and much heavier predicate — the
virtual-market reconstruction plus nine named filters — and whose futures half
is exactly the staged bank. A DB-direct twin of *that* did not exist. This
module is it.

Where the population comes from, and why that is the SAFE answer
-----------------------------------------------------------------
``_calibration_population_ctes`` is **665 lines / 42.7 KB** of SQL construction.
It is also a PURE FUNCTION returning a STRING: no database, no clock, no side
effect.

This module **imports it and uses its output verbatim**. It does not hand-copy
it, and that is a deliberate call rather than a shortcut:

* **Ruling 009 freezes COMMITS to that file, not reads of it.** Nothing here
  changes a line of it, so ``_main_input_fingerprint()`` does not move, no
  banked unit is invalidated, and the convergence count does not restart. The
  directive granting this work says so directly — *"reader only (no exception
  needed for a reader)"*. ``routes/calibration.py:111`` already imports the same
  function at request time, so this is the established path, not a new one.
* **A hand-mirror of 42.7 KB of SQL is pure risk with no upside.** The twin
  exists to answer "does the published curve match the database". A twin that
  re-implements the population would be answering a *different* question —
  "does my copy of the predicate match the original" — and answering it badly,
  since any transcription slip shows up as a false Gate-0 disagreement that
  costs a queue to chase. **Ruling 094 cuts against the hand-copy, not for it**:
  a derivation that agrees with itself proves nothing, and a hand-mirror is a
  second thing that can silently drift.
* **The mirror is PINNED anyway.** ``test_calibration_published_twin_p078.py``
  asserts the SQL this module builds is byte-identical to the frozen builder's,
  so if anyone ever forks the predicate the guard reds in both directions —
  the same technique CAL-P034 used for ``DECLARED_CENSUS_COLUMNS``.

What IS re-derived here is the half that was actually missing: **the fold from
the population's rows to the published payload's shape**, which lives inside the
frozen module's staged machinery and has never had an independent reader.

The comparison is BOUNDED, never equality
------------------------------------------
:func:`reconcile` compares a DB-direct fold against a served payload and
classifies the result. It refuses to report agreement it cannot justify:

``agrees``
    every compared bucket is within tolerance.
``disagrees``
    at least one bucket is outside it — a real finding.
``unmeasurable``
    the payload does not disclose its own drift, so there is no bound to be
    within. **This is not a pass.** A curve that will not say how old it is
    cannot be checked against a live database, and reporting that as agreement
    is gotcha #53 on the gate itself.

The tolerance is derived from the bank's disclosed drift, not chosen: a census
with ``units_drifted`` of ``units_banked`` has had that share of its slots move
underneath it, so the population it counted differs from today's by roughly that
share and the buckets may differ by up to it. A bank reporting zero drift with
zero unknown gets the tight bound, and that is the only case where a
near-equality reading is earned.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Iterable, Optional

#: Bucket count of the published curve. Ten decile bins, matching
#: ``LEAST(FLOOR(p * 10)::int, 9)`` in the population's own bucketing.
CANONICAL_BUCKETS = 10

#: The floor tolerance, in probability points, for a bank that reports ZERO
#: drift and zero unknown. Not zero: the twin and the payload are read at
#: different instants against a population that moves ~2,099 rows in 35 minutes
#: (measured, #2007), so demanding exact equality would manufacture a
#: disagreement out of the clock. Equivalence-to-equality is retired.
TIGHT_TOLERANCE_PP = 0.5

#: How much tolerance one drifted unit buys. A bank with ``d`` of ``b`` slots
#: drifted counted a population that differs from today's by about ``d/b``, so
#: the bound scales with that share across the full 0-100 pp range.
DRIFT_TOLERANCE_SCALE_PP = 100.0

VERDICT_AGREES = "agrees"
VERDICT_DISAGREES = "disagrees"
VERDICT_UNMEASURABLE = "unmeasurable"

#: **RULING 124 — the MIN-N FLOOR on ``published_only_in_scope``.**
#:
#: An in-scope published bucket carrying ``n <= 2`` outcomes is REPORTED, and
#: can never ALONE force ``disagrees``.
#:
#: Why a floor at all. CAL-P086B made an in-scope published cell with no twin
#: row force ``disagrees``, and that was right — before it, ``agrees`` was
#: reachable over 28.8% of the curve and **a fold that produced nothing read as
#: agreement**, i.e. Gate 5 could be met by a timeout. But it also made the
#: verdict answer to the KEY SET rather than to tolerance, and
#: ``published_only_in_scope`` is **not tolerance-scaled**: one thin bucket
#: forces ``disagrees`` at any bound, including the 100 pp bound the bank's own
#: 128/128 drift currently pins. The tail of a partitioned population is always
#: populated by ones and twos, so a rule that weighs them equally is a rule that
#: can never go green for reasons unrelated to what it grades.
#:
#: Why 2, and why this is not an escape hatch. MEASURED on the 2026-08-22
#: payload (``ARTIFACT-CAL-P087-GATE0-SPLIT-PRE-READ.json``): **159 of the 608
#: in-scope bucket keys carry ``n <= 2``**, so **449 survive the floor** and
#: Gate 0 still reads RED today. ``agrees``-by-timeout stays dead — a fold that
#: produces nothing leaves all 449 unmatched. That property is the ruling's
#: precondition, not a happy accident, and
#: ``test_cal_p088_min_n_floor.py::test_floor_cannot_resurrect_agrees_by_timeout``
#: pins it.
#:
#: The floor is REPORTED, never silent (gotcha #53): suppressed keys are
#: published under ``published_only_in_scope_below_floor`` with their own
#: counts, so "no thin cells" and "thin cells discounted" are distinguishable.
MIN_IN_SCOPE_N_FLOOR = 2

#: The sources the fold's population can ever produce. MEASURED, not assumed
#: (CAL-P086B, 2026-08-21):
#:
#:     SELECT source, count(*) FROM futures_markets WHERE status = 'resolved'
#:     GROUP BY 1  ->  polymarket 569,781 | kalshi 225,274 | datagolf 295
#:
#: The published curve carries **seven** sources. The other four —
#: ``odds_api``, ``odds_api_bookmaker``, ``odds_api_totals``,
#: ``odds_api_spreads`` — are built by separate SQL in
#: ``precompute_calibration.py`` (:3677, :3729, :3778, and the bookmaker path at
#: :3838) over a different population, so ``_calibration_population_ctes()``
#: cannot emit a row for them no matter how long the fold is allowed to run.
#:
#: Measured share, same day, against ``GET /api/calibration``: **203 of 285
#: published cells (71.2%)**, 874 of 1,934 buckets, and 135,102 of 867,101
#: outcomes (15.58%) sit outside this set.
#:
#: This constant exists so that fact is a DECLARATION with a number rather than
#: an emergent property of a SQL file nobody reads to the bottom. Widening it
#: without widening the fold would be a lie in the flattering direction: it
#: would move real gaps from ``published_only_in_scope`` (a disagreement) into
#: ``published_only_out_of_scope`` (a declared limit), which is precisely the
#: move ruling 087 says an exclusion must be mutation-tested against.
FOLD_POPULATION_SOURCES = frozenset({"kalshi", "polymarket", "datagolf"})


#: The DB-direct fold over the canonical population. ``deduped`` is the final
#: published-row CTE the frozen chain ends on, and ``adj_opening_probability`` is
#: the curve price after normalization — the same two names
#: ``routes/calibration.py``'s debug sampler reads, so this counts the rows the
#: published curve actually buckets rather than a lookalike set.
#:
#: Grouped by source and category as well as bucket, because the payload is
#: reported per (source, category) cell and a pooled comparison would let two
#: cells' errors cancel — which is exactly how the 41 pp
#: ``hockey/container_member`` cell hid behind a −6.58 pp pooled gap for months.
#:
#: #2111: ``price_moved`` is the FOURTH grouping dimension, and it is not
#: optional. The producer's own published-bucket query
#: (``precompute_calibration.py:2800``) reads
#: ``SELECT bucket_idx, source, category, price_moved, is_nonexclusive_bundle
#: ... FROM bucketed`` — where ``bucketed`` is ``SELECT * FROM deduped`` — and
#: then merges the bundle rows back on the original FOUR keys in Python, which
#: is why the served payload carries no ``is_nonexclusive_bundle`` field and why
#: FOUR is the whole key. Measured against the live payload 2026-08-23:
#: ``(source, category, bucket_idx)`` yields 1,483 distinct keys over 1,938 rows
#: (**455 collapsed**); adding ``price_moved`` yields **1,938 distinct, 0
#: collapsed**, and adding ``is_nonexclusive_bundle`` on top changes nothing.
#:
#: Folding by three while the payload reports four is not a smaller comparison,
#: it is a WRONG one: it compares a pooled DB rate against whichever single
#: stratum happened to come last in list order. ``deduped`` carries the column,
#: so this costs one grouping dimension and no extra scan.
FOLD_TAIL_SQL = """
SELECT
    d.source                                                    AS source,
    d.category                                                  AS category,
    d.price_moved                                               AS price_moved,
    LEAST(FLOOR(d.adj_opening_probability * 10)::int, 9)        AS bucket_idx,
    COUNT(*)                                                    AS n,
    SUM(CASE WHEN d.is_winner THEN 1 ELSE 0 END)                AS winners,
    SUM(d.adj_opening_probability)                              AS sum_prob
FROM deduped d
GROUP BY 1, 2, 3, 4
ORDER BY 1, 2, 3, 4
"""


def published_population_fold_sql() -> str:
    """The DB-direct twin's one statement, built on the CANONICAL population.

    Imported inside the function rather than at module scope on purpose: the
    frozen module pulls in a large slice of the app, and a top-level import here
    would put that cost — and an import cycle risk — on anything that merely
    wants :func:`reconcile`. The reader pays for it; the pure half does not.
    """
    from app.tasks.precompute_calibration import _calibration_population_ctes

    return "WITH " + _calibration_population_ctes() + FOLD_TAIL_SQL


def normalize_price_moved(value: Any) -> Optional[bool]:
    """Canonicalize a ``price_moved`` value to ``True`` / ``False`` / ``None``.

    #2111. The two sides of this comparison arrive from different transports —
    one from a JSON payload, one from a database driver — and a key is only a
    key if both sides spell it the same way. ``None`` is preserved as a THIRD
    value rather than folded into ``False``: a row whose price-movement is
    unknown is not a row whose price did not move, and collapsing them here
    would be a miniature of the very defect this function exists to fix.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "t", "yes", "y", "1"}:
            return True
        if lowered in {"false", "f", "no", "n", "0"}:
            return False
        return None
    if isinstance(value, (int, float)):
        return bool(value)
    return None


#: The published-side bucket key, and now the DB side's too. ``bucket_idx``
#: alone was the #2111 defect.
BucketKey = tuple[int, Optional[bool]]


def fold_rows_to_cells(
    rows: Iterable[Any],
) -> dict[tuple[str, str], dict[BucketKey, dict]]:
    """``(source, category) -> {(bucket_idx, price_moved): {n, winners, sum_prob}}``.

    Accepts driver rows or plain objects, the same accessor dance the rest of
    this codebase does, because a reader that only works against one row type is
    a reader that cannot be tested without a database.

    #2111: the inner key gained ``price_moved`` and the outer key deliberately
    did NOT. The CELL is still ``(source, category)`` — that is the unit the
    payload reports, the unit ``cells_db`` / ``cells_published`` count, and the
    unit the 41 pp ``hockey/container_member`` finding was expressed in. Pushing
    ``price_moved`` up into the cell key would have doubled those two counts and
    silently changed what every existing reader of them means, which is a second
    behaviour change hiding inside a bug fix.
    """
    cells: dict[tuple[str, str], dict[BucketKey, dict]] = {}
    for row in rows:
        m = dict(row._mapping) if hasattr(row, "_mapping") else dict(vars(row))
        key = (str(m.get("source")), str(m.get("category")))
        bucket = m.get("bucket_idx")
        if bucket is None:
            continue
        bkey: BucketKey = (int(bucket), normalize_price_moved(m.get("price_moved")))
        cells.setdefault(key, {})[bkey] = {
            "n": int(m.get("n") or 0),
            "winners": int(m.get("winners") or 0),
            "sum_prob": float(m.get("sum_prob") or 0.0),
        }
    return cells


def observed_rate(bucket: Mapping[str, Any]) -> Optional[float]:
    """Winners over n, or ``None`` for an empty bucket.

    ``None`` rather than 0.0: an empty bucket has no observed rate, and a 0.0
    there would read as "nothing in this band ever won", which is a claim about
    the world rather than about the sample.
    """
    n = int(bucket.get("n") or 0)
    if n <= 0:
        return None
    return int(bucket.get("winners") or 0) / n


def tolerance_pp(staged: Any) -> Optional[float]:
    """The agreement bound this payload's own disclosure earns.

    ``None`` means UNMEASURABLE — the payload does not say how stale it is, so
    there is no bound and no verdict. Returning a default here would be the
    whole failure this module is guarding against: a gate that passes because
    the thing it is checking declined to be checked.

    Zero drift only counts when every banked unit was CHECKABLE (CAL-P069: six
    unmeasurable units published as ``units_drifted: 0``). An unknown remainder
    is treated as drift, because that is the direction that cannot invent a pass.
    """
    if not isinstance(staged, Mapping) or staged.get("measured") is not True:
        return None
    banked = staged.get("units_banked")
    drifted = staged.get("units_drifted")
    unknown = staged.get("units_drift_unknown")
    if not isinstance(banked, int) or banked <= 0:
        return None
    if not isinstance(drifted, int):
        return None
    moved = drifted + (unknown if isinstance(unknown, int) else 0)
    moved = max(0, min(moved, banked))
    return max(TIGHT_TOLERANCE_PP, DRIFT_TOLERANCE_SCALE_PP * moved / banked)


def reconcile(
    *,
    db_cells: Mapping[tuple[str, str], Mapping[BucketKey, Mapping[str, Any]]],
    published_buckets: Iterable[Mapping[str, Any]],
    staged: Any,
) -> dict[str, Any]:
    """Compare the DB-direct fold against a served payload, within its own bound.

    ``published_buckets`` is the payload's bucket list; each entry is expected to
    carry ``source``, ``category``, ``bucket_idx``, ``price_moved`` and an
    observed rate under either ``actual_rate`` or ``winners``/``n``.

    Every bucket lands in exactly one of four places, and the last two are the
    ones that make the verdict trustworthy:

    * **compared** — present on both sides, difference measured.
    * **outside** — compared and beyond tolerance. Any one of these disagrees.
    * **db_only** / **published_only** — present on one side. **Counted and
      reported, never silently skipped**: a population that has gained or lost a
      whole cell is a bigger finding than a cell that moved two points, and an
      instrument that quietly compares the intersection would report its
      cleanest number on its worst day.

    CAL-P086B: ``published_only`` is SPLIT, and the split changes the verdict
    -------------------------------------------------------------------------
    Counting a published-only bucket was honest but not sufficient, because the
    **verdict** never looked at the count. Measured 2026-08-21: the fold's
    population can produce three of the payload's seven sources, so **203 of
    285 published cells (71.2%)** were landing in ``published_only`` every run
    — and ``agrees`` was still reachable over the remaining 28.8%. ``agrees`` is
    the word a certifier reads; the list underneath it is not.

    So the bucket is split on the distinction gotcha #53 exists to protect:

    * ``published_only_out_of_scope`` — the source is not in
      :data:`FOLD_POPULATION_SOURCES`. The twin could **never** have seen it.
      A declared, counted limit. Does not affect the verdict.
    * ``published_only_in_scope`` — the source IS one the fold covers, and the
      cell still has no twin row. That is the twin and the producer disagreeing
      about the population, and it **forces** ``disagrees``.

    ``published_only`` is retained as the union so an existing reader loses no
    rows. ``db_only`` is deliberately unchanged: the twin seeing MORE than the
    payload is a different and less alarming asymmetry, and folding it into this
    change would be a second behaviour change hiding inside the first.

    CAL-P088 / #2111: the bucket key carries ``price_moved``
    -------------------------------------------------------
    The payload's bucket rows are keyed on FOUR dimensions. This function keyed
    on three, so **455 of 1,937 rows were overwritten** — rate *and* ``n``. Two
    consequences, and the second is the one that made it apply-blocking:

    * the fold's POOLED rate was compared against whichever ``price_moved``
      stratum happened to come last in list order — not a comparison of the same
      quantity;
    * ``scope.outcomes_published`` discarded the overwritten rows' ``n`` and read
      **526,462 against a payload total of 869,978 — 39.5% short** — so every
      percentage in the scope block was computed over a short denominator.

    It was harmless only while ``db_rows`` was 0. The first fold that succeeds is
    exactly the run Gate 5 waits on, so it had to land first.

    Both sides now carry the dimension: :data:`FOLD_TAIL_SQL` groups by
    ``price_moved`` (``deduped`` carries the column — the producer's own query
    selects it) and the key is ``(bucket_idx, price_moved)``. The CELL stays
    ``(source, category)``. ``scope.published_rows_read`` /
    ``published_rows_collapsed`` report the collapse rather than asserting it
    away, because the acceptance criterion is that it can never return SILENTLY.

    CAL-P088 / RULING 124: the MIN-N FLOOR
    --------------------------------------
    An in-scope miss with ``n <= 2`` (:data:`MIN_IN_SCOPE_N_FLOOR`) is reported
    but cannot ALONE force ``disagrees``. See the constant for the measurement
    that makes this safe: 449 of 608 in-scope keys sit above the floor, so a
    fold that produces nothing still reads RED and ``agrees``-by-timeout stays
    dead.
    """
    bound = tolerance_pp(staged)

    published: dict[tuple[str, str], dict[BucketKey, float]] = {}
    # Bucket sizes, kept alongside the rates so the scope block can report a
    # share of OUTCOMES and not only a share of cells. The two differ a lot
    # here — 71.2% of cells are out of scope but only 15.58% of outcomes are —
    # and quoting whichever is more flattering is the failure this block exists
    # to prevent.
    # ``None`` means the payload did not DISCLOSE a size for this bucket, which
    # is not the same fact as a size of zero and must not be discounted by
    # RULING 124's floor. Same asymmetry :func:`tolerance_pp` uses for an
    # undisclosed bank: the unknown direction is the one that cannot invent a
    # pass.
    published_n: dict[tuple[str, str], dict[BucketKey, Optional[int]]] = {}
    # #2111: rows that arrived with a key already present. By construction of
    # the four-dimension key this is 0 against a well-formed payload, and it is
    # COUNTED rather than asserted because the acceptance criterion is that the
    # collapse can never return SILENTLY. An assertion would crash the gate; a
    # counter makes the next occurrence a number in the artifact.
    rows_seen = 0
    rows_collapsed = 0
    for entry in published_buckets:
        if not isinstance(entry, Mapping):
            continue
        bucket = entry.get("bucket_idx")
        if bucket is None:
            continue
        n = entry.get("n")
        rate = entry.get("actual_rate")
        if rate is None:
            winners = entry.get("winners")
            if isinstance(n, int) and n > 0 and isinstance(winners, int):
                rate = winners / n
        if rate is None:
            continue
        key = (str(entry.get("source")), str(entry.get("category")))
        # #2111: the payload's bucket rows are keyed on FOUR dimensions, not
        # three. Keying on three overwrote 455 of 1,937 rows — rate AND n — so
        # the fold's pooled rate was compared against whichever price_moved
        # stratum happened to come last, and scope.outcomes_published dropped
        # the discarded row's n and read 39.5% short of the payload's own total.
        bkey: BucketKey = (int(bucket), normalize_price_moved(entry.get("price_moved")))
        rows_seen += 1
        if bkey in published.get(key, {}):
            rows_collapsed += 1
        published.setdefault(key, {})[bkey] = float(rate)
        published_n.setdefault(key, {})[bkey] = int(n) if isinstance(n, int) else None

    compared: list[dict[str, Any]] = []
    outside: list[dict[str, Any]] = []
    db_only: list[dict[str, Any]] = []
    published_only: list[dict[str, Any]] = []

    for key, buckets in db_cells.items():
        for bucket, stats in buckets.items():
            bucket_idx, price_moved = bucket
            mine = observed_rate(stats)
            theirs = published.get(key, {}).get(bucket)
            if mine is None:
                continue
            if theirs is None:
                db_only.append(
                    {"source": key[0], "category": key[1], "bucket_idx": bucket_idx,
                     "price_moved": price_moved, "n": int(stats.get("n") or 0)}
                )
                continue
            delta_pp = abs(mine - theirs) * 100.0
            record = {
                "source": key[0], "category": key[1], "bucket_idx": bucket_idx,
                "price_moved": price_moved,
                "db_rate": mine, "published_rate": theirs,
                "delta_pp": delta_pp, "n": int(stats.get("n") or 0),
            }
            compared.append(record)
            if bound is not None and delta_pp > bound:
                outside.append(record)

    published_only_in_scope: list[dict[str, Any]] = []
    published_only_out_of_scope: list[dict[str, Any]] = []
    sources_out_of_scope: set[str] = set()
    outcomes_published = 0
    outcomes_out_of_scope = 0
    outcomes_compared = 0

    # RULING 124: the in-scope misses that are thick enough to speak for
    # themselves, and the thin ones that are reported but cannot force a
    # verdict alone.
    published_only_in_scope_below_floor: list[dict[str, Any]] = []
    outcomes_in_scope_below_floor = 0

    for key, buckets in published.items():
        for bucket in buckets:
            bucket_idx, price_moved = bucket
            n_known = published_n.get(key, {}).get(bucket)
            n_here = n_known or 0
            outcomes_published += n_here
            in_scope = key[0] in FOLD_POPULATION_SOURCES
            if not in_scope:
                sources_out_of_scope.add(key[0])
                outcomes_out_of_scope += n_here
            if bucket not in db_cells.get(key, {}):
                record = {
                    "source": key[0],
                    "category": key[1],
                    "bucket_idx": bucket_idx,
                    "price_moved": price_moved,
                    "n": n_here,
                }
                published_only.append(record)
                if not in_scope:
                    published_only_out_of_scope.append(record)
                else:
                    published_only_in_scope.append(record)
                    # RULING 124. Note the record lands in BOTH lists: the union
                    # ``published_only_in_scope`` keeps every row so no reader
                    # loses one, and the below-floor list names the subset the
                    # verdict discounts. A floor that removed rows from the
                    # reported set would be indistinguishable from a fold that
                    # found them.
                    #
                    # ``n_known is not None`` is load-bearing: a bucket whose
                    # size the payload never disclosed is NOT a thin bucket, and
                    # discounting it would let an undisclosed population buy
                    # silence — the exact move ``tolerance_pp`` refuses one level
                    # up. Undisclosed counts toward the verdict.
                    if n_known is not None and n_known <= MIN_IN_SCOPE_N_FLOOR:
                        published_only_in_scope_below_floor.append(record)
                        outcomes_in_scope_below_floor += n_here
            else:
                outcomes_compared += n_here

    # RULING 124: only the misses ABOVE the floor can force a verdict.
    in_scope_above_floor = (
        len(published_only_in_scope) - len(published_only_in_scope_below_floor)
    )

    if bound is None:
        verdict = VERDICT_UNMEASURABLE
    elif outside or in_scope_above_floor > 0:
        # An in-scope published cell with no twin row is the twin and the
        # producer disagreeing about the POPULATION. Before CAL-P086B this was
        # counted and then ignored by the verdict.
        #
        # RULING 124 narrows WHICH of them may force it — never whether they are
        # reported. ``n <= 2`` is discounted because the rule is not
        # tolerance-scaled and the tail of any partitioned population is thin by
        # construction; 449 of the 608 in-scope keys measured on 2026-08-22 sit
        # above the floor, so this cannot resurrect ``agrees``-by-timeout.
        verdict = VERDICT_DISAGREES
    else:
        verdict = VERDICT_AGREES

    scope = {
        "fold_population_sources": sorted(FOLD_POPULATION_SOURCES),
        "sources_out_of_scope": sorted(sources_out_of_scope),
        "buckets_published": sum(len(b) for b in published.values()),
        "buckets_compared": len(compared),
        "buckets_out_of_scope": len(published_only_out_of_scope),
        "buckets_in_scope_missing": len(published_only_in_scope),
        # RULING 124. Both numbers, always: the floor's whole legitimacy is that
        # the discounted set is visible beside the deciding one.
        "min_in_scope_n_floor": MIN_IN_SCOPE_N_FLOOR,
        "buckets_in_scope_missing_below_floor": len(
            published_only_in_scope_below_floor
        ),
        "buckets_in_scope_missing_above_floor": in_scope_above_floor,
        "outcomes_in_scope_missing_below_floor": outcomes_in_scope_below_floor,
        # #2111. ``published_rows_read`` is the payload's own row count as this
        # function saw it and ``published_rows_collapsed`` is how many of them
        # shared a four-dimension key. The pair is what makes the fix checkable
        # from the artifact alone: a non-zero collapse is now a REPORTED number
        # instead of a silent overwrite of a rate and an n.
        "published_rows_read": rows_seen,
        "published_rows_collapsed": rows_collapsed,
        "outcomes_published": outcomes_published,
        "outcomes_out_of_scope": outcomes_out_of_scope,
        "pct_published_outcomes_in_scope": (
            round(100.0 * (outcomes_published - outcomes_out_of_scope) / outcomes_published, 4)
            if outcomes_published
            else None
        ),
    }

    return {
        "verdict": verdict,
        # Named even when it is None, so a reader never has to infer why a
        # verdict came out unmeasurable.
        "tolerance_pp": bound,
        "compared": len(compared),
        "outside": outside,
        "worst_delta_pp": max((r["delta_pp"] for r in compared), default=None),
        "db_only": db_only,
        # The union, retained so an existing reader loses no rows.
        "published_only": published_only,
        # ... and the split, which is what the verdict now reads.
        "published_only_in_scope": published_only_in_scope,
        "published_only_out_of_scope": published_only_out_of_scope,
        # RULING 124: the discounted subset, reported under its own key. It is a
        # SUBSET of ``published_only_in_scope``, not a fourth disjoint bucket —
        # the union above still carries every row.
        "published_only_in_scope_below_floor": published_only_in_scope_below_floor,
        "cells_db": len(db_cells),
        "cells_published": len(published),
        # Always present, including on an unmeasurable run: a reader must never
        # have to infer coverage from a missing key.
        "scope": scope,
    }
