#!/usr/bin/env python3
"""LAT-P126 mutation battery for the `/playoffs/golf` schedule cache + warm.

A guard suite that passes proves the code runs; it does not prove the code is
PINNED. Each mutant below is a plausible way a later edit could break this —
mostly the kind of edit that reads as a simplification. If a mutant SURVIVES,
the suite has a hole and the fix is to add the missing assertion, never to
delete the mutant (LAT-P115's M7 survived and the survivor was the finding).

Two mutants here exist specifically because of LAT-P125's M5/M6, which survived:
every test in that cycle read the cache key THROUGH the shared constant, so the
route and its warmer moved in lockstep and a respelling was invisible. M10 and
M16 respell the key on ONE side only. They are the reason `LITERAL_KEY` in the
suite is a written-out string.

Mutations are applied to the real source files, the suite is run to completion,
and the files are restored — SERIALLY. Never concurrently, and never while
another pytest is in flight: `inspect.getsource` re-reads the file mid-run and a
source edit under a running suite produces phantom failures that read as real
reds.

Both halves of every mutant are written as VERBATIM literals, never `\\n`-escaped
ones. `scan_mutation_residue.py` Pass B flags a file holding a REPLACEMENT whose
NEEDLE is absent, and an escaped needle is absent by construction.

Run:  python3 backend/scripts/evals/golf_schedule_cache_mutations.py
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
ROUTE = ROOT / "app" / "routes" / "playoffs.py"
WARMER = ROOT / "app" / "tasks" / "precompute_category_pages.py"
SUITE = ROOT / "tests" / "test_golf_schedule_cache_lat_p126.py"

#: (id, target, description, old, new). `old` must appear EXACTLY once in its
#: target — a mutation that matches zero or many places is a harness bug
#: reported as such, never counted as a kill.
MUTANTS: list[tuple[str, pathlib.Path, str, str, str]] = [
    (
        "M1",
        ROUTE,
        "never read the cache — every visitor pays DataGolf again",
        """        if cached:
            return shape_golf_schedule(json.loads(cached), now_str)""",
        """        if False:
            return shape_golf_schedule(json.loads(cached), now_str)""",
    ),
    (
        "M2",
        ROUTE,
        "back to five sequential round trips — the user pays the sum",
        """        results = await _asyncio.gather(
            *(service.get_schedule(tour=tour) for tour in GOLF_SCHEDULE_TOURS),
            return_exceptions=True,
        )""",
        """        results = []
        for _tour in GOLF_SCHEDULE_TOURS:
            try:
                results.append(await service.get_schedule(tour=_tour))
            except Exception as _exc:
                results.append(_exc)""",
    ),
    (
        "M3",
        ROUTE,
        "drop return_exceptions — one dead tour takes the whole page down",
        """            *(service.get_schedule(tour=tour) for tour in GOLF_SCHEDULE_TOURS),
            return_exceptions=True,""",
        """            *(service.get_schedule(tour=tour) for tour in GOLF_SCHEDULE_TOURS),""",
    ),
    (
        "M4",
        ROUTE,
        "TTL back to 3600 — it expires before the hourly warm that refills it",
        """GOLF_SCHEDULE_TTL_S = 3900""",
        """GOLF_SCHEDULE_TTL_S = 3600""",
    ),
    (
        "M5",
        ROUTE,
        "stop writing the last-good mirror — a DataGolf outage empties the page",
        """            await rc.set(
                f"{GOLF_SCHEDULE_CACHE_KEY}:stale",
                payload,
                ex=GOLF_SCHEDULE_STALE_TTL_S,
            )""",
        """            pass""",
    ),
    (
        "M6",
        ROUTE,
        "shape reads the clock itself — the cached badge freezes on the fetch day",
        """def shape_golf_schedule(raw: dict, now_str: str) -> dict:""",
        """def shape_golf_schedule(raw: dict, now_str: str) -> dict:
    now_str = raw.get("fetched_at", "")[:10] or now_str""",
    ),
    (
        "M7",
        ROUTE,
        "last_updated back to serve time — hour-old bytes claim to be fresh",
        """        "last_updated": raw.get("fetched_at"),""",
        """        "last_updated": datetime.now(timezone.utc).isoformat(),""",
    ),
    (
        "M8",
        ROUTE,
        "cache an empty fetch over a good one — the section vanishes for an hour",
        """    if not raw.get("tours"):""",
        """    if False:""",
    ),
    (
        "M9",
        ROUTE,
        "500 on a fetch failure instead of serving last-good",
        """        stale = await _read_golf_schedule_stale()
        if stale is not None:
            return _mark_last_good(
                shape_golf_schedule(stale, now_str), "fetch_failed", degraded=True
            )
        raise HTTPException(status_code=500, detail="Failed to fetch golf schedule")""",
        """        raise HTTPException(status_code=500, detail="Failed to fetch golf schedule")""",
    ),
    (
        "M10",
        ROUTE,
        "respell the key on the ROUTE side only — LAT-P125's M5/M6 class",
        """GOLF_SCHEDULE_CACHE_KEY = "bainluck:category:playoffs:golf:schedule\"""",
        """GOLF_SCHEDULE_CACHE_KEY = "bainluck:category:playoffs:golf-schedule\"""",
    ),
    (
        "M11",
        ROUTE,
        "sort the tours — the PGA tab stops being the one that opens",
        """    tour_schedules = []
    for entry in raw.get("tours") or []:""",
        """    tour_schedules = []
    for entry in sorted(raw.get("tours") or [], key=lambda e: str(e.get("tour"))):""",
    ),
    (
        "M12",
        ROUTE,
        "shape mutates the cached dict — the second serve sees the first's answer",
        """            events.append({
                "event_id": t.get("event_id"),""",
        """            t["status"] = display_status
            events.append({
                "event_id": t.get("event_id"),""",
    ),
    (
        "M13",
        WARMER,
        "warmer writes only the primary — nothing behind it when DataGolf dies",
        """    rc.set(f"{GOLF_SCHEDULE_CACHE_KEY}:stale", payload, ex=GOLF_SCHEDULE_STALE_TTL_S)""",
        """    pass""",
    ),
    (
        "M14",
        WARMER,
        "warmer overwrites a good cache with an empty fetch",
        """    if not tours:""",
        """    if False:""",
    ),
    (
        "M15",
        WARMER,
        "move the warm behind the grids — it starves first when budget runs out",
        """        ("golf_schedule", _precompute_golf_schedule),
        ("grids", _precompute_grids),""",
        """        ("grids", _precompute_grids),
        ("golf_schedule", _precompute_golf_schedule),""",
    ),
    (
        "M16",
        WARMER,
        "respell the key on the WARMER side only — warm and route diverge",
        """    rc.set(GOLF_SCHEDULE_CACHE_KEY, payload, ex=GOLF_SCHEDULE_TTL_S)""",
        """    rc.set("bainluck:category:playoffs:golfschedule", payload, ex=GOLF_SCHEDULE_TTL_S)""",
    ),
    (
        "M17",
        WARMER,
        "warm the schedule off the golf listing's success path — LAT-P001's coupling",
        """        ("golf_schedule", _precompute_golf_schedule),""",
        """""",
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
        [ROUTE, WARMER], "/tmp/lat_p126_golf_schedule_guard_backups",
        "golf_schedule_cache",
    ):
        return _main()


def _main() -> int:
    originals = {ROUTE: ROUTE.read_text(), WARMER: WARMER.read_text()}

    print(f"denominator: {len(MUTANTS)} mutants queued across "
          f"{len(originals)} target files")
    baseline = _run_suite()
    if baseline != 0:
        print(f"HARNESS FAILURE: the unmutated suite exits {baseline}, not 0. "
              "Nothing below is a verdict.")
        return 2
    print("baseline: suite GREEN on the unmutated tree\n")

    killed, survived, broken = [], [], []
    try:
        for mid, target, desc, old, new in MUTANTS:
            original = originals[target]
            n = original.count(old)
            if n != 1:
                broken.append((mid, f"anchor matched {n} times, expected exactly 1"))
                print(f"{mid:4} HARNESS  {desc}\n     anchor matched {n} times — not a verdict")
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
