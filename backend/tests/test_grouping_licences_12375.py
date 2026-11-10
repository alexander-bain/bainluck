"""Red-first tests for #12375: grouping kind licences, reviewed promotion, suspension, and second-kind exam.

PILLAR: TRUTH / DISCOVER · SHIP:
1. A licensed kind's proposal becomes a live card through the reviewed path;
   unexamined/ungraded kinds stay HELD or FAIL and cannot promote under a licence.
2. One wrong card served suspends the kind and stops new cards at the next run.
3. A second kind (``same_deadline_board``) runs its exam over real deadline
   markets and posts its FAIL.
"""

from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.utils.grouping_licences import (
    DEFAULT_CONTAINERS_DIR,
    DEFAULT_LICENCES_PATH,
    DEFAULT_SAME_DEADLINE_DATASET_PATH,
    build_default_same_deadline_board_exam_cases,
    build_lakers_next_3_games_proposal,
    default_grouping_licences_registry,
    detect_served_card_violation,
    format_same_deadline_board_exam_markdown,
    get_kind_licence_status,
    is_kind_licensed_for_promotion,
    load_grouping_licences,
    promote_licensed_proposal_to_definition,
    run_licensed_promotion_pass,
    score_same_deadline_board_exam,
    suspend_grouping_kind,
)
from app.utils.roundup_containers import (
    ROUNDUP_PRODUCERS,
    RoundupMembers,
    build_roundup_producer_from_definition,
    compose_roundup_container,
    compose_roundup_feed_item,
    load_roundup_definition,
)
from app.utils.subject_sequence import produce_subject_sequence

NOW_NOV_8 = datetime(2026, 11, 8, 22, 0, 0, tzinfo=timezone.utc)
OBS_NOV_8 = "2026-11-08T21:55:00Z"


def _sample_lakers_events() -> list[dict]:
    return [
        {
            "id": 15343927,
            "sport": "basketball_nba",
            "status": "scheduled",
            "commence_time": "2026-11-08T23:00:00Z",
            "home_team": "Detroit Pistons",
            "home_team_name": "Detroit Pistons",
            "away_team": "Los Angeles Lakers",
            "away_team_name": "Los Angeles Lakers",
            "home_team_data": {"name": "Detroit Pistons", "short_name": "Pistons"},
            "away_team_data": {"name": "Los Angeles Lakers", "short_name": "Lakers"},
            "hero_probability": 0.41,
            "hero_probability_away": 0.59,
            "hero_probability_source": "blend",
            "hero_probability_observed_at": OBS_NOV_8,
            "current_odds": {"home": 0.41, "away": 0.59},
        },
        {
            "id": 15341337,
            "sport": "basketball_nba",
            "status": "scheduled",
            "commence_time": "2026-11-10T00:00:00Z",
            "home_team": "Los Angeles Lakers",
            "home_team_name": "Los Angeles Lakers",
            "away_team": "Toronto Raptors",
            "away_team_name": "Toronto Raptors",
            "home_team_data": {"name": "Los Angeles Lakers", "short_name": "Lakers"},
            "away_team_data": {"name": "Toronto Raptors", "short_name": "Raptors"},
            "hero_probability": 0.68,
            "hero_probability_away": 0.32,
            "hero_probability_source": "blend",
            "hero_probability_observed_at": OBS_NOV_8,
            "current_odds": {"home": 0.68, "away": 0.32},
        },
        {
            "id": 15342583,
            "sport": "basketball_nba",
            "status": "scheduled",
            "commence_time": "2026-11-12T01:00:00Z",
            "home_team": "Milwaukee Bucks",
            "home_team_name": "Milwaukee Bucks",
            "away_team": "Los Angeles Lakers",
            "away_team_name": "Los Angeles Lakers",
            "home_team_data": {"name": "Milwaukee Bucks", "short_name": "Bucks"},
            "away_team_data": {"name": "Los Angeles Lakers", "short_name": "Lakers"},
            "hero_probability": 0.53,
            "hero_probability_away": 0.47,
            "hero_probability_source": "blend",
            "hero_probability_observed_at": OBS_NOV_8,
            "current_odds": {"home": 0.53, "away": 0.47},
        },
    ]


