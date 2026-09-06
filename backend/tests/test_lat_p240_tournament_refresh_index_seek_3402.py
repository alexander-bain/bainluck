"""LAT-P240 (#3402) — this rail's per-market lookups must SEEK, not scan.

═══ THE DEFECT, MEASURED IN PRODUCTION 2026-09-05 ═══

``_write_refreshed_prices`` loops per returned market and issues two statements
keyed on ``futures_markets.external_id``. The only index covering that column is
the composite ``uq_futures_source_external (source, external_id)``. A probe that
omits the LEADING column still *uses* that index — the planner picks it, and the
plan node even reads ``Index Scan`` — but it cannot seek. It scans the whole
thing.

``EXPLAIN (ANALYZE, BUFFERS)`` on production, same row, same plan shape:

    WHERE fm.external_id = :cid                          5,458.591 ms  31,160 blocks read
    WHERE fm.source = 'polymarket' AND fm.external_id = :cid  0.059 ms       2 blocks read

Two statements per market × ``markets_returned`` 95 = 190 statements, against a
measured ``last_duration_ms`` of 188,869 — 994 ms each. The arithmetic closes,
and it accounts for essentially the whole task.

═══ WHY A TOURNAMENT RAIL IS GUARDED UNDER A SEARCH SHIP ═══

``background`` is a 2-slot queue measured ~1.9x oversubscribed. Overlaying this
task's real occupancy intervals (``recent_durations_at`` + ``recent_durations_ms``)
on the typeahead warmer ring's own holes attributed **654 of 1,290 dead seconds
— 50.7%** to this task, present in all four of the longest holes. The warmed
search head is entirely cold ~42% of the time, and this rail was the single
largest contributor. See #3398 / #3402.

═══ WHAT THIS GUARDS, AND WHY IT IS THE CLASS AND NOT THE LINE ═══

The assertion is not "line 354 has a source predicate". It is: **every statement
this rail emits that filters ``futures_markets.external_id`` also constrains
``futures_markets.source``.** A third statement added to this loop next year with
the same omission fails here without anyone remembering #3402 — which is the
point, because the omission is invisible at the call site and costs a second
every time.

WHY EXECUTION AND NOT SOURCE-READING: the same reason
``test_tournament_refresh_writes_its_book_q428`` gives. ``assert "source" in
source_text`` passes against a dead branch, a second copy of the writer, or a
line after an early ``continue``. Every assertion below reads the compiled SQL of
a statement the shipping code actually emitted.

RED-FIRST BY EXECUTION: with either predicate removed, ``test_every_external_id
_probe_supplies_the_leading_column`` fails naming the offending statement.
"""

from __future__ import annotations

import contextlib
from datetime import datetime, timezone

import pytest
from sqlalchemy.dialects import postgresql

from app.services.polymarket_api import PolymarketMarket
from app.tasks.tournament_price_refresh import _write_refreshed_prices

YES_ID, NO_ID = 7001, 7002
CONDITION = "0xlatp240"

#: The leading column of ``uq_futures_source_external``. Named here once so the
#: assertions read as "the index's leading column" rather than as a string.
LEADING_COLUMN = "futures_markets.source"
PROBED_COLUMN = "futures_markets.external_id"


class _Result:
    """Permissive stand-in; answers every shape rather than only today's."""

    def __init__(self, rows=()):
        self._rows = list(rows)

    def all(self):
        return self._rows

    def fetchall(self):
        return self._rows

    def scalar_one(self):
        return YES_ID

    def scalar_one_or_none(self):
        return None

    def scalar(self):
        return None

    def first(self):
        return self._rows[0] if self._rows else None

    def scalars(self):
        return self

    @property
    def rowcount(self):
        return len(self._rows)

    def __iter__(self):
        return iter(self._rows)


class RecordingSession:
    """Records every statement handed to ``execute``."""

    def __init__(self, outcome_rows):
        self.statements: list[object] = []
        self._outcome_rows = outcome_rows

    async def execute(self, stmt, *args, **kwargs):
        self.statements.append(stmt)
        if getattr(stmt, "is_select", False):
            return _Result(self._outcome_rows)
        return _Result()

    async def commit(self):
        return None

    async def rollback(self):
        return None


def _market(**kw) -> PolymarketMarket:
    defaults = dict(
        condition_id=CONDITION,
        question="Will Carlos Alcaraz win the 2026 US Open?",
        outcomes=["Yes", "No"],
        outcome_prices=[0.61, 0.39],
        best_bid=0.60,
        best_ask=0.62,
        last_trade_price=0.61,
        volume_24h=1234.0,
        active=True,
    )
    defaults.update(kw)
    return PolymarketMarket(**defaults)


