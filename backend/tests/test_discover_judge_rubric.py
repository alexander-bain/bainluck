"""Unit tests for the Discover LLM judge rubric v2 (#596).

Covers the pure prompt/context-assembly helpers: CU v2 profile consumption
(present + missing), the dead/extreme promote-disqualification rule, the dynamic
live-sports context, and corrective few-shots from human verdicts. The judge is
advisory-only (writes llm_proposed_* rows; never touches ranking), so these guard
the prompt the LLM actually sees.
"""

from app.tasks.enrich_markets import (
    _get_cu_v2_profile,
    _compact_feed_item_for_llm,
    _format_live_sports_context,
    _format_judge_few_shots,
    _assemble_judge_prompt,
    _JUDGE_FALLBACK_FEW_SHOTS,
)


class TestCuV2ProfileReader:
    def test_accepts_v2(self):
        meta = {"discover_llm": {"schema_version": 2, "temporal_class": "deadline", "liveness": "active"}}
        assert _get_cu_v2_profile(meta) == meta["discover_llm"]

    def test_rejects_v1(self):
        assert _get_cu_v2_profile({"discover_llm": {"schema_version": 1}}) is None

    def test_rejects_missing_or_malformed(self):
        assert _get_cu_v2_profile(None) is None
        assert _get_cu_v2_profile({}) is None
        assert _get_cu_v2_profile({"discover_llm": "nope"}) is None


class TestCompactWithProfile:
    def _item(self):
        return {
            "score": 50,
            "data": {"id": 7, "name": "Mkt", "status": "open",
                     "top_outcomes": [{"probability": 0.6}]},
        }

    def test_profile_present_adds_cu_fields(self):
        prof = {"temporal_class": "event_tied", "liveness": "dead"}
        c = _compact_feed_item_for_llm(self._item(), prof)
        assert c["cu_profile"] is True
        assert c["temporal_class"] == "event_tied"
        assert c["liveness"] == "dead"

    def test_profile_missing_degrades_gracefully(self):
        c = _compact_feed_item_for_llm(self._item(), None)
        assert c["cu_profile"] is False
        assert "temporal_class" not in c
        assert "liveness" not in c

    def test_extreme_probability_flagged(self):
        item = self._item()
        item["data"]["top_outcomes"] = [{"probability": 0.995}]
        c = _compact_feed_item_for_llm(item, None)
        assert c["probability_extreme"] is True


class TestLiveSportsContext:
    def test_lists_leagues_with_counts(self):
        out = _format_live_sports_context([("basketball_nba", 3), ("icehockey_nhl", 2)])
        assert "basketball_nba (3)" in out
        assert "icehockey_nhl (2)" in out
        assert "HIGH-VALUE" in out

    def test_empty_says_none_detected(self):
        out = _format_live_sports_context([])
        assert "none detected" in out

    def test_filters_zero_and_empty(self):
        out = _format_live_sports_context([("baseball_mlb", 5), (None, 9), ("x", 0)])
        assert "baseball_mlb (5)" in out
        assert "None" not in out


class TestJudgeFewShots:
    def test_corrective_lines_from_rejections(self):
        out = _format_judge_few_shots([
            {"name": "Dead Market", "decision": "rejected_promote"},
            {"name": "Live NHL", "decision": "rejected_downrank"},
        ])
        assert "Dead Market" in out and "do NOT promote" in out
        assert "Live NHL" in out and "do NOT downrank" in out

    def test_accepted_confirmations(self):
        out = _format_judge_few_shots([{"name": "Geo Deal", "decision": "accepted_promote"}])
        assert "Geo Deal" in out and "promote (reviewer confirmed)" in out

    def test_falls_back_when_no_human_verdicts(self):
        assert _format_judge_few_shots([]) == _JUDGE_FALLBACK_FEW_SHOTS

    def test_caps_at_six(self):
        rows = [{"name": f"M{i}", "decision": "rejected_promote"} for i in range(20)]
        out = _format_judge_few_shots(rows)
        assert len(out.splitlines()) == 6


class TestAssembleJudgePrompt:
    def _prompt(self):
        compact = [{"id": 1, "name": "X", "liveness": "dead", "temporal_class": "deadline", "cu_profile": True}]
        return _assemble_judge_prompt(
            "June 12, 2026",
            _format_live_sports_context([("basketball_nba", 3)]),
            _format_judge_few_shots([{"name": "Dead Mkt", "decision": "rejected_promote"}]),
            compact,
            [],
        )

    def test_contains_date(self):
        assert "June 12, 2026" in self._prompt()

    def test_contains_sports_context(self):
        assert "basketball_nba (3)" in self._prompt()

    def test_contains_cu_fields_and_dead_disqualification(self):
        p = self._prompt()
        assert "temporal_class" in p and "liveness" in p
        # The HARD rule: dead/extreme/extreme-probability cannot be promoted.
        assert "never 'promote'" in p
        assert "dead" in p and "extreme" in p

    def test_contains_human_few_shots(self):
        assert "Dead Mkt" in self._prompt()

    def test_contains_json_schema_instruction(self):
        assert '"reviews"' in self._prompt()
