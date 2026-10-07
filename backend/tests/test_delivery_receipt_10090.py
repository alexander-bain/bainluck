"""#10090 — the per-minute delivery receipt: what one live game's consumer
received, and which published revision carried it.

WHY THIS FILE EXISTS. Alex, 2026-10-06: incoming rate, browser arrival rate and
lag are three separate numbers, and "5 Kalshi revisions in 112 s" could not be
split into a quiet venue, coalesced inputs or suppressed ones. The page capture
counts frames (`rev`, `source_value`, `updated_at`), never inputs. The Kalshi
consumer kept no per-input marks at all; Polymarket's #837 receipt logs hold
chains, coalesced, not an input count. So nothing linked a consumer input to the
`rev` the browser received.

The receipt line, one per source × live event × UTC minute:
  raw       venue messages for this game's contracts, before the price policy
  accepted  prices the policy kept, split per outcome into changed / repeats /
            first (no prior in this run)
  stamps    rev@stamped_at@newest_recv@oldest_recv@covered for every committed
            stamp — `stamped_at` is the SSE frame's `updated_at` byte for byte,
            so the offline analyzer joins on (source, event, rev) exactly.

Controls: an event never stamped `live` writes no line (non-vacuity partner of
the live case); inputs after the committed one are NOT covered by that stamp;
the real Kalshi consumer, which used to attach no receipts, now carries marks
from `handle_ticker` into the stamp.
"""

import asyncio
import json
import logging

import pytest
import websockets

import app.services.kalshi_ws as kalshi_svc
import app.tasks.kalshi_ws as kalshi_task
import app.tasks.live_blend_refresh as blend_mod
from app.tasks.live_blend_refresh import LiveBlendRefresher, TailReceipts
from tests.test_ws_flush_retry_q491 import (
    EVENT_ID,
    KALSHI_OUTCOME_ID,
    KALSHI_SLATE,
    KALSHI_TICKER,
    _install_slate,
)

LOGGER = "app.tasks.live_blend_refresh"
EPOCH = 1_791_321_600.0  # 2026-10-06T21:20:00Z, a minute boundary


class _Clock:
    def __init__(self, t=0.0):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture
def clock(monkeypatch):
    c = _Clock()
    monkeypatch.setattr(blend_mod, "_mono", c)
    monkeypatch.setattr(blend_mod, "_wall", lambda: EPOCH + c.t)
    return c


@pytest.fixture(autouse=True)
def _info(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=LOGGER)
    # Process-local hand-off: every test starts from its own previous run.
    monkeypatch.setattr(blend_mod, "_live_handoff", {})


def _lines(caplog):
    out = []
    for rec in caplog.records:
        msg = rec.getMessage()
        if "delivery-receipt run=" in msg:
            out.append(dict(
                kv.split("=", 1) for kv in msg.split("delivery-receipt ", 1)[1].split()
            ))
    return out


def _stamps(line):
    if line["stamps"] == "-":
        return []
    return [dict(zip(("rev", "stamped_at", "newest", "oldest", "covered"), s.split("@")))
            for s in line["stamps"].split(";")]


def _refresher(status="live", previously_live=(1,)):
    """A real refresher whose batch stamps without a database; each stamp
    publishes the next `rev` with the given event status. `previously_live`
    is what the previous consumer run handed over (`close_all`)."""
    blend_mod._live_handoff["kalshi"] = frozenset(previously_live)
    r = LiveBlendRefresher("kalshi", min_refresh_interval_s=2.0)
    r.receipts = TailReceipts("kalshi")
    revs = {"n": 100}
    statuses = {"now": status}

    async def _batch(event_ids, now):
        for eid in event_ids:
            r._last_refresh_at[eid] = now
            revs["n"] += 1
            r._dispositions[eid] = (
                "stamped", 0.61, f"2026-10-06T21:20:{now:06.3f}+00:00",
                r._last_written_value.get(eid), revs["n"], statuses["now"],
            )
            r._last_written_value[eid] = 0.61
            r._last_write_at[eid] = now

    r._refresh_batch = _batch
    return r, statuses


