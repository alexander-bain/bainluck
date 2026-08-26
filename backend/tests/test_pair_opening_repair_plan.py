"""The pair-opening complement repair, as a content-addressed plan.

CERT-403A's first P1 is the design brief:

    "The historical repair has no executable, immutable ApplyPlan and leaves two
     mandatory write semantics undecided ... an attended historical UPDATE cannot
     be certified from a prose predicate. There is no frozen row set, no per-row
     before value/CAS, no complete-content digest, no refusal vocabulary, no
     rollback record, and no chosen treatment for the stale American-odds twin.
     The apply could touch a different population when run and leave repaired
     rows indistinguishable from source quotes."

Every clause of that sentence is a test class below.

THE TWO DECISIONS, AND WHY THEY ARE TESTS RATHER THAN PROSE
-----------------------------------------------------------
* ``opening_american_odds`` **moves with the probability** — it is a pure
  function of it, so recomputing is not an invention while NULLing would make
  the row unique in its table. ``TestTheAmericanOddsTwinIsDecided``.
* Provenance is ``opening_source = 'pair_complement_repair'``, on the column
  that already exists. The staged spec called a missing provenance column a
  blocker on this half; it is not missing, so the blocker is discharged with no
  DDL and no migration. ``TestProvenanceIsMandatory``.

WHAT THIS FILE DOES NOT CLAIM
-----------------------------
That the repair is WORTH running. CAL-P097 re-derived that separately and the
answer moved a long way: **815 of 823** eligible Under legs already carry a
``calibration_probability``, and the published curve reads
``COALESCE(calibration_probability, opening_probability)``, so this apply
rewrites a column the curve does not read on 99.0% of its own population.
Measured per cell through the real coalesce, ``baseball/quantity`` moves
25.59 -> 25.09 and ``basketball/quantity`` and ``tennis/quantity`` do not move
at all. That is a decision for Alex, not a property of the rail — the rail's job
is to make the write impossible to perform unreviewed, and that is what is
tested here.
"""

from __future__ import annotations

import pytest

from app.utils.repair_apply_plan import (
    PAIR_OPENING_REPAIR_PLAN_SCHEMA,
    PAIR_OPENING_REPAIR_SOURCE,
    PAIR_OPENING_REVIEWED_FIELDS,
    REASON_PAIR_ALREADY_REPAIRED,
    REASON_PAIR_AMERICAN_DRIFT,
    REASON_PAIR_BEFORE_DRIFT_MULTI,
    REASON_PAIR_OBSERVATION_INCOMPLETE,
    REASON_PAIR_OPENING_DRIFT,
    REASON_PAIR_OUTCOME_MISSING,
    REASON_PAIR_SOURCE_DRIFT,
    REASON_PAIR_STAMPED_NOT_THIS_PLAN,
    REASON_PLAN_CORRUPT,
    REASON_PLAN_HASH_MISMATCH,
    PlannedPairOpeningRepair,
    bind_apply,
    build_pair_opening_repair_plan,
    decode_pair_opening_repair_plan,
    pair_opening_repair_gate,
)


def _row(
    outcome_id: int = 501,
    *,
    before: float = 0.30,
    over: float = 0.30,
    after: float | None = None,
    before_source: str | None = None,
    before_american: int | None = 233,
    after_american: int | None = -143,
) -> PlannedPairOpeningRepair:
    """One reviewed Under leg. Defaults are a real repairable specimen.

    Both legs stored at 0.30 (the identical-copy signature, pair sum 0.60, well
    outside the 0.02 tolerance); the Over leg's 0.30 is the real price by the
    measured direction result, so the Under leg's true opening is 0.70.
    """
    return PlannedPairOpeningRepair(
        outcome_id=outcome_id,
        market_id=9001,
        expected_before_opening=before,
        expected_before_american=before_american,
        expected_before_source=before_source,
        after_opening=(1 - over) if after is None else after,
        after_american=after_american,
        over_outcome_id=500,
        over_opening=over,
        market_name="Yankees vs Red Sox o/u 8.5",
    )


