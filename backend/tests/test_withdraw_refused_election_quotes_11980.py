"""#11980: six refused old quotes become absent, never prices or grades.

Execute the repair SQL with the existing SQLite adapter. These fixtures do
not prove PostgreSQL lock scheduling.
"""

import json
from contextlib import asynccontextmanager
from unittest.mock import ANY, AsyncMock

import pytest
from sqlalchemy import text

from scripts import repair_11947_clock_settled_kalshi_markets_still_trading as repair
from tests.test_repair_clock_settled_kalshi_11947 import db  # noqa: F401

MID = 34277584
OLD = "2026-11-03 12:52:24"
TARGETS = {152597195, 152597197}


@pytest.fixture
async def quote_db(db):  # noqa: F811
    for column in (
        "calibration_probability NUMERIC",
        "current_american_odds INTEGER DEFAULT 170",
        "current_yes_bid NUMERIC DEFAULT .14",
        "current_yes_ask NUMERIC DEFAULT .20",
        "probability_change_24h NUMERIC DEFAULT .1",
        "price_changed_at TEXT DEFAULT '2026-11-02 22:00:01'",
        "rank INTEGER DEFAULT 1",
    ):
        db.connection.execute(text("ALTER TABLE futures_outcomes ADD COLUMN " + column))
    db.connection.execute(
        text(
            f"ALTER TABLE {repair.BACKUP_TABLE} ADD COLUMN banked_at TEXT "
            "DEFAULT '2026-11-04 16:26:24'"
        )
    )
    db.connection.execute(
        text(
            "INSERT INTO futures_markets (id,name,source,external_id,status,settled_at) "
            "VALUES (:id,'Alaska rounds','kalshi','KXAKSENATEROUND-26','resolved',"
            "'2026-11-03 20:16:37')"
        ),
        {"id": MID},
    )
    for oid, name, prob, rank in (
        (152597195, "2", 0.17, 3),
        (152597196, "3", 0.44, 1),
        (152597197, "1", 0.37, 2),
    ):
        db.connection.execute(
            text(
                "INSERT INTO futures_outcomes "
                "(id,market_id,name,external_id,is_winner,resolution_source,"
                "current_probability,last_updated,rank) VALUES "
                "(:id,:mid,:name,:ticker,FALSE,'ungradeable_result',:prob,:old,:rank)"
            ),
            {
                "id": oid,
                "mid": MID,
                "name": name,
                "ticker": "KXAKSENATEROUND-26-" + name,
                "prob": prob,
                "old": OLD,
                "rank": rank,
            },
        )
    db.connection.commit()
    market, legs = await repair.snapshot(db, MID)
    db.connection.execute(
        text(
            f"INSERT INTO {repair.BACKUP_TABLE} (market_id,before_json) VALUES (:mid,:b)"
        ),
        {"mid": MID, "b": json.dumps({"market": market, "legs": legs})},
    )
    db.connection.execute(
        text("UPDATE futures_markets SET status='open',settled_at=NULL WHERE id=:mid"),
        {"mid": MID},
    )
    db.connection.execute(
        text(
            "UPDATE futures_outcomes SET is_winner=NULL,resolution_source=NULL "
            "WHERE market_id=:mid"
        ),
        {"mid": MID},
    )
    db.connection.commit()
    return db


def refused(ticker):
    return {
        "ticker": ticker,
        "event_ticker": "KXAKSENATEROUND-26",
        "title": "Alaska Senate rounds",
        "status": "active",
        "result": "",
        "yes_bid_dollars": "0.03",
        "yes_ask_dollars": "0.87",
        "last_price_dollars": "0.99",
    }


@pytest.mark.asyncio
async def test_default_dry_run_names_only_the_two_reviewed_legs_and_changes_nothing(
    quote_db,
):
    before = await repair.quote_snapshot(quote_db, MID)
    banked = await repair.read_backup(quote_db, MID)
    read = AsyncMock(side_effect=refused)
    result = await repair.withdraw_refused_quotes(quote_db, MID, read)
    assert result["verdict"] == "would_withdraw"
    assert {r["id"] for r in result["withdraw"]} == TARGETS
    assert read.await_count == 2
    assert await repair.quote_snapshot(quote_db, MID) == before
    assert await repair.read_backup(quote_db, MID) == banked


