"""#11947: fresh trading evidence retracts a false settlement, never a grade.

Execute the repair's SQL on SQLite, as the #3780 template does. SQLite lacks
row locks, so the adapter omits FOR UPDATE; these tests cover the predicates,
transactions and interleaved state changes, not Postgres lock scheduling.
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine, text

from scripts import repair_11947_clock_settled_kalshi_markets_still_trading as repair


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch):
    monkeypatch.setattr(
        repair, "utc_now", lambda: datetime(2026, 11, 4, tzinfo=timezone.utc)
    )


class Session:
    def __init__(self, connection):
        self.connection = connection

    async def execute(self, statement, params=None):
        if str(statement).endswith(" FOR UPDATE"):
            statement = text(str(statement).removesuffix(" FOR UPDATE"))
        return self.connection.execute(statement, params or {})

    async def commit(self):
        self.connection.commit()

    async def rollback(self):
        self.connection.rollback()


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    with engine.connect() as connection:
        connection.execute(
            text(
                "CREATE TABLE futures_markets (id INTEGER PRIMARY KEY, name TEXT, "
                "source TEXT, external_id TEXT, status TEXT, settled_at TEXT, "
                "resolution_date TEXT DEFAULT '2026-11-03T15:00:00+00:00')"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE futures_outcomes (id INTEGER PRIMARY KEY, market_id INTEGER, "
                "name TEXT, external_id TEXT, is_winner BOOLEAN, resolution_source TEXT, "
                "current_probability NUMERIC, last_updated TEXT)"
            )
        )
        connection.execute(
            text(
                f"CREATE TABLE {repair.BACKUP_TABLE} (market_id INTEGER PRIMARY KEY, before_json TEXT)"
            )
        )
        # Refusals precede the subject, including a completely empty eligible page.
        for market_id in range(1, 8):
            source = "polymarket" if market_id == 6 else "kalshi"
            status = "open" if market_id == 4 else "resolved"
            settled_at = None if market_id == 5 else "2026-11-03T20:16:37Z"
            connection.execute(
                text(
                    "INSERT INTO futures_markets (id, name, source, external_id, status, settled_at) "
                    "VALUES (:id, 'control', :source, 'CONTROL', :status, :settled)"
                ),
                {
                    "id": market_id,
                    "source": source,
                    "status": status,
                    "settled": settled_at,
                },
            )
            if market_id != 7:
                connection.execute(
                    text(
                        "INSERT INTO futures_outcomes VALUES (:id, :id, 'Yes', 'CONTROL', :winner, :source, .58, 'old')"
                    ),
                    {
                        "id": market_id,
                        "winner": market_id == 3,
                        "source": (
                            "api_settlement"
                            if market_id == 2
                            else None if market_id == 1 else "ungradeable_result"
                        ),
                    },
                )
        connection.execute(
            text(
                "INSERT INTO futures_markets (id, name, source, external_id, status, settled_at) VALUES "
                "(109918, 'Democrats sweep', 'kalshi', 'SWEEP', 'resolved', '2026-11-03T20:16:37Z')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO futures_outcomes VALUES "
                "(1601726, 109918, 'Yes', 'SWEEP', FALSE, 'ungradeable_result', .575, '2026-11-03T08:55:57Z')"
            )
        )
        connection.commit()
        yield Session(connection)
    engine.dispose()


def trading(ticker):
    return {
        "ticker": ticker,
        "status": "active",
        "result": "",
        "close_time": "2027-11-03T15:00:00Z",
    }


@pytest.mark.asyncio
async def test_census_has_the_subject_and_refuses_every_control_even_across_empty_pages(
    db, monkeypatch
):
    monkeypatch.setattr(repair, "PAGE_SIZE", 1)
    population = await repair.census(db)
    assert [row["market"]["id"] for row in population] == [109918]
    assert population[0]["market"]["name"] == "Democrats sweep"


@pytest.mark.asyncio
async def test_default_dry_run_reads_the_exact_venue_ticker_and_writes_nothing(db):
    before = await repair.snapshot(db, 109918)
    read = AsyncMock(side_effect=trading)
    result = await repair.repair_market(db, 109918, read)
    assert result["verdict"] == "would_reopen"
    read.assert_awaited_once_with("SWEEP")
    assert await repair.snapshot(db, 109918) == before
    assert (
        db.connection.execute(
            text(f"SELECT count(*) FROM {repair.BACKUP_TABLE}")
        ).scalar()
        == 0
    )


@pytest.mark.parametrize(
    "record",
    [
        None,
        {"ticker": "OTHER", "status": "active", "result": ""},
        {"ticker": "SWEEP", "status": "finalized", "result": ""},
        {"ticker": "SWEEP", "status": "closed", "result": ""},
        {"ticker": "SWEEP", "status": "active", "result": "no"},
        {"ticker": "SWEEP", "status": "active"},
    ],
)
@pytest.mark.asyncio
async def test_absent_or_contradictory_venue_evidence_never_reopens(db, record):
    before = await repair.snapshot(db, 109918)
    result = await repair.repair_market(
        db, 109918, AsyncMock(return_value=record), apply=True
    )
    assert result["verdict"] != "reopened"
    assert await repair.snapshot(db, 109918) == before


@pytest.mark.asyncio
async def test_apply_banks_the_before_state_and_preserves_the_real_price_and_clock(db):
    before = await repair.snapshot(db, 109918)
    result = await repair.repair_market(
        db, 109918, AsyncMock(side_effect=trading), apply=True
    )
    assert result["verdict"] == "reopened"
    market, legs = await repair.snapshot(db, 109918)
    assert (market["status"], market["settled_at"]) == ("open", None)
    assert repair.instant(market["resolution_date"]) == datetime(
        2027, 11, 3, 15, tzinfo=timezone.utc
    )
    assert (legs[0]["is_winner"], legs[0]["resolution_source"]) == (None, None)
    for key in ("current_probability", "last_updated"):
        assert legs[0][key] == before[1][0][key]
    banked = json.loads(
        db.connection.execute(
            text(
                f"SELECT before_json FROM {repair.BACKUP_TABLE} WHERE market_id=109918"
            )
        ).scalar()
    )
    assert banked["market"]["status"] == "resolved"
    assert banked["market"]["resolution_date"] == before[0]["resolution_date"]
    assert banked["legs"][0]["resolution_source"] == "ungradeable_result"
    again = await repair.repair_market(
        db, 109918, AsyncMock(side_effect=trading), apply=True
    )
    assert again["verdict"] == "no_longer_eligible"


@pytest.mark.asyncio
async def test_a_venue_grade_arriving_after_the_read_is_never_erased(db):
    async def newly_graded(ticker):
        db.connection.execute(
            text(
                "UPDATE futures_outcomes SET is_winner=TRUE, resolution_source='api_settlement' WHERE id=1601726"
            )
        )
        db.connection.commit()
        return trading(ticker)

    result = await repair.repair_market(db, 109918, newly_graded, apply=True)
    assert result["verdict"] == "concurrent_drift"
    market, legs = await repair.snapshot(db, 109918)
    assert market["status"] == "resolved"
    assert (legs[0]["is_winner"], legs[0]["resolution_source"]) == (1, "api_settlement")


@pytest.mark.asyncio
async def test_a_new_leg_requires_its_own_fresh_venue_read(db):
    async def extra_leg(ticker):
        db.connection.execute(
            text(
                "INSERT INTO futures_outcomes VALUES "
                "(1601727, 109918, 'New', 'NEW', FALSE, 'ungradeable_result', .2, 'old')"
            )
        )
        db.connection.commit()
        return trading(ticker)

    result = await repair.repair_market(db, 109918, extra_leg, apply=True)
    assert result["verdict"] == "concurrent_drift"
    assert (await repair.snapshot(db, 109918))[0]["status"] == "resolved"


@pytest.mark.asyncio
async def test_a_network_error_never_becomes_trading_evidence(db):
    before = await repair.snapshot(db, 109918)
    with pytest.raises(RuntimeError, match="offline"):
        await repair.repair_market(
            db, 109918, AsyncMock(side_effect=RuntimeError("offline")), apply=True
        )
    assert await repair.snapshot(db, 109918) == before


@pytest.mark.asyncio
async def test_scoped_census_names_only_reviewed_ids(db):
    db.connection.execute(
        text(
            "INSERT INTO futures_markets (id, name, source, external_id, status, settled_at) VALUES "
            "(109919, 'Another candidate', 'kalshi', 'OTHER', 'resolved', '2026-11-03T20:16:37Z')"
        )
    )
    db.connection.execute(
        text(
            "INSERT INTO futures_outcomes VALUES "
            "(1601727, 109919, 'Yes', 'OTHER', FALSE, 'ungradeable_result', .2, 'old')"
        )
    )
    db.connection.commit()
    population = await repair.census(db, {109919})
    assert [row["market"]["id"] for row in population] == [109919]


def test_cli_defaults_to_dry_run(monkeypatch):
    run = AsyncMock(return_value=0)
    monkeypatch.setattr(repair, "run", run)
    monkeypatch.setattr("sys.argv", ["repair_11947"])
    with pytest.raises(SystemExit) as exited:
        repair.main()
    assert exited.value.code == 0
    run.assert_awaited_once_with(
        apply=False, census_only=False, only_ids=None, refresh_close_time=False
    )


@pytest.mark.parametrize(
    "close_time", [None, "garbage", "2027-11-03T15:00:00", "2026-11-03T15:00:00Z"]
)
@pytest.mark.asyncio
async def test_a_missing_invalid_or_past_venue_cutoff_cannot_reopen_a_frozen_market(
    db, close_time
):
    before = await repair.snapshot(db, 109918)
    result = await repair.repair_market(
        db,
        109918,
        AsyncMock(return_value={**trading("SWEEP"), "close_time": close_time}),
        apply=True,
    )
    assert result["verdict"] == "venue_close_time_not_future"
    assert await repair.snapshot(db, 109918) == before
    assert await repair.read_backup(db, 109918) is None


def legacy_reopen(db, *, bank=True):
    """The deployed first repair's state: grading retracted, cutoff unchanged."""
    market, legs = (
        db.connection.execute(text(repair.READ_MARKET), {"id": 109918})
        .mappings()
        .one(),
        db.connection.execute(text(repair.READ_LEGS), {"id": 109918}).mappings().all(),
    )
    before = {"market": dict(market), "legs": [dict(leg) for leg in legs]}
    # The original version banked no resolution_date field.
    before["market"].pop("resolution_date")
    if bank:
        db.connection.execute(
            text(f"INSERT INTO {repair.BACKUP_TABLE} VALUES (109918, :before)"),
            {"before": json.dumps(before)},
        )
    db.connection.execute(
        text(
            "UPDATE futures_markets SET status='open', settled_at=NULL WHERE id=109918"
        )
    )
    db.connection.execute(
        text(
            "UPDATE futures_outcomes SET is_winner=NULL, resolution_source=NULL WHERE market_id=109918"
        )
    )
    db.connection.commit()
    return before


