"""#10090 preview receipt: one line per preview arm per UTC minute (log only).

Pins (speed's 20261029T2043Z directive):
* a minute rollover emits exactly ONE line with the minute's counts, refusals
  by reason and recv→publish percentiles;
* a minute with nothing in it emits a ZERO line (the instrument was on); no
  line at all only when nothing rolled it;
* the hot path gains counter increments only: nothing awaited, no Redis or
  database call, and a failing receipt cannot cost a send.
"""

import ast
from datetime import datetime, timedelta, timezone
import inspect
import json
import logging
import re
import textwrap
from types import SimpleNamespace

import pytest

from app.tasks import live_blend_refresh as lbr
from app.tasks.live_blend_refresh import InputMark, LiveBlendRefresher, TailReceipts
from app.utils import blend_preview
from app.utils import preview_receipt as pr
from app.utils.preview_receipt import PREVIEW_RECEIPT_COUNTS, PreviewReceipt

LOGGER = "app.utils.preview_receipt"
T0 = 1_800_000_000.0 - (1_800_000_000.0 % 60) + 5.0  # 5 s into a UTC minute


class Clock:
    def __init__(self):
        self.mono = 100.0
        self.wall = T0

    def advance(self, seconds):
        self.mono += seconds
        self.wall += seconds


def mark(event_id, recv_mono, seq=1):
    return InputMark(seq=seq, event_id=event_id, outcome_id=7, probability=0.5,
                     kind="price", recv_wall=0.0, recv_mono=recv_mono,
                     venue_ts_ms=None, event_ordinal=seq)


def blend(event_id):
    return {"event_id": event_id, "source": "kalshi", "preview": {"kind": "blend"}}


def lines(caplog):
    return [r.getMessage() for r in caplog.records
            if r.name == LOGGER and "preview-receipt" in r.getMessage()]


def fields(line):
    return dict(re.findall(r"(\w+)=(\S+)", line.split(": preview-receipt ", 1)[1]))


def receipt(clock, counts):
    return PreviewReceipt("kalshi", lambda: dict(counts),
                          mono=lambda: clock.mono, wall=lambda: clock.wall)


def test_a_minute_rollover_writes_exactly_one_line_with_counts_and_percentiles(caplog):
    caplog.set_level(logging.INFO, logger=LOGGER)
    clock = Clock()
    counts = {key: 0 for key in PREVIEW_RECEIPT_COUNTS}
    counts.update({"published": 10, "refused:bucket_full": 4, "capacity:done": 2})
    r = receipt(clock, counts)
    r.roll()  # opens the minute; the baseline is read here
    # Ten events, each committed once and carried by one published blend,
    # 100..1000 ms after its receipt.
    for i in range(1, 11):
        r.committed({i: mark(i, clock.mono)})
        clock.advance(0.1 * i)
        r.published(blend(i), None, ("published",))
        clock.advance(-0.1 * i)
    # Same mark twice counts once; a newer revision before a blend coalesces.
    r.committed({11: mark(11, clock.mono)})
    r.committed({11: mark(11, clock.mono)})
    r.committed({11: mark(11, clock.mono + 0.5, seq=2)})
    # Not charged: a refused publish, a revoke, a blend with nothing awaiting.
    r.committed({12: mark(12, clock.mono)})
    r.published(blend(12), None, ("stale",))
    r.published({"event_id": 12, "preview": {"kind": "revoke"}}, None, ("published",))
    r.published(blend(99), None, ("published",))
    counts.update({"published": 22, "revoked": 3, "ledger_superseded": 1,
                   "refused:bucket_full": 6, "refused:no_base": 1,
                   "refused:local_ticket": 2, "capacity:done": 5, "capacity:error": 2,
                   "no_reading": 4})
    clock.advance(30)
    r.roll()
    assert lines(caplog) == []  # still inside the minute
    clock.advance(30)
    r.roll()
    clock.advance(1)
    r.roll()
    (line,) = lines(caplog)
    assert line.startswith("blend_preview[kalshi]: preview-receipt run=")
    f = fields(line)
    assert f["window_start"] == datetime.fromtimestamp(T0, tz=timezone.utc).isoformat(
        timespec="milliseconds")
    assert float(f["window_s"]) == pytest.approx(55.0)  # watched from T0, not the floor
    assert (f["published"], f["revoked"], f["superseded"], f["no_reading"]) == ("12", "3", "1", "4")
    assert f["refused"] == "bucket_full:2,local_ticket:2,no_base:1"
    assert (f["committed"], f["measured"], f["coalesced"], f["unpreviewed"]) == ("13", "10", "1", "0")
    assert f["latency_clock"] == "mono"
    assert (f["p50_ms"], f["p90_ms"], f["p99_ms"], f["max_ms"]) == ("500", "900", "1000", "1000")
    assert f["worst"] == "10:1000,9:900,8:800"
    assert (f["capacity_passes"], f["capacity_error"], f["capacity_end"]) == ("5", "2", "done:3,error:2")
    assert r.lines == 1


