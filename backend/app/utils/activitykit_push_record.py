"""#10542 step 1: one log line per Live Activity push, saying how old its numbers were.

On Nov 16 (Magic at Celtics) Alex's locked phone sat minutes behind Apple Sports
while every push came back ``accepted``. One read-only look showed our score was
current and the phone was about three priority-5 pushes behind. Nothing recorded
that per push. This line does, for every push, so "is the lag ours or Apple's?"
is answered from the logs instead of a one-off production read.

Each line carries:
- ``activity``: a short hash of the activity id (never the id or any token);
- ``event``, ``kind`` (update / terminal / stop) and ``priority`` (10 = what the
  reader sees changed, 5 = a refresh of the same screen);
- ``screen``: lifecycle, away-home score and the printed chance, so consecutive
  lines for one activity show what changed;
- ``score_age`` / ``chance_age``: seconds from the reading's own clock to the
  moment the push left (``-`` when the push carries no such clock);
- ``outcome`` / ``reason``: Apple's answer as our transport classifies it
  (``accepted`` is Apple taking the push, not the phone showing it);
- ``apple_ms``: how long the send took, from dispatch to answer;
- ``attempt``: 1 for a first send, higher for a retry of the same command.

Everything is read from the command's own body, so the ages are those of the
exact reading Apple received, not a newer one observed while it was in flight.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging

from app.utils.activitykit_delivery_state import Attempt

logger = logging.getLogger("app.activitykit.push")

_SWIFT_REFERENCE = datetime(2001, 1, 1, tzinfo=timezone.utc)


def activity_ref(activity_id: str) -> str:
    """Twelve hex characters: enough to follow one activity across lines."""
    return hashlib.sha256(activity_id.encode("utf-8")).hexdigest()[:12]


def _age(snapshot: dict, key: str, sent_at: datetime) -> str:
    value = snapshot.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return "-"
    observed = _SWIFT_REFERENCE + timedelta(seconds=value)
    return f"{(sent_at - observed).total_seconds():.1f}"


def _screen(snapshot: dict) -> str:
    def part(key: str) -> str:
        value = snapshot.get(key)
        return "-" if value is None else str(value)

    chance = snapshot.get("homeRenderedPercent")
    return (
        f"{part('lifecycle')} {part('awayScore')}-{part('homeScore')} "
        f"{'-' if chance is None else str(chance) + '%'}"
    )


def push_record(
    attempt: Attempt,
    *,
    activity_id: str,
    sent_at: datetime,
    answered_at: datetime,
    outcome: str,
    reason: str,
) -> str:
    """The one line for one push. Pure; raises nothing for an odd body."""
    try:
        aps = json.loads(attempt.push.body).get("aps", {})
        snapshot = aps.get("content-state", {}).get("snapshot", {})
    except (ValueError, AttributeError):
        snapshot = {}
    apple_ms = max(0, round((answered_at - sent_at).total_seconds() * 1000))
    return (
        f"activitykit push: activity={activity_ref(activity_id)}"
        f" event={snapshot.get('eventID', '-')}"
        f" kind={attempt.kind} priority={attempt.push.priority}"
        f" screen=[{_screen(snapshot)}]"
        f" score_age={_age(snapshot, 'scoreObservedAt', sent_at)}"
        f" chance_age={_age(snapshot, 'probabilityObservedAt', sent_at)}"
        f" outcome={outcome} reason={reason}"
        f" apple_ms={apple_ms} attempt={attempt.count}"
    )


def log_push(attempt: Attempt, **fields) -> None:
    """Log the line; a logging problem never touches the send's own outcome."""
    try:
        logger.info(push_record(attempt, **fields))
    except Exception:  # pragma: no cover - defensive: the record is best-effort
        pass
