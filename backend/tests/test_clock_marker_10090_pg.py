"""#10090 amendment P2 on a real Postgres: LISTEN, request, reply, causal order.

Skipped unless ``CLOCK_MARKER_TEST_DATABASE_URL`` names a disposable LOCAL
database (no table is touched; LISTEN/NOTIFY only). The collector here runs in
the same process, so its stamps and the producer's ``lo``/``hi`` share one
``time.monotonic``: every exchange must satisfy ``S < lo <= hi < R``.

    CLOCK_MARKER_TEST_DATABASE_URL=postgresql://localhost/postgres \\
        python3 -m pytest tests/test_clock_marker_10090_pg.py -v
"""

import asyncio
import json
import os
import time

import pytest

from app.utils import clock_bridge as cb

DB_URL = os.environ.get("CLOCK_MARKER_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    not DB_URL or not any(h in DB_URL for h in ("localhost", "127.0.0.1")),
    reason="needs CLOCK_MARKER_TEST_DATABASE_URL on a local disposable Postgres",
)
CASE = "pgloop20261030"


def test_a_real_listen_answers_every_request_inside_its_send_and_receive():
    import asyncpg

    env = {"DATABASE_URL": DB_URL, "DYNO": "worker-ws.1", "CLOCK_MARKER_CASE": CASE,
           "CLOCK_MARKER_EXPIRES_AT": str(time.time() + 120)}
    lines = []
    bridge = cb.ClockBridge(env=env, period_s=0.2,
                            emit=lambda prefix, pid, text: lines.append((prefix, text)))

    async def collector():
        conn = await asyncpg.connect(DB_URL)
        inbox = asyncio.Queue()
        await conn.add_listener(f"cmr_{CASE}", lambda c, p, ch, payload: inbox.put_nowait(
            (time.monotonic(), json.loads(payload))))
        bridge.armed("kalshi", 1.5)
        _, bind = await asyncio.wait_for(inbox.get(), 3.0)
        assert bind["k"] == "bind" and bind["clock"] == "time.monotonic"
        exchanges = []
        for slot in range(12):
            body = json.dumps(dict(v=1, case=CASE, tok=bind["tok"], run=bind["run"],
                                   slot=slot, nonce=os.urandom(16).hex()))
            sent = time.monotonic()
            await conn.execute("SELECT pg_notify($1, $2)", bind["ch"], body)
            received, reply = await asyncio.wait_for(inbox.get(), 1.0)
            exchanges.append((sent, reply, received, json.loads(body)["nonce"]))
            await asyncio.sleep(0.03)
        # A spoof on the producer's channel earns nothing.
        await conn.execute("SELECT pg_notify($1, $2)", bind["ch"], json.dumps(dict(
            v=1, case=CASE, tok="0" * 16, run=bind["run"], slot=99, nonce="a" * 32)))
        _, end = await asyncio.wait_for(inbox.get(), 4.0)
        await conn.close()
        return bind, exchanges, end

    bind, exchanges, end = asyncio.run(collector())
    finish = bridge._thread
    if finish is not None:
        finish.join(5.0)
    for sent, reply, received, nonce in exchanges:
        assert reply["k"] == "m" and reply["nonce"] == nonce
        assert sent < reply["lo"] <= reply["hi"] < received
    assert [r["slot"] for _, r, _, _ in exchanges] == list(range(12))
    assert end["k"] == "end" and end["why"] == "RUN_END"
    assert end["i"] == 12 and end["f"]["foreign"] == 1
    # P's own lines only. A bare database has no ``dnpl_authority`` table, so P's
    # AUTHORITY read faults and P reconnects, exactly as it does dark.
    for prefix, text in lines:
        assert prefix in {"clock_bridge", "clock_bridge_authority", "clock_bridge_fault"}
        if prefix == "clock_bridge_fault":
            assert json.loads(text)["stage"] == "AUTHORITY"
    assert any(prefix == "clock_bridge" for prefix, _ in lines)
