"""Contract tests for GET /api/feed.

Tests response shape and query parameter validation, not exact data values.
The feed is the home page — the most important endpoint for user experience.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.routes.feed import (
    _apply_manual_review_decision_map,
    _filter_reviewed_feed_items,
    _review_key_for_feed_item,
)


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

    async def test_include_events_false_skips_golf_tournaments(self, client, monkeypatch):
        from app.routes import feed

        called = False

        async def fake_score_golf(*args, **kwargs):
            nonlocal called
            called = True
            return []

        monkeypatch.setattr(feed, "_score_golf_tournaments", fake_score_golf)

        resp = await client.get("/api/feed?include_events=false&include_futures=false")

        assert resp.status_code == 200
        assert called is False

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

    async def test_limit_validation_not_integer(self, client):
        resp = await client.get("/api/feed?limit=abc")
        assert resp.status_code == 422

    async def test_include_events_validation_not_boolean(self, client):
        resp = await client.get("/api/feed?include_events=maybe")
        assert resp.status_code == 422

    async def test_malformed_tags_are_ignored(self, client):
        resp = await client.get("/api/feed?tags=not-json")
        body = resp.json()

        assert resp.status_code == 200
        assert body["items"] == []

    async def test_non_list_tags_are_ignored(self, client):
        resp = await client.get("/api/feed?tags=%7B%22sport%22%3A%22basketball%22%7D")
        body = resp.json()

        assert resp.status_code == 200
        assert body["items"] == []

    async def test_include_both_false_skips_all_scorers(self, client, monkeypatch):
        from app.routes import feed

        called = {"events": False, "futures": False, "golf": False}

        async def fake_score_events(*args, **kwargs):
            called["events"] = True
            return []

        async def fake_score_futures(*args, **kwargs):
            called["futures"] = True
            return []

        async def fake_score_golf(*args, **kwargs):
            called["golf"] = True
            return []

        monkeypatch.setattr(feed, "_score_events", fake_score_events)
        monkeypatch.setattr(feed, "_score_futures", fake_score_futures)
        monkeypatch.setattr(feed, "_score_golf_tournaments", fake_score_golf)

        resp = await client.get("/api/feed?include_events=false&include_futures=false")

        assert resp.status_code == 200
        assert resp.json()["items"] == []
        assert called == {"events": False, "futures": False, "golf": False}


class TestFeedMockedDataContract:
    async def test_mocked_futures_response_envelope_and_item_shape(self, client, monkeypatch):
        from app.routes import feed

        async def fake_score_futures(*args, **kwargs):
            return [
                {
                    "type": "futures",
                    "score": 84,
                    "reason": "Leader moved higher",
                    "headline": "Acme leads at 64%",
                    "context_summary": "Acme is the current leader.",
                    "data": {
                        "id": 101,
                        "name": "Who will win the launch race?",
                        "source": "kalshi",
                        "source_count": 1,
                        "sources": ["kalshi"],
                        "market_tier": 3,
                        "status": "open",
                        "top_outcomes": [
                            {"id": 1, "name": "Acme", "probability": 0.64, "rank": 1, "movement": 0.08},
                        ],
                        "outcome_count": 2,
                        "market_tags": ["category:tech", "source:kalshi"],
                    },
                    "_sort_time": 1000,
                    "_quality_class": "keep",
                    "_quality_family_key": "launch",
                    "_quality_story_key": "launch-race",
                }
            ]

        async def fake_apply_review_decisions(*args, **kwargs):
            return None

        monkeypatch.setattr(feed, "_score_futures", fake_score_futures)
        monkeypatch.setattr(feed, "_apply_manual_review_decisions", fake_apply_review_decisions)
        monkeypatch.setattr(feed, "diversify_discover_first_page", lambda items, **kwargs: items)

        resp = await client.get("/api/feed?include_events=false")
        body = resp.json()

        assert resp.status_code == 200
        assert set(body) == {"items", "total", "limit", "offset", "has_more"}
        assert body["total"] == 1
        assert body["has_more"] is False
        assert len(body["items"]) == 1

        item = body["items"][0]
        assert item["type"] == "futures"
        assert item["score"] == 84
        assert item["reason"] == "Leader moved higher"
        assert item["headline"] == "Acme leads at 64%"
        assert item["context_summary"] == "Acme is the current leader."
        assert "_sort_time" not in item
        assert "_quality_class" not in item
        assert "_quality_family_key" not in item
        assert "_quality_story_key" not in item

        data = item["data"]
        assert data["id"] == 101
        assert data["source"] == "kalshi"
        assert data["sources"] == ["kalshi"]
        assert data["top_outcomes"][0]["probability"] == 0.64
        assert data["market_tags"] == ["category:tech", "source:kalshi"]

    async def test_mocked_items_are_sorted_and_paginated_after_scoring(self, client, monkeypatch):
        from app.routes import feed

        async def fake_score_futures(*args, **kwargs):
            return [
                {"type": "futures", "score": 10, "reason": "low", "headline": "Low", "data": {"id": 1}},
                {"type": "futures", "score": 90, "reason": "high", "headline": "High", "data": {"id": 2}},
                {"type": "futures", "score": 50, "reason": "mid", "headline": "Mid", "data": {"id": 3}},
            ]

        async def fake_apply_review_decisions(*args, **kwargs):
            return None

        monkeypatch.setattr(feed, "_score_futures", fake_score_futures)
        monkeypatch.setattr(feed, "_apply_manual_review_decisions", fake_apply_review_decisions)
        monkeypatch.setattr(feed, "diversify_discover_first_page", lambda items, **kwargs: items)

        resp = await client.get("/api/feed?include_events=false&limit=1&offset=1")
        body = resp.json()

        assert resp.status_code == 200
        assert body["total"] == 3
        assert body["limit"] == 1
        assert body["offset"] == 1
        assert body["has_more"] is True
        assert [item["data"]["id"] for item in body["items"]] == [3]


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
        assert "debug_timing" in body
        assert body["debug_timing"]["total_ms"] >= 0
        assert any(stage["stage"] == "futures" for stage in body["debug_timing"]["stages"])
        assert any(stage["stage"] == "futures.candidate_queries" for stage in body["debug_timing"]["stages"])
        assert "x-feed-elapsed-ms" in resp.headers
        assert body["debug_summary"]["items"] == 0
        assert body["debug_items"] == []

    async def test_exclude_reviewed_requires_admin_auth(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "test-admin")

        resp = await client.get("/api/feed?exclude_reviewed=true")

        assert resp.status_code == 403


class TestFeedReviewedFiltering:
    def test_review_key_for_feed_item_uses_type_and_data_id(self):
        item = {"type": "futures", "data": {"id": "123"}}

        assert _review_key_for_feed_item(item) == ("futures", 123)

    def test_filter_reviewed_feed_items_removes_matching_items(self):
        items = [
            {"type": "futures", "data": {"id": 1}},
            {"type": "event", "data": {"id": 2}},
            {"type": "futures", "data": {"id": 3}},
        ]

        kept, filtered = _filter_reviewed_feed_items(
            items,
            {("futures", 1), ("event", 2)},
        )

        assert filtered == 2
        assert [item["data"]["id"] for item in kept] == [3]


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


class TestDiscoverEffectiveSettlementFollowups:
    async def test_followups_require_admin_secret(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "test-admin")

        resp = await client.get(
            "/api/admin/discover-quality/effective-settlement-followups"
        )

        assert resp.status_code == 422

    async def test_followups_reject_bad_admin_secret(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "test-admin")

        resp = await client.get(
            "/api/admin/discover-quality/effective-settlement-followups?secret=bad"
        )

        assert resp.status_code == 403

    async def test_followups_return_suppressed_market_diagnostics(
        self,
        client,
        mock_db,
        monkeypatch,
    ):
        from app.routes import feed

        monkeypatch.setenv("ADMIN_TOKEN", "test-admin")
        markets = [
            SimpleNamespace(id=101, source="kalshi"),
            SimpleNamespace(id=202, source="polymarket"),
        ]
        result = MagicMock()
        result.scalars.return_value.all.return_value = markets
        mock_db.execute.return_value = result

        def _fake_followup(market, now):
            if market.id == 202:
                return None
            return {
                "market_id": market.id,
                "source": market.source,
                "name": "Will the Knicks make the NBA Finals?",
                "status": "open",
                "category": "sports",
                "llm_sport_category": "basketball",
                "leader_name": "No",
                "leader_probability": 0.91,
                "leader_opening_probability": 0.18,
                "max_recent_movement": 0.004,
                "updated_at": "2026-05-21T00:00:00+00:00",
                "days_since_update": 1.2,
                "age_bucket": "recent_source_update",
                "resolution_date": None,
                "commence_time": None,
                "blockers": ["sports_effectively_settled"],
                "checks": {"sports_effectively_settled": True},
                "top_outcomes": [{"name": "No", "probability": 0.91}],
                "suggested_action": "Run or inspect Kalshi settlement/API winner backfill for this market.",
            }

        monkeypatch.setattr(
            feed, "build_effective_settlement_followup_item", _fake_followup
        )

        resp = await client.get(
            "/api/admin/discover-quality/effective-settlement-followups?secret=test-admin&limit=10"
        )
        body = resp.json()

        assert resp.status_code == 200
        assert body["count"] == 1
        assert body["source_counts"] == {"kalshi": 1}
        assert body["category_counts"] == {"basketball": 1}
        assert body["age_buckets"] == {"recent_source_update": 1}
        assert body["items"][0]["market_id"] == 101
        assert body["items"][0]["blockers"] == ["sports_effectively_settled"]
        assert "settlement" in body["items"][0]["suggested_action"].lower()


class TestDiscoverInteractions:
    async def test_records_discover_interaction_batch(self, client):
        resp = await client.post(
            "/api/feed/interactions",
            json={
                "interactions": [
                    {
                        "action": "impression",
                        "item_type": "futures",
                        "item_id": "123",
                        "category": "tech",
                        "item_name": "AI market",
                        "score": 88,
                        "rank": 4,
                        "surface": "web",
                        "source": "viewport",
                    },
                    {
                        "action": "detail_click",
                        "item_type": "futures",
                        "item_id": "123",
                        "category": "tech",
                        "surface": "web",
                        "source": "card",
                    },
                ]
            },
            headers={"x-session-id": "test-session"},
        )

        assert resp.status_code == 200
        assert resp.json() == {"status": "ok", "recorded": 2}

    async def test_discover_engagement_summary_requires_admin_secret(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "test-admin")

        resp = await client.get("/api/admin/discover-engagement?secret=bad")

        assert resp.status_code == 403

    async def test_discover_launch_health_trends_shape(self, client, mock_db, monkeypatch):
        from unittest.mock import MagicMock

        monkeypatch.setenv("ADMIN_TOKEN", "test-admin")
        results = []
        for _ in range(3):
            total = MagicMock()
            total.scalar.return_value = 0
            repeat = MagicMock()
            repeat.all.return_value = []
            impressions = MagicMock()
            impressions.all.return_value = []
            results.extend([total, repeat, impressions])
        mock_db.execute.side_effect = results

        resp = await client.get(
            "/api/admin/discover-engagement/launch-health-trends?secret=test-admin"
        )
        body = resp.json()

        assert resp.status_code == 200
        assert [row["window"] for row in body["windows"]] == ["1h", "24h", "7d"]
        assert body["windows"][0]["repeat_rate"] == 0
        assert body["windows"][0]["stale_rate"] == 0

    async def test_discover_engagement_summary_rolls_up_rates(self, client, mock_db, monkeypatch):
        from unittest.mock import MagicMock

        monkeypatch.setenv("ADMIN_TOKEN", "test-admin")
        old_update = datetime.now(timezone.utc) - timedelta(days=3)
        grouped = MagicMock()
        grouped.all.return_value = [
            ("native", "basketball", "event", "impression", 20),
            ("native", "basketball", "event", "open", 4),
            ("native", "basketball", "event", "share", 1),
        ]
        score_buckets = MagicMock()
        score_buckets.all.return_value = [
            (95, "impression", 10),
            (95, "detail_click", 3),
            (35, "impression", 10),
            (35, "dismiss", 2),
        ]
        top_items = MagicMock()
        top_items.all.return_value = [
            ("event", "1", "Lakers vs Celtics", "basketball", "native", 2),
        ]
        review = MagicMock()
        review.all.return_value = [
            ("event", "1", "Lakers vs Celtics", "basketball", "native", False, "impression", 10, 5, 91),
            ("event", "1", "Lakers vs Celtics", "basketball", "native", False, "detail_click", 3, None, None),
        ]
        repeat = MagicMock()
        repeat.all.return_value = []
        impression_items = MagicMock()
        impression_items.all.return_value = [
            SimpleNamespace(
                item_type="futures",
                item_id="123",
                item_name="Will stale market resolve?",
                category="politics",
                surface="native",
                impressions=7,
            )
        ]
        futures_result = MagicMock()
        futures_result.all.return_value = [
            SimpleNamespace(
                id=123,
                status="open",
                updated_at=old_update,
                resolution_date=None,
            )
        ]
        decisions = MagicMock()
        decisions.scalars.return_value.all.return_value = []
        mock_db.execute.side_effect = [
            grouped,
            score_buckets,
            review,
            decisions,
            repeat,
            impression_items,
            futures_result,
            top_items,
        ]

        resp = await client.get("/api/admin/discover-engagement?secret=test-admin&days=7")
        body = resp.json()

        assert resp.status_code == 200
        assert body["totals"]["impressions"] == 20
        assert body["totals"]["opens"] == 4
        assert body["totals"]["shares"] == 1
        assert body["score_buckets"][0]["bucket"] == "90-99"
        assert body["score_buckets"][0]["open_rate"] == 0.3
        assert body["score_buckets"][1]["bucket"] == "30-39"
        assert body["score_buckets"][1]["dismiss_rate"] == 0.2
        assert any(
            row["surface"] == "native"
            and row["category"] == "basketball"
            and row["open_rate"] == 0.2
            for row in body["groups"]
        )
        assert body["opportunities"][0]["kind"] == "promote"
        assert body["review_queue"][0]["kind"] == "promote"
        assert body["review_queue"][0]["auth_segment"] == "anonymous"
        assert body["launch_health"]["repeat_rate"] == 0
        assert body["launch_health"]["stale_impressions"] == 7
        assert body["launch_health"]["top_stale_items"][0]["root_cause_label"] == "No recent market update"
        assert body["launch_health"]["top_stale_items"][0]["root_cause"]["code"] == "no_recent_market_update"
        assert body["runtime_config"]["interaction_suppression_enabled"] is True
        assert body["top_items"][0]["item_name"] == "Lakers vs Celtics"


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


class TestDiscoverReviewDecisionScoring:
    """Human review decisions from admin should nudge ranking scores."""

    def test_manual_review_decisions_apply_bounded_score_changes(self):
        items = [
            {"type": "futures", "score": 96, "data": {"id": 1}},
            {"type": "futures", "score": 12, "data": {"id": 2}},
            {"type": "event", "score": 50, "data": {"id": 3}},
        ]

        _apply_manual_review_decision_map(
            items,
            {
                ("futures", "1"): "accepted_promote",
                ("futures", "2"): "accepted_downrank",
            },
        )

        assert items[0]["score"] == 100
        assert items[0]["_review_decision"] == "accepted_promote"
        assert items[1]["score"] == 0
        assert items[1]["_review_decision"] == "accepted_downrank"
        assert items[2]["score"] == 50
