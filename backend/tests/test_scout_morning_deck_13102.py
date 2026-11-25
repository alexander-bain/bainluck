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
        '"member_ids"',
    ):
        assert forbidden not in serialized, forbidden

    # Key persisted strictly in Redis
    raw_key = rc.get(f"{SCOUT_DECK_KEY_REDIS_PREFIX}:2026-11-26")
    assert raw_key is not None
    sealed = json.loads(raw_key)
    origins = {v["origin"] for v in sealed["entries"].values()}
    assert origins == {"scout", "public"}
    scout_key_entries = [v for v in sealed["entries"].values() if v["origin"] == "scout"]
    assert {tuple(v["member_ids"]) for v in scout_key_entries} == {(11, 12, 13), (21, 22, 23)}


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


async def test_public_producer_omits_unpriced_or_nameless_members_and_refuses_below_min(monkeypatch):
    from app.utils import discover_fun_scout as dfs
    from app.utils import discover_fun_tags as dft
    from app.utils.roundup_containers import RoundupMembers, RoundupRefusal

    monkeypatch.setattr(dft, "fun_market_ids_for_sub_tag", lambda _tag: [101, 102, 103, 104])
    defn = _staged_fixture(9)["rule_definition"]
    defn["stage"] = "public"
    defn["rule"]["min_numbered_members"] = 3

    def _row(mid: int, name: str | None, prob: float | None, volume: float = 100.0):
        return SimpleNamespace(
            id=mid,
            status="open",
            volume=volume,
            name=f"Market {mid}",
            question=f"Market {mid}?",
            category="culture",
            outcomes=[] if (name is None and prob is None) else [
                SimpleNamespace(name=name, current_probability=prob, probability_change_24h=0.01, rank=1)
            ],
        )

    # 2 valid + 1 unpriced (prob=None) + 1 empty outcome name -> refuses rather than inventing "Yes 50%"
    refused_rows = [
        _row(101, "Alpha", 0.62, 400.0),
        _row(102, "Beta", 0.38, 300.0),
        _row(103, "Gamma", None, 200.0),
        _row(104, "", 0.50, 100.0),
    ]
    producer = dfs.build_fun_scout_set_producer(defn)
    res_refused = await producer.produce(_FakeDB(refused_rows))
    assert isinstance(res_refused, RoundupRefusal)
    assert res_refused.reasons == ("too_few_live_members:2<3",)

    # 3 valid + 1 unpriced -> omits unpriced row cleanly without synthesizing 0.5 / "Yes"
    passing_rows = [
        _row(101, "Alpha", 0.62, 400.0),
        _row(102, "Beta", 0.38, 300.0),
        _row(103, "Gamma", 0.25, 250.0),
        _row(104, "Delta", None, 999.0),
    ]
    res_ok = await producer.produce(_FakeDB(passing_rows))
    assert isinstance(res_ok, RoundupMembers)
    assert [m["id"] for m in res_ok.members] == [101, 102, 103]
    assert all(r["label"] != "Market 104?" for r in res_ok.rows)


async def test_public_producer_pins_graded_member_ids_and_gates_rule_additions(monkeypatch):
    from app.utils import discover_fun_scout as dfs
    from app.utils.roundup_containers import RoundupMembers

    staged = _staged_fixture(4)
    sealed_key = {
        "deck_date": "2026-11-26",
        "entries": {
            "s01": {
                "origin": "scout",
                "slug": staged["slug"],
                "name": staged["name"],
                "member_ids": [41, 42, 43],
                "rule_definition": staged["rule_definition"],
            }
        },
    }
    judgments = [
        {
            "market_name": "s01",
            "label": "Keep",
            "notes": "ship these 3",
            "label_metadata": {"deck_date": "2026-11-26", "item_id": "s01", "grade": "Keep"},
        }
    ]
    plan = plan_scout_promotions(judgments, sealed_key, deck_date="2026-11-26")
    promoted_def = plan["promote"][0]["definition"]
    assert promoted_def["scout"]["graded_member_ids"] == [41, 42, 43]
    promoted_def["rule"] = {
        "producer": "fun_scout_set",
        "min_numbered_members": 3,
        "card_rows": 4,
        "title_ilike": "%Anything%",
    }

    rows_by_id = {
        mid: SimpleNamespace(
            id=mid,
            status="open",
            volume=100.0 * mid,
            name=f"Graded {mid}",
            question=f"Graded {mid}?",
            category="culture",
            source="kalshi",
            outcomes=[SimpleNamespace(name="Yes", current_probability=0.45, probability_change_24h=0.0, rank=1)],
        )
        for mid in (41, 42, 43, 99, 88)
    }

    class _InspectDB:
        def __init__(self) -> None:
            self.sqls: list[str] = []

        async def execute(self, stmt):
            sql = str(stmt)
            self.sqls.append(sql)
            if "ILIKE" in sql.upper() or "LIKE" in sql.upper():
                out = [rows_by_id[41], rows_by_id[42], rows_by_id[43], rows_by_id[99], rows_by_id[88]]
            else:
                out = [rows_by_id[41], rows_by_id[42], rows_by_id[43]]
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: out))

    db_pinned = _InspectDB()
    producer_pinned = build_roundup_producer_from_definition(promoted_def)
    res_pinned = await producer_pinned.produce(db_pinned)
    assert isinstance(res_pinned, RoundupMembers)
    assert [m["id"] for m in res_pinned.members] == [41, 42, 43]
    assert not any("LIKE" in s.upper() for s in db_pinned.sqls)

    # allow_rule_additions fails closed when split-set gate is absent, and admits only gate-clean rows when present.
    def_with_additions = json.loads(json.dumps(promoted_def))
    def_with_additions["rule"]["allow_rule_additions"] = True
    producer_add = build_roundup_producer_from_definition(def_with_additions)

    monkeypatch.delattr(dfs, "detect_scout_split_set", raising=False)
    res_no_gate = await producer_add.produce(_InspectDB())
    assert [m["id"] for m in res_no_gate.members] == [41, 42, 43]

    class _Row:
        def __init__(self, market_id, title, category, source):
            self.market_id = market_id
            self.title = title

    monkeypatch.setattr(dfs, "ScoutMarketRow", _Row, raising=False)
    monkeypatch.setattr(
        dfs,
        "detect_scout_split_set",
        lambda _name, rows: SimpleNamespace(reason="split") if any(r.market_id == 99 for r in rows) else None,
        raising=False,
    )
    res_gated = await producer_add.produce(_InspectDB())
    assert [m["id"] for m in res_gated.members] == [41, 42, 43, 88]
