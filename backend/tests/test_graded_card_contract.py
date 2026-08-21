"""#1933 — the graded-card gate is ONE decision, shared by every surface that
writes a judgment, and the percent it fingerprints at is a CROSS-RUNTIME rule.

Three things are pinned here, and each of them is a thing that has already gone
wrong once:

1. ``rendered_percent`` against ``contracts/rendered_percent.json`` — UX-P110
   shipped it with Python's banker's rounding under a comment asserting the
   JavaScript answer.
2. The served-outcome constants against the slices the two serializers actually
   render — a fingerprint over rows a surface does not show refuses verdicts
   nobody can explain.
3. ``drift_outcome``'s three values, including the one that only native can
   reach, because a policy with an arm no test drives is a policy with an arm
   nobody has read.

Pure throughout: no database, no app import beyond the two route modules whose
source is being read.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from app.utils.graded_card import (
    ABSENT_REFUSE,
    ABSENT_UNBOUND,
    LABEL_PASS_SERVED_OUTCOMES,
    NATIVE_SERVED_OUTCOMES,
    OMITTED,
    card_fingerprint,
    drift_outcome,
    is_complement_pair,
    rendered_card_percents,
    rendered_percent,
)

CONTRACT_PATH = (
    Path(__file__).resolve().parents[2] / "contracts" / "rendered_percent.json"
)
CONTRACT = json.loads(CONTRACT_PATH.read_text())
CASES = CONTRACT["cases"]
CARD_CASES = CONTRACT["card_cases"]


# ── 1. THE PERCENT, AGAINST THE SHARED TABLE ────────────────────────────────


@pytest.mark.parametrize(
    "case", CASES, ids=[str(c["probability"]) for c in CASES]
)
def test_rendered_percent_matches_the_contract(case):
    assert rendered_percent(case["probability"]) == case["percent"]


def test_the_contract_still_contains_rows_that_catch_bankers_rounding():
    """A table can be defanged by deleting rows, silently and while staying green.

    Only five rows in the file disagree with Python's built-in ``round``; a suite
    that happens to keep the other twelve passes against the exact defect this
    contract was written for. So the discriminating rows are asserted to exist,
    and asserted to actually discriminate — the flag in the JSON is checked
    against arithmetic, not trusted.
    """
    discriminating = [c for c in CASES if c.get("discriminates")]
    assert len(discriminating) >= 5

    for case in discriminating:
        product = case["probability"] * 100
        assert round(product) != case["percent"], (
            f"{case['probability']} is flagged as discriminating but Python's "
            f"round() agrees with the contract on it — the flag is wrong"
        )

    for case in CASES:
        if case["probability"] is None or case.get("discriminates"):
            continue
        product = case["probability"] * 100
        assert round(product) == case["percent"], (
            f"{case['probability']} is NOT flagged as discriminating but "
            f"round() disagrees — the flag is wrong"
        )


def test_rendered_percent_does_not_use_pythons_round():
    """The positive assertions above would all pass on a decimal-based rewrite
    that happened to agree. This pins the arithmetic the contract names: the
    multiply happens first, in float, and ``round`` is not the operator."""
    source = inspect.getsource(rendered_percent)
    body = "\n".join(
        line for line in source.splitlines() if not line.strip().startswith("#")
    )
    # The docstring says "NOT round()" — so exclude the prose before checking.
    code = body.split('"""')[-1]
    assert "math.floor" in code
    assert "+ 0.5" in code
    assert "round(" not in code


def test_contract_declares_all_three_runtimes_and_their_files_exist():
    repo = CONTRACT_PATH.parent.parent
    runtimes = {impl["runtime"] for impl in CONTRACT["implementations"]}
    assert runtimes == {"python", "typescript", "swift"}
    for impl in CONTRACT["implementations"]:
        assert (repo / impl["path"]).exists(), impl["path"]
        assert (repo / impl["driven_by"]).exists(), impl["driven_by"]
        text = (repo / impl["path"]).read_text()
        assert impl["symbol"] in text
        # Version 2 (#2060) — every runtime owes the CARD rule too, or the three
        # agree about each number and still disagree about the sum.
        assert impl["card_symbol"] in text, (
            f"{impl['runtime']} declares {impl['card_symbol']} in the contract "
            f"but {impl['path']} does not define it"
        )


# ── 1b. THE CARD, AGAINST THE SHARED TABLE (#2060) ──────────────────────────


@pytest.mark.parametrize(
    "case", CARD_CASES, ids=[str(c["probabilities"]) for c in CARD_CASES]
)
def test_rendered_card_percents_matches_the_contract(case):
    assert rendered_card_percents(case["probabilities"]) == case["percents"]


@pytest.mark.parametrize(
    "case", CARD_CASES, ids=[str(c["probabilities"]) for c in CARD_CASES]
)
def test_complement_pair_flag_matches_the_contract(case):
    assert is_complement_pair(case["probabilities"]) is case["complement_pair"]


