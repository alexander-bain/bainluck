import json
from pathlib import Path

from backend.scripts.evals.event_negative_cache_precedence_contract import decide


FIXTURES = Path(__file__).parent / "fixtures" / "event_negative_cache_precedence_contract.json"


def test_all_cache_states_match_authority():
    for case in json.loads(FIXTURES.read_text()):
        assert decide(**case["input"]) == case["expected"], case["id"]


def test_last_good_beats_both_live_failure_shapes():
    for failure in ("none", "exception"):
        result = decide(positive=False, negative=False, stale=True, build=failure)
        assert result == {"response": "stale", "write": "none"}


def test_only_never_seen_none_writes_negative():
    assert decide(positive=False, negative=False, stale=False, build="none")["write"] == "negative"
    assert decide(positive=False, negative=False, stale=True, build="none")["write"] == "none"


def test_positive_always_has_highest_read_precedence():
    for build in ("success", "none", "exception"):
        assert decide(positive=True, negative=True, stale=True, build=build)["response"] == "positive"
