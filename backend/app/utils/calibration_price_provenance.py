"""CAL-P077 (#1145, #1978, #1544) — WHERE the curve's price came from, and WHEN.

**A price captured after the question was answered is not a price. It is the
answer, wearing a price's clothes.**

What this module is for
-----------------------
Fable's CAL-P077 ruling (d) named the top calibration lever "the which-price
fix": re-price or exclude rows that fall back to ``opening_probability``, scoped
per cell, with expected ΔECE from the measured value gaps. Building the
instrument to size that fix measured something the framing did not predict, so
the module is named for what was found rather than for what was expected.

The curve prices every outcome as
``COALESCE(fo.calibration_probability, fo.opening_probability)``
(``_calibration_population_ctes``' ``curve_price`` default). Two distinct things
hide behind that expression, and a third hides behind both:

``cp_absent``
    ``calibration_probability IS NULL``. The read side supplies an opening
    price. This is the class codex's round-2 subcohort work measured
    (basketball 14.8%, hockey 24.8%, tennis 1.5-3.0%, economics 4.5%).
``cp_eq_open``
    ``calibration_probability = opening_probability``. The WRITER already fell
    back: ``backfill_winners`` Part A stores
    ``COALESCE(closing.probability, opening_probability)``, so a row with no
    pre-commence snapshot banks the opening under the closing line's name. This
    class is invisible to a ``cp IS NULL`` probe and is **the larger half** — 37%
    to 84% of every cell measured.
``cp_moved``
    A genuinely distinct closing price.

That is the *which-price* axis, and on its own it does not explain the outliers.
The axis that does is **capture age**: was our EARLIEST observation of this
outcome taken before or after the market resolved?

``pregame`` / ``after_commence`` / ``after_resolution`` / ``no_capture_ts``
    from ``fo.opening_captured_at`` against ``fm.commence_time`` and
    ``fm.resolution_date``.

Measured in production 2026-08-20, full cells, not sampled
----------------------------------------------------------
``hockey/container_member`` — the 41 pp cell with "NO known mechanism":

=====================  ======  =========  ========  =========
class                       n   avg price   winrate     gap pp
=====================  ======  =========  ========  =========
cp_absent, after_res      367       0.017     1.000      -98.3
cp_eq_open, after_res     880       0.295     0.002      +29.3
cp_moved, after_commence  129       0.434     0.434      **0.0**
=====================  ======  =========  ========  =========

Two catastrophic errors of OPPOSITE SIGN, summing to a pooled gap of -6.6 pp.
That is why every gap-based alarm in the program walked past this cell for
months: **the cell's honest-looking gap was two hindsight artifacts cancelling.**
And the sub-population whose first look was a real pre-resolution quote is
calibrated to 0.0 pp — not "less bad", exactly right.

There is no price to recover for the rest. Of the 1,259 hindsight rows in that
cell, **0 have any ``futures_odds_snapshots`` row before ``commence_time`` and 0
before ``resolution_date``** (basketball/quantity: 0 of 8,387;
basketball/container_member: 32 of 3,737). Our first observation postdates the
answer, so "re-price against venue close" has nothing to read. **Exclusion is
not the fallback option here; it is the only sound one**, and that is a
measurement, not a preference.

Pooled over all 49 cells (grade ``complete``), dropping ``after_resolution``:
**ECE 3.780 pp -> 1.771 pp, Δ -2.009 pp, on 9.1% of rows dropped.**

Why the exclusion is safe to specify at market granularity
-----------------------------------------------------------
``opening_captured_at`` is per-outcome and ``resolution_date`` is per-market, so
in principle the predicate could split a field and break the sum-to-1 invariant
the completeness gate guarantees. Measured over 36,309 markets in the four
worst cells: **3 markets are mixed (0.008%).** The predicate is market-clean, so
it is specified at the market level and the three stragglers are excluded whole
— symmetric by construction, winners and losers together, which is the standing
requirement for every exclusion on this curve.

The honest caveat, stated because it is the one that could sink this
--------------------------------------------------------------------
The predicate is outcome-blind in DEFINITION (when we polled) but not in
EFFECT: hindsight rows have a different winrate from the rest (hockey 0.296 vs
0.430). Dropping rows can always lower ECE by removing hard rows, so the claim
needs a non-vacuity control, and it has three:

1. **Absent mechanism, absent effect.** Of the cells with n>=1,000 and a
   hindsight share below 2%, **all 10 move by |ΔECE| < 0.20 pp**. A generic
   row-dropping effect would move them too.
2. **The dropped population is the corrupt one.** Dropped-row ECE is 24-48 pp in
   every affected cell; kept-row ECE is 4.6-12.4 pp.
3. **The kept population is calibrated, not merely better** (hockey kept gap
   +0.61 pp on the cell that read -6.58 pp whole).

What this module does NOT do
-----------------------------
It does not change the curve. No policy here is wired into
``_calibration_population_ctes``, which stays frozen under ruling 009; CAL-P077
ships the instrument and the plan, and the exclusion goes to pre-cert and Alex
MC first. Everything here is **pure** — no session, no I/O, no clock — because
there is no local Postgres in this sandbox and a DB-bound decision is an
untested one. The reader that supplies rows is
``backend/scripts/measure_price_provenance.py``.

Gate 0 / ruling (e): the SQL below re-derives the census population OUTSIDE
``precompute_calibration.py``, and it is held to the substitute-reader standard
rather than trusted — :data:`PROVENANCE_FOLD_SQL` reproduced
``ARTIFACT-CAL-P076-1978-ALL-CELLS-CENSUS.json``'s ``ece_complete`` and
``n_complete`` on **49 of 49 cells** (hockey/container_member 41.00 / 1,514 /
-6.58, identical to two decimals). A reader that cannot reproduce the artifact
it extends is a second opinion, not an instrument.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, Mapping, Sequence

# ---------------------------------------------------------------------------
# The two axes
# ---------------------------------------------------------------------------

#: Which price the curve actually used, and who chose it.
PRICE_CP_ABSENT = "cp_absent"
PRICE_CP_EQ_OPEN = "cp_eq_open"
PRICE_CP_MOVED = "cp_moved"
PRICE_CLASSES: tuple[str, ...] = (PRICE_CP_ABSENT, PRICE_CP_EQ_OPEN, PRICE_CP_MOVED)

#: When our EARLIEST observation of the outcome was taken.
#:
#: ``no_capture_ts`` is its own class and is never folded into ``pregame``. A
#: missing ``opening_captured_at`` means we do not know when we first looked,
#: and "we did not record it" resolving to the reassuring reading is gotcha #53
#: at the top of the product's most-cited number.
CAPTURE_PREGAME = "pregame"
CAPTURE_AFTER_COMMENCE = "after_commence"
CAPTURE_AFTER_RESOLUTION = "after_resolution"
CAPTURE_NO_TS = "no_capture_ts"
CAPTURE_CLASSES: tuple[str, ...] = (
    CAPTURE_PREGAME,
    CAPTURE_AFTER_COMMENCE,
    CAPTURE_AFTER_RESOLUTION,
    CAPTURE_NO_TS,
)

#: Grade classes, mirrored from ``app.utils.cohort_cell_census`` so a fold here
#: can be compared with that census cell-for-cell. Re-stated rather than
#: imported: this module is the SUBSTITUTE reader, and a substitute that imports
#: its subject's definitions cannot disagree with it, which is the whole value.
GRADE_COMPLETE = "complete"
GRADE_INCOMPLETE = "incomplete"
GRADE_NEVER = "never"

#: The population, restated from ``app.utils.cohort_cell_census`` for the same
#: reason. If these ever diverge the reconciliation below fails loudly, which is
#: the point of duplicating them.
POPULATION_SOURCE = "polymarket"
POPULATION_STATUS = "resolved"
POPULATION_MARKET_TYPES: tuple[str, ...] = ("quantity", "container_member")

#: Below this an ECE is ABSENT with a reason, never a number. Matches
#: ``cohort_cell_census.MIN_CELL_N``.
MIN_CELL_N = 30

#: The curve price, verbatim from ``_calibration_population_ctes``' default.
#: Duplicated deliberately (see the module docstring on ruling (e)) and pinned
#: by ``tests/test_calibration_price_provenance_p077.py`` against the live
#: default, so a change to the curve price cannot silently orphan this reader.
CURVE_PRICE = "COALESCE(fo.calibration_probability, fo.opening_probability)"


# ---------------------------------------------------------------------------
# The reader's SQL — one statement, one cell, <= 3 * 4 * 3 * 10 grouped rows
# ---------------------------------------------------------------------------

#: One cell's fold, on the census population, with the two new axes added.
#:
#: ``{cat}`` / ``{mt}`` are the cell; ``{k}`` / ``{m}`` are a ``MOD`` partition so
#: an oversized cell can be walked in pieces without an ``ORDER BY id`` pkey walk
#: (CAL-P074's density trap — a cell-scoped ordered walk filters millions of ids
#: for a thinly-scattered cell and hits ``statement_timeout``). ``k=1`` served
#: every one of the 49 cells inside the 10 s ``db-query`` row budget; the
#: partition exists for the read path that does not have that headroom.
#:
#: The three trailing predicates are ``_BINS_SQL``'s, verbatim, and they are what
#: make this reproduce the census rather than merely resemble it.
PROVENANCE_FOLD_SQL = """
SELECT CASE WHEN fo.calibration_probability IS NULL THEN 'cp_absent'
            WHEN fo.calibration_probability = fo.opening_probability THEN 'cp_eq_open'
            ELSE 'cp_moved' END AS price_class,
       CASE WHEN fo.opening_captured_at IS NULL THEN 'no_capture_ts'
            WHEN fm.resolution_date IS NOT NULL
                 AND fo.opening_captured_at > fm.resolution_date THEN 'after_resolution'
            WHEN fm.commence_time IS NOT NULL
                 AND fo.opening_captured_at > fm.commence_time THEN 'after_commence'
            ELSE 'pregame' END AS capture_class,
       CASE WHEN NOT EXISTS (SELECT 1 FROM futures_outcomes f2
                             WHERE f2.market_id = fo.market_id
                               AND f2.resolution_source IS NULL) THEN 'complete'
            WHEN EXISTS (SELECT 1 FROM futures_outcomes f3
                         WHERE f3.market_id = fo.market_id
                           AND f3.resolution_source IS NOT NULL) THEN 'incomplete'
            ELSE 'never' END AS grade,
       LEAST(FLOOR({curve_price} * 10), 9)::int AS bin,
       COUNT(*) AS n,
       SUM({curve_price}) AS sum_prob,
       SUM(CASE WHEN fo.is_winner THEN 1 ELSE 0 END) AS winners
