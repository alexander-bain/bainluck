"""Isolated real-producer driver. No production clients, writes, or source edits.

Source logic: LiveBlendRefresher.refresh/refresh_pending/_preview_before_stamp,
real source estimator, PreviewRegistry, and _publish_previews serialization.
Injected boundaries: in-memory SQL row/55P03 outcome, clock, Redis fence script
semantics, cached no-inversion verdict, and post-commit publication callback.
Scheduled step times are fixture inputs, NOT a measured production cadence.
"""
from __future__ import annotations
import asyncio
import copy
import inspect
import json
import os
from pathlib import Path
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

sys.dont_write_bytecode = True
SOURCE = Path(os.environ.get('PRODUCER_DEPENDENCY_SOURCE', str(Path(__file__).resolve().parent.parent / 'source')))
sys.path.insert(0, str(SOURCE / 'backend'))
# These are fixture destinations, never production connections. The session and
# Redis objects below are always explicitly injected; no connection is opened.
os.environ.setdefault('DATABASE_URL', 'postgresql+asyncpg://fixture:fixture@127.0.0.1:1/fixture')
import pytest
from sqlalchemy.sql.dml import Insert, Update
from current_source import load
# Bind the selected candidate before fixture imports. Direct use must not rely
# on a test module having already replaced app.utils.blend_preview.
blend_preview, lbr = load(candidate=True)
from app.utils.aggregation import observation_basis, stamp_source_reading
from app.utils.live_push import build_frame, build_source_snapshot
from tests.test_live_blend_refresh import _LockedRowSession, _Result

PINNED_SHA = 'b2b92fe86467d0accdb02f7b765ada020b594aec'  # two saved producer modules; fixture dependencies stay pinned
DEFAULT_FIXTURE_PERIOD_S = 2.0
DEFAULT_WALL = datetime(2026, 10, 21, 0, 0, tzinfo=timezone.utc)


class FixtureClock:
    def __init__(self, wall=DEFAULT_WALL):
        self.seconds = 0.0
        self.wall = wall
    def mono(self):
        return 1000.0 + self.seconds
    def now(self):
        return self.wall + timedelta(seconds=self.seconds)


class PreviewSession(_LockedRowSession):
    def __init__(self, driver):
        self.driver = driver
        super().__init__([(driver.market, driver.event)], driver.outcomes, None, locked=True)
        self.preview_reads = 0
        self.successful_updates = 0
        self.commits = 0
    async def execute(self, statement, *args, **kwargs):
        if isinstance(statement, Insert):
            # Durable publication intent is recorded in production. This rig
            # exercises quote/retry behavior, not durable intent recovery.
            return _Result()
        if isinstance(statement, Update) and not self.locked:
            d = self.driver
            self._returned = stamp_source_reading(
                copy.deepcopy(d.stored), d.source, d.value,
                now=d.clock.now(), observed_basis=observation_basis(d.outcomes[:1]),
            )
            self.returned_rev = d.base_rev + 1
            self.successful_updates += 1
        result = await super().execute(statement, *args, **kwargs)
        if not isinstance(statement, Update):
            keys = [getattr(c, 'key', None) for c in getattr(statement, 'selected_columns', ())]
            if 'preview_sources' in keys:
                self.preview_reads += 1
                result._rows = [tuple(row) + (self.driver.stored, self.driver.base_rev)
                                for row in result._rows]
        return result


class MemoryFenceConnection:
    """Executes ONLY the two exact preview fence script contracts in memory.

    This is not Redis/Lua integration evidence. It lets the real producer own
    its epoch and serialize its publish payload rather than inventing frames.
    """
    def __init__(self, driver):
        self.driver = driver
        self.epoch = 0
        self.owner = None
        self.response = None
        self.disconnected = False
    async def send_command(self, command, script, nkeys, *args):
        assert command == 'EVAL'
        if script == blend_preview.FENCE_CLAIM_SCRIPT:
            assert nkeys == 2
            self.epoch += 1
            self.owner = self.epoch
            if self.driver.on_owner_epoch is not None:
                self.driver.on_owner_epoch(self.epoch)
            self.response = self.epoch
        elif script == blend_preview.FENCE_PUBLISH_SCRIPT:
            assert nkeys == 1
            _, epoch, *offers = args
            published = fenced = 0
            for i in range(0, len(offers), 3):
                kind, channel, payload = offers[i:i + 3]
                if kind == 'revoke' or self.owner == epoch:
                    await self.driver._capture(json.loads(payload), 'preview',
                                               channel=channel, serialized_payload=payload)
                    published += 1
                else:
                    fenced += 1
            self.response = (published, fenced, str(self.owner or ''))
        else:
            raise AssertionError('Unexpected Redis script; no network fallback exists')
    async def read_response(self):
        return self.response
    async def disconnect(self):
        self.disconnected = True


