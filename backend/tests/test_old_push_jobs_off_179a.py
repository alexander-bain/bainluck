"""Ruling 179-A (Alex, Nov 13 2026): the two old push jobs are switched off.

The daily challenge push and big-move alerts no longer run on a timer. Their
tasks stay registered so a switch-back is one beat entry, not a revert of code.
"""

from app.tasks import celery_app

OFF_TASKS = (
    "app.tasks.send_daily_challenge_push",
    "app.tasks.send_big_move_alerts",
)


def test_neither_old_push_job_is_on_the_beat_schedule():
    scheduled = {entry.get("task") for entry in celery_app.conf.beat_schedule.values()}
    for task in OFF_TASKS:
        assert task not in scheduled, f"{task} is back on a timer; ruling 179-A switched it off"
    for name in ("daily-challenge-push", "big-move-alerts"):
        assert name not in celery_app.conf.beat_schedule


def test_both_tasks_stay_registered_so_switching_back_is_one_entry():
    for task in OFF_TASKS:
        assert task in celery_app.tasks


def test_the_new_notification_pushes_keep_their_timers():
    # 179-A switches off the OLD jobs only; the morning digest stays on.
    assert "morning-digest-daily" in celery_app.conf.beat_schedule
