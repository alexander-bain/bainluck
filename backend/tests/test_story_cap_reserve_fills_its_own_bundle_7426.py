"""#7426 — a story that folds into ONE card must not be capped as if it took N.

Measured on production 2026-09-20 (`783430a4`): ``diversify_quality_families``
caps ``story:middle_east_conflict`` at 4, and ``assemble_story_theme_bundles``
folded exactly those four into a single "Middle East" card whose
``max_items_per_bundle`` is 6. ~25 distinct eligible questions competed for the
four seats, so the surplus was not demoted — it was deleted from the feed. One
of them, `3484764` "Iran leadership change by...?" (tier 2, 408,757 in 24h, the
cohort's second-highest volume), was absent from all 131 served items while
serving correctly in the politics-tagged slice.

The repair carries the story cap's surplus out of band and spends it only inside
a bundle that actually forms. The two directions this file holds (gotcha #43):
the bundle GAINS the surplus, AND nothing about slot allocation moves — the
ranked list the cap returns is unchanged, an unfolded story never serves a
reserved item, and the reserve can never conjure a bundle that would not have
formed.
"""

from app.utils.discover_bundles import (
    _with_story_overflow,
    assemble_story_theme_bundles,
)
from app.utils.feed_market_quality import (
    STORY_OVERFLOW_RESERVE,
    diversify_quality_families,
)

MIDDLE_EAST = "story:middle_east_conflict"
# The production cap for that story, read off `diversify_quality_families`. The
# point of the fix is that the bundle is no longer bounded by this number.
MIDDLE_EAST_SLOT_CAP = 4


def _item(
    market_id: int,
    name: str,
    *,
    score: float,
    story: str = MIDDLE_EAST,
    family: str | None = None,
) -> dict:
    return {
        "type": "futures",
        "score": score,
        "_rank_score": score,
        "_sort_time": 1000 + market_id,
        "reason": "reason",
        "headline": name,
        "data": {
            "id": market_id,
            "name": name,
            "llm_sport_category": "politics",
            "source": "kalshi",
        },
        "_quality_story_key": story,
        # Distinct by default: the EXACT-family cap is a same-wording cap and is
        # not what this file is about.
        "_quality_family_key": family or f"family-{market_id}",
    }


def _middle_east_cohort(count: int) -> list[dict]:
    """``count`` distinct Middle East questions, ranked highest id first."""
    names = [
        "Will the U.S. invade Iran before 2027?",
        "Peak traffic through the Strait of Hormuz?",
        "US x Iran ceasefire continues through October 31?",
        "Will the Iranian regime fall before 2027?",
        "Iran leadership change by...?",
        "Prime Minister of Israel after the next election?",
        "US-Iran nuclear deal?",
        "Foreign intervention in Gaza by..?",
        "Israeli airspace closed by...?",
        "US obtains Iranian enriched uranium by...?",
    ]
    assert count <= len(names)
    return [
        _item(i + 1, names[i], score=100 - i)
        for i in range(count)
    ]


def _cap(items: list[dict]) -> list[dict]:
    """The production call shape (`_dedupe_and_cap` in routes/feed.py)."""
    return diversify_quality_families(
        items, exact_family_cap=1, story_family_cap=5
    )


# ── THE SHIP ─────────────────────────────────────────────────────────────────


def test_the_middle_east_card_seats_every_question_it_has_room_for():
    """The reader-visible half: six distinct questions, one card, six seats.

    Before the fix this bundle carried four — the slot cap — and the other two
    questions were unreachable from Discover entirely.
    """
    cohort = _middle_east_cohort(6)

    kept = _cap(cohort)
    result = assemble_story_theme_bundles(kept)

    bundles = [it for it in result if it["type"] == "bundle"]
    assert len(bundles) == 1, "the story must still take exactly one feed slot"
    bundle = bundles[0]
    assert bundle["data"]["story_key"] == MIDDLE_EAST
    assert sorted(bundle["data"]["member_ids"]) == [1, 2, 3, 4, 5, 6]
    assert bundle["data"]["item_count"] == 6


def test_the_surplus_question_the_issue_named_reaches_the_card():
    """`Iran leadership change by...?` is the 5th-ranked question in the cohort.

    It is the specimen #7426 was filed on: it must be ON the card, not merely
    "somewhere in the payload".
    """
    cohort = _middle_east_cohort(6)

    bundle = next(
        it
        for it in assemble_story_theme_bundles(_cap(cohort))
        if it["type"] == "bundle"
    )

    names = [m["data"]["name"] for m in bundle["data"]["items"]]
    assert "Iran leadership change by...?" in names


def test_a_bundle_never_seats_more_than_its_own_maximum():
    """Ten questions, one card, six seats — the reserve fills, it does not flood."""
    bundle = next(
        it
        for it in assemble_story_theme_bundles(_cap(_middle_east_cohort(10)))
        if it["type"] == "bundle"
    )

    assert bundle["data"]["item_count"] == 6


