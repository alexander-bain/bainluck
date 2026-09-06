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


#: The ``events`` table's own vocabulary, which is NOT the card vocabulary above.
#: A row is ``scheduled``/``live``/``suspended``/``completed``/``closed``; a card
#: is ``upcoming``/``live``/``settled``. Downgrading an event row to
#: ``"upcoming"`` would emit a status no client parses, so the two need different
#: fallbacks and this is the one place that difference is written down.
#:
#: ``suspended`` (live/048) passes through here VERBATIM, and that is the correct
#: behaviour rather than an omission: this rule only ever downgrades a premature
#: ``live``, and a suspended row makes no claim about being played, so there is
#: nothing for the invariant to catch.
EVENT_NOT_STARTED = "scheduled"


#: The event statuses a row may hold and still be a match someone could be
#: watching. An ALLOWLIST, deliberately, and it lives here beside the vocabulary
#: it is drawn from rather than in the one surface that first needed it.
#:
#: UX-P180 (#2167), repairing CERT-1987. That rail shipped the complement —
#: ``status != "completed"`` — which is the same shape of mistake as every
#: retirement-marker bug in this codebase: it enumerates what to reject, so every
#: status nobody thought of is admitted by default. Measured on production
#: 2026-09-05, that default was not a rounding error:
#:
#:     closed      212,289      <- the dominant terminal state, all admitted
#:     completed    15,731      <- the only one the denylist caught
#:     scheduled     2,252
#:     suspended     1,608
#:     live             98
#:     voided            66     <- a retirement marker, admitted
#:     merged            22     <- a retirement marker, admitted
#:
#: ``closed`` is what a definitive StatPal completion writes, so the rail was
#: excluding the RARE terminal state and admitting the common one.
#:
#: ``suspended`` IS playable and is included: it is a rain delay, not an ending,
#: and the row makes no claim about being over (see the note above). It is not
#: exempt from a caller's clock floor, though — a match suspended three days ago
#: is not on now, and only ``live`` should ever bypass a freshness test.
EVENT_PLAYABLE_STATUSES = frozenset({"live", "scheduled", "suspended"})


def event_is_playable(status: str | None) -> bool:
    """Could this event row be a match someone is watching or waiting for?

    Allowlist semantics: an unrecognised status is NOT playable. A new terminal
    state added upstream must fail closed here rather than silently start
    rendering as a fixture.
    """
    return status in EVENT_PLAYABLE_STATUSES


def served_event_status(status: str | None, commence_time, now: datetime) -> str | None:
    """The status a PUBLIC surface may show for an event row. Pure.

    Same invariant as :func:`enforce_live_requires_start`, in the ``events``
    vocabulary. Every public serializer that emits ``event.status`` goes through
    this; admin surfaces deliberately do NOT, because an operator debugging a
    contradictory row must see the contradiction rather than a repaired reading.

    MEASURED 2026-08-17 (queue 364, #1779 family) — the reason this exists as a
    consumed function and not only as a declared rule. Four MLB events were
    serving ``status: "live"`` with live scores while their own
    ``commence_time`` sat **40–51 hours in the future**:

        15199901  Detroit @ Pittsburgh   commence 2026-08-19 16:35Z  live 0–5
        15199882  San Diego @ NY Mets    commence 2026-08-19 17:10Z  live 2–1
        15200229  Arizona @ Boston       commence 2026-08-19 20:10Z  live 4–0
        15199886  Miami @ Philadelphia   commence 2026-08-19 22:05Z  live 4–1

    Each is a second row for a game that also exists at its correct Aug-17 time,
    with the same ``espn_id`` and the same score. The invariant they violate was
    already written, already correct, and had **zero callers**:
    ``enforce_live_requires_start`` shipped as "one canonical rule for every
    surface" and no surface imported it. A rule with no consumer is a document.

    This is the staleness cardinal sin inverted — not stale-when-live but
    live-when-not-started — and it is the same class as gotcha #46's
    ``completed_at >= commence_time``, which IS guarded. The forward-facing twin
    was not.
    """
    return enforce_live_requires_start(
        status, commence_time, now, fallback=EVENT_NOT_STARTED
    )
