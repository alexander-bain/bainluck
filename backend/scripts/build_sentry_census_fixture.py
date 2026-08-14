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

## Schema 2 — the signature fields, retained (codex C-CERT-SENTRY-R2 finding 3)

Schema 1 kept ``(error.type, culprit, transaction, logger, message)`` and
nothing else. That is strictly LESS than the shipped classifier reads: it
resolves a failure site from an explicit fingerprint, then from the **deepest
in-app stack frame**, and only then falls back to ``culprit``. A fixture with no
frames therefore drives every row down the fallback, which merges distinct
production failure sites into one bucket and makes the replay **undercount**
sends — the optimistic direction, against a margin that was ~5% wide.

That mattered because the other known distortion (empty exception modules)
pushes the other way, so the replay's error was bidirectional and its result
could not be called a ceiling in good conscience.

Schema 2 retains, per row and anonymised but TYPED:

* ``site`` — the deepest ``in_app`` frame as ``module:function``, reconstructed
  from Discover's aligned ``stack.module`` / ``stack.function`` /
  ``stack.in_app`` arrays. This is the exact input ``_failure_site`` prefers.
* ``frame_depth`` — how many frames the event carried, so a row that has no
  in-app frame at all is distinguishable from one we failed to parse.
* ``issue`` — Sentry's OWN grouping id, anonymised to ``g<N>``. It is never fed
  to the filter. It is the independent yardstick that lets the suite measure
  whether our signature collapses distinct production buckets, instead of
  asserting that it does not.
* ``exc_chain`` — the full ordered ``error.type`` list, so ``values[-1]``
  (outermost) is a fact in the fixture rather than a reconstruction.
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

