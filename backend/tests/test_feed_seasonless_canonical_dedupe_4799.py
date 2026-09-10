"""#4799 — a Discover card that names no season does not become a second card.

The reader's specimen, production 2026-09-10 06:35 PT, page one slot 2 at 390px
(`_discover-040-BEFORE-worldseries-expanded-390.png`): one card headed
"⚾ BASEBALL · 2 markets" holding

    MLB World Series Winner          Los Angeles Dodgers lead at 29%   29%
    MLB World Series Champion 2026   Los Angeles Dodgers lead at 32%   32%

One question, one leader, two numbers. The two rows differ in `canonical_market_key`
only by the season segment, and one of them is empty (`baseball:MLB:championship:`),
so neither dedupe pass could see them as one question.

Every test below is written against `_canonical_dedupe_keys` and
`_dedupe_futures_by_canonical` directly, because the rule is a pure function of the
items the feed already holds.
"""

from app.routes.feed import (
    _canonical_dedupe_keys,
    _dedupe_futures_by_canonical,
)


def _card(
    market_id: int,
    name: str,
    key: str | None,
    outcomes: list[str],
    score: float,
) -> dict:
    return {
        "type": "futures",
        "score": score,
        "data": {
            "id": market_id,
            "name": name,
            "canonical_market_key": key,
            "resolution_date": None,
            "top_outcomes": [{"name": outcome} for outcome in outcomes],
        },
    }


def _seasonless_world_series() -> dict:
    """id 1 as served: odds_api, no season in the key, no resolution date at all."""
    return _card(
        1,
        "MLB World Series Winner",
        "baseball:MLB:championship:",
        ["Los Angeles Dodgers", "Milwaukee Brewers", "New York Yankees"],
        85,
    )


def _seasoned_world_series() -> dict:
    """id 114584 as served: the same three teams, in the same order, with a season."""
    return _card(
        114584,
        "MLB World Series Champion 2026",
        "baseball:MLB:championship:2026",
        ["Los Angeles Dodgers", "Milwaukee Brewers", "New York Yankees"],
        82,
    )


