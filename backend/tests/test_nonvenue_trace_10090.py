"""#10090: the nonvenue receipt's bounds and fields, without a database.

PILLARS: TRUTH / FORMATTING. SHIP: the acceptance case can be scored on an
ordinary held page whose headline moved because a sportsbook, ESPN or model
reading changed, not only a venue's.

The commit/rollback/publication path is exercised on real PostgreSQL in
integration/test_nonvenue_trace_pg_10090.py. These pin what needs no database:
enablement bounds, the warm arm, the line and byte budgets, pending overflow,
the complete-bag fields, evidence sanitising, line ordinals, that a disarmed
process builds nothing, and how the final read decides FINAL_STATE_ESTABLISHED
(one read per traced COMMIT; any moved blend input, pending ORM write, vanished
row or failed read keeps it NOT_ESTABLISHED).
"""

import json


import pytest

from app.utils import nonvenue_trace as nt
from app.utils.nonvenue_trace import NonvenueTrace

WALL = 1_000_000.0


@pytest.fixture(autouse=True)
def _fresh():
    nt.reset_for_tests()
    yield
    nt.reset_for_tests()


def make(now=None, mono=None, **env):
    base = {"NONVENUE_TRACE_EVENTS": "7,8", "NONVENUE_TRACE_EXPIRES_AT": str(WALL + 300),
            "NONVENUE_TRACE_MAX_LINES": "256", "DYNO": "worker-realtime.1",
            "HEROKU_SLUG_COMMIT": "abc123"}
    base.update(env)
    lines = []
    now = now or [WALL]
    trace = NonvenueTrace.from_env(
        {k: v for k, v in base.items() if v is not None},
        wall=lambda: now[0], mono=mono or (lambda: now[0] - WALL + 10.0),
        emit=lambda text: lines.append(json.loads(text)), run="r",
    )
    return trace, lines


class Txn:
    is_active = True


def frame(event=7, source="espn", value=0.6, status="live", rev=11):
    return {"event_id": event, "p": 0.6, "source": source, "source_value": value,
            "updated_at": "2026-10-28T18:00:00+00:00", "status": status,
            "rev": {str(event): rev}}


BAG = {"espn": {"value": 0.6, "updated_at": "2026-10-28T18:00:00+00:00",
                "observed_basis": {"101": 1.5}},
       "betting_book_count": 3}


def select(trace, f, *, txn=None, evidence=None, prior=None, inputs=None):
    return trace.seam_entered(f["event_id"], transaction=txn or Txn(), source=f["source"],
                              value=f["source_value"], evidence=evidence, metadata_keys=[],
                              prior=prior, inputs=inputs)


def write(trace, f, *, txn=None, evidence=None, sources=None, prior=None, inputs=None):
    txn = txn or Txn()
    obs = select(trace, f, txn=txn, evidence=evidence, prior=prior, inputs=inputs)
    trace.written(obs, f, transaction=txn, rev=f["rev"][str(f["event_id"])],
                  stamped_at=f["updated_at"],
                  sources=BAG if sources is None else sources, status=f["status"],
                  espn=None, opening=None, prior_txn_row_write=None)
    return obs


def entry(f, rev=None, sources=None):
    observation = {"source": f["source"], "value": f["source_value"],
                   "removed": f["source_value"] is None,
                   "rev": rev if rev is not None else f["rev"][str(f["event_id"])],
                   "stamped_at": f["updated_at"], "returned_sources": sources or BAG,
                   "metadata_keys": [], "evidence": None, "prior_txn_row_write": None}
    return (object(), f, None, None, observation)


def sent(f):
    return f["status"] == "live" and f["source_value"] is not None


