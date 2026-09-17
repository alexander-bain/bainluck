"""#2602/#6444 — a UFC card is a story; the promotion is not.

Alex's September 16 physical-phone test read seven consecutive UFC cards with
"no images or event context", tapping through to "a generic UFC league page with
eight fights; only the first identifies UFC 331".

The backend half of that was a regex that matched the event number and then threw
it away::

    if re.search(r"\\bufc\\s+\\d{3,}\\b", lower) or ...:
        return "story:ufc_events"      # <- 331 matched here, and discarded

So UFC 331 (September 19) and UFC 332 (October) shared one bucket headed "UFC",
asking "Who wins on the next card?" — a question with no answer about a set that
spans two different nights.

What was actually being served when this was written (`GET /api/feed?limit=200`,
2026-09-17T00:0xZ) is the specimen the LIVE test below pins: a single bundle,
``story_key: story:ufc_events``, ``title: "UFC"``, ``shared_question: "Who wins on
the next card?"``, ``member_ids: [13793105, 58728394]`` — which are "Will Aljamain
Sterling become UFC champion in 2026?" and "Will Donald Trump attend UFC 332?".
Neither member is a fight, so the question was false of both.

These tests are about the KEY carrying the event identity, and about the copy
being true of the family it heads.
"""

import pytest

from app.utils.discover_bundles import assemble_story_theme_bundles
from app.utils.feed_market_quality import (
    UFC_EVENT_STORY_PREFIX,
    _story_key,
    diversify_quality_families,
    ufc_event_display_name,
)


def _key(name: str) -> str | None:
    return _story_key(name, "mma")


def _item(market_id: int, name: str, score: float = 70.0) -> dict:
    return {
        "type": "futures",
        "score": score,
        "_sort_time": 0,
        "data": {
            "id": market_id,
            "name": name,
            "llm_sport_category": "mma",
            "source": "polymarket",
        },
    }


# Real production rows (futures_markets, 2026-09-17). Kept verbatim: the venue
# writes the event number into the name, and that string IS the input under test.
UFC_331_FIGHTS = [
    "UFC 331: Renato Moicano vs. Brian Ortega (Lightweight, Main Card)",
    "UFC 331: Alexandre Pantoja vs. Joshua Van (Flyweight, Main Card)",
    "UFC 331: Tai Tuivasa vs. Robelis Despaigne (Heavyweight, Prelims)",
    "UFC 331: Giga Chikadze vs. Joanderson Brito (Featherweight, Early Prelims)",
]


class TestEventIdentitySurvivesIntoTheKey:
    def test_two_different_cards_are_two_different_stories(self):
        """The defect, stated directly: 331 and 332 must not share a bucket."""
        assert _key(UFC_331_FIGHTS[0]) != _key("UFC 332: A Fighter vs. B Fighter")

    def test_every_fight_on_one_card_shares_that_card_s_key(self):
        keys = {_key(name) for name in UFC_331_FIGHTS}
        assert keys == {f"{UFC_EVENT_STORY_PREFIX}331"}

    def test_the_key_round_trips_to_a_name_a_reader_recognises(self):
        assert ufc_event_display_name(_key(UFC_331_FIGHTS[0])) == "UFC 331"

    def test_an_off_card_market_joins_its_own_event(self):
        """Notice 40: an off-card novelty belongs to the event container.

        "Will Donald Trump attend UFC 332?" is a UFC 332 market. It is not a UFC
        331 market, and it is not a fight.
        """
        assert (
            _key("Will Donald Trump attend UFC 332?") == f"{UFC_EVENT_STORY_PREFIX}332"
        )
        assert _key("Will Donald Trump attend UFC 332?") != _key(UFC_331_FIGHTS[0])


