"""Tests for model-proposed new grouping kinds to Alex only, five example cards each (#9937).

Covers:
1. Committed proposals in ``docs/discover/new-kind-proposals-2026-11.json`` and
   ``.md`` carry ``audience="alex_only"``, ``example_card_count == 5`` per kind,
   reproducible selectors (73-A), stronger-single alternatives, and ``>= 3``
   priced rows per example card.
2. Validator refuses proposals with fewer than 5 example cards, invalid
   relations/level (71-A), hand lists of market IDs (73-A), standing exclusions,
   unpriced/settled rows, or forbidden ``question`` wording.
3. Decide 61-A spend discipline: uses ``LEGACY_MODEL`` from
   ``app.services.llm_models``, prints the estimated cost before running, and
   enforces the ``$5.00``/run and ``$30.00``/Nov caps.
4. Catalog admission & reader isolation: requires ``>= 6`` Alex grades with
   ``0`` ``"no"`` verdicts to join the catalog, and strictly guarantees that
   **nothing reaches readers without a licence** (``reader_reachable is False``
   and ``is_kind_licensed(kind) is False``).
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from app.services.llm_models import LEGACY_MODEL
from app.utils.grouping_kind_proposer import (
    DEFAULT_KIND_PROPOSALS_JSON_PATH,
    DEFAULT_KIND_PROPOSALS_MD_PATH,
    DEFAULT_KIND_PROPOSER_MODEL,
    KIND_PROPOSER_MONTHLY_CAP_USD,
    KIND_PROPOSER_RUN_CAP_USD,
    MIN_GRADED_CARDS_FOR_CATALOG,
    REQUIRED_EXAMPLE_CARDS_PER_KIND,
    KindProposalSpendCapExceededError,
    evaluate_kind_catalog_admission,
    load_committed_kind_proposals,
    propose_new_grouping_kinds,
    validate_proposed_grouping_kind,
)
from app.utils.grouping_licences import is_kind_licensed
from app.utils.roundup_containers import ROUNDUP_PRODUCERS, _KIND_TO_MODULE_BUILDER


class TestCommittedNewKindProposalsForAlex:
    """#9937 Exit: a proposal with five example cards each is committed for Alex's grading."""

    def test_committed_proposals_load_with_five_example_cards_each_and_alex_only_audience(
        self,
    ) -> None:
        assert DEFAULT_KIND_PROPOSALS_JSON_PATH.exists()
        assert DEFAULT_KIND_PROPOSALS_MD_PATH.exists()
        md_text = DEFAULT_KIND_PROPOSALS_MD_PATH.read_text(encoding="utf-8")
        assert "season_stat_leaders" in md_text
        assert "qualification_stage_board" in md_text
        assert "[grouping-kind-proposer]" in md_text

        data = load_committed_kind_proposals()
        assert data["audience"] == "alex_only"
        assert data["accepted_count"] == 2
        proposals = data["proposals"]
        assert len(proposals) == 2

        for prop in proposals:
            assert prop["audience"] == "alex_only"
            assert prop["example_card_count"] == REQUIRED_EXAMPLE_CARDS_PER_KIND == 5
            assert len(prop["example_cards"]) == 5
            assert prop["licence_status"] == "UNLICENSED"
            assert prop["reader_reachable"] is False
            assert is_kind_licensed(prop["kind"]) is False
            assert prop["kind"] not in _KIND_TO_MODULE_BUILDER
            for card in prop["example_cards"]:
                assert len(card["rows"]) >= 3
                assert card["stronger_single_alternative"]["market_id"] > 0
                assert card["slug"] not in ROUNDUP_PRODUCERS


