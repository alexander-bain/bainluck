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


def load_json(path: str | Path) -> list[dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    for key in ("rows", "outcomes", "items"):
        if isinstance(data.get(key), list):
            return data[key]
    raise ValueError(f"No row array found in {path}")


async def load_from_session(session: Any) -> list[dict[str, Any]]:
    """Load the CANONICAL published calibration population from an AsyncSession (Queue #257 Item 2).

    Previously this loaded RAW ``calibration_probability IS NOT NULL`` rows — the
    whole unfiltered corpus including guessed/void/heuristic resolutions, illiquid
    placeholders, Kalshi prop-threshold settlement collapses, weather fabricated
    midpoints, and raw one-sided-ask field prices. The sweep is supposed to measure
    what the /calibration curve actually PUBLISHES, so it now consumes the same
    canonical eligible + exclusion-filtered + field-normalized population as
    ``app.tasks.precompute_calibration.compute_calibration_payload``, reusing that
    module's exclusion PREDICATE constants so the two cannot silently drift.

    It also carries a virtual-market / QUESTION identity (``question_id``) per row
    so the sweep can report independent-question N (distinct questions) alongside
    the correlated outcome N — a field of 100 candidate outcomes is ONE question,
    not 100 independent samples, so Wilson / sample-size honesty must key off the
    question count, not the outcome count.

    Read-only (gotcha #21). The heavy CTE is Postgres-only; production re-runs
    execute it, CI exercises the JSON-fixture path + a mocked session.
    """
    from sqlalchemy import text

    # Reuse the canonical exclusion predicates so the sweep population matches the
    # published curve and cannot drift from it (the Queue #257 anti-duplication
    # thesis). Only the market-grouping scaffolding is assembled here; every
    # drift-prone predicate comes from the one shared module.
    from app.tasks.precompute_calibration import (
        GOLF_PLACEHOLDER_HIGH_BAND,
        KALSHI_LIQUIDITY_EXISTS,
        MEX_NORMALIZE_THRESHOLD,
        POLY_PLACEHOLDER_EXCLUDE,
        WEATHER_WIDE_SPREAD_MIN,
        kalshi_prop_threshold_exclude_sql,
    )

    prop_excl = kalshi_prop_threshold_exclude_sql(
        source="vm.source",
        name="fo.name",
        category="vm.category",
        calibration_probability="fo.calibration_probability",
        opening_probability="fo.opening_probability",
    )
    # Mirrors compute_calibration_payload's resolution-authority exclusion list
    # (guessed / void / heuristic resolutions are never in the published curve).
    resolution_exclusion = (
        "('pass2_guess', 'pass3_threshold', 'pass2_loser', 'all_losers', "
        "'did_not_play', 'withdrew', 'no_pregame_trading')"
    )

    sql = text(f"""
        WITH market_info AS (
            SELECT fm.id AS market_id, fm.source, fm.event_id, fm.group_id,
                COALESCE(fm.llm_sport_category, 'uncategorized') AS category,
                fm.llm_league, fm.mutually_exclusive, fm.market_type
            FROM futures_markets fm
            WHERE fm.status = 'resolved'
              AND NOT COALESCE(
                  (fm.market_metadata->>'datagolf_recovery_residual')::boolean, false)
        ),
        malformed_binaries AS (
            SELECT fo.market_id
            FROM futures_outcomes fo
            JOIN market_info mi ON mi.market_id = fo.market_id
            WHERE mi.mutually_exclusive = true
            GROUP BY fo.market_id
            HAVING COUNT(*) = 2
               AND COUNT(*) FILTER (WHERE fo.is_winner = true) <> 1
        ),
        esports_multi_bundles AS (
            SELECT fo.market_id
            FROM futures_outcomes fo
            JOIN market_info mi ON mi.market_id = fo.market_id
            WHERE mi.category = 'esports'
            GROUP BY fo.market_id
            HAVING COUNT(*) >= 3
               AND COUNT(*) FILTER (WHERE fo.is_winner = true) >= 2
        ),
        golf_placeholder_markets AS (
            SELECT fo.market_id
            FROM futures_outcomes fo
            JOIN market_info mi ON mi.market_id = fo.market_id
            WHERE mi.category = 'golf'
              AND mi.mutually_exclusive = true
              AND mi.event_id IS NULL
              AND COALESCE(fo.calibration_probability, fo.opening_probability) >= {GOLF_PLACEHOLDER_HIGH_BAND}
              AND fo.opening_probability IS NOT NULL
              AND fo.opening_probability > 0 AND fo.opening_probability < 1
              AND (fo.resolution_source IS NOT NULL
                   AND fo.resolution_source NOT IN {resolution_exclusion})
              AND COALESCE(fo.volume, -1) != 0
            GROUP BY fo.market_id
            HAVING COUNT(*) >= 2
        ),
        mex_win_counts AS (
            SELECT fo.market_id,
                COUNT(*) FILTER (WHERE fo.is_winner = true) AS win_count
            FROM futures_outcomes fo
            JOIN market_info mi ON mi.market_id = fo.market_id
            WHERE (mi.mutually_exclusive = true OR mi.market_type = 'field')
            GROUP BY fo.market_id
        ),
        mex_norm_markets AS (
            SELECT fo.market_id,
                SUM(COALESCE(fo.calibration_probability, fo.opening_probability)) AS cp_sum
            FROM futures_outcomes fo
            JOIN market_info mi ON mi.market_id = fo.market_id
            JOIN mex_win_counts mwc ON mwc.market_id = fo.market_id
            WHERE (mi.mutually_exclusive = true OR mi.market_type = 'field')
              AND mwc.win_count = 1
              AND fo.opening_probability IS NOT NULL
              AND fo.opening_probability > 0 AND fo.opening_probability < 1
              AND (fo.resolution_source IS NOT NULL
                   AND fo.resolution_source NOT IN {resolution_exclusion})
              AND COALESCE(fo.volume, -1) != 0
            GROUP BY fo.market_id
            HAVING COUNT(*) >= 3
               AND SUM(COALESCE(fo.calibration_probability, fo.opening_probability)) > {MEX_NORMALIZE_THRESHOLD}
        ),
        base AS (
            SELECT
                fo.id AS outcome_id, fo.market_id, fo.name AS outcome_name,
                fo.is_winner,
                vm.source, vm.llm_league,
                vm.category AS llm_sport_category, vm.market_type,
                COALESCE('g:' || vm.group_id,
                         'e:' || vm.event_id::text,
                         'm:' || vm.market_id::text) AS question_id,
                COALESCE(fo.calibration_probability, fo.opening_probability) AS raw_cp,
                mnm.market_id AS mnm_market_id,
                mnm.cp_sum AS mnm_cp_sum,
                (mb.market_id IS NOT NULL) AS is_malformed_binary,
                (emb.market_id IS NOT NULL) AS is_esports_bundle,
                (gpm.market_id IS NOT NULL
                 AND COALESCE(fo.calibration_probability, fo.opening_probability)
                     >= {GOLF_PLACEHOLDER_HIGH_BAND}) AS is_golf_placeholder,
                {KALSHI_LIQUIDITY_EXISTS} AS is_liquid,
                {POLY_PLACEHOLDER_EXCLUDE} AS is_poly_placeholder,
                ({prop_excl}) AS is_kalshi_prop_threshold,
                (vm.source = 'kalshi' AND vm.category = 'weather'
                 AND fo.current_yes_bid IS NOT NULL AND fo.current_yes_ask IS NOT NULL
                 AND (fo.current_yes_ask - fo.current_yes_bid) >= {WEATHER_WIDE_SPREAD_MIN}
                 AND NOT EXISTS (
                    SELECT 1 FROM futures_odds_snapshots fos
                    WHERE fos.outcome_id = fo.id AND fos.last_price > 0)
                ) AS is_weather_wide_spread
            FROM futures_outcomes fo
            JOIN market_info vm ON vm.market_id = fo.market_id
            LEFT JOIN malformed_binaries mb ON mb.market_id = fo.market_id
            LEFT JOIN esports_multi_bundles emb ON emb.market_id = fo.market_id
            LEFT JOIN golf_placeholder_markets gpm ON gpm.market_id = fo.market_id
            LEFT JOIN mex_norm_markets mnm ON mnm.market_id = fo.market_id
            WHERE fo.opening_probability IS NOT NULL
              AND fo.opening_probability > 0 AND fo.opening_probability < 1
              AND (fo.resolution_source IS NOT NULL
                   AND fo.resolution_source NOT IN {resolution_exclusion})
              AND COALESCE(fo.volume, -1) != 0
        ),
        -- Queue #257 Item 1 field-completeness (mirrors the payload gate): a
        -- candidate field is normalized only if every eligible member survived
        -- every exclusion and the winner survived; a partial field is dropped.
        field_completeness AS (
            SELECT b.market_id,
                COUNT(*) AS eligible_n,
                COUNT(*) FILTER (
                    WHERE b.is_liquid AND NOT b.is_poly_placeholder
                      AND NOT b.is_malformed_binary AND NOT b.is_esports_bundle
                      AND NOT b.is_golf_placeholder AND NOT b.is_kalshi_prop_threshold
                      AND NOT b.is_weather_wide_spread
                ) AS survivor_n,
                COUNT(*) FILTER (
                    WHERE b.is_winner
                      AND b.is_liquid AND NOT b.is_poly_placeholder
                      AND NOT b.is_malformed_binary AND NOT b.is_esports_bundle
                      AND NOT b.is_golf_placeholder AND NOT b.is_kalshi_prop_threshold
                      AND NOT b.is_weather_wide_spread
                ) AS survivor_win_n
            FROM base b
            WHERE b.mnm_market_id IS NOT NULL
            GROUP BY b.market_id
        )
        SELECT
            b.outcome_id, b.market_id, b.outcome_name, b.is_winner,
            b.source, b.llm_league, b.llm_sport_category, b.market_type,
            b.question_id,
            CASE WHEN b.mnm_market_id IS NOT NULL
                      AND fc.survivor_n = fc.eligible_n
                      AND fc.survivor_win_n = 1
                      AND fc.survivor_n >= 3
                 THEN b.raw_cp / b.mnm_cp_sum
                 ELSE b.raw_cp
            END AS probability
        FROM base b
        LEFT JOIN field_completeness fc ON fc.market_id = b.market_id
        WHERE b.is_liquid AND NOT b.is_poly_placeholder
          AND NOT b.is_malformed_binary
          AND NOT b.is_esports_bundle
          AND NOT b.is_golf_placeholder
          AND NOT b.is_kalshi_prop_threshold
          AND NOT b.is_weather_wide_spread
          -- Partial candidate fields are excluded, never normalized over survivors.
          AND NOT (b.mnm_market_id IS NOT NULL
                   AND NOT (fc.survivor_n = fc.eligible_n
                            AND fc.survivor_win_n = 1
                            AND fc.survivor_n >= 3))
    """)
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
    if n <= 0:
        return None
    phat = successes / n
    denom = 1 + z * z / n
    center = (phat + z * z / (2 * n)) / denom
    margin = z * math.sqrt((phat * (1 - phat) + z * z / (4 * n)) / n) / denom
    return max(0.0, center - margin), min(1.0, center + margin)


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
    actual_ci = wilson_interval(winners, n)
    signed_error = predicted - actual
    high = [row for row in rows if row["probability"] >= HIGH_PRICE]
    high_losers = sum(1 - row["actual"] for row in high)
    high_expected_loser_rate = _mean((1 - row["probability"] for row in high)) if high else None
    high_ci = wilson_interval(high_losers, len(high))
    sufficient = independent_questions >= MIN_COHORT_N
    anti_flag = bool(
        sufficient
        and len(high) >= MIN_ANTI_N
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
        "predicted_rate": round(predicted, 6),
        "actual_rate": round(actual, 6),
        "actual_rate_ci95": _rounded_interval(actual_ci),
        "signed_error": round(signed_error, 6),
        "direction": direction,
        "ece": round(expected_calibration_error(rows), 6),
        "calibration_slope": _round_optional(calibration_slope(rows)),
        "anti_calibration": {
            "flag": anti_flag,
            "high_price_n": len(high),
            "losers": high_losers,
            "loser_rate": round(high_losers / len(high), 6) if high else None,
            "expected_loser_rate": _round_optional(high_expected_loser_rate),
            "loser_rate_ci95": _rounded_interval(high_ci),
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
