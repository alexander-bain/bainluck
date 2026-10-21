"""#10090 / #10883 TSP-1 — two previewing sources share one per-event ledger.

SHIP: fresh observations from both venues advance a held page with one
complete, correctly ordered probability, without conflicting publishers or
false freshness. These cases pin the corrected contract (non-author review of
proposal f981f811, conditions 1–7) on a REAL Redis: two `LedgerRegistry`
objects are the two venue processes (production runs each venue in its own
process), each with its own owner claim, sharing nothing but Redis.

Real Redis: a private ``redis-server`` (``EVENT_FRAME_REDIS_SERVER`` or
``PATH``; CI's backend shards set it and ``EVENT_FRAME_REDIS_REQUIRED``), else
the loopback server ``PM_WITHDRAWAL_REDIS_URL`` names (a dedicated db, flushed
around each case). Clock-sensitive cases swap the script's Redis ``TIME`` for
a test key, so expiry and rollback are deterministic; every other case runs
the shipped script byte-for-byte.

``TSP1_MUTANT=<name>`` applies one entry of `MUTANTS` to the script (G3);
each must turn at least one case red.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse

import pytest

from app.utils import blend_preview
from app.utils.aggregation import compute_aggregate_probability, stamp_source_reading

SOURCES = frozenset({"kalshi", "polymarket"})
EV = 7
NOW = datetime.now(timezone.utc)
FRESH = NOW.isoformat()
BASE10 = {"kalshi": {"value": 0.5, "updated_at": FRESH},
          "polymarket": {"value": 0.5, "updated_at": FRESH}}
CLOCK_KEY = "tsp1:test:clock"
REAL_NOW = (
    "local function now_ms()\n"
    "  local t = redis.call('TIME')\n"
    "  return tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)\n"
    "end"
)
FAKE_NOW = f"local function now_ms() return tonumber(redis.call('GET', '{CLOCK_KEY}')) end"
#: The shipped script, captured before any case patches the module.
SHIPPED = blend_preview.LEDGER_SCRIPT

#: G3: (old, new) text replacements in LEDGER_SCRIPT, one at a time.
MUTANTS = {
    "publish_no_seq_cas": (
        "if st.gen ~= gen or st.seq ~= seq then return {'stale'} end", ""),
    "no_owner_prune": (
        "local function stale(s, m) return m.owner ~= owners[s] or m.expires <= now end",
        "local function stale(s, m) return m.expires <= now end"),
    "publish_no_contributor_expiry": ("or m.expires ~= x or x <= now then", "or m.expires ~= x then"),
    "publish_no_contributor_owner": (
        "if m == nil or o == nil or x == nil or m.owner ~= o or owners[s] ~= o",
        "if m == nil or o == nil or x == nil or m.owner ~= o"),
    "continue_renews_deadline": ("    expires = mine.expires\n", "    expires = now + max_ms\n"),
    "open_renews_chain": ("      if mine.chain == chain then return {'chain_exists'} end\n", ""),
    "continue_accepts_old_local": (
        "    if lseq <= mine.lseq then return {'old_local'} end\n    expires = mine.expires",
        "    expires = mine.expires"),
    "settle_ignores_entry_owner": (
        "local remove = ARGV[6] == 'settle' and mine ~= nil and mine.owner == claim",
        "local remove = ARGV[6] == 'settle' and mine ~= nil"),
    "settle_no_floor": (
        "  local adopt = brev ~= nil and ARGV[9] ~= '' and (st.base_rev == nil or brev > st.base_rev)",
        "  local adopt = false"),
    "terminal_is_delete": ("  redis.call('HSET', L, P .. 'term', decimal(ctx))\n", ""),
    "stale_terminal_accepted": (
        "  if st.live ~= nil and ctx < st.live then return {'stale_terminal'} end\n", ""),
    "ttl_not_recomputed": ("  local ttl = least - now\n", "  local ttl = 60000\n"),
    "reinit_after_loss": (
        "    if redis.call('EXISTS', MARK) == 1 then return {'lost'} end\n", ""),
    "no_owner_fence": ("if owners[src] ~= claim then return {'fenced'} end\n", ""),
    "no_expiry_prune": (
        "local function stale(s, m) return m.owner ~= owners[s] or m.expires <= now end",
        "local function stale(s, m) return m.owner ~= owners[s] end"),
    "no_regen_after_newer_claim": (
        "  if st.gen ~= nil and shared <= st.gen then return st.gen, st.seq end\n",
        "  if st.gen ~= nil then return st.gen, st.seq end\n"),
    "shared_counter_from_zero": (
        "  local n = math.max(epoch, shared)\n  if n >= MAX then return {'exhausted'} end\n  n = n + 1",
        "  local n = epoch\n  if n >= MAX then return {'exhausted'} end\n  n = n + 1"),
}


def _script(*, fake_clock: bool = False, fault: str | None = None) -> str:
    script = SHIPPED
    mutant = os.environ.get("TSP1_MUTANT")
    if mutant:
        old, new = MUTANTS[mutant]
        assert script.count(old) == 1, mutant
        script = script.replace(old, new)
    if fake_clock:
        assert script.count(REAL_NOW) == 1
        script = script.replace(REAL_NOW, FAKE_NOW)
    if fault:
        marker = f"  -- @@FAULT:{fault}\n"
        assert script.count(marker) == 1
        script = script.replace(marker, "  error('injected fault')\n")
    return script


# ------------------------------------------------------------------ real Redis


@pytest.fixture
def redis_kwargs():
    binary = os.environ.get("EVENT_FRAME_REDIS_SERVER") or shutil.which("redis-server")
    url = os.environ.get("PM_WITHDRAWAL_REDIS_URL")
    if binary:
        with tempfile.TemporaryDirectory(prefix="tsp1-10090-") as tmp:
            sock = Path(tmp) / "redis.sock"
            with (Path(tmp) / "redis.log").open("w") as log:
                process = subprocess.Popen(
                    [binary, "--port", "0", "--unixsocket", str(sock),
                     "--save", "", "--appendonly", "no"],
                    stdout=log, stderr=subprocess.STDOUT,
                )
                try:
                    deadline = time.monotonic() + 3
                    while not sock.exists():
                        if process.poll() is not None:
                            pytest.fail((Path(tmp) / "redis.log").read_text())
                        if time.monotonic() > deadline:
                            pytest.fail("private Redis startup timed out")
                        time.sleep(0.01)
                    yield {"unix_socket_path": str(sock)}
                finally:
                    process.terminate()
                    process.wait(timeout=5)
        return
    if url:
        import redis

        parsed = urlparse(url)
        db = int((parsed.path or "/0").lstrip("/") or 0)
        if parsed.scheme != "redis" or parsed.hostname not in ("localhost", "127.0.0.1") or db == 0:
            pytest.fail(f"PM_WITHDRAWAL_REDIS_URL must be loopback with a dedicated db, got {url!r}")
        kwargs = {"host": parsed.hostname, "port": parsed.port or 6379, "db": db}
        sync = redis.Redis(socket_timeout=5, **kwargs)
        sync.flushdb()
        try:
            yield kwargs
        finally:
            sync.flushdb()
            sync.close()
        return
    if os.environ.get("EVENT_FRAME_REDIS_REQUIRED"):
        pytest.fail("EVENT_FRAME_REDIS_REQUIRED is set but no real Redis was found")
    pytest.skip("set EVENT_FRAME_REDIS_SERVER or PM_WITHDRAWAL_REDIS_URL for the TSP-1 ledger cases")


class Rig:
    """One Redis, two venue processes, one subscriber reading what was SENT."""

    def __init__(self, client, listener, monkeypatch, fake_clock):
        self.client = client
        self.listener = listener
        self.monkeypatch = monkeypatch
        self.fake_clock = fake_clock
        self.sent: list[dict] = []
        self.stats: dict = {}
        self.k = self.p = None

    async def call(self, *args):
        return await self.client.execute_command(*args)

    @staticmethod
    def channel(event_id):
        return f"tsp1:ev:{event_id}"

    def use(self, **kwargs):
        self.monkeypatch.setattr(blend_preview, "LEDGER_SCRIPT", _script(**kwargs))

    async def clock(self, ms):
        await self.client.set(CLOCK_KEY, str(ms))

    def registry(self, max_s=60.0):
        return blend_preview.LedgerRegistry(sources=SOURCES, max_uncommitted_s=max_s,
                                            clock=lambda: 0.0)

    async def run(self, reg, ops):
        await reg.execute(ops, self.call, self.channel, self.stats)
        return await self.drain()

    async def drain(self):
        got = []
        while True:
            message = await self.listener.get_message(ignore_subscribe_messages=True, timeout=0.05)
            if message is None:
                break
            got.append(json.loads(message["data"]))
        self.sent.extend(got)
        return got

    async def hget(self, field):
        value = await self.client.hget(blend_preview.LEDGER_KEY, field)
        return None if value is None else value.decode()


@pytest.fixture
async def rig(redis_kwargs, monkeypatch, request):
    from redis.asyncio import Redis

    fake_clock = getattr(request, "param", None) == "fake_clock"
    client = Redis(**redis_kwargs)
    pubsub_client = Redis(**redis_kwargs)
    listener = pubsub_client.pubsub()
    await listener.psubscribe("tsp1:ev:*")
    await listener.get_message(timeout=0.2)  # the psubscribe confirmation
    r = Rig(client, listener, monkeypatch, fake_clock)
    r.use(fake_clock=fake_clock)
    # Production already holds the single-source counter; ledger epochs rise above it.
    await client.set(blend_preview.FENCE_EPOCH_KEY, "41")
    if fake_clock:
        await r.clock(1_000_000)
    r.k, r.p = r.registry(), r.registry()
    await r.k.claim(r.call, "kalshi")
    await r.p.claim(r.call, "polymarket")
    try:
        yield r
    finally:
        await listener.aclose() if hasattr(listener, "aclose") else await listener.close()
        await pubsub_client.aclose() if hasattr(pubsub_client, "aclose") else await pubsub_client.close()
        await client.aclose() if hasattr(client, "aclose") else await client.close()


def _ev(status="live"):
    return SimpleNamespace(status=status, espn_win_prob_home=None, opening_home_probability=None)


def _stamp(seconds=0):
    return NOW + timedelta(seconds=seconds)


def _propose(reg, source, value, *, rev=10, base=BASE10, status="live", basis_s=1.0,
             event_id=EV):
    return reg.propose(
        event_id, source, value=value, event=_ev(status), row_sources=base, row_rev=rev,
        observed_basis={f"{source}-1": NOW.timestamp() - 30 + basis_s},
        stamped_at=_stamp(basis_s),
    )


def _expected(base, pending):
    bag = dict(base)
    for name, (value, at) in pending.items():
        bag = stamp_source_reading(bag, name, value, now=at,
                                   observed_basis={f"{name}-1": NOW.timestamp() - 30 + (at - NOW).total_seconds()})
    shim = SimpleNamespace(win_probability_sources=bag, status="live",
                           espn_win_prob_home=None, opening_home_probability=None)
    return compute_aggregate_probability(shim, "live")


def _blends(frames):
    return [f for f in frames if f["preview"]["kind"] == "blend"]


class Reader:
    """Test oracle: the unchanged reader rules (frontend/lib/blendPreview.ts)."""

    def __init__(self):
        self.epoch, self.held = -1, None

    def after(self, frame, now_ms=0):
        preview = frame["preview"]
        if preview["epoch"] < self.epoch:
            return
        held = None if preview["epoch"] > self.epoch else self.held
        self.epoch = preview["epoch"]
        if preview["kind"] == "revoke":
            if held is not None and held["seq"] <= preview["through_seq"]:
                held = None
        elif held is None or preview["seq"] > held["seq"]:
            held = {"seq": preview["seq"], "p": frame["p"],
                    "expires": now_ms + preview["ttl_ms"], "pending": preview["pending"]}
        self.held = held


# ----------------------------------------------------------------------- G1


class TestComposition:
    async def test_the_last_writers_frame_carries_both_pending_values(self, rig):
        first = await rig.run(rig.k, _propose(rig.k, "kalshi", 0.6))
        second = await rig.run(rig.p, _propose(rig.p, "polymarket", 0.7, basis_s=2))
        [a], [b] = _blends(first), _blends(second)
        assert a["preview"]["pending"] == {"kalshi": 0.6}
        assert b["preview"]["pending"] == {"kalshi": 0.6, "polymarket": 0.7}
        # One identity domain: the event's generation, sequence 1 then 2.
        assert a["preview"]["epoch"] == b["preview"]["epoch"] > 41
        assert (a["preview"]["seq"], b["preview"]["seq"]) == (1, 2)
        assert b["p"] == pytest.approx(_expected(BASE10, {"kalshi": (0.6, _stamp(1)),
                                                          "polymarket": (0.7, _stamp(2))}))
        assert b["preview"]["pending_entries"] is None  # folded readers refuse (limit 7)
        assert b["preview"]["ttl_ms"] > 0 and isinstance(b["preview"]["ttl_ms"], int)

    async def test_a_composition_overtaken_by_a_newer_write_is_never_sent(self, rig):
        stale = await rig.k.prepare(_propose(rig.k, "kalshi", 0.6), rig.call, rig.stats)
        await rig.run(rig.p, _propose(rig.p, "polymarket", 0.7, basis_s=2))
        for frame in stale:
            await rig.k._publish(frame, rig.call, rig.channel, rig.stats)
        sent = await rig.drain()
        assert sent == [] and rig.stats["ledger_superseded"] == 1
        reader = Reader()
        for frame in rig.sent:
            reader.after(frame)
        assert reader.held["pending"] == {"kalshi": 0.6, "polymarket": 0.7}

    async def test_folded_projection_refuses_ledger_frames(self, rig):
        from app.utils.folded_blend_preview import FoldedPreviewBase

        [frame] = _blends(await rig.run(rig.k, _propose(rig.k, "kalshi", 0.6)))
        base = FoldedPreviewBase(EV, dict(BASE10), {"kalshi": EV}, {str(EV): 10, "8": 3},
                                 {"status": "live", "home_score": None, "away_score": None,
                                  "completed_at": None, "espn_win_prob_home": None,
                                  "opening_home_probability": None,
                                  "opening_away_probability": None, "commence_time": None},
                                 "baseball_mlb")
        assert base.project(frame, members={EV, 8}, floors={}) is None
        frame2 = _blends(await rig.run(rig.p, _propose(rig.p, "polymarket", 0.7, basis_s=2)))[0]
        assert set(frame2["preview"]["pending"]) == SOURCES
        assert base.project(frame2, members={EV, 8}, floors={}) is None


class TestCommittedFloor:
    async def test_a_commit_republishes_the_sibling_on_the_new_base(self, rig):
        await rig.run(rig.k, _propose(rig.k, "kalshi", 0.6))
        await rig.run(rig.p, _propose(rig.p, "polymarket", 0.7, basis_s=2))
        seq = rig.p.pending_seq(EV, "polymarket")
        bag11 = stamp_source_reading(dict(BASE10), "polymarket", 0.7, now=_stamp(2))
        [frame] = await rig.run(rig.p, rig.p.committed(EV, "polymarket", seq=seq, sources=bag11,
                                                         rev=11, event=_ev()))
        assert frame["preview"]["base_rev"] == 11
        assert frame["preview"]["pending"] == {"kalshi": 0.6}

    async def test_a_stale_base_sibling_composes_on_the_committed_floor(self, rig):
        """Review condition 4: PM commits 11; Kalshi still holds its rev-10 row."""
        await rig.run(rig.p, _propose(rig.p, "polymarket", 0.7, basis_s=2))
        seq = rig.p.pending_seq(EV, "polymarket")
        bag11 = stamp_source_reading(dict(BASE10), "polymarket", 0.7, now=_stamp(2))
        await rig.run(rig.p, rig.p.committed(EV, "polymarket", seq=seq, sources=bag11,
                                             rev=11, event=_ev()))
        # Kalshi's next attempt read its row BEFORE PM's commit (rev 10).
        [frame] = _blends(await rig.run(rig.k, _propose(rig.k, "kalshi", 0.62, rev=10)))
        assert frame["preview"]["base_rev"] == 11, "never composed on the older committed bag"
        assert frame["p"] == pytest.approx(_expected(bag11, {"kalshi": (0.62, _stamp(1))}))
        reader = Reader()
        for f in rig.sent:
            reader.after(f)
        assert reader.held is not None and reader.held["p"] == frame["p"]

    async def test_a_stale_base_never_drops_an_unrelated_pending_entry(self, rig):
        await rig.run(rig.p, _propose(rig.p, "polymarket", 0.7, basis_s=2))
        # Kalshi commits rev 11 (its own value); PM's pending value is unrelated.
        bag11 = stamp_source_reading(dict(BASE10), "kalshi", 0.55, now=_stamp(0))
        [frame] = await rig.run(rig.k, rig.k.committed(EV, "kalshi", seq=None, sources=bag11,
                                                         rev=11, event=_ev()))
        assert frame["preview"]["pending"] == {"polymarket": 0.7}
        assert frame["preview"]["base_rev"] == 11


class TestOwnership:
    async def test_a_replaced_owners_entry_and_delayed_commit_lose(self, rig):
        await rig.run(rig.k, _propose(rig.k, "kalshi", 0.6))
        old_seq = rig.k.pending_seq(EV, "kalshi")
        replacement = rig.registry()
        await replacement.claim(rig.call, "kalshi")
        # The old process is fenced at Redis, for proposals and for settlement.
        assert await rig.run(rig.k, _propose(rig.k, "kalshi", 0.61, basis_s=3)) == []
        await rig.run(replacement, _propose(replacement, "kalshi", 0.64, basis_s=4))
        mine = await rig.hget(f"e:{EV}:m:kalshi")
        assert mine.split()[0] == str(replacement.claims["kalshi"])
        # Old owner's delayed commit (any through_seq) cannot delete the replacement's entry.
        await rig.run(rig.k, [rig.k._settle_op(EV, "kalshi", old_seq + 50, "unorderable")])
        assert await rig.hget(f"e:{EV}:m:kalshi") == mine
        [frame] = _blends(await rig.run(rig.p, _propose(rig.p, "polymarket", 0.7, basis_s=5)))
        assert frame["preview"]["pending"] == {"kalshi": 0.64, "polymarket": 0.7}

    async def test_an_entry_whose_owner_left_is_pruned_not_composed(self, rig):
        await rig.run(rig.k, _propose(rig.k, "kalshi", 0.6))
        await rig.client.hdel(blend_preview.LEDGER_KEY, "owner:kalshi")
        [frame] = _blends(await rig.run(rig.p, _propose(rig.p, "polymarket", 0.7, basis_s=2)))
        assert frame["preview"]["pending"] == {"polymarket": 0.7}
        assert await rig.hget(f"e:{EV}:m:kalshi") is None

    async def test_settle_deletes_only_this_owners_entry_through_its_sequence(self, rig):
        """A same-owner entry newer than the commit's sequence stays."""
        await rig.run(rig.k, _propose(rig.k, "kalshi", 0.6))
        first = rig.k.pending_seq(EV, "kalshi")
        await rig.run(rig.k, _propose(rig.k, "kalshi", 0.62, basis_s=2))
        assert rig.k.pending_seq(EV, "kalshi") > first
        await rig.run(rig.k, [rig.k._settle_op(EV, "kalshi", first, "unorderable")])
        assert await rig.hget(f"e:{EV}:m:kalshi") is not None
        # Another owner's settle never deletes it either.
        await rig.run(rig.p, [rig.p._settle_op(EV, "kalshi", 10**6, "unorderable")])
        assert await rig.hget(f"e:{EV}:m:kalshi") is not None


