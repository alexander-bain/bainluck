from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes import admin


def _client_with_db(db) -> TestClient:
    app = FastAPI()
    app.include_router(admin.router, prefix="/admin")

    async def _override_get_db():
        return db

    app.dependency_overrides[admin.get_db] = _override_get_db
    return TestClient(app)


class _WriteDB:
    def __init__(self):
        self.added = None
        self.committed = False

    def add(self, row):
        self.added = row

    async def commit(self):
        self.committed = True
        self.added.id = 99


def test_pairwise_label_persists_feed_context(monkeypatch):
    db = _WriteDB()
    monkeypatch.setattr(admin, "_check_admin_secret", lambda secret: secret == "ok")

    response = _client_with_db(db).post(
        "/admin/pairwise/label?secret=ok",
        json={
            "card_a_market_id": 1,
            "card_b_market_id": 2,
            "card_a_score": 80.0,
            "card_b_score": 65.0,
            "choice": "b",
            "reviewer": "alex",
            "pair_id": "adjacent_rank:batch:1:2",
            "pair_strategy": "adjacent_rank",
            "surface": "discover_quality",
            "batch_id": "batch",
            "confidence": "medium",
            "ranking_error": True,
            "notes": "B is more surprising",
            "card_a_snapshot": {"rank": 1, "name": "A"},
            "card_b_snapshot": {"rank": 2, "name": "B"},
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "label_id": 99}
    assert db.committed is True
    assert db.added.pair_id == "adjacent_rank:batch:1:2"
    assert db.added.pair_strategy == "adjacent_rank"
    assert db.added.surface == "discover_quality"
    assert db.added.batch_id == "batch"
    assert db.added.confidence == "medium"
    assert db.added.ranking_error is True
    assert db.added.notes == "B is more surprising"
    assert db.added.card_a_snapshot == {"rank": 1, "name": "A"}
    assert db.added.card_b_snapshot == {"rank": 2, "name": "B"}
