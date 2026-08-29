#!/usr/bin/env python3
"""CAL-P126 — how big is 16-CAL on the WHOLE curve, and what does it do to 1.89?

Ruling 134 note: this is a read-only instrument. It writes nothing to the
database, it does not re-implement the producer's population — every mode below
drives ``_calibration_population_ctes`` itself — and ``git diff origin/master --
backend/app frontend`` is empty on the branch that carries it. Ruling 009
freezes commits to ``precompute_calibration.py``; this file only imports it.

It is option **(a) MEASURE FIRST** of ``0-PHANTOM`` in ``YOUR-TURN.md``, which
is the written default if Alex does not answer, and he has not.

WHAT 16-CAL IS
--------------
``deduped`` is the CTE the producer's own docstring calls *"the final published
population"* and it is ``SELECT ro.* FROM normalized ro`` — one row per outcome
by construction. CAL-P125 measured ``polymarket/basketball`` publishing 13,116
rows standing on 7,419 distinct outcomes (43.44% phantom) and ``cricket`` at
12.85%, and isolated the cause by differential:

    vm_stats   GROUP BY vm_id, source, category, is_grouped, mutually_exclusive
    clean_vms  SELECT * FROM vm_stats WHERE ...
    ranked_outcomes  JOIN clean_vms cv ON cv.vm_id = vm.vm_id
                                      AND cv.source = vm.source

Five grouping columns, two join columns. Every extra ``clean_vms`` row for a
``(vm_id, source)`` re-emits that whole virtual question's outcomes.

The comment sitting twenty lines below that join says, in the file's own words,
*"``vm_stats`` GROUPs BY ``(vm_id, source)``, ``clean_vms`` JOINs on both"*.
That is what the author believed the grain was. It is not the grain.

WHY A NEW FILE RATHER THAN A FLAG ON THE WHOLE-VM RAIL
--------------------------------------------------------
``calibration_whole_vm_fold.py --phantom`` already counts phantom rows for one
cell, exactly, and this file uses it for precisely that. But CAL-P125-1 asks two
questions that mode cannot answer:

  * **how much of the WHOLE curve is affected** — 913,851 outcomes over 103
    cells, where the whole-vm rail costs a Stage A roster read per cell and
    ``polymarket/baseball`` alone is a ~20 minute fold; and
  * **what the published 1.89 becomes** — which needs de-duplicated BUCKET
    aggregates, not a row count.

So there are three modes, cheapest first, and each one narrows what the next has
to pay for.

THE THREE MODES
---------------
``--scan`` — **the free half of the answer, and it is most of the answer.**
The fan-out is a fact about ``clean_vms``, and ``clean_vms`` is ``vm_stats``
filtered. The filter only ever REMOVES rows, so a virtual question whose markets
all agree on ``(category, is_grouped, mutually_exclusive)`` cannot fan out no
matter what the filter does — one combination in, at most one row out. Counting
those combinations needs only ``virtual_market``, which is where Stage A stops,
so a cell costs one query of a few seconds instead of a fold. A cell that scans
clean is **provably zero-phantom** and never needs to be folded at all; a cell
that scans dirty gets an upper bound and a place in the queue.

``--cell`` — the exact answer for one cell: per ``(bucket_idx, source, category,
price_moved)``, the as-shipped ``(n, winners, sum_prob)`` and the de-duplicated
ones, plus a COHERENCE census (below). Runs either straight through the cell's
own chain (``--direct``, cheap cells) or over the whole-vm rail's frozen roster
(big cells). The two paths emit the same JSON and can be run against each other.

``--headline`` — substitutes those cells into ``/api/calibration``'s OWN bucket
list and recomputes ``mce_closing_line`` the way ``_cohort_mce`` does. The
payload publishes every bucket it aggregated, so the headline is reproducible
from it exactly (verified: 1.89 and 1.54 both to the published digit), which
means a cell measured today can be substituted without re-measuring the other
102.

THE COHERENCE CENSUS, AND WHY THE ANSWER IS NOT "JUST COUNT DISTINCT"
------------------------------------------------------------------------
It is tempting to say the de-duplicated bucket is ``COUNT(DISTINCT
outcome_id)``. That is only right if the copies of an outcome are the SAME row,
and they are not obviously the same row: the ``clean_vms`` rows that produce
them carry different ``eligible`` / ``has_winner`` / ``total_outcomes``
aggregates, and ``eligible`` is read downstream by ``mode_prices`` (``eligible
>= 3``) and by the field-completeness gate. Two copies of one outcome can in
principle be published at two prices, in two buckets, on two sides of
``price_moved``.

So this file does not assume. It attributes each published row ``1/copies`` of
an outcome — which is exactly ``COUNT(DISTINCT outcome_id)`` when the copies
agree, and a defensible split when they do not — and it separately COUNTS the
rows whose copies disagree on bucket, on price, on ``is_winner`` and on
``price_moved``. If those counts are zero the de-duplication is a pure
re-weighting and the headline delta below is exact. If they are not zero, the
curve publishes one outcome at two prices, which is a second and worse finding,
and the census is how it gets found rather than assumed away.

WHAT THIS FILE DOES NOT CLAIM
-------------------------------
* **It does not fix anything.** No ruling-009 exception is taken and no
  candidate fix is written. The output is a number Alex can rule on.
* **It does not reach the four ``odds_api*`` sources**, and it says so by name
  rather than by omission. ``futures_markets`` holds only ``polymarket``,
  ``kalshi`` and ``datagolf`` (measured: 602,303 / 245,604 / 315 resolved), so
  the 137,829 outcomes those four sources contribute — 15.1% of the curve —
  come from a different chain that has no ``clean_vms`` in it and cannot carry
  this defect. ``--scan`` prints that split rather than leaving the reader to
  infer that a source with no rows was measured.
* **Scoping ``market_info`` to a category is not free** — a group or event whose
  markets span two categories is counted short and can fall below the ``>= 3``
  gate. That is CAL-P124-2, closed, measured at <= 0.10% of ``basketball`` and
  0.50% of ``baseball`` and provably zero on ``cricket``, and
  ``calibration_whole_vm_fold.py --bound`` re-measures it per cell. It is stated
  here because every mode in this file inherits it.

Usage::

    # the whole curve, cheap — every cell, provably-clean ones named as such
    python3 backend/scripts/calibration_phantom_curve.py --scan \\
        --out artifacts/cal-p126/scan.json

    # one cell exactly, straight through its own chain
    python3 backend/scripts/calibration_phantom_curve.py --cell \\
        --source polymarket --category cricket --direct \\
        --out artifacts/cal-p126/cell-polymarket-cricket.json

    # one big cell, over the whole-vm rail's frozen roster
    python3 backend/scripts/calibration_phantom_curve.py --cell \\
        --source polymarket --category basketball \\
        --roster-cache artifacts/cal-p126/roster-basketball.json \\
        --out artifacts/cal-p126/cell-polymarket-basketball.json

    # what it does to 1.89
    python3 backend/scripts/calibration_phantom_curve.py --headline \\
        --payload artifacts/cal-p126/payload.json \\
        --cells artifacts/cal-p126/cell-*.json
"""

