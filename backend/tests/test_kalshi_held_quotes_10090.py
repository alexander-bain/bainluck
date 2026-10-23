"""#10090 — Kalshi's held-quote overlay (#11138's helper) on the SHIPPED flush.

## the ship

A reader holding a live event page sees a changed Kalshi price in the headline
and chart promptly while a foreign transaction holds that price's
`futures_outcomes` row, and keeps seeing newer changes during the write's retry
cooldown. Root's real-PG/EventPage lab (attempt21/24, isolated, on 1a02deea55):
held Kalshi .375 5087.73 ms on the parent → 105.22 ms; a newer quote during the
cooldown 16.09 ms; a known-ambiguous 80 ms lock 2299.94 → 278.29 ms.

## the rig

#10655's rig: the shipped `flush_prices`, exec'd with a controlled session that
refuses a locked row with 55P03 under the periodic budget. A real
`HeldRowQuotes` is installed; only its two database reads are replaced (the
clock sample and `stored_at_or_after`, whose NEW-quotes-only rule the fake
keeps). Event 100's legs are outcomes 1 and 2 (market 10); outcome 1 is held.

## what is asserted (the guards Root's handoff named, before promotion)

* a refused live phase stamps its received quotes now, rows stay buffered,
  and the ordinary write lands them and releases the hold;
* during the write's cooldown a NEWER quote is stamped with no extra UPDATE
  and no change to the retry deadline; an unchanged one costs nothing;
* the known-ambiguity cadence retry: only a POSITIVE read on a LIVE phase,
  one PRICE_FLUSH_SECONDS window per write, then the 2 s backoff; unknown
  reads, non-live phases and the final drain keep the old behaviour;
* non-blend legs never join; a leg whose buffered value is not its mark's
  holds its whole event out; a mark changing during the read is caught by the
  next cooldown flush;
* a settled market (before or during the read) takes no overlay and loses any
  it held; the real lifecycle closures record that and release the legs;
* cancellation during the read keeps every price and holds nothing.

Ordering and state only, not production timing.
"""

from __future__ import annotations

import ast
import asyncio
import itertools
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.tasks.kalshi_ws as kalshi_task
from app.tasks import live_blend_refresh as lbr
from app.tasks.live_blend_refresh import HeldRowQuotes
from tests.test_kalshi_game_isolation_10655 import rig

SOURCE = Path(kalshi_task.__file__)
EVENT, MARKET = 100, 10
PERIOD = 0.25


class Clock:
    def __init__(self, monkeypatch, t=1000.0):
        self.t = t
        monkeypatch.setattr(lbr, "_mono", lambda: self.t)


def held_rig(monkeypatch, *, answer=frozenset(), live=(EVENT,), locked=(1,)):
    """Event 100 only (outcomes 1, 2); outcome ``locked`` refuses under budget.

    ``answer`` is what the pre-hold read reports for NEW quotes: a set of ids
    whose stored row is at/after the bound, None (unknown), or a callable.
    """
    x = rig(locked=set(locked))
    x.release.set()
    for oid in (3, 9):
        x.batch.pop(oid)
    held = HeldRowQuotes()
    held._database_bound = 100.0
    samples, reads = [], []

    async def sample(sessions):
        samples.append(True)
        return True

    async def stored_at_or_after(sessions, quotes):
        new = {
            oid: q for oid, q in quotes.items()
            if held._quotes.get(oid) != (round(float(q[0]), 6), float(q[1]))
        }
        reads.append(dict(new))
        if not new:
            return set()
        if callable(answer):
            return await answer(x, new)
        return None if answer is None else set(answer) & set(new)

    held.sample_database_clock = sample
    held.stored_at_or_after = stored_at_or_after
    refresher = x.ns["blend_refresher"]
    refresher.held_quotes = held
    stamped = []
    original = refresher.refresh

    async def refresh(ids, **kwargs):
        # What the stamp would read for each held leg at this moment.
        stamped.append((tuple(sorted(ids)), dict(held._quotes)))
        return await original(ids, **kwargs)

    refresher.refresh = refresh
    x.ns["flush_period"] = PERIOD
    # #10090 closure names a live set reaches (the rig predates live sets).
    x.ns.setdefault("yield_written_nonlive_tail", kalshi_task.yield_written_nonlive_tail)
    x.ns.setdefault("live_preempts_tail", kalshi_task.live_preempts_tail)
    x.ns["live_event_ids"] = set(live) if live else None
    x.ns["input_marks"] = {}
    seq = itertools.count(1)

    def tick(oid, value):
        mark = SimpleNamespace(outcome_id=oid, seq=next(seq), probability=value)
        x.batch[oid] = (value, None, None)
        x.ns["input_marks"][oid] = mark
        held.note_input(mark)

    x.tick, x.held, x.reads, x.stamped, x.samples = tick, held, reads, stamped, samples
    x.prices = x.ns["prices"]
    tick(1, 0.61)
    tick(2, 0.39)
    return x


