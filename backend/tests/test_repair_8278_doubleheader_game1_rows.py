"""#8278: the doubleheader repair touches game 2's game-1 window and nothing else.

The script's judgment is three pure refusals plus a pinned predicate. These tests
drive the refusals with dicts and read the predicate text; the SQL's selection
rests on the production measurement pinned in ``TABLES`` and re-counted by the
script before it writes.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load():
    sys.path.insert(0, str(_SCRIPTS))
    spec = importlib.util.spec_from_file_location(
        "repair_8278", _SCRIPTS / "repair_8278_doubleheader_game1_rows.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


m = _load()


def _row(
    id_,
    status="scheduled",
    commence=None,
    home="Baltimore Orioles",
    away="Toronto Blue Jays",
):
    return {
        "id": id_,
        "home_team_name": home,
        "away_team_name": away,
        "status": status,
        "commence_time": commence or m.GAME2_COMMENCE,
    }


GAME1 = _row(
    m.GAME1_ID,
    status="completed",
    commence=datetime(2026, 9, 23, 17, 35, tzinfo=timezone.utc),
)
GAME2 = _row(m.GAME2_ID)


def test_refuses_off_the_heavy_app(monkeypatch):
    monkeypatch.setenv("HEROKU_APP_NAME", "bainluck")
    assert "bainluck-heavy" in m.wrong_app_refusal()
    monkeypatch.delenv("HEROKU_APP_NAME")
    assert m.wrong_app_refusal() is not None
    monkeypatch.setenv("HEROKU_APP_NAME", "bainluck-heavy")
    assert m.wrong_app_refusal() is None


def test_the_measured_rows_pass():
    assert m.rows_refusal(GAME1, GAME2) is None


def test_game2_rescheduled_refuses():
    moved = dict(GAME2, commence_time=datetime(2026, 9, 24, 17, 5, tzinfo=timezone.utc))
    assert "moved" in m.rows_refusal(GAME1, moved)


def test_game1_not_completed_refuses():
    assert "expected 'completed'" in m.rows_refusal(dict(GAME1, status="live"), GAME2)


def test_a_row_that_is_no_longer_this_fixture_refuses():
    assert m.rows_refusal(GAME1, dict(GAME2, home_team_name="New York Yankees"))
    assert m.rows_refusal(None, GAME2)
    assert m.rows_refusal(GAME1, None)


def test_exact_counts_pass_and_any_drift_refuses():
    pinned = {t: n for t, (_, n) in m.TABLES.items()}
    assert pinned == {
        "odds_snapshots": 1913,
        "score_snapshots": 113,
        "win_prob_snapshots": 47,
    }
    assert m.counts_refusal(pinned) is None
    for t in pinned:
        for delta in (-1, 1):
            assert t in m.counts_refusal(dict(pinned, **{t: pinned[t] + delta}))
    assert m.counts_refusal({}) is not None


def test_population_is_game2_inside_game1s_window_only():
    for t in m.TABLES:
        where = m.population_where(t)
        assert f"event_id = {m.GAME2_ID}" in where
        assert str(m.GAME1_ID) not in where
        assert "captured_at >= '2026-09-23 17:30:00+00'" in where
        assert "captured_at < '2026-09-23 20:30:00+00'" in where
    # Kalshi's series is game 2's own market and must never be in scope.
    assert m.population_where("win_prob_snapshots").endswith(
        "(source IN ('mlb', 'stat_model'))"
    )


def test_window_closes_before_game2_can_produce_an_in_game_row():
    end = datetime.fromisoformat(m.WINDOW_END.replace("+00", "+00:00"))
    assert end < m.GAME2_COMMENCE


def test_backups_are_per_table_backup_prefixed():
    assert {m.backup_table(t) for t in m.TABLES} == {
        "backup_8278_odds_snapshots",
        "backup_8278_score_snapshots",
        "backup_8278_win_prob_snapshots",
    }