class MemoryPool:
    def __init__(self, connection):
        self.connection = connection
    async def get_connection(self, *args):
        return self.connection
    async def release(self, connection):
        assert connection is self.connection


class ProducerDriver:
    """One process-local producer, used serially within its context.

    on_frame(frame, metadata) can be sync or async. Frames are already generated
    by the real producer; metadata describes fixture time and DB attempt order.
    Instantiate with base_rev=0 to align a browser seed at revision zero.
    """
    def __init__(self, *, event_id=1, base_rev=10, initial_value=.2, value=.73,
                 max_uncommitted_s=60.0, on_frame=None, wall=DEFAULT_WALL, on_owner_epoch=None):
        self.event_id, self.base_rev = int(event_id), int(base_rev)
        self.initial_value, self.value = float(initial_value), float(value)
        self.source = 'polymarket'
        self.clock = FixtureClock(wall)
        self.max_uncommitted_s = float(max_uncommitted_s)
        self.on_frame = on_frame
        self.on_owner_epoch = on_owner_epoch
        self.frames, self.steps = [], []
        self.mp = pytest.MonkeyPatch()
        old_wall = wall - timedelta(seconds=1)
        self.stored = {self.source: {'value': initial_value, 'updated_at': old_wall.isoformat(),
                       'observed_basis': {'101': old_wall.timestamp()}, 'observed_value': initial_value}}
        self.event = SimpleNamespace(id=self.event_id, home_team_name='Boston Celtics',
            away_team_name='Golden State Warriors', completed_at=None, status='live',
            commence_time=None, espn_win_prob_home=None, opening_home_probability=None,
            win_probability_sources=self.stored)
        self.market = SimpleNamespace(id=10, event_id=self.event_id, source=self.source,
            external_id='fixture-pm-boston-golden-state', name='Boston Celtics vs. Golden State Warriors',
            status='open', market_metadata={})
        self.outcomes = [SimpleNamespace(id=101 + i, market_id=10, name=name,
            rank=i, current_probability=p, last_updated=wall, is_winner=None,
            external_id=f'fixture-outcome-{101+i}', resolution_source=None)
            for i, (name, p) in enumerate([
                ('Boston Celtics', self.value), ('Golden State Warriors', 1-self.value)])]
        self.session = PreviewSession(self)
        self.registry = None
        self.refresher = None
        self._started = False
    def __enter__(self):
        self.mp.setenv(blend_preview.SOURCE_ENV, self.source)
        self.mp.setenv(blend_preview.EVENT_IDS_ENV, str(self.event_id))
        self.mp.setattr(lbr, '_mono', self.clock.mono)
        clock = self.clock
        class ClockDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                value = clock.now()
                return value if tz is not None else value.replace(tzinfo=None)
        self.mp.setattr(blend_preview, 'datetime', ClockDatetime)
        self.registry = blend_preview.PreviewRegistry(clock=self.clock.mono,
                max_uncommitted_s=self.max_uncommitted_s, wall_clock=lambda: self.clock.now().timestamp())
        self.mp.setattr(blend_preview, '_REGISTRY', self.registry)
        @asynccontextmanager
        async def sessions():
            before = self.session.successful_updates
            yield self.session
            if self.session.successful_updates > before:
                self.session.commits += 1
        self.refresher = lbr.LiveBlendRefresher(self.source, session_factory=sessions)
        # No separate chart/recovery workers are relevant to this boundary test.
        self.mp.setattr(self.refresher, '_start_history', lambda **kw: None)
        self.mp.setattr(self.refresher, '_start_normal_recovery', lambda **kw: None)
        self.refresher._inversion[self.event_id] = (float('inf'), False)
        self.connection = MemoryFenceConnection(self)
        self.refresher._redis = SimpleNamespace(connection_pool=MemoryPool(self.connection))
        async def committed(frames):
            for frame in frames:
                assert self.session.commits > 0, 'Commit frame must follow session commit'
                await self._capture(frame, 'committed')
        self.mp.setattr(self.refresher, '_publish', committed)
        return self
    def __exit__(self, *args):
        self.mp.undo()
    def seed_frame(self):
        frame = build_frame(event_id=self.event_id, probability=self.initial_value,
             source=self.source, source_value=self.initial_value,
             updated_at=self.stored[self.source]['updated_at'], status='live', rev=self.base_rev)
        frame['source_snapshot'] = build_source_snapshot(self.event_id, frame['rev'], self.stored)
        return frame
    async def _capture(self, frame, kind, **extra):
        item = {'kind': kind, 'fixture_at_s': self.clock.seconds,
                'source_observed_at': self.outcomes[0].last_updated.isoformat(),
                'updates_attempted_before_publish': len(self.session.updates),
                'commits_before_publish': self.session.commits,
                'frame': copy.deepcopy(frame),
                'publication_boundary': ('real_publish_previews_memory_fence_fixture'
                    if kind == 'preview' else 'real_commit_frame_capture_after_fake_transaction'),
                'production_redis_or_database_verified': False, **extra}
        if kind == 'preview' and frame['preview']['kind'] == 'blend':
            item['lease_expires_fixture_s'] = self.clock.seconds + frame['preview']['ttl_ms'] / 1000
        self.frames.append(item)
        if self.on_frame is not None:
            outcome = self.on_frame(copy.deepcopy(frame), {k:v for k,v in item.items() if k != 'frame'})
            if inspect.isawaitable(outcome):
                await outcome
    def lease(self, *, at_s=None):
        sample_mono = self.clock.mono() if at_s is None else 1000 + float(at_s)
        if sample_mono < self.clock.mono():
            raise ValueError('Lease sample cannot precede the current fixture clock')
        state = self.registry._events.get(self.event_id)
        entry = state.pending.get(self.source) if state else None
        return {'sample_at_s': sample_mono - 1000, 'pending': entry is not None,
                'remaining_ttl_ms': None if entry is None else max(0, int(
                    (self.max_uncommitted_s - (sample_mono - entry.since)) * 1000)),
                'chain_since_fixture_s': None if entry is None else entry.since - 1000,
                'expired_value': None if state is None else state.expired.get(self.source)}
    async def step(self, at_s, *, locked=True, fresh=None):
        if float(at_s) < self.clock.seconds:
            raise ValueError('Fixture clock cannot run backwards')
        self.clock.seconds = float(at_s)
        self.session.locked = bool(locked)
        if fresh is None:
            fresh = not self._started
        start = len(self.frames)
        before = dict(self.refresher.stats)
        method = 'refresh([event_id])' if fresh else 'refresh_pending() → refresh(())'
        if fresh:
            await self.refresher.refresh([self.event_id], flush_started=self.clock.mono())
        else:
            await self.refresher.refresh_pending(flush_started=self.clock.mono())
        self._started = True
        result = {'at_s': self.clock.seconds, 'method': method, 'row_locked': bool(locked),
                  'fresh_input': bool(fresh), 'source_observed_at': self.outcomes[0].last_updated.isoformat(),
                  'stats_delta': {k:v-before.get(k,0) for k,v in self.refresher.stats.items()
                                  if v != before.get(k,0)},
                  'lock_retry': sorted(self.refresher._lock_retry),
                  'refresh_floor_present': self.event_id in self.refresher._last_refresh_at,
                  'lease': self.lease(), 'publications': copy.deepcopy(self.frames[start:])}
        self.steps.append(result)
        return result
    def report(self):
        return {'source_sha': PINNED_SHA, 'fixture': {'event_id': self.event_id,
              'base_rev': self.base_rev, 'initial_probability': self.initial_value,
              'new_probability': self.value, 'max_uncommitted_s': self.max_uncommitted_s,
              'source_observed_at': self.outcomes[0].last_updated.isoformat(),
              'scheduled_call_times_are_fixture_inputs': True,
              'production_environment_override_verified': False,
              'global_republish_bound_claimed': False},
              'seed_frame': self.seed_frame(), 'steps': self.steps,
              'publications': self.frames, 'preview_stats': dict(self.refresher.preview_stats)}


