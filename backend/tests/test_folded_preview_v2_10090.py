"""Split-origin DNPL keeps both pending readings, independent fences and leases."""
from copy import deepcopy
from dataclasses import replace
import asyncio
import json

import pytest

from app.utils.blend_preview import PreviewRegistry
from app.utils.folded_blend_preview_v2 import FoldedPreviewSession
from app.utils.hero_probability import resolve_hero
from app.utils.proven_duplicates import FoldedBlendView
from tests.test_folded_blend_preview_10090 import rig


def setup():
    event, _, _, base, pm, _, now = rig()
    base.sources['kalshi'] = {'value': .5, 'updated_at': now.isoformat()}
    base.owners['kalshi'] = 3
    [kalshi] = PreviewRegistry(epoch=900, clock=lambda: 100.).propose(
        3, 'kalshi', value=.7, event=event, row_sources={'kalshi': base.sources['kalshi']},
        row_rev=7, observed_basis={'201': now.timestamp()}, stamped_at=now)
    for frame in (kalshi, pm):
        frame['preview'].update(pending_entries_version=2, pending_entries_authority='event-ledger-v1')
    pm['preview']['epoch'] = 12
    pm['preview']['seq'] = 80
    session = FoldedPreviewSession(1, [1, 2, 3], session='test-session')
    return session, base, kalshi, pm, event


def send(session, base, frame=None, now=100., floors=None, **kw):
    return session.update(base, floors=floors or {}, now=now, frame=frame, **kw)


def auth(frame):
    return frame['preview']['origin_authority']


def revoke(frame, seq=None):
    meta = frame['preview']
    seq = seq or meta['seq'] + 1
    return {'event_id': frame['event_id'], 'p': None, 'status': 'live', 'provisional': True,
            'preview': {'kind': 'revoke', 'epoch': meta['epoch'], 'seq': seq, 'through_seq': seq - 1}}


@pytest.mark.parametrize('order', [('kalshi', 'pm'), ('pm', 'kalshi')])
def test_independent_epochs_compose_both_sources_and_full_committed_bag(order):
    session, base, kalshi, pm, event = setup()
    frames = {'kalshi': kalshi, 'pm': pm}
    first = send(session, base, frames[order[0]])
    final = send(session, base, frames[order[1]], now=100.1)
    entries = {**kalshi['preview']['pending_entries'], **pm['preview']['pending_entries']}
    expected = resolve_hero(FoldedBlendView(event, {**base.sources, **entries}))
    assert final['p'] == expected.home_probability
    assert final['p_away'] is None and final['sport'] == 'soccer_epl'
    assert final['display_observed_at'] == base.sources['betting']['updated_at']
    assert final['preview']['base_fold_revision'] == {'1': 11, '2': 22, '3': 7}
    assert auth(final)['3']['epoch'] == 900 and auth(final)['2']['epoch'] == 12
    assert final['preview']['fold_seq'] > first['preview']['fold_seq']
    assert final['preview']['fold_session'] == 'test-session'
    assert 'epoch' not in final['preview'] and 'seq' not in final['preview']
    assert 'rev' not in final
    assert base.sources['kalshi']['value'] == .5
    # Accepted v1 continues to refuse split-origin ledger authority.
    assert base.project(pm, members=[1, 2, 3], floors={}) is None


def test_old_a_cannot_replace_a2_when_b_advances_and_duplicate_cannot_renew():
    session, base, kalshi, pm, _ = setup()
    send(session, base, kalshi)
    a2 = deepcopy(kalshi)
    a2['preview']['seq'] += 1
    a2['preview']['pending']['kalshi'] = .9
    a2['preview']['pending_entries']['kalshi'].update(value=.9, observed_value=.9)
    a2['source_value'] = .9
    send(session, base, a2, now=100.1)
    assert send(session, base, kalshi, now=100.2) is None
    both = send(session, base, pm, now=100.3)
    assert session.origins['3'].entries['kalshi']['value'] == .9
    deadline = session.origins['3'].deadline
    assert send(session, base, a2, now=101.) is None
    assert session.origins['3'].deadline == deadline
    assert auth(both)['3']['seq'] == a2['preview']['seq']


