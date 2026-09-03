"""Guards for the migration lock policy (#2724).

The defect class: a migration's ``ALTER TABLE`` queues for a lock it cannot get,
and because a pending ``ACCESS EXCLUSIVE`` blocks every later reader of that
table, the whole site's reads of ``futures_markets`` pile up behind it and are
released together minutes later. The reader sees a blank page.

Two things have to hold, and they are guarded separately because they fail
separately:

* the POLICY is correct in isolation (this module's unit tests), and
* the policy is actually ARMED on the path Heroku's release phase runs
  (:class:`TestEnvPyArmsTheLockTimeout`, which executes ``alembic/env.py``).

The second is the one that would otherwise rot: every unit test here would stay
green if someone deleted the two lines in ``env.py`` that use them.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest import mock

import pytest

from app.utils.migration_lock_budget import (
    DEFAULT_ATTEMPTS,
    DEFAULT_BACKOFF_MS,
    DEFAULT_LOCK_TIMEOUT_MS,
    LOCK_TIMEOUT_CEILING_MS,
    LOCK_TIMEOUT_FLOOR_MS,
    RELEASE_PHASE_BUDGET_S,
    MigrationLockSettings,
    lock_timeout_option,
    max_total_wait_s,
    resolve_settings,
    run_with_lock_retry,
    should_retry,
)

ENV_PY = Path(__file__).resolve().parents[1] / "alembic" / "env.py"


class _LockTimeout(Exception):
    """Stands in for psycopg2's error: classification is by ``pgcode`` (55P03)."""

    pgcode = "55P03"


class _RealMigrationBug(Exception):
    pgcode = "42P07"  # duplicate_table — a bug, not contention


def _settings(**kwargs) -> MigrationLockSettings:
    base = {"lock_timeout_ms": 5_000, "attempts": 4, "backoff_ms": 0}
    base.update(kwargs)
    return MigrationLockSettings(**base)


class TestLockTimeoutOption:
    def test_it_is_the_libpq_connect_option_postgres_actually_parses(self):
        # `-c name=value` is what libpq accepts in `options`. Executing `SET`
        # instead would leave the migration's FIRST statement unprotected.
        assert lock_timeout_option(5_000) == "-c lock_timeout=5000"

    def test_the_value_is_a_bare_integer_of_milliseconds(self):
        # lock_timeout's bare-integer form is milliseconds. A stray unit suffix
        # here is not a parse error to libpq, it is a different duration.
        assert lock_timeout_option(1_250) == "-c lock_timeout=1250"


class TestResolveSettings:
    def test_an_empty_environment_lands_on_the_documented_defaults(self):
        s = resolve_settings({})
        assert s.lock_timeout_ms == DEFAULT_LOCK_TIMEOUT_MS
        assert s.attempts == DEFAULT_ATTEMPTS
        assert s.backoff_ms == DEFAULT_BACKOFF_MS

    def test_the_environment_can_override_each_knob(self):
        s = resolve_settings(
            {
                "ALEMBIC_LOCK_TIMEOUT_MS": "9000",
                "ALEMBIC_LOCK_ATTEMPTS": "2",
                "ALEMBIC_LOCK_BACKOFF_MS": "500",
            }
        )
        assert (s.lock_timeout_ms, s.attempts, s.backoff_ms) == (9000, 2, 500)

    @pytest.mark.parametrize("raw", ["", "   ", "abc", "5s", "-1", "0", None])
    def test_an_unusable_value_falls_back_rather_than_failing_the_deploy(self, raw):
        # A typo in a config var must not be able to stop migrations landing.
        env = {} if raw is None else {"ALEMBIC_LOCK_TIMEOUT_MS": raw}
        assert resolve_settings(env).lock_timeout_ms == DEFAULT_LOCK_TIMEOUT_MS

    def test_a_wait_longer_than_the_clients_abort_is_clamped_away(self):
        # The frontend API client gives up at 20s. A lock_timeout above that
        # can blank the page no matter what the rest of this module does, so
        # the ceiling is not advisory.
        s = resolve_settings({"ALEMBIC_LOCK_TIMEOUT_MS": "600000"})
        assert s.lock_timeout_ms == LOCK_TIMEOUT_CEILING_MS
        assert s.lock_timeout_ms <= 20_000

    def test_a_wait_too_short_to_mean_contention_is_clamped_up(self):
        s = resolve_settings({"ALEMBIC_LOCK_TIMEOUT_MS": "5"})
        assert s.lock_timeout_ms == LOCK_TIMEOUT_FLOOR_MS

    def test_attempts_are_at_least_one_so_migrations_always_run(self):
        assert resolve_settings({"ALEMBIC_LOCK_ATTEMPTS": "-3"}).attempts == (
            DEFAULT_ATTEMPTS
        )


