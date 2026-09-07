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
import json
import textwrap
from importlib import import_module
from unittest.mock import MagicMock, patch

import pytest

from app.utils.feed_cache import (
    FEED_LIVE_REPUBLISH_BUDGET_S,
    FEED_LIVE_REPUBLISH_CONCURRENCY,
    FEED_LIVE_REPUBLISH_PERIOD_S,
    FEED_PREWARM_MIN_VIABLE_BUILD_S,
    FEED_RESPONSE_STALE_TTL_LIVE_SECONDS,
    FEED_RESPONSE_STALE_TTL_SECONDS,
    live_republish_headroom_s,
    live_republish_target_headroom_s,
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

    🔄 AMENDED by D68-next (#3060, L1B-050): `realtime` -> `heavy`. On 2026-09-05
    all four `realtime` co-tenants graded `overruns`
    (`GET /api/admin/celery/schedule-adherence`), single-flight caps them at ~4
    of 4 slots, and this beat completed 50 passes in 7.97 h — **7.0 % of its
    scheduled fires** — while `heavy`'s census depth read 0. `realtime` had
    become the exact lane #2236 was written to keep this task out of.

    🔄 AMENDED AGAIN by #3765 (LAT-P179, Fable D51): `heavy` -> `realtime`, and
    the two amendments together are the point of this docstring. On 2026-09-07 at
    03:47Z the same endpoint reported this beat at **0.30 deliveries per scheduled
    fire over a 25,137 s window, verdict `behind`** — `heavy` is concurrency 2 and
    both slots sit under `precompute_calibration_main` and
    `match_prediction_markets` for minutes at a time — while four of five
    `realtime` co-tenants graded `on_schedule` (0.97–0.99; only
    `poll_datagolf_inplay` still `overruns`) and `realtime`'s queue depth was 0.

    **NEITHER LANE RESERVES THIS BEAT A SLOT.** That is the durable finding, and
    it is why this test asserts a specific lane rather than a principle: the beat
    goes to whichever lane is currently measured idle, and the assertion is a pin
    on the last measurement, not a law. What is a law is the half asserted last —
    NOT `background` — which is unchanged across both moves and both readings.

    Both surfaces are asserted because beat `options` override `task_routes`; a
    disagreement makes the queue depend on whether the task was published by the
    beat or by hand. Since this task left `HEAVY_TASKS`, nothing else checks that
    pair for it — `test_heavy_beat_literals_match_their_effective_queue` iterates
    HEAVY_TASKS members — so this assertion IS the agreement guard now.
    """
    from app.tasks import HEAVY_TASKS, celery_app

    conf = celery_app.conf
    entry = conf.beat_schedule["prewarm-live-feed-shapes"]
    assert entry["options"]["queue"] == "realtime", entry["options"]
    assert conf.task_routes["app.tasks.prewarm_live_feed_shapes"] == {
        "queue": "realtime"
    }
    # Non-membership asserted directly, not left implicit. The loop under
    # HEAVY_TASKS OVERWRITES `task_routes` for every member, so a re-added member
    # line would silently win over the `realtime` route above and the beat literal
    # would be the only surface still saying `realtime` — the exact
    # two-surfaces-disagree arrangement the block comment forbids. Without this
    # line the `task_routes` assertion above would catch it, but only by accident
    # of ordering; this says what is actually required.
    assert "app.tasks.prewarm_live_feed_shapes" not in HEAVY_TASKS

    # And the surviving half of the original guard, unchanged: `background` is
    # still disqualified, and the fall-through hazard is still that deleting the
    # queue option IS choosing it, because it is the default.
    assert entry["options"]["queue"] != "background"
    assert conf.task_default_queue == "background"


# --- The live set: what the pass selects on ----------------------------------


class _FakePipe:
    """MULTI/EXEC: buffer client-side, apply on `execute`, apply nothing on failure.

    `_record_shape_liveness` writes only through this, so a test that wants to see
    what the writer did reads `rc._txns` — the queued commands, in order — rather
    than `rc.hset.call_args_list`. That is not bookkeeping: the whole CERT-1920
    repair is that the three commands are ONE round trip, and a fake that let them
    land individually would keep vouching for the writer that could not.
    """

    def __init__(self, rc):
        self._rc = rc
        self.queued = []

    def hset(self, key, field, value):
        self.queued.append(("hset", key, field, value))
        return self

    def hdel(self, key, field):
        self.queued.append(("hdel", key, field))
        return self

    def expire(self, key, seconds):
        self.queued.append(("expire", key, seconds))
        return self

    def execute(self):
        self._rc._txns.append(list(self.queued))
        if self._rc._exec_raises is not None:
            raise self._rc._exec_raises
        for op, key, *args in self.queued:
            if op == "hset":
                self._rc._state[args[0]] = args[1]
            elif op == "hdel":
                self._rc._state.pop(args[0], None)
            elif op == "expire":
                self._rc._ttl = args[0]


def _fake_rc(hash_state=None):
    """A MagicMock Redis with a real dict behind the live-shape hash."""
    state = dict(hash_state or {})
    rc = MagicMock()
    rc.hgetall.side_effect = lambda key: dict(state)
    rc.hset.side_effect = lambda key, field, value: state.__setitem__(field, value)
    rc.hdel.side_effect = lambda key, field: state.pop(field, None)
    rc.get.return_value = None
    rc._state = state
    rc._txns = []
    rc._ttl = None
    rc._exec_raises = None

    def _pipeline(transaction=False):
        assert transaction is True, (
            "the writer opened a non-transactional pipeline — the dead-man's "
            "heartbeat and its expiry can be applied apart again (CERT-1920)"
        )
        return _FakePipe(rc)

    rc.pipeline.side_effect = _pipeline
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
    assert rc._ttl == pcp.FEED_PREWARM_LIVE_SHAPES_TTL_S

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
    """The marker is an optimisation input; the warm is the product.

    Both failure points are exercised, because the writer now has two. Opening
    the pipeline can fail (no connection at all) and `execute` can fail (the round
    trip died). Only the second existed as a hazard before CERT-1920's repair
    moved the writes into a transaction, and a test that still injected at
    `rc.hset` would pass without touching either.
    """
    dead = MagicMock()
    dead.pipeline.side_effect = RuntimeError("redis down")
    pcp._record_shape_liveness(dead, "sports", True)
    pcp._record_shape_liveness(dead, "sports", False)

    for live in (True, False):
        mid_flight = _fake_rc()
        mid_flight._exec_raises = RuntimeError("connection reset before EXEC")
        pcp._record_shape_liveness(mid_flight, "sports", live)
        assert mid_flight._txns, "no transaction was attempted"
        assert mid_flight._state == {}, (
            "a failed transaction still landed a write — the heartbeat can be "
            "published without the expiry that bounds it (CERT-1920)"
        )
        assert mid_flight._ttl is None


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

    🔴 **#3233 REWROTE HALF 1, AND THE REASON IS THE POINT OF THIS WHOLE FILE.**
    Half 1 used to assert `warmed[0][1] == BUDGET/N` — that the first target got
    *exactly* its fair share and no more. That assertion was green in CI every day
    while production published nothing, because **`BUDGET/N` was the defect**: at
    N=5 the fair share is 4 s, one feed build costs more than that, and a
    perfectly fair division of a wall that is too small starts five builds and
    kills all five. The test was pinned to the mechanism instead of to the
    property, so it defended the bug.

    The property it should always have asserted is *no target is starved* — which
    now means: every target that is STARTED gets at least what a build costs, and
    a target that cannot get that is skipped rather than started and killed.

    Half 2 is unchanged and still valid: `_prewarm_target_deadline` is still the
    allocator for the 120 s host pass, and its fair-share proof is a real property
    of that helper, tested here where it was first written down.
    """
    n = len(pcp.FEED_PREWARM_SHAPES)
    floor = FEED_LIVE_REPUBLISH_BUDGET_S / n

    # --- half 1: no started target is under-funded, and none is silently lost --
    rc = _fake_rc({s["label"]: "1" for s in pcp.FEED_PREWARM_SHAPES})
    _, warmed = _run_live_pass(rc)
    assert len(warmed) == n, (
        f"{n - len(warmed)} of {n} live targets never started — a live shape "
        "dropped from a pass is a 60s cold window for whoever opens that tab"
    )
    for label, deadline_s in warmed:
        assert deadline_s >= FEED_PREWARM_MIN_VIABLE_BUILD_S, (
            f"{label} was started with {deadline_s}s, under the "
            f"{FEED_PREWARM_MIN_VIABLE_BUILD_S}s a build costs — a target that "
            "cannot finish must be SKIPPED, not started and killed (#3233)"
        )

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


# --- #3233: the wall has to cover the work, not just be divided fairly -------


def test_pass_budget_covers_every_target_at_the_declared_concurrency():
    """The invariant #3233 was the absence of, and the reason it is a test.

    #2236 compared a period against a ceiling. Nothing anywhere compared the wall
    against the COST OF THE WORK INSIDE IT, and that is the gap production fell
    through: five targets, a 20 s wall, a fair share of 4 s, and a feed build that
    costs more than 4 s. Every counter stayed green.

        ceil(N / CONCURRENCY) * MIN_VIABLE_BUILD_S <= BUDGET

    Named after the invariant and asserted over the DECLARED shape set, so a
    shape added past the pass's real capacity fails here — at the moment of the
    addition, which is the only moment anyone is looking.

    🔴 **The capacity is asserted by value, because it is not what the author of
    this test first assumed.** The #3233 writeup claimed a sixth shape would trip
    this guard; the arithmetic says the TENTH does
    (`CONCURRENCY * floor(BUDGET / MIN_VIABLE)` = 3 * 3 = 9 fit). Both statements
    cannot be acted on the same way, and only one of them had been evaluated. A
    guard whose trip point nobody has computed is a guard whose trip point could
    be anywhere, including past every case that will ever occur
    (`r_guard_value_set_below_the_defect_never_fires`, in the other direction).
    """
    n = len(pcp.FEED_PREWARM_SHAPES)
    headroom = live_republish_target_headroom_s(n)
    assert headroom >= 0, (
        f"{n} shapes at concurrency {FEED_LIVE_REPUBLISH_CONCURRENCY} need "
        f"{-headroom:.1f}s more than the {FEED_LIVE_REPUBLISH_BUDGET_S}s wall. The "
        "wall cannot be raised (PERIOD + BUDGET == the #2216 ceiling), so either "
        "the concurrency goes up or the shape does not go in."
    )

    # The trip point, evaluated rather than assumed. Derived from the declared
    # constants so changing any of them re-derives it instead of stranding a
    # literal, but ASSERTED as a boundary so the value is visible to a reader.
    capacity = FEED_LIVE_REPUBLISH_CONCURRENCY * int(
        FEED_LIVE_REPUBLISH_BUDGET_S // FEED_PREWARM_MIN_VIABLE_BUILD_S
    )
    assert live_republish_target_headroom_s(capacity) >= 0
    assert live_republish_target_headroom_s(capacity + 1) < 0, (
        f"the headroom function does not bite at {capacity + 1} targets, so it "
        "cannot detect a target count that provably cannot fit"
    )
    assert live_republish_target_headroom_s(0) == FEED_LIVE_REPUBLISH_BUDGET_S
    assert n <= capacity, (
        f"{n} declared shapes against a capacity of {capacity} — this should have "
        "been caught by the headroom assertion above"
    )


def test_a_build_gets_its_own_engine_so_the_pool_size_is_not_the_bound():
    """🔴 A correction to the reasoning this guard shipped with (#3233).

    The original assertion compared `FEED_LIVE_REPUBLISH_CONCURRENCY` against the
    `pool_size=3` regexed out of `tasks/base.py`, on the stated reasoning that
    three concurrent builds would "take overflow" from one shared pool. **They
    cannot**: `get_task_session()` calls `_get_task_engine()` on every entry, so
    each concurrent build brings its OWN engine, its own pool of three, and
    disposes it on exit. Three builds are three engines holding one connection
    each — never three checkouts of one pool.

    The number 3 is still safe. The reason it was safe was wrong, and a guard that
    passes for a mechanism that does not exist is the one that stays green while
    the real bound moves (`r_guard_pinned_to_a_mechanism_contracts_its_bug`). So
    the mechanism is asserted here, in the source, and the real bound —
    **connections in flight** — is measured at runtime in the test below.

    Asserted as structure rather than prose: the engine factory is called INSIDE
    the session context manager. If someone hoists it to a module-level singleton
    (a reasonable optimisation) the pooled bound becomes real again, this test
    fails, and whoever does it is pointed at the test below rather than
    discovering the interaction on production.
    """
    base = import_module("app.tasks.base")
    session_src = textwrap.dedent(inspect.getsource(base.get_task_session))
    assert "_get_task_engine()" in session_src, (
        "get_task_session no longer builds its own engine. If the engine is now "
        "shared, concurrent builds DO contend for one pool and "
        "FEED_LIVE_REPUBLISH_CONCURRENCY must be re-derived against pool_size + "
        "max_overflow — see the runtime guard below"
    )
    assert "engine.dispose()" in session_src, (
        "a per-call engine that is not disposed leaks its pool once per build, "
        "which at this concurrency is once per 40s beat (#1162)"
    )


def test_the_pass_never_holds_more_sessions_than_the_concurrency_it_declares():
    """The connection budget, measured at runtime instead of inferred (#3233).

    `FEED_LIVE_REPUBLISH_CONCURRENCY` is a semaphore bound in one function. What
    the database feels is **sessions open at once**, and nothing had ever compared
    the two — the shipped guard compared a constant against another constant read
    out of a third file. Between the semaphore and a connection sit the target
    list, `gather`, and the skip path, any of which could grow a second session
    per build or leak one past the `async with`.

    So this counts them: the real `_prewarm_feed_shape` runs, `get_task_session`
    is instrumented, and the peak is asserted. Because each session carries its
    own engine (test above), **peak sessions IS the connection count this beat
    adds to Postgres.** That sentence is the whole reason this test replaced a
    regex.

    Run at the DECLARED constants — no patched budget — so the assertion is about
    the configuration that ships.

    The saturation precondition is asserted first and is not a formality: with a
    build that returns instantly the peak is 1, the bound passes trivially, and the
    guard would be green against any concurrency whatsoever.
    """
    import asyncio
    from contextlib import asynccontextmanager

    from app.utils.feed_cache import FEED_PREWARM_KEY_SCOPE_KEY

    in_flight = 0
    peak = 0
    opened = 0

    @asynccontextmanager
    async def _counting_session():
        nonlocal in_flight, peak, opened
        in_flight += 1
        opened += 1
        peak = max(peak, in_flight)
        try:
            yield MagicMock()
        finally:
            in_flight -= 1

    async def _fake_get_feed(**kwargs):
        # The route is what resolves and records the cache key; stand in for it so
        # the build reaches the publish path instead of bailing at `no_key`, and
        # hold the session open long enough for the waves to actually overlap.
        kwargs["request"].scope[FEED_PREWARM_KEY_SCOPE_KEY] = (
            f"bainluck:feed:{kwargs.get('mode') or 'discover'}:{kwargs['limit']}"
        )
        await asyncio.sleep(0.02)
        return {"build_quality": "complete", "items": [{"id": 1}, {"id": 2}]}

    rc = _fake_rc({s["label"]: "1" for s in pcp.FEED_PREWARM_SHAPES})
    with patch("app.tasks.base.get_task_session", _counting_session), patch(
        "app.routes.feed.get_feed", _fake_get_feed
    ), patch("app.tasks.redis_state.get_redis_client", lambda: rc):
        published = asyncio.run(pcp._prewarm_live_feed_shapes())

    n = len(pcp.FEED_PREWARM_SHAPES)
    assert published == n, f"only {published} of {n} targets published"
    assert opened == n, (
        f"{opened} sessions were opened for {n} builds — a build that takes two "
        "sessions doubles this beat's connection cost invisibly"
    )
    # PRECONDITION: the waves really overlapped, so the bound below is being tested.
    assert peak == FEED_LIVE_REPUBLISH_CONCURRENCY, (
        f"peak was {peak}, not the declared concurrency "
        f"{FEED_LIVE_REPUBLISH_CONCURRENCY}. Below it the builds never overlapped "
        "and this assertion proves nothing; above it the semaphore is not bounding "
        "the pass at all"
    )
    assert in_flight == 0, (
        f"{in_flight} session(s) still open after the pass returned — each one is a "
        "leaked engine and its pool (#1162)"
    )


def _run_live_pass_with_costed_builds(
    rc, *, build_cost_s, budget_s, min_viable_s, concurrency
):
    """Drive the pass with builds that actually CONSUME time and can time out.

    The scale is 1/100th of production so the test is fast, and the ratio is what
    matters: a build that costs more than a fair share of the wall. The fake
    reproduces `asyncio.wait_for`'s contract faithfully — a build given less than
    it costs burns its whole deadline and publishes NOTHING, which is the exact
    production behaviour (`{"outcome": "timeout"}`, "the request path will rebuild
    cold").
    """
    import asyncio

    started_order = []

    async def costed_warm(shape, _rc, *, deadline_s):
        started_order.append(shape["label"])
        if deadline_s < build_cost_s:
            await asyncio.sleep(deadline_s)
            return {"outcome": "timeout"}
        await asyncio.sleep(build_cost_s)
        return {"outcome": "ok", "items": 3, "live": True}

    with patch.object(pcp, "_prewarm_feed_shape", costed_warm), patch(
        "app.tasks.redis_state.get_redis_client", lambda: rc
    ), patch.object(
        import_module("app.utils.feed_cache"),
        "FEED_LIVE_REPUBLISH_BUDGET_S",
        budget_s,
    ), patch.object(
        import_module("app.utils.feed_cache"),
        "FEED_PREWARM_MIN_VIABLE_BUILD_S",
        min_viable_s,
    ), patch.object(
        import_module("app.utils.feed_cache"),
        "FEED_LIVE_REPUBLISH_CONCURRENCY",
        concurrency,
    ):
        result = asyncio.run(pcp._prewarm_live_feed_shapes())
    return result, started_order


def test_a_slow_build_no_longer_starves_the_whole_pass():
    """The production defect of #3233, executed.

    Every shape live, and every build costing more than `BUDGET / N`. That is not
    a hypothetical: it is what production did 1,322 times a day, with 290
    `Feed pre-warm TIMEOUT`s in 24 h and nothing published.

    Serially, with each target given its fair `BUDGET / N`, **every** build is
    killed and the pass publishes ZERO. Run in waves of `CONCURRENCY` under the
    same wall, the same builds fit. The assertion is on the count published,
    because that is the only number a reader of the Sports tab can feel.
    """
    n = len(pcp.FEED_PREWARM_SHAPES)
    budget_s = 0.20
    # More than a fair share (0.04s at n=5), comfortably less than a wave's worth
    # of the wall. This is the whole shape of the bug in one inequality.
    build_cost_s = 0.06
    assert build_cost_s > budget_s / n, "the fixture does not reproduce the defect"

    rc = _fake_rc({s["label"]: "1" for s in pcp.FEED_PREWARM_SHAPES})
    published, started = _run_live_pass_with_costed_builds(
        rc,
        build_cost_s=build_cost_s,
        budget_s=budget_s,
        min_viable_s=build_cost_s,
        concurrency=FEED_LIVE_REPUBLISH_CONCURRENCY,
    )

    assert len(started) == n, "a live target was never even started"
    assert published >= FEED_LIVE_REPUBLISH_CONCURRENCY, (
        f"only {published} of {n} targets published. Serial 1/N slicing publishes "
        "0 here — that is the bug — so anything at or below the first wave means "
        "the pass is still dividing the wall instead of running waves in it"
    )


def _live_prewarm_report(rc):
    """The status payload a READER sees, parsed back off the `setex` that wrote it.

    Deliberately not the return value. `_prewarm_live_feed_shapes` returns a COUNT,
    and a count cannot answer "which shapes" — the question every assertion about
    waves has to ask. The status key is also the only thing an operator can read on
    production, so a guard that reads it is grading the same artifact they are.
    """
    calls = [
        c
        for c in rc.setex.call_args_list
        if c.args and c.args[0] == pcp.FEED_LIVE_PREWARM_STATUS_KEY
    ]
    assert calls, "the pass wrote no status payload at all"
    return json.loads(calls[-1].args[2])


def _sports_tab_labels():
    """Every warmed shape that a reader of the Sports tab waits on.

    Derived from the declared shapes, not listed here. Three today — `sports`
    (web), `sports_native`, and `sports_native_events` (the native tab's
    events-only backfill, whose `mode` is None because the route's
    Discover-default guard skips it; see `FEED_PREWARM_SHAPES`). A fourth added
    tomorrow is covered without touching this file, which is the point:
    `r_guards_are_named_after_the_invariant_not_the_feature`.
    """
    return [
        s["label"] for s in pcp.FEED_PREWARM_SHAPES if s["label"].startswith("sports")
    ]


def test_a_target_in_a_later_wave_publishes_like_one_in_the_first():
    """The half of #3233 its own first guard did not cover.

    `test_a_slow_build_no_longer_starves_the_whole_pass` asserts
    `published >= CONCURRENCY` — satisfied by wave 1 ALONE. A regression that
    published the first three targets and dropped everything behind them would
    leave that assertion green, and the shapes it would drop are the ones the
    commit subject is about: at `CONCURRENCY = 3` over the declared shape order,
    wave 1 is `discover, sports, discover_native` and **wave 2 is
    `sports_native, sports_native_events` — the native Sports tab, entire.**

    So the fix's headline ("the Sports tab stops paying") rested on a wave nothing
    asserted. Raised by the review of the shipped change
    (`CERT-1905-SECOND-WAVE-AND-CONNECTION-BUDGET-GUARD`).

    The wave boundary is DERIVED — everything at or past index `CONCURRENCY` in
    the target list cannot run in the first wave, whatever the order becomes — and
    the precondition that a later wave exists at all is asserted before the
    assertion that needs it, because a guard over an empty list is not a guard
    (`r_fake_collapsing_two_hashes_makes_a_vacuous_guard`).
    """
    n = len(pcp.FEED_PREWARM_SHAPES)
    budget_s = 0.20
    build_cost_s = 0.06
    assert build_cost_s > budget_s / n, "the fixture does not reproduce the defect"

    rc = _fake_rc({s["label"]: "1" for s in pcp.FEED_PREWARM_SHAPES})
    _published, started = _run_live_pass_with_costed_builds(
        rc,
        build_cost_s=build_cost_s,
        budget_s=budget_s,
        min_viable_s=build_cost_s,
        concurrency=FEED_LIVE_REPUBLISH_CONCURRENCY,
    )
    report = _live_prewarm_report(rc)
    shapes = report["shapes"]

    # Wave membership comes from the targets the pass INTENDED to serve, not from
    # the ones it managed to start. The first draft read `started`, and under the
    # pre-repair mutation — where every target is skipped before the build is
    # called — `started` is empty, so the precondition below tripped and reported
    # "the shape set has shrunk" about a pass that was failing exactly as designed.
    # A guard must not describe its own subject's failure as its own irrelevance.
    target_order = [
        s["label"] for s in pcp.FEED_PREWARM_SHAPES if s["label"] in rc._state
    ]
    assert set(started) <= set(target_order), (started, target_order)

    # PRECONDITION 1: there IS a wave past the first. Without this the test is
    # green on a shape set that never exercises the thing it is named after.
    later_wave = target_order[FEED_LIVE_REPUBLISH_CONCURRENCY:]
    assert later_wave, (
        f"{n} shapes at concurrency {FEED_LIVE_REPUBLISH_CONCURRENCY} all fit in "
        "one wave, so this guard is asserting nothing. It must be re-pointed (or "
        "the shape set has shrunk below the case #3233 was about)"
    )

    # PRECONDITION 2: the Sports tab really is behind that boundary. This is the
    # clause the review asked for, and it is the reason the wave matters at all.
    sports = _sports_tab_labels()
    assert len(sports) >= 2, f"expected the Sports tab to warm several shapes, got {sports}"
    assert set(sports) & set(later_wave), (
        f"no Sports shape sits in a later wave ({sports} vs wave-2 {later_wave}) — "
        "the ordering has changed and this guard no longer covers the case the "
        "commit subject claims"
    )

    for label in later_wave:
        wave = 1 + target_order.index(label) // FEED_LIVE_REPUBLISH_CONCURRENCY
        assert shapes.get(label, {}).get("outcome") == "ok", (
            f"{label} is in wave {wave} and did not publish: {shapes.get(label)}. A "
            "pass that serves only its first wave is the #3233 defect with a larger "
            "constant"
        )

    for label in sports:
        assert shapes.get(label, {}).get("outcome") == "ok", (
            f"the Sports tab shape {label} did not publish: {shapes.get(label)}. "
            "This is the shape a reader of /sports waits on"
        )


def _fake_rc_two_hashes(live_labels, absent_labels):
    """A fake Redis that can actually produce ABSENT targets.

    🔴 `_fake_rc` cannot, and the first draft of the ordering test below was
    VACUOUS because of it. Its `hgetall` returns the same dict for every key, so
    the live-marker hash and the shape-KEY hash are one object: the only labels
    with a remembered cache key are exactly the live ones, and
    `_absent_prewarm_labels` excludes those. `absent_labels` came back empty, the
    ordering assertion sat behind `if absent_positions:`, and the test passed
    while ordering absent-before-live — which is the mutation it exists to catch.

    Two hashes, kept apart, plus an `exists` that answers per key. The general
    clause: **a fake that collapses two identities into one cannot observe a bug
    that lives in the difference between them**, and the tell is a guard that
    stays green under the mutation it names.
    """
    live_state = {label: "1" for label in live_labels}
    # Every shape has a remembered key; only the absent ones have lost the mirror.
    key_state = {s["label"]: f"feed:{s['label']}" for s in pcp.FEED_PREWARM_SHAPES}
    gone = {f"feed:{label}:stale" for label in absent_labels}

    rc = MagicMock()

    def _hgetall(key):
        if key == pcp.FEED_PREWARM_SHAPE_KEYS_KEY:
            return dict(key_state)
        return dict(live_state)

    rc.hgetall.side_effect = _hgetall
    rc.hset.side_effect = lambda key, field, value: (
        key_state if key == pcp.FEED_PREWARM_SHAPE_KEYS_KEY else live_state
    ).__setitem__(field, value)
    rc.hdel.side_effect = lambda key, field: (
        key_state if key == pcp.FEED_PREWARM_SHAPE_KEYS_KEY else live_state
    ).pop(field, None)
    rc.exists.side_effect = lambda key: 0 if key in gone else 1
    rc.get.return_value = None
    return rc


def test_the_absent_fixture_really_produces_absent_targets():
    """The ordering guard below is only as good as this, so it is asserted first.

    A precondition that is merely assumed is how the first draft of that guard
    came to pass while ordering absent labels ahead of live ones.
    """
    rc = _fake_rc_two_hashes({"sports"}, {"discover", "discover_native"})
    assert pcp._live_prewarm_labels(rc) == {"sports"}
    assert pcp._absent_prewarm_labels(rc, exclude={"sports"}) == {
        "discover",
        "discover_native",
    }


def test_live_labels_are_started_before_absent_labels():
    """LAT-P112's priority rule has to survive the concurrency (#3233).

    "The net never competes with the invariant": a shape whose mirror has gone is
    a `background`-queue incident this pass covers for, while a LIVE shape is the
    #2216 ceiling itself. Serially the ordering was the loop order. Concurrently
    it is `gather` creating tasks in list order plus `asyncio.Semaphore` handing
    the lock to its waiters FIFO — which is a real guarantee, but one nobody
    should have to re-derive from the standard library to trust a warm rail.

    Driven at concurrency 1 on purpose: the ordering rule is about which target
    gets the wall FIRST, and running one at a time is the only arrangement in
    which "first" is observable rather than a race.
    """
    live = {"sports", "sports_native"}
    absent = {"discover", "discover_native"}
    rc = _fake_rc_two_hashes(live, absent)

    _, started = _run_live_pass_with_costed_builds(
        rc,
        build_cost_s=0.02,
        budget_s=0.40,
        min_viable_s=0.02,
        concurrency=1,
    )

    assert set(started) >= live, f"a live label was not republished: {started}"
    absent_positions = [index for index, label in enumerate(started) if label in absent]
    assert absent_positions, (
        "no absent target was scheduled, so this test proves nothing about "
        "ordering — the fixture, not the code, is what failed"
    )
    last_live = max(started.index(label) for label in live)
    assert last_live < min(absent_positions), (
        f"an absent label started before a live one ({started}) — the safety "
        "net is competing with the #2236 ceiling it is supposed to sit behind"
    )


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


# --- CERT-1914: the live set's dead-man's switch must be readable -------------


def test_no_shape_label_can_collide_with_the_heartbeat_field():
    """The heartbeat shares the live-set hash, so its name must be unusable as a label.

    A shape called `__host_warm_at` would be silently dropped from `live_labels`
    by the exclusion this repair adds, and would never be republished. Asserted
    over the declared shape sets rather than over a literal, so enrolling a new
    shape re-runs the check.
    """
    from app.tasks.precompute_category_pages import (
        FEED_PREWARM_LIVE_HEARTBEAT_FIELD,
        FEED_PREWARM_SHAPES,
        GROUPED_FEED_PREWARM_SHAPES,
    )

    labels = {s["label"] for s in FEED_PREWARM_SHAPES}
    labels |= {s["label"] for s in GROUPED_FEED_PREWARM_SHAPES}
    assert labels, "no shapes were read — this guard would pass vacuously"
    assert FEED_PREWARM_LIVE_HEARTBEAT_FIELD not in labels


def test_the_heartbeat_is_written_on_every_successful_warm_live_or_not():
    """Both directions, because the quiet one is the direction that was broken.

    A live warm keeping the key alive was never in doubt — it writes a label. The
    failure was the NOT-live warm, whose only write was an `hdel`, and which
    therefore deleted the very key a reader consults to decide whether warms are
    happening at all.
    """
    from app.tasks.precompute_category_pages import (
        FEED_PREWARM_LIVE_HEARTBEAT_FIELD,
        FEED_PREWARM_LIVE_SHAPES_KEY,
        FEED_PREWARM_LIVE_SHAPES_TTL_S,
        _record_shape_liveness,
    )

    for live in (True, False):
        rc = _fake_rc()
        _record_shape_liveness(rc, "sports", live=live)
        assert len(rc._txns) == 1, "the write was not a single transaction"
        queued = rc._txns[0]
        written = {
            field
            for op, key, field, *_ in queued
            if op == "hset" and key == FEED_PREWARM_LIVE_SHAPES_KEY
        }
        assert FEED_PREWARM_LIVE_HEARTBEAT_FIELD in written, (
            f"no heartbeat written on a live={live} warm — the dead-man's switch "
            "cannot tell a quiet rail from a dead one"
        )
        assert (
            "expire",
            FEED_PREWARM_LIVE_SHAPES_KEY,
            FEED_PREWARM_LIVE_SHAPES_TTL_S,
        ) in queued, (
            "the expiry is not in the same transaction as the heartbeat, so a "
            "failed round trip can publish a heartbeat that never expires"
        )


def test_the_heartbeat_is_written_before_the_label_is_cleared():
    """Order is the guarantee, not an accident of how it reads.

    If the `hdel` ran first, clearing the last live label would delete the hash
    and a concurrent reader would see the switch fired on a healthy rail — the
    same wrong answer, in a smaller window. Writing the heartbeat first means the
    hash always holds a field and `hdel` can never empty it.
    """
    from app.tasks.precompute_category_pages import (
        FEED_PREWARM_LIVE_HEARTBEAT_FIELD,
        _record_shape_liveness,
    )

    rc = _fake_rc()
    _record_shape_liveness(rc, "sports", live=False)

    order = [(op, field) for op, _key, field, *_ in rc._txns[0] if op != "expire"]
    assert ("hdel", "sports") in order, "the label was never cleared"
    assert order.index(("hset", FEED_PREWARM_LIVE_HEARTBEAT_FIELD)) < order.index(
        ("hdel", "sports")
    ), "the heartbeat is queued after the hdel, so the expiry binds to no key"


def test_the_heartbeat_is_not_selected_as_a_live_shape():
    """`_live_prewarm_labels` must exclude it, or the rail reports a phantom."""
    from app.tasks.precompute_category_pages import (
        FEED_PREWARM_LIVE_HEARTBEAT_FIELD,
        _live_prewarm_labels,
    )

    rc = MagicMock()
    rc.hgetall.return_value = {
        b"sports": b"1",
        FEED_PREWARM_LIVE_HEARTBEAT_FIELD.encode(): b"1788624114",
    }
    assert _live_prewarm_labels(rc) == {"sports"}
