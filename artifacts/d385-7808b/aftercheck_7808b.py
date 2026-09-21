"""AFTER-CHECK for #7808 half two — run against production once a release carries it.

Pays the claim the ship actually makes: `2027 US Open Men's Singles Winner` stops
naming Jakub Mensik, whose book bids 4c, as the man likeliest to win a major, and
leads with a leg somebody is buying.

Written to fail BEFORE the release and required to do so, because an after-check
that has only ever been seen green is not evidence that it can go red.

Three things it deliberately does NOT do:

  * it never reads a PERCENT. The board is live and re-normalises; Sinner's number
    will have moved by the time this is payable, and a percent-keyed check would go
    red on a price move and be called a failed fix.
  * it separates "could not read" (exit 2) from "the defect is served" (exit 1), so
    a market that legitimately falls out of the ranked slice is never recorded as
    either paid or failed.
  * it reads `items[*].data.*`, the shape the feed actually serves. Half one's
    instrument first keyed on `item['top_outcomes']` and printed nine blank rows,
    which would have read as the fix failing.
"""

import json
import os
import subprocess
import sys
import urllib.parse

MARKET_ID = 61308736
NO_BUYER = "Jakub Mensik"       # bid 4c — must NOT be on the card
BUYERS = ("Jannik Sinner", "Carlos Alcaraz")  # bid 7c each — must be


def feed_slice():
    qs = urllib.parse.urlencode({"tags": '["sport:tennis"]', "limit": 9})
    url = f"{os.environ['BAINLUCK_API']}/api/feed?{qs}"
    out = subprocess.run(["curl", "-s", url], capture_output=True, text=True)
    if out.returncode != 0:
        print(f"CANNOT READ: curl exit {out.returncode}")
        sys.exit(2)
    try:
        return json.loads(out.stdout)
    except json.JSONDecodeError:
        print(f"CANNOT READ: not JSON — {out.stdout[:300]!r}")
        sys.exit(2)


def main():
    payload = feed_slice()
    items = payload.get("items") or []
    card = None
    for item in items:
        data = item.get("data") or {}
        if data.get("id") == MARKET_ID:
            card = data
            break
    if card is None:
        print(f"CANNOT READ: {MARKET_ID} is not in this slice "
              f"({len(items)} items). Not a pass and not a failure.")
        sys.exit(2)

    names = [o.get("name") for o in (card.get("top_outcomes") or [])]
    print(f"market {MARKET_ID}: {card.get('name')}")
    print("top_outcomes, in served order (names only, by design):")
    for i, n in enumerate(names, 1):
        print(f"    {i}. {n}")

    problems = []
    if NO_BUYER in names:
        problems.append(
            f"{NO_BUYER!r} is on the card at position {names.index(NO_BUYER) + 1}; "
            f"his book bids 4c and nobody is buying him"
        )
    if names and names[0] == NO_BUYER:
        problems.append(f"and he is LEADING it")
    missing = [b for b in BUYERS if b not in names]
    if missing:
        problems.append(f"legs with a real buyer are absent: {missing}")

    print()
    if problems:
        for p in problems:
            print(f"FAIL: {p}")
        sys.exit(1)
    print(f"PASS: the card is led by {names[0]!r} and {NO_BUYER} is off it.")
    sys.exit(0)


if __name__ == "__main__":
    main()
