"""One story does not get nine cards on the Sports first page (#3511).

THE FINDING
-----------
On 2026-09-07 04:40Z, ``GET /api/feed?limit=20&mode=sports`` served **ten
finished games in twenty slots**, and nine of the ten carried the *same*
headline — ``Recent upset`` — over near-identical reason copy: "Won as 33%
underdog", "Won as 17% underdog", "Won as 32% underdog", "Won as 54% underdog",
and five more. The tenth was ``Line moving``. A reader scrolling the Sports page
at 9:40pm PT did not see ten results; they saw one sentence printed nine times.

WHAT THIS IS *NOT* — MEASURED BEFORE IT WAS BUILT
--------------------------------------------------
Three plausible causes were checked against production and all three are
innocent, which is why this pass is a reorder and not a filter:

1. **Not the cache.** The payload carried ``built_at`` 48s old against a 30s
   TTL, and every one of the ten rows had a real ``completed_at`` between 2.2h
   and 15.6h in the past. Nothing was serving a pre-final snapshot.

2. **Not a rail that fails to flush.** All ten sat legitimately inside the
   24h finished window, and nine of the ten were already past
   ``COMPLETED_DECAY_HOURS``, i.e. carrying the full ``COMPLETED_MAX_DECAY``
   demotion #3484 shipped. The decay worked; it simply lost to an empty slate.

3. **Not a hoist that missed a live game.** The served pool held exactly ONE
   priced live event and it was at slot 2. A second live row sat at slot 43 with
   ``current_odds: null`` and ``is_hoistable_live_event`` refused it *by
   design* (see ``live_first_page``'s "WHY A PRICE IS REQUIRED").

The count itself is mostly a thin-slate fact. The DB window held 86 live and 103
scheduled rows, but the overnight slate was Challenger tennis: the ``min_score``
gate in ``_score_events`` correctly rejected it, so the served pool was 51
finished / 2 live / 1 scheduled out of 91 items. Decaying finished games harder
would push them under that same gate and EMPTY the surface — #1091 exactly.

SO THE DEFECT IS REPETITION, NOT RECENCY — AND DISCOVER ALREADY FIXED IT
-------------------------------------------------------------------------
``diversify_discover_first_page`` caps repeated archetypes at 3 per first page
(``_DISCOVER_FIRST_PAGE_ARCHETYPE_CAPS``). It is invoked under ``if
discover_mode:`` and nowhere else, so the Sports first page — the one surface
whose cards are *all* ``sports_story`` and therefore all one archetype — has
never had a repeat-rail cap of any kind. This module gives it one, scoped so it
cannot cost the surface a single game.

SCOPED TO FINISHED CARDS, DELIBERATELY
---------------------------------------
The cap counts only ``completed``/``closed`` events. Capping on headline alone
would count ``Live`` — every live game shares that label — and would push live
rows off the page to satisfy a diversity rule, which is precisely the defect
#2709 shipped ``hoist_live_events_into_first_page`` to end. A live or upcoming
game is never counted, never displaced, and never blocked by this pass.

SWAP, NEVER DROP
----------------
Same contract as ``hoist_live_events_into_first_page`` and
``enforce_first_page_quality_floor``, whose shape this mirrors: a surplus
finished card is **swapped** with the best admissible card beyond the window, so
the displaced card keeps its place further down and the page keeps its length.
No score is touched, nothing is deleted, and the input list is returned
unchanged on any error (gotcha #42/#43). If the pool beyond the window has
nothing to trade, the page is returned exactly as it arrived — a thin slate
keeps its ninth upset rather than losing a slot, because a shorter page is not
an improvement on a repetitive one.

WHY THREE
---------
Three is ``_DISCOVER_FIRST_PAGE_ARCHETYPE_CAPS``' own default and its
``sports_story`` value. Three cards still tell the reader plainly that the night
was full of upsets; the fourth through ninth only tell them again. It is a
sibling of an existing constant rather than a new opinion about the page.

ORDER: THIS RUNS BEFORE THE LIVE HOIST
---------------------------------------
``hoist_live_events_into_first_page`` is Alex's P1 acceptance criterion and must
have the last word on first-page membership. It displaces the *worst* window
slots and swaps in live games, so running it after this pass can only improve on
what this pass leaves; running it before would let this pass trade a hoisted
live game away. A test asserts the call order rather than a comment claiming it.
"""

from __future__ import annotations

__all__ = [
    "FINISHED_RAIL_FIRST_PAGE_CAP",
    "FINISHED_STATUSES",
    "finished_rail_key",
    "cap_repeated_finished_rails",
]

