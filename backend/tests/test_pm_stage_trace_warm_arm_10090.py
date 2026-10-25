"""#10090: the PM stage trace can arm inside a warm worker, not on its restart.

The production specimen sat about 9.5 minutes into a warm session; the trace
started collecting at once and expired 600 s after the config restart. With
WS_PM_TRACE_ARM_AT the trace is built as before but stays silent and stateless
until the arm instant, then follows one exact changed input through the same
stages, inside a window still capped at 600 s and 256 lines. The real game
flush, chunk writer and refresher run on the existing `trace_rig` fakes.
"""

import pytest

from app.tasks import live_blend_refresh as blend
from app.utils.pm_stage_trace import PMStageTrace
from tests.test_pm_stage_trace_10090 import WALL, flush, outcome, stage, trace_rig

ARM = WALL + 540.0  # wall clock at arm; the rig's monotonic clock starts at 500
ARM_MONO = 500.0 + 540.0


def warm_env(arm=ARM, expires=ARM + 300, lines="256"):
    return {
        "WS_PM_TRACE_EVENT": "1",
        "WS_PM_TRACE_OUTCOMES": "1",
        "WS_PM_TRACE_ARM_AT": str(arm),
        "WS_PM_TRACE_EXPIRES_AT": str(expires),
        "WS_PM_TRACE_MAX_LINES": lines,
    }


def held_state(trace):
    return {
        "accepted": dict(trace.accepted), "waiting": dict(trace.waiting),
        "last_value": dict(trace.last_value), "commits": dict(trace.commits),
        "stamps": dict(trace.stamps), "pinned": dict(trace.pinned),
        "joined": dict(trace.joined), "written": set(trace.written),
        "flush": trace.flush, "chunk": trace.chunk, "attempt": trace.attempt,
        "seqs": (trace.flush_seq, trace.chunk_seq, trace.attempt_seq),
    }


EMPTY = {
    "accepted": {}, "waiting": {}, "last_value": {}, "commits": {}, "stamps": {},
    "pinned": {}, "joined": {}, "written": set(), "flush": None, "chunk": None,
    "attempt": None, "seqs": (0, 0, 0),
}


@pytest.mark.asyncio
async def test_before_arming_only_start_is_written_and_nothing_is_held(monkeypatch):
    baseline = await outcome(trace_rig(monkeypatch, env={}))
    t = trace_rig(monkeypatch, env=warm_env())
    # The rig accepted both outcomes; a whole flush, write and stamp ran.
    assert await outcome(t) == baseline
    t.accept(1, 0.55, 5)  # a CHANGE before arming opens nothing
    assert await flush(t, started=t.clock[0])
    t.clock[0] = ARM_MONO - 0.001
    t.accept(1, 0.5, 6)
    assert await flush(t, started=t.clock[0])
    (start,) = t.lines
    assert start["stage"] == "START" and start["collection"] == "WAITING_FOR_ARM"
    assert start["arm_at"] == ARM and start["expires_at"] == ARM + 300
    assert start["mapping"] == {"1": "MAPPED"}
    assert held_state(t.trace) == EMPTY
    assert t.trace.arm_mono == ARM_MONO


@pytest.mark.asyncio
async def test_after_arming_one_exact_changed_input_runs_through_every_stage(monkeypatch):
    t = trace_rig(monkeypatch, env=warm_env())
    assert await flush(t, started=500.0)  # the warm worker's earlier traffic
    assert [line["stage"] for line in t.lines] == ["START"]
    t.clock[0] = ARM_MONO + 0.25
    changed = t.accept(1, 0.55, 7)
    t.reading[0] = 0.85  # the new price moves the blend
    assert await flush(t, started=t.clock[0])

    stages = [line["stage"] for line in t.lines]
    assert stages[:3] == ["START", "ARMED", "ACCEPTED"], stages
    armed = t.lines[1]
    assert armed["armed_mono"] == ARM_MONO + 0.25 and armed["arm_mono"] == ARM_MONO
    assert armed["late_by_s"] == 0.25 and armed["window_left_s"] == 299.75
    assert armed["mapping"] == {"1": "MAPPED"}

    (accepted,) = stage(t.lines, "ACCEPTED")
    assert accepted["input_seq"] == changed.seq and accepted["probability"] == 0.55
    # The trace saw nothing before arming, so it does not claim a run start.
    assert accepted["first_since_armed"] is True and "first_of_run" not in accepted
    (chunk,) = stage(t.lines, "CHUNK")
    assert chunk["result"] == "COMMITTED" and chunk["written"] == [[1, changed.seq, 0.55]]
    (committed,) = stage(t.lines, "PRICE_COMMITTED")
    assert committed["input_seq"] == committed["carries_changed_seq"] == changed.seq
    assert committed["superseded_unwritten"] == committed["committed_unstamped"] == []
    (event,) = stage(t.lines, "EVENT_COMMITTED")
    assert event["input_seq"] == changed.seq
    (attempt,) = stage(t.lines, "ATTEMPT")
    assert attempt["attempt"] == event["attempt"] and attempt["joined"] is True
    # No identity from before arming appears anywhere.
    seqs = {line.get("input_seq") for line in t.lines} - {None}
    assert seqs == {changed.seq}
    assert not t.trace.waiting