@pytest.mark.asyncio
async def test_apply_banks_quotes_and_clears_only_current_fields_without_a_false_clock(
    quote_db,
):
    before = await repair.quote_snapshot(quote_db, MID)
    original = await repair.read_backup(quote_db, MID)
    result = await repair.withdraw_refused_quotes(
        quote_db, MID, AsyncMock(side_effect=refused), apply=True
    )
    assert result["verdict"] == "withdrawn"
    market, legs = await repair.quote_snapshot(quote_db, MID)
    assert market == before[0]
    old_by_id = {leg["id"]: leg for leg in before[1]}
    for leg in legs:
        if leg["id"] in TARGETS:
            for key in (
                "current_probability",
                "current_american_odds",
                "current_yes_bid",
                "current_yes_ask",
                "probability_change_24h",
            ):
                assert leg[key] is None
        else:
            assert leg == old_by_id[leg["id"]]
        for key in (
            "is_winner",
            "resolution_source",
            "calibration_probability",
            "last_updated",
            "price_changed_at",
        ):
            assert leg[key] == old_by_id[leg["id"]][key]
    banked = await repair.read_backup(quote_db, MID)
    assert banked["market"] == original["market"]
    assert banked["legs"] == original["legs"]
    assert banked["quote_withdrawal_befores"][0]["legs"] == before[1]
    assert next(leg for leg in legs if leg["id"] == 152597196)["rank"] == 1
    read = AsyncMock(side_effect=refused)
    again = await repair.withdraw_refused_quotes(quote_db, MID, read, apply=True)
    assert again["verdict"] == "nothing_to_withdraw"
    read.assert_not_awaited()
    assert await repair.read_backup(quote_db, MID) == banked


@pytest.mark.parametrize(
    "record",
    [
        None,
        {"ticker": "OTHER", "status": "active", "result": ""},
        {"status": "finalized", "result": "yes"},
        {"status": "active", "result": "no"},
        {"status": "active"},
    ],
)
@pytest.mark.asyncio
async def test_missing_or_answered_venue_record_never_withdraws(quote_db, record):
    before = await repair.quote_snapshot(quote_db, MID)
    banked = await repair.read_backup(quote_db, MID)

    async def read(ticker):
        return {"ticker": ticker, **record} if record is not None else None

    result = await repair.withdraw_refused_quotes(quote_db, MID, read, apply=True)
    assert result["verdict"] != "withdrawn"
    assert await repair.quote_snapshot(quote_db, MID) == before
    assert await repair.read_backup(quote_db, MID) == banked


@pytest.mark.asyncio
async def test_a_current_accepted_quote_is_not_withdrawn(quote_db):
    before = await repair.quote_snapshot(quote_db, MID)

    async def read(ticker):
        return {
            **refused(ticker),
            "yes_bid_dollars": "0.59",
            "yes_ask_dollars": "0.61",
            "last_price_dollars": "0.60",
        }

    result = await repair.withdraw_refused_quotes(quote_db, MID, read, apply=True)
    assert result["verdict"] == "nothing_to_withdraw"
    assert {r["reason"] for r in result["skipped"]} == {"venue_quote_accepted"}
    assert await repair.quote_snapshot(quote_db, MID) == before


def test_the_normal_writers_empty_book_refusal_is_also_respected():
    assert (
        repair.quote_refusal(
            {
                **refused("KXOHHAWKINS-26-MZAY"),
                "yes_bid_dollars": "0.04",
                "yes_ask_dollars": "0.94",
                "last_price_dollars": "0.48",
            }
        )
        == "writer_empty_book"
    )


@pytest.mark.parametrize(
    "change",
    [
        "current_probability=.73,last_updated='2026-11-04 17:00:00'",
        "is_winner=TRUE,resolution_source='api_settlement'",
        "calibration_probability=.17",
        "external_id='OTHER'",
    ],
)
@pytest.mark.asyncio
async def test_a_concurrent_quote_grade_capture_or_membership_change_wins(
    quote_db, change
):
    banked = await repair.read_backup(quote_db, MID)

    async def read(ticker):
        if ticker.endswith("-2"):
            quote_db.connection.execute(
                text("UPDATE futures_outcomes SET " + change + " WHERE id=152597195")
            )
            quote_db.connection.commit()
        return refused(ticker)

    result = await repair.withdraw_refused_quotes(quote_db, MID, read, apply=True)
    assert result["verdict"] == "concurrent_drift"
    leg = next(
        r
        for r in (await repair.quote_snapshot(quote_db, MID))[1]
        if r["id"] == 152597195
    )
    assert leg["current_probability"] is not None
    assert await repair.read_backup(quote_db, MID) == banked


@pytest.mark.asyncio
async def test_a_healthy_siblings_concurrent_price_survives(quote_db):
    from app.utils.futures_rank import rerank_market_field_stmt

    async def read(ticker):
        quote_db.connection.execute(
            text(
                "UPDATE futures_outcomes SET current_probability=.1, "
                "last_updated='2026-11-04 17:00:00' WHERE id=152597196"
            )
        )
        await quote_db.execute(rerank_market_field_stmt(MID))
        quote_db.connection.commit()
        return refused(ticker)

    result = await repair.withdraw_refused_quotes(quote_db, MID, read, apply=True)
    assert result["verdict"] == "withdrawn"
    leg = next(r for r in result["after"]["legs"] if r["id"] == 152597196)
    assert (leg["current_probability"], leg["last_updated"]) == (
        0.1,
        "2026-11-04 17:00:00",
    )


