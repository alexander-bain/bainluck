from scripts.evals.precommence_live_authority import (
    START_AUTHORITIES,
    evaluate,
    load_corpus,
    resolve_write,
    validate_claim,
)


def test_corpus_is_versioned_and_fixture_first() -> None:
    corpus = load_corpus()
    assert corpus["schema_version"] == "precommence-live-authority/v1"
    assert corpus["canonical_issues"] == ["#1207", "#1483"]
    assert len(corpus["scenarios"]) == 13


def test_all_accepted_rows_match_declared_outcomes() -> None:
    result = evaluate(load_corpus())
    assert all(not errors for errors in result["accepted"].values()), result


def test_counterexamples_fail_exactly() -> None:
    for row in load_corpus()["rejected_counterexamples"]:
        assert set(validate_claim(row)) == set(row["expected_violations"])


def test_only_real_start_authorities_can_establish_live() -> None:
    corpus = load_corpus()
    live_rows = [row for row in corpus["scenarios"] if resolve_write(row)["stored_status"] == "live"]
    assert live_rows
    assert all(row["commence_confidence"] in START_AUTHORITIES for row in live_rows)
    assert all(row["start_relation"] == "past" for row in live_rows)


def test_unknown_start_fails_non_live_without_suppressing_card() -> None:
    row = next(row for row in load_corpus()["scenarios"] if row["id"] == "unknown_start_live_claim")
    result = resolve_write(row)
    assert result["stored_status"] == "scheduled"
    assert result["display_status"] == "upcoming"
    assert result["suppress_card"] is False


def test_terminal_reopen_requires_started_authoritative_replay() -> None:
    corpus = load_corpus()
    started = next(row for row in corpus["scenarios"] if row["id"] == "authoritative_replay_after_false_settle")
    future = next(row for row in corpus["scenarios"] if row["id"] == "future_replay_claim_cannot_reopen")
    assert resolve_write(started)["stored_status"] == "live"
    assert resolve_write(future)["stored_status"] == "closed"


def test_existing_future_live_is_the_only_repair_row() -> None:
    corpus = load_corpus()
    repair_ids = [row["id"] for row in corpus["scenarios"] if resolve_write(row)["repair_eligible"]]
    assert repair_ids == ["existing_future_live_requires_bounded_repair"]
