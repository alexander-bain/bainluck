"""Tests for NCAA Tournament seed matchup helpers."""

from app.utils.seed_matchups import (
    get_first_round_seed_history,
    get_historical_upset_rate,
    get_notable_upsets,
    get_seed_context_text,
)


class TestHistoricalUpsetRate:
    def test_seed_lookup_is_order_insensitive(self):
        forward = get_historical_upset_rate("mens", 5, 12)
        reversed_lookup = get_historical_upset_rate("mens", 12, 5)

        assert forward is not None
        assert forward == reversed_lookup

    def test_unknown_tournament_returns_none(self):
        assert get_historical_upset_rate("international", 1, 16) is None


class TestSeedContextText:
    def test_context_text_names_lower_seed_as_underdog(self):
        context = get_seed_context_text("mens", 5, 12)

        assert "12 seeds" in context
        assert "5 seeds" in context
        assert "upset" in context.lower() or "beat" in context.lower()

    def test_missing_history_returns_empty_string(self):
        assert get_seed_context_text("mens", 1, 1) == ""


class TestFirstRoundSeedHistory:
    def test_first_round_history_is_sorted_by_higher_seed(self):
        rows = get_first_round_seed_history("mens")

        assert rows
        assert [row["higher_seed"] for row in rows] == sorted(
            row["higher_seed"] for row in rows
        )
        assert rows[0]["label"] == "#1 vs #16"
        assert rows[-1]["label"] == "#8 vs #9"

    def test_unknown_tournament_returns_empty_first_round_history(self):
        assert get_first_round_seed_history("unknown") == []


class TestNotableUpsets:
    def test_notable_upsets_are_tournament_scoped(self):
        mens = get_notable_upsets("mens")
        womens = get_notable_upsets("womens")

        assert mens
        assert womens
        assert mens is not womens

    def test_unknown_tournament_returns_empty_notable_upsets(self):
        assert get_notable_upsets("unknown") == []
