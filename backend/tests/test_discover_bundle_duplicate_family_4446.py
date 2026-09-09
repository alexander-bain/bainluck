"""#4446 — a group card shows one row per question, not one row per venue.

The specimen is production's own page one on 2026-09-09: the World Cup bundle
served Kalshi's "2027 FIFA Women's World Cup Champion" and Polymarket's "FIFA
Women's World Cup 2027 Winner" two rows apart, both above the fold (all three
members render in the collapsed peek at ``PEEK_COUNT = 5``), inside a card whose
whole job is to fold a family.

Every fixture name here is a title production actually served that morning, and
the controls are its actual NEIGHBOURS rather than invented near-misses — a
deduper is only as good as the cards it declines to delete, and the cards it can
delete are the ones sitting next to the duplicate.
"""

from app.utils.discover_bundles import assemble_story_theme_bundles

WC_STORY = "story:fifa_world_cup"
SLAM_STORY = "story:grand_slam_tennis"


def _member(
    market_id: int,
    name: str,
    *,
    source: str,
    story_key: str,
    score: float,
    category: str = "soccer",
) -> dict:
    return {
        "type": "futures",
        "score": score,
        "reason": "reason",
        "headline": name,
        "data": {
            "id": market_id,
            "name": name,
            "llm_sport_category": category,
            "source": source,
        },
        "_quality_story_key": story_key,
        "_sort_time": 1000 + market_id,
    }


def _world_cup_members() -> list[dict]:
    """The three rows the World Cup bundle carried, in served rank order."""
    return [
        _member(56775503, "2027 FIFA Women's World Cup Champion", source="kalshi", story_key=WC_STORY, score=90),
        _member(56775477, "2030 FIFA World Cup Champion", source="kalshi", story_key=WC_STORY, score=88),
        _member(60607659, "FIFA Women's World Cup 2027 Winner", source="polymarket", story_key=WC_STORY, score=70),
    ]


def _bundle(result: list[dict]) -> dict | None:
    return next((it for it in result if it["type"] == "bundle"), None)


def test_the_world_cup_bundle_serves_the_womens_2027_question_once():
    result = assemble_story_theme_bundles(_world_cup_members())

    bundle = _bundle(result)
    assert bundle is not None
    assert bundle["data"]["member_ids"] == [56775503, 56775477], (
        "the Polymarket restatement of the Kalshi row folds; the 2030 men's "
        "tournament beside it is a different question and stays"
    )
    assert bundle["data"]["item_count"] == 2


def test_the_folded_row_does_not_come_back_as_its_own_card():
    """The half a fold can silently undo.

    Members that a bundle does not claim fall through the emit loop and are
    re-emitted as standalone cards. A dedupe that only trimmed the member list
    would therefore move the duplicate further down page one rather than remove
    it — the reader still sees the question twice, just further apart.
    """
    result = assemble_story_theme_bundles(_world_cup_members())

    standalone_ids = [
        it["data"]["id"] for it in result if it["type"] == "futures"
    ]
    assert 60607659 not in standalone_ids
    assert standalone_ids == []


def test_the_mens_and_womens_us_open_both_survive_in_one_bundle():
    """The control this fix had to be built around, not tuned past.

    These two rows share a ``canonical_market_key`` (``tennis::championship:2026``)
    and sat in ONE bundle on the same page as the duplicate, so the obvious
    cheap key would have deleted the women's US Open. They are different
    questions and both stay.
    """
    members = [
        _member(114159, "2026 Men's US Open Winner (Tennis)", source="polymarket", story_key=SLAM_STORY, score=90, category="tennis"),
        _member(34277839, "US Open Women's Singles Winner", source="kalshi", story_key=SLAM_STORY, score=85, category="tennis"),
    ]

    bundle = _bundle(assemble_story_theme_bundles(members))

    assert bundle is not None
    assert bundle["data"]["item_count"] == 2
    assert sorted(bundle["data"]["member_ids"]) == sorted([114159, 34277839])


def test_two_listings_from_one_venue_are_that_venues_business():
    """The venue gate. Kalshi listing two similar questions is not our duplicate
    to fold — the pair that motivated this fix is one question on two venues."""
    members = [
        _member(1, "2027 FIFA Women's World Cup Champion", source="kalshi", story_key=WC_STORY, score=90),
        _member(2, "FIFA Women's World Cup 2027 Winner", source="kalshi", story_key=WC_STORY, score=70),
    ]

    bundle = _bundle(assemble_story_theme_bundles(members))

    assert bundle is not None
    assert bundle["data"]["item_count"] == 2


def test_the_duplicate_does_not_spend_a_member_slot():
    """The fold runs BEFORE the cap, so the freed slot goes to a real question.

    With room for two members, a cluster of [A, A-restated, B] must serve A and
    B. Folding after the cap would have served A and A-restated and dropped B —
    the duplicate would then cost the reader a question as well as a row.
    """
    members = _world_cup_members()
    members[1], members[2] = members[2], members[1]  # duplicate ranks above B

    bundle = _bundle(assemble_story_theme_bundles(members, max_items_per_bundle=2))

    assert bundle is not None
    assert bundle["data"]["member_ids"] == [56775503, 56775477]


def test_a_pair_that_is_only_a_duplicate_is_left_alone():
    """Conservative floor: dedupe must never be a delete.

    Two members that are the same question have nothing left to fold into a
    bundle, so the cluster drops below ``min_items`` and is returned untouched —
    both rows still ship. Suppressing one here would remove a card with no
    surviving bundle row to represent it.
    """
    members = [
        _member(56775503, "2027 FIFA Women's World Cup Champion", source="kalshi", story_key=WC_STORY, score=90),
        _member(60607659, "FIFA Women's World Cup 2027 Winner", source="polymarket", story_key=WC_STORY, score=70),
    ]

    result = assemble_story_theme_bundles(members)

    assert [it["type"] for it in result] == ["futures", "futures"]
    assert [it["data"]["id"] for it in result] == [56775503, 60607659]
