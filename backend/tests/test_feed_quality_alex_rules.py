"""Alex interview feed-quality rules (2026-06-15; see
.claude/handoff/alex_interestingness_heuristics_2026-06-15.md).

Implemented as classifier rules with gold assertions here:
R2 — asset price-LEVEL markets (stocks/crypto/commodities ' above $X') never surface;
     macro policy/event markets (Fed/recession/CPI) stay eligible.
R3 — novel sports framings (nationality/region/aggregate angle) are BOOSTED to
     compelling; vanilla stat-line player props are not.
R6 — resolved SPORTS never surface as live cards.
R8 — "#1 yes, #2 no": number-one markets eligible; runner-up/#2 downranked.

Filed (need new signals / product work) — encoded as skipped gold-assertion
stubs at the bottom so the intent + provenance stay visible: R1, R4, R7, R9.
See docs/interestingness-rules.md for the full provenance manifest.
"""

import pytest

from app.utils.feed_market_quality import (
    classify_market_quality,
    _is_asset_price_level,
    _is_novel_sports_framing,
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


class TestR3NovelSportsFraming:
    """R3 — nationality/region/aggregate sports framings are compelling."""

    def test_verbatim_examples_boosted(self):
        # Alex's two verbatim examples must land as compelling.
        assert _is_novel_sports_framing(
            "Will a Canadian team win the NHL Stanley Cup?", "hockey"
        )
        assert (
            q("Will a Canadian team win the NHL Stanley Cup?", sport_category="hockey")
            .quality_class
            == "compelling"
        )
        assert _is_novel_sports_framing(
            "Will a golfer from Europe or from Asia finish higher?", "golf"
        )
        assert (
            q(
                "Will a golfer from Europe or from Asia finish higher?",
                sport_category="golf",
            ).quality_class
            == "compelling"
        )

    def test_region_vs_region_framing(self):
        assert _is_novel_sports_framing(
            "Will a European golfer finish higher than an American?", "golf"
        )

    def test_vanilla_player_prop_not_boosted(self):
        # R3 must NOT fire on standard stat-line props.
        assert not _is_novel_sports_framing("Will LeBron James score 30+ points?", "basketball")

    def test_non_sports_nationality_not_matched(self):
        # Gated on sports category: "a Canadian company" is not a sports framing.
        assert not _is_novel_sports_framing("Will a Canadian company IPO in 2026?", "tech")
        assert not _is_novel_sports_framing("Will a European bank collapse?", "economics")

    def test_plain_team_futures_not_over_matched(self):
        # A normal team-win futures without a nationality/region angle stays out.
        assert not _is_novel_sports_framing("Will the Lakers win the title?", "basketball")


# --------------------------------------------------------------------------- #
# Filed rules — gold-assertion stubs (need new signals / product work). These
# encode the INTENT + provenance so the assertion is ready the moment the signal
# lands. Skipped, not deleted. See docs/interestingness-rules.md.
# --------------------------------------------------------------------------- #
class TestFiledRulesGoldAssertions:
    @pytest.mark.skip(reason="R1 filed: resolved-unless-(surprising×explained) gate needs a "
                             "surprise×explanation-quality signal in the settled/resolution path")
    def test_r1_resolved_market_downranked_unless_surprising_and_explained(self):
        # Gold: a plain resolved market must NOT reach the top-K; a resolved
        # market that is surprising AND has a great 'why' explanation may.
        raise AssertionError("signal not implemented")

    @pytest.mark.skip(reason="R4 filed: 'non-intuitable odds' needs a priors-guessability "
                             "signal (novel entity-pair / specific scenario detection)")
    def test_r4_non_intuitable_odds_boosted(self):
        # Gold: "Will Taylor Swift get married at Madison Square Garden?" — odds
        # a smart fan could not pre-guess — should rank ABOVE a guessable market.
        raise AssertionError("signal not implemented")

    @pytest.mark.skip(reason="R7 filed: theme grouping is a product work item (multi-angle "
                             "cards), bigger than a classifier tweak")
    def test_r7_same_theme_markets_grouped_not_scattered(self):
        # Gold: N markets on one geopolitical theme should surface as ONE
        # multi-angle cluster, not N scattered cards.
        raise AssertionError("grouping not implemented")

    @pytest.mark.skip(reason="R9 filed: numeric markets need a frame-of-reference enrichment "
                             "(comparison/expectation baseline) before they read as interesting")
    def test_r9_bare_numeric_market_needs_frame_of_reference(self):
        # Gold: a bare box-office/critic-score threshold is only interesting with
        # a comparison baseline (vs prior films / budget / other releases).
        raise AssertionError("enrichment not implemented")