FROM futures_outcomes fo
JOIN futures_markets fm ON fm.id = fo.market_id
WHERE fm.source = '{source}'
  AND fm.status = '{status}'
  AND fm.market_type IN ({types})
  AND COALESCE(fm.llm_sport_category, 'uncategorized') = '{cat}'
  AND COALESCE(fm.market_type, 'unknown') = '{mt}'
  AND MOD(fm.id, {k}) = {m}
  AND {curve_price} > 0
  AND {curve_price} < 1
  AND fo.opening_probability IS NOT NULL
  AND fo.is_winner IS NOT NULL
GROUP BY 1, 2, 3, 4
"""

#: CAL-P085 (#2087) — the SAME fold, at the granularity the apply actually runs at.
#:
#: :data:`PROVENANCE_FOLD_SQL` ends ``GROUP BY 1, 2, 3, 4``. Market identity is
#: aggregated away **in SQL**, before any Python selector can see it, so
#: :class:`FoldRow` carries none and a whole-market policy is not merely
#: unimplemented on that structure — it is **not expressible** on it.
#: ``C-APPLY-PRE-WHICHPRICE-R2`` returned BLOCK on exactly that (P1 #3), and it
#: was right to: ruling 103 approves an exclusion that drops **whole markets,
#: winners and losers together**, and the ``3.7630 -> 1.7662 pp`` headline was
#: measured leg-by-leg. Two different predicates, one number.
#:
#: The repair is to **aggregate legs -> market BEFORE folding**, not to carry a
#: market id through the fold. Carrying the id would return one row per market
#: (464,777 of them) through a rail that truncates at 1,000 and would have to be
#: re-aggregated in Python anyway. Aggregating first keeps the statement's output
#: bounded by ``grade x bin x 3 x 3 x 3`` and leaves the arithmetic where the
#: pure module can test it.
#:
#: **The market-level levels are ORDERED, not flags.** Each is a three-level
#: ladder whose top level implies the middle one, which is what lets policies
#: B/C/D/E each be one comparison instead of a bit-vector:
#:
#: ``mkt_price_level``     ``all_moved`` => ``no_absent`` => ``has_absent``
#: ``mkt_capture_level``   ``all_pregame_or_nots`` => ``no_after_res`` => ``has_after_res``
#:
#: ``mkt_capture_level_pop`` is the same capture ladder computed over **only the
#: legs the curve actually reads** (the ``FILTER`` clause), against the plain one
#: computed over **every leg of the market**. The apply's CTE is an unfiltered
#: ``EXISTS`` over ``futures_outcomes``, and ruling 103's own
#: ``101 mixed markets in 464,777`` came from :data:`LEG_SPLIT_SQL`, which is
#: likewise unfiltered — so the **all-legs** ladder is the one that will run and
#: the **population-legs** ladder is the sensitivity. They are measured together
#: because a leg the curve drops can still be the leg that condemns the market,
#: and "which legs vote" is a design choice this program had never written down.
#:
#: ``grade`` moves into the CTE as two boolean aggregates. It was already a
#: market-level property computed by two correlated ``EXISTS`` subqueries **per
#: row**; expressing it as ``bool_or`` over the same legs is identical by
#: construction (the cell predicates are all on ``fm``, so a market is wholly in
#: or wholly out of a cell) and is what buys back the CTE's extra scan.
#:
#: ``MOD(fm.id, {k})`` partitioning stays SAFE here: it partitions on the MARKET
#: key, and every aggregate below is within-market, so no market is ever split
#: across two statements. A partitioned run and a ``k=1`` run are the same fold.
WHOLE_MARKET_FOLD_SQL = """
WITH mkt AS (
    SELECT fo.market_id AS market_id,
           BOOL_OR(fo.resolution_source IS NULL) AS any_ungraded,
           BOOL_OR(fo.resolution_source IS NOT NULL) AS any_graded,
           BOOL_OR(fo.calibration_probability IS NULL) AS any_absent,
           BOOL_AND(fo.calibration_probability IS NOT NULL
                    AND fo.calibration_probability IS DISTINCT FROM fo.opening_probability
                   ) AS all_moved,
           BOOL_OR(fo.opening_captured_at IS NOT NULL
                   AND fm.resolution_date IS NOT NULL
                   AND fo.opening_captured_at > fm.resolution_date) AS any_after_res,
           BOOL_AND(fo.opening_captured_at IS NULL
                    OR (NOT (fm.resolution_date IS NOT NULL
                             AND fo.opening_captured_at > fm.resolution_date)
                        AND NOT (fm.commence_time IS NOT NULL
                                 AND fo.opening_captured_at > fm.commence_time))
                   ) AS all_pregame_or_nots,
           BOOL_OR(fo.opening_captured_at IS NOT NULL
                   AND fm.resolution_date IS NOT NULL
                   AND fo.opening_captured_at > fm.resolution_date)
               FILTER (WHERE {curve_price} > 0 AND {curve_price} < 1
                         AND fo.opening_probability IS NOT NULL
                         AND fo.is_winner IS NOT NULL) AS any_after_res_pop,
           BOOL_AND(fo.opening_captured_at IS NULL
                    OR (NOT (fm.resolution_date IS NOT NULL
                             AND fo.opening_captured_at > fm.resolution_date)
                        AND NOT (fm.commence_time IS NOT NULL
                                 AND fo.opening_captured_at > fm.commence_time))
                   )
               FILTER (WHERE {curve_price} > 0 AND {curve_price} < 1
                         AND fo.opening_probability IS NOT NULL
                         AND fo.is_winner IS NOT NULL) AS all_pregame_or_nots_pop
    FROM futures_outcomes fo
    JOIN futures_markets fm ON fm.id = fo.market_id
    WHERE fm.source = '{source}'
      AND fm.status = '{status}'
      AND fm.market_type IN ({types})
      AND COALESCE(fm.llm_sport_category, 'uncategorized') = '{cat}'
      AND COALESCE(fm.market_type, 'unknown') = '{mt}'
      AND MOD(fm.id, {k}) = {m}
    GROUP BY 1
)
SELECT CASE WHEN NOT mkt.any_ungraded THEN 'complete'
            WHEN mkt.any_graded THEN 'incomplete'
            ELSE 'never' END AS grade,
       LEAST(FLOOR({curve_price} * 10), 9)::int AS bin,
       CASE WHEN mkt.all_moved THEN 'all_moved'
            WHEN NOT mkt.any_absent THEN 'no_absent'
            ELSE 'has_absent' END AS mkt_price_level,
       CASE WHEN mkt.all_pregame_or_nots THEN 'all_pregame_or_nots'
            WHEN NOT mkt.any_after_res THEN 'no_after_res'
            ELSE 'has_after_res' END AS mkt_capture_level,
       CASE WHEN mkt.all_pregame_or_nots_pop IS NULL
                 OR mkt.any_after_res_pop IS NULL THEN 'unknown'
            WHEN mkt.all_pregame_or_nots_pop THEN 'all_pregame_or_nots'
            WHEN NOT mkt.any_after_res_pop THEN 'no_after_res'
            ELSE 'has_after_res' END AS mkt_capture_level_pop,
       COUNT(*) AS n,
       SUM({curve_price}) AS sum_prob,
       SUM(CASE WHEN fo.is_winner THEN 1 ELSE 0 END) AS winners