# ── NOTHING ABOUT SLOTS MOVES ────────────────────────────────────────────────


def test_the_cap_still_returns_exactly_the_rows_it_returned_before():
    """The reserve is side state, not a widened return value.

    Every ranking, first-page composition and slot decision downstream reads
    this list, so if it grew by one the fix would be a feed change wearing a
    bundle change's clothes.
    """
    cohort = _middle_east_cohort(10)

    kept = _cap(cohort)

    assert [it["data"]["id"] for it in kept] == [1, 2, 3, 4]
    assert len(kept) == MIDDLE_EAST_SLOT_CAP


def test_a_story_that_cannot_fold_never_serves_a_reserved_item():
    """No bundle ⇒ today's behaviour exactly: four cards, and the surplus stays gone.

    A reserved item is not in the list the bundler walks, so there is no path by
    which it can be emitted on its own — this asserts that rather than assuming
    it.
    """
    cohort = _middle_east_cohort(6)
    kept = _cap(cohort)

    # `min_items` unreachable ⇒ the fold cannot happen for any cluster.
    result = assemble_story_theme_bundles(kept, min_items=99)

    assert [it["type"] for it in result] == ["futures"] * MIDDLE_EAST_SLOT_CAP
    assert [it["data"]["id"] for it in result] == [1, 2, 3, 4]


def test_the_reserve_cannot_conjure_a_bundle_that_would_not_have_formed():
    """A cap of 1 means one card from this story, and it still does.

    `story:drake_iceman` and `story:music_charts` are cap-1 dials. One survivor
    can never reach `min_items=2`, so the reserve must stay unspent rather than
    turn a deliberate single card into a pack.
    """
    cohort = [
        _item(1, "Will Drake release Iceman in 2026?", score=90, story="story:drake_iceman"),
        _item(2, "Will Iceman go number one?", score=80, story="story:drake_iceman"),
        _item(3, "Iceman certified platinum in 2026?", score=70, story="story:drake_iceman"),
    ]

    kept = _cap(cohort)
    result = assemble_story_theme_bundles(kept)

    assert len(kept) == 1
    assert [it["type"] for it in result] == ["futures"]


# ── THE RESERVE'S OWN BOUNDS ─────────────────────────────────────────────────


def test_the_reserve_holds_only_the_story_it_came_from():
    """A cross-story seat would put an unrelated question on the card."""
    members = [_item(1, "Will the U.S. invade Iran before 2027?", score=90)]
    members[0]["_story_overflow_members"] = [
        _item(2, "Iran leadership change by...?", score=88),
        _item(3, "Will Russia and Ukraine agree a ceasefire?", score=87,
              story="story:russia_ukraine"),
    ]

    topped = _with_story_overflow(members, MIDDLE_EAST)

    assert [it["data"]["id"] for it in topped] == [1, 2]


def test_a_same_wording_duplicate_is_not_revived_into_the_card():
    """The EXACT-family cap is a same-wording cap; its rejects stay rejected.

    Reviving one would put two phrasings of one question on a single card, which
    is the thing that cap exists to prevent.
    """
    cohort = [
        _item(1, "Will the U.S. invade Iran before 2027?", score=90, family="shared"),
        _item(2, "Will the US invade Iran before 2027?", score=89, family="shared"),
        _item(3, "Peak traffic through the Strait of Hormuz?", score=88),
    ]

    kept = _cap(cohort)
    reserves = [it.get("_story_overflow_members") for it in kept]

    assert [it["data"]["id"] for it in kept] == [1, 3]
    assert all(not r for r in reserves), "a family-cap reject must not be reserved"


def test_the_reserve_is_bounded():
    """Carrying more than a bundle can seat is dead weight in every request."""
    cohort = _middle_east_cohort(10) + [
        _item(20 + i, f"Iran sanctions question {i}?", score=50 - i) for i in range(6)
    ]

    kept = _cap(cohort)

    reserve = kept[0].get("_story_overflow_members") or []
    assert len(reserve) == STORY_OVERFLOW_RESERVE


def test_every_survivor_carries_the_reserve():
    """Hanging it off one carrier would make that row's survival load-bearing."""
    kept = _cap(_middle_east_cohort(6))

    reserves = [it.get("_story_overflow_members") for it in kept]
    assert all(r is not None for r in reserves)
    # One shared list, not four copies.
    assert all(r is reserves[0] for r in reserves)


def test_the_reserve_never_reaches_a_reader():
    """Private keys are prefix-stripped at serve time; the members carry none."""
    bundle = next(
        it
        for it in assemble_story_theme_bundles(_cap(_middle_east_cohort(6)))
        if it["type"] == "bundle"
    )

    for member in bundle["data"]["items"]:
        assert not [k for k in member if k.startswith("_")]
