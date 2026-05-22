#!/usr/bin/env python3
"""Decide whether stored search tsvectors are justified by real traces.

This script is intentionally read-only. It accepts exported production search
queries and optional database access for EXPLAIN ANALYZE on representative
queries. It does not create indexes, migrations, triggers, or table columns.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

MIN_TRACE_ROWS = 500
MIN_UNIQUE_QUERIES = 50
MIN_OBSERVATION_DAYS = 7
TRACE_P95_REVIEW_MS = 300.0
TRACE_P99_REVIEW_MS = 750.0
DB_PLAN_P95_REVIEW_MS = 150.0
DB_PLAN_MAX_REVIEW_MS = 750.0

QUERY_KEYS = ("query", "q", "search_query", "searchTerm", "term")
LATENCY_KEYS = (
    "latency_ms",
    "duration_ms",
    "response_time_ms",
    "elapsed_ms",
    "server_latency_ms",
)
TIMESTAMP_KEYS = ("timestamp", "created_at", "event_time", "time", "date")
RESULT_COUNT_KEYS = ("results_count", "total_results", "result_count")
CLICK_KEYS = ("clicked", "has_click", "result_click", "search_result_click")


@dataclass(frozen=True)
class SearchTrace:
    query: str
    latency_ms: float | None = None
    results_count: int | None = None
    clicked: bool | None = None
    timestamp: datetime | None = None


@dataclass(frozen=True)
class PlanMeasurement:
    surface: str
    query: str
    execution_ms: float
    planning_ms: float
    sequential_scans: int
    sort_nodes: int
    shared_read_blocks: int


@dataclass(frozen=True)
class Decision:
    status: str
    reason: str
    next_step: str


def _first_value(row: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return None


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _to_bool(value: Any) -> bool | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "clicked"}:
        return True
    if normalized in {"0", "false", "no", "n", "none"}:
        return False
    return None


def _to_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if text.isdigit():
        number = int(text)
        if number > 10_000_000_000:
            number = number / 1000
        return datetime.fromtimestamp(number, tz=timezone.utc)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def trace_from_row(row: dict[str, Any]) -> SearchTrace | None:
    query = _first_value(row, QUERY_KEYS)
    if query is None:
        return None
    query = str(query).strip()
    if len(query) < 2:
        return None

    results_count = _to_int(_first_value(row, RESULT_COUNT_KEYS))
    zero_results = _to_bool(row.get("zero_results"))
    if zero_results is True:
        results_count = 0

    return SearchTrace(
        query=query,
        latency_ms=_to_float(_first_value(row, LATENCY_KEYS)),
        results_count=results_count,
        clicked=_to_bool(_first_value(row, CLICK_KEYS)),
        timestamp=_to_datetime(_first_value(row, TIMESTAMP_KEYS)),
    )


def load_traces(path: Path) -> list[SearchTrace]:
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    elif suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            rows = data.get("queries") or data.get("events") or data.get("rows") or []
        else:
            rows = data
    elif suffix == ".csv":
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
    else:
        rows = [
            {"query": line} for line in path.read_text(encoding="utf-8").splitlines()
        ]

    traces = [trace_from_row(row) for row in rows if isinstance(row, dict)]
    return [trace for trace in traces if trace is not None]


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * (pct / 100)
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    weight = rank - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def observation_days(traces: list[SearchTrace]) -> float | None:
    timestamps = [trace.timestamp for trace in traces if trace.timestamp is not None]
    if len(timestamps) < 2:
        return None
    delta = max(timestamps) - min(timestamps)
    return delta.total_seconds() / 86_400


def summarize_traces(traces: list[SearchTrace]) -> dict[str, Any]:
    latencies = [trace.latency_ms for trace in traces if trace.latency_ms is not None]
    query_counts = Counter(trace.query.strip().lower() for trace in traces)
    result_counts = [
        trace.results_count for trace in traces if trace.results_count is not None
    ]
    clicked = [trace.clicked for trace in traces if trace.clicked is not None]

    zero_result_rate = None
    if result_counts:
        zero_result_rate = sum(1 for count in result_counts if count == 0) / len(
            result_counts
        )

    click_rate = None
    if clicked:
        click_rate = sum(1 for value in clicked if value is True) / len(clicked)

    return {
        "trace_rows": len(traces),
        "unique_queries": len(query_counts),
        "observation_days": observation_days(traces),
        "latency_count": len(latencies),
        "latency_ms": {
            "p50": percentile(latencies, 50),
            "p95": percentile(latencies, 95),
            "p99": percentile(latencies, 99),
            "max": max(latencies) if latencies else None,
        },
        "zero_result_rate": zero_result_rate,
        "click_rate": click_rate,
        "top_queries": query_counts.most_common(20),
    }


def representative_queries(traces: list[SearchTrace], limit: int) -> list[str]:
    counts = Counter(trace.query.strip().lower() for trace in traces)
    return [query for query, _count in counts.most_common(limit)]


def _psycopg_url(database_url: str) -> str:
    parsed = urlparse(database_url)
    scheme = parsed.scheme
    if scheme in {"postgres", "postgresql+asyncpg"}:
        scheme = "postgresql"
    return urlunparse(parsed._replace(scheme=scheme))


def _walk_plan(node: dict[str, Any]) -> dict[str, int]:
    totals = {
        "sequential_scans": 1 if node.get("Node Type") == "Seq Scan" else 0,
        "sort_nodes": 1 if node.get("Node Type") == "Sort" else 0,
        "shared_read_blocks": int(node.get("Shared Read Blocks") or 0),
    }
    for child in node.get("Plans") or []:
        child_totals = _walk_plan(child)
        for key, value in child_totals.items():
            totals[key] += value
    return totals


EVENT_PLAN_SQL = """
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT e.id
FROM events e
JOIN sports s ON e.sport_id = s.id
WHERE (
    e.home_team_name ILIKE %(pattern)s
    OR e.away_team_name ILIKE %(pattern)s
)
AND e.commence_time >= now() - interval '30 days'
AND e.status IN ('scheduled', 'live', 'completed', 'closed')
ORDER BY
    ts_rank_cd(
        setweight(to_tsvector('english', coalesce(e.home_team_name, '')), 'A')
        || setweight(to_tsvector('english', coalesce(e.away_team_name, '')), 'A'),
        websearch_to_tsquery('english', %(query)s)
    ) DESC,
    e.commence_time DESC NULLS LAST
