"""#4147 — an authored shared question must be true of the members it heads.

THE DEFECT, read off production 2026-09-10 20:36Z, `GET /api/feed?limit=250`.
Slot 36 served a group headed by one question in the singular over two
tournaments three years apart:

    Who wins the World Cup?
      · 2027 FIFA Women's World Cup Champion   soccer:FIFA_WC:championship:2027
      · 2030 FIFA World Cup Champion           soccer:FIFA_WC:championship:2030

A reader who restates the header — the D1 bar — asks "who wins the World Cup?"
and is handed Spain at 20% and France at 12%, and cannot tell which of them
answers it. Neither does; the question has no single answer as posed.

The mechanism: `resolve_story_question` reads AUTHORED_STORY_QUESTIONS by
`story_key` alone and never looks at who is in the group, so the authored
sentence bypasses the guard the derived path already carries ("No shared phrase
means no question means no bundle").

🔴 THE AXIS IS SEASON, NOT COHORT, AND THE NEGATIVE CASES ARE THE POINT. The
intuitive key — men's vs women's is a different cohort — was checked against all
nine theme bundles served at that timestamp and is wrong: it would also split
`story:grand_slam_tennis`, whose members are the US Open men's and women's
singles, `tennis::championship:2026` for BOTH, the same tournament in the same
season and a group a reader wants kept. Season splits the World Cup and touches
nothing else — 1 of the 9 served bundles changes, and it is the defect.

🔴 AN UNKNOWN SEASON IS NOT A DISAGREEMENT. Four of those nine (ai, macro_rates,
middle_east_conflict, russia_ukraine) carry members with no canonical key at all.
A test suite that only proved "the World Cup splits" would pass on a fix that
also dissolved those four on missing data, so silence is asserted here in both
its forms — every member silent, and only one member speaking.
"""

import pytest

from app.utils.discover_bundles import (
    AUTHORED_STORY_QUESTIONS,
    _make_theme_bundle_item,
    _member_season,
    _members_span_multiple_seasons,
    assemble_story_theme_bundles,
)


def _member(
    market_id: int,
    name: str,
    canonical_market_key: str | None,
    score: float = 72.0,
    llm_sport_category: str = "soccer",
) -> dict:
    """A feed item in the shape the bundler consumes.

    `llm_sport_category` is a real parameter and not decoration: it is an input
    to `_theme_story_key`, so a fixture that hardcodes it puts members in the
    WRONG family the moment a test reaches `assemble_story_theme_bundles`. The
    tennis pair below keyed as `story:minor_soccer_leagues` until this was
    threaded through, and the end-to-end control caught it.
    """
    return {
        "type": "futures",
        "score": score,
        "reason": "reason",
        "headline": name,
        "_sort_time": 0.0,
        "data": {
            "id": market_id,
            "name": name,
            "llm_sport_category": llm_sport_category,
            "canonical_market_key": canonical_market_key,
            "discover_card": {},
        },
    }


# The exact pair production folded into slot 36, by id, name and canonical key.
WORLD_CUP_2027_2030 = [
    _member(
        56775503,
        "2027 FIFA Women's World Cup Champion",
        "soccer:FIFA_WC:championship:2027",
    ),
    _member(
        56775477,
        "2030 FIFA World Cup Champion",
        "soccer:FIFA_WC:championship:2030",
    ),
]

# Slot 6 of the same payload: same tournament, same season, two cohorts. The
# group a cohort key would have wrongly dissolved.
GRAND_SLAM_2026 = [
    _member(
        1, "US Open Women's Singles Winner", "tennis::championship:2026", 83.0, "tennis"
    ),
    _member(
        2, "US Open Men's Singles Winner", "tennis::championship:2026", 82.0, "tennis"
    ),
]


# ── The defect ───────────────────────────────────────────────────────────────


def test_world_cup_members_span_two_seasons():
    assert _members_span_multiple_seasons(WORLD_CUP_2027_2030) is True


def test_a_question_is_not_served_over_two_seasons():
    """The live specimen folds no more."""
    assert (
        _make_theme_bundle_item("story:fifa_world_cup", WORLD_CUP_2027_2030) is None
    )


def test_the_false_sentence_is_gone_from_the_served_payload():
    """The absence assertion — the authored string must not reach a reader.

    Named explicitly rather than inferred from `is None`, so that a future
    change which keeps the card and merely re-words the header still fails.
    """
    bundle = _make_theme_bundle_item("story:fifa_world_cup", WORLD_CUP_2027_2030)
    served = "" if bundle is None else repr(bundle)
    assert AUTHORED_STORY_QUESTIONS["story:fifa_world_cup"] not in served
    assert "Who wins the World Cup?" not in served


