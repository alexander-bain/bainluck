"""#10090 the preview graph cache's hooks: what the writers hand over and forget.

`preview_from_commit` (composing a preview from a write's RETURNING rows) lost
its trial and was removed in the settings freeze (docs/live-settings.md). What
it shared with `preview_at_receipt` stays and is pinned here: each writer hands
its committed rows over only once committed, a settlement / grade / resolution
/ withdrawal forgets its legs whether or not it committed, and a graph's ranks
follow the re-rank statement's rule.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace as Row

import pytest

from app.tasks import live_blend_refresh as module
from app.tasks.live_blend_refresh import LiveBlendRefresher
from app.utils import blend_preview
from app.utils.aggregation import compute_aggregate_probability, stamp_source_reading
from app.utils.live_blend import (
    MarketOutcomes, compute_source_home_probability, has_proven_home_orientation,
)
from tests.test_blend_preview_ledger_tsp1_10090 import redis_kwargs, rig  # noqa: F401

SOURCES = frozenset({"kalshi", "polymarket"})
EV = 7
HOME, AWAY = "Reynolds / Watt", "Behar / Paris"
CONDITION = "0x" + "20" * 32
MARKET, HOME_LEG, AWAY_LEG = 66756997, 250776126, 250776127
#: Rebound at the start of EVERY test by `anchors` below; these import-time
#: values only serve a caller that runs outside one.
NOW = datetime.now(timezone.utc)
#: The cached read's statement time, and the rows it saw.
READ_AT = NOW - timedelta(seconds=1)
SEEN = NOW - timedelta(seconds=2)
SWITCH_ENV = "SPEED_SWITCH_TODAY_PREVIEW_FROM_COMMIT"


def bag(*, pm=0.46, kalshi=0.5):
    return {"kalshi": {"value": kalshi, "updated_at": (NOW - timedelta(seconds=5)).isoformat()},
            "polymarket": {"value": pm, "updated_at": (NOW - timedelta(seconds=3)).isoformat()}}


def event(*, rev=10, ticket=0, status="live", sources=None, at=None):
    sources = bag() if sources is None else sources
    at = READ_AT if at is None else at
    return Row(id=EV, sport_key="tennis_atp_lyon", home_team_name=HOME, away_team_name=AWAY,
               status=status, completed_at=None, commence_time=NOW - timedelta(hours=3),
               win_probability_sources={"polymarket": sources.get("polymarket")},
               espn_win_prob_home=None, opening_home_probability=None,
               preview_sources=sources, preview_rev=rev, preview_context_at=at,
               preview_read_ticket=ticket)


def legs(*, home="0.460000", away="0.540000", seen=None, market_status="open", ranks=(2, 1)):
    seen = SEEN if seen is None else seen
    market = Row(id=MARKET, source="polymarket", external_id=CONDITION, event_id=EV,
                 name="Lyon Open (Doubles): Reynolds/Watt vs Behar/Paris",
                 status=market_status, market_metadata={})
    rows = [
        Row(id=HOME_LEG, market_id=MARKET, name="Reynolds/Watt", rank=ranks[0],
            current_probability=Decimal(home), last_updated=seen, is_winner=None,
            external_id=CONDITION, resolution_source=None),
        Row(id=AWAY_LEG, market_id=MARKET, name="Behar/Paris", rank=ranks[1],
            current_probability=Decimal(away), last_updated=seen, is_winner=None,
            external_id=CONDITION + "_side1", resolution_source=None),
    ]
    return [MarketOutcomes(market, rows, NOW - timedelta(hours=3), False)]


def returned(*, oid=HOME_LEG, price="0.480000", seen=None, **extra):
    """One row as the price UPDATE ... RETURNING hands it over."""
    seen = NOW if seen is None else seen
    values = dict(id=oid, market_id=MARKET, current_probability=Decimal(price),
                  last_updated=seen, is_winner=None, resolution_source=None,
                  quote_moved=True, database_clock=seen)
    values.update(extra)
    return Row(**values)


def read(r, ev, group, *, overlaid=(), started=None):
    """What `_read_groups` hands the cache: the graph and its un-overlaid rows."""
    rows = {id(row) for entry in group for row in entry.outcomes if row.id not in overlaid}
    r._remember_preview_graphs({EV: (ev, group)}, rows,
                               module._mono() if started is None else started)


async def drained(r):
    task = r._commit_preview_task
    if task is not None:
        await asyncio.wait_for(task, 5)


def proposals(sent):
    return [op for frames in sent for op in frames if op.get("ledger_op") == "propose"]


def comparable(op):
    """An operation as Redis composes it. `stamped_at` is each path's compose
    time (`datetime.now`), the same instant to within the test's run."""
    op = dict(op)
    payload = json.loads(op.pop("payload"))
    assert payload.pop("stamped_at")
    return {**op, "payload": payload}


