"""#10090 — open-contract receive/decode in a child process.

Real child processes and real pipes; only the venue socket is replaced, by a
fake client inside the child that emits as fast as the pipe lets it.
"""

import asyncio
import os
import subprocess
import sys
import textwrap

import pytest

from app.services import polymarket_ws_process as pwp

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROCESS_FILE = os.path.join(BACKEND, "app", "services", "polymarket_ws_process.py")

DRIVER = textwrap.dedent(
    """
    import asyncio, importlib.util, json, os, sys
    spec = importlib.util.spec_from_file_location("pwp_child", sys.argv[1])
    pwp = importlib.util.module_from_spec(spec); spec.loader.exec_module(pwp)
    pwp.STATS_SECONDS = 0.05
    N, LEDGER, PAD = int(sys.argv[2]), sys.argv[3], "x" * 2048

    class FakeClient:
        def __init__(self, **config):
            self.config, self.updates, self.emitted = config, [], 0
            self.on_price = self.on_trade = None
        @property
        def stats(self):
            return {"connected": True, "shards": 1, "emitted": self.emitted,
                    "config": self.config, "updates": self.updates}
        def update_asset_ids(self, ids, *, price_book_snapshots=None):
            self.updates.append((ids, price_book_snapshots))
        async def run_refreshable(self, ids, *, price_book_snapshots=None):
            for seq in range(N):
                handler = self.on_trade if seq % 5 == 4 else self.on_price
                await handler({"asset_id": ids[seq % len(ids)], "seq": seq, "pad": PAD})
                self.emitted = seq + 1
                with open(LEDGER, "w") as f:
                    f.write(str(self.emitted))
            await asyncio.Event().wait()

    sys.exit(asyncio.run(pwp.serve_receiver(FakeClient)))
    """
)


def _proxy(tmp_path, n):
    ledger = tmp_path / "emitted"
    ledger.write_text("0")
    proxy = pwp.PolymarketOpenReceiverProcess(
        max_concurrent_handshakes=3, max_queue=4, price_book_snapshots=True,
        command=[sys.executable, "-c", DRIVER, PROCESS_FILE, str(n), str(ledger)],
    )
    return proxy, ledger


@pytest.mark.asyncio
async def test_order_backpressure_and_shutdown_through_a_real_child(tmp_path, monkeypatch):
    """Every frame arrives once, in emit order, on the right handler; a stalled
    parent stalls the child within the pipe bound; cancel reaps the child."""
    n = 2000
    proxy, ledger = _proxy(tmp_path, n)
    seen, stall = [], asyncio.Event()

    async def on_price(msg):
        seen.append(("p", msg["seq"]))
        if msg["seq"] == 0:
            await stall.wait()

    async def on_trade(msg):
        seen.append(("t", msg["seq"]))

    proxy.on_price, proxy.on_trade = on_price, on_trade
    spawned = []
    real_exec = asyncio.create_subprocess_exec

    async def recording_exec(*args, **kwargs):
        spawned.append(await real_exec(*args, **kwargs))
        return spawned[-1]

    monkeypatch.setattr(pwp.asyncio, "create_subprocess_exec", recording_exec)
    run = asyncio.create_task(proxy.run_refreshable(["a", "b", "c"]))
    for _ in range(200):
        if seen:
            break
        await asyncio.sleep(0.01)
    assert seen == [("p", 0)]

    # Parent stalled on frame 0: the child may only fill the bounded pipe.
    await asyncio.sleep(0.5)
    stalled_at = int(ledger.read_text())
    assert 0 < stalled_at < 200, stalled_at

    stall.set()
    for _ in range(500):
        if len(seen) == n:
            break
        await asyncio.sleep(0.01)
    assert [seq for _, seq in seen] == list(range(n))
    assert all((kind == "t") == (seq % 5 == 4) for kind, seq in seen)

    for _ in range(100):
        if proxy.stats.get("emitted") == n:
            break
        await asyncio.sleep(0.02)
    assert proxy.is_connected
    assert proxy.stats["config"] == {
        "max_concurrent_handshakes": 3, "max_queue": 4, "price_book_snapshots": True,
    }

    run.cancel()
    with pytest.raises(asyncio.CancelledError):
        await run
    (child,) = spawned
    assert child.returncode == 0  # left on stdin EOF, not killed
    assert not proxy.is_connected
    with pytest.raises(RuntimeError, match="not running"):
        proxy.update_asset_ids(["a"])


@pytest.mark.asyncio
async def test_catalog_updates_reach_the_child_latest_last(tmp_path):
    proxy, _ = _proxy(tmp_path, 1)
    proxy.on_price = proxy.on_trade = lambda msg: None
    run = asyncio.create_task(proxy.run_refreshable(["a"]))
    for _ in range(200):
        if proxy.stats.get("emitted") == 1:
            break
        await asyncio.sleep(0.01)
    proxy.update_asset_ids(["a", "b"])
    proxy.update_asset_ids(["b", "c", "b"], price_book_snapshots=False)
    for _ in range(200):
        updates = proxy.stats.get("updates") or []
        if updates and updates[-1][0] == ["b", "c"]:
            break
        await asyncio.sleep(0.01)
    assert updates[-1] == (["b", "c"], False)
    run.cancel()
    await asyncio.gather(run, return_exceptions=True)


@pytest.mark.asyncio
async def test_a_child_that_exits_fails_the_run():
    proxy = pwp.PolymarketOpenReceiverProcess(command=[sys.executable, "-c", "pass"])
    with pytest.raises(RuntimeError, match="receiver exited"):
        await proxy.run_refreshable(["a"])
    assert not proxy.is_connected


def test_the_child_entry_point_never_imports_the_app_services_package():
    """The child stays small: no database/LLM stack behind `app.services`."""
    probe = textwrap.dedent(
        """
        import runpy, sys
        entry = runpy.run_path("run_pm_open_receiver.py", run_name="probe")
        entry["_load"]("app.services.polymarket_ws", "polymarket_ws.py")
        entry["_load"]("app.services.polymarket_ws_process", "polymarket_ws_process.py")
        heavy = [m for m in ("app.services", "sqlalchemy", "app.services.database")
                 if m in sys.modules]
        print(heavy)
        """
    )
    out = subprocess.run(
        [sys.executable, "-c", probe], cwd=BACKEND, capture_output=True, text=True,
        timeout=60,
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "[]"
    # And the real entry point exits cleanly when its parent closes the pipe.
    done = subprocess.run(
        [sys.executable, "run_pm_open_receiver.py"], cwd=BACKEND,
        input=b"", capture_output=True, timeout=60,
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout == b""