def _roundtrip(plan):
    """Serialize and decode, the way an attended apply actually loads a plan."""
    return decode_pair_opening_repair_plan(plan.as_payload())


class TestTheFrozenRowSet:
    """"There is no frozen row set" — there is one, and it is addressed."""

    def test_the_address_is_order_independent(self):
        a = build_pair_opening_repair_plan([_row(1), _row(2), _row(3)])
        b = build_pair_opening_repair_plan([_row(3), _row(1), _row(2)])
        assert a.plan_hash == b.plan_hash

    def test_the_address_moves_when_any_written_field_moves(self):
        base = build_pair_opening_repair_plan([_row()]).plan_hash
        assert build_pair_opening_repair_plan(
            [_row(after_american=-144)]
        ).plan_hash != base
        assert build_pair_opening_repair_plan(
            [_row(before=0.31, over=0.31)]
        ).plan_hash != base
        assert build_pair_opening_repair_plan([_row(502)]).plan_hash != base

    def test_the_address_moves_when_the_over_leg_moves(self):
        """The queue-368 ``sport_id`` lesson, one rail along.

        The Over leg is never written, but ``after_opening`` is defined as its
        complement. Left outside the digest, an edited Over price would keep the
        approved address and repair to a number nobody approved.
        """
        base = build_pair_opening_repair_plan([_row(over=0.30)]).plan_hash
        moved = build_pair_opening_repair_plan([_row(over=0.40)]).plan_hash
        assert moved != base

    def test_renaming_the_market_does_not_mint_a_new_address(self):
        """Prose for the reviewer must not invalidate an approval."""
        a = build_pair_opening_repair_plan([_row()])
        b_row = _row()
        b = build_pair_opening_repair_plan(
            [PlannedPairOpeningRepair(**{**b_row.__dict__, "market_name": "Other"})]
        )
        assert a.plan_hash == b.plan_hash

    def test_a_decoded_plan_re_derives_its_own_address(self):
        plan, reason = _roundtrip(build_pair_opening_repair_plan([_row(), _row(502)]))
        assert reason == "ok" and plan is not None
        assert plan.plan_hash == plan.as_payload()["plan_hash"]

    def test_an_edited_artifact_is_refused(self):
        payload = build_pair_opening_repair_plan([_row()]).as_payload()
        payload["rows"][0]["after"]["opening_probability"] = 0.65
        plan, reason = decode_pair_opening_repair_plan(payload)
        assert plan is None and reason == REASON_PLAN_CORRUPT

    def test_a_plan_from_another_rail_is_refused(self):
        payload = build_pair_opening_repair_plan([_row()]).as_payload()
        payload["schema"] = "team-identity-mapping-repair-plan/v2"
        plan, reason = decode_pair_opening_repair_plan(payload)
        assert plan is None and reason == REASON_PLAN_CORRUPT

    def test_the_schema_is_this_rails_own(self):
        assert PAIR_OPENING_REPAIR_PLAN_SCHEMA == (
            "pair-opening-complement-repair-plan/v1"
        )


class TestTheApplyIsBoundToTheReviewedPlan:
    """The cert's "could touch a different population when run", refused."""

    def test_the_operators_hash_must_match(self):
        plan = build_pair_opening_repair_plan([_row()])
        ok, reasons = bind_apply(plan, presented_hash=plan.plan_hash)
        assert ok and not reasons

    def test_a_different_plan_is_refused_by_name(self):
        plan = build_pair_opening_repair_plan([_row()])
        other = build_pair_opening_repair_plan([_row(999)])
        ok, reasons = bind_apply(plan, presented_hash=other.plan_hash)
        assert not ok and reasons == [REASON_PLAN_HASH_MISMATCH]

    def test_no_hash_at_all_is_refused(self):
        plan = build_pair_opening_repair_plan([_row()])
        ok, reasons = bind_apply(plan, presented_hash=None)
        assert not ok and reasons == [REASON_PLAN_HASH_MISMATCH]


