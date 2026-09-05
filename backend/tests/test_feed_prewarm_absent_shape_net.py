"""LAT-P112 — guards for the absent-shape net on the feed warm rail.

THE DEFECT THESE EXIST TO MAKE IMPOSSIBLE, in the numbers that found it.

`#2236` closed the live-shape half of this class and proved its invariant
`PERIOD + BUDGET <= ceiling` against the host beat's DECLARED period of 120s.
The declared period is not what the queue delivers. Measured on production
2026-08-29, slug `f0b512b8`:

* `precompute-discover-candidate-base` — the beat that hosts
  `_prewarm_discover_feed_responses`, i.e. the only thing that keeps the
  anonymous Discover and Sports first-paint entries alive — is routed to
  `background`. Its last 49 fires: p50 gap **138s**, **ten gaps over 300s**,
  maximum **2,511s**. Declared: 120s.
* The non-live stale ceiling is `FEED_RESPONSE_STALE_TTL_SECONDS` = 300s. Past
  it the entry is not stale, it is GONE, and the next arrival pays a full build.
* Production's own always-sampled `/api/feed` window, same hour:
  `hit` p50 **10.8 ms**, `stale_hit` p50 **14.4 ms**, `miss` **3,722.7 ms**.
* The control that makes this a statement about the QUEUE and not the
  scheduler: `prewarm-live-feed-shapes`, same beat scheduler, same 24 hours,
  routed to `realtime` (depth 0 against `background`'s 25) — p50 gap **40s**
  against a declared 40s, one excursion over 120s in 49 fires.

So the fix rides the rail that is punctual and asks the one question it was not
asking: is anything simply gone? Every test below is one half of making that
question mandatory, or of stopping the answer from costing anything when it is
"no" — which is the answer on every healthy pass.
"""

import inspect
import re
import textwrap
from importlib import import_module
from unittest.mock import MagicMock, patch

import pytest

from app.utils.feed_cache import (
    FEED_LIVE_REPUBLISH_BUDGET_S,
    FEED_RESPONSE_STALE_TTL_SECONDS,
)

pcp = import_module("app.tasks.precompute_category_pages")


# --- The fake ----------------------------------------------------------------


def _fake_rc(*, live=None, shape_keys=None, present_keys=()):
    """A MagicMock Redis with real dicts behind BOTH hashes and a key space.

    Two hashes, not one: the existing `_fake_rc` in `test_feed_live_prewarm.py`
    backs every `hgetall` with the same dict, which cannot express "this shape
    is not live AND its mirror is gone" — the exact state this net selects on.
    """
    hashes = {
        pcp.FEED_PREWARM_LIVE_SHAPES_KEY: dict(live or {}),
        pcp.FEED_PREWARM_SHAPE_KEYS_KEY: dict(shape_keys or {}),
    }
    keyspace = set(present_keys)

    rc = MagicMock()
    rc.hgetall.side_effect = lambda key: dict(hashes.setdefault(key, {}))
    rc.hset.side_effect = lambda key, field, value: hashes.setdefault(
        key, {}
    ).__setitem__(field, value)
    rc.hdel.side_effect = lambda key, field: hashes.setdefault(key, {}).pop(field, None)
    rc.exists.side_effect = lambda key: 1 if key in keyspace else 0
    rc.get.return_value = None
    rc._hashes = hashes
    rc._keyspace = keyspace
    return rc


def _all_labels():
    return [s["label"] for s in pcp.FEED_PREWARM_SHAPES]


def _keys_for(labels):
    return {label: f"feed_cache:{label}" for label in labels}


def _mirrors_for(labels):
    return [f"feed_cache:{label}:stale" for label in labels]


def _run_live_pass(rc):
    """Drive `_prewarm_live_feed_shapes` with `_prewarm_feed_shape` stubbed."""
    import asyncio

    warmed = []

    async def fake_warm(shape, _rc, *, deadline_s):
        warmed.append((shape["label"], deadline_s))
        return {"outcome": "ok", "items": 3, "live": True}

    with patch.object(pcp, "_prewarm_feed_shape", fake_warm), patch(
        "app.tasks.redis_state.get_redis_client", lambda: rc
    ):
        result = asyncio.run(pcp._prewarm_live_feed_shapes())
    return result, warmed


