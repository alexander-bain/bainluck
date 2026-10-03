"""#10305 — the one-row mode of the anchor-schedule rail: its statement and its route.

The lock, the transaction and the rows a write reaches are proved on real
Postgres in ``integration/test_reconcile_anchor_schedule_member_10305_pg.py``.
This file holds what needs no server: a statement that leaves out a fenced
column is refused (a fence that checks only what the caller remembered is the
caller's memory), the move predicate admits exactly one move, and the route
never lets a member call page or widen into the sport-wide apply it replaces.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

import app.routes.admin_events as admin_events
from app.tasks import reconcile_anchor_schedule as rail

UTC = timezone.utc
OURS = datetime(2031, 3, 7, 5, 17, tzinfo=UTC)
THEIRS = datetime(2031, 3, 7, 22, 17, tzinfo=UTC)


def _expect(**over):
    base = {c: None for c in rail.MEMBER_FENCE_COLUMNS}
    base.update(espn_id="9103050001", commence_time=OURS.isoformat(),
                commence_time_source="odds_api", status="scheduled",
                home_team_name="A", away_team_name="B", event_tags=["t2", "t1"])
    base.update(over)
    return base


@dataclass(frozen=True)
class _D:
    event_id: int = 1
    espn_id: str = "9103050001"
    ours: datetime = OURS
    theirs: datetime = THEIRS
    orientation_inverted: bool = False
    write: dict = field(default_factory=lambda: {
        "commence_time": THEIRS, "commence_time_source": "espn"})


class TestStatement:
    def test_every_fenced_column_must_be_stated(self):
        expect = _expect()
        del expect["event_tags"]
        with pytest.raises(ValueError, match="missing=\\['event_tags'\\]"):
            rail._member_spec(expect, [], THEIRS)

    def test_an_unfenced_column_is_refused_rather_than_ignored(self):
        with pytest.raises(ValueError, match="extra=\\['win_probability_sources'\\]"):
            rail._member_spec(_expect(win_probability_sources={}), [], THEIRS)

    def test_authority_start_must_carry_an_offset(self):
        with pytest.raises(ValueError, match="UTC offset"):
            rail._member_spec(_expect(), [], "2031-03-07T22:17:00")

    def test_an_anchor_states_exactly_its_key(self):
        with pytest.raises(ValueError, match="each expected anchor"):
            rail._member_spec(_expect(), [{"event_id": 1, "source": "espn"}], THEIRS)


class TestFenceDiff:
    def test_equal_state_in_another_spelling_is_clean(self):
        observed = dict(_expect(), commence_time=OURS, event_tags='["t1", "t2"]')
        expect = _expect(commence_time="2031-03-07T05:17:00Z")
        assert rail.member_fence_diff(observed, [], expect=expect, expect_anchors=[]) == {}

    def test_one_moved_column_is_named_and_only_it(self):
        observed = dict(_expect(), commence_time=OURS, status="in_progress")
        diff = rail.member_fence_diff(observed, [], expect=_expect(), expect_anchors=[])
        assert list(diff) == ["status"]

    def test_an_extra_anchor_is_drift(self):
        observed = dict(_expect(), commence_time=OURS)
        extra = [{"event_id": 9, "source": "espn", "source_id": "9103050001", "id_kind": "game"}]
        diff = rail.member_fence_diff(observed, extra, expect=_expect(), expect_anchors=[])
        assert list(diff) == ["anchors"]

    def test_a_missing_row_is_drift(self):
        assert rail.member_fence_diff(None, [], expect=_expect(), expect_anchors=[]) == {"row": "MISSING"}


class TestMovePredicate:
    only = staticmethod(rail.member_move_only(1, "9103050001", OURS, THEIRS))

    def test_the_stated_move_is_admitted(self):
        assert self.only(_D()) is True

    @pytest.mark.parametrize("change", [
        {"event_id": 2},
        {"espn_id": "9103050002"},
        {"ours": THEIRS},
        {"theirs": datetime(2031, 3, 7, 23, 17, tzinfo=UTC)},
        {"orientation_inverted": True},
        {"write": {"commence_time": THEIRS, "commence_time_source": "espn", "status": "x"}},
    ])
    def test_any_other_move_is_not(self, change):
        assert self.only(_D(**change)) is False


class TestRoute:
    @pytest.fixture(autouse=True)
    def _admin(self, monkeypatch):
        monkeypatch.setattr(admin_events, "_check_admin_secret", lambda *a, **k: None)
        monkeypatch.setattr(admin_events, "_check_admin_destructive", lambda *a, **k: None)

    def _post(self, **kw):
        args = dict(request=None, secret=None, apply=False, limit=None, sport=None,
                    cursor=None, undo_identity=None, member=None, db=object())
        args.update(kw)
        return asyncio.run(admin_events.reconcile_anchor_schedule_endpoint(**args))

    MEMBER = {"event_id": 1, "expect": {}, "expect_anchors": [], "authority_start": THEIRS.isoformat()}

    @pytest.mark.parametrize("widen", [{"sport": "basketball_wnba"}, {"cursor": "c"}, {"limit": 5}])
    def test_a_member_call_never_pages_or_widens(self, widen, monkeypatch):
        called = []

        async def would_run(*a, **k):
            called.append(k)
            return {"terminal": "plan_only", "examined": 0, "moves": [], "by_verdict": {}}

        # Both doors would answer: the refusal can only come from the route.
        monkeypatch.setattr(rail, "reconcile_member", would_run)
        monkeypatch.setattr(rail, "reconcile", would_run)
        with pytest.raises(HTTPException) as err:
            self._post(member=self.MEMBER, **widen)
        assert err.value.status_code == 400 and "one named row" in err.value.detail
        assert called == []

    def test_a_malformed_statement_is_the_callers_400(self):
        with pytest.raises(HTTPException) as err:
            self._post(member={"event_id": 1, "expect": {}, "authority_start": THEIRS.isoformat()},
                       apply=True)
        assert err.value.status_code == 400 and "missing=" in err.value.detail

    def test_a_member_call_reaches_reconcile_member_and_not_the_sweep(self, monkeypatch):
        seen = {}

        async def fake_member(db, **kw):
            seen.update(kw)
            return {"terminal": "plan_only", "examined": 1, "moves": [], "by_verdict": {}}

        async def no_sweep(*a, **k):
            raise AssertionError("the sweep must not run for a member call")

        monkeypatch.setattr(rail, "reconcile_member", fake_member)
        monkeypatch.setattr(rail, "reconcile", no_sweep)
        out = self._post(member=self.MEMBER, apply=True)
        assert seen == {"event_id": 1, "expect": {}, "expect_anchors": [],
                        "authority_start": THEIRS.isoformat(), "apply": True}
        assert out["terminal"] == "plan_only"