async def run_scenario(*, times=(0, 2, 4, 6), locked=(True, True, True, False), **kwargs):
    if len(times) != len(locked):
        raise ValueError('times and locked must have equal lengths')
    with ProducerDriver(**kwargs) as driver:
        for time, lock in zip(times, locked):
            await driver.step(time, locked=lock)
        return driver.report()


async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--jsonl', action='store_true', help='init, step, lease, report, close commands')
    args = parser.parse_args()
    if not args.jsonl:
        print(json.dumps(await run_scenario(), indent=2))
        return
    driver = None
    try:
        for line in sys.stdin:
            request = json.loads(line)
            command = request.get('command')
            if command == 'init':
                if driver:
                    driver.__exit__(None, None, None)
                driver = ProducerDriver(**request.get('options', {})).__enter__()
                result = {'seed_frame': driver.seed_frame()}
            elif command == 'step':
                result = await driver.step(request['at_s'], locked=request.get('locked', True),
                                           fresh=request.get('fresh'))
            elif command == 'lease':
                result = driver.lease(at_s=request.get('at_s'))
            elif command == 'report':
                result = driver.report()
            elif command == 'close':
                result = {'closed': True}
            else:
                raise ValueError(f'Unknown command {command}')
            print(json.dumps({'id': request.get('id'), 'result': result}), flush=True)
            if command == 'close':
                break
    finally:
        if driver:
            driver.__exit__(None, None, None)

if __name__ == '__main__':
    asyncio.run(main())
