#!/usr/bin/env python3
"""LAT-P127 mutation battery for the futures-detail provenance cache.

A guard suite that passes proves the code runs; it does not prove the code is
PINNED. Each mutant below is a plausible way a later edit could break this —
mostly the kind of edit that reads as a simplification or a tidy-up. If a mutant
SURVIVES, the suite has a hole and the fix is to add the missing assertion,
never to delete the mutant (LAT-P115's M7 survived and the survivor WAS the
finding).

Three mutants exist because of specific survivors in earlier cycles:

  M-KEY  respells the cache key ROUTE-SIDE ONLY. LAT-P125's M5/M6 survived
         because every test read the key through the shared constant, so the
         constant and its readers moved in lockstep. The suite writes the key
         out as a literal; this mutant is why.
  M-INT  drops the int-key restoration. It is the one that CANNOT be caught at
         the HTTP layer — FastAPI stringifies int dict keys too, so a hit and a
         miss ship byte-identical bytes either way. Only the object-equality
         assertion sees it. #1587's class.
  M-GATE moves the `> 1 book` guard back to where it was. The DISTINCT used to
         gate whether the breakdown was COMPUTED; now it gates whether it is
         ATTACHED. Get that wrong and single-book markets grow a field.

🔴 TWO SURVIVORS ON THE FIRST RUN, AND THE FIXTURE WAS THE BUG — RECORDED HERE
BECAUSE THE NEXT BATTERY WILL MAKE THE SAME MISTAKE. The suite's rows all
carried one identical FRESH timestamp, one row per bookmaker. That made two
properties untestable at once: `stale` is False whether it is computed or
hard-coded when nothing is old, and the "a newer row replaces the kept one"
branch in `_get_source_breakdown` never runs when each bookmaker has one row.
The fixture now spans three ages and gives two bookmakers two rows each.

An early form of M-CAPTURED nulled `captured_at` in the dict INITIALISER and
survived for a third reason worth writing down: it is an EQUIVALENT MUTANT. The
initialiser's value is immediately repaired by the `existing is None` arm of the
overwrite branch below it, so no fixture could ever kill it. It was replaced by
the mutation of the overwrite branch itself, which is observable, and by
M-CUTOFF, which attacks the same honesty property from the other side. A mutant
that cannot be killed is not a hole in the suite — but it must be shown to be
equivalent, not quietly deleted.

Mutations are applied to the real source file, the suite is run to completion,
and the file is restored — SERIALLY. Never concurrently, and never while another
pytest is in flight: `inspect.getsource` re-reads the file mid-run and a source
edit under a running suite produces phantom failures that read as real reds.

Both halves of every mutant are VERBATIM literals, never `\\n`-escaped ones.
`scan_mutation_residue.py` Pass B flags a file holding a REPLACEMENT whose
NEEDLE is absent, and an escaped needle is absent by construction.

Run:  python3 backend/scripts/evals/futures_detail_sources_cache_mutations.py
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
ROUTE = ROOT / "app" / "routes" / "futures.py"
SUITE = ROOT / "tests" / "integration" / "test_futures_detail_sources_cache_lat_p127.py"
CONTRACT = ROOT / "tests" / "integration" / "test_route_futures.py"

#: (id, description, old, new). `old` must appear EXACTLY once in ROUTE — a
#: mutation that matches zero or many places is a harness bug reported as such,
#: never counted as a kill.
MUTANTS: list[tuple[str, str, str, str]] = [
    (
        "M1",
        "never read the cache — every load pays the 189,312-row sort again",
        """        cached = redis.get(cache_key)
        if cached:""",
        """        cached = redis.get(cache_key)
        if False:""",
    ),
    (
        "M2",
        "never write the cache — the second load is as slow as the first",
        """    if redis is not None:
        try:
            redis.set(""",
        """    if False:
        try:
            redis.set(""",
    ),
    (
        "M-KEY",
        "respell the key ROUTE-SIDE ONLY (LAT-P125 M5/M6's survivor class)",
        """    return f"bainluck:futures:detail-sources:{market_id}\"""",
        """    return f"bainluck:futures:market-sources:{market_id}\"""",
    ),
    (
        "M-ID",
        "drop market_id from the key — every market serves market 1's sources",
        """    return f"bainluck:futures:detail-sources:{market_id}\"""",
        """    return "bainluck:futures:detail-sources\"""",
    ),
    (
        "M-TTL",
        "TTL to 4 hours — a staleness budget longer than the write cadence",
        """MARKET_SOURCES_TTL_S = 300""",
        """MARKET_SOURCES_TTL_S = 14400""",
    ),
    (
        "M-NOTTL",
        "forget the expiry — the entry never refreshes",
        """                ex=MARKET_SOURCES_TTL_S,""",
        """                ex=None,""",
    ),
    (
        "M-INT",
        "skip the int-key restore — invisible over HTTP, wrong in process",
        """                _restore_source_breakdown(payload["source_breakdown"]),""",
        """                payload["source_breakdown"],""",
    ),
    (
        "M-GATE",
        "attach source_breakdown to single-book markets too",
        """    if len(bookmakers) > 1 and source_breakdown:""",
        """    if source_breakdown:""",
    ),
    (
        "M-ORDER",
        "reverse the derived bookmaker order — no longer ORDER BY bookmaker",
        """    bookmakers = [s["source"] for s in source_breakdown]""",
        """    bookmakers = [s["source"] for s in reversed(source_breakdown)]""",
    ),
    (
        "M-DEDUP",
        "derive bookmakers from the raw rows, re-admitting duplicates",
        """    bookmakers = [s["source"] for s in source_breakdown]""",
        """    bookmakers = [s["source"] for s in source_breakdown] * 2""",
    ),
    (
        "M-EMPTY",
        "run the scan for outcome-less markets — a pointless query and key",
        """    if outcome_ids:
        bookmakers, source_breakdown = await _load_market_sources(
            db, market_id, outcome_ids
        )""",
        """    if True:
        bookmakers, source_breakdown = await _load_market_sources(
            db, market_id, outcome_ids
        )""",
    ),
    (
        "M-REDIS",
        "let a dead Redis 500 the page instead of degrading to a query",
        """    except Exception:
        logger.debug("futures detail source cache read failed", exc_info=True)""",
        """    except Exception:
        raise""",
    ),
    (
        "M-SETRAISE",
        "let a failing cache WRITE take down a response that was already built",
        """        except Exception:
            logger.debug("futures detail source cache write failed", exc_info=True)""",
        """        except Exception:
            raise""",
    ),
    (
        "M-STALE",
        "hard-code stale=False — the cache could then lie about its own age",
        """                "stale": is_stale,""",
        """                "stale": False,""",
    ),
    (
        "M-CAPTURED",
        "drop the newest captured_at — a cached row then reports a stale time",
        """            by_bookmaker[bookmaker]["captured_at"] = captured_at.isoformat()""",
        """            by_bookmaker[bookmaker]["captured_at"] = None""",
    ),
    (
        "M-CUTOFF",
        "widen the staleness window to a century — nothing is ever stale",
        """SOURCE_STALENESS_DAYS = 7""",
        """SOURCE_STALENESS_DAYS = 36500""",
    ),
    (
        "M-MUTATE",
        "restore in place — the caller's cached dict gets rewritten under it",
        """    restored = []
    for row in rows:
        row = dict(row)""",
        """    restored = []
    for row in rows:
        pass""",
    ),
]


