#!/usr/bin/env python3
"""#7872 — simulate the proposed subtraction over every served futures card.

The proposal: inside `feedContextSnippet`'s four-door chain, each candidate also
loses a resolution-window clause when the card's own eyebrow already prints the
same field. Measures what every card's caption becomes, and names every card
that ends up SILENT as a result.

Usage: python3 simulate_7872.py <feed.json>
"""
import json
import re
import sys

from census_7872 import caption, resolves_label, strip_head

WINDOW_CLAUSE = r"resolv(?:es|ing) within (?:a day|two days|a week|a month)"
# whole string
RE_WHOLE = re.compile(rf"^(?:{WINDOW_CLAUSE})\.?$", re.I)
# trailing clause after ; — or after , when nothing follows
RE_TAIL = re.compile(rf"\s*[;,]\s*(?:{WINDOW_CLAUSE})\.?\s*$", re.I)
# leading clause followed by , and more text
RE_HEAD = re.compile(rf"^(?:{WINDOW_CLAUSE})\s*,\s*", re.I)


def strip_window(text):
    raw = (text or "").strip()
    if not raw:
        return ""
    if RE_WHOLE.match(raw):
        return ""
    out = RE_TAIL.sub("", raw)
    out = RE_HEAD.sub("", out)
    out = out.strip()
    if not out:
        return ""
    return out[0].upper() + out[1:]


def new_caption(item, eyebrow):
    data = item.get("data") or {}
    heading = data.get("name")
    trail = []
    for label, c in (
        ("context_summary", item.get("context_summary")),
        ("headline", item.get("headline")),
        ("reason", item.get("reason")),
        ("hook_description", data.get("hook_description")),
    ):
        t = strip_head(c, heading).strip()
        if eyebrow:
            t = strip_window(t)
        trail.append((label, t))
        if t:
            return t, label, trail
    return "", None, trail


def main():
    with open(sys.argv[1]) as fh:
        payload = json.load(fh)
    items = payload.get("items") or payload.get("feed") or []
    futures = [i for i in items if i.get("type") == "futures"]

    changed, silenced, unchanged = [], [], 0
    for i in futures:
        data = i.get("data") or {}
        eyebrow, branch = resolves_label(data.get("resolution_date"))
        before = caption(i)
        after, door, trail = new_caption(i, eyebrow)
        if before == after:
            unchanged += 1
            continue
        row = {
            "name": data.get("name"),
            "eyebrow": eyebrow,
            "branch": branch,
            "before": before,
            "after": after,
            "door": door,
            "trail": trail,
        }
        (silenced if not after else changed).append(row)

    print(f"futures cards: {len(futures)}   unchanged: {unchanged}")
    print(f"CHANGED (caption keeps saying something): {len(changed)}")
    print(f"SILENCED (caption becomes empty): {len(silenced)}")
    print()
    for r in changed:
        print(f"  {r['name']}   [{r['eyebrow']}]")
        print(f"    before: {r['before']}")
        print(f"    after : {r['after']}   (door: {r['door']})")
    print()
    print("=== SILENCED — every door, so the loss is visible ===")
    for r in silenced:
        print(f"  {r['name']}   [{r['eyebrow']}]")
        print(f"    before: {r['before']}")
        for label, t in r["trail"]:
            print(f"      {label:<17}: {t!r}")
    # control: no card WITHOUT an eyebrow may be touched
    print()
    print("=== CONTROL: cards with no eyebrow ===")
    for i in futures:
        data = i.get("data") or {}
        eyebrow, branch = resolves_label(data.get("resolution_date"))
        if eyebrow:
            continue
        before = caption(i)
        after, _, _ = new_caption(i, eyebrow)
        print(f"  [{branch}] {data.get('name')}")
        print(f"    before: {before!r}")
        print(f"    after : {after!r}   {'UNTOUCHED' if before == after else '*** CHANGED — BUG ***'}")


if __name__ == "__main__":
    main()
