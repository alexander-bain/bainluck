"""#10248 — a golf market's 24h column shows how far each contender moved today.

Specimen: Alfred Dunhill Links Championship - Winner (futures 62904927). The
chart showed Matthew Jordan rising from ~2% to 15% while every row's 24h column
was "-": DataGolf never wrote `probability_change_24h`, and the sweep's dated
bank (A8) only banks legs whose last per-write move clears the 2-point floor —
which a 90 s DataGolf poll almost never does.

Calibration decision D1–D5 (`10248-CALIBRATION-ELIGIBILITY-DECISION.md`):
the writers store the shared per-write delta (0 on an unchanged poll, NULL with
no previous price), `datagolf_model` is scale-identical, DataGolf markets get a
floor-free A8 arm that marks its bank, shared A8/A9 exclude them, and the reader
serves a stored 0 off a MARKED bank.

Everything here runs the real code on a real database, with no hand-built bank:
the ACTUAL DataGolf writers (both rails, external API and Redis faked), the
ACTUAL `update_max_movement` sweep, and the ACTUAL `/api/futures/{id}` route.
The four strawmen at the bottom each break one decision and must turn the
positive case red — that is what shows the positive case is not passing for a
reason this file did not intend.

Opt-in on `SEARCH_TEST_DATABASE_URL` like its neighbours; CI's `search-recall`
job runs it with the all-skipped detector.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #10248 DataGolf "
        "dated-movement gate (CI job: search-recall)"
    ),
)

EVENT_ID = "2026551"
EVENT_NAME = "Alfred Dunhill Links Championship"
JORDAN = 1001
# The rest of a winner field, so the board sums to 1.0 and the detail route's
# display normalisation leaves it alone (a squeezed board serves no 24h column
# at all, which would make every assertion below vacuous).
FIELD = {1002: 0.40, 1003: 0.25, 1004: 0.15, 1005: 0.05}


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


def _engine():
    from sqlalchemy.ext.asyncio import create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base

    return create_async_engine(DB_URL)


def _ago(hours: float) -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=hours)


def _ext(tour: str, market_type: str) -> str:
    return f"datagolf:{tour}:{EVENT_ID}:{market_type}"


async def _reset_and_seed(markets):
    """`markets`: list of dicts — tour, market_type, legs.

    Each leg: (dg_id, current_probability or None, [(hours_ago, prob, bookmaker)]).
    A leg with `current_probability` None and no observations is not created.
    Returns {(tour, market_type): market_id} and {(tour, market_type, dg_id): outcome_id}.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.models.models import FuturesMarket, FuturesOddsSnapshot, FuturesOutcome
    from app.services.database import Base

    engine = _engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    market_ids: dict = {}
    outcome_ids: dict = {}
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        for spec in markets:
            tour, market_type = spec["tour"], spec["market_type"]
            label = "Winner" if market_type == "win" else market_type
            market = FuturesMarket(
                source="datagolf",
                external_id=_ext(tour, market_type),
                name=f"{EVENT_NAME} - {label}",
                category="championship" if market_type == "win" else "placement",
                llm_sport_category="golf",
                status="open",
                mutually_exclusive=(market_type == "win"),
                commence_time=_ago(30),
                resolution_date=datetime.now(timezone.utc) + timedelta(days=2),
                market_metadata={"datagolf_event_id": EVENT_ID, "tour": tour},
            )
            session.add(market)
            await session.flush()
            market_ids[(tour, market_type)] = market.id
            for dg_id, current, observations in spec["legs"]:
                outcome = FuturesOutcome(
                    market_id=market.id,
                    external_id=f"dg_{dg_id}",
                    name=f"Player {dg_id}" if dg_id != JORDAN else "Matthew Jordan",
                    current_probability=current,
                    opening_probability=spec.get("opening", {}).get(dg_id, current),
                    last_updated=_ago(0.5),
                )
                session.add(outcome)
                await session.flush()
                outcome_ids[(tour, market_type, dg_id)] = outcome.id
                for hours_ago, prob, bookmaker, *rest in observations:
                    valid_until = rest[0] if rest else _ago(hours_ago)
                    session.add(
                        FuturesOddsSnapshot(
                            outcome_id=outcome.id,
                            bookmaker=bookmaker,
                            probability=prob,
                            captured_at=_ago(hours_ago),
                            valid_until=valid_until,
                            reading_count=1,
                        )
                    )
        await session.commit()
    await engine.dispose()
    return market_ids, outcome_ids


