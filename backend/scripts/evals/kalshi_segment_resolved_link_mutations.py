#!/usr/bin/env python3
"""Q048 mutation battery — the segment reconciler must SEE a resolved link.

A guard suite that passes proves the code runs; it does not prove the code is
PINNED. Each mutant below is a plausible later edit — and every one of them is a
*simplification*, which is the point: the defect this queue closes was itself
one word (`status == "open"`) that looked like a sensible bound.

The specimen, measured on production 2026-09-02: 25 Kalshi tennis markets sat on
the wrong event of their own segment and **all 25 were `resolved`**, so the
open-only read had a 100% blind spot on exactly the population that matters. M1
restores that word; if M1 ever survives, the suite has stopped testing the
defect.

Mutations are applied to the real source file, the suite is run to completion,
and the file is restored — SERIALLY, never while another pytest is in flight
(`inspect.getsource` re-reads the file mid-run, and a source edit under a
running suite produces phantom failures that read as real reds).

Run:  python3 backend/scripts/evals/kalshi_segment_resolved_link_mutations.py
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
RECONCILER = ROOT / "app" / "tasks" / "prediction_market_matching.py"
DEDUP = ROOT / "app" / "utils" / "search_fixture_dedup.py"
SUITE = ROOT / "tests" / "test_kalshi_segment_reads_a_resolved_link_q048.py"

#: (id, description, old, new, target). `old` must appear EXACTLY once IN ITS
#: OWN TARGET — a mutation that matches zero or many places is a harness bug
#: reported as such, never counted as a kill.
#:
#: Two targets because the ship has two halves and either alone leaves the
#: defect on the page: the reconciler moves the market off the ghost, and the
#: search dedup stops rendering the ghost. Measured on production 2026-09-02,
#: `15300753` holds ZERO markets and still ranks FIRST for "Gauff" — so the
#: reconciler half on its own does not deliver the ship.
MUTANTS: list[tuple[str, str, str, str, object]] = [
    (
        "M1",
        "restore `status == \"open\"` — THE DEFECT: a resolved winner market "
        "is invisible and its ghost keeps it forever",
        """                    or_(
                        FuturesMarket.status == "open",
                        and_(
                            FuturesMarket.created_at >= window_floor,
                            FuturesMarket.event_id.isnot(None),
                        ),
                    ),""",
        '                    FuturesMarket.status == "open",',
        RECONCILER,
    ),
    (
        "M2",
        "drop the `event_id IS NOT NULL` narrowing — 176 historical props "
        "adopt in one pass, a blast radius nobody measured",
        """                        and_(
                            FuturesMarket.created_at >= window_floor,
                            FuturesMarket.event_id.isnot(None),
                        ),""",
        "                        FuturesMarket.created_at >= window_floor,",
        RECONCILER,
    ),
    (
        "M3",
        "make the window decorative — a ten-year read is unbounded in all but "
        "name and will trip the cap every run",
        "KALSHI_SEGMENT_WINDOW_DAYS = 14",
        "KALSHI_SEGMENT_WINDOW_DAYS = 3650",
        RECONCILER,
    ),
    (
        "M4",
        "reconcile a TRUNCATED read instead of refusing it — a segment whose "
        "schedule-derived member fell off the cap adopts onto the ghost",
        """            stats["truncated"] = True
            logger.error(""",
        """            stats["truncated"] = True
            _unused_but_keeps_the_branch = logger.info(""",
        RECONCILER,
    ),
    (
        "M5",
        "never flag the truncation — the caller cannot tell a refusal from a "
        "clean pass",
        '            stats["truncated"] = True',
        '            stats["truncated"] = False',
        RECONCILER,
    ),
    (
        "M6",
        "let the ticker-derived twin win the segment — converges the props "
        "onto the GHOST, a strictly worse bug that still reports success",
        '''    scheduled = [
        eid for eid in ids
        if provenance.get(eid) not in (None, _TICKER_DERIVED_COMMENCE_SOURCE)
    ]''',
        '''    scheduled = [
        eid for eid in ids
        if provenance.get(eid) in (None, _TICKER_DERIVED_COMMENCE_SOURCE)
    ]''',
        RECONCILER,
    ),
    (
        "M7",
        "put the cap back to the open-only bound — the widened population "
        "reaches it and reconciliation silently stops",
        "MAX_KALSHI_SEGMENT_ROWS = 20000",
        "MAX_KALSHI_SEGMENT_ROWS = 5000",
        RECONCILER,
    ),
    (
        "M8",
        "swallow a resolved market's settlement into the link write — gotcha "
        "#21, and unrecoverable precisely because these rows are already graded",
        '            values = {"event_id": target}',
        '            values = {"event_id": target, "status": "open"}',
        RECONCILER,
    ),
    (
        "M9",
        "make the derived-start window inert — 19 of the 22 measured ghost "
        "pairs fall back outside it and the ship silently does not ship",
        "DERIVED_START_WINDOW_HOURS = 96",
        "DERIVED_START_WINDOW_HOURS = 36",
        DEDUP,
    ),
    (
        "M10",
        "widen when EITHER side is derived — two stand-ins would pair off a "
        "gap nobody reported",
        "    one_side_derived = a.derived_start != b.derived_start",
        "    one_side_derived = a.derived_start or b.derived_start",
        DEDUP,
    ),
    (
        "M11",
        "read a NULL provenance as derived — silently widens the window for "
        "nearly every row on the site, which is the narrowness q076 spelled out",
        """        self.derived_start = not commence_time_is_a_reported_start(
            getattr(obj, "commence_time_source", None)
        )""",
        '        self.derived_start = getattr(obj, "commence_time_source", None) in (None, "kalshi_ticker")',
        DEDUP,
    ),
    (
        "M12",
        "drop the bound entirely for derived pairs — any PAST meeting of the "
        "same two players then dominates a future ghost",
        "    hours = DERIVED_START_WINDOW_HOURS if one_side_derived else FIXTURE_TIME_WINDOW_HOURS",
        "    hours = 10**9 if one_side_derived else FIXTURE_TIME_WINDOW_HOURS",
        DEDUP,
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
        [RECONCILER, DEDUP],
        "/tmp/q048_kalshi_segment_guard_backups",
        "kalshi_segment_resolved_link",
    ):
        return _main()


def _main() -> int:
    originals = {t: t.read_text() for t in (RECONCILER, DEDUP)}

    baseline = _run_suite()
    if baseline != 0:
        print(f"HARNESS FAILURE: the unmutated suite exits {baseline}, not 0. "
              "Nothing below is a verdict.")
        return 2
    print(f"baseline: suite GREEN on the unmutated tree "
          f"({len(MUTANTS)} mutants queued)\n")

    killed, survived, broken = [], [], []
    try:
        for mid, desc, old, new, target in MUTANTS:
            original = originals[target]
            n = original.count(old)
            if n != 1:
                broken.append((mid, f"anchor matched {n} times, expected exactly 1"))
                print(f"{mid:4} HARNESS  {desc}\n     anchor matched {n} times "
                      "— not a verdict")
                continue
            mutated = original.replace(old, new, 1)
            if mutated == original:
                broken.append((mid, "replacement is identical to the needle"))
                print(f"{mid:4} HARNESS  {desc}\n     mutation did not APPLY "
                      "— not a verdict")
                continue
            target.write_text(mutated)
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
                print(f"{mid:4} HARNESS  {desc}\n     pytest exit {rc} "
                      "— the gate never ran")
    finally:
        for t, text in originals.items():
            t.write_text(text)

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