class TestTheBudgetFitsTheReleasePhase:
    def test_the_default_policy_worst_case_fits_with_room_to_spare(self):
        # gotcha #31: the release phase is not a place to spend minutes. This is
        # the guard that reds if a future default quietly grows past it.
        worst = max_total_wait_s(resolve_settings({}))
        assert worst < RELEASE_PHASE_BUDGET_S
        assert worst <= 30.0, f"default policy can cost {worst}s of the release"

    def test_the_worst_case_counts_every_attempt_and_every_backoff(self):
        # 3 attempts x 5s waiting + 2 x 2s sleeping.
        s = _settings(lock_timeout_ms=5_000, attempts=3, backoff_ms=2_000)
        assert max_total_wait_s(s) == pytest.approx(19.0)

    def test_even_the_maximum_configurable_policy_fits_the_release_phase(self):
        worst = max_total_wait_s(
            resolve_settings(
                {
                    "ALEMBIC_LOCK_TIMEOUT_MS": "999999",
                    "ALEMBIC_LOCK_ATTEMPTS": "999",
                    "ALEMBIC_LOCK_BACKOFF_MS": "999999",
                }
            )
        )
        assert worst < RELEASE_PHASE_BUDGET_S


class TestShouldRetry:
    def test_a_lock_timeout_that_committed_nothing_is_retried(self):
        assert should_retry(_LockTimeout(), 1, _settings(), "abc", "abc") is True

    def test_a_real_migration_bug_surfaces_on_the_first_attempt(self):
        # Retrying a genuine failure four times turns one legible error into
        # four, and delays the release by the whole backoff budget.
        assert should_retry(_RealMigrationBug(), 1, _settings(), "abc", "abc") is False

    def test_the_last_attempt_is_not_retried(self):
        assert should_retry(_LockTimeout(), 4, _settings(attempts=4), "a", "a") is False

    def test_a_batch_that_already_committed_part_of_itself_is_never_replayed(self):
        # add_market_tags / add_taxonomy_tags issue a bare COMMIT and
        # add_prov_play_enum_value uses autocommit_block(), so a batch CAN be
        # half-applied when a later migration times out. Replaying it is worse
        # than failing.
        assert should_retry(_LockTimeout(), 1, _settings(), "abc", "def") is False

    def test_a_database_with_no_version_row_yet_counts_as_uncommitted(self):
        assert should_retry(_LockTimeout(), 1, _settings(), None, None) is True

    def test_a_version_appearing_where_there_was_none_blocks_the_retry(self):
        assert should_retry(_LockTimeout(), 1, _settings(), None, "abc") is False


class TestRunWithLockRetry:
    def test_a_clean_run_is_executed_exactly_once(self):
        calls = []
        result = run_with_lock_retry(
            lambda: calls.append(1) or "done",
            _settings(),
            read_version=lambda: "abc",
            sleep=lambda _: None,
        )
        assert result == "done"
        assert len(calls) == 1

    def test_a_transient_lock_timeout_is_retried_and_then_succeeds(self):
        attempts = {"n": 0}

        def attempt_once():
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise _LockTimeout()
            return "landed"

        slept = []
        result = run_with_lock_retry(
            attempt_once,
            _settings(attempts=4, backoff_ms=2_000),
            read_version=lambda: "abc",
            sleep=slept.append,
        )
        assert result == "landed"
        assert attempts["n"] == 3
        assert slept == [2.0, 2.0]

    def test_a_real_migration_bug_is_raised_immediately_without_sleeping(self):
        attempts = {"n": 0}

        def attempt_once():
            attempts["n"] += 1
            raise _RealMigrationBug()

        slept = []
        with pytest.raises(_RealMigrationBug):
            run_with_lock_retry(
                attempt_once,
                _settings(attempts=4),
                read_version=lambda: "abc",
                sleep=slept.append,
            )
        assert attempts["n"] == 1, "a genuine failure must not be retried"
        assert slept == []

    def test_exhausting_the_attempts_raises_the_lock_timeout(self):
        def attempt_once():
            raise _LockTimeout()

        with pytest.raises(_LockTimeout):
            run_with_lock_retry(
                attempt_once,
                _settings(attempts=3),
                read_version=lambda: "abc",
                sleep=lambda _: None,
            )

    def test_a_moving_version_stops_the_retry_mid_flight(self):
        attempts = {"n": 0}
        versions = iter(["a", "a", "a", "b"])

        def attempt_once():
            attempts["n"] += 1
            raise _LockTimeout()

        with pytest.raises(_LockTimeout):
            run_with_lock_retry(
                attempt_once,
                _settings(attempts=5),
                read_version=lambda: next(versions),
                sleep=lambda _: None,
            )
        # attempt 1 (a -> a) retried; attempt 2 (a -> b) must not be.
        assert attempts["n"] == 2

    def test_the_version_is_read_again_after_the_failure_not_reused(self):
        # The migration's own connection is in an aborted transaction after a
        # lock timeout, so the post-failure read must be its own call. If the
        # runner reused the pre-attempt value, the two would always compare
        # equal and the half-applied guard above would be vacuous.
        reads = []

        def read_version():
            reads.append(1)
            return "abc"

        with pytest.raises(_LockTimeout):
            run_with_lock_retry(
                lambda: (_ for _ in ()).throw(_LockTimeout()),
                _settings(attempts=1),
                read_version=read_version,
                sleep=lambda _: None,
            )
        assert len(reads) == 2, "one read before the attempt, one after it failed"


