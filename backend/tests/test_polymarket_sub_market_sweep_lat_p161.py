"""LAT-P161: the parent→sub-market ``event_id`` sweep runs ONCE per poll.

THE DEFECT, MEASURED ON PRODUCTION 2026-08-31 (``pg_stat_statements``, age
77 d 9:57 → 1,858 hourly polls):

    UPDATE futures_markets sub SET event_id = parent.event_id
    FROM futures_markets parent WHERE sub.group_type = 'polymarket_sub_market' ...

    calls            83,631      -> 45.0 per poll, exactly BATCH_SIZE-shaped
    total_exec_time  189,625,725 ms  (52.7 hours)
    mean_exec_time   2,267 ms    max 125,417 ms
    shared_blks_read 3,005,544,566   = 20.04% of ALL disk reads in the database
    rows                 15,686      = 0.19 per call, 8.4 per poll

It sat at the end of ``_process_event_batch``, so it fired once per 50 events,
but its predicate names NO batch state — every one of the 45 calls re-scanned the
same corpus. 242,891 unlinked sub-markets carrying a ``group_id`` whose parent has
no ``event_id`` were rescanned 45 times an hour, 1,080 times a day, to write 8.4
rows. It is the single largest disk-read consumer in the database, from 0.001% of
its calls.

WHY IT IS A SHIP AND NOT A TIDY-UP. ``poll_polymarket_markets`` has a p95 duration
of 459,001 ms against a **540 s soft limit** — 85% of its kill budget — and this
statement is ~102 s of that (22%). A poll that is cut off stops refreshing
Polymarket prices, which are what the Discover cards and the politics / economics
/ entertainment pages print.

WHAT THESE GUARDS ARE FOR. There was no test in this repo that executed this sweep
at all — the reason it survived. So these tests DRIVE ``_poll_polymarket_markets``
and count real calls; they never read source text. Two of them exist only to prove
the instrument can see a number other than the one the claim wants (a zero, or a
one, is not evidence until the counter has been shown to move).
"""

from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

from app.tasks import polymarket as poly


class _FakeRedis:
    """No-op stand-in for the page-cursor client."""

    def get(self, *_a, **_k):
        return None

    def setex(self, *_a, **_k):
        return True


class _FakeService:
    """Gamma stand-in: `pages` pages of `per_page` events, then empty."""

    def __init__(self, pages: int, per_page: int, raise_on_get_events: bool = False):
        self._pages = pages
        self._per_page = per_page
        self._raise = raise_on_get_events
        self.closed = False

    async def get_events(self, *, offset: int = 0, **_kw):
        if self._raise:
            raise RuntimeError("gamma exploded")
        page = offset // 100
        if page >= self._pages:
            return []
        return [{"id": f"evt-{page}-{i}"} for i in range(self._per_page)]

    async def get_tags(self, *_a, **_k):
        # Settled-recovery pass contributes no extra batches in these runs.
        return []

    def _parse_event(self, event_data):
        return SimpleNamespace(id=event_data["id"], markets=[{"m": 1}], active=True)

    async def close(self):
        self.closed = True


def _run_poll(
    monkeypatch,
    *,
    pages: int = 1,
    per_page: int = 100,
    explode_batch: bool = False,
):
    """Execute the real ``_poll_polymarket_markets`` with the DB and Gamma stubbed.

    Returns ``(stats, counters)`` where ``counters`` records how many times the
    batch processor and the sweep actually RAN. Nothing here inspects source text.

    ``explode_batch`` raises from the batch processor, which is the reachable way
    to a TOP-LEVEL error: a ``get_events`` failure is caught by the poll's own
    per-page handler and only breaks pagination, so it never unwinds that far.
    (The first draft of this file assumed otherwise and the guard caught it.)
    """
    import asyncio

    counters = {"batches": 0, "sweeps": 0}

    async def _fake_batch(*_a, **_k):
        counters["batches"] += 1
        if explode_batch:
            raise RuntimeError("batch exploded")

    async def _fake_sweep():
        counters["sweeps"] += 1
        return 7  # a distinguishable, non-zero rowcount

    def _fake_session(*_a, **_k):
        # Both one-time cleanup blocks are wrapped in `try/except Exception`, so
        # refusing a session skips them without touching the path under test.
        raise RuntimeError("no database in this harness")

    service = _FakeService(pages, per_page)

    monkeypatch.setattr(poly, "_process_event_batch", _fake_batch)
    monkeypatch.setattr(poly, "link_polymarket_sub_markets", _fake_sweep)
    monkeypatch.setattr(poly, "get_task_session", _fake_session)
    monkeypatch.setattr(
        "app.tasks.redis_state.get_redis_client", lambda *a, **k: _FakeRedis()
    )
    monkeypatch.setattr(
        "app.services.polymarket_api.PolymarketAPIService", lambda *a, **k: service
    )

    stats = asyncio.run(poly._poll_polymarket_markets())
    return stats, counters


