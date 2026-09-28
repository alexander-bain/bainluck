"""#9468 — a Spotify market whose legs are nested dates is served as a LADDER, not a race.

Production 2026-09-28, `/api/entertainment` → `themes.music.spotify_race[0]` was
Kalshi's "When will Spotify release 2026 Wrapped?" (market 109527), legs in price
order: Before Dec 4 82.5 · Before Dec 5 82.5 · Before Dec 3 78.0 · Before Dec 2
20.0 … and `SpotifyRace` numbered them 1-8 as a chart race. "Before Dec 5"
contains "Before Dec 4"; nothing is ranked.

`_build_music` now marks such a row `ladder: True` and serves its legs in rung
(calendar) order, via the discriminator the feed and outcome display already
share (`cumulative_outcome_ladder`, dates on). A race of named contenders is
`ladder: False` and keeps its price order.
"""

import itertools
from datetime import datetime, timezone
from types import SimpleNamespace

from app.routes.entertainment import _build_music

_IDS = itertools.count(1)


def _outcome(name: str, prob: float):
    return SimpleNamespace(
        id=next(_IDS), name=name, current_probability=prob,
        probability_change_24h=0.0,
    )


def _spotify_market(market_id: int, name: str, legs):
    return SimpleNamespace(
        id=market_id,
        name=name,
        external_id=f"kxspotify-{market_id}",
        source="kalshi",
        outcomes=[_outcome(n, p) for n, p in legs],
        volume_24h=1000,
        resolution_date=None,
        updated_at=datetime(2026, 9, 28, tzinfo=timezone.utc),
        image_url=None,
        hook_description=None,
    )


#: The production specimen's nine legs, raw 0-1 (the ninth is off the 8-slot rack).
WRAPPED = [
    ("Before Dec 4, 2026", 0.825),
    ("Before Dec 5, 2026", 0.825),
    ("Before Dec 3, 2026", 0.78),
    ("Before Dec 2, 2026", 0.20),
    ("Before Dec 1, 2026", 0.12),
    ("Before Nov 30, 2026", 0.10),
    ("Before Nov 29, 2026", 0.08),
    ("Before Nov 28, 2026", 0.07),
    ("Before Nov 27, 2026", 0.05),
]

CALENDAR = [
    "Before Nov 28, 2026",
    "Before Nov 29, 2026",
    "Before Nov 30, 2026",
    "Before Dec 1, 2026",
    "Before Dec 2, 2026",
    "Before Dec 3, 2026",
    "Before Dec 4, 2026",
    "Before Dec 5, 2026",
]


def _music(*markets):
    return _build_music({"music": list(markets)})


def _row(result, market_id):
    return next(r for r in result["spotify_race"] if r["market_id"] == market_id)


def test_the_wrapped_ladder_is_marked_and_served_in_calendar_order():
    result = _music(
        _spotify_market(109527, "When will Spotify release 2026 Wrapped?", WRAPPED)
    )
    row = _row(result, 109527)
    assert row["ladder"] is True
    assert [o["name"] for o in row["top_outcomes"]] == CALENDAR


def test_reordering_changes_neither_the_headline_nor_the_slice():
    """Only ORDER moves: same eight legs, same prices, same `prob` leader."""
    row = _row(
        _music(_spotify_market(109527, "When will Spotify release 2026 Wrapped?", WRAPPED)),
        109527,
    )
    assert row["prob"] == 82.5
    assert row["outcome_count"] == 9
    assert {o["name"]: o["prob"] for o in row["top_outcomes"]} == {
        n: round(p * 100, 1) for n, p in WRAPPED[:8]
    }


def test_a_race_of_named_contenders_is_not_a_ladder_and_keeps_price_order():
    race = [("Bad Bunny", 0.41), ("Taylor Swift", 0.33), ("The Weeknd", 0.12)]
    row = _row(_music(_spotify_market(7, "Top artist on Spotify this week?", race)), 7)
    assert row["ladder"] is False
    assert [o["name"] for o in row["top_outcomes"]] == [
        "Bad Bunny", "Taylor Swift", "The Weeknd",
    ]


def test_one_contender_among_dates_disqualifies_the_whole_row():
    """Every leg must be a rung; a stray prose leg keeps the row a (price-ordered) list."""
    legs = [("Before Dec 4, 2026", 0.8), ("Not in 2026", 0.1), ("Before Dec 1, 2026", 0.2)]
    row = _row(_music(_spotify_market(8, "When will Spotify release 2026 Wrapped?", legs)), 8)
    assert row["ladder"] is False
    assert [o["name"] for o in row["top_outcomes"]] == [
        "Before Dec 4, 2026", "Before Dec 1, 2026", "Not in 2026",
    ]


def test_a_single_leg_binary_is_not_a_ladder():
    row = _row(
        _music(_spotify_market(109277, "Will Playboi Carti release BABY BOI this year?",
                               [("Yes", 0.215)])),
        109277,
    )
    assert row["ladder"] is False

