"""#11937 (127-A, stage 1): Discover's card-worth ranker, candidate 1.

The design (Fable, #11937, 2:28 PM PT Nov 11, amended by the 2:31 PM rulings)
asks the same questions of every card and lets each surface weigh the answers.
This module answers them for Discover from the features a slate already stores
(``ranking_eval.card_features``), so the harness's ``--replay`` and, once a
candidate passes, the feed call the same function.

What candidate 1 does, and deliberately does not do:

* It reorders the cards Discover already served, within the first page
  (``PAGE`` seats). It never seats a card the feed did not serve: the feed's own
  gates, suppressed families and caps decided those, and an unserved card is
  usually ungraded, which the held-out score cannot read anyway.
* Gates come first and are never traded for worth: a served card whose truth
  flags fail (settled without its result, stale price, missing blend) leaves the
  page instead of moving down it.
* Standing seating rules hold: a finished game keeps its served seat; two
  grouped cards are never adjacent; no entity appears more than twice in the
  opening ten.
* Question 1 ("how many care") has no stored input yet (tier, stakes and story
  class are not captured), so it carries no weight. ``score`` is never an input.
* "Grouped beats lone" has a fixed weight; it is not tuned on Nov 8, which has
  nothing usable about grouped cards below its opening ten.

Unknown inputs are neutral, never zero: an unknown 24-hour move is not "did not
move".
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

#: Seats candidate 1 may reorder: Discover's first page.
PAGE = 20
#: The opening ten, where the repeat rule applies.
OPENING = 10
#: No entity more than this many times in the opening ten (design section 2).
MAX_ENTITY_REPEATS = 2

#: Grouped card kinds: one card standing for several markets.
GROUPED_TYPES = frozenset({"bundle", "concept", "tournament"})

#: Discover weights, frozen for candidate 1. "form" is the fixed starting weight
#: for grouped-beats-lone (ruling 6) and is not tuned.
WEIGHTS: dict[str, float] = {
    "contest": 1.0,
    "moved": 1.0,
    "timely": 0.5,
    "form": 1.0,
    "support": 0.25,
}

#: A 24-hour move this large (10 points) counts as fully "moved".
MOVE_FULL = 0.10
#: Neutral value for an input the card does not have.
NEUTRAL = 0.5

GATE_FLAGS = ("settled_without_result", "stale", "blend_missing")


def _num(value: Any) -> Optional[float]:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _when(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)


def fails_gate(card: dict) -> bool:
    """A truth-gate failure: known True on any flag. Unknown (None) is not a
    failure here; the harness reports unknowns beside the score (ruling 2)."""
    return any(card.get(flag) is True for flag in GATE_FLAGS)


def is_grouped(card: dict) -> bool:
    return card.get("type") in GROUPED_TYPES


def is_finished_game(card: dict) -> bool:
    return card.get("type") == "event" and card.get("settled") is True


def contest(card: dict) -> float:
    """A real contest: 1.0 at 50%, 0.0 at a certainty. Unknown is neutral."""
    p = _num(card.get("probability"))
    if p is None:
        return NEUTRAL
    return max(0.0, 1.0 - abs(p - 0.5) * 2.0)


def moved(card: dict) -> float:
    m = _num(card.get("movement_24h"))
    if m is None:
        return NEUTRAL
    return min(abs(m) / MOVE_FULL, 1.0)


def timely(card: dict, now: Optional[datetime]) -> float:
    """Live or starting within a day, or resolving within a week: 1.0. A card
    with no clock at all is neutral."""
    start = _when(card.get("start_time"))
    resolve = _when(card.get("resolution_time"))
    if now is None or (start is None and resolve is None):
        return NEUTRAL
    hours = []
    if start is not None:
        hours.append((start - now).total_seconds() / 3600)
    if resolve is not None:
        hours.append((resolve - now).total_seconds() / 3600)
    soonest = min(hours, key=abs)
    if -6 <= soonest <= 24:
        return 1.0
    if 0 < soonest <= 24 * 7:
        return 0.5
    return 0.0


def support(card: dict) -> float:
    count = _num(card.get("source_count"))
    if count is None:
        return NEUTRAL
    spread = _num(card.get("source_spread"))
    base = 1.0 if count >= 2 else 0.5
    return base - (0.5 if spread is not None and spread > 0.10 else 0.0)


def worth(card: dict, now: Optional[datetime] = None) -> float:
    parts = {
        "contest": contest(card),
        "moved": moved(card),
        "timely": timely(card, now),
        "form": 1.0 if is_grouped(card) else 0.0,
        "support": support(card),
    }
    return sum(WEIGHTS[name] * value for name, value in parts.items())


def _served_pos(card: dict) -> float:
    pos = card.get("served_position")
    return pos if isinstance(pos, (int, float)) and not isinstance(pos, bool) else math.inf


def _entities(card: dict) -> list[str]:
    return [str(e) for e in (card.get("entities") or []) if e]


def rank(candidates: Iterable[dict], *, now: Optional[datetime] = None) -> list[dict]:
    """Candidate 1's order: the served first page reordered by worth under the
    gates and seating rules, then everything else in served order."""
    cards = sorted((dict(c) for c in candidates), key=_served_pos)
    if now is None:
        # Replay has no clock: the slate's newest price reading stands in for
        # the capture time, so the same slate always ranks the same way.
        stamps = [t for t in (_when(c.get("price_observed_at")) for c in cards) if t]
        now = max(stamps) if stamps else None
    served = [c for c in cards if _served_pos(c) != math.inf]
    unserved = [c for c in cards if _served_pos(c) == math.inf]

    page = [c for c in served[:PAGE] if not fails_gate(c)]
    gated = [c for c in served[:PAGE] if fails_gate(c)]
    rest = served[PAGE:]

    # Finished games keep their served seat (index within the page).
    fixed = {int(_served_pos(c)) - 1: c for c in page if is_finished_game(c) and _served_pos(c) <= PAGE}
    movable = sorted(
        (c for c in page if not (is_finished_game(c) and _served_pos(c) <= PAGE)),
        key=lambda c: (-worth(c, now), _served_pos(c)),
    )

    seats: list[Optional[dict]] = [None] * len(page)
    for index, card in fixed.items():
        if index < len(seats):
            seats[index] = card
    leftovers = [c for i, c in fixed.items() if i >= len(seats)]
    queue = leftovers + movable

    counts: dict[str, int] = {}
    for index in range(len(seats)):
        if seats[index] is not None:
            if index < OPENING:
                for name in _entities(seats[index]):
                    counts[name] = counts.get(name, 0) + 1
            continue
        previous = seats[index - 1] if index > 0 else None
        following = seats[index + 1] if index + 1 < len(seats) else None
        pick = None
        for card in queue:
            if is_grouped(card) and (
                (previous is not None and is_grouped(previous))
                or (following is not None and is_grouped(following))
            ):
                continue
            if index < OPENING and any(counts.get(n, 0) >= MAX_ENTITY_REPEATS for n in _entities(card)):
                continue
            pick = card
            break
        if pick is None and queue:
            pick = queue[0]  # nothing satisfies the rules: keep worth order
        if pick is None:
            break
        queue.remove(pick)
        seats[index] = pick
        if index < OPENING:
            for name in _entities(pick):
                counts[name] = counts.get(name, 0) + 1

    ordered = [c for c in seats if c is not None] + queue
    return ordered + gated + rest + unserved
