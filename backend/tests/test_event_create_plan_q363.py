"""The attended CREATE rail is bound to its plan (#1796/#1902, queue 363).

Alex, 2026-08-17, ruling the four MC decisions: *attended event-CREATE from
venue truth is APPROVED — for the Aug 5 game and as the ruled pattern (provider
anchors, plan artifact, pre-cert, always attended).*

This file exists because a create rail can fail in ways the two update rails
cannot, and every one of them is a way of writing a row nobody approved:

* **The before state is absence**, so there is no ``expected_before_id`` to
  compare against. If the existence check runs before the transaction rather
  than inside it, the rail has read a world its own write then changes — the
  #1798 defect in the create direction.
* **A doubleheader is two real games with the same clubs on the same day.** An
  existence check keyed on the matchup drops the second one silently. The
  328-game population contains doubleheaders, so this is a live hazard and not
  a hypothetical.
* **The reviewed object is a SET OF IDS.** Keyed on a COUNT it expires while
  nothing is wrong — the measured Aug 10-12 ``2/14 -> 16/0`` inversion, where
  the ordinary pipeline repaired rows between windows and the plan's premise
  evaporated without anything being broken.

Every test below is one of those failures, executed.
"""

from __future__ import annotations

import pytest

from app.utils.repair_apply_plan import (
    CREATE_PLAN_SCHEMA,
    REASON_PLAN_CORRUPT,
    REASON_PLAN_EMPTY,
    REASON_PLAN_HASH_MISMATCH,
    REASON_PLAN_MISSING,
    CreatePlan,
    PlannedCreate,
    bind_apply,
    build_create_plan,
    create_gate,
    decode_create_plan,
    mutations_outside_approved_keys,
)


def _row(truth_id: str, home: int = 10, away: int = 20, when: str = "2026-08-15T23:15:00+00:00"):
    return PlannedCreate(
        truth_id=truth_id,
        provider="espn",
        home_team_id=home,
        away_team_id=away,
        home_name="Pittsburgh Pirates",
        away_name="Boston Red Sox",
        commence_time=when,
        sport_id=3,
        label=f"Boston Red Sox @ Pittsburgh Pirates ({truth_id})",
    )


#: Row #1 of the 328 — Alex's own missing game (#1925).
SOX_AT_PIRATES = "401816534"
#: The Aug 5 MIN@KC game item 1 creates as population 1 (#1902).
AUG5_MIN_AT_KC = "401816407"


class TestThePlanIsContentAddressed:
    def test_the_same_rows_address_the_same_plan(self):
        a = build_create_plan([_row("1"), _row("2")])
        b = build_create_plan([_row("2"), _row("1")])
        assert a.plan_hash == b.plan_hash, "row ORDER must not change the address"

    def test_a_changed_club_is_a_different_plan(self):
        """Alex approves a list of GAMES. A plan that silently swapped a club
        while keeping the provider id must not pass as the reviewed one."""
        a = build_create_plan([_row("1")])
        b = build_create_plan(
            [
                PlannedCreate(
                    truth_id="1",
                    provider="espn",
                    home_team_id=10,
                    away_team_id=99,
                    home_name="Pittsburgh Pirates",
                    away_name="Chicago White Sox",
                    commence_time="2026-08-15T23:15:00+00:00",
                )
            ]
        )
        assert a.plan_hash != b.plan_hash

    def test_a_changed_start_time_is_a_different_plan(self):
        """The one place this rail deliberately differs from the binding rail.

        There, ``commence_time`` is outside the address because the rail only
        displays it. Here it is a VALUE BEING WRITTEN into a new row, so a plan
        whose start times moved since review is a plan the reviewer never saw.
        """
        a = build_create_plan([_row("1", when="2026-08-15T23:15:00+00:00")])
        b = build_create_plan([_row("1", when="2026-08-15T17:05:00+00:00")])
        assert a.plan_hash != b.plan_hash

    def test_relabelling_does_not_mint_a_new_address(self):
        """Prose assembled for the reviewer is not a written value."""
        a = build_create_plan([_row("1")])
        b_row = _row("1")
        b = build_create_plan(
            [
                PlannedCreate(
                    **{**b_row.as_payload(), "label": "reworded for the pack"}
                )
            ]
        )
        assert a.plan_hash == b.plan_hash

    def test_a_create_plan_never_collides_with_a_binding_plan(self):
        """Distinct namespaces. Two plans holding the same integers must not be
        interchangeable at an apply."""
        from app.utils.repair_apply_plan import BindingApplyPlan, PlannedBinding

        create = build_create_plan([_row("1")])
        binding = BindingApplyPlan(
            rows=(
                PlannedBinding(
                    event_id=1,
                    side="home",
                    expected_before_id=10,
                    before_name="Pittsburgh Pirates",
                    after_id=20,
                    after_name="Boston Red Sox",
                    defect="cross_club",
                ),
            )
        )
        assert create.plan_hash != binding.plan_hash