LIMIT 25
"""

FUTURES_PLAN_SQL = """
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT fm.id
FROM futures_markets fm
WHERE (
    fm.name ILIKE %(pattern)s
    OR EXISTS (
        SELECT 1
        FROM futures_outcomes fo
        WHERE fo.market_id = fm.id
        AND fo.name ILIKE %(pattern)s
    )
)
AND fm.status = 'open'
AND (fm.resolution_date IS NULL OR fm.resolution_date >= now())
ORDER BY
    ts_rank_cd(
        setweight(to_tsvector('english', coalesce(fm.name, '')), 'B')
        || setweight(
            to_tsvector(
                'english',
                coalesce((
                    SELECT string_agg(fo2.name, ' ')
                    FROM futures_outcomes fo2
                    WHERE fo2.market_id = fm.id
                ), '')
            ),
            'C'
        ),
        websearch_to_tsquery('english', %(query)s)
    ) DESC,
    fm.market_tier ASC NULLS LAST,
    fm.volume DESC NULLS LAST,
    fm.updated_at DESC
LIMIT 20
"""

TEAM_PLAN_SQL = """
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT t.id
FROM teams t
LEFT JOIN sports s ON t.sport_id = s.id
WHERE (
    t.name ILIKE %(pattern)s
    OR t.abbreviation ILIKE %(pattern)s
    OR t.alternate_names::text ILIKE %(pattern)s
)
ORDER BY
    ts_rank_cd(
        setweight(to_tsvector('english', coalesce(t.name, '')), 'A')
        || setweight(to_tsvector('english', coalesce(t.abbreviation, '')), 'A')
        || setweight(to_tsvector('english', coalesce(t.alternate_names::text, '')), 'A'),
        websearch_to_tsquery('english', %(query)s)
    ) DESC,
    t.name
