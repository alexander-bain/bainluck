"""#2006 — a backend that blocks vacuum must alarm, not sit behind a green probe.

## the incident this guards, and the one the first attempt rebuilt

#2005: one client backend held ``backend_xmin`` for ~40 hours. Vacuum could not
advance anywhere in the database, the default landing page served 500s, and
everything that was actually watched read survivable — Grid Sentinel green, link
rate 91.0%, ``/api/health`` ``{"status":"ok","db":true}``. It was found by
accident by a Phase-0 probe and fixed in one command once found.

A candidate for this issue (2026-09-20) published the numbers on the readiness
probe behind this classifier::

    if xmin_age is None or xact_age_s is None or dead_pct is None:
        return "unavailable"

which is #2005's failure mode rebuilt inside its own fix: the incident shape
(``xmin_age=81_643`` with no table stats — a reachable read, not an error, since
``Q_WORST_DEAD_PCT`` filters to tables over 1,000 tuples and returns no row when
none qualify) classified as "we could not tell", and the caller only degraded on
``page``. **An absent signal outranked a present and bad one.** The review
rejected it and named the repair: classify each signal independently, take the
worst KNOWN verdict, and reserve ``unavailable`` for all-three-absent.

So the arms below are, in order: the classifier's independence (including the
exact incident shape), and then the whole thing driven through **the real
scheduled caller** — ``app.tasks.run_freshness_watchdog``, the callable the beat
dispatches every 10 minutes — with only its transport stubbed. Nothing here
touches the readiness probe, and nothing here cancels a backend.

## why the caller and not the check

A check that classifies correctly and is wired to nothing is the dead-tuple
ratio of scope item 4: visible in ``pg_stat_user_tables`` for the whole of #2005
and read by nothing. The alarm is the ship, so the alarm is what is driven — the
beat's own entry point, through ``_tracked_run``, into the shared ``_alert`` rail
(Sentry fingerprinted on ``[vacuum_block, postgres]``) and the shared GitHub
filing rail, with the emission cooldown and the recovery clear both exercised.
"""

import json

import pytest

from app.tasks import watchdog


# ── the fake transport ────────────────────────────────────────────────────
#
# The module's `_FakeRedis` in `test_watchdog.py` has no `set(nx=, ex=)`, which
# is the whole cooldown primitive, so this file carries its own rather than
# widening a fixture two hundred lines away in another file.


class _FakeRedis:
    """Sync Redis stand-in with the four commands this rail uses.

    ``set(nx=True)`` is modelled honestly — it refuses when the key exists —
    because that refusal IS ``_alert_on_cooldown``'s entire test, and a fake
    that always accepted would make the suppression arm vacuous.
    """

    def __init__(self, initial=None):
        self.store = dict(initial or {})

    def get(self, key):
        value = self.store.get(key)
        return value.encode() if isinstance(value, str) else value

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.store:
            return False
        self.store[key] = value
        return True

    def setex(self, key, _ttl, value):
        self.store[key] = value

    def delete(self, key):
        self.store.pop(key, None)


#: The #2005 reading, from the issue body: 81,643 xids of held horizon, and a
#: transaction that had been open for the better part of two days.
INCIDENT_XMIN = 81_643
INCIDENT_XACT_S = 40 * 3600

#: The healthy reading, measured ten minutes after the backend was killed.
HEALTHY_XMIN = 372


def _signals(**overrides):
    """A full signal dict with every field absent, then the named ones set."""
    base = {
        "xmin_age": None,
        "xact_age_s": None,
        "xact_pid": None,
        "xact_backend_type": None,
        "xact_application_name": None,
        "worst_table": None,
        "worst_dead_pct": None,
    }
    base.update(overrides)
    return base


