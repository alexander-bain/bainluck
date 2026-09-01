#!/usr/bin/env python3
"""Q499 mutation battery for the side-less-price drain.

A green suite proves the code runs; it does not prove the code is PINNED. Every
mutant here is a plausible later edit, and three of them read as improvements:

  M-SHORTCUT   derives the side by splitting the market name on " vs ". This is
               the single most likely future edit to this file — it removes a
               network call, it is obviously correct on a sample, and it is
               WRONG: it cannot tell which of the two names the price belongs
               to, which IS the defect the rail exists to repair. It is the same
               mutant Q492's own guard was written to catch, one layer out.
  M-CLOSED     drops `include_closed=True`. Reads as removing a redundant
               kwarg. Measured against production Gamma: the default read
               returns 7 of 40 legs in this cohort, so the drain would call 82%
               of its own population missing and report itself finished.
  M-VENUESILENT  turns a venue failure into an empty answer. Reads as
               resilience. It converts "we could not ask" into "there is
               nothing there" — gotcha #36 and #53 in one line.

🔴 AND ONE WHOSE FAILURE MODE IS NOT A WRONG NUMBER. M-CURSORJUMP advances the
cursor past the batch the venue refused to answer for. Every count stays
plausible, every terminal stays honest-looking, and the legs in that batch are
never examined again by any later call. A drain that silently skips is worse
than one that stops.

🔴 MANIFEST_DIR IS REPOINTED BEFORE THE GUARD IS USED (#2330). The shared guard
defaults to `/tmp/bainluck_mutation_guard`, which every worktree on this machine
also uses. A battery that crashes there can be "recovered" by the next lane's
run and restore ITS live files from THIS tree's backups. Both the manifest dir
and the backup dir below are worktree-unique, derived from the repo path.

Mutations are applied to the real source files, the suite runs to completion,
and the files are restored — SERIALLY. Never concurrently, and never while
another pytest is in flight: a source edit under a running suite produces
phantom failures that read as real reds. Run this in an rsync COPY of the
worktree when any other lane's suite might start.

Both halves of every mutant are VERBATIM literals, never `\\n`-escaped ones.
`scan_mutation_residue.py` Pass B flags a file holding a REPLACEMENT whose
NEEDLE is absent, and an escaped needle is absent by construction.

Run:  python3 backend/scripts/evals/polymarket_leg_label_drain_mutations.py
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
RAIL = ROOT / "app" / "tasks" / "repair_polymarket_leg_label.py"
SERVICE = ROOT / "app" / "services" / "polymarket_api.py"
SUITE = ROOT / "tests" / "test_repair_polymarket_leg_label_q499.py"

#: #2330 — see the module docstring. Derived from the worktree path so two
#: checkouts of this repo never share a manifest or a backup directory.
_TREE = hashlib.sha1(str(ROOT).encode()).hexdigest()[:10]
_mutation_guard.MANIFEST_DIR = pathlib.Path(f"/tmp/bainluck_mutation_guard_{_TREE}")
BACKUP_DIR = f"/tmp/q499_leg_label_backups_{_TREE}"

#: (id, target, description, old, new). `old` must appear EXACTLY once in the
#: target — a mutation that matches zero or many places is a harness bug
#: reported as such, never counted as a kill.
MUTANTS: list[tuple[str, pathlib.Path, str, str, str]] = [
    (
        "M-SHORTCUT",
        RAIL,
        "derive the side by splitting the market name — the Q492 mutant, one layer out",
        """                new_name = _leg_label(market, row["market_name"])""",
        """                new_name = row["market_name"].split(" vs ")[0].split(": ")[-1]""",
    ),
    (
        "M-CLOSED",
        RAIL,
        "drop include_closed — the venue answers for 7 of every 40 legs",
        """                condition_ids,
                batch_size=GAMMA_BATCH_SIZE,
                include_closed=True,
            ),""",
        """                condition_ids,
                batch_size=GAMMA_BATCH_SIZE,
            ),""",
    ),
    (
        "M-VENUESILENT",
        RAIL,
        "a venue failure becomes an empty answer — 'we could not ask' reads as 'nothing there'",
        """    except Exception as exc:  # noqa: BLE001 — 429/5xx re-raised as one verdict
        raise VenueUnavailable(f"{type(exc).__name__}: {exc}") from exc""",
        """    except Exception:  # noqa: BLE001
        return {}""",
    ),
    (
        "M-CURSORJUMP",
        RAIL,
        "advance the cursor past the batch the venue refused — a silent skip",
        """        resume_after = last_examined if last_examined is not None else (after_id or None)""",
        """        resume_after = stopped_before""",
    ),
    (
        "M-TOUCHSTAMP",
        RAIL,
        "bump last_updated — the repair forges a venue observation (#2024)",
        """               SET name = v.new_name""",
        """               SET name = v.new_name, last_updated = NOW()""",
    ),
    (
        "M-NOCAS",
        RAIL,
        "drop the compare-and-set — a concurrent re-ingest is clobbered",
        """             WHERE fo.id = v.id
               AND fo.name IS NOT DISTINCT FROM v.old_name""",
        """             WHERE fo.id = v.id""",
    ),
    (
        "M-NORETURNING",
        RAIL,
        "drop RETURNING — `relabelled` becomes a guess, `raced` becomes unobservable",
        """               AND fo.name IS NOT DISTINCT FROM v.old_name
         RETURNING fo.id""",
        """               AND fo.name IS NOT DISTINCT FROM v.old_name""",
    ),
    (
        "M-NOCOLLIDE",
        RAIL,
        "write both legs of a market that would take the same label",
        """        if len(names) != len(set(names)):""",
        """        if False:""",
    ),
    (
        "M-RACEDONFAIL",
        RAIL,
        "count `raced` for a write that never ran — N phantom re-ingests",
        """        if write_terminal is None:""",
        """        if True:""",
    ),
    (
        "M-COUNTAFTERFAIL",
        RAIL,
        "run the terminal count after a failed write — CERT-681's second cleanup",
        """    if write_terminal is None and count_budget >= REMAINING_COUNT_MIN_BUDGET_SECONDS:""",
        """    if count_budget >= REMAINING_COUNT_MIN_BUDGET_SECONDS:""",
    ),
    (
        "M-NOCLEANUPRESERVE",
        RAIL,
        "stop charging the cleanup to the reserve — the failure path goes unpaid",
        """POST_LOOP_NON_COUNT_RESERVE_SECONDS = 6.5""",
        """POST_LOOP_NON_COUNT_RESERVE_SECONDS = 3.5""",
    ),
    (
        "M-EXHAUSTED",
        RAIL,
        "report the scan exhausted on a full page — the tail is never drained",
        """        scan_exhausted = len(rows) < cap""",
        """        scan_exhausted = True""",
    ),
    (
        "M-CENSUSZERO",
        RAIL,
        "a census that could not look answers zero — which reads as `drained`",
        """        out["reason"] = f"census_query_failed: {type(exc).__name__}: {exc}"
        out["elapsed_s"] = round(time.monotonic() - started, 2)
        return out""",
        """        out["reason"] = f"census_query_failed: {type(exc).__name__}: {exc}"
        out["total_legs"] = 0
        out["elapsed_s"] = round(time.monotonic() - started, 2)
        return out""",
    ),
    (
        "M-WIDENCAP",
        RAIL,
        "let ?limit= raise the cap past the module constant — buys the H12",
        """    cap = min(int(limit), APPLY_LEG_CAP) if limit else APPLY_LEG_CAP""",
        """    cap = int(limit) if limit else APPLY_LEG_CAP""",
    ),
    (
        "M-DEADLINE",
        RAIL,
        "raise the loop deadline past what the wall can carry — H12 with no cursor",
        """DEADLINE_SECONDS = 10""",
        """DEADLINE_SECONDS = 25""",
    ),
    (
        "M-SERVICE-ONECALL",
        SERVICE,
        "honour include_closed in the signature but not on the wire",
        """        filters: list[list[tuple[str, str]]] = [[]]
        if include_closed:
            filters.append([("closed", "true")])""",
        """        filters: list[list[tuple[str, str]]] = [[]]""",
    ),
    (
        "M-SERVICE-CLOSEDONLY",
        SERVICE,
        "swap the union for the closed pass alone — the open half disappears",
        """        filters: list[list[tuple[str, str]]] = [[]]
        if include_closed:
            filters.append([("closed", "true")])""",
        """        filters: list[list[tuple[str, str]]] = [[]]
        if include_closed:
            filters = [[("closed", "true")]]""",
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
    with guarded_targets([RAIL, SERVICE], BACKUP_DIR, "polymarket_leg_label_drain"):
        return _main()


def _main() -> int:
    originals = {RAIL: RAIL.read_text(), SERVICE: SERVICE.read_text()}

    print(f"denominator: {len(MUTANTS)} mutants queued against 2 files")
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
                print(f"{mid:20} HARNESS  {desc}\n                     NOT APPLIED on disk")
                continue
            _purge_pycache()
            rc = _run_suite()
            target.write_text(original)  # restore before anything else runs
            # Byte-prove the REVERT, not just the mutation. A partial revert
            # leaves the next mutant measuring a tree nobody described.
            if target.read_text() != original:
                print(f"{mid:20} ABORT    revert did not apply to {target.name}")
                return 2
            _purge_pycache()
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
        for target, original in originals.items():
            target.write_text(original)

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


def _purge_pycache() -> None:
    """A stale `__pycache__` is how a reverted mutant keeps failing, and how an
    applied one keeps passing. Both directions read as a verdict."""
    import shutil

    for cache in (ROOT / "app").rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