from __future__ import annotations

import argparse
import glob
import importlib.util
import json
import sys
import time
import urllib.request
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS.parent))

from app.tasks.precompute_calibration import (  # noqa: E402
    VM_ROSTER_IS_GROUPED_PARAM,
    VM_ROSTER_MARKET_IDS_PARAM,
    VM_ROSTER_MARKET_INFO_EXTRA,
    VM_ROSTER_VM_IDS_PARAM,
    _calibration_population_ctes,
)


def _load(name: str):
    """Load a sibling script WITHOUT registering it in ``sys.modules``.

    CAL-P123's convention and CAL-P125's warning: these modules mutate shared
    state at import time (``calibration_family_fold`` adds four dimensions to
    ``cce.DIMENSIONS``, ``calibration_whole_vm_fold`` adds ``publegs``), so a
    module left in ``sys.modules`` makes those mutations visible to every other
    test in the pytest process.
    """
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


#: The whole-vm rail, reached whole rather than re-implemented. This file needs
#: three things from it — Stage A with its roster cache, ``plan_units``-backed
#: unit planning, and the roster-array renderers — and every one of them carries
#: a guard suite there that would not travel with a copy.
wvf = _load("calibration_whole_vm_fold")
cce = wvf.cce


# ---------------------------------------------------------------------------
# MODE 1 — the free scan: which cells CANNOT be phantom
# ---------------------------------------------------------------------------
#: One row per cell: how many of its virtual questions carry more than one
#: ``clean_vms`` grain.
#:
#: ``combos`` counts the DISTINCT ``(category, is_grouped, mutually_exclusive)``
#: triples inside a ``(vm_id, source)`` — exactly the three columns ``vm_stats``
#: groups by and ``ranked_outcomes`` does not join on. It is computed over
#: ``virtual_market`` rather than ``vm_stats``, which is the whole economy of
#: this mode: ``vm_stats`` joins ``futures_outcomes`` and is the expensive step,
#: while ``virtual_market`` is where Stage A already stops.
#:
#: **The direction of the inequality is what makes it usable.** ``clean_vms``
#: filters ``vm_stats``; a filter cannot create a grain. So
#: ``combos == 1`` ⇒ at most one ``clean_vms`` row ⇒ **zero phantom, proved**,
#: and ``combos > 1`` is an upper bound that the exact mode has to settle. A
#: clean scan is therefore a real all-clear and a dirty one is only a queue
#: position — the asymmetry is deliberate and is the reason this mode is
#: allowed to be cheap (CAL-P124's lesson 8: an instrument that reports a
#: derivative has said nothing about the level, so this one reports which side
#: of zero the level is on and refuses to guess the rest).
#:
#: The three columns are also counted SEPARATELY, because CAL-P125 isolated
#: ``mutually_exclusive`` as the only one that fans out on one unit of one cell
#: and a claim measured on one unit of one cell is a hypothesis (lesson 1).
SCAN_TAIL = """
, vm_combo AS (
    SELECT vm_id, source, COUNT(*) AS markets,
           COUNT(DISTINCT (category, is_grouped, mutually_exclusive)) AS combos,
           COUNT(DISTINCT mutually_exclusive) AS mexc,
           COUNT(DISTINCT category) AS catc,
           COUNT(DISTINCT is_grouped) AS grpc
    FROM virtual_market GROUP BY vm_id, source
)
SELECT COUNT(*) AS vms,
       COUNT(*) FILTER (WHERE combos > 1) AS multi_vms,
       COALESCE(SUM(markets), 0) AS markets,
       COALESCE(SUM(markets) FILTER (WHERE combos > 1), 0) AS multi_markets,
       COALESCE(SUM(combos), 0) AS combo_rows,
       COUNT(*) FILTER (WHERE mexc > 1) AS mex_vms,
       COUNT(*) FILTER (WHERE catc > 1) AS cat_vms,
       COUNT(*) FILTER (WHERE grpc > 1) AS grp_vms
FROM vm_combo
"""