#: Credentials carried in a QUERY STRING, which is how a live secret reached a
#: tracked file and stayed there (found 2026-08-14, queue 351).
#:
#: An error message is not a safe thing to commit. Sentry captured
#: ``Client error '403 Forbidden' for url '...&secret=<64 hex>'`` — the app's real
#: ``ADMIN_TOKEN``, sent on the legacy ``?secret=`` path that Queue #252 removed
#: from auth but did not remove from the CALLER, so it kept being sent, kept
#: 403ing, and kept being recorded. The fixture then gzipped it into the repo.
#:
#: Two reasons it survived a certification that explicitly scanned for secrets:
#: the value is inside a URL inside a message field rather than in anything
#: shaped like a config line, and **the artifact is gzip** — the repo's
#: gitleaks backstop scans text, and a `.gz` blob is opaque to it. A binary
#: fixture is a scanning blind spot, so the scrub has to happen at the source.
#:
#: Scrub the VALUE and keep the parameter name: the name is what makes the
#: leak legible to the next reader.
_QS_CREDENTIAL_RE = re.compile(
    r"(?i)\b(secret|token|api[_-]?key|apikey|password|passwd|pwd|auth|access[_-]?token|"
    r"admin[_-]?token|signature|sig)=([^&\s'\"]+)"
)


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
    text = _HOST_RE.sub(PLACEHOLDER_BROKER_HOST, text)
    return _QS_CREDENTIAL_RE.sub(r"\1=REDACTED", text)


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
        # schema 2: the signature fields the shipped classifier actually reads
        ("field", "issue"), ("field", "stack.module"), ("field", "stack.function"),
        ("field", "stack.in_app"),
        ("field", "count()"), ("query", "event.type:error"),
    ])
    defaults = _fetch(org, token, base + [
        ("field", "message"), ("field", "culprit"), ("field", "logger"),
        ("field", "transaction"), ("field", "server_name"), ("field", "issue"),
        ("field", "timestamp.to_day"), ("field", "count()"), ("query", "event.type:default"),
    ])

    dynos: dict[str, str] = {}
    issues: dict[str, str] = {}

    def dyno(raw: str) -> str:
        raw = raw or "?"
        if raw not in dynos:
            dynos[raw] = f"d{len(dynos)}"
        return dynos[raw]

    def issue(raw) -> str:
        raw = str(raw or "?")
        if raw not in issues:
            issues[raw] = f"g{len(issues)}"
        return issues[raw]

    def deepest_in_app(r) -> tuple[str, int]:
        """``(module:function, frame_depth)`` for the deepest in-app frame.

        Discover returns three parallel arrays, ordered outermost-first exactly
        as Sentry stores them, so the LAST in-app entry is the deepest — the
        same frame ``_failure_site`` picks. Misalignment is possible in
        principle (the arrays are independent columns), so the length check is
        real: a mismatched row records no site rather than a wrong one, and the
        depth still says frames were present.
        """
        mods = r.get("stack.module") or []
        funcs = r.get("stack.function") or []
        flags = r.get("stack.in_app") or []
        depth = max(len(mods), len(funcs))
        if not (len(mods) == len(funcs) == len(flags)) or not mods:
            return "", depth
        chosen = None
        for module, function, in_app in zip(mods, funcs, flags):
            if in_app:
                chosen = (module, function)
        if chosen is None:
            chosen = (mods[-1], funcs[-1])
        return f"{chosen[0] or '?'}:{chosen[1] or '?'}", depth

    raw_rows = []
    for r in errors:
        types = r.get("error.type") or []
        site, depth = deepest_in_app(r)
        raw_rows.append({
            "kind": "error",
            "day": (r.get("timestamp.to_day") or "")[:10],
            "dyno": dyno(r.get("server_name")),
            "count": r["count()"],
            "exc_type": types[-1] if types else "",
            "exc_chain": list(types),
            "culprit": r.get("culprit") or "",
            "transaction": r.get("transaction") or "",
            "logger": "",
            "message": _scrub(r.get("message") or "")[:300],
            "site": _scrub(site),
            "frame_depth": depth,
            "issue": issue(r.get("issue") or r.get("issue.id")),
        })
    for r in defaults:
        raw_rows.append({
            "kind": "default",
            "day": (r.get("timestamp.to_day") or "")[:10],
            "dyno": dyno(r.get("server_name")),
            "count": r["count()"],
            "exc_type": "",
            "exc_chain": [],
            "culprit": r.get("culprit") or "",
            "transaction": r.get("transaction") or "",
            "logger": r.get("logger") or "",
            "message": _scrub(r.get("message") or "")[:300],
            "site": "",
            "frame_depth": 0,
            "issue": issue(r.get("issue") or r.get("issue.id")),
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
        # schema 2: `site` and `issue` join the key. Merging across either would
        # be merging across the exact distinction the fixture now exists to
        # preserve — two failure sites collapsed here are indistinguishable
        # downstream, which is finding 3 rebuilt inside the builder.
        key = (row["kind"], row["day"], row["dyno"], row["exc_type"],
               row["culprit"], row["transaction"], row["logger"], shape,
               row["site"], row["issue"])
        hit = merged.get(key)
        if hit is None:
            merged[key] = dict(row)
        else:
            hit["count"] += row["count"]
    rows = sorted(merged.values(), key=lambda r: (r["day"], r["dyno"], -r["count"]))

    out = {
        "schema_version": 2,
        "_provenance": {
            "source": "Sentry Discover API, organizations/{org}/events/",
            "window": {"start": args.start, "end": args.end},
            "queries": ["event.type:error", "event.type:default"],
            "group_by": ["signature fields", "server_name", "timestamp.to_day"],
            "fields": [
                "error.type", "culprit", "transaction", "message", "logger",
                "server_name", "issue", "stack.module", "stack.function",
                "stack.in_app", "timestamp.to_day", "count()",
            ],
            "note": (
                "server_name is anonymised to d<N>, Sentry's issue id to g<N>; the "
                f"production broker host is replaced with {PLACEHOLDER_BROKER_HOST}. "
                "Regenerate with scripts/build_sentry_census_fixture.py."
            ),
            "schema_2": (
                "site/frame_depth/issue/exc_chain retained so the replay drives the "
                "signature path the shipped classifier actually takes, and so bucket "
                "collapse is MEASURED against Sentry's own grouping rather than assumed."
            ),
        },
        "broker_host": PLACEHOLDER_BROKER_HOST,
        "days": sorted({r["day"] for r in rows}),
        "dyno_count": len(dynos),
        "issue_count": len(issues),
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
