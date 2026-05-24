"""Focused route contract tests for Discover ranking judgments."""

from datetime import date, datetime, timezone
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes import admin_judgments


def _client_with_db(db) -> TestClient:
    app = FastAPI()
    app.include_router(admin_judgments.router)

    async def _override_get_db():
        return db

    app.dependency_overrides[admin_judgments.get_db] = _override_get_db
    app.dependency_overrides[admin_judgments.get_db_rw] = _override_get_db
    return TestClient(app)


class _WriteDB:
    def __init__(self):
        self.added = None
        self.committed = False

    def add(self, row):
        self.added = row

    async def commit(self):
        self.committed = True

    async def refresh(self, row):
        row.id = 42
        row.date = date(2026, 5, 23)
        row.created_at = datetime(2026, 5, 23, 12, 0, tzinfo=timezone.utc)


class _ExecuteResult:
    def __init__(self, scalar_value=None, scalar_rows=None, rows=None):
        self.scalar_value = scalar_value
        self.scalar_rows = scalar_rows or []
        self.rows = rows or []

    def scalar(self):
        return self.scalar_value

    def scalars(self):
        return self

    def all(self):
        return self.scalar_rows or self.rows


class _ReadDB:
    def __init__(self, results):
        self.results = list(results)

    async def execute(self, statement):
        if not self.results:
            raise AssertionError(f"Unexpected query: {statement}")
        return self.results.pop(0)


