"""The all-cells provenance census, as pure logic — #1978's worker, minus the database.

WHY THIS IS A WORKER AND NOT A QUERY, in one paragraph, so the next person does
not re-litigate it. ``GET /api/admin/cohort-provenance-split`` is the correct
full-population reader and it is *deployed*; it returns **HTTP 503 at 30.21 s**,
measured again by CAL-P075 AFTER the 40 h orphan backend was killed and the
vacuum reclaimed both tables — so bloat was never the cause. The planner drives
that query from a **Parallel Seq Scan on futures_outcomes** (155,184 of 177,891
total cost, CAL-P074's plan). Every selective predicate lives on
``futures_markets``, the side that is not driving, so **narrowing the filter does
not narrow the scan**: CAL-P074 measured the smallest reportable cell
(``cricket/container_member``, 0.44% of the population) time out on the same
10 s budget as the query over all 49 cells. A 12-to-76-minute job cannot be an
HTTP request, and no amount of making it a better query changes that.

WHAT DOES WORK, and it is the whole rail: ``fo.market_id = ANY(ARRAY[<ids>])``
bounds the plan where a join and a range predicate do not. Page an explicit id
roster, aggregate each page by that array, reduce the bin aggregates in Python.
Measured 645 markets/s on a quiet database and 101 markets/s against a live
producer beat — the same job, 6x apart, which is why nothing here is bounded by
a fixed wall-clock budget (ruling 089: a budget derived only from successes
cannot be corrected by the failures it causes). It checkpoints per page instead,
so a cancellation costs one page rather than the run.

THE ROSTER IS FLATTENED AND CATEGORY IS A **GROUPING KEY, NEVER A FILTER**, and
that single decision deletes two separate defects:

* **The id-space density trap** (CAL-P074). A per-cell roster query walks the
  primary key filtering as it goes, so its cost is ``1/density`` — the number of
  id-space pages crossed to collect ``n`` hits — and not the cell's size.
  ``tennis/container_member`` (27,739 markets) took **504 s** where the LARGER
  ``table_tennis/quantity`` (35,999) took **56 s**. A single monotonic walk over
  the whole population never pays that: every page is dense by construction,
  because every row it crosses is in the population.
* **Sharding by category is UNSOUND, not merely slow** — CAL-P075 measured this
  and it is why the note on ``repair_pm_never_graded._CENSUS_SQL`` saying "shard
  by category and retry" must not be followed. Categories are not closed under
  the virtual-question identity: ``geopolitics``'s groups also contain **38
  ``politics``** markets and its events also contain **47 ``tennis`` + 2
  ``soccer``** markets, so re-deriving ``group_sizes``/``event_sizes`` over a
  category-scoped population flips the ``>= 3`` gate and silently reassigns
  ``vm_id``. **That hazard does not apply to THIS census** — it reads the raw
  provenance population with no virtual-market identity and no dedup, exactly as
  the endpoint does — and the reason it does not apply is that category is never
  a filter here. Stated rather than left implicit, because the two populations
  are one function call apart and conflating them is a one-line mistake.

THE TWINS (Fable, CAL-P075 item 4, from the rebaseline ruling's honest-GREEN
form). A single blended ECE over this cohort averages three populations that
mean different things, and the blend hides which one moves it:

* ``complete``   — every leg of the market carries a ``resolution_source``.
  Something looked at the whole market and graded all of it.
* ``incomplete`` — SOME legs carry one and some do not. A partial verdict.
  ``repair_pm_never_graded`` deliberately leaves these to the authority ladder
  ("a partially-graded market is left ... rather than half rewritten here"), so
  **nobody is measuring them** — which is exactly why they get their own twin.
* ``never``      — no leg carries one. ``is_winner = false`` here is the column
  DEFAULT standing in for a grade nobody wrote (#1912's whole cohort), so its
  ECE is an artifact of the default and not a calibration fact.

Reporting ``ece_complete`` and ``ece_incomplete`` as twins rather than one
number is the honest-GREEN form: a cell is only GREEN when the population it is
green ON is stated. ``ece_all`` and ``ece_venue`` are kept unchanged so the
existing endpoint's contract is preserved and the twins are additive.

EVERYTHING IN THIS MODULE IS PURE. No session, no I/O, no clock. The worker in
``app.tasks.cohort_cell_census_worker`` supplies rows and time; every decision
that could be wrong is made here, where a test can reach it without a database
(there is no local Postgres in this sandbox, so a DB-bound decision is an
untested one).
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

#: Schema of the persisted artifact. Bump when the payload shape changes; the
#: reader refuses an unexpected version rather than guessing at the difference.
CENSUS_SCHEMA = "cohort-cell-census/v2"

#: Durable slot for the checkpoint + final artifact. One identity, overwritten
#: as the run advances, so a resumed run and a reader see the same address.
CENSUS_IDENTITY = "calibration:cohort_cell_census"

#: The population, stated once. Mirrors ``GET /api/admin/cohort-provenance-split``
#: exactly — a second definition of one population is how a census ends up
#: describing rows the endpoint it replaces never counted.
POPULATION_SOURCE = "polymarket"
POPULATION_STATUS = "resolved"
POPULATION_MARKET_TYPES: tuple[str, ...] = ("quantity", "container_member")

#: Reporting floor. Below this an ECE is ABSENT with a reason, never a number.
#: Matches the endpoint's ``n < 30`` guard so the two cannot disagree.
MIN_CELL_N = 30

#: Grade classes. Order is the reporting order.
GRADE_COMPLETE = "complete"
GRADE_INCOMPLETE = "incomplete"
GRADE_NEVER = "never"
GRADE_CLASSES: tuple[str, ...] = (GRADE_COMPLETE, GRADE_INCOMPLETE, GRADE_NEVER)

# ---------------------------------------------------------------------------
# Calibration-truth eligibility — the SECOND axis, added by CAL-P093 (#1978).
#
# WHY THIS EXISTS, because the cell ranking it corrects was already being worked
# as a queue. The grade twins above ask "did anything grade this market?".
# Eligibility asks a different and, for a calibration number, prior question:
# "may the grade that exists GRADE A PUBLISHED FORECAST?" — see
# ``app.utils.resolution_authority.CALIBRATION_TRUTH_ELIGIBLE_SOURCES``. A leg
# graded ``pass2_loser`` is fully ``complete`` on the grade axis and is dropped
# by the published curve on the eligibility axis, so the two axes are orthogonal
# and a census that carries only the first reports an ECE for rows no user's
# curve ever contained.
#
# MEASURED, CAL-P093 (2026-08-24), the reason this is not a refactor:
# ``basketball/quantity`` reads **24.27 pp over n=13,067** unfiltered and
# **5.73 pp over n=2,104** restricted to truth-eligible legs. Of the 18.54 pp
# difference, the single largest term is 1,690 ``pass2_loser`` markets that are
# priced coherently (pair sum 0.9954) and carry **zero winning legs** — a
# resolved two-leg mutually-exclusive market in which nothing won. Those rows
# are already excluded from the published curve at
# ``precompute_calibration.py`` and they were never excluded here.
#
# ``ece_all`` / ``ece_venue`` / the grade twins are UNCHANGED and keep mirroring
# ``GET /api/admin/cohort-provenance-split``. This is additive, exactly as the
# grade twins were: the fix for a number that means the wrong thing is a second
# number that says which, not a redefinition of the first (gotcha #53 — an
# absent distinction and a made distinction must not share a rendering).
#
# NOT a re-grade. Nothing here writes ``is_winner`` (gotcha #21): the poison
# cohort is reported out of the eligible twin and left exactly where it is.
TRUTH_ELIGIBLE = "eligible"
TRUTH_INELIGIBLE = "ineligible"
TRUTH_CLASSES: tuple[str, ...] = (TRUTH_ELIGIBLE, TRUTH_INELIGIBLE)

#: Below this many ids a range that still times out is IRREDUCIBLE and must be
#: reported as an absence with its bounds, never halved into invisibility. 25 is
#: CAL-P066's floor, carried unchanged because it was measured, not chosen.
BISECT_FLOOR_IDS = 25


# ---------------------------------------------------------------------------
# Grade classification — the twins' discriminator
# ---------------------------------------------------------------------------


def classify_market_grade(legs_total: int, legs_graded: int) -> str:
    """``complete`` / ``incomplete`` / ``never`` for one market.

    The three-way split is the point. A two-way "graded vs not" collapses
    ``incomplete`` into whichever side the implementer happened to pick, and the
    two sides mean opposite things: a fully-graded market is EVIDENCE, a
    never-graded one is a DEFAULT wearing evidence's clothes (#1912), and a
    partially-graded one is neither — it is a market something started grading
    and did not finish, which is the only one of the three that implicates the
    grader rather than the data.

    ``legs_graded > legs_total`` cannot happen from the SQL (the graded count is
    a FILTER over the same rows), so it is not defended against with a clamp —
    a clamp would silently absorb the bug that produced it. It classifies as
    ``complete``, which is what equality means, and the reconciliation in
    :func:`reconcile_markets` is what would notice a count that is wrong.
    """
    if legs_total <= 0:
        # No legs at all is not a grade state; it is a market with nothing in
        # the population. Callers filter these out before they get here, so
        # reaching this is a caller bug and ``never`` is the conservative read:
        # it can only ever add rows to the cohort nobody trusts.
        return GRADE_NEVER
    if legs_graded <= 0:
        return GRADE_NEVER
    if legs_graded >= legs_total:
        return GRADE_COMPLETE
    return GRADE_INCOMPLETE


# ---------------------------------------------------------------------------
# Bin accumulation
# ---------------------------------------------------------------------------


def bin_key(
    league: str, market_type: str, grade: str, bucket: int, truth: str
) -> str:
    """A JSON-safe composite key.

    A string rather than a tuple because this dictionary is persisted into a
    JSONB checkpoint between beats, and a tuple key does not survive a
    round-trip through JSON — it comes back as a list, which is unhashable, and
    the resumed run would rebuild an empty accumulator while reporting the
    banked page count. That failure looks exactly like a working resume.

    ``truth`` is the fifth component as of ``v2``. It is REQUIRED and has no
    default: a default would let a v1-shaped caller fold every row into one
    eligibility class silently, and the resulting ``ece_eligible`` would equal
    ``ece_all`` — which is precisely the wrong number wearing the right name.
    The schema bump is what protects a persisted v1 checkpoint; the missing
    default is what protects a stale caller.
    """
    return f"{league}\x1f{market_type}\x1f{grade}\x1f{bucket}\x1f{truth}"


def parse_bin_key(key: str) -> tuple[str, str, str, int, str]:
    """Inverse of :func:`bin_key`. Raises on a malformed key rather than
    returning a default — a key we cannot parse is a checkpoint we cannot
    trust, and the run must fail loudly instead of reducing over a fragment.

    A v1 (four-part) key raises here rather than being upgraded in place. The
    checkpoint reader already refuses a version it does not expect
    (``expected_version=CENSUS_SCHEMA``), so reaching this with a short key
    means something bypassed that guard, and inventing the missing component is
    how a fold silently attributes ineligible rows to the eligible twin."""
    league, market_type, grade, bucket, truth = key.split("\x1f")
    return league, market_type, grade, int(bucket), truth


def fold_page(
    accumulator: dict[str, dict[str, float]],
    rows: Iterable[Any],
) -> dict[str, dict[str, float]]:
    """Add one page's bin aggregates into the running fold. Returns the same dict.

    **Idempotency is NOT claimed and must not be assumed.** Folding a page twice
    double-counts it. The caller's protection is the cursor: a page is banked
    with the cursor that produced it in the same checkpoint write, so a resume
    either has both or neither. This is called out because ``advance`` on the
    staged-futures cursor next door IS idempotent, and a reader who assumes the
    same here gets a census that is quietly 2x on one page.

    Rows carry ``league``, ``market_type``, ``grade``, ``truth``, ``bin``,
    ``n``, ``sum_prob``, ``winners`` — attribute access, so a SQLAlchemy ``Row``
    and a test's simple namespace are interchangeable. ``truth`` is read with
    plain attribute access and NOT ``getattr(row, "truth", ...)``: a row that
    has lost the column must raise, because the fallback value would land every
    row in one eligibility class and the twin would look measured.
    """
    for row in rows:
        key = bin_key(
            str(row.league),
            str(row.market_type),
            str(row.grade),
            int(row.bin),
            str(row.truth),
        )
        slot = accumulator.get(key)
        if slot is None:
            slot = {"n": 0.0, "sum_prob": 0.0, "winners": 0.0}
            accumulator[key] = slot
        slot["n"] += float(row.n or 0)
        slot["sum_prob"] += float(row.sum_prob or 0.0)
        slot["winners"] += float(row.winners or 0.0)
    return accumulator


# ---------------------------------------------------------------------------
# ECE
# ---------------------------------------------------------------------------


def ece_from_bins(bins: Sequence[Mapping[str, float]]) -> tuple[float | None, bool]:
    """``(ece_pp, used_fallback)`` over bin aggregates, n-weighted, 10-bin.

    Delegates to :func:`app.tasks.precompute_calibration._compute_horizon_mce`
    so this census and the published curve compute ECE with ONE definition. The
    local arithmetic below is a fallback for when that import fails, and it is
    labelled ``used_fallback=True`` all the way out to the response — an ECE
    computed by a different definition must never render unmarked beside one
    that was not. (That labelling is copied from
    ``GET /api/admin/cohort-provenance-split``, which already got this right.)

    Returns ``(None, False)`` below :data:`MIN_CELL_N`. Not ``0.0`` — a cell too
    small to measure has an ABSENT ECE, and a zero would rank it as the
    best-calibrated cell in the table.
    """
    total_n = sum(float(b.get("n") or 0) for b in bins)
    if total_n < MIN_CELL_N:
        return None, False
    populated = [dict(b) for b in bins if (b.get("n") or 0)]
    try:
        from app.tasks.precompute_calibration import _compute_horizon_mce

        value = _compute_horizon_mce(populated, weighted=True)
        if value is not None:
            return round(value, 2), False
    except Exception:  # noqa: BLE001 — a missing canonical impl must not lose the run
        pass
    total = 0.0
    for b in populated:
        n = float(b["n"])
        avg_p = float(b["sum_prob"]) / n
        avg_a = float(b["winners"]) / n
        total += n / total_n * abs(avg_p - avg_a)
    return round(total * 100, 2), True


def gap_from_bins(bins: Sequence[Mapping[str, float]]) -> float | None:
    """Signed mean(prob) - mean(actual) in pp, or ``None`` on an empty set.

    Kept beside the ECE because ECE is unsigned: two cells with the same 14 pp
    can be over- and under-confident respectively, and #1145's whole open
    question is a SIGN (the 0-10 band over-resolving +41.5 pp).
    """
    total_n = sum(float(b.get("n") or 0) for b in bins)
    if not total_n:
        return None
    avg_p = sum(float(b.get("sum_prob") or 0.0) for b in bins) / total_n
    avg_a = sum(float(b.get("winners") or 0.0) for b in bins) / total_n
    return round((avg_p - avg_a) * 100, 2)


# ---------------------------------------------------------------------------
# Bisection — never skip a timing-out range
# ---------------------------------------------------------------------------


def bisect_range(lo: int, hi: int) -> tuple[tuple[int, int], tuple[int, int]] | None:
    """Halve ``[lo, hi]`` by id, or ``None`` when it is irreducible.

    CAL-P066 got all 27 categories exact in 74 calls / 415 s by recursive
    id-range bisection where fixed sharding could not finish at all. The rule it
    encodes: **a range that times out is bisected, never skipped.** A skipped
    range and an empty range produce the same output (gotcha #53), so a census
    that skips reports fewer cells than exist and cannot tell you it did.

    ``None`` below :data:`BISECT_FLOOR_IDS` means the caller must record an
    ABSENCE with these bounds — an irreducible range is a real finding about the
    database, not a reason to drop rows quietly.
    """
    if hi <= lo or (hi - lo) < BISECT_FLOOR_IDS:
        return None
    mid = lo + (hi - lo) // 2
    return (lo, mid), (mid + 1, hi)


# ---------------------------------------------------------------------------
# Reconciliation — the check that caught the silent 10% read
# ---------------------------------------------------------------------------


def reconcile_markets(
    roster_totals: Mapping[str, int], paged_totals: Mapping[str, int]
) -> dict[str, Any]:
    """Compare the independently-obtained roster count against what paging saw.

    THIS IS THE CHECK THAT CAUGHT THE ONLY SILENT WRONG ANSWER SO FAR. Paging
    without ``ORDER BY id`` read 1,317 of ``basketball/quantity``'s 13,121
    markets, reported them as the cell, and produced plausible ECEs 3 pp off.
    Nothing errored, nothing looked short, and the only reason it was found is
    that the cheap ``GROUP BY`` over ``futures_markets`` alone (1.9 s, no join)
    gives a total that owes nothing to the paging rail.

    Two independent derivations of one count, compared. A mismatch is reported
    per cell and makes that cell ``measured: false`` — it does not raise, because
    the other 48 cells are still worth having, and it does not warn-and-continue,
    because a warning next to a number is read as the number.
    """
    cells = sorted(set(roster_totals) | set(paged_totals))
    mismatches = []
    for cell in cells:
        expected = int(roster_totals.get(cell, 0))
        seen = int(paged_totals.get(cell, 0))
        if expected != seen:
            mismatches.append(
                {"cell": cell, "roster": expected, "paged": seen, "delta": seen - expected}
            )
    return {
        "checked_cells": len(cells),
        "mismatched_cells": len(mismatches),
        "mismatches": mismatches,
        "ok": not mismatches,
    }


# ---------------------------------------------------------------------------
# Report assembly
# ---------------------------------------------------------------------------


def cell_id(league: str, market_type: str) -> str:
    return f"{league}/{market_type}"


def _bins_for(
    accumulator: Mapping[str, Mapping[str, float]],
    league: str,
    market_type: str,
    grades: Sequence[str],
    truths: Sequence[str] = TRUTH_CLASSES,
) -> list[dict[str, float]]:
    """The 10 bin aggregates for one cell restricted to ``grades`` (and ``truths``).

    ``truths`` defaults to BOTH classes so every existing caller keeps its
    existing population — the eligibility axis is opt-in at the call site, which
    is what makes ``ece_all``/``ece_venue``/the grade twins byte-identical to v1
    on the same rows.
    """
    out: dict[int, dict[str, float]] = {}
    for key, slot in accumulator.items():
        k_league, k_type, k_grade, k_bin, k_truth = parse_bin_key(key)
        if k_league != league or k_type != market_type or k_grade not in grades:
            continue
        if k_truth not in truths:
            continue
        agg = out.setdefault(k_bin, {"n": 0.0, "sum_prob": 0.0, "winners": 0.0})
        agg["n"] += float(slot.get("n") or 0)
        agg["sum_prob"] += float(slot.get("sum_prob") or 0.0)
        agg["winners"] += float(slot.get("winners") or 0.0)
    return list(out.values())


def build_report(
    *,
    accumulator: Mapping[str, Mapping[str, float]],
    roster_totals: Mapping[str, int],
    paged_totals: Mapping[str, int],
    failed_ranges: Sequence[Mapping[str, Any]] = (),
    complete: bool,
    elapsed_s: float,
    pages_done: int,
) -> dict[str, Any]:
    """The census artifact: one row per cell, with per-cell ``measured``.

    **Every cell in the roster appears, including the zeroes.** #1978's argument
    rests on a zero-fallback control (``politics/quantity`` at 8.88), so a census
    that lists only cells with a positive share deletes the comparison that makes
    the finding mean anything. The roster ``GROUP BY`` over ``futures_markets``
    alone costs 1.9 s and returns all of them — there is no excuse for a cell to
    be missing, and a missing cell and an empty cell are indistinguishable in the
    output (gotcha #53), so this function refuses to produce that ambiguity.

    **``measured`` is PER CELL, not per run.** CAL-P074's directive, and the
    reason is operational: an all-or-nothing verdict is what makes people re-run
    the expensive thing. A run that gets 44 of 49 cells reports 44 measurements
    and 5 absences, each with a reason, and the next run can be pointed at the 5.
    """
    recon = reconcile_markets(roster_totals, paged_totals)
    mismatched = {m["cell"] for m in recon["mismatches"]}

    # A range that could not be read makes every cell it could have contained
    # unmeasurable. We cannot know WHICH cells those were — that is the whole
    # nature of a range that did not return — so an unreduced failure taints the
    # run rather than a named cell, and is reported as such instead of being
    # spread over the cells by a guess.
    irreducible = [dict(r) for r in failed_ranges]

    cells: list[dict[str, Any]] = []
    for cell in sorted(roster_totals):
        league, _, market_type = cell.partition("/")
        n_markets = int(roster_totals[cell])

        all_bins = _bins_for(accumulator, league, market_type, GRADE_CLASSES)
        venue_bins = _bins_for(
            accumulator, league, market_type, (GRADE_COMPLETE, GRADE_INCOMPLETE)
        )
        complete_bins = _bins_for(accumulator, league, market_type, (GRADE_COMPLETE,))
        incomplete_bins = _bins_for(
            accumulator, league, market_type, (GRADE_INCOMPLETE,)
        )
        never_bins = _bins_for(accumulator, league, market_type, (GRADE_NEVER,))
        # The eligibility twin. Grades are unrestricted on purpose: eligibility
        # is a per-LEG property and already implies a real grade (every eligible
        # source is non-NULL), so intersecting it with the market-level grade
        # axis would silently drop eligible legs sitting in partially-graded
        # markets — the exact cohort ``repair_pm_never_graded`` leaves alone.
        eligible_bins = _bins_for(
            accumulator, league, market_type, GRADE_CLASSES, (TRUTH_ELIGIBLE,)
        )

        n_all = int(sum(b["n"] for b in all_bins))
        n_eligible = int(sum(b["n"] for b in eligible_bins))
        n_venue = int(sum(b["n"] for b in venue_bins))
        n_complete = int(sum(b["n"] for b in complete_bins))
        n_incomplete = int(sum(b["n"] for b in incomplete_bins))
        n_never = int(sum(b["n"] for b in never_bins))

        measured = True
        reason: str | None = None
        if cell in mismatched:
            measured = False
            reason = "roster_vs_paged_mismatch"
        elif irreducible and not complete:
            measured = False
            reason = "run_incomplete_with_irreducible_range"
        elif not complete:
            measured = False
            reason = "run_incomplete"

        ece_all, fb_all = ece_from_bins(all_bins)
        ece_venue, fb_venue = ece_from_bins(venue_bins)
        ece_complete, fb_complete = ece_from_bins(complete_bins)
        ece_incomplete, fb_incomplete = ece_from_bins(incomplete_bins)
        ece_eligible, fb_eligible = ece_from_bins(eligible_bins)

        cells.append(
            {
                "cell": cell,
                "league": league,
                "market_type": market_type,
                "measured": measured,
                "measured_reason": reason,
                "n_markets_roster": n_markets,
                "n_markets_paged": int(paged_totals.get(cell, 0)),
                "n_all": n_all,
                "n_venue": n_venue,
                "n_default": n_all - n_venue,
                "graded_share": round(n_venue / n_all, 3) if n_all else None,
                "null_default_share": (
                    round((n_all - n_venue) / n_all, 3) if n_all else None
                ),
                # The twins. Both are reported even when one is absent, because
                # "we did not measure the incomplete cohort" and "the incomplete
                # cohort is fine" must not share a rendering.
                "n_complete": n_complete,
                "n_incomplete": n_incomplete,
                "n_never": n_never,
                "incomplete_share": (
                    round(n_incomplete / n_all, 3) if n_all else None
                ),
                # The eligibility twin (CAL-P093). ``n_eligible`` is reported
                # beside it and is load-bearing: on the four cells measured so
                # far it is 3.7%–51% of ``n_all``, so an ``ece_eligible`` read
                # without its n invites the reading that the cell got better
                # rather than that most of it was never on the curve.
                "n_eligible": n_eligible,
                "eligible_share": (
                    round(n_eligible / n_all, 3) if n_all else None
                ),
                "ece_eligible": ece_eligible,
                "gap_eligible": gap_from_bins(eligible_bins),
                "ece_label_eligible": "fallback-nonparity" if fb_eligible else None,
                "ece_all": ece_all,
                "ece_venue": ece_venue,
                "ece_complete": ece_complete,
                "ece_incomplete": ece_incomplete,
                "gap_all": gap_from_bins(all_bins),
                "gap_complete": gap_from_bins(complete_bins),
                "gap_incomplete": gap_from_bins(incomplete_bins),
                "ece_label_all": "fallback-nonparity" if fb_all else None,
                "ece_label_venue": "fallback-nonparity" if fb_venue else None,
                "ece_label_complete": "fallback-nonparity" if fb_complete else None,
                "ece_label_incomplete": (
                    "fallback-nonparity" if fb_incomplete else None
                ),
            }
        )

    measured_cells = sum(1 for c in cells if c["measured"])
    return {
        "schema": CENSUS_SCHEMA,
        "sampled": False,
        "population": "full",
        "population_predicate": {
            "source": POPULATION_SOURCE,
            "status": POPULATION_STATUS,
            "market_type_in": list(POPULATION_MARKET_TYPES),
        },
        "complete": complete,
        "cells_total": len(cells),
        "cells_measured": measured_cells,
        "cells_absent": len(cells) - measured_cells,
        "markets_roster": int(sum(roster_totals.values())),
        "markets_paged": int(sum(paged_totals.values())),
        "pages_done": pages_done,
        "elapsed_s": round(elapsed_s, 2),
        "reconciliation": recon,
        "irreducible_ranges": irreducible,
        "cells": sorted(cells, key=lambda c: (c["ece_all"] is None, -(c["ece_all"] or 0))),
        "note": (
            "complete = every leg has a resolution_source; incomplete = some but "
            "not all; never = none (the #1912 default-false cohort). ece_venue is "
            "complete+incomplete together and is kept for parity with "
            "GET /api/admin/cohort-provenance-split. A cell with measured=false "
            "carries a reason and NO trustworthy ECE — an absent measurement is "
            "never a clean zero (gotcha #53). ece_eligible is the SECOND axis "
            "(CAL-P093): legs whose resolution_source may grade a published "
            "forecast (CALIBRATION_TRUTH_ELIGIBLE_SOURCES). It is the number "
            "comparable to the published curve; ece_all is not, because it "
            "includes the pass2_loser/clean_resolution rows precompute_"
            "calibration already excludes. Rank cells by ece_eligible x "
            "n_eligible, never by ece_all."
        ),
    }
