#!/usr/bin/env python3
"""CAL-P125 — fold a published cell WITHOUT shattering its virtual questions.

Ruling 134 note: this is a read-only instrument. It writes nothing, it does not
re-implement the producer's population, and ``git diff origin/master --
backend/app frontend`` is empty on the branch that carries it. Ruling 009
freezes commits to ``precompute_calibration.py``; this file only imports it,
which is what every test in ``backend/tests`` already does.

WHY THIS FILE EXISTS
--------------------
``calibration_cell_exact.py`` chunks on ``fm.id`` and **re-derives**
``virtual_market`` inside every chunk. The producer's own docstring
(``_virtual_market_ctes``) says in as many words why that is wrong:

    group and event sizes are counted over ``market_info``, so re-deriving them
    from a FILTERED ``market_info`` silently changes them ... a chunk holding
    fewer than 3 would see the event collapse below the gate entirely, silently
    re-assigning every one of its markets to ``m:`` — a different question
    identity, a different representative, a different bucket.

CAL-P124 measured the damage. On ``polymarket/basketball`` the id-range rail
reproduces **8,426 of the cell's 13,135 published rows — −35.85%**, and the
missing 36% is not a sample: it is removed by a mechanism that also re-assigns
markets between the very classes a rule would name. Two board cells
(``basketball`` rank 11, ``hockey`` rank 16 — 26,232 excess-outcomes between
them) were declared UNMEASURED on that basis, and rank 1's banked K' rule
carries an unretired error bar for the same reason: ``polymarket/baseball``
sits at 32.2% on the wide-cluster axis and K' passes at 2.71 against a 3.0 bar.

THE FIX IS THE PRODUCER'S OWN, NOT A NEW IDEA
-----------------------------------------------
The staged build solved this in production (Queue 300D Item 0) and the solution
is already in the frozen file. This script drives it from the read rail:

  **Stage A — freeze the generation.** Derive ``virtual_market`` ONCE for the
  whole cell and read the roster out. Nothing downstream of ``virtual_market``
  is referenced, so PostgreSQL plans the rest of the chain away
  (``_futures_generation_sql``'s own argument).

  **Stage B — replay it.** Per unit call
  ``_calibration_population_ctes(frozen_vm_roster=True,
  market_info_extra=VM_ROSTER_MARKET_INFO_EXTRA)`` — the SAME call
  ``_main_futures_sql(frozen=True)`` makes — and cut the units with the
  producer's OWN planner, :func:`plan_units`, which guarantees a ``vm_id`` is
  never split.

So a chunk here is a REPLAY of one coherent global derivation rather than a
re-derivation over a subset. Every chunk's rows are exactly the global rows
restricted to that chunk, **by construction**, not by measurement.

THE TWO CHUNKING PROBLEMS, AND WHY NEITHER IS AN ID RANGE
-----------------------------------------------------------
1. *Stage A cannot be read in one request.* The unscoped global chain blows the
   Heroku router timeout (CAL-P124 measured ``Application Error`` at 103 s — do
   not retry it). So the CTEs are scoped to the cell and the READ is chunked on
   ``abs(hashtext(vm_id)::bigint) % N``, a filter on the OUTER select that never
   touches ``market_info`` and therefore cannot move a group/event size.

   A chunk that truncates or times out is SPLIT ``(N, k) -> (2N, k), (2N, k+N)``,
   which is an exact refinement — ``x % 2N in {k, k+N}`` iff ``x % N == k`` —
   so a ``vm_id`` never lands in two chunks and never in none. The split fires
   on the response's own ``truncated`` flag, never on a row-count heuristic
   (gotcha #53).

   ``hashtext`` is not on ``sql_read_guard``'s pure-function allowlist, which is
   the ANALYZE path's list; it is accepted on the row path and that was probed
   before this file was written. The ``::bigint`` cast is not decoration:
   ``hashtext`` returns int4 and ``abs(-2147483648)`` overflows, which would
   error one chunk out of billions and read as an empty range.

2. *Stage B cannot split a unit.* Splitting a ``vm_id`` is the entire bug this
   file exists to remove, so an oversized unit is re-planned at ``2 x buckets``
   rather than cut. That is again an exact refinement, for the same modular
   reason, and it uses :func:`plan_units` so the guarantee is the producer's
   rather than this file's. A single ``vm_id`` that alone exceeds the statement
   budget is raised BY NAME — it is the one case this rail cannot measure, and
   an instrument that cannot measure something must say so (CAL-P124's lesson 8
   in reverse: no silent all-clear).

THE ONE RESIDUAL, MEASURED RATHER THAN ASSERTED
-------------------------------------------------
Stage A is scoped to ``(source, category)``. The SOURCE half is exactly free:
``group_sizes`` / ``event_sizes`` are already ``GROUP BY ..., source``, so
restricting ``market_info`` to one source removes only rows that could never
have joined. The CATEGORY half is not free — a group or event whose markets
carry two ``llm_sport_category`` values is counted short, and can fall below the
``>= 3`` gate that the global derivation clears.

That is CAL-P124-2, and ``--bound`` measures it instead of assuming it (both
axes, per cell, ~7 s each). Measured 2026-08-29 against ``q268``:

    cell                     spanning groups (mkts)   spanning events (mkts)
    polymarket/basketball          11 (12)                  10 (15)
    polymarket/hockey               0  (0)                   1  (8)
    polymarket/baseball           298 (312)                204 (230)
    polymarket/cricket              0  (0)                   0  (0)
    polymarket/economics            8 (12)                   0  (0)

Those are UPPER bounds on re-assignment, and loose ones — a group with five
in-cell members and two outside spans categories but clears ``>= 3`` both ways,
so it re-assigns nothing. Where the exact figure was computed directly
(``baseball``: 325 of 64,558 markets, 0.50%) it came in ~40% under the 542-market
bound. On ``basketball`` the bound is **<= 27 markets of 26,007 (<= 0.10%)**,
against the −35.85% this rail removes. ``cricket`` is provably ZERO, which is why
it is the regression control below.

WHAT THIS RAIL STILL DOES NOT DO
----------------------------------
It inherits one omission from ``calibration_cell_exact`` rather than adding it:
a cross-source ``e:<event_id>`` virtual question sees only THIS source's
markets, because ``market_info`` is scoped to the roster. Per ruling 125 the
mode-price and dedup keys are ``(vm_id, source)``, so the only source-blind key
left is the representative window — read only on the non-multi branch, which a
cross-source ``e:`` never takes. Stated, not silently inherited.

Usage::

    # the residual bound alone (~15 s, two queries)
    python3 backend/scripts/calibration_whole_vm_fold.py \\
        --source polymarket --category basketball --bound

    # Stage A alone — the roster census, no fold
    python3 backend/scripts/calibration_whole_vm_fold.py \\
        --source polymarket --category basketball --stage-a-only

    # the whole thing
    python3 backend/scripts/calibration_whole_vm_fold.py \\
        --source polymarket --category basketball --by none \\
        --out artifacts/cal-p125/whole-vm-basketball.json
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from collections import defaultdict
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
from app.utils.calibration_staged_futures import plan_units  # noqa: E402


def _load(name: str):
    """Load a sibling script WITHOUT registering it in ``sys.modules``.

    CAL-P123's convention, and its reason applies verbatim: these modules mutate
    shared state at import time (``calibration_cluster_sigma`` adds ``marketid``
    to ``cce.DIMENSIONS``, ``calibration_family_fold`` adds four more), so a
    module left in ``sys.modules`` makes those mutations visible to every other
    test in the pytest process and CAL-P121's suite goes red — correctly.
    """
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


#: The rail, reached THROUGH ``calibration_family_fold`` rather than beside it.
#:
#: ``_load`` builds a fresh module object each call, so loading both siblings
#: independently would give this file a ``calibration_cell_exact`` on which the
#: four family dimensions are NOT registered — and ``--by family`` is the only
#: dimension that can name a Polymarket market family, which is exactly what a
#: Polymarket cell needs. Taking the family fold's own ``cce`` yields one module
#: object carrying the rail AND its four extra dimensions.
ffold = _load("calibration_family_fold")
cce = ffold.cce


# ---------------------------------------------------------------------------
# The one dimension this rail adds: HOW MANY LEGS OF THE MARKET WERE PUBLISHED
# ---------------------------------------------------------------------------
#: ``shape | pub<N>``, where N is the number of the market's outcomes that
#: reached ``deduped`` — the published population.
#:
#: WHY THIS IS NOT ``sumband`` WEARING A HAT. Every existing dimension bands the
#: published price SUM (``msums`` is ``SUM(adj_opening_probability)`` over
#: ``deduped``), and on a two-outcome market that quantity conflates two facts
#: that mean opposite things: *both legs published and coherent* (sum ~1) and
#: *one leg published at a low price* (sum <= 1.15 by having one term). The
#: ``sumband`` fold on ``polymarket/basketball`` reads
#: ``binary|a_sum_le_1.15`` at **1,096 rows, ECE 24.56, gap +21.06** against
#: ``binary|b_sum_1.15_2`` at **1,994 rows, ECE 10.6, gap −0.14** — a 21-point
#: one-sided error next to a two-sided one — and no dimension on the rail can
#: say which of the two facts the first class is.
#:
#: A COUNT distinguishes them and a SUM cannot. That is the whole reason this
#: exists, and it is the difference between a rule that names a mechanism and a
#: rule that names a threshold nobody can defend.
#:
#: It also puts a number on 12-CAL at last. The lone-claim filter is stated as a
#: Kalshi question and CAL-P123 showed it on ``polymarket/cricket`` (33 rows, 33
#: winners, 0 losers); ``pub1`` is that cohort, counted, on any cell, in one
#: fold rather than a census.
#:
#: ``mlegs`` reads ``deduped`` and is appended as a trailing CTE, exactly as
#: ``SUMBAND_PRE`` does — the published population is the thing being counted,
#: so counting it anywhere earlier would count a different set.
PUBLEGS_PRE = """,
mlegs AS (
    SELECT market_id, COUNT(*) AS legs FROM deduped GROUP BY market_id
)"""
PUBLEGS_JOIN = cce.SHAPE_JOIN + "\nLEFT JOIN mlegs ml ON ml.market_id = d.market_id"
PUBLEGS_EXPR = """
CASE WHEN sh.mw = 0 THEN 'void'
     WHEN sh.mn >= 3 AND sh.mw >= 2 THEN 'bundle'
     WHEN sh.mn >= 3 AND sh.mw = 1 THEN 'field1'
     WHEN sh.mn = 2 THEN 'binary'
     ELSE 'single' END
