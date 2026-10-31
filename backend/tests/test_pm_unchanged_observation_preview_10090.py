"""An unchanged price acknowledgement can feed optional DNPL, never a stamp."""

from types import SimpleNamespace
from app.tasks.polymarket_ws import books_with_complements, _poly_book_is_untradeable
from app.tasks.live_blend_refresh import HeldRowQuotes
import pytest

from tests.test_pm_quote_lock_bound_10090 import writer_rig
from tests.test_ws_flush_cadence_10090 import _FakeTime
from tests.test_polymarket_withdrawal_speed_10651 import ROOT, compile_functions


@pytest.mark.parametrize("successor", [None, "same-price", "sustained-same-price", "a-b-a", "withdraw-restore", "routing",
                                              "owner-other", "owner-same", "owner-unknown",
                                              "release-other", "release-same", "release-then-finish", "new-window"])
async def test_successful_unchanged_ack_hands_frozen_observation_to_preview_only(monkeypatch, successor):
    clock = _FakeTime(monkeypatch, t=1000)
    database = {1: .6, 2: .4}
    r, state = writer_rig(clock, database=database, batch=dict(database), mapping={1: 10, 2: 10}, books={})
    state.held = False
    assert await r.ns["flush_prices"](flush_started=1000)
    original_writes = list(state.commits)
    refresher = r.ns["blend_refresher"]
    refresher.preview_events = {10}
    observed = []

    class Bounds(HeldRowQuotes):
        # Keep the real returned-clock ticket API; this no-row acknowledgement
        # has no write clock and must retain the existing sampling fallback.
        def bound_for(self, mark):
            return None if mark is None else 1000.5

        async def sample_database_clock(self, *args):
            pass

        def release(self, *args):
            pass

        def __contains__(self, oid):
            return False

        def note_input(self, mark):
            pass

    async def preview(observations, validate):
        if successor == "same-price":
            r.ns["_mark_input"](1, .6, "price_change", {})
        elif successor == "sustained-same-price":
            for _ in range(100):
                for oid, value in database.items():
                    r.ns["_mark_input"](oid, value, "price_change", {})
        elif successor == "a-b-a":
            r.ns["_mark_input"](1, .7, "price_change", {})
            r.ns["_mark_input"](1, .6, "price_change", {})
        elif successor == "withdraw-restore":
            await r.ns["handle_price"]({"asset_id": "asset", "best_bid": "0.01", "best_ask": "0.99"})
            assert not r.ns["observation_continuity"]
            r.ns["withdraw_buffer"].clear()
            for oid, value in database.items():
                r.ns["_mark_input"](oid, value, "price_change", {})
        elif successor == "routing":
            r.ns["routing_generation"] += 1
        owner = r.ns["catalog_boundary"].stamp_owner(refresher)
        if successor in ("owner-other", "owner-same", "owner-unknown"):
            owner.task = SimpleNamespace(done=lambda: False)
            owner.events = {99} if successor == "owner-other" else {10} if successor == "owner-same" else None
        elif successor in ("release-other", "release-same", "release-then-finish"):
            refresher._admission.released[99 if successor == "release-other" else 10] = 1
            if successor == "release-then-finish":
                refresher._admission = None
        elif successor == "new-window":
            refresher._admission = SimpleNamespace(released={})
        try:
            allowed = await validate(set(observations))
            observed.append((observations, allowed))
        finally:
            owner.task = None
            owner.events = None

    refresher.held_quotes = Bounds()
    refresher.preview_accepted_observations = preview
    refresher._admission = SimpleNamespace(released={})
    r.ns["routing_generation"] = 0
    r.ns["observation_continuity"] = {oid: (object(), value) for oid, value in database.items()}
    marks = {oid: SimpleNamespace(seq=oid + 10, outcome_id=oid, probability=value)
             for oid, value in database.items()}
    r.ns["input_marks"].update(marks)
    seq = [100]

    def note_input(eid, oid, value, kind, timestamp):
        seq[0] += 1
        return SimpleNamespace(seq=seq[0], outcome_id=oid, probability=value)

    r.ns["tail_receipts"].note_input = note_input
    r.ns.update(asset_to_market={"asset": 1}, open_asset_to_market={}, open_asset_mirrors={},
                books_by_asset={}, _note_raw=lambda asset: None, _tick_targets=lambda asset: [1],
                books_with_complements=books_with_complements,
                _poly_book_is_untradeable=_poly_book_is_untradeable,
                repeat_skip_s=0.0)  # #10090: today's path (`PM_WS_REPEAT_SKIP_MS=0`)
    compile_functions(ROOT / "app/tasks/polymarket_ws.py", ["_mark_input", "handle_price"], r.ns)
    r.ns["price_buffer"].update(database)
    r.trace.clear()
    r.marks.clear()
    clock.t = 1001
    assert await r.ns["flush_prices"](flush_started=1001)
    assert len(observed) == 1
    observations, allowed = observed[0]
    assert allowed == ({10} if successor in (None, "same-price", "sustained-same-price", "owner-other", "release-other") else set())
    assert observations == {10: {oid: (value, 1000.5, marks[oid]) for oid, value in database.items()}}
    assert state.commits == original_writes
    assert r.ns["successful_price_write_at"] == {1: 1000, 2: 1000}
    assert not r.marks and not any(kind == "refresh" for kind, _ in r.trace)