@pytest.mark.asyncio
async def test_a_run_starting_inside_the_window_arms_at_once_and_delivery_is_unchanged(
    monkeypatch,
):
    baseline = await outcome(trace_rig(monkeypatch, env={}))
    # A recycle 100 s into the window: ARM_AT is past, expiry still ahead.
    t = trace_rig(monkeypatch, env=warm_env(arm=WALL - 100, expires=WALL + 200))
    assert await outcome(t) == baseline
    start, armed = t.lines[:2]
    assert start["collection"] == "WAITING_FOR_ARM" and armed["stage"] == "ARMED"
    assert armed["late_by_s"] == 100.0 and armed["window_left_s"] == 200.0
    assert stage(t.lines, "EVENT_COMMITTED")


@pytest.mark.asyncio
async def test_window_budget_and_a_wall_clock_rollback_cannot_extend_tracing(monkeypatch):
    now = [WALL]
    t = trace_rig(monkeypatch, env=warm_env(), wall=lambda: now[0])
    now[0] = WALL - 10_000  # wall clock goes BACK; arm and expiry are monotonic
    t.clock[0] = ARM_MONO
    t.accept(1, 0.55, 7)
    assert [line["stage"] for line in t.lines] == ["START", "ARMED", "ACCEPTED"]
    t.clock[0] = ARM_MONO + 300  # the configured window has elapsed
    t.accept(1, 0.5, 8)
    assert t.lines[-1]["stage"] == "STOP" and t.lines[-1]["reason"] == "EXPIRED"
    assert held_state(t.trace) == EMPTY and not t.trace.active()

    # Arm instant passes with no entry point; the next call is after expiry.
    late = trace_rig(monkeypatch, env=warm_env())
    late.clock[0] = ARM_MONO + 300
    late.accept(1, 0.55, 7)
    assert [line["stage"] for line in late.lines] == ["START", "STOP"]
    assert late.lines[1]["reason"] == "EXPIRED_BEFORE_ARMED"
    assert held_state(late.trace) == EMPTY

    budget = trace_rig(monkeypatch, env=warm_env(lines="4"))
    budget.clock[0] = ARM_MONO
    for seq, value in enumerate((0.55, 0.5, 0.45, 0.4), 7):
        budget.accept(1, value, seq)
    assert await flush(budget, started=budget.clock[0])
    assert [line["stage"] for line in budget.lines] == [
        "START", "ARMED", "ACCEPTED", "STOP",
    ]
    assert budget.lines[-1]["reason"] == "BUDGET_STOP"
    assert held_state(budget.trace) == EMPTY


def make(env, event_of=None, mono=None):
    lines = []
    base = {"WS_PM_TRACE_EVENT": "7", "WS_PM_TRACE_OUTCOMES": "70"}
    base.update(env)
    clock = mono or [1.0]
    trace = PMStageTrace.from_env(
        base, run="r", event_of=event_of if event_of is not None else {70: 7},
        wall=lambda: WALL, mono=lambda: clock[0], emit=lines.append,
    )
    return trace, lines


@pytest.mark.parametrize("arm, expires", [
    ("", WALL + 300),
    ("soon", WALL + 300),
    ("nan", WALL + 300),
    ("inf", WALL + 300),
    ("-inf", WALL + 300),
    ("1" * 33, WALL + 300),
    (str(WALL + 1801), WALL + 1900),  # waits longer than 1800 s
    (str(WALL + 100), WALL + 701),  # window longer than 600 s
    (str(WALL + 300), WALL + 300),  # empty window
    (str(WALL + 300), WALL + 200),  # expiry before arm
    (str(WALL - 700), WALL - 100),  # whole window already past
])
def test_malformed_or_unbounded_arm_controls_disable_the_trace(arm, expires):
    trace, lines = make({"WS_PM_TRACE_ARM_AT": arm, "WS_PM_TRACE_EXPIRES_AT": str(expires)})
    assert trace is None and lines == []


