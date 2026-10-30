"""#10090 decision J = A — the server half of ``confirmed_at``.

SHIP. On a live game page the "seconds ago" counter stays at a few seconds
while the markets keep confirming the price, so a steady price between points
no longer looks like a 25-second delay; and a page opened on a steady price
gets its clock with the first heartbeat instead of waiting ~11 s for a frame.

THE GUARD UNDER TEST (Alex's rule): ``confirmed_at`` never advances while a
newer, different price is held or unpublished. Each guard below has a red
partner: the same input stream with the guard's condition removed advances.
"""

import asyncio
import json
from types import SimpleNamespace

import pytest

from app.utils import confirmed_at as ca
from app.utils.confirmed_at import ConfirmedAt, ConfirmedReads, combine

E, HOME, AWAY, PROP = 7, 70, 71, 79
STAMPED_AT = "2026-10-29T23:00:05.000000+00:00"
STAMP_WALL = 1_793_314_805.0  # STAMPED_AT as epoch seconds


class _Clock:
    def __init__(self, mono=100.0, wall=STAMP_WALL):
        self.mono, self.wall = mono, wall

    def tick(self, s):
        self.mono += s
        self.wall += s


@pytest.fixture
def clock():
    return _Clock()


def _tracker(clock, **kw):
    kw.setdefault("preview_ttl_s", 60.0)
    return ConfirmedAt("kalshi", mono=lambda: clock.mono, wall=lambda: clock.wall, **kw)


def _rows(**prices):
    return [SimpleNamespace(id=int(k[1:]), current_probability=v) for k, v in prices.items()]


def _publish(t, kind="stamped", status="live", acked=True, rev=9, **prices):
    """One committed batch for E whose reading blended ``prices``. A stamp's
    frame is then acknowledged by the publisher (``acked``), as
    `LiveBlendRefresher._publish_prices` reports it (lane1 R2): only then is
    it on readers' screens."""
    t.begin([E])
    if prices:
        t.note_basis(E, _rows(**prices))
    disposition = (("stamped", 0.6, STAMPED_AT, None, rev, status) if kind == "stamped"
                   else (kind, 0.6))
    t.resolved(E, disposition)
    if kind == "stamped" and acked:
        t.published({(E, rev)})


def _state(t):
    return t._events[E]


def _c(t):
    return _state(t).confirmed


# ── the tracker: agreement advances, a held change freezes ──────────────────

class TestAgreement:
    def test_an_unchanged_input_advances_confirmed_at(self, clock):
        t = _tracker(clock)
        t.note_input(E, HOME, 0.6, clock.wall)
        _publish(t, o70=0.6)
        assert _c(t) == STAMP_WALL  # the publication itself
        clock.tick(10)
        t.note_input(E, HOME, 0.6000001, clock.wall)  # same at 6 places
        assert _c(t) == clock.wall
        assert _state(t).held_since is None

    def test_nothing_is_confirmed_before_this_run_published(self, clock):
        t = _tracker(clock)
        t.note_input(E, HOME, 0.6, clock.wall)
        assert _c(t) is None
        # ...and the unknown state is reported as a hold, for a bounded time.
        assert t.report(_state(t), clock.wall)[1] == int(clock.wall * 1000)
        clock.tick(ca.UNKNOWN_HOLD_S + 1)
        assert t.report(_state(t), clock.wall)[1] is None

    def test_a_held_different_price_does_not_advance_until_it_publishes(self, clock):
        t = _tracker(clock)
        _publish(t, o70=0.6)
        clock.tick(1)
        t.note_input(E, HOME, 0.62, clock.wall)  # the venue moved; not published
        moved_at = clock.wall
        before = _c(t)
        for _ in range(5):  # the market keeps confirming the NEW price
            clock.tick(1)
            t.note_input(E, HOME, 0.62, clock.wall)
            assert _c(t) == before
        assert _state(t).held_since == moved_at
        assert t.report(_state(t), clock.wall) == (int(before * 1000), int(moved_at * 1000))
        # The change publishes: the stamp blended 0.62.
        clock.tick(1)
        t.begin([E])
        t.note_basis(E, _rows(o70=0.62))
        t.resolved(E, ("stamped", 0.62, ca.iso(clock.wall), 0.6, 10, "live"))
        # Committed, not yet acknowledged by the publisher: still held (R2).
        assert _c(t) == before and _state(t).held_since is not None
        t.published({(E, 10)})
        assert _state(t).held_since is None
        assert _c(t) == clock.wall > before  # the publication itself
        clock.tick(1)
        t.note_input(E, HOME, 0.62, clock.wall)
        assert _c(t) == clock.wall

    @pytest.mark.parametrize("guarded", [True, False])
    def test_red_partner_without_the_guard_the_same_stream_advances(self, clock, guarded):
        """The same input stream through the real check and through one that
        ignores the newest inputs: only the guard keeps it frozen."""
        class NoGuard(ConfirmedAt):
            def agrees(self, state):
                return isinstance(state.pub, dict)

        cls = ConfirmedAt if guarded else NoGuard
        t = cls("kalshi", mono=lambda: clock.mono, wall=lambda: clock.wall, preview_ttl_s=60.0)
        _publish(t, o70=0.6, o71=0.4)
        before = _c(t)
        clock.tick(1)
        t.note_input(E, HOME, 0.62, clock.wall)  # held: not published
        clock.tick(1)
        t.note_input(E, AWAY, 0.4, clock.wall)   # the other leg repeats
        assert (_c(t) == before) is guarded

    def test_a_different_price_on_any_published_leg_holds_the_event(self, clock):
        t = _tracker(clock)
        _publish(t, o70=0.6, o71=0.4)
        clock.tick(1)
        t.note_input(E, AWAY, 0.45, clock.wall)
        before = _c(t)
        clock.tick(1)
        t.note_input(E, HOME, 0.6, clock.wall)  # HOME agrees, AWAY does not
        assert _c(t) == before
        assert _state(t).held_since is not None

    def test_the_newest_input_decides_a_flicker_never_published(self, clock):
        """0.6 → 0.62 → 0.6 inside one flush, no batch took 0.62: the newest
        venue price equals what readers see, so it confirms."""
        t = _tracker(clock)
        _publish(t, o70=0.6)
        clock.tick(1)
        t.note_input(E, HOME, 0.62, clock.wall)
        clock.tick(0.1)
        t.note_input(E, HOME, 0.6, clock.wall)
        assert _c(t) == clock.wall

    def test_a_leg_the_reading_did_not_blend_neither_confirms_nor_holds(self, clock):
        t = _tracker(clock)
        _publish(t, o70=0.6)
        before = _c(t)
        clock.tick(1)
        t.note_input(E, PROP, 0.3, clock.wall)
        assert _c(t) == before and _state(t).held_since is None
        t.note_input(E, PROP, 0.31, clock.wall)
        assert _c(t) == before and _state(t).held_since is None

    def test_a_basis_row_without_an_id_publishes_nothing_to_agree_with(self, clock):
        t = _tracker(clock)
        t.begin([E])
        t.note_basis(E, [SimpleNamespace(current_probability=0.6)])
        t.resolved(E, ("stamped", 0.6, STAMPED_AT, None, 9, "live"))
        assert E not in t._events or not isinstance(_state(t).pub, dict)


