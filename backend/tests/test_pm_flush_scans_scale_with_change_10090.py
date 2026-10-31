"""#10090: the Polymarket flush's per-pass scans scale with what changed, not the buffer.

pm-cpu-sample 00:43–00:48Z on ac9f9c37 (v5989): `owners()`'s price-buffer
setcomp (`<setcomp>:6089`, 7.2 %) still walked every buffered leg to find the
free events' legs, and `standalone_open_outcome_ids` + its nested
`eventless_open` (2.4 % + 2.1 %) made a Python call per buffered leg at five
call sites per flush.

- `EventIndexedPrices` files each buffered leg under its event, so `owners()`
  reads only the free events' legs. Its index must equal a scan after any mix
  of mutations, and after a catalog refresh re-files it.
- `standalone_open_outcome_ids` filters to open legs in C first; same answer.
"""

import ast
import random
from pathlib import Path

import pytest

import app.tasks.polymarket_ws as consumer
from app.tasks.polymarket_ws import EventIndexedPrices, standalone_open_outcome_ids
from tests import test_pm_observation_beside_price_10090 as beside
from tests import test_pm_observation_owners_scan_10090 as owners_scan
from tests.test_blend_preview_display_before_persist_195 import _blends
from tests.test_fresh_observation_preview_10090 import preview_enabled  # noqa: F401


def scanned(buffer, event_of):
    by_event = {}
    for oid in buffer:
        by_event.setdefault(event_of.get(oid), set()).add(oid)
    return by_event


def indexed(buffer):
    return {eid: set(buffer.legs(eid)) for eid in buffer._legs}


# ── the index ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize('seed', range(40))
def test_the_index_equals_a_scan_after_any_mutations(seed):
    rnd = random.Random(seed)
    event_of = {oid: rnd.choice([1, 2, 3, None]) for oid in range(40)}
    buffer = EventIndexedPrices()
    buffer.follow(event_of)
    for _ in range(300):
        op = rnd.randrange(9)
        oid = rnd.randrange(50)  # some legs have no event at all
        if op <= 2:
            buffer[oid] = rnd.random()
        elif op == 3 and oid in buffer:
            del buffer[oid]
        elif op == 4:
            buffer.pop(oid, None)
        elif op == 5 and buffer and rnd.random() < .2:
            buffer.popitem()
        elif op == 6:
            buffer.setdefault(oid, .5)
        elif op == 7:
            if rnd.random() < .5:
                buffer.update({oid: .1, oid + 1: .2})
            else:
                buffer |= {oid: .3}
        elif rnd.random() < .05:
            buffer.clear()
        else:
            # A catalog refresh moves legs between events, then re-files.
            for moved in rnd.sample(range(50), 5):
                event_of[moved] = rnd.choice([1, 2, 4, None])
            event_of.pop(rnd.randrange(50), None)
            buffer.refile()
        assert indexed(buffer) == scanned(buffer, event_of), (seed, op)
        assert all(buffer.legs(eid) for eid in buffer._legs), 'no empty filings'


def test_a_re_write_at_the_same_event_keeps_one_filing():
    buffer = EventIndexedPrices({5: 1})
    buffer[5] = .1
    buffer[5] = .2
    assert set(buffer.legs(1)) == {5} and dict(buffer) == {5: .2}
    assert buffer.legs(99) == ()


def test_the_consumer_buffer_is_indexed_and_follows_the_live_event_map():
    """Wiring: `price_buffer` is the index, follows the map, and the catalog
    refresh re-files it after both map updates and before the lock drops."""
    tree = ast.parse(Path(consumer.__file__).read_text())
    calls = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and getattr(node.target, 'id', None) == 'price_buffer':
            assert isinstance(node.value, ast.Call) and node.value.func.id == 'EventIndexedPrices'
            calls['built'] = node.lineno
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and getattr(node.func.value, 'id', None) in ('price_buffer', 'event_id_by_outcome')):
            key = f'{node.func.value.id}.{node.func.attr}'
            args = [getattr(a, 'id', None) for a in node.args]
            calls.setdefault((key, tuple(args)), []).append(node.lineno)
    follows = calls[('price_buffer.follow', ('event_id_by_outcome',))]
    assert len(follows) == 1 and follows[0] > calls['built']
    refiles = calls[('price_buffer.refile', ())]
    last_update = max(calls[('event_id_by_outcome.update', ('fresh_events',))]
                      + calls[('event_id_by_outcome.update', ('bridge',))])
    assert any(0 < line - last_update <= 2 for line in refiles), (last_update, refiles)


# ── owners() on the index ───────────────────────────────────────────────────

class CountingMap(dict):
    """`event_id_by_outcome` that records which legs `owners()` looked up."""

    looked = None

    def get(self, oid, default=None):
        if CountingMap.looked is not None:
            CountingMap.looked.add(oid)
        return dict.get(self, oid, default)


