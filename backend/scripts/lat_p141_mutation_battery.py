#!/usr/bin/env python3
"""LAT-P141 mutation battery — does the guard suite hold the page base down?

THE DEFECT WAS A CACHE KEY THAT ASKED A QUESTION THE BUILD DOES NOT ANSWER.
``GET /api/feed`` builds the whole ranked list and slices
``feed_items[offset : offset + limit]``; the response cache nevertheless keyed on
``offset``, so every page after the first was a cold rebuild of a list the server
had already produced (production 2026-08-30: offset=0 46 ms, offset=50 1,329 ms).

A fix that stores a list and slices it has TWO failure directions, and only one
of them is slow:

* **It stops helping** — the key fragments, the base expires early, the warmer
  never fills it. Costs a second. Recoverable.
* **It serves the wrong page** — the key stops distinguishing two builds, the
  slice comes off the wrong offset, ``has_more`` ends the scroll early, a
  personalized reader gets the anonymous list. Costs correctness, is invisible
  to every latency instrument, and is what most of the mutants below are for.

The key mutants in particular are the point of this file. Dropping ``limit``
from the base key makes native and web share one list; dropping the ctx guard
hands identified users the anonymous feed. Neither changes a millisecond and
neither makes a test about speed fail — so if the suite does not kill them, the
suite is measuring the wrong thing.

Each mutant asserts its edit CHANGED the file before running anything (a
mutation that fails to apply reports green and proves nothing), and every target
is restored from a byte-for-byte backup in a ``finally`` with a SHA-256 compare.

Backups are namespaced by the WORKTREE, not just the filename: /tmp is shared
across worktrees and a battery here must never restore a sibling's file.

Run from ``backend/``:  ``python3 scripts/lat_p141_mutation_battery.py``
"""

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROUTE = Path("app/routes/feed.py")
CACHE = Path("app/utils/feed_cache.py")
TARGETS = [ROUTE, CACHE]
SUITES = [
    "tests/test_feed_page_base_p141.py",
    "tests/integration/test_route_feed_page_base_p141.py",
    # The tiers this one sits between. A mutant that satisfies the new file
    # while breaking LAT-P001's warmer contract or LAT-P089's share is not
    # killed, it is traded.
    "tests/integration/test_route_feed_prewarm.py",
    "tests/test_feed_inert_principal_share_p089.py",
]

