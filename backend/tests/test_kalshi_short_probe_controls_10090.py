"""#10090 — a live phase's short first lock probe, and its exact escalation.

A refused 1 ms probe gets the phase's ordinary 50 ms attempt in the same flush
(overlay refused as ambiguous) or at the next flush start (overlay admitted or
unknown), never a second probe in one write episode. A probe refusal is not an
error: it is counted apart and logged below ERROR (worker-ws sends ERROR to
Sentry). Root attempt37; live qualification R1/R2 (2026-10-17 2211Z).
"""
import logging

import pytest

from tests.test_kalshi_held_quotes_10090 import (
    Clock, EVENT, PERIOD, held_rig, writes_of,
)


@pytest.mark.asyncio
async def test_only_one_short_probe_then_original_episode_and_backoff(monkeypatch):
    clock = Clock(monkeypatch)
    x = held_rig(monkeypatch, answer={1})
    start = clock.t
    window = x.ns['PRICE_FLUSH_SECONDS']
    rounds = []
    while clock.t < start + 2 * window + 1:
        before = writes_of(x, 1)
        await x.flush(flush_started=clock.t)
        count = writes_of(x, 1) - before
        rounds.append((clock.t - start, count))
        assert not x.stamped and not x.held._quotes
        assert set(x.batch) == {1, 2}
        clock.t = round(clock.t + PERIOD, 6)
    assert rounds[0] == (0.0, 2)
    assert all(count <= 1 for _, count in rounds[1:])
    active = [t for t, count in rounds if count]
    assert [t for t in active if t < window] == [i * PERIOD for i in range(int(window / PERIOD))]
    slow = [t for t in active if t >= window]
    assert slow and all(b - a >= window for a, b in zip(slow, slow[1:]))
    budgets = [value for kind, value in x.trace if kind == 'lock_timeout']
    assert budgets == ['1ms'] + ['50ms'] * (sum(c for _, c in rounds) - 1)
    x.lock_released.set()
    clock.t = max(x.prices.lock_retry_until.values())
    await x.flush(flush_started=clock.t)
    assert x.committed == [1, 2] and not x.batch
    assert not x.prices.lock_retry_until and not x.prices.ambiguous_retry_since


@pytest.mark.asyncio
async def test_immediate_escalation_lands_newer_snapshot_after_probe(monkeypatch):
    clock = Clock(monkeypatch)

    async def release_and_change(x, quotes):
        assert quotes[1] == (.61, 100.0)
        x.tick(1, .70)
        x.lock_released.set()
        return {1}

    x = held_rig(monkeypatch, answer=release_and_change)
    from tests import test_kalshi_game_isolation_10655 as price_rig
    original_price_writes = price_rig.price_writes
    observed_writes = []

    def capture_writes(statement, params):
        writes = original_price_writes(statement, params)
        observed_writes.extend(writes)
        return writes

    monkeypatch.setattr(price_rig, "price_writes", capture_writes)
    assert await x.flush(flush_started=clock.t)
    assert [float(value) for oid, value in observed_writes if oid == 1] == [.61, .70]
    assert writes_of(x, 1) == 2
    assert x.committed == [1, 2] and not x.batch
    assert not x.held._quotes and not x.prices.lock_retry_until
    assert x.stamped == [((EVENT,), {})]
    assert [v for k, v in x.trace if k == 'lock_timeout'] == ['1ms', '50ms']


@pytest.mark.asyncio
@pytest.mark.parametrize('answer', [None, set()])
async def test_unknown_or_admitted_refusal_gets_its_ordinary_attempt_at_the_next_flush_start(
    monkeypatch, answer,
):
    clock = Clock(monkeypatch)
    x = held_rig(monkeypatch, answer=answer)
    start = clock.t
    window = x.ns['PRICE_FLUSH_SECONDS']
    await x.flush(flush_started=clock.t)
    assert writes_of(x, 1) == 1
    assert [v for k, v in x.trace if k == 'lock_timeout'] == ['1ms']
    assert x.prices.lock_retry_until == {1: start + PERIOD, 2: start + PERIOD}
    assert not x.prices.ambiguous_retry_since
    assert set(x.batch) == {1, 2} and not x.committed
    assert x.stamped[0][1] == {1: (.61, 100.0), 2: (.39, 100.0)}
    # Still held at the next flush start: the ordinary attempt, then 2 s.
    clock.t = start + PERIOD
    await x.flush(flush_started=clock.t)
    assert [v for k, v in x.trace if k == 'lock_timeout'] == ['1ms', '50ms']
    assert x.prices.lock_retry_until == {1: clock.t + window, 2: clock.t + window}
    # Past the backoff: the ordinary budget again, never a second short probe.
    clock.t += window
    await x.flush(flush_started=clock.t)
    assert [v for k, v in x.trace if k == 'lock_timeout'] == ['1ms', '50ms', '50ms']
    x.lock_released.set()
    clock.t += window
    await x.flush(flush_started=clock.t)
    assert x.committed == [1, 2] and not x.batch
    assert not x.prices.short_probe_refused, 'the episode ends with the write'
    # The next write episode starts with a short probe again.
    x.lock_released.clear()
    x.tick(1, .66)
    clock.t += PERIOD
    await x.flush(flush_started=clock.t)
    assert [v for k, v in x.trace if k == 'lock_timeout'][-1] == '1ms'


