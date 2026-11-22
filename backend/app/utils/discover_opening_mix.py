"""Discover opening-ten 9:1 + topic-mix seating rule (#13400, Decision 329: A).

Composes seats 1..10 of the Discover deck for ``machinery=1`` readers:
* Target ~9 grouped cards to 1 single futures market across seats 1..10.
* Topic mix across the 10 seats (Alex + Fable 6:30 PM PT):
  - ~3 ``odd`` (max 3; pure ``ODD`` cards ahead of weather/novelty fallbacks)
  - 2..3 ``entertainment``
  - 2 ``sports`` (including any non-conflict sports single if chosen)
  - 1..2 ``tech_business``
  - <= 1 across ``politics``, ``world``, and ``money`` combined (never Seat 1)
* The 1 single futures card is chosen from ``odd``, ``entertainment``,
  ``sports``, or ``tech_business`` (never a conflict/politics/world/money
  market unless nothing else qualifies) and does not duplicate a covered market.
* Concept cards (``type == "concept"``) are never pinned or promoted.
* No live game (nor any grouped card wrapping a live game) enters seats 1..10.
* Grouped cards may sit adjacent inside seats 1..10; Decision 123-A
  non-adjacency for round-up cards still holds from seat 11 onward (index >= 10).
"""

from __future__ import annotations

import copy
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from app.utils.discover_opening_seating import (
    EVENT_LIVE_STATUSES,
    classify_card,
)
from app.utils.roundup_containers import (
    ROUNDUP_PRODUCERS,
    _CLIENT_SPORT_CATEGORIES,
    _is_grouped_feed_card,
    _is_near_identical_sibling_family,
    _is_roundup_bundle_card,
    _is_roundup_opening_eligible,
    _is_sibling_family_bundle,
    _prune_bundles_below_roundups,
    _roundup_covered_market_ids,
    _roundup_item_slug,
)

OPENING_MIX_SIZE = 10
OPENING_MIX_GROUPED_TARGET = 9
OPENING_MIX_SINGLE_CAP = 1
OPENING_MIX_DEFAULT_SINGLE_SEAT = 4  # 0-based index -> seat 5

TOPIC_ODD = "odd"
TOPIC_ENTERTAINMENT = "entertainment"
TOPIC_SPORTS = "sports"
TOPIC_TECH_BUSINESS = "tech_business"
TOPIC_PWM = "politics_world_money"

NON_PWM_TOPICS: tuple[str, ...] = (
    TOPIC_ODD,
    TOPIC_ENTERTAINMENT,
    TOPIC_SPORTS,
    TOPIC_TECH_BUSINESS,
)
ALL_OPENING_TOPICS: tuple[str, ...] = (*NON_PWM_TOPICS, TOPIC_PWM)

TOPIC_MAX_TOTAL: dict[str, int] = {
    TOPIC_ODD: 3,
    TOPIC_ENTERTAINMENT: 3,
    TOPIC_SPORTS: 2,
    TOPIC_TECH_BUSINESS: 2,
    TOPIC_PWM: 1,
}

TOPIC_MIN_GROUPS: dict[str, int] = {
    TOPIC_ODD: 2,
    TOPIC_ENTERTAINMENT: 2,
    TOPIC_SPORTS: 1,  # Leaves headroom for a standout sports single (e.g. Super Bowl) -> total 2 sports
    TOPIC_TECH_BUSINESS: 1,
}

