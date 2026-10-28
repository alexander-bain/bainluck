"""#10090 R1: the PM stage trace arms a fold's member events in one setting.

PILLARS: TRUTH / FORMATTING. SHIP: the acceptance case can be scored on an
ordinary held page, including one whose two rows for one game are folded and
whose PM origin is the OTHER member.

`WS_PM_TRACE_EVENT` used to take one event, so a fold whose PM-elected origin
was the other member's row was uncovered. These pin:

* 1-4 event ids, 1-8 outcomes mapped to any of them, one window, ONE shared
  line budget; one event keeps its four-outcome cap and its exact lines
  (pinned byte-for-byte in the R1 return against 422be4cb's own tests);
* every per-event line names its event: attempts, open chains, admission,
  fences and stamps are held per member, so one member's stamp never closes
  the other's chain;
* the other member's PREVIEW / SELECTED are written once it has a retained
  commit, exactly as the one traced event's were;
* the warm arm re-reads every member's mapping at ARMED.
"""

from types import SimpleNamespace

import pytest

from app.tasks import live_blend_refresh as blend
from app.utils.pm_stage_trace import PMStageTrace
from tests.test_pm_stage_trace_10090 import STORED, WALL, flush, stage, trace_rig

EVENT_OF = {70: 7, 71: 7, 80: 8, 81: 8, 90: 9}


def make(lines=None, mono=None, **env):
    base = {
        "WS_PM_TRACE_EVENT": "7,8", "WS_PM_TRACE_OUTCOMES": "70,80",
        "WS_PM_TRACE_EXPIRES_AT": str(WALL + 300), "WS_PM_TRACE_MAX_LINES": "256",
    }
    base.update(env)
    lines = [] if lines is None else lines
    trace = PMStageTrace.from_env(
        base, run="r", event_of=dict(EVENT_OF), wall=lambda: WALL,
        mono=mono or (lambda: 1.0), emit=lines.append,
    )
    return trace, lines


def mark(trace, seq, oid, value):
    m = blend.InputMark(
        seq=seq, event_id=EVENT_OF[oid], outcome_id=oid, probability=value, kind="price",
        recv_wall=WALL, recv_mono=1.0, venue_ts_ms=None, event_ordinal=seq,
    )
    trace.input_accepted(m)
    return m


def write(trace, marks):
    chunk = {m.outcome_id: m.probability for m in marks}
    by_oid = {m.outcome_id: m for m in marks}
    trace.flush_begin(1.0, False, by_oid, chunk)
    token = trace.chunk_begin(0, sorted(chunk))
    trace.chunk_write(token, chunk, by_oid)
    trace.write_stage(chunk, "COMMITTED",
                      rows=[SimpleNamespace(id=oid, last_updated=STORED) for oid in chunk])
    trace.chunk_end(token, True)
    return token


def test_one_setting_arms_up_to_four_members_with_their_mapping_named():
    trace, lines = make(WS_PM_TRACE_OUTCOMES="70,80,90,99")
    (start,) = lines
    assert start["events"] == [7, 8] and "event" not in start
    assert start["mapping"] == {"70": "MAPPED", "80": "MAPPED", "90": "OTHER_EVENT",
                                "99": "UNMAPPED"}
    assert start["outcome_event"] == {"70": 7, "80": 8}
    assert start["events_without_outcome"] == []
    assert trace.targets == frozenset({70, 80}) and trace.event is None
    # A member armed with no mapped outcome is named, not read as covered.
    _, lines = make(WS_PM_TRACE_EVENT="7,8,9", WS_PM_TRACE_OUTCOMES="70,80")
    assert lines[0]["events_without_outcome"] == [9]
    # Bounds: at most four events; a fold may name eight outcomes, one event four.
    assert make(WS_PM_TRACE_EVENT="7,8,9,10")[0] is not None
    assert make(WS_PM_TRACE_EVENT="7,8,9,10,11")[0] is None
    assert make(WS_PM_TRACE_OUTCOMES="70,71,80,81,90,91,92,93")[0] is not None
    assert make(WS_PM_TRACE_OUTCOMES="70,71,80,81,90,91,92,93,94")[0] is None
    assert make(WS_PM_TRACE_EVENT="7", WS_PM_TRACE_OUTCOMES="70,71,72,73,74")[0] is None
    assert make(WS_PM_TRACE_EVENT="7,x")[0] is None
    assert make(WS_PM_TRACE_EVENT="7,,8")[0] is None
    assert make(WS_PM_TRACE_EVENT="7," * 30 + "8")[0] is None
    # One event: the single-event START, unchanged.
    trace, lines = make(WS_PM_TRACE_EVENT="7", WS_PM_TRACE_OUTCOMES="70,80")
    assert lines[0]["event"] == 7 and "events" not in lines[0]
    assert "outcome_event" not in lines[0] and lines[0]["mapping"]["80"] == "OTHER_EVENT"
    # No outcome mapped to any member: stopped, as before.
    trace, lines = make(WS_PM_TRACE_OUTCOMES="90")
    assert [line["stage"] for line in lines] == ["START", "STOP"]
    assert lines[1]["reason"] == "NO_MAPPED_OUTCOME"


