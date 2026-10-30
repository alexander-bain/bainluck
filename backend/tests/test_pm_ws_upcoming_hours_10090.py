"""#10090 — the Polymarket socket's upcoming-game window is a setting.

`_slate_event_window`'s scheduled arm used to end at a literal
`NOW() + INTERVAL '6 hours'`. It now reads `PM_WS_UPCOMING_HOURS` (env, read
once at import, default 6, clamped to 1..6). Unset, the predicate is the same
SQL text as before; set to 3, only the scheduled arm's upper bound moves.

The real-Postgres half (a 4 h game dropped, a 2 h game, a live game and a
suspended open market kept) is
`integration/test_ws_slate_upcoming_hours_pg_10090.py`.
"""

import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy.dialects import postgresql

from app.tasks import polymarket_ws


def _sql(clause) -> str:
    return str(
        clause.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


def _base_window():
    """The predicate exactly as it stood before #10090 (62557fad)."""
    from sqlalchemy import and_, or_, text

    from app.models.models import Event
    from app.tasks.ws_slate import suspended_open_market_arm

    return or_(
        Event.status == "live",
        and_(
            Event.status == "scheduled",
            Event.commence_time.isnot(None),
            Event.commence_time >= text(
                f"NOW() - INTERVAL '{int(polymarket_ws.SLATE_MAX_AGE_HOURS)} hours'"
            ),
            Event.commence_time <= text("NOW() + INTERVAL '6 hours'"),
        ),
        suspended_open_market_arm(),
    )


class TestTheDefaultIsTheOldWindow:
    def test_the_default_is_six(self):
        assert polymarket_ws.PM_WS_UPCOMING_HOURS_DEFAULT == 6

    def test_at_six_the_predicate_is_byte_identical_to_before(self, monkeypatch):
        monkeypatch.setattr(polymarket_ws, "PM_WS_UPCOMING_HOURS", 6)
        assert _sql(polymarket_ws._slate_event_window()) == _sql(_base_window())

    def test_unset_env_reads_six(self, monkeypatch):
        monkeypatch.delenv("PM_WS_UPCOMING_HOURS", raising=False)
        assert polymarket_ws._upcoming_hours_env() == 6

    def test_blank_env_reads_six(self, monkeypatch):
        monkeypatch.setenv("PM_WS_UPCOMING_HOURS", "  ")
        assert polymarket_ws._upcoming_hours_env() == 6


class TestThreeMovesOnlyTheUpperBound:
    def test_three_renders_a_three_hour_bound(self, monkeypatch):
        monkeypatch.setattr(polymarket_ws, "PM_WS_UPCOMING_HOURS", 3)
        sql = _sql(polymarket_ws._slate_event_window())
        assert "events.commence_time <= NOW() + INTERVAL '3 hours'" in sql
        assert "INTERVAL '6 hours'" not in sql

    def test_three_leaves_live_floor_and_suspended_arm_alone(self, monkeypatch):
        monkeypatch.setattr(polymarket_ws, "PM_WS_UPCOMING_HOURS", 3)
        got = _sql(polymarket_ws._slate_event_window())
        want = _sql(_base_window()).replace(
            "NOW() + INTERVAL '6 hours'", "NOW() + INTERVAL '3 hours'"
        )
        # The only difference from the old predicate is that one literal.
        assert got == want
        assert "events.status = 'live' OR" in got
        assert "NOW() - INTERVAL '24 hours'" in got

    def test_the_bound_is_read_at_call_time_from_the_module_setting(
        self, monkeypatch
    ):
        monkeypatch.setattr(polymarket_ws, "PM_WS_UPCOMING_HOURS", 2)
        assert "NOW() + INTERVAL '2 hours'" in _sql(polymarket_ws._slate_event_window())

    def test_the_literal_can_only_hold_a_number(self, monkeypatch):
        # Rendered through int(), like the floor: a non-number never reaches SQL.
        monkeypatch.setattr(
            polymarket_ws, "PM_WS_UPCOMING_HOURS", "3 hours'; DROP TABLE events; --"
        )
        with pytest.raises(ValueError):
            polymarket_ws._slate_event_window()


class TestBadValuesClamp:
    @pytest.mark.parametrize(
        "raw, want",
        [
            ("3", 3),
            (" 3 ", 3),
            ("1", 1),
            ("6", 6),
            ("0", 1),
            ("-4", 1),
            ("7", 6),
            ("48", 6),
        ],
    )
    def test_whole_numbers_clamp_to_one_through_six(self, monkeypatch, raw, want):
        monkeypatch.setenv("PM_WS_UPCOMING_HOURS", raw)
        assert polymarket_ws._upcoming_hours_env() == want

    @pytest.mark.parametrize("raw", ["3.5", "abc", "6h", "three", "nan"])
    def test_anything_else_is_the_default(self, monkeypatch, raw):
        monkeypatch.setenv("PM_WS_UPCOMING_HOURS", raw)
        assert polymarket_ws._upcoming_hours_env() == 6

    def test_a_clamped_value_warns_once(self, monkeypatch, caplog):
        monkeypatch.setenv("PM_WS_UPCOMING_HOURS", "12")
        with caplog.at_level(logging.WARNING, logger=polymarket_ws.logger.name):
            assert polymarket_ws._upcoming_hours_env() == 6
        assert [r.getMessage() for r in caplog.records] == [
            "Polymarket WS: PM_WS_UPCOMING_HOURS='12' is outside 1..6; using 6"
        ]

    def test_an_unparseable_value_warns_once(self, monkeypatch, caplog):
        monkeypatch.setenv("PM_WS_UPCOMING_HOURS", "3h")
        with caplog.at_level(logging.WARNING, logger=polymarket_ws.logger.name):
            assert polymarket_ws._upcoming_hours_env() == 6
        assert len(caplog.records) == 1
        assert "not a whole number" in caplog.records[0].getMessage()

    def test_an_in_range_value_is_silent(self, monkeypatch, caplog):
        monkeypatch.setenv("PM_WS_UPCOMING_HOURS", "3")
        with caplog.at_level(logging.WARNING, logger=polymarket_ws.logger.name):
            polymarket_ws._upcoming_hours_env()
        assert caplog.records == []


def test_the_module_setting_is_read_from_the_env_at_import():
    """Restart-only re-scope: a fresh process with the env set imports 3."""
    backend = Path(__file__).resolve().parents[1]
    env = {**os.environ, "PM_WS_UPCOMING_HOURS": "3"}
    out = subprocess.run(
        [
            sys.executable,
            "-c",
            "from app.tasks import polymarket_ws as m; print(m.PM_WS_UPCOMING_HOURS)",
        ],
        cwd=backend,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert out.returncode == 0, out.stderr[-2000:]
    assert out.stdout.strip().splitlines()[-1] == "3"