def test_enablement_is_bounded():
    trace, lines = make()
    (start,) = lines
    assert start["stage"] == "START" and start["events"] == [7, 8] and start["line"] == 1
    assert start["schema"] == "nonvenue-trace/1" and start["slug_commit"] == "abc123"
    assert start["dyno"] == "worker-realtime.1" and isinstance(start["pid"], int)
    assert start["max_bytes"] == nt.MAX_BYTES and start["run"] == "r"
    assert NonvenueTrace.from_env({}) is None
    assert make(NONVENUE_TRACE_EVENTS="1,2,3,4")[0] is not None
    assert make(NONVENUE_TRACE_EVENTS="1,2,3,4,5")[0] is None
    assert make(NONVENUE_TRACE_EVENTS="7; DROP")[0] is None
    assert make(NONVENUE_TRACE_EVENTS="7,,8")[0] is None
    assert make(NONVENUE_TRACE_EXPIRES_AT=str(WALL + 601))[0] is None
    assert make(NONVENUE_TRACE_EXPIRES_AT=str(WALL - 1))[0] is None
    assert make(NONVENUE_TRACE_EXPIRES_AT="soon")[0] is None
    assert make(NONVENUE_TRACE_MAX_LINES="3")[0] is None
    assert make(NONVENUE_TRACE_MAX_LINES="257")[0] is None
    assert make(NONVENUE_TRACE_ARM_AT=str(WALL + 1801),
                NONVENUE_TRACE_EXPIRES_AT=str(WALL + 2000))[0] is None
    assert make(NONVENUE_TRACE_ARM_AT=str(WALL + 60),
                NONVENUE_TRACE_EXPIRES_AT=str(WALL + 661))[0] is None
    assert make(NONVENUE_TRACE_ARM_AT="x" * 33,
                NONVENUE_TRACE_EXPIRES_AT=str(WALL + 300))[0] is None


def test_disarmed_process_builds_nothing_and_reads_the_environment_once(monkeypatch):
    reads = []

    class Env(dict):
        def get(self, key, default=None):
            reads.append(key)
            return super().get(key, default)

    monkeypatch.setattr(nt.os, "environ", Env())
    assert nt.nonvenue_trace() is None and nt.nonvenue_trace() is None
    assert reads == ["NONVENUE_TRACE_EVENTS"]


def test_a_committed_observation_carries_its_bag_identity_and_every_clock():
    trace, lines = make()
    f = frame()
    txn = Txn()
    write(trace, f, txn=txn, prior={"espn": {"value": 0.55, "updated_at": "2026-10-28T17:59:00+00:00"}},
          inputs=lambda: {"espn_id": "401", "clock": "4:32"})
    (selected,) = [x for x in lines if x["stage"] == "SELECTED"]
    assert (selected["txn"], selected["obs"], selected["event"], selected["source"]) == (1, 1, 7, "espn")
    assert selected["changed_sources"] == ["espn"] and selected["removed_sources"] == []
    assert (selected["prior_value"], selected["value_unchanged"]) == (0.55, False)
    assert selected["prior_clock"] == "ORM_VIEW_MAY_BE_STALE"
    assert selected["inputs"] == {"clock": "4:32", "espn_id": "401"}
    assert selected["select_clock"] == "SEAM_ENTRY_BEFORE_AWAITED_PROBE_AND_UPDATE"
    assert "seam_mono" in selected and "rev" not in selected
    trace.commit_started([entry(f)], sent)
    trace.committed([entry(f)], {7: f}, sent)
    token = trace.publish_started(f)
    trace.published(token, True)
    (pub,) = [x for x in lines if x["stage"] == "PUBLICATION"]
    assert (pub["txn"], pub["obs"], pub["event"], pub["rev"], pub["source"]) == (1, 1, 7, 11, "espn")
    assert (pub["value"], pub["result"], pub["commit_result"]) == (0.6, "SENT", "COMMITTED")
    assert pub["stamped_at"] == f["updated_at"] and "_inputs" not in pub
    final = pub["final"]
    assert (final["final_state"], final["as_of"]) == (
        "FINAL_STATE_NOT_ESTABLISHED", "LAST_TRACED_RETURNING")
    assert final["blend_probability"] == 0.6 and final["queued_frame_matches"] is True
    assert final["coverage"] and final["observations_in_txn"] == 1
    assert pub["bag"] == [{"source": "espn", "value": 0.6,
                           "updated_at": "2026-10-28T18:00:00+00:00", "weight": pub["bag"][0]["weight"],
                           "refused": False, "observed_basis": {"101": 1.5}}]
    assert pub["bag_other_keys"] == ["betting_book_count"] and pub["bag_omitted"] == 0
    assert pub["bag_hash"] == nt._hash(BAG) and pub["tier"] is not None
    assert pub["recomputed_p"] == 0.6 and pub["p_matches"] is True
    assert pub["frame_hash"] == nt._hash(f) and pub["frame_unchanged"] is True
    for clock in ("returned", "commit_start", "commit_end", "publish_start", "publish_end"):
        assert f"{clock}_wall" in pub and f"{clock}_mono" in pub
    assert [x["line"] for x in lines] == list(range(1, len(lines) + 1))
    assert not trace.pending and not trace.ready


