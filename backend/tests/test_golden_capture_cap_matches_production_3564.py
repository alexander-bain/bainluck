"""#3564: the golden capture must ask production's question, not a smaller one.

``scripts/capture_matching_golden_fixture.py`` builds each market's candidate
list with the same shape the matcher uses -- ``ORDER BY commence_time LIMIT n``
-- but it kept its own ``n``. For a long time that ``n`` was 10 while the
matcher's was 20, and the comment beside it treated the gap as harmless
truncation of "the rows it would have scored last".

It is not harmless. The cap does not shorten the candidate list, it changes the
question: 327 of the 709 golden pairs sit exactly at the cap, so for 46% of the
corpus the fixture hands the matcher a different population than production
hands it -- and *which* rows survive depends on what production had ingested at
capture time. Two captures four days apart: of the 207 pairs at the cap in both,
141 (68%) had a different candidate id set, and of 69 regressions 40 were at the
cap in both with not one keeping its set.

The golden set (#2706) is a ratchet. A ratchet whose question moves is not one.

Why this test parses source instead of importing a shared constant: the matcher
is lane1's file under D39 and the golden set is lane1b's, so neither side may
reach into the other to define the number. The invariant is therefore checked
where it actually lives -- in both files' text -- and this test is the only
thing coupling them. If lane1 retunes the matcher's limit, this goes red and
tells lane1b the fixture's question has moved, which is exactly the signal
#3564 exists to produce. It is deliberately NOT an assertion that the number is
20; it asserts the two agree, whatever the matcher says.

This ship does not re-capture. ``matching_golden_baseline.json`` cannot be
regenerated (INTEGRATOR-236, lane1/147) and is byte-unchanged here; raising the
cap only governs a future capture, which is its own ship with its own
re-adjudication pass.
"""

import ast
import json
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
MATCHER = BACKEND_ROOT / "app" / "tasks" / "prediction_market_matching.py"
CAPTURE = BACKEND_ROOT / "scripts" / "capture_matching_golden_fixture.py"
INPUTS = BACKEND_ROOT / "tests" / "fixtures" / "matching_golden_inputs.json"


def _candidate_limits(source: str) -> list[int]:
    """Every ``.order_by(Event.commence_time).limit(<int>)`` in the matcher.

    Matched structurally rather than by regex so that reformatting, line
    wrapping or an intervening comment cannot quietly stop this test from
    finding the sites -- a guard that silently matches nothing is the failure
    mode this whole file is about.
    """
    tree = ast.parse(source)
    limits: list[int] = []
    for node in ast.walk(tree):
        # .limit(<int>)
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute) or node.func.attr != "limit":
            continue
        if len(node.args) != 1 or not isinstance(node.args[0], ast.Constant):
            continue
        if not isinstance(node.args[0].value, int):
            continue
        # ...whose receiver is .order_by(Event.commence_time)
        recv = node.func.value
        if not isinstance(recv, ast.Call):
            continue
        if not isinstance(recv.func, ast.Attribute) or recv.func.attr != "order_by":
            continue
        if len(recv.args) != 1:
            continue
        arg = recv.args[0]
        if not isinstance(arg, ast.Attribute) or arg.attr != "commence_time":
            continue
        if not isinstance(arg.value, ast.Name) or arg.value.id != "Event":
            continue
        limits.append(node.args[0].value)
    return limits


def _capture_max_candidates(source: str) -> int:
    """``MAX_CANDIDATES`` read as a module-level literal, without importing.

    ``scripts/`` has no ``__init__.py`` and the module mutates ``sys.path`` at
    import time, so reading the assignment is both cheaper and quieter than
    making it importable.
    """
    tree = ast.parse(source)
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "MAX_CANDIDATES":
                assert isinstance(node.value, ast.Constant), (
                    "MAX_CANDIDATES must stay a plain int literal so this guard "
                    "can read it without importing the capture script"
                )
                return node.value.value
    pytest.fail("MAX_CANDIDATES not found in capture_matching_golden_fixture.py")


