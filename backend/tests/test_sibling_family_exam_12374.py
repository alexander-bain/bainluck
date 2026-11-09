"""Red-first tests for #12374: the sibling-family exam on set-aside cards.

PILLAR: DISCOVER / TRUTH · SHIP: Before model-proposed sibling cards reach
Discover, the model passes a scored exam on set-aside cards never used for
tuning (#12221 §3, Decide 61-A / 63-A).
"""

from __future__ import annotations

import copy
import json

import pytest

from app.utils.sibling_family_exam import (
    EXAM_PASSES,
    EXAM_SCHEMA_VERSION,
    MIN_TEST_CARDS,
    build_default_sibling_family_exam_dataset,
    estimate_sibling_family_exam_cost,
    export_sibling_family_exam_for_evals,
    format_sibling_family_exam_markdown,
    run_sibling_family_exam,
    score_sibling_family_exam,
    wilson95_interval,
)


def _graded_dataset(
    *,
    better_count: int = 18,
    same_count: int = 1,
    worse_count: int = 1,
) -> list[dict]:
    """Return a copy of the 32-card dataset with explicit human grades on the 20 test cards."""
    cards = copy.deepcopy(build_default_sibling_family_exam_dataset())
    test_idx = 0
    for card in cards:
        if card["split"] != "test":
            card["human_grade"] = "better"
            continue
        if test_idx < better_count:
            card["human_grade"] = "better"
        elif test_idx < better_count + same_count:
            card["human_grade"] = "same"
        elif test_idx < better_count + same_count + worse_count:
            card["human_grade"] = "worse"
        else:
            card["human_grade"] = None
        test_idx += 1
    return cards


class TestDatasetSplitAndSpendGuard:
    """#12374: dev + test split (20+ test cards) and Decide 61-A spend guard."""

    def test_default_dataset_has_at_least_20_held_out_test_cards_and_disjoint_ids(
        self,
    ) -> None:
        cards = build_default_sibling_family_exam_dataset()
        test_cards = [c for c in cards if c["split"] == "test"]
        dev_cards = [c for c in cards if c["split"] == "dev"]
        assert len(test_cards) >= MIN_TEST_CARDS
        assert len(test_cards) == 20
        assert len(dev_cards) == 12
        card_ids = [c["card_id"] for c in cards]
        assert len(set(card_ids)) == len(card_ids)

        dev_market_ids = {
            m["market_id"]
            for c in dev_cards
            for p in EXAM_PASSES
            for m in c["passes"][p]["members"]
        }
        test_market_ids = {
            m["market_id"]
            for c in test_cards
            for p in EXAM_PASSES
            for m in c["passes"][p]["members"]
        }
        assert dev_market_ids.isdisjoint(test_market_ids)

    def test_cost_estimate_prints_before_run_and_enforces_61a_caps(self) -> None:
        printed: list[str] = []
        record = run_sibling_family_exam(printer=printed.append)
        assert len(printed) == 1
        assert "[sibling_family_exam 61-A]" in printed[0]
        assert "estimated_cost=$" in printed[0]
        assert "status=OK" in printed[0]
        assert record["cost"]["actual_usd"] < 5.00

        # Exceeding the $5/run cap raises ValueError before scoring
        over_run = estimate_sibling_family_exam_cost(
            5000, passes=3, est_input_tokens_per_call=2000, est_output_tokens_per_call=1000
        )
        assert not over_run.within_caps
        assert "CAP_EXCEEDED" in over_run.format_banner()

        # Exceeding the $30/month cap raises ValueError
        with pytest.raises(ValueError, match="spend cap exceeded"):
            run_sibling_family_exam(month_spent_before_usd=29.99, printer=lambda _: None)

    def test_wilson95_interval_matches_reference_bounds(self) -> None:
        assert wilson95_interval(0, 0) == (0.0, 0.0)
        assert wilson95_interval(20, 20) == (83.9, 100.0)
        assert wilson95_interval(18, 20) == (69.9, 97.2)
        assert wilson95_interval(0, 20) == (0.0, 16.1)