def test_observations_group_by_outer_transaction_and_keep_no_ops():
    trace, lines = make()
    first, second = Txn(), Txn()
    a, b = frame(rev=11), frame(source="stat_model", rev=12)
    write(trace, a, txn=first, prior={"espn": {"value": 0.6}})  # a no-op by the ORM view
    write(trace, b, txn=first)
    c = frame(event=8, rev=3)
    write(trace, c, txn=second)
    records = {id(fr): rec for fr, rec in trace.pending.values()}
    assert [records[id(x)]["txn"] for x in (a, b, c)] == [1, 1, 2]
    assert [records[id(x)]["obs"] for x in (a, b, c)] == [1, 2, 3]
    selected = [x for x in lines if x["stage"] == "SELECTED"]
    assert selected[0]["value_unchanged"] is True
    assert selected[1]["value_unchanged"] is None  # no ORM view supplied
    # An ended transaction is forgotten; a new one gets a new id.
    first.is_active = second.is_active = False
    write(trace, frame(rev=13), txn=Txn())
    assert sorted(r["txn"] for _, r in trace.pending.values())[-1] == 3
    assert len(trace.txns) == 1


def test_untraced_events_and_frames_cost_nothing():
    trace, lines = make()
    f = frame(event=9)
    assert select(trace, f, inputs=lambda: 1 / 0) is None  # never evaluated
    trace.written(None, f, transaction=Txn(), rev=1, stamped_at=None, sources=BAG,
                  status="live", espn=None, opening=None, prior_txn_row_write=None)
    trace.commit_started([entry(f)], sent)
    trace.committed([entry(f)], {9: f}, sent)
    assert trace.publish_started(f) is None
    trace.publish_closed([f], "ERROR")
    trace.rolled_back(None, [entry(f)])
    assert [x["stage"] for x in lines] == ["START"]


def test_evidence_is_sanitised_and_bounded():
    trace, lines = make()
    f = frame(source="betting")
    population = [{"book": f"book{i}", "home_probability": 0.5 + i / 100} for i in range(20)]
    write(trace, f, evidence={"rule": "median", "floor": 2, "decision": "admitted",
                              "median": 0.6, "split_pair": None, "population": population,
                              "secret\nkey": "x" * 200, "nan": float("nan")})
    (selected,) = [x for x in lines if x["stage"] == "SELECTED"]
    evidence = selected["evidence"]
    assert evidence["rule"] == "median" and evidence["floor"] == 2
    assert len(evidence["population"]) == 17 and evidence["population"][-1] == {"omitted": 4}
    assert evidence["population"][0] == {"book": "book0", "home_probability": 0.5}
    assert evidence["nan"] is None and evidence["UNPRINTABLE"] == "UNPRINTABLE"


def test_a_wide_bag_is_bounded_and_counted(monkeypatch):
    trace, lines = make()
    from app.utils import aggregation

    names = [f"src{i:02d}" for i in range(20)]
    monkeypatch.setattr(aggregation, "SOURCE_WEIGHTS", dict.fromkeys(names, 1.0))
    wide = {name: {"value": 0.5, "updated_at": "2026-10-28T18:00:00+00:00"} for name in names}
    f = frame()
    write(trace, f, sources=wide)
    trace.committed([entry(f)], {7: f}, lambda fr: False)
    (unsent,) = [x for x in lines if x["stage"] == "WRITE_UNSENT"]
    assert len(unsent["bag"]) == 16 and unsent["bag_omitted"] == 4
    assert unsent["bag_hash"] == nt._hash(wide)


