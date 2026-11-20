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
import re
from typing import Literal

Lifecycle = Literal["scheduled", "live", "suspended", "final", "closed", "unknown"]
Result = Literal["home", "away", "draw"]
_LIFECYCLES = {"scheduled", "live", "suspended", "final", "closed", "unknown"}
_RESULTS = {"home", "away", "draw"}
_FORECAST_LIFECYCLES = {"scheduled", "live"}
_PERIOD_LIFECYCLES = {"live", "suspended"}
_TERMINAL_LIFECYCLES = {"final", "closed"}
_HEX_RE = re.compile(r"^#[0-9A-F]{6}$")
_SPORT_RE = re.compile(r"^[A-Za-z0-9_]{1,64}$")
_SWIFT_REFERENCE = datetime(2001, 1, 1, tzinfo=timezone.utc)
_MAX_SWIFT_INT = (1 << 63) - 1
MAX_PAYLOAD_BYTES = 4096
# #10542 step 4: the activity turns stale only when the score has gone unconfirmed
# this long (the chance's clock is used only while there is no score). It was the
# older of both clocks + 120 s, so two minutes of Apple's priority-5 delay turned
# a 20-second-old score orange (Magic at Celtics, Nov 16). Not a fetch TTL. The
# app's GameActivityController.staleDate(for:) applies the same rule while open.
OBSERVATION_MAX_AGE = timedelta(seconds=360)


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
    # #12999 — headline display fields matching Swift GameActivitySnapshot so
    # server APNs pushes draw the exact same headline as the app foreground.
    away_rendered_percent: int | None = None
    home_headline_tenths: int | None = None
    sport: str | None = None
    home_abbreviation: str | None = None
    away_abbreviation: str | None = None
    home_color_hex: str | None = None
    away_color_hex: str | None = None
    away_secondary_color_hex: str | None = None
    period_label: str | None = None
    result: Result | None = None
    pregame_away_percent: int | None = None
    pregame_home_percent: int | None = None
    # #13000 (250-A) — True only on a scoreless live game whose league has no
    # live score feed; omitted otherwise to stay byte-identical for 1.0.6.
    score_source_unavailable: bool | None = None

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
        if self.away_rendered_percent is not None:
            _integer(
                self.away_rendered_percent,
                "away_rendered_percent",
                minimum=0,
                maximum=100,
            )
            if self.home_rendered_percent is None:
                raise ActivityKitPayloadError(
                    "away_rendered_percent requires home_rendered_percent"
                )
        if self.home_headline_tenths is not None:
            _integer(
                self.home_headline_tenths,
                "home_headline_tenths",
                minimum=0,
                maximum=1000,
            )
            if self.away_rendered_percent is None:
                raise ActivityKitPayloadError(
                    "home_headline_tenths requires a two-way pair"
                )
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
        if self.sport is not None:
            if not isinstance(self.sport, str) or not _SPORT_RE.match(self.sport):
                raise ActivityKitPayloadError("sport must be a short plain sport key")
        for name in ("home_abbreviation", "away_abbreviation"):
            value = getattr(self, name)
            if value is not None and (
                not isinstance(value, str) or not 1 <= len(value.strip()) <= 6
            ):
                raise ActivityKitPayloadError(f"{name} must be 1..6 characters")
        for name in ("home_color_hex", "away_color_hex", "away_secondary_color_hex"):
            value = getattr(self, name)
            if value is not None and (
                not isinstance(value, str) or not _HEX_RE.match(value)
            ):
                raise ActivityKitPayloadError(f"{name} must be #RRGGBB")
        if self.period_label is not None:
            if (
                self.lifecycle not in _PERIOD_LIFECYCLES
                or not isinstance(self.period_label, str)
                or not 1 <= len(self.period_label.strip()) <= 24
            ):
                raise ActivityKitPayloadError(
                    "period_label requires a live or suspended lifecycle and 1..24 chars"
                )
        if self.result is not None:
            if self.lifecycle != "final" or self.result not in _RESULTS:
                raise ActivityKitPayloadError(
                    "result requires final lifecycle and home/away/draw"
                )
        if (self.pregame_away_percent is None) != (self.pregame_home_percent is None):
            raise ActivityKitPayloadError(
                "pregame_away_percent and pregame_home_percent must appear together"
            )
        for name in ("pregame_away_percent", "pregame_home_percent"):
            value = getattr(self, name)
            if value is not None:
                _integer(value, name, minimum=0, maximum=100)
        if self.score_source_unavailable is not None:
            if (
                self.score_source_unavailable is not True
                or self.lifecycle != "live"
                or self.home_score is not None
                or self.away_score is not None
            ):
                raise ActivityKitPayloadError(
                    "score_source_unavailable may only be True on a scoreless live game"
                )

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
            ("awayRenderedPercent", self.away_rendered_percent),
            ("homeHeadlineTenths", self.home_headline_tenths),
            ("sport", self.sport),
            ("homeAbbreviation", self.home_abbreviation),
            ("awayAbbreviation", self.away_abbreviation),
            ("homeColorHex", self.home_color_hex),
            ("awayColorHex", self.away_color_hex),
            ("awaySecondaryColorHex", self.away_secondary_color_hex),
            ("periodLabel", self.period_label),
            ("result", self.result),
            ("pregameAwayPercent", self.pregame_away_percent),
            ("pregameHomePercent", self.pregame_home_percent),
            ("scoreSourceUnavailable", self.score_source_unavailable),
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


