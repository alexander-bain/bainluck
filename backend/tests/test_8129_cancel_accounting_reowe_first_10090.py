"""#8129 / #10090: the cancel accounting names a re-owed bookkept event first.

The `reowe-bookkept` mutant arm of the PG gate expects the accounting to refuse
with "bookkept event re-owed". On master CI 38072528256 two siblings (8, 11)
happened to be in the ambiguous commit-before-bookkeeping seam when the cancel
landed, so the mutant's event 9 made `redundant` {8, 9, 11} and the size bound
fired first: the mutant was caught under the wrong message. Which siblings sit
in the seam is timing, so the arm was a flake. This replays that exact state
against the real `cancelled_accounting` without a database server (the PG file
is skip-gated locally, so a guard for it must not be).
"""

import pytest

from app.tasks.live_blend_refresh import FRESH_STAMP_WORKERS
from tests.integration import test_live_blend_grouped_commit_8129_pg as gate

ALL = set(range(1, 13))
KEPT = ALL - {6}  # event 6's commit failed
SEAM = {8, 11}  # committed, cancelled before bookkeeping


class _Result:
    def __init__(self, ids):
        self._ids = ids

    def scalars(self):
        return list(self._ids)


class _Session:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, _stmt):
        return _Result(KEPT)  # each kept stamp has its chart point


class _Rig:
    def maker(self):
        return _Session()


class _Refresher:
    def __init__(self, owed):
        written = KEPT - SEAM
        self._owed = owed
        self._last_written_value = {eid: 0.7 for eid in written}
        self._last_snapshot_at = {eid: object() for eid in written}
        self.stats = {"stamped": len(written)}

    def pending_event_ids(self):
        return list(self._owed)


@pytest.fixture(autouse=True)
def _kept(monkeypatch):
    async def committed_events(_rig):
        return set(KEPT)

    monkeypatch.setattr(gate, "committed_events", committed_events)


def test_the_replayed_state_crosses_the_size_bound():
    # Precondition: with 9 re-owed, `redundant` alone would trip the bound.
    assert len((SEAM | {6, 9}) & KEPT) > FRESH_STAMP_WORKERS - 1


async def test_source_state_passes_with_two_siblings_in_the_seam():
    kept, redundant = await gate.cancelled_accounting(
        _Rig(), _Refresher(SEAM | {6}), owed_at_least={6}
    )
    assert kept == KEPT and redundant == SEAM


async def test_reowed_bookkept_event_is_refused_by_name_not_by_size():
    with pytest.raises(AssertionError, match=r"bookkept event re-owed: \[9\]"):
        await gate.cancelled_accounting(
            _Rig(), _Refresher(SEAM | {6, 9}), owed_at_least={6}
        )