def test_each_member_keeps_its_own_attempt_chain_and_stamp():
    trace, lines = make()
    a, b = mark(trace, 1, 70, 0.4), mark(trace, 2, 80, 0.6)
    assert {line["event"] for line in stage(lines, "ACCEPTED")} == {7, 8}
    write(trace, [a, b])
    (chunk,) = stage(lines, "CHUNK")
    assert (chunk["event"], chunk["events"], chunk["selected"]) == ("MULTIPLE", [7, 8], [70, 80])
    assert [(c["event"], c["input_seq"]) for c in stage(lines, "PRICE_COMMITTED")] == [
        (7, 1), (8, 2)]
    # Both members are now traced; an untraced event is not.
    assert trace.tracks_event(7) and trace.tracks_event(8) and not trace.tracks_event(9)

    trace.stage_admission("REFRESH", None, [7, 8, 9], due=[7], excluded=[], fresh=[7, 8])
    admissions = stage(lines, "ADMISSION")
    assert [(x["event"], x["reason"], x["open_seqs"]) for x in admissions] == [
        (7, "DUE", [1]), (8, "NOT_DUE_THROTTLED_OR_BUDGET", [2])]

    trace.attempt_start([7, 9], 1.0)
    trace.attempt_start([8], 1.0)
    assert trace.attempts[7]["open_at_start"] == [1] and trace.attempts[7]["group"] == 2
    assert trace.attempts[8]["open_at_start"] == [2]
    # Member 7's stamp names only its own outcome, even with 80 in the basis.
    trace.stamp(7, {"70": STORED.timestamp(), "80": STORED.timestamp()}, 41, "db-clock")
    (joined,) = stage(lines, "EVENT_COMMITTED")
    assert (joined["event"], joined["outcome"], joined["revision"]) == (7, 70, 41)
    assert joined["attempt"] == trace.attempts[7]["attempt"]
    assert sorted(trace.waiting) == [2], "member 8's chain stays open"
    trace.attempt_committed([7, 9], {7: ("stamped", None, "db-clock", None, 41)})
    trace.attempt_released([7, 9])
    (attempt,) = stage(lines, "ATTEMPT")
    assert (attempt["event"], attempt["kind"], attempt["revision"], attempt["joined"]) == (
        7, "stamped", 41, True)
    assert 7 not in trace.attempts and 8 in trace.attempts
    trace.stamp(8, {"80": STORED.timestamp()}, 42, "db-clock")
    trace.attempt_released([8])
    assert [(e["event"], e["outcome"]) for e in stage(lines, "EVENT_COMMITTED")] == [
        (7, 70), (8, 80)]
    assert [x["event"] for x in stage(lines, "ATTEMPT")] == [7, 8]
    assert not trace.waiting


def test_a_chunk_fenced_on_two_members_names_each_held_attempt():
    trace, lines = make()
    a, b = mark(trace, 1, 70, 0.4), mark(trace, 2, 80, 0.6)
    trace.attempt_start([7], 1.0)
    held7 = trace.attempts[7]["attempt"]
    chunk = {70: 0.4, 80: 0.6}
    trace.flush_begin(1.0, False, {70: a, 80: b}, chunk)
    token = trace.chunk_begin(0, [70, 80])
    trace.fence(token, {7: object(), 8: object()}, {7, 8})
    fenced = stage(lines, "FENCED")
    assert [(f["event"], f["held_attempt"]) for f in fenced] == [
        (7, held7), (8, "QUEUED_NOT_STARTED")]
    assert token["fenced_by"] == {"7": held7, "8": "QUEUED_NOT_STARTED"}
    # Fenced on one member only: the single-event field shape.
    token2 = trace.chunk_begin(1, [70, 80])
    trace.fence(token2, {}, {8})
    assert token2["fenced_by"] == "QUEUED_NOT_STARTED"