@pytest.mark.parametrize('lifecycle', ['revoke', 'expiry', 'commit'])
def test_removing_a_recomposes_b_and_a_same_tuple_never_returns(lifecycle):
    session, base, kalshi, pm, event = setup()
    kalshi['preview']['ttl_ms'] = 200
    send(session, base, kalshi)
    send(session, base, pm, now=100.01)
    if lifecycle == 'revoke':
        result = send(session, base, revoke(kalshi), now=100.1)
        expected_state = 'revoked'
    elif lifecycle == 'expiry':
        result = send(session, base, now=100.201)
        expected_state = 'expired'
    else:
        cold = send(session, base, now=100.1, floors={'3': 8})
        assert cold['preview']['kind'] == 'revoke'
        assert auth(cold)['2']['state'] == 'pending'
        base = replace(base, revision={**base.revision, '3': 8},
                       sources={**base.sources, **kalshi['preview']['pending_entries']})
        result = send(session, base, now=100.2, floors={'3': 8})
        expected_state = 'committed'
    assert result['preview']['kind'] == 'blend'
    assert auth(result)['3']['state'] == expected_state
    assert auth(result)['2']['state'] == 'pending'
    expected = resolve_hero(FoldedBlendView(event, {**base.sources, **pm['preview']['pending_entries']}))
    assert result['p'] == expected.home_probability
    assert send(session, base, kalshi, now=100.3) is None
    assert session.origins['3'].state == expected_state


def test_earliest_expiry_does_not_renew_when_other_origin_updates():
    session, base, kalshi, pm, _ = setup()
    kalshi['preview']['ttl_ms'] = 500
    send(session, base, kalshi)
    send(session, base, pm, now=100.1)
    pm['preview']['seq'] += 1
    last = send(session, base, pm, now=100.4)
    assert 98 <= last['preview']['ttl_ms'] <= 100
    assert session.wait_seconds(100.4, 1.) == pytest.approx(.1)
    expired = send(session, base, now=100.501)
    assert auth(expired)['3']['state'] == 'expired'
    assert expired['preview']['kind'] == 'blend'


@pytest.mark.parametrize('cause', ['cache', 'reset'])
def test_cache_loss_and_recovery_keep_fences_and_need_newer_tuple(cause):
    session, base, kalshi, pm, _ = setup()
    send(session, base, kalshi)
    send(session, base, pm)
    if cause == 'reset':
        session.reset()
    withdrawn = send(session, None if cause == 'cache' else base, now=100.1)
    assert withdrawn['preview']['kind'] == 'revoke'
    assert all(a['state'] == 'revoked' for a in auth(withdrawn).values())
    assert send(session, base, kalshi, now=100.2) is None
    assert send(session, base, pm, now=100.2) is None
    pm['preview']['seq'] += 1
    resumed = send(session, base, pm, now=100.3)
    assert resumed['preview']['kind'] == 'blend'
    assert auth(resumed)['3']['state'] == 'revoked'
    assert resumed['preview']['fold_session'] == withdrawn['preview']['fold_session']


@pytest.mark.parametrize('bad', ['authority', 'legacy', 'basis', 'base', 'owner', 'value', 'elapsed'])
def test_invalid_input_cannot_acquire_split_authority(bad):
    session, base, kalshi, pm, _ = setup()
    kw = {}
    if bad == 'authority': pm['preview']['pending_entries_authority'] = 'fabricated'
    elif bad == 'legacy': pm['preview']['pending_entries_version'] = 1
    elif bad == 'basis': pm['preview']['pending_entries']['polymarket']['observed_basis'] = {}
    elif bad == 'base': pm['preview']['base_rev'] = 21
    elif bad == 'owner': base.owners['polymarket'] = 3
    elif bad == 'value': pm['preview']['pending_entries']['polymarket']['value'] = .1
    else: kw['elapsed_ms'] = pm['preview']['ttl_ms']
    assert send(session, base, pm, **kw) is None
    assert session.origins == {}


