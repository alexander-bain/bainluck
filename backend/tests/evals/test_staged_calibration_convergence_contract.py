from scripts.evals.staged_calibration_convergence_contract import evaluate, evaluate_pack, load_pack


def test_all_lifecycle_cases_match_the_declared_contract() -> None:
    result = evaluate_pack(load_pack())
    assert result["passed"] == result["cases"] == 14


def test_a_completed_cursor_cannot_seed_a_new_published_generation() -> None:
    pack = load_pack()
    case = next(row for row in pack["cases"] if row["id"] == "completed-cursor-must-not-seed-next-build")
    result = evaluate(case["input"], pack["policy"])
    assert result["verdict"] == "refuse"
    assert "COMPLETED_CURSOR_REUSED" in result["errors"]
    assert "CURSOR_NOT_CLEARED_AFTER_PUBLISH" in result["errors"]


def test_superseded_cursor_write_is_not_proof_this_unit_persisted() -> None:
    pack = load_pack()
    case = next(row for row in pack["cases"] if row["id"] == "superseded-is-not-this-unit-durable")
    assert evaluate(case["input"], pack["policy"])["errors"] == ["SUPERSEDED_COUNTED_DURABLE"]


def test_changed_unit_does_not_invalidate_untouched_siblings() -> None:
    pack = load_pack()
    case = next(row for row in pack["cases"] if row["id"] == "one-changed-unit-only-drops-itself")
    result = evaluate(case["input"], pack["policy"])
    assert result["kept_units"] == ["a", "c"]
    assert result["banked_units"] == ["a", "b2", "c"]
