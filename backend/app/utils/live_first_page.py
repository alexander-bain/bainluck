"""A live game reaches the first page of a games-led feed (#2709, Alex P1).

THE FINDING
-----------
On 2026-09-03 the served `/api/feed?mode=sports` pool held **nine live, priced
events** — eight of them US Open matches. Exactly **one** was inside the
twenty-item first paint that `app/sports/page.tsx` requests; the other eight sat
at served slots 48, 49, 102, 103, 104, 110, 111 and 119. Naomi Osaka, Amanda
Anisimova, Madison Keys and Felix Auger-Aliassime were all past slot 100, so a
reader had to paginate six times before "Live Now" named them. Alex saw the same
page a day earlier and reported the harder version: a live rail of five with
**zero** of the six live US Open matches in it.

WHY THE EXISTING MACHINERY DOES NOT COVER IT
--------------------------------------------
Two independent reasons, and neither is a bug in the thing that has it:

1. **`_rank_key` is `(_rank_score, _sort_time)`.** Event scoring gives a live
   US Open match 95 and a finished MLB game 98, so every completed game
   deterministically outranks every live match. `_score_*` sets
   `sort_time = now + 86400` for live rows, which *used* to carry them to the
   top — but #141/Item 1 de-saturated the scores, and `_rank_key`'s own
   docstring records the consequence: recency "now only breaks GENUINE ties".
   Distinct floats never tie, so the live boost has been inert on this path.
   That is a premise that expired, not a line that was ever wrong.

2. **`lead_with_tonights_games` is Discover-only.** `compose_lead` is invoked as
   `compose_lead(items, include_tonights_games=discover_mode)` and the comment
   above it says so in as many words: "only the tonight's-games prefix is
   Discover-mode-only, so Sports mode never invokes it." That was a reasonable
   call — Discover's problem was having no games at all — and this module
   ANSWERS it rather than deleting it: Discover keeps `compose_lead`, and the
   games-led surfaces get a completeness rule of their own.

MEMBERSHIP, NOT POSITION — WHICH IS WHY THIS IS SMALL
------------------------------------------------------
The frontend already renders live first. `groupFeedIntoSections`
(`lib/feedSections.ts`) buckets every item into Live Now / Just Happened /
Upcoming / Top Markets and pushes "live" first, unconditionally, whatever slot
an item arrived in. So the rail was never mis-ordered — the live rows simply were
not on the page to be grouped. This pass therefore fixes MEMBERSHIP of the first
page and touches ordering only incidentally. A hoisted match renders in exactly
the same place it would have if it had ranked there on its own.

PROMOTE, DO NOT UN-DEMOTE — AND NEVER DROP
-------------------------------------------
Same contract as `enforce_first_page_quality_floor`, whose shape this mirrors:
each admitted live row is **SWAPPED** with a non-live card in the window, so the
displaced card keeps its place in the feed further down and the page keeps its
length. No score is touched, nothing is deleted, and the input is returned
unchanged on any error (gotcha #42/#43). #1091 is the standing lesson that
changing a feed cap is how the Sports tab got emptied; this cannot empty
anything, because it removes nothing.

WHY THERE IS A CAP AT ALL
-------------------------
Because the unbounded version has already happened here. `feed.py`'s candidate
comment records 2026-08-21: 2,911 live `esports` rows resolving to ten distinct
matchups took 488 of 500 slots and the feed served one real game, twice. A rule
that says "every live row leads" is that incident waiting for a second sport. The
cap is half the window, so a live flood can take at most half the first page and
the other half still answers every other question the surface exists for.

WHY A PRICE IS REQUIRED
-----------------------
Alex's acceptance criterion is "every event with status **live and a price**".
An unpriced live row renders a card with no number, which is the thing #2710 had
just finished removing from this same page; hoisting one would spend a first-page
slot to put back the defect the previous ship removed. Unpriced live rows keep
their place in the feed and are deliberately out of scope.
"""

from __future__ import annotations

from decimal import Decimal

__all__ = [
    "LIVE_FIRST_PAGE_WINDOW_SHARE",
    "MARQUEE_PIN_KEY",
    "is_hoistable_live_event",
    "live_first_page_budget",
    "hoist_live_events_into_first_page",
]

# The item flag `compose_lead` uses for a calendar-flagged marquee. Mirrored here
# (not imported) only as a name; the two modules must agree, and a test asserts
# they do rather than a comment claiming it.
MARQUEE_PIN_KEY = "_marquee_pin"

# At most this share of the first page may be given to hoisted live games. See
# "WHY THERE IS A CAP AT ALL" — this exists because the unbounded version took
# 488 of 500 slots on 2026-08-21, not because half is a pleasing number.
LIVE_FIRST_PAGE_WINDOW_SHARE = 2  # denominator: window_size // 2