@pytest.mark.parametrize('change', ['members', 'owners', 'terminal'])
def test_membership_election_or_terminal_never_revives_old_overlay(change):
    session, base, kalshi, pm, _ = setup()
    send(session, base, kalshi)
    send(session, base, pm)
    if change == 'members': base = replace(base, revision={**base.revision, '4': 1})
    elif change == 'owners': base = replace(base, owners={**base.owners, 'polymarket': 1})
    else: base = replace(base, context={**base.context, 'status': 'completed'})
    out = send(session, base, now=100.1)
    assert out['preview']['kind'] == 'revoke'
    assert all(a['state'] == 'revoked' for a in auth(out).values())
    assert len(session.origins) == 2


async def test_actual_route_v2_negotiation_both_origins_revoke_and_recovery(monkeypatch):
    from app.routes import event_stream as route
    from app.utils import live_fanout
    from tests.test_folded_event_stream_invalidation_837 import Hub, Request
    _, base, kalshi, pm, _ = setup()
    hub = Hub()
    current = [base]
    hub.folded_preview_base = lambda eid, **kw: current[0]
    hub.forget_folded_preview = lambda eid: current.__setitem__(0, None)
    blocked = asyncio.Event()
    async def recovery(*args):
        await blocked.wait()
    hub.project_recovery_quote = recovery
    monkeypatch.setattr(live_fanout, 'fanout', lambda: hub)
    monkeypatch.setattr(route, 'preview_route_events', lambda: {1})
    monkeypatch.setattr(route, 'latest_frames', lambda ids: asyncio.sleep(0, result=[]))
    monkeypatch.setattr(route, '_current_reconcile', lambda *args: asyncio.sleep(0, result={
        'event_id': 1, 'custody_id': 'state:test', 'removal_rev': base.revision}))
    request = Request()
    request.query_params = {'preview_protocol': 'folded-v2'}
    stream = route._stream(1, request, [1, 2, 3])
    def decode(chunk): return json.loads(chunk.split('data: ')[1])
    try:
        await anext(stream)
        opened = decode(await anext(stream))
        assert opened['fold_session']
        assert 'event: reconcile' in await asyncio.wait_for(anext(stream), 1)
        for frame in (kalshi, pm):
            hub.subscriptions[f'live:event:{frame["event_id"]}'].offer(json.dumps(frame))
            shown = decode(await asyncio.wait_for(anext(stream), 1))
            assert shown['preview']['fold_session'] == opened['fold_session']
        assert set(auth(shown)) == {'2', '3'}
        hub.subscriptions['live:event:3'].offer(json.dumps(revoke(kalshi)))
        shown = decode(await asyncio.wait_for(anext(stream), 1))
        assert auth(shown)['2']['state'] == 'pending'
        assert auth(shown)['3']['state'] == 'revoked'
        hub.subscriptions['live:event:2'].offer(live_fanout.Recovery(1))
        withdrawn = decode(await asyncio.wait_for(anext(stream), 1))
        assert withdrawn['preview']['kind'] == 'revoke'
        assert withdrawn['preview']['fold_session'] == opened['fold_session']
        assert 'event: resync' in await asyncio.wait_for(anext(stream), 1)
    finally:
        await stream.aclose()
    assert len(hub.released) == 3


async def test_actual_route_expiry_recomposes_sibling_while_sql_stays_blocked(monkeypatch):
    from app.routes import event_stream as route
    from app.utils import live_fanout
    from tests.test_folded_event_stream_invalidation_837 import Hub, Request
    _, base, kalshi, pm, _ = setup()
    kalshi['preview']['ttl_ms'] = 100
    hub = Hub()
    hub.folded_preview_base = lambda eid, **kw: base
    async def blocked(*args): await asyncio.Event().wait()
    hub.project_recovery_quote = blocked
    monkeypatch.setattr(live_fanout, 'fanout', lambda: hub)
    monkeypatch.setattr(route, 'preview_route_events', lambda: {1})
    monkeypatch.setattr(route, 'latest_frames', lambda ids: asyncio.sleep(0, result=[]))
    monkeypatch.setattr(route, '_current_reconcile', lambda *args: asyncio.sleep(0, result={
        'event_id': 1, 'custody_id': 'state:test', 'removal_rev': base.revision}))
    request = Request()
    request.query_params = {'preview_protocol': 'folded-v2'}
    stream = route._stream(1, request, [1, 2, 3])
    try:
        await anext(stream)
        await anext(stream)
        await asyncio.wait_for(anext(stream), 1)
        for frame in (kalshi, pm):
            hub.subscriptions[f'live:event:{frame["event_id"]}'].offer(json.dumps(frame))
            await asyncio.wait_for(anext(stream), 1)
        expired = json.loads((await asyncio.wait_for(anext(stream), .5)).split('data: ')[1])
        assert auth(expired)['3']['state'] == 'expired'
        assert auth(expired)['2']['state'] == 'pending'
        assert expired['preview']['kind'] == 'blend'
    finally:
        await stream.aclose()


