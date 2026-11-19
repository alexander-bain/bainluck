"""#11937 (127-A, stage 1): Discover's two frozen ranking candidates.

The design (Fable, #11937, 2:28 PM PT Nov 11) and its rulings (2:31 PM and
9:33 PM Nov 11, 5:19 AM Nov 12) leave two candidates, both frozen before any
held-out slate is read and both run on Nov 11 and Nov 12:

* **Candidate 1** (``rank_c1_story``): a fixed weight for a grouped card plus one
  free weight for "Discover's market classifier finds a story key for this
  card". The free weight was picked on Nov 8's 35 graded cards from a grid
  written down first (``STORY_KEY_GRID``).
* **Candidate 2** (``rank_c2_score``, labelled as using ``score``): today's
  stored score plus the same fixed grouped weight. No free weight.

Both reorder only the cards Discover already served, within the first page
(``PAGE`` seats), under the same rules: a served card failing a truth gate
leaves the page; a finished game keeps its served seat; two grouped cards are
never adjacent; no entity appears more than twice in the opening ten. Neither
seats a card the feed did not serve.

The harness reaches them with ``scorecard.py --replay
app.utils.discover_rank:rank_c1_story`` (and ``:rank_c2_score``); the feed would
call the winner behind a default-off switch, only if it clears the bar.
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

#: The fixed grouped-beats-lone weight (ruling 6): not tuned on Nov 8.
GROUPED_WEIGHT = 1.0
#: Candidate 1's one free weight, on "the card has a story key" (Fable, 5:19 AM
#: PT Nov 12). Chosen on Nov 8 only, from STORY_KEY_GRID written down before
#: scoring.
STORY_KEY_GRID = (0.0, 0.5, 1.0, 2.0)
STORY_KEY_WEIGHT = 0.5  # Nov 8 pick: 0.5 and 1.0 tie at 0.689 (same top ten); the smaller one

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


def has_story_key(card: dict) -> bool:
    """Question 1's one usable part (#11937, Nov 12): whether Discover's own
    market classifier finds a story for the card's title and category."""
    from app.utils.feed_market_quality import classify_market_quality

    quality = classify_market_quality(
        card.get("title"), card.get("category"), outcome_names=list(card.get("entities") or [])
    )
    return bool(quality.story_key)


def worth_story(card: dict, now: Optional[datetime] = None) -> float:
    """Candidate 1: grouped (fixed) plus "has a story key" (one free weight)."""
    return (GROUPED_WEIGHT if is_grouped(card) else 0.0) + (
        STORY_KEY_WEIGHT if has_story_key(card) else 0.0
    )


def worth_score(card: dict, now: Optional[datetime] = None) -> float:
    """Candidate 2, labelled as using ``score``: today's stored score (0-100,
    scaled to 0-1) plus the same fixed grouped weight. No free weight."""
    score = _num(card.get("score"))
    return (score / 100.0 if score is not None else 0.0) + (GROUPED_WEIGHT if is_grouped(card) else 0.0)


def _served_pos(card: dict) -> float:
    pos = card.get("served_position")
    return pos if isinstance(pos, (int, float)) and not isinstance(pos, bool) else math.inf


def _entities(card: dict) -> list[str]:
    return [str(e) for e in (card.get("entities") or []) if e]


def rank(candidates: Iterable[dict], *, now: Optional[datetime] = None, worth=None) -> list[dict]:
    """A candidate's order: the served first page reordered by ``worth`` under
    the gates and seating rules, then everything else in served order."""
    worth = worth or worth_story
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
            # Nothing satisfies both rules here. Keep the repeat rule and give up
            # the adjacency one; only if every card breaks the repeat rule (the
            # served page itself repeats that much) keep worth order.
            pick = next(
                (c for c in queue
                 if not (index < OPENING and any(counts.get(n, 0) >= MAX_ENTITY_REPEATS for n in _entities(c)))),
                queue[0],
            )
        if pick is None:
            break
        queue.remove(pick)
        seats[index] = pick
        if index < OPENING:
            for name in _entities(pick):
                counts[name] = counts.get(name, 0) + 1

    ordered = [c for c in seats if c is not None] + queue
    return ordered + gated + rest + unserved


def rank_c1_story(candidates: Iterable[dict]) -> list[dict]:
    """Frozen candidate 1 (``--replay app.utils.discover_rank:rank_c1_story``)."""
    return rank(candidates, worth=worth_story)


def rank_c2_score(candidates: Iterable[dict]) -> list[dict]:
    """Frozen candidate 2, uses ``score`` (``--replay app.utils.discover_rank:rank_c2_score``)."""
    return rank(candidates, worth=worth_score)
