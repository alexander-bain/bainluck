#!/usr/bin/env python3
"""#8237 — sweep every served futures card against its own page, and ATTRIBUTE each split.

    source ~/.claude/.env && python3 artifacts-discover/d438/crossread_8237.py [--tag BEFORE]

Exit 0 = no split in the withheld class · 1 = splits found · 2 = UNPAYABLE (empty window).

Unlike d437's after-check this carries NO watch list: the two filed specimens rotate
out of the feed within the hour (d437 trap N-F), so the population is "every futures
card the reader is served right now" and the verdict is about the CLASS.

Each split is attributed, because a split can have more than one cause:
  withheld  -> the page has `prices_withheld > 0` and refuses the squeeze (#7103),
               while the card drops those legs (#7632) and divides by the remainder.
               This is #8237.
  ceiling   -> priced sum is outside the band on one side only.
  other     -> neither; needs its own read before anyone calls it #8237.

The implied card divisor (page/card) is printed beside the page's own priced sum, so
the mechanism is measured on each row rather than assumed from the count.
"""
import json
import os
import subprocess
import sys
import time

API = os.environ.get("BAINLUCK_API")
if not API:
    print("BAINLUCK_API unset — `source ~/.claude/.env` first")
    sys.exit(2)

TAG = "BEFORE"
if "--tag" in sys.argv:
    TAG = sys.argv[sys.argv.index("--tag") + 1]

CATEGORIES = ["soccer", "football", "entertainment", "basketball", "baseball",
              "politics", "economics"]
FIELD_SUM_MAX = 1.60


def get(url, tries=4):
    """GET with the 429 body handled: it is valid JSON, so a naive reader raises
    KeyError and reads as a broken probe instead of a rate limit (d437 trap N-E)."""
    for _ in range(tries):
        raw = subprocess.run(
            ["curl", "-s", "-w", "\n%{http_code}", url], capture_output=True, text=True
        ).stdout
        body, _, code = raw.rpartition("\n")
        code = code.strip()
        if code == "429":
            try:
                time.sleep(float(json.loads(body).get("retry_after", 15)) + 2)
            except Exception:
                time.sleep(17)
            continue
        if code != "200":
            print(f"  ! HTTP {code} on {url.split('/api/')[-1][:60]}")
            return None
        try:
            return json.loads(body)
        except Exception:
            return None
    return None


def served_cards():
    cards = {}
    for cat in CATEGORIES:
        d = get(f"{API}/api/feed?limit=250&category={cat}&include_events=false")
        if not d:
            continue
        for item in d.get("items", []):
            if item.get("type") != "futures":
                continue
            data = item.get("data") or {}
            outs = data.get("top_outcomes") or []
            if data.get("id") and outs:
                cards.setdefault(int(data["id"]), (cat, data.get("name", ""), outs))
        time.sleep(1.2)
    return cards


def main():
    cards = served_cards()
    print(f"[{TAG}] served futures cards across {len(CATEGORIES)} categories: {len(cards)}\n")
    if not cards:
        print("UNPAYABLE — empty window: no futures cards served. NOT a pass.")
        return 2

    hdr = f"{'id':<11}{'leader':<24}{'CARD':>8}{'PAGE':>8}{'sum':>8}{'div':>7}{'wh':>5}  class"
    print(hdr)
    print("-" * len(hdr))
    splits, checked = [], 0
    rows = []
    for mid in sorted(cards):
        cat, name, outs = cards[mid]
        detail = get(f"{API}/api/futures/{mid}")
        time.sleep(1.0)
        if not detail or "outcomes" not in detail:
            continue
        page_by_name = {o["name"]: o.get("probability") for o in detail["outcomes"]}
        withheld = detail.get("prices_withheld") or 0
        # Read, never inferred from the sum: `20269743` carries a withheld leg AND
        # a band sum and is NOT this class, because it is non-exclusive — the two
        # surfaces diverge there BY DESIGN (the card divides gotcha #58's
        # independent-binary field; the page keeps it raw under #199). A
        # sum-and-withheld heuristic called it #8237 and overstated the class by one.
        me = detail.get("mutually_exclusive")
        priced = [o["probability"] for o in detail["outcomes"]
                  if o.get("probability") is not None]
        psum = sum(priced)

        lead = outs[0]
        card = lead.get("probability")
        page = page_by_name.get(lead["name"])
        if card is None or page is None:
            continue
        checked += 1
        agrees = abs(card - page) <= 0.005
        div = round(page / card, 4) if card else None
        if agrees:
            klass = "agree"
        elif me and withheld > 0:
            klass = "WITHHELD (#8237)"
        elif not me:
            klass = "non-ME (by design)"
        else:
            klass = "other (ME, nothing withheld)"
        rows.append((mid, lead["name"], card, page, psum, div, withheld, klass, name, cat, me))
        if not agrees:
            splits.append(rows[-1])
            print(f"{mid:<11}{lead['name'][:23]:<24}{card:>8}{page:>8}"
                  f"{psum:>8.3f}{(div if div else 0):>7.3f}{withheld:>5}  {klass}")

    if not checked:
        print("\nUNPAYABLE — cards served but no leader priced on both sides. NOT a pass.")
        return 2

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"crossread-{TAG}.json")
    with open(out, "w") as fh:
        json.dump([dict(zip(
            "id leader card page priced_sum implied_div withheld class market category me".split(),
            r)) for r in rows], fh, indent=1)

    by = {}
    for r in splits:
        by[r[7]] = by.get(r[7], 0) + 1
    print(f"\n[{TAG}] cross-read {checked} cards · {len(splits)} split · {by or 'none'}")
    print(f"rows -> {out}")
    # The verdict is about THIS class only. A non-ME split is the deliberate
    # divergence and is not a failure of #8237; it is counted and printed so
    # nobody reads its disappearance — or its persistence — as this fix's doing.
    mine = by.get("WITHHELD (#8237)", 0)
    print(f"[{TAG}] #8237 class: {mine}")
    return 1 if mine else 0


if __name__ == "__main__":
    sys.exit(main())
