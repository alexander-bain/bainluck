#!/usr/bin/env python3
"""UX-P124 item 1+2 — characterize a set of Discover captures.

MEASUREMENT ONLY. Reads the raw payloads `capture-top20.sh` wrote; touches no
network and no production state. Everything it prints is derived from files.

WHAT IT REFUSES TO DO
---------------------
It will not report a churn/repeat number from a single pull. "Repeat rate" over
one observation is not a small sample, it is an undefined quantity, and the
tempting thing to print (0%? 100%?) is a number a reader will quote. With fewer
than two pulls on a surface the verdict is UNKNOWN and says why — the UX-P123
lesson that an invariant nothing could violate is not evidence.

CARD IDENTITY
-------------
Cards are keyed the way the backend keys them (`futures:<id>`, `event:<id>`,
`concept:<key>`, `bundle:<key>`) rather than by rendered name. Two pulls can
render the same market under different headline text as its movement changes,
and a name-keyed diff would score that as churn when the user is looking at the
same card. Identity is the thing that decides whether a returning user has seen
it before.
"""

import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone


def card_key(item):
    """Stable identity for a feed card, mirroring the backend's card_key shape."""
    t = item.get("type")
    d = item.get("data") or {}
    if t == "futures":
        return f"futures:{d.get('id')}"
    if t == "event":
        return f"event:{d.get('id')}"
    if t == "concept":
        return f"concept:{d.get('key') or d.get('name')}"
    if t == "tournament":
        return f"tournament:{d.get('slug') or d.get('key') or d.get('name')}"
    if t == "bundle":
        return f"bundle:{d.get('key') or d.get('theme') or d.get('title')}"
    return f"{t}:{d.get('id') or d.get('name')}"


def load_pulls(out_dir):
    path = os.path.join(out_dir, "pulls.jsonl")
    if not os.path.exists(path):
        return []
    pulls = []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if line:
                pulls.append(json.loads(line))
    return pulls


def surface_slates(pulls, surface):
    """[(captured_at, commit, [card_key,...], raw_payload)] for one surface."""
    out = []
    for p in pulls:
        s = (p.get("surfaces") or {}).get(surface) or {}
        raw = s.get("raw_path")
        if not raw or not os.path.exists(raw):
            continue
        try:
            with open(raw) as fh:
                body = json.load(fh)
        except Exception:
            continue
        items = body.get("items")
        if not isinstance(items, list):
            continue
        out.append((p.get("captured_at"), p.get("deployed_commit"),
                    [card_key(i) for i in items], body))
    return out


def churn_report(slates, label):
    print(f"\n--- CHURN: {label} ({len(slates)} pulls) ---")
    if len(slates) < 2:
        print("  UNKNOWN — needs >=2 pulls on this surface. A repeat rate over one")
        print("  observation is undefined, not zero.")
        return
    first = set(slates[0][2])
    seen_counts = Counter()
    for _, _, keys, _ in slates:
        seen_counts.update(set(keys))

    print(f"  window: {slates[0][0]} -> {slates[-1][0]}")
    commits = {c for _, c, _, _ in slates}
    if len(commits) > 1:
        print(f"  !! SPANS {len(commits)} DEPLOYED COMMITS {sorted(commits)} —")
        print("     these pulls are not one population; read the split, not the mean.")

    # consecutive-pull overlap
    for i in range(1, len(slates)):
        a, b = set(slates[i - 1][2]), set(slates[i][2])
        held = len(a & b)
        print(f"  pull {i} -> {i+1} ({slates[i-1][0][11:19]} -> {slates[i][0][11:19]}): "
              f"{held}/{len(b)} held over, {len(b - a)} new")

    # first vs last: the "opened it twice" question
    last = set(slates[-1][2])
    print(f"  FIRST vs LAST: {len(first & last)}/{len(last)} of the final slate was "
          f"already on the first slate")

    # cards present in every pull = the furniture
    always = [k for k, n in seen_counts.items() if n == len(slates)]
    print(f"  present in ALL {len(slates)} pulls: {len(always)} cards "
          f"({100*len(always)//max(1,len(last))}% of a 20-card page)")
    distinct = len(seen_counts)
    print(f"  distinct cards across the whole window: {distinct} "
          f"(a perfectly static feed would show {len(last)})")
    return {"always": always, "distinct": distinct, "pulls": len(slates)}


