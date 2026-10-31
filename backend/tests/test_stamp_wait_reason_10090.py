"""#10090 — `stamp_wait_reason`: why a live game's oldest unstamped input waits.

Ship: no live game's price is left frozen for minutes. Production 03:40Z
2026-10-31 (Polymarket 15331470, live soccer): an input received 03:40:12.988
was stamped at 03:42:10.714, 117.7 s later (oldest input 03:40:09.205). The
admission and read state that would say why was not retained, so the fix is
still a guess. This line names the cause from state the refresher already
holds; log only.

Controls: each reason fires on a constructed state; nothing below
STAMP_WAIT_BUDGET_S; at most one line per event per minute (an episode that
printed closes with STAMPED); the minute line's count; and identical
behaviour with `STAMP_WAIT_REASON_LOG=0`.
"""
import logging
from collections import deque

import pytest

from app.tasks import live_blend_refresh as module
from tests.test_single_event_commit_10090 import rig

LOGGER = "app.tasks.live_blend_refresh"
WALL = 1_800_000_000.0


@pytest.fixture
def clocks(monkeypatch):
    clock = {"mono": 1000.0, "wall": WALL}
    monkeypatch.setattr(module, "_mono", lambda: clock["mono"])
    monkeypatch.setattr(module, "_wall", lambda: clock["wall"])
    monkeypatch.delenv(module.STAMP_WAIT_REASON_ENV, raising=False)
    return clock


def _advance(clock, seconds):
    clock["mono"] += seconds
    clock["wall"] += seconds


def _refresher(**kwargs):
    r = module.LiveBlendRefresher("polymarket", **kwargs)
    r.receipts = module.TailReceipts("polymarket")
    return r


def _owe_input(r, event_id, *, age, seq=5, outcome=50):
    """A live event whose oldest uncovered input arrived ``age`` s ago."""
    receipts = r.receipts
    receipts._live_events.add(event_id)
    receipts._uncovered[event_id] = deque([(seq, module._wall() - age, outcome)])


def _lines(caplog):
    return [rec.getMessage() for rec in caplog.records
            if "stamp_wait_reason=" in rec.getMessage()]


def _reason(line):
    return line.split("stamp_wait_reason=", 1)[1].split()[0]


def _field(line, name):
    return line.split(f" {name}=", 1)[1].split()[0]


@pytest.fixture
def info(caplog):
    caplog.set_level(logging.INFO, logger=LOGGER)
    return caplog


# ── each reason, on a constructed state ─────────────────────────────────────


@pytest.mark.parametrize("reason, build", [
    ("QUEUED_OR_RUNNING",
     lambda r: setattr(r, "_admission", module._FreshAdmission(1000.0, 1000.0, [7]))),
    ("RETRY_HOLD", lambda r: r._failed_hold_until.update({7: 1010.0})),
    ("NO_VALID_READING", lambda r: r._book_refused.update({7: ((), ())})),
    ("NOT_OWED", lambda r: None),
    ("NOT_DUE", lambda r: (r._throttle_deferred.add(7),
                           r._last_refresh_at.update({7: 999.0}))),
    ("DUE_REASON", lambda r: r._throttle_deferred.add(7)),
])
def test_each_selection_reason_fires_on_its_state(clocks, info, reason, build):
    r = _refresher(min_refresh_interval_s=25.0)
    _owe_input(r, 7, age=30.0)
    build(r)
    r._stamp_wait_sweep("admit", 1000.0, due_reason="DUE_REASON")
    (line,) = _lines(info)
    assert _reason(line) == reason
    assert _field(line, "event") == "7" and _field(line, "outcome") == "50"
    assert _field(line, "seq") == "5" and _field(line, "age_s") == "30.000"
    assert _field(line, "venue") == "polymarket"
    assert _field(line, "run") == r.receipts.run
    assert r.stamp_spans.wait_reasons == {reason: {7}}


