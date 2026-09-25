"""#8422 — one Odds API fixture re-issued under a new id prints once, not twice.

**SHIP: /search?q=arsenal lists Fleetwood Town v Arsenal once, at the real
kick-off — not twice, 19 hours apart.** (Pillar: MATCHING.)

The specimens are production's, read 2026-09-25 01:45Z: the Fleetwood block
(old id unlisted by `/events`, new id listed) is tagged; the WNBA Lynx v Liberty
block (the UNLISTED id is the newer one) and every block where both ids are
still listed are refused. The SQL half runs against real Postgres in
`tests/integration/test_odds_api_reissued_twin_8422_pg.py`.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import pytest

from app.utils.odds_api_reissued_twins import (
    ReissueRow,
    candidate_blocks,
    plan_reissue_tags,
    relisted_banked_ids,
)

UTC = timezone.utc
NOW = datetime(2026, 9, 25, 1, 45, tzinfo=UTC)
EFL = "soccer_england_efl_cup"
OLD, NEW = "95b553f793547e502d7124f78511f2cf", "29d04f0dddd5b30cd51de9acb7925795"


def row(eid, oid, at, seen, *, sport=EFL, home="Fleetwood Town", away="Arsenal",
        status="scheduled", other_anchor=False, tagged=False, ids=None):
    return ReissueRow(
        event_id=eid, sport_key=sport, home=home, away=away, commence_time=at,
        status=status, odds_api_ids=frozenset(ids or {oid}), first_seen_at=seen,
        other_anchor=other_anchor, already_tagged=tagged,
    )


GHOST = row(15313977, OLD, datetime(2026, 10, 28, 15, tzinfo=UTC), datetime(2026, 9, 17, 10, 5, tzinfo=UTC))
CANON = row(15314731, NEW, datetime(2026, 10, 27, 20, tzinfo=UTC), datetime(2026, 9, 18, 22, 7, tzinfo=UTC))


def plan_for(rows, schedules):
    return plan_reissue_tags(candidate_blocks(rows, now=NOW), schedules)


class TestTheJudgement:
    def test_fleetwood_the_unlisted_older_id_is_tagged_onto_the_listed_one(self):
        plan = plan_for([GHOST, CANON], {EFL: {NEW}})
        assert [(t.duplicate_id, t.canonical_id) for t in plan.tags] == [(15313977, 15314731)]
        assert plan.tags[0].ghost_odds_api_ids == OLD

    def test_both_ids_listed_is_two_games_and_is_refused(self):
        # Argentina / Chile / Libertadores specimens: both ids still listed.
        plan = plan_for([GHOST, CANON], {EFL: {OLD, NEW}})
        assert plan.tags == [] and plan.refusals[0]["reason"] == "all_listed"

    def test_wnba_the_unlisted_id_is_the_newer_one_and_is_refused(self):
        wnba = "basketball_wnba"
        sunday = row(15318132, "4a5f", datetime(2026, 9, 27, 18, tzinfo=UTC),
                     datetime(2026, 9, 23, 1, tzinfo=UTC), sport=wnba,
                     home="Minnesota Lynx", away="New York Liberty")
        friday = row(15318133, "430c", datetime(2026, 9, 26, 0, 30, tzinfo=UTC),
                     datetime(2026, 9, 23, 2, tzinfo=UTC), sport=wnba,
                     home="Minnesota Lynx", away="New York Liberty")
        plan = plan_for([sunday, friday], {wnba: {"4a5f"}})
        assert plan.tags == []
        assert plan.refusals[0]["reason"] == "ghost_15318133_is_the_newer_id"

    def test_an_unread_schedule_is_not_an_empty_one(self):
        plan = plan_for([GHOST, CANON], {})
        assert plan.tags == [] and plan.refusals[0]["reason"] == "schedule_not_read"

    def test_a_ghost_another_authority_vouches_for_is_refused(self):
        anchored = row(15313977, OLD, GHOST.commence_time, GHOST.first_seen_at, other_anchor=True)
        assert plan_for([anchored, CANON], {EFL: {NEW}}).tags == []

    def test_no_listed_canonical_and_several_listed_are_refused(self):
        assert plan_for([GHOST, CANON], {EFL: set()}).refusals[0]["reason"] == "no_listed_canonical"
        third = row(15320000, "abc", CANON.commence_time + timedelta(hours=2), CANON.first_seen_at)
        plan = plan_for([GHOST, CANON, third], {EFL: {NEW, "abc"}})
        assert plan.tags == [] and plan.refusals[0]["reason"] == "several_listed"

    def test_a_canonical_that_is_itself_a_duplicate_is_refused(self):
        tagged = row(15314731, NEW, CANON.commence_time, CANON.first_seen_at, tagged=True)
        assert plan_for([GHOST, tagged], {EFL: {NEW}}).tags == []

    def test_an_already_tagged_ghost_is_not_planned_again(self):
        done = row(15313977, OLD, GHOST.commence_time, GHOST.first_seen_at, tagged=True)
        assert plan_for([done, CANON], {EFL: {NEW}}).tags == []

    def test_a_row_holding_both_ids_is_listed_and_never_its_own_ghost(self):
        both = row(15313977, OLD, GHOST.commence_time, GHOST.first_seen_at, ids={OLD, NEW})
        plan = plan_for([both, CANON], {EFL: {NEW}})
        assert plan.tags == [] and plan.refusals[0]["reason"] == "all_listed"


class TestTheCandidateBlock:
    def test_different_pairs_sports_or_far_apart_rows_never_block(self):
        other_pair = row(15313978, "x", GHOST.commence_time, GHOST.first_seen_at, home="Arsenal", away="Fleetwood Town")
        other_sport = row(15313979, "y", GHOST.commence_time, GHOST.first_seen_at, sport="soccer_epl")
        far = row(15313980, "z", CANON.commence_time + timedelta(days=4), GHOST.first_seen_at)
        assert candidate_blocks([CANON, other_pair, other_sport, far], now=NOW) == []

    def test_near_kickoff_and_retired_rows_are_out(self):
        soon = row(1, "a", NOW + timedelta(minutes=30), NOW - timedelta(days=3))
        soon2 = row(2, "b", NOW + timedelta(hours=5), NOW - timedelta(days=2))
        assert candidate_blocks([soon, soon2], now=NOW) == []
        voided = row(15313977, OLD, GHOST.commence_time, GHOST.first_seen_at, status="voided")
        assert candidate_blocks([voided, CANON], now=NOW) == []


class TestTheLift:
    def test_a_relisted_id_lifts_its_label_and_an_unread_sport_lifts_nothing(self):
        banked = {15313977: (EFL, frozenset({OLD}))}
        assert relisted_banked_ids(banked, {EFL: {OLD, NEW}}) == [15313977]
        assert relisted_banked_ids(banked, {EFL: {NEW}}) == []
        assert relisted_banked_ids(banked, {}) == []


# ── the pass, with its database and provider replaced ──────────────────────


class FakeService:
    def __init__(self, listed=None, fail=()):
        self.listed, self.fail, self.calls = listed or {}, set(fail), []

    async def get_events(self, sport):
        self.calls.append(sport)
        if sport in self.fail:
            raise RuntimeError("503 from provider")
        return [{"id": i} for i in self.listed.get(sport, ())]


@pytest.fixture
def sweep(monkeypatch):
    import app.tasks.base as base
    import app.tasks.odds_api_reissued_twin_sweep as mod

    state = {"rows": [GHOST, CANON], "banked": {}, "written": [], "lifted": {}, "confirmed": None}

    @asynccontextmanager
    async def fake_session():
        class S:
            async def rollback(self):
                pass
        yield S()

    async def load_rows(session, *, lookahead):
        filler = [
            row(900000 + i, f"f{i}", NOW + timedelta(days=2, minutes=i), NOW, home=f"H{i}", away=f"A{i}")
            for i in range(mod.MIN_ROWS_FLOOR)
        ]
        rows = state["rows"] + filler
        return rows, {r.event_id: "[]" for r in rows}

    async def load_banked(session):
        return state["banked"]

    async def ensure_backup(session, tags, current):
        return len(tags)

    async def write_tags(session, tags):
        state["written"] += [t.duplicate_id for t in tags]
        return len(tags), []

    async def tagged_now(session, ids):
        return set(ids) if state["confirmed"] is None else state["confirmed"]

    async def lift_tags(session, lifts):
        state["lifted"].update(lifts)
        return len(lifts), []

    monkeypatch.setattr(base, "get_task_session", fake_session)
    monkeypatch.setattr(mod, "load_rows", load_rows)
    monkeypatch.setattr(mod, "load_banked_labels", load_banked)
    monkeypatch.setattr(mod, "ensure_backup", ensure_backup)
    monkeypatch.setattr(mod, "write_tags", write_tags)
    monkeypatch.setattr(mod, "tagged_now", tagged_now)
    monkeypatch.setattr(mod, "lift_tags", lift_tags)
    monkeypatch.delenv(mod.REISSUED_TWIN_SWEEP_DISABLED_ENV, raising=False)
    return mod, state


def run(mod, service, **kw):
    import asyncio

    return asyncio.run(mod.run_odds_api_reissued_twin_sweep(service=service, now=NOW, **kw))


class TestThePass:
    def test_tags_the_fleetwood_ghost_and_reads_complete(self, sweep):
        mod, state = sweep
        service = FakeService({EFL: {NEW}})
        out = run(mod, service)
        assert out["terminal"] == "complete" and out["tagged"] == 1
        assert state["written"] == [15313977]
        assert service.calls == [EFL]  # only the sport holding a block is read

    def test_a_quiet_pass_asks_the_provider_nothing(self, sweep):
        mod, state = sweep
        state["rows"] = [CANON]
        service = FakeService()
        out = run(mod, service)
        assert out["terminal"] == "complete" and service.calls == []

    def test_a_failed_schedule_read_is_damage_not_a_quiet_zero(self, sweep):
        mod, _ = sweep
        out = run(mod, FakeService(fail={EFL}))
        assert out["terminal"] == "partial" and out["tagged"] == 0
        assert out["errors"] and EFL in out["errors"][0]

    def test_an_unconfirmed_write_is_partial(self, sweep):
        mod, state = sweep
        state["confirmed"] = set()
        assert run(mod, FakeService({EFL: {NEW}}))["terminal"] == "partial"

    def test_a_relisted_label_is_lifted(self, sweep):
        mod, state = sweep
        state["rows"] = [CANON]
        state["banked"] = {15313977: (EFL, frozenset({OLD}), 15314731)}
        out = run(mod, FakeService({EFL: {OLD, NEW}}))
        assert state["lifted"] == {15313977: 15314731} and out["lifted"] == 1

    def test_the_floor_refuses_a_read_that_lost_its_population(self, sweep, monkeypatch):
        mod, _ = sweep

        async def few(session, *, lookahead):
            return [GHOST, CANON], {}

        monkeypatch.setattr(mod, "load_rows", few)
        out = run(mod, FakeService({EFL: {NEW}}))
        assert out["terminal"] == "failed" and out["measured"] is False

    def test_the_stop_switch_reads_nothing(self, sweep, monkeypatch):
        mod, state = sweep
        monkeypatch.setenv(mod.REISSUED_TWIN_SWEEP_DISABLED_ENV, "1")
        service = FakeService({EFL: {NEW}})
        out = run(mod, service)
        assert out["terminal"] == "skipped" and service.calls == [] and state["written"] == []

    def test_no_tag_is_written_when_search_stops_reading_it(self, sweep, monkeypatch):
        mod, state = sweep
        monkeypatch.setattr(mod, "consumer_is_live", lambda: False)
        out = run(mod, FakeService({EFL: {NEW}}))
        assert out["terminal"] == "failed" and state["written"] == []

    def test_dry_run_writes_nothing(self, sweep):
        mod, state = sweep
        out = run(mod, FakeService({EFL: {NEW}}), apply=False)
        assert out["terminal"] == "no_work" and out["planned"] == 1 and state["written"] == []


def test_the_consumer_check_reads_the_real_search_route():
    from app.tasks.odds_api_reissued_twin_sweep import consumer_is_live

    assert consumer_is_live() is True


def test_the_beat_runs_apply_on_background_and_the_module_window():
    from app.tasks import celery_app

    entry = celery_app.conf.beat_schedule["odds-api-reissued-twin-sweep"]
    assert entry["task"] == "app.tasks.odds_api_reissued_twin_sweep"
    assert entry["kwargs"] == {"apply": True}
    assert entry["options"] == {"queue": "background"}
