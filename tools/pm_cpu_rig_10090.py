"""#10090 rig: CPU per 10k venue messages in the real Polymarket consumer.

    python3 tools/pm_cpu_rig_10090.py arm SECONDS [--warm S] [--profile OUT]
        [--gc MODE] [--refresh S] [--game-fps N] [--open-fps N] [--game-flush S]
    python3 tools/pm_cpu_rig_10090.py server PORT CERT KEY GAME_FPS OPEN_FPS  (spawned)
    python3 tools/pm_cpu_rig_10090.py redis PORT                              (spawned)
    RIG_PM_CPU_CHILD=1 ... (the open receiver child, spawned by the consumer)

A measurement instrument, not a CI test: one arm takes minutes, and it needs
``fakeredis`` (with ``lupa``), ``psutil`` and ``cryptography`` installed.

``arm`` runs the real ``_run_polymarket_ws_consumer`` the way production does
(in-process game client, the open-contract client received in its real child
process, book snapshots priced, a 0.25 s game flush) against a local TLS venue
(``server``, its own process) that streams production-shaped frames:
``price_change`` (both legs of a market, with their best bid/ask),
``best_bid_ask``, full-depth ``book``, rare ``last_trade_price`` and
``tick_size_change``, skewed so a few legs of each shard take most of the
traffic. Defaults are production's 13:12-13:13Z minute of 10/30: ~1,900 game
frames/s over ~5.2k legs and ~1,200 open frames/s over ~68k assets, of which
~6% tick (production's open backlog, 'deferred' ~3.3k rows/s, says ~7.5k legs
do; this rig's runs ~4.4-6.8k rows/s, so it overstates the backlog). Measure
after ``--warm`` >= 180 s: the subscribe dumps dirty every open leg and the
side flush drains them at ~500 rows/s.

The database is a fake that answers the consumer's reads from a fixed catalog,
waits ``STATEMENT_RTT_S`` per statement and RETURNs the rows a chunk's price
UPDATE would write. Every statement goes through SQLAlchemy's own cache-key /
compile-on-miss / bind path for the asyncpg dialect, so the statement-building
CPU production pays stays in; the driver's wire encoding does not. Market
invalidations publish to a Redis (fakeredis, its own process). The blend
refresher's stamp/publish is stubbed (as in the #11218 rig): this measures the
consumer's receive, per-message and flush path, NOT the refresher.

It measures ``SECONDS`` of THIS process only: CPU seconds, venue messages
handled (game frames received + open frames forwarded by the child), the event
loop's late wakes (a 0.25 s sleep, as the worker-ws heartbeat samples it),
every collection's pause by generation, RSS, and the consumer's own minute
counters as rates. One JSON line. ``--profile OUT`` writes a cProfile of the
window (coroutine "calls" there count resumptions).

``--gc``: ``default`` (whatever the consumer itself does); ``freeze``
(``gc.freeze()`` once after warm-up); ``thresh:A,B,C`` (``gc.set_threshold``).
``--refresh S`` runs a catalog handover every S seconds (production: ~5-11 min).
"""

import argparse
import asyncio
import cProfile
import gc
import json
import logging
import os
import random
import signal
import ssl
import subprocess
import sys
import time

# tools/ beside backend/: the instrument lives outside the collected test tree
# (it needs fakeredis, lupa, psutil and cryptography, which CI does not install).
BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
HERE = os.path.abspath(__file__)

SEED = 10090
EVENTS = 60
SLATE_MARKETS = 2_600   # ~5.2k game legs (production legs=5125-5330)
OPEN_MARKETS = 34_200   # ~68.4k open assets (production assets=68406)
GAME_FPS = 1_900.0      # production game msgs 115k/min at 13:12-13:13Z
OPEN_FPS = 1_200.0      # production open msgs 72k/min, same minute
READ_DELAY_S = 0.05
STATEMENT_RTT_S = 0.002  # every statement's round trip to the database
OPEN_ACTIVE = 0.06      # share of an open shard's assets that tick
GAME_MOVE = 0.015       # a tick moves the game book: ~350 rows/s written with liveness (13:12Z: 349)
OPEN_MOVE = 0.3


