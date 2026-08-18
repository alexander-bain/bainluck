"""The Discover floor alarm must fail when a whole CARD CLASS goes dark (#1948).

THE MEASUREMENT THIS SUITE EXISTS FOR, from the #1948 production run:

    renderable_cards: 41
    items_returned:   50
    type_concept:      9        41 = 50 - 9

Every concept card on the first page was unrenderable. The concept tier was
invisible on iOS and on web. The alarm PASSED, because 41 clears a floor of 12.

It had the incident in its own evidence block and reported healthy — the alarm
photographed the defect and called it fine. That is gotcha #53's shape
("an empty 200 is not an absence — it is a response shape"): the reading that
means "we are fine" and the reading that means "an entire tier is gone" produced
the same verdict, so the verdict carried no information. UX-P089 banked the same
lesson one cycle earlier, when a card-count limb would have been green through
the whole load-budget incident.
"""

import importlib

# `from app.tasks import flow_sentinel` resolves to the registered CELERY TASK
# proxy, not the module — the module's helpers are invisible through it. Import
# the module by path, as the sibling sentinel suites do.
fs = importlib.import_module("app.tasks.flow_sentinel")


def _card(kind, data):
    return {"type": kind, "data": data}


def _renderable_futures(n=20):
    return [_card("futures", {"top_outcomes": [{"name": "Yes", "probability": 0.6}]})
            for _ in range(n)]


def _dark_concepts(n=9):
    """A concept with neither a leader nor a whathit result — precisely what
    #1948 shipped, and the suppress state on both surfaces."""
    return [_card("concept", {"key": f"event:ufc:26aug{i}", "fight_count": 5,
                              "entry_count": 0})
            for i in range(n)]


# ---------------------------------------------------------------------------
# The regression
# ---------------------------------------------------------------------------


def test_an_alarm_that_photographs_the_incident_and_passes_is_gotcha_53_in_a_new_hat():
    """THE #1948 PAGE, REPRODUCED EXACTLY, MUST NOW FAIL.

    41 renderable of 50 items with all 9 concepts dark. Before this limb the
    verdict was PASS and the evidence block contained the whole incident.
    """
    items = _renderable_futures(41) + _dark_concepts(9)
    assert fs.feed_renderable_card_count(items) == 41, "precondition: the 41/50 page"

    failures = fs.discover_first_page_failures(
        renderable=41,
        elapsed_s=2.466,   # comfortably inside the 6s budget — limb 2 is green
        cache_status="miss",
        items=items,
    )

    limbs = {f["limb"] for f in failures}
    assert "starved" not in limbs, "41 clears the floor of 12 — limb 1 is green"
    assert "undeliverable" not in limbs, "2.466s clears the 6s budget — limb 2 is green"
    assert "dark_class" in limbs, (
        "the whole concept tier was dark and the alarm passed anyway — this is "
        "the defect the limb exists for"
    )

    dark = next(f for f in failures if f["limb"] == "dark_class")
    assert dark["card_type"] == "concept"
    assert dark["built"] == 9
    assert dark["renderable"] == 0
    assert "concept" in dark["detail"]


def test_the_concept_class_is_healthy_once_the_leaders_come_back():
    """The other direction, which gotcha #43 requires of every cap/alarm guard:
    the fix must turn this green, or the limb is just a permanent red."""
    items = _renderable_futures(41) + [
        _card("concept", {"key": "event:cycling:vuelta-2026",
                          "leader": {"name": "Tadej Pogacar", "probability": 0.751}})
        for _ in range(9)
    ]

    failures = fs.discover_first_page_failures(
        renderable=fs.feed_renderable_card_count(items),
        elapsed_s=2.466,
        cache_status="miss",
        items=items,
    )
    assert failures == []


def test_a_settled_concept_leading_with_its_result_is_renderable_not_dark():
    """"Settled means settled" — a WHAT-HIT card has an answer and is not dark
    merely because it has no probability."""
    items = _renderable_futures(41) + [
        _card("concept", {"key": "event:ufc:x", "marquee_whathit": True,
                          "winner": "Someone"})
        for _ in range(4)
    ]
    assert fs.feed_dark_card_classes(items) == []


# ---------------------------------------------------------------------------
# Not crying wolf
# ---------------------------------------------------------------------------


def test_a_card_type_that_is_simply_absent_is_not_dark():
    """Absent and broken are different facts (gotcha #53, again).

    A page with no concepts on it — a quiet week — must not fire. Only a type
    the server BUILT and no client can render is dark.
    """
    items = _renderable_futures(30)
    assert fs.feed_dark_card_classes(items) == []
    assert fs.discover_first_page_failures(
        renderable=30, elapsed_s=1.0, cache_status="miss", items=items
    ) == []


