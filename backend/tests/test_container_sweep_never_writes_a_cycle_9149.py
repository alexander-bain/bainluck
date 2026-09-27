"""#9149 — the container sweep never tags a row `duplicate-of` a row that is
itself already a proven duplicate.

Production, 2026-09-27: 25 pairs of Polymarket rows each carried
``provenance:duplicate-of:<the other>``, all 50 banked by this sweep in both
directions. The election flipped between passes, the old canonical became the
new duplicate, and the sweep tagged it ``duplicate-of`` the row that already
named it. ``not_a_proven_duplicate`` hides both rows, so the fixture left every
rail — the whole J2 League slate of 2026-09-26, Gotham FC v Chicago Stars.

These tests drive the REAL ``run_polymarket_container_twin_sweep`` with only the
database edges faked, and hand it the one input the older harness never did:
the rows' CURRENT tags.
"""

from __future__ import annotations

import asyncio
import contextlib

from app.services.anchor_channel import duplicate_tag
from app.tasks import polymarket_container_twin_sweep as sweep
from app.tasks.polymarket_container_twin_sweep import split_todo
from app.utils.polymarket_container_twins import (
    ContainerMarket,
    ContainerRow,
    ContainerTag,
)
from app.utils.task_verdict import verdict_for

KICKOFF = "2026-09-26T08:00:00Z"
#: Blaublitz Akita v Albirex Niigata, 2026-09-26 — one of the ten J2 pairs.
BASE_ID = 15311278
COMPANION_ID = 15311291
TITLE = "Blaublitz Akita vs. Albirex Niigata"


def _m(event_id: int, name: str, vgs: str = KICKOFF) -> ContainerMarket:
    return ContainerMarket(event_id=event_id, name=name, venue_game_start=vgs)


FAMILY = [
    _m(BASE_ID, TITLE),
    _m(COMPANION_ID, f"{TITLE} - More Markets"),
]


def _filler():
    return [
        _m(900000 + i, f"Filler {i} FC vs. Filler {i} United")
        for i in range(sweep.MIN_MARKETS_FLOOR)
    ]


def _rows(winner: int, loser: int) -> dict[int, ContainerRow]:
    return {
        winner: ContainerRow(winner, identity_rank=(2,), venue_game_starts=frozenset({KICKOFF})),
        loser: ContainerRow(loser, identity_rank=(1,), venue_game_starts=frozenset({KICKOFF})),
    }


def _run(monkeypatch, *, rows, current_tags):
    written: list[ContainerTag] = []
    markets = [*_filler(), *FAMILY]
    known = {m.event_id: ContainerRow(m.event_id, identity_rank=(1,)) for m in markets}
    known.update(rows)

    async def _load_rows(session, *, lookback, lookahead):
        return list(markets), known, dict(current_tags)

    async def _ensure_backup(session, todo, tags):
        return len(todo)

    async def _write_tags(session, todo, *, progress_every=0):
        written.extend(todo)
        return len(todo), []

    async def _tagged_now(session, ids):
        return set(ids)

    class _Session:
        async def rollback(self):
            pass

    @contextlib.asynccontextmanager
    async def _fake_session():
        yield _Session()

    import app.tasks.base as base

    monkeypatch.setattr(base, "get_task_session", _fake_session)
    monkeypatch.setattr(sweep, "load_rows", _load_rows)
    monkeypatch.setattr(sweep, "ensure_backup", _ensure_backup)
    monkeypatch.setattr(sweep, "write_tags", _write_tags)
    monkeypatch.setattr(sweep, "tagged_now", _tagged_now)
    monkeypatch.setattr(sweep, "fold_is_live", lambda: True)
    summary = asyncio.run(sweep.run_polymarket_container_twin_sweep(apply=True))
    return summary, written


class TestTheFlipNoLongerWritesTheSecondHalf:
    def test_a_flipped_election_does_not_tag_the_old_canonical(self, monkeypatch):
        """The specimen. Last pass: companion → base. This pass the election
        prefers the companion, so the plan says base → companion — and the
        companion already names the base. Writing it is the cycle."""
        summary, written = _run(
            monkeypatch,
            rows=_rows(winner=COMPANION_ID, loser=BASE_ID),
            current_tags={COMPANION_ID: f'["{duplicate_tag(BASE_ID)}"]', BASE_ID: "[]"},
        )

        assert written == []
        assert summary["to_tag"] == 0
        assert summary["withheld_canonical_is_duplicate"] == 1
        assert summary["withheld_samples"] == [f"{BASE_ID}->{COMPANION_ID}"]
        assert summary["already_tagged"] == 0
        assert summary["terminal"] == "complete"
        assert verdict_for("polymarket_container_twin_sweep", summary).verdict == "complete"

    def test_control_the_same_family_untagged_is_still_written(self, monkeypatch):
        """Strawman control: the guard must not be refusing the family itself.
        Same rows, same election, no tags on disk → the tag is written."""
        summary, written = _run(
            monkeypatch,
            rows=_rows(winner=COMPANION_ID, loser=BASE_ID),
            current_tags={COMPANION_ID: "[]", BASE_ID: "[]"},
        )

        assert [(t.duplicate_id, t.canonical_id) for t in written] == [
            (BASE_ID, COMPANION_ID)
        ]
        assert summary["withheld_canonical_is_duplicate"] == 0

    def test_an_unflipped_family_stays_already_tagged_not_withheld(self, monkeypatch):
        """The steady state: the election agrees with the tag already on disk.
        That is `already_tagged`, never a withholding."""
        summary, written = _run(
            monkeypatch,
            rows=_rows(winner=BASE_ID, loser=COMPANION_ID),
            current_tags={COMPANION_ID: f'["{duplicate_tag(BASE_ID)}"]', BASE_ID: "[]"},
        )

        assert written == []
        assert summary["already_tagged"] == 1
        assert summary["withheld_canonical_is_duplicate"] == 0

    def test_a_canonical_tagged_by_another_rail_is_withheld_too(self, monkeypatch):
        """The canonical names some THIRD row (another rail's proof). Writing
        would be a second hop the reader never follows."""
        summary, written = _run(
            monkeypatch,
            rows=_rows(winner=BASE_ID, loser=COMPANION_ID),
            current_tags={BASE_ID: f'["{duplicate_tag(15195323)}"]', COMPANION_ID: "[]"},
        )

        assert written == []
        assert summary["withheld_canonical_is_duplicate"] == 1


class TestSplitTodo:
    def test_the_three_outcomes(self):
        planned = [
            ContainerTag(1, 2, "fresh"),
            ContainerTag(3, 4, "duplicate already tagged"),
            ContainerTag(5, 6, "canonical already tagged"),
        ]
        todo, withheld = split_todo(planned, {3, 6})
        assert [t.duplicate_id for t in todo] == [1]
        assert [t.duplicate_id for t in withheld] == [5]

    def test_a_row_tagged_both_ways_is_skipped_not_withheld(self):
        """A duplicate that already carries a tag is left alone first — the
        pre-existing rule — whatever its canonical's state."""
        todo, withheld = split_todo([ContainerTag(1, 2, "x")], {1, 2})
        assert todo == [] and withheld == []
