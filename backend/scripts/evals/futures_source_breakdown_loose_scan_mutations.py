#!/usr/bin/env python3
"""LAT-P148 (#2333) mutation battery for the market-page loose index scan.

A green suite proves the code runs; it does not prove the code is PINNED. Every
mutant below is a plausible later edit — and here that word is unusually
literal, because almost all of them read as IMPROVEMENTS. This statement is a
hand-written index skip scan, and every clause in it that looks decorative is
load-bearing. The battery exists to make sure the tests, not review attention,
are what stops those edits.

The three that matter most, because a careful engineer would make them:

  M-NOTNULL  adds ``AND s.captured_at IS NOT NULL``. The sibling module
             `app.utils.latest_observation` (LAT-P147) ADDS exactly this and
             documents it as load-bearing — so the mutation has a citation in
             the same repo. It is still wrong here: P147 replaces a ``max()``
             (which skips nulls) and this replaces a WINDOW function (which,
             like ``ORDER BY ... DESC``, is NULLS FIRST). Same predicate,
             opposite correctness, and `captured_at` is genuinely nullable on
             production. A guard that only knew "P147 does it" would pass it.
  M-NULLSLAST  adds ``NULLS LAST``. Reads as defensive; P147 measured it at 19x
             slower because it stops matching the index's own ordering.
  M-TIEBREAK adds ``, s.id DESC``. Reads as determinism. Same mechanism — the
             probe stops being a one-row backward read and becomes a Sort over
             the whole pair.

🔴 AND THE ONE WHOSE FAILURE MODE IS NOT A WRONG ANSWER. M-NOTERM drops the
recursive term's ``WHERE p.bookmaker IS NOT NULL``. The walk then asks for
``bookmaker > NULL`` forever. No fixture and no HTTP test would show a wrong
number; a web dyno would hang. It is in the battery because "the suite is green"
must not be able to mean "and nothing spins".

🔴 MANIFEST_DIR IS REPOINTED BEFORE THE GUARD IS USED (#2330). The shared guard
defaults to `/tmp/bainluck_mutation_guard`, which every worktree on this machine
also uses. A battery that crashes there can be "recovered" by the next lane's
run and restore ITS live files from THIS tree's backups. Both the manifest dir
and the backup dir below are worktree-unique, derived from the repo path, so a
concurrent latency/calibration/ux battery cannot collide with this one.

Mutations are applied to the real source file, the suite runs to completion, and
the file is restored — SERIALLY. Never concurrently, and never while another
pytest is in flight: a source edit under a running suite produces phantom
failures that read as real reds.

Both halves of every mutant are VERBATIM literals, never `\\n`-escaped ones.
`scan_mutation_residue.py` Pass B flags a file holding a REPLACEMENT whose
NEEDLE is absent, and an escaped needle is absent by construction.

Run:  python3 backend/scripts/evals/futures_source_breakdown_loose_scan_mutations.py
Exit: 0 = every mutant killed. 1 = at least one survived. Anything else is the
      harness failing, not a verdict (gotcha #54).
"""

from __future__ import annotations

import hashlib
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import _mutation_guard  # noqa: E402
from _mutation_guard import guarded_targets  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
ROUTE = ROOT / "app" / "routes" / "futures.py"
SUITE = ROOT / "tests" / "test_futures_source_breakdown_loose_scan_lat_p148.py"
CACHE_SUITE = (
    ROOT / "tests" / "integration" / "test_futures_detail_sources_cache_lat_p127.py"
)

#: #2330 — see the module docstring. Derived from the worktree path so two
#: checkouts of this repo never share a manifest or a backup directory.
_TREE = hashlib.sha1(str(ROOT).encode()).hexdigest()[:10]
_mutation_guard.MANIFEST_DIR = pathlib.Path(f"/tmp/bainluck_mutation_guard_{_TREE}")
BACKUP_DIR = f"/tmp/lat_p148_loose_scan_backups_{_TREE}"