class TestOpenWork:
    def test_an_open_batch_freezes_until_it_resolves(self, clock):
        t = _tracker(clock)
        _publish(t, o70=0.6)
        before = _c(t)
        t.begin([E])  # a preview or stamp may publish before it resolves
        clock.tick(1)
        t.note_input(E, HOME, 0.6, clock.wall)
        assert _c(t) == before
        t.resolved(E, ("lock",))
        clock.tick(1)
        t.note_input(E, HOME, 0.6, clock.wall)
        assert _c(t) == clock.wall

    def test_a_batch_that_never_resolves_stops_freezing_after_its_bound(self, clock):
        t = _tracker(clock)
        _publish(t, o70=0.6)
        t.begin([E])
        clock.tick(ca.BUSY_MAX_S + 1)
        t.note_input(E, HOME, 0.6, clock.wall)
        assert _c(t) == clock.wall

    def test_a_previewing_batch_that_failed_to_stamp_freezes_for_the_preview_ttl(self, clock):
        t = _tracker(clock, preview_ttl_s=60.0)
        _publish(t, o70=0.6)
        before = _c(t)
        t.begin([E], previewing=[E])
        t.resolved(E, ("lock",))  # the preview may still be on readers' screens
        clock.tick(30)
        t.note_input(E, HOME, 0.6, clock.wall)
        assert _c(t) == before
        clock.tick(31)
        t.note_input(E, HOME, 0.6, clock.wall)
        assert _c(t) == clock.wall

    def test_a_stamp_ends_the_preview_freeze(self, clock):
        t = _tracker(clock)
        _publish(t, o70=0.6)
        t.begin([E], previewing=[E])
        t.failed([E])
        clock.tick(1)
        t.note_input(E, HOME, 0.6, clock.wall)
        frozen = _c(t)
        _publish(t, o70=0.6)
        clock.tick(1)
        t.note_input(E, HOME, 0.6, clock.wall)
        assert _c(t) == clock.wall > frozen

    def test_a_lock_skip_without_a_preview_does_not_freeze(self, clock):
        t = _tracker(clock)
        _publish(t, o70=0.6)
        t.begin([E])
        t.resolved(E, ("lock",))
        clock.tick(1)
        t.note_input(E, HOME, 0.6, clock.wall)
        assert _c(t) == clock.wall

    def test_a_refused_stale_stamp_forgets_what_was_published(self, clock):
        t = _tracker(clock)
        _publish(t, o70=0.6)
        before = _c(t)
        t.begin([E])
        t.resolved(E, ("stale", 0.6))
        clock.tick(1)
        t.note_input(E, HOME, 0.6, clock.wall)
        assert _c(t) == before

    def test_a_pending_withdrawal_that_refutes_a_published_leg_holds(self, clock):
        withdrawn = {}
        t = _tracker(clock, refutes=lambda oid, p: withdrawn.get(oid) is not None
                     and not withdrawn[oid][0] <= p <= withdrawn[oid][1])
        _publish(t, o70=0.6, o71=0.4)
        before = _c(t)
        withdrawn[HOME] = (0.01, 0.2)  # a wide book that prices 0.6 out
        clock.tick(1)
        t.note_withdrawal(E, HOME)
        assert _state(t).held_since == clock.wall
        clock.tick(1)
        t.note_input(E, AWAY, 0.4, clock.wall)
        assert _c(t) == before
        # Red partner: the same book containing 0.6 does not hold.
        withdrawn[HOME] = (0.5, 0.7)
        clock.tick(1)
        t.note_input(E, AWAY, 0.4, clock.wall)
        assert _c(t) == clock.wall

    def test_a_reading_that_did_not_publish_is_not_agreed_with(self, clock):
        """Rows staged for a reading whose batch then refused or skipped the
        stamp never become the published basis."""
        t = _tracker(clock)
        _publish(t, o70=0.6)
        t.begin([E])
        t.note_basis(E, _rows(o70=0.62))
        t.resolved(E, ("lock",))
        assert _state(t).pub == {HOME: 0.6}
        clock.tick(1)
        t.note_input(E, HOME, 0.62, clock.wall)
        assert _state(t).held_since == clock.wall

    def test_a_silent_reading_reports_nothing(self, clock):
        t = _tracker(clock)
        _publish(t, o70=0.6)
        t.begin([E])
        t.resolved(E, ("no_reading",))
        assert t.report(_state(t), clock.wall) == (None, None)

    def test_a_final_stamp_forgets_the_event(self, clock):
        t = _tracker(clock)
        _publish(t, status="completed", o70=0.6)
        assert E not in t._events

    def test_unchanged_dispositions_agree_without_claiming_a_publication(self, clock):
        t = _tracker(clock)
        t.note_input(E, HOME, 0.6, clock.wall)
        recv = clock.wall
        clock.tick(30)
        _publish(t, kind="unchanged", o70=0.6)
        assert _c(t) == recv  # the input's own receipt, not the batch's time


# ── the writer: throttled, one hash per event, a field per venue ────────────

class _Pipe:
    def __init__(self, sink, fail):
        self.sink, self.fail, self.ops = sink, fail, []

    def hset(self, key, field, value):
        self.ops.append(("hset", key, field, value))

    def expire(self, key, ttl):
        self.ops.append(("expire", key, ttl))

    async def execute(self):
        if self.fail:
            raise ConnectionError("down")
        self.sink.append(self.ops)


class _Client:
    def __init__(self):
        self.batches, self.fail = [], False

    def pipeline(self, transaction=True):
        assert transaction is False
        return _Pipe(self.batches, self.fail)


class TestWriter:
    def test_take_due_writes_a_change_once_and_refreshes_a_hold(self, clock):
        t = _tracker(clock)
        _publish(t, o70=0.6)
        due = t.take_due()
        assert [eid for eid, _ in due] == [E]
        payload = json.loads(due[0][1])
        assert payload == {"c": int(STAMP_WALL * 1000), "h": None, "w": int(clock.wall * 1000)}
        assert t.take_due() is None  # nothing changed, nothing held: the writer may stop
        clock.tick(1)
        t.note_input(E, HOME, 0.62, clock.wall)
        assert json.loads(t.take_due()[0][1])["h"] == int(clock.wall * 1000)
        assert t.take_due() == []  # held, not yet due a refresh
        clock.tick(ca.HELD_REFRESH_S)
        assert [eid for eid, _ in t.take_due()] == [E]

    @pytest.mark.asyncio
    async def test_the_writer_throttles_to_one_write_per_interval(self, clock, monkeypatch):
        monkeypatch.setattr(ca, "WRITE_INTERVAL_S", 0.05)
        client = _Client()
        t = _tracker(clock, client=lambda: client)
        _publish(t, o70=0.6)
        for _ in range(8):  # agreeing inputs across one interval, the loop turning
            clock.tick(0.001)
            t.note_input(E, HOME, 0.6, clock.wall)
            await asyncio.sleep(0.005)
        await asyncio.sleep(0.04)
        assert len(client.batches) == 1
        (ops,) = client.batches
        assert ops[0][:3] == ("hset", ca.confirmed_key(E), "kalshi")
        assert json.loads(ops[0][3])["c"] == int(clock.wall * 1000)
        assert ops[1] == ("expire", ca.confirmed_key(E), ca.KEY_TTL_S)
        await asyncio.sleep(0.08)
        assert t._task is None  # nothing dirty, nothing held: stopped
        t.close()

    @pytest.mark.asyncio
    async def test_a_failed_write_is_retried(self, clock, monkeypatch):
        monkeypatch.setattr(ca, "WRITE_INTERVAL_S", 0.02)
        client = _Client()
        client.fail = True
        t = _tracker(clock, client=lambda: client)
        _publish(t, o70=0.6)
        await asyncio.sleep(0.03)
        assert t.stats["write_errors"] >= 1 and client.batches == []
        client.fail = False
        await asyncio.sleep(0.05)
        assert client.batches
        t.close()


