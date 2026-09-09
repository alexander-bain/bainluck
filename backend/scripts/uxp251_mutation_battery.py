#!/usr/bin/env python3
"""UX-P251 mutation battery — does the guard hold the ship up?

Each mutant reverses one thing the ship claims. The battery proves the edit
APPLIED (exact-count replace, or it aborts), runs the guard, restores from a
sha256-checked copy, and re-runs the baseline. Run from an rsync copy.

Re-aimed twice. First after the tier census forced the redesign: the ship is no
longer "fold the two clocks", it is "a SEPARATE blocker with a SEPARATE number".
Then again for version four, which takes the stamp from `price_polled_at` — the
carrier CERT-949 already built — instead of carrying two per-outcome columns of
its own. The CERT-688 coalesce mutants went with that code; mutants K-N replace
them, and they aim at the failure this version can actually have: picking the
wrong CARRIER, which yields `None`, and `None` does not block. Every one of
those breakages is silent.
"""
import hashlib, pathlib, subprocess, sys

FEED = pathlib.Path("app/routes/feed.py")
STALE = pathlib.Path("app/utils/market_staleness.py")
SNAP = pathlib.Path("app/utils/futures_market_snapshot.py")
SUITES = [
    "tests/test_feed_dead_market_clock_uxp251.py",
    "tests/test_feed_stale_suppression.py",
    "tests/test_futures_market_snapshot_lat_p174.py",
    "tests/test_my_stuff_price_freshness_cert949.py",
    "tests/test_sports_page_categories.py",
]

MUTANTS = [
    # ── the ship itself ──────────────────────────────────────────────────────
    ("A", FEED,
     '    if _prices_have_stopped(newest_outcome_at, now):\n        blockers.append("prices_stopped")',
     "",
     "KILL", "the whole ship: the blocker is gone from /api/feed", 1),
    ("B", STALE, "PRICES_STOPPED_DAYS = 14", "PRICES_STOPPED_DAYS = 2",
     "KILL", "the two clocks share a constant again — this is the tier-3 wipeout", 1),
    ("C", STALE, "PRICES_STOPPED_DAYS = 14", "PRICES_STOPPED_DAYS = 120",
     "KILL", "loosened past the dead shelf — the bridesmaids card comes back", 1),
    ("D", STALE,
     "    stamp = _as_utc(newest_outcome_at)\n    if stamp is None:\n        return False",
     "    stamp = _as_utc(newest_outcome_at)\n    if stamp is None:\n        return True",
     "KILL", "'no stamp' read as death — takes an unstamped source dark wholesale", 1),
    ("E", FEED,
     "    newest_outcome_at: datetime | None,\n    stale_no_movement_days: float = 2,",
     "    newest_outcome_at: datetime | None = None,\n    stale_no_movement_days: float = 2,",
     "KILL", "the silent-fallback hole: a caller that forgets the price clock is not caught", 1),
    ("F", FEED,
     "        if _prices_have_stopped(_price_poll_stamp(market), now):\n            continue",
     "",
     "KILL", "the Sports tab loses the blocker — the half-swept fix", 1),
    ("G", FEED,
     "                newest_outcome_at=_price_poll_stamp(market),\n                stale_no_movement_days=_gate_no_movement_days,",
     "                newest_outcome_at=market.updated_at,\n                stale_no_movement_days=_gate_no_movement_days,",
     "KILL", "the LIVE path passes the parent stamp as if it were the prices'", 1),
    ("H", FEED,
     "    updated_at = _utc(market.updated_at)\n    if updated_at:",
     "    updated_at = None\n    if updated_at:",
     "KILL", "the parent-row rules are disabled — this ship must be ADDITIVE, not a replacement", 1),
    ("I", STALE,
     "    if not isinstance(value, datetime):\n        return None",
     "    if value is None:\n        return None",
     "KILL", "a non-datetime treated as a stamp — MagicMock comparison raises inside the swallow", 1),
    ("J", STALE,
     "    if value.tzinfo is None:\n        return value.replace(tzinfo=timezone.utc)\n    return value",
     "    return value  # naive stays naive",
     "KILL", "naive stamps stop being read as UTC — TypeError at request time, not in any test", 1),
    # ── VERSION FOUR: the two carrier shapes of `price_poll_stamp` ───────────
    # These replace the CERT-688 `_MOVEMENT_STAMP_COLUMNS` mutants. That coalesce
    # is gone: the stamp now comes from `price_polled_at`, the value CERT-949
    # already folds per market, so the reachable ways to break it are the ways a
    # caller can pick the WRONG CARRIER — and every one of them fails SILENTLY,
    # because a mis-read carrier yields `None` and `None` does not block.
    ("K", SNAP,
     '    state = market.__dict__\n    if "price_polled_at" in state:\n        return state["price_polled_at"]\n    return _price_polled_at(state.get("outcomes") or [])',
     '    state = market.__dict__\n    folded = _price_polled_at(state.get("outcomes") or [])\n    if folded is not None:\n        return folded\n    return state.get("price_polled_at")',
     "KILL", "carrier order inverted — a REBUILT market would re-derive from outcomes "
             "that the wire format does not carry, so Discover's whole futures pool "
             "reports 'no evidence' and the gate quietly stops existing there", 1),
    ("L", SNAP,
     '    return _price_polled_at(state.get("outcomes") or [])',
     "    return None",
     "KILL", "the ORM fallback is dropped — sports mode has no derived column, so "
             "the Sports tab silently loses the blocker again", 1),
    ("M", SNAP,
     '    if "price_polled_at" in state:\n        return state["price_polled_at"]',
     '    if getattr(market, "price_polled_at", None) is not None:\n        return state["price_polled_at"]',
     "KILL", "`getattr` on a deferred column lazy-loads and raises MissingGreenlet "
             "inside the per-item serializer; a folded None also stops being honoured", 1),
    ("N", SNAP,
     '    return _price_polled_at(state.get("outcomes") or [])',
     '    return _price_polled_at((state.get("outcomes") or [])[:10])',
     "KILL", "a top-ten proxy — measured: 207 markets carry a tail outcome more than "
             "a day fresher than anything in their top ten, and all 207 read as dead", 1),
]