@pytest.fixture
def rig(monkeypatch):
    """Drive the REAL scheduled caller with every transport disposable.

    Stubbed: the three sibling checks (they have their own guards and their own
    databases), the Postgres read (its SQL is proven against a real server in
    ``tests/integration/test_vacuum_block_signals_2006_real_postgres.py``),
    Sentry, and the GitHub token — which is blanked rather than stubbed out, so
    ``_file_watchdog_issue`` itself runs and returns its own no-token verdict
    instead of being replaced by a lambda that proves only that a lambda was
    called.

    NOT stubbed: `_alert`, `_alert_on_cooldown`, `_clear_alert_cooldown`,
    `_file_watchdog_issue`, `_run_vacuum_block_watchdog`, the classifier, the
    summary write, and `run_freshness_watchdog` itself.
    """
    import app.tasks as tasks_module
    from app.tasks import bug_report_github

    redis = _FakeRedis()
    captured = []

    async def _no_creation():
        return {}

    monkeypatch.setattr(watchdog, "_run_creation_freshness_watchdog", _no_creation)
    monkeypatch.setattr(watchdog, "_run_phase_heartbeat_watchdog", lambda: {"stuck": []})
    monkeypatch.setattr(
        watchdog, "_run_bookmaker_curve_watchdog", lambda: {"key_present": True}
    )
    monkeypatch.setattr(watchdog, "_bounded_rc", lambda: redis)
    monkeypatch.setattr(
        watchdog.sentry_sdk,
        "capture_message",
        lambda msg, level=None: captured.append(msg),
    )
    monkeypatch.setattr(
        watchdog.sentry_sdk,
        "new_scope",
        lambda: __import__("contextlib").nullcontext(
            type("S", (), {"set_tag": lambda self, *a: None})()
        ),
    )
    # No token ⇒ the filing rail short-circuits before any network call and says
    # so in its return value. That return value is what the arms assert on.
    monkeypatch.setattr(bug_report_github, "GITHUB_TOKEN", "")

    class _Rig:
        redis = None
        sentry = None

        def run(self, **signal_overrides):
            signals = _signals(**signal_overrides)

            async def _read():
                return signals

            monkeypatch.setattr(watchdog, "_read_vacuum_signals", _read)
            summary = tasks_module.run_freshness_watchdog()
            return summary["vacuum_block"]

    rig = _Rig()
    rig.redis = redis
    rig.sentry = captured
    return rig


# ── the classifier ────────────────────────────────────────────────────────


class TestSignalsAreJudgedIndependently:
    """The named repair from the 2026-09-20 review, arm by arm."""

    def test_the_incident_shape_pages_with_no_table_stats_at_all(self):
        """THE regression. 81,643 xids held, table stats absent → `page`.

        The rejected candidate returned `unavailable` here, and its caller only
        degraded on `page`, so the shape that cost 40 hours published `ready`.
        """
        status, per_signal = watchdog.classify_vacuum_signals(
            INCIDENT_XMIN, None, None
        )
        assert status == "page"
        assert per_signal["xmin_age"] == "page"
        assert per_signal["worst_dead_pct"] == "unknown"

    def test_a_page_on_the_wall_clock_survives_an_absent_xid_reading(self):
        """The mirror image — the other signal carries it on its own."""
        status, per_signal = watchdog.classify_vacuum_signals(
            None, INCIDENT_XACT_S, None
        )
        assert status == "page"
        assert per_signal["xact_age_s"] == "page"

    def test_nothing_known_is_unavailable_and_is_never_ok(self):
        """All three absent is the only genuine "we could not tell"."""
        status, per_signal = watchdog.classify_vacuum_signals(None, None, None)
        assert status == "unavailable"
        assert set(per_signal.values()) == {"unknown"}

    def test_the_healthy_reading_is_ok(self):
        """372 xids, a 12-second transaction, 3% dead — the control.

        Without this arm every arm above is satisfied by a classifier that
        answers `page` to everything.
        """
        status, per_signal = watchdog.classify_vacuum_signals(HEALTHY_XMIN, 12, 3.0)
        assert status == "ok"
        assert set(per_signal.values()) == {"ok"}

    def test_the_worst_known_signal_wins_not_the_last_one(self):
        """A page beside two `ok`s is a page, in either order."""
        assert watchdog.classify_vacuum_signals(HEALTHY_XMIN, 12, 90.0)[0] == "page"
        assert watchdog.classify_vacuum_signals(INCIDENT_XMIN, 12, 3.0)[0] == "page"
        assert watchdog.classify_vacuum_signals(HEALTHY_XMIN, 2_000, 3.0)[0] == "warn"

    def test_a_present_warn_outranks_two_absent_signals(self):
        status, _ = watchdog.classify_vacuum_signals(None, 2_000, None)
        assert status == "warn"

    def test_the_wall_clock_warn_clears_the_longest_legitimate_holder(self):
        """The issue proposes 15 min; the calibration beats cancel at 17–22 min.

        A warn under the longest DESIGNED transaction fires on healthy behaviour
        several times a day, which is how an alarm gets ignored. This asserts the
        departure rather than leaving it to the comment above it.
        """
        assert watchdog.VACUUM_XACT_WARN_S > 22 * 60
        assert watchdog.VACUUM_XACT_WARN_S < watchdog.VACUUM_XACT_PAGE_S


