"""Current Odds outright quote identity; never an anchor for older history."""

from datetime import datetime, timezone
from typing import Any


def current_quote_identity(markets: list[Any], sport_key: str, polled_at: datetime) -> dict | None:
    """Retain only an unambiguous provider event shared by every quoted book.

    The poll still uses a rolling sport-key row. Consumers must require an
    outcome refreshed at/after polled_at before using this anchor; older prices
    and history do not inherit a newly observed edition. A missing/ambiguous
    batch returns None so the writer clears any previous current anchor.
    """
    identities = set()
    for market in markets:
        event_id = getattr(market, "event_id", None)
        raw_time = getattr(market, "event_commence_time", None)
        if (not isinstance(event_id, str) or not event_id.strip()
                or not isinstance(raw_time, str)
                or getattr(market, "sport_key", None) != sport_key):
            return None
        try:
            commence = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
        except ValueError:
            return None
        if commence.tzinfo is None or commence.utcoffset() is None:
            return None
        identities.add((event_id, commence.astimezone(timezone.utc).isoformat()))
    if len(identities) != 1:
        return None
    event_id, commence = identities.pop()
    return {
        "event_id": event_id,
        "commence_time": commence,
        "sport_key": sport_key,
        "polled_at": polled_at.isoformat(),
        "scope": "current_quotes_only",
    }
