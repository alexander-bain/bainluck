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

    def unique(self):
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
        "fixable_interesting": False,
        "repair_type": None,
        "repair_target_entity": None,
        "repair_note": None,
        "reviewer": "alex",
        "created_at": datetime(2026, 5, 23, 12, 0, tzinfo=timezone.utc),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_create_judgment_accepts_json_body(monkeypatch):
    db = _WriteDB()
    monkeypatch.setattr(
        admin_judgments, "_check_admin_secret", lambda secret, **kw: secret == "ok"
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
        admin_judgments, "_check_admin_secret", lambda secret, **kw: secret == "ok"
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
        admin_judgments, "_check_admin_secret", lambda secret, **kw: secret == "ok"
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
        admin_judgments, "_check_admin_secret", lambda secret, **kw: secret == "ok"
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


class _DeleteDB:
    """Mock DB for the DELETE endpoint: a single-row lookup + delete + commit."""

    def __init__(self, judgment):
        self._judgment = judgment
        self.deleted = None
        self.committed = False

    async def execute(self, statement):
        judgment = self._judgment
        return SimpleNamespace(scalar_one_or_none=lambda: judgment)

    async def delete(self, row):
        self.deleted = row

    async def commit(self):
        self.committed = True


def test_delete_judgment_removes_row_and_commits(monkeypatch):
    # L2-108 Item 2: Rapid-mode "undo last" — deleting a judgment removes the
    # row and commits (read-your-writes) so a mis-tap never lingers in the set.
    judgment = _judgment(id=99, label="kill")
    db = _DeleteDB(judgment)
    monkeypatch.setattr(
        admin_judgments, "_check_admin_secret", lambda secret, **kw: True
    )

    response = _client_with_db(db).delete("/admin/ranking-judgments/99?secret=ok")

    assert response.status_code == 200
    assert response.json() == {"status": "deleted", "id": 99, "label": "kill"}
    assert db.deleted is judgment
    assert db.committed is True


def test_delete_judgment_missing_returns_404(monkeypatch):
    db = _DeleteDB(None)
    monkeypatch.setattr(
        admin_judgments, "_check_admin_secret", lambda secret, **kw: True
    )

    response = _client_with_db(db).delete("/admin/ranking-judgments/12345?secret=ok")

    assert response.status_code == 404
    assert db.deleted is None
    assert db.committed is False


def test_delete_judgment_requires_auth(monkeypatch):
    from fastapi import HTTPException

    def _reject(*_args, **_kwargs):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    db = _DeleteDB(_judgment(id=99))
    monkeypatch.setattr(admin_judgments, "_check_admin_secret", _reject)

    response = _client_with_db(db).delete("/admin/ranking-judgments/99?secret=wrong")

    assert response.status_code == 403
    assert db.deleted is None
    assert db.committed is False


def test_labeling_candidate_strata_parser_ignores_unknown_values():
    assert admin_judgments._parse_candidate_strata("weather,nope,finance_ladder") == [
        "weather",
        "finance_ladder",
    ]


def test_labeling_candidate_strata_parser_accepts_low_confidence():
    result = admin_judgments._parse_candidate_strata("low_confidence,weather")
    assert result == ["low_confidence", "weather"]


def test_low_confidence_stratum_included_in_defaults():
    assert "low_confidence" in admin_judgments.DEFAULT_LABELING_STRATA


def test_labeling_candidates_low_confidence_stratum(monkeypatch):
    """The low_confidence stratum returns boundary markets with moderate volume."""
    market = SimpleNamespace(
        id=456,
        name="Will Tesla stock close above $200 this week?",
        description="Boundary market",
        llm_sport_category="tech",
        sport=None,
        source="kalshi",
        hook_description="A moderate-confidence market",
        image_url=None,
        group_id=None,
        resolution_date=None,
        created_at=datetime(2026, 5, 23, 12, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 5, 23, 12, 0, tzinfo=timezone.utc),
        outcomes=[
            SimpleNamespace(
                id=10,
                name="Yes",
                current_probability=0.45,
                probability_change_24h=0.02,
                rank=1,
            )
        ],
    )
    db = _ReadDB(
        [
            _ExecuteResult(rows=[]),  # reviewed keys
            _ExecuteResult(scalar_rows=[market]),  # low_confidence stratum
        ]
    )
    monkeypatch.setattr(
        admin_judgments, "_check_admin_secret", lambda secret, **kw: secret == "ok"
    )

    response = _client_with_db(db).get(
        "/admin/ranking-judgments/candidates?secret=ok&strata=low_confidence&limit=10"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["strata"] == ["low_confidence"]
    assert len(body["items"]) == 1
    assert body["items"][0]["id"] == 456
    assert body["items"][0]["stratum"] == "low_confidence"
    assert body["items"][0]["selection_reason"] == "labeling:low_confidence"


def test_labeling_candidates_returns_stratified_items(monkeypatch):
    market = SimpleNamespace(
        id=123,
        name="Will it rain in New York?",
        description="Weather context",
        llm_sport_category="weather",
        sport=None,
        source="kalshi",
        hook_description=None,
        image_url=None,
        group_id="weather-nyc",
        resolution_date=None,
        created_at=datetime(2026, 5, 23, 12, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 5, 23, 12, 0, tzinfo=timezone.utc),
        outcomes=[
            SimpleNamespace(
                id=1,
                name="Yes",
                current_probability=0.62,
                probability_change_24h=0.03,
                rank=1,
            )
        ],
    )
    db = _ReadDB(
        [
            _ExecuteResult(rows=[]),
            _ExecuteResult(scalar_rows=[market]),
        ]
    )
    monkeypatch.setattr(
        admin_judgments, "_check_admin_secret", lambda secret, **kw: secret == "ok"
    )

    response = _client_with_db(db).get(
        "/admin/ranking-judgments/candidates?secret=ok&strata=weather&limit=10"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["candidate_source"] == "labeling_sampler_v1"
    assert body["strata"] == ["weather"]
    assert body["items"][0]["id"] == 123
    assert body["items"][0]["stratum"] == "weather"
    assert body["items"][0]["selection_reason"] == "labeling:weather"
    assert body["reviewed_filter"]["filtered_count"] == 0


def test_labeling_candidates_excludes_reviewed_market(monkeypatch):
    """Submitting a judgment for a market excludes it from subsequent candidate
    queries for the same reviewer — verifying server-side reviewed state."""
    market_reviewed = SimpleNamespace(
        id=100,
        name="Already reviewed market",
        description=None,
        llm_sport_category="weather",
        sport=None,
        source="kalshi",
        hook_description=None,
        image_url=None,
        group_id=None,
        resolution_date=None,
        created_at=datetime(2026, 5, 23, 12, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 5, 23, 12, 0, tzinfo=timezone.utc),
        outcomes=[
            SimpleNamespace(
                id=10,
                name="Yes",
                current_probability=0.50,
                probability_change_24h=None,
                rank=1,
            )
        ],
    )
    market_new = SimpleNamespace(
        id=200,
        name="Not yet reviewed market",
        description=None,
        llm_sport_category="weather",
        sport=None,
        source="kalshi",
        hook_description=None,
        image_url=None,
        group_id=None,
        resolution_date=None,
        created_at=datetime(2026, 5, 23, 12, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 5, 23, 12, 0, tzinfo=timezone.utc),
        outcomes=[
            SimpleNamespace(
                id=20,
                name="No",
                current_probability=0.40,
                probability_change_24h=None,
                rank=1,
            )
        ],
    )
    # First query result: reviewed keys query returns market 100 as already
    # reviewed by "alex" on surface "native_discover".
    reviewed_row = SimpleNamespace(item_type="futures", market_id=100, event_id=None)
    db = _ReadDB(
        [
            # load_reviewed_ranking_keys query
            _ExecuteResult(rows=[(reviewed_row.item_type, reviewed_row.market_id, reviewed_row.event_id)]),
            # stratum query returns both markets
            _ExecuteResult(scalar_rows=[market_reviewed, market_new]),
        ]
    )
    monkeypatch.setattr(
        admin_judgments, "_check_admin_secret", lambda secret, **kw: secret == "ok"
    )

    response = _client_with_db(db).get(
        "/admin/ranking-judgments/candidates"
        "?secret=ok&strata=weather&limit=10&reviewer=alex&reviewed_surface=native_discover"
    )

    assert response.status_code == 200
    body = response.json()
    # Market 100 should be excluded, only market 200 remains
    assert len(body["items"]) == 1
    assert body["items"][0]["id"] == 200
    assert body["reviewed_filter"]["filtered_count"] == 1
    assert body["reviewed_filter"]["reviewed_key_count"] == 1
    assert body["reviewed_filter"]["reviewer"] == "alex"


def test_create_judgment_accepts_nested_card_snapshot_metadata(monkeypatch):
    db = _WriteDB()
    monkeypatch.setattr(
        admin_judgments, "_check_admin_secret", lambda secret, **kw: secret == "ok"
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
        admin_judgments, "_check_admin_secret", lambda secret, **kw: secret == "ok"
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
        admin_judgments, "_check_admin_secret", lambda secret, **kw: secret == "ok"
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
        admin_judgments, "_check_admin_secret", lambda secret, **kw: secret == "ok"
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
        admin_judgments, "_check_admin_secret", lambda secret, **kw: secret == "ok"
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
        admin_judgments, "_check_admin_secret", lambda secret, **kw: secret == "ok"
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


# ---------------------------------------------------------------------------
# Eval-export endpoint tests
# ---------------------------------------------------------------------------


def test_eval_export_returns_json_with_hashed_reviewer(monkeypatch):
    judgment = _judgment(
        market_id=100,
        label="love",
        reviewer="alex@example.com",
        category_at_review="politics",
        archetype_at_review="world_event",
        quality_class_at_review="compelling",
        label_metadata={
            "card_snapshot": {
                "source": "polymarket",
                "category": "politics",
                "archetype": "world_event",
                "quality_class": "compelling",
                "hook_description": "A political market",
                "image_url": "https://example.com/img.jpg",
                "rendered_probability": 0.72,
                "story_key": "story:election",
                "family_key": "politics:us",
                "group_id": "group-1",
            }
        },
    )
    db = _ReadDB([_ExecuteResult(scalar_rows=[judgment])])
    monkeypatch.setattr(
        admin_judgments, "_check_admin_secret", lambda secret, **kw: secret == "ok"
    )

    response = _client_with_db(db).get(
        "/admin/ranking-judgments/eval-export?secret=ok&days=30"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert "split_counts" in body
    assert "label_counts" in body
    assert body["label_counts"]["love"] == 1
    row = body["rows"][0]
    assert row["market_id"] == 100
    assert row["label"] == "love"
    assert row["reviewer_hash"] != "alex@example.com"
    assert len(row["reviewer_hash"]) == 12
    assert row["split"] in ("train", "dev", "test")
    assert row["category"] == "politics"
    assert row["source"] == "polymarket"
    assert row["has_hook"] is True
    assert row["has_image"] is True
    assert row["rendered_probability"] == 0.72
    assert row["story_key"] == "story:election"
    assert row["surface"] == "discover"


def test_eval_export_split_is_deterministic():
    """Same market_id always maps to the same split."""
    split1 = admin_judgments._dataset_split(100, None)
    split2 = admin_judgments._dataset_split(100, None)
    assert split1 == split2
    assert split1 in ("train", "dev", "test")


def test_eval_export_reviewer_hash_is_consistent():
    """Same reviewer always produces the same hash."""
    h1 = admin_judgments._reviewer_hash("alex")
    h2 = admin_judgments._reviewer_hash("alex")
    assert h1 == h2
    assert len(h1) == 12


def test_eval_export_different_reviewers_different_hashes():
    h1 = admin_judgments._reviewer_hash("alex")
    h2 = admin_judgments._reviewer_hash("sam")
    assert h1 != h2


def test_eval_export_csv_format(monkeypatch):
    judgment = _judgment(market_id=200, label="bad", reason_tags=["boring", "stale"])
    db = _ReadDB([_ExecuteResult(scalar_rows=[judgment])])
    monkeypatch.setattr(
        admin_judgments, "_check_admin_secret", lambda secret, **kw: secret == "ok"
    )

    response = _client_with_db(db).get(
        "/admin/ranking-judgments/eval-export?secret=ok&fmt=csv"
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "discover_labels_eval.csv" in response.headers["content-disposition"]
    assert "market_id,event_id,market_name,reviewer_hash,label" in response.text
    assert "bad" in response.text


def test_eval_export_split_filter(monkeypatch):
    judgments = [
        _judgment(id=1, market_id=i, label="love")
        for i in range(1, 101)
    ]
    db = _ReadDB([_ExecuteResult(scalar_rows=judgments)])
    monkeypatch.setattr(
        admin_judgments, "_check_admin_secret", lambda secret, **kw: secret == "ok"
    )

    response = _client_with_db(db).get(
        "/admin/ranking-judgments/eval-export?secret=ok&split=test"
    )

    assert response.status_code == 200
    body = response.json()
    for row in body["rows"]:
        assert row["split"] == "test"


def test_eval_export_no_pii_in_output(monkeypatch):
    judgment = _judgment(
        market_id=300,
        reviewer="secret.person@meta.com",
    )
    db = _ReadDB([_ExecuteResult(scalar_rows=[judgment])])
    monkeypatch.setattr(
        admin_judgments, "_check_admin_secret", lambda secret, **kw: secret == "ok"
    )

    response = _client_with_db(db).get(
        "/admin/ranking-judgments/eval-export?secret=ok"
    )

    body = response.json()
    raw_text = str(body)
    assert "secret.person@meta.com" not in raw_text
    assert body["rows"][0]["reviewer_hash"] != "secret.person@meta.com"


def test_eval_export_requires_auth(monkeypatch):
    db = _ReadDB([])
    monkeypatch.setattr(
        admin_judgments, "_check_admin_secret", lambda secret, **kw: False
    )

    response = _client_with_db(db).get(
        "/admin/ranking-judgments/eval-export?secret=wrong"
    )

    assert response.status_code == 403


async def _fake_resolve_admin_email(_request, _db=None):
    return "admin@test.com"


async def _fake_resolve_admin_email_none(_request, _db=None):
    return None


def test_create_judgment_resolves_native_reviewer_to_admin_email(monkeypatch):
    """When reviewer=native and the request has a Bearer token, the server
    resolves the reviewer to the admin's email for per-user reviewed state."""
    db = _WriteDB()
    monkeypatch.setattr(
        admin_judgments, "_check_admin_secret", lambda secret, **kw: secret == "ok"
    )
    monkeypatch.setattr(
        admin_judgments, "_resolve_admin_email", _fake_resolve_admin_email,
    )

    response = _client_with_db(db).post(
        "/admin/ranking-judgments?secret=ok&label=love&reviewer=native",
    )

    assert response.status_code == 200
    assert db.added.reviewer == "admin@test.com"


def test_create_judgment_keeps_explicit_reviewer(monkeypatch):
    """When reviewer is explicitly set (not 'native'), it is not resolved."""
    db = _WriteDB()
    monkeypatch.setattr(
        admin_judgments, "_check_admin_secret", lambda secret, **kw: secret == "ok"
    )
    monkeypatch.setattr(
        admin_judgments, "_resolve_admin_email", _fake_resolve_admin_email,
    )

    response = _client_with_db(db).post(
        "/admin/ranking-judgments?secret=ok&label=love&reviewer=sam",
    )

    assert response.status_code == 200
    assert db.added.reviewer == "sam"


def test_create_judgment_native_reviewer_fallback_when_unauthenticated(monkeypatch):
    """When reviewer=native but no Bearer token (anonymous admin via secret),
    reviewer stays 'native'."""
    db = _WriteDB()
    monkeypatch.setattr(
        admin_judgments, "_check_admin_secret", lambda secret, **kw: secret == "ok"
    )
    monkeypatch.setattr(
        admin_judgments, "_resolve_admin_email", _fake_resolve_admin_email_none,
    )

    response = _client_with_db(db).post(
        "/admin/ranking-judgments?secret=ok&label=love&reviewer=native",
    )

    assert response.status_code == 200
    assert db.added.reviewer == "native"


# ---------------------------------------------------------------------------
# Coverage endpoint tests
# ---------------------------------------------------------------------------


class _CoverageDB:
    """Mock DB for coverage endpoint that handles both judgment query and
    queue health queries (reviewed keys + per-stratum market queries)."""

    def __init__(self, judgments, reviewed_rows=None, stratum_markets=None):
        self._judgments = judgments
        self._reviewed_rows = reviewed_rows or []
        self._stratum_markets = stratum_markets or []
        self._call_count = 0

    async def execute(self, statement):
        self._call_count += 1
        # First call: judgment query
        if self._call_count == 1:
            return _ExecuteResult(scalar_rows=self._judgments)
        # Second call: load_reviewed_ranking_keys
        if self._call_count == 2:
            return _ExecuteResult(rows=self._reviewed_rows)
        # Remaining calls: per-stratum market queries
        return _ExecuteResult(scalar_rows=list(self._stratum_markets))


def test_coverage_returns_stratum_heatmap_and_queue_health(monkeypatch):
    j1 = _judgment(
        id=1,
        label="love",
        reviewer="alex",
        category_at_review="politics",
        label_metadata={
            "card_snapshot": {
                "stratum": "top_feed_like",
                "selection_reason": "labeling:top_feed_like",
                "category": "politics",
            }
        },
    )
    j2 = _judgment(
        id=2,
        label="bad",
        reviewer="alex",
        category_at_review="weather",
        label_metadata={
            "card_snapshot": {
                "selection_reason": "labeling:weather",
                "category": "weather",
            }
        },
    )
    db = _CoverageDB([j1, j2])
    monkeypatch.setattr(
        admin_judgments, "_check_admin_secret", lambda secret, **kw: secret == "ok"
    )

    response = _client_with_db(db).get(
        "/admin/ranking-judgments/coverage?secret=ok"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total_reviewed"] == 2
    assert body["window"] == "all"

    # by_stratum should have top_feed_like and weather
    strata_names = [s["stratum"] for s in body["by_stratum"]]
    assert "top_feed_like" in strata_names
    assert "weather" in strata_names

    # by_verdict
    assert body["by_verdict"]["love"] == 1
    assert body["by_verdict"]["bad"] == 1

    # by_category
    assert "politics" in body["by_category"]
    assert "weather" in body["by_category"]

    # reviewer_progress
    assert len(body["reviewer_progress"]) == 1
    assert body["reviewer_progress"][0]["total"] == 2

    # queue_health has one entry per DEFAULT_LABELING_STRATA
    assert len(body["queue_health"]) == len(admin_judgments.DEFAULT_LABELING_STRATA)

    # insufficient_strata flags strata with < 50 labels
    assert "top_feed_like" in body["insufficient_strata"]

    assert "generated_at" in body


def test_coverage_window_filter(monkeypatch):
    """Passing window=24h filters to recent judgments only."""
    j_old = _judgment(
        id=1,
        label="love",
        created_at=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
        label_metadata={},
    )
    j_new = _judgment(
        id=2,
        label="bad",
        created_at=datetime(2026, 5, 25, 12, 0, tzinfo=timezone.utc),
        label_metadata={},
    )
    # The endpoint filters in the SQL query, but our mock returns all rows.
    # We just verify the endpoint accepts the window param without error.
    db = _CoverageDB([j_old, j_new])
    monkeypatch.setattr(
        admin_judgments, "_check_admin_secret", lambda secret, **kw: secret == "ok"
    )

    response = _client_with_db(db).get(
        "/admin/ranking-judgments/coverage?secret=ok&window=7d"
    )

    assert response.status_code == 200
    assert response.json()["window"] == "7d"


def test_coverage_requires_auth(monkeypatch):
    db = _CoverageDB([])
    monkeypatch.setattr(
        admin_judgments, "_check_admin_secret", lambda secret, **kw: False
    )

    response = _client_with_db(db).get(
        "/admin/ranking-judgments/coverage?secret=wrong"
    )

    assert response.status_code == 403


def test_coverage_unknown_stratum_fallback(monkeypatch):
    """Judgments without stratum info in snapshot are classified as 'unknown'."""
    j = _judgment(id=1, label="love", label_metadata=None)
    db = _CoverageDB([j])
    monkeypatch.setattr(
        admin_judgments, "_check_admin_secret", lambda secret, **kw: secret == "ok"
    )

    response = _client_with_db(db).get(
        "/admin/ranking-judgments/coverage?secret=ok"
    )

    assert response.status_code == 200
    strata = [s["stratum"] for s in response.json()["by_stratum"]]
    assert "unknown" in strata


def test_card_snapshot_preserves_stratum_and_selection_reason(monkeypatch):
    """The stratum and selection_reason fields are now in the allowed snapshot keys."""
    db = _WriteDB()
    monkeypatch.setattr(
        admin_judgments, "_check_admin_secret", lambda secret, **kw: secret == "ok"
    )

    response = _client_with_db(db).post(
        "/admin/ranking-judgments?secret=ok&label=love",
        json={
            "card_snapshot": {
                "stratum": "weather",
                "selection_reason": "labeling:weather",
                "name": "Rain market",
            }
        },
    )

    assert response.status_code == 200
    snapshot = db.added.label_metadata["card_snapshot"]
    assert snapshot["stratum"] == "weather"
    assert snapshot["selection_reason"] == "labeling:weather"


def test_labeling_candidates_firebase_admin_not_shortcircuited(monkeypatch):
    """Regression: the workbench sends a Firebase user token in the Bearer header
    (for reviewer identity), so `_check_admin_secret` RAISES (token != ADMIN_TOKEN).
    The endpoint must fall back to the Firebase-admin check via `_authorize_admin`
    and NOT 403. Before the fix, the raising secret check short-circuited the
    `and`, 403-ing legit admins and breaking the Labeling Workbench.
    """
    from fastapi import HTTPException

    market = SimpleNamespace(
        id=789, name="Will the Fed cut in September?", description=None,
        llm_sport_category="economics", sport=None, source="kalshi",
        hook_description=None, image_url=None, group_id=None, resolution_date=None,
        created_at=datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc),
        outcomes=[SimpleNamespace(id=1, name="Yes", current_probability=0.5,
                                  probability_change_24h=0.01, rank=1)],
    )
    db = _ReadDB([_ExecuteResult(rows=[]), _ExecuteResult(scalar_rows=[market])])

    def _raise_secret(secret=None, **kw):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    async def _admin_ok(secret, request, db):
        return True

    monkeypatch.setattr(admin_judgments, "_check_admin_secret", _raise_secret)
    monkeypatch.setattr(admin_judgments, "_check_admin_auth", _admin_ok)

    response = _client_with_db(db).get(
        "/admin/ranking-judgments/candidates?strata=low_confidence&limit=10"
    )
    assert response.status_code == 200, response.text
