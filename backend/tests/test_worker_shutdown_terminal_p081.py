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

LAT-P329 (#4950) — THE PARAGRAPH ABOVE IS WHERE THE BUG CAME FROM, AND IT IS
LEFT STANDING SO THE NEXT READER SEES THE STEP. Those ``+24s`` / ``+16s`` deltas
were computed OUTSIDE the dyno, against a ``heroku releases`` row. The env vars
were then assumed to reproduce that subtraction from INSIDE the dying worker.
They cannot: they are baked in at boot, so a worker being torn down names the
release it is RUNNING — during a deploy, by construction the one being REPLACED.
The old ``release_age_s`` therefore measured the OUTGOING release's window, and
the note beside it read a large value as "not a deploy", which is every ordinary
deploy kill. Two production specimens, a day apart, both +17s and both exonerated
by the old rule:

    2026-09-10  env v4410 (19:53:13Z) age 3350 -> 20:49:03Z; v4411 at 20:48:46Z
    2026-09-11  env v4426 (07:46:23Z) age 3682 -> 08:47:45Z; v4427 at 08:47:28Z

Three behaviours are pinned here, and the second is the one that would hurt most
if it regressed: an interrupted task is recorded as PARTIAL rather than a
failure; the ``SystemExit`` is **re-raised regardless**, because a handler that
swallows one is a worker that will not shut down; and no field or note draws a
conclusion about the cause from the running release's age alone.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.task_verdict import attribute_teardown, describe_worker_shutdown


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

    def test_the_running_release_is_named_and_its_window_measured(self, monkeypatch):
        """The 19:35:48Z specimen, replayed against v3877 at 19:35:24Z.

        LAT-P329 renamed the age field. What this reads is how long the release
        the worker was RUNNING had been live — not, as the original name and this
        test's original title both claimed, the age of whatever killed it.
        """
        failed_at = datetime(2026, 8, 20, 19, 35, 48, tzinfo=timezone.utc)
        monkeypatch.setenv("HEROKU_RELEASE_VERSION", "v3877")
        monkeypatch.setenv("HEROKU_RELEASE_CREATED_AT", "2026-08-20T19:35:24Z")
        monkeypatch.setenv("HEROKU_SLUG_COMMIT", "b86ffdd4c0ffee")
        monkeypatch.setenv("DYNO", "worker-heavy.1")

        out = describe_worker_shutdown(SystemExit(-241), now=failed_at.timestamp())
        assert out["release_version"] == "v3877"
        assert out["slug_commit"] == "b86ffdd4"
        assert out["dyno"] == "worker-heavy.1"
        assert out["running_release_age_s"] == 24
        assert "release_age_s" not in out, (
            "the old name is the trap #4950 is about — it reads as the killer's age"
        )

    def test_the_teardown_instant_is_written_down_not_left_to_arithmetic(
        self, monkeypatch
    ):
        """LAT-P329 (#4950). ``interrupted_at`` is the one fact only the dying
        process holds, and the whole attribution turns on it. Before it existed a
        reader had to add ``release_age_s`` to ``release_created_at`` by hand —
        which is exactly the step at which #4950's reader was routed wrong."""
        failed_at = datetime(2026, 9, 11, 8, 47, 45, tzinfo=timezone.utc)
        monkeypatch.setenv("HEROKU_RELEASE_VERSION", "v4426")
        monkeypatch.setenv("HEROKU_RELEASE_CREATED_AT", "2026-09-11T07:46:23Z")
        out = describe_worker_shutdown(SystemExit(-241), now=failed_at.timestamp())
        assert out["interrupted_at"] == "2026-09-11T08:47:45Z"
        assert out["running_release_age_s"] == 3682

    def test_the_note_no_longer_exonerates_a_deploy_for_being_old(self, monkeypatch):
        """The regression that would restore the bug. The old note said a large
        age "means it was not [this release], and the cause is elsewhere" — and
        the age is large in every ordinary deploy kill, because it measures the
        OUTGOING release's window. Any note that draws a conclusion from the age
        alone is the defect coming back."""
        now = datetime(2026, 9, 11, 8, 47, 45, tzinfo=timezone.utc)
        monkeypatch.setenv("HEROKU_RELEASE_VERSION", "v4426")
        monkeypatch.setenv("HEROKU_RELEASE_CREATED_AT", _iso(now - timedelta(hours=30)))
        note = describe_worker_shutdown(SystemExit(-241), now=now.timestamp())["note"]
        assert "interrupted_at" in note, "the note must point at the fact that decides it"
        assert "does NOT rule a deploy out" in note
        assert "means it was not" not in note

    def test_an_old_release_does_not_get_blamed_for_the_teardown(self, monkeypatch):
        """The direction that still matters. A dyno cycle, a quota kill and a
        deploy all raise the same exception, and the summary must not conclude
        "deploy" for any of them — it reports, and attribution happens later."""
        now = datetime(2026, 8, 20, 19, 35, 48, tzinfo=timezone.utc)
        monkeypatch.setenv("HEROKU_RELEASE_VERSION", "v3800")
        monkeypatch.setenv(
            "HEROKU_RELEASE_CREATED_AT", _iso(now - timedelta(hours=30))
        )
        out = describe_worker_shutdown(SystemExit(-241), now=now.timestamp())
        assert out["running_release_age_s"] == 108_000
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
        assert "running_release_age_s" not in out
        assert "running_release_age_reason" not in out

    def test_an_unparseable_release_stamp_is_declared_not_dropped(self, monkeypatch):
        """Ruling 075, second clause: "we could not read it" must not render the
        same as "there was nothing to read"."""
        monkeypatch.setenv("HEROKU_RELEASE_CREATED_AT", "yesterday-ish")
        out = describe_worker_shutdown(SystemExit(0))
        assert out["running_release_age_reason"] == "unparseable"
        assert "running_release_age_s" not in out


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


# =============================================================================
# LAT-P329 (#4950) — attribution, as a function instead of a sentence
# =============================================================================
#
# The old note told a reader to judge by ``release_age_s``. That number is the
# outgoing release's window length, so on every ordinary deploy kill it is large
# and the note said "not a deploy". Two production specimens, a day apart, are
# replayed below verbatim; both are +17s, and under the old rule both read as
# "the cause is elsewhere".


class TestAttributingATeardownToTheReleaseThatCausedIt:
    #: Module-level function, held as a ``staticmethod`` deliberately: a bare
    #: function in a class body binds as a method, and ``self._attr(summary, …)``
    #: would silently pass ``self`` as the summary.
    _attr = staticmethod(attribute_teardown)

    #: `heroku releases -a bainluck`, 2026-09-11 09:4xZ, verbatim.
    RELEASES = [
        {"version": "v4427", "created_at": "2026-09-11T08:47:28Z"},
        {"version": "v4426", "created_at": "2026-09-11T07:46:23Z"},
        {"version": "v4425", "created_at": "2026-09-11T06:56:46Z"},
        {"version": "v4424", "created_at": "2026-09-11T06:47:17Z"},
    ]

    def test_the_live_specimen_names_v4427_where_the_old_note_said_elsewhere(self):
        """Read from production `GET /api/admin/ops-snapshot` at 2026-09-11
        09:40Z: `poll_kalshi`, terminal `interrupted`, env release v4426, age
        3682s. 07:46:23Z + 3682s = 08:47:45Z, and v4427 was created 08:47:28Z."""
        summary = {
            "terminal": "interrupted",
            "release_version": "v4426",
            "release_created_at": "2026-09-11T07:46:23Z",
            "interrupted_at": "2026-09-11T08:47:45Z",
            "running_release_age_s": 3682,
        }
        out = self._attr(summary, self.RELEASES)
        assert out["killed_by_release"] == "v4427"
        assert out["lead_s"] == 17
        assert out["running_release"] == "v4426"

    def test_the_9_10_specimen_from_the_issue_body_lands_the_same_way(self):
        """#4950's own reading: env v4410 (19:53:13Z), age 3350 -> 20:49:03Z;
        v4411 created 20:48:46Z. A second specimen, a different day, +17s."""
        summary = {
            "release_version": "v4410",
            "release_created_at": "2026-09-10T19:53:13Z",
            "interrupted_at": "2026-09-10T20:49:03Z",
        }
        releases = [
            {"version": "v4411", "created_at": "2026-09-10T20:48:46Z"},
            {"version": "v4410", "created_at": "2026-09-10T19:53:13Z"},
        ]
        out = self._attr(summary, releases)
        assert out["killed_by_release"] == "v4411"
        assert out["lead_s"] == 17

    def test_a_summary_written_before_the_rename_is_still_attributable(self):
        """There are pre-LAT-P329 rows in Redis right now, spelled
        ``release_age_s`` and carrying no ``interrupted_at``. Reconstructing the
        instant from the stamp plus the age is the arithmetic #4950's reader did
        by hand, and dropping those rows would throw away the only specimens we
        have of the bug."""
        summary = {
            "release_version": "v4426",
            "release_created_at": "2026-09-11T07:46:23Z",
            "release_age_s": 3682,
        }
        out = self._attr(summary, self.RELEASES)
        assert out["killed_by_release"] == "v4427"
        assert out["interrupted_at"] == "2026-09-11T08:47:45Z"

    def test_a_release_never_kills_the_dyno_it_started(self):
        """The clause the environment can never satisfy on its own. A worker torn
        down 20s after booting on v4427 was killed by something else — v4427
        started it. Without this the function would blame the running release for
        every fast teardown and be confidently wrong."""
        summary = {
            "release_version": "v4427",
            "release_created_at": "2026-09-11T08:47:28Z",
            "interrupted_at": "2026-09-11T08:47:48Z",
        }
        out = self._attr(summary, self.RELEASES)
        assert out["killed_by_release"] is None
        assert out["basis"] == "no_newer_release_within_180s"

    def test_a_quiet_window_reports_the_cause_is_elsewhere(self):
        """The case the old note thought it was detecting, and the reason the
        function has to be able to say no: a dyno cycle or a memory quota kill
        must not be dressed up as a deploy."""
        summary = {
            "release_version": "v4425",
            "release_created_at": "2026-09-11T06:56:46Z",
            "interrupted_at": "2026-09-11T07:20:00Z",
        }
        out = self._attr(summary, self.RELEASES)
        assert out["killed_by_release"] is None
        assert "elsewhere" in out["detail"]

    def test_a_release_created_after_the_interrupt_is_not_the_cause(self):
        """Direction matters. v4427 at 08:47:28Z cannot have killed something
        that died at 08:00:00Z, and a window check on absolute distance would
        say it did."""
        summary = {
            "release_version": "v4426",
            "release_created_at": "2026-09-11T07:46:23Z",
            "interrupted_at": "2026-09-11T08:47:00Z",
        }
        out = self._attr(summary, [{"version": "v4427", "created_at": "2026-09-11T08:47:28Z"}])
        assert out["killed_by_release"] is None

    def test_the_nearest_qualifying_release_wins_when_two_land_together(self):
        """Deploys batch. When two land inside the window the one immediately
        before the interrupt is the killer, not the earlier one."""
        summary = {
            "release_version": "v4424",
            "release_created_at": "2026-09-11T06:47:17Z",
            "interrupted_at": "2026-09-11T06:58:00Z",
        }
        out = self._attr(
            summary,
            [
                {"version": "v4425", "created_at": "2026-09-11T06:56:46Z"},
                {"version": "v4426b", "created_at": "2026-09-11T06:57:50Z"},
            ],
        )
        assert out["killed_by_release"] == "v4426b"
        assert out["lead_s"] == 10

    def test_a_summary_with_no_usable_time_says_so_rather_than_guessing(self):
        out = self._attr({"release_version": "v4426"}, self.RELEASES)
        assert out["killed_by_release"] is None
        assert out["basis"] == "no_interrupt_time"

    def test_a_junk_release_row_is_skipped_not_fatal(self):
        """One unreadable row must not cost the attribution the other rows can
        still make — the answer is what an operator is here for."""
        summary = {
            "release_version": "v4426",
            "release_created_at": "2026-09-11T07:46:23Z",
            "interrupted_at": "2026-09-11T08:47:45Z",
        }
        out = self._attr(
            summary,
            [
                {"version": None, "created_at": "2026-09-11T08:47:40Z"},
                {"version": "v4427x", "created_at": "not-a-date"},
                None,
                {"version": "v4427", "created_at": "2026-09-11T08:47:28Z"},
            ],
        )
        assert out["killed_by_release"] == "v4427"

    def test_an_empty_release_list_is_not_an_attribution(self):
        summary = {"interrupted_at": "2026-09-11T08:47:45Z"}
        assert self._attr(summary, [])["killed_by_release"] is None

    def test_a_release_stamp_in_local_time_is_reported_as_its_utc_instant(self):
        """Found by running `tools/why-was-it-killed.sh` against production, not
        by reading the code: `heroku releases` prints `-0700` stamps, and the
        report rendered v4427 as `01:47:28Z` — the Pacific wall clock wearing a
        UTC suffix. The attribution was right (these are aware datetimes, and the
        lead is still 17s); the number a reader would copy out was not."""
        from datetime import datetime, timedelta, timezone as tz

        pacific = tz(timedelta(hours=-7))
        summary = {
            "release_version": "v4426",
            "release_created_at": "2026-09-11T07:46:23Z",
            "interrupted_at": "2026-09-11T08:47:45Z",
        }
        out = self._attr(
            summary,
            [{
                "version": "v4427",
                "created_at": datetime(2026, 9, 11, 1, 47, 28, tzinfo=pacific),
            }],
        )
        assert out["killed_by_release"] == "v4427"
        assert out["lead_s"] == 17
        assert out["killer_created_at"] == "2026-09-11T08:47:28Z", (
            "a -0700 stamp must be converted, not suffixed with Z"
        )
