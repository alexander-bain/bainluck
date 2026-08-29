#!/usr/bin/env python3
"""LAT-P135 — mutation battery for the fuzzy-fallback access-path guards.

WHAT THIS PROVES. `tests/test_typeahead_fuzzy_index_lat_p135.py` asserts six
properties over two route functions. Every one of them is a statement about
SOURCE SHAPE, and a shape assertion is exactly the kind that can be true for the
wrong reason — it passes if the string is present anywhere, including in a
comment, including in dead code, including in the wrong order. This battery
breaks each property on purpose and requires the guard to notice.

🔴 IT MUTATES STRINGS IN MEMORY AND NEVER TOUCHES DISK. `_mutation_guard.py`
records why that matters: a disk-mutating harness once left mutant M3 of
`typeahead_warmer_mutations` inside a real commit, because it was SIGTERM'd
between backup and restore and SIGTERM does not run `finally`. That harness
needs a signal-handling guard, a manifest and a recovery path. This one needs
none of it — there is no file to leave behind, so there is no residue to detect,
and `scan_mutation_residue.py` PASS A has nothing to verify here because nothing
is ever written. `_mutation_guard`'s own docstring says new harnesses should
prefer this design; this is one.

🔴 THE ORACLE IS THE GUARD ITSELF, IMPORTED, NOT REIMPLEMENTED. The checks come
from the test module via `CHECKS`. A battery that re-expressed the six properties
would be a second copy that drifts from the first, and the drift would show up as
a green battery over a broken guard — which is the failure this whole file exists
to prevent, rebuilt one level up.

🔴 THE BATTERY PULLS BOTH WAYS. `M8-PIN-LOWER` is declared `survives` and the run
FAILS if it is killed. A battery whose every mutant dies has not shown that the
guard is precise, only that it is loud: a check asserting `pin == 0.25` exactly
would kill M8 and would also reject a future, harmless widening. The invariant is
`pin <= boundary`, not `pin == 0.25`, and M8 is the mutant that tells those two
apart.

`M9-SEARCH-REVERT` mutates the OTHER surface. The defect being guarded is drift
between two twins, so a battery that only ever mutates `/typeahead` would leave
the twin's half of the contract unproven.

Exit codes (gotcha #54 — read the VALUE): 0 = every mutant behaved as declared.
1 = at least one mutant survived that should have died, or died that should have
survived, or could not be applied. Anything else is the harness failing.
"""

from __future__ import annotations

import os
import sys

