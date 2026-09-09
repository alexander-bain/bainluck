"""D1 clause c (#4066) — a bundle's reason is its shared question, not a count.

THE DEFECT, read off production 2026-09-08 21:07Z, `GET /api/feed?limit=20`.
SEVEN of the twenty served items were bundles, and all seven gave a count:

    item 3   headline '2028 Election'   reason '2 related markets'
    item 5   headline 'AI'              reason '2 related markets'
    item 6   headline 'Awards Season'   reason '2 related markets'
    item 7   headline 'Fed & Rates'     reason '3 related markets'
    item 9   headline 'Middle East'     reason '4 related markets'
    item 11  headline 'World Cup'       reason '3 related markets'
    (rendered on the web card as "· 2 related", `ThemeBundleCard.tsx`)

A count says how many rows are behind the chevron. It does not say why the rows
belong together, which is the only thing that earns a group ONE slot instead of
its members taking their own. Rulings 143/145 and the commissioned plan both ask
for the editorial question instead.

🔴 THE ABSENCE ASSERTION IS THE POINT. "2 related markets" is not a substring of
the fixed output, so each test asserts the exact served string is gone as well as
naming the sentence that replaced it — a test that only checked "the reason is
non-empty" passed on the defect.
"""

import pytest

from app.utils.discover_bundles import (
    AUTHORED_STORY_QUESTIONS,
    AUTHORED_STORY_TITLES,
    _make_awards_bundle_item,
    _make_theme_bundle_item,
    assemble_story_theme_bundles,
    resolve_story_question,
)


def _member(market_id: int, name: str, score: float = 80.0) -> dict:
    return {
        "type": "futures",
        "score": score,
        "reason": "reason",
        "headline": name,
        "_sort_time": 0.0,
        "data": {
            "id": market_id,
            "name": name,
            "llm_sport_category": "politics",
            "discover_card": {},
        },
    }


# The two members production folded into item 3, by name.
US_2028 = [
    _member(101, "2028 U.S. Presidential Election winner?", 86.0),
    _member(102, "2028 Democratic presidential nominee", 84.0),
]


# ── The question itself ──────────────────────────────────────────────────────


def test_every_authored_story_title_has_an_authored_question():
    """A family we bothered to name is a family we can state the question for.

    Without this, adding a title (the cheap edit) silently leaves the family
    folding on a derived phrase or not folding at all.
    """
    missing = sorted(set(AUTHORED_STORY_TITLES) - set(AUTHORED_STORY_QUESTIONS))

    assert missing == []


def test_every_authored_question_is_a_question():
    not_questions = sorted(
        key for key, text in AUTHORED_STORY_QUESTIONS.items() if not text.endswith("?")
    )

    assert not_questions == []


def test_no_authored_question_counts_its_members():
    """The failure mode being guarded is a count wearing a question mark."""
    for key, text in AUTHORED_STORY_QUESTIONS.items():
        assert "related" not in text.lower(), key
        assert "markets" not in text.lower(), key


def test_an_authored_family_uses_its_authored_question():
    question, source = resolve_story_question(
        "story:us_2028_election", [m["data"]["name"] for m in US_2028]
    )

    assert question == "Who wins in 2028?"
    assert source == "authored"


def test_an_unauthored_family_falls_back_to_the_phrase_its_members_share():
    question, source = resolve_story_question(
        "story:nobody_authored_this",
        [
            "Best Actor at the 99th Academy Awards",
            "Best Actress at the 99th Academy Awards",
        ],
    )

    # "Actor"/"Actress" differ, so the run they share starts at "at".
    assert question == "Who wins at the 99th academy awards?"
    assert source == "derived"


def test_a_shared_phrase_is_never_manufactured_out_of_one_members_title():
    """The bug this guard exists for, caught while writing it.

    `_derive_race_label` falls back to the SHORTEST MEMBER NAME when the members
    share nothing. Routed through the question builder, two markets with nothing
    in common produced "Who wins Oil above $90?" — a group asserting a common
    question that does not exist, which is worse than the count it replaced.
    """
    question, source = resolve_story_question(
        "story:nobody_authored_this", ["Oil above $90", "Taylor Swift engaged"]
    )

    assert "Oil above $90" not in (question or "")
    assert source != "derived"


def test_an_unauthored_story_key_still_folds_on_a_weaker_question():
    """Queue 307 made ANY story_key foldable; clause (c) does not undo that.

    The key itself asserts the members are one story, so the family keeps its
    slot with a question naming the story — never with a count. Authoring a
    sentence in AUTHORED_STORY_QUESTIONS upgrades it.
    """
    question, source = resolve_story_question(
        "story:macro_widgets", ["Oil above $90", "Taylor Swift engaged"]
    )

    assert question == "What's the latest on Macro Widgets?"
    assert source == "story_title"
    assert "related" not in question.lower()


# ── What the bundle serves ───────────────────────────────────────────────────


def test_the_2028_bundle_asks_its_question_instead_of_counting():
    bundle = _make_theme_bundle_item("story:us_2028_election", US_2028)

    assert bundle is not None
    assert bundle["reason"] == "Who wins in 2028?"
    assert bundle["data"]["shared_question"] == "Who wins in 2028?"
    # The served defect, verbatim.
    assert bundle["reason"] != "2 related markets"
    assert "related markets" not in bundle["reason"]
    # The title the chip renders is unchanged — this is a new line, not a rename.
    assert bundle["headline"] == "2028 Election"
    assert bundle["data"]["debug_bundles"]["question_source"] == "authored"


def test_a_family_with_no_statable_question_is_not_folded():
    """It yields the slot rather than spending one on "N related markets".

    Reachable when the story_key derives no title either — the only remaining
    case after the story-title tier.
    """
    strangers = [
        _member(201, "Oil above $90 in December?"),
        _member(202, "Taylor Swift engaged by New Year?"),
    ]

    assert _make_theme_bundle_item("story:", strangers) is None


def test_an_unfoldable_family_leaves_its_members_in_the_feed():
    """The members must not vanish with the bundle they did not get."""
    strangers = [
        _member(201, "Oil above $90 in December?"),
        _member(202, "Taylor Swift engaged by New Year?"),
    ]

    out = assemble_story_theme_bundles(
        [dict(item, _story_key_override="story:") for item in strangers]
    )
    served_ids = {item["data"]["id"] for item in out if item.get("type") == "futures"}

    assert served_ids == {201, 202}


def test_an_awards_cluster_asks_who_wins_the_race_it_shares():
    members = [
        _member(301, "Best Actor at the 99th Academy Awards"),
        _member(302, "Best Actress at the 99th Academy Awards"),
    ]

    bundle = _make_awards_bundle_item("group:oscars99", members)

    assert bundle["reason"].startswith("Who wins ")
    assert bundle["reason"].endswith("?")
    assert bundle["reason"] == f"Who wins {bundle['headline']}?"
    assert "related markets" not in bundle["reason"]
    assert bundle["data"]["shared_question"] == bundle["reason"]


@pytest.mark.parametrize("story_key", sorted(AUTHORED_STORY_QUESTIONS))
def test_every_authored_family_folds(story_key: str):
    """No authored family loses its bundle to the new None path."""
    members = [_member(401, "Market A"), _member(402, "Market B")]

    bundle = _make_theme_bundle_item(story_key, members)

    assert bundle is not None
    assert bundle["reason"] == AUTHORED_STORY_QUESTIONS[story_key]
