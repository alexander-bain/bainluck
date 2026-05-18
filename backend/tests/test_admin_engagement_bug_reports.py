from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.routes import admin_engagement


class _Result:
    def __init__(self, row=None, rowcount=None):
        self._row = row
        self.rowcount = rowcount

    def first(self):
        return self._row


class _Session:
    def __init__(self, *results):
        self.results = list(results)
        self.executed = []
        self.commit_count = 0

    async def execute(self, statement):
        self.executed.append(statement)
        return self.results.pop(0)

    async def commit(self):
        self.commit_count += 1


@pytest.fixture(autouse=True)
def allow_admin_auth(monkeypatch):
    async def check_admin_auth(secret, request, db):
        return True

    monkeypatch.setattr(admin_engagement, "_check_admin_auth", check_admin_auth)


@pytest.fixture
def sent_tasks(monkeypatch):
    calls = []

    def send_task(name, args=None, kwargs=None):
        calls.append({"name": name, "args": args, "kwargs": kwargs})
        return SimpleNamespace(id="task-123")

    from app.tasks import celery_app

    monkeypatch.setattr(celery_app, "send_task", send_task)
    return calls


async def _update_report(db, report_id=123, **overrides):
    params = {
        "report_id": report_id,
        "request": SimpleNamespace(),
        "secret": None,
        "status": None,
        "category": None,
        "admin_notes": None,
        "resolution_summary": None,
        "backlog_ref": None,
        "user_email": None,
        "db": db,
    }
    params.update(overrides)
    return await admin_engagement.update_bug_report(**params)


@pytest.mark.asyncio
async def test_update_bug_report_enqueues_fixed_email_on_fixed_transition(sent_tasks):
    db = _Session(
        _Result(
            SimpleNamespace(
                status="in_progress",
                resolution_summary=None,
                notification_sent_at=None,
            )
        ),
        _Result(rowcount=1),
    )

    response = await _update_report(
        db,
        report_id=123,
        status="fixed",
        resolution_summary="Fixed the blank Discover card.",
    )

    assert response == {"status": "ok"}
    assert db.commit_count == 1
    assert sent_tasks == [
        {
            "name": "app.tasks.send_bug_fixed_email",
            "args": [123],
            "kwargs": None,
        }
    ]


@pytest.mark.asyncio
async def test_update_bug_report_enqueues_actioned_email_with_existing_summary(sent_tasks):
    db = _Session(
        _Result(
            SimpleNamespace(
                status="reviewed",
                resolution_summary="Shipped the missing fallback image.",
                notification_sent_at=None,
            )
        ),
        _Result(rowcount=1),
    )

    await _update_report(
        db,
        report_id=456,
        status="actioned",
    )

    assert sent_tasks == [
        {
            "name": "app.tasks.send_bug_fixed_email",
            "args": [456],
            "kwargs": None,
        }
    ]


@pytest.mark.asyncio
async def test_update_bug_report_does_not_enqueue_without_non_empty_summary(sent_tasks):
    db = _Session(
        _Result(
            SimpleNamespace(
                status="in_progress",
                resolution_summary="Previously useful summary",
                notification_sent_at=None,
            )
        ),
        _Result(rowcount=1),
    )

    await _update_report(
        db,
        report_id=789,
        status="fixed",
        resolution_summary="   ",
    )

    assert sent_tasks == []


@pytest.mark.asyncio
async def test_update_bug_report_does_not_double_enqueue_for_already_fixed(sent_tasks):
    db = _Session(
        _Result(
            SimpleNamespace(
                status="fixed",
                resolution_summary="Fixed already.",
                notification_sent_at=None,
            )
        ),
        _Result(rowcount=1),
    )

    await _update_report(
        db,
        report_id=321,
        status="actioned",
        resolution_summary="Marked actioned after the fix.",
    )

    assert sent_tasks == []


@pytest.mark.asyncio
async def test_update_bug_report_does_not_enqueue_when_already_notified(sent_tasks):
    db = _Session(
        _Result(
            SimpleNamespace(
                status="in_progress",
                resolution_summary=None,
                notification_sent_at=datetime.now(timezone.utc),
            )
        ),
        _Result(rowcount=1),
    )

    await _update_report(
        db,
        report_id=654,
        status="fixed",
        resolution_summary="Fixed the issue.",
    )

    assert sent_tasks == []
