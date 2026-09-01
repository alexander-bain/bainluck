"""Fast-lane CLOB token top-up — address the slate directly, never wait for a rotation.

WHY THIS EXISTS.  ``poll_polymarket_markets`` now stamps ``clob_token_ids`` at
ingest (Q460), and it does so on the UPDATE path as well as the insert, so
existing rows acquire the key when the poll reaches them.  Measured on
production 2026-08-31: the first sync after that deploy took 0 -> 701 markets
carrying the key, 558 of them rows created before the deploy.  The write works.

**Reaching the row is the problem.**  Gamma caps ``/events`` at offset 2000, so
the poll addresses at most ~2,000 of ~39,000 open markets per run; it rotates a
20-page cursor and truncates on a 420s budget.  Which markets get refreshed in a
given hour is therefore a rotation, not a guarantee — the same fact
``PolymarketAPIService.get_markets_by_conditions`` was written for ("any given
event is re-priced only when the cursor happens to land on it").

Measured consequence for the fast lane, 2026-08-31 03:58 UTC, ~2h after the
deploy: 701 markets carried tokens and **0 of the 77 markets the WebSocket
consumer actually subscribes to** were among them.  The socket kept returning
``no_asset_ids``.  A ship that depends on a rotation reaching it is a ship with
no delivery date.

So the fast lane asks for exactly the markets it needs.  ``/markets?condition_ids=``
is the one Gamma read not subject to the offset cap, because it does not
paginate — it names its markets.  The slate is ~77 markets, two orders of
magnitude below the catalogue, so this is cheap and bounded, and it makes the
socket's coverage independent of the catalogue sweep entirely.

This does not replace the ingest stamp.  Ingest still owns the other ~39,000
markets and every future row; this closes the gap for the small, time-critical
subset where "eventually" is not an answer.
"""

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

#: Upper bound on one top-up pass.  The fast-lane slate is ~77 markets, so this
#: is ~4x headroom rather than a real limit — it exists so that a slate query
#: that unexpectedly widens (a matching change, a busy Saturday) cannot turn one
#: socket recycle into a thousand-market Gamma sweep.  Exceeding it is LOGGED,
#: never silent: a truncated top-up that read as "nothing was missing" is the
#: same class of lie this module was written to end (gotcha #53).
MAX_TOPUP_MARKETS = 300


def condition_id_of(external_id: Optional[str]) -> Optional[str]:
    """The Gamma condition id a ``FuturesMarket.external_id`` addresses, or None.

    Polymarket sub-market rows store the bare condition id; outcome rows store it
    with a ``_yes`` / ``_no`` suffix, and a caller holding the wrong one is a
    404 (the reason `12fd2496` exists).  ``removesuffix`` rather than the
    ``rstrip("_yes")`` in that commit: ``rstrip`` takes a CHARACTER SET, so it
    eats any trailing run of ``_``/``y``/``e``/``s`` — on a hex condition id
    ending in ``e`` it silently truncates a real character.

    Returns None for parent rows, whose ``external_id`` is a Gamma EVENT id
    (a bare integer), not a condition id.  Those are addressable too, but by a
    different endpoint, and guessing which one an id is would be the bug this
    function prevents.  ``0x`` is the discriminator.
    """
    if not external_id:
        return None
    cid = external_id.removesuffix("_yes").removesuffix("_no")
    return cid if cid.startswith("0x") else None


async def topup_clob_tokens(
    session,
    markets: list[tuple[int, Optional[str]]],
    *,
    service=None,
    max_markets: int = MAX_TOPUP_MARKETS,
) -> dict[int, list[str]]:
    """Fetch and persist ``clob_token_ids`` for ``markets`` that lack them.

    ``markets`` is ``[(futures_market_id, external_id), ...]``.  Returns
    ``{futures_market_id: [token, ...]}`` for the markets that were actually
    filled, so the caller can subscribe in the same pass rather than waiting for
    the next recycle to re-read the row it just wrote.

    Writes MERGE (``COALESCE(md,'{}') || jsonb_build_object(...)``), the same
    idiom the ingest uses, so a top-up cannot clobber ``polymarket_event_id``,
    ``matchup_title`` or the venue-settled stamp that share this column.
    """
    from sqlalchemy import cast, func, literal, update
    from sqlalchemy.dialects.postgresql import JSONB

    from app.models.models import FuturesMarket

    addressable: dict[str, int] = {}
    for market_id, external_id in markets:
        cid = condition_id_of(external_id)
        if cid:
            addressable[cid] = market_id

    if not addressable:
        return {}

    if len(addressable) > max_markets:
        # Loud, not silent — and deterministic, so a repeated run makes progress
        # through the same order rather than re-drawing the same truncated slice.
        kept = sorted(addressable)[:max_markets]
        logger.warning(
            "Polymarket token top-up: %d markets needed tokens, capped at %d "
            "(%d deferred to the next recycle)",
            len(addressable),
            max_markets,
            len(addressable) - max_markets,
        )
        addressable = {cid: addressable[cid] for cid in kept}

    own_service = service is None
    if own_service:
        from app.services.polymarket_api import PolymarketAPIService

        service = PolymarketAPIService()

    try:
        # Rate-limit and server errors re-raise out of this call by design
        # (gotcha #36) — an empty list would read as "these markets have no
        # tokens", which is exactly the false negative that hid this gap.
        fetched = await service.get_markets_by_conditions(list(addressable))
    finally:
        if own_service:
            await service.close()

    filled: dict[int, list[str]] = {}
    for market in fetched:
        market_id = addressable.get(getattr(market, "condition_id", "") or "")
        if market_id is None:
            continue
        tokens = [
            str(t) for t in (getattr(market, "clob_token_ids", None) or []) if str(t)
        ]
        if not tokens:
            continue

        await session.execute(
            update(FuturesMarket)
            .where(FuturesMarket.id == market_id)
            .values(
                market_metadata=func.coalesce(
                    FuturesMarket.market_metadata,
                    cast(literal("{}"), JSONB),
                ).op("||")(
                    func.jsonb_build_object(
                        "clob_token_ids",
                        cast(literal(json.dumps(tokens)), JSONB),
                    )
                )
            )
        )
        filled[market_id] = tokens

    logger.info(
        "Polymarket token top-up: %d markets asked, %d returned by Gamma, "
        "%d stamped with tokens",
        len(addressable),
        len(fetched),
        len(filled),
    )
    return filled
