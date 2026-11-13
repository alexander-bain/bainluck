"""#11937 (Alex, 7:42 AM PT Fri Nov 13): a market that is not trading is not featured.

"If they're stale because of illiquid trading, we just shouldn't be featuring
the market." A Discover card or round-up member whose market nobody has traded
for a week shows a number the venue's book no longer stands behind (the Oscars
Best Casting market inside Awards Season had last traded 19 days earlier; most
of an Argentine relegation round-up, 9 to 62 days).

## the signal

``futures_markets.quiet_since``: the first time a poll read the market's venue
24-hour volume as zero, with no non-zero reading since. A database trigger keeps
it on every write of ``volume_24h``, so every writer (the Polymarket event and
sub-market polls, the Kalshi board) is covered without each being changed:

* ``volume_24h > 0``  -> ``quiet_since`` is cleared (it traded in the last day);
* ``volume_24h = 0``  -> ``quiet_since`` keeps its first stamp, or takes now();
* ``volume_24h IS NULL`` (not read) -> unchanged.

A market quiet for ``QUIET_DAYS`` (6) has had no trade for at least seven days:
the 24-hour window covers the day before the first zero. ``NULL`` means trading
or not yet observed, never stale, so nothing disappears before the column has
been read for a week.

## why this module holds the DDL

The migration (``alembic/versions/fm_quiet_since_11937.py``) and the model's
``after_create`` hook run these exact statements, so every real-Postgres gate
carries the production trigger. This module imports nothing from the app.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any, Optional

QUIET_COLUMN = "quiet_since"
FUNCTION_NAME = "keep_futures_market_quiet_since"
TRIGGER_NAME = "trg_keep_futures_market_quiet_since"

#: Days of observed zero 24-hour volume before a market counts as not trading.
QUIET_DAYS = 6
#: Default on: the rule cannot fire before a market has been read as quiet for
#: QUIET_DAYS, so turning it on is safe the moment the column exists.
SWITCH_ENV = "DISCOVER_HIDE_NOT_TRADING"

CREATE_FUNCTION_SQL = f"""
CREATE OR REPLACE FUNCTION {FUNCTION_NAME}() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.volume_24h IS NULL THEN
        IF TG_OP = 'UPDATE' THEN
            NEW.{QUIET_COLUMN} := OLD.{QUIET_COLUMN};
        END IF;
    ELSIF NEW.volume_24h > 0 THEN
        NEW.{QUIET_COLUMN} := NULL;
    ELSIF TG_OP = 'UPDATE' AND OLD.{QUIET_COLUMN} IS NOT NULL THEN
        NEW.{QUIET_COLUMN} := OLD.{QUIET_COLUMN};
    ELSE
        NEW.{QUIET_COLUMN} := now();
    END IF;
    RETURN NEW;
END;
$$;
"""

DROP_TRIGGER_SQL = f"DROP TRIGGER IF EXISTS {TRIGGER_NAME} ON futures_markets;"
CREATE_TRIGGER_SQL = (
    f"CREATE TRIGGER {TRIGGER_NAME} BEFORE INSERT OR UPDATE OF volume_24h "
    f"ON futures_markets FOR EACH ROW EXECUTE FUNCTION {FUNCTION_NAME}();"
)
DROP_FUNCTION_SQL = f"DROP FUNCTION IF EXISTS {FUNCTION_NAME}();"


def hide_not_trading_enabled(environ: Optional[dict] = None) -> bool:
    env = os.environ if environ is None else environ
    return str(env.get(SWITCH_ENV, "true")).strip().lower() not in {"0", "false", "off", "no"}


def is_not_trading(quiet_since: Optional[datetime], now: datetime) -> bool:
    """True only when the market has been read as quiet for QUIET_DAYS or more.
    Unknown (``None``) is never stale."""
    if quiet_since is None:
        return False
    return quiet_since <= now - timedelta(days=QUIET_DAYS)


def market_not_trading(market: Any, now: datetime) -> bool:
    """A served market (ORM row or the cached plain snapshot) that should not be featured."""
    if not hide_not_trading_enabled():
        return False
    return is_not_trading(getattr(market, "quiet_since", None), now)


#: A round-up left with fewer members than this after its not-trading members
#: are dropped is not featured at all.
ROUNDUP_MIN_MEMBERS = 2


def _market_id(value: Any) -> Optional[int]:
    return int(value) if isinstance(value, int) and not isinstance(value, bool) else None


def trim_roundup(item: dict, stale_ids: set[int]) -> Optional[dict]:
    """A round-up card without its not-trading members, or ``None`` when too few
    remain. A round-up is rated by its stalest member (Fable, Nov 13): none of
    its members may be a market nobody trades, so each such member is removed
    from every place the card draws or counts it (rows, items, member ids)."""
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
        out_data["roundup"] = {**roundup, "rows": rows}
    out["data"] = out_data
    return out


async def drop_not_trading_roundup_members(db: Any, produced: list[dict], now: datetime, covered_ids) -> list[dict]:
    """Remove not-trading members from produced round-ups (one read of
    ``quiet_since`` for every market they cover), dropping any round-up left too
    small. ``covered_ids(item)`` returns the market ids a round-up shows."""
    if not produced or not hide_not_trading_enabled():
        return produced
    ids = set()
    for item in produced:
        ids |= set(covered_ids(item))
    if not ids:
        return produced
    from sqlalchemy import select

    from app.models.models import FuturesMarket

    rows = (await db.execute(
        select(FuturesMarket.id, FuturesMarket.quiet_since).where(FuturesMarket.id.in_(sorted(ids)))
    )).all()
    stale = {int(r[0]) for r in rows if is_not_trading(r[1], now)}
    if not stale:
        return produced
    kept = []
    for item in produced:
        trimmed = trim_roundup(item, stale)
        if trimmed is not None:
            kept.append(trimmed)
    return kept
