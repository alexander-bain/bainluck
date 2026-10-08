"""#10734 — a deferred open-contract grade ends where the inline grade ended. Real Postgres.

THE SHIP. An open-contract Kalshi connection now hands its per-leg grade
(#10022) to the #10667 dispatcher, so an unrelated contract's quote is read,
buffered and stored while another contract's settlement is still in its
transaction. The unit file (``tests/test_ws_open_contract_auxiliary_dispatch_10734.py``)
proves the callback order with a recording grader; a recording grader writes
no row, so it cannot say what the database holds afterwards. This file runs
the real consumer, the real dispatcher, the real admission rule, the real
grader and the real flush SQL on Postgres. Only the slate SELECTs are replayed
(they are the subscription, not the subject) and the socket is a recording one.

    the_ship ................. While SD21's grade transaction is held open, the
                               unrelated SGA quote is committed (read from a
                               second connection). With admission refused (the
                               old inline shape) it is not. Both arms then end
                               in the same rows: each leg its venue's 0/1 and
                               ``api_settlement``, SD20 the only winner, the
                               board resolved once, by its last leg; SD21's late
                               0.51 quote refused by the #5411 guard; opening and
                               calibration prices untouched; no history rows;
                               every frame published only after its row was
                               committed.
    two_prefixes_stay_inline . One market whose legs carry two ticker prefixes.
                               The real admission keeps that connection inline,
                               so the second leg grades after the first commits
                               and the board resolves. STRAWMAN: force the
                               connection prepared and the second leg's
                               ``NOT EXISTS`` reads the first leg's open
                               transaction — both legs graded, board left open.
                               That is the hazard the admission rule exists for.

Opt-in on ``DELAY_CONTRACT_DATABASE_URL`` (CI job ``search-recall``, group
``isolated``, the #10022 step's database). This file drops and creates only the
tables it names.
"""

from __future__ import annotations

import asyncio
import json
import os

import pytest

DB_URL = os.environ.get("DELAY_CONTRACT_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set DELAY_CONTRACT_DATABASE_URL to run the real-Postgres deferred "
            "open-contract grade gate (CI job `search-recall` provisions one)"
        ),
    ),
]

BOARD = "KXMLBSERIESSCORE-26CHCSDWC"
SD20, SD21, CHC21, CHC20 = (f"{BOARD}-{s}" for s in ("SD20", "SD21", "CHC21", "CHC20"))
SGA = "KXNBAMVP-27-SGA"
SPLIT_X, SPLIT_Y = "KXSPLITA-26-X", "KXSPLITB-26-Y"

TABLES = (
    "sports", "teams", "venues", "events", "futures_markets", "futures_outcomes",
    "futures_odds_snapshots",
)


# ------------------------------------------------------------- the database ----


@pytest.fixture
async def pg():
    """(async engine, sync engine) on freshly created tables."""
    from sqlalchemy import create_engine
    from sqlalchemy.ext.asyncio import create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    wanted = [Base.metadata.tables[name] for name in TABLES]
    engine = create_async_engine(DB_URL)
    sync = create_engine(DB_URL.replace("+asyncpg", "+psycopg2"))
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all, tables=wanted, checkfirst=True)
        await conn.run_sync(Base.metadata.create_all, tables=wanted)
    try:
        yield engine, sync
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all, tables=wanted, checkfirst=True)
        await engine.dispose()
        sync.dispose()


async def _seed(engine, markets):
    """``markets``: {market ticker: [(leg ticker, price, is_winner, source)]}.

    Returns (market ids by ticker, outcome ids by leg ticker). Every leg carries
    an opening and a calibration price so the grade can be seen not to move them.
    """
    from sqlalchemy import update
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.models.models import FuturesMarket, FuturesOutcome, Sport

    maker = async_sessionmaker(engine, expire_on_commit=False)
    market_ids, outcome_ids = {}, {}
    async with maker() as session:
        sport = Sport(key="baseball_mlb", name="MLB")
        session.add(sport)
        await session.flush()
        for ext, legs in markets.items():
            market = FuturesMarket(
                source="kalshi", external_id=ext, sport_id=sport.id,
                name=ext, status="open",
            )
            session.add(market)
            await session.flush()
            market_ids[ext] = market.id
            for ticker, price, won, source in legs:
                leg = FuturesOutcome(
                    market_id=market.id, external_id=ticker, name=ticker,
                    current_probability=price, opening_probability=0.5,
                    calibration_probability=0.6, is_winner=won,
                    resolution_source=source,
                )
                session.add(leg)
                await session.flush()
                outcome_ids[ticker] = leg.id
        # The ORM default fills `is_winner=False`; the poll's ungraded rows are NULL.
        await session.execute(
            update(FuturesOutcome)
            .where(FuturesOutcome.resolution_source.is_(None))
            .values(is_winner=None)
        )
        await session.commit()
    return market_ids, outcome_ids