def _licensed_subject_sequence_registry() -> dict:
    reg = copy.deepcopy(default_grouping_licences_registry())
    reg["kinds"]["subject_sequence"]["status"] = "PASS"
    reg["kinds"]["subject_sequence"]["exam_as_of"] = "2026-11-08"
    reg["kinds"]["subject_sequence"]["exam_receipt"] = (
        "docs/discover/subject-sequence-exam-2026-11.md"
    )
    return reg


class TestExit1LicensedProposalBecomesLiveCardThroughReviewedPath:
    """#12375 Exit 1: a licensed kind's proposal becomes a live card through the reviewed path, while unexamined/ungraded kinds are held."""

    def test_live_licence_registry_holds_unexamined_and_ungraded_kinds(self) -> None:
        assert DEFAULT_LICENCES_PATH.exists()
        reg = load_grouping_licences()
        assert get_kind_licence_status(reg, "subject_sequence") == "HELD"
        assert reg["kinds"]["subject_sequence"]["exam_receipt"] is None
        assert is_kind_licensed_for_promotion(reg, "subject_sequence") is False
        assert get_kind_licence_status(reg, "sibling_family") == "PASS"
        assert is_kind_licensed_for_promotion(reg, "sibling_family") is True
        assert get_kind_licence_status(reg, "same_deadline_board") == "FAIL"
        assert is_kind_licensed_for_promotion(reg, "same_deadline_board") is False

    async def test_hand_authored_lakers_definition_and_licensed_promotion_path(
        self, tmp_path: Path
    ) -> None:
        # 1. Verify the committed hand-authored lakers-next-3-games.json in backend/data/containers/
        committed_path = DEFAULT_CONTAINERS_DIR / "lakers-next-3-games.json"
        assert committed_path.exists()
        defn = load_roundup_definition(committed_path)
        assert defn["slug"] == "lakers-next-3-games"
        assert "authored_by" not in defn
        assert "lakers-next-3-games" in ROUNDUP_PRODUCERS

        producer = build_roundup_producer_from_definition(defn)
        selection = await produce_subject_sequence(
            defn, _sample_lakers_events(), now=NOW_NOV_8
        )
        assert isinstance(selection, RoundupMembers)
        assert [m["event_id"] for m in selection.members] == [
            15343927,
            15341337,
            15342583,
        ]
        feed_item = compose_roundup_feed_item(producer, selection)
        assert feed_item is not None
        assert (
            feed_item["data"]["collection_ref"]["href"]
            == "/sport/basketball/nba/team/los-angeles-lakers"
        )
        assert feed_item["data"]["roundup"]["presentation"] == "strip"
        container = compose_roundup_container(producer, selection)
        assert container["slug"] == "lakers-next-3-games"
        assert container["state"] == "published"

        # 2. Verify that once a kind earns PASS with its exam_receipt, promote_licensed_proposal_to_definition
        # writes the reviewed definition file with authored_by.review_path == "tier-b-pr"
        licensed_reg = _licensed_subject_sequence_registry()
        proposal = build_lakers_next_3_games_proposal()
        outcome = promote_licensed_proposal_to_definition(
            proposal,
            registry=licensed_reg,
            output_dir=tmp_path,
            proposed_at="2026-11-08",
        )
        assert outcome.promoted is True
        assert outcome.slug == "lakers-next-3-games"
        assert outcome.definition is not None
        assert outcome.definition["membership"] == defn["membership"] == "subject_sequence"
        assert outcome.definition["authored_by"] == {
            "kind": "proposer",
            "proposer_kind": "subject_sequence",
            "licence_status": "PASS",
            "exam_receipt": "docs/discover/subject-sequence-exam-2026-11.md",
            "review_path": "tier-b-pr",
            "proposed_at": "2026-11-08",
        }
        assert (tmp_path / "lakers-next-3-games.json").exists()

    def test_unlicensed_or_receiptless_kinds_are_refused_promotion(self) -> None:
        reg = load_grouping_licences()
        subj_outcome = promote_licensed_proposal_to_definition(
            build_lakers_next_3_games_proposal(),
            registry=reg,
        )
        assert subj_outcome.promoted is False
        assert subj_outcome.reason == "kind_not_licensed:held"

        held_sib_reg = copy.deepcopy(reg)
        held_sib_reg["kinds"]["sibling_family"]["status"] = "HELD"
        sib_outcome = promote_licensed_proposal_to_definition(
            {"kind": "sibling_family", "slug": "sibling-fed-cuts"},
            registry=held_sib_reg,
        )
        assert sib_outcome.promoted is False
        assert sib_outcome.reason == "kind_not_licensed:held"

        # Under Decide 117-A, sibling_family is PASS and its 6 verified serve families
        # are promoted into backend/data/containers/ with clean reader-facing slugs,
        # proposal_id provenance, and review_path == "tier-b-pr"
        for promoted_slug, expected_proposal_id in (
            (
                "nhl-players-100-points-2026-27",
                "proposed-polymarket-will-contenders-record-100-points",
            ),
            (
                "uecl-top-8-2026-27",
                "proposed-polymarket-will-teams-finish-top-8-in-uecl-league-phase",
            ),
            (
                "uecl-playoff-places-2026-27",
                "proposed-polymarket-will-teams-finish-9th-24th-in-uecl-league-phase",
            ),
            (
                "liga-profesional-relegation-2026",
                "proposed-polymarket-will-contenders-be-relegated-from-the-2026-liga",
            ),
            (
                "mlb-world-series-pennant-2027",
                "proposed-polymarket-will-teams-advance-to-the-world-series-in-the-20",
            ),
            (
                "nhl-playoffs-2026-27",
                "proposed-polymarket-will-the-contenders-make-the-2026-27-nhl-playoff",
            ),
        ):
            assert not promoted_slug.startswith("proposed-")
            p_path = DEFAULT_CONTAINERS_DIR / f"{promoted_slug}.json"
            assert p_path.exists()
            p_defn = load_roundup_definition(p_path)
            assert p_defn["proposal_id"] == expected_proposal_id
            assert p_defn["destination_href"] == f"/collections/{promoted_slug}"
            assert p_defn["authored_by"]["proposer_kind"] == "sibling_family"
            assert p_defn["authored_by"]["licence_status"] == "PASS"
            assert p_defn["authored_by"]["review_path"] == "tier-b-pr"
            assert promoted_slug in ROUNDUP_PRODUCERS

        board_outcome = promote_licensed_proposal_to_definition(
            {"kind": "same_deadline_board", "slug": "by-january-31"},
            registry=reg,
        )
        assert board_outcome.promoted is False
        assert board_outcome.reason == "kind_not_licensed:fail"

        # A PASS entry without an exam_receipt is also refused
        bad_reg = copy.deepcopy(reg)
        bad_reg["kinds"]["subject_sequence"]["status"] = "PASS"
        bad_reg["kinds"]["subject_sequence"]["exam_receipt"] = None
        no_receipt_outcome = promote_licensed_proposal_to_definition(
            build_lakers_next_3_games_proposal(),
            registry=bad_reg,
        )
        assert no_receipt_outcome.promoted is False
        assert no_receipt_outcome.reason == "missing_exam_receipt"