FROM futures_outcomes fo
JOIN futures_markets fm ON fm.id = fo.market_id
JOIN mkt ON mkt.market_id = fo.market_id
WHERE fm.source = '{source}'
  AND fm.status = '{status}'
  AND fm.market_type IN ({types})
  AND COALESCE(fm.llm_sport_category, 'uncategorized') = '{cat}'
  AND COALESCE(fm.market_type, 'unknown') = '{mt}'
  AND MOD(fm.id, {k}) = {m}
  AND {curve_price} > 0
  AND {curve_price} < 1
  AND fo.opening_probability IS NOT NULL
  AND fo.is_winner IS NOT NULL
GROUP BY 1, 2, 3, 4, 5
"""

#: Does the exclusion split any market's legs? The design rests on the answer
#: being ~zero, so it is a query and not an assumption.
LEG_SPLIT_SQL = """
WITH per_market AS (
    SELECT fo.market_id,
           COUNT(*) AS legs,
           COUNT(*) FILTER (
               WHERE fm.resolution_date IS NOT NULL
                 AND fo.opening_captured_at > fm.resolution_date
           ) AS legs_after_resolution
    FROM futures_outcomes fo
    JOIN futures_markets fm ON fm.id = fo.market_id
    WHERE fm.source = '{source}'
      AND fm.status = '{status}'
      AND fm.market_type IN ({types})
      AND COALESCE(fm.llm_sport_category, 'uncategorized') = '{cat}'
      AND COALESCE(fm.market_type, 'unknown') = '{mt}'
      AND MOD(fm.id, {k}) = {m}
    GROUP BY 1
)
SELECT COUNT(*) AS markets,
       COUNT(*) FILTER (WHERE legs_after_resolution = legs) AS all_after,
       COUNT(*) FILTER (WHERE legs_after_resolution = 0) AS none_after,
       COUNT(*) FILTER (
           WHERE legs_after_resolution > 0 AND legs_after_resolution < legs
       ) AS mixed
