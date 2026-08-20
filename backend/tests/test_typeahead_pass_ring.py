"""Guards for the typeahead warmer's pass ring and its read-only admin surface.

LAT-P074 (#1866, #1609, #1996).

**What this file is defending, and it is not the arithmetic.** The arithmetic in
`app/utils/typeahead_pass_ring.py` is trivial: sort, index, count. What is not
trivial — and what this program has been bitten by four separate times — is that
an instrument must never let "I could not check" render as "there is nothing to
report". Every test below that looks pedantic is that failure, pinned:

* `test_an_unreadable_redis_is_not_no_data` — gotcha #53's exact shape.
* `test_a_firing_warmer_that_skips_every_beat_is_not_no_data` — the diagnosis a
  bare empty ring cannot make, and the state production is closest to.
* `test_the_record_is_written_on_the_skip_path_too` — a skip that writes nothing
  is a skip that is indistinguishable from a warmer that never fired.
* `test_recording_never_breaks_a_pass` — an instrument that can break its own
  subject is worse than no instrument. The warmer is explicitly NOT load-bearing
  and this must not be the thing that changes that.

And the TTL derivation's guards are here rather than in the beat-budget file
because they are about the same measurement: the pass-only wall this ring exists
to make readable.
"""

from __future__ import annotations

import json

import pytest

from app.utils.typeahead_beat_budget import (
    PASS_ONLY_WALL_MAX_S,
    PASS_ONLY_WALL_MEDIAN_S,
    PASS_ONLY_WALL_MIN_S,
    RESPONSE_CACHE_TTL_S,
    SAFETY_MARGIN_S,
    BeatVerdict,
    TtlVerdict,
    derive_response_ttl_s,
    grade_beat_interval,
)
from app.utils.typeahead_pass_ring import (
    STATUS_NO_DATA,
    STATUS_OK,
    STATUS_UNREADABLE,
    decode_records,
    decode_state,
    summarise,
    unreadable,
)


def _pass(at, wall, period, expired=0, terminal="complete"):
    return {
        "at": at,
        "terminal": terminal,
        "skip_reason": None,
        "seconds_wall": wall,
        "period_s": period,
        "expired": expired,
        "rebuilt": 40,
        "fresh": 0,
        "warmed": 40,
        "total": 40,
        "concurrency": 4,
        "head_source": "redis:search:trending:24h",
        "timeouts": 0,
        "errors": 0,
    }


# ---------------------------------------------------------------------------
# The three states, which are three and not two
# ---------------------------------------------------------------------------


def test_an_unreadable_redis_is_not_no_data():
    """Gotcha #53 / ruling 075 clause 2, at the point of WRITING.

    A read that could not happen and a read that found nothing are opposite
    findings, and every instrument in this repo that has lied to us has lied by
    collapsing them. `unreadable` must be reachable, distinct, and must not
    report a single measured zero.
    """
    payload = unreadable("boom", now=1000.0, ring_max=32, ttl_s=45)

    assert payload["status"] == STATUS_UNREADABLE
    assert payload["status"] != STATUS_NO_DATA
    assert payload["passes"]["n"] is None, "an unmeasured count must not read as 0"
    assert payload["skips"]["total"] is None
    assert payload["passes"]["expired"]["total"] is None
    assert payload["reason"] == "boom"


def test_an_empty_ring_on_a_healthy_redis_is_no_data():
    payload = summarise([], decode_state({}), now=1000.0, ring_max=32, ttl_s=45)

    assert payload["status"] == STATUS_NO_DATA
    # Counted zeros, not absent ones — Redis DID answer.
    assert payload["passes"]["n"] == 0
    assert payload["skips"]["total"] == 0


