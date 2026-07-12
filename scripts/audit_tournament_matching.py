#!/usr/bin/env python3
"""Tournament-completeness audit (#999 / L2-62).

Per event concept, measures how completely the event-group matcher has gathered
the tournament's markets: the winner-field entrant count + the associated child
markets (matchups/props), broken down by source. This is the number we hill-climb
from now on — "Wimbledon is a row, not a project" (Alex).

Modeled on the L1–L4 matching-audit pattern (measure → fix → re-measure). Runs
against the live API (no DATABASE_URL needed): `/api/event/{key}` for the matched
result, and the admin db-query aggregate for a domain candidate ceiling.

Usage:
    source ~/.claude/.env
    python3 scripts/audit_tournament_matching.py            # print table
    python3 scripts/audit_tournament_matching.py --save      # write baseline JSON
    python3 scripts/audit_tournament_matching.py --compare    # diff vs saved baseline
"""

import argparse
import json
import os
import subprocess
import sys
from collections import Counter

_SNAPSHOT = os.path.join(os.path.dirname(__file__), ".audit_tournament_matching.json")

# Event rows to track. `candidate_sql` is a domain heuristic ceiling (source
# markets that COULD belong); associated = what the matcher actually grouped.
EVENTS = [
    {
        "key": "event:tennis:2026-women-s-wimbledon-winner",
        "label": "Wimbledon (Women)",
        "candidate_sql": (
            "SELECT count(*) FROM futures_markets WHERE llm_sport_category='tennis' "
            "AND status='open' AND (name ILIKE '% vs %' OR name ILIKE '% v %')"
        ),
    },
    {
        "key": "event:golf:the-open-championship",
        "label": "The Open (Golf)",
        "candidate_sql": (
            "SELECT count(*) FROM futures_markets WHERE llm_sport_category='golf' "
            "AND status='open'"
        ),
    },
    {
        "key": "event:tennis:2026-women-s-us-open-winner-tennis",
        "label": "US Open (Women)",
        "candidate_sql": (
            "SELECT count(*) FROM futures_markets WHERE llm_sport_category='tennis' "
            "AND status='open' AND (name ILIKE '% vs %' OR name ILIKE '% v %')"
        ),
    },
    {
        # L2-87 (B6): the awards adapter's non-sports proof. The ceiling is every
        # open Oscar market (categories + nominations + novelties); the adapter
        # groups the currently-active edition into co-equal category children.
        "key": "event:awards:oscars",
        "label": "Oscars (Awards)",
        "candidate_sql": (
            "SELECT count(*) FROM futures_markets WHERE status='open' "
            "AND external_id ILIKE '%KXOSCAR%'"
        ),
    },
]


def _api() -> str:
    api = os.getenv("BAINLUCK_API")
    if not api:
        print("ERROR: set BAINLUCK_API (source ~/.claude/.env)", file=sys.stderr)
        sys.exit(2)
    return api.rstrip("/")


def _curl_json(url: str, headers=None, method="GET", body=None):
    cmd = ["curl", "-s", "-X", method, url]
    for h in headers or []:
        cmd += ["-H", h]
    if body is not None:
        cmd += ["-d", body]
    try:
        out = subprocess.check_output(cmd, timeout=40)
        return json.loads(out)
    except Exception as exc:  # noqa: BLE001
        return {"__error__": str(exc)}


def _candidate_count(api: str, token: str, sql: str) -> int | None:
    body = json.dumps({"sql": sql, "limit": 1})
    d = _curl_json(
        f"{api}/api/admin/db-query",
        headers=[f"Authorization: Bearer {token}", "Content-Type: application/json"],
        method="POST",
        body=body,
    )
    rows = d.get("rows") if isinstance(d, dict) else None
    if rows and rows[0]:
        try:
            return int(rows[0][0])
        except (TypeError, ValueError):
            return None
    return None


def audit() -> dict:
    api = _api()
    token = os.getenv("ADMIN_TOKEN", "")
    result = {"events": []}
    for ev in EVENTS:
        env = _curl_json(f"{api}/api/event/{ev['key']}")
        if not isinstance(env, dict) or "event" not in env:
            row = {"label": ev["label"], "key": ev["key"], "found": False,
                   "entrants": 0, "children": 0, "by_source": {}, "candidate": None}
        else:
            children = env.get("children") or []
            by_source, by_method = Counter(), Counter()
            for c in children:
                by_source[c.get("source") or c.get("src") or "?"] += 1
                by_method[c.get("method") or "?"] += 1
            candidate = _candidate_count(api, token, ev["candidate_sql"])
            # Unassociated candidate pool = the ceiling minus what we grouped (the
            # number we hill-climb DOWN). Never below 0.
            unassociated = (
                max(candidate - len(children), 0) if candidate is not None else None
            )
            row = {
                "label": ev["label"],
                "key": ev["key"],
                "found": True,
                "status": env.get("event", {}).get("status"),
                "entrants": len((env.get("primary") or {}).get("competitors") or []),
                "children": len(children),
                "by_source": dict(by_source),
                "by_method": dict(by_method),
                "candidate": candidate,
                "unassociated": unassociated,
            }
        result["events"].append(row)
    return result


def print_table(data: dict, baseline: dict | None = None):
    base_by_key = {e["key"]: e for e in (baseline or {}).get("events", [])}
    print(f"{'Event':<22} {'Status':<9} {'Entr':>5} {'Child':>6} {'Unassoc':>8}  By-method / by-source")
    print("-" * 92)
    for e in data["events"]:
        if not e["found"]:
            print(f"{e['label']:<22} {'NOT FOUND':<9}")
            continue
        delta = ""
        if e["key"] in base_by_key:
            d = e["children"] - base_by_key[e["key"]].get("children", 0)
            if d:
                delta = f"  ({'+' if d > 0 else ''}{d} vs baseline)"
        bymeth = ", ".join(f"{k}:{v}" for k, v in sorted(e.get("by_method", {}).items()))
        bysrc = ", ".join(f"{k}:{v}" for k, v in sorted(e["by_source"].items()))
        unassoc = e.get("unassociated")
        unassoc_s = str(unassoc) if unassoc is not None else "—"
        print(f"{e['label']:<22} {e.get('status',''):<9} {e['entrants']:>5} {e['children']:>6} {unassoc_s:>8}  [{bymeth}] ({bysrc}){delta}")


def main():
    p = argparse.ArgumentParser(description="Tournament-completeness audit (#999)")
    p.add_argument("--save", action="store_true", help="write current result as the baseline")
    p.add_argument("--compare", action="store_true", help="diff current vs saved baseline")
    args = p.parse_args()

    data = audit()
    baseline = None
    if args.compare and os.path.exists(_SNAPSHOT):
        baseline = json.load(open(_SNAPSHOT))
    print_table(data, baseline)
    if args.save:
        json.dump(data, open(_SNAPSHOT, "w"), indent=2)
        print(f"\nSaved baseline -> {_SNAPSHOT}")


if __name__ == "__main__":
    main()