# (name, target, description, old, new)
MUTANTS = [
    # -- the key: stop distinguishing two builds ----------------------------
    (
        "M-KEY-DROPS-LIMIT",
        CACHE,
        "native (50) and web (20) share one base — two different lists, one key",
        'f"pagebase:{sport or \'all\'}:{limit}:"',
        'f"pagebase:{sport or \'all\'}:"',
    ),
    # The base key's second and third f-string lines are byte-identical to
    # `feed_response_cache_key`'s, so every anchor below carries the
    # `pagebase:` line with it. The battery refuses a non-unique anchor rather
    # than editing whichever copy `str.replace` reaches first — an ambiguous
    # mutation proves nothing about the file it did not touch.
    (
        "M-KEY-DROPS-MODE",
        CACHE,
        "Discover and Sports share a base — the Sports tab serves Discover's list",
        "        f\"pagebase:{sport or 'all'}:{limit}:\"\n"
        "        f\"{include_events}:{include_futures}:{tags or ''}:{event_pct or ''}:\"\n"
        "        f\"{my_teams_only}:{mode or 'discover'}\"",
        "        f\"pagebase:{sport or 'all'}:{limit}:\"\n"
        "        f\"{include_events}:{include_futures}:{tags or ''}:{event_pct or ''}:\"\n"
        '        f"{my_teams_only}"',
    ),
    (
        "M-KEY-DROPS-EVENT-PCT",
        CACHE,
        "the Discover event ratio stops keying — a different demotion, same key",
        "        f\"pagebase:{sport or 'all'}:{limit}:\"\n"
        "        f\"{include_events}:{include_futures}:{tags or ''}:{event_pct or ''}:\"",
        "        f\"pagebase:{sport or 'all'}:{limit}:\"\n"
        "        f\"{include_events}:{include_futures}:{tags or ''}:\"",
    ),
    (
        "M-KEY-DROPS-MY-TEAMS",
        CACHE,
        "a followed-teams list and an everyone list collide",
        "        f\"pagebase:{sport or 'all'}:{limit}:\"\n"
        "        f\"{include_events}:{include_futures}:{tags or ''}:{event_pct or ''}:\"\n"
        "        f\"{my_teams_only}:{mode or 'discover'}\"",
        "        f\"pagebase:{sport or 'all'}:{limit}:\"\n"
        "        f\"{include_events}:{include_futures}:{tags or ''}:{event_pct or ''}:\"\n"
        "        f\"{mode or 'discover'}\"",
    ),
    (
        "M-KEY-DROPS-SPORT",
        CACHE,
        "a sport-filtered feed and the whole feed share a list",
        "        f\"pagebase:{sport or 'all'}:{limit}:\"",
        '        f"pagebase:{limit}:"',
    ),
    (
        "M-KEY-DROPS-INCLUDE-FUTURES",
        CACHE,
        "the events-only backfill shape collides with the full feed",
        "        f\"pagebase:{sport or 'all'}:{limit}:\"\n"
        "        f\"{include_events}:{include_futures}:{tags or ''}:{event_pct or ''}:\"",
        "        f\"pagebase:{sport or 'all'}:{limit}:\"\n"
        "        f\"{include_events}:{tags or ''}:{event_pct or ''}:\"",
    ),
    (
        "M-KEY-CONSTANT",
        CACHE,
        "one base for every shape in the product",
        "    return f\"{FEED_PAGE_BASE_CACHE_PREFIX}:{hashlib.md5(parts.encode()).hexdigest()}\"",
        '    return f"{FEED_PAGE_BASE_CACHE_PREFIX}:one"',
    ),
    (
        "M-KEY-ESCAPES-FEED-NAMESPACE",
        CACHE,
        "a base an invalidation cannot reach — it re-serves the pre-invalidation list",
        'FEED_PAGE_BASE_CACHE_PREFIX = f"{FEED_RESPONSE_CACHE_PREFIX}:pagebase"',
        'FEED_PAGE_BASE_CACHE_PREFIX = "feed_pagebase"',
    ),
    # -- the renderer: serve the wrong window --------------------------------
    (
        "M-RENDER-SLICE-FROM-ZERO",
        CACHE,
        "THE USER-VISIBLE BUG — page 2 shows page 1 again, forever",
        '    out["items"] = items[offset : offset + limit]',
        '    out["items"] = items[0 : limit]',
    ),
    (
        "M-RENDER-SLICE-BY-PAGE-INDEX",
        CACHE,
        "treat offset as a page number — the classic off-by-a-multiple",
        '    out["items"] = items[offset : offset + limit]',
        '    out["items"] = items[offset * limit : offset * limit + limit]',
    ),
    (
        "M-RENDER-TOTAL-IS-THE-PAGE",
        CACHE,
        "report the window as the whole feed — the scroll ends after one page",
        '    out["total"] = total\n    out["limit"] = limit',
        '    out["total"] = len(out["items"])\n    out["limit"] = limit',
    ),
    (
        "M-RENDER-HAS-MORE-OFF-THE-PAGE",
        CACHE,
        "a plausible rewrite that is wrong on a full final page",
        '    out["has_more"] = (offset + limit) < total',
        '    out["has_more"] = len(out["items"]) == limit',
    ),
    (
        "M-RENDER-HAS-MORE-OFF-BY-ONE",
        CACHE,
        "<= instead of < — one empty page at the end of every scroll",
        '    out["has_more"] = (offset + limit) < total',
        '    out["has_more"] = (offset + limit) <= total',
    ),
    # -- the renderer: stop failing closed -----------------------------------
    (
        "M-RENDER-NO-TOTAL-INVARIANT",
        CACHE,
        "accept a truncated base — has_more computed off a number the list cannot support",
        "    if not isinstance(total, int) or total != len(items):\n        return None",
        "    if not isinstance(total, int):\n        total = len(items)",
    ),
    (
        "M-RENDER-NO-LIST-CHECK",
        CACHE,
        "a half-written blob is sliced instead of refused",
        "    items = base.get(\"items\")\n    if not isinstance(items, list):\n        return None",
        "    items = base.get(\"items\") or []",
    ),
    (
        "M-RENDER-LEAKS-BUILT-AT",
        CACHE,
        "the base's internal provenance field ships in the public response",
        "    out.pop(FEED_PAGE_BASE_BUILT_AT_FIELD, None)",
        "    pass",
    ),
    (
        "M-RENDER-KEEPS-STORED-CACHE-META",
        CACHE,
        "serve the STORING serve's cache metadata as this serve's",
        '    out.pop("cache", None)\n    out.pop(FEED_PAGE_BASE_BUILT_AT_FIELD, None)',
        "    out.pop(FEED_PAGE_BASE_BUILT_AT_FIELD, None)",
    ),
    (
        "M-BUILT-AT-MINTS-A-CLOCK",
        CACHE,
        "CERT-409's exact defect — every hop restarts the live ceiling's clock",
        "    built_at = base.get(FEED_PAGE_BASE_BUILT_AT_FIELD)\n    return float(built_at) if isinstance(built_at, (int, float)) else None",
        "    import time as _t\n    built_at = base.get(FEED_PAGE_BASE_BUILT_AT_FIELD)\n    return float(built_at) if isinstance(built_at, (int, float)) else _t.time()",
    ),
    (
        "M-KILL-SWITCH-INVERTED",
        CACHE,
        "a typo'd config value silently disables the fix",
        "    raw = os.environ.get(FEED_PAGE_BASE_ENV)\n    if raw is None:\n        return True\n    return str(raw).strip().lower() not in _PAGE_BASE_OFF_VALUES",
        "    raw = os.environ.get(FEED_PAGE_BASE_ENV)\n    if raw is None:\n        return True\n    return str(raw).strip().lower() in {'1', 'true', 'yes', 'on'}",
    ),
    # -- the route: the base never reaches the render ------------------------
    (
        "M-ROUTE-SCRUB-PAGE-ONLY",
        ROUTE,
        "revert the scrub to `paginated` — page 2 ships _rank_score to every reader",
        "        for item in feed_items:\n            # #1885: PROMOTE the story key",
        "        for item in paginated:\n            # #1885: PROMOTE the story key",
    ),
    (
        "M-ROUTE-NO-CTX-GUARD",
        ROUTE,
        "THE WRONG-PERSON'S-FEED DOOR — identified readers get the anonymous list",
        "            and not my_teams_only\n            and ctx == PersonalizationContext()\n        ):",
        "            and not my_teams_only\n        ):",
    ),
    (
        "M-ROUTE-NO-MY-TEAMS-GUARD",
        ROUTE,
        "a followed-teams page becomes reachable from a shared list",
        "            and not my_teams_only\n            and ctx == PersonalizationContext()",
        "            and ctx == PersonalizationContext()",
    ),
    (
        "M-ROUTE-IGNORES-KILL-SWITCH",
        ROUTE,
        "the operator lever stops working — the only remedy is a deploy",
        "            and feed_page_base_enabled()\n            and not my_teams_only",
        "            and not my_teams_only",
    ),
    (
        "M-ROUTE-WARMER-READS-THE-BASE",
        ROUTE,
        "LAT-P001 AGAIN — the warmer is served from the tier it exists to fill",
        "            _base_raw, _base_status = (\n                (None, None)\n                if _prewarm_rebuild\n                else await _read_shared_feed_cache(_shared_redis, _page_base_key)\n            )",
        "            _base_raw, _base_status = await _read_shared_feed_cache(\n                _shared_redis, _page_base_key\n            )",
    ),
    (
        "M-ROUTE-BUILDERS-TTL",
        ROUTE,
        "stamp the reader's 5s lifetime on the anonymous list — the fix measures as noise",
        "                    _base_fresh_ttl, _base_stale_ttl = feed_response_cache_ttls(\n                        my_teams_only=False,\n                        identified=False,",
        "                    _base_fresh_ttl, _base_stale_ttl = feed_response_cache_ttls(\n                        my_teams_only=False,\n                        identified=bool(feed_user or feed_session_id),",
    ),
    (
        "M-ROUTE-BASE-KEEPS-PAGE-FIELDS",
        ROUTE,
        "store one serve's window on the list — a later reader takes it for the base's own",
        '                    for _per_serve in ("cache", "limit", "offset", "has_more"):',
        '                    for _per_serve in ("cache",):',
    ),
    (
        "M-ROUTE-BASE-STORES-THE-PAGE",
        ROUTE,
        "publish the sliced page as the base — page 2 of a 50-item 'whole feed'",
        '                    _page_base_body["items"] = feed_items',
        '                    _page_base_body["items"] = paginated',
    ),
    (
        "M-ROUTE-NO-BUILT-AT",
        ROUTE,
        "drop the provenance — remember_last_good falls back to read time",
        "                    _page_base_body[FEED_PAGE_BASE_BUILT_AT_FIELD] = _built_at",
        "                    pass",
    ),
    (
        "M-ROUTE-SHAPE-RETYPED-DROPS-A-FIELD",
        ROUTE,
        "re-type the shape and forget one — page 2 comes off a differently-built list",
        '                k: v for k, v in _cache_shape.items() if k != "offset"',
        '                k: v for k, v in _cache_shape.items()\n                if k not in ("offset", "mode")',
    ),
]