@pytest.fixture(autouse=True)
def anchors(monkeypatch):
    """Every anchor is an offset from ONE wall-clock read taken at the start of
    THIS test (gotcha #44: offset first; nothing here truncates or branches).

    They used to be taken once, at import. The code under test stamps its own
    pending reading with the real `datetime.now` when it composes, so in a CI
    shard that reached this file minutes after collecting it, the fixture's
    Kalshi stamp (NOW - 5 s) fell more than `HERO_RELATIVE_GRACE_SECONDS`
    behind that stamp, the blend's relative recency decay engaged, and every
    later read of the clock decayed it a little more: the frame (composed
    first) and `_expected_p` (computed after) differed in the sixth place
    (0.549808 vs 0.549807, CI 41069588766). Anchored here, the fixture's
    stamps are seconds old whenever the test runs.
    """
    now = datetime.now(timezone.utc)
    module_globals = globals()
    monkeypatch.setitem(module_globals, "NOW", now)
    monkeypatch.setitem(module_globals, "READ_AT", now - timedelta(seconds=1))
    monkeypatch.setitem(module_globals, "SEEN", now - timedelta(seconds=2))
    return now


@pytest.fixture
def r(monkeypatch, anchors):
    blend_preview.reset_registry_for_tests()
    monkeypatch.setattr(blend_preview, "_REGISTRY", blend_preview.LedgerRegistry(sources=SOURCES))
    monkeypatch.setattr(blend_preview, "preview_events_for",
                        lambda source: frozenset({EV}) if source == "polymarket" else frozenset())
    monkeypatch.setenv(SWITCH_ENV, "1")
    refresher = LiveBlendRefresher("polymarket")
    refresher.sent = []

    async def record(frames, *, prepare_frames=None):
        refresher.sent.append(list(frames))

    monkeypatch.setattr(refresher, "_publish_previews", record)
    yield refresher
    blend_preview.reset_registry_for_tests()


def test_the_fixture_is_a_proven_reading_of_the_home_leg_alone():
    reading = compute_source_home_probability(legs(), HOME, AWAY)
    assert has_proven_home_orientation(reading)
    assert [row.id for row in reading.contributing_outcomes] == [HOME_LEG]
    assert round(reading.home_probability, 4) == 0.46


def _skip_cases():
    later = NOW + timedelta(seconds=1)
    return {
        # The cache never holds a graph it could not compose honestly.
        "overlaid_row": dict(overlaid={HOME_LEG}, uncached=True),
        "not_live": dict(ev=dict(status="scheduled"), uncached=True),
        "no_ticket": dict(ev=dict(ticket=None), uncached=True),
        # Even were the resolver to read a closed market, nothing composes on it.
        "market_closed": dict(legs=dict(market_status="closed"), resolver_admits_closed=True),
        "market_suspended": dict(legs=dict(market_status="suspended"), resolver_admits_closed=True),
        # The committed rows say this is no moving live price.
        "settled_row": dict(row=dict(resolution_source="polymarket")),
        "winner_row": dict(row=dict(is_winner=True)),
        # The re-read path's own gates, not only the cache's.
        "held_quote": dict(held={AWAY_LEG}),
        "lock_retry": dict(lock_retry=True),
        "failed_hold": dict(failed_hold=1.0),
        "stored_unchanged_unobserved": dict(ev=dict(sources=bag(pm=0.48) | {"polymarket": {
            "value": 0.48, "updated_at": (NOW + timedelta(seconds=1)).isoformat()}})),
        "forgotten_after_read": dict(forget=True),
        "not_a_contributor": dict(row=dict(oid=AWAY_LEG, price="0.520000")),
        "older_than_read": dict(row=dict(seen=SEEN - timedelta(seconds=1))),
        "returning_lacks_columns": dict(row=dict(current_probability=None)),
        "unmoved": dict(last_written=0.48),
        # The graph aged, or something newer replaced the committed row.
        "aged": dict(age=module.PREVIEW_GRAPH_MAX_AGE_S + 0.01),
        "superseded_by_newer_read": dict(newer_read=later),
        # The stamp's own path owns these.
        "unproven_orientation": dict(unproven=True),
        "current_book_proof": dict(proof=True),
    }