def test_a_firing_warmer_that_skips_every_beat_is_not_no_data():
    """`passes.n == 0` with `skips.total > 0` is the single most useful state here.

    A warmer wedged behind its own lock and a warmer that has never run produce
    the same empty ring. They are opposite diagnoses — one needs the lock
    cleared, the other needs the beat investigated — so the skip counters exist
    precisely to separate them, and this asserts they do.
    """
    state = decode_state({"skips:lock": "17", "skips:min_period": "3"})
    payload = summarise([], state, now=1000.0, ring_max=32, ttl_s=45)

    assert payload["status"] == STATUS_OK, "skips ARE data; this is not an absence"
    assert payload["passes"]["n"] == 0
    assert payload["skips"]["total"] == 20
    assert payload["skips"]["by_reason"] == {"lock": 17, "min_period": 3}


# ---------------------------------------------------------------------------
# The distribution — the thing `last_result_summary` structurally cannot give
# ---------------------------------------------------------------------------


def test_the_pass_distribution_is_computed_over_passes_only():
    """A no-op in the ring must never drag the wall percentiles down.

    This is the exact defect in the number LAT-P073 reached for: `warm_typeahead`'s
    p95 duration of 44.6 s was a percentile over a MIXED distribution of real
    passes and ~10 ms no-ops. Skips are counted, never ringed — but if one ever
    reaches the ring, it must not enter the arithmetic.
    """
    records = [
        _pass(100.0, 40.0, 50.0),
        _pass(200.0, 50.0, 60.0),
        {"at": 250.0, "terminal": "skipped", "skip_reason": "lock",
         "seconds_wall": 0.0, "period_s": None, "expired": 0},
    ]
    payload = summarise(records, decode_state({}), now=300.0, ring_max=32, ttl_s=45)

    assert payload["passes"]["n"] == 2
    assert payload["passes"]["seconds_wall"]["min"] == 40.0
    assert payload["passes"]["seconds_wall"]["max"] == 50.0
    assert payload["passes"]["seconds_wall"]["n"] == 2, (
        "the 0.0s skip must be outside the wall distribution entirely"
    )


def test_walls_over_the_response_ttl_are_counted_not_left_to_the_reader():
    records = [_pass(100.0, 40.0, 50.0), _pass(200.0, 53.9, 60.0), _pass(300.0, 46.9, 55.0)]
    payload = summarise(records, decode_state({}), now=400.0, ring_max=32, ttl_s=45)

    assert payload["passes"]["walls_over_response_ttl"] == 2
    assert payload["response_cache_ttl_s"] == 45, (
        "the threshold travels WITH the measurement; a reader must not have to "
        "re-derive it from another file"
    )


def test_expired_is_reported_per_pass_because_that_is_the_registered_halt():
    """`expired` is cache-entry LOSS — the publish gate's halt and #1866's cost.

    Reported as `passes_with_loss` / `worst` / `total` rather than a mean,
    because loss here is a step function: LAT-P063 measured 20 passes for 20 that
    a period over the TTL loses entries and one under it loses none. A mean over
    a step function describes no pass that ever happened.
    """
    records = [_pass(1.0, 40.0, 49.9, expired=1), _pass(2.0, 47.8, 275.9, expired=40)]
    payload = summarise(records, decode_state({}), now=10.0, ring_max=32, ttl_s=45)

    assert payload["passes"]["expired"]["passes_with_loss"] == 2
    assert payload["passes"]["expired"]["worst"] == 40
    assert payload["passes"]["expired"]["total"] == 41
    assert payload["passes"]["expired"]["measured_over_passes"] == 2


def test_a_percentile_is_nearest_rank_so_it_names_a_real_pass():
    """An interpolated p95 reports a wall no pass ever had.

    When the question is "did a pass cross the 45 s TTL", inventing a value
    between two real ones is the wrong kind of answer.
    """
    records = [_pass(float(i), float(30 + i), 50.0) for i in range(10)]
    payload = summarise(records, decode_state({}), now=100.0, ring_max=32, ttl_s=45)

    walls = {float(30 + i) for i in range(10)}
    assert payload["passes"]["seconds_wall"]["p50"] in walls
    assert payload["passes"]["seconds_wall"]["p95"] in walls


