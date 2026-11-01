"""#10090: the flush scans answered from the installed catalog give the walk's answer.

`PMCatalogScans` precomputes, at each catalog install, which open legs are
standalone and which legs each event has. The flushes then answer
`standalone_open_outcome_ids` with one set intersection and the observation
scan (`price_owned_events`) by reading only the legs of the events it asks
about. Each case runs both on the same inputs and requires the same set; the
switch (`PM_SCAN_PREFILTER=0`), a stale map and a foreign map take the walk.
"""

import ast
import inspect
import random
import re

import pytest

import app.tasks.polymarket_ws as pm
from app.tasks.polymarket_ws import (
    PMCatalogScans,
    price_owned_events,
    standalone_open_outcome_ids,
)


@pytest.fixture(autouse=True)
def switch_on(monkeypatch):
    monkeypatch.setattr(pm, "PM_SCAN_PREFILTER", True)


def _world(rng, n):
    """Linked, eventless and paired legs; some partners unbuffered or bridged."""
    oids = rng.sample(range(1, 40 * n + 10), n)
    events = {}
    for oid in oids:
        roll = rng.random()
        if roll < 0.45:
            events[oid] = rng.randrange(1, max(2, n // 4))
        elif roll < 0.5:
            events[oid] = None  # a mapped leg with no event
        # else unmapped: `.get` is None too
    complement = {}
    shuffled = oids[:]
    rng.shuffle(shuffled)
    for a, b in zip(shuffled[0:n // 2:2], shuffled[1:n // 2:2]):
        complement[a], complement[b] = b, a
    for a in shuffled[n // 2: n // 2 + n // 10]:
        b = 10**9 + a  # a partner that is not buffered, sometimes bridged
        complement[a], complement[b] = b, a
        if rng.random() < 0.5:
            events[b] = rng.randrange(1, max(2, n // 4))
    open_ids = {oid for oid in list(oids) + list(complement) if rng.random() < 0.8}
    return oids, events, complement, open_ids


def _walk_guard():
    calls = []

    def walk(*args):
        calls.append(args)
        return standalone_open_outcome_ids(*args)

    return walk, calls


@pytest.mark.parametrize("seed", range(40))
def test_standalone_matches_the_walk(seed):
    rng = random.Random(seed)
    n = rng.choice([0, 1, 2, 7, 50, 400])
    oids, events, complement, open_ids = _world(rng, n)
    scans = PMCatalogScans()
    scans.rebuild(open_ids, events, complement)
    walk, calls = _walk_guard()
    extra = [10**9 + 7, 10**12]  # legs the catalog never named
    buffer = {oid: rng.random() for oid in oids + extra}
    subset = set(rng.sample(oids, len(oids) // 3)) if oids else set()
    for outcome_ids in (buffer, set(oids), list(reversed(oids)), oids + oids[:3], subset, {}):
        got = scans.standalone(walk, outcome_ids, open_ids, events, complement)
        assert got == standalone_open_outcome_ids(outcome_ids, open_ids, events, complement)
        assert isinstance(got, set)
    assert calls == [], "the installed catalog must answer without the walk"


def test_a_pair_with_one_bridged_side_stays_whole():
    # 1/2: 2 bridged, so neither; 3/4 both eventless, so both; 5 has no
    # partner; 6's partner is not open; 7 has an event.
    events = {2: 900, 7: 901}
    complement = {1: 2, 2: 1, 3: 4, 4: 3, 6: 60, 60: 6}
    open_ids = {1, 2, 3, 4, 5, 6, 7}
    scans = PMCatalogScans()
    scans.rebuild(open_ids, events, complement)
    walk, calls = _walk_guard()
    buffer = dict.fromkeys(range(1, 9), 0.5)
    assert scans.standalone(walk, buffer, open_ids, events, complement) == {3, 4, 5}
    assert calls == []


def _catalog():
    # 1 linked; 2 and 3 open and eventless with no partner.
    return {1, 2, 3}, {1: 10}, {}


@pytest.mark.parametrize("change", ["event", "open", "complement"])
def test_a_map_written_outside_an_install_takes_the_walk(change):
    open_ids, events, complement = _catalog()
    scans = PMCatalogScans()
    scans.rebuild(open_ids, events, complement)
    walk, calls = _walk_guard()
    buffer = dict.fromkeys([1, 2, 3, 4], 0.5)
    assert scans.standalone(walk, buffer, open_ids, events, complement) == {2, 3}
    assert calls == []
    if change == "event":
        events[2] = 20
        expected = {3}
    elif change == "open":
        open_ids.add(4)
        expected = {2, 3, 4}
    else:
        complement[3], complement[1] = 1, 3  # 3's partner is linked
        expected = {2}
    assert scans.standalone(walk, buffer, open_ids, events, complement) == expected
    assert len(calls) == 1


@pytest.mark.parametrize("foreign", ["event", "open", "complement"])
def test_equal_maps_of_another_consumer_take_the_walk(foreign):
    open_ids, events, complement = _catalog()
    scans = PMCatalogScans()
    scans.rebuild(open_ids, events, complement)
    walk, calls = _walk_guard()
    maps = {"open": open_ids, "event": events, "complement": complement}
    maps[foreign] = type(maps[foreign])(maps[foreign])
    buffer = dict.fromkeys([1, 2, 3], 0.5)
    assert scans.standalone(
        walk, buffer, maps["open"], maps["event"], maps["complement"]) == {2, 3}
    assert len(calls) == 1


def test_the_switch_off_walks_and_installs_nothing(monkeypatch):
    open_ids, events, complement = _catalog()
    scans = PMCatalogScans()
    scans.rebuild(open_ids, events, complement)
    walk, calls = _walk_guard()
    buffer = dict.fromkeys([1, 2, 3], 0.5)
    monkeypatch.setattr(pm, "PM_SCAN_PREFILTER", False)
    assert scans.standalone(walk, buffer, open_ids, events, complement) == {2, 3}
    scans.rebuild(open_ids, events, complement)
    monkeypatch.setattr(pm, "PM_SCAN_PREFILTER", True)
    assert scans.standalone(walk, buffer, open_ids, events, complement) == {2, 3}
    assert len(calls) == 2


def _observation_world(rng, n):
    oids, events, _complement, _open = _world(rng, n)
    buffer = {}
    continuity, ack = {}, {}
    for oid in oids:
        value = round(rng.random(), 6)
        roll = rng.random()
        if roll < 0.25:
            buffer[oid] = value  # never acknowledged: owns its event
        elif roll < 0.5:
            buffer[oid] = value
            continuity[oid] = ack[oid] = (rng.randrange(9), value)  # passes
        elif roll < 0.6:
            buffer[oid] = value + 4e-8  # sub-rounding noise still passes
            continuity[oid] = ack[oid] = (1, value)
        elif roll < 0.7:
            buffer[oid] = value  # A-B-A: same value back, newer token unacknowledged
            continuity[oid] = (2, value)
            ack[oid] = (1, value)
        elif roll < 0.8:
            buffer[oid] = value + 1e-5  # moved off the acknowledged value
            continuity[oid] = ack[oid] = (1, value)
        elif roll < 0.9:
            buffer[oid] = value
            continuity[oid] = (1, value)  # acknowledgement missing
        # else: catalogued, not buffered
    linked = sorted({e for e in events.values() if e is not None})
    non_blend = set(rng.sample(oids, len(oids) // 6)) if oids else set()
    return buffer, events, linked, non_blend, continuity, ack


@pytest.mark.parametrize("seed", range(40))
def test_price_owned_matches_the_walk(seed):
    rng = random.Random(1000 + seed)
    n = rng.choice([0, 1, 3, 60, 500])
    buffer, events, linked, non_blend, continuity, ack = _observation_world(rng, n)
    scans = PMCatalogScans()
    scans.rebuild(set(), events, {})
    frees = [
        set(),
        set(linked),
        set(rng.sample(linked, len(linked) // 3)) if linked else set(),
        {10**12},  # an event no leg belongs to
        set(linked) | {None},  # None admits unmapped legs: the walk answers
    ]
    for free in frees:
        walk = price_owned_events(buffer, free, events, non_blend, continuity, ack)
        assert scans.price_owned(buffer, free, events, non_blend, continuity, ack) == walk
        assert price_owned_events(
            buffer, free, events, non_blend, continuity, ack, scans.legs_by_event,
        ) == walk


def test_price_owned_named_cases():
    buffer = {1: 0.5, 2: 0.4, 3: 0.3 + 4e-8, 4: 0.2, 5: 0.7, 6: 0.6, 8: 0.1}
    events = {1: 10, 2: 20, 3: 30, 4: 40, 5: 50, 6: 60, 7: 70, 8: 80, 9: 80}
    continuity = {2: (1, 0.4), 3: (1, 0.3), 4: (2, 0.2), 5: (1, 0.71), 6: (1, 0.6)}
    ack = {2: (1, 0.4), 3: (1, 0.3), 4: (1, 0.2), 5: (1, 0.71), 6: (1, 0.6)}
    non_blend = {6}
    free = {10, 20, 30, 40, 50, 60, 70, 80}
    scans = PMCatalogScans()
    scans.rebuild(set(), events, {})
    # 1 unacknowledged, 4 A-B-A, 5 moved, 8 unacknowledged (9 unbuffered);
    # 2/3 acknowledged, 6 a prop, 7 not buffered.
    expected = {10, 40, 50, 80}
    assert price_owned_events(buffer, free, events, non_blend, continuity, ack) == expected
    assert scans.price_owned(buffer, free, events, non_blend, continuity, ack) == expected


def test_price_owned_reads_only_the_free_events_legs():
    class Counted(float):
        reads = 0

        def __float__(self):
            Counted.reads += 1
            return float.__float__(self)

    events = {oid: oid % 50 for oid in range(5000)}
    buffer = {oid: Counted(0.25) for oid in events}
    continuity = {oid: (1, 0.25) for oid in events}
    ack = dict(continuity)
    scans = PMCatalogScans()
    scans.rebuild(set(), events, {})
    assert scans.price_owned(buffer, {3}, events, set(), continuity, ack) == set()
    assert Counted.reads == 100, "only event 3's legs are read"
    # A leg added outside an install: the stale index would miss it; the walk
    # finds it (no continuity, so it owns event 3).
    events[5000] = 3
    buffer[5000] = Counted(0.9)
    assert scans.price_owned(buffer, {3}, events, set(), continuity, ack) == {3}


def test_the_switch_reads_off_words(monkeypatch):
    for raw, on in ((None, True), ("", True), ("1", True), ("on", True),
                    ("0", False), (" OFF ", False), ("false", False), ("no", False)):
        if raw is None:
            monkeypatch.delenv("PM_SCAN_PREFILTER", raising=False)
        else:
            monkeypatch.setenv("PM_SCAN_PREFILTER", raw)
        assert pm._scan_prefilter_env() is on


CATALOG_MAPS = ("event_id_by_outcome", "open_outcome_ids", "open_complement_of")
MUTATORS = {"update", "clear", "pop", "popitem", "setdefault", "add", "discard",
            "remove", "intersection_update", "difference_update",
            "symmetric_difference_update"}


def test_every_catalog_map_write_in_the_consumer_is_followed_by_a_rebuild():
    """Exactness rests on this: the three maps change only where a rebuild
    follows before any await. A new writer elsewhere reddens this test.

    #10090 11/01: a handover's install may instead `invalidate()` the scans
    before any await (they answer by the exact walk meanwhile), then
    `rebuild_cooperatively` once the maps settle: the synchronous rebuild froze
    the loop at every 10-minute handover."""
    src = inspect.getsource(pm._run_polymarket_ws_consumer)
    tree = ast.parse(src)
    writes, rebuilds, awaits, cooperative = [], [], [], []
    for node in ast.walk(tree):
        if isinstance(node, ast.Await):
            awaits.append(node.lineno)
        if isinstance(node, (ast.AsyncWith, ast.AsyncFor)):
            awaits.append(node.lineno)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            target = node.func.value
            if node.func.attr in ("rebuild", "invalidate") \
                    and ast.unparse(target) == "catalog_boundary.scans":
                rebuilds.append(node.lineno)
            if node.func.attr == "rebuild_cooperatively" \
                    and ast.unparse(target) == "catalog_boundary.scans":
                cooperative.append(node.lineno)
            if node.func.attr in MUTATORS and isinstance(target, ast.Name) \
                    and target.id in CATALOG_MAPS:
                writes.append(node.lineno)
        if isinstance(node, (ast.Assign, ast.AugAssign, ast.Delete)):
            targets = node.targets if isinstance(node, (ast.Assign, ast.Delete)) else [node.target]
            for t in targets:
                base = t.value if isinstance(t, ast.Subscript) else t
                if isinstance(base, ast.Name) and base.id in CATALOG_MAPS:
                    if isinstance(t, ast.Subscript) or isinstance(node, ast.AugAssign):
                        writes.append(node.lineno)
        if isinstance(node, ast.For):
            # `for owners in (market_by_outcome, event_id_by_outcome): del owners[oid]`
            if isinstance(node.iter, ast.Tuple) and any(
                isinstance(e, ast.Name) and e.id in CATALOG_MAPS for e in node.iter.elts
            ):
                writes.append(node.lineno)
    assert writes, "the guard must see the catalog install's writes"
    assert len(rebuilds) >= 2, "one rebuild at start, one at each install"
    assert cooperative and max(cooperative) > max(rebuilds), (
        "an install that only invalidated rebuilds the scans after it")
    for line in writes:
        after = [r for r in rebuilds if r > line]
        assert after, f"line {line}: a catalog map write with no rebuild after it"
        between = [a for a in awaits if line < a < after[0]]
        assert not between, f"line {line}: an await before its rebuild ({between})"
    # The initial build comes after the three maps exist.
    first = min(rebuilds)
    for name in CATALOG_MAPS:
        defined = re.search(rf"^\s+{name}(: [^=]+)? = ", src, re.M)
        assert defined and src[:defined.start()].count("\n") + 1 < first