#: The cells to scan, read from the database rather than from a list in this
#: file. A hard-coded cell list is the routing accident that skipped
#: ``kalshi/golf`` across four handoffs (CAL-P125), and the board's 14 cells are
#: not the curve's 103.
CELL_LIST_SQL = """
SELECT fm.source, COALESCE(fm.llm_sport_category, 'uncategorized') AS category,
       COUNT(*) AS resolved_markets
FROM futures_markets fm
WHERE fm.status = 'resolved'
GROUP BY 1, 2
ORDER BY 3 DESC
"""

#: The sources ``futures_markets`` actually holds. Named rather than inferred:
#: the four ``odds_api*`` sources publish 137,829 outcomes through a DIFFERENT
#: chain, and a scan that simply returned no rows for them would read as "clean"
#: when the honest word is "out of scope" (gotcha #53 — an empty result is a
#: response shape, not an absence).
FUTURES_SOURCES = ("polymarket", "kalshi", "datagolf")


def cell_list() -> list[tuple[str, str, int]]:
    r = cce.db_query(CELL_LIST_SQL, limit=500)
    if r["row_count"] >= 500 or bool(r.get("truncated")):
        raise RuntimeError("cell list hit the row cap — the curve grew a tail "
                           "this query cannot see (gotcha: the 1000-row cap "
                           "truncates silently)")
    return [(str(s), str(c), int(n)) for s, c, n in r["rows"]]


def scan_sql(source: str, category: str) -> str:
    pop = _calibration_population_ctes(
        market_info_extra=(
            f"AND fm.source = '{source}' "
            f"AND COALESCE(fm.llm_sport_category, 'uncategorized') = '{category}'"
        )
    )
    return cce._strip_sql_comments("WITH " + pop + SCAN_TAIL)


def scan_cell(source: str, category: str) -> dict:
    t0 = time.time()
    try:
        r = cce.db_query(scan_sql(source, category), limit=5)
    except cce.QueryTimeout as exc:
        # NOT retried and NOT silently skipped. The scan's whole value is that a
        # clean cell is PROVED clean; a cell nobody could scan is a hole in the
        # proof and has to be visible as one.
        return {"source": source, "category": category, "status": "SCAN_TIMEOUT",
                "secs": round(time.time() - t0, 1), "detail": str(exc)[:200]}
    row = {c: int(v or 0) for c, v in zip(r["columns"], r["rows"][0])}
    row.update(source=source, category=category, status="ok",
               secs=round(time.time() - t0, 1))
    row.update(_scan_derived(row))
    return row


