"""#3564: automate the merged-blob read that caught the CERT-2152 bounce.

``matching_golden_baseline.json`` is a whole-file generated artifact, and that
is what makes it dangerous to merge. Two branches that both regenerate it do not
conflict -- the merged blob is simply one side's file, with no reviewable diff
line and ``git merge-tree`` exit 0. On 2026-09-06 a branch carried
``passing_count: 665`` over master's ``668`` and only a hand read at the merge
desk caught it (integrator/239); the same read had to be repeated on the
repaired branch to confirm the second 665 was honest.

WHAT THE BOUNCE ACTUALLY WAS, because the obvious guess is wrong and a guard
built on the guess would have waved it through. The bounced blob DID name all
eight pairs that stopped passing -- a "name what fell" rule alone accepts it.
Its real defect was the floor it measured itself against: it was re-derived on
its own stale branch point (649) and reported "649 -> 665, no regressions" while
replacing master's 668. The eight it named were the eight that fell against 649.
A ratchet is only a ratchet against the floor of record.

So the guard enforces two rules, and the second is the load-bearing one:

    1. every pair that stops passing is named, by market id, in reset_reason;
    2. a drop names the target's own floor, proving it was measured against the
       floor of record and not against a stale branch point.

Both are checked against numbers the guard RECOMPUTES from the two blobs, never
against the proposal's own narrative -- which is precisely the thing that was
wrong. The two real blobs are exercised end to end below.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from scripts.check_golden_baseline_floor import (  # noqa: E402
    BLOB_PATH,
    BlobUnreadable,
    compare_baselines,
    read_blob,
)


def baseline(pairs: dict[str, bool], reset_reason=None) -> dict:
    """A minimal well-formed baseline whose header matches its body."""
    return {
        "pair_count": len(pairs),
        "passing_count": sum(1 for v in pairs.values() if v),
        "reset_reason": reset_reason,
        "pairs": pairs,
    }


# =============================================================================
# Rule 1 -- name what fell
# =============================================================================


def test_an_unchanged_baseline_is_accepted():
    b = baseline({"1": True, "2": False})
    assert compare_baselines(b, b).ok


def test_a_pure_improvement_needs_no_reason():
    """Ordinary matcher progress must not need ceremony, or the guard becomes a
    tax that lanes route around."""
    v = compare_baselines(
        baseline({"1": True, "2": False}),
        baseline({"1": True, "2": True}),
    )
    assert v.ok, v.problems
    assert v.rose == ["2"]
    assert v.fell == []


def test_a_silent_floor_drop_is_refused():
    v = compare_baselines(
        baseline({"1": True, "2": True}),
        baseline({"1": True, "2": False}),
    )
    assert not v.ok
    assert v.fell == ["2"]
    assert "no `reset_reason`" in "\n".join(v.problems)


def test_a_reason_that_does_not_name_the_fallen_pair_is_refused():
    """A prose reason is not a naming: a reader cannot check it against #3707."""
    v = compare_baselines(
        baseline({"1": True, "2": True}),
        baseline(
            {"1": True, "2": False},
            reset_reason="re-captured at production's own cap; 1 pair fell",
        ),
    )
    assert not v.ok
    assert "not named in `reset_reason`" in "\n".join(v.problems)


def test_naming_only_some_of_the_fallen_pairs_is_refused():
    v = compare_baselines(
        baseline({"1": True, "2": True, "3": True}),
        baseline(
            {"1": False, "2": False, "3": True},
            reset_reason="floor 3 -> 1; market 1 fell",
        ),
    )
    assert not v.ok
    assert "2" in "\n".join(v.problems)


def test_the_gate_is_per_pair_not_on_the_headline_count():
    """Eight down and eight up leaves passing_count identical. The aggregate is
    only the part that is easy to eyeball; the ratchet is per pair."""
    v = compare_baselines(
        baseline({"1": True, "2": False}),
        baseline({"1": False, "2": True}),
    )
    assert v.target_passing == v.proposed_passing == 1
    assert not v.ok, "a swap that preserves the count is still a regression"
    assert v.fell == ["1"]