def _winner_field(jordan_obs, jordan_current=0.02, tour="pga", extra_markets=()):
    legs = [(JORDAN, jordan_current, jordan_obs)]
    legs += [(dg, p, [(19, p, "datagolf_model")]) for dg, p in FIELD.items()]
    return [{"tour": tour, "market_type": "win", "legs": legs}, *extra_markets]


class _Ctx:
    """A real session on the test database that commits on clean exit."""

    def __init__(self, on_session=None):
        self._on_session = on_session

    async def __aenter__(self):
        from sqlalchemy.ext.asyncio import async_sessionmaker

        self._engine = _engine()
        self._session = async_sessionmaker(self._engine, expire_on_commit=False)()
        if self._on_session:
            self._on_session(self._session)
        return self._session

    async def __aexit__(self, exc_type, *_exc):
        if exc_type is None:
            await self._session.commit()
        else:
            await self._session.rollback()
        await self._session.close()
        await self._engine.dispose()
        return False


class _FakeRedis:
    def __init__(self):
        self.store: dict = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None):
        self.store[key] = value

    def delete(self, key):
        self.store.pop(key, None)


def _players(prices: dict, field: str = "win"):
    from app.services.datagolf_api import DataGolfPlayer

    return [
        DataGolfPlayer(dg_id=dg, player_name=f"Player {dg}", **{field: p})
        for dg, p in prices.items()
    ]


def _tournament():
    from app.services.datagolf_api import DataGolfTournament

    now = datetime.now(timezone.utc)
    return DataGolfTournament(
        event_id=EVENT_ID,
        event_name=EVENT_NAME,
        course="St Andrews",
        start_date=(now - timedelta(days=1)).strftime("%Y-%m-%d"),
        end_date=(now + timedelta(days=2)).strftime("%Y-%m-%d"),
        status=None,
        tour="pga",
    )


class _FakeService:
    def __init__(self, players_by_tour):
        self._players = players_by_tour

    async def get_schedule(self, tour):
        return [_tournament()] if tour in self._players else []

    async def get_pre_tournament(self, tour):
        return list(self._players.get(tour, []))

    async def get_in_play_with_info(self, tour):
        players = list(self._players.get(tour, []))
        return players, ({"event_name": EVENT_NAME} if players else None)

    async def close(self):
        return None


def _write(monkeypatch, rail: str, prices: dict, *, tour: str = "pga", field: str = "win"):
    """Drive the REAL DataGolf writer for one rail against this database."""
    import app.services.datagolf_api as datagolf_api
    import app.tasks.datagolf as datagolf
    import app.tasks.redis_state as redis_state

    service = _FakeService({tour: _players(prices, field)})
    redis = _FakeRedis()
    monkeypatch.setattr(datagolf, "get_task_session", lambda: _Ctx())
    monkeypatch.setattr(datagolf_api, "DataGolfAPIService", lambda *a, **kw: service)
    monkeypatch.setattr(redis_state, "get_redis_client", lambda *a, **kw: redis)
    if rail == "pre":
        stats = asyncio.run(datagolf._poll_datagolf_markets())
        assert stats.get("inplay_price_writes_deferred", 0) == 0, stats
    else:
        stats = asyncio.run(datagolf._poll_datagolf_live())
    assert stats.get("snapshots_written", 0) >= 0, stats
    return stats


