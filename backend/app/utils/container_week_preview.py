"""Bounded presentation of an NFL week's published market membership.

Games are never capped. Market selection reads existing activity fields, not
outcomes: at most twelve boards are hydrated on entry. Continuation walks IDs
from the same membership revision, excluding the initial picks, so changing
activity ranks cannot skip or repeat a board halfway through a visit.
"""

from __future__ import annotations

import base64
import binascii
import json
import math
from collections import Counter
from dataclasses import asdict, dataclass

from app.utils.container_read_cache import CONTAINER_READ_FRESH_TTL_SECONDS
from app.utils.game_market_class import classify_game_market_class

PREVIEW_LIMIT = 12
PER_GAME_LIMIT = 2
PAGE_DEFAULT = 50
PAGE_MAX = 100


@dataclass(frozen=True)
class MarketSummary:
    id: int
    event_id: int | None
    name: str
    external_id: str | None
    volume_24h: int | None
    volume: int | None

    def group(self, event_ids: set[int]) -> str:
        if self.event_id not in event_ids:
            return "futures"
        kind = classify_game_market_class(self.name or "", self.external_id)
        return "props" if kind == "player_prop" else "game_markets"

    def rank(self) -> tuple:
        return (-max(self.volume_24h or 0, 0), -max(self.volume or 0, 0), self.id)


def ranked_preview(rows: list[MarketSummary], event_ids: set[int]) -> list[int]:
    """Give each available group seats, then fill by activity; max two/game."""
    ranked = sorted({row.id: row for row in rows}.values(), key=lambda row: row.rank())
    picked: list[int] = []
    by_game: Counter = Counter()

    def take(row: MarketSummary) -> bool:
        if row.id in picked or len(picked) >= PREVIEW_LIMIT:
            return False
        if row.event_id in event_ids and by_game[row.event_id] >= PER_GAME_LIMIT:
            return False
        picked.append(row.id)
        if row.event_id in event_ids:
            by_game[row.event_id] += 1
        return True

    for group in ("props", "futures", "game_markets"):
        count = 0
        for row in ranked:
            if row.group(event_ids) == group and take(row):
                count += 1
                if count == 4:
                    break
    for row in ranked:
        take(row)
    return picked


@dataclass(frozen=True)
class WeekMarketPreview:
    """The price-free part of the first page, before game-card hydration."""

    selected: list[int]
    related_by_event: dict[int, int]
    unclassified_by_event: dict[int, int]
    classes_by_market: dict[int, str]


@dataclass(frozen=True)
class PreparedWeekMarketPreview:
    observed_at: float
    plan: WeekMarketPreview

    def encode(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"))


def prepared_week_preview_key(response_key: str) -> str:
    return f"{response_key}:week-preview-v1"


def decode_prepared_week_preview(
    raw: bytes | str | None, now: float,
) -> PreparedWeekMarketPreview | None:
    # A malformed or expired derivative has the same fallback as a missing one.
    if not raw or len(raw) > 16_384:
        return None
    try:
        payload = json.loads(raw)
        clock = payload["observed_at"]
        plan = payload["plan"]
        selected = plan["selected"]
        related = {int(k): v for k, v in plan["related_by_event"].items()}
        unclassified = {int(k): v for k, v in plan["unclassified_by_event"].items()}
        classes = {int(k): v for k, v in plan["classes_by_market"].items()}
    except (AttributeError, KeyError, TypeError, ValueError):
        return None
    if (
        type(clock) not in (int, float) or not math.isfinite(clock)
        or not 0 <= now - clock < CONTAINER_READ_FRESH_TTL_SECONDS
        or not isinstance(selected, list) or len(selected) > PREVIEW_LIMIT
        or any(type(mid) is not int or mid <= 0 for mid in selected)
        or len(set(selected)) != len(selected)
        or any(eid <= 0 or type(count) is not int or count <= 0 for eid, count in related.items())
        or any(type(count) is not int or not 0 < count <= related.get(eid, 0)
               for eid, count in unclassified.items())
        or not set(classes).issubset(selected)
        or any(kind not in ("prop", "side_question") for kind in classes.values())
    ):
        return None
    return PreparedWeekMarketPreview(
        clock, WeekMarketPreview(selected, related, unclassified, classes)
    )


def plan_market_preview(
    members: list[dict], summaries: dict[int, MarketSummary], event_ids: set[int]
) -> WeekMarketPreview:
    from app.utils.container_graph import CLASS_UNCLASSIFIED

    selected = ranked_preview(list(summaries.values()), event_ids)
    deferred = set(summaries).difference(selected)
    related_by_event = Counter(
        summaries[market_id].event_id for market_id in deferred
        if summaries[market_id].event_id in event_ids
    )
    unclassified_ids = {
        member["id"] for member in members
        if member["type"] == "market" and member["id"] in deferred
        and (member.get("class") or CLASS_UNCLASSIFIED) == CLASS_UNCLASSIFIED
    }
    unclassified_by_event = Counter(
        summaries[market_id].event_id for market_id in unclassified_ids
        if summaries[market_id].event_id in event_ids
    )
    return WeekMarketPreview(
        selected, dict(related_by_event), dict(unclassified_by_event),
        market_member_classes(summaries, selected, event_ids),
    )


def market_member_classes(
    summaries: dict[int, MarketSummary], selected: list[int], event_ids: set[int]
) -> dict[int, str]:
    classes = {}
    for market_id in selected:
        row = summaries.get(market_id)
        if row is not None and row.event_id in event_ids:
            classes[market_id] = "prop" if row.group(event_ids) == "props" else "side_question"
    return classes


def presented_members(
    members: list[dict],
    selected: list[int],
    classes_by_market: dict[int, str],
) -> list[dict]:
    """Use the shared game classifier for linked derivatives, never 'Title'."""
    result = []
    markets = {}
    for member in members:
        if member["type"] != "market":
            result.append(member)
        else:
            markets.setdefault(member["id"], member)
    for mid in selected:
        member = markets[mid]
        kind = classes_by_market.get(mid)
        result.append({**member, "class": kind} if kind else member)
    return result


def encode_cursor(
    container_id: int, revision: int, own: bool, after: int, excluded: list[int]
) -> str:
    raw = json.dumps(
        [container_id, revision, own, after, sorted(excluded)], separators=(",", ":")
    )
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(value: str) -> tuple[int, int, bool, int, list[int]] | None:
    if not isinstance(value, str) or len(value) > 512:
        return None
    try:
        data = json.loads(base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)))
    except (binascii.Error, ValueError, UnicodeDecodeError):
        return None
    if not isinstance(data, list) or len(data) != 5:
        return None
    cid, revision, own, after, excluded = data
    if (
        any(type(v) is not int or v < 0 for v in (cid, revision, after))
        or type(own) is not bool
        or not isinstance(excluded, list)
        or len(excluded) > PREVIEW_LIMIT
        or any(type(v) is not int or v <= 0 for v in excluded)
        or len(set(excluded)) != len(excluded)
    ):
        return None
    return cid, revision, own, after, excluded
