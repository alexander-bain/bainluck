"""#10090 — under ``POLYMARKET_WS_OPEN_SCOPE=slate`` a market a reader holds
keeps streaming, and a market leaves the socket only after a quiet period.

``slate`` narrows the PM open arm to live and near-start markets. Without these
seeds a reader holding a low-volume market's page would see an up-to-an-hour-old
price. Seeds added here: the markets and events a reader holds
(``utils/reader_presence``: ``PUBSUB CHANNELS`` over the SSE hub's
``live:market:*`` / ``live:event:*`` channels) and the served markets; every
seed stays one until ``OPEN_SCOPE_QUIET_S`` after it last was
(``OpenScopeMemory``). Between refreshes a held market the scope has not seen
brings the refresh forward, at most once per
``OPEN_SCOPE_EARLY_REFRESH_MIN_S``. That the hub unsubscribes a channel once
its last reader leaves is ``test_sse_shares_one_pubsub_connection_6515.py``'s
subject.

Fixtures (speed's 1909Z list):

9. a held market outside the slate stays on the socket (by market and by its
   event), and a market no longer held stays until its quiet period ends;
10. an early refresh is rate-limited, and a held id with no open Polymarket
    market (a Kalshi page) is asked about once and never refreshes;
11. an unreadable held set narrows nothing: the last held set stands in and
    nothing ages out; with none read yet every open contract is installed; the
    between-refresh check never refreshes on an unreadable read.
"""

import asyncio

import pytest

from app.tasks import polymarket_open_contracts as open_mod
from app.tasks import polymarket_ws as task
from app.utils import reader_presence as presence_mod
from app.utils.reader_presence import (
    PresenceUnreadable,
    ReaderPresence,
    presence_from_channels,
    read_reader_presence,
)
from tests.test_pm_open_scope_slate_10090 import (
    OPEN_MARKET,
    OPEN_NO,
    OPEN_YES,
    ScopeRig,
    _arm,
    _consumer_locals,
)

BOTH = {"oY": OPEN_YES, "oN": OPEN_NO}
HELD_EVENT = 900


# ── the held set ─────────────────────────────────────────────────────────────


def test_the_channel_prefixes_are_the_publishers_own():
    from app.utils.live_push import event_channel
    from app.utils.market_quote_push import market_channel

    assert presence_mod.MARKET_CHANNEL_PREFIX + "7" == market_channel(7)
    assert presence_mod.EVENT_CHANNEL_PREFIX + "7" == event_channel(7)


def test_presence_parses_bytes_and_text_and_skips_malformed_names():
    held = presence_from_channels(
        [b"live:market:17", "live:market:18", "live:market:x", "live:event:5"],
        [b"live:event:900", "live:event:", "other:event:3"],
    )
    assert held == ReaderPresence(frozenset({17, 18}), frozenset({900}))


class _Client:
    def __init__(self, replies=None, fail=None):
        self.replies, self.fail, self.asked = replies or {}, fail, []

    def pubsub_channels(self, pattern="*"):
        self.asked.append(pattern)
        if self.fail is not None:
            raise self.fail
        return self.replies.get(pattern, [])


def test_the_read_asks_the_two_hub_patterns():
    client = _Client({"live:market:*": [b"live:market:17"], "live:event:*": []})
    assert read_reader_presence(client) == ReaderPresence(frozenset({17}))
    assert client.asked == ["live:market:*", "live:event:*"]


@pytest.mark.parametrize(
    "client",
    [
        _Client(fail=ConnectionError("down")),
        _Client(fail=RuntimeError("ERR unknown command 'PUBSUB'")),
        _Client({"live:market:*": None}),
    ],
)
def test_an_unread_held_set_raises_and_is_never_an_empty_one(client):
    with pytest.raises(PresenceUnreadable):
        read_reader_presence(client)


# ── the memory, as plain data ────────────────────────────────────────────────


