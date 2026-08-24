#!/usr/bin/env python3
"""Recorded-evidence wrapper around ``POST /api/admin/db-query``.

``db_query.py`` prints a table. That is fine for a look, and useless as evidence:
it drops ``sql_fingerprint``, ``duration_ms`` and ``truncated`` on the floor, so a
number quoted from it cannot be re-found, re-run, or checked for the 1,000-row cap.
Every figure in ``artifacts/subcohort2/SUBCOHORT_DIAGNOSIS.md`` cites a stored JSON
with those three fields; this is the thing that stores them.

It also makes the two failure shapes distinguishable (gotcha #53). A statement
timeout, a refusal by the read guard, and an honest zero-row answer all arrive as
"nothing useful" to a careless caller. Here they are ``status: failed`` with a
``reason``, ``status: refused``, and ``status: ok`` with ``row_count: 0``
respectively — recorded, not inferred.

Usage:
    python3 backend/scripts/dbq_probe.py --label my_probe --out artifacts/x \\
        --timeout-ms 10000 --sql "SELECT 1"
    python3 backend/scripts/dbq_probe.py --label my_probe --out artifacts/x \\
        --sql-file /tmp/query.sql
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API = os.environ.get("BAINLUCK_API", "https://api.bainluck.com")


def run(sql: str, timeout_ms: int, explain: bool = False, analyze: bool = False) -> dict:
    token = os.environ.get("ADMIN_TOKEN", "")
    if not token:
        print("ERROR: ADMIN_TOKEN not set. Run: source ~/.claude/.env", file=sys.stderr)
        sys.exit(2)

    body: dict = {"sql": sql}
    if explain:
        body["explain"] = True
    if analyze:
        body["analyze"] = True
    if explain or analyze:
        # MEASURED 2026-08-24: the endpoint refuses `timeout_ms` on the ROW path
        # ("only supported with `explain: true`"). The row path is therefore fixed
        # at the server's 10 s budget and cannot be widened from here — which is
        # why the folds below shard the population instead of asking for longer.
        body["timeout_ms"] = timeout_ms

    request = urllib.request.Request(
        f"{API}/api/admin/db-query",
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=(timeout_ms / 1000.0) + 30) as response:
            payload = json.loads(response.read())
        payload["status"] = "ok"
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode(errors="replace")
        try:
            detail = json.loads(raw).get("detail", raw)
        except json.JSONDecodeError:
            detail = raw
        if isinstance(detail, dict):
            reason = detail.get("reason", "query_failed")
            correlation = detail.get("correlation_id")
        else:
            reason = str(detail)[:400]
            correlation = None
        payload = {
            # A timeout is a fact about the query shape; a refusal is a fact about the
            # read guard. Naming them apart is the whole point of recording at all.
            "status": "failed" if "timeout" in reason.lower() else "refused",
            "reason": reason,
            "correlation_id": correlation,
            "http_status": exc.code,
        }
    except Exception as exc:  # transport, not the database
        payload = {"status": "transport_error", "reason": f"{type(exc).__name__}: {exc}"[:400]}

    payload["wall_ms"] = round((time.monotonic() - started) * 1000, 1)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True, help="artifact basename")
    parser.add_argument("--out", required=True, help="artifact directory")
    parser.add_argument("--sql")
    parser.add_argument("--sql-file")
    parser.add_argument("--timeout-ms", type=int, default=10_000)
    parser.add_argument("--explain", action="store_true")
    parser.add_argument("--analyze", action="store_true")
    parser.add_argument("--note", default="")
    args = parser.parse_args()

    if bool(args.sql) == bool(args.sql_file):
        print("ERROR: pass exactly one of --sql / --sql-file", file=sys.stderr)
        return 2
    sql = args.sql if args.sql else Path(args.sql_file).read_text()

    result = run(sql, args.timeout_ms, explain=args.explain, analyze=args.analyze)
    result["label"] = args.label
    result["note"] = args.note
    result["timeout_ms_requested"] = args.timeout_ms

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{args.label}.json"
    path.write_text(json.dumps(result, indent=2, default=str))

    status = result.get("status")
    print(f"[{status}] {args.label} -> {path}")
    print(
        f"  fp={result.get('sql_fingerprint')} "
        f"duration_ms={result.get('duration_ms')} wall_ms={result.get('wall_ms')} "
        f"rows={result.get('row_count')} truncated={result.get('truncated')}"
    )
    if status != "ok":
        print(f"  reason={result.get('reason')} corr={result.get('correlation_id')}")
        return 1
    for row in (result.get("rows") or [])[:40]:
        print("  " + " | ".join(str(v) for v in row))
    if result.get("columns"):
        print("  columns: " + ", ".join(str(c) for c in result["columns"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
