"""Ruling 025 — the availability envelope.

One vocabulary for the question *"is what you are looking at the real thing?"*::

    availability ∈ {fresh, stale, degraded, empty}

Any response that serves **fallback, stale, partial or substitute** content in
place of its primary pool must declare that state in its envelope. This module
is the vocabulary and the stamper; it is pure, imports nothing, and holds no
policy about WHICH state a given path is in — that decision belongs to the code
that did the serving, because that is the only place where the answer is known.

Clause 2, written down here because it is the trap
--------------------------------------------------
**The declaration is computed from what was SERVED. It is never mapped from
cache-metrics vocabulary** (``miss`` / ``hit`` / ``stale_hit`` / ``error``).
Those buckets have a different writer and different semantics — ``miss`` is
*fresh-but-uncached*, not ``empty`` — so no 1:1 mapping exists and none may be
built. The temptation is real because the two vocabularies are the same size and
two of the words rhyme, which is exactly why the ruling names it.

The four states
---------------
``fresh``
    The primary pool answered, inside its own freshness bound. Nothing was
    substituted.
``stale``
    A **complete** copy of the primary pool was served, but an old one — the
    content is whole, the age is the compromise. A dated last-good.
``degraded``
    What was served is **not a whole, trustworthy copy** of the primary pool:
    partial content, a substitute shape, or a copy this build could not
    validate. Complete-but-old is ``stale``; incomplete-at-any-age is
    ``degraded``.
``empty``
    Nothing was served. The honest refusal.
"""

from __future__ import annotations

from typing import Any

#: The envelope field name. One key, top level, so a consumer never has to know
#: which subsystem answered in order to find the declaration.
AVAILABILITY_FIELD = "availability"

AVAILABILITY_FRESH = "fresh"
AVAILABILITY_STALE = "stale"
AVAILABILITY_DEGRADED = "degraded"
AVAILABILITY_EMPTY = "empty"

#: Exactly four. Ruling 025 clause 5 pairs each with exactly one client
#: rendering, which only works if the set is closed.
AVAILABILITY_VALUES: frozenset[str] = frozenset(
    {
        AVAILABILITY_FRESH,
        AVAILABILITY_STALE,
        AVAILABILITY_DEGRADED,
        AVAILABILITY_EMPTY,
    }
)


def declare(payload: dict[str, Any], availability: str) -> dict[str, Any]:
    """Stamp the served state onto an outgoing payload; return a new dict.

    Raises ``ValueError`` on a state outside the vocabulary. That is deliberate:
    a typo'd or invented state is indistinguishable from an undeclared one to
    every consumer, and the whole point of the ruling is that the distinction is
    forced at the boundary rather than left to the reader.
    """
    if availability not in AVAILABILITY_VALUES:
        raise ValueError(
            f"availability {availability!r} is not one of "
            f"{sorted(AVAILABILITY_VALUES)} (ruling 025)"
        )
    out = dict(payload)
    out[AVAILABILITY_FIELD] = availability
    return out
