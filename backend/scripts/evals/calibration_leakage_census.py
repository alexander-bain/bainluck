"""Read-only calibration leakage census and counterfactual.

The production/session loader composes the canonical published calibration CTE.
The CLI is deliberately JSON-only; ops may call ``run_from_session`` through an
approved read-only session rail.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from scripts.evals.cohort_sweep import analyze_cohort, normalize_rows


PRICE_DERIVED_SOURCES = frozenset({"clean_resolution", "settlement_sync"})
EXCLUDED_RESOLUTION_SOURCES = frozenset(
    {
        "pass2_guess",
        "pass3_threshold",
        "pass2_loser",
        "all_losers",
        "did_not_play",
        "withdrew",
        "no_pregame_trading",
    }
)


def resolution_classes() -> dict[str, frozenset[str]]:
    from app.utils.resolution_authority import (
        AUTHORITATIVE_SOURCES,
        DETERMINISTIC_SOURCES,
        KNOWN_SOURCES,
        TERMINAL_SOURCES,
    )

    structural_terminal = TERMINAL_SOURCES - PRICE_DERIVED_SOURCES
    return {
        "independent_authoritative": AUTHORITATIVE_SOURCES,
        "independent_deterministic": DETERMINISTIC_SOURCES,
        "price_derived": PRICE_DERIVED_SOURCES,
        "structural_terminal": structural_terminal,
        "known": KNOWN_SOURCES,
    }


def classify_resolution_source(source: Any) -> str:
    if source is None or str(source).strip() == "":
        return "missing"
    value = str(source)
    if value in EXCLUDED_RESOLUTION_SOURCES:
        return "excluded_family"
    classes = resolution_classes()
    for label in (
        "price_derived",
        "independent_authoritative",
        "independent_deterministic",
        "structural_terminal",
    ):
        if value in classes[label]:
            return label
    return "unknown"


async def load_from_session(session: Any) -> dict[str, Any]:
    """Load canonical published rows plus a read-only sports closing audit."""
    from sqlalchemy import text
    from app.tasks.precompute_calibration import _calibration_population_ctes

    canonical_sql = text(
        "WITH "
        + _calibration_population_ctes()
        + """
        SELECT
            d.outcome_id, d.market_id, d.outcome_name, d.is_winner,
            d.source, d.llm_league,
            d.category AS llm_sport_category, d.market_type,
            d.vm_id AS question_id,
            d.adj_opening_probability AS probability,
            d.is_mex_normalized,
            fo.resolution_source,
            fo.opening_probability,
            fo.calibration_probability,
            fo.current_probability
        FROM deduped d
        JOIN futures_outcomes fo ON fo.id = d.outcome_id
        """
    )
    canonical = await session.execute(canonical_sql)

    sports_sql = text(
        """
        SELECT e.id AS event_id, e.commence_time,
               e.closing_home_probability AS stored_moneyline,
               moneyline.home_win_probability AS expected_moneyline,
               e.closing_home_spread AS stored_spread,
               spread.home_spread AS expected_spread,
               e.closing_over_under AS stored_total,
               total.over_under AS expected_total
        FROM events e
        LEFT JOIN LATERAL (
            SELECT os.home_win_probability
            FROM odds_snapshots os
            WHERE os.event_id = e.id AND os.captured_at < e.commence_time
              AND os.home_win_probability IS NOT NULL
            ORDER BY os.captured_at DESC LIMIT 1
        ) moneyline ON true
        LEFT JOIN LATERAL (
            SELECT os.home_spread
            FROM odds_snapshots os
            WHERE os.event_id = e.id AND os.captured_at < e.commence_time
              AND os.home_spread IS NOT NULL
            ORDER BY os.captured_at DESC LIMIT 1
        ) spread ON true
        LEFT JOIN LATERAL (
            SELECT os.over_under
            FROM odds_snapshots os
            WHERE os.event_id = e.id AND os.captured_at < e.commence_time
              AND os.over_under IS NOT NULL
            ORDER BY os.captured_at DESC LIMIT 1
        ) total ON true
        WHERE e.status IN ('completed', 'closed')
          AND e.commence_time IS NOT NULL
          AND (
              (e.closing_home_probability IS NOT NULL
               AND moneyline.home_win_probability IS NOT NULL
               AND ABS(e.closing_home_probability - moneyline.home_win_probability) > 0.0001)
           OR (e.closing_home_spread IS NOT NULL AND spread.home_spread IS NOT NULL
               AND e.closing_home_spread IS DISTINCT FROM spread.home_spread)
           OR (e.closing_over_under IS NOT NULL AND total.over_under IS NOT NULL
               AND e.closing_over_under IS DISTINCT FROM total.over_under)
          )
        ORDER BY e.id
        """
    )
    sports = await session.execute(sports_sql)
    return {
        "rows": [dict(row._mapping) for row in canonical.all()],
        "sports_closing_mismatches": [dict(row._mapping) for row in sports.all()],
    }


async def load_rows(source: str | Path | Any) -> dict[str, Any]:
    if hasattr(source, "execute"):
        return await load_from_session(source)
    data = json.loads(Path(source).read_text(encoding="utf-8"))
    if isinstance(data, list):
        return {"rows": data, "sports_closing_mismatches": []}
    return {
        "rows": data.get("rows") or data.get("outcomes") or [],
        "sports_closing_mismatches": data.get("sports_closing_mismatches") or [],
    }


def _metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "outcomes": 0,
            "questions": 0,
            "ece": None,
            "mce": None,
            "brier": None,
            "actual_rate_ci95": None,
        }
    bins: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        bins[min(int(row["probability"] * 10), 9)].append(row)
    gaps = [
        abs(
            sum(r["probability"] for r in group) / len(group)
            - sum(r["actual"] for r in group) / len(group)
        )
        for group in bins.values()
    ]
    ece = sum(len(group) / len(rows) * gap for group, gap in zip(bins.values(), gaps))
    brier = sum((r["probability"] - r["actual"]) ** 2 for r in rows) / len(rows)
    analyzed = analyze_cohort(("_all", "_all", "_all"), rows)
    return {
        "outcomes": len(rows),
        "questions": analyzed["independent_questions"],
        "ece": round(ece, 6),
        "mce": round(max(gaps), 6),
        "brier": round(brier, 6),
        "actual_rate_ci95": analyzed["actual_rate_ci95"],
        "uncertainty_method": analyzed["actual_rate_ci95_method"],
    }


def _bucket_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for bucket in range(10):
        group = [r for r in rows if min(int(r["probability"] * 10), 9) == bucket]
        if not group:
            continue
        result.append(
            {
                "bucket": bucket,
                "outcomes": len(group),
                "questions": len({r["question_id"] for r in group}),
                "predicted": round(sum(r["probability"] for r in group) / len(group), 6),
                "actual": round(sum(r["actual"] for r in group) / len(group), 6),
            }
        )
    return result


def _bucket_deltas(
    current: list[dict[str, Any]], counterfactual: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    before = {row["bucket"]: row for row in _bucket_rows(current)}
    after = {row["bucket"]: row for row in _bucket_rows(counterfactual)}
    return [
        {
            "bucket": bucket,
            "outcomes_removed": before.get(bucket, {}).get("outcomes", 0)
            - after.get(bucket, {}).get("outcomes", 0),
            "questions_before": before.get(bucket, {}).get("questions", 0),
            "questions_after": after.get(bucket, {}).get("questions", 0),
            "actual_delta": (
                round(after[bucket]["actual"] - before[bucket]["actual"], 6)
                if bucket in before and bucket in after else None
            ),
        }
        for bucket in sorted(set(before) | set(after))
    ]


def _cohort_counterfactual(
    current: list[dict[str, Any]], counterfactual: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    keys = sorted(
        {
            (r["source"], r["league_category"], r["market_type"])
            for r in current
        }
    )
    output = []
    for key in keys:
        before = [
            r for r in current
            if (r["source"], r["league_category"], r["market_type"]) == key
        ]
        after = [
            r for r in counterfactual
            if (r["source"], r["league_category"], r["market_type"]) == key
        ]
        output.append(
            {
                "source": key[0],
                "league_category": key[1],
                "market_type": key[2],
                "current": _metrics(before),
                "counterfactual": _metrics(after),
            }
        )
    return output


def build_report(payload: dict[str, Any], *, strict_unknown: bool = True) -> dict[str, Any]:
    rows = normalize_rows(payload.get("rows") or [])
    for row in rows:
        row["resolution_class"] = classify_resolution_source(row.get("resolution_source"))
        row["is_mex_normalized"] = bool(row.get("is_mex_normalized"))

    unknown_sources = sorted(
        {str(r["resolution_source"]) for r in rows if r["resolution_class"] == "unknown"}
    )
    if strict_unknown and unknown_sources:
        raise ValueError(f"Unknown resolution sources: {', '.join(unknown_sources)}")

    impacted_questions = {
        r["question_id"] for r in rows if r["resolution_class"] == "price_derived"
    }
    counterfactual = [r for r in rows if r["question_id"] not in impacted_questions]
    upper_bound = [
        r for r in rows
        if r["calibration_probability"] is not None
        and r["current_probability"] is not None
        and (
            math.isclose(float(r["calibration_probability"]), float(r["current_probability"]), abs_tol=1e-6)
            or float(r["calibration_probability"]) <= 0.05
            or float(r["calibration_probability"]) >= 0.95
        )
    ]

    class_counts = Counter(r["resolution_class"] for r in rows)
    source_counts = Counter(str(r["resolution_source"] or "missing") for r in rows)
    census_cells: dict[tuple[str, str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        census_cells[
            (
                row["source"],
                row["league_category"],
                row["market_type"],
                str(row["resolution_source"] or "missing"),
                row["resolution_class"],
            )
        ].append(row)
    resolution_census = [
        {
            "source": key[0],
            "league_category": key[1],
            "market_type": key[2],
            "resolution_source": key[3],
            "resolution_class": key[4],
            "outcomes": len(cell),
            "questions": len({r["question_id"] for r in cell}),
        }
        for key, cell in sorted(census_cells.items())
    ]
    mismatches = payload.get("sports_closing_mismatches") or []
    current_metrics = _metrics(rows)
    counterfactual_metrics = _metrics(counterfactual)
    return {
        "contract": {
            "population": "canonical_deduped_rows",
            "counterfactual": "drop_whole_question_if_any_published_row_is_clean_resolution",
            "websocket_exposure": "upper_bound_not_attribution",
        },
        "current": current_metrics,
        "counterfactual": counterfactual_metrics,
        "metric_delta_counterfactual_minus_current": {
            metric: (
                round(counterfactual_metrics[metric] - current_metrics[metric], 6)
                if counterfactual_metrics[metric] is not None and current_metrics[metric] is not None
                else None
            )
            for metric in ("ece", "mce", "brier")
        },
        "removed": {
            "questions": len(impacted_questions),
            "outcomes": len(rows) - len(counterfactual),
            "normalized_field_questions": len(
                {
                    r["question_id"]
                    for r in rows
                    if r["question_id"] in impacted_questions and r["is_mex_normalized"]
                }
            ),
        },
        "resolution_class_outcomes": dict(sorted(class_counts.items())),
        "resolution_source_outcomes": dict(sorted(source_counts.items())),
        "resolution_census": resolution_census,
        "unknown_resolution_sources": unknown_sources,
        "terminal_price_upper_bound": {
            "outcomes": len(upper_bound),
            "questions": len({r["question_id"] for r in upper_bound}),
            "meaning": "calibration price equals current price or is <=.05/>=.95; not proof of websocket origin",
        },
        "bucket_current": _bucket_rows(rows),
        "bucket_counterfactual": _bucket_rows(counterfactual),
        "bucket_deltas": _bucket_deltas(rows, counterfactual),
        "cohorts": _cohort_counterfactual(rows, counterfactual),
        "sports_closing_mismatches": {
            "count": len(mismatches),
            "event_ids": [row.get("event_id") for row in mismatches],
            "rows": mismatches,
        },
        "unmeasurable": [
            "selected calibration snapshot id/captured_at/selector method",
            "resolution observed_at/effective_at/evidence timestamp",
            "exact Polymarket websocket-derived calibration row count",
        ],
    }


async def run_from_session(session: Any) -> dict[str, Any]:
    return build_report(await load_from_session(session))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="JSON export containing canonical calibration rows")
    parser.add_argument("--allow-unknown", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args()
    report = build_report(
        asyncio.run(load_rows(args.input)), strict_unknown=not args.allow_unknown
    )
    rendered = json.dumps(report, indent=2, default=str) + "\n"
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
