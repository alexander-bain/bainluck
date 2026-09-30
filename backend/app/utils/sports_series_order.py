"""The sooner game of a series takes the earlier Sports slot (#9602).

THE FINDING
-----------
Seen on production 2026-09-29 11:12Z: ``GET /api/feed?mode=sports`` served
Phillies @ Braves **NLWC Game 2** (tomorrow 18:00Z, score 65) at slot 3 and
**Game 1** of the same series (today 18:00Z, score 45) at slot 15. White Sox @
Astros showed the same split. ``groupFeedIntoSections`` never re-sorts, so
"Upcoming" printed tomorrow's game above today's.

The twenty points are honest about each game on its own: Game 2's only price is
Kalshi 51%, so it earns the close-matchup signals; Game 1 is a 63/37 favorite on
which Kalshi, Polymarket and the sportsbooks agree. What is wrong is only the
ORDER — a reader following the series reads today's game first.

WHY A REORDER AND NOT A SCORE TERM
----------------------------------
Same reasoning as #9489 (``sports_imminent_marquee``): the score measures what
a game promises, and a "played sooner" term big enough to overcome a closeness
gap would move every upcoming card. This pass changes no score and no card
outside a series.

WHAT IT DOES
------------
Upcoming games are grouped by series — same sport, same two teams, either
home/away order. For each series with more than one game on the page, the slots
those games already hold are refilled in kickoff order. So:

* **Only same-matchup upcoming games move, and only among their own slots.**
  Every other card keeps its exact slot; the page's membership is unchanged.
* **The series keeps its best slot.** Game 1 inherits the slot Game 2 earned,
  and Game 2 takes the one Game 1 held.
* **Kickoff ties keep their served order** (a doubleheader's listed times, or
  two rows for one game), so the pass never churns a tie.
* **A marquee pin keeps its exact slot** (``MARQUEE_PIN_KEY``, C185), as in
  #9489's pass.

Pure, stable, length-preserving; returns the input unchanged on any error
(gotcha #42/#43).
"""

from __future__ import annotations

import logging

from app.utils.sports_imminent_marquee import _is_upcoming_event
from app.utils.tonights_games import MARQUEE_PIN_KEY, _parse_dt

logger = logging.getLogger(__name__)


def series_key(item: dict) -> tuple[str, frozenset[str]] | None:
    """``(sport, {team, team})`` for an upcoming game, or ``None`` if unkeyable."""
    data = item.get("data") or {}
    sport = (data.get("sport") or "").strip().lower()
    home = (data.get("home_team") or "").strip().lower()
    away = (data.get("away_team") or "").strip().lower()
    if not sport or not home or not away or home == away:
        return None
    return sport, frozenset((home, away))


def order_series_games_by_kickoff(items: list[dict]) -> tuple[list[dict], dict]:
    """Refill each series' upcoming slots in kickoff order.

    Returns ``(items, meta)``. ``meta["series"]`` counts series with two or more
    games on the page and ``meta["moved"]`` how many slots changed occupant, so
    a page with no series (0/0) never reads the same as one already in order
    (N/0) — gotcha #53.
    """
    empty_meta = {"series": 0, "moved": 0}
    try:
        groups: dict[tuple[str, frozenset[str]], list[int]] = {}
        for i, it in enumerate(items):
            if not _is_upcoming_event(it) or it.get(MARQUEE_PIN_KEY):
                continue
            key = series_key(it)
            if key is None:
                continue
            if _parse_dt((it.get("data") or {}).get("commence_time")) is None:
                continue
            groups.setdefault(key, []).append(i)

        series = [slots for slots in groups.values() if len(slots) > 1]
        meta = dict(empty_meta)
        meta["series"] = len(series)
        if not series:
            return items, meta

        out = list(items)
        for slots in series:
            by_kickoff = sorted(
                slots, key=lambda i: _parse_dt(items[i]["data"]["commence_time"])
            )
            for slot, src in zip(slots, by_kickoff):
                out[slot] = items[src]
                meta["moved"] += slot != src
        if not meta["moved"]:
            return items, meta
        return out, meta
    except Exception:  # pragma: no cover - defensive, mirrors live_first_page
        logger.exception("Sports series kickoff order failed; page unchanged")
        return items, empty_meta