def test_a_quiet_minute_writes_a_zero_line_and_nothing_rolled_writes_nothing(caplog):
    caplog.set_level(logging.INFO, logger=LOGGER)
    clock = Clock()
    r = receipt(clock, {"published": 5})
    clock.advance(600)
    assert lines(caplog) == []  # never rolled: no line, no baseline
    r.roll()
    clock.advance(60)
    r.roll()
    (line,) = lines(caplog)
    f = fields(line)
    assert all(f[k] == "0" for k in ("published", "revoked", "committed", "measured",
                                     "unpreviewed", "capacity_passes", "capacity_error"))
    assert (f["refused"], f["p50_ms"], f["max_ms"], f["worst"], f["capacity_end"]) == (
        "-", "-", "-", "-", "-")
    # A gap of several minutes closes only the open minute: one more line.
    clock.advance(180)
    r.roll()
    assert len(lines(caplog)) == 2


def test_a_committed_revision_no_blend_carried_ages_out_as_unpreviewed(caplog):
    caplog.set_level(logging.INFO, logger=LOGGER)
    clock = Clock()
    r = receipt(clock, {})
    r.committed({1: mark(1, clock.mono), 2: mark(2, clock.mono + 50)})
    clock.advance(61)
    r.roll()
    f = fields(lines(caplog)[0])
    assert (f["committed"], f["unpreviewed"], f["measured"]) == ("2", "1", "0")
    clock.advance(1)
    r.published(blend(2), None, ("published",))  # still awaiting: charged next minute
    clock.advance(60)
    r.roll()
    f = fields(lines(caplog)[1])
    assert (f["committed"], f["measured"], f["max_ms"]) == ("0", "1", "12000")


def test_samples_past_the_cap_keep_an_exact_max_and_count_the_overflow(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=LOGGER)
    monkeypatch.setattr(pr, "PREVIEW_RECEIPT_MAX_SAMPLES", 2)
    clock = Clock()
    r = receipt(clock, {})
    for i, lag in ((1, 0.1), (2, 0.2), (3, 0.9)):
        r.committed({i: mark(i, clock.mono - lag)})
        r.published(blend(i), None, ("published",))
    clock.advance(60)
    r.roll()
    f = fields(lines(caplog)[0])
    assert (f["measured"], f["latency_dropped"], f["max_ms"]) == ("3", "1", "900")
    assert f["worst"].startswith("3:900")


def test_a_replaced_counter_restarts_from_zero_instead_of_going_negative(caplog):
    caplog.set_level(logging.INFO, logger=LOGGER)
    clock = Clock()
    counts = {"refused:full": 9}
    r = receipt(clock, counts)
    r.roll()
    counts["refused:full"] = 2  # a new registry
    clock.advance(60)
    r.roll()
    assert fields(lines(caplog)[0])["refused"] == "full:2"


# ── zero cost on the hot path ────────────────────────────────────────────────

def _awaits(fn) -> bool:
    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    return any(isinstance(node, (ast.Await, ast.AsyncFor, ast.AsyncWith))
               for node in ast.walk(tree))


def test_nothing_on_the_receipt_path_awaits():
    for fn in (PreviewReceipt.committed, PreviewReceipt.published, PreviewReceipt.roll,
               PreviewReceipt._roll, PreviewReceipt._emit,
               LiveBlendRefresher._observe_committed, LiveBlendRefresher._preview_observer,
               LiveBlendRefresher._preview_receipt_counters,
               LiveBlendRefresher._log_preview_capacity_receipt,
               blend_preview.LedgerRegistry._refusal):
        assert not inspect.iscoroutinefunction(fn), fn.__qualname__
        assert not _awaits(fn), fn.__qualname__
    from app.utils.dnpl_authority_registry import AuthorityLedgerRegistry

    for fn in (AuthorityLedgerRegistry._drop, AuthorityLedgerRegistry.propose):
        assert not inspect.iscoroutinefunction(fn) and not _awaits(fn), fn.__qualname__
    # The module imports no I/O client.
    source = inspect.getsource(pr)
    assert "import redis" not in source and "sqlalchemy" not in source


