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
            source = spec.get("source", "datagolf")
            market = FuturesMarket(
                source=source,
                market_tier=spec.get("market_tier"),
                external_id=(
                    _ext(tour, market_type)
                    if source == "datagolf"
                    else f"{source}:{tour}:{EVENT_ID}:{market_type}"
                ),
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
                    probability_change_24h=spec.get("deltas", {}).get(dg_id),
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


def _write(
    monkeypatch, rail: str, prices: dict, *, tour: str = "pga", field: str = "win",
    beat_owns: bool = False,
):
    """Drive the REAL DataGolf writer for one rail against this database.

    `beat_owns` publishes the in-play beat's ownership of this event, which is
    what stands the pre-tournament rail's price writes down (#7935/#7958)."""
    import app.services.datagolf_api as datagolf_api
    import app.tasks.datagolf as datagolf
    import app.tasks.redis_state as redis_state

    service = _FakeService({tour: _players(prices, field)})
    redis = _FakeRedis()
    if beat_owns:
        redis.store[f"{datagolf.INPLAY_OWNER_KEY_PREFIX}:{tour}"] = EVENT_ID.encode()
    monkeypatch.setattr(datagolf, "get_task_session", lambda: _Ctx())
    monkeypatch.setattr(datagolf_api, "DataGolfAPIService", lambda *a, **kw: service)
    monkeypatch.setattr(redis_state, "get_redis_client", lambda *a, **kw: redis)
    if rail == "pre":
        stats = asyncio.run(datagolf._poll_datagolf_markets())
        if not beat_owns:
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

    # S1: the seed carries no bank and no delta — everything after is earned.
    from app.utils.futures_market_snapshot import DATED_BASIS_METADATA_KEY

    deltas, metadata = _rows(market_ids, outcome_ids)
    assert deltas[jordan] is None
    assert DATED_BASIS_METADATA_KEY not in (metadata[mid] or {})

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
        # R4: a second bookmaker in the window (`sources != 1`).
        (
            "second bookmaker in the window",
            [(19, 0.02, "datagolf_model"), (15, 0.03, "kalshi")],
            None,
        ),
        # P6 / R4b: a foreign-scale (sportsbook) row on the leg refuses too.
        (
            "foreign-scale row in the window",
            [(19, 0.02, "datagolf_model"), (16, 0.04, "draftkings")],
            None,
        ),
        # R5: an opening price is not a dated observation.
        ("opening only", [], 0.02),
        # R6: a pre-window row whose `valid_until` was stretched by dedup to
        # inside the window does not date the old price.
        ("pre-window row, valid_until stretched", [(30, 0.02, "datagolf_model", _ago(2))], None),
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


# ---------------------------------------------------------------------------
# More refusals (R7–R11), persistence (P1–P3, P5) — the case map's ids
# ---------------------------------------------------------------------------


async def _exec(sql: str, **params):
    from sqlalchemy import text

    engine = _engine()
    try:
        async with engine.begin() as conn:
            await conn.execute(text(sql), params)
    finally:
        await engine.dispose()


def _kalshi_market(deltas: dict, legs) -> dict:
    return {
        "tour": "pga", "market_type": "kwin", "source": "kalshi",
        "deltas": deltas, "legs": legs,
    }


def _jordan_served(monkeypatch) -> float | None:
    markets, outcomes = asyncio.run(_ids())
    mid = markets[("pga", "win")]
    return _served(monkeypatch, mid)[outcomes[(mid, f"dg_{JORDAN}")]]


SHARED_A8_MARK = (
    "jsonb_build_object('dated_movement_basis', bank.payload)",
    "jsonb_build_object('dated_movement_basis', bank.payload, "
    "'dated_movement_basis_eligibility', 'priced_leg')",
)


def _r7(monkeypatch, rewrite=None):
    """A Kalshi leg banked by the SHARED arm (its 0.05 cleared the floor), then
    an unchanged Kalshi poll stores 0 before the next sweep. The direct UPDATE
    stands in only for that stored value."""
    market_ids, outcome_ids = asyncio.run(
        _reset_and_seed([
            _kalshi_market(
                {2001: 0.05},
                [(2001, 0.30, [(19, 0.25, "kalshi"), (1, 0.30, "kalshi")])],
            )
        ])
    )
    mid = market_ids[("pga", "kwin")]
    oid = outcome_ids[("pga", "kwin", 2001)]
    _sweep(monkeypatch, rewrite=rewrite)
    asyncio.run(_exec(
        "UPDATE futures_outcomes SET probability_change_24h = 0 WHERE id = :id", id=oid
    ))
    _, metadata = _rows(market_ids, outcome_ids)
    return _served(monkeypatch, mid)[oid], metadata[mid] or {}


def test_r7_a_shared_bank_keeps_the_zero_refusal(monkeypatch) -> None:
    from app.utils.futures_market_snapshot import (
        DATED_BASIS_ELIGIBILITY_METADATA_KEY,
        DATED_BASIS_METADATA_KEY,
    )

    served, metadata = _r7(monkeypatch)
    assert DATED_BASIS_METADATA_KEY in metadata, "the shared arm must have banked the leg"
    assert DATED_BASIS_ELIGIBILITY_METADATA_KEY not in metadata
    assert served is None, f"a non-DataGolf stored 0 must still refuse; got {served}"


def test_strawman_w5_a_mark_on_a_shared_bank_serves_a_zero(monkeypatch) -> None:
    def _rewrite(sql):
        if SHARED_A8_MARK[0] in sql:
            return sql.replace(*SHARED_A8_MARK)
        return sql

    served, _ = _r7(monkeypatch, rewrite=_rewrite)
    assert served is not None and abs(served - 0.05) < 1e-6, served


def _bank_then_starve(monkeypatch, rewrite=None):
    """Bank the specimen, then delete its old observation so nothing qualifies:
    the market stays in A8-DG's scope with an EMPTY payload."""
    from app.utils.futures_market_snapshot import (
        DATED_BASIS_ELIGIBILITY_METADATA_KEY,
        DATED_BASIS_METADATA_KEY,
    )

    run = _drive_specimen(monkeypatch, "live")
    assert run["served"] is not None
    asyncio.run(_exec(
        "DELETE FROM futures_odds_snapshots WHERE captured_at < now() - interval '6 hours'"
    ))
    _sweep(monkeypatch, rewrite=rewrite)
    markets, outcomes = asyncio.run(_ids())
    _, metadata = _rows(markets, outcomes)
    md = metadata[markets[("pga", "win")]] or {}
    return DATED_BASIS_METADATA_KEY in md, DATED_BASIS_ELIGIBILITY_METADATA_KEY in md


def test_an_emptied_datagolf_bank_takes_its_mark_with_it(monkeypatch) -> None:
    bank, mark = _bank_then_starve(monkeypatch)
    assert not bank and not mark, (bank, mark)


def test_strawman_w5_a_mark_left_behind_by_an_emptied_bank(monkeypatch) -> None:
    from app.utils.futures_market_snapshot import DATED_BASIS_ELIGIBILITY_METADATA_KEY

    drop = f"- CAST('{DATED_BASIS_ELIGIBILITY_METADATA_KEY}' AS text)"

    def _rewrite(sql):
        if "jsonb_object_agg" in sql and DATED_BASIS_ELIGIBILITY_METADATA_KEY in sql:
            assert drop in sql
            return sql.replace(drop, "", 1)
        return sql

    bank, mark = _bank_then_starve(monkeypatch, rewrite=_rewrite)
    assert not bank and mark, (bank, mark)


def test_r8_a_revived_leg_is_not_served(monkeypatch) -> None:
    asyncio.run(_reset_and_seed(
        _winner_field([(19, 0.02, "datagolf_model")], jordan_current=None)
    ))
    _write(monkeypatch, "live", _priced(0.15))
    markets, outcomes = asyncio.run(_ids())
    mid = markets[("pga", "win")]
    jordan = outcomes[(mid, f"dg_{JORDAN}")]
    deltas, _ = _rows(markets, outcomes)
    assert deltas[jordan] is None, f"a revival write has no previous price; stored {deltas[jordan]}"
    _sweep(monkeypatch)
    assert _jordan_served(monkeypatch) is None


def test_r9_the_deferred_pre_tournament_rail_writes_no_delta(monkeypatch) -> None:
    market_ids, outcome_ids = asyncio.run(
        _reset_and_seed(_winner_field([(19, 0.02, "datagolf_model")]))
    )
    stats = _write(monkeypatch, "pre", _priced(0.15), beat_owns=True)
    assert stats.get("inplay_price_writes_deferred", 0) > 0, stats
    deltas, _ = _rows(market_ids, outcome_ids)
    assert deltas[outcome_ids[("pga", "win", JORDAN)]] is None


def test_r10_a_stale_leg_keeps_a_null_delta(monkeypatch) -> None:
    field = _winner_field([(19, 0.02, "datagolf_model")])
    field[0]["legs"].append((1006, 0.05, [(19, 0.05, "datagolf_model")]))
    field[0]["deltas"] = {1006: 0.05}
    market_ids, outcome_ids = asyncio.run(_reset_and_seed(field))
    _write(monkeypatch, "live", _priced(0.15))  # 1006 is not in the board
    deltas, _ = _rows(market_ids, outcome_ids)
    assert deltas[outcome_ids[("pga", "win", 1006)]] is None


def test_r11_a_market_that_leaves_open_loses_its_bank(monkeypatch) -> None:
    from app.utils.futures_market_snapshot import (
        DATED_BASIS_ELIGIBILITY_METADATA_KEY,
        DATED_BASIS_METADATA_KEY,
    )

    run = _drive_specimen(monkeypatch, "live")
    assert run["served"] is not None
    asyncio.run(_exec("UPDATE futures_markets SET status = 'resolved'"))
    result = _sweep(monkeypatch)
    markets, outcomes = asyncio.run(_ids())
    _, metadata = _rows(markets, outcomes)
    md = metadata[markets[("pga", "win")]] or {}
    assert DATED_BASIS_METADATA_KEY not in md and DATED_BASIS_ELIGIBILITY_METADATA_KEY not in md
    assert result["dated_basis_unbanked_datagolf"] == 1, result


def test_p1_successive_tiny_polls_keep_the_bank(monkeypatch) -> None:
    run = _drive_specimen(monkeypatch, "live")
    assert run["served"] is not None
    for price, expected in ((0.151, 0.131), (0.1505, 0.1305)):
        _write(monkeypatch, "live", _priced(price))
        _sweep(monkeypatch)
        served = _jordan_served(monkeypatch)
        assert served is not None and abs(served - expected) < 1e-6, (price, served)


def test_p2_an_overnight_of_unchanged_polls_keeps_the_answer(monkeypatch) -> None:
    run = _drive_specimen(monkeypatch, "live")
    assert run["served"] is not None
    for _ in range(10):
        _write(monkeypatch, "live", _priced(0.15))
        _sweep(monkeypatch)
    served = _jordan_served(monkeypatch)
    assert served is not None and abs(served - 0.13) < 1e-6, served


def test_p3_prices_of_zero_and_one_are_previous_prices(monkeypatch) -> None:
    cut = {
        "tour": "pga", "market_type": "make_cut",
        "legs": [
            (3001, 0.0, [(19, 0.0, "datagolf_model")]),
            (3002, 1.0, [(19, 1.0, "datagolf_model")]),
        ],
    }
    market_ids, outcome_ids = asyncio.run(_reset_and_seed([cut]))
    _write(monkeypatch, "live", {3001: 0.03, 3002: 0.97}, field="make_cut")
    deltas, _ = _rows(market_ids, outcome_ids)
    assert abs(float(deltas[outcome_ids[("pga", "make_cut", 3001)]]) - 0.03) < 1e-6
    assert abs(float(deltas[outcome_ids[("pga", "make_cut", 3002)]]) + 0.03) < 1e-6


def test_p5_a_kalshi_market_in_the_same_sweep_keeps_the_shared_floor(monkeypatch) -> None:
    from app.utils.futures_market_snapshot import (
        DATED_BASIS_ELIGIBILITY_METADATA_KEY,
        DATED_BASIS_METADATA_KEY,
    )

    kalshi = _kalshi_market(
        {2001: 0.05, 2002: 0.01},
        [
            (2001, 0.30, [(19, 0.25, "kalshi"), (1, 0.30, "kalshi")]),
            (2002, 0.11, [(19, 0.10, "kalshi"), (1, 0.11, "kalshi")]),
        ],
    )
    market_ids, outcome_ids = asyncio.run(
        _reset_and_seed(_winner_field([(19, 0.02, "datagolf_model")], extra_markets=(kalshi,)))
    )
    _write(monkeypatch, "live", _priced(0.15))
    _write(monkeypatch, "live", _priced(0.15))
    _sweep(monkeypatch)
    _, metadata = _rows(market_ids, outcome_ids)
    k = metadata[market_ids[("pga", "kwin")]] or {}
    dg = metadata[market_ids[("pga", "win")]] or {}
    assert set(k.get(DATED_BASIS_METADATA_KEY) or {}) == {str(outcome_ids[("pga", "kwin", 2001)])}
    assert DATED_BASIS_ELIGIBILITY_METADATA_KEY not in k
    assert str(outcome_ids[("pga", "win", JORDAN)]) in (dg.get(DATED_BASIS_METADATA_KEY) or {})
    assert dg.get(DATED_BASIS_ELIGIBILITY_METADATA_KEY) == "priced_leg"


# ---------------------------------------------------------------------------
# D5 — the three root-approved SERVES sites, through their real code
# ---------------------------------------------------------------------------


async def _digest():
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.tasks.daily_digest import build_digest_content

    engine = _engine()
    try:
        async with AsyncSession(engine) as session:
            return await build_digest_content(session)
    finally:
        await engine.dispose()


def _market_moves(monkeypatch) -> list[dict]:
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.main import app
    from app.services import get_db

    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")

    async def _go():
        engine = _engine()

        async def _get_db():
            async with AsyncSession(engine, expire_on_commit=False) as session:
                yield session

        app.dependency_overrides[get_db] = _get_db
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                r = await client.get("/api/market-moves", params={"limit": 50})
                assert r.status_code == 200, r.text
                return r.json()["items"]
        finally:
            app.dependency_overrides.clear()
            await engine.dispose()

    return [i for i in asyncio.run(_go()) if i.get("type") == "futures_mover"]


def test_d5a_digest_and_market_moves_state_the_dated_move(monkeypatch) -> None:
    field = _winner_field([(19, 0.02, "datagolf_model")])
    field[0]["market_tier"] = 1
    asyncio.run(_reset_and_seed(field))
    _write(monkeypatch, "live", _priced(0.15))
    _write(monkeypatch, "live", _priced(0.15))  # stored 0
    _sweep(monkeypatch)

    digest = asyncio.run(_digest())
    jordan = [m for m in digest["movers"] if m["outcome"] == "Matthew Jordan"]
    assert jordan and abs(jordan[0]["change"] - 0.13) < 1e-6, digest["movers"]

    moves = [i for i in _market_moves(monkeypatch) if i["outcome_name"] == "Matthew Jordan"]
    assert moves and abs(moves[0]["change_24h"] - 0.13) < 1e-6, moves


def test_d5b_d5c_an_undated_poll_delta_is_not_served_but_kalshi_is_unchanged(monkeypatch) -> None:
    """A DataGolf leg with a stored 0.05 and nothing banked is not a mover on
    either surface; the same stored 0.05 on a Kalshi market is served as before."""
    dg = {
        "tour": "pga", "market_type": "win", "market_tier": 1,
        "deltas": {JORDAN: 0.05},
        "legs": [(JORDAN, 0.15, [(1, 0.15, "datagolf_model")])],
    }
    kalshi = _kalshi_market({2001: 0.05}, [(2001, 0.15, [(1, 0.15, "kalshi")])])
    kalshi["market_tier"] = 1
    asyncio.run(_reset_and_seed([dg, kalshi]))

    digest = asyncio.run(_digest())
    names = {m["outcome"]: m["change"] for m in digest["movers"]}
    assert "Matthew Jordan" not in names, digest["movers"]
    assert abs(names["Player 2001"] - 0.05) < 1e-6, digest["movers"]

    moves = {i["outcome_name"]: i["change_24h"] for i in _market_moves(monkeypatch)}
    assert "Matthew Jordan" not in moves, moves
    assert abs(moves["Player 2001"] - 0.05) < 1e-6, moves


def _push(monkeypatch, seed):
    """Run the REAL `_send_big_move_alerts` with FCM captured, one pinned user."""
    import app.tasks.base as base_mod
    import app.tasks.push_notifications as push

    market_ids, outcome_ids = asyncio.run(_reset_and_seed(seed))

    async def _pin_everything():
        from sqlalchemy.ext.asyncio import async_sessionmaker

        from app.models.models import DeviceToken, User, UserPin

        engine = _engine()
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            user = User()
            session.add(user)
            await session.flush()
            for mid in market_ids.values():
                session.add(UserPin(user_id=user.id, pin_type="future", target_id=mid))
            session.add(DeviceToken(
                device_token="tok-10248", platform="ios", user_id=user.id, is_active=True,
            ))
            await session.commit()
        await engine.dispose()

    asyncio.run(_pin_everything())
    return market_ids, outcome_ids, base_mod, push


def _send(monkeypatch, base_mod, push) -> tuple[dict, list[str]]:
    bodies: list[str] = []
    monkeypatch.setattr(base_mod, "get_task_session", lambda: _Ctx())
    monkeypatch.setattr(
        push, "_send_fcm_message", lambda token, title, body, data=None: bodies.append(body) or "id"
    )
    return asyncio.run(push._send_big_move_alerts()), bodies


def test_d5a_the_big_move_push_states_the_dated_move(monkeypatch) -> None:
    """Raw per-poll delta 0.20 (0.10 → 0.30) selects the alert; the body must
    say the dated day move, 0.30 − 0.02 observed 19 h ago = 28.0pp."""
    seed = _winner_field([(19, 0.02, "datagolf_model"), (2, 0.10, "datagolf_model")],
                         jordan_current=0.10)
    _, outcome_ids, base_mod, push = _push(monkeypatch, seed)
    _write(monkeypatch, "live", {JORDAN: 0.30, **FIELD})
    _sweep(monkeypatch)
    result, bodies = _send(monkeypatch, base_mod, push)
    assert any("up 28.0pp" in b for b in bodies), (result, bodies)
    assert not any("20.0pp" in b for b in bodies), bodies


def test_d5b_d5c_an_undated_big_poll_is_not_pushed_but_kalshi_is(monkeypatch) -> None:
    dg = {
        "tour": "pga", "market_type": "win",
        "deltas": {JORDAN: 0.20},
        "legs": [(JORDAN, 0.30, [(1, 0.30, "datagolf_model")])],
    }
    kalshi = _kalshi_market({2001: 0.20}, [(2001, 0.30, [(1, 0.30, "kalshi")])])
    _, _, base_mod, push = _push(monkeypatch, [dg, kalshi])
    result, bodies = _send(monkeypatch, base_mod, push)
    # One user pinned both markets: the alert names the Kalshi move and never
    # the DataGolf leg, which had no dated move to state.
    assert len(bodies) == 1 and "Player 2001 is up 20.0pp" in bodies[0], (result, bodies)
    assert not any("Matthew Jordan" in b for b in bodies), bodies


def test_d5a_a_big_poll_whose_dated_move_is_small_is_not_a_big_move_alert(monkeypatch) -> None:
    """Calibration's 07:23Z receipt. Basis 0.22 seen 19 h ago, 0.10 two hours
    ago, then a poll at 0.30: stored +0.20 nominates the row, but the dated day
    move is +0.08. The alert prints the dated move, so it must clear the same
    0.15 bar on it — no "Big Move Alert" for 8 points."""
    seed = _winner_field([(19, 0.22, "datagolf_model"), (2, 0.10, "datagolf_model")],
                         jordan_current=0.10)
    _, _, base_mod, push = _push(monkeypatch, seed)
    _write(monkeypatch, "live", {JORDAN: 0.30, **FIELD})
    _sweep(monkeypatch)
    result, bodies = _send(monkeypatch, base_mod, push)
    assert not any("Matthew Jordan" in b for b in bodies), (result, bodies)
    assert bodies == [], (result, bodies)


def test_d5a_a_dated_big_fall_is_still_a_big_move_alert(monkeypatch) -> None:
    """The bar is on the dated move's SIZE, either sign: basis 0.48 at 19 h,
    0.50 two hours ago, a poll to 0.30 (stored -0.20, the negative select) is a
    dated -0.18 day, a true big move, sent as a fall. Also the rig's positive
    control for the test above. (A fall nominated by a POSITIVE stored delta
    cannot reach the push: the shared contradicted-direction sweep step NULLs a
    claim whose dated change has the opposite sign.)"""
    seed = _winner_field([(19, 0.48, "datagolf_model"), (2, 0.50, "datagolf_model")],
                         jordan_current=0.50)
    _, _, base_mod, push = _push(monkeypatch, seed)
    _write(monkeypatch, "live", {JORDAN: 0.30, **FIELD})
    _sweep(monkeypatch)
    result, bodies = _send(monkeypatch, base_mod, push)
    assert any("Matthew Jordan is down 18.0pp" in b for b in bodies), (result, bodies)
    assert not any("20.0pp" in b for b in bodies), bodies


def test_d5a_a_dated_move_of_zero_is_not_a_digest_mover(monkeypatch) -> None:
    """Basis 0.15 at 19 h, 0.10 two hours ago, a poll back to 0.15: stored
    +0.05 nominates the row, the dated day move is 0. The digest must not list
    it as a top mover at "+0.0pp"; a Kalshi row's stored 0.05 still lists."""
    kalshi = _kalshi_market(
        {2001: 0.05}, [(2001, 0.30, [(19, 0.25, "kalshi"), (1, 0.30, "kalshi")])]
    )
    seed = _winner_field([(19, 0.15, "datagolf_model"), (2, 0.10, "datagolf_model")],
                         jordan_current=0.10, extra_markets=(kalshi,))
    asyncio.run(_reset_and_seed(seed))
    _write(monkeypatch, "live", {JORDAN: 0.15, **FIELD})
    _sweep(monkeypatch)

    digest = asyncio.run(_digest())
    names = {m["outcome"]: m["change"] for m in digest["movers"]}
    assert "Matthew Jordan" not in names, digest["movers"]
    assert abs(names["Player 2001"] - 0.05) < 1e-6, digest["movers"]


# ---------------------------------------------------------------------------
# D5 — the two files root approved at 07:42Z: league_futures + enrich_markets
# ---------------------------------------------------------------------------


def _enrich_spine(monkeypatch):
    """The spine (basis 0.02 at 19 h, 0.15 now, an unchanged poll storing 0,
    the real sweep) beside a Kalshi winner whose stored +0.05 is the control.
    Both markets tier 1, ranked leader-first, and linked to an upcoming
    fixture so the hook task's own selection admits them."""
    from sqlalchemy import text

    kalshi = _kalshi_market(
        {2001: 0.05}, [(2001, 0.30, [(19, 0.25, "kalshi"), (1, 0.30, "kalshi")])]
    )
    kalshi["market_tier"] = 1
    field = _winner_field([(19, 0.02, "datagolf_model")], extra_markets=(kalshi,))
    field[0]["market_tier"] = 1
    market_ids, outcome_ids = asyncio.run(_reset_and_seed(field))
    _write(monkeypatch, "live", _priced(0.15))
    _write(monkeypatch, "live", _priced(0.15))  # stored 0
    _sweep(monkeypatch)

    async def _link():
        from sqlalchemy.ext.asyncio import async_sessionmaker

        from app.models.models import Event, Sport

        engine = _engine()
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            sport = Sport(key="golf_pga", name="PGA")
            session.add(sport)
            await session.flush()
            event = Event(
                sport_id=sport.id, home_team_name="Round 3", away_team_name="Field",
                commence_time=datetime.now(timezone.utc) + timedelta(days=1),
            )
            session.add(event)
            await session.flush()
            await session.execute(text("UPDATE futures_markets SET event_id = :e"), {"e": event.id})
            await session.execute(text(
                "UPDATE futures_outcomes SET rank = CASE WHEN name IN"
                " ('Matthew Jordan', 'Player 2001') THEN 1 ELSE 2 END"
            ))
            await session.commit()
        await engine.dispose()

    asyncio.run(_link())
    return market_ids, outcome_ids


class _FakeLLM:
    """An OpenAI-shaped client that records every prompt and replies `reply`."""

    def __init__(self, reply: str):
        from types import SimpleNamespace

        self.prompts: list[str] = []
        self._reply = reply
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        from types import SimpleNamespace

        self.prompts.append(kwargs["messages"][-1]["content"])
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self._reply))]
        )


