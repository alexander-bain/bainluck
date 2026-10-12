"""Gamma event → the rows ingestion would store. Shared by the #5343 tests.

Mirrors ``app/tasks/polymarket.py``'s futures ingest for a non-negRisk,
multi-market event: one PARENT row (``external_id = event.id``, metadata
``polymarket_event_id`` / ``event_title`` / ``polymarket_event_slug`` /
``market_count``) and one CHILD per market whose Yes price is positive
(``external_id = conditionId``, metadata ``polymarket_event_id`` as a string and
the slug), every row on ``group_id = 'polymarket:{id}'``. A market whose Yes
price is zero is skipped, as ingestion skips it.

``roster_at`` stamps the PROPOSED ``polymarket_event_roster`` key on the parent:
builder-owned input standing in for the ingestion field that does not exist yet.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

FIXTURES = Path(__file__).parent / "fixtures"
GAMMA_FILES = {
    "1038648": FIXTURES / "polymarket_leg_dates_8466" / "gamma-event-1038648.json",
    "106884": FIXTURES / "provider_event_collections_5343" / "gamma-event-106884.json",
    "86832": FIXTURES / "provider_event_collections_5343" / "gamma-event-86832.json",
    "145916": FIXTURES / "provider_event_collections_5343" / "gamma-event-145916.json",
}


def load_gamma(event_id: str) -> dict:
    return json.loads(GAMMA_FILES[event_id].read_text())


def _instant(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)


def _yes_price(market: dict) -> float:
    try:
        return float(json.loads(market.get("outcomePrices") or "[]")[0])
    except (ValueError, IndexError, TypeError):
        return 0.0


def _resolved_zero(market: dict) -> bool:
    try:
        prices = json.loads(market.get("outcomePrices") or "[]")
    except ValueError:
        return False
    return (
        market.get("closed") is True
        and market.get("umaResolutionStatus") == "resolved"
        and prices == ["0", "1"]
    )


def roster_payload(
    event: dict, observed_at: datetime, *, drop: tuple = (), extra: tuple = ()
) -> dict:
    markets = [
        {"id": m["conditionId"], "closed": bool(m.get("closed"))}
        for m in event["markets"]
        if m["conditionId"] not in drop
    ]
    markets += [{"id": cid, "closed": False} for cid in extra]
    return {
        "observed_at": observed_at.isoformat(),
        "complete": True,
        "event_closed": bool(event.get("closed")),
        "markets": markets,
    }


def ingested_rows(
    event: dict,
    domain: str,
    *,
    first_id: int,
    roster_at: Optional[datetime] = None,
    title: Optional[str] = None,
    store_resolved_zero: bool = False,
) -> list[dict]:
    """Plain dicts, one per stored row, ids from ``first_id`` (parent first).

    ``store_resolved_zero`` models Live's mount 2 (narrow arm): a closed leg with
    ``umaResolutionStatus == "resolved"`` and prices exactly ``["0", "1"]`` is
    stored as a resolved row instead of skipped. Off, rows are today's ingestion.
    """
    event_id = str(event["id"])
    group_id = f"polymarket:{event_id}"
    parent_meta = {
        "polymarket_event_id": event_id,
        "event_title": title or event["title"],
        "polymarket_event_slug": event["slug"],
        "market_count": len(event["markets"]),
    }
    if roster_at is not None:
        parent_meta["polymarket_event_roster"] = roster_payload(event, roster_at)
    rows = [
        {
            "id": first_id,
            "source": "polymarket",
            "external_id": event_id,
            "group_id": group_id,
            "status": "resolved" if event.get("closed") else "open",
            "name": title or event["title"],
            "llm_sport_category": domain,
            "commence_time": _instant(event.get("startDate")),
            "resolution_date": _instant(event.get("endDate")),
            "market_metadata": parent_meta,
        }
    ]
    next_id = first_id + 1
    for market in event["markets"]:
        if _yes_price(market) <= 0 and not (
            store_resolved_zero and _resolved_zero(market)
        ):
            continue
        rows.append(
            {
                "id": next_id,
                "source": "polymarket",
                "external_id": market["conditionId"],
                "group_id": group_id,
                "status": "resolved" if market.get("closed") else "open",
                "name": market["question"],
                "llm_sport_category": domain,
                "commence_time": _instant(event.get("startDate")),
                "resolution_date": _instant(market.get("endDate")),
                "market_metadata": {
                    "polymarket_event_id": event_id,
                    "polymarket_event_slug": event["slug"],
                },
            }
        )
        next_id += 1
    return rows