# ── the refresher's wiring ───────────────────────────────────────────────────

@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(lbr, "_mono", lambda: c.mono)
    monkeypatch.setattr(lbr, "_wall", lambda: c.wall)
    return c


def test_only_a_preview_arm_gets_a_receipt():
    assert LiveBlendRefresher("kalshi").preview_receipt is not None
    assert LiveBlendRefresher("polymarket").preview_receipt is not None
    assert LiveBlendRefresher("betting").preview_receipt is None


def test_the_refresher_charges_committed_marks_to_published_blends(caplog, clock, monkeypatch):
    caplog.set_level(logging.INFO, logger=LOGGER)
    registry = SimpleNamespace(refusal_counts={("kalshi", "bucket_full"): 3,
                                               ("polymarket", "bucket_full"): 50})
    monkeypatch.setattr(blend_preview, "_REGISTRY", registry)
    r = LiveBlendRefresher("kalshi")
    receipts = TailReceipts("kalshi")
    r._observe_committed(receipts, {42: mark(42, clock.mono)}, clock.wall, set(), clock.mono)
    clock.advance(0.25)
    observe = r._preview_observer()
    assert observe == r.preview_receipt.published  # no trace: the receipt alone
    observe(blend(42), None, ("published",))
    r.preview_stats["published"] += 1
    registry.refusal_counts[("kalshi", "bucket_full")] = 5
    registry.refusal_counts[("polymarket", "bucket_full")] = 90
    r._log_preview_capacity_receipt("error", r._preview_capacity_counts((), (), None), 0, 0)
    r.stats["no_reading"] += 2
    clock.advance(60)
    r.preview_receipt.roll()
    f = fields(lines(caplog)[0])
    assert (f["published"], f["measured"], f["p50_ms"], f["no_reading"]) == ("1", "1", "250", "2")
    assert f["refused"] == "bucket_full:2"  # this arm's only
    assert (f["capacity_passes"], f["capacity_error"]) == ("1", "1")


def test_a_failing_trace_observer_still_lets_the_receipt_count(clock, monkeypatch):
    r = LiveBlendRefresher("kalshi")
    seen = []

    def broken(frame, meta, reply):
        seen.append(frame["event_id"])
        raise RuntimeError("trace failure")

    monkeypatch.setattr(r, "_stage_hook", lambda name: broken if name == "preview" else None)
    r._observe_committed(TailReceipts("kalshi"), {42: mark(42, clock.mono)},
                         clock.wall, set(), clock.mono)
    blend_preview.observe_publication(r._preview_observer(), blend(42), {}, ["published"])
    assert seen == [42] and r.preview_receipt._measured == 1


def test_a_failing_receipt_costs_neither_the_trace_nor_the_send(clock, monkeypatch):
    r = LiveBlendRefresher("kalshi")
    seen = []
    monkeypatch.setattr(r, "_stage_hook",
                        lambda name: (lambda f, m, rep: seen.append(rep)) if name == "preview" else None)
    monkeypatch.setattr(r.preview_receipt, "published",
                        lambda *a: (_ for _ in ()).throw(RuntimeError("receipt failure")))
    blend_preview.observe_publication(r._preview_observer(), blend(42), {}, ["published"])
    assert seen == [("published",)]
    # Bookkeeping entry points go through `_receipt_call`, which swallows.
    monkeypatch.setattr(r.preview_receipt, "committed",
                        lambda staged: (_ for _ in ()).throw(RuntimeError("receipt failure")))
    r._observe_committed(TailReceipts("kalshi"), {42: mark(42, clock.mono)},
                         clock.wall, set(), clock.mono)