class TestTheStructuralRefusals:
    """Four plans that would report success while doing the wrong thing."""

    def test_a_duplicate_outcome_id_is_refused(self):
        payload = build_pair_opening_repair_plan([_row(501), _row(501)]).as_payload()
        plan, reason = decode_pair_opening_repair_plan(payload)
        assert plan is None and reason == REASON_PLAN_CORRUPT

    def test_a_no_op_row_is_refused(self):
        """``before == after`` means ``p == 1 - p``, i.e. the 0.5000 pair.

        A no-op write reports ``rowcount = 1`` and changes nothing, so the row
        would be indistinguishable from a successful repair. It is also a real
        class, not a hypothetical: it is exactly the exact-0.5000 placeholder
        pair, which is not repairable by complement because its complement is
        itself.
        """
        payload = build_pair_opening_repair_plan(
            [_row(before=0.50, over=0.50)]
        ).as_payload()
        plan, reason = decode_pair_opening_repair_plan(payload)
        assert plan is None and reason == REASON_PLAN_CORRUPT

    def test_an_after_that_is_not_the_complement_is_refused(self):
        """The plan's licence is the measured direction result and nothing else."""
        payload = build_pair_opening_repair_plan(
            [_row(before=0.30, over=0.30, after=0.62)]
        ).as_payload()
        plan, reason = decode_pair_opening_repair_plan(payload)
        assert plan is None and reason == REASON_PLAN_CORRUPT

    @pytest.mark.parametrize("over", [0.0, 1.0])
    def test_a_probability_outside_the_open_interval_is_refused(self, over):
        payload = build_pair_opening_repair_plan(
            [_row(before=0.5, over=over)]
        ).as_payload()
        plan, reason = decode_pair_opening_repair_plan(payload)
        assert plan is None and reason == REASON_PLAN_CORRUPT

    def test_a_missing_field_is_corrupt_rather_than_decoding_as_none(self):
        payload = build_pair_opening_repair_plan([_row()]).as_payload()
        del payload["rows"][0]["over_opening"]
        plan, reason = decode_pair_opening_repair_plan(payload)
        assert plan is None and reason == REASON_PLAN_CORRUPT


class TestTheAmericanOddsTwinIsDecided:
    """"No chosen treatment for the stale American-odds twin" — it moves."""

    def test_the_after_odds_are_carried_and_addressed(self):
        plan = build_pair_opening_repair_plan([_row(after_american=-143)])
        assert plan.as_payload()["rows"][0]["after"]["opening_american_odds"] == -143
        other = build_pair_opening_repair_plan([_row(after_american=-142)])
        assert other.plan_hash != plan.plan_hash, (
            "the odds the apply writes are outside the address — an artifact "
            "could be edited to write different odds under an approved hash"
        )

    def test_the_before_odds_are_carried_for_rollback(self):
        plan = build_pair_opening_repair_plan([_row(before_american=233)])
        assert plan.as_payload()["rows"][0]["before"]["opening_american_odds"] == 233

    def test_a_null_before_odds_is_distinguishable_from_a_zero(self):
        """ABSENT is not EMPTY — ``digest_fields`` encodes None as ``-1:``."""
        a = build_pair_opening_repair_plan([_row(before_american=None)])
        b = build_pair_opening_repair_plan([_row(before_american=0)])
        assert a.plan_hash != b.plan_hash


