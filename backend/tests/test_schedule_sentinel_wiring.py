"""Wiring guards for the Schedule Sentinel (#1796, Queue 342).

A sentinel nobody can reach and nothing schedules is a detector that does not
detect. These assert the rails exist and cannot be quietly removed:

  * the Celery task and its daily beat entry (gotcha #12);
  * both admin endpoints, on a mounted router, with the admin-secret gate
    (gotcha #2);
  * the cockpit tile — including the two rules that make it honest: the badge is
    "N of M leagues have a truth source" and NOT_COVERED is not green.

No anchor here reads the wall clock (gotcha #44) — every payload is a literal.
"""

import importlib

ss = importlib.import_module("app.tasks.schedule_sentinel")


# ---------------------------------------------------------------------------
# Celery task + beat (gotcha #12)
# ---------------------------------------------------------------------------
class TestTaskAndBeat:
    def test_task_is_registered(self):
        from app.tasks import celery_app

        assert "app.tasks.schedule_sentinel" in celery_app.tasks

    def test_beat_entry_exists_and_is_daily(self):
        from app.tasks import celery_app

        entry = celery_app.conf.beat_schedule["schedule-sentinel-daily"]
        assert entry["task"] == "app.tasks.schedule_sentinel"
        assert entry["options"]["queue"] == "heavy"

    def test_beat_does_not_collide_with_a_sibling_sentinel(self):
        """The morning sentinels are deliberately staggered on 2 heavy slots
        (#233). A new one landing on an occupied minute re-creates the
        congestion #232 diagnosed."""
        from app.tasks import celery_app

        fires: dict[tuple, str] = {}
        for name, entry in celery_app.conf.beat_schedule.items():
            if (entry.get("options") or {}).get("queue") != "heavy":
                continue
            sched = entry.get("schedule")
            hour = getattr(sched, "hour", None)
            minute = getattr(sched, "minute", None)
            if hour is None or minute is None:
                continue
            key = (frozenset(hour), frozenset(minute))
            assert key not in fires, (
                f"{name} fires at the same time as {fires[key]} on the heavy queue")
            fires[key] = name

    def test_task_is_routed_to_the_heavy_queue(self):
        from app.tasks import celery_app

        route = celery_app.conf.task_routes.get("app.tasks.schedule_sentinel")
        assert route == {"queue": "heavy"}

    def test_time_limits_leave_room_for_the_inner_deadline(self):
        """#966: the soft limit must sit under the hard limit and above the run's
        480s inner deadline, or a slow run SIGKILLs untracked."""
        from app.tasks import celery_app

        task = celery_app.tasks["app.tasks.schedule_sentinel"]
        assert 480 < task.soft_time_limit < task.time_limit


# ---------------------------------------------------------------------------
# Admin endpoints (gotcha #2)
# ---------------------------------------------------------------------------
class TestAdminEndpoints:
    def _paths(self):
        from app.main import app

        return {r.path: r for r in app.routes if hasattr(r, "path")}

    def test_run_and_last_are_both_mounted(self):
        paths = self._paths()
        assert "/api/admin/schedule-sentinel/run" in paths
        assert "/api/admin/schedule-sentinel/last" in paths

    def test_run_is_a_post_and_last_is_a_get(self):
        paths = self._paths()
        assert "POST" in paths["/api/admin/schedule-sentinel/run"].methods
        assert "GET" in paths["/api/admin/schedule-sentinel/last"].methods

    def test_write_endpoint_checks_the_admin_secret(self):
        """gotcha #2: an admin WRITE endpoint without ``_check_admin_secret`` is
        an open door."""
        import inspect

        from app.routes import admin

        src = inspect.getsource(admin.trigger_schedule_sentinel)
        assert "_check_admin_secret" in src

    def test_read_endpoint_checks_the_admin_secret(self):
        import inspect

        from app.routes import admin

        src = inspect.getsource(admin.get_schedule_sentinel_last)
        assert "_check_admin_secret" in src

    def test_last_reads_the_same_key_the_sentinel_writes(self):
        import inspect

        from app.routes import admin

        src = inspect.getsource(admin.get_schedule_sentinel_last)
        assert "bainluck:schedule_sentinel:last" in src
        assert "sentinel:schedule" in src
        producer = inspect.getsource(ss._run_schedule_sentinel)
        assert "bainluck:schedule_sentinel:last" in producer
        assert "sentinel:schedule" in producer


# ---------------------------------------------------------------------------
# Cockpit tile
# ---------------------------------------------------------------------------
def _payload(per_league, **scorecard):
    sc = {"leagues_total": len(per_league), "coverage_label": "x of y",
          "per_league": per_league}
    sc.update(scorecard)
    return {"mode": "live", "generated_at": "2026-08-13T07:36:00+00:00",
            "scorecard": sc, "filed": []}


