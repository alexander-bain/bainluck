"""Regression tests for Discover negative-feedback propagation."""

from types import SimpleNamespace

from app.routes.feed import _should_skip_futures_for_recent_dismissal
from app.utils.feed_market_quality import classify_market_quality
from app.utils.personalization import PersonalizationContext


def test_recently_dismissed_group_id_suppresses_related_futures():
    ctx = PersonalizationContext(recent_dismissed_group_ids={"polymarket:123"})
    market = SimpleNamespace(group_id="polymarket:123")

    assert _should_skip_futures_for_recent_dismissal(
        market=market,
        ctx=ctx,
        my_teams_only=False,
    ) is True


def test_recently_dismissed_story_key_suppresses_related_futures():
    ctx = PersonalizationContext(recent_dismissed_story_keys={"story:russia_ukraine"})
    market = SimpleNamespace(group_id=None)
    quality = classify_market_quality(
        "Will Russia capture Kharkiv before July?",
        sport_category="geopolitics",
    )

    assert _should_skip_futures_for_recent_dismissal(
        market=market,
        quality=quality,
        ctx=ctx,
        my_teams_only=False,
    ) is True


def test_my_teams_only_does_not_apply_dismissed_story_filter():
    ctx = PersonalizationContext(
        recent_dismissed_story_keys={"story:russia_ukraine"},
        recent_dismissed_group_ids={"polymarket:123"},
    )
    market = SimpleNamespace(group_id="polymarket:123")
    quality = classify_market_quality(
        "Will Russia capture Kharkiv before July?",
        sport_category="geopolitics",
    )

    assert _should_skip_futures_for_recent_dismissal(
        market=market,
        quality=quality,
        ctx=ctx,
        my_teams_only=True,
    ) is False