def test_the_matcher_still_has_candidate_selectors_to_compare_against():
    """The guard is worthless if it finds nothing. Assert it found the sites.

    Three today (the narrow window, the broad-window retry, and the
    sport-prefix count). If a refactor drops below that, this test has stopped
    measuring the thing it claims to measure and must be re-pointed rather than
    left green.
    """
    limits = _candidate_limits(MATCHER.read_text())
    assert len(limits) >= 3, (
        f"expected at least 3 `.order_by(Event.commence_time).limit(n)` candidate "
        f"selectors in {MATCHER.name}, found {len(limits)}: {limits}. The matcher "
        "was probably refactored -- re-point this guard, do not delete it."
    )


def test_every_production_candidate_selector_uses_the_same_limit():
    """One capture cap cannot mirror two different production limits.

    If the matcher ever selects 20 in one path and 30 in another, the fixture's
    single ``MAX_CANDIDATES`` is provably wrong for one of them, and #3564's
    defect is back in a new shape.
    """
    limits = _candidate_limits(MATCHER.read_text())
    assert len(set(limits)) == 1, (
        f"the matcher's candidate selectors disagree: {sorted(set(limits))}. "
        "The golden capture has one cap and cannot mirror both; decide which "
        "population the fixture is a snapshot of before re-capturing."
    )


def test_the_golden_capture_cap_equals_the_matchers_limit():
    """#3564 proper: the fixture asks production's question.

    Not pinned to a literal 20 on purpose -- pinning both sides to a number is
    how they drifted in the first place. This asserts agreement.
    """
    production = _candidate_limits(MATCHER.read_text())[0]
    capture = _capture_max_candidates(CAPTURE.read_text())
    assert capture == production, (
        f"golden capture keeps {capture} candidates per market but the matcher "
        f"scores {production}. Every pair at the cap is then adjudicated against "
        "a population production never sees, and which rows survive depends on "
        "ingest timing at capture -- the #3564 defect. Raise MAX_CANDIDATES to "
        f"{production} (and re-capture as its own ship, with a re-adjudication "
        "pass -- the fixture cannot simply be regenerated)."
    )


def test_the_capture_query_actually_uses_the_constant():
    """A cap nothing reads is a comment.

    The value is interpolated into the UNION ALL block's LIMIT and sizes the
    db-query page. If either stops referencing it, the constant above becomes
    decorative and the two tests above would pass while the script kept
    capturing at whatever is hard-coded in the SQL.
    """
    source = CAPTURE.read_text()
    assert "LIMIT {MAX_CANDIDATES}" in source, (
        "the per-market LIMIT no longer interpolates MAX_CANDIDATES; this guard "
        "and the constant have been decoupled from the query they describe"
    )
    assert "CANDIDATE_BATCH * MAX_CANDIDATES" in source, (
        "the db-query page size no longer derives from MAX_CANDIDATES, so "
        "raising the cap would silently truncate the page instead of widening it"
    )


# =============================================================================
# #3768: the fixture on disk, not just the sources that describe it
#
# Every test above compares SOURCE to SOURCE. None of them opens the fixture. So
# raising the cap in both declared places at once -- a legitimate production
# change -- leaves all four green while the fixture on disk is still a snapshot
# at the OLD cap, asking every market a different question than production asks
# it. That is #3564 again, arriving through the front door.
#
# Measured on master by mutating MAX_CANDIDATES and the matcher's `.limit()`
# sites 20 -> 30 together: this file 4 passed, and the only red anywhere was
# `test_matching_golden_set_2706.py::test_the_fixtures_known_truncation_is_
# banked_and_may_only_improve`, whose message is
#
#     the fixture's fidelity changed to {... 'at_cap': 0 ...}
#     -- update the pinned constants
#
# THE INSTRUCTION IS WRONG AND FOLLOWING IT RE-CREATES #3564. The fixture did
# not change; the cap moved underneath it. Re-pinning `at_cap` to 0 greens the
# suite over a stale fixture AND makes the ratchet vacuous, since the assertion
# is `at_cap <= 189` and nothing can ever exceed 0 again. A guard whose stated
# remedy is the regression is worse than no guard: it launders a red into a
# silent pass via a fix that looks authorized.
#
# So these two run BEFORE that ratchet can mislead, and say `re-capture`.
# =============================================================================


