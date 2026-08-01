from copy import deepcopy

from scripts.evals.settled_event_result_authority import evaluate, evaluate_pack, load_pack


def _case(case_id: str):
    pack = load_pack()
    case = deepcopy(next(row for row in pack["cases"] if row["id"] == case_id))
    return pack, case


def test_versioned_corpus_matches_every_declared_surface() -> None:
    pack = load_pack()
    result = evaluate_pack(pack)
    assert pack["policy"]["contract_version"] == "settled-event-result-authority/v1"
    assert result["passed"] == result["cases"] == 19
    assert not [row for row in result["results"] if row["expected_mismatches"]]


def test_decisive_final_overrides_loser_favored_stale_blend_everywhere() -> None:
    pack, case = _case("completed_home_win_loser_favored")
    result = evaluate(case, pack["policy"])
    assert case["last_live_blend"]["home"] == 0.001
    assert result["winner_side"] == "home"
    assert result["api"]["allowed_terminal_home_probability"] == 1.0
    assert result["api"]["stale_live_probability_may_headline"] is False
    assert set(result["surfaces"][key] for key in (
        "metadata_mode", "web_hero_mode", "native_hero_mode", "card_mode"
    )) == {"result"}
    assert result["surfaces"]["probability_copy_allowed"] is False


def test_home_away_orientation_is_not_price_derived() -> None:
    pack, home = _case("completed_home_win_loser_favored")
    _, away = _case("closed_away_win_loser_favored")
    h = evaluate(home, pack["policy"]); a = evaluate(away, pack["policy"])
    assert (h["winner_side"], h["api"]["allowed_terminal_home_probability"]) == ("home", 1.0)
    assert (a["winner_side"], a["api"]["allowed_terminal_home_probability"]) == ("away", 0.0)


def test_tie_never_fabricates_winner_or_fifty_fifty_probability() -> None:
    pack, case = _case("completed_tie")
    result = evaluate(case, pack["policy"])
    assert result["authority_state"] == "tie"
    assert result["winner_side"] is None
    assert result["api"]["allowed_terminal_home_probability"] is None
    assert result["surfaces"]["metadata_mode"] == "tie"


def test_non_decisive_dispositions_are_explicit_not_live_probability() -> None:
    pack = load_pack()
    rows = {row["id"]: row for row in evaluate_pack(pack)["results"]}
    for case_id in ("abandoned", "cancelled", "postponed", "void", "no_contest"):
        assert rows[case_id]["authority_state"] == "non_decisive"
        assert rows[case_id]["api"]["mode"] == "typed_disposition"
        assert rows[case_id]["surfaces"]["probability_copy_allowed"] is False


def test_missing_conflicting_reopened_and_invalid_authority_are_unknown() -> None:
    pack = load_pack()
    rows = {row["id"]: row for row in evaluate_pack(pack)["results"]}
    for case_id in ("completed_missing_score", "completed_partial_score", "result_reopened", "provider_score_conflict", "unknown_status"):
        assert rows[case_id]["authority_state"] == "unknown"
        assert rows[case_id]["api"]["mode"] == "typed_unknown"
        assert rows[case_id]["sentinel"]["verdict"] == "unknown"


def test_live_final_looking_score_does_not_settle_from_score_alone() -> None:
    pack, case = _case("live_final_looking_score")
    result = evaluate(case, pack["policy"])
    assert result["authority_state"] == "live"
    assert result["api"]["mode"] == "live_probability"
    assert result["chart"]["terminal_result_marker"] is None


def test_poison_position_is_order_independent_and_contained() -> None:
    pack = load_pack()
    rows = {row["id"]: row for row in evaluate_pack(pack)["results"]}
    selected = [rows[f"poison_score_{position}"] for position in ("first", "middle", "last")]
    for row in selected:
        assert row["authority_state"] == "unknown"
        assert row["reasons"] == ["POISON_SCORE_EVIDENCE"]
        assert row["sentinel"]["verdict"] == "unknown"


def test_negative_noninteger_null_and_boolean_scores_are_rejected() -> None:
    pack, base = _case("completed_home_win_loser_favored")
    for value in (-1, 1.5, None, True):
        case = deepcopy(base)
        case["score_evidence"][0]["home"] = value
        result = evaluate(case, pack["policy"])
        assert result["authority_state"] == "unknown"
        assert "INVALID_SCORE" in result["reasons"]


def test_conflicting_duplicate_source_is_unknown() -> None:
    pack, case = _case("completed_home_win_loser_favored")
    case["score_evidence"].append({"source": "espn_final", "home": 2, "away": 3})
    result = evaluate(case, pack["policy"])
    assert result["authority_state"] == "unknown"
    assert "DUPLICATE_SOURCE_CONFLICT" in result["reasons"]


def test_score_source_order_and_cache_replay_are_deterministic() -> None:
    pack, case = _case("completed_home_win_loser_favored")
    case["score_evidence"].append({"source": "statpal_final", "home": 3, "away": 2})
    first = evaluate(case, pack["policy"])
    case["score_evidence"].reverse()
    assert evaluate(case, pack["policy"]) == first
    assert evaluate(deepcopy(case), deepcopy(pack["policy"])) == first


def test_chart_history_is_never_rewritten_and_title_suffix_is_single() -> None:
    pack = load_pack()
    for row in evaluate_pack(pack)["results"]:
        assert row["chart"]["history_mutated"] is False
        assert row["surfaces"]["title_suffix_count"] == 1
