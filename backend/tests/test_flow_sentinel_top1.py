"""Queue #246 Item 1d / #1206 — TOP-1 correctness matcher for the gold-set family
queries: the RIGHT surface must LEAD, not merely appear."""
import pytest

from app.tasks.flow_sentinel import (
    GOLD_SET_TOP1,
    _run_search_gold_top1,
    gold_top1_misses,
    search_top1_matches,
)


def test_concept_top1_match():
    payload = {"event_concepts": [{"key": "event:awards:grammys", "name": "The Grammys"}]}
    assert search_top1_matches(payload, "concept", "event:awards:grammys") is True


def test_concept_wrong_leader_fails():
    payload = {"event_concepts": [{"key": "event:awards:oscars"}]}
    assert search_top1_matches(payload, "concept", "event:awards:grammys") is False


def test_concept_prefix_marker():
    payload = {"event_concepts": [{"key": "event:golf:the-masters-2027"}]}
    assert search_top1_matches(payload, "concept", "event:golf:") is True


def test_team_top1_match_case_insensitive():
    payload = {"teams": [{"name": "New England Patriots"}]}
    assert search_top1_matches(payload, "team", "patriots") is True


def test_missing_surface_is_false():
    assert search_top1_matches({}, "concept", "x") is False
    assert search_top1_matches({"event_concepts": []}, "concept", "x") is False
    assert search_top1_matches({"teams": []}, "team", "x") is False


def test_bad_payload_and_unknown_kind():
    assert search_top1_matches(None, "concept", "x") is False
    assert search_top1_matches({"event_concepts": [{"key": "k"}]}, "bogus", "k") is False


def test_gold_top1_misses_filter():
    results = [
        {"query": "a", "top1_ok": True},
        {"query": "b", "top1_ok": False},
    ]
    assert [r["query"] for r in gold_top1_misses(results)] == ["b"]


def test_gold_set_top1_wellformed():
    for query, kind, marker in GOLD_SET_TOP1:
        assert query and kind in ("concept", "team") and marker


class _Resp:
    def __init__(self, payload):
        self._p = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._p


class _Client:
    """Returns a canned payload per query so the flow runner is testable offline."""

    def __init__(self, by_query):
        self._by_query = by_query

    async def get(self, path, params=None):
        return _Resp(self._by_query.get((params or {}).get("q"), {}))


@pytest.mark.asyncio
async def test_flow_runner_all_pass():
    canned = {
        q: ({"event_concepts": [{"key": m}]} if k == "concept"
            else {"teams": [{"name": m}]})
        for q, k, m in GOLD_SET_TOP1
    }
    result = await _run_search_gold_top1(_Client(canned))
    assert result["flow"] == "search_gold_top1"
    assert result["passed"] is True
    assert result["failures"] == []
    assert result["evidence"]["top1_rate"] == 1.0


@pytest.mark.asyncio
async def test_flow_runner_reports_misses():
    # Empty payloads for every query → every entry misses top-1 and files.
    result = await _run_search_gold_top1(_Client({}))
    assert result["passed"] is False
    assert len(result["failures"]) == len(GOLD_SET_TOP1)
    assert result["evidence"]["top1_ok"] == 0
