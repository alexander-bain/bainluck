"""Guardrails for the MLB pre-game polling tier (issue #892).

These tests lock in the cost-sensitive configuration the ops lane sized at
~2.48%/mo. The Odds API bills per ``events x market_types x regions`` (gotcha
#11), so the biggest regression risks are silent config drift: adding ``us2``
(doubles cost), widening the window, or overlapping the existing 0-2h "soon"
tier. Catch those here rather than on the monthly quota bill.
"""

from app.tasks import odds_polling as op
from app.tasks import celery_app


class TestPregameConfig:
    def test_scoped_to_mlb_only(self):
        assert op.MLB_PREGAME_SPORT_KEY == "baseball_mlb"

    def test_us_region_only(self):
        # Adding us2 would push the tier from ~2.5% to ~5% of the monthly
        # budget (#892 sizing). Keep it single-region.
        assert op.MLB_PREGAME_REGIONS == "us"
        assert "us2" not in op.MLB_PREGAME_REGIONS

    def test_full_game_markets(self):
        assert set(op.MLB_PREGAME_MARKETS.split(",")) == {"h2h", "spreads", "totals"}

    def test_window_starts_at_t_minus_2h_no_soon_overlap(self):
        # The "soon" tier owns 0-2h; the pre-game window must end at T-2h so the
        # two never double-poll.
        assert op.MLB_PREGAME_WINDOW_START_H == 2

    def test_window_ends_at_48h(self):
        assert op.MLB_PREGAME_WINDOW_END_H == 48
        assert op.MLB_PREGAME_WINDOW_START_H < op.MLB_PREGAME_WINDOW_END_H

    def test_min_interval_allows_30min_beat(self):
        # The beat fires every 30 min (1800s); the floor must be below that or
        # every other fire would be skipped by the interval gate.
        assert op.MLB_PREGAME_MIN_INTERVAL < 1800


class TestPregameWiring:
    def test_task_registered(self):
        assert "app.tasks.poll_mlb_pregame" in celery_app.tasks

    def test_beat_entry_runs_every_30min(self):
        entry = celery_app.conf.beat_schedule.get("poll-mlb-pregame")
        assert entry is not None
        assert entry["task"] == "app.tasks.poll_mlb_pregame"
        # crontab(minute="*/30") → fires at :00 and :30 only.
        assert entry["schedule"].minute == {0, 30}
