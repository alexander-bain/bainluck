"""Contract tests for prediction stats endpoints."""

from datetime import datetime, timezone
from types import SimpleNamespace

from app.dependencies.auth import get_optional_user
from app.routes.predictions import _identity_filter


class _Result:
    def __init__(self, one=None, all_rows=None):
        self._one = one
        self._all_rows = all_rows or []

    def one(self):
        return self._one

    def all(self):
        return self._all_rows


class _Session:
    def __init__(self):
        self.statements = []
        self._results = [
            _Result(one=SimpleNamespace(total=2, correct=1)),
            _Result(all_rows=[SimpleNamespace(cat="sports", total=2, correct=1)]),
            _Result(all_rows=[]),
            _Result(all_rows=[SimpleNamespace(correct=True), SimpleNamespace(correct=False)]),
            _Result(all_rows=[]),
        ]

    async def execute(self, statement):
        self.statements.append(str(statement))
        return self._results.pop(0)


class _QueuedSession:
    def __init__(self, results):
        self.statements = []
        self._results = list(results)

    async def execute(self, statement):
        self.statements.append(str(statement))
        return self._results.pop(0)


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


async def test_stats_response_shape_for_session_identity(client, monkeypatch):
    """Stats should expose stable aggregate fields for anonymous sessions."""
    from app.routes import predictions

    session = _QueuedSession([
        _Result(one=SimpleNamespace(total=3, correct=2)),
        _Result(all_rows=[
            SimpleNamespace(correct=True),
            SimpleNamespace(correct=False),
            SimpleNamespace(correct=True),
        ]),
    ])
    monkeypatch.setattr(predictions, "get_session", lambda: _SessionContext(session))

    resp = await client.get("/api/predictions/stats", headers={"x-session-id": "anon-123"})

    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {
        "total",
        "correct",
        "accuracy",
        "current_streak",
        "best_streak",
    }
    assert body == {
        "total": 3,
        "correct": 2,
        "accuracy": 0.667,
        "current_streak": 1,
        "best_streak": 1,
    }
    assert session.statements
    assert all("user_predictions.session_id" in statement for statement in session.statements)


async def test_detailed_stats_uses_authenticated_user_without_session_id(client, monkeypatch):
    """Signed-in native users should not need the anonymous session id to see stats."""
    from app.main import app
    from app.routes import predictions

    user = SimpleNamespace(id=42)
    session = _Session()

    async def _mock_get_optional_user():
        return user

    try:
        app.dependency_overrides[get_optional_user] = _mock_get_optional_user
        monkeypatch.setattr(predictions, "get_session", lambda: _SessionContext(session))

        resp = await client.get("/api/predictions/detailed-stats")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert body["correct"] == 1
        assert body["by_category"]["sports"]["total"] == 2
        assert session.statements
        assert all("user_predictions.user_id" in statement for statement in session.statements)
        assert all("user_predictions.id <" not in statement for statement in session.statements)
    finally:
        app.dependency_overrides.pop(get_optional_user, None)


def test_prediction_identity_filter_keeps_current_session_for_signed_in_user():
    statement = str(_identity_filter(user_id=42, session_id="native-session"))

    assert "user_predictions.user_id" in statement
    assert "user_predictions.session_id" in statement
    assert " OR " in statement


async def test_detailed_stats_response_includes_dashboard_collections(client, monkeypatch):
    """Detailed stats contract includes breakdown, trend, badge, and recent lists."""
    from app.routes import predictions

    session = _Session()
    monkeypatch.setattr(predictions, "get_session", lambda: _SessionContext(session))

    resp = await client.get("/api/predictions/detailed-stats", headers={"x-session-id": "anon-456"})

    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {
        "total",
        "correct",
        "accuracy",
        "current_streak",
        "best_streak",
        "by_category",
        "trend",
        "badges",
        "recent",
    }
    assert body["by_category"] == {
        "sports": {"total": 2, "correct": 1, "accuracy": 0.5}
    }
    assert isinstance(body["trend"], list)
    assert isinstance(body["badges"], list)
    assert isinstance(body["recent"], list)


async def test_resolutions_response_shape(client, monkeypatch):
    """Resolved predictions should serialize the recent prediction card shape."""
    from app.routes import predictions

    created_at = datetime(2026, 5, 17, 12, 30, tzinfo=timezone.utc)
    pred = SimpleNamespace(
        market_id=99,
        guess="higher",
        threshold=55,
        actual_probability=0.62,
        correct=True,
        created_at=created_at,
    )
    session = _QueuedSession([
        _Result(all_rows=[(pred, "Fed cuts rates in June?", "economics")]),
    ])
    monkeypatch.setattr(predictions, "get_session", lambda: _SessionContext(session))

    resp = await client.get("/api/predictions/resolutions", headers={"x-session-id": "anon-789"})

    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"resolutions"}
    assert body["resolutions"] == [
        {
            "market_name": "Fed cuts rates in June?",
            "category": "economics",
            "guess": "higher",
            "threshold": 55,
            "actual": 62,
            "correct": True,
            "created_at": created_at.isoformat(),
        }
    ]


async def test_submit_prediction_requires_full_payload(client):
    resp = await client.post("/api/predictions", json={"market_id": 1, "guess": "higher"})

    assert resp.status_code == 422
    errors = resp.json()["detail"]
    missing_fields = {tuple(error["loc"]) for error in errors if error["type"] == "missing"}
    assert ("body", "threshold") in missing_fields
    assert ("body", "actual_probability") in missing_fields
    assert ("body", "correct") in missing_fields


async def test_submit_prediction_rejects_invalid_field_types(client):
    resp = await client.post(
        "/api/predictions",
        json={
            "market_id": "not-an-int",
            "guess": "higher",
            "threshold": 50,
            "actual_probability": 0.58,
            "correct": True,
        },
    )

    assert resp.status_code == 422
    errors = resp.json()["detail"]
    assert any(tuple(error["loc"]) == ("body", "market_id") for error in errors)