def test_a_deferred_cohort_or_withdrawal_is_named(clocks, info):
    r = _refresher()
    _owe_input(r, 7, age=6.0)
    r._throttle_deferred.add(7)
    r._stamp_wait_sweep("admit", 1000.0, excluded={7}, due_reason="LIVE_DEBT_SLOT_BUSY")
    assert [_reason(line) for line in _lines(info)] == ["COHORT_UNFINISHED_OR_WITHDRAWAL"]


def test_a_full_live_debt_allowance_at_the_door_is_slot_busy(clocks, info):
    r = _refresher(min_refresh_interval_s=25.0)
    _owe_input(r, 7, age=12.0)
    r._live_event_ids.add(7)
    r._throttle_deferred.add(7)
    window = module._FreshAdmission(1000.0, 1000.0, [])
    slots = module._admitted_debt_slots()
    window.debts = set(range(100, 100 + slots))
    window.live_debts = set(range(200, 200 + module._admitted_live_debt_slots(slots)))
    r._admission = window
    assert r.admit_fresh([], flush_started=1000.0) == frozenset()
    assert [_reason(line) for line in _lines(info)] == ["LIVE_DEBT_SLOT_BUSY"]
    assert _field(_lines(info)[0], "site") == "admit"
    assert 7 in r._throttle_deferred  # still owed, untouched


async def test_a_spent_debt_budget_in_refresh_is_named(clocks, info):
    r = _refresher(min_refresh_interval_s=25.0)
    _owe_input(r, 7, age=8.0)
    r._throttle_deferred.add(7)
    r._pending_flush_started = 1000.0
    r._pending_fresh_flush = True
    r._pending_attempts = r._pending_attempts_limit
    await r.refresh([], flush_started=1000.0)
    assert [_reason(line) for line in _lines(info)] == ["DEBT_BUDGET_SPENT"]
    assert r._throttle_deferred == {7}


async def test_nothing_owed_on_a_quiet_flush_is_not_owed(clocks, info):
    r = _refresher()
    _owe_input(r, 7, age=20.0)
    await r.refresh_pending(flush_started=1000.0)
    (line,) = _lines(info)
    assert _reason(line) == "NOT_OWED" and _field(line, "site") == "pending"


@pytest.mark.parametrize("disposition, reason", [
    (("no_reading",), "NO_VALID_READING"),
    (("stale", 0.5), "NO_VALID_READING"),
    (("lock",), "ROW_LOCK_SKIPPED"),
    (("unchanged", 0.5), "READ_UNCHANGED"),
    (("error",), "READ_ERROR"),
    (None, "CATALOG_CLOSED"),  # the read returned no group for the event
])
def test_each_read_reason_fires_on_its_disposition(clocks, info, disposition, reason):
    r = _refresher()
    _owe_input(r, 7, age=9.0)
    r._stamp_wait_read([7], {} if disposition is None else {7: disposition})
    (line,) = _lines(info)
    assert _reason(line) == reason and _field(line, "site") == "read"


def test_a_successful_raw_read_does_not_close_an_input_wait(clocks, info):
    r = _refresher()
    _owe_input(r, 7, age=9.0)
    r._throttle_deferred.add(7)
    r._stamp_wait_sweep("admit", 1000.0, due_reason="LIVE_DEBT_SLOT_BUSY")
    r._stamp_wait_read([7], {7: ("stamped", 0.5, "t", None, 42, "live")})
    assert [_reason(line) for line in _lines(info)] == ["LIVE_DEBT_SLOT_BUSY"]
    assert 7 in r.stamp_waits._episodes
    assert "STAMPED" not in r.stamp_spans.wait_reasons


async def test_a_real_refresh_logs_admitted_then_stamped_for_an_aged_live_input(
    monkeypatch, clocks, info,
):
    x = rig(monkeypatch, count=1, statuses={1: "live"})
    x.r.receipts = module.TailReceipts("polymarket")
    _owe_input(x.r, 1, age=40.0, seq=9, outcome=10)
    x.r.receipts.stage([module.InputMark(
        9, 1, 10, 0.5, "price", module._wall() - 40.0, 960.0, None, 1,
    )])
    await x.r.refresh([1], flush_started=1000.0)
    assert x.published == [1]
    lines = _lines(info)
    assert [(_reason(line), _field(line, "site")) for line in lines] == [
        ("ADMITTED", "refresh"), ("STAMPED", "read"),
    ]
    # The closing line carries what the wait saw since the last line.
    assert _field(lines[1], "seen") == "STAMPED:1"
    assert _field(lines[1], "admitted_age_s") == "40.000"