# ── the reader: combine venues, never past a live hold ──────────────────────

def _entry(c=None, h=None, w=None):
    return json.dumps({"c": c, "h": h, "w": w})


class TestCombine:
    NOW = 1_793_314_900.0
    MS = int(NOW * 1000)

    def test_the_newest_agreement_across_venues(self):
        got = combine([_entry(c=self.MS - 5000, w=self.MS), _entry(c=self.MS - 2000, w=self.MS)],
                      self.NOW)
        assert got == (self.MS - 2000) / 1000

    def test_a_live_hold_caps_every_venue(self):
        entries = [_entry(c=self.MS - 2000, w=self.MS),                    # kalshi, agrees
                   _entry(c=self.MS - 9000, h=self.MS - 6000, w=self.MS)]  # pm, held
        assert combine(entries, self.NOW) == (self.MS - 9000) / 1000

    def test_a_hold_whose_writer_went_quiet_no_longer_caps(self):
        stale = self.MS - int(ca.HELD_FRESH_S * 1000) - 1
        entries = [_entry(c=self.MS - 2000, w=self.MS),
                   _entry(c=self.MS - 90000, h=self.MS - 80000, w=stale)]
        assert combine(entries, self.NOW) == (self.MS - 2000) / 1000

    def test_nothing_known_is_none_and_a_future_stamp_is_clamped(self):
        assert combine([], self.NOW) is None
        assert combine([_entry(w=self.MS)], self.NOW) is None
        assert combine(["{bad", _entry(c=self.MS + 500, w=self.MS)], self.NOW) == self.NOW


class TestReads:
    @pytest.mark.asyncio
    async def test_many_streams_share_one_read_per_event_per_second(self, clock):
        calls = []

        async def fetch(ids):
            calls.append(list(ids))
            return {eid: [_entry(c=int(clock.wall * 1000), w=int(clock.wall * 1000))] for eid in ids}

        reads = ConfirmedReads(fetch, mono=lambda: clock.mono, wall=lambda: clock.wall)
        assert await reads.current([E], 0.1) == int(clock.wall * 1000) / 1000
        for _ in range(50):
            reads.peek([E])
        await asyncio.sleep(0)
        assert calls == [[E]]
        clock.tick(ca.READ_TTL_S)
        reads.peek([E])
        await asyncio.sleep(0)
        assert calls == [[E], [E]]

    @pytest.mark.asyncio
    async def test_a_failed_read_is_unknown_not_an_error(self, clock):
        async def fetch(ids):
            return None

        reads = ConfirmedReads(fetch, mono=lambda: clock.mono, wall=lambda: clock.wall)
        assert await reads.current([E], 0.1) is None


# ── the route: on connect, and on every advance, as a named heartbeat ───────

def _sse(chunks, name):
    out = []
    for chunk in chunks:
        if chunk.startswith(f"event: {name}\n"):
            out.append(json.loads(chunk.split("data: ", 1)[1]))
    return out


@pytest.fixture
def route_reads(monkeypatch):
    """The real hub and route; `confirmed_at` comes from a scripted read."""
    from tests._event_stream_legacy_view import install_legacy_view

    install_legacy_view(monkeypatch)
    script = {"c": None, "step": 0.0, "calls": 0}

    async def fetch(ids):
        script["calls"] += 1
        if script["c"] is None:
            return {eid: [] for eid in ids}
        c = script["c"] + script["step"] * (script["calls"] - 1)
        ms = int(c * 1000)
        return {eid: [_entry(c=ms, w=ms)] for eid in ids}

    monkeypatch.setattr(ca, "_READS", ConfirmedReads(fetch))
    return script


class TestRoute:
    @pytest.mark.asyncio
    async def test_connect_sends_the_current_confirmed_at_once_the_replay_is_out(
        self, route_reads, monkeypatch,
    ):
        # lane1 R3: nothing waits for this read before the replay; the next
        # pass carries it (FRAME_WAIT_S apart when idle, shortened here).
        from app.routes import event_stream as mod
        from tests.test_live_push import FakePubSub, _collect

        import time as _time
        monkeypatch.setattr(mod, "FRAME_WAIT_S", 0.01)
        route_reads["c"] = _time.time() - 3
        chunks = await _collect(5, FakePubSub(), monkeypatch, disconnect_after=3)
        names = [c.split("\n", 1)[0] for c in chunks if c.startswith("event: ")]
        assert names[:2] == ["event: open", "event: heartbeat"]
        (beat,) = _sse(chunks, "heartbeat")[:1]
        assert set(beat) == {"t", "confirmed_at"}
        assert beat["confirmed_at"] == ca.iso(int(route_reads["c"] * 1000) / 1000)

    @pytest.mark.asyncio
    async def test_unknown_on_connect_sends_nothing_new(self, route_reads, monkeypatch):
        """Old readers' frames are unchanged: no extra frame when nothing is
        known, and a published price is forwarded byte for byte."""
        from datetime import datetime, timezone

        from tests.test_live_push import FakePubSub, _collect, _frame

        fresh = _frame(event_id=5, updated_at=datetime.now(timezone.utc).isoformat())
        chunks = await _collect(5, FakePubSub([{"type": "message", "data": json.dumps(fresh)}]),
                                monkeypatch, disconnect_after=6)
        names = [c.split("\n", 1)[0] for c in chunks if c.startswith("event: ")]
        assert "event: heartbeat" not in names
        (prob,) = _sse(chunks, "probability")
        assert prob == fresh and "confirmed_at" not in json.dumps(prob)

    @pytest.mark.asyncio
    async def test_the_interval_heartbeat_carries_the_added_key_only(self, route_reads, monkeypatch):
        from app.routes import event_stream as mod
        from tests.test_live_push import FakePubSub, _collect

        monkeypatch.setattr(mod, "HEARTBEAT_INTERVAL_S", 0.0)
        chunks = await _collect(5, FakePubSub(), monkeypatch, disconnect_after=2)
        beats = _sse(chunks, "heartbeat")
        assert beats and all(set(b) == {"t", "confirmed_at"} for b in beats)
        assert all(b["confirmed_at"] is None for b in beats)

    @pytest.mark.parametrize("min_gap,expect_more", [(0.0, True), (60.0, False)])
    @pytest.mark.asyncio
    async def test_an_advance_is_pushed_and_throttled(self, route_reads, monkeypatch,
                                                      min_gap, expect_more):
        from app.routes import event_stream as mod
        from tests.test_live_push import FakePubSub, _collect

        import time as _time
        monkeypatch.setattr(mod, "CONFIRMED_BEAT_MIN_S", min_gap)
        monkeypatch.setattr(ca, "READ_TTL_S", 0.0)
        route_reads["c"], route_reads["step"] = _time.time() - 30, 1.0
        chunks = await _collect(5, FakePubSub(), monkeypatch, disconnect_after=8)
        stamps = [b["confirmed_at"] for b in _sse(chunks, "heartbeat")]
        assert stamps and stamps == sorted(set(stamps))  # only ever newer
        assert (len(stamps) > 1) is expect_more


