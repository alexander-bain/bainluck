from scripts.evals.watchdog_ledger_evidence_contract import evaluate_pack, extract, load_pack


def test_corpus_matches_declared_current_and_contract_results() -> None:
    result = evaluate_pack(load_pack())
    assert result["passed"] == result["cases"] == 7


def test_exact_live_incident_retains_phase_and_expensive_stage() -> None:
    case = load_pack()["cases"][0]
    result = extract(case["payload"], current_sql=False)
    assert result["names"][:2] == ["futures", "stage:read:futures_unit"]


def test_malformed_diagnostic_sibling_cannot_suppress_valid_evidence() -> None:
    rows = {case["id"]: case for case in load_pack()["cases"]}
    for case_id in (
        "json_null_stage_map_must_not_erase_phase",
        "poison_stage_must_not_erase_valid_siblings",
        "wrong_phase_shape_must_not_erase_valid_stages",
    ):
        payload = rows[case_id]["payload"]
        assert extract(payload, current_sql=True)["verdict"] == "no_evidence"
        assert extract(payload, current_sql=False)["verdict"] == "useful_evidence"


def test_stage_order_is_cost_descending_not_json_key_order() -> None:
    case = next(c for c in load_pack()["cases"] if c["id"] == "stage_cost_order_is_descending")
    assert extract(case["payload"], current_sql=False)["names"] == [
        "stage:expensive", "stage:middle", "stage:cheap"
    ]