# ---------------------------------------------------------------- catalog ----

class Catalog:
    """The same markets in every process: built from SEED alone."""

    def __init__(self):
        rng = random.Random(SEED)
        self.next_mid, self.next_oid = 1_000_000, 50_000_000
        self.slate = [self._market(rng, "1", 14_000_000 + rng.randrange(EVENTS))
                      for _ in range(SLATE_MARKETS)]
        self.open = [self._market(rng, "2", None) for _ in range(OPEN_MARKETS)]
        self.by_mid = {}
        self.partner, self.condition = {}, {}
        for m in self.slate + self.open:
            a, b = m["tokens"]
            self.partner[a], self.partner[b] = b, a
            self.condition[a] = self.condition[b] = m["cond"]

    def _market(self, rng, prefix, event):
        mid, self.next_mid = self.next_mid, self.next_mid + 1
        oids, self.next_oid = (self.next_oid, self.next_oid + 1), self.next_oid + 2
        cond = "0x%064x" % rng.getrandbits(256)
        tokens = [prefix + str(rng.randrange(10**75, 10**76)) for _ in range(2)]
        return {"mid": mid, "cond": cond, "oids": oids, "tokens": tokens,
                "event": event, "name": "Will %s happen?" % cond[:12]}

    @staticmethod
    def legs(m, graded=None):
        for i, side in ((0, "yes"), (1, "no")):
            ext = f"{m['cond']}_{side}"
            yield (m["oids"][i], m["mid"], ext) if graded is None else (
                m["oids"][i], m["mid"], ext, graded)


# ------------------------------------------------------------------ venue ----

def _level(p, rng):
    return {"price": f"{p:.3f}", "size": f"{rng.uniform(1, 50000):.2f}"}


