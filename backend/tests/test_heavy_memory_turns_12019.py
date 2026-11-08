"""#12019: the full Kalshi poll and the matcher never share worker-heavy.

Measured on production Nov 8: the 12:45 PM PT poll started beside
``match_prediction_markets`` on the one 1 GB worker-heavy dyno, R14 fired every
22 s from 12:55:12 and R15 SIGKILLed it at 12:57:24, before it created a market.

🔴 THE LOAD-BEARING CHECKS:

* ``test_poll_waits_while_the_matcher_holds_the_dyno`` — a poll that finds the
  matcher running must not start; it marks itself pending and retries.
* ``test_matcher_declines_while_a_poll_is_pending`` — the matcher's next tick
  hands the dyno to the waiting poll instead of starting another 13-minute pass.
* ``test_matcher_declines_while_the_poll_runs`` — the other direction.

Their opposite arms stop the rule passing by never running anything: an idle
dyno runs each task, the event-ticker poll never waits, a poll that has waited
out its retries runs anyway, and no Redis means today's behaviour.
"""

from unittest.mock import patch

import pytest

import app.tasks as tasks
from app.tasks import heavy_memory_turns as turns
from app.utils import single_flight


class _Redis:
    """The operations ``single_flight`` and the turn keys use. TTLs recorded only."""

    def __init__(self):
        self.store: dict[str, bytes] = {}
        self.ttls: dict[str, int] = {}

    def set(self, k, v, nx=False, ex=None):
        if nx and k in self.store:
            return None
        self.store[k] = v.encode() if isinstance(v, str) else v
        if ex is not None:
            self.ttls[k] = ex
        return True

    def exists(self, k):
        return 1 if k in self.store else 0

    def delete(self, k):
        return 1 if self.store.pop(k, None) is not None else 0

    def eval(self, script, numkeys, key, token):
        assert script == single_flight.RELEASE_IF_OWNER_LUA
        stored = self.store.get(key)
        if stored is not None and stored == token.encode():
            del self.store[key]
            return 1
        return 0


class _Retry(Exception):
    pass


LEASE_KEY = single_flight.lease_key(turns.LEASE_TASK)


@pytest.fixture
def rig():
    rc = _Redis()
    ran: list[str] = []
    seen_lease: list[bool] = []

    def tracked(label, coro):
        coro.close()
        ran.append(label)
        seen_lease.append(LEASE_KEY in rc.store)
        return {"ran": label}

    async def fake_poll(event_ticker=None):  # pragma: no cover - closed unawaited
        return {}

    async def fake_match(limit):  # pragma: no cover - closed unawaited
        return {}

    retry_calls: list[dict] = []

    def fake_retry(**kwargs):
        retry_calls.append(kwargs)
        return _Retry()

    with patch.object(single_flight, "_client", return_value=rc), patch.object(
        turns, "_client", return_value=rc
    ), patch.object(tasks, "_tracked_run", side_effect=tracked), patch(
        "app.tasks.kalshi._poll_kalshi_markets", side_effect=fake_poll
    ), patch(
        "app.tasks.prediction_market_matching._match_prediction_markets",
        side_effect=fake_match,
    ), patch.object(
        tasks.poll_kalshi_markets, "retry", side_effect=fake_retry
    ):
        yield rc, ran, seen_lease, retry_calls


def _poll(retries=0, **kwargs):
    task = tasks.poll_kalshi_markets
    task.push_request(retries=retries)
    try:
        return task.run(**kwargs)
    finally:
        task.pop_request()


def _match():
    return tasks.match_prediction_markets.run(limit=500)


def _hold_lease(rc, token="other:0"):
    rc.store[LEASE_KEY] = token.encode()


def test_idle_dyno_runs_the_poll_under_the_lease_and_frees_it(rig):
    rc, ran, seen_lease, retry_calls = rig
    assert _poll() == {"ran": "poll_kalshi"}
    assert ran == ["poll_kalshi"] and seen_lease == [True]
    assert retry_calls == []
    assert LEASE_KEY not in rc.store
    assert rc.ttls[LEASE_KEY] == turns.POLL_LEASE_TTL_S


