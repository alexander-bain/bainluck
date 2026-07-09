"""#999 L2-72: UFC adapter pure helpers (co_equal_list card grouping)."""

from datetime import datetime, timezone, timedelta

from app.utils.event_ufc import ufc_card_token, ufc_status

NOW = datetime(2026, 6, 20, 20, 0, tzinfo=timezone.utc)


class TestCardToken:
    def test_extracts_date_token_from_fight_ticker(self):
        assert ufc_card_token("kalshi:KXUFCFIGHT-26JUN20KAPHOR") == "26jun20"
        assert ufc_card_token("KXUFCFIGHT-26JUL11MCGHOL") == "26jul11"

    def test_same_card_shares_token(self):
        a = ufc_card_token("kalshi:KXUFCFIGHT-26JUN20COLTAN")
        b = ufc_card_token("kalshi:KXUFCFIGHT-26JUN20SHACHO")
        assert a == b == "26jun20"

    def test_non_fight_tickers_are_none(self):
        # Title futures / props / "who fights next" are NOT card fights.
        for ext in [
            "kalshi:KXUFCHEAVYWEIGHTTITLE-26",
            "kalshi:KXTRUMPUFC-26AUG",
            "kalshi:KXMCGREGORFIGHTNEXT-28",
            None,
            "",
        ]:
            assert ufc_card_token(ext) is None


class TestUfcStatus:
    def test_upcoming_before_card(self):
        assert ufc_status(NOW + timedelta(hours=48), NOW) == "upcoming"

    def test_live_during_fight_night(self):
        assert ufc_status(NOW + timedelta(hours=2), NOW) == "live"

    def test_settled_after_card(self):
        assert ufc_status(NOW - timedelta(hours=10), NOW) == "settled"

    def test_unknown_time_upcoming(self):
        assert ufc_status(None, NOW) == "upcoming"
