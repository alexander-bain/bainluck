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
* **A real pair.** Both halves present, finite and not below zero. Never one
  half, never a complement.
* **A sport whose pair is a final score.** American football, basketball and
  soccer only — UX's table in `frontend/lib/projectedFinalPair.ts`. The writer's
  `sportsbook_spread_is_a_margin` is wider (everything but baseball and fights)
  and is NOT the gate here: a puck line is pinned at ±1.5 (NHL 15333056 and
  15332424 both "4 – 3" whatever the price; AHL 15327140 "0.0 – 1.5") and a
  tennis pair is games under a sets scoreboard (15326853 "11.2 – 11.3" over
  0 – 2). The shared gate stays as it is; the writer and the web read it.

The read is optional, so it carries its own server-side bound
(`read_card_projected_pairs_bounded`): a slow read costs the cards their pair,
never the events stage that already scored them.

The pair travels with `projection_captured_at`, which is detail's
`current_odds.captured_at` (the newest row the consensus read). It has its own name
because the card's `current_odds` probability is the blend, and a bare
`captured_at` there would date the wrong number (#7221).

── #2920: THE IN-PLAY PAIR, MARKED (`current_odds.live_projection`) ────────────

A bare live pair says nothing about which reading it is. Detail and search serve
`current_odds.projected_*` through the stale filter's fall-back-to-all, so on a
live game they can hold the pregame pair, and their `captured_at` is the newest
`captured_at`, not the effective time this module's live gate reads. A client
therefore cannot tell an in-play pair from a pregame one. UX's card and the event
page print a live projected final only from one marked object, served the same
way on all four routes (`/api/events/{id}`, `/api/events/search`, `/api/feed`,
`/api/leagues/{sport}`) so the card never leads the page:

* **The same admission as the card pair, then narrower.** Served `live`, a
  supported sport, and every row the filter kept confirmed at or after
  `commence_time`: the gate above, unchanged. On top of that, the start must be
  one a schedule published and not a placeholder (#11296's `pregame_boundary`).
  A market close or ticker date in `commence_time` (gotcha #14) could otherwise
  pass a pregame reading off as in-play.
* **A pair is one book's pair.** Of the rows the card consensus reads (reversed
  books already out), only those whose projected pair solves their own spread
  and total and does not crown their own moneyline underdog contribute
  (#11296's `_own_pair`). The object's pair is the mean over exactly those
  rows, and so are its count and both stamps. No input outside that set reaches
  it.
* **Stamps from the rows.** `earliest_confirmed_at` is the oldest effective
  time (`valid_until`, else `captured_at`) among the contributors, and it is
  never before `boundary_at`. `latest_captured_at` is their newest `captured_at`.
* **Soccer is regulation only.** Its lines settle on 90 minutes, so the object is
  served only while the stored `period` says regulation is being played: a half,
  halftime, or a minute up to 90 (stoppage only after 45 or 90). Extra time,
  penalties, a missing period and any spelling not on that list are withheld.
  `soccer_regulation_in_play` is the rule.

Nothing here is a new read or a new formula: the four routes hand in the rows
they already hold.
"""

from __future__ import annotations

import logging
import math
import re
from collections import defaultdict
from datetime import datetime
from typing import Any, Iterable, Optional

from sqlalchemy import text

from app.utils.odds_filtering import _effective_time, filter_stale_bookmaker_snapshots
from app.utils.odds_math import aggregate_bookmaker_odds, detect_reversed_bookmakers
from app.utils.pregame_projection import (
    BASIS_CONSENSUS_SPREAD_TOTAL,
    SOURCE_SPORTSBOOKS,
    _loaded,
    _own_pair,
    _utc,
    pregame_boundary,
    projection_format,
)

logger = logging.getLogger(__name__)

#: Served statuses a card may carry a projected pair on.
CARD_PROJECTION_STATUSES = frozenset({"scheduled", "live"})

#: #2920 — the marked in-play pair's key inside `current_odds`, and its labels.
LIVE_PROJECTION_KEY = "live_projection"
KIND_IN_PLAY = "in_play"
BOUNDARY_COMMENCE_TIME = "commence_time"

#: The keys this module adds to a card's `current_odds`. Additive only.
CARD_PROJECTION_KEYS = (
    "projected_home_score",
    "projected_away_score",
    "projection_captured_at",
    LIVE_PROJECTION_KEY,
)

#: Soccer `period` values that name a phase of regulation outright. Written by
#: ESPN's `status.type.detail` (`Halftime`) and StatPal's live status (`HT`);
#: compared lower-cased and exact.
_SOCCER_REGULATION_PHASES = frozenset(
    {"1st half", "2nd half", "first half", "second half", "1h", "2h",
     "ht", "halftime", "half time", "half-time"}
)
#: A match minute with optional stoppage: ESPN `67'` / `90'+3'`, StatPal `67` /
#: `90+3` (`StatPalAPI._SOCCER_MINUTE`).
_SOCCER_MINUTE = re.compile(r"^(\d{1,3})'?(?:\s*\+\s*(\d{1,2})'?)?$")

#: Sport-key prefixes whose sportsbook pair is a final score in the scoreboard's
#: unit. UX's exact table (`frontend/lib/projectedFinalPair.ts`
#: `PROJECTED_FINAL_FORMATS`); everything else, undeclared keys included, is no.
CARD_PROJECTION_SPORT_PREFIXES = ("americanfootball_", "basketball_", "soccer_")

#: The pair read's own server-side bound (`statement_timeout`). A ceiling, not a
#: target: no plan or timing exists at hundreds of ids, and a read that hits it
#: serves the cards with no pair.
CARD_PROJECTION_READ_CAP_MS = 1500
#: Kept back from the request budget that remains, so the statement's cancel and
#: the savepoint rollback finish before the events-stage deadline would fire.
CARD_PROJECTION_DEADLINE_MARGIN_MS = 500
#: Below this, the read is not started at all.
CARD_PROJECTION_MIN_READ_MS = 50


def card_projection_wanted(
    served_status: Optional[str], sport_key: Optional[str]
) -> bool:
    """True when a card in this state and sport could carry a pair at all.

    Decides which ids are read, so a finished game or a sport whose pair is not
    a final score costs nothing.
    """
    return (
        served_status in CARD_PROJECTION_STATUSES
        and isinstance(sport_key, str)
        and sport_key.startswith(CARD_PROJECTION_SPORT_PREFIXES)
    )


def soccer_regulation_in_play(period: Optional[str]) -> bool:
    """True only when ``period`` positively says regulation is being played.

    A half, halftime, a minute from 0 to 90, or stoppage after 45 or 90. A
    minute past 90 with no stoppage mark is extra time. Anything unlisted,
    including an empty period, is False: a soccer pair settles on 90 minutes.
    """
    text = str(period or "").strip().lower()
    if text in _SOCCER_REGULATION_PHASES:
        return True
    match = _SOCCER_MINUTE.match(text)
    if match is None:
        return False
    minute = int(match.group(1))
    if match.group(2) is not None:
        return minute in (45, 90)
    return minute <= 90


def card_projection_card(
    event: Any, *, served_status: Optional[str], sport_key: Optional[str]
) -> dict:
    """The inputs one card's pair is decided on, read from its row before any read.

    ``live_boundary_at`` is the row's start when a schedule published it and it
    is not a placeholder (`pregame_boundary`), else None. ``period`` is the
    stored phase. Both read already-loaded state only (gotcha #42).
    """
    boundary_at, _reason = pregame_boundary(event)
    return {
        "id": event.id,
        "stored_status": event.status,
        "served_status": served_status,
        "commence_time": event.commence_time,
        "sport_key": sport_key,
        "live_boundary_at": boundary_at,
        "period": _loaded(event, "period"),
    }


def card_projection_read_timeout_ms(remaining_s: Optional[float]) -> int:
    """The pair read's `statement_timeout` in whole ms, or 0 for "do not read".

    ``remaining_s`` is the request budget left (None when the caller has no
    request budget, e.g. the price refresh): the bound is the cap, or what is
    left less the margin when that is smaller.
    """
    bound = CARD_PROJECTION_READ_CAP_MS
    if remaining_s is not None:
        bound = min(bound, int(remaining_s * 1000) - CARD_PROJECTION_DEADLINE_MARGIN_MS)
    return bound if bound >= CARD_PROJECTION_MIN_READ_MS else 0


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
    live_boundary_at: Optional[datetime] = None,
    period: Optional[str] = None,
) -> Optional[dict]:
    """The card's projected pair from one event's latest row per sportsbook, or None.

    ``snapshots`` is exactly what `latest_odds_per_bookmaker_query` returns for
    the event. ``stored_status`` drives the stale filter, as on detail;
    ``served_status`` is the status the card prints and decides admission.
    ``live_boundary_at`` and ``period`` (`card_projection_card`) decide the
    marked in-play object on a live card; without them it is not served.
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

    pair = {
        "projected_home_score": home,
        "projected_away_score": away,
        "projection_captured_at": max(s.captured_at for s in filtered).isoformat(),
    }
    if served_status == "live":
        live = _live_projection(
            agg_snapshots,
            commence_time=commence_time,
            boundary_at=live_boundary_at,
            sport_key=sport_key,
            period=period,
        )
        if live is not None:
            pair[LIVE_PROJECTION_KEY] = live
    return pair


def _live_projection(
    agg_snapshots: list,
    *,
    commence_time: datetime,
    boundary_at: Optional[datetime],
    sport_key: Optional[str],
    period: Optional[str],
) -> Optional[dict]:
    """The marked in-play object over the card consensus's own rows, or None.

    Called only once the live gate has passed: every row in ``agg_snapshots``
    was confirmed at or after ``commence_time``.
    """
    fmt = projection_format(sport_key)
    boundary = _utc(boundary_at)
    if fmt is None or boundary is None or boundary != _utc(commence_time):
        return None
    unit, basis_period = fmt
    if basis_period == "regulation" and not soccer_regulation_in_play(period):
        return None

    contributors = []
    for snap in agg_snapshots:
        own = _own_pair(snap)
        if own is not None:
            contributors.append((snap, own))
    if not contributors:
        return None
    aggregated = aggregate_bookmaker_odds(
        [
            {"projected_home_score": h, "projected_away_score": a}
            for _, (h, a) in contributors
        ]
    )
    home = _score(aggregated.get("projected_home_score"))
    away = _score(aggregated.get("projected_away_score"))
    if home is None or away is None:
        return None
    earliest = min(_utc(_effective_time(s)) for s, _ in contributors)
    if earliest < boundary:
        return None
    return {
        "projected_home_score": home,
        "projected_away_score": away,
        "kind": KIND_IN_PLAY,
        "boundary": BOUNDARY_COMMENCE_TIME,
        "boundary_at": boundary.isoformat(),
        "earliest_confirmed_at": earliest.isoformat(),
        "latest_captured_at": max(_utc(s.captured_at) for s, _ in contributors).isoformat(),
        "source": SOURCE_SPORTSBOOKS,
        "basis": BASIS_CONSENSUS_SPREAD_TOTAL,
        "bookmaker_count": len(contributors),
        "unit": unit,
        "period": basis_period,
    }


def event_live_projection(
    snapshots: list, event: Any, *, served_status: Optional[str], sport_key: Optional[str]
) -> Optional[dict]:
    """The marked in-play object for one event from the rows a route already holds.

    For `/api/events/{id}` and `/api/events/search`, which read each book's
    latest row themselves. The admission is the cards' (`card_projected_pair`),
    so all four routes answer one game the same way.
    """
    card = card_projection_card(event, served_status=served_status, sport_key=sport_key)
    pair = card_projected_pair(
        list(snapshots or ()),
        stored_status=card["stored_status"],
        served_status=served_status,
        commence_time=card["commence_time"],
        sport_key=sport_key,
        live_boundary_at=card["live_boundary_at"],
        period=card["period"],
    )
    return pair.get(LIVE_PROJECTION_KEY) if pair else None


def attach_card_projected_pair(
    current_odds: Optional[dict], pair: Optional[dict]
) -> None:
    """Add ``pair`` to a card's existing ``current_odds``. Mutates in place.

    Only an existing ``current_odds`` gains the keys: a card with no probability
    has no `current_odds` to extend, and creating one here would hand the client
    an object with no probability in it. Existing keys are never overwritten,
    and a None value is no key at all (#2920: detail and search hand in
    ``{LIVE_PROJECTION_KEY: None}`` on every game the object is withheld from).
    """
    if not isinstance(current_odds, dict) or not pair:
        return
    for key in CARD_PROJECTION_KEYS:
        if pair.get(key) is not None and key not in current_odds:
            current_odds[key] = pair[key]


async def read_card_projected_pairs(db: Any, cards: Iterable[dict]) -> dict[int, dict]:
    """``{event_id: pair}`` for the cards that may carry one, in ONE statement.

    Each card is `card_projection_card`'s dict (``live_boundary_at`` and
    ``period`` may be absent: no in-play object then). Cards that `card_projection_wanted` refuses are not read.
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
                live_boundary_at=card.get("live_boundary_at"),
                period=card.get("period"),
            )
        except Exception:  # noqa: BLE001 — gotcha #42: one event, not the page
            logger.exception("card projected pair failed for event %s", event_id)
            continue
        if pair is not None:
            pairs[event_id] = pair
    return pairs


async def read_card_projected_pairs_bounded(
    db: Any, cards: list[dict], *, timeout_ms: int
) -> dict[int, dict]:
    """`read_card_projected_pairs` under its own server-side bound.

    SAVEPOINT → ``SET LOCAL statement_timeout`` → the read → ROLLBACK TO
    SAVEPOINT. The read writes nothing, and rolling the savepoint back (never
    releasing it) reverts the SET LOCAL, so the bound cannot leak into a later
    stage on the same session. A statement that runs out raises
    ``QueryCanceledError`` out of the savepoint; the caller's catch turns it into
    "no pair". Bounding the wait from asyncio instead would cancel the statement
    mid-flight on the request session and bound the wait, not the session.

    No wanted card, or ``timeout_ms`` below the floor, means no round trip at all.
    """
    if timeout_ms < CARD_PROJECTION_MIN_READ_MS or not any(
        card_projection_wanted(c.get("served_status"), c.get("sport_key"))
        for c in cards
    ):
        return {}
    async with db.begin_nested() as savepoint:
        await db.execute(text(f"SET LOCAL statement_timeout = '{int(timeout_ms)}ms'"))
        pairs = await read_card_projected_pairs(db, cards)
        await savepoint.rollback()
    return pairs