# ── the wiring: the real refresher's batch, and the real Kalshi consumer ────

class TestRefresherWiring:
    @pytest.mark.asyncio
    async def test_a_real_stamp_publishes_its_blended_rows_to_the_tracker(self, monkeypatch):
        """`_refresh_batch` stages the stamp's contributing rows and
        `TailReceipts.resolve` hands them over after the commit: a later input
        at the blended price confirms, a different one holds."""
        from contextlib import asynccontextmanager
        from datetime import datetime, timezone

        from app.tasks.live_blend_refresh import LiveBlendRefresher, TailReceipts
        from tests.test_live_blend_refresh import _RecordingSession

        fresh = datetime.now(timezone.utc).isoformat()
        event = SimpleNamespace(id=E, home_team_name="Twins", away_team_name="Yankees",
                                completed_at=None, status="live", espn_win_prob_home=None,
                                opening_home_probability=None)
        market = SimpleNamespace(id=10, event_id=E, name="Twins vs Yankees")
        session = _RecordingSession([(market, event)], [],
                                    {"kalshi": {"value": 0.6, "updated_at": fresh}})
        session.returned_rev = 3

        @asynccontextmanager
        async def _fake_session():
            yield session

        blended = SimpleNamespace(id=HOME, current_probability=0.6)
        mid_batch = []

        def _reading(group, home, away):
            # Inside the batch: the event is open work, so nothing confirms.
            mid_batch.append(tracker._events[E].busy_until is not None)
            return SimpleNamespace(
                home_probability=0.6, away_probability=None, draw_probability=None,
                eligibility=None, market=market, outcome=blended,
                contributing_outcomes=(blended,), yes_probability=0.6,
            )

        monkeypatch.setattr("app.tasks.base.get_task_session", _fake_session)
        monkeypatch.setattr("app.utils.live_blend.compute_source_home_probability", _reading)

        async def _no_inversion(session, event_id, home_prob, source):
            return home_prob

        async def _no_snapshot(session, **kwargs):
            return object(), False

        monkeypatch.setattr("app.tasks.prediction_market_matching._check_and_fix_inversion",
                            _no_inversion)
        monkeypatch.setattr("app.tasks.snapshots._create_or_update_win_prob_snapshot",
                            _no_snapshot)
        r = LiveBlendRefresher("kalshi")

        async def _capture(frames):
            # The publisher acknowledges every frame it is handed (R2).
            return r._normal_revisions(frames)

        monkeypatch.setattr(r, "_publish", _capture)
        r.receipts = TailReceipts("kalshi")
        tracker = r.receipts.confirmed = ConfirmedAt("kalshi", preview_ttl_s=60.0)
        # The consumer hands only headline legs' marks over (see the
        # real-consumer cases below); a prop's input reaches no tracker.
        tracker.note_mark(r.receipts.note_input(E, HOME, 0.6, "ticker"))
        r.receipts.note_input(E, PROP, 0.3, "ticker")

        await r.refresh([E])

        assert r._dispositions[E][0] == "stamped"
        assert mid_batch and all(mid_batch)
        state = tracker._events[E]
        assert state.pub == {HOME: 0.6}
        assert set(state.latest) == {HOME}
        assert state.busy_until is None and state.held_since is None
        stamped = state.confirmed
        # The newer of the publication and the agreeing input it blended.
        assert stamped == max(ca._stamp_wall(r._dispositions[E][2]),
                              state.latest[HOME][1])
        await asyncio.sleep(0.01)
        tracker.note_mark(r.receipts.note_input(E, HOME, 0.6, "ticker"))
        assert state.confirmed > stamped
        tracker.note_mark(r.receipts.note_input(E, HOME, 0.61, "ticker"))
        assert state.held_since is not None
        r.receipts.close_all("test")


class TestTheRealKalshiConsumer:
    @pytest.mark.asyncio
    async def test_socket_repeats_confirm_and_a_new_price_holds(self, monkeypatch):
        """The production consumer: `handle_ticker` marks winner-leg inputs as
        headline, the stamp hands over what it blended, the venue's repeat of
        that price confirms and its later different price holds."""
        import time as _time

        import app.services.kalshi_ws as kalshi_svc
        import app.tasks.kalshi_ws as kalshi_task
        import app.tasks.live_blend_refresh as blend_mod
        from app.tasks.live_blend_refresh import LiveBlendRefresher
        from tests.test_delivery_receipt_10090 import _run_until_consumed, _ticker
        from tests.test_ws_flush_retry_q491 import (
            EVENT_ID, KALSHI_OUTCOME_ID, KALSHI_SLATE, _install_slate,
        )

        seen = {}

        class _Recording(LiveBlendRefresher):
            def __init__(self, source, **kw):
                kw["min_refresh_interval_s"] = 0.01
                super().__init__(source, **kw)
                seen["refresher"] = self
                self._rev = 500

            async def _refresh_batch(self, event_ids, now, *, prepared=None,
                                     on_committed=None, publish_committed=None):
                for eid in event_ids:
                    self._last_refresh_at[eid] = now
                    self._rev += 1
                    # Every stamp here blends the FIRST price, 0.42.
                    self._dispositions[eid] = (
                        "stamped", 0.42, ca.iso(_time.time()),
                        self._last_written_value.get(eid), self._rev, "live",
                    )
                    self._note_confirm_basis(eid, [SimpleNamespace(
                        id=KALSHI_OUTCOME_ID, current_probability=0.42)])
                    self._last_written_value[eid] = 0.42
                    self._last_write_at[eid] = now
                if on_committed is not None:
                    on_committed(event_ids)
                # Its frames are acknowledged, as `_publish_prices` reports (R2).
                self._note_confirm_published({(eid, self._rev) for eid in event_ids}, set())

        monkeypatch.setattr(ConfirmedAt, "_kick", lambda self: None)  # no Redis writer
        monkeypatch.setenv("KALSHI_API_KEY_ID", "test-key")
        monkeypatch.setenv("KALSHI_RSA_PRIVATE_KEY", "test-secret")
        monkeypatch.setattr(kalshi_svc, "_load_rsa_key", lambda: object())
        monkeypatch.setattr(kalshi_svc, "_sign_ws_request", lambda _k, _i: {})
        monkeypatch.setattr(kalshi_task, "PRICE_FLUSH_SECONDS", 0.02)
        monkeypatch.setattr(blend_mod, "LiveBlendRefresher", _Recording)
        monkeypatch.setattr(blend_mod, "_live_handoff", {"kalshi": frozenset({EVENT_ID})})
        frames = [
            (0.0, _ticker(yes_bid_dollars="0.40", yes_ask_dollars="0.44")),   # 0.42
            (0.15, _ticker(yes_bid_dollars="0.41", yes_ask_dollars="0.43")),  # 0.42 again
            (0.15, _ticker(yes_bid_dollars="0.46", yes_ask_dollars="0.50")),  # 0.48: moved
            (0.15, _ticker(yes_bid_dollars="0.46", yes_ask_dollars="0.50")),  # 0.48 again
        ]
        writes: list = []
        _install_slate(monkeypatch, KALSHI_SLATE, writes, {"fail_writes": 0, "failed": 0})

        await _run_until_consumed(
            monkeypatch, kalshi_task, kalshi_task._run_kalshi_ws_consumer, frames,
        )

        tracker = seen["refresher"].receipts.confirmed
        assert isinstance(tracker, ConfirmedAt) and tracker.source == "kalshi"
        state = tracker._events[EVENT_ID]
        assert state.pub == {KALSHI_OUTCOME_ID: 0.42}
        assert state.latest[KALSHI_OUTCOME_ID][0] == 0.48
        # Confirmed by the 0.42 repeat, frozen from the moment 0.48 arrived.
        assert state.confirmed is not None and state.held_since is not None
        assert state.confirmed < state.held_since
        assert tracker.stats["advanced"] >= 2


