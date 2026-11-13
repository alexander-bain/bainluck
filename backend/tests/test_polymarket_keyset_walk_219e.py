"""#219E / decision 170-188: the hourly Polymarket poll re-reads events its offset
scan cannot reach.

Gamma caps ``/events`` offset paging at 2,000, so the poll's newest-first scan
reached only the 2,000 newest active events, and an active market in an older
event was never re-read by it: on Nov 13, 70 of 95 Polymarket cards on Discover
were over 30 minutes old (#12633). ``_keyset_walk_active_events`` walks every
active event by ``/events/keyset`` from a saved cursor inside the poll's budget.
"""

from types import SimpleNamespace

import pytest

import app.tasks.polymarket as pm
from app.services.polymarket_api import PolymarketAPIService


class _Redis:
    def __init__(self, cursor=None):
        self.store = {} if cursor is None else {pm.POLYMARKET_KEYSET_CURSOR_KEY: cursor}

    def get(self, key):
        return self.store.get(key)

    def setex(self, key, ttl, value):
        self.store[key] = value

    def delete(self, key):
        self.store.pop(key, None)


class _Service:
    """Three keyset pages: c0 -> c1 -> c2 -> end."""

    PAGES = {
        None: ([{"id": "1"}, {"id": "2"}], "c1"),
        "c1": ([{"id": "3"}, {"id": "4"}], "c2"),
        "c2": ([{"id": "5"}], None),
    }

    _NEVER = object()

    def __init__(self, fail_on=_NEVER):
        self.asked, self.fail_on = [], fail_on

    async def get_events_keyset(self, *, active, closed, limit, after_cursor=None):
        assert active is True and closed is False and limit == 100
        self.asked.append(after_cursor)
        if after_cursor == self.fail_on:
            raise RuntimeError("429 Too Many Requests")
        return self.PAGES[after_cursor]

    def _parse_event(self, event_data):
        return SimpleNamespace(id=event_data["id"], markets=["m"])


class _Clock:
    def __init__(self, step):
        self.t, self.step = 0.0, step

    def __call__(self):
        self.t += self.step
        return self.t


def _writer(written, fail=False):
    async def _process(batch):
        if fail:
            raise RuntimeError("deadlock")
        written.append([e.id for e in batch])

    return _process


@pytest.mark.asyncio
async def test_the_walk_reaches_every_active_event_and_starts_over_at_the_end():
    rc, written = _Redis(), []
    out = await pm._keyset_walk_active_events(
        _Service(), rc, seen_ids={"2"}, process_batch=_writer(written),
        started=0.0, clock=_Clock(1),
    )
    # event 2 was handled by this run's offset scan, so it is skipped
    assert written == [["1"], ["3", "4"], ["5"]]
    assert out["keyset_pages"] == 3 and out["keyset_events"] == 4
    assert out["keyset_complete"] is True and out["keyset_error"] is None
    assert pm.POLYMARKET_KEYSET_CURSOR_KEY not in rc.store  # next run starts over


@pytest.mark.asyncio
async def test_a_run_resumes_from_the_saved_cursor():
    service, written = _Service(), []
    await pm._keyset_walk_active_events(
        service, _Redis(cursor="c1"), seen_ids=set(), process_batch=_writer(written),
        started=0.0, clock=_Clock(1),
    )
    assert service.asked[0] == "c1"
    assert written == [["3", "4"], ["5"]]


@pytest.mark.asyncio
async def test_the_walk_stops_at_its_share_of_the_budget_and_saves_its_place():
    rc, written, service = _Redis(), [], _Service()
    # each clock read advances 120 s against a 300 s stop: two pages fit
    out = await pm._keyset_walk_active_events(
        service, rc, seen_ids=set(), process_batch=_writer(written),
        started=0.0, stop_at_s=300, clock=_Clock(120),
    )
    assert out["keyset_pages"] == 2 and out["keyset_complete"] is False
    assert rc.store[pm.POLYMARKET_KEYSET_CURSOR_KEY] == "c2"


@pytest.mark.asyncio
async def test_a_failed_read_keeps_the_cursor_and_never_raises():
    rc, written = _Redis(cursor="c1"), []
    out = await pm._keyset_walk_active_events(
        _Service(fail_on="c1"), rc, seen_ids=set(), process_batch=_writer(written),
        started=0.0, clock=_Clock(1),
    )
    assert written == [] and "429" in out["keyset_error"]
    assert rc.store[pm.POLYMARKET_KEYSET_CURSOR_KEY] == "c1"


@pytest.mark.asyncio
async def test_a_failed_write_does_not_advance_the_cursor():
    rc = _Redis(cursor="c1")
    out = await pm._keyset_walk_active_events(
        _Service(), rc, seen_ids=set(), process_batch=_writer([], fail=True),
        started=0.0, clock=_Clock(1),
    )
    assert "deadlock" in out["keyset_error"]
    assert rc.store[pm.POLYMARKET_KEYSET_CURSOR_KEY] == "c1"  # the page is re-read next run


@pytest.mark.asyncio
async def test_the_service_sends_after_cursor_and_returns_the_next_one():
    sent = {}

    class _Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"events": [{"id": "9"}], "next_cursor": "c9"}

    class _Client:
        async def get(self, path, params=None):
            sent["path"], sent["params"] = path, params
            return _Response()

    svc = object.__new__(PolymarketAPIService)
    svc.gamma_client = _Client()
    events, cursor = await svc.get_events_keyset(after_cursor="c8")
    assert sent["path"] == "/events/keyset"
    # only after_cursor advances the walk; cursor/next_cursor are ignored by Gamma
    assert sent["params"] == {"limit": 100, "active": "true", "closed": "false", "after_cursor": "c8"}
    assert events == [{"id": "9"}] and cursor == "c9"


def test_the_poll_calls_the_walk_after_its_offset_scan():
    import inspect

    src = inspect.getsource(pm._poll_polymarket_markets)
    assert src.index('stats["hit_page_cap"]') < src.index("_keyset_walk_active_events(")
    assert src.index("_keyset_walk_active_events(") < src.index("Supplementary pass: fetch settled sports")