# e3490dcd: a committed re-rank patches the graph's ranks to `_field_ranks` (what
# `rerank_market_fields_stmt` stores in the write's transaction) instead of
# dropping the graph. live's positive guard (87515fd9 review): both cases red with
# e3490dcd reverted.


async def test_a_change_outside_the_price_write_drops_the_graph_and_its_late_read(r, monkeypatch):
    """A settlement or withdrawal (`forget_preview_outcomes`): the cached graph
    goes, a read that started before the change is never kept, and a read that
    started after it is kept again."""
    clock = [100.0]
    monkeypatch.setattr(module, "_mono", lambda: clock[0])
    read(r, event(), legs())
    clock[0] += 0.1
    r.forget_preview_outcomes([HOME_LEG])
    assert r._preview_graphs == {} and r._preview_graph_outcomes == {}
    read(r, event(at=NOW), legs(), started=clock[0] - 0.05)
    assert r._preview_graphs == {}
    read(r, event(at=NOW), legs(), started=clock[0] + 0.01)
    assert set(r._preview_graphs) == {EV}


def test_field_ranks_are_the_rerank_statements_rule():
    """`field_rank_expr`: rank() (ties share), DESC, NULLS LAST."""
    ranks = module._field_ranks
    assert ranks([Decimal("0.6"), Decimal("0.4")]) == [1, 2]
    assert ranks([Decimal("0.5"), Decimal("0.5"), Decimal("0.1")]) == [1, 1, 3]
    assert ranks([None, Decimal("0.2"), None]) == [2, 1, 2]


# --------------------------------------------------------------- real Redis


def _expected_p(base, pm_value):
    shim = Row(win_probability_sources=stamp_source_reading(dict(base), "polymarket", pm_value),
               status="live", espn_win_prob_home=None, opening_home_probability=None)
    return compute_aggregate_probability(shim, "live")


def _blends(frames):
    return [f for f in frames if f["preview"]["kind"] == "blend"]


@pytest.fixture
def on_redis(rig, r, monkeypatch):  # noqa: F811 — the TSP-1 fixture
    """The refresher's proposals executed by the polymarket process's claimed registry."""
    monkeypatch.setattr(blend_preview, "_REGISTRY", rig.p)

    async def execute(frames, *, prepare_frames=None):
        await rig.p.execute(frames, rig.call, rig.channel, rig.stats)

    monkeypatch.setattr(r, "_publish_previews", execute)
    return rig


async def _ticket(rig):
    ticket, _ = await rig.p.read_ticket(rig.call, "polymarket")
    assert isinstance(ticket, int)
    return ticket


async def test_redis_publishes_the_composed_value_on_the_cached_base(r, on_redis):
    rig = on_redis
    read(r, event(ticket=await _ticket(rig)), legs())
    r.note_committed_rows([returned()])
    await drained(r)
    [frame] = _blends(await rig.drain())
    assert frame["preview"]["pending"] == {"polymarket": 0.48}
    assert frame["p"] == pytest.approx(_expected_p(bag(), 0.48))


