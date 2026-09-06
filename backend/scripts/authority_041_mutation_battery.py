"""Mutation battery for #3519 — `identity.ours_covered_in_span_pct`.

Each mutant is a single edit to production source that reproduces a real way the
in-span number could be wrong, paired with the ONE test node that must go red.
A mutant that survives means the guard names a behaviour nobody is holding.

Applied by string replacement and restored from the captured original — never
`git checkout --`, which eats uncommitted work in a shared tree. `__pycache__`
is cleared between mutants so a stale .pyc cannot serve the pre-mutation module.

    python3 scripts/authority_041_mutation_battery.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
TARGET = BACKEND / "app" / "utils" / "authority_agreement.py"
SUITE = "tests/test_authority_in_span_agreement_3519.py"

#: (name, why it matters, find, replace, the test node that must go red)
MUTANTS: list[tuple[str, str, str, str, str]] = [
    (
        "denominator-crossed-to-every-miss",
        "The bug itself: score the in-span question over ALL our misses, which "
        "is `ours_covered_pct` again and reads horizon, not agreement.",
        '_pct(both, both + ours_horizon["inside_statpal_span"])',
        "_pct(both, both + ours_only)",
        "test_the_in_span_number_is_scored_on_the_inside_bucket_and_not_on_every_miss",
    ),
    (
        "span-guard-dropped",
        "Divide anyway when StatPal published no timed fixture. The denominator "
        "collapses to `both` and the row reports a perfect score on no evidence.",
        """            _pct(both, both + ours_horizon["inside_statpal_span"])
            if statpal_has_span
            else None""",
        """            _pct(both, both + ours_horizon["inside_statpal_span"])""",
        "test_an_untimed_statpal_fixture_that_still_pairs_does_not_fake_a_span",
    ),
    (
        "empty-span-reported-as-a-span",
        "`timed_span` returns a degenerate span instead of `None`, so 'no window "
        "to be inside of' becomes 'this window', silently placing every miss.",
        """    starts = [s.start for s in side if s.start is not None]
    if not starts:
        return None
    return min(starts), max(starts)""",
        """    starts = [s.start for s in side if s.start is not None]
    if not starts:
        starts = [datetime.min.replace(tzinfo=timezone.utc)]
    return min(starts), max(starts)""",
        "test_timed_span_distinguishes_no_span_from_an_instantaneous_one",
    ),
    (
        "in-span-number-made-governing",
        "Ship it as a gate rather than a report. D63 is Alex's; a change that "
        "quietly scores a sport on this number must not pass CI silently.",
        '"basketball_nba": ("ours_covered_pct",),',
        '"basketball_nba": ("ours_covered_pct", "ours_covered_in_span_pct"),',
        "test_the_new_number_governs_no_sport_today",
    ),
    (
        "denominator-map-entry-crossed",
        "The published percentage and the population it claims disagree — the "
        "exact failure `IDENTITY_DENOMINATORS` exists to prevent.",
        """    "ours_covered_in_span_pct": lambda i: int(i["both"])
    + int(i["ours_only_by_horizon"]["inside_statpal_span"]),""",
        """    "ours_covered_in_span_pct": lambda i: int(i["both"])
    + int(i["ours_only"]),""",
        "test_the_new_number_can_state_the_population_it_was_scored_on",
    ),
    (
        "equality-on-a-contained-inventory-broken",
        "Add a fudge so the new number diverges from the old even where both "
        "spans agree — this is what silently redefines a running seven-day clock.",
        '_pct(both, both + ours_horizon["inside_statpal_span"])',
        '_pct(both, both + ours_horizon["inside_statpal_span"] + 1)',
        "test_a_sport_inside_statpals_span_reads_the_same_under_both_numbers",
    ),
]


def _clear_pycache() -> None:
    for cache in BACKEND.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)


def _run(node: str) -> int:
    _clear_pycache()
    return subprocess.run(
        [sys.executable, "-m", "pytest", f"{SUITE}::{node}", "-q", "--no-header"],
        cwd=BACKEND,
        capture_output=True,
    ).returncode


def main() -> int:
    original = TARGET.read_text()

    # A dead control kills nothing: the suite must be green before we start, or
    # every "killed" below is a mutant killed by an already-red test.
    _clear_pycache()
    baseline = subprocess.run(
        [sys.executable, "-m", "pytest", SUITE, "-q", "--no-header"],
        cwd=BACKEND,
        capture_output=True,
    )
    if baseline.returncode != 0:
        print("BASELINE IS RED — every verdict below would be meaningless")
        print(baseline.stdout.decode()[-2000:])
        return 1
    print(f"baseline GREEN ({SUITE})\n")

    survivors: list[str] = []
    try:
        for name, why, find, replace, node in MUTANTS:
            if original.count(find) != 1:
                print(f"SKIP  {name}: anchor matched {original.count(find)}x, need 1")
                survivors.append(f"{name} (anchor drift)")
                continue

            TARGET.write_text(original.replace(find, replace, 1))
            code = _run(node)
            TARGET.write_text(original)

            if code == 0:
                print(f"SURVIVED  {name}\n          {why}\n          {node}\n")
                survivors.append(name)
            elif code == 1:
                print(f"killed    {name}  <- {node}")
            else:
                # gotcha #124: 1 is a result, anything else is a harness story.
                print(f"HARNESS   {name}: exit {code}, the gate never ran")
                survivors.append(f"{name} (exit {code})")
    finally:
        TARGET.write_text(original)
        _clear_pycache()

    print()
    if survivors:
        print(f"{len(survivors)}/{len(MUTANTS)} SURVIVED: {survivors}")
        return 1
    print(f"{len(MUTANTS)}/{len(MUTANTS)} killed, 0 survived")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