|| '|pub' ||
CASE WHEN ml.legs IS NULL THEN 'na'
     WHEN ml.legs >= 4 THEN '4plus'
     ELSE ml.legs::text END
|| '/' ||
CASE WHEN sh.mn IS NULL THEN 'na'
     WHEN sh.mn >= 4 THEN '4plus'
     ELSE sh.mn::text END
"""

#: ``setdefault``, never ``DIMENSIONS[k] = v`` — CAL-P121's convention. Rebinding
#: would let this file silently change what an existing ``--by`` means for
#: everyone who imports the rail. The guard suite asserts this name is absent
#: before registration and present after, and that it is the ONLY one added.
ADDED_DIMENSIONS = {
    "publegs": (PUBLEGS_EXPR, PUBLEGS_JOIN, PUBLEGS_PRE),
}
_PRE_EXISTING = frozenset(cce.DIMENSIONS)
for _name, _spec in ADDED_DIMENSIONS.items():
    cce.DIMENSIONS.setdefault(_name, _spec)


# ---------------------------------------------------------------------------
# CAL-P124-2 — the category-scoping residual, as a measurement
# ---------------------------------------------------------------------------
#: Groups (or events) that hold markets both inside and outside the cell.
#:
#: An UPPER bound on re-assignment and deliberately so: computing the exact
#: figure needs both cardinalities joined back per market, which measured 9.2 s
#: on ``baseball`` and timed out on every other cell against the row path's hard
#: 10 s. Where both were computed the bound was loose by ~40% in the SAFE
#: direction (over-stating the residual), so a small bound is a real all-clear
#: and a large one is a reason to look harder.
#:
#: ``{chunk}`` partitions on a hash of the GROUPING KEY, so every group lands
#: wholly inside one residue class and the per-class counts simply ADD. Chunking
#: on ``fm.id`` here would be silently wrong — it would cut groups apart and
#: each piece would look like a group that does not span.
SPAN_SQL = """
SELECT COUNT(*) AS spanning, COALESCE(SUM(nc), 0) AS cell_markets
FROM (
    SELECT fm.{col},
           COUNT(*) FILTER (
               WHERE COALESCE(fm.llm_sport_category, 'uncategorized') = '{category}'
           ) AS nc
    FROM futures_markets fm
    WHERE fm.status = 'resolved'
      AND fm.source = '{source}'
      AND fm.{col} IS NOT NULL
      {chunk}
    GROUP BY 1
    HAVING COUNT(*) FILTER (
               WHERE COALESCE(fm.llm_sport_category, 'uncategorized') = '{category}'
           ) > 0
       AND COUNT(*) FILTER (
               WHERE COALESCE(fm.llm_sport_category, 'uncategorized') <> '{category}'
           ) > 0
) t
"""

CELL_MARKETS_SQL = """
SELECT COUNT(*) AS n
FROM futures_markets fm
WHERE fm.status = 'resolved'
  AND fm.source = '{source}'
  AND COALESCE(fm.llm_sport_category, 'uncategorized') = '{category}'
  {chunk}