class TestTheRealPolymarketConsumer:
    @pytest.mark.asyncio
    async def test_a_repeat_confirms_and_a_refuting_wide_book_holds(self, monkeypatch):
        """`_mark_input` marks game legs as headline; a wide book that prices
        the published leg out is buffered as a withdrawal and holds the event
        (red partner: the same tracker with that book contradicting nothing)."""
        import time as _time

        import app.tasks.live_blend_refresh as blend_mod
        import app.tasks.polymarket_ws as poly_task
        from app.tasks.live_blend_refresh import LiveBlendRefresher
        from tests.test_delivery_receipt_10090 import _run_until_consumed
        from tests.test_ws_flush_retry_q491 import (
            EVENT_ID, POLY_SLATE, YES_OUTCOME_ID, YES_TOKEN, _install_slate, _poly_frame,
        )

        seen, at_withdrawal = {}, []

        class _Recording(LiveBlendRefresher):
            def __init__(self, source, **kw):
                kw["min_refresh_interval_s"] = 0.01
                super().__init__(source, **kw)
                seen["refresher"] = self
                self._rev = 700

            async def _refresh_batch(self, event_ids, now, *, prepared=None,
                                     on_committed=None, publish_committed=None):
                for eid in event_ids:
                    self._last_refresh_at[eid] = now
                    self._rev += 1
                    self._dispositions[eid] = (
                        "stamped", 0.7, ca.iso(_time.time()),
                        self._last_written_value.get(eid), self._rev, "live",
                    )
                    self._note_confirm_basis(eid, [SimpleNamespace(
                        id=YES_OUTCOME_ID, current_probability=0.7)])
                    self._last_written_value[eid] = 0.7
                    self._last_write_at[eid] = now
                if on_committed is not None:
                    on_committed(event_ids)
                # Its frames are acknowledged, as `_publish_prices` reports (R2).
                self._note_confirm_published({(eid, self._rev) for eid in event_ids}, set())

        real_note_withdrawal = ConfirmedAt.note_withdrawal

        def _spy(self, event_id, outcome_id):
            real_note_withdrawal(self, event_id, outcome_id)
            state = self._events.get(event_id)
            if state is not None and isinstance(state.pub, dict):
                at_withdrawal.append((outcome_id, self.refutes(outcome_id, 0.7),
                                      state.held_since, state.confirmed))

        monkeypatch.setattr(ConfirmedAt, "_kick", lambda self: None)  # no Redis writer
        monkeypatch.setattr(ConfirmedAt, "note_withdrawal", _spy)
        monkeypatch.setattr(poly_task, "PRICE_FLUSH_SECONDS", 0.02)
        monkeypatch.setattr(blend_mod, "LiveBlendRefresher", _Recording)
        monkeypatch.setattr(blend_mod, "_live_handoff", {"polymarket": frozenset({EVENT_ID})})
        frames = [
            (0.0, _poly_frame("best_bid_ask", YES_TOKEN, best_bid="0.68", best_ask="0.72")),
            (0.15, _poly_frame("best_bid_ask", YES_TOKEN, best_bid="0.69", best_ask="0.71")),
            (0.15, _poly_frame("best_bid_ask", YES_TOKEN, best_bid="0.01", best_ask="0.40")),
        ]
        writes: list = []
        _install_slate(monkeypatch, POLY_SLATE, writes, {"fail_writes": 0, "failed": 0})

        await _run_until_consumed(
            monkeypatch, poly_task, poly_task._run_polymarket_ws_consumer, frames,
        )

        tracker = seen["refresher"].receipts.confirmed
        assert tracker.source == "polymarket" and tracker.refutes is not None
        state = tracker._events[EVENT_ID]
        assert state.pub == {YES_OUTCOME_ID: 0.7}
        assert state.latest[YES_OUTCOME_ID][0] == 0.7  # the socket's inputs arrived
        assert tracker.stats["advanced"] >= 2  # the stamp, then the 0.70 repeat
        held = [w for w in at_withdrawal if w[0] == YES_OUTCOME_ID]
        assert held, at_withdrawal
        _oid, refuted, held_since, confirmed = held[0]
        assert refuted is True
        assert held_since is not None and confirmed is not None and confirmed <= held_since


# ── lane1's REVISE on 9dd290e2 (R1-R6, S1-S2) ───────────────────────────────


