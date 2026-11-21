"""#13292 — finished three-way soccer games preserve ``draw_probability`` in ``prematch_odds``.

Specimen from Builder C's trace on #13292: Espanyol 1, Athletic Bilbao 0
(La Liga, event 15342130). ``win_prob_snapshots`` already held Kalshi's full
three-way pregame partition (``home=0.685, away=0.115, draw=0.200``), and
``PREMATCH_PRIOR_SQL`` selected ``draw_probability``, but
``resolve_prematch_reading`` / ``serialize_prematch_odds`` dropped it. Because
1.0.7 iOS decodes ``prematch_odds.draw_probability`` and falls back to the
2-row layout (withholding the away side on soccer) when ``draw_probability`` is
missing, the game header printed "69%" for Athletic Bilbao and blank for
Espanyol while Discover printed "12% underdog".

Pinned here:
1. Venue rungs (Kalshi / Polymarket) emit ``draw_probability`` when the row
   carries a valid three-way partition, and NEVER fabricate one when ``draw`` is
   missing or inconsistent.
2. Books rung emits ``draw_probability`` on draw-priced sports when the stored
   de-vigged opening pair is genuinely sub-unit (matching ``opening_odds``), and
   NEVER on two-way sports or complement-only pairs.
3. ``_second_slot`` tolerates minimal ``SimpleNamespace`` readings without
   ``away_probability`` / ``draw_probability`` attributes.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.tasks.prediction_market_matching import _second_slot
from app.utils.prematch_reading import (
    resolve_prematch_reading,
    serialize_prematch_odds,
)


def test_espanyol_bilbao_15342130_emits_kalshi_draw_probability():
    """Real specimen #13292: Kalshi (0.685, 0.115, 0.200) -> full 3-way prematch_odds."""
    by_source = {"kalshi": (0.685, 0.115, 0.200)}
    resolved = resolve_prematch_reading(
        by_source=by_source,
        books_home=0.672,
        books_away=0.126,
        sport="soccer_spain_la_liga",
    )
    assert resolved == {
        "home_probability": 0.685,
        "away_probability": 0.115,
        "draw_probability": 0.200,
        "source": "kalshi",
    }

    serialized = serialize_prematch_odds(
        by_source=by_source,
        books_home=0.672,
        books_away=0.126,
        sport="soccer_spain_la_liga",
    )
    assert serialized is not None
    assert serialized["home_probability"] == pytest.approx(0.685)
    assert serialized["away_probability"] == pytest.approx(0.115)
    assert serialized["draw_probability"] == pytest.approx(0.200)
    assert serialized["home_rendered_percent"] == 69
    assert serialized["away_rendered_percent"] == 12
    assert serialized["source"] == "kalshi"


def test_books_rung_emits_draw_probability_on_three_way_soccer():
    """Books rung on soccer (0.672, 0.126) -> draw_probability 0.202 matching opening_odds."""
    serialized = serialize_prematch_odds(
        by_source={},
        books_home=0.672,
        books_away=0.126,
        sport="soccer_spain_la_liga",
    )
    assert serialized is not None
    assert serialized["source"] == "books"
    assert serialized["home_probability"] == pytest.approx(0.672)
    assert serialized["away_probability"] == pytest.approx(0.126)
    assert serialized["draw_probability"] == pytest.approx(0.202)


def test_two_way_sports_never_emit_draw_probability():
    """Wrong neighbour: NBA / NFL / NHL never emit draw_probability."""
    for sport in ("basketball_nba", "americanfootball_nfl", "icehockey_nhl"):
        serialized = serialize_prematch_odds(
            by_source={"kalshi": (0.62, 0.38)},
            books_home=0.60,
            books_away=0.40,
            sport=sport,
        )
        assert serialized is not None
        assert "draw_probability" not in serialized


def test_drawless_venue_reading_never_fabricates_draw_probability():
    """Wrong neighbour: a venue row with draw=None must NOT invent draw from 1 - home - away."""
    serialized = serialize_prematch_odds(
        by_source={"kalshi": (0.685, 0.115, None)},
        books_home=0.672,
        books_away=0.126,
        sport="soccer_spain_la_liga",
    )
    assert serialized is not None
    assert serialized["source"] == "kalshi"
    assert "draw_probability" not in serialized


def test_inconsistent_venue_draw_is_not_emitted():
    """Wrong neighbour: a venue draw violating the partition tolerance is not emitted."""
    serialized = serialize_prematch_odds(
        by_source={"kalshi": (0.685, 0.115, 0.50)},
        books_home=0.672,
        books_away=0.126,
        sport="soccer_spain_la_liga",
    )
    assert serialized is not None
    assert "draw_probability" not in serialized


def test_second_slot_handles_stub_reading_without_away_or_draw():
    """Regression guard for live_blend_refresh stub SimpleNamespace readings."""
    stub = SimpleNamespace(home_probability=0.62)
    away, draw = _second_slot(stub, 0.62)
    assert away == pytest.approx(0.38)
    assert draw is None
