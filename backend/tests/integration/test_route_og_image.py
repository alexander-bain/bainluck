"""Integration tests for GET /api/og/prediction.

Validates OG image card HTML generation for prediction shares.
Uses the shared ``client`` / ``mock_db`` fixtures from conftest.py.
"""

from types import SimpleNamespace

import pytest


class _MockResult:
    def __init__(self, row=None):
        self._row = row

    def one_or_none(self):
        return self._row


class TestOGPredictionCard:
    async def test_returns_200_html(self, client, mock_db):
        mock_db.execute.return_value = _MockResult(
            SimpleNamespace(name="Will Bitcoin hit $100K?", llm_sport_category="crypto")
        )
        resp = await client.get("/api/og/prediction?market_id=1&guess=higher&correct=true&threshold=50&actual=65")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")

    async def test_correct_shows_checkmark(self, client, mock_db):
        mock_db.execute.return_value = _MockResult(
            SimpleNamespace(name="Fed rate cuts", llm_sport_category="economics")
        )
        body = (await client.get("/api/og/prediction?market_id=1&correct=true")).text
        assert "Correct" in body
        assert "#16a34a" in body

    async def test_incorrect_shows_x(self, client, mock_db):
        mock_db.execute.return_value = _MockResult(
            SimpleNamespace(name="Fed rate cuts", llm_sport_category="economics")
        )
        body = (await client.get("/api/og/prediction?market_id=1&correct=false")).text
        assert "Not quite" in body
        assert "#dc2626" in body

    async def test_market_name_in_og_meta(self, client, mock_db):
        mock_db.execute.return_value = _MockResult(
            SimpleNamespace(name="NBA Finals winner?", llm_sport_category="basketball")
        )
        body = (await client.get("/api/og/prediction?market_id=1")).text
        assert "NBA Finals winner?" in body
        assert "og:title" in body

    async def test_unknown_market_uses_default_name(self, client, mock_db):
        mock_db.execute.return_value = _MockResult(None)
        body = (await client.get("/api/og/prediction?market_id=999")).text
        assert "Prediction Market" in body

    async def test_missing_market_id_returns_422(self, client):
        resp = await client.get("/api/og/prediction")
        assert resp.status_code == 422

    async def test_post_rejected(self, client):
        resp = await client.post("/api/og/prediction?market_id=1")
        assert resp.status_code == 405
