"""Pure APNs update/end contract for W3.2 (#10542), with no delivery side effects.

The content-state is GameActivityAttributes.ContentState from W3.1: a single
``snapshot``. Its Date values use Swift Codable's default 2001 reference epoch;
APNs envelope dates use Unix seconds. Already-rendered percentages come from
the shared snapshot projection, never a second backend rounding decision.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import math
from typing import Literal

Lifecycle = Literal["scheduled", "live", "suspended", "final", "closed", "unknown"]
_LIFECYCLES = {"scheduled", "live", "suspended", "final", "closed", "unknown"}
_FORECAST_LIFECYCLES = {"scheduled", "live"}
_TERMINAL_LIFECYCLES = {"final", "closed"}
_SWIFT_REFERENCE = datetime(2001, 1, 1, tzinfo=timezone.utc)
_MAX_SWIFT_INT = (1 << 63) - 1
MAX_PAYLOAD_BYTES = 4096
# Same observation-age policy as W3.1 GameActivityController, not a fetch TTL.
OBSERVATION_MAX_AGE = timedelta(seconds=120)


class ActivityKitPayloadError(ValueError):
    """The proposed push cannot truthfully represent the shared game contract."""


def _integer(value: object, name: str, *, minimum: int, maximum: int) -> None:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ActivityKitPayloadError(f"{name} must be an integer in range")


def _date(value: object, name: str) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ActivityKitPayloadError(f"{name} must be a timezone-aware datetime")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class GameActivitySnapshot:
    """Validated fields of the existing Swift snapshot; no implicit observation time."""

    event_id: int
    home_team: str
    away_team: str
    lifecycle: Lifecycle
    home_score: int | None = None
    away_score: int | None = None
    home_rendered_percent: int | None = None
    score_observed_at: datetime | None = None
    probability_observed_at: datetime | None = None

    def __post_init__(self) -> None:
        _integer(self.event_id, "event_id", minimum=1, maximum=_MAX_SWIFT_INT)
        for name in ("home_team", "away_team"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ActivityKitPayloadError(f"{name} must name a team")
        if not isinstance(self.lifecycle, str) or self.lifecycle not in _LIFECYCLES:
            raise ActivityKitPayloadError(
                "lifecycle must come from the shared projection"
            )
        for name in ("home_score", "away_score"):
            value = getattr(self, name)
            if value is not None:
                _integer(value, name, minimum=0, maximum=_MAX_SWIFT_INT)
        if self.home_rendered_percent is not None:
            _integer(
                self.home_rendered_percent,
                "home_rendered_percent",
                minimum=0,
                maximum=100,
            )
            if self.lifecycle not in _FORECAST_LIFECYCLES:
                raise ActivityKitPayloadError("This lifecycle must suppress forecasts")
        if (
            self.probability_observed_at is not None
            and self.home_rendered_percent is None
        ):
            raise ActivityKitPayloadError(
                "A probability clock requires its displayed reading"
            )
        for name in ("score_observed_at", "probability_observed_at"):
            value = getattr(self, name)
            if value is not None:
                _date(value, name)

    @property
    def is_terminal(self) -> bool:
        return self.lifecycle in _TERMINAL_LIFECYCLES

    def content_state(self) -> dict:
        """Exactly ContentState(snapshot:), including Swift optional-key omission."""
        snapshot: dict = {
            "eventID": self.event_id,
            "homeTeam": self.home_team,
            "awayTeam": self.away_team,
            "lifecycle": self.lifecycle,
        }
        for key, value in (
            ("homeScore", self.home_score),
            ("awayScore", self.away_score),
            ("homeRenderedPercent", self.home_rendered_percent),
        ):
            if value is not None:
                snapshot[key] = value
        for key, value in (
            ("scoreObservedAt", self.score_observed_at),
            ("probabilityObservedAt", self.probability_observed_at),
        ):
            if value is not None:
                snapshot[key] = (_date(value, key) - _SWIFT_REFERENCE).total_seconds()
        return {"snapshot": snapshot}


@dataclass(frozen=True)
class ActivityKitPush:
    """Encoded bounded body, without a token, credentials, topic or network client."""

    body: bytes

    @property
    def headers(self) -> dict[str, str]:
        # Routine updates do not alert. Expiration zero prevents APNs storing an
        # old reading while a device is offline; retry/reconciliation is a later owner.
        return {
            "apns-push-type": "liveactivity",
            "apns-priority": "5",
            "apns-expiration": "0",
        }


def _envelope(snapshot: GameActivitySnapshot, sent_at: datetime, event: str) -> dict:
    if not isinstance(snapshot, GameActivitySnapshot):
        raise ActivityKitPayloadError(
            "snapshot must be a validated GameActivitySnapshot"
        )
    sent_at = _date(sent_at, "sent_at")
    timestamp = math.floor(sent_at.timestamp())
    if timestamp < 0:
        raise ActivityKitPayloadError("sent_at must have a nonnegative Unix timestamp")
    for clock in (snapshot.score_observed_at, snapshot.probability_observed_at):
        if clock is not None and _date(clock, "observation") > sent_at:
            raise ActivityKitPayloadError(
                "A producer observation cannot be later than send time"
            )
    return {
        "timestamp": timestamp,
        "event": event,
        "content-state": snapshot.content_state(),
    }


def _encode(aps: dict) -> ActivityKitPush:
    try:
        body = json.dumps(
            {"aps": aps}, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        ).encode("utf-8")
    except (ValueError, UnicodeError) as error:
        raise ActivityKitPayloadError("Payload must be finite UTF-8 JSON") from error
    if len(body) > MAX_PAYLOAD_BYTES:
        raise ActivityKitPayloadError(
            "ActivityKit payload exceeds the APNs 4 KiB limit"
        )
    return ActivityKitPush(body=body)


def build_activitykit_update(
    snapshot: GameActivitySnapshot, *, sent_at: datetime
) -> ActivityKitPush:
    """Update a nonterminal game; freshness belongs to displayed producer clocks.

    ``sent_at`` is explicitly provided send/ordering time. It never supplies a
    missing producer clock. Unknown displayed clocks mark the reading stale now.
    """
    aps = _envelope(snapshot, sent_at, "update")
    if snapshot.is_terminal:
        raise ActivityKitPayloadError(
            "Authoritative terminal lifecycle requires an end push"
        )
    clocks = []
    if snapshot.home_score is not None or snapshot.away_score is not None:
        clocks.append(snapshot.score_observed_at)
    if snapshot.home_rendered_percent is not None:
        clocks.append(snapshot.probability_observed_at)
    if not clocks or any(clock is None for clock in clocks):
        aps["stale-date"] = aps["timestamp"]
    else:
        oldest = min(_date(clock, "observation") for clock in clocks)
        aps["stale-date"] = max(
            0, math.floor((oldest + OBSERVATION_MAX_AGE).timestamp())
        )
    return _encode(aps)


def build_activitykit_end(
    snapshot: GameActivitySnapshot,
    *,
    sent_at: datetime,
    reason: Literal["terminal", "stop"] = "terminal",
) -> ActivityKitPush:
    """End for authoritative final/closed, or an explicit user stop.

    A terminal end keeps the system's default final-reading dismissal behavior.
    An explicit stop immediately dismisses without relabeling the game as final.
    """
    aps = _envelope(snapshot, sent_at, "end")
    if reason == "terminal":
        if not snapshot.is_terminal:
            raise ActivityKitPayloadError(
                "An end push requires terminal authority or explicit stop"
            )
    elif reason == "stop":
        aps["dismissal-date"] = max(0, aps["timestamp"] - 1)
    else:
        raise ActivityKitPayloadError("Unknown end reason")
    return _encode(aps)
