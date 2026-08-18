"""#1951 — the sentinel's admission predicate must BEHAVE like the two clients.

`frontend/__tests__/ios/conceptAdmissionParity.test.ts` is the structural link:
it asserts, against source, that all three copies of the Discover card-admission
rule carry the same arms in the same order. This file is the behavioural half —
it drives the Python copy through the rows and proves the outcomes, which a
source assertion cannot do.

THE DEFECT THIS RATCHETS AGAINST, stated exactly. `feed_item_is_renderable`
shipped in UX-P092 (#1948) as a third implementation of a rule that already had
two, and it carried the PRE-#1935 reading on two arms:

    tournament:  golfers OR marquee_whathit      (both clients: golfers ALONE)
    concept:     marquee_whathit OR leader       (both clients: whathit needs a
                                                  nameable result; leader must be
                                                  usable, not merely present)

and was missing web's fourth futures authority (`resolution_date` in the past).

That matters more here than in a renderer. The predicate feeds the DARK-CLASS
limb, whose entire job is naming card types the server builds and no client can
render — the #1935 family. A detector that is MORE PERMISSIVE than the surfaces
it speaks for cannot see the family it hunts. Measured against a real 75-card
production page (`522caea4`) with its seven tournaments mutated to the
golferless-whathit shape: both clients suppress all seven, and the old predicate
scored the class `7 built, 7 renderable` — a PASS over a fully dark tier. That is
#1948's own failure mode (an alarm fully green while a tier is dark) reproduced
inside the fix for #1948.

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
from datetime import datetime, timedelta, timezone

import pytest

from app.tasks.flow_sentinel import (
    discover_first_page_failures,
    feed_dark_card_classes,
    feed_item_is_renderable,
    feed_renderable_card_count,
)

NOW = datetime(2026, 8, 18, 4, 45, tzinfo=timezone.utc)


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


# ---------------------------------------------------------------------------
# The shared matrix — the same claims the TS contract test makes about web, and
# the Swift block makes about native. A row here is a claim about the RULE.
# ---------------------------------------------------------------------------
CONCEPT_MATRIX = [
    pytest.param(
        concept(leader={"name": "Joshua Van", "probability": 0.5217, "field_size": 2}),
        True,
        id="unsettled concept WITH a leader is admitted (the #1939 class)",
    ),
    pytest.param(
        concept(
            key="event:cycling:vuelta-2026",
            domain="cycling",
            leader={"name": "Tadej Pogacar", "probability": 0.751, "field_size": 30},
        ),
        True,
        id="the Vuelta specimen — 0.751 of a 30-rider field is admitted",
    ),
    pytest.param(
        concept(),
        False,
        id="unsettled concept with NO leader is suppressed (the #1486 class)",
    ),
    pytest.param(
        concept(marquee_whathit=True, winner="Tadej Pogacar"),
        True,
        id="settled WHAT-HIT with a named winner is admitted",
    ),
    pytest.param(
        concept(marquee_whathit=True, result_summary="Won by 1:12"),
        True,
        id="settled WHAT-HIT with only a result_summary is admitted (#1935)",
    ),
    pytest.param(
        concept(marquee_whathit=True),
        False,
        id="settled WHAT-HIT that can name NOTHING is suppressed (#1935)",
    ),
    pytest.param(
        concept(marquee_whathit=True, winner="   ", result_summary="  "),
        False,
        id="whitespace is not a result (#1935)",
    ),
    pytest.param(
        # "Settled means settled." The server never sends both, so this row pins
        # the ORDER of the two arms rather than a live case — precisely the kind
        # of invariant that rots silently.
        concept(
            marquee_whathit=True,
            leader={"name": "Joshua Van", "probability": 0.5217},
        ),
        False,
        id="settled-but-resultless does NOT fall back to a leader",
    ),
]


@pytest.mark.parametrize("item,renderable", CONCEPT_MATRIX)
def test_concept_admission_matches_both_clients(item, renderable):
    assert feed_item_is_renderable(item, now=NOW) is renderable


# The Python copy faces malformed payloads for the SAME reason web does: native
# can write `leader != nil` because its decoder throws on a malformed leader
# first. Python has no such gate, and `{}` is truthy — so a presence test written
# "to match native" would match the source and not the behaviour.
@pytest.mark.parametrize(
    "leader",
    [
        pytest.param({}, id="an empty object"),
        pytest.param({"name": "   ", "probability": 0.6}, id="a blank name"),
        pytest.param({"name": "Joshua Van"}, id="a missing probability"),
        pytest.param({"name": "Joshua Van", "probability": "0.6"}, id="a string probability"),
        pytest.param({"name": "Joshua Van", "probability": True}, id="a bool probability"),
        pytest.param({"name": "Joshua Van", "probability": 1.4}, id="probability over 1.0 (gotcha #23)"),
        pytest.param({"name": "Joshua Van", "probability": -0.1}, id="a negative probability"),
        pytest.param("Joshua Van", id="a bare string instead of an object"),
        pytest.param(None, id="an explicit null"),
    ],
)
def test_an_unusable_leader_does_not_admit_the_card(leader):
    assert feed_item_is_renderable(concept(leader=leader), now=NOW) is False


class TestTournamentArm:
    """#1935 deleted the bare `marquee_whathit` arm from BOTH clients. This copy
    kept it, which is the headline half of #1951."""

    def test_golfers_admit(self):
        assert feed_item_is_renderable(
            tournament(golfers=[{"name": "Scottie Scheffler", "probability": 0.21}]),
            now=NOW,
        ) is True

    def test_golferless_whathit_is_suppressed(self):
        # The exact shape both clients drop and this predicate used to admit.
        # `TournamentCard`/`DiscoverTournamentCard` render the champion hero
        # inside `golfers.first`, so this card is a gradient, a chip and a title.
        assert feed_item_is_renderable(
            tournament(golfers=[], marquee_whathit=True), now=NOW
        ) is False

    def test_bare_tournament_is_suppressed(self):
        assert feed_item_is_renderable(tournament(), now=NOW) is False