# --- The selection: what "gone" means ----------------------------------------


def test_a_first_paint_shape_with_no_stale_mirror_is_rebuilt():
    """The headline. This is the 3,722.7 ms build, moved off the user's wait.

    One shape's mirror is missing and every other mirror is present. Only the
    missing one may be rebuilt — a net that rebuilds its neighbours is a second
    warm rail wearing a safety net's name, and it would put four extra cold
    builds on the realtime queue every 40 seconds.
    """
    labels = _all_labels()
    gone = labels[0]
    rc = _fake_rc(
        shape_keys=_keys_for(labels),
        present_keys=_mirrors_for(labels[1:]),
    )

    assert pcp._absent_prewarm_labels(rc) == {gone}

    _, warmed = _run_live_pass(rc)
    assert [label for label, _ in warmed] == [gone]


def test_a_healthy_rail_builds_nothing_and_the_net_stays_free():
    """The state on every ordinary pass, and it must cost no build at all.

    `#2236`'s affordability argument for a 40s beat is that the idle pass is one
    `HGETALL` and one `SETEX`. LAT-P112 may add reads to that and must not add
    work: with every mirror present the net's answer is the empty set and the
    pass still reports `no_live_shapes`.
    """
    labels = _all_labels()
    rc = _fake_rc(shape_keys=_keys_for(labels), present_keys=_mirrors_for(labels))

    assert pcp._absent_prewarm_labels(rc) == set()

    result, warmed = _run_live_pass(rc)
    assert warmed == []
    assert result == "no_live_shapes"


def test_a_label_with_no_remembered_key_is_skipped_and_not_built():
    """Fail closed. The direction of failure is the whole argument.

    Immediately after a deploy the shape-key hash is empty, and "I do not know
    this shape's key" must mean "do nothing" rather than "assume the worst and
    rebuild". Assuming the worst would make every deploy trigger five cold
    builds on the realtime queue inside the first 40 seconds — the moment that
    queue is least able to absorb them. The net arms itself per shape, as the
    host rail warms each one and records its key.
    """
    labels = _all_labels()
    rc = _fake_rc(shape_keys={}, present_keys=[])

    assert pcp._absent_prewarm_labels(rc) == set()

    _, warmed = _run_live_pass(rc)
    assert warmed == []

    # And per shape, not all-or-nothing: one known key with a dead mirror is
    # rebuilt even while the other four are still unknown.
    rc = _fake_rc(shape_keys=_keys_for([labels[2]]), present_keys=[])
    assert pcp._absent_prewarm_labels(rc) == {labels[2]}


def test_the_probe_reads_the_stale_mirror_and_never_the_head():
    """Probing the head would rebuild every shape on almost every pass.

    The head TTL is 60s (`FEED_RESPONSE_TTL_ANON_SECONDS`) and the host rail is
    a 120s beat, so the head is legitimately absent most of the time and a
    reader served from `<key>:stale` waits ~14 ms. That is not a hole. The hole
    is the mirror going, because `routes/feed.py::_read_shared_feed_cache` has
    nothing left to fall back to.

    Asserted on the probe's own call arguments rather than on an outcome,
    because the outcomes coincide whenever both keys are absent — which is
    exactly the fixture a careless version of this test would use.
    """
    labels = _all_labels()
    rc = _fake_rc(
        shape_keys=_keys_for(labels),
        # Heads present, mirrors gone: the hole, dressed as health.
        present_keys=[f"feed_cache:{label}" for label in labels],
    )

    assert pcp._absent_prewarm_labels(rc) == set(labels), (
        "the net read the head key — a live head with a dead mirror is still a "
        "hole, because the head dies at 60s and nothing catches the next reader"
    )

    probed = [call.args[0] for call in rc.exists.call_args_list]
    assert probed, "the net performed no existence probe at all"
    for key in probed:
        assert key.endswith(":stale"), (
            f"probed {key!r} — reading the head makes this pass rebuild every "
            "shape every 40s, which is the cost #2236's docstring refused"
        )


