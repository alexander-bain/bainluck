"""#11937 (Ruling 277: A): Discover's frozen Candidate 3 ranking order.

Frozen before Candidate 3's six-morning blind grading window opens on
``/grade/pair``. ``backend/app/utils/discover_rank.py`` (Candidates 1 and 2) is
kept untouched so historical replays and its recorded SHA-256 freeze stay intact.

What Candidate 3 changes over Candidate 2 (Ruling 277: A, #13100, #13106, #13097):
1. **Bounded lift for grouped cards** (``GROUPED_LIFT = +0.06`` instead of C2's
   flat ``+1.0``), and standing non-fun news story bundles with no dated >=2pt
   24h move do not coast to seats 1-3 ahead of fresh/moving cards.
2. **Recency & movement:** dated >=2pt 24h movement (on outcomes >=5%), live or
   imminent games/tournaments (within 24h), and near-term resolution
   (``0 <= days <= 14``, never ``days < 0``) earn bounded freshness lifts.
3. **Far-horizon discount (>60 days), with fun-tagged markets EXEMPT:** quiet
   non-fun markets settling >60d out (-0.18) or >180d out (-0.24) step back;
   markets in ``backend/data/discover/fun_markets.json`` are exempt.
4. **Mix alignment toward Alex's target (3 odd, 2.5 entertainment, 0.5 politics):**
   reorders across ``served[:60]`` (so fun and entertainment cards below seat 20
   can reach the opening ten), caps opening-ten politics/world at <=1 and only
   when major/moving (keeping quiet/minor foreign elections out), caps fun at
   <=3 (<=1 long-shot single), caps entertainment at <=3 (<=1 weekly Netflix
   chart card), and caps sports at <=4 across distinct sports (<=1 per sport).

The harness reaches it with
``scorecard.py --replay app.utils.discover_rank_c3:rank_c3_mix``. Discover itself
does not call this while the ranking switch is off; it is used only by the blind
morning evaluation routes (``pair="p3"``) and offline scoring.
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from app.utils.discover_fun_tags import fun_market_ids_for_sub_tag, load_fun_markets_registry

#: Candidate pool drawn from the served slate so fun/entertainment cards seated
#: beyond page 1 can compete for the opening ten.
POOL_SIZE = 60
#: Fixed-seat window for finished games (matches discover_rank.PAGE).
PAGE = 20
#: Opening ten, where repeat and category-mix rules apply.
OPENING = 10
#: Standing entity repeat cap in the opening ten.
MAX_ENTITY_REPEATS = 2

#: Opening-ten mix ceilings (Ruling 277: A / #13106).
MAX_FUN_OPENING = 3
MAX_LONG_SHOT_SINGLES_OPENING = 1
MAX_ENTERTAINMENT_OPENING = 3
MAX_WEEKLY_CHART_OPENING = 1
MAX_POLITICS_OPENING = 1
POLITICS_OPENING_MIN_SCORE = 85.0
MAX_SPORTS_OPENING = 4
MAX_PER_SPORT_OPENING = 1

#: Bounded grouped-card lift (replaces Candidate 2's flat +1.0).
GROUPED_LIFT = 0.06
STATIC_STORY_BUNDLE_PENALTY = -0.06

#: Recency / movement weights.
MOVEMENT_MIN_ABS = 0.02
MOVEMENT_MIN_PROB = 0.05
MOVEMENT_BASE_LIFT = 0.07
MOVEMENT_MAX_LIFT = 0.14
LIVE_IMMINENT_LIFT = 0.08
NEAR_RESOLUTION_DAYS = 14.0
NEAR_RESOLUTION_LIFT = 0.04

#: Far-horizon discounts (>60 days, >180 days); fun-tagged markets are exempt.
FAR_HORIZON_DAYS = 60.0
VERY_FAR_HORIZON_DAYS = 180.0
FAR_HORIZON_DISCOUNT = -0.18
VERY_FAR_HORIZON_DISCOUNT = -0.24

#: Mix alignment lifts / penalties.
FUN_LIFT = 0.10
ENTERTAINMENT_LIFT = 0.06
POLITICS_PENALTY = -0.14

GROUPED_TYPES = frozenset({"bundle", "concept", "tournament"})
GATE_FLAGS = ("settled_without_result", "stale", "blend_missing")

POLITICS_CATEGORIES = frozenset({"politics", "geopolitics", "world"})
ENTERTAINMENT_CATEGORIES = frozenset(
    {"entertainment", "culture", "media", "movies", "music", "tv"}
)
SPORTS_CATEGORIES = frozenset(
    {
        "football",
        "basketball",
        "baseball",
        "hockey",
        "soccer",
        "golf",
        "tennis",
        "mma",
        "boxing",
        "motorsport",
        "racing",
        "olympics",
        "nfl",
        "nba",
        "mlb",
        "nhl",
        "ncaab",
        "wncaab",
        "ncaaf",
        "mls",
        "epl",
        "ufc",
        "f1",
        "sports",
        "icehockey_nhl",
        "basketball_ncaab",
        "basketball_wncaab",
        "americanfootball_nfl",
        "americanfootball_ncaaf",
        "basketball_nba",
        "baseball_mlb",
    }
)
_WEEKLY_CHART_RE = re.compile(r"\btop\s+(?:global|us|u\.s\.)\s+netflix\b", re.IGNORECASE)


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


def _served_pos(card: dict) -> float:
    pos = card.get("served_position")
    return pos if isinstance(pos, (int, float)) and not isinstance(pos, bool) else math.inf


def _entities(card: dict) -> list[str]:
    return [str(e) for e in (card.get("entities") or []) if e]


def fails_gate(card: dict) -> bool:
    return any(card.get(flag) is True for flag in GATE_FLAGS)


def is_grouped(card: dict) -> bool:
    return card.get("type") in GROUPED_TYPES


def is_finished_game(card: dict) -> bool:
    return card.get("type") == "event" and card.get("settled") is True


def _fun_id_sets(
    fun_ids: Optional[frozenset[int]] = None,
    long_shot_ids: Optional[frozenset[int]] = None,
) -> tuple[frozenset[int], frozenset[int]]:
    if fun_ids is not None and long_shot_ids is not None:
        return fun_ids, long_shot_ids
    reg = load_fun_markets_registry()
    resolved_fun = fun_ids if fun_ids is not None else frozenset(reg.markets.keys())
    resolved_ls = (
        long_shot_ids
        if long_shot_ids is not None
        else frozenset(fun_market_ids_for_sub_tag("long-shot"))
    )
    return resolved_fun, resolved_ls


def _card_market_ids(card: dict) -> list[int]:
    inner = card.get("card") or {}
    data = inner.get("data") or {}
    kind = card.get("type") or inner.get("type")
    mids: list[int] = []
    if kind == "futures":
        mid = data.get("id") or data.get("market_id")
        if mid is not None:
            try:
                mids.append(int(mid))
            except (TypeError, ValueError):
                pass
    elif kind == "bundle":
        for member in data.get("items") or []:
            md = (member or {}).get("data") or {}
            mid = md.get("id") or md.get("market_id")
            if mid is not None:
                try:
                    mi = int(mid)
                    if mi not in mids:
                        mids.append(mi)
                except (TypeError, ValueError):
                    pass
        for mid in data.get("member_ids") or []:
            try:
                mi = int(mid)
                if mi not in mids:
                    mids.append(mi)
            except (TypeError, ValueError):
                pass
    return mids


def is_fun_tagged(card: dict, *, fun_ids: Optional[frozenset[int]] = None) -> bool:
    resolved_fun, _ = _fun_id_sets(fun_ids=fun_ids)
    return any(mid in resolved_fun for mid in _card_market_ids(card))


def is_long_shot_single(
    card: dict, *, long_shot_ids: Optional[frozenset[int]] = None
) -> bool:
    if card.get("type") != "futures":
        return False
    _, resolved_ls = _fun_id_sets(long_shot_ids=long_shot_ids)
    mids = _card_market_ids(card)
    return bool(mids) and all(mid in resolved_ls for mid in mids)


def _category(card: dict) -> str:
    return str(card.get("category") or "").strip().lower()


def is_politics(card: dict, *, fun_ids: Optional[frozenset[int]] = None) -> bool:
    return (not is_fun_tagged(card, fun_ids=fun_ids)) and (_category(card) in POLITICS_CATEGORIES)


def is_entertainment(card: dict) -> bool:
    return _category(card) in ENTERTAINMENT_CATEGORIES


def is_sports(card: dict) -> bool:
    if card.get("type") in ("event", "tournament"):
        return True
    cat = _category(card)
    if cat in SPORTS_CATEGORIES:
        return True
    return any(
        cat.startswith(prefix)
        for prefix in (
            "basketball",
            "football",
            "hockey",
            "icehockey",
            "baseball",
            "soccer",
            "tennis",
            "golf",
            "mma",
        )
    )


def _sport_bucket(card: dict) -> str:
    cat = _category(card)
    if card.get("type") == "tournament" or "golf" in cat:
        return "golf"
    if "hockey" in cat or cat == "nhl":
        return "hockey"
    if "basketball" in cat or cat in ("nba", "ncaab", "wncaab"):
        return "basketball"
    if "football" in cat or cat in ("nfl", "ncaaf"):
        return "football"
    if "baseball" in cat or cat == "mlb":
        return "baseball"
    if "soccer" in cat or cat in ("mls", "epl"):
        return "soccer"
    return cat or str(card.get("type") or "")


def is_weekly_chart(card: dict) -> bool:
    return bool(_WEEKLY_CHART_RE.search(str(card.get("title") or "")))


def resolution_days_until(card: dict, now: Optional[datetime]) -> Optional[float]:
    if now is None:
        return None
    dates: list[datetime] = []
    direct = _when(card.get("resolution_time"))
    if direct is not None:
        dates.append(direct)
    data = (card.get("card") or {}).get("data") or {}
    if not dates:
        fallback = _when(data.get("resolution_date") or data.get("end_date"))
        if fallback is not None:
            dates.append(fallback)
        for member in data.get("items") or []:
            md = (member or {}).get("data") or {}
            mdt = _when(md.get("resolution_date") or md.get("end_date"))
            if mdt is not None:
                dates.append(mdt)
    if not dates:
        return None
    return (min(dates) - now).total_seconds() / 86400.0


def max_dated_move_24h(card: dict) -> float:
    data = (card.get("card") or {}).get("data") or {}
    moves: list[float] = []

    def _scan(mapping: Any) -> None:
        if not isinstance(mapping, dict):
            return
        for key in ("top_outcomes", "outcomes"):
            for outcome in mapping.get(key) or []:
                if not isinstance(outcome, dict):
                    continue
                prob = _num(outcome.get("probability"))
                mv = _num(outcome.get("movement"))
                if mv is None:
                    mv = _num(outcome.get("price_change_24h"))
                if mv is not None and (prob is None or prob >= MOVEMENT_MIN_PROB):
                    moves.append(abs(mv))

    _scan(data)
    for member in data.get("items") or []:
        _scan((member or {}).get("data"))
    return max(moves) if moves else 0.0


def is_live_or_imminent(card: dict, now: Optional[datetime]) -> bool:
    if now is None:
        return False
    kind = card.get("type")
    if kind in ("event", "tournament"):
        start = _when(card.get("start_time"))
        if start is not None:
            hours = (start - now).total_seconds() / 3600.0
            if -6.0 <= hours <= 24.0:
                return True
        if kind == "tournament":
            days = resolution_days_until(card, now)
            if days is not None and 0.0 <= days <= 4.0:
                return True
    return False


def worth_c3(
    card: dict,
    now: Optional[datetime] = None,
    *,
    fun_ids: Optional[frozenset[int]] = None,
) -> float:
    """Candidate 3 worth score (bounded grouped lift, recency, far-horizon
    discount with fun-tagged markets exempt, and mix alignment)."""
    base = (_num(card.get("score")) or 0.0) / 100.0
    fun = is_fun_tagged(card, fun_ids=fun_ids)
    move = max_dated_move_24h(card)
    days = resolution_days_until(card, now)

    # 1. Bounded grouped-card lift; quiet non-fun story bundles do not coast.
    grouped_adj = GROUPED_LIFT if is_grouped(card) else 0.0
    if card.get("type") == "bundle" and not fun and move < MOVEMENT_MIN_ABS:
        story_key = ((card.get("card") or {}).get("data") or {}).get("story_key") or ""
        if story_key and not is_sports(card):
            grouped_adj = STATIC_STORY_BUNDLE_PENALTY

    # 2. Recency & movement (past-date days < 0 earns no near-term credit).
    recency_adj = 0.0
    if move >= MOVEMENT_MIN_ABS:
        recency_adj += min(MOVEMENT_MAX_LIFT, MOVEMENT_BASE_LIFT + move)
    if is_live_or_imminent(card, now):
        recency_adj += LIVE_IMMINENT_LIFT
    if days is not None and 0.0 <= days <= NEAR_RESOLUTION_DAYS:
        recency_adj += NEAR_RESOLUTION_LIFT

    # 3. Far-horizon discount (>60d), fun-tagged markets EXEMPT (Ruling 277: A).
    horizon_adj = 0.0
    if not fun and move < MOVEMENT_MIN_ABS and days is not None:
        if days > VERY_FAR_HORIZON_DAYS:
            horizon_adj = VERY_FAR_HORIZON_DISCOUNT
        elif days > FAR_HORIZON_DAYS:
            horizon_adj = FAR_HORIZON_DISCOUNT

    # 4. Mix alignment toward Alex's target (3 odd, 2.5 entertainment, 0.5 politics).
    mix_adj = 0.0
    if fun:
        mix_adj += FUN_LIFT
    if is_entertainment(card):
        mix_adj += ENTERTAINMENT_LIFT
    if is_politics(card, fun_ids=fun_ids):
        mix_adj += POLITICS_PENALTY

    return round(base + grouped_adj + recency_adj + horizon_adj + mix_adj, 6)


def rank_c3_mix(
    candidates: Iterable[dict],
    *,
    now: Optional[datetime] = None,
    fun_ids: Optional[frozenset[int]] = None,
    long_shot_ids: Optional[frozenset[int]] = None,
) -> list[dict]:
    """Frozen Candidate 3 (``--replay app.utils.discover_rank_c3:rank_c3_mix``)."""
    resolved_fun, resolved_ls = _fun_id_sets(fun_ids=fun_ids, long_shot_ids=long_shot_ids)
    cards = sorted((dict(c) for c in candidates), key=_served_pos)
    if now is None:
        stamps = [t for t in (_when(c.get("price_observed_at")) for c in cards) if t]
        now = max(stamps) if stamps else None

    served = [c for c in cards if _served_pos(c) != math.inf]
    unserved = [c for c in cards if _served_pos(c) == math.inf]

    pool = [c for c in served[:POOL_SIZE] if not fails_gate(c)]
    gated = [c for c in served[:POOL_SIZE] if fails_gate(c)]
    rest = served[POOL_SIZE:]

    # Finished games on page 1 keep their served seat.
    fixed = {
        int(_served_pos(c)) - 1: c
        for c in pool
        if is_finished_game(c) and _served_pos(c) <= PAGE
    }
    movable = sorted(
        (c for c in pool if not (is_finished_game(c) and _served_pos(c) <= PAGE)),
        key=lambda c: (-worth_c3(c, now, fun_ids=resolved_fun), _served_pos(c)),
    )

    seats: list[Optional[dict]] = [None] * len(pool)
    for index, card in fixed.items():
        if index < len(seats):
            seats[index] = card
    leftovers = [c for i, c in fixed.items() if i >= len(seats)]
    queue = leftovers + movable

    entity_counts: dict[str, int] = {}
    sport_counts: dict[str, int] = {}
    fun_count = 0
    long_shot_count = 0
    entertainment_count = 0
    weekly_chart_count = 0
    politics_count = 0
    sports_count = 0

    def _record_opening(chosen: dict) -> None:
        nonlocal fun_count, long_shot_count, entertainment_count, weekly_chart_count
        nonlocal politics_count, sports_count
        for name in _entities(chosen):
            entity_counts[name] = entity_counts.get(name, 0) + 1
        if is_fun_tagged(chosen, fun_ids=resolved_fun):
            fun_count += 1
        if is_long_shot_single(chosen, long_shot_ids=resolved_ls):
            long_shot_count += 1
        if is_entertainment(chosen):
            entertainment_count += 1
        if is_weekly_chart(chosen):
            weekly_chart_count += 1
        if is_politics(chosen, fun_ids=resolved_fun):
            politics_count += 1
        if is_sports(chosen):
            sports_count += 1
            sb = _sport_bucket(chosen)
            sport_counts[sb] = sport_counts.get(sb, 0) + 1

    def _breaks_adjacency(card: dict, prev: Optional[dict], nxt: Optional[dict]) -> bool:
        return is_grouped(card) and (
            (prev is not None and is_grouped(prev)) or (nxt is not None and is_grouped(nxt))
        )

    def _breaks_entities(card: dict) -> bool:
        return any(entity_counts.get(n, 0) >= MAX_ENTITY_REPEATS for n in _entities(card))

    def _breaks_opening_mix(card: dict) -> bool:
        if is_fun_tagged(card, fun_ids=resolved_fun) and fun_count >= MAX_FUN_OPENING:
            return True
        if (
            is_long_shot_single(card, long_shot_ids=resolved_ls)
            and long_shot_count >= MAX_LONG_SHOT_SINGLES_OPENING
        ):
            return True
        if is_entertainment(card) and entertainment_count >= MAX_ENTERTAINMENT_OPENING:
            return True
        if is_weekly_chart(card) and weekly_chart_count >= MAX_WEEKLY_CHART_OPENING:
            return True
        if is_politics(card, fun_ids=resolved_fun):
            if politics_count >= MAX_POLITICS_OPENING:
                return True
            score = _num(card.get("score")) or 0.0
            if score < POLITICS_OPENING_MIN_SCORE and max_dated_move_24h(card) < MOVEMENT_MIN_ABS:
                return True
        if is_sports(card):
            if sports_count >= MAX_SPORTS_OPENING:
                return True
            if sport_counts.get(_sport_bucket(card), 0) >= MAX_PER_SPORT_OPENING:
                return True
        return False

    for index in range(len(seats)):
        if seats[index] is not None:
            if index < OPENING:
                _record_opening(seats[index])  # type: ignore[arg-type]
            continue
        previous = seats[index - 1] if index > 0 else None
        following = seats[index + 1] if index + 1 < len(seats) else None

        pick: Optional[dict] = None
        if index < OPENING:
            # Pass 1: satisfy adjacency, entity repeat, and opening-ten mix caps.
            pick = next(
                (
                    c
                    for c in queue
                    if not _breaks_adjacency(c, previous, following)
                    and not _breaks_entities(c)
                    and not _breaks_opening_mix(c)
                ),
                None,
            )
            # Pass 2: relax mix caps if pool is narrow, keeping adjacency + entity rules.
            if pick is None:
                pick = next(
                    (
                        c
                        for c in queue
                        if not _breaks_adjacency(c, previous, following)
                        and not _breaks_entities(c)
                    ),
                    None,
                )
            # Pass 3: relax adjacency, keeping entity repeat rule.
            if pick is None:
                pick = next((c for c in queue if not _breaks_entities(c)), None)
        else:
            pick = next(
                (c for c in queue if not _breaks_adjacency(c, previous, following)),
                None,
            )

        if pick is None and queue:
            pick = queue[0]
        if pick is None:
            break
        queue.remove(pick)
        seats[index] = pick
        if index < OPENING:
            _record_opening(pick)

    ordered = [c for c in seats if c is not None] + queue
    return ordered + gated + rest + unserved