#: (id, description, old, new). `old` must appear EXACTLY once in ROUTE — a
#: mutation that matches zero or many places is a harness bug reported as such,
#: never counted as a kill.
MUTANTS: list[tuple[str, str, str, str]] = [
    (
        "M-NOTNULL",
        "add `captured_at IS NOT NULL` — P147's call, inverted here",
        """                     WHERE s.outcome_id = p.outcome_id
                       AND s.bookmaker = p.bookmaker
                     ORDER BY s.captured_at DESC""",
        """                     WHERE s.outcome_id = p.outcome_id
                       AND s.bookmaker = p.bookmaker
                       AND s.captured_at IS NOT NULL
                     ORDER BY s.captured_at DESC""",
    ),
    (
        "M-NULLSLAST",
        "`NULLS LAST` — defensive-looking, 19x slower (P147)",
        """                     ORDER BY s.captured_at DESC
                     LIMIT 1""",
        """                     ORDER BY s.captured_at DESC NULLS LAST
                     LIMIT 1""",
    ),
    (
        "M-TIEBREAK",
        "`, s.id DESC` tiebreak — determinism that costs the index",
        """                     ORDER BY s.captured_at DESC
                     LIMIT 1""",
        """                     ORDER BY s.captured_at DESC, s.id DESC
                     LIMIT 1""",
    ),
    (
        "M-NOTERM",
        "drop the recursive terminator — the walk never ends",
        """                  FROM pairs p
                 WHERE p.bookmaker IS NOT NULL
            )""",
        """                  FROM pairs p
            )""",
    ),
    (
        "M-DESCSEED",
        "seed on the HIGHEST bookmaker — one source per outcome, silently",
        """                         WHERE s.outcome_id = o.outcome_id
                         ORDER BY s.bookmaker
                         LIMIT 1) AS bookmaker""",
        """                         WHERE s.outcome_id = o.outcome_id
                         ORDER BY s.bookmaker DESC
                         LIMIT 1) AS bookmaker""",
    ),
    (
        "M-DESCSTEP",
        "walk downwards from the seed — collapses to one source",
        """                           AND s.bookmaker > p.bookmaker
                         ORDER BY s.bookmaker""",
        """                           AND s.bookmaker > p.bookmaker
                         ORDER BY s.bookmaker DESC""",
    ),
    (
        "M-GTE",
        "`>=` instead of `>` — the walk stops advancing",
        "                           AND s.bookmaker > p.bookmaker",
        "                           AND s.bookmaker >= p.bookmaker",
    ),
    (
        "M-LIMIT2",
        "`LIMIT 2` in the LATERAL — no longer a top-1 seek",
        """                     ORDER BY s.captured_at DESC
                     LIMIT 1
                   ) AS latest""",
        """                     ORDER BY s.captured_at DESC
                     LIMIT 2
                   ) AS latest""",
    ),
    (
        "M-DOUBLECOLON",
        "`::integer[]` — asyncpg reads `::` as the start of a bind",
        "                  FROM unnest(CAST(:outcome_ids AS integer[])) AS o(outcome_id)",
        "                  FROM unnest(:outcome_ids::integer[]) AS o(outcome_id)",
    ),
    (
        "M-INTERPOLATE",
        "interpolate the ids instead of binding them",
        """        {"outcome_ids": list(outcome_ids)},
    )""",
        """        {"outcome_ids_unused": list(outcome_ids)},
    )""",
    ),
    (
        # 🔴 THIS MUTANT WAS REWRITTEN AFTER SURVIVING. Its first form prepended
        # a `-- restored --` COMMENT to the CTE and called that "the window
        # function is back". Nothing about the statement changed, so nothing
        # could kill it — it was not an equivalent mutant, it was a mutant that
        # did not mutate. Recorded because the failure is easy to repeat: a
        # mutant must reintroduce the DEFECT, not a label for it.
        "M-WINDOWBACK",
        "resolve the pair with a window function — answer-identical, scan-shaped",
        """                    SELECT s.probability, s.captured_at
                      FROM futures_odds_snapshots s
                     WHERE s.outcome_id = p.outcome_id
                       AND s.bookmaker = p.bookmaker
                     ORDER BY s.captured_at DESC
                     LIMIT 1""",
        """                    SELECT w.probability, w.captured_at FROM (
                        SELECT s.probability, s.captured_at,
                               row_number() OVER (
                                   ORDER BY s.captured_at DESC) AS rn
                          FROM futures_odds_snapshots s
                         WHERE s.outcome_id = p.outcome_id
                           AND s.bookmaker = p.bookmaker) w
                     WHERE w.rn = 1""",
    ),
    (
        "M-UNSORTED",
        "stop sorting sources by name",
        # 🔴 SINGLE-QUOTED ON PURPOSE. The needle contains `s["source"]`, and
        # spelling it in a double-quoted Python string makes it `s[\"source\"]`
        # in this FILE's text — so Pass B of `scan_mutation_residue.py` sees the
        # replacement present and the needle absent, and reports this harness as
        # residue. The module docstring warns about escaped literals; this line
        # is the one that got caught doing it, in the full suite rather than in
        # the standalone scan, because Pass B only reads CHANGED files and there
        # were none until the commit landed.
        '    return sorted(by_bookmaker.values(), key=lambda s: s["source"])',
        "    return list(by_bookmaker.values())",
    ),
    (
        "M-STALEOFF",
        "hard-code `stale: False` — muted sources render as live",
        """                "stale": is_stale,""",
        """                "stale": False,""",
    ),
    (
        "M-DROPNULL",
        "skip null-captured_at rows — the NULLS FIRST row disappears",
        """    for outcome_id, bookmaker, probability, captured_at in rows.all():
        if bookmaker not in by_bookmaker:""",
        """    for outcome_id, bookmaker, probability, captured_at in rows.all():
        if captured_at is None:
            continue
        if bookmaker not in by_bookmaker:""",
    ),
    (
        "M-CUTOFF",
        "grade staleness against a cutoff that can never fire",
        "    staleness_cutoff = datetime.now(timezone.utc) - timedelta(days=SOURCE_STALENESS_DAYS)",
        "    staleness_cutoff = datetime.now(timezone.utc) - timedelta(days=100000)",
    ),
    (
        "M-INTKEYS",
        "stringify the outcome keys — #1587's class at the source",
        """        by_bookmaker[bookmaker]["outcomes"][outcome_id] = round(""",
        """        by_bookmaker[bookmaker]["outcomes"][str(outcome_id)] = round(""",
    ),
]