@pytest.mark.asyncio
async def test_date_only_dry_run_keeps_the_old_backup_and_every_row_unchanged(db):
    banked = legacy_reopen(db)
    before = await repair.snapshot(db, 109918)
    result = await repair.repair_market(
        db, 109918, AsyncMock(side_effect=trading), refresh_close_time=True
    )
    assert result["verdict"] == "would_refresh_close_time"
    assert result["resolution_date_from_venue"] == "2027-11-03T15:00:00+00:00"
    assert await repair.snapshot(db, 109918) == before
    assert await repair.read_backup(db, 109918) == banked


@pytest.mark.asyncio
async def test_legacy_date_only_apply_banks_the_cutoff_without_touching_the_retraction_or_price(
    db,
):
    original = legacy_reopen(db)
    before = await repair.snapshot(db, 109918)
    result = await repair.repair_market(
        db, 109918, AsyncMock(side_effect=trading), apply=True, refresh_close_time=True
    )
    assert result["verdict"] == "close_time_refreshed"
    after, legs = await repair.snapshot(db, 109918)
    assert repair.instant(after["resolution_date"]) == datetime(
        2027, 11, 3, 15, tzinfo=timezone.utc
    )
    assert {k: v for k, v in after.items() if k != "resolution_date"} == {
        k: v for k, v in before[0].items() if k != "resolution_date"
    }
    assert legs == before[1]
    banked = await repair.read_backup(db, 109918)
    assert banked["market"] == original["market"]
    assert banked["legs"] == original["legs"]
    assert banked["close_time_repair_befores"] == [
        {"market": before[0], "legs": before[1]}
    ]
    again = await repair.repair_market(
        db, 109918, AsyncMock(side_effect=trading), apply=True, refresh_close_time=True
    )
    assert again["verdict"] == "close_time_current"
    assert await repair.read_backup(db, 109918) == banked