def _run_enrich(monkeypatch, task_name: str, reply: str) -> list[str]:
    import app.services.llm as llm
    import app.tasks.enrich_markets as em

    fake = _FakeLLM(reply)
    monkeypatch.setattr(llm, "_get_client", lambda: fake)
    monkeypatch.setattr(em, "get_task_session", lambda: _Ctx())
    asyncio.run(getattr(em, task_name)())
    return fake.prompts


def _line(prompts: list[str], name: str) -> str:
    lines = [ln for p in prompts for ln in p.splitlines() if f"{name}:" in ln]
    assert lines, (name, prompts)
    return lines[0]


def test_d5_league_card_states_the_dated_move(monkeypatch) -> None:
    """`/api/leagues/{sport}` cards: `_serialize_outcomes`, both callers' shape
    (a full ORM market), on the real rows. DataGolf → dated +0.13, not the
    stored 0; Kalshi → its stored +0.05 exactly as before."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import selectinload

    from app.models.models import FuturesMarket
    from app.routes.league_futures import _serialize_outcomes

    market_ids, _ = _enrich_spine(monkeypatch)

    async def _cards():
        engine = _engine()
        out = {}
        async with AsyncSession(engine, expire_on_commit=False) as session:
            for key in (("pga", "win"), ("pga", "kwin")):
                market = (await session.execute(
                    select(FuturesMarket)
                    .options(selectinload(FuturesMarket.outcomes))
                    .where(FuturesMarket.id == market_ids[key])
                )).scalar_one()
                ordered = sorted(market.outcomes, key=lambda o: -float(o.current_probability))
                out.update({r["name"]: r["movement_24h"] for r in _serialize_outcomes(ordered, market)})
        await engine.dispose()
        return out

    cards = asyncio.run(_cards())
    assert cards["Matthew Jordan"] is not None and abs(cards["Matthew Jordan"] - 0.13) < 1e-6, cards
    assert abs(cards["Player 2001"] - 0.05) < 1e-6, cards


def test_d5_hook_prompt_states_the_dated_move(monkeypatch) -> None:
    """`enrich_market_hooks` (stored, then served as `hook_description`): the
    DataGolf leader's leaderboard line carries its dated day move; on the
    stored 0 it would carry none. Kalshi's line keeps its stored +5%."""
    from app.utils.hook_prompt import NO_HOOK_SENTINEL

    _enrich_spine(monkeypatch)
    prompts = _run_enrich(monkeypatch, "enrich_market_hooks", NO_HOOK_SENTINEL)
    jordan = _line(prompts, "Matthew Jordan")
    assert "↑12% 24h" in jordan or "↑13% 24h" in jordan, jordan
    assert "↑5% 24h" in _line(prompts, "Player 2001"), prompts


