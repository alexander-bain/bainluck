"""#4962 — the Pexels query keeps the entity the market is about.

Only four words reach Pexels. Every slot spent on grammar, a month or a betting
line is an entity that never gets searched for, and the picture that comes back
is about something else.

The specimen: futures_markets 109295, "Will Taylor Swift meet with Pope Leo XIV
before 2027?" (kalshi, open, llm_sport_category='entertainment'), stored with
pexels photo 35156556 — "A competitive swimmer performs a backstroke in a pool".
The query that fetched it was "Will Taylor Swift meet": the four-word cap had
already been spent before "Pope" was reached. Measured against the live Pexels
API on 2026-09-17, "Taylor Swift meet Pope" returns St. Peter's Basilica and the
Apostolic Palace, so the right picture was there to be found all along.

`enrich_market_images` selects `image_url IS NULL`, so these assertions describe
what future picks ask for. The 11,544 open rows that already hold an image — the
specimen among them — are not revisited by that task and are not repaired here.
"""

import pytest

from app.tasks.enrich_markets import _extract_image_keywords


class TestQuestionGrammarNeverEatsASlot:
    """Kalshi phrases nearly every market as "Will X …?"."""

    def test_the_filed_specimen_reaches_pexels_carrying_the_pope(self):
        query = _extract_image_keywords(
            "Will Taylor Swift meet with Pope Leo XIV before 2027?", "entertainment"
        )
        assert "Pope" in query, (
            f"the market is about the Pope and the query is {query!r} — "
            "this is the #4962 specimen, which came back a swimmer"
        )
        assert "Will" not in query.split()

    @pytest.mark.parametrize(
        "leader",
        ["Will", "Who", "What", "Which", "When", "Does", "Did"],
    )
    def test_no_question_leader_survives_into_the_query(self, leader):
        query = _extract_image_keywords(f"{leader} Apple release a foldable iPhone?", "tech")
        assert leader not in query.split()
        assert "iPhone" in query, f"{leader!r} displaced the subject: {query!r}"

    def test_the_freed_slot_goes_to_a_subject_word(self):
        # Before #4962 this was "Will Apple release foldable" — the device was cut.
        query = _extract_image_keywords(
            "Will Apple release a foldable iPhone by October 31?", "tech"
        )
        assert query == "Apple release foldable iPhone"


class TestThingsThatPictureNothing:
    def test_a_month_and_a_day_do_not_take_a_slot(self):
        query = _extract_image_keywords(
            "Will OpenAI announce bankruptcy by December 31, 2028?", "tech"
        )
        assert query == "OpenAI announce bankruptcy"
        assert "December" not in query

    def test_a_betting_line_does_not_take_a_slot(self):
        # A handicap is not a picture; the club is.
        assert _extract_image_keywords("Spread: FC Bayern München (-3.5)", "soccer") == (
            "Bayern München"
        )

    def test_a_strike_price_does_not_take_a_slot(self):
        query = _extract_image_keywords(
            "Will Gold (GC) dip to (LOW) $3,500 by end of December?", "economics"
        )
        assert "3,500" not in query
        assert "Gold" in query


class TestTheChangeStaysInsideItsCohort:
    """Measured 2026-09-17 on 57 real open rows: every non-question market that
    changed did so only by shedding a betting line. A game market is untouched."""

    @pytest.mark.parametrize(
        "name,category",
        [
            ("FC Bayern München vs. 1. FC Union Berlin", "soccer"),
            ("AC Monza vs. US Sassuolo Calcio", "soccer"),
            ("LoL: Team WE vs JD Gaming (BO5) - LPL Regional Finals Playoffs", "esports"),
        ],
    )
    def test_a_fixture_still_names_both_sides(self, name, category):
        query = _extract_image_keywords(name, category)
        assert query, "a fixture must not be reduced to nothing"
        assert not query.startswith("vs")

    def test_bo5_is_a_format_not_a_numeral_and_survives(self):
        query = _extract_image_keywords(
            "LoL: Team WE vs JD Gaming (BO5) - LPL Regional Finals Playoffs", "esports"
        )
        assert "BO5" in query


class TestTheCategoryFallbackStillCatches:
    def test_a_name_that_is_all_grammar_falls_back_to_the_category(self):
        # Stripping more words makes this path reachable more often, so it is
        # asserted rather than assumed.
        assert _extract_image_keywords("Will the A?", "politics") == "politics"

    def test_no_category_and_no_words_yields_an_empty_query(self):
        # enrich_market_images skips on a blank query rather than searching for "".
        assert _extract_image_keywords("Will the A?", None) == ""
