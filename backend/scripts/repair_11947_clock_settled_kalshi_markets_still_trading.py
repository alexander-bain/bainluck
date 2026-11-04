"""#11947: reopen falsely settled Kalshi markets on fresh trading evidence.

CERT-752 / repair_3780: absence of an authority result cannot end a market.
The complete census is printed before venue reads or writes. Post that census
on #11947 before applying; --only-ids scopes later runs to reviewed ids.
Every stored leg must have a fresh public Kalshi record saying active/open
with an explicitly empty result and a valid future close_time. The reopen
carries max(close_time), as Kalshi ingestion does: a past stored cutoff would
otherwise keep the reopened market out of the existing price populations.

Dry-run is the default. Apply banks the market and every leg's prior state in
bak_11947_clock_settlement in the same transaction as the repair. It rechecks
the entire predicate under row locks; a concurrent grade wins. Prices, price
clocks, snapshots and history are never written.

--refresh-close-time repairs only the cutoff of an already-reopened, ungraded
market whose original retraction is proved by this repair's banked before-image.
It requires --only-ids and preserves that original backup while banking the
date-repair before-image alongside it in the same row and transaction.
This restores fallback eligibility; socket admission keeps its existing rules.

    python3 scripts/repair_11947_clock_settled_kalshi_markets_still_trading.py --census-only
    python3 scripts/repair_11947_clock_settled_kalshi_markets_still_trading.py --only-ids 109918
    python3 scripts/repair_11947_clock_settled_kalshi_markets_still_trading.py --only-ids 109918 --apply
    python3 scripts/repair_11947_clock_settled_kalshi_markets_still_trading.py --only-ids 109918 --refresh-close-time

Run the deployed script as a Heroku detached one-off task, as in repair_3780.
"""

import argparse
import asyncio
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from urllib.parse import quote
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import bindparam, text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.utils.agent_origin import tagged  # noqa: E402

BACKUP_TABLE = "bak_11947_clock_settlement"
PUBLIC_API = "https://api.elections.kalshi.com/trade-api/v2"
PAGE_SIZE = 1000
MARKET_COLUMNS = "id, name, source, external_id, status, settled_at, resolution_date"
OUTCOME_COLUMNS = (
    "id, market_id, name, external_id, is_winner, resolution_source, "
    "current_probability, last_updated"
)
CENSUS_PAGE = text(
    f"SELECT {MARKET_COLUMNS} FROM futures_markets "
    "WHERE id > :after_id AND source = 'kalshi' AND status = 'resolved' "
    "AND settled_at IS NOT NULL ORDER BY id LIMIT :page_size"
)
SCOPED_CENSUS_PAGE = text(
    CENSUS_PAGE.text.replace(" ORDER BY id", " AND id IN :only_ids ORDER BY id")
).bindparams(bindparam("only_ids", expanding=True))
SCOPED_OPEN_CENSUS_PAGE = text(
    f"SELECT {MARKET_COLUMNS} FROM futures_markets "
    "WHERE id > :after_id AND source = 'kalshi' AND status = 'open' "
    "AND settled_at IS NULL AND id IN :only_ids ORDER BY id LIMIT :page_size"
).bindparams(bindparam("only_ids", expanding=True))
PAGE_LEGS = text(
    f"SELECT {OUTCOME_COLUMNS} FROM futures_outcomes "
    "WHERE market_id IN :ids ORDER BY id"
).bindparams(bindparam("ids", expanding=True))
READ_MARKET = f"SELECT {MARKET_COLUMNS} FROM futures_markets WHERE id = :id"
READ_LEGS = (
    f"SELECT {OUTCOME_COLUMNS} FROM futures_outcomes WHERE market_id = :id ORDER BY id"
)


def eligible(market, legs):
    return (
        market is not None
        and market["source"] == "kalshi"
        and market["status"] == "resolved"
        and market["settled_at"] is not None
        and bool(legs)
        and all(
            leg["is_winner"] is not True
            and leg["is_winner"] != 1
            and leg["resolution_source"] == "ungradeable_result"
            for leg in legs
        )
    )


