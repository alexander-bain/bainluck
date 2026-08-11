"""CAL-P027 (#1544) — the overlap census: does move-count predict real volume?

Ruling 011 defines "well-traded" as an ordered per-row ladder — ``volume_proven``
(volume present, traded iff ``> 0``), then ``movement_inferred`` (no volume,
adequate observation density, ``>= N`` distinct price changes), then ``unknown``.
The exit exam is explicit that the middle rung is not a predicate change:

    "N is measured, not chosen. On rows carrying BOTH volume and adequate
    snapshots, measure how well `>= N moves` predicts `volume > 0`."

This module is that measurement. It does not apply the ladder and it does not
classify anything — applying it needs a ``CALIBRATION_POPULATION_VERSION`` bump,
which is blocked behind the publish (ruling 009). It exists so that ruling 011,
which is already staged as the freeze-lift successor, can EXECUTE on the day the
freeze lifts rather than begin on that day.

WHY A RAIL AND NOT A QUERY. Measured against production 2026-08-09 (and matching
what the exam recorded a day earlier):

    bare ``COUNT(*)`` over ``futures_outcomes``          9.93 s / 10 s timeout
    8M-id window at the dense head, no snapshot join     STATEMENT TIMEOUT
    ``LAG()`` move-count over ``futures_odds_snapshots`` STATEMENT TIMEOUT at
                                                         5M, 500K and 100K ids

The snapshot table is the cost, not the window, so shrinking the window is not
the fix — bounding it *and* raising the per-window timeout is. That is the same
wall ``census_reachability`` (CAL-P012) and ``census_prop_threshold_cliff``
(CAL-P018) hit, so this follows their convention rather than inventing a third.

ROW-BOUNDED, NOT ID-WIDTH. Inherited from ``census_reachability``, whose first
cut got this wrong and measured the cost. Re-confirmed here: 3,237,030 outcomes
live in a 218,050,432-wide id space, and a fixed id width that returns in 0.47 s
at one end times out at the other. ``LIMIT :scan`` makes every window cost about
the same wherever it lands.

**This window is more expensive per row than any prior census** — it is the only
one doing correlated snapshot scans, which the cliff census explicitly noted it
was NOT doing. ``DEFAULT_SCAN`` is therefore a fifth of that module's, on
purpose. Do not raise it to match the others; they are walking a cheaper row.

THREE VOLUME STATES, NEVER TWO. ``futures_outcomes.volume`` is nullable and its
own comment says so: "NULL = not yet fetched, 0 = confirmed zero trading". Those
are different facts, and collapsing them is precisely the error ruling 011 was
written to stop — it names the resulting "thin markets look better calibrated"
inversion as its load-bearing failure. So ``absent`` / ``zero`` / ``positive``
are counted separately all the way through, and no code path folds one into
another.

Worth flagging for whoever reads the first walk: across three sampled windows on
2026-08-09 (8,509 / 2,759 / 2,560 eligible outcomes) **``volume = 0`` did not
occur once** — every row carrying volume carried ``volume > 0``. If that holds at
population scale, tier 1 never classifies anything as *untraded*, only as
proven-traded or unknown, and the ladder's entire negative side rests on tier 2.
That would be a finding about ruling 011 itself, which is why the ``zero`` column
is published rather than assumed empty.

TWO SCHEMA FACTS THAT WOULD OTHERWISE CORRUPT N. Both would have produced a
plausible number, which is the expensive kind of wrong:

  1. **Snapshots are per-bookmaker.** Ordering an outcome's snapshots by
     ``captured_at`` across books and counting changes fabricates a "move" every
     time two books quote differently. Moves are counted
     ``PARTITION BY (outcome_id, bookmaker)``. The multi-book case is rare in
     futures (``odds_api`` holds 12 markets against polymarket's 553,876 and
     kalshi's 191,114) but a one-clause guard is cheaper than the reasoning.
  2. **DataGolf dedups at write time; nobody else does.** It increments
     ``reading_count`` on a repeated reading; kalshi, polymarket and the
     sportsbook path insert a fresh row per poll. So ``COUNT(*)`` is *not*
     observation density. Density is ``SUM(reading_count)`` — how many times we
     LOOKED — while the row count is reported alongside it, because moves are
     drawn from rows. One observable standing for two different facts is
     gotcha #53's shape, one table over.

     This matters for adequacy in the direction that is easy to get backwards: a
     deduped outcome with one row and fifty readings is not sparse. We looked
     fifty times and it never moved, which is *evidence of no trading* — not the
     absence of evidence that ruling 011 forbids treating as thinness.

WHICH POPULATION THIS IS, STATED RATHER THAN OMITTED. The predicate is the
curve's **eligible** stage: ``fm.status = 'resolved'``, a truth-eligible
``resolution_source`` (imported, never retyped), and a non-null curve price. It
is deliberately a SUPERSET of the curve's published ``deduped`` population.

That is a decision, not an oversight. This census measures a property of capture
and trading — whether we observed a market move — which is independent of the
exclusions the curve applies for other reasons. Pinning it to ``deduped`` would
make N drift every time an exclusion changed, and would make the measurement
un-reproducible across population versions. CAL-P013's finding was that a second
*definition* is how these drift apart; the defence is not to avoid ever scoping
differently, it is to import the shared predicate and name the stage out loud.

Note also that ``fm.status = 'resolved'`` excludes most Kalshi settled markets by
construction (gotcha #33: they stay ``'open'`` in the DB). That is the curve's
behaviour, faithfully inherited — it is not this census's to fix, and a census
that "helpfully" widened it would be measuring a population the curve does not
plot.

READ-ONLY. ``apply`` is accepted and ignored, like every other census on the
repair rail.
"""

