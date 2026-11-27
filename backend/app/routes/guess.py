"""Daily /guess challenge and group-board API routes (#12619, 443: A).

Privacy & product guarantees:
- Persists ONLY `(day_pt, group_code, nickname, answers, step_times)`. Zero
  accounts, device IDs, IP addresses, or client-submitted scores stored.
- Server resolves & freezes each PT day's pack once from open markets, swaps
  closed/unpriced cards for that day's spare, and never fabricates numbers.
- Strictly one board per random group link; zero public board endpoints.
"""

from __future__ import annotations

import asyncio
import hashlib
import secrets
import time
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import GuessGroupEntry
from app.services.database import get_db_rw
from app.utils.guess_daily import (
    MAX_GROUP_ENTRIES,
    _GROUP_LOCK_NS,
    _acquire_advisory_lock,
    build_group_board_payload,
    clean_nickname,
    get_or_freeze_daily_edition,
    group_lock_key,
    score_answers,
    today_pt,
    validate_group_code,
    GuessEditionNotFoundError,
    GuessEditionUnavailableError,
    GuessInvalidGroupCodeError,
    GuessInvalidSubmissionError,
)
from app.utils.rate_limit import _get_async_rl_redis

router = APIRouter(prefix="/api/guess", tags=["guess"])

_CLIENT_WINDOW_S = 300
_CLIENT_LIMIT = 8
_GROUP_WINDOW_S = 60
_GROUP_LIMIT = 20

# Ephemeral per-process salt so rate-limit keys hold no recoverable IP address.
_EPHEMERAL_SALT = secrets.token_hex(16)
_MEM_BUCKETS: dict[str, tuple[int, int]] = {}


def _reset_rate_limits_for_tests() -> None:
    """Clear in-memory fallback burst counters between unit tests."""
    _MEM_BUCKETS.clear()


