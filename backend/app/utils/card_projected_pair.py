"""#11295 — the sportsbooks' projected final on list cards, read once per page.

`/api/events/{id}` and `/api/events/search` serve `current_odds.projected_home_score`
/ `projected_away_score`: the mean of each sportsbook's spread-and-total pair over
the latest row per book, after the stale-book filter and with reversed books left
out. Measured by UX on 2026-10-19 22:24Z, event 14780563 (49ers v Commanders,
before kickoff): 29.6 / 22.3 from 21 sportsbooks on detail and search, while
`/api/feed` and `/api/leagues/{sport}` `upcoming_games` served probabilities
only. The shared card already prints a pair when it is present, so Sports,
Discover and the league rail showed no projected final for a game whose own page
had one.

Neither list route read the snapshot rows at all; their `current_odds` is the
blend and nothing else. So this is one batched read of the SAME statement the
search and list routes use (`latest_odds_per_bookmaker_query`), sized to the cards
actually being served, then the SAME three steps `get_event` runs, in its order:
`filter_stale_bookmaker_snapshots` → `detect_reversed_bookmakers` →
`aggregate_bookmaker_odds`. No second formula and no per-card read.

What a card may carry is narrower than what detail serves, on purpose:

* **Scheduled or live only.** A finished game's latest pair is the last in-game
  reading, not a pregame forecast (that baseline is #11296, separate).
* **Live needs live evidence.** On a live game the stale filter falls back to
  every book when no book has quoted since the start, so detail can serve the
  pregame pair under a live game. A card withholds it: every row the pair came
  from must have been confirmed at or after `commence_time` — the filter's own
  test, not a new cutoff.
* **A real pair.** Both halves present, finite and not below zero, and the sport's
  spread must be a margin (`sportsbook_spread_is_a_margin`, the writer's own
  gate). Never one half, never a complement, never 0–0.

The pair travels with `projection_captured_at`, which is detail's
`current_odds.captured_at` (the newest row the consensus read). It has its own name
because the card's `current_odds` probability is the blend, and a bare
`captured_at` there would date the wrong number (#7221).
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from datetime import datetime
from typing import Any, Iterable, Optional

from app.utils.odds_filtering import _effective_time, filter_stale_bookmaker_snapshots
from app.utils.odds_math import (
    aggregate_bookmaker_odds,
    detect_reversed_bookmakers,
    sportsbook_spread_is_a_margin,
)

logger = logging.getLogger(__name__)

#: Served statuses a card may carry a projected pair on.
CARD_PROJECTION_STATUSES = frozenset({"scheduled", "live"})

#: The keys this module adds to a card's `current_odds`. Additive only.
CARD_PROJECTION_KEYS = (
    "projected_home_score",
    "projected_away_score",
    "projection_captured_at",
)


def card_projection_wanted(
    served_status: Optional[str], sport_key: Optional[str]
) -> bool:
    """True when a card in this state and sport could carry a pair at all.

    Decides which ids are read, so a finished game or a run-line sport costs
    nothing.
    """
    return served_status in CARD_PROJECTION_STATUSES and sportsbook_spread_is_a_margin(
        sport_key
    )


def _score(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 0:
        return None
    return number


def card_projected_pair(
    snapshots: list,
    *,
    stored_status: Optional[str],
    served_status: Optional[str],
    commence_time: Optional[datetime],
    sport_key: Optional[str],
) -> Optional[dict]:
    """The card's projected pair from one event's latest row per sportsbook, or None.

    ``snapshots`` is exactly what `latest_odds_per_bookmaker_query` returns for
    the event. ``stored_status`` drives the stale filter, as on detail;
    ``served_status`` is the status the card prints and decides admission.
    """
    if not snapshots or not card_projection_wanted(served_status, sport_key):
        return None

    filtered = filter_stale_bookmaker_snapshots(
        snapshots, event_status=stored_status, commence_time=commence_time
    )
    if not filtered:
        return None

    if served_status == "live":
        if commence_time is None:
            return None
        if any(_effective_time(s) < commence_time for s in filtered):
            return None

    reversed_books = detect_reversed_bookmakers(filtered)
    agg_snapshots = [s for s in filtered if s.bookmaker not in reversed_books]
    if not agg_snapshots:
        agg_snapshots = filtered
    aggregated = aggregate_bookmaker_odds(agg_snapshots)

    home = _score(aggregated.get("projected_home_score"))
    away = _score(aggregated.get("projected_away_score"))
    if home is None or away is None:
        return None

    return {
        "projected_home_score": home,
        "projected_away_score": away,
        "projection_captured_at": max(s.captured_at for s in filtered).isoformat(),
    }


def attach_card_projected_pair(
    current_odds: Optional[dict], pair: Optional[dict]
) -> None:
    """Add ``pair`` to a card's existing ``current_odds``. Mutates in place.

    Only an existing ``current_odds`` gains the keys: a card with no probability
    has no `current_odds` to extend, and creating one here would hand the client
    an object with no probability in it. Existing keys are never overwritten.
    """
    if not isinstance(current_odds, dict) or not pair:
        return
    for key in CARD_PROJECTION_KEYS:
        if key in pair and key not in current_odds:
            current_odds[key] = pair[key]


async def read_card_projected_pairs(db: Any, cards: Iterable[dict]) -> dict[int, dict]:
    """``{event_id: pair}`` for the cards that may carry one, in ONE statement.

    Each card is ``{"id", "stored_status", "served_status", "commence_time",
    "sport_key"}``. Cards that `card_projection_wanted` refuses are not read.
    Nothing is caught here: the caller decides what a failed read costs.
    """
    from app.routes.events import latest_odds_per_bookmaker_query

    wanted: dict[int, dict] = {}
    for card in cards:
        if card_projection_wanted(card.get("served_status"), card.get("sport_key")):
            wanted[int(card["id"])] = card
    if not wanted:
        return {}

    by_event: dict[int, list] = defaultdict(list)
    for snap in (
        (await db.execute(latest_odds_per_bookmaker_query(sorted(wanted))))
        .scalars()
        .all()
    ):
        by_event[snap.event_id].append(snap)

    pairs: dict[int, dict] = {}
    for event_id, snaps in by_event.items():
        card = wanted.get(event_id)
        if card is None:
            continue
        try:
            pair = card_projected_pair(
                snaps,
                stored_status=card.get("stored_status"),
                served_status=card.get("served_status"),
                commence_time=card.get("commence_time"),
                sport_key=card.get("sport_key"),
            )
        except Exception:  # noqa: BLE001 — gotcha #42: one event, not the page
            logger.exception("card projected pair failed for event %s", event_id)
            continue
        if pair is not None:
            pairs[event_id] = pair
    return pairs