# ── the age budget ──────────────────────────────────────────────────────────


def test_no_line_under_the_budget(clocks, info):
    r = _refresher()
    _owe_input(r, 7, age=module.STAMP_WAIT_BUDGET_S - 0.1)
    _owe_input(r, 8, age=module.STAMP_WAIT_BUDGET_S - 0.1)
    r._stamp_wait_sweep("admit", 1000.0, due_reason="LIVE_DEBT_SLOT_BUSY")
    r._stamp_wait_read([7], {7: ("no_reading",)})
    assert _lines(info) == [] and r.stamp_spans.wait_reasons == {}
    assert "wait_reasons" not in r.stamp_spans.line()
    _advance(clocks, 0.1)  # now exactly at the budget
    r._stamp_wait_sweep("admit", 1000.0, due_reason="LIVE_DEBT_SLOT_BUSY")
    assert sorted(_field(line, "event") for line in _lines(info)) == ["7", "8"]


def test_a_non_live_event_is_never_logged(clocks, info):
    r = _refresher()
    _owe_input(r, 7, age=60.0)
    r.receipts._live_events.discard(7)
    r._stamp_wait_sweep("admit", 1000.0, due_reason="LIVE_DEBT_SLOT_BUSY")
    assert _lines(info) == []


# ── the rate limit ──────────────────────────────────────────────────────────


def test_one_line_per_event_per_minute_and_seen_counts_every_reason(clocks, info):
    r = _refresher()
    _owe_input(r, 7, age=6.0)
    _owe_input(r, 8, age=6.0)
    r._throttle_deferred.update({7, 8})
    r._stamp_wait_sweep("admit", 1000.0, due_reason="LIVE_DEBT_SLOT_BUSY")
    for _ in range(5):
        _advance(clocks, 10.0)
        r._failed_hold_until[7] = clocks["mono"] + 1.0
        r._stamp_wait_sweep("admit", clocks["mono"], due_reason="LIVE_DEBT_SLOT_BUSY")
    assert len(_lines(info)) == 2  # one per event in the first minute
    _advance(clocks, 10.0)  # 60 s after each first line
    r._stamp_wait_sweep("admit", clocks["mono"], due_reason="LIVE_DEBT_SLOT_BUSY")
    lines = [line for line in _lines(info) if _field(line, "event") == "7"]
    assert len(lines) == 2
    assert _field(lines[1], "seen") == "LIVE_DEBT_SLOT_BUSY:1,RETRY_HOLD:5"
    assert _field(lines[1], "age_s") == "66.000"


async def test_the_stamp_that_ends_a_printed_wait_is_always_logged(
    monkeypatch, clocks, info,
):
    x = rig(monkeypatch, count=7, statuses=dict.fromkeys(range(1, 8), "live"))
    r = x.r
    r.receipts = module.TailReceipts("polymarket")
    r.unchanged_restamp_interval_s = 0.0
    _owe_input(r, 7, age=6.0)
    r._throttle_deferred.add(7)
    r._stamp_wait_sweep("admit", 1000.0, due_reason="LIVE_DEBT_SLOT_BUSY")
    _advance(clocks, 3.0)
    r.receipts.stage([module.InputMark(
        5, 7, 50, 0.5, "price", module._wall() - 9.0, 994.0, None, 1,
    )])
    await r.refresh([7], flush_started=clocks["mono"])
    assert not r.receipts._uncovered[7]
    assert [_reason(line) for line in _lines(info)] == ["LIVE_DEBT_SLOT_BUSY", "STAMPED"]
    # The NEXT genuinely covered input is rate-limited from that stamp's line.
    _owe_input(r, 7, age=6.0, seq=11)
    r._stamp_wait_sweep("admit", clocks["mono"], due_reason="LIVE_DEBT_SLOT_BUSY")
    r.receipts.stage([module.InputMark(
        11, 7, 50, 0.6, "price", module._wall() - 6.0, clocks["mono"] - 6.0, None, 2,
    )])
    await r.refresh([7], flush_started=clocks["mono"])
    assert not r.receipts._uncovered[7]
    assert len(_lines(info)) == 2
    assert r.stamp_waits._episodes == {}