class TestSeasonlessCanonicalDedupe:
    def test_the_page_one_pair_becomes_one_card(self):
        items = [_seasonless_world_series(), _seasoned_world_series()]

        deduped = _dedupe_futures_by_canonical(items)

        assert [item["data"]["id"] for item in deduped] == [1], (
            "the seasonless card and its only seasoned sibling are one question; the "
            "better-ranked row survives"
        )

    def test_the_seasonless_card_adopts_its_siblings_key(self):
        items = [_seasonless_world_series(), _seasoned_world_series()]

        assert _canonical_dedupe_keys(items) == [
            "baseball:MLB:championship:2026",
            "baseball:MLB:championship:2026",
        ]

    def test_two_seasoned_siblings_are_a_guess_and_are_refused(self):
        """`baseball:MLB:championship` holds open rows for 2024, 2026, 2027 and 2028.

        With two editions on the page there is no way to tell which one a seasonless
        card belongs to, so it stays its own card rather than joining the nearer.
        """
        next_year = _card(
            222222,
            "MLB World Series Champion 2027",
            "baseball:MLB:championship:2027",
            ["Los Angeles Dodgers", "New York Yankees"],
            80,
        )
        items = [_seasonless_world_series(), _seasoned_world_series(), next_year]

        deduped = _dedupe_futures_by_canonical(items)

        assert {item["data"]["id"] for item in deduped} == {1, 114584, 222222}
        assert _canonical_dedupe_keys(items)[0] == "baseball:MLB:championship:"

    def test_a_pair_that_disagrees_on_who_leads_stays_two_cards(self):
        """The arm is stricter than the exact-key pass it extends.

        A deduper that over-pairs deletes a card the reader wanted, and same-leader is
        the duplication the reader actually sees. Two cards that lead with different
        outcomes are left on the page rather than resolved to one by rank.
        """
        other_leader = _card(
            114584,
            "MLB World Series Champion 2026",
            "baseball:MLB:championship:2026",
            ["Milwaukee Brewers", "Los Angeles Dodgers"],
            82,
        )
        items = [_seasonless_world_series(), other_leader]

        assert {item["data"]["id"] for item in _dedupe_futures_by_canonical(items)} == {
            1,
            114584,
        }

    def test_a_card_with_no_outcomes_is_never_adopted(self):
        empty = _card(
            9, "MLB World Series Winner", "baseball:MLB:championship:", [], 90
        )
        items = [empty, _seasoned_world_series()]

        assert {item["data"]["id"] for item in _dedupe_futures_by_canonical(items)} == {
            9,
            114584,
        }

    def test_the_leaders_match_across_two_venues_spelling_of_the_same_name(self):
        """Two venues are two spellings — the comparison is casefolded and trimmed.

        The pair is only ever two rows because two venues listed it; requiring a
        byte-identical leader would refuse the fold on capitalisation alone.
        """
        other_case = _card(
            114584,
            "MLB World Series Champion 2026",
            "baseball:MLB:championship:2026",
            [" los angeles dodgers ", "Milwaukee Brewers"],
            82,
        )
        items = [_seasonless_world_series(), other_case]

        assert [item["data"]["id"] for item in _dedupe_futures_by_canonical(items)] == [
            1
        ]

    def test_two_cards_with_no_outcomes_are_not_the_same_question(self):
        """Two blanks are not a match.

        `_outcomes_overlap` gives an outcome-less pair the benefit of the doubt, so
        without a truthy leader on both sides this arm would fold two cards on the
        strength of neither of them saying anything.
        """
        seasonless = _card(
            61, "MLB World Series Winner", "baseball:MLB:championship:", [], 90
        )
        seasoned = _card(
            62, "MLB Pennant 2026", "baseball:MLB:championship:2026", [], 80
        )

        assert {
            item["data"]["id"]
            for item in _dedupe_futures_by_canonical([seasonless, seasoned])
        } == {61, 62}

    def test_generic_yes_no_binaries_do_not_swallow_each_other(self):
        """A shared "Yes" leader is not a shared question.

        `_outcomes_overlap` routes an all-binary pair through
        `_binary_names_compatible_for_dedupe`, and that gate still binds after adoption:
        two unrelated geopolitics binaries keep their own cards.
        """
        seasonless = _card(
            31,
            "Will the U.S. invade Iran before 2027?",
            "geopolitics:UN:prediction:",
            ["Yes", "No"],
            70,
        )
        seasoned = _card(
            32,
            "Will Norway ratify the seabed treaty in 2026?",
            "geopolitics:UN:prediction:2026",
            ["Yes", "No"],
            65,
        )

        assert {
            item["data"]["id"]
            for item in _dedupe_futures_by_canonical([seasonless, seasoned])
        } == {31, 32}

    def test_seasonless_rows_sharing_one_key_still_fold_together(self):
        """22 open markets share `soccer::championship:` today.

        They fold against each other under the exact-key pass, and this change must not
        split them — the adoption arm only fires when a SEASONED sibling is present.
        """
        first = _card(
            41,
            "Champions League Winner",
            "soccer::championship:",
            ["Real Madrid", "Manchester City"],
            77,
        )
        second = _card(
            42,
            "UEFA Champions League Winner",
            "soccer::championship:",
            ["Real Madrid", "Arsenal"],
            70,
        )

        deduped = _dedupe_futures_by_canonical([first, second])

        assert [item["data"]["id"] for item in deduped] == [41]
        assert _canonical_dedupe_keys([first, second]) == [
            "soccer::championship:",
            "soccer::championship:",
        ]

    def test_two_seasoned_editions_are_never_folded_into_each_other(self):
        this_year = _seasoned_world_series()
        next_year = _card(
            222222,
            "MLB World Series Champion 2027",
            "baseball:MLB:championship:2027",
            ["Los Angeles Dodgers", "Milwaukee Brewers"],
            80,
        )

        assert {
            item["data"]["id"]
            for item in _dedupe_futures_by_canonical([this_year, next_year])
        } == {114584, 222222}

    def test_a_key_that_already_names_a_season_is_returned_verbatim(self):
        items = [_seasoned_world_series()]

        assert _canonical_dedupe_keys(items) == ["baseball:MLB:championship:2026"]

    def test_keys_that_are_not_four_segments_are_untouched(self):
        odd = _card(51, "Something odd", "politics:championship", ["Yes"], 60)
        missing = _card(52, "No key at all", None, ["Yes"], 59)

        assert _canonical_dedupe_keys([odd, missing]) == ["politics:championship", None]

    def test_the_survivor_is_the_better_ranked_row_in_either_order(self):
        """Feed order must not decide which of the two numbers the reader gets."""
        forwards = [_seasonless_world_series(), _seasoned_world_series()]
        backwards = [_seasoned_world_series(), _seasonless_world_series()]

        assert [
            item["data"]["id"] for item in _dedupe_futures_by_canonical(forwards)
        ] == [1]
        assert [
            item["data"]["id"] for item in _dedupe_futures_by_canonical(backwards)
        ] == [1]
