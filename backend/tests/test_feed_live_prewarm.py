"""#2236 — guards for the live feed republish pass.

The defect these exist to make impossible: two individually-correct changes
shipped the same day and their PRODUCT was that every live-containing feed shape
paid a full cold build once per 60 seconds, forever, while the warm rail
reported success on every pass.

* #2216 capped a payload containing a live card at `ttl 30 / stale 60`. Past 60s
  the page is rebuilt, not served older. That is the fix Alex's stale-score
  report asked for and it is not negotiable here.
* LAT-P099 enrolled the native Sports shape in the pre-warm, which is hosted
  inside the every-120s `precompute_discover_candidate_base` beat.

120 > 60, so the key was gone a full minute before its next chance to be
refreshed. Measured on production v3911 as a clean repeating sawtooth:
`miss → hit → stale_hit → stale_hit → miss`, every 60s, on `limit=50&mode=sports`
and `limit=20&mode=sports` alike, with the cold sample at 1.0–1.5s (14.4s once)
against 0.31–0.35s warm.

Nothing in the codebase compared those two numbers, because they lived in two
files and neither was expressed in terms of the other. Every test below is one
half of making that comparison mandatory.
"""

import inspect
import textwrap
from importlib import import_module
from unittest.mock import MagicMock, patch

import pytest

from app.utils.feed_cache import (
    FEED_LIVE_REPUBLISH_BUDGET_S,
    FEED_LIVE_REPUBLISH_PERIOD_S,
    FEED_RESPONSE_STALE_TTL_LIVE_SECONDS,
    FEED_RESPONSE_STALE_TTL_SECONDS,
    live_republish_headroom_s,
)

pcp = import_module("app.tasks.precompute_category_pages")


# --- The invariant #2236 was the absence of ----------------------------------


def test_a_republish_pass_lands_before_the_previous_one_expires():
    """PERIOD + BUDGET <= the live stale ceiling. The red-first gate for #2236.

    Stated as a worst case, not an average. A pass fires at t=0 and publishes a
    payload whose stale mirror dies at t=60. The next pass fires at t=PERIOD and
    may consume its whole BUDGET before it publishes. If the sum exceeds the
    ceiling there is a window where the key is simply gone and a user pays a cold
    build — which is precisely the measured state of production before this, with
    PERIOD=120 and no budget term in the arithmetic at all.

    This assertion fails on every way of reintroducing the bug: lengthening the
    period, widening the budget, or shortening the ceiling underneath both.
    """
    headroom = live_republish_headroom_s()
    assert headroom >= 0, (
        f"period {FEED_LIVE_REPUBLISH_PERIOD_S}s + budget "
        f"{FEED_LIVE_REPUBLISH_BUDGET_S}s exceeds the live stale ceiling "
        f"{FEED_RESPONSE_STALE_TTL_LIVE_SECONDS}s by {-headroom}s — a live shape "
        "will be gone from the cache before its next republish, which is #2236"
    )


def test_the_120s_host_beat_is_recorded_as_insufficient_for_live_shapes():
    """The reason this pass exists, executed rather than asserted in prose.

    If someone later deletes `prewarm-live-feed-shapes` believing the 120s pass
    covers it, this is the test that says why it does not. It deliberately reads
    the host beat's real period out of the schedule instead of hardcoding 120 —
    the day that beat drops below the ceiling, the narrow pass is genuinely
    redundant and this test should be the thing that says so.
    """
    from app.tasks import celery_app

    schedule = celery_app.conf.beat_schedule["precompute-discover-candidate-base"][
        "schedule"
    ]
    minutes = sorted(schedule.minute)
    host_period_s = (minutes[1] - minutes[0]) * 60.0

    assert host_period_s > FEED_RESPONSE_STALE_TTL_LIVE_SECONDS, (
        f"the host warm beat now runs every {host_period_s}s, inside the "
        f"{FEED_RESPONSE_STALE_TTL_LIVE_SECONDS}s live ceiling — the separate "
        "live republish pass may be redundant; re-derive it before deleting it"
    )
    # And the general shape of the trap: the host beat IS sufficient for the
    # ordinary (non-live) stale window, which is exactly why the gap was
    # invisible. One number covered one class of payload and not the other.
    assert host_period_s < FEED_RESPONSE_STALE_TTL_SECONDS


