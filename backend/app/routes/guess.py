"""Daily /guess challenge and group-board API routes (#12619, 443: A).

Privacy & product guarantees:
- Persists ONLY `(day_pt, group_code, nickname, answers, step_times)`. Zero
  accounts, device IDs, IP addresses, or client-submitted scores stored.
- Server resolves & freezes each PT day's pack once from open markets, swaps
  closed/unpriced cards for that day's spare, and never fabricates numbers.
- Public board (`/api/guess/board`) serves one paged snapshot across visible games
  with zero `group_code` fields and a 60-second shared cache, plus admin `hidden_at` hiding.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import secrets
import time
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import GuessGroupEntry
from app.routes.admin_utils import _check_admin_secret, admin_account_identity
from app.services.database import get_db_rw
from app.utils.guess_daily import (
    GROUP_LOCK_NS,
    MAX_DAILY_ENTRIES,
    MAX_GROUP_ENTRIES,
    RETENTION_DAYS,
    _acquire_advisory_lock,
    build_group_board_payload,
    build_public_board_snapshot,
    get_or_freeze_daily_edition,
    group_lock_key,
    score_answers,
    slice_public_board_page,
    today_pt,
    validate_group_code,
    validate_nickname,
    GuessEditionNotFoundError,
    GuessEditionUnavailableError,
    GuessEditionUnscheduledError,
    GuessInvalidGroupCodeError,
    GuessInvalidSubmissionError,
)
from app.utils.rate_limit import _get_async_rl_redis, _router_peer_ip

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/guess", tags=["guess"])

_CLIENT_WINDOW_S = 300
_CLIENT_LIMIT = 8
_GROUP_WINDOW_S = 60
_GROUP_LIMIT = 20
_SALT_TTL_S = 172800
_PUBLIC_BOARD_CACHE_TTL_S = 60
_PUBLIC_BOARD_CACHE_PREFIX = "guess_pub:board:v1:"

# Process-local cache of `(day_key, salt, from_redis)` plus bounded in-memory
# fallbacks when Redis is unavailable (never logged or returned to clients).
_CACHED_SALT: tuple[str, str, bool] = ("", "", False)
_FALLBACK_SALTS: dict[str, str] = {}
_MEM_BUCKETS: dict[str, tuple[int, int]] = {}
_DAILY_CEILING_LOGGED_DAYS: set[date] = set()
_PUBLIC_BOARD_MEM_CACHE: dict[str, tuple[float, dict]] = {}


def _reset_rate_limits_for_tests() -> None:
    """Clear in-memory fallback burst counters and salt caches between tests."""
    global _CACHED_SALT
    _CACHED_SALT = ("", "", False)
    _FALLBACK_SALTS.clear()
    _MEM_BUCKETS.clear()
    _DAILY_CEILING_LOGGED_DAYS.clear()
    _PUBLIC_BOARD_MEM_CACHE.clear()


async def _get_cached_public_board(day_key: str) -> Optional[dict]:
    redis_cli = _get_async_rl_redis()
    if redis_cli is not None:
        try:
            raw = await asyncio.wait_for(
                redis_cli.get(f"{_PUBLIC_BOARD_CACHE_PREFIX}{day_key}"),
                timeout=1.0,
            )
            decoded = _decode_redis_str(raw)
            if decoded:
                parsed = json.loads(decoded)
                if isinstance(parsed, dict):
                    return parsed
        except Exception:
            pass
    cached = _PUBLIC_BOARD_MEM_CACHE.get(day_key)
    if cached is not None:
        exp_mono, snapshot = cached
        if time.monotonic() < exp_mono:
            return snapshot
        _PUBLIC_BOARD_MEM_CACHE.pop(day_key, None)
    return None


async def _store_cached_public_board(day_key: str, snapshot: dict) -> None:
    redis_cli = _get_async_rl_redis()
    if redis_cli is not None:
        try:
            await asyncio.wait_for(
                redis_cli.set(
                    f"{_PUBLIC_BOARD_CACHE_PREFIX}{day_key}",
                    json.dumps(snapshot, separators=(",", ":")),
                    ex=_PUBLIC_BOARD_CACHE_TTL_S,
                ),
                timeout=1.0,
            )
            return
        except Exception:
            pass
    if len(_PUBLIC_BOARD_MEM_CACHE) > 16:
        _PUBLIC_BOARD_MEM_CACHE.clear()
    _PUBLIC_BOARD_MEM_CACHE[day_key] = (
        time.monotonic() + _PUBLIC_BOARD_CACHE_TTL_S,
        snapshot,
    )


async def _invalidate_public_board_cache(day_key: str) -> None:
    _PUBLIC_BOARD_MEM_CACHE.pop(day_key, None)
    redis_cli = _get_async_rl_redis()
    if redis_cli is not None:
        try:
            await asyncio.wait_for(
                redis_cli.delete(f"{_PUBLIC_BOARD_CACHE_PREFIX}{day_key}"),
                timeout=1.0,
            )
        except Exception:
            pass


def _decode_redis_str(raw: object) -> Optional[str]:
    if isinstance(raw, (bytes, bytearray)):
        text = raw.decode("utf-8", errors="replace").strip()
        return text or None
    if isinstance(raw, str):
        text = raw.strip()
        return text or None
    return None


async def _get_daily_rate_limit_salt(now_s: int) -> str:
    """Return one random rate-limit salt shared across dynos and rotated daily."""
    global _CACHED_SALT
    day_key = today_pt(datetime.fromtimestamp(now_s, tz=timezone.utc)).isoformat()
    cached_day, cached_salt, cached_from_redis = _CACHED_SALT
    if cached_from_redis and cached_day == day_key and cached_salt:
        return cached_salt

    salt_key = f"guess_rl:salt:{day_key}"
    redis_cli = _get_async_rl_redis()
    if redis_cli is not None:
        try:
            existing = _decode_redis_str(
                await asyncio.wait_for(redis_cli.get(salt_key), timeout=1.0)
            )
            if existing:
                _CACHED_SALT = (day_key, existing, True)
                return existing
            candidate = secrets.token_hex(16)
            created = await asyncio.wait_for(
                redis_cli.set(salt_key, candidate, nx=True, ex=_SALT_TTL_S),
                timeout=1.0,
            )
            if created:
                _CACHED_SALT = (day_key, candidate, True)
                return candidate
            winner = _decode_redis_str(
                await asyncio.wait_for(redis_cli.get(salt_key), timeout=1.0)
            )
            if winner:
                _CACHED_SALT = (day_key, winner, True)
                return winner
        except Exception:
            pass

    if day_key not in _FALLBACK_SALTS:
        _FALLBACK_SALTS.clear()
        _FALLBACK_SALTS[day_key] = secrets.token_hex(16)
    salt = _FALLBACK_SALTS[day_key]
    _CACHED_SALT = (day_key, salt, False)
    return salt


def _ephemeral_client_bucket(request: Request, salt: str) -> str:
    """Hash only the router-appended peer address so callers cannot forge hops."""
    raw = _router_peer_ip(request)
    return hashlib.sha256(f"{salt}:{raw}".encode("utf-8")).hexdigest()[:24]


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
    salt = await _get_daily_rate_limit_salt(now_s)
    client_count = await _hit_window(
        f"c:{_ephemeral_client_bucket(request, salt)}", _CLIENT_WINDOW_S, now_s
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


async def _log_daily_ceiling_once(day_pt_val: date) -> None:
    day_str = day_pt_val.isoformat()
    redis_cli = _get_async_rl_redis()
    if redis_cli is not None:
        try:
            first_today = await asyncio.wait_for(
                redis_cli.set(
                    f"guess_rl:daily_cap_logged:{day_str}",
                    "1",
                    nx=True,
                    ex=_SALT_TTL_S,
                ),
                timeout=1.0,
            )
            if not first_today:
                return
            _DAILY_CEILING_LOGGED_DAYS.add(day_pt_val)
            logger.error(
                "Guess daily entry ceiling reached for %s PT (%d entries); refusing new games until tomorrow.",
                day_str,
                MAX_DAILY_ENTRIES,
            )
            return
        except Exception:
            pass

    if day_pt_val in _DAILY_CEILING_LOGGED_DAYS:
        return
    if len(_DAILY_CEILING_LOGGED_DAYS) > 64:
        _DAILY_CEILING_LOGGED_DAYS.clear()
    _DAILY_CEILING_LOGGED_DAYS.add(day_pt_val)
    logger.error(
        "Guess daily entry ceiling reached for %s PT (%d entries); refusing new games until tomorrow.",
        day_str,
        MAX_DAILY_ENTRIES,
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
    except GuessEditionUnscheduledError:
        return JSONResponse(
            status_code=503,
            content={
                "detail": "No new cards today. Here is the latest set.",
                "reason": "unscheduled",
            },
        )
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


@router.get("/board")
async def get_public_guess_board(
    response: Response,
    day: Optional[date] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    entry_id: Optional[int] = Query(default=None),
    db: AsyncSession = Depends(get_db_rw),
):
    """Return one PT day's paged public board across visible games (1-min cached)."""
    today = today_pt()
    target_day = day or today
    oldest_kept = today - timedelta(days=RETENTION_DAYS)
    if target_day > today or target_day < oldest_kept:
        raise HTTPException(
            status_code=404,
            detail=f"Edition day {target_day} is outside the active window.",
        )

    day_key = target_day.isoformat()
    snapshot = await _get_cached_public_board(day_key)
    if snapshot is None:
        try:
            edition = await get_or_freeze_daily_edition(db, target_day)
        except GuessEditionUnscheduledError:
            return JSONResponse(
                status_code=503,
                content={
                    "detail": "No new cards today. Here is the latest set.",
                    "reason": "unscheduled",
                },
            )
        except GuessEditionNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except GuessEditionUnavailableError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        snapshot = await build_public_board_snapshot(db, edition)
        await _store_cached_public_board(day_key, snapshot)

    response.headers["Cache-Control"] = (
        "private, no-store"
        if entry_id is not None
        else f"public, max-age={_PUBLIC_BOARD_CACHE_TTL_S}"
    )
    return slice_public_board_page(
        snapshot,
        page=page,
        page_size=page_size,
        entry_id=entry_id,
    )


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

    nickname, refusal_msg = validate_nickname(payload.nickname)
    if refusal_msg or not nickname:
        return JSONResponse(
            status_code=422,
            content={
                "detail": refusal_msg or "Please pick another nickname.",
                "reason": "nickname_refused",
            },
        )

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
        db, GROUP_LOCK_NS, group_lock_key(edition.day_pt, clean_code)
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
            existing.hidden_at is None
            and list(existing.answers) == scored["answers"]
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

    daily_count = await db.scalar(
        select(func.count(GuessGroupEntry.id)).where(
            GuessGroupEntry.day_pt == edition.day_pt,
        )
    )
    if int(daily_count or 0) >= MAX_DAILY_ENTRIES:
        await _log_daily_ceiling_once(edition.day_pt)
        raise HTTPException(
            status_code=429,
            detail="Today's shared boards are full right now. Please try again tomorrow.",
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
    await _invalidate_public_board_cache(edition.day_pt.isoformat())
    return await build_group_board_payload(db, edition, clean_code)


@router.post(
    "/admin/entries/{entry_id}/hide",
    dependencies=[Depends(admin_account_identity)],
)
async def hide_guess_entry(
    entry_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db_rw),
):
    """Hide one stored entry by setting `hidden_at` (never deleting rows)."""
    _check_admin_secret(None, request=request)
    entry = await db.scalar(
        select(GuessGroupEntry).where(GuessGroupEntry.id == entry_id)
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="Entry not found.")
    if entry.hidden_at is None:
        entry.hidden_at = datetime.now(timezone.utc)
        await db.commit()
    await _invalidate_public_board_cache(entry.day_pt.isoformat())
    return {
        "status": "hidden",
        "entry_id": int(entry.id),
        "day": entry.day_pt.isoformat(),
        "hidden_at": entry.hidden_at.isoformat(),
    }
