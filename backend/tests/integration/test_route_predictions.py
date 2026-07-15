"""Contract tests for prediction stats endpoints."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.dependencies.auth import get_optional_user
from app.routes.predictions import _identity_filter


class _Result:
    def __init__(self, one=None, all_rows=None, scalar_value=None):
        self._one = one
        self._all_rows = all_rows or []
        self._scalar_value = scalar_value

    def one(self):
        return self._one

    def all(self):
        return self._all_rows

    def scalar(self):
        return self._scalar_value


async def test_stats_response_shape_for_session_identity(client, mock_db):
    """Stats should expose stable aggregate fields for anonymous sessions."""
    mock_db.execute = AsyncMock(side_effect=[
        _Result(one=SimpleNamespace(total=3, correct=2)),
        _Result(all_rows=[
            SimpleNamespace(correct=True),
            SimpleNamespace(correct=False),
            SimpleNamespace(correct=True),
        ]),
    ])

    resp = await client.get("/api/predictions/stats", headers={"x-session-id": "anon-123"})

    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"total", "correct", "accuracy", "current_streak", "best_streak"}
    assert body == {
        "total": 3,
        "correct": 2,
        "accuracy": 0.667,
        "current_streak": 1,
        "best_streak": 1,
    }


async def test_detailed_stats_uses_authenticated_user_without_session_id(client, mock_db):
    """Signed-in native users should not need the anonymous session id to see stats."""
    from app.main import app

    user = SimpleNamespace(id=42)

    mock_db.execute = AsyncMock(side_effect=[
        _Result(one=SimpleNamespace(total=2, correct=1)),
        _Result(all_rows=[SimpleNamespace(cat="sports", total=2, correct=1)]),
        _Result(all_rows=[]),
        _Result(all_rows=[SimpleNamespace(correct=True), SimpleNamespace(correct=False)]),
        _Result(all_rows=[]),
    ])

    async def _mock_get_optional_user():
        return user

    try:
        app.dependency_overrides[get_optional_user] = _mock_get_optional_user

        resp = await client.get("/api/predictions/detailed-stats")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert body["correct"] == 1
        assert body["by_category"]["sports"]["total"] == 2
    finally:
        app.dependency_overrides.pop(get_optional_user, None)


def test_prediction_identity_filter_keeps_current_session_for_signed_in_user():
    statement = str(_identity_filter(user_id=42, session_id="native-session"))

    assert "user_predictions.user_id" in statement
    assert "user_predictions.session_id" in statement
    assert " OR " in statement


async def test_detailed_stats_response_includes_dashboard_collections(client, mock_db):
    """Detailed stats contract includes breakdown, trend, badge, and recent lists."""
    mock_db.execute = AsyncMock(side_effect=[
        _Result(one=SimpleNamespace(total=2, correct=1)),
        _Result(all_rows=[SimpleNamespace(cat="sports", total=2, correct=1)]),
        _Result(all_rows=[]),
        _Result(all_rows=[SimpleNamespace(correct=True), SimpleNamespace(correct=False)]),
        _Result(all_rows=[]),
    ])

    resp = await client.get("/api/predictions/detailed-stats", headers={"x-session-id": "anon-456"})

    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {
        "total", "correct", "accuracy", "current_streak", "best_streak",
        "by_category", "trend", "badges", "recent",
    }
    assert body["by_category"] == {
        "sports": {"total": 2, "correct": 1, "accuracy": 0.5}
    }
    assert isinstance(body["trend"], list)
    assert isinstance(body["badges"], list)
    assert isinstance(body["recent"], list)


async def test_detailed_stats_empty_mocked_data_returns_zero_contract(client, mock_db):
    """Empty stats should still return the full dashboard contract."""
    mock_db.execute = AsyncMock(side_effect=[
        _Result(one=SimpleNamespace(total=0, correct=0)),
        _Result(all_rows=[]),
        _Result(all_rows=[]),
        _Result(all_rows=[]),
        _Result(all_rows=[]),
    ])

    resp = await client.get("/api/predictions/detailed-stats", headers={"x-session-id": "anon-empty"})

    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "total": 0, "correct": 0, "accuracy": 0,
        "current_streak": 0, "best_streak": 0,
        "by_category": {}, "trend": [], "badges": [], "recent": [],
    }


async def test_resolutions_response_shape(client, mock_db):
    """Resolved predictions should serialize the recent prediction card shape."""
    created_at = datetime(2026, 5, 17, 12, 30, tzinfo=timezone.utc)
    pred = SimpleNamespace(
        market_id=99, guess="higher", threshold=55,
        actual_probability=0.62, correct=True, created_at=created_at,
    )
    mock_db.execute = AsyncMock(return_value=_Result(
        all_rows=[(pred, "Fed cuts rates in June?", "economics")],
    ))

    resp = await client.get("/api/predictions/resolutions", headers={"x-session-id": "anon-789"})

    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"resolutions"}
    assert body["resolutions"] == [{
        # market_id lets the client link a settled result back to /futures/{id}
        # (Queue L2-119).
        "market_id": 99,
        "market_name": "Fed cuts rates in June?",
        "category": "economics",
        "guess": "higher",
        "threshold": 55,
        "actual": 62,
        "correct": True,
        "created_at": created_at.isoformat(),
    }]


async def test_resolutions_empty_mocked_data_returns_empty_list(client, mock_db):
    """No resolved predictions should serialize as an empty resolutions list."""
    mock_db.execute = AsyncMock(return_value=_Result(all_rows=[]))

    resp = await client.get("/api/predictions/resolutions", headers={"x-session-id": "anon-empty"})

    assert resp.status_code == 200
    assert resp.json() == {"resolutions": []}


async def test_submit_prediction_records_anonymous_session_prediction(client, mock_db):
    """Submit should persist the request payload when no server probability exists."""
    mock_db.execute = AsyncMock(return_value=_Result(scalar_value=None))
    mock_db.add = lambda x: setattr(mock_db, '_added', x)
    mock_db.commit = AsyncMock()

    resp = await client.post(
        "/api/predictions",
        headers={"x-session-id": "anon-submit"},
        json={
            "market_id": 123, "guess": "higher", "threshold": 50,
            "actual_probability": 0.58, "correct": True,
        },
    )

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    pred = mock_db._added
    assert pred.user_id is None
    assert pred.session_id == "anon-submit"
    assert pred.market_id == 123
    assert pred.guess == "higher"


async def test_submit_prediction_uses_server_probability_when_available(client, mock_db):
    """Server-side current probability is authoritative for correctness."""
    mock_db.execute = AsyncMock(return_value=_Result(scalar_value=0.62))
    mock_db.add = lambda x: setattr(mock_db, '_added', x)
    mock_db.commit = AsyncMock()

    resp = await client.post(
        "/api/predictions",
        headers={"x-session-id": "anon-submit"},
        json={
            "market_id": 456, "guess": "higher", "threshold": 55,
            "actual_probability": 0.10, "correct": False,
        },
    )

    assert resp.status_code == 200
    pred = mock_db._added
    assert pred.actual_probability == 0.62
    assert pred.correct is True


async def test_submit_prediction_requires_full_payload(client):
    resp = await client.post("/api/predictions", json={"market_id": 1, "guess": "higher"})
    assert resp.status_code == 422