def _legs(sync, outcome_ids):
    """What a second connection sees: {ticker: (is_winner, source, price, opening, calibration)}."""
    from sqlalchemy import text

    with sync.connect() as conn:
        rows = conn.execute(text(
            "SELECT external_id, is_winner, resolution_source, current_probability, "
            "opening_probability, calibration_probability FROM futures_outcomes"
        )).all()
    return {
        r[0]: (r[1], r[2], float(r[3]), float(r[4]), float(r[5]))
        for r in rows if r[0] in outcome_ids
    }


def _market(sync, market_id):
    from sqlalchemy import text

    with sync.connect() as conn:
        return conn.execute(
            text("SELECT status, settled_at IS NOT NULL FROM futures_markets WHERE id = :id"),
            {"id": market_id},
        ).one()


def _snapshot_rows(sync):
    from sqlalchemy import text

    with sync.connect() as conn:
        return conn.execute(text("SELECT count(*) FROM futures_odds_snapshots")).scalar_one()


async def _until(predicate, timeout=2.0):
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not predicate():
        if loop.time() > deadline:
            return False
        await asyncio.sleep(0.02)
    return True


# ------------------------------------------------------------- the consumer ----


def _install_pg_sessions(monkeypatch, engine, open_rows):
    """Every UPDATE (and the flush's lock budget) runs on a real AsyncSession that
    commits when the consumer's block exits cleanly and rolls back otherwise —
    the task factory's contract. SELECTs are the slate, replayed."""
    from sqlalchemy import Update
    from sqlalchemy.ext.asyncio import AsyncSession

    import app.tasks.base as task_base
    from app.utils.repair_lock_budget import SET_LOCK_TIMEOUT_SQL
    from tests._kalshi_price_session import bind_sessions
    from tests.test_ws_open_contract_prices_9484 import _Result, _sql

    class _Session:
        def __init__(self, real):
            self._real = real

        @property
        def sync_session(self):
            return self._real.sync_session

        @property
        def info(self):
            return self._real.info

        async def execute(self, stmt, params=None):
            if stmt is SET_LOCK_TIMEOUT_SQL or isinstance(stmt, Update):
                if params is None:
                    return await self._real.execute(stmt)
                return await self._real.execute(stmt, params)
            if "futures_outcomes.is_winner IS NULL" in _sql(stmt):
                return _Result(list(open_rows))
            return _Result([])  # no linked slate, no bridge, no live re-read

    class _Ctx:
        async def __aenter__(self):
            self.real = AsyncSession(engine, expire_on_commit=False)
            return _Session(self.real)

        async def __aexit__(self, exc_type, *_exc):
            try:
                if exc_type is None:
                    await self.real.commit()
                else:
                    await self.real.rollback()
            finally:
                await self.real.close()
            return False

    monkeypatch.setattr(
        task_base, "get_task_session", bind_sessions(lambda *a, **kw: _Ctx())
    )


class _Publisher:
    """Records every market frame with what a SECOND connection saw as it went."""

    def __init__(self, sync, outcome_ids, market_ids):
        self._sync, self._outcomes, self._markets = sync, outcome_ids, market_ids
        self.frames = []

    async def publish(self, _channel, payload):
        frame = json.loads(payload)
        self.frames.append((
            frame,
            _legs(self._sync, self._outcomes),
            {ext: tuple(_market(self._sync, mid)) for ext, mid in self._markets.items()},
        ))
        return 0

    @property
    def connection_pool(self):
        from tests.test_ws_market_change_hooks_9484 import _PipelinedPublish

        return _PipelinedPublish(self)


def _refresher(publisher):
    from app.utils.market_quote_push import publish_committed_market_changes
    from tests.test_ws_open_contract_prices_9484 import _NoopRefresher

    class _Refresher(_NoopRefresher):
        async def publish_market_changes(self, session):
            return await publish_committed_market_changes(session, publisher)

    return _Refresher


def _hold_grades(monkeypatch, held, *, after=None):
    """Hold ``held``'s grade INSIDE its transaction (after the grader's two
    UPDATEs, before the consumer's block commits). ``after``: legs whose grade
    starts only once the held one has written."""
    from app.tasks import ws_open_contracts as oc

    graded = oc.grade_open_contract_leg
    entered, release = asyncio.Event(), asyncio.Event()

    async def grade(session, **kw):
        if kw["outcome_id"] in (after or ()):
            await entered.wait()
        result = await graded(session, **kw)
        if kw["outcome_id"] == held:
            entered.set()
            await release.wait()
        return result

    monkeypatch.setattr(oc, "grade_open_contract_leg", grade)
    return entered, release