def _scan_derived(row: dict) -> dict:
    """The scan's verdict and its two SIZE figures — and only one is a proof.

    **``phantom_possible`` is the whole point and it is exact in one direction.**
    ``combos == 1`` means at most one ``clean_vms`` row means zero phantom, and
    no measurement can overturn it. ``combos > 1`` means the exact mode has to
    settle it.

    **Neither percentage is an upper bound on the phantom ROW rate, and an
    earlier version of this file published one that claimed to be.** It reported
    ``(combo_rows - vms) / combo_rows`` — a rate over virtual QUESTIONS — and
    the exact folds went straight through it:

        cell                    questions fanning     actual phantom rows
        kalshi/hockey                    25.21%              47.08%
        polymarket/basketball            13.22%              43.44%
        polymarket/cricket               16.87%              12.85%

    Two of three EXCEED it, and not by rounding. The reason is a real finding
    rather than an arithmetic slip: **the questions that fan out are
    systematically the big ones.** A virtual question carries two
    ``mutually_exclusive`` values precisely when it bundles claims of different
    shapes — a game group holding a moneyline and a player prop — and that is
    also what makes it large. On ``basketball``, 13.2% of the questions hold
    81.7% of the markets.

    So this returns the two figures under names that say what they count, and
    the docstring says which one tracks the damage (``fanned_market_pct``, which
    over-stated it on all three exact cells and is the closer estimate) rather
    than dressing either as a guarantee. That is CAL-P124's lesson 8 read the
    right way round: a warning that fires has not sized anything.
    """
    return {
        "phantom_possible": row["multi_vms"] > 0,
        "fanned_question_pct": (round(row["multi_vms"] / row["vms"] * 100, 2)
                                if row["vms"] else 0.0),
        "fanned_market_pct": (round(row["multi_markets"] / row["markets"] * 100, 2)
                              if row["markets"] else 0.0),
    }


# ---------------------------------------------------------------------------
# MODE 2 — the exact per-cell bucket delta
# ---------------------------------------------------------------------------
#: The published population, bucketed the way the producer buckets it, counted
#: twice: once as shipped and once with each outcome worth 1.
#:
#: ``bucket_idx`` is copied from the producer verbatim — ``LEAST(FLOOR(
#: adj_opening_probability * 10)::int, 9)`` — and the grouping key is the
#: producer's own ``(bucket_idx, source, category, price_moved)``, which is what
#: the served ``buckets`` list is keyed on. That is not tidiness: it is what
#: lets ``--headline`` substitute a cell into the payload's own aggregate
#: instead of rebuilding the other 102 cells.
#:
#: ``copies`` is computed over the same ``bucketed`` set, so ``1.0 / c.copies``
#: sums to exactly 1 per outcome across whatever buckets its copies land in.
#: When the copies agree (the coherence columns are all zero) that is
#: ``COUNT(DISTINCT outcome_id)`` per bucket, exactly; when they do not, it is a
#: proportional split AND the disagreement is reported next to it.
CELL_TAIL = """
, bucketed AS (
    SELECT outcome_id, source, category, price_moved, is_winner,
           adj_opening_probability::float AS p,
           LEAST(FLOOR(adj_opening_probability * 10)::int, 9) AS bucket_idx
    FROM deduped
),
copies AS (
    SELECT outcome_id, COUNT(*) AS copies,
           COUNT(DISTINCT bucket_idx) AS nb,
           COUNT(DISTINCT p) AS np,
           COUNT(DISTINCT is_winner) AS nw,
           COUNT(DISTINCT price_moved) AS nm
    FROM bucketed GROUP BY outcome_id
)
SELECT b.bucket_idx, b.source, b.category, b.price_moved,
       COUNT(*) AS n_ship,
       COALESCE(SUM(CASE WHEN b.is_winner THEN 1 ELSE 0 END), 0) AS w_ship,
       COALESCE(SUM(b.p), 0) AS s_ship,
       COALESCE(SUM(1.0 / c.copies), 0) AS n_dedup,
       COALESCE(SUM(CASE WHEN b.is_winner THEN 1.0 ELSE 0.0 END / c.copies), 0) AS w_dedup,
       COALESCE(SUM(b.p / c.copies), 0) AS s_dedup,
       COUNT(*) FILTER (WHERE c.copies > 1) AS rows_duplicated,
       COUNT(*) FILTER (WHERE c.nb > 1) AS incoherent_bucket,
       COUNT(*) FILTER (WHERE c.np > 1) AS incoherent_price,
       COUNT(*) FILTER (WHERE c.nw > 1) AS incoherent_winner,
       COUNT(*) FILTER (WHERE c.nm > 1) AS incoherent_price_moved
FROM bucketed b
JOIN copies c ON c.outcome_id = b.outcome_id
GROUP BY 1, 2, 3, 4
ORDER BY 1, 2, 3, 4
"""

#: The four columns that key a published bucket. The order is the producer's.
BUCKET_KEY = ("bucket_idx", "source", "category", "price_moved")

#: The six measured quantities. Three are the payload's; three are their
#: de-duplicated twins.
MEASURES = ("n_ship", "w_ship", "s_ship", "n_dedup", "w_dedup", "s_dedup")

#: The four ways two copies of one outcome can disagree.
COHERENCE = ("incoherent_bucket", "incoherent_price", "incoherent_winner",
             "incoherent_price_moved")


def _row_to_bucket(columns, values) -> dict:
    d = dict(zip(columns, values))
    out = {
        "bucket_idx": int(d["bucket_idx"]),
        "source": str(d["source"]),
        "category": str(d["category"]),
        "price_moved": bool(d["price_moved"]),
    }
    for m in MEASURES:
        out[m] = float(d[m] or 0)
    for m in ("rows_duplicated",) + COHERENCE:
        out[m] = int(d[m] or 0)
    return out