def test_one_unrenderable_card_of_a_type_is_a_card_bug_not_a_dark_class():
    """The floor-alarm discipline from `feed_renderable_card_count`'s own
    docstring: do not litigate individual cards. A noisy floor alarm gets muted,
    and a muted alarm is no alarm. One bad card belongs to the empty-envelope
    work (#1935); a whole tier with no survivors is a mechanism.
    """
    items = _renderable_futures(30) + _dark_concepts(1)
    assert fs.feed_dark_card_classes(items) == []


def test_a_class_with_one_survivor_is_not_dark():
    items = _renderable_futures(30) + _dark_concepts(8) + [
        _card("concept", {"key": "event:f1:gp",
                          "leader": {"name": "Max", "probability": 0.6}})
    ]
    assert fs.feed_dark_card_classes(items) == []


def test_a_dark_class_is_detected_for_any_type_not_just_concepts():
    """The limb is general. `tournament` going dark is the same defect — and
    concepts and tournaments share the empty-envelope classifier that #1935 was
    filed against, so both can go out the same way.
    """
    items = _renderable_futures(30) + [
        _card("tournament", {"name": "The Open"}) for _ in range(3)
    ]
    dark = fs.feed_dark_card_classes(items)
    assert [d["type"] for d in dark] == ["tournament"]
    assert dark[0]["built"] == 3


def test_two_classes_dark_at_once_report_two_failures():
    items = _renderable_futures(30) + _dark_concepts(4) + [
        _card("tournament", {"name": "The Open"}) for _ in range(2)
    ]
    failures = fs.discover_first_page_failures(
        renderable=30, elapsed_s=1.0, cache_status="miss", items=items
    )
    assert sorted(f["card_type"] for f in failures if f["limb"] == "dark_class") == [
        "concept",
        "tournament",
    ]


def test_a_bundle_is_dark_only_when_none_of_its_children_render():
    dark_bundle = _card("bundle", {"items": _dark_concepts(3)})
    live_bundle = _card("bundle", {"items": _renderable_futures(2)})

    assert fs.feed_dark_card_classes(_renderable_futures(30) + [dark_bundle] * 2)
    assert fs.feed_dark_card_classes(_renderable_futures(30) + [live_bundle] * 2) == []


# ---------------------------------------------------------------------------
# The limbs stay independent, and the thresholds are live
# ---------------------------------------------------------------------------


def test_the_older_two_limbs_still_fire_without_items():
    """`items` is optional — an older caller keeps limbs 1 and 2."""
    failures = fs.discover_first_page_failures(
        renderable=3, elapsed_s=9.0, cache_status="miss"
    )
    assert {f["limb"] for f in failures} == {"starved", "undeliverable"}


def test_a_redis_override_reaches_the_VERDICT_not_only_the_evidence():
    """The thresholds were default arguments, which Python binds ONCE at import.

    `_load_overrides()` reassigns those globals from Redis at the start of every
    run, so an operator raising the floor saw their new number echoed back in
    the evidence block while the verdict was still graded against the old one.
    The same trap would have swallowed `DISCOVER_DARK_CLASS_MIN` the day it
    shipped.
    """
    items = _renderable_futures(30) + _dark_concepts(1)
    assert fs.feed_dark_card_classes(items) == [], "precondition: 1 < min of 2"

    original = fs.DISCOVER_DARK_CLASS_MIN
    try:
        fs.DISCOVER_DARK_CLASS_MIN = 1
        assert [d["type"] for d in fs.feed_dark_card_classes(items)] == ["concept"]
        assert any(
            f["limb"] == "dark_class"
            for f in fs.discover_first_page_failures(
                renderable=30, elapsed_s=1.0, cache_status="miss", items=items
            )
        ), "the override reached feed_dark_card_classes but not the verdict"
    finally:
        fs.DISCOVER_DARK_CLASS_MIN = original

    original_floor = fs.DISCOVER_FIRST_PAGE_FLOOR
    try:
        fs.DISCOVER_FIRST_PAGE_FLOOR = 40
        assert any(
            f["limb"] == "starved"
            for f in fs.discover_first_page_failures(
                renderable=30, elapsed_s=1.0, cache_status="miss"
            )
        ), "raising the floor via the override did not change the verdict"
    finally:
        fs.DISCOVER_FIRST_PAGE_FLOOR = original_floor


def test_the_dark_class_min_is_a_registered_tunable():
    """Every other threshold in this flow is Redis-overridable; a hard-coded one
    cannot be widened during an incident without a deploy."""
    import inspect

    src = inspect.getsource(fs._load_overrides)
    assert "flow:sentinel_discover_dark_class_min" in src
    assert "DISCOVER_DARK_CLASS_MIN" in src
