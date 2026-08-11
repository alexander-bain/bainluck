#!/usr/bin/env python3
"""Run SQL queries against production via the admin db-query endpoint.

Usage: python3 backend/scripts/db_query.py "SELECT COUNT(*) FROM futures_markets"

Queue 332 Item 5: ported from the retired ``GET /api/admin/query`` to the single
hardened rail, ``POST /api/admin/db-query``. Two differences matter to anyone reading
old invocations:

  * The token goes in the ``Authorization: Bearer`` header, never ``?secret=``. The
    query-string form leaked through shell history and proxy logs, and had in fact
    stopped authenticating altogether when #252 removed query-param auth — this
    script was 403ing long before the endpoint was retired.
  * A failed query is an HTTP 400 whose body is ``{reason, correlation_id}``, not a
    200 carrying the raw database message. An operator who needs the real error reads
    it out of the logs by correlation id. The old rail's 200-with-error made a failure
    and an empty result the same shape to a caller (gotcha #53).
"""

import json
import os
import sys
import urllib.error
import urllib.request

API = os.environ.get("BAINLUCK_API", "https://api.bainluck.com")


def query(sql: str) -> dict:
    token = os.environ.get("ADMIN_TOKEN", "")
    if not token:
        print("ERROR: ADMIN_TOKEN not set. Run: source ~/.claude/.env", file=sys.stderr)
        sys.exit(1)

    request = urllib.request.Request(
        f"{API}/api/admin/db-query",
        data=json.dumps({"sql": sql}).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        try:
            detail = json.loads(body).get("detail", body)
        except json.JSONDecodeError:
            detail = body
        return {"error": detail}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 db_query.py 'SELECT ...'")
        sys.exit(1)

    result = query(" ".join(sys.argv[1:]))

    if result.get("error"):
        error = result["error"]
        if isinstance(error, dict):
            print(
                f"ERROR: {error.get('reason', 'query_failed')} "
                f"(correlation_id={error.get('correlation_id', '?')})",
                file=sys.stderr,
            )
        else:
            print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)

    columns = result.get("columns") or []
    # The POST rail returns rows as LISTS aligned to `columns`; the retired GET rail
    # returned dicts. Normalising here keeps the printer honest about column order.
    rows = result.get("rows") or []

    if not rows:
        print("(no rows)")
        sys.exit(0)

    widths = {
        index: max(len(str(column)), max(len(str(row[index])) for row in rows))
        for index, column in enumerate(columns)
    }
    print(" | ".join(str(c).rjust(widths[i]) for i, c in enumerate(columns)))
    print("-+-".join("-" * widths[i] for i in range(len(columns))))
    for row in rows:
        print(" | ".join(str(row[i]).rjust(widths[i]) for i in range(len(columns))))

    suffix = " (TRUNCATED at the row cap)" if result.get("truncated") else ""
    print(f"\n({result.get('row_count', len(rows))} rows){suffix}")
