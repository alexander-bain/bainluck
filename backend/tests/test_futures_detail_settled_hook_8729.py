"""#8729 — a settled market's detail page stops printing its pre-match sentence.

THE READER'S COMPLAINT. ``/futures/62341453`` (*Chicken Coop Esports vs.
Liquid*, Kalshi), production 2026-09-25 22:38Z and again 2026-09-26 19:41Z:

    "This market has been settled"   Liquid WON
    "Liquid and Chicken Coop Esports are scheduled to compete on
     September 25, 2026."

``status: resolved``, ``hook_withheld: false``. The hook writer selects
``status == 'open'`` only, so a sentence written before the match is never
replaced once it settles, and nothing in ``is_hook_stale`` knows about
settlement — a one-day-old hook with an unchanged leader passes every rule.

WHAT WOULD MAKE THIS FILE VACUOUS: a gate that empties every hook. So each
settled case is paired with the SAME market, same hook, same clock, with only
``status`` flipped back to ``open`` — and that one must publish unchanged.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.utils.hook_staleness import (
    CURRENT_HOOK_POLICY_VERSION,
    HOOK_POLICY_METADATA_KEY,
)

#: The sentence production served, verbatim.
_HOOK = (
    "Liquid and Chicken Coop Esports are scheduled to compete"
    " on September 25, 2026."
)


def _outcome(oid, name, prob, *, is_winner=None):
    return SimpleNamespace(
        id=oid,
        name=name,
        external_id=f"kx-{oid}",
        current_probability=prob,
        current_american_odds=None,
        rank=oid,
        rank_change_24h=None,
        probability_change_24h=None,
        opening_probability=None,
        opening_american_odds=None,
        is_winner=is_winner,
        resolution_source=None,
        last_updated=None,
    )


def _market(status):
    settled = status == "resolved"
    return SimpleNamespace(
        id=62341453,
        name="Chicken Coop Esports vs. Liquid",
        description=None,
        category="sports",
        source="kalshi",
        external_id="KXVALORANTGAME-26SEP25CCELIQ",
        status=status,
        sport=None,
        sport_id=None,
        event_id=None,
        market_type=None,
        market_tier=3,
        llm_sport_category="esports",
        mutually_exclusive=True,
        commence_time=None,
        resolution_date=datetime(2026, 9, 25, 19, 29, 53, tzinfo=timezone.utc),
        created_at=None,
        updated_at=None,
        group_id=None,
        canonical_market_key=None,
        hook_description=_HOOK,
        # Fresh, current policy, leader unchanged: every is_hook_stale rule
        # passes it, so only settlement can refuse it.
        hook_generated_at=datetime.now(timezone.utc) - timedelta(hours=6),
        hook_leader_at_generation="Liquid",
        image_url=None,
        category_tags=[],
        market_metadata={HOOK_POLICY_METADATA_KEY: CURRENT_HOOK_POLICY_VERSION},
        outcomes=[
            _outcome(1, "Liquid", 0.62, is_winner=True if settled else None),
            _outcome(
                2, "Chicken Coop Esports", 0.38, is_winner=False if settled else None
            ),
        ],
    )


class TestSettledMarketHook:
    def test_the_settled_specimen_withholds_its_pre_match_sentence(self):
        from app.routes.futures import _format_market_detail

        detail = _format_market_detail(_market("resolved"), None, set())

        assert detail["status"] == "resolved"
        assert (
            detail["hook_description"] is None
        ), "a settled page must not say the teams 'are scheduled to compete'"
        assert detail["hook_withheld"] is True

    def test_the_same_market_still_open_publishes_the_sentence(self):
        """THE CONTROL. Same hook, same clock, same leader — only status differs."""
        from app.routes.futures import _format_market_detail

        detail = _format_market_detail(_market("open"), None, set())

        assert detail["hook_description"] == _HOOK
        assert detail["hook_withheld"] is False

    @pytest.mark.parametrize("status", ["resolved", "open"])
    def test_no_hook_is_never_reported_as_withheld(self, status):
        # `hook_withheld` has to tell "we refused prose" from "there was none".
        from app.routes.futures import _format_market_detail

        market = _market(status)
        market.hook_description = None
        detail = _format_market_detail(market, None, set())

        assert detail["hook_description"] is None
        assert detail["hook_withheld"] is False
