"""#4437 Decide 89-A: when a request may read ``open_futures_outcomes``, and how.

THE SHIP. A dropdown or Search keystroke whose letters appear in outcome names
("chi", "mid") matched them across ``futures_outcomes`` — 9.4 GB, 8.8 M rows,
about 95% on closed markets. "chi" read ~67 k matching outcomes to keep ~1,200
open markets (Nov 7: over 20 s as written, 8.5 s at best rewritten). Over the
open markets' outcomes alone (~262 k rows) the same match is a small one.

THE CONTRACT, which is what makes a second copy safe to read:

* **Only while maintained.** ``app.tasks.open_futures_outcomes`` writes
  :data:`STATE_KEY` after every pass, with a TTL of :data:`STALE_AFTER_SECONDS`.
  No state, a state older than that, a state whose first full cycle has not
  finished, or ``OPEN_FUTURES_OUTCOMES_READ=0``: :func:`open_outcomes_floor`
  returns ``None`` and every caller builds today's ``futures_outcomes`` lookup,
  unchanged.
* **Never behind on new outcomes.** Outcomes with an id above the state's
  ``reader_floor`` (the watermark of the pass BEFORE the latest, so one whole
  pass of slack for a row committed late) are matched on ``futures_outcomes``
  directly, by primary-key range, beside the copy.
* **Name predicates only.** :func:`on_open_outcomes` moves a predicate onto the
  copy only when it reads nothing of ``futures_outcomes`` but ``name``; anything
  else (a price floor, a team anchor) keeps the original lookup, or verifies its
  candidates on the real rows (:func:`outcome_ids_named`).
* **Markets are re-checked as before.** The copy only nominates market ids; every
  caller's own ``futures_markets`` predicates (open, not past, not played) still
  decide, so a market that closed since the last pass never shows.

What the copy can lag, by at most one rotation of the task (an hour): an outcome
RENAMED in place, or a market that REOPENED with outcomes it already had.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

from sqlalchemy import select, union_all
from sqlalchemy.sql.visitors import iterate, replacement_traverse

from app.models.models import FuturesOutcome, OpenFuturesOutcome

logger = logging.getLogger(__name__)

#: The maintainer's state: ``{"watermark", "reader_floor", "pass_at", "cycle_complete"}``.
STATE_KEY = "bainluck:open_futures_outcomes:state"

#: A copy whose last pass is older than this is not read. Three missed 5-minute
#: passes; the key is also written with this TTL, so a stopped maintainer
#: expires its own state.
STALE_AFTER_SECONDS = 900

#: How long a process keeps a state it read before asking Redis again.
_STATE_MEMO_SECONDS = 20.0

_memo: dict[str, Any] = {"at": None, "state": None}


def read_enabled() -> bool:
    """``OPEN_FUTURES_OUTCOMES_READ`` (default on): the operator's off switch."""
    return os.getenv("OPEN_FUTURES_OUTCOMES_READ", "1").strip().lower() not in {"0", "false", "off", "no"}


def _fetch_state() -> dict | None:
    try:
        from app.tasks.redis_state import get_redis_client

        raw = get_redis_client(fast_fail=True).get(STATE_KEY)
    except Exception as exc:  # noqa: BLE001 — no state is "read the original"
        logger.warning("open_futures_outcomes state unreadable: %s", exc)
        return None
    if not raw:
        return None
    try:
        state = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return state if isinstance(state, dict) else None


def _state() -> dict | None:
    now = time.monotonic()
    at = _memo["at"]
    if at is None or now - at >= _STATE_MEMO_SECONDS:
        _memo["state"] = _fetch_state()
        _memo["at"] = now
    return _memo["state"]


def state_is_servable(state: dict | None, *, now: float | None = None) -> bool:
    """Whether a maintainer state lets a request read the copy."""
    if not isinstance(state, dict) or not state.get("cycle_complete"):
        return False
    pass_at = state.get("pass_at")
    floor = state.get("reader_floor")
    if not isinstance(pass_at, (int, float)) or not isinstance(floor, int):
        return False
    return ((time.time() if now is None else now) - pass_at) < STALE_AFTER_SECONDS


def open_outcomes_floor() -> int | None:
    """The outcome id above which ``futures_outcomes`` is read directly, or ``None``.

    ``None`` means: do not read the copy; build the original lookup.
    """
    if not read_enabled():
        return None
    state = _state()
    if not state_is_servable(state):
        return None
    return int(state["reader_floor"])


_FO = FuturesOutcome.__table__
_OFO = OpenFuturesOutcome.__table__


def _futures_outcome_columns(expr) -> set[str]:
    return {el.key for el in iterate(expr) if getattr(el, "table", None) is _FO}


def on_open_outcomes(expr):
    """``expr`` with ``futures_outcomes.name`` read from the copy, or ``None``.

    ``None`` when the predicate reads any other ``futures_outcomes`` column: the
    copy carries names only, and a price or a team anchor is never guessed.
    """
    if _futures_outcome_columns(expr) - {"name"}:
        return None

    def _swap(el):
        if getattr(el, "table", None) is _FO and getattr(el, "key", None) == "name":
            return _OFO.c.name
        return None

    return replacement_traverse(expr, {}, _swap)


def market_ids_with_outcome(*outcome_where):
    """``SELECT market_id`` of outcomes matching ``outcome_where``, over the copy.

    The copy's rows UNION ALL the outcomes newer than the reader floor, matched
    on ``futures_outcomes`` itself. ``None`` = build the original lookup (the copy
    is not servable, or a predicate reads more than the name).
    """
    floor = open_outcomes_floor()
    if floor is None or not outcome_where:
        return None
    moved = [on_open_outcomes(w) for w in outcome_where]
    if any(m is None for m in moved):
        return None
    return union_all(
        select(_OFO.c.market_id).where(*moved),
        select(FuturesOutcome.market_id).where(FuturesOutcome.id > floor, *outcome_where),
    )


def outcome_ids_named(name_where):
    """``SELECT outcome id`` of outcomes whose NAME matches, over the copy; or ``None``.

    For a lookup that needs more than the name (the headline-contender lane's
    price floor and team anchor): it keeps every predicate on the real
    ``futures_outcomes`` rows and adds ``id = ANY(this)``, so the trigram match
    runs over open markets only and the rest is a primary-key read of the
    candidates.
    """
    floor = open_outcomes_floor()
    if floor is None:
        return None
    moved = on_open_outcomes(name_where)
    if moved is None:
        return None
    return union_all(
        select(_OFO.c.outcome_id).where(moved),
        select(FuturesOutcome.id).where(FuturesOutcome.id > floor, name_where),
    )
