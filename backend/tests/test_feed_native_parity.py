"""#240 Item 4 + Item 2b: native feed parity guards.

- All-0% cards are suppressed at the quality layer (Alex's 3× 0% golf cards).
- Live game events with team media survive Discover-mode noise filtering so the
  native Live Now tab and the live badge stay honest (#1091: game events are
  never capped into an empty tab).
"""

from app.routes.feed import (
    _suppress_zero_probability_cards,
    _filter_discover_event_noise,
    _demote_non_exceptional_discover_events,
)


class TestSuppressZeroProbabilityCards:
    def test_drops_futures_card_with_all_zero_outcomes(self):
        items = [
            {
                "type": "futures",
                "data": {
                    "leader_probability": 0.0,
                    "outcomes": [
                        {"name": "Golfer A", "probability": 0.0},
                        {"name": "Golfer B", "probability": 0.0},
                    ],
                },
            }
        ]
        kept, dropped = _suppress_zero_probability_cards(items)
        assert dropped == 1
        assert kept == []

    def test_keeps_futures_card_with_a_positive_outcome(self):
        items = [
            {
                "type": "futures",
                "data": {
                    "leader_probability": 0.42,
                    "outcomes": [
                        {"name": "A", "probability": 0.42},
                        {"name": "B", "probability": 0.0},
                    ],
                },
            }
        ]
        kept, dropped = _suppress_zero_probability_cards(items)
        assert dropped == 0
        assert len(kept) == 1

    def test_never_suppresses_events_even_at_zero(self):
        # A game at 0% home prob is a near-certain away win — still a real story.
        items = [
            {"type": "event", "data": {"current_odds": {"home_probability": 0.0}}}
        ]
        kept, dropped = _suppress_zero_probability_cards(items)
        assert dropped == 0
        assert len(kept) == 1

    def test_keeps_card_with_no_evaluable_outcomes(self):
        items = [{"type": "futures", "data": {"outcomes": []}}]
        kept, dropped = _suppress_zero_probability_cards(items)
        assert dropped == 0
        assert len(kept) == 1


class TestLiveEventSurvivesDiscoverNoiseFilter:
    def _live_event(self, *, with_media: bool, score: float = 35.0) -> dict:
        data = {"status": "live"}
        if with_media:
            data["home_team_data"] = {"logo": "x", "primary_color": "#000"}
        return {"type": "event", "score": score, "data": data}

    def test_routine_live_game_with_media_survives(self):
        """A demoted (score 35) routine live game with logos must NOT be filtered
        out of Discover mode — the native Live Now tab depends on it (#240 2b)."""
        items = [self._live_event(with_media=True, score=35.0)]
        _demote_non_exceptional_discover_events(items)  # caps at 35 (no exception)
        out = _filter_discover_event_noise(items)
        assert len(out) == 1, "live game with team media should survive"

    def test_obscure_no_media_live_game_still_removed(self):
        """An obscure no-logo live game (Alex's 'unknown Copa América games')
        still gets filtered from Discover."""
        items = [self._live_event(with_media=False, score=35.0)]
        out = _filter_discover_event_noise(items)
        assert out == [], "obscure no-media live game should be removed"
