"""Tests for #13102 (Ruling 276: B): Nightly Fun Scout model registry, code checks,
Decide 60-A / 61-A / 73-A / 32-C rule files, licence ramp, and spend caps.

No test makes a network call. All dates are frozen historical timestamps.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pytest

from app.services import llm_request
from app.services.llm_models import (
    CLAUDE_OPUS_MODEL,
    CLAUDE_SONNET_MODEL,
    LEGACY_MODEL,
    MODELS,
    REPLACEMENT_MODEL,
    estimate_cost_usd,
    resolve_model,
)
from app.services.llm_request import MemoryBudgetLedger
from app.utils.discover_fun_scout import (
    LICENCE_AUTO,
    LICENCE_SUSPENDED,
    SCOUT_ANTHROPIC_API_KEY_ENV,
    SCOUT_MONTHLY_CAP_USD,
    SCOUT_RUN_CAP_USD,
    FunScoutMissingKeyError,
    FunScoutSpendCapExceededError,
    ScoutLicenceState,
    ScoutMarketRow,
    ScoutProposedSet,
    ScoutUncoveredFamily,
    advance_scout_licence_clean_day,
    assert_fun_scout_within_caps,
    build_scout_anthropic_client,
    build_scout_rule_file_definition,
    check_scout_anthropic_key_status,
    check_scout_member,
    dedupe_cross_venue_members,
    estimate_fun_scout_spend,
    evaluate_scout_against_seed_sets,
    format_fun_scout_pre_run_spend_line,
    retire_scout_set,
    run_nightly_fun_scout,
    suspend_scout_licence_on_wrong_card,
    validate_scout_proposed_set,
    write_scout_rule_files,
)
from app.utils.discover_fun_tags import FunMarketEntry
from app.utils.roundup_containers import validate_roundup_definition

FROZEN_NOW = datetime(2025, 2, 15, 18, 0, tzinfo=timezone.utc)


def _mk(
    mid: int,
    title: str,
    *,
    source: str = "polymarket",
    status: str = "open",
    volume: float = 50_000.0,
    days_out: int = 60,
    canonical: str | None = None,
    category: str = "culture",
) -> ScoutMarketRow:
    return ScoutMarketRow(
        market_id=mid,
        source=source,
        title=title,
        status=status,
        category=category,
        resolution_date=FROZEN_NOW + timedelta(days=days_out),
        volume=volume,
        volume_24h=2_500.0,
        canonical_market_key=canonical,
    )


class TestClaudeModelRegistryAndKeys:
    def test_claude_models_registered_with_exact_nov_19_prices(self, monkeypatch):
        monkeypatch.delenv("LLM_MODEL", raising=False)
        monkeypatch.delenv("LLM_MODEL_FUN_SCOUT_SETS", raising=False)
        monkeypatch.delenv("LLM_MODEL_FUN_SCOUT_TAG", raising=False)

        assert MODELS[CLAUDE_SONNET_MODEL].provider == "anthropic"
        assert MODELS[CLAUDE_SONNET_MODEL].input_per_m == 2.0
        assert MODELS[CLAUDE_SONNET_MODEL].output_per_m == 10.0

        assert MODELS[CLAUDE_OPUS_MODEL].provider == "anthropic"
        assert MODELS[CLAUDE_OPUS_MODEL].input_per_m == 4.0
        assert MODELS[CLAUDE_OPUS_MODEL].output_per_m == 20.0

        assert resolve_model("fun_scout_tag") == LEGACY_MODEL
        assert resolve_model("fun_scout_sets") == CLAUDE_SONNET_MODEL

        # Global OpenAI migration override must NOT break Anthropic task
        monkeypatch.setenv("LLM_MODEL", REPLACEMENT_MODEL)
        assert resolve_model("fun_scout_tag") == REPLACEMENT_MODEL
        assert resolve_model("fun_scout_sets") == CLAUDE_SONNET_MODEL

        # Task-scoped override switches cleanly to Opus
        monkeypatch.setenv("LLM_MODEL_FUN_SCOUT_SETS", CLAUDE_OPUS_MODEL)
        assert resolve_model("fun_scout_sets") == CLAUDE_OPUS_MODEL

    def test_anthropic_usage_cost_estimation(self):
        usage = SimpleNamespace(input_tokens=50_000, output_tokens=4_000)
        assert estimate_cost_usd(CLAUDE_SONNET_MODEL, usage) == pytest.approx(
            (50_000 * 2.0 + 4_000 * 10.0) / 1_000_000
        )
        assert estimate_cost_usd(CLAUDE_OPUS_MODEL, usage) == pytest.approx(
            (50_000 * 4.0 + 4_000 * 20.0) / 1_000_000
        )

    def test_key_reads_only_scout_var_and_never_exposes_value(self, monkeypatch):
        monkeypatch.delenv(SCOUT_ANTHROPIC_API_KEY_ENV, raising=False)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-wrong-shared-key")

        status = check_scout_anthropic_key_status()
        assert status == {"env": SCOUT_ANTHROPIC_API_KEY_ENV, "is_set": False, "length": 0}
        with pytest.raises(FunScoutMissingKeyError):
            build_scout_anthropic_client()

        secret = "sk-ant-scout-unit-test-placeholder-key"
        monkeypatch.setenv(SCOUT_ANTHROPIC_API_KEY_ENV, secret)
        status_set = check_scout_anthropic_key_status()
        assert status_set == {
            "env": SCOUT_ANTHROPIC_API_KEY_ENV,
            "is_set": True,
            "length": len(secret),
        }
        assert secret not in json.dumps(status_set)


class TestSpendCapsAndPreRunPrint:
    def test_nightly_4400_titles_under_40_cents_on_sonnet(self, monkeypatch):
        monkeypatch.delenv("LLM_MODEL", raising=False)
        monkeypatch.delenv("LLM_MODEL_FUN_SCOUT_SETS", raising=False)
        monkeypatch.delenv("LLM_MODEL_FUN_SCOUT_TAG", raising=False)

        est = estimate_fun_scout_spend(4400)
        assert est["tag_cost_usd"] < 0.05
        assert est["estimated_run_cost_usd"] < 0.40
        assert est["within_caps"] is True

        line = format_fun_scout_pre_run_spend_line(est)
        assert "[discover-fun-scout]" in line
        assert f"cap=${SCOUT_RUN_CAP_USD:.2f}" in line
        assert f"cap=${SCOUT_MONTHLY_CAP_USD:.2f}" in line

    def test_run_and_monthly_caps_fail_closed(self):
        over_run = estimate_fun_scout_spend(
            4400,
            set_model=CLAUDE_OPUS_MODEL,
            set_input_tokens=2_000_000,
        )
        assert over_run["within_caps"] is False
        with pytest.raises(FunScoutSpendCapExceededError):
            assert_fun_scout_within_caps(over_run)

        over_month = estimate_fun_scout_spend(
            4400,
            prior_monthly_spend_usd=29.99,
        )
        assert over_month["within_caps"] is False
        with pytest.raises(FunScoutSpendCapExceededError):
            assert_fun_scout_within_caps(over_month)


class TestCodeEnforcedChecks:
    def test_member_checks_enforce_open_volume_taste_and_ahead(self):
        assert check_scout_member(None, now=FROZEN_NOW) == (False, "market_missing")
        assert check_scout_member(_mk(1, "Will GTA VI ship?", status="closed"), now=FROZEN_NOW)[0] is False
        assert check_scout_member(_mk(2, "Will GTA VI ship?", volume=500.0), now=FROZEN_NOW)[0] is False
        # Taste guard (273: B): blocks health/divorce/pregnancy/nukes, ALLOWS engagements
        assert check_scout_member(_mk(3, "Will Taylor Swift divorce in 2025?"), now=FROZEN_NOW)[0] is False
        assert check_scout_member(_mk(4, "Will Zendaya be pregnant in 2025?"), now=FROZEN_NOW)[0] is False
        assert check_scout_member(_mk(5, "Nuclear weapon detonated before 2026?"), now=FROZEN_NOW)[0] is False
        assert check_scout_member(_mk(6, "Will Zendaya get engaged in 2025?"), now=FROZEN_NOW) == (True, None)
        # Past-dated event refused
        assert check_scout_member(_mk(7, "Past snow event", days_out=-3), now=FROZEN_NOW)[0] is False

    def test_cross_venue_dedup_keeps_higher_volume_row(self):
        kalshi = _mk(10, "Will the U.S. confirm aliens exist?", source="kalshi", volume=40_000, canonical="aliens:2025")
        poly = _mk(11, "Will the U.S. confirm aliens exist?", source="polymarket", volume=95_000, canonical="aliens:2025")
        other = _mk(12, "Is Earth flat?", source="polymarket", volume=20_000)

        kept, deduped = dedupe_cross_venue_members([kalshi, poly, other])
        assert [m.market_id for m in kept] == [11, 12]
        assert deduped == [(10, 11)]

    def test_set_requires_three_live_distinct_members_and_refuses_retired(self):
        catalog = {
            1: _mk(1, "Will GTA VI ship in 2025?", source="polymarket", volume=80_000, canonical="gta6"),
            2: _mk(2, "Will GTA VI ship in 2025?", source="kalshi", volume=30_000, canonical="gta6"),
            3: _mk(3, "Will Winds of Winter release in 2025?", volume=60_000),
            4: _mk(4, "Will Half-Life 3 be announced in 2025?", volume=45_000),
            5: _mk(5, "Will thin market happen?", volume=100.0),
        }
        # Only 2 surviving after cross-venue dedup + thin drop -> rejected
        too_small = ScoutProposedSet(
            slug="will-it-ever-come-out",
            name="Will it ever come out?",
            kicker="LONG WAIT",
            category="culture",
            why_better_together="Three delayed cultural releases side by side.",
            look="bars",
            member_ids=(1, 2, 3, 5),
        )
        vset, err = validate_scout_proposed_set(too_small, catalog, now=FROZEN_NOW)
        assert vset is None
        assert err == "too_few_live_members:2<3"

        # 3 distinct live members -> accepted
        valid_prop = ScoutProposedSet(
            slug="will-it-ever-come-out",
            name="Will it ever come out?",
            kicker="LONG WAIT",
            category="culture",
            why_better_together="Three delayed cultural releases side by side.",
            look="bars",
            member_ids=(1, 2, 3, 4, 5),
        )
        vset, err = validate_scout_proposed_set(valid_prop, catalog, now=FROZEN_NOW)
        assert err is None and vset is not None
        assert len(vset.members) == 3
        assert vset.deduped_members == ((2, 1),)
        assert vset.dropped_members[0][0] == 5

        # Retired set is refused
        retired = retire_scout_set(
            [],
            slug="will-it-ever-come-out",
            name="Will it ever come out?",
            reason="Alex graded down",
            retired_at=FROZEN_NOW,
        )
        vset_ret, err_ret = validate_scout_proposed_set(
            valid_prop,
            catalog,
            retired_slugs=frozenset(r["slug"] for r in retired),
            now=FROZEN_NOW,
        )
        assert vset_ret is None and err_ret == "retired_set:will-it-ever-come-out"


class TestRuleFilesLicenceAndEndToEnd:
    def test_rule_file_uses_selector_and_validates_under_60a_73a(self, tmp_path):
        catalog = {
            1: _mk(1, "White Christmas in New York?"),
            2: _mk(2, "White Christmas in Chicago?"),
            3: _mk(3, "White Christmas in Boston?"),
            4: _mk(4, "Will Taylor Swift headline?"),
            5: _mk(5, "Will Beyonce tour?"),
            6: _mk(6, "Will Drake drop an album?"),
            7: _mk(7, "Third set row 1"),
            8: _mk(8, "Third set row 2"),
            9: _mk(9, "Third set row 3"),
        }
        vsets = []
        for idx, (slug, name, look, mids) in enumerate(
            [
                ("white-christmas", "White Christmas", "map", (1, 2, 3)),
                ("pop-stars-2025", "Pop Stars in 2025", "faces", (4, 5, 6)),
                ("third-set-capped", "Third Set", "bars", (7, 8, 9)),
            ]
        ):
            v, err = validate_scout_proposed_set(
                ScoutProposedSet(
                    slug=slug,
                    name=name,
                    kicker="FUN",
                    category="culture",
                    why_better_together="Better side by side.",
                    look=look,
                    member_ids=mids,
                ),
                catalog,
                now=FROZEN_NOW,
            )
            assert err is None and v is not None
            vsets.append(v)

        # Definition passes validate_roundup_definition and carries fun_tag selector (73-A)
        faces_def = build_scout_rule_file_definition(
            vsets[1], model_used=CLAUDE_SONNET_MODEL, created_at=FROZEN_NOW
        )
        assert validate_roundup_definition(faces_def)["rule"]["selector"] == {"fun_tag": "pop-stars-2025"}
        assert faces_def["image_credit_required"] is True  # 195-A
        assert faces_def["novelty_seat"] is True  # 32-C
        assert faces_def["scout"]["requires_fable_look"] is True

        # Max 2 new sets written per day
        lic = ScoutLicenceState()
        written = write_scout_rule_files(
            vsets, tmp_path, model_used=CLAUDE_SONNET_MODEL, created_at=FROZEN_NOW, licence_state=lic
        )
        assert len(written) == 2

        # 7 clean days earn auto licence; 1 wrong card suspends immediately
        for day in range(1, 8):
            advance_scout_licence_clean_day(lic, f"2025-02-{day:02d}")
        assert lic.status == LICENCE_AUTO
        suspend_scout_licence_on_wrong_card(
            lic, slug="white-christmas", reason="served resolved row", at=FROZEN_NOW
        )
        assert lic.status == LICENCE_SUSPENDED
        assert (
            write_scout_rule_files(
                vsets,
                tmp_path / "suspended",
                model_used=CLAUDE_SONNET_MODEL,
                created_at=FROZEN_NOW,
                licence_state=lic,
            )
            == []
        )

    def test_end_to_end_pipeline_routes_through_request_layer_and_evaluates_benchmark(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.delenv("LLM_MODEL", raising=False)
        monkeypatch.delenv("LLM_MODEL_FUN_SCOUT_SETS", raising=False)
        monkeypatch.delenv("LLM_MODEL_FUN_SCOUT_TAG", raising=False)
        llm_request.set_ledger(MemoryBudgetLedger())

        catalog = [
            _mk(101, "Will GTA VI release before 2026?"),
            _mk(102, "Will Winds of Winter release before 2026?"),
            _mk(103, "Will Hollow Knight Silksong release before 2026?"),
            _mk(104, "Will the U.S. confirm aliens exist?"),
        ]

        openai_calls = []

        class _FakeOpenAI:
            class _Chat:
                class _Completions:
                    def create(self, **kwargs):
                        openai_calls.append(kwargs)
                        body = json.dumps(
                            {
                                "tagged": [
                                    {"market_id": 101, "fun_group": "vaporware", "is_fun_single": False, "set_hint": "will-it-ever-come-out", "reason": "long wait"},
                                    {"market_id": 102, "fun_group": "vaporware", "is_fun_single": False, "set_hint": "will-it-ever-come-out", "reason": "long wait"},
                                    {"market_id": 103, "fun_group": "vaporware", "is_fun_single": False, "set_hint": "will-it-ever-come-out", "reason": "long wait"},
                                    {"market_id": 104, "fun_group": "aliens", "is_fun_single": True, "set_hint": None, "reason": "water cooler"},
                                ]
                            }
                        )
                        return SimpleNamespace(
                            choices=[SimpleNamespace(message=SimpleNamespace(content=body))],
                            usage=SimpleNamespace(prompt_tokens=400, completion_tokens=120),
                        )

                completions = _Completions()

            chat = _Chat()

        anthropic_calls = []

        class _FakeAnthropic:
            class _Messages:
                def create(self, **kwargs):
                    anthropic_calls.append(kwargs)
                    body = json.dumps(
                        {
                            "sets": [
                                {
                                    "slug": "will-it-ever-come-out",
                                    "name": "Will it ever come out?",
                                    "kicker": "LONG WAIT",
                                    "category": "culture",
                                    "why_better_together": "Three famous delayed releases side by side.",
                                    "look": "bars",
                                    "selector_kind": "fun_tag",
                                    "member_ids": [101, 102, 103],
                                }
                            ]
                        }
                    )
                    return SimpleNamespace(
                        content=[SimpleNamespace(text=body)],
                        usage=SimpleNamespace(input_tokens=1200, output_tokens=250),
                    )

            messages = _Messages()

        result = run_nightly_fun_scout(
            catalog,
            [ScoutUncoveredFamily("vaporware", "Will GTA VI release?", 6)],
            openai_client=_FakeOpenAI(),
            anthropic_client=_FakeAnthropic(),
            output_dir=tmp_path / "rules",
            now=FROZEN_NOW,
        )

        assert len(openai_calls) == 1 and openai_calls[0]["model"] == LEGACY_MODEL
        assert len(anthropic_calls) == 1 and anthropic_calls[0]["model"] == CLAUDE_SONNET_MODEL
        assert "system" in anthropic_calls[0]
        assert "temperature" not in anthropic_calls[0]
        assert "top_p" not in anthropic_calls[0]
        assert "top_k" not in anthropic_calls[0]
        assert result["actual_total_cost_usd"] > 0
        assert len(result["validated_sets"]) == 1
        assert len(result["verified_singles"]) == 1
        assert result["verified_singles"][0]["market_id"] == 104
        assert len(result["written_rule_files"]) == 1

        seed = {
            101: FunMarketEntry(101, "GTA VI", ("vaporware",), "odd", "culture"),
            102: FunMarketEntry(102, "Winds of Winter", ("vaporware",), "odd", "culture"),
            103: FunMarketEntry(103, "Silksong", ("vaporware",), "odd", "culture"),
        }
        bench = evaluate_scout_against_seed_sets(result["validated_sets"], seed)
        assert bench["matched_seed_count"] == 1
        assert bench["matched_seed_groups"][0]["recall"] == 1.0


class TestScoutDurabilityPreFlip13124:
    """Covers Fable's 3 pre-flip durability items on #13124 + real database import."""

    def test_task_module_imports_real_database_session_maker(self):
        import importlib

        from app.services.database import async_session_maker

        scout_task = importlib.import_module("app.tasks.discover_fun_scout")
        assert scout_task.async_session_maker is async_session_maker

    @pytest.mark.asyncio
    async def test_nightly_run_persists_full_sets_singles_and_spend_to_redis_and_github(
        self, tmp_path, monkeypatch
    ):
        import importlib
        from unittest.mock import AsyncMock, MagicMock

        scout_task = importlib.import_module("app.tasks.discover_fun_scout")
        from app.utils.discover_fun_scout import ScoutValidatedSet

        store: dict[str, Any] = {}

        class _FakeRedis:
            def get(self, key):
                return store.get(key)

            def set(self, key, val, ex=None):
                store[key] = val

            def incrbyfloat(self, key, delta):
                cur = float(store.get(key, 0.0))
                store[key] = str(cur + float(delta))
                return float(store[key])

            def expire(self, key, ttl):
                return True

        fake_redis = _FakeRedis()
        monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda: fake_redis)
        monkeypatch.setattr(scout_task, "_UNRECORDED_SPEND_MONTHS", set())
        monkeypatch.setenv("GITHUB_TOKEN", "test-scout-publish-token-value")

        posted: list[dict[str, Any]] = []

        def _fake_post(url, headers=None, json=None, timeout=None):
            posted.append({"url": url, "body": (json or {}).get("body", "")})
            resp = MagicMock()
            resp.status_code = 201
            resp.json.return_value = {
                "html_url": "https://github.com/alexander-bain/bainluck/issues/13102#issuecomment-999"
            }
            return resp

        monkeypatch.setattr(scout_task.httpx, "post", _fake_post)

        members = (
            ScoutMarketRow(
                market_id=101,
                source="kalshi",
                title="Will GTA VI release in 2026?",
                status="open",
                category="culture",
                volume=50000,
            ),
            ScoutMarketRow(
                market_id=102,
                source="polymarket",
                title="Will Winds of Winter release?",
                status="open",
                category="culture",
                volume=40000,
            ),
            ScoutMarketRow(
                market_id=103,
                source="kalshi",
                title="Will Half-Life 3 be announced?",
                status="open",
                category="culture",
                volume=30000,
            ),
        )
        vset = ScoutValidatedSet(
            slug="long-awaited-releases",
            name="Long-awaited releases",
            kicker="Waiting",
            category="culture",
            why_better_together="Three delayed cultural releases.",
            look="bars",
            members=members,
            selector_kind="fun_tag",
            title_ilike=None,
            template=None,
            footer="Updated nightly",
        )
        fake_result = {
            "spend_line": "fun-scout pre-run: 3424 titles est=$0.09",
            "actual_total_cost_usd": 0.11,
            "set_model": CLAUDE_SONNET_MODEL,
            "tagged_count": 4,
            "verified_singles": [
                {
                    "market_id": 104,
                    "title": "Will Costco raise hot dog price?",
                    "fun_group": "food",
                    "reason": "classic odd market",
                }
            ],
            "validated_sets": [vset],
            "rejected_sets": [{"slug": "bad-set", "reason": "too_few_members"}],
            "written_rule_files": [],
            "licence_state": {"status": "awaiting_look", "clean_days": 1},
        }
        monkeypatch.setattr(
            scout_task, "fetch_open_non_sports_markets_for_scout", AsyncMock(return_value=list(members))
        )
        monkeypatch.setattr(scout_task, "build_scout_openai_client", lambda: object())
        monkeypatch.setattr(scout_task, "build_scout_anthropic_client", lambda: object())
        monkeypatch.setattr(scout_task, "run_nightly_fun_scout", lambda *a, **kw: fake_result)

        out = await scout_task._run_discover_fun_scout(
            force=True, output_dir=tmp_path, now=FROZEN_NOW
        )

        assert out["status"] == "completed"
        assert out["monthly_ledger_recorded"] is True
        assert out["redis_artifact_saved"] is True
        assert out["verified_single_count"] == 1
        assert out["verified_singles"][0]["market_id"] == 104
        assert len(out["staged_sets"]) == 1
        assert out["staged_sets"][0]["rule_definition"]["slug"] == "long-awaited-releases"
        assert out["github_comment_url"].endswith("#issuecomment-999")

        # Redis durable snapshot holds full staged sets, singles, and spend
        assert "bainluck:fun_scout:latest" in store
        saved_json = json.loads(store["bainluck:fun_scout:latest"])
        assert saved_json["staged_sets"][0]["slug"] == "long-awaited-releases"
        assert saved_json["verified_singles"][0]["market_id"] == 104

        # GitHub comment on #13102 carries staged sets in full, verified singles, and spend
        assert len(posted) == 1
        assert "/issues/13102/comments" in posted[0]["url"]
        body = posted[0]["body"]
        assert "long-awaited-releases" in body
        assert "Will Costco raise hot dog price?" in body
        assert "fun-scout pre-run: 3424 titles est=$0.09" in body
        assert "test-scout-publish-token-value" not in body

    def test_durable_licence_state_and_retired_sets_persist_in_redis_and_fail_closed(
        self, tmp_path, monkeypatch
    ):
        import importlib

        scout_task = importlib.import_module("app.tasks.discover_fun_scout")
        from app.utils.discover_fun_scout import (
            LICENCE_AUTO,
            LICENCE_AWAITING_LOOK,
            ScoutLicenceState,
        )

        store: dict[str, Any] = {}

        class _FakeRedis:
            def get(self, key):
                return store.get(key)

            def set(self, key, val, ex=None):
                store[key] = val

        monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda: _FakeRedis())

        ok, err = scout_task.save_licence_state_durable(
            ScoutLicenceState(status=LICENCE_AUTO, clean_days=7, last_clean_day="2025-05-01")
        )
        assert ok is True and err is None
        loaded = scout_task._load_licence_state(tmp_path / "missing.json")
        assert loaded.status == LICENCE_AUTO
        assert loaded.clean_days == 7

        ok_r, err_r = scout_task.retire_scout_set_durable("old-retired-slug")
        assert ok_r is True and err_r is None
        retired = scout_task._load_retired_sets_durable(tmp_path / "missing_retired.json")
        assert "old-retired-slug" in retired

        # If Redis fails, licence falls back safely to awaiting_look (0 clean days)
        # and retired sets fail closed (raise).
        def _broken_redis():
            raise RuntimeError("redis down")

        monkeypatch.setattr("app.tasks.redis_state.get_redis_client", _broken_redis)
        fallback = scout_task._load_licence_state(tmp_path / "missing.json")
        assert fallback.status == LICENCE_AWAITING_LOOK
        assert fallback.clean_days == 0
        with pytest.raises(RuntimeError, match="redis down"):
            scout_task._load_retired_sets_durable(tmp_path / "missing_retired.json")

    @pytest.mark.asyncio
    async def test_failed_monthly_ledger_write_marks_month_unknown_and_closes_next_run(
        self, tmp_path, monkeypatch
    ):
        import importlib
        from unittest.mock import AsyncMock

        scout_task = importlib.import_module("app.tasks.discover_fun_scout")

        store: dict[str, Any] = {}

        class _FailingSpendRedis:
            def get(self, key):
                return store.get(key)

            def set(self, key, val, ex=None):
                store[key] = val

            def incrbyfloat(self, key, delta):
                raise RuntimeError("write timeout")

            def expire(self, key, ttl):
                return True

        monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda: _FailingSpendRedis())
        monkeypatch.setattr(scout_task, "_UNRECORDED_SPEND_MONTHS", set())
        monkeypatch.setattr(
            scout_task, "fetch_open_non_sports_markets_for_scout", AsyncMock(return_value=[])
        )
        monkeypatch.setattr(scout_task, "build_scout_openai_client", lambda: object())
        monkeypatch.setattr(scout_task, "build_scout_anthropic_client", lambda: object())
        monkeypatch.setattr(
            scout_task,
            "run_nightly_fun_scout",
            lambda *a, **kw: {
                "spend_line": "est=$0.10",
                "actual_total_cost_usd": 0.12,
                "set_model": CLAUDE_SONNET_MODEL,
                "tagged_count": 0,
                "verified_singles": [],
                "validated_sets": [],
                "rejected_sets": [],
                "written_rule_files": [],
                "licence_state": {"status": "awaiting_look", "clean_days": 0},
            },
        )

        out = await scout_task._run_discover_fun_scout(
            force=True, output_dir=tmp_path, now=FROZEN_NOW, publish_to_github=False
        )
        assert out["status"] == "completed_ledger_write_failed"
        assert out["monthly_ledger_recorded"] is False
        assert "write timeout" in (out["monthly_ledger_error"] or "")

        # Next run's spend check MUST fail closed (inf) even after clearing in-process state
        month_key = FROZEN_NOW.strftime("%Y-%m")
        scout_task._UNRECORDED_SPEND_MONTHS.clear()
        assert scout_task._read_monthly_spend_usd(month_key) == float("inf")

    def test_scout_comment_escapes_mentions_issue_refs_pipes_and_backticks(self):
        import importlib
        import re

        scout_task = importlib.import_module("app.tasks.discover_fun_scout")

        tricky_title = "Will @octocat | #12345 win `Best` \nShow?"
        artifact = {
            "run_date": "2025-05-01",
            "run_at": "2025-05-01T09:30:00+00:00",
            "spend_line": "fun-scout pre-run: 3424 titles est=$0.09",
            "actual_total_cost_usd": 0.11,
            "set_model": CLAUDE_SONNET_MODEL,
            "licence_state": {"status": "awaiting_look", "clean_days": 0},
            "monthly_ledger_recorded": True,
            "staged_sets": [
                {
                    "slug": "tricky-set",
                    "name": "Who beats @octocat on #12345?",
                    "kicker": "Watch @octocat | #12345",
                    "category": "entertainment",
                    "why_better_together": "Links @octocat & #12345 in `one` place",
                    "look": "bars",
                    "members": [
                        {
                            "market_id": 501,
                            "source": "polymarket",
                            "title": tricky_title,
                            "volume": 25000,
                            "category": "entertainment",
                        }
                    ],
                    "rule_definition": {
                        "slug": "tricky-set",
                        "note": "contains ```triple``` fence and @octocat #12345",
                    },
                }
            ],
            "verified_singles": [
                {
                    "market_id": 502,
                    "fun_group": "pop-culture",
                    "title": tricky_title,
                    "reason": "Mentions @octocat | refs #12345 and `ticks`",
                }
            ],
            "rejected_sets": [{"slug": "bad", "reason": "@octocat #12345"}],
        }

        body = scout_task.format_scout_nightly_comment_markdown(artifact)

        # Every singles table row keeps exactly 4 columns (5 unescaped pipes)
        table_rows = [
            line for line in body.splitlines() if line.startswith("| `502`")
        ]
        assert len(table_rows) == 1
        row = table_rows[0]
        assert r"\|" in row
        assert len(re.findall(r"(?<!\\)\|", row)) == 5

        # Fenced JSON block upgrades to 4+ backticks when JSON contains ```
        assert "````json" in body

        # Strip fenced code blocks and inline code spans: zero raw @mentions or #12345 remain
        stripped = re.sub(r"(`{3,})[^\n]*\n.*?\n\1", "", body, flags=re.DOTALL)
        # Strip inline multi- and single-backtick code spans
        stripped = re.sub(r"(`+)(?:(?!\1).)*\1", "", stripped)
        assert "@octocat" not in stripped
        assert "#12345" not in stripped

    def test_scout_comment_caps_body_under_github_limit_at_1000_singles(self):
        import importlib
        import re

        scout_task = importlib.import_module("app.tasks.discover_fun_scout")

        staged_sets = [
            {
                "slug": f"staged-set-{i}",
                "name": f"Staged Set Number {i}",
                "kicker": "Curated fun set",
                "category": "culture",
                "why_better_together": "Three related markets with clear contrast.",
                "look": "bars",
                "members": [
                    {
                        "market_id": 1000 + i * 10 + j,
                        "source": "polymarket",
                        "title": f"Staged set {i} member {j} market title",
                        "volume": 50000,
                        "category": "culture",
                    }
                    for j in range(3)
                ],
                "rule_definition": {
                    "slug": f"staged-set-{i}",
                    "name": f"Staged Set Number {i}",
                    "members": [1000 + i * 10 + j for j in range(3)],
                },
            }
            for i in range(1, 3)
        ]
        singles = [
            {
                "market_id": 10_000 + i,
                "fun_group": "pop-culture",
                "title": f"Will quirky event number {i:04d} happen before the end of 2027?",
                "reason": f"High-interest non-sports market candidate #{i:04d} with strong volume.",
            }
            for i in range(1000)
        ]
        artifact = {
            "run_date": "2025-05-01",
            "run_at": "2025-05-01T09:30:00+00:00",
            "spend_line": "fun-scout pre-run: 3424 titles est=$0.09",
            "actual_total_cost_usd": 0.14,
            "set_model": CLAUDE_SONNET_MODEL,
            "licence_state": {"status": "awaiting_look", "clean_days": 2},
            "monthly_ledger_recorded": True,
            "staged_sets": staged_sets,
            "verified_singles": singles,
            "rejected_sets": [{"slug": "rejected-1", "reason": "too_few_members"}],
        }

        body = scout_task.format_scout_nightly_comment_markdown(artifact)

        assert len(body) <= 65_536
        assert len(body) <= scout_task.SCOUT_GITHUB_COMMENT_MAX_CHARS
        # Header, spend line, and both staged sets (with rule JSON) stay whole
        assert "fun-scout pre-run: 3424 titles est=$0.09" in body
        assert "staged-set-1" in body and "staged-set-2" in body
        assert '"members": [' in body
        # Singles table is truncated cleanly with an explicit "first N of 1000" line
        m = re.search(r"Showing first (\d+) of 1000 verified singles", body)
        assert m is not None
        shown = int(m.group(1))
        assert 0 < shown < 1000


