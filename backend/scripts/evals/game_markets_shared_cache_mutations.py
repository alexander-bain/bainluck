#!/usr/bin/env python3
"""LAT-P121 mutation battery for the game-markets shared cache (#1587).

A guard suite that passes proves the code runs; it does not prove the code is
PINNED. Each mutant below is a plausible way this change could be broken by a
later edit — the kind of edit that looks like a simplification, or like a tidy-up
of "two constants that mean the same thing". If a mutant survives, the suite has
a hole and the fix is to add the missing assertion, NOT to delete the mutant
(LAT-P115's M7 survived and the survivor was the finding).

Two of these are the ones this battery exists for:

  * **M1 / M2 — the age bound on the mirror.** This payload is a function of the
    CLOCK as well as of the database: it filters props through
    `prop_window_closed` and publishes `served_event_status`. A latency fix that
    quietly lets a 24h mirror of a LIVE game reach a reader ships a formatting
    lie, and it ships as a WIN — every latency number improves.
  * **M4 / M14 — serving stale with nothing coming behind it.** A mirror served
    without a rebuild scheduled is a cache that goes permanently cold and reports
    itself fast forever.

Mutations are applied to the real source files, the suite is run to completion,
and the files are restored — SERIALLY. Never concurrently, and never while
another pytest is in flight: `inspect.getsource` re-reads the file mid-run and a
source edit under a running suite produces phantom failures that read as real
reds.

The `try/finally` in `_main()` restores on an exception; it does NOT survive a
SIGTERM or SIGKILL. `guarded_targets` is the shared primitive that closes that
window (manifest + `--recover`).

Run:  python3 backend/scripts/evals/game_markets_shared_cache_mutations.py
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
CACHE = ROOT / "app" / "utils" / "game_markets_cache.py"
ROUTE = ROOT / "app" / "routes" / "events.py"
SUITE = ROOT / "tests" / "test_game_markets_shared_cache.py"

#: (id, description, target, old, new). `old` must appear EXACTLY once in
#: `target` — a mutation that matches zero or many places is a harness bug
#: reported as such, never counted as a kill.
MUTANTS: list[tuple[str, str, pathlib.Path, str, str]] = [
    (
        "M1",
        "drop the mirror's age bound — a 24h mirror of a LIVE game is served",
        CACHE,
        "STALE_SERVE_CEILING = 5",
        "STALE_SERVE_CEILING = 10**9",
    ),
    (
        "M2",
        "an unknown status takes the LONGER ceiling — a missing field serves stale",
        CACHE,
        '    return str(envelope.get(SOURCE_STATUS_FIELD) or "")',
        '    return str(envelope.get(SOURCE_STATUS_FIELD) or "completed")',
    ),
    (
        "M3",
        "never consult the mirror — a primary expiry costs a full rebuild again",
        CACHE,
        "    mirror = read_slot(client, keys.stale)",
        "    mirror = None",
    ),
    (
        "M4",
        "serve the mirror but never kick the rebuild — the tier goes permanently cold",
        ROUTE,
        """        if _serve_stale_and_refresh(
            f"game_markets:{event_id}", lambda: _rebuild_game_markets(event_id)
        ):
            return body""",
        "        if True:\n            return body",
    ),
    (
        "M5",
        "skip the shared write — back to a per-process cache with extra steps",
        ROUTE,
        "    gmc.write(event_id, enveloped)",
        "    pass",
    ),
    (
        "M6",
        "never read the shared slot — every worker rebuilds independently",
        ROUTE,
        "    body, state = gmc.read(event_id)",
        '    body, state = (None, "miss")',
    ),
    (
        "M7",
        "give a live game the finished game's TTL — a stale board for an hour",
        CACHE,
        "    return FRESH_TTL_FINAL if is_final(status) else FRESH_TTL_LIVE",
        "    return FRESH_TTL_FINAL",
    ),
    (
        "M8",
        "re-base the live fresh TTL — a latency win that is really a freshness loss",
        CACHE,
        "FRESH_TTL_LIVE = 30",
        "FRESH_TTL_LIVE = 300",
    ),
    (
        "M9",
        "serve a mirror that cannot say when it was built — the bound is unevaluable",
        CACHE,
        '        return False, "no_created_at"',
        '        return True, "no_created_at"',
    ),
    (
        "M10",
        "publish a mirror read as `live` — the consumer cannot tell it is stale",
        CACHE,
        "    return with_availability(mirror, AVAILABILITY_STALE_OK), \"stale_ok\"",
        "    return with_availability(mirror, AVAILABILITY_LIVE), \"stale_ok\"",
    ),
    (
        "M11",
        "memoise the un-enveloped body — L1 and L2 readers get different payloads",
        ROUTE,
        "    _write_game_markets_memo(event_id, source_status, served)\n    return served",
        "    _write_game_markets_memo(event_id, source_status, response)\n    return served",
    ),
    (
        "M12",
        "give the primary the mirror's TTL — the mirror path can never be reached",
        CACHE,
        "        primary_ttl=fresh_ttl(source_status_of(enveloped)),",
        "        primary_ttl=STALE_TTL,",
    ),
    (
        "M13",
        "share the concept tier's namespace — two payload shapes on one key",
        CACHE,
        'CACHE_PREFIX = "bainluck:game_markets:"',
        'CACHE_PREFIX = "bainluck:event_concept:"',
    ),
    (
        "M14",
        "no loop to refresh behind us, serve stale anyway — fail-OPEN",
        ROUTE,
        """        # No running loop to refresh behind us — fall through and build, rather
        # than serve stale with nothing coming to replace it.""",
        "        return body",
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
        [CACHE, ROUTE],
        "/tmp/lat_p121_game_markets_cache_guard_backups",
        "game_markets_shared_cache",
    ):
        return _main()


