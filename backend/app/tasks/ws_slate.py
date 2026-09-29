"""#9484 — a suspended match whose market is still trading keeps its price stream.

Both venue sockets subscribe from events that are ``live`` or ``scheduled``
within 6 h. ``suspended`` was in neither arm, so a row the graph suspends drops
off the socket at the next recycle, and a market the venue is still trading
freezes at its last price with nothing that will ever refresh it.

The specimen (2026-09-28): Dickerson v Pereira, event 15320435, Kalshi
``KXATPCHALLENGERMATCH-26SEP28DICPER``. Scheduled 17:10Z, no score ever, and
``suspended`` by 20:45Z — which is where the never-observed tennis bound of the
live→suspended nets lands (3.0 h + 0.5 h margin = 20:40Z; the writer itself is
not proven). Our outcomes stopped at 20:45Z, the first recycle after. At
23:32Z the contract was active at DIC .89/.90 while the page still showed .51
and "Last number 2 hours ago".

The suspension is not wrong to make — it is the graph declining to call an
unobserved row live, and nothing here reverses it. What was wrong is that the
event's PHASE decided whether its MARKET's price is delivered. Alex's ruling on
#9484: market lifecycle, not game phase, decides streaming. This is that rule
for the ``suspended`` phase: an open contract on a recently suspended event is
subscribed; the event's status is never written from here.

Two bounds, each against a measured population (production 2026-09-28 23:4xZ,
events ``suspended`` with ``commence_time`` inside 24 h):

    kalshi ....... 243 events, 507 markets,  49 not resolved
    polymarket ... 264 events, 5,321 markets, 208 not resolved

- **The market is not ``resolved``.** 90 % of those markets are already
  settled, and a settled token answers the socket with silence. The NULL arm
  fails OPEN, for the reason ``polymarket_ws._slate_market_filter`` gives:
  production's column is nullable, and a plain ``!=`` drops a NULL.
- **The event started inside ``SUSPENDED_SLATE_MAX_AGE_HOURS``.** Suspended
  rows accumulate — postponed fixtures, abandoned matches, the rain-delay that
  never resumed — and unlike ``live`` nothing advances them out, so the arm
  needs the floor the ``live`` arm deliberately does not carry.
"""

#: How long after its scheduled start a ``suspended`` event's open markets stay
#: subscribed. The same 24 h as the Polymarket ``scheduled`` arm's floor
#: (``SLATE_MAX_AGE_HOURS``): long enough for a suspension that resumes the same
#: day, short enough that the pile of never-resumed rows stays out.
SUSPENDED_SLATE_MAX_AGE_HOURS = 24


def suspended_open_market_arm():
    """The slate arm for a suspended event: open market, recent start.

    Meant to sit inside a slate's ``or_()`` beside the ``live`` and
    ``scheduled`` arms, in a query that joins both ``events`` and
    ``futures_markets``.
    """
    from sqlalchemy import and_, or_, text

    from app.models.models import Event, FuturesMarket

    return and_(
        Event.status == "suspended",
        Event.commence_time >= text(
            f"NOW() - INTERVAL '{int(SUSPENDED_SLATE_MAX_AGE_HOURS)} hours'"
        ),
        or_(
            FuturesMarket.status.is_(None),
            FuturesMarket.status != "resolved",
        ),
    )
