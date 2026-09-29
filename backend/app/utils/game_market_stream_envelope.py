"""Loaded-input identity and clocks for held embedded markets (#9524).

Row revision is ordering metadata, never quote freshness. Observations come
from the existing builder's real price observation map, not last_updated.
"""
from datetime import datetime, timezone
from typing import Iterable, Mapping


def _positive_id(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def _stamp(value):
    if not isinstance(value, datetime):
        return None
    return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()


def game_market_stream_envelope(
    market_ids: Iterable[int], outcomes: Iterable[object], observed_at: Mapping[int, datetime]
) -> dict:
    """Keep withheld markets subscribed; bind every loaded outcome, not just top rows."""
    ids = sorted({value for raw in market_ids if (value := _positive_id(raw)) is not None})
    selected = set(ids)
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
    return {"stream_market_ids": ids, "outcome_market_ids": bindings,
            "outcome_revision_at": revisions, "outcome_observed_at": observations}
