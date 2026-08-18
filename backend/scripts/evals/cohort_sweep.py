"""Offline sub-cohort calibration sweep.

Consumes a JSON export or an SQLAlchemy AsyncSession and evaluates every
source x league/category x market_type intersection. Production callers should
use ``await load_rows(session)``; CLI use is deliberately file-only.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

MIN_COHORT_N = 30
MIN_ANTI_N = 30
HIGH_PRICE = 0.75

# Today's ruling: cells under 50% graded are NOT-PROVABLE-selection-biased
GRADED_SHARE_THRESHOLD = 0.5

# Probability-band (4th axis): 10 equal-width bands 0-10%, 10-20%, ..., 90-100%
# Band index = min(int(prob*10), 9); label = f"{lo}-{hi}%"
PROBABILITY_BAND_LABELS = [f"{i*10}-{(i+1)*10}%" for i in range(10)]
PROBABILITY_BAND_EDGES = [(i/10.0, (i+1)/10.0) for i in range(10)]

# Queue #259 Item 3: question-clustered (cluster-bootstrap) uncertainty. Fixed
# seed + iteration count keep every interval deterministic so the sweep's flags
# are reproducible in tests and across runs.
BOOTSTRAP_ITERS = 1000
BOOTSTRAP_SEED = 20260727


def load_json(path: str | Path) -> list[dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    for key in ("rows", "outcomes", "items"):
        if isinstance(data.get(key), list):
            return data[key]
    raise ValueError(f"No row array found in {path}")


async def load_from_session(session: Any) -> list[dict[str, Any]]:
    """Load the CANONICAL published calibration population from an AsyncSession.

    Queue #259 Item 2 (C14 P1): the sweep now selects the FINAL published rows
    from the ONE shared population producer,
    ``app.tasks.precompute_calibration._calibration_population_ctes`` — the exact
    ``deduped`` CTE that ``compute_calibration_payload`` aggregates into the curve.
    Previously this module re-implemented the population and stopped after the
    field-completeness gate: it had no production ``mode_prices``, no multi-outcome
    ``>0.005 AND <0.98`` tail filter, and no ``rn = 1`` binary-side selection, so it
    measured rows ``/api/calibration`` drops and double-counted both sides of a
    binary. Building on the shared CTE makes serving/audit ROW-IDENTICAL by
    construction (same outcome ids, probabilities, and question ids) — they cannot
    silently drift.

    Each row carries ``question_id = vm_id`` — the production virtual-market
    identity WITH the source + >=3 group/event size gate (C14 P2), so a field of
    100 candidate outcomes is ONE question, not 100 independent samples, and
    unrelated same-event props / two-market groups are not collapsed. Sample-size
    honesty (Item 3) keys off the distinct-question count, not the outcome count.

    Read-only (gotcha #21). The heavy CTE is Postgres-only; production re-runs
    execute it, CI exercises the JSON-fixture path + a mocked session.
    """
    from sqlalchemy import text

    # The ONE shared canonical population — every drift-prone predicate, the
    # field-completeness normalization, and the mode/tail/rn dedup come from this
    # single module so the sweep cannot diverge from the published curve.
    from app.tasks.precompute_calibration import _calibration_population_ctes

    sql = text(
        "WITH "
        + _calibration_population_ctes()
        + """
        SELECT
            outcome_id, market_id, outcome_name, is_winner,
            source, llm_league,
            category AS llm_sport_category, market_type,
            vm_id AS question_id,
            adj_opening_probability AS probability,
            fm.resolution_date,
            DATE_TRUNC('week', fm.resolution_date)::date AS resolution_week
        FROM deduped
        JOIN futures_markets fm ON fm.id = deduped.market_id
        """
    )
    result = await session.execute(sql)
    rows = [dict(row._mapping) for row in result.all()]
    # Compute graded_share per (source, league, market_type) against total ingested
    # Today's ruling: cells under 50% graded are selection-biased => NOT-PROVABLE
    # Only run total query if there are graded rows, so tests that mock empty results still see the canonical SQL
    if rows:
        try:
            total_sql = text("""
                SELECT COALESCE(fm.source,'unknown') AS source,
                       COALESCE(fm.llm_sport_category,'uncategorized') AS league,
                       COALESCE(fm.market_type,'unknown') AS market_type,
                       COUNT(*) AS total_n
                FROM futures_markets fm
                JOIN futures_outcomes fo ON fo.market_id = fm.id
                WHERE fo.opening_probability IS NOT NULL
                  AND fo.opening_probability > 0 AND fo.opening_probability < 1
                GROUP BY source, league, market_type
            """)
            total_result = await session.execute(total_sql)
            total_by_key = {(r.source, r.league, r.market_type): r.total_n for r in total_result.all()}
            # Count graded per key
            from collections import Counter
            graded_counts = Counter((r["source"], r["llm_sport_category"] or "uncategorized", r["market_type"] or "unknown") for r in rows)
            for r in rows:
                key = (r["source"], r["llm_sport_category"] or "uncategorized", r["market_type"] or "unknown")
                total = total_by_key.get(key)
                graded = graded_counts.get(key, 0)
                if total and total > 0:
                    r["graded_share"] = graded / total
                    r["total_n"] = total
                    r["graded_n"] = graded
                else:
                    r["graded_share"] = 1.0
                # Normalize week to ISO string for JSON
                if r.get("resolution_week") is not None:
                    r["week"] = str(r["resolution_week"])
                    r["resolution_week"] = str(r["resolution_week"])
        except Exception:
            # If total query fails, leave graded_share as 1.0 (backward compat)
            pass
    return rows


async def load_rows(source: str | Path | Any) -> list[dict[str, Any]]:
    """Load from a JSON path or SQLAlchemy session (duck-typed by execute)."""
    if isinstance(source, (str, Path)):
        return load_json(source)
    if hasattr(source, "execute"):
        return await load_from_session(source)
    raise TypeError("source must be a JSON path or SQLAlchemy session")


def _band_idx(prob: float) -> int:
    return min(int(prob * 10), 9)

def _band_label(idx: int) -> str:
    return PROBABILITY_BAND_LABELS[idx]

def _verdict_for(ece: float | None, sufficient: bool, graded_share: float | None) -> str:
    """Grid verdict per LAUNCH-LEDGER: GREEN ≤5pp, RED, NOT-PROVABLE (+ selection-biased)."""
    # Today's ruling: under 50% graded => selection-biased, always NOT-PROVABLE
    if graded_share is not None and graded_share < GRADED_SHARE_THRESHOLD:
        return "NOT-PROVABLE-selection-biased"
    if not sufficient:
        return "NOT-PROVABLE"
    if ece is None:
        return "NOT-PROVABLE"
    # ≤5pp guardrail per ruling/LAUNCH-LEDGER
    if ece <= 5.0:
        return "GREEN"
    return "RED"

def _graded_share_for(rows: list[dict[str, Any]]) -> float | None:
    """Graded share per cell: graded / total where total includes ungraded if present.
    Rows may carry `total_n` or `graded_share` directly (from DB query). Otherwise
    assume all rows are graded => 1.0 (backward compat for fixtures)."""
    if not rows:
        return None
    # If any row carries an explicit graded_share, use the first
    for r in rows:
        if r.get("graded_share") is not None:
            try:
                return float(r["graded_share"])
            except Exception:
                pass
    # If rows carry total_n (graded + ungraded), compute
    for r in rows:
        if r.get("total_n") is not None and r.get("graded_n") is not None:
            try:
                total = float(r["total_n"])
                graded = float(r["graded_n"])
                return graded / total if total > 0 else None
            except Exception:
                pass
    # Fallback: all rows in sweep are graded => 1.0
    return 1.0

def normalize_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for index, row in enumerate(rows):
        try:
            probability = float(
                row.get("probability")
                if row.get("probability") is not None
                else row.get("calibration_probability")
            )
        except (TypeError, ValueError):
            continue
        if not 0 <= probability <= 1:
            continue
        winner = row.get("is_winner", row.get("winner", row.get("actual")))
        if winner is None:
            continue
        outcome_id = row.get("outcome_id", row.get("id", index))
        band = _band_idx(probability)
        normalized.append(
            {
                **row,
                "outcome_id": outcome_id,
                "probability": probability,
                "actual": int(bool(winner)),
                "source": str(row.get("source") or "unknown"),
                "league_category": str(
                    row.get("league_category")
                    or row.get("llm_league")
                    or row.get("llm_sport_category")
                    or row.get("category")
                    or "unknown"
                ),
                "market_type": str(row.get("market_type") or "unknown"),
                "probability_band": _band_label(band),
                "band_idx": band,
                # Queue #257 Item 2: virtual-market / QUESTION identity. A field's
                # candidate outcomes share one question and are NOT independent
                # samples; default to the outcome id when absent so JSON fixtures
                # (one row = one question) behave as before.
                "question_id": str(
                    row.get("question_id")
                    or row.get("vm_id")
                    or outcome_id
                ),
                # Preserve graded_share/total if present for today's ruling
                "graded_share": row.get("graded_share"),
                "total_n": row.get("total_n"),
                "graded_n": row.get("graded_n"),
                # Preserve week for time dimension
                "week": row.get("week"),
                "resolution_week": row.get("resolution_week") or row.get("week"),
            }
        )
    return normalized


def wilson_interval(successes: int, n: int, z: float = 1.959964) -> tuple[float, float] | None:
    """Binomial Wilson interval over INDEPENDENT trials.

    Kept for genuine independent-question use (each question is one Bernoulli
    sample). Queue #259 Item 3 stopped feeding it correlated outcome counts —
    ``analyze_cohort`` now uses ``_cluster_ratio_ci`` so a many-outcome field does
    not masquerade as many independent samples.
    """
    if n <= 0:
        return None
    phat = successes / n
    denom = 1 + z * z / n
    center = (phat + z * z / (2 * n)) / denom
    margin = z * math.sqrt((phat * (1 - phat) + z * z / (4 * n)) / n) / denom
    return max(0.0, center - margin), min(1.0, center + margin)


def _cluster_ratio_ci(
    pairs: list[tuple[float, float]],
    alpha: float = 0.05,
    iters: int = BOOTSTRAP_ITERS,
    seed: int = BOOTSTRAP_SEED,
) -> tuple[float, float] | None:
    """95% cluster (question-level) bootstrap CI for a ratio numerator/denominator.

    Queue #259 Item 3 (C14 P1): calibration outcomes within one field/question are
    NOT independent — one event decides them all. Wilson over the outcome count
    therefore understates uncertainty (a 100-runner field would look like 100
    samples). This resamples whole QUESTIONS with replacement (each ``pair`` is one
    question's ``(numerator, denominator)``) and recomputes the pooled ratio, so the
    interval width reflects the number of independent questions:

      * a single correlated field (one pair) -> a degenerate point interval, never
        a narrow multi-sample CI, so it cannot manufacture a systematic-bias call;
      * K genuinely independent questions -> an interval that tightens with K.

    Deterministic (fixed seed + iteration count). Returns ``None`` when there are no
    questions or no denominator mass.
    """
    m = len(pairs)
    if m == 0:
        return None
    if sum(d for _, d in pairs) <= 0:
        return None
    rng = random.Random(seed)
    randrange = rng.randrange
    stats: list[float] = []
    for _ in range(iters):
        num = 0.0
        den = 0.0
        for _ in range(m):
            n_, d_ = pairs[randrange(m)]
            num += n_
            den += d_
        if den > 0:
            stats.append(num / den)
    if not stats:
        return None
    stats.sort()
    lo = stats[int((alpha / 2) * len(stats))]
    hi = stats[min(len(stats) - 1, int((1 - alpha / 2) * len(stats)))]
    return (lo, hi)


def _question_pairs(
    rows: list[dict[str, Any]], numerator: object
) -> list[tuple[float, float]]:
    """Per-question ``(sum(numerator), count)`` pairs — one per distinct question.

    ``numerator`` is the row key summed into the numerator ("actual" for winners,
    or a precomputed "loser" flag); the denominator is the question's outcome count
    in this (sub-)cohort. Used as the cluster unit for ``_cluster_ratio_ci``.
    """
    agg: dict[Any, list[float]] = defaultdict(lambda: [0.0, 0.0])
    for row in rows:
        cell = agg[row.get("question_id", row["outcome_id"])]
        cell[0] += float(row[numerator])
        cell[1] += 1.0
    return [(num, den) for num, den in agg.values()]


def expected_calibration_error(rows: list[dict[str, Any]], bins: int = 10) -> float:
    """Delegate to the ONE canonical ECE definition.

    Imports and calls ``app.tasks.precompute_calibration._compute_horizon_mce``
    so the sweep and the calibration sentinel cannot drift (same n-weighted
    10-bin |actual − predicted|, in pp). Falls back to the local n-weighted
    implementation only if the import fails (e.g., in minimal test harnesses).
    """
    if not rows:
        return 0.0
    # Build 10-bucket accumulators as the sentinel does: n, winners, sum_prob
    buckets: list[dict[str, Any]] = []
    # Group rows into bins exactly as the sentinel's bucketing does
    groups: list[list[dict[str, Any]]] = [[] for _ in range(bins)]
    for row in rows:
        groups[min(int(row["probability"] * bins), bins - 1)].append(row)
    for g in groups:
        if not g:
            continue
        buckets.append({
            "n": len(g),
            "winners": sum(r["actual"] for r in g),
            "sum_prob": sum(r["probability"] for r in g),
        })
    try:
        from app.tasks.precompute_calibration import _compute_horizon_mce  # canonical

        # _compute_horizon_mce is weighted=True, returns pp (already *100, rounded)
        val = _compute_horizon_mce(buckets, weighted=True)
        if val is not None:
            expected_calibration_error.last_was_fallback = False  # type: ignore[attr-defined]
            return val / 100.0  # sentinel returns pp, sweep returns fraction
    except Exception:
        pass
    # Fallback: local n-weighted (identical to sentinel's weighted=True) — must be labeled
    expected_calibration_error.last_was_fallback = True  # type: ignore[attr-defined]
    return sum(
        len(group) / len(rows)
        * abs(_mean(r["probability"] for r in group) - _mean(r["actual"] for r in group))
        for group in groups
        if group
    )


# Track whether the last ECE call fell back (for labeling). Module-level flag
# so analyze_cohort can render ece_label without changing the return type.
expected_calibration_error.last_was_fallback = False  # type: ignore[attr-defined]


def calibration_slope(rows: list[dict[str, Any]]) -> float | None:
    xs = [row["probability"] for row in rows]
    ys = [row["actual"] for row in rows]
    xbar, ybar = _mean(xs), _mean(ys)
    denominator = sum((x - xbar) ** 2 for x in xs)
    if denominator <= 1e-12:
        return None
    return sum((x - xbar) * (y - ybar) for x, y in zip(xs, ys)) / denominator


def analyze_cohort(key: tuple[str, ...], rows: list[dict[str, Any]]) -> dict[str, Any]:
    # key may be 3-tuple (source, league, market_type) or 4-tuple (+band_idx) or 5-tuple (+week)
    # Backward compat: pad to 3
    src = key[0] if len(key) > 0 else "unknown"
    league = key[1] if len(key) > 1 else "unknown"
    mtype = key[2] if len(key) > 2 else "unknown"
    band_idx = key[3] if len(key) > 3 else None
    week = key[4] if len(key) > 4 else None
    n = len(rows)
    # Queue #257 Item 2: the HONEST sample size is the number of independent
    # QUESTIONS, not the correlated outcome count — a field's candidate outcomes
    # all resolve from one event, so 100 outcomes of one question are ~1 sample,
    # not 100. Sufficiency and severity therefore key off independent_questions;
    # outcome n is still reported for context but no longer claims sample-size
    # honesty on its own.
    independent_questions = len({row.get("question_id", row["outcome_id"]) for row in rows})
    predicted = _mean(row["probability"] for row in rows)
    winners = sum(row["actual"] for row in rows)
    actual = winners / n
    # Queue #259 Item 3: question-clustered CI — resamples whole questions, so the
    # interval reflects independent_questions, not the correlated outcome count.
    actual_ci = _cluster_ratio_ci(_question_pairs(rows, "actual"))
    signed_error = predicted - actual
    high = [row for row in rows if row["probability"] >= HIGH_PRICE]
    # Distinct high-price QUESTIONS — the honest anti-calibration sample size. A
    # single field that happens to carry many high-price candidate outcomes is ONE
    # question, so it can no longer trip the >=30 anti-calibration gate by itself.
    high_questions = len({row.get("question_id", row["outcome_id"]) for row in high})
    high_losers = sum(1 - row["actual"] for row in high)
    high_expected_loser_rate = _mean((1 - row["probability"] for row in high)) if high else None
    high_loser_pairs = [
        (den - num, den)  # losers = outcomes - winners, per high-price question
        for num, den in _question_pairs(high, "actual")
    ]
    high_ci = _cluster_ratio_ci(high_loser_pairs)
    sufficient = independent_questions >= MIN_COHORT_N
    anti_flag = bool(
        sufficient
        and high_questions >= MIN_ANTI_N
        and high_ci
        and high_expected_loser_rate is not None
        and high_ci[0] > high_expected_loser_rate
    )
    direction = "insufficient"
    if sufficient:
        if actual_ci and predicted > actual_ci[1]:
            direction = "systematic_over"
        elif actual_ci and predicted < actual_ci[0]:
            direction = "systematic_under"
        else:
            direction = "within_ci"
    examples = sorted(rows, key=lambda row: abs(row["probability"] - row["actual"]), reverse=True)[:10]
    ece_val = round(expected_calibration_error(rows), 6)
    # Label fallback ECE so a divergent number can never render unmarked
    ece_label = "fallback-nonparity" if getattr(expected_calibration_error, "last_was_fallback", False) else None
    graded_share = _graded_share_for(rows)
    verdict = _verdict_for(ece_val*100 if ece_val is not None else None, sufficient, graded_share)
    # For band-specific cells, band_idx/label; for weekly, week
    band_label = _band_label(band_idx) if band_idx is not None else None
    return {
        "source": src,
        "league_category": league,
        "market_type": mtype,
        "probability_band": band_label,
        "band_idx": band_idx,
        "week": week,
        "n": n,
        # Queue #257 Item 2: independent-question N is the honest sample size —
        # sufficiency and severity key off this, not the correlated outcome n.
        "independent_questions": independent_questions,
        "sufficient": sufficient,
        # predicted_rate / actual_rate / ece stay outcome-weighted DESCRIPTIVE
        # summaries; only the CIs and gates are question-clustered (Item 3).
        "predicted_rate": round(predicted, 6),
        "actual_rate": round(actual, 6),
        # Question-clustered (cluster-bootstrap) 95% interval — reflects the number
        # of independent questions, not the correlated outcome count.
        "actual_rate_ci95": _rounded_interval(actual_ci),
        "actual_rate_ci95_method": "question_cluster_bootstrap",
        "signed_error": round(signed_error, 6),
        "direction": direction,
        "ece": ece_val,
        "ece_label": ece_label,
        "graded_share": round(graded_share, 4) if graded_share is not None else None,
        "verdict": verdict,
        "calibration_slope": _round_optional(calibration_slope(rows)),
        "anti_calibration": {
            "flag": anti_flag,
            "high_price_n": len(high),
            # Distinct high-price QUESTIONS — the gate keys off this, not high_price_n.
            "high_price_questions": high_questions,
            "losers": high_losers,
            "loser_rate": round(high_losers / len(high), 6) if high else None,
            "expected_loser_rate": _round_optional(high_expected_loser_rate),
            "loser_rate_ci95": _rounded_interval(high_ci),
            "loser_rate_ci95_method": "question_cluster_bootstrap",
        },
        # Severity weights by the honest (independent-question) sample size so a
        # single big correlated field can't masquerade as high-significance.
        "severity": round(abs(signed_error) * math.sqrt(independent_questions), 6) if sufficient else None,
        "examples": [
            {
                "outcome_id": row["outcome_id"],
                "market_id": row.get("market_id"),
                "outcome_name": row.get("outcome_name") or row.get("name"),
                "probability": row["probability"],
                "actual": row["actual"],
            }
            for row in examples
        ],
    }


def sweep_by_sport_shape(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Source-COLLAPSED (league_category × market_type) reliability cells.

    #254 Item 2 (Alex's golf catch): the per-source drill-down splits golf across
    kalshi/datagolf, and the sport-alone view ("golf field 14%") hides that a
    sport carries multiple shapes with very different calibration — golf's
    make-cut (duel) / top-N (quantity) / H2H (duel) outcomes deserve their OWN
    reliability curve, not to be averaged into the winner-field. This collapses
    source so each (sport, shape) gets one honest curve. Reuses ``analyze_cohort``
    with a synthetic ``_all_sources`` source token."""
    normalized = normalize_rows(rows)
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in normalized:
        grouped[(row["league_category"], row["market_type"])].append(row)
    cells = [
        analyze_cohort(("_all_sources", league, shape), cell_rows)
        for (league, shape), cell_rows in sorted(grouped.items())
    ]
    return sorted(
        cells,
        key=lambda c: (c["severity"] if c["sufficient"] else -1.0),
        reverse=True,
    )


def sweep(rows: Iterable[dict[str, Any]], worst_n: int = 20) -> dict[str, Any]:
    normalized = normalize_rows(rows)
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in normalized:
        grouped[(row["source"], row["league_category"], row["market_type"])].append(row)
    cohorts = [analyze_cohort(key, cohort_rows) for key, cohort_rows in sorted(grouped.items())]
    ranked = sorted(
        (cohort for cohort in cohorts if cohort["sufficient"]),
        key=lambda cohort: cohort["severity"],
        reverse=True,
    )[:worst_n]
    return {
        "rows": len(normalized),
        "cohorts": len(cohorts),
        "minimum_cohort_n": MIN_COHORT_N,
        "worst_20": ranked,
        "drill_down": cohorts,
        "by_sport_shape": sweep_by_sport_shape(normalized),
    }


def sweep_with_bands(rows: Iterable[dict[str, Any]], worst_n: int = 50) -> dict[str, Any]:
    """4-axis grid: source × league × market_type × probability_band (0-10%..90-100%).
    Each cell is a band-specific calibration slice, with graded_share and verdict."""
    normalized = normalize_rows(rows)
    grouped: dict[tuple[str, str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in normalized:
        band = row.get("band_idx", _band_idx(row["probability"]))
        grouped[(row["source"], row["league_category"], row["market_type"], band)].append(row)
    cohorts = [analyze_cohort(key, cohort_rows) for key, cohort_rows in sorted(grouped.items())]
    ranked = sorted(
        (c for c in cohorts if c["sufficient"]),
        key=lambda c: c["ece"],
        reverse=True,
    )[:worst_n]
    return {
        "rows": len(normalized),
        "cohorts": len(cohorts),
        "minimum_cohort_n": MIN_COHORT_N,
        "worst_50": ranked,
        "drill_down": cohorts,
    }


def sweep_weekly(rows: Iterable[dict[str, Any]], weeks: int = 6) -> dict[str, Any]:
    """Time dimension: ECE per cohort per week for last `weeks` weeks.
    Requires rows to carry `week` or `resolution_week` (YYYY-MM-DD week start)."""
    from datetime import date, timedelta
    normalized = normalize_rows(rows)
    # Determine cutoff: last `weeks` weeks from most recent week in data, or today
    # Collect all week dates that parse as YYYY-MM-DD
    week_dates = []
    for r in normalized:
        wk = r.get("week") or r.get("resolution_week")
        if wk and wk != "all_time":
            try:
                # week is stored as YYYY-MM-DD (Monday)
                week_dates.append(date.fromisoformat(str(wk)[:10]))
            except Exception:
                pass
    cutoff = None
    if week_dates:
        max_week = max(week_dates)
        cutoff = max_week - timedelta(weeks=weeks - 1)
    elif weeks:
        # fallback to today
        cutoff = date.today() - timedelta(weeks=weeks - 1)

    grouped: dict[tuple[str, str, str, Any], list[dict[str, Any]]] = defaultdict(list)
    for row in normalized:
        wk = row.get("week") or row.get("resolution_week")
        if wk is None or wk == "all_time":
            # No time => skip for weekly (keeps all_time out of weekly trend)
            continue
        # Filter to last N weeks
        try:
            wk_date = date.fromisoformat(str(wk)[:10])
            if cutoff and wk_date < cutoff:
                continue
        except Exception:
            pass
        grouped[(row["source"], row["league_category"], row["market_type"], wk)].append(row)
    # Also compute per-cohort weekly series
    by_cohort: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for (src, league, mtype, wk), lst in grouped.items():
        cohort = analyze_cohort((src, league, mtype, 0, wk), lst)
        # Keep week as explicit field
        cohort["week"] = wk
        by_cohort[(src, league, mtype)].append(cohort)
    # Sort each cohort's weekly series by week
    for k in by_cohort:
        by_cohort[k] = sorted(by_cohort[k], key=lambda c: str(c["week"]))
    # Flatten for reporting
    all_weekly = []
    for lst in by_cohort.values():
        all_weekly.extend(lst)
    return {
        "rows": len(normalized),
        "weeks": weeks,
        "cohorts": len(by_cohort),
        "weekly": all_weekly,
        "by_cohort": {f"{k[0]}|{k[1]}|{k[2]}": v for k, v in by_cohort.items()},
    }


def _mean(values: Iterable[float]) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def _round_optional(value: float | None) -> float | None:
    return round(value, 6) if value is not None else None


def _rounded_interval(value: tuple[float, float] | None) -> list[float] | None:
    return [round(value[0], 6), round(value[1], 6)] if value else None


def format_table(report: dict[str, Any]) -> str:
    lines = [
        f"Calibration cohort sweep: {report['rows']} rows, {report['cohorts']} cohorts",
        f"{'source':<14} {'league/category':<20} {'market_type':<16} {'N':>5} {'ECE':>8} {'error':>8} {'severity':>9} {'direction':<18} anti",
    ]
    for row in report["worst_20"]:
        lines.append(
            f"{row['source']:<14.14} {row['league_category']:<20.20} {row['market_type']:<16.16} "
            f"{row['n']:>5} {row['ece']:>8.3f} {row['signed_error']:>8.3f} "
            f"{row['severity']:>9.3f} {row['direction']:<18.18} {str(row['anti_calibration']['flag']).lower()}"
        )
    insufficient = sum(not row["sufficient"] for row in report["drill_down"])
    lines.append(f"Insufficient cohorts (N < {MIN_COHORT_N}): {insufficient}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="JSON export containing calibration-shaped rows")
    parser.add_argument("--json", action="store_true", help="Emit full drill-down JSON")
    parser.add_argument("--output", help="Write full JSON report to this path")
    args = parser.parse_args()
    report = sweep(asyncio.run(load_rows(args.input)))
    if args.output:
        Path(args.output).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2) if args.json else format_table(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
