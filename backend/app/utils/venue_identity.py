"""Read the venue event identity carried by a row.

A venue names its markets itself. Kalshi gives every event a ticker
(``KXNBAMVP-27``: series ``KXNBAMVP``, the 2026-27 edition); Polymarket gives
every event an id. ``FuturesMarket.group_id`` already stores exactly that
identity (``kalshi:<event ticker>``, ``polymarket:<event id>``). This module
reads it, and nothing else, so a consumer can check one narrow thing before it
lets a title, a family key or a name join two rows: does the venue's own
identity already say these are different markets?

``same_venue_market`` answers:

* ``True``  — same venue event, which can contain different market contracts.
* ``False`` — different event identities within one venue.
* ``None``  — different venues, or an identity is missing. The venue cannot
  answer; the caller keeps whatever rule it already had.

These are identity comparisons, not settlement-equivalence decisions. Equal
event IDs or edition tokens alone never authorize blending market contracts.
The historical function name is retained for candidate compatibility.

``kalshi_supersedes`` answers whether one Kalshi row comes from a LATER edition
of the same market than another (``KXNBAMVP-27`` over ``KXNBAMVP-26``). It
compares the venue's own two-digit edition tokens and never a date, and only
between tickers that are identical apart from that token: per-player series
(``KXNEXTTEAMNFL-26JCHASE``, ``KXNEXTTEAMNFL-27JBURROW``) carry the token too,
and two players are never editions of each other.

DOCTRINE (``competition_identity.py``, ``futures_verified_title.py``,
``theme_definitions`` ``oscars-edition@1``): assigned, never inferred. An
edition is read from the venue's literal identity. ``resolution_date`` is a
schedule the venue may pad by years (#2644), ``updated_at`` is any write
(#11579), and the calendar is not evidence. None of them is read here.

Pure: no DB, no network, no imports from the app.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

__all__ = [
    "VenueIdentity",
    "venue_identity",
    "same_venue_market",
    "kalshi_supersedes",
    "RULE_VERSION",
]

#: Named once so a consumer can record which reading it applied.
RULE_VERSION = "venue-identity@1"

#: ``KXNBAMVP-27`` → series ``KXNBAMVP``, edition token ``27``, rest ``""``;
#: ``KXNBASEED-27EAST8`` → ``KXNBASEED`` / ``27`` / ``EAST8``. The token is the
#: first two digits after the first hyphen and must not be followed by a third
#: digit; the rest is everything after it.
_KALSHI_EVENT_RE = re.compile(
    r"^(?P<series>[A-Z][A-Z0-9]*)-(?P<yy>\d{2})(?!\d)(?P<rest>.*)$"
)

#: The same plausibility window ``event_awards.edition_year`` uses: a two-digit
#: token outside 2020–2045 is a series id (``KXGRAMAOTY-69``), not an edition.
_EDITION_MIN, _EDITION_MAX = 20, 45


@dataclass(frozen=True)
class VenueIdentity:
    venue: str
    #: The venue's own event identity (Kalshi event ticker, Polymarket event id).
    event: str
    #: Kalshi series ticker, when the event ticker has the series-edition shape.
    series: Optional[str] = None
    #: Kalshi two-digit edition token (``27`` for ``KXNBAMVP-27``), when plausible.
    edition: Optional[int] = None
    #: The event ticker's text after the edition token: ``""`` for
    #: ``KXNBAMVP-27``, ``"JCHASE"`` for ``KXNEXTTEAMNFL-26JCHASE``.
    rest: Optional[str] = None


def venue_identity(source: Any, group_id: Any) -> Optional[VenueIdentity]:
    """The venue market named by ``group_id``, or None when it names none.

    ``group_id`` must carry the row's own venue as its prefix; a group id from a
    different venue than ``source`` is refused rather than trusted.
    """
    if not isinstance(source, str) or not isinstance(group_id, str):
        return None
    venue = source.strip().lower()
    prefix, sep, event = group_id.strip().partition(":")
    if not sep or not event or prefix.lower() != venue:
        return None
    if venue != "kalshi":
        return VenueIdentity(venue=venue, event=event)
    match = _KALSHI_EVENT_RE.match(event)
    if not match:
        return VenueIdentity(venue=venue, event=event)
    yy = int(match.group("yy"))
    edition = yy if _EDITION_MIN <= yy <= _EDITION_MAX else None
    return VenueIdentity(
        venue=venue,
        event=event,
        series=match.group("series"),
        edition=edition,
        rest=match.group("rest"),
    )


def same_venue_market(
    a: Optional[VenueIdentity], b: Optional[VenueIdentity]
) -> Optional[bool]:
    """True / False when one venue's identity decides it; None when it cannot."""
    if a is None or b is None or a.venue != b.venue:
        return None
    return a.event == b.event


def kalshi_supersedes(
    later: Optional[VenueIdentity], earlier: Optional[VenueIdentity]
) -> bool:
    """True when ``later`` is a later edition of the same Kalshi market.

    Same series, same ticker text after the edition token, and a higher token:
    ``KXNBAMVP-27`` supersedes ``KXNBAMVP-26``; ``KXNEXTTEAMNFL-27JBURROW`` does
    not supersede ``KXNEXTTEAMNFL-26JCHASE``.
    """
    return (
        later is not None
        and earlier is not None
        and later.venue == earlier.venue == "kalshi"
        and later.series is not None
        and later.series == earlier.series
        and later.rest == earlier.rest
        and later.edition is not None
        and earlier.edition is not None
        and later.edition > earlier.edition
    )
