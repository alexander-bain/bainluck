"""A market we have already settled does not draw the chart of a game that has
not kicked off (#5890 answer 2, the third rail of #5820 / #5771).

THE SPECIMEN, READ ON PRODUCTION 2026-09-13 18:06Z
--------------------------------------------------
`bainluck.com/events/15298125` (Sevilla v Valencia, kick-off 19:00Z) at 390px,
**58 minutes before kick-off**: an honest hero — `59% – 41%`, "2 sportsbooks" —
over a Win Probability chart whose green Kalshi line runs flat near 50%, **cliffs
vertically to a labelled `99%`**, and holds it to the right edge, under a control
reading "Lead changes (7)". The x-axis prints `11:06 AM … 3:56 PM` with no date,
so a reader takes it for this afternoon.

Every one of those points comes from market **60482102**
(`KXLALIGAGAME-26SEP13SEVVCF`), whose own row reads `status='resolved',
settled_at 2026-09-11 22:49:23Z`. The rows refute each other and no ground truth
is needed: a settlement stamped two days before kick-off cannot be that fixture's
price history.

WHY THIS IS A THIRD RAIL AND NOT A RE-FIX
-----------------------------------------
The same market, the same predicate, three surfaces:

* #5820 refused it as the **blend's** speaker (`admissible_as_blend_speaker`) —
  live, and it is why that page's hero reads 59% instead of 99%.
* #5771 refused it as a **market card** on `/game-markets` — the "Sevilla 99%"
  card one scroll below the hero.
* This refuses it as a **chart series**. `/history` was the last rail still
  drawing the number the other two had withdrawn.

#5890 asked the question directly ("should `/history`'s tail be truncated at the
withdrawal?") and routed it here, to the backend. The answer this module gives is
narrower than truncation and wider than a tail:

**TRUNCATING AT `settled_at` WOULD HAVE FIXED NOTHING — MEASURED.** Over the 21
production events in scope, the points at or after the settlement stamp number
**0, 1 or 2**; Sevilla has exactly **one** of 942. The cliff is drawn *before*
the stamp. A tail-truncation ships a no-op that reads like a fix.

WHAT IT DOES NOT TOUCH, AND THE POPULATION THAT PROVES IT
---------------------------------------------------------
Measured 2026-09-13 18:0xZ over every event with `commence_time > now()` whose
win-prob rows carry a `game_state.market_id`:

    market references on unstarted events   665  across 476 events
    settled by `status`                      22
    settled by an `is_winner` grade          16  (all a subset of the 22)
    -> withheld                              22  markets on  21 events
    -> untouched                            643  markets on 455 events

An event that has **started**, and an event that is **finished**, are both out of
scope by construction: the caller asks `_event_has_not_kicked_off` first, so
"settled means settled" (a completed event keeps its whole journey, gotcha #43)
cannot be reached from here at all.

WHAT THE READER LOSES, SAID PLAINLY
------------------------------------
14 of the 21 events draw their entire win-prob rail from the settled market, so
their chart goes **empty** rather than wrong; 3 of those still have a sportsbook
line and 11 do not. That is the intended direction under notice 34 — if a number
cannot be shown honestly, leave the space empty — and the frontend already draws
"Chart available at game time" for a pre-kickoff event with no series, which is
exactly what `/events/15293325` renders today.

THE CAUSE UNDERNEATH, FILED NOT FIXED
--------------------------------------
On 18 of the 21, the market's own ticker names a date that has passed
(`KXBOXING-26SEP03SANFORION` settled 09-04 on an event our row dates 09-17;
`KXSERIEAGAME-26SEP12SASJUV` settled 09-13 on an event our row dates 09-13 18:45Z)
— our `commence_time` is stale, not the settlement. That is a matching symptom
and belongs to lane1 under D35/#2693; it is filed, not fixed here. This module
withholds on the CONTRADICTION, so it is correct whichever side of it is wrong.
"""

from __future__ import annotations

from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.models import FuturesMarket
from app.utils.settledness import market_assigned_settled