async def _consume(monkeypatch, engine, *, frames, open_rows, publisher, refresh=1.5):
    import app.tasks.kalshi_ws as kalshi_task
    import app.tasks.live_blend_refresh as blend_mod
    import app.tasks.ws_admission as admission
    from tests.test_ws_open_contract_prices_9484 import _install_socket

    monkeypatch.setenv("KALSHI_API_KEY_ID", "test-key")
    monkeypatch.setenv("KALSHI_RSA_PRIVATE_KEY", "test-secret")
    monkeypatch.setattr(kalshi_task, "SUBSCRIPTION_REFRESH_SECONDS", refresh)
    monkeypatch.setattr(kalshi_task, "PRICE_FLUSH_SECONDS", 0.02)
    monkeypatch.setattr(admission, "ADMISSION_CHECK_SECONDS", 60.0)
    monkeypatch.setattr(admission, "ADMISSION_MIN_RECYCLE_SECONDS", 0)
    monkeypatch.setattr(blend_mod, "LiveBlendRefresher", _refresher(publisher))
    _install_socket(monkeypatch, {open_rows[0][0]: list(frames)})
    _install_pg_sessions(monkeypatch, engine, open_rows)
    return await asyncio.wait_for(kalshi_task._run_kalshi_ws_consumer(), timeout=10)


# ------------------------------------------------------------------ the ship ----


SHIP_MARKETS = {
    BOARD: [
        (SD20, 0.99, None, None), (SD21, 0.14, None, None),
        (CHC21, 0.04, None, None), (CHC20, 0.0, False, "api_settlement"),
    ],
    "KXNBAMVP-27": [(SGA, 0.30, None, None)],
}


async def _ship(monkeypatch, pg, *, prepared):
    from tests.test_ws_open_contract_prices_9484 import _settle, _tick
    from app.tasks import ws_open_contracts as oc

    engine, sync = pg
    market_ids, ids = await _seed(engine, SHIP_MARKETS)
    if not prepared:
        monkeypatch.setattr(oc, "prepared_shard_indexes", lambda _ids, _shards: set())
    entered, release = _hold_grades(monkeypatch, ids[SD21])
    publisher = _Publisher(sync, ids, market_ids)
    open_rows = [
        (t, market_ids[BOARD], ids[t]) for t in (CHC21, SD20, SD21)
    ] + [(SGA, market_ids["KXNBAMVP-27"], ids[SGA])]
    frames = [
        _settle(SD21, result="no"),
        _tick(SD21, bid="0.50", ask="0.52", price="0.51"),  # a late, live-looking quote
        _settle(CHC21, result="no"),
        _settle(SD20, result="yes"),
        _tick(SGA),  # 0.40 / 0.42 → 0.41
    ]
    job = asyncio.create_task(_consume(
        monkeypatch, engine, frames=frames, open_rows=open_rows, publisher=publisher,
    ))
    try:
        assert await _until(entered.is_set), "SD21's grade never started"
        sga_stored = await _until(
            lambda: _legs(sync, ids)[SGA][2] == pytest.approx(0.41),
            timeout=1.0 if prepared else 0.4,
        )
        during = _legs(sync, ids), tuple(_market(sync, market_ids[BOARD]))
    finally:
        release.set()
    stats = await job
    return dict(
        ids=ids, market_ids=market_ids, sga_stored_while_held=sga_stored,
        during=during, final=_legs(sync, ids),
        board=tuple(_market(sync, market_ids[BOARD])),
        snapshots=_snapshot_rows(sync), frames=publisher.frames, stats=stats,
    )


def _assert_final(run):
    ids, final = run["ids"], run["final"]
    # Each leg its own venue declaration; opening and calibration untouched.
    assert final[SD21] == (False, "api_settlement", 0.0, 0.5, 0.6)
    assert final[CHC21] == (False, "api_settlement", 0.0, 0.5, 0.6)
    assert final[SD20] == (True, "api_settlement", 1.0, 0.5, 0.6)
    assert final[CHC20] == (False, "api_settlement", 0.0, 0.5, 0.6)
    assert [t for t, row in final.items() if row[0]] == [SD20], "no sibling crowned"
    assert final[SGA] == (None, None, pytest.approx(0.41), 0.5, 0.6)
    assert run["board"] == ("resolved", True)
    assert run["snapshots"] == 0, "no history row is written by a grade"
    # SD21's 0.51 arrived after its grade and was refused at the UPDATE (#5411).
    assert run["stats"]["settled_declined"] >= 1
    assert run["stats"]["open_contract_settlements"] == 3
    assert run["stats"]["open_contract_markets_resolved"] == 1
    assert run["stats"]["errors"] == 0

    board_id = run["market_ids"][BOARD]
    board_frames = [(f, legs, m) for f, legs, m in run["frames"] if f["market_id"] == board_id]
    terminal = [x for x in board_frames if x[0].get("terminal")]
    assert len(terminal) == 1, "the board announced terminal exactly once"
    # Every frame went out after the row it names was committed.
    for frame, legs, markets in board_frames:
        if frame.get("terminal"):
            assert markets[BOARD] == ("resolved", True)
            assert legs[SD20][:2] == (True, "api_settlement")
        for oid in frame.get("outcome_ids") or []:
            ticker = next(t for t, i in ids.items() if i == oid)
            assert legs[ticker][1] == "api_settlement", (ticker, frame)
    return {
        "final": final, "board": run["board"],
        "board_frames": sorted(
            (bool(f.get("terminal")), tuple(f.get("outcome_ids") or ())) for f, _l, _m in board_frames
        ),
    }


