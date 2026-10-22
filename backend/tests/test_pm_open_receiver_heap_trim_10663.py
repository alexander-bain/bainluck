"""#10663 — the open-contract receiver child trims its C heap on a timer.

The two venue processes trim after each catalog refresh (#11218); the receiver
child, the only other glibc process in worker-ws, never did. These pin the
wiring: the child's timer calls the trim while frames keep flowing, the entry
point hands it ``app.utils.heap_trim`` loaded by path (not the ``app.utils``
package and its database stack), under its own arm name.
"""

import ast
import asyncio
import os
import subprocess
import sys
import textwrap

import pytest

from app.services import polymarket_ws_process as pwp

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROCESS_FILE = os.path.join(BACKEND, "app", "services", "polymarket_ws_process.py")
HEAP_TRIM_FILE = os.path.join(BACKEND, "app", "utils", "heap_trim.py")

DRIVER = textwrap.dedent(
    """
    import asyncio, importlib.util, sys, time
    T0 = time.monotonic()
    spec = importlib.util.spec_from_file_location("pwp_child", sys.argv[1])
    pwp = importlib.util.module_from_spec(spec); spec.loader.exec_module(pwp)
    pwp.STATS_SECONDS = 0.02
    pwp.HEAP_TRIM_SECONDS = float(sys.argv[2])
    N = int(sys.argv[3])
    trims = []

    class FakeClient:
        def __init__(self, **config):
            self.emitted = 0
            self.on_price = self.on_trade = None
        @property
        def stats(self):
            return {"connected": True, "emitted": self.emitted, "trims": len(trims),
                    "elapsed": time.monotonic() - T0}
        def update_asset_ids(self, ids, *, price_book_snapshots=None):
            pass
        async def run_refreshable(self, ids, *, price_book_snapshots=None):
            for seq in range(N):
                await self.on_price({"asset_id": ids[0], "seq": seq})
                self.emitted = seq + 1
                await asyncio.sleep(0.002)
            await asyncio.Event().wait()

    sys.exit(asyncio.run(pwp.serve_receiver(
        FakeClient, release_free_heap=lambda: trims.append(1),
    )))
    """
)


async def _run_child(cadence: float, n: int, settle: float):
    proxy = pwp.PolymarketOpenReceiverProcess(
        command=[sys.executable, "-c", DRIVER, PROCESS_FILE, str(cadence), str(n)],
    )
    seen = []

    async def on_price(msg):
        seen.append(msg["seq"])

    proxy.on_price, proxy.on_trade = on_price, lambda msg: None
    run = asyncio.create_task(proxy.run_refreshable(["a"]))
    try:
        for _ in range(1000):
            if proxy.stats.get("emitted") == n and len(seen) == n:
                break
            await asyncio.sleep(0.01)
        await asyncio.sleep(settle)
        return seen, dict(proxy.stats)
    finally:
        run.cancel()
        await asyncio.gather(run, return_exceptions=True)


@pytest.mark.asyncio
async def test_the_child_trims_on_its_timer_while_frames_keep_flowing():
    seen, stats = await _run_child(cadence=0.1, n=300, settle=0.5)
    assert seen == list(range(300))
    assert stats["trims"] >= 3, stats
    assert stats["trims"] <= stats["elapsed"] / 0.1 + 1, stats  # one per cadence


@pytest.mark.asyncio
async def test_the_child_does_not_trim_before_its_cadence():
    seen, stats = await _run_child(cadence=3600.0, n=50, settle=0.3)
    assert seen == list(range(50))
    assert stats["trims"] == 0, stats


def test_the_entry_point_passes_heap_trim_loaded_by_path_under_its_own_arm():
    """``main()`` hands ``serve_receiver`` a trim that reaches
    ``app.utils.heap_trim.release_free_heap("polymarket_open_receiver")``, and
    loading it imports neither the ``app.utils`` package nor the database."""
    probe = textwrap.dedent(
        """
        import runpy, sys
        entry = runpy.run_path("run_pm_open_receiver.py", run_name="probe")
        captured = []

        class StubAsyncio:
            @staticmethod
            def run(coro):
                captured.append(coro.cr_frame.f_locals["release_free_heap"])
                coro.close()
                return 0

        entry["main"].__globals__["asyncio"] = StubAsyncio
        assert entry["main"]() == 0
        heavy = [m for m in ("app.utils", "app.services", "sqlalchemy")
                 if m in sys.modules]
        arms = []
        sys.modules["app.utils.heap_trim"].release_free_heap = arms.append
        (trim,) = captured
        trim()
        print(heavy, arms)
        """
    )
    out = subprocess.run(
        [sys.executable, "-c", probe], cwd=BACKEND, capture_output=True, text=True,
        timeout=60,
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "[] ['polymarket_open_receiver']"


def test_heap_trim_stays_loadable_by_path_in_the_child():
    """The child execs ``heap_trim.py`` by path: stdlib imports only."""
    tree = ast.parse(open(HEAP_TRIM_FILE).read())
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.add((node.module or "").split(".")[0])
    assert modules <= {"ctypes", "logging", "os", "time", "typing"}, modules
