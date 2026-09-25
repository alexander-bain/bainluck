"""#8692 — a between-rounds source keeps its basis for the golf card's move (real Postgres).

PILLAR: DISCOVER/TRUTH. SHIP: the golf card's "up N points today" stops leaving
out DataGolf every evening.

Seen on production 2026-09-25 19:25Z: Discover's FedEx Open de France card read
"Matt Fitzpatrick ▲9.9" on a blend that had moved ≈+15.7. The move averages the
sources that have a ~24h-ago basis (#3013), and the basis used to be "a write
captured 23–25h ago". DataGolf's model stops writing between rounds (its last
9/24 write was 17:58:33Z, 0.169), so every evening it had no row in that window
and its 0.169 → 0.440 dropped out. Which sources counted changed with the hour,
and the same golfer's "today" number jumped between two hourly rebuilds with no
price change.

The basis is now the source's number AS OF now−23h: its latest write at or before
that instant, no older than 36h (`MOVE_BASIS_MAX_AGE`). The whole change is that
SQL, so only Postgres can grade it — which row a `LATERAL ... ORDER BY ... LIMIT 1`
returns, and which rows the two bounds let it see.

The Fitzpatrick rows are production's own (fixture `golf_move_basis_8692`), at
their production ids.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DB_URL,
    reason="set SEARCH_TEST_DATABASE_URL to run the real-Postgres #8692 golf move-basis gate",
)

FIXTURE = json.loads(
    (
        Path(__file__).resolve().parent.parent
        / "fixtures"
        / "golf_move_basis_8692"
        / "fitzpatrick_snapshots.json"
    ).read_text()
)

DG, KALSHI, PM = 232672440, 231407113, 233295412
SOURCE_OF = {DG: "datagolf_model", KALSHI: "kalshi", PM: "polymarket"}
#: (market id, source, market name, outcome name) — production's.
MARKETS = {
    DG: (61720782, "datagolf", "FedEx Open de France - Winner", "Matt Fitzpatrick"),
    KALSHI: (61720900, "kalshi", "FedEx Open de France Winner", "Matt Fitzpatrick"),
    PM: (61720901, "polymarket", "DP World Tour: Open de France Winner", "Matthew Fitzpatrick"),
}
CURRENT = {int(k): v for k, v in FIXTURE["current_probability"].items()}
PM_SCALE = FIXTURE["polymarket_winner_field_scale"]

#: The rebuild the issue was filed on, and the hourly rebuilds either side of it.
REBUILD = datetime(2026, 9, 25, 19, 25, tzinfo=timezone.utc)
DG_LAST_PRE_GAP = datetime(2026, 9, 24, 17, 58, 33, 699126, tzinfo=timezone.utc)

#: Synthetic controls, one outcome each, ages relative to REBUILD.
CONTROL_MARKET = 70869200
#: label → (outcome id, [(hours before REBUILD, probability)])
CONTROLS = {
    "beyond_cap": (70869201, [(36.25, 0.30)]),
    "just_inside_cap": (70869202, [(35.9, 0.31)]),
    "too_new_only": (70869203, [(22.5, 0.90)]),
    "latest_not_first": (70869204, [(22.0, 0.99), (24.0, 0.40), (30.0, 0.20)]),
    "too_new_beside_too_old": (70869205, [(22.0, 0.99), (37.0, 0.10)]),
}


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value)


#: Every test here only READS the seeded rows, so the schema is rebuilt and seeded
#: once per module run; each test still gets its own engine on its own loop.
_SEEDED = False


@pytest.fixture
async def pg_engine():
    from sqlalchemy.ext.asyncio import create_async_engine

    global _SEEDED
    engine = create_async_engine(DB_URL)
    if not _SEEDED:
        await _rebuild_and_seed(engine)
        _SEEDED = True
    yield engine
    await engine.dispose()


async def _rebuild_and_seed(engine) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.models.models import FuturesMarket, FuturesOddsSnapshot, FuturesOutcome
    from app.services.database import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        for outcome_id, (market_id, source, market_name, name) in MARKETS.items():
            session.add(FuturesMarket(
                id=market_id, source=source, external_id=f"m-{market_id}",
                name=market_name, category="futures", market_tier=1, status="open",
            ))
            await session.flush()
            session.add(FuturesOutcome(
                id=outcome_id, market_id=market_id, external_id=f"o-{outcome_id}",
                name=name, current_probability=CURRENT[outcome_id],
            ))
        session.add(FuturesMarket(
            id=CONTROL_MARKET, source="kalshi", external_id="m-controls",
            name="Controls - Winner", category="futures", market_tier=1, status="open",
        ))
        await session.flush()
        for label, (outcome_id, _) in CONTROLS.items():
            session.add(FuturesOutcome(
                id=outcome_id, market_id=CONTROL_MARKET, external_id=f"o-{label}",
                name=label, current_probability=0.5,
            ))
        await session.flush()

        for row in FIXTURE["rows"]:
            session.add(FuturesOddsSnapshot(
                outcome_id=row["outcome_id"], bookmaker=row["bookmaker"],
                probability=float(row["probability"]), captured_at=_ts(row["captured_at"]),
            ))
        for label, (outcome_id, writes) in CONTROLS.items():
            for hours, prob in writes:
                session.add(FuturesOddsSnapshot(
                    outcome_id=outcome_id, bookmaker="kalshi", probability=prob,
                    captured_at=REBUILD - timedelta(hours=hours),
                ))
        await session.commit()


async def _basis(engine, now: datetime, ids) -> dict[int, float]:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.routes.golf import _fetch_24h_snapshots

    async with AsyncSession(engine) as db:
        return await _fetch_24h_snapshots(db, list(ids), now)


def _served_move(basis: dict[int, float]) -> tuple[float | None, bool, set[str]]:
    """The card's number, through the REAL aggregation (#3013)."""
    from app.routes.golf import _aggregate_golfer_outcome

    class _Outcome:
        def __init__(self, oid):
            self.id = oid
            self.name = MARKETS[oid][3]
            self.current_probability = CURRENT[oid]
            self.probability_change_24h = None
            self.opening_probability = None

    data: dict[str, dict] = {}
    for oid in (DG, KALSHI, PM):
        _aggregate_golfer_outcome(
            _Outcome(oid), SOURCE_OF[oid], data, basis,
            prob_scale=PM_SCALE if oid == PM else 1.0,
        )
    (entry,) = data.values()
    return entry["movement_24h"], entry["movement_is_dated"], set(entry["dated_deltas"])


