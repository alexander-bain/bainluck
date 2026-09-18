"""The family left behind by the #2602/#6444 split says something true of itself.

#2602/#6444 gave every numbered card its own key (`story:ufc_event:331`) and its
own sentence ("What happens at UFC 331?"). It did not touch the sentence on the
key the split leaves behind.

That residual key is not a leftover: `_UFC_NUMBERED_EVENT_RE` deliberately sends
the *unnumbered* names to it, and the minting rule says why in as many words —
"a bare 'UFC' with no number names no single card". The arm that reaches it is
``\\bufc\\b.*\\b(title|champion|main event)\\b``. So the family is, by
construction, exactly the season-long questions — and it was still asking "Who
wins on the next card?", which is false of every one of them.

A phone-width shot of Discover on 2026-09-18 07:35Z had it as the first card:
three of "Who will be UFC Heavyweight / Featherweight / Bantamweight champion at
the end of 2026?" under the header "UFC · Who wins on the next card?".

The specimens below are the live population verbatim (`futures_markets`,
2026-09-18): 37 rows matched the arm, all of them 2026 championship questions,
none of them a fight. The two shapes the venue writes are both pinned.
"""

import pytest

from app.utils.discover_bundles import (
    AUTHORED_STORY_QUESTIONS,
    assemble_story_theme_bundles,
)
from app.utils.feed_market_quality import UFC_EVENT_STORY_PREFIX, _story_key

#: Verbatim production rows (futures_markets, 2026-09-18). Both shapes the venue
#: writes into this family: the per-division "who holds it at the end" question,
#: and the per-fighter "does he get one at all" question.
LIVE_DIVISION_TITLES = [
    "Who will be UFC Heavyweight champion at the end of 2026?",
    "Who will be UFC Featherweight champion at the end of 2026?",
    "Who will be UFC Bantamweight champion at the end of 2026?",
]
LIVE_FIGHTER_TITLES = [
    "Will Ciryl Gane become UFC champion in 2026?",
    "Will Merab Dvalishvili become UFC champion in 2026?",
    "Who will become a UFC champion in 2026?",
]


def _item(market_id: int, name: str, score: float = 70.0) -> dict:
    return {
        "type": "futures",
        "score": score,
        "_sort_time": 0,
        "data": {
            "id": market_id,
            "name": name,
            "llm_sport_category": "mma",
            "source": "kalshi",
        },
    }


def _only_bundle(names: list[str]) -> dict:
    bundles = [
        item
        for item in assemble_story_theme_bundles(
            [_item(90000 + i, name) for i, name in enumerate(names)]
        )
        if item["type"] == "bundle"
    ]
    assert len(bundles) == 1, [b["data"]["story_key"] for b in bundles]
    return bundles[0]


class TestTheResidualFamilyIsWhatWeThinkItIs:
    """If these fail, the fix below is aimed at a family that no longer exists."""

    @pytest.mark.parametrize("name", LIVE_DIVISION_TITLES + LIVE_FIGHTER_TITLES)
    def test_a_season_long_title_question_lands_on_the_residual_key(self, name):
        assert _story_key(name, "mma") == "story:ufc_events"

    @pytest.mark.parametrize("name", LIVE_DIVISION_TITLES + LIVE_FIGHTER_TITLES)
    def test_and_never_mints_a_card_of_its_own(self, name):
        key = _story_key(name, "mma")
        assert not key.startswith(UFC_EVENT_STORY_PREFIX), key


class TestTheQuestionIsTrueOfTheMembers:
    def test_the_residual_family_no_longer_promises_a_card(self):
        """The defect, stated directly, on the exact copy the reader saw."""
        assert (
            AUTHORED_STORY_QUESTIONS["story:ufc_events"]
            != "Who wins on the next card?"
        )

    @pytest.mark.parametrize(
        "names", [LIVE_DIVISION_TITLES, LIVE_FIGHTER_TITLES], ids=["division", "fighter"]
    )
    def test_neither_live_shape_is_headed_by_an_occasion(self, names):
        """No "next", no "card", no "tonight" — the members span a season.

        Asserted on the assembled bundle rather than the dict, because the
        bundle is what the payload carries and a later branch in
        `_make_theme_bundle_item` could override the authored sentence (the
        golf and per-event branches both do exactly that).
        """
        reason = _only_bundle(names)["reason"].lower()
        for occasion_word in ("next card", "card", "tonight", "main event"):
            assert occasion_word not in reason, reason

    @pytest.mark.parametrize(
        "names", [LIVE_DIVISION_TITLES, LIVE_FIGHTER_TITLES], ids=["division", "fighter"]
    )
    def test_the_question_asks_about_a_title(self, names):
        reason = _only_bundle(names)["reason"].lower()
        assert "title" in reason or "champion" in reason, reason

    def test_the_sentence_states_no_year_it_could_outlive(self):
        """The members' year moves; an authored sentence cannot follow it.

        `_members_span_multiple_seasons` already refuses a family whose members
        straddle two seasons, so the sentence never has to name one — and must
        not, or it goes stale the first January after it is written.
        """
        question = AUTHORED_STORY_QUESTIONS["story:ufc_events"]
        assert "202" not in question, question
        assert "this year" not in question.lower(), question


class TestTheSplitFamilyStillSaysWhatItSaid:
    """The per-event branch overrides the authored dict; prove it still does."""

    def test_a_numbered_card_is_still_headed_by_its_own_name(self):
        bundle = _only_bundle(
            [
                "UFC 331: Renato Moicano vs. Brian Ortega (Lightweight, Main Card)",
                "UFC 331: Alexandre Pantoja vs. Joshua Van (Flyweight, Main Card)",
            ]
        )
        assert bundle["headline"] == "UFC 331"
        assert bundle["reason"] == "What happens at UFC 331?"