def test_episodes_end_when_the_event_stops_waiting(clocks, info):
    r = _refresher()
    _owe_input(r, 7, age=6.0)
    r._stamp_wait_sweep("admit", 1000.0, due_reason="LIVE_DEBT_SLOT_BUSY")
    assert set(r.stamp_waits._episodes) == {7}
    r.receipts._uncovered[7].clear()  # a stamp covered it
    _advance(clocks, 61.0)
    r._stamp_wait_sweep("admit", clocks["mono"], due_reason="LIVE_DEBT_SLOT_BUSY")
    assert r.stamp_waits._episodes == {} and r.stamp_waits._last_line == {}


def test_the_minute_line_counts_events_by_reason_and_resets(clocks):
    r = _refresher()
    for event_id in (7, 8, 9):
        _owe_input(r, event_id, age=7.0)
    r._throttle_deferred.update({8, 9})
    r._last_refresh_at[9] = 999.9
    r.min_refresh_interval_s = 25.0
    for _ in range(3):  # repeated sweeps count each event once
        r._stamp_wait_sweep("admit", 1000.0, due_reason="LIVE_DEBT_SLOT_BUSY")
    assert r.stamp_spans.line().endswith(
        " wait_reasons=LIVE_DEBT_SLOT_BUSY:1,NOT_DUE:1,NOT_OWED:1"
    )
    r.stamp_spans.reset()
    assert "wait_reasons" not in r.stamp_spans.line()