@pytest.mark.parametrize(
    "case", CARD_CASES, ids=[str(c["probabilities"]) for c in CARD_CASES]
)
def test_the_naive_column_is_arithmetic_not_annotation(case):
    """`naive` records what INDEPENDENT rounding gives, and is checked, not trusted.

    It is the column that makes `discriminates` meaningful, so a wrong value there
    would quietly disarm the row-preservation test below.
    """
    assert [rendered_percent(p) for p in case["probabilities"]] == case["naive"]


def test_the_card_contract_keeps_the_rows_that_catch_independent_rounding():
    """A table can be defanged by deleting rows while staying green.

    Six rows disagree with independent per-outcome rounding; those six ARE the
    defect. A suite keeping only the other nine passes against the exact bug the
    rule was written for. The flag is verified against arithmetic rather than
    believed.
    """
    discriminating = [c for c in CARD_CASES if c.get("discriminates")]
    assert len(discriminating) >= 6

    for case in discriminating:
        assert case["percents"] != case["naive"], (
            f"{case['probabilities']} is flagged as discriminating but the card "
            f"rule agrees with independent rounding on it — the flag is wrong"
        )
    for case in CARD_CASES:
        if case.get("discriminates"):
            continue
        assert case["percents"] == case["naive"], (
            f"{case['probabilities']} is NOT flagged as discriminating but the "
            f"card rule disagrees with independent rounding — the flag is wrong"
        )


def test_the_card_contract_pins_the_leave_alone_direction_too():
    """Gotcha #43: a guard's tests must assert BOTH directions.

    The table must keep two-outcome rows that are NOT complement pairs and whose
    rendered sums are deliberately not 100 — otherwise a future 'simplification'
    that normalizes every pair of outcomes passes the whole suite while inventing
    probabilities on thin books.
    """
    left_alone = [
        c
        for c in CARD_CASES
        if len(c["probabilities"]) == 2
        and not c["complement_pair"]
        and all(p is not None for p in c["probabilities"])
    ]
    assert len(left_alone) >= 4
    sums = {sum(c["percents"]) for c in left_alone}
    assert sums - {100}, (
        "every left-alone row happens to sum to 100, so this test cannot "
        "distinguish 'left alone' from 'normalized'"
    )


def test_a_complement_pair_always_renders_exactly_one_hundred():
    """The display-layer invariant, stated once against the contract table."""
    pairs = [c for c in CARD_CASES if c["complement_pair"]]
    assert len(pairs) >= 6
    for case in pairs:
        assert sum(case["percents"]) == 100, case["probabilities"]


def test_none_is_not_zero():
    """'No price' and '0%' are different cards, so they must be different
    fingerprints. The contract's first row says so; this says why."""
    withheld = card_fingerprint(
        title="t", status="open", resolution_date=None, field_coherent=True,
        outcomes=[{"name": "Yes", "probability": None}],
        served_outcomes=NATIVE_SERVED_OUTCOMES,
    )
    zero = card_fingerprint(
        title="t", status="open", resolution_date=None, field_coherent=True,
        outcomes=[{"name": "Yes", "probability": 0.0}],
        served_outcomes=NATIVE_SERVED_OUTCOMES,
    )
    assert withheld != zero


# ── 2. THE SERVED SLICE, AGAINST THE SERIALIZERS ────────────────────────────


def test_label_pass_constant_matches_the_slice_that_route_renders():
    from app.routes import admin_label_pass

    source = inspect.getsource(admin_label_pass._live_features)
    assert "outcomes[:LABEL_PASS_SERVED_OUTCOMES]" in source, (
        "the label-pass serializer must slice by the constant, not a literal — "
        "a literal is how the fingerprint and the picture drift apart"
    )
    assert LABEL_PASS_SERVED_OUTCOMES == 8


def test_native_constant_matches_the_slice_that_route_renders():
    from app.routes import admin_judgments

    source = inspect.getsource(admin_judgments._serialize_labeling_candidate)
    assert "outcomes[:NATIVE_SERVED_OUTCOMES]" in source
    assert NATIVE_SERVED_OUTCOMES == 5


def test_the_two_surfaces_really_do_render_different_slices():
    """Not a tautology, and worth its own row: the whole reason
    ``served_outcomes`` is a required argument is that these two numbers differ.
    If they ever converge, the argument can go — and someone should have to
    delete this test to find that out."""
    assert LABEL_PASS_SERVED_OUTCOMES != NATIVE_SERVED_OUTCOMES


def test_fingerprint_ignores_outcomes_past_the_served_slice():
    served = [{"name": f"O{i}", "probability": 0.1} for i in range(5)]
    extra = served + [{"name": "O5", "probability": 0.9}]
    kwargs = dict(
        title="t", status="open", resolution_date=None, field_coherent=True,
        served_outcomes=NATIVE_SERVED_OUTCOMES,
    )
    assert card_fingerprint(outcomes=served, **kwargs) == card_fingerprint(
        outcomes=extra, **kwargs
    )


