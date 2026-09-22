#!/usr/bin/env python3
"""#7872 census — which futures cards print their resolution twice.

Replicates the two strings the card actually renders, from the served payload:
  eyebrow  = resolvesLabel(data.resolution_date)      (discover/utils.ts:91)
  caption  = feedContextSnippet(item)                 (discover/utils.ts:592)

Usage: python3 census_7872.py <feed.json>
"""
import json
import re
import sys
from datetime import datetime, timezone

NOW = datetime.now(timezone.utc)


def parse(d):
    if not d:
        return None
    try:
        s = d.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def resolves_label(d):
    """discover/utils.ts resolvesLabel — returns (text, branch)."""
    dt = parse(d)
    if dt is None:
        return "", "no-date"
    diff_h = (dt - NOW).total_seconds() / 3600
    if diff_h < 0:
        return "", "past"
    if diff_h < 1:
        return f"Closes in {max(1, round(diff_h * 60))}m", "minutes"
    if diff_h < 24:
        return f"Closes in {round(diff_h)}h", "hours"
    if diff_h < 48:
        return "Closes tomorrow", "tomorrow"
    if diff_h < 168:
        return f"Closes {dt.strftime('%b %-d')}", "closes-date"
    return f"Resolves {dt.strftime('%b %-d, %Y')}", "resolves-date"


TRUNC = re.compile(r"^(.{12,}?)\.\.\.(?=\s|$)")


def strip_head(text, name):
    raw = (text or "").strip()
    name = (name or "").strip().rstrip("? ").strip()
    if not raw or not name:
        return raw
    cut = -1
    if raw.lower().startswith(name.lower()):
        cut = len(name)
    else:
        m = TRUNC.match(raw)
        if m and name.lower().startswith(m.group(1).strip().lower()):
            cut = len(m.group(0))
    if cut < 0:
        return raw
    rest = re.sub(r"^[\s:,;–—-]+", "", raw[cut:])
    if not rest:
        return ""
    return rest[0].upper() + rest[1:]


def caption(item):
    data = item.get("data") or {}
    heading = data.get("name")
    for c in (
        item.get("context_summary"),
        item.get("headline"),
        item.get("reason"),
        data.get("hook_description"),
    ):
        t = strip_head(c, heading).strip()
        if t:
            return t
    return ""


WINDOW_RE = re.compile(
    r"resolves within (a day|two days|a week|a month)|resolving (today|soon)|"
    r"resolves (today|tomorrow|this month|next month)",
    re.I,
)


def main():
    with open(sys.argv[1]) as fh:
        payload = json.load(fh)
    items = payload.get("items") or payload.get("feed") or []
    futures = [i for i in items if i.get("type") == "futures"]
    rows = []
    for i in futures:
        data = i.get("data") or {}
        eyebrow, branch = resolves_label(data.get("resolution_date"))
        cap = caption(i)
        m = WINDOW_RE.search(cap)
        rows.append(
            {
                "name": data.get("name"),
                "id": data.get("id"),
                "resolution_date": data.get("resolution_date"),
                "eyebrow": eyebrow,
                "branch": branch,
                "caption": cap,
                "window_clause": m.group(0) if m else None,
            }
        )

    dup = [r for r in rows if r["eyebrow"] and r["window_clause"]]
    from collections import Counter

    print(f"futures cards: {len(rows)}")
    print("eyebrow branch:", dict(Counter(r["branch"] for r in rows)))
    print("captions with a window clause:", sum(1 for r in rows if r["window_clause"]))
    print(f"BOTH (the defect): {len(dup)}")
    print()
    for r in dup:
        print(f"  {r['name']}")
        print(f"    eyebrow  [{r['branch']}]: {r['eyebrow']}")
        print(f"    caption            : {r['caption']}")
        print(f"    clause             : {r['window_clause']!r}")
    print()
    print("--- window clause but NO eyebrow (not the defect) ---")
    for r in rows:
        if r["window_clause"] and not r["eyebrow"]:
            print(f"  [{r['branch']}] {r['name']} :: {r['caption']}")
    with open(sys.argv[1].replace(".json", "-census.json"), "w") as out:
        json.dump(rows, out, indent=1)


if __name__ == "__main__":
    main()
