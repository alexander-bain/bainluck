"""#10090: the nonvenue receipt's bounds and fields, without a database.

PILLARS: TRUTH / FORMATTING. SHIP: the acceptance case can be scored on an
ordinary held page whose headline moved because a sportsbook, ESPN or model
reading changed, not only a venue's.

The commit/rollback/publication path is exercised on real PostgreSQL in
integration/test_nonvenue_trace_pg_10090.py. These pin what needs no database:
enablement bounds, the warm arm, the line and byte budgets, pending overflow,
the complete-bag fields, evidence sanitising, line ordinals, and that a
disarmed process builds nothing.
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


def write(trace, f, *, txn=None, evidence=None, sources=None, prior=None):
    token = trace.seam_entered(f["event_id"])
    trace.written(token, f, transaction=txn or Txn(), value=f["source_value"],
                  removed=f["source_value"] is None, rev=f["rev"][str(f["event_id"])],
                  stamped_at=f["updated_at"], sources=BAG if sources is None else sources,
                  status=f["status"], espn=None, opening=None, evidence=evidence,
                  metadata_keys=[], prior=prior, prior_txn_row_write=None)
    return token


def entry(f):
    return (object(), f, None, None, {})


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
    write(trace, f, txn=txn, prior={"espn": {"value": 0.55, "updated_at": "2026-10-28T17:59:00+00:00"}})
    trace.commit_started([entry(f)])
    trace.committed([entry(f)], {7: f}, lambda fr: True)
    token = trace.publish_started(f)
    trace.published(token, True)
    (pub,) = [x for x in lines if x["stage"] == "PUBLICATION"]
    assert (pub["txn"], pub["obs"], pub["event"], pub["rev"], pub["source"]) == (1, 1, 7, 11, "espn")
    assert (pub["value"], pub["result"], pub["commit_result"]) == (0.6, "SENT", "COMMITTED")
    assert pub["changed_sources"] == ["espn"] and pub["removed_sources"] == []
    assert (pub["prior_value"], pub["value_unchanged"]) == (0.55, False)
    assert pub["prior_clock"] == "ORM_VIEW_MAY_BE_STALE"
    assert pub["stamped_at"] == f["updated_at"]
    assert pub["bag"] == [{"source": "espn", "value": 0.6,
                           "updated_at": "2026-10-28T18:00:00+00:00", "weight": pub["bag"][0]["weight"],
                           "refused": False, "observed_basis": {"101": 1.5}}]
    assert pub["bag_other_keys"] == ["betting_book_count"] and pub["bag_omitted"] == 0
    assert pub["bag_hash"] == nt._hash(BAG) and pub["tier"] is not None
    assert pub["recomputed_p"] == 0.6 and pub["p_matches"] is True
    assert pub["frame_hash"] == nt._hash(f) and pub["frame_unchanged"] is True
    for clock in ("seam", "returned", "commit_start", "commit_end", "publish_start",
                  "publish_end"):
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
    assert records[id(a)]["value_unchanged"] is True
    assert records[id(b)]["value_unchanged"] is None  # no ORM view supplied
    # An ended transaction is forgotten; a new one gets a new id.
    first.is_active = second.is_active = False
    write(trace, frame(rev=13), txn=Txn())
    assert sorted(r["txn"] for _, r in trace.pending.values())[-1] == 3
    assert len(trace.txns) == 1


def test_untraced_events_and_frames_cost_nothing():
    trace, lines = make()
    assert trace.seam_entered(9) is None
    f = frame(event=9)
    trace.written(None, f, transaction=Txn(), value=0.6, removed=False, rev=1, stamped_at=None,
                  sources=BAG, status="live", espn=None, opening=None, evidence=None,
                  metadata_keys=[], prior=None, prior_txn_row_write=None)
    trace.commit_started([entry(f)])
    trace.committed([entry(f)], {9: f}, lambda fr: True)
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
    trace.committed([entry(f)], {7: f}, lambda fr: False)
    (unsent,) = [x for x in lines if x["stage"] == "WRITE_UNSENT"]
    evidence = unsent["evidence"]
    assert evidence["rule"] == "median" and evidence["floor"] == 2
    assert len(evidence["population"]) == 17 and evidence["population"][-1] == {"omitted": 4}
    assert evidence["population"][0] == {"book": "book0", "home_probability": 0.5}
    assert evidence["nan"] is None and evidence["UNPRINTABLE"] == "UNPRINTABLE"
    assert unsent["reason"] == "STATUS_NOT_LIVE"


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
    trace.commit_started([entry(f) for f in frames])
    trace.committed([entry(f) for f in frames], {7: frames[5], 8: frames[4]},
                    lambda fr: True)
    assert len(lines) <= 5 and lines[-1]["stage"] == "STOP"
    assert lines[-1]["reason"] == "BUDGET_STOP" and lines[-1]["observations"] == 6
    assert lines[-1]["awaiting_commit"] + lines[-1]["awaiting_publication"] >= 1
    assert not trace.pending and not trace.ready and not trace.active()


def test_the_byte_budget_stops(monkeypatch):
    monkeypatch.setattr(nt, "MAX_BYTES", 4096 + 1500)
    trace, lines = make()
    for i in range(10):
        f = frame(rev=i)
        write(trace, f)
        trace.committed([entry(f)], {7: f}, lambda fr: False)
    assert lines[-1]["stage"] == "STOP" and lines[-1]["reason"] == "BYTE_BUDGET_STOP"
    assert sum(len(json.dumps(x, sort_keys=True)) for x in lines[:-1]) < nt.MAX_BYTES


def test_pending_overflow_stops_rather_than_dropping_an_observation():
    trace, lines = make()
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
    trace.commit_started([entry(f)])
    assert lines[-1] == {**lines[-1], "stage": "STOP", "reason": "EXPIRED",
                         "awaiting_commit": 1}
    trace.committed([entry(f)], {7: f}, lambda fr: True)
    assert not [x for x in lines if x["stage"] in ("PUBLICATION", "WRITE_UNSENT")]


def test_warm_arm_keeps_nothing_before_the_instant():
    now = [WALL]
    trace, lines = make(now=now, NONVENUE_TRACE_ARM_AT=str(WALL + 60),
                        NONVENUE_TRACE_EXPIRES_AT=str(WALL + 300))
    assert lines[0]["collection"] == "WAITING_FOR_ARM"
    assert write(trace, frame(rev=1)) is None
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
    assert trace.seam_entered(bad) is None
    trace.written({}, bad, transaction=bad, value=None, removed=False, rev=None,
                  stamped_at=None, sources=bad, status=None, espn=None, opening=None,
                  evidence=None, metadata_keys=None, prior=bad, prior_txn_row_write=None)
    trace.commit_started(bad)
    trace.committed(bad, bad, bad)
    trace.rolled_back(bad, bad)
    assert trace.publish_started(bad) is None
    trace.published(bad, True)
    trace.publish_closed(bad, "ERROR")
    trace.pending[1] = (bad, {})  # corrupt state: still no raise
    trace.commit_started([(None, bad)])
    trace.committed([(None, bad)], {}, None)