async def test_a_retirement_after_the_cached_read_refuses_it_and_the_reread_opens(r, on_redis):
    rig = on_redis
    ticket = await _ticket(rig)
    read(r, event(ticket=ticket), legs())
    # Any retirement since the read moves the ledger-global barrier.
    await rig.p.execute([rig.p.retire_missing(99, "polymarket", ticket)],
                        rig.call, rig.channel, rig.stats)
    assert await _ticket(rig) == ticket + 1
    r.note_committed_rows([returned()])
    await drained(r)
    assert await rig.drain() == []
    assert rig.p.refusal_counts[("polymarket", "read_required")] == 1
    assert not rig.p.has_pending(EV, "polymarket"), "a refused open leaves no local chain"
    # Today's path, unchanged: its own read takes the new ticket and opens.
    ev, group = event(ticket=ticket + 1, at=NOW), legs(home="0.480000", seen=NOW)
    reading = compute_source_home_probability(group, HOME, AWAY)
    await r._preview_before_stamp({EV: (ev, group)}, {EV: (
        [], {}, reading, 0.48, reading.contributing_outcomes)}, {})
    [frame] = _blends(await rig.drain())
    assert frame["preview"]["pending"] == {"polymarket": 0.48}


async def test_a_settle_after_the_cached_read_is_never_previewed_over(r, on_redis):
    rig = on_redis
    ticket = await _ticket(rig)
    read(r, event(ticket=ticket), legs())
    # Another read saw the game finish and recorded the terminal (rev 11).
    await rig.p.execute([rig.p.terminal_read(EV, "polymarket", 11, ticket)],
                        rig.call, rig.channel, rig.stats)
    r.note_committed_rows([returned()])
    await drained(r)
    assert _blends(await rig.drain()) == []


async def test_a_moved_base_composes_on_the_committed_floor_never_the_cached_one(r, on_redis):
    rig = on_redis
    read(r, event(ticket=await _ticket(rig)), legs())
    # A moving game: this arm's previous price is already pending on rev 10.
    r.note_committed_rows([returned(price="0.470000", seen=NOW - timedelta(milliseconds=500))])
    await drained(r)
    assert [f["preview"]["pending"] for f in _blends(await rig.drain())] == [{"polymarket": 0.47}]
    # The other venue's process stamps rev 11 after the cached read.
    bag11 = bag(kalshi=0.62)
    await rig.run(rig.k, rig.k.committed(EV, "kalshi", seq=None, sources=bag11, rev=11,
                                         event=event(rev=11, at=NOW)))
    r.note_committed_rows([returned(price="0.480000", seen=NOW)])
    await drained(r)
    [frame] = _blends(await rig.drain())
    assert frame["preview"]["pending"] == {"polymarket": 0.48}
    assert frame["preview"]["base_rev"] == 11
    assert frame["p"] == pytest.approx(_expected_p(bag11, 0.48))
    assert frame["p"] != pytest.approx(_expected_p(bag(), 0.48))


async def test_with_no_ledger_state_a_moved_base_frame_names_its_older_base(r, on_redis):
    """A commit on an event Redis holds no state for records no base (`none`),
    so the composition stands on the cached rev 10 and its frame says so. The
    reader shows a preview only while it holds no NEWER committed revision
    (`frontend/lib/blendPreview.ts` `displayedPreview`): the rev-11 commit's own
    frame hides it. Today's path has the same exposure inside its read-to-
    propose window; here the window is the cached graph's age."""
    rig = on_redis
    read(r, event(ticket=await _ticket(rig)), legs())
    await rig.run(rig.k, rig.k.committed(EV, "kalshi", seq=None, sources=bag(kalshi=0.62),
                                         rev=11, event=event(rev=11, at=NOW)))
    r.note_committed_rows([returned()])
    await drained(r)
    [frame] = _blends(await rig.drain())
    assert frame["preview"]["base_rev"] == 10
    assert frame["p"] == pytest.approx(_expected_p(bag(), 0.48))


# ------------------------------------------------------------ the PM writer