from __future__ import annotations

from sqlalchemy import text

from app.utils.resolution_authority import CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL

#: Outcome ROWS walked per call — NOT a span of ids (see the module docstring).
#: A fifth of ``census_prop_threshold_cliff``'s because this is the only census
#: doing correlated snapshot scans.
DEFAULT_SCAN = 100_000
MAX_SCAN = 500_000

#: Per-window statement timeout — fail this window fast rather than hold the
#: router wall open and return an H12 carrying no evidence.
_WINDOW_TIMEOUT = "20s"

#: The curve price, mirroring every other read path.
_CURVE_PRICE = "COALESCE(fo.calibration_probability, fo.opening_probability)"

CENSUS_NAME = "overlap-trading"

#: The three volume states, in ladder order. ``absent`` is NOT ``zero``.
VOLUME_STATES = ("absent", "zero", "positive")

#: Observation-density bands — how many times we LOOKED (``SUM(reading_count)``).
#: ``(label, lo, hi)``; ``hi=None`` is open-ended. Band ``"1"`` is its own band
#: because a single captured quote is exam item 3's stamped-settlement signature.
DENSITY_BANDS: tuple[tuple[str, int, int | None], ...] = (
    ("0", 0, 0),
    ("1", 1, 1),
    ("2", 2, 2),
    ("3-4", 3, 4),
    ("5-9", 5, 9),
    ("10-49", 10, 49),
    ("50+", 50, None),
)

#: Move-count bands. Deliberately fine-grained at the low end: N is expected to
#: live there, and a coarse band would make the census unable to answer its own
#: question. Widening these is not a simplification, it is a loss of resolution.
MOVE_BANDS: tuple[tuple[str, int, int | None], ...] = (
    ("0", 0, 0),
    ("1", 1, 1),
    ("2", 2, 2),
    ("3", 3, 3),
    ("4", 4, 4),
    ("5-9", 5, 9),
    ("10-19", 10, 19),
    ("20+", 20, None),
)

_BOUNDS_SQL = """
    SELECT MIN(id) AS lo, MAX(id) AS hi, COUNT(*) AS n,
           (SELECT MAX(id) FROM futures_outcomes) AS watermark
    FROM (SELECT id FROM futures_outcomes WHERE id > :cursor
          ORDER BY id ASC LIMIT :scan) w
"""
# ^ ``watermark`` is the head of the id space, read in the SAME statement as the
# window bounds so the two cannot describe different instants. It is the C258
# contract's ``source_watermark``: stable across every window means the walk saw
# ONE table state (a snapshot); a move means rows arrived mid-walk and the result
# is a ROLLING read of a table that changed underneath it. Both are usable — but
# only if which one you have is recorded, which is the whole point. An indexed
# MAX(id) is a cheap price for the difference between an artifact and a claim.