# Real Redis proves these packets retain the existing event-ledger final-send
# checks. Independent sessions/generations are never synthesized by the route.
from tests.test_blend_preview_ledger_tsp1_10090 import (
    BASE10, FRESH, _blends, _ev, _propose,
    redis_kwargs as redis_kwargs, rig as ledger_rig,
)
from app.utils.folded_blend_preview import FoldedPreviewBase


@pytest.mark.parametrize('order', [('kalshi', 'polymarket'), ('polymarket', 'kalshi')])
async def test_real_redis_independent_event_ledgers_compose_and_terminal_keeps_sibling(ledger_rig, order):
    event = _ev()
    event.id = 1
    base = FoldedPreviewBase.capture(
        event, {**BASE10, 'betting': {'value': .4, 'updated_at': FRESH}, 'betting_book_count': 6},
        {'betting': 1, 'kalshi': 3, 'polymarket': 2}, {'1': 11, '2': 10, '3': 10}, 'soccer_epl')
    session = FoldedPreviewSession(1, [1, 2, 3])
    registries = {'kalshi': ledger_rig.k, 'polymarket': ledger_rig.p}
    ids = {'kalshi': 3, 'polymarket': 2}
    values = {'kalshi': .6, 'polymarket': .7}
    sent = {}
    for source in order:
        [frame] = _blends(await ledger_rig.run(registries[source], _propose(
            registries[source], source, values[source], event_id=ids[source])))
        sent[source] = frame
        displayed = send(session, base, frame)
    assert set(auth(displayed)) == {'2', '3'}
    assert auth(displayed)['2']['epoch'] != auth(displayed)['3']['epoch']
    expected = resolve_hero(FoldedBlendView(event, {
        **base.sources, **sent['kalshi']['preview']['pending_entries'],
        **sent['polymarket']['preview']['pending_entries']}))
    assert displayed['p'] == expected.home_probability
    terminal = await ledger_rig.run(ledger_rig.k, ledger_rig.k.committed(
        3, 'kalshi', seq=None, sources=BASE10, rev=11, event=_ev('completed')))
    assert terminal and terminal[-1]['preview']['kind'] == 'revoke'
    final = send(session, base, terminal[-1], now=100.1)
    assert auth(final)['3']['state'] == 'revoked'
    assert auth(final)['2']['state'] == 'pending'
    assert final['preview']['kind'] == 'blend'


def test_unrelated_origin_cannot_grow_state_or_obtain_authority():
    session, base, kalshi, pm, _ = setup()
    send(session, base, kalshi)
    send(session, base, pm)
    for number in range(4, 504):
        fake = deepcopy(kalshi)
        fake['event_id'] = number
        assert send(session, base, fake) is None
    assert set(session.origins) == {'2', '3'}


def test_new_epoch_only_retires_its_own_ordering_domain():
    session, base, kalshi, pm, _ = setup()
    send(session, base, kalshi)
    send(session, base, pm)
    kalshi['preview'].update(epoch=901, seq=1)
    send(session, base, kalshi, now=100.1)
    pm['preview']['seq'] += 1
    final = send(session, base, pm, now=100.2)
    assert auth(final)['3']['epoch'] == 901
    assert auth(final)['2']['epoch'] == 12
    assert auth(final)['2']['seq'] == 81


def test_mailbox_age_subtracted_and_last_origin_expiry_withdraws():
    session, base, kalshi, _, _ = setup()
    kalshi['preview']['ttl_ms'] = 1000
    first = send(session, base, kalshi, elapsed_ms=125.2)
    assert first['preview']['ttl_ms'] <= 874
    final = send(session, base, now=100.875)
    assert final['preview']['kind'] == 'revoke'
    assert auth(final)['3']['state'] == 'expired'
    assert final['preview']['ttl_ms'] == 0