def _real_refresher(monkeypatch, *, publish):
    """The real `_refresh_batch` on a one-event session (as TestRefresherWiring),
    with ``publish`` standing in for `_publish` (Redis)."""
    from contextlib import asynccontextmanager
    from datetime import datetime, timezone

    from app.tasks.live_blend_refresh import LiveBlendRefresher, TailReceipts
    from tests.test_live_blend_refresh import _RecordingSession

    fresh = datetime.now(timezone.utc).isoformat()
    event = SimpleNamespace(id=E, home_team_name="Twins", away_team_name="Yankees",
                            completed_at=None, status="live", espn_win_prob_home=None,
                            opening_home_probability=None)
    market = SimpleNamespace(id=10, event_id=E, name="Twins vs Yankees")
    price = {"p": 0.6}
    sessions = []

    @asynccontextmanager
    async def _fake_session():
        session = _RecordingSession([(market, event)], [],
                                    {"kalshi": {"value": price["p"], "updated_at": fresh}})
        session.returned_rev = 3 + len(sessions)
        sessions.append(session)
        yield session

    def _reading(group, home, away):
        blended = SimpleNamespace(id=HOME, current_probability=price["p"])
        return SimpleNamespace(
            home_probability=price["p"], away_probability=None, draw_probability=None,
            eligibility=None, market=market, outcome=blended,
            contributing_outcomes=(blended,), yes_probability=price["p"],
        )

    async def _no_inversion(session, event_id, home_prob, source):
        return home_prob

    async def _no_snapshot(session, **kwargs):
        return object(), False

    monkeypatch.setattr("app.tasks.base.get_task_session", _fake_session)
    monkeypatch.setattr("app.utils.live_blend.compute_source_home_probability", _reading)
    monkeypatch.setattr("app.tasks.prediction_market_matching._check_and_fix_inversion",
                        _no_inversion)
    monkeypatch.setattr("app.tasks.snapshots._create_or_update_win_prob_snapshot",
                        _no_snapshot)
    r = LiveBlendRefresher("kalshi", min_refresh_interval_s=0)
    monkeypatch.setattr(r, "_publish", lambda frames: publish(r, frames))
    monkeypatch.setattr(r, "_start_normal_recovery", lambda: None)
    r.receipts = TailReceipts("kalshi")
    tracker = r.receipts.confirmed = ConfirmedAt("kalshi", preview_ttl_s=60.0)
    return r, tracker, price


class TestR2ConfirmationWaitsForPublication:
    """lane1 R2: `committed()` resolves at COMMIT, before the frame is
    published. A stamp readers do not have yet is a newer, different price."""

    @pytest.mark.asyncio
    async def test_a_publication_that_raises_never_lets_agreeing_inputs_advance(
        self, monkeypatch,
    ):
        async def broken(r, frames):
            raise ConnectionError("redis down")

        r, tracker, price = _real_refresher(monkeypatch, publish=broken)
        tracker.note_mark(r.receipts.note_input(E, HOME, 0.6, "ticker"))
        await r.refresh([E])
        assert r._dispositions[E][0] == "stamped"
        state = tracker._events[E]
        assert state.pub is None, "its frame never reached readers"
        before = state.confirmed
        for _ in range(3):
            await asyncio.sleep(0.002)
            tracker.note_mark(r.receipts.note_input(E, HOME, 0.6, "ticker"))
        assert state.confirmed == before
        assert tracker.report(state, __import__("time").time())[1] is not None  # held
        r.receipts.close_all("test")

    @pytest.mark.asyncio
    async def test_a_frame_that_failed_to_build_never_lets_agreeing_inputs_advance(
        self, monkeypatch,
    ):
        async def acks(r, frames):
            return r._normal_revisions(frames)

        def broken_frame(**kwargs):
            raise ValueError("frame build failed")

        r, tracker, _price = _real_refresher(monkeypatch, publish=acks)
        monkeypatch.setattr("app.utils.live_push.build_frame", broken_frame)
        tracker.note_mark(r.receipts.note_input(E, HOME, 0.6, "ticker"))
        await r.refresh([E])
        assert r._dispositions[E][0] == "stamped", "the stamp itself committed"
        state = tracker._events[E]
        assert state.pub is None
        before = state.confirmed
        await asyncio.sleep(0.002)
        tracker.note_mark(r.receipts.note_input(E, HOME, 0.6, "ticker"))
        assert state.confirmed == before
        r.receipts.close_all("test")

    @pytest.mark.asyncio
    async def test_after_the_acknowledgement_agreeing_inputs_advance(self, monkeypatch):
        async def acks(r, frames):
            return r._normal_revisions(frames)

        r, tracker, _price = _real_refresher(monkeypatch, publish=acks)
        tracker.note_mark(r.receipts.note_input(E, HOME, 0.6, "ticker"))
        await r.refresh([E])
        state = tracker._events[E]
        assert state.pub == {HOME: 0.6} and state.awaiting is None
        stamped = state.confirmed
        assert stamped is not None
        await asyncio.sleep(0.002)
        tracker.note_mark(r.receipts.note_input(E, HOME, 0.6, "ticker"))
        assert state.confirmed > stamped
        r.receipts.close_all("test")

    def test_committed_but_unacknowledged_holds_until_the_publisher_answers(self, clock):
        t = _tracker(clock)
        _publish(t, o70=0.6, acked=False, rev=9)
        clock.tick(1)
        t.note_input(E, HOME, 0.6, clock.wall)
        assert _c(t) is None and _state(t).held_since is not None
        t.published({(E, 8)})  # an older frame's answer changes nothing
        assert _c(t) is None
        t.published({(E, 9)})
        assert _c(t) == clock.wall and _state(t).held_since is None

    def test_an_unacknowledged_revision_is_unknown_until_the_next_stamp(self, clock):
        t = _tracker(clock)
        _publish(t, o70=0.6, acked=False, rev=9)
        t.published((), {(E, 9)})
        assert _state(t).pub is None
        clock.tick(1)
        t.note_input(E, HOME, 0.6, clock.wall)
        assert _c(t) is None

    def test_an_answer_before_its_batch_resolves_is_kept_for_it(self, clock):
        # The singleton refresh publishes inline, then resolves.
        t = _tracker(clock)
        t.published({(E, 9)})
        _publish(t, o70=0.6, acked=False, rev=9)
        assert _state(t).awaiting is None and _c(t) == STAMP_WALL
        t2 = _tracker(clock)
        t2.published((), {(E, 9)})
        _publish(t2, o70=0.6, acked=False, rev=9)
        assert t2._events[E].pub is None

    def test_a_lost_acknowledgement_gives_up_as_unknown(self, clock):
        t = _tracker(clock)
        _publish(t, o70=0.6, acked=False, rev=9)
        clock.tick(ca.AWAITING_MAX_S + 1)
        t.note_input(E, HOME, 0.6, clock.wall)
        assert _state(t).pub is None and _c(t) is None


