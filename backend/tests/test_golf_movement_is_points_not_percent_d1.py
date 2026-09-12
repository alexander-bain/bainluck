"""The golf card's movement is POINTS; it printed a "%" and meant something else.

Found mystery-shopping Discover page one (D48), Sat 2026-09-12 12:24Z. Slot 5, the
Amgen Irish Open, served:

    DP World Tour: Shane Lowry leads at 47.8% (up 10.0% today)

and rendered the same number as a green ``▲10%`` pill on the hero. The payload
behind it was ``{"name": "Shane Lowry", "probability": 0.478, "movement_24h": 0.1}``.

``movement_24h`` is a probability DELTA in 0-1 units — it falls back to
``probability_change_24h`` (``routes/feed.py``, ``_resolve_concept_leader``), which
every writer stores as ``new - previous``. So ``0.1`` is **ten percentage points**:
Lowry went 37.8% -> 47.8%. Printed as "up 10.0%" a reader reads a tenth more than he
had — about 4.8 points — which is less than half the real move, and in a unit the
number was never in.

THE SAME SENTENCE FAMILY ALREADY GETS THIS RIGHT. The futures cards say "Down 22.5
points since Feb 3", via ``feed_reasons._point_change`` — whose docstring is
literally "Convert a probability delta to percentage points for display" and whose
arithmetic, ``round(abs(value) * 100, 1)``, is character-for-character what the golf
line was doing before printing a different unit beside it. Two renderers, one
transform, two nouns. The fix imports the shared formatter instead of repeating the
arithmetic, because repeating it is how they drifted.

This is D1 (#4066) clause (a) — "movement is points since a dated baseline … never a
relative % off a tiny base" — reaching a first-ten card by the inverse error: points
printed as a percent.

Guards here, in the order they matter:

1. the served reason names points and carries no bare "%" on the movement;
2. the number itself is unchanged (this was a unit LABEL bug, not an arithmetic one);
3. the golf renderer and the futures formatter cannot drift apart again;
4. "1 point" is singular, and "10.0" does not print its trailing zero.

The harness drives the REAL ``_score_golf_tournaments`` over a stubbed golf base,
copied deliberately from ``test_golf_tour_badge_uxp185.py`` — whose own docstring
records that an earlier version of that guard rebuilt the f-string itself and stayed
green when the fix was reverted. Rebuilding the sentence under test is the vacuity
trap for this exact line.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.utils.feed_reasons import _points


#: Gotcha #44 — offset from the clock, never a literal date, or this window becomes
#: a calendar window that expires. Same derivation as the uxp185 guard.
_FEED_NOW = (datetime.now(timezone.utc) - timedelta(minutes=1)).replace(microsecond=0)

#: The reported specimen: Lowry at 47.8% having gained ten points on the day.
_LOWRY_PROBABILITY = 0.478
_LOWRY_MOVEMENT = 0.1


def _tournament(movement: float, probability: float = _LOWRY_PROBABILITY) -> dict:
    """One golf-base entry, shaped as `get_golf_base` publishes it."""
    return {
        "key": "irish-open",
        "name": "Amgen Irish Open",
        "slug": "amgen-irish-open",
        "tour": "dp_world",
        "tour_label": "DP World Tour",
        "is_major": False,
        "is_tour_event": True,
        "commence_time": (_FEED_NOW + timedelta(days=1)).isoformat(),
        "resolution_date": (_FEED_NOW + timedelta(days=4)).isoformat(),
        "start_date": (_FEED_NOW + timedelta(days=1)).isoformat(),
        "end_date": (_FEED_NOW + timedelta(days=4)).isoformat(),
        "market_names": ["Amgen Irish Open Winner"],
        "market_ids": [1],
        "golfers": [
            {
                "id": 1,
                "name": "Shane Lowry",
                "probability": probability,
                "movement_24h": movement,
                "probability_change_24h": movement,
                "american_odds": None,
                "is_winner": None,
                "rank": 1,
            }
        ],
    }


def _reason(monkeypatch, movement: float) -> str:
    """The reason string the REAL scorer serves for that tournament."""
    import app.utils.golf_base as golf_base
    from app.routes import feed as feed_module

    async def _fake_base(db, now, stages=None):
        return ([_tournament(movement)], "fresh")

    monkeypatch.setattr(golf_base, "get_golf_base", _fake_base)
    items = asyncio.run(
        feed_module._score_golf_tournaments(None, _FEED_NOW, None, None)
    )
    assert len(items) == 1, f"card dropped, so the reason is untested: {items}"
    return items[0]["reason"]


# --- 1. The reported defect ----------------------------------------------

class TestTheMovementIsSaidInPoints:
    def test_the_reported_card_says_points(self, monkeypatch):
        """#2757-adjacent / D1(a), head-on: the Irish Open sentence."""
        reason = _reason(monkeypatch, _LOWRY_MOVEMENT)
        assert reason == "DP World Tour: Shane Lowry leads at 47.8% (up 10 points today)"

    def test_the_movement_clause_carries_no_percent_sign(self, monkeypatch):
        """The `47.8%` is a probability and keeps its sign; the delta must not.

        Asserted on the parenthetical alone so the leader's own percentage — which
        is correctly a percent — cannot satisfy or break this.
        """
        reason = _reason(monkeypatch, _LOWRY_MOVEMENT)
        clause = reason[reason.index("(") : reason.index(")") + 1]
        assert "%" not in clause, (
            f"the movement clause still prints a percent sign: {clause!r}. "
            "A probability delta of 0.1 is ten POINTS, not ten percent."
        )
        assert "points" in clause

    def test_a_downward_move_is_also_points(self, monkeypatch):
        clause = _reason(monkeypatch, -0.075)
        assert "(down 7.5 points today)" in clause
        assert "%" not in clause[clause.index("(") :]


