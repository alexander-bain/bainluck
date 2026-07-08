"""#999 L2-62: entrant-set event matcher (the group_type=event discriminator)."""

from app.utils.event_matcher import (
    player_key,
    entrant_key_set,
    extract_match_players,
    market_in_event,
)


class TestPlayerKey:
    def test_surname_diacritic_free(self):
        assert player_key("Iga Świątek") == "swiatek"
        assert player_key("Coco Gauff") == "gauff"
        assert player_key("Sabalenka") == "sabalenka"  # surname-only form

    def test_empty_safe(self):
        assert player_key("") == ""
        assert player_key(None) == ""


class TestExtractMatchPlayers:
    def test_vs_forms(self):
        assert extract_match_players("Sabalenka vs Osaka") == ("sabalenka", "osaka")
        assert extract_match_players("Eala v Swiatek") == ("eala", "swiatek")
        assert extract_match_players("Djokovic def. Nadal") == ("djokovic", "nadal")

    def test_strips_round_suffix(self):
        assert extract_match_players("Halys vs O'Connell: Set 1 Winner") == ("halys", "oconnell")

    def test_non_match_is_none(self):
        assert extract_match_players("2026 Wimbledon Winner") is None
        assert extract_match_players("") is None


class TestMarketInEvent:
    # The women's Wimbledon draw (entrant keys), diacritics handled.
    FIELD = entrant_key_set([
        "Aryna Sabalenka", "Naomi Osaka", "Iga Świątek", "Alexandra Eala",
        "Coco Gauff",
    ])

    def test_both_in_draw_associates(self):
        assert market_in_event("Sabalenka vs Osaka", self.FIELD) is True
        assert market_in_event("Eala vs Swiatek", self.FIELD) is True  # diacritic match

    def test_concurrent_challenger_excluded(self):
        # NEGATIVE CASE (queue-required): a Challenger match in the same window
        # whose players are NOT in the slam draw must not associate.
        assert market_in_event("Bertran vs Soto", self.FIELD) is False
        assert market_in_event("Kosaka vs Ounmuang", self.FIELD) is False

    def test_one_player_in_draw_excluded(self):
        # a mixed/exhibition where only one side is in the draw
        assert market_in_event("Gauff vs Ounmuang", self.FIELD) is False

    def test_empty_field_and_non_match(self):
        assert market_in_event("Sabalenka vs Osaka", set()) is False
        assert market_in_event("2026 Wimbledon Winner", self.FIELD) is False