def test_idle_dyno_runs_the_matcher_under_the_lease_and_frees_it(rig):
    rc, ran, seen_lease, _ = rig
    assert _match() == {"ran": "prediction_market_match"}
    assert ran == ["prediction_market_match"] and seen_lease == [True]
    assert LEASE_KEY not in rc.store
    assert rc.ttls[LEASE_KEY] == turns.MATCH_LEASE_TTL_S


def test_poll_waits_while_the_matcher_holds_the_dyno(rig):
    rc, ran, _, retry_calls = rig
    _hold_lease(rc)
    with pytest.raises(_Retry):
        _poll()
    assert ran == []
    assert retry_calls == [
        {"countdown": turns.POLL_RETRY_COUNTDOWN_S, "max_retries": turns.POLL_MAX_RETRIES}
    ]
    assert rc.exists(turns.PENDING_KEY)
    assert rc.ttls[turns.PENDING_KEY] == turns.PENDING_TTL_S
    # The matcher's lease is untouched.
    assert rc.store[LEASE_KEY] == b"other:0"


def test_matcher_declines_while_a_poll_is_pending(rig):
    rc, ran, _, _ = rig
    turns.mark_poll_pending(rc)
    out = _match()
    assert out["skipped"] is True and out["reason"] == "kalshi_poll_pending"
    assert ran == []
    assert LEASE_KEY not in rc.store


def test_matcher_declines_while_the_poll_runs(rig):
    rc, ran, _, _ = rig
    _hold_lease(rc, "poll:0")
    out = _match()
    assert out["skipped"] is True and out["reason"] == "already_running"
    assert ran == []
    assert rc.store[LEASE_KEY] == b"poll:0"


def test_the_poll_clears_its_pending_mark_once_it_runs(rig):
    rc, ran, _, _ = rig
    turns.mark_poll_pending(rc)
    _poll(retries=3)
    assert ran == ["poll_kalshi"]
    assert not rc.exists(turns.PENDING_KEY)
    # ... so the matcher's next tick runs again.
    _match()
    assert ran == ["poll_kalshi", "prediction_market_match"]


def test_a_poll_that_waited_out_its_retries_runs_anyway(rig):
    rc, ran, _, retry_calls = rig
    _hold_lease(rc)
    turns.mark_poll_pending(rc)
    assert _poll(retries=turns.POLL_MAX_RETRIES) == {"ran": "poll_kalshi"}
    assert retry_calls == []
    assert ran == ["poll_kalshi"]
    assert not rc.exists(turns.PENDING_KEY)
    # It never took, so it never released, the matcher's lease.
    assert rc.store[LEASE_KEY] == b"other:0"


def test_the_event_ticker_poll_never_waits(rig):
    rc, ran, _, retry_calls = rig
    _hold_lease(rc)
    assert _poll(event_ticker="KXNFLGAME-26NOV08KCBUF") == {"ran": "poll_kalshi"}
    assert retry_calls == [] and ran == ["poll_kalshi"]
    assert not rc.exists(turns.PENDING_KEY)


def test_no_redis_means_both_run_as_before(rig):
    _, ran, _, retry_calls = rig
    with patch.object(single_flight, "_client", return_value=None), patch.object(
        turns, "_client", return_value=None
    ):
        _poll()
        _match()
    assert ran == ["poll_kalshi", "prediction_market_match"]
    assert retry_calls == []


def test_a_task_that_raises_still_frees_the_dyno(rig):
    rc, _, _, _ = rig

    def boom(label, coro):
        coro.close()
        raise RuntimeError("R15")

    with patch.object(tasks, "_tracked_run", side_effect=boom):
        with pytest.raises(RuntimeError):
            _match()
    assert LEASE_KEY not in rc.store


def test_memory_line_names_the_task(rig, caplog):
    with caplog.at_level("INFO", logger="app.tasks.heavy_memory_turns"):
        _match()
    lines = [r.getMessage() for r in caplog.records if "heavy_memory_turn" in r.getMessage()]
    assert len(lines) == 1
    assert "task=match_prediction_markets" in lines[0]
    assert "peak_mb=" in lines[0]