_PURE_ODD_SLUGS: frozenset[str] = frozenset(
    {
        "machinery-elon-musk-side-quests",
        "machinery-long-shots",
    }
)
_ODD_SLUGS: frozenset[str] = frozenset(
    {
        *_PURE_ODD_SLUGS,
        "machinery-white-christmas",
        "roundup-tomorrows-highs",
        "roundup-will-it-snow",
        "for-scale-snow-in-dc",
    }
)
_ENTERTAINMENT_SLUGS: frozenset[str] = frozenset(
    {
        "machinery-2026-summed-up",
        "machinery-who-gets-engaged",
        "machinery-next-james-bond",
        "machinery-stage-and-cover",
        "machinery-oscars-best-picture",
        "machinery-cast-delayed-cancelled",
        "machinery-game-awards-2026",
        "machinery-long-awaited",
        "roundup-opening-weekend",
        "gta-vi-album-features",
    }
)
_SPORTS_SLUGS: frozenset[str] = frozenset(
    {
        "machinery-big-championships-2027",
        "machinery-nba-night",
        "machinery-nfl-week",
        "roundup-cfp-picture",
        "roundup-nfl-division-front-runners",
        "roundup-closest-games-tonight",
        "liga-profesional-relegation-2026",
        "nhl-playoffs-2026-27",
        "golf-this-week",
        "celtics-next-3-games",
        "lakers-next-3-games",
    }
)
_TECH_BUSINESS_SLUGS: frozenset[str] = frozenset(
    {
        "machinery-ai-and-big-tech-race",
        "machinery-space-race",
        "machinery-unsolved-big-problems",
        "by-november-30",
        "who-announces-before-2027",
    }
)
_PWM_SLUGS: frozenset[str] = frozenset(
    {
        "machinery-2028-presidential",
        "machinery-fed-and-macro",
        "for-scale-us-recession-2026",
        "by-december-31",
    }
)

_CONFLICT_PWM_KEYWORDS: tuple[str, ...] = (
    "ceasefire",
    "invade",
    "invasion",
    "military strike",
    "strike on",
    "missile",
    "nuclear weapon",
    "nato",
    "ukraine",
    "russia",
    "iran",
    "israel",
    "gaza",
    "hamas",
    "hezbollah",
    "taiwan",
    "war ",
    "conflict",
    "sanctions",
    "prime minister",
    "election",
    "presidential",
    "nominee",
    "congress",
    "senate",
    "recession",
    "fed ",
    "fomc",
    "interest rate",
    "rate cut",
    "inflation",
    "tariff",
    "treasury",
    "trump",
    "biden",
    "spain",
)

_ODD_SINGLE_KEYWORDS: tuple[str, ...] = (
    "alien",
    "ufo",
    "uap",
    "white christmas",
    "bigfoot",
    "loch ness",
)

_TITLE_STOPWORDS: frozenset[str] = frozenset(
    {
        "will",
        "with",
        "what",
        "which",
        "when",
        "where",
        "the",
        "and",
        "for",
        "from",
        "into",
        "that",
        "this",
        "most",
        "more",
        "than",
        "odds",
        "hit",
        "end",
        "2026",
        "2027",
        "december",
        "november",
        "before",
        "after",
    }
)

_PWM_CATEGORIES: frozenset[str] = frozenset(
    {"politics", "geopolitics", "economics", "world", "money", "macro"}
)
_ENTERTAINMENT_CATEGORIES: frozenset[str] = frozenset(
    {"entertainment", "culture", "movies", "music", "tv", "awards"}
)
_TECH_CATEGORIES: frozenset[str] = frozenset(
    {"tech", "business", "finance", "science", "space", "ai"}
)
_SPORTS_CATEGORIES: frozenset[str] = frozenset(_CLIENT_SPORT_CATEGORIES | {"sports"})


def _card_title(item: Mapping[str, Any]) -> str:
    data = item.get("data")
    if not isinstance(data, Mapping):
        return str(item.get("headline") or "")
    return str(
        data.get("title")
        or data.get("name")
        or data.get("question")
        or item.get("headline")
        or data.get("id")
        or ""
    )


def _card_slug(item: Mapping[str, Any]) -> str:
    slug = _roundup_item_slug(item)
    if slug:
        return slug
    data = item.get("data")
    if isinstance(data, Mapping):
        return str(data.get("slug") or "")
    return ""


def _title_tokens(item: Mapping[str, Any]) -> set[str]:
    raw = _card_title(item).lower()
    words = ["".join(ch for ch in w if ch.isalnum()) for w in raw.split()]
    return {w for w in words if len(w) >= 4 and w not in _TITLE_STOPWORDS}


def is_pure_odd_grouped_card(item: Mapping[str, Any]) -> bool:
    """Return True for genuinely weird/novelty ``ODD`` grouped cards (before weather fallbacks)."""
    slug = _card_slug(item).lower()
    if slug in _PURE_ODD_SLUGS:
        return True
    data = item.get("data")
    roundup = data.get("roundup") if isinstance(data, Mapping) else None
    kicker = (
        str(roundup.get("kicker") or "").strip().lower()
        if isinstance(roundup, Mapping)
        else ""
    )
    if not kicker and slug in ROUNDUP_PRODUCERS:
        kicker = str(ROUNDUP_PRODUCERS[slug].kicker or "").strip().lower()
    return kicker.startswith("odd ")