def _pm_writer(*, fail_commit=False):
    """The SHIPPED `write_chunk` in the PM game flush rig, its UPDATE returning
    the committed rows (`test_pm_event_before_notification_10090`'s seam)."""
    from contextlib import asynccontextmanager

    from app.tasks.polymarket_ws import _PMPriceWriteResult
    from tests.test_polymarket_withdrawal_speed_10651 import ROOT, compile_functions
    from tests.test_polymarket_withdrawal_speed_10651 import rig as pm_rig

    r = pm_rig(batch={1: 0.6, 2: 0.4}, books={})
    noted = []

    class Session:
        def __init__(self):
            self.info = {}

        async def execute(self, statement, params=None):
            if isinstance(statement, tuple) and statement[0] == "prices":
                return Row(all=lambda: [
                    Row(id=oid, ord=i, market_id=10, quote_moved=True, last_updated=NOW,
                        current_probability=Decimal(str(value)), is_winner=False,
                        resolution_source=None, database_clock=NOW)
                    for i, (oid, value) in enumerate(statement[1].items())
                ])
            return Row(rowcount=1)

    @asynccontextmanager
    async def session():
        r.trace.append(("begin", None))
        yield Session()
        if fail_commit:
            raise RuntimeError("commit refused")
        r.trace.append(("commit", None))

    class Refresher:
        async def publish_market_changes(self, session):
            r.trace.append(("market", None))

        def pending_event_ids(self):
            return frozenset()

        async def refresh(self, ids, **kwargs):
            r.trace.append(("refresh", sorted(ids)))

        async def refresh_pending(self, **kwargs):
            pass

        def note_committed_rows(self, rows, marks=None):
            r.trace.append(("noted", [(row.id, row.current_probability) for row in rows]))

    r.ns.update(
        get_task_session=session, blend_refresher=Refresher(),
        _PMPriceWriteResult=_PMPriceWriteResult,
        chunk_price_update_execution=lambda chunk, **kw: (("prices", chunk), {}),
        pm_rerank_market_fields_execution=lambda ids: (
            r.ns["rerank_market_fields_stmt"](ids), {}
        ),
    )
    compile_functions(ROOT / "app/tasks/polymarket_ws.py", ["write_chunk"], r.ns)
    return r


async def test_the_pm_writer_hands_over_its_returned_rows_right_after_commit():
    r = _pm_writer()
    await r.ns["flush_prices"]()
    noted = [entry for entry in r.trace if entry[0] == "noted"]
    assert noted == [("noted", [(1, Decimal("0.6")), (2, Decimal("0.4"))])]
    at = r.trace.index(noted[0])
    assert r.trace[at - 1] == ("commit", None), r.trace
    assert at < r.trace.index(("refresh", [10]))


async def test_a_pm_write_whose_commit_fails_hands_over_nothing():
    r = _pm_writer(fail_commit=True)
    assert await r.ns["flush_prices"]() is False
    assert not [entry for entry in r.trace if entry[0] == "noted"]


# ---------------------------------------------------------- the Kalshi writer


@pytest.mark.parametrize("failure", [None, "rollback", "cancel"])
async def test_the_kalshi_writer_hands_over_its_returned_rows_only_once_committed(failure):
    """`test_kalshi_returned_clock_10090`'s seam: the shipped flush, its price
    phase returning rows, the session's exit held open to look inside it."""
    from contextlib import asynccontextmanager

    from app.utils.kalshi_price_pipeline import PriceRunResult
    from tests.test_kalshi_game_isolation_10655 import rig as kalshi_rig
    from tests.test_kalshi_pipelined_stamps_10090 import held_refresher

    r = kalshi_rig()
    r.batch.pop(3)
    r.batch.pop(9)
    r.release.set()
    stamp_gate, _calls = held_refresher(r, hold_ids=())
    noted = []
    r.ns["blend_refresher"].note_committed_rows = lambda rows, marks=None: noted.append(
        sorted(row.id for row in rows))
    real_phase = r.ns["prices"].phase

    async def phase(session, values, **kwargs):
        async for result in real_phase(session, values, **kwargs):
            yield PriceRunResult(result.attempted, tuple(
                Row(**vars(row), database_clock=NOW, current_probability=Decimal("0.6"),
                    is_winner=None, resolution_source=None) for row in result.rows))

    r.ns["prices"].phase = phase
    real_session = r.ns["get_task_session"]
    exiting, release = asyncio.Event(), asyncio.Event()

    @asynccontextmanager
    async def session():
        async with real_session() as s:
            yield s
            exiting.set()
            await release.wait()
            if failure == "rollback":
                raise RuntimeError("commit refused")
            if failure == "cancel":
                raise asyncio.CancelledError()

    r.ns["get_task_session"] = session
    task = asyncio.create_task(r.flush())
    try:
        await asyncio.wait_for(exiting.wait(), 2)
        assert noted == [], "nothing is handed over before COMMIT"
        release.set()
        if failure == "cancel":
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            assert await asyncio.wait_for(task, 2) is (failure is None)
        assert noted == ([[1, 2]] if failure is None else [])
    finally:
        release.set()
        stamp_gate.set()
        await asyncio.gather(task, return_exceptions=True)
        await r.ns["prices"].join_stamp(r.ns["blend_refresher"])


