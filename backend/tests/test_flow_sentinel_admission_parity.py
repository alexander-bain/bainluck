"""#1951 — the sentinel's admission predicate is DRIVEN BY the shared decision.

`contracts/feed_card_admission.json` is the Discover card-admission rule. This
file is the Python implementation's half of answering to it: it loads the table
and drives `feed_item_is_renderable` through EVERY row. The web implementation is
driven through the same rows by `frontend/__tests__/ios/conceptAdmissionParity.
test.ts`, which also source-asserts native and enforces the registry.

WHAT CHANGED IN CYCLE 91, AND WHY IT IS NOT COSMETIC. Cycle 90 corrected this
predicate's three drifted arms and pinned the corrections with a hand-written
matrix that DUPLICATED the TypeScript one. That fixed the instance and left the
mechanism: two matrices, in two languages, that a reader must diff by eye to know
they still say the same thing. Ruling 021 is exactly about this — *when two
consumers must agree about the same input, the unit to share is the DECISION, not
the ingredient; a shared predicate under two policies is still two policies.*
Three implementations that merely AGREE are three policies. The table is the
decision; these tests are the only thing each implementation is allowed to answer
to.

THE DEFECT THE TABLE RATCHETS AGAINST, stated exactly. `feed_item_is_renderable`
shipped in UX-P092 (#1948) as a third implementation of a rule that already had
two, and it carried the PRE-#1935 reading:

    tournament:  golfers OR marquee_whathit      (both clients: golfers ALONE)
    concept:     marquee_whathit OR leader       (both clients: whathit needs a
                                                  nameable result; leader must be
                                                  usable, not merely present)
    futures:     no resolution_date authority    (both clients have one)

That matters more here than in a renderer. The predicate feeds the DARK-CLASS
limb, whose entire job is naming card types the server builds and no client can
render — the #1935 family. A detector MORE PERMISSIVE than the surfaces it speaks
for cannot see the family it hunts. Measured against a real 75-card production
page (`522caea4`) with its seven tournaments mutated to the golferless-whathit
shape: both clients suppress all seven, and the old predicate scored the class
`7 built, 7 renderable` — a PASS over a fully dark tier. That is #1948's own
failure mode reproduced inside the fix for #1948.

WHY THIS IS NOT THE "PERMISSIVE READING" THE FLOOR LIMB ASKED FOR. The
`feed_renderable_card_count` docstring argues for permissiveness, and it is right
about the FLOOR limb: under-counting there means a noisy alarm, and a noisy alarm
gets muted. But that argument is about erring against the FLOOR, not about
disagreeing with the CLIENTS. Matching them is not strictness, it is accuracy — a
card the clients drop is genuinely not on the reader's page. On the 327-card
production sample this was written against, the corrected predicate changes the
renderable count by exactly ZERO (58/75 either way), because today's population
contains no specimen of any of the three drifts. See
`test_corrected_predicate_does_not_move_a_healthy_page`.
"""

from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.tasks.flow_sentinel import (
    discover_first_page_failures,
    feed_dark_card_classes,
    feed_item_is_renderable,
    feed_renderable_card_count,
)

CONTRACT_PATH = (
    Path(__file__).resolve().parents[2] / "contracts" / "feed_card_admission.json"
)


def _load_contract() -> dict:
    # A path typo must not read as a clean pass — an unrunnable check and a
    # passing check are indistinguishable from the exit code (gotcha #54's
    # cousin), and this file's whole value is that it runs.
    assert CONTRACT_PATH.is_file(), f"the shared decision is missing: {CONTRACT_PATH}"
    return json.loads(CONTRACT_PATH.read_text())


CONTRACT = _load_contract()
NOW = datetime.fromisoformat(CONTRACT["now"].replace("Z", "+00:00"))

# `feed_item_is_renderable` returns a bool, not a reason code, and that asymmetry
# is deliberate — the reason codes are web's suppression TELEMETRY, while the
# sentinel only needs the verdict. The shared unit is the DECISION, so a row's
# `expected_reason: null` reads as True here and any string reads as False.
_CASES = [
    pytest.param(
        case["item"],
        (
            not case["expected_suppressed"]
            if case.get("malformed_envelope")
            else case["expected_reason"] is None
        ),
        id=case["id"],
    )
    for case in CONTRACT["cases"]
]