async def _flush(r, clock, t, inputs, event_id=1):
    """The socket's order: messages (raw), accepted inputs under the lock, the
    commit, `stage`, then `refresh`."""
    clock.t = t
    marks = []
    for outcome_id, p in inputs:
        r.receipts.note_raw(event_id)
        if p is not None:  # None = a message the price policy refused
            marks.append(r.receipts.note_input(event_id, outcome_id, p, "ticker"))
    r.receipts.stage(marks)
    await r.refresh([event_id])
    return marks


class TestTheMinuteLine:
    @pytest.mark.asyncio
    async def test_counts_and_the_stamps_that_carried_them(self, clock, caplog):
        r, _ = _refresher()
        await _flush(r, clock, 1.0, [(11, 0.60), (12, 0.40), (11, None)])
        await _flush(r, clock, 3.0, [(11, 0.60), (11, 0.61)])
        clock.t = 61.0
        await r.refresh_pending()  # a quiet flush in the next minute closes this one

        (line,) = _lines(caplog)
        assert line["event"] == "1" and line["window_start"].startswith("2026-10-06T21:20:00")
        assert line["window_s"] == "60.000"
        assert (line["raw"], line["accepted"]) == ("5", "4")
        assert (line["changed"], line["repeats"], line["first"]) == ("1", "1", "2")
        assert line["outcomes"] == "11:3:1:1:1,12:1:0:0:1"
        first, second = _stamps(line)
        assert (first["rev"], first["covered"]) == ("101", "2")
        assert (second["rev"], second["covered"]) == ("102", "2")
        assert first["stamped_at"] == "2026-10-06T21:20:01.000+00:00"
        assert first["newest"].startswith("2026-10-06T21:20:01")
        assert line["stamps_dropped"] == "0"

    @pytest.mark.asyncio
    async def test_an_event_never_stamped_live_writes_no_line(self, clock, caplog):
        """Upcoming games and futures stamp too; only a live game is receipted."""
        r, _ = _refresher(status="scheduled", previously_live=())
        await _flush(r, clock, 1.0, [(11, 0.60)])
        clock.t = 61.0
        await r.refresh_pending()
        assert _lines(caplog) == []

    @pytest.mark.asyncio
    async def test_the_minute_a_game_goes_final_is_still_written(self, clock, caplog):
        r, statuses = _refresher()
        await _flush(r, clock, 1.0, [(11, 0.60)])
        statuses["now"] = "final"
        await _flush(r, clock, 3.0, [(11, 0.99)])
        clock.t = 61.0
        await r.refresh_pending()
        (line,) = _lines(caplog)
        assert len(_stamps(line)) == 2
        # ...and the NEXT minute, final throughout, writes nothing.
        await _flush(r, clock, 63.0, [(11, 0.99)])
        clock.t = 121.0
        await r.refresh_pending()
        assert len(_lines(caplog)) == 1


class TestCoverage:
    @pytest.mark.asyncio
    async def test_an_input_after_the_committed_one_waits_for_the_next_stamp(
        self, clock, caplog,
    ):
        r, _ = _refresher()
        clock.t = 1.0
        committed = r.receipts.note_input(1, 11, 0.60, "ticker")
        later = r.receipts.note_input(1, 11, 0.62, "ticker")  # buffered mid-write
        r.receipts.stage([committed])
        await r.refresh([1])
        clock.t = 3.0
        r.receipts.stage([later])
        await r.refresh([1])
        clock.t = 61.0
        await r.refresh_pending()
        first, second = _stamps(_lines(caplog)[0])
        assert first["covered"] == "1" and second["covered"] == "1"

    @pytest.mark.asyncio
    async def test_a_throttled_price_is_covered_by_the_deferred_stamp(self, clock, caplog):
        r, _ = _refresher()
        await _flush(r, clock, 1.0, [(11, 0.60)])
        await _flush(r, clock, 1.5, [(11, 0.61)])  # both inside the 2 s floor
        await _flush(r, clock, 1.8, [(11, 0.62)])
        clock.t = 3.5
        await r.refresh_pending()
        clock.t = 61.0
        await r.refresh_pending()
        stamps = _stamps(_lines(caplog)[0])
        assert [s["covered"] for s in stamps] == ["1", "2"]
        assert stamps[1]["oldest"] < stamps[1]["newest"]


