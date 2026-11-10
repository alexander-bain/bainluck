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
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from fastapi import HTTPException
import pytest

from app.routes.admin_ranking_eval import (
    get_grouping_kind_proposals,
    load_grouping_grade_deck,
)
from app.services.llm_models import LEGACY_MODEL
from app.utils.grouping_kind_proposer import (
    DEFAULT_KIND_PROPOSALS_JSON_PATH,
    DEFAULT_KIND_PROPOSALS_MD_PATH,
    DEFAULT_KIND_PROPOSER_MODEL,
    DEFAULT_NEW_KINDS_EXAM_JSON_PATH,
    DOCS_KIND_PROPOSALS_JSON_PATH,
    DOCS_NEW_KINDS_EXAM_JSON_PATH,
    KIND_PROPOSER_MONTHLY_CAP_USD,
    KIND_PROPOSER_RUN_CAP_USD,
    MIN_GRADED_CARDS_FOR_CATALOG,
    NEW_KINDS_EXAM_SLATE_ID,
    REQUIRED_EXAMPLE_CARDS_PER_KIND,
    KindProposalSpendCapExceededError,
    compute_selection_carrying_title,
    evaluate_kind_catalog_admission,
    load_committed_kind_proposals,
    load_new_kinds_exam_cards,
    propose_new_grouping_kinds,
    validate_proposed_grouping_kind,
)
from app.utils.grouping_licences import UNLICENSED_PROPOSED_KINDS, is_kind_licensed
from app.utils.roundup_containers import ROUNDUP_PRODUCERS, _KIND_TO_MODULE_BUILDER

_BACKEND_DIR = Path(__file__).resolve().parents[1]