def reopened_eligible(market, legs):
    return (
        market is not None
        and market["source"] == "kalshi"
        and market["status"] == "open"
        and market["settled_at"] is None
        and bool(legs)
        and all(
            leg["is_winner"] is None and leg["resolution_source"] is None
            for leg in legs
        )
    )


def instant(value):
    try:
        stamp = (
            value
            if isinstance(value, datetime)
            else datetime.fromisoformat(value.replace("Z", "+00:00"))
        )
        return stamp.astimezone(timezone.utc) if stamp.utcoffset() is not None else None
    except (ValueError, TypeError, AttributeError):
        return None


def utc_now():
    return datetime.now(timezone.utc)


def owns_reopened(backup, market, legs):
    if not isinstance(backup, dict):
        return False
    try:
        prior, prior_legs = backup["market"], backup["legs"]
        return (
            eligible(prior, prior_legs)
            and prior["id"] == market["id"]
            and prior["external_id"] == market["external_id"]
            and {(leg["id"], leg["external_id"]) for leg in prior_legs}
            == {(leg["id"], leg["external_id"]) for leg in legs}
        )
    except (KeyError, TypeError):
        return False


async def read_backup(session, market_id):
    value = (
        await session.execute(
            text(f"SELECT before_json FROM {BACKUP_TABLE} WHERE market_id = :id"),
            {"id": market_id},
        )
    ).scalar_one_or_none()
    return json.loads(value) if value is not None else None


def venue_refusal(record, ticker):
    if not isinstance(record, dict) or record.get("ticker") != ticker:
        return "missing_or_mismatched_market"
    if record.get("status") not in {"active", "open"}:
        return "venue_not_trading"
    if "result" not in record or record["result"] not in ("", None):
        return "venue_result_present_or_missing"
    return None


def fingerprint(market, legs):
    return (
        tuple(
            market[k]
            for k in (
                "id",
                "source",
                "external_id",
                "status",
                "settled_at",
                "resolution_date",
            )
        ),
        tuple(
            tuple(
                leg[k] for k in ("id", "external_id", "is_winner", "resolution_source")
            )
            for leg in legs
        ),
    )


async def census(session, only_ids=None, *, refresh_close_time=False):
    """Keyset pages bound each read; an empty eligible page is not exhaustion."""
    if refresh_close_time and not only_ids:
        raise ValueError("--refresh-close-time requires --only-ids")
    predicate = reopened_eligible if refresh_close_time else eligible
    found = []
    after_id = 0
    while True:
        params = {"after_id": after_id, "page_size": PAGE_SIZE}
        query = CENSUS_PAGE
        if only_ids is not None:
            query = (
                SCOPED_OPEN_CENSUS_PAGE if refresh_close_time else SCOPED_CENSUS_PAGE
            )
            params["only_ids"] = sorted(only_ids)
        markets = (await session.execute(query, params)).mappings().all()
        if not markets:
            return found
        legs = defaultdict(list)
        rows = (
            (await session.execute(PAGE_LEGS, {"ids": [m["id"] for m in markets]}))
            .mappings()
            .all()
        )
        for leg in rows:
            legs[leg["market_id"]].append(dict(leg))
        for market in markets:
            if predicate(market, legs[market["id"]]):
                found.append({"market": dict(market), "legs": legs[market["id"]]})
        after_id = markets[-1]["id"]
        await session.rollback()  # Each page releases its read transaction.


async def snapshot(session, market_id, *, lock=False):
    # Lock grades before the parent. Re-read membership under the parent lock
    # as well: a leg could have been inserted while that lock was awaited.
    suffix = " FOR UPDATE" if lock else ""
    legs = (
        (await session.execute(text(READ_LEGS + suffix), {"id": market_id}))
        .mappings()
        .all()
    )
    market = (
        (await session.execute(text(READ_MARKET + suffix), {"id": market_id}))
        .mappings()
        .one_or_none()
    )
    if lock:
        legs = (
            (await session.execute(text(READ_LEGS + suffix), {"id": market_id}))
            .mappings()
            .all()
        )
    return dict(market) if market else None, [dict(leg) for leg in legs]


