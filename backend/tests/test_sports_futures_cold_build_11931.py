"""#11931 — Sports futures cold-build query cuts (zero behavior change).

Live `feed_stage_observability` on `mode=sports` showed two avoidable DB costs
inside `_score_sports_mode_futures` (even under `max_shared_age_scope(0.0)`):
1. `graded_out_leg_ids_by_market` (`sports_futures.out_legs`, up to 2.02 s)
   re-queried `futures_outcomes` for `is_winner` and `resolution_source`, even
   though `load_sports_markets` / `_futures_feed_load_options` already loaded
   both columns via `OUTCOME_LOAD_ONLY_EXTRA`.
2. `withheld_price_outcome_ids_for_markets` (`sports_futures.withheld`, up to
   2.15 s) queried the 51 GB `futures_odds_snapshots` table TWICE for
   `bookmaker='kalshi'` whenever a pool had both Kalshi unsupported-price and
   Kalshi wide-book midpoint candidates.

This test pins:
- Zero SQL queries in `graded_out_leg_ids_by_market` when real SQLAlchemy
  `FuturesOutcome` rows already have `is_winner` + `resolution_source` loaded
  via `load_only(...)`, with identical verdicts to the DB-backed path.
- Deferred `load_only` rows (missing `is_winner` / `resolution_source`) and
  snapshot legs fall through to the DB query cleanly; mixed pools query ONLY
  the unloaded legs and merge both sets.
- `withheld_price_outcome_ids_for_markets` merges overlapping Kalshi trade and
  midpoint reads into ONE `futures_odds_snapshots` query, deduplicates IDs, and
  matches per-market `_withheld_price_outcome_ids` verdicts identically on
  `None`-only, `None` + float, and multi-float trade rows.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, load_only

from app.models.models import Base, FuturesMarket, FuturesOutcome
from app.routes import futures as futures_route
from app.utils import graded_out_field_legs as graded_mod


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


class _ForbiddenDB:
    async def execute(self, statement):
        raise AssertionError(f"Expected zero DB queries, got: {statement}")


class _RecordingAsyncShim:
    def __init__(self, session):
        self._s = session
        self.queries = 0

    async def execute(self, statement):
        self.queries += 1
        return self._s.execute(statement)


def _seed_outcomes(rows: list[tuple[int, int, str, float, bool, str | None]]):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine, tables=[FuturesMarket.__table__, FuturesOutcome.__table__]
    )
    s = Session(engine, expire_on_commit=False)
    for oid, mid, name, prob, is_winner, source in rows:
        s.add(
            FuturesOutcome(
                id=oid,
                market_id=mid,
                external_id=f"o-{oid}",
                name=name,
                current_probability=prob,
                is_winner=is_winner,
                resolution_source=source,
            )
        )
    s.commit()
    return s


class TestGradedOutInMemoryFastPath:
    def test_loaded_orm_outcomes_grade_with_zero_db_queries(self):
        s = _seed_outcomes(
            [
                (501, 88, "AliveFav", 0.55, False, None),
                (502, 88, "Eliminated", 0.005, False, "api_settlement"),
                (503, 88, "GuessOnly", 0.01, False, "llm_guess"),
                (504, 88, "Retracted", 0.01, False, "ungradeable_result"),
                (505, 88, "WinnerLow", 0.01, True, "api_settlement"),
                (506, 88, "LiveContender", 0.25, False, "api_settlement"),
                (507, 88, "DefaultedFalse", 0.01, False, None),
            ]
        )

        loaded_outcomes = (
            s.execute(
                select(FuturesOutcome)
                .options(
                    load_only(
                        FuturesOutcome.id,
                        FuturesOutcome.current_probability,
                        FuturesOutcome.is_winner,
                        FuturesOutcome.resolution_source,
                    )
                )
                .where(FuturesOutcome.market_id == 88)
            )
            .scalars()
            .all()
        )
        board = SimpleNamespace(
            id=88, status="open", market_type="field", outcomes=loaded_outcomes
        )
        got = asyncio.run(
            graded_mod.graded_out_leg_ids_by_market(_ForbiddenDB(), [board])
        )
        assert got == {88: frozenset({502})}

    def test_deferred_orm_outcomes_fall_back_to_db_without_lazy_load(self):
        s = _seed_outcomes(
            [
                (601, 200, "OutDeferred", 0.01, False, "api_settlement"),
                (602, 200, "AliveDeferred", 0.02, False, None),
            ]
        )
        # Load WITHOUT is_winner / resolution_source (simulates deferred columns).
        deferred_outcomes = (
            s.execute(
                select(FuturesOutcome)
                .options(
                    load_only(FuturesOutcome.id, FuturesOutcome.current_probability)
                )
                .where(FuturesOutcome.market_id == 200)
            )
            .scalars()
            .all()
        )
        shim = _RecordingAsyncShim(s)
        board = SimpleNamespace(
            id=200, status="open", market_type="field", outcomes=deferred_outcomes
        )
        got = asyncio.run(graded_mod.graded_out_leg_ids_by_market(shim, [board]))
        assert got == {200: frozenset({601})}
        assert shim.queries == 1

    def test_mixed_loaded_orm_and_snapshot_pool_queries_only_snapshot_legs(self):
        s = _seed_outcomes(
            [
                (701, 100, "LoadedOut", 0.01, False, "api_settlement"),
                (601, 200, "SnapshotOut", 0.01, False, "api_settlement"),
                (602, 200, "SnapshotAlive", 0.02, False, None),
            ]
        )
        loaded_outcomes = (
            s.execute(
                select(FuturesOutcome)
                .options(
                    load_only(
                        FuturesOutcome.id,
                        FuturesOutcome.current_probability,
                        FuturesOutcome.is_winner,
                        FuturesOutcome.resolution_source,
                    )
                )
                .where(FuturesOutcome.market_id == 100)
            )
            .scalars()
            .all()
        )
        shim = _RecordingAsyncShim(s)
        loaded_board = SimpleNamespace(
            id=100, status="open", market_type="field", outcomes=loaded_outcomes
        )
        snapshot_board = SimpleNamespace(
            id=200,
            status="open",
            market_type="field",
            outcomes=[
                SimpleNamespace(id=601, current_probability=0.01),
                SimpleNamespace(id=602, current_probability=0.02),
            ],
        )

        got = asyncio.run(
            graded_mod.graded_out_leg_ids_by_market(shim, [loaded_board, snapshot_board])
        )
        assert got == {100: frozenset({701}), 200: frozenset({601})}
        assert shim.queries == 1


class TestWithheldKalshiSingleQueryUnion:
    @staticmethod
    def _kalshi_board(mid: int, legs: list):
        return SimpleNamespace(
            id=mid,
            source="kalshi",
            external_id=f"KXTEST-{mid}",
            market_type="field",
            market_metadata={"shape": {"expected_winners": 1}},
            outcomes=legs,
        )

    @staticmethod
    def _polymarket_board(mid: int, legs: list):
        return SimpleNamespace(
            id=mid,
            source="polymarket",
            external_id=f"pm-{mid}",
            market_type="field",
            market_metadata={},
            outcomes=legs,
        )

    @staticmethod
    def _leg(oid: int, name: str, prob: float, *, bid: float, ask: float):
        return SimpleNamespace(
            id=oid,
            name=name,
            current_probability=Decimal(str(prob)),
            current_yes_bid=Decimal(str(bid)),
            current_yes_ask=Decimal(str(ask)),
            resolution_source=None,
            volume_24h=None,
            volume_24h_at=None,
            is_winner=False,
            last_updated=None,
        )

    def test_kalshi_unsupported_and_midpoint_arms_issue_one_query_matching_per_market(
        self, monkeypatch
    ):
        # 1c/99c Kalshi legs trigger BOTH `_unsupported_price_candidates` AND
        # `_refuted_midpoint_candidates`. Previously that ran 2 separate
        # `futures_odds_snapshots` joins for `bookmaker='kalshi'`.
        b1 = self._kalshi_board(
            1,
            [
                self._leg(11, "NoTrade", 0.50, bid=0.01, ask=0.99),
                self._leg(12, "TradedMid", 0.45, bid=0.05, ask=0.85),
                self._leg(13, "TradedFar", 0.45, bid=0.05, ask=0.85),
                self._leg(14, "CleanFav", 0.60, bid=0.59, ask=0.61),
            ],
        )
        b2 = self._polymarket_board(
            2,
            [
                self._leg(21, "PolyWide", 0.50, bid=0.01, ask=0.99),
                self._leg(22, "PolyTight", 0.50, bid=0.49, ask=0.51),
            ],
        )

        kalshi_snapshot_rows = [
            (11, None),
            (12, None),
            (12, Decimal("0.45")),
            (13, Decimal("0.04")),
            (13, Decimal("0.06")),
        ]
        poly_snapshot_rows = [(21, Decimal("0.02"))]

        calls: list[tuple[str, str, list[int]]] = []

        async def fake_kalshi_trades(_db, oids):
            calls.append(("kalshi_max", "kalshi", list(oids)))
            out: dict = {}
            for oid, price in kalshi_snapshot_rows:
                if oid not in oids:
                    continue
                if oid not in out or (
                    price is not None and (out[oid] is None or price > out[oid])
                ):
                    out[oid] = price
            return out

        async def fake_venue_rows(_db, venue, oids):
            calls.append(("venue_rows", venue, list(oids)))
            src = kalshi_snapshot_rows if venue == "kalshi" else poly_snapshot_rows
            return [(oid, p) for oid, p in src if oid in oids]

        monkeypatch.setattr(futures_route, "_newest_kalshi_trades", fake_kalshi_trades)
        monkeypatch.setattr(futures_route, "_newest_venue_trade_rows", fake_venue_rows)

        batched = asyncio.run(
            futures_route.withheld_price_outcome_ids_for_markets(None, [b1, b2])
        )

        # Exactly 1 Kalshi query (merged union) + 1 Polymarket query = 2 total,
        # never 3, with sorted deduplicated IDs.
        assert calls == [
            ("venue_rows", "kalshi", [11, 12, 13]),
            ("venue_rows", "polymarket", [21]),
        ]

        # Parity check against the single-market per-page path for both boards.
        per_b1 = asyncio.run(futures_route._withheld_price_outcome_ids(None, b1))
        per_b2 = asyncio.run(futures_route._withheld_price_outcome_ids(None, b2))
        assert batched[1] == per_b1
        assert batched[2] == per_b2
        assert 11 in batched[1] and 13 in batched[1] and 12 not in batched[1]
        assert batched[2] == {21}

    def test_kalshi_only_unsupported_without_midpoint_keeps_kalshi_max_path(
        self, monkeypatch
    ):
        b = self._kalshi_board(
            3,
            [self._leg(31, "ThinAsk", 0.50, bid=0.0, ask=0.99)],
        )
        monkeypatch.setattr(
            futures_route, "_refuted_midpoint_candidates", lambda _m: []
        )

        calls: list[tuple[str, list[int]]] = []

        async def fake_kalshi_trades(_db, oids):
            calls.append(("kalshi_max", list(oids)))
            return {31: None}

        async def fake_venue_rows(_db, venue, oids):
            calls.append((f"venue:{venue}", list(oids)))
            return []

        monkeypatch.setattr(futures_route, "_newest_kalshi_trades", fake_kalshi_trades)
        monkeypatch.setattr(futures_route, "_newest_venue_trade_rows", fake_venue_rows)

        got = asyncio.run(
            futures_route.withheld_price_outcome_ids_for_markets(None, [b])
        )
        assert calls == [("kalshi_max", [31])]
        assert 31 in got[3]