class TestChains:
    async def test_older_local_sequences_and_repeated_opens_are_refused(self, rig):
        open_ops = _propose(rig.k, "kalshi", 0.6)
        continue_ops = _propose(rig.k, "kalshi", 0.62, basis_s=2)
        assert open_ops[0]["mode"] == "open" and continue_ops[0]["mode"] == "continue"
        await rig.run(rig.k, open_ops)
        await rig.run(rig.k, continue_ops)
        before = await rig.hget(f"e:{EV}:m:kalshi")
        # Delayed duplicate of the continue, then a delayed re-send of the open.
        assert await rig.run(rig.k, [dict(continue_ops[0])]) == []
        assert await rig.run(rig.k, [dict(open_ops[0])]) == []
        assert await rig.hget(f"e:{EV}:m:kalshi") == before
        assert rig.stats["ledger_refused"] == 2

    @pytest.mark.parametrize("rig", ["fake_clock"], indirect=True)
    async def test_an_open_reusing_a_stored_chain_never_renews_its_deadline(self, rig):
        """A crafted/replayed open: same chain, higher local sequence."""
        [op] = _propose(rig.k, "kalshi", 0.6)
        await rig.run(rig.k, [op])
        before = await rig.hget(f"e:{EV}:m:kalshi")
        await rig.clock(1_030_000)
        assert await rig.run(rig.k, [{**op, "local_seq": op["local_seq"] + 5}]) == []
        assert await rig.hget(f"e:{EV}:m:kalshi") == before
        assert rig.stats["ledger_refused"] == 1

    async def test_a_continue_whose_chain_is_missing_never_opens_a_lifetime(self, rig):
        await rig.run(rig.k, _propose(rig.k, "kalshi", 0.6))
        await rig.client.hdel(blend_preview.LEDGER_KEY, f"e:{EV}:m:kalshi", f"e:{EV}:p:kalshi")
        ops = _propose(rig.k, "kalshi", 0.6, basis_s=2)
        assert ops[0]["mode"] == "continue"
        assert await rig.run(rig.k, ops) == []
        assert await rig.hget(f"e:{EV}:m:kalshi") is None
        # The same value is not re-proposed until a commit, refusal or new value.
        assert _propose(rig.k, "kalshi", 0.6, basis_s=3) == []

    @pytest.mark.parametrize("rig", ["fake_clock"], indirect=True)
    async def test_a_chain_deadline_is_fixed_across_retries(self, rig):
        await rig.run(rig.k, _propose(rig.k, "kalshi", 0.6))
        deadline = int((await rig.hget(f"e:{EV}:m:kalshi")).split()[3])
        assert deadline == 1_000_000 + 60_000
        await rig.clock(1_030_000)
        [frame] = _blends(await rig.run(rig.k, _propose(rig.k, "kalshi", 0.61, basis_s=2)))
        assert int((await rig.hget(f"e:{EV}:m:kalshi")).split()[3]) == deadline
        assert frame["preview"]["ttl_ms"] == 30_000
        await rig.clock(deadline)
        assert _blends(await rig.run(rig.k, _propose(rig.k, "kalshi", 0.61, basis_s=3))) == []
        assert await rig.hget(f"e:{EV}:m:kalshi") is None
        assert _propose(rig.k, "kalshi", 0.61, basis_s=4) == [], "expired value never re-opens"