#: Read by `scan_mutation_residue.py` (its `DISK_FREE` set), and VERIFIED there
#: rather than taken on trust — a name in that list can drift away from a harness
#: that later grows a real `write_text`, but this constant is edited by whoever
#: does the growing. Every mutant here is a source STRING held in memory and
#: handed straight to the oracle: no tracked file, no temp file, no backup, no
#: residue, nothing a SIGKILL can leave behind.
MUTATES_WORKING_TREE = False

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(os.path.dirname(_HERE))
for _p in (_BACKEND, os.path.join(_BACKEND, "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from test_typeahead_fuzzy_index_lat_p135 import (  # noqa: E402
    CHECKS,
    source_of,
)

#: The pin statement, per surface — `search_events` imports `text`, the typeahead
#: block imports it as `sql_text`. Spelled per surface rather than matched with a
#: wildcard so a mutation that cannot be applied says so instead of silently
#: matching nothing.
_PIN_CALL = {
    "search_events": 'text("SET LOCAL pg_trgm.similarity_threshold = 0.25")',
    "typeahead_search": 'sql_text("SET LOCAL pg_trgm.similarity_threshold = 0.25")',
}


def _drop(needle: str):
    def apply(code: str) -> str:
        return code.replace(needle, "", 1)

    return apply


def _swap(needle: str, replacement: str):
    def apply(code: str) -> str:
        return code.replace(needle, replacement, 1)

    return apply


def _move_pin_to_the_end(surface: str):
    """Relocate the pin BELOW the query it governs, preserving both statements.

    Deletion is a different mutant (M2). This one keeps the `SET LOCAL` present
    so that any check merely testing for its PRESENCE still passes — which is the
    point: only the ordering check can catch it.
    """

    def apply(code: str) -> str:
        pin = _PIN_CALL[surface]
        if pin not in code:
            return code
        return code.replace(pin, "", 1) + f"\n    await db.execute({pin})\n"

    return apply


#: label -> (surface, mutate, expectation). `survives` is a declaration, not a
#: tolerance: the run fails if such a mutant is killed.
MUTANTS: tuple[tuple[str, str, object, str], ...] = (
    (
        "M1-REVERT-OPERATOR",
        "typeahead_search",
        _drop('Team.name.op("%")(q),\n'),
        "killed",
    ),
    (
        "M2-DROP-PIN",
        "typeahead_search",
        _drop(_PIN_CALL["typeahead_search"]),
        "killed",
    ),
    (
        "M3-PIN-ABOVE-BOUNDARY",
        "typeahead_search",
        _swap(
            "SET LOCAL pg_trgm.similarity_threshold = 0.25",
            "SET LOCAL pg_trgm.similarity_threshold = 0.35",
        ),
        "killed",
    ),
    (
        "M4-PIN-AFTER-QUERY",
        "typeahead_search",
        _move_pin_to_the_end("typeahead_search"),
        "killed",
    ),
    (
        "M5-BOUNDARY-WIDENED",
        "typeahead_search",
        _swap(
            "func.similarity(Team.name, q) > 0.25",
            "func.similarity(Team.name, q) > 0.30",
        ),
        "killed",
    ),
    (
        "M6-DROP-RANKING",
        "typeahead_search",
        _drop("func.similarity(Team.name, q).desc()"),
        "killed",
    ),
    (
        "M7-DROP-BOUNDARY",
        "typeahead_search",
        _drop("func.similarity(Team.name, q) > 0.25,\n"),
        "killed",
    ),
    (
        "M8-PIN-LOWER",
        "typeahead_search",
        _swap(
            "SET LOCAL pg_trgm.similarity_threshold = 0.25",
            "SET LOCAL pg_trgm.similarity_threshold = 0.10",
        ),
        "survives",
    ),
    (
        "M9-SEARCH-REVERT",
        "search_events",
        _drop('Team.name.op("%")(q),\n'),
        "killed",
    ),
)


def main() -> int:
    baseline: dict[str, str] = {}
    for surface in ("search_events", "typeahead_search"):
        code = source_of(surface)
        problems = [c(code) for c in CHECKS]
        live = [p for p in problems if p is not None]
        baseline[surface] = code
        if live:
            print(f"HARNESS FAILURE — {surface} does not pass its own guards clean:")
            for problem in live:
                print(f"    {problem}")
            return 2

    print(f"# LAT-P135 fuzzy-index battery — {len(MUTANTS)} mutants, "
          f"{len(CHECKS)} checks, in-memory (no disk)")
    killed = survived = not_applied = wrong = 0

    for label, surface, mutate, expectation in MUTANTS:
        original = baseline[surface]
        mutated = mutate(original)
        if mutated == original:
            print(f"  {label:24} NOT-APPLIED   needle absent in {surface}")
            not_applied += 1
            continue

        caught_by = [c.__name__ for c in CHECKS if c(mutated) is not None]
        outcome = "killed" if caught_by else "survives"
        ok = outcome == expectation
        if outcome == "killed":
            killed += 1
        else:
            survived += 1
        if not ok:
            wrong += 1

        mark = "  " if ok else "<-- WRONG"
        detail = ", ".join(caught_by) if caught_by else "no check objected"
        print(
            f"  {label:24} {outcome:9} (declared {expectation:9}) {mark} "
            f"[{surface}] {detail}"
        )

    print()
    print(
        f"killed {killed} · survived {survived} · not-applied {not_applied} · "
        f"MISDECLARED {wrong}"
    )
    if wrong or not_applied:
        print("## VERDICT: FAIL — the guards do not bind the way this file claims")
        return 1
    print("## VERDICT: every mutant behaved as declared")
    return 0


if __name__ == "__main__":
    sys.exit(main())