# ------------------------------------------- changes outside the price write


class _Forgets:
    def __init__(self):
        from app.tasks.live_blend_refresh import HeldRowQuotes

        self.held_quotes = HeldRowQuotes()
        self.forgotten = []
        self.trace = []

    def forget_preview_outcomes(self, ids):
        self.forgotten.append(sorted(ids))
        self.trace.append("forget")

    async def publish_market_changes(self, session):
        self.trace.append("publish")


@pytest.mark.parametrize("status,failure,forgotten", [
    ("determined", None, [[1, 2]]),
    # Committed or not: the commit may have landed, also when a cancellation
    # cuts it (lane1 R2 on 3d769974).
    ("determined", "error", [[1, 2]]),
    ("determined", "cancel", [[1, 2]]),
    ("active", None, []),
])
async def test_a_kalshi_settlement_forgets_its_markets_legs(status, failure, forgotten):
    import logging

    from sqlalchemy import update

    from app.models.models import FuturesMarket, FuturesOutcome
    from app.tasks import kalshi_ws as kalshi_task
    from tests.test_kalshi_held_quotes_10090 import MARKET as KMARKET, _lift, _Session

    class Failing(_Session):
        async def execute(self, stmt, *args):
            if failure == "cancel":
                raise asyncio.CancelledError()
            raise RuntimeError("settlement write refused")

    refresher = _Forgets()
    ns = _lift(
        "handle_lifecycle",
        asyncio=asyncio, update=update, FuturesMarket=FuturesMarket,
        FuturesOutcome=FuturesOutcome, settled_values=kalshi_task.settled_values,
        queue_market_change=lambda *a, **kw: None, is_terminal=kalshi_task.is_terminal,
        open_contract_ids={}, ticker_to_ids={"KXG-A": (KMARKET, 1), "KXG-B": (KMARKET, 2)},
        market_id_by_ext={"KXG": KMARKET}, buffer_lock=asyncio.Lock(),
        price_buffer={}, get_task_session=lambda: (Failing if failure else _Session)([]),
        blend_refresher=refresher, prices=kalshi_task._KalshiPriceOwner(),
        market_id_by_outcome={1: KMARKET, 2: KMARKET, 5: 50},
        logger=logging.getLogger(__name__), stats={"errors": 0, "settlements": 0},
        _UNCAPTURED=object(),
    )
    call = ns["handle_lifecycle"]({"market_ticker": "KXG-A", "status": status, "result": "yes"})
    if failure == "cancel":
        with pytest.raises(asyncio.CancelledError):
            await call
    else:
        await call
    assert refresher.forgotten == forgotten
    if status == "determined" and failure is None:
        # Before the publication's await, where a sibling leg's commit could run.
        assert refresher.trace == ["forget", "publish"]