def test_the_other_members_preview_and_selection_are_written():
    """The R1 hole: a fold whose PM origin is the member not named first."""
    frame = {"event_id": 8, "preview": {"kind": "revoke", "epoch": 3, "seq": 4,
                                        "through_seq": 4, "reason": "withdrawn"}}
    # One event named: the other member is never traced. Both armed: the other
    # member is traced once IT has a retained commit, not on its sibling's.
    for env, both, expect in (
        ({"WS_PM_TRACE_EVENT": "7", "WS_PM_TRACE_OUTCOMES": "70"}, True, False),
        ({}, False, False),
        ({}, True, True),
    ):
        trace, lines = make(**env)
        written = [mark(trace, 1, 70, 0.4)]
        if both:
            written.append(mark(trace, 2, 80, 0.6))
        write(trace, written)
        trace.preview(frame, {}, ["published", 1500])
        token = trace.selection_open(8)
        sel = trace.selection(token, "polymarket", "proposal", route="refresh",
                              value=0.6, basis={"80": STORED.timestamp()}, then="PROPOSE")
        previews, selected = stage(lines, "PREVIEW"), stage(lines, "SELECTED")
        if not expect:
            assert previews == [] and selected == [] and sel is None
            continue
        assert [(p["event"], p["kind"], p["seq"]) for p in previews] == [(8, "revoke", 4)]
        (s,) = selected
        assert s["event"] == 8 and (s["sel"], s["attempt"]) == sel
        assert s["inputs"] == [{"outcome": 80, "input_seq": 2, "receive_id": "UNAVAILABLE",
                                "linkage": "EXACT_OUTCOME_OBSERVATION_BASIS"}]


def test_the_line_budget_is_shared_across_members():
    trace, lines = make(WS_PM_TRACE_MAX_LINES="6")
    for seq in range(1, 9):
        mark(trace, seq, 70 if seq % 2 else 80, seq / 100)
    assert len(lines) <= 6 and lines[-1]["stage"] == "STOP"
    assert lines[-1]["reason"] == "BUDGET_STOP"
    assert not trace.active() and not trace.waiting and not trace.attempts


def test_warm_arm_re_reads_every_members_mapping():
    now = [1.0]
    event_of = dict(EVENT_OF)
    lines = []
    trace = PMStageTrace.from_env(
        {"WS_PM_TRACE_EVENT": "7,8", "WS_PM_TRACE_OUTCOMES": "70,80",
         "WS_PM_TRACE_ARM_AT": str(WALL + 60), "WS_PM_TRACE_EXPIRES_AT": str(WALL + 300)},
        run="r", event_of=event_of, wall=lambda: WALL + now[0] - 1.0,
        mono=lambda: now[0], emit=lines.append,
    )
    assert lines[0]["collection"] == "WAITING_FOR_ARM"
    assert lines[0]["outcome_event"] == {"70": 7, "80": 8}
    mark(trace, 1, 70, 0.4)
    assert len(lines) == 1, "nothing before the arm instant"
    event_of[80] = 9  # member 8's outcome was re-mapped while waiting
    now[0] = 61.5
    mark(trace, 2, 70, 0.5)
    (armed,) = stage(lines, "ARMED")
    assert armed["events"] == [7, 8] and armed["mapping"] == {"70": "MAPPED",
                                                               "80": "OTHER_EVENT"}
    assert armed["outcome_event"] == {"70": 7} and trace.targets == frozenset({70})
    assert armed["events_without_outcome"] == [8]
    assert [a["input_seq"] for a in stage(lines, "ACCEPTED")] == [2]


@pytest.mark.asyncio
async def test_two_members_flushed_and_stamped_on_the_real_path(monkeypatch):
    t = trace_rig(
        monkeypatch, mapping={1: 1, 2: 2}, contributing=(1, 2),
        env={"WS_PM_TRACE_EVENT": "1,2", "WS_PM_TRACE_OUTCOMES": "1,2",
             "WS_PM_TRACE_EXPIRES_AT": str(WALL + 300), "WS_PM_TRACE_MAX_LINES": "256"},
    )
    assert await flush(t, started=500.0)
    assert sorted(t.x.published) == [1, 2]
    assert [(a["event"], a["outcome"]) for a in stage(t.lines, "ACCEPTED")] == [(1, 1), (2, 2)]
    (chunk,) = stage(t.lines, "CHUNK")
    assert chunk["event"] == "MULTIPLE" and chunk["events"] == [1, 2]
    joined = sorted((e["event"], e["outcome"]) for e in stage(t.lines, "EVENT_COMMITTED"))
    assert joined == [(1, 1), (2, 2)], "each member's stamp joins only its own outcome"
    attempts = {a["event"]: a for a in stage(t.lines, "ATTEMPT")}
    assert set(attempts) == {1, 2} and all(a["joined"] for a in attempts.values())
    assert attempts[1]["attempt"] != attempts[2]["attempt"]
    assert not t.trace.waiting
