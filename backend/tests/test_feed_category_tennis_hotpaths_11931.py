"""Tests for #11931 category single-CTE union, multi-league sport-pill hint, and stage timing."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

import app.routes.feed as feed_mod
from app.models.models import Event, FuturesMarket, Sport
from app.services.database import Base
from app.utils.category_candidate_union import build_category_candidate_union_query

NOW = datetime(2026, 7, 30, 12, 0, 0, tzinfo=timezone.utc)


def _pg_sql(stmt) -> str:
    return str(stmt.compile(dialect=postgresql.dialect())).lower()


class _SyncBackedAsyncSession(AsyncSession):
    """Minimal AsyncSession adapter backed by an in-memory sqlite3 Session."""

    def __init__(self, sync_session: Session) -> None:
        self._sync = sync_session
        self.executed_pg_sql: list[str] = []

    async def execute(self, statement, *args, **kwargs):
        self.executed_pg_sql.append(_pg_sql(statement))
        return self._sync.execute(statement, *args, **kwargs)


class TestCategoryCandidateUnionSQL:
    def test_politics_category_compiles_materialized_cte_union(self):
        id_filters, specs = feed_mod._discover_candidate_pool_specs(
            NOW, category_filter="politics"
        )
        active = [
            (n, q, lim)
            for n, q, lim in specs
            if not feed_mod._pool_disjoint_from_category(n, "politics")
        ]
        assert len(active) == 5
        union_q = build_category_candidate_union_query(id_filters, active)
        assert union_q is not None
        sql = _pg_sql(union_q)
        assert "with cat_base as materialized" in sql
        assert "from futures_markets" in sql
        assert sql.count("union all") == 4
        assert "llm_sport_category =" in sql

    def test_basketball_category_compiles_materialized_cte_union_for_sports_pools(self):
        id_filters, specs = feed_mod._discover_candidate_pool_specs(
            NOW, category_filter="basketball"
        )
        active = [
            (n, q, lim)
            for n, q, lim in specs
            if not feed_mod._pool_disjoint_from_category(n, "basketball")
        ]
        assert len(active) == 3
        union_q = build_category_candidate_union_query(id_filters, active)
        assert union_q is not None
        sql = _pg_sql(union_q)
        assert "with cat_base as materialized" in sql
        assert sql.count("union all") == 2

    def test_empty_active_specs_returns_none(self):
        assert build_category_candidate_union_query([], []) is None


@pytest.mark.asyncio
class TestCategoryCandidateUnionExecutionParity:
    async def test_union_matches_sequential_pools_bit_for_bit(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine, tables=[FuturesMarket.__table__])

        with Session(engine) as sync_db:
            rows = [
                # Politics rows covering volume, movement, enriched, editorial_recall, timely
                FuturesMarket(
                    id=101,
                    external_id="p-vol-top",
                    source="polymarket",
                    name="2028 Presidential Winner",
                    status="open",
                    llm_sport_category="politics",
                    volume_24h=900_000.0,
                    market_tier=1,
                    max_movement_24h=0.02,
                    hook_description="Top volume race",
                    hook_generated_at=NOW - timedelta(hours=3),
                    updated_at=NOW - timedelta(minutes=10),
                    resolution_date=NOW + timedelta(days=300),
                    is_editorial_recall=True,
                ),
                FuturesMarket(
                    id=102,
                    external_id="p-mov-top",
                    source="kalshi",
                    name="Senate Control 2026",
                    status="open",
                    llm_sport_category="politics",
                    volume_24h=150_000.0,
                    market_tier=2,
                    max_movement_24h=0.14,
                    updated_at=NOW - timedelta(minutes=5),
                    resolution_date=NOW + timedelta(days=20),
                    is_editorial_recall=False,
                ),
                FuturesMarket(
                    id=103,
                    external_id="p-timely",
                    source="polymarket",
                    name="House Vote This Week",
                    status="open",
                    llm_sport_category="politics",
                    volume_24h=40_000.0,
                    market_tier=2,
                    max_movement_24h=0.0,
                    image_url="https://cdn.example.com/house.jpg",
                    hook_generated_at=NOW - timedelta(minutes=20),
                    updated_at=NOW - timedelta(minutes=2),
                    resolution_date=NOW + timedelta(days=2),
                    is_editorial_recall=True,
                ),
                # Excluded politics rows (closed or expired)
                FuturesMarket(
                    id=104,
                    external_id="p-closed",
                    source="polymarket",
                    name="Closed Politics Race",
                    status="closed",
                    llm_sport_category="politics",
                    volume_24h=9_999_999.0,
                    market_tier=1,
                ),
                FuturesMarket(
                    id=105,
                    external_id="p-expired",
                    source="kalshi",
                    name="Expired Politics Race",
                    status="open",
                    llm_sport_category="politics",
                    volume_24h=8_888_888.0,
                    market_tier=1,
                    resolution_date=NOW - timedelta(days=1),
                ),
                # Basketball rows (sports category)
                FuturesMarket(
                    id=201,
                    external_id="b-finals",
                    source="polymarket",
                    name="Will Celtics win NBA Finals?",
                    status="open",
                    llm_sport_category="basketball",
                    volume_24h=500_000.0,
                    market_tier=1,
                    updated_at=NOW - timedelta(minutes=5),
                    resolution_date=NOW + timedelta(days=180),
                ),
                FuturesMarket(
                    id=202,
                    external_id="b-mvp",
                    source="kalshi",
                    name="NBA MVP Award Winner",
                    status="open",
                    llm_sport_category="basketball",
                    volume_24h=250_000.0,
                    market_tier=1,
                    updated_at=NOW - timedelta(minutes=10),
                    resolution_date=NOW + timedelta(days=150),
                ),
            ]
            sync_db.add_all(rows)
            sync_db.commit()

            for cat in ("politics", "basketball"):
                id_filters, specs = feed_mod._discover_candidate_pool_specs(
                    NOW, category_filter=cat
                )
                seq_ids: list[int] = []
                seq_counts: dict[str, int] = {}
                for name, query, _lim in specs:
                    if feed_mod._pool_disjoint_from_category(name, cat):
                        seq_counts[name] = 0
                        continue
                    r = sync_db.execute(query)
                    ids = list(r.scalars().all())
                    seq_counts[name] = len(ids)
                    seq_ids.extend(ids)
                seq_deduped = list(dict.fromkeys(seq_ids))

                db = _SyncBackedAsyncSession(sync_db)
                with patch.object(
                    feed_mod,
                    "_external_curator_recall_market_ids",
                    new=AsyncMock(return_value=[]),
                ):
                    stages: list[str] = []
                    got_ids, got_counts, got_ext = (
                        await feed_mod._compute_ordered_candidate_ids(
                            db,
                            NOW,
                            None,
                            category_filter=cat,
                            mark_timing=stages.append,
                        )
                    )

                assert len(db.executed_pg_sql) == 1
                assert got_ext == []
                assert got_ids == seq_deduped, f"{cat}: {got_ids} != {seq_deduped}"
                for name, cnt in seq_counts.items():
                    assert got_counts[name] == cnt, f"{cat}/{name}: {got_counts[name]} != {cnt}"
                assert got_counts["deduped"] == len(seq_deduped)
                assert "pool_category_union" in stages

        engine.dispose()


@pytest.mark.asyncio
class TestSportFilterIndexCap:
    async def test_small_vs_large_sport_family_uses_index_cap(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine, tables=[Sport.__table__, Event.__table__])

        with Session(engine) as sync_db:
            # 2 football sports (<= 8 -> direct sport_id IN)
            for i in range(2):
                sync_db.add(
                    Sport(
                        id=10 + i,
                        key=f"americanfootball_league_{i}",
                        name=f"FB {i}",
                        active=True,
                    )
                )
            # 12 tennis sports (> 8 -> (sport_id + 0) IN)
            for i in range(12):
                sync_db.add(
                    Sport(
                        id=100 + i,
                        key=f"tennis_atp_tour_{i}",
                        name=f"ATP {i}",
                        active=True,
                    )
                )
            sync_db.commit()

            db_fb = _SyncBackedAsyncSession(sync_db)
            timings: list[dict[str, float | str]] = []
            await feed_mod._score_events(
                db_fb,
                NOW,
                "football",
                feed_mod.PersonalizationContext(),
                sports_mode=True,
                timing_records=timings,
                timing_started_at=0.0,
            )
            ev_queries_fb = [s for s in db_fb.executed_pg_sql if "from events" in s]
            assert ev_queries_fb, "expected events query for football"
            assert "events.sport_id in" in ev_queries_fb[-1]
            assert "events.sport_id + " not in ev_queries_fb[-1]
            assert any(entry.get("stage") == "events.query" for entry in timings)

            db_tn = _SyncBackedAsyncSession(sync_db)
            await feed_mod._score_events(
                db_tn,
                NOW,
                "tennis",
                feed_mod.PersonalizationContext(),
                sports_mode=True,
            )
            ev_queries_tn = [s for s in db_tn.executed_pg_sql if "from events" in s]
            assert ev_queries_tn, "expected events query for tennis"
            assert "events.sport_id + " in ev_queries_tn[-1]

        engine.dispose()