"""


def _sum_over_residues(make_sql, ncols: int, n: int = 1, k: int = 0,
                       depth: int = 0) -> list[int]:
    """A scalar aggregate the row path cannot finish in one statement.

    Every caller here aggregates over a key that ``make_sql``'s ``{chunk}``
    partitions on, so the residue classes are disjoint and exhaustive and the
    per-class results ADD. That is the whole reason this is a sum and not an
    average or a max — a helper that summed a non-additive aggregate would be
    wrong quietly, so it is not general and does not pretend to be.

    A statement that times out is SPLIT, never retried at the same size: the
    measured cost of these scans sits within a second or two of the row path's
    hard 10 s ceiling, so the same query genuinely succeeds and fails across
    runs (both observed on ``polymarket/cricket``, 7.4 s then cancelled). A
    retry loop would turn that into a coin flip; halving turns it into an answer.
    """
    try:
        r = cce.db_query(make_sql(n, k), limit=5)
        return [int(v or 0) for v in r["rows"][0][:ncols]]
    except cce.QueryTimeout:
        if depth > 10:
            raise RuntimeError(
                f"aggregate residue {k} mod {n} irreducible at depth {depth}")
        a = _sum_over_residues(make_sql, ncols, 2 * n, k, depth + 1)
        b = _sum_over_residues(make_sql, ncols, 2 * n, k + n, depth + 1)
        return [x + y for x, y in zip(a, b)]


def cross_category_bound(source: str, category: str) -> dict:
    """How much of the cell COULD be mis-assigned by scoping Stage A to a category."""
    out: dict = {}
    for col in ("group_id", "event_id"):
        def make(n, k, col=col):
            chunk = ("" if n == 1 else
                     f"AND ABS(HASHTEXT(fm.{col}::text)::bigint) % {n} = {k}")
            return SPAN_SQL.format(col=col, source=source, category=category,
                                   chunk=chunk)
        spanning, markets = _sum_over_residues(make, 2)
        out[col] = {"spanning": spanning, "cell_markets": markets}

    def make_cell(n, k):
        chunk = "" if n == 1 else f"AND fm.id % {n} = {k}"
        return CELL_MARKETS_SQL.format(source=source, category=category, chunk=chunk)

    out["cell_markets_total"] = _sum_over_residues(make_cell, 1)[0]
    out["upper_bound_markets"] = (out["group_id"]["cell_markets"]
                                  + out["event_id"]["cell_markets"])
    tot = out["cell_markets_total"]
    out["upper_bound_pct"] = round(out["upper_bound_markets"] / tot * 100, 4) if tot else None
    return out


# ---------------------------------------------------------------------------
# Stage A — freeze the generation
# ---------------------------------------------------------------------------
#: The roster read. Selecting only from ``virtual_market`` is what makes it
#: cheap: PostgreSQL does not execute an unreferenced ``WITH`` subquery, so
#: naming the full chain costs nothing and everything downstream —
#: ``ranked_outcomes``, the price joins, the whole per-outcome universe — is
#: planned away. ``_futures_generation_sql`` makes exactly this argument.
#:
#: The hash filter sits on the OUTER select, deliberately. Push it into
#: ``market_info`` and it becomes a filtered population, which is the defect
#: this file exists to remove.
STAGE_A_TAIL = """
SELECT market_id, source, vm_id, is_grouped
FROM virtual_market
WHERE ABS(HASHTEXT(vm_id)::bigint) % {n} = {k}
ORDER BY market_id
"""


class RosterRow:
    """One Stage A row, with attribute access.

    ``plan_units`` and ``generation_fingerprint`` read production SQLAlchemy
    ``Row`` objects, and the helper they go through accepts either attributes or
    mapping keys. Handing them attributes keeps this rail on the same branch as
    the producer instead of the one only tests exercise.

    **Hand-written rather than a ``@dataclass``, and that is not a style
    choice.** ``from __future__ import annotations`` makes every annotation a
    string, and ``dataclasses`` resolves those through
    ``sys.modules[cls.__module__]`` — which is ``None`` here, because
    :func:`_load` deliberately does not register this module (CAL-P123's rule:
    a sibling left in ``sys.modules`` leaks its dimension registrations into
    every other test in the pytest process). The decorator raises
    ``AttributeError: 'NoneType' object has no attribute '__dict__'`` at import.
    A dataclass and this loader cannot both be right; the loader is the one with
    a guard suite behind it.
    """

    __slots__ = ("market_id", "source", "vm_id", "is_grouped")

    def __init__(self, market_id, source, vm_id, is_grouped):
        self.market_id = int(market_id)
        self.source = str(source)
        self.vm_id = str(vm_id)
        self.is_grouped = bool(is_grouped)

    def __eq__(self, other):
        return isinstance(other, RosterRow) and self._t() == other._t()

    def __hash__(self):
        return hash(self._t())

    def __repr__(self):
        return (f"RosterRow(market_id={self.market_id}, source={self.source!r}, "
                f"vm_id={self.vm_id!r}, is_grouped={self.is_grouped})")

    def _t(self):
        return (self.market_id, self.source, self.vm_id, self.is_grouped)


def stage_a_sql(source: str, category: str, n: int, k: int) -> str:
    pop = _calibration_population_ctes(
        market_info_extra=(
            f"AND fm.source = '{source}' "
            f"AND COALESCE(fm.llm_sport_category, 'uncategorized') = '{category}'"
        )
    )
    return cce._strip_sql_comments(
        "WITH " + pop + STAGE_A_TAIL.format(n=n, k=k))


def _read_hash_chunk(source: str, category: str, n: int, k: int,
                     depth: int = 0, log=None) -> list[RosterRow]:
    """One residue class of the roster, or an exact refinement of it.

    Truncation and statement-timeout are the same fact wearing two faces — the
    residue class is too big — and only one of them is loud. Both split.
    """
    try:
        r = cce.db_query(stage_a_sql(source, category, n, k), limit=cce.ROW_CAP)
        truncated = bool(r.get("truncated")) or r["row_count"] >= cce.ROW_CAP
    except cce.QueryTimeout:
        r, truncated = None, True

    if r is not None and not truncated:
        return [RosterRow(int(m), str(s), str(v), bool(g)) for m, s, v, g in r["rows"]]

    # ``x % 2n in {k, k+n}`` iff ``x % n == k`` — an exact refinement, so a
    # ``vm_id`` lands in exactly one of the two halves and in neither's
    # complement. Depth 12 is 4,096x the starting partition; a cell that still
    # will not fit at that width is a finding, not a retry.
    if depth > 12:
        raise RuntimeError(
            f"Stage A residue {k} mod {n} irreducible at depth {depth} — "
            f"the roster read cannot be chunked small enough for the row path")
    if log:
        log(f"      split {k} mod {n} -> {k},{k + n} mod {2 * n}")
    return (_read_hash_chunk(source, category, 2 * n, k, depth + 1, log)
            + _read_hash_chunk(source, category, 2 * n, k + n, depth + 1, log))


def stage_a(source: str, category: str, n: int) -> list[RosterRow]:
    rows: list[RosterRow] = []
    t0 = time.time()

    def log(msg):
        print(msg, file=sys.stderr, flush=True)

    for k in range(n):
        log(f"    Stage A [{k + 1}/{n}] residue {k} mod {n} "
            f"({len(rows)} rows, {time.time() - t0:.0f}s)")
        rows.extend(_read_hash_chunk(source, category, n, k, 0, log))
    return rows


def load_or_freeze(source: str, category: str, n: int,
                   cache: str | None) -> tuple[list[RosterRow], float, str]:
    """Stage A, reusing a cached generation when one is on disk for THIS cell.

    Stage A is 78% of a basketball fold (395 s of 508 s measured) and it does
    not depend on the dimension, so folding a cell by five dimensions costs five
    roster reads for no new information. Caching it turns the second and later
    folds into ~2 minutes.

    **The cache is keyed and refused, never merged.** A roster is a claim about
    which markets are eligible and which virtual question each belongs to, and
    replaying one cell's roster against another cell — or against a chain whose
    eligibility predicate has since changed — would produce a fold that is
    complete, plausible and about a different population. So: the source and
    category must match or the file is refused BY NAME, and the roster's age is
    PRINTED on every reuse rather than mentioned once at write time. An old
    roster is a real risk (markets resolve into the cell continuously) and the
    only defensible design is to make the reader see the age every time.
    """
    if cache:
        p = Path(cache)
        if p.exists():
            blob = json.loads(p.read_text())
            if (blob.get("source"), blob.get("category")) != (source, category):
                raise SystemExit(
                    f"roster cache {cache} holds {blob.get('source')}/"
                    f"{blob.get('category')}, not {source}/{category}. Refusing "
                    f"to fold one cell's rows under another cell's name.")
            rows = [RosterRow(*r) for r in blob["rows"]]
            age_h = (time.time() - blob["captured_at"]) / 3600
            print(f"  STAGE A — REUSED from {cache} "
                  f"({len(rows)} rows, frozen {age_h:.1f}h ago)")
            if age_h > 24:
                print("    ⚠️  the cached generation is over a day old; markets "
                      "resolve into a cell continuously. Re-freeze before "
                      "benching a rule on it.")
            return rows, 0.0, "reused"

    t0 = time.time()
    rows = stage_a(source, category, n)
    secs = time.time() - t0
    if cache:
        p = Path(cache)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({
            "source": source, "category": category, "roster_buckets": n,
            "captured_at": time.time(),
            "rows": [[r.market_id, r.source, r.vm_id, r.is_grouped] for r in rows],
        }))
        print(f"  STAGE A — froze {len(rows)} rows to {cache}")
    return rows, secs, "frozen"


# ---------------------------------------------------------------------------
# Stage B — replay the frozen generation, one whole-vm unit at a time
# ---------------------------------------------------------------------------
def _bigint_array(vals) -> str:
    return "ARRAY[" + ",".join(str(int(v)) for v in vals) + "]"


def _text_array(vals) -> str:
    # Doubling the quote is the whole escape under ``standard_conforming_strings``
    # (on by default since PG 9.1), and a backslash therefore needs none. A
    # ``vm_id`` is ``g:<group_id>`` / ``e:<id>`` / ``m:<id>`` and Polymarket's
    # group ids are ``polymarket:<event id>``, so no quote has ever appeared —
    # which is exactly why escaping has to be here rather than argued away.
    return "ARRAY[" + ",".join("'" + str(v).replace("'", "''") + "'" for v in vals) + "]"


def _bool_array(vals) -> str:
    return "ARRAY[" + ",".join("true" if v else "false" for v in vals) + "]"


def unit_sql(unit, assignment: dict, dim: str, holdout_at: int | None) -> str:
    """One unit's fold, with the frozen roster inlined as literals.

    ``db-query`` is a text endpoint and takes no binds, so the three parallel
    arrays the producer passes as parameters are rendered into the statement.
    They are rendered AFTER comment-stripping, so a ``--`` inside a ``vm_id``
    can never be read as a comment and a stripper bug can never eat a roster.
    """
    if dim in cce.PER_CHUNK_DIMENSIONS:
        raise ValueError(
            f"--by {dim} is an id-RANGE dimension (it is handed lo/hi and "
            f"pre-computes per range). This rail has no id ranges; its chunks "
            f"are whole virtual questions. Use the id-range rail for it.")
    expr, join, pre = cce.DIMENSIONS[dim]

    market_ids = list(unit.market_ids)
    if not market_ids:
        raise ValueError(f"unit {unit.index} carries no markets")

    half = ("'ALL'" if holdout_at is None else
            f"CASE WHEN d.market_id < {int(holdout_at)} THEN 'OLD' ELSE 'NEW' END")

    template = cce._strip_sql_comments(
        "WITH "
        + _calibration_population_ctes(
            frozen_vm_roster=True, market_info_extra=VM_ROSTER_MARKET_INFO_EXTRA)
        + pre
        + f"""
