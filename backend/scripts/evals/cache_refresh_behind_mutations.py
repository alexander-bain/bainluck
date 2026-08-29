#!/usr/bin/env python3
"""LAT-P116 mutation battery for the refresh-behind caches.

A guard suite that passes proves the code runs; it does not prove the code is
PINNED. Each mutant below is a plausible way this change could be broken by a
later edit — the kind of edit that looks like a simplification. If a mutant
survives, the suite has a hole and the fix is to add the missing assertion, NOT
to delete the mutant (LAT-P115's M7 survived and the survivor was the finding).

Mutations are applied to the real source file, the suite is run to completion,
and the file is restored — SERIALLY. Never concurrently, and never while another
pytest is in flight: `inspect.getsource` re-reads the file mid-run and a source
edit under a running suite produces phantom failures that read as real reds.

The `try/finally` in `main()` restores on an exception; it does NOT survive a
SIGTERM or a SIGKILL, and a harness that dies between write and restore leaves a
mutant sitting in `events.py`. `guarded_targets` is the shared primitive that
closes that window (manifest + `--recover`), and `test_mutation_guard.py`'s
`test_every_on_disk_harness_is_guarded` fails any on-disk harness without it —
which is exactly how this one was caught, on its first full-suite run.

Run:  python3 backend/scripts/evals/cache_refresh_behind_mutations.py
Exit: 0 = every mutant killed. 1 = at least one survived. Anything else is the
      harness failing, not a verdict (gotcha #54).
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _mutation_guard import guarded_targets  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
TARGET = ROOT / "app" / "routes" / "events.py"
SUITE = ROOT / "tests" / "test_search_cache_refresh_behind.py"

#: (id, description, old, new). `old` must appear EXACTLY once — a mutation that
#: matches zero or many places is a harness bug reported as such, never counted
#: as a kill.
MUTANTS: list[tuple[str, str, str, str]] = [
    (
        "M1",
        "serve stale but never kick the rebuild — the cache goes permanently cold",
        '        if age < _EI_CACHE_TTL * _STALE_SERVE_CEILING and _serve_stale_and_refresh(\n'
        '            "ei_percentiles", _rebuild_ei_percentiles\n'
        '        ):\n'
        '            return _ei_cache',
        '        if age < _EI_CACHE_TTL * _STALE_SERVE_CEILING:\n'
        '            return _ei_cache',
    ),
    (
        "M2",
        "drop the in-flight guard — a burst of expired callers stampedes",
        "    if name in _STALE_REFRESH_INFLIGHT:\n        return True",
        "    if False:\n        return True",
    ),
    (
        "M3",
        "drop the ceiling — a permanently-failing refresh serves stale forever",
        "_STALE_SERVE_CEILING = 5",
        "_STALE_SERVE_CEILING = 10**9",
    ),
    (
        "M4",
        "clear the cache when a rebuild fails — a DB blip empties it",
        '            logger.warning("cache refresh-behind failed for %s: %s", name, exc)',
        '            logger.warning("cache refresh-behind failed for %s: %s", name, exc)\n'
        '            globals()["_ei_cache"] = {}',
    ),
    # 🔴 M5 and M8 are written as literal multi-line strings, not `\n`-escaped
    # ones, and that is not a style choice. `scan_mutation_residue.py` Pass B
    # flags any file holding a REPLACEMENT whose NEEDLE is absent. Both of these
    # have single-line replacements, so the replacement appears verbatim in this
    # harness — and with an escaped needle the needle does not, so the scanner
    # correctly reported this file as holding two loose mutants. Writing the
    # needle verbatim too puts both halves in the file and clears the pair.
    (
        "M5",
        "do not hold a strong ref — the GC can collect a rebuild mid-flight",
        """    _STALE_REFRESH_TASKS.add(task)
    task.add_done_callback(_STALE_REFRESH_TASKS.discard)""",
        "    task.add_done_callback(_STALE_REFRESH_TASKS.discard)",
    ),
    (
        "M6",
        "leave the in-flight flag set on failure — the cache never refreshes again",
        "        finally:\n            _STALE_REFRESH_INFLIGHT.discard(name)",
        "        finally:\n            pass",
    ),
    (
        "M7",
        "serve an EMPTY cache as stale — a fresh process ships a search with no logos",
        "    now = time.monotonic()\n    if _ei_cache:\n        age = now - _ei_cache_time",
        "    now = time.monotonic()\n    if True:\n        age = now - _ei_cache_time",
    ),
    (
        "M8",
        "team half: serve stale but never rebuild",
        """        if age < _TEAM_CACHE_TTL or (
            age < _TEAM_CACHE_TTL * _STALE_SERVE_CEILING
            and _serve_stale_and_refresh("team_lookup", _rebuild_team_lookup)
        ):""",
        "        if age < _TEAM_CACHE_TTL * _STALE_SERVE_CEILING:",
    ),
    (
        "M9",
        "no running loop returns True — stale is served forever off the loop",
        "    except RuntimeError:\n"
        "        # No loop (sync test harness, script import). Nothing can run behind the\n"
        "        # caller, so refuse rather than serve stale forever.\n"
        "        return False",
        "    except RuntimeError:\n        return True",
    ),
    (
        "M10",
        "team rebuild shapes rows itself instead of reusing the extractor — drift",
        "        full_lookup = _shape_team_lookup(result.scalars().all())\n\n"
        "    _team_cache = full_lookup\n"
        "    _team_cache_time = time.monotonic()",
        "        full_lookup = _dedupe_team_name_lookup(\n"
        "            [_snapshot_team(t) for t in result.scalars().all()][:1]\n"
        "        )\n\n"
        "    _team_cache = full_lookup\n"
        "    _team_cache_time = time.monotonic()",
    ),
]


def _run_suite() -> int:
    return subprocess.run(
        [sys.executable, "-m", "pytest", str(SUITE), "-q", "--no-header", "-x"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    ).returncode


def main() -> int:
    with guarded_targets(
        [TARGET], "/tmp/lat_p116_cache_refresh_guard_backups", "cache_refresh_behind"
    ):
        return _main()


def _main() -> int:
    original = TARGET.read_text()

    baseline = _run_suite()
    if baseline != 0:
        print(f"HARNESS FAILURE: the unmutated suite exits {baseline}, not 0. "
              "Nothing below is a verdict.")
        return 2
    print(f"baseline: suite GREEN on the unmutated tree ({len(MUTANTS)} mutants queued)\n")

    killed, survived, broken = [], [], []
    try:
        for mid, desc, old, new in MUTANTS:
            n = original.count(old)
            if n != 1:
                broken.append((mid, f"anchor matched {n} times, expected exactly 1"))
                print(f"{mid:4} HARNESS  {desc}\n     anchor matched {n} times — not a verdict")
                continue
            TARGET.write_text(original.replace(old, new, 1))
            rc = _run_suite()
            TARGET.write_text(original)  # restore before anything else runs
            if rc == 0:
                survived.append((mid, desc))
                print(f"{mid:4} SURVIVED {desc}")
            elif rc == 1:
                killed.append(mid)
                print(f"{mid:4} killed   {desc}")
            else:
                broken.append((mid, f"pytest exit {rc}"))
                print(f"{mid:4} HARNESS  {desc}\n     pytest exit {rc} — the gate never ran")
    finally:
        TARGET.write_text(original)

    print(f"\n{len(killed)}/{len(MUTANTS)} killed, {len(survived)} survived, "
          f"{len(broken)} harness failures")
    for mid, desc in survived:
        print(f"  SURVIVOR {mid}: {desc}")
    if broken:
        for mid, why in broken:
            print(f"  BROKEN {mid}: {why}")
        return 2
    return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(main())