def test_an_empty_distribution_carries_the_same_keys_as_a_full_one():
    """The same contract `typeahead_warmer._no_work` carries, for the same reason.

    A consumer must never have to branch on `n` to learn whether a field exists.
    """
    full = summarise([_pass(1.0, 40.0, 50.0)], decode_state({}),
                     now=10.0, ring_max=32, ttl_s=45)
    empty = summarise([], decode_state({}), now=10.0, ring_max=32, ttl_s=45)

    assert set(full["passes"]["seconds_wall"]) == set(empty["passes"]["seconds_wall"])
    assert empty["passes"]["seconds_wall"]["p50"] is None, "unmeasured, not zero"


# ---------------------------------------------------------------------------
# Decoding — a reader that drops real data reports a false absence
# ---------------------------------------------------------------------------


def test_records_decode_from_bytes_and_from_str():
    raw = [json.dumps(_pass(1.0, 40.0, 50.0)).encode(), json.dumps(_pass(2.0, 41.0, 51.0))]
    assert len(decode_records(raw)) == 2, (
        "a client configured for bytes and one configured for str must not "
        "produce 'the warmer has not run' about a warmer that has"
    )


def test_unparseable_entries_are_dropped_not_guessed_at():
    raw = [b"not json", json.dumps(_pass(1.0, 40.0, 50.0)), b"[1,2,3]"]
    decoded = decode_records(raw)
    assert len(decoded) == 1
    assert decoded[0]["seconds_wall"] == 40.0


def test_an_unanticipated_skip_reason_still_lands_somewhere_countable():
    """A fixed schema would drop a reason nobody predicted — silently.

    `skips:<reason>` fields mean a new skip reason appears in the payload the
    first time it fires, instead of being absorbed into a total that no longer
    adds up.
    """
    state = decode_state({b"skips:some_new_reason": b"4"})
    assert state["skips"] == {"some_new_reason": 4}
    assert state["skips_total"] == 4


# ---------------------------------------------------------------------------
# The warmer's own write path
# ---------------------------------------------------------------------------


def test_the_ring_record_projects_timeouts_and_errors_to_counts():
    """Their presence changes how a wall reads; their contents do not.

    A 32-deep ring of full summaries carrying query strings is larger and harder
    to read than the numbers that answer the question.
    """
    from app.tasks.typeahead_warmer import _pass_ring_record

    record = _pass_ring_record(
        {"terminal": "partial", "seconds_wall": 53.92, "period_s": 294.663,
         "expired": 40, "timeouts": ["red sox", "world cup"], "errors": []},
        at=1000.0,
    )
    assert record["timeouts"] == 2
    assert record["errors"] == 0
    assert record["seconds_wall"] == 53.92
    assert "q" not in json.dumps(record), "no query strings in the ring"


def test_recording_never_breaks_a_pass():
    """An instrument must not be able to break the thing it measures.

    The warmer's contract is that it is NOT load-bearing — a cold miss still
    builds inline in the route. A `_record_outcome` that can raise would quietly
    convert that into a load-bearing task.
    """
    import app.tasks.redis_state as redis_state
    from app.tasks.typeahead_warmer import _record_outcome

    def _boom():
        raise RuntimeError("redis is gone")

    original = redis_state.get_redis_client
    redis_state.get_redis_client = _boom
    try:
        _record_outcome({"terminal": "complete", "seconds_wall": 40.0}, now=1.0)
    finally:
        redis_state.get_redis_client = original


def test_the_record_is_written_on_the_skip_path_too():
    """A skip that writes nothing is indistinguishable from a beat that never fired.

    Asserted on the SOURCE of `_warm_typeahead`, because the alternative is a
    live Redis, and the thing being guarded is that a future edit does not remove
    the call from the `_no_work` branch while leaving it on the pass branch —
    which is precisely how `skip_reason` got added to only one shape once before.
    """
    import inspect

    from app.tasks import typeahead_warmer

    src = inspect.getsource(typeahead_warmer._warm_typeahead)
    assert src.count("_record_outcome(") == 2, (
        "both the skip path and the pass path must record; found "
        f"{src.count('_record_outcome(')} call(s)"
    )