class TestTheBoundOnWhatCountsAsACard:
    def test_a_season_long_question_names_no_card_and_joins_no_event_family(self):
        """A championship run is not a night. It keeps the generic key.

        This is the guard against "fix the bucket by widening the bucket": if
        every UFC market were swept into an event family, the family would again
        be answering a question its members do not share.
        """
        key = _key("Will Aljamain Sterling become UFC champion in 2026?")
        assert key == "story:ufc_events"
        assert not key.startswith(UFC_EVENT_STORY_PREFIX)

    @pytest.mark.parametrize(
        "name",
        [
            "Will Francis Ngannou return to the UFC by December 31, 2026?",
            "UFC: Who Will Jean Silva Fight Next?",
            "UFC Fight Night: Ricky Simon vs. Montel Jackson (Bantamweight, Prelims)",
        ],
    )
    def test_an_unnumbered_name_mints_no_event_key(self, name):
        key = _key(name)
        assert key is None or not key.startswith(UFC_EVENT_STORY_PREFIX), key

    def test_a_year_is_not_a_card_number(self):
        """`\\d{3,}` unbounded would read a stray year as an event number."""
        key = _key("Will the UFC 2026 season sell out?")
        assert key is None or not key.startswith(UFC_EVENT_STORY_PREFIX), key


class TestTheBundleSaysSomethingTrueAboutItsMembers:
    def test_a_card_folds_under_its_own_name_not_the_promotion_s(self):
        bundles = [
            item
            for item in assemble_story_theme_bundles(
                [_item(60285728 + i, n) for i, n in enumerate(UFC_331_FIGHTS)]
            )
            if item["type"] == "bundle"
        ]
        assert len(bundles) == 1
        bundle = bundles[0]
        assert bundle["headline"] == "UFC 331"
        assert bundle["data"]["title"] == "UFC 331"
        # The promotion-wide question is what the reader was getting before.
        assert bundle["reason"] != "Who wins on the next card?"
        assert "UFC 331" in bundle["reason"]

    def test_two_cards_in_one_slate_do_not_merge(self):
        items = [_item(1 + i, n) for i, n in enumerate(UFC_331_FIGHTS[:2])] + [
            _item(101, "UFC 332: A Fighter vs. B Fighter"),
            _item(102, "UFC 332: C Fighter vs. D Fighter"),
        ]
        titles = {
            item["headline"]
            for item in assemble_story_theme_bundles(items)
            if item["type"] == "bundle"
        }
        assert titles == {"UFC 331", "UFC 332"}

    def test_the_live_specimen_no_longer_folds_on_a_false_question(self):
        """The exact pair production was serving as one "UFC" bundle.

        A season-long championship question and a novelty about who attends a
        different card share no question. They are two separate cards now, which
        is where they were before anything folded them.
        """
        live = [
            _item(13793105, "Will Aljamain Sterling become UFC champion in 2026?", 71),
            _item(58728394, "Will Donald Trump attend UFC 332?", 70),
        ]
        out = assemble_story_theme_bundles(live)
        assert [item["type"] for item in out] == ["futures", "futures"]
        assert not any(item["type"] == "bundle" for item in out)


class TestSplittingTheKeyDidNotRaiseTheCap:
    def test_one_card_is_still_capped_at_three(self):
        """`story:ufc_events` carried a hand-written cap of 3.

        A derived key can never appear in that literal dict, so without the
        prefix entry the whole family would fall through to the default 5 — the
        split would have quietly loosened a dial while claiming to fix grouping.
        """
        items = [
            {"_quality_story_key": f"{UFC_EVENT_STORY_PREFIX}331", "score": 90 - i}
            for i in range(6)
        ]
        assert len(diversify_quality_families(items)) == 3

    def test_the_cap_is_per_card_not_per_promotion(self):
        """Two cards are two families: capping is not a reason to re-merge them."""
        items = [
            {"_quality_story_key": f"{UFC_EVENT_STORY_PREFIX}331", "score": 90 - i}
            for i in range(4)
        ] + [
            {"_quality_story_key": f"{UFC_EVENT_STORY_PREFIX}332", "score": 80 - i}
            for i in range(4)
        ]
        kept = diversify_quality_families(items)
        assert len(kept) == 6
        counts = {}
        for item in kept:
            counts[item["_quality_story_key"]] = (
                counts.get(item["_quality_story_key"], 0) + 1
            )
        assert counts == {
            f"{UFC_EVENT_STORY_PREFIX}331": 3,
            f"{UFC_EVENT_STORY_PREFIX}332": 3,
        }