def test_a_quiet_flush_rolls_the_preview_minute(caplog, clock):
    caplog.set_level(logging.INFO, logger=LOGGER)
    import asyncio

    r = LiveBlendRefresher("kalshi")
    r._start_normal_recovery = lambda: None
    r._start_history = lambda: None
    asyncio.run(r.refresh_pending())
    clock.advance(60)
    asyncio.run(r.refresh_pending())
    assert len(lines(caplog)) == 1


# ── the registries' counts ───────────────────────────────────────────────────

def test_ledger_refusals_are_counted_by_source_and_status():
    reg = blend_preview.LedgerRegistry(sources=frozenset({"kalshi", "polymarket"}))
    stats = {}
    reg._refusal(stats, "bucket_full", "propose", "kalshi", 1)
    reg._refusal(stats, "bucket_full", "propose", "kalshi", 2)
    reg._refusal(stats, "fenced", "publish", "polymarket", 3)
    assert reg.refusal_counts == {("kalshi", "bucket_full"): 2, ("polymarket", "fenced"): 1}
    assert stats == {"ledger_refused": 2, "fenced": 1}  # unchanged accounting


def test_the_authority_adapters_local_drops_are_counted_and_still_drop():
    from app.utils.dnpl_authority_registry import AuthorityLedgerRegistry

    reg = AuthorityLedgerRegistry(sources=frozenset({"kalshi"}))
    assert reg.propose(1, "kalshi", value=0.5, event=SimpleNamespace()) == []
    reg._halted = True
    assert reg.propose(1, "kalshi", value=0.5, event=SimpleNamespace()) == []
    assert reg.refusal_counts == {("kalshi", "local_unclaimed"): 1, ("kalshi", "local_halted"): 1}


# ── end to end through the real ledger send (needs a real Redis) ─────────────

from tests.test_blend_preview_ledger_tsp1_10090 import redis_kwargs  # noqa: E402,F401


async def test_a_real_ledger_send_is_charged_to_its_committed_input(
        redis_kwargs, monkeypatch, caplog):  # noqa: F811
    from redis.asyncio import Redis

    from app.utils.live_push import event_channel

    caplog.set_level(logging.INFO, logger=LOGGER)
    clock = Clock()
    monkeypatch.setattr(lbr, "_mono", lambda: clock.mono)
    monkeypatch.setattr(lbr, "_wall", lambda: clock.wall)
    sources = frozenset({"kalshi", "polymarket"})
    monkeypatch.setenv(blend_preview.LEDGER_SOURCES_ENV, "kalshi,polymarket")
    blend_preview.reset_registry_for_tests()
    monkeypatch.setattr(blend_preview, "_REGISTRY", blend_preview.LedgerRegistry(sources=sources))
    client = Redis(**redis_kwargs)
    listener_client = Redis(**redis_kwargs)
    listener = listener_client.pubsub()
    now = datetime.now(timezone.utc)
    event_id = 42
    clock_iso = (now - timedelta(seconds=3)).isoformat()
    bag = {name: {"value": v, "updated_at": clock_iso}
           for name, v in (("kalshi", 0.5), ("polymarket", 0.5), ("betting", 0.55),
                           ("espn", 0.6))}
    event = SimpleNamespace(status="live", espn_win_prob_home=None,
                            opening_home_probability=None, preview_read_ticket=0,
                            sport_key=None, preview_context_at=now, commence_time=now,
                            completed_at=None)
    try:
        await client.set(blend_preview.FENCE_EPOCH_KEY, "41")
        await listener.subscribe(event_channel(event_id))
        await listener.get_message(timeout=0.2)
        refresher = LiveBlendRefresher("kalshi")
        monkeypatch.setattr(refresher, "_client", lambda: client)
        await refresher.claim_preview_display()
        refresher._observe_committed(TailReceipts("kalshi"), {event_id: mark(event_id, clock.mono)},
                                     clock.wall, set(), clock.mono)
        clock.advance(0.4)
        await refresher._publish_previews(blend_preview.registry().propose(
            event_id, "kalshi", value=0.70, event=event, row_sources=bag, row_rev=10,
            observed_basis={"101": (now - timedelta(seconds=1)).timestamp()}, stamped_at=now))
        frame = json.loads((await listener.get_message(
            ignore_subscribe_messages=True, timeout=1))["data"])
        assert frame["preview"]["kind"] == "blend"
        clock.advance(60)
        refresher.preview_receipt.roll()
        f = fields(lines(caplog)[0])
        assert (f["published"], f["measured"], f["max_ms"]) == ("1", "1", "400")
    finally:
        blend_preview.reset_registry_for_tests()
        for c in (listener, listener_client, client):
            await (c.aclose() if hasattr(c, "aclose") else c.close())