class TestExit2SuspendingKindStopsNewCardsAtNextRun:
    """#12375 Exit 2: one wrong card served suspends the kind and stops new cards at the next run."""

    def test_wrong_served_card_automatically_suspends_kind_and_stops_new_cards(
        self, tmp_path: Path
    ) -> None:
        reg = _licensed_subject_sequence_registry()
        licences_file = tmp_path / "grouping_licences.json"
        out_dir = tmp_path / "containers"

        # Run 1 (while licensed, clean served cards): promotes candidate card
        clean_served_card = {
            "slug": "celtics-next-3-games",
            "members": [
                {"id": 1, "card": {"status": "scheduled"}},
                {"id": 2, "card": {"status": "scheduled"}},
                {"id": 3, "card": {"status": "scheduled"}},
            ],
            "rows": [
                {"probability": 0.62},
                {"probability": 0.55},
                {"probability": 0.71},
            ],
        }
        assert detect_served_card_violation(clean_served_card) is None

        run1 = run_licensed_promotion_pass(
            "subject_sequence",
            [build_lakers_next_3_games_proposal()],
            served_cards=[clean_served_card],
            registry=reg,
            licences_path=licences_file,
            output_dir=out_dir,
        )
        assert run1["stopped"] is False
        assert len(run1["promoted_definitions"]) == 1

        # Next run: one served card has a settled game in row 1 -> automatically suspends kind & stops promotion
        wrong_served_card = {
            "slug": "celtics-next-3-games",
            "members": [
                {"id": 1, "card": {"status": "completed"}},
                {"id": 2, "card": {"status": "scheduled"}},
                {"id": 3, "card": {"status": "scheduled"}},
            ],
        }
        assert detect_served_card_violation(wrong_served_card) == (
            "celtics-next-3-games",
            "Served settled member in row 1 (status=completed)",
        )

        next_proposal = {
            **build_lakers_next_3_games_proposal(),
            "slug": "knicks-next-3-games",
            "name": "New York Knicks: next 3 games",
        }
        run2 = run_licensed_promotion_pass(
            "subject_sequence",
            [next_proposal],
            served_cards=[wrong_served_card],
            registry=reg,
            licences_path=licences_file,
            output_dir=out_dir,
        )
        assert run2["stopped"] is True
        assert run2["stopped_reason"] == "kind_suspended"
        assert run2["licence_status"] == "SUSPENDED"
        assert run2["suspended_by_card_slug"] == "celtics-next-3-games"
        assert "status=completed" in run2["suspended_reason"]
        assert run2["promoted_definitions"] == []
        assert run2["refused_slugs"] == ["knicks-next-3-games"]
        assert not (out_dir / "knicks-next-3-games.json").exists()

        # Persisted licence file records SUSPENDED
        persisted = load_grouping_licences(licences_file)
        assert get_kind_licence_status(persisted, "subject_sequence") == "SUSPENDED"