# --------------------------------------------------------------------------
# HARNESS VALIDITY. These come first on purpose. Every assertion below them is
# "the sweep ran exactly once", and a harness that cannot count to two would
# satisfy that while measuring nothing.
# --------------------------------------------------------------------------


def test_harness_can_see_more_than_one_batch(monkeypatch):
    """The batch counter must be able to reach a number > 1.

    If it could not, `sweeps == 1` would be indistinguishable from
    `there was only ever one batch`, and the whole file would be vacuous.
    """
    _stats, counters = _run_poll(monkeypatch, pages=1, per_page=100)
    assert counters["batches"] >= 2, (
        "harness is vacuous: one page of 100 events at BATCH_SIZE=50 must drive "
        f"at least 2 batches, saw {counters['batches']}"
    )


def test_harness_can_see_more_than_one_sweep(monkeypatch):
    """The sweep counter must be able to reach 2 when the sweep is called twice.

    Proves the counter is wired to the name the poll actually calls, so a later
    `== 1` is a measurement rather than a counter that never moves.
    """
    import asyncio

    counters = {"sweeps": 0}

    async def _fake_sweep():
        counters["sweeps"] += 1
        return 0

    monkeypatch.setattr(poly, "link_polymarket_sub_markets", _fake_sweep)

    async def _twice():
        await poly.link_polymarket_sub_markets()
        await poly.link_polymarket_sub_markets()

    asyncio.run(_twice())
    assert counters["sweeps"] == 2


# --------------------------------------------------------------------------
# THE CLAIM
# --------------------------------------------------------------------------


def test_sweep_runs_once_per_poll_not_once_per_batch(monkeypatch):
    """One page / 100 events / BATCH_SIZE=50 → many batches, exactly ONE sweep."""
    _stats, counters = _run_poll(monkeypatch, pages=1, per_page=100)
    assert counters["batches"] >= 2
    assert counters["sweeps"] == 1, (
        "the sub-market sweep must run once per POLL. Once per batch is the "
        "defect: 45 calls/poll, 20.04% of all database disk reads, to write 8.4 rows"
    )


def test_sweep_count_does_not_grow_with_the_number_of_batches(monkeypatch):
    """Triple the events and the sweep count must not move.

    This is the property that actually bounds the cost. A per-batch sweep would
    scale 1:1 with batches here; a per-poll sweep is flat.
    """
    _s1, small = _run_poll(monkeypatch, pages=1, per_page=100)
    _s2, large = _run_poll(monkeypatch, pages=3, per_page=100)

    assert large["batches"] > small["batches"], (
        "harness did not actually scale the batch count — the comparison below "
        f"would be vacuous (small={small['batches']}, large={large['batches']})"
    )
    assert small["sweeps"] == large["sweeps"] == 1, (
        f"sweep count tracked batch count: {small} vs {large}"
    )


def test_sweep_still_runs_when_the_poll_raises(monkeypatch):
    """A top-level failure must still write the links it can.

    Per-batch, a poll that blew up kept whatever the completed batches had swept.
    The replacement must not be weaker, which is why the call sits after the
    top-level `finally` rather than at the end of the `try`.
    """
    stats, counters = _run_poll(monkeypatch, pages=1, per_page=100, explode_batch=True)
    assert counters["sweeps"] == 1, (
        "the sweep was skipped on the error path — this is strictly worse than "
        "the per-batch behaviour it replaced"
    )
    assert stats["errors"], "harness bug: the poll was supposed to record an error"