# ── the ship's subsets (speed's 20261029T2359Z directive) ───────────────────


def valued(event_id, p, status="live"):
    return {"event_id": event_id, "source": "kalshi", "p": p, "status": status,
            "preview": {"kind": "blend"}}


def charge(r, clock, event_id, p, lag, status="live", seq=1):
    r.committed({event_id: mark(event_id, clock.mono - lag, seq=seq)})
    r.published(valued(event_id, p, status), None, ("published",))


def close_minute(r, clock, caplog):
    clock.advance(60)
    r.roll()
    return fields(lines(caplog)[-1])


def test_live_percentiles_count_only_blends_whose_frame_said_live(caplog):
    caplog.set_level(logging.INFO, logger=LOGGER)
    clock = Clock()
    r = receipt(clock, {})
    charge(r, clock, 1, 0.50, 0.2, status="live")
    charge(r, clock, 2, 0.50, 5.0, status="scheduled")
    charge(r, clock, 3, 0.50, 7.0, status="suspended")
    f = close_minute(r, clock, caplog)
    assert (f["measured"], f["max_ms"]) == ("3", "7000")  # today's fields unchanged
    assert (f["live_measured"], f["live_p50_ms"], f["live_max_ms"]) == ("1", "200", "200")


def test_a_repeat_value_is_not_charged_as_moved_latency(caplog):
    caplog.set_level(logging.INFO, logger=LOGGER)
    clock = Clock()
    r = receipt(clock, {})
    charge(r, clock, 1, 0.61, 0.1)              # first blend of the event: first
    charge(r, clock, 1, 0.61, 9.0, seq=2)       # same value again: a repeat
    charge(r, clock, 1, 0.64, 0.3, seq=3)       # moved
    charge(r, clock, 2, 0.40, 0.2, status="scheduled")  # first, pre-game
    charge(r, clock, 2, 0.45, 0.8, status="scheduled", seq=2)  # moved, not live
    f = close_minute(r, clock, caplog)
    assert (f["measured"], f["first"], f["repeat"]) == ("5", "2", "1")
    assert (f["moved_measured"], f["moved_p50_ms"], f["moved_max_ms"]) == ("2", "300", "800")
    assert (f["live_moved_measured"], f["live_moved_max_ms"]) == ("1", "300")
    assert f["live_moved_worst"] == "1:300"
    assert f["max_ms"] == "9000"  # the repeat is still in today's fields


def test_the_last_value_outlives_the_minute_and_uncharged_blends_update_it(caplog):
    caplog.set_level(logging.INFO, logger=LOGGER)
    clock = Clock()
    r = receipt(clock, {})
    charge(r, clock, 1, 0.50, 0.1)
    close_minute(r, clock, caplog)
    # A blend with nothing awaiting still moves the remembered value.
    r.published(valued(1, 0.55), None, ("published",))
    charge(r, clock, 1, 0.55, 0.4, seq=2)       # equal to that blend: repeat
    charge(r, clock, 1, 0.58, 0.6, seq=3)       # moved across the minute line
    # A refused send changes nothing.
    r.committed({1: mark(1, clock.mono, seq=4)})
    r.published(valued(1, 0.90), None, ("stale",))
    f = close_minute(r, clock, caplog)
    assert (f["first"], f["repeat"], f["moved_measured"], f["moved_max_ms"]) == ("0", "1", "1", "600")


def test_a_mark_older_than_the_await_window_is_purged_when_charged(caplog):
    caplog.set_level(logging.INFO, logger=LOGGER)
    clock = Clock()
    r = receipt(clock, {})
    charge(r, clock, 5, 0.50, 0.1)  # first; opens the minute at +5 s
    clock.advance(56)
    r.roll()                         # +61: the first minute closes
    r.committed({5: mark(5, clock.mono, seq=2)})  # just after the close
    clock.advance(59)
    r.roll()           # +120: this close keeps it (59 s old), as before
    clock.advance(10)  # 69 s old: before this fix, charged as 69000 ms
    r.published(valued(5, 0.70), None, ("published",))
    f = close_minute(r, clock, caplog)
    assert (f["measured"], f["unpreviewed"], f["max_ms"]) == ("0", "1", "-")
    assert (f["moved_measured"], f["live_moved_max_ms"]) == ("0", "-")
    # The blend still published: the next one compares against 0.70.
    charge(r, clock, 5, 0.70, 0.1, seq=3)
    f = close_minute(r, clock, caplog)
    assert (f["measured"], f["repeat"], f["moved_measured"]) == ("1", "1", "0")


