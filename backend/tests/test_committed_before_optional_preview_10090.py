"""Committed non-canary probabilities do not queue behind optional preview I/O."""

import asyncio
from contextlib import asynccontextmanager
import pytest
from app.utils import blend_preview
from app.utils.aggregation import stamp_source_reading
from tests.test_blend_preview_display_before_persist_195 import (
    STORED,
    _event,
    _PreviewSession,
)
from tests.test_blend_preview_195_review_guards import _reader, _agg
from tests.test_live_blend_refresh import _one_event_refresher


def rig(monkeypatch, *, revoke=False, fail_commit=False):
    blend_preview.reset_registry_for_tests()
    monkeypatch.setenv(blend_preview.SOURCE_ENV, "polymarket")
    monkeypatch.delenv("LIVE_BLEND_PREVIEW_SOURCES", raising=False)
    monkeypatch.setenv(blend_preview.EVENT_IDS_ENV, "1")
    events = [_event(1), _event(2)]
    reg = blend_preview.registry()
    reg.propose(
        1,
        "kalshi",
        value=0.3,
        event=events[0][0],
        row_sources=STORED,
        row_rev=10,
        observed_basis={"7": 100.0} if revoke else None,
    )
    returned = stamp_source_reading(dict(STORED), "polymarket", 0.9)
    if revoke:
        returned = stamp_source_reading(
            returned, "kalshi", 0.45, observed_basis={"7": 200.0}
        )
    session = _PreviewSession(
        [(m, e) for e, m in events], returned, stored=STORED, rev=10, locked=False
    )
    session.returned_rev = 11
    r, _ = _one_event_refresher(monkeypatch, session)
    committed, wire, history_started = [], [], []

    @asynccontextmanager
    async def factory():
        yield session
        if fail_commit:
            raise RuntimeError("outer commit failed")
        committed.append(True)

    r._session_factory = factory
    r._normal_retry_at = float("inf")
    monkeypatch.setattr(r, "_start_history", lambda: history_started.append(True))

    async def publish(frames):
        assert committed, "no committed frame before outer transaction succeeds"
        wire.extend(("committed", f) for f in frames)
        return r._normal_revisions(frames)

    async def previews(frames):
        wire.extend(("preview", f) for f in frames)

    r._publish, r._publish_previews = publish, previews
    return r, wire, committed, history_started, returned


@pytest.mark.parametrize("wait_at", ["prepare", "publish"])
@pytest.mark.parametrize("revoke", [False, True])
async def test_committed_noncanary_bypasses_optional_settlement_io(
    monkeypatch, wait_at, revoke
):
    r, wire, committed, history_started, returned = rig(monkeypatch, revoke=revoke)
    entered, release = asyncio.Event(), asyncio.Event()
    original_prepare, original_publish = r._prepare_ledger_previews, r._publish_previews

    async def prepare(items):
        if wait_at == "prepare":
            entered.set()
            await release.wait()
        return await original_prepare(items)

    async def preview(frames):
        if committed and wait_at == "publish":
            entered.set()
            await release.wait()
        await original_publish(frames)

    r._prepare_ledger_previews, r._publish_previews = prepare, preview
    task = asyncio.create_task(r._refresh_batch([1, 2], 0.0))
    try:
        async with asyncio.timeout(1):
            await entered.wait()
        assert [f["event_id"] for k, f in wire if k == "committed"] == [2]
        assert r._normal_acked == {2: 11}
        assert r._normal_inflight == {(1, 11)}
        assert not history_started and not task.done()
    finally:
        release.set()
        await task
    assert [f["event_id"] for k, f in wire if k == "committed"] == [2, 1]
    assert r._normal_acked == {2: 11, 1: 11} and not r._normal_inflight
    assert history_started
    canary = [(k, f) for k, f in wire if f["event_id"] == 1]
    kinds = [(k, f.get("preview", {}).get("kind")) for k, f in canary]
    if revoke:
        assert kinds == [
            ("preview", "blend"),
            ("committed", None),
            ("preview", "revoke"),
        ]
        assert (
            _reader(canary, committed_rev=10, committed_p=_agg(STORED))[1:]
            == [pytest.approx(_agg(returned))] * 2
        )
    else:
        assert kinds == [
            ("preview", "blend"),
            ("preview", "blend"),
            ("committed", None),
        ]
        assert (
            len(set(_reader(canary, committed_rev=10, committed_p=_agg(STORED)))) == 1
        )