def _merge(into: dict, rows: list[dict]) -> None:
    """Accumulate bucket rows onto their key. Units partition virtual questions
    and a market belongs to exactly one, so per-unit rows simply ADD."""
    for r in rows:
        k = tuple(r[c] for c in BUCKET_KEY)
        slot = into.get(k)
        if slot is None:
            slot = into[k] = {c: r[c] for c in BUCKET_KEY}
            for m in MEASURES + ("rows_duplicated",) + COHERENCE:
                slot[m] = 0 if m not in MEASURES else 0.0
        for m in MEASURES:
            slot[m] += r[m]
        for m in ("rows_duplicated",) + COHERENCE:
            slot[m] += r[m]


def cell_direct(source: str, category: str) -> tuple[dict, str]:
    """The cell's own chain, one statement. Ground truth where it fits."""
    pop = _calibration_population_ctes(
        market_info_extra=(
            f"AND fm.source = '{source}' "
            f"AND COALESCE(fm.llm_sport_category, 'uncategorized') = '{category}'"
        )
    )
    sql = cce._strip_sql_comments("WITH " + pop + CELL_TAIL)
    r = cce.db_query(sql, limit=cce.ROW_CAP)
    if bool(r.get("truncated")) or r["row_count"] >= cce.ROW_CAP:
        raise RuntimeError("cell bucket read hit the row cap")
    acc: dict = {}
    _merge(acc, [_row_to_bucket(r["columns"], v) for v in r["rows"]])
    return acc, "direct"


def cell_over_roster(source: str, category: str, roster_buckets: int,
                     buckets: int, cache: str | None) -> tuple[dict, str]:
    """The whole-vm rail: freeze the generation once, replay it per unit.

    Used where ``--direct`` cannot finish. The units come from the producer's
    own ``plan_units`` through :mod:`calibration_whole_vm_fold`, so a ``vm_id``
    is never split — which matters here more than anywhere, because splitting a
    virtual question would split its duplicate copies apart and the phantom
    would vanish into the chunk boundary.
    """
    global _ROSTER_CACHE
    rows, _secs, _how = wvf.load_or_freeze(source, category, roster_buckets, cache)
    _ROSTER_CACHE = rows
    assignment = {r.market_id: (r.vm_id, r.is_grouped) for r in rows}
    units = wvf.plan_units(rows, buckets=buckets)
    tpl = cce._strip_sql_comments(
        "WITH " + _calibration_population_ctes(
            frozen_vm_roster=True,
            market_info_extra=VM_ROSTER_MARKET_INFO_EXTRA) + CELL_TAIL)

    acc: dict = {}
    t0 = time.time()
    for i, unit in enumerate(units):
        _merge(acc, _unit_rows(tpl, unit, assignment, buckets, 0))
        if i % 16 == 0:
            print(f"    cell buckets [{i + 1}/{len(units)}] "
                  f"({time.time() - t0:.0f}s)", file=sys.stderr, flush=True)
    return acc, "roster"


def _unit_rows(tpl: str, unit, assignment: dict, buckets: int, depth: int) -> list[dict]:
    mk = list(unit.market_ids)
    sql = (tpl
           .replace(f":{VM_ROSTER_MARKET_IDS_PARAM}", wvf._bigint_array(mk))
           .replace(f":{VM_ROSTER_VM_IDS_PARAM}",
                    wvf._text_array(assignment[x][0] for x in mk))
           .replace(f":{VM_ROSTER_IS_GROUPED_PARAM}",
                    wvf._bool_array(assignment[x][1] for x in mk)))
    try:
        if len(sql) > cce.MAX_SQL_CHARS:
            raise cce.QueryTimeout(f"SQL {len(sql)} chars over the cap")
        r = cce.db_query(sql, limit=cce.ROW_CAP)
        if bool(r.get("truncated")) or r["row_count"] >= cce.ROW_CAP:
            raise cce.QueryTimeout("reply at the row cap")
        return [_row_to_bucket(r["columns"], v) for v in r["rows"]]
    except cce.QueryTimeout as exc:
        if len(unit.vm_ids) <= 1:
            raise RuntimeError(
                f"virtual question {unit.vm_ids[0] if unit.vm_ids else '?'} "
                f"({len(unit.market_ids)} markets) does not fit in one statement "
                f"and MUST NOT be split — splitting a vm_id would split its own "
                f"duplicate copies apart and report the phantom as absent. "
                f"Cause: {exc}") from exc
        if depth > 8:
            raise RuntimeError(
                f"unit {unit.index} still failing at partition depth {depth}: {exc}")
        mine = {v for v in unit.vm_ids}
        sub_rows = [r for r in _ROSTER_CACHE if r.vm_id in mine]
        print(f"      unit {unit.index} re-planned at {buckets * 2} buckets: {exc}",
              file=sys.stderr, flush=True)
        out: list[dict] = []
        for sub in wvf.plan_units(sub_rows, buckets=buckets * 2):
            out.extend(_unit_rows(tpl, sub, assignment, buckets * 2, depth + 1))
        return out


