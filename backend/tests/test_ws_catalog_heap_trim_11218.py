"""#11218 — worker-ws hands the catalog reads' freed memory back after each refresh.

v5785: worker-ws stepped up ~16-38 MB at each Polymarket catalog handover AND
each Kalshi scope refresh, flat between them, 811 -> 944.7 MB in 40 minutes.
A local control holds Python's live memory and pymalloc arenas flat apart from
~1 MB a handover, so what grows is freed memory the C allocator keeps.

Guards: (1) the trim itself, which never raises and has a ``WS_HEAP_TRIM=0``
undo; (2) on glibc, the allocator keeps freed heap until trimmed, and the trim
returns it (the production allocator: CI's ubuntu runner is the heroku-24
base); (3) both arms trim once after every refresh, after the read's working
set is garbage.
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
import textwrap
import warnings
from contextlib import asynccontextmanager

import pytest
import websockets

from app.utils import heap_trim

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def fresh_trim(monkeypatch):
    monkeypatch.setattr(heap_trim, "_trim_fn", None)
    monkeypatch.delenv("WS_HEAP_TRIM", raising=False)


class Trim:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def __call__(self, pad):
        self.calls.append(pad)
        if self.fail:
            raise OSError("trim broke")
        return 1


def test_trims_once_and_states_what_it_released(monkeypatch, fresh_trim, caplog):
    trim = Trim()
    monkeypatch.setattr(heap_trim, "_malloc_trim", lambda: trim)
    rss = iter([900 * 2**20, 870 * 2**20])
    monkeypatch.setattr(heap_trim, "_rss_bytes", lambda: next(rss))
    caplog.set_level(logging.INFO, logger=heap_trim.__name__)
    assert heap_trim.release_free_heap("polymarket") == 30 * 2**20
    assert trim.calls == [0]
    (line,) = [r.getMessage() for r in caplog.records]
    assert line.startswith(
        "worker-ws heap trim: arm=polymarket released=30.0MB rss=900.0->870.0MB took="
    )


def test_undo_flag_skips_the_trim(monkeypatch, fresh_trim):
    trim = Trim()
    monkeypatch.setattr(heap_trim, "_malloc_trim", lambda: trim)
    monkeypatch.setenv("WS_HEAP_TRIM", "0")
    assert heap_trim.release_free_heap("kalshi") is None
    assert trim.calls == []
    monkeypatch.setenv("WS_HEAP_TRIM", "1")
    heap_trim.release_free_heap("kalshi")
    assert trim.calls == [0]


def test_a_failed_trim_never_reaches_the_consumer(monkeypatch, fresh_trim, caplog):
    monkeypatch.setattr(heap_trim, "_malloc_trim", lambda: Trim(fail=True))
    caplog.set_level(logging.WARNING, logger=heap_trim.__name__)
    assert heap_trim.release_free_heap("kalshi") is None
    assert "worker-ws heap trim failed (arm=kalshi)" in caplog.text


def test_no_malloc_trim_in_this_c_library_is_a_quiet_no_op(monkeypatch, fresh_trim):
    class NoTrim:
        pass

    monkeypatch.setattr(heap_trim.ctypes, "CDLL", lambda _name: NoTrim())
    assert heap_trim._malloc_trim() is None
    assert heap_trim._trim_fn is False  # resolved once, not per refresh
    assert heap_trim.release_free_heap("polymarket") is None


GLIBC = sys.platform.startswith("linux") and os.confstr("CS_GNU_LIBC_VERSION") is not None


@pytest.mark.skipif(not GLIBC, reason="malloc_trim and its heap retention are glibc's")
def test_glibc_keeps_freed_heap_until_the_trim_returns_it():
    # A fresh interpreter so the heap holds nothing but this pattern: 120 MB of
    # 40 kB buffers (under glibc's 128 kB mmap threshold, so heap, not mmap)
    # with a long-lived 700 B allocation after each, the shape of a catalog
    # read interleaved with live traffic. Freeing the buffers leaves holes
    # that free() never returns; one trim does.
    script = textwrap.dedent(
        """
        import json, sys
        sys.path.insert(0, sys.argv[1])
        from app.utils.heap_trim import _rss_bytes, release_free_heap
        base = _rss_bytes()
        held, pins = [], []
        for _ in range(3000):
            held.append(bytearray(40_000))
            pins.append(bytearray(700))
        loaded = _rss_bytes()
        del held
        freed = _rss_bytes()
        released = release_free_heap("control")
        trimmed = _rss_bytes()
        print(json.dumps(dict(base=base, loaded=loaded, freed=freed,
                              trimmed=trimmed, released=released, pins=len(pins))))
        """
    )
    run = subprocess.run(
        [sys.executable, "-c", script, BACKEND],
        capture_output=True, text=True, timeout=120,
        env={**os.environ, "WS_HEAP_TRIM": "1"},
    )
    assert run.returncode == 0, run.stderr
    got = json.loads(run.stdout.strip().splitlines()[-1])
    mb = {k: v / 2**20 for k, v in got.items() if k not in ("pins",) and v is not None}
    working_set = mb["loaded"] - mb["base"]
    assert working_set > 100, mb
    # Parent behaviour: free() alone gives back almost none of it.
    assert mb["loaded"] - mb["freed"] < 0.2 * working_set, mb
    # Candidate: the trim hands most of it back, and says so.
    assert mb["freed"] - mb["trimmed"] > 0.6 * working_set, mb
    # Its own receipt matches (within a page or two of interpreter noise).
    assert abs(got["released"] - (got["freed"] - got["trimmed"])) < 2**21, got


def _rig(trim: str, handovers: int = 6) -> tuple[list[dict], dict]:
    run = subprocess.run(
        [sys.executable, os.path.join(BACKEND, "tests", "_pm_handover_memory_rig_11218.py"),
         str(handovers)],
        capture_output=True, text=True, timeout=300, cwd=BACKEND,
        env={**os.environ, "WS_HEAP_TRIM": trim},
    )
    assert run.returncode == 0, run.stderr[-3000:]
    lines = [json.loads(line) for line in run.stdout.splitlines() if line.startswith("{")]
    return [x for x in lines if "handover" in x], lines[-1]


@pytest.mark.skipif(not GLIBC, reason="malloc_trim and its heap retention are glibc's")
def test_real_handovers_leave_returnable_heap_that_the_consumer_now_returns():
    """The deciding control, on the production allocator: the real consumer,
    live traffic interleaved with slowed catalog reads, six handovers per arm.

    Parent (``WS_HEAP_TRIM=0``): after the handovers the heap holds freed
    memory that is still resident; one trim returns it. Candidate: the
    consumer's own per-refresh trims have already returned it.
    """
    parent, parent_end = _rig("0")
    candidate, candidate_end = _rig("1")
    mb = 2**20

    def col(rows, key, scale=1):
        return [None if x[key] is None else round(x[key] / scale, 1) for x in rows]

    summary = (
        f"parent rss MB={col(parent, 'rss', mb)} lag ms={col(parent, 'max_lag_ms')} "
        f"end rss={parent_end['rss'] / mb:.1f} reclaimable={parent_end['reclaimable'] / mb:.1f}MB"
        f" | candidate rss MB={col(candidate, 'rss', mb)} lag ms={col(candidate, 'max_lag_ms')}"
        f" released MB={col(candidate, 'released', mb)} trim ms={col(candidate, 'trim_ms')}"
        f" end rss={candidate_end['rss'] / mb:.1f} reclaimable="
        f"{candidate_end['reclaimable'] / mb:.1f}MB"
    )
    # Stated on a green run too (CI prints the warnings summary): the numbers
    # are the control's result, not only its failure message.
    warnings.warn(f"#11218 glibc handover control: {summary}")
    assert all(x["released"] is None for x in parent), summary
    # Every refresh after the startup install trimmed, and said what it gave back.
    assert candidate[0]["released"] is None, summary
    assert all(isinstance(x["released"], int) for x in candidate[1:]), summary
    assert parent_end["reclaimable"] > 2 * mb, summary
    assert candidate_end["reclaimable"] < 0.5 * parent_end["reclaimable"], summary
    # The benefit is resident memory, not only a smaller remainder.
    assert candidate_end["rss"] < parent_end["rss"], summary
    # The cost: the trim is synchronous work on the delivery loop. Bounded
    # loosely here; the per-refresh `took=` line is the production reading.
    assert max(x["trim_ms"] for x in candidate[1:]) < 250, summary


# ---------------------------------------------------- the two consumers ----


@pytest.mark.asyncio
async def test_polymarket_trims_after_every_installed_catalog_refresh(monkeypatch):
    from app.tasks import live_blend_refresh as blend
    from app.tasks import polymarket_ws as task
    from tests.test_pm_open_cycle_lifetime_10090 import CatalogRig
    from tests.test_ws_consumer_session_lifetime_2471 import _install

    rig, finished, trims, stop = CatalogRig(), [], [], asyncio.Event()
    finish = task._PMCatalogHandoverTiming.finish

    def on_finish(self, outcome):
        finish(self, outcome)
        finished.append(self.reason)

    def recorded_trim(arm):
        trims.append((arm, len(finished)))
        if len(trims) >= 3:
            stop.set()
        return 0

    class Socket:
        async def send(self, payload):
            return None

        def __aiter__(self):
            return self

        async def __anext__(self):
            await asyncio.Event().wait()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    class Refresher(blend.LiveBlendRefresher):
        async def refresh(self, *args, **kwargs):
            return None

        async def refresh_pending(self, **kwargs):
            return None

    _install(monkeypatch, rig)
    monkeypatch.setattr(websockets, "connect", lambda *a, **k: Socket())
    monkeypatch.setattr(blend, "LiveBlendRefresher", Refresher)
    monkeypatch.setattr(task._PMCatalogHandoverTiming, "finish", on_finish)
    monkeypatch.setattr(heap_trim, "release_free_heap", recorded_trim)
    monkeypatch.setattr(task, "SUBSCRIPTION_REFRESH_SECONDS", 0.04)
    monkeypatch.setattr(task, "PRICE_FLUSH_SECONDS", 10)
    monkeypatch.delenv("PM_WS_PRICE_FLUSH_SECONDS", raising=False)
    monkeypatch.delenv("POLYMARKET_WS_OPEN_RECEIVER_PROCESS", raising=False)
    monkeypatch.setenv("POLYMARKET_WS_OPEN_CONTRACT_PRICES", "1")
    monkeypatch.setenv("WS_OPEN_CONTRACT_PRICES", "1")

    stats = await asyncio.wait_for(task._run_polymarket_ws_consumer(stop=stop), 10)

    # The startup install is not a refresh; each refresh trims once, after its
    # own handover finished (so its read's copies were already dropped).
    assert finished[0] == "initial"
    assert trims == [("polymarket", n) for n in range(2, len(trims) + 2)]
    assert stats["catalog_refreshes"] == len(trims)


@pytest.mark.asyncio
async def test_kalshi_trims_after_every_scope_refresh_whatever_its_verdict(monkeypatch):
    import app.services.kalshi_ws as service
    import app.tasks.kalshi_ws as task
    import app.tasks.live_blend_refresh as blend
    import app.tasks.ws_admission as admission
    from tests.test_kalshi_subscription_continuity_10090 import Prices, Scope, Socket

    monkeypatch.setenv("KALSHI_API_KEY_ID", "control")
    monkeypatch.setenv("KALSHI_RSA_PRIVATE_KEY", "control")
    monkeypatch.setenv("WS_OPEN_CONTRACT_PRICES", "1")
    monkeypatch.setenv("WS_OPEN_CONTRACT_SETTLEMENT", "1")
    monkeypatch.delenv("WS_KALSHI_TRACE_TICKERS", raising=False)
    monkeypatch.setattr(task, "SUBSCRIPTION_REFRESH_SECONDS", 0.02)
    monkeypatch.setattr(task, "kalshi_flush_cadence", lambda: (1000, 2, None, 4))
    monkeypatch.setattr(admission, "ADMISSION_CHECK_SECONDS", 0.01)
    monkeypatch.setattr(admission, "ADMISSION_MIN_RECYCLE_SECONDS", 0)
    monkeypatch.setattr(service, "_load_rsa_key", object)
    monkeypatch.setattr(service, "_sign_ws_request", lambda *_: {})
    monkeypatch.setattr("app.tasks.ws_liveness.report", lambda *_a, **_k: None)

    @asynccontextmanager
    async def connect(*_args, **_kwargs):
        yield Socket()

    async def publish(_self, _session):
        return 0

    monkeypatch.setattr(websockets, "connect", connect)
    monkeypatch.setattr(blend.LiveBlendRefresher, "publish_market_changes", publish)
    scope = Scope()
    trims = []

    def recorded_trim(arm):
        # Recorded with the reads it follows: a trim before its read would
        # find nothing of that read's to give back.
        trims.append((arm, scope.linked_reads))
        return 0

    monkeypatch.setattr(task, "release_free_heap", recorded_trim)
    running = asyncio.create_task(task._run_kalshi_ws_consumer.__wrapped__.__wrapped__(
        sessions=scope, prices=Prices(scope),
    ))
    try:
        for _ in range(1000):
            if len(trims) >= 2:
                break
            await asyncio.sleep(0.01)
        reads_before_failure = scope.linked_reads
        scope.fail_next = True  # a failed reread still read, and still trims
        await asyncio.wait_for(scope.failed.wait(), 10)
        for _ in range(1000):
            if any(reads > reads_before_failure for _arm, reads in trims):
                break
            await asyncio.sleep(0.01)
    finally:
        running.cancel()
        await asyncio.gather(running, return_exceptions=True)
    assert len(trims) >= 3, trims
    assert {arm for arm, _ in trims} == {"kalshi"}
    # One trim per refresh, each after that refresh's slate read.
    reads = [n for _arm, n in trims]
    assert reads == sorted(set(reads)) and reads[0] >= 2, trims
    assert any(n > reads_before_failure for n in reads), trims