#: Statuses this pass counts as a finished game. ``suspended`` is absent on
#: purpose: it is not a result, it renders a different card, and live/048 put it
#: in the candidate pool precisely so a paused match keeps a place on the page.
FINISHED_STATUSES = ("completed", "closed")

#: At most this many finished cards may share one rail on the first page. See
#: "WHY THREE" — this is ``_DISCOVER_FIRST_PAGE_ARCHETYPE_CAPS["sports_story"]``
#: by descent, not an independent guess.
FINISHED_RAIL_FIRST_PAGE_CAP = 3


def finished_rail_key(item: dict) -> str | None:
    """The rail a finished game's card sits on, or ``None`` if it is not one.

    The key is the ``headline`` — the string the reader actually sees repeated
    ("Recent upset", "Line moving"). It is deliberately NOT the internal reason
    code: two cards can reach one headline by different codes, and the reader
    counting repetitions is counting headlines.

    Every ``None`` here is a no-op: a row this refuses keeps exactly the place
    the ranker already gave it.
    """
    if not isinstance(item, dict) or item.get("type") != "event":
        return None

    data = item.get("data")
    if not isinstance(data, dict):
        return None

    if (data.get("status") or "").strip().lower() not in FINISHED_STATUSES:
        return None

    headline = item.get("headline")
    if not isinstance(headline, str):
        return None
    headline = headline.strip()
    # An unlabelled finished card is not a rail. Counting every headline-less
    # result as one shared bucket would cap cards that repeat nothing — the
    # served page carried eight of them and they are all different games.
    return headline or None


def cap_repeated_finished_rails(
    items: list[dict],
    *,
    first_page_size: int = 20,
    max_per_rail: int = FINISHED_RAIL_FIRST_PAGE_CAP,
) -> tuple[list[dict], dict]:
    """Swap surplus same-rail finished cards off the first page.

    Pure, stable and length-preserving. Returns ``(items, meta)``; ``meta``
    reports an unmet cap loudly (gotcha #53, no silent caps) so a page that kept
    a repeat because the pool had nothing to trade does not read the same as a
    page that had no repeats at all.
    """
    empty_meta = {
        "over_cap_before": 0,
        "replacements_available": 0,
        "swapped": 0,
        "over_cap_after": 0,
        "unswapped": 0,
        "cap": max_per_rail,
    }
    try:
        window_size = min(first_page_size, len(items))
        if window_size <= 0 or max_per_rail < 0:
            return items, empty_meta

        window = items[:window_size]
        tail = items[window_size:]

        # Walk the window in served order so the cards KEPT are the best-ranked
        # of their rail; the surplus is always the weakest N of a repeat group.
        seen: dict[str, int] = {}
        over_cap: list[int] = []
        for i, it in enumerate(window):
            rail = finished_rail_key(it)
            if rail is None:
                continue
            seen[rail] = seen.get(rail, 0) + 1
            if seen[rail] > max_per_rail:
                over_cap.append(i)

        meta = dict(empty_meta)
        meta["over_cap_before"] = len(over_cap)
        meta["over_cap_after"] = len(over_cap)
        meta["unswapped"] = len(over_cap)
        if not over_cap:
            return items, meta

        # A replacement must not recreate the problem it is fixing. A tail card
        # is admissible when it is not itself a finished card on a rail that is
        # already at its cap — counted against the SAME running tally the window
        # walk built, and updated as replacements are admitted, so trading six
        # "Recent upset" cards for six more is impossible.
        kept_counts = {rail: min(n, max_per_rail) for rail, n in seen.items()}
        replacements: list[int] = []
        for t_idx, it in enumerate(tail):
            if len(replacements) >= len(over_cap):
                break
            rail = finished_rail_key(it)
            if rail is not None:
                if kept_counts.get(rail, 0) >= max_per_rail:
                    continue
                kept_counts[rail] = kept_counts.get(rail, 0) + 1
            replacements.append(t_idx)

        meta["replacements_available"] = len(replacements)
        swaps = min(len(over_cap), len(replacements))
        if swaps <= 0:
            return items, meta

        new_window = list(window)
        new_tail = list(tail)
        # Worst surplus card pairs with the best available replacement: walk the
        # over-cap list from the BACK (weakest slot first) and the tail from the
        # front (the tail is already in served order, so "first" IS "best").
        for pair in range(swaps):
            w_idx = over_cap[len(over_cap) - 1 - pair]
            t_idx = replacements[pair]
            new_window[w_idx], new_tail[t_idx] = new_tail[t_idx], new_window[w_idx]

        meta["swapped"] = swaps
        meta["over_cap_after"] = len(over_cap) - swaps
        meta["unswapped"] = len(over_cap) - swaps
        return new_window + new_tail, meta
    except Exception:  # pragma: no cover - defensive, mirrors live_first_page
        return items, empty_meta
