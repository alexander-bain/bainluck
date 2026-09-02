"""LAT-P111 — RED-proof for `tests/test_search_futures_tier_split.py`.

A green guard suite proves the code passes it. It does NOT prove the suite would
notice if the code broke — and for this change that second property is the whole
point, because the failure mode is a page that is quietly missing a row and
still returns HTTP 200. LAT-P002 shipped exactly that and survived a full deploy
verification.

So each mutant below breaks the tier split in one specific way and the harness
demands the oracle FAIL. A survivor is a hole in the suite, reported as such.

NOTHING ON DISK IS MODIFIED. `_fetch_futures_window`'s source is mutated as a
STRING and `exec`'d into a throwaway function whose `__globals__` are the real
`app.routes.events` module dict — so the mutant sees the same constants and the
same `_apply_search_statement_timeout` the test monkeypatches, while the file in
the tree is never touched. This is the shape `tests/test_mutation_guard.py`
names as preferred, and it is immune by construction to the SIGTERM-leaves-a-
mutant-behind failure that `guarded_targets` exists to catch: there is no
`write_text` and no `copy2` here, so there is nothing to restore.

THE HARNESS IS ALSO A PYTEST PLUGIN. That is not a trick, it is what avoids the
disk write: `pytest -p search_tier_split_mutations` re-imports this module inside
the child, and `pytest_configure` swaps in the mutant named by `$LATP111_MUTANT`
BEFORE collection imports the test module. Without the env var it is inert, so
the plugin cannot affect a normal run.

Usage:  python3 scripts/evals/search_tier_split_mutations.py
Exit 0 = every mutant killed. Exit 1 = at least one survived.
"""

from __future__ import annotations

import inspect
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[1]
ORACLE = "tests/test_search_futures_tier_split.py"

#: Where every needle below is supposed to live. Declared even though this
#: harness never writes to disk, because `scan_mutation_residue.py`'s Pass A is
#: not only a residue check — it asserts each needle is still PRESENT in its
#: target, which is how a mutant that has quietly stopped aiming at anything
#: gets caught. A harness whose needles have drifted reports 8/8 killed while
#: testing nothing.
TARGET = BACKEND / "app/routes/events.py"

#: (id, needle, replacement, what a survivor would mean)
MUTANTS: list[dict[str, str]] = [
    {
        "id": "M1-boundary-off-by-one",
        "needle": "if len(tier1_rows) >= _SEARCH_FUTURES_WINDOW:",
        "replacement": "if len(tier1_rows) > _SEARCH_FUTURES_WINDOW:",
        "why": "the skip never fires, because the tier<=1 query is itself "
        "LIMITed to the window and can never RETURN more than it. The "
        "whole saving is silently off and every test still sees a "
        "correct page.",
    },
    {
        "id": "M2-always-skip",
        "needle": "if len(tier1_rows) >= _SEARCH_FUTURES_WINDOW:",
        "replacement": "if True:",
        "why": "outcome-only recall is DELETED. `masters winner`-shaped "
        "queries lose their answer while the response stays a 200.",
    },
    {
        "id": "M3-never-skip",
        "needle": "if len(tier1_rows) >= _SEARCH_FUTURES_WINDOW:",
        "replacement": "if False:",
        "why": "the no-op 'fix' — every page is still correct, and the 805 ms "
        "is still paid. This is the mutant an identity-only suite "
        "cannot kill, which is why the absence assertions exist.",
    },
    {
        "id": "M4-no-dedup",
        "needle": "        if m.id in seen:\n            continue",
        "replacement": "        if False:\n            continue",
        "why": "a market matching BOTH arms is rendered twice on the page.",
    },
    {
        "id": "M5-outcome-rows-reversed",
        "needle": "for m in outcome_rows:",
        "replacement": "for m in list(outcome_rows)[::-1]:",
        "why": "tier-2 rows arrive in the wrong order, so the split page "
        "diverges from the unsplit one below the tier boundary.",
    },
    {
        "id": "M6-no-rearm",
        "needle": "    await _apply_search_statement_timeout(db, deadline)",
        "replacement": "    pass",
        "why": "the EXPENSIVE half of the stage inherits a bound sized for the "
        "cheap half — the exact defect LAT-P005's re-arm was added for.",
    },
    {
        "id": "M7-absent-reported-as-skipped",
        "needle": 'return tier1_rows, "absent"',
        "replacement": 'return tier1_rows, "skipped"',
        "why": "the post-deploy check reads this field. A query that never had "
        "an outcome arm would be counted as a saving this change made.",
    },
    {
        "id": "M8-window-cap-removed",
        "needle": "        if len(merged) >= _SEARCH_FUTURES_WINDOW:\n            break",
        "replacement": "        if False:\n            break",
        "why": "the window is the page's only dedup headroom (LAT-P038); "
        "overfilling it changes what the refill path believes.",
    },
]