def test_a_wider_slice_sees_a_move_the_narrower_one_cannot():
    """The inverse of the row above — otherwise "ignores extra outcomes" is
    satisfied by a fingerprint that ignores outcomes entirely."""
    base = [{"name": f"O{i}", "probability": 0.1} for i in range(6)]
    moved = base[:5] + [{"name": "O5", "probability": 0.9}]
    kwargs = dict(title="t", status="open", resolution_date=None, field_coherent=True)
    assert card_fingerprint(
        outcomes=base, served_outcomes=8, **kwargs
    ) != card_fingerprint(outcomes=moved, served_outcomes=8, **kwargs)
    assert card_fingerprint(
        outcomes=base, served_outcomes=5, **kwargs
    ) == card_fingerprint(outcomes=moved, served_outcomes=5, **kwargs)


def test_served_outcomes_has_no_default():
    """A default is how the third surface silently inherits the first surface's
    picture. Keyword-only and required."""
    signature = inspect.signature(card_fingerprint)
    parameter = signature.parameters["served_outcomes"]
    assert parameter.default is inspect.Parameter.empty
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY


# ── 3. THE SHARED DECISION, ALL THREE VALUES ────────────────────────────────

LIVE = {"title": "Michigan Senate winner?", "status": "open", "probability": 0.61,
        "field_coherent": True}


def test_matching_fingerprint_is_bound():
    out = drift_outcome("abc123", "abc123", live_card=LIVE)
    assert out["status"] == "bound"
    assert out["fingerprint"] == "abc123"


def test_a_moved_card_is_a_typed_conflict_with_zero_writes():
    out = drift_outcome("abc123", "def456", live_card=LIVE, on_absent=ABSENT_REFUSE)
    assert out["status"] == "conflict"
    assert out["reason"] == "card_drifted"
    assert out["writes"] == 0
    assert out["applied"] is False
    # The refusal carries the live card so the client can re-render without a
    # second round trip, and so a human can see WHAT moved.
    assert out["live_card"]["title"] == LIVE["title"]
    assert out["expected"] == "def456"


def test_an_absent_fingerprint_refuses_on_a_page_and_is_unbound_on_a_binary():
    """The one place native is not web, asserted rather than described.

    A web tab is re-served on every load, so refusing is a reload. A native
    binary is not, so refusing would void every label from the build already on
    Alex's phone — on the surface #1933 records him preferring.
    """
    web = drift_outcome(OMITTED, "def456", live_card=LIVE, on_absent=ABSENT_REFUSE)
    assert web["status"] == "conflict"
    assert web["reason"] == "card_fingerprint_missing"

    native = drift_outcome(OMITTED, "def456", live_card=LIVE, on_absent=ABSENT_UNBOUND)
    assert native["status"] == "unbound"
    assert native["reason"] == "client_did_not_declare_gate"
    # Unbound is not a refusal — but it is never silence either.
    assert native["expected"] == "def456"


def test_declaring_the_gate_and_sending_nothing_is_a_refusal_on_both_surfaces():
    """An empty value is a client bug, not a legacy build, and the two get
    different answers. This is the row that makes the tri-state real: without
    it, ``on_absent=UNBOUND`` could be implemented as "never refuse"."""
    for policy in (ABSENT_REFUSE, ABSENT_UNBOUND):
        out = drift_outcome("", "def456", live_card=LIVE, on_absent=policy)
        assert out["status"] == "conflict", policy
        assert out["reason"] == "card_fingerprint_missing", policy


def test_refuse_is_the_default_policy():
    """A caller that forgets to state a policy gets the safe one. The unbound
    arm has to be asked for by name."""
    out = drift_outcome(OMITTED, "def456", live_card=LIVE)
    assert out["status"] == "conflict"


def test_a_bound_verdict_cannot_be_reached_with_two_empty_fingerprints():
    """If both sides are empty, equality alone would say "bound" — and that is
    the failure mode where a market with no card at all passes the gate."""
    out = drift_outcome("", None, live_card={}, on_absent=ABSENT_REFUSE)
    assert out["status"] == "conflict"


def test_both_routes_import_the_shared_decision_rather_than_reimplementing_it():
    """#1933's actual complaint: 'a fix that lives inside one route handler is a
    fix that the next surface will also miss.' A second hand-written comparison
    in either route would satisfy every behavioural test above and reintroduce
    the defect, so the import is asserted directly."""
    from app.routes import admin_judgments, admin_label_pass

    for module in (admin_label_pass, admin_judgments):
        source = inspect.getsource(module)
        assert "from app.utils.graded_card import" in source, module.__name__
        assert "drift_outcome" in source, module.__name__
