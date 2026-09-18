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

from app.tasks.enrich_markets import (
    _extract_image_keywords,
    _image_query_candidates,
)


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
        ["Will", "Who", "What", "Which", "When", "How", "Does", "Did"],
    )
    def test_no_question_leader_survives_into_the_query(self, leader):
        query = _extract_image_keywords(f"{leader} Apple release a foldable iPhone?", "tech")
        assert leader not in query.split()
        assert "iPhone" in query, f"{leader!r} displaced the subject: {query!r}"

    def test_a_leading_name_that_is_also_a_question_word_costs_only_a_first_name(self):
        # "Will Mackinnon" is a real pickleball player. Stripping "Will" is still
        # right here: the surname is the distinctive half, and the old query
        # ("PPA Men's Doubles Will") ended on the dangling first name anyway.
        query = _extract_image_keywords(
            "PPA - Men's Doubles: Will Mackinnon / Brandon French vs Gabriel Joseph",
            "pickleball",
        )
        assert "Mackinnon" in query
        assert "Will" not in query.split()

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


# ---------------------------------------------------------------------------
# CERT-3047's required repair — the category is an INDEPENDENT RELEVANCE SIGNAL.
# ---------------------------------------------------------------------------


class TestTheOriginalFiledSpecimenIsPinned:
    """#4962's FIRST specimen — "Presidents Cup Winner", category `golf`.

    Trimming the name is not enough and the cert said so: the name reduces to
    exactly "Presidents Cup", which is a real question with a real answer that
    is not ours. Measured against the live Pexels API 2026-09-18: "Presidents
    Cup" returns the White House, the White House, Mount Rushmore, Mount
    Rushmore and one golf course; "Presidents Cup golf" returns five golf
    photographs. The signal that tells them apart was in the row all along.

    Provider result sets drift, so the ASSERTION is on the query we construct —
    deterministic and replayable — never on what came back that night.
    """

    def test_the_golf_signal_reaches_pexels(self):
        first = _image_query_candidates("Presidents Cup Winner", "golf")[0]
        assert "golf" in first.split(), (
            f"the original #4962 specimen still asks Pexels {first!r} — the row "
            "knew it was golf and the query did not"
        )
        assert "Presidents" in first and "Cup" in first

    def test_the_name_query_is_unchanged_and_is_still_the_fallback(self):
        # The repair may not cost a row a picture it would have had.
        candidates = _image_query_candidates("Presidents Cup Winner", "golf")
        assert candidates[-1] == _extract_image_keywords("Presidents Cup Winner", "golf")
        assert candidates[-1] == "Presidents Cup"
        assert len(candidates) == 2


class TestTheCategoryIsCarriedAsWords:
    def test_an_underscored_machine_token_becomes_words(self):
        # `table_tennis` is 2,762 imageless open rows. "table_tennis" is not a
        # word anybody photographs.
        first = _image_query_candidates("Wang Chuqin to win", "table_tennis")[0]
        assert first.endswith("table tennis")
        assert "_" not in first

    @pytest.mark.parametrize("category", ["other", "sports", "sport", "", None, "   "])
    def test_a_category_that_pictures_nothing_is_not_appended(self, category):
        candidates = _image_query_candidates("Manchester United title", category)
        assert candidates == [_extract_image_keywords("Manchester United title", category)]

    def test_a_category_already_in_the_name_is_not_repeated(self):
        candidates = _image_query_candidates("Golf Masters champion", "golf")
        assert len(candidates) == 1, f"asked Pexels for golf twice: {candidates!r}"

    def test_only_the_missing_half_of_a_two_word_category_is_added(self):
        first = _image_query_candidates("Tennis table showdown", "table_tennis")[0]
        assert first.split().count("table") == 1

    def test_the_all_grammar_fallback_does_not_search_its_category_twice(self):
        # `_extract_image_keywords` already answers "politics" here.
        assert _image_query_candidates("Will the A?", "politics") == ["politics"]

    def test_a_blank_query_yields_no_candidates_at_all(self):
        assert _image_query_candidates("Will the A?", None) == []


class TestEveryCandidateListIsUsable:
    """A widening matched by grammar reaches rows nobody reasoned about, so the
    INVARIANTS are asserted over the shapes this repair can produce."""

    @pytest.mark.parametrize(
        "name,category",
        [
            ("Presidents Cup Winner", "golf"),
            ("Will Taylor Swift meet with Pope Leo XIV before 2027?", "entertainment"),
            ("FC Bayern München vs. 1. FC Union Berlin", "soccer"),
            ("Wang Chuqin to win", "table_tennis"),
            ("Will the A?", "politics"),
            ("Spread: FC Bayern München (-3.5)", "soccer"),
        ],
    )
    def test_at_most_two_candidates_none_blank_no_duplicates(self, name, category):
        candidates = _image_query_candidates(name, category)
        assert len(candidates) <= 2
        assert all(c.strip() for c in candidates)
        assert len(set(candidates)) == len(candidates)
        if candidates:
            # The last candidate is always exactly what this task asked for
            # before the qualifier existed — that is what makes it a fallback.
            assert candidates[-1] == _extract_image_keywords(name, category)
