"""#1501 — the Sentry noise filter, and the two bugs that made the old one inert.

The old filter lived inline in app/main.py and dropped almost nothing:
  1. Celery workers never import app.main, so it ran only in the web dyno.
  2. Its redis test asked for "redis" in the message, but redis-py names the
     EC2 host instead, so the largest single burner passed straight through.

These tests pin BOTH the drop policy and the wiring, because a filter that is
merely present has already been shown to be worth nothing.
"""

import pytest

from app.utils.sentry_filter import before_send, should_drop


def _exc_info(exc):
    return (type(exc), exc, None)


class _FakeRedisConnectionError(ConnectionError):
    """Stands in for redis.exceptions.ConnectionError (module identity matters)."""


_FakeRedisConnectionError.__module__ = "redis.exceptions"


# --- the regression that mattered most --------------------------------------

def test_redis_connection_error_dropped_even_though_message_never_says_redis():
    """The 1,829-event burner: 31% of a monthly quota in one signature.

    redis-py's message names the Heroku EC2 endpoint, NOT the word "redis", so
    the old `"redis" in str(exc)` test never fired.
    """
    exc = _FakeRedisConnectionError(
        "Error 8 connecting to ec2-3-92-219-100.compute-1.amazonaws.com:6379. "
        "nodename nor servname provided, or not known."
    )
    assert "redis" not in str(exc).lower(), "fixture must reproduce the real message"
    assert should_drop(_exc_info(exc), None) is True


def test_builtin_connection_error_to_heroku_redis_endpoint_dropped():
    """Some socket errors surface as the builtin class (module 'builtins')."""
    exc = ConnectionError(
        "Error 104 connecting to ec2-3-92-219-100.compute-1.amazonaws.com:6379."
    )
    assert should_drop(_exc_info(exc), None) is True


def test_worker_lost_error_dropped_despite_the_old_list_saying_WorkerLost():
    """billiard's class is WorkerLostError; the old tuple said "WorkerLost"."""
    exc = type("WorkerLostError", (Exception,), {})("worker died")
    assert should_drop(_exc_info(exc), None) is True


def test_soft_time_limit_exceeded_dropped():
    """614 events/cycle and absent from the old list entirely."""
    exc = type("SoftTimeLimitExceeded", (Exception,), {})()
    assert should_drop(_exc_info(exc), None) is True


def test_sigkill_log_record_dropped_though_it_carries_no_exception():
    """599 events. Arrives from billiard as a log record: exc_info is None, so a
    name-based filter structurally cannot see it."""
    msg = "Process 'ForkPoolWorker-5' pid:35 exited with 'signal 9 (SIGKILL)'"
    assert should_drop(None, msg) is True


# --- the other half: real signal must survive -------------------------------

def test_our_own_connection_error_is_kept():
    """A ConnectionError from our HTTP clients is signal, not transport churn."""
    exc = ConnectionError("Kalshi API unreachable: connect timeout")
    assert should_drop(_exc_info(exc), None) is False


def test_ordinary_application_errors_are_kept():
    for exc in (
        ValueError("bad probability 1.4"),
        KeyError("players"),
        RuntimeError("Event loop is closed"),
    ):
        assert should_drop(_exc_info(exc), None) is False, exc


def test_integrity_error_is_kept():
    """#1445's uq_game_moment_event_key class must never be filtered."""
    exc = type("IntegrityError", (Exception,), {})("duplicate key")
    assert should_drop(_exc_info(exc), None) is False


def test_watchdog_alert_text_is_not_filtered_here():
    """#1158's Sentry-only classes are cut by cooldown at the source, never by
    dropping them in before_send."""
    assert should_drop(None, "Market CREATION stalled: kalshi — no new markets in 7.3h") is False
    assert should_drop(None, "Suspected event-loop block: poll_kalshi phase 'upsert_loop@243s'") is False


# --- before_send contract ----------------------------------------------------

def test_before_send_returns_none_to_drop_and_event_to_keep():
    exc = _FakeRedisConnectionError("Error 8 connecting to ec2-x.compute-1.amazonaws.com:6379.")
    assert before_send({"message": None}, {"exc_info": _exc_info(exc)}) is None
    event = {"message": "something real"}
    assert before_send(event, {"exc_info": _exc_info(ValueError("x"))}) is event


def test_before_send_fails_open_on_internal_error():
    """A raising before_send is swallowed by the SDK and the event is sent
    anyway — so a bug here would silently restore the full burn rate. Assert the
    fail-open is explicit rather than accidental."""
    class Hostile(dict):
        def get(self, *a, **k):
            raise RuntimeError("boom")

    event = {"message": "keep me"}
    assert before_send(event, Hostile()) is event


def test_before_send_reads_logentry_message_shape():
    event = {"logentry": {"message": "Process 'ForkPoolWorker-2' exited with 'signal 9 (SIGKILL)'"}}
    assert before_send(event, {}) is None


# --- wiring: the actual #1501 root cause ------------------------------------

def test_both_processes_install_the_same_filter():
    """The whole bug was ONE process having the filter. Assert both inits
    reference the shared module, so this cannot silently regress."""
    import inspect

    import app.main as main_mod
    import app.tasks as tasks_mod

    main_src = inspect.getsource(main_mod)[:4000]
    tasks_src = inspect.getsource(tasks_mod)[:60000]

    assert "from app.utils.sentry_filter import before_send" in main_src
    assert "from app.utils.sentry_filter import before_send" in tasks_src
    # and both must actually pass it to init, not merely import it
    assert "before_send=_before_send" in main_src
    assert "before_send=_sentry_before_send" in tasks_src


def test_worker_init_has_no_inline_filter_left():
    """Guard against someone re-adding a second, divergent policy."""
    import inspect

    import app.tasks as tasks_mod

    src = inspect.getsource(tasks_mod)
    assert "def _before_send" not in src, "worker must use the shared filter only"