SELECT {expr} AS k,
       LEAST(FLOOR(d.adj_opening_probability * 10)::int, 9) AS b,
       {half} AS h,
       COUNT(*) AS n,
       SUM(CASE WHEN d.is_winner THEN 1 ELSE 0 END) AS w,
       ROUND(SUM(d.adj_opening_probability)::numeric, 6) AS sp
FROM deduped d
{join}
GROUP BY 1, 2, 3""")

    sql = (template
           .replace(f":{VM_ROSTER_MARKET_IDS_PARAM}", _bigint_array(market_ids))
           .replace(f":{VM_ROSTER_VM_IDS_PARAM}",
                    _text_array(assignment[m][0] for m in market_ids))
           .replace(f":{VM_ROSTER_IS_GROUPED_PARAM}",
                    _bool_array(assignment[m][1] for m in market_ids)))
    # An unsubstituted bind would reach the server as a literal ``:name`` and
    # fail with a syntax error that reads like a guard refusal. Say which.
    for p in (VM_ROSTER_MARKET_IDS_PARAM, VM_ROSTER_VM_IDS_PARAM,
              VM_ROSTER_IS_GROUPED_PARAM):
        if f":{p}" in sql:
            raise RuntimeError(f"roster parameter :{p} was not substituted")
    return sql


def fold_unit(rows: list[RosterRow], unit, assignment: dict, dim: str,
              holdout_at: int | None, buckets: int, depth: int = 0) -> list:
    """Fold one unit, re-PLANNING (never splitting) when it does not fit.

    Three failure modes, and the quietest is checked before the request rather
    than diagnosed from its reply: a statement over the length cap, a statement
    that times out, and a reply at the row cap. All three mean the same thing —
    too many whole questions in one unit — and the answer to all three is a
    finer partition, never a cut ``vm_id``.
    """
    try:
        sql = unit_sql(unit, assignment, dim, holdout_at)
        if len(sql) > cce.MAX_SQL_CHARS:
            raise cce.QueryTimeout(f"SQL {len(sql)} chars over the cap")
        r = cce.db_query(sql, limit=cce.ROW_CAP)
        if bool(r.get("truncated")) or r["row_count"] >= cce.ROW_CAP:
            raise cce.QueryTimeout("reply at the row cap")
        return r["rows"]
    except cce.QueryTimeout as exc:
        if len(unit.vm_ids) <= 1:
            raise RuntimeError(
                f"virtual question {unit.vm_ids[0] if unit.vm_ids else '?'} "
                f"({len(unit.market_ids)} markets) does not fit in one statement "
                f"and MUST NOT be split — splitting a vm_id is the defect this "
                f"rail removes. Cause: {exc}") from exc
        if depth > 8:
            raise RuntimeError(
                f"unit {unit.index} still failing at partition depth {depth}: {exc}"
            ) from exc

        # ``bucket_of`` is SHA-256 mod ``buckets``, so ``2 x buckets`` refines
        # this unit exactly: every vm_id here lands in one of two sub-buckets
        # and in no other unit. Re-planning through the producer's own planner
        # keeps the "never split a vm_id" guarantee where it belongs.
        mine = {v for v in unit.vm_ids}
        sub_rows = [r for r in rows if r.vm_id in mine]
        print(f"      unit {unit.index} re-planned at {buckets * 2} buckets "
              f"({len(unit.vm_ids)} questions, {len(unit.market_ids)} markets): {exc}",
              file=sys.stderr, flush=True)
        out: list = []
        for sub in plan_units(sub_rows, buckets=buckets * 2):
            out.extend(fold_unit(sub_rows, sub, assignment, dim, holdout_at,
                                 buckets * 2, depth + 1))
        return out


#: CAL-P125 — how many of a cell's published rows are the SAME outcome twice.
#:
#: ``deduped`` is one row per outcome by construction — ``SELECT ro.* FROM
#: normalized ro`` — so ``COUNT(*) > COUNT(DISTINCT outcome_id)`` is not a
#: judgement call about a threshold. It is an arithmetic impossibility, and it
#: is measured rather than asserted because the payload carries the same rows:
#: the SELF-CHECK cannot see this, and neither can any fold.
PHANTOM_TAIL = """
, mlegs AS (
    SELECT market_id, COUNT(*) AS legs,
           COUNT(DISTINCT outcome_id) AS dlegs
    FROM deduped GROUP BY market_id
)
SELECT COALESCE(SUM(legs), 0) AS published_rows,
       COALESCE(SUM(dlegs), 0) AS distinct_outcomes,
       COUNT(*) FILTER (WHERE legs > dlegs) AS markets_affected,
       COUNT(*) AS markets