async def _run(monkeypatch, markets=None) -> RecordingSession:
    session = RecordingSession([(YES_ID, "Yes"), (NO_ID, "No")])

    # A real async context manager, NOT an AsyncMock: a double built with
    # AsyncMock returns a coroutine from every method, so `async with
    # get_task_session()` fails in every test that uses one while production is
    # correct. (LAT-P239 rule (nn).)
    @contextlib.asynccontextmanager
    async def _fake_session():
        yield session

    import app.tasks.base as base

    monkeypatch.setattr(base, "get_task_session", _fake_session)

    stats = {
        "outcomes_updated": 0,
        "snapshots_written": 0,
        "unpriced": 0,
        "volume_observed": 0,
    }
    await _write_refreshed_prices(
        markets if markets is not None else [_market()],
        stats,
        now=datetime(2026, 9, 6, 4, 30, tzinfo=timezone.utc),
    )
    return session


def _compiled(stmt) -> tuple[str, dict]:
    c = stmt.compile(dialect=postgresql.dialect())
    return str(c), c.params


def _probes(session) -> list[tuple[str, dict]]:
    """Every emitted statement that filters on ``external_id``."""
    out = []
    for stmt in session.statements:
        text, params = _compiled(stmt)
        if PROBED_COLUMN in text:
            out.append((text, params))
    return out


@pytest.mark.asyncio
async def test_the_rail_still_probes_external_id_at_all(monkeypatch):
    """Non-vacuity. If this rail stops probing ``external_id``, the guard below
    would pass over an empty list and quietly protect nothing."""
    session = await _run(monkeypatch)
    probes = _probes(session)
    assert len(probes) >= 2, (
        "expected at least the per-market UPDATE and the per-market SELECT to "
        f"probe {PROBED_COLUMN}; got {len(probes)}. If the rail was "
        "restructured, re-target this guard — do not delete it."
    )


@pytest.mark.asyncio
async def test_every_external_id_probe_supplies_the_leading_column(monkeypatch):
    """THE CLASS GUARD. #3402.

    Not "the two known statements are fixed" — *every* statement this rail
    emits against ``external_id``. A probe without ``source`` scans
    ``uq_futures_source_external`` end to end: 5,458 ms and 31,160 blocks
    against 0.059 ms and 2, measured on production.
    """
    session = await _run(monkeypatch)
    offenders = [
        text for text, _ in _probes(session) if LEADING_COLUMN not in text
    ]
    assert not offenders, (
        f"{len(offenders)} statement(s) filter {PROBED_COLUMN} without "
        f"constraining {LEADING_COLUMN}, the leading column of the only index "
        "that covers it. Each one scans the whole index (~994 ms measured), and "
        "this rail runs two per market, ~95 markets, every 10 minutes on a "
        "2-slot queue. Offending SQL:\n\n" + "\n\n".join(offenders)
    )


@pytest.mark.asyncio
async def test_the_leading_column_is_bound_to_polymarket(monkeypatch):
    """The predicate must be the one the register actually pins.

    A guard that only checked ``source`` appeared somewhere in the text would
    pass on ``source == 'kalshi'`` — which seeks beautifully and matches nothing,
    turning a latency fix into a silent no-op rail. That is this codebase's
    founding false-GREEN shape and the module docstring says so.
    """
    session = await _run(monkeypatch)
    probes = _probes(session)
    assert probes, "non-vacuity is covered by its own test; this one needs rows"
    for text, params in probes:
        bound = {v for v in params.values() if isinstance(v, str)}
        assert "polymarket" in bound, (
            "an external_id probe constrains source to something other than "
            f"'polymarket'; bound string params were {sorted(bound)}. The "
            "register these condition ids come from is "
            "`registered_polymarket_conditions`, and every one of the 518,851 "
            "`0x…` external_ids in futures_markets is polymarket's.\n\n" + text
        )


@pytest.mark.asyncio
async def test_the_predicate_does_not_narrow_what_the_rail_writes(monkeypatch):
    """Behaviour preservation, asserted rather than asserted-in-prose.

    Adding a predicate is only free if it excludes nothing. The outcome writes
    and snapshots must be exactly what they were before #3402 — the fix is a
    plan change, and a plan change that alters output is not a plan change.
    """
    session = await _run(monkeypatch)
    inserts = [
        text for text, _ in (_compiled(s) for s in session.statements)
        if "INSERT INTO futures_odds_snapshots" in text
    ]
    outcome_updates = [
        text for text, _ in (_compiled(s) for s in session.statements)
        if "UPDATE futures_outcomes" in text
    ]
    # Two legs priced (Yes and No) => two outcome updates and two snapshots,
    # unchanged by the predicate, which touches only the market-level lookups.
    assert len(outcome_updates) == 2, outcome_updates
    assert len(inserts) == 2, inserts