def _judgment(**overrides):
    values = {
        "id": 7,
        "date": date(2026, 5, 23),
        "surface": "discover",
        "rank_seen": 3,
        "item_type": "futures",
        "market_id": 123,
        "event_id": None,
        "market_name": "Will this test pass?",
        "label": "love",
        "reason_tags": ["timely", "clear"],
        "better_than": None,
        "worse_than": None,
        "notes": "useful",
        "score_at_review": 87.5,
        "category_at_review": "tech",
        "archetype_at_review": "ai",
        "quality_class_at_review": "compelling",
        "headline_at_review": "Test headline",
        "feed_request_id": "feed-1",
        "label_metadata": {},
        "reviewer": "alex",
        "created_at": datetime(2026, 5, 23, 12, 0, tzinfo=timezone.utc),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_create_judgment_accepts_json_body(monkeypatch):
    db = _WriteDB()
    monkeypatch.setattr(
        admin_judgments, "_check_admin_secret", lambda secret: secret == "ok"
    )

    response = _client_with_db(db).post(
        "/admin/ranking-judgments",
        json={
            "secret": "ok",
            "label": "love",
            "market_id": 123,
            "market_name": "Will this test pass?",
            "reason_tags": ["timely", "clear"],
            "score_at_review": 87.5,
            "category_at_review": "tech",
            "label_metadata": {"source": "manual"},
            "card_snapshot": {
                "schema_version": "discover-card-v1",
                "batch_id": "batch-1",
                "rank": 4,
                "item_type": "futures",
                "market_id": 123,
                "name": "Will this test pass?",
                "source": "polymarket",
                "story_key": "story:test",
                "family_key": "test:family",
                "group_id": "group-1",
                "context": "Test context",
                "image_url": "https://example.com/image.jpg",
                "hook_description": "Test hook",
                "rendered_probability": 0.61,
                "top_outcomes": [{"name": "Yes", "probability": 0.61}],
                "ignored": "drop me",
            },
            "would_be_interesting_if": "It were about the #1 Netflix movie",
            "fixable_interest_score": 5,
            "fix_type": "wrong_entity_rank",
            "desired_entity_or_variant": "#1 Netflix movie",
            "current_entity_or_variant": "#2 Netflix movie",
            "create_issue_candidate": True,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "id": 42, "label": "love"}
    assert db.committed is True
    assert db.added.surface == "discover"
    assert db.added.item_type == "futures"
    assert db.added.market_id == 123
    assert db.added.reason_tags == ["timely", "clear"]
    assert db.added.label_metadata == {
        "source": "manual",
        "card_snapshot": {
            "schema_version": "discover-card-v1",
            "batch_id": "batch-1",
            "rank": 4,
            "item_type": "futures",
            "market_id": 123,
            "name": "Will this test pass?",
            "source": "polymarket",
            "story_key": "story:test",
            "family_key": "test:family",
            "group_id": "group-1",
            "context": "Test context",
            "image_url": "https://example.com/image.jpg",
            "hook_description": "Test hook",
            "rendered_probability": 0.61,
            "top_outcomes": [{"name": "Yes", "probability": 0.61}],
        },
        "fixable_interest": {
            "would_be_interesting_if": "It were about the #1 Netflix movie",
            "fixable_interest_score": 5,
            "fix_type": "wrong_entity_rank",
            "desired_entity_or_variant": "#1 Netflix movie",
            "current_entity_or_variant": "#2 Netflix movie",
            "create_issue_candidate": True,
        },
    }


def test_create_judgment_keeps_query_param_write_path(monkeypatch):
    db = _WriteDB()
    monkeypatch.setattr(
        admin_judgments, "_check_admin_secret", lambda secret: secret == "ok"
    )

    response = _client_with_db(db).post(
        "/admin/ranking-judgments"
        "?secret=ok&label=bad&reason_tags=boring,duplicate&reviewer=sam"
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "id": 42, "label": "bad"}
    assert db.added.label == "bad"
    assert db.added.reason_tags == ["boring", "duplicate"]
    assert db.added.reviewer == "sam"


def test_create_judgment_canonicalizes_reason_tag_aliases(monkeypatch):
    db = _WriteDB()
    monkeypatch.setattr(
        admin_judgments, "_check_admin_secret", lambda secret: secret == "ok"
    )

    response = _client_with_db(db).post(
        "/admin/ranking-judgments"
        "?secret=ok&label=bad&reason_tags=fun,needs-context,duplicate,fun"
    )

    assert response.status_code == 200
    assert db.added.reason_tags == ["fun_or_weird", "unclear", "duplicate"]


def test_create_judgment_nests_metadata_fixable_interest(monkeypatch):
    db = _WriteDB()
    monkeypatch.setattr(
        admin_judgments, "_check_admin_secret", lambda secret: secret == "ok"
    )

    response = _client_with_db(db).post(
        "/admin/ranking-judgments?secret=ok&label=bad",
        json={
            "label_metadata": {
                "would_be_interesting_if": "It were not stale",
                "fix_type": "staleness",
            }
        },
    )

    assert response.status_code == 200
    assert db.added.label_metadata == {
        "fixable_interest": {
            "would_be_interesting_if": "It were not stale",
            "fix_type": "staleness",
        }
    }


def test_create_judgment_accepts_nested_card_snapshot_metadata(monkeypatch):
    db = _WriteDB()
    monkeypatch.setattr(
        admin_judgments, "_check_admin_secret", lambda secret: secret == "ok"
    )

    response = _client_with_db(db).post(
        "/admin/ranking-judgments?secret=ok&label=love",
        json={
            "label_metadata": {
                "card_snapshot": {
                    "batch_id": "batch-2",
                    "feed_request_id": "req-1",
                    "name": "Snapshot name",
                    "top_outcomes": [{"name": "Yes", "probability": 0.72}],
                    "reasons": ["compelling_topic"],
                    "unbounded": "ignored",
                }
            }
        },
    )

    assert response.status_code == 200
    assert db.added.label_metadata == {
        "card_snapshot": {
            "schema_version": "discover-card-v1",
            "batch_id": "batch-2",
            "feed_request_id": "req-1",
            "name": "Snapshot name",
            "top_outcomes": [{"name": "Yes", "probability": 0.72}],
            "reasons": ["compelling_topic"],
        }
    }


def test_list_judgments_returns_rows_and_summary(monkeypatch):
    db = _ReadDB(
        [
            _ExecuteResult(scalar_value=1),
            _ExecuteResult(scalar_rows=[_judgment()]),
            _ExecuteResult(rows=[("love", 1)]),
        ]
    )
    monkeypatch.setattr(
        admin_judgments, "_check_admin_secret", lambda secret: secret == "ok"
    )

    response = _client_with_db(db).get(
        "/admin/ranking-judgments?secret=ok&label=love&surface=discover"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["summary"] == {"love": 1}
    assert body["judgments"][0]["event_id"] is None
    assert body["judgments"][0]["label_metadata"] == {}
    assert body["judgments"][0]["card_snapshot"] is None
    assert body["judgments"][0]["reason_tags"] == ["timely", "clear"]
    assert body["judgments"][0]["created_at"] == "2026-05-23T12:00:00+00:00"


def test_summary_judgments_returns_category_breakdown(monkeypatch):
    db = _ReadDB(
        [
            _ExecuteResult(rows=[("love", 2), ("bad", 1)]),
            _ExecuteResult(rows=[("tech", "love", 2), (None, "bad", 1)]),
            _ExecuteResult(rows=[("love", 80.25, 72.0, 91.0, 2)]),
            _ExecuteResult(scalar_value=1),
        ]
    )
    monkeypatch.setattr(
        admin_judgments, "_check_admin_secret", lambda secret: secret == "ok"
    )

    response = _client_with_db(db).get("/admin/ranking-judgments/summary?secret=ok")

    assert response.status_code == 200
    assert response.json() == {
        "total": 3,
        "labels": {"love": 2, "bad": 1},
        "pairwise_count": 1,
        "score_by_label": [
            {
                "label": "love",
                "avg_score": 80.2,
                "min_score": 72.0,
                "max_score": 91.0,
                "count": 2,
            }
        ],
        "by_category": {"tech": {"love": 2}, "uncategorized": {"bad": 1}},
    }


def test_export_judgments_streams_csv(monkeypatch):
    db = _ReadDB([_ExecuteResult(scalar_rows=[_judgment()])])
    monkeypatch.setattr(
        admin_judgments, "_check_admin_secret", lambda secret: secret == "ok"
    )

    response = _client_with_db(db).get("/admin/ranking-judgments/export?secret=ok")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "ranking_judgments.csv" in response.headers["content-disposition"]
    assert "market_name,label,reason_tags" in response.text
    assert "label_metadata,card_snapshot,reviewer" in response.text
    assert "Will this test pass?,love,\"timely,clear\"" in response.text


def test_fixable_interest_clusters_groups_rows(monkeypatch):
    metadata = {
        "card_snapshot": {
            "name": "Will the #2 Netflix movie stay #2?",
            "story_key": "story:netflix",
            "family_key": "entertainment:streaming",
            "group_id": "group-netflix",
            "category": "entertainment",
        },
        "fixable_interest": {
            "would_be_interesting_if": "It were about #1",
            "fixable_interest_score": 5,
            "fix_type": "wrong_entity_rank",
            "desired_entity_or_variant": "#1 Netflix movie",
            "current_entity_or_variant": "#2 Netflix movie",
            "create_issue_candidate": True,
        },
    }
    db = _ReadDB(
        [
            _ExecuteResult(
                scalar_rows=[
                    _judgment(id=1, market_id=123, label_metadata=metadata),
                    _judgment(id=2, market_id=124, rank_seen=7, label="bad", label_metadata=metadata),
                ]
            )
        ]
    )
    monkeypatch.setattr(
        admin_judgments, "_check_admin_secret", lambda secret: secret == "ok"
    )

    response = _client_with_db(db).get(
        "/admin/ranking-judgments/fixable-interest/clusters?secret=ok&status=all"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    cluster = body["clusters"][0]
    assert cluster["status"] == "open"
    assert cluster["fix_type"] == "wrong_entity_rank"
    assert cluster["story_key"] == "story:netflix"
    assert cluster["count"] == 2
    assert cluster["issue_candidate_count"] == 2
    assert cluster["max_fixable_interest_score"] == 5
    assert cluster["affected_ranks"] == [3, 7]
    assert cluster["market_ids"] == [123, 124]
    assert cluster["examples"][0]["card_snapshot"]["name"] == "Will the #2 Netflix movie stay #2?"


def test_triage_fixable_interest_cluster_updates_matching_rows(monkeypatch):
    metadata = {
        "card_snapshot": {"story_key": "story:netflix", "name": "Netflix market"},
        "fixable_interest": {
            "would_be_interesting_if": "It were about #1",
            "fix_type": "wrong_entity_rank",
        },
    }
    matching = _judgment(id=1, market_id=123, label_metadata=metadata)
    nonmatching = _judgment(
        id=2,
        market_id=124,
        label_metadata={
            "card_snapshot": {"story_key": "story:other"},
            "fixable_interest": {
                "would_be_interesting_if": "It were fresh",
                "fix_type": "staleness",
            },
        },
    )
    cluster_id = admin_judgments._cluster_id(admin_judgments._cluster_identity(matching))

    class _WriteReadDB(_ReadDB):
        def __init__(self):
            super().__init__([_ExecuteResult(scalar_rows=[matching, nonmatching])])
            self.committed = False

        async def commit(self):
            self.committed = True

    db = _WriteReadDB()
    monkeypatch.setattr(
        admin_judgments, "_check_admin_secret", lambda secret: secret == "ok"
    )

    response = _client_with_db(db).post(
        f"/admin/ranking-judgments/fixable-interest/clusters/{cluster_id}/triage",
        json={
            "secret": "ok",
            "status": "linked",
            "github_issue_url": "https://github.com/alexander-bain/bainluck/issues/602",
            "github_issue_number": 602,
            "notes": "Created follow-up issue",
        },
    )

    assert response.status_code == 200
    assert response.json()["updated_count"] == 1
    assert db.committed is True
    assert matching.label_metadata["fixable_interest"]["triage"] == {
        "status": "linked",
        "github_issue_url": "https://github.com/alexander-bain/bainluck/issues/602",
        "github_issue_number": 602,
        "notes": "Created follow-up issue",
    }
    assert "triage" not in nonmatching.label_metadata["fixable_interest"]