def writes_of(x, oid):
    return sum(1 for t in x.trace if t == ("write", oid))


def budgets(x):
    return [v for k, v in x.trace if k == "lock_timeout"]


async def past_the_short_probe(x, clock):
    """#10090 — the first refusal is the short probe; its ordinary attempt is
    at the next flush start. Run both, so the ordinary backoff is in force."""
    await x.flush(flush_started=clock.t)
    clock.t += PERIOD
    await x.flush(flush_started=clock.t)
    assert budgets(x) == ["1ms", "50ms"]


def held_value(x, oid):
    entry = x.held._quotes.get(oid)
    return None if entry is None else entry[0]


async def test_a_refused_live_phase_stamps_its_received_quotes_and_the_write_lands_later(monkeypatch):
    clock = Clock(monkeypatch)
    x = held_rig(monkeypatch)
    assert await x.flush(flush_started=clock.t) is True
    # Rolled back: nothing committed, both prices still buffered.
    assert x.committed == [] and set(x.batch) == {1, 2}
    # The received quotes reached the stamp while the row is held.
    assert x.stamped == [((EVENT,), {1: (0.61, 100.0), 2: (0.39, 100.0)})]
    assert x.reads == [{1: (0.61, 100.0), 2: (0.39, 100.0)}]
    # Not ambiguous, no cadence episode. The refusal was the short probe: the
    # ordinary attempt is at the next flush start, not after the 2 s backoff.
    until = clock.t + PERIOD
    assert x.prices.lock_retry_until == {1: until, 2: until}
    assert x.prices.ambiguous_retry_since == {}
    # The holder lets go; the ordinary write lands both rows.
    x.lock_released.set()
    clock.t = until
    assert await x.flush(flush_started=clock.t) is True
    assert x.committed == [1, 2] and not x.batch
    assert budgets(x) == ["1ms", "50ms"]
    assert 1 not in x.held and 2 not in x.held
    assert not x.prices.lock_retry_until


async def test_a_newer_quote_during_the_cooldown_is_stamped_without_another_update(monkeypatch):
    clock = Clock(monkeypatch)
    x = held_rig(monkeypatch)
    await past_the_short_probe(x, clock)
    deadline = dict(x.prices.lock_retry_until)
    assert deadline == {1: clock.t + x.ns["PRICE_FLUSH_SECONDS"]} | {
        2: clock.t + x.ns["PRICE_FLUSH_SECONDS"]}
    assert writes_of(x, 1) == 2 and len(x.stamped) == 1

    clock.t += PERIOD
    x.tick(1, 0.65)  # attempt21's .395: a newer Kalshi quote, row still held
    assert await x.flush(flush_started=clock.t) is True
    assert writes_of(x, 1) == 2, "no UPDATE inside the write's cooldown"
    assert x.prices.lock_retry_until == deadline, "the retry deadline is unchanged"
    assert held_value(x, 1) == 0.65
    assert x.stamped[-1][0] == (EVENT,) and x.stamped[-1][1][1][0] == 0.65
    assert x.reads[-1] == {1: (0.65, 100.0)}, "only the changed quote is read"

    # An unchanged quote during the cooldown: no read, no stamp, no write.
    clock.t += PERIOD
    stamps = len(x.stamped)
    await x.flush(flush_started=clock.t)
    assert len(x.stamped) == stamps and x.reads[-1] == {}
    assert writes_of(x, 1) == 2


