"""#5343 / #5344 — the three membership defects CERT-4043 reproduced, each guarded.

SHIP: a provider event's collection keeps every member through a roster outage,
never trusts a parent that names another event, and is never offered to readers
while its stored membership differs from what the pass proves. Pillars:
MATCHING / DISCOVER / TRUTH.

1. 5343-EXPIRED-ROSTER-DELETION — an expired (or undated) roster that no longer
   lists a member CARRIES it; only a roster fresh at the pass instant removes.
2. 5343-PARENT-IDENTITY-CONFLICT — a parent whose metadata names another event
   is a conflict: no roster, no header, no eligibility.
3. 5343-PREFLIGHT-STORED-MEMBERSHIP — the publication preflight compares the
   stored slots (every source, every child type, child containers) to the
   assembly and refuses any missing, extra or reclassified one.

Each class pairs the refusal with the healthy control on the same data, so a
guard that refused everything would fail its control.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.tasks import provider_event_collection_assembly as writer
from app.utils import provider_event_collections as pec
from app.utils.provider_event_collections import (
    CARRIED_ROSTER_NOT_FRESH,
    CARRIED_ROW_ABSENT,
    EDGE_CLASS,
    EXCLUDED_GROUP_ANCHOR,
    EXCLUDED_IDENTITY_CONFLICT,
    EXCLUDED_NOT_IN_ROSTER,
    INELIGIBLE_IDENTITY_CONFLICTS,
    INELIGIBLE_MEMBERS_CARRIED,
    INELIGIBLE_ROSTER_EXPIRED,
    INELIGIBLE_STORED_MISSING,
    INELIGIBLE_STORED_UNPROVED,
    ROSTER_MAX_AGE,
    ROSTER_PARENT_CONFLICT,
    PriorDecision,
    assemble_event,
    header_changes,
    identity_from_group_id,
    plan_event_pass,
    provider_row,
    publication_eligibility,
    stored_membership_refusals,
)
from tests.provider_event_fixtures_5343 import ingested_rows, load_gamma, roster_payload

OBSERVED = datetime(2026, 10, 12, 0, 49, 13, tzinfo=timezone.utc)
EVENT = "1038648"
IDENTITY = identity_from_group_id(f"polymarket:{EVENT}")


def _raw():
    return ingested_rows(
        load_gamma(EVENT), "geopolitics", first_id=1000, roster_at=OBSERVED
    )


def _prior(assembly) -> dict:
    return {
        d.child_id: PriorDecision(
            d.child_id,
            d.reason,
            d.evidence.get("external_id"),
            (
                datetime.fromisoformat(d.evidence["applied_roster_at"])
                if d.evidence.get("applied_roster_at")
                else None
            ),
            d.evidence.get("applied_roster_digest"),
        )
        for d in assembly.decisions
    }


def _applied():
    """A six-member collection as one fresh pass leaves it."""
    raw = _raw()
    a = assemble_event(IDENTITY, [provider_row(r) for r in raw], now=OBSERVED)
    assert len(a.kept) == 6 and a.complete
    return raw, a


def _dropping(raw, victim_external_id, observed_at):
    raw[0]["market_metadata"][pec.ROSTER_KEY] = roster_payload(
        load_gamma(EVENT), observed_at, drop=(victim_external_id,)
    )
    return [provider_row(r) for r in raw]


def _victim(raw, a):
    child_id = sorted(a.kept)[0]
    return child_id, next(r["external_id"] for r in raw if r["id"] == child_id)


# ---------------------------------------------------------------------------
# 1. An expired roster is an outage: it carries, it never removes
# ---------------------------------------------------------------------------


class TestExpiredRosterCarries:
    STAMP = OBSERVED + timedelta(minutes=1)  # newer than the applied roster

    def _next(self, now, *, rows=None):
        raw, a = _applied()
        victim, external = _victim(raw, a)
        rows = rows or _dropping(raw, external, self.STAMP)
        b = assemble_event(IDENTITY, rows, edged=a.kept, prior=_prior(a), now=now)
        return a, b, victim

    def test_the_reviewers_case_keeps_the_member(self):
        """CERT-4043: stamped T+1min, evaluated T+8h, deletes was (1001,)."""
        a, b, victim = self._next(OBSERVED + timedelta(hours=8))
        assert plan_event_pass(b, a.kept).deletes == ()
        assert victim in b.kept
        decision = next(d for d in b.decisions if d.child_id == victim)
        assert decision.reason == CARRIED_ROSTER_NOT_FRESH
        assert decision.keep_edge and decision.outcome == pec.OUTCOME_WITHHELD
        assert not b.roster_subtracts and not b.complete
        reasons = publication_eligibility(b, now=OBSERVED + timedelta(hours=8)).reasons
        assert INELIGIBLE_ROSTER_EXPIRED in reasons
        assert INELIGIBLE_MEMBERS_CARRIED in reasons

    def test_the_same_roster_fresh_removes_the_member(self):
        """Control on the same data: a confirmed fresh removal still retires."""
        a, b, victim = self._next(self.STAMP + timedelta(hours=1))
        assert plan_event_pass(b, a.kept).deletes == (victim,)
        assert b.roster_subtracts and b.complete
        assert (
            next(d for d in b.decisions if d.child_id == victim).reason
            == EXCLUDED_NOT_IN_ROSTER
        )

    def test_the_age_boundary_is_inclusive(self):
        a, at_edge, victim = self._next(self.STAMP + ROSTER_MAX_AGE)
        assert plan_event_pass(at_edge, a.kept).deletes == (victim,)
        a, past, victim = self._next(self.STAMP + ROSTER_MAX_AGE + timedelta(seconds=1))
        assert plan_event_pass(past, a.kept).deletes == ()

    def test_a_pass_that_cannot_date_the_roster_removes_nothing(self):
        raw, a = _applied()
        victim, external = _victim(raw, a)
        b = assemble_event(
            IDENTITY,
            _dropping(raw, external, self.STAMP),
            edged=a.kept,
            prior=_prior(a),
        )
        assert plan_event_pass(b, a.kept).deletes == ()
        assert not b.roster_subtracts

    def test_an_expired_roster_cannot_retire_a_vanished_row(self):
        raw, a = _applied()
        victim, external = _victim(raw, a)
        rows = [r for r in _dropping(raw, external, self.STAMP) if r.id != victim]
        b = assemble_event(
            IDENTITY,
            rows,
            edged=a.kept,
            prior=_prior(a),
            now=OBSERVED + timedelta(hours=8),
        )
        assert victim in b.kept
        assert next(d for d in b.decisions if d.child_id == victim).reason == (
            CARRIED_ROW_ABSENT
        )

    def test_an_expired_roster_still_keeps_an_unedged_dropped_market_out(self):
        """It adds no edge for a market it does not list; nothing is subtracted."""
        raw = _raw()
        external = raw[1]["external_id"]
        b = assemble_event(
            IDENTITY,
            _dropping(raw, external, self.STAMP),
            now=OBSERVED + timedelta(hours=8),
        )
        assert raw[1]["id"] not in b.kept

    @pytest.mark.asyncio
    async def test_the_writer_threads_its_pass_instant_into_the_plan(self):
        """The writer's plan, not just the pure call: a dry run at T+8h deletes
        nothing, and the same state at a fresh instant deletes the member."""
        raw, a = _applied()
        victim, external = _victim(raw, a)
        rows = _dropping(raw, external, self.STAMP)

        async def container(*_):
            return {
                "id": 12,
                "slug": IDENTITY.slug,
                "name": None,
                "category": None,
                "status": "scheduled",
                "window_start": None,
                "window_end": None,
                "publication_state": "unpublished",
                "revision": 7,
            }

        async def read_state(*_):
            return writer._EventState(edges=dict(a.kept), prior=_prior(a), rows=rows)

        class Session:
            async def rollback(self):
                return None

        with patch.object(writer, "_select_container", container), patch.object(
            writer, "_read_state", read_state
        ):
            late = await writer.assemble_provider_event(
                Session(), IDENTITY, apply=False, now=OBSERVED + timedelta(hours=8)
            )
            fresh = await writer.assemble_provider_event(
                Session(), IDENTITY, apply=False, now=self.STAMP + timedelta(hours=1)
            )
        assert late["edges_deleted"] == 0 and late["receipt"]["retired"] == 0
        assert fresh["edges_deleted"] == 1


# ---------------------------------------------------------------------------
# 2. A parent that names another event is a conflict, not evidence
# ---------------------------------------------------------------------------


class TestParentIdentityConflict:
    def _assembled(self, parent_event_id, **kw):
        raw = _raw()
        if parent_event_id is None:
            raw[0]["market_metadata"].pop("polymarket_event_id")
        else:
            raw[0]["market_metadata"]["polymarket_event_id"] = parent_event_id
        return raw, assemble_event(
            IDENTITY, [provider_row(r) for r in raw], now=OBSERVED, **kw
        )

    def test_the_reviewers_case_refuses(self):
        """CERT-4043: parent metadata 86832 under polymarket:1038648 was eligible."""
        raw, a = self._assembled("86832")
        e = publication_eligibility(a, now=OBSERVED + timedelta(hours=1))
        assert not e.eligible
        assert INELIGIBLE_IDENTITY_CONFLICTS in e.reasons
        assert a.roster is None and a.roster_state == ROSTER_PARENT_CONFLICT
        assert not a.complete and not a.roster_subtracts
        assert raw[0]["id"] in a.identity_conflicts
        parent = next(d for d in a.decisions if d.child_id == raw[0]["id"])
        assert parent.reason == EXCLUDED_IDENTITY_CONFLICT and not parent.keep_edge

    def test_a_conflicted_parent_changes_no_header(self):
        _, a = self._assembled("86832", current_status="scheduled")
        current = {
            "name": "Stored label",
            "category": "politics",
            "status": "scheduled",
            "window_start": OBSERVED - timedelta(days=3),
            "window_end": OBSERVED + timedelta(days=30),
        }
        assert header_changes(a.header, current) == {}

    def test_a_conflicted_parent_roster_cannot_retire_a_member(self):
        raw, a = _applied()
        victim, external = _victim(raw, a)
        rows = _dropping(raw, external, OBSERVED + timedelta(minutes=1))
        rows[0] = provider_row(
            {
                **raw[0],
                "market_metadata": {
                    **raw[0]["market_metadata"],
                    "polymarket_event_id": "86832",
                },
            }
        )
        b = assemble_event(
            IDENTITY,
            rows,
            edged=a.kept,
            prior=_prior(a),
            now=OBSERVED + timedelta(hours=1),
        )
        assert plan_event_pass(b, a.kept).deletes == ()
        assert victim in b.kept

    @pytest.mark.parametrize("parent_event_id", [EVENT, None])
    def test_a_healthy_parent_still_publishes(self, parent_event_id):
        """Control: matching metadata (two signals) or none (group alone)."""
        raw, a = self._assembled(parent_event_id)
        assert publication_eligibility(a, now=OBSERVED + timedelta(hours=1)).eligible
        assert a.roster_state == pec.ROSTER_USABLE
        parent = next(d for d in a.decisions if d.child_id == raw[0]["id"])
        assert parent.reason == EXCLUDED_GROUP_ANCHOR


# ---------------------------------------------------------------------------
# 3. The preflight proves the stored membership, slot for slot
# ---------------------------------------------------------------------------


class TestStoredMembershipRefusals:
    def test_exact_membership_has_no_refusal(self):
        _, a = _applied()
        slots = {("market", c): EDGE_CLASS for c in a.kept}
        assert stored_membership_refusals(a, slots) == ()

    def test_a_missing_slot_is_named(self):
        _, a = _applied()
        slots = {("market", c): EDGE_CLASS for c in sorted(a.kept)[1:]}
        assert stored_membership_refusals(a, slots) == (INELIGIBLE_STORED_MISSING,)

    @pytest.mark.parametrize(
        "extra",
        [
            {("market", 99999): EDGE_CLASS},  # a market no member proves
            {("event", 5): EDGE_CLASS},  # another child type
            {("container", 77): None},  # a child container
        ],
    )
    def test_an_unproved_slot_is_named(self, extra):
        _, a = _applied()
        slots = {("market", c): EDGE_CLASS for c in a.kept}
        assert stored_membership_refusals(a, {**slots, **extra}) == (
            INELIGIBLE_STORED_UNPROVED,
        )

    def test_a_reclassified_slot_is_unproved(self):
        _, a = _applied()
        slots = {("market", c): EDGE_CLASS for c in a.kept}
        slots[("market", sorted(a.kept)[0])] = "contender"
        assert stored_membership_refusals(a, slots) == (INELIGIBLE_STORED_UNPROVED,)


class TestPreflightReadsTheStore:
    """The writer's preflight, through the same patched reads CERT-4043 used."""

    async def _evaluate(self, state):
        async def container(*_):
            return {
                "id": 12,
                "slug": IDENTITY.slug,
                "status": "scheduled",
                "publication_state": "unpublished",
                "revision": 7,
            }

        async def read_state(*_):
            return state

        with patch.object(writer, "_select_container", container), patch.object(
            writer, "_read_state", read_state
        ):
            return await writer.evaluate_provider_event_collection(
                object(), IDENTITY.slug, now=OBSERVED + timedelta(hours=1)
            )

    def _state(self, **kw):
        raw, a = _applied()
        base = dict(
            edges=dict(a.kept), prior=_prior(a), rows=[provider_row(r) for r in raw]
        )
        base.update(kw)
        return a, writer._EventState(**base)

    @pytest.mark.asyncio
    async def test_exact_stored_membership_is_eligible(self):
        _, state = self._state()
        verdict = await self._evaluate(state)
        assert verdict["eligible"] is True, verdict
        assert verdict["eligibility"]["eligible"] is True

    @pytest.mark.asyncio
    async def test_the_reviewers_case_five_stored_for_six_proved_refuses(self):
        a, state = self._state()
        state.edges.pop(sorted(a.kept)[0])
        verdict = await self._evaluate(state)
        assert verdict["eligible"] is False
        assert verdict["reasons"] == [INELIGIBLE_STORED_MISSING]
        assert verdict["eligibility"]["eligible"] is False

    @pytest.mark.asyncio
    async def test_a_foreign_slot_on_a_proved_member_in_its_class_is_eligible(self):
        a, state = self._state()
        held = sorted(a.kept)[0]
        state.edges.pop(held)
        state.foreign = {held}
        state.foreign_classes = {held: EDGE_CLASS}
        assert (await self._evaluate(state))["eligible"] is True

    @pytest.mark.asyncio
    async def test_a_foreign_slot_on_a_proved_member_in_another_class_refuses(self):
        a, state = self._state()
        held = sorted(a.kept)[0]
        state.edges.pop(held)
        state.foreign = {held}
        state.foreign_classes = {held: "contender"}
        verdict = await self._evaluate(state)
        assert verdict["eligible"] is False
        assert verdict["reasons"] == [INELIGIBLE_STORED_UNPROVED]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "extra",
        [
            dict(foreign={99999}, foreign_classes={99999: EDGE_CLASS}),
            dict(other_slots={("event", 5): EDGE_CLASS}),
            dict(child_containers=[77]),
        ],
    )
    async def test_a_slot_the_reader_would_serve_but_no_member_proves_refuses(
        self, extra
    ):
        _, state = self._state(**extra)
        verdict = await self._evaluate(state)
        assert verdict["eligible"] is False
        assert verdict["reasons"] == [INELIGIBLE_STORED_UNPROVED]
