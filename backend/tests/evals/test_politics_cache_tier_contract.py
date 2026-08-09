import json
from pathlib import Path

from scripts.evals.politics_cache_tier_contract import evaluate


FIXTURE = Path(__file__).parent / "fixtures" / "politics_cache_tier_contract.json"


def pack():
    return json.loads(FIXTURE.read_text())


def test_every_fixture_matches_the_oracle():
    for case in pack()["cases"]:
        assert evaluate(case["input"]) == case["expected"], case["id"]


def test_malformed_primary_cannot_hide_healthy_stale():
    case = next(row for row in pack()["cases"] if row["id"] == "current-malformed-primary")
    result = evaluate(case["input"])
    assert result["selected_tier"] == "stale"
    assert "MALFORMED_PRIMARY_BLOCKS_FALLBACK" in result["reasons"]


def test_complete_live_build_writes_both_tiers():
    case = next(row for row in pack()["cases"] if row["id"] == "clean-live-build")
    assert evaluate(case["input"])["verdict"] == "ALLOW"


def test_stale_requires_status_and_age():
    case = next(row for row in pack()["cases"] if row["id"] == "current-undated-stale")
    assert set(evaluate(case["input"])["reasons"]) == {"STALE_AGE_HIDDEN", "STALE_STATUS_HIDDEN"}