# ── the alarm, through the caller the beat actually dispatches ────────────


class TestTheScheduledCallerAlarms:
    def test_the_incident_shape_alarms_and_files_one_board_issue(self, rig):
        """Page-level xmin, no table stats: the shape the review named."""
        result = rig.run(
            xmin_age=INCIDENT_XMIN,
            xact_age_s=INCIDENT_XACT_S,
            xact_pid=1685421,
            xact_application_name="",
            xact_backend_type="client backend",
        )

        assert result["status"] == "page"
        assert result["alerted"] is True
        assert len(rig.sentry) == 1
        assert "81643" in rig.sentry[0].replace(",", "")
        assert "1685421" in rig.sentry[0]
        # The filing rail was reached — and, with no token, said so rather than
        # calling out. The action name is the proof the real function ran.
        assert result["filed"]["action"] == "skipped_no_token"
        assert result["filed"]["fingerprint"] == "vacuum_block:postgres"
        # And the admin surfaces can read it.
        flag = json.loads(rig.redis.store[watchdog.VACUUM_BLOCK_FLAG_KEY])
        assert flag["status"] == "page"
        assert flag["xact_pid"] == 1685421

    def test_wholly_absent_stats_are_silent_and_are_not_ok(self, rig):
        """A monitor that cannot read must not alarm AND must not reassure."""
        result = rig.run()

        assert result["status"] == "unavailable"
        assert result["alerted"] is False
        assert rig.sentry == []
        assert watchdog.VACUUM_BLOCK_FLAG_KEY not in rig.redis.store

    def test_the_healthy_control_alarms_about_nothing(self, rig):
        result = rig.run(xmin_age=HEALTHY_XMIN, xact_age_s=12, worst_dead_pct=3.0)

        assert result["status"] == "ok"
        assert result["alerted"] is False
        assert rig.sentry == []
        assert watchdog.VACUUM_BLOCK_FLAG_KEY not in rig.redis.store

    def test_a_warn_alarms_but_does_not_file_an_issue(self, rig):
        """Proportionality: an auto-filed issue per warn is how a board stops
        being read. The Sentry event still goes."""
        result = rig.run(xmin_age=20_000, xact_age_s=12, worst_dead_pct=3.0)

        assert result["status"] == "warn"
        assert result["alerted"] is True
        assert len(rig.sentry) == 1
        assert "filed" not in result

    def test_a_persisting_stall_emits_once_per_cooldown_window(self, rig):
        """Suppression. #1501: this class was 24% of a whole Sentry billing
        cycle before the cooldown, at two events per reading."""
        first = rig.run(xmin_age=INCIDENT_XMIN, xact_age_s=INCIDENT_XACT_S)
        second = rig.run(xmin_age=INCIDENT_XMIN, xact_age_s=INCIDENT_XACT_S)

        assert first["alerted"] is True
        assert second["alerted"] is False
        assert second["status"] == "page", "suppressed is not resolved"
        assert len(rig.sentry) == 1
        # Suppressed reading still refreshes the flag the admin surfaces read.
        assert watchdog.VACUUM_BLOCK_FLAG_KEY in rig.redis.store

    def test_recovery_clears_the_flag_and_re_arms_the_alarm(self, rig):
        """The behaviour a flag-only monitor lacks.

        The cooldown is 6 h and the beat is 10 min, so a stall that clears and
        RECURS inside one window would be silent the second time — the alarm
        would be quietest exactly when a stall is flapping. The third run is the
        arm that matters: a test that stopped at "the flag was deleted" passes
        against a rail that stays mute for the next six hours.
        """
        rig.run(xmin_age=INCIDENT_XMIN, xact_age_s=INCIDENT_XACT_S)

        recovered = rig.run(xmin_age=HEALTHY_XMIN, xact_age_s=12, worst_dead_pct=3.0)
        assert recovered["status"] == "ok"
        assert watchdog.VACUUM_BLOCK_FLAG_KEY not in rig.redis.store

        recurrence = rig.run(xmin_age=INCIDENT_XMIN, xact_age_s=INCIDENT_XACT_S)
        assert recurrence["alerted"] is True, (
            "a second episode inside the cooldown window must alarm again"
        )
        assert len(rig.sentry) == 2

    def test_an_unreadable_reading_also_re_arms(self, rig):
        """`unavailable` clears the flag — it is not a state to leave latched —
        but it must not itself alarm, and it must not leave the next real page
        suppressed."""
        rig.run(xmin_age=INCIDENT_XMIN, xact_age_s=INCIDENT_XACT_S)
        rig.run()
        again = rig.run(xmin_age=INCIDENT_XMIN, xact_age_s=INCIDENT_XACT_S)

        assert again["alerted"] is True
        assert len(rig.sentry) == 2