def _sweep(monkeypatch, rewrite=None):
    """Drive the REAL `update_max_movement`. `rewrite(sql) -> sql | None` is the
    strawman hook: None skips the statement, a string replaces it."""
    import app.tasks.base as base_mod
    import app.tasks.futures_movers_warm as warm_mod
    from app.tasks import update_max_movement

    def _hook(session):
        if rewrite is None:
            return
        from sqlalchemy import text

        real = session.execute

        class _Skipped:
            rowcount = 0

        async def _execute(stmt, *args, **kwargs):
            sql = str(stmt)
            new = rewrite(sql)
            if new is None:
                return _Skipped()
            if new != sql:
                stmt = text(new)
            return await real(stmt, *args, **kwargs)

        session.execute = _execute

    async def _no_warm(_session):
        return {"terminal": "skipped", "completed": 0}

    monkeypatch.setattr(base_mod, "get_task_session", lambda: _Ctx(_hook))
    monkeypatch.setattr(warm_mod, "warm_futures_movers", _no_warm)
    return update_max_movement.run()


async def _read_rows(market_ids, outcome_ids):
    from sqlalchemy import select

    from app.models.models import FuturesMarket, FuturesOutcome

    engine = _engine()
    try:
        async with engine.connect() as conn:
            deltas = {
                row.id: row.probability_change_24h
                for row in await conn.execute(
                    select(FuturesOutcome.id, FuturesOutcome.probability_change_24h)
                )
            }
            metadata = {
                row.id: row.market_metadata
                for row in await conn.execute(
                    select(FuturesMarket.id, FuturesMarket.market_metadata)
                )
            }
    finally:
        await engine.dispose()
    return deltas, metadata


def _rows(market_ids, outcome_ids):
    return asyncio.run(_read_rows(market_ids, outcome_ids))


def _served(monkeypatch, market_id) -> dict:
    """GET /api/futures/{id} through the real app → {outcome_id: change_24h}."""
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession

    import app.routes.futures as fr
    from app.dependencies.auth import get_optional_user
    from app.main import app
    from app.services.database import get_db, get_db_rw

    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")

    async def _no_sources(_db, _market_id, _outcome_ids):
        return [], []

    monkeypatch.setattr(fr, "_load_market_sources", _no_sources)

    async def _go():
        engine = _engine()

        async def _get_db():
            async with AsyncSession(engine, expire_on_commit=False) as session:
                yield session

        async def _anon():
            return None

        app.dependency_overrides[get_db] = _get_db
        app.dependency_overrides[get_db_rw] = _get_db
        app.dependency_overrides[get_optional_user] = _anon
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                r = await client.get(f"/api/futures/{market_id}")
                assert r.status_code == 200, r.text
                return r.json()
        finally:
            app.dependency_overrides.clear()
            await engine.dispose()

    body = asyncio.run(_go())
    return {o["id"]: o.get("probability_change_24h") for o in body["outcomes"]}


def _priced(jordan: float) -> dict:
    return {JORDAN: jordan, **FIELD}


def _drive_specimen(monkeypatch, rail, *, rewrite=None):
    """The disposition's specimen: 0.02 observed 19 h ago → 0.15 → 0.15."""
    market_ids, outcome_ids = asyncio.run(
        _reset_and_seed(_winner_field([(19, 0.02, "datagolf_model")]))
    )
    mid = market_ids[("pga", "win")]
    jordan = outcome_ids[("pga", "win", JORDAN)]

    _write(monkeypatch, rail, _priced(0.15))
    deltas, _ = _rows(market_ids, outcome_ids)
    first = deltas[jordan]

    _write(monkeypatch, rail, _priced(0.15))
    deltas, _ = _rows(market_ids, outcome_ids)
    second = deltas[jordan]

    result = _sweep(monkeypatch, rewrite=rewrite)
    _, metadata = _rows(market_ids, outcome_ids)
    served = _served(monkeypatch, mid)
    return {
        "first": first,
        "second": second,
        "result": result,
        "metadata": metadata[mid] or {},
        "served": served[jordan],
        "jordan": jordan,
    }