def test_the_line_budget_stops_and_names_its_counters():
    trace, lines = make(NONVENUE_TRACE_MAX_LINES="5")
    frames = [frame(event=7 if i % 2 else 8, rev=i) for i in range(6)]
    for f in frames:
        write(trace, f)
    trace.commit_started([entry(f) for f in frames], sent)
    trace.committed([entry(f) for f in frames], {7: frames[5], 8: frames[4]}, sent)
    assert len(lines) <= 5 and lines[-1]["stage"] == "STOP"
    assert lines[-1]["reason"] == "BUDGET_STOP"
    stop = lines[-1]
    # N3: every observation is either printed with a terminal or counted.
    terminals = [x for x in lines if x["stage"] in ("WRITE_UNSENT", "PUBLICATION")]
    assert stop["observations"] == len(terminals) + stop["awaiting_write"] + \
        stop["awaiting_commit"] + stop["awaiting_publication"]
    assert not trace.pending and not trace.ready and not trace.active()


def test_the_byte_budget_stops(monkeypatch):
    monkeypatch.setattr(nt, "MAX_BYTES", nt.BYTE_RESERVE + 1500)
    trace, lines = make()
    for i in range(10):
        f = frame(rev=i)
        write(trace, f)
        trace.committed([entry(f)], {7: f}, lambda fr: False)
    assert lines[-1]["stage"] == "STOP" and lines[-1]["reason"] == "BYTE_BUDGET_STOP"
    assert sum(len(json.dumps(x, sort_keys=True)) for x in lines[:-1]) < nt.MAX_BYTES


def test_pending_overflow_stops_rather_than_dropping_an_observation():
    trace, lines = make()
    trace.limit = 10_000  # this test is about pending state, not lines
    for i in range(nt.MAX_PENDING + 1):
        write(trace, frame(rev=i))
    assert lines[-1]["stage"] == "STOP" and lines[-1]["reason"] == "PENDING_OVERFLOW"
    assert lines[-1]["awaiting_commit"] == nt.MAX_PENDING and not trace.pending


def test_expiry_stops_and_discards():
    now = [WALL]
    trace, lines = make(now=now)
    f = frame()
    write(trace, f)
    now[0] = WALL + 301
    trace.commit_started([entry(f)], sent)
    assert lines[-1] == {**lines[-1], "stage": "STOP", "reason": "EXPIRED",
                         "awaiting_commit": 1}
    trace.committed([entry(f)], {7: f}, sent)
    assert not [x for x in lines if x["stage"] in ("PUBLICATION", "WRITE_UNSENT")]


def test_warm_arm_keeps_nothing_before_the_instant():
    now = [WALL]
    trace, lines = make(now=now, NONVENUE_TRACE_ARM_AT=str(WALL + 60),
                        NONVENUE_TRACE_EXPIRES_AT=str(WALL + 300))
    assert lines[0]["collection"] == "WAITING_FOR_ARM"
    obs = write(trace, frame(rev=1))
    assert obs is None
    assert not trace.pending and len(lines) == 1
    now[0] = WALL + 61.5
    write(trace, frame(rev=2))
    (armed,) = [x for x in lines if x["stage"] == "ARMED"]
    assert armed["late_by_s"] == 1.5 and armed["window_left_s"] == 238.5
    assert list(trace.pending.values())[0][1]["rev"] == 2
    now[0] = WALL + 301
    assert not trace.active() and lines[-1]["reason"] == "EXPIRED"


def test_every_entry_point_swallows_its_own_failure():
    trace, lines = make()
    bad = object()
    assert trace.seam_entered(bad, transaction=bad, source=bad, value=None, evidence=None,
                              metadata_keys=None, prior=bad, inputs=None) is None
    trace.written(1, bad, transaction=bad, rev=None, stamped_at=None, sources=bad,
                  status=None, espn=None, opening=None, prior_txn_row_write=None)
    trace.write_failed(bad, bad)
    trace.missing_row(bad)
    trace.commit_started(bad, bad)
    trace.committed(bad, bad, bad)
    trace.rolled_back(bad, bad)
    assert trace.publish_started(bad) is None
    trace.published(bad, True)
    trace.publish_closed(bad, "ERROR")
    trace.pending[1] = (bad, {})  # corrupt state: still no raise
    trace.commit_started([(None, bad)], None)
    trace.committed([(None, bad)], {}, None)