@pytest.mark.asyncio
async def test_date_only_requires_this_repairs_backup(db):
    legacy_reopen(db, bank=False)
    before = await repair.snapshot(db, 109918)
    read = AsyncMock(side_effect=trading)
    result = await repair.repair_market(
        db, 109918, read, apply=True, refresh_close_time=True
    )
    assert result["verdict"] == "unowned_repair_backup"
    read.assert_not_awaited()
    assert await repair.snapshot(db, 109918) == before


@pytest.mark.asyncio
async def test_date_only_refuses_a_changed_leg_membership(db):
    legacy_reopen(db)
    db.connection.execute(
        text("UPDATE futures_outcomes SET external_id='OTHER' WHERE id=1601726")
    )
    db.connection.commit()
    before = await repair.snapshot(db, 109918)
    read = AsyncMock(side_effect=trading)
    result = await repair.repair_market(
        db, 109918, read, apply=True, refresh_close_time=True
    )
    assert result["verdict"] == "unowned_repair_backup"
    read.assert_not_awaited()
    assert await repair.snapshot(db, 109918) == before


@pytest.mark.asyncio
async def test_a_leg_price_updated_during_the_venue_read_is_preserved(db):
    legacy_reopen(db)

    async def price_moved(ticker):
        db.connection.execute(
            text(
                "UPDATE futures_outcomes SET current_probability=.96, last_updated='fresh' WHERE id=1601726"
            )
        )
        db.connection.commit()
        return trading(ticker)

    result = await repair.repair_market(
        db, 109918, price_moved, apply=True, refresh_close_time=True
    )
    assert result["verdict"] == "close_time_refreshed"
    assert result["locked_before"]["legs"] == result["after"]["legs"]
    assert result["after"]["legs"][0]["current_probability"] == 0.96
    assert result["after"]["legs"][0]["last_updated"] == "fresh"