def _run_suite() -> int:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(SUITE),
            str(CACHE_SUITE),
            "-q",
            "--no-header",
            "-x",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    ).returncode


def main() -> int:
    with guarded_targets([ROUTE], BACKUP_DIR, "futures_source_breakdown_loose_scan"):
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
                    f"{mid:14} HARNESS  {desc}\n"
                    f"               anchor matched {n} times — not a verdict"
                )
                continue
            mutated = original.replace(old, new, 1)
            if mutated == original:
                broken.append((mid, "replacement is a no-op — NOT APPLIED"))
                print(f"{mid:14} HARNESS  {desc}\n               NOT APPLIED")
                continue
            ROUTE.write_text(mutated)
            # Prove the mutation is actually on disk before believing its
            # result: one that failed to apply reports green as a survivor.
            if ROUTE.read_text() != mutated:
                ROUTE.write_text(original)
                broken.append((mid, "write-back verification failed"))
                print(f"{mid:14} HARNESS  {desc}\n               NOT APPLIED on disk")
                continue
            rc = _run_suite()
            ROUTE.write_text(original)  # restore before anything else runs
            if rc == 0:
                survived.append((mid, desc))
                print(f"{mid:14} SURVIVED {desc}")
            elif rc == 1:
                killed.append(mid)
                print(f"{mid:14} killed   {desc}")
            else:
                broken.append((mid, f"pytest exit {rc}"))
                print(
                    f"{mid:14} HARNESS  {desc}\n"
                    f"               pytest exit {rc} — the gate never ran"
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