class TestFuturesArm:
    """The one drift in the STRICT direction — this copy lacked web's fourth
    settlement authority, so it under-counted a healthy page."""

    def test_outcomes_admit(self):
        assert feed_item_is_renderable(
            futures(top_outcomes=[{"name": "Yes", "probability": 0.62}]), now=NOW
        ) is True

    @pytest.mark.parametrize(
        "data",
        [
            pytest.param({"resolved": True}, id="resolved"),
            pytest.param({"winner": "Yes"}, id="a named winner"),
            pytest.param({"status": "settled"}, id="a terminal status"),
            pytest.param({"status": "FINALIZED"}, id="a terminal status, upper case"),
        ],
    )
    def test_authoritative_settlement_admits(self, data):
        assert feed_item_is_renderable(futures(**data), now=NOW) is True

    def test_a_past_resolution_date_admits(self):
        past = (NOW - timedelta(days=2)).isoformat()
        assert feed_item_is_renderable(futures(resolution_date=past), now=NOW) is True

    def test_a_future_resolution_date_does_not(self):
        future = (NOW + timedelta(days=2)).isoformat()
        assert feed_item_is_renderable(futures(resolution_date=future), now=NOW) is False

    def test_an_unparseable_resolution_date_falls_closed(self):
        assert feed_item_is_renderable(futures(resolution_date="soon"), now=NOW) is False

    def test_a_zero_outcome_unsettled_future_is_suppressed(self):
        assert feed_item_is_renderable(futures(), now=NOW) is False


class TestStructuralArms:
    def test_an_event_is_always_renderable(self):
        # Unconditional on all three surfaces, and correctly so: an event card is
        # a real matchup plus a status/score, never a bare tile.
        assert feed_item_is_renderable({"type": "event", "data": {}}, now=NOW) is True

    def test_a_bundle_is_renderable_when_any_member_is(self):
        item = {
            "type": "bundle",
            "data": {"items": [concept(), concept(leader={"name": "X", "probability": 0.5})]},
        }
        assert feed_item_is_renderable(item, now=NOW) is True

    def test_an_all_empty_bundle_is_not(self):
        item = {"type": "bundle", "data": {"items": [concept(), concept()]}}
        assert feed_item_is_renderable(item, now=NOW) is False

    def test_recursion_is_bounded(self):
        item = {"type": "bundle", "data": {"items": []}}
        for _ in range(6):
            item = {"type": "bundle", "data": {"items": [item]}}
        assert feed_item_is_renderable(item, now=NOW) is False

    @pytest.mark.parametrize(
        "item",
        [
            pytest.param({"type": "wormhole", "data": {}}, id="an unknown type"),
            pytest.param({"type": "concept"}, id="a card with no data"),
            pytest.param({"type": "concept", "data": []}, id="a card whose data is a list"),
            pytest.param("not a card", id="a bare string"),
            pytest.param(None, id="a null"),
        ],
    )
    def test_it_falls_closed(self, item):
        assert feed_item_is_renderable(item, now=NOW) is False


# ---------------------------------------------------------------------------
# The specimen. A recorded production page SHAPE (`522caea4`, 2026-08-18) with
# the class counts it actually served, so the limb is graded on the thing it
# failed on rather than on a hand-built two-card page.
# ---------------------------------------------------------------------------
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