def test_a_seed_stays_one_until_its_quiet_period_ends():
    memory = open_mod.OpenScopeMemory()
    assert memory.seeds({1}, {9}, now=0.0, quiet_s=10.0) == ({1}, {9})
    assert memory.seeds(set(), set(), now=9.9, quiet_s=10.0) == ({1}, {9})
    assert memory.seeds({2}, set(), now=10.0, quiet_s=10.0) == ({2}, set())


def test_an_unexpired_refresh_ages_nothing_out():
    memory = open_mod.OpenScopeMemory()
    memory.seeds({1}, {9}, now=0.0, quiet_s=10.0)
    assert memory.seeds(set(), set(), now=99.0, quiet_s=10.0, expire=False) == (
        {1},
        {9},
    )


def test_unseen_skips_seeds_and_the_game_socket_and_note_asks_once():
    memory = open_mod.OpenScopeMemory()
    memory.seeds({1}, {9}, now=0.0, quiet_s=10.0)
    held = ReaderPresence(frozenset({1, 2, 3}), frozenset({9, 10, 11}))
    assert memory.unseen(held, {3}, {11}) == ({2}, {10})
    memory.note({2}, {10}, 1.0)
    assert memory.unseen(held, {3}, {11}) == (set(), set())
    assert memory.market_seen[1] == 0.0  # note never refreshes a seed's time


def test_the_early_refresh_wait():
    memory = open_mod.OpenScopeMemory()
    assert memory.early_refresh_wait(5.0, 120.0) == 0.0
    memory.early_refresh_at = 5.0
    assert memory.early_refresh_wait(65.0, 120.0) == 60.0
    assert memory.early_refresh_wait(125.0, 120.0) == 0.0


def test_a_mirror_of_a_game_token_is_remembered_by_market():
    admission = open_mod.OpenContractAdmission()
    admission.asset_mirrors = {"g1": [(1, 50)], "o1": [(2, 51)]}
    assert open_mod.game_mirror_market_ids(admission, {"g1"}) == {50}


# ── the real consumer ────────────────────────────────────────────────────────


class Held:
    """The held set each read answers; ``fail`` makes every read unreadable."""

    def __init__(self, markets=(), events=()):
        self.markets, self.events, self.fail, self.reads = set(markets), set(events), False, 0

    def __call__(self):
        self.reads += 1
        if self.fail:
            raise PresenceUnreadable("ConnectionError: down")
        return ReaderPresence(frozenset(self.markets), frozenset(self.events))


class Phases:
    """Slate reads in the consumer's frame once its startup admission is
    installed (an empty scope included): read 0 starts the first loop refresh,
    read k follows the k-th refresh's boundary."""

    def __init__(self):
        self.reads = -1

    def __call__(self):
        local = _consumer_locals()
        if local is None or "admission_task" not in local:
            return None, None
        if not local["admission_task"].done():
            return None, None
        self.reads += 1
        return self.reads, local


def _age_out():
    memory = open_mod.open_scope_memory()
    for seen in (memory.market_seen, memory.event_seen):
        for key in seen:
            seen[key] -= open_mod.OPEN_SCOPE_QUIET_S


async def _refreshes(monkeypatch, rig, held, steps):
    """Run the consumer under ``slate``; ``steps[k](local)`` runs after the
    k-th timer refresh's boundary and returns True to stop."""
    stop, phases = asyncio.Event(), Phases()

    def on_slate_read(_n):
        n, local = phases()
        if n is not None and n in steps and steps[n](local):
            stop.set()

    rig.on_slate_read = on_slate_read
    _arm(monkeypatch, rig, "slate", presence=held)
    return await asyncio.wait_for(task._run_polymarket_ws_consumer(stop=stop), 30)