def test_a_failing_witness_keeps_its_receipt_through_commit_and_publication():
    trace, lines = make()
    f = frame()
    obs = write(trace, f, inputs=lambda: 1 / 0)  # the producer's witness raises
    assert obs is not None and trace.hook_errors == 1
    trace.commit_started([entry(f)], sent)
    trace.committed([entry(f)], {7: f}, sent)
    trace.published(trace.publish_started(f), True)
    trace._stop("EXPIRED")
    (sel,) = [x for x in lines if x["stage"] == "SELECTED"]
    (pub,) = [x for x in lines if x["stage"] == "PUBLICATION"]
    assert sel["inputs"] == "WITNESS_ERROR" and pub["obs"] == sel["obs"] == obs
    assert pub["result"] == "SENT"
    stop = lines[-1]
    assert (stop["observations"], stop["published"], stop["awaiting_write"],
            stop["hook_errors"]) == (1, 1, 0, 1)


def test_a_witness_datetime_prints_as_iso_text_at_any_depth():
    from datetime import datetime, timezone

    at = datetime(2026, 10, 28, 18, 5, 3, 120000, tzinfo=timezone.utc)
    trace, lines = make()
    write(trace, frame(source="betting"),
          inputs=lambda: {"captured_at": at, "books": [{"captured_at": at}]})
    (sel,) = [x for x in lines if x["stage"] == "SELECTED"]
    assert sel["inputs"]["captured_at"] == "2026-10-28T18:05:03.120000+00:00"
    assert sel["inputs"]["books"][0]["captured_at"] == "2026-10-28T18:05:03.120000+00:00"
    assert nt._text("1st & 10, Smith's ball (OT)") == "1st & 10, Smith's ball (OT)"


@pytest.mark.parametrize("held", ["selected", "pending", "ready"])
@pytest.mark.parametrize("traffic", ["seam", "commit", "publish"])
def test_untraced_traffic_stops_an_expired_trace_that_still_owes_something(held, traffic):
    """lane1b P3: a traced event goes quiet while an obligation is held; the
    next untraced write, COMMIT or publication after expiry prints STOP."""
    now = [WALL]
    trace, lines = make(now=now)
    f = frame()
    if held == "selected":
        select(trace, f)  # its UPDATE never returns
    else:
        write(trace, f)
        if held == "ready":
            trace.commit_started([entry(f)], sent)
            trace.committed([entry(f)], {7: f}, sent)  # committed, never drained
    now[0] = WALL + 301
    other = frame(event=9)
    if traffic == "seam":
        assert select(trace, other) is None
    elif traffic == "commit":
        trace.commit_started([entry(other)], sent)
    else:
        assert trace.publish_started(other) is None
    stop = lines[-1]
    assert (stop["stage"], stop["reason"]) == ("STOP", "EXPIRED")
    owed = {"selected": "awaiting_write", "pending": "awaiting_commit",
            "ready": "awaiting_publication"}[held]
    assert stop[owed] == 1
    assert not (trace.selected or trace.pending or trace.ready)


def test_untraced_traffic_with_nothing_owed_prints_nothing_even_after_expiry():
    now = [WALL]
    trace, lines = make(now=now)
    now[0] = WALL + 301
    other = frame(event=9)
    select(trace, other)
    trace.commit_started([entry(other)], sent)
    trace.publish_started(other)
    assert [x["stage"] for x in lines] == ["START"]


def test_a_selection_whose_write_never_returns_is_closed_or_counted():
    import asyncio

    trace, lines = make()
    hung, failed, cancelled, missing = (frame(rev=i) for i in range(4))
    obs = {name: select(trace, f) for name, f in
           (("hung", hung), ("failed", failed), ("cancelled", cancelled), ("missing", missing))}
    assert [x["stage"] for x in lines[1:]] == ["SELECTED"] * 4, "emitted before any await"
    trace.write_failed(obs["failed"], RuntimeError("deadlock"))
    trace.write_failed(obs["cancelled"], asyncio.CancelledError())
    trace.missing_row(obs["missing"])
    closed = {x["obs"]: x for x in lines if x["stage"] == "WRITE_UNSENT"}
    assert (closed[obs["failed"]]["reason"], closed[obs["failed"]]["error"]) == (
        "UPDATE_ERROR", "RuntimeError")
    assert closed[obs["cancelled"]]["reason"] == "UPDATE_CANCELLED"
    assert closed[obs["missing"]]["reason"] == "MISSING_ROW"
    assert "failed_mono" in closed[obs["missing"]]
    trace._stop("EXPIRED")  # the hung UPDATE is still owed: counted, not silent
    assert lines[-1]["awaiting_write"] == 1 and lines[-1]["observations"] == 4