def test_a_frame_without_a_value_is_never_moved(caplog):
    caplog.set_level(logging.INFO, logger=LOGGER)
    clock = Clock()
    r = receipt(clock, {})
    charge(r, clock, 1, None, 0.1)
    charge(r, clock, 1, 0.5, 0.1, seq=2)
    charge(r, clock, 1, None, 0.1, seq=3)
    f = close_minute(r, clock, caplog)
    assert (f["first"], f["repeat"], f["moved_measured"]) == ("1", "2", "0")


def test_the_remembered_values_are_bounded(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=LOGGER)
    monkeypatch.setattr(pr, "PREVIEW_RECEIPT_MAX_EVENTS", 2)
    clock = Clock()
    r = receipt(clock, {})
    for eid in (1, 2, 3):  # the third clears the memory, then is remembered
        r.published(valued(eid, 0.5), None, ("published",))
    assert r._last_value == {3: 0.5}
    charge(r, clock, 1, 0.6, 0.1)
    f = close_minute(r, clock, caplog)
    assert (f["first"], f["moved_measured"]) == ("1", "0")


def test_observation_timeouts_and_read_required_phases_reach_the_line(caplog, clock, monkeypatch):
    caplog.set_level(logging.INFO, logger=LOGGER)
    reg = blend_preview.LedgerRegistry(sources=frozenset({"kalshi", "polymarket"}))
    monkeypatch.setattr(blend_preview, "_REGISTRY", reg)
    r = LiveBlendRefresher("kalshi")
    r.preview_receipt.roll()
    stats = {}
    reg._refusal(stats, "read_required", "propose", "kalshi", 1)
    reg._refusal(stats, "read_required", "propose", "kalshi", 2)
    reg._refusal(stats, "read_required", "retire_missing", "kalshi", 3)
    reg._refusal(stats, "read_required", "propose", "polymarket", 4)
    reg._refusal(stats, "bucket_full", "propose", "kalshi", 5)
    r.preview_stats["observation_timeouts"] = 4
    clock.advance(60)
    r.preview_receipt.roll()
    f = fields(lines(caplog)[0])
    assert f["refused"] == "bucket_full:1,read_required:3"  # unchanged field
    assert f["read_required"] == "propose:2,retire_missing:1"  # this arm's only
    assert (f["observation_timeouts"], f["publish_errors"]) == ("4", "0")
    assert reg.read_required_phases == {("kalshi", "propose"): 2,
                                        ("kalshi", "retire_missing"): 1,
                                        ("polymarket", "propose"): 1}


def test_the_line_format_is_pinned():
    # Today's fields first, in today's order (earlier lines stay comparable);
    # the ship's subsets appended after capacity_end.
    keys = re.findall(r"(\w+)=", pr.PREVIEW_RECEIPT_FORMAT)
    assert keys == [
        "run", "window_start", "window_s", "published", "revoked", "recomposed",
        "superseded", "withdrawn", "fenced", "authority_refused", "publish_errors",
        "no_reading", "refused", "committed", "measured", "coalesced", "unpreviewed",
        "latency_clock", "p50_ms", "p90_ms", "p99_ms", "max_ms", "latency_dropped", "worst",
        "capacity_passes", "capacity_error", "capacity_end",
        "observation_timeouts", "read_required", "first", "repeat",
        "live_measured", "live_p50_ms", "live_p90_ms", "live_p99_ms", "live_max_ms",
        "moved_measured", "moved_p50_ms", "moved_p90_ms", "moved_p99_ms", "moved_max_ms",
        "live_moved_measured", "live_moved_p50_ms", "live_moved_p90_ms",
        "live_moved_p99_ms", "live_moved_max_ms", "live_moved_worst",
    ]
    assert pr.PREVIEW_RECEIPT_FORMAT.startswith("blend_preview[%s]: preview-receipt run=%s ")
