"""#999 L2-72 / L2-84: UFC adapter pure helpers (co_equal_list card grouping,
card naming, prop classification, concept derivation)."""

from datetime import datetime, timezone, timedelta

from app.utils.event_ufc import (
    ufc_card_token,
    ufc_any_card_token,
    ufc_card_number,
    ufc_card_label,
    is_ufc_fight_market,
    classify_ufc_prop,
    derive_ufc_concept,
    ufc_status,
)

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


class TestAnyCardToken:
    def test_prop_ticker_shares_card_date_token(self):
        # A prop (KXUFCMOV) shares the card date-token with its fight (KXUFCFIGHT).
        assert ufc_any_card_token("kalshi:KXUFCMOV-26MAR07HOLOLI") == "26mar07"
        assert ufc_any_card_token("kalshi:KXUFCROUNDS-26MAR07HOLOLI") == "26mar07"
        assert ufc_any_card_token("KXUFCFIGHT-26JUL11MCGHOL") == "26jul11"

    def test_non_ufc_ticker_none(self):
        assert ufc_any_card_token("kalshi:KXNBA-26JAN01") is None
        assert ufc_any_card_token(None) is None


class TestCardNumberAndLabel:
    def test_extracts_numbered_card(self):
        assert ufc_card_number("UFC 329: McGregor vs. Holloway 2") == "UFC 329"
        assert ufc_card_number(None, "UFC329: X vs Y") == "UFC 329"
        assert ufc_card_number("Fight Night: A vs B") is None

    def test_numbered_card_label_is_major(self):
        label, is_major = ufc_card_label("UFC 329: McGregor vs. Holloway 2")
        assert label == "UFC 329: McGregor vs. Holloway 2"
        assert is_major is True

    def test_numbered_card_label_from_event_title_when_name_bare(self):
        # A fight named just "McGregor vs Holloway 2" but whose Kalshi event_title
        # carries the number still reads as the numbered card.
        label, is_major = ufc_card_label(
            "McGregor vs. Holloway 2", ("UFC 329: McGregor vs. Holloway 2",)
        )
        assert label == "UFC 329: McGregor vs. Holloway 2"
        assert is_major is True

    def test_fight_night_fallback(self):
        label, is_major = ufc_card_label("Fight Night: Yakhyaev vs Walker")
        assert label == "Fight Night: Yakhyaev vs Walker"
        assert is_major is False

    def test_bare_headline_last_resort(self):
        label, is_major = ufc_card_label("Jones vs Gane")
        assert label == "Jones vs Gane"
        assert is_major is False


class TestIsFightMarket:
    def test_two_sided_fight(self):
        assert is_ufc_fight_market("kalshi:KXUFCFIGHT-26JUL11MCGHOL", 2) is True

    def test_non_two_sided_rejected(self):
        assert is_ufc_fight_market("kalshi:KXUFCFIGHT-26JUL11MCGHOL", 1) is False

    def test_prop_ticker_not_a_fight(self):
        assert is_ufc_fight_market("kalshi:KXUFCMOV-26MAR07HOLOLI", 2) is False


class TestClassifyProp:
    def test_kalshi_prop_tickers(self):
        assert classify_ufc_prop("kalshi:KXUFCMOV-26MAR07HOLOLI", "Method of Victory") == "method"
        assert classify_ufc_prop("kalshi:KXUFCMOF-26MAR07HOLOLI", "Method of Finish") == "method"
        assert classify_ufc_prop("kalshi:KXUFCROUNDS-26MAR07HOLOLI", "Round of Finish") == "rounds"
        assert classify_ufc_prop("kalshi:KXUFCVICROUND-26MAR07HOLOLI", "Round of Victory") == "rounds"
        assert classify_ufc_prop("kalshi:KXUFCDISTANCE-26MAR07HOLOLI", "Go the Distance") == "distance"
        assert classify_ufc_prop("kalshi:KXUFCOCCUR-26CMCGMHOL", "Will A and B fight at UFC 329?") == "occurrence"

    def test_polymarket_method_by_name(self):
        # Poly props have hash tickers (no date token) — classify by name.
        assert classify_ufc_prop("0xabc", "Will Max Holloway win by KO or TKO?") == "method"
        assert classify_ufc_prop("0xdef", "Will Conor McGregor win by KO or TKO?") == "method"

    def test_novelty_attend_is_occurrence(self):
        assert classify_ufc_prop("kalshi:KXTRUMPUFC-26JUL", "Will Donald Trump attend UFC 329?") == "occurrence"

    def test_plain_fight_is_not_a_prop(self):
        assert classify_ufc_prop("kalshi:KXUFCFIGHT-26JUL11MCGHOL", "UFC 329: McGregor vs. Holloway 2") is None


class TestDeriveConcept:
    def test_fight_market_yields_card_concept(self):
        c = derive_ufc_concept(
            "kalshi:KXUFCFIGHT-26JUL11MCGHOL", "UFC 329: McGregor vs. Holloway 2", 2
        )
        assert c is not None
        assert c["key"] == "event:ufc:26jul11"
        assert c["name"] == "UFC 329: McGregor vs. Holloway 2"
        assert c["is_major"] is True
        assert c["domain"] == "ufc"

    def test_non_fight_returns_none(self):
        assert derive_ufc_concept("kalshi:KXUFCMOV-26MAR07HOLOLI", "Method of Victory", 4) is None
        assert derive_ufc_concept("kalshi:KXUFCFIGHT-26JUL11MCGHOL", "X vs Y", 1) is None
