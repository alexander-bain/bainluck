"""#3481 / #3480: the two `turbo_collapse_*` beats stay retired.

Measured on production 2026-10-02 before the retirement (task-metrics
``last_result_summary``), and it is the whole reason this guard exists:

* ``turbo_collapse_futures``, started 12:30:06Z, ran 21.5 min and returned
  ``{"rows_deleted": 0, "keepers_updated": 0, "partitions_processed": 5000}``;
  its partition pick was a parallel sequential scan of the 240M-row / 62 GB
  ``futures_odds_snapshots`` heap, seen in ``pg_stat_activity`` at 728 s;
* ``turbo_collapse_odds`` (07:04Z, 16 min) returned the same 0 / 0 / 5000.

The pick has no cursor and a collapse leaves its keepers behind, so a processed
partition stays eligible and the same set returns every pass (the defect #7878
fixed for win-prob only). Retiring the beats therefore changes no stored row; it
removes up to ~35 minutes of whole-table reads, four times a day, from the
database every reader shares.

What is deliberately NOT retired, and asserted below so a later tidy-up cannot
take it with them: the tasks themselves (the admin ``/cleanup/turbo-collapse``
route still queues them by hand) and the daily ``collapse-*-snapshots-daily``
entries, including win-prob's watermarked pass, which does real work.
"""

from app.tasks import celery_app

RETIRED_BEATS = ("turbo-collapse-futures", "turbo-collapse-odds")
RETIRED_TASKS = ("app.tasks.turbo_collapse_futures", "app.tasks.turbo_collapse_odds")


def _schedule():
    return celery_app.conf.beat_schedule


def test_the_turbo_beat_names_are_not_scheduled():
    for name in RETIRED_BEATS:
        assert name not in _schedule(), f"{name} came back (#3481: it wrote 0 rows)"


def test_no_beat_entry_schedules_a_turbo_task_under_another_name():
    # A rename would dodge the name check above; the task is what costs.
    offenders = {
        name: entry["task"]
        for name, entry in _schedule().items()
        if entry.get("task") in RETIRED_TASKS
    }
    assert offenders == {}


def test_the_tasks_stay_registered_for_the_admin_route():
    for task in RETIRED_TASKS:
        assert task in celery_app.tasks, f"{task} must stay callable by hand"


def test_the_daily_collapse_passes_are_untouched():
    daily = {
        name: entry
        for name, entry in _schedule().items()
        if entry.get("task") == "app.tasks.collapse_snapshots"
    }
    tables = sorted(entry["kwargs"]["table"] for entry in daily.values())
    assert tables == ["futures", "odds", "winprob"]
