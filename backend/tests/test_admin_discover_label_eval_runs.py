from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.routes import admin_engagement


class _ScalarsResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


class _Session:
    def __init__(self, *results):
        self.results = list(results)
        self.executed = []

    async def execute(self, statement):
        self.executed.append(statement)
        return self.results.pop(0)


@pytest.fixture(autouse=True)
def allow_admin_secret(monkeypatch):
    monkeypatch.setattr(admin_engagement, "_check_admin_secret", lambda secret: secret == "ok")


def _run(**overrides):
    values = {
        "run_id": "run-1",
        "eval_name": "discover_label_gold_set",
        "status": "ok",
        "surface": None,
        "reviewer": None,
        "top_k": 20,
        "row_count": 12,
        "captured_at": datetime(2026, 5, 23, 12, 0, tzinfo=timezone.utc),
        "dataset_window_start": datetime(2026, 5, 1, tzinfo=timezone.utc),
        "dataset_window_end": datetime(2026, 5, 23, tzinfo=timezone.utc),
        "tapworthy_at_k": 0.7,
        "boring_rate_at_k": 0.1,
        "duplicate_family_rate_at_k": 0.0,
        "unclear_rate_at_k": 0.2,
        "bad_explanation_rate_at_k": 0.3,
        "bad_image_rate_at_k": 0.0,
        "broad_appeal_at_k": 0.8,
        "fixable_interest_rate_at_k": 0.2,
        "tapworthy_recall_at_k": 0.6,
        "notable_regressions": [],
        "metric_summary": {"row_count": 12},
        "category_breakdowns": {"tech": {"row_count": 3}},
        "eval_metadata": {"days": 30},
        "error": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_list_discover_label_eval_runs_serializes_recent_runs():
    db = _Session(_ScalarsResult([_run()]))

    response = await admin_engagement.list_discover_label_eval_runs(
        secret="ok",
        limit=20,
        db=db,
    )

    assert response["runs"][0]["run_id"] == "run-1"
    assert response["runs"][0]["tapworthy_at_k"] == 0.7
    assert "metric_summary" not in response["runs"][0]


@pytest.mark.asyncio
async def test_get_discover_label_eval_run_returns_full_details():
    db = _Session(_ScalarsResult([_run()]))

    response = await admin_engagement.get_discover_label_eval_run(
        run_id="run-1",
        secret="ok",
        db=db,
    )

    assert response["run_id"] == "run-1"
    assert response["metric_summary"] == {"row_count": 12}
    assert response["category_breakdowns"] == {"tech": {"row_count": 3}}


@pytest.mark.asyncio
async def test_label_eval_trends_adds_run_over_run_deltas():
    db = _Session(
        _ScalarsResult(
            [
                _run(run_id="new", tapworthy_at_k=0.8, boring_rate_at_k=0.2),
                _run(run_id="old", tapworthy_at_k=0.7, boring_rate_at_k=0.1),
            ]
        )
    )

    response = await admin_engagement.list_discover_label_eval_trends(
        secret="ok",
        limit=12,
        db=db,
    )

    assert response["runs"][0]["run_id"] == "new"
    assert response["runs"][0]["deltas"]["tapworthy_at_k"] == 0.1
    assert response["runs"][0]["deltas"]["boring_rate_at_k"] == 0.1


@pytest.mark.asyncio
async def test_snapshot_endpoint_queues_celery_task(monkeypatch):
    calls = []

    def send_task(name, kwargs=None):
        calls.append({"name": name, "kwargs": kwargs})
        return SimpleNamespace(id="task-123")

    from app.tasks import celery_app

    monkeypatch.setattr(celery_app, "send_task", send_task)

    response = await admin_engagement.trigger_discover_label_eval_snapshot(
        secret="ok",
        days=14,
        top_k=10,
        limit=100,
        surface="discover",
        reviewer="alex",
    )

    assert response["queued"] is True
    assert response["task_id"] == "task-123"
    assert calls == [
        {
            "name": "app.tasks.snapshot_discover_label_eval_run",
            "kwargs": {
                "days": 14,
                "top_k": 10,
                "limit": 100,
                "surface": "discover",
                "reviewer": "alex",
            },
        }
    ]