class TestItRidesTheExistingSurfaces:
    def test_the_verdict_is_on_the_summary_the_admin_surfaces_read(self, rig):
        """`bainluck:watchdog:summary` is already read by the celery dashboard
        (`routes/admin_celery.py`) and the cockpit (`routes/admin_cockpit.py`),
        both admin-authenticated. That is the visibility this ship reuses — no
        new endpoint, and nothing on the unauthenticated readiness probe."""
        rig.run(xmin_age=HEALTHY_XMIN, xact_age_s=12, worst_dead_pct=3.0)

        summary = json.loads(rig.redis.store[watchdog.WATCHDOG_SUMMARY_KEY])
        assert summary["vacuum_block"]["status"] == "ok"
        assert "creation" in summary and "phase_heartbeat" in summary

    def test_the_readiness_probe_is_not_touched(self):
        """The rejected candidate put three sequential `pg_stat_*` reads on the
        unauthenticated probe. This ship does not, and the guard says so rather
        than relying on nobody adding it later."""
        from pathlib import Path

        health = Path(watchdog.__file__).resolve().parents[1] / "routes" / "health.py"
        text = health.read_text(encoding="utf-8")
        assert "pg_stat_activity" not in text
        assert "backend_xmin" not in text
        assert "db_vacuum_signals" not in text

    def test_a_raising_vacuum_check_does_not_take_the_older_checks_down(
        self, monkeypatch
    ):
        """This check is the newest of four and must never be why the other
        three stop running."""

        async def _creation():
            return {"sentinel": "creation ran"}

        async def _boom():
            raise RuntimeError("unexpected")

        monkeypatch.setattr(watchdog, "_run_creation_freshness_watchdog", _creation)
        monkeypatch.setattr(
            watchdog, "_run_phase_heartbeat_watchdog", lambda: {"stuck": []}
        )
        monkeypatch.setattr(
            watchdog, "_run_bookmaker_curve_watchdog", lambda: {"key_present": True}
        )
        monkeypatch.setattr(watchdog, "_read_vacuum_signals", _boom)
        monkeypatch.setattr(watchdog, "_bounded_rc", lambda: _FakeRedis())

        import app.tasks as tasks_module

        summary = tasks_module.run_freshness_watchdog()

        assert summary["creation"] == {"sentinel": "creation ran"}
        assert summary["vacuum_block"]["status"] == "unavailable"
        assert summary["vacuum_block"]["alerted"] is False

    def test_the_beat_dispatches_this_caller_often_enough_to_page_in_an_hour(self):
        """The acceptance criterion is "fires within ~1 h". The wall-clock page
        threshold is 1 h, so the beat's own cadence is the rest of the budget —
        read from the schedule rather than retyped, so it cannot drift."""
        from app.tasks import celery_app

        entry = celery_app.conf.beat_schedule["run-freshness-watchdog"]
        assert entry["task"] == "app.tasks.run_freshness_watchdog"
        minutes = sorted(getattr(entry["schedule"], "minute", ()) or ())
        gaps = [b - a for a, b in zip(minutes, minutes[1:])] or [60]
        assert max(gaps) <= 15, (
            "the beat must run often enough that a 1 h page is delivered inside "
            f"~1 h; largest gap is {max(gaps)} min"
        )