def band_for(value: int, bands: tuple[tuple[str, int, int | None], ...]) -> str:
    """Return the band label for ``value``.

    The ONE definition of banding. :func:`_band_case_sql` renders the identical
    boundaries into SQL from this same table, and a test asserts the two agree
    across the range — so the aggregate and any Python-side re-derivation cannot
    drift into disagreeing about which bucket a row is in.
    """
    for label, lo, hi in bands:
        if value >= lo and (hi is None or value <= hi):
            return label
    # Unreachable while the tables start at 0 and end open — but a silent
    # wrong band is worse than a loud unknown one.
    return "unknown"


def _band_case_sql(expr: str, bands: tuple[tuple[str, int, int | None], ...]) -> str:
    """Render ``bands`` as a SQL CASE over ``expr``, from the same table.

    Built rather than hand-written for the reason the cliff census builds its
    exclusion clause: a retyped boundary is a second opinion.
    """
    arms = []
    for label, lo, hi in bands:
        if hi is None:
            arms.append(f"WHEN {expr} >= {lo} THEN '{label}'")
        else:
            arms.append(f"WHEN {expr} >= {lo} AND {expr} <= {hi} THEN '{label}'")
    return "CASE " + " ".join(arms) + " ELSE 'unknown' END"


def _cohorts_sql() -> str:
    """The per-window aggregate, rendered from the canonical predicates.

    Built by a function rather than held as a module constant so the imported
    truth allowlist is interpolated once, here, next to the columns it reads —
    the same shape ``precompute_calibration`` and the cliff census both use.
    """
    density_case = _band_case_sql("COALESCE(po.observations, 0)", DENSITY_BANDS)
    move_case = _band_case_sql("COALESCE(po.moves, 0)", MOVE_BANDS)
    return f"""
    WITH pop AS (
        SELECT fo.id AS outcome_id,
            fm.source AS source,
            COALESCE(fm.llm_sport_category, 'uncategorized') AS category,
            CASE
                WHEN fo.volume IS NULL THEN 'absent'
                WHEN fo.volume > 0 THEN 'positive'
                ELSE 'zero'
            END AS volume_state
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fm.id = fo.market_id
        WHERE fo.id >= :lo AND fo.id <= :hi
          AND fm.status = 'resolved'
          AND fo.resolution_source IN {CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL}
          AND {_CURVE_PRICE} IS NOT NULL
    ),
    snaps AS (
        -- PARTITION BY bookmaker: two books quoting differently is not a move.
        -- captured_at then id, so same-timestamp rows order deterministically
        -- rather than letting the planner decide what "previous" means.
        SELECT s.outcome_id,
            s.bookmaker,
            COALESCE(s.reading_count, 1) AS reading_count,
            s.probability,
            LAG(s.probability) OVER (
                PARTITION BY s.outcome_id, s.bookmaker
                ORDER BY s.captured_at, s.id
            ) AS prev_probability
        FROM futures_odds_snapshots s
        JOIN pop ON pop.outcome_id = s.outcome_id
        WHERE s.outcome_id >= :lo AND s.outcome_id <= :hi
    ),
    per_book AS (
        SELECT outcome_id,
            bookmaker,
            COUNT(*) AS snapshot_rows,
            SUM(reading_count) AS observations,
            SUM(CASE WHEN prev_probability IS NOT NULL
                      AND probability IS DISTINCT FROM prev_probability
                     THEN 1 ELSE 0 END) AS moves
        FROM snaps
        GROUP BY 1, 2
    ),
    per_outcome AS (
        -- MAX, not SUM, across books: ruling 011 takes "the strongest evidence
        -- available". Summing would multiply a market's evidence by its book
        -- count and make a widely-quoted market look more traded than it is.
        SELECT outcome_id,
            SUM(snapshot_rows) AS snapshot_rows,
            MAX(observations) AS observations,
            MAX(moves) AS moves
        FROM per_book
        GROUP BY 1
    )
    SELECT p.source AS source,
        p.category AS category,
        p.volume_state AS volume_state,
        {density_case} AS density_band,
        {move_case} AS move_band,
        COUNT(*) AS n,
        SUM(COALESCE(po.snapshot_rows, 0)) AS snapshot_rows,
        SUM(COALESCE(po.observations, 0)) AS observations,
        SUM(COALESCE(po.moves, 0)) AS moves
    FROM pop p
    LEFT JOIN per_outcome po ON po.outcome_id = p.outcome_id
    GROUP BY 1, 2, 3, 4, 5
"""


