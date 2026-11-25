"""Tests for #13102 Decision 385: A blind morning scout deck & Keep promotion gate."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

from starlette.requests import Request

import app.routes.admin_ranking_eval as admin
from app.utils.roundup_containers import ROUNDUP_PRODUCERS, build_roundup_producer_from_definition
from app.utils.scout_morning_deck import (
    SCOUT_DECK_KEY_REDIS_PREFIX,
    SCOUT_DECK_SURFACE,
    build_scout_morning_deck,
)
from scripts.promote_kept_scout_sets import apply_scout_promotions, plan_scout_promotions

FROZEN_NOW = datetime(2026, 11, 26, 15, 0, tzinfo=timezone.utc)


class _MemoryRedis:
    def __init__(self) -> None:
        self.kv: dict[str, str] = {}

    def get(self, key: str):
        return self.kv.get(key)

    def set(self, key: str, val: str, ex: int | None = None):
        self.kv[key] = val
        return True

    def mget(self, keys):
        return [self.kv.get(k) for k in keys]


class _FakeDB:
    def __init__(self, rows=()):
        self.rows = list(rows)

    async def execute(self, stmt):
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: self.rows))


def _staged_fixture(idx: int) -> dict:
    slug = f"scout-secret-slug-{idx}"
    return {
        "slug": slug,
        "name": f"Novelty Set {idx}",
        "kicker": "CURIOSITIES",
        "category": "culture",
        "why_better_together": "Grouped together for morning review.",
        "look": "bars",
        "members": [
            {"market_id": idx * 10 + 1, "source": "polymarket", "title": f"Kalshi vs market A{idx}?", "volume": 1000, "category": "culture"},
            {"market_id": idx * 10 + 2, "source": "kalshi", "title": f"Market B{idx} happens?", "volume": 900, "category": "culture"},
            {"market_id": idx * 10 + 3, "source": "polymarket", "title": f"Market C{idx} happens?", "volume": 800, "category": "culture"},
        ],
        "rule_definition": {
            "slug": slug,
            "membership": "computed-produced",
            "kind": "roundup",
            "relations": ["same_subject"],
            "level": "related",
            "kicker": "CURIOSITIES",
            "name": f"Novelty Set {idx}",
            "category": "culture",
            "tag": "CULTURE",
            "section_title": f"Novelty Set {idx}",
            "footer": "Updated continuously.",
            "look": "bars",
            "stage": "preview",
            "scout": {"origin": "discover_fun_scout", "requires_fable_look": True},
            "rule": {
                "producer": "fun_scout_set",
                "min_numbered_members": 3,
                "card_rows": 3,
                "selector": {"fun_tag": slug},
            },
        },
    }


def _public_fixture(idx: int) -> dict:
    return {
        "slug": f"public-decoy-slug-{idx}",
        "name": f"Public Roundup {idx}",
        "kicker": "TECH & AI",
        "category": "tech",
        "summary": "Publicly curated set of open markets.",
        "look": "bars",
        "members": [
            {"title": f"AI benchmark {idx}a?", "leading_outcome": "Yes", "probability": 0.42, "change_24h": 0.03},
            {"title": f"AI benchmark {idx}b?", "leading_outcome": "Yes", "probability": 0.55, "change_24h": -0.02},
            {"title": f"AI benchmark {idx}c?", "leading_outcome": "Yes", "probability": 0.31, "change_24h": 0.01},
        ],
        "rule_definition": {
            "slug": f"public-decoy-slug-{idx}",
            "kind": "roundup",
            "relations": ["same_subject"],
            "level": "related",
            "stage": "public",
            "rule": {"producer": "container_machinery", "selector": {"fun_tag": f"public-{idx}"}},
        },
    }


async def test_blind_deck_mixes_equally_and_keeps_key_strictly_in_redis(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "a" * 32)
    rc = _MemoryRedis()
    rc.set(
        "bainluck:fun_scout:run:2026-11-26",
        json.dumps(
            {
                "run_date": "2026-11-26",
                "staged_sets": [_staged_fixture(1), _staged_fixture(2)],
            }
        ),
    )
    market_rows = [
        SimpleNamespace(
            id=11,
            status="open",
            name="Polymarket live title 11?",
            question="Polymarket live title 11?",
            image_url="https://example.com/11.jpg",
            outcomes=[SimpleNamespace(name="Yes", current_probability=0.61, probability_change_24h=0.04, rank=1)],
        ),
        SimpleNamespace(
            id=12,
            status="open",
            name="Live title 12?",
            question="Live title 12?",
            image_url=None,
            outcomes=[SimpleNamespace(name="Yes", current_probability=0.33, probability_change_24h=-0.02, rank=1)],
        ),
        SimpleNamespace(
            id=13,
            status="open",
            name="Live title 13?",
            question="Live title 13?",
            image_url=None,
            outcomes=[SimpleNamespace(name="Yes", current_probability=0.19, probability_change_24h=0.0, rank=1)],
        ),
    ]
    db = _FakeDB(market_rows)

    deck = await build_scout_morning_deck(
        db,
        deck_date="2026-11-26",
        redis_client=rc,
        public_override=[_public_fixture(1), _public_fixture(2)],
        now=FROZEN_NOW,
    )
    assert deck["status"] == "ready"
    assert deck["staged_count"] == 2
    assert deck["decoy_count"] == 2
    assert deck["total_count"] == 4
    assert len(deck["items"]) == 4

    # Reload order must be deterministic for the same date
    deck2 = await build_scout_morning_deck(
        db,
        deck_date="2026-11-26",
        redis_client=rc,
        public_override=[_public_fixture(1), _public_fixture(2)],
        now=FROZEN_NOW,
    )
    assert [i["item_id"] for i in deck["items"]] == [i["item_id"] for i in deck2["items"]]
    assert [i["title"] for i in deck["items"]] == [i["title"] for i in deck2["items"]]

    # Zero leakage in browser JSON response
    serialized = json.dumps(deck).lower()
    for forbidden in (
        "scout-secret-slug",
        "public-decoy-slug",
        "requires_fable_look",
        "discover_fun_scout",
        "kalshi",
        "polymarket",
        '"origin"',
        '"slug"',
        '"market_id"',
    ):
        assert forbidden not in serialized, forbidden

    # Key persisted strictly in Redis
    raw_key = rc.get(f"{SCOUT_DECK_KEY_REDIS_PREFIX}:2026-11-26")
    assert raw_key is not None
    sealed = json.loads(raw_key)
    origins = {v["origin"] for v in sealed["entries"].values()}
    assert origins == {"scout", "public"}


async def test_admin_route_validates_date_and_returns_clean_empty_state(monkeypatch):
    monkeypatch.setattr(admin, "_check_admin_secret", lambda *a, **k: True)
    rc = _MemoryRedis()

    import app.utils.scout_morning_deck as mod

    orig_build = mod.build_scout_morning_deck

    async def _call_build(db, *, deck_date=None):
        return await orig_build(db, deck_date=deck_date, redis_client=rc)

    monkeypatch.setattr(mod, "build_scout_morning_deck", _call_build)
    req = Request({"type": "http", "method": "GET", "path": "/", "headers": [], "query_string": b""})
    out = await admin.get_scout_morning_deck(req, date="2026-11-26", secret=None, db=_FakeDB())
    assert out["status"] == "empty"
    assert out["items"] == []


def test_keep_promotion_ignores_decoys_and_validates_container_files(tmp_path):
    assert SCOUT_DECK_SURFACE == "grade_scout_morning_deck"
    staged1 = _staged_fixture(1)
    public1 = _public_fixture(1)
    sealed_key = {
        "deck_date": "2026-11-26",
        "entries": {
            "s01": {
                "origin": "scout",
                "slug": staged1["slug"],
                "name": staged1["name"],
                "rule_definition": staged1["rule_definition"],
            },
            "s02": {
                "origin": "public",
                "slug": public1["slug"],
                "name": public1["name"],
                "rule_definition": public1["rule_definition"],
            },
        },
    }
    judgments = [
        {"market_name": "s01", "label": "Keep", "notes": "great set", "label_metadata": {"deck_date": "2026-11-26", "item_id": "s01", "grade": "Keep"}},
        {"market_name": "s02", "label": "Keep", "notes": "ignore public decoy", "label_metadata": {"deck_date": "2026-11-26", "item_id": "s02", "grade": "Keep"}},
    ]
    plan = plan_scout_promotions(judgments, sealed_key, deck_date="2026-11-26")
    assert len(plan["promote"]) == 1
    assert plan["promote"][0]["slug"] == staged1["slug"]
    assert plan["promote"][0]["definition"]["stage"] == "public"
    assert plan["ignored_decoys"] == ["s02"]

    dry = apply_scout_promotions(plan, containers_dir=tmp_path, write=False)
    assert dry["written_files"] == [] and dry["promote_count"] == 1

    written = apply_scout_promotions(plan, containers_dir=tmp_path, write=True)
    assert len(written["written_files"]) == 1
    promoted_doc = json.loads((tmp_path / f"{staged1['slug']}.json").read_text(encoding="utf-8"))
    assert promoted_doc["stage"] == "public"
    assert promoted_doc["rule"]["producer"] == "fun_scout_set"
    # Verify roundup_containers builds a fun_scout_set producer via _KIND_TO_MODULE_BUILDER
    built_producer = build_roundup_producer_from_definition(promoted_doc)
    assert built_producer.slug == promoted_doc["slug"]
    assert callable(built_producer.produce)
    assert callable(ROUNDUP_PRODUCERS["roundup-tomorrows-highs"].produce)