@pytest.mark.asyncio
async def test_a_held_market_outside_the_slate_stays_on_the_socket(monkeypatch):
    """9a. Nothing on the slate. Held by its market, the open binary is kept;
    held by nobody (control) it is dropped."""
    for held, expected in ((Held(markets={OPEN_MARKET}), BOTH), (Held(), {})):
        seen = {}
        rig = ScopeRig(eligible=[[]])

        def step(local, seen=seen):
            seen["open"] = dict(local["open_asset_to_outcome"])
            return True

        stats = await _refreshes(monkeypatch, rig, held, {1: step})
        assert seen["open"] == expected
        assert stats["open_contract_scope_held_markets"] == len(held.markets)


@pytest.mark.asyncio
async def test_a_held_event_keeps_its_open_markets_on_the_socket(monkeypatch):
    """9a. A reader on the event page holds ``live:event:<id>``; its open
    markets are read by event and kept."""
    seen, rig = {}, ScopeRig(eligible=[[]])
    rig.held_rows = [(OPEN_MARKET, HELD_EVENT)]

    def step(local):
        seen["open"] = dict(local["open_asset_to_outcome"])
        return True

    await _refreshes(monkeypatch, rig, Held(events={HELD_EVENT}), {1: step})
    assert seen["open"] == BOTH
    assert any(HELD_EVENT in events for _markets, events in rig.held_reads)


@pytest.mark.asyncio
async def test_a_market_no_longer_held_stays_until_its_quiet_period_ends(monkeypatch):
    """9b. Held at startup, then released: kept through the next refreshes,
    dropped at the first refresh after its quiet period."""
    seen, rig, held = {}, ScopeRig(eligible=[[]]), Held(markets={OPEN_MARKET})

    def released(local):
        seen[0] = dict(local["open_asset_to_outcome"])
        held.markets.clear()  # the reader leaves before refresh 1

    def still_quiet(local):
        seen[1] = dict(local["open_asset_to_outcome"])
        _age_out()  # the quiet period passes before refresh 2

    def after_quiet(local):
        seen[2] = dict(local["open_asset_to_outcome"])
        return True

    await _refreshes(
        monkeypatch, rig, held, {0: released, 1: still_quiet, 2: after_quiet}
    )
    assert seen[0] == BOTH and seen[1] == BOTH
    assert seen[2] == {}


@pytest.mark.asyncio
async def test_an_early_refresh_is_rate_limited(monkeypatch):
    """10. The timer never fires. A newly held market brings one refresh at
    once; a second, held right after that refresh, waits out the minimum
    interval. A held id with no open Polymarket market (a Kalshi page) is
    asked about once and brings no refresh."""
    rig, held = ScopeRig(eligible=[[]]), Held()
    rig.held_rows = [(OPEN_MARKET, None), (18, None)]
    stop, phases, refreshes, consumer_stats = asyncio.Event(), Phases(), [], []
    kalshi_refreshed = []
    monkeypatch.setattr(open_mod, "OPEN_SCOPE_PRESENCE_CHECK_S", 0.01)
    monkeypatch.setattr(open_mod, "OPEN_SCOPE_EARLY_REFRESH_MIN_S", 0.4)

    def on_slate_read(_n):
        n, local = phases()
        if n is None:
            return
        consumer_stats.append(local["stats"])
        refreshes.append(
            (
                open_mod.open_scope_memory().early_refresh_at,
                dict(local["open_asset_to_outcome"]),
            )
        )
        if n == 1:
            stop.set()

    async def run():
        # The rig's timer is 0.02 s; this test needs it never to fire.
        monkeypatch.setattr(task, "SUBSCRIPTION_REFRESH_SECONDS", 60)
        consumer = asyncio.ensure_future(task._run_polymarket_ws_consumer(stop=stop))
        while held.reads == 0:  # startup read the held set: an empty scope
            await asyncio.sleep(0.01)
        held.markets.add(999)  # a Kalshi page: no open Polymarket market
        reads = held.reads
        while held.reads < reads + 10:
            await asyncio.sleep(0.005)
        kalshi_refreshed.append(bool(refreshes))
        held.markets.add(OPEN_MARKET)
        while not consumer_stats or consumer_stats[0].get("held_refreshes") != 1:
            await asyncio.sleep(0.005)
        held.markets.add(18)  # right after the first early refresh installed
        return await consumer

    rig.on_slate_read = on_slate_read
    _arm(monkeypatch, rig, "slate", presence=held)
    stats = await asyncio.wait_for(run(), 30)

    assert kalshi_refreshed == [False]
    assert stats["held_refreshes"] == 2 and stats["recycle_reason"] == "held"
    assert stats.get("catalog_refreshes") == 2
    first, second = refreshes[0][0], refreshes[1][0]
    assert second - first >= 0.4 - 0.02
    assert refreshes[0][1] == {} and refreshes[1][1] == BOTH
    asked_999 = [m for m, _e in rig.held_reads if 999 in m]
    assert len(asked_999) == 1
    assert stats["held_market_ids"] == [18]


