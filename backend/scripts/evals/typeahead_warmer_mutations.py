"""Mutation coverage for the `/typeahead` page warmer (#1866, LAT-P056).

WHY THIS HARNESS AND NOT JUST THE TESTS. Every failure mode this warmer has is
SILENT. It cannot crash a page, it cannot 500 a user, and it cannot return a
wrong answer — the only thing it can do wrong is *not warm* while reporting that
it did. A test suite that passes tells you the tests pass; it does not tell you
the tests would notice. So each guard gets a mutant that breaks it in the exact
way it would break in production, and the suite has to catch every one.

The three that matter, and why each is its own mutant rather than folded in:

* **M1/M2 — the debug flags.** `/typeahead`'s `debug_evidence` / `debug_timing`
  default to `Query(False)`, a marker object that is TRUTHY. Passing the default
  instead of a literal `False` makes the route skip its cache write, so the
  warmer does all the work and warms nothing. They are SEPARATE mutants because
  the route's guard is a conjunction: dropping only one leaves the other
  intact, the cache write still gets skipped, and a single combined mutant would
  let a half-broken caller look covered.

* **M3 — the empty head.** A run with nothing to warm must read PARTIAL. This
  is the ten-week zero-yield-SUCCESS shape (gotcha #53) aimed at a warmer.

* **M4 — the per-item guard.** One bad query must not wipe the pass (gotcha
  #42), and the loop must not abort on the first error.

* **M5 — the rollback.** A timed-out query leaves an aborted transaction; if the
  loop keeps the session without rolling back, every SUBSEQUENT query fails.
  Without its own mutant, M4 already passes and this stays uncovered.

* **M6 — the head-source label.** Which source produced the head changes what
  the run means; if it can be hardcoded and nothing notices, the summary is
  decoration rather than evidence.

Every mutation is proven APPLIED before it is scored (an anchor that matches 0
or 2+ times is NOT-APPLIED, never a silent SURVIVED), the control must be green
on unmutated source first (gotcha #122), and every target is restored
SHA-identical.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]

WARMER = BACKEND / "app" / "tasks" / "typeahead_warmer.py"

TARGETS = (WARMER,)
BACKUP_DIR = Path("/tmp/lat_p056_backups")

ORACLES = ["tests/test_typeahead_warmer.py"]

MUTATIONS: list[tuple[str, Path, str, str, str]] = [
    (
        "M1", WARMER,
        "debug_evidence falls back to the route's Query(False) default — TRUTHY, "
        "so the route skips its cache write and the warmer warms NOTHING",
        "                debug_evidence=False,\n                debug_timing=False,\n",
        "                debug_timing=False,\n",
    ),
    (
        "M2", WARMER,
        "debug_timing falls back to the default — the other half of the route's "
        "conjunction, and a mutant M1 would not catch",
        "                debug_timing=False,\n                db=session,\n",
        "                db=session,\n",
    ),
    (
        "M3", WARMER,
        "an EMPTY head reports `complete` — a warmer that warmed nothing "
        "reporting a clean success (gotcha #53)",
        '        "terminal": "complete" if head and not timeouts and not errors else "partial",\n',
        '        "terminal": "complete" if not timeouts and not errors else "partial",\n',
    ),
    (
        "M4", WARMER,
        "one throwing query aborts the whole loop, so healthy siblings never "
        "warm (gotcha #42)",
        "    except Exception:  # noqa: BLE001\n"
        '        logger.warning("typeahead_warmer: %r failed", q, exc_info=True)\n'
        "        await _safe_rollback(session)\n"
        '        return {"q": q, "ok": False, "reason": "error",\n'
        '                "seconds": round(time.monotonic() - started, 3)}\n',
        "    except Exception:  # noqa: BLE001\n"
        '        logger.warning("typeahead_warmer: %r failed", q, exc_info=True)\n'
        "        raise\n",
    ),
    (
        "M5", WARMER,
        "a failed query does NOT roll back, so its aborted transaction poisons "
        "the shared session and every later query in the run fails",
        "async def _safe_rollback(session) -> None:\n    try:\n        await session.rollback()\n",
        "async def _safe_rollback(session) -> None:\n    try:\n        pass\n",
    ),
    (
        "M6", WARMER,
        "the head source is hardcoded, so a run that fell back to the static "
        "floor reports itself as the live distribution",
        '        return head[:limit], "db:search_query_logs:30d"\n',
        '        return head[:limit], "redis:search:trending:24h"\n',
    ),
]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_oracles() -> tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *ORACLES, "-q", "--no-header"],
        cwd=BACKEND, capture_output=True, text=True,
    )
    if proc.returncode not in (0, 1):
        raise SystemExit(
            f"oracle exited {proc.returncode} — a usage error, not a result "
            f"(gotcha #121). Refusing to score.\n{proc.stdout[-2000:]}"
        )
    tail = [ln for ln in proc.stdout.strip().splitlines() if ln.strip()]
    return proc.returncode == 0, (tail[-1] if tail else "<no output>")


def main() -> int:
    BACKUP_DIR.mkdir(exist_ok=True)
    original = {t: _sha(t) for t in TARGETS}
    backups = {}
    for t in TARGETS:
        b = BACKUP_DIR / t.name
        shutil.copy2(t, b)
        backups[t] = b

    print("=" * 78)
    print("CONTROL — oracles against UNMUTATED source")
    ok, summary = _run_oracles()
    print(f"  {summary}")
    if not ok:
        print("\nCONTROL IS RED. Every mutant below would score a KILL it did not")
        print("earn (gotcha #122). Aborting without running any mutation.")
        return 2
    print("  control: oracles PASS on unmutated source")
    print("=" * 78)

    killed, survived, not_applied = [], [], []
    for mid, target, desc, old, new in MUTATIONS:
        source = backups[target].read_text()
        count = source.count(old)
        if count != 1:
            not_applied.append((mid, f"anchor matched {count}x, expected 1"))
            print(f"{mid:>4}  NOT-APPLIED  ({count}x anchor)  {desc}")
            continue

        target.write_text(source.replace(old, new, 1))
        if _sha(target) == original[target]:
            not_applied.append((mid, "file unchanged after write"))
            print(f"{mid:>4}  NOT-APPLIED  (no byte change)  {desc}")
            shutil.copy2(backups[target], target)
            continue

        ok, summary = _run_oracles()
        shutil.copy2(backups[target], target)
        assert _sha(target) == original[target], "restore did not reproduce the original"

        if ok:
            survived.append((mid, desc))
            print(f"{mid:>4}  SURVIVED     {desc}\n        {summary}")
        else:
            killed.append((mid, desc))
            print(f"{mid:>4}  KILLED       {desc}")

    print("=" * 78)
    print(f"killed {len(killed)}/{len(MUTATIONS)} · survived {len(survived)} · "
          f"not-applied {len(not_applied)}")
    for mid, desc in survived:
        print(f"  SURVIVOR {mid}: {desc}")
    for mid, why in not_applied:
        print(f"  NOT-APPLIED {mid}: {why}")
    for t in TARGETS:
        assert _sha(t) == original[t], f"{t.name} not restored"
    print("target restored, SHA matches original")
    return 0 if (not survived and not not_applied) else 1


if __name__ == "__main__":
    raise SystemExit(main())