#: Set by :func:`cell_over_roster` before it plans, read by the re-plan branch
#: of :func:`_unit_rows`. A module global rather than a parameter because the
#: recursion is depth-first over an exact refinement and threading the full
#: roster through every frame buys nothing; it holds plain ``RosterRow`` values,
#: never a live ORM row (gotcha #6).
_ROSTER_CACHE: list = []


def cell_report(acc: dict, source: str, category: str, how: str) -> dict:
    buckets = sorted(acc.values(), key=lambda b: tuple(b[c] for c in BUCKET_KEY))
    n_ship = sum(b["n_ship"] for b in buckets)
    n_dedup = sum(b["n_dedup"] for b in buckets)
    coh = {m: sum(b[m] for b in buckets) for m in COHERENCE}
    return {
        "cell": f"{source}/{category}",
        "source": source,
        "category": category,
        "path": how,
        "published_rows": int(round(n_ship)),
        "distinct_outcomes": int(round(n_dedup)),
        "phantom_rows": int(round(n_ship - n_dedup)),
        "phantom_pct": round((n_ship - n_dedup) / n_ship * 100, 2) if n_ship else 0.0,
        "rows_duplicated": sum(b["rows_duplicated"] for b in buckets),
        "coherence": coh,
        "coherent": all(v == 0 for v in coh.values()),
        "buckets": buckets,
    }


# ---------------------------------------------------------------------------
# MODE 3 — what it does to the published number
# ---------------------------------------------------------------------------
def cohort_mce(buckets, price_moved: bool) -> float | None:
    """``_cohort_mce`` from the producer, over a list of published buckets.

    Re-stated here rather than imported because the producer's copy is a closure
    inside a 400-line builder. It is pinned by a guard test that reproduces the
    SERVED ``mce_closing_line`` and ``mce_opening_price`` from the SERVED
    ``buckets`` — so if the producer's aggregation ever changes shape, the test
    goes red against production rather than this file drifting quietly.

    Note what it is: an UNWEIGHTED mean over bucket indices of the pooled
    |actual - predicted|. Ten buckets, each pooled over every source and
    category. That is why one cell's re-weighting can move the headline at all,
    and why the move is not proportional to the cell's size.

    **The comparison is ``!=`` against the RAW value, never ``bool(...)``, and
    that is not defensive style.** ``price_moved`` is NULL on 890 of the served
    payload's 1,963 buckets, carrying exactly 137,829 outcomes — the four
    ``odds_api*`` sources to the row. The producer's ``b.get("price_moved") !=
    pred`` puts a NULL bucket in NEITHER cohort; coercing with ``bool()`` puts
    every one of them in the ``False`` cohort and drags ``mce_opening_price``
    from 1.54 to 1.06. That was written the coercing way here first and the
    served-payload test below is what caught it.

    It is also the reason the headline delta is worth computing at all: the
    published 1.89 is an average over the futures half ONLY, which is exactly
    the half that carries 16-CAL.
    """
    agg: dict[int, dict] = {}
    for b in buckets:
        if b.get("price_moved") != price_moved:
            continue
        a = agg.setdefault(int(b["bucket_idx"]), {"n": 0.0, "w": 0.0, "s": 0.0})
        a["n"] += float(b["n"])
        a["w"] += float(b["winners"])
        a["s"] += float(b["sum_prob"])
    if not agg:
        return None
    total = 0.0
    for v in agg.values():
        if v["n"] == 0:
            continue
        total += abs(v["w"] / v["n"] - v["s"] / v["n"])
    return round(total / len(agg) * 100, 2)


