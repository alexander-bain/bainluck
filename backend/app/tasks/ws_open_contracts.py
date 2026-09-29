"""#9484 — an open Kalshi contract streams its price whatever its event's phase.

The Kalshi socket subscribes from events that are ``live``, ``scheduled``
within 6 h, or recently ``suspended`` (``kalshi_ws._kalshi_slate_event_window``).
Every market outside that join — a standalone future or prop with no
``event_id``, or a game market whose event is days away — never reached the
wire, so its stored price moved only when the 2 h REST poll came round, and
the #9484 post-commit invalidation had nothing to say about it. Alex's ruling
on #9484: market lifecycle, not game phase, decides streaming.

This is that rule for PRICES on Kalshi. Eligibility is the contract's own
unsettled truth, never a kickoff horizon:

- the market is not ``resolved`` (NULL fails OPEN — the column is nullable and
  a plain ``!=`` drops a NULL, as ``ws_slate`` says) and carries no
  ``settled_at``;
- the market has not passed its ``expiration_time`` (NULL fails open);
- the outcome has a venue ticker and no ``is_winner``.

Measured once to size this (production 2026-09-29 04:5xZ): 4,941 such Kalshi
markets outside the event link, 48,051 tickers, 5,104 of which moved price in
the previous 24 h — a write load well under the linked slate's.

**Prices only, never settlement.** ``handle_lifecycle`` treats a market as a
two-sided game line: when one ticker settles it marks the whole market
``resolved`` and writes the OPPOSITE ``is_winner`` onto every other outcome.
On a multi-candidate future one candidate settling "no" would crown every
other candidate. So these tickers join the price map only; the lifecycle map
(``market_id_by_ext``) stays the linked slate, and they ride connections that
subscribe to the ``ticker`` channel alone.

**Their own connections, so the live game never pays for them.** The linked
slate's socket is unchanged. The admitted tickers are fanned over separate
connections of at most ``OPEN_CONTRACT_TICKERS_PER_CONNECTION``: production has
held 23,456 tickers on one Kalshi socket with full delivery (#837 measurement,
2026-09-22), so 20,000 sits under a size already observed to work, and a
rejected or throttled open-contract subscribe cannot take the game slate's
prices down with it.

``WS_OPEN_CONTRACT_PRICES=0`` turns the whole arm off at the next recycle with
no deploy — the undo line.
"""

import os
from collections.abc import Iterable, Mapping

#: Tickers per open-contract connection. Below the 23,456 one production socket
#: has carried in full; see the module docstring.
OPEN_CONTRACT_TICKERS_PER_CONNECTION = int(
    os.getenv("KALSHI_WS_OPEN_CONTRACT_TICKERS_PER_CONNECTION", "20000")
)


def open_contract_prices_enabled() -> bool:
    """False only when ``WS_OPEN_CONTRACT_PRICES`` is set to ``0``."""
    return os.getenv("WS_OPEN_CONTRACT_PRICES", "1").strip() != "0"


def kalshi_open_contract_stmt():
    """Every unsettled Kalshi outcome with a ticker: (ticker, market_id, outcome_id).

    No event join and no event window — that is the point. The caller removes
    the tickers the linked slate already carries.
    """
    from sqlalchemy import or_, select, text

    from app.models.models import FuturesMarket, FuturesOutcome

    return (
        select(
            FuturesOutcome.external_id,
            FuturesOutcome.market_id,
            FuturesOutcome.id,
        )
        .join(FuturesMarket, FuturesOutcome.market_id == FuturesMarket.id)
        .where(
            FuturesMarket.source == "kalshi",
            or_(
                FuturesMarket.status.is_(None),
                FuturesMarket.status != "resolved",
            ),
            FuturesMarket.settled_at.is_(None),
            or_(
                FuturesMarket.expiration_time.is_(None),
                FuturesMarket.expiration_time > text("NOW()"),
            ),
            FuturesOutcome.external_id.isnot(None),
            FuturesOutcome.is_winner.is_(None),
        )
    )


def open_contract_ticker_map(
    rows: Iterable[tuple[str, int, int]],
    linked: Mapping[str, tuple[int, int]],
) -> dict[str, tuple[int, int]]:
    """ticker → (market_id, outcome_id) for the rows the linked slate lacks.

    Keys are upper-cased like the linked map's, so a ticker the game socket
    already carries is never subscribed twice.
    """
    out: dict[str, tuple[int, int]] = {}
    for ext_id, market_id, outcome_id in rows:
        if not ext_id:
            continue
        ticker = ext_id.upper()
        if ticker in linked:
            continue
        out[ticker] = (market_id, outcome_id)
    return out


def shard_tickers(
    tickers: Iterable[str],
    per_connection: int = OPEN_CONTRACT_TICKERS_PER_CONNECTION,
) -> list[list[str]]:
    """Sorted tickers in connection-sized shards, none lost.

    Sorted so a recycle re-deals the same shards when the population has not
    moved.
    """
    ordered = sorted(tickers)
    size = max(1, int(per_connection))
    return [ordered[i:i + size] for i in range(0, len(ordered), size)]
