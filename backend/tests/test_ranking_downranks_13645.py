"""Tests for #13645: Alex's cold-read six downranks, family rules, fixed eval cases, and 40-card pair."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from starlette.requests import Request

import app.routes.admin_ranking_eval as admin
from app.utils.discover_opening_mix import (
    apply_discover_opening_mix,
    is_opening_weather_excluded_roundup,
)
from app.utils.discover_rank_13645 import rank_13645_downranks
from app.utils.feed_market_quality import (
    classify_market_quality,
    diversify_quality_families,
    quality_score_adjustment,
)
from app.utils.ranking_eval import RANKING_SNAPSHOTS_ENV

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXED_CASES_PATH = REPO_ROOT / "evals" / "ranking" / "fixed_cases.json"
FROZEN_NOW = datetime(2026, 11, 24, 18, 0, tzinfo=timezone.utc)


def _roundup_card(slug: str, title: str, *, category: str, score: float = 80.0, member_ids=(1, 2)):
    return {
        "type": "bundle",
        "score": score,
        "headline": title,
        "data": {
            "id": f"roundup:{slug}",
            "title": title,
            "kind": "roundup",
            "story_key": f"roundup:{slug}",
            "category": category,
            "item_count": len(member_ids),
            "member_ids": list(member_ids),
            "items": [
                {
                    "type": "futures",
                    "score": score,
                    "data": {"id": mid, "name": f"Member {mid}", "status": "open"},
                }
                for mid in member_ids
            ],
            "collection_ref": {
                "slug": slug,
                "href": f"/collections/{slug}",
                "name": title,
                "revision": "1",
                "collection_count": len(member_ids),
            },
        },
    }


def _futures_card(mid: int, name: str, *, category: str = "politics", score: float = 75.0):
    return {
        "type": "futures",
        "score": score,
        "headline": name,
        "data": {
            "id": mid,
            "name": name,
            "llm_sport_category": category,
            "status": "open",
            "top_outcomes": [{"name": "Yes", "probability": 0.5}],
        },
    }


class TestDownrankFamilyRules13645:
    def test_weekly_single_stock_price_excluded_and_ticker_deduped(self):
        weekly_titles = [
            "Micron (MU) closes week of Nov 23?",
            "How high will Micron (MU) finish the week of November 23?",
            "Will Micron Technology, Inc. (MU) hit (LOW) $600 Week of November 23 2026?",
            "Tesla (TSLA) closes week of Nov 23?",
            "Will SpaceX (SPCX) hit (LOW) $117.50 Week of November 23 2026?",
        ]
        for title in weekly_titles:
            q = classify_market_quality(title, sport_category="economics")
            assert q.quality_class == "low_quality", title
            assert "asset_price_level" in q.reasons, title
            assert q.story_key is not None and q.story_key.startswith("story:equity_ticker:"), title
            assert quality_score_adjustment(q) <= -35, title

        # Exemptions: earnings, IPO close/valuation stay eligible and distinct from weekly ladders
        earnings = classify_market_quality(
            "Will Marvell (MRVL) beat quarterly earnings?",
            sport_category="economics",
        )
        assert earnings.quality_class in ("normal", "compelling")
        assert "asset_price_level" not in earnings.reasons
        assert earnings.story_key == "story:single_stock_earnings"

        anthropic_ipo = classify_market_quality(
            "Anthropic closes below IPO price ($83) by November 25?",
            sport_category="tech",
        )
        assert anthropic_ipo.quality_class in ("normal", "compelling")
        assert "asset_price_level" not in anthropic_ipo.reasons

        anthropic_val = classify_market_quality(
            "Will Anthropic's valuation hit (HIGH) $1.75T by December 31?",
            sport_category="tech",
        )
        assert "asset_price_level" not in anthropic_val.reasons

        # 1-per-ticker cap collapses all 3 Micron cards to 1
        mu_items = []
        for idx, title in enumerate(weekly_titles[:3], start=1):
            q = classify_market_quality(title, sport_category="economics")
            mu_items.append(
                {
                    "type": "futures",
                    "score": 70 - idx,
                    "_quality_family_key": q.family_key,
                    "_quality_story_key": q.story_key,
                    "data": {"id": 9000 + idx, "name": title},
                }
            )
        capped = diversify_quality_families(mu_items)
        assert len(capped) == 1

    def test_non_us_central_banks_and_foreign_gdp_penalized_without_ban(self):
        for title in (
            "Bank of Canada Decision in December?",
            "Reserve Bank of New Zealand decision in December?",
            "Brazil GDP Growth in Q3 2026 (QoQ)?",
        ):
            q = classify_market_quality(title, sport_category="economics")
            assert q.quality_class == "normal", title
            assert "non_us_macro_downrank" in q.reasons, title
            assert quality_score_adjustment(q) == -20, title

        # U.S. Fed & U.S. GDP must NOT be penalized
        for us_title in (
            "Will the Fed cut interest rates in January?",
            "Will the Fed cut before the ECB?",
            "US GDP growth above 2.5% in Q4?",
        ):
            q = classify_market_quality(us_title, sport_category="economics")
            assert "non_us_macro_downrank" not in q.reasons, us_title

    def test_minor_conference_title_berth_penalized_and_cfp_kept(self):
        for title in (
            "James Madison advances to the Sun Belt Championship Game",
            "NCAA Football: Team to Qualify for 2026 Mountain West Championship Game",
            "NCAA Football: Team to Qualify for 2026 MAC Championship Game",
        ):
            q = classify_market_quality(title, sport_category="football")
            assert q.quality_class == "normal", title
            assert "minor_conf_title_berth" in q.reasons, title
            assert quality_score_adjustment(q) == -20, title

        for major_title in (
            "College Football Playoff National Championship Winner",
            "Oregon wins the Big Ten Championship Game",
            "Texas advances to the SEC Championship Game",
        ):
            q = classify_market_quality(major_title, sport_category="football")
            assert "minor_conf_title_berth" not in q.reasons, major_title

    def test_yemen_houthi_tactical_folds_into_middle_east_and_penalized(self):
        for title in (
            "Houthis enter Aden?",
            "Houthis successfully target shipping by November 30?",
            "Pakistan military action against Yemen by December 31?",
        ):
            q = classify_market_quality(
                title,
                sport_category="geopolitics",
                persisted_story_key=f"llm:{title[:16]}",
            )
            assert q.story_key == "story:middle_east_conflict", title
            assert "regional_conflict_operational" in q.reasons, title
            assert quality_score_adjustment(q) == -15, title

        ceasefire = classify_market_quality(
            "Israel x Hamas ceasefire extended through 2026?",
            sport_category="geopolitics",
        )
        assert ceasefire.story_key == "story:middle_east_conflict"
        assert "regional_conflict_operational" not in ceasefire.reasons

    def test_tomorrows_highs_excluded_from_opening_ten(self):
        weather_card = _roundup_card(
            "roundup-tomorrows-highs",
            "Where tomorrow's high is least certain",
            category="weather",
            score=99.0,
            member_ids=[10, 11],
        )
        assert is_opening_weather_excluded_roundup(weather_card) is True

        white_xmas = _roundup_card(
            "machinery-white-christmas",
            "White Christmas",
            category="weather",
            score=85.0,
            member_ids=[12, 13],
        )
        assert is_opening_weather_excluded_roundup(white_xmas) is False

        deck = [
            weather_card,
            _roundup_card("machinery-elon-musk-side-quests", "Elon Musk", category="tech", score=88.0, member_ids=[20, 21]),
            _roundup_card("machinery-long-shots", "Long shots", category="culture", score=84.0, member_ids=[22, 23]),
            white_xmas,
            _roundup_card("machinery-oscars-best-picture", "Oscars", category="entertainment", score=85.0, member_ids=[24, 25]),
            _roundup_card("machinery-next-james-bond", "Bond", category="entertainment", score=82.0, member_ids=[26, 27]),
            _roundup_card("machinery-2026-summed-up", "2026 Summed Up", category="entertainment", score=81.0, member_ids=[28, 29]),
            _roundup_card("machinery-ai-and-big-tech-race", "AI Race", category="tech", score=80.0, member_ids=[30, 31]),
            _roundup_card("machinery-ai-model-leaderboard-2026", "AI Models", category="tech", score=79.0, member_ids=[32, 33]),
            _roundup_card("roundup-cfp-picture", "CFP", category="sports", score=86.0, member_ids=[34, 35]),
            _roundup_card("roundup-nhl-playoffs-2026-27", "NHL", category="sports", score=83.0, member_ids=[36, 37]),
            _roundup_card("machinery-2028-presidential", "2028", category="politics", score=90.0, member_ids=[38, 39]),
            _futures_card(901, "U.S. confirms aliens before 2027?", category="culture", score=78.0),
            _futures_card(902, "Deep fallback card", category="politics", score=60.0),
        ]
        mixed = apply_discover_opening_mix(deck, now=FROZEN_NOW)
        opening_slugs = {
            (it.get("data") or {}).get("story_key") for it in mixed[:10]
        }
        assert "roundup:roundup-tomorrows-highs" not in opening_slugs
        assert "roundup:tomorrows-highs" not in opening_slugs
        assert any(
            (it.get("data") or {}).get("id") == "roundup:roundup-tomorrows-highs"
            for it in mixed[10:]
        )


class TestFixedCasesAndShippedPair13645:
    def test_fixed_cases_file_holds_all_six_alex_quotes_and_passes_after_replay(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "scorecard", REPO_ROOT / "tools" / "ranking" / "scorecard.py"
        )
        sc = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sc)

        doc = json.loads(FIXED_CASES_PATH.read_text(encoding="utf-8"))
        assert len(doc["cases"]) == 6
        slate_path = REPO_ROOT / "evals" / "ranking" / "slates" / "2026-11-24-discover-d2cc84c651b109d6.json"
        slate = sc.load_json(slate_path)

        before = sc.score_fixed_cases(slate["served_order"])
        assert before["checked"] == 5 and before["violations"] == 2

        replayed_keys = [c["item_key"] for c in rank_13645_downranks(slate["candidates"])]
        after = sc.score_fixed_cases(replayed_keys)
        assert after["checked"] == 5 and after["violations"] == 0
        assert replayed_keys.index("bundle:roundup:tomorrows-highs") >= 10
        assert replayed_keys.index("futures:60542247") >= 40
        assert replayed_keys.index("futures:71579101") >= 40

    async def test_get_pair_40_cards_on_shipped_nov24_slate(self, monkeypatch):
        class EmptyDB:
            def __init__(self):
                self.added = []

            async def execute(self, stmt):
                return SimpleNamespace(
                    scalars=lambda: SimpleNamespace(first=lambda: None, all=lambda: [])
                )

            def add(self, row):
                self.added.append(row)

            async def commit(self):
                pass

        monkeypatch.setattr(admin, "_check_admin_secret", lambda *a, **k: True)
        monkeypatch.setenv(RANKING_SNAPSHOTS_ENV, "1")
        monkeypatch.setenv("ADMIN_TOKEN", "pair-13645-test-secret")

        req = Request({"type": "http", "method": "GET", "path": "/", "headers": [], "query_string": b""})
        out = await admin.get_pair(
            req,
            slate="d2cc84c651b109d6",
            pair="p13645",
            surface="discover",
            secret=None,
            db=EmptyDB(),
        )
        assert set(out) == {"slate_id", "pair", "captured_at", "left", "right"}
        assert len(out["left"]) == len(out["right"]) == 40
        assert out["left"] != out["right"]

        left_ids = [(c["card"].get("data") or {}).get("id") for c in out["left"]]
        right_ids = [(c["card"].get("data") or {}).get("id") for c in out["right"]]
        # Exactly one side is the proposed 40 (no tomorrow's highs in 1..10, no BoC/TSLA in 1..40)
        sides = [left_ids, right_ids]
        proposed_sides = [
            s for s in sides
            if "roundup:tomorrows-highs" not in s[:10]
            and 60542247 not in s[:40]
            and "60542247" not in s[:40]
            and 71579101 not in s[:40]
            and "71579101" not in s[:40]
        ]
        assert len(proposed_sides) == 1

        # Pick submission works cleanly on p13645 without leaking side
        pick_db = EmptyDB()
        body = admin.PairPickIn(
            slate_id="d2cc84c651b109d6",
            pair="p13645",
            grader="Alex Bain",
            choice="right",
            opened_discover_today=True,
        )
        res = await admin.post_pair_pick(body, req, secret=None, db=pick_db)
        assert res == {"status": "ok"}
        assert len(pick_db.added) == 1
        assert pick_db.added[0].item_key == "pair:p13645"
        assert re.fullmatch(r"shareable|neither|interesting", str(pick_db.added[0].grade))
