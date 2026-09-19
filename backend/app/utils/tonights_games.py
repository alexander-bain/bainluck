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
    "live_game_card_has_substance",
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


def live_game_card_has_substance(item: dict) -> bool:
    """Does this LIVE game card put anything on the screen beyond two names?

    #4872, from the ranking eval's first row (0/10, hard check FAILS). Two cards
    led Discover at slots 2 and 3 on 2026-09-10 19:20Z, both scored **35** — the
    demotion cap, i.e. the scorer had already called them non-exceptional — and
    both sat above a 98 and a 100:

        Bodø/Glimt @ Bayern Munich    0–0  clock=None  period=None  96% / 4%
        Sabah FK @ Manchester United  0–0  clock=None  period=None  97% / 3%

    with `reason=""` and one crest missing each. The reader met a green card, a
    grey placeholder box, the word "Live", and nothing else.

    **WHY THIS PREDICATE EXISTS HERE AND NOT IN THE QUALITY FLOOR.**
    `feed_market_quality.is_wholly_silent_card` is the shipped rule for a card
    that does not speak, and it opens `if item.get("type") != "futures"`. That
    scope is DELIBERATE and its docstring gives the reason — *"a game card
    renders two team names, two scores and two logos"* — so a game card is never
    silent for want of a caption. **That premise is true of the card it was
    written about and false of this one:** a just-kicked-off game has 0–0, no
    clock, and (per #4862, 35 of 49 served cards) frequently one missing crest.
    Widening the futures predicate instead would collide head-on with #4681 and
    notice 27, which require a settled marquee final — a card whose story IS the
    score and which routinely carries no caption — to reach page one. So the
    game-card test lives here, next to the pass that seats these cards, and the
    futures predicate is left exactly as it is.

    **THE DOORS, and why `headline` is not one of them.** A live card's headline
    is the literal string ``"Live"`` on every live game, silent or not. Admitting
    it would make this predicate true for the entire population it exists to
    catch — the survivor a "just check all the text fields" version leaves
    behind. Substance is a SENTENCE (`reason`/`context_summary`) or EVIDENCE THE
    GAME IS UNDER WAY (a clock, a period, or a score on the board).

    **A 0–0 with no clock is not a scoreless game, it is an unstarted one.** A
    genuine 0–0 in the 60th minute carries a clock or a period and passes here on
    that. The pair above carry neither, which is why "0–0" is not treated as a
    score a reader can read.
    """
    if not isinstance(item, dict):
        return False
    data = item.get("data") if isinstance(item.get("data"), dict) else {}

    for door in ("reason", "context_summary"):
        if str(item.get(door) or "").strip():
            return True
    for door in ("game_clock", "period"):
        if str(data.get(door) or "").strip():
            return True

    # `bool` is an `int` subclass, so an explicit exclusion — a `True` here would
    # otherwise read as the number 1 and put a phantom goal on the board.
    scores = [data.get("home_score"), data.get("away_score")]
    return any(
        isinstance(s, int) and not isinstance(s, bool) and s > 0 for s in scores
    )


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


