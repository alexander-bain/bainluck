"""Last night's marquee final gets a seat on page one — #5100, the placement half of #4681.

#4681 shipped the ADMISSION half: `_recent_marquee_final_ids` picks at most
`_DISCOVER_RECENT_FINAL_SLOTS` finished marquee games, the noise filter stops
deleting them and the demotion stops capping them to 35. Measured on production
2026-09-11 10:26Z, that half works and is not enough:

    pos 133 of 135   RC Lens @ Slavia Praha (UCL, tier:1)   display 42
    pos 134 of 135   Texas Rangers @ Seattle Mariners (MLB)  display 39

Both carried `discover_marquee_final: true`. Both were the LAST TWO CARDS ON THE
DECK. At `FEED_PAGE_LIMIT = 20` the reader meets them on page seven, which is the
same nothing as not selecting them — the lesson `_recent_marquee_final_ids`
already states one layer up ("a card that survives only one of the two is still
not on the page"), recurring one layer deeper.

**The cause is the freshness decay, not the demotion.** `apply_completed_freshness_decay`
(#3484) runs inside `_score_events`, multiplying display AND ordering score by a
factor that ramps from 1.0 at `COMPLETED_FRESH_HOURS = 1.5` to `1 - COMPLETED_MAX_DECAY
= 0.45` at `COMPLETED_DECAY_HOURS = 6.0`. Both specimens were past six hours and sat
exactly at the floor: inverting the served value gives pre-decay displays of ~93 and
~87 — two of the highest-scoring events in the pool, each multiplied down below the
132nd futures card. A game that ends at 03:26Z is 9.6h old at 6am Pacific, so a
morning reader hits the floor by construction. That is precisely the window #5100 is
named for.

**Why this seats rather than un-decays.** Exempting a kept final from the decay
restores ~93 and lands it in the top ten, above every live market — stronger than the
ship asks for. "Findable this morning" is page one, not top billing, and the decay is
load-bearing for every finished game that is NOT one of the two selected. So nothing
here touches a score: this is a pure stable reorder, the same discipline
`compose_lead`'s comment insists on ("PROMOTE, DO NOT UN-DEMOTE").

**Why it is not `compose_lead`.** `tonights_games.compose_lead` deliberately rejects
finished games — "a finished game is not tonight's game, it is a result" — and that
rejection should stand. Reaching page one and leading the deck are different claims,
and this module makes only the first.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


#: The first slot a seated final may take. Positions below this are spoken for:
#: `compose_lead` owns the prefix under C185's contract (`MAX_LEAD = 3`), and
#: clause (d) governs the first `FIRST_PAGE_WHY_NOW_WINDOW = 10` slots, which are
#: the page's "what is happening now" band. A result belongs in page one's back
#: half — present without hunting, not claiming the morning's top story.
#:
#: ITS OWN NUMBER, deliberately equal to `FIRST_PAGE_WHY_NOW_WINDOW` today. The
#: two answer different questions — one screens futures copy, one places a game
#: card — and reading the seat floor off the why-now constant would silently move
#: this ship the next time clause (d)'s window is retuned. This file already
#: carries the sibling discipline in `feed.py` ("Two windows, two numbers, both
#: stated"). `test_the_seat_floor_is_ten_5100` fails if it moves in silence.
DISCOVER_FINAL_SEAT_FLOOR = 10


def seat_marquee_finals(
    items: list[dict],
    kept_final_ids: set[int] | None,
    *,
    first_page_size: int,
    seat_floor: int = DISCOVER_FINAL_SEAT_FLOOR,
) -> tuple[list[dict], dict]:
    """Move any selected marquee final that missed page one onto it.

    Returns ``(items, meta)``. ``meta`` carries ``seated``, ``already_on_page``,
    ``unseated`` and ``seats_available`` so the caller can log a shortfall rather
    than cap in silence (gotcha #53 — "we seated nothing" and "there was nothing
    to seat" are opposite facts).

    A MOVE, NOT AN INSERT. Each seated card is removed from where it ranked and
    re-inserted at the seat, so length and membership are preserved exactly and
    no surface can be emptied (#1091, gotcha #43). The cost is real and intended:
    every card between the seat and the final's old position shifts down one, so
    seating one card pushes the card at slot 19 to slot 20.

    Three cards are deliberately left alone:

    * a final that is NOT in ``kept_final_ids`` — the ordinary Superettan /
      MiLB / Kleague tail stays exactly where it ranked. #4681's acceptance
      criterion 3 is that ordinary finished games are not readmitted, and a
      placement pass that seated them would break it from the other side.
    * a final ALREADY inside ``first_page_size`` — a game that ended inside the
      1.5h fresh window ranks on its own merit, and moving it DOWN to the seat
      floor would be this pass demoting the very card it exists to promote.
    * everything below ``seat_floor`` — the lead prefix is never rewritten here.
      Two passes that both write a prefix cannot be sequenced into the intended
      result; `feed.py` pays for that lesson in `compose_lead`'s own comment, and
      this pass declines to become the second prefix writer.

    Args:
        items: the composed deck, already ordered.
        kept_final_ids: event ids `_recent_marquee_final_ids` chose this request.
            ``None`` or empty means the arm selected nothing and this is a no-op.
        first_page_size: how many cards the reader's first page holds. Passed in
            rather than read from a constant so the caller keeps one authority
            for "page one" (`DISCOVER_COMPOSITION_WINDOW`) — a second copy here
            is exactly the drift #5101 removed from the composition stages.
        seat_floor: the earliest slot a seated final may take.
    """
    meta = {
        "seated": 0,
        "already_on_page": 0,
        "unseated": 0,
        "seats_available": 0,
    }
    if not kept_final_ids or not items:
        return items, meta

    seats_available = min(first_page_size, len(items)) - seat_floor
    meta["seats_available"] = max(0, seats_available)
    if seats_available <= 0:
        # Reachable by configuration, not by data: a seat floor at or past the
        # page size leaves nowhere legal to sit. Loud rather than a silent no-op,
        # because it reads identically to "the arm selected nothing".
        logger.warning(
            "Discover final seating: no legal seat — floor %d is at or past the "
            "first page (%d cards, deck of %d); %d selected final(s) left where "
            "they ranked",
            seat_floor,
            first_page_size,
            len(items),
            len(kept_final_ids),
        )
        meta["unseated"] = len(kept_final_ids)
        return items, meta

    try:
        # `first_page_size` alone, NOT `min(first_page_size, len(items))`. A
        # position is always below the deck length, so the clamp that
        # `seats_available` genuinely needs is provably dead here — a mutation
        # replacing it survived the whole suite, which is what surfaced it.
        # Spelling it as a bound it does not have would invite the next reader
        # to "fix" the asymmetry with the two lines above.
        to_seat: list[dict] = []
        for position, item in enumerate(items):
            if item.get("type") != "event":
                continue
            if (item.get("data") or {}).get("id") not in kept_final_ids:
                continue
            if position < first_page_size:
                meta["already_on_page"] += 1
                continue
            to_seat.append(item)

        if not to_seat:
            return items, meta

        if len(to_seat) > seats_available:
            meta["unseated"] = len(to_seat) - seats_available
            logger.warning(
                "Discover final seating: %d selected final(s) kept off page one "
                "— only %d seat(s) between floor %d and page size %d",
                meta["unseated"],
                seats_available,
                seat_floor,
                first_page_size,
            )
            to_seat = to_seat[:seats_available]

        # Identity, not equality: two distinct cards can compare equal as dicts,
        # and `list.remove` would then drop the wrong one.
        seated_ids = {id(item) for item in to_seat}
        remainder = [item for item in items if id(item) not in seated_ids]
        meta["seated"] = len(to_seat)
        return remainder[:seat_floor] + to_seat + remainder[seat_floor:], meta
    except Exception:
        # One malformed card must never cost the reader the whole deck
        # (gotcha #42). Placement is a nicety; the page is not.
        logger.exception(
            "Discover final seating failed; deck returned in its ranked order"
        )
        return items, {
            "seated": 0,
            "already_on_page": 0,
            "unseated": len(kept_final_ids),
            "seats_available": max(0, seats_available),
        }