def test_revoke_during_stale_base_wait_prevents_sibling_resurrection():
    session, base, kalshi, pm, _ = setup()
    send(session, base, kalshi)
    send(session, base, pm)
    waiting = send(session, base, floors={'3': 8}, now=100.1)
    assert auth(waiting)['2']['state'] == 'pending'
    withdrawn = send(session, base, revoke(pm), floors={'3': 8}, now=100.2)
    assert auth(withdrawn)['2']['state'] == 'revoked'
    fresh = replace(base, revision={**base.revision, '3': 8})
    assert send(session, fresh, floors={'3': 8}, now=100.3) is None
    assert all(item.state != 'pending' for item in session.origins.values())


def newer_pm(pm, value=.35):
    frame = deepcopy(pm)
    frame['preview']['seq'] += 1
    frame['preview']['pending']['polymarket'] = value
    frame['preview']['pending_entries']['polymarket'].update(value=value, observed_value=value)
    frame['source_value'] = value
    return frame


def test_argon_newer_sibling_during_commit_gap_is_retained_but_not_published():
    session, base, kalshi, pm, event = setup()
    send(session, base, kalshi)
    send(session, base, pm, now=100.01)
    waiting = send(session, base, floors={'3': 8}, now=100.1)
    assert waiting['preview']['kind'] == 'revoke'
    pm2 = newer_pm(pm)
    gap = send(session, base, pm2, floors={'3': 8}, now=100.15)
    # Admission depends on B's own valid committed base. Publication still
    # requires A's newer committed component; no incomplete blend is sent.
    assert session.origins['2'].seq == 81
    assert gap['preview']['kind'] == 'revoke' and gap['p'] is None
    assert auth(gap)['3']['state'] == 'committed'
    assert auth(gap)['2']['state'] == 'pending'
    fresh = replace(base, revision={**base.revision, '3': 8},
                    sources={**base.sources, **kalshi['preview']['pending_entries']})
    resumed = send(session, fresh, floors={'3': 8}, now=100.2)
    expected = resolve_hero(FoldedBlendView(event, {**fresh.sources, **pm2['preview']['pending_entries']}))
    assert auth(resumed)['2']['seq'] == 81
    assert resumed['p'] == expected.home_probability
    assert send(session, fresh, pm, floors={'3': 8}, now=100.3) is None


@pytest.mark.parametrize('unprojectable', ['base_rev', 'unelected', 'basis', 'authority', 'expired'])
def test_argon_newer_unprojectable_blend_retires_previous_tuple(unprojectable):
    session, base, _, pm, _ = setup()
    send(session, base, pm)
    pm2 = newer_pm(pm)
    kwargs = {}
    if unprojectable == 'base_rev':
        pm2['preview']['base_rev'] += 1
    elif unprojectable == 'unelected':
        entry = pm2['preview']['pending_entries']['polymarket']
        pm2['preview']['pending_entries']['kalshi'] = deepcopy(entry)
        pm2['preview']['pending']['kalshi'] = .35
    elif unprojectable == 'basis':
        pm2['preview']['pending_entries']['polymarket']['observed_basis'] = {}
    elif unprojectable == 'authority':
        pm2['preview']['pending_entries_authority'] = 'unknown'
    else:
        kwargs['elapsed_ms'] = pm2['preview']['ttl_ms']
    withdrawn = send(session, base, pm2, now=100.1, **kwargs)
    assert session.origins['2'].identity == (12, 81)
    assert session.origins['2'].state == 'revoked'
    assert withdrawn['preview']['kind'] == 'revoke'
    assert auth(withdrawn)['2'] == {'epoch': 12, 'seq': 81, 'state': 'revoked'}
    assert send(session, base, pm, now=100.2) is None
    # A repaired retransmission of an explicitly retired identity cannot
    # revive it; only a genuinely later tuple may be admitted.
    assert send(session, base, newer_pm(pm), now=100.3) is None