# ── The negative cases: what must keep folding ───────────────────────────────


def test_one_tournament_two_cohorts_still_folds():
    """A cohort key would have dissolved this. A season key must not."""
    bundle = _make_theme_bundle_item("story:grand_slam_tennis", GRAND_SLAM_2026)
    assert bundle is not None
    assert bundle["data"]["shared_question"] == "Who wins the Slam?"
    assert bundle["data"]["item_count"] == 2


def test_members_that_all_state_the_same_season_still_fold():
    same = [
        _member(
            11, "Texas Senate winner?", "politics:US:championship:2027", 74.0, "politics"
        ),
        _member(
            12, "Ohio Senate winner?", "politics:US:championship:2027", 73.0, "politics"
        ),
    ]
    assert _members_span_multiple_seasons(same) is False
    bundle = _make_theme_bundle_item("story:us_state_races", same)
    assert bundle is not None
    assert bundle["data"]["shared_question"] == "Who wins the big state races?"


def test_silence_from_every_member_is_not_a_disagreement():
    """russia_ukraine's shape: no member carries a canonical key at all."""
    silent = [
        _member(21, "Russia x Ukraine ceasefire agreement by...?", None, 85.0),
        _member(22, "Putin out as President of Russia by December 31, 2026?", None),
    ]
    assert _members_span_multiple_seasons(silent) is False
    bundle = _make_theme_bundle_item("story:russia_ukraine", silent)
    assert bundle is not None
    assert bundle["data"]["shared_question"] == "How does the war in Ukraine end?"


def test_one_speaker_alone_is_not_a_disagreement():
    """ai's shape: one member states a season, the other states none."""
    mixed = [
        _member(
            31, "Best AI at the end of 2026?", "tech::championship:2026", 91.0, "tech"
        ),
        _member(32, "DeepSeek market share this week", None, 88.0, "tech"),
    ]
    assert _members_span_multiple_seasons(mixed) is False
    bundle = _make_theme_bundle_item("story:ai", mixed)
    assert bundle is not None
    assert bundle["data"]["shared_question"] == "Which AI model comes out on top?"


# ── End to end: SPLIT means split, not delete ────────────────────────────────
#
# The whole change hangs on what `assemble_story_theme_bundles` does with a
# `None` from the fold. If a refused bundle dropped its members, this "fix"
# would delete two real markets from page one instead of ungrouping them —
# strictly worse than the false header it set out to remove. Asserted here at
# the assembly level rather than trusted from `_make_theme_bundle_item`'s
# docstring, because that is the sentence a reader actually experiences.


def test_a_refused_bundle_returns_its_members_as_their_own_cards():
    out = assemble_story_theme_bundles(list(WORLD_CUP_2027_2030))

    assert [item["type"] for item in out] == ["futures", "futures"]
    assert {item["data"]["id"] for item in out} == {56775503, 56775477}
    # Nothing folded, so nothing may claim the group's question.
    assert not any(item.get("type") == "bundle" for item in out)


def test_a_kept_bundle_still_folds_end_to_end():
    """The positive control: the same path still produces a bundle."""
    out = assemble_story_theme_bundles(list(GRAND_SLAM_2026))

    bundles = [item for item in out if item.get("type") == "bundle"]
    assert len(bundles) == 1
    assert bundles[0]["data"]["shared_question"] == "Who wins the Slam?"
    assert bundles[0]["data"]["item_count"] == 2


# ── The season reader ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "key,expected",
    [
        ("soccer:FIFA_WC:championship:2027", "2027"),
        ("tennis::championship:2026", "2026"),
        ("basketball:NBA:championship:2025-26", "2025-26"),
        # Empty season axis — the key exists but says nothing about when.
        ("economics::championship:", None),
        # Not four parts: malformed, so unknown rather than an IndexError.
        ("soccer:FIFA_WC:championship", None),
        ("a:b:c:d:e", None),
        ("", None),
        (None, None),
        (12345, None),
    ],
)
def test_member_season_reads_the_fourth_axis(key, expected):
    assert _member_season(_member(1, "n", key)) == expected


def test_a_member_with_no_data_block_is_silent():
    assert _member_season({"type": "futures"}) is None
    assert _member_season({}) is None
