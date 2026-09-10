#!/usr/bin/env python3
"""Run a read-only SELECT against production /api/admin/db-query.

Usage: cal-dbq-1081.py <sql-file> [limit]
Reads BAINLUCK_API / ADMIN_TOKEN from the environment (source ~/.claude/.env first).
Prints a header row then tab-separated rows, so the shape is obvious in a log.
"""
import json
import os
import sys
import urllib.request

sql = open(sys.argv[1]).read().strip().rstrip(";")
limit = int(sys.argv[2]) if len(sys.argv) > 2 else 500

api = os.environ["BAINLUCK_API"].rstrip("/")
token = os.environ["ADMIN_TOKEN"]

req = urllib.request.Request(
    f"{api}/api/admin/db-query",
    data=json.dumps({"sql": sql, "limit": limit}).encode(),
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    method="POST",
)
try:
    with urllib.request.urlopen(req, timeout=60) as r:
        body = json.load(r)
except urllib.error.HTTPError as e:
    print("HTTP", e.code)
    print(e.read().decode()[:2000])
    sys.exit(1)

cols = body.get("columns") or []
rows = body.get("rows") or []
print("\t".join(str(c) for c in cols))
for row in rows:
    print("\t".join("" if v is None else str(v) for v in row))
print(f"-- {len(rows)} rows", file=sys.stderr)