class TestProvenanceIsMandatory:
    """"Leave repaired rows indistinguishable from source quotes" — they are not."""

    def test_every_row_carries_the_repair_stamp(self):
        plan = build_pair_opening_repair_plan([_row(), _row(502)])
        for row in plan.as_payload()["rows"]:
            assert row["after"]["opening_source"] == PAIR_OPENING_REPAIR_SOURCE

    def test_the_stamp_fits_the_existing_column(self):
        """``FuturesOutcome.opening_source`` is ``String(30)`` — no DDL needed.

        This is what discharges the staged spec's blocker ("if there is no
        column for it, that is a blocker on this half"). The column exists and
        already carries ``clob_history`` / ``first_snapshot`` /
        ``bid_ask_midpoint``, so a repaired opening is permanently
        distinguishable from a quote with no migration.
        """
        from app.models.models import FuturesOutcome

        length = FuturesOutcome.__table__.c.opening_source.type.length
        assert len(PAIR_OPENING_REPAIR_SOURCE) <= length

    def test_an_artifact_naming_a_different_stamp_is_refused(self):
        payload = build_pair_opening_repair_plan([_row()]).as_payload()
        payload["rows"][0]["after"]["opening_source"] = "clob_history"
        plan, reason = decode_pair_opening_repair_plan(payload)
        assert plan is None and reason == REASON_PLAN_CORRUPT


class TestThePerRowCAS:
    """"No per-row before value/CAS" — and a refusal vocabulary that discriminates.

    CERT-406A returned **BLOCK** on this class, and the finding is the reason the
    helper below now names three columns instead of two:

        "The live gate accepts source and American-odds drift ... a one-row plan
         expecting opening=0.30, opening_american_odds=233, opening_source=None
         returned (True, []) for all three hostile states: source changed to
         clob_history; American odds changed to 999; and both changed together
         while opening remained 0.30. That is not a per-row CAS over the plan's
         semantic write set."

    ``TestTheCASBindsEveryReviewedField`` is those three states, executed.
    """

    @staticmethod
    def _observed(opening, source=None, american=233):
        """A COMPLETE observation — all three reviewed columns.

        The default ``american=233`` is ``_row``'s default before-odds, so an
        observation built with no explicit odds is an UNCHANGED one. Two columns
        used to be enough here because the gate only read two; a partial mapping
        is now a named refusal, which is the point.
        """
        return {
            "opening_probability": opening,
            "opening_american_odds": american,
            "opening_source": source,
        }

    def test_an_unchanged_row_passes(self):
        plan = build_pair_opening_repair_plan([_row(501, before=0.30)])
        ok, drifted = pair_opening_repair_gate(plan, {501: self._observed(0.30)})
        assert ok and not drifted

    def test_a_rewritten_row_is_named_as_drift(self):
        plan = build_pair_opening_repair_plan([_row(501, before=0.30)])
        ok, drifted = pair_opening_repair_gate(plan, {501: self._observed(0.44)})
        assert not ok
        assert drifted[0]["reason_code"] == REASON_PAIR_OPENING_DRIFT
        assert drifted[0]["observed_opening"] == 0.44

    def test_a_vanished_row_is_a_DIFFERENT_named_reason(self):
        """MISSING and DRIFT send an operator at different next actions."""
        plan = build_pair_opening_repair_plan([_row(501)])
        ok, drifted = pair_opening_repair_gate(plan, {501: None})
        assert not ok and drifted[0]["reason_code"] == REASON_PAIR_OUTCOME_MISSING

    def test_an_already_repaired_row_is_not_reported_as_drift(self):
        """A resumed partial run must read as resumable, not as re-reviewable.

        Told this row "drifted", an operator would re-derive and re-approve a
        plan that had simply already done part of its work. The observation is
        this plan's own after-image: 0.70 = 1 - 0.30, odds -143, stamped.
        """
        plan = build_pair_opening_repair_plan([_row(501, before=0.30)])
        ok, drifted = pair_opening_repair_gate(
            plan,
            {501: self._observed(0.70, PAIR_OPENING_REPAIR_SOURCE, american=-143)},
        )
        assert not ok
        assert drifted[0]["reason_code"] == REASON_PAIR_ALREADY_REPAIRED
        assert drifted[0]["drifted_fields"] == []

    def test_one_drifted_row_does_not_cancel_its_siblings(self):
        """The failure ``create_gate`` and ``mapping_repair_gate`` both record.

        A wholesale refusal would let one live re-write throw away 822 approved
        repairs, so drift is reported per row and the caller drops only those.
        """
        plan = build_pair_opening_repair_plan(
            [_row(501, before=0.30), _row(502, before=0.30), _row(503, before=0.30)]
        )
        ok, drifted = pair_opening_repair_gate(
            plan,
            {
                501: self._observed(0.30),
                502: self._observed(0.99),
                503: self._observed(0.30),
            },
        )
        assert not ok
        assert [d["outcome_id"] for d in drifted] == [502]
        survivors = set(plan.outcome_ids) - {d["outcome_id"] for d in drifted}
        assert survivors == {501, 503}

    def test_a_row_the_plan_never_named_is_not_reachable(self):
        """The apply's work list is the plan, never a re-derivation."""
        plan = build_pair_opening_repair_plan([_row(501)])
        assert plan.outcome_ids == (501,)
        ok, _ = pair_opening_repair_gate(
            plan, {501: self._observed(0.30), 777: self._observed(0.30)}
        )
        assert ok, "an unrelated live row must not affect the reviewed set"