def test_skips_are_counted_and_passes_are_ringed():
    """Two thirds of executions are no-ops (measured). Ringing them would flush
    the pass history out of a 32-deep list inside twenty minutes."""
    import inspect

    from app.tasks import typeahead_warmer

    src = inspect.getsource(typeahead_warmer._record_outcome)
    assert "hincrby" in src.lower()
    assert "lpush" in src.lower()
    assert "ltrim" in src.lower(), "the ring is bounded on every write, not by TTL"


# ---------------------------------------------------------------------------
# The TTL derivation — LAT-P074 item 3, ruling 075
# ---------------------------------------------------------------------------


def test_the_derived_ttl_is_the_quantised_period_floor_plus_a_stated_margin():
    """The number, with both floors named in the same record (ruling 075 (2)).

    Fable ruled `TTL >= measured worst pass wall + margin`. That prices the
    wall; what an entry has to survive is the PERIOD, which is the wall
    quantised up to the next beat fire. Both are reported so the departure is
    visible rather than substituted.
    """
    d = derive_response_ttl_s(measured_period_s=45.0)

    assert d.measured_wall_floor_s == PASS_ONLY_WALL_MAX_S
    assert d.margin_s == SAFETY_MARGIN_S, (
        "the margin is the module's OWN existing SAFE/MARGINAL constant, not a "
        "number invented after seeing the answer"
    )
    assert d.quantised_period_floor_s == 60.0, "10s beat, 53.920s worst wall -> 60s"
    assert d.derived_ttl_s == 65.0
    assert d.wall_plus_margin_ttl_s == 59.0, "Fable's literal reading, carried"
    assert d.derived_ttl_s > d.wall_plus_margin_ttl_s


def test_a_derivation_with_no_measured_wall_refuses_rather_than_defaulting():
    """Ruling 075: where the history cannot support a derivation, refuse loudly.

    A default number here would be a TTL nobody measured, shipped into a cliff
    whose whole property is that it is a step function.
    """
    d = derive_response_ttl_s(worst_pass_wall_s=0)

    assert d.verdict == TtlVerdict.REFUSED
    assert d.derived_ttl_s is None
    assert d.prediction_holds is False


def test_an_ungraded_prediction_is_not_a_met_one():
    """No period supplied -> `PREDICTION_UNGRADED`, never `SUFFICIENT`.

    Ruling 075's second clause in its sharpest form: the derivation may not
    report that loss goes to zero on the strength of a quantity it never read.
    """
    d = derive_response_ttl_s()

    assert d.verdict == TtlVerdict.PREDICTION_UNGRADED
    assert d.verdict != TtlVerdict.INSUFFICIENT_FOR_PREDICTION
    assert d.prediction_holds is False
    assert d.derived_ttl_s == 65.0, "the NUMBER is still derived; only the claim is not"
    assert d.loss_free_ttl_s is None


def test_the_wall_derived_ttl_does_not_meet_its_prediction_at_the_measured_period():
    """🔴 THE FINDING. The wall is not the floor this prediction turns on.

    An entry is rebuilt once per PASS, so it must survive from one rebuild to the
    next — that gap is the pass PERIOD. Production measured periods of 236.9 s,
    275.9 s and 294.7 s on 2026-08-20 (`expired: 40/40` on all three) alongside
    one at 49.9 s (`expired: 1`). A 60 s TTL therefore satisfies Fable's
    inequality and still loses every entry on a stalled pass.

    The derivation must SAY so rather than return the number quietly.
    """
    d = derive_response_ttl_s(measured_period_s=275.923)

    assert d.verdict == TtlVerdict.INSUFFICIENT_FOR_PREDICTION
    assert d.prediction_holds is False
    assert d.derived_ttl_s == 65.0
    assert d.loss_free_ttl_s == 281.0, "275.923 + 5.0, rounded up"
    assert "does NOT go to zero" in d.reason
    assert "the defect is the period, not the TTL" in d.reason


