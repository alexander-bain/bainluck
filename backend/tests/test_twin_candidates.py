"""Unit tests for ``tools/matching/twin_candidates.py``."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "tools" / "matching" / "twin_candidates.py"

spec = importlib.util.spec_from_file_location("twin_candidates", MODULE_PATH)
assert spec is not None and spec.loader is not None
twin_candidates = importlib.util.module_from_spec(spec)
sys.modules["twin_candidates"] = twin_candidates
spec.loader.exec_module(twin_candidates)


def test_lexical_prefilter_matches_cross_venue_twins_and_excludes_registered_or_noise():
    markets = [
        # True twin candidate: Kalshi "Pro Football Coach of the Year" vs Polymarket "NFL Coach of the Year"
        {
            "id": 8122712,
            "source": "kalshi",
            "name": "Pro Football Coach of the Year 2026?",
            "llm_sport_category": "football",
            "resolution_date": "2027-02-06T00:00:00+00:00",
            "top_outcomes": [
                {"name": "Ben Johnson", "probability": 0.25},
                {"name": "Dan Campbell", "probability": 0.18},
            ],
        },
        {
            "id": 56933329,
            "source": "polymarket",
            "name": "NFL Coach of the Year 2026",
            "llm_sport_category": "football",
            "resolution_date": "2027-02-06T00:00:00+00:00",
            "top_outcomes": [
                {"name": "Ben Johnson", "probability": 0.24},
                {"name": "Dan Campbell", "probability": 0.19},
            ],
        },
        # Already-registered NFL division market (must be excluded):
        {
            "id": 53674,
            "source": "kalshi",
            "name": "NFC East Division Winner?",
            "llm_sport_category": "football",
            "resolution_date": "2027-01-11T00:00:00+00:00",
            "top_outcomes": [{"name": "Philadelphia Eagles", "probability": 0.55}],
        },
        {
            "id": 55104218,
            "source": "polymarket",
            "name": "NFC East Division Winner",
            "llm_sport_category": "football",
            "resolution_date": "2027-01-11T00:00:00+00:00",
            "top_outcomes": [{"name": "Philadelphia Eagles", "probability": 0.55}],
        },
        # Intraday up/down noise (must be excluded):
        {
            "id": 999001,
            "source": "kalshi",
            "name": "Gold Up or Down - November 3, 3:00PM-3:15PM ET",
            "llm_sport_category": "economics",
        },
        {
            "id": 999002,
            "source": "polymarket",
            "name": "Gold Up or Down - November 3, 3:00PM-3:15PM ET",
            "llm_sport_category": "economics",
        },
    ]

    shortlist = twin_candidates.prefilter_pairs(markets, min_score=0.34)
    assert len(shortlist) == 1
    assert shortlist[0].kalshi["id"] == 8122712
    assert shortlist[0].polymarket["id"] == 56933329
    assert shortlist[0].lexical_score > 0.5


def test_cost_cap_never_exceeds_sixty_dollars():
    pair = twin_candidates.CandidatePair(
        kalshi={"id": 109657, "source": "kalshi", "name": "Fed decision in Dec 2026?"},
        polymarket={"id": 57574250, "source": "polymarket", "name": "Fed interest rates: December 2026"},
        lexical_score=0.65,
        shared_tokens=("2026", "december", "fed"),
        shared_outcomes=(),
    )
    reqs = twin_candidates.build_batch_requests([pair] * 50)
    capped, est_cost = twin_candidates.enforce_cost_cap(reqs, max_cost_usd=0.10)
    assert est_cost <= 0.10
    assert 0 < len(capped) < 50


def test_parse_and_format_report_enforces_three_checks_and_market_terminology():
    pair = twin_candidates.CandidatePair(
        kalshi={
            "id": 109657,
            "source": "kalshi",
            "name": "Fed decision in Dec 2026?",
            "llm_sport_category": "economics",
            "resolution_date": "2026-12-09T18:59:00+00:00",
        },
        polymarket={
            "id": 57574250,
            "source": "polymarket",
            "name": "Fed decision in December?",
            "llm_sport_category": "economics",
            "resolution_date": "2026-12-10T00:00:00+00:00",
        },
        lexical_score=0.72,
        shared_tokens=("2026", "december", "decision", "fed"),
        shared_outcomes=(),
    )
    row = {
        "custom_id": pair.custom_id,
        "result": {
            "type": "succeeded",
            "message": {
                "content": [
                    {
                        "type": "text",
                        "text": (
                            '{"same_proposition": {"pass": true, "reason": "Both questions ask for the Dec 2026 FOMC rate action."}, '
                            '"same_deadline": {"pass": true, "reason": "Both close on the Dec 9-10 FOMC announcement."}, '
                            '"same_resolution_rule": {"pass": true, "reason": "Both settle on the official FOMC statement."}, '
                            '"outcome_aliases": [{"kalshi": "Hike 25bps", "polymarket": "25 bps increase"}], '
                            '"confidence": "high", '
                            '"evidence": "Identical Dec 2026 FOMC rate question with 1-to-1 outcome aliases."}'
                        ),
                    }
                ]
            },
        },
    }
    verdict = twin_candidates.parse_batch_result_row(row)
    assert verdict["confidence"] == "high"
    assert "question" not in verdict["evidence"].lower()
    assert "question" not in verdict["same_proposition"]["reason"].lower()

    json_payload, md_text = twin_candidates.format_candidates_report(
        [pair],
        {pair.custom_id: verdict},
        batch_id="msgbatch_test123",
        model_used="claude-sonnet-5-5",
        estimated_cost_usd=0.015,
        generated_at="2026-11-03T20:15:00Z",
    )
    assert json_payload["pairs_sent"] == 1
    assert json_payload["high_confidence_candidates"] == 1
    assert "Hike 25bps" in md_text
    assert "question" not in md_text.lower()
