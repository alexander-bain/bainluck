"""1.0.8 plain APNs game-alerts dispatcher (#13081, #13079, Rulings 258-261: A, 271: A).

Triggers for pinned games (default-off behind ``GAME_ALERTS_PUSH_ENABLED=true``):

1. **Starts (258: A):** plain ``"Starting now"`` alert ONLY to opted-in devices
   that cannot start a Live Activity (``kickoff_plan(...).alert`` — no
   ``la_start_token``, older app, or App Clip), and never to a phone that
   already holds an active Live Activity for that game.
2. **Close late (259: A, 260: A, 271: A):** final period (or OT/extra time)
   with blended win probability between 35% and 65% inclusive; for **soccer
   (271: A)**, from the 75th minute on (clock required on the feed) when no
   result (home, away, or draw) is above 65%, naming ``draw`` when the draw is
   the likeliest result. At most once per game per phone. Suppressed on any
   phone already showing that game's Live Activity (260: A), and skipped for
   ephemeral App Clip rows (which opt in for final-score only).
3. **Final (260: A, #13079):** completed/closed game — sent to every opted-in
   phone, including phones showing that game's Live Activity and valid (< 8 h)
   App Clip rows.

Every alert uses standard interruption level (never Time Sensitive, 261: A),
carries ``event_id`` in userInfo for tap routing, enforces once-per-device-per-
game-per-trigger dedup in Redis, and clears unregistered tokens on APNs 410 via
``push_audience.forget_token``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math
import re
from typing import Awaitable, Callable, Protocol
from uuid import UUID

from sqlalchemy import exists, or_, select
from sqlalchemy.dialects.postgresql import array as pg_array
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.activitykit import ActivityKitRegistration
from app.models.models import Event, UserPin
from app.models.push_device import PushDevice
from app.services.activitykit_apns import APNsResult
from app.services.apns_alert import (
    APNsAlertTransport,
    AlertTriggerKind,
    GameAlertPush,
)
from app.services.push_audience import (
    APPCLIP_LIFETIME,
    AlertTarget,
    alert_targets,
    forget_token,
    kickoff_plan,
)
from app.utils.activitykit_payload import OBSERVATION_MAX_AGE
from app.utils.activitykit_projection import project_activitykit_snapshot
from app.utils.activitykit_start_payload import build_activitykit_start_alert
from app.utils.draw_priced_winner import sport_prices_a_draw
from app.utils.graded_card import rendered_percent

_DEVICES = PushDevice.__table__
_PINS = UserPin.__table__
_REG = ActivityKitRegistration.__table__

#: Bounded live close-late lookback and lead windows.
LIVE_ALERT_LOOKBACK = timedelta(hours=6)
LIVE_ALERT_LEAD = timedelta(minutes=15)
#: "Starting now" only fires within 15 minutes of commence_time (and only in
#: the first period when a period label is present; <= 15' when soccer has a clock).
START_JUST_LIVE_WINDOW = timedelta(minutes=15)
#: Max live soccer clock minute that still qualifies as "just started".
SOCCER_JUST_STARTED_MAX_MINUTE = 15
#: Bounded final-alert lookback so historic finished rows never fire phantom buzzes.
FINAL_ALERT_LOOKBACK = timedelta(hours=12)
#: Once-per-(device, event, trigger) dedup TTL in Redis.
ALERT_DEDUP_TTL_SECONDS = 48 * 3600
#: Expiration horizon for APNs delivery attempts.
ALERT_EXPIRATION_SECONDS = 30 * 60
#: Maximum candidate events scanned per trigger class per 30 s beat.
MAX_EVENTS_PER_BEAT = 50
#: Close-late probability window (Ruling 259: A, inclusive).
CLOSE_LATE_MIN_PERCENT = 35
CLOSE_LATE_MAX_PERCENT = 65
#: Soccer close-late minute threshold (Ruling 271: A, inclusive; clock required).
SOCCER_CLOSE_LATE_MIN_MINUTE = 75

_SOCCER_STOPPAGE_CLOCK_RE = re.compile(
    r"^\s*(\d{1,3})\s*'?\s*\+\s*(\d{1,2})\s*'?\s*$"
)
_SOCCER_MMSS_CLOCK_RE = re.compile(r"^\s*(\d{1,3})\s*:\s*(\d{2})\s*$")
_SOCCER_MINUTE_CLOCK_RE = re.compile(
    r"^\s*(\d{1,3})\s*(?:'|th|st|nd|rd|min)?\s*$", re.IGNORECASE
)

# Period parsing for Starts ("first period") and Ruling 259: A ("final period").
_FIRST_PERIOD_RE = re.compile(
    r"\b(?:1st(?:\s+(?:quarter|qtr|period|half|inning|set|round))?|q1|p1|1h|r1"
    r"|(?:top|mid(?:dle)?|bot(?:tom)?)\s+1(?:st)?|set\s+1|round\s+1)\b",
    re.IGNORECASE,
)
_TERMINAL_PERIOD_RE = re.compile(
    r"\bfinal\b(?!\s+set\b)|\bft\b|\bfull[- ]?time\b|\bended\b|\bpostponed\b"
    r"|\bcancell?ed\b|\babandoned\b|\bhalftime\b|\bhalf[- ]?time\b",
    re.IGNORECASE,
)
_END_OF_PERIOD_RE = re.compile(r"\bend\s+of\b", re.IGNORECASE)
_OVERTIME_RE = re.compile(
    r"\b(?:\d*\s*ot|overtime|extra\s*time|et|so|shootout|penalties|pens)\b",
    re.IGNORECASE,
)
_QUARTER_4_RE = re.compile(r"\b(?:4th(?:\s+quarter|\s+qtr)?|q4)\b", re.IGNORECASE)
_PERIOD_3_RE = re.compile(r"\b(?:3rd(?:\s+period)?|p3)\b", re.IGNORECASE)
_HALF_2_RE = re.compile(r"\b(?:2nd\s+half|2h)\b", re.IGNORECASE)
_INNING_RE = re.compile(
    r"\b(?:top|bot(?:tom)?|mid(?:dle)?|end)?\s*(\d{1,2})(?:st|nd|rd|th)?\b",
    re.IGNORECASE,
)
_TENNIS_FINAL_SET_RE = re.compile(
    r"\b(?:final\s+set|(?:3rd|5th)\s+set|set\s+[35])\b", re.IGNORECASE
)

_NEUTRAL_VS_SPORTS = (
    "soccer_",
    "tennis_",
    "mma_",
    "boxing_",
    "golf_",
    "cricket_",
    "rugby_",
)


def is_final_period(sport_key: str | None, period: str | None) -> bool:
    """True when ``period`` places a live game in its final regulation period or OT.

    Conservative by design: terminal strings (``Final``, ``Final/OT``,
    ``Halftime``), intermission markers (``End of 3rd Quarter``), and unknown
    labels return ``False``.
    """
    if not isinstance(period, str):
        return False
    text = period.strip()
    if not text:
        return False
    if _TERMINAL_PERIOD_RE.search(text):
        return False
    if _END_OF_PERIOD_RE.search(text):
        return False
    if _OVERTIME_RE.search(text):
        return True

    sport = (sport_key or "").strip().lower()
    if sport.startswith("americanfootball_"):
        return bool(_QUARTER_4_RE.search(text))
    if sport == "basketball_ncaab":
        # Men's college basketball plays two halves; women's plays four quarters.
        return bool(_HALF_2_RE.search(text))
    if sport.startswith("basketball_"):
        return bool(_QUARTER_4_RE.search(text))
    if sport.startswith("icehockey_"):
        return bool(_PERIOD_3_RE.search(text))
    if sport.startswith("baseball_"):
        if re.search(r"\bend\s+8(?:th)?\b", text, re.IGNORECASE):
            return False
        m = _INNING_RE.search(text)
        return bool(m and int(m.group(1)) >= 9)
    if sport.startswith("soccer_"):
        return bool(_HALF_2_RE.search(text))
    if sport.startswith("tennis_"):
        return bool(_TENNIS_FINAL_SET_RE.search(text))
    return False


def _raw_period(detail: Mapping[str, object]) -> str | None:
    espn = detail.get("espn")
    if isinstance(espn, Mapping) and isinstance(espn.get("period"), str):
        return espn["period"].strip() or None
    raw = detail.get("period")
    if isinstance(raw, str):
        return raw.strip() or None
    return None


def _raw_game_clock(detail: Mapping[str, object]) -> str | None:
    espn = detail.get("espn")
    if isinstance(espn, Mapping):
        for key in ("game_clock", "clock"):
            val = espn.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    for key in ("game_clock", "clock"):
        val = detail.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


def _is_soccer_sport(sport_key: str | None) -> bool:
    return (sport_key or "").strip().lower().startswith("soccer_")


def parse_soccer_clock(
    raw_clock: str | None, *, period: str | None = None
) -> tuple[int, str] | None:
    """Parse a live soccer game clock into ``(minute, display_label)`` (Ruling 271: A).

    Returns ``None`` when no clock is present on the feed, when the period is
    terminal/halftime/1st half, or when the clock string cannot be parsed as a
    valid match minute (conservative: no clock -> no buzz).
    """
    if isinstance(period, str) and period.strip():
        p = period.strip()
        if (
            _TERMINAL_PERIOD_RE.search(p)
            or _END_OF_PERIOD_RE.search(p)
            or is_first_period(p)
        ):
            return None
    if not isinstance(raw_clock, str):
        return None
    text = raw_clock.strip()
    if not text or _TERMINAL_PERIOD_RE.search(text):
        return None

    m = _SOCCER_STOPPAGE_CLOCK_RE.match(text)
    if m:
        base_min = int(m.group(1))
        added = int(m.group(2))
        if 0 <= base_min <= 150:
            return (base_min, f"{base_min}+{added}'")
        return None

    m = _SOCCER_MMSS_CLOCK_RE.match(text)
    if m:
        minute = int(m.group(1))
        if 0 <= minute <= 150:
            return (minute, f"{minute}'")
        return None

    m = _SOCCER_MINUTE_CLOCK_RE.match(text)
    if m:
        minute = int(m.group(1))
        if 0 <= minute <= 150:
            return (minute, f"{minute}'")
        return None

    return None


def _valid_probability(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    v = float(value)
    return v if math.isfinite(v) and 0.0 <= v <= 1.0 else None


def _three_way_rendered_percents(
    detail: Mapping[str, object],
) -> tuple[int, int, int] | None:
    """Return ``(home_pct, away_pct, draw_pct)`` for a 3-way match, or ``None``.

    Refuses opening-tagged readings and returns ``None`` if any of the three
    outcomes is missing, so draw-priced matches never misread a 2-way pair.
    """
    if detail.get("hero_probability_source") == "opening":
        return None
    odds = detail.get("current_odds")
    odds_map = odds if isinstance(odds, Mapping) else {}
    cur_home = _valid_probability(odds_map.get("home_probability"))
    if cur_home is not None:
        home_p = cur_home
        away_p = _valid_probability(odds_map.get("away_probability"))
        draw_p = _valid_probability(odds_map.get("draw_probability"))
    else:
        home_p = _valid_probability(detail.get("hero_probability"))
        away_p = _valid_probability(detail.get("hero_probability_away"))
        draw_p = _valid_probability(detail.get("hero_probability_draw"))

    if home_p is None or away_p is None or draw_p is None:
        return None
    home_pct = rendered_percent(home_p)
    away_pct = rendered_percent(away_p)
    draw_pct = rendered_percent(draw_p)
    if home_pct is None or away_pct is None or draw_pct is None:
        return None
    return (home_pct, away_pct, draw_pct)


def _parse_commence_time(value: object) -> datetime | None:
    if isinstance(value, datetime):
        if value.utcoffset() is None:
            return None
        return value.astimezone(timezone.utc)
    if isinstance(value, str) and value.strip():
        try:
            dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        if dt.utcoffset() is None:
            return None
        return dt.astimezone(timezone.utc)
    return None


def _probability_is_fresh(
    snapshot, *, now: datetime, max_age: timedelta = OBSERVATION_MAX_AGE
) -> bool:
    prob_at = snapshot.probability_observed_at
    if prob_at is None or prob_at.utcoffset() is None:
        return False
    age = now.astimezone(timezone.utc) - prob_at.astimezone(timezone.utc)
    return timedelta(0) <= age <= max_age


def is_first_period(period: str | None) -> bool:
    """True when ``period`` places a live game in its opening period."""
    if not isinstance(period, str):
        return False
    text = period.strip()
    if not text:
        return False
    if _TERMINAL_PERIOD_RE.search(text) or _END_OF_PERIOD_RE.search(text):
        return False
    if _OVERTIME_RE.search(text):
        return False
    return bool(_FIRST_PERIOD_RE.search(text))


def _parse_soccer_minute_any_period(raw_clock: str | None) -> int | None:
    """Extract the match minute from a live soccer clock regardless of period."""
    if not isinstance(raw_clock, str):
        return None
    text = raw_clock.strip()
    if not text or _TERMINAL_PERIOD_RE.search(text):
        return None
    for pattern in (
        _SOCCER_STOPPAGE_CLOCK_RE,
        _SOCCER_MMSS_CLOCK_RE,
        _SOCCER_MINUTE_CLOCK_RE,
    ):
        m = pattern.match(text)
        if m:
            minute = int(m.group(1))
            return minute if 0 <= minute <= 150 else None
    return None


def is_just_started(detail: Mapping[str, object], *, now: datetime) -> bool:
    """True only when a live game has just begun (Fable look #13088 item 1).

    Prevents a phone that pins a game mid-period (e.g., 40' in soccer or late
    in a tennis first set) — or every pinned live game on the day the switch
    turns on — from receiving a late ``"Starting now"`` alert:
    - ``commence_time`` must ALWAYS be within ``START_JUST_LIVE_WINDOW``
      (15 minutes) of ``now``.
    - If a period label is present, it must also be the first period (Q1 / 1st
      Period / 1st Half / Top/Mid/Bot 1st / 1st Set / Round 1).
    - For soccer, if a live clock is present on the feed, its match minute must
      also be ``<= 15``.
    """
    snapshot = project_activitykit_snapshot(detail)
    if snapshot.lifecycle != "live":
        return False
    ct = _parse_commence_time(detail.get("commence_time"))
    if ct is None:
        return False
    elapsed = now.astimezone(timezone.utc) - ct
    if not (-START_JUST_LIVE_WINDOW <= elapsed <= START_JUST_LIVE_WINDOW):
        return False
    period = _raw_period(detail)
    if period is not None and not is_first_period(period):
        return False
    if _is_soccer_sport(snapshot.sport):
        soccer_min = _parse_soccer_minute_any_period(_raw_game_clock(detail))
        if soccer_min is not None and soccer_min > SOCCER_JUST_STARTED_MAX_MINUTE:
            return False
    return True


def is_close_late(
    detail: Mapping[str, object],
    *,
    now: datetime | None = None,
    freshness_window: timedelta = OBSERVATION_MAX_AGE,
) -> bool:
    """Rulings 259: A & 271: A — close-late trigger with fresh observation.

    - **Soccer (271: A):** from the 75th minute on (clock required on the feed;
      no clock -> no buzz), when no result (home, away, or draw) is above 65%.
    - **All other sports (259: A):** final period (or OT) with blended win
      probability between 35% and 65% inclusive.
    """
    snapshot = project_activitykit_snapshot(detail)
    if snapshot.lifecycle != "live":
        return False
    clock = now if now is not None else datetime.now(timezone.utc)
    if not _probability_is_fresh(snapshot, now=clock, max_age=freshness_window):
        return False

    if _is_soccer_sport(snapshot.sport):
        parsed = parse_soccer_clock(
            _raw_game_clock(detail), period=_raw_period(detail)
        )
        if parsed is None or parsed[0] < SOCCER_CLOSE_LATE_MIN_MINUTE:
            return False
        three_way = _three_way_rendered_percents(detail)
        if three_way is None:
            return False
        return max(three_way) <= CLOSE_LATE_MAX_PERCENT

    if snapshot.home_rendered_percent is None:
        return False
    if not (CLOSE_LATE_MIN_PERCENT <= snapshot.home_rendered_percent <= CLOSE_LATE_MAX_PERCENT):
        return False
    return is_final_period(snapshot.sport, _raw_period(detail))


def _matchup_title(away: str, home: str, sport: str | None) -> str:
    s = (sport or "").strip().lower()
    sep = " vs " if any(s.startswith(p) for p in _NEUTRAL_VS_SPORTS) else " at "
    return f"{away}{sep}{home}"


def _leader_summary(snapshot, detail: Mapping[str, object] | None = None) -> str | None:
    if snapshot.sport and sport_prices_a_draw(snapshot.sport):
        three_way = _three_way_rendered_percents(detail) if detail is not None else None
        if three_way is None:
            return None
        home_pct, away_pct, draw_pct = three_way
        if draw_pct >= home_pct and draw_pct >= away_pct:
            return f"draw {draw_pct}%"
        if home_pct >= away_pct:
            return f"{snapshot.home_team} {home_pct}%"
        return f"{snapshot.away_team} {away_pct}%"

    home_pct = snapshot.home_rendered_percent
    if home_pct is None:
        return None
    away_pct = (
        snapshot.away_rendered_percent
        if snapshot.away_rendered_percent is not None
        else max(0, 100 - home_pct)
    )
    if home_pct >= away_pct:
        return f"{snapshot.home_team} {home_pct}%"
    return f"{snapshot.away_team} {away_pct}%"


def build_game_alert_payload(
    detail: Mapping[str, object],
    *,
    trigger_kind: AlertTriggerKind,
    device_id: UUID,
    now: datetime,
) -> GameAlertPush | None:
    """Build one plain-English APNs alert push from a canonical event detail."""
    snapshot = project_activitykit_snapshot(detail)
    if not isinstance(snapshot.event_id, int):
        return None
    away = (snapshot.away_team or "").strip()
    home = (snapshot.home_team or "").strip()
    if not away or not home:
        return None

    exp = int(now.timestamp()) + ALERT_EXPIRATION_SECONDS
    cmd_id = f"{trigger_kind}:{snapshot.event_id}:{device_id}"

    if trigger_kind == "start":
        if not is_just_started(detail, now=now):
            return None
        # Share the exact kickoff alert builder with `activitykit_start_payload`
        # so the title, wording ("Starting now · Team 52%"), and 6-minute
        # `OBSERVATION_MAX_AGE` freshness gate stay identical across both paths.
        start_alert = build_activitykit_start_alert(snapshot, sent_at=now)
        return GameAlertPush(
            event_id=snapshot.event_id,
            trigger_kind="start",
            title=start_alert["title"],
            body=start_alert["body"],
            command_id=cmd_id,
            expiration_epoch=exp,
        )

    if trigger_kind == "close_late":
        if not is_close_late(detail, now=now):
            return None
        if snapshot.away_score is not None and snapshot.home_score is not None:
            title = f"{away} {snapshot.away_score}–{snapshot.home_score} {home}"
        else:
            title = _matchup_title(away, home, snapshot.sport)
        leader = _leader_summary(snapshot, detail)
        if _is_soccer_sport(snapshot.sport):
            parsed_clock = parse_soccer_clock(
                _raw_game_clock(detail), period=_raw_period(detail)
            )
            clock_label = parsed_clock[1] if parsed_clock is not None else None
            if clock_label and leader:
                body = f"Close late ({clock_label}) · {leader}"
            elif clock_label:
                body = f"Close late ({clock_label})"
            else:
                body = "Close late"
        else:
            period = snapshot.period_label or _raw_period(detail)
            if period and leader:
                body = f"Close late ({period}) · {leader}"
            elif leader:
                body = f"Close late · {leader}"
            else:
                body = "Close late"
        return GameAlertPush(
            event_id=snapshot.event_id,
            trigger_kind="close_late",
            title=title,
            body=body,
            command_id=cmd_id,
            expiration_epoch=exp,
        )

    if trigger_kind == "final":
        if snapshot.lifecycle not in {"final", "closed"}:
            return None
        has_scores = (
            snapshot.away_score is not None and snapshot.home_score is not None
        )
        if has_scores:
            if snapshot.result == "home" or (
                snapshot.result is None and snapshot.home_score > snapshot.away_score
            ):
                title = (
                    f"Final: {home} {snapshot.home_score}–{snapshot.away_score} {away}"
                )
                body = f"{home} won"
            elif snapshot.result == "away" or (
                snapshot.result is None and snapshot.away_score > snapshot.home_score
            ):
                title = (
                    f"Final: {away} {snapshot.away_score}–{snapshot.home_score} {home}"
                )
                body = f"{away} won"
            else:
                title = (
                    f"Final: {away} {snapshot.away_score}–{snapshot.home_score} {home}"
                )
                body = "Draw" if snapshot.result == "draw" else "Final score"
        else:
            title = f"Final: {_matchup_title(away, home, snapshot.sport)}"
            if snapshot.result == "home":
                body = f"{home} won"
            elif snapshot.result == "away":
                body = f"{away} won"
            elif snapshot.result == "draw":
                body = "Draw"
            else:
                body = "Final"
        return GameAlertPush(
            event_id=snapshot.event_id,
            trigger_kind="final",
            title=title,
            body=body,
            command_id=cmd_id,
            expiration_epoch=exp,
        )

    return None


class GameAlertDedupStore(Protocol):
    """Atomic once-per-(trigger, event, device) claim; releases only on retry."""

    async def claim(
        self,
        trigger_kind: AlertTriggerKind,
        event_id: int,
        device_id: UUID,
        ttl_seconds: int,
    ) -> bool: ...

    async def release(
        self,
        trigger_kind: AlertTriggerKind,
        event_id: int,
        device_id: UUID,
    ) -> None: ...


class RedisGameAlertDedupStore:
    """Bounded Redis NX+EX dedup backed by the shared process pool."""

    def __init__(self, client_factory=None) -> None:
        self._client_factory = client_factory

    def _client(self):
        if self._client_factory is not None:
            return self._client_factory()
        from app.tasks.redis_state import get_redis_client

        return get_redis_client()

    @staticmethod
    def key(
        trigger_kind: AlertTriggerKind, event_id: int, device_id: UUID
    ) -> str:
        return f"game_alert:{trigger_kind}:{event_id}:{device_id}"

    async def claim(
        self,
        trigger_kind: AlertTriggerKind,
        event_id: int,
        device_id: UUID,
        ttl_seconds: int,
    ) -> bool:
        k = self.key(trigger_kind, event_id, device_id)

        def _set():
            return bool(self._client().set(k, "1", nx=True, ex=ttl_seconds))

        return await asyncio.to_thread(_set)

    async def release(
        self,
        trigger_kind: AlertTriggerKind,
        event_id: int,
        device_id: UUID,
    ) -> None:
        k = self.key(trigger_kind, event_id, device_id)

        def _del():
            self._client().delete(k)

        await asyncio.to_thread(_del)


class AlertTransportFactory(Protocol):
    def for_env(self, apns_env: str) -> APNsAlertTransport: ...
    async def aclose(self) -> None: ...


@dataclass(frozen=True)
class GameAlertDispatchSummary:
    live_events_scanned: int = 0
    final_events_scanned: int = 0
    attempted: int = 0
    accepted: int = 0
    start_accepted: int = 0
    close_late_accepted: int = 0
    final_accepted: int = 0
    skipped_dedup: int = 0
    skipped_active_la: int = 0
    token_forgotten: int = 0
    retryable: int = 0
    rejected: int = 0

    def as_dict(self) -> dict[str, int | str]:
        return {
            "status": "ok",
            "terminal": "ok",
            "live_events_scanned": self.live_events_scanned,
            "final_events_scanned": self.final_events_scanned,
            "attempted": self.attempted,
            "accepted": self.accepted,
            "start_accepted": self.start_accepted,
            "close_late_accepted": self.close_late_accepted,
            "final_accepted": self.final_accepted,
            "skipped_dedup": self.skipped_dedup,
            "skipped_active_la": self.skipped_active_la,
            "token_forgotten": self.token_forgotten,
            "retryable": self.retryable,
            "rejected": self.rejected,
        }


async def _canonical_detail_reader(db: AsyncSession, event_id: int) -> dict:
    from app.routes.events import build_event_detail_uncoalesced

    return await build_event_detail_uncoalesced(db, event_id)


def _has_addressable_notification_pin(now: datetime):
    return exists(
        select(1).where(
            _DEVICES.c.notification_token.is_not(None),
            or_(
                _DEVICES.c.platform != "appclip",
                _DEVICES.c.created_at > now - APPCLIP_LIFETIME,
            ),
            or_(
                _DEVICES.c.pinned_event_ids.contains(pg_array([Event.id])),
                exists(
                    select(1).where(
                        _DEVICES.c.user_id.is_not(None),
                        _PINS.c.user_id == _DEVICES.c.user_id,
                        _PINS.c.pin_type == "event",
                        _PINS.c.target_id == Event.id,
                    )
                ),
            ),
        )
    )


def build_live_alert_event_ids_query(
    *, now: datetime, limit: int = MAX_EVENTS_PER_BEAT
):
    return (
        select(Event.id)
        .where(
            Event.status == "live",
            Event.commence_time.is_not(None),
            Event.commence_time >= now - LIVE_ALERT_LOOKBACK,
            Event.commence_time <= now + LIVE_ALERT_LEAD,
            _has_addressable_notification_pin(now),
        )
        .order_by(Event.commence_time.asc(), Event.id.asc())
        .limit(limit)
    )


def build_final_alert_event_ids_query(
    *, now: datetime, limit: int = MAX_EVENTS_PER_BEAT
):
    return (
        select(Event.id)
        .where(
            Event.status.in_(("completed", "closed")),
            Event.commence_time.is_not(None),
            Event.commence_time >= now - FINAL_ALERT_LOOKBACK,
            Event.commence_time <= now,
            _has_addressable_notification_pin(now),
        )
        .order_by(Event.commence_time.desc(), Event.id.asc())
        .limit(limit)
    )


async def find_live_alert_event_ids(
    db: AsyncSession, *, now: datetime, limit: int = MAX_EVENTS_PER_BEAT
) -> list[int]:
    query = build_live_alert_event_ids_query(now=now, limit=limit)
    return list((await db.execute(query)).scalars().all())


async def find_final_alert_event_ids(
    db: AsyncSession, *, now: datetime, limit: int = MAX_EVENTS_PER_BEAT
) -> list[int]:
    query = build_final_alert_event_ids_query(now=now, limit=limit)
    return list((await db.execute(query)).scalars().all())


async def _active_la_device_ids(
    db: AsyncSession, event_id: int, device_ids: list[UUID], *, now: datetime
) -> set[UUID]:
    """Devices currently showing an active Live Activity for ``event_id``."""
    if not device_ids:
        return set()
    rows = await db.execute(
        select(_REG.c.device_id).where(
            _REG.c.event_id == event_id,
            _REG.c.device_id.in_(device_ids),
            _REG.c.is_active.is_(True),
            _REG.c.expires_at > now,
        )
    )
    return {d for d in rows.scalars().all() if d is not None}


async def _all_kickoff_alert_targets(
    db: AsyncSession,
    event_id: int,
    *,
    now: datetime,
    min_app_version: str | None,
) -> list[AlertTarget]:
    targets: list[AlertTarget] = []
    cursor: UUID | None = None
    while True:
        plan = await kickoff_plan(
            db,
            event_id,
            now=now,
            min_app_version=min_app_version,
            after=cursor,
        )
        targets.extend(plan.alert)
        if plan.next_after is None:
            break
        cursor = plan.next_after
    return targets


async def _all_alert_targets(
    db: AsyncSession, event_id: int, *, now: datetime
) -> list[AlertTarget]:
    targets: list[AlertTarget] = []
    cursor: UUID | None = None
    while True:
        page = await alert_targets(db, "event", event_id, now=now, after=cursor)
        targets.extend(page)
        if len(page) < 500:
            break
        cursor = page[-1].device_id
    return targets


async def _deliver_for_targets(
    *,
    sessions: async_sessionmaker[AsyncSession],
    transports: AlertTransportFactory,
    provider_token: Callable[[], Awaitable[str]],
    dedup: GameAlertDedupStore,
    detail: Mapping[str, object],
    event_id: int,
    trigger_kind: AlertTriggerKind,
    targets: list[AlertTarget],
    clock: datetime,
    counters: dict[str, int],
) -> None:
    if not targets:
        return
    for target in targets:
        push = build_game_alert_payload(
            detail,
            trigger_kind=trigger_kind,
            device_id=target.device_id,
            now=clock,
        )
        if push is None:
            return
        claimed = await dedup.claim(
            trigger_kind, event_id, target.device_id, ALERT_DEDUP_TTL_SECONDS
        )
        if not claimed:
            counters["skipped_dedup"] += 1
            continue

        counters["attempted"] += 1
        jwt = await provider_token()
        transport = transports.for_env(target.apns_env)
        result: APNsResult = await transport.send(
            push,
            device_token=target.token,
            topic=target.topic,
            provider_token=jwt,
        )
        if result.outcome == "accepted":
            counters["accepted"] += 1
            counters[f"{trigger_kind}_accepted"] += 1
        elif result.outcome == "unavailable":
            async with sessions() as db:
                await forget_token(db, "notification_token", target.token)
                await db.commit()
            counters["token_forgotten"] += 1
        elif result.outcome == "retry":
            await dedup.release(trigger_kind, event_id, target.device_id)
            counters["retryable"] += 1
        else:
            counters["rejected"] += 1


async def dispatch_game_alerts(
    sessions: async_sessionmaker[AsyncSession],
    transports: AlertTransportFactory,
    provider_token: Callable[[], Awaitable[str]],
    dedup: GameAlertDedupStore,
    *,
    now: datetime | None = None,
    min_app_version: str | None = "1.0.8",
    detail_reader: Callable[[AsyncSession, int], Awaitable[dict]] | None = None,
    live_finder: Callable[[AsyncSession, datetime], Awaitable[list[int]]] | None = None,
    final_finder: Callable[[AsyncSession, datetime], Awaitable[list[int]]] | None = None,
) -> GameAlertDispatchSummary:
    """One bounded sweep across Starts (258), Close Late (259/260), and Final (260)."""
    clock = now if now is not None else datetime.now(timezone.utc)
    if clock.utcoffset() is None:
        raise ValueError("An aware clock is required")
    clock = clock.astimezone(timezone.utc)

    reader = detail_reader or _canonical_detail_reader
    find_live = live_finder or (lambda db, ts: find_live_alert_event_ids(db, now=ts))
    find_final = final_finder or (lambda db, ts: find_final_alert_event_ids(db, now=ts))

    async with sessions() as db:
        live_event_ids = await find_live(db, clock)
        final_event_ids = await find_final(db, clock)

    counters: dict[str, int] = {
        "attempted": 0,
        "accepted": 0,
        "start_accepted": 0,
        "close_late_accepted": 0,
        "final_accepted": 0,
        "skipped_dedup": 0,
        "skipped_active_la": 0,
        "token_forgotten": 0,
        "retryable": 0,
        "rejected": 0,
    }

    # --- 1 & 2. Live events: Starts (258: A) + Close Late (259: A, 260: A) ---
    for event_id in live_event_ids:
        async with sessions() as db:
            detail = await reader(db, event_id)
            start_active = is_just_started(detail, now=clock)
            start_candidates = (
                await _all_kickoff_alert_targets(
                    db, event_id, now=clock, min_app_version=min_app_version
                )
                if start_active
                else []
            )
            close_late_active = is_close_late(detail, now=clock)
            close_candidates = (
                await _all_alert_targets(db, event_id, now=clock)
                if close_late_active
                else []
            )
            all_ids = list(
                {t.device_id for t in start_candidates}
                | {t.device_id for t in close_candidates}
            )
            active_la_ids = await _active_la_device_ids(
                db, event_id, all_ids, now=clock
            )

        # Starts (258: A): only phones that cannot start a Live Activity and
        # are not already showing one; skip ephemeral App Clip (#13088: final-only).
        eligible_starts: list[AlertTarget] = []
        for target in start_candidates:
            if target.platform == "appclip":
                continue
            if target.device_id in active_la_ids:
                counters["skipped_active_la"] += 1
                continue
            eligible_starts.append(target)

        await _deliver_for_targets(
            sessions=sessions,
            transports=transports,
            provider_token=provider_token,
            dedup=dedup,
            detail=detail,
            event_id=event_id,
            trigger_kind="start",
            targets=eligible_starts,
            clock=clock,
            counters=counters,
        )

        # Close late (259: A, 260: A): suppress phones already showing that
        # game's Live Activity; skip ephemeral App Clip (final-only per #13079).
        if close_late_active:
            eligible_close: list[AlertTarget] = []
            for target in close_candidates:
                if target.platform == "appclip":
                    continue
                if target.device_id in active_la_ids:
                    counters["skipped_active_la"] += 1
                    continue
                eligible_close.append(target)

            await _deliver_for_targets(
                sessions=sessions,
                transports=transports,
                provider_token=provider_token,
                dedup=dedup,
                detail=detail,
                event_id=event_id,
                trigger_kind="close_late",
                targets=eligible_close,
                clock=clock,
                counters=counters,
            )

    # --- 3. Final events (260: A + #13079 App Clip) ---
    for event_id in final_event_ids:
        async with sessions() as db:
            detail = await reader(db, event_id)
            final_targets = await _all_alert_targets(db, event_id, now=clock)

        await _deliver_for_targets(
            sessions=sessions,
            transports=transports,
            provider_token=provider_token,
            dedup=dedup,
            detail=detail,
            event_id=event_id,
            trigger_kind="final",
            targets=final_targets,
            clock=clock,
            counters=counters,
        )

    return GameAlertDispatchSummary(
        live_events_scanned=len(live_event_ids),
        final_events_scanned=len(final_event_ids),
        **counters,
    )