def test_the_period_is_declared_beside_the_ceiling_not_beside_the_beat():
    """The beat must import the period, never restate it.

    A literal in the beat schedule is how #2236 happened: the ceiling moved and
    the period could not know. `float(FEED_LIVE_REPUBLISH_PERIOD_S)` in the
    schedule means whoever edits the ceiling is editing the period's immediate
    neighbour, and the invariant test above fires the moment they disagree.
    """
    from app.tasks import celery_app

    entry = celery_app.conf.beat_schedule["prewarm-live-feed-shapes"]
    assert entry["schedule"] == float(FEED_LIVE_REPUBLISH_PERIOD_S)

    source = inspect.getsource(import_module("app.tasks"))
    marker = '"prewarm-live-feed-shapes": {'
    start = source.index(marker)
    block = source[start : source.index("},", start)]
    assert "FEED_LIVE_REPUBLISH_PERIOD_S" in block, (
        "the beat entry restates its period as a literal — that is the two-files"
        " arrangement #2236 was"
    )


def test_the_hard_time_limit_is_below_the_period():
    """A wedged pass must be dead before its successor fires.

    This is what makes an overlap lock unnecessary rather than merely unlikely:
    a task whose hard limit exceeds its own beat period can have two instances
    building the same shapes at once, and the second would publish an OLDER
    payload over a newer one — a staleness bug introduced by the staleness fix.
    """
    from app.tasks import _LIVE_PREWARM_HARD_LIMIT_S, _LIVE_PREWARM_SOFT_LIMIT_S

    assert _LIVE_PREWARM_HARD_LIMIT_S < FEED_LIVE_REPUBLISH_PERIOD_S, (
        f"hard limit {_LIVE_PREWARM_HARD_LIMIT_S}s >= period "
        f"{FEED_LIVE_REPUBLISH_PERIOD_S}s — two passes can overlap"
    )
    assert _LIVE_PREWARM_SOFT_LIMIT_S < _LIVE_PREWARM_HARD_LIMIT_S, (
        "soft must precede hard or the pass dies in an untracked SIGKILL and "
        "reports nothing at all"
    )
    assert FEED_LIVE_REPUBLISH_BUDGET_S < _LIVE_PREWARM_SOFT_LIMIT_S, (
        "the pass budget must expire before Celery's soft limit, so a slow pass "
        "reports per-shape timeouts instead of one opaque SoftTimeLimitExceeded"
    )


def test_the_beat_carries_an_expires_bound_of_exactly_one_period():
    """#1609's rule, and here it is the contract rather than hygiene.

    🔴 **Added because the mutation battery found nothing guarding it.** The
    existing `test_1609_warmer_beats_carry_an_expires_bound` asserts that every
    beat LISTED in `_EXPIRING_WARMER_BEATS` has a bound — it cannot notice a beat
    that is simply absent from the list. Deleting this beat's entry was green
    across every suite, which is the same species of hole the list exists to
    close: a guard over the members of a set is not a guard over membership.

    Why the bound matters more here than for an ordinary warmer: the whole point
    of the task is to publish a payload no older than 60 s. A message still
    queued past its own period would republish a build the next fire is about to
    redo — it cannot be anything but superseded.
    """
    from app.tasks import _EXPIRING_WARMER_BEATS

    assert "prewarm-live-feed-shapes" in _EXPIRING_WARMER_BEATS, (
        "the live republish beat has no `expires` bound — a message that "
        "outlives its own period republishes a build its successor is about to "
        "redo, on the one task whose contract is freshness"
    )
    assert _EXPIRING_WARMER_BEATS["prewarm-live-feed-shapes"] == int(
        FEED_LIVE_REPUBLISH_PERIOD_S
    ), "the bound must be exactly one period — the flat #1609 rule"


def test_the_pass_runs_on_realtime_and_not_on_background():
    """A queue choice that is part of the correctness argument, not of the cost one.

    `PERIOD + BUDGET <= 60` assumes the pass STARTS at its period. `background`
    is documented in `app/tasks/__init__.py` as having ~one effective slot for
    ~45 beats, is measured at ~90% slot occupancy, and its own budget module
    (`app/utils/typeahead_beat_budget.py`) says ordinary co-tenant bursts produce
    multi-minute waits. A pass that starts two minutes late publishes nothing in
    time: the key already expired and the user already paid the cold build.

    So placing this on `background` would make the fix PARTIALLY INERT, and
    inert in the silent way — the beat would report success on every pass it
    eventually ran. That is why this is a test and not a comment.

    Both surfaces are asserted because beat `options` override `task_routes`; a
    disagreement makes the queue depend on whether the task was published by the
    beat or by hand.
    """
    from app.tasks import celery_app

    conf = celery_app.conf
    entry = conf.beat_schedule["prewarm-live-feed-shapes"]
    assert entry["options"]["queue"] == "realtime", entry["options"]
    assert conf.task_routes["app.tasks.prewarm_live_feed_shapes"] == {
        "queue": "realtime"
    }
    # And the fall-through hazard, named: deleting the queue option is the same
    # as choosing `background`, because that is the default.
    assert conf.task_default_queue == "background"


