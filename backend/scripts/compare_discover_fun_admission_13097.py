#!/usr/bin/env python3
"""#13097 (Rulings 272: A / 273: B) — read-only before/after comparison for fun admission.

Runs strictly inside ``SET TRANSACTION READ ONLY`` with Redis cache reads/writes
disabled in-process so it cannot write to Postgres or Redis.

Reports:
1. Per-guard drop counts across the 101 seeded fun markets (plus the 2 excluded
   Taylor Swift wedding markets from the original 103-market pass) at both the
   proposed 10,000 lifetime-volume bar and a 5,000 sensitivity check.
2. Side-by-side first 30 Discover seats BEFORE (``DISCOVER_FUN_ADMISSION_ENABLED=0``)
   vs AFTER (``DISCOVER_FUN_ADMISSION_ENABLED=1``), built through the real
   ``get_feed`` pipeline.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import Response  # noqa: E402
from sqlalchemy import select, text  # noqa: E402
from starlette.requests import Request as ASGIRequest  # noqa: E402

from app.models.models import FuturesMarket  # noqa: E402
from app.routes import feed as feed_mod  # noqa: E402
from app.tasks.base import get_task_session  # noqa: E402
from app.utils import candidate_base as candidate_base_mod  # noqa: E402
from app.utils import request_cache as request_cache_mod  # noqa: E402
from app.utils.discover_fun_tags import (  # noqa: E402
    DISCOVER_FUN_ADMISSION_ENV,
    DISCOVER_FUN_MIN_LIFETIME_VOLUME_ENV,
    FUN_TAG_DEFAULT_MIN_LIFETIME_VOLUME,
    evaluate_fun_market_guards,
    get_fun_market_entry,
    load_fun_markets_registry,
)

# The two Taylor Swift wedding markets from the original 103-market seed pass
# (removed at 1:10 PM PT under Ruling 273: B; checked here so the guard report
# proves Check 3 catches them even if re-proposed).
EXCLUDED_ORIGINAL_SEED_IDS = (52755900, 113799)


@contextmanager
def _env_override(values: dict[str, str | None]) -> Iterator[None]:
    prior = {k: os.environ.get(k) for k in values}
    try:
        for k, v in values.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        yield
    finally:
        for k, v in prior.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


@contextmanager
def _no_cache_side_effects() -> Iterator[None]:
    """Disable Redis reads/writes and background cache publication in-process."""
    orig_get_redis = request_cache_mod.get_shared_async_redis
    orig_schedule = request_cache_mod.schedule_background

    async def _no_redis() -> None:
        return None

    def _noop_schedule(coro: Any) -> None:
        if hasattr(coro, "close"):
            coro.close()

    request_cache_mod.get_shared_async_redis = _no_redis  # type: ignore[assignment]
    request_cache_mod.schedule_background = _noop_schedule  # type: ignore[assignment]
    candidate_base_mod._reset_l0_for_tests()
    try:
        yield
    finally:
        request_cache_mod.get_shared_async_redis = orig_get_redis  # type: ignore[assignment]
        request_cache_mod.schedule_background = orig_schedule  # type: ignore[assignment]
        candidate_base_mod._reset_l0_for_tests()


def _fake_request() -> ASGIRequest:
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "https",
        "path": "/api/feed",
        "raw_path": b"/api/feed",
        "query_string": b"limit=50&offset=0&event_pct=0.15&mode=discover",
        "headers": [],
        "client": ("127.0.0.1", 0),
        "server": ("api.bainluck.com", 443),
    }
    return ASGIRequest(scope)


def _summarize_seat(seat: int, item: dict[str, Any]) -> dict[str, Any]:
    item_type = str(item.get("type") or "")
    data = item.get("data") or {}
    market_id = data.get("id") if item_type == "futures" else None
    entry = get_fun_market_entry(int(market_id)) if market_id is not None else None
    title = (
        data.get("name")
        or data.get("title")
        or item.get("headline")
        or f"{data.get('away_team_name', '')} @ {data.get('home_team_name', '')}".strip(" @")
    )
    return {
        "seat": seat,
        "type": item_type,
        "id": data.get("id") or data.get("slug") or item.get("id"),
        "title": str(title or "")[:90],
        "score": item.get("score"),
        "category": data.get("llm_sport_category") or data.get("category") or data.get("sport"),
        "fun_tags": list(entry.sub_tags) if entry is not None else [],
        "fun_bucket": entry.fun_bucket if entry is not None else None,
    }


async def _run_comparison(
    *,
    min_lifetime_volume: int,
    seats: int,
    machinery: int | None,
    as_json: bool,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    registry = load_fun_markets_registry()
    audit_ids = list(registry.ordered_market_ids) + [
        mid
        for mid in EXCLUDED_ORIGINAL_SEED_IDS
        if mid not in registry.markets
    ]

    async with get_task_session() as db:
        await db.execute(text("SET TRANSACTION READ ONLY"))

        rows_res = await db.execute(
            select(
                FuturesMarket.id,
                FuturesMarket.name,
                FuturesMarket.description,
                FuturesMarket.source,
                FuturesMarket.status,
                FuturesMarket.event_id,
                FuturesMarket.volume,
                FuturesMarket.volume_24h,
                FuturesMarket.resolution_date,
                FuturesMarket.llm_sport_category,
                FuturesMarket.market_metadata,
            ).where(FuturesMarket.id.in_(audit_ids))
        )
        rows_by_id = {int(r.id): r for r in rows_res.all()}

        def _audit_at_bar(bar: int) -> dict[str, Any]:
            missing = []
            passed = []
            dropped_trading = []
            dropped_taste = []
            dropped_ahead = []
            for mid in registry.ordered_market_ids:
                entry = registry.markets[mid]
                row = rows_by_id.get(mid)
                if row is None:
                    missing.append({"id": mid, "title": entry.title})
                    continue
                verdict = evaluate_fun_market_guards(
                    title=row.name,
                    description=row.description,
                    status=row.status,
                    volume=row.volume,
                    resolution_date=row.resolution_date,
                    sport_category=row.llm_sport_category,
                    market_metadata=row.market_metadata,
                    now=now,
                    entry=entry,
                    min_lifetime_volume=bar,
                    concluded_events=registry.concluded_events,
                )
                rec = {
                    "id": mid,
                    "title": row.name,
                    "source": row.source,
                    "volume": row.volume,
                    "volume_24h": row.volume_24h,
                    "stored_category": row.llm_sport_category,
                    "fun_category": entry.discover_category,
                    "sub_tags": list(entry.sub_tags),
                    "reasons": list(verdict.reasons),
                }
                if verdict.passed:
                    passed.append(rec)
                if not verdict.passed_real_trading:
                    dropped_trading.append(rec)
                if not verdict.passed_taste:
                    dropped_taste.append(rec)
                if not verdict.passed_still_ahead:
                    dropped_ahead.append(rec)
            return {
                "bar": bar,
                "seed_count": len(registry.ordered_market_ids),
                "missing_from_db": missing,
                "passed_count": len(passed),
                "dropped_real_trading_count": len(dropped_trading),
                "dropped_taste_count": len(dropped_taste),
                "dropped_still_ahead_count": len(dropped_ahead),
                "dropped_real_trading": dropped_trading,
                "dropped_taste": dropped_taste,
                "dropped_still_ahead": dropped_ahead,
            }

        audit_primary = _audit_at_bar(min_lifetime_volume)
        audit_5k = _audit_at_bar(5_000)

        excluded_wedding_audit = []
        for mid in EXCLUDED_ORIGINAL_SEED_IDS:
            row = rows_by_id.get(mid)
            if row is None:
                continue
            verdict = evaluate_fun_market_guards(
                title=row.name,
                description=row.description,
                status=row.status,
                volume=row.volume,
                resolution_date=row.resolution_date,
                sport_category=row.llm_sport_category,
                market_metadata=row.market_metadata,
                now=now,
                min_lifetime_volume=min_lifetime_volume,
                concluded_events=registry.concluded_events,
            )
            excluded_wedding_audit.append(
                {
                    "id": mid,
                    "title": row.name,
                    "status": row.status,
                    "volume": row.volume,
                    "passed": verdict.passed,
                    "reasons": list(verdict.reasons),
                }
            )

        with _no_cache_side_effects():
            with _env_override(
                {
                    DISCOVER_FUN_ADMISSION_ENV: "0",
                    DISCOVER_FUN_MIN_LIFETIME_VOLUME_ENV: str(min_lifetime_volume),
                }
            ):
                before_resp = await feed_mod.get_feed(
                    response=Response(),
                    request=_fake_request(),
                    limit=max(50, seats),
                    offset=0,
                    sport=None,
                    category=None,
                    include_events=True,
                    include_futures=True,
                    my_teams_only=False,
                    mode="discover",
                    tags=None,
                    event_pct=0.15,
                    edition=None,
                    debug=False,
                    debug_ground_truth=False,
                    debug_personalization=False,
                    exclude_reviewed=False,
                    reviewer=None,
                    reviewed_surface=None,
                    machinery=machinery,
                    secret=None,
                    db=db,
                    user=None,
                )

            with _env_override(
                {
                    DISCOVER_FUN_ADMISSION_ENV: "1",
                    DISCOVER_FUN_MIN_LIFETIME_VOLUME_ENV: str(min_lifetime_volume),
                }
            ):
                after_resp = await feed_mod.get_feed(
                    response=Response(),
                    request=_fake_request(),
                    limit=max(50, seats),
                    offset=0,
                    sport=None,
                    category=None,
                    include_events=True,
                    include_futures=True,
                    my_teams_only=False,
                    mode="discover",
                    tags=None,
                    event_pct=0.15,
                    edition=None,
                    debug=False,
                    debug_ground_truth=False,
                    debug_personalization=False,
                    exclude_reviewed=False,
                    reviewer=None,
                    reviewed_surface=None,
                    machinery=machinery,
                    secret=None,
                    db=db,
                    user=None,
                )

        await db.rollback()

    before_items = (before_resp.get("items") or [])[:seats]
    after_items = (after_resp.get("items") or [])[:seats]
    before_seats = [_summarize_seat(i + 1, item) for i, item in enumerate(before_items)]
    after_seats = [_summarize_seat(i + 1, item) for i, item in enumerate(after_items)]

    before_all_fun = [
        _summarize_seat(i + 1, item)
        for i, item in enumerate(before_resp.get("items") or [])
        if item.get("type") == "futures"
        and (item.get("data") or {}).get("id") in registry.markets
    ]
    after_all_fun = [
        _summarize_seat(i + 1, item)
        for i, item in enumerate(after_resp.get("items") or [])
        if item.get("type") == "futures"
        and (item.get("data") or {}).get("id") in registry.markets
    ]

    report = {
        "generated_at_utc": now.isoformat(),
        "min_lifetime_volume": min_lifetime_volume,
        "machinery": machinery,
        "guard_audit": audit_primary,
        "guard_audit_5k": {
            "bar": audit_5k["bar"],
            "passed_count": audit_5k["passed_count"],
            "dropped_real_trading_count": audit_5k["dropped_real_trading_count"],
            "dropped_taste_count": audit_5k["dropped_taste_count"],
            "dropped_still_ahead_count": audit_5k["dropped_still_ahead_count"],
        },
        "excluded_wedding_audit": excluded_wedding_audit,
        "before_total_items": len(before_resp.get("items") or []),
        "after_total_items": len(after_resp.get("items") or []),
        "before_top_seats": before_seats,
        "after_top_seats": after_seats,
        "before_fun_in_feed": before_all_fun,
        "after_fun_in_feed": after_all_fun,
    }
    if as_json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(f"=== #13097 Fun Admission Read-Only Comparison ({now.isoformat()}) ===")
        print(
            f"Seed list: {audit_primary['seed_count']} markets | bar={min_lifetime_volume:,} -> "
            f"passed={audit_primary['passed_count']}, "
            f"dropped_real_trading={audit_primary['dropped_real_trading_count']}, "
            f"dropped_taste={audit_primary['dropped_taste_count']}, "
            f"dropped_still_ahead={audit_primary['dropped_still_ahead_count']}"
        )
        print(
            f"Sensitivity at bar=5,000 -> passed={audit_5k['passed_count']}, "
            f"dropped_real_trading={audit_5k['dropped_real_trading_count']}"
        )
        print("Excluded original wedding markets:")
        for row in excluded_wedding_audit:
            print(f"  - {row['id']} ({row['title']}): passed={row['passed']} reasons={row['reasons']}")
        print(f"\nFun markets in returned page: BEFORE={len(before_all_fun)}, AFTER={len(after_all_fun)}")
        print(f"\n=== First {seats} Seats: BEFORE vs AFTER ===")
        print(f"{'Seat':>4} | {'BEFORE (switch OFF)':<52} | {'AFTER (switch ON)':<52}")
        print("-" * 116)
        for idx in range(seats):
            b = before_seats[idx] if idx < len(before_seats) else None
            a = after_seats[idx] if idx < len(after_seats) else None
            b_txt = (
                f"{'[FUN] ' if b['fun_tags'] else ''}{b['type']}:{b['id']} {b['title']}"[:52]
                if b
                else ""
            )
            a_txt = (
                f"{'[FUN] ' if a['fun_tags'] else ''}{a['type']}:{a['id']} {a['title']}"[:52]
                if a
                else ""
            )
            print(f"{idx + 1:>4} | {b_txt:<52} | {a_txt:<52}")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only before/after comparison of Discover fun-market admission (#13097)."
    )
    parser.add_argument(
        "--min-volume",
        type=int,
        default=FUN_TAG_DEFAULT_MIN_LIFETIME_VOLUME,
        help="Minimum lifetime trading bar (default: 10000).",
    )
    parser.add_argument(
        "--seats",
        type=int,
        default=30,
        help="Number of leading Discover seats to compare (default: 30).",
    )
    parser.add_argument(
        "--machinery",
        type=int,
        default=None,
        help="Optional machinery query param (e.g. 1).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit full JSON report.",
    )
    args = parser.parse_args()
    asyncio.run(
        _run_comparison(
            min_lifetime_volume=args.min_volume,
            seats=args.seats,
            machinery=args.machinery,
            as_json=args.json,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