def market_ids_in_series(win_prob_history: dict) -> set[int]:
    """Every ``game_state.market_id`` the chart's win-prob series are drawn from.

    Defensive about shape on purpose: ``game_state`` is JSONB and a row may hold
    a list, a string or nothing at all, and a non-numeric id must not throw a
    page build. A point with no market id is not from a market (ESPN, the stat
    model) and is never withheld by anything in this module.
    """
    ids: set[int] = set()
    for points in (win_prob_history or {}).values():
        for point in points or []:
            ids.add(_point_market_id(point))
    ids.discard(None)
    return ids


def _point_market_id(point) -> int | None:
    if not isinstance(point, dict):
        return None
    state = point.get("game_state")
    if not isinstance(state, dict):
        return None
    raw = state.get("market_id")
    if raw is None or isinstance(raw, bool):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


async def settled_market_ids(db, market_ids: Iterable[int]) -> set[int]:
    """Of ``market_ids``, the ones our own rows say are settled.

    Delegates to :func:`app.utils.settledness.market_assigned_settled` rather
    than testing ``status`` here (#1951), so gotcha #33's settled-but-
    ``status='open'`` Kalshi rows are caught by the grade arm — which is why the
    outcomes are eager-loaded: the predicate reads them, and a lazy load inside
    an async request raises.

    Asked of the markets the SERIES names, not of the event's linked markets: a
    point can carry the id of a market that was since unlinked or relinked, and
    the question "did we settle the thing that drew this line" is about the
    former, not the latter.
    """
    ids = {int(m) for m in market_ids if m is not None}
    if not ids:
        return set()
    rows = (
        (
            await db.execute(
                select(FuturesMarket)
                .options(selectinload(FuturesMarket.outcomes))
                .where(FuturesMarket.id.in_(ids))
            )
        )
        .scalars()
        .unique()
        .all()
    )
    return {m.id for m in rows if market_assigned_settled(m)}


def drop_series_from_markets(
    win_prob_history: dict, sources_meta: dict, market_ids: set[int]
) -> int:
    """Remove every point drawn from ``market_ids``. Returns how many went.

    Mutates both dicts in place, the same contract as the #1828 cross-game
    filter beside it, and for the same reason: `period_markers`, the ESPN score
    supplement and `aggregate_line` are all derived from `win_prob_history`
    further down, so a filter that returned a copy would fix the payload's chart
    and leave its own derivations drawing the withheld number.

    A source left with NO points is removed from both dicts. Keeping the key
    with ``snapshot_count: 0`` would advertise a source in the legend and the
    "+N sources" control that plots nothing — the caption naming a source the
    chart does not carry is #5890's third question, answered the same way here.
    """
    if not market_ids:
        return 0
    dropped = 0
    for source in list(win_prob_history):
        kept = []
        for point in win_prob_history[source]:
            if _point_market_id(point) in market_ids:
                dropped += 1
                continue
            kept.append(point)
        if kept:
            win_prob_history[source] = kept
            if source in sources_meta:
                sources_meta[source]["snapshot_count"] = len(kept)
        else:
            del win_prob_history[source]
            sources_meta.pop(source, None)
    return dropped


async def withhold_settled_market_series(db, win_prob_history: dict, sources_meta: dict):
    """The whole pass: find the settled markets behind the chart, drop their points.

    Returns ``(dropped_points, settled_market_ids)`` so the caller can log what
    went and a test can tell "nothing to drop" from "dropped nothing" (gotcha
    #53 — the zero-yield case has to be legible).

    🔴 THE CALLER OWNS THE SCOPE. This function never asks whether the event has
    started; `routes/events._event_has_not_kicked_off` does, beside the sibling
    gate that makes the same judgement for `/game-markets`. Calling this on a
    started or finished event would delete a real journey.
    """
    ids = market_ids_in_series(win_prob_history)
    if not ids:
        return 0, set()
    settled = await settled_market_ids(db, ids)
    return drop_series_from_markets(win_prob_history, sources_meta, settled), settled