class TestBounds:
    @pytest.mark.asyncio
    async def test_the_stamp_list_is_capped_and_the_overflow_counted(
        self, clock, caplog, monkeypatch,
    ):
        monkeypatch.setattr(blend_mod, "DELIVERY_RECEIPT_MAX_STAMPS", 2)
        r, _ = _refresher()
        for i in range(4):
            await _flush(r, clock, 1.0 + 2 * i, [(11, 0.60 + i / 100)])
        clock.t = 61.0
        await r.refresh_pending()
        (line,) = _lines(caplog)
        assert len(_stamps(line)) == 2 and line["stamps_dropped"] == "2"

    @pytest.mark.asyncio
    async def test_a_crowded_minute_writes_the_busiest_games_and_counts_the_rest(
        self, clock, caplog, monkeypatch,
    ):
        monkeypatch.setattr(blend_mod, "DELIVERY_RECEIPT_MAX_EVENTS", 2)
        r, _ = _refresher(previously_live=(1, 2, 3))
        await _flush(r, clock, 1.0, [(11, 0.6)], event_id=1)
        await _flush(r, clock, 1.1, [(21, 0.6), (21, 0.61), (21, 0.62)], event_id=2)
        await _flush(r, clock, 1.2, [(31, 0.6), (31, 0.61)], event_id=3)
        clock.t = 61.0
        await r.refresh_pending()
        assert sorted(x["event"] for x in _lines(caplog)) == ["2", "3"]
        (overflow,) = [m.getMessage() for m in caplog.records
                       if "delivery-receipt-overflow" in m.getMessage()]
        assert "events_dropped=1 dropped=1" in overflow

    @pytest.mark.asyncio
    async def test_the_exit_writes_the_partial_minute_with_its_real_length(
        self, clock, caplog,
    ):
        r, _ = _refresher()
        await _flush(r, clock, 1.0, [(11, 0.60)])
        clock.t = 30.5
        r.receipts.close_all("exit")
        (line,) = _lines(caplog)
        assert line["window_s"] == "30.500"
        assert "delivery_lines=1" in [
            m.getMessage() for m in caplog.records if "tail-receipt summary" in m.getMessage()
        ][0]


# ------------------------------------------------ the real Kalshi consumer ----


class _TimedFrames:
    def __init__(self, frames):
        self._frames = list(frames)

    async def send(self, _payload):
        return None

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._frames:
            delay, frame = self._frames.pop(0)
            await asyncio.sleep(delay)
            return frame
        await asyncio.sleep(3600)
        raise StopAsyncIteration  # pragma: no cover


def _ticker(**msg):
    return json.dumps({"type": "ticker", "msg": {"market_ticker": KALSHI_TICKER, **msg}})