async def test_the_cooldown_admission_waits_for_its_events_running_stamp(monkeypatch):
    clock = Clock(monkeypatch)
    x = held_rig(monkeypatch)
    # Past the probe, so the flushes below sit inside the ordinary 2 s backoff
    # and are cooldown flushes, not the probe's ordinary attempt (#11208 C2).
    await past_the_short_probe(x, clock)
    writes = writes_of(x, 1)
    # The event's stamp is still running when the newer quote arrives.
    never = asyncio.Event()
    x.prices.stamping = asyncio.create_task(never.wait())
    x.prices.stamping_events = {EVENT}
    try:
        clock.t += PERIOD
        x.tick(1, 0.65)
        stamps = len(x.stamped)
        await x.flush(flush_started=clock.t)
        assert len(x.stamped) == stamps and held_value(x, 1) == 0.61
        assert set(x.batch) == {1, 2}, "the newer quote stays buffered"
    finally:
        never.set()
        await x.prices.stamping
    clock.t += PERIOD
    await x.flush(flush_started=clock.t)
    assert held_value(x, 1) == 0.65 and x.stamped[-1][1][1][0] == 0.65
    # Both were cooldown flushes: no write attempt, no new budget.
    assert writes_of(x, 1) == writes and budgets(x) == ["1ms", "50ms"]


@pytest.mark.parametrize("answer,live,fast", [
    ({1}, (EVENT,), True),    # known newer stored row, live game: cadence retry
    (None, (EVENT,), False),  # unknown read: held as before
    (set(), (EVENT,), False),  # held and stamped: nothing to hurry
    ({1}, (), False),         # known but not live: 2 s backoff
])
def test_only_a_known_ambiguity_on_a_live_phase_retries_on_the_cadence(monkeypatch, answer, live, fast):
    async def run():
        clock = Clock(monkeypatch)
        x = held_rig(monkeypatch, answer=answer, live=live)
        await x.flush(flush_started=clock.t)
        # A live phase's first refusal is its short probe: the ordinary attempt
        # follows at the next flush start whatever the overlay said. The
        # cadence EPISODE (``fast``) is still only a known ambiguity's.
        until = clock.t + (PERIOD if live else x.ns["PRICE_FLUSH_SECONDS"])
        assert x.prices.lock_retry_until == {1: until, 2: until}
        # A refused event is not held (its stamp could only republish the row).
        assert (1 in x.held) is (answer != {1})
        assert bool(x.stamped) is (answer != {1})
        assert bool(x.prices.ambiguous_retry_since) is fast
    asyncio.run(run())


async def test_a_sustained_ambiguous_hold_gets_one_window_of_cadence_retries(monkeypatch):
    clock = Clock(monkeypatch)
    x = held_rig(monkeypatch, answer={1})
    window = x.ns["PRICE_FLUSH_SECONDS"]
    start = clock.t
    attempts = []
    writes_per_round = []
    while clock.t < start + 2 * window + 1:
        if not any(u > clock.t for u in x.prices.lock_retry_until.values()):
            attempts.append(clock.t - start)
        before_writes = writes_of(x, 1)
        await x.flush(flush_started=clock.t)
        writes_per_round.append(writes_of(x, 1) - before_writes)
        clock.t = round(clock.t + PERIOD, 6)
    fast = [a for a in attempts if a < window]
    assert fast == [i * PERIOD for i in range(int(window / PERIOD))]
    # Past the window: the ordinary backoff, never a 4 Hz stream.
    slow = [a for a in attempts if a >= window]
    assert slow and all(b - a >= window for a, b in zip(slow, slow[1:]))
    # One initial 1 ms probe plus its immediate ordinary 50 ms retry.
    # Every later round retains the original single-attempt/backoff contract.
    assert writes_per_round[0] == 2
    assert all(count <= 1 for count in writes_per_round[1:])
    assert writes_of(x, 1) == len(attempts) + 1
    assert [value for kind, value in x.trace if kind == "lock_timeout"] == (
        ["1ms"] + ["50ms"] * len(attempts)
    )
    assert x.prices.ambiguous_retry_since == {1: start, 2: start}
    assert not x.stamped, "a refused event is never stamped from a stale row"
    # The write lands: the episode ends with it.
    x.lock_released.set()
    clock.t = max(x.prices.lock_retry_until.values())
    await x.flush(flush_started=clock.t)
    assert x.committed == [1, 2]
    assert x.prices.ambiguous_retry_since == {} and not x.prices.lock_retry_until


async def test_the_final_drain_never_holds_and_waits_for_the_row(monkeypatch):
    Clock(monkeypatch)
    x = held_rig(monkeypatch)
    task = asyncio.create_task(x.flush(final_drain=True))
    await asyncio.sleep(0)
    for _ in range(20):
        if ("lock-wait", 1) in x.trace:
            break
        await asyncio.sleep(0)
    assert ("lock-wait", 1) in x.trace, "the drain waits instead of giving up"
    x.lock_released.set()
    assert await asyncio.wait_for(task, 2) is True
    assert x.committed == [1, 2] and not x.batch
    assert x.reads == [] and not x.held._quotes
    # Its ordinary stamp follows the commit and reads no held quote.
    assert x.stamped == [((EVENT,), {})]


