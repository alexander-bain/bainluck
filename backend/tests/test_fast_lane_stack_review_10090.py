"""Independent #10090 regressions for the frozen cc7ec67f stack review."""

import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from app.tasks import live_blend_refresh as lbr
from tests.test_stamp_tx_spans_10090 import rig


def test_large_worker_setting_clamps_at_consumer_import():
    """A parseable integer above float range must honor the documented clamp."""
    env = dict(os.environ)
    env.update(
        FRESH_STAMP_WORKERS="9" * 400,
        DATABASE_URL="postgresql+asyncpg://127.0.0.1:1/review_only",
        REDIS_URL="redis://127.0.0.1:1/0",
    )
    result = subprocess.run(
        [
            sys.executable, "-c",
            "import json; import app.tasks.live_blend_refresh as r; "
            "from app.tasks.base import _consumer_pool_size; "
            "print(json.dumps([r.FRESH_STAMP_WORKERS, _consumer_pool_size()]))",
        ],
        cwd=Path(__file__).resolve().parents[1], env=env,
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [8, 10]


@pytest.mark.asyncio
async def test_wait_across_minute_reset_reports_full_slot_with_finished_transaction(monkeypatch):
    """A 61-second slot wait must not finish with a false zero for slot_full."""
    x = rig(monkeypatch)
    # This counter is independent of preview authority; keep external Redis
    # out of a stamp-slot accounting test.
    x.r.preview = False
    x.r.preview_events = frozenset()
    slots = x.r._session_slots
    for _ in range(lbr.FRESH_STAMP_WORKERS):
        await slots.acquire()
    stamp = asyncio.create_task(x.r._refresh_batch([1], 1000.0))
    released = 0
    try:
        await asyncio.sleep(0)
        assert len(slots._waiters) == 1
        # stats_loop prints and resets while this transaction is still waiting.
        x.clock.advance(61.0)
        x.r.stamp_spans.reset()
        slots.release()
        released += 1
        await stamp
        spans = x.r.stamp_spans
        assert spans.transactions == 1
        assert spans.spent["slot"] == 61.0 + 1 / 32
        assert x.r._dispositions[1][0] == "stamped"
        assert len(x.published) == 1
        assert spans.slot_full == 1
    finally:
        if not stamp.done():
            stamp.cancel()
            await asyncio.gather(stamp, return_exceptions=True)
        for _ in range(lbr.FRESH_STAMP_WORKERS - released):
            slots.release()
