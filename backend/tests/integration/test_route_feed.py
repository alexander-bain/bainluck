"""Contract tests for GET /api/feed.

Tests response shape and query parameter validation, not exact data values.
The feed is the home page — the most important endpoint for user experience.
"""

import pytest


class TestFeedEmptyShape:
    """With an empty DB, the feed returns a valid empty response."""

    async def test_returns_200(self, client):
        resp = await client.get("/api/feed")
        assert resp.status_code == 200

    async def test_has_required_keys(self, client):
        resp = await client.get("/api/feed")
        body = resp.json()
        for key in ["items", "total", "limit", "offset", "has_more"]:
            assert key in body, f"Missing key: {key}"

    async def test_items_is_list(self, client):
        resp = await client.get("/api/feed")
        body = resp.json()
        assert isinstance(body["items"], list)

    async def test_empty_db_returns_empty_items(self, client):
        resp = await client.get("/api/feed")
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 0

    async def test_has_more_is_false_when_empty(self, client):
        resp = await client.get("/api/feed")
        body = resp.json()
        assert body["has_more"] is False

    async def test_limit_defaults_to_200(self, client):
        resp = await client.get("/api/feed")
        body = resp.json()
        assert body["limit"] == 200

    async def test_offset_defaults_to_0(self, client):
        resp = await client.get("/api/feed")
        body = resp.json()
        assert body["offset"] == 0

    async def test_total_is_int(self, client):
        resp = await client.get("/api/feed")
        body = resp.json()
        assert isinstance(body["total"], int)
        assert body["total"] >= 0


class TestFeedQueryParams:

    async def test_custom_limit(self, client):
        resp = await client.get("/api/feed?limit=10")
        body = resp.json()
        assert body["limit"] == 10

    async def test_custom_offset(self, client):
        resp = await client.get("/api/feed?offset=5")
        body = resp.json()
        assert body["offset"] == 5

    async def test_sport_filter_accepted(self, client):
        resp = await client.get("/api/feed?sport=basketball")
        assert resp.status_code == 200

    async def test_multiple_sport_filter(self, client):
        resp = await client.get("/api/feed?sport=basketball&sport=baseball")
        assert resp.status_code == 200

    async def test_include_events_false(self, client):
        resp = await client.get("/api/feed?include_events=false")
        assert resp.status_code == 200

    async def test_include_futures_false(self, client):
        resp = await client.get("/api/feed?include_futures=false")
        assert resp.status_code == 200

    async def test_include_both_false_returns_empty(self, client):
        resp = await client.get("/api/feed?include_events=false&include_futures=false")
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []

    async def test_status_filter_accepted(self, client):
        resp = await client.get("/api/feed?status=live")
        assert resp.status_code == 200

    async def test_limit_validation_too_high(self, client):
        resp = await client.get("/api/feed?limit=99999")
        assert resp.status_code == 422

    async def test_limit_validation_zero(self, client):
        resp = await client.get("/api/feed?limit=0")
        assert resp.status_code == 422

    async def test_offset_validation_negative(self, client):
        resp = await client.get("/api/feed?offset=-1")
        assert resp.status_code == 422


class TestFeedDebug:
    async def test_debug_requires_admin_secret(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "test-admin")

        resp = await client.get("/api/feed?debug=true")

        assert resp.status_code == 403

    async def test_debug_returns_diagnostics_for_admin(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "test-admin")

        resp = await client.get("/api/feed?debug=true&secret=test-admin")
        body = resp.json()

        assert resp.status_code == 200
        assert "debug_summary" in body
        assert "debug_items" in body
        assert body["debug_summary"]["items"] == 0
        assert body["debug_items"] == []


class TestDiscoverQualityTrace:
    async def test_trace_requires_admin_secret(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "test-admin")

        resp = await client.get("/api/admin/discover-quality/trace/123")

        assert resp.status_code == 422

    async def test_trace_rejects_bad_admin_secret(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "test-admin")

        resp = await client.get("/api/admin/discover-quality/trace/123?secret=bad")

        assert resp.status_code == 403

    async def test_trace_returns_404_for_missing_market(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "test-admin")

        resp = await client.get("/api/admin/discover-quality/trace/123?secret=test-admin")

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Market not found"

    async def test_trace_returns_pipeline_shape(self, client, monkeypatch):
        from app.routes import feed

        monkeypatch.setenv("ADMIN_TOKEN", "test-admin")

        async def _fake_trace(db, market_id, **kwargs):
            return {
                "market": {"id": market_id, "name": "Will this ship?"},
                "base_eligibility": {"eligible": True, "blockers": [], "checks": {}},
                "candidate_pools": {
                    "included": True,
                    "deduped_candidate_count": 1,
                    "candidate_position": 1,
                    "pools": [],
                },
                "score_trace": {
                    "eligible_before_caps": True,
                    "blockers": [],
                    "scores": {"highlight": 90, "after_quality": 90, "after_explanation": 90, "final": 90},
                },
                "rank_phases": {
                    "raw_futures_rank": 1,
                    "post_canonical_dedupe_rank": 1,
                    "post_initial_sort_rank": 1,
                    "post_event_demote_rank": 1,
                    "post_event_mix_rank": 1,
                    "post_diversity_rank": 1,
                    "returned_rank": 1,
                    "returned": True,
                    "dropped_by_canonical_dedupe": False,
                },
                "final_ranking": {"survived_final_caps": True, "final_futures_rank": 1},
                "suggested_fix": "No immediate fix.",
            }

        monkeypatch.setattr(feed, "build_discover_market_trace", _fake_trace)

        resp = await client.get("/api/admin/discover-quality/trace/123?secret=test-admin")
        body = resp.json()

        assert resp.status_code == 200
        assert body["market"]["id"] == 123
        assert body["candidate_pools"]["included"] is True
        assert body["rank_phases"]["returned_rank"] == 1
        assert body["final_ranking"]["survived_final_caps"] is True
        assert "suggested_fix" in body


class TestFeedMyTeamsAnonymous:
    """my_teams_only without auth returns early with requires_auth flag."""

    async def test_returns_200(self, client):
        resp = await client.get("/api/feed?my_teams_only=true")
        assert resp.status_code == 200

    async def test_requires_auth_flag(self, client):
        resp = await client.get("/api/feed?my_teams_only=true")
        body = resp.json()
        assert body.get("requires_auth") is True
        assert body.get("my_teams_only") is True

    async def test_empty_items(self, client):
        resp = await client.get("/api/feed?my_teams_only=true")
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 0


class TestFeedResponseTypes:
    """Verify field types in the response match the frontend's expectations."""

    async def test_total_limit_offset_are_ints(self, client):
        resp = await client.get("/api/feed")
        body = resp.json()
        assert isinstance(body["total"], int)
        assert isinstance(body["limit"], int)
        assert isinstance(body["offset"], int)

    async def test_has_more_is_bool(self, client):
        resp = await client.get("/api/feed")
        body = resp.json()
        assert isinstance(body["has_more"], bool)
