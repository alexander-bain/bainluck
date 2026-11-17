"""When a golf tournament observably started: the cutoff for its "Pregame" (#12740).

A golf tournament page shows each golfer's "Pregame" chance. Until now that was
the first reading we ever stored (``opening_probability``), which can be weeks
early or, for a market picked up late, mid-tournament. The fix serves the last
reading before the first tee time, and that needs the first tee time.

We do not store tee times. DataGolf's ``field-updates`` lists them, but as local
course times with no timezone in our data. So this records the next best thing,
measured rather than guessed: **the first 5-minute in-play poll in which any
player in ROUND 1 has completed a hole.** Play was under way by then, at most one
poll after the first group teed off.

Rules, each one a way the cutoff could otherwise lie:

* **Set once.** ``SET NX``: the first observation sticks, and later polls can
  never move the cutoff forward into the tournament.
* **Round 1 only.** A first sighting in round 2 or later (a market picked up late,
  or this shipping mid-event) records nothing, because it would date "pregame"
  inside the tournament. The reader then uses its fallback (midnight UTC of the
  start date).
* **This event only.** The caller passes the event ids of the open markets that
  belong to the in-play event, so next week's already-open markets cannot borrow
  this week's start.

Pure apart from the one Redis write, so it is tested without a worker.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Optional

FIRST_PLAY_KEY_PREFIX = "bainluck:golf:first_play"
#: Long enough to cover a tournament and the week its page stays up afterwards.
FIRST_PLAY_TTL_S = 30 * 24 * 3600


def first_play_key(tour: str, event_id: str) -> str:
    return f"{FIRST_PLAY_KEY_PREFIX}:{tour}:{event_id}"


def _holes_done(thru) -> bool:
    """Has this player completed at least one hole of the current round?

    DataGolf's ``thru`` is a string: a hole count ("1".."18"), "F" for a finished
    round, or empty / "0" before the player starts.
    """
    if thru is None:
        return False
    text = str(thru).strip().upper()
    if not text:
        return False
    if text.startswith("F"):
        return True
    digits = "".join(ch for ch in text if ch.isdigit())
    return bool(digits) and int(digits) > 0


def round_one_play_seen(players: Iterable) -> bool:
    """Any player in round 1 with a completed hole."""
    return any(
        getattr(p, "current_round", None) == 1 and _holes_done(getattr(p, "thru", None))
        for p in players
    )


def note_first_play(
    redis_client,
    *,
    tour: str,
    event_ids: Iterable[str],
    players: Iterable,
    now: Optional[datetime] = None,
) -> list[str]:
    """Record the first round-1 play for each event id; return the ids newly set.

    Never raises: the in-play poll it rides must not fail because of a cutoff.
    """
    players = list(players)
    ids = sorted({e for e in event_ids if e})
    if not ids or not round_one_play_seen(players):
        return []
    stamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
    written: list[str] = []
    for event_id in ids:
        try:
            if redis_client.set(
                first_play_key(tour, event_id), stamp, nx=True, ex=FIRST_PLAY_TTL_S
            ):
                written.append(event_id)
        except Exception:
            continue
    return written


def read_first_play(redis_client, tour: str, event_id: str) -> Optional[datetime]:
    """The recorded cutoff, or None when none was recorded (use the fallback)."""
    try:
        raw = redis_client.get(first_play_key(tour, event_id))
    except Exception:
        return None
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode()
    try:
        moment = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)
