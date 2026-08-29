#!/usr/bin/env python3
"""LAT-P136 mutation battery for the related-futures shared cache (P127-2).

A guard suite that passes proves the code runs; it does not prove the code is
PINNED. Each mutant below is a plausible way this change could be broken by a
later edit — the kind of edit that looks like a simplification, or like
"unifying" two tiers that deliberately disagree. If a mutant survives, the suite
has a hole and the fix is to add the missing assertion, NOT to delete the mutant
(LAT-P115's M7 survived and the survivor was the finding).

Mutations are applied to the real source files, the suite is run to completion,
and the files are restored — SERIALLY. Never concurrently, and never while
another pytest is in flight: `inspect.getsource` re-reads the file mid-run and a
source edit under a running suite produces phantom failures that read as real
reds.

The `try/finally` in `_main()` restores on an exception; it does NOT survive a
SIGTERM or a SIGKILL. `guarded_targets` is the shared primitive that closes that
window (manifest + `--recover`), and `test_mutation_guard.py`'s
`test_every_on_disk_harness_is_guarded` fails any on-disk harness without it.

🔴 TWO TARGETS, ONE BATTERY, AND THAT IS THE POINT. The defect this ship fixes
is not in either file alone — it is that the ROUTE's serve ladder and the
MODULE's serve decision have to agree. A battery that could only mutate one of
them could not tell a broken ladder from a broken policy.

Run:  python3 backend/scripts/evals/related_futures_shared_cache_mutations.py
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
MODULE = ROOT / "app" / "utils" / "related_futures_cache.py"
SUITE = ROOT / "tests" / "test_related_futures_shared_cache_lat_p136.py"

#: (id, target, description, old, new). `old` must appear EXACTLY once in
#: `target` — a mutation that matches zero or many places is a harness bug
#: reported as such, never counted as a kill.
MUTANTS: list[tuple[str, pathlib.Path, str, str, str]] = [
    (
        "M1",
        ROUTE,
        "never read the shared slot — every worker rebuilds, the pre-ship defect",
        """    body, state = rfc.read(event_id)
    if state == "live" and body is not None:""",
        """    body, state = (None, "miss")
    if state == "live" and body is not None:""",
    ),
    (
        "M2",
        ROUTE,
        "publish the EMPTY exits too — 'no futures' sticks for a TTL after they arrive",
        """    if not cacheable:
        # An `empty` exit. NOT published, and that is carried across from the""",
        """    if False:
        # An `empty` exit. NOT published, and that is carried across from the""",
    ),
    (
        "M3",
        ROUTE,
        "let debug read the cache — the debug reader gets someone else's payload",
        """    if debug:
        response, source_status, market_ids, _cacheable = (
            await _build_related_futures(event_id, db, debug=True)
        )
        return response""",
        """    if False:
        response, source_status, market_ids, _cacheable = (
            await _build_related_futures(event_id, db, debug=True)
        )
        return response""",
    ),
    (
        "M4",
        ROUTE,
        "serve the mirror but never kick the rebuild — the tier goes permanently stale",
        """        if _serve_stale_and_refresh(
            f"related_futures:{event_id}", lambda: _rebuild_related_futures(event_id)
        ):
            return body""",
        """        if True:
            return body""",
    ),
    (
        "M5",
        ROUTE,
        "the refresh-behind overwrites a real mirror with an EMPTY rebuild",
        """        if not cacheable:
            # The mirror we are refreshing behind is a REAL answer; an `empty`""",
        """        if False:
            # The mirror we are refreshing behind is a REAL answer; an `empty`""",
    ),
    (
        "M6",
        ROUTE,
        "watermark over the season markets only — series and props drop out",
        """        season_market_ids + game_prop_ids + series_market_ids,""",
        """        season_market_ids,""",
    ),
    (
        "M7",
        ROUTE,
        "store the raw dict — a datetime round-trips as a different string shape",
        """    enveloped = jsonable_encoder(
        rfc.stamp(response, source_status=source_status, lifecycle_watermark=watermark)
    )""",
        """    enveloped = rfc.stamp(
        response, source_status=source_status, lifecycle_watermark=watermark
    )""",
    ),
    (
        "M8",
        MODULE,
        "pick a third mirror-age ceiling instead of the page's own law",
        """    return _gmc.stale_serve_ceiling_seconds(status)""",
        """    return 5 * fresh_ttl(status)""",
    ),
    (
        "M9",
        MODULE,
        "serve the mirror without checking its age — a day-old game clock ships",
        """    servable, reason = mirror_is_servable(mirror)
    if not servable:""",
        """    servable, reason = (True, "fresh_enough")
    if not servable:""",
    ),
    (
        "M10",
        MODULE,
        "an unknown source_status takes the LONGER ceiling",
        """    return _gmc.source_status_of(payload)""",
        """    return _gmc.source_status_of(payload) or "completed\"""",
    ),
    (
        "M11",
        MODULE,
        "give the primary slot the mirror's TTL — the fresh window becomes 24h",
        """        primary_ttl=fresh_ttl(source_status_of(enveloped)),""",
        """        primary_ttl=STALE_TTL,""",
    ),
    (
        "M12",
        MODULE,
        "copy the sibling's Redis prefix — two tiers overwrite each other per event",
        '''CACHE_PREFIX = "bainluck:related_futures:"''',
        """CACHE_PREFIX = _gmc.CACHE_PREFIX""",
    ),
    (
        "M13",
        MODULE,
        "re-base the live fresh TTL onto the sibling's — content freshness changes",
        """FRESH_TTL_LIVE = 60""",
        """FRESH_TTL_LIVE = _gmc.FRESH_TTL_LIVE""",
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
        "/tmp/lat_p136_related_futures_guard_backups",
        "related_futures_shared_cache",
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
