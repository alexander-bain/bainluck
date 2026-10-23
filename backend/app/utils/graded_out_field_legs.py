"""#11493 — a leg of a still-open FIELD the venue has already knocked out.

Production, 2026-10-23 10:44Z: ``/api/feed`` served "MLB World Series Champion
2026" (polymarket 114584, ``status: open``) as Brewers 64% · Rays 37% ·
**Houston Astros 1%**. The same card feeds Discover, the futures page's "More
baseball" rail and the app. Twenty-nine of its thirty clubs are stored
``is_winner false`` + ``resolution_source 'api_settlement'``: the venue graded
them out and kept a residue quote (Astros 0.005), which still sorts into the
card's top three. The two clubs still playing carry ``resolution_source NULL``.

So the card drops a leg the venue has authoritatively graded out of an open
field, the way a graded leg the venue stops pricing already leaves it. The test
is the one Search's out cell reads (``frontend/lib/openFieldLegOut.ts``, itself
the backend's ``_outcome_is_settled`` for an open market):

* **Open field only.** ``status == 'open'`` and ``market_type == 'field'``. A
  settled board is a result and shows what ran; a ladder rung or a Yes/No side
  graded false is not a contender eliminated.
* **An authoritative grade, never a bare ``false``.** ``is_winner`` defaults to
  FALSE, so it cannot tell "lost" from "nobody looked"; the source must be tier 3
  (``AUTHORITATIVE_SOURCES``). The retraction and the guess family earn nothing.
* **A price that admits the loss.** At or above ``TERMINAL_LOSER_CEILING`` the
  book still prices it as a live contender and the leg stays (#4597 residue).
* **Fails open.** A failed read drops nothing, and a verdict that would empty the
  card keeps every leg.

The cached feed path rebuilds legs without ``is_winner`` / ``resolution_source``
(``futures_market_snapshot.OUTCOME_COLUMNS``), so the grade is read here by
primary key once per scoring pass (one SELECT per ``CHUNK`` ids), over only the
legs whose price could admit it — the ``_team_names_by_id`` shape, nothing added
to the size-capped artifact.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

from sqlalchemy import select

from app.models.models import FuturesOutcome
from app.utils.market_shape import SHAPE_FIELD
from app.utils.resolution_authority import AUTHORITATIVE_SOURCES

logger = logging.getLogger(__name__)

#: Mirror of ``_TERMINAL_LOSER_CEILING`` in ``routes/league_futures.py``.
TERMINAL_LOSER_CEILING = 0.20

#: Ids per SELECT. Well under asyncpg's 32,767 bind parameters, so no pool can
#: raise on size and leave the request's transaction aborted. Measured on
#: production 2026-10-23: 1,000 candidate ids from the 150 busiest open fields
#: read in 5-40 ms warm on the primary key.
CHUNK = 5000


def _is_open_field(market) -> bool:
    values = market.__dict__
    return values.get("status") == "open" and values.get("market_type") == SHAPE_FIELD


def _price_admits_loss(outcome) -> bool:
    price = outcome.__dict__.get("current_probability")
    return price is None or float(price) < TERMINAL_LOSER_CEILING


def candidate_leg_ids(markets: Iterable) -> dict[int, int]:
    """``{outcome id: market id}`` for the legs whose grade could drop them."""
    return {
        outcome.id: market.id
        for market in markets
        if _is_open_field(market)
        for outcome in market.outcomes
        if _price_admits_loss(outcome)
    }


async def graded_out_leg_ids_by_market(
    db, markets: Iterable
) -> dict[int, frozenset[int]]:
    """``{market id: outcome ids graded out}`` for this pool. Never raises."""
    try:
        candidates = candidate_leg_ids(markets)
        if not candidates:
            return {}
        ids = list(candidates)
        out: dict[int, set[int]] = {}
        for start in range(0, len(ids), CHUNK):
            result = await db.execute(
                select(FuturesOutcome.id).where(
                    FuturesOutcome.id.in_(ids[start : start + CHUNK]),
                    FuturesOutcome.is_winner.is_(False),
                    FuturesOutcome.resolution_source.in_(AUTHORITATIVE_SOURCES),
                )
            )
            for (outcome_id,) in result.all():
                out.setdefault(candidates[outcome_id], set()).add(outcome_id)
        return {market_id: frozenset(ids) for market_id, ids in out.items()}
    except Exception:
        logger.warning("graded-out legs read failed; every leg stays", exc_info=True)
        return {}


def drop_graded_out_legs(outcomes: list, out_ids: frozenset[int] | None) -> list:
    """``outcomes`` without the legs graded out; every leg if none would survive."""
    if not out_ids:
        return outcomes
    survivors = [o for o in outcomes if o.id not in out_ids]
    return survivors or outcomes