LIMIT 5
"""


def run_db_plans(database_url: str, queries: list[str]) -> list[PlanMeasurement]:
    try:
        import psycopg2
    except ImportError as exc:
        raise SystemExit(
            "psycopg2 is required for --database-url plan analysis"
        ) from exc

    measurements: list[PlanMeasurement] = []
    plan_sql = {
        "events": EVENT_PLAN_SQL,
        "futures": FUTURES_PLAN_SQL,
        "teams": TEAM_PLAN_SQL,
    }

    with psycopg2.connect(_psycopg_url(database_url)) as conn:
        conn.set_session(readonly=True, autocommit=False)
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout = '10s'")
            cur.execute("SET LOCAL default_transaction_read_only = on")
            for query in queries:
                params = {"query": query, "pattern": f"%{query}%"}
                for surface, sql in plan_sql.items():
                    cur.execute(sql, params)
                    explain = cur.fetchone()[0][0]
                    plan_totals = _walk_plan(explain["Plan"])
                    measurements.append(
                        PlanMeasurement(
                            surface=surface,
                            query=query,
                            execution_ms=float(explain.get("Execution Time") or 0),
                            planning_ms=float(explain.get("Planning Time") or 0),
                            sequential_scans=plan_totals["sequential_scans"],
                            sort_nodes=plan_totals["sort_nodes"],
                            shared_read_blocks=plan_totals["shared_read_blocks"],
                        )
                    )
        conn.rollback()
    return measurements


def summarize_plans(measurements: list[PlanMeasurement]) -> dict[str, Any]:
    by_surface: dict[str, list[PlanMeasurement]] = {}
    for measurement in measurements:
        by_surface.setdefault(measurement.surface, []).append(measurement)

    summary: dict[str, Any] = {}
    for surface, rows in sorted(by_surface.items()):
        executions = [row.execution_ms for row in rows]
        summary[surface] = {
            "count": len(rows),
            "execution_ms": {
                "p50": percentile(executions, 50),
                "p95": percentile(executions, 95),
                "max": max(executions) if executions else None,
            },
            "sequential_scan_count": sum(row.sequential_scans for row in rows),
            "sort_node_count": sum(row.sort_nodes for row in rows),
            "shared_read_blocks": sum(row.shared_read_blocks for row in rows),
            "slowest": [
                asdict(row)
                for row in sorted(
                    rows, key=lambda item: item.execution_ms, reverse=True
                )[:5]
            ],
        }
    return summary


def decide(
    trace_summary: dict[str, Any], plan_summary: dict[str, Any] | None
) -> Decision:
    rows = int(trace_summary["trace_rows"])
    unique_queries = int(trace_summary["unique_queries"])
    days = trace_summary["observation_days"]
    enough_window = days is None or days >= MIN_OBSERVATION_DAYS

    if (
        rows < MIN_TRACE_ROWS
        or unique_queries < MIN_UNIQUE_QUERIES
        or not enough_window
    ):
        return Decision(
            status="keep_open_pending_traces",
            reason=(
                f"Need at least {MIN_TRACE_ROWS} rows, {MIN_UNIQUE_QUERIES} unique "
                f"queries, and preferably {MIN_OBSERVATION_DAYS} days before adding "
                "stored vectors."
            ),
            next_step="Collect a larger production trace export, then rerun this script.",
        )

    latency = trace_summary["latency_ms"]
    p95 = latency.get("p95")
    p99 = latency.get("p99")
    trace_slow = (p95 is not None and p95 >= TRACE_P95_REVIEW_MS) or (
        p99 is not None and p99 >= TRACE_P99_REVIEW_MS
    )

    plan_slow = False
    if plan_summary:
        for surface in plan_summary.values():
            plan_latency = surface["execution_ms"]
            surface_p95 = plan_latency.get("p95")
            surface_max = plan_latency.get("max")
            if (surface_p95 is not None and surface_p95 >= DB_PLAN_P95_REVIEW_MS) or (
                surface_max is not None and surface_max >= DB_PLAN_MAX_REVIEW_MS
            ):
                plan_slow = True
                break

    if trace_slow and plan_summary is None:
        return Decision(
            status="collect_db_plans_before_migration",
            reason="Endpoint traces are slow, but there is no database plan evidence yet.",
            next_step=(
                "Run with --database-url against a production follower or short "
                "read-only production window."
            ),
        )

    if trace_slow and plan_slow:
        return Decision(
            status="candidate_for_stored_tsvector_spike",
            reason=(
                "Production traces and representative database plans both exceed "
                "review thresholds."
            ),
            next_step=(
                "Open a migration spike that benchmarks stored vectors and GIN "
                "indexes before shipping triggers."
            ),
        )

    return Decision(
        status="do_not_add_stored_vectors_yet",
        reason=(
            "Current evidence does not show enough search latency pressure to "
            "justify stored vectors."
        ),
        next_step=(
            "Keep query-time FTS, continue collecting search latency and "
            "click/zero-result traces."
        ),
    )


def build_report(
    traces: list[SearchTrace],
    database_url: str | None,
    plan_limit: int,
) -> dict[str, Any]:
    trace_summary = summarize_traces(traces)
    plan_measurements: list[PlanMeasurement] = []
    plan_summary = None

    if database_url:
        plan_queries = representative_queries(traces, plan_limit)
        plan_measurements = run_db_plans(database_url, plan_queries)
        plan_summary = summarize_plans(plan_measurements)

    decision = decide(trace_summary, plan_summary)
    return {
        "decision": asdict(decision),
        "thresholds": {
            "min_trace_rows": MIN_TRACE_ROWS,
            "min_unique_queries": MIN_UNIQUE_QUERIES,
            "min_observation_days": MIN_OBSERVATION_DAYS,
            "trace_p95_review_ms": TRACE_P95_REVIEW_MS,
            "trace_p99_review_ms": TRACE_P99_REVIEW_MS,
            "db_plan_p95_review_ms": DB_PLAN_P95_REVIEW_MS,
            "db_plan_max_review_ms": DB_PLAN_MAX_REVIEW_MS,
        },
        "trace_summary": trace_summary,
        "plan_summary": plan_summary,
        "plan_measurements": [asdict(row) for row in plan_measurements],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit whether stored full-text search vectors are justified."
    )
    parser.add_argument(
        "--queries-file",
        required=True,
        type=Path,
        help="CSV, JSON, JSONL, or TXT export of production search traces.",
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL"),
        help="Optional Postgres URL for read-only EXPLAIN ANALYZE. Defaults to DATABASE_URL.",
    )
    parser.add_argument(
        "--no-db",
        action="store_true",
        help="Skip database EXPLAIN even if DATABASE_URL is set.",
    )
    parser.add_argument(
        "--plan-limit",
        type=int,
        default=25,
        help="Number of most common queries to measure when database analysis is enabled.",
    )
    parser.add_argument(
        "--output",
        choices=("text", "json"),
        default="text",
        help="Report format.",
    )
    args = parser.parse_args(argv)

    traces = load_traces(args.queries_file)
    if not traces:
        raise SystemExit(
            "No valid search traces found. Expected a query/q/search_query field "
            "or one query per TXT line."
        )

    database_url = None if args.no_db else args.database_url
    report = build_report(traces, database_url, args.plan_limit)

    if args.output == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    decision = report["decision"]
    trace_summary = report["trace_summary"]
    print(f"Decision: {decision['status']}")
    print(f"Reason: {decision['reason']}")
    print(f"Next step: {decision['next_step']}")
    print()
    print(
        "Trace sample: "
        f"{trace_summary['trace_rows']} rows, "
        f"{trace_summary['unique_queries']} unique queries, "
        f"{trace_summary['observation_days']} days"
    )
    print(f"Latency ms: {trace_summary['latency_ms']}")
    print(f"Zero-result rate: {trace_summary['zero_result_rate']}")
    print(f"Click rate: {trace_summary['click_rate']}")

    if report["plan_summary"]:
        print()
        print("Plan summary:")
        print(json.dumps(report["plan_summary"], indent=2, sort_keys=True))

    return 0


if __name__ == "__main__":
    sys.exit(main())