class TestEveryGatePassOrFail:
    """#12374: measured gates return PASS or FAIL; ungraded Gate 1 returns HELD."""

    def test_baseline_ungraded_test_set_holds_gate_1_and_passes_structural_gates(
        self,
    ) -> None:
        record = score_sibling_family_exam(build_default_sibling_family_exam_dataset())
        assert record["schema"] == EXAM_SCHEMA_VERSION
        assert record["result"] == "HELD"
        assert record["licences"] == {"sibling_family": "HELD"}

        gates = {g["id"]: g for g in record["gate_results"]}
        assert set(gates.keys()) == {
            "card_vs_single_member",
            "relation_truth",
            "freshness_and_count",
            "run_to_run_stability",
        }
        assert gates["card_vs_single_member"]["result"] == "HELD"
        assert gates["card_vs_single_member"]["observed"]["better_k"] == 0
        assert gates["card_vs_single_member"]["observed"]["graded_k"] == 0
        assert gates["card_vs_single_member"]["observed"]["ungraded_k"] == 20
        assert gates["card_vs_single_member"]["observed"]["n"] == 20
        assert gates["card_vs_single_member"]["observed"]["better_pct"] is None
        assert gates["card_vs_single_member"]["observed"]["better_wilson95"] is None
        assert gates["relation_truth"]["result"] == "PASS"
        assert gates["freshness_and_count"]["result"] == "PASS"
        assert gates["run_to_run_stability"]["result"] == "PASS"
        assert gates["run_to_run_stability"]["observed"]["k"] == 32
        assert gates["run_to_run_stability"]["observed"]["n"] == 32

    def test_default_dataset_is_derived_from_real_proposer_and_nonzero_varied_api_usage(
        self,
    ) -> None:
        import json
        from app.utils.sibling_family_exam import DEFAULT_EXAM_DATASET_PATH

        raw = json.loads(DEFAULT_EXAM_DATASET_PATH.read_text(encoding="utf-8"))
        # Raw dataset stores candidate_markets and raw model replies, never pre-baked pass members
        for c in raw["cards"]:
            assert len(c["candidate_markets"]) >= 3
            for m in c["candidate_markets"]:
                assert int(m["id"]) >= 10_000_000
            for pid in ("1", "2", "3"):
                assert "members" not in c["passes"][pid]
                assert int(c["passes"][pid]["input_tokens"]) > 0
                assert int(c["passes"][pid]["output_tokens"]) > 0

        cards = build_default_sibling_family_exam_dataset()
        in_toks = {
            int(c["passes"][pid]["input_tokens"])
            for c in cards
            for pid in ("1", "2", "3")
        }
        out_toks = {
            int(c["passes"][pid]["output_tokens"])
            for c in cards
            for pid in ("1", "2", "3")
        }
        # Usage-rated OpenAI API replies vary across families/passes rather than uniform constants
        assert len(in_toks) >= 10
        assert len(out_toks) >= 5
        record = score_sibling_family_exam(cards)
        assert record["cost"]["basis"] == "usage_rated"
        assert record["cost"]["input_tokens"] == 58434
        assert record["cost"]["output_tokens"] == 13224
        assert record["cost"]["actual_usd"] > 0

    def test_partially_graded_test_set_holds_gate_1_and_computes_rate_and_wilson_over_graded_only(
        self,
    ) -> None:
        # 10 of 20 graded (9 Better, 1 Same, 10 ungraded): gate & headline stay HELD,
        # and rate + Wilson CI are computed over the 10 graded cards only (not /20).
        cards = _graded_dataset(better_count=9, same_count=1, worse_count=0)
        record = score_sibling_family_exam(cards)
        assert record["result"] == "HELD"
        assert record["licences"] == {"sibling_family": "HELD"}

        g1 = next(
            g for g in record["gate_results"] if g["id"] == "card_vs_single_member"
        )
        assert g1["result"] == "HELD"
        obs = g1["observed"]
        assert obs["graded_k"] == 10
        assert obs["ungraded_k"] == 10
        assert obs["better_k"] == 9
        assert obs["better_pct"] == 90.0
        assert obs["better_wilson95"] == list(wilson95_interval(9, 10))
        assert obs["worse_wilson95"] == list(wilson95_interval(0, 10))

        p1_test = record["per_pass"]["1"]["test"]
        assert p1_test["graded"] == 10
        assert p1_test["ungraded"] == 10
        assert p1_test["better"] == {
            "k": 9,
            "n": 10,
            "ungraded": 10,
            "pct": 90.0,
            "wilson95": list(wilson95_interval(9, 10)),
        }

    def test_all_four_gates_pass_when_human_grades_meet_85_better_and_10_worse_bars(
        self,
    ) -> None:
        # 18/20 (90%) Better >= 85%, 1/20 (5%) Worse <= 10%
        cards = _graded_dataset(better_count=18, same_count=1, worse_count=1)
        record = score_sibling_family_exam(cards, auto_publish_licensed=False)
        gates = {g["id"]: g["result"] for g in record["gate_results"]}
        assert gates == {
            "card_vs_single_member": "PASS",
            "relation_truth": "PASS",
            "freshness_and_count": "PASS",
            "run_to_run_stability": "PASS",
        }
        assert record["result"] == "PASS"
        assert record["licences"] == {"sibling_family": "HELD"}

        licensed_record = score_sibling_family_exam(cards, auto_publish_licensed=True)
        assert licensed_record["licences"] == {"sibling_family": "PASS"}

    def test_gate_1_fails_when_better_below_85_percent_or_worse_above_10_percent(
        self,
    ) -> None:
        # 16/20 (80%) Better < 85% -> FAIL
        below_better = score_sibling_family_exam(
            _graded_dataset(better_count=16, same_count=4, worse_count=0)
        )
        g1_below = next(
            g for g in below_better["gate_results"] if g["id"] == "card_vs_single_member"
        )
        assert g1_below["result"] == "FAIL"
        assert below_better["result"] == "FAIL"

        # 17/20 (85%) Better, but 3/20 (15%) Worse > 10% -> FAIL
        above_worse = score_sibling_family_exam(
            _graded_dataset(better_count=17, same_count=0, worse_count=3)
        )
        g1_worse = next(
            g for g in above_worse["gate_results"] if g["id"] == "card_vs_single_member"
        )
        assert g1_worse["result"] == "FAIL"
        assert above_worse["result"] == "FAIL"

    def test_gate_2_fails_on_parent_mismatch_or_duplicate_member(self) -> None:
        cards = _graded_dataset(better_count=19, same_count=1, worse_count=0)
        first_test = next(c for c in cards if c["split"] == "test")
        first_test["passes"]["2"]["members"][0]["parent_subject"] = "Unrelated event"

        record = score_sibling_family_exam(cards)
        g2 = next(g for g in record["gate_results"] if g["id"] == "relation_truth")
        assert g2["by_pass"]["1"]["result"] == "PASS"
        assert g2["by_pass"]["2"]["result"] == "FAIL"
        assert g2["result"] == "FAIL"
        assert record["result"] == "FAIL"

        # Duplicate member ID in Pass 1 -> FAIL
        cards_dup = _graded_dataset(better_count=19, same_count=1, worse_count=0)
        first_test_dup = next(c for c in cards_dup if c["split"] == "test")
        dup_id = first_test_dup["passes"]["1"]["members"][0]["market_id"]
        first_test_dup["passes"]["1"]["members"][1]["market_id"] = dup_id
        record_dup = score_sibling_family_exam(cards_dup)
        g2_dup = next(
            g for g in record_dup["gate_results"] if g["id"] == "relation_truth"
        )
        assert g2_dup["by_pass"]["1"]["duplicate_cards"] == 1
        assert g2_dup["result"] == "FAIL"

    def test_gate_2_fails_when_derived_member_market_does_not_belong_to_parent_through_build_default_dataset(
        self,
    ) -> None:
        from app.utils.sibling_family_exam import DEFAULT_EXAM_DATASET_PATH

        raw = json.loads(DEFAULT_EXAM_DATASET_PATH.read_text(encoding="utf-8"))
        # Append an unrelated candidate market to the first test card (leaving the first
        # two markets untouched so word-for-word quotes still verify).
        first_test_raw = next(c for c in raw["cards"] if c["split"] == "test")
        first_test_raw["candidate_markets"].append(
            {
                "id": 99990001,
                "name": "Will the Federal Reserve cut rates at the December 2026 FOMC meeting?",
                "source": first_test_raw["rule"]["source"],
                "status": "open",
                "yes_probability": 0.41,
                "description": "Resolves Yes if the FOMC lowers the target range in December 2026.",
            }
        )
        derived_cards = build_default_sibling_family_exam_dataset(raw_payload=raw)
        record = score_sibling_family_exam(derived_cards)
        g2 = next(g for g in record["gate_results"] if g["id"] == "relation_truth")
        assert g2["by_pass"]["1"]["k"] == 19
        assert g2["by_pass"]["1"]["n"] == 20
        assert g2["by_pass"]["1"]["result"] == "FAIL"
        assert g2["result"] == "FAIL"
        assert record["result"] == "FAIL"

    def test_gate_3_fails_on_settled_member_or_member_count_outside_3_to_6(
        self,
    ) -> None:
        cards = _graded_dataset(better_count=19, same_count=1, worse_count=0)
        first_test = next(c for c in cards if c["split"] == "test")
        first_test["passes"]["1"]["members"][0]["settled"] = True

        record = score_sibling_family_exam(cards)
        g3 = next(
            g for g in record["gate_results"] if g["id"] == "freshness_and_count"
        )
        assert g3["by_pass"]["1"]["result"] == "FAIL"
        assert g3["result"] == "FAIL"
        assert record["result"] == "FAIL"

        # Only 2 members -> FAIL
        cards_short = _graded_dataset(better_count=19, same_count=1, worse_count=0)
        first_test_short = next(c for c in cards_short if c["split"] == "test")
        first_test_short["passes"]["3"]["members"] = first_test_short["passes"]["3"][
            "members"
        ][:2]
        record_short = score_sibling_family_exam(cards_short)
        g3_short = next(
            g for g in record_short["gate_results"] if g["id"] == "freshness_and_count"
        )
        assert g3_short["by_pass"]["3"]["result"] == "FAIL"
        assert g3_short["result"] == "FAIL"

    def test_gate_4_fails_when_3_pass_agreement_drops_below_90_percent(self) -> None:
        cards = _graded_dataset(better_count=19, same_count=1, worse_count=0)
        # Default dataset starts at 32/32 agreed; mutating 4 cards -> 28/32 = 87.5% < 90%
        for idx in range(4):
            cards[idx]["passes"]["3"]["members"][0]["market_id"] = 999000 + idx
        record = score_sibling_family_exam(cards)
        g4 = next(
            g for g in record["gate_results"] if g["id"] == "run_to_run_stability"
        )
        assert g4["observed"]["k"] == 28
        assert g4["observed"]["n"] == 32
        assert g4["result"] == "FAIL"
        assert record["result"] == "FAIL"

    def test_export_and_markdown_receipt_contain_no_private_card_strings(self) -> None:
        dataset = build_default_sibling_family_exam_dataset()
        record = score_sibling_family_exam(dataset)
        exported = export_sibling_family_exam_for_evals(record)
        serialized = json.dumps(exported)
        first_card = dataset[0]
        assert str(first_card["card_id"]) not in serialized
        assert str(first_card["parent_subject"]) not in serialized
        assert str(first_card["passes"]["1"]["members"][0]["market_id"]) not in serialized

        md = format_sibling_family_exam_markdown(record)
        assert "card_vs_single_member" in md
        assert "relation_truth" in md
        assert "freshness_and_count" in md
        assert "run_to_run_stability" in md
        assert "Waiting for grades: 0 of 20 graded (20 ungraded)" in md
        assert "**HELD**" in md
        assert "**PASS**" in md

    def test_published_evals_json_and_docs_receipt_match_scorer_output_on_committed_dataset(
        self,
    ) -> None:
        from pathlib import Path

        from app.utils.sibling_family_exam import DEFAULT_EXAM_DATASET_PATH

        repo_root = Path(__file__).resolve().parents[2]
        evals_json_path = (
            repo_root / "frontend" / "lib" / "evals" / "data" / "sibling-family-exam-2026-11.json"
        )
        docs_md_path = repo_root / "docs" / "discover" / "sibling-family-exam-2026-11.md"

        record = run_sibling_family_exam(printer=lambda _: None)
        expected_json = export_sibling_family_exam_for_evals(record)
        expected_md = format_sibling_family_exam_markdown(
            record, cost_banner=record.get("cost_banner")
        )
        published_json = json.loads(evals_json_path.read_text(encoding="utf-8"))
        published_md = docs_md_path.read_text(encoding="utf-8")
        raw_dataset = json.loads(DEFAULT_EXAM_DATASET_PATH.read_text(encoding="utf-8"))

        assert published_json == expected_json
        assert published_md.strip() == expected_md.strip()
        assert published_json["cost"]["actual_usd"] == raw_dataset["actual_cost_usd"] == 0.0167
        assert published_json["cost"]["input_tokens"] == raw_dataset["total_input_tokens"] == 58434
        assert published_json["cost"]["output_tokens"] == raw_dataset["total_output_tokens"] == 13224
