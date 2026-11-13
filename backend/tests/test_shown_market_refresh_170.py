"""Decision 170 / 188 (Alex, Nov 13): every number a page shows is read from its
venue in the last 30 minutes, and a market its venue reports closed leaves
Discover.

* ``refresh_shown_futures_prices`` re-runs the hourly price writer in
  identity-only mode (both class budgets 0) with 15-minute clocks, at :04, :19
  and :34 on ``heavy``; with the hourly :50 pass that is a re-read every 14-16
  minutes. The hourly writer alone reached 895 of 2,568 candidates on Nov 13 and
  left 70 of 95 Polymarket Discover cards over 30 minutes old (#12633).
* Discover's candidate pool drops a market carrying the writer's venue-closed
  stamp. Category pages keep ``market_reads_settled``'s 48-hour rule.
"""

from datetime import datetime, timezone

from sqlalchemy.dialects import postgresql

import app.tasks as tasks_mod
from app.routes.feed import _discover_candidate_pool_specs
from app.utils.futures_liveness import VENUE_SETTLED_KEY

TASK = "app.tasks.refresh_shown_futures_prices"
NOW = datetime(2026, 11, 13, 17, 0, tzinfo=timezone.utc)


def test_the_pass_is_the_hourly_writer_in_identity_only_mode(monkeypatch):
    calls, seen = [], {}

    async def _run():
        return {"task": "futures_price_refresh"}

    def _writer(**kwargs):
        calls.append(kwargs)
        return _run()

    def _tracked(name, coro):
        seen["tracked_as"] = name
        coro.close()
        return {"ok": True}

    monkeypatch.setattr("app.tasks.futures_price_refresh._refresh_stale_futures_prices", _writer)
    monkeypatch.setattr(tasks_mod, "_tracked_run", _tracked)
    tasks_mod.celery_app.tasks[TASK].run()

    (kwargs,) = calls
    assert kwargs["kalshi_budget"] == 0 and kwargs["polymarket_budget"] == 0
    assert kwargs["served_refresh_minutes"] == tasks_mod.SHOWN_REFRESH_MINUTES == 15
    assert kwargs["registered_refresh_minutes"] == 15
    assert kwargs["category_page_refresh_minutes"] == 15
    assert kwargs["threshold_label_per_run"] == 0
    # its own run history, never the hourly pass's
    assert seen["tracked_as"] == "shown_futures_refresh"


def test_it_runs_three_times_an_hour_on_heavy_and_never_beside_the_hourly_pass():
    beat = tasks_mod.celery_app.conf.beat_schedule
    entry = beat["refresh-shown-futures-prices"]
    assert entry["task"] == TASK
    assert entry["options"]["queue"] == "heavy"
    minutes = sorted(entry["schedule"].minute)
    assert minutes == [4, 19, 34] == list(tasks_mod.SHOWN_REFRESH_BEAT_MINUTES)
    hourly = beat["refresh-stale-futures-prices-hourly"]["schedule"].minute
    assert hourly == {50}
    # with the hourly pass, no gap is longer than 16 minutes
    all_minutes = sorted(minutes + [50])
    gaps = [(b - a) for a, b in zip(all_minutes, all_minutes[1:])] + [60 - all_minutes[-1] + all_minutes[0]]
    assert max(gaps) <= 16
    assert TASK in tasks_mod.HEAVY_TASKS
    assert tasks_mod.celery_app.conf.task_routes[TASK] == {"queue": "heavy"}


def test_no_other_hourly_heavy_beat_shares_its_minutes():
    conf = tasks_mod.celery_app.conf
    clashes = []
    for name, e in conf.beat_schedule.items():
        if name == "refresh-shown-futures-prices":
            continue
        queue = (e.get("options") or {}).get("queue") or (conf.task_routes.get(e["task"]) or {}).get("queue")
        minutes = getattr(e["schedule"], "minute", None)
        if queue != "heavy" or minutes is None or len(minutes) > 12:
            continue  # sub-hourly sweeps (every 3 or 5 minutes) are not hourly neighbours
        if set(minutes) & set(tasks_mod.SHOWN_REFRESH_BEAT_MINUTES):
            clashes.append(name)
    assert clashes == []


def _sql(clauses):
    return " AND ".join(
        str(c.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
        for c in clauses
    )


def test_discover_drops_a_market_its_venue_reports_closed():
    id_filters, _ = _discover_candidate_pool_specs(NOW)
    assert VENUE_SETTLED_KEY in _sql(id_filters)


def test_category_pages_keep_their_own_settled_rule():
    id_filters, _ = _discover_candidate_pool_specs(NOW, category_filter="politics")
    assert VENUE_SETTLED_KEY not in _sql(id_filters)