def test_dropping_a_passing_pair_from_the_corpus_must_also_be_named():
    """Deleting the pair is not a way to stop it failing."""
    v = compare_baselines(baseline({"1": True, "2": True}), baseline({"1": True}))
    assert not v.ok
    assert v.dropped == ["2"]


def test_dropping_a_failing_pair_needs_no_reason():
    """Only a pair that was PASSING is part of the floor being defended."""
    v = compare_baselines(baseline({"1": True, "2": False}), baseline({"1": True}))
    assert v.ok, v.problems
    assert v.dropped == ["2"]


def test_a_new_pair_is_not_counted_as_a_rise():
    """A pair that did not exist in the target cannot have improved; conflating
    the two would let corpus growth paper over a real regression."""
    v = compare_baselines(baseline({"1": True}), baseline({"1": True, "2": True}))
    assert v.ok, v.problems
    assert v.added == ["2"]
    assert v.rose == []


# =============================================================================
# Rule 2 -- a drop must name the floor of record
# =============================================================================


def test_a_drop_that_never_mentions_the_targets_floor_is_refused():
    """THE BOUNCE, in miniature: every fallen pair named, and still refused,
    because the reason talks about a floor that is not the one being replaced."""
    v = compare_baselines(
        baseline({"5001": True, "5002": True, "5003": True}),
        baseline(
            {"5001": True, "5002": True, "5003": False},
            reset_reason="re-capture: 649 -> 665 against the branch point, no "
            "regressions. Pair 5003 was already failing there.",
        ),
    )
    assert not v.ok
    problems = "\n".join(v.problems)
    # Rule 1 is satisfied -- 5003 IS named. Only rule 2 refuses it.
    assert "not named in `reset_reason`" not in problems
    assert "never mentions 3" in problems
    assert "stale branch point" in problems


def test_a_drop_that_names_the_targets_floor_is_accepted():
    v = compare_baselines(
        baseline({"1": True, "2": True, "3": True}),
        baseline(
            {"1": True, "2": True, "3": False},
            reset_reason="anchored on the floor on master, 3: drops to 2 because "
            "pair 3 is a duplicate-event twin.",
        ),
    )
    assert v.ok, v.problems


def test_the_floor_is_matched_as_a_standalone_number_not_a_substring():
    """A plain substring test reads ``668`` inside the market id ``59700668``
    and the drop then certifies itself. Same false positive that made a loose
    ``supersedes`` grep hit ``362146`` during a merge gate.

    Here the target floor is 12 and the reason mentions only market 59700129 --
    which contains "12" -- so a substring check would accept.
    """
    pairs = {str(i): True for i in range(12)}
    target = baseline(pairs)
    proposed_pairs = dict(pairs)
    proposed_pairs["0"] = False
    v = compare_baselines(
        target,
        baseline(
            proposed_pairs,
            reset_reason="market 0 fell; see also unrelated market 59700129",
        ),
    )
    assert not v.ok, "a floor of 12 must not be satisfied by the '12' in 59700129"
    assert "never mentions 12" in "\n".join(v.problems)


def test_a_rise_needs_no_floor_statement():
    """Rule 2 fires only on a drop; ordinary progress stays ceremony-free."""
    v = compare_baselines(
        baseline({"1": True, "2": False}), baseline({"1": True, "2": True})
    )
    assert v.ok, v.problems


# =============================================================================
# A blob that misdescribes itself
# =============================================================================


def test_a_header_that_disagrees_with_its_body_is_refused_not_compared():
    """``passing_count`` is a label the fixture writes about itself, and a
    partial regeneration leaves it describing the previous body."""
    bad = baseline({"1": True, "2": False})
    bad["passing_count"] = 99
    v = compare_baselines(baseline({"1": True}), bad)
    assert not v.ok
    assert "internally inconsistent" in "\n".join(v.problems)


def test_an_inconsistent_target_is_refused_too():
    bad = baseline({"1": True})
    bad["pair_count"] = 42
    v = compare_baselines(bad, baseline({"1": True}))
    assert not v.ok
    assert "target baseline is internally inconsistent" in "\n".join(v.problems)