def test_argon_origin_admission_still_requires_its_own_current_floor():
    session, base, _, pm, _ = setup()
    send(session, base, pm)
    pm2 = newer_pm(pm)
    refused = send(session, base, pm2, floors={'2': 23}, now=100.1)
    assert refused['preview']['kind'] == 'revoke'
    assert auth(refused)['2'] == {'epoch': 12, 'seq': 81, 'state': 'revoked'}
    assert not session.origins['2'].entries
    fresh = replace(base, revision={**base.revision, '2': 23})
    assert send(session, fresh, pm2, floors={'2': 23}, now=100.2) is None
    pm3 = newer_pm(pm2, value=.4)
    pm3['preview']['base_rev'] = 23
    resumed = send(session, fresh, pm3, floors={'2': 23}, now=100.3)
    assert resumed['preview']['kind'] == 'blend'
    assert auth(resumed)['2']['seq'] == 82


@pytest.mark.parametrize('change', ['members', 'owners', 'terminal', 'missing'])
def test_argon_newer_admission_never_bypasses_session_or_base_eligibility(change):
    session, base, kalshi, pm, _ = setup()
    send(session, base, kalshi)
    send(session, base, pm)
    if change == 'members': base = replace(base, revision={**base.revision, '4': 1})
    elif change == 'owners': base = replace(base, owners={**base.owners, 'polymarket': 1})
    elif change == 'terminal': base = replace(base, context={**base.context, 'status': 'completed'})
    else: base = None
    withdrawn = send(session, base, newer_pm(pm), now=100.1)
    assert withdrawn['preview']['kind'] == 'revoke'
    assert all(item.state != 'pending' for item in session.origins.values())
    assert len(session.origins) == 2


async def test_argon_real_redis_newest_during_gap_and_unelected_successor(ledger_rig):
    event = _ev()
    event.id = 1
    base = FoldedPreviewBase.capture(
        event, {**BASE10, 'betting': {'value': .4, 'updated_at': FRESH}, 'betting_book_count': 6},
        {'betting': 1, 'kalshi': 3, 'polymarket': 2}, {'1': 11, '2': 10, '3': 10}, 'soccer_epl')
    session = FoldedPreviewSession(1, [1, 2, 3])
    [kalshi] = _blends(await ledger_rig.run(ledger_rig.k, _propose(
        ledger_rig.k, 'kalshi', .6, event_id=3)))
    [pm] = _blends(await ledger_rig.run(ledger_rig.p, _propose(
        ledger_rig.p, 'polymarket', .7, event_id=2)))
    send(session, base, kalshi)
    send(session, base, pm)
    send(session, base, floors={'3': 11}, now=100.1)
    [pm2] = _blends(await ledger_rig.run(ledger_rig.p, _propose(
        ledger_rig.p, 'polymarket', .35, event_id=2, basis_s=2)))
    gap = send(session, base, pm2, floors={'3': 11}, now=100.2)
    assert gap['preview']['kind'] == 'revoke'
    assert auth(gap)['2']['seq'] == pm2['preview']['seq']
    fresh = replace(base, revision={**base.revision, '3': 11},
                    sources={**base.sources, **kalshi['preview']['pending_entries']})
    resumed = send(session, fresh, floors={'3': 11}, now=100.3)
    expected = resolve_hero(FoldedBlendView(event, {**fresh.sources, **pm2['preview']['pending_entries']}))
    assert resumed['p'] == expected.home_probability
    assert auth(resumed)['2']['seq'] == pm2['preview']['seq']
    # A second source really joins B's event ledger, but the folded page
    # elects Kalshi from A. Refuse this whole packet and retire B's old tuple.
    [mixed] = _blends(await ledger_rig.run(ledger_rig.k, _propose(
        ledger_rig.k, 'kalshi', .65, event_id=2, basis_s=3)))
    assert set(mixed['preview']['pending_entries']) == {'kalshi', 'polymarket'}
    withdrawn = send(session, fresh, mixed, floors={'3': 11}, now=100.4)
    assert auth(withdrawn)['2'] == {
        'epoch': mixed['preview']['epoch'], 'seq': mixed['preview']['seq'], 'state': 'revoked'}
    assert withdrawn['preview']['kind'] == 'revoke'
    assert send(session, fresh, pm2, floors={'3': 11}, now=100.5) is None