class TestEnvPyArmsTheLockTimeout:
    """Execute ``alembic/env.py`` and assert what it hands to the driver.

    This is the guard that cannot be satisfied by the unit tests above. It runs
    the module exactly as the release phase does — the file calls
    ``run_migrations_online()`` at import — with the engine and the alembic
    context faked, and inspects the ``connect_args`` that reached
    ``create_engine``.
    """

    def _run_env_py(self, monkeypatch, *, run_migrations=None):
        """Run ``env.py`` and report the connect_args of the MIGRATION connection.

        env.py opens more than one connection — the version probe gets its own —
        and both now carry libpq ``options``. Picking "the first one with
        options" would let the probe satisfy a guard about the migration, so the
        connection is identified by the only thing that actually matters: which
        one was handed to ``context.configure``, i.e. which one the migrations
        ran on. Every connection mock is traced back to the engine that made it.
        """
        import alembic
        import sqlalchemy

        captured = {"all_connect_args": [], "ran": 0}
        by_connection = {}

        def fake_create_engine(url, **kwargs):
            connect_args = kwargs.get("connect_args", {})
            captured["all_connect_args"].append(connect_args)
            engine = mock.MagicMock()
            connection = engine.connect.return_value.__enter__.return_value
            # The version probe reads `alembic_version`. It has to answer with a
            # real, stable value: two bare MagicMocks never compare equal, which
            # would make every retry look like a half-applied batch and the
            # half-applied guard vacuous.
            connection.execute.return_value.first.return_value = ("abc",)
            by_connection[id(connection)] = connect_args
            return engine

        def default_run_migrations():
            captured["ran"] += 1

        fake_context = mock.MagicMock()
        fake_context.is_offline_mode.return_value = False
        fake_context.config.config_file_name = None
        fake_context.run_migrations.side_effect = (
            run_migrations or default_run_migrations
        )

        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db.example.com:5432/x")
        monkeypatch.setattr(sqlalchemy, "create_engine", fake_create_engine)
        monkeypatch.setattr(alembic, "context", fake_context)

        spec = importlib.util.spec_from_file_location("_alembic_env_guard", ENV_PY)
        module = importlib.util.module_from_spec(spec)
        sys.modules["_alembic_env_guard"] = module
        try:
            spec.loader.exec_module(module)
        finally:
            sys.modules.pop("_alembic_env_guard", None)

        configured = [
            c.kwargs["connection"]
            for c in fake_context.configure.call_args_list
            if "connection" in c.kwargs
        ]
        assert configured, "env.py never configured a migration connection"
        captured["migration_connect_args"] = by_connection[id(configured[-1])]
        return captured

    def test_the_migration_connection_arms_lock_timeout(self, monkeypatch):
        captured = self._run_env_py(monkeypatch)
        assert captured["ran"] == 1, "the guard did not actually run the migrations"

        args = captured["migration_connect_args"]
        assert "options" in args, (
            "the connection the migrations ran on carried no libpq `options`; "
            "nothing bounds how long an ALTER TABLE will queue behind a "
            "straggler, and #2724 is reachable again"
        )
        assert args["options"] == lock_timeout_option(DEFAULT_LOCK_TIMEOUT_MS)

    def test_the_configured_timeout_reaches_the_driver(self, monkeypatch):
        # Proves the value is read from the environment at run time rather than
        # hard-coded next to a constant that only the unit tests can see.
        monkeypatch.setenv("ALEMBIC_LOCK_TIMEOUT_MS", "7000")
        captured = self._run_env_py(monkeypatch)
        assert captured["migration_connect_args"]["options"] == "-c lock_timeout=7000"

    def test_ssl_is_still_required_for_a_remote_database(self, monkeypatch):
        # Arming lock_timeout must not displace the existing connect_args.
        captured = self._run_env_py(monkeypatch)
        assert captured["migration_connect_args"].get("sslmode") == "require"

    def test_the_version_probe_is_itself_bounded(self, monkeypatch):
        # The probe runs during exactly the contention it reports on. If it were
        # unbounded it could hang for the minutes this change exists to prevent.
        captured = self._run_env_py(monkeypatch)
        probes = [
            a
            for a in captured["all_connect_args"]
            if a is not captured["migration_connect_args"]
        ]
        assert probes, "expected the version probe to open its own connection"
        for args in probes:
            assert "lock_timeout" in args.get("options", "")
            assert "statement_timeout" in args.get("options", "")

    def test_a_lock_timeout_during_migrations_is_retried(self, monkeypatch):
        state = {"n": 0}

        def flaky():
            state["n"] += 1
            if state["n"] == 1:
                raise _LockTimeout()

        monkeypatch.setenv("ALEMBIC_LOCK_BACKOFF_MS", "0")
        self._run_env_py(monkeypatch, run_migrations=flaky)
        assert state["n"] == 2, "env.py did not retry a transient lock timeout"