def _main() -> int:
    originals = {path: path.read_text() for path in (CACHE, ROUTE)}

    baseline = _run_suite()
    if baseline != 0:
        print(
            f"HARNESS FAILURE: the unmutated suite exits {baseline}, not 0. "
            "Nothing below is a verdict."
        )
        return 2
    # 🔴 The DENOMINATOR is printed BEFORE the first verdict, deliberately.
    # LAT-P120's battery reported `11/11 killed` over a table a third of whose
    # entries had silently failed to append; a run that prints only its kills
    # reads as a clean sweep over whatever survived the edit.
    print(
        f"baseline: suite GREEN on the unmutated tree "
        f"({len(MUTANTS)} mutants queued across {len(originals)} targets)\n"
    )

    killed, survived, broken = [], [], []
    try:
        for mid, desc, target, old, new in MUTANTS:
            original = originals[target]
            n = original.count(old)
            if n != 1:
                broken.append((mid, f"anchor matched {n} times in {target.name}"))
                print(
                    f"{mid:4} HARNESS  {desc}\n"
                    f"     anchor matched {n} times in {target.name} — not a verdict"
                )
                continue
            target.write_text(original.replace(old, new, 1))
            rc = _run_suite()
            target.write_text(original)  # restore before anything else runs
            if rc == 0:
                survived.append((mid, desc))
                print(f"{mid:4} SURVIVED {desc}")
            elif rc == 1:
                killed.append(mid)
                print(f"{mid:4} killed   {desc}")
            else:
                broken.append((mid, f"pytest exit {rc}"))
                print(
                    f"{mid:4} HARNESS  {desc}\n"
                    f"     pytest exit {rc} — the gate never ran"
                )
    finally:
        for path, text in originals.items():
            path.write_text(text)

    print(
        f"\n{len(killed)}/{len(MUTANTS)} killed, {len(survived)} survived, "
        f"{len(broken)} harness failures"
    )
    for mid, desc in survived:
        print(f"  SURVIVOR {mid}: {desc}")
    if broken:
        for mid, why in broken:
            print(f"  BROKEN {mid}: {why}")
        return 2
    return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(main())
