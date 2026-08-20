"""CAL-P081 (#2052, #2007) — a deploy is not a task failure, and the record must
say which deploy.

The specimen, read live from production on 2026-08-20T19:5xZ:

    last_verdict          "thrown"
    last_verdict_reason   "SystemExit"
    last_error            "-241"
    consecutive_failures  "2"
    last_failure_at       "2026-08-20T19:35:48.815957+00:00"

Nothing in ``app/`` raises ``SystemExit`` (grep, whole package), so it came from
the runtime — and ``_tracked_run`` catches ``BaseException``, so the process was
alive enough to write to Redis, which rules out SIGKILL/OOM (those land in
``hard_kills_24h``, a separate counter).

Naming it took a manual cross-reference against ``heroku releases``:

    failure 19:35:48Z   release v3877 at 19:35:24Z   +24 s
    failure 16:16:18Z   release v3873 at 16:16:02Z   +16 s

Two for two, and neither half of that correlation was in the record. Heroku
already exports ``HEROKU_RELEASE_VERSION`` and ``HEROKU_RELEASE_CREATED_AT`` into
the dyno environment, so the missing half is free — it just was never written
down at the moment it was true.

Two behaviours are pinned here and the second is the one that would hurt if it
regressed: an interrupted task is recorded as PARTIAL rather than a failure, and
the ``SystemExit`` is **re-raised regardless**, because a handler that swallows
one is a worker that will not shut down.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.task_verdict import describe_worker_shutdown


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class TestTheShutdownDescribesItself:
    def test_the_exact_production_exception_is_named_class_and_code(self):
        out = describe_worker_shutdown(SystemExit(-241))
        assert out["terminal"] == "interrupted"
        assert out["exception_class"] == "SystemExit"
        assert out["exit_code"] == -241
        assert out["reason"] == "SystemExit(-241)"

    def test_a_bare_str_of_the_exception_is_no_longer_the_only_record(self):
        """``str(SystemExit(-241))`` is ``'-241'`` and is ambiguous between at
        least ``KeyError(-241)``, ``Exception(-241)`` and an exit code. The class
        and the code are now separate fields, so no reader has to guess."""
        assert str(SystemExit(-241)) == "-241"
        out = describe_worker_shutdown(SystemExit(-241))
        assert out["exception_class"] != out["exit_code"]

    def test_a_celery_shutdown_subclass_keeps_its_own_name(self):
        from celery.exceptions import WorkerShutdown

        assert issubclass(WorkerShutdown, SystemExit)
        out = describe_worker_shutdown(WorkerShutdown(15))
        assert out["exception_class"] == "WorkerShutdown"

    def test_a_release_seconds_old_is_what_makes_it_attributable(self, monkeypatch):
        """The 19:35:48Z specimen, replayed against v3877 at 19:35:24Z."""
        failed_at = datetime(2026, 8, 20, 19, 35, 48, tzinfo=timezone.utc)
        monkeypatch.setenv("HEROKU_RELEASE_VERSION", "v3877")
        monkeypatch.setenv("HEROKU_RELEASE_CREATED_AT", "2026-08-20T19:35:24Z")
        monkeypatch.setenv("HEROKU_SLUG_COMMIT", "b86ffdd4c0ffee")
        monkeypatch.setenv("DYNO", "worker-heavy.1")

        out = describe_worker_shutdown(SystemExit(-241), now=failed_at.timestamp())
        assert out["release_version"] == "v3877"
        assert out["slug_commit"] == "b86ffdd4"
        assert out["dyno"] == "worker-heavy.1"
        assert out["release_age_s"] == 24

    def test_an_old_release_does_not_get_blamed_for_the_teardown(self, monkeypatch):
        """The direction that matters more. A dyno cycle, a quota kill and a
        deploy all raise the same exception; only the age separates them, and a
        summary that concluded "deploy" would make the other two invisible."""
        now = datetime(2026, 8, 20, 19, 35, 48, tzinfo=timezone.utc)
        monkeypatch.setenv("HEROKU_RELEASE_VERSION", "v3800")
        monkeypatch.setenv(
            "HEROKU_RELEASE_CREATED_AT", _iso(now - timedelta(hours=30))
        )
        out = describe_worker_shutdown(SystemExit(-241), now=now.timestamp())
        assert out["release_age_s"] == 108_000
        assert "deploy" not in out["reason"]

    def test_off_heroku_there_is_no_release_to_name_and_none_is_invented(
        self, monkeypatch
    ):
        for var in (
            "HEROKU_RELEASE_VERSION",
            "HEROKU_RELEASE_CREATED_AT",
            "HEROKU_SLUG_COMMIT",
            "DYNO",
        ):
            monkeypatch.delenv(var, raising=False)
        out = describe_worker_shutdown(SystemExit(1))
        assert out["release_version"] is None
        assert "release_age_s" not in out
        assert "release_age_reason" not in out

    def test_an_unparseable_release_stamp_is_declared_not_dropped(self, monkeypatch):
        """Ruling 075, second clause: "we could not read it" must not render the
        same as "there was nothing to read"."""
        monkeypatch.setenv("HEROKU_RELEASE_CREATED_AT", "yesterday-ish")
        out = describe_worker_shutdown(SystemExit(0))
        assert out["release_age_reason"] == "unparseable"
        assert "release_age_s" not in out


class TestTheTerminalIsInterruptedNotFailed:
    """The wiring in ``_tracked_run``, driven through the real wrapper."""

    @staticmethod
    def _wire(monkeypatch):
        calls: dict[str, list] = {"incomplete": [], "failure": [], "success": []}
        from app.tasks import redis_state

        monkeypatch.setattr(
            redis_state, "record_task_incomplete",
            lambda *a, **k: calls["incomplete"].append((a, k)),
        )
        monkeypatch.setattr(
            redis_state, "record_task_failure",
            lambda *a, **k: calls["failure"].append((a, k)),
        )
        monkeypatch.setattr(
            redis_state, "record_task_success",
            lambda *a, **k: calls["success"].append((a, k)),
        )
        monkeypatch.setattr(redis_state, "record_task_started", lambda *a, **k: None)
        monkeypatch.setattr(redis_state, "record_task_label", lambda *a, **k: None)
        monkeypatch.setattr(redis_state, "touch_worker_liveness", lambda *a, **k: None)
        return calls

    def test_a_systemexit_is_recorded_as_incomplete_and_never_as_a_failure(
        self, monkeypatch
    ):
        import app.tasks as tasks

        calls = self._wire(monkeypatch)

        async def _boom():
            raise SystemExit(-241)

        with pytest.raises(SystemExit):
            tasks._tracked_run("precompute_calibration_main", _boom())

        assert calls["failure"] == [], (
            "a deploy tearing down the worker must not advance "
            "consecutive_failures against a task that was working"
        )
        assert len(calls["incomplete"]) == 1
        _, kwargs = calls["incomplete"][0]
        assert kwargs["verdict_reason"] == "interrupted:SystemExit"
        assert kwargs["result_summary"]["terminal"] == "interrupted"
        assert kwargs["result_summary"]["exit_code"] == -241

    def test_the_systemexit_is_re_raised_so_the_worker_can_actually_exit(
        self, monkeypatch
    ):
        """The failure mode of getting this wrong is worse than the bug fixed:
        a swallowed ``SystemExit`` is a worker that ignores its shutdown."""
        import app.tasks as tasks

        self._wire(monkeypatch)

        async def _boom():
            raise SystemExit(-241)

        with pytest.raises(SystemExit) as caught:
            tasks._tracked_run("precompute_calibration_main", _boom())
        assert caught.value.code == -241

    def test_an_ordinary_exception_is_still_a_failure(self, monkeypatch):
        """The control. This change must not turn real errors green."""
        import app.tasks as tasks

        calls = self._wire(monkeypatch)

        async def _boom():
            raise RuntimeError("relation does not exist")

        with pytest.raises(RuntimeError):
            tasks._tracked_run("precompute_calibration_main", _boom())

        assert len(calls["failure"]) == 1
        assert calls["incomplete"] == []

    def test_keyboardinterrupt_is_left_alone(self, monkeypatch):
        """Scoped to ``SystemExit`` deliberately. ``KeyboardInterrupt`` is not a
        Heroku teardown and widening the branch on a hunch is how a class of
        real failures becomes invisible."""
        import app.tasks as tasks

        calls = self._wire(monkeypatch)

        async def _boom():
            raise KeyboardInterrupt()

        with pytest.raises(KeyboardInterrupt):
            tasks._tracked_run("precompute_calibration_main", _boom())
        assert len(calls["failure"]) == 1