@pytest.mark.asyncio
async def test_the_reopen_uses_the_latest_fresh_close_across_all_stored_legs(db):
    db.connection.execute(
        text(
            "INSERT INTO futures_outcomes VALUES (1601727,109918,'Another','OTHER',FALSE,'ungradeable_result',.2,'old')"
        )
    )
    db.connection.commit()

    async def record(ticker):
        return {
            **trading(ticker),
            "close_time": (
                "2028-11-03T15:00:00Z" if ticker == "OTHER" else "2027-11-03T15:00:00Z"
            ),
        }

    read = AsyncMock(side_effect=record)
    result = await repair.repair_market(db, 109918, read, apply=True)
    assert result["verdict"] == "reopened"
    assert read.await_count == 2
    assert repair.instant(result["after"]["market"]["resolution_date"]) == datetime(
        2028, 11, 3, 15, tzinfo=timezone.utc
    )


@pytest.mark.asyncio
async def test_a_concurrent_cutoff_change_is_not_overwritten(db):
    legacy_reopen(db)

    async def moved(ticker):
        db.connection.execute(
            text(
                "UPDATE futures_markets SET resolution_date='2028-11-03T15:00:00Z' WHERE id=109918"
            )
        )
        db.connection.commit()
        return trading(ticker)

    result = await repair.repair_market(
        db, 109918, moved, apply=True, refresh_close_time=True
    )
    assert result["verdict"] == "concurrent_drift"
    assert (await repair.snapshot(db, 109918))[0][
        "resolution_date"
    ] == "2028-11-03T15:00:00Z"
    assert "close_time_repair_befores" not in await repair.read_backup(db, 109918)


@pytest.mark.asyncio
async def test_date_only_preserves_a_concurrent_venue_grade(db):
    legacy_reopen(db)

    async def graded(ticker):
        db.connection.execute(
            text(
                "UPDATE futures_outcomes SET is_winner=TRUE, resolution_source='api_settlement' WHERE id=1601726"
            )
        )
        db.connection.commit()
        return trading(ticker)

    result = await repair.repair_market(
        db, 109918, graded, apply=True, refresh_close_time=True
    )
    assert result["verdict"] == "concurrent_drift"
    assert (await repair.snapshot(db, 109918))[1][0][
        "resolution_source"
    ] == "api_settlement"


@pytest.mark.asyncio
async def test_date_only_census_requires_an_explicit_scope_and_reports_the_old_cutoff(
    db,
):
    legacy_reopen(db)
    with pytest.raises(ValueError, match="requires --only-ids"):
        await repair.census(db, refresh_close_time=True)
    rows = await repair.census(db, {109918}, refresh_close_time=True)
    assert [row["market"]["id"] for row in rows] == [109918]
    assert rows[0]["market"]["resolution_date"] == "2026-11-03T15:00:00+00:00"


def test_cli_date_only_requires_explicit_ids(monkeypatch):
    run = AsyncMock(return_value=0)
    monkeypatch.setattr(repair, "run", run)
    monkeypatch.setattr("sys.argv", ["repair_11947", "--refresh-close-time"])
    with pytest.raises(SystemExit) as exited:
        repair.main()
    assert exited.value.code == 2
    run.assert_not_awaited()


def test_cli_date_only_still_defaults_to_dry_run(monkeypatch):
    run = AsyncMock(return_value=0)
    monkeypatch.setattr(repair, "run", run)
    monkeypatch.setattr(
        "sys.argv", ["repair_11947", "--refresh-close-time", "--only-ids", "109918"]
    )
    with pytest.raises(SystemExit) as exited:
        repair.main()
    assert exited.value.code == 0
    run.assert_awaited_once_with(
        apply=False, census_only=False, only_ids={109918}, refresh_close_time=True
    )
