"""The list/search formatter credits the exact headline inputs on both sides."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from app.routes.events import _format_event_with_aggregated_odds
from app.utils.aggregation import stamp_source_reading
from tests.test_blend_fold_chart_pin_parity_3911 import _event_row


def quote(sources, key, value, now, minutes=2):
    at = now - timedelta(minutes=minutes)
    return stamp_source_reading(
        sources, key, value, now=now,
        observed_basis={"42": at.timestamp()} if key in {"kalshi", "polymarket"} else None,
        price_read_at=at,
    )


def card(row, folded=None):
    return _format_event_with_aggregated_odds(row, None, folded_sources=folded)


@pytest.mark.parametrize("status, method", [
    ("scheduled", "Bain Luck blend · the weighted middle of these sources"),
    ("live", "Bain Luck blend · a weighted average of these sources"),
])
def test_folded_list_headline_credits_its_twin_without_mutating_the_row(status, method):
    now = datetime.now(timezone.utc)
    canonical = quote({}, "polymarket", .60, now, 3)
    folded = quote(canonical, "kalshi", .62, now)
    original = deepcopy(canonical)
    row = _event_row(now, sources=canonical)
    row.status = status
    if status == "live":
        row.commence_time = now - timedelta(hours=1)
    data = card(row, folded)
    assert data["hero_probability"] == pytest.approx(.61)
    home, away = data["source_mark"], data["away_source_mark"]
    assert home["state"] == away["state"] == "blend"
    assert [(s["key"], s["probability"]) for s in home["sources"]] == [("kalshi", .62), ("polymarket", .60)]
    assert [s["probability"] for s in away["sources"]] == [.38, .40]
    assert [s["observed_at"] for s in home["sources"]] == [
        (now - timedelta(minutes=n)).isoformat().replace("+00:00", "Z") for n in (2, 3)
    ]
    assert [s["observed_at"] for s in away["sources"]] == [s["observed_at"] for s in home["sources"]]
    assert home["method"] == method
    assert row.win_probability_sources == original


def test_same_price_new_read_replaces_the_age_in_the_list_payload():
    now = datetime.now(timezone.utc)
    row = _event_row(now, sources=quote({}, "kalshi", .62, now, 3))
    before = card(row)
    row.win_probability_sources = quote(row.win_probability_sources, "kalshi", .62, now, 1)
    after = card(row)
    assert before["hero_probability"] == after["hero_probability"] == .62
    for field in ("source_mark", "away_source_mark"):
        assert before[field]["sources"][0]["observed_at"] == (now - timedelta(minutes=3)).isoformat().replace("+00:00", "Z")
        assert after[field]["sources"][0]["observed_at"] == (now - timedelta(minutes=1)).isoformat().replace("+00:00", "Z")


@pytest.mark.parametrize("damage", ["poll_only", "changed_value"])
def test_unbound_times_stay_unknown_in_search_cards(damage):
    now = datetime.now(timezone.utc)
    sources = quote({}, "kalshi", .62, now)
    if damage == "poll_only":
        sources["kalshi"].pop("price_read")
    else:
        sources["kalshi"]["value"] = .63
    data = card(_event_row(now, sources=sources))
    source = data["source_mark"]["sources"][0]
    assert source["probability"] == (.62 if damage == "poll_only" else .63)
    assert source["observed_at"] is None
    assert source["reason"] == "observation_unknown"


def test_divergence_lists_only_the_source_that_fed_the_headline():
    now = datetime.now(timezone.utc)
    sources = quote(quote({}, "betting", .90, now), "kalshi", .10, now)
    sources["betting_book_count"] = 5
    data = card(_event_row(now, sources=sources))
    assert data["hero_probability"] == .90
    assert data["source_mark"]["state"] == "single"
    assert [(s["key"], s["probability"], s["count"]) for s in data["source_mark"]["sources"]] == [("betting", .90, 5)]


def test_draw_priced_away_is_unavailable_but_a_verified_final_keeps_both_results():
    now = datetime.now(timezone.utc)
    row = _event_row(now, sources=quote({}, "kalshi", .62, now))
    row.sport.key = "soccer_epl"
    live = card(row)
    assert live["hero_probability_away"] is None
    assert live["away_source_mark"] == {"state": "none", "sources": [], "reason": "away_unavailable"}
    row.status = "completed"
    row.commence_time = now - timedelta(hours=2)
    row.completed_at = now - timedelta(minutes=3)
    row.home_score, row.away_score = 1, 2
    row.score_source = "espn"
    final = card(row)
    assert final["source_mark"]["state"] == final["away_source_mark"]["state"] == "settled"
    assert final["source_mark"]["settled"]["result"] == "Lost"
    assert final["away_source_mark"]["settled"]["result"] == "Won"
    assert final["source_mark"]["sources"] == final["away_source_mark"]["sources"] == []


def test_a_card_with_no_current_or_historical_price_has_an_explicit_mark():
    row = _event_row(datetime.now(timezone.utc), sources={})
    row.opening_home_probability = row.opening_away_probability = None
    data = card(row)
    assert data["source_mark"] == data["away_source_mark"] == {
        "state": "none", "sources": [], "reason": "no_probability",
    }