class TestCommittedNewKindProposalsForAlex:
    """#9937 Exit: a proposal with five example cards each is committed for Alex's grading."""

    def test_backend_data_copy_exists_inside_backend_and_matches_docs_copy(
        self,
    ) -> None:
        assert DEFAULT_KIND_PROPOSALS_JSON_PATH.is_absolute()
        assert DEFAULT_KIND_PROPOSALS_JSON_PATH == (
            _BACKEND_DIR / "data" / "discover" / "new-kind-proposals-2026-11.json"
        )
        assert _BACKEND_DIR in DEFAULT_KIND_PROPOSALS_JSON_PATH.parents
        assert DEFAULT_KIND_PROPOSALS_JSON_PATH.exists()
        assert DOCS_KIND_PROPOSALS_JSON_PATH.exists()
        assert DEFAULT_KIND_PROPOSALS_JSON_PATH.read_text(
            encoding="utf-8"
        ) == DOCS_KIND_PROPOSALS_JSON_PATH.read_text(encoding="utf-8")

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
            assert prop["kind"] in UNLICENSED_PROPOSED_KINDS
            assert is_kind_licensed(prop["kind"]) is False
            assert prop["kind"] not in _KIND_TO_MODULE_BUILDER
            for card in prop["example_cards"]:
                assert len(card["rows"]) >= 3
                assert card["stronger_single_alternative"]["market_id"] > 0
                assert card["as_of"] == data["generated_at"]
                assert card["as_of_label"] == "as of Nov 9, 1:15 PM PT"
                assert card["slug"] not in ROUNDUP_PRODUCERS

    def test_grading_deck_mounts_ten_new_kind_example_cards_with_as_of_labels(
        self,
    ) -> None:
        data = load_committed_kind_proposals()
        deck = load_grouping_grade_deck()
        nk_items = [
            it
            for it in deck["items"]
            if it.get("proposed_kind")
            in ("season_stat_leaders", "qualification_stage_board")
        ]
        assert len(nk_items) == 10
        for it in nk_items:
            assert it["as_of"] == data["generated_at"]
            assert it["as_of_label"] == "as of Nov 9, 1:15 PM PT"
            assert it["proposed_card"]["as_of_label"] == "as of Nov 9, 1:15 PM PT"
            assert it["kind_verdict"] == "refuse"
            assert it["refusal_reasons"] == ["not_licensed"]
            assert "trust_pass" not in it
            assert it["best_single"]["id"] > 0
            assert 0 < it["best_single"]["rendered_percent"] < 100


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

        cand_missing_single_prob = self._base_valid_kind()
        cand_missing_single_prob["example_cards"][0]["stronger_single_alternative"][
            "probability"
        ] = None
        res_sp = validate_proposed_grouping_kind(cand_missing_single_prob)
        assert res_sp["ok"] is False
        assert "invalid_stronger_single_probability" in str(res_sp["reason"])

        cand_six_cards = self._base_valid_kind()
        cand_six_cards["example_cards"].append(
            copy.deepcopy(cand_six_cards["example_cards"][0])
        )
        res_six = validate_proposed_grouping_kind(cand_six_cards)
        assert res_six["ok"] is False
        assert res_six["reason"] == "requires_5_example_cards_got_6"

    @pytest.mark.asyncio
    async def test_load_committed_kind_proposals_and_route_fail_loudly_on_missing_or_invalid_data(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        missing_path = tmp_path / "does-not-exist.json"
        with pytest.raises(FileNotFoundError):
            load_committed_kind_proposals(path=missing_path)

        bad_json_path = tmp_path / "bad.json"
        bad_json_path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        with pytest.raises(ValueError, match="expected mapping"):
            load_committed_kind_proposals(path=bad_json_path)

        bad_prop_path = tmp_path / "refused.json"
        bad_prop = self._base_valid_kind()
        bad_prop["example_cards"] = bad_prop["example_cards"][:3]
        bad_prop_path.write_text(
            json.dumps({"generated_at": "2027-01-15T21:15:00Z", "proposals": [bad_prop]}),
            encoding="utf-8",
        )
        loaded_refused = load_committed_kind_proposals(path=bad_prop_path)
        assert loaded_refused["accepted_count"] == 0
        assert loaded_refused["refused_count"] == 1
        assert loaded_refused["refused"] == [
            {
                "kind": "season_stat_leaders",
                "reason": "requires_5_example_cards_got_3",
            }
        ]

        monkeypatch.setattr(
            "app.routes.admin_ranking_eval._check_admin_secret", lambda *_a, **_kw: None
        )
        monkeypatch.setattr(
            "app.utils.grouping_kind_proposer.load_committed_kind_proposals",
            lambda: load_committed_kind_proposals(path=missing_path),
        )
        with pytest.raises(HTTPException) as exc_404:
            await get_grouping_kind_proposals(request=MagicMock(), secret="ok")
        assert exc_404.value.status_code == 404

        monkeypatch.setattr(
            "app.utils.grouping_kind_proposer.load_committed_kind_proposals",
            lambda: load_committed_kind_proposals(path=bad_prop_path),
        )
        with pytest.raises(HTTPException) as exc_500:
            await get_grouping_kind_proposals(request=MagicMock(), secret="ok")
        assert exc_500.value.status_code == 500
        assert exc_500.value.detail["reason"] == "committed_kind_proposals_refused"


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

        # Also maps /grade/groupings RankingGrade rows by item_key and amazing/fine/no grade
        page_rows = [
            {
                "item_key": "nhl-2026-teams-100-points-benchmark",
                "grader": "Alex Bain",
                "grade": "amazing",
            },
            {
                "item_key": "nhl-2026-teams-110-points-benchmark",
                "grader": "Alex",
                "grade": "fine",
            },
        ]
        verdict_page = evaluate_kind_catalog_admission("season_stat_leaders", page_rows)
        assert verdict_page["yes_count"] == 2
        assert verdict_page["no_count"] == 0

        # Pre-fix calibration grades (from grouping-candidates-2026-11 or graded_on_pre_fix_headings=True)
        # are recorded in pre_fix_yes_count and do NOT count as a pass on the new selection-carrying titles
        pre_fix_rows = [
            {
                "slate_id": "grouping-candidates-2026-11",
                "item_key": "nhl-2026-teams-100-points-benchmark",
                "grader": "Alex",
                "grade": "amazing",
            }
            for _ in range(6)
        ]
        verdict_pre_fix = evaluate_kind_catalog_admission(
            "season_stat_leaders", pre_fix_rows
        )
        assert verdict_pre_fix["pre_fix_yes_count"] == 6
        assert verdict_pre_fix["yes_count"] == 0
        assert verdict_pre_fix["joins_catalog"] is False

    def test_selection_carrying_titles_and_twenty_card_held_out_exam_deck(
        self,
    ) -> None:
        # 1. Complete division (N <= 8)
        complete_meta = compute_selection_carrying_title(
            [
                {"label": "Cincinnati Bengals", "probability": 0.935, "rendered_percent": 94},
                {"label": "Pittsburgh Steelers", "probability": 0.715, "rendered_percent": 72},
                {"label": "Cleveland Browns", "probability": 0.2365, "rendered_percent": 24},
                {"label": "Baltimore Ravens", "probability": 0.16, "rendered_percent": 16},
            ],
            total_member_count=4,
            subject_unit="teams",
            question_subtitle="Which AFC North teams will make the 2027 NFL playoffs?",
            selection_type="complete_group",
        )
        assert complete_meta["title"] == "Which AFC North teams will make the 2027 NFL playoffs?"
        assert complete_meta["subtitle"] is None
        assert complete_meta["count_line"] == "Showing 4 of 4 teams"

        # 2. Clear leader (> 1 point)
        leader_meta = compute_selection_carrying_title(
            [
                {"label": "Minnesota Wild", "probability": 0.955, "rendered_percent": 96},
                {"label": "Carolina Hurricanes", "probability": 0.94, "rendered_percent": 94},
            ],
            total_member_count=32,
            subject_unit="teams",
            race_name="NHL playoff race",
            question_subtitle="Which NHL team will make the 2026–27 playoffs?",
            selection_type="top_5",
        )
        assert leader_meta["title"] == "Minnesota Wild lead the NHL playoff race at 96%"
        assert leader_meta["subtitle"] == "Which NHL team will make the 2026–27 playoffs?"
        assert leader_meta["count_line"] == "Showing 2 of 32 teams"

        # 3. Close race (within 1 point)
        tie_meta = compute_selection_carrying_title(
            [
                {"label": "Connor McDavid", "probability": 0.962, "rendered_percent": 96},
                {"label": "Nathan MacKinnon", "probability": 0.9595, "rendered_percent": 96},
            ],
            total_member_count=101,
            subject_unit="players",
            race_name="NHL 80-point race",
            question_subtitle="Which NHL players will reach 80+ points in 2026–27?",
            selection_type="top_5",
            unnumbered_count=9,
        )
        assert (
            tie_meta["title"]
            == "Connor McDavid and Nathan MacKinnon top the NHL 80-point race at 96%"
        )
        assert tie_meta["subtitle"] == "Which NHL players will reach 80+ points in 2026–27?"
        assert (
            tie_meta["count_line"]
            == "Showing 2 of 101 players · No number yet for 9 players"
        )

        # 4. Bubble slice (closest to 50%)
        bubble_meta = compute_selection_carrying_title(
            [
                {"label": "Anaheim Ducks", "probability": 0.505, "rendered_percent": 50},
                {"label": "Buffalo Sabres", "probability": 0.445, "rendered_percent": 44},
            ],
            total_member_count=32,
            subject_unit="teams",
            selection_type="bubble_50",
            bubble_title="Five NHL teams on the 2026–27 playoff bubble",
        )
        assert bubble_meta["title"] == "Five NHL teams on the 2026–27 playoff bubble"
        assert bubble_meta["subtitle"] == "Closest to 50% · 32 teams"
        assert bubble_meta["count_line"] == "Showing 2 of 32 teams"

        # 5. Fallback when no natural title for S
        fallback_meta = compute_selection_carrying_title(
            [{"label": "Team A", "probability": 0.5, "rendered_percent": 50}],
            total_member_count=20,
            subject_unit="teams",
            question_subtitle="Which team qualifies?",
            selection_type="fallback",
        )
        assert fallback_meta["count_line"] == "Top 1 by chance · 20 teams"

        # 6. Verify 20-card held-out exam slate
        assert DEFAULT_NEW_KINDS_EXAM_JSON_PATH.exists()
        assert DOCS_NEW_KINDS_EXAM_JSON_PATH.exists()
        assert DEFAULT_NEW_KINDS_EXAM_JSON_PATH.read_text(
            encoding="utf-8"
        ) == DOCS_NEW_KINDS_EXAM_JSON_PATH.read_text(encoding="utf-8")

        exam = load_new_kinds_exam_cards()
        assert exam["slate_id"] == NEW_KINDS_EXAM_SLATE_ID
        assert exam["accepted_count"] == 20
        assert exam["refused_count"] == 0
        stat_cards = [c for c in exam["cards"] if c["kind"] == "season_stat_leaders"]
        qual_cards = [c for c in exam["cards"] if c["kind"] == "qualification_stage_board"]
        bubble_cards = [c for c in exam["cards"] if c["selection_type"] == "bubble_50"]
        assert len(stat_cards) == 10
        assert len(qual_cards) == 10
        assert len(bubble_cards) == 3

        # Disjoint from the 10 calibration cards by slug, selector, and row market_ids
        calib = load_committed_kind_proposals()
        calib_cards = [
            c
            for p in calib["proposals"]
            for c in p["example_cards"]
        ]
        calib_slugs = {c["slug"] for c in calib_cards}
        exam_slugs = {c["slug"] for c in exam["cards"]}
        assert calib_slugs.isdisjoint(exam_slugs)

        def _selector_tuple(card: dict[str, Any]) -> tuple[str, str, str]:
            sel = card["selector"]
            assert sel.get("sport"), f"missing sport in selector on {card['slug']}"
            assert sel.get("title_ilike"), f"missing title_ilike in selector on {card['slug']}"
            assert sel.get("window"), f"missing window in selector on {card['slug']}"
            assert sel.get("selector"), f"missing selector rule in selector on {card['slug']}"
            return (
                str(sel["sport"]),
                str(sel["title_ilike"]),
                str(sel["selector"]),
            )

        calib_selectors = {_selector_tuple(c) for c in calib_cards}
        exam_selectors = {_selector_tuple(c) for c in exam["cards"]}
        assert len(calib_selectors) == 10
        assert len(exam_selectors) == 20
        assert calib_selectors.isdisjoint(exam_selectors)

        # Row market_id sets are distinct and share at most 1 market_id across any (exam, calibration) pair
        calib_id_sets = {
            frozenset(int(r["market_id"]) for r in c["rows"]) for c in calib_cards
        }
        exam_id_sets = {
            frozenset(int(r["market_id"]) for r in c["rows"]) for c in exam["cards"]
        }
        assert calib_id_sets.isdisjoint(exam_id_sets)
        for ec in exam["cards"]:
            e_ids = {int(r["market_id"]) for r in ec["rows"]}
            for cc in calib_cards:
                c_ids = {int(r["market_id"]) for r in cc["rows"]}
                assert len(e_ids & c_ids) <= 1, (
                    f"{ec['slug']} shares >1 market_ids with calibration card {cc['slug']}: {e_ids & c_ids}"
                )

        # All 10 calibration cards preserve graded_title (the pre-fix headings Alex graded)
        # and calibration_summary marks graded_on_pre_fix_headings=True
        for cc in calib_cards:
            assert cc.get("graded_title")
            assert cc["graded_title"] != cc["title"]
        cal_sum = exam["calibration_summary"]
        assert cal_sum["graded_on_pre_fix_headings"] is True
        assert cal_sum["counts_as_pass_on_new_titles"] is False
        assert cal_sum["season_stat_leaders"]["graded_on_pre_fix_headings"] is True
        assert cal_sum["season_stat_leaders"]["counts_as_pass_on_new_titles"] is False
        assert cal_sum["qualification_stage_board"]["graded_on_pre_fix_headings"] is True
        assert cal_sum["qualification_stage_board"]["counts_as_pass_on_new_titles"] is False

        # All 30 cards (10 calibration + 20 exam) reproduce title, subtitle, count_line, and selection_type
        # directly from compute_selection_carrying_title using the card's stored inputs
        for card in [*calib_cards, *exam["cards"]]:
            recomputed = compute_selection_carrying_title(
                card["rows"],
                total_member_count=card["member_count"],
                subject_unit=card["subject_unit"],
                race_name=card.get("race_name"),
                question_subtitle=card.get("question_subtitle") or "",
                selection_type=card["selection_type"],
                bubble_title=card.get("bubble_title"),
                unnumbered_count=int(card.get("unnumbered_count") or 0),
            )
            assert card["title"] == recomputed["title"], f"title mismatch on {card['slug']}"
            assert card["subtitle"] == recomputed["subtitle"], f"subtitle mismatch on {card['slug']}"
            assert card["count_line"] == recomputed["count_line"], f"count_line mismatch on {card['slug']}"
            assert card["selection_type"] == recomputed["selection_type"], f"selection_type mismatch on {card['slug']}"

        # Validator refuses a card whose title does not match compute_selection_carrying_title
        tampered_prop = copy.deepcopy(calib["proposals"][0])
        tampered_prop["example_cards"][0]["title"] = "Tampered non-reproducible headline"
        tampered_res = validate_proposed_grouping_kind(tampered_prop)
        assert tampered_res["ok"] is False
        assert str(tampered_res["reason"]).startswith("non_reproducible_selection_title:")

        # Served via load_grouping_grade_deck(slate_id="new-kinds-exam-test-2026-11")
        deck = load_grouping_grade_deck(slate_id=NEW_KINDS_EXAM_SLATE_ID)
        assert deck["slate_id"] == NEW_KINDS_EXAM_SLATE_ID
        assert len(deck["items"]) == 20
        for item in deck["items"]:
            for r in item["proposed_card"]["rows"]:
                assert 0 < r["probability"] < 1
                assert 0 <= r["rendered_percent"] <= 100
                assert r.get("observed_at")

        # Every row stamped at one time 8 days before as_of, or missing observed_at, is refused.
        raw_exam = json.loads(DEFAULT_NEW_KINDS_EXAM_JSON_PATH.read_text(encoding="utf-8"))
        stale_card = copy.deepcopy(raw_exam["cards"][0])
        for r in stale_card["rows"]:
            r["observed_at"] = "2026-11-01T12:00:00Z"
        missing_obs_card = copy.deepcopy(raw_exam["cards"][1])
        missing_obs_card["rows"][0].pop("observed_at", None)
        refused_exam_path = Path(__file__).resolve().parent / "_tmp_refused_exam_9937.json"
        try:
            refused_exam_path.write_text(
                json.dumps(
                    {
                        "slate_id": NEW_KINDS_EXAM_SLATE_ID,
                        "generated_at": "2026-11-10T16:50:00Z",
                        "cards": [stale_card, missing_obs_card],
                    }
                ),
                encoding="utf-8",
            )
            refused_exam = load_new_kinds_exam_cards(path=refused_exam_path)
            assert refused_exam["accepted_count"] == 0
            assert refused_exam["refused_count"] == 2
            reasons = [entry["reason"] for entry in refused_exam["refused"]]
            assert any(str(r).startswith("stale_quote:") for r in reasons)
            assert any(str(r).startswith("missing_observed_at:") for r in reasons)
        finally:
            refused_exam_path.unlink(missing_ok=True)