def test_a_live_label_is_never_also_an_absent_target():
    """No shape may be built twice in one pass.

    A live shape is already being republished. Selecting it a second time
    because its mirror also happens to be gone would double the pass's cost at
    precisely the moment it is most loaded, and would publish the older of two
    builds over the newer.
    """
    labels = _all_labels()
    live = {labels[0]: "1"}
    rc = _fake_rc(live=live, shape_keys=_keys_for(labels), present_keys=[])

    absent = pcp._absent_prewarm_labels(rc, exclude=set(live))
    assert labels[0] not in absent

    _, warmed = _run_live_pass(rc)
    built = [label for label, _ in warmed]
    assert len(built) == len(set(built)), f"a shape was built twice: {built}"
    assert set(built) == set(labels)


# --- The ordering: the net must not endanger #2236's ceiling ------------------


def test_live_labels_take_their_budget_slice_before_absent_ones():
    """`PERIOD + BUDGET <= 60` is load-bearing; the net must not spend it first.

    The budget is allocated in list order by `_prewarm_target_deadline`, so the
    ORDER of `targets` is the priority rule, not a cosmetic detail. If an absent
    shape were allowed to run first it could consume its slice before the live
    republish starts, and a live payload published late is the #2236 defect
    returning through the door its own fix left open.
    """
    labels = _all_labels()
    live_label = labels[-1]
    rc = _fake_rc(
        live={live_label: "1"},
        shape_keys=_keys_for(labels),
        present_keys=[],
    )

    _, warmed = _run_live_pass(rc)
    order = [label for label, _ in warmed]
    assert order[0] == live_label, (
        f"absent shapes ran before the live one ({order}) — the live republish "
        "must never queue behind a safety net"
    )
    # It is genuinely last in the declared shape order, so this cannot pass by
    # accident of `FEED_PREWARM_SHAPES` happening to list it first.
    assert labels.index(live_label) == len(labels) - 1


def test_the_net_changes_neither_term_of_the_2236_invariant():
    """A safety net that widened the budget would break the thing it protects.

    Stated as a test rather than as a comment because the tempting fix for "the
    net ran out of budget" is to widen `FEED_LIVE_REPUBLISH_BUDGET_S`, and the
    ceiling arithmetic has zero headroom.

    🔴 **#3233 RE-ANCHORED THIS ON THE INTENT.** It used to match the source text
    `budget_left = float(FEED_LIVE_REPUBLISH_BUDGET_S)`. That line was the serial
    allocator, and the serial allocator was the #3233 defect — so this guard's
    literal made the bug part of the contract, and removing the bug broke a test
    whose stated purpose ("no second budget") the repair never violated. A
    source-text guard has to match the property, not the statement that happened
    to carry it (`r_shared_judgment_needs_a_callsite_guard`: match the NAME
    SHAPE, not the line).
    """
    from app.utils.feed_cache import (
        live_republish_headroom_s,
        live_republish_target_headroom_s,
    )

    assert live_republish_headroom_s() >= 0
    # #3233's second term: the wall must also cover the WORK, not merely be
    # divided fairly among it.
    assert live_republish_target_headroom_s(len(pcp.FEED_PREWARM_SHAPES)) >= 0

    source = textwrap.dedent(inspect.getsource(pcp._prewarm_live_feed_shapes))
    assert "FEED_LIVE_REPUBLISH_BUDGET_S" in source, (
        "the pass no longer starts from the declared budget — the net may have "
        "been given an allowance of its own, which is a second budget the "
        "#2236 invariant does not know about"
    )
    # `*_BUDGET_S` and not "BUDGET": the pass's comments discuss the invariant in
    # prose ("PERIOD + BUDGET == 60"), and a guard that cannot tell a constant
    # from a sentence fails on documentation.
    other_budgets = {
        name
        for name in re.findall(r"\b[A-Z]+(?:_[A-Z]+)*_BUDGET_S\b", source)
        if name != "FEED_LIVE_REPUBLISH_BUDGET_S"
    }
    assert not other_budgets, (
        f"the pass references a second budget symbol {sorted(other_budgets)} — "
        "#2236's invariant is stated over ONE budget term and cannot see another"
    )


