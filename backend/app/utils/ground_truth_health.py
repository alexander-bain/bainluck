"""Health checks for advisory Discover ground-truth inputs."""

from __future__ import annotations

from typing import Any

DEFAULT_MIN_LOAD_RATE = 0.25


def assess_ground_truth_report_health(
    report: dict[str, Any],
    *,
    label: str,
    min_load_rate: float = DEFAULT_MIN_LOAD_RATE,
) -> dict[str, Any]:
    """Return a compact health summary for a ground-truth report.

    The input is the existing ``{"items": ..., "metadata": ...}`` shape used by
    Polymarket email and external-curator/social ground-truth loaders.
    """
    metadata = report.get("metadata") or {}
    raw_row_count = _int(metadata.get("raw_row_count"))
    loaded_count = _int(metadata.get("loaded_count"))
    configured = bool(metadata.get("configured"))
    filter_counts = metadata.get("filter_counts") or {}
    issues: list[dict[str, str]] = []

    if not configured:
        issues.append(
            {
                "severity": "info",
                "code": "not_configured",
                "message": f"{label} ground truth is not configured.",
            }
        )
    if metadata.get("error"):
        issues.append(
            {
                "severity": "critical",
                "code": "load_error",
                "message": str(metadata["error"]),
            }
        )
    if configured and raw_row_count == 0:
        issues.append(
            {
                "severity": "warning",
                "code": "empty_source",
                "message": f"{label} source returned no rows.",
            }
        )
    if raw_row_count > 0 and loaded_count == 0:
        issues.append(
            {
                "severity": "critical",
                "code": "no_loaded_rows",
                "message": f"{label} parsed zero usable rows from {raw_row_count} raw rows.",
            }
        )
    if raw_row_count > 0 and loaded_count > 0:
        load_rate = loaded_count / raw_row_count
        effective_row_count = _effective_row_count(raw_row_count, filter_counts)
        effective_load_rate = (
            loaded_count / effective_row_count if effective_row_count > 0 else load_rate
        )
        if effective_load_rate < min_load_rate:
            issues.append(
                {
                    "severity": "warning",
                    "code": "low_load_rate",
                    "message": (
                        f"{label} loaded {loaded_count}/{effective_row_count} eligible rows "
                        f"({loaded_count}/{raw_row_count} raw)."
                    ),
                }
            )
    else:
        load_rate = None
        effective_row_count = None
        effective_load_rate = None

    if metadata.get("stale") is True:
        latest_date = metadata.get("latest_date") or "unknown"
        stale_after_days = metadata.get("stale_after_days") or "?"
        issues.append(
            {
                "severity": "warning",
                "code": "stale",
                "message": f"{label} latest date {latest_date} is older than {stale_after_days} days.",
            }
        )

    for source in metadata.get("source_health") or []:
        if source.get("stale") is True:
            source_name = source.get("source") or "unknown source"
            latest_date = source.get("latest_date") or "unknown"
            issues.append(
                {
                    "severity": "warning",
                    "code": "stale_source",
                    "message": f"{label} source {source_name} is stale; latest date {latest_date}.",
                }
            )

    severity = _rollup_severity(issues)
    return {
        "label": label,
        "severity": severity,
        "ok": severity in {"ok", "info"},
        "configured": configured,
        "raw_row_count": raw_row_count,
        "loaded_count": loaded_count,
        "load_rate": round(load_rate, 4) if load_rate is not None else None,
        "eligible_row_count": effective_row_count,
        "eligible_load_rate": round(effective_load_rate, 4)
        if effective_load_rate is not None
        else None,
        "latest_date": metadata.get("latest_date"),
        "latest_source_date": metadata.get("latest_source_date"),
        "latest_loaded_date": metadata.get("latest_loaded_date"),
        "stale": metadata.get("stale"),
        "stale_after_days": metadata.get("stale_after_days"),
        "min_interestingness": metadata.get("min_interestingness"),
        "lookback_days": metadata.get("lookback_days"),
        "cutoff_date": metadata.get("cutoff_date"),
        "filter_counts": filter_counts,
        "issues": issues,
    }


def summarize_ground_truth_health(
    reports: list[dict[str, Any]],
) -> dict[str, Any]:
    """Combine several report health summaries."""
    severity = _rollup_severity(
        [
            {"severity": report.get("severity", "ok")}
            for report in reports
            if report.get("severity")
        ]
    )
    return {
        "severity": severity,
        "ok": severity in {"ok", "info"},
        "reports": reports,
        "issue_count": sum(len(report.get("issues") or []) for report in reports),
    }


def _rollup_severity(issues: list[dict[str, str]]) -> str:
    severities = {issue.get("severity", "info") for issue in issues}
    if "critical" in severities:
        return "critical"
    if "warning" in severities:
        return "warning"
    if "info" in severities:
        return "info"
    return "ok"


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _effective_row_count(raw_row_count: int, filter_counts: dict[str, Any]) -> int:
    """Return rows expected to survive intentional recency/quality filters."""
    if not filter_counts:
        return raw_row_count
    source_rows = _int(filter_counts.get("source_rows")) or raw_row_count
    filtered = (
        _int(filter_counts.get("outside_lookback"))
        + _int(filter_counts.get("non_market_name"))
        + _int(filter_counts.get("low_interestingness"))
    )
    return max(0, source_rows - filtered)