def anchor_scope_text() -> str:
    """The text this harness counts its anchors in — ONE function, not the file.

    #2391. `scan_mutation_residue.py` graded these needles against the whole of
    `app/routes/events.py` and reported `M6-no-rearm` as matching twice, i.e. as
    a mutant that could never run. It runs and it is KILLED: the second match is
    in a different function, and this harness never looks there. The scan was
    right about the substring and wrong about the DENOMINATOR.

    So the scope is published rather than described. The scan calls this and
    `_mutate` uses it, which makes the two counts the same expression — they
    cannot drift into disagreeing again the way a written-down claim can.
    """
    import app.routes.events as E

    return inspect.getsource(E._fetch_futures_window)


def _mutate(mutant: dict) -> object:
    """Build the mutated `_fetch_futures_window`, in memory."""
    import app.routes.events as E

    src = anchor_scope_text()
    if src.count(mutant["needle"]) != 1:
        raise SystemExit(
            f"HARNESS: needle for {mutant['id']} matched "
            f"{src.count(mutant['needle'])} times, expected exactly 1 — the "
            "source moved and this mutant is no longer aimed at anything"
        )
    mutated = src.replace(mutant["needle"], mutant["replacement"])
    ns: dict = {}
    exec(compile(mutated, "<mutant>", "exec"), E.__dict__, ns)
    return ns["_fetch_futures_window"]


# --------------------------------------------------------------------------
# pytest plugin half — active only when $LATP111_MUTANT is set.
# --------------------------------------------------------------------------
def pytest_configure(config):  # noqa: D103 - pytest hook
    mid = os.environ.get("LATP111_MUTANT")
    if not mid:
        return
    mutant = next((m for m in MUTANTS if m["id"] == mid), None)
    if mutant is None:
        raise SystemExit(f"HARNESS: unknown mutant {mid!r}")
    import app.routes.events as E

    E._fetch_futures_window = _mutate(mutant)


# --------------------------------------------------------------------------
# Driver half.
# --------------------------------------------------------------------------
def main() -> int:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(HERE) + os.pathsep + env.get("PYTHONPATH", "")

    print(f"LAT-P111 mutation run — oracle: {ORACLE}")
    print(f"{len(MUTANTS)} mutants\n")

    # A green baseline first: if the oracle is red before any mutation, every
    # "kill" below is the baseline failing and the run means nothing.
    base = subprocess.run(
        [sys.executable, "-m", "pytest", ORACLE, "-q"],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
    )
    if base.returncode != 0:
        print(f"HARNESS: baseline oracle is NOT green (exit {base.returncode}).")
        print(base.stdout[-2000:])
        return 2
    print("baseline: GREEN (exit 0)\n")

    survivors, harness_errors = [], []
    for m in MUTANTS:
        env["LATP111_MUTANT"] = m["id"]
        r = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                ORACLE,
                "-x",
                "-q",
                "-p",
                "search_tier_split_mutations",
            ],
            cwd=BACKEND,
            env=env,
            capture_output=True,
            text=True,
        )
        # Read the exit code BY VALUE (gotcha #124): 1 is a RESULT. Anything
        # else is a story about the harness and is never counted as a kill.
        if r.returncode == 1:
            verdict = "KILLED"
        elif r.returncode == 0:
            verdict = "SURVIVED"
            survivors.append(m)
        else:
            verdict = f"HARNESS (exit {r.returncode})"
            harness_errors.append((m, r))
        print(f"  {m['id']:<34} {verdict}")

    print()
    for m, r in harness_errors:
        print(f"--- {m['id']} harness output ---")
        print((r.stdout + r.stderr)[-1500:])
    for m in survivors:
        print(f"SURVIVOR {m['id']}: {m['why']}")

    if harness_errors:
        print("\nCANNOT MEASURE — a mutant never ran. This is not a pass.")
        return 2
    if survivors:
        print(f"\n{len(survivors)}/{len(MUTANTS)} SURVIVED — the oracle has holes.")
        return 1
    print(f"{len(MUTANTS)}/{len(MUTANTS)} killed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
