"""Genuine Kalshi no-write observations may preview without durable debt."""
from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.utils import blend_preview
from tests.test_fresh_observation_preview_10090 import acknowledged_rig, preview_enabled
from tests.test_blend_preview_display_before_persist_195 import _blends


def kalshi_rig(monkeypatch):
    parts = acknowledged_rig(monkeypatch)
    r, session = parts[:2]
    r.source = 'kalshi'
    monkeypatch.setenv(blend_preview.SOURCE_ENV, 'kalshi')
    session.stored['kalshi'] = session.stored.pop('polymarket')
    session._market_rows[0][0].source = 'kalshi'
    return parts


async def test_kalshi_complete_observation_previews_without_any_write(monkeypatch):
    r, session, frames, committed, rows, _, observations, validate, now = kalshi_rig(monkeypatch)
    await r.preview_accepted_observations(observations, validate)
    assert len(_blends(frames)) == 1
    assert _blends(frames)[0]['display_observed_at'] == (now - timedelta(seconds=1)).isoformat()
    assert all(row.last_updated == now - timedelta(seconds=3) for row in rows)
    assert not session.updates and not committed and not r._lock_retry and not r._history


@pytest.mark.parametrize('case', ['stale', 'changed', 'settled', 'frozen-partner', 'missing-partner'])
async def test_kalshi_observation_requires_current_complete_basis(monkeypatch, case):
    r, session, frames, _, rows, _, observations, validate, now = kalshi_rig(monkeypatch)
    if case == 'stale':
        rows[0].last_updated = now
    elif case == 'changed':
        rows[0].current_probability = .8
    elif case == 'settled':
        rows[1].is_winner = True
    elif case == 'frozen-partner':
        value, _, mark = observations[1][rows[1].id]
        observations[1][rows[1].id] = (value, (now - timedelta(seconds=10)).timestamp(), mark)
    else:
        observations[1].pop(rows[1].id)
    await r.preview_accepted_observations(observations, validate)
    assert not _blends(frames) and not session.updates


@pytest.mark.parametrize('transition', ['same', 'same-repeat', 'changed', 'a-b-a', 'withdraw-restore',
                                      'connection', 'routing', 'settled', 'owner-same', 'owner-other',
                                      'release-same', 'release-other', 'replacement-window'])
async def test_no_write_phase_revalidates_continuity_and_event_ownership(transition):
    from tests.test_kalshi_game_isolation_10655 import rig
    r = rig(declined=1)
    for oid in (2, 3, 9):
        r.batch.pop(oid)
    prices = r.ns['prices']
    prices.committed_outcome_ids.add(1)
    refresher = r.ns['blend_refresher']
    refresher.preview_events = {100}
    refresher._admission = SimpleNamespace(released={})

    class Bounds:
        def bound_for(self, mark):
            return 1000.
        async def sample_database_clock(self, *args):
            pass
        def release(self, *args):
            pass
        def __contains__(self, oid):
            return False

    refresher.held_quotes = Bounds()
    mark = SimpleNamespace(seq=10, probability=.6)
    r.ns['input_marks'][1] = mark
    signature = [object()]
    token = (object(), r.batch[1], 'TICKER', signature[0])
    r.ns['observation_continuity'] = {1: token}
    r.ns['observation_signature'] = lambda ticker: signature[0]
    observed = []

    async def preview(observations, validate):
        assert await validate({100}) == {100}
        if transition == 'same-repeat':
            r.ns['input_marks'][1] = SimpleNamespace(seq=11, probability=.6)
        elif transition == 'changed':
            r.ns['input_marks'][1] = SimpleNamespace(seq=11, probability=.7)
        elif transition in ('a-b-a', 'withdraw-restore'):
            r.ns['observation_continuity'][1] = (object(), *token[1:])
        elif transition == 'connection':
            signature[0] = object()
        elif transition == 'routing':
            r.events[1] = 200
        elif transition == 'settled':
            prices.settled_market_ids.add(10)
        elif transition.startswith('owner-'):
            prices.stamping = SimpleNamespace(done=lambda: False)
            prices.held_events = lambda _: {100 if transition == 'owner-same' else 200}
        elif transition.startswith('release-'):
            refresher._admission.released[100 if transition == 'release-same' else 200] = 1
        elif transition == 'replacement-window':
            refresher._admission = SimpleNamespace(released={})
        try:
            observed.append((observations, await validate({100})))
        finally:
            prices.stamping = None

    refresher.preview_accepted_observations = preview
    await r.flush()
    assert len(observed) == 1
    observations, allowed = observed[0]
    assert observations == {100: {1: (.6, 1000., mark)}}
    assert allowed == ({100} if transition in ('same', 'same-repeat', 'owner-other', 'release-other') else set())
    assert not r.committed
    assert not any(kind == 'refresh' and ids for kind, ids in r.trace)


@pytest.mark.parametrize('refused_at', ['read', 'publish', 'changed-contributors'])
async def test_kalshi_optional_path_preserves_current_book_proof_without_parking(monkeypatch, refused_at):
    r, session, frames, _, rows, reading, observations, validate, _ = kalshi_rig(monkeypatch)
    market = session._market_rows[0][0]
    market.external_id = 'KXATPCHALLENGERMATCH-26OCT21PAIR-HOME'
    r.require_current_book_proof = True
    parked = []
    monkeypatch.setattr(r, '_park_book_refused', lambda *args: parked.append(args))
    calls = []

    def compute(*args, **kwargs):
        calls.append(kwargs)
        assert kwargs['require_current_book_midpoint'] is True
        assert 'current_primary_input' in kwargs
        if (refused_at == 'read' or (refused_at == 'publish' and len(calls) == 2)):
            kwargs['current_book_refused']()
            return None
        if refused_at == 'changed-contributors' and len(calls) == 2:
            return SimpleNamespace(home_probability=.9, named_home_quote=True,
                                   contributing_outcomes=[rows[0]])
        return reading

    monkeypatch.setattr('app.utils.live_blend.compute_source_home_probability', compute)
    await r.preview_accepted_observations(observations, validate)
    assert len(calls) == (1 if refused_at == 'read' else 2)
    assert not _blends(frames) and not session.updates and not parked


def test_actual_handler_continuity_retains_repeats_but_fences_changes_and_withdrawals():
    import ast
    from pathlib import Path
    import app.tasks.kalshi_ws as consumer
    tree = ast.parse(Path(consumer.__file__).read_text())
    [node] = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
              and n.name == 'note_observation_continuity']
    signature = [object()]
    ns = dict(observation_signature=lambda ticker: signature[0], event_id_by_outcome={1: 100},
              blend_refresher=SimpleNamespace(preview_events={100}), non_blend_outcome_ids=set(),
              observation_continuity={})
    exec(compile(ast.Module(body=[node], type_ignores=[]), consumer.__file__, 'exec'), ns)
    note = ns['note_observation_continuity']
    note(1, 'TICKER', (.6, .59, .61))
    first = ns['observation_continuity'][1]
    note(1, 'TICKER', (.6, .59, .61))
    assert ns['observation_continuity'][1] == first
    note(1, 'TICKER', (.7, .69, .71))
    note(1, 'TICKER', (.6, .59, .61))
    second = ns['observation_continuity'][1]
    assert second != first
    note(1, 'TICKER', None)
    assert not ns['observation_continuity']
    note(1, 'TICKER', (.6, .59, .61))
    assert ns['observation_continuity'][1] != second
    signature[0] = None
    note(1, 'TICKER', (.6, .59, .61))
    assert not ns['observation_continuity']