FROM mlegs"""


def phantom_census(rows: list[RosterRow], buckets: int) -> dict:
    """Published rows vs the distinct outcomes behind them, over the whole cell.

    Run over EVERY unit, never a sample: a partial sweep here reads as a small
    duplication rate rather than as a partial sweep, which is gotcha #53 aimed
    at the one number that would decide whether the curve is trustworthy.
    """
    assignment = {r.market_id: (r.vm_id, r.is_grouped) for r in rows}
    units = plan_units(rows, buckets=buckets)
    tpl = cce._strip_sql_comments(
        "WITH " + _calibration_population_ctes(
            frozen_vm_roster=True,
            market_info_extra=VM_ROSTER_MARKET_INFO_EXTRA) + PHANTOM_TAIL)

    tot = [0, 0, 0, 0]
    t0 = time.time()
    for i, unit in enumerate(units):
        mk = list(unit.market_ids)
        sql = (tpl
               .replace(f":{VM_ROSTER_MARKET_IDS_PARAM}", _bigint_array(mk))
               .replace(f":{VM_ROSTER_VM_IDS_PARAM}",
                        _text_array(assignment[x][0] for x in mk))
               .replace(f":{VM_ROSTER_IS_GROUPED_PARAM}",
                        _bool_array(assignment[x][1] for x in mk)))
        r = cce.db_query(sql, limit=5)
        for j, v in enumerate(r["rows"][0][:4]):
            tot[j] += int(v or 0)
        if i % 16 == 0:
            print(f"    phantom census [{i + 1}/{len(units)}] "
                  f"({time.time() - t0:.0f}s)", file=sys.stderr, flush=True)

    pub, dis, aff, mk_ = tot
    return {"published_rows": pub, "distinct_outcomes": dis,
            "phantom_rows": pub - dis,
            "phantom_pct": round((pub - dis) / pub * 100, 2) if pub else None,
            "markets_affected": aff, "markets": mk_}


def stage_b(rows: list[RosterRow], dim: str, buckets: int,
            holdout_at: int | None) -> tuple[dict, dict, int]:
    assignment = {r.market_id: (r.vm_id, r.is_grouped) for r in rows}
    units = plan_units(rows, buckets=buckets)

    def _new():
        return defaultdict(lambda: defaultdict(lambda: {"n": 0, "w": 0, "sp": 0.0}))

    by_key, halves = _new(), {"OLD": _new(), "NEW": _new()}
    t0 = time.time()
    for i, unit in enumerate(units):
        print(f"    Stage B [{i + 1}/{len(units)}] unit {unit.index}: "
              f"{len(unit.vm_ids)} questions, {len(unit.market_ids)} markets "
              f"({time.time() - t0:.0f}s)", file=sys.stderr, flush=True)
        for k, b, h, n, w, sp in fold_unit(rows, unit, assignment, dim,
                                           holdout_at, buckets):
            targets = [by_key] + ([halves[h]] if h in halves else [])
            for t in targets:
                v = t[k][b]
                v["n"] += n
                v["w"] += w
                v["sp"] += float(sp)
    return by_key, halves, len(units)


# ---------------------------------------------------------------------------
def roster_census(rows: list[RosterRow]) -> dict:
    kinds: dict[str, int] = defaultdict(int)
    for r in rows:
        kinds[r.vm_id.split(":", 1)[0]] += 1
    sizes: dict[str, int] = defaultdict(int)
    for r in rows:
        sizes[r.vm_id] += 1
    grouped = sum(1 for r in rows if r.is_grouped)
    return {
        "roster_rows": len(rows),
        "distinct_markets": len({r.market_id for r in rows}),
        "distinct_vm_ids": len(sizes),
        "markets_grouped": grouped,
        "markets_ungrouped": len(rows) - grouped,
        "vm_by_kind": dict(sorted(kinds.items())),
        "largest_vm_markets": max(sizes.values()) if sizes else 0,
        "vm_ids_over_100_markets": sum(1 for v in sizes.values() if v > 100),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", required=True)
    ap.add_argument("--category", required=True)
    ap.add_argument("--by", default="none")
    ap.add_argument("--roster-buckets", type=int, default=64,
                    help="Stage A residue classes; a class that truncates or "
                         "times out is refined to 2N, exactly")
    ap.add_argument("--buckets", type=int, default=64,
                    help="Stage B units; an oversized unit is RE-PLANNED at "
                         "2x, never split")
    ap.add_argument("--holdout-at", type=int, default=None,
                    help="a market_id; fold OLD (< id) and NEW (>= id) apart. "
                         "Applied INSIDE the group key, so unlike the id-range "
                         "rail it needs no chunk edge to stay uncontaminated.")
    ap.add_argument("--roster-cache",
                    help="reuse (or write) the Stage A generation at this path. "
                         "Stage A is ~78%% of a fold and does not depend on "
                         "--by, so a second dimension is ~2 min instead of ~8. "
                         "Keyed on source/category and refused on a mismatch; "
                         "its age is printed on every reuse.")
    ap.add_argument("--bound", action="store_true",
                    help="measure the CAL-P124-2 category-scoping residual and stop")
    ap.add_argument("--stage-a-only", action="store_true",
                    help="freeze the generation, print the roster census, stop")
    ap.add_argument("--phantom", action="store_true",
                    help="count the cell's published rows against the DISTINCT "
                         "outcomes behind them, and stop. deduped is one row "
                         "per outcome by construction, so any excess is rows "
                         "the curve counts more than once.")
    ap.add_argument("--out")
    args = ap.parse_args()

    known = set(cce.DIMENSIONS)
    if args.by not in known:
        ap.error(f"--by {args.by} unknown; available: {' '.join(sorted(known))}")

    print(f"{args.source}/{args.category}   whole-vm rail (CAL-P125)")
    print()

    t_bound = time.time()
    bound = cross_category_bound(args.source, args.category)
    print("  CAL-P124-2 — the category-scoping residual, measured")
    print(f"    {'cell markets':<26} {bound['cell_markets_total']:>8}")
    for col in ("group_id", "event_id"):
        b = bound[col]
        print(f"    {'spanning ' + col:<26} {b['spanning']:>8} "
              f"({b['cell_markets']} cell markets)")
    print(f"    {'UPPER BOUND re-assigned':<26} {bound['upper_bound_markets']:>8} "
          f"({bound['upper_bound_pct']}%)   [{time.time() - t_bound:.0f}s]")
    print()
    if args.bound:
        return 0

    rows, secs_a, how = load_or_freeze(args.source, args.category,
                                       args.roster_buckets, args.roster_cache)
    census = roster_census(rows)
    print(f"  STAGE A — the frozen generation ({how}, {secs_a:.0f}s, "
          f"{args.roster_buckets} residue classes)")
    for k, v in census.items():
        print(f"    {k:<26} {v if not isinstance(v, dict) else json.dumps(v):>8}")
    print()
    if args.stage_a_only:
        return 0

    if args.phantom:
        t_p = time.time()
        ph = phantom_census(rows, args.buckets)
        print(f"  PHANTOM CENSUS — published rows vs the outcomes behind them "
              f"({time.time() - t_p:.0f}s)")
        print(f"    {'published rows in deduped':<30} {ph['published_rows']:>8}")
        print(f"    {'DISTINCT outcomes behind them':<30} {ph['distinct_outcomes']:>8}")
        print(f"    {'PHANTOM rows':<30} {ph['phantom_rows']:>8}   "
              f"({ph['phantom_pct']}% of the cell)")
        print(f"    {'markets affected':<30} {ph['markets_affected']:>8} "
              f"of {ph['markets']}")
        if args.out:
            Path(args.out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.out).write_text(json.dumps(
                {"source": args.source, "category": args.category,
                 "cross_category_bound": bound, "roster_census": census,
                 "phantom": ph}))
            print(f"  wrote {args.out}")
        return 0

    t_b = time.time()
    by_key, halves, n_units = stage_b(rows, args.by, args.buckets, args.holdout_at)
    secs_b = time.time() - t_b

    pooled = cce.pool(by_key)
    n, ece, gap = cce.fold(pooled)
    pn, pece, pgap, meta = cce.payload_cell(args.source, args.category)

    print(f"  STAGE B — {n_units} whole-vm units, --by {args.by} ({secs_b:.0f}s)")
    print(f"  curve generated {meta['generated_at']}  "
          f"population {meta['population_version']}")
    print()
    print("  SELF-CHECK — the producer's own chain against the payload it produced")
    print(f"    {'whole-vm replica':<18} n={n:>7}  ECE={ece:>6}  gap={gap:>+7}")
    print(f"    {'payload':<18} n={pn:>7}  ECE={pece:>6}  gap={pgap:>+7}")
    dn = None
    if pn:
        dn = (n - pn) / pn * 100
        print(f"    {'delta':<18} n={n - pn:>+7} ({dn:+.2f}%)  "
              f"ECE={ece - pece:+.2f}  gap={gap - pgap:+.2f}")
    print()

    if args.by != "none":
        print(f"  {'class':<40} {'n':>7} {'share':>7} {'ECE':>7} {'gap':>8}")
        for k in sorted(by_key, key=lambda k: -sum(v["n"] for v in by_key[k].values())):
            kn, kece, kgap = cce.fold(by_key[k])
            print(f"  {str(k):<40} {kn:>7} {kn / n * 100:>6.1f}% "
                  f"{kece:>7} {kgap:>+8}")
        print()

    if args.holdout_at:
        print(f"  HOLDOUT on market_id {args.holdout_at}")
        for half in ("OLD", "NEW"):
            print(f"    {half}")
            for k in sorted(halves[half],
                            key=lambda k: -sum(v["n"] for v in halves[half][k].values())):
                kn, kece, kgap = cce.fold(halves[half][k])
                print(f"      {str(k):<40} {kn:>7} {kece:>7} {kgap:>+8}")
        print()

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        with open(args.out, "w") as fh:
            json.dump({
                "rail": "whole_vm", "source": args.source,
                "category": args.category, "by": args.by,
                "roster_buckets": args.roster_buckets, "buckets": args.buckets,
                "units": n_units,
                "seconds": {"stage_a": round(secs_a, 1), "stage_b": round(secs_b, 1)},
                "cross_category_bound": bound,
                "roster_census": census,
                "payload": {"n": pn, "ece": pece, "gap": pgap, **meta},
                "exact": {"n": n, "ece": ece, "gap": gap, "delta_pct": dn},
                "by_key": {str(k): {str(b): v for b, v in bb.items()}
                           for k, bb in by_key.items()},
                "halves": {h: {str(k): {str(b): v for b, v in bb.items()}
                               for k, bb in hv.items()}
                           for h, hv in halves.items()} if args.holdout_at else None,
            }, fh)
        print(f"  wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
