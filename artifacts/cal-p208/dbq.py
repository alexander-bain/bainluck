#!/usr/bin/env python3
"""Thin db-query client for the calibration lane. Prints raw body on refusal (no `rows` key)."""
import json, os, sys, urllib.request

API = os.environ["BAINLUCK_API"].rstrip("/")
TOK = os.environ["ADMIN_TOKEN"]


def q(sql, limit=500):
    body = json.dumps({"sql": sql, "limit": limit}).encode()
    req = urllib.request.Request(
        f"{API}/api/admin/db-query", data=body,
        headers={"Authorization": f"Bearer {TOK}", "Content-Type": "application/json"},
    )
    try:
        raw = urllib.request.urlopen(req, timeout=40).read().decode()
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
    d = json.loads(raw)
    if "rows" not in d:
        print("REFUSED / no rows key:", raw, file=sys.stderr)
        return None
    return d


if __name__ == "__main__":
    sql = sys.stdin.read()
    d = q(sql)
    if d is None:
        sys.exit(2)
    print(json.dumps(d, indent=1, default=str))