FROM per_market
"""

#: Is there ANY earlier quote to re-price a hindsight row against? This is the
#: query that decides re-price vs exclude, so it is part of the instrument and
#: not a one-off. It answered 0 / 0 / 32 across the three worst cells.
REPRICE_FEASIBILITY_SQL = """
SELECT COUNT(*) AS n_after_resolution,
       COUNT(*) FILTER (WHERE EXISTS (
           SELECT 1 FROM futures_odds_snapshots s
           WHERE s.outcome_id = fo.id
             AND s.captured_at < fm.commence_time
             AND s.probability > 0 AND s.probability < 1
       )) AS with_pre_commence_snapshot,
       COUNT(*) FILTER (WHERE EXISTS (
           SELECT 1 FROM futures_odds_snapshots s
           WHERE s.outcome_id = fo.id
             AND s.captured_at < fm.resolution_date
             AND s.probability > 0 AND s.probability < 1
       )) AS with_pre_resolution_snapshot,
       COUNT(*) FILTER (WHERE EXISTS (
           SELECT 1 FROM futures_odds_snapshots s WHERE s.outcome_id = fo.id
       )) AS with_any_snapshot
FROM futures_outcomes fo
JOIN futures_markets fm ON fm.id = fo.market_id
WHERE fm.source = '{source}'
  AND fm.status = '{status}'
  AND fm.market_type IN ({types})
  AND COALESCE(fm.llm_sport_category, 'uncategorized') = '{cat}'
  AND COALESCE(fm.market_type, 'unknown') = '{mt}'
  AND MOD(fm.id, {k}) = {m}
  AND fm.resolution_date IS NOT NULL
  AND fo.opening_captured_at > fm.resolution_date
  AND {curve_price} > 0
  AND {curve_price} < 1
  AND fo.opening_probability IS NOT NULL