def test_a_terminal_at_the_budget_edge_is_counted_never_lost():
    for remaining in range(1, 4):
        trace, lines = make(NONVENUE_TRACE_MAX_LINES="8")
        f = frame()
        write(trace, f)
        trace.commit_started([entry(f)], sent)
        trace.committed([entry(f)], {7: f}, sent)
        token = trace.publish_started(f)
        trace.lines = trace.limit - remaining  # the budget edge
        trace.published(token, True)
        stop = [x for x in lines if x["stage"] == "STOP"]
        printed = [x for x in lines if x["stage"] == "PUBLICATION"]
        if stop:
            assert stop[0]["awaiting_publication"] + len(printed) == 1
        else:
            assert len(printed) == 1


def test_a_frame_never_handed_over_reads_batch_closure_not_publish_end():
    trace, lines = make()
    first, second = frame(event=7), frame(event=8, rev=3)
    for f in (first, second):
        write(trace, f)
    entries = [entry(first), entry(second)]
    trace.commit_started(entries, sent)
    trace.committed(entries, {7: first, 8: second}, sent)
    trace.publish_started(first)
    trace.publish_closed([first, second], "TIMEOUT")
    pubs = {x["event"]: x for x in lines if x["stage"] == "PUBLICATION"}
    assert pubs[7]["result"] == "TIMEOUT" and "publish_end_mono" in pubs[7]
    assert pubs[8]["result"] == "NOT_ATTEMPTED_AFTER_TIMEOUT"
    assert "publish_end_mono" not in pubs[8] and "batch_closed_mono" in pubs[8]


def test_send_failures_are_counted():
    trace, lines = make()
    trace.emit = lambda text: 1 / 0
    write(trace, frame())
    trace.emit = lambda text: lines.append(json.loads(text))
    trace._stop("EXPIRED")
    assert lines[-1]["send_errors"] == 1


def test_a_transaction_not_yet_begun_is_bound_when_the_update_returns():
    trace, lines = make()
    f = frame()
    obs = trace.seam_entered(7, transaction=None, source="espn", value=0.6, evidence=None,
                             metadata_keys=[], prior=None, inputs=None)
    (sel,) = [x for x in lines if x["stage"] == "SELECTED"]
    assert sel["txn"] is None and sel["txn_pending"] is True
    txn = Txn()
    trace.written(obs, f, transaction=txn, rev=11, stamped_at=f["updated_at"], sources=BAG,
                  status="live", espn=None, opening=None, prior_txn_row_write=None)
    (_frame, record), = trace.pending.values()
    assert record["txn"] == 1 and record["obs"] == sel["obs"]


# ── the final read (FINAL_STATE_ESTABLISHED) ─────────────────────────────────


def row(f, **changes):
    """The committing row exactly as `write` left it, then ``changes``."""
    base = dict(rev=f["rev"][str(f["event_id"])], sources=BAG, status=f["status"],
                espn_win_prob_home=None, opening_home_probability=None, orm_pending=False)
    base.update(changes)
    return base


def commit(trace, frames, read):
    pending = [entry(f) for f in frames]
    trace.commit_started(pending, sent, read=read)
    trace.committed(pending, {f["event_id"]: f for f in frames}, sent)
    for f in frames:
        trace.published(trace.publish_started(f), True)


def finals(lines):
    return {x["event"]: x["final"] for x in lines if x["stage"] == "PUBLICATION"}


def test_one_read_per_commit_establishes_every_unmoved_traced_event():
    trace, lines = make()
    a, b = frame(event=7, rev=11), frame(event=8, rev=4)
    write(trace, a)
    write(trace, b)
    calls = []

    def read(ids):
        calls.append(ids)
        return {7: row(a), 8: row(b)}

    commit(trace, [a, b], read)
    assert calls == [[7, 8]] and trace.final_reads == 1
    for event, final in finals(lines).items():
        assert (final["final_state"], final["check"], final["differs"]) == (
            "FINAL_STATE_ESTABLISHED", "ROW_MATCHES_LAST_TRACED_RETURNING", [])
        assert final["observed_rev"] == {7: 11, 8: 4}[event]
        assert final["observed_bag_hash"] == nt._hash(BAG) and final["read_ms"] >= 0
        assert final["as_of"] == "LAST_TRACED_RETURNING"
        assert final["blend_probability"] == 0.6  # still built from the RETURNING
    trace._stop("EXPIRED")
    assert lines[-1]["final_reads"] == 1


