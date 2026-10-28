"""#10090: the nonvenue receipt's bounds, without a database.

PILLARS: TRUTH / FORMATTING. SHIP: the acceptance case can be scored on an
ordinary held page whose headline moved because a sportsbook, ESPN or model
reading changed, not only a venue's.

The commit/rollback/publication path is exercised on real PostgreSQL in
integration/test_nonvenue_trace_pg_10090.py. These pin what needs no database:
enablement bounds, the warm arm, the shared line budget, pending overflow,
evidence sanitising, and that a disarmed process builds nothing.
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
            "NONVENUE_TRACE_MAX_LINES": "256", "DYNO": "worker-realtime.1"}
    base.update(env)
    lines = []
    now = now or [WALL]
    trace = NonvenueTrace.from_env(
        {k: v for k, v in base.items() if v is not None},
        wall=lambda: now[0], mono=mono or (lambda: now[0] - WALL + 10.0),
        emit=lambda record: lines.append(json.loads(json.dumps(record))), run="r",
    )
    return trace, lines


def frame(event=7, source="espn", value=0.6, status="live", rev=11):
    return {"event_id": event, "p": 0.55, "source": source, "source_value": value,
            "updated_at": "2026-10-28T18:00:00+00:00", "status": status,
            "rev": {str(event): rev}}


def write(trace, f, *, evidence=None, entry=None):
    trace.written(f, value=f["source_value"], removed=f["source_value"] is None,
                  rev=f["rev"][str(f["event_id"])], stamped_at=f["updated_at"],
                  entry=entry if entry is not None else {"value": f["source_value"]},
                  evidence=evidence, metadata_keys=[])


def entry(f):
    return (object(), f, None, None, {})


def test_enablement_is_bounded():
    trace, lines = make()
    (start,) = lines
    assert start["stage"] == "START" and start["events"] == [7, 8]
    assert start["dyno"] == "worker-realtime.1" and isinstance(start["pid"], int)
    assert start["upstream_clock"] == "NOT_SUPPLIED_AT_SEAM" and start["run"] == "r"
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
    # Warm arm: at most 1800 s away, window at most 600 s after it.
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


def test_a_committed_write_reaches_its_publication_line_with_every_clock():
    trace, lines = make()
    f = frame()
    write(trace, f, entry={"value": 0.6, "observed_basis": {"101": 1.5},
                           "observed_value": 0.6, "eligibility": {"status": "verified"}})
    trace.commit_started([entry(f)])
    trace.committed([entry(f)], {7: f}, lambda fr: True)
    token = trace.publish_started(f)
    trace.published(token, True)
    (pub,) = [x for x in lines if x["stage"] == "PUBLICATION"]
    assert (pub["event"], pub["rev"], pub["source"], pub["value"], pub["result"]) == (
        7, 11, "espn", 0.6, "SENT")
    assert pub["stamped_at"] == f["updated_at"]
    assert pub["stamped_clock"] == "DB_CLOCK_TIMESTAMP_IN_UPDATE"
    assert pub["observed_basis"] == {"101": 1.5} and pub["entry_eligibility"] == {
        "status": "verified"}
    assert pub["evidence"] is None and pub["upstream_clock"] == "NOT_SUPPLIED_AT_SEAM"
    for clock in ("returned", "commit_start", "commit_end", "publish_start", "publish_end"):
        assert f"{clock}_wall" in pub and f"{clock}_mono" in pub
    assert not trace.pending and not trace.ready


def test_untraced_events_and_frames_cost_nothing():
    trace, lines = make()
    f = frame(event=9)
    write(trace, f)
    trace.commit_started([entry(f)])
    trace.committed([entry(f)], {9: f}, lambda fr: True)
    assert trace.publish_started(f) is None
    trace.publish_closed([f], "ERROR")
    trace.rolled_back([entry(f)])
    assert [x["stage"] for x in lines] == ["START"]


def test_evidence_is_sanitised_and_bounded():
    trace, lines = make()
    f = frame(source="betting")
    population = [{"book": f"book{i}", "home_probability": 0.5 + i / 100} for i in range(20)]
    write(trace, f, evidence={"rule": "median", "floor": 2, "decision": "admitted",
                              "median": 0.6, "split_pair": None, "population": population,
                              "secret\nkey": "x" * 200, "nan": float("nan")})
    trace.committed([entry(f)], {7: f}, lambda fr: False)  # removal/not-live: unsent
    (unsent,) = [x for x in lines if x["stage"] == "WRITE_UNSENT"]
    evidence = unsent["evidence"]
    assert evidence["rule"] == "median" and evidence["floor"] == 2
    assert len(evidence["population"]) == 17 and evidence["population"][-1] == {"omitted": 4}
    assert evidence["population"][0] == {"book": "book0", "home_probability": 0.5}
    assert evidence["nan"] is None and evidence["UNPRINTABLE"] == "UNPRINTABLE"
    assert unsent["reason"] == "STATUS_NOT_LIVE"


def test_the_line_budget_is_shared_and_stop_names_what_was_owed():
    trace, lines = make(NONVENUE_TRACE_MAX_LINES="5")
    frames = [frame(event=7 if i % 2 else 8, rev=i) for i in range(6)]
    for f in frames:
        write(trace, f)
    trace.commit_started([entry(f) for f in frames])
    trace.committed([entry(f) for f in frames], {7: frames[5], 8: frames[4]},
                    lambda fr: True)
    assert len(lines) <= 5 and lines[-1]["stage"] == "STOP"
    assert lines[-1]["reason"] == "BUDGET_STOP"
    assert lines[-1]["awaiting_commit"] + lines[-1]["awaiting_publication"] >= 1
    assert not trace.pending and not trace.ready and not trace.active()


def test_pending_overflow_stops_rather_than_dropping_a_write():
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
    early = frame(rev=1)
    write(trace, early)
    assert not trace.pending and len(lines) == 1
    now[0] = WALL + 61.5
    late = frame(rev=2)
    write(trace, late)
    (armed,) = [x for x in lines if x["stage"] == "ARMED"]
    assert armed["late_by_s"] == 1.5 and armed["window_left_s"] == 238.5
    assert list(trace.pending.values())[0][1]["rev"] == 2
    now[0] = WALL + 301
    assert not trace.active() and lines[-1]["reason"] == "EXPIRED"


def test_every_entry_point_swallows_its_own_failure():
    trace, lines = make()
    bad = object()
    trace.written(bad, value=None, removed=False, rev=None, stamped_at=None, entry=None,
                  evidence=None, metadata_keys=None)
    trace.commit_started(bad)
    trace.committed(bad, bad, bad)
    trace.rolled_back(bad)
    assert trace.publish_started(bad) is None
    trace.published(bad, True)
    trace.publish_closed(bad, "ERROR")
    trace.pending[1] = (bad, {})  # corrupt state: still no raise
    trace.commit_started([(None, bad)])
    trace.committed([(None, bad)], {}, None)