class TestTheCASBindsEveryReviewedField:
    """CERT-406A's P1, one test per hostile state it executed.

    The apply overwrites ``opening_probability``, ``opening_american_odds`` and
    ``opening_source``. All three are serialized into the payload's ``before``
    block and all three are inside ``digest_line``, so all three are part of the
    before-image the reviewer approved — and therefore all three are part of the
    write set the compare half has to bind. A CAS over a subset of its own write
    set silently authorises the rest.

    What each of these would have cost, concretely: a concurrent writer sets
    ``opening_source = 'clob_history'`` between dry-run and apply. The old gate
    said unchanged, the apply overwrote the source with
    ``pair_complement_repair``, and the rollback record — which is the ``before``
    block — now names a provenance the row did not have. Rolling back would
    RESTORE a value that was never there.
    """

    @staticmethod
    def _observed(opening=0.30, american=233, source=None):
        return {
            "opening_probability": opening,
            "opening_american_odds": american,
            "opening_source": source,
        }

    @staticmethod
    def _plan():
        """CERT-406A's specimen exactly: opening 0.30, odds 233, source NULL."""
        return build_pair_opening_repair_plan(
            [_row(501, before=0.30, before_american=233, before_source=None)]
        )

    def test_the_unmutated_specimen_is_eligible(self):
        """The control. Without it the three below could pass by refusing all rows."""
        ok, drifted = pair_opening_repair_gate(self._plan(), {501: self._observed()})
        assert ok and not drifted

    def test_hostile_source_drift_is_refused_and_named(self):
        """"source changed to clob_history" — returned ``(True, [])``."""
        ok, drifted = pair_opening_repair_gate(
            self._plan(), {501: self._observed(source="clob_history")}
        )
        assert not ok, "a row another writer has claimed is not an unchanged row"
        assert drifted[0]["reason_code"] == REASON_PAIR_SOURCE_DRIFT
        assert drifted[0]["drifted_fields"] == ["opening_source"]
        assert drifted[0]["observed"]["opening_source"] == "clob_history"
        assert drifted[0]["expected_before"]["opening_source"] is None

    def test_hostile_american_odds_drift_is_refused_and_named(self):
        """"American odds changed to 999" — returned ``(True, [])``."""
        ok, drifted = pair_opening_repair_gate(
            self._plan(), {501: self._observed(american=999)}
        )
        assert not ok
        assert drifted[0]["reason_code"] == REASON_PAIR_AMERICAN_DRIFT
        assert drifted[0]["drifted_fields"] == ["opening_american_odds"]
        assert drifted[0]["observed"]["opening_american_odds"] == 999
        assert drifted[0]["expected_before"]["opening_american_odds"] == 233

    def test_hostile_both_fields_drift_while_the_opening_holds(self):
        """"both changed together while opening remained 0.30" — ``(True, [])``.

        The reason code is deliberately not one of the two single-field codes: a
        single-field name on a two-field drift reads as a complete account of
        the damage and is not one. ``drifted_fields`` carries both regardless.
        """
        ok, drifted = pair_opening_repair_gate(
            self._plan(),
            {501: self._observed(opening=0.30, american=999, source="clob_history")},
        )
        assert not ok
        assert drifted[0]["reason_code"] == REASON_PAIR_BEFORE_DRIFT_MULTI
        assert drifted[0]["drifted_fields"] == [
            "opening_american_odds",
            "opening_source",
        ]
        assert drifted[0]["observed_opening"] == 0.30, (
            "the probability really is unchanged — that is what made this the "
            "hostile case the old gate could not see"
        )

    def test_a_one_field_mutation_retires_only_its_own_row(self):
        """Strictness must not become the wholesale refusal the rail forbids.

        CERT-406A's fix-sketch asks for both halves: each hostile one-field
        mutation fails, AND unchanged siblings remain eligible.
        """
        plan = build_pair_opening_repair_plan(
            [
                _row(501, before=0.30, before_american=233),
                _row(502, before=0.30, before_american=233),
                _row(503, before=0.30, before_american=233),
            ]
        )
        ok, drifted = pair_opening_repair_gate(
            plan,
            {
                501: self._observed(),
                502: self._observed(source="clob_history"),
                503: self._observed(american=999),
            },
        )
        assert not ok
        assert {d["outcome_id"]: d["reason_code"] for d in drifted} == {
            502: REASON_PAIR_SOURCE_DRIFT,
            503: REASON_PAIR_AMERICAN_DRIFT,
        }
        survivors = set(plan.outcome_ids) - {d["outcome_id"] for d in drifted}
        assert survivors == {501}

    def test_a_null_odds_twin_becoming_a_number_is_drift(self):
        """NULL -> 0 is not "still null". The gate compares NULL-ness, not truth.

        ``0`` is falsy and a legal American-odds value is never 0, so a
        normalising comparison would read this as unchanged. 232 of the 823
        reviewed rows carry no stored odds, so this is the majority-adjacent
        case, not an exotic one.
        """
        plan = build_pair_opening_repair_plan(
            [_row(501, before=0.30, before_american=None)]
        )
        ok, drifted = pair_opening_repair_gate(
            plan, {501: self._observed(american=0)}
        )
        assert not ok
        assert drifted[0]["reason_code"] == REASON_PAIR_AMERICAN_DRIFT

    def test_a_number_becoming_null_is_drift(self):
        ok, drifted = pair_opening_repair_gate(
            self._plan(), {501: self._observed(american=None)}
        )
        assert not ok
        assert drifted[0]["reason_code"] == REASON_PAIR_AMERICAN_DRIFT

    def test_an_observation_missing_a_reviewed_column_fails_CLOSED(self):
        """The silent version of the same bug, one layer up.

        A caller whose SELECT forgets ``opening_american_odds`` hands the gate a
        mapping where ``.get()`` returns ``None`` — indistinguishable from a
        genuinely NULL column. On the 232 reviewed rows whose odds ARE NULL that
        would compare equal and pass, so the whole widening could be defeated by
        a query, not by a writer. Refused by name instead (gotcha #53: an
        absence and a value must not arrive in the same shape).
        """
        plan = build_pair_opening_repair_plan(
            [_row(501, before=0.30, before_american=None)]
        )
        ok, drifted = pair_opening_repair_gate(
            plan, {501: {"opening_probability": 0.30, "opening_source": None}}
        )
        assert not ok
        assert drifted[0]["reason_code"] == REASON_PAIR_OBSERVATION_INCOMPLETE
        assert drifted[0]["unobserved_fields"] == ["opening_american_odds"]

    def test_the_reviewed_field_set_is_exactly_the_written_field_set(self):
        """The structural version of the finding, so it cannot regress quietly.

        Whatever the gate binds must equal what the payload's ``before`` block
        serializes and what the ``after`` block writes. Add a fourth written
        column later and this fails until the CAS is widened with it.
        """
        payload = build_pair_opening_repair_plan([_row()]).as_payload()["rows"][0]
        assert set(PAIR_OPENING_REVIEWED_FIELDS) == set(payload["before"])
        assert set(PAIR_OPENING_REVIEWED_FIELDS) == set(payload["after"])

    def test_a_stamped_row_holding_someone_elses_values_is_not_resumable(self):
        """"Already applied" is a claim about THIS plan, so THIS plan's after-image
        is the test — not the presence of the stamp.

        A bare stamp check would let a row that carries the provenance but not
        the approved value be reported as resumable and skipped without review,
        which is the one outcome the ALREADY_REPAIRED code exists to make safe.
        """
        plan = build_pair_opening_repair_plan([_row(501, before=0.30)])
        ok, drifted = pair_opening_repair_gate(
            plan,
            {
                501: self._observed(
                    opening=0.61, american=-143, source=PAIR_OPENING_REPAIR_SOURCE
                )
            },
        )
        assert not ok
        assert drifted[0]["reason_code"] == REASON_PAIR_STAMPED_NOT_THIS_PLAN
        assert drifted[0]["drifted_fields"] == ["opening_probability"]