#: Apple's two Live Activity priorities. "5" is delivered when convenient, so a
#: locked phone can show a reading minutes old; "10" is delivered now (#10542:
#: Magic at Celtics, Nov 16, the phone sat three priority-5 pushes behind a score
#: the server already had).
PRIORITIES = ("5", "10")


def _priority(value: object) -> str:
    if value not in PRIORITIES:
        raise ActivityKitPayloadError("APNs priority must be '5' or '10'")
    return value


@dataclass(frozen=True)
class ActivityKitPush:
    """Encoded bounded body, without a token, credentials, topic or network client."""

    body: bytes
    priority: str = "5"

    def __post_init__(self) -> None:
        _priority(self.priority)

    @property
    def headers(self) -> dict[str, str]:
        # Routine updates do not alert. Expiration zero prevents APNs storing an
        # old reading while a device is offline; retry/reconciliation is a later owner.
        return {
            "apns-push-type": "liveactivity",
            "apns-priority": self.priority,
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


def _encode(aps: dict, priority: str = "5") -> ActivityKitPush:
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
    return ActivityKitPush(body=body, priority=_priority(priority))


def build_activitykit_update(
    snapshot: GameActivitySnapshot, *, sent_at: datetime, priority: str = "5"
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
    has_score = snapshot.home_score is not None or snapshot.away_score is not None
    has_chance = snapshot.home_rendered_percent is not None
    # A displayed number with no clock is stale now. Otherwise the score's clock
    # decides; the chance prints its own age and decides only when there is no score.
    unknown = (has_score and snapshot.score_observed_at is None) or (
        has_chance and snapshot.probability_observed_at is None
    )
    clock = (
        snapshot.score_observed_at
        if has_score
        else snapshot.probability_observed_at if has_chance else None
    )
    if unknown or clock is None:
        aps["stale-date"] = aps["timestamp"]
    else:
        aps["stale-date"] = max(
            0,
            math.floor((_date(clock, "observation") + OBSERVATION_MAX_AGE).timestamp()),
        )
    return _encode(aps, priority)


def build_activitykit_end(
    snapshot: GameActivitySnapshot,
    *,
    sent_at: datetime,
    reason: Literal["terminal", "stop"] = "terminal",
    priority: str = "5",
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
    return _encode(aps, priority)
