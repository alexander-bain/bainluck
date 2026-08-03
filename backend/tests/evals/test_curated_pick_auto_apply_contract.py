from __future__ import annotations

import copy

from scripts.evals.curated_pick_auto_apply_contract import decide, evaluate_case, evaluate_corpus, load_corpus


def _case(case_id: str) -> dict:
    return copy.deepcopy(next(row for row in load_corpus()["cases"] if row["id"] == case_id))


def test_committed_corpus_matches_oracles() -> None:
    report = evaluate_corpus(load_corpus())
    assert report["total"] == 31
    assert report["passed"] == report["total"], report["cases"]


def test_gate_order_is_lifecycle_quality_match_envelope() -> None:
    row = _case("stale-bab-el-mandeb")
    row["canonical_quality"] = "suppress"
    row["match"]["item_id_match"] = False
    assert decide(row)["reason"] == "lifecycle_past"
    row = _case("offbrand-crypto-ladder")
    row["match"]["item_id_match"] = False
    assert decide(row)["reason"] == "quality_suppressed"


def test_dry_run_never_mutates_and_active_requires_eyeball() -> None:
    assert decide(_case("fresh-israel-pm-dry-run"))["mutations"] == 0
    assert decide(_case("active-without-eyeball"))["reason"] == "activation_not_approved"


def test_bounds_ttl_duplicate_and_switch() -> None:
    assert decide(_case("cap-near"))["effective_delta"] == 20
    assert decide(_case("duplicate-idempotent"))["effective_delta"] == 8
    assert decide(_case("expired-ttl"))["effective_delta"] == 0
    assert decide(_case("disabled-switch"))["mutations"] == 0


def test_canonical_category_and_non_pii_evidence() -> None:
    assert evaluate_case(_case("wrong-email-category-canonical-wins")) == []
    assert evaluate_case(_case("poison-email-category-used")) == ["UNTRUSTED_EMAIL_CATEGORY_USED"]
    assert evaluate_case(_case("poison-dry-run-pii")) == ["DRY_RUN_PII_LEAK"]