@pytest.mark.parametrize("failure", [None, "error", "cancel"])
async def test_an_open_contract_grade_forgets_its_leg_committed_or_not(failure):
    """lane1 R1 on 3d769974: the open-contract grade writes one leg's
    `is_winner`, settled price and `last_updated` outside the price write; a
    bridged game-winner leg sits in its live event's cached graph."""
    import logging

    from tests.test_kalshi_held_quotes_10090 import MARKET as KMARKET, _lift, _Session

    graded = Row(id=7, last_updated=NOW)

    async def grade(session, *, market_id, outcome_id, state, result):
        if failure == "cancel":
            raise asyncio.CancelledError()
        if failure == "error":
            raise RuntimeError("grade write refused")
        return graded, None

    refresher = _Forgets()
    stats = {"errors": 0, "open_contract_settlements": 0, "open_contract_markets_resolved": 0,
             "open_contract_lifecycle_unverdicted": 0}
    ns = _lift(
        "handle_open_contract_lifecycle",
        open_contract_settlement_enabled=lambda: True,
        lifecycle_verdict=lambda msg: ("settled", True), lifecycle_state=lambda msg: "settled",
        open_contract_ids={"KXG-A": (KMARKET, 7)}, open_grade_admission=asyncio.Lock(),
        get_task_session=lambda: _Session([]), grade_open_contract_leg=grade,
        queue_market_change=lambda *a, **kw: None, buffer_lock=asyncio.Lock(), price_buffer={},
        blend_refresher=refresher, logger=logging.getLogger(__name__), stats=stats,
    )
    call = ns["handle_open_contract_lifecycle"]("KXG-A", {"market_ticker": "KXG-A"})
    if failure == "cancel":
        with pytest.raises(asyncio.CancelledError):
            await call
    else:
        await call
    assert refresher.forgotten == [[7]]
    if failure is None:
        assert refresher.trace == ["forget", "publish"]
        assert stats["open_contract_settlements"] == 1


def _lift_pm(*names, **ns):
    import ast
    from pathlib import Path

    import app.tasks.polymarket_ws as pm

    source = Path(pm.__file__)
    tree = ast.parse(source.read_text())
    nodes = [n for n in ast.walk(tree)
             if isinstance(n, ast.AsyncFunctionDef) and n.name in names]
    assert sorted(n.name for n in nodes) == sorted(names)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), ns)
    return ns


@pytest.mark.parametrize("failure", [False, True])
async def test_a_pm_resolution_forgets_its_legs_committed_or_not(failure):
    import logging
    from contextlib import asynccontextmanager

    from sqlalchemy import select

    from app.models.models import FuturesMarket

    refresher = _Forgets()

    async def apply(session, market_id, outcomes, verdict):
        if failure:
            raise RuntimeError("resolution write refused")
        return len(outcomes)

    class Session:
        async def execute(self, stmt):
            return Row(scalar_one_or_none=lambda: None)

    @asynccontextmanager
    async def session():
        yield Session()

    ns = _lift_pm(
        "_write_resolution", get_task_session=session, _apply_ws_resolution=apply,
        select=select, FuturesMarket=FuturesMarket, queue_market_change=lambda *a, **k: None,
        blend_refresher=refresher, logger=logging.getLogger(__name__),
    )
    call = ns["_write_resolution"]("0x" + "ab" * 32, 10, [(1, "a"), (2, "b")],
                                   ("winner", 1), {})
    if failure:
        with pytest.raises(RuntimeError):
            await call
    else:
        await call
    assert refresher.forgotten == [[1, 2]]


@pytest.mark.parametrize("fail", [False, True])
async def test_a_pm_withdrawal_forgets_the_withdrawn_legs_committed_or_not(fail):
    from tests.test_polymarket_withdrawal_speed_10651 import rig as pm_rig

    r = pm_rig(batch={}, books={1: (0.1, 0.9)}, fail=fail)
    refresher = _Forgets()
    for name in ("refresh", "refresh_pending"):
        setattr(refresher, name, getattr(r.ns["blend_refresher"], name))
    r.ns["blend_refresher"] = refresher
    result = await r.ns["flush_withdrawals"](only_events={10})
    assert (result is None) is fail
    assert refresher.forgotten == [[1]]