class TestTheRealKalshiConsumer:
    @pytest.mark.asyncio
    async def test_ticker_inputs_reach_the_stamp_that_published_them(
        self, monkeypatch, caplog,
    ):
        seen = {}

        class _Recording(LiveBlendRefresher):
            def __init__(self, source, **kw):
                super().__init__(source, min_refresh_interval_s=0.01, **kw)
                seen["refresher"] = self
                self._rev = 500

            async def _refresh_batch(
                self, event_ids, now, *, prepared=None, on_committed=None
            ):
                for eid in event_ids:
                    self._last_refresh_at[eid] = now
                    self._rev += 1
                    self._dispositions[eid] = (
                        "stamped", 0.5, f"stamp-{self._rev}",
                        self._last_written_value.get(eid), self._rev, "live",
                    )
                    self._last_written_value[eid] = 0.5
                    self._last_write_at[eid] = now
                if on_committed is not None:
                    on_committed(event_ids)

        monkeypatch.setenv("KALSHI_API_KEY_ID", "test-key")
        monkeypatch.setenv("KALSHI_RSA_PRIVATE_KEY", "test-secret")
        monkeypatch.setattr(kalshi_svc, "_load_rsa_key", lambda: object())
        monkeypatch.setattr(kalshi_svc, "_sign_ws_request", lambda _k, _i: {})
        monkeypatch.setattr(kalshi_task, "SUBSCRIPTION_REFRESH_SECONDS", 0.8)
        monkeypatch.setattr(kalshi_task, "PRICE_FLUSH_SECONDS", 0.02)
        monkeypatch.setattr(blend_mod, "LiveBlendRefresher", _Recording)
        blend_mod._live_handoff["kalshi"] = frozenset({EVENT_ID})  # the previous run
        frames = [
            (0.0, _ticker(yes_bid_dollars="0.40", yes_ask_dollars="0.44")),
            (0.15, _ticker(yes_bid_dollars="0.40", yes_ask_dollars="0.44")),  # repeat
            (0.15, _ticker(yes_bid_dollars="0.40")),  # one-sided: raw, not a price
            (0.15, _ticker(yes_bid_dollars="0.46", yes_ask_dollars="0.50")),
        ]

        def _connect(*_a, **_kw):
            class _Ctx:
                async def __aenter__(self):
                    return _TimedFrames(frames)

                async def __aexit__(self, *_exc):
                    return False

            return _Ctx()

        monkeypatch.setattr(websockets, "connect", _connect)
        writes: list = []
        _install_slate(monkeypatch, KALSHI_SLATE, writes, {"fail_writes": 0, "failed": 0})

        await kalshi_task._run_kalshi_ws_consumer()

        assert seen["refresher"].receipts is not None
        lines = [x for x in _lines(caplog) if x["event"] == str(EVENT_ID)]
        assert lines, [m.getMessage() for m in caplog.records][-20:]
        total = {k: sum(int(x[k]) for x in lines)
                 for k in ("raw", "accepted", "changed", "repeats", "first")}
        assert total == {"raw": 4, "accepted": 3, "changed": 1, "repeats": 1, "first": 1}
        stamps = [s for x in lines for s in _stamps(x)]
        assert sum(int(s["covered"]) for s in stamps) == 3
        assert all(s["stamped_at"] == f"stamp-{s['rev']}" for s in stamps)
        assert all(s["newest"] != "-" for s in stamps if s["covered"] != "0")
        assert {o.split(":")[0] for x in lines for o in x["outcomes"].split(",")} == {
            str(KALSHI_OUTCOME_ID)
        }


class TestTheRealPolymarketConsumer:
    @pytest.mark.asyncio
    async def test_a_refused_wide_book_is_raw_but_not_an_input(
        self, monkeypatch, caplog,
    ):
        """Two book messages for the game's token: a tradeable one (raw and an
        input) and a wide one #1578 refuses (raw only)."""
        import app.tasks.polymarket_ws as poly_task
        from tests.test_live_blend_tail_receipt_837 import _install_timed_socket
        from tests.test_ws_flush_retry_q491 import (
            POLY_SLATE, YES_OUTCOME_ID, YES_TOKEN, _poly_frame,
        )

        class _Recording(LiveBlendRefresher):
            def __init__(self, source, **kw):
                super().__init__(source, min_refresh_interval_s=0.01, **kw)
                self._rev = 700

            async def _refresh_batch(
                self, event_ids, now, *, prepared=None, on_committed=None
            ):
                for eid in event_ids:
                    self._last_refresh_at[eid] = now
                    self._rev += 1
                    self._dispositions[eid] = (
                        "stamped", 0.7, f"stamp-{self._rev}",
                        self._last_written_value.get(eid), self._rev, "live",
                    )
                    self._last_written_value[eid] = 0.7
                    self._last_write_at[eid] = now
                if on_committed is not None:
                    on_committed(event_ids)

        monkeypatch.setattr(poly_task, "SUBSCRIPTION_REFRESH_SECONDS", 0.8)
        monkeypatch.setattr(poly_task, "PRICE_FLUSH_SECONDS", 0.02)
        monkeypatch.setattr(blend_mod, "LiveBlendRefresher", _Recording)
        blend_mod._live_handoff["polymarket"] = frozenset({EVENT_ID})
        _install_timed_socket(monkeypatch, [
            (0.0, _poly_frame("best_bid_ask", YES_TOKEN, best_bid="0.68", best_ask="0.72")),
            (0.15, _poly_frame("best_bid_ask", YES_TOKEN, best_bid="0.10", best_ask="0.90")),
        ])
        writes: list = []
        _install_slate(monkeypatch, POLY_SLATE, writes, {"fail_writes": 0, "failed": 0})

        await poly_task._run_polymarket_ws_consumer()

        lines = [x for x in _lines(caplog) if x["event"] == str(EVENT_ID)]
        assert lines, [m.getMessage() for m in caplog.records][-20:]
        assert sum(int(x["raw"]) for x in lines) == 2
        assert sum(int(x["accepted"]) for x in lines) == 1
        outcomes = {o.split(":")[0] for x in lines for o in x["outcomes"].split(",")}
        assert outcomes == {str(YES_OUTCOME_ID)}
        assert sum(int(s["covered"]) for x in lines for s in _stamps(x)) == 1


