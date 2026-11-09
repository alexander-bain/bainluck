"""Apple MetricKit diagnostics from consenting phones (#12309).

THE SHIP. We find out about hangs, slow launches and crashes on readers'
phones even when Crashlytics misses them (watchdog kills, memory terminations,
a crash before it starts), so a fix like #12278 starts from Apple's own call
stack rather than a guess.

WHAT ARRIVES. The app's `MetricKitForwarder12309` subscribes to MetricKit and,
ONLY for a reader who granted telemetry consent, posts each diagnostic (crash,
hang, CPU or disk-write exception, slow launch) on its own, and each day's
metrics, as one body: the kind, the version and device fields from the
payload's own metadata, and MetricKit's JSON untouched. A reader who declined
or never chose sends nothing, and the phone deletes anything it was holding
when consent goes. MetricKit carries no user identifier; this route adds none
and stores no IP, session or cookie (`MetricKitPayload` has no column for one).

RATE LIMITING. Deliberately none of its own, as for
``/api/telemetry/client-timing``: ``/api/telemetry`` is not in
``_EXEMPT_PREFIXES`` (``app/utils/rate_limit.py``), so the global
``RateLimitMiddleware`` meters this path at the anonymous ceiling of 60
requests/minute per client IP. ``test_metrickit_route.py`` asserts the
non-exemption.

SIZE. The body is read with a hard cap BEFORE it is parsed, so an oversized
body is refused with 413 without being held in memory whole.

RETENTION. Rows older than `RETENTION_DAYS` are deleted by the ingest path, at
most once per `PRUNE_EVERY_SECONDS` per process.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import MetricKitPayload
from app.routes.admin_utils import _check_admin_secret
from app.services import get_db, get_db_rw

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/telemetry/metrickit", tags=["telemetry"])

#: One row per MetricKit diagnostic, by its class, or per day's metrics. The
#: app's `MetricKitRecord12309.Kind` is the same set.
ACCEPTED_KINDS = frozenset({"crash", "hang", "cpu_exception", "disk_write", "launch", "metrics"})

#: The largest body accepted. One diagnostic's call-stack tree is tens of
#: kilobytes and a day's metrics a few; the app drops anything larger before
#: sending (`MetricKitRecord12309.maxBodyBytes`, the same number).
MAX_BODY_BYTES = 512 * 1024

RETENTION_DAYS = 30
PRUNE_EVERY_SECONDS = 3600

#: `time.monotonic()` of the last retention sweep in this process.
_last_prune: float = 0.0

RECENT_DIAGNOSTICS = 25
MAX_SUMMARY_ROWS = 200


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------


class MetricKitSubmission(BaseModel):
    """One body. Unknown top-level keys are ignored, never stored."""

    kind: str = Field(max_length=16)
    app_version: Optional[str] = Field(default=None, max_length=64)
    app_build: Optional[str] = Field(default=None, max_length=64)
    os_version: Optional[str] = Field(default=None, max_length=64)
    device_type: Optional[str] = Field(default=None, max_length=64)
    #: MetricKit's own JSON for this diagnostic or day: always an object.
    payload: Dict[str, Any]


async def _read_bounded(request: Request, cap: int) -> bytes:
    """The request body, refused with 413 as soon as it passes ``cap`` bytes.

    A declared ``Content-Length`` over the cap is refused before anything is
    read; a body sent without one (chunked) is refused the moment it passes.
    """
    declared = request.headers.get("content-length")
    if declared is not None:
        try:
            declared_bytes = int(declared)
        except ValueError:
            raise HTTPException(status_code=400, detail="Bad Content-Length")
        if declared_bytes > cap:
            raise HTTPException(status_code=413, detail=f"Body over {cap} bytes")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > cap:
            raise HTTPException(status_code=413, detail=f"Body over {cap} bytes")
    return bytes(body)


async def _maybe_prune(db: AsyncSession) -> None:
    """Delete rows past retention, at most once per `PRUNE_EVERY_SECONDS`.

    A failed sweep is logged loudly and never costs the payload that was just
    stored: it runs after that commit.
    """
    global _last_prune
    now = time.monotonic()
    if now - _last_prune < PRUNE_EVERY_SECONDS:
        return
    _last_prune = now
    try:
        # CAST(:days AS integer) is load-bearing: an untyped bind beside an
        # INTERVAL literal is resolved by Postgres as an interval, and
        # `interval * interval` is not an operator (see telemetry.py).
        await db.execute(
            text(
                "DELETE FROM metrickit_payloads "
                "WHERE received_at < now() - (CAST(:days AS integer) * INTERVAL '1 day')"
            ),
            {"days": RETENTION_DAYS},
        )
        await db.commit()
    except Exception:
        await db.rollback()
        logger.exception("metrickit retention sweep failed")


@router.post("", status_code=202)
async def ingest_metrickit(
    request: Request,
    db: AsyncSession = Depends(get_db_rw),
) -> Dict[str, int]:
    """Store one MetricKit diagnostic or day's metrics.

    Unauthenticated by design, as ``POST /api/feedback/bug-report`` and
    ``POST /api/telemetry/client-timing`` are: most readers are signed out, and
    the row must not be attributable to anyone anyway.

    A body the phone could never fix (unknown kind, malformed JSON, a payload
    that is not an object, an oversized body) is refused with 4xx, and the
    phone drops it. A body that failed to SAVE is answered 503, and the phone
    keeps it and tries again: "it returned" is not "it worked" (gotcha #53).
    """
    raw = await _read_bounded(request, MAX_BODY_BYTES)
    try:
        submission = MetricKitSubmission.model_validate_json(raw)
    except ValidationError:
        # The detail is a fixed sentence: the validation errors would echo the
        # submitted values back.
        raise HTTPException(status_code=422, detail="Not a MetricKit submission")
    if submission.kind not in ACCEPTED_KINDS:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown kind. Expected one of: {sorted(ACCEPTED_KINDS)}",
        )

    row = MetricKitPayload(
        kind=submission.kind,
        app_version=submission.app_version,
        app_build=submission.app_build,
        os_version=submission.os_version,
        device_type=submission.device_type,
        payload=submission.payload,
        payload_bytes=len(json.dumps(submission.payload, separators=(",", ":")).encode()),
    )
    try:
        db.add(row)
        await db.commit()
    except Exception:
        await db.rollback()
        logger.exception("metrickit ingest failed to persist one %s payload", submission.kind)
        raise HTTPException(status_code=503, detail="Not stored; try again later")

    await _maybe_prune(db)
    return {"stored": 1}


# ---------------------------------------------------------------------------
# Read (admin)
# ---------------------------------------------------------------------------


@router.get("/summary")
async def metrickit_summary(
    request: Request,
    secret: str = Query(None, description="Admin secret"),
    days: int = Query(7, ge=1, le=RETENTION_DAYS),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Counts by kind and app version, and the newest diagnostics to open.

    Admin-gated, as the client-timing summary is: the ingest must be public,
    but a public read would hand anyone the app's crash stacks.
    """
    _check_admin_secret(secret, request=request)

    window = "received_at >= now() - (CAST(:days AS integer) * INTERVAL '1 day')"
    counts = await db.execute(
        text(f"""
            SELECT kind, COALESCE(app_version, 'unknown') AS app_version, COUNT(*) AS n
            FROM metrickit_payloads
            WHERE {window}
            GROUP BY kind, COALESCE(app_version, 'unknown')
            ORDER BY n DESC
            LIMIT :row_cap
        """),
        {"days": days, "row_cap": MAX_SUMMARY_ROWS},
    )
    recent = await db.execute(
        text(f"""
            SELECT id, kind, received_at, app_version, app_build, os_version,
                   device_type, payload_bytes
            FROM metrickit_payloads
            WHERE kind <> 'metrics' AND {window}
            ORDER BY received_at DESC
            LIMIT :recent
        """),
        {"days": days, "recent": RECENT_DIAGNOSTICS},
    )
    by_kind: List[Dict[str, Any]] = [
        {"kind": r.kind, "app_version": r.app_version, "n": int(r.n)} for r in counts
    ]
    diagnostics: List[Dict[str, Any]] = [
        {
            "id": r.id,
            "kind": r.kind,
            "received_at": r.received_at.isoformat() if r.received_at else None,
            "app_version": r.app_version,
            "app_build": r.app_build,
            "os_version": r.os_version,
            "device_type": r.device_type,
            "payload_bytes": r.payload_bytes,
        }
        for r in recent
    ]
    return {"window_days": days, "by_kind_and_version": by_kind, "recent_diagnostics": diagnostics}


@router.get("/{payload_id}")
async def metrickit_payload(
    payload_id: int,
    request: Request,
    secret: str = Query(None, description="Admin secret"),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """One stored diagnostic, its MetricKit JSON whole: the stack to start from."""
    _check_admin_secret(secret, request=request)
    row = (
        await db.execute(select(MetricKitPayload).where(MetricKitPayload.id == payload_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="No such payload")
    return {
        "id": row.id,
        "kind": row.kind,
        "received_at": row.received_at.isoformat() if row.received_at else None,
        "app_version": row.app_version,
        "app_build": row.app_build,
        "os_version": row.os_version,
        "device_type": row.device_type,
        "payload_bytes": row.payload_bytes,
        "payload": row.payload,
    }
