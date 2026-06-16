"""Alex interview feed-quality rules R2/R6/R8 (Queue #56, 2026-06-15).

R2 — asset price-LEVEL markets (stocks/crypto/commodities ' above $X') never surface;
     macro policy/event markets (Fed/recession/CPI) stay eligible.
R6 — resolved SPORTS never surface as live cards.
R8 — "#1 yes, #2 no": number-one markets eligible; runner-up/#2 downranked.
"""

from app.utils.feed_market_quality import (
    classify_market_quality,
    _is_asset_price_level,
    _is_runner_up_rank,
    _is_resolved_sports,
)


def q(name, **kw):
    return classify_market_quality(name, **kw)


class TestR2AssetPriceLevel:
    def test_single_stock_price_level_suppressed(self):
        assert _is_asset_price_level("Will META close above $700 in 2026?")
        assert q("Will META close above $700 in 2026?", sport_category="tech").quality_class == "low_quality"

    def test_crypto_and_commodity_price_levels(self):
        assert _is_asset_price_level("Will Bitcoin reach $150,000 by year end?")
        assert _is_asset_price_level("Will oil close above $90 this month?")
        assert _is_asset_price_level("S&P 500 above 6000 by June?")

    def test_macro_event_markets_stay_eligible(self):
        # Fed/recession/CPI are policy/EVENT markets — NOT asset price levels
        assert not _is_asset_price_level("Fed rate decision in June 2026?")
        assert not _is_asset_price_level("Will there be a recession in 2026?")
        assert not _is_asset_price_level("How many Fed rate cuts in 2026?")
        r = q("Fed rate decision in June 2026?", sport_category="economics")
        assert "asset_price_level" not in r.reasons
        assert r.quality_class != "low_quality"

    def test_non_asset_dollar_markets_not_flagged(self):
        # Box office / funding aren't asset price levels (no asset context)
        assert not _is_asset_price_level("Will the movie gross over $100M opening weekend?")
        assert not _is_asset_price_level("Will the startup raise $50M Series B?")


class TestR8RunnerUp:
    def test_number_one_is_eligible(self):
        assert not _is_runner_up_rank("Will Drake have the #1 song on Billboard?")
        assert not _is_runner_up_rank("Will this be the number one movie this weekend?")

    def test_runner_up_downranked(self):
        assert _is_runner_up_rank("Will this song be #2 on the Hot 100?")
        assert _is_runner_up_rank("Will the album finish second this week?")
        assert _is_runner_up_rank("Runner-up at the box office?")
        assert q("Will this song be #2 on the Hot 100?", sport_category="entertainment").quality_class == "low_quality"

    def test_number_one_market_not_low_quality_from_r8(self):
        r = q("Will Drake have the #1 song on Billboard this week?", sport_category="entertainment")
        assert "runner_up_rank" not in r.reasons


class TestR6ResolvedSports:
    def test_resolved_sports_suppressed(self):
        r = q("Lakers vs Celtics", sport_category="basketball", status="resolved")
        assert r.quality_class == "suppress"
        assert "resolved_sports" in r.reasons
        assert _is_resolved_sports("completed", "hockey")
        assert _is_resolved_sports("closed", "soccer")

    def test_open_sports_not_suppressed_by_r6(self):
        assert not _is_resolved_sports("open", "basketball")
        r = q("Lakers vs Celtics", sport_category="basketball", status="open")
        assert "resolved_sports" not in r.reasons

    def test_resolved_non_sports_not_r6(self):
        assert not _is_resolved_sports("resolved", "politics")
        assert not _is_resolved_sports("resolved", "economics")

    def test_default_status_none_is_safe(self):
        # No status passed → R6 never fires (back-compat with old callers)
        assert not _is_resolved_sports(None, "basketball")
