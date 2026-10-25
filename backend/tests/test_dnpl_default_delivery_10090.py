"""TRUTH: eligible probabilities reach held pages before persistence by default."""
from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy.sql.dml import Update

from app.tasks.live_blend_refresh import LiveBlendRefresher
from app.utils import blend_preview
from tests.test_blend_preview_ledger_tsp1_10090 import redis_kwargs  # noqa: F401
from tests.test_blend_preview_display_before_persist_195 import _PreviewSession, _event, STORED
from tests.test_live_blend_refresh import _one_event_refresher
from tests.test_dnpl_redis_authority_10090 import rig, initial  # noqa: F401


@pytest.fixture(autouse=True)
def clean_registry():
    blend_preview.reset_registry_for_tests()
    yield
    blend_preview.reset_registry_for_tests()


@pytest.mark.parametrize("old_setting", [None, "", "7", "malformed", "kalshi"])
def test_old_settings_cannot_exclude_new_events(monkeypatch, old_setting):
    for key in (blend_preview.SOURCE_ENV, blend_preview.EVENT_IDS_ENV, blend_preview.LEDGER_SOURCES_ENV):
        if old_setting is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, old_setting)
    workers = [LiveBlendRefresher(source) for source in ("kalshi", "polymarket")]
    assert isinstance(blend_preview.registry(), blend_preview.LedgerRegistry)
    assert blend_preview.registry().ledger_sources == {"kalshi", "polymarket"}
    for eid in (7, 15333395, 15333999):
        assert eid in blend_preview.preview_route_events()
        for worker in workers:
            assert worker.preview and eid in worker.preview_events


@pytest.mark.parametrize("eid", [None, True, False, 0, -1, "7", 7.0, 9007199254740992])
def test_invalid_event_identity_is_excluded(eid):
    assert eid not in blend_preview.preview_route_events()
    assert eid not in blend_preview.preview_events_for("kalshi")


@pytest.mark.parametrize("source", ["espn", "betting", "", "Kalshi"])
def test_unsupported_producers_keep_committed_delivery(source):
    assert not blend_preview.preview_events_for(source)


def test_scope_selects_finite_arriving_batches():
    scope = blend_preview.preview_route_events()
    with pytest.raises(TypeError):
        iter(scope)
    assert scope.isdisjoint([])
    assert not scope.isdisjoint([1, 2])
    assert scope.isdisjoint([0, None])
    assert [eid for eid in (0, 7, 15333999) if eid in scope] == [7, 15333999]


