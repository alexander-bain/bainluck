"""#1703 — the bug-report GitHub-issue enqueue must not block the request, and
must not fail silently.

Scope of this file: the helper's contract (exact task name and args, loud but
HONEST failure) and the handler's contract (it *schedules* the enqueue, it never
runs it inline). Those are answerable without an HTTP stack.

The claim these tests deliberately CANNOT settle is the user-visible one — that
the response reaches the reader while a blocked publisher is still blocked. A
stubbed broker that returns instantly proves nothing about a broker that hangs,
and a direct call to the handler has no ASGI `send` to observe. That claim is
measured in
``tests/integration/test_feedback_enqueue_asgi_1703.py`` and only there.

No test in this file touches a real broker: ``app.tasks`` is replaced in
``sys.modules`` with a stub module, which also keeps the heavy real import out.
"""

import logging
import sys
import types
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi import BackgroundTasks

from app.routes.feedback import (
    BugReportSubmission,
    _enqueue_bug_report_github_issue,
    submit_bug_report,
)

TASK_NAME = "app.tasks.create_github_issue_for_bug_report"


class _StubCeleryApp:
    def __init__(self, send_task_impl):
        self.send_task_mock = Mock(side_effect=send_task_impl)

    def send_task(self, *args, **kwargs):
        return self.send_task_mock(*args, **kwargs)


def _install_stub_celery(send_task_impl, monkeypatch):
    """Put a stub ``app.tasks`` in ``sys.modules`` for the test's duration."""
    stub_app = _StubCeleryApp(send_task_impl)
    stub_tasks = types.ModuleType("app.tasks")
    stub_tasks.celery_app = stub_app
    monkeypatch.setitem(sys.modules, "app.tasks", stub_tasks)
    return stub_app


def _dead_broker(*args, **kwargs):
    raise ConnectionError("Error 61 connecting to localhost:6379. Connection refused.")


def _report_db():
    """Fake session whose ``refresh`` assigns the id a real commit would."""

    async def _commit():
        return None

    async def _refresh(report):
        report.id = 456

    return SimpleNamespace(add=lambda _x: None, commit=_commit, refresh=_refresh)


def test_enqueue_helper_publishes_exact_task_name_and_args(monkeypatch):
    stub = _install_stub_celery(lambda *a, **k: Mock(), monkeypatch)

    _enqueue_bug_report_github_issue(456)

    stub.send_task_mock.assert_called_once_with(TASK_NAME, args=[456])


def test_enqueue_helper_logs_a_warning_naming_the_report_on_broker_failure(
    monkeypatch, caplog
):
    """A dropped enqueue is attributable: the warning carries the report id."""
    _install_stub_celery(_dead_broker, monkeypatch)

    with caplog.at_level(logging.WARNING, logger="app.routes.feedback"):
        _enqueue_bug_report_github_issue(456)  # must not raise

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "456" in warnings[0].getMessage()


def test_enqueue_failure_log_does_not_overclaim_that_no_issue_was_created(
    monkeypatch, caplog
):
    """A raised publish is AMBIGUOUS, so the log may not assert an outcome.

    kombu can raise after the message reached the broker. "no GitHub issue will
    be created" would be a claim this frame cannot support; "not confirmed" is
    what it actually knows. Guarding the wording because the honest sentence is
    the whole point of the change — a loud log that lies is not an improvement
    on a silent one.
    """
    _install_stub_celery(_dead_broker, monkeypatch)

    with caplog.at_level(logging.WARNING, logger="app.routes.feedback"):
        _enqueue_bug_report_github_issue(456)

    message = caplog.records[0].getMessage().lower()
    assert "not confirmed" in message
    assert "no github issue will be created" not in message


async def test_handler_schedules_the_enqueue_and_never_runs_it_inline(
    monkeypatch, caplog
):
    """The request path does not touch the broker at all."""
    inline_calls = []

    def _must_not_run_inline(*args, **kwargs):
        inline_calls.append((args, kwargs))
        raise AssertionError("the enqueue ran inline, in the request path")

    _install_stub_celery(_must_not_run_inline, monkeypatch)
    background = BackgroundTasks()

    with caplog.at_level(logging.WARNING, logger="app.routes.feedback"):
        response = await submit_bug_report(
            request=SimpleNamespace(headers={}),
            body=BugReportSubmission(description="Something broke"),
            db=_report_db(),
            user=None,
            background_tasks=background,
        )

    assert response["status"] == "ok"
    assert inline_calls == []
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
    # Exactly one scheduled unit of work, and it is the real enqueue for THIS
    # report — not some other callable that happens to be scheduled.
    assert len(background.tasks) == 1
    assert background.tasks[0].func is _enqueue_bug_report_github_issue
    assert background.tasks[0].args == (456,)


async def test_the_scheduled_task_is_the_one_that_publishes(monkeypatch, caplog):
    """Running the scheduled task the way Starlette would does the publish.

    Without this, "it was scheduled" and "it ever happens" are two different
    claims and only the first is tested.
    """
    stub = _install_stub_celery(lambda *a, **k: Mock(), monkeypatch)
    background = BackgroundTasks()

    await submit_bug_report(
        request=SimpleNamespace(headers={}),
        body=BugReportSubmission(description="Something broke"),
        db=_report_db(),
        user=None,
        background_tasks=background,
    )
    stub.send_task_mock.assert_not_called()

    await background()  # Starlette's own runner: sync funcs go to a threadpool

    stub.send_task_mock.assert_called_once_with(TASK_NAME, args=[456])


async def test_a_dead_broker_in_the_scheduled_task_still_returns_ok(
    monkeypatch, caplog
):
    """gotcha #29: anonymous submission keeps working through a broker outage."""
    _install_stub_celery(_dead_broker, monkeypatch)
    background = BackgroundTasks()

    with caplog.at_level(logging.WARNING, logger="app.routes.feedback"):
        response = await submit_bug_report(
            request=SimpleNamespace(headers={}),
            body=BugReportSubmission(description="Something broke"),
            db=_report_db(),
            user=None,
            background_tasks=background,
        )
        await background()  # must not raise out of the background runner

    assert response == {"status": "ok", "id": 456, "category": "other"}
    assert any(
        r.levelno == logging.WARNING and "456" in r.getMessage() for r in caplog.records
    )