@pytest.mark.parametrize("field,moved", [
    ("rev", 12),
    ("sources", {"espn": {"value": 0.2, "updated_at": "2026-10-28T18:01:00+00:00"}}),
    ("status", "final"),  # moves no rev: the trigger counts the bag only
    ("espn_win_prob_home", 0.4),
    ("opening_home_probability", 0.55),
])
def test_any_blend_input_moved_after_the_last_traced_returning_is_not_established(
    field, moved
):
    trace, lines = make()
    f = frame()
    write(trace, f)
    commit(trace, [f], lambda ids: {7: row(f, **{field: moved})})
    final = finals(lines)[7]
    assert (final["final_state"], final["check"], final["differs"]) == (
        "FINAL_STATE_NOT_ESTABLISHED", "ROW_DIFFERS", [field])
    assert final["observed_rev"] == (12 if field == "rev" else 11)


def test_a_pending_orm_write_to_the_row_is_not_established_even_when_it_matches():
    trace, lines = make()
    f = frame()
    write(trace, f)
    commit(trace, [f], lambda ids: {7: row(f, orm_pending=True)})
    final = finals(lines)[7]
    assert (final["final_state"], final["check"], final["orm_write_pending"]) == (
        "FINAL_STATE_NOT_ESTABLISHED", "ORM_WRITE_PENDING", True)


def test_a_vanished_row_or_a_failed_read_is_not_established_and_never_raises():
    trace, lines = make()
    f, g = frame(rev=11), frame(rev=12)
    write(trace, f)
    commit(trace, [f], lambda ids: {})
    write(trace, g)

    def broken(ids):
        raise ConnectionError("read failed")

    commit(trace, [g], broken)
    first, second = [x["final"] for x in lines if x["stage"] == "PUBLICATION"]
    assert (first["final_state"], first["check"]) == ("FINAL_STATE_NOT_ESTABLISHED",
                                                      "ROW_MISSING")
    assert (second["final_state"], second["check"], second["error"]) == (
        "FINAL_STATE_NOT_ESTABLISHED", "READ_ERROR", "ConnectionError")
    assert trace.hook_errors == 1 and trace.final_reads == 2
    assert trace.n_published == 2  # both terminals printed


def test_no_read_without_a_traced_event_an_active_trace_or_a_built_final(monkeypatch):
    calls = []

    def read(ids):
        calls.append(ids)
        return {}

    trace, lines = make()
    untraced = frame(event=9)
    commit(trace, [untraced], read)  # an untraced commit
    f = frame()
    write(trace, f)
    trace.commit_started([entry(f)], sent)  # no reader: NOT_READ
    assert trace.pending[id(f)][1]["final"]["check"] == "NOT_READ"
    from app.utils import probability_publication

    monkeypatch.setattr(probability_publication, "build_publication",
                        lambda **_kw: 1 / 0)
    g = frame(rev=12)
    write(trace, g)
    trace.commit_started([entry(g)], sent, read=read)  # final not built
    assert trace.pending[id(g)][1]["final"]["error"] == "ZeroDivisionError"
    trace._stop("EXPIRED")
    h = frame(rev=13)
    trace.commit_started([entry(h)], sent, read=read)  # stopped
    assert calls == [] and trace.final_reads == 0


def test_the_final_read_is_the_last_before_commit_hook_in_the_app():
    """The final read can only miss a write made AFTER it inside the same
    transaction: pending ORM state (named ORM_WRITE_PENDING) or a later
    ``before_commit`` listener. This pins that `nonvenue_live_push` registers
    the only one in ``app/``; a second must answer whether it writes events."""
    import pathlib
    import re as _re

    app = pathlib.Path(nt.__file__).resolve().parents[1]
    hooks = sorted(
        str(path.relative_to(app))
        for path in app.rglob("*.py")
        if _re.search(r"""listen(?:s_for)?\([^)]*["']before_commit["']""", path.read_text())
    )
    assert hooks == ["utils/nonvenue_live_push.py"]