class TestTheApplyRefusesByName:
    def test_no_artifact_is_refused_as_missing(self):
        plan, reason = decode_create_plan(None)
        assert plan is None and reason == REASON_PLAN_MISSING
        ok, reasons = bind_apply(plan, decode_reason=reason, presented_hash="x")
        assert not ok and reasons == [REASON_PLAN_MISSING]

    def test_a_wrong_schema_is_refused_as_corrupt(self):
        plan, reason = decode_create_plan(
            {"schema": "event-team-binding-apply-plan/v1", "rows": []}
        )
        assert plan is None and reason == REASON_PLAN_CORRUPT

    def test_an_edited_artifact_is_refused_as_corrupt(self):
        """The stored address is RE-DERIVED, never believed."""
        payload = build_create_plan([_row("1")]).as_payload()
        payload["rows"][0]["away_team_id"] = 999
        plan, reason = decode_create_plan(payload)
        assert plan is None and reason == REASON_PLAN_CORRUPT

    def test_the_operator_presenting_a_stale_hash_is_refused(self):
        payload = build_create_plan([_row("1")]).as_payload()
        plan, reason = decode_create_plan(payload)
        ok, reasons = bind_apply(
            plan, decode_reason=reason, presented_hash="1f4158148d53c35da87efde6b40320b2"
        )
        assert not ok and reasons == [REASON_PLAN_HASH_MISMATCH]

    def test_an_empty_plan_applies_nothing(self):
        plan = build_create_plan([])
        ok, reasons = bind_apply(
            plan, decode_reason="ok", presented_hash=plan.plan_hash
        )
        assert not ok and reasons == [REASON_PLAN_EMPTY]

    def test_the_matching_hash_is_the_only_thing_that_proceeds(self):
        payload = build_create_plan([_row(SOX_AT_PIRATES)]).as_payload()
        plan, reason = decode_create_plan(payload)
        ok, reasons = bind_apply(
            plan, decode_reason=reason, presented_hash=payload["plan_hash"]
        )
        assert ok and reasons == []

    def test_a_duplicate_truth_id_cannot_decode(self):
        """Two rows for one provider id would create the same game twice."""
        payload = build_create_plan([_row("1"), _row("1")]).as_payload()
        plan, reason = decode_create_plan(payload)
        assert plan is None and reason == REASON_PLAN_CORRUPT

    def test_a_row_outside_the_plan_is_named(self):
        """The #1798 specimen, in the create direction: a game that became
        eligible AFTER review must be refused, not written."""
        plan = build_create_plan([_row(SOX_AT_PIRATES)])
        outside = mutations_outside_approved_keys(
            plan, ["espn:" + SOX_AT_PIRATES, "espn:401899999"]
        )
        assert outside == ["espn:401899999"]


class TestTheDoubleheaderHazard:
    """R5 hit this blind spot and R6 answered it in the merge primitive. The
    create rail must not learn it a third time."""

    def test_two_games_same_clubs_same_day_are_two_plan_rows(self):
        plan = build_create_plan(
            [
                _row("401816534", when="2026-08-15T17:05:00+00:00"),
                _row("401816535", when="2026-08-15T23:15:00+00:00"),
            ]
        )
        assert len(plan.rows) == 2
        assert plan.duplicate_truth_ids() == []

    def test_a_doubleheader_is_reported_not_suppressed(self):
        plan = build_create_plan(
            [
                _row("401816534", when="2026-08-15T17:05:00+00:00"),
                _row("401816535", when="2026-08-15T23:15:00+00:00"),
                _row("401816600", when="2026-08-16T23:15:00+00:00"),
            ]
        )
        assert plan.doubleheaders() == ["401816534", "401816535"]

    def test_the_row_key_is_the_truth_id_not_the_matchup(self):
        """If the row key were (clubs, date), the twin bill would collapse to
        one work item and the second game would never be created."""
        plan = build_create_plan(
            [
                _row("401816534", when="2026-08-15T17:05:00+00:00"),
                _row("401816535", when="2026-08-15T23:15:00+00:00"),
            ]
        )
        assert plan.row_keys == ("espn:401816534", "espn:401816535")
        assert len(set(plan.row_keys)) == 2