"""


def _types_tuple() -> str:
    return ", ".join(f"'{t}'" for t in POPULATION_MARKET_TYPES)


def render_sql(template: str, *, cat: str, mt: str, k: int = 1, m: int = 0) -> str:
    """Render one of the templates for a cell.

    ``cat``/``mt`` are interpolated rather than bound because these run through
    the admin ``db-query`` read rail, which takes SQL text and no parameters.
    They are therefore validated here instead of trusted: a cell name is a slug
    from ``llm_sport_category`` / ``market_type``, and anything else is a
    programming error caught at render time rather than a string reaching the
    database.
    """
    for label, value in (("cat", cat), ("mt", mt)):
        if not isinstance(value, str) or not value:
            raise ValueError(f"{label} must be a non-empty string")
        if not all(ch.isalnum() or ch in "_-" for ch in value):
            raise ValueError(f"{label} is not a cell slug: {value!r}")
    if not isinstance(k, int) or k < 1:
        raise ValueError("k must be a positive int")
    if not isinstance(m, int) or not (0 <= m < k):
        raise ValueError("m must satisfy 0 <= m < k")
    return template.format(
        curve_price=CURVE_PRICE,
        source=POPULATION_SOURCE,
        status=POPULATION_STATUS,
        types=_types_tuple(),
        cat=cat,
        mt=mt,
        k=k,
        m=m,
    )


# ---------------------------------------------------------------------------
# The pure fold
# ---------------------------------------------------------------------------


class FoldRow:
    """One grouped row of :data:`PROVENANCE_FOLD_SQL`, validated.

    A plain tuple would do, and did, in the throwaway version of this. It is a
    class because the reader hands back rows from a JSON round trip where
    ``sum_prob`` arrives as a ``str`` (numeric) and everything else as ``int``,
    and a silent ``str`` in an arithmetic position is how a fold produces a
    number that is wrong rather than an error that is loud.
    """

    __slots__ = ("price_class", "capture_class", "grade", "bin", "n", "sum_prob", "winners")

    def __init__(
        self,
        price_class: str,
        capture_class: str,
        grade: str,
        bin_: int,
        n: int,
        sum_prob: float,
        winners: int,
    ) -> None:
        if price_class not in PRICE_CLASSES:
            raise ValueError(f"unknown price_class {price_class!r}")
        if capture_class not in CAPTURE_CLASSES:
            raise ValueError(f"unknown capture_class {capture_class!r}")
        if grade not in (GRADE_COMPLETE, GRADE_INCOMPLETE, GRADE_NEVER):
            raise ValueError(f"unknown grade {grade!r}")
        self.price_class = price_class
        self.capture_class = capture_class
        self.grade = grade
        self.bin = int(bin_)
        self.n = int(n)
        self.sum_prob = float(sum_prob)
        self.winners = int(winners)
        if self.n <= 0:
            raise ValueError("n must be positive")
        if not (0 <= self.bin <= 9):
            raise ValueError(f"bin out of range: {self.bin}")
        if not (0 <= self.winners <= self.n):
            raise ValueError(f"winners {self.winners} outside 0..{self.n}")

    @classmethod
    def from_row(cls, row: Sequence[Any]) -> "FoldRow":
        if len(row) != 7:
            raise ValueError(f"expected 7 columns, got {len(row)}")
        return cls(str(row[0]), str(row[1]), str(row[2]), row[3], row[4], row[5], row[6])


Selector = Callable[[FoldRow], bool]


def ece(rows: Iterable[FoldRow], keep: Selector | None = None) -> dict[str, Any]:
    """Bin-pooled ECE over the selected rows.

    ``ECE = sum_b (n_b / N) * |mean_price_b - winrate_b|``, the same fold
    ``cohort_cell_census.fold_cells`` performs, so a selector of "everything with
    grade complete" must reproduce that census's ``ece_complete`` exactly. It
    does, on 49 of 49 cells.

    Returns ``ece``/``gap`` as **percentage points** and ``n`` as a count.
    ``ece`` is ``None`` below :data:`MIN_CELL_N` with a ``reason`` — an absent
    measurement is never a clean zero.
    """
    bins: dict[int, list[float]] = {}
    for row in rows:
        if keep is not None and not keep(row):
            continue
        slot = bins.setdefault(row.bin, [0.0, 0.0, 0.0])
        slot[0] += row.n
        slot[1] += row.sum_prob
        slot[2] += row.winners

    total = sum(int(s[0]) for s in bins.values())
    if total == 0:
        return {"ece": None, "gap": None, "n": 0, "reason": "empty"}
    value = sum(
        (s[0] / total) * abs((s[1] / s[0]) - (s[2] / s[0])) for s in bins.values()
    )
    gap = (
        sum(s[1] for s in bins.values()) - sum(s[2] for s in bins.values())
    ) / total
    out: dict[str, Any] = {
        "ece": round(value * 100, 4),
        "gap": round(gap * 100, 4),
        "n": total,
    }
    if total < MIN_CELL_N:
        out["ece"] = None
        out["reason"] = f"below_min_cell_n:{total}<{MIN_CELL_N}"
    return out


# ---------------------------------------------------------------------------
# The candidate policies
# ---------------------------------------------------------------------------


def _complete(row: FoldRow) -> bool:
    return row.grade == GRADE_COMPLETE


#: Every candidate, evaluated on grade ``complete`` so the twins stay honest.
#:
#: ``A_today`` is not a proposal — it is the control, and every Δ is stated
#: against it. The rest are the options ruling (d) put on the table, plus the one
#: the measurement produced.
POLICIES: dict[str, Selector] = {
    # The curve as it ships today.
    "A_today": _complete,
    # Codex's round-2 probe, promoted to a policy: drop only the read-side
    # fallback. Measured to catch under half the damage, because the writer-side
    # fallback (cp_eq_open) is the larger class.
    "B_exclude_cp_absent": lambda r: _complete(r) and r.price_class != PRICE_CP_ABSENT,
    # THE PROPOSAL. Drop rows whose earliest observation postdates the answer.
    "C_exclude_hindsight": lambda r: _complete(r)
    and r.capture_class != CAPTURE_AFTER_RESOLUTION,
    # Drop every fallback price of either kind. Measured to be WORSE than C on
    # cells where the fallback is honest (tennis +6.0 pp, +5.4 pp) — it throws
    # away real prices to catch a mechanism that is not there.
    "D_moved_price_only": lambda r: _complete(r) and r.price_class == PRICE_CP_MOVED,
    # The strictest reading of capture age. Keeps only what we saw before the
    # contest began, plus rows whose capture time we never recorded.
    "E_pregame_or_unknown_ts": lambda r: _complete(r)
    and r.capture_class in (CAPTURE_PREGAME, CAPTURE_NO_TS),
}

#: The policy CAL-P077 proposes, named once so a caller cannot pick it by
#: string and drift.
PROPOSED_POLICY = "C_exclude_hindsight"


def policy_table(rows: Iterable[FoldRow]) -> dict[str, dict[str, Any]]:
    """Every ROW-LEVEL policy's ECE for one cell, each with its Δ against ``A_today``.

    Kept, unchanged in behaviour, as the thing the whole-market table is compared
    AGAINST. It is not the apply's predicate — see :data:`WHOLE_MARKET_POLICIES`.
    """
    return _table(list(rows), POLICIES)


# ---------------------------------------------------------------------------
# CAL-P085 (#2087) — the same policies, at the apply's granularity
# ---------------------------------------------------------------------------

#: The two market-level ladders emitted by :data:`WHOLE_MARKET_FOLD_SQL`, top
#: level first. Ordered, and the order is load-bearing: the top level implies
#: the middle one, so ``!= bottom`` and ``== top`` are the only two comparisons
#: any whole-market policy needs.
MARKET_PRICE_LEVELS: tuple[str, ...] = ("all_moved", "no_absent", "has_absent")
MARKET_CAPTURE_LEVELS: tuple[str, ...] = (
    "all_pregame_or_nots",
    "no_after_res",
    "has_after_res",
)

#: What the SQL emits when a market's population-legs ladder is undefined — i.e.
#: the ``FILTER`` matched nothing, so ``BOOL_AND``/``BOOL_OR`` returned NULL.
#:
#: This cannot happen for a market that reaches the outer SELECT, because the
#: outer SELECT applies the same predicate the FILTER does, so any market in the
#: result has at least one population leg. It is emitted as its own value rather
#: than folded into a level precisely because it cannot happen: gotcha #53 says a
#: reading that only exists when an assumption broke must not resolve to the
#: reassuring value. :class:`MarketFoldRow` raises on it.
MARKET_LEVEL_UNKNOWN = "unknown"


class MarketFoldRow:
    """One grouped row of :data:`WHOLE_MARKET_FOLD_SQL`, validated.

    Duck-compatible with :class:`FoldRow` on ``bin``/``n``/``sum_prob``/
    ``winners``, so :func:`ece` folds either without knowing which it has. It
    deliberately does NOT carry ``price_class``/``capture_class``: those are
    per-leg, this row is a group of legs whose only shared classification is
    their market's, and a per-leg attribute here would invite exactly the
    row-level selector that #2087 is about.
    """

    __slots__ = (
        "grade",
        "bin",
        "mkt_price_level",
        "mkt_capture_level",
        "mkt_capture_level_pop",
        "n",
        "sum_prob",
        "winners",
    )

    def __init__(
        self,
        grade: str,
        bin_: int,
        mkt_price_level: str,
        mkt_capture_level: str,
        mkt_capture_level_pop: str,
        n: int,
        sum_prob: float,
        winners: int,
    ) -> None:
        if grade not in (GRADE_COMPLETE, GRADE_INCOMPLETE, GRADE_NEVER):
            raise ValueError(f"unknown grade {grade!r}")
        if mkt_price_level not in MARKET_PRICE_LEVELS:
            raise ValueError(f"unknown mkt_price_level {mkt_price_level!r}")
        for label, value in (
            ("mkt_capture_level", mkt_capture_level),
            ("mkt_capture_level_pop", mkt_capture_level_pop),
        ):
            if value == MARKET_LEVEL_UNKNOWN:
                raise ValueError(
                    f"{label} is {MARKET_LEVEL_UNKNOWN!r}: a market reached the fold with no "
                    "population leg, which the outer predicate makes impossible — the fold and "
                    "the filter have drifted apart"
                )
            if value not in MARKET_CAPTURE_LEVELS:
                raise ValueError(f"unknown {label} {value!r}")
        self.grade = grade
        self.bin = int(bin_)
        self.mkt_price_level = mkt_price_level
        self.mkt_capture_level = mkt_capture_level
        self.mkt_capture_level_pop = mkt_capture_level_pop
        self.n = int(n)
        self.sum_prob = float(sum_prob)
        self.winners = int(winners)
        if self.n <= 0:
            raise ValueError("n must be positive")
        if not (0 <= self.bin <= 9):
            raise ValueError(f"bin out of range: {self.bin}")
        if not (0 <= self.winners <= self.n):
            raise ValueError(f"winners {self.winners} outside 0..{self.n}")

    @classmethod
    def from_row(cls, row: Sequence[Any]) -> "MarketFoldRow":
        if len(row) != 8:
            raise ValueError(f"expected 8 columns, got {len(row)}")
        return cls(
            str(row[0]),
            row[1],
            str(row[2]),
            str(row[3]),
            str(row[4]),
            row[5],
            row[6],
            row[7],
        )


MarketSelector = Callable[[MarketFoldRow], bool]


def _wm_complete(row: MarketFoldRow) -> bool:
    return row.grade == GRADE_COMPLETE


#: Policies A-E again, each lifted to the market.
#:
#: **The lift is one rule applied five times, not five judgement calls:** a
#: whole-market policy keeps a market iff EVERY leg of that market satisfies the
#: row-level selector of the same name. That is the only lift consistent with
#: ruling 103's "winners and losers together", and it is what makes the two
#: tables comparable cell-for-cell.
#:
#: ``A_today`` is unchanged by the lift and that is a fact worth stating rather
#: than a coincidence: ``grade`` is ALREADY market-level (it is computed from the
#: market's outcomes), so the control is the same population under both
#: granularities — which is what makes it a usable reconciliation key.
WHOLE_MARKET_POLICIES: dict[str, MarketSelector] = {
    "A_today": _wm_complete,
    "B_exclude_cp_absent": lambda r: _wm_complete(r)
    and r.mkt_price_level != "has_absent",
    "C_exclude_hindsight": lambda r: _wm_complete(r)
    and r.mkt_capture_level != "has_after_res",
    "D_moved_price_only": lambda r: _wm_complete(r)
    and r.mkt_price_level == "all_moved",
    "E_pregame_or_unknown_ts": lambda r: _wm_complete(r)
    and r.mkt_capture_level == "all_pregame_or_nots",
}

#: The sensitivity: the same two capture policies decided by **only the legs the
#: curve reads**, instead of every leg of the market.
#:
#: Not a proposal. It exists so the artifact can say which legs voted and what
#: the other reading would have given, because the apply's CTE picks one and
#: nothing in ruling 103 argues for the choice — it simply makes it.
WHOLE_MARKET_POPULATION_LEG_POLICIES: dict[str, MarketSelector] = {
    "C_exclude_hindsight": lambda r: _wm_complete(r)
    and r.mkt_capture_level_pop != "has_after_res",
    "E_pregame_or_unknown_ts": lambda r: _wm_complete(r)
    and r.mkt_capture_level_pop == "all_pregame_or_nots",
}


def _table(
    rows: Sequence[Any], policies: Mapping[str, Any], baseline_name: str = "A_today"
) -> dict[str, dict[str, Any]]:
    baseline = ece(rows, policies[baseline_name]) if baseline_name in policies else None
    out: dict[str, dict[str, Any]] = {}
    for name, selector in policies.items():
        result = ece(rows, selector)
        if baseline is None:
            result["delta_ece"] = None
        elif result["ece"] is not None and baseline["ece"] is not None:
            result["delta_ece"] = round(result["ece"] - baseline["ece"], 4)
        else:
            result["delta_ece"] = None
        out[name] = result
    return out


def market_policy_table(rows: Iterable[MarketFoldRow]) -> dict[str, Any]:
    """Every WHOLE-MARKET policy's ECE for one cell, plus the legs-that-vote sensitivity."""
    materialised = list(rows)
    out: dict[str, Any] = {
        "all_legs": _table(materialised, WHOLE_MARKET_POLICIES),
    }
    baseline = out["all_legs"]["A_today"]
    pop = _table(materialised, WHOLE_MARKET_POPULATION_LEG_POLICIES, baseline_name="")
    for name, result in pop.items():
        result["delta_ece"] = (
            None
            if result["ece"] is None or baseline["ece"] is None
            else round(result["ece"] - baseline["ece"], 4)
        )
        # The number a reader actually wants: does it matter which legs vote?
        allv = out["all_legs"][name]
        result["delta_vs_all_legs_ece"] = (
            None
            if result["ece"] is None or allv["ece"] is None
            else round(result["ece"] - allv["ece"], 4)
        )
        result["delta_vs_all_legs_n"] = result["n"] - allv["n"]
    out["population_legs"] = pop
    return out