def freshness_report(body, label):
    """How old/again-able is the CONTENT, independent of whether the slate moved."""
    print(f"\n--- CONTENT FRESHNESS: {label} ---")
    items = body.get("items") or []
    now = datetime.now(timezone.utc)
    horizons, no_date, movers, flat = [], 0, 0, 0
    for i in items:
        d = i.get("data") or {}
        rd = d.get("resolution_date")
        if rd:
            try:
                dt = datetime.fromisoformat(rd.replace("Z", "+00:00"))
                horizons.append((dt - now).days)
            except Exception:
                no_date += 1
        else:
            no_date += 1
        # biggest 24h move across the card's rendered outcomes
        outs = (d.get("discover_card") or {}).get("distribution_outcomes") or \
               d.get("top_outcomes") or []
        mv = 0.0
        for o in outs:
            try:
                mv = max(mv, abs(float(o.get("movement") or 0)))
            except (TypeError, ValueError):
                pass
        if mv >= 0.01:
            movers += 1
        else:
            flat += 1
    if horizons:
        horizons.sort()
        mid = horizons[len(horizons) // 2]
        print(f"  resolution horizon (days out): min={horizons[0]} median={mid} "
              f"max={horizons[-1]}  n={len(horizons)}")
        print(f"    resolving within 7 days:  {sum(1 for h in horizons if h <= 7)}")
        print(f"    resolving beyond 90 days: {sum(1 for h in horizons if h > 90)}")
    print(f"  cards with NO resolution_date: {no_date}/{len(items)}")
    print(f"  cards whose rendered numbers moved >=1pt in 24h: {movers}/{len(items)} "
          f"(flat: {flat})")


def mix_report(body, label):
    print(f"\n--- MIX: {label} ---")
    items = body.get("items") or []
    print("  types:      ", dict(Counter(i.get("type") for i in items)))
    cats = Counter((i.get("data") or {}).get("llm_sport_category") or "(none)"
                   for i in items)
    print("  categories: ", dict(cats))


def interestingness_report(body, label):
    """Item 2 — the per-card component view, straight off the served payload."""
    print(f"\n--- INTERESTINGNESS COMPONENTS: {label} ---")
    items = body.get("items") or []
    rows, missing = [], 0
    for n, i in enumerate(items, 1):
        d = i.get("data") or {}
        if "interestingness_score" not in d:
            missing += 1
            rows.append((n, i.get("type"), i.get("score"), None, [],
                         (d.get("name") or "")[:44]))
            continue
        rows.append((n, i.get("type"), i.get("score"),
                     d.get("interestingness_score"),
                     d.get("interestingness_reasons") or [],
                     (d.get("name") or "")[:44]))
    print(f"  cards carrying an interestingness_score: {len(items)-missing}/{len(items)}")
    print(f"  cards the blend CANNOT see (no score on the card): {missing}/{len(items)}")
    print()
    print("  rank type      display  interest  reasons / name")
    for n, t, s, i_s, reasons, name in rows:
        print("  %4d %-9s %-8s %-9s %s | %s"
              % (n, t, s, "-" if i_s is None else round(i_s, 1),
                 ",".join(reasons)[:38], name))
    scored = [r[3] for r in rows if r[3] is not None]
    if scored:
        print(f"\n  interestingness spread over the served page: "
              f"min={min(scored):.1f} max={max(scored):.1f} "
              f"range={max(scored)-min(scored):.1f}")
        print("  (a narrow range means the signal cannot re-order the page even at")
        print("   a high blend weight — the multiplier has nothing to multiply.)")
    allr = Counter(r for row in rows for r in row[4])
    if allr:
        print(f"\n  reason frequency across the page: {dict(allr)}")


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "/tmp/ux-p124-captures"
    pulls = load_pulls(out_dir)
    print("=" * 72)
    print(f"UX-P124 DISCOVER CAPTURE ANALYSIS — {out_dir}")
    print(f"pulls on record: {len(pulls)}")
    print("=" * 72)
    if not pulls:
        print("NO CAPTURES. Run capture-top20.sh first.")
        return 1

    for surface in ("anon", "session", "debug"):
        slates = surface_slates(pulls, surface)
        if not slates:
            print(f"\n--- {surface}: no parseable payloads ---")
            continue
        churn_report(slates, surface)

    anon = surface_slates(pulls, "anon")
    if anon:
        latest = anon[-1][3]
        mix_report(latest, "anon, latest pull")
        freshness_report(latest, "anon, latest pull")
        interestingness_report(latest, "anon, latest pull")

    # The returning-user question: same minute, two identities.
    sess = surface_slates(pulls, "session")
    if anon and sess:
        a, s = set(anon[-1][2]), set(sess[-1][2])
        print("\n--- RETURNING USER vs FIRST-TIME VISITOR (latest pull, same minute) ---")
        print(f"  anon slate:    {len(a)} cards")
        print(f"  session slate: {len(s)} cards")
        print(f"  shared:        {len(a & s)}  ({100*len(a & s)//max(1,len(s))}%)")
        print(f"  session-only:  {len(s - a)}")
        if a == s:
            print("  IDENTICAL — carrying a session id changed nothing on this pull.")
            print("  Impression suppression is driven by DiscoverInteraction rows the")
            print("  CLIENT writes; a bare GET never writes one, so this measures the")
            print("  personalization path only, not the seen-suppression path.")

    debug = surface_slates(pulls, "debug")
    if debug:
        body = debug[-1][3]
        ds = body.get("debug_summary") or {}
        print("\n--- CAP / DEMOTION / QUALITY STATE (debug, latest pull) ---")
        for k in ("boring_count", "ladder_count", "duplicate_family_count",
                  "explanation_ok_count", "category_spread", "max_category_count",
                  "snippet_issue_count"):
            if k in ds:
                print(f"  {k:26s} {ds[k]}")
        if ds.get("strict_targets"):
            print("  strict_targets:")
            for k, v in ds["strict_targets"].items():
                print(f"    {'PASS' if v else 'FAIL'}  {k}")
        mg = body.get("missing_ground_truth_summary") or {}
        if mg:
            print(f"\n  GROUND-TRUTH MISSES: {mg.get('total')} items a curator "
                  f"expected that the page did not show")
            for k, v in (mg.get("bucket_counts") or {}).items():
                print(f"    {v:4d}  {k}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
