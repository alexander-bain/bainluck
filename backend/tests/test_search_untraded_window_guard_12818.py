"""#12818: Search 60-row futures window guard against untraded/empty-book saturation.

A market nobody has traded must never push a traded market out of the 60-row
SQL window (`_SEARCH_FUTURES_WINDOW` + `_SEARCH_FUTURES_REFILL`).
"""

from __future__ import annotations

import inspect
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.routes import events as events_mod

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")


class _FakeRedis:
    def __init__(self):
        self.data: dict[str, str] = {}

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.data:
            return False
        self.data[key] = value
        return True

    def setex(self, key, ttl, value):
        self.data[key] = value
        return True

    def delete(self, key):
        self.data.pop(key, None)
        return 1


def _row(
    mid: int,
    name: str,
    *,
    tier: int = 0,
    volume=1000,
    volume_24h=None,
    open_interest=None,
    source: str = "polymarket",
    outcomes=(),
):
    return SimpleNamespace(
        id=mid,
        name=name,
        _tier=tier,
        volume=volume,
        volume_24h=volume_24h,
        open_interest=open_interest,
        source=source,
        outcomes=list(outcomes),
    )


def _outcome(
    prob: float | None = 0.5,
    bid: float | None = None,
    ask: float | None = None,
    *,
    volume=None,
    volume_24h=None,
):
    return SimpleNamespace(
        current_probability=prob,
        current_yes_bid=bid,
        current_yes_ask=ask,
        volume=volume,
        volume_24h=volume_24h,
    )


