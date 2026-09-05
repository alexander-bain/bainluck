#!/usr/bin/env python3
"""Mutation battery for authority/024 — the flip switch and its floor (#2867).

Every guard this ship adds is attacked here by the defect it claims to catch,
and each attack names the ONE test that must go red. A guard no mutant can kill
is decoration.

Two of these attacks are the reason the battery exists rather than the tests
alone. `MINIMUM_SCORED_DENOMINATOR = 1` is a floor set BELOW what the defect
produces — it reads like a guard, changes no test name, and never fires; the
same class as the dead guard the lane found on 9/4. And
`MINIMUM_SCORED_DENOMINATOR = 50` is the opposite mistake: a floor guessed
upward past NBA's measured 41-game population, pre-empting a ruling (#3071) that
is Alex's. A floor is only honest if BOTH directions are pinned.

Each mutation is applied to the real source file, PROVED to have applied by
re-reading the file (a battery that silently no-ops reports SURVIVED for a guard
that was never attacked), the pinned test is run, and the file is restored
byte-identically with the hash checked.

Run from `backend/`:  python3 scripts/authority_024_mutation_battery.py
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

AGREEMENT = "app/utils/authority_agreement.py"
SWITCH = "app/config/authority_by_sport.py"

TESTS = (
    "tests/test_authority_flip_switch.py",
    "tests/test_authority_governing_number.py",
    "tests/test_authority_agreement_endpoint.py",
)

FLIP = "tests/test_authority_flip_switch.py::"

#: (label, file, old, new, the test node that MUST go red)
MUTATIONS = [
    (
        # The whole floor removed. 100% of one game reads MEETS again, which is
        # seven days from a source-of-record flip decided by arithmetic.
        "floor-removed-entirely",
        AGREEMENT,
        "    if too_few:\n        return {\n            **block,\n            "
        '"gate": GATE_TOO_FEW,',
        "    if False:\n        return {\n            **block,\n            "
        '"gate": GATE_TOO_FEW,',
        FLIP + "test_one_game_at_100_pct_does_not_meet_the_bar",
    ),
    (
        # A floor set below what the defect produces never fires. This is the
        # mutant that would otherwise survive every test in the file: the
        # constant is still there, still named, still commented, and dead.
        "floor-set-below-the-defect",
        AGREEMENT,
        "MINIMUM_SCORED_DENOMINATOR = 2",
        "MINIMUM_SCORED_DENOMINATOR = 1",
        FLIP + "test_one_game_at_100_pct_does_not_meet_the_bar",
    ),
    (
        # And the other direction: a floor guessed upward is an answer to #3071
        # that Alex has not given, and it silently stops NBA's clock.
        "floor-guessed-past-the-measured-population",
        AGREEMENT,
        "MINIMUM_SCORED_DENOMINATOR = 2",
        "MINIMUM_SCORED_DENOMINATOR = 50",
        FLIP + "test_todays_real_nba_and_nhl_populations_still_clear_the_floor",
    ),
    (
        # Off by one at the floor's own boundary, which is a whole sport's
        # two-game days silently unscored.
        "floor-inclusive-at-its-own-boundary",
        AGREEMENT,
        "if denominators[name] < MINIMUM_SCORED_DENOMINATOR",
        "if denominators[name] <= MINIMUM_SCORED_DENOMINATOR",
        "tests/test_authority_governing_number.py::"
        "test_the_ledger_line_carries_the_verdict_so_the_bus_never_picks_a_number",
    ),
    (
        # A too-small day filed as a disagreement. Both are "did not advance"
        # and only one of them resets seven days of real agreement.
        "too-few-collapsed-into-below",
        AGREEMENT,
        'GATES_CARRY_STREAK = frozenset({GATE_NO_SCORE, GATE_TOO_FEW, GATE_PENDING})',
        'GATES_CARRY_STREAK = frozenset({GATE_NO_SCORE, GATE_PENDING})',
        FLIP
        + "test_an_unscorable_day_carries_the_streak_rather_than_resetting_it"
        + "[TOO-FEW-TO-SCORE]",
    ),
    (
        # The two identity numbers sharing one denominator. They differ by
        # exactly the StatPal-only games, which is the entire reason the row
        # carries two numbers instead of one.
        "both-numbers-scored-over-the-union",
        AGREEMENT,
        '    "ours_covered_pct": lambda i: int(i["both"]) + int(i["ours_only"]),',
        '    "ours_covered_pct": lambda i: int(i["both"]) + int(i["statpal_only"])'
        ' + int(i["ours_only"]),',
        FLIP + "test_the_two_denominators_are_not_the_same_number",
    ),
    (
        # A governing number with no stated denominator waved through on a
        # guessed one — D55's silent pass, in the one place it decides a flip.
        "unnamed-denominator-guessed-instead-of-refused",
        AGREEMENT,
        "    build = IDENTITY_DENOMINATORS.get(name)\n    if build is None:\n        return None",
        "    build = IDENTITY_DENOMINATORS.get(name)\n    if build is None:\n        return 999",
        FLIP + "test_an_unteachable_governing_number_scores_nothing_rather_than_meeting",
    ),
    (
        # The ledger line back to `covers=100.0%` with no population. This is
        # the line a bus operator reads every morning.
        "ledger-token-drops-the-denominator",
        AGREEMENT,
        "f\"{name}={governing['values'][name]}%/{denominators.get(name, '?')}\"",
        "f\"{name}={governing['values'][name]}%\"",
        FLIP + "test_the_ledger_line_prints_the_denominator_beside_the_percentage",
    ),
    (
        # A failed read resetting the streak. READ-FAILED is not a gate state,
        # so a counter that only knows gate states throws away six good days the
        # first morning StatPal 500s — spec rule 6, gotcha #53.
        "read-failed-resets-the-streak",
        AGREEMENT,
        "    carried = GATES_CARRY_STREAK | {READ_FAILED}",
        "    carried = GATES_CARRY_STREAK",
        FLIP
        + "test_an_unscorable_day_carries_the_streak_rather_than_resetting_it"
        + "[READ-FAILED]",
    ),
    (
        # "Carried" read as "counted": six good days and a quiet Tuesday
        # manufacturing the seventh.
        "a-carried-day-counts-as-agreement",
        AGREEMENT,
        "        elif gate in carried:\n            continue",
        "        elif gate in carried:\n            streak += 1",
        FLIP + "test_a_carried_day_cannot_manufacture_a_seventh",
    ),
    (
        # The streak as the best run rather than the run it ends on. A sport
        # that agreed for six days in July would flip in September.
        "streak-is-the-best-run-not-the-tail",
        AGREEMENT,
        "        else:\n            break\n    return streak",
        "        else:\n            continue\n    return streak",
        FLIP + "test_the_streak_is_the_tail_not_the_best_run",
    ),
    (
        # A fifth gate state that the payload's opening sentence never mentions.
        # This mutant is the point of repairing that guard: it survived the
        # hardcoded four-name version of the same test.
        "summary-never-told-about-the-new-state",
        AGREEMENT,
        'f"`{GATE_NO_SCORE}` (nothing to divide by), `{GATE_TOO_FEW}` (a denominator "',
        'f"`{GATE_NO_SCORE}` (nothing to divide by), `` (a denominator "',
        "tests/test_authority_agreement_endpoint.py::"
        "test_the_summary_names_every_gate_state",
    ),
    (
        # Off by one at the seven-day boundary — a week of waiting that looks
        # exactly like a sport that has not qualified.
        "seventh-day-does-not-count",
        SWITCH,
        "    if streak < FLIP_STREAK_DAYS:",
        "    if streak <= FLIP_STREAK_DAYS:",
        FLIP + "test_seven_days_permits_the_measured_half_and_says_the_other_half_is_alex",
    ),
    (
        # MLB waited on instead of ruled on. Ten perfect days do not move a
        # sport with no governing number, and a refusal that says "not yet"
        # instead of "this needs a ruling" is how 9/4 was spent.
        "no-governing-number-answered-as-a-wait",
        SWITCH,
        "    if not GOVERNING_IDENTITY_NUMBERS.get(sport_key):",
        "    if False and not GOVERNING_IDENTITY_NUMBERS.get(sport_key):",
        FLIP + "test_a_sport_with_no_governing_number_is_refused_as_a_ruling_not_a_wait",
    ),
    (
        # The switch thrown in a diff, with no evidence and no YOUR-TURN entry.
        "a-sport-flipped-without-its-evidence",
        SWITCH,
        '    "basketball_nba": ESPN,',
        '    "basketball_nba": STATPAL,',
        FLIP + "test_a_flipped_sport_must_carry_its_evidence",
    ),
    (
        # A typo in a sport key taking down a Celery task, or worse, resolving
        # to something other than the site's existing behaviour.
        "unknown-sport-key-raises",
        SWITCH,
        "    return AUTHORITY_BY_SPORT.get(sport_key, DEFAULT_AUTHORITY)",
        "    return AUTHORITY_BY_SPORT[sport_key]",
        FLIP + "test_an_unknown_sport_key_resolves_to_espn_and_does_not_raise",
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
    print(f"{len(TESTS)} suites green")

    killed: list[str] = []
    survived: list[str] = []
    for label, rel, old, new, test in MUTATIONS:
        path = REPO / rel
        original = path.read_text()
        before = hashlib.sha256(original.encode()).hexdigest()
        if original.count(old) != 1:
            print(
                f"  {label}: ANCHOR NOT UNIQUE ({original.count(old)} matches) — abort"
            )
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
        print(
            f"  {label}: {'KILLED' if code != 0 else 'SURVIVED'} (exit {code}) via {test}"
        )

    print(f"\n{len(killed)}/{len(MUTATIONS)} killed, {len(survived)} survived")
    if survived:
        print("SURVIVED:", ", ".join(survived))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
