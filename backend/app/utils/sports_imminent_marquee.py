"""Tonight's marquee game leads the Sports tab's Upcoming list (#9489).

THE FINDING
-----------
Seen on production 2026-09-28 23:05Z, one hour before Monday Night Football:
``GET /api/feed?limit=20&mode=sports`` served Eagles @ Bears (NFL, ``tier:1``,
primetime, national TV, kickoff 00:15Z) at slot 6 with score 48, below four
games that start TOMORROW — Cubs @ Padres 87, Red Sox @ Yankees 70, Canadiens
@ Maple Leafs 55, White Sox @ Astros 52. ``groupFeedIntoSections``
(``frontend/lib/feedSections.ts``) partitions the payload and **never
re-sorts**, so "Upcoming" printed tonight's game fifth, below the fold on a
phone, under a list that read reverse-chronological.

WHY A REORDER AND NOT A SCORE TERM
----------------------------------
The event score measures what is happening INSIDE a game — closeness, upsets,
swings. A game that has not kicked off has none of that, and the score has no
term for "it starts in an hour"; #4898 recorded the same structural fact on the
Discover side and #4541 chose a pin over a boost for the same reason: the drama
stack runs up to the 98 display cap, so any additive term big enough to put
tonight's game first would distort every card it touches. This pass changes no
score. It changes which upcoming game sits in which upcoming slot.

WHAT IT DOES
------------
The slots on the page that currently hold a not-yet-started game are refilled:
first every **imminent marquee** game (not started, ``tier:1``, kickoff strictly
ahead and within ``IMMINENT_KICKOFF_HOURS``), then every other not-started game,
each group in its original served order. So:

* **Nothing but upcoming games moves.** Live, finished, futures, tournament and
  concept cards keep their exact slots — the live hoist, the finished-rail cap
  and the futures cap all keep what they decided.
* **The page keeps the same number of game slots.** An imminent game in the tail
  can take a first-page upcoming slot, and the later-starting game it displaces
  takes the tail slot it vacated. That is a trade of one upcoming game for
  another, so the pass is bounded by construction: on an NFL Sunday with twelve
  marquee kickoffs inside the window, Upcoming leads with the day's games and
  holds exactly as many cards as it did.
* **Minor games are not promoted.** Only ``tier:1`` qualifies, so a next-day
  playoff game still sits above an imminent Challenger match or an MLS fixture —
  the second direction of #9489's done-when.
* **A marquee pin keeps its exact slot** (``MARQUEE_PIN_KEY``, C185), the same
  guarantee the live hoist gives.

WHY SIX HOURS
-------------
It is ``_DISCOVER_IMMINENT_KICKOFF_HOURS`` (#4898), the window after which a
marquee game becomes Discover material; a test pins the two together so the
surfaces cannot disagree about when a game counts as "tonight". It is wider
than the one hour #9489 names on purpose: a reader who opens the tab at 1pm on
a Monday should already see tonight's game above tomorrow's.

WHY ``commence_time`` STRICTLY AHEAD
------------------------------------
A start time in the past on a still-``scheduled`` row means the status is
lagging, not that the game is imminent — ``tonights_games._is_eligible`` and
``_imminent_marquee_kickoff_ids`` both refuse it for that reason, and this pass
must not disagree with them. Once the game goes live the live hoist owns it.

Pure, stable, length-preserving; returns the input unchanged on any error
(gotcha #42/#43).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from app.utils.tonights_games import MARQUEE_PIN_KEY, _parse_dt

logger = logging.getLogger(__name__)

#: How long before kickoff a marquee game leads Upcoming. Pinned equal to
#: ``feed._DISCOVER_IMMINENT_KICKOFF_HOURS`` by
#: ``test_sports_imminent_marquee_9489`` — see the module docstring.
IMMINENT_KICKOFF_HOURS = 6

#: "Not started yet" — mirrors ``tonights_games._is_eligible`` and
#: ``feed._DISCOVER_IMMINENT_STATUSES``, empty string included.
UPCOMING_STATUSES = frozenset({"scheduled", "upcoming", "pre", ""})


def _is_upcoming_event(item: object) -> bool:
    if not isinstance(item, dict) or item.get("type") != "event":
        return False
    data = item.get("data") or {}
    status = (data.get("status") or "").strip().lower()
    return status in UPCOMING_STATUSES


def is_imminent_marquee_game(
    item: dict, now: datetime, *, hours: int = IMMINENT_KICKOFF_HOURS
) -> bool:
    """A not-started ``tier:1`` game whose kickoff is ahead and within ``hours``."""
    if not _is_upcoming_event(item):
        return False
    data = item.get("data") or {}
    if "tier:1" not in (data.get("event_tags") or []):
        return False
    commence = _parse_dt(data.get("commence_time"))
    if commence is None:
        return False
    return now < commence <= now + timedelta(hours=hours)


def lead_upcoming_with_imminent_marquee_games(
    items: list[dict],
    *,
    now: datetime | None = None,
    hours: int = IMMINENT_KICKOFF_HOURS,
) -> tuple[list[dict], dict]:
    """Refill the page's upcoming-game slots, imminent marquee games first.

    Returns ``(items, meta)``. ``meta["imminent"]`` counts the qualifying games
    and ``meta["moved"]`` how many upcoming slots changed occupant, so a request
    with nothing to do (0/0) never reads the same as one where every imminent
    game was already in front (N/0) — gotcha #53.
    """
    empty_meta = {"imminent": 0, "moved": 0, "hours": hours}
    try:
        now = now or datetime.now(timezone.utc)
        slots = [
            i
            for i, it in enumerate(items)
            if _is_upcoming_event(it) and not it.get(MARQUEE_PIN_KEY)
        ]
        imminent = [
            i for i in slots if is_imminent_marquee_game(items[i], now, hours=hours)
        ]
        meta = dict(empty_meta)
        meta["imminent"] = len(imminent)
        if not imminent:
            return items, meta

        imminent_set = set(imminent)
        order = imminent + [i for i in slots if i not in imminent_set]
        out = list(items)
        for slot, src in zip(slots, order):
            out[slot] = items[src]
        meta["moved"] = sum(1 for slot, src in zip(slots, order) if slot != src)
        return out, meta
    except Exception:  # pragma: no cover - defensive, mirrors live_first_page
        logger.exception("Sports imminent-marquee upcoming lead failed; page unchanged")
        return items, empty_meta
