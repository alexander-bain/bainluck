"""Ruling 188 (#11937): a market nobody is trading never takes a Discover seat.

Alex, Nov 13: "If they're stale because of illiquid trading, we just shouldn't
be featuring the market."

The test needs no schema change: a market is NOT TRADING when

* none of its prices has moved for ``QUIET_DAYS`` (the newest
  ``futures_outcomes.price_changed_at`` across its legs, which every price poll
  maintains — #2024), and
* the venue reports no 24-hour volume for it (``futures_markets.volume_24h`` is
  zero, or the venue does not report one).

A market with ANY recent volume is trading, whatever its price did. A market
with no price stamp at all is unknown and is never refused (gotcha #53): the
rule removes only what it can show is dead.

#12694 adds a column that dates the quiet spell from the volume itself; it
waits for Alex. This version is the one that ships without it.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta
from typing import Any, Optional

from app.utils.futures_market_snapshot import latest_price_change

#: No price movement for this long, with no reported volume, is "not trading".
#: The Nov 13 sizing on #11937 put the cut at a week without trades.
QUIET_DAYS = 7
#: Off switch, read on every call so it needs no deploy. Default on.
SWITCH_ENV = "DISCOVER_HIDE_NOT_TRADING"
#: A round-up left with fewer members than this is not featured at all.
ROUNDUP_MIN_MEMBERS = 2


def hide_not_trading_enabled(environ: Optional[dict] = None) -> bool:
    env = os.environ if environ is None else environ
    return str(env.get(SWITCH_ENV, "true")).strip().lower() not in {"0", "false", "off", "no"}


def is_not_trading(price_changed_at: Optional[datetime], volume_24h: Any, now: datetime) -> bool:
    """True only when the price has been still for ``QUIET_DAYS`` and the venue
    reports no volume. Unknown price age is never stale."""
    if price_changed_at is None:
        return False
    if volume_24h is not None and float(volume_24h) > 0:
        return False
    return price_changed_at <= now - timedelta(days=QUIET_DAYS)


def market_not_trading(market: Any, now: datetime) -> bool:
    """A served market (ORM row or cached snapshot row) that must not be featured."""
    if not hide_not_trading_enabled():
        return False
    # Both carriers, read through the two names the scoring loop's read audit
    # treats as structural: a rebuilt snapshot row carries the folded stamp in
    # its instance dict; an ORM (or `__slots__`) row folds its own outcomes.
    state = getattr(market, "__dict__", None) or {}
    if "price_changed_at" in state:
        stamp = state["price_changed_at"]
    else:
        stamp = latest_price_change(getattr(market, "outcomes", None) or [])
    return is_not_trading(stamp, getattr(market, "volume_24h", None), now)


def _market_id(value: Any) -> Optional[int]:
    return int(value) if isinstance(value, int) and not isinstance(value, bool) else None


def trim_roundup(item: dict, stale_ids: set[int]) -> Optional[dict]:
    """A round-up card without its not-trading members, or ``None`` when too few
    remain. A round-up is rated by its stalest member: none of the markets it
    shows may be one nobody trades, so each is removed from every place the card
    draws or counts it (rows, items, member ids)."""
    data = item.get("data")
    if not isinstance(data, dict) or not stale_ids:
        return item
    member_ids = [m for m in (data.get("member_ids") or []) if _market_id(m) not in stale_ids]
    items = [
        i for i in (data.get("items") or [])
        if not (isinstance(i, dict) and _market_id((i.get("data") or {}).get("id")) in stale_ids)
    ]
    roundup = data.get("roundup")
    rows = None
    if isinstance(roundup, dict) and isinstance(roundup.get("rows"), list):
        rows = [r for r in roundup["rows"] if not (isinstance(r, dict) and _market_id(r.get("market_id")) in stale_ids)]
    shown = rows if rows is not None else (items or member_ids)
    if len(shown) < ROUNDUP_MIN_MEMBERS:
        return None
    out = dict(item)
    out_data = dict(data)
    out_data["member_ids"] = member_ids
    out_data["items"] = items
    out_data["item_count"] = len(member_ids)
    if rows is not None:
        out_data["roundup"] = {**roundup, "rows": rows, "count_line": _recount(roundup, data, rows, stale_ids)}
    out["data"] = out_data
    return out


_COUNT_LINE_RE = re.compile(r"^Showing (\d+) of (\d+)")


def _recount(roundup: dict, data: dict, rows: list, stale_ids: set[int]) -> Optional[str]:
    """The card's "Showing K of N" after its quiet members leave. Monday's render
    (Nov 16) caught "By November 30" drawing 4 rows under "Showing 5 of 6". K is
    the rows still drawn, N drops by the members removed; when every remaining
    member is drawn the line goes, as a builder omits it when nothing is hidden."""
    line = roundup.get("count_line")
    match = _COUNT_LINE_RE.match(line) if isinstance(line, str) else None
    if not match:
        return line
    removed = sum(1 for m in (data.get("member_ids") or []) if _market_id(m) in stale_ids)
    total = max(int(match.group(2)) - removed, len(rows))
    if len(rows) >= total:
        return None
    return f"Showing {len(rows)} of {total}" + line[match.end():]


async def drop_not_trading_roundup_members(db: Any, produced: list[dict], now: datetime, covered_ids) -> list[dict]:
    """Remove not-trading members from produced round-ups with ONE read (each
    covered market's volume and its newest price change), dropping any round-up
    left too small. ``covered_ids(item)`` returns the market ids a round-up shows."""
    if not produced or not hide_not_trading_enabled():
        return produced
    ids: set[int] = set()
    for item in produced:
        ids |= set(covered_ids(item))
    if not ids:
        return produced
    from sqlalchemy import func, select

    from app.models.models import FuturesMarket, FuturesOutcome

    rows = (await db.execute(
        select(FuturesMarket.id, FuturesMarket.volume_24h, func.max(FuturesOutcome.price_changed_at))
        .outerjoin(FuturesOutcome, FuturesOutcome.market_id == FuturesMarket.id)
        .where(FuturesMarket.id.in_(sorted(ids)))
        .group_by(FuturesMarket.id, FuturesMarket.volume_24h)
    )).all()
    stale = {int(r[0]) for r in rows if is_not_trading(r[2], r[1], now)}
    if not stale:
        return produced
    kept = []
    for item in produced:
        trimmed = trim_roundup(item, stale)
        if trimmed is not None:
            kept.append(trimmed)
    return kept
