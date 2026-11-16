"""Regression guards for #12093 follow-up defects on /weather & /economics."""

from datetime import datetime, timezone
from types import SimpleNamespace

from app.routes.economics import _distribution_row
from app.routes.weather import (
    _get_yes_outcome,
    _get_yes_probability_raw,
    _get_yes_settled,
    _monthly_city_best,
)


def _outcome(
    name: str,
    prob: float | None,
    *,
    rank: int = 1,
    is_winner: bool | None = None,
    resolution_source: str | None = None,
    bid: float | None = None,
    ask: float | None = None,
):
    return SimpleNamespace(
        id=rank,
        name=name,
        current_probability=prob,
        rank=rank,
        is_winner=is_winner,
        resolution_source=resolution_source,
        current_yes_bid=bid,
        current_yes_ask=ask,
        probability_change_24h=None,
    )


def _market(
    market_id: int,
    name: str,
    outcomes: list,
    *,
    resolution_date: datetime | None = None,
    source: str = "kalshi",
):
    return SimpleNamespace(
        id=market_id,
        name=name,
        outcomes=outcomes,
        resolution_date=resolution_date,
        external_id=f"KX-{market_id}",
        source=source,
        bookmakers=[source],
        mutually_exclusive=False,
    )


def test_monthly_city_best_excludes_single_day_rain_markets_and_deduplicates_cities():
    nov_end = datetime(2026, 12, 1, 4, 59, 59, tzinfo=timezone.utc)
    dec_end = datetime(2027, 1, 1, 4, 59, 59, tzinfo=timezone.utc)
    feb_day = datetime(2027, 2, 15, 8, 0, 0, tzinfo=timezone.utc)

    markets = [
        _market(1, "Rain in Austin in Nov 2026?", [_outcome("Above 1 inch", 1.0)], resolution_date=nov_end),
        _market(2, "Rain in Austin in Dec 2026?", [_outcome("Above 1 inch", 0.42)], resolution_date=dec_end),
        # Single-day game/event rain markets that previously matched ilike("Rain in%in%")
        _market(3, "Rain in Austin on Feb 14, 2027?", [_outcome("Yes", 0.26)], resolution_date=feb_day),
        _market(4, "Rain in Indianapolis on Nov 27, 2026?", [_outcome("Yes", 0.36)], resolution_date=nov_end),
        _market(5, "Rain in Washington, DC on Dec 3, 2026?", [_outcome("Yes", 0.30)], resolution_date=dec_end),
        # Genuine monthly DC market normalizes punctuation cleanly
        _market(6, "Rain in Washington, DC in Nov 2026?", [_outcome("Above 1 inch", 0.55)], resolution_date=nov_end),
    ]

    best = _monthly_city_best(markets)
    assert set(best.keys()) == {"Austin", "Washington DC"}
    assert best["Austin"][1].id == 1
    assert best["Austin"][2] == "Nov 2026"
    assert best["Washington DC"][1].id == 6


def test_monthly_rain_selects_above_1_inch_leg_and_requires_authoritative_settlement():
    settled_austin = _market(
        63653029,
        "Rain in Austin in Nov 2026?",
        [
            _outcome("Above 3 inches", 1.0, rank=1, is_winner=True, resolution_source="api_settlement"),
            _outcome("Above 1 inch", 1.0, rank=2, is_winner=True, resolution_source="api_settlement"),
            _outcome("Above 4 inches", 0.805, rank=3),
        ],
    )
    assert _get_yes_outcome(settled_austin).name == "Above 1 inch"
    assert _get_yes_probability_raw(settled_austin) == 1.0
    assert _get_yes_settled(settled_austin) is True

    # Open ungraded leg at 0.995 must NOT be marked settled (renders >99%, never ✓ Won)
    open_high = _market(
        63653099,
        "Rain in Seattle in Nov 2026?",
        [
            _outcome("Above 0.5 inch", 0.999, rank=1),
            _outcome("Above 1 inch", 0.995, rank=2, is_winner=None, resolution_source=None),
        ],
    )
    assert _get_yes_outcome(open_high).name == "Above 1 inch"
    assert _get_yes_probability_raw(open_high) == 0.995
    assert _get_yes_settled(open_high) is False


def test_mortgage_ladder_marks_settled_rungs_reached_and_drops_unquoted_live_rungs():
    mortgage = _market(
        109321,
        "How high will the 30-year mortgage rate get in 2026?",
        [
            _outcome("Above 6.2%", 0.976, rank=1, is_winner=True, resolution_source="api_settlement"),
            _outcome("Above 6.3%", 0.962, rank=2, is_winner=True, resolution_source="api_settlement"),
            _outcome("Above 6.4%", 0.978, rank=3, is_winner=True, resolution_source="api_settlement"),
            _outcome("Above 6.5%", 1.0, rank=4, is_winner=True, resolution_source="api_settlement"),
            _outcome("Above 7.4%", 0.525, rank=5, bid=0.50, ask=0.55),
            _outcome("Above 7.6%", 0.09, rank=6, bid=0.07, ask=0.11),
            # Unquoted 1c/99c book carrying stale 0.13 last trade must be dropped
            _outcome("Above 7.7%", 0.13, rank=7, bid=0.01, ask=0.99),
            _outcome("Above 7.8%", 0.09, rank=8, bid=0.07, ask=0.11),
        ],
    )
    dist = _distribution_row(mortgage, min_outcomes=3)
    assert dist is not None
    assert dist["kind"] == "ladder"
    assert dist["reached_labels"] == [
        "Above 6.2%",
        "Above 6.3%",
        "Above 6.4%",
        "Above 6.5%",
    ]
    labels = [label for _, label in dist["rows"]]
    assert "Above 7.7%" not in labels
    by_label = {label: prob for prob, label in dist["rows"]}
    assert by_label["Above 6.2%"] == 100.0
    assert by_label["Above 6.3%"] == 100.0
    assert by_label["Above 7.4%"] == 52.5
