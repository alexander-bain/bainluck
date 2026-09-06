"""Mutation battery for #3616 — `identity.ours_only_in_span_composition`.

Each mutant is a single edit to production source that reproduces a real way the
decomposition could be wrong, paired with the ONE test node that must go red. A
mutant that survives means the guard names a behaviour nobody is holding.

The two that matter most are the tolerance and the two refusals. Drop the
tolerance and MLB's three-game series read as duplicates of each other, which
would have the row blaming #3093 for games that are genuinely different; turn
either refusal into zeros and tennis — the sport with the largest known
duplicate population on the row — is exonerated by a number nobody measured.

Applied by string replacement and restored from the captured original — never
`git checkout --`, which eats uncommitted work in a shared tree. `__pycache__`
is cleared between mutants so a stale .pyc cannot serve the pre-mutation module.

    python3 scripts/authority_047_mutation_battery.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
TARGET = BACKEND / "app" / "utils" / "authority_agreement.py"
SUITE = "tests/test_authority_in_span_composition_3616.py"

#: (name, why it matters, find, replace, the test node that must go red)
MUTANTS: list[tuple[str, str, str, str, str]] = [
    (
        "kickoff-tolerance-dropped",
        "Same key is enough to call two rows the same game. MLB's schedule unit "
        "is a three-game series and all three share a key by design, so the row "
        "would report genuinely different games as our own duplicates.",
        """        d = _delta(a, b)
        return d is not None and d <= WITHIN""",
        """        return True""",
        "test_a_series_is_not_a_duplicate",
    ),
    (
        "silent-strategy-answers-zero",
        "A join that declares no identity relation gets zeros instead of `None`. "
        "Reads as *measured, no duplicates* about tennis, whose duplicates are "
        "the largest known population on the row (gotcha #53).",
        """    if same_game is None or bucket_key is None:
        return None, []""",
        """    if same_game is None or bucket_key is None:
        return {"second_row_for_a_matched_game": 0, "our_only_row_for_the_game": 0}, []""",
        "test_a_join_that_cannot_say_publishes_none_and_not_zeros",
    ),
    (
        "no-span-answers-zero",
        "Decompose a bucket that does not exist. With no timed StatPal fixture "
        "every miss is `unplaceable` and there is no in-span bucket to split.",
        """    span = timed_span(fixtures)
    if span is None:""",
        """    span = timed_span(fixtures)
    if False:""",
        "test_a_side_with_no_span_publishes_none_rather_than_a_split_of_nothing",
    ),
    (
        "in-span-filter-dropped",
        "Decompose EVERY ours-only row, not the in-span ones. The two counts "
        "stop summing to the bucket they claim to decompose, so a reader "
        "subtracting them from `inside_statpal_span` gets a negative residue.",
        """        if miss.start is None or miss.start < first or miss.start > last:
            continue""",
        """        if miss.start is None:
            continue""",
        "test_the_composition_sums_to_the_bucket_it_decomposes",
    ),
    (
        "twin-searched-among-all-our-rows",
        "Look for the twin among every row of ours rather than the MATCHED "
        "ones. Two unmatched rows for one game would then read as a duplicate "
        "of a matched game, crediting the join with a pairing it never made.",
        """    for _f, matched in paired:""",
        """    for matched in [r for _f, r in paired] + list(ours_only):""",
        "test_the_in_span_misses_are_named_as_ours_or_theirs",
    ),
    (
        "buckets-swapped",
        "Report a duplicate as the residue and the residue as a duplicate. Every "
        "count still sums correctly, so only an assertion on the NAMES catches "
        "it — and it inverts who owns the fix.",
        """        if matched_twin is not None:
            counts["second_row_for_a_matched_game"] += 1""",
        """        if matched_twin is not None:
            counts["our_only_row_for_the_game"] += 1""",
        "test_the_in_span_misses_are_named_as_ours_or_theirs",
    ),
    (
        "receipt-names-only-the-spare",
        "Drop the matched row from the receipt. #3093's repair has to choose "
        "which of the two rows to keep, and one event id alone cannot be acted "
        "on — the count would be readable and the finding still unactionable.",
        """            receipts.append(_row_receipt(miss, matched_row=sibling.ref, duplicate_of=bucket))""",
        """            receipts.append(_row_receipt(miss, duplicate_of=bucket))""",
        "test_the_receipts_name_both_halves_of_the_pair",
    ),
    (
        "unmatched-duplicates-not-clustered",
        "CERT-2104's BLOCK, reintroduced: compare a miss only against MATCHED "
        "rows. Two rows of ours for a game StatPal never listed then read as two "
        "holes — our own duplication inflating the hole count, which is the "
        "defect this whole field exists to remove.",
        """        reps = unmatched_reps.setdefault(key, [])
        unmatched_twin = next((r for r in reps if same_game(miss, r)), None)""",
        """        reps = unmatched_reps.setdefault(key, [])
        unmatched_twin = None""",
        "test_two_duplicate_rows_for_a_game_statpal_never_listed_are_one_miss",
    ),
    (
        "unmatched-duplicate-counted-as-a-matched-one",
        "Fix the new class by blurring it into the old one. The counts add up "
        "and the two kinds of evidence — a second row for a game we can see "
        "StatPal has, versus one for a game we cannot find at all — stop being "
        "distinguishable.",
        """            counts["second_row_for_an_unmatched_game"] += 1
            _receipt(miss, unmatched_twin, "another_unmatched_row_of_ours")""",
        """            counts["second_row_for_a_matched_game"] += 1
            _receipt(miss, unmatched_twin, "a_row_that_matched_statpal")""",
        "test_the_matched_and_unmatched_duplicate_buckets_are_not_interchangeable",
    ),
    (
        "every-unmatched-row-becomes-its-own-representative",
        "Append the representative BEFORE testing it, so a row always matches "
        "itself and no row is ever the unique miss. `our_only_row_for_the_game` "
        "collapses to zero and the only bucket that counts games stops counting.",
        """        reps.append(miss)
        counts["our_only_row_for_the_game"] += 1""",
        """        counts["our_only_row_for_the_game"] += 1""",
        "test_two_duplicate_rows_for_a_game_statpal_never_listed_are_one_miss",
    ),
    (
        "bucket-key-made-finer-than-the-predicate",
        "Bucket on pair AND exact kickoff. The twin is 20 minutes off by "
        "construction, so every lookup misses and the row reports our own "
        "second row as StatPal's hole — silently, with nothing else noticing.",
        """        our_side_bucket_key=lambda side: _pair_key(side, normalize),""",
        """        our_side_bucket_key=lambda side: f"{_pair_key(side, normalize)}@{side.start}",""",
        "test_the_bucket_key_never_separates_two_rows_the_predicate_joins",
    ),
    (
        "half-a-contract-absorbed-by-a-fallback",
        "Accept a predicate with no bucket key instead of refusing it. That is "
        "the quadratic build this field exists to prevent — 11ms to 5.5s at "
        "2,000 games — and it would ship green.",
        """        if (self.same_game_on_our_side is None) != (self.our_side_bucket_key is None):""",
        """        if False:""",
        "test_half_a_same_game_contract_is_refused_at_construction",
    ),
    (
        "twin-search-unbucketed-again",
        "Scan every matched row for every miss. Correct, and unaffordable: the "
        "regression is invisible to an assertion on the counts, which is why "
        "the guard counts predicate CALLS.",
        """            (r for r in matched_by_bucket.get(key, ()) if same_game(miss, r)), None""",
        """            (r for _f, r in paired if same_game(miss, r)), None""",
        "test_the_twin_search_does_not_scan_every_matched_row",
    ),
    (
        "default-join-stops-declaring-its-relation",
        "The key join forgets to publish `same_game_on_our_side`, so every sport "
        "falls back to the silent-strategy refusal and the field reads `None` "
        "everywhere — the finding disappears without a single number changing.",
        """        same_game_on_our_side=same_game,""",
        """""",
        "test_the_in_span_misses_are_named_as_ours_or_theirs",
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