@pytest.mark.asyncio
async def test_an_unreadable_held_set_keeps_the_previous_scope(monkeypatch):
    """11a. Held at startup, released before refresh 1 (kept: quiet period).
    Refresh 2 cannot read the held set and the quiet period has passed: the
    previous scope stands, since nothing ages out on an unreadable read.
    Refresh 3 reads again: dropped."""
    seen, rig, held = {}, ScopeRig(eligible=[[]]), Held(markets={OPEN_MARKET})

    def released(local):
        held.markets.clear()

    def unreadable(local):
        seen[1] = dict(local["open_asset_to_outcome"])
        held.fail = True
        _age_out()

    def kept(local):
        seen[2] = (
            dict(local["open_asset_to_outcome"]),
            local["stats"]["open_contract_scope_presence_unreadable"],
        )
        held.fail = False

    def read_again(local):
        seen[3] = dict(local["open_asset_to_outcome"])
        return True

    await _refreshes(
        monkeypatch, rig, held,
        {0: released, 1: unreadable, 2: kept, 3: read_again},
    )
    assert seen[1] == BOTH
    assert seen[2] == (BOTH, 1)
    assert seen[3] == {}


@pytest.mark.asyncio
async def test_an_unreadable_held_set_with_none_read_installs_every_contract(
    monkeypatch,
):
    """11b. No held set has ever been read in this process: nothing to narrow
    to, so the full admission is installed and the scope is not."""
    seen, rig, held = {}, ScopeRig(eligible=[[]]), Held()
    held.fail = True

    def step(local):
        seen["open"] = dict(local["open_asset_to_outcome"])
        seen["installed"] = local["open_scope_installed"]
        return True

    stats = await _refreshes(monkeypatch, rig, held, {1: step})
    assert seen == {"open": BOTH, "installed": False}
    assert stats["open_contract_scope_presence_unreadable"] == 1


@pytest.mark.asyncio
async def test_an_unreadable_presence_check_never_refreshes(monkeypatch):
    """11c. Between refreshes an unreadable held set brings no refresh."""
    rig, held = ScopeRig(eligible=[[]]), Held()
    rig.held_rows = [(OPEN_MARKET, None)]
    stop = asyncio.Event()
    monkeypatch.setattr(open_mod, "OPEN_SCOPE_PRESENCE_CHECK_S", 0.01)

    async def run():
        monkeypatch.setattr(task, "SUBSCRIPTION_REFRESH_SECONDS", 60)
        consumer = asyncio.ensure_future(task._run_polymarket_ws_consumer(stop=stop))
        while held.reads == 0:  # startup read the held set: an empty scope
            await asyncio.sleep(0.01)
        held.markets, held.fail = {OPEN_MARKET}, True
        reads = held.reads
        while held.reads < reads + 10:
            await asyncio.sleep(0.01)
        stop.set()
        return await consumer

    _arm(monkeypatch, rig, "slate", presence=held)
    stats = await asyncio.wait_for(run(), 30)
    assert "held_refreshes" not in stats
    assert stats.get("catalog_refreshes", 0) == 0
    assert rig.held_reads == []