def market_level_shares(rows: Iterable[MarketFoldRow]) -> dict[str, dict[str, float]]:
    """Share of the complete-graded cell sitting at each rung of each ladder."""
    materialised = [r for r in rows if _wm_complete(r)]
    total = sum(r.n for r in materialised)
    if total == 0:
        return {"price": {}, "capture": {}, "capture_population_legs": {}}

    def share(attr: str, levels: Sequence[str]) -> dict[str, float]:
        return {
            level: round(
                sum(r.n for r in materialised if getattr(r, attr) == level) / total, 6
            )
            for level in levels
        }

    return {
        "price": share("mkt_price_level", MARKET_PRICE_LEVELS),
        "capture": share("mkt_capture_level", MARKET_CAPTURE_LEVELS),
        "capture_population_legs": share(
            "mkt_capture_level_pop", MARKET_CAPTURE_LEVELS
        ),
    }


def reconciles_with_row_fold(
    market_rows: Iterable[MarketFoldRow],
    row_rows: Iterable[FoldRow],
    *,
    tolerance_pp: float = 0.0005,
) -> dict[str, Any]:
    """Does the market-aware fold read the SAME population as the row-level one?

    The two statements share a WHERE clause verbatim, so ``A_today`` — the
    control, which no policy touches — must agree on ``n`` EXACTLY and on ``ece``
    to within float noise. This is the only check that can catch the new CTE
    quietly changing what gets counted, which is the failure that would make
    every number below it wrong in the same direction and therefore invisible.

    ``tolerance_pp`` is float-comparison slack, not population slack. ``n`` is
    compared for equality with no slack at all; the two reads are minutes apart
    but ``futures_outcomes`` rows for RESOLVED markets do not move, and a
    non-zero ``n_delta`` is reported rather than absorbed.
    """
    mine = ece(list(market_rows), WHOLE_MARKET_POLICIES["A_today"])
    theirs = ece(list(row_rows), POLICIES["A_today"])
    # ``n_delta`` is computed on BOTH paths and is never absent. It is the field
    # a reader quotes, and the below-floor / empty path is exactly when they are
    # most likely to quote it — an unmeasurable ECE does not make the row counts
    # unmeasurable. Omitting it here raised ``KeyError`` in the reader's own
    # summary line on a sweep where every market-aware read failed: the artifact
    # was already written, so the run died AFTER succeeding, with a traceback in
    # place of the honest "1 = partial sweep" exit.
    n_delta = mine["n"] - theirs["n"]
    if mine["ece"] is None or theirs["ece"] is None:
        return {
            "reconciled": None,
            "reason": mine.get("reason") or theirs.get("reason") or "no_ece",
            "n_delta": n_delta,
            "market_fold": mine,
            "row_fold": theirs,
        }
    delta = abs(mine["ece"] - theirs["ece"])
    return {
        "reconciled": bool(delta <= tolerance_pp and n_delta == 0),
        "delta_pp": round(delta, 6),
        "n_delta": n_delta,
        "market_fold": mine,
        "row_fold": theirs,
    }