def run_suites() -> int:
    return subprocess.run(
        [sys.executable, "-m", "pytest", *SUITES, "-q", "--no-header"],
        capture_output=True,
        text=True,
    ).returncode


def main() -> int:
    for target in TARGETS:
        if not target.is_file():
            print(f"FATAL: run from backend/ — {target} not found")
            return 2

    # /tmp is shared across worktrees; namespace by cwd so a battery here can
    # never restore a sibling worktree's copy of the same filename.
    slug = hashlib.sha256(os.getcwd().encode()).hexdigest()[:12]

    backups, originals, shas = {}, {}, {}
    for target in TARGETS:
        backup = Path(f"/tmp/lat_p141_{slug}_{target.name}.backup")
        shutil.copy2(target, backup)
        backups[target] = backup
        originals[target] = backup.read_text()
        shas[target] = hashlib.sha256(originals[target].encode()).hexdigest()

    print(f"denominator: {len(MUTANTS)} mutants queued")
    print(f"targets:     {' '.join(str(t) for t in TARGETS)}")
    print(f"suites:      {' '.join(SUITES)}")
    baseline = run_suites()
    print(
        f"baseline:    suites on the unmutated tree -> exit {baseline} "
        f"({'GREEN' if baseline == 0 else 'RED'})"
    )
    if baseline != 0:
        print("FATAL: baseline is not green; every 'killed' would be meaningless")
        for target, backup in backups.items():
            shutil.copy2(backup, target)
        return 2

    killed, survived, harness = [], [], []
    try:
        for name, target, desc, old, new in MUTANTS:
            original = originals[target]
            if old not in original:
                harness.append(name)
                print(f"{name:<34} HARNESS-FAIL  anchor not found — never applied")
                continue
            if original.count(old) != 1:
                harness.append(name)
                print(
                    f"{name:<34} HARNESS-FAIL  anchor is not unique "
                    f"({original.count(old)}x) — the edit is ambiguous"
                )
                continue
            mutated = original.replace(old, new, 1)
            if mutated == original:
                harness.append(name)
                print(f"{name:<34} HARNESS-FAIL  replace was a no-op")
                continue
            target.write_text(mutated)
            assert target.read_text() != original, "mutation did not reach disk"
            rc = run_suites()
            target.write_text(original)
            if rc != 0:
                killed.append(name)
                print(f"{name:<34} killed    {desc}")
            else:
                survived.append(name)
                print(f"{name:<34} SURVIVED  {desc}")
    finally:
        for target, backup in backups.items():
            shutil.copy2(backup, target)
            restored = hashlib.sha256(target.read_text().encode()).hexdigest()
            assert restored == shas[target], f"restore failed for {target} — tree is dirty"
            print(f"restore:     {target} SHA-256 identical ({restored[:16]}…)")

    print(
        f"\n{len(killed)}/{len(MUTANTS)} killed, {len(survived)} survived, "
        f"{len(harness)} harness failures"
    )
    if harness:
        print("🔴 a harness failure is NOT a pass — the mutant never ran")
        return 2
    return 0 if len(killed) == len(MUTANTS) else 1


if __name__ == "__main__":
    sys.exit(main())
