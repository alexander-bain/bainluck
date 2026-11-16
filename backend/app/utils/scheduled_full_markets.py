"""#11286 (decision 138: A): scheduled NFL and NBA games get spreads and totals once an hour.

A scheduled game outside the live and starting-soon tiers was polled for the
moneyline only (`h2h`): by discovery every 15 min, and by the poller's "later"
tier for games 2-6 h out. So the projected-points chart had nothing to draw
until two hours before kickoff. Builder E counted projections recorded per
scheduled NFL game in 24 h: 0 for all 14.

Now, for these two leagues only, ONE fetch an hour asks for
``h2h,spreads,totals``, whichever path reaches the sport first that hour. Both
paths share this stamp, so the hour is never paid twice. The Odds API bills
events × markets × regions, so this costs 2 market-units per listed event per
hour: ~670 a day for the NFL (14 games) and ~2,400-3,070 for the NBA, against
~224,000 a day of headroom on Nov 11 (#11286).

Fail closed: if Redis can't be read the stamp can't be honoured, and the fetch
stays ``h2h``. The quota is the constrained resource, and a lost stamp must not
turn one fetch an hour into four.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: The two leagues decision 138 names. No other league.
SCHEDULED_FULL_MARKET_SPORTS = frozenset({"americanfootball_nfl", "basketball_nba"})

#: What the hourly fetch asks for, and what every other fetch keeps asking for.
SCHEDULED_FULL_MARKETS = "h2h,spreads,totals"
MONEYLINE_ONLY = "h2h"

#: Once an hour. The stamp is 55 minutes, not 60, because discovery runs at :05
#: and :35 and its fetch lands a minute or so into the run: with 60, the run an
#: hour after a fetch came 59 minutes later and stayed moneyline-only, so lines
#: refreshed every ~90 minutes, matching #12599's 90-minute bound, and the
#: projected final blinked out at each refresh (Nov 12 reads, #11286). 55 lets that
#: run take it, so lines refresh every 60 minutes and never twice in 55.
SCHEDULED_FULL_MARKETS_INTERVAL_SECONDS = 55 * 60

STAMP_PREFIX = "bainluck:scheduled_full_markets:"


def stamp_key(sport_key: str) -> str:
    return f"{STAMP_PREFIX}{sport_key}"


def scheduled_markets(sport_key: str, r, now_ts: float) -> str:
    """The markets a scheduled-game fetch should ask for now. Never raises."""
    if sport_key not in SCHEDULED_FULL_MARKET_SPORTS or r is None:
        return MONEYLINE_ONLY
    try:
        raw = r.get(stamp_key(sport_key))
    except Exception:
        return MONEYLINE_ONLY
    if raw is None:
        return SCHEDULED_FULL_MARKETS
    try:
        last = float(raw.decode() if isinstance(raw, bytes) else raw)
    except (TypeError, ValueError):
        return SCHEDULED_FULL_MARKETS
    if now_ts - last >= SCHEDULED_FULL_MARKETS_INTERVAL_SECONDS:
        return SCHEDULED_FULL_MARKETS
    return MONEYLINE_ONLY


def record_full_fetch(sport_key: str, r, now_ts: float) -> None:
    """Stamp the hour as paid, after a full-markets fetch succeeded. Never raises."""
    if r is None:
        return
    try:
        r.set(stamp_key(sport_key), str(now_ts), ex=SCHEDULED_FULL_MARKETS_INTERVAL_SECONDS * 3)
    except Exception:  # noqa: BLE001 — the stamp is an optimisation, never a reason to fail a poll
        # A lost stamp means the next pass may pay for lines again within the hour:
        # bounded quota cost, never a failed fetch. Logged so a sick Redis is visible.
        logger.debug("scheduled full-markets stamp not recorded for %s", sport_key, exc_info=True)
