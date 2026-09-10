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

A SECOND PASS LIVES HERE: THE SLOTS THE CLIENT THROWS AWAY (#3836)
-------------------------------------------------------------------
``swap_client_deleted_finished_off_first_page`` is a sibling of the cap above
and shares its rail bookkeeping, which is the whole reason it is in this file
rather than its own: a replacement it admits must not recreate the repetition
the cap has just removed, and the only way to guarantee that is to count rails
against the same key function. See that function's docstring for the finding.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

__all__ = [
    "CLIENT_COMPLETED_MAX_AGE_HOURS",
    "CLIENT_MARQUEE_FINAL_MAX_AGE_HOURS",
    "FINISHED_RAIL_FIRST_PAGE_CAP",
    "FINISHED_STATUSES",
    "FUTURES_FIRST_PAGE_CAP",
    "cap_futures_on_games_led_first_page",
    "client_deletes_finished_card",
    "finished_card_max_age_hours",
    "finished_event_age_anchor",
    "finished_rail_key",
    "cap_repeated_finished_rails",
    "swap_client_deleted_finished_off_first_page",
]

#: The age, in hours since the game ENDED (:func:`finished_event_age_anchor`,
#: #4776), past which the WEB CLIENT deletes a finished game before it paints.
#:
#: THIS IS A MIRROR, NOT A POLICY. The authority is
#: ``frontend/lib/discover/feedFreshness.ts``::
#:
#:     export const COMPLETED_EVENT_MAX_AGE_HOURS = 8;
#:
#: which ``/sports`` applies through ``applyFinishedCardGuard`` and Discover
#: applies directly. Inventing a second threshold here is how the two surfaces
#: start disagreeing about what "old" means, so
#: ``test_client_deletion_mirror_3836.py`` READS that file and fails if the two
#: numbers ever diverge. Change the frontend constant and this one follows, or
#: CI stops you.
CLIENT_COMPLETED_MAX_AGE_HOURS = 8

#: The same age for a card Discover kept as one of its marquee finals (#4681),
#: which the client grants a longer life. D118 = B, Alex, Thu 2026-09-10.
#:
#: ALSO A MIRROR, NOT A POLICY, for the same reason and guarded by the same
#: test. The authority is ``frontend/lib/discover/feedFreshness.ts``::
#:
#:     export const MARQUEE_FINAL_MAX_AGE_HOURS = 14;
#:
#: Eight hours from the whistle retired the NFL season opener at 4:26am Pacific
#: — after #4776 had already moved the clock off the kickoff — so no anchor
#: change could deliver "last night's big game is there with your coffee".
#: Fourteen puts an 8:30pm final on the page at 10:30am.
#:
#: It is a SECOND number rather than a bigger first one because the reader of
#: the ordinary window is ``/sports``' shared guard, which no ruling moved. The
#: two numbers are selected between per card by
#: :func:`finished_card_max_age_hours`, never by which caller is asking.
CLIENT_MARQUEE_FINAL_MAX_AGE_HOURS = 14

#: Statuses this pass counts as a finished game. ``suspended`` is absent on
#: purpose: it is not a result, it renders a different card, and live/048 put it
#: in the candidate pool precisely so a paused match keeps a place on the page.
FINISHED_STATUSES = ("completed", "closed")

#: At most this many finished cards may share one rail on the first page. See
#: "WHY THREE" — this is ``_DISCOVER_FIRST_PAGE_ARCHETYPE_CAPS["sports_story"]``
#: by descent, not an independent guess.
FINISHED_RAIL_FIRST_PAGE_CAP = 3

#: At most this many ``futures`` cards may occupy the Sports first page (#4497).
#: See ``cap_futures_on_games_led_first_page``'s "WHY TWO" — unlike the rail cap
#: above this does NOT descend from an existing constant, and the docstring says
#: so rather than borrowing authority it does not have.
FUTURES_FIRST_PAGE_CAP = 2


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
        # Both lists are walked FRONT to front, and the pairing is index-for-
        # index. `over_cap` is ascending window slots; `replacements` is
        # ascending tail slots, and the tail is already in served order, so its
        # front IS its best. Earliest surplus slot therefore takes the best
        # replacement, and the page keeps descending rank.
        #
        # This used to walk `over_cap` from the BACK, on the reasoning that the
        # weakest slot should get the best card. That inverts the page: with
        # replacements scoring 80, 78, 75 the reader got 75 then 78 then 80
        # going DOWN, each swapped card outranking the one above it. Reading
        # order is the whole point of a ranked page, and the two objectives are
        # not in tension anyway — when there are fewer replacements than
        # surplus cards, fixing the EARLIEST repeats is also what the reader
        # notices, because a fourth "Recent upset" at slot 6 is more obvious
        # than one at slot 19.
        for pair in range(swaps):
            w_idx = over_cap[pair]
            t_idx = replacements[pair]
            new_window[w_idx], new_tail[t_idx] = new_tail[t_idx], new_window[w_idx]

        meta["swapped"] = swaps
        meta["over_cap_after"] = len(over_cap) - swaps
        meta["unswapped"] = len(over_cap) - swaps
        return new_window + new_tail, meta
    except Exception:  # pragma: no cover - defensive, mirrors live_first_page
        return items, empty_meta


def _commence_age_hours(value, *, now: datetime) -> float | None:
    """Hours since ``value``, or ``None`` if it cannot be read as a time.

    ``None`` is the client's answer too, and deliberately so. In JavaScript a
    missing or unparseable ``commence_time`` makes ``hoursAgo`` NaN, and
    ``NaN > 8`` is ``false`` — the card is KEPT. So an unreadable timestamp must
    mean "the client will render this", never "assume it is old and trade it
    away". Getting this backwards would swap out cards that are about to appear.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    # A naive stamp is UTC everywhere else in this payload; reading it as local
    # time would shift the age by the host's offset and make the answer depend
    # on which machine served the request.
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return (now - parsed).total_seconds() / 3600.0


def finished_event_age_anchor(data: dict) -> object:
    """The stamp a finished card's age is measured from — ``ed.ended_at ||
    ed.commence_time`` in ``feedFreshness.ts``'s ``finishedEventAgeAnchor``.

    THE PREFERENCE IS ONLY EVER SAFE IN ONE DIRECTION, and that is why it is a
    named function rather than an inline ``or``. A game ends after it starts, so
    ``ended_at`` is never older than ``commence_time`` and ageing on it can only
    ever KEEP a card the old rule deleted — it cannot newly delete one. The
    expensive error this whole module guards against (trading away a slot for a
    card the browser was going to paint) is therefore unreachable through this
    change, which is what let it go in without re-deriving #3836's swap pass.

    ``ended_at`` is preferred only when it is a NON-EMPTY STRING. JavaScript's
    ``||`` and Python's ``or`` agree on ``None``, ``""`` and a missing key, and
    disagree on the shapes that cannot occur in this payload (``[]`` is falsy in
    Python and truthy in JS); pinning the type here makes the two sides agree on
    the malformed cases too, and lands the disagreement on the KEEP side either
    way, since a garbage stamp reads as an unreadable age and an unreadable age
    is rendered.
    """
    if not isinstance(data, dict):
        return None
    ended_at = data.get("ended_at")
    if isinstance(ended_at, str) and ended_at.strip():
        return ended_at
    return data.get("commence_time")


def finished_card_max_age_hours(data: dict) -> float:
    """The window THIS finished card gets — the mirror of
    ``finishedEventMaxAgeHours`` in ``feedFreshness.ts``.

    ``discover_marquee_final is True`` and nothing looser. The flag is stamped
    ``False`` as well as ``True``, and it is absent entirely from a ``/sports``
    payload and from any Discover payload cached before D118 shipped, so three
    distinct states reach here and only one of them is evidence. Truthiness
    would fold the other two into the long window and keep dead cards on the
    page; an identity test on ``True`` is what makes an unstamped payload behave
    exactly as it did yesterday.
    """
    if not isinstance(data, dict):
        return float(CLIENT_COMPLETED_MAX_AGE_HOURS)
    if data.get("discover_marquee_final") is True:
        return float(CLIENT_MARQUEE_FINAL_MAX_AGE_HOURS)
    return float(CLIENT_COMPLETED_MAX_AGE_HOURS)


def client_deletes_finished_card(
    item: dict, *, now: datetime | None = None, max_age_hours: float | None = None
) -> bool:
    """True when the web client will delete this card before it paints.

    A line-for-line mirror of ``isStale``'s event arm in
    ``frontend/lib/discover/feedFreshness.ts``::

        if (ed.status === "completed" || ed.status === "closed") {
          const anchor = finishedEventAgeAnchor(ed);   // ed.ended_at || ed.commence_time
          const hoursAgo =
            (Date.now() - new Date(anchor).getTime()) / (1000*60*60);
          if (hoursAgo > COMPLETED_EVENT_MAX_AGE_HOURS) return true;
        }

    Two details in that snippet are load-bearing and are easy to get wrong:

    * **The clock starts at the whistle, not the kickoff** (#4776). It ages on
      ``ended_at`` and falls back to ``commence_time``. This was
      ``commence_time`` alone until 2026-09-10, on the stated grounds that
      ``completed_at`` "is ``None`` in the served payload" — true of
      ``completed_at``, and the payload carries the same fact under D109's
      ``ended_at`` on 39 of 39 finished rows. Charging a finished card for its
      own duration cost it a measured median 2.26h of an eight-hour life (MLB
      2.78h, NFL 3.11h), which is why the NFL season opener left Discover at
      1:20AM PT and #4681's marquee arm has never had a morning it could fire
      on. ``ended_at`` is OPTIONAL by D109's rule — absent on unsettled rows,
      and a cached payload can predate it — so the fallback is not defensive
      dressing, it is the contract.
    * The comparison is strict ``>``. A card at exactly the threshold is
      RENDERED, so this function must not use ``>=``.

    ``max_age_hours`` overrides the window for the ONE caller that must ask
    before the answer exists: ``_recent_marquee_final_ids`` is what decides
    whether a card is a marquee final, so it cannot read the flag that records
    that decision (#4681 + D118). Every other caller leaves it ``None`` and gets
    :func:`finished_card_max_age_hours`, which reads the served payload exactly
    as the browser does.

    Only ``type == "event"`` cards are considered. Futures have their own arm in
    ``isStale`` keyed on ``resolution_date``; this pass does not reason about
    them, because the defect it fixes is finished GAMES eating game slots, and
    widening it to a second lifecycle without a second measurement is how a
    narrow fix becomes an unreviewable one.
    """
    if not isinstance(item, dict) or item.get("type") != "event":
        return False
    data = item.get("data")
    if not isinstance(data, dict):
        return False
    if (data.get("status") or "").strip().lower() not in FINISHED_STATUSES:
        return False
    age = _commence_age_hours(
        finished_event_age_anchor(data), now=now or datetime.now(timezone.utc)
    )
    if age is None:
        return False
    window = (
        float(max_age_hours)
        if max_age_hours is not None
        else finished_card_max_age_hours(data)
    )
    return age > window


def _renders_as_a_game(item: dict, *, now: datetime) -> bool:
    """An event card the client will actually paint — the #1091 unit of account."""
    return (
        isinstance(item, dict)
        and item.get("type") == "event"
        and not client_deletes_finished_card(item, now=now)
    )


def swap_client_deleted_finished_off_first_page(
    items: list[dict],
    *,
    first_page_size: int = 20,
    max_per_rail: int = FINISHED_RAIL_FIRST_PAGE_CAP,
    now: datetime | None = None,
) -> tuple[list[dict], dict]:
    """Trade first-page cards the client deletes for cards it will render.

    THE FINDING (#3836), measured on production 2026-09-07
    ------------------------------------------------------
    ``GET /api/feed?limit=20&mode=sports`` served four finished games — at slots
    11, 13, 14 and 15, aged 15.3h, 20.3h, 14.1h and 12.3h since commence — that
    the client deletes before paint. Those four slots are not recovered:
    ``FEED_PAGE_LIMIT`` is 20 and ``nextFeedRequest`` marches ``0 -> 20 -> 40``
    with no overlap, so page two does not backfill them. The reader's first
    screen was a **sixteen-card page wearing a twenty-card budget.**

    AND IT IS NOT A THIN-SLATE FACT. The same pull at ``limit=60`` held 21
    admissible cards beyond the window — 12 open futures, 4 scheduled games, 4
    upcoming concepts and one *fresh* completed game. The ranker was not short of
    things the reader would see; it simply did not know which of its own picks
    the client was about to throw away.

    WHY THE RAIL CAP ABOVE DOES NOT ALREADY COVER THIS
    ---------------------------------------------------
    It was the obvious suspect and the measurement clears it. The window held
    exactly three "Recent upset" cards — exactly ``FINISHED_RAIL_FIRST_PAGE_CAP``
    — so ``over_cap_before`` was 0 and the cap never fired, and the page still
    lost four slots. Teaching only the cap's replacement choice about the 8h rule
    would have shipped nothing measurable on this payload. The gap is one layer
    up: no first-page pass knew the client's rule at all.

    THREE THINGS IT MUST NOT DO
    ----------------------------
    1. **Undo the cap.** A replacement that is itself a finished card on a rail
       already at ``max_per_rail`` recreates #3805. Rails are counted with
       ``finished_rail_key`` — the same function the cap uses — against the
       cards that remain **once every doomed card is treated as departing**.

       READ THAT LAST CLAUSE LITERALLY; IT IS NOT THE SAME AS "AFTER THE PLANNED
       SWAPS", WHICH IS WHAT THIS SENTENCE USED TO SAY (#3853). ``swaps`` is
       ``min(len(doomed), len(replacements))``, so on a thin tail some doomed
       cards have no replacement and STAY on the page — and their rails are
       still written off as free. That reads like a bug, and CERT-2204's grader
       filed it as one: four doomed cards on a rail plus one fresh same-rail
       tail card, and page one ends up *carrying* four.

       It is deliberate, because the two counts measure different things. The
       cap bounds what the reader SEES repeated, and a doomed card is by
       definition never rendered. Counting a stayer's rail as occupied would
       refuse the fresh card, and refusing it is worse twice over: it spends a
       page-one slot on something the client deletes, which is the whole defect
       #3836 exists to end; and it removes the last non-stale game, which trips
       the client's ``keptToAvoidEmptyGames`` reprieve (point 2 below), which
       keeps EVERY stale game — so the reader sees four identical headlines
       instead of one. As-served and as-rendered move in opposite directions
       here, so the as-served count is not a conservative proxy for the cap; it
       is an anti-proxy. ``TestThinTailRailAccounting3853`` pins the rendered
       invariant and goes red if this is ever "fixed".
    2. **Empty the surface (#1091 / gotcha #43).** The client's own guard
       reprieves stale games when they are the only games
       (``keptToAvoidEmptyGames``). If this pass trades them away first, that
       reprieve never fires and the reader gets a *gameless sports page* — a
       worse defect than the one being fixed. So the pass checks its own outcome
       and DECLINES ENTIRELY, returning the input untouched, whenever the plan
       would leave the window with no game the client will paint. Declining is
       reported in ``meta`` rather than logged as success.
    3. **Shorten the page.** Swap, never drop — the same contract as
       ``enforce_first_page_quality_floor`` and
       ``hoist_live_events_into_first_page``. Length is preserved, no score is
       touched, and the input list is returned unchanged on any error
       (gotcha #42).

    Live and scheduled cards are never counted and never displaced, for the same
    reason the cap gives: a diversity or freshness rule that pushes a live game
    off page one is the defect #2709 shipped the hoist to end.

    Returns ``(items, meta)``. ``meta`` reports an unmet swap loudly (gotcha #53)
    so a page that kept a doomed card because the pool had nothing to trade does
    not read the same as a page that had no doomed cards at all.
    """
    empty_meta = {
        "client_deleted_before": 0,
        "replacements_available": 0,
        "swapped": 0,
        "client_deleted_after": 0,
        "unswapped": 0,
        "declined_to_keep_a_game": False,
        "max_age_hours": CLIENT_COMPLETED_MAX_AGE_HOURS,
    }
    try:
        now = now or datetime.now(timezone.utc)
        window_size = min(first_page_size, len(items))
        if window_size <= 0:
            return items, empty_meta

        window = items[:window_size]
        tail = items[window_size:]

        doomed = [
            i
            for i, it in enumerate(window)
            if client_deletes_finished_card(it, now=now)
        ]
        meta = dict(empty_meta)
        meta["client_deleted_before"] = len(doomed)
        meta["client_deleted_after"] = len(doomed)
        meta["unswapped"] = len(doomed)
        if not doomed:
            return items, meta

        # Rail bookkeeping starts from the cards that SURVIVE the swap, not from
        # every card in the window: the doomed cards are leaving, so the rails
        # they occupy are freed and a replacement may legitimately take one. On
        # the measured payload all three "Recent upset" cards were doomed, which
        # is precisely the case where counting the window as-served would refuse
        # the best available replacement for no reason.
        doomed_set = set(doomed)
        kept_counts: dict[str, int] = {}
        for i, it in enumerate(window):
            if i in doomed_set:
                continue
            rail = finished_rail_key(it)
            if rail is not None:
                kept_counts[rail] = kept_counts.get(rail, 0) + 1

        replacements: list[int] = []
        for t_idx, it in enumerate(tail):
            if len(replacements) >= len(doomed):
                break
            # A replacement the client also deletes is not a replacement; it is
            # the same defect moved up the page.
            if client_deletes_finished_card(it, now=now):
                continue
            rail = finished_rail_key(it)
            if rail is not None:
                if kept_counts.get(rail, 0) >= max_per_rail:
                    continue
                kept_counts[rail] = kept_counts.get(rail, 0) + 1
            replacements.append(t_idx)

        meta["replacements_available"] = len(replacements)
        swaps = min(len(doomed), len(replacements))
        if swaps <= 0:
            return items, meta

        new_window = list(window)
        new_tail = list(tail)
        # Front-to-front, index-for-index, exactly as the cap above pairs its
        # own lists and for the same reason: `doomed` is ascending window slots
        # and `replacements` is ascending tail slots over an already-ranked
        # tail, so the earliest doomed slot takes the best replacement and the
        # page keeps descending rank. Pairing the weakest slot with the best
        # card inverts reading order; that inversion is the CERT-2190 repair
        # recorded in the cap's own comment, and repeating it here would undo
        # that fix on a different pass.
        for pair in range(swaps):
            w_idx = doomed[pair]
            t_idx = replacements[pair]
            new_window[w_idx], new_tail[t_idx] = new_tail[t_idx], new_window[w_idx]

        # #1091, checked on the OUTCOME rather than argued from the inputs. The
        # question is not "did we swap carefully" but "does the reader still get
        # a game", and the only honest way to answer it is to look at the page
        # this pass is about to return.
        if not any(_renders_as_a_game(it, now=now) for it in new_window):
            meta["declined_to_keep_a_game"] = True
            meta["swapped"] = 0
            meta["client_deleted_after"] = len(doomed)
            meta["unswapped"] = len(doomed)
            return items, meta

        meta["swapped"] = swaps
        meta["client_deleted_after"] = len(doomed) - swaps
        meta["unswapped"] = len(doomed) - swaps
        return new_window + new_tail, meta
    except Exception:  # pragma: no cover - defensive, mirrors live_first_page
        logger.exception("Sports first-page client-deletion swap failed; page unchanged")
        return items, empty_meta


def cap_futures_on_games_led_first_page(
    items: list[dict],
    *,
    first_page_size: int = 20,
    max_futures: int = FUTURES_FIRST_PAGE_CAP,
    max_per_rail: int = FINISHED_RAIL_FIRST_PAGE_CAP,
    now: datetime | None = None,
) -> tuple[list[dict], dict]:
    """Trade surplus futures cards on the Sports first page for games.

    THE FINDING (#4497), measured on production 2026-09-09 23:34Z
    -------------------------------------------------------------
    ``GET /api/feed?mode=sports&limit=60`` served **four futures in the first
    twenty slots** — "Los Angeles Rams leads at 14%" (Super Bowl winner) at 4,
    "Justin Gaethje leads at 84%" at 7, "Alexander Volkanovski leads at 49%" at
    10 and "New favorite: USA (65%)" at 13. Three of them are in the top ten.

    Those slots are not recovered. ``FEED_PAGE_LIMIT`` is 20 and
    ``nextFeedRequest`` marches ``0 -> 20 -> 40`` with no overlap, so page two
    does not backfill them — the same budget arithmetic #3836 is built on. The
    client files futures under "Top Markets", so they do not visibly displace a
    game *section*; the cost is that the games-led surface spent a fifth of its
    one-and-only first page asking who will hold a title belt on 31 December.

    AND IT IS NOT A THIN SLATE. The same pull held 21 event cards in the tail
    against 18 futures, so the ranker had games to give.

    WHY A CAP AND NOT A REORDER
    ----------------------------
    The obvious fix is to push futures down, and it does not work — it was
    tried against this exact payload before this pass was written. A reorder is
    length-preserving *within the same membership*, so every futures card it
    demotes still sits inside the 20-slot budget; the reader gets the same four
    futures in a different order and not one extra game. Only a swap across the
    window boundary converts a futures slot into a game slot.

    The same measurement ruled out the other obvious fix, which is worth
    recording because it looks more correct than it is:
    ``compose_lead(items, include_tonights_games=discover_mode)`` switches the
    tonight's-games lead pass OFF in Sports mode, which reads like a plain bug
    on the one surface whose job is "what's on tonight". Turning it on yields
    three routine MLS overtimes in slots 1-3, one of them scoring 65 and
    outranking four score-98 games, because ``_lead_sort_key`` puts every live
    row in tier 0 ahead of every upcoming row and ``MAX_LEAD`` is 3. It also
    frees no budget, for the reason above. That flag is not this defect's fix.

    WHY TWO
    -------
    Unlike ``FINISHED_RAIL_FIRST_PAGE_CAP``, this number does not descend from
    an existing constant, and pretending otherwise would be worse than saying
    so: it is an opinion about a games-led page, stated once, here. Two futures
    on twenty slots still carries the season-long stories onto page one — the
    Super Bowl field and the title-belt question both survive on the measured
    payload — while leaving eighteen slots to answer the question the reader
    opened the Sports tab to ask. It is a keyword argument so a later
    measurement can move it without editing this reasoning.

    WHAT IT MUST NOT DO
    -------------------
    1. **Recreate the defects the siblings above just fixed.** A replacement is
       refused when the client deletes it (``client_deletes_finished_card``,
       #3836) or when it is a finished card on a rail already at
       ``max_per_rail`` (``finished_rail_key``, #3511/#3805). Rails are counted
       against the window as it survives this pass — every card here stays
       except the futures being traded out, and a futures card occupies no rail.
    2. **Displace a game.** Only ``type == "futures"`` cards are ever moved, and
       only ever outward. Live, scheduled and finished games are neither counted
       nor touched, so this cannot cost the surface a game the way #1091 did —
       the swap's direction guarantees the window ends with strictly more game
       cards than it started with, which is the opposite of the failure mode.
    3. **Shorten the page.** Swap, never drop. Length is preserved, no score is
       touched, and the input is returned unchanged on any error (gotcha
       #42/#43).

    ORDER: AFTER THE TWO SIBLINGS, BEFORE THE LIVE HOIST
    -----------------------------------------------------
    After, so a futures slot this frees is offered to a tail card those passes
    have already vetted rather than competing with them for the same trade.
    Before the hoist, for the reason the whole chain observes: that pass is
    Alex's P1 acceptance criterion and keeps the last word on first-page
    membership. ``test_sports_first_page_rails_wiring_3511`` asserts the
    position rather than trusting this paragraph.

    Returns ``(items, meta)``. ``meta`` reports an unmet cap loudly (gotcha #53)
    so a page that kept a surplus futures card because the tail had no game to
    trade does not read the same as a page that was never over cap.
    """
    empty_meta = {
        "over_cap_before": 0,
        "replacements_available": 0,
        "swapped": 0,
        "over_cap_after": 0,
        "unswapped": 0,
        "cap": max_futures,
    }
    try:
        now = now or datetime.now(timezone.utc)
        window_size = min(first_page_size, len(items))
        if window_size <= 0 or max_futures < 0:
            return items, empty_meta

        window = items[:window_size]
        tail = items[window_size:]

        # Walked in served order, so the futures cards KEPT are the best-ranked
        # of their cohort and the surplus is always the weakest N.
        seen = 0
        over_cap: list[int] = []
        for i, it in enumerate(window):
            if not isinstance(it, dict) or it.get("type") != "futures":
                continue
            seen += 1
            if seen > max_futures:
                over_cap.append(i)

        meta = dict(empty_meta)
        meta["over_cap_before"] = len(over_cap)
        meta["over_cap_after"] = len(over_cap)
        meta["unswapped"] = len(over_cap)
        if not over_cap:
            return items, meta

        # Every window card except the departing futures stays, and a futures
        # card sits on no rail, so the surviving rail counts are simply the
        # window's own. (Contrast the sibling above, where the doomed cards ARE
        # rail-holders and their rails have to be written off as freed.)
        kept_counts: dict[str, int] = {}
        for it in window:
            rail = finished_rail_key(it)
            if rail is not None:
                kept_counts[rail] = kept_counts.get(rail, 0) + 1

        replacements: list[int] = []
        for t_idx, it in enumerate(tail):
            if len(replacements) >= len(over_cap):
                break
            # A replacement must be a GAME — `type == "event"` — and not merely
            # "not a futures card". Admitting anything non-futures satisfies the
            # cap while buying the reader nothing: on the measured payload the
            # best two non-futures tail cards were one game and one `concept`,
            # so the looser test swapped a futures card for a concept card and
            # the games-led page ended with the same fifteen games it started
            # with. The cap is not the point; the game is.
            if not isinstance(it, dict) or it.get("type") != "event":
                continue
            if client_deletes_finished_card(it, now=now):
                continue
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
        # Front-to-front, index-for-index, as both siblings pair their lists and
        # for the same reason: the earliest surplus slot takes the best-ranked
        # replacement so the page keeps descending rank. Pairing the weakest slot
        # with the best card is the CERT-2190 inversion, recorded in the cap's
        # own comment; repeating it here would reintroduce it on a third pass.
        for pair in range(swaps):
            w_idx = over_cap[pair]
            t_idx = replacements[pair]
            new_window[w_idx], new_tail[t_idx] = new_tail[t_idx], new_window[w_idx]

        meta["swapped"] = swaps
        meta["over_cap_after"] = len(over_cap) - swaps
        meta["unswapped"] = len(over_cap) - swaps
        return new_window + new_tail, meta
    except Exception:  # pragma: no cover - defensive, mirrors live_first_page
        logger.exception("Sports first-page futures cap failed; page unchanged")
        return items, empty_meta