async def test_failed_outer_commit_still_publishes_no_committed_sibling(monkeypatch):
    r, wire, _, _, _ = rig(monkeypatch, fail_commit=True)
    with pytest.raises(RuntimeError, match="outer commit failed"):
        await r._refresh_batch([1, 2], 0.0)
    assert not any(k == "committed" for k, _ in wire)
    assert not r._normal_inflight and not r._normal_acked


@pytest.mark.parametrize("cancel_at", ["independent", "ledger"])
async def test_cancellation_keeps_acknowledged_sibling_and_releases_unsent_custody(
    monkeypatch, cancel_at
):
    r, wire, _, history_started, _ = rig(monkeypatch)
    entered = asyncio.Event()
    publish = r._publish

    async def blocked_publish(frames):
        if cancel_at == "independent":
            entered.set()
            await asyncio.Event().wait()
        return await publish(frames)

    async def blocked_prepare(items):
        entered.set()
        await asyncio.Event().wait()

    r._publish, r._prepare_ledger_previews = blocked_publish, blocked_prepare
    task = asyncio.create_task(r._refresh_batch([1, 2], 0.0))
    try:
        async with asyncio.timeout(1):
            await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert not r._normal_inflight
    assert r._normal_acked == ({} if cancel_at == "independent" else {2: 11})
    assert history_started


async def test_failed_sibling_send_remains_owed_and_canary_still_finishes(monkeypatch):
    r, wire, _, history_started, _ = rig(monkeypatch)
    publish = r._publish

    async def fail_sibling(frames):
        if any(f["event_id"] == 2 for f in frames):
            raise ConnectionError("independent committed publication failed")
        return await publish(frames)

    r._publish = fail_sibling
    await r._refresh_batch([1, 2], 0.0)
    assert r._normal_has_debt and r._normal_acked == {1: 11}
    assert not r._normal_inflight and history_started
    assert [f["event_id"] for k, f in wire if k == "committed"] == [1]


async def test_split_keeps_existing_committed_sender_callback(monkeypatch):
    r, wire, _, _, _ = rig(monkeypatch)
    batches = []

    async def sender(frames):
        batches.append([f["event_id"] for f in frames])
        await r._publish_prices(frames)

    await r._refresh_batch([1, 2], 0.0, publish_committed=sender)
    assert batches == [[2], [1]]
    assert r._normal_acked == {2: 11, 1: 11}


async def test_all_canary_batch_keeps_one_committed_send_after_recomposition(
    monkeypatch,
):
    r, wire, _, _, _ = rig(monkeypatch)
    r.preview_events = frozenset({1, 2})
    batches = []

    async def sender(frames):
        batches.append([f["event_id"] for f in frames])
        assert any(
            k == "preview" and f["preview"].get("base_rev") == 11 for k, f in wire
        )
        await r._publish_prices(frames)

    await r._refresh_batch([1, 2], 0.0, publish_committed=sender)
    assert batches == [[1, 2]]


async def test_disabled_preview_preserves_original_committed_batch(monkeypatch):
    r, _, _, _, _ = rig(monkeypatch)
    r.preview_events = frozenset()
    r.preview = False
    batches = []

    async def unexpected_prepare(items):
        pytest.fail("disabled preview must not prepare a settlement")

    async def sender(frames):
        batches.append([f["event_id"] for f in frames])
        await r._publish_prices(frames)

    r._prepare_ledger_previews = unexpected_prepare
    await r._refresh_batch([1, 2], 0.0, publish_committed=sender)
    assert batches == [[1, 2]]
