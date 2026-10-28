"""#10090: the graph read binds its events as ONE array, with identical rows.

`event_id = ANY(:event_ids)` replaced an expanding `event_id IN (...)`, whose
every list length was its own statement, so its own prepared statement per
connection (production pg_stat_statements: 170 Polymarket / 18 Kalshi shapes
cycling a 100-entry cache). On real PostgreSQL: the same snapshot answers both
forms with byte-identical rows on the stamp and preview paths, and one
connection prepares a single statement across batch sizes.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Event, FuturesMarket, FuturesOutcome
from app.tasks.live_blend_refresh import LiveBlendRefresher
from tests.integration.test_live_blend_grouped_commit_8129_pg import DB_URL, rig as _rig, seed

rig = _rig

pytestmark = [pytest.mark.asyncio, pytest.mark.skipif(not DB_URL, reason="disposable PostgreSQL required")]


class ExpandingInOracle:
    """Run the statement as given AND with the old expanding IN, same snapshot."""

    def __init__(self, session, source):
        self.session = session
        self.source = source
        self.pairs = []

    async def execute(self, statement):
        ids = statement.compile().params["event_ids"]
        old = statement._clone()
        old._where_criteria = (
            FuturesMarket.source == self.source,
            FuturesMarket.event_id.in_(ids),
        )
        assert "IN (__[POSTCOMPILE_event_id_1])" in str(old)
        assert "event_id = ANY (:event_ids)" in str(statement)
        new_rows = (await self.session.execute(statement)).all()
        old_rows = (await self.session.execute(old)).all()
        self.pairs.append((ids, new_rows, old_rows))

        class Rows:
            def all(self):
                return new_rows

        return Rows()


async def _mixed_slate(rig):
    """Two venues, several markets per event, one market with no outcomes."""
    await seed(rig, count=6)
    now = datetime.now(timezone.utc)
    async with rig.maker() as session:
        for market_id, event_id, source, ticker in (
            (101, 1, "kalshi", "KXMLBGAME-26OCT28MIACHC-CHC"),
            (102, 1, "kalshi", "KXMLBTOTAL-26OCT28MIACHC-9"),
            (103, 2, "kalshi", "KXMLBGAME-26OCT28MIACHC2-MIA"),
            (104, 3, "polymarket", "game-3-alt"),
            (105, 4, "polymarket", "no-outcomes"),
        ):
            session.add(FuturesMarket(
                id=market_id, source=source, external_id=ticker, event_id=event_id,
                name="Miami Marlins vs Chicago Cubs", status="open", category="game",
                market_type="duel",
            ))
        await session.flush()
        for outcome_id, market_id, name, price in (
            (1001, 101, "Chicago Cubs", .61), (1002, 101, "Miami Marlins", .39),
            (1003, 102, "Over 9", .52), (1004, 103, "Miami Marlins", .44),
            (1005, 104, "Chicago Cubs", .58), (1006, 104, "Miami Marlins", .42),
        ):
            session.add(FuturesOutcome(
                id=outcome_id, market_id=market_id, external_id=f"o-{outcome_id}", name=name,
                current_probability=price, rank=1, last_updated=now - timedelta(seconds=outcome_id % 7),
            ))
        await session.commit()
    async with rig.engine.begin() as conn:
        await conn.execute(update(Event).where(Event.id == 2).values(
            win_probability_sources={"kalshi": {"value": .44, "nested": [1, {"a": None}]}},
        ))


@pytest.mark.parametrize("source", ["polymarket", "kalshi"])
@pytest.mark.parametrize("preview", [False, True], ids=["stamp-path", "preview-path"])
async def test_array_bind_returns_the_expanding_in_rows_byte_for_byte(rig, source, preview, monkeypatch):
    await _mixed_slate(rig)
    refresher = LiveBlendRefresher(source)
    refresher.preview_events = frozenset({1, 2, 3, 4}) if preview else frozenset()

    async def admission():
        return None

    monkeypatch.setattr(refresher, "_preview_admission_read", admission)
    cases = ([1], [2, 1], [1, 2, 3, 4, 5, 6], [6, 999, 3], [], [3, 3])
    async with rig.maker() as session:
        oracle = ExpandingInOracle(session, source)
        for ids in cases:
            await refresher._read_groups(oracle, ids, overlay_held=not preview)
    assert [ids for ids, _, _ in oracle.pairs] == [list(ids) for ids in cases]
    returned = 0
    for ids, new_rows, old_rows in oracle.pairs:
        # Same snapshot, same projection: identical tuples once sorted (neither
        # form promises an order; the grouping is keyed). The preview path's
        # trailing statement_timestamp() is each statement's own clock.
        def rows(found):
            if preview:
                assert all(isinstance(row[-1], datetime) for row in found)
                found = [row[:-1] for row in found]
            return sorted(map(tuple, found), key=repr)

        assert rows(new_rows) == rows(old_rows), ids
        returned += len(new_rows)
    assert returned  # the cases are not vacuous for either venue


async def test_one_connection_prepares_one_statement_across_batch_sizes(rig, monkeypatch):
    await _mixed_slate(rig)
    refresher = LiveBlendRefresher("polymarket")
    refresher.preview_events = frozenset()
    async with rig.engine.connect() as conn:
        session = AsyncSession(bind=conn)
        for ids in ([1], [1, 2], [1, 2, 3], list(range(1, 41)), [5]):
            await refresher._read_groups(session, ids)
        prepared = (await conn.execute(text(
            "SELECT statement FROM pg_prepared_statements"
            " WHERE statement LIKE '%FROM futures_markets JOIN events%'"
            " AND statement NOT LIKE '%pg_prepared_statements%'"
        ))).scalars().all()
        await session.close()
    assert len(prepared) == 1, prepared
    assert "futures_markets.event_id = ANY ($" in prepared[0]
