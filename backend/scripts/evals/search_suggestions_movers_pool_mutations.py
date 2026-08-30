#!/usr/bin/env python3
"""LAT-P151 (#2285) mutation battery for the search-suggestions movers pool.

A green suite proves the code runs; it does not prove the code is PINNED. Every
mutant below is a plausible later edit, and on this change most of them read as
CLEANUPS — which is the whole hazard. The pooled arm's correctness rests on
three things that look like accidents of authorship: a join that is absent, a
`> 0.02` that is not `>=`, and a status tuple with one element in it.

🔴 THE ONE THAT MATTERS MOST IS M-JOIN. `select(FuturesOutcome).where(market_id
IN pool)` with no `JOIN futures_markets` looks like an oversight — the status
filter is "missing", and adding the join back makes the query read the way every
other query in the file reads. It also returns the IDENTICAL rows, on every
fixture, forever: the pool already carries the status. What it does is put
`futures_markets` back ABOVE the sort, where `LIMIT 5` cannot bound it, and the
statement goes straight back to 146,425 shared blocks and an external merge to
disk. A suite of equivalence tests cannot see that. `test_the_pooled_arm_does_
not_join_the_market_table` can, and M-JOIN is the proof that it does.

🔴 AND THE ONE WHOSE FAILURE MODE IS SILENT DATA LOSS. M-NULLMAX drops
`max_movement_24h IS NOT NULL` from the shared pool. In PostgreSQL `ORDER BY x
DESC` is NULLS FIRST, so every market that has never had the column written
sorts to the TOP of the pool and evicts the real movers — on production that is
a pool of 400 nulls returning nothing at all, while the tests (SQLite sorts
nulls last on DESC) would keep passing on behaviour alone. It is killed here by
the SHAPE assertions, which is exactly why those assertions are not redundant
with the equivalence tests.

🔴 MANIFEST_DIR IS REPOINTED BEFORE THE GUARD IS USED (#2330). The shared guard
defaults to `/tmp/bainluck_mutation_guard`, which every worktree on this machine
also uses. A battery that crashes there can be "recovered" by the next lane's
run and restore ITS live files from THIS tree's backups. Both the manifest dir
and the backup dir below are worktree-unique, derived from the repo path, so a
concurrent latency/calibration/ux battery cannot collide with this one.

Mutations are applied to the real source files, the suite runs to completion,
and the files are restored — SERIALLY. Never concurrently, and never while
another pytest is in flight: a source edit under a running suite produces
phantom failures that read as real reds.

TWO TARGETS, AND THE SECOND ONE IS THE POINT OF THE REFACTOR. Half the mutants
land on `app/utils/movement_pool.py`, which `/api/futures/movers` also reads. The
oracle therefore includes that route's own equivalence gate: a mutation to the
shared bound must be killed by BOTH consumers, which is the property that makes
one home better than two spellings.

Both halves of every mutant are VERBATIM literals, never `\\n`-escaped ones.
`scan_mutation_residue.py` Pass B flags a file holding a REPLACEMENT whose
NEEDLE is absent, and an escaped needle is absent by construction.

Run:  python3 backend/scripts/evals/search_suggestions_movers_pool_mutations.py
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
ROUTE = ROOT / "app" / "routes" / "events.py"
POOL = ROOT / "app" / "utils" / "movement_pool.py"

SUITE = ROOT / "tests" / "test_search_suggestions_movers_pool_lat_p151.py"
#: The OTHER consumer of the shared bound. In the oracle because a mutation to
#: `movement_pool.py` that only this queue's suite catches would mean the two
#: surfaces are still independently guarded, which is the state the extraction
#: exists to end.
MOVERS_SUITE = ROOT / "tests" / "test_futures_movers_pool_bound.py"
COLD_SUITE = (
    ROOT / "tests" / "integration" / "test_route_search_suggestions_cold_p124.py"
)

#: #2330 — see the module docstring. Derived from the worktree path so two
#: checkouts of this repo never share a manifest or a backup directory.
_TREE = hashlib.sha1(str(ROOT).encode()).hexdigest()[:10]
_mutation_guard.MANIFEST_DIR = pathlib.Path(f"/tmp/bainluck_mutation_guard_{_TREE}")
BACKUP_DIR = f"/tmp/lat_p151_movers_pool_backups_{_TREE}"

#: (id, target, description, old, new). `old` must appear EXACTLY once in
#: `target` — a mutation that matches zero or many places is a harness bug
#: reported as such, never counted as a kill.
MUTANTS: list[tuple[str, pathlib.Path, str, str, str]] = [
    # ---------------------------------------------------------------- shape
    (
        "M-JOIN",
        ROUTE,
        "re-state the status filter as a join — identical rows, 1.14 GB back",
        """        query = select(FuturesOutcome).where(
            *conditions,
            FuturesOutcome.market_id.in_(""",
        """        query = select(FuturesOutcome).join(FuturesMarket).where(
            FuturesMarket.status.in_(_SUGGESTION_MOVERS_STATUSES),
            *conditions,
            FuturesOutcome.market_id.in_(""",
    ),
    (
        "M-INLINE",
        ROUTE,
        "section 3 stops calling the builder — the fix becomes unreachable",
        "        movers_q = _build_suggestion_movers_query(pooled=_SUGGESTION_MOVERS_POOLED)",
        """        movers_q = (
            select(FuturesOutcome)
            .join(FuturesMarket)
            .where(
                FuturesMarket.status == "open",
                FuturesOutcome.probability_change_24h.isnot(None),
                func.abs(FuturesOutcome.probability_change_24h) > 0.02,
            )
            .order_by(func.abs(FuturesOutcome.probability_change_24h).desc())
            .options(selectinload(FuturesOutcome.market))
            .limit(5)
        )""",
    ),
    (
        "M-FLAGPINNED",
        ROUTE,
        "hard-code `pooled=True` — the rollback flag stops being reachable",
        "        movers_q = _build_suggestion_movers_query(pooled=_SUGGESTION_MOVERS_POOLED)",
        "        movers_q = _build_suggestion_movers_query(pooled=True)",
    ),
    (
        "M-LEGACYPOOLED",
        ROUTE,
        "pool the legacy arm too — the oracle stops being an oracle",
        """        query = (
            select(FuturesOutcome)
            .join(FuturesMarket)
            .where(
                FuturesMarket.status.in_(_SUGGESTION_MOVERS_STATUSES),
                *conditions,
            )
        )""",
        """        query = select(FuturesOutcome).where(
            *conditions,
            FuturesOutcome.market_id.in_(
                market_pool_subquery(
                    pool_size=_SUGGESTION_MOVERS_POOL,
                    statuses=_SUGGESTION_MOVERS_STATUSES,
                )
            ),
        )""",
    ),
    # ----------------------------------------------------- what a person sees
    (
        "M-GTE",
        ROUTE,
        "`>= 0.02` instead of `> 0.02` — a flat market becomes a mover",
        "        func.abs(FuturesOutcome.probability_change_24h) > 0.02,\n    ]",
        "        func.abs(FuturesOutcome.probability_change_24h) >= 0.02,\n    ]",
    ),
    (
        "M-THRESHOLD",
        ROUTE,
        "loosen the threshold to 1% — more chips, different chips",
        "        func.abs(FuturesOutcome.probability_change_24h) > 0.02,\n    ]",
        "        func.abs(FuturesOutcome.probability_change_24h) > 0.01,\n    ]",
    ),
    (
        "M-SIGNED-FILTER",
        ROUTE,
        "drop `abs` from the filter — every faller disappears",
        "        func.abs(FuturesOutcome.probability_change_24h) > 0.02,\n    ]",
        "        FuturesOutcome.probability_change_24h > 0.02,\n    ]",
    ),
    (
        "M-SIGNED-ORDER",
        ROUTE,
        "drop `abs` from the ordering — -0.99 ranks below +0.03",
        "        query.order_by(func.abs(FuturesOutcome.probability_change_24h).desc())",
        "        query.order_by(FuturesOutcome.probability_change_24h.desc())",
    ),
    (
        "M-ASC",
        ROUTE,
        "ascending — the five SMALLEST movers, which still renders fine",
        "        query.order_by(func.abs(FuturesOutcome.probability_change_24h).desc())",
        "        query.order_by(func.abs(FuturesOutcome.probability_change_24h).asc())",
    ),
    (
        "M-STATUS-WIDEN",
        ROUTE,
        "adopt `/movers`' status list — a product change inside a perf queue",
        '_SUGGESTION_MOVERS_STATUSES = ("open",)',
        '_SUGGESTION_MOVERS_STATUSES = ("open", "active")',
    ),
    (
        "M-LIMIT",
        ROUTE,
        "ten movers instead of five — section 3 swallows the window",
        "_SUGGESTION_MOVERS_LIMIT = 5",
        "_SUGGESTION_MOVERS_LIMIT = 10",
    ),
    (
        "M-NO-NOTNULL",
        ROUTE,
        "drop the IS NOT NULL — invisible in behaviour, visible in the plan",
        "        FuturesOutcome.probability_change_24h.isnot(None),\n        func.abs(",
        "        func.abs(",
    ),
    # --------------------------------------------------------------- the pool
    (
        "M-POOL-BELOW-ASK",
        ROUTE,
        "shrink the pool under the ask — the answer silently truncates",
        "_SUGGESTION_MOVERS_POOL = 400",
        "_SUGGESTION_MOVERS_POOL = 3",
    ),
    (
        "M-POOL-DRIFT",
        ROUTE,
        "retune the pool to 40 — the atomic probes no longer cover it",
        "_SUGGESTION_MOVERS_POOL = 400",
        "_SUGGESTION_MOVERS_POOL = 40",
    ),
    (
        "M-FLAG-DEFAULT-OFF",
        ROUTE,
        "default the rollback flag to the SLOW arm — ships nothing",
        """_SUGGESTION_MOVERS_POOLED = os.getenv(
    "SEARCH_SUGGESTIONS_MOVERS_POOLED", "1"
).strip().lower() not in ("0", "false", "no")""",
        """_SUGGESTION_MOVERS_POOLED = os.getenv(
    "SEARCH_SUGGESTIONS_MOVERS_POOLED", "0"
).strip().lower() not in ("0", "false", "no")""",
    ),
    # ------------------------------------------------ the shared bound itself
    (
        "M-NULLMAX",
        POOL,
        "drop `max_movement_24h IS NOT NULL` — NULLS FIRST evicts every mover",
        """            FuturesMarket.status.in_(tuple(statuses)),
            FuturesMarket.max_movement_24h.isnot(None),""",
        """            FuturesMarket.status.in_(tuple(statuses)),""",
    ),
    (
        "M-POOL-ASC",
        POOL,
        "order the pool ascending — the QUIETEST markets become the pool",
        "        .order_by(FuturesMarket.max_movement_24h.desc())",
        "        .order_by(FuturesMarket.max_movement_24h.asc())",
    ),
    (
        "M-POOL-UNBOUNDED",
        POOL,
        "drop the LIMIT — correct answers, and the scan is back",
        """        .order_by(FuturesMarket.max_movement_24h.desc())
        .limit(pool_size)""",
        """        .order_by(FuturesMarket.max_movement_24h.desc())""",
    ),
    (
        "M-POOL-NO-STATUS",
        POOL,
        "drop the status filter — resolved markets crowd out live ones",
        """            FuturesMarket.status.in_(tuple(statuses)),
            FuturesMarket.max_movement_24h.isnot(None),""",
        """            FuturesMarket.max_movement_24h.isnot(None),""",
    ),
    (
        "M-POOL-WRONG-COLUMN",
        POOL,
        "select the movement instead of the id — `market_id IN (floats)`",
        "        select(FuturesMarket.id)",
        "        select(FuturesMarket.max_movement_24h)",
    ),
]


def _run_suite() -> int:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(SUITE),
            str(MOVERS_SUITE),
            str(COLD_SUITE),
            "-q",
            "--no-header",
            "-x",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    ).returncode


def main() -> int:
    with guarded_targets([ROUTE, POOL], BACKUP_DIR, "search_suggestions_movers_pool"):
        return _main()


def _main() -> int:
    originals = {ROUTE: ROUTE.read_text(), POOL: POOL.read_text()}

    print(
        f"denominator: {len(MUTANTS)} mutants queued against "
        f"{ROUTE.name} + {POOL.name}"
    )
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
        for mid, target, desc, old, new in MUTANTS:
            original = originals[target]
            n = original.count(old)
            if n != 1:
                broken.append((mid, f"anchor matched {n} times, expected exactly 1"))
                print(
                    f"{mid:20} HARNESS  {desc}\n"
                    f"                     anchor matched {n} times — not a verdict"
                )
                continue
            mutated = original.replace(old, new, 1)
            if mutated == original:
                broken.append((mid, "replacement is a no-op — NOT APPLIED"))
                print(f"{mid:20} HARNESS  {desc}\n                     NOT APPLIED")
                continue
            target.write_text(mutated)
            # Prove the mutation is actually on disk before believing its
            # result: one that failed to apply reports green as a survivor.
            if target.read_text() != mutated:
                target.write_text(original)
                broken.append((mid, "write-back verification failed"))
                print(
                    f"{mid:20} HARNESS  {desc}\n"
                    f"                     NOT APPLIED on disk"
                )
                continue
            rc = _run_suite()
            target.write_text(original)  # restore before anything else runs
            if rc == 0:
                survived.append((mid, desc))
                print(f"{mid:20} SURVIVED {desc}")
            elif rc == 1:
                killed.append(mid)
                print(f"{mid:20} killed   {desc}")
            else:
                broken.append((mid, f"pytest exit {rc}"))
                print(
                    f"{mid:20} HARNESS  {desc}\n"
                    f"                     pytest exit {rc} — the gate never ran"
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
