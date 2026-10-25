"""Did this event's ``commence_time`` come from a schedule? (#10880)

The iPhone "Add to Calendar" action writes a start time into a reader's own
calendar, where nothing of ours can correct it later. So it may only use a
start that a SCHEDULE published: a sports schedule provider reporting when the
game is played. A prediction market's close, expiration, listing stamp or
ticker date is not a start. ``app/utils/event_completion.py`` documents each of
those values, with the production measurements behind them:

==================  ==========================================================
``kalshi``           ``occurrence_datetime``, byte-identical to the expected
                     EXPIRATION (3h after a soccer kick-off, 11 of 11)
``kalshi_ticker``    a DATE parsed out of a ticker, resolved to midnight UTC
``kalshi_ticker_time``  a market's HHMM; often right, but still a market's word
``polymarket``       Gamma ``startDate``, the LISTING stamp (minted rows read
                     11-18h early)
``polymarket_venue`` Gamma ``gameStartTime``, the venue's word for the start
==================  ==========================================================

Only the three schedule providers below count. Everything else counts as not
from a schedule, including NULL (a row that predates provenance) and any value
added later. A new provider joins this set by name; nothing gets in by default.

This is provenance, not a clock rule. It says nothing about whether the hour
is a placeholder (``start_is_tbd`` answers that) or whether the game has
started (the status and the clock answer that). A client needs all three.
"""

from __future__ import annotations

from typing import Any, Optional

#: The ``events.commence_time_source`` values written by a sports schedule
#: provider: ESPN's scoreboard (``tasks/espn_sync.py``, ``utils/espn_helpers.py``,
#: ``tasks/sports.py``), StatPal's fixture listing (``tasks/statpal_sync.py``)
#: and The Odds API's event list (``tasks/odds_polling.py``, ``tasks/sports.py``).
SCHEDULE_START_SOURCES = frozenset({"espn", "statpal", "odds_api"})


def start_is_from_schedule(commence_time_source: Optional[str]) -> bool:
    """True iff the stored start was written by a sports schedule provider."""
    return commence_time_source in SCHEDULE_START_SOURCES


def served_start_is_from_schedule(
    commence_time_source: Optional[str],
    stored_start: Any,
    served_start: Any,
) -> bool:
    """``start_is_from_schedule`` for a route that may serve another start.

    The event page (``/api/events/{id}``) serves ``served_commence_time``, not
    the column. While a row is held (#9634) that is StatPal's start for a LATER
    SESSION: when the session begins, not when this match does. A tennis match
    can be third on its court, so the session's start is not a start a calendar
    entry can carry. The column's provenance says nothing about a value the
    column does not hold, so a substituted start serves False. Only when the
    route serves the stored start does the stored provenance answer.
    """
    if stored_start is None or served_start != stored_start:
        return False
    return start_is_from_schedule(commence_time_source)


#: How many read-only views may sit in front of the row. Today there is one
#: (``FoldedBlendView``); the bound only keeps a cycle from looping.
_MAX_VIEW_DEPTH = 4


def loaded_commence_time_source(row: Any) -> Optional[str]:
    """The row's ``commence_time_source``, read only from already-loaded state.

    Two rules, and each one has had a cost:

    - ``__dict__``, never ``getattr``. On an expired async ORM row ``getattr``
      lazy-loads, which raises ``MissingGreenlet`` inside the per-item feed
      serializer (#1698; gotcha #42).
    - Look THROUGH read-only views. ``/api/feed/price-cards``
      (``feed_prices._event_cards``) hands the scorer a ``FoldedBlendView``,
      which keeps the real row as ``_event`` and forwards attributes with
      ``__getattr__``. The view's own ``__dict__`` has no column, so reading
      only the view served False on the price refresh. iOS adopts that card
      wholesale, so "Add to Calendar" disappeared from a Discover game after
      its first price update (lane1b's review of PR #11145).

    Anything not loaded reads as None, which serves "not from a schedule".
    """
    for _ in range(_MAX_VIEW_DEPTH):
        state = getattr(row, "__dict__", None)
        if not isinstance(state, dict):
            return None
        if "commence_time_source" in state:
            return state["commence_time_source"]
        row = state.get("_event")
        if row is None:
            return None
    return None
