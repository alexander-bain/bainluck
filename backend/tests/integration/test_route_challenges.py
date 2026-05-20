"""Contract tests for Challenge endpoints: /api/challenges/*

Tests create challenge, get challenge, and accept challenge.
Uses the shared ``client`` / ``mock_db`` fixtures from conftest.py.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _MockResult:
    def __init__(self, first_value=None, scalar_value=None):
        self._first = first_value
        self._scalar = scalar_value

    def first(self):
        return self._first

    def scalar(self):
        return self._scalar


def _make_challenge(
    id: int = 1,
    challenge_code: str = "BL-abc123",
    market_id: int = 42,
    market_name: str = "Will the Fed cut rates?",
    creator_guess: str = "higher",
    creator_threshold: int = 55,
    friend_guess: str | None = None,
    creator_correct: bool | None = None,
    friend_correct: bool | None = None,
    actual_probability: float | None = None,
    resolved_at=None,
):
    ch = MagicMock()
    ch.id = id
    ch.challenge_code = challenge_code
    ch.market_id = market_id
    ch.market_name = market_name
    ch.creator_guess = creator_guess
    ch.creator_threshold = creator_threshold
    ch.friend_guess = friend_guess
    ch.creator_correct = creator_correct
    ch.friend_correct = friend_correct
    ch.actual_probability = actual_probability
    ch.resolved_at = resolved_at
    ch.created_at = datetime(2026, 5, 18, 10, 0, tzinfo=timezone.utc)
    ch.friend_session_id = None
    return ch


# ===========================================================================
# POST /api/challenges — create a challenge
# ===========================================================================

@pytest.mark.asyncio
async def test_create_challenge_requires_body(client):
    resp = await client.post("/api/challenges", json={})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_challenge_requires_all_fields(client):
    resp = await client.post("/api/challenges", json={"market_id": 1})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_challenge_rejects_invalid_guess(client, mock_db):
    resp = await client.post(
        "/api/challenges",
        json={"market_id": 42, "guess": "invalid", "threshold": 50},
    )
    assert resp.status_code == 400
    assert "higher" in resp.json()["detail"] or "lower" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_create_challenge_market_not_found(client, mock_db):
    mock_db.execute = AsyncMock(return_value=_MockResult(first_value=None))

    resp = await client.post(
        "/api/challenges",
        json={"market_id": 999, "guess": "higher", "threshold": 50},
    )
    assert resp.status_code == 404
    assert "Market not found" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_create_challenge_success(client, mock_db):
    mock_db.execute = AsyncMock(side_effect=[
        _MockResult(first_value=SimpleNamespace(id=42, name="Will Fed cut rates?")),
        _MockResult(scalar_value=None),  # no code collision
    ])
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()

    resp = await client.post(
        "/api/challenges",
        json={"market_id": 42, "guess": "higher", "threshold": 55},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert "challenge_code" in body
    assert body["challenge_code"].startswith("BL-")
    assert "url" in body
    assert "bainluck.com/challenge/" in body["url"]
    assert body["market_name"] == "Will Fed cut rates?"
    assert body["creator_guess"] == "higher"
    assert body["threshold"] == 55


# ===========================================================================
# GET /api/challenges/{code} — get challenge details
# ===========================================================================

@pytest.mark.asyncio
async def test_get_challenge_not_found(client, mock_db):
    mock_db.execute = AsyncMock(return_value=_MockResult(scalar_value=None))

    resp = await client.get("/api/challenges/BL-nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_challenge_success(client, mock_db):
    challenge = _make_challenge()
    mock_db.execute = AsyncMock(side_effect=[
        _MockResult(scalar_value=challenge),
        _MockResult(scalar_value=0.62),
    ])

    resp = await client.get("/api/challenges/BL-abc123")
    assert resp.status_code == 200
    body = resp.json()

    expected_keys = {
        "challenge_code", "market_name", "market_id",
        "creator_guess", "threshold", "friend_guess",
        "current_probability", "creator_correct", "friend_correct",
        "resolved_at", "created_at",
    }
    assert set(body.keys()) == expected_keys
    assert body["challenge_code"] == "BL-abc123"
    assert body["market_name"] == "Will the Fed cut rates?"
    assert body["current_probability"] == 0.62


@pytest.mark.asyncio
async def test_get_challenge_null_probability(client, mock_db):
    challenge = _make_challenge()
    mock_db.execute = AsyncMock(side_effect=[
        _MockResult(scalar_value=challenge),
        _MockResult(scalar_value=None),
    ])

    resp = await client.get("/api/challenges/BL-abc123")
    assert resp.status_code == 200
    assert resp.json()["current_probability"] is None


# ===========================================================================
# POST /api/challenges/{code}/accept — friend accepts
# ===========================================================================

@pytest.mark.asyncio
async def test_accept_challenge_requires_body(client):
    resp = await client.post("/api/challenges/BL-abc123/accept", json={})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_accept_challenge_rejects_invalid_guess(client, mock_db):
    resp = await client.post(
        "/api/challenges/BL-abc123/accept",
        json={"guess": "sideways"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_accept_challenge_not_found(client, mock_db):
    mock_db.execute = AsyncMock(return_value=_MockResult(scalar_value=None))

    resp = await client.post(
        "/api/challenges/BL-nonexistent/accept",
        json={"guess": "lower"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_accept_challenge_already_accepted(client, mock_db):
    challenge = _make_challenge(friend_guess="lower")
    mock_db.execute = AsyncMock(return_value=_MockResult(scalar_value=challenge))

    resp = await client.post(
        "/api/challenges/BL-abc123/accept",
        json={"guess": "higher"},
    )
    assert resp.status_code == 409
    assert "already accepted" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_accept_challenge_success(client, mock_db):
    challenge = _make_challenge()
    mock_db.execute = AsyncMock(side_effect=[
        _MockResult(scalar_value=challenge),
        _MockResult(scalar_value=0.62),
    ])
    mock_db.commit = AsyncMock()

    resp = await client.post(
        "/api/challenges/BL-abc123/accept",
        json={"guess": "lower"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "accepted"
    assert body["challenge_code"] == "BL-abc123"
    assert body["friend_guess"] == "lower"
    assert "actual_probability" in body
    assert "creator_correct" in body
    assert "friend_correct" in body