class TestFrozenBenchmarkInput:
    """#13102: Frozen Nov 19 benchmark input and fail-closed dry-run safety."""

    def test_frozen_benchmark_fixture_loads_and_dry_runs_without_api_calls(
        self, monkeypatch
    ):
        from scripts import run_fun_scout_benchmark_13102 as bench

        def _forbid(*_a, **_k):
            raise AssertionError("Paid model client must never be built in dry-run")

        monkeypatch.setattr(bench, "build_scout_openai_client", _forbid)
        monkeypatch.setattr(bench, "build_scout_anthropic_client", _forbid)

        assert bench.DEFAULT_BENCHMARK_FIXTURE.is_file()
        summary = bench.summarize_fixture_dry_run(
            bench.DEFAULT_BENCHMARK_FIXTURE,
            models=[CLAUDE_SONNET_MODEL, CLAUDE_OPUS_MODEL],
        )
        assert summary["total_markets"] == 3424
        assert summary["passing_code_checks"] > 3000
        assert summary["passing_by_source"]["kalshi"] > 1000
        assert summary["passing_by_source"]["polymarket"] > 1000
        assert summary["seed_markets_present"] >= 80
        assert 0.0 < summary["combined_est_usd"] < 1.0

        # Calling main with --dry-run OR without --execute stays zero-cost.
        assert bench.main(["--dry-run"]) == 0
        assert bench.main([]) == 0

    def test_anthropic_payload_omits_sampling_kwargs_and_binds_real_sdk_signature(
        self, monkeypatch
    ):
        """Regression guard for #13102: Anthropic SDK v2.x removed temperature/top_p/top_k."""
        import inspect

        import anthropic.resources.messages as anthropic_messages

        payload = llm_request._anthropic_payload(
            request={
                "model": CLAUDE_SONNET_MODEL,
                "max_tokens": 8000,
                "temperature": 0.3,
            },
            messages=[
                {"role": "system", "content": "You are the Fun Scout."},
                {"role": "user", "content": "Build sets."},
            ],
            extra={
                "response_format": {"type": "json_object"},
                "temperature": 0.2,
                "top_p": 0.9,
                "top_k": 40,
            },
        )
        assert payload["model"] == CLAUDE_SONNET_MODEL
        assert payload["max_tokens"] == 8000
        assert payload["system"] == "You are the Fun Scout."
        assert payload["messages"] == [{"role": "user", "content": "Build sets."}]
        for forbidden in ("temperature", "top_p", "top_k", "response_format"):
            assert forbidden not in payload

        # Validate against the real installed anthropic SDK signature (v2.x on CI & Heroku).
        sig = inspect.signature(anthropic_messages.Messages.create)
        bound = sig.bind(object(), **payload)
        assert bound.kwargs["model"] == CLAUDE_SONNET_MODEL

        # Also prove complete_chat_detailed succeeds against a strict SDK v2-shaped client
        # that rejects unexpected kwargs like temperature (unlike **kwargs fakes).
        monkeypatch.setattr(llm_request, "_get_ledger", lambda: MemoryBudgetLedger())
        received = []

        class _StrictAnthropicV2Client:
            class _Messages:
                def create(self, *, max_tokens, messages, model, system=None):
                    received.append(
                        {
                            "max_tokens": max_tokens,
                            "messages": messages,
                            "model": model,
                            "system": system,
                        }
                    )
                    return SimpleNamespace(
                        content=[SimpleNamespace(text='{"sets": []}')],
                        usage=SimpleNamespace(input_tokens=100, output_tokens=10),
                        stop_reason="end_turn",
                    )

            messages = _Messages()

        res = llm_request.complete_chat_detailed(
            "fun_scout_sets",
            _StrictAnthropicV2Client(),
            messages=[
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "hi"},
            ],
            max_output_tokens=100,
            temperature=0.3,
        )
        assert len(received) == 1
        assert res.model == CLAUDE_SONNET_MODEL

    def test_execute_refuses_when_estimate_exceeds_max_estimate_usd(self, monkeypatch):
        from scripts import run_fun_scout_benchmark_13102 as bench

        def _forbid(*_a, **_k):
            raise AssertionError("Paid model client must not be built when estimate exceeds limit")

        monkeypatch.setattr(bench, "build_scout_openai_client", _forbid)
        monkeypatch.setattr(bench, "build_scout_anthropic_client", _forbid)
        rc = bench.main(["--execute", "--max-estimate-usd", "0.01"])
        assert rc == 2

    def test_execute_shares_single_tagging_pass_across_models_and_prints_report(
        self, tmp_path, monkeypatch, capsys
    ):
        from scripts import run_fun_scout_benchmark_13102 as bench

        monkeypatch.setattr(llm_request, "_get_ledger", lambda: MemoryBudgetLedger())
        fixture_path = tmp_path / "mini-benchmark.json"
        fixture_path.write_text(
            json.dumps(
                {
                    "captured_at": FROZEN_NOW.isoformat(),
                    "markets": [
                        {
                            "market_id": 101,
                            "source": "polymarket",
                            "title": "Will GTA VI release before 2027?",
                            "status": "open",
                            "category": "entertainment",
                            "volume": 50000,
                            "resolution_date": (FROZEN_NOW + timedelta(days=90)).isoformat(),
                        },
                        {
                            "market_id": 102,
                            "source": "kalshi",
                            "title": "Will Winds of Winter be published before 2027?",
                            "status": "open",
                            "category": "culture",
                            "volume": 35000,
                            "resolution_date": (FROZEN_NOW + timedelta(days=90)).isoformat(),
                        },
                        {
                            "market_id": 103,
                            "source": "polymarket",
                            "title": "Will Silksong release before 2027?",
                            "status": "open",
                            "category": "entertainment",
                            "volume": 45000,
                            "resolution_date": (FROZEN_NOW + timedelta(days=90)).isoformat(),
                        },
                    ],
                    "uncovered_families": [],
                }
            ),
            encoding="utf-8",
        )

        openai_calls = []

        class _FakeOpenAI:
            class _Chat:
                class _Completions:
                    def create(self, **kwargs):
                        openai_calls.append(kwargs)
                        body = json.dumps(
                            {
                                "tagged": [
                                    {"market_id": 101, "fun_group": "vaporware", "is_fun_single": False, "set_hint": "wait", "reason": "delayed"},
                                    {"market_id": 102, "fun_group": "vaporware", "is_fun_single": False, "set_hint": "wait", "reason": "delayed"},
                                    {"market_id": 103, "fun_group": "vaporware", "is_fun_single": False, "set_hint": "wait", "reason": "delayed"},
                                ]
                            }
                        )
                        return SimpleNamespace(
                            choices=[SimpleNamespace(message=SimpleNamespace(content=body))],
                            usage=SimpleNamespace(prompt_tokens=200, completion_tokens=80),
                        )

                completions = _Completions()

            chat = _Chat()

        anthropic_models_called = []

        class _StrictAnthropicV2:
            class _Messages:
                def create(self, *, max_tokens, messages, model, system=None):
                    anthropic_models_called.append(model)
                    body = json.dumps(
                        {
                            "sets": [
                                {
                                    "slug": "will-it-ever-come-out",
                                    "name": "Will it ever come out?",
                                    "kicker": "LONG WAIT",
                                    "category": "culture",
                                    "why_better_together": "Three famous delayed releases side by side.",
                                    "look": "bars",
                                    "selector_kind": "fun_tag",
                                    "member_ids": [101, 102, 103],
                                }
                            ]
                        }
                    )
                    return SimpleNamespace(
                        content=[SimpleNamespace(text=body)],
                        usage=SimpleNamespace(input_tokens=500, output_tokens=150),
                        stop_reason="end_turn",
                    )

            messages = _Messages()

        monkeypatch.setattr(bench, "build_scout_openai_client", lambda: _FakeOpenAI())
        monkeypatch.setattr(bench, "build_scout_anthropic_client", lambda: _StrictAnthropicV2())

        rc = bench.main(["--execute", "--fixture", str(fixture_path)])
        assert rc == 0
        # Tagging ran ONCE even though two Claude models were benchmarked.
        assert len(openai_calls) == 1
        assert anthropic_models_called == [CLAUDE_SONNET_MODEL, CLAUDE_OPUS_MODEL]

        out = capsys.readouterr().out
        assert "Shared tagging pass complete" in out
        assert "Will it ever come out?" in out
        assert "Will GTA VI release before 2027?" in out
        assert "Benchmark total actual spend:" in out