# ---------------------------------------------------------------------------
# The positive case, on both rails
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rail", ["pre", "live"])
def test_the_specimen_serves_its_dated_day_move(monkeypatch, rail) -> None:
    from app.utils.futures_market_snapshot import (
        DATED_BASIS_ELIGIBILITY_METADATA_KEY,
        DATED_BASIS_METADATA_KEY,
        DATED_BASIS_PRICED_LEG,
    )

    run = _drive_specimen(monkeypatch, rail)

    assert run["first"] is not None and abs(float(run["first"]) - 0.13) < 1e-6, (
        f"{rail}: the first write must store the per-write delta 0.13, got {run['first']}"
    )
    assert run["second"] is not None and float(run["second"]) == 0.0, (
        f"{rail}: an unchanged poll stores 0 (D1), not NULL; got {run['second']}"
    )
    bank = run["metadata"].get(DATED_BASIS_METADATA_KEY) or {}
    cell = bank.get(str(run["jordan"]))
    assert cell is not None and abs(cell[0] - 0.02) < 1e-9, (
        f"{rail}: A8-DG must bank the 0.02 observed 19 h ago and A9 must leave it; "
        f"metadata={run['metadata']} result={run['result']}"
    )
    assert run["metadata"].get(DATED_BASIS_ELIGIBILITY_METADATA_KEY) == DATED_BASIS_PRICED_LEG
    assert run["served"] is not None and abs(run["served"] - 0.13) < 1e-6, (
        f"{rail}: the served ladder must show +0.13 (0.15 now − 0.02 at 19 h); got {run['served']}"
    )


def test_a_tiny_poll_keeps_the_bank_and_moves_the_answer(monkeypatch) -> None:
    """A 0.05-point poll is far under the floor; the shared A9 would delete the
    bank on it. A9-DG keeps it, and the served move follows the new price."""
    run = _drive_specimen(monkeypatch, "live")
    assert run["served"] is not None

    _write(monkeypatch, "live", _priced(0.1505))
    result = _sweep(monkeypatch)
    market_ids, _ = asyncio.run(_ids())
    served = _served(monkeypatch, market_ids[("pga", "win")])

    assert served[run["jordan"]] is not None and abs(served[run["jordan"]] - 0.1305) < 1e-6, (
        f"a tiny poll lost the dated move: {served[run['jordan']]} result={result}"
    )


async def _ids():
    from sqlalchemy import select

    from app.models.models import FuturesMarket, FuturesOutcome

    engine = _engine()
    try:
        async with engine.connect() as conn:
            markets = {}
            for row in await conn.execute(
                select(FuturesMarket.id, FuturesMarket.external_id)
            ):
                _, tour, _, market_type = row.external_id.split(":")
                markets[(tour, market_type)] = row.id
            outcomes = {
                (row.market_id, row.external_id): row.id
                for row in await conn.execute(
                    select(FuturesOutcome.id, FuturesOutcome.market_id, FuturesOutcome.external_id)
                )
            }
    finally:
        await engine.dispose()
    return markets, outcomes


def test_a_flat_leg_beside_a_mover_serves_its_measured_flat_day(monkeypatch) -> None:
    """Swept after ONE poll: Jordan's 0.13 clears the floor, so the market is in
    the SHARED arm's scope too. Without its `source` exclusion, A8 would replace
    the DataGolf bank with only the legs at the floor, and every flat leg beside
    the mover would lose its cell. With it, a flat leg serves 0.0 — a day the
    bank measured as flat — and the mover serves +0.13."""
    market_ids, outcome_ids = asyncio.run(
        _reset_and_seed(_winner_field([(19, 0.02, "datagolf_model")]))
    )
    mid = market_ids[("pga", "win")]
    _write(monkeypatch, "live", _priced(0.15))
    _sweep(monkeypatch)
    served = _served(monkeypatch, mid)

    mover = served[outcome_ids[("pga", "win", JORDAN)]]
    flat = served[outcome_ids[("pga", "win", 1002)]]
    assert mover is not None and abs(mover - 0.13) < 1e-6, mover
    assert flat == 0.0, f"a measured flat day serves 0.0, got {flat}"