async def repair_market(
    session, market_id, read_market, *, apply=False, refresh_close_time=False
):
    predicate = reopened_eligible if refresh_close_time else eligible
    before, legs = await snapshot(session, market_id)
    if not predicate(before, legs):
        return {"id": market_id, "verdict": "no_longer_eligible"}
    if refresh_close_time and not owns_reopened(
        await read_backup(session, market_id), before, legs
    ):
        return {"id": market_id, "verdict": "unowned_repair_backup"}
    evidence, closes = [], []
    for leg in legs:
        ticker = leg["external_id"]
        if not isinstance(ticker, str) or not ticker:
            return {"id": market_id, "verdict": "missing_ticker"}
        record = await read_market(ticker)
        evidence.append(
            {k: record.get(k) for k in ("ticker", "status", "result", "close_time")}
            if isinstance(record, dict)
            else None
        )
        refusal = venue_refusal(record, ticker)
        if refusal:
            return {"id": market_id, "verdict": refusal, "venue": evidence}
        close = instant(record.get("close_time"))
        if close is None or close <= utc_now():
            return {
                "id": market_id,
                "verdict": "venue_close_time_not_future",
                "venue": evidence,
            }
        closes.append(close)
    # The existing Kalshi ingestion contract uses the latest leg close.
    close = max(closes)
    report = {
        "id": market_id,
        "before": {"market": before, "legs": legs},
        "venue": evidence,
        "resolution_date_from_venue": close.isoformat(),
    }
    if refresh_close_time and instant(before["resolution_date"]) == close:
        return {**report, "verdict": "close_time_current"}
    if not apply:
        return {
            **report,
            "verdict": (
                "would_refresh_close_time" if refresh_close_time else "would_reopen"
            ),
        }

    # End the read transaction before taking the write locks and re-reading.
    await session.rollback()
    current, current_legs = await snapshot(session, market_id, lock=True)
    if not predicate(current, current_legs) or fingerprint(
        current, current_legs
    ) != fingerprint(before, legs):
        await session.rollback()
        return {**report, "verdict": "concurrent_drift"}
    banked = await read_backup(session, market_id)
    if refresh_close_time and not owns_reopened(banked, current, current_legs):
        await session.rollback()
        return {**report, "verdict": "concurrent_drift"}
    if banked is not None:
        # Preserve the original retraction backup, including legacy rows that
        # did not capture resolution_date. The parent lock serializes this row's
        # repair; the added before-image commits with the cutoff update.
        banked.setdefault("close_time_repair_befores", []).append(
            {"market": current, "legs": current_legs}
        )
        await session.execute(
            text(
                f"UPDATE {BACKUP_TABLE} SET before_json = :before WHERE market_id = :id"
            ),
            {"id": market_id, "before": json.dumps(banked, default=str)},
        )
    else:
        await session.execute(
            text(
                f"INSERT INTO {BACKUP_TABLE} (market_id, before_json) VALUES (:id, :before) "
                "ON CONFLICT (market_id) DO NOTHING"
            ),
            {
                "id": market_id,
                "before": json.dumps(
                    {"market": current, "legs": current_legs}, default=str
                ),
            },
        )
    cleared_count = len(current_legs)
    if not refresh_close_time:
        cleared = await session.execute(
            text(
                "UPDATE futures_outcomes SET is_winner = NULL, resolution_source = NULL "
                "WHERE market_id = :id AND is_winner IS NOT TRUE "
                "AND resolution_source = 'ungradeable_result'"
            ),
            {"id": market_id},
        )
        cleared_count = cleared.rowcount
    state_clause = (
        "status = 'open' AND settled_at IS NULL"
        if refresh_close_time
        else "status = 'resolved' AND settled_at IS NOT NULL"
    )
    set_clause = (
        "resolution_date = :close_time"
        if refresh_close_time
        else "status = 'open', settled_at = NULL, resolution_date = :close_time"
    )
    reopened = await session.execute(
        text(
            f"UPDATE futures_markets SET {set_clause} "
            f"WHERE id = :id AND source = 'kalshi' AND {state_clause}"
        ),
        {"id": market_id, "close_time": close},
    )
    if cleared_count != len(current_legs) or reopened.rowcount != 1:
        await session.rollback()
        return {**report, "verdict": "concurrent_drift"}
    after, after_legs = await snapshot(session, market_id)
    await session.commit()
    return {
        **report,
        "verdict": "close_time_refreshed" if refresh_close_time else "reopened",
        "backup_table": BACKUP_TABLE,
        "locked_before": {"market": current, "legs": current_legs},
        "after": {"market": after, "legs": after_legs},
    }


