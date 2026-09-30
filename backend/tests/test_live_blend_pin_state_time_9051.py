"""#9051: the current blend pin follows real quotes within the same minute.

A synthetic presentation endpoint is not a new quote. Its x position is the
server's exact as-of time; the surviving quote's observation stays unchanged.
"""
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

from app.routes.events import _pin_blend_edge

QUOTE = datetime(2026, 9, 27, 5, 0, tzinfo=timezone.utc)
FRAME = datetime(2026, 9, 27, 5, 1, 10, tzinfo=timezone.utc)
NOW = datetime(2026, 9, 27, 5, 1, 20, 123456, tzinfo=timezone.utc)


def _event(status="live"):
    return SimpleNamespace(
        status=status, home_score=None, away_score=None, completed_at=None,
        espn_win_prob_home=None, opening_home_probability=0.5,
        win_probability_sources={"polymarket": {"value": 0.4, "updated_at": QUOTE.isoformat()}},
    )


def test_current_pin_does_not_overwrite_real_publication_in_its_minute():
    event = _event()
    sources = deepcopy(event.win_probability_sources)
    line = [{"timestamp": QUOTE.isoformat(), "home_probability": 0.45},
            {"timestamp": FRAME.isoformat(), "home_probability": 0.6}]
    before = deepcopy(line)
    assert _pin_blend_edge(line, event, is_live=True, now=NOW, served_blend=0.4)
    assert line[:-1] == before, "the real60% quote must survive unchanged"
    assert line[-1] == {"timestamp": NOW.isoformat(), "home_probability": 0.4}
    assert event.win_probability_sources == sources, "presentation must not redate quotes"


def test_current_pin_follows_held_frame_even_when_server_history_only_has_minute_buckets():
    line = [{"timestamp": QUOTE.isoformat(), "home_probability": 0.45}]
    assert _pin_blend_edge(line, _event(), is_live=True, now=NOW, served_blend=0.4)
    # This is the time comparison used when the page merges a real held frame
    # at05:01:10. Flooring the pin to05:01:00 puts the removed blend last.
    assert datetime.fromisoformat(line[-1]["timestamp"]) > FRAME
    assert line[-1]["timestamp"] == NOW.isoformat()


def test_pregame_pin_retains_existing_minute_policy_and_does_not_append():
    line = [{"timestamp": QUOTE.isoformat(), "home_probability": 0.45},
            {"timestamp": FRAME.isoformat(), "home_probability": 0.6}]
    assert _pin_blend_edge(line, _event("scheduled"), is_live=False, now=NOW, served_blend=0.4)
    assert len(line) == 2
    assert line[-1] == {"timestamp": FRAME.isoformat(), "home_probability": 0.4}


def test_exact_time_pin_is_idempotent_for_the_same_served_value():
    line = [{"timestamp": QUOTE.isoformat(), "home_probability": 0.45}]
    assert _pin_blend_edge(line, _event(), is_live=True, now=NOW, served_blend=0.4)
    once = deepcopy(line)
    assert _pin_blend_edge(line, _event(), is_live=True, now=NOW, served_blend=0.4)
    assert line == once
