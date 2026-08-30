#!/usr/bin/env python3
"""LAT-P144 mutation battery for the season-market discovery cache (P136-1).

A guard suite that passes proves the code runs; it does not prove the code is
PINNED. Each mutant below is a plausible way this change could be broken by a
later edit — mostly the edits that look like tidying: collapsing the two TTLs
into one, dropping the `debug` bypass as dead weight, "simplifying" the key.
If a mutant survives, the suite has a hole and the fix is to add the missing
assertion, NOT to delete the mutant (LAT-P115's M7 survived and the survivor
was the finding).

Mutations are applied to the real source files, the suite is run to completion,
and the files are restored — SERIALLY. Never concurrently, and never while
another pytest is in flight: `inspect.getsource` re-reads the file mid-run and a
source edit under a running suite produces phantom failures that read as real
reds.

The `try/finally` in `_main()` restores on an exception; it does NOT survive a
SIGTERM or a SIGKILL. `guarded_targets` is the shared primitive that closes that
window (manifest + `--recover`), and `test_mutation_guard.py`'s
`test_every_on_disk_harness_is_guarded` fails any on-disk harness without it.

🔴 TWO TARGETS, ONE BATTERY. The defect is not in either file alone: the MODULE
decides what may be cached and for how long, and the ROUTE decides when to ask.
A battery that could only mutate one of them could not tell a cache that never
gets consulted from a cache that answers wrongly — and the first of those is
exactly the pre-ship state, which every test must be able to see.

Run:  python3 backend/scripts/evals/season_market_discovery_mutations.py
      (from `backend/` — a repo-root launch exits 2 with "can't open file",
       which is a story about the harness, not a verdict; gotcha #54)
Exit: 0 = every mutant killed. 1 = at least one survived. Anything else is the
      harness failing, not a verdict.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _mutation_guard import guarded_targets  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
ROUTE = ROOT / "app" / "routes" / "events.py"
MODULE = ROOT / "app" / "utils" / "season_market_discovery.py"
SUITE = ROOT / "tests" / "test_season_market_discovery_lat_p144.py"

#: (id, target, description, old, new). `old` must appear EXACTLY once in
#: `target` — a mutation that matches zero or many places is a harness bug
#: reported as such, never counted as a kill.
MUTANTS: list[tuple[str, pathlib.Path, str, str, str]] = [
    (
        "M1",
        ROUTE,
        "never consult the cache — the pre-ship defect, 1,061 ms per event page",
        """    season_market_ids = (
        None if debug else _smd.read(event_sport_key, event_is_finished)
    )""",
        """    season_market_ids = None""",
    ),
    (
        "M2",
        ROUTE,
        "never publish — every reader is the first reader, forever",
        """        if not debug:
            _smd.write(event_sport_key, event_is_finished, season_market_ids)""",
        """        pass""",
    ),
    (
        "M3",
        ROUTE,
        "let debug read the cache — a debug request stops seeing uncached truth",
        """        None if debug else _smd.read(event_sport_key, event_is_finished)""",
        """        _smd.read(event_sport_key, event_is_finished)""",
    ),
    (
        "M4",
        ROUTE,
        "let debug publish — the debug reader's build becomes everyone's answer",
        """        if not debug:
            _smd.write""",
        """        if True:
            _smd.write""",
    ),
    (
        "M5",
        ROUTE,
        "cache the RAW rows, not the tier-capped list — an extra market reaches the page",
        """        if not debug:
            _smd.write(event_sport_key, event_is_finished, season_market_ids)""",
        """        if not debug:
            _smd.write(
                event_sport_key, event_is_finished, [r.id for r in _tier_rows]
            )""",
    ),
    (
        "M6",
        ROUTE,
        "key on the sport PREFIX — baseball_milb serves baseball_mlb's markets",
        """        None if debug else _smd.read(event_sport_key, event_is_finished)""",
        """        None if debug else _smd.read(sport_prefix, event_is_finished)""",
    ),
    (
        "M7",
        ROUTE,
        "drop finishedness from the read — a finished event serves the live answer",
        """        None if debug else _smd.read(event_sport_key, event_is_finished)""",
        """        None if debug else _smd.read(event_sport_key, False)""",
    ),
    (
        "M8",
        ROUTE,
        "drop finishedness from the write — the two shapes overwrite each other",
        """            _smd.write(event_sport_key, event_is_finished, season_market_ids)""",
        """            _smd.write(event_sport_key, False, season_market_ids)""",
    ),
    (
        "M9",
        MODULE,
        "an empty answer reads back as a miss — the slowest sport never gets a hit",
        """    if not isinstance(value, list):
        return None""",
        """    if not isinstance(value, list) or not value:
        return None""",
    ),
    (
        "M10",
        MODULE,
        "one TTL for both — an empty sport stays empty for the full found window",
        """    return TTL_FOUND if market_ids else TTL_EMPTY""",
        """    return TTL_FOUND""",
    ),
    (
        "M11",
        MODULE,
        "the empty TTL grows past the found one — the split inverts",
        """TTL_EMPTY = 60""",
        """TTL_EMPTY = TTL_FOUND * 2""",
    ),
    (
        "M12",
        MODULE,
        "finishedness leaves the key — one slot answers two different queries",
        '''    shape = "final" if event_is_finished else "live"
    return f"{CACHE_PREFIX}{sport_key}:{shape}"''',
        '''    return f"{CACHE_PREFIX}{sport_key}"''',
    ),
    (
        "M13",
        MODULE,
        "the sport leaves the key — every sport shares one answer",
        '''    return f"{CACHE_PREFIX}{sport_key}:{shape}"''',
        '''    return f"{CACHE_PREFIX}{shape}"''',
    ),
    (
        "M14",
        MODULE,
        "a booking of True passes as a market id — id 1 lands on the page",
        """        if isinstance(item, bool) or not isinstance(item, int):
            return None""",
        """        if not isinstance(item, int):
            return None""",
    ),
    (
        "M15",
        MODULE,
        "any JSON decodes — a dict or a bare number reads as an answer",
        """    if not isinstance(value, list):
        return None""",
        """    if False:
        return None""",
    ),
    (
        "M16",
        MODULE,
        "a sick Redis raises out of read instead of costing a rebuild",
        """    try:
        raw = client.get(cache_key(sport_key, event_is_finished))
    except Exception:""",
        """    if True:
        raw = client.get(cache_key(sport_key, event_is_finished))
    if False:""",
    ),
    (
        "M17",
        MODULE,
        "a sick Redis raises out of write instead of degrading to uncached",
        """    try:
        client.setex(
            cache_key(sport_key, event_is_finished),
            ttl_for(market_ids),
            json.dumps(list(market_ids)),
        )
    except Exception:
        logger.warning(
            "season-market discovery: write failed for %s", sport_key
        )
        return False
    return True""",
        """    client.setex(
        cache_key(sport_key, event_is_finished),
        ttl_for(market_ids),
        json.dumps(list(market_ids)),
    )
    return True""",
    ),
    (
        "M18",
        MODULE,
        "write reports success when there is no client at all",
        """    if client is None:
        return False""",
        """    if client is None:
        return True""",
    ),
    (
        "M19",
        MODULE,
        "the stored order is sorted — the positional tier cap picks other markets",
        """            json.dumps(list(market_ids)),""",
        """            json.dumps(sorted(market_ids)),""",
    ),
    (
        "M20",
        MODULE,
        "the generation marker leaves the namespace — a shape change cannot invalidate",
        '''CACHE_PREFIX = "bainluck:season_markets:v1:"''',
        '''CACHE_PREFIX = "bainluck:season_markets:"''',
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
        [ROUTE, MODULE],
        "/tmp/lat_p144_season_market_discovery_guard_backups",
        "season_market_discovery",
    ):
        return _main()


def _main() -> int:
    originals = {path: path.read_text() for path in (ROUTE, MODULE)}

    baseline = _run_suite()
    if baseline != 0:
        print(
            f"HARNESS FAILURE: the unmutated suite exits {baseline}, not 0. "
            "Nothing below is a verdict."
        )
        return 2
    print(f"baseline: suite GREEN on the unmutated tree ({len(MUTANTS)} mutants queued)\n")

    killed, survived, broken = [], [], []
    try:
        for mid, target, desc, old, new in MUTANTS:
            original = originals[target]
            n = original.count(old)
            if n != 1:
                broken.append((mid, f"anchor matched {n} times, expected exactly 1"))
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
                print(f"{mid:4} HARNESS  {desc}\n     pytest exit {rc} — the gate never ran")
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