class Venue:
    """One connection's frames: a skewed walk over its subscribed markets."""

    def __init__(self, ids, catalog, game):
        self.rng = random.Random(hash(ids[0]) if ids else 0)
        self.catalog, self.game = catalog, game
        # Production's open book is mostly quiet: its open backlog (deferred
        # ~3.3k rows/s at a 2 s side flush, 13:12Z) says ~7.5k legs tick, so an
        # open shard streams for ~6% of its assets; every game leg ticks.
        if not game:
            ids = self.rng.sample(ids, max(1, round(len(ids) * OPEN_ACTIVE)))
        self.ids = ids
        n = len(ids)
        weights = [1.0 / (i + 1) ** 1.1 for i in range(n)]
        self.rng.shuffle(weights)
        total, acc, self.cum = sum(weights), 0.0, []
        for w in weights:
            acc += w / total
            self.cum.append(acc)
        self.mid = {}

    def _pick(self):
        import bisect

        return self.ids[min(len(self.ids) - 1, bisect.bisect(self.cum, self.rng.random()))]

    def _yes_mid(self, asset):
        m = self.mid.get(asset)
        if m is None:
            m = self.mid[asset] = self.rng.uniform(0.06, 0.94)
        if self.rng.random() < (GAME_MOVE if self.game else OPEN_MOVE):
            m = min(0.97, max(0.03, m + self.rng.choice((-0.01, 0.01))))
            self.mid[asset] = m
        return m

    def _bbo(self, asset):
        m = self._yes_mid(asset)
        spread = 0.01 if self.game else self.rng.choice((0.01, 0.02, 0.04))
        return round(m - spread / 2, 3), round(m + spread / 2, 3)

    def book(self, asset, ts):
        bid, ask = self._bbo(asset)
        rng = self.rng
        return {
            "market": self.catalog.condition.get(asset, "0x0"), "asset_id": asset,
            "timestamp": ts, "hash": "%040x" % rng.getrandbits(160),
            "bids": [_level(max(0.001, bid - 0.01 * i), rng) for i in range(14, -1, -1)],
            "asks": [_level(min(0.999, ask + 0.01 * i), rng) for i in range(14, -1, -1)],
            "event_type": "book", "tick_size": "0.01", "last_trade_price": f"{bid:.3f}",
        }

    def frame(self):
        rng, ts = self.rng, str(int(time.time() * 1000))
        asset = self._pick()
        r = rng.random()
        # last_trade_price is rare: production accepted ~2 trades/s (13:12Z).
        cut = (0.50, 0.70, 0.978, 0.98) if self.game else (0.60, 0.80, 0.99, 0.995)
        if r < cut[0]:
            bid, ask = self._bbo(asset)
            other = self.catalog.partner.get(asset, asset)
            changes = []
            for a, (b, k) in ((asset, (bid, ask)), (other, (1 - ask, 1 - bid))):
                changes.append({
                    "asset_id": a, "price": f"{b:.3f}", "size": f"{rng.uniform(1, 9999):.2f}",
                    "side": rng.choice(("BUY", "SELL")), "hash": "%040x" % rng.getrandbits(160),
                    "best_bid": f"{b:.3f}", "best_ask": f"{k:.3f}",
                })
            return {"market": self.catalog.condition.get(asset, "0x0"),
                    "price_changes": changes, "timestamp": ts, "event_type": "price_change"}
        if r < cut[1]:
            bid, ask = self._bbo(asset)
            return {"event_type": "best_bid_ask", "market": self.catalog.condition.get(asset),
                    "asset_id": asset, "best_bid": f"{bid:.3f}", "best_ask": f"{ask:.3f}",
                    "spread": f"{ask - bid:.3f}", "timestamp": ts}
        if r < cut[2]:
            return self.book(asset, ts)
        if r < cut[3]:
            bid, ask = self._bbo(asset)
            return {"asset_id": asset, "event_type": "last_trade_price", "fee_rate_bps": "0",
                    "market": self.catalog.condition.get(asset), "price": f"{(bid + ask) / 2:.3f}",
                    "side": "BUY", "size": f"{rng.uniform(5, 500):.2f}", "timestamp": ts}
        return {"event_type": "tick_size_change", "asset_id": asset,
                "market": self.catalog.condition.get(asset),
                "old_tick_size": "0.01", "new_tick_size": "0.001", "timestamp": ts}


async def serve_venue(port, cert, key, game_fps, open_fps):
    import websockets
    from websockets.asyncio.server import serve

    catalog = Catalog()
    game_total = sum(len(m["tokens"]) for m in catalog.slate)
    open_total = sum(len(m["tokens"]) for m in catalog.open)
    sent = [0]

    async def handler(ws):
        sub = json.loads(await ws.recv())
        ids = sub.get("assets_ids") or []
        if not ids:
            return
        game = ids[0].startswith("1")
        venue = Venue(ids, catalog, game)
        rate = (game_fps * len(ids) / game_total) if game else (open_fps * len(ids) / open_total)
        ts = str(int(time.time() * 1000))
        await ws.send(json.dumps([venue.book(a, ts) for a in ids], separators=(",", ":")))

        async def pongs():
            async for message in ws:
                if message == "PING":
                    await ws.send("PONG")

        reader = asyncio.create_task(pongs())
        owed, last = 0.0, time.monotonic()
        try:
            while True:
                await asyncio.sleep(0.02)
                now = time.monotonic()
                owed += rate * (now - last)
                last = now
                while owed >= 1:
                    owed -= 1
                    await ws.send(json.dumps(venue.frame(), separators=(",", ":")))
                    sent[0] += 1
        except websockets.ConnectionClosed:
            pass
        finally:
            reader.cancel()

    async def report():
        while True:
            await asyncio.sleep(5)
            print(json.dumps({"venue_sent": sent[0]}), file=sys.stderr, flush=True)

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    async with serve(handler, "127.0.0.1", port, max_size=None, ssl=context):
        print("READY", flush=True)
        await report()


