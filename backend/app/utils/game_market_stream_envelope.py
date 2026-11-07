"""Loaded-input identity and clocks for held embedded markets (#9524).

Row revision is ordering metadata, never quote freshness. Observations come
from the existing builder's real price observation map, not last_updated.
"""
from datetime import datetime, timezone
from typing import Iterable, Mapping

from app.utils.market_quote_push import SOURCES
from app.utils.settledness import ASSIGNED_SETTLED_STATUSES


def stream_admits(source: object, status: object, has_winner: bool) -> bool:
    """Whether `/api/markets/stream` will hold this market open (#12283).

    The one predicate: the stream route admits by it, and the envelope only
    names markets it would admit. A venue market that is not settled and has no
    graded winner; never the linked game's phase.
    """
    return (
        source in SOURCES
        and str(status or "").lower() not in ASSIGNED_SETTLED_STATUSES
        and not has_winner
    )


def _positive_id(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def _stamp(value):
    if not isinstance(value, datetime):
        return None
    return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()


def game_market_stream_envelope(
    market_ids: Iterable[int],
    outcomes: Iterable[object],
    observed_at: Mapping[int, datetime],
    markets: Iterable[object] | None = None,
) -> dict:
    """Keep withheld markets subscribed; bind every loaded outcome, not just top rows.

    #12283: with `markets` given, `stream_market_ids` names only the markets the
    stream would admit. A finished NBA game (15342680, Nov 7) served 423 ids, all
    settled; the page opened nine 50-id streams, the route answered 409 to each
    and 429 to the ninth. A settled market is still BOUND (its outcomes keep their
    clocks for the reconciler); it is just never subscribed to.
    """
    outcomes = list(outcomes)
    ids = sorted({value for raw in market_ids if (value := _positive_id(raw)) is not None})
    selected = set(ids)
    streamed = ids
    if markets is not None:
        won = {vars(o).get("market_id") for o in outcomes if vars(o).get("is_winner") is True}
        fields = {vars(m).get("id"): vars(m) for m in markets}
        streamed = [
            mid for mid in ids
            if mid in fields
            and stream_admits(fields[mid].get("source"), fields[mid].get("status"), mid in won)
        ]
    bindings = {}
    revisions = {}
    observations = {}
    for outcome in outcomes:
        # Already-loaded scalar fields only: never a lazy ORM read/new query.
        fields = vars(outcome)
        outcome_id = _positive_id(fields.get("id"))
        market_id = _positive_id(fields.get("market_id"))
        if outcome_id is None or market_id not in selected:
            continue
        key = str(outcome_id)
        bindings[key] = market_id
        revisions[key] = _stamp(fields.get("last_updated"))
        observations[key] = _stamp(observed_at.get(outcome_id))
    return {"stream_market_ids": streamed, "outcome_market_ids": bindings,
            "outcome_revision_at": revisions, "outcome_observed_at": observations}