def test_an_empty_baseline_is_refused_rather_than_vacuously_accepted():
    v = compare_baselines(baseline({"1": True}), baseline({}))
    assert not v.ok
    assert "nothing to compare" in "\n".join(v.problems)


# =============================================================================
# The two real cases, reproduced from the recorded blobs
# =============================================================================

#: The eight pairs that stop passing when the fixture is re-captured at
#: production's cap of 20. All duplicate-event ("twin") failures, filed as
#: #3707 -- production holds more than one event row for one fixture, so the
#: sole-fixture criterion picks no winner.
FELL = [
    "59173709",
    "59700659",
    "59700662",
    "59700871",
    "59705002",
    "59705003",
    "59723435",
    "59767325",
]
#: The five that improved in the same run.
ROSE = ["59173370", "59173376", "59707277", "59707492", "59708412"]

#: Verbatim-in-substance reductions of the two real ``reset_reason`` values.
#: Full texts live in the blobs themselves; what is preserved here is the only
#: property that separates them -- the bounced one names 649 and 665 and never
#: 668, the repair names 668. Checked against the real blobs by the
#: archaeological test below whenever the dead sha is still fetchable.
BOUNCED_REASON = (
    "#3564 step 2: the FIXTURE was re-captured at MAX_CANDIDATES=20. "
    "This baseline was first written at 649 against branch point 17ab0512 and "
    "re-evaluating gives 665, so 649 -> 665 with no regressions. "
    "The floor drops for exactly 8 named pairs: " + ", ".join(FELL)
)
REPAIRED_REASON = (
    "#3564 step 2: the FIXTURE was re-captured at MAX_CANDIDATES=20. "
    "THIS RECORD IS ANCHORED ON 668, THE FLOOR ON MASTER (2825151d, #3672). "
    "An earlier attempt was measured against 649, the floor at the older branch "
    "point, and reported '649 -> 665, no regressions' while silently replacing "
    "master's 668. Re-derived here on top of master: 5 up, 8 down, 668 -> 665. "
    "THE 8 THAT FELL: " + ", ".join(FELL) + ". THE 5 THAT ROSE: " + ", ".join(ROSE)
)


def _real_shaped_pair_maps():
    """Two 709-pair maps with the real counts: 668 passing, then 665.

    Filler is fixed in both, so the only movement is the real 8 down / 5 up.
    660 passing filler + the 8 (passing only in the target) = 668; + the 5
    (passing only in the proposal) = 665. Total 696 filler + 13 = 709 pairs.
    """
    filler = {f"f{i}": i < 660 for i in range(696)}
    target = {**filler, **{m: True for m in FELL}, **{m: False for m in ROSE}}
    proposed = {**filler, **{m: False for m in FELL}, **{m: True for m in ROSE}}
    return target, proposed


def test_the_real_case_counts_are_the_ones_that_were_argued_about():
    """Guard the fixtures above: if these stop being 668/665 the two tests
    below are no longer reproducing the incident they claim to."""
    t, p = _real_shaped_pair_maps()
    assert sum(t.values()) == 668
    assert sum(p.values()) == 665
    assert len(t) == len(p) == 709


def test_the_bounced_blob_is_refused():
    """CERT-2152, the merge integrator/239 turned back."""
    t, p = _real_shaped_pair_maps()
    v = compare_baselines(baseline(t), baseline(p, reset_reason=BOUNCED_REASON))
    assert not v.ok
    assert sorted(v.fell) == FELL
    # Refused for the right reason: the pairs WERE all named.
    problems = "\n".join(v.problems)
    assert "never mentions 668" in problems
    assert "not named in `reset_reason`" not in problems


def test_the_repaired_blob_is_accepted():
    """CERT-2163. Same 665, same eight fallen pairs -- accepted because it is
    measured against the floor it is actually replacing."""
    t, p = _real_shaped_pair_maps()
    v = compare_baselines(baseline(t), baseline(p, reset_reason=REPAIRED_REASON))
    assert v.ok, v.report()
    assert v.proposed_passing < v.target_passing, "the drop is real, not papered over"


