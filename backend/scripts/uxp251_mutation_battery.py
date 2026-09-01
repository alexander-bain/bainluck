#!/usr/bin/env python3
"""UX-P251 mutation battery — does the guard hold the ship up?

Each mutant reverses one thing the ship claims. The battery proves the edit
APPLIED (exact-count replace, or it aborts), runs the guard, restores from a
sha256-checked copy, and re-runs the baseline. Run from an rsync copy.

Re-aimed after the tier census forced the redesign: the ship is no longer "fold
the two clocks", it is "a SEPARATE blocker with a SEPARATE number", so the
mutants that mattered changed with it.
"""
import hashlib, pathlib, subprocess, sys

FEED = pathlib.Path("app/routes/feed.py")
STALE = pathlib.Path("app/utils/market_staleness.py")
SUITES = [
    "tests/test_feed_dead_market_clock_uxp251.py",
    "tests/test_feed_stale_suppression.py",
    "tests/test_sports_page_categories.py",
]

MUTANTS = [
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
    ("E", STALE,
     "        stamp = _outcome_movement_stamp(outcome)\n        if stamp is not None and (newest is None or stamp > newest):\n            newest = stamp",
     "        stamp = _outcome_movement_stamp(outcome)\n        if stamp is not None and newest is None:\n            newest = stamp",
     "KILL", "first stamp wins, not newest — a fresh tail outcome stops counting", 1),
    ("F", STALE,
     "        raw = outcome.get(column) if is_mapping else getattr(outcome, column, None)",
     "        raw = outcome.get(column) if is_mapping else None",
     "KILL", "the ORM row shape stops being read — every market reports 'no evidence'", 1),
    ("G", FEED,
     "    newest_outcome_at: datetime | None,\n    stale_no_movement_days: float = 2,",
     "    newest_outcome_at: datetime | None = None,\n    stale_no_movement_days: float = 2,",
     "KILL", "the silent-fallback hole: a caller that forgets the price clock is not caught", 1),
    ("H", FEED,
     "        if _prices_have_stopped(_newest_outcome_stamp(market.outcomes), now):\n            continue",
     "",
     "KILL", "the Sports tab loses the blocker — the half-swept fix", 1),
    ("I", FEED, "            FuturesOutcome.last_updated,\n        ),", "        ),",
     "KILL", "load_only drops the column: lazy-loads per outcome, crashes the async route", 2),
    ("J", FEED,
     "                newest_outcome_at=_newest_outcome_stamp(market.outcomes),\n                stale_no_movement_days=_gate_no_movement_days,",
     "                newest_outcome_at=market.updated_at,\n                stale_no_movement_days=_gate_no_movement_days,",
     "KILL", "the LIVE path passes the parent stamp as if it were the prices'", 1),
    ("K", STALE,
     "    if not isinstance(value, datetime):\n        return None",
     "    if value is None:\n        return None",
     "KILL", "a non-datetime treated as a stamp — MagicMock comparison raises inside the swallow", 1),
    ("L", STALE,
     "    if value.tzinfo is None:\n        return value.replace(tzinfo=timezone.utc)\n    return value",
     "    return value  # naive stays naive",
     "KILL", "naive stamps stop being read as UTC — TypeError at request time, not in any test", 1),
    ("M", FEED,
     "    updated_at = _utc(market.updated_at)\n    if updated_at:",
     "    updated_at = None\n    if updated_at:",
     "KILL", "the parent-row rules are disabled — this ship must be ADDITIVE, not a replacement", 1),
    # ── CERT-688: the version-two revert, in its three shapes ────────────────
    ("N", STALE,
     '_MOVEMENT_STAMP_COLUMNS = ("price_changed_at", "last_updated")',
     '_MOVEMENT_STAMP_COLUMNS = ("last_updated",)',
     "KILL", "version two exactly: the poll touch-stamp is the only clock, so an "
             "actively polled market frozen 59 days still reaches the feed", 1),
    ("O", STALE,
     '_MOVEMENT_STAMP_COLUMNS = ("price_changed_at", "last_updated")',
     '_MOVEMENT_STAMP_COLUMNS = ("last_updated", "price_changed_at")',
     "KILL", "order reversed — the touch-stamp always wins because it is never "
             "NULL, so the movement column becomes unreachable dead code", 1),
    ("P", STALE,
     '_MOVEMENT_STAMP_COLUMNS = ("price_changed_at", "last_updated")',
     '_MOVEMENT_STAMP_COLUMNS = ("price_changed_at",)',
     "KILL", "the fallback is dropped — 97% of rows are NULL on the new column, "
             "so the named specimen reports 'no evidence' and comes back", 1),
    ("Q", FEED,
     "            FuturesOutcome.price_changed_at,\n            FuturesOutcome.last_updated,",
     "            FuturesOutcome.last_updated,",
     "KILL", "load_only drops the movement column: lazy-loads per outcome on "
             "exactly the freshly-repriced markets, crashes the async route", 2),
]


def run_suites():
    p = subprocess.run([sys.executable, "-m", "pytest", *SUITES, "-q", "--no-header", "-x", "--tb=no"],
                       capture_output=True, text=True)
    tail = [l for l in p.stdout.splitlines() if "passed" in l or "failed" in l or "error" in l.lower()]
    return p.returncode, (tail[-1] if tail else "(no summary)")


def main():
    originals = {p: p.read_text() for p in (FEED, STALE)}
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