def test_the_prediction_holds_in_the_healthy_period_regime():
    """The same derivation, at the period the warmer reaches when it is not stalled."""
    d = derive_response_ttl_s(measured_period_s=49.897)

    assert d.verdict == TtlVerdict.SUFFICIENT
    assert d.prediction_holds is True
    assert d.derived_ttl_s == 65.0
    assert d.max_staleness_s == 65.0, (
        "the staleness cost Fable asked to have bounded and named: an entry may "
        "be up to one TTL old"
    )


def test_the_pass_only_measurement_graded_the_live_beat_unsafe_at_the_old_ttl():
    """🔴 THE HALT, NOW DISCHARGED — kept as the record of what forced the swap.

    ⚠️ **REWRITTEN, LAT-P075**, exactly as the queue warned it would have to be.
    This test used to call `grade_beat_interval` with the module DEFAULTS and
    assert UNSAFE: `MEASURED_WALL_*` still held LAT-P063's mixed 32.0/29.4/42.6,
    the pass-only triple sat beside it unused, and substituting the 40.991 s
    median flipped the live 10 s beat to UNSAFE against the **45 s** TTL —
    P(10) = 10 * ceil(40.991/10) = 50 s, over the cliff on a TYPICAL pass.

    Both halves of that sentence have now moved: `MEASURED_WALL_*` **is** the
    pass-only triple, and the TTL **is** 65. So the assertion is pinned to the
    old TTL explicitly rather than to the defaults, because what it records is a
    historical fact about 45 s — that the live beat was unsafe there — and that
    fact is the entire reason 45 s is gone. Written against the defaults it would
    now silently assert something else.
    """
    grade = grade_beat_interval(
        10.0,
        wall_median_s=PASS_ONLY_WALL_MEDIAN_S,
        wall_max_s=PASS_ONLY_WALL_MAX_S,
        wall_min_s=PASS_ONLY_WALL_MIN_S,
        ttl_s=45,
    )

    assert grade.verdict == BeatVerdict.UNSAFE
    assert grade.crosses_cliff_on_median is True
    assert grade.period_at_median_s == 50.0
    assert grade.is_shippable is False


def test_the_swapped_defaults_now_grade_the_live_beat_safe():
    """And the same call on the DEFAULTS is what shipping the TTL bought.

    With `MEASURED_WALL_*` swapped to the pass-only triple and the TTL at 65, the
    grader's default answer for the live 10 s beat is SAFE for the first time in
    this program's history. This is the positive half of the halt's discharge,
    and it is asserted through the defaults deliberately — if either constant
    drifts back, this goes red without anyone having to remember why.
    """
    grade = grade_beat_interval(10.0)

    assert grade.verdict == BeatVerdict.SAFE
    assert grade.period_at_worst_s == 60.0
    assert grade.is_shippable is True


