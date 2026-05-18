"""Regression tests for Discover-mode event demotion."""

from app.routes.feed import _demote_non_exceptional_discover_events


def _event_item(
    *,
    score: int,
    headline: str,
    sport: str,
    event_tags: list[str] | None = None,
    ei_score: int | None = None,
) -> dict:
    data = {
        "sport": sport,
        "event_tags": event_tags or [],
    }
    if ei_score is not None:
        data["ei"] = {"score": ei_score}
    return {
        "type": "event",
        "score": score,
        "headline": headline,
        "data": data,
    }


def test_low_tier_soccer_upset_is_demoted_in_discover_mode():
    item = _event_item(
        score=95,
        headline="Historic upset",
        sport="soccer_brazil_campeonato",
        event_tags=["tier:4"],
    )

    _demote_non_exceptional_discover_events([item])

    assert item["score"] == 35


def test_major_league_nba_upset_keeps_discover_exception():
    item = _event_item(
        score=80,
        headline="Historic upset",
        sport="basketball_nba",
        event_tags=["tier:1"],
    )

    _demote_non_exceptional_discover_events([item])

    assert item["score"] == 80


def test_raw_high_score_without_event_interest_is_demoted():
    item = _event_item(
        score=95,
        headline="Close game",
        sport="soccer_argentina_primera_division",
        event_tags=["tier:4"],
    )

    _demote_non_exceptional_discover_events([item])

    assert item["score"] == 35
