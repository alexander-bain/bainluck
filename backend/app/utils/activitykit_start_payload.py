"""Pure APNs push-to-start contract for Live Activities (#13052 / 254-A / 178-B).

Follows the agreed payload contract from #11934 (Nov 15):
- `apns-push-type: liveactivity`, `apns-priority: 10`, `apns-expiration: 0`
- `aps.event = "start"`, `attributes-type = "GameActivityAttributes"`,
  `attributes = {"eventID": N}`, `content-state = snapshot.content_state()`,
  `stale-date = sent_at + 10 min`, `alert = {"title": ..., "body": ...}`,
  and `input-push-token = 1` when the device runs iOS 18+.

Disjoint from `activitykit_payload.py` update/end code so start-push payloads
automatically inherit whatever headline fields `GameActivitySnapshot.content_state()`
emits without duplicating schema logic.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import math

from app.utils.activitykit_payload import (
    ActivityKitPayloadError,
    ActivityKitPush,
    GameActivitySnapshot,
    MAX_PAYLOAD_BYTES,
    OBSERVATION_MAX_AGE,
)

#: Apple's Live Activity attributes type name in Swift (`GameActivityAttributes.swift`).
GAME_ACTIVITY_ATTRIBUTES_TYPE = "GameActivityAttributes"
#: Kickoff start-push staleness horizon before subsequent 30 s updates take over (#11934).
START_STALE_WINDOW = timedelta(minutes=10)


def _aware_utc(value: object, name: str) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ActivityKitPayloadError(f"{name} must be a timezone-aware datetime")
    return value.astimezone(timezone.utc)


def _format_percent(
    percent: int, *, sub_one: bool = False, above_ninety_nine: bool = False
) -> str:
    if sub_one or percent <= 0:
        return "<1%"
    if above_ninety_nine or percent >= 100:
        return ">99%"
    return f"{percent}%"


def build_activitykit_start_alert(
    snapshot: GameActivitySnapshot,
    *,
    sent_at: datetime,
    freshness_window: timedelta = OBSERVATION_MAX_AGE,
) -> dict[str, str]:
    """Build the Apple-required `aps.alert` for a push-to-start Live Activity.

    Apple requires an `alert` dictionary on `event: "start"` pushes. Includes a
    team win-chance only when `probability_observed_at` is present and fresh
    within `freshness_window`; otherwise omits the number rather than quoting an
    older reading.
    """
    sent_at_utc = _aware_utc(sent_at, "sent_at")
    title = f"{snapshot.away_team} at {snapshot.home_team}"
    body = "Starting now"

    home_pct = snapshot.home_rendered_percent
    prob_at = snapshot.probability_observed_at
    if home_pct is not None and prob_at is not None:
        prob_utc = _aware_utc(prob_at, "probability_observed_at")
        age = sent_at_utc - prob_utc
        if timedelta(0) <= age <= freshness_window:
            if home_pct >= 50:
                leader = snapshot.home_team
                leader_pct = home_pct
                sub_one = snapshot.home_sub_one is True
                above_ninety_nine = snapshot.home_above_ninety_nine is True
            else:
                leader = snapshot.away_team
                leader_pct = (
                    snapshot.away_rendered_percent
                    if snapshot.away_rendered_percent is not None
                    else 100 - home_pct
                )
                sub_one = snapshot.away_sub_one is True
                above_ninety_nine = snapshot.away_above_ninety_nine is True
            body = (
                f"Starting now · {leader} "
                f"{_format_percent(leader_pct, sub_one=sub_one, above_ninety_nine=above_ninety_nine)}"
            )

    return {"title": title, "body": body}


def build_activitykit_start(
    snapshot: GameActivitySnapshot,
    *,
    sent_at: datetime,
    input_push_token: bool = False,
    priority: str = "10",
    freshness_window: timedelta = OBSERVATION_MAX_AGE,
) -> ActivityKitPush:
    """Encode an APNs push-to-start payload for a live game (`event: "start"`).

    Only live games may trigger a kickoff start push. Terminal (`final`/`closed`),
    scheduled, or suspended snapshots are rejected so a stale or ended game never
    opens a phantom Live Activity.
    """
    if not isinstance(snapshot, GameActivitySnapshot):
        raise ActivityKitPayloadError(
            "snapshot must be a validated GameActivitySnapshot"
        )
    if snapshot.lifecycle != "live":
        raise ActivityKitPayloadError(
            "A Live Activity start push requires a live game snapshot"
        )
    sent_at_utc = _aware_utc(sent_at, "sent_at")
    timestamp = math.floor(sent_at_utc.timestamp())
    if timestamp < 0:
        raise ActivityKitPayloadError("sent_at must have a nonnegative Unix timestamp")
    for clock in (snapshot.score_observed_at, snapshot.probability_observed_at):
        if clock is not None and _aware_utc(clock, "observation") > sent_at_utc:
            raise ActivityKitPayloadError(
                "A producer observation cannot be later than send time"
            )

    aps: dict = {
        "timestamp": timestamp,
        "event": "start",
        "attributes-type": GAME_ACTIVITY_ATTRIBUTES_TYPE,
        "attributes": {"eventID": snapshot.event_id},
        "content-state": snapshot.content_state(),
        "stale-date": max(
            0, math.floor((sent_at_utc + START_STALE_WINDOW).timestamp())
        ),
        "alert": build_activitykit_start_alert(
            snapshot, sent_at=sent_at_utc, freshness_window=freshness_window
        ),
    }
    if input_push_token:
        aps["input-push-token"] = 1

    try:
        body = json.dumps(
            {"aps": aps}, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        ).encode("utf-8")
    except (ValueError, UnicodeError) as error:
        raise ActivityKitPayloadError("Payload must be finite UTF-8 JSON") from error
    if len(body) > MAX_PAYLOAD_BYTES:
        raise ActivityKitPayloadError(
            "ActivityKit start payload exceeds the APNs 4 KiB limit"
        )
    return ActivityKitPush(body=body, priority=priority)