def test_sql_order_places_untraded_guard_first_while_preserving_tier_order():
    """`_futures_untraded_rank` sorts first; tier<rank<prefix<market_tier holds."""
    src = inspect.getsource(events_mod.search_events)
    order_by = src[src.index("def _futures_window_query(") :]
    order_by = order_by[order_by.index(".order_by(") :]

    guard_at = order_by.index("_futures_untraded_rank.asc()")
    tier_at = order_by.index("_futures_name_tier.asc()")
    rank_at = order_by.index("futures_search_rank.desc()")
    assert guard_at < tier_at < rank_at

    sql = str(
        select(events_mod._futures_untraded_order_key()).compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "futures_markets.volume >" in sql
    assert "futures_markets.volume_24h >" in sql
    assert "futures_markets.open_interest >" in sql
    assert "futures_markets.volume IS NOT NULL" in sql
    assert "futures_markets.source =" in sql
    assert "EXISTS (SELECT 1" in sql and "FROM futures_outcomes" in sql


def test_futures_row_is_traded_matches_volume_and_empty_book_semantics():
    """Python predicate agrees across explicit 0, NULL+empty-book, odds_api, and legacy priced rows."""
    is_traded = events_mod._futures_row_is_traded

    # Explicit positive liquidity on market always traded
    assert is_traded(_row(1, "Marquee", volume=44_000_000))
    assert is_traded(_row(2, "Day vol", volume=0, volume_24h=250))
    assert is_traded(_row(3, "Open int", volume=None, open_interest=15))

    # Explicit zero market volume with no 24h/OI activity is untraded
    assert not is_traded(
        _row(
            4,
            "Zero Vol",
            volume=0,
            volume_24h=0,
            open_interest=0,
            outcomes=[_outcome(0.5, 0.49, 0.51)],
        )
    )
    assert not is_traded(_row(5, "Zero Vol Minimal", volume=0, outcomes=[]))

    # Sportsbooks carry no contract volume column
    assert is_traded(_row(6, "Sportsbook", volume=None, source="odds_api", outcomes=[]))

    # NULL market volume (Kalshi `or None` zero volume or sparse test fixtures)
    assert not is_traded(_row(7, "Null Prob", volume=None, outcomes=[_outcome(None)]))
    assert not is_traded(
        _row(8, "Empty Mid", volume=None, outcomes=[_outcome(0.50, 0.01, 0.99)])
    )
    assert not is_traded(
        _row(9, "Boundary Empty", volume=None, outcomes=[_outcome(0.51, 0.05, 0.95)])
    )
    assert not is_traded(
        _row(10, "Bidless Empty", volume=None, outcomes=[_outcome(0.50, None, 0.99)])
    )
    assert not is_traded(_row(11, "No Outcomes", volume=None, outcomes=[]))

    # NULL market volume WITH real priced outcome or outcome volume is kept traded
    assert is_traded(
        _row(12, "Tight Book", volume=None, outcomes=[_outcome(0.35, 0.33, 0.37)])
    )
    assert is_traded(
        _row(13, "Legacy Fixture", volume=None, outcomes=[_outcome(0.35, None, None)])
    )
    assert is_traded(
        _row(14, "Off Mid Trade", volume=None, outcomes=[_outcome(0.15, 0.01, 0.99)])
    )
    assert is_traded(
        _row(
            15,
            "Outcome Vol",
            volume=None,
            outcomes=[_outcome(0.50, 0.01, 0.99, volume_24h=25.0)],
        )
    )


class _StubResult:
    def __init__(self, rows):
        self._rows = list(rows)

    def scalars(self):
        return self

    def unique(self):
        return self

    def all(self):
        return list(self._rows)


class _FakeNested:
    async def commit(self):
        return None

    async def rollback(self):
        return None


class _FakeDB:
    async def execute(self, stmt):
        return _StubResult(stmt)

    async def begin_nested(self):
        return _FakeNested()


def _make_window_builders(rows_by_id: dict[int, SimpleNamespace], arm_ids: dict[str, list[int]]):
    def candidates_in(arms):
        seen: list[int] = []
        for arm in arms:
            for mid in arm_ids[arm]:
                if mid not in seen:
                    seen.append(mid)
        return seen

    class _WindowQuery(list):
        def limit(self, n):
            return _WindowQuery(self[:n])

    def window_query(cand_ids):
        rows = [rows_by_id[mid] for mid in cand_ids]
        rows.sort(
            key=lambda m: (
                0 if events_mod._futures_row_is_traded(m) else 1,
                m._tier,
                -(m.volume or 0),
                m.id,
            )
        )
        return _WindowQuery(rows[: events_mod._SEARCH_FUTURES_WINDOW])

    return candidates_in, window_query


@pytest.mark.asyncio
async def test_fetch_futures_window_does_not_skip_outcome_arm_on_untraded_saturation():
    """60 untraded tier-0 rows must not skip a traded tier-2 outcome-only row."""
    rows = {
        mid: _row(mid, f"Donald Trump {mid}", tier=0, volume=0)
        for mid in range(1, 61)
    }
    rows[999] = _row(
        999, "2028 Presidential Election Winner", tier=2, volume=10_000_000
    )
    candidates_in, window_query = _make_window_builders(
        rows,
        {"name": list(range(1, 61)), "outcome": [999]},
    )

    got, state = await events_mod._fetch_futures_window(
        _FakeDB(),
        window_query,
        candidates_in,
        ["name"],
        "outcome",
        deadline=1e18,
        tier1_limit=events_mod._SEARCH_FUTURES_WINDOW + events_mod._SEARCH_FUTURES_REFILL,
        row_is_traded=events_mod._futures_row_is_traded,
    )
    assert state == "merged"
    assert got[0].id == 999
    assert len(got) == events_mod._SEARCH_FUTURES_WINDOW


@pytest.mark.asyncio
async def test_fetch_futures_window_skips_when_20_traded_tier1_rows_fill_window():
    rows = {
        mid: _row(mid, f"Traded {mid}", tier=0, volume=5000 - mid)
        for mid in range(1, 21)
    }
    for mid in range(21, 31):
        rows[mid] = _row(mid, f"Untraded {mid}", tier=0, volume=0)
    rows[999] = _row(999, "Outcome Match", tier=2, volume=999_999)
    candidates_in, window_query = _make_window_builders(
        rows,
        {"name": list(range(1, 31)), "outcome": [999]},
    )

    got, state = await events_mod._fetch_futures_window(
        _FakeDB(),
        window_query,
        candidates_in,
        ["name"],
        "outcome",
        deadline=1e18,
        tier1_limit=events_mod._SEARCH_FUTURES_WINDOW + events_mod._SEARCH_FUTURES_REFILL,
        row_is_traded=events_mod._futures_row_is_traded,
    )
    assert state == "skipped"
    assert [m.id for m in got[:20]] == list(range(1, 21))
    assert 999 not in {m.id for m in got}


@pytest.mark.asyncio
async def test_fetch_futures_window_counts_traded_rows_for_split_arms():
    rows = {
        mid: _row(mid, f"Untraded {mid}", tier=0, volume=0)
        for mid in range(1, 56)
    }
    for mid in range(100, 105):
        rows[mid] = _row(mid, f"Traded Tier1 {mid}", tier=0, volume=1000)
    rows[200] = _row(200, "Traded Split", tier=1, volume=500)
    candidates_in, window_query = _make_window_builders(
        rows,
        {"name": list(range(1, 56)) + list(range(100, 105)), "split": [200]},
    )
    split_report: dict = {}

    got, state = await events_mod._fetch_futures_window(
        _FakeDB(),
        window_query,
        candidates_in,
        ["name"],
        None,
        deadline=1e18,
        tier1_limit=events_mod._SEARCH_FUTURES_WINDOW + events_mod._SEARCH_FUTURES_REFILL,
        split_arms=["split"],
        split_report=split_report,
        row_is_traded=events_mod._futures_row_is_traded,
    )
    assert state == "absent"
    assert split_report["state"] == "merged"
    traded_ids = {m.id for m in got if events_mod._futures_row_is_traded(m)}
    assert traded_ids == {100, 101, 102, 103, 104, 200}


def test_futures_refill_in_hand_and_sunk_spare_guard_against_untraded_tail():
    refill_n = events_mod._SEARCH_FUTURES_REFILL
    all_traded = [_row(i, f"T {i}", volume=100) for i in range(refill_n)]
    mixed = all_traded[:-1] + [_row(999, "Untraded", volume=0)]

    assert (
        events_mod._futures_refill_in_hand(
            "skipped", all_traded, row_is_traded=events_mod._futures_row_is_traded
        )
        == all_traded
    )
    assert (
        events_mod._futures_refill_in_hand(
            "skipped", mixed, row_is_traded=events_mod._futures_row_is_traded
        )
        is None
    )
    assert (
        events_mod._futures_refill_in_hand(
            "absent", mixed, row_is_traded=events_mod._futures_row_is_traded
        )
        == mixed
    )

    sunk = events_mod._sunk_slot_spare_rows(
        "skipped",
        mixed,
        over_cap_ids={1},
        answer_rows=1,
        refill_source="not_fired",
        row_is_traded=events_mod._futures_row_is_traded,
    )
    assert [m.id for m in sunk] == [i for i in range(refill_n - 1)]


@pytest.mark.skipif(
    not DB_URL,
    reason="set SEARCH_TEST_DATABASE_URL to run real-Postgres #12818 Donald Trump guard test",
)
@pytest.mark.asyncio
async def test_donald_trump_untraded_markets_cannot_displace_traded_from_60_row_window():
    """#12818 real PG: 65 untraded tier-5 'Donald Trump' markets cannot crowd out $44M Trump or traded rows."""
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401
    from app.main import app
    from app.models.models import FuturesMarket, FuturesOutcome, Sport
    from app.services.database import Base, get_db, get_db_rw

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    res_dt = now + timedelta(days=90)

    async with maker() as s:
        pol = Sport(key="politics_us", name="US Politics")
        s.add(pol)
        await s.flush()

        marquee = FuturesMarket(
            source="polymarket",
            external_id="PM-TRUMP-44M",
            name="Donald J. Trump: 2026 Presidential Approval Benchmark Score",
            market_type="politics",
            llm_sport_category="politics",
            status="open",
            sport_id=pol.id,
            market_tier=1,
            volume=44_000_000,
            volume_24h=250_000,
            resolution_date=res_dt,
            updated_at=now - timedelta(hours=1),
        )
        s.add(marquee)
        await s.flush()
        s.add(
            FuturesOutcome(
                market_id=marquee.id,
                external_id="PM-TRUMP-44M-YES",
                name="Above 45%",
                current_probability=0.46,
                current_yes_bid=0.45,
                current_yes_ask=0.47,
            )
        )

        # 65 short-title tier-5 Polymarket markets nobody has traded (`volume=0`, empty/NULL books)
        # exceeding _SEARCH_FUTURES_WINDOW + _SEARCH_FUTURES_REFILL (= 60) with exact phrase match.
        untraded_ids: list[int] = []
        for idx in range(65):
            u = FuturesMarket(
                source="polymarket",
                external_id=f"PM-TRUMP-EMPTY-{idx}",
                name="Donald Trump",
                market_type="politics",
                llm_sport_category="politics",
                status="open",
                sport_id=pol.id,
                market_tier=5,
                volume=0,
                volume_24h=0,
                open_interest=0,
                resolution_date=res_dt,
                updated_at=now,
            )
            s.add(u)
            await s.flush()
            untraded_ids.append(u.id)
            s.add(
                FuturesOutcome(
                    market_id=u.id,
                    external_id=f"PM-TRUMP-EMPTY-{idx}-YES",
                    name="Yes",
                    current_probability=None if idx % 2 == 0 else 0.50,
                    current_yes_bid=None if idx % 2 == 0 else 0.01,
                    current_yes_ask=None if idx % 2 == 0 else 0.99,
                )
            )

        # Kalshi-shaped zero-volume (`volume=None`) empty-book market (`0.01/0.99 @ 0.50`)
        kalshi_empty = FuturesMarket(
            source="kalshi",
            external_id="KX-TRUMP-EMPTY",
            name="Donald Trump",
            market_type="politics",
            llm_sport_category="politics",
            status="open",
            sport_id=pol.id,
            market_tier=5,
            volume=None,
            volume_24h=None,
            open_interest=None,
            resolution_date=res_dt,
            updated_at=now,
        )
        s.add(kalshi_empty)
        await s.flush()
        s.add(
            FuturesOutcome(
                market_id=kalshi_empty.id,
                external_id="KX-TRUMP-EMPTY-YES",
                name="Yes",
                current_probability=0.50,
                current_yes_bid=0.01,
                current_yes_ask=0.99,
            )
        )

        # Control: Kalshi `volume=None` market with a genuine tight book must NOT be treated as untraded
        null_vol_priced = FuturesMarket(
            source="kalshi",
            external_id="KX-TRUMP-PRICED",
            name="Donald Trump Cabinet Confirmation Odds",
            market_type="politics",
            llm_sport_category="politics",
            status="open",
            sport_id=pol.id,
            market_tier=2,
            volume=None,
            volume_24h=None,
            open_interest=None,
            resolution_date=res_dt,
            updated_at=now - timedelta(minutes=10),
        )
        s.add(null_vol_priced)
        await s.flush()
        s.add(
            FuturesOutcome(
                market_id=null_vol_priced.id,
                external_id="KX-TRUMP-PRICED-YES",
                name="Yes",
                current_probability=0.35,
                current_yes_bid=0.33,
                current_yes_ask=0.37,
            )
        )

        # Tier-2 outcome-only traded market (`name` omits "Trump", outcome names "Donald Trump")
        outcome_only_traded = FuturesMarket(
            source="polymarket",
            external_id="PM-TIME-POTY-2026",
            name="Time Person of the Year 2026",
            market_type="culture",
            llm_sport_category="culture",
            status="open",
            sport_id=pol.id,
            market_tier=2,
            volume=10_000_000,
            volume_24h=100_000,
            resolution_date=res_dt,
            updated_at=now - timedelta(minutes=20),
        )
        s.add(outcome_only_traded)
        await s.flush()
        s.add(
            FuturesOutcome(
                market_id=outcome_only_traded.id,
                external_id="PM-TIME-POTY-2026-TRUMP",
                name="Donald Trump",
                current_probability=0.18,
                current_yes_bid=0.17,
                current_yes_ask=0.19,
            )
        )
        await s.commit()

        # Verify exact SQL <-> Python agreement across every seeded market
        sql_rows = (
            await s.execute(
                select(FuturesMarket.id, events_mod._futures_untraded_order_key())
            )
        ).all()
        sql_rank_by_id = dict(sql_rows)
        all_markets = (
            await s.execute(select(FuturesMarket))
        ).scalars().all()
        for m in all_markets:
            await s.refresh(m, attribute_names=["outcomes"])
            expected_rank = 0 if events_mod._futures_row_is_traded(m) else 1
            assert sql_rank_by_id[m.id] == expected_rank, (m.external_id, sql_rank_by_id[m.id], expected_rank)

    async def _override():
        async with maker() as sess:
            yield sess

    app.dependency_overrides[get_db] = _override
    app.dependency_overrides[get_db_rw] = _override
    fake = _FakeRedis()
    try:
        with patch("app.tasks.redis_state.get_redis_client", return_value=fake):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/api/events/search", params={"q": "donald trump"})
                assert resp.status_code == 200, resp.text
                body = resp.json()
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()

    returned_ids = [f["id"] for f in body.get("futures", [])]
    assert returned_ids, "CONTROL: search returned no futures at all"
    assert returned_ids[0] == marquee.id, (
        f"65 untraded tier-5 markets pushed $44M marquee Trump off slot 0: {returned_ids}"
    )
    assert null_vol_priced.id in returned_ids
    assert outcome_only_traded.id in returned_ids
    assert kalshi_empty.id not in returned_ids
    assert not any(uid in returned_ids for uid in untraded_ids)