def cohort_key(
    source: str, category: str, volume_state: str, density_band: str, move_band: str
) -> str:
    """Stable text key for one cohort, so windows merge without tuple keys.

    Text because a merged census crosses a JSON boundary on its way back through
    the admin rail, and a tuple key would not survive it.
    """
    return f"{source}|{category}|{volume_state}|{density_band}|{move_band}"


def merge_windows(windows: list[dict]) -> dict[str, dict]:
    """Fold per-window cohort rows into one census.

    Pure, so the arithmetic is testable without a database — which is not a
    stylistic preference here: there is no local Postgres in this sandbox, so a
    non-pure fold would be untested until CI.

    **Sums, never averages of averages.** Each window contributes counts only;
    every rate is derived at the very end. Averaging per-window means would
    weight a 12-row window like a 100,000-row one.
    """
    merged: dict[str, dict] = {}
    for window in windows:
        for row in window.get("cohorts") or []:
            key = cohort_key(
                row["source"],
                row["category"],
                row["volume_state"],
                row["density_band"],
                row["move_band"],
            )
            slot = merged.setdefault(
                key,
                {
                    "source": row["source"],
                    "category": row["category"],
                    "volume_state": row["volume_state"],
                    "density_band": row["density_band"],
                    "move_band": row["move_band"],
                    "n": 0,
                    "snapshot_rows": 0,
                    "observations": 0,
                    "moves": 0,
                },
            )
            slot["n"] += int(row.get("n") or 0)
            slot["snapshot_rows"] += int(row.get("snapshot_rows") or 0)
            slot["observations"] += int(row.get("observations") or 0)
            slot["moves"] += int(row.get("moves") or 0)
    return merged


def with_rates(merged: dict[str, dict]) -> list[dict]:
    """Derive per-cohort means once, at the end, from the summed totals.

    A cohort with no rows cannot have a mean; it reports ``None`` rather than
    0.0 — an unmeasured rate and a measured zero are different claims, and this
    whole census exists to tell two such claims apart.
    """
    out = []
    for row in merged.values():
        n = int(row["n"])
        item = dict(row)
        item["mean_observations"] = (row["observations"] / n) if n else None
        item["mean_moves"] = (row["moves"] / n) if n else None
        out.append(item)
    return sorted(
        out,
        key=lambda r: (
            r["source"],
            r["category"],
            r["volume_state"],
            r["density_band"],
            r["move_band"],
        ),
    )


def _move_band_min(label: str) -> int:
    """Lowest move count a row in ``label`` can have."""
    for name, lo, _hi in MOVE_BANDS:
        if name == label:
            return lo
    raise KeyError(f"unknown move band {label!r}")


def _move_band_max(label: str) -> int | None:
    for name, _lo, hi in MOVE_BANDS:
        if name == label:
            return hi
    raise KeyError(f"unknown move band {label!r}")


def _density_band_min(label: str) -> int:
    for name, lo, _hi in DENSITY_BANDS:
        if name == label:
            return lo
    raise KeyError(f"unknown density band {label!r}")


def band_is_wholly_at_or_above(label: str, n: int) -> bool:
    """True when EVERY row in move band ``label`` satisfies ``moves >= n``.

    Banded data cannot answer a threshold that splits a band. Rather than
    guessing a within-band distribution, :func:`precision_for_threshold`
    evaluates only thresholds that fall on a band boundary and refuses the rest
    — a precision figure produced by interpolating inside a band would look
    exactly as publishable as a real one.
    """
    return _move_band_min(label) >= n


def threshold_is_on_a_band_boundary(n: int) -> bool:
    """True when ``>= n`` can be evaluated exactly against the bands."""
    return any(lo == n for _label, lo, _hi in MOVE_BANDS)


