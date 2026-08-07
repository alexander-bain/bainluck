import json
from pathlib import Path

from backend.scripts.evals.data_quality_alert_episode_contract import evaluate, fingerprint


FIXTURES = Path(__file__).parent / "fixtures" / "data_quality_alert_episode_contract.json"


def test_corpus_matches_oracle():
    cases = json.loads(FIXTURES.read_text())
    assert len(cases) >= 15
    for case in cases:
        assert evaluate(case) == case["expected"], case["id"]


def test_value_drift_does_not_change_episode_identity():
    a = {"check": "espn_freshness", "scope": "global", "value": 1}
    b = {"check": "espn_freshness", "scope": "global", "value": 99}
    assert fingerprint(a) == fingerprint(b)


def test_global_and_event_incidents_are_distinct():
    global_fp = fingerprint({"check": "espn_freshness", "scope": "global"})
    event_fp = fingerprint({"check": "espn_capture_gap", "scope": "event", "event_id": 42})
    assert global_fp != event_fp

