from scripts.evals.settled_score_repair_contract import ALLOWED_MUTATIONS, decide, evaluate, load


def _case(case_id):
    return next(case for case in load()["cases"] if case["id"] == case_id)


def test_corpus_matches_oracle():
    result = evaluate(load())
    assert result["total"] == 19
    assert result["passed"] == result["total"], result["cases"]


def test_ambiguous_authority_never_mutates():
    for case_id in (
        "partial-game-refusal",
        "provider-disagreement-refusal",
        "special-disposition-refusal",
        "swapped-orientation-refusal",
        "doubleheader-neighbour-refusal",
        "inverted-timestamps-refusal",
        "authority-timestamp-order-refusal",
        "cross-event-poison",
    ):
        result = decide(_case(case_id))
        assert result["verdict"] == "refuse"
        assert result["mutations"] == []


def test_apply_is_compare_and_swap_and_atomic():
    assert decide(_case("concurrent-change-refusal"))["verdict"] == "refuse"
    assert decide(_case("atomic-rollback-on-derived-write-failure"))["mutations"] == []
    assert decide(_case("idempotent-retry-after-success"))["verdict"] == "noop"
    for position in ("first", "middle", "last"):
        case = next(row for row in load()["cases"] if row.get("batch_position") == position)
        assert decide(case)["verdict"] == "refuse"


def test_successful_mutations_stay_inside_allowlist():
    for case in load()["cases"]:
        result = decide(case)
        assert set(result["mutations"]) <= ALLOWED_MUTATIONS