class TestTheDerivedArtifact:
    """Properties of the committed 823-row plan, asserted on the artifact itself.

    These are not unit tests of the rail — they pin the EVIDENCE, so a
    re-derivation that quietly changed the population or the arithmetic fails
    here rather than at an attended apply.
    """

    @staticmethod
    def _artifact() -> dict:
        import json
        from pathlib import Path

        path = (
            Path(__file__).resolve().parents[2]
            / "artifacts"
            / "cal-p097"
            / "pair_opening_repair_plan.json"
        )
        assert path.exists(), f"the reviewed plan artifact is missing: {path}"
        return json.loads(path.read_text())

    def test_the_artifact_decodes_and_re_derives_its_own_address(self):
        payload = self._artifact()
        plan, reason = decode_pair_opening_repair_plan(payload)
        assert reason == "ok" and plan is not None
        assert plan.plan_hash == payload["plan_hash"]

    def test_the_widened_CAS_did_not_move_the_address(self):
        """CERT-406A's two P1s must not fix each other into a new bug.

        The CAS widening (``opening_source`` and ``opening_american_odds`` now
        bound by the live gate) touches the COMPARE half only. Both fields were
        already inside ``digest_line`` — that is precisely why they counted as
        reviewed before-image — so the reviewed 823-row write set still has the
        address the artifact was committed under. If this ever fails, the
        artifact must be re-derived and re-approved rather than re-labelled.
        """
        payload = self._artifact()
        assert payload["plan_hash"] == "17cead8e0e4e6c6ac9742f51e40a8804"

    def test_there_is_exactly_one_machine_readable_address(self):
        """CERT-406A P1#2: "two incompatible approved addresses for the same
        823-row plan" — the staged pack said ``84b01cd1...`` while the committed
        artifact said ``17cead8e...``.

        An attended apply cannot be released with two authoritative addresses:
        the hash IS the identity of the approved write set, so a second one
        leaves an operator unable to tell the reviewed plan from a superseded
        artifact. The prose copy is corrected in the pack; this stops a THIRD
        copy from being minted in code, where it would then be the one thing
        that never gets re-read.

        The rule the test enforces: **the address is read from the artifact,
        never restated.** ``decode_pair_opening_repair_plan`` already re-derives
        it and refuses a payload that disagrees, so no caller needs a literal.
        The one literal permitted is in this file, in the test above, whose
        entire job is to notice the address moving.
        """
        import re
        from pathlib import Path

        backend = Path(__file__).resolve().parents[1]
        this_file = Path(__file__).resolve()
        stale = "84b01cd1e837747152d5345b6d86541e"
        live = self._artifact()["plan_hash"]
        offenders = []
        for path in list(backend.rglob("*.py")) + list(backend.rglob("*.sql")):
            if path == this_file or ".venv" in path.parts or "node_modules" in path.parts:
                continue
            text = path.read_text(errors="ignore")
            for literal in (stale, live):
                if literal in text:
                    offenders.append(f"{path.relative_to(backend)} restates {literal}")
        assert not offenders, (
            "the plan address must be read from the artifact, not copied: "
            + "; ".join(offenders)
        )
        assert re.fullmatch(r"[0-9a-f]{32}", live), live

    def test_the_population_is_the_823_the_direction_evidence_covers(self):
        """CERT-403A P1#2: 823, not the 1,829 the staged spec priced."""
        payload = self._artifact()
        assert payload["row_count"] == 823
        assert payload["market_count"] == 823, "one Under leg per market, exactly"

    def test_every_written_probability_lands_on_the_columns_scale(self):
        """``opening_probability`` is ``Numeric(7, 6)``.

        Regression pin for a defect in the FIRST derivation of this artifact:
        ``1.0 - 0.32`` is 0.6799999999999999 in binary float, and
        ``probability_to_american`` turned that into -212 where the true
        complement gives -213. Eleven rows carried the off-by-one. A plan is a
        promise about exact values, so the arithmetic must land on the grid the
        column stores.
        """
        for row in self._artifact()["rows"]:
            p = row["after"]["opening_probability"]
            assert round(p, 6) == p, f"outcome {row['outcome_id']} writes {p!r}"

    def test_the_stored_american_odds_corroborate_the_repair_direction(self):
        """The row contains a SECOND witness, and it agrees with the repair.

        This is the strongest evidence the direction is right, and neither the
        staged spec nor CERT-403A used it. The corruption copied the Over leg's
        price onto the Under leg's ``opening_probability`` — but it did **not**
        touch ``opening_american_odds``, which kept the true Under-side value.

        Measured over the committed artifact: of the 781 rows carrying odds,
        **780 (99.9%) match the REPAIRED probability and 0 match the stored
        one**. So each of these rows already disagrees with itself, and the
        column that was not corrupted says exactly what ``under := 1 - p`` says.

        That converts the direction argument from a statistical one (win rate vs
        price over 823 graded pairs, r = 0.886) into a structural one: the
        repair restores agreement between two columns of the same row, rather
        than imposing a level inferred from outcomes.
        """
        from app.utils.odds_math import probability_to_american

        rows = self._artifact()["rows"]
        priced = [r for r in rows if r["before"]["opening_american_odds"] is not None]
        matches_repaired = sum(
            r["before"]["opening_american_odds"]
            == probability_to_american(r["after"]["opening_probability"])
            for r in priced
        )
        matches_stored = sum(
            r["before"]["opening_american_odds"]
            == probability_to_american(r["before"]["opening_probability"])
            for r in priced
        )
        assert matches_stored == 0, (
            "some stored odds agree with the stored probability — the premise "
            "that only opening_probability was corrupted does not hold"
        )
        assert matches_repaired / len(priced) > 0.99, (
            f"only {matches_repaired}/{len(priced)} stored odds corroborate the "
            f"repaired price; the direction evidence has weakened"
        )

    def test_the_artifact_carries_the_worth_warning(self):
        """The 99.0% coalesce finding travels WITH the plan, not beside it.

        An artifact that can be approved without seeing why it is worth far less
        than the record claims is an artifact that will be approved on the
        record's number.
        """
        context = self._artifact()["context"]
        assert "COALESCE" in context["worth_warning"]
        assert context["american_odds_treatment"] == (
            "recomputed from the repaired probability"
        )
        assert context["complete"] is True
