"""#3016 — `GET /api/events` serves the games on now first, then the games still
to play, then the games already behind us.

WHAT A READER SAW. Production 2026-11-08 05:07Z, `GET /api/events?sport=
soccer_other&limit=50`: the first 13 rows were `suspended`, kicked off 3-5 hours
earlier, with no score (LA Galaxy @ Real Salt Lake, Miami FC @ Louisville City,
Colorado Rapids @ FC Dallas, ...). The 12 games actually being played came
after them, and the 25 still to play after those. The page's own read
(`days=14`, 200 rows) had the same head: 13 suspended, 11 live, 176 scheduled.

WHY. The query orders by `commence_time`, and a game that kicked off at 00:00Z
sorts ahead of one that kicked off at 05:00Z. So whatever started earliest and
never reported an ending leads the list. That holds every day a catch-all league
plays: its unanchored rows go `suspended` at their kickoff and wait there for a
venue grade.

WHAT THIS DOES. It re-sorts the page the query already chose, stably, into three
phases. Each phase keeps the query's own order (kickoff ascending):

  ON_NOW         `live`, and a `suspended` game that has a score: a match stopped
                 mid-play (the MLB rain delay `live/048` made the state for).
                 Its card prints `No result reported · last score 3-2` and it
                 belongs beside the live games.
  STILL_TO_PLAY  `scheduled`, short of the served `started_without_result`
                 (the same predicate the card reads, `event_completion`). An
                 unrecognised status lands here too, as it does on the page.
  BEHIND_US      everything else: a `suspended` row with no score, a `scheduled`
                 row past its grace, a venue-graded row, and every Final.

NOTHING IS DROPPED OR ADDED. The re-sort runs after the query's `limit`, so the
set of rows a page serves is unchanged; only their order is. That is the same
bargain the twin fold makes above it in the route ("folding after the limit
keeps `offset` in raw-row space"): offset pagination still neither skips nor
repeats a row, and the order is the phase order within each page. No caller
pages today (`fetchEvents` sends neither `limit` nor `offset`).

Sorting in SQL instead would have changed WHICH rows a capped page holds.
`?sport=soccer_other&days=14` reaches the 200-row cap, so a phase-first ORDER BY
would push every suspended row and every Final past it. That would hide them by
volume, which the issue itself rules out ("do not fix this by excluding
`suspended`").

THE PAGE IS NOT DECIDED HERE. `/sports/{key}` re-partitions every row with the
shared ladder (`frontend/lib/sports/leagueSections.ts`), so this order only
decides what a payload reader meets first and the order inside the page's live
section, which keeps payload order. The ladder's finer rungs (an ESPN stoppage
word, `#9265`) are deliberately not copied here: a second copy of that allowlist
is the drift `lib/eventState.ts` exists to prevent, and a row they move lands in
the page's Finished section whatever its position in the payload.
"""

from __future__ import annotations

from app.utils.event_completion import EVENT_SUSPENDED

ON_NOW = 0
STILL_TO_PLAY = 1
BEHIND_US = 2

#: Statuses that can only be behind us once ON_NOW and STILL_TO_PLAY declined
#: them. Anything outside the set is an unrecognised status and is treated as
#: still to play, the page's own answer (`eventSectionKey`).
_KNOWN_STATUSES = frozenset({"scheduled", "live", EVENT_SUSPENDED, "completed", "closed"})


def _has_score(row: dict) -> bool:
    return row.get("home_score") is not None and row.get("away_score") is not None


def reader_phase(row: dict) -> int:
    """Which of the three phases a SERVED row belongs to. See the module docstring."""
    status = row.get("status")
    if status == "live":
        return ON_NOW
    if status == EVENT_SUSPENDED and _has_score(row) and not row.get("venue_settled"):
        return ON_NOW
    if status == "scheduled" and not row.get("started_without_result"):
        return STILL_TO_PLAY
    if status not in _KNOWN_STATUSES:
        return STILL_TO_PLAY
    return BEHIND_US


def in_reader_order(rows: list[dict]) -> list[dict]:
    """``rows`` re-sorted by phase. Stable, so each phase keeps the given order."""
    return sorted(rows, key=reader_phase)