class TestExit3SecondKindExamVerdict:
    """#12375 Exit 3: second kind (same_deadline_board) runs its exam over real deadline markets and posts its FAIL."""

    def test_default_cases_are_derived_from_real_market_dataset_through_select_same_deadline_board(
        self,
    ) -> None:
        assert DEFAULT_SAME_DEADLINE_DATASET_PATH.exists()
        raw_ds = json.loads(DEFAULT_SAME_DEADLINE_DATASET_PATH.read_text(encoding="utf-8"))
        assert raw_ds["schema"] == "same-deadline-board-exam-dataset/1"
        assert len(raw_ds["deadlines"]) == 20
        total_candidates = sum(len(d["candidate_markets"]) for d in raw_ds["deadlines"])
        assert total_candidates >= 70

        cases = build_default_same_deadline_board_exam_cases()
        assert len(cases) == 20
        passing = [c for c in cases if c["passes_supply_and_diversity"]]
        assert [c["deadline"] for c in passing] == [
            "2026-11-30",
            "2026-12-15",
            "2026-12-31",
            "2027-01-31",
            "2027-02-28",
            "2027-04-30",
            "2027-06-30",
        ]
        for c in passing:
            assert 4 <= len(c["selected_market_ids"]) <= 6
            assert all(isinstance(mid, int) and mid > 1_000_000 for mid in c["selected_market_ids"])
            assert c["distinct_categories"] >= 3
            assert c["all_same_calendar_day"] is True
            assert c["no_excluded_classes"] is True

    def test_same_deadline_board_exam_evaluates_all_four_gates_and_posts_fail(
        self,
    ) -> None:
        record = score_same_deadline_board_exam()
        assert record["kind"] == "same_deadline_board"
        assert record["candidate_deadlines"] == 20
        assert record["result"] == "FAIL"
        assert record["licence_status"] == "FAIL"

        gates = {g["id"]: g for g in record["gate_results"]}
        assert set(gates.keys()) == {
            "card_vs_single_member",
            "deadline_and_category_truth",
            "freshness_and_count",
            "run_to_run_stability",
        }
        assert gates["card_vs_single_member"]["result"] == "HELD"
        assert gates["card_vs_single_member"]["observed"]["graded_k"] == 0
        assert gates["card_vs_single_member"]["observed"]["ungraded_k"] == 20
        assert gates["deadline_and_category_truth"]["result"] == "FAIL"
        assert gates["deadline_and_category_truth"]["observed"]["k"] == 7
        assert gates["deadline_and_category_truth"]["observed"]["n"] == 20
        assert gates["freshness_and_count"]["result"] == "FAIL"
        assert gates["freshness_and_count"]["observed"]["k"] == 7
        assert gates["run_to_run_stability"]["result"] == "PASS"
        assert gates["run_to_run_stability"]["observed"]["k"] == 20

        md = format_same_deadline_board_exam_markdown(record)
        assert "same_deadline_board" in md
        assert "**FAIL**" in md
        assert "deadline_and_category_truth" in md

        # Verify sibling_family row is computed dynamically from sibling_record
        custom_sib = {
            "licences": {"sibling_family": "PASS"},
            "gate_results": [
                {"result": "PASS", "observed": {"graded_k": 20, "n": 20}},
                {"result": "PASS"},
                {"result": "PASS"},
                {"result": "PASS"},
            ],
        }
        md_custom = format_same_deadline_board_exam_markdown(
            record, sibling_record=custom_sib
        )
        assert "4/4 gates `PASS`, Gate 1 `20/20` graded) | **PASS**" in md_custom

        # Parity check with committed docs receipt and grouping_licences.json
        repo_root = DEFAULT_LICENCES_PATH.parents[2]
        receipt_path = repo_root / "docs" / "discover" / "same-deadline-board-exam-2026-11.md"
        assert receipt_path.read_text(encoding="utf-8").strip() == md.strip()
        assert load_grouping_licences() == default_grouping_licences_registry()

    def test_scorer_transitions_between_held_and_pass_when_gates_2_to_4_pass(
        self,
    ) -> None:
        ungraded_passing_cases = [
            {
                "deadline": f"2027-01-{i + 1:02d}",
                "title": f"By January {i + 1}",
                "selected_market_ids": [60000001, 60000002, 60000003, 60000004],
                "live_in_band_binary_members": 5,
                "distinct_categories": 4,
                "all_same_calendar_day": True,
                "no_excluded_classes": True,
                "deterministic_across_3_runs": True,
                "passes_supply_and_diversity": True,
                "human_grade": None,
            }
            for i in range(20)
        ]
        held_rec = score_same_deadline_board_exam(ungraded_passing_cases)
        assert held_rec["result"] == "HELD"
        assert held_rec["licence_status"] == "HELD"

        graded_passing_cases = [
            {**c, "human_grade": "better" if idx < 18 else "same"}
            for idx, c in enumerate(ungraded_passing_cases)
        ]
        pass_rec = score_same_deadline_board_exam(graded_passing_cases)
        assert pass_rec["result"] == "PASS"
        assert pass_rec["licence_status"] == "PASS"

    def test_canonical_team_page_href_uses_sport_hierarchy_and_refuses_unmapped_sport(
        self,
    ) -> None:
        from app.utils.subject_sequence import canonical_team_page_href

        assert (
            canonical_team_page_href("los-angeles-lakers", sport="basketball_nba")
            == "/sport/basketball/nba/team/los-angeles-lakers"
        )
        assert (
            canonical_team_page_href("real-madrid", sport="soccer_spain_la_liga")
            == "/sport/soccer/laliga/team/real-madrid"
        )
        with pytest.raises(ValueError, match="Unmapped sport/league"):
            canonical_team_page_href("mystery-fc", sport="curling_world")

    async def test_produce_and_build_subject_sequence_refuse_unmapped_sport_without_raising(
        self,
    ) -> None:
        from app.utils.roundup_containers import RoundupRefusal
        from app.utils.subject_sequence import (
            build_subject_sequence_producer,
            produce_subject_sequence,
        )

        unmapped_defn = {
            "slug": "mystery-fc-next-3-games",
            "membership": "subject_sequence",
            "kind": "roundup",
            "relations": ["same_subject", "same_measure", "same_window"],
            "level": "member",
            "kicker": "NEXT 3 GAMES",
            "name": "Mystery FC: next 3 games",
            "category": "curling",
            "tag": "CURLING",
            "section_title": "Next 3 games",
            "footer": "Combined win probability · next 3 games in schedule order",
            "rule": {
                "producer": "subject_sequence",
                "sport": "curling_world",
                "team_name": "Mystery FC",
                "team_short_name": "Mystery",
                "team_slug": "mystery-fc",
                "league": "curling",
                "window_days": 21,
                "count": 3,
            },
        }
        # 1. Construction must not raise ValueError on unmapped sport
        producer = build_subject_sequence_producer(
            unmapped_defn, now_fn=lambda: NOW_NOV_8
        )
        assert producer.slug == "mystery-fc-next-3-games"
        assert producer.destination_href == "/collections/mystery-fc-next-3-games"

        # 2. produce_subject_sequence must return RoundupRefusal(("unmapped_team_sport", ...))
        refusal = await produce_subject_sequence(
            unmapped_defn, _sample_lakers_events(), now=NOW_NOV_8
        )
        assert isinstance(refusal, RoundupRefusal)
        assert refusal.reasons == (("unmapped_team_sport", "curling_world"),)

        # 3. producer.produce(db) also returns RoundupRefusal cleanly
        prod_outcome = await producer.produce(_sample_lakers_events())
        assert isinstance(prod_outcome, RoundupRefusal)
        assert prod_outcome.reasons == (("unmapped_team_sport", "curling_world"),)

    async def test_evaluate_roundup_producer_suspends_kind_on_wrong_served_card_and_blocks_next_run(
        self, tmp_path: Path
    ) -> None:
        from app.utils.grouping_licences import save_grouping_licences
        from app.utils.roundup_containers import (
            RoundupProducer,
            evaluate_roundup_producer,
        )

        reg = _licensed_subject_sequence_registry()
        licences_file = tmp_path / "grouping_licences.json"
        save_grouping_licences(reg, licences_file)

        # Build a producer for subject_sequence that emits a violating card (a completed member)
        violating_producer = RoundupProducer(
            slug="violating-lakers-card",
            name="Los Angeles Lakers: next 3 games",
            kind="roundup",
            membership="subject_sequence",
            relations=("same_subject", "same_measure", "same_window"),
            level="member",
            category="nba",
            section_title="Next 3 games",
            footer="Combined win probability · next 3 games in schedule order",
            kicker="NEXT 3 GAMES",
            tag="NBA",
            destination_href="/sport/basketball/nba/team/los-angeles-lakers",
            rule={"producer": "subject_sequence", "cache": "none"},
            produce=lambda _db: RoundupMembers(
                members=[
                    {"id": 1, "event_id": 1, "status": "completed", "card": {"id": 1, "status": "completed"}},
                    {"id": 2, "event_id": 2, "status": "scheduled", "card": {"id": 2, "status": "scheduled"}},
                    {"id": 3, "event_id": 3, "status": "scheduled", "card": {"id": 3, "status": "scheduled"}},
                ],
                rows=[
                    {"event_id": 1, "label": "vs Grizzlies · Nov 10", "probability": 0.64},
                    {"event_id": 2, "label": "@ Pelicans · Nov 13", "probability": 0.58},
                    {"event_id": 3, "label": "vs Spurs · Nov 15", "probability": 0.53},
                ],
                footer="Combined win probability · next 3 games in schedule order",
                destination_href="/sport/basketball/nba/team/los-angeles-lakers",
            ),
        )

        # Evaluate the violating producer: it must refuse to serve and suspend subject_sequence
        fi_1, cp_1 = await evaluate_roundup_producer(
            violating_producer,
            [],
            licences_registry=reg,
            licences_path=licences_file,
        )
        assert fi_1 is None
        assert cp_1 is None
        assert get_kind_licence_status(reg, "subject_sequence") == "SUSPENDED"
        assert (
            reg["kinds"]["subject_sequence"]["suspended_by_card_slug"]
            == "violating-lakers-card"
        )

        # Next run of a valid subject_sequence producer is now skipped because the kind is SUSPENDED
        valid_defn = load_roundup_definition(
            DEFAULT_CONTAINERS_DIR / "lakers-next-3-games.json"
        )
        valid_producer = build_roundup_producer_from_definition(valid_defn)
        fi_2, cp_2 = await evaluate_roundup_producer(
            valid_producer,
            _sample_lakers_events(),
            licences_registry=reg,
            licences_path=licences_file,
        )
        assert fi_2 is None
        assert cp_2 is None
