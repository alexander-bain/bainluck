#!/usr/bin/env python3
"""Run SQL queries against production via the admin query endpoint.

Usage: python3 backend/scripts/db_query.py "SELECT COUNT(*) FROM futures_markets"
"""

import json
import os
import sys
import urllib.parse
import urllib.request


def query(sql: str) -> dict:
    token = os.environ.get("ADMIN_TOKEN", "")
    if not token:
        print("ERROR: ADMIN_TOKEN not set. Run: source .env.claude", file=sys.stderr)
        sys.exit(1)
    url = (
        f"https://api.bainluck.com/api/admin/query"
        f"?secret={urllib.parse.quote(token)}"
        f"&sql={urllib.parse.quote(sql)}"
    )
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.loads(resp.read())


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 db_query.py 'SELECT ...'")
        sys.exit(1)

    sql = " ".join(sys.argv[1:])
    result = query(sql)

    if result.get("error"):
        print(f"ERROR: {result['error']}", file=sys.stderr)
        sys.exit(1)

    if not result.get("rows"):
        print("(no rows)")
        sys.exit(0)

    columns = result["columns"]
    rows = result["rows"]

    widths = {c: max(len(str(c)), max(len(str(r.get(c, ""))) for r in rows)) for c in columns}
    header = " | ".join(str(c).rjust(widths[c]) for c in columns)
    print(header)
    print("-+-".join("-" * widths[c] for c in columns))
    for row in rows:
        print(" | ".join(str(row.get(c, "")).rjust(widths[c]) for c in columns))
    print(f"\n({len(rows)} rows)")