def _is_eligible(
    item: dict,
    now: datetime,
    soon_window_hours: int,
    protected_event_ids: set[int] | None = None,
) -> bool:
    """A game a reader would call 'on tonight' — live, or about to start.

    Deliberately strict. Every rejection below keeps an item in the Discover
    mix where it already was; none of them removes anything.

    ``protected_event_ids`` is the set the ADMISSION arm already selected for
    this request (#4898's ``_imminent_marquee_kickoff_ids``). Such an id widens
    the kickoff window and NOTHING else: every other rejection below — finished,
    suspended, media-less, start time in the past — still applies to it. See
    :func:`compose_lead` for why the window is the only gate that may differ.
    """
    if item.get("type") != "event":
        return False

    data = item.get("data") or {}
    status = (data.get("status") or "").strip().lower()

    # A finished game is not "tonight's game" — it is a result, and the settled
    # surfaces own it. Leading with one would be the opposite of the ruling.
    #
    # `suspended` (live/048) is rejected HERE, explicitly, rather than being left
    # to the `return False` at the bottom. The outcome is identical today; the
    # difference is that the rejection is now a decision on the record — a match
    # nobody is watching is not the game to LEAD the deck with, however true its
    # card is. It still appears in the mix (this pass only re-orders), so the
    # rejection costs the reader nothing and buys the next editor a reason.
    if status in {
        "completed",
        "closed",
        "suspended",
        "postponed",
        "cancelled",
        "canceled",
    }:
        return False

    # Same bar the noise filter already applies: no logos, no lead slot. This is
    # what keeps a minor-league fixture out of the first card.
    if not (data.get("home_team_data") or data.get("away_team_data")):
        return False

    if status == "live":
        # #4872 — and this NARROWS Alex's own acceptance criterion, so it is
        # written as a decision rather than slipped in as a guard. The criterion
        # on record (`live_first_page.py`, "WHY A PRICE IS REQUIRED") is "every
        # event with status live and a price"; this adds "and with something on
        # the screen". The case for it is that a 0–0 kick-off with no clock, a
        # 97–3 price and a missing crest is not "the game that is on tonight" in
        # any reader's sense of the phrase — and the scorer had already said so,
        # capping both specimens at 35 while the lead seated them at slots 2 and
        # 3 above a 98 and a 100. The lead was overriding a judgement the ranker
        # had already made correctly.
        #
        # Safe by construction, which is the reason this pass is the right place
        # for it: `compose_lead` only RE-ORDERS. A rejection here leaves the card
        # exactly where the ranker put it — nothing is dropped, so this cannot
        # empty anything (#1091, gotcha #43, and the module docstring's promise).
        return live_game_card_has_substance(item)

    if status in {"scheduled", "upcoming", "pre", ""}:
        # NOT extended to this arm, deliberately. A scheduled game has no clock
        # and no score BECAUSE IT HAS NOT STARTED, and its substance is its start
        # time — the same test here would reject every upcoming game and delete
        # the pre-game half of the lead. The bus's row also flagged two
        # "Starting soon" cards, but on `/sports`, which is a different pass and
        # a different measurement; widening on the strength of a reading taken
        # somewhere else is how a narrow fix becomes an unreviewable one.
        commence = _parse_dt(data.get("commence_time"))
        if commence is None:
            return False
        # Strictly ahead of us and inside the window. A start time in the past
        # on a still-"scheduled" row means the status is lagging, not that the
        # game is imminent, so it does not qualify.
        #
        # The past-start rejection is checked FIRST and applies to protected ids
        # too: the admission arm rejects a lagging status for this exact reason,
        # and a pass that disagreed with the arm feeding it is the defect shape
        # #4898's own docstring warns about.
        delta = commence - now
        if delta < timedelta(0):
            return False
        if delta <= timedelta(hours=soon_window_hours):
            return True
        # Outside the lead pass's own window, but the admission arm chose this
        # game for THIS request — so it leads from the arm's window, not from a
        # second one this pass would have to be kept in sync with.
        return bool(protected_event_ids) and data.get("id") in protected_event_ids

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
    protected_event_ids: set[int] | None = None,
) -> list[dict]:
    """The bounded set of items that should lead, in the order they should lead.

    A protected game sorts by the SAME key as every other one — live first, then
    soonest to start — so widening the window never lets a game six hours out
    displace one starting in twenty minutes. It can only fill a slot the more
    imminent games did not.
    """
    eligible = [
        it
        for it in feed_items
        if _is_eligible(it, now, soon_window_hours, protected_event_ids)
    ]
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
    protected_event_ids: set[int] | None = None,
) -> list[dict]:
    """The ONE ordering pass for the front of the Discover deck (C185).

    Returns ``[pinned marquees] + [up to max_lead tonight games] + [remainder]``,
    every slice in stable input order.

    ONE SELECTION DECISION, NOT TWO WINDOWS (T4-A1, #5099)
    -----------------------------------------------------
    ``protected_event_ids`` is #4898's admission set — the about-to-start
    marquee games the display chain already decided to KEEP this request. Before
    it was threaded here, admission and seating read two different windows:
    ``_DISCOVER_IMMINENT_KICKOFF_HOURS = 6`` decided what survived and
    ``SOON_WINDOW_HOURS = 4`` decided what led, so between T-6h and T-4h a
    marquee game was on the page but was not seated by this pass. Any top-three
    placement it had in that band came from whatever the diversity pass happened
    to do — measured, not argued: at T-6h/T-5h/T-4.5h the specimen sat at rank 3
    with this pass a no-op, and moved to rank 1 only at T-3h when its own window
    opened.

    Widening ``SOON_WINDOW_HOURS`` would have been the wrong fix twice over: it
    is C185's contract and it governs every routine game too. Passing the set
    the other pass already chose keeps ONE selection decision with two
    consumers, which is the same shape #4898 used for its two deleting passes.

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
            select_tonights_games(
                unpinned, now, max_lead, soon_window_hours, protected_event_ids
            )
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