@pytest.fixture
def indexed_rig(monkeypatch):
    """`consumer_rig` whose price buffer is the production index."""
    made = beside.rig

    def rig(**kwargs):
        state = made(**kwargs)
        mapping = CountingMap(state.ns['event_id_by_outcome'])
        state.ns['event_id_by_outcome'] = mapping
        buffer = EventIndexedPrices(mapping)
        buffer.update(state.ns['price_buffer'])
        state.ns['price_buffer'] = buffer
        return state

    monkeypatch.setattr(beside, 'rig', rig)
    CountingMap.looked = None
    yield
    CountingMap.looked = None


async def test_owners_never_looks_up_a_buffered_leg_of_another_event(monkeypatch, indexed_rig):
    rig = beside.consumer_rig(monkeypatch)
    assert isinstance(rig.ns['price_buffer'], EventIndexedPrices)
    await beside.warm(rig)
    for oid in range(5000, 5300):
        owners_scan.acknowledged_leg(rig, oid, 500 + oid % 7, .25)
    await rig.feed()
    CountingMap.looked = set()
    await rig.ns['flush_observations']()
    looked, CountingMap.looked = CountingMap.looked, None
    assert _blends(rig.frames), 'the free event still advances'
    unrelated = looked & set(range(5000, 5300))
    assert not unrelated, f'{len(unrelated)} legs of other events were looked up'


@pytest.mark.parametrize('partner', ['unacknowledged', 'no-continuity', 'changed', 'acknowledged', 'non-blend'])
@pytest.mark.parametrize('noise', [False, True])
async def test_the_indexed_owners_gives_the_scans_answer(monkeypatch, indexed_rig, partner, noise):
    """The scan path's equivalence cases, run on the index (green before/after)."""
    await owners_scan.test_only_the_same_events_partner_decides_and_unrelated_noise_never_does(
        monkeypatch, partner, noise,
    )


@pytest.mark.parametrize('case', [
    'test_unrelated_buffered_legs_are_never_read',
    'test_an_event_a_withdrawal_already_owns_skips_the_scan',
    'test_a_stamp_with_unknown_membership_still_refuses_everything',
])
async def test_the_scan_paths_other_guards_hold_on_the_index(monkeypatch, indexed_rig, case):
    owners_scan.Counted.reads = 0
    await getattr(owners_scan, case)(monkeypatch)


async def test_a_leg_moved_to_a_pending_event_by_a_refresh_owns_it(monkeypatch, indexed_rig):
    """A buffered leg of another event that a catalog refresh re-files under the
    pending event is seen there (without `refile` it stays under its old event)."""
    rig = beside.consumer_rig(monkeypatch)
    await beside.warm(rig)
    await rig.feed()
    rig.ns['event_id_by_outcome'][103] = 7
    rig.ns['price_buffer'][103] = .5  # unacknowledged, filed under event 7
    rig.ns['event_id_by_outcome'][103] = 1
    rig.ns['price_buffer'].refile()
    await rig.ns['flush_observations']()
    assert not _blends(rig.frames)
    assert 101 in rig.boundary.observation_pending


# ── standalone_open_outcome_ids ─────────────────────────────────────────────

def reference_standalone(outcome_ids, open_ids, event_of, complement_of):
    """The pre-cut body, verbatim in behaviour."""
    def eventless_open(oid):
        return oid in open_ids and event_of.get(oid) is None

    return {
        oid for oid in outcome_ids
        if eventless_open(oid)
        and ((other := complement_of.get(oid)) is None or eventless_open(other))
    }


@pytest.mark.parametrize('seed', range(60))
def test_standalone_gives_the_reference_answer(seed):
    rnd = random.Random(seed)
    universe = range(60)
    open_ids = {oid for oid in universe if rnd.random() < .6}
    event_of = {oid: rnd.choice([None, 1, 2]) for oid in universe if rnd.random() < .7}
    complement_of = {}
    for a in universe:
        if rnd.random() < .3:
            b = rnd.randrange(70)
            complement_of[a], complement_of[b] = b, a
    buffered = {oid: .5 for oid in rnd.sample(range(70), 30)}
    for outcome_ids in (buffered, list(buffered), set(buffered), []):
        for opened in (open_ids, frozenset(open_ids), list(open_ids)):
            assert standalone_open_outcome_ids(
                outcome_ids, opened, event_of, complement_of,
            ) == reference_standalone(outcome_ids, set(opened), event_of, complement_of)


class CountingComplements(dict):
    reads = 0

    def get(self, oid, default=None):
        CountingComplements.reads += 1
        return dict.get(self, oid, default)


def test_standalone_does_no_per_leg_work_for_legs_that_are_not_open():
    """Most buffered legs are game legs; they cost nothing here now."""
    CountingComplements.reads = 0
    buffered = {oid: .5 for oid in range(1000)}
    open_ids = {1, 2, 3}
    complements = CountingComplements({1: 2, 2: 1, 500: 501, 501: 500})
    assert standalone_open_outcome_ids(buffered, open_ids, {3: 9}, complements) == {1, 2}
    assert CountingComplements.reads <= 2, CountingComplements.reads
