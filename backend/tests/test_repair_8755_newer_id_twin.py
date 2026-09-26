"""#8755 — the one-off label for a twin past the re-issued sweep's window.

**SHIP: a WNBA playoff game that hasn't started stops showing as LIVE under a
two-day-old price.** (Pillar: TRUTH.)

`scripts/repair_8755_newer_id_twin.py` runs the sweep's own planner over two
named ids. These tests pin that it writes ONLY when that planner says
``ghost → canonical`` — the specimen as production holds it (ghost ``live``, past
its made-up start) — and that every other outcome writes nothing and exits 2.
The SQL half runs against real Postgres in
`tests/integration/test_odds_api_reissued_twin_8422_pg.py`.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import pytest

from app.utils.odds_api_reissued_twins import ReissueRow
from scripts.repair_8755_newer_id_twin import judge

UTC = timezone.utc
WNBA = "basketball_wnba"
GHOST, CANON = 15318133, 15318132
FANDUEL = ("fanduel", -300, 235, "-7.5", "173.5")
LINES = {CANON: frozenset({FANDUEL, ("draftkings", -270, 220, "-6.5", "173.5")}),
         GHOST: frozenset({FANDUEL})}


def row(eid, oid, at, seen, *, status="scheduled", home="Minnesota Lynx",
        away="New York Liberty", sport=WNBA, other_anchor=False, tagged=False):
    return ReissueRow(
        event_id=eid, sport_key=sport, home=home, away=away, commence_time=at,
        status=status, odds_api_ids=frozenset({oid}), first_seen_at=seen,
        other_anchor=other_anchor, already_tagged=tagged,
    )


# Production, 2026-09-26 01:55Z: the ghost is `live`, 85 minutes past a start
# that was never a start — the sweep's window (future, open statuses) cannot see it.
G = row(GHOST, "430c", datetime(2026, 9, 26, 0, 30, tzinfo=UTC),
        datetime(2026, 9, 24, 2, 18, 9, tzinfo=UTC), status="live")
C = row(CANON, "4a5f", datetime(2026, 9, 27, 18, tzinfo=UTC),
        datetime(2026, 9, 24, 2, 16, 38, tzinfo=UTC), other_anchor=True)  # ESPN 401918014
LISTED = {WNBA: {"4a5f"}}


class TestJudge:
    def test_the_specimen_is_planned_ghost_onto_sunday(self):
        tag, reason = judge([G, C], LISTED, LINES, ghost=GHOST, canonical=CANON)
        assert reason == "planned" and (tag.duplicate_id, tag.canonical_id) == (GHOST, CANON)

    def test_without_the_moved_line_the_sweeps_refusal_is_reported(self):
        tag, reason = judge([G, C], LISTED, {CANON: LINES[CANON]}, ghost=GHOST, canonical=CANON)
        assert tag is None and reason == "ghost_15318133_is_the_newer_id"

    def test_swapped_roles_are_refused_not_reversed(self):
        tag, reason = judge([G, C], LISTED, LINES, ghost=CANON, canonical=GHOST)
        assert tag is None

    def test_a_ghost_the_provider_still_lists_is_refused(self):
        tag, reason = judge([G, C], {WNBA: {"4a5f", "430c"}}, LINES, ghost=GHOST, canonical=CANON)
        assert tag is None and reason == "all_listed"

    def test_a_different_pair_is_refused_before_the_planner(self):
        other = row(CANON, "4a5f", C.commence_time, C.first_seen_at, away="Indiana Fever")
        tag, reason = judge([G, other], LISTED, LINES, ghost=GHOST, canonical=CANON)
        assert tag is None and reason.startswith("not one pair")

    def test_a_row_that_is_not_odds_api_anchored_is_refused(self):
        tag, reason = judge([C], LISTED, LINES, ghost=GHOST, canonical=CANON)
        assert tag is None and "15318133" in reason

    def test_an_already_labelled_ghost_is_a_no_op(self):
        tagged = row(GHOST, "430c", G.commence_time, G.first_seen_at, status="live", tagged=True)
        assert judge([tagged, C], LISTED, LINES, ghost=GHOST, canonical=CANON) == (None, "already_tagged")


class FakeService:
    def __init__(self, listed=None, fail=False):
        self.listed, self.fail = listed or {}, fail

    async def get_events(self, sport):
        if self.fail:
            raise RuntimeError("503 from provider")
        return [{"id": i} for i in self.listed.get(sport, ())]

    async def close(self):
        pass


@pytest.fixture
def repair(monkeypatch):
    import app.tasks.base as base
    import scripts.repair_8755_newer_id_twin as mod

    state = {"rows": [G, C], "lines": LINES, "banked": [], "written": [], "confirmed": None}

    @asynccontextmanager
    async def fake_session():
        yield object()

    async def load_rows_by_id(session, ids):
        rows = [r for r in state["rows"] if r.event_id in ids]
        return rows, {r.event_id: "[]" for r in rows}

    async def load_book_lines(session, ids):
        return state["lines"]

    async def ensure_backup(session, tags, current):
        state["banked"] += [t.duplicate_id for t in tags]
        return len(tags)

    async def write_tags(session, tags):
        state["written"] += [t.duplicate_id for t in tags]
        return len(tags), []

    async def tagged_now(session, ids):
        return set(ids) if state["confirmed"] is None else state["confirmed"]

    monkeypatch.setattr(base, "get_task_session", fake_session)
    for name, fn in (("load_rows_by_id", load_rows_by_id), ("load_book_lines", load_book_lines),
                     ("ensure_backup", ensure_backup), ("write_tags", write_tags),
                     ("tagged_now", tagged_now)):
        monkeypatch.setattr(mod, name, fn)
    return mod, state


def go(mod, service, apply):
    return asyncio.run(mod.run(ghost=GHOST, canonical=CANON, apply=apply, service=service))


class TestRun:
    def test_dry_run_writes_nothing(self, repair):
        mod, state = repair
        assert go(mod, FakeService(LISTED), apply=False) == 0
        assert state["banked"] == state["written"] == []

    def test_apply_banks_before_it_labels_and_reads_back(self, repair):
        mod, state = repair
        assert go(mod, FakeService(LISTED), apply=True) == 0
        assert state["banked"] == [GHOST] and state["written"] == [GHOST]

    def test_an_unconfirmed_write_exits_1(self, repair):
        mod, state = repair
        state["confirmed"] = set()
        assert go(mod, FakeService(LISTED), apply=True) == 1

    def test_an_unread_schedule_refuses_and_writes_nothing(self, repair):
        mod, state = repair
        assert go(mod, FakeService(fail=True), apply=True) == 2
        assert state["written"] == []

    def test_a_refusal_exits_2_and_writes_nothing(self, repair):
        mod, state = repair
        state["lines"] = {CANON: LINES[CANON]}
        assert go(mod, FakeService(LISTED), apply=True) == 2
        assert state["banked"] == state["written"] == []

    def test_no_label_when_search_stops_reading_it(self, repair, monkeypatch):
        mod, state = repair
        monkeypatch.setattr(mod, "consumer_is_live", lambda: False)
        assert go(mod, FakeService(LISTED), apply=True) == 2
        assert state["written"] == []