class TestR7AHoldKeepsItsStartIntoUnknown:
    """lane1 R7 (b3ab03fc): awaiting -> unknown must not drop or move the
    hold's start, or `combine` lets the other venue's later agreements count
    while this venue's committed, different price is still unpublished."""

    def _h(self, t, clock):
        return t.report(_state(t), clock.wall)[1]

    def test_a_lost_acknowledgement_keeps_the_holds_start(self, clock):
        t = _tracker(clock)
        t0 = int(clock.wall * 1000)
        _publish(t, o70=0.6, acked=False, rev=9)
        assert self._h(t, clock) == t0
        clock.tick(ca.AWAITING_MAX_S + 1)
        t.note_input(E, HOME, 0.6, clock.wall)  # the input that gives up
        assert _state(t).pub is None
        assert self._h(t, clock) == t0
        clock.tick(1)
        t.note_input(E, HOME, 0.6, clock.wall)
        assert self._h(t, clock) == t0

    def test_an_unacknowledged_answer_keeps_the_holds_start(self, clock):
        t = _tracker(clock)
        t0 = int(clock.wall * 1000)
        _publish(t, o70=0.6, acked=False, rev=9)
        clock.tick(5)
        t.published((), {(E, 9)})
        assert _state(t).pub is None
        assert self._h(t, clock) == t0

    def test_the_other_venues_later_agreement_does_not_count(self, clock):
        t = _tracker(clock)
        t0 = int(clock.wall * 1000)
        _publish(t, o70=0.6, acked=False, rev=9)
        clock.tick(ca.AWAITING_MAX_S + 1)
        t.note_input(E, HOME, 0.6, clock.wall)
        now = int(clock.wall * 1000)
        c, h = t.report(_state(t), clock.wall)
        entries = [_entry(c=c, h=h, w=now),          # this venue, unknown
                   _entry(c=t0 + 30_000, w=now)]     # the other venue agrees
        assert combine(entries, clock.wall) is None


class TestR5TheUnknownHoldFollowsTheLastInput:
    def test_inputs_every_5s_for_60s_keep_the_hold_then_it_lapses_30s_after(self, clock):
        t = _tracker(clock)
        _publish(t, kind="stale")  # nothing comparable: unknown
        start = clock.wall
        t.note_input(E, HOME, 0.5, clock.wall)
        for _ in range(12):
            clock.tick(5)
            t.note_input(E, HOME, 0.5 + 0.01 * _, clock.wall)
        assert clock.wall - start == 60
        assert t.report(_state(t), clock.wall)[1] == int(start * 1000)
        clock.tick(ca.UNKNOWN_HOLD_S - 1)
        assert t.report(_state(t), clock.wall)[1] is not None
        clock.tick(2)
        assert t.report(_state(t), clock.wall)[1] is None

    def test_speaking_again_after_a_lapse_starts_a_new_hold(self, clock):
        t = _tracker(clock)
        _publish(t, kind="stale")
        t.note_input(E, HOME, 0.5, clock.wall)
        clock.tick(ca.UNKNOWN_HOLD_S + 5)
        assert t.report(_state(t), clock.wall)[1] is None
        t.note_input(E, HOME, 0.55, clock.wall)
        assert t.report(_state(t), clock.wall)[1] == int(clock.wall * 1000)


class TestR6AHoldIsWrittenAtOnce:
    @pytest.mark.asyncio
    async def test_a_hold_reaches_redis_within_one_loop_turn(self, clock, monkeypatch):
        monkeypatch.setattr(ca, "WRITE_INTERVAL_S", 30.0)  # no tick in this test
        client = _Client()
        t = _tracker(clock, client=lambda: client)
        _publish(t, o70=0.6)
        clock.tick(1)
        t.note_input(E, HOME, 0.62, clock.wall)  # a different price: a hold
        for _ in range(3):
            await asyncio.sleep(0)
        assert client.batches, "the hold waited for the advance throttle"
        payload = json.loads(client.batches[-1][0][3])
        assert payload["h"] == int(clock.wall * 1000)
        t.close()

    @pytest.mark.asyncio
    async def test_a_stamps_publication_wait_keeps_the_throttle(self, clock, monkeypatch):
        monkeypatch.setattr(ca, "WRITE_INTERVAL_S", 30.0)
        client = _Client()
        t = _tracker(clock, client=lambda: client)
        _publish(t, o70=0.6, acked=False)  # committed, its frame in flight
        for _ in range(3):
            await asyncio.sleep(0)
        assert client.batches == []
        t.close()


class TestS1S2:
    def test_unchanged_stages_its_basis_only_when_the_row_stores_that_value(self):
        from app.tasks.live_blend_refresh import LiveBlendRefresher, TailReceipts

        r = LiveBlendRefresher("kalshi")
        r.receipts = TailReceipts("kalshi")
        tracker = r.receipts.confirmed = ConfirmedAt("kalshi", preview_ttl_s=60.0)
        rows = _rows(o70=0.6)
        poll_wrote = SimpleNamespace(win_probability_sources={"kalshi": {"value": 0.58}})
        r._note_confirm_basis(E, rows, stored_row=poll_wrote, value=0.6)
        assert E not in tracker._basis
        stored = SimpleNamespace(win_probability_sources={"kalshi": {"value": 0.6}})
        r._note_confirm_basis(E, rows, stored_row=stored, value=0.6)
        assert tracker._basis[E] == {HOME: 0.6}

    @pytest.mark.asyncio
    async def test_a_failed_read_is_an_attempt(self, clock):
        calls = []

        async def down(ids):
            calls.append(ids)
            return None

        reads = ConfirmedReads(down, mono=lambda: clock.mono, wall=lambda: clock.wall)
        await reads.current([E], 0.1)
        await reads.current([E], 0.1)
        assert len(calls) == 1
        clock.tick(ca.READ_TTL_S)
        await reads.current([E], 0.1)
        assert len(calls) == 2


def _fold_stream(monkeypatch, reads, order=None):
    from app.routes import event_stream as route
    from app.utils import live_fanout
    from tests.test_folded_event_stream_invalidation_837 import Hub, Request

    hub, release = Hub(), asyncio.Event()
    hub.confirmed_reads = lambda: reads

    async def project(event_id, frame):
        await release.wait()
        return {"event_id": E, "hero_probability": 0.4,
                "blend_fold_revision": {"1": 11, "2": 22}}

    async def replay(ids):
        if order is not None:
            order.append("replay")
        return []

    async def no_coverage(event_id, ids):
        await asyncio.Event().wait()

    hub.project_folded_quote = project
    monkeypatch.setattr(live_fanout, "fanout", lambda: hub)
    monkeypatch.setattr(route, "latest_frames", replay)
    monkeypatch.setattr(route, "_current_reconcile", no_coverage)
    monkeypatch.setattr(route, "FRAME_WAIT_S", 0.01)
    monkeypatch.setattr(route, "CONFIRMED_BEAT_MIN_S", 0.0)
    return route._stream(1, Request(), [1, 2]), hub, release


