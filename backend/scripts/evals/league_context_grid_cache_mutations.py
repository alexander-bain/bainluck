#!/usr/bin/env python3
"""LAT-P128 mutation battery for the event page's league-context grid read.

A guard suite that passes proves the code runs; it does not prove the code is
PINNED. Each mutant below is a plausible way a later edit could put the defect
back — and this defect is unusually easy to put back, because the broken call
and the fixed call differ by one identifier. Both functions live in the same
module, take the same arguments and return the same shape. Only one of them
reads the Redis key that the hourly grid warm keeps populated.

If a mutant SURVIVES, the suite has a hole and the fix is to add the missing
assertion, never to delete the mutant (LAT-P115's M7 survived and the survivor
WAS the finding).

The battery is deliberately split across two attack surfaces, because the
defect has two doors:

  M-RAW           the IMPORT. Aliases the raw builder back over the cached
                  name, which is exactly the pre-LAT-P128 behaviour with the
                  call site untouched — the most honest possible restoration
                  of the bug.
  M-HOURS/-TOP/   the ARGUMENT LIST. `get_playoff_grid_cached` only consults
  -DEBUG          Redis when `not debug and hours is None and top == 10`.
                  Passing the wrapper a non-default triple leaves the import
                  correct, every other test green, and the cache bypassed —
                  a silent re-entry that no amount of staring at the import
                  line would catch.

M-SWALLOW attacks the other half of the change. The wrapper can RAISE where the
raw builder returned; narrowing the `except` lets a degraded side panel take the
whole event page down with it.

The remaining mutants (M-TREND, M-PROB, M-NORM) attack the transformation the
grid payload goes through on both the warm and cold paths. They are here because
the warm path is new: before this cycle every context was built from a live
Python object, and now most are built from a JSON round-trip. A mutant that only
one of those two paths can see would be a real hole.

Mutations are applied to the real source file, the suite is run to completion,
and the file is restored — SERIALLY. Never concurrently, and never while another
pytest is in flight: `inspect.getsource` re-reads the file mid-run and a source
edit under a running suite produces phantom failures that read as real reds.

Both halves of every mutant are VERBATIM literals, never `\\n`-escaped ones.
`scan_mutation_residue.py` Pass B flags a file holding a REPLACEMENT whose
NEEDLE is absent, and an escaped needle is absent by construction.

Run:  python3 backend/scripts/evals/league_context_grid_cache_mutations.py
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
SERVICE = ROOT / "app" / "services" / "league_context.py"
SUITE = ROOT / "tests" / "test_league_context_grid_cache_lat_p128.py"
CONTRACT = ROOT / "tests" / "test_league_context.py"

#: (id, description, old, new). `old` must appear EXACTLY once in SERVICE — a
#: mutation that matches zero or many places is a harness bug reported as such,
#: never counted as a kill.
MUTANTS: list[tuple[str, str, str, str]] = [
    (
        "M-RAW",
        "alias the RAW builder over the cached name — the defect itself, restored",
        """from app.routes.playoffs import get_playoff_grid_cached""",
        """from app.routes.playoffs import get_playoff_grid as get_playoff_grid_cached""",
    ),
    (
        "M-HOURS",
        "pass hours=24 — import stays right, cache_eligible goes false",
        """            hours=None,""",
        """            hours=24,""",
    ),
    (
        "M-TOP",
        "pass top=25 — same silent bypass through the argument list",
        """            top=10,""",
        """            top=25,""",
    ),
    (
        "M-DEBUG",
        "pass debug=True — the third term of cache_eligible",
        """            debug=False,""",
        """            debug=True,""",
    ),
    (
        "M-SWALLOW",
        "narrow the except — the wrapper's 503 escapes into the event page",
        """    except Exception as e:""",
        """    except (ValueError, KeyError) as e:""",
    ),
    (
        "M-TREND",
        "write the probability into changes_24h — warm and cold both wrong",
        """                trend = stage.get("trend_24h")
                if trend is not None:
                    changes[col_key] = trend""",
        """                trend = stage.get("trend_24h")
                if trend is not None:
                    changes[col_key] = prob""",
    ),
    (
        "M-PROB",
        "invert the stage probability guard — every cell drops out",
        """                prob = stage.get("probability")
                if prob is not None:""",
        """                prob = stage.get("probability")
                if prob is None:""",
    ),
    (
        "M-NORM",
        "skip name normalisation — the teams dict keys stop being lookup-able",
        """        norm_name = normalize_name(name)""",
        """        norm_name = name""",
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
        [SERVICE],
        "/tmp/lat_p128_league_context_grid_cache_guard_backups",
        "league_context_grid_cache",
    ):
        return _main()


def _main() -> int:
    original = SERVICE.read_text()

    print(f"denominator: {len(MUTANTS)} mutants queued against {SERVICE.name}")
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
            SERVICE.write_text(mutated)
            # Prove the mutation is actually on disk before believing its result:
            # a mutant that failed to apply reports a green suite as a survivor.
            if SERVICE.read_text() != mutated:
                SERVICE.write_text(original)
                broken.append((mid, "write-back verification failed"))
                print(f"{mid:11} HARNESS  {desc}\n            NOT APPLIED on disk")
                continue
            rc = _run_suite()
            SERVICE.write_text(original)  # restore before anything else runs
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
        SERVICE.write_text(original)

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