def _searched_candidates(pair: dict) -> list[dict]:
    """The candidates the capture's SEARCH returned, without an appended answer.

    Identical to `test_matching_golden_set_2706.py`'s helper of the same name,
    and duplicated rather than imported: that module builds its pinned constants
    at import time, so importing it here would couple this guard's collection to
    the very ratchet it exists to run ahead of.

    Do NOT be tempted by the shorter "the answer is the last element" test. It
    agrees on the cap but counts 150 pairs at it rather than 189, because a pair
    can carry the answer without it being last. `search_surfaced_the_answer` is
    the fixture's own record of whether an answer was appended, and it is the
    only definition that reproduces the pin.
    """
    if pair["search_surfaced_the_answer"]:
        return pair["events"]
    return [e for e in pair["events"] if e["id"] != pair["correct_event_id"]]


def _observed_capture_cap(pairs: list[dict]) -> int:
    """The cap the fixture was ACTUALLY captured at, read from the data."""
    return max(len(_searched_candidates(p)) for p in pairs)


@pytest.fixture(scope="module")
def golden_pairs() -> list[dict]:
    pairs = json.loads(INPUTS.read_text())["pairs"]
    assert pairs, "the golden inputs fixture is empty; every cap below is vacuous"
    return pairs


def test_the_fixture_was_captured_at_the_cap_the_capture_script_declares(
    golden_pairs,
):
    """A stale fixture must say `re-capture`, never `update the pinned constants`.

    Deliberately `==` and not `<=`. A fixture captured at a LOWER cap than
    production is #3564 exactly, and a fixture captured at a HIGHER one is
    scoring rows production never offers -- both are the fixture asking a
    different question, and neither is a pin to bump.
    """
    declared = _capture_max_candidates(CAPTURE.read_text())
    observed = _observed_capture_cap(golden_pairs)
    assert observed == declared, (
        f"matching_golden_inputs.json was captured at {observed} candidates per "
        f"market, but capture_matching_golden_fixture.py now declares "
        f"{declared}. The fixture is a snapshot at the old cap and is asking "
        f"every market a different question than production asks it -- #3564.\n"
        f"\n"
        f"RE-CAPTURE the fixture (its own ship, with a re-adjudication pass). Do "
        f"NOT update the pinned constants in test_matching_golden_set_2706.py: "
        f"that test is about to fail too, and its message will tell you to "
        f"re-pin `at_cap`. Re-pinning greens the suite over the stale fixture "
        f"and leaves the ratchet asserting `at_cap <= 0`, which can never fire."
    )


def test_at_least_one_pair_actually_reaches_the_cap(golden_pairs):
    """Otherwise the test above proves nothing.

    `max(len(...)) == declared` is only evidence that the capture truncated if
    something was truncated. A corpus whose every market happened to return
    fewer candidates than the cap would satisfy an `observed <= declared` check
    forever while the cap went untested -- the class of guard that silently
    matches nothing, which this whole file is about.

    If this ever legitimately goes to zero -- production thinned out enough that
    no market reaches the cap -- the fixture has stopped exercising truncation
    at all and the cap guard above needs rethinking, not deleting.
    """
    declared = _capture_max_candidates(CAPTURE.read_text())
    at_cap = [p for p in golden_pairs if len(_searched_candidates(p)) >= declared]
    assert at_cap, (
        f"no golden pair reaches the declared cap of {declared}, so nothing in "
        "this fixture is truncated and the cap agreement above is vacuous -- it "
        "would hold for any cap larger than the longest candidate list."
    )
