"""#12013: actual venue results, live contracts and pending closed contracts differ."""

import json
from copy import deepcopy
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text

from scripts import repair_11947_clock_settled_kalshi_markets_still_trading as repair
from tests.test_repair_clock_settled_kalshi_11947 import db  # noqa: F401

MID = 109918
OID = 1601726
NOW = datetime(2026, 11, 4, 22, tzinfo=timezone.utc)


@pytest.fixture
def subject(db, monkeypatch):
    monkeypatch.setattr(repair, "utc_now", lambda: NOW)
    db.connection.execute(
        text("ALTER TABLE futures_outcomes ADD COLUMN current_american_odds INTEGER")
    )
    db.connection.execute(
        text("ALTER TABLE futures_outcomes ADD COLUMN price_changed_at TEXT")
    )
    db.connection.execute(
        text(
            "UPDATE futures_outcomes SET current_american_odds=-135, price_changed_at='old' WHERE id=:id"
        ),
        {"id": OID},
    )
    db.connection.commit()
    return db


def event(*, result="", status="active", close="2026-11-08T15:00:00Z"):
    return {
        "event": {
            "event_ticker": "SWEEP",
            "markets": [
                {
                    "ticker": "SWEEP",
                    "status": status,
                    "result": result,
                    "close_time": close,
                    "settlement_ts": "2026-11-04T05:33:46Z",
                }
            ],
        },
        "markets": [],
    }  # The real API also carries an empty top-level list.


async def backup_rows(db):
    return (await db.execute(text(f"SELECT * FROM {repair.BACKUP_TABLE}"))).all()


@pytest.mark.asyncio
@pytest.mark.parametrize("result,expected", [("yes", True), ("no", False)])
async def test_binary_venue_results_replace_clock_markers_and_bank_every_written_value(
    subject, result, expected
):
    before = await repair.appendix_snapshot(subject, MID)
    report = await repair.reconcile_appendix_market(
        subject,
        MID,
        AsyncMock(return_value=event(result=result, status="finalized")),
        apply=True,
    )
    market, legs = await repair.appendix_snapshot(subject, MID)
    assert report["verdict"] == "reconciled"
    assert report["state"] == "venue_graded"
    assert market["status"] == "resolved"
    assert repair.instant(market["settled_at"]) == repair.instant(
        "2026-11-04T05:33:46Z"
    )
    assert bool(legs[0]["is_winner"]) is expected
    assert legs[0]["resolution_source"] == "api_settlement"
    assert legs[0]["current_probability"] == int(expected)
    assert legs[0]["current_american_odds"] is None
    assert repair.instant(legs[0]["last_updated"]) == NOW
    bank = json.loads((await backup_rows(subject))[0]._mapping["before_json"])
    assert bank["legs"][0]["current_probability"] == before[1][0]["current_probability"]
    assert bank["legs"][0]["current_american_odds"] == -135
    assert bank["legs"][0]["price_changed_at"] == "old"
    assert report["before_clock_legs"] == 1 and report["after_clock_legs"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,close,state",
    [
        ("active", "2026-11-08T15:00:00Z", "still_trading"),
        ("active", "2026-11-01T13:29:00Z", "awaiting_result"),
        ("closed", "2026-11-01T13:29:00Z", "awaiting_result"),
    ],
)
async def test_pending_contract_reopens_at_venue_close_without_touching_any_quote_clock(
    subject, status, close, state
):
    before = await repair.appendix_snapshot(subject, MID)
    report = await repair.reconcile_appendix_market(
        subject,
        MID,
        AsyncMock(return_value=event(status=status, close=close)),
        apply=True,
    )
    market, legs = await repair.appendix_snapshot(subject, MID)
    assert report["state"] == state and report["verdict"] == "reconciled"
    assert market["status"] == "open" and market["settled_at"] is None
    assert repair.instant(market["resolution_date"]) == repair.instant(close)
    assert legs[0]["is_winner"] is None and legs[0]["resolution_source"] is None
    for key in [
        "current_probability",
        "current_american_odds",
        "last_updated",
        "price_changed_at",
    ]:
        assert legs[0][key] == before[1][0][key]


@pytest.mark.asyncio
async def test_dry_run_is_read_only_even_for_a_declared_winner(subject):
    before = await repair.appendix_snapshot(subject, MID)
    report = await repair.reconcile_appendix_market(
        subject, MID, AsyncMock(return_value=event(result="yes", status="finalized"))
    )
    assert report["verdict"] == "would_reconcile"
    assert await repair.appendix_snapshot(subject, MID) == before
    assert await backup_rows(subject) == []