def run_suites():
    p = subprocess.run([sys.executable, "-m", "pytest", *SUITES, "-q", "--no-header", "-x", "--tb=no"],
                       capture_output=True, text=True)
    tail = [l for l in p.stdout.splitlines() if "passed" in l or "failed" in l or "error" in l.lower()]
    return p.returncode, (tail[-1] if tail else "(no summary)")


def main():
    originals = {p: p.read_text() for p in (FEED, STALE, SNAP)}
    shas = {p: hashlib.sha256(t.encode()).hexdigest() for p, t in originals.items()}
    code, summary = run_suites()
    print(f"BASELINE: exit {code} — {summary}")
    if code != 0:
        print("Baseline is red. A battery on a red baseline measures nothing.")
        return 2
    results = []
    for mid, path, old, new, prediction, why, sites in MUTANTS:
        text = path.read_text()
        n = text.count(old)
        if n != sites:
            print(f"{mid}: APPLY FAILED — {n} matches, expected {sites}. ABORTING.")
            for p, t in originals.items():
                p.write_text(t)
            return 3
        path.write_text(text.replace(old, new))
        assert path.read_text() != originals[path], f"{mid}: file unchanged after write"
        code, summary = run_suites()
        verdict = "KILL" if code != 0 else "SURVIVE"
        flag = "" if verdict == prediction else "   <-- UNEXPECTED"
        print(f"{mid}: predicted {prediction:8s} got {verdict:8s} ({summary}){flag}\n     {why}")
        results.append((mid, prediction, verdict))
        path.write_text(originals[path])
        assert hashlib.sha256(path.read_text().encode()).hexdigest() == shas[path], f"{mid}: restore mismatch"
    code, summary = run_suites()
    print(f"\nRESTORED BASELINE: exit {code} — {summary}")
    killed = sum(1 for _, _, v in results if v == "KILL")
    unexpected = [m for m, p, v in results if p != v]
    print(f"{killed}/{len(results)} killed; {len(unexpected)} unexpected: {unexpected or 'none'}")
    return 0 if code == 0 and not unexpected else 1


if __name__ == "__main__":
    raise SystemExit(main())