def test_a_previous_price_of_zero_is_a_price(monkeypatch) -> None:
    """0.0 is a real golf price (a graded miss). The first write after it is a
    +0.15 move, not "no previous price"."""
    asyncio.run(_reset_and_seed(_winner_field([(19, 0.0, "datagolf_model")], jordan_current=0.0)))
    _write(monkeypatch, "live", _priced(0.15))
    _sweep(monkeypatch)
    markets, outcomes = asyncio.run(_ids())
    mid = markets[("pga", "win")]
    jordan = outcomes[(mid, f"dg_{JORDAN}")]
    served = _served(monkeypatch, mid)
    assert served[jordan] is not None and abs(served[jordan] - 0.15) < 1e-6, served[jordan]


def test_each_market_and_tour_dates_its_own_legs(monkeypatch) -> None:
    """The same player in winner and top-5, and the same dg_id on another tour,
    each get their own cell from their own history — never a sibling's."""
    top5 = {
        "tour": "pga",
        "market_type": "top_5",
        "legs": [(JORDAN, 0.30, [(18, 0.30, "datagolf_model")])],
    }
    euro = {
        "tour": "euro",
        "market_type": "win",
        "legs": [(JORDAN, 0.60, [(20, 0.60, "datagolf_model")])],
    }
    market_ids, outcome_ids = asyncio.run(
        _reset_and_seed(_winner_field([(19, 0.02, "datagolf_model")], extra_markets=(top5, euro)))
    )
    _write(monkeypatch, "live", _priced(0.15))
    _write(monkeypatch, "live", {JORDAN: 0.45}, field="top_5")
    _write(monkeypatch, "live", {JORDAN: 0.55}, tour="euro")
    _write(monkeypatch, "live", _priced(0.15))
    _write(monkeypatch, "live", {JORDAN: 0.45}, field="top_5")
    _write(monkeypatch, "live", {JORDAN: 0.55}, tour="euro")
    _sweep(monkeypatch)

    win = _served(monkeypatch, market_ids[("pga", "win")])[outcome_ids[("pga", "win", JORDAN)]]
    t5 = _served(monkeypatch, market_ids[("pga", "top_5")])[outcome_ids[("pga", "top_5", JORDAN)]]
    eu = _served(monkeypatch, market_ids[("euro", "win")])[outcome_ids[("euro", "win", JORDAN)]]
    assert win is not None and abs(win - 0.13) < 1e-6, win
    assert t5 is not None and abs(t5 - 0.15) < 1e-6, t5
    assert eu is not None and abs(eu - (-0.05)) < 1e-6, eu

    _, metadata = _rows(market_ids, outcome_ids)
    from app.utils.futures_market_snapshot import DATED_BASIS_METADATA_KEY

    for key, mid in market_ids.items():
        own = {str(oid) for (t, mt, _), oid in outcome_ids.items() if (t, mt) == key}
        bank = (metadata[mid] or {}).get(DATED_BASIS_METADATA_KEY) or {}
        assert set(bank) <= own, f"{key} banked a sibling's leg: {bank} vs own {own}"


# ---------------------------------------------------------------------------
# Refusals — each serves None, never 0
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "label,observations,opening",
    [
        ("basis 11 h old", [(11, 0.02, "datagolf_model")], None),
        ("basis 25 h old", [(25, 0.02, "datagolf_model")], None),
        (
            "second bookmaker in the window",
            [(19, 0.02, "datagolf_model"), (15, 0.03, "kalshi")],
            None,
        ),
        # A pre-window snapshot whose `valid_until` reaches into the window does
        # not date the old price, and an opening price is not an observation.
        ("opening only", [(30, 0.02, "datagolf_model", _ago(1))], 0.02),
    ],
)
def test_a_day_nobody_observed_is_not_served(monkeypatch, label, observations, opening) -> None:
    extra = {"opening": {JORDAN: opening}} if opening is not None else {}
    field = _winner_field(observations)
    field[0].update(extra)
    asyncio.run(_reset_and_seed(field))
    _write(monkeypatch, "live", _priced(0.15))
    _write(monkeypatch, "live", _priced(0.15))
    _sweep(monkeypatch)
    markets, outcomes = asyncio.run(_ids())
    mid = markets[("pga", "win")]
    jordan = outcomes[(mid, f"dg_{JORDAN}")]
    served = _served(monkeypatch, mid)[jordan]
    assert served is None, f"{label}: served {served}; a refusal is None, never a number"
    # The producer's bar, not only the reader's: the reader re-checks the age
    # window itself, so a bank that admitted an 11 h basis would still serve
    # None and this case alone could not see it.
    from app.utils.futures_market_snapshot import DATED_BASIS_METADATA_KEY

    _, metadata = _rows(markets, outcomes)
    bank = (metadata[mid] or {}).get(DATED_BASIS_METADATA_KEY) or {}
    assert str(jordan) not in bank, f"{label}: A8-DG banked {bank.get(str(jordan))}"