# --- 2. The number did not move ------------------------------------------

class TestOnlyTheUnitChanged:
    """This was a label bug. Silently changing the magnitude would be worse."""

    @pytest.mark.parametrize("movement", [0.1, 0.015, -0.225, 0.078])
    def test_the_magnitude_is_still_delta_times_one_hundred(self, monkeypatch, movement):
        reason = _reason(monkeypatch, movement)
        expected = round(abs(movement) * 100, 1)
        if expected == int(expected):
            expected = int(expected)
        assert f"{expected} point" in reason, reason


# --- 3. The two renderers cannot drift again -----------------------------

class TestTheGolfCardUsesTheSharedFormatter:
    """The root cause was two copies of one transform, not a typo."""

    @pytest.mark.parametrize("movement", [0.1, 0.02, -0.375, 0.011])
    def test_the_served_clause_is_exactly_the_futures_formatter(
        self, monkeypatch, movement
    ):
        reason = _reason(monkeypatch, movement)
        assert _points(movement) in reason, (
            f"golf served {reason!r} but the shared formatter says "
            f"{_points(movement)!r} — the two have drifted apart again"
        )

    def test_the_formatter_is_the_one_the_futures_cards_use(self):
        """Pins the arithmetic the docstring promises, so a change there is seen."""
        assert _points(0.225) == "22.5 points"  # "Down 22.5 points since Feb 3"
        assert _points(0.1) == "10 points"


# --- 4. The small print --------------------------------------------------

class TestTheCopyReadsLikeEnglish:
    def test_one_point_is_singular(self, monkeypatch):
        assert "(up 1 point today)" in _reason(monkeypatch, 0.01)

    def test_a_whole_number_drops_its_trailing_zero(self, monkeypatch):
        """The old string said "10.0%"; "10.0 points" would be no better."""
        reason = _reason(monkeypatch, 0.1)
        assert "10 points" in reason
        assert "10.0" not in reason

    def test_a_fractional_move_keeps_its_decimal(self, monkeypatch):
        assert "7.8 points" in _reason(monkeypatch, 0.078)

    def test_a_move_below_the_threshold_says_nothing_at_all(self, monkeypatch):
        """Unchanged by this ship, and the reason it is safe to assert equality
        in the first test: sub-1-point noise never reaches the sentence."""
        reason = _reason(monkeypatch, 0.004)
        assert "point" not in reason
        assert reason == "DP World Tour: Shane Lowry leads at 47.8%"