def _finite_probability(value: object) -> bool:
    """Is ``value`` a real, printable probability?

    ``bool`` is excluded deliberately: it is an ``int`` subclass, so a bare
    ``isinstance(x, (int, float))`` admits ``True`` as the number 1.

    ``Decimal`` is admitted deliberately too. Event probabilities reach Python
    from ``Numeric`` columns as ``decimal.Decimal``, and ``Decimal`` is NOT an
    instance of ``float`` — nor of ``numbers.Real``. That seam has now bitten
    this codebase twice (#2554, and UX-P276's first draft of the props-strip
    predicate, which would have emptied the strip on every request), so the
    admission is spelled out here instead of being inferred from a type
    annotation.
    """
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return value == value and value not in (float("inf"), float("-inf"))
    if isinstance(value, Decimal):
        return value.is_finite()
    return False


def is_hoistable_live_event(item: dict) -> bool:
    """A live, priced game — the population Alex's acceptance criterion names.

    Deliberately strict, and every rejection is a no-op: a row this refuses
    keeps exactly the place the ranker already gave it.
    """
    if not isinstance(item, dict) or item.get("type") != "event":
        return False

    data = item.get("data")
    if not isinstance(data, dict):
        return False

    # `suspended` is rejected HERE, explicitly, for the same reason
    # `tonights_games._is_eligible` rejects it: a rain-delayed match is not a
    # game that is on right now, however true its card is. It also is not what
    # the "Live Now" header claims — `liveSectionTitle` renames the whole
    # section "Live & Paused" the moment one is present, so hoisting one would
    # change the header for every other reader of that rail.
    if (data.get("status") or "").strip().lower() != "live":
        return False

    odds = data.get("current_odds")
    if not isinstance(odds, dict):
        return False
    return _finite_probability(odds.get("home_probability")) or _finite_probability(
        odds.get("away_probability")
    )


def live_first_page_budget(window_size: int) -> int:
    """How many live rows the first page may hold in total.

    A ceiling on the POPULATION in the window, not on the number of swaps: a
    page that already holds its full share of live games needs no hoist, and
    this returns the same number either way.
    """
    if window_size <= 0:
        return 0
    return max(1, window_size // LIVE_FIRST_PAGE_WINDOW_SHARE)


def hoist_live_events_into_first_page(
    items: list[dict],
    *,
    first_page_size: int = 20,
    max_live: int | None = None,
) -> tuple[list[dict], dict]:
    """Swap buried live games into the first page. Pure, stable, length-preserving.

    Returns ``(items, meta)``. ``meta`` reports the shortfall loudly (gotcha #53,
    "no silent caps"): a page that could not fit every live game must not report
    the same thing as one that did.
    """
    empty_meta = {
        "live_in_window_before": 0,
        "live_available_beyond": 0,
        "hoisted": 0,
        "live_in_window_after": 0,
        "unhoisted": 0,
        "budget": 0,
    }
    try:
        window_size = min(first_page_size, len(items))
        if window_size <= 0:
            return items, empty_meta

        window = items[:window_size]
        tail = items[window_size:]

        live_in_window = [i for i, it in enumerate(window) if is_hoistable_live_event(it)]
        live_in_tail = [i for i, it in enumerate(tail) if is_hoistable_live_event(it)]

        budget = live_first_page_budget(window_size) if max_live is None else max_live
        meta = {
            "live_in_window_before": len(live_in_window),
            "live_available_beyond": len(live_in_tail),
            "hoisted": 0,
            "live_in_window_after": len(live_in_window),
            "unhoisted": len(live_in_tail),
            "budget": budget,
        }
        if not live_in_tail:
            return items, meta

        room = budget - len(live_in_window)
        if room <= 0:
            return items, meta

        # Displaceable window slots, WORST FIRST — which is also the editorially
        # correct choice, since the tail of the window is the weakest card on the
        # page.
        #
        # TWO mechanisms guard `compose_lead`'s prefix (C185) and they cover
        # DIFFERENT cases, which was measured rather than assumed. Walking
        # backwards protects a pin at index 0 on its own: with the
        # `MARQUEE_PIN_KEY` skip deleted the suite still passed 33/33. The skip
        # is what protects a pin placed anywhere else — a back-first walk reaches
        # the LAST slot first, so a pin sitting there would be the first thing
        # swapped out. Both cases now have a named control, and deleting either
        # mechanism turns one of them red.
        displaceable = [
            i
            for i in range(window_size - 1, -1, -1)
            if not is_hoistable_live_event(window[i]) and not window[i].get(MARQUEE_PIN_KEY)
        ]

        swaps = min(room, len(live_in_tail), len(displaceable))
        if swaps <= 0:
            return items, meta

        new_window = list(window)
        new_tail = list(tail)
        # Best available live row (the tail is already in served order, so
        # "first" IS "best") pairs with the worst displaceable window slot.
        for pair in range(swaps):
            w_idx = displaceable[pair]
            t_idx = live_in_tail[pair]
            new_window[w_idx], new_tail[t_idx] = new_tail[t_idx], new_window[w_idx]

        meta["hoisted"] = swaps
        meta["live_in_window_after"] = len(live_in_window) + swaps
        meta["unhoisted"] = len(live_in_tail) - swaps
        return new_window + new_tail, meta
    except Exception:  # pragma: no cover - defensive, mirrors lead_with_tonights_games
        return items, empty_meta