def classify_discover_opening_topic(item: Mapping[str, Any]) -> str:
    """Classify a Discover feed card into one of the 5 opening-mix topic buckets."""
    data = item.get("data") if isinstance(item.get("data"), Mapping) else {}
    slug = _card_slug(item).lower()
    raw_id = str(data.get("id") or "").strip().lower()
    story_key = str(data.get("story_key") or item.get("story_key") or "").strip().lower()
    roundup = data.get("roundup") if isinstance(data.get("roundup"), Mapping) else {}
    kicker = str(roundup.get("kicker") or "").strip().lower()
    tag = str(roundup.get("tag") or "").strip().lower()
    title = _card_title(item).lower()

    prod = ROUNDUP_PRODUCERS.get(slug) if slug else None
    prod_cat = str(getattr(prod, "category", "") or "").strip().lower()
    if not kicker and prod is not None:
        kicker = str(getattr(prod, "kicker", "") or "").strip().lower()

    if _is_grouped_feed_card(item):
        if (
            slug in _ODD_SLUGS
            or kicker.startswith(("odd ", "weather "))
            or prod_cat in ("odd", "weather")
            or tag in ("odd", "weather")
        ):
            return TOPIC_ODD
        if slug in _PWM_SLUGS or kicker.startswith(("politics", "economics", "world")):
            return TOPIC_PWM
        if (
            slug in _ENTERTAINMENT_SLUGS
            or kicker.startswith(("entertainment", "culture", "the oscars"))
            or prod_cat in _ENTERTAINMENT_CATEGORIES
            or tag in _ENTERTAINMENT_CATEGORIES
            or "oscars" in kicker
            or "oscars" in story_key
            or "oscars" in raw_id
        ):
            return TOPIC_ENTERTAINMENT
        if (
            slug in _SPORTS_SLUGS
            or prod_cat in _SPORTS_CATEGORIES
            or tag in _SPORTS_CATEGORIES
            or any(
                k in kicker
                for k in ("sports", "nba", "nfl", "nhl", "mlb", "soccer", "golf")
            )
        ):
            return TOPIC_SPORTS
        if (
            slug in _TECH_BUSINESS_SLUGS
            or kicker.startswith(("tech", "business", "science"))
            or prod_cat in _TECH_CATEGORIES
            or tag in _TECH_CATEGORIES
            or raw_id.startswith(("theme:story:ai", "theme:story:ipo", "comparison:ipo"))
            or story_key in ("ai", "story:ai", "story:ipo_markets")
            or slug == "ai"
        ):
            return TOPIC_TECH_BUSINESS
        if (
            prod_cat in _PWM_CATEGORIES
            or tag in _PWM_CATEGORIES
            or "conflict" in story_key
            or "macro" in story_key
            or "rates" in story_key
            or "election" in story_key
        ):
            return TOPIC_PWM
        if any(k in title for k in _CONFLICT_PWM_KEYWORDS):
            return TOPIC_PWM
        return TOPIC_PWM

    cat = str(data.get("llm_sport_category") or data.get("category") or "").strip().lower()
    # Conflict / geopolitics / macro / politics keywords take precedence over
    # generic categories so war/election markets never enter as the non-conflict single.
    if cat in _PWM_CATEGORIES or any(k in title for k in _CONFLICT_PWM_KEYWORDS):
        return TOPIC_PWM
    if cat in ("weather", "health", "odd") or any(k in title for k in _ODD_SINGLE_KEYWORDS):
        return TOPIC_ODD
    if cat in _ENTERTAINMENT_CATEGORIES:
        return TOPIC_ENTERTAINMENT
    if cat in _SPORTS_CATEGORIES:
        return TOPIC_SPORTS
    if cat in _TECH_CATEGORIES:
        return TOPIC_TECH_BUSINESS
    return TOPIC_PWM


def is_conflict_or_pwm_card(item: Mapping[str, Any]) -> bool:
    """Return True when ``item`` belongs to conflict / politics / world / money."""
    return classify_discover_opening_topic(item) == TOPIC_PWM