def precision_for_threshold(
    merged: dict[str, dict],
    n: int,
    *,
    min_density: int,
    source: str | None = None,
) -> dict:
    """How well does ``>= n moves`` predict ``volume > 0``?

    This is the function that FIXES N rather than describing the data, so it is
    deliberately strict about what it will answer.

    Restricted to the **overlap population** the exam specifies: rows carrying
    BOTH a volume reading (``positive`` or ``zero`` — never ``absent``, which is
    the unknown the ladder must not silently resolve) and observation density at
    or above ``min_density``. Rows without volume cannot score a predictor of
    volume; including them would inflate whichever way the majority fell.

    Returns ``supported=False`` with a reason instead of a number when the
    question cannot be answered honestly — an unmeasurable N must come back to
    Alex as a real choice, per the exam's pre-declared PREMISE-BROKEN handling.
    Do not "fix" that by returning 0.0.
    """
    if not threshold_is_on_a_band_boundary(n):
        return {
            "threshold": n,
            "supported": False,
            "reason": "threshold_splits_a_band",
        }

    tp = fp = fn = tn = 0
    for row in merged.values():
        if source is not None and row["source"] != source:
            continue
        if row["volume_state"] == "absent":
            continue
        if _density_band_min(row["density_band"]) < min_density:
            continue
        count = int(row["n"])
        predicted_traded = band_is_wholly_at_or_above(row["move_band"], n)
        actually_traded = row["volume_state"] == "positive"
        if predicted_traded and actually_traded:
            tp += count
        elif predicted_traded and not actually_traded:
            fp += count
        elif not predicted_traded and actually_traded:
            fn += count
        else:
            tn += count

    support = tp + fp + fn + tn
    if not support:
        return {
            "threshold": n,
            "supported": False,
            "reason": "no_overlap_rows",
            "support": 0,
        }

    return {
        "threshold": n,
        "supported": True,
        "min_density": min_density,
        "source": source,
        "support": support,
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "true_negative": tn,
        "precision": (tp / (tp + fp)) if (tp + fp) else None,
        "recall": (tp / (tp + fn)) if (tp + fn) else None,
    }


def is_complete_walk(windows: list[dict]) -> bool:
    """True only when the walk reached the end of the id space.

    A PARTIAL walk must never be published as an N. Its counts are real but its
    denominator is not the population, and a threshold fixed against part of the
    table is a guess wearing a measurement's clothing.

    This is the TAIL rung ONLY, and on its own it is not enough: a walk can end
    exhausted having skipped a region in the middle. :func:`evaluate_closure` is
    the full C258 contract and calls this for its tail rung, so the two cannot
    drift about what "the tail closed" means.
    """
    return bool(windows) and bool(windows[-1].get("exhausted"))


#: C258 closure reason codes. Named constants rather than inline strings so a
#: consumer greps for the code instead of matching prose, and so a typo is an
#: ImportError instead of a rung that silently never fires.
TAIL_NOT_EXHAUSTED = "TAIL_NOT_EXHAUSTED"
START_CURSOR_MISMATCH = "START_CURSOR_MISMATCH"
CURSOR_CHAIN_BROKEN = "CURSOR_CHAIN_BROKEN"
WINDOW_BOUNDS_INVALID = "WINDOW_BOUNDS_INVALID"
SOURCE_WATERMARK_DRIFT = "SOURCE_WATERMARK_DRIFT"
SOURCE_WATERMARK_ABSENT = "SOURCE_WATERMARK_ABSENT"

#: The rungs that make a walk NOT closed. Watermark codes are deliberately
#: absent: a drifted or missing watermark downgrades the EVIDENCE CLASS, it does
#: not make the walk partial. Conflating the two is what let a rolling read be
#: reported as a snapshot.
_CLOSURE_BLOCKING = (
    TAIL_NOT_EXHAUSTED,
    START_CURSOR_MISMATCH,
    CURSOR_CHAIN_BROKEN,
    WINDOW_BOUNDS_INVALID,
)

#: The three evidence classes, and they are three for a reason (gotcha #53's
#: shape): "we walked one table state", "we walked a moving table", and "we did
#: not finish". Folding the middle into either neighbour is a lie in one
#: direction or the other.
WALK_EVIDENCE_CLASSES = ("snapshot", "rolling", "partial")