async def test_a_non_blend_leg_never_joins_the_overlay(monkeypatch):
    clock = Clock(monkeypatch)
    x = held_rig(monkeypatch, locked=(1, 2))
    x.ns["non_blend_outcome_ids"].add(2)
    await x.flush(flush_started=clock.t)
    assert 2 not in x.held and held_value(x, 1) == 0.61
    assert all(2 not in quotes for quotes in x.reads)
    assert x.stamped and x.stamped[0][0] == (EVENT,)


async def test_only_a_held_legs_landing_write_bypasses_the_repeat_predicate(monkeypatch):
    """Root attempt30: a held leg's newest quote can equal the stored price, so
    its landing write is forced (the real-PG gate proves the publication). A
    leg the overlay never held keeps the repeat predicate in the same phase."""
    import tests.test_kalshi_game_isolation_10655 as iso

    forced = {}
    params_of = iso.statement_params

    def recording(stmt, bind=None):
        params = params_of(stmt, bind)
        if "kalshi_outcome_id" in params:
            forced[params["kalshi_outcome_id"]] = params["kalshi_force_observation"]
        return params

    monkeypatch.setattr(iso, "statement_params", recording)
    clock = Clock(monkeypatch)
    x = held_rig(monkeypatch, locked=(1, 2))
    x.ns["non_blend_outcome_ids"].add(2)
    # Neither leg is a first observation of this run.
    x.prices.committed_outcome_ids.update({1, 2})
    await x.flush(flush_started=clock.t)
    assert 1 in x.held and 2 not in x.held
    assert forced == {1: False}, "the refused attempt held nothing yet"

    x.lock_released.set()
    clock.t = x.prices.lock_retry_until[1]
    forced.clear()
    assert await x.flush(flush_started=clock.t) is True
    assert forced == {1: True, 2: False}
    assert x.committed == [1, 2] and 1 not in x.held


async def test_a_leg_whose_buffer_is_not_its_mark_holds_its_whole_event_out(monkeypatch):
    clock = Clock(monkeypatch)
    x = held_rig(monkeypatch)
    x.batch[2] = (0.41, None, None)  # buffered without its own input mark
    await x.flush(flush_started=clock.t)
    assert not x.held._quotes and not x.stamped and x.reads == []
    assert set(x.batch) == {1, 2}


async def test_a_mark_changing_during_the_read_is_caught_by_the_next_cooldown_flush(monkeypatch):
    clock = Clock(monkeypatch)

    async def tick_meanwhile(x, quotes):
        if 1 in quotes and quotes[1][0] == 0.65:
            x.tick(1, 0.70)  # arrives while the read is out
        return set()

    x = held_rig(monkeypatch, answer=tick_meanwhile)
    await past_the_short_probe(x, clock)
    # A newer quote; the cooldown flush's read is out when 0.70 arrives.
    clock.t += PERIOD
    x.tick(1, 0.65)
    await x.flush(flush_started=clock.t)
    # The snapshot's own quote is held: a real quote at its own bound.
    assert held_value(x, 1) == 0.65 and x.batch[1][0] == 0.70
    clock.t += PERIOD
    await x.flush(flush_started=clock.t)
    assert held_value(x, 1) == 0.70 and x.stamped[-1][1][1][0] == 0.70
    # Both caught inside the ordinary backoff: cooldown flushes, no write
    # attempt after the probe and its ordinary attempt (#11208 C2).
    assert writes_of(x, 1) == 2 and budgets(x) == ["1ms", "50ms"]


async def test_a_settled_market_takes_no_overlay_and_releases_what_it_held(monkeypatch):
    clock = Clock(monkeypatch)
    x = held_rig(monkeypatch)
    x.held._quotes[1] = (0.55, 90.0)  # held before the market settled
    x.prices.settled_market_ids.add(MARKET)
    await x.flush(flush_started=clock.t)
    assert not x.held._quotes and not x.stamped and x.reads == []
    until = clock.t + PERIOD  # the short probe's ordinary attempt
    assert x.prices.lock_retry_until == {1: until, 2: until}
    assert set(x.batch) == {1, 2}, "the ordinary write still carries the price"


async def test_a_settlement_during_the_read_drops_the_whole_event(monkeypatch):
    clock = Clock(monkeypatch)

    async def settles_meanwhile(x, quotes):
        x.prices.settled_market_ids.add(MARKET)
        return set()

    x = held_rig(monkeypatch, answer=settles_meanwhile)
    await x.flush(flush_started=clock.t)
    assert not x.held._quotes and not x.stamped


