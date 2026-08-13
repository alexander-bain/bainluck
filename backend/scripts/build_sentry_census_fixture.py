#!/usr/bin/env python3
"""Rebuild the Sentry census fixture that `tests/test_sentry_filter.py` replays (#1501).

The volume claim in #1501 has to be re-derivable, not quoted. This script pulls
the real accepted-event census for one billing cycle out of Sentry's Discover
API and writes ``tests/fixtures/sentry_census_2026_07_21.json.gz``.

Why a fixture and not a live call in the test: the error quota is exhausted, and
Sentry only retains 90 days, so a test that queried live would go silently green
on an empty answer — gotcha #53's shape, which is the same failure mode #1501 is
about.

Usage (needs SENTRY_AUTH_TOKEN + SENTRY_ORG in the environment)::

    python3 scripts/build_sentry_census_fixture.py \
        --start 2026-07-21T00:00:00 --end 2026-07-29T00:00:00

Two anonymisations are applied deliberately:

* ``server_name`` (a Heroku dyno-incarnation UUID) becomes ``d<N>``. Only the
  *partition* matters to the replay, never the identity.
* the production broker hostname becomes ``ec2-0-0-0-0.compute-1.amazonaws.com``.
  The replay sets ``REDIS_URL`` to that host, so the drop rule is exercised
  exactly as in production while no production endpoint enters a tracked file.
  The placeholder keeps the real suffix on purpose: the hostile specimen in the
  test suite shares it, which is the whole point of finding (a).
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import sys
import urllib.parse
import urllib.request

PLACEHOLDER_BROKER_HOST = "ec2-0-0-0-0.compute-1.amazonaws.com"
_HOST_RE = re.compile(r"ec2-\d+-\d+-\d+-\d+\.compute-1\.amazonaws\.com")
_REDIS_URL_RE = re.compile(r"rediss?://[^\s]*")


def _fetch(org: str, token: str, params: list[tuple[str, str]]) -> list[dict]:
    rows: list[dict] = []
    cursor = ""
    for _ in range(60):
        query = list(params)
        if cursor:
            query.append(("cursor", cursor))
        url = f"https://sentry.io/api/0/organizations/{org}/events/?" + urllib.parse.urlencode(query)
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.loads(resp.read())
            link = resp.headers.get("Link", "")
        rows.extend(payload.get("data", []))
        nxt = ""
        for part in link.split(","):
            if 'rel="next"' in part and 'results="true"' in part:
                found = re.search(r'cursor="([^"]*)"', part)
                nxt = found.group(1) if found else ""
        if not nxt:
            break
        cursor = nxt
    return rows


def _scrub(text: str) -> str:
    text = _REDIS_URL_RE.sub("rediss://REDACTED@" + PLACEHOLDER_BROKER_HOST + ":10819", text or "")
    return _HOST_RE.sub(PLACEHOLDER_BROKER_HOST, text)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--out", default="tests/fixtures/sentry_census_2026_07_21.json.gz")
    args = ap.parse_args()

    token = os.getenv("SENTRY_AUTH_TOKEN")
    org = os.getenv("SENTRY_ORG")
    if not token or not org:
        print("SENTRY_AUTH_TOKEN and SENTRY_ORG are required", file=sys.stderr)
        return 2

    base = [
        ("start", args.start),
        ("end", args.end),
        ("project", "-1"),
        ("per_page", "100"),
        ("sort", "-count"),
    ]
    errors = _fetch(org, token, base + [
        ("field", "error.type"), ("field", "culprit"), ("field", "transaction"),
        ("field", "message"), ("field", "server_name"), ("field", "timestamp.to_day"),
        ("field", "count()"), ("query", "event.type:error"),
    ])
    defaults = _fetch(org, token, base + [
        ("field", "message"), ("field", "culprit"), ("field", "logger"),
        ("field", "transaction"), ("field", "server_name"),
        ("field", "timestamp.to_day"), ("field", "count()"), ("query", "event.type:default"),
    ])

    dynos: dict[str, str] = {}

    def dyno(raw: str) -> str:
        raw = raw or "?"
        if raw not in dynos:
            dynos[raw] = f"d{len(dynos)}"
        return dynos[raw]

    raw_rows = []
    for r in errors:
        types = r.get("error.type") or []
        raw_rows.append({
            "kind": "error",
            "day": (r.get("timestamp.to_day") or "")[:10],
            "dyno": dyno(r.get("server_name")),
            "count": r["count()"],
            "exc_type": types[-1] if types else "",
            "culprit": r.get("culprit") or "",
            "transaction": r.get("transaction") or "",
            "logger": "",
            "message": _scrub(r.get("message") or "")[:300],
        })
    for r in defaults:
        raw_rows.append({
            "kind": "default",
            "day": (r.get("timestamp.to_day") or "")[:10],
            "dyno": dyno(r.get("server_name")),
            "count": r["count()"],
            "exc_type": "",
            "culprit": r.get("culprit") or "",
            "transaction": r.get("transaction") or "",
            "logger": r.get("logger") or "",
            "message": _scrub(r.get("message") or "")[:300],
        })

    # Collapse rows that differ ONLY in digits inside the SAME (dyno, day).
    #
    # Sentry groups by exact message, so one condition fragments into hundreds of
    # rows over its hour-value / retry counter / pid / task-uuid. No rule in
    # app/utils/sentry_filter.py keys on a digit, and neither does the throttle
    # signature, so collapsing on the digit-erased message cannot change a single
    # verdict — it only stops a 1.8 MB fixture from entering the repo. One real
    # representative message is kept per merged group, digits intact.
    merged: dict[tuple, dict] = {}
    for row in raw_rows:
        shape = re.sub(r"\d+", "#", row["message"])
        key = (row["kind"], row["day"], row["dyno"], row["exc_type"],
               row["culprit"], row["transaction"], row["logger"], shape)
        hit = merged.get(key)
        if hit is None:
            merged[key] = dict(row)
        else:
            hit["count"] += row["count"]
    rows = sorted(merged.values(), key=lambda r: (r["day"], r["dyno"], -r["count"]))

    out = {
        "_provenance": {
            "source": "Sentry Discover API, organizations/{org}/events/",
            "window": {"start": args.start, "end": args.end},
            "queries": ["event.type:error", "event.type:default"],
            "group_by": ["signature fields", "server_name", "timestamp.to_day"],
            "note": (
                "server_name is anonymised to d<N>; the production broker host is "
                f"replaced with {PLACEHOLDER_BROKER_HOST}. Regenerate with "
                "scripts/build_sentry_census_fixture.py."
            ),
        },
        "broker_host": PLACEHOLDER_BROKER_HOST,
        "days": sorted({r["day"] for r in rows}),
        "dyno_count": len(dynos),
        "totals": {
            "error": sum(r["count"] for r in rows if r["kind"] == "error"),
            "default": sum(r["count"] for r in rows if r["kind"] == "default"),
        },
        "rows": rows,
    }
    # gzipped: the uncompressed census is ~800 KB of highly repetitive text and
    # compresses ~15x. Fidelity is kept in full rather than truncated away.
    with gzip.open(args.out, "wt", encoding="utf-8") as fh:
        json.dump(out, fh, separators=(",", ":"), sort_keys=True)
    print(f"wrote {args.out}: {len(rows)} groups, {sum(r['count'] for r in rows)} events, "
          f"{len(dynos)} dyno incarnations, {len(out['days'])} days")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