class TestCockpitTile:
    def _group(self, monkeypatch, payload):
        from app.routes import admin_cockpit as ac

        class _Read:
            degraded = False
            ok = True
            value = payload

        monkeypatch.setattr(ac, "_read_state", lambda key: _Read())
        return ac._schedule_sentinel_group()

    def test_tile_is_registered_in_the_cockpit_payload(self):
        import inspect

        from app.routes import admin_cockpit as ac

        src = inspect.getsource(ac.cockpit)
        assert '"schedule_sentinel": _schedule_sentinel_group()' in src

    def test_tile_is_in_the_degraded_completeness_list(self):
        """A tile absent from that list can go unreadable without the payload
        ever declaring itself partial."""
        import inspect

        from app.routes import admin_cockpit as ac

        assert '"schedule_sentinel"' in inspect.getsource(ac.cockpit)

    def test_green_when_every_covered_league_reconciles(self, monkeypatch):
        g = self._group(monkeypatch, _payload([
            {"league": "mlb", "verdict": "green", "covered": True,
             "real_defects": 0, "watch": 0, "days_unverified": []},
        ], coverage_label="1 of 1 leagues have a truth source",
            leagues_covered=1, leagues_not_covered=0))
        assert g["status"] == "green"

    def test_red_when_a_covered_league_has_real_defects(self, monkeypatch):
        g = self._group(monkeypatch, _payload([
            {"league": "mlb", "verdict": "red", "covered": True,
             "real_defects": 13, "watch": 0, "days_unverified": []},
        ]))
        assert g["status"] == "red"
        assert g["per_league"][0]["status"] == "red"

    def test_uncovered_league_is_not_green(self, monkeypatch):
        """The whole point of #1796, restated on the tile: silently scoring a
        league we cannot measure as green is the failure mode."""
        g = self._group(monkeypatch, _payload([
            {"league": "mlb", "verdict": "green", "covered": True,
             "real_defects": 0, "watch": 0, "days_unverified": []},
            {"league": "npb", "verdict": "not_covered", "covered": False,
             "real_defects": 0, "watch": 0, "days_unverified": []},
        ], coverage_label="1 of 2 leagues have a truth source",
            leagues_covered=1, leagues_not_covered=1))
        assert g["status"] == "amber"
        npb = next(r for r in g["per_league"] if r["league"] == "npb")
        assert npb["status"] == "grey"
        assert npb["status"] != "green"

    def test_tile_shows_the_n_of_m_label_not_a_percentage(self, monkeypatch):
        g = self._group(monkeypatch, _payload([
            {"league": "mlb", "verdict": "green", "covered": True,
             "real_defects": 0, "watch": 0, "days_unverified": []},
        ], coverage_label="10 of 16 leagues have a truth source"))
        assert g["coverage_label"] == "10 of 16 leagues have a truth source"
        assert "%" not in g["coverage_label"]

    def test_watch_does_not_escalate_the_tile(self, monkeypatch):
        """L2-157: a clean-but-watch surface stays GREEN with a count."""
        g = self._group(monkeypatch, _payload([
            {"league": "ncaab", "verdict": "green", "covered": True,
             "real_defects": 0, "watch": 42, "days_unverified": []},
        ], leagues_covered=1, leagues_not_covered=0))
        assert g["status"] == "green"
        assert g["watch_total"] == 42

    def test_unverified_day_makes_the_tile_amber(self, monkeypatch):
        g = self._group(monkeypatch, _payload([
            {"league": "mlb", "verdict": "green_unverified", "covered": True,
             "real_defects": 0, "watch": 0,
             "days_unverified": ["2026-08-12: statsapi fetch failed"]},
        ], leagues_covered=1, leagues_not_covered=0))
        assert g["status"] == "amber"

    def test_unreadable_verdict_is_explicit_not_green(self, monkeypatch):
        """C102: a tile must never borrow GREEN from a dependency outage."""
        from app.routes import admin_cockpit as ac
        from app.utils import health_reads

        degraded = health_reads.RedisRead(
            key="bainluck:schedule_sentinel:last",
            status="unavailable",
            value=None,
            error="redis down",
        )
        monkeypatch.setattr(ac, "_read_state", lambda key: degraded)
        g = ac._schedule_sentinel_group()
        assert g is not None
        assert g.get("status") != "green"
        assert g.get("unreadable") is True

    def test_no_run_cached_returns_none(self, monkeypatch):
        from app.routes import admin_cockpit as ac

        class _Read:
            degraded = False
            ok = True
            value = None

        monkeypatch.setattr(ac, "_read_state", lambda key: _Read())
        assert ac._schedule_sentinel_group() is None
