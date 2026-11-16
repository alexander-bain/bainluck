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
            5000,
            passes=3,
            est_input_tokens_per_call=2000,
            est_output_tokens_per_call=1000,
        )
        assert not over_run.within_caps
        assert "CAP_EXCEEDED" in over_run.format_banner()

        # Exceeding the $30/month cap raises ValueError
        with pytest.raises(ValueError, match="spend cap exceeded"):
            run_sibling_family_exam(
                month_spent_before_usd=29.99, printer=lambda _: None
            )

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
        ungraded_cards = _graded_dataset(better_count=0, same_count=0, worse_count=0)
        record = score_sibling_family_exam(ungraded_cards)
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

    def test_109a_grade_mapping_pins_amazing_and_fine_to_better_and_no_to_worse_with_strict_reading(
        self,
    ) -> None:
        from app.routes.admin_ranking_eval import (
            EXAM_TEST_GROUPING_SLATE_ID,
            load_grouping_grade_deck,
        )
        from app.utils.sibling_family_exam import normalize_exam_human_grade

        assert normalize_exam_human_grade("amazing") == "better"
        assert normalize_exam_human_grade("fine") == "better"
        assert normalize_exam_human_grade("no") == "worse"
        assert normalize_exam_human_grade("shareable") == "better"
        assert normalize_exam_human_grade("interesting") == "better"
        assert normalize_exam_human_grade("neither") == "worse"
        assert normalize_exam_human_grade(None) is None

        cards = build_default_sibling_family_exam_dataset()
        # Every graded card's grade must name that card's own family_slug; ungraded cards stay null.
        graded_cards = [c for c in cards if c.get("human_grade") is not None]
        assert len(graded_cards) == 26
        graded_test = [c for c in graded_cards if c["split"] == "test"]
        graded_dev = [c for c in graded_cards if c["split"] == "dev"]
        assert len(graded_test) == 20
        assert len(graded_dev) == 6
        for c in cards:
            assert "graded_item_key" not in c
            if c.get("human_grade") is not None:
                assert c.get("graded_family_slug") == c["family_slug"]
            else:
                assert "graded_family_slug" not in c

        committed_record = score_sibling_family_exam(cards)
        assert committed_record["result"] == "PASS"
        assert committed_record["licences"] == {"sibling_family": "PASS"}
        g1_obs = committed_record["gate_results"][0]["observed"]
        assert g1_obs["graded_k"] == 20
        assert g1_obs["ungraded_k"] == 0
        assert g1_obs["better_k"] == 20
        assert g1_obs["worse_k"] == 0
        assert g1_obs["better_pct"] == 100.0
        assert g1_obs["better_wilson95"] == [83.9, 100.0]
        assert g1_obs["strict_amazing_k"] == 20
        assert g1_obs["strict_amazing_pct"] == 100.0
        assert g1_obs["graded_on_pre_fix_headings"] is False
        assert "83.9%" in g1_obs["grading_note"]

        p1_dev = committed_record["per_pass"]["1"]["dev"]
        assert p1_dev["expected"] == 12
        assert p1_dev["graded"] == 6
        assert p1_dev["ungraded"] == 6
        assert p1_dev["better"]["k"] == 6
        assert p1_dev["strict_amazing"]["k"] == 3

        # And the 20 fixed test cards are served on /grade/groupings as their own slate.
        test_deck = load_grouping_grade_deck(slate_id=EXAM_TEST_GROUPING_SLATE_ID)
        assert test_deck["slate_id"] == EXAM_TEST_GROUPING_SLATE_ID
        assert len(test_deck["items"]) == 20
        expected_test_slugs = [c["family_slug"] for c in cards if c["split"] == "test"]
        assert [it["item_key"] for it in test_deck["items"]] == expected_test_slugs

        # Verify 109-A scoring when all 20 test cards carry amazing/fine/no grades:
        synthetic_cards = copy.deepcopy(cards)
        test_idx = 0
        for c in synthetic_cards:
            if c["split"] != "test":
                continue
            if test_idx < 9:
                c["human_grade"] = "amazing"
            elif test_idx < 19:
                c["human_grade"] = "fine"
            else:
                c["human_grade"] = "no"
            test_idx += 1
        synthetic_record = score_sibling_family_exam(synthetic_cards)
        syn_obs = synthetic_record["gate_results"][0]["observed"]
        assert syn_obs["better_k"] == 19
        assert syn_obs["worse_k"] == 1
        assert syn_obs["graded_k"] == 20
        assert syn_obs["better_pct"] == 95.0
        assert syn_obs["strict_amazing_k"] == 9
        assert syn_obs["strict_amazing_pct"] == 45.0
        assert (
            syn_obs["grade_mapping"] == "109-A: amazing + fine -> better, no -> worse"
        )

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
            g
            for g in below_better["gate_results"]
            if g["id"] == "card_vs_single_member"
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
        g3 = next(g for g in record["gate_results"] if g["id"] == "freshness_and_count")
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
        assert (
            str(first_card["passes"]["1"]["members"][0]["market_id"]) not in serialized
        )

        md = format_sibling_family_exam_markdown(record)
        assert "card_vs_single_member" in md
        assert "relation_truth" in md
        assert "freshness_and_count" in md
        assert "run_to_run_stability" in md
        assert (
            "the interval's low end is `83.9%`, which is what `20` cards from one grader can show"
            in md
        )
        assert "**PASS**" in md

    def test_published_evals_json_and_docs_receipt_match_scorer_output_on_committed_dataset(
        self,
    ) -> None:
        from pathlib import Path

        from app.utils.sibling_family_exam import DEFAULT_EXAM_DATASET_PATH

        repo_root = Path(__file__).resolve().parents[2]
        evals_json_path = (
            repo_root
            / "frontend"
            / "lib"
            / "evals"
            / "data"
            / "sibling-family-exam-2026-11.json"
        )
        docs_md_path = (
            repo_root / "docs" / "discover" / "sibling-family-exam-2026-11.md"
        )

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
        assert (
            published_json["cost"]["actual_usd"]
            == raw_dataset["actual_cost_usd"]
            == 0.0167
        )
        assert (
            published_json["cost"]["input_tokens"]
            == raw_dataset["total_input_tokens"]
            == 58434
        )
        assert (
            published_json["cost"]["output_tokens"]
            == raw_dataset["total_output_tokens"]
            == 13224
        )

    def test_nhl_100_points_players_and_teams_never_mix_when_both_present(self) -> None:
        import asyncio
        from pathlib import Path

        from app.utils.roundup_containers import RoundupMembers, load_roundup_definition
        from app.utils.sibling_family import produce_sibling_family

        containers_dir = Path(__file__).resolve().parents[1] / "data" / "containers"
        liga_defn = load_roundup_definition(
            containers_dir / "liga-profesional-relegation-2026.json"
        )
        nhl_playoffs_defn = load_roundup_definition(
            containers_dir / "nhl-playoffs-2026-27.json"
        )
        assert (
            liga_defn["name"]
            == "Which club will be relegated from the 2026 Liga Profesional (Argentina)?"
        )
        assert (
            nhl_playoffs_defn["name"]
            == "Which team will make the 2026-27 NHL Playoffs?"
        )

        defn = {
            "slug": "nhl-players-100-points-2026-27",
            "name": "Which NHL player will record 100+ points in 2026-27?",
            "kind": "roundup",
            "category": "sports",
            "tag": "NHL",
            "kicker": "NHL · APR 30",
            "section_title": "2026-27 regular season",
            "footer": "Each player is their own market. They don't add up to 100%.",
            "membership": "sibling-family",
            "relations": ["same_measure", "same_window", "sibling"],
            "level": "grouped",
            "rule": {
                "producer": "sibling_family",
                "source": "polymarket",
                "group_id": "polymarket:1098356",
                "template": "Will * record 100+ points?",
                "title_template": "Which NHL player will record 100+ points in 2026-27?",
                "kicker_prefix": "NHL",
                "kicker_include_date": True,
                "subject_unit": "players",
                "outcome_name": "Yes",
                "lead_rule": "nearest_open_deadline",
                "closed_world": False,
                "min_numbered_members": 3,
                "card_rows": 5,
            },
        }

        shared_res = "2027-04-30T03:59:00+00:00"
        from datetime import datetime, timezone

        fresh_obs = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        mixed_pool_without_gids = [
            {
                "id": 63105212,
                "name": "Will Connor McDavid record 100+ points?",
                "status": "open",
                "source": "polymarket",
                "category": "hockey",
                "resolution_date": shared_res,
                "outcomes": [{"id": 1, "name": "Yes", "probability": 0.9235, "observed_at": fresh_obs}],
            },
            {
                "id": 63105213,
                "name": "Will Nathan MacKinnon record 100+ points?",
                "status": "open",
                "source": "polymarket",
                "category": "hockey",
                "resolution_date": shared_res,
                "outcomes": [{"id": 2, "name": "Yes", "probability": 0.877, "observed_at": fresh_obs}],
            },
            {
                "id": 63218794,
                "name": "Will Leon Draisaitl record 100+ points?",
                "status": "open",
                "source": "polymarket",
                "category": "hockey",
                "resolution_date": shared_res,
                "outcomes": [{"id": 3, "name": "Yes", "probability": 0.875, "observed_at": fresh_obs}],
            },
            {
                "id": 63218575,
                "name": "Will the Colorado Avalanche record 100+ points?",
                "status": "open",
                "source": "polymarket",
                "category": "hockey",
                "resolution_date": shared_res,
                "outcomes": [{"id": 4, "name": "Yes", "probability": 0.95, "observed_at": fresh_obs}],
            },
            {
                "id": 63218573,
                "name": "Will the Carolina Hurricanes record 100+ points?",
                "status": "open",
                "source": "polymarket",
                "category": "hockey",
                "resolution_date": shared_res,
                "outcomes": [{"id": 5, "name": "Yes", "probability": 0.91, "observed_at": fresh_obs}],
            },
        ]

        produced = asyncio.run(produce_sibling_family(mixed_pool_without_gids, defn))
        assert isinstance(produced, RoundupMembers)
        row_labels = [r["label"] for r in produced.rows]
        assert row_labels == ["Connor McDavid", "Nathan MacKinnon", "Leon Draisaitl"]
        assert "Colorado Avalanche" not in row_labels
        assert "Carolina Hurricanes" not in row_labels
        assert produced.sections[0]["title"] == "2026-27 regular season"

    def test_rules_1_and_2_quote_freshness_age_mark_and_top_k_unnumbered_refusal(
        self,
    ) -> None:
        from datetime import datetime, timezone

        from app.utils.roundup_containers import RoundupMembers, RoundupRefusal
        from app.utils.sibling_family import select_sibling_family

        now = datetime(2026, 11, 10, 18, 30, 0, tzinfo=timezone.utc)
        res_date = "2027-05-31T23:59:00Z"

        # 1. Clean cohort where one row is 9 hours old (>6h, <=7d): serves and passes observed_at
        # on every shown row so RoundupCard renders the age mark ("9h ago").
        clean_markets = [
            {
                "id": 7001,
                "name": "Will Club A finish top 8?",
                "status": "open",
                "source": "polymarket",
                "category": "soccer",
                "resolution_date": res_date,
                "outcomes": [
                    {
                        "id": 70011,
                        "name": "Yes",
                        "probability": 0.45,
                        "last_updated": "2026-11-10T18:10:00Z",
                    }
                ],
            },
            {
                "id": 7002,
                "name": "Will Monaco finish top 8?",
                "status": "open",
                "source": "polymarket",
                "category": "soccer",
                "resolution_date": res_date,
                "outcomes": [
                    {
                        "id": 70021,
                        "name": "Yes",
                        "probability": 0.31,
                        "last_updated": "2026-11-10T08:29:53Z",
                    }
                ],
            },
            {
                "id": 7003,
                "name": "Will Club C finish top 8?",
                "status": "open",
                "source": "polymarket",
                "category": "soccer",
                "resolution_date": res_date,
                "outcomes": [
                    {
                        "id": 70031,
                        "name": "Yes",
                        "probability": 0.25,
                        "last_updated": "2026-11-10T17:50:00Z",
                    }
                ],
            },
        ]
        served = select_sibling_family(clean_markets, now=now)
        assert isinstance(served, RoundupMembers)
        monaco_row = next(r for r in served.rows if r["label"] == "Monaco")
        assert monaco_row["observed_at"] == "2026-11-10T08:29:53Z"

        # 2. UECL top-8 specimen (polymarket:1024921): Brighton (28%, Oct 23, 18d old),
        # SC Freiburg (19%, Oct 18, 23d old), Twente (19%, Oct 22, 19d old) alongside
        # Monaco (31%, 9h old) -> stale quotes withheld and card refused.
        uecl_top8_specimen = [
            {
                "id": 62916634,
                "name": "Will Trabzonspor finish top 8 in UECL league phase?",
                "status": "open",
                "source": "polymarket",
                "category": "soccer",
                "resolution_date": res_date,
                "outcomes": [
                    {
                        "id": 1,
                        "name": "Yes",
                        "probability": 0.33,
                        "last_updated": "2026-11-03T15:31:24Z",
                    }
                ],
            },
            {
                "id": 62916655,
                "name": "Will Monaco finish top 8 in UECL league phase?",
                "status": "open",
                "source": "polymarket",
                "category": "soccer",
                "resolution_date": res_date,
                "outcomes": [
                    {
                        "id": 2,
                        "name": "Yes",
                        "probability": 0.31,
                        "last_updated": "2026-11-10T08:29:53Z",
                    }
                ],
            },
            {
                "id": 62916637,
                "name": "Will Brighton finish top 8 in UECL league phase?",
                "status": "open",
                "source": "polymarket",
                "category": "soccer",
                "resolution_date": res_date,
                "outcomes": [
                    {
                        "id": 3,
                        "name": "Yes",
                        "probability": 0.28,
                        "last_updated": "2026-10-23T07:00:35Z",
                    }
                ],
            },
            {
                "id": 62916658,
                "name": "Will SC Freiburg finish top 8 in UECL league phase?",
                "status": "open",
                "source": "polymarket",
                "category": "soccer",
                "resolution_date": res_date,
                "outcomes": [
                    {
                        "id": 4,
                        "name": "Yes",
                        "probability": 0.19,
                        "last_updated": "2026-10-18T20:46:24Z",
                    }
                ],
            },
            {
                "id": 62916641,
                "name": "Will Twente finish top 8 in UECL league phase?",
                "status": "open",
                "source": "polymarket",
                "category": "soccer",
                "resolution_date": res_date,
                "outcomes": [
                    {
                        "id": 5,
                        "name": "Yes",
                        "probability": 0.19,
                        "last_updated": "2026-10-22T23:09:47Z",
                    }
                ],
            },
        ]
        uecl_refusal = select_sibling_family(uecl_top8_specimen, now=now)
        assert isinstance(uecl_refusal, RoundupRefusal)
        assert (
            dict(uecl_refusal.reasons).get("family")
            == "unnumbered_members_could_change_top_rows"
        )
        assert "Brighton" in dict(uecl_refusal.reasons).get("stale_quotes_withheld", ())

        # 3. NHL 100-points specimen (polymarket:1098356): Kyle Connor's 41% is 24 days old
        # AND 18 unnumbered players (including Nathan MacKinnon and David Pastrnak) sit in
        # a top-5 cohort -> refused even if all priced players were fresh.
        nhl_specimen = [
            {
                "id": 63105212,
                "name": "Will Connor McDavid record 100+ points?",
                "status": "open",
                "source": "polymarket",
                "category": "hockey",
                "resolution_date": res_date,
                "outcomes": [
                    {
                        "id": 11,
                        "name": "Yes",
                        "probability": 0.80,
                        "last_updated": "2026-11-10T18:22:08Z",
                    }
                ],
            },
            {
                "id": 63105215,
                "name": "Will Nikita Kucherov record 100+ points?",
                "status": "open",
                "source": "polymarket",
                "category": "hockey",
                "resolution_date": res_date,
                "outcomes": [
                    {
                        "id": 12,
                        "name": "Yes",
                        "probability": 0.545,
                        "last_updated": "2026-11-10T18:22:08Z",
                    }
                ],
            },
            {
                "id": 63218794,
                "name": "Will Leon Draisaitl record 100+ points?",
                "status": "open",
                "source": "polymarket",
                "category": "hockey",
                "resolution_date": res_date,
                "outcomes": [
                    {
                        "id": 13,
                        "name": "Yes",
                        "probability": 0.47,
                        "last_updated": "2026-11-10T18:22:13Z",
                    }
                ],
            },
            {
                "id": 63218805,
                "name": "Will Kyle Connor record 100+ points?",
                "status": "open",
                "source": "polymarket",
                "category": "hockey",
                "resolution_date": res_date,
                "outcomes": [
                    {
                        "id": 14,
                        "name": "Yes",
                        "probability": 0.41,
                        "last_updated": "2026-10-17T17:53:03Z",
                    }
                ],
            },
            {
                "id": 63218801,
                "name": "Will Martin Necas record 100+ points?",
                "status": "open",
                "source": "polymarket",
                "category": "hockey",
                "resolution_date": res_date,
                "outcomes": [
                    {
                        "id": 15,
                        "name": "Yes",
                        "probability": 0.33,
                        "last_updated": "2026-11-06T20:45:07Z",
                    }
                ],
            },
            {
                "id": 63218824,
                "name": "Will Kirill Kaprizov record 100+ points?",
                "status": "open",
                "source": "polymarket",
                "category": "hockey",
                "resolution_date": res_date,
                "outcomes": [
                    {
                        "id": 16,
                        "name": "Yes",
                        "probability": 0.30,
                        "last_updated": "2026-11-10T18:00:00Z",
                    }
                ],
            },
            *[
                {
                    "id": 63219000 + idx,
                    "name": f"Will {player} record 100+ points?",
                    "status": "open",
                    "source": "polymarket",
                    "category": "hockey",
                    "resolution_date": res_date,
                    "outcomes": [{"id": 100 + idx, "name": "Yes", "probability": None}],
                }
                for idx, player in enumerate(
                    (
                        "Nathan MacKinnon",
                        "David Pastrnak",
                        "Auston Matthews",
                        "Mikko Rantanen",
                        "Mitch Marner",
                    )
                )
            ],
        ]
        nhl_refusal = select_sibling_family(nhl_specimen, now=now)
        assert isinstance(nhl_refusal, RoundupRefusal)
        assert (
            dict(nhl_refusal.reasons).get("family")
            == "unnumbered_members_could_change_top_rows"
        )

        # 4. Every row stamped at one identical time, 8 days before now -> refused.
        eight_days_ago = "2026-11-02T18:30:00Z"
        uniform_stale_cohort = [
            {
                "id": 8001 + idx,
                "name": f"Will Club {club} finish top 8?",
                "status": "open",
                "source": "polymarket",
                "category": "soccer",
                "resolution_date": res_date,
                "outcomes": [
                    {
                        "id": 80010 + idx,
                        "name": "Yes",
                        "probability": prob,
                        "last_updated": eight_days_ago,
                    }
                ],
            }
            for idx, (club, prob) in enumerate(
                (("Alpha", 0.72), ("Beta", 0.58), ("Gamma", 0.44))
            )
        ]
        uniform_stale_refusal = select_sibling_family(uniform_stale_cohort, now=now)
        assert isinstance(uniform_stale_refusal, RoundupRefusal)
        assert (
            dict(uniform_stale_refusal.reasons).get("family")
            == "unnumbered_members_could_change_top_rows"
        )
        assert dict(uniform_stale_refusal.reasons).get("stale_quotes_withheld") == (
            "Alpha",
            "Beta",
            "Gamma",
        )

        # 5. A priced row with no observation time does not count as fresh -> refused.
        missing_obs_cohort = [
            {
                "id": 8101,
                "name": "Will Club Alpha finish top 8?",
                "status": "open",
                "source": "polymarket",
                "category": "soccer",
                "resolution_date": res_date,
                "outcomes": [{"id": 81011, "name": "Yes", "probability": 0.72}],
            },
            {
                "id": 8102,
                "name": "Will Club Beta finish top 8?",
                "status": "open",
                "source": "polymarket",
                "category": "soccer",
                "resolution_date": res_date,
                "outcomes": [
                    {
                        "id": 81021,
                        "name": "Yes",
                        "probability": 0.58,
                        "last_updated": "2026-11-10T18:10:00Z",
                    }
                ],
            },
            {
                "id": 8103,
                "name": "Will Club Gamma finish top 8?",
                "status": "open",
                "source": "polymarket",
                "category": "soccer",
                "resolution_date": res_date,
                "outcomes": [
                    {
                        "id": 81031,
                        "name": "Yes",
                        "probability": 0.44,
                        "last_updated": "2026-11-10T18:10:00Z",
                    }
                ],
            },
        ]
        missing_obs_refusal = select_sibling_family(missing_obs_cohort, now=now)
        assert isinstance(missing_obs_refusal, RoundupRefusal)
        assert "Alpha" in dict(missing_obs_refusal.reasons).get(
            "stale_quotes_withheld", ()
        )

    def test_decision_123a_at_most_two_sibling_family_in_first_20_and_no_adjacent_grouped_cards(
        self,
    ) -> None:
        from app.utils.roundup_containers import (
            _is_roundup_bundle_card,
            _is_sibling_family_bundle,
            insert_roundup_feed_items,
        )

        # Build a 25-card Discover deck of ordinary futures/event cards.
        base_deck = [
            {
                "type": "futures",
                "score": float(100 - idx),
                "headline": f"Story {idx}",
                "data": {"id": 5000 + idx, "name": f"Market {idx}", "status": "open"},
            }
            for idx in range(25)
        ]

        def _make_roundup_bundle(
            slug: str,
            title: str,
            *,
            sibling: bool,
        ) -> dict:
            return {
                "type": "bundle",
                "score": 80.0,
                "headline": title,
                "data": {
                    "id": f"roundup:{slug}",
                    "title": title,
                    "kind": "roundup",
                    "story_key": f"roundup:{slug}",
                    "collection_ref": {
                        "slug": slug,
                        "href": f"/collections/{slug}",
                        "name": title,
                        "revision": 1,
                        "collection_count": 10,
                    },
                    "roundup": {
                        "kicker": "ROUNDUP",
                        "tag": "SPORTS",
                        "footer": "Each row is its own market.",
                        "relations": (
                            ["same_measure", "same_window", "sibling"]
                            if sibling
                            else ["same_window"]
                        ),
                        "level": "grouped",
                        "rows": [
                            {"label": f"{slug} row {i}", "probability": 0.5 - i * 0.05}
                            for i in range(3)
                        ],
                    },
                },
            }

        # Mix existing round-up cards ("By November 30", "By December 31") with 5 eligible sibling-family cards.
        roundup_cards = [
            _make_roundup_bundle("by-november-30", "By November 30", sibling=False),
            _make_roundup_bundle(
                "liga-profesional-relegation-2026",
                "Which clubs will be relegated from Argentina's Liga Profesional in 2026?",
                sibling=True,
            ),
            _make_roundup_bundle("by-december-31", "By December 31", sibling=False),
            _make_roundup_bundle(
                "nhl-playoffs-2026-27",
                "Which NHL team will make the 2026–27 playoffs?",
                sibling=True,
            ),
            _make_roundup_bundle(
                "gta-vi-album-features",
                "Will they be featured on GTA VI: The Album?",
                sibling=True,
            ),
            _make_roundup_bundle(
                "snow-first-flakes-2026",
                "Will it snow by November 15?",
                sibling=True,
            ),
            _make_roundup_bundle(
                "who-announces-before-2027",
                "Who will announce a 2028 presidential run before 2027?",
                sibling=True,
            ),
        ]

        seated = insert_roundup_feed_items(
            base_deck,
            roundup_cards,
            seat_floor=10,
            page_window=20,
        )

        # 1. At most 2 sibling-family cards in Discover's first 20 seats (indices 0..19).
        first_20_siblings = [
            it["data"]["id"] for it in seated[:20] if _is_sibling_family_bundle(it)
        ]
        assert len(first_20_siblings) == 2
        assert first_20_siblings == [
            "roundup:liga-profesional-relegation-2026",
            "roundup:nhl-playoffs-2026-27",
        ]

        # 2. The remaining 3 sibling-family cards seat after the first 20 seats (index >= 20).
        after_20_siblings = [
            it["data"]["id"] for it in seated[20:] if _is_sibling_family_bundle(it)
        ]
        assert len(after_20_siblings) == 3

        # 3. Never two grouped (round-up) cards in a row anywhere in the seated feed.
        grouped_indices = [
            idx for idx, it in enumerate(seated) if _is_roundup_bundle_card(it)
        ]
        assert len(grouped_indices) == 7
        for a, b in zip(grouped_indices, grouped_indices[1:]):
            assert b - a >= 2, f"Adjacent grouped cards at indices {a} and {b}"

    def test_insert_roundup_feed_items_terminates_with_one_non_sibling_and_pins_2_and_3_order(
        self,
    ) -> None:
        """Regression guard for the Nov 11 production hang: when exactly one
        non-sibling round-up is paired with sibling-family round-ups, the
        interleaving loop in ``insert_roundup_feed_items`` must advance and
        finish within a strict time limit, while preserving the existing
        interleaving order for 2 and 3 non-siblings.
        """
        import signal
        from app.utils.roundup_containers import (
            _is_roundup_bundle_card,
            insert_roundup_feed_items,
        )

        base_deck = [
            {
                "type": "futures",
                "score": float(100 - idx),
                "headline": f"Story {idx}",
                "data": {"id": 6000 + idx, "name": f"Market {idx}", "status": "open"},
            }
            for idx in range(25)
        ]

        def _make_roundup(slug: str, *, sibling: bool) -> dict:
            return {
                "type": "bundle",
                "score": 80.0,
                "headline": slug,
                "data": {
                    "id": f"roundup:{slug}",
                    "title": slug,
                    "kind": "roundup",
                    "story_key": f"roundup:{slug}",
                    "collection_ref": {
                        "slug": slug,
                        "href": f"/collections/{slug}",
                        "name": slug,
                        "revision": 1,
                        "collection_count": 10,
                    },
                    "roundup": {
                        "kicker": "ROUNDUP",
                        "tag": "SPORTS",
                        "footer": "Each row is its own market.",
                        "relations": (
                            ["same_measure", "same_window", "sibling"]
                            if sibling
                            else ["same_window"]
                        ),
                        "level": "grouped",
                        "rows": [
                            {"label": f"{slug} row {i}", "probability": 0.5 - i * 0.05}
                            for i in range(3)
                        ],
                    },
                },
            }

        def _run_with_timeout(roundup_cards: list[dict]) -> list[str]:
            def _on_alarm(_signum: int, _frame: object) -> None:
                raise TimeoutError("insert_roundup_feed_items timed out")

            prev_handler = signal.signal(signal.SIGALRM, _on_alarm)
            signal.setitimer(signal.ITIMER_REAL, 0.5)
            try:
                seated = insert_roundup_feed_items(
                    base_deck,
                    roundup_cards,
                    seat_floor=10,
                    page_window=20,
                )
            finally:
                signal.setitimer(signal.ITIMER_REAL, 0.0)
                signal.signal(signal.SIGALRM, prev_handler)
            return [
                it["data"]["id"] for it in seated if _is_roundup_bundle_card(it)
            ]

        ns1 = _make_roundup("ns-1", sibling=False)
        ns2 = _make_roundup("ns-2", sibling=False)
        ns3 = _make_roundup("ns-3", sibling=False)
        sib1 = _make_roundup("sib-1", sibling=True)
        sib2 = _make_roundup("sib-2", sibling=True)

        # Case 1: 1 non-sibling + 2 siblings (hung infinitely on master)
        assert _run_with_timeout([ns1, sib1, sib2]) == [
            "roundup:ns-1",
            "roundup:sib-1",
            "roundup:sib-2",
        ]

        # Case 2: 2 non-siblings + 2 siblings (pins existing order)
        assert _run_with_timeout([ns1, sib1, ns2, sib2]) == [
            "roundup:ns-1",
            "roundup:ns-2",
            "roundup:sib-1",
            "roundup:sib-2",
        ]

        # Case 3: 3 non-siblings + 2 siblings (pins existing order)
        assert _run_with_timeout([ns1, sib1, ns2, sib2, ns3]) == [
            "roundup:ns-1",
            "roundup:ns-2",
            "roundup:sib-1",
            "roundup:ns-3",
            "roundup:sib-2",
        ]