@pytest.mark.parametrize(
    "field, value, reason",
    [
        ("calibration_probability", ".17", "captured_closing_line"),
        ("last_updated", "'2026-11-04 17:00:00'", "newer_writer_since_reopen"),
        ("price_changed_at", "'2026-11-04 17:00:00'", "newer_writer_since_reopen"),
    ],
)
@pytest.mark.asyncio
async def test_captured_lines_and_post_repair_writers_are_not_withdrawn(
    quote_db, field, value, reason
):
    quote_db.connection.execute(
        text(f"UPDATE futures_outcomes SET {field}={value} WHERE id=152597195")
    )
    quote_db.connection.commit()
    result = await repair.withdraw_refused_quotes(
        quote_db, MID, AsyncMock(side_effect=refused), apply=True
    )
    assert result["verdict"] == "withdrawn"
    assert {r["id"] for r in result["withdraw"]} == {152597197}
    assert {r["reason"] for r in result["skipped"]} == {reason}


@pytest.mark.asyncio
async def test_an_unowned_backup_cannot_withdraw_a_quote(quote_db):
    quote_db.connection.execute(
        text(f"DELETE FROM {repair.BACKUP_TABLE} WHERE market_id=:mid"), {"mid": MID}
    )
    quote_db.connection.commit()
    read = AsyncMock(side_effect=refused)
    result = await repair.withdraw_refused_quotes(quote_db, MID, read, apply=True)
    assert result["verdict"] == "unowned_repair_backup"
    read.assert_not_awaited()


@pytest.mark.asyncio
async def test_incomplete_or_unreachable_venue_evidence_cannot_be_spent(quote_db):
    before = await repair.quote_snapshot(quote_db, MID)
    banked = await repair.read_backup(quote_db, MID)
    with pytest.raises(ValueError, match="incomplete"):
        await repair.withdraw_refused_quotes(
            quote_db,
            MID,
            AsyncMock(
                return_value={
                    "ticker": "KXAKSENATEROUND-26-2",
                    "status": "active",
                    "result": "",
                }
            ),
            apply=True,
        )
    with pytest.raises(RuntimeError, match="offline"):
        await repair.withdraw_refused_quotes(
            quote_db, MID, AsyncMock(side_effect=RuntimeError("offline")), apply=True
        )
    assert await repair.quote_snapshot(quote_db, MID) == before
    assert await repair.read_backup(quote_db, MID) == banked


@pytest.mark.asyncio
async def test_the_mode_refuses_any_market_outside_alexs_exact_scope(quote_db):
    with pytest.raises(ValueError, match="outside"):
        await repair.withdraw_refused_quotes(quote_db, 109918, AsyncMock(), apply=True)
    with pytest.raises(ValueError, match="five reviewed markets"):
        await repair.run_quote_withdrawal(apply=True, only_ids={109918})


def test_cli_withdrawal_requires_explicit_market_scope(monkeypatch):
    monkeypatch.setattr("sys.argv", ["repair_11947", "--withdraw-refused-quotes"])
    with pytest.raises(SystemExit) as exited:
        repair.main()
    assert exited.value.code == 2


def test_cli_withdrawal_defaults_to_dry_run(monkeypatch):
    run = AsyncMock(return_value=0)
    monkeypatch.setattr(repair, "run_quote_withdrawal", run)
    monkeypatch.setattr(
        "sys.argv",
        ["repair_11947", "--withdraw-refused-quotes", "--only-ids", str(MID)],
    )
    with pytest.raises(SystemExit) as exited:
        repair.main()
    assert exited.value.code == 0
    run.assert_awaited_once_with(apply=False, only_ids={MID})


@pytest.mark.parametrize(
    "verdict, exit_code",
    [
        ("withdrawn", 0),
        ("nothing_to_withdraw", 0),
        ("venue_not_trading", 1),
        ("concurrent_drift", 1),
    ],
)
@pytest.mark.asyncio
async def test_a_refused_withdrawal_is_not_reported_as_a_successful_run(
    quote_db, monkeypatch, verdict, exit_code
):
    from app.tasks import base

    @asynccontextmanager
    async def session(**kwargs):
        yield quote_db

    monkeypatch.setattr(base, "get_task_session", session)
    operation = AsyncMock(return_value={"id": MID, "verdict": verdict})
    monkeypatch.setattr(repair, "withdraw_refused_quotes", operation)
    assert await repair.run_quote_withdrawal(only_ids={MID}) == exit_code
    operation.assert_awaited_once_with(quote_db, MID, ANY, apply=False)
