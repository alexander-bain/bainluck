"""Does a market's OWN id agree with the event it is linked to? (#1902, queue 363)

Lifted OUT of ``scripts/census_settlement_contamination.py``, where queue 362
first wrote it, because Alex ruled that the 2,069 date-disagreement outcomes are
**QUARANTINED from published calibration curves as under review until
identity-verified** — and a predicate that lives in a script cannot be consumed
by the payload that publishes the curve.

Lifting rather than copying is deliberate, and it is the standing lesson from two
separate divergences inside one week: the concept-eligibility rule (web behind
iOS, #1924) and the label-pass live derivation (native behind web, #1933). Both
were scoped to the endpoint that happened to carry the bug report rather than to
the class, and both then diverged. **A shared eligibility predicate gets ONE
implementation.** The census script now imports this module; there is no second
copy to drift.

## Why the quarantine keys on the PREDICATE, never on the 2,069

The tempting shortcut is to freeze the reviewed ids and exclude that list. It is
the same mistake the population-2 census refused when it refused RE-KEY: a count
(or a frozen list) is a claim about the world's current state, which the ordinary
pipeline repairs on its own, so it expires while nothing is wrong.

A cruder re-measurement makes the point concretely. A raw ``-YYMONDD`` regex over
``KXMLB%`` tickers returns **more than a thousand** markets, not 165 — because
gotcha #14 is real: many Kalshi tickers carry a CLOSE date, not a game date, and
a regex cannot tell the two apart. :func:`ticker_game_date` returning ``None`` on
anything it cannot read as a game date is what keeps this predicate honest, and
it is why the quarantine must be evaluated, not remembered.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

__all__ = [
    "ticker_game_date",
    "market_identity_disputed",
    "eastern_game_date",
    "QUARANTINE_REASON",
]

#: The reason string a quarantined row carries into the payload. Named, because a
#: row dropped without a reason is indistinguishable from a row that was never
#: there — and a calibration page that silently sheds rows is exactly the
#: dishonesty Alex's ruling forbids.
QUARANTINE_REASON = "market_identity_disputed"

_TICKER_DATE_RE = re.compile(r"-(\d{2})([A-Z]{3})(\d{2})")
_MONTHS = {
    m: i + 1
    for i, m in enumerate(
        ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
         "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
    )
}


def ticker_game_date(external_id: str | None) -> date | None:
    """The date the MARKET says it is about, from its own ticker. ``None`` if absent.

    Kalshi game tickers carry ``YYMONDD`` immediately after the series prefix
    (``KXMLBTOTAL-26AUG051940MINKC`` -> 2026-08-05), in US Eastern, and gotcha #14
    says to trust it over ``commence_time`` for game matching — the venue's
    ``commence_time`` is frequently the close time.

    Returning ``None`` for an unparseable ticker is deliberate and load-bearing: a
    market whose identity we cannot read is NOT thereby in agreement with its
    event. It is unknown, and :func:`market_identity_disputed` must not mark it
    certain.
    """
    if not external_id:
        return None
    m = _TICKER_DATE_RE.search(external_id)
    if not m:
        return None
    yy, mon, dd = m.group(1), m.group(2), m.group(3)
    month = _MONTHS.get(mon)
    if month is None:
        return None
    try:
        return date(2000 + int(yy), month, int(dd))
    except ValueError:
        return None


def eastern_game_date(commence_time) -> date | None:
    """The event's game-date in US Eastern, which is the calendar the ticker uses.

    Comparing against the UTC date would manufacture a disagreement for every
    night game — a 19:40 ET first pitch is the NEXT UTC day — and a census that
    cries wolf on most of its population teaches its reader to skip it.
    """
    if isinstance(commence_time, str):
        try:
            commence_time = datetime.fromisoformat(commence_time)
        except ValueError:
            return None
    if not isinstance(commence_time, datetime):
        return None
    if commence_time.tzinfo is None:
        commence_time = commence_time.replace(tzinfo=timezone.utc)
    return commence_time.astimezone(ZoneInfo("America/New_York")).date()


def market_identity_disputed(external_id: str | None, commence_time) -> bool:
    """True when the market's OWN id names a different game-date than its event.

    QUEUE 362, and it is the ordering ruling arriving a FOURTH time — market
    identity is identity too.

    The specimen: outcome rows ``217508565``-``217508571`` sit on market
    ``58609021``, whose ticker is ``KXMLBTOTAL-26AUG051940MINKC`` — the **Aug 5**
    MIN@KC game. It is linked to event ``15187509``, which is soundly and
    correctly the **Aug 6** game, and that event stores 8-2, which is the **Aug
    4** game's score. Three games in one grade. Nothing about the EVENT is
    disputed, so the old ``disputed`` check waved it through as "identity
    certain" and the census declared 3 of its rows adjudicable — computing a
    grade for the Aug 5 market from the Aug 6 game's truth.

    A market bound to the wrong game is exactly as un-adjudicable as an event
    wearing the wrong id, and for the same reason: the truth we would pair it
    with is some other game's.
    """
    ticker_date = ticker_game_date(external_id)
    if ticker_date is None or commence_time is None:
        return False
    event_date = eastern_game_date(commence_time)
    if event_date is None:
        return False
    return ticker_date != event_date