def _contains_live_event_signal(item: Mapping[str, Any], *, now: datetime) -> bool:
    """Return True when ``item`` itself is live or carries any live child event."""
    if classify_card(dict(item), now=now).restricted:
        return True
    data = item.get("data")
    if not isinstance(data, Mapping):
        return False
    status = str(data.get("status") or "").strip().lower()
    if status in EVENT_LIVE_STATUSES and item.get("type") in ("event", "bundle"):
        return True
    for child in data.get("items") or ():
        if not isinstance(child, Mapping):
            continue
        if child.get("type") == "event":
            cdata = child.get("data")
            cstatus = (
                str(cdata.get("status") or "").strip().lower()
                if isinstance(cdata, Mapping)
                else ""
            )
            if cstatus in EVENT_LIVE_STATUSES or classify_card(dict(child), now=now).restricted:
                return True
    return False


def _grouped_priority_key(
    pair: tuple[int, dict[str, Any]],
) -> tuple[int, float, int]:
    """Non-circular priority within a topic bucket (independent of hydrated scores)."""
    idx, item = pair
    topic = classify_discover_opening_topic(item)
    non_pure_odd = 0 if (topic != TOPIC_ODD or is_pure_odd_grouped_card(item)) else 1
    data = item.get("data") if isinstance(item.get("data"), Mapping) else {}
    if data.get("kind") == "theme":
        return (non_pure_odd, -float(item.get("score") or 0.0), idx)
    return (non_pure_odd, 0.0, idx)


def _clear_opening_mix_marker(card: Mapping[str, Any]) -> dict[str, Any]:
    data = card.get("data")
    roundup = data.get("roundup") if isinstance(data, Mapping) else None
    has_flag = (isinstance(data, Mapping) and "opening_mix_seat" in data) or (
        isinstance(roundup, Mapping) and "opening_mix_seat" in roundup
    )
    if not has_flag:
        return card if isinstance(card, dict) else dict(card)
    out = copy.deepcopy(dict(card))
    out_data = out.get("data")
    if isinstance(out_data, dict):
        out_data.pop("opening_mix_seat", None)
        out_roundup = out_data.get("roundup")
        if isinstance(out_roundup, dict):
            out_roundup.pop("opening_mix_seat", None)
    return out


def _mark_opening_mix_card(
    card: Mapping[str, Any],
    *,
    anchor: Optional[Mapping[str, Any]],
) -> dict[str, Any]:
    out = copy.deepcopy(dict(card))
    if not out.get("score") and isinstance(anchor, Mapping):
        out["score"] = float(anchor.get("score", 0.0) or 0.0)
        if "_rank_score" in anchor and "_rank_score" not in out:
            out["_rank_score"] = anchor["_rank_score"]
        if "_sort_time" in anchor and "_sort_time" not in out:
            out["_sort_time"] = anchor["_sort_time"]
    if _is_roundup_bundle_card(out) and isinstance(out.get("data"), dict):
        out["data"]["opening_mix_seat"] = True
        if isinstance(out["data"].get("roundup"), dict):
            out["data"]["roundup"]["opening_mix_seat"] = True
    return out