class TestPublicationRevalidation:
    @pytest.mark.parametrize("rig", ["fake_clock"], indirect=True)
    async def test_a_contributor_that_expires_during_composition_is_not_sent(self, rig):
        await rig.run(rig.k, _propose(rig.k, "kalshi", 0.6))            # deadline 1,060,000
        await rig.clock(1_050_000)
        frames = await rig.p.prepare(_propose(rig.p, "polymarket", 0.7, basis_s=2),
                                     rig.call, rig.stats)               # deadline 1,110,000
        assert set(frames[0]["preview"]["pending"]) == SOURCES
        await rig.clock(1_060_000)
        for frame in frames:
            await rig.p._publish(frame, rig.call, rig.channel, rig.stats)
        sent = await rig.drain()
        assert [f["preview"]["pending"] for f in sent] == [{"polymarket": 0.7}]
        assert sent[0]["preview"]["ttl_ms"] == 50_000
        assert rig.stats["ledger_recomposed"] == 1

    async def test_a_sibling_owner_lost_after_the_read_set_is_not_sent(self, rig):
        await rig.run(rig.k, _propose(rig.k, "kalshi", 0.6))
        frames = await rig.p.prepare(_propose(rig.p, "polymarket", 0.7, basis_s=2),
                                     rig.call, rig.stats)
        seq_before = await rig.hget(f"e:{EV}:seq")
        await rig.client.hdel(blend_preview.LEDGER_KEY, "owner:kalshi")  # no seq/counter change
        assert await rig.hget(f"e:{EV}:seq") == seq_before
        for frame in frames:
            await rig.p._publish(frame, rig.call, rig.channel, rig.stats)
        sent = await rig.drain()
        assert [f["preview"]["pending"] for f in sent] == [{"polymarket": 0.7}]

    @pytest.mark.parametrize("rig", ["fake_clock"], indirect=True)
    async def test_the_readers_ttl_is_computed_at_the_final_send(self, rig):
        frames = await rig.k.prepare(_propose(rig.k, "kalshi", 0.6), rig.call, rig.stats)
        await rig.clock(1_005_000)
        for frame in frames:
            await rig.k._publish(frame, rig.call, rig.channel, rig.stats)
        [sent] = await rig.drain()
        assert sent["preview"]["ttl_ms"] == 55_000


