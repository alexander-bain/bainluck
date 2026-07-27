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
            -- vm_id is the size-gated production virtual-question identity.
            vm_id AS question_id,
            -- adj_opening_probability is the final published (normalized where a
            -- complete field, raw otherwise) curve price.
            adj_opening_probability AS probability
        FROM deduped
        """
    )
    result = await session.execute(sql)
    return [dict(row._mapping) for row in result.all()]


async def load_rows(source: str | Path | Any) -> list[dict[str, Any]]:
    """Load from a JSON path or SQLAlchemy session (duck-typed by execute)."""
    if isinstance(source, (str, Path)):
        return load_json(source)
    if hasattr(source, "execute"):
        return await load_from_session(source)
    raise TypeError("source must be a JSON path or SQLAlchemy session")


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
                # Queue #257 Item 2: virtual-market / QUESTION identity. A field's
                # candidate outcomes share one question and are NOT independent
                # samples; default to the outcome id when absent so JSON fixtures
                # (one row = one question) behave as before.
                "question_id": str(
                    row.get("question_id")
                    or row.get("vm_id")
                    or outcome_id
                ),
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
    if not rows:
        return 0.0
    groups: list[list[dict[str, Any]]] = [[] for _ in range(bins)]
    for row in rows:
        groups[min(int(row["probability"] * bins), bins - 1)].append(row)
    return sum(
        len(group) / len(rows)
        * abs(_mean(r["probability"] for r in group) - _mean(r["actual"] for r in group))
        for group in groups
        if group
    )


def calibration_slope(rows: list[dict[str, Any]]) -> float | None:
    xs = [row["probability"] for row in rows]
    ys = [row["actual"] for row in rows]
    xbar, ybar = _mean(xs), _mean(ys)
    denominator = sum((x - xbar) ** 2 for x in xs)
    if denominator <= 1e-12:
        return None
    return sum((x - xbar) * (y - ybar) for x, y in zip(xs, ys)) / denominator


def analyze_cohort(key: tuple[str, str, str], rows: list[dict[str, Any]]) -> dict[str, Any]:
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
    return {
        "source": key[0],
        "league_category": key[1],
        "market_type": key[2],
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
        "ece": round(expected_calibration_error(rows), 6),
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
