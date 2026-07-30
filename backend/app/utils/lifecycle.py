"""Shared lifecycle time-ordering invariant (Queue 283 / C81 real-world-lifecycle).

One canonical rule for every surface that labels a card/event/concept "live":

    live  =>  now >= authoritative start/commence time

A card may be labeled ``live`` ONLY once its authoritative start time has passed.
Unknown or unparseable start authority is NOT sufficient to establish live — it
fails to ``upcoming`` (never live). This module is import-safe (stdlib only) so
every classifier and the Flow Sentinel can share the exact same predicate rather
than re-deriving it (the drift that let combat/winner-field cards read "live"
before their event started, and the Flow Sentinel finding on #1483).

The rule is deliberately narrow: it only ever DOWNGRADES a proposed ``live`` to
``upcoming``. It never invents ``settled``, never reads price/title/model
knowledge, and leaves already-correct ``upcoming``/``settled`` states untouched.
"""

from __future__ import annotations

from datetime import datetime


def live_start_satisfied(start, now: datetime) -> bool:
    """True iff ``start`` is a known, comparable time that is at or before ``now``.

    Missing (None) or non-comparable start authority returns False — the
    invariant's "unknown time authority never establishes live" clause.
    """
    if start is None:
        return False
    try:
        return start <= now
    except TypeError:
        # tz-naive vs tz-aware, wrong type, etc. — cannot prove the event
        # started, so it is not live.
        return False


def enforce_live_requires_start(
    state: str | None,
    start,
    now: datetime,
    *,
    fallback: str = "upcoming",
) -> str | None:
    """Return ``state`` unchanged unless it claims ``live`` before its start.

    Only ``"live"`` is ever rewritten (to ``fallback``); every other state
    passes through verbatim so this can wrap any classifier without altering
    upcoming/settled/unmeasured decisions.
    """
    if state == "live" and not live_start_satisfied(start, now):
        return fallback
    return state