@pytest.mark.parametrize("source", ["kalshi", "polymarket"])
async def test_new_events_publish_before_locked_persistence_without_enrollment(
    monkeypatch, redis_kwargs, source, rig,  # noqa: F811
):
    from redis.asyncio import Redis
    from app.services.dnpl_authority import AuthorityStore
    from app.utils.dnpl_authority_transport import decode_preview
    from app.utils.live_push import event_channel

    authority_client, authority = rig
    await initial(authority_client, authority)
    ready = replace(authority, state="ready")
    sampled_at = datetime.now(timezone.utc) - timedelta(seconds=2)

    async def sample(store):
        return ready, sampled_at

    monkeypatch.setattr(AuthorityStore, "read_for_producer", sample)
    for key in (blend_preview.SOURCE_ENV, blend_preview.EVENT_IDS_ENV, blend_preview.LEDGER_SOURCES_ENV):
        monkeypatch.delenv(key, raising=False)
    client = Redis(**redis_kwargs)
    listener_client = Redis(**redis_kwargs)
    listener = listener_client.pubsub()
    seen = []

    class Session(_PreviewSession):
        async def execute(self, statement, *args, **kwargs):
            if isinstance(statement, Update):
                message = await listener.get_message(ignore_subscribe_messages=True, timeout=1)
                assert message is not None, "event UPDATE began before DNPL publication"
                receipt = decode_preview(message["channel"].decode(), message["data"], 0)
                assert receipt is not None and receipt.authority == ready
                seen.append(json.loads(receipt.payload))
            return await super().execute(statement, *args, **kwargs)

    session = Session([], None, stored=STORED, rev=10)
    worker, committed = _one_event_refresher(monkeypatch, session)
    # The recovered domain requires a genuine post-binding source observation.
    # The shared helper's old reading has no contributing row or source clock.
    monkeypatch.setattr(
        "app.utils.live_blend.compute_source_home_probability",
        lambda group, home, away: SimpleNamespace(
            home_probability=.9, away_probability=None, draw_probability=None,
            eligibility=None,
            contributing_outcomes=(SimpleNamespace(
                id=1, last_updated=datetime.now(timezone.utc),
            ),),
        ),
    )
    worker.source = source
    monkeypatch.setattr(worker, "_client", lambda: client)
    try:
        # Same worker, new events after construction; no event-list mutation.
        for eid in (15333395, 15333999):
            event, market = _event(eid)
            session._market_rows = [(market, event)]
            await listener.subscribe(event_channel(eid))
            await listener.get_message(timeout=1)
            await worker._refresh_batch([eid], 0.)
            assert seen[-1]["event_id"] == eid
            assert seen[-1]["preview"]["kind"] == "blend"
            assert seen[-1]["preview"]["pending"] == {source: .9}
            assert 0 < seen[-1]["preview"]["ttl_ms"] <= 60000
        assert len(seen) == 2
        assert not committed
        assert worker._lock_retry == {15333395, 15333999}
    finally:
        for item in (listener, listener_client, client):
            await item.aclose()


def test_commit_only_events_do_not_accumulate_when_admission_is_unavailable():
    from tests.test_blend_preview_ledger_tsp1_10090 import _ev, BASE10
    reg = blend_preview.LedgerRegistry(sources=blend_preview.PREVIEW_SOURCES, max_events=2)
    event = _ev()
    event.preview_read_ticket = None
    for eid in range(1, 514):
        assert reg.propose(eid, 'kalshi', value=.7, event=event, row_sources=BASE10, row_rev=10) == []
        [op] = reg.committed(eid, 'kalshi', seq=None, sources=BASE10, rev=11, event=event)
        assert op['ledger_op'] == 'settle' and op['base_rev'] == 11
        assert json.loads(op['base'])['sources'] == BASE10
        assert len(reg._events) == 0


@pytest.mark.parametrize('kind', ['terminal', 'unobserved'])
def test_early_return_admission_stays_bounded_and_preserves_active_chain(kind):
    from tests.test_blend_preview_ledger_tsp1_10090 import _ev, _propose, BASE10
    reg = blend_preview.LedgerRegistry(sources=blend_preview.PREVIEW_SOURCES, max_events=2)
    _propose(reg, 'kalshi', .7, event_id=1)
    pending_seq = reg.pending_seq(1, 'kalshi')
    assert pending_seq is not None
    active_state = reg._events[1]
    active_entry = active_state.pending['kalshi']
    active_chain = reg._chains[(1, 'kalshi')]
    evicted = []
    for eid in range(2, 20):
        event = _ev('completed' if kind == 'terminal' else 'live')
        ops = reg.propose(eid, 'kalshi', value=.5, event=event, row_sources=BASE10,
                          row_rev=10, observation_only=(kind == 'unobserved'))
        evicted.extend(op for op in ops if op.get('reason') == 'evicted')
        assert len(reg._events) <= 2
        assert reg._events[1] is active_state
        assert active_state.pending['kalshi'] is active_entry
        assert reg.pending_seq(1, 'kalshi') == pending_seq
        assert reg._chains == {(1, 'kalshi'): active_chain}
    # Terminal/observation-only contexts carry no work or expiry proof. They
    # must make room before an active reader loses its still-valid preview.
    assert evicted == []
    assert set(reg._events) == ({1} if kind == 'terminal' else {1, 19})
