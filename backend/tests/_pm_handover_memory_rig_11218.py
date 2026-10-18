"""#11218 rig: the real Polymarket consumer through catalog handovers, for RSS.

Run as a script in a fresh interpreter (``test_ws_catalog_heap_trim_11218``):

    python3 tests/_pm_handover_memory_rig_11218.py HANDOVERS

The real ``_run_polymarket_ws_consumer`` (in-process open client) reads a
catalog of fake rows in the consumer's own query shapes, with ~1-2% turnover
per handover, slowed reads, and venue sockets that stream quotes the whole
time, so the reads' working set is interleaved with live allocations the way
production's 10-60 s reads are. ``WS_HEAP_TRIM`` decides the arm. One JSON
line per handover (``rss``, the consumer's own ``released`` when it trimmed),
then one final line with what a further trim would still return.
"""

import asyncio
import gc
import json
import os
import random
import sys
import time

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)

from _pytest.monkeypatch import MonkeyPatch  # noqa: E402
import websockets  # noqa: E402
from sqlalchemy.sql.dml import Update  # noqa: E402

from app.tasks import live_blend_refresh as blend  # noqa: E402
from app.tasks import polymarket_open_contracts as admission  # noqa: E402
from app.tasks import polymarket_token_topup as topup  # noqa: E402
from app.tasks import polymarket_ws as task  # noqa: E402
from app.tasks import ws_admission  # noqa: E402
from app.utils import heap_trim  # noqa: E402
from tests.test_pm_open_cycle_lifetime_10090 import CatalogRig  # noqa: E402
from tests.test_ws_consumer_session_lifetime_2471 import _install  # noqa: E402

SLATE_MARKETS, OPEN_MARKETS, EVENTS = 3_000, 12_000, 120
READ_DELAY_S, FRAMES_PER_S = 0.05, 40
rng = random.Random(11218)


class Result:
    rowcount = 1

    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)

    def scalars(self):
        return self


class Sink(list):
    def append(self, _item):
        pass

    def extend(self, _items):
        pass