def test_d5_discover_classifier_prompt_drives_the_dict_path(monkeypatch) -> None:
    """`enrich_discover_llm_metadata` reads the plain DICT snapshot of each
    market (`cand_rows`). `reader_change_24h(<dict>, …)` cannot see a dict's
    source and returns the raw value, so a naive route prints nothing here on
    the stored 0. The carrier makes it "+13.0pp"; Kalshi keeps "+5.0pp"."""
    _enrich_spine(monkeypatch)
    prompts = _run_enrich(monkeypatch, "enrich_discover_llm_metadata", "{}")
    assert "24h move +13.0pp" in _line(prompts, "Matthew Jordan"), prompts
    assert "24h move +5.0pp" in _line(prompts, "Player 2001"), prompts


def test_d5_snippet_angle_reads_the_dated_move(monkeypatch) -> None:
    """`enrich_snippet_angles` (stored as `snippet_v2`, then served): the
    leader's `MarketContext.movement_24h` is the dated move for DataGolf and
    the stored value for Kalshi."""
    import app.tasks.enrich_markets as em
    import app.utils.snippet_angles as sa

    _enrich_spine(monkeypatch)
    seen: dict = {}

    def _capture(ctx):
        seen[ctx.outcome_name] = ctx.movement_24h
        return None  # no angle: no rephrase call

    monkeypatch.setattr(sa, "select_angle", _capture)
    monkeypatch.setattr(em, "get_task_session", lambda: _Ctx())
    asyncio.run(em.enrich_snippet_angles())
    assert seen.get("Matthew Jordan") is not None, seen
    assert abs(float(seen["Matthew Jordan"]) - 0.13) < 1e-6, seen
    assert abs(float(seen["Player 2001"]) - 0.05) < 1e-6, seen