def _run_suite() -> int:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(SUITE),
            str(CONTRACT),
            "-q",
            "--no-header",
            "-x",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    ).returncode


def main() -> int:
    with guarded_targets(
        [ROUTE],
        "/tmp/lat_p127_futures_detail_sources_guard_backups",
        "futures_detail_sources_cache",
    ):
        return _main()


def _main() -> int:
    original = ROUTE.read_text()

    print(f"denominator: {len(MUTANTS)} mutants queued against {ROUTE.name}")
    baseline = _run_suite()
    if baseline != 0:
        print(
            f"HARNESS FAILURE: the unmutated suite exits {baseline}, not 0. "
            "Nothing below is a verdict."
        )
        return 2
    print("baseline: suite GREEN on the unmutated tree\n")

    killed, survived, broken = [], [], []
    try:
        for mid, desc, old, new in MUTANTS:
            n = original.count(old)
            if n != 1:
                broken.append((mid, f"anchor matched {n} times, expected exactly 1"))
                print(
                    f"{mid:11} HARNESS  {desc}\n"
                    f"            anchor matched {n} times — not a verdict"
                )
                continue
            mutated = original.replace(old, new, 1)
            if mutated == original:
                broken.append((mid, "replacement is a no-op — NOT APPLIED"))
                print(f"{mid:11} HARNESS  {desc}\n            NOT APPLIED")
                continue
            ROUTE.write_text(mutated)
            # Prove the mutation is actually on disk before believing its result:
            # a mutant that failed to apply reports a green suite as a survivor.
            if ROUTE.read_text() != mutated:
                ROUTE.write_text(original)
                broken.append((mid, "write-back verification failed"))
                print(f"{mid:11} HARNESS  {desc}\n            NOT APPLIED on disk")
                continue
            rc = _run_suite()
            ROUTE.write_text(original)  # restore before anything else runs
            if rc == 0:
                survived.append((mid, desc))
                print(f"{mid:11} SURVIVED {desc}")
            elif rc == 1:
                killed.append(mid)
                print(f"{mid:11} killed   {desc}")
            else:
                broken.append((mid, f"pytest exit {rc}"))
                print(
                    f"{mid:11} HARNESS  {desc}\n"
                    f"            pytest exit {rc} — the gate never ran"
                )
    finally:
        ROUTE.write_text(original)

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