class TestTerminal:
    async def test_terminal_is_a_tombstone_with_one_ordered_revoke(self, rig):
        await rig.run(rig.k, _propose(rig.k, "kalshi", 0.6))
        await rig.run(rig.p, _propose(rig.p, "polymarket", 0.7, basis_s=2))
        [revoke] = await rig.run(rig.p, _propose(rig.p, "polymarket", 0.7, rev=12,
                                                 status="final", basis_s=3))
        assert revoke["preview"]["kind"] == "revoke"
        assert revoke["preview"]["through_seq"] == revoke["preview"]["seq"] - 1
        assert await rig.hget(f"e:{EV}:term") == "12"
        assert await rig.hget(f"e:{EV}:m:kalshi") is None
        # Kalshi's delayed pre-terminal proposals (read at rev 11 and 12) recreate nothing.
        assert await rig.run(rig.k, _propose(rig.k, "kalshi", 0.61, rev=11, basis_s=4)) == []
        assert await rig.run(rig.k, _propose(rig.k, "kalshi", 0.62, rev=12, basis_s=5)) == []
        assert await rig.hget(f"e:{EV}:m:kalshi") is None
        reader = Reader()
        for frame in rig.sent:
            reader.after(frame)
        assert reader.held is None

    async def test_a_delayed_terminal_never_erases_a_newer_reopening(self, rig):
        await rig.run(rig.p, _propose(rig.p, "polymarket", 0.7, rev=12, status="final"))
        # A newer authoritative live status (rev 13) may reopen.
        [frame] = _blends(await rig.run(rig.k, _propose(rig.k, "kalshi", 0.6, rev=13)))
        assert await rig.hget(f"e:{EV}:term") is None
        # The rev-12 terminal observation arrives late, from the other arm.
        assert await rig.run(rig.p, _propose(rig.p, "polymarket", 0.7, rev=12,
                                             status="final", basis_s=2)) == []
        assert await rig.hget(f"e:{EV}:term") is None
        assert await rig.hget(f"e:{EV}:m:kalshi") is not None
        reader = Reader()
        for f in rig.sent:
            reader.after(f)
        assert reader.held["seq"] == frame["preview"]["seq"]