def class_shares(rows: Iterable[FoldRow]) -> dict[str, dict[str, float]]:
    """Share of the complete-graded cell in each class on each axis.

    The hindsight share is the cell's *exposure* to the mechanism, and it is what
    makes the vacuity control checkable: a cell with a share near zero whose ECE
    moves under policy C would falsify the whole account.
    """
    materialised = [r for r in rows if _complete(r)]
    total = sum(r.n for r in materialised)
    if total == 0:
        return {"price": {}, "capture": {}}

    def share(attr: str, classes: Sequence[str]) -> dict[str, float]:
        return {
            cls: round(
                sum(r.n for r in materialised if getattr(r, attr) == cls) / total, 6
            )
            for cls in classes
        }

    return {
        "price": share("price_class", PRICE_CLASSES),
        "capture": share("capture_class", CAPTURE_CLASSES),
    }


def reconciles_with_census(
    rows: Iterable[FoldRow], census_cell: Mapping[str, Any], *, tolerance_pp: float = 0.15
) -> dict[str, Any]:
    """Does this reader reproduce the census cell it extends? (Ruling (e).)

    The substitute-reader standard, applied to itself. A reader that adds two
    axes to a published census and cannot reproduce that census on the axes they
    share is a second opinion, and CAL-P075 already measured what a second
    opinion costs: the cohort sweep counted rows the curve drops because it
    re-implemented the population.

    ``tolerance_pp`` is not slack for a wrong fold — the 49-cell reconciliation
    matched to two decimals. It absorbs population movement between the census
    and the re-read, which is real and signed: the two economics/politics cells
    drifted by 8-15 rows over the two hours between them.
    """
    materialised = list(rows)
    mine = ece(materialised, POLICIES["A_today"])
    theirs_ece = census_cell.get("ece_complete")
    theirs_n = census_cell.get("n_complete")

    if theirs_ece is None:
        return {
            "reconciled": None,
            "reason": "census_cell_has_no_ece_complete",
            "mine": mine,
        }
    if mine["ece"] is None:
        return {"reconciled": None, "reason": mine.get("reason", "no_ece"), "mine": mine}

    delta = abs(mine["ece"] - float(theirs_ece))
    return {
        "reconciled": delta <= tolerance_pp,
        "delta_pp": round(delta, 4),
        "mine": mine,
        "census": {"ece_complete": theirs_ece, "n_complete": theirs_n},
        "n_delta": (mine["n"] - int(theirs_n)) if theirs_n is not None else None,
    }