def test_the_ring_wall_grades_the_ratified_ttl_marginal():
    """🔴 DISCLOSURE: the ratified TTL's own input moved before it shipped.

    65 s was derived from `PASS_ONLY_WALL_MAX_S = 53.920` (n=17) and ratified on
    that basis — Fable's GO ruling 4 calls it "the first value the live beat has
    ever graded SAFE". LAT-P075 then took the FIRST production read of the pass
    ring that shipped on `program/latency-67`, and the worst wall came back at
    **61.282 s** over 26 passes: +7.36 s.

    At that number the same grader returns **MARGINAL, not SAFE** — P(10) =
    10 * ceil(61.282/10) = 70 s, over 65 — and the TTL that would return SAFE is
    75 s.

    **65 ships anyway and this test does not object to it.** Ruling 4 closes TTL
    derivation and forecloses precisely this move: a TTL raised to survive the
    regressed period is a decision to serve stale data instead of fixing the
    regression. The repair shipped in the same commit is the `expires` bound.

    So what this test IS: the third instance of one specific failure, made
    unmissable. A maximum drawn from a finite sample is a LOWER BOUND, and this
    program has now read one as a bound and been wrong at 42.6 (by 11.3 s) and
    again at 53.920 (by 7.36 s). It goes red if anyone edits `RING_WALL_MAX_S`
    down to make the margin look better, or quietly re-derives the TTL upward to
    reach SAFE — the two ways this disclosure could be made to disappear.
    """
    from app.utils.typeahead_beat_budget import (
        RESPONSE_CACHE_TTL_S,
        RING_WALL_MAX_S,
        RING_WALL_MEDIAN_S,
        RING_WALL_MIN_S,
    )

    assert RING_WALL_MAX_S > PASS_ONLY_WALL_MAX_S, (
        "the ring read is the disclosure; if it no longer exceeds the ratified "
        "input there is nothing to disclose and this test should be deleted"
    )

    at_ratified = grade_beat_interval(
        10.0,
        wall_median_s=RING_WALL_MEDIAN_S,
        wall_max_s=RING_WALL_MAX_S,
        wall_min_s=RING_WALL_MIN_S,
        ttl_s=RESPONSE_CACHE_TTL_S,
    )
    assert at_ratified.verdict == BeatVerdict.MARGINAL
    assert at_ratified.period_at_worst_s == 70.0
    assert at_ratified.is_shippable is False

    # The number that WOULD be safe here, stated so nobody has to recompute it
    # to know the size of the gap — and deliberately not shipped.
    at_75 = grade_beat_interval(
        10.0,
        wall_median_s=RING_WALL_MEDIAN_S,
        wall_max_s=RING_WALL_MAX_S,
        wall_min_s=RING_WALL_MIN_S,
        ttl_s=75,
    )
    assert at_75.verdict == BeatVerdict.SAFE


def test_the_ttl_that_returns_the_live_beat_to_safe():
    """And the number that undoes it — the other half of the halt.

    At 65 s the live 10 s beat grades SAFE on the pass-only measurement — the
    first time in this program's history that it has. P(10) = 60 s at the worst
    wall, clearing 65 s by exactly `SAFETY_MARGIN_S`.

    And the two nearby values do NOT, which is why 65 rather than 60: at 60 s
    the period equals the TTL and the grader returns MARGINAL with zero
    headroom, the "coincidence of arithmetic" that constant exists to refuse.
    """
    safe = grade_beat_interval(
        10.0,
        wall_median_s=PASS_ONLY_WALL_MEDIAN_S,
        wall_max_s=PASS_ONLY_WALL_MAX_S,
        wall_min_s=PASS_ONLY_WALL_MIN_S,
        ttl_s=65,
    )
    assert safe.verdict == BeatVerdict.SAFE
    assert safe.period_at_worst_s == 60.0
    assert safe.is_shippable is True

    for ttl in (59, 60):
        near = grade_beat_interval(
            10.0,
            wall_median_s=PASS_ONLY_WALL_MEDIAN_S,
            wall_max_s=PASS_ONLY_WALL_MAX_S,
            wall_min_s=PASS_ONLY_WALL_MIN_S,
            ttl_s=ttl,
        )
        assert near.verdict != BeatVerdict.SAFE, (
            f"a {ttl}s TTL leaves no headroom over a 60s quantised period"
        )


def test_the_current_ttl_is_still_the_live_one():
    """The TTL that is actually live, pinned so it cannot drift unremarked.

    ⚠️ **45 -> 65, LAT-P075.** This test previously asserted 45 and read "Fable
    ruled a HALT on the TTL: bring the number, do not ship it." **The halt is
    discharged** — Fable ratified 65 on 2026-08-19 (GO ruling 4), so the number
    shipped and this assertion moved with it.

    It keeps its job in the new position: 65 is now the ruled value, and a change
    away from it without a fresh ruling should turn this red. In particular it
    goes red on the move ruling 4 explicitly forecloses — raising the TTL again
    to survive the period regression (553 s zeroes the loss, and is a decision to
    serve stale data rather than fix the regression).
    """
    assert RESPONSE_CACHE_TTL_S == 65