async def test_cancellation_during_the_read_keeps_every_price_and_holds_nothing(monkeypatch):
    clock = Clock(monkeypatch)
    entered, never = asyncio.Event(), asyncio.Event()

    async def blocks(x, quotes):
        entered.set()
        await never.wait()

    x = held_rig(monkeypatch, answer=blocks)
    task = asyncio.create_task(x.flush(flush_started=clock.t))
    await asyncio.wait_for(entered.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert set(x.batch) == {1, 2} and x.committed == []
    assert not x.held._quotes and not x.stamped
    x.lock_released.set()
    assert await x.flush(flush_started=clock.t) is True
    assert x.committed == [1, 2] and not x.batch


async def test_a_refresher_without_an_overlay_keeps_the_old_path(monkeypatch):
    clock = Clock(monkeypatch)
    x = held_rig(monkeypatch)
    del x.ns["blend_refresher"].held_quotes
    await x.flush(flush_started=clock.t)
    assert not x.stamped and x.reads == [] and x.samples == []
    until = clock.t + x.ns["PRICE_FLUSH_SECONDS"]
    assert x.prices.lock_retry_until == {1: until, 2: until}


# ── the lifecycle closures: settlement and grading release the overlay ────


def _lift(*names, **ns):
    tree = ast.parse(SOURCE.read_text())
    nodes = [n for n in ast.walk(tree)
             if isinstance(n, ast.AsyncFunctionDef) and n.name in names]
    assert sorted(n.name for n in nodes) == sorted(names)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), "exec"), ns)
    return ns


class _Session:
    def __init__(self, statements):
        self.statements = statements

    async def execute(self, stmt, *args):
        self.statements.append(stmt)
        return SimpleNamespace(first=lambda: None)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _Refresher:
    def __init__(self):
        self.held_quotes = HeldRowQuotes()

    async def publish_market_changes(self, session):
        pass


@pytest.mark.parametrize("status,settles", [("determined", True), ("active", False)])
async def test_a_linked_settlement_frame_releases_and_refuses_its_markets_legs(status, settles):
    from sqlalchemy import update

    from app.models.models import FuturesMarket, FuturesOutcome

    refresher, statements = _Refresher(), []
    for oid in (1, 2, 5):
        refresher.held_quotes._quotes[oid] = (0.5, 100.0)
    ns = _lift(
        "handle_lifecycle",
        asyncio=asyncio, update=update, FuturesMarket=FuturesMarket,
        FuturesOutcome=FuturesOutcome, settled_values=kalshi_task.settled_values,
        queue_market_change=lambda *a, **kw: None, is_terminal=kalshi_task.is_terminal,
        open_contract_ids={}, ticker_to_ids={"KXG-A": (MARKET, 1), "KXG-B": (MARKET, 2)},
        market_id_by_ext={"KXG": MARKET}, buffer_lock=asyncio.Lock(),
        price_buffer={1: (0.6, None, None)}, get_task_session=lambda: _Session(statements),
        blend_refresher=refresher, prices=kalshi_task._KalshiPriceOwner(),
        market_id_by_outcome={1: MARKET, 2: MARKET, 5: 50},
        logger=logging.getLogger(__name__), stats={"errors": 0, "settlements": 0},
        _UNCAPTURED=object(),
    )
    await ns["handle_lifecycle"]({"market_ticker": "KXG-A", "status": status, "result": "yes"})
    assert (MARKET in ns["prices"].settled_market_ids) is settles
    assert (1 in refresher.held_quotes) is not settles
    assert (2 in refresher.held_quotes) is not settles
    assert 5 in refresher.held_quotes, "another market's held leg is untouched"
    assert bool(statements) is settles
    assert ns["price_buffer"] == {1: (0.6, None, None)}, "the buffered price is kept"


def test_an_open_contract_grade_releases_only_its_own_leg():
    source = SOURCE.read_text()
    start = source.index("    async def handle_open_contract_lifecycle(")
    body = source[start:source.index("\n    async def ", start + 10)]
    pop = body.index("price_buffer.pop(outcome_id, None)")
    release = body.index("held.release((outcome_id,))")
    lock = body.rindex("async with buffer_lock:", 0, pop)
    assert lock < pop < release
    assert "async with buffer_lock:" not in body[pop:release]
    assert "settled_market_ids" not in body, (
        "one graded leg must not refuse its market's other open legs"
    )