class TestTheLiveSetSurvivesARecycle:
    @pytest.mark.asyncio
    async def test_a_game_first_seen_live_this_run_counts_from_its_first_stamp(
        self, clock, caplog,
    ):
        r, _ = _refresher(previously_live=())
        await _flush(r, clock, 1.0, [(11, 0.60)])   # not yet known live: uncounted
        await _flush(r, clock, 3.0, [(11, 0.61)])
        clock.t = 61.0
        await r.refresh_pending()
        (line,) = _lines(caplog)
        assert (line["accepted"], line["first"]) == ("1", "1")
        assert [s["covered"] for s in _stamps(line)] == ["0", "1"]

    @pytest.mark.asyncio
    async def test_close_all_hands_the_live_games_to_the_next_run(self, clock, caplog):
        r, _ = _refresher(previously_live=())
        await _flush(r, clock, 1.0, [(11, 0.60)])
        r.receipts.close_all("recycle_reset")
        nxt = TailReceipts("kalshi")
        clock.t = 70.0
        nxt.note_input(1, 11, 0.62, "ticker")
        clock.t = 125.0
        nxt.roll()
        assert [x["accepted"] for x in _lines(caplog)] == ["0", "1"]


class TestCoverageNeverClaimsUnwatchedSeconds:
    """Root's independent repro (clob-delivery-metrics-root-review/
    test_first_partial_window.py, 2026-10-06): a consumer created 57 s into a
    minute logged window_s=60 for 3 s of watching — 3/min instead of 60/min."""

    def test_a_run_that_starts_mid_minute_reports_only_what_it_watched(
        self, monkeypatch, caplog,
    ):
        now = [57.0]
        monkeypatch.setattr(blend_mod, "_wall", lambda: now[0])
        monkeypatch.setattr(blend_mod, "_mono", lambda: now[0])
        blend_mod._live_handoff["kalshi"] = frozenset({42})
        receipt = TailReceipts("kalshi")
        for instant in (57.0, 58.0, 59.0):
            now[0] = instant
            receipt.note_raw(42)
            receipt.note_input(42, 7, 0.5, "ticker")
        now[0] = 60.0
        receipt.roll()
        (line,) = _lines(caplog)
        assert line["raw"] == line["accepted"] == "3" and line["repeats"] == "2"
        assert line["window_s"] == "3.000"
        assert line["window_start"] == "1970-01-01T00:00:57.000+00:00"

    @pytest.mark.asyncio
    async def test_a_game_that_goes_live_mid_minute_starts_at_its_first_live_stamp(
        self, clock, caplog,
    ):
        r, _ = _refresher(previously_live=())
        await _flush(r, clock, 20.0, [(11, 0.60)])  # first live stamp at :20
        await _flush(r, clock, 30.0, [(11, 0.61)])
        clock.t = 61.0
        await r.refresh_pending()
        (line,) = _lines(caplog)
        assert line["window_start"] == "2026-10-06T21:20:20.000+00:00"
        assert line["window_s"] == "40.000"

    def test_the_exit_partial_minute_starts_where_watching_did(self, monkeypatch, caplog):
        now = [130.0]
        monkeypatch.setattr(blend_mod, "_wall", lambda: now[0])
        monkeypatch.setattr(blend_mod, "_mono", lambda: now[0])
        blend_mod._live_handoff["kalshi"] = frozenset({42})
        receipt = TailReceipts("kalshi")
        receipt.note_input(42, 7, 0.5, "ticker")
        now[0] = 140.0
        receipt.close_all("exit")
        (line,) = _lines(caplog)
        assert (line["window_start"], line["window_s"]) == ("1970-01-01T00:02:10.000+00:00", "10.000")