#: Timing verdicts. ``unknown`` is a first-class answer, not a failure — see
#: :func:`evaluate_closure`.
TIMING_VERDICTS = ("pre_settlement", "contaminated", "unknown")


def evaluate_closure(
    windows: list[dict],
    *,
    start_cursor: int = 0,
    chronology: dict | None = None,
) -> dict:
    """The C258 eight-case closure contract, as the production rail implements it.

    Returns ``{process_exit, walk_evidence, timing_verdict, reason_codes}``.

    The rungs, and why each exists:

    * **Tail** (:func:`is_complete_walk`) — the last window must report
      ``exhausted``.
    * **Chain** — each window's ``cursor_in`` must equal the PRIOR window's
      ``next_offset``, and the first must equal ``start_cursor``. ``next_offset``
      alone records where a window ended and says nothing about where the next
      one began, so a skipped region folds in looking exactly like a clean walk.
    * **Bounds** — ``lo > cursor_in`` and ``hi >= lo``. Note ``lo > cursor_in``,
      NOT ``lo == cursor_in + 1``: **sparse ids are valid.** The id space has
      two-orders-of-magnitude density variation, so demanding numeric adjacency
      would fail every legitimate walk of a sparse region — the check is
      monotonic non-overlap, which is the property that actually matters.
    * **Watermark** — one stable value across every window means the walk saw a
      single table state. This rung sets the EVIDENCE CLASS and never the exit
      code.

    ``timing_verdict`` is decided by **chronology alone**. Density, quote counts
    and price shape are not evidence about WHEN a quote was taken; with no
    settlement timestamp the honest answer is ``unknown``, and returning it is
    the point rather than a shortfall (this is the C-item that downgraded the
    entertainment rival from REFUTED to UNKNOWN).

    Mirrors ``scripts/evals/calibration_census_closure_contract.evaluate`` case
    for case; ``tests/test_overlap_census_closure_p032.py`` runs the shipped
    eight-case pack through THIS function and asserts the two agree, so the
    contract cannot drift away from the rail that has to satisfy it.
    """
    reasons: list[str] = []
    if not is_complete_walk(windows):
        reasons.append(TAIL_NOT_EXHAUSTED)

    prior: object = None
    watermark: object = None
    for index, window in enumerate(windows):
        cursor_in = window.get("cursor_in")
        if index == 0 and cursor_in != start_cursor:
            reasons.append(START_CURSOR_MISMATCH)
        if prior is not None and cursor_in != prior:
            reasons.append(CURSOR_CHAIN_BROKEN)

        bounds = window.get("window")
        # A ``None`` window is the empty tail the rail returns at the end of the
        # id space — it has no bounds to check, and that is not a defect.
        if bounds and isinstance(cursor_in, int):
            if bounds["lo"] <= cursor_in or bounds["hi"] < bounds["lo"]:
                reasons.append(WINDOW_BOUNDS_INVALID)

        prior = window.get("next_offset")

        mark = window.get("source_watermark")
        if watermark is None:
            watermark = mark
        elif mark != watermark:
            reasons.append(SOURCE_WATERMARK_DRIFT)

    if watermark is None:
        reasons.append(SOURCE_WATERMARK_ABSENT)

    complete = not any(code in reasons for code in _CLOSURE_BLOCKING)
    if not complete:
        evidence = "partial"
    elif watermark is not None and SOURCE_WATERMARK_DRIFT not in reasons:
        evidence = "snapshot"
    else:
        evidence = "rolling"

    settled = (chronology or {}).get("settlement_at")
    final_quote = (chronology or {}).get("final_quote_at")
    if settled is None or final_quote is None:
        timing = "unknown"
    elif final_quote >= settled:
        timing = "contaminated"
    else:
        timing = "pre_settlement"

    return {
        "process_exit": 0 if complete else 1,
        "walk_evidence": evidence,
        "timing_verdict": timing,
        "reason_codes": sorted(set(reasons)),
    }


#: Adaptive-scan bounds for :func:`next_scan`. The floor is not decoration: a
#: walk that shrinks without limit stops making progress while still looking
#: busy, which is the same class of silent non-answer this census exists to end.
WALK_SCAN_START = 5_000
WALK_SCAN_MIN = 250
WALK_SCAN_MAX = 20_000