class Catalog:
    def __init__(self):
        self.next_mid, self.next_oid = 1_000_000, 50_000_000
        self.slate = [self.market(rng.randrange(EVENTS)) for _ in range(SLATE_MARKETS)]
        self.open = [self.market(None) for _ in range(OPEN_MARKETS)]
        self.by_mid = {}

    def market(self, event):
        mid, self.next_mid = self.next_mid, self.next_mid + 1
        oids, self.next_oid = (self.next_oid, self.next_oid + 1), self.next_oid + 2
        condition = "0x%064x" % rng.getrandbits(256)
        return {
            "mid": mid, "cond": condition, "oids": oids,
            "tokens": [str(rng.getrandbits(255)), str(rng.getrandbits(255))],
            "event": None if event is None else 14_000_000 + event,
            "name": "Will %s happen?" % condition[:12],
        }

    def turnover(self):
        for pool, n, linked in ((self.slate, SLATE_MARKETS // 50, True),
                                (self.open, OPEN_MARKETS // 100, False)):
            for _ in range(n):
                pool.pop(rng.randrange(len(pool)))
            pool.extend(self.market(rng.randrange(EVENTS) if linked else None)
                        for _ in range(n))

    @staticmethod
    def legs(m, graded=None):
        for i, side in ((0, "yes"), (1, "no")):
            ext = f"{m['cond']}_{side}"
            yield (m["oids"][i], m["mid"], ext) if graded is None else (
                m["oids"][i], m["mid"], ext, graded)


CATALOG = Catalog()
OPEN_MARKETS_SQL = str(admission.open_contract_markets_stmt())
OPEN_OUTCOMES_SQL = str(admission.open_contract_outcomes_stmt())
SLATE_OUTCOMES_SQL = (
    "SELECT futures_outcomes.id, futures_outcomes.market_id, futures_outcomes.external_id"
)


def rows_for(stmt):
    sql, c = str(stmt), CATALOG
    if sql == OPEN_MARKETS_SQL:
        c.by_mid = {m["mid"]: m for m in c.open}
        return [(m["mid"], m["tokens"], None, None, None, m["name"], m["cond"])
                for m in c.open]
    if sql == OPEN_OUTCOMES_SQL:
        ids = stmt.compile().params["market_ids"]
        return [leg for mid in sorted(ids) if (m := c.by_mid.get(mid))
                for leg in c.legs(m, graded=False)]
    if "linked_event_id" in sql:
        return [(*leg, m["cond"], m["event"]) for m in c.slate for leg in c.legs(m)]
    if "futures_markets.market_metadata" in sql:
        return [(m["mid"], m["cond"], {"clob_token_ids": m["tokens"]}, "scheduled")
                for m in c.slate]
    if sql.startswith(SLATE_OUTCOMES_SQL):
        return [leg for m in c.slate for leg in c.legs(m)]
    return []


class Rig(CatalogRig):
    def get_task_session(self, **kwargs):
        original = super(CatalogRig, self).get_task_session(**kwargs)

        class Context:
            async def __aenter__(self):
                session = await original.__aenter__()
                execute = session.execute

                async def route(stmt, params=None):
                    if isinstance(stmt, Update):
                        return await execute(stmt, params)
                    await asyncio.sleep(READ_DELAY_S)
                    return Result(rows_for(stmt))

                session.execute = route
                return session

            async def __aexit__(self, *exc):
                return await original.__aexit__(*exc)

        return Context()


class Socket:
    """A venue shard that streams top-of-book quotes for what it subscribed."""

    def __init__(self):
        self.queue = asyncio.Queue()
        self.feeder = None

    async def feed(self, assets):
        r = random.Random(len(assets))
        while True:
            await asyncio.sleep(1.0 / FRAMES_PER_S)
            if self.queue.qsize() < 4:
                bid = r.randrange(5, 90) / 100
                self.queue.put_nowait(json.dumps([
                    {"event_type": "best_bid_ask", "asset_id": r.choice(assets),
                     "best_bid": "%.2f" % bid, "best_ask": "%.2f" % (bid + 0.02),
                     "timestamp": str(int(time.time() * 1000))}
                    for _ in range(8)
                ]))

    async def send(self, payload):
        if payload != "PING" and self.feeder is None:
            assets = json.loads(payload)["assets_ids"]
            self.feeder = asyncio.get_running_loop().create_task(self.feed(assets))

    def __aiter__(self):
        return self

    async def __anext__(self):
        return await self.queue.get()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        if self.feeder is not None:
            self.feeder.cancel()
        return False


async def main(handovers):
    mp, rig = MonkeyPatch(), Rig()
    rig.writes = Sink()

    class Refresher(blend.LiveBlendRefresher):
        async def refresh(self, *a, **k):
            return None

        async def refresh_pending(self, **k):
            return None

    async def no_topup(*_a, **_k):
        return {}

    async def never(*_a, **_k):
        await asyncio.Event().wait()

    finished, released = [], []
    finish = task._PMCatalogHandoverTiming.finish
    real_trim = heap_trim.release_free_heap

    def on_finish(self, outcome):
        finish(self, outcome)
        finished.append(outcome)
        CATALOG.turnover()

    def counted_trim(arm):
        got = real_trim(arm)
        released.append(got)
        return got

    _install(mp, rig)
    mp.setattr(websockets, "connect", lambda *a, **k: Socket())
    mp.setattr(blend, "LiveBlendRefresher", Refresher)
    mp.setattr(topup, "topup_clob_tokens", no_topup)
    mp.setattr(topup, "topup_outcome_clob_tokens", no_topup)
    mp.setattr(ws_admission, "watch_for_unadmitted_live_events", never)
    mp.setattr(task._PMCatalogHandoverTiming, "finish", on_finish)
    mp.setattr(heap_trim, "release_free_heap", counted_trim)
    mp.setattr(task, "SUBSCRIPTION_REFRESH_SECONDS", 0.5)
    for name in ("PM_WS_PRICE_FLUSH_SECONDS", "POLYMARKET_WS_OPEN_RECEIVER_PROCESS"):
        mp.delenv(name, raising=False)
    mp.setenv("POLYMARKET_WS_OPEN_CONTRACT_PRICES", "1")
    mp.setenv("WS_OPEN_CONTRACT_PRICES", "1")

    stop = asyncio.Event()
    owner = asyncio.create_task(task._run_polymarket_ws_consumer(stop=stop))
    seen = 0
    while seen < handovers:
        await asyncio.sleep(0.02)
        if len(finished) > seen:
            seen = len(finished)
            await asyncio.sleep(0.3)  # both socket owners reconcile
            gc.collect()
            print(json.dumps({"handover": seen, "rss": heap_trim._rss_bytes(),
                              "released": released[-1] if released else None}),
                  flush=True)
    # What the allocator still holds that a trim would return, measured while
    # the consumer is still running, exactly as after the last handover.
    gc.collect()
    trim = heap_trim._malloc_trim()
    before = heap_trim._rss_bytes()
    if trim is not None:
        trim(0)
    print(json.dumps({"final": True, "rss": before,
                      "reclaimable": None if trim is None or before is None
                      else before - heap_trim._rss_bytes()}), flush=True)
    stop.set()
    await asyncio.wait_for(owner, 60)
    mp.undo()


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1])))
