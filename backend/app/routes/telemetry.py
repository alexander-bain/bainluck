"""First-party client-timing sink (LAT-P232, #2751).

Stage 1 of the un-gated path designed in
``ARTIFACT-LAT-P231-the-ungated-path-design.md``.

WHAT THIS IS FOR. The felt number — how long after a tap the reader actually sees
a card — is computed in the browser on every screen arrival today
(``first_card_ms``, marked "🔴 THE NEEDLE" in ``lib/screenTiming.ts``) and then
thrown away, because its only transport is gtag and this lane holds no GA
credential. Every latency claim the lane makes is therefore a server-side proxy
for a wait it cannot see. This endpoint is where the number lands instead, so it
becomes readable via ``db-query`` with no vendor and no credential.

WHAT IT IS NOT. It is not new collection. The browser mirrors the
ALREADY-SANITIZED packet from inside ``trackEvent``'s ``sendEvent()``, after both
consent checks, for three event names only. Every field stored is one already
being sent to Google for that same reader in that same moment under that same
grant — and route-shaped fields are stored MORE coarsely here than GA gets them.
``app/utils/client_timing_contract.py`` holds the full claim and is the authority
on what may be stored.

Un-gating the beacon so it also describes readers who declined (Stage 2) is a
separate, larger question that is Alex's to rule on. Nothing here un-gates
anything.

RATE LIMITING. Deliberately none of its own. ``/api/telemetry`` is not in
``_EXEMPT_PREFIXES`` (``app/utils/rate_limit.py``), so the global
``RateLimitMiddleware`` already meters this path at the anonymous ceiling of
60 requests/minute per client IP — the repo's own tested mechanism, applied
without a second bespoke limiter to drift from it. ``test_telemetry_route.py``
asserts the non-exemption, so an exemption added later reds the suite rather
than silently opening a public write endpoint.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import ClientTimingEvent
from app.routes.admin_utils import _check_admin_secret
from app.services import get_db, get_db_rw
from app.utils.client_timing_contract import (
    ACCEPTED_EVENT_NAMES,
    MAX_EVENTS_PER_REQUEST,
    NOT_MEASURED,
    PROMOTED_DIMENSIONS,
    validate_packet,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/telemetry", tags=["telemetry"])


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------


class ClientTimingPacket(BaseModel):
    """One submitted packet. Both fields are re-validated by the contract."""

    name: str = Field(max_length=64)
    params: Dict[str, Any] = Field(default_factory=dict)


class ClientTimingBatch(BaseModel):
    """A beacon body.

    ``max_length`` bounds the batch at the schema layer so an oversized body is
    refused by FastAPI before any of it reaches the contract or the database.
    """

    events: List[ClientTimingPacket] = Field(
        default_factory=list, max_length=MAX_EVENTS_PER_REQUEST
    )


@router.post("/client-timing", status_code=202)
async def ingest_client_timing(
    request: Request,
    body: ClientTimingBatch,
    db: AsyncSession = Depends(get_db_rw),
) -> Dict[str, int]:
    """Accept a bounded batch of client performance packets.

    Unauthenticated by design — the same posture as ``POST
    /api/feedback/bug-report``, and for the same reason: the reader this measures
    is usually signed out, and requiring auth would bias the sample toward
    exactly the population whose latency we already understand.

    Refusal is per packet, never per batch: an unknown event name or a malformed
    value costs that packet (or that key) and nothing else. One bad item must not
    wipe the pass (gotcha #42). The response says how many of each so a client
    bug shows up as a rising ``rejected`` count rather than as silence.
    """
    accepted = 0
    rejected = 0
    rows: List[ClientTimingEvent] = []

    for packet in body.events:
        name, clean = validate_packet(packet.name, packet.params)
        if name is None:
            rejected += 1
            continue
        # A packet whose every key was dropped carries no measurement. Storing it
        # would add a row that can only dilute a denominator.
        if not clean:
            rejected += 1
            continue

        rows.append(
            ClientTimingEvent(
                event_name=name,
                params=clean,
                **{d: clean.get(d) for d in PROMOTED_DIMENSIONS},
            )
        )
        accepted += 1

    if rows:
        try:
            db.add_all(rows)
            await db.commit()
        except Exception:
            # A beacon must never surface a failure to the reader's page, and a
            # telemetry outage must never look like a healthy quiet sink — so it
            # is swallowed for the caller and LOUD in the log (gotcha #53:
            # "it returned" is not "it worked").
            await db.rollback()
            logger.exception(
                "client-timing ingest failed to persist %d packet(s)", len(rows)
            )
            return {"accepted": 0, "rejected": rejected + accepted, "stored": 0}

    return {"accepted": accepted, "rejected": rejected, "stored": len(rows)}


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

#: The metric each accepted event is summarised on.
_SUMMARY_METRIC = {
    "screen_timing": "first_card_ms",
    "feed_telemetry": "duration_ms",
    "web_vital": "metric_value",
}

MAX_WINDOW_HOURS = 720  # 30 days
MAX_SUMMARY_ROWS = 200


@router.get("/client-timing/summary")
async def client_timing_summary(
    request: Request,
    secret: str = Query(None, description="Admin secret"),
    event_name: str = Query("screen_timing"),
    hours: int = Query(24, ge=1, le=MAX_WINDOW_HOURS),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Percentiles for one event, grouped by surface and device class.

    Admin-gated: the ingest must be public for the sample to be honest, but an
    unbounded public aggregation endpoint is a free query engine. Reads are the
    lane's, via ``ADMIN_TOKEN``.

    ``NOT_MEASURED`` (``-1``) is counted, never averaged. It means "the surface
    never reached a first card", which is a different claim from "it was slow",
    and folding it into a percentile would report the surfaces that never
    finished as the fastest ones. ``not_measured`` beside ``measured`` is the
    whole reason the packet carries the marker instead of omitting the key.
    """
    _check_admin_secret(secret, request=request)

    if event_name not in ACCEPTED_EVENT_NAMES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown event_name. Expected one of: {sorted(ACCEPTED_EVENT_NAMES)}",
        )

    metric = _SUMMARY_METRIC[event_name]

    # `metric` and `event_name` are both closed-set lookups above, never caller
    # text, so the f-string cannot carry an injection. The window and the row cap
    # are bound parameters.
    sql = text(f"""
        WITH sample AS (
            SELECT
                COALESCE(surface, 'unknown')      AS surface,
                COALESCE(device_class, 'unknown') AS device_class,
                CASE
                    WHEN (params->>'{metric}') IS NULL THEN NULL
                    ELSE (params->>'{metric}')::numeric
                END AS metric_value
            FROM client_timing_events
            WHERE event_name = :event_name
              AND created_at >= now() - (CAST(:hours AS integer) * INTERVAL '1 hour')
        )
        SELECT
            surface,
            device_class,
            COUNT(*)                                          AS n,
            COUNT(*) FILTER (WHERE metric_value = :not_measured) AS not_measured,
            COUNT(*) FILTER (WHERE metric_value > :not_measured) AS measured,
            percentile_cont(0.50) WITHIN GROUP (
                ORDER BY metric_value
            ) FILTER (WHERE metric_value > :not_measured)     AS p50,
            percentile_cont(0.75) WITHIN GROUP (
                ORDER BY metric_value
            ) FILTER (WHERE metric_value > :not_measured)     AS p75,
            percentile_cont(0.95) WITHIN GROUP (
                ORDER BY metric_value
            ) FILTER (WHERE metric_value > :not_measured)     AS p95
        FROM sample
        GROUP BY surface, device_class
        ORDER BY n DESC
        LIMIT :row_cap
        """)

    result = await db.execute(
        sql,
        {
            "event_name": event_name,
            # CAST(:hours AS integer) is load-bearing: an UNTYPED bind sitting
            # beside an INTERVAL literal is resolved BY Postgres as an interval,
            # and `interval * interval` is not an operator — so the uncast form
            # fails at execution time, not at parse time, and would therefore
            # survive every test that does not touch a real database.
            "hours": hours,
            "not_measured": NOT_MEASURED,
            "row_cap": MAX_SUMMARY_ROWS,
        },
    )

    rows: List[Dict[str, Any]] = []
    for r in result.mappings():
        rows.append(
            {
                "surface": r["surface"],
                "device_class": r["device_class"],
                "n": int(r["n"]),
                "measured": int(r["measured"]),
                "not_measured": int(r["not_measured"]),
                "p50": _as_float(r["p50"]),
                "p75": _as_float(r["p75"]),
                "p95": _as_float(r["p95"]),
            }
        )

    return {
        "event_name": event_name,
        "metric": metric,
        "window_hours": hours,
        "row_count": len(rows),
        "truncated": len(rows) >= MAX_SUMMARY_ROWS,
        "rows": rows,
    }


def _as_float(value: Any) -> Optional[float]:
    """`percentile_cont` returns Decimal over a numeric column, not float."""
    return None if value is None else round(float(value), 1)