@pytest.mark.parametrize("item,renderable", _CASES)
def test_every_row_of_the_shared_decision(item, renderable):
    assert feed_item_is_renderable(item, now=NOW) is renderable


class TestTheTableIsWorthAnsweringTo:
    """A table can only ratchet what it covers, so its coverage is asserted too.

    Without these, the fold degrades quietly into the thing it replaced: someone
    adds a card type, gives it no rows, and every implementation's suite stays
    green while the type ships dark on all three surfaces — #1935 restated.
    """

    def test_the_declared_python_implementation_is_this_one(self):
        impls = {i["id"]: i for i in CONTRACT["implementations"]}
        sentinel = impls["sentinel"]
        assert sentinel["symbol"] == "feed_item_is_renderable"
        path = CONTRACT_PATH.parents[1] / sentinel["path"]
        assert path.is_file(), path
        assert f"def {sentinel['symbol']}(" in path.read_text()

    @pytest.mark.parametrize("card_type", CONTRACT["emitted_types"])
    def test_every_emitted_type_is_decided_in_both_directions(self, card_type):
        # One-directional coverage is the failure mode that matters: a type with
        # only admitted rows is satisfied by `return True`, and a type with only
        # suppressed rows is satisfied by `return False` — which would "detect"
        # perfectly and starve the feed.
        #
        # This guard found its own exception on its first run: `event` is
        # genuinely unconditional on all three surfaces, so it has no well-formed
        # suppression row and never can. That is now DECLARED in
        # `unconditional_types` rather than tolerated here — a declaration is
        # checkable and a tolerance is not — and a declared unconditional type
        # still owes a malformed-envelope row, so `return True` stays insufficient
        # even for it.
        rows = [
            case
            for case in CONTRACT["cases"]
            if isinstance(case["item"], dict) and case["item"].get("type") == card_type
        ]
        verdicts = {
            case["expected_reason"] is None
            for case in rows
            if not case.get("malformed_envelope")
        }
        if card_type in CONTRACT.get("unconditional_types", []):
            assert verdicts == {True}, card_type
            assert any(case.get("malformed_envelope") for case in rows), (
                f"`{card_type}` is declared unconditional, so its only proof that "
                f"the arm is not a bare `return True` is a malformed-envelope row"
            )
            return
        assert verdicts == {True, False}, (
            f"`{card_type}` is emitted by a producer but the shared decision does "
            f"not pin both verdicts for it (got {verdicts or 'no rows at all'})"
        )

    def test_the_producers_emit_exactly_the_declared_types(self):
        # The guard that makes a NEW card type impossible to ship dark. A type the
        # server can build and the table does not name would be `unknown_type` on
        # web and False here — dark on arrival, and silent, because no limb can
        # report a class nobody enumerated.
        import re

        root = CONTRACT_PATH.parents[1]
        found: set[str] = set()
        for producer in CONTRACT["producers"]:
            src = (root / producer["path"]).read_text()
            emitted = set(re.findall(r'"type": *"([a-z_]+)"', src))
            assert emitted == set(producer["emits"]), (
                f"{producer['path']} emits {sorted(emitted)}, declared "
                f"{sorted(producer['emits'])}"
            )
            found |= emitted
        assert found == set(CONTRACT["emitted_types"])


# ---------------------------------------------------------------------------
# The specimen. A recorded production page SHAPE (`522caea4`, 2026-08-18) with
# the class counts it actually served, so the limb is graded on the thing it
# failed on rather than on a hand-built two-card page.
#
# These are NOT rows of the shared decision and must not move into the table:
# the table is about ONE CARD's admission, and these are about what the LIMB
# reports over a page. Same predicate, different unit.
# ---------------------------------------------------------------------------
def concept(**data) -> dict:
    base = {
        "key": "event:ufc:26aug20",
        "name": "UFC Fight Night",
        "domain": "mma",
        "status": "upcoming",
        "is_major": True,
        "marquee_whathit": False,
    }
    base.update(data)
    return {"type": "concept", "data": base}


def tournament(**data) -> dict:
    base = {"name": "The Open Championship", "status": "upcoming"}
    base.update(data)
    return {"type": "tournament", "data": base}


def futures(**data) -> dict:
    base = {"name": "Who wins the 2026 election?", "top_outcomes": []}
    base.update(data)
    return {"type": "futures", "data": base}