def make_cert(directory):
    import datetime

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder().subject_name(name).issuer_name(name)
        .public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=2))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), True)
        .sign(key, hashes.SHA256())
    )
    cert_path, key_path = os.path.join(directory, "cert.pem"), os.path.join(directory, "key.pem")
    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    with open(key_path, "wb") as f:
        f.write(key.private_bytes(serialization.Encoding.PEM,
                                  serialization.PrivateFormat.PKCS8,
                                  serialization.NoEncryption()))
    return cert_path, key_path


# ------------------------------------------------------------------ child ----

def run_child():
    """The production child entry (``run_pm_open_receiver.py``), on this venue."""
    import importlib.util
    import logging

    def load(name, *parts):
        spec = importlib.util.spec_from_file_location(name, os.path.join(BACKEND, "app", *parts))
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module

    logging.basicConfig(level=logging.WARNING, format="child %(name)s: %(message)s")
    client = load("app.services.polymarket_ws", "services", "polymarket_ws.py")
    process = load("app.services.polymarket_ws_process", "services", "polymarket_ws_process.py")
    heap = load("app.utils.heap_trim", "utils", "heap_trim.py")
    client.WS_URL = os.environ["RIG_PM_CPU_URL"]
    client._TLS_CONTEXT = ssl.create_default_context(cafile=os.environ["RIG_PM_CPU_CA"])
    return asyncio.run(process.serve_receiver(
        client.PolymarketWebSocket,
        release_free_heap=lambda: heap.release_free_heap("polymarket_open_receiver"),
    ))


# -------------------------------------------------------------------- arm ----