def test_a_new_leg_is_not_served(monkeypatch) -> None:
    asyncio.run(_reset_and_seed(_winner_field([(19, 0.02, "datagolf_model")])))
    newcomer = 1099
    _write(monkeypatch, "live", {**_priced(0.15), newcomer: 0.01})
    _write(monkeypatch, "live", {**_priced(0.15), newcomer: 0.01})
    _sweep(monkeypatch)
    markets, outcomes = asyncio.run(_ids())
    mid = markets[("pga", "win")]
    oid = outcomes[(mid, f"dg_{newcomer}")]
    deltas, _ = _rows(markets, outcomes)
    served = _served(monkeypatch, mid)
    assert served[oid] is None, served[oid]
    # Its second poll has a previous price, so it stores 0 — but nothing it
    # was ever observed at is 12 h old, so nothing may date its day.
    assert deltas[oid] is not None and float(deltas[oid]) == 0.0


# ---------------------------------------------------------------------------
# Strawmen — each breaks one decision and must turn the positive case red
# ---------------------------------------------------------------------------


def _mark_key() -> str:
    from app.utils.futures_market_snapshot import DATED_BASIS_ELIGIBILITY_METADATA_KEY

    return DATED_BASIS_ELIGIBILITY_METADATA_KEY


def test_strawman_shared_arm_only_goes_dark(monkeypatch) -> None:
    """Without A8-DG / A9-DG the shared arm's floor leaves the leg unbanked."""
    run = _drive_specimen(
        monkeypatch, "live", rewrite=lambda sql: None if _mark_key() in sql else sql
    )
    assert run["served"] is None, run


def test_strawman_a9_without_the_exclusion_deletes_the_bank(monkeypatch) -> None:
    line = "AND fm.source IS DISTINCT FROM 'datagolf'"

    def _rewrite(sql):
        if "NOT EXISTS" in sql and "abs(fo.probability_change_24h) >= :floor" in sql:
            assert line in sql, "A9's exclusion is gone — the strawman would be vacuous"
            return sql.replace(line, "")
        return sql

    run = _drive_specimen(monkeypatch, "live", rewrite=_rewrite)
    assert run["served"] is None, run


def test_strawman_reader_without_the_mark_refuses_zero(monkeypatch) -> None:
    import app.utils.futures_market_snapshot as fms

    monkeypatch.setattr(fms, "dated_basis_admits_zero", lambda _market: False)
    run = _drive_specimen(monkeypatch, "live")
    assert run["second"] is not None and float(run["second"]) == 0.0
    assert run["served"] is None, run


def test_strawman_writer_treating_zero_as_absent_loses_the_move(monkeypatch) -> None:
    import app.tasks.datagolf as datagolf

    def _falsy(previous, prob):  # the `if old_prob` idiom from tasks/futures.py
        return prob - float(previous) if previous else None

    monkeypatch.setattr(datagolf, "_per_write_change", _falsy)
    asyncio.run(_reset_and_seed(_winner_field([(19, 0.0, "datagolf_model")], jordan_current=0.0)))
    _write(monkeypatch, "live", _priced(0.15))
    _sweep(monkeypatch)
    markets, outcomes = asyncio.run(_ids())
    mid = markets[("pga", "win")]
    served = _served(monkeypatch, mid)[outcomes[(mid, f"dg_{JORDAN}")]]
    assert served is None, served