async def test_the_ship(monkeypatch, pg):
    deferred = await _ship(monkeypatch, pg, prepared=True)

    # THE SHIP: SGA's quote was committed while SD21's grade transaction was open.
    assert deferred["sga_stored_while_held"] is True
    during, board_during = deferred["during"]
    assert during[SD21][:2] == (None, None), "SD21's grade was not yet committed"
    # The board waited behind its own settlement.
    assert during[SD20][:2] == (None, None) and during[CHC21][:2] == (None, None)
    assert board_during == ("open", False)
    deferred_end = _assert_final(deferred)

    # Same frames, admission refused: the pre-#10734 inline shape, on fresh tables.
    engine, sync = pg
    await _reset(engine)
    monkeypatch.undo()
    inline = await _ship(monkeypatch, pg, prepared=False)

    assert inline["sga_stored_while_held"] is False, "inline: the quote waits for the grade"
    assert _assert_final(inline) == deferred_end


async def _reset(engine):
    import app.models.models  # noqa: F401
    from app.services.database import Base

    wanted = [Base.metadata.tables[name] for name in TABLES]
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all, tables=wanted, checkfirst=True)
        await conn.run_sync(Base.metadata.create_all, tables=wanted)


# --------------------------------------------- the admission is load-bearing ----


SPLIT_MARKETS = {
    "KXSPLIT-26": [(SPLIT_X, 0.40, None, None), (SPLIT_Y, 0.60, None, None)],
    "KXNBAMVP-27": [(SGA, 0.30, None, None)],
}


async def _two_prefixes(monkeypatch, pg, *, force_prepared):
    from tests.test_ws_open_contract_prices_9484 import _settle
    from app.tasks import ws_open_contracts as oc

    engine, sync = pg
    market_ids, ids = await _seed(engine, SPLIT_MARKETS)
    if force_prepared:
        monkeypatch.setattr(
            oc, "prepared_shard_indexes", lambda _ids, shards: set(range(len(shards)))
        )
    entered, release = _hold_grades(monkeypatch, ids[SPLIT_X], after=(ids[SPLIT_Y],))
    publisher = _Publisher(sync, ids, market_ids)
    split = market_ids["KXSPLIT-26"]
    open_rows = [
        (SPLIT_X, split, ids[SPLIT_X]), (SPLIT_Y, split, ids[SPLIT_Y]),
        (SGA, market_ids["KXNBAMVP-27"], ids[SGA]),
    ]
    job = asyncio.create_task(_consume(
        monkeypatch, engine,
        frames=[_settle(SPLIT_X, result="no"), _settle(SPLIT_Y, result="yes")],
        open_rows=open_rows, publisher=publisher,
    ))
    try:
        assert await _until(entered.is_set)
        # Prepared: Y grades and commits against X's open transaction. Inline: it
        # cannot start, because the reader is still inside X's callback.
        y_graded_while_held = await _until(
            lambda: _legs(sync, ids)[SPLIT_Y][1] == "api_settlement",
            timeout=1.0 if force_prepared else 0.3,
        )
    finally:
        release.set()
    await job
    return y_graded_while_held, _legs(sync, ids), tuple(_market(sync, split))


async def test_two_prefixes_stay_inline(monkeypatch, pg):
    y_early, legs, board = await _two_prefixes(monkeypatch, pg, force_prepared=False)

    assert y_early is False
    assert legs[SPLIT_X][:3] == (False, "api_settlement", 0.0)
    assert legs[SPLIT_Y][:3] == (True, "api_settlement", 1.0)
    assert board == ("resolved", True)

    # STRAWMAN: the same market with its connection forced onto the dispatcher.
    engine, _sync = pg
    await _reset(engine)
    monkeypatch.undo()
    y_early, legs, board = await _two_prefixes(monkeypatch, pg, force_prepared=True)

    assert y_early is True
    assert legs[SPLIT_X][:2] == (False, "api_settlement")
    assert legs[SPLIT_Y][:2] == (True, "api_settlement")
    assert board == ("open", False), "both legs graded, neither saw the other: board stranded"