# --- The live set: what the pass selects on ----------------------------------


def _fake_rc(hash_state=None):
    """A MagicMock Redis with a real dict behind the live-shape hash."""
    state = dict(hash_state or {})
    rc = MagicMock()
    rc.hgetall.side_effect = lambda key: dict(state)
    rc.hset.side_effect = lambda key, field, value: state.__setitem__(field, value)
    rc.hdel.side_effect = lambda key, field: state.pop(field, None)
    rc.get.return_value = None
    rc._state = state
    return rc


def test_a_live_warm_enters_the_set_and_a_not_live_warm_leaves_it():
    """Both directions, on every warm. Clearing matters as much as setting.

    A shape that goes not-live but stays in the set keeps a 40s beat rebuilding a
    payload whose own TTL is 60/300 and which the 120s pass already covers —
    paying three times over for nothing, silently, until someone reads a bill.
    """
    rc = _fake_rc()

    pcp._record_shape_liveness(rc, "sports_native", True)
    assert pcp._live_prewarm_labels(rc) == {"sports_native"}
    rc.expire.assert_called_with(
        pcp.FEED_PREWARM_LIVE_SHAPES_KEY, pcp.FEED_PREWARM_LIVE_SHAPES_TTL_S
    )

    pcp._record_shape_liveness(rc, "sports_native", False)
    assert pcp._live_prewarm_labels(rc) == set()


def test_the_live_set_ttl_outlives_the_beat_that_refreshes_it():
    """A dead-man's switch, not a cache.

    The set is rewritten by the 120s pass. Its TTL must exceed that period or the
    live picture lapses between healthy passes and the republisher goes quiet
    while games are on. It must NOT exceed it by much: if the main warm rail
    dies, this pass has to stop believing an hour-old liveness picture.
    """
    assert pcp.FEED_PREWARM_LIVE_SHAPES_TTL_S > 120
    assert pcp.FEED_PREWARM_LIVE_SHAPES_TTL_S <= 600


def test_the_live_set_reader_fails_to_empty_not_to_everything():
    """A Redis error must republish NOTHING, not every shape on the site.

    Direction of failure is the whole argument. Wrong-and-empty costs one 60s
    sawtooth — the pre-#2236 status quo. Wrong-and-full is a 40s beat rebuilding
    the entire feed surface off a transient error.
    """
    rc = MagicMock()
    rc.hgetall.side_effect = RuntimeError("redis down")
    assert pcp._live_prewarm_labels(rc) == set()


def test_a_marker_write_failure_never_breaks_the_warm():
    """The marker is an optimisation input; the warm is the product."""
    rc = MagicMock()
    rc.hset.side_effect = RuntimeError("redis down")
    rc.hdel.side_effect = RuntimeError("redis down")
    pcp._record_shape_liveness(rc, "sports", True)
    pcp._record_shape_liveness(rc, "sports", False)


# --- The pass itself ----------------------------------------------------------


def _run_live_pass(rc, warm_result=None):
    """Drive `_prewarm_live_feed_shapes` with `_prewarm_feed_shape` stubbed."""
    import asyncio

    warmed = []

    async def fake_warm(shape, _rc, *, deadline_s):
        warmed.append((shape["label"], deadline_s))
        return dict(warm_result or {"outcome": "ok", "items": 3, "live": True})

    with patch.object(pcp, "_prewarm_feed_shape", fake_warm), patch(
        "app.tasks.redis_state.get_redis_client", lambda: rc
    ):
        result = asyncio.run(pcp._prewarm_live_feed_shapes())
    return result, warmed