# ---------------------------------------------------------------------------
# The endpoint is mounted, and is not `/celery-debug`'s shape
# ---------------------------------------------------------------------------


def test_the_endpoint_is_actually_mounted():
    """Gotcha #2. A handler that is written but not reachable is not shipped.

    Asserted against the live app route table rather than against an
    `include_router` line, because the failure this catches is exactly the case
    where the line looks right and the path is still absent.
    """
    from app.main import app

    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/api/admin/typeahead-warmer/last" in paths


def test_the_endpoint_takes_no_celery_broadcast():
    """#1994: four blocking celery broadcasts inline in an `async def` black-holed
    the entire production API for ten minutes. This surface is pure Redis.

    Named rather than assumed, because "it is only a read-only debug route" is
    the sentence that preceded the outage.
    """
    import inspect

    from app.routes import admin_celery

    src = inspect.getsource(admin_celery.typeahead_warmer_last)
    body = src.split('"""', 2)[-1]  # the docstring NAMES both; the body must not call them
    assert "control.inspect" not in body
    assert "_inspect_snapshot" not in body
    # 🔴 The CALL, not the import. This assertion read `"run_in_threadpool" in
    # body` on its first pass and a mutation that deleted the `await` while
    # leaving the import line SURVIVED it — the substring was still there and
    # the endpoint was blocking the event loop. Reported in the LAT-P074 report
    # rather than quietly tightened; the tightening is here.
    assert "await run_in_threadpool(_read)" in body, (
        "the bounded Redis client still blocks for up to 5s (gotcha #39), and "
        "5s of a blocked event loop under a refreshing dashboard tab is #1994 "
        "at a smaller scale. An import of run_in_threadpool is not a use of it"
    )


def test_the_endpoint_requires_the_admin_secret():
    import inspect

    from app.routes import admin_celery

    src = inspect.getsource(admin_celery.typeahead_warmer_last)
    assert "_check_admin_secret" in src


def test_the_lrange_bound_is_not_caller_supplied():
    """An endpoint whose cost a caller can raise is one a caller can use to hurt
    the instance — #1807's lesson, one size down."""
    import inspect

    from app.routes import admin_celery

    sig = inspect.signature(admin_celery.typeahead_warmer_last)
    assert set(sig.parameters) == {"request", "secret"}, (
        f"no cost-bearing query parameters; got {sorted(sig.parameters)}"
    )


@pytest.mark.parametrize("status", [STATUS_OK, STATUS_NO_DATA, STATUS_UNREADABLE])
def test_every_status_is_reachable_and_distinct(status):
    """Three states, and each one has to be produceable. A status constant that
    no code path can emit is documentation, not an instrument."""
    produced = {
        STATUS_OK: summarise([_pass(1.0, 40.0, 50.0)], decode_state({}),
                             now=10.0, ring_max=32, ttl_s=45)["status"],
        STATUS_NO_DATA: summarise([], decode_state({}),
                                  now=10.0, ring_max=32, ttl_s=45)["status"],
        STATUS_UNREADABLE: unreadable("x", now=10.0, ring_max=32, ttl_s=45)["status"],
    }
    assert produced[status] == status


# ---------------------------------------------------------------------------
# The handler end to end, over a stubbed Redis
#
# The tests above prove the parts: the reduction, the decode, the mounting, the
# absence of a broadcast. None of them prove the WIRING — that the handler reads
# the keys the warmer writes, passes the real TTL through, and turns a raising
# client into `unreadable` rather than a 500. A suite that tests every part and
# no assembly is how a correctly-implemented endpoint ships reading the wrong key.
# ---------------------------------------------------------------------------


class _StubPipeline:
    def __init__(self, ring, state, boom=False):
        self._ring, self._state, self._boom = ring, state, boom
        self.calls = []

    def lrange(self, key, start, end):
        self.calls.append(("lrange", key, start, end))
        return self

    def hgetall(self, key):
        self.calls.append(("hgetall", key))
        return self

    def execute(self):
        if self._boom:
            raise RuntimeError("redis is gone")
        return [self._ring, self._state]


