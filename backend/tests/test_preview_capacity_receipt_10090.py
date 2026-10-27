"""#10090: every preview capacity pass leaves one report-only receipt line.

Production 10/23 had the ledger `full` fleet-wide for a whole minute with no
`maintenance incomplete` line, and a pass that returns silently could not tell
apart (a) a slate wider than 512, (b) rows stuck live/scheduled, and (c) an
incompatible owner withholding the residents. The receipt names which, from
worker-ws logs alone, without changing admission, retirement, cap or TTL.
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import pytest

from app.tasks import live_blend_refresh as lbr
from app.tasks.live_blend_refresh import LiveBlendRefresher
from app.utils import blend_preview

NOW = datetime.now(timezone.utc)


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


class _Rig:
    def __init__(self, monkeypatch, *, tickets, rows=(), reread=(), fail=None, idle=(),
                 redis_now=1_000_000):
        self.tickets = list(tickets)
        self.reads = [list(rows)] + [list(r) for r in reread]
        self.fail = fail
        self.retired, self.missing, self.idle_retired = [], [], []

        @asynccontextmanager
        async def factory():
            yield self

        self.worker = LiveBlendRefresher('kalshi', session_factory=factory)
        self.candidate_ticket = None
        self.policy_rereads = 0

        async def ticket(include_candidates=False):
            # capacity_ticket (the first, candidates call) also returns the
            # ledger's idle hint and Redis TIME (ms, #11565); per-target
            # read_ticket calls return two.
            if include_candidates:
                if self.candidate_ticket is None:
                    self.candidate_ticket = self.tickets.pop(0)
                value = self.candidate_ticket
            elif self.policy_rereads:
                self.policy_rereads -= 1
                value = self.candidate_ticket
            else:
                value = self.tickets.pop(0)
            return (*value, set(idle), redis_now) if include_candidates else value

        async def classify(ticket, candidates):
            # This receipt rig has no policy debt. Real classification and
            # policy retirement are exercised by the reservation PG controls.
            pass

        async def retire_policy(eid, ticket, deadline_ms, when):
            self.policy_rereads += 1

        async def retire(eid, rev, ticket):
            self.retired.append(eid)

        async def retire_idle(eid, ticket, deadline_ms, when):
            self.idle_retired.append(eid)

        async def publish(frames):
            self.missing.extend(frames)

        class _Registry:
            # Receipt-only rig: ledger cleanup has separate reservation controls.
            ledger = False

            @staticmethod
            def retire_missing(eid, source, ticket):
                return ('retire_missing', eid)

        monkeypatch.setattr(self.worker, '_preview_ticket', ticket)
        monkeypatch.setattr(self.worker, '_classify_preview_residents', classify)
        monkeypatch.setattr(self.worker, '_retire_policy_preview_event', retire_policy)
        monkeypatch.setattr(self.worker, '_retire_preview_event', retire)
        monkeypatch.setattr(self.worker, '_retire_idle_preview_event', retire_idle)
        monkeypatch.setattr(self.worker, '_publish_previews', publish)
        monkeypatch.setattr(blend_preview, 'registry', lambda: _Registry)

    async def execute(self, statement, *args, **kwargs):
        if self.fail is not None:
            raise self.fail
        return _Result(self.reads.pop(0) if self.reads else [])


def _receipts(caplog):
    return [r.getMessage() for r in caplog.records
            if 'preview capacity pass' in r.getMessage()]


def _fields(line):
    return dict(part.split('=', 1) for part in line.split(': ', 1)[1].split()[3:])


async def test_full_pass_splits_residents_by_state_and_counts_attempts(monkeypatch, caplog):
    # Anchored at call time, not import: a CI shard runs minutes after import.
    now = datetime.now(timezone.utc)
    rows = [
        (1, 10, False, 'live', now - timedelta(hours=10), now),
        (2, 10, False, 'live', now - timedelta(hours=1), now),
        (3, 10, False, 'scheduled', now + timedelta(hours=2), now),
        (4, 10, True, 'final', now - timedelta(hours=3), now),
        (6, 10, False, 'suspended', now - timedelta(hours=2), now),
    ]
    # Target 4 retires from the first read; target 5 is missing on its reread.
    rig = _Rig(monkeypatch, tickets=[(7, [1, 2, 3, 4, 5, 6]), (8, [])], rows=rows)
    caplog.set_level(logging.INFO, logger=lbr.__name__)
    await rig.worker._maintain_preview_capacity()
    assert rig.retired == [4] and rig.missing == [('retire_missing', 5)]
    [line] = _receipts(caplog)
    assert line.startswith('live_blend_refresh[kalshi]: preview capacity pass end=done ')
    assert _fields(line) == {
        'end': 'done', 'candidates': '6', 'missing': '1', 'retirable': '1',
        'attempted': '2', 'live': '2', 'scheduled': '1', 'suspended': '1',
        'other': '1', 'live_over_6h': '1', 'oldest_live_h': '10.0',
        'idle': '0', 'idle_attempted': '0',
    }


async def test_idle_reclaim_is_counted_apart_from_attempted(monkeypatch, caplog):
    # #11550's idle reclaim: only future-scheduled idle residents are tried;
    # an idle hint on a live row is counted as idle but never attempted.
    now = datetime.now(timezone.utc)
    rows = [
        (2, 10, False, 'live', now - timedelta(hours=1), now),
        (3, 10, False, 'scheduled', now + timedelta(hours=2), now),
        (4, 10, True, 'final', now - timedelta(hours=3), now),
        (9, 10, False, 'scheduled', now + timedelta(hours=5), now),
    ]
    rig = _Rig(monkeypatch, tickets=[(7, [2, 3, 4, 9]), (8, []), (9, [])], rows=rows,
               reread=[[rows[3]], [rows[1]]], idle={2, 3, 9})
    caplog.set_level(logging.INFO, logger=lbr.__name__)
    await rig.worker._maintain_preview_capacity()
    assert rig.retired == [4] and rig.idle_retired == [9, 3] and rig.missing == []
    [line] = _receipts(caplog)
    fields = _fields(line)
    assert fields['end'] == 'done' and fields['attempted'] == '1'
    assert fields['idle'] == '3' and fields['idle_attempted'] == '2'


async def test_spent_idle_budget_is_named_deadline(monkeypatch, caplog):
    # #11565: with no Redis deadline the pass stops before an idle reclaim
    # and the receipt names that, instead of the pass logging nothing.
    now = datetime.now(timezone.utc)
    rows = [(9, 10, False, 'scheduled', now + timedelta(hours=5), now)]
    rig = _Rig(monkeypatch, tickets=[(7, [9])], rows=rows, idle={9}, redis_now=None)
    caplog.set_level(logging.INFO, logger=lbr.__name__)
    await rig.worker._maintain_preview_capacity()
    assert rig.idle_retired == []
    [line] = _receipts(caplog)
    fields = _fields(line)
    assert fields['end'] == 'deadline'
    assert fields['idle'] == '1' and fields['idle_attempted'] == '0'


@pytest.mark.parametrize('ticket, end', [((None, []), 'no_ticket'), ((3, []), 'no_candidates')])
async def test_silent_returns_now_leave_a_receipt(monkeypatch, caplog, ticket, end):
    # These return paths name the observed outcome, not a diagnosed cause.
    # Reservation maintenance can return residents below the total cap too.
    rig = _Rig(monkeypatch, tickets=[ticket])
    caplog.set_level(logging.INFO, logger=lbr.__name__)
    await rig.worker._maintain_preview_capacity()
    [line] = _receipts(caplog)
    fields = _fields(line)
    assert fields['end'] == end and fields['candidates'] == '0'
    assert fields['oldest_live_h'] == '-' and fields['attempted'] == '0'


@pytest.mark.parametrize('stop, end', [
    ('classification', 'ticket_lost'),
    ('policy_item', 'ticket_lost'),
    ('policy_pass', 'ticket_lost'),
    ('empty_after_policy', 'no_candidates'),
])
async def test_reservation_prepass_returns_keep_receipt(monkeypatch, caplog, stop, end):
    rig = _Rig(monkeypatch, tickets=[(7, [9])], idle={9})
    original_ticket = rig.worker._preview_ticket
    candidate_calls = 0

    async def ticket(include_candidates=False):
        nonlocal candidate_calls
        if include_candidates:
            candidate_calls += 1
            if ((stop == 'classification' and candidate_calls == 2)
                    or (stop == 'policy_pass' and candidate_calls == 3)):
                return None, [], set(), 1_000_000
            if stop == 'empty_after_policy' and candidate_calls == 3:
                return 7, [], set(), 1_000_000
        elif stop == 'policy_item':
            return None, []
        return await original_ticket(include_candidates=include_candidates)

    monkeypatch.setattr(rig.worker, '_preview_ticket', ticket)
    caplog.set_level(logging.INFO, logger=lbr.__name__)
    await rig.worker._maintain_preview_capacity()
    [line] = _receipts(caplog)
    assert _fields(line)['end'] == end
    assert rig.retired == [] and rig.idle_retired == [] and rig.missing == []
    assert rig.worker.preview_stats['publish_errors'] == 0


async def test_ticket_lost_mid_pass_is_named(monkeypatch, caplog):
    rows = [(1, 10, True, 'final', NOW), (2, 10, True, 'final', NOW)]
    rig = _Rig(monkeypatch, tickets=[(7, [1, 2]), (None, [])], rows=rows)
    caplog.set_level(logging.INFO, logger=lbr.__name__)
    await rig.worker._maintain_preview_capacity()
    [line] = _receipts(caplog)
    fields = _fields(line)
    assert fields['end'] == 'ticket_lost' and fields['attempted'] == '1'
    assert fields['candidates'] == '2' and fields['retirable'] == '2'


async def test_error_keeps_the_incomplete_warning_and_adds_a_receipt(monkeypatch, caplog):
    rig = _Rig(monkeypatch, tickets=[(7, [1])], fail=RuntimeError('db'))
    caplog.set_level(logging.INFO, logger=lbr.__name__)
    await rig.worker._maintain_preview_capacity()
    assert any('preview capacity maintenance incomplete' in r.getMessage()
               for r in caplog.records)
    assert rig.worker.preview_stats['publish_errors'] == 1
    [line] = _receipts(caplog)
    assert ' end=error ' in line


async def test_counting_fault_never_stops_reclamation(monkeypatch, caplog):
    rows = [(1, 10, True, 'final', NOW)]
    rig = _Rig(monkeypatch, tickets=[(7, [1, 2]), (8, [])], rows=rows)

    counts = rig.worker._preview_capacity_counts

    def broken(candidates, rows, now):
        if rows:
            raise TypeError('count')
        return counts(candidates, rows, now)

    monkeypatch.setattr(rig.worker, '_preview_capacity_counts', broken)
    caplog.set_level(logging.INFO, logger=lbr.__name__)
    await rig.worker._maintain_preview_capacity()
    assert rig.retired == [1] and rig.missing == [('retire_missing', 2)]
    assert rig.worker.preview_stats['publish_errors'] == 0
    assert any('preview capacity receipt uncounted' in r.getMessage() for r in caplog.records)
    [line] = _receipts(caplog)
    assert _fields(line)['end'] == 'done' and _fields(line)['attempted'] == '2'


async def test_cancelled_pass_logs_no_receipt(monkeypatch, caplog):
    rig = _Rig(monkeypatch, tickets=[(7, [1])])
    started = asyncio.Event()

    async def held(statement, *args, **kwargs):
        started.set()
        await asyncio.sleep(60)

    monkeypatch.setattr(rig, 'execute', held)
    caplog.set_level(logging.INFO, logger=lbr.__name__)
    task = asyncio.create_task(rig.worker._maintain_preview_capacity())
    # Fail promptly if maintenance exits before reaching the held DB read.
    await asyncio.wait_for(started.wait(), timeout=2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert _receipts(caplog) == []


def test_alarm_format_is_unchanged():
    # Operators stop on the first ALARM line; the receipt must not move it.
    assert blend_preview.LEDGER_ALARM_FORMAT == (
        "blend_preview ledger ALARM status=%s phase=%s source=%s count=%d event_id=%s")
    assert 'ALARM' not in lbr.PREVIEW_CAPACITY_RECEIPT_FORMAT
