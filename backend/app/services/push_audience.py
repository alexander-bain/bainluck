"""212-A / 177-A / 178-B: which phones hear about a game or a market, with no account.

SHIP: a reader who pinned a game without signing in gets its kickoff, big-swing
and final alerts; at kickoff a phone that can start a Live Activity by push gets
that instead of a plain notification, never both.

This module answers "who" and "how to address them"; it never sends anything.
The sender (Speed's half of 212-A) owns APNs, the provider token, the "at most
twice" swing cap and the one-kickoff-per-game record (Redis, with an expiry).

Rules it carries, from the agreed payload note on #11934 (Builder F, Nov 15):
- A pin reaches a phone either from the phone's own row
  (``pinned_event_ids @> ARRAY[id]``, GIN-indexed) or, once the phone is signed
  in, from its reader's account pins (``user_pins``): "pins follow the reader".
- The App Clip is a separate app to Apple: its alerts go to the clip's topic,
  it never gets a Live Activity, and its permission lasts 8 hours, so a clip
  row older than that is never addressed (and :func:`purge_expired_appclip_devices`
  deletes it).
- ``apns_env`` picks Apple's production or sandbox server per row.
- Tokens are transport credentials: they are kept out of ``repr`` and never
  logged here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal, Optional
from uuid import UUID

from sqlalchemy import and_, delete, exists, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import UserPin
from app.models.push_device import PushDevice

_DEVICES = PushDevice.__table__
_PINS = UserPin.__table__

APP_TOPIC = "com.bainluck.Bain-Luck"
CLIP_TOPIC = APP_TOPIC + ".Clip"
LIVE_ACTIVITY_TOPIC = APP_TOPIC + ".push-type.liveactivity"
#: Apple's ephemeral App Clip notification permission lasts 8 hours.
APPCLIP_LIFETIME = timedelta(hours=8)
#: ``input-push-token: 1`` on a start push is understood from iOS 18.
INPUT_PUSH_TOKEN_OS = 18
MAX_PAGE = 500

PinKind = Literal["event", "market"]
#: ``user_pins.pin_type`` for each kind (`routes/user.py` calls a market pin "future").
_ACCOUNT_PIN_TYPE = {"event": "event", "market": "future"}


@dataclass(frozen=True)
class AlertTarget:
    """One plain notification: ``apns-push-type: alert`` to ``topic``."""

    device_id: UUID
    platform: str
    apns_env: str
    topic: str
    token: str = field(repr=False)


@dataclass(frozen=True)
class StartTarget:
    """One Live Activity start push to the phone's push-to-start token."""

    device_id: UUID
    apns_env: str
    input_push_token: bool
    app_version: Optional[str]
    token: str = field(repr=False)
    topic: str = LIVE_ACTIVITY_TOPIC


@dataclass(frozen=True)
class KickoffPlan:
    """178-B: one push per phone at kickoff — a start push where the phone can
    take one, else the plain "It's starting" alert."""

    start: list[StartTarget]
    alert: list[AlertTarget]
    next_after: Optional[UUID] = None


def alert_topic(platform: str) -> str:
    return CLIP_TOPIC if platform == "appclip" else APP_TOPIC


def _version(value: Optional[str]) -> Optional[tuple[int, ...]]:
    if not value:
        return None
    parts = []
    for piece in value.split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        if not digits or digits != piece:
            return None
        parts.append(int(digits))
    return tuple(parts) if parts else None


def can_take_start_push(app_version: Optional[str], min_app_version: Optional[str]) -> bool:
    """A start push goes only to a build that can decode it. With no minimum set,
    any build with a start token qualifies; an unreadable version never does
    when a minimum is set."""
    if min_app_version is None:
        return True
    have, need = _version(app_version), _version(min_app_version)
    if have is None or need is None:
        return False
    width = max(len(have), len(need))
    return have + (0,) * (width - len(have)) >= need + (0,) * (width - len(need))


def _validate(kind: str, target_id: int, limit: int, now: datetime) -> None:
    if kind not in _ACCOUNT_PIN_TYPE:
        raise ValueError("kind must be 'event' or 'market'")
    if isinstance(target_id, bool) or not isinstance(target_id, int) or not 0 < target_id < 2**31:
        raise ValueError("A positive integer id is required")
    if not isinstance(limit, int) or not 1 <= limit <= MAX_PAGE:
        raise ValueError(f"limit must be between 1 and {MAX_PAGE}")
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError("An aware clock is required")


def _pinned(kind: PinKind, target_id: int):
    column = _DEVICES.c.pinned_event_ids if kind == "event" else _DEVICES.c.pinned_market_ids
    account = exists().where(
        _PINS.c.user_id == _DEVICES.c.user_id,
        _PINS.c.pin_type == _ACCOUNT_PIN_TYPE[kind],
        _PINS.c.target_id == target_id,
    )
    return or_(column.contains([target_id]), and_(_DEVICES.c.user_id.is_not(None), account))


