"""LAT-P274 (#2143 residual): the size guard that had nothing re-measuring it.

`test_feed_market_load_fits_the_shared_wire_lat_p221` asks the question every
size guard should be asked — *what re-measures the number it is comparing to?* —
and cannot answer it for itself. Its `PROD_OUTCOMES` is hand-copied out of a
production query, so the alarm is only ever as fresh as the last person to run
that query. It has already failed in exactly that way: copied 2026-09-04 and not
re-read, it was still sizing 6,904 outcomes two weeks later while production
carried 9,325.

The count it needs was already being computed on every build and thrown away.
`assert_plain_data` must walk the artifact counting nodes to enforce
`_MAX_NODES`, and then discarded the total when it returned. LAT-P274 returns
it, records a per-namespace high-water mark, and warns once when the growth
alarm is crossed.

WHAT THESE TESTS ARE FOR, and the traps they are written against:

  * The returned count must be THE SAME count `_MAX_NODES` is enforced on. A
    second, parallel counter that happened to agree today would drift silently,
    and the guard reading it would be decoration. Pinned by driving `_MAX_NODES`
    to exactly the returned value and one below it.
  * The alarm must FAIL OPEN. Crossing it may not change whether the artifact is
    shared — `_MAX_NODES` refuses, this only speaks. An alarm that also degraded
    the cache gives the operator an incentive to silence it.
  * The alarm must be able to STAY QUIET. A warning that fires on every build is
    not a signal, and a test that only ever proves the loud case cannot tell a
    working alarm from one wired to a constant `True`.
  * The alarm must not be derived from `_MAX_NODES` (LAT-P273). An alarm
    expressed as a fraction of the cap it warns about rises with that cap, so
    raising the safety cap would relax the alarm in the same commit.
"""

import asyncio
import logging

import pytest

from app.utils import principal_independent_cache as pic


@pytest.fixture(autouse=True)
def _cold_worker():
    """Every test here starts as a cold worker and leaves one behind.

    The gauge and the once-per-process alarm latch are process-global, so
    without this a crossing in one test silences the next — the cross-test leak
    that makes an alarm look like it never fires.
    """
    pic.clear_shared_builds()
    yield
    pic.clear_shared_builds()


def _build(value):
    async def _builder():
        return value

    return _builder


def _get(namespace, key, value):
    return asyncio.run(pic.get_or_build(namespace, key, _build(value)))


# --------------------------------------------------------------------------
# the count is the REAL count, not a parallel one
# --------------------------------------------------------------------------


def test_assert_plain_data_returns_the_number_of_nodes_it_walked():
    """A hand-countable shape, counted by hand.

    5 nodes: the dict, the inner list, its two ints, and the None.

    DICT KEYS ARE NOT NODES. The walk type-checks every key but only recurses
    into values, so `{"a": ..., "b": ...}` costs nothing for "a" and "b". Worth
    pinning explicitly: the first version of this test counted the two keys,
    asserted 7, and was wrong about the thing the whole gauge reports. Anyone
    sizing a payload against this number needs to know it counts values.
    """
    value = {"a": [1, 2], "b": None}

    assert pic.assert_plain_data(value) == 5


def test_the_returned_count_is_the_same_count_the_safety_cap_is_enforced_on():
    """The anti-drift pin, and the reason this is a return value and not a
    second counter.

    If the number handed back were computed anywhere but the `_MAX_NODES` walk,
    the two could disagree and every guard reading the gauge would be measuring
    something the cache does not actually enforce. Driving the cap to exactly
    the returned value must PASS and to one below it must RAISE; only the real
    count satisfies both.
    """
    value = {"rows": [[i, str(i), None] for i in range(40)]}
    counted = pic.assert_plain_data(value)

    original = pic._MAX_NODES
    try:
        pic._MAX_NODES = counted
        pic.assert_plain_data(value)  # exactly at the cap: allowed

        pic._MAX_NODES = counted - 1
        with pytest.raises(pic.NotPlainData):
            pic.assert_plain_data(value)
    finally:
        pic._MAX_NODES = original


# --------------------------------------------------------------------------
# the gauge
# --------------------------------------------------------------------------


def test_a_build_records_its_node_count_against_its_namespace():
    value = {"rows": [[i, str(i)] for i in range(25)]}
    expected = pic.assert_plain_data(value)

    _get("lat_p274_ns", ("k",), value)

    assert pic.shared_build_stats()["node_high_water"]["lat_p274_ns"] == expected


