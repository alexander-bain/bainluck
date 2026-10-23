"""Warm preview authority is scoped to the requesting stream's fold membership."""

import asyncio
from dataclasses import replace

import pytest

from app.utils import folded_live_quote as module
from app.utils.folded_blend_preview import QuoteWithPreviewBase
from tests.test_folded_blend_preview_10090 import rig


def trigger(label):
    return {"event_id": 2, "rev": {"2": 22}, "updated_at": label}


@pytest.mark.parametrize("new_revision", [
    {"1": 11, "2": 22},
    {"1": 11, "2": 22, "3": 7, "4": 0},
])
async def test_changed_membership_warms_and_late_old_read_cannot_replace_it(monkeypatch, new_revision):
    _, _, _, old_base, frame, _, _ = rig()
    new_base = replace(old_base, revision=new_revision)
    entered, release = asyncio.Event(), asyncio.Event()
    calls = 0

    async def load(*args):
        nonlocal calls
        calls += 1
        call = calls
        if call == 2:
            entered.set()
            await release.wait()
        return QuoteWithPreviewBase({"event_id": 1}, new_base if call == 3 else old_base)

    monkeypatch.setattr(module, "load_folded_quote", load)
    projector = module.FoldedQuoteProjector()
    await projector.project(1, trigger("initial"))
    late = asyncio.create_task(projector.project(1, trigger("old-read")))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        await projector.project(1, trigger("new-stream"), fresh=True)
        members = [int(key) for key in new_revision]
        projected = projector.project_preview(1, frame, members=members, floors=new_revision)
        assert projected is not None
        assert projected["preview"]["base_fold_revision"] == new_revision
        release.set()
        await late
        assert projector.project_preview(1, frame, members=members, floors=new_revision) == projected
        # The old stream has its own exact membership; it cannot borrow the new one.
        old_projected = projector.project_preview(1, frame, members=[1, 2, 3], floors=old_base.revision)
        assert old_projected["preview"]["base_fold_revision"] == old_base.revision
        projector.forget_preview_base(1)
        assert projector.project_preview(1, frame, members=members, floors=new_revision) is None
        assert projector.project_preview(1, frame, members=[1, 2, 3], floors={}) is None
    finally:
        release.set()
        await asyncio.gather(late, return_exceptions=True)


async def test_same_membership_late_lower_revision_does_not_regress_base(monkeypatch):
    _, _, _, old_base, frame, _, _ = rig()
    newer = replace(old_base, revision={**old_base.revision, "1": 12})
    entered, release = asyncio.Event(), asyncio.Event()
    calls = 0

    async def load(*args):
        nonlocal calls
        calls += 1
        if calls == 1:
            entered.set()
            await release.wait()
            return QuoteWithPreviewBase({"event_id": 1}, old_base)
        return QuoteWithPreviewBase({"event_id": 1}, newer)

    monkeypatch.setattr(module, "load_folded_quote", load)
    projector = module.FoldedQuoteProjector()
    late = asyncio.create_task(projector.project(1, trigger("old")))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        await projector.project(1, trigger("new"))
        release.set()
        await late
        projected = projector.project_preview(1, frame, members=[1, 2, 3], floors=newer.revision)
        assert projected is not None
        assert projected["preview"]["base_fold_revision"] == newer.revision
    finally:
        release.set()
        await asyncio.gather(late, return_exceptions=True)


async def test_membership_scoped_cache_remains_bounded(monkeypatch):
    _, _, _, base, frame, _, _ = rig()
    revision = base.revision

    async def load(*args):
        return QuoteWithPreviewBase({"event_id": 1}, replace(base, revision=revision))

    monkeypatch.setattr(module, "load_folded_quote", load)
    monkeypatch.setattr(module, "MAX_CACHED", 2)
    projector = module.FoldedQuoteProjector()
    for extra in (4, 5, 6):
        revision = {**base.revision, str(extra): 0}
        await projector.project(1, trigger(str(extra)))
    assert len(projector._preview_bases) == 2
    assert projector.project_preview(1, frame, members=[1, 2, 3, 4], floors={}) is None
    assert projector.project_preview(1, frame, members=[1, 2, 3, 6], floors={}) is not None


async def test_recovery_forget_fences_inflight_base_until_fresh_load(monkeypatch):
    _, _, _, base, frame, _, _ = rig()
    entered, release = asyncio.Event(), asyncio.Event()

    async def load(*args):
        entered.set()
        await release.wait()
        return QuoteWithPreviewBase({"event_id": 1}, base)

    monkeypatch.setattr(module, "load_folded_quote", load)
    projector = module.FoldedQuoteProjector()
    late = asyncio.create_task(projector.project(1, trigger("same-revision"), fresh=True))
    joined = None
    try:
        await asyncio.wait_for(entered.wait(), 1)
        projector.forget_preview_base(1)
        joined = asyncio.create_task(projector.project(1, trigger("same-revision"), fresh=True))
        await asyncio.sleep(0)
        release.set()
        assert await late is None
        assert await joined is None  # post-boundary waiter cannot mistake this for warming
        assert projector.project_preview(1, frame, members=[1, 2, 3], floors={}) is None
        await projector.project(1, trigger("after-recovery"), fresh=True)
        assert projector.project_preview(1, frame, members=[1, 2, 3], floors={}) is not None
    finally:
        release.set()
        await asyncio.gather(late, return_exceptions=True)
        if joined is not None:
            await asyncio.gather(joined, return_exceptions=True)
