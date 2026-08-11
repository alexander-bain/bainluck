"""Lead the Discover deck with tonight's games (Alex ruling 2026-08-08(d)(1)).

The finding: `bainluck.com` returned 55 cards with ZERO game events, led by
"Will the U.S. confirm that aliens exist?" and "Hantavirus pandemic in 2026?".
That was *designed* behaviour — Discover demotes non-exceptional events so
futures can compete — and it was the right design for a pure discovery surface.
It became wrong the moment "find tonight's game" was named a north-star task,
because the default page could not start that task.

**Ruled: during a live season the landing page leads with tonight's games — live
or starting soon — with the Discover mix below.**

DESIGN: PROMOTE, DO NOT UN-DEMOTE
---------------------------------
The obvious implementation is to relax the demotion cap. This does not do that,
deliberately. The demotion is load-bearing for the rest of Discover, and #1091
is the standing lesson that changing a feed cap is exactly how the Sports tab
got emptied. Instead this is a **pure stable reorder** in the same shape as
`_pin_marquee_items`: it moves a bounded number of already-present items to the
front, touches no score, drops nothing, and returns the input unchanged on any
error. It cannot empty anything, because it removes nothing.

"DURING A LIVE SEASON" NEEDS NO CALENDAR
---------------------------------------
Nothing here consults a season window. If no game is live or imminent, the
eligible set is empty and the pass is a no-op — which is precisely the correct
behaviour out of season, and one less thing to keep in sync with reality
(`season_windows` exists, but a rule that self-answers is better than a rule
that needs a lookup to be right).

NOT A SCOREBOARD
----------------
The ruling says lead with tonight's games, not show every game. `MAX_LEAD` caps
it at a handful, and games without team media are ineligible — the same bar
`_filter_discover_event_noise` already applies, and the reason a minor-league
fixture must never be the first thing a reader sees. (Alex's Kalshi pass caught
that exact failure in search: "Lehigh Valley IronPigs at Worcester Red Sox"
outranking the actual MLB game.)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

__all__ = [
    "MAX_LEAD",
    "SOON_WINDOW_HOURS",
    "MARQUEE_PIN_KEY",
    "select_tonights_games",
    "lead_with_tonights_games",
    "compose_lead",
]

# The flag `_score_*` sets on a calendar-flagged marquee that is currently live.
# Named here because `compose_lead` is now the single place the marquee prefix
# and the tonight-games prefix are decided together, so the key has to be
# readable from this module rather than only from the route.
MARQUEE_PIN_KEY = "_marquee_pin"

# How many games may lead the deck. Enough to answer "what's on tonight",
# far short of a scoreboard.
MAX_LEAD = 3

# How far ahead "starting soon" reaches. Wide enough to cover the pre-game
# window a reader is actually thinking about, narrow enough that a lunchtime
# visit does not lead with a game eight hours away.
SOON_WINDOW_HOURS = 4


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _is_eligible(item: dict, now: datetime, soon_window_hours: int) -> bool:
    """A game a reader would call 'on tonight' — live, or about to start.

    Deliberately strict. Every rejection below keeps an item in the Discover
    mix where it already was; none of them removes anything.
    """
    if item.get("type") != "event":
        return False

    data = item.get("data") or {}
    status = (data.get("status") or "").strip().lower()

    # A finished game is not "tonight's game" — it is a result, and the settled
    # surfaces own it. Leading with one would be the opposite of the ruling.
    if status in {"completed", "closed", "postponed", "cancelled", "canceled"}:
        return False

    # Same bar the noise filter already applies: no logos, no lead slot. This is
    # what keeps a minor-league fixture out of the first card.
    if not (data.get("home_team_data") or data.get("away_team_data")):
        return False

    if status == "live":
        return True

    if status in {"scheduled", "upcoming", "pre", ""}:
        commence = _parse_dt(data.get("commence_time"))
        if commence is None:
            return False
        # Strictly ahead of us and inside the window. A start time in the past
        # on a still-"scheduled" row means the status is lagging, not that the
        # game is imminent, so it does not qualify.
        delta = commence - now
        return timedelta(0) <= delta <= timedelta(hours=soon_window_hours)

    return False


def _lead_sort_key(item: dict, now: datetime) -> tuple:
    """Live games first, then the soonest to start.

    Within the live tier the existing rank order decides, so a marquee live game
    still beats a routine one — this pass re-orders, it does not re-judge.
    """
    data = item.get("data") or {}
    status = (data.get("status") or "").strip().lower()
    if status == "live":
        return (0, 0.0, -float(item.get("_rank_score") or item.get("score") or 0))
    commence = _parse_dt(data.get("commence_time"))
    seconds_away = (commence - now).total_seconds() if commence else float("inf")
    return (1, seconds_away, 0.0)


def select_tonights_games(
    feed_items: list[dict],
    now: datetime,
    max_lead: int = MAX_LEAD,
    soon_window_hours: int = SOON_WINDOW_HOURS,
) -> list[dict]:
    """The bounded set of items that should lead, in the order they should lead."""
    eligible = [it for it in feed_items if _is_eligible(it, now, soon_window_hours)]
    eligible.sort(key=lambda it: _lead_sort_key(it, now))
    return eligible[:max_lead]


def lead_with_tonights_games(
    feed_items: list[dict],
    now: datetime | None = None,
    max_lead: int = MAX_LEAD,
    soon_window_hours: int = SOON_WINDOW_HOURS,
) -> list[dict]:
    """Move up to ``max_lead`` live/imminent games to the front. Pure and stable.

    Everyone else keeps their relative order, nothing is dropped, no score is
    touched, and any error returns the input unchanged (gotcha #42/#43).
    """
    try:
        if not feed_items:
            return feed_items
        if now is None:
            now = datetime.now(timezone.utc)

        lead = select_tonights_games(feed_items, now, max_lead, soon_window_hours)
        if not lead:
            return feed_items

        lead_ids = {id(it) for it in lead}
        rest = [it for it in feed_items if id(it) not in lead_ids]
        return lead + rest
    except Exception:  # noqa: BLE001 — a reorder must never break the feed
        return feed_items


def compose_lead(
    feed_items: list[dict],
    now: datetime | None = None,
    *,
    include_tonights_games: bool = True,
    max_lead: int = MAX_LEAD,
    soon_window_hours: int = SOON_WINDOW_HOURS,
) -> list[dict]:
    """The ONE ordering pass for the front of the Discover deck (C185).

    Returns ``[pinned marquees] + [up to max_lead tonight games] + [remainder]``,
    every slice in stable input order.

    WHY THIS IS ONE FUNCTION AND NOT TWO PASSES
    -------------------------------------------
    It used to be two, run back to back in the route: ``_pin_marquee_items``
    returned ``pinned + rest``, and then ``lead_with_tonights_games`` returned
    ``lead + rest`` over that result. Both write a PREFIX, so they compose as
    last-writer-wins: the second pass hoisted a live/imminent game above the
    marquee the first pass had just pinned. The Open and the World Cup final
    lost the top slot to a routine game — the exact failure class the marquee
    pin exists to prevent.

    The route comment asserted the opposite ("It runs AFTER the marquee pin
    deliberately: an in-progress marquee concept … keeps the very top"), which
    is why the defect survived review: the code and the comment disagreed and
    the comment was the more convincing of the two. Two prefix-writers cannot be
    ordered into the intended result — running the marquee pass second would
    just invert which one loses. The composition has to be single.

    Ordering authority is ``tests/evals/fixtures/discover_lead_order_contract.json``
    (C185's eight-case corpus), which this function is bound to by
    ``tests/evals/test_discover_lead_order_contract.py``.

    Preserves every property of the two passes it replaces: pure, stable, no
    score touched, nothing dropped or duplicated, and any error returns the
    input unchanged (gotchas #42/#43).
    """
    try:
        if not feed_items:
            return feed_items
        if now is None:
            now = datetime.now(timezone.utc)

        pinned = [it for it in feed_items if it.get(MARQUEE_PIN_KEY)]
        unpinned = [it for it in feed_items if not it.get(MARQUEE_PIN_KEY)]

        # Selected from the UNPINNED items only. A marquee that is itself an
        # eligible game is already leading, so it must not also consume one of
        # the `max_lead` slots — that would silently shorten the game lead-in
        # while looking like a cap.
        games = (
            select_tonights_games(unpinned, now, max_lead, soon_window_hours)
            if include_tonights_games
            else []
        )

        if not pinned and not games:
            return feed_items

        game_ids = {id(it) for it in games}
        tail = [it for it in unpinned if id(it) not in game_ids]
        return pinned + games + tail
    except Exception:  # noqa: BLE001 — a reorder must never break the feed
        return feed_items