class TestTheTruthIdGate:
    """*Apply may proceed only when a re-derivation at apply time produces a
    MISSING id set whose intersection with THIS set is THIS set.*"""

    def test_all_still_missing_passes(self):
        plan = build_create_plan([_row("1"), _row("2")])
        ok, no_longer = create_gate(plan, ["1", "2", "3"])
        assert ok and no_longer == []

    def test_an_id_created_since_review_is_named_not_silently_dropped(self):
        """The ordinary pipeline creating a game between review and apply is the
        system working. It is still an id the plan may not act on."""
        plan = build_create_plan([_row("1"), _row("2")])
        ok, no_longer = create_gate(plan, ["1"])
        assert not ok
        assert no_longer == ["2"]

    def test_one_upstream_create_does_not_cancel_the_approved_siblings(self):
        """A wholesale refusal would let one row veto 327. The gate names the
        casualty and the caller keeps the rest."""
        plan = build_create_plan([_row(str(i)) for i in range(10)])
        _, no_longer = create_gate(plan, [str(i) for i in range(1, 10)])
        survivors = [r for r in plan.rows if r.truth_id not in set(no_longer)]
        assert no_longer == ["0"]
        assert len(survivors) == 9

    def test_the_gate_compares_sets_not_counts(self):
        """The Aug 10-12 ``2/14 -> 16/0`` inversion: the COUNT matched while the
        membership had completely turned over. A count-keyed gate waves that
        through; a set-keyed gate refuses it."""
        plan = build_create_plan([_row("1"), _row("2")])
        rederived = ["8", "9"]  # same COUNT, disjoint membership
        assert len(rederived) == len(plan.truth_ids)
        ok, no_longer = create_gate(plan, rederived)
        assert not ok
        assert no_longer == ["1", "2"]


class TestTheRealPopulations:
    """Bound to the two populations Alex actually ruled on, so a refactor that
    breaks them fails here rather than in production."""

    def test_population_one_is_the_aug_5_game(self):
        plan = build_create_plan(
            [
                PlannedCreate(
                    truth_id=AUG5_MIN_AT_KC,
                    provider="espn",
                    home_team_id=118,
                    away_team_id=142,
                    home_name="Kansas City Royals",
                    away_name="Minnesota Twins",
                    commence_time="2026-08-05T23:40:00+00:00",
                    sport_id=3,
                )
            ]
        )
        assert plan.truth_ids == (AUG5_MIN_AT_KC,)
        assert plan.duplicate_truth_ids() == []
        ok, _ = bind_apply(plan, presented_hash=plan.plan_hash)
        assert ok

    def test_the_reviewed_328_set_is_the_gate_input(self):
        """The staged artifact's own id set. If this file and the artifact ever
        disagree about what was approved, the disagreement surfaces here."""
        import json
        import pathlib

        artifact = (
            pathlib.Path(__file__).resolve().parents[2]
            / ".claude/handoff/ARTIFACT-Q362-POPULATION-2-CREATE-SET.json"
        )
        if not artifact.exists():  # handoff dir is gitignored; CI has no copy
            pytest.skip("handoff artifact not present in this checkout")
        data = json.loads(artifact.read_text())
        assert data["id_count"] == 328
        assert SOX_AT_PIRATES in data["truth_ids"], "row #1, Alex's missing game"
        assert AUG5_MIN_AT_KC in data["truth_ids"], "population 1 is a subset of 328"


def test_the_schema_is_pinned():
    """Bumping it invalidates every artifact in flight, which is correct — but
    it must be a decision, not a drift."""
    assert CREATE_PLAN_SCHEMA == "event-create-from-truth-plan/v1"
    assert CreatePlan().as_payload()["schema"] == CREATE_PLAN_SCHEMA
