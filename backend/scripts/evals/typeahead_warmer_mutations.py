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

from _mutation_guard import guarded_targets  # noqa: E402

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
        # LAT-P134 re-target: the terminal expression grew a `no_writes` term
        # and was reflowed over four lines. Re-pointed by the cycle that moved
        # it — a needle left drifting scores NOT-APPLIED, which prints next to
        # the kills and reads like coverage.
        '            if head and not timeouts and not errors and not no_writes\n',
        '            if not timeouts and not errors and not no_writes\n',
    ),
    (
        # 🔴 RE-TARGETED BY LAT-P134, and by the cycle that MOVED the code it
        # points at rather than by a later reader guessing. The needle had
        # drifted (#2113/#2154) — `scan_mutation_residue` PASS A had been
        # reporting it as harness drift for weeks, which scores NOT-APPLIED and
        # never a false kill, so the defect was simply uncovered. LAT-P134
        # restructured this very try/except (the route call moved into a `try`
        # with a `finally` that resets `_force_cache_rebuild`), which is exactly
        # the edit a per-item-guard mutant exists to police. Leaving it drifted
        # would have meant shipping a rewrite of the guard with the battery for
        # that guard switched off. M6 remains drifted and is NOT touched here:
        # it points at `resolve_head`, which this cycle did not change.
        "M4", WARMER,
        "one throwing query aborts the whole loop, so healthy siblings never "
        "warm (gotcha #42)",
        "    except Exception:  # noqa: BLE001\n"
        '        logger.warning("typeahead_warmer: %r failed", q, exc_info=True)\n'
        "        await _safe_rollback(session)\n"
        '        return {"q": q, "ok": False, "reason": "error",\n'
        '                "ttl_before": ttl_before, "rebuilt": True, "ttl_after": None,\n'
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
        # LAT-P134 re-target. This one is NOT LAT-P134's doing — it drifted when
        # `resolve_head` gained the blended head and the local became
        # `log_head` (LAT-P078). It is taken here because #2113/#2154 name
        # exactly these two mutants as "now unguarded", the harness was already
        # open on this desk, and a NOT-APPLIED printed beside nine kills reads
        # like coverage to everyone who does not scroll.
        '        return log_head[:limit], "db:search_query_logs:30d"\n',
        '        return log_head[:limit], "redis:search:trending:24h"\n',
    ),
    (
        "M7", WARMER,
        "the single-run lock is ignored, so at a 30s cadence a slow cold run "
        "gets a second copy piled on top of it doing identical work",
        "    if not _acquire_run_lock():\n",
        "    if False:\n",
    ),
    (
        "M8", WARMER,
        "a SKIPPED run reports `complete` — a wedged lock would then read as a "
        "healthy warmer forever, on every beat",
        '            "terminal": "skipped",\n',
        '            "terminal": "complete",\n',
    ),
    (
        "M9", WARMER,
        "the lock is never released, so one run wedges the warmer off for the "
        "whole lock TTL after every beat",
        "    finally:\n        _release_run_lock()\n",
        "    finally:\n        pass\n",
    ),
    (
        "M10", WARMER,
        "the lock fails CLOSED on a Redis blip — the warmer silently stops "
        "warming and reports a clean skip every beat",
        '        logger.warning("typeahead_warmer: lock unavailable, warming anyway", exc_info=True)\n'
        "        return True\n",
        '        logger.warning("typeahead_warmer: lock unavailable, warming anyway", exc_info=True)\n'
        "        return False\n",
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


def _main() -> int:
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



def main() -> int:
    """Run the harness with an UNCONDITIONAL restore around it — #2107 sibling.

    `_main()` still restores after each mutant, exactly as before; this is the
    net under it. The incident it exists for is `bcdcd95f`, where a harness
    died at **exit 143** between writing a mutant and restoring it, and the
    mutant rode a commit. `try/finally` alone does not survive SIGTERM, so the
    guard installs the handler that gives `finally` something to run on — see
    `_mutation_guard.py` for the four failure cases and which one is not
    catchable.
    """
    with guarded_targets(TARGETS, BACKUP_DIR, 'lat_p056_typeahead_warmer'):
        return _main()

if __name__ == "__main__":
    raise SystemExit(main())
