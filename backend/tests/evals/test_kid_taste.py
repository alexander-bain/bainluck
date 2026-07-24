import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from scripts.evals.kid_taste import analyze, load_rows


FIXTURE = Path(__file__).parent / "fixtures/kid_taste.json"


def test_planted_taste_patterns_and_scorer_divergence_are_recovered():
    report = analyze(json.loads(FIXTURE.read_text()))
    alex = next(profile for profile in report["profiles"] if profile["kid"] == "kid:alex")

    assert report["kids"] == 2
    assert report["interaction_rows"] == 6
    assert alex["likes"] == 2
    assert alex["dislikes"] == 1
    assert alex["categories"][0]["category"] in {"baseball", "music", "weather"}
    assert alex["scorer_agreement"]["pearson"] < -0.9
    assert alex["scorer_agreement"]["hardest_divergences"][0]["item_name"] in {
        "Album winner",
        "Rain tomorrow",
    }


def test_streaks_namespace_flags_and_inter_kid_agreement():
    report = analyze(json.loads(FIXTURE.read_text()))
    alex = next(profile for profile in report["profiles"] if profile["kid"] == "kid:alex")

    assert alex["predictions"]["accuracy"] == 0.8
    assert alex["predictions"]["best_streak"] == 2
    assert alex["predictions"]["current_streak"] == 2
    assert alex["predictions"]["namespace_flags"] == {
        "definite_missing_market": 1,
        "unverifiable_legacy": 2,
        "verified_futures": 2,
    }
    assert report["namespace_caveat"]["definite_missing_market"] == 1
    assert report["namespace_caveat"]["unverifiable_legacy"] == 3
    assert report["inter_kid_agreement"]["micro_agreement_rate"] == pytest.approx(2 / 3)


@pytest.mark.asyncio
async def test_loader_accepts_json_and_sqlalchemy_session(monkeypatch):
    export = await load_rows(FIXTURE)
    assert len(export["discover_interactions"]) == 8

    session = MagicMock()
    session.execute = AsyncMock()
    expected = {"discover_interactions": [], "user_predictions": [], "interestingness": []}
    monkeypatch.setattr("scripts.evals.kid_taste.load_from_session", AsyncMock(return_value=expected))
    assert await load_rows(session) == expected


def test_empty_export_is_stable():
    report = analyze({})
    assert report["kids"] == 0
    assert report["profiles"] == []
    assert report["inter_kid_agreement"]["micro_agreement_rate"] is None
