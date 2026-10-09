"""#10090 — a fresh population within the stamp workers waits on no shared read.

Progress: a blocked population-wide preparation read can no longer hold two or
three ready games' stamps. Coherence: those stamps publish exactly the frames
the shared-read path publishes for the same committed rows.
"""

import asyncio

import pytest

from tests.test_single_event_commit_10090 import rig


@pytest.mark.parametrize("count", [2, 3])
async def test_fresh_population_within_workers_stamps_while_shared_read_blocks(
    monkeypatch, count,
):
    x = rig(monkeypatch, count=count)
    blocked = asyncio.Event()

    async def never_returns(event_ids):
        await blocked.wait()
        raise AssertionError("a fresh population within the workers was prepared")

    x.r._prepare_groups = never_returns
    await asyncio.wait_for(x.r.refresh(range(1, count + 1), flush_started=1000), 1)
    assert sorted(x.published) == sorted(x.committed) == list(range(1, count + 1))
    assert x.r.stats["stamped"] == count and x.r.stats["errors"] == 0
    assert not x.r.pending_event_ids()


@pytest.mark.parametrize("count", [2, 3])
async def test_own_session_reads_publish_the_shared_read_paths_frames(
    monkeypatch, count,
):
    from app.tasks import live_blend_refresh as module

    def frames_by_event(x):
        return {frame["event_id"]: frame for frame in x.frames}

    own = rig(monkeypatch, count=count)
    await own.r.refresh(range(1, count + 1), flush_started=1000)

    # One worker forces the existing shared-read path for the same rows.
    monkeypatch.setattr(module, "FRESH_STAMP_WORKERS", 1)
    shared = rig(monkeypatch, count=count)
    await shared.r.refresh(range(1, count + 1), flush_started=1000)

    assert own.commands.count("read") == count
    assert shared.commands.count("read") == 1 + count - 1
    assert frames_by_event(own) == frames_by_event(shared)
    assert len(own.frames) == count
    assert own.r._last_written_value == shared.r._last_written_value