class TestRevokeIdentity:
    async def test_a_delayed_revoke_never_revokes_a_newer_sibling_preview(self, rig):
        await rig.run(rig.k, _propose(rig.k, "kalshi", 0.6))
        [revoke] = await rig.run(rig.k, rig.k.refused(EV, "kalshi", "error"))
        [newer] = _blends(await rig.run(rig.p, _propose(rig.p, "polymarket", 0.7, basis_s=2)))
        assert revoke["preview"]["epoch"] == newer["preview"]["epoch"]
        assert revoke["preview"]["through_seq"] < newer["preview"]["seq"]
        reader = Reader()
        for frame in (newer, revoke):  # the revoke arrives late
            reader.after(frame)
        assert reader.held is not None and reader.held["seq"] == newer["preview"]["seq"]


class TestAuthority:
    async def test_whole_ledger_loss_stops_previews_until_explicit_reinitialization(self, rig):
        await rig.run(rig.k, _propose(rig.k, "kalshi", 0.6))
        await rig.client.delete(blend_preview.LEDGER_KEY)
        assert await rig.run(rig.p, _propose(rig.p, "polymarket", 0.7, basis_s=2)) == []
        assert await rig.run(rig.k, _propose(rig.k, "kalshi", 0.6, basis_s=3)) == []
        fresh = rig.registry()
        with pytest.raises(RuntimeError, match="lost"):
            await fresh.claim(rig.call, "kalshi")
        assert await rig.client.exists(blend_preview.LEDGER_KEY) == 0

    async def test_a_lost_epoch_field_or_global_counter_never_restarts_from_zero(self, rig):
        [before] = _blends(await rig.run(rig.k, _propose(rig.k, "kalshi", 0.6)))
        await rig.client.delete(blend_preview.FENCE_EPOCH_KEY)  # the shared counter
        fresh = rig.registry()
        claim = await fresh.claim(rig.call, "polymarket")
        assert claim > before["preview"]["epoch"]
        await rig.client.hdel(blend_preview.LEDGER_KEY, "epoch")
        assert await rig.run(rig.k, _propose(rig.k, "kalshi", 0.62, basis_s=2)) == []
        with pytest.raises(RuntimeError, match="lost"):
            await rig.registry().claim(rig.call, "kalshi")

    async def test_first_use_refuses_when_single_source_owners_survive_a_lost_counter(self, rig):
        await rig.client.flushdb()
        await rig.client.set(blend_preview.fence_owner_key("polymarket"), "40")
        with pytest.raises(RuntimeError, match="lost"):
            await rig.registry().claim(rig.call, "polymarket")
        await rig.client.set(blend_preview.FENCE_EPOCH_KEY, "40")
        assert await rig.registry().claim(rig.call, "polymarket") == 41

    @pytest.mark.parametrize("value,expected", [("01", "malformed"), ("4.0", "malformed"),
                                                ("9007199254740992", "malformed"),
                                                ("9007199254740991", "exhausted")])
    async def test_malformed_or_exhausted_authority_refuses(self, rig, value, expected):
        await rig.client.hset(blend_preview.LEDGER_KEY, "epoch", value)
        await rig.client.set(blend_preview.FENCE_EPOCH_KEY, "1")
        with pytest.raises(RuntimeError, match=expected):
            await rig.registry().claim(rig.call, "kalshi")

    @pytest.mark.parametrize("rig", ["fake_clock"], indirect=True)
    async def test_frozen_or_rolled_back_redis_time_never_reorders_frames(self, rig):
        [a] = _blends(await rig.run(rig.k, _propose(rig.k, "kalshi", 0.6)))
        await rig.clock(900_000)  # Redis time steps back 100 s
        [b] = _blends(await rig.run(rig.p, _propose(rig.p, "polymarket", 0.7, basis_s=2)))
        [c] = _blends(await rig.run(rig.k, _propose(rig.k, "kalshi", 0.61, basis_s=3)))
        ids = [(f["preview"]["epoch"], f["preview"]["seq"]) for f in (a, b, c)]
        assert ids == sorted(ids) and len(set(ids)) == 3
        # Deleting the ledger at a frozen millisecond replays nothing.
        await rig.client.delete(blend_preview.LEDGER_KEY)
        assert await rig.run(rig.p, _propose(rig.p, "polymarket", 0.71, basis_s=4)) == []