def _ephemeral_client_bucket(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for") or ""
    first_ip = xff.split(",")[0].strip() if xff else ""
    raw = first_ip or (request.client.host if request.client else "") or "anonymous"
    return hashlib.sha256(f"{_EPHEMERAL_SALT}:{raw}".encode("utf-8")).hexdigest()[:24]


async def _hit_window(key: str, window_s: int, now_s: int) -> int:
    bucket = now_s // window_s
    full_key = f"guess_rl:{key}:{bucket}"

    redis_cli = _get_async_rl_redis()
    if redis_cli is not None:
        try:
            count = await asyncio.wait_for(redis_cli.incr(full_key), timeout=1.0)
            if int(count) == 1:
                await asyncio.wait_for(redis_cli.expire(full_key, window_s + 5), timeout=1.0)
            return int(count)
        except Exception:
            pass

    if len(_MEM_BUCKETS) > 2048:
        stale = [k for k, (b, _) in _MEM_BUCKETS.items() if k.endswith(f":{b}") and now_s // window_s > b + 2]
        for k in stale[:1024]:
            _MEM_BUCKETS.pop(k, None)
        if len(_MEM_BUCKETS) > 2048:
            _MEM_BUCKETS.clear()

    prev_bucket, prev_count = _MEM_BUCKETS.get(full_key, (bucket, 0))
    next_count = (prev_count + 1) if prev_bucket == bucket else 1
    _MEM_BUCKETS[full_key] = (bucket, next_count)
    return next_count


async def _enforce_guess_burst_limits(request: Request, group_code: str) -> None:
    now_s = int(time.time())
    client_count = await _hit_window(
        f"c:{_ephemeral_client_bucket(request)}", _CLIENT_WINDOW_S, now_s
    )
    if client_count > _CLIENT_LIMIT:
        raise HTTPException(
            status_code=429,
            detail="Too many games sent from here right now. Please try again in a few minutes.",
        )
    group_count = await _hit_window(f"g:{group_code}", _GROUP_WINDOW_S, now_s)
    if group_count > _GROUP_LIMIT:
        raise HTTPException(
            status_code=429,
            detail="This group board is busy right now. Please try again in a minute.",
        )


class GuessEntrySubmission(BaseModel):
    """Strict payload accepting ONLY answers and step times — never client scores."""

    model_config = ConfigDict(extra="forbid")

    day: Optional[date] = None
    nickname: str = Field(..., min_length=1, max_length=32)
    answers: list[int] = Field(..., min_length=15, max_length=15)
    step_times: list[int] = Field(..., min_length=3, max_length=3)


@router.get("/today")
async def get_today_guess_pack(
    day: Optional[date] = Query(default=None),
    db: AsyncSession = Depends(get_db_rw),
):
    """Return today's (or an active retained day's) frozen 15-card edition."""
    try:
        edition = await get_or_freeze_daily_edition(db, day)
    except GuessEditionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except GuessEditionUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    current_pt = today_pt()
    return {
        "day": edition.day_pt.isoformat(),
        "today_day": current_pt.isoformat(),
        "is_today": edition.day_pt == current_pt,
        "edition_code": edition.edition_code,
        "frozen_at": edition.frozen_at.isoformat(),
        "pack": edition.pack_json,
    }


@router.get("/groups/{group_code}")
async def get_guess_group_board(
    group_code: str,
    day: Optional[date] = Query(default=None),
    db: AsyncSession = Depends(get_db_rw),
):
    """Return stored finished entries for one group link on an active PT day."""
    try:
        clean_code = validate_group_code(group_code)
        edition = await get_or_freeze_daily_edition(db, day)
    except GuessInvalidGroupCodeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except GuessEditionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except GuessEditionUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return await build_group_board_payload(db, edition, clean_code)


@router.post("/groups/{group_code}/entries", status_code=201)
async def submit_guess_group_entry(
    group_code: str,
    payload: GuessEntrySubmission,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db_rw),
):
    """Save one finished game on a group board; computes scores purely on the server."""
    try:
        clean_code = validate_group_code(group_code)
    except GuessInvalidGroupCodeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    nickname = clean_nickname(payload.nickname)
    if not nickname:
        raise HTTPException(status_code=422, detail="Please type a valid nickname.")

    await _enforce_guess_burst_limits(request, clean_code)

    try:
        edition = await get_or_freeze_daily_edition(db, payload.day)
        scored = score_answers(edition.pack_json, payload.answers, payload.step_times)
    except GuessEditionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except GuessEditionUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except GuessInvalidSubmissionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    await _acquire_advisory_lock(
        db, _GROUP_LOCK_NS, group_lock_key(edition.day_pt, clean_code)
    )

    existing = await db.scalar(
        select(GuessGroupEntry).where(
            GuessGroupEntry.day_pt == edition.day_pt,
            GuessGroupEntry.group_code == clean_code,
            GuessGroupEntry.nickname_lower == nickname.lower(),
        )
    )
    if existing is not None:
        if (
            list(existing.answers) == scored["answers"]
            and list(existing.step_times) == scored["step_times"]
        ):
            response.status_code = 200
            return await build_group_board_payload(db, edition, clean_code)
        raise HTTPException(
            status_code=409,
            detail="That nickname already finished in this group today.",
        )

    entry_count = await db.scalar(
        select(func.count(GuessGroupEntry.id)).where(
            GuessGroupEntry.day_pt == edition.day_pt,
            GuessGroupEntry.group_code == clean_code,
        )
    )
    if int(entry_count or 0) >= MAX_GROUP_ENTRIES:
        raise HTTPException(
            status_code=429,
            detail="This group board already has 30 finished games for today.",
        )

    db.add(
        GuessGroupEntry(
            day_pt=edition.day_pt,
            group_code=clean_code,
            nickname=nickname,
            nickname_lower=nickname.lower(),
            answers=scored["answers"],
            step_times=scored["step_times"],
        )
    )
    await db.flush()
    await db.commit()
    return await build_group_board_payload(db, edition, clean_code)
