"""#13511 Item 3: Opening value validity — trade or real two-sided quote required."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.models.models import (
    FuturesOddsSnapshot,
    FuturesOutcome,
)
from app.routes.events import _game_markets_cache, get_game_markets
from app.routes.futures import _format_market_detail, get_futures_market, get_probability_timeline
from app.utils.feed_market_quality import FEED_PHANTOM_MIN_SPREAD
from app.utils.opening_quote_validity import (
    _detect_dialect_name,
    _fetch_earliest_opening_snapshots,
    _fetch_timed_opening_snapshots,
    is_real_two_sided_quote,
    is_valid_opening_trade,
    load_unsupported_opening_ids,
    opening_capture_is_supported,
    opening_snapshot_supports_opening,
)


# ---------------------------------------------------------------------------
# Event 14792841 (Michigan vs Ohio St.) — 30 recorded prediction-market
# opening values beside their capture-window order book & trade state.
# ---------------------------------------------------------------------------
EVENT_14792841_AUDIT_ROWS: tuple[tuple[int, str, float, float, float, float | None, bool], ...] = (
    # (market_id, outcome_name, open_prob, yes_bid, yes_ask, last_price_at_capture, expected_pass)
    # 72478412 — Team Receiving Touchdowns (5)
    (72478412, "Ohio St.: 3+", 0.495, 0.40, 0.59, None, True),
    (72478412, "Ohio St.: 1+", 0.80, 0.61, 0.99, 0.99, False),
    (72478412, "Ohio St.: 2+", 0.615, 0.37, 0.86, None, False),
    (72478412, "Michigan: 2+", 0.215, 0.19, 0.24, 0.24, True),
    (72478412, "Michigan: 3+", 0.18, 0.01, 0.35, None, False),
    # 72478381 — Team Rushing Yards (13)
    (72478381, "Michigan: 75+", 0.765, 0.56, 0.97, None, False),
    (72478381, "Michigan: 50+", 0.77, 0.56, 0.98, None, False),
    (72478381, "Michigan: 100+", 0.68, 0.63, 0.73, None, True),
    (72478381, "Ohio St.: 100+", 0.64, 0.59, 0.71, None, True),
    (72478381, "Michigan: 125+", 0.455, 0.25, 0.58, None, False),
    (72478381, "Michigan: 150+", 0.275, 0.22, 0.33, None, True),
    (72478381, "Ohio St.: 125+", 0.405, 0.21, 0.60, None, False),
    (72478381, "Ohio St.: 150+", 0.245, 0.18, 0.30, None, True),
    (72478381, "Ohio St.: 175+", 0.185, 0.01, 0.36, None, False),
    (72478381, "Ohio St.: 200+", 0.175, 0.01, 0.34, None, False),
    (72478381, "Ohio St.: 225+", 0.075, 0.01, 0.14, None, True),
    (72478381, "Michigan: 175+", 0.205, 0.01, 0.41, None, False),
    (72478381, "Michigan: 200+", 0.205, 0.01, 0.40, None, False),
    # 72524375 — Team Receiving Yards (12)
    (72524375, "Michigan: 50+", 0.76, 0.53, 0.99, None, False),
    (72524375, "Michigan: 75+", 0.76, 0.53, 0.99, None, False),
    (72524375, "Michigan: 100+", 0.73, 0.65, 0.79, None, True),
    (72524375, "Ohio St.: 175+", 0.745, 0.54, 0.94, None, False),
    (72524375, "Ohio St.: 200+", 0.645, 0.58, 0.72, None, True),
    (72524375, "Michigan: 125+", 0.615, 0.41, 0.83, None, False),
    (72524375, "Ohio St.: 250+", 0.36, 0.29, 0.43, None, True),
    (72524375, "Michigan: 150+", 0.405, 0.32, 0.46, None, True),
    (72524375, "Michigan: 175+", 0.335, 0.20, 0.48, None, False),
    (72524375, "Ohio St.: 275+", 0.24, 0.01, 0.46, None, False),
    (72524375, "Ohio St.: 300+", 0.15, 0.08, 0.22, None, True),
    (72524375, "Michigan: 200+", 0.16, 0.07, 0.21, None, True),
)


class _SqliteAsyncAdapter:
    """AsyncSession-compatible wrapper over an in-memory SQLite engine."""

    def __init__(self, conn):
        self._conn = conn
        self.bind = conn.engine

    async def execute(self, stmt, *args, **kwargs):
        return self._conn.execute(stmt, *args, **kwargs)


class TestOpeningQuoteValidityPredicates:
    def test_threshold_comes_from_shared_constant(self):
        assert FEED_PHANTOM_MIN_SPREAD == 0.20
        assert is_real_two_sided_quote(0.40, 0.59) is True
        assert is_real_two_sided_quote(0.40, 0.60) is False
        assert is_real_two_sided_quote(0.0, 0.10) is False
        assert is_real_two_sided_quote(0.85, 1.0) is False
        assert is_real_two_sided_quote(0.01, 0.14) is True

    def test_empty_book_midpoints_and_wide_books_are_refused(self):
        assert opening_capture_is_supported(0.00, 0.99, None, opening_probability=0.495) is False
        assert opening_capture_is_supported(0.01, 0.99, None, opening_probability=0.50) is False
        assert opening_capture_is_supported(0.05, 0.95, None, opening_probability=0.50) is False
        assert opening_capture_is_supported(0.37, 0.86, None, opening_probability=0.615) is False
        assert opening_capture_is_supported(0.01, 0.35, None, opening_probability=0.18) is False
        assert opening_capture_is_supported(0.01, 0.46, None, opening_probability=0.24) is False

    def test_wide_book_midpoint_cannot_borrow_unrelated_trade(self):
        # Ohio St.: 1+ specimen: book 0.61/0.99 (midpoint 0.80), trade at 0.99.
        assert (
            opening_capture_is_supported(0.61, 0.99, 0.99, opening_probability=0.80)
            is False
        )
        # Same book if opening actually recorded the trade price -> supported.
        assert (
            opening_capture_is_supported(0.61, 0.99, 0.99, opening_probability=0.99)
            is True
        )

    def test_real_two_sided_quote_supports_ohio_state_3plus_at_495(self):
        # 2026-11-28T00:49:04Z capture had active 0.40/0.59 quote (spread 0.19 < 0.20).
        assert (
            opening_capture_is_supported(0.40, 0.59, None, opening_probability=0.495)
            is True
        )
        assert (
            opening_capture_is_supported(0.19, 0.24, 0.24, opening_probability=0.215)
            is True
        )

    def test_ieee754_tolerance_boundary_and_refuted_trade(self):
        # 0.51 - 0.50 == 0.010000000000000009 in binary float; 6dp rounding preserves exact 0.01.
        assert is_valid_opening_trade(0.50, 0.01, 0.99) is True
        assert (
            opening_capture_is_supported(0.01, 0.99, 0.50, opening_probability=0.51)
            is True
        )
        assert (
            opening_capture_is_supported(0.01, 0.99, 0.50, opening_probability=0.52)
            is False
        )
        # Book-refuted trade: ask=0.09 refutes stale trade at 0.52.
        assert is_valid_opening_trade(0.52, 0.00, 0.09) is False
        assert (
            opening_capture_is_supported(0.00, 0.09, 0.52, opening_probability=0.52)
            is False
        )

    def test_non_orderbook_snapshot_fails_open(self):
        assert opening_snapshot_supports_opening(0.55, None, None, None) is True
        assert (
            opening_snapshot_supports_opening(
                Decimal("0.495"), Decimal("0.40"), Decimal("0.59"), None
            )
            is True
        )
        assert (
            opening_snapshot_supports_opening(
                Decimal("0.80"), Decimal("0.61"), Decimal("0.99"), Decimal("0.99")
            )
            is False
        )

    def test_event_14792841_30_outcome_audit_splits_13_pass_and_17_fail(self):
        assert len(EVENT_14792841_AUDIT_ROWS) == 30
        passed = []
        failed = []
        for market_id, outcome_name, open_p, bid, ask, last_p, expected in EVENT_14792841_AUDIT_ROWS:
            actual = opening_capture_is_supported(
                bid, ask, last_p, opening_probability=open_p
            )
            assert actual is expected, (
                f"Mismatch on {market_id} {outcome_name}: open={open_p} "
                f"book={bid}/{ask} last={last_p} expected={expected} got={actual}"
            )
            if actual:
                passed.append((market_id, outcome_name))
            else:
                failed.append((market_id, outcome_name))
        assert len(passed) == 13
        assert len(failed) == 17
        assert passed[0] == (72478412, "Ohio St.: 3+")


class TestLoaderAndRoutes:
    def test_sqlite_adapter_loads_timed_and_untimed_with_provenance_guard(self):
        import asyncio

        engine = sa.create_engine("sqlite://")
        for tbl in (
            FuturesOutcome.__table__,
            FuturesOddsSnapshot.__table__,
        ):
            tbl.create(engine)

        t_cap = datetime(2026, 11, 28, 0, 49, 4, tzinfo=timezone.utc)
        t_later = t_cap + timedelta(hours=2)
        try:
            with engine.begin() as conn:
                conn.execute(
                    sa.insert(FuturesOutcome.__table__).values(
                        [
                            # 1. Timed real quote -> SUPPORTED
                            dict(
                                id=1,
                                market_id=72478412,
                                external_id="OSU3",
                                name="Ohio St.: 3+",
                                current_probability=0.18,
                                opening_probability=0.495,
                                opening_captured_at=t_cap,
                            ),
                            # 2. Timed wide-book stub ask w/ 0.99 trade -> UNSUPPORTED
                            dict(
                                id=2,
                                market_id=72478412,
                                external_id="OSU1",
                                name="Ohio St.: 1+",
                                current_probability=0.74,
                                opening_probability=0.80,
                                opening_captured_at=t_cap,
                            ),
                            # 3. Untimed, earliest snap matches opening (0.205) on 0.01/0.41 -> UNSUPPORTED
                            dict(
                                id=3,
                                market_id=72478412,
                                external_id="MICH175",
                                name="Michigan: 175+",
                                current_probability=None,
                                opening_probability=0.205,
                                opening_captured_at=None,
                            ),
                            # 4. Untimed, earliest snap does NOT match opening -> fail-open SUPPORTED
                            dict(
                                id=4,
                                market_id=72478412,
                                external_id="UNMATCHED",
                                name="Ohio St.: 4+",
                                current_probability=0.10,
                                opening_probability=0.35,
                                opening_captured_at=None,
                            ),
                        ]
                    )
                )
                conn.execute(
                    sa.insert(FuturesOddsSnapshot.__table__).values(
                        [
                            dict(
                                id=101,
                                outcome_id=1,
                                bookmaker="consensus",
                                probability=0.495,
                                yes_bid=0.40,
                                yes_ask=0.59,
                                last_price=None,
                                captured_at=t_cap,
                            ),
                            dict(
                                id=102,
                                outcome_id=1,
                                bookmaker="consensus",
                                probability=0.18,
                                yes_bid=0.01,
                                yes_ask=0.99,
                                last_price=None,
                                captured_at=t_later,
                            ),
                            dict(
                                id=103,
                                outcome_id=2,
                                bookmaker="consensus",
                                probability=0.80,
                                yes_bid=0.61,
                                yes_ask=0.99,
                                last_price=0.99,
                                captured_at=t_cap,
                            ),
                            dict(
                                id=104,
                                outcome_id=3,
                                bookmaker="consensus",
                                probability=0.205,
                                yes_bid=0.01,
                                yes_ask=0.41,
                                last_price=None,
                                captured_at=t_cap,
                            ),
                            dict(
                                id=105,
                                outcome_id=4,
                                bookmaker="consensus",
                                probability=0.12,
                                yes_bid=0.01,
                                yes_ask=0.45,
                                last_price=None,
                                captured_at=t_cap,
                            ),
                        ]
                    )
                )

            with engine.connect() as conn:
                db = _SqliteAsyncAdapter(conn)
                outcomes = list(
                    conn.execute(sa.select(FuturesOutcome)).mappings()
                )
                ns_outcomes = [SimpleNamespace(**o) for o in outcomes]
                market = SimpleNamespace(id=72478412, source="kalshi", market_metadata=None)
                unsupported = asyncio.run(
                    load_unsupported_opening_ids(db, ns_outcomes, {72478412: market})
                )
                assert unsupported == {2, 3}
        finally:
            engine.dispose()

    def test_postgres_lateral_sql_compiles_cleanly(self):
        class _RecordingDialectDb:
            bind = SimpleNamespace(dialect=postgresql.dialect())

            def __init__(self):
                self.sqls: list[str] = []

            async def execute(self, stmt, *args, **kwargs):
                self.sqls.append(
                    str(stmt.compile(dialect=postgresql.dialect()))
                )
                res = MagicMock()
                res.all.return_value = []
                return res

        import asyncio

        db = _RecordingDialectDb()
        asyncio.run(
            _fetch_timed_opening_snapshots(
                db,
                [10],
                dialect_name="postgresql",
                FuturesOddsSnapshot=FuturesOddsSnapshot,
                FuturesOutcome=FuturesOutcome,
            )
        )
        asyncio.run(
            _fetch_earliest_opening_snapshots(
                db,
                [11],
                dialect_name="postgresql",
                FuturesOddsSnapshot=FuturesOddsSnapshot,
                FuturesOutcome=FuturesOutcome,
            )
        )
        assert len(db.sqls) == 2
        assert "LATERAL" in db.sqls[0]
        assert "INTERVAL" in db.sqls[0]
        assert "LATERAL" in db.sqls[1]

    @pytest.mark.asyncio
    async def test_mock_db_bind_fails_open_safely(self):
        # Ensures test harnesses using MagicMock AsyncSession do not treat
        # `str(bind.dialect.name)` as an unknown non-postgres dialect or crash.
        db = MagicMock()
        db.bind = MagicMock()
        outcome = SimpleNamespace(
            id=1,
            market_id=72478412,
            opening_probability=Decimal("0.495"),
            opening_captured_at=MagicMock(),
        )
        market = SimpleNamespace(id=72478412, source="kalshi", market_metadata=None)
        res = await load_unsupported_opening_ids(db, [outcome], {72478412: market})
        assert res == set()

    @pytest.mark.asyncio
    async def test_format_market_detail_partial_vs_complete_withholding(self):
        now = datetime.now(timezone.utc)
        market = SimpleNamespace(
            id=72478412,
            name="Michigan vs Ohio St.: Team Receiving Touchdowns",
            description=None,
            category="prop",
            source="kalshi",
            external_id="KXNCAAFTEAMRECTD-26NOV28MICHOSU",
            status="open",
            sport=None,
            sport_id=None,
            event_id=14792841,
            market_type="binary",
            market_tier=2,
            llm_sport_category="football",
            mutually_exclusive=False,
            commence_time=now + timedelta(hours=1),
            resolution_date=now + timedelta(hours=5),
            created_at=now - timedelta(days=1),
            updated_at=now,
            group_id=None,
            canonical_market_key=None,
            hook_description=None,
            image_url=None,
            category_tags=[],
            market_metadata=None,
            outcomes=[
                SimpleNamespace(
                    id=1,
                    market_id=72478412,
                    name="Ohio St.: 3+",
                    external_id="OSU3",
                    current_probability=0.18,
                    current_american_odds=456,
                    rank=1,
                    rank_change_24h=None,
                    probability_change_24h=None,
                    opening_probability=0.495,
                    opening_american_odds=102,
                    is_winner=None,
                    resolution_source=None,
                    last_updated=now,
                ),
                SimpleNamespace(
                    id=2,
                    market_id=72478412,
                    name="Ohio St.: 1+",
                    external_id="OSU1",
                    current_probability=0.74,
                    current_american_odds=-285,
                    rank=2,
                    rank_change_24h=None,
                    probability_change_24h=None,
                    opening_probability=0.80,
                    opening_american_odds=-400,
                    is_winner=None,
                    resolution_source=None,
                    last_updated=now,
                ),
            ],
        )

        partial = _format_market_detail(
            market,
            ["kalshi"],
            unsupported_opening_ids={2},
            normalize_numbers=False,
        )
        by_id = {o["id"]: o for o in partial["outcomes"]}
        assert by_id[1]["opening_probability"] == pytest.approx(0.495)
        assert by_id[1]["opening_american_odds"] == 102
        assert by_id[2]["opening_probability"] is None
        assert by_id[2]["opening_american_odds"] is None
        assert partial["openings_withheld"] is False

        total_withheld = _format_market_detail(
            market,
            ["kalshi"],
            unsupported_opening_ids={1, 2},
            normalize_numbers=False,
        )
        assert all(o["opening_probability"] is None for o in total_withheld["outcomes"])
        assert all(o["opening_american_odds"] is None for o in total_withheld["outcomes"])
        assert total_withheld["openings_withheld"] is True

    @pytest.mark.asyncio
    async def test_game_markets_and_futures_routes_withhold_unsupported_openings(self):
        t_cap = datetime(2026, 11, 28, 0, 49, 4, tzinfo=timezone.utc)
        now = t_cap + timedelta(hours=3)
        event = SimpleNamespace(
            id=14792841,
            sport=SimpleNamespace(id=1, key="americanfootball_ncaaf", name="NCAAF"),
            sport_id=1,
            home_team_name="Michigan Wolverines",
            away_team_name="Ohio State Buckeyes",
            home_team=None,
            away_team=None,
            home_team_id=10,
            away_team_id=11,
            commence_time=now + timedelta(hours=1),
            commence_time_source="espn",
            status="scheduled",
            home_score=None,
            away_score=None,
            completed_at=None,
            statpal_end_time=None,
            period=None,
            game_clock=None,
            box_score_data=None,
            win_probability_sources=None,
            ei_metadata=None,
            event_tags=[],
            espn_id="401628492",
            external_id="evt-14792841",
        )
        outcomes = [
            SimpleNamespace(
                id=9001,
                market_id=72478412,
                name="Ohio St.: 3+",
                external_id="OSU3",
                current_probability=Decimal("0.1800"),
                current_american_odds=456,
                current_yes_bid=Decimal("0.17"),
                current_yes_ask=Decimal("0.19"),
                opening_probability=Decimal("0.4950"),
                opening_american_odds=102,
                opening_captured_at=t_cap,
                rank=1,
                rank_change_24h=None,
                probability_change_24h=Decimal("-0.3150"),
                is_winner=None,
                resolution_source=None,
                last_updated=now,
                price_changed_at=now,
                market=None,
                team=None,
                team_id=None,
            ),
            SimpleNamespace(
                id=9002,
                market_id=72478412,
                name="Ohio St.: 1+",
                external_id="OSU1",
                current_probability=Decimal("0.7400"),
                current_american_odds=-285,
                current_yes_bid=Decimal("0.72"),
                current_yes_ask=Decimal("0.76"),
                opening_probability=Decimal("0.8000"),
                opening_american_odds=-400,
                opening_captured_at=t_cap,
                rank=2,
                rank_change_24h=None,
                probability_change_24h=Decimal("-0.0600"),
                is_winner=None,
                resolution_source=None,
                last_updated=now,
                price_changed_at=now,
                market=None,
                team=None,
                team_id=None,
            ),
        ]
        market = SimpleNamespace(
            id=72478412,
            event_id=14792841,
            sport=event.sport,
            sport_id=1,
            source="kalshi",
            external_id="KXNCAAFTEAMRECTD-26NOV28MICHOSU",
            name="Michigan vs Ohio St.: Team Receiving Touchdowns",
            description=None,
            category="prop",
            status="open",
            market_type="player_prop",
            market_tier=2,
            llm_sport_category="football",
            mutually_exclusive=False,
            commence_time=event.commence_time,
            resolution_date=event.commence_time + timedelta(hours=4),
            created_at=t_cap - timedelta(days=1),
            updated_at=now,
            settled_at=None,
            group_id=None,
            canonical_market_key=None,
            hook_description=None,
            image_url=None,
            category_tags=[],
            market_metadata=None,
            outcomes=outcomes,
        )
        for o in outcomes:
            o.market = market

        _game_markets_cache.clear()
        try:
            with (
                patch(
                    "app.routes.events.load_unsupported_opening_ids",
                    new=AsyncMock(return_value={9002}),
                ),
                patch(
                    "app.utils.latest_observation.load_latest_observed_at",
                    new=AsyncMock(return_value={9001: now, 9002: now}),
                ),
            ):
                class _GameMarketsDb:
                    async def scalar(self, stmt, *a, **kw):
                        return None

                    async def execute(self, stmt, *a, **kw):
                        r = MagicMock()
                        s = str(stmt).lower()
                        if "from events" in s:
                            r.scalar_one_or_none.return_value = event
                        elif "from futures_markets" in s and "polymarket_sub_market" not in s:
                            r.scalars.return_value.all.return_value = [market]
                        elif "from futures_outcomes" in s:
                            r.scalars.return_value.all.return_value = list(outcomes)
                        else:
                            r.all.return_value = []
                            r.scalars.return_value.all.return_value = []
                            r.scalar_one_or_none.return_value = None
                        return r

                gm = await get_game_markets(14792841, db=_GameMarketsDb())
        finally:
            _game_markets_cache.clear()

        props = gm["player_props"]
        assert props
        all_items = []
        for p in props:
            if isinstance(p.get("outcomes"), list):
                all_items.extend(p["outcomes"])
            else:
                all_items.append(p)
        by_name = {item.get("name") or item.get("outcome_name"): item for item in all_items}
        osu3 = by_name["Ohio St.: 3+"]
        osu1 = by_name["Ohio St.: 1+"]
        assert osu3["opening_over_probability"] == pytest.approx(0.495)
        assert osu3["pregame_mark"] == pytest.approx(0.495)
        assert osu3["movement"] == pytest.approx(-0.315)
        assert osu1["opening_over_probability"] is None
        assert osu1["pregame_mark"] is None
        assert osu1["movement"] is None
        # Stored ORM DB row was NOT mutated (read-side rule, gotcha #21 / #144).
        assert outcomes[1].opening_probability == Decimal("0.8000")

        # Verify futures routes call `load_unsupported_opening_ids` in both detail and history.
        mock_loader = AsyncMock(return_value={9002})
        with (
            patch("app.routes.futures.load_unsupported_opening_ids", mock_loader),
            patch("app.routes.futures._load_market_sources", new=AsyncMock(return_value=(["kalshi"], []))),
            patch("app.routes.futures._withheld_price_outcome_ids", new=AsyncMock(return_value=set())),
            patch("app.routes.futures._fleet_newest_observation", new=AsyncMock(return_value=now)),
            patch("app.routes.futures._game_container_leg_sides", new=AsyncMock(return_value={})),
            patch("app.routes.futures._game_container_lead_leg", new=AsyncMock(return_value=None)),
            patch("app.routes.futures.out_legs_by_market", new=AsyncMock(return_value={})),
            patch("app.routes.futures.grammy_nominee_fields", new=AsyncMock(return_value={})),
            patch("app.routes.futures.grammy_pre_nomination_board", new=AsyncMock(return_value=None)),
        ):
            class _FuturesDb:
                async def execute(self, stmt, *a, **kw):
                    r = MagicMock()
                    r.scalar_one_or_none.return_value = market
                    r.all.return_value = []
                    r.scalars.return_value.all.return_value = []
                    return r

            detail = await get_futures_market(
                72478412, db=_FuturesDb(), representation="source"
            )

        detail_by_id = {o["id"]: o for o in detail["outcomes"]}
        assert detail_by_id[9001]["opening_probability"] == pytest.approx(0.495)
        assert detail_by_id[9002]["opening_probability"] is None
        assert detail_by_id[9002]["opening_american_odds"] is None
        assert detail["openings_withheld"] is False
        assert mock_loader.await_count == 1
        assert callable(get_probability_timeline)

    @pytest.mark.asyncio
    async def test_sync_as_async_wrapper_detects_sqlite_dialect_and_runs_portable_query(self):
        from sqlalchemy.orm import Session

        engine = sa.create_engine("sqlite:///:memory:")
        try:
            FuturesOutcome.__table__.create(engine)
            FuturesOddsSnapshot.__table__.create(engine)
            t_cap = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)
            with Session(engine) as s:
                s.execute(
                    sa.insert(FuturesOutcome).values(
                        [
                            dict(
                                id=11,
                                market_id=8801,
                                external_id="K-EMPTY",
                                name="Yes",
                                current_probability=0.50,
                                opening_probability=0.495,
                                opening_captured_at=t_cap,
                            ),
                            dict(
                                id=12,
                                market_id=8801,
                                external_id="K-TIGHT",
                                name="No",
                                current_probability=0.50,
                                opening_probability=0.50,
                                opening_captured_at=t_cap,
                            ),
                        ]
                    )
                )
                s.execute(
                    sa.insert(FuturesOddsSnapshot).values(
                        [
                            dict(
                                id=201,
                                outcome_id=11,
                                bookmaker="consensus",
                                probability=0.495,
                                yes_bid=0.0,
                                yes_ask=0.99,
                                last_price=None,
                                captured_at=t_cap,
                            ),
                            dict(
                                id=202,
                                outcome_id=12,
                                bookmaker="consensus",
                                probability=0.50,
                                yes_bid=0.48,
                                yes_ask=0.52,
                                last_price=None,
                                captured_at=t_cap,
                            ),
                        ]
                    )
                )
                s.commit()

                class _SyncAsAsync:
                    def __init__(self, session):
                        self._session = session

                    async def execute(self, statement):
                        return self._session.execute(statement)

                wrapper = _SyncAsAsync(s)
                assert _detect_dialect_name(wrapper) == "sqlite"
                outcomes = list(s.execute(sa.select(FuturesOutcome)).scalars().all())
                market = SimpleNamespace(id=8801, source="kalshi", market_metadata=None)
                unsupported = await load_unsupported_opening_ids(
                    wrapper, outcomes, {8801: market}
                )
                assert unsupported == {11}
        finally:
            engine.dispose()

    @pytest.mark.asyncio
    async def test_finite_async_mock_side_effect_exhaustion_is_caught(self):
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[])
        outcomes = [
            SimpleNamespace(
                id=31,
                market_id=8802,
                opening_probability=Decimal("0.495"),
                opening_captured_at=datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc),
            ),
            SimpleNamespace(
                id=32,
                market_id=8802,
                opening_probability=Decimal("0.50"),
                opening_captured_at=None,
            ),
        ]
        market = SimpleNamespace(
            id=8802,
            source="kalshi",
            market_metadata={"unpriced_opening_ids": [32]},
        )
        unsupported = await load_unsupported_opening_ids(db, outcomes, {8802: market})
        assert unsupported == {32}
        assert db.execute.await_count == 1
