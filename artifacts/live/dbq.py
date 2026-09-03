#!/usr/bin/env python3
"""live/039 — a db-query client that does not fight the shell.

Reads SQL on stdin so a query full of single quotes survives zsh intact, and
prints rows as labelled dicts rather than the raw positional arrays the endpoint
returns.
"""
import json
import os
import sys
import urllib.request

API = os.environ["BAINLUCK_API"]
TOKEN = os.environ["ADMIN_TOKEN"]


def main() -> int:
    sql = sys.stdin.read().strip()
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    body = json.dumps({"sql": sql, "limit": limit}).encode()
    req = urllib.request.Request(
        f"{API}/api/admin/db-query",
        data=body,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.load(resp)
    except urllib.error.HTTPError as exc:
        print(f"HTTP {exc.code}: {exc.read().decode()[:2000]}")
        return 1

    cols = payload.get("columns") or []
    rows = payload.get("rows")
    if rows is None:
        print(json.dumps(payload, indent=2, default=str)[:4000])
        return 0
    print(f"columns: {cols}   rows: {len(rows)}")
    for row in rows:
        print(json.dumps(dict(zip(cols, row)), default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