class TestR3R4TheStream:
    @pytest.mark.asyncio
    async def test_the_replay_is_read_before_the_confirmation_read_starts(self, monkeypatch):
        order = []

        async def fetch(ids):
            order.append("confirmed")
            return {eid: [] for eid in ids}

        stream, _hub, _release = _fold_stream(monkeypatch, ConfirmedReads(fetch), order)
        pending = None
        try:
            for _ in range(2):  # retry, open
                await asyncio.wait_for(anext(stream), 1)
            pending = asyncio.create_task(anext(stream))  # the loop turns
            await asyncio.sleep(0.05)
        finally:
            if pending is not None:
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)
            await stream.aclose()
        # 9dd290e2 awaited this read (up to 100 ms) BEFORE the replay.
        assert order[:2] == ["replay", "confirmed"]

    @pytest.mark.asyncio
    async def test_no_confirmed_at_advance_while_a_fold_projection_is_pending(self, monkeypatch):
        """lane1 R4: a folded page's headline moves only on `folded_probability`."""
        import time as _time

        from tests.test_folded_live_quote_10090 import trigger

        monkeypatch.setattr(ca, "READ_TTL_S", 0.0)
        now = {"c": _time.time() - 20}

        async def fetch(ids):
            now["c"] += 1.0  # the venues keep confirming
            ms = int(now["c"] * 1000)
            return {eid: [_entry(c=ms, w=ms)] for eid in ids}

        stream, hub, release = _fold_stream(monkeypatch, ConfirmedReads(fetch))

        def data(chunk):
            return json.loads(chunk.split("data: ")[1])

        pending = None
        try:
            chunks = [await asyncio.wait_for(anext(stream), 1) for _ in range(3)]
            first = [data(c) for c in chunks if c.startswith("event: heartbeat")]
            assert first, chunks  # retry, open, then the first confirmed heartbeat
            sent = max(b["confirmed_at"] for b in first)
            hub.subscriptions["live:event:2"].offer(json.dumps(trigger()))
            # Until the raw invalidation is handled no fold is owed: a beat
            # may still go out. From it on, the headline waits on the fold.
            while True:
                chunk = await asyncio.wait_for(anext(stream), 1)
                if chunk.startswith("event: heartbeat"):
                    sent = max(sent, data(chunk)["confirmed_at"])
                elif chunk.startswith("event: probability"):
                    assert data(chunk)["folded_quote_pending"] is True
                    break
            # The projection is pending: the loop keeps turning (FRAME_WAIT_S
            # 0.01) and the venues keep confirming, but nothing may go out.
            pending = asyncio.create_task(anext(stream))
            await asyncio.sleep(0.15)
            assert not pending.done(), pending.result()
            release.set()
            folded = await asyncio.wait_for(pending, 1)
            pending = None
            assert folded.startswith("event: folded_probability"), folded
            beat = await asyncio.wait_for(anext(stream), 1)
            assert beat.startswith("event: heartbeat") and data(beat)["confirmed_at"] > sent
        finally:
            release.set()
            if pending is not None:
                await asyncio.gather(pending, return_exceptions=True)
            await stream.aclose()


class TestR8NoBeatWhileARecoveryReadIsOwed:
    @pytest.mark.asyncio
    async def test_no_confirmed_at_advance_while_a_confirmed_recovery_read_is_owed(
            self, monkeypatch):
        """lane1 R8 (b3ab03fc): a frame published between the replay read and
        SUBSCRIBE reaches the reader only through the CONFIRMED recovery read;
        until it does, no heartbeat may carry a `confirmed_at` vouching for it."""
        import time as _time

        from app.utils import live_fanout

        monkeypatch.setattr(ca, "READ_TTL_S", 0.0)
        now = {"c": _time.time() - 20}

        async def fetch(ids):
            now["c"] += 1.0
            ms = int(now["c"] * 1000)
            return {eid: [_entry(c=ms, w=ms)] for eid in ids}

        stream, hub, release = _fold_stream(monkeypatch, ConfirmedReads(fetch))
        beats = []
        try:
            for _ in range(2):  # retry, open
                await asyncio.wait_for(anext(stream), 1)
            hub.subscriptions["live:event:2"].offer(live_fanout.CONFIRMED)
            deadline = asyncio.get_running_loop().time() + 0.3
            while asyncio.get_running_loop().time() < deadline:
                try:
                    chunk = await asyncio.wait_for(anext(stream), 0.1)
                except asyncio.TimeoutError:
                    break
                if chunk.startswith("event: heartbeat"):
                    beats.append(json.loads(chunk.split("data: ")[1]).get("confirmed_at"))
        finally:
            release.set()
            await stream.aclose()
        assert not [b for b in beats if b is not None], beats


def _stamping_refresher(seen, basis):
    """A refresher whose every stamp blends ``basis`` ({outcome: price}) and
    whose frame the publisher acknowledges (as `_publish_prices` reports)."""
    import time as _time

    from app.tasks.live_blend_refresh import LiveBlendRefresher

    class _Stamping(LiveBlendRefresher):
        def __init__(self, source, **kw):
            kw["min_refresh_interval_s"] = 0.01
            super().__init__(source, **kw)
            seen["refresher"] = self
            self._rev = 900

        async def _refresh_batch(self, event_ids, now, *, prepared=None,
                                 on_committed=None, publish_committed=None):
            for eid in event_ids:
                self._last_refresh_at[eid] = now
                self._rev += 1
                self._dispositions[eid] = (
                    "stamped", 0.5, ca.iso(_time.time()),
                    self._last_written_value.get(eid), self._rev, "live",
                )
                self._note_confirm_basis(eid, [
                    SimpleNamespace(id=oid, current_probability=p) for oid, p in basis.items()
                ])
                self._last_written_value[eid] = 0.5
                self._last_write_at[eid] = now
            if on_committed is not None:
                on_committed(event_ids)
            self._note_confirm_published({(eid, self._rev) for eid in event_ids}, set())

        async def publish_market_changes(self, _session):
            return 0

    return _Stamping


def _assert_bridged_leg_holds(tracker, event_id, leg, moved_to):
    state = tracker._events[event_id]
    # 9dd290e2: the bridged leg never reached the tracker (`latest` had no
    # entry), so the slate leg's agreeing input confirmed the event while the
    # bridged leg's newer, different price was held.
    assert leg in state.latest and state.latest[leg][0] == moved_to
    assert state.held_since is not None
    assert state.confirmed is None or state.confirmed <= state.held_since


class TestR1BridgedLegsReachTheTracker:
    @pytest.mark.asyncio
    async def test_kalshi_a_bridged_open_winner_on_a_mixed_event_holds(self, monkeypatch):
        from tests import test_ws_open_contract_prices_9484 as k

        joh_ticker, joh_market, joh_outcome = "KXATPMATCH-26SEP28ANGJOH-JOH", 8, 82
        seen = {}
        monkeypatch.setattr(ConfirmedAt, "_kick", lambda self: None)  # no Redis writer
        await k._run(
            monkeypatch,
            frames_for={
                k.LINKED_TICKER: [k._tick(k.LINKED_TICKER, "0.40", "0.42", "0.41")] * 3,
                joh_ticker: [k._tick(joh_ticker, "0.64", "0.66", "0.65")],
            },
            open_rows=[(joh_ticker, joh_market, joh_outcome, 900, k.LINKED_EVENT_TICKER)],
            events_admitted=[900],
            refresher=_stamping_refresher(seen, {71: 0.41, joh_outcome: 0.59}),
        )
        tracker = seen["refresher"].receipts.confirmed
        assert tracker._events[900].pub == {71: 0.41, joh_outcome: 0.59}
        _assert_bridged_leg_holds(tracker, 900, joh_outcome, 0.65)

    # The Polymarket twin needs the #10664 real-transaction rig, so it lives
    # in tests/test_ws_polymarket_open_contract_prices_9484.py, the file CI's
    # real-PostgreSQL gate runs (and fails on any skip):
    # TestTheBridgedLegFeedsConfirmedAt.
