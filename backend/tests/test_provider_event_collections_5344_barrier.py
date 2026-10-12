"""#5344 — the roster barrier: Authority's B1 and B2 (semantic review 2026-10-12 03:22Z).

SHIP: a provider event's collection can always be corrected by the provider's next
real roster, and two different rosters at one instant never move its membership.
Pillars: MATCHING / DISCOVER / TRUTH.

B1. A future-dated ``observed_at`` (a writer clock fault) used to pass the
    freshness test with a negative age, remove members, and become the barrier —
    so every real roster after it read ``roster_older_than_applied`` until that
    instant arrived. Now: refused as ``roster_from_future`` past
    ``ROSTER_FUTURE_SKEW``, adding, removing and advancing nothing.
B2. An equal ``observed_at`` used to authorize a conflicting change, because the
    barrier stored only the instant. Now every decision row carries
    ``applied_roster_digest``; at an equal instant a matching digest is a no-op
    and a different one is ``roster_conflicting_equal_barrier``: no admission, no
    roster removal, no header change, no revision bump.

Each refusal is paired with its healthy control on the same data, so a guard that
refused everything fails its control. The transaction half (both commit orders)
lives in ``tests/integration/test_provider_event_collections_5343_pg.py``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.utils import provider_event_collections as pec
from app.utils.provider_event_collections import (
    ADMITTED_ROSTER_MEMBER,
    CARRIED_ROSTER_CONFLICT,
    EXCLUDED_NOT_IN_ROSTER,
    EXCLUDED_ROSTER_CONFLICT,
    EXCLUDED_WITHDRAWN,
    INELIGIBLE_MEMBERS_CARRIED,
    ROSTER_CONFLICTING_EQUAL,
    ROSTER_FROM_FUTURE,
    ROSTER_FUTURE_SKEW,
    ROSTER_OLDER_THAN_APPLIED,
    ROSTER_PASS_UNDATED,
    ROSTER_USABLE,
    PriorDecision,
    assemble_event,
    header_changes,
    identity_from_group_id,
    parse_roster,
    plan_event_pass,
    provider_row,
    publication_eligibility,
)
from tests.provider_event_fixtures_5343 import ingested_rows, load_gamma, roster_payload

EVENT = "1038648"
IDENTITY = identity_from_group_id(f"polymarket:{EVENT}")
T0 = datetime(2026, 10, 12, 1, 0, tzinfo=timezone.utc)


def _rows(observed_at, *, drop=(), extra_rows=(), title=None):
    event = load_gamma(EVENT)
    raw = ingested_rows(event, "politics", first_id=1000)
    raw[0]["market_metadata"][pec.ROSTER_KEY] = roster_payload(
        event, observed_at, drop=drop
    )
    if title is not None:
        raw[0]["market_metadata"]["event_title"] = title
    return [provider_row(r) for r in [*raw, *extra_rows]]


def _prior(assembly) -> dict:
    """What the writer reads back from the decision rows this pass wrote."""
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


def _applied(observed_at=T0, **kw):
    a = assemble_event(IDENTITY, _rows(observed_at, **kw), now=observed_at)
    assert a.roster_state == ROSTER_USABLE and a.complete
    return a


def _child_external(a, child_id):
    return next(d.evidence["external_id"] for d in a.decisions if d.child_id == child_id)


def _next(a, rows, now):
    return assemble_event(IDENTITY, rows, edged=a.kept, prior=_prior(a), now=now)


# ---------------------------------------------------------------------------
# B1. A roster from the future is refused, and the next real roster corrects
# ---------------------------------------------------------------------------


class TestB1FutureRoster:
    def test_authoritys_probe_a_is_refused_then_the_real_roster_applies(self):
        """Probe A: stamped T0+30d, then a real T0+1h roster dropping a member.
        Before: ``roster_older_than_applied`` and the member stayed edged."""
        a = _applied()
        victim = sorted(a.kept)[0]
        external = _child_external(a, victim)

        b = _next(a, _rows(T0 + timedelta(days=30), drop=(external,)), T0 + timedelta(minutes=5))
        assert b.roster_state == ROSTER_FROM_FUTURE
        assert b.roster is None and not b.roster_subtracts
        # It removed nothing, admitted nothing new, and did not become the barrier.
        assert plan_event_pass(b, a.kept).deletes == ()
        assert set(b.kept) == set(a.kept)
        assert all(d.evidence["applied_roster_at"] == T0.isoformat() for d in b.decisions)
        assert {d.evidence["applied_roster_digest"] for d in b.decisions} == {
            a.roster.digest
        }

        now = T0 + timedelta(hours=1, minutes=1)
        c = _next(b, _rows(T0 + timedelta(hours=1), drop=(external,)), now)
        assert c.roster_state == ROSTER_USABLE
        assert plan_event_pass(c, b.kept).deletes == (victim,)
        assert next(d for d in c.decisions if d.child_id == victim).reason == (
            EXCLUDED_NOT_IN_ROSTER
        )
        assert publication_eligibility(c, now=now).eligible

    def test_a_future_roster_cannot_admit_or_complete(self):
        a = _applied()
        b = _next(a, _rows(T0 + timedelta(days=30)), T0 + timedelta(minutes=5))
        assert not b.complete
        assert not any(d.reason == ADMITTED_ROSTER_MEMBER for d in b.decisions)
        assert not publication_eligibility(b, now=T0 + timedelta(minutes=5)).eligible

    def test_the_skew_boundary(self):
        """At exactly ``now + ROSTER_FUTURE_SKEW`` the roster is usable (a
        writer's clock read moments after ours); one second past, refused."""
        now = T0 + timedelta(hours=1)
        a = _applied()
        at_edge = _next(a, _rows(now + ROSTER_FUTURE_SKEW), now)
        past = _next(a, _rows(now + ROSTER_FUTURE_SKEW + timedelta(seconds=1)), now)
        assert at_edge.roster_state == ROSTER_USABLE
        assert past.roster_state == ROSTER_FROM_FUTURE

    def test_a_pass_with_no_instant_refuses_every_roster(self):
        """The writer always supplies the database clock. Without it a roster can
        be proved neither fresh nor not-from-the-future, so it decides nothing."""
        a = _applied()
        external = _child_external(a, sorted(a.kept)[0])
        b = assemble_event(
            IDENTITY,
            _rows(T0 + timedelta(minutes=10), drop=(external,)),
            edged=a.kept,
            prior=_prior(a),
        )
        assert b.roster_state == ROSTER_PASS_UNDATED
        assert plan_event_pass(b, a.kept).deletes == ()
        assert all(d.evidence["applied_roster_at"] == T0.isoformat() for d in b.decisions)

    def test_a_fresh_collection_never_starts_from_a_future_roster(self):
        a = assemble_event(IDENTITY, _rows(T0 + timedelta(days=30)), now=T0)
        assert a.roster_state == ROSTER_FROM_FUTURE
        assert all(d.evidence["applied_roster_at"] is None for d in a.decisions)
        assert not a.complete


# ---------------------------------------------------------------------------
# B2. An equal barrier: a repeat is a no-op, a conflict changes nothing
# ---------------------------------------------------------------------------


class TestB2EqualBarrier:
    NOW = T0 + timedelta(minutes=2)

    def test_authoritys_probe_b_refuses_the_conflicting_change(self):
        """Probe B: same ``observed_at``, one market dropped. Before:
        ``deletes [1001]``, ``membership_changed true``."""
        a = _applied()
        victim = sorted(a.kept)[0]
        b = _next(a, _rows(T0, drop=(_child_external(a, victim),)), self.NOW)
        plan = plan_event_pass(b, a.kept)
        assert b.roster_state == ROSTER_CONFLICTING_EQUAL
        assert plan.deletes == () and plan.upserts == ()
        assert plan.membership_changed is False
        assert set(b.kept) == set(a.kept)
        decision = next(d for d in b.decisions if d.child_id == victim)
        assert decision.reason == CARRIED_ROSTER_CONFLICT and decision.keep_edge
        # The barrier is unchanged: instant AND digest.
        assert {d.evidence["applied_roster_digest"] for d in b.decisions} == {
            a.roster.digest
        }
        assert INELIGIBLE_MEMBERS_CARRIED in publication_eligibility(
            b, now=self.NOW
        ).reasons

    def test_the_identical_repeat_is_a_no_op(self):
        """Control on the same data: the same roster again changes nothing and
        writes the same evidence, so the writer has no decision row to write."""
        a = _applied()
        b = _next(a, _rows(T0), self.NOW)
        plan = plan_event_pass(b, a.kept)
        assert b.roster_state == ROSTER_USABLE
        assert plan.membership_changed is False
        assert [(d.child_id, d.outcome, d.reason, d.evidence) for d in b.decisions] == [
            (d.child_id, d.outcome, d.reason, d.evidence) for d in a.decisions
        ]

    def test_a_conflicting_equal_roster_admits_nothing(self):
        """The conflicting roster LISTS a member the applied one dropped: it may
        not re-admit it. The member keeps ``not_in_provider_roster`` so the hold
        survives into the next roster-less pass."""
        a0 = _applied()
        victim = sorted(a0.kept)[0]
        external = _child_external(a0, victim)
        a = _next(a0, _rows(T0 + timedelta(hours=1), drop=(external,)), T0 + timedelta(hours=1))
        assert victim not in a.kept

        b = _next(a, _rows(T0 + timedelta(hours=1)), T0 + timedelta(hours=1, minutes=2))
        assert b.roster_state == ROSTER_CONFLICTING_EQUAL
        assert victim not in b.kept
        held = next(d for d in b.decisions if d.child_id == victim)
        assert held.reason == EXCLUDED_NOT_IN_ROSTER and held.evidence.get("held")
        assert plan_event_pass(b, a.kept).upserts == ()

        # The next pass with no roster at all still does not resurrect it.
        raw = ingested_rows(load_gamma(EVENT), "politics", first_id=1000)
        c = _next(b, [provider_row(r) for r in raw], T0 + timedelta(hours=2))
        assert victim not in c.kept

    def test_a_new_row_is_not_admitted_through_a_conflict(self):
        """A row that claims the event but holds no edge is excluded by name."""
        event = load_gamma(EVENT)
        a = _applied()
        newcomer = ingested_rows(event, "politics", first_id=2000)[1]
        newcomer["external_id"] = "0x" + "ab" * 32
        b = _next(
            a,
            _rows(T0, drop=(_child_external(a, sorted(a.kept)[0]),), extra_rows=[newcomer]),
            self.NOW,
        )
        assert b.roster_state == ROSTER_CONFLICTING_EQUAL
        decision = next(d for d in b.decisions if d.child_id == newcomer["id"])
        assert decision.reason == EXCLUDED_ROSTER_CONFLICT and not decision.keep_edge
        assert plan_event_pass(b, a.kept).upserts == ()

    def test_a_conflict_leaves_the_header_alone(self):
        """A header change would bump the revision on its own."""
        a = _applied()
        b = _next(
            a,
            _rows(T0, drop=(_child_external(a, sorted(a.kept)[0]),), title="A new title"),
            self.NOW,
        )
        assert b.roster_state == ROSTER_CONFLICTING_EQUAL
        assert header_changes(b.header, {"name": a.header.name, "status": "scheduled"}) == {}

    def test_a_persons_withdrawal_still_applies_through_a_conflict(self):
        """A correction is not roster evidence; the conflict never blocks it."""
        a = _applied()
        victim = sorted(a.kept)[1]
        b = assemble_event(
            IDENTITY,
            _rows(T0, drop=(_child_external(a, sorted(a.kept)[0]),)),
            edged=a.kept,
            withdrawn=[victim],
            prior=_prior(a),
            now=self.NOW,
        )
        assert b.roster_state == ROSTER_CONFLICTING_EQUAL
        assert next(d for d in b.decisions if d.child_id == victim).reason == (
            EXCLUDED_WITHDRAWN
        )
        assert plan_event_pass(b, a.kept).deletes == (victim,)

    def test_a_barrier_with_no_digest_cannot_prove_a_repeat(self):
        """Rows at the barrier instant that carry no digest, or disagree, fail
        closed: even an identical roster is refused as a conflict."""
        a = _applied()
        undigested = {
            k: PriorDecision(p.child_id, p.reason, p.external_id, p.applied_roster_at)
            for k, p in _prior(a).items()
        }
        b = assemble_event(
            IDENTITY, _rows(T0), edged=a.kept, prior=undigested, now=self.NOW
        )
        assert b.roster_state == ROSTER_CONFLICTING_EQUAL

        split = dict(_prior(a))
        first = next(iter(split))
        p = split[first]
        split[first] = PriorDecision(
            p.child_id, p.reason, p.external_id, p.applied_roster_at, "0" * 64
        )
        c = assemble_event(IDENTITY, _rows(T0), edged=a.kept, prior=split, now=self.NOW)
        assert c.roster_state == ROSTER_CONFLICTING_EQUAL

    def test_an_older_roster_is_still_older_not_a_conflict(self):
        a = _applied(T0 + timedelta(minutes=1))
        b = _next(a, _rows(T0), T0 + timedelta(minutes=3))
        assert b.roster_state == ROSTER_OLDER_THAN_APPLIED

    def test_the_digest_travels_through_stale_passes(self):
        a = _applied()
        c = a
        for _ in range(3):
            c = _next(c, _rows(T0 - timedelta(hours=1)), self.NOW)
            assert c.roster_state == ROSTER_OLDER_THAN_APPLIED
            assert {d.evidence["applied_roster_digest"] for d in c.decisions} == {
                a.roster.digest
            }
        # And the conflicting equal pass after them is still caught.
        d = _next(c, _rows(T0, drop=(_child_external(a, sorted(a.kept)[0]),)), self.NOW)
        assert d.roster_state == ROSTER_CONFLICTING_EQUAL


class TestDigest:
    def _roster(self, markets, event_closed=False):
        roster, reason = parse_roster(
            {
                "observed_at": T0.isoformat(),
                "complete": True,
                "event_closed": event_closed,
                "markets": markets,
            }
        )
        assert reason is None
        return roster

    A = "0x" + "a" * 64
    B = "0x" + "b" * 64

    def test_order_does_not_matter(self):
        one = self._roster([{"id": self.A, "closed": False}, {"id": self.B, "closed": True}])
        two = self._roster([{"id": self.B, "closed": True}, {"id": self.A, "closed": False}])
        assert one.digest == two.digest

    @pytest.mark.parametrize(
        "other",
        [
            ([{"id": "0x" + "a" * 64, "closed": True}, {"id": "0x" + "b" * 64, "closed": True}], False),
            ([{"id": "0x" + "a" * 64, "closed": False}], False),
            ([{"id": "0x" + "a" * 64, "closed": False}, {"id": "0x" + "b" * 64, "closed": None}], False),
            ([{"id": "0x" + "a" * 64, "closed": False}, {"id": "0x" + "b" * 64, "closed": True}], True),
        ],
        ids=["a-leg-closed", "a-leg-missing", "closed-unknown", "event-closed"],
    )
    def test_any_change_in_what_it_says_changes_it(self, other):
        base = self._roster([{"id": self.A, "closed": False}, {"id": self.B, "closed": True}])
        markets, event_closed = other
        assert self._roster(markets, event_closed).digest != base.digest
