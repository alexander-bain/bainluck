"""#1579 — the daily price-direction filler suppressor must not be an asset roster.

`_DAILY_EQUITY_DIRECTION_RE` names its assets, so it only ever covered the slice of
Polymarket's daily-direction product somebody remembered to add. Measured on the
2026-08-07 production slate it had drifted behind every commodity, every non-US
index and a row of equities — and four commodity cards reached the live feed at
once, all printing exactly 50.0%.

Every name below is a verbatim production row from that slate.
"""

import pytest

from app.utils.feed_market_quality import (
    _DAILY_EQUITY_DIRECTION_RE,
    _story_key,
    classify_market_quality,
    is_daily_direction_filler,
)

# The four that reached the live feed together, all at exactly 50.0% on tight,
# genuinely-real books (Gold 0.49/0.51, the rest 0.46/0.54). Not phantoms —
# UX-P011 correctly leaves them alone. They are filler, not fabrication.
FEED_OFFENDERS = [
    "Gold (XAUUSD) Up or Down on August 10?",
    "Silver (XAGUSD) Up or Down on August 10?",
    "WTI Crude Oil (WTI) Up or Down on August 10?",
    "Natural Gas (NG) Up or Down on August 10?",
]

# Open members of the same family the roster also missed.
ROSTER_MISSED = [
    "DAX (DAX) Up or Down on August 10?",
    "FTSE 100 (UKX) Up or Down on August 10?",
    "Hang Seng (HSI) Up or Down on August 10?",
    "Nikkei 225 (NIK) Up or Down on August 10?",
    "NYA (NYA) Up or Down on August 10?",
    "Coinbase (COIN) Up or Down on August 10?",
    "Micron (MU) Up or Down on August 10?",
    "Palantir (PLTR) Up or Down on August 10?",
    "Airbnb (ABNB) Up or Down on August 10?",
    "Opendoor (OPEN) Up or Down on August 10?",
]

# Names the legacy roster already caught. They must keep matching.
ROSTER_ALREADY_CAUGHT = [
    "NVIDIA (NVDA) Up or Down on August 10?",
    "S&P 500 (SPX) Opens Up or Down on August 10?",
    "S&P 500 (SPY) closes above $745 on August 10?",
    "Amazon (AMZN) closes above ___ on August 10?",
]

# The reason the rule requires a parenthesised ticker rather than just
# "up or down + a date". All three are unrelated families on the SAME slate.
MUST_NOT_SUPPRESS = [
    ("Berlin State Election: Turnout Up or Down?", "politics"),
    ("Mecklenburg-Vorpommern Parliamentary Election: Turnout Up or Down?", "politics"),
    ("Canada's population Up or Down this year?", "politics"),
    ("Charizard ex Up or Down: July", "entertainment"),
    ("151 Ultra-Premium Collection Up or Down: July", "entertainment"),
    ("Perfect Order Booster Box Up or Down: July", "entertainment"),
]

# Tickered markets that are NOT direction bets — no direction phrase, so the
# shape rule must ignore them. The first is a real economics ladder.
MUST_NOT_SUPPRESS_TICKERED = [
    "What will Gold (XAUUSD) hit in August 2026?",
    "What will SpaceX (SPCX) hit in August 2026?",
    "Fed decision in September 2026?",
    "CPI year-over-year in Oct 2026?",
]


class TestShapeRuleCatchesTheDrift:
    @pytest.mark.parametrize("name", FEED_OFFENDERS + ROSTER_MISSED)
    def test_family_member_is_filler(self, name):
        assert is_daily_direction_filler(name) is True

    @pytest.mark.parametrize("name", FEED_OFFENDERS + ROSTER_MISSED)
    def test_and_the_roster_alone_would_have_missed_it(self, name):
        """Pins the actual defect: without the shape rule these walk through.

        If this ever fails because the roster grew to include the asset, the
        shape rule is still the thing preventing the NEXT drift.
        """
        assert _DAILY_EQUITY_DIRECTION_RE.search(name) is None

    @pytest.mark.parametrize("name", FEED_OFFENDERS + ROSTER_MISSED)
    def test_family_member_is_capped_by_a_story_key(self, name):
        """Every member lands under SOME story key, so the family cannot flood.

        Usually `story:daily_equity_direction`. WTI Crude Oil is the deliberate
        exception: `story:oil` matches earlier in the chain and is the more
        specific grouping, so it caps there instead. Either way the card is
        capped and the quality gate below still fires — asserting the exact key
        would be asserting chain order, not behaviour.
        """
        key = _story_key(name, "economics")
        assert key is not None
        if "WTI" not in name and "Crude" not in name:
            assert key == "story:daily_equity_direction"

    def test_a_new_asset_needs_no_code_edit(self):
        """The point of the rule: coverage without maintenance."""
        assert is_daily_direction_filler(
            "Some Brand New Thing (BRND) Up or Down on December 3?"
        ) is True


class TestNoRegressionOnTheLegacyRoster:
    @pytest.mark.parametrize("name", ROSTER_ALREADY_CAUGHT)
    def test_still_filler(self, name):
        assert is_daily_direction_filler(name) is True

    @pytest.mark.parametrize("name", ROSTER_ALREADY_CAUGHT)
    def test_still_matched_by_the_roster_itself(self, name):
        assert _DAILY_EQUITY_DIRECTION_RE.search(name) is not None


class TestBothDirectionGuard:
    """gotcha #43 — suppression is the sharp edge.

    The parenthesised-ticker requirement is what keeps these unrelated families
    alive. A width-first "up or down + date" rule would have taken all of them.
    """

    @pytest.mark.parametrize("name,category", MUST_NOT_SUPPRESS)
    def test_neighbouring_family_untouched(self, name, category):
        assert is_daily_direction_filler(name) is False

    @pytest.mark.parametrize("name,category", MUST_NOT_SUPPRESS)
    def test_neighbouring_family_keeps_its_own_story_key(self, name, category):
        assert _story_key(name, category) != "story:daily_equity_direction"

    @pytest.mark.parametrize("name", MUST_NOT_SUPPRESS_TICKERED)
    def test_tickered_but_not_a_direction_bet(self, name):
        assert is_daily_direction_filler(name) is False


class TestClassifierWiring:
    """The predicate must actually reach the quality verdict, not just exist."""

    @pytest.mark.parametrize("name", FEED_OFFENDERS)
    def test_offender_is_not_high_quality(self, name):
        result = classify_market_quality(name, "economics")
        assert result.quality_class in ("low_quality", "suppress"), (
            f"{name!r} classified {result.quality_class!r} — "
            "the daily-direction gate did not fire"
        )

    @pytest.mark.parametrize("name", FEED_OFFENDERS)
    def test_offender_carries_the_reason_and_story_key(self, name):
        result = classify_market_quality(name, "economics")
        assert "daily_equity_direction" in result.reasons
        # Capped under some story key; see the note on WTI above.
        assert result.story_key is not None

    def test_a_real_economics_market_is_unaffected(self):
        result = classify_market_quality("Fed decision in September 2026?", "economics")
        assert result.quality_class not in ("low_quality", "suppress")