def test_the_gauge_is_a_HIGH_WATER_mark_and_a_smaller_later_build_cannot_lower_it():
    """Composition churn, not growth, is the normal reason this number moves.

    The top-700 population reshuffles between builds, so a last-seen gauge
    reports whatever the most recent shuffle happened to be — and answers "how
    big has this got?" wrongly at exactly the moment the answer matters.
    """
    big = {"rows": [[i, str(i)] for i in range(60)]}
    small = {"rows": [[1, "1"]]}
    big_nodes = pic.assert_plain_data(big)

    _get("lat_p274_ns", ("big",), big)
    _get("lat_p274_ns", ("small",), small)

    assert pic.assert_plain_data(small) < big_nodes
    assert pic.shared_build_stats()["node_high_water"]["lat_p274_ns"] == big_nodes


def test_two_namespaces_are_gauged_apart():
    """The whole point of the guard is naming WHICH artifact grew."""
    big = {"rows": [[i, str(i)] for i in range(50)]}
    small = {"rows": [[1, "1"]]}

    _get("lat_p274_big", ("k",), big)
    _get("lat_p274_small", ("k",), small)

    gauge = pic.shared_build_stats()["node_high_water"]
    assert gauge["lat_p274_big"] == pic.assert_plain_data(big)
    assert gauge["lat_p274_small"] == pic.assert_plain_data(small)
    assert gauge["lat_p274_big"] > gauge["lat_p274_small"]


def test_the_gauge_cannot_grow_a_bucket_per_arbitrary_namespace():
    """A long-lived worker must not accumulate one entry per arbitrary string.

    Same discipline as `_ns_stats`: past `MAX_TRACKED_NAMESPACES` everything
    folds into the overflow bucket rather than growing without bound.
    """
    for i in range(pic.MAX_TRACKED_NAMESPACES + 10):
        _get(f"lat_p274_flood_{i}", ("k",), {"v": i})

    gauge = pic.shared_build_stats()["node_high_water"]
    assert len(gauge) <= pic.MAX_TRACKED_NAMESPACES + 1
    assert pic._NS_OVERFLOW_BUCKET in gauge


def test_the_gauge_and_its_alarm_latch_reset_with_the_worker():
    _get("lat_p274_ns", ("k",), {"rows": [[1, "1"]]})
    assert pic.shared_build_stats()["node_high_water"]

    pic.clear_shared_builds()

    assert pic.shared_build_stats()["node_high_water"] == {}
    assert pic._ns_node_alarmed == set()


def test_the_stats_payload_ships_the_alarm_beside_the_gauge():
    """A gauge whose reader has to go and find what it is judged against is a
    number, not a signal."""
    stats = pic.shared_build_stats()

    assert stats["node_alarm"] == pic.NODE_GROWTH_ALARM
    assert isinstance(stats["node_high_water"], dict)


def test_the_gauge_is_not_folded_into_by_namespace_which_the_fleet_rail_SUMS():
    """LAT-P272's rail sums `by_namespace` across workers.

    A high-water mark is a gauge, and the sum of per-worker maxima is a number
    with no meaning. This pins the gauge OUT of the summed view — the mistake is
    a one-line one and it would produce a plausible, wrong fleet number.
    """
    _get("lat_p274_ns", ("k",), {"rows": [[i, str(i)] for i in range(30)]})

    by_ns = pic.shared_build_stats()["by_namespace"].get("lat_p274_ns", {})
    assert not any("node" in counter for counter in by_ns)


# --------------------------------------------------------------------------
# the alarm
# --------------------------------------------------------------------------


def test_crossing_the_growth_alarm_warns_and_names_the_namespace(monkeypatch, caplog):
    value = {"rows": [[i, str(i)] for i in range(40)]}
    monkeypatch.setattr(pic, "NODE_GROWTH_ALARM", pic.assert_plain_data(value) - 1)

    with caplog.at_level(logging.WARNING, logger=pic.logger.name):
        _get("lat_p274_loud", ("k",), value)

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    message = warnings[0].getMessage()
    assert "lat_p274_loud" in message
    assert "growth alarm" in message