class TestFaults:
    async def test_a_fault_after_the_sequence_moves_fails_older_read_sets(self, rig):
        await rig.run(rig.k, _propose(rig.k, "kalshi", 0.6))
        older = await rig.p.prepare(_propose(rig.p, "polymarket", 0.7, basis_s=2),
                                    rig.call, rig.stats)
        seq = await rig.hget(f"e:{EV}:seq")
        rig.use(fault="propose")
        with pytest.raises(Exception, match="injected fault"):
            await rig.k.execute(_propose(rig.k, "kalshi", 0.62, basis_s=3), rig.call,
                                rig.channel, rig.stats)
        assert int(await rig.hget(f"e:{EV}:seq")) == int(seq) + 1
        rig.use()
        for frame in older:
            await rig.p._publish(frame, rig.call, rig.channel, rig.stats)
        assert await rig.drain() == []
        # The unknown write is treated as possibly made: Kalshi's next value
        # continues the chain it believes it opened, and Redis (which kept the
        # 0.6 entry) accepts it; nothing re-opens a lifetime.
        [frame] = _blends(await rig.run(rig.k, _propose(rig.k, "kalshi", 0.63, basis_s=4)))
        assert frame["preview"]["pending"] == {"kalshi": 0.63, "polymarket": 0.7}

    async def test_a_settle_fault_leaves_the_sequence_ahead(self, rig):
        await rig.run(rig.k, _propose(rig.k, "kalshi", 0.6))
        older = await rig.p.prepare(_propose(rig.p, "polymarket", 0.7, basis_s=2),
                                    rig.call, rig.stats)
        rig.use(fault="settle")
        with pytest.raises(Exception, match="injected fault"):
            await rig.k.execute(rig.k.refused(EV, "kalshi", "error"), rig.call,
                                rig.channel, rig.stats)
        rig.use()
        for frame in older:
            await rig.p._publish(frame, rig.call, rig.channel, rig.stats)
        assert await rig.drain() == []