def test_the_bounds_allow_a_warm_window_and_leave_the_default_unchanged():
    # 25 minutes out, 600 s long: refused without ARM_AT, accepted with it.
    far = {"WS_PM_TRACE_EXPIRES_AT": str(WALL + 2100)}
    assert make(far)[0] is None
    trace, lines = make({**far, "WS_PM_TRACE_ARM_AT": str(WALL + 1500)})
    assert trace is not None and trace.arm_mono == 1.0 + 1500
    assert trace.deadline - trace.arm_mono == 600
    # Default START: same fields as before, and collection starts at once.
    trace, lines = make({"WS_PM_TRACE_EXPIRES_AT": str(WALL + 300)})
    assert set(lines[0]) - {"run", "receive_wall", "receive_mono", "emitted_wall",
                            "emitted_mono"} == {
        "stage", "event", "outcomes", "mapping", "expires_at", "max_lines",
        "accept_clock",
    }
    assert trace.arm_mono is None and trace.active()
    trace.input_accepted(blend.InputMark(
        seq=1, event_id=7, outcome_id=70, probability=0.5, kind="price",
        recv_wall=WALL, recv_mono=1.0, venue_ts_ms=None, event_ordinal=1,
    ))
    assert lines[-1]["stage"] == "ACCEPTED" and lines[-1]["first_of_run"] is True
    assert "first_since_armed" not in lines[-1]


def test_mapping_is_validated_at_start_and_re_read_when_armed():
    event_of = {70: 7}
    clock = [1.0]
    env = {"WS_PM_TRACE_ARM_AT": str(WALL + 60), "WS_PM_TRACE_EXPIRES_AT": str(WALL + 120)}
    trace, lines = make(env, event_of, clock)
    event_of[70] = 8  # the run's map changed before arming
    clock[0] = 61.0
    assert not trace.active()
    assert [line["stage"] for line in lines] == ["START", "ARMED", "STOP"]
    assert lines[1]["mapping"] == {"70": "OTHER_EVENT"}
    assert lines[2]["reason"] == "NO_MAPPED_OUTCOME"

    # Unmapped at START stays out even if the map gains it before arming.
    event_of, clock = {70: 7}, [1.0]
    trace, lines = make({**env, "WS_PM_TRACE_OUTCOMES": "70,71"}, event_of, clock)
    event_of[71] = 7
    clock[0] = 61.0
    assert trace.active() and trace.targets == frozenset({70})
    assert lines[1]["mapping"] == {"70": "MAPPED"}

    # No mapped outcome at START still stops at once, never waiting to arm.
    trace, lines = make(env, {70: 8})
    assert [line["stage"] for line in lines] == ["START", "STOP"]
    assert trace.arm_mono is None and not trace.active()


def test_a_fence_by_an_attempt_older_than_arming_is_not_called_unstarted():
    clock = [1.0]
    env = {"WS_PM_TRACE_ARM_AT": str(WALL + 60), "WS_PM_TRACE_EXPIRES_AT": str(WALL + 120)}
    trace, lines = make(env, {70: 7}, clock)
    trace.attempt_start([7], 1.0)  # before arming: not seen
    clock[0] = 61.0
    mark = blend.InputMark(
        seq=3, event_id=7, outcome_id=70, probability=0.5, kind="price",
        recv_wall=WALL, recv_mono=61.0, venue_ts_ms=None, event_ordinal=3,
    )
    trace.input_accepted(mark)
    trace.flush_begin(61.0, False, {70: mark}, {70: 0.5})
    token = trace.chunk_begin(0, [70])
    trace.fence(token, {7: object()}, {7})
    (fenced,) = stage(lines, "FENCED")
    assert fenced["held_attempt"] == "UNTRACKED_MAY_PREDATE_ARMED"
    # Once an attempt is seen after arming, the default label returns.
    trace.attempt_start([7], 61.5)
    trace.attempt_released([7])
    assert trace.untracked_attempt == "QUEUED_NOT_STARTED"