def _production_shaped_page() -> list[dict]:
    page: list[dict] = []
    page += [{"type": "event", "data": {"id": i}} for i in range(12)]
    page += [
        futures(name=f"market {i}", top_outcomes=[{"name": "Yes", "probability": 0.5}])
        for i in range(39)
    ]
    page += [
        tournament(name=f"tour {i}", golfers=[{"name": "A", "probability": 0.2}])
        for i in range(7)
    ]
    # The #1948 population as served: 17 concepts, every one leaderless.
    page += [concept(key=f"event:ufc:26aug{i}") for i in range(17)]
    return page


def test_corrected_predicate_does_not_move_a_healthy_page():
    """The measured answer to "does matching the clients make the floor noisy".

    On the production population this was written against, the three corrections
    are all no-ops — there is no live specimen of any of them. The floor limb
    sees the same number it saw before, which is why this change carries no
    cry-wolf risk for limb 1 and is pure sight for limb 3.
    """
    page = _production_shaped_page()
    renderable = feed_renderable_card_count(page)
    assert renderable == 58, renderable
    assert len(page) == 75

    # Limb 1 is untouched: 58 clears the floor of 12 comfortably, exactly as it
    # did before, and only the dark-class limb fires.
    failures = discover_first_page_failures(
        renderable=renderable, elapsed_s=3.744, cache_status="miss", items=page
    )
    assert [f["limb"] for f in failures] == ["dark_class"]
    assert failures[0]["card_type"] == "concept"
    assert failures[0]["built"] == 17


def test_the_golferless_whathit_tier_is_now_reported_dark():
    """The specimen the OLD predicate scored as a PASS.

    This is the regression proof for #1951: mutate the same production page's
    seven tournaments into the shape both clients drop, and the class must be
    named. Under the pre-fix reading this assertion fails — the class scored
    `7 built, 7 renderable` and the page reported healthy.
    """
    page = copy.deepcopy(_production_shaped_page())
    for item in page:
        if item["type"] == "tournament":
            item["data"]["golfers"] = []
            item["data"]["marquee_whathit"] = True

    dark = {d["type"]: d for d in feed_dark_card_classes(page)}
    assert "tournament" in dark, (
        "the tournament tier is dark on both surfaces and the detector must say so"
    )
    assert dark["tournament"]["built"] == 7
    assert dark["tournament"]["renderable"] == 0

    failures = discover_first_page_failures(
        renderable=feed_renderable_card_count(page),
        elapsed_s=3.744,
        cache_status="miss",
        items=page,
    )
    assert {f["card_type"] for f in failures if f["limb"] == "dark_class"} == {
        "concept",
        "tournament",
    }


def test_the_resultless_whathit_concept_tier_is_reported_dark():
    """The same proof for the concept arm's settled half."""
    page = copy.deepcopy(_production_shaped_page())
    for item in page:
        if item["type"] == "concept":
            item["data"]["marquee_whathit"] = True
            item["data"]["winner"] = ""
            item["data"]["result_summary"] = None

    dark = {d["type"]: d for d in feed_dark_card_classes(page)}
    assert dark["concept"]["built"] == 17
    assert dark["concept"]["renderable"] == 0


def test_a_tier_that_can_name_its_result_is_not_dark():
    """The non-vacuity control.

    Without this, every assertion above is satisfied by a predicate that returns
    False for everything — which would "detect" beautifully and starve the feed.
    """
    page = copy.deepcopy(_production_shaped_page())
    for item in page:
        if item["type"] == "concept":
            item["data"]["marquee_whathit"] = True
            item["data"]["winner"] = "Tadej Pogacar"

    assert feed_dark_card_classes(page) == []
    assert feed_renderable_card_count(page) == 75


def test_a_malformed_page_does_not_take_the_limb_down():
    """The page-level half of the malformed-envelope rows.

    Web's copy THREW on two of those shapes, inside a render-path `.filter()`
    (#1951). The sentinel's exposure is the mirror image: a single malformed card
    must not abort the census and blank an evidence block, because a limb that
    raises reports nothing and a limb reporting nothing reads as healthy.
    """
    page = _production_shaped_page()
    page += [None, "not a card", {"type": "concept"}, {"type": "event", "data": None}]

    assert feed_renderable_card_count(page) == 58
    dark = {d["type"]: d for d in feed_dark_card_classes(page)}
    assert dark["concept"]["renderable"] == 0
