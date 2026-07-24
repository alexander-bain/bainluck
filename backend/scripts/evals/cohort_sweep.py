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
    """Load calibration-shaped rows from an SQLAlchemy AsyncSession."""
    from sqlalchemy import select
    from app.models.models import FuturesMarket, FuturesOutcome

    statement = (
        select(
            FuturesOutcome.id.label("outcome_id"),
            FuturesOutcome.market_id,
            FuturesOutcome.name.label("outcome_name"),
            FuturesOutcome.calibration_probability.label("probability"),
            FuturesOutcome.is_winner,
            FuturesMarket.source,
            FuturesMarket.llm_league,
            FuturesMarket.llm_sport_category,
            FuturesMarket.category,
            FuturesMarket.market_type,
        )
        .join(FuturesMarket, FuturesMarket.id == FuturesOutcome.market_id)
        .where(FuturesOutcome.calibration_probability.isnot(None))
    )
    result = await session.execute(statement)
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
        normalized.append(
            {
                **row,
                "outcome_id": row.get("outcome_id", row.get("id", index)),
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
    predicted = _mean(row["probability"] for row in rows)
    winners = sum(row["actual"] for row in rows)
    actual = winners / n
    actual_ci = wilson_interval(winners, n)
    signed_error = predicted - actual
    high = [row for row in rows if row["probability"] >= HIGH_PRICE]
    high_losers = sum(1 - row["actual"] for row in high)
    high_expected_loser_rate = _mean((1 - row["probability"] for row in high)) if high else None
    high_ci = wilson_interval(high_losers, len(high))
    sufficient = n >= MIN_COHORT_N
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
        "severity": round(abs(signed_error) * math.sqrt(n), 6) if sufficient else None,
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
