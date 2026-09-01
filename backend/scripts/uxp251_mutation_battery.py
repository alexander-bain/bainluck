#!/usr/bin/env python3
"""UX-P251 mutation battery — does the guard actually hold the ship up?

Each mutant is a one-edit reversal of something the ship claims. The battery
proves it APPLIED (exact-count string replace, or it aborts), runs the guard,
restores from a sha256-checked copy, and re-runs the baseline at the end.

Run from `/tmp/uxp251-mut/backend` — an rsync copy, never the live worktree.
"""

import hashlib
import pathlib
import subprocess
import sys

FEED = pathlib.Path("app/routes/feed.py")
STALE = pathlib.Path("app/utils/market_staleness.py")
SUITES = [
    "tests/test_feed_dead_market_clock_uxp251.py",
    "tests/test_feed_stale_suppression.py",
]

# (id, file, old, new, prediction, why it matters, expected_sites)
MUTANTS = [
    (
        "A",
        FEED,
        "updated_at = _freshness_clock(market.updated_at, newest_outcome_at)",
        "updated_at = _utc(market.updated_at)",
        "KILL",
        "the whole ship: the oracle goes back to the parent-row clock",
        1,
    ),
    (
        "B",
        STALE,
        "    stamps = [s for s in (_as_utc(market_updated_at), _as_utc(newest_outcome_at)) if s]\n    return min(stamps) if stamps else None",
        "    stamps = [s for s in (_as_utc(market_updated_at), _as_utc(newest_outcome_at)) if s]\n    return max(stamps) if stamps else None",
        "KILL",
        "the NEWER stamp instead of the older — a poller touch vouches for prices again",
        1,
    ),
    (
        "C",
        STALE,
        "        stamp = _as_utc(raw)\n        if stamp is not None and (newest is None or stamp > newest):\n            newest = stamp",
        "        stamp = _as_utc(raw)\n        if stamp is not None and newest is None:\n            newest = stamp",
        "KILL",
        "first stamp wins instead of newest — a fresh tail outcome stops counting",
        1,
    ),
    (
        "D",
        STALE,
        '        else:\n            raw = getattr(outcome, "last_updated", None)',
        '        else:\n            raw = None',
        "KILL",
        "the ORM row shape stops being read at all — every market reports 'no evidence'",
        1,
    ),
    (
        "E",
        STALE,
        "def freshness_clock(\n    market_updated_at: datetime | None,\n    newest_outcome_at: datetime | None,\n) -> datetime | None:",
        "def freshness_clock(\n    market_updated_at: datetime | None,\n    newest_outcome_at: datetime | None = None,\n) -> datetime | None:",
        "SURVIVE",
        "a default on the PURE helper is harmless — the oracle's kwarg is the gate, "
        "and mutant F is what proves that",
        1,
    ),
    (
        "F",
        FEED,
        "    newest_outcome_at: datetime | None,\n    stale_no_movement_days: float = 2,",
        "    newest_outcome_at: datetime | None = None,\n    stale_no_movement_days: float = 2,",
        "KILL",
        "the silent-fallback hole: a caller that forgets the price clock keeps the old behaviour",
        1,
    ),
    (
        "G",
        FEED,
        "        _sports_clock = _freshness_clock(\n            market.updated_at, _newest_outcome_stamp(market.outcomes)\n        )",
        "        _sports_clock = _utc(market.updated_at)",
        "KILL",
        "the Sports tab reverts to its own copy of the wrong clock — the half-swept fix",
        1,
    ),
    (
        "H",
        FEED,
        "            FuturesOutcome.last_updated,\n        ),",
        "        ),",
        "KILL",
        "load_only drops the column: the async route lazy-loads per outcome and crashes",
        2,
    ),
    (
        "I",
        FEED,
        "                newest_outcome_at=_newest_outcome_stamp(market.outcomes),\n                stale_no_movement_days=_gate_no_movement_days,",
        "                newest_outcome_at=market.updated_at,\n                stale_no_movement_days=_gate_no_movement_days,",
        "KILL",
        "the LIVE path passes the parent stamp as if it were the prices'",
        1,
    ),
    (
        "J",
        STALE,
        "    if value.tzinfo is None:\n        return value.replace(tzinfo=timezone.utc)\n    return value",
        "    return value  # naive stays naive",
        "KILL",
        "naive stamps stop being read as UTC — a TypeError at request time, not in any test",
        1,
    ),
    (
        "K",
        STALE,
        "    if not isinstance(value, datetime):\n        return None",
        "    if value is None:\n        return None",
        "KILL",
        "a non-datetime is treated as a stamp — MagicMock comparison raises inside the swallow",
        1,
    ),
]


def run_suites() -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *SUITES, "-q", "--no-header", "-x", "--tb=no"],
        capture_output=True,
        text=True,
    )
    tail = [ln for ln in proc.stdout.splitlines() if "passed" in ln or "failed" in ln or "error" in ln.lower()]
    return proc.returncode, (tail[-1] if tail else "(no summary)")


def main() -> int:
    originals = {p: p.read_text() for p in (FEED, STALE)}
    shas = {p: hashlib.sha256(t.encode()).hexdigest() for p, t in originals.items()}

    code, summary = run_suites()
    print(f"BASELINE: exit {code} — {summary}")
    if code != 0:
        print("Baseline is red. A battery on a red baseline measures nothing.")
        return 2

    results = []
    for mid, path, old, new, prediction, why, sites in MUTANTS:
        text = originals[path].replace(*(old, new)) if False else path.read_text()
        n = text.count(old)
        if n != sites:
            print(f"{mid}: APPLY FAILED — {n} matches, expected {sites}. ABORTING.")
            for p, t in originals.items():
                p.write_text(t)
            return 3
        path.write_text(text.replace(old, new))
        # Prove it applied by reading the file back, not by trusting the write.
        assert new in path.read_text(), f"{mid}: mutant not present after write"

        code, summary = run_suites()
        verdict = "KILL" if code != 0 else "SURVIVE"
        flag = "" if verdict == prediction else "   <-- UNEXPECTED"
        print(f"{mid}: predicted {prediction:8s} got {verdict:8s} ({summary}){flag}")
        print(f"     {why}")
        results.append((mid, prediction, verdict))

        path.write_text(originals[path])
        assert hashlib.sha256(path.read_text().encode()).hexdigest() == shas[path], (
            f"{mid}: restore did not reproduce the original sha256"
        )

    code, summary = run_suites()
    print(f"\nRESTORED BASELINE: exit {code} — {summary}")
    killed = sum(1 for _, _, v in results if v == "KILL")
    unexpected = [m for m, p, v in results if p != v]
    print(f"{killed}/{len(results)} killed; {len(unexpected)} unexpected: {unexpected or 'none'}")
    return 0 if code == 0 and not unexpected else 1


if __name__ == "__main__":
    raise SystemExit(main())