async def run(
    *, apply=False, census_only=False, only_ids=None, refresh_close_time=False
):
    from app.tasks.base import get_task_session

    if refresh_close_time and not only_ids:
        raise ValueError("--refresh-close-time requires --only-ids")
    mode = "APPLY" if apply else "DRY_RUN"
    if refresh_close_time:
        mode += "_CLOSE_TIME"
    print(
        json.dumps(
            {
                "repair": 11947,
                "mode": mode,
                "at": datetime.now(ZoneInfo("America/Los_Angeles")).isoformat(),
            }
        ),
        flush=True,
    )
    async with get_task_session(
        statement_timeout_ms=15000, lock_timeout_ms=5000
    ) as session:
        population = await census(
            session, only_ids, refresh_close_time=refresh_close_time
        )
        print(
            json.dumps(
                {
                    "census_count": len(population),
                    "scope": "all_candidates" if only_ids is None else sorted(only_ids),
                    "census": [
                        {
                            k: row["market"][k]
                            for k in (
                                "id",
                                "name",
                                "external_id",
                                "settled_at",
                                "resolution_date",
                            )
                        }
                        for row in population
                    ],
                },
                default=str,
            ),
            flush=True,
        )
        await session.rollback()
        if census_only:
            return 0
        selected = [
            r["market"]["id"]
            for r in population
            if only_ids is None or r["market"]["id"] in only_ids
        ]
        if apply and only_ids is None:
            raise ValueError(
                "--apply requires --only-ids naming the census rows reviewed on #11947"
            )
        if apply:
            await session.execute(
                text(
                    f"CREATE TABLE IF NOT EXISTS {BACKUP_TABLE} ("
                    "market_id BIGINT PRIMARY KEY, before_json TEXT NOT NULL, "
                    "banked_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)"
                )
            )
            await session.commit()
        counts = defaultdict(int)
        async with httpx.AsyncClient(base_url=PUBLIC_API, timeout=10.0) as client:

            async def read_market(ticker):
                response = await client.get(
                    "/markets/" + quote(ticker, safe=""), headers=tagged(PUBLIC_API)
                )
                if response.status_code == 404:
                    return None
                response.raise_for_status()
                return response.json().get("market")

            for market_id in selected:
                try:
                    report = await repair_market(
                        session,
                        market_id,
                        read_market,
                        apply=apply,
                        refresh_close_time=refresh_close_time,
                    )
                except Exception as exc:
                    await session.rollback()
                    report = {"id": market_id, "verdict": "error", "error": str(exc)}
                counts[report["verdict"]] += 1
                print(json.dumps(report, default=str), flush=True)
                await session.rollback()
                if report["verdict"] == "error":
                    break  # An unreadable venue/DB is a stop, never a retry or a clean zero.
        print(json.dumps({"selected": selected, "counts": dict(counts)}), flush=True)
        return int(bool(counts["error"] or counts["concurrent_drift"]))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--census-only", action="store_true")
    parser.add_argument(
        "--refresh-close-time",
        action="store_true",
        help="Only refresh the cutoff of banked, already-reopened ids",
    )
    parser.add_argument(
        "--only-ids", help="Comma-separated census ids reviewed before apply"
    )
    args = parser.parse_args()
    only_ids = (
        {int(value) for value in args.only_ids.split(",")} if args.only_ids else None
    )
    if only_ids is not None and (not only_ids or any(value < 1 for value in only_ids)):
        parser.error("--only-ids requires positive market ids")
    if args.apply and args.census_only:
        parser.error("--apply and --census-only are mutually exclusive")
    if args.refresh_close_time and only_ids is None:
        parser.error("--refresh-close-time requires --only-ids")
    raise SystemExit(
        asyncio.run(
            run(
                apply=args.apply,
                census_only=args.census_only,
                only_ids=only_ids,
                refresh_close_time=args.refresh_close_time,
            )
        )
    )


if __name__ == "__main__":
    main()