def test_no_absent_target_can_be_starved_by_the_ones_ahead_of_it():
    """Gotcha #34, inherited. Fair share must hold with the net's targets in the list."""
    labels = _all_labels()
    n = len(labels)
    floor = FEED_LIVE_REPUBLISH_BUDGET_S / n

    rc = _fake_rc(shape_keys=_keys_for(labels), present_keys=[])
    _, warmed = _run_live_pass(rc)

    assert len(warmed) == n
    for label, deadline_s in warmed:
        assert deadline_s >= floor - 1e-9, (
            f"{label} was allotted {deadline_s}s, below the {floor}s floor — the "
            "net's targets are not being given a fair share of the budget"
        )


# --- The remembered key: the route's answer, carried forward ------------------


def test_the_remembered_key_is_the_one_the_route_resolved():
    """Written from the scope readback, never re-derived — the LAT-P001 rule.

    The comment above `FEED_PREWARM_LIVE_SHAPES_KEY` forbids a per-key marker
    precisely because it would have to re-derive the response cache key outside
    the route. This records the key the route itself produced, which is the
    opposite move; the test is what keeps it the opposite move.
    """
    from contextlib import asynccontextmanager
    import asyncio

    from app.utils.feed_cache import FEED_PREWARM_KEY_SCOPE_KEY, FEED_PREWARM_SCOPE_KEY

    rc = _fake_rc()

    async def fake_get_feed(**kwargs):
        request = kwargs["request"]
        assert request.scope.get(FEED_PREWARM_SCOPE_KEY) is True
        request.scope[FEED_PREWARM_KEY_SCOPE_KEY] = "feed_cache:resolved-by-route"
        return {"items": [{"id": "a"}], "total": 1}

    @asynccontextmanager
    async def fake_session():
        yield MagicMock()

    shape = dict(pcp.FEED_PREWARM_SHAPES[0])
    with patch("app.routes.feed.get_feed", fake_get_feed), patch(
        "app.tasks.base.get_task_session", fake_session
    ):
        result = asyncio.run(pcp._prewarm_feed_shape(shape, rc))

    assert result["outcome"] == "ok"
    assert rc._hashes[pcp.FEED_PREWARM_SHAPE_KEYS_KEY] == {
        shape["label"]: "feed_cache:resolved-by-route"
    }
    rc.expire.assert_any_call(
        pcp.FEED_PREWARM_SHAPE_KEYS_KEY, pcp.FEED_PREWARM_SHAPE_KEYS_TTL_S
    )


def test_the_net_never_derives_a_cache_key_of_its_own():
    """A source guard, because no behavioural test can see the difference.

    An independently-derived key that happens to agree today is correct today
    and is the LAT-P001 two-writers defect the moment the key builder changes —
    and it fails in the direction that matters: the net would probe a key nobody
    publishes, find it absent every pass, and rebuild every shape forever.
    """
    source = textwrap.dedent(inspect.getsource(pcp._absent_prewarm_labels))
    for forbidden in ("feed_response_cache_key", "feed_cache_key", "_cache_shape"):
        assert forbidden not in source, (
            f"`_absent_prewarm_labels` mentions {forbidden!r} — it must read the "
            "key the route resolved out of the hash, never build one"
        )


def test_the_remembered_key_outlives_the_longest_observed_hole():
    """The mapping is a cache, not a dead-man's switch — unlike the live set.

    If it expired on the liveness hash's 300s dead-man's timer, then the very
    outage this net exists for would erase the net: a 2,511s gap means no warm,
    which means no rewrite, which means the mapping lapses and every shape falls
    back to "unknown, skip". The net would be armed only when it was not needed.
    """
    assert pcp.FEED_PREWARM_SHAPE_KEYS_TTL_S > pcp.FEED_PREWARM_LIVE_SHAPES_TTL_S
    assert pcp.FEED_PREWARM_SHAPE_KEYS_TTL_S >= 3_600, (
        "the remembered key must outlive the 2,511s worst observed warm gap, or "
        "the net disarms itself during the outage it exists to cover"
    )


