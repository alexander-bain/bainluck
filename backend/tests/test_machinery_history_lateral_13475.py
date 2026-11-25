"""Unit tests for #13475 item 4: per-outcome LATERAL newest-96 snapshot query."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from app.utils.container_machinery import (
    _build_machinery_history_lateral_stmt,
    _load_snapshot_from_db,
)


def test_build_machinery_history_lateral_stmt_compiles_with_lateral_limit_and_no_window() -> None:
    cutoff = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(hours=168)
    stmt = _build_machinery_history_lateral_stmt([101, 202, 101], cutoff)
    compiled = str(
        stmt.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    low = compiled.lower()
    assert "lateral" in low
    assert "limit 96" in low
    assert "row_number" not in low
    assert "over (" not in low
    assert "want_outcomes" in low
    assert "order by" in low


def test_build_machinery_history_lateral_stmt_handles_empty_outcomes() -> None:
    cutoff = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(hours=168)
    stmt = _build_machinery_history_lateral_stmt([], cutoff)
    compiled = str(stmt.compile(dialect=postgresql.dialect()))
    assert "futures_odds_snapshots" in compiled.lower()
    assert "row_number" not in compiled.lower()


@pytest.mark.asyncio
async def test_load_snapshot_from_db_executes_lateral_history_and_collects_points(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_dt = datetime.now(timezone.utc).replace(microsecond=0)
    defn = {
        "slug": "machinery-fed-and-macro",
        "name": "Fed & U.S. Macro",
        "kind": "roundup",
        "rule": {
            "producer": "container_machinery",
            "sections": [
                {
                    "key": "rate_history",
                    "title": "FOMC Moves",
                    "atom_query": {
                        "kind": "market_history",
                        "any_tokens": ["fed decision"],
                        "max_items": 2,
                        "max_outcomes": 3,
                        "hours": 168,
                    },
                }
            ],
        },
    }

    fake_outcomes = [
        SimpleNamespace(
            id=501,
            name="Hold",
            current_probability=Decimal("0.72"),
            implied_probability=Decimal("0.72"),
            opening_probability=None,
            image_url=None,
            last_updated=now_dt,
            is_winner=None,
            resolution_source=None,
            volume_24h=100,
            volume_24h_at=now_dt,
        ),
        SimpleNamespace(
            id=502,
            name="Cut 25",
            current_probability=Decimal("0.28"),
            implied_probability=Decimal("0.28"),
            opening_probability=None,
            image_url=None,
            last_updated=now_dt,
            is_winner=None,
            resolution_source=None,
            volume_24h=100,
            volume_24h_at=now_dt,
        ),
    ]
    fm = SimpleNamespace(
        id=9001,
        name="Fed Decision in Dec",
        title="Fed Decision in Dec",
        category="economics",
        llm_sport_category="economics",
        status="open",
        source="kalshi",
        external_id="KXFEDDEC-26DEC",
        mutually_exclusive=True,
        market_type="field",
        volume=10000,
        volume_24h=1500,
        liquidity=5000,
        image_url=None,
        close_time=now_dt + timedelta(days=30),
        commence_time=now_dt + timedelta(days=30),
        settlement_date=now_dt + timedelta(days=30),
        end_date=now_dt + timedelta(days=30),
        outcomes=fake_outcomes,
    )

    executed_sql: list[str] = []

    class _Res:
        def __init__(self, rows):
            self._rows = rows

        def unique(self):
            return self

        def scalars(self):
            return self

        def all(self):
            return list(self._rows)

    class _FakeDB:
        def __init__(self):
            self.calls = 0

        async def execute(self, stmt):
            self.calls += 1
            sql = str(stmt.compile(dialect=postgresql.dialect())).lower()
            executed_sql.append(sql)
            if "lateral" in sql:
                return _Res(
                    [
                        (501, now_dt - timedelta(hours=10), Decimal("0.68")),
                        (501, now_dt - timedelta(hours=1), Decimal("0.72")),
                    ]
                )
            if self.calls == 1:
                return _Res([(9001, "Fed Decision in Dec", 1500.0)])
            if self.calls == 2:
                return _Res([fm])
            return _Res([])

    async def _fake_batched_withheld(db, markets):
        return {m.id: set() for m in markets}

    async def _fake_fleet(db, fm_arg):
        return now_dt

    async def _fake_out_legs(markets):
        return {}

    async def _fake_vt(db, fm_arg):
        return SimpleNamespace(reason="not_a_title_question")

    def _fake_format(fm_arg, *_args, **_kwargs):
        return {
            "outcomes": [
                {"id": o.id, "name": o.name, "probability": float(o.current_probability)}
                for o in fm_arg.outcomes
            ]
        }

    monkeypatch.setattr(
        "app.routes.futures.withheld_price_outcome_ids_for_markets",
        _fake_batched_withheld,
    )
    monkeypatch.setattr("app.routes.futures._fleet_newest_observation", _fake_fleet)
    monkeypatch.setattr("app.routes.futures.out_legs_by_market", _fake_out_legs)
    monkeypatch.setattr("app.routes.futures._resolve_verified_title", _fake_vt)
    monkeypatch.setattr("app.routes.futures._format_market_detail", _fake_format)
    monkeypatch.setattr(
        "app.routes.futures._apply_verified_title_to_detail", lambda d, v, fm_arg, **kwargs: None
    )

    snapshot = await _load_snapshot_from_db(_FakeDB(), defn, now_dt)
    assert any("lateral" in s for s in executed_sql)
    assert snapshot["market_histories"][501] == [
        {"timestamp": (now_dt - timedelta(hours=10)).isoformat(), "probability": 0.68},
        {"timestamp": (now_dt - timedelta(hours=1)).isoformat(), "probability": 0.72},
    ]