def test_the_alarm_stays_QUIET_below_the_threshold(monkeypatch, caplog):
    """The anti-vacuity half.

    Without this, an alarm hard-wired to fire always passes the test above and
    tells an operator nothing. Same payload, same namespace, alarm one node
    ABOVE the count instead of one below.
    """
    value = {"rows": [[i, str(i)] for i in range(40)]}
    monkeypatch.setattr(pic, "NODE_GROWTH_ALARM", pic.assert_plain_data(value) + 1)

    with caplog.at_level(logging.WARNING, logger=pic.logger.name):
        _get("lat_p274_quiet", ("k",), value)

    assert [r for r in caplog.records if r.levelno == logging.WARNING] == []


def test_the_alarm_speaks_once_per_process_not_once_per_cold_feed(monkeypatch, caplog):
    value = {"rows": [[i, str(i)] for i in range(40)]}
    monkeypatch.setattr(pic, "NODE_GROWTH_ALARM", pic.assert_plain_data(value) - 1)

    with caplog.at_level(logging.WARNING, logger=pic.logger.name):
        for i in range(5):
            _get("lat_p274_loud", (f"k{i}",), value)

    assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == 1


def test_crossing_the_alarm_does_not_stop_the_artifact_being_shared(monkeypatch):
    """FAIL OPEN. `_MAX_NODES` refuses; the growth alarm only speaks.

    An alarm that degraded the cache would hand the operator an incentive to
    silence it, which is the opposite of what an early warning is for.
    """
    value = {"rows": [[i, str(i)] for i in range(40)]}
    monkeypatch.setattr(pic, "NODE_GROWTH_ALARM", 1)

    returned = _get("lat_p274_loud", ("k",), value)

    assert returned == value
    assert pic.peek_shared_build("lat_p274_loud") == value
    assert pic.shared_build_stats()["refused"] == 0


def test_a_refused_artifact_is_not_gauged(monkeypatch):
    """An ORM-shaped value never becomes a node count.

    `_note_nodes` is called with the walk's return, so a walk that RAISES must
    record nothing — otherwise the gauge would carry a partial count for an
    artifact that was never shared.
    """

    class _NotPlain:
        pass

    _get("lat_p274_refused", ("k",), {"orm": _NotPlain()})

    assert pic.shared_build_stats()["refused"] == 1
    assert "lat_p274_refused" not in pic.shared_build_stats()["node_high_water"]


# --------------------------------------------------------------------------
# does it reach a reader?
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_production_can_actually_read_the_gauge(monkeypatch):
    """The half that makes this a signal rather than a local variable.

    LAT-P221's whole lesson was an artifact refused on every publish for weeks
    while a counter faithfully recorded it and NO ROUTE READ THE COUNTER. A
    gauge only `shared_build_stats()` can see would repeat that exactly.

    `/api/admin/shared-build-stats` returns `stats` wholesale today, so this
    passes by construction — which is the point of pinning it. The day someone
    switches that endpoint to an explicit key list, this goes red instead of the
    gauge going quietly invisible.
    """
    from httpx import ASGITransport, AsyncClient

    from app.main import app
    from app.routes import admin as admin_routes

    monkeypatch.setattr(admin_routes, "_check_admin_secret", lambda *a, **k: None)

    value = {"rows": [[i, str(i)] for i in range(30)]}
    expected = pic.assert_plain_data(value)
    await pic.get_or_build("market_load", ("k",), _build(value))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/admin/shared-build-stats")

    assert resp.status_code == 200, resp.text
    stats = resp.json()["stats"]
    assert stats["node_high_water"]["market_load"] == expected
    assert stats["node_alarm"] == pic.NODE_GROWTH_ALARM


# --------------------------------------------------------------------------
# LAT-P273's separation, pinned again on this side
# --------------------------------------------------------------------------


def test_the_growth_alarm_is_not_a_fraction_of_the_safety_cap():
    """Raising `_MAX_NODES` must not relax the growth alarm.

    The two answer different questions — "is it unsafe to walk?" versus "is this
    artifact getting big?" — and one number served both until LAT-P273, which is
    why neither was trustworthy. A literal constant is the enforcement.
    """
    alarm_before = pic.NODE_GROWTH_ALARM
    original = pic._MAX_NODES
    try:
        pic._MAX_NODES = original * 4
        assert pic.NODE_GROWTH_ALARM == alarm_before
    finally:
        pic._MAX_NODES = original


def test_the_growth_alarm_fires_before_the_safety_cap_refuses():
    """The ordering that makes the alarm worth having: it must be reachable
    while the share still works."""
    assert pic.NODE_GROWTH_ALARM < pic._MAX_NODES