def _old_window_sources(now: datetime) -> set[int]:
    """What the pre-#8692 23–25h `between` would have dated, over the same rows."""
    lo, hi = now - timedelta(hours=25), now - timedelta(hours=23)
    return {r["outcome_id"] for r in FIXTURE["rows"] if lo <= _ts(r["captured_at"]) <= hi}


class TestTheBetweenRoundsSourceCounts:
    async def test_datagolfs_last_write_before_the_gap_is_its_basis(self, pg_engine):
        """THE guard: a 25.5h-old DataGolf write still counts (0.169 → 0.440)."""
        assert 25.4 < (REBUILD - DG_LAST_PRE_GAP).total_seconds() / 3600 < 25.5
        basis = await _basis(pg_engine, REBUILD, (DG, KALSHI, PM))
        assert basis == {DG: pytest.approx(0.169124), KALSHI: 0.165, PM: 0.165}

    async def test_the_card_states_the_blends_whole_move(self, pg_engine):
        basis = await _basis(pg_engine, REBUILD, (DG, KALSHI, PM))
        move, dated, sources = _served_move(basis)
        assert sources == {"datagolf_model", "kalshi", "polymarket"}
        expected = (
            (0.439817 - 0.169124) + (0.255 - 0.165) + (0.395 - 0.165) * PM_SCALE
        ) / 3
        assert move == pytest.approx(expected, abs=1e-4)
        assert move > 0.15, "the card would again read ~+9.9 on a ≈+15.7 blend move"
        assert dated is True

    async def test_the_move_is_stable_across_a_rebuild_where_coverage_flipped(self, pg_engine):
        before, after = REBUILD - timedelta(hours=1), REBUILD
        # CONTROL: over these exact rows the old window DID flip DataGolf out
        # between these two rebuilds, so a stable answer below is the fix.
        assert DG in _old_window_sources(before)
        assert DG not in _old_window_sources(after)

        moves = [_served_move(await _basis(pg_engine, t, (DG, KALSHI, PM))) for t in (before, after)]
        assert moves[0] == moves[1]
        assert moves[0][2] == {"datagolf_model", "kalshi", "polymarket"}

    async def test_the_evening_after_the_filed_rebuild_still_dates_every_source(self, pg_engine):
        """20:25Z: the old window held NO source at all (Kalshi next wrote at 22:49Z)."""
        later = REBUILD + timedelta(hours=1)
        assert _old_window_sources(later) == set()
        basis = await _basis(pg_engine, later, (DG, KALSHI, PM))
        assert set(basis) == {DG, KALSHI, PM}


class TestTheCapAndTheOrdering:
    async def _controls(self, engine) -> dict[str, float | None]:
        ids = {oid: label for label, (oid, _) in CONTROLS.items()}
        basis = await _basis(engine, REBUILD, ids)
        return {label: basis.get(oid) for oid, label in ids.items()}

    async def test_a_source_with_no_write_inside_the_cap_stays_undated(self, pg_engine):
        """CONTROL: 36h15m old is past the cap — absent, never a stale guess."""
        got = await self._controls(pg_engine)
        assert got["beyond_cap"] is None
        assert got["too_new_beside_too_old"] is None
        assert got["just_inside_cap"] == pytest.approx(0.31)

    async def test_a_write_newer_than_23h_is_never_the_basis(self, pg_engine):
        got = await self._controls(pg_engine)
        assert got["too_new_only"] is None

    async def test_the_basis_is_the_latest_eligible_write_not_the_oldest(self, pg_engine):
        got = await self._controls(pg_engine)
        assert got["latest_not_first"] == pytest.approx(0.40)

    async def test_an_outcome_with_no_rows_is_absent(self, pg_engine):
        assert await _basis(pg_engine, REBUILD, [99999999]) == {}