def _enforce_post_opening_non_adjacency(remainder: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Preserve Decision 123-A non-adjacency for round-up cards from seat 11 onward."""
    items = list(remainder)
    idx = 1
    while idx < len(items):
        if _is_roundup_bundle_card(items[idx - 1]) and _is_roundup_bundle_card(items[idx]):
            swap_at: Optional[int] = None
            for probe in range(idx + 1, len(items)):
                if not _is_roundup_bundle_card(items[probe]):
                    swap_at = probe
                    break
            if swap_at is None:
                break
            non_roundup = items.pop(swap_at)
            items.insert(idx, non_roundup)
        idx += 1
    return items


def _order_opening_ten(
    grouped_pairs: list[tuple[int, dict[str, Any]]],
    single_pairs: list[tuple[int, dict[str, Any]]],
    *,
    seat_count: int,
    anchor: Optional[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Arrange selected opening cards across seats 1..10.

    - Seat 1 is never conflict / politics / world / money unless nothing else exists.
    - Pure ODD leads Seat 1 when present.
    - Remaining non-PWM groups alternate across topics where possible.
    - At-most-1 PWM card sits near the back of seats 1..10.
    - Single futures card is interleaved cleanly inside seats 1..10 (default around seat 5).
    """
    non_pwm_groups = [p for p in grouped_pairs if classify_discover_opening_topic(p[1]) != TOPIC_PWM]
    pwm_groups = [p for p in grouped_pairs if classify_discover_opening_topic(p[1]) == TOPIC_PWM]
    non_pwm_singles = [p for p in single_pairs if classify_discover_opening_topic(p[1]) != TOPIC_PWM]
    pwm_singles = [p for p in single_pairs if classify_discover_opening_topic(p[1]) == TOPIC_PWM]

    # Seat 1: pure ODD -> ODD -> entertainment -> tech_business -> sports -> fallback
    first_group: Optional[tuple[int, dict[str, Any]]] = None
    for pred in (
        lambda it: is_pure_odd_grouped_card(it),
        lambda it: classify_discover_opening_topic(it) == TOPIC_ODD,
        lambda it: classify_discover_opening_topic(it) == TOPIC_ENTERTAINMENT,
        lambda it: classify_discover_opening_topic(it) == TOPIC_TECH_BUSINESS,
        lambda it: classify_discover_opening_topic(it) == TOPIC_SPORTS,
    ):
        match = next((p for p in non_pwm_groups if pred(p[1])), None)
        if match is not None:
            first_group = match
            break

    remaining_non_pwm = [p for p in non_pwm_groups if first_group is None or p[0] != first_group[0]]
    interleaved: list[tuple[int, dict[str, Any]]] = [first_group] if first_group is not None else []
    pool = list(remaining_non_pwm)
    while pool:
        last_topic = classify_discover_opening_topic(interleaved[-1][1]) if interleaved else ""
        pick_idx = next(
            (i for i, (_, it) in enumerate(pool) if classify_discover_opening_topic(it) != last_topic),
            0,
        )
        interleaved.append(pool.pop(pick_idx))

    ordered_groups = interleaved + pwm_groups
    ordered_singles = non_pwm_singles + pwm_singles

    # Interleave the single card(s) cleanly inside seats 1..10 without taking Seat 1
    # when any non-PWM group is available.
    opening_pairs: list[tuple[int, dict[str, Any]]] = list(ordered_groups)
    for offset_idx, s_pair in enumerate(ordered_singles):
        target_pos = min(OPENING_MIX_DEFAULT_SINGLE_SEAT + offset_idx * 2, len(opening_pairs))
        if not ordered_groups:
            target_pos = min(offset_idx, len(opening_pairs))
        else:
            target_pos = max(1, target_pos)
            # Nudge by +/- 1 if adjacent group shares the same topic
            s_topic = classify_discover_opening_topic(s_pair[1])
            for cand_pos in (target_pos, target_pos - 1, target_pos + 1):
                if 1 <= cand_pos <= len(opening_pairs):
                    left_t = classify_discover_opening_topic(opening_pairs[cand_pos - 1][1])
                    right_t = (
                        classify_discover_opening_topic(opening_pairs[cand_pos][1])
                        if cand_pos < len(opening_pairs)
                        else ""
                    )
                    if s_topic != left_t and s_topic != right_t:
                        target_pos = cand_pos
                        break
        opening_pairs.insert(target_pos, s_pair)

    return [
        _mark_opening_mix_card(it, anchor=anchor)
        for _, it in opening_pairs[:seat_count]
    ]


def apply_discover_opening_mix(
    items: list[dict[str, Any]],
    *,
    now: Optional[datetime] = None,
    seat_count: int = OPENING_MIX_SIZE,
    page_window: int = 20,
) -> list[dict[str, Any]]:
    """Compose Discover seats 1..10 under Decision 329: A (9G:1S + topic mix).

    Returns ``items`` unchanged when the deck has ``<= seat_count`` cards or no
    opening-eligible grouped cards. Never pins ``concept`` cards and never puts a
    live event (or live-wrapping grouped card) into seats 1..10.
    """
    if not items or len(items) <= seat_count:
        return items

    effective_now = (
        now
        if isinstance(now, datetime) and now.tzinfo is not None
        else datetime.now(timezone.utc)
    )

    eligible_groups: list[tuple[int, dict[str, Any]]] = [
        (idx, it)
        for idx, it in enumerate(items)
        if isinstance(it, Mapping)
        and _is_grouped_feed_card(it)
        and it.get("type") != "concept"
        and not _contains_live_event_signal(it, now=effective_now)
        and _is_roundup_opening_eligible(it, items, now=effective_now)
    ]
    if not eligible_groups:
        return items

    # Identify all single futures candidates eligible for opening seats
    raw_singles: list[tuple[int, dict[str, Any]]] = [
        (idx, it)
        for idx, it in enumerate(items)
        if isinstance(it, Mapping)
        and not _is_grouped_feed_card(it)
        and it.get("type") == "futures"
        and not classify_card(dict(it), now=effective_now).restricted
    ]
    non_pwm_singles = [p for p in raw_singles if classify_discover_opening_topic(p[1]) != TOPIC_PWM]
    singles_pool = non_pwm_singles if non_pwm_singles else raw_singles
    singles_sorted = sorted(
        singles_pool,
        key=lambda pair: (-float(pair[1].get("score") or 0.0), pair[0]),
    )

    sorted_groups = sorted(eligible_groups, key=_grouped_priority_key)
    grouped_target = min(OPENING_MIX_GROUPED_TARGET, seat_count - (1 if singles_sorted else 0))

    chosen_groups: list[tuple[int, dict[str, Any]]] = []
    chosen_indices: set[int] = set()
    seen_sibling_groups: list[Mapping[str, Any]] = []
    topic_counts: Counter[str] = Counter()

    def _can_take_group(it: Mapping[str, Any], limit_map: Mapping[str, int]) -> bool:
        t = classify_discover_opening_topic(it)
        if topic_counts[t] >= limit_map.get(t, 0):
            return False
        if _is_sibling_family_bundle(it) and any(
            _is_near_identical_sibling_family(it, prev) for prev in seen_sibling_groups
        ):
            return False
        return True

    def _add_group(idx: int, it: dict[str, Any]) -> None:
        chosen_groups.append((idx, it))
        chosen_indices.add(idx)
        topic_counts[classify_discover_opening_topic(it)] += 1
        if _is_sibling_family_bundle(it):
            seen_sibling_groups.append(it)

    # Pass 1a: fill per-topic minimum group targets across non-PWM topics.
    for topic in NON_PWM_TOPICS:
        target_min = TOPIC_MIN_GROUPS[topic]
        for idx, it in sorted_groups:
            if len(chosen_groups) >= grouped_target:
                break
            if idx in chosen_indices or classify_discover_opening_topic(it) != topic:
                continue
            if topic_counts[topic] >= target_min:
                break
            if _can_take_group(it, TOPIC_MAX_TOTAL):
                _add_group(idx, it)

    # Pass 1b: fill up to `max(grouped_target - 1, 8)` non-PWM grouped slots, leaving
    # headroom so the top non-conflict single can claim its topic slot.
    non_pwm_group_cap = max(0, grouped_target - 1)
    for topic in (TOPIC_ODD, TOPIC_ENTERTAINMENT, TOPIC_TECH_BUSINESS, TOPIC_SPORTS):
        for idx, it in sorted_groups:
            if len(chosen_groups) >= non_pwm_group_cap:
                break
            if idx in chosen_indices or classify_discover_opening_topic(it) != topic:
                continue
            if _can_take_group(it, TOPIC_MAX_TOTAL):
                _add_group(idx, it)

    # Pick the single futures card(s) needed to reach `seat_count` alongside up to
    # `grouped_target` groups (1 under normal supply).
    covered_ids: set[int] = set()
    grouped_tokens: list[set[str]] = []
    for _, git in chosen_groups:
        grouped_tokens.append(_title_tokens(git))
        covered_ids.update(_roundup_covered_market_ids(git))

    def _single_fits(it: Mapping[str, Any], *, strict_max: bool) -> bool:
        data = it.get("data")
        did = data.get("id") if isinstance(data, Mapping) else None
        if isinstance(did, int) and did in covered_ids:
            return False
        toks = _title_tokens(it)
        if any(len(toks & gtoks) >= 2 for gtoks in grouped_tokens):
            return False
        t = classify_discover_opening_topic(it)
        if strict_max and topic_counts[t] >= TOPIC_MAX_TOTAL[t]:
            return False
        return True

    chosen_singles: list[tuple[int, dict[str, Any]]] = []
    if singles_sorted:
        for strict in (True, False):
            for idx, it in singles_sorted:
                if idx in chosen_indices:
                    continue
                if classify_discover_opening_topic(it) == TOPIC_PWM and strict:
                    continue
                if _single_fits(it, strict_max=strict):
                    chosen_singles.append((idx, it))
                    chosen_indices.add(idx)
                    topic_counts[classify_discover_opening_topic(it)] += 1
                    break
            if chosen_singles:
                break

    single_ids = {
        it["data"]["id"]
        for _, it in chosen_singles
        if isinstance(it.get("data"), Mapping) and isinstance(it["data"].get("id"), int)
    }
    single_tokens: list[set[str]] = [_title_tokens(it) for _, it in chosen_singles]

    # Pass 2: complete up to `grouped_target` grouped cards (non-PWM within caps -> <=1 PWM -> relaxed non-PWM).
    relaxed_non_pwm_caps = {
        TOPIC_ODD: 4,
        TOPIC_ENTERTAINMENT: 4,
        TOPIC_SPORTS: 3,
        TOPIC_TECH_BUSINESS: 3,
        TOPIC_PWM: 1,
    }
    for allowed_topics, limit_map in (
        (NON_PWM_TOPICS, TOPIC_MAX_TOTAL),
        ((TOPIC_PWM,), TOPIC_MAX_TOTAL),
        (NON_PWM_TOPICS, relaxed_non_pwm_caps),
        (ALL_OPENING_TOPICS, relaxed_non_pwm_caps),
    ):
        if len(chosen_groups) >= grouped_target:
            break
        for idx, it in sorted_groups:
            if len(chosen_groups) >= grouped_target:
                break
            if idx in chosen_indices:
                continue
            if classify_discover_opening_topic(it) not in allowed_topics:
                continue
            if single_ids and (_roundup_covered_market_ids(it) & single_ids):
                continue
            if single_tokens and any(
                len(_title_tokens(it) & stoks) >= 2 for stoks in single_tokens
            ):
                continue
            if _can_take_group(it, limit_map):
                _add_group(idx, it)

    # If grouped supply was below `grouped_target`, fill remaining opening seats with
    # non-PWM singles first while honoring PWM <= 1.
    needed_singles = seat_count - len(chosen_groups) - len(chosen_singles)
    if needed_singles > 0:
        for pass_non_pwm_only in (True, False):
            if needed_singles <= 0:
                break
            for idx, it in singles_sorted:
                if needed_singles <= 0:
                    break
                if idx in chosen_indices:
                    continue
                t = classify_discover_opening_topic(it)
                if pass_non_pwm_only and t == TOPIC_PWM:
                    continue
                if t == TOPIC_PWM and topic_counts[TOPIC_PWM] >= TOPIC_MAX_TOTAL[TOPIC_PWM]:
                    continue
                data = it.get("data")
                did = data.get("id") if isinstance(data, Mapping) else None
                if isinstance(did, int) and did in covered_ids:
                    continue
                chosen_singles.append((idx, it))
                chosen_indices.add(idx)
                topic_counts[t] += 1
                needed_singles -= 1

    # Fallback: if we still couldn't fill `seat_count` (e.g. non-PWM + PWM cap reached on tiny deck),
    # let caller's original deck fill naturally without promoting any live/concept card.
    anchor = items[0] if items else None
    opening = _order_opening_ten(
        chosen_groups,
        chosen_singles,
        seat_count=seat_count,
        anchor=anchor,
    )
    if len(opening) < seat_count:
        for idx, it in enumerate(items):
            if len(opening) >= seat_count:
                break
            if idx in chosen_indices or it.get("type") == "concept":
                continue
            if _contains_live_event_signal(it, now=effective_now):
                continue
            chosen_indices.add(idx)
            opening.append(_mark_opening_mix_card(it, anchor=anchor))

    remainder = [
        _clear_opening_mix_marker(it) if _is_roundup_bundle_card(it) else it
        for idx, it in enumerate(items)
        if idx not in chosen_indices
    ]
    remainder = _enforce_post_opening_non_adjacency(remainder)

    combined = [*opening, *remainder]
    opening_roundup_ids = {
        card["data"].get("id")
        for card in opening
        if isinstance(card, Mapping)
        and isinstance(card.get("data"), Mapping)
        and card["data"].get("id") is not None
    }
    if opening_roundup_ids:
        combined = _prune_bundles_below_roundups(combined, opening_roundup_ids)
    return combined
