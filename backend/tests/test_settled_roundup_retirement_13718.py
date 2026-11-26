"""Tests for #13718: settled-means-settled round-up retirement, series_hub indexed query, and health breakdown."""

from __future__ import annotations

import copy
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from importlib import import_module
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from app.routes import health as health_route
from app.utils import roundup_containers as rc_mod
from app.utils import series_hub as sh_mod

pcp = import_module("app.tasks.precompute_category_pages")


class _CaptureSession:
    """AsyncSession stand-in that captures compiled SQL statements."""

    def __init__(self) -> None:
        self.sql_statements: list[str] = []

    async def execute(self, stmt: Any) -> Any:
        compiled = str(
            stmt.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        )
        self.sql_statements.append(compiled)
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: []))


def _register_test_producer(
    *,
    slug: str,
    rule: dict[str, Any],
    produce_fn: Any,
) -> rc_mod.RoundupProducer:
    return rc_mod.RoundupProducer(
        slug=slug,
        name="Test Settled Hub",
        kind="roundup",
        category="mlb",
        section_title="Series Outlook",
        footer="Test footer",
        rule=rule,
        produce=produce_fn,
        kicker="MLB",
        story_key=f"roundup:{slug}",
    )


@pytest.mark.asyncio
async def test_series_hub_loader_avoids_leading_wildcard_ilike_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Explicit series_market_ids skip ILIKE completely; series_code fallback uses anchored LIKE (#13718)."""
    from sqlalchemy.ext.asyncio import AsyncSession

    monkeypatch.setattr(sh_mod, "AsyncSession", _CaptureSession, raising=False)
    import sqlalchemy.ext.asyncio as sqla_ext

    monkeypatch.setattr(sqla_ext, "AsyncSession", _CaptureSession)

    async def _no_games(_db: Any, _ids: list[int]) -> tuple[dict, list]:
        return {}, []

    monkeypatch.setattr("app.routes.containers._hydrate_event_cards", _no_games)

    # 1. Explicit series_market_ids present (like mlb-2026-alwc-bos-nyy.json) -> zero ILIKE/LIKE.
    db_explicit = _CaptureSession()
    assert isinstance(db_explicit, AsyncSession) or True
    await sh_mod._load_series_hub_from_db(
        db_explicit,
        {
            "producer": "series_hub",
            "sport": "baseball_mlb",
            "series_code": "26BOSNYYWC",
            "event_ids": [15319563, 15321907],
            "series_market_ids": [62383730, 62455755, 62455756],
            "prop_market_ids": [63367383, 63398300],
            "path_market_ids": [],
        },
    )
    assert len(db_explicit.sql_statements) == 1
    sql_explicit = db_explicit.sql_statements[0]
    assert "ILIKE" not in sql_explicit.upper()
    assert "%26BOSNYYWC%" not in sql_explicit
    assert "62383730" in sql_explicit
    assert "15319563" in sql_explicit

    # 2. Only series_code given -> anchored KXMLBSERIES* LIKE prefixes, never leading '%'.
    db_code_only = _CaptureSession()
    await sh_mod._load_series_hub_from_db(
        db_code_only,
        {
            "producer": "series_hub",
            "sport": "baseball_mlb",
            "series_code": "26BOSNYYWC",
        },
    )
    assert len(db_code_only.sql_statements) == 1
    sql_code = db_code_only.sql_statements[0]
    assert "ILIKE" not in sql_code.upper()
    assert "LIKE '%" not in sql_code.upper()
    assert "KXMLBSERIES-26BOSNYYWC%" in sql_code
    assert "KXMLBSERIESSCORE-26BOSNYYWC%" in sql_code


@pytest.mark.asyncio
async def test_settled_retirement_skips_discover_and_keeps_collection_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fixed settled round-ups retire from Discover after 1st build while /collections/{slug} still serves (#13718)."""
    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")
    monkeypatch.setenv("CONTAINERS_READ_CACHE_ENABLED", "true")
    rc_mod.reset_roundup_cache_for_tests()
    now = datetime(2026, 11, 25, 9, 0, 0, tzinfo=timezone.utc)

    series_calls = 0
    generic_calls = 0

    def _produce_settled_series(_db: Any) -> rc_mod.RoundupMembers:
        nonlocal series_calls
        series_calls += 1
        return rc_mod.RoundupMembers(
            members=[
                {
                    "id": 15319563,
                    "type": "event",
                    "destination": {"href": "/events/15319563"},
                    "card": {
                        "id": 15319563,
                        "status": "completed",
                        "home_team": "New York Yankees",
                        "away_team": "Boston Red Sox",
                    },
                },
                {
                    "id": 62383730,
                    "type": "market",
                    "destination": {"href": "/futures/62383730"},
                    "card": {
                        "id": 62383730,
                        "status": "resolved",
                        "outcomes": [{"name": "Yankees", "probability": 1.0}],
                    },
                },
            ],
            rows=(),
            suppress_feed_item=True,
            footer="New York Yankees won series 2-0",
        )

    def _produce_generic_settled(_db: Any) -> rc_mod.RoundupMembers:
        nonlocal generic_calls
        generic_calls += 1
        return rc_mod.RoundupMembers(
            members=[
                {
                    "id": 9101,
                    "type": "market",
                    "destination": {"href": "/futures/9101"},
                    "card": {
                        "id": 9101,
                        "name": "Market A settled",
                        "status": "settled",
                        "top_outcome": "Yes",
                        "probability": 1.0,
                        "outcomes": [{"name": "Yes", "probability": 1.0}],
                    },
                },
                {
                    "id": 9102,
                    "type": "market",
                    "destination": {"href": "/futures/9102"},
                    "card": {
                        "id": 9102,
                        "name": "Market B settled",
                        "status": "final",
                        "top_outcome": "No",
                        "probability": 0.0,
                        "outcomes": [{"name": "No", "probability": 0.0}],
                    },
                },
            ],
            rows=[
                {"market_id": 9101, "label": "Market A", "probability": 1.0, "rendered_percent": 100},
                {"market_id": 9102, "label": "Market B", "probability": 0.0, "rendered_percent": 0},
            ],
            title="Settled Generic Set",
        )

    p_series = _register_test_producer(
        slug="mlb-2026-alwc-bos-nyy",
        rule={"producer": "series_hub", "series_market_ids": [62383730], "event_ids": [15319563]},
        produce_fn=_produce_settled_series,
    )
    p_generic = _register_test_producer(
        slug="settled-fixed-set",
        rule={"producer": "custom_fixed", "market_ids": [9101, 9102]},
        produce_fn=_produce_generic_settled,
    )
    monkeypatch.setattr(
        rc_mod,
        "ROUNDUP_PRODUCERS",
        {p_series.slug: p_series, p_generic.slug: p_generic},
    )
    monkeypatch.setattr(rc_mod, "ensure_optional_roundup_candidates", lambda: None)

    # First evaluate builds & retires both
    db = object()
    meta_s: dict[str, Any] = {}
    fi_s, cp_s = await rc_mod.evaluate_roundup_producer(p_series, db, now=now, outcome_meta=meta_s)
    assert fi_s is None and cp_s is not None
    assert meta_s["settled_retired"] is True
    assert meta_s["fixed_members"] is True
    assert meta_s["long_skip"] is True
    assert meta_s["reason"] == "all_members_settled"

    meta_g: dict[str, Any] = {}
    fi_g, cp_g = await rc_mod.evaluate_roundup_producer(p_generic, db, now=now, outcome_meta=meta_g)
    assert fi_g is None and cp_g is not None
    assert meta_g["settled_retired"] is True
    assert meta_g["fixed_members"] is True
    assert meta_g["long_skip"] is True
    assert meta_g["reason"] == "all_members_settled"

    # Reset counts for Discover stage test
    series_calls = 0
    generic_calls = 0
    base_items = [
        {"type": "futures", "score": 80 - i, "data": {"id": 5000 + i, "name": f"F{i}", "status": "open"}}
        for i in range(15)
    ]
    before = rc_mod.get_roundup_read_failure_stats_10m(now=now.timestamp())
    out = await rc_mod.add_roundup_feed_items(db, copy.deepcopy(base_items), now=now)
    after = rc_mod.get_roundup_read_failure_stats_10m(now=now.timestamp())

    # Neither settled set appeared on Discover and neither hit produce or dropped_no_copy!
    assert all(it.get("type") != "bundle" for it in out)
    assert series_calls == 0
    assert generic_calls == 0
    assert after == before

    # Direct set page (`serve_roundup`) STILL serves the settled results page!
    served_series = await rc_mod.serve_roundup("mlb-2026-alwc-bos-nyy", db, include_children=False, now=now)
    served_generic = await rc_mod.serve_roundup("settled-fixed-set", db, include_children=False, now=now)
    assert served_series["state"] == "published"
    assert served_generic["state"] == "published"
    assert series_calls == 0
    assert generic_calls == 0


@pytest.mark.asyncio
async def test_prewarm_standing_roundups_retires_and_skips_settled_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Standing prewarm stores settled_retired once (preserving container page) and skips DB on next pass (#13718)."""
    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")
    monkeypatch.setenv("CONTAINERS_READ_CACHE_ENABLED", "true")
    rc_mod.reset_roundup_cache_for_tests()

    kv: dict[str, tuple[str, int]] = {}
    hashes: dict[str, dict[str, str]] = {}

    fake_rc = MagicMock()
    fake_rc.set.side_effect = lambda k, v, ex=0: kv.__setitem__(k, (v, ex))
    fake_rc.get.side_effect = lambda k: kv[k][0] if k in kv else None
    fake_rc.ttl.side_effect = lambda k: kv[k][1] if k in kv else -2
    fake_rc.hset.side_effect = lambda k, f, v: hashes.setdefault(k, {}).__setitem__(f, v)
    fake_rc.hdel.side_effect = lambda k, f: hashes.setdefault(k, {}).pop(f, None)
    fake_rc.hgetall.side_effect = lambda k: dict(hashes.get(k, {}))
    fake_rc.exists.side_effect = lambda k: 1 if k in kv else 0

    produce_calls = 0

    def _produce_settled(_db: Any) -> rc_mod.RoundupMembers:
        nonlocal produce_calls
        produce_calls += 1
        return rc_mod.RoundupMembers(
            members=[
                {
                    "id": 15319563,
                    "type": "event",
                    "destination": {"href": "/events/15319563"},
                    "card": {"id": 15319563, "status": "completed"},
                },
                {
                    "id": 62383730,
                    "type": "market",
                    "destination": {"href": "/futures/62383730"},
                    "card": {"id": 62383730, "status": "resolved", "outcomes": [{"name": "NYY", "probability": 1.0}]},
                },
            ],
            rows=(),
            suppress_feed_item=True,
        )

    def _produce_active(_db: Any) -> rc_mod.RoundupMembers:
        return rc_mod.RoundupMembers(
            members=[
                {
                    "id": 8801,
                    "type": "market",
                    "destination": {"href": "/futures/8801"},
                    "card": {
                        "id": 8801,
                        "name": "Active 1",
                        "status": "open",
                        "outcomes": [{"name": "Yes", "probability": 0.6}],
                    },
                },
                {
                    "id": 8802,
                    "type": "market",
                    "destination": {"href": "/futures/8802"},
                    "card": {
                        "id": 8802,
                        "name": "Active 2",
                        "status": "open",
                        "outcomes": [{"name": "Yes", "probability": 0.4}],
                    },
                },
            ],
            rows=[
                {"market_id": 8801, "label": "Active 1", "probability": 0.6, "rendered_percent": 60},
                {"market_id": 8802, "label": "Active 2", "probability": 0.4, "rendered_percent": 40},
            ],
        )

    p_settled = _register_test_producer(
        slug="mlb-2026-alwc-bos-nyy",
        rule={"producer": "series_hub", "series_market_ids": [62383730], "event_ids": [15319563]},
        produce_fn=_produce_settled,
    )
    p_active = _register_test_producer(
        slug="roundup-active-open",
        rule={"producer": "field_leaders"},
        produce_fn=_produce_active,
    )
    monkeypatch.setattr(
        rc_mod,
        "ROUNDUP_PRODUCERS",
        {p_settled.slug: p_settled, p_active.slug: p_active},
    )

    db = object()

    @asynccontextmanager
    async def _fake_session(**_kw):
        yield db

    monkeypatch.setattr("app.tasks.base.get_task_session", _fake_session)

    res1 = await pcp._prewarm_standing_roundups(deadline_s=5.0, rc=fake_rc)
    assert produce_calls == 1
    assert res1["slugs"]["mlb-2026-alwc-bos-nyy"]["outcome"] == "settled_retired"
    assert res1["slugs"]["mlb-2026-alwc-bos-nyy"]["redis_written"] is True
    assert res1["slugs"]["roundup-active-open"]["outcome"] == "ok"
    assert "mlb-2026-alwc-bos-nyy" in hashes.get(rc_mod.STANDING_RETIRED_SLUGS_KEY, {})

    raw_cached = json.loads(kv[rc_mod._redis_cache_key(p_settled.slug)][0])
    assert raw_cached["feed_item"] is None
    assert raw_cached["container_payload"] is not None
    assert raw_cached["settled_retired"] is True
    assert raw_cached["clean_empty"] is True
    assert raw_cached["nothing_to_show"] is True

    # Second prewarm pass skips mlb-2026-alwc-bos-nyy with ZERO producer/DB calls!
    res2 = await pcp._prewarm_standing_roundups(deadline_s=5.0, rc=fake_rc)
    assert produce_calls == 1
    assert res2["slugs"]["mlb-2026-alwc-bos-nyy"]["outcome"] == "settled_retired"
    assert res2["slugs"]["mlb-2026-alwc-bos-nyy"]["elapsed_ms"] == 0.0


@pytest.mark.asyncio
async def test_roundup_with_any_open_member_is_not_retired(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A set with at least one open/scheduled member stays active on Discover (#13718)."""
    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")
    monkeypatch.setenv("CONTAINERS_READ_CACHE_ENABLED", "true")
    rc_mod.reset_roundup_cache_for_tests()
    now = datetime(2026, 11, 25, 9, 0, 0, tzinfo=timezone.utc)

    def _produce_mixed(_db: Any) -> rc_mod.RoundupMembers:
        return rc_mod.RoundupMembers(
            members=[
                {
                    "id": 9201,
                    "type": "event",
                    "destination": {"href": "/events/9201"},
                    "card": {"id": 9201, "status": "completed"},
                },
                {
                    "id": 9202,
                    "type": "event",
                    "destination": {"href": "/events/9202"},
                    "card": {"id": 9202, "status": "scheduled", "commence_time": "2026-11-26T00:00:00Z"},
                },
            ],
            rows=[
                {"market_id": 9202, "label": "Series Winner · Celtics", "probability": 0.55, "rendered_percent": 55},
                {"market_id": 9203, "label": "Exact Score · 2-0", "probability": 0.35, "rendered_percent": 35},
            ],
        )

    p_mixed = _register_test_producer(
        slug="live-series-mixed",
        rule={"producer": "series_hub", "series_market_ids": [9202, 9203], "event_ids": [9201, 9202]},
        produce_fn=_produce_mixed,
    )
    monkeypatch.setattr(rc_mod, "ROUNDUP_PRODUCERS", {p_mixed.slug: p_mixed})
    monkeypatch.setattr(rc_mod, "ensure_optional_roundup_candidates", lambda: None)

    async def _no_screen(_db: Any, produced: list, _now: Any, _cov: Any) -> list:
        return produced

    monkeypatch.setattr("app.utils.not_trading.drop_not_trading_roundup_members", _no_screen)

    base_items = [
        {"type": "futures", "score": 80 - i, "data": {"id": 6000 + i, "name": f"M{i}", "status": "open"}}
        for i in range(15)
    ]
    db = object()
    out = await rc_mod.add_roundup_feed_items(db, base_items, now=now)
    bundle_slugs = [
        (it.get("data") or {}).get("collection_ref", {}).get("slug")
        for it in out
        if it.get("type") == "bundle"
    ]
    assert bundle_slugs == ["live-series-mixed"]


@pytest.mark.asyncio
async def test_health_exposes_roundup_reads_10m_by_slug_without_breaking_aggregate_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`/api/health` keeps exact 5 aggregate keys on `roundup_reads_10m` and adds `roundup_reads_10m_by_slug` (#13718)."""
    rc_mod.reset_roundup_cache_for_tests()
    now_ts = datetime(2026, 11, 25, 9, 0, 0, tzinfo=timezone.utc).timestamp()

    rc_mod._record_roundup_read_failure(
        "mlb-2026-alwc-bos-nyy", kept_last_good=False, reason="timeout", now=now_ts
    )
    rc_mod._record_roundup_read_failure(
        "mlb-2026-alwc-bos-nyy", kept_last_good=False, reason="timeout", now=now_ts + 5
    )
    rc_mod._record_roundup_read_failure(
        "roundup-oscars-best-picture", kept_last_good=True, reason="budget_exhausted", now=now_ts + 6
    )

    breakdown = rc_mod.get_roundup_read_failure_breakdown_10m(now=now_ts + 10)
    assert list(breakdown.keys()) == ["mlb-2026-alwc-bos-nyy", "roundup-oscars-best-picture"]
    assert breakdown["mlb-2026-alwc-bos-nyy"]["dropped_no_copy"] == 2
    assert breakdown["mlb-2026-alwc-bos-nyy"]["last_reason"] == "timeout"
    assert breakdown["roundup-oscars-best-picture"]["kept_last_good"] == 1
    assert breakdown["roundup-oscars-best-picture"]["last_reason"] == "budget_exhausted"

    class _Conn:
        async def __aenter__(self) -> "_Conn":
            return self

        async def __aexit__(self, *args: Any) -> bool:
            return False

        async def execute(self, *_args: Any) -> None:
            return None

    class _FakeEngine:
        def connect(self) -> _Conn:
            return _Conn()

    fake_rc = MagicMock()
    fake_rc.ping.return_value = True
    monkeypatch.setattr("app.services.database.engine", _FakeEngine())
    monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda: fake_rc)
    monkeypatch.setattr(
        rc_mod,
        "get_roundup_read_failure_stats_10m",
        lambda: {
            "window_seconds": 600,
            "failed": 3,
            "kept_last_good": 1,
            "dropped_no_copy": 2,
            "had_nothing_to_show": 0,
        },
    )

    resp = await health_route.api_health_check()
    body = json.loads(resp.body.decode("utf-8"))
    assert set(body["roundup_reads_10m"].keys()) == {
        "window_seconds",
        "failed",
        "kept_last_good",
        "dropped_no_copy",
        "had_nothing_to_show",
    }
    assert "roundup_reads_10m_by_slug" in body


@pytest.mark.asyncio
async def test_all_settled_fixed_set_gets_24h_long_skip_and_retired_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Truly settled/resolved fixed sets (including settled_preserved) earn the 24h long skip."""
    import contextlib
    from datetime import datetime, timezone

    from app.tasks import precompute_category_pages as precompute_mod

    rc_mod.reset_roundup_cache_for_tests()
    calls = 0
    frozen_now = datetime(2026, 10, 5, 18, 0, tzinfo=timezone.utc)

    def _produce_settled(_db: Any) -> rc_mod.RoundupMembers:
        nonlocal calls
        calls += 1
        return rc_mod.RoundupMembers(
            members=[
                {
                    "id": 9301,
                    "type": "market",
                    "destination": {"href": "/futures/9301"},
                    "card": {
                        "id": 9301,
                        "name": "Market Resolved",
                        "status": "resolved",
                        "top_outcome": "Yes",
                        "probability": 1.0,
                        "outcomes": [{"name": "Yes", "probability": 1.0}],
                    },
                },
                {
                    "id": 9302,
                    "type": "market",
                    "destination": {"href": "/futures/9302"},
                    "card": {
                        "id": 9302,
                        "name": "Market Preserved",
                        "status": "closed",
                        "baseline_status": "settled_preserved",
                        "top_outcome": "No",
                        "probability": 0.0,
                        "outcomes": [{"name": "No", "probability": 0.0}],
                    },
                },
            ],
            rows=[
                {"market_id": 9301, "label": "Market Resolved", "probability": 1.0, "rendered_percent": 100},
                {"market_id": 9302, "label": "Market Preserved", "probability": 0.0, "rendered_percent": 0},
            ],
            title="Settled With Preserved Member",
        )

    kv: dict[str, tuple[str, int | None]] = {}
    hashes: dict[str, dict[str, str]] = {}

    class _SyncRedis:
        def get(self, key: str) -> str | None:
            item = kv.get(key)
            return item[0] if item else None

        def set(self, key: str, value: str, ex: int | None = None) -> bool:
            kv[key] = (value, ex)
            return True

        def ttl(self, key: str) -> int:
            item = kv.get(key)
            return int(item[1] or -1) if item else -2

        def hset(self, key: str, field: str, value: str) -> int:
            hashes.setdefault(key, {})[field] = value
            return 1

        def hdel(self, key: str, *fields: str) -> int:
            bucket = hashes.get(key, {})
            return sum(1 for f in fields if bucket.pop(f, None) is not None)

        def hgetall(self, key: str) -> dict[str, str]:
            return dict(hashes.get(key, {}))

        def expire(self, _key: str, _ttl: int) -> bool:
            return True

    fake_rc = _SyncRedis()
    p_settled = _register_test_producer(
        slug="settled-preserved-fixed",
        rule={"producer": "custom_fixed", "market_ids": [9301, 9302]},
        produce_fn=_produce_settled,
    )
    monkeypatch.setattr(rc_mod, "ROUNDUP_PRODUCERS", {p_settled.slug: p_settled})
    monkeypatch.setattr(rc_mod, "ensure_optional_roundup_candidates", lambda: None)
    monkeypatch.setattr("app.routes.containers.containers_read_enabled", lambda: True)
    db = object()
    monkeypatch.setattr(
        "app.tasks.base.get_task_session",
        lambda **_kw: contextlib.nullcontext(db),
    )
    monkeypatch.setattr("time.time", lambda: frozen_now.timestamp())

    res1 = await precompute_mod._prewarm_standing_roundups(rc=fake_rc)
    assert calls == 1
    assert res1["slugs"]["settled-preserved-fixed"]["outcome"] == "settled_retired"

    raw = json.loads(kv[rc_mod._redis_cache_key("settled-preserved-fixed")][0])
    assert raw["settled_retired"] is True
    assert raw["long_skip"] is True
    assert raw["nothing_to_show_reason"] == "all_members_settled"
    assert float(raw["ttl_s"]) == rc_mod.ROUNDUP_SETTLED_RETIRED_TTL_S
    assert "settled-preserved-fixed" in hashes.get(rc_mod.STANDING_RETIRED_SLUGS_KEY, {})

    res2 = await precompute_mod._prewarm_standing_roundups(rc=fake_rc)
    assert calls == 1
    assert res2["slugs"]["settled-preserved-fixed"]["outcome"] == "settled_retired"


@pytest.mark.asyncio
async def test_all_closed_without_result_keeps_short_ttl_and_no_retired_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Halted/closed sets without a result keep short cache TTL and never set the 24h skip marker."""
    import contextlib
    from datetime import datetime, timezone

    from app.tasks import precompute_category_pages as precompute_mod

    rc_mod.reset_roundup_cache_for_tests()
    calls = 0
    frozen_now = datetime(2026, 10, 5, 18, 0, tzinfo=timezone.utc)

    def _produce_closed(_db: Any) -> rc_mod.RoundupMembers:
        nonlocal calls
        calls += 1
        return rc_mod.RoundupMembers(
            members=[
                {
                    "id": 9401,
                    "type": "market",
                    "destination": {"href": "/futures/9401"},
                    "card": {
                        "id": 9401,
                        "name": "Halted Market A",
                        "status": "closed",
                        "top_outcome": "Yes",
                        "probability": 0.52,
                        "outcomes": [{"name": "Yes", "probability": 0.52}],
                    },
                },
                {
                    "id": 9402,
                    "type": "market",
                    "destination": {"href": "/futures/9402"},
                    "card": {
                        "id": 9402,
                        "name": "Settled Market B",
                        "status": "final",
                        "top_outcome": "No",
                        "probability": 0.0,
                        "outcomes": [{"name": "No", "probability": 0.0}],
                    },
                },
            ],
            rows=[
                {"market_id": 9401, "label": "Halted Market A", "probability": 0.52, "rendered_percent": 52},
                {"market_id": 9402, "label": "Settled Market B", "probability": 0.0, "rendered_percent": 0},
            ],
            title="Temporarily Closed Set",
        )

    kv: dict[str, tuple[str, int | None]] = {}
    hashes: dict[str, dict[str, str]] = {}

    class _SyncRedis:
        def get(self, key: str) -> str | None:
            item = kv.get(key)
            return item[0] if item else None

        def set(self, key: str, value: str, ex: int | None = None) -> bool:
            kv[key] = (value, ex)
            return True

        def ttl(self, key: str) -> int:
            item = kv.get(key)
            return int(item[1] or -1) if item else -2

        def hset(self, key: str, field: str, value: str) -> int:
            hashes.setdefault(key, {})[field] = value
            return 1

        def hdel(self, key: str, *fields: str) -> int:
            bucket = hashes.get(key, {})
            return sum(1 for f in fields if bucket.pop(f, None) is not None)

        def hgetall(self, key: str) -> dict[str, str]:
            return dict(hashes.get(key, {}))

        def expire(self, _key: str, _ttl: int) -> bool:
            return True

    fake_rc = _SyncRedis()
    p_closed = _register_test_producer(
        slug="closed-fixed-set",
        rule={"producer": "custom_fixed", "market_ids": [9401, 9402]},
        produce_fn=_produce_closed,
    )
    monkeypatch.setattr(rc_mod, "ROUNDUP_PRODUCERS", {p_closed.slug: p_closed})
    monkeypatch.setattr(rc_mod, "ensure_optional_roundup_candidates", lambda: None)

    db = object()
    meta: dict[str, Any] = {}
    fi, cp = await rc_mod.evaluate_roundup_producer(p_closed, db, now=frozen_now, outcome_meta=meta)
    assert fi is None and cp is not None
    assert meta["settled_retired"] is True
    assert meta["long_skip"] is False
    assert meta["reason"] == "all_members_closed"
    assert rc_mod._roundup_settled_retired_local == {}

    monkeypatch.setattr("app.routes.containers.containers_read_enabled", lambda: True)
    monkeypatch.setattr(
        "app.tasks.base.get_task_session",
        lambda **_kw: contextlib.nullcontext(db),
    )
    monkeypatch.setattr("time.time", lambda: frozen_now.timestamp())

    calls = 0
    await precompute_mod._prewarm_standing_roundups(rc=fake_rc)
    assert calls == 1
    raw = json.loads(kv[rc_mod._redis_cache_key("closed-fixed-set")][0])
    assert raw["settled_retired"] is True
    assert raw.get("long_skip") is not True
    assert raw["nothing_to_show_reason"] == "all_members_closed"
    assert float(raw["ttl_s"]) == rc_mod.ROUNDUP_CACHE_TTL_S
    assert "closed-fixed-set" not in hashes.get(rc_mod.STANDING_RETIRED_SLUGS_KEY, {})

    # Next standing prewarm pass must re-evaluate (NOT long-skipped).
    await precompute_mod._prewarm_standing_roundups(rc=fake_rc)
    assert calls == 2


@pytest.mark.asyncio
async def test_closed_set_recovers_on_reopen_after_short_ttl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When a closed-without-result set reopens after ROUNDUP_CACHE_TTL_S, Discover recovers it."""
    from datetime import datetime, timedelta, timezone

    rc_mod.reset_roundup_cache_for_tests()
    t0 = datetime(2026, 10, 5, 18, 0, tzinfo=timezone.utc)
    member_status = "closed"
    calls = 0

    def _produce(_db: Any) -> rc_mod.RoundupMembers:
        nonlocal calls
        calls += 1
        return rc_mod.RoundupMembers(
            members=[
                {
                    "id": 9501,
                    "type": "market",
                    "destination": {"href": "/futures/9501"},
                    "card": {
                        "id": 9501,
                        "name": "Resumable Market",
                        "status": member_status,
                        "top_outcome": "Yes",
                        "probability": 0.55,
                        "outcomes": [{"name": "Yes", "probability": 0.55}],
                    },
                },
                {
                    "id": 9502,
                    "type": "market",
                    "destination": {"href": "/futures/9502"},
                    "card": {
                        "id": 9502,
                        "name": "Closed Partner",
                        "status": "closed",
                        "top_outcome": "No",
                        "probability": 0.45,
                        "outcomes": [{"name": "No", "probability": 0.45}],
                    },
                },
            ],
            rows=[
                {"market_id": 9501, "label": "Resumable Market", "probability": 0.55, "rendered_percent": 55},
                {"market_id": 9502, "label": "Closed Partner", "probability": 0.45, "rendered_percent": 45},
            ],
            title="Reopenable Closed Set",
        )

    p = _register_test_producer(
        slug="reopenable-closed-set",
        rule={"producer": "custom_fixed", "market_ids": [9501, 9502]},
        produce_fn=_produce,
    )
    monkeypatch.setattr(rc_mod, "ROUNDUP_PRODUCERS", {p.slug: p})
    monkeypatch.setattr(rc_mod, "ensure_optional_roundup_candidates", lambda: None)
    monkeypatch.setattr("app.routes.containers.containers_read_enabled", lambda: True)

    db = object()
    fi0, cp0 = await rc_mod.evaluate_roundup_producer(p, db, now=t0)
    assert fi0 is None and cp0 is not None
    assert calls == 1

    # Within short TTL, cache keeps it hidden without hitting produce_fn.
    member_status = "open"
    fi_mid, _cp_mid = await rc_mod.evaluate_roundup_producer(
        p, db, now=t0 + timedelta(seconds=30)
    )
    assert fi_mid is None
    assert calls == 1

    # Right after ROUNDUP_CACHE_TTL_S expires, re-evaluation recovers the feed item.
    t_reopen = t0 + timedelta(seconds=rc_mod.ROUNDUP_CACHE_TTL_S + 1)
    fi_reopen, cp_reopen = await rc_mod.evaluate_roundup_producer(p, db, now=t_reopen)
    assert fi_reopen is not None and cp_reopen is not None
    assert calls == 2

    base_items = [
        {"type": "futures", "score": 80 - i, "data": {"id": 6200 + i, "name": f"M{i}", "status": "open"}}
        for i in range(12)
    ]
    out = await rc_mod.add_roundup_feed_items(db, base_items, now=t_reopen)
    bundles = [
        it
        for it in out
        if it.get("type") == "bundle"
        and ((it.get("data") or {}).get("collection_ref") or {}).get("slug")
        == "reopenable-closed-set"
    ]
    assert len(bundles) == 1


@pytest.mark.asyncio
async def test_series_hub_loader_normalizes_lowercase_series_code() -> None:
    """series_code anchored LIKE prefixes normalize lowercase/whitespace codes (#13718)."""
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.utils import series_hub as sh_mod

    seen_sql: list[str] = []

    class _EmptyRes:
        def fetchall(self) -> list[Any]:
            return []

        def scalars(self) -> Any:
            class _S:
                def all(self) -> list[Any]:
                    return []

            return _S()

    class _CaptureDB(AsyncSession):
        def __init__(self) -> None:
            pass

        async def execute(self, stmt: Any, *_args: Any, **_kwargs: Any) -> _EmptyRes:
            compiled = str(
                stmt.compile(
                    dialect=postgresql.dialect(),
                    compile_kwargs={"literal_binds": True},
                )
            )
            seen_sql.append(compiled)
            return _EmptyRes()

    await sh_mod._load_series_hub_from_db(
        _CaptureDB(),
        {"sport": "baseball_mlb", "series_code": " 26bosnyywc "},
    )
    joined = "\n".join(seen_sql)
    assert "KXMLBSERIES-26BOSNYYWC%" in joined
    assert "KXMLBSERIESSCORE-26BOSNYYWC%" in joined
    assert "KXMLBSERIESGAMES-26BOSNYYWC%" in joined
    assert "KXMLBSERIESSPREAD-26BOSNYYWC%" in joined
    assert "LIKE '%" not in joined
