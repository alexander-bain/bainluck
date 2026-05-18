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


class _ScalarsResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


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


async def _list_reports(db, **overrides):
    params = {
        "request": SimpleNamespace(),
        "secret": None,
        "status": None,
        "limit": 50,
        "db": db,
    }
    params.update(overrides)
    return await admin_engagement.list_bug_reports(**params)


def test_suggest_bug_report_category_returns_decisive_deterministic_category():
    category = admin_engagement._suggest_bug_report_category(
        "The Celtics game probability is stale and the wrong score is showing.",
        {"page": "event_detail"},
    )

    assert category == "data_quality"


def test_suggest_bug_report_category_returns_none_for_unknown_metadata():
    category = admin_engagement._suggest_bug_report_category(
        "Something feels off.",
        {"page": "discover"},
    )

    assert category is None


@pytest.mark.asyncio
async def test_list_bug_reports_backfills_missing_decisive_category():
    report = SimpleNamespace(
        id=42,
        user_id=7,
        session_id="session-1",
        description="The chart text is cut off and overlaps the card.",
        screenshot_base64=None,
        app_state={"page": "discover"},
        status="new",
        category=None,
        admin_notes=None,
        backlog_ref=None,
        resolution_summary=None,
        user_email=None,
        notification_sent_at=None,
        created_at=datetime(2026, 5, 18, tzinfo=timezone.utc),
    )
    db = _Session(_ScalarsResult([report]), _Result(rowcount=1))

    response = await _list_reports(db)

    assert response["reports"][0]["category"] == "ui"
    assert report.category == "ui"
    assert db.commit_count == 1
    assert len(db.executed) == 2


@pytest.mark.asyncio
async def test_list_bug_reports_leaves_unknown_category_unset():
    report = SimpleNamespace(
        id=43,
        user_id=None,
        session_id="session-2",
        description="This felt weird.",
        screenshot_base64="abc123",
        app_state={"page": "discover"},
        status="new",
        category=None,
        admin_notes=None,
        backlog_ref=None,
        resolution_summary=None,
        user_email=None,
        notification_sent_at=None,
        created_at=None,
    )
    db = _Session(_ScalarsResult([report]))

    response = await _list_reports(db)

    assert response["reports"][0]["category"] is None
    assert report.category is None
    assert db.commit_count == 0
    assert len(db.executed) == 1


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