class Window:
    """This process's CPU, loop lag and collections over the measured window."""

    def __init__(self):
        self.gc_started = None
        self.reset()

    def reset(self):
        self.cpu0, self.wall0 = time.process_time(), time.monotonic()
        self.lags, self.pauses = [], {0: [], 1: [], 2: []}

    def on_gc(self, phase, info):
        if phase == "start":
            self.gc_started = time.perf_counter()
        elif self.gc_started is not None:
            self.pauses[info["generation"]].append(time.perf_counter() - self.gc_started)
            self.gc_started = None

    async def sample(self):
        while True:
            before = time.monotonic()
            await asyncio.sleep(0.25)
            self.lags.append(max(0.0, time.monotonic() - before - 0.25))

    def result(self):
        wall = time.monotonic() - self.wall0
        lags = sorted(self.lags) or [0.0]
        n = len(lags)
        gcs = {}
        for gen, pauses in self.pauses.items():
            gcs[f"gen{gen}"] = {
                "n": len(pauses),
                "total_ms": round(sum(pauses) * 1000, 1),
                "max_ms": round(max(pauses, default=0.0) * 1000, 1),
            }
        return {
            "wall_s": round(wall, 2),
            "cpu_s": round(time.process_time() - self.cpu0, 3),
            "lag_p50_ms": round(lags[n // 2] * 1000, 1),
            "lag_p95_ms": round(lags[min(n - 1, int(n * 0.95))] * 1000, 1),
            "lag_max_ms": round(lags[-1] * 1000, 1),
            "gc": gcs,
        }


class Sink(list):
    def append(self, _item):
        pass

    def extend(self, _items):
        pass


class StatsLines(logging.Handler):
    """The consumer's own minute lines: counters read at each, for deltas."""

    FIELDS = ("prices", "trades", "msgs", "written", "deferred", "snapshot_quotes")

    def __init__(self):
        super().__init__(logging.INFO)
        self.marks = []

    def emit(self, record):
        import re

        text = record.getMessage()
        if text.startswith("Polymarket WS open contracts:"):
            found = dict(re.findall(r"(written|deferred|snapshot_quotes)=(\d+)", text))
            self.marks.append((time.monotonic(), "open", {k: int(v) for k, v in found.items()}))
        elif text.startswith("Polymarket WS: ") and " prices, " in text:
            m = re.match(r"Polymarket WS: (\d+) prices, (\d+) trades.* (\d+) msgs", text)
            if m:
                self.marks.append((time.monotonic(), "game", {
                    "prices": int(m[1]), "trades": int(m[2]), "msgs": int(m[3])}))

    def deltas(self):
        out = {}
        for kind in ("game", "open"):
            marks = [m for m in self.marks if m[1] == kind]
            if len(marks) >= 2:
                (t0, _, a), (t1, _, b) = marks[0], marks[-1]
                out[kind] = {k: round((b[k] - a.get(k, 0)) / (t1 - t0), 1)
                             for k in b if k in a}
        return out


def _free_port():
    probe = __import__("socket").socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return port


def serve_redis(port):
    """A Redis for the consumer's publications, in its own process (fakeredis)."""
    from fakeredis import TcpFakeServer

    server = TcpFakeServer(("127.0.0.1", port), server_type="redis")
    print("READY", flush=True)
    server.serve_forever()


def _rss_mb():
    import psutil

    return round(psutil.Process().memory_info().rss / 2**20, 1)


async def run_arm(opts):
    import tempfile
    from decimal import Decimal
    from types import SimpleNamespace

    redis_port = _free_port()
    redis_server = subprocess.Popen([sys.executable, HERE, "redis", str(redis_port)],
                                    stdout=subprocess.PIPE, text=True)
    assert redis_server.stdout.readline().strip() == "READY"
    os.environ["REDIS_URL"] = f"redis://127.0.0.1:{redis_port}/0"
    sys.path.insert(0, BACKEND)
    from _pytest.monkeypatch import MonkeyPatch
    from sqlalchemy.dialects.postgresql.asyncpg import dialect as asyncpg_dialect
    from sqlalchemy.orm import Session as SyncSession
    from sqlalchemy.sql.dml import Update

    from app.services import polymarket_ws as client_mod
    from app.services import polymarket_ws_process as process_mod
    from app.tasks import live_blend_refresh as blend
    from app.tasks import polymarket_open_contracts as admission
    from app.tasks import polymarket_token_topup as topup
    from app.tasks import polymarket_ws as task
    from app.tasks import ws_admission
    from tests._pm_slate_link_read_10663 import answer_slate_link_read
    from tests._pm_slate_market_read_10663 import answer_slate_market_read
    from tests.test_ws_consumer_session_lifetime_2471 import _install, _Rig
    from tests.test_ws_flush_retry_q491 import _Result

    class Result(_Result):
        """The few result accessors the consumer's other statements read."""

        def scalar_one(self):
            return self._rows[0][0]

        scalar = scalar_one_or_none = scalar_one

        def one_or_none(self):
            return self._rows[0] if self._rows else None

        first = one_or_none

        def mappings(self):
            return self

        def scalars(self):
            return Result([row[0] for row in self._rows])

    catalog = Catalog()
    market_of = {oid: m["mid"] for m in catalog.slate + catalog.open for oid in m["oids"]}
    stored: dict[int, float] = {}
    open_markets_sql = str(admission.open_contract_markets_stmt())
    open_outcomes_sql = str(admission.open_contract_outcomes_stmt())
    slate_outcomes_sql = (
        "SELECT futures_outcomes.id, futures_outcomes.market_id, futures_outcomes.external_id"
    )

    def rows_for(stmt):
        sql, c = str(stmt), catalog
        if sql == open_markets_sql:
            c.by_mid = {m["mid"]: m for m in c.open}
            return [(m["mid"], m["tokens"], None, None, None, m["name"], m["cond"])
                    for m in c.open]
        if sql == open_outcomes_sql:
            ids = stmt.compile().params["market_ids"]
            return [leg for mid in sorted(ids) if (m := c.by_mid.get(mid))
                    for leg in c.legs(m, graded=False)]
        if "linked_event_id" in sql:
            return answer_slate_link_read(stmt, [
                (*leg, m["cond"], m["event"]) for m in c.slate for leg in c.legs(m)])
        if "futures_markets.market_metadata" in sql:
            return answer_slate_market_read(stmt, [
                (m["mid"], m["cond"], {"clob_token_ids": m["tokens"]}, "in_progress")
                for m in c.slate
            ])
        if sql.startswith(slate_outcomes_sql):
            return [leg for m in c.slate for leg in c.legs(m)]
        return []

    # What an engine pays per statement before the driver: cache key, then a
    # compile on a miss, then the bound parameters.
    dialect, compiled_cache = asyncpg_dialect(), {}

    def compile_like_engine(stmt, params):
        try:
            key = stmt._generate_cache_key()
            if key is None:
                compiled = stmt.compile(dialect=dialect)
                compiled.construct_params(params)
                return
            compiled = compiled_cache.get(key.key)
            if compiled is None:
                compiled = compiled_cache[key.key] = stmt.compile(dialect=dialect)
            compiled.construct_params(params, extracted_parameters=key[1])
        except Exception:
            return

    def chunk_rows(stmt, params):
        # The values the statement carries (its memoized cache key's binds),
        # never a second compile: that would be the rig's cost, not the app's.
        key = stmt._generate_cache_key()
        bound = {b.key: b.value for b in key.bindparams} if key is not None else {}
        bound.update(params or {})
        ids, prices = bound.get("chunk_ids"), bound.get("chunk_prices")
        if ids is None or prices is None:
            return None
        force = bound.get("chunk_force") or [False] * len(ids)
        now = time.time()
        from datetime import datetime, timezone

        stamp = datetime.fromtimestamp(now, timezone.utc)
        rows = []
        for ord_, (oid, price, forced) in enumerate(zip(ids, prices, force), 1):
            price = float(price)
            if oid not in market_of:
                continue
            moved = stored.get(oid) != round(price, 6)
            if not (moved or forced):
                continue
            stored[oid] = round(price, 6)
            rows.append(SimpleNamespace(
                ord=ord_, id=oid, market_id=market_of[oid], last_updated=stamp,
                quote_moved=moved, database_clock=stamp,
                current_probability=Decimal(f"{price:.6f}"), is_winner=None,
                resolution_source=None,
            ))
        return rows

    class Rig(_Rig):
        def __init__(self):
            super().__init__([])

        def get_task_session(self, **kwargs):
            original = super().get_task_session(**kwargs)

            class Context:
                async def __aenter__(self):
                    session = await original.__aenter__()

                    async def route(stmt, params=None):
                        compile_like_engine(stmt, params)
                        await asyncio.sleep(STATEMENT_RTT_S)
                        if isinstance(stmt, Update):
                            if stmt.table.name == "futures_outcomes":
                                rows = chunk_rows(stmt, params)
                                if rows is not None:
                                    return Result(rows, rowcount=len(rows))
                            return Result([], rowcount=0)
                        if getattr(stmt, "text", None) is not None:  # SET ... / text()
                            return Result([(10_000,)])
                        await asyncio.sleep(READ_DELAY_S)
                        return Result(rows_for(stmt))

                    # A real (never-connected) ORM session carries the
                    # transaction and the after-commit hooks the market-change
                    # publication rides, as an AsyncSession's would.
                    sync = SyncSession()
                    session.sync_session, session.info = sync, sync.info

                    async def commit():
                        await asyncio.sleep(STATEMENT_RTT_S)
                        if sync.get_transaction() is not None:
                            sync.commit()

                    async def rollback():
                        if sync.get_transaction() is not None:
                            sync.rollback()

                    async def routed(stmt, params=None):
                        if sync.get_transaction() is None:
                            sync.begin()
                        return await route(stmt, params)

                    session.execute = routed
                    session.commit, session.rollback = commit, rollback
                    return session

                async def __aexit__(self, *exc):
                    return await original.__aexit__(*exc)

            return Context()

    tmp = tempfile.mkdtemp(prefix="rig-pm-cpu-")
    cert, key = make_cert(tmp)
    port = _free_port()
    venue_log = open(os.path.join(tmp, "venue.log"), "w")
    server = subprocess.Popen(
        [sys.executable, HERE, "server", str(port), cert, key,
         str(opts.game_fps), str(opts.open_fps)],
        stdout=subprocess.PIPE, stderr=venue_log, text=True,
    )
    url = f"wss://localhost:{port}/ws/market"
    mp = MonkeyPatch()
    try:
        assert server.stdout.readline().strip() == "READY"
        rig = Rig()
        # The shared rig records every session it lends (for its own tests);
        # kept here, that record would be a leak the consumer does not have.
        rig.calls, rig.log, rig.writes = Sink(), Sink(), Sink()

        class Refresher(blend.LiveBlendRefresher):
            async def refresh(self, *a, **k):
                return None

            async def refresh_pending(self, **k):
                return None

        async def no_topup(*_a, **_k):
            return {}

        async def never(*_a, **_k):
            await asyncio.Event().wait()

        async def claim(debt, _sessions):
            if debt._owner_id is None:
                debt._owner_id = 1
            return True

        clients = []

        class Client(client_mod.PolymarketWebSocket):
            def __init__(self, *a, **k):
                super().__init__(*a, **k)
                clients.append(self)

        forwarded = [0]
        real_read_frame = process_mod.read_frame

        async def counted_read_frame(reader, *a, **k):
            message = await real_read_frame(reader, *a, **k)
            if isinstance(message, tuple) and message and message[0] in ("p", "t"):
                forwarded[0] += 1
            return message

        _install(mp, rig)
        mp.setattr(task.PMWithdrawalDebt, "_claim_owner", claim)
        mp.setattr(client_mod, "WS_URL", url)
        mp.setattr(client_mod, "_TLS_CONTEXT", ssl.create_default_context(cafile=cert))
        mp.setattr(client_mod, "PolymarketWebSocket", Client)
        mp.setattr(process_mod, "RECEIVER_SCRIPT", HERE)
        mp.setattr(process_mod, "read_frame", counted_read_frame)
        mp.setattr(blend, "LiveBlendRefresher", Refresher)
        mp.setattr(topup, "topup_clob_tokens", no_topup)
        mp.setattr(topup, "topup_outcome_clob_tokens", no_topup)
        mp.setattr(ws_admission, "watch_for_unadmitted_live_events", never)
        mp.setattr(task, "SUBSCRIPTION_REFRESH_SECONDS", opts.refresh)
        mp.delenv("PM_WS_PRICE_FLUSH_SECONDS", raising=False)
        mp.setenv("PM_WS_GAME_FLUSH_SECONDS", str(opts.game_flush))
        for name, value in (
            ("POLYMARKET_WS_OPEN_CONTRACT_PRICES", "1"),
            ("WS_OPEN_CONTRACT_PRICES", "1"),
            ("POLYMARKET_WS_OPEN_RECEIVER_PROCESS", "1"),
            ("RIG_PM_CPU_CHILD", "1"),
            ("RIG_PM_CPU_URL", url),
            ("RIG_PM_CPU_CA", cert),
        ):
            mp.setenv(name, value)

        lines = StatsLines()
        task.logger.addHandler(lines)
        task.logger.setLevel(logging.INFO)
        stop = asyncio.Event()
        owner = asyncio.create_task(task._run_polymarket_ws_consumer(stop=stop))
        window = Window()
        sampler = asyncio.create_task(window.sample())
        await asyncio.sleep(opts.warm)
        if owner.done():
            owner.result()
        if opts.gc == "freeze":
            gc.collect()
            gc.freeze()
        elif opts.gc.startswith("thresh:"):
            gc.set_threshold(*(int(x) for x in opts.gc[7:].split(",")))
        game_msgs = lambda: sum(c.stats.get("messages", 0) for c in clients)  # noqa: E731
        g0, f0, rss0 = game_msgs(), forwarded[0], _rss_mb()
        gc.callbacks.append(window.on_gc)
        window.reset()
        if opts.tracemalloc:
            import tracemalloc

            tracemalloc.start(1)
            snap0 = tracemalloc.take_snapshot()
        profiler = cProfile.Profile() if opts.profile else None
        if profiler:
            profiler.enable()
        await asyncio.sleep(opts.seconds)
        if profiler:
            profiler.disable()
        result = window.result()
        if opts.tracemalloc:
            growth = tracemalloc.take_snapshot().compare_to(snap0, "lineno")
            result["tracemalloc_top"] = [
                {"kb": round(stat.size_diff / 1024), "n": stat.count_diff,
                 "at": [f"{f.filename.rsplit('/', 2)[-1]}:{f.lineno}" for f in stat.traceback][:6]}
                for stat in growth[:12]
            ]
            tracemalloc.stop()
        gc.callbacks.remove(window.on_gc)
        game, fwd = game_msgs() - g0, forwarded[0] - f0
        msgs = game + fwd
        result.update({
            "gc_mode": opts.gc, "gc_threshold": gc.get_threshold(),
            "game_msgs": game, "open_forwarded": fwd, "msgs": msgs,
            "msgs_per_s": round(msgs / result["wall_s"], 1),
            "cpu_frac": round(result["cpu_s"] / result["wall_s"], 3),
            "cpu_s_per_10k": round(result["cpu_s"] * 10_000 / max(1, msgs), 3),
            "rss_start_mb": rss0, "rss_end_mb": _rss_mb(),
            "frozen": gc.get_freeze_count(), "gc_count": gc.get_count(),
            "stored_writes": len(stored),
            "consumer_minute_deltas": lines.deltas(),
        })
        if profiler:
            profiler.dump_stats(opts.profile)
        stop.set()
        sampler.cancel()
        try:
            await asyncio.wait_for(owner, 60)
        except Exception as exc:  # the measurement is already taken
            result["shutdown"] = repr(exc)[:200]
        return result
    finally:
        mp.undo()
        for proc in (server, redis_server):
            proc.send_signal(signal.SIGTERM)
            proc.wait(10)
        venue_log.close()


def main():
    if os.environ.get("RIG_PM_CPU_CHILD") == "1" and len(sys.argv) == 1:
        sys.exit(run_child())
    mode = sys.argv[1]
    if mode == "redis":
        serve_redis(int(sys.argv[2]))
        return
    if mode == "server":
        port, cert, key, gfps, ofps = sys.argv[2:7]
        asyncio.run(serve_venue(int(port), cert, key, float(gfps), float(ofps)))
        return
    parser = argparse.ArgumentParser()
    parser.add_argument("mode")
    parser.add_argument("seconds", type=float)
    parser.add_argument("--warm", type=float, default=30.0)
    parser.add_argument("--profile")
    parser.add_argument("--gc", default="default")
    parser.add_argument("--game-fps", type=float, default=GAME_FPS)
    parser.add_argument("--open-fps", type=float, default=OPEN_FPS)
    parser.add_argument("--game-flush", type=float, default=0.25)
    parser.add_argument("--tracemalloc", action="store_true")
    parser.add_argument("--refresh", type=float, default=3600.0,
                        help="catalog handover period (production: timer, ~5-11 min)")
    opts = parser.parse_args()
    print(json.dumps(asyncio.run(run_arm(opts))), flush=True)


if __name__ == "__main__":
    main()
