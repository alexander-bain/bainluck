#!/usr/bin/env python3
"""Mutation battery for authority/022 — the ours-only horizon mirror (#2867).

Every guard added by this ship is attacked here by the defect it claims to
catch, and each attack names the ONE test that must go red. A guard that no
mutant can kill is decoration, and the mirror is one keystroke from a defect
nobody would see: both splits take (misses, span_source), and swapping the
second argument produces four buckets that still sum correctly and are both
wrong.

Each mutation is applied to the real source file, PROVED to have applied by
re-reading the file (a battery that silently no-ops reports SURVIVED for a
guard that was never attacked), the pinned test is run, and the file is
restored byte-identically with the hash checked.

Run from `backend/`:  python3 scripts/authority_022_mutation_battery.py
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

AGREEMENT = "app/utils/authority_agreement.py"

TESTS = (
    "tests/test_authority_agreement.py",
    "tests/test_stamp_v1_agreement_row.py",
)

#: (label, file, old, new, the test node that MUST go red)
MUTATIONS = [
    (
        # The copy-paste. `real_rows` is the argument sitting right beside the
        # right one, and the statpal-side call two lines up uses it.
        "mirror-placed-against-our-own-span",
        AGREEMENT,
        "ours_horizon = _ours_only_by_horizon(ours_only, real_fixtures)",
        "ours_horizon = _ours_only_by_horizon(ours_only, real_rows)",
        "tests/test_authority_agreement.py::"
        "test_the_two_splits_measure_against_opposite_spans_in_one_pass",
    ),
    (
        # Spec rule 5 in reverse: a TBD bracket entry six months out silently
        # widening the span, so a game past StatPal's window reads as a
        # disagreement inside it.
        "span-drawn-before-the-exclusions",
        AGREEMENT,
        "ours_horizon = _ours_only_by_horizon(ours_only, real_fixtures)",
        "ours_horizon = _ours_only_by_horizon(ours_only, fixtures)",
        "tests/test_authority_agreement.py::"
        "test_a_placeholder_fixture_cannot_widen_the_span_it_is_excluded_from",
    ),
    (
        # An empty span reported as an empty split — the claim that every game
        # we hold falls inside a window that does not exist.
        "no-span-reports-zeros-instead-of-unplaceable",
        AGREEMENT,
        '        split["unplaceable"] = len(misses)\n        return split',
        '        return split',
        "tests/test_authority_agreement.py::"
        "test_a_read_with_no_timed_fixture_places_nothing_beyond_statpals_last",
    ),
    (
        # A row with no kickoff quietly counted as a disagreement.
        "untimed-miss-falls-through-to-inside",
        AGREEMENT,
        "        if m.start is None:\n"
        '            split["unplaceable"] += 1\n'
        "        elif m.start < first:\n"
        "            split[before] += 1\n"
        "        elif m.start > last:",
        "        if m.start is not None and m.start < first:\n"
        "            split[before] += 1\n"
        "        elif m.start is not None and m.start > last:",
        "tests/test_authority_agreement.py::"
        "test_an_untimed_row_of_ours_is_unplaceable_and_not_quietly_inside",
    ),
    (
        # The one that would clear the bar on a sport nobody measured: the
        # split subtracted from the governing number instead of reported
        # beside it.
        "horizon-subtracted-from-the-governing-number",
        AGREEMENT,
        '"ours_covered_pct": _pct(both, both + ours_only),',
        '"ours_covered_pct": _pct(\n'
        '            both, both + ours_only - ours_horizon["beyond_statpal_last"]\n'
        "        ),",
        "tests/test_authority_agreement.py::"
        "test_the_mirror_is_reported_beside_the_governing_number_never_inside_it",
    ),
    (
        # The finding bucket emptied into the harmless one — the shape that
        # would let an ingestion gap read as StatPal's horizon.
        "a-miss-inside-the-window-counted-as-beyond-it",
        AGREEMENT,
        "        elif m.start > last:\n            split[beyond] += 1",
        "        elif m.start >= first:\n            split[beyond] += 1",
        "tests/test_authority_agreement.py::"
        "test_a_game_of_ours_inside_statpals_window_is_the_finding",
    ),
]


def _purge_pycache() -> None:
    for cache in REPO.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)


def _run(test: str) -> int:
    return subprocess.run(
        [sys.executable, "-m", "pytest", test, "-q", "--no-header", "-x"],
        cwd=REPO,
        capture_output=True,
        text=True,
    ).returncode


def main() -> int:
    print("baseline:", end=" ", flush=True)
    _purge_pycache()
    for test in TESTS:
        code = _run(test)
        if code != 0:
            print(f"\nBASELINE RED on {test} (exit {code}) — battery aborted")
            return 2
    print("both suites green")

    killed: list[str] = []
    survived: list[str] = []
    for label, rel, old, new, test in MUTATIONS:
        path = REPO / rel
        original = path.read_text()
        before = hashlib.sha256(original.encode()).hexdigest()
        if original.count(old) != 1:
            print(f"  {label}: ANCHOR NOT UNIQUE ({original.count(old)} matches) — abort")
            return 3
        path.write_text(original.replace(old, new, 1))
        applied = path.read_text()
        assert new in applied, f"{label}: replacement text absent"
        assert old not in applied, f"{label}: mutation did not apply"
        _purge_pycache()
        code = _run(test)
        path.write_text(original)
        assert (
            hashlib.sha256(path.read_text().encode()).hexdigest() == before
        ), f"{label}: restore was not byte-identical"
        _purge_pycache()
        (killed if code != 0 else survived).append(label)
        print(f"  {label}: {'KILLED' if code != 0 else 'SURVIVED'} (exit {code}) via {test}")

    print(f"\n{len(killed)}/{len(MUTATIONS)} killed, {len(survived)} survived")
    if survived:
        print("SURVIVED:", ", ".join(survived))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
