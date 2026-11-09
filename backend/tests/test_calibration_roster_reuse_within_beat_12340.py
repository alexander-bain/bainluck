"""#12340: a beat reads the futures roster once, not twice.

Measured on the Nov 9, 07:49Z beat: ``stage_counts['read:futures_generation']``
was 2 and the two reads cost 345,971 ms between them. The publish pass reads the
roster, defers the unit loop (CAL-P994 / D45(A)), and the rebuild pass of the
SAME beat used to read it again. Now the rebuild pass takes the publish pass's
roster, but only while the inputs the staged cursor is keyed to are unchanged
(Fable's condition 1); otherwise it reads, as before. Nothing outlives the beat
(condition 3): the hold is on the runner and is released on every exit of the
rebuild pass.

The harness is ``test_calibration_publish_first_994``'s: the real loop, the real
cursor codec, an in-memory cursor store.
"""
import pytest

from tests.test_calibration_publish_first_994 import (  # noqa: F401 (fixture)
    _FakeDB,
    _FakeRunner,
    _publish_pass,
    _rebuild_pass,
    _roster,
    _serving_state,
    wiring,
)


class _CountingDB(_FakeDB):
    """``_FakeDB`` that also counts roster reads (the statement with no params)."""

    def __init__(self, roster, **kw):
        super().__init__(roster, **kw)
        self.roster_reads = 0

    async def execute(self, statement, params=None):
        if params is None:
            self.roster_reads += 1
        return await super().execute(statement, params)


async def _deferred_beat(pc, roster, *, window_ms=10_000):
    """A publish pass that defers its rebuild, on a counting DB."""
    await _serving_state(pc, roster)
    db = _CountingDB(roster)
    _merged, runner, db = await _publish_pass(pc, roster=roster, window_ms=window_ms, db=db)
    assert runner.rebuild_deferred, "the scenario needs a beat that defers"
    return runner, db


@pytest.mark.asyncio
async def test_a_deferred_beat_reads_the_roster_once(wiring):
    pc, _store = wiring
    runner, db = await _deferred_beat(pc, _roster(60))
    assert db.roster_reads == 1

    await _rebuild_pass(pc, db, runner)

    assert db.roster_reads == 1, "the rebuild pass read the roster a second time"
    assert runner.ledger.gauges.get("roster:reused") == 1
    assert db.unit_reads > 0, "the rebuild pass must still run its units"


@pytest.mark.asyncio
async def test_a_changed_unit_fingerprint_throws_the_held_roster_away(wiring, monkeypatch):
    pc, _store = wiring
    runner, db = await _deferred_beat(pc, _roster(60))
    real = pc.staged_unit_fingerprint()
    monkeypatch.setattr(pc, "staged_unit_fingerprint", lambda: real + "-moved")

    await _rebuild_pass(pc, db, runner)

    assert db.roster_reads == 2, "a roster held under another statement was reused"
    assert "roster:reused" not in runner.ledger.gauges


@pytest.mark.asyncio
async def test_a_changed_population_version_throws_the_held_roster_away(wiring):
    pc, _store = wiring
    runner, db = await _deferred_beat(pc, _roster(60))
    held = getattr(runner, pc.REUSABLE_ROSTER_ATTR)
    setattr(runner, pc.REUSABLE_ROSTER_ATTR, (held[0], "another-population", held[2]))

    await _rebuild_pass(pc, db, runner)

    assert db.roster_reads == 2


@pytest.mark.asyncio
async def test_the_hold_is_released_by_the_pass_that_uses_it(wiring):
    pc, _store = wiring
    runner, db = await _deferred_beat(pc, _roster(60))
    assert getattr(runner, pc.REUSABLE_ROSTER_ATTR) is not None

    await _rebuild_pass(pc, db, runner)

    assert getattr(runner, pc.REUSABLE_ROSTER_ATTR) is None


@pytest.mark.asyncio
async def test_a_publish_pass_that_does_not_defer_holds_nothing(wiring):
    pc, _store = wiring
    # A cold cursor runs its units inline and never defers.
    _merged, runner, _db = await _publish_pass(pc, roster=_roster(60), window_ms=10_000)
    assert not runner.rebuild_deferred
    assert getattr(runner, pc.REUSABLE_ROSTER_ATTR, None) is None


@pytest.mark.asyncio
async def test_every_exit_of_the_rebuild_releases_the_hold(wiring):
    pc, _store = wiring
    runner = _FakeRunner(window_ms=0)
    runner.rebuild_deferred = True
    pc._offer_roster_for_rebuild(runner, _roster(3))

    result = await pc._run_deferred_rebuild(runner)

    assert result["status"] == "no_window"
    assert getattr(runner, pc.REUSABLE_ROSTER_ATTR) is None


@pytest.mark.asyncio
async def test_reuse_banks_what_a_fresh_read_banks_and_one_more(wiring):
    """The reused roster is the same generation, so the units banked are the same ones."""
    pc, store = wiring
    roster = _roster(60)

    runner, db = await _deferred_beat(pc, roster, window_ms=600)
    start = dict(store["cursor"])
    await _rebuild_pass(pc, db, runner)
    reused = store["cursor"]["committed_units"]

    store["cursor"] = start
    runner2 = _FakeRunner(window_ms=600)
    db2 = _CountingDB(roster)
    _merged, runner2, db2 = await _publish_pass(pc, roster=roster, window_ms=600, db=db2, runner=runner2)
    pc.drop_roster_for_rebuild(runner2)  # force the old behaviour: a fresh read
    await _rebuild_pass(pc, db2, runner2)

    assert db2.roster_reads == 2
    fresh = store["cursor"]["committed_units"]
    # The same units in the same order: one generation, one plan. The fresh read
    # spends one more stage of the window (the fake runner charges 100 ms a
    # stage, one unit's cost), so the reused beat banks one unit MORE, which is
    # the whole point.
    assert reused[: len(fresh)] == fresh
    assert len(reused) == len(fresh) + 1