def test_an_empty_live_set_builds_nothing_but_still_reports():
    """The common case — off-hours this pass must be uninteresting, not invisible.

    One `HGETALL`, one `SETEX`, no build. That is what makes a 40s beat
    affordable beside a 120s pass measured at p50 9.8s / p95 14.2s; the cost
    scales with the number of shapes actually live, which is the only thing it
    should scale with.

    It still writes its report, because gotcha #53: "nothing was live" and "this
    beat has not run since the deploy" are different facts with opposite
    remedies, and an absent status key states both at once.
    """
    import json

    rc = _fake_rc()
    result, warmed = _run_live_pass(rc)
    assert result == "no_live_shapes"
    assert warmed == []

    written = {call.args[0]: call.args[2] for call in rc.setex.call_args_list}
    assert (
        pcp.FEED_LIVE_PREWARM_STATUS_KEY in written
    ), "an idle pass that writes nothing is indistinguishable from a dead beat"
    report = json.loads(written[pcp.FEED_LIVE_PREWARM_STATUS_KEY])
    assert report["live_labels"] == []
    assert report["shapes"] == {}


def test_only_the_shapes_recorded_live_are_rebuilt():
    rc = _fake_rc({"sports_native": "1", "sports": "1"})
    result, warmed = _run_live_pass(rc)
    assert {label for label, _ in warmed} == {"sports_native", "sports"}
    assert result == 2


def test_a_label_no_longer_in_the_shape_set_is_ignored():
    """A stale marker from a deleted shape must not crash or invent a target."""
    rc = _fake_rc({"sports_native": "1", "a_shape_that_was_deleted": "1"})
    _, warmed = _run_live_pass(rc)
    assert [label for label, _ in warmed] == ["sports_native"]


def test_bytes_keys_from_a_raw_redis_client_are_decoded():
    """`get_redis_client()` is not guaranteed to be decode_responses.

    A byte-string label silently matches no shape, so the pass would warm nothing
    and report `no_live_shapes` — indistinguishable from a quiet night, which is
    gotcha #53's shape exactly.
    """
    rc = _fake_rc({b"sports_native": b"1"})
    _, warmed = _run_live_pass(rc)
    assert [label for label, _ in warmed] == ["sports_native"]


def test_no_live_target_can_be_starved_by_the_ones_ahead_of_it():
    """Gotcha #34 again, on the new budget. Same arithmetic guarantee.

    The live pass reuses `_prewarm_target_deadline`, so every target's floor is
    BUDGET/N regardless of order — but it reuses it with a DIFFERENT budget, and
    a fair-share proof that holds for 80s does not automatically get executed for
    20s. It is executed here, in the two halves it takes.

    🔴 **The first draft of this test was green against a naive shared budget and
    the mutation battery is what caught it.** It asserted `deadline >= BUDGET/N`
    while driving the pass with an INSTANT fake warm, so `budget_left` never
    fell — and `deadline_s = budget_left` (the exact defect) hands every target
    the whole 20 s, which clears a floor of 4 s comfortably. A starvation test
    whose targets consume nothing cannot observe starvation. That is worth more
    than the assertion it fixes: a guard can be red-proof-shaped and still be
    testing nothing, and the only thing that showed it was mutating the code it
    claimed to protect.
    """
    n = len(pcp.FEED_PREWARM_SHAPES)
    floor = FEED_LIVE_REPUBLISH_BUDGET_S / n

    # --- half 1: the allocation the pass actually performs -------------------
    # With instant warms the remaining budget never falls, so fair share makes
    # the FIRST target's slice exactly BUDGET/N. A naive `deadline = budget_left`
    # hands it the whole budget instead, which is the shape being excluded.
    rc = _fake_rc({s["label"]: "1" for s in pcp.FEED_PREWARM_SHAPES})
    _, warmed = _run_live_pass(rc)
    assert len(warmed) == n
    assert warmed[0][1] == pytest.approx(floor), (
        f"first target got {warmed[0][1]}s of the {FEED_LIVE_REPUBLISH_BUDGET_S}s "
        f"budget, not its {floor}s fair share — the budget is not being divided"
    )
    for label, deadline_s in warmed:
        assert (
            deadline_s >= floor - 1e-9
        ), f"{label} was allotted {deadline_s}s, below the {floor}s floor"

    # --- half 2: the adversarial case, where every target eats its whole slice -
    # This is the scenario that starves a naive shared budget, simulated rather
    # than slept through. The floor must hold in every loop position.
    budget_left = float(FEED_LIVE_REPUBLISH_BUDGET_S)
    for index in range(n):
        deadline_s = pcp._prewarm_target_deadline(budget_left, n - index)
        assert deadline_s >= floor - 1e-9, (
            f"target {index} of {n} allotted {deadline_s}s, below the {floor}s "
            "floor, when every target ahead of it consumed its full allowance"
        )
        budget_left = max(0.0, budget_left - deadline_s)