def _addressable(now: datetime):
    return or_(
        _DEVICES.c.platform != "appclip",
        _DEVICES.c.created_at > now - APPCLIP_LIFETIME,
    )


async def _rows(db, kind, target_id, *, now, after, limit, needs):
    query = (
        select(
            _DEVICES.c.device_id,
            _DEVICES.c.platform,
            _DEVICES.c.apns_env,
            _DEVICES.c.notification_token,
            _DEVICES.c.la_start_token,
            _DEVICES.c.os_major,
            _DEVICES.c.app_version,
        )
        .where(_pinned(kind, target_id), _addressable(now), needs)
        .order_by(_DEVICES.c.device_id)
        .limit(limit)
    )
    if after is not None:
        query = query.where(_DEVICES.c.device_id > after)
    return (await db.execute(query)).mappings().all()


def _alert(row) -> AlertTarget:
    return AlertTarget(
        device_id=row["device_id"],
        platform=row["platform"],
        apns_env=row["apns_env"],
        topic=alert_topic(row["platform"]),
        token=row["notification_token"],
    )


async def alert_targets(
    db: AsyncSession,
    kind: PinKind,
    target_id: int,
    *,
    now: datetime,
    after: Optional[UUID] = None,
    limit: int = MAX_PAGE,
) -> list[AlertTarget]:
    """Every phone that pinned this game (or market) and has a notification
    token, one page at a time in ``device_id`` order (pass the last id back as
    ``after``). Used for swing and final alerts, and market alerts."""
    _validate(kind, target_id, limit, now)
    rows = await _rows(
        db, kind, target_id, now=now, after=after, limit=limit,
        needs=_DEVICES.c.notification_token.is_not(None),
    )
    return [_alert(r) for r in rows]


async def kickoff_plan(
    db: AsyncSession,
    event_id: int,
    *,
    now: datetime,
    min_app_version: Optional[str] = None,
    after: Optional[UUID] = None,
    limit: int = MAX_PAGE,
) -> KickoffPlan:
    """178-B at kickoff: each phone that pinned the game gets exactly one push.

    A phone (never the App Clip) holding a push-to-start token on a build that
    can decode the start push gets the start push; every other phone with a
    notification token gets the plain alert. ``next_after`` is set when the page
    was full, so the caller pages on.
    """
    _validate("event", event_id, limit, now)
    rows = await _rows(
        db, "event", event_id, now=now, after=after, limit=limit,
        needs=or_(
            _DEVICES.c.notification_token.is_not(None),
            _DEVICES.c.la_start_token.is_not(None),
        ),
    )
    start, alert = [], []
    for row in rows:
        if (
            row["la_start_token"] is not None
            and row["platform"] != "appclip"
            and can_take_start_push(row["app_version"], min_app_version)
        ):
            start.append(
                StartTarget(
                    device_id=row["device_id"],
                    apns_env=row["apns_env"],
                    input_push_token=(row["os_major"] or 0) >= INPUT_PUSH_TOKEN_OS,
                    app_version=row["app_version"],
                    token=row["la_start_token"],
                )
            )
        elif row["notification_token"] is not None:
            alert.append(_alert(row))
    return KickoffPlan(
        start=start,
        alert=alert,
        next_after=rows[-1]["device_id"] if len(rows) == limit else None,
    )


async def forget_token(
    db: AsyncSession, column: Literal["notification_token", "la_start_token"], token: str
) -> int:
    """Apple answered 410 for this token: the phone no longer has it. Clear it
    (and its start stamp) without touching the row's pins. Returns rows changed;
    the caller commits."""
    if column not in ("notification_token", "la_start_token"):
        raise ValueError("Unknown token column")
    values = {column: None}
    if column == "la_start_token":
        values["la_start_token_at"] = None
    result = await db.execute(
        update(_DEVICES).where(_DEVICES.c[column] == token).values(**values)
    )
    return result.rowcount or 0


async def purge_expired_appclip_devices(db: AsyncSession, *, now: datetime) -> int:
    """Delete App Clip rows past Apple's 8-hour permission. They are never
    addressed after that anyway (see :func:`_addressable`); this keeps the table
    from holding dead clip tokens. Returns rows deleted; the caller commits."""
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError("An aware clock is required")
    result = await db.execute(
        delete(_DEVICES).where(
            _DEVICES.c.platform == "appclip",
            _DEVICES.c.created_at <= now - APPCLIP_LIFETIME,
        )
    )
    return result.rowcount or 0
