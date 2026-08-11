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


#: How reassuring each state is to a reader, most reassuring first. This is an
#: ordering over the VOCABULARY — not a policy about which state a path is in —
#: which is why it lives beside the words rather than in any one route.
_STRENGTH: dict[str, int] = {
    AVAILABILITY_FRESH: 3,
    AVAILABILITY_STALE: 2,
    AVAILABILITY_DEGRADED: 1,
    AVAILABILITY_EMPTY: 0,
}


def never_stronger(current: str | None, proposed: str) -> str:
    """Clamp ``proposed`` so a re-wrap can weaken a declaration but never heal one.

    A payload can be re-wrapped on its way out — a fallback tier picks up a copy
    some earlier tier already classified, stamps its own ``cache`` block on it
    and declares again. That second declaration is computed from what the
    FALLBACK knows (this copy is old), and it does not know what the first tier
    knew (this copy was never validated). Letting it win means an incomplete
    payload correctly labelled ``degraded`` comes out the far side labelled
    ``stale`` — and ``stale`` promises, by this module's own definition, a
    *whole* copy whose only compromise is age. The content did not change; only
    the claim about it improved, which is the one direction a re-wrap must never
    move.

    This is gotcha #53 in the availability vocabulary: two paths produce the same
    word for different reasons, and the ambiguity resolves toward the more
    reassuring reading unless something forbids it. This forbids it.

    ``current`` is what the payload already claims (``None`` when it claims
    nothing). An unreadable value is treated as no claim: it tells a consumer
    exactly as little as an absent one, and inventing a rank for it would be a
    second guess on top of a typo.

    ``empty`` is deliberately not a claim content can make. It means *nothing was
    served*, so a dict that is on its way to a client contradicts it; honouring
    it would emit a body full of numbers declared absent. A payload carrying it
    is treated as claiming nothing.
    """
    proposed_rank = _STRENGTH.get(proposed)
    if current is None or proposed_rank is None:
        # An invalid ``proposed`` is returned untouched so ``declare`` raises the
        # precise ValueError about it, rather than this clamp dying first with a
        # KeyError that names nothing.
        return proposed
    current_rank = _STRENGTH.get(current)
    if current_rank is None or current == AVAILABILITY_EMPTY:
        return proposed
    return current if current_rank < proposed_rank else proposed


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