class _StubRedis:
    def __init__(self, ring, state, boom=False):
        self.pipe = _StubPipeline(ring, state, boom)

    def pipeline(self):
        return self.pipe


def _call_endpoint(ring, state, boom=False):
    import asyncio

    import app.tasks.redis_state as redis_state
    from app.routes import admin_celery
    from app.routes import admin_utils

    stub = _StubRedis(ring, state, boom)
    orig_client = redis_state.get_redis_client
    orig_check = admin_utils._check_admin_secret
    redis_state.get_redis_client = lambda *a, **k: stub
    admin_celery._check_admin_secret = lambda *a, **k: None
    try:
        return asyncio.run(admin_celery.typeahead_warmer_last(request=None, secret="x")), stub
    finally:
        redis_state.get_redis_client = orig_client
        admin_celery._check_admin_secret = orig_check


def test_the_handler_reads_the_keys_the_warmer_actually_writes():
    """The assembly test. A handler reading the wrong key returns a clean
    `no_data` about a warmer that is working perfectly."""
    from app.tasks.typeahead_warmer import _PASS_RING_KEY, _WARMER_STATE_KEY

    payload, stub = _call_endpoint([json.dumps(_pass(1.0, 47.776, 275.923, expired=40))], {})

    reads = {c[1] for c in stub.pipe.calls}
    assert reads == {_PASS_RING_KEY, _WARMER_STATE_KEY}
    assert payload["status"] == STATUS_OK
    assert payload["passes"]["n"] == 1
    assert payload["passes"]["seconds_wall"]["max"] == 47.776
    assert payload["passes"]["expired"]["worst"] == 40


def test_the_handler_passes_the_real_response_ttl_through():
    """The threshold has to travel with the measurement, and it has to be the
    LIVE one — a payload carrying a hardcoded 45 would keep reading correct
    right up until the day the TTL is ruled to 65, and then be silently wrong.

    🔴 The value assertion below is a TAUTOLOGY while the constant equals 45,
    and a mutation replacing `RESPONSE_CACHE_TTL_S` with the literal `45`
    SURVIVED it on the first pass. Reported in the LAT-P074 report rather than
    quietly tightened (doctrine clause 16, banked this window and paying out
    inside it for the second time). The source assertion is the tightening: it
    bites today, and the value assertion becomes real the moment the TTL moves.
    """
    import inspect

    from app.routes import admin_celery

    body = inspect.getsource(admin_celery.typeahead_warmer_last).split('"""', 2)[-1]
    # COUNT, not `in`. The handler has TWO call sites that take the TTL — the
    # `summarise` path and the `unreadable` path — and a substring check is
    # satisfied by either one surviving. The mutation that hardcoded `45` in the
    # `summarise` call survived a bare `in` twice, for exactly that reason.
    assert body.count("ttl_s=RESPONSE_CACHE_TTL_S") == 2, (
        "BOTH the ok path and the unreadable path must pass the live constant, "
        "not a literal that happens to equal it today"
    )

    payload, _ = _call_endpoint([json.dumps(_pass(1.0, 47.776, 50.0))], {})
    assert payload["response_cache_ttl_s"] == RESPONSE_CACHE_TTL_S


def test_a_raising_redis_returns_unreadable_not_a_500_and_not_a_zero():
    payload, _ = _call_endpoint([], {}, boom=True)

    assert payload["status"] == STATUS_UNREADABLE
    assert payload["passes"]["n"] is None
    assert "redis is gone" in payload["reason"]


def test_the_handler_reports_a_firing_but_skipping_warmer():
    payload, _ = _call_endpoint([], {"skips:lock": "9"})

    assert payload["status"] == STATUS_OK
    assert payload["passes"]["n"] == 0
    assert payload["skips"]["by_reason"] == {"lock": 9}