class TestModeReturn:
    """Root's R1 countercase: ledger → single-source → ledger while a page stays open."""

    async def _legacy_claim(self, rig, source="kalshi"):
        # The existing single-source claim: INCR the shared counter + SET its owner.
        return int(await rig.call("EVAL", blend_preview.FENCE_CLAIM_SCRIPT, 2,
                                  blend_preview.FENCE_EPOCH_KEY,
                                  blend_preview.fence_owner_key(source)))

    async def test_a_ledger_frame_after_a_single_source_epoch_rises_above_it(self, rig):
        [first] = _blends(await rig.run(rig.k, _propose(rig.k, "kalshi", 0.6)))
        reader = Reader()
        reader.after(first)
        legacy = await self._legacy_claim(rig)
        assert legacy > first["preview"]["epoch"]
        # A held reader that received a single-source frame keeps floor `legacy`.
        reader.after({"p": 0.55, "preview": {"kind": "blend", "epoch": legacy, "seq": 1,
                                             "ttl_ms": 60000, "pending": {"kalshi": 0.55}}})
        back = rig.registry()
        claim = await back.claim(rig.call, "kalshi")
        assert claim > legacy
        [frame] = _blends(await rig.run(back, _propose(back, "kalshi", 0.62, basis_s=2)))
        assert frame["preview"]["epoch"] > claim > legacy
        assert int(await rig.hget(f"e:{EV}:gen")) == frame["preview"]["epoch"]
        reader.after(frame)
        assert reader.held is not None and reader.held["p"] == frame["p"]
        # The sequence keeps rising across the new generation.
        assert frame["preview"]["seq"] > first["preview"]["seq"]

    async def test_the_new_generation_keeps_every_pending_entry_and_fences_older_work(self, rig):
        await rig.run(rig.k, _propose(rig.k, "kalshi", 0.6))
        [before] = _blends(await rig.run(rig.p, _propose(rig.p, "polymarket", 0.7, basis_s=2)))
        # Prepared under the old generation, delivered late.
        late = await rig.p.prepare(_propose(rig.p, "polymarket", 0.71, basis_s=3),
                                   rig.call, rig.stats)
        legacy = await self._legacy_claim(rig)
        reader = Reader()
        reader.after(before)
        reader.after({"p": 0.5, "preview": {"kind": "blend", "epoch": legacy, "seq": 9,
                                            "ttl_ms": 60000, "pending": {"kalshi": 0.5}}})
        back = rig.registry()
        await back.claim(rig.call, "kalshi")
        [frame] = _blends(await rig.run(back, _propose(back, "kalshi", 0.63, basis_s=4)))
        # Polymarket's process never restarted: its pending value composes in.
        assert frame["preview"]["pending"] == {"kalshi": 0.63, "polymarket": 0.71}
        reader.after(frame)
        assert reader.held["p"] == frame["p"]
        for old in late:
            await rig.p._publish(old, rig.call, rig.channel, rig.stats)
        assert await rig.drain() == []
        # An old-generation revoke, delivered late, is below the new floor.
        reader.after({"p": None, "preview": {"kind": "revoke", "epoch": before["preview"]["epoch"],
                                             "seq": 99, "through_seq": 98}})
        assert reader.held["p"] == frame["p"]

    async def test_a_delayed_sibling_claim_moves_the_generation_again(self, rig):
        await rig.run(rig.k, _propose(rig.k, "kalshi", 0.6))
        [a] = _blends(await rig.run(rig.p, _propose(rig.p, "polymarket", 0.7, basis_s=2)))
        # Polymarket restarts later: a new owner claim; its old entry is pruned.
        restarted = rig.registry()
        await restarted.claim(rig.call, "polymarket")
        [b] = _blends(await rig.run(rig.k, _propose(rig.k, "kalshi", 0.61, basis_s=3)))
        assert b["preview"]["epoch"] > a["preview"]["epoch"]
        assert b["preview"]["pending"] == {"kalshi": 0.61}
        [c] = _blends(await rig.run(restarted, _propose(restarted, "polymarket", 0.72, basis_s=4)))
        assert c["preview"]["epoch"] == b["preview"]["epoch"]
        assert c["preview"]["seq"] == b["preview"]["seq"] + 1
        assert c["preview"]["pending"] == {"kalshi": 0.61, "polymarket": 0.72}
        reader = Reader()
        for f in rig.sent:
            reader.after(f)
        assert reader.held["seq"] == c["preview"]["seq"]

    async def test_a_settle_after_a_newer_claim_revokes_in_the_new_generation(self, rig):
        [a] = _blends(await rig.run(rig.k, _propose(rig.k, "kalshi", 0.6)))
        legacy = await self._legacy_claim(rig, "polymarket")
        [revoke] = await rig.run(rig.k, rig.k.refused(EV, "kalshi", "error"))
        assert revoke["preview"]["kind"] == "revoke"
        assert revoke["preview"]["epoch"] > legacy > a["preview"]["epoch"]
        reader = Reader()
        reader.after({"p": 0.5, "preview": {"kind": "blend", "epoch": legacy, "seq": 3,
                                            "ttl_ms": 60000, "pending": {"polymarket": 0.5}}})
        reader.after(revoke)
        assert reader.epoch == revoke["preview"]["epoch"] and reader.held is None


# ------------------------------------------------------------- off path (G4)


class TestSwitch:
    def test_unset_leaves_the_single_source_path(self, monkeypatch):
        monkeypatch.delenv(blend_preview.LEDGER_SOURCES_ENV, raising=False)
        monkeypatch.setenv(blend_preview.SOURCE_ENV, "polymarket")
        monkeypatch.setenv(blend_preview.EVENT_IDS_ENV, "7")
        blend_preview.reset_registry_for_tests()
        try:
            assert type(blend_preview.registry()) is blend_preview.PreviewRegistry
            assert blend_preview.preview_events_for("polymarket") == frozenset({7})
            assert blend_preview.preview_events_for("kalshi") == frozenset()
        finally:
            blend_preview.reset_registry_for_tests()

    def test_set_names_both_sources_and_ignores_the_single_switch(self, monkeypatch):
        monkeypatch.setenv(blend_preview.LEDGER_SOURCES_ENV, "kalshi, polymarket")
        monkeypatch.setenv(blend_preview.SOURCE_ENV, "polymarket")
        monkeypatch.setenv(blend_preview.EVENT_IDS_ENV, "7")
        blend_preview.reset_registry_for_tests()
        try:
            assert blend_preview.preview_source() is None
            assert isinstance(blend_preview.registry(), blend_preview.LedgerRegistry)
            assert blend_preview.preview_events_for("kalshi") == frozenset({7})
            assert blend_preview.preview_events_for("polymarket") == frozenset({7})
            assert blend_preview.preview_route_events() == frozenset({7})
        finally:
            blend_preview.reset_registry_for_tests()

    @pytest.mark.parametrize("raw", ["kalshi,", "kalshi,espn", "Kalshi", ","])
    def test_a_malformed_list_turns_every_preview_off(self, monkeypatch, raw):
        monkeypatch.setenv(blend_preview.LEDGER_SOURCES_ENV, raw)
        monkeypatch.setenv(blend_preview.SOURCE_ENV, "polymarket")
        monkeypatch.setenv(blend_preview.EVENT_IDS_ENV, "7")
        assert blend_preview.preview_events_for("kalshi") == frozenset()
        assert blend_preview.preview_events_for("polymarket") == frozenset()
        assert blend_preview.preview_route_events() == frozenset()


# ---------------------------------------------------- the refresher boundary