# =============================================================================
# Archaeology: the actual recorded blobs, when they can still be read
# =============================================================================

#: The force-pushed CERT-2152 sha. It does not exist on the remote, so CI can
#: never see it and this control is local-only by nature -- which is exactly why
#: the incident is also pinned as data above rather than only as a git read.
BOUNCED_SHA = "7bf301b9"

#: The floor the bounce was actually measured against: the last master commit to
#: write the baseline before it, holding ``passing_count`` 668.
#:
#: This is pinned, and NOT read from ``origin/master``, because ``origin/master``
#: is a MOVING floor. CERT-2163 (#3706) replaces the baseline with the 665 blob,
#: whose pairs are byte-identical to the bounced blob's -- the two differ only in
#: ``reset_reason``. Against that master the comparator correctly reports no
#: movement, and an assertion of "must still be refused" flips from pass to FAIL
#: for a reason that has nothing to do with the rule under test. Anchoring the
#: archaeology to a moving ref is the very defect this module exists to catch.
FLOOR_OF_RECORD_SHA = "2825151d"


def _git_show(ref: str):
    proc = subprocess.run(
        ["git", "show", f"{ref}:{BLOB_PATH}"],
        capture_output=True,
        text=True,
        cwd=BACKEND_ROOT,
    )
    return json.loads(proc.stdout) if proc.returncode == 0 else None


def test_the_recorded_bounced_blob_really_did_omit_the_floor_it_replaced():
    """Confirms the reduction above is faithful to the blob it stands in for.

    Skips when the dead sha is unfetchable. A skip loses only the corroboration;
    the rule itself is pinned on data that needs no git.
    """
    blob = _git_show(BOUNCED_SHA)
    floor = _git_show(FLOOR_OF_RECORD_SHA)
    if blob is None or floor is None:
        pytest.skip(
            f"{BOUNCED_SHA} or {FLOOR_OF_RECORD_SHA} not present in this checkout"
        )

    assert floor["passing_count"] == 668, (
        f"{FLOOR_OF_RECORD_SHA} is pinned as the 668 floor the bounce was measured "
        "against; if it no longer holds 668 the anchor is wrong, not the rule"
    )
    v = compare_baselines(floor, blob)
    assert not v.ok, "the real bounced blob must still be refused"
    assert "never mentions" in "\n".join(v.problems)
    assert sorted(v.fell) == FELL


#: CERT-2163's repaired blob (#3706). Becomes ``origin/master``'s baseline the
#: moment that PR lands.
REPAIRED_SHA = "4f3ce944180741482c98ad3ad77bd3c89aebaa7b"


def test_the_archaeology_is_anchored_to_a_fixed_floor_not_to_moving_master():
    """The regression that anchoring on ``origin/master`` would have caused.

    Reading the anchor from ``origin/master`` passes today only because master
    still holds 668. Once #3706 lands, master holds the 665 blob, whose pairs are
    identical to the bounced blob's -- so the comparator sees NO movement and the
    archaeology test above would have failed on an anchor bug rather than on the
    rule it guards. This pins that, so nobody re-points the anchor at a ref that
    moves.
    """
    bounced = _git_show(BOUNCED_SHA)
    repaired = _git_show(REPAIRED_SHA)
    if bounced is None or repaired is None:
        skipped = BOUNCED_SHA if bounced is None else REPAIRED_SHA
        pytest.skip(f"{skipped} not present in this checkout")

    assert repaired["pairs"] == bounced["pairs"], (
        "the bounce and its repair differ only in reset_reason -- if that stops "
        "being true this test is no longer describing the hazard it pins"
    )
    moving = compare_baselines(repaired, bounced)
    assert moving.ok and not moving.fell, (
        "against post-#3706 master the bounced blob reads as clean; an anchor "
        "that moves therefore inverts the archaeology test's verdict"
    )


# =============================================================================
# The harness itself
# =============================================================================


def test_an_unreadable_ref_raises_rather_than_reading_as_a_pass():
    """gotcha #124: a check that could not run must never look like a green."""
    with pytest.raises(BlobUnreadable):
        read_blob("refs/heads/no-such-branch-3564")