@pytest.mark.asyncio
async def test_existing_venue_grade_survives_even_when_the_event_archive_omits_its_ticker(
    subject,
):
    await subject.execute(
        text(
            "INSERT INTO futures_outcomes (id,market_id,name,external_id,is_winner,resolution_source,current_probability,last_updated) VALUES (1601727,:mid,'Old leg','ARCHIVED',FALSE,'api_settlement',0,'archive')"
        ),
        {"mid": MID},
    )
    await subject.commit()
    before = await repair.appendix_snapshot(subject, MID)
    assert await repair.census(subject, {MID}) == []
    assert len(await repair.census(subject, {MID}, include_partial=True)) == 1
    report = await repair.reconcile_appendix_market(
        subject, MID, AsyncMock(return_value=event()), apply=True
    )
    assert report["verdict"] == "reconciled"
    _, after = await repair.appendix_snapshot(subject, MID)
    assert after[1] == before[1][1]


@pytest.mark.asyncio
async def test_scalar_is_never_reopened_or_mapped_to_a_binary_loss(subject):
    before = await repair.appendix_snapshot(subject, MID)
    report = await repair.reconcile_appendix_market(
        subject,
        MID,
        AsyncMock(return_value=event(result="scalar", status="finalized")),
        apply=True,
    )
    assert report["verdict"] == "venue_settled_scalar"
    assert await repair.appendix_snapshot(subject, MID) == before
    assert await backup_rows(subject) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        "wrong_event",
        "empty_event",
        "missing_leg",
        "duplicate_leg",
        "missing_close",
        "missing_result",
        "bad_status",
        "missing_settlement_time",
    ],
)
async def test_unknown_evidence_refuses_with_no_backup_or_writes(subject, failure):
    payload = event()
    record = payload["event"]["markets"][0]
    if failure == "wrong_event":
        payload["event"]["event_ticker"] = "WRONG"
    if failure == "empty_event":
        payload["event"]["markets"] = []
    if failure == "missing_leg":
        record["ticker"] = "WRONG"
    if failure == "duplicate_leg":
        payload["event"]["markets"].append(deepcopy(record))
    if failure == "missing_close":
        record["close_time"] = None
    if failure == "missing_result":
        record.pop("result")
    if failure == "bad_status":
        record["status"] = "inactive"
    if failure == "missing_settlement_time":
        record.update(status="finalized", result="yes", settlement_ts=None)
    before = await repair.appendix_snapshot(subject, MID)
    report = await repair.reconcile_appendix_market(
        subject, MID, AsyncMock(return_value=payload), apply=True
    )
    assert report["verdict"] != "reconciled"
    assert await repair.appendix_snapshot(subject, MID) == before
    assert await backup_rows(subject) == []


@pytest.mark.asyncio
async def test_concurrent_venue_grade_wins_and_prevents_the_planned_reopen(subject):
    async def read(_):
        await subject.execute(
            text(
                "UPDATE futures_outcomes SET is_winner=TRUE,resolution_source='api_settlement' WHERE id=:id"
            ),
            {"id": OID},
        )
        await subject.commit()
        return event()

    report = await repair.reconcile_appendix_market(subject, MID, read, apply=True)
    assert report["verdict"] == "concurrent_drift"
    assert await backup_rows(subject) == []
    assert (await repair.appendix_snapshot(subject, MID))[1][0][
        "resolution_source"
    ] == "api_settlement"


@pytest.mark.asyncio
async def test_original_backup_is_retained_with_a_new_locked_before_image(subject):
    original = {"market": {"id": MID}, "original_receipt": "banked"}
    await subject.execute(
        text(f"INSERT INTO {repair.BACKUP_TABLE} VALUES (:id,:body)"),
        {"id": MID, "body": json.dumps(original)},
    )
    await subject.commit()
    await repair.reconcile_appendix_market(
        subject, MID, AsyncMock(return_value=event()), apply=True
    )
    bank = json.loads((await backup_rows(subject))[0]._mapping["before_json"])
    assert bank["original_receipt"] == "banked" and bank["market"] == original["market"]
    assert len(bank["appendix_repair_befores"]) == 1
    assert bank["appendix_repair_befores"][0]["legs"][0]["current_probability"] == 0.575


def test_cli_requires_exact_scope_and_never_defaults_to_apply(monkeypatch):
    monkeypatch.setattr("sys.argv", ["repair", "--reconcile-appendix"])
    with pytest.raises(SystemExit) as error:
        repair.main()
    assert error.value.code == 2

    async def run(**kwargs):
        assert kwargs == {"only_ids": {MID}, "apply": False, "census_only": False}
        return 0

    monkeypatch.setattr(repair, "run_appendix", run)
    monkeypatch.setattr(
        "sys.argv", ["repair", "--reconcile-appendix", "--only-ids", str(MID)]
    )
    with pytest.raises(SystemExit) as error:
        repair.main()
    assert error.value.code == 0