def test_a_failing_classifier_never_raises(clocks, info, monkeypatch):
    r = _refresher()
    _owe_input(r, 7, age=6.0)

    def broken(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(r.receipts, "aged_obligations", broken)
    r._stamp_wait_sweep("admit", 1000.0, due_reason="LIVE_DEBT_SLOT_BUSY")
    r._stamp_wait_read([7], {})
    assert r.stamp_waits.errors == 2 and _lines(info) == []


# ── the switch ──────────────────────────────────────────────────────────────


def test_the_due_check_changes_nothing(clocks):
    r = _refresher(min_refresh_interval_s=25.0)
    r._failed_hold_until[7] = 999.0  # expired
    r._last_refresh_at[7] = 990.0
    assert r._due_unchanged(7, 1000.0) is False
    assert r._failed_hold_until == {7: 999.0} and r._clock_high is None
    assert r._due(7, 1000.0) is False
    assert 7 not in r._failed_hold_until  # `_due` itself still drops it


async def test_a_queued_fresh_reread_keeps_its_uncovered_wait(monkeypatch, clocks, info):
    x = rig(monkeypatch, count=4, statuses=dict.fromkeys(range(1, 5), "live"))
    x.r.receipts = module.TailReceipts("polymarket")
    _owe_input(x.r, 4, age=20.0, seq=4, outcome=40)
    x.r.receipts.stage([module.InputMark(
        4, 4, 40, 0.5, "price", module._wall() - 20.0, 980.0, None, 1,
    )])
    await x.r.refresh(range(1, 5), flush_started=1000.0)
    assert x.r._dispositions[4][6] is False
    assert list(x.r.receipts._uncovered[4]) == [(4, WALL - 20.0, 40)]
    assert [_reason(line) for line in _lines(info)] == ["ADMITTED"]
    assert 4 in x.r.stamp_waits._episodes
    assert x.r.stamp_spans.wait_reasons["READ_UNCOVERED"] == {4}


async def test_a_newer_uncommitted_input_keeps_waiting_after_an_older_stamp(
    monkeypatch, clocks, info,
):
    x = rig(monkeypatch, count=1, statuses={1: "live"})
    x.r.receipts = module.TailReceipts("polymarket")
    _owe_input(x.r, 1, age=20.0, seq=5, outcome=10)
    x.r.receipts.stage([module.InputMark(
        4, 1, 10, 0.5, "price", module._wall() - 30.0, 970.0, None, 1,
    )])
    await x.r.refresh([1], flush_started=1000.0)
    assert list(x.r.receipts._uncovered[1]) == [(5, WALL - 20.0, 10)]
    assert [_reason(line) for line in _lines(info)] == ["ADMITTED"]
    assert 1 in x.r.stamp_waits._episodes
    assert x.r.stamp_spans.wait_reasons["READ_UNCOVERED"] == {1}


async def test_a_broken_wait_sink_cannot_drop_a_due_input(monkeypatch, clocks):
    x = rig(monkeypatch, count=1, statuses={1: "live"})
    x.r.receipts = module.TailReceipts("polymarket")
    _owe_input(x.r, 1, age=20.0, seq=1, outcome=10)
    x.r.adopt_pending({1})

    class BrokenWaitSink(logging.Handler):
        def emit(self, record):
            if "stamp_wait_reason" in record.getMessage():
                raise OSError("diagnostic sink unavailable")

    logger = logging.getLogger(LOGGER)
    old_level = logger.level
    logger.setLevel(logging.INFO)
    handler = BrokenWaitSink()
    logger.addHandler(handler)
    raised = None
    try:
        try:
            await x.r.refresh_pending(flush_started=1000.0)
        except Exception as exc:
            raised = exc
    finally:
        logger.removeHandler(handler)
        logger.setLevel(old_level)
    assert raised is None, (raised, x.r.pending_event_ids(), x.published)
    assert x.published == [1] or 1 in x.r.pending_event_ids()


async def _scenario(monkeypatch, clocks):
    x = rig(monkeypatch, count=3, failure="lock",
            statuses={1: "live", 2: "live", 3: "live"})
    x.r.receipts = module.TailReceipts("polymarket")
    for event_id in (1, 2, 3):
        _owe_input(x.r, event_id, age=30.0, seq=event_id, outcome=event_id * 10)
    x.r.receipts.stage([
        module.InputMark(eid, eid, eid * 10, 0.5, "price", module._wall() - 30.0,
                         970.0, None, 1)
        for eid in (1, 2, 3)
    ])
    x.r._failed_hold_until[3] = 1005.0
    await x.r.refresh([1, 2, 3], flush_started=1000.0)
    _advance(clocks, 2.0)
    await x.r.refresh_pending(flush_started=1002.0)
    r = x.r
    return r, {
        "published": list(x.published),
        "commands": list(x.commands),
        "stats": dict(r.stats),
        "pending": r.pending_event_ids(),
        "lock_retry": set(r._lock_retry),
        "deferred": set(r._throttle_deferred),
        "holds": dict(r._failed_hold_until),
        "last": dict(r._last_refresh_at),
        "dispositions": dict(r._dispositions),
        "clock_high": r._clock_high,
    }


async def test_behaviour_is_identical_with_the_switch_off(monkeypatch, clocks, info):
    r_on, on = await _scenario(monkeypatch, clocks)
    assert [(_field(line, "event"), _reason(line)) for line in _lines(info)] == [
        ("1", "ADMITTED"), ("2", "ADMITTED"), ("3", "RETRY_HOLD"), ("1", "STAMPED"),
    ]
    # Event 2's lock skips (the flush's, then the quiet flush's retry) fell
    # inside its minute: counted for its next line, not lines of their own.
    assert r_on.stamp_spans.wait_reasons["ROW_LOCK_SKIPPED"] == {2}
    assert r_on.stamp_waits._episodes[2]["seen"]["ROW_LOCK_SKIPPED"] == 2
    info.clear()
    clocks.update(mono=1000.0, wall=WALL)
    monkeypatch.setenv(module.STAMP_WAIT_REASON_ENV, "0")
    r_off, off = await _scenario(monkeypatch, clocks)
    assert _lines(info) == [] and r_off.stamp_spans.wait_reasons == {}
    assert "wait_reasons" not in r_off.stamp_spans.line()
    assert on == off