def test_a_key_marker_write_failure_never_breaks_the_warm():
    """The marker is an optimisation input; the warm is the product."""
    rc = MagicMock()
    rc.hset.side_effect = RuntimeError("redis down")
    rc.expire.side_effect = RuntimeError("redis down")
    pcp._record_shape_cache_key(rc, "discover", "feed_cache:abc")


# --- Failure directions and decoding -----------------------------------------


def test_the_absent_reader_fails_to_empty_not_to_everything():
    """A Redis error must rebuild NOTHING, not every shape on the site.

    Same direction rule as `_live_prewarm_labels`, and for a sharper reason: a
    reader that treated an error as "gone" would turn one transient Redis blip
    into five cold feed builds every 40 seconds until it cleared.
    """
    rc = MagicMock()
    rc.hgetall.side_effect = RuntimeError("redis down")
    assert pcp._absent_prewarm_labels(rc) == set()

    rc = MagicMock()
    rc.hgetall.return_value = {"discover": "feed_cache:abc"}
    rc.exists.side_effect = RuntimeError("redis down")
    assert pcp._absent_prewarm_labels(rc) == set()


def test_bytes_from_a_raw_redis_client_are_decoded():
    """`get_redis_client()` is not guaranteed to be `decode_responses`.

    An undecoded label matches no shape and an undecoded key probes
    `b'...':stale` as a string — either way the net silently selects nothing and
    reports the healthy state, which is gotcha #53's shape exactly.
    """
    label = _all_labels()[0]
    rc = MagicMock()
    rc.hgetall.return_value = {label.encode(): b"feed_cache:bytes"}
    rc.exists.side_effect = lambda key: 0
    assert pcp._absent_prewarm_labels(rc) == {label}
    assert rc.exists.call_args.args[0] == "feed_cache:bytes:stale"


def test_an_empty_remembered_key_is_not_probed():
    """A blank value must be "unknown", not a probe of `":stale"`.

    `EXISTS ":stale"` returns 0 for every shape, so treating a blank as a key
    would mark the whole pool absent off one bad hash write.
    """
    rc = MagicMock()
    rc.hgetall.return_value = {_all_labels()[0]: ""}
    rc.exists.side_effect = lambda key: 0
    assert pcp._absent_prewarm_labels(rc) == set()
    rc.exists.assert_not_called()


def test_a_remembered_label_outside_the_shape_set_is_ignored():
    """A stale mapping from a deleted shape must not invent a target."""
    rc = _fake_rc(
        shape_keys={"a_shape_that_was_deleted": "feed_cache:ghost"},
        present_keys=[],
    )
    assert pcp._absent_prewarm_labels(rc) == set()


# --- Observability ------------------------------------------------------------


def test_absent_labels_are_reported_separately_from_live_labels():
    """A hole the net covered must still be visible AS a hole.

    Merging the two into `live_labels` would make this fix hide its own trigger:
    the `background` queue could starve the host rail for an hour and every
    report would read like a busy evening of live games. An empty
    `absent_labels` on every pass is the healthy state; a non-empty one is a
    queue incident, and the two must be distinguishable without a deploy.
    """
    import json

    labels = _all_labels()
    gone = labels[1]
    rc = _fake_rc(
        live={labels[0]: "1"},
        shape_keys=_keys_for(labels),
        present_keys=_mirrors_for([label for label in labels if label != gone]),
    )

    _run_live_pass(rc)

    written = {call.args[0]: call.args[2] for call in rc.setex.call_args_list}
    report = json.loads(written[pcp.FEED_LIVE_PREWARM_STATUS_KEY])
    assert report["live_labels"] == [labels[0]]
    assert report["absent_labels"] == [gone]