def substitute(payload_buckets: list[dict], cells: list[dict]) -> tuple[list[dict], dict]:
    """Replace each measured cell's buckets with their de-duplicated twins.

    **The substitution is a RATIO, not a replacement, and that is load-bearing.**
    The whole-vm rail reproduces a cell to within a fraction of a percent, not
    exactly (CAL-P125 measured -0.14% on ``basketball``, +0.00% on ``cricket``),
    and the category-scoping residual above is real if small. Substituting the
    rail's absolute numbers would fold that shortfall into the headline delta
    and report rail error as phantom error. Scaling the PAYLOAD's own bucket by
    the rail's ``dedup / ship`` ratio cancels any per-bucket factor common to
    both measurements, which is exactly what the rail's shortfall is.

    A bucket the rail measured and the payload does not publish is reported, not
    dropped: it means the two populations disagree about which buckets exist,
    which is a bigger finding than the ratio.
    """
    ratios: dict[tuple, dict] = {}
    for cell in cells:
        for b in cell["buckets"]:
            k = (int(b["bucket_idx"]), b["source"], b["category"],
                 b["price_moved"])
            ratios[k] = b

    out, stats = [], {"substituted": 0, "untouched": 0, "rail_only": [],
                      "cells": [c["cell"] for c in cells]}
    seen = set()
    for pb in payload_buckets:
        # RAW, not ``bool(...)`` — a NULL ``price_moved`` bucket is in neither
        # cohort and must not be silently keyed onto the False one.
        k = (int(pb["bucket_idx"]), pb["source"], pb["category"],
             pb["price_moved"])
        r = ratios.get(k)
        if r is None:
            out.append({"bucket_idx": pb["bucket_idx"], "price_moved": pb["price_moved"],
                        "n": float(pb["n"]), "winners": float(pb["winners"]),
                        "sum_prob": float(pb["sum_prob"])})
            stats["untouched"] += 1
            continue
        seen.add(k)
        stats["substituted"] += 1

        def scale(measure_ship: str, measure_dedup: str, published: float) -> float:
            ship = r[measure_ship]
            return published * (r[measure_dedup] / ship) if ship else 0.0

        out.append({
            "bucket_idx": pb["bucket_idx"], "price_moved": pb["price_moved"],
            "n": scale("n_ship", "n_dedup", float(pb["n"])),
            # ``winners`` scales on the WINNER ratio, not the row ratio: a bucket
            # whose duplicated rows are disproportionately winners moves its
            # actual rate, and that movement is the entire mechanism by which
            # de-duplication can change a calibration error rather than just an n.
            "winners": scale("w_ship", "w_dedup", float(pb["winners"])),
            "sum_prob": scale("s_ship", "s_dedup", float(pb["sum_prob"])),
        })
    for k in ratios:
        if k not in seen:
            stats["rail_only"].append(list(k))
    return out, stats


def headline(payload: dict, cells: list[dict]) -> dict:
    published = [{"bucket_idx": b["bucket_idx"], "price_moved": b["price_moved"],
                  "n": float(b["n"]), "winners": float(b["winners"]),
                  "sum_prob": float(b["sum_prob"])} for b in payload["buckets"]]
    repro_close = cohort_mce(published, True)
    repro_open = cohort_mce(published, False)
    dedup, stats = substitute(payload["buckets"], cells)
    new_close = cohort_mce(dedup, True)
    new_open = cohort_mce(dedup, False)
    return {
        "generated_at": payload.get("generated_at"),
        "published_closing": payload.get("mce_closing_line"),
        "published_opening": payload.get("mce_opening_price"),
        "reproduced_closing": repro_close,
        "reproduced_opening": repro_open,
        "reproduction_exact": (repro_close == payload.get("mce_closing_line")
                               and repro_open == payload.get("mce_opening_price")),
        "dedup_closing": new_close,
        "dedup_opening": new_open,
        "delta_closing": (None if new_close is None or repro_close is None
                          else round(new_close - repro_close, 2)),
        "delta_opening": (None if new_open is None or repro_open is None
                          else round(new_open - repro_open, 2)),
        "outcomes_published": sum(b["n"] for b in payload["buckets"]),
        "outcomes_dedup": round(sum(b["n"] for b in dedup), 1),
        **stats,
    }


def fetch_payload(url: str | None) -> dict:
    import os
    base = (url or os.environ["BAINLUCK_API"]).rstrip("/")
    with urllib.request.urlopen(base + "/api/calibration", timeout=120) as fh:
        return json.loads(fh.read().decode())


# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--scan", action="store_true",
                    help="every cell: is phantom POSSIBLE here at all (cheap)")
    ap.add_argument("--cell", action="store_true",
                    help="one cell, exactly: per-bucket shipped vs de-duplicated")
    ap.add_argument("--headline", action="store_true",
                    help="substitute measured cells into the payload, recompute MCE")
    ap.add_argument("--source")
    ap.add_argument("--category")
    ap.add_argument("--direct", action="store_true",
                    help="--cell: run the cell's own chain in one statement")
    ap.add_argument("--roster-cache")
    ap.add_argument("--roster-buckets", type=int, default=32)
    ap.add_argument("--buckets", type=int, default=32)
    ap.add_argument("--min-markets", type=int, default=0,
                    help="--scan: skip cells below this resolved-market count")
    ap.add_argument("--payload", help="--headline: a saved /api/calibration body")
    ap.add_argument("--cells", nargs="*", default=[],
                    help="--headline: --cell output files (globs allowed)")
    ap.add_argument("--out")
    args = ap.parse_args()

    if sum(bool(x) for x in (args.scan, args.cell, args.headline)) != 1:
        ap.error("choose exactly one of --scan / --cell / --headline")

    if args.scan:
        cells = [c for c in cell_list() if c[2] >= args.min_markets]
        in_scope = [c for c in cells if c[0] in FUTURES_SOURCES]
        print(f"SCAN — {len(in_scope)} cells over {len(FUTURES_SOURCES)} futures "
              f"sources ({sum(c[2] for c in in_scope):,} resolved markets)")
        results = []
        for i, (src, cat, n) in enumerate(in_scope):
            r = scan_cell(src, cat)
            r["resolved_markets"] = n
            results.append(r)
            flag = ("TIMEOUT" if r["status"] != "ok"
                    else ("PHANTOM POSSIBLE" if r["phantom_possible"] else "clean"))
            print(f"  [{i + 1}/{len(in_scope)}] {src}/{cat:<18} {n:>7,} mkts  "
                  f"{r.get('secs', 0):>5.1f}s  {flag}"
                  # Neither figure is a bound on the phantom ROW rate; they are
                  # printed as coverage, which is what they are. See
                  # ``_scan_derived``.
                  + (f"  ({r['fanned_question_pct']}% of questions, "
                     f"{r['fanned_market_pct']}% of markets)"
                     if r["status"] == "ok" and r["phantom_possible"] else ""))
        clean = [r for r in results if r["status"] == "ok" and not r["phantom_possible"]]
        dirty = [r for r in results if r["status"] == "ok" and r["phantom_possible"]]
        to = [r for r in results if r["status"] != "ok"]
        print(f"\n  {'PROVABLY CLEAN cells':<34} {len(clean):>4}  "
              f"({sum(r['resolved_markets'] for r in clean):,} markets)")
        print(f"  {'cells where phantom is possible':<34} {len(dirty):>4}  "
              f"({sum(r['resolved_markets'] for r in dirty):,} markets)")
        print(f"  {'cells that could not be scanned':<34} {len(to):>4}  "
              f"({sum(r['resolved_markets'] for r in to):,} markets)")
        blob = {"mode": "scan", "futures_sources": list(FUTURES_SOURCES),
                "cells": results}
        if args.out:
            Path(args.out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.out).write_text(json.dumps(blob, indent=1))
            print(f"  wrote {args.out}")
        return 0

    if args.cell:
        if not (args.source and args.category):
            ap.error("--cell needs --source and --category")
        t0 = time.time()
        if args.direct:
            acc, how = cell_direct(args.source, args.category)
        else:
            acc, how = cell_over_roster(args.source, args.category,
                                        args.roster_buckets, args.buckets,
                                        args.roster_cache)
        rep = cell_report(acc, args.source, args.category, how)
        rep["secs"] = round(time.time() - t0, 1)
        print(f"\n{rep['cell']}  ({how}, {rep['secs']}s)")
        print(f"  {'published rows':<24} {rep['published_rows']:>9,}")
        print(f"  {'distinct outcomes':<24} {rep['distinct_outcomes']:>9,}")
        print(f"  {'PHANTOM rows':<24} {rep['phantom_rows']:>9,}   "
              f"({rep['phantom_pct']}% of the cell)")
        print(f"  {'copies agree':<24} {'yes' if rep['coherent'] else 'NO'}"
              + ("" if rep["coherent"] else f"   {rep['coherence']}"))
        if args.out:
            Path(args.out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.out).write_text(json.dumps(rep, indent=1))
            print(f"  wrote {args.out}")
        return 0

    payload = (json.loads(Path(args.payload).read_text()) if args.payload
               else fetch_payload(None))
    paths: list[str] = []
    for c in args.cells:
        paths.extend(sorted(glob.glob(c)) or [c])
    cells = [json.loads(Path(p).read_text()) for p in paths]
    h = headline(payload, cells)
    print(f"HEADLINE — {h['generated_at']}")
    print(f"  {'published closing / opening':<32} "
          f"{h['published_closing']} / {h['published_opening']}")
    print(f"  {'reproduced from its own buckets':<32} "
          f"{h['reproduced_closing']} / {h['reproduced_opening']}"
          f"   {'EXACT' if h['reproduction_exact'] else 'MISMATCH'}")
    print(f"  {'de-duplicated':<32} {h['dedup_closing']} / {h['dedup_opening']}")
    print(f"  {'DELTA':<32} {h['delta_closing']:+} / {h['delta_opening']:+}")
    print(f"  {'buckets substituted':<32} {h['substituted']} of "
          f"{h['substituted'] + h['untouched']}")
    print(f"  {'outcomes published -> dedup':<32} "
          f"{h['outcomes_published']:,} -> {h['outcomes_dedup']:,}")
    if h["rail_only"]:
        print(f"  ⚠️  {len(h['rail_only'])} buckets the rail measured and the "
              f"payload does not publish: {h['rail_only'][:5]}")
    if not h["reproduction_exact"]:
        print("  ⚠️  the payload's own buckets do not reproduce its own headline "
              "— the delta below is not trustworthy until that is explained")
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(h, indent=1))
        print(f"  wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
