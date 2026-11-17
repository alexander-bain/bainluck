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
from collections import Counter
from dataclasses import dataclass

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


def presented_members(
    members: list[dict],
    summaries: dict[int, MarketSummary],
    selected: list[int],
    event_ids: set[int],
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
        row = summaries.get(member["id"])
        if row is not None and row.event_id in event_ids:
            group = row.group(event_ids)
            result.append(
                {**member, "class": "prop" if group == "props" else "side_question"}
            )
        else:
            result.append(member)
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