class TestKindProposalValidationAndGuardrails:
    """#9937: enforces 5 example cards, 71-A relations/level, 73-A selectors, and standing exclusions."""

    def _base_valid_kind(self) -> dict[str, Any]:
        loaded = load_committed_kind_proposals()
        return copy.deepcopy(loaded["proposals"][0])

    def test_refuses_proposal_with_fewer_than_five_example_cards(self) -> None:
        candidate = self._base_valid_kind()
        candidate["example_cards"] = candidate["example_cards"][:4]
        res = validate_proposed_grouping_kind(candidate)
        assert res["ok"] is False
        assert res["reason"] == "requires_5_example_cards_got_4"

    def test_refuses_hand_list_of_market_ids_in_example_card_selector_73a(self) -> None:
        candidate = self._base_valid_kind()
        candidate["example_cards"][0]["selector"] = {
            "sport": "americanfootball_nfl",
            "market_ids": [62810101, 62810102, 62810103],
        }
        res = validate_proposed_grouping_kind(candidate)
        assert res["ok"] is False
        assert "hand_list_forbidden_in_new_kind" in str(res["reason"])

    def test_refuses_invalid_relations_or_equivalent_without_twin_71a(self) -> None:
        candidate = self._base_valid_kind()
        candidate["level"] = "equivalent"
        res = validate_proposed_grouping_kind(candidate)
        assert res["ok"] is False
        assert res["reason"] == "equivalent_requires_twin_relation"

    def test_refuses_standing_exclusions_unpriced_rows_and_forbidden_question_word(
        self,
    ) -> None:
        cand_excl = self._base_valid_kind()
        cand_excl["example_cards"][0]["title"] = "Which player says a mention word tonight?"
        res_excl = validate_proposed_grouping_kind(cand_excl)
        assert res_excl["ok"] is False
        assert "standing_exclusion_triggered" in str(res_excl["reason"])

        cand_unpriced = self._base_valid_kind()
        cand_unpriced["example_cards"][0]["rows"][0]["probability"] = 1.0
        res_unpriced = validate_proposed_grouping_kind(cand_unpriced)
        assert res_unpriced["ok"] is False
        assert "unpriced_or_settled_row" in str(res_unpriced["reason"])

        cand_q = self._base_valid_kind()
        cand_q["title"] = "Season Stat Milestone Questions"
        res_q = validate_proposed_grouping_kind(cand_q)
        assert res_q["ok"] is False
        assert res_q["reason"] == "forbidden_question_word"


class TestKindProposerSpendAndCatalogAdmission:
    """#9937: Decide 61-A spend caps + 6 graded cards with zero 'no' + licence required for readers."""

    def test_prints_spend_before_run_and_enforces_61a_caps(self) -> None:
        assert DEFAULT_KIND_PROPOSER_MODEL == LEGACY_MODEL
        assert KIND_PROPOSER_RUN_CAP_USD == 5.00
        assert KIND_PROPOSER_MONTHLY_CAP_USD == 30.00

        printed: list[str] = []
        loaded = load_committed_kind_proposals()
        out = propose_new_grouping_kinds(
            loaded["proposals"],
            prior_november_spend_usd=0.0045,
            print_fn=printed.append,
        )
        assert len(printed) == 1
        assert "[grouping-kind-proposer]" in printed[0]
        assert f"model={LEGACY_MODEL}" in printed[0]
        assert out["accepted_count"] == 2
        assert out["audience"] == "alex_only"

        with pytest.raises(KindProposalSpendCapExceededError):
            propose_new_grouping_kinds(
                loaded["proposals"],
                prior_november_spend_usd=29.99999,
                avg_input_tokens=500_000,
                print_fn=lambda _: None,
            )

    def test_catalog_admission_requires_six_alex_yes_grades_with_no_nos_and_licence_to_reach_readers(
        self,
    ) -> None:
        assert MIN_GRADED_CARDS_FOR_CATALOG == 6

        # Only 5 'yes' grades -> does not yet join catalog
        five_yes = [
            {"kind": "season_stat_leaders", "grader": "alex", "verdict": "yes"}
            for _ in range(5)
        ]
        verdict_5 = evaluate_kind_catalog_admission("season_stat_leaders", five_yes)
        assert verdict_5["joins_catalog"] is False
        assert verdict_5["can_reach_readers"] is False

        # 6 'yes' grades + 1 'no' grade -> refused because no_count > 0
        six_yes_one_no = [
            *five_yes,
            {"kind": "season_stat_leaders", "grader": "alex", "verdict": "yes"},
            {"kind": "season_stat_leaders", "grader": "alex", "verdict": "no"},
        ]
        verdict_with_no = evaluate_kind_catalog_admission(
            "season_stat_leaders", six_yes_one_no
        )
        assert verdict_with_no["joins_catalog"] is False
        assert verdict_with_no["can_reach_readers"] is False

        # 6 'yes' grades and 0 'no' grades -> joins catalog, but still cannot reach readers without a licence!
        six_yes = [
            {"kind": "season_stat_leaders", "grader": "alex", "verdict": "yes"}
            for _ in range(6)
        ]
        verdict_6 = evaluate_kind_catalog_admission("season_stat_leaders", six_yes)
        assert verdict_6["joins_catalog"] is True
        assert verdict_6["is_licensed"] is False
        assert verdict_6["can_reach_readers"] is False
