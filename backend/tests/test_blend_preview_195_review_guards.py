"""#10090 (attempt195 contract) — guards for Authority's four review findings.

Authority's review of `f167bd44a3` confirmed four defects with countercases
that PASSED because each defect was present
(`artifacts/.../attempt195-display-before-persist/independent-review/`).
These are those countercases inverted: each fails on `f167bd44a3` and passes
on the repair.

* R1 — every composition refuses a pending source the SQL stamp would refuse
  as stale (#8910), against the row this arm read AND a sibling's RETURNING.
* R2 — a sibling's surviving pending value is recomposed on the committed base
  and published BEFORE the committed frame; revokes still follow it.
* R3 — every attempted event is settled, including one missing from the group
  read and the empty-group early return; a withdrawn source is revoked.
* R4 — the uncommitted limit bounds one value across retries: an expired value
  is not re-proposed until a commit, refusal or different value ends it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.utils import blend_preview
from app.utils.aggregation import (
    compute_aggregate_probability,
    reading_regresses_stored_observation,
    stamp_source_reading,
)
from tests.test_blend_preview_display_before_persist_195 import (
    STORED,
    _PreviewSession,
    _event,
    _revokes,
)
from tests.test_live_blend_refresh import _one_event_refresher

FRESH = datetime.now(timezone.utc).isoformat()


@pytest.fixture(autouse=True)
def _fresh_registry(monkeypatch):
    blend_preview.reset_registry_for_tests()
    # Explicit legacy subject: its ordering/fencing regressions remain covered.
    monkeypatch.setattr(blend_preview, "_REGISTRY", blend_preview.PreviewRegistry())
    monkeypatch.setattr(blend_preview, "preview_events_for",
                        lambda source: frozenset(range(1, 600)) if source == "polymarket" else frozenset())
    yield
    blend_preview.reset_registry_for_tests()


def _agg(bag):
    return compute_aggregate_probability(
        SimpleNamespace(win_probability_sources=bag, status="live",
                        espn_win_prob_home=None, opening_home_probability=None),
        "live",
    )


def _ctx(status="live"):
    return SimpleNamespace(status=status, espn_win_prob_home=None,
                           opening_home_probability=None)


def _registry(clock=None, **kw):
    t = {"now": 0.0}
    reg = blend_preview.PreviewRegistry(
        max_uncommitted_s=kw.pop("max_s", 60.0),
        clock=clock or (lambda: t["now"]), epoch=7, **kw,
    )
    return reg, t


def _wire(monkeypatch, r):
    wire: list[tuple[str, dict]] = []

    async def _committed(frames):
        wire.extend(("committed", f) for f in frames)

    async def _previews(frames):
        wire.extend(("preview", f) for f in frames)

    monkeypatch.setattr(r, "_publish", _committed)
    monkeypatch.setattr(r, "_publish_previews", _previews)
    return wire


def _reader(wire, *, committed_rev, committed_p):
    """frontend/lib/blendPreview.ts, one event, one epoch: what the hero shows
    after each wire frame. A preview hides only when committed rev > base."""
    held = None
    shown = []
    for kind, frame in wire:
        if kind == "committed":
            committed_rev = frame["rev"][str(frame["event_id"])]
            committed_p = frame["p"]
        elif frame["preview"]["kind"] == "revoke":
            if held is not None and held["seq"] <= frame["preview"]["through_seq"]:
                held = None
        elif held is None or frame["preview"]["seq"] > held["seq"]:
            held = {"seq": frame["preview"]["seq"], "base": frame["preview"]["base_rev"],
                    "p": frame["p"]}
        visible = held is not None and committed_rev <= held["base"]
        shown.append(held["p"] if visible else committed_p)
    return shown


# ── R1 ─────────────────────────────────────────────────────────────────────

class TestR1StaleObservationGuard:
    BASE = {
        "kalshi": {"value": 0.5, "updated_at": FRESH},
        "polymarket": {"value": 0.40, "updated_at": FRESH,
                       "observed_basis": {"7": 200.0}, "observed_value": 0.40},
    }

    def test_a_reading_the_sql_stamp_would_refuse_is_not_previewed_on_the_row_base(self):
        older = {"7": 100.0}
        assert reading_regresses_stored_observation(self.BASE, "polymarket", older)
        frames = blend_preview.registry().propose(
            1, "polymarket", value=0.9, event=_ctx(), row_sources=self.BASE, row_rev=10,
            observed_basis=older,
        )
        assert frames == [], "nothing was shown, so nothing to show or revoke"
        assert not blend_preview.registry().has_pending(1, "polymarket")

    def test_a_stale_reading_revokes_what_it_was_shown_over_and_spares_a_sibling(self):
        reg, _ = _registry()
        [k] = reg.propose(1, "kalshi", value=0.3, event=_ctx(), row_sources=self.BASE, row_rev=10)
        [still_k] = reg.propose(1, "polymarket", value=0.9, event=_ctx(), row_sources=self.BASE,
                                row_rev=10, observed_basis={"7": 100.0})
        assert still_k["preview"]["kind"] == "blend"
        assert still_k["preview"]["pending"] == {"kalshi": 0.3}
        assert still_k["p"] == pytest.approx(k["p"])
        # The arm's own earlier, admitted PM preview is withdrawn by a stale one.
        [pm] = reg.propose(2, "polymarket", value=0.6, event=_ctx(), row_sources=STORED, row_rev=10,
                           observed_basis={"7": 100.0})
        [revoke] = reg.propose(2, "polymarket", value=0.9, event=_ctx(), row_sources=self.BASE,
                               row_rev=11, observed_basis={"7": 150.0})
        assert revoke["preview"]["kind"] == "revoke" and revoke["preview"]["reason"] == "stale"
        assert revoke["preview"]["through_seq"] == pm["preview"]["seq"]

    def test_a_newer_or_equal_observation_is_still_previewed(self):
        reg, _ = _registry()
        for eid, basis in ((1, {"7": 300.0}), (2, {"7": 200.0}), (3, None)):
            [frame] = reg.propose(eid, "polymarket", value=0.9, event=_ctx(),
                                  row_sources=self.BASE, row_rev=10, observed_basis=basis)
            assert frame["preview"]["pending"] == {"polymarket": 0.9}, basis

    def test_a_siblings_returning_base_refuses_a_pending_value_it_has_overtaken(self):
        reg, _ = _registry()
        [k] = reg.propose(1, "kalshi", value=0.3, event=_ctx(), row_sources=STORED, row_rev=10)
        [both] = reg.propose(1, "polymarket", value=0.9, event=_ctx(), row_sources=STORED,
                             row_rev=10, observed_basis={"7": 100.0})
        assert both["preview"]["pending"] == {"kalshi": 0.3, "polymarket": 0.9}
        # Kalshi commits rev 11; its RETURNING carries the poll's later PM observation.
        returned = stamp_source_reading(
            stamp_source_reading(dict(STORED), "kalshi", 0.3),
            "polymarket", 0.45, observed_basis={"7": 200.0},
        )
        assert reading_regresses_stored_observation(returned, "polymarket", {"7": 100.0})
        [revoke] = reg.committed(1, "kalshi", seq=k["preview"]["seq"], sources=returned, rev=11)
        assert revoke["preview"]["kind"] == "revoke" and revoke["preview"]["reason"] == "stale"
        assert not reg.has_pending(1)

    def test_a_returning_base_spares_a_pending_value_it_has_not_overtaken(self):
        reg, _ = _registry()
        [k] = reg.propose(1, "kalshi", value=0.3, event=_ctx(), row_sources=STORED, row_rev=10)
        reg.propose(1, "polymarket", value=0.9, event=_ctx(), row_sources=STORED,
                    row_rev=10, observed_basis={"7": 300.0})
        returned = stamp_source_reading(
            stamp_source_reading(dict(STORED), "kalshi", 0.3),
            "polymarket", 0.45, observed_basis={"7": 200.0},
        )
        [again] = reg.committed(1, "kalshi", seq=k["preview"]["seq"], sources=returned, rev=11)
        assert again["preview"]["kind"] == "blend" and again["preview"]["base_rev"] == 11
        assert again["preview"]["pending"] == {"polymarket": 0.9}


# ── R2 ─────────────────────────────────────────────────────────────────────

class TestR2RecomposeBeforeTheCommittedFrame:
    async def test_a_siblings_commit_never_puts_its_older_stored_value_back(self, monkeypatch):
        """Authority's R2 setup: Kalshi 0.30 pending (row held); Polymarket's
        stamp commits rev 11 whose bag still holds the STORED Kalshi 0.50."""
        event, market = _event()
        reg = blend_preview.registry()
        reg.propose(1, "kalshi", value=0.30, event=event, row_sources=STORED, row_rev=10)
        returned = stamp_source_reading(dict(STORED), "polymarket", 0.9)
        session = _PreviewSession([(market, event)], returned, stored=STORED, rev=10, locked=False)
        session.returned_rev = 11
        r, _ = _one_event_refresher(monkeypatch, session)
        wire = _wire(monkeypatch, r)

        await r.refresh([1])

        kinds = [k for k, _ in wire]
        assert kinds == ["preview", "preview", "committed"], kinds
        before, after, commit = (f for _, f in wire)
        assert before["preview"]["pending"] == {"kalshi": 0.30, "polymarket": 0.9}
        assert after["preview"]["base_rev"] == 11
        assert after["preview"]["pending"] == {"kalshi": 0.30}
        assert after["p"] == pytest.approx(before["p"])
        assert commit["rev"] == {"1": 11} and commit["p"] == pytest.approx(_agg(returned))
        assert commit["p"] != pytest.approx(before["p"])
        shown = _reader(wire, committed_rev=10, committed_p=_agg(STORED))
        assert shown == [pytest.approx(before["p"])] * 3, (
            "the older Kalshi value never reaches the hero", shown,
        )

    async def test_a_revoke_still_follows_the_committed_frame(self, monkeypatch):
        """Retirement ordering: a sibling refused against the RETURNING base
        is revoked AFTER the commit, so the hero goes to the new commit, not
        back to the older committed value."""
        event, market = _event()
        reg = blend_preview.registry()
        reg.propose(1, "kalshi", value=0.30, event=event, row_sources=STORED, row_rev=10,
                    observed_basis={"7": 100.0})
        returned = stamp_source_reading(
            stamp_source_reading(dict(STORED), "kalshi", 0.45, observed_basis={"7": 200.0}),
            "polymarket", 0.9,
        )
        session = _PreviewSession([(market, event)], returned, stored=STORED, rev=10, locked=False)
        session.returned_rev = 11
        r, _ = _one_event_refresher(monkeypatch, session)
        wire = _wire(monkeypatch, r)

        await r.refresh([1])

        kinds = [(k, f["preview"]["kind"] if k == "preview" else None) for k, f in wire]
        assert kinds == [("preview", "blend"), ("committed", None), ("preview", "revoke")], kinds
        assert wire[2][1]["preview"]["reason"] == "stale"
        shown = _reader(wire, committed_rev=10, committed_p=_agg(STORED))
        assert shown[1:] == [pytest.approx(_agg(returned))] * 2
        assert not reg.has_pending(1)

    async def test_an_own_commit_with_nothing_else_pending_still_retires_without_a_revoke(self, monkeypatch):
        event, market = _event()
        returned = stamp_source_reading(dict(STORED), "polymarket", 0.9)
        session = _PreviewSession([(market, event)], returned, stored=STORED, rev=10, locked=False)
        session.returned_rev = 11
        r, _ = _one_event_refresher(monkeypatch, session)
        wire = _wire(monkeypatch, r)
        await r.refresh([1])
        assert [k for k, _ in wire] == ["preview", "committed"]
        assert not blend_preview.registry().has_pending(1)


# ── R3 ─────────────────────────────────────────────────────────────────────

class TestR3SettleEveryAttemptedEvent:
    async def test_the_empty_group_early_return_revokes_the_sources_pending_value(self, monkeypatch):
        """Authority's R3: Polymarket pending (row held), then its markets
        leave the group read. The next attempt reads no group."""
        event, market = _event()
        session = _PreviewSession([(market, event)], None, stored=STORED, rev=10)
        r, _ = _one_event_refresher(monkeypatch, session)
        sent: list[dict] = []

        async def _record(frames):
            sent.extend(frames)

        monkeypatch.setattr(r, "_publish_previews", _record)
        await r.refresh([1])
        assert blend_preview.registry().has_pending(1, "polymarket")

        session._market_rows = []
        r._last_refresh_at.clear()
        await r.refresh([1])
        [revoke] = _revokes([(0, f) for f in sent])
        assert revoke["preview"]["reason"] == "no_group"
        assert not blend_preview.registry().has_pending(1, "polymarket")

        [k] = blend_preview.registry().propose(
            1, "kalshi", value=0.30, event=event, row_sources=STORED, row_rev=12,
        )
        assert k["preview"]["pending"] == {"kalshi": 0.30}, "no ghost source"

    async def test_an_event_missing_beside_a_present_one_is_settled_and_the_held_one_kept(self, monkeypatch):
        (e1, m1), (e2, m2) = _event(1), _event(2)
        session = _PreviewSession([(m1, e1), (m2, e2)], None, stored=STORED, rev=10)
        r, _ = _one_event_refresher(monkeypatch, session)
        sent: list[dict] = []

        async def _record(frames):
            sent.extend(frames)

        monkeypatch.setattr(r, "_publish_previews", _record)
        await r._refresh_batch([1, 2], 0.0)
        assert blend_preview.registry().has_pending(1) and blend_preview.registry().has_pending(2)

        session._market_rows = [(m2, e2)]  # event 1 lost this source's market
        sent.clear()
        await r._refresh_batch([1, 2], 1.0)
        assert [(f["event_id"], f["preview"]["reason"]) for f in _revokes([(0, f) for f in sent])] == [
            (1, "no_group"),
        ]
        assert not blend_preview.registry().has_pending(1)
        assert blend_preview.registry().has_pending(2, "polymarket"), "still lock-deferred"

    async def test_a_prepared_read_omitting_an_event_settles_it(self, monkeypatch):
        event, market = _event()
        session = _PreviewSession([(market, event)], None, stored=STORED, rev=10)
        r, _ = _one_event_refresher(monkeypatch, session)
        sent: list[dict] = []

        async def _record(frames):
            sent.extend(frames)

        monkeypatch.setattr(r, "_publish_previews", _record)
        await r.refresh([1])
        await r._refresh_batch([1], 1.0, prepared={})
        assert [f["preview"]["reason"] for f in _revokes([(0, f) for f in sent])] == ["no_group"]
        assert not blend_preview.registry().has_pending(1)

    async def test_a_withdrawn_source_is_revoked_after_its_invalidation(self, monkeypatch):
        from app.tasks import polymarket_ws as pm
        from app.tasks.live_blend_refresh import LiveBlendRefresher

        reg = blend_preview.registry()
        reg.propose(1, "kalshi", value=0.30, event=_ctx(), row_sources=STORED, row_rev=10)
        reg.propose(1, "polymarket", value=0.9, event=_ctx(), row_sources=STORED, row_rev=10)
        r = LiveBlendRefresher("polymarket")
        assert r.preview is True
        wire: list[tuple[str, dict]] = []

        async def _committed(frames):
            wire.extend(("committed", f) for f in frames)
            return {(f["event_id"], f["rev"]["1"]) for f in frames}

        async def _previews(frames):
            wire.extend(("preview", f) for f in frames)

        monkeypatch.setattr(r, "_publish", _committed)
        monkeypatch.setattr(r, "_publish_previews", _previews)
        invalidation = {"event_id": 1, "p": None, "rev": {"1": 11}, "invalidation": True}

        await pm._publish_committed_withdrawals(r, [invalidation])

        assert [k for k, _ in wire] == ["committed", "preview"]
        assert wire[1][1]["preview"]["pending"] == {"kalshi": 0.30}
        assert not reg.has_pending(1, "polymarket")
        [k] = reg.propose(1, "kalshi", value=0.31, event=_ctx(), row_sources=STORED, row_rev=11)
        assert k["preview"]["pending"] == {"kalshi": 0.31}

    @pytest.mark.parametrize("scope", [frozenset(), frozenset({2, 3})])
    async def test_withdrawal_outside_explicit_scope_touches_no_registry(self, monkeypatch, scope):
        from app.tasks import polymarket_ws as pm
        from app.tasks.live_blend_refresh import LiveBlendRefresher

        monkeypatch.setattr(blend_preview, "preview_events_for", lambda source: scope)
        blend_preview.registry().propose(
            1, "polymarket", value=0.9, event=_ctx(), row_sources=STORED, row_rev=10)
        r = LiveBlendRefresher("polymarket")

        async def _committed(frames):
            return set()

        async def _forbidden(frames):
            raise AssertionError("no preview publication when disabled")

        monkeypatch.setattr(r, "_publish", _committed)
        monkeypatch.setattr(r, "_publish_previews", _forbidden)
        await pm._publish_committed_withdrawals(
            r, [{"event_id": 1, "p": None, "rev": {"1": 11}, "invalidation": True}])
        assert blend_preview.registry().has_pending(1, "polymarket")


# ── R4 ─────────────────────────────────────────────────────────────────────

class TestR4TheLimitBoundsAValueAcrossRetries:
    async def test_an_expired_value_is_not_reopened_by_the_retry_that_expires_it(self, monkeypatch):
        """Authority's R4: previewed at t=0, row held; retried at t=61."""
        clock = [0.0]
        blend_preview._REGISTRY = blend_preview.PreviewRegistry(
            max_uncommitted_s=60.0, clock=lambda: clock[0], epoch=7)
        event, market = _event()
        session = _PreviewSession([(market, event)], None, stored=STORED, rev=10)
        r, _ = _one_event_refresher(monkeypatch, session)
        batches: list[list[dict]] = []

        async def _record(frames):
            batches.append(list(frames))

        monkeypatch.setattr(r, "_publish_previews", _record)
        await r.refresh([1])                      # t=0: previewed, row held
        clock[0] = 61.0
        r._last_refresh_at.clear()
        await r.refresh([1])                      # t=61: still held
        last = [b for b in batches if b][-1]
        assert [f["preview"]["kind"] for f in last] == ["revoke"], last
        assert last[0]["preview"]["reason"] == "expired"

        clock[0] = 120.0
        r._last_refresh_at.clear()
        await r.refresh([1])                      # t=120: still held, same value
        assert [f for b in batches[-1:] for f in b] == [], "nothing re-opened"
        assert not blend_preview.registry().has_pending(1)

    def test_only_a_commit_a_refusal_or_a_different_value_ends_the_expired_chain(self):
        reg, t = _registry(max_s=10.0)
        for eid in (1, 2, 3):
            reg.propose(eid, "kalshi", value=0.7, event=_ctx(), row_sources=STORED, row_rev=10)
        t["now"] = 10.0
        assert [f["preview"]["reason"] for f in reg.expire()] == ["expired"] * 3
        t["now"] = 15.0
        for eid in (1, 2, 3):
            assert reg.propose(eid, "kalshi", value=0.7, event=_ctx(),
                               row_sources=STORED, row_rev=10) == []
        # A different value opens a new, full chain.
        [new] = reg.propose(1, "kalshi", value=0.72, event=_ctx(), row_sources=STORED, row_rev=10)
        assert new["preview"]["ttl_ms"] == 10_000
        # A commit ends the chain: the same value later previews again.
        assert reg.committed(2, "kalshi", seq=None, sources=STORED, rev=11) == []
        [after_commit] = reg.propose(2, "kalshi", value=0.7, event=_ctx(),
                                     row_sources=STORED, row_rev=11)
        assert after_commit["preview"]["kind"] == "blend"
        # So does a refusal.
        assert reg.refused(3, "kalshi", "stale") == []
        [after_refusal] = reg.propose(3, "kalshi", value=0.7, event=_ctx(),
                                      row_sources=STORED, row_rev=10)
        assert after_refusal["preview"]["kind"] == "blend"

    def test_a_terminal_event_forgets_its_expired_chain(self):
        reg, t = _registry(max_s=10.0)
        reg.propose(1, "kalshi", value=0.7, event=_ctx(), row_sources=STORED, row_rev=10)
        t["now"] = 10.0
        reg.expire()
        reg.propose(1, "kalshi", value=0.7, event=_ctx("completed"), row_sources=STORED, row_rev=11)
        assert reg._events[1].expired == {}

    def test_expired_markers_live_in_the_bounded_event_state(self):
        reg, t = _registry(max_s=10.0, max_events=2)
        for eid in (1, 2):
            reg.propose(eid, "kalshi", value=0.7, event=_ctx(), row_sources=STORED, row_rev=10)
        t["now"] = 10.0
        reg.expire()
        reg.propose(3, "kalshi", value=0.7, event=_ctx(), row_sources=STORED, row_rev=10)
        assert len(reg._events) == 2 and 1 not in reg._events
        assert all(len(s.expired) <= 1 for s in reg._events.values())

    def test_a_sibling_keeps_its_own_lifetime_when_one_source_expires(self):
        reg, t = _registry(max_s=10.0)
        reg.propose(1, "kalshi", value=0.7, event=_ctx(), row_sources=STORED, row_rev=10)
        t["now"] = 5.0
        reg.propose(1, "polymarket", value=0.6, event=_ctx(), row_sources=STORED, row_rev=10)
        t["now"] = 10.0
        [recomposed] = reg.expire()
        assert recomposed["preview"]["pending"] == {"polymarket": 0.6}
        assert recomposed["preview"]["ttl_ms"] == 5_000
        assert reg.propose(1, "kalshi", value=0.7, event=_ctx(), row_sources=STORED,
                           row_rev=10) == []
        assert reg.has_pending(1, "polymarket")
