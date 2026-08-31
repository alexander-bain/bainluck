"""Shared read-rail helpers for CAL-P155 probes. Read-only; no writes, no tasks."""
import json
import os
import sys
import urllib.error
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "backend"))
API = os.environ.get("BAINLUCK_API", "").rstrip("/")
TOKEN = os.environ.get("ADMIN_TOKEN", "")


def query(sql: str, limit: int = 500, timeout_ms: int | None = None) -> dict:
    payload = {"sql": sql, "limit": limit}
    if timeout_ms is not None:
        payload["timeout_ms"] = timeout_ms
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{API}/api/admin/db-query",
        data=body,
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=180) as fh:
        return json.load(fh)


def rows_as_dicts(res: dict) -> list[dict]:
    """db-query rows are ARRAYS — zip against the declared column order."""
    cols = res.get("columns") or []
    return [dict(zip(cols, row)) for row in (res.get("rows") or [])]


def chain(tail: str, market_info_extra: str = "") -> str:
    from app.tasks.precompute_calibration import _calibration_population_ctes
    from app.utils.sql_comment_strip import count_statement_separators, strip_sql_comments

    raw = "WITH " + _calibration_population_ctes(market_info_extra=market_info_extra) + tail
    sql = strip_sql_comments(raw)
    seps = count_statement_separators(sql)
    if seps:
        raise RuntimeError(f"stripped copy still carries {seps} semicolon(s)")
    return sql