def test_rowcount_is_reported_in_stats(monkeypatch):
    """The sweep's rowcount reaches `stats`, so a dead sweep is visible.

    Note this also fixes a reporting bug: the per-batch version ASSIGNED
    `stats["sub_markets_linked"] = rowcount` on every batch with a non-zero
    result, so the number reported was the last such batch's, never the poll's
    total. "It returned" is not "it worked" (gotcha #53).
    """
    stats, _counters = _run_poll(monkeypatch, pages=1, per_page=100)
    assert stats["sub_markets_linked"] == 7


# --------------------------------------------------------------------------
# EQUIVALENCE. The move must not have edited the statement.
# --------------------------------------------------------------------------


def test_the_statement_is_byte_equivalent_to_the_one_it_replaced(monkeypatch):
    """The SQL is the graded original, modulo whitespace and its alias binding.

    The whole safety argument for running this once per poll is that the
    predicate is GLOBAL — it reads committed table state and names no batch. If a
    future edit adds a batch-scoped clause, the hoist stops being equivalent and
    links go missing silently. Pin the exact predicate.
    """
    normalized = re.sub(r"\s+", " ", poly.LINK_SUB_MARKETS_SQL).strip()
    expected = (
        "UPDATE futures_markets sub "
        "SET event_id = parent.event_id "
        "FROM futures_markets parent "
        "WHERE sub.group_type = 'polymarket_sub_market' "
        "AND sub.event_id IS NULL "
        "AND sub.group_id IS NOT NULL "
        "AND parent.source = 'polymarket' "
        "AND parent.group_type = 'polymarket_event' "
        "AND parent.group_id = sub.group_id "
        "AND parent.event_id IS NOT NULL"
    )
    assert normalized == expected


def test_the_predicate_names_no_batch_state():
    """No bind parameter may enter the sweep's predicate.

    A `:group_ids`-style clause would make the statement depend on the caller,
    which is exactly what would break the once-per-poll equivalence.
    """
    assert ":" not in poly.LINK_SUB_MARKETS_SQL, (
        "the sweep grew a bind parameter — it is no longer batch-independent and "
        "the once-per-poll hoist is no longer equivalence-preserving"
    )


def _batch_processor_symbols() -> tuple[set[str], list[str]]:
    """Identifiers referenced, and string literals contained, by the batch loop.

    Read off the AST, NOT the raw source. Two reasons, both of which bit this file:

    * A guard on raw text goes RED on a COMMENT that merely names the thing it is
      forbidding — the breadcrumb left where the sweep used to live did exactly
      that (the inverse of the "docstring quotes the SQL" vacuity class).
    * A guard on one spelling misses the others. The battery's M2 restored the
      full 45-calls-per-poll defect as
      ``session.execute(_text(LINK_SUB_MARKETS_SQL))`` — same statement, same
      cost, and the SQL literal appears nowhere in the function.
    """
    import ast
    import inspect
    import textwrap

    tree = ast.parse(textwrap.dedent(inspect.getsource(poly._process_event_batch)))
    names: set[str] = set()
    strings: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            strings.append(node.value)
    return names, strings


@pytest.mark.parametrize(
    "identifier", ["LINK_SUB_MARKETS_SQL", "link_polymarket_sub_markets"]
)
def test_the_batch_processor_references_no_sweep_symbol(identifier):
    """The batch loop may not reach the sweep by name, in any spelling."""
    names, _strings = _batch_processor_symbols()
    assert identifier not in names, (
        f"_process_event_batch references {identifier!r} — running the sweep per "
        "batch is the 20.04%-of-all-disk-reads defect (45 calls/poll to write 8.4 rows)"
    )


def test_the_batch_processor_inlines_no_copy_of_the_statement():
    """Nor by pasting the SQL back in as a literal."""
    _names, strings = _batch_processor_symbols()
    offenders = [s for s in strings if "SET event_id = parent.event_id" in s]
    assert not offenders, (
        "_process_event_batch contains an inlined copy of the sub-market sweep"
    )


@pytest.mark.parametrize("attr", ["link_polymarket_sub_markets", "LINK_SUB_MARKETS_SQL"])
def test_the_sweep_is_reachable_at_module_scope(attr):
    """It stays importable so a guard can execute it without driving a poll.

    The failure mode this queue inherited (CERT-523) was a fix that lived behind a
    helper production never called, green behind ~30 tests that read its source.
    """
    assert hasattr(poly, attr)
