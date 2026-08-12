#!/usr/bin/env python3
"""probe_adapter_floor — does every concept adapter 404 on a slug that matches nothing?

UX-P066 / #1793.

## Why this is a script and not just a test

`tests/test_concept_adapter_negative_floor.py` proves the floor exists against an
EMPTY database — the adapter is asked for something when it holds nothing. That is
the right unit guard, and it is not the same question as this one.

This script asks the production question: with the real market corpus loaded, and
every tolerant matching rule live, does a slug that names no competition still come
back 404? Those differ precisely where the bug lived. Tennis passed "no markets ->
None" the whole time; what it failed was "a corpus full of markets, and a slug whose
only surviving token was generic" — `not-a-tournament-zzq` served "Serena Williams to
Win a Tournament in 2026", because a length filter had reduced the slug to the single
word `tournament`.

So: the test guards the floor's EXISTENCE, this guards its BEHAVIOUR under real data.
A defect that only appears when the shelves are full needs a probe that reads a full
shelf.

## What it reads

Public production endpoints only — no admin token, no DB. `/api/event/{key}` is
exactly what a reader is handed, and it is what `horizon_sentinel` reads to decide
"does this event have a page", so measuring anything else would measure a different
system.

    python3 scripts/probe_adapter_floor.py
    python3 scripts/probe_adapter_floor.py --domain tennis --json out.json

## Reading the output

`has_page` uses `horizon_sentinel`'s OWN definition (`horizon_sentinel.py:304-325`):
a 200 carrying non-empty competitors, sections or children. A 200 with a hollow
envelope is NOT a page, and neither the sentinel nor this probe counts it as one —
see gotcha #53, an empty 200 is a response shape, not a fact.

Any `NO FLOOR` row is the #1793 class and should be treated as a P1: serving the
wrong competition is worse than serving nothing, because absence is legible and a
confident wrong answer is not. It also silently disables the sentinel's needs-page
alarm for that entire domain.
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

DEFAULT_API = "https://api.bainluck.com"

# Every domain in `app/utils/event_concept.py`'s registry as of 2026-08-12.
DOMAINS = [
    "golf", "tennis", "f1", "ufc", "boxing", "awards", "election", "soccer", "cycling",
]

# Two probes per domain. Neither can name a real competition.
#   nonsense  — shares no token with anything.
#   near_miss — plausibly SHAPED, and per-domain, so a tolerant matcher gets its
#               best chance to leak. This is the one that catches real defects:
#               the generic-token leak that exposed tennis was a near_miss.
NONSENSE = "zzqqxx-does-not-exist-9999"
NEAR_MISS = {
    "golf": "not-a-tournament-zzq",
    "tennis": "not-a-tournament-zzq",
    "f1": "atlantis-grand-prix",
    "ufc": "ufc-999",
    "boxing": "nobody-vs-nobody",
    "awards": "the-zzq-awards-2031",
    "election": "zzq-general-election-2031",
    "soccer": "zzq-cup-2031",
    "cycling": "tour-de-zzq-2031",
}


def fetch(api: str, key: str, timeout: float = 30.0):
    url = f"{api}/api/event/{key}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, None
    except Exception as exc:  # network/timeout — report, never silently pass
        print(f"    ! request failed for {key}: {exc}", file=sys.stderr)
        return None, None


def describe(payload):
    """What did the adapter actually SERVE, and does it count as a page?"""
    if not isinstance(payload, dict):
        return {"served": "(404)", "n_comp": 0, "n_sec": 0, "n_child": 0, "has_page": False}
    event = payload.get("event") or {}
    primary = payload.get("primary") or {}
    n_comp = len(primary.get("competitors") or [])
    n_sec = len(payload.get("sections") or [])
    n_child = len(payload.get("children") or [])
    return {
        "served": str(event.get("name") or payload.get("detail") or "?")[:60],
        "n_comp": n_comp,
        "n_sec": n_sec,
        "n_child": n_child,
        # horizon_sentinel.py:321-325, deliberately the same rule.
        "has_page": bool(n_comp or n_sec or n_child),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default=DEFAULT_API)
    ap.add_argument("--domain", action="append", help="limit to one domain (repeatable)")
    ap.add_argument("--json", dest="json_out", help="write the rows to this path")
    ap.add_argument("--sleep", type=float, default=1.3,
                    help="seconds between requests; the public API allows 60/min and a "
                         "throttled JSON parses as a false negative")
    args = ap.parse_args()

    domains = args.domain or DOMAINS
    rows = []
    for dom in domains:
        for label, slug in (("nonsense", NONSENSE), ("near_miss", NEAR_MISS.get(dom, NONSENSE))):
            key = f"event:{dom}:{slug}"
            status, payload = fetch(args.api, key)
            info = describe(payload) if status == 200 else {
                "served": f"({status})", "n_comp": 0, "n_sec": 0, "n_child": 0,
                "has_page": False,
            }
            if status is None:
                info["has_page"] = None  # unknown, never "fine"
            rows.append({"domain": dom, "probe": label, "key": key, "http": status, **info})
            print(
                f"{dom:9s} {label:9s} HTTP {str(status):4s}  has_page={str(info['has_page']):5s} "
                f"comp={info['n_comp']:3d} sec={info['n_sec']:2d} child={info['n_child']:4d}  "
                f"served={info['served']}"
            )
            sys.stdout.flush()
            time.sleep(args.sleep)

    leaks = [r for r in rows if r["has_page"]]
    unknown = [r for r in rows if r["has_page"] is None]
    print()
    print(f"=== {len(leaks)} / {len(rows)} probes served a page for a slug matching nothing ===")
    if unknown:
        print(f"⚠️  {len(unknown)} probe(s) could not be measured — NOT the same as a pass.")
    print()
    print("domain     floor")
    for dom in domains:
        mine = [r for r in rows if r["domain"] == dom]
        if any(r["has_page"] is None for r in mine):
            verdict = "UNKNOWN — request failed"
        elif any(r["has_page"] for r in mine):
            verdict = f"** NO FLOOR ** ({sum(1 for r in mine if r['has_page'])}/{len(mine)} leaked)"
        else:
            verdict = "ok (404s)"
        print(f"{dom:10s} {verdict}")

    if args.json_out:
        with open(args.json_out, "w") as fh:
            json.dump(rows, fh, indent=2)
        print(f"\nwrote {args.json_out}")

    # Non-zero when a floor is missing OR a probe could not be measured, so this
    # can gate a rail without anyone having to read it.
    return 1 if (leaks or unknown) else 0


if __name__ == "__main__":
    raise SystemExit(main())