def brief_lock(x):
    """A holder that releases within 50 ms but not within 1 ms."""
    budgets = lambda: [v for k, v in x.trace if k == 'lock_timeout']
    x.lock_released.is_set = lambda: bool(budgets()) and budgets()[-1] != '1ms'
    return budgets


@pytest.mark.asyncio
@pytest.mark.parametrize('answer', [set(), None])
async def test_a_brief_lock_with_an_admitted_overlay_lands_by_the_next_flush_start(
    monkeypatch, answer,
):
    clock = Clock(monkeypatch)
    x = held_rig(monkeypatch, answer=answer)
    budgets = brief_lock(x)
    start = clock.t
    await x.flush(flush_started=clock.t)
    assert not x.committed and budgets() == ['1ms']
    clock.t = start + PERIOD
    await x.flush(flush_started=clock.t)
    assert x.committed == [1, 2] and not x.batch, budgets()
    assert budgets() == ['1ms', '50ms']
    assert not x.prices.lock_retry_until and not x.prices.short_probe_refused


@pytest.mark.asyncio
async def test_a_recurring_brief_lock_is_written_at_the_second_flush(monkeypatch):
    clock = Clock(monkeypatch)
    x = held_rig(monkeypatch, answer=set())
    budgets = brief_lock(x)
    start = clock.t
    flushes = 0
    while clock.t < start + 5 * x.ns['PRICE_FLUSH_SECONDS'] and not x.committed:
        await x.flush(flush_started=clock.t)
        flushes += 1
        clock.t = round(clock.t + x.ns['flush_period'], 6)
    assert x.committed == [1, 2] and flushes == 2, budgets()


@pytest.mark.asyncio
async def test_a_short_probe_refusal_is_counted_apart_and_never_logged_as_an_error(
    monkeypatch, caplog,
):
    clock = Clock(monkeypatch)
    x = held_rig(monkeypatch, answer=set())
    caplog.set_level(logging.DEBUG)
    await x.flush(flush_started=clock.t)
    assert x.stats['short_probe_refused'] == 2
    assert x.stats['errors'] == 0 and x.stats['requeued'] == 0
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert any('short probe refused' in r.getMessage() for r in caplog.records)
    # Its ordinary attempt's refusal is a real failed write, as before.
    caplog.clear()
    clock.t += PERIOD
    await x.flush(flush_started=clock.t)
    assert x.stats['errors'] == 1 and x.stats['requeued'] == 2
    assert x.stats['short_probe_refused'] == 2
    assert [r.levelno for r in caplog.records if r.levelno >= logging.ERROR] == [logging.ERROR]


@pytest.mark.asyncio
async def test_a_phase_without_a_flush_start_never_probes(monkeypatch):
    clock = Clock(monkeypatch)
    x = held_rig(monkeypatch, answer=set())
    await x.flush()
    assert [v for k, v in x.trace if k == 'lock_timeout'] == ['50ms']
    assert x.stats['short_probe_refused'] == 0 and not x.prices.short_probe_refused


@pytest.mark.asyncio
async def test_a_refusal_ends_with_its_buffered_price_like_the_ambiguity_episode(monkeypatch):
    clock = Clock(monkeypatch)
    x = held_rig(monkeypatch, answer=set())
    await x.flush(flush_started=clock.t)
    assert x.prices.short_probe_refused == {1, 2}
    # The prices leave the buffer unwritten (a settlement's removal): the next
    # flush's snapshot forgets the refusal with the price that earned it.
    x.batch.clear()
    clock.t += PERIOD
    await x.flush(flush_started=clock.t)
    assert not x.prices.short_probe_refused
    x.tick(1, .62)
    x.tick(2, .38)
    clock.t += PERIOD
    await x.flush(flush_started=clock.t)
    assert [t[1] for t in x.trace if t[0] == 'lock_timeout'] == ['1ms', '1ms']


#: A beside pass's exclusion of the running flush's unfinished input: nothing.
BESIDE_NOTHING_EXCLUDED = (frozenset(), frozenset(), frozenset())


@pytest.mark.asyncio
@pytest.mark.parametrize('answer', [set(), None])
@pytest.mark.parametrize('offset', [0.05, 0.10, 0.20])
async def test_a_beside_pass_never_probes_so_a_brief_lock_lands_by_the_next_main_start(
    monkeypatch, answer, offset,
):
    """#11208 C1 (Authority's probe): `serve_live_beside` runs on its own clock
    `offset` s into a main flush. A probe refusal there would set its retry to
    beside start + period, past the main flush's next start, so the row and its
    chart point would wait ~2 periods. The beside pass writes at the ordinary
    budget at once, as before the probe existed."""
    clock = Clock(monkeypatch)
    x = held_rig(monkeypatch, answer=answer)

    def budgets():
        return [v for k, v in x.trace if k == 'lock_timeout']

    # A brief lock: refuses the 1 ms probe, admits the 50 ms budget.
    x.lock_released.is_set = lambda: bool(budgets()) and budgets()[-1] != '1ms'
    main_start = clock.t
    clock.t = main_start + offset
    await x.flush(clock.t, beside=BESIDE_NOTHING_EXCLUDED)
    assert x.committed == [1, 2], (budgets(), dict(x.prices.lock_retry_until))
    assert budgets() == ['50ms']
    assert not x.prices.short_probe_refused and not x.prices.lock_retry_until
