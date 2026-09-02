"""Which feed items belong under a "Live Now" heading.

UX-1035 / #2709. A section heading with a count beside it is a claim about
everything under it (the rule ruling 027 and UX-P210 both turn on). ``/sports``
renders "Live Now · N" from whatever LIVE items happen to fall inside the
score-ranked FIRST PAGE, so the number is really "live items in the top 20",
printed as if it were "live". Measured on production 2026-09-02 22:5xZ with the
banked payload ``artifacts-ux-1035/BEFORE-sports-feed-full-2026-09-02.json``:
the ranked ``mode=sports`` list held **14** live items, **6** of them inside the
first 20. Nine live US Open matches were in play and exactly one — Wang vs
Kalinskaya at rank 16 — was above the cut, so the rail said five and showed no
tennis while six courts were mid-match.

The fix is a PROJECTION, not a bigger page: ``GET /api/feed?live_only=true``
returns the live slice of the same ranked list, so the rail can be sourced from
all of it while the main list keeps its bounded 20-item first paint (L2-240 /
LAT-P171). This module is the single predicate both halves agree on.

🔴 THIS MIRRORS ``groupFeedIntoSections`` IN ``frontend/lib/feedSections.ts``
AND MUST KEEP MIRRORING IT. The frontend still sections the merged pool itself,
so an item this predicate admits but the sectioner routes elsewhere lands under
"Upcoming" instead of vanishing — visibly wrong rather than silently missing,
which is the failure mode we want. ``test_feed_live_section.py`` pins the two
against each other on the banked payload.
"""

from typing import Any

# Item types that are markets, not matches. The frontend sectioner routes both
# to "Top Markets" unconditionally — a futures card has no phase of its own, and
# reading one off its price is the doctrine violation #2711 is about — so a
# liveness predicate must refuse them BY TYPE, before it ever looks at `status`.
_NON_EVENT_TYPES = frozenset({"futures", "bundle"})


def feed_item_is_live(item: Any) -> bool:
    """Is this feed item one the "Live Now" rail is a promise about?

    Pure: no clock, no I/O. The phase comes off the payload the build already
    computed, never off a comparison against "now" — gotcha #44's rule, and the
    reason this can be tested against a banked payload months after its games
    ended.

    ``tournament`` items carry ``schedule_status`` rather than ``status``;
    everything else (``event``, ``concept``) carries ``status``. Anything whose
    shape this cannot read is NOT live: an unreadable phase is an unproven one,
    and over-claiming is the bug being fixed.
    """
    if not isinstance(item, dict):
        return False
    if item.get("type") in _NON_EVENT_TYPES:
        return False
    data = item.get("data")
    if not isinstance(data, dict):
        return False
    if data.get("schedule_status") == "in-progress":
        return True
    return data.get("status") == "live"


def filter_live_items(items: Any) -> list:
    """The live sub-list of a ranked feed list, in the order it arrived.

    Order is preserved rather than re-sorted: the ranking is the build's, and a
    projection that re-ranks is a second opinion about score that nothing asked
    for.
    """
    if not isinstance(items, list):
        return []
    return [item for item in items if feed_item_is_live(item)]