def test_the_healthy_report_states_the_empty_hole_rather_than_omitting_it():
    """Gotcha #53: an absent field and a zero-yield field are different facts.

    "This deploy does not have the net" and "the net found nothing" have
    opposite remedies, and a missing key states both at once.
    """
    import json

    labels = _all_labels()
    rc = _fake_rc(shape_keys=_keys_for(labels), present_keys=_mirrors_for(labels))
    _run_live_pass(rc)

    written = {call.args[0]: call.args[2] for call in rc.setex.call_args_list}
    report = json.loads(written[pcp.FEED_LIVE_PREWARM_STATUS_KEY])
    assert "absent_labels" in report
    assert report["absent_labels"] == []


# --- The premise the whole fix rests on ---------------------------------------


def test_the_net_rides_a_different_queue_from_the_rail_it_covers():
    """If both beats sit on `background` the net is inert, and silently so.

    This is the entire causal claim, executed. The host rail is late because
    `background` is contended; a net hosted on the same queue would be late in
    the same passes for the same reason and would report success on every pass
    it eventually ran. The measured difference across one 24h window: host beat
    p50 gap 138s / max 2,511s on `background`, net beat p50 gap 40s / max 202s
    on `realtime`.
    """
    from app.tasks import celery_app

    conf = celery_app.conf
    host = conf.beat_schedule["precompute-discover-candidate-base"]
    net = conf.beat_schedule["prewarm-live-feed-shapes"]

    assert net["options"]["queue"] == "realtime"
    assert conf.task_routes["app.tasks.prewarm_live_feed_shapes"] == {
        "queue": "realtime"
    }
    host_queue = host.get("options", {}).get("queue", conf.task_default_queue)
    assert host_queue != net["options"]["queue"], (
        "the warm rail and the net that covers it now share a queue — whatever "
        "starves one starves the other, and LAT-P112's fix is inert"
    )


def test_the_hole_this_closes_is_arithmetic_and_not_a_hypothesis():
    """The host beat's declared period is inside the ceiling; its delivery is not.

    Kept as a live assertion so the day someone shortens the ceiling below the
    declared period, this fires and says the hole is no longer merely a delivery
    problem — it is a design one, and the net is no longer sufficient.
    """
    from app.tasks import celery_app

    schedule = celery_app.conf.beat_schedule["precompute-discover-candidate-base"][
        "schedule"
    ]
    minutes = sorted(schedule.minute)
    declared_period_s = (minutes[1] - minutes[0]) * 60.0

    assert declared_period_s < FEED_RESPONSE_STALE_TTL_SECONDS, (
        f"the host warm beat's DECLARED period is {declared_period_s}s against a "
        f"{FEED_RESPONSE_STALE_TTL_SECONDS}s stale ceiling — the hole is now in "
        "the schedule itself and a delivery-time safety net cannot close it"
    )
    # And the observed gap that motivated the net, recorded as a number rather
    # than as prose so a later reader can compare against it: p50 138s, ten of
    # 49 gaps over 300s, max 2,511s (production, 2026-08-29, slug f0b512b8).
    assert declared_period_s == pytest.approx(120.0)


def test_the_grouped_feed_shapes_are_deliberately_outside_the_net():
    """A named scope decision, pinned so it stays a decision.

    `/api/futures/grouped-feed` has the same exposure but is the Sports tab's
    THIRD request and does not gate first paint (`cold_path_snapshot.py` marks
    it `blocking=False`). Widening the net to it buys realtime slot time for a
    wait nobody is doing. If that changes, this test is where the argument is.
    """
    labels = {s["label"] for s in pcp.FEED_PREWARM_SHAPES}
    grouped = {s["label"] for s in pcp.GROUPED_FEED_PREWARM_SHAPES}
    assert not (labels & grouped)

    rc = _fake_rc(shape_keys={label: f"feed_cache:{label}" for label in grouped})
    assert pcp._absent_prewarm_labels(rc) == set(), (
        "a grouped-feed label reached the net's candidate set — the net selects "
        "over FEED_PREWARM_SHAPES only, by declaration"
    )