#: Seconds. Under FAST the region is sparse and the next window can afford more;
#: over SLOW it is dense and the next one must ask for less. Both sit well inside
#: the rail's own 20 s per-window statement timeout so the policy steers BEFORE
#: the window dies rather than only reacting after it has.
WALK_FAST_S = 3.0
WALK_SLOW_S = 12.0


def next_scan(scan: int, *, seconds: float, timed_out: bool) -> int:
    """Choose the next window's row budget from how the last one went.

    CAL-P030. The rail is bounded PER WINDOW by design, so reaching exhaustion
    needs a driver, and a fixed row budget cannot work: CAL-P027 measured
    density varying by two orders of magnitude across the id space, and this
    walk confirmed it — 5,000 rows returned in 2.3 s at the head and timed out
    repeatedly in the middle. A constant is wrong at one end whichever end it is
    tuned for.

    **A timeout halves and the caller must retry the SAME cursor.** Skipping the
    window instead would be the cheaper-looking bug: the walk would complete,
    report ``exhausted``, and quietly omit exactly the dense regions where most
    of the population lives. An N fixed against a walk that skipped its hot
    cohorts is biased in an invisible direction, so the only honest responses to
    a hot window are a smaller bite or an abort — never a step over it.
    """
    if timed_out:
        return max(WALK_SCAN_MIN, scan // 2)
    if seconds < WALK_FAST_S:
        return min(WALK_SCAN_MAX, int(scan * 1.5))
    if seconds > WALK_SLOW_S:
        return max(WALK_SCAN_MIN, int(scan * 0.6))
    return scan


async def census(
    session,
    apply: bool = False,
    limit: int | None = None,
    offset: int | None = None,
) -> dict:
    """Walk one bounded outcome-row window and count the overlap cohorts.

    ``limit``   outcome ROWS to walk in this call (not an id span).
    ``offset``  outcome-id cursor, exclusive. Pass the returned ``next_offset``
                to continue; omit to start at the beginning.
    ``apply``   ignored; this census never writes.
    """
    scan = min(int(limit or DEFAULT_SCAN), MAX_SCAN)
    cursor = int(offset) if offset is not None else 0

    await session.execute(text(f"SET LOCAL statement_timeout = '{_WINDOW_TIMEOUT}'"))

    bounds = (
        await session.execute(text(_BOUNDS_SQL), {"cursor": cursor, "scan": scan})
    ).mappings().first()

    lo, hi, walked = bounds["lo"], bounds["hi"], int(bounds["n"] or 0)
    watermark = bounds["watermark"]
    watermark = None if watermark is None else str(watermark)

    if not walked:
        # End of the id space. Exhausted with zero rows is a COMPLETE walk of an
        # empty tail, not a failure — the caller needs that to stop looping.
        return {
            "census": CENSUS_NAME,
            "rows_walked": 0,
            "cursor_in": cursor,
            "window": None,
            "next_offset": None,
            "exhausted": True,
            "source_watermark": watermark,
            "cohorts": [],
        }

    rows = (
        await session.execute(text(_cohorts_sql()), {"lo": lo, "hi": hi})
    ).mappings().all()

    cohorts = [
        {
            "source": row["source"],
            "category": row["category"],
            "volume_state": row["volume_state"],
            "density_band": row["density_band"],
            "move_band": row["move_band"],
            "n": int(row["n"] or 0),
            "snapshot_rows": int(row["snapshot_rows"] or 0),
            "observations": int(row["observations"] or 0),
            "moves": int(row["moves"] or 0),
        }
        for row in rows
    ]

    return {
        "census": CENSUS_NAME,
        "rows_walked": walked,
        # ``cursor_in`` is the cursor this window was ASKED to continue from.
        # Without it a folded walk cannot tell a clean resume from a skipped
        # region: ``next_offset`` alone says where each window ended and nothing
        # at all about whether the next one started there (C258).
        "cursor_in": cursor,
        "window": {"lo": lo, "hi": hi},
        "next_offset": hi,
        "exhausted": walked < scan,
        "source_watermark": watermark,
        "eligible_rows_in_window": sum(c["n"] for c in cohorts),
        "cohorts": cohorts,
    }
