"""#11493 — a "which division will the champion come from" leg the grid has put out.

Production, 2026-10-23 07:17Z (main v5887): the Discover card "MLB 2026: World
Series Division Winner" (polymarket 63448360) read NL Central 63% · AL East 37%
· **AL Central <1%**, while ``/api/playoffs/mlb`` marked all five AL Central
clubs ``championship: eliminated``. The venue had already graded NL East, AL
West and NL West ``is_winner false`` — those legs carry no price and leave the
card — but AL Central kept its last quote (0.0005, stamped 19 Oct) because the
venue had not graded it yet. No price can say "out"; the verdict lives only in
the grid build (venue grade, register, the ESPN clinch overlay,
``propagate_elimination``).

So the card reads that verdict from the grid's CACHED payload and drops a
division leg every one of whose clubs is out of the title — exactly how the
venue's own graded divisions already leave it. Three rules keep it honest:

* **Cache only.** A cold grid build is ~12 s; a miss, a timeout or an unusable
  payload is today's answer (every leg stays), never a reason to build.
* **One question.** Only the MLB division-of-the-champion board
  (``baseball:MLB:division_winner:<season>`` whose title names the World
  Series), read against the grid's ``championship`` column. The per-division
  boards in the same key family ("NHL Atlantic Division Winner") have club
  legs, never division labels, so no leg of theirs can match.
* **Fails open on any doubt.** A different season, a club with no
  conference/division that is still alive, or a verdict that would put EVERY
  division out returns nothing to drop.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable

logger = logging.getLogger(__name__)

#: The board this reads: "MLB <season>: World Series Division Winner".
DIVISION_OF_CHAMPION_KEY_PREFIX = "baseball:MLB:division_winner:"

#: The grid league whose ``championship`` column answers that board.
GRID_LEAGUE = "mlb"

#: The column whose verdict decides a division of the champion.
GRID_COLUMN = "championship"

#: How the venue labels a league in a division leg ("AL Central").
_CONFERENCE_ABBR = {"American League": "AL", "National League": "NL"}

#: Cell states that mean the club can no longer win the column. "lost" is the
#: tournament register's word for the same thing.
_OUT_STATES = frozenset({"eliminated", "lost"})


def _norm(label: str | None) -> str:
    return " ".join((label or "").split()).casefold()


def division_of_champion_season(market) -> str | None:
    """The season of an open MLB division-of-the-champion board, else ``None``."""
    if getattr(market, "status", None) != "open":
        return None
    key = getattr(market, "canonical_market_key", None) or ""
    if not key.startswith(DIVISION_OF_CHAMPION_KEY_PREFIX):
        return None
    if "world series" not in (getattr(market, "name", None) or "").casefold():
        return None
    return key[len(DIVISION_OF_CHAMPION_KEY_PREFIX) :] or None


def out_division_labels(payload, season: str | None) -> frozenset[str]:
    """Normalised division labels ("al central") whose every club is out.

    Empty when the payload is absent, names no season or a different one, or
    holds a club that is still alive but carries no conference/division (it
    could belong to any division, so none can be called out).
    """
    if not isinstance(payload, dict) or not season:
        return frozenset()
    grid_season = payload.get("season")
    if not grid_season or str(grid_season) != str(season):
        return frozenset()
    states: dict[str, set[bool]] = {}
    for row in payload.get("teams") or []:
        if not isinstance(row, dict):
            continue
        cell = (row.get("cells") or {}).get(GRID_COLUMN)
        out = isinstance(cell, dict) and cell.get("state") in _OUT_STATES
        abbr = _CONFERENCE_ABBR.get(row.get("conference"))
        division = row.get("division")
        if not abbr or not division:
            if not out:
                return frozenset()
            continue
        states.setdefault(_norm(f"{abbr} {division}"), set()).add(out)
    labels = frozenset(label for label, seen in states.items() if seen == {True})
    if labels and len(labels) == len(states):
        # Every division out is a broken payload, not a finished season — a
        # finished season has a club whose cell reads "won".
        return frozenset()
    return labels


async def read_cached_grid(league_slug: str) -> dict | None:
    """The league's grid payload from Redis, or ``None``. NEVER builds.

    The fresh key first, then the 24 h ``:stale`` mirror only on a clean miss;
    a timeout or error stops at once. Elimination does not reverse inside a
    season, so a last-good payload's "eliminated" is still true — the season
    check in :func:`out_division_labels` keeps last season's verdict off this
    season's board.
    """
    from app.routes.playoffs import _grid_payload_usable
    from app.utils.request_cache import bounded_redis_call, get_shared_async_redis

    cache_key = f"bainluck:category:playoffs:{league_slug}"
    client = await get_shared_async_redis()
    for key in (cache_key, f"{cache_key}:stale"):
        result = await bounded_redis_call(lambda k=key: client.get(k))
        if result.is_failure:
            return None
        if result.is_miss:
            continue
        payload = json.loads(result.value)
        if _grid_payload_usable(payload):
            return payload
    return None


async def out_legs_by_market(markets: Iterable) -> dict[int, frozenset[str]]:
    """``{market id: normalised leg labels to drop}`` for this pool. Never raises.

    Reads Redis only when the pool holds a division-of-the-champion board, and
    at most once per call.
    """
    try:
        seasons = {
            m.id: season for m in markets if (season := division_of_champion_season(m))
        }
        if not seasons:
            return {}
        payload = await read_cached_grid(GRID_LEAGUE)
        out: dict[int, frozenset[str]] = {}
        for market_id, season in seasons.items():
            labels = out_division_labels(payload, season)
            if labels:
                out[market_id] = labels
        return out
    except Exception:
        logger.warning("grid out-legs read failed; every leg stays", exc_info=True)
        return {}


def drop_out_division_legs(outcomes: list, out_labels: frozenset[str] | None) -> list:
    """``outcomes`` without the legs whose label the grid has put out."""
    if not out_labels:
        return outcomes
    return [o for o in outcomes if _norm(getattr(o, "name", None)) not in out_labels]