def test_the_pass_budget_is_a_constant_not_a_product_of_the_target_count():
    """LAT-P100's lesson, inherited rather than re-learned.

    A per-item deadline multiplied by an item count is a budget that silently
    tightens every time someone adds an item, and it fails at the moment of the
    addition rather than the moment of the mistake. Here it would fail worse: the
    bound is not headroom, it is the second term of the #2236 invariant, so
    growing it past 20s breaks the ceiling arithmetic itself.
    """
    source = textwrap.dedent(inspect.getsource(pcp._prewarm_live_feed_shapes))
    assert "FEED_LIVE_REPUBLISH_BUDGET_S" in source
    assert "* len(" not in source


def test_the_live_pass_builds_through_the_shared_warmer():
    """One writer. A faster republisher that reimplemented the publish would have
    to re-derive the cache key, re-apply the live ceiling, and re-refuse degraded
    and empty payloads — the LAT-P001 two-writers-one-key defect with a new
    period attached.
    """
    source = textwrap.dedent(inspect.getsource(pcp._prewarm_live_feed_shapes))
    assert "_prewarm_feed_shape(" in source
    assert "setex(cache_key" not in source
    assert "feed_response_cache_ttls" not in source, (
        "the live pass must not compute TTLs of its own — that is the shared "
        "warmer's job and two copies of the ceiling is the #2216 defect"
    )


@pytest.mark.parametrize(
    "switch_attr",
    ["FEED_PREWARM_ENABLED_KEY", "FEED_LIVE_PREWARM_ENABLED_KEY"],
)
def test_both_kill_switches_stop_the_pass(switch_attr):
    """Its own switch, and the rail's.

    Separate because the two passes have different costs and different blast
    radii — turning the main warm off makes every first paint cold, turning this
    one off restores exactly the pre-#2236 sawtooth and nothing worse. It honours
    the rail's switch too, because "the warm rail is off" must mean the whole
    rail or the switch is a lie.
    """
    off_key = getattr(pcp, switch_attr)
    rc = _fake_rc({"sports_native": "1"})
    rc.get.side_effect = lambda key: "0" if key == off_key else None

    result, warmed = _run_live_pass(rc)
    assert result == "disabled"
    assert warmed == []


def test_the_pass_reports_which_shapes_it_republished():
    """`no_live_shapes` and "the beat never ran" must not read the same.

    Gotcha #53: an absence two different causes produce is not evidence. The
    status key is how production answers "is the sawtooth gone because this is
    working, or because nothing has been live all night?"
    """
    import json

    rc = _fake_rc({"sports_native": "1"})
    result, _ = _run_live_pass(rc)
    assert result == 1

    written = {call.args[0]: call.args[2] for call in rc.setex.call_args_list}
    assert pcp.FEED_LIVE_PREWARM_STATUS_KEY in written
    report = json.loads(written[pcp.FEED_LIVE_PREWARM_STATUS_KEY])
    assert report["live_labels"] == ["sports_native"]
    assert report["period_s"] == FEED_LIVE_REPUBLISH_PERIOD_S
    assert report["pass_budget_s"] == FEED_LIVE_REPUBLISH_BUDGET_S
    assert report["shapes"]["sports_native"]["outcome"] == "ok"


def test_a_failing_shape_does_not_stop_the_ones_behind_it():
    """Gotcha #42. `_prewarm_feed_shape` never raises, and the loop relies on it —
    so the reliance is pinned here rather than assumed.
    """
    rc = _fake_rc({"sports_native": "1", "sports": "1"})
    result, warmed = _run_live_pass(
        rc, warm_result={"outcome": "error", "error": "boom"}
    )
    assert len(warmed) == 2
    assert result == 0


def test_the_shared_warmer_reports_liveness_in_its_result():
    """The 120s pass's own report must say which shapes were live.

    Without it, `/api/admin` can see that a warm succeeded but not whether the
    payload it published was one that dies in 60s — which is the single fact
    #2236 turned on, and the one nobody could read at the time.
    """
    source = textwrap.dedent(inspect.getsource(pcp._prewarm_feed_shape))
    assert '"live": live' in source
    assert "_record_shape_liveness(rc, label, live)" in source