class TestRefresherBoundary:
    async def test_frames_keep_the_ledger_generation_not_the_process_claim(
        self, redis_kwargs, monkeypatch,
    ):
        """Condition 6: ledger mode bypasses `_publish_previews`' epoch overwrite."""
        from redis.asyncio import Redis

        from app.tasks.live_blend_refresh import LiveBlendRefresher

        monkeypatch.setenv(blend_preview.LEDGER_SOURCES_ENV, "kalshi,polymarket")
        monkeypatch.setenv(blend_preview.EVENT_IDS_ENV, str(EV))
        blend_preview.reset_registry_for_tests()
        client = Redis(**redis_kwargs)
        listener_client = Redis(**redis_kwargs)
        listener = listener_client.pubsub()
        try:
            from app.utils.live_push import event_channel

            await client.set(blend_preview.FENCE_EPOCH_KEY, "41")
            await listener.subscribe(event_channel(EV))
            await listener.get_message(timeout=0.2)
            refresher = LiveBlendRefresher("kalshi")
            assert refresher.preview and refresher.preview_events == frozenset({EV})
            monkeypatch.setattr(refresher, "_client", lambda: client)
            # Another process claims polymarket first, so claims and generations differ.
            other = blend_preview.LedgerRegistry(sources=SOURCES)
            await other.claim(lambda *a: client.execute_command(*a), "polymarket")
            claim = await refresher.claim_preview_display()
            preview = blend_preview.registry()
            await refresher._publish_previews(_propose(preview, "kalshi", 0.6))
            message = await listener.get_message(ignore_subscribe_messages=True, timeout=1)
            frame = json.loads(message["data"])
            assert frame["preview"]["kind"] == "blend"
            assert frame["preview"]["epoch"] == int(await client.hget(blend_preview.LEDGER_KEY,
                                                                     f"e:{EV}:gen"))
            assert frame["preview"]["epoch"] != claim
            assert refresher.preview_stats["published"] == 1
            settled = await refresher._prepare_ledger_previews(
                preview.refused(EV, "kalshi", "error"))
            assert [f["preview"]["kind"] for f in settled] == ["revoke"]
            await refresher._publish_previews(settled)
            message = await listener.get_message(ignore_subscribe_messages=True, timeout=1)
            revoke = json.loads(message["data"])
            assert revoke["preview"]["epoch"] == frame["preview"]["epoch"]
            assert revoke["preview"]["through_seq"] == frame["preview"]["seq"]
        finally:
            blend_preview.reset_registry_for_tests()
            for c in (listener, listener_client, client):
                await (c.aclose() if hasattr(c, "aclose") else c.close())

    async def test_a_page_stays_current_across_ledger_single_source_ledger_switches(
        self, redis_kwargs, monkeypatch,
    ):
        """Root's R1 countercase through the real refresher, both modes, page held open."""
        from redis.asyncio import Redis

        from app.tasks.live_blend_refresh import LiveBlendRefresher
        from app.utils.live_push import event_channel

        client = Redis(**redis_kwargs)
        listener_client = Redis(**redis_kwargs)
        listener = listener_client.pubsub()

        def mode(ledger: bool):
            if ledger:
                monkeypatch.setenv(blend_preview.LEDGER_SOURCES_ENV, "kalshi,polymarket")
                monkeypatch.delenv(blend_preview.SOURCE_ENV, raising=False)
            else:
                monkeypatch.delenv(blend_preview.LEDGER_SOURCES_ENV, raising=False)
                monkeypatch.setenv(blend_preview.SOURCE_ENV, "kalshi")
            monkeypatch.setenv(blend_preview.EVENT_IDS_ENV, str(EV))
            blend_preview.reset_registry_for_tests()  # a restarted process
            refresher = LiveBlendRefresher("kalshi")
            assert refresher.preview
            monkeypatch.setattr(refresher, "_client", lambda: client)
            return refresher, blend_preview.registry()

        async def received():
            message = await listener.get_message(ignore_subscribe_messages=True, timeout=1)
            assert message is not None, "nothing was published"
            return json.loads(message["data"])

        try:
            await client.set(blend_preview.FENCE_EPOCH_KEY, "41")
            await listener.subscribe(event_channel(EV))
            await listener.get_message(timeout=0.2)
            page = Reader()
            # The Polymarket process stays on ledger mode throughout (claimed once).
            pm = blend_preview.LedgerRegistry(sources=SOURCES)
            pm_call = lambda *a: client.execute_command(*a)  # noqa: E731
            await pm.claim(pm_call, "polymarket")

            refresher, preview = mode(ledger=True)
            await refresher._publish_previews(_propose(preview, "kalshi", 0.6))
            first = await received()
            page.after(first)
            await pm.execute(_propose(pm, "polymarket", 0.7, basis_s=2), pm_call,
                             event_channel, {})
            page.after(await received())

            refresher, preview = mode(ledger=False)
            await refresher._publish_previews(_propose(preview, "kalshi", 0.61, basis_s=3))
            legacy = await received()
            assert legacy["preview"]["epoch"] > first["preview"]["epoch"]
            page.after(legacy)
            assert page.held["p"] == legacy["p"]

            refresher, preview = mode(ledger=True)
            await refresher._publish_previews(_propose(preview, "kalshi", 0.62, basis_s=4))
            back = await received()
            assert back["preview"]["kind"] == "blend"
            assert back["preview"]["epoch"] > legacy["preview"]["epoch"]
            assert back["preview"]["pending"] == {"kalshi": 0.62, "polymarket": 0.7}
            page.after(back)
            assert page.held is not None and page.held["p"] == back["p"]
            # A reconnect keeps the floor and holds nothing until the next frame.
            reconnected = Reader()
            reconnected.epoch = page.epoch
            await pm.execute(_propose(pm, "polymarket", 0.71, basis_s=5), pm_call,
                             event_channel, {})
            later = await received()
            for reader in (page, reconnected):
                reader.after(later)
                assert reader.held is not None and reader.held["p"] == later["p"]
            assert later["preview"]["pending"] == {"kalshi": 0.62, "polymarket": 0.71}
        finally:
            blend_preview.reset_registry_for_tests()
            for c in (listener, listener_client, client):
                await (c.aclose() if hasattr(c, "aclose") else c.close())
