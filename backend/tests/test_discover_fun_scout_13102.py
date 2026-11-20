"""Tests for #13102 (Ruling 276: B): Nightly Fun Scout model registry, code checks,
Decide 60-A / 61-A / 73-A / 32-C rule files, licence ramp, and spend caps.

No test makes a network call. All dates are frozen historical timestamps.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

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
    LICENCE_AWAITING_LOOK,
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
