"""#10090 — the Kalshi socket's upcoming-game window is 6 h, with no setting.

`KALSHI_WS_UPCOMING_HOURS` was tried at 2 on 2026-11-01 and removed 23 minutes
later when Kalshi rate-limited the 30-second poll that covered the gap; the
settings freeze deleted the knob (docs/live-settings.md). The predicate is the
SQL text it always was.
"""

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


def test_the_predicate_is_byte_identical_to_the_six_hour_window():
    assert _sql(kalshi_ws._kalshi_slate_event_window()) == _sql(_base_window())


def test_the_knob_is_gone():
    assert not hasattr(kalshi_ws, "KALSHI_WS_UPCOMING_HOURS")
    assert not hasattr(kalshi_ws, "_kalshi_upcoming_hours_env")
