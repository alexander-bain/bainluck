"""#10090 — the Kalshi socket's upcoming-game window is a setting.

`_kalshi_slate_event_window`'s scheduled arm ended at a literal
`NOW() + INTERVAL '6 hours'`. It now reads `KALSHI_WS_UPCOMING_HOURS` (env,
read once at import, default 6, clamped to 1..6), as the Polymarket socket
reads `PM_WS_UPCOMING_HOURS`. Unset, the predicate is the same SQL text as
before; set to 2, only the scheduled arm's upper bound moves. 11/01: the
Kalshi venue process ran at 83-89% of a core on the Sunday slate.
"""

import logging

import pytest
from sqlalchemy.dialects import postgresql

from app.tasks import kalshi_ws


def _sql(clause) -> str:
    return str(clause.compile(dialect=postgresql.dialect(),
                              compile_kwargs={"literal_binds": True}))


def _base_window():
    """The predicate exactly as it stood before this setting."""
    from sqlalchemy import and_, or_, text

    from app.models.models import Event
    from app.tasks.ws_slate import suspended_open_market_arm

    return or_(
        Event.status == "live",
        and_(
            Event.status == "scheduled",
            Event.commence_time.isnot(None),
            Event.commence_time <= text("NOW() + INTERVAL '6 hours'"),
        ),
        suspended_open_market_arm(),
    )


def test_at_the_default_the_predicate_is_byte_identical_to_before(monkeypatch):
    assert kalshi_ws.KALSHI_WS_UPCOMING_HOURS_DEFAULT == 6
    monkeypatch.setattr(kalshi_ws, "KALSHI_WS_UPCOMING_HOURS", 6)
    assert _sql(kalshi_ws._kalshi_slate_event_window()) == _sql(_base_window())


def test_two_moves_only_the_upper_bound(monkeypatch):
    monkeypatch.setattr(kalshi_ws, "KALSHI_WS_UPCOMING_HOURS", 2)
    want = _sql(_base_window()).replace("NOW() + INTERVAL '6 hours'",
                                        "NOW() + INTERVAL '2 hours'")
    assert _sql(kalshi_ws._kalshi_slate_event_window()) == want


def test_the_literal_can_only_hold_a_number(monkeypatch):
    monkeypatch.setattr(kalshi_ws, "KALSHI_WS_UPCOMING_HOURS", "2 hours'; DROP TABLE events; --")
    with pytest.raises(ValueError):
        kalshi_ws._kalshi_slate_event_window()


@pytest.mark.parametrize("raw, want", [(None, 6), ("  ", 6), ("2", 2), (" 2 ", 2), ("1", 1),
                                       ("0", 1), ("-3", 1), ("7", 6), ("48", 6),
                                       ("2.5", 6), ("2h", 6), ("two", 6)])
def test_the_env_clamps_to_one_through_six_and_anything_else_is_six(monkeypatch, raw, want):
    if raw is None:
        monkeypatch.delenv("KALSHI_WS_UPCOMING_HOURS", raising=False)
    else:
        monkeypatch.setenv("KALSHI_WS_UPCOMING_HOURS", raw)
    assert kalshi_ws._kalshi_upcoming_hours_env() == want


def test_a_clamped_value_warns_once(monkeypatch, caplog):
    monkeypatch.setenv("KALSHI_WS_UPCOMING_HOURS", "12")
    with caplog.at_level(logging.WARNING, logger=kalshi_ws.logger.name):
        assert kalshi_ws._kalshi_upcoming_hours_env() == 6
    assert [r.getMessage() for r in caplog.records] == [
        "Kalshi WS: KALSHI_WS_UPCOMING_HOURS='12' is outside 1..6; using 6"]
