"""One authority for "is this child settled?" — ruling 036 in a single operator.

Every concept adapter renders children (fights on a card, rounds of a tournament,
stages of a grand tour, matches in a draw, categories at a ceremony, races in an
election) and every one of them has to decide whether a child is still an open
question. Six adapters answered that question, and until #1803 not one of them
asked the event.

THE DEFECT THIS MODULE EXISTS TO MAKE UNREPRESENTABLE
-----------------------------------------------------
The only settled signal a futures-sourced child ever got was **price
convergence**: the leader is at/above 0.97 (or at/below 0.03), so the question
must be decided. It fails on exactly the questions it most needs to grade.
MEASURED on production ``v3790``: ``event:ufc:26aug08`` (fought 2026-08-09, card
status ``settled``) still rendered "Johns vs Rosas" at 0.54/0.44 and a KO prop at
0.505/0.495. Both are coin flips — the furthest a price can be from convergence.

**A fight that ends at a coin flip never converges, so the markets that resolved
LEAST cleanly are precisely the ones that keep looking live.** Inference fails
worst where it matters most, which is why widening the inference is not the fix —
widening it is how this bug got here.

THE SHAPE (ruling 036, ratified by Alex 2026-08-12 as the standing shape for
every settledness path)
---------------------------------------------------------------------------
The event's **assigned** state is combined with ``or`` / ``max()`` and **never
substituted**. An event in play has ``assigned_settled`` False and the result is
bit-for-bit the inference it has always been, so the dangerous direction —
suppressing a market that is genuinely live — is *unrepresentable* rather than
merely unintended. A reviewer confirms it by reading one operator instead of
re-deriving a case analysis.

THE SUBTLETY, AND IT IS THE WHOLE REASON THIS IS A FUNCTION AND NOT A CONVENTION
-------------------------------------------------------------------------------
**Monotonicity protects the DIRECTION, not the INPUT.** ``or`` guarantees the new
term can only ever *add* settledness relative to the old inference. It does not
make the term *true*. Pass something price-derived as ``assigned_settled`` and the
guarantee is intact while the answer is wrong — with a brand-new failure mode:
one runaway favourite marking every sibling settled while they are undecided.

This bit almost every caller. In ``event_awards`` and ``event_election``,
``event_status`` is itself computed from the same convergence test
(``event_awards.py`` / ``event_election.py``, the ``marquee_top >= 0.97`` arms), so
the obvious "OR in ``event_status``" would chain two inferences and call it
assigned state. **The term must be assigned, not merely available**, which is why
each caller passes an explicitly-named term and ``tests/test_settledness_authority``
asserts that none of them passes a price-derived one.

WHICH ASSIGNED TERM — the parent settles its children only when it is ATOMIC IN TIME
------------------------------------------------------------------------------------
A fight card, a golf tournament, a grand tour and a ceremony each conclude as one
thing: when the parent is over, every child was played. A slam is the same — a
concluded draw means every match happened. An **election is not**: races decide
independently and runoffs run weeks past election night, so a graded marquee race
says nothing about a down-ballot one. Election children therefore consult only
their *own* assigned state, and ``test_a_graded_parent_does_not_settle_an_ungraded
_election_child`` pins that asymmetry.

Callers: ``event_combat.fight_child_settled``, ``event_cycling``, ``event_tennis``,
``event_awards``, ``event_election``. ``routes/golf._completed_round_ceiling`` is the
same shape over an ``int`` ceiling rather than a ``bool`` and keeps its own
``max()`` — see its docstring.
"""

from __future__ import annotations

# The convergence band. A leader at/above HIGH (or at/below LOW) is *inferred*
# decided. Display-only and never authoritative (gotcha #21): authoritative
# grading is ``is_winner``, and Kalshi leaves settled markets ``status='open'``
# (gotcha #33), which is the reason an inference was ever needed here.
CONVERGED_HIGH = 0.97
CONVERGED_LOW = 0.03

# Statuses that are an ASSIGNED settlement — the source telling us the question is
# closed, rather than us deducing it from a number. One-way: presence means
# settled, absence means unknown (gotcha #33), which is exactly what a monotone
# ``or`` term wants.
ASSIGNED_SETTLED_STATUSES = frozenset({"resolved", "closed", "settled", "final"})


def price_converged(lead_prob: float | None) -> bool:
    """The INFERENCE, named so call sites stop re-typing the band.

    True when the leading outcome has run to an extreme. This is the test that
    fails on coin flips; it is kept because for a card/tournament still in play it
    is the only signal there is, and it is the exact behaviour every adapter had
    before #1803.
    """
    if lead_prob is None:
        return False
    return lead_prob >= CONVERGED_HIGH or lead_prob <= CONVERGED_LOW


def market_assigned_settled(market, outcomes=None) -> bool:
    """The per-child ASSIGNED term: this market's own status, or its own grade.

    Two signals, both authoritative and neither price-derived:

    * ``market.status`` in :data:`ASSIGNED_SETTLED_STATUSES` — the source closed it.
    * any outcome with ``is_winner`` set — the source graded it. Authoritative
      (gotcha #21), and the one that matters most in practice because Kalshi
      settled markets keep ``status='open'`` (gotcha #33).

    ``outcomes`` may be passed when the caller has already filtered field and
    placeholder rows; otherwise ``market.outcomes`` is read. Defensive about
    attribute absence so a partially-loaded ORM row degrades to "unknown" (False)
    rather than raising inside a page build — a lookup must never throw the page.
    """
    status = (getattr(market, "status", None) or "").lower()
    if status in ASSIGNED_SETTLED_STATUSES:
        return True
    rows = outcomes if outcomes is not None else (getattr(market, "outcomes", None) or [])
    return any(bool(getattr(o, "is_winner", False)) for o in rows)


def settled_under_assigned_state(inferred: bool, assigned_settled: bool) -> bool:
    """Ruling 036's monotone combinator. The argument order is the point.

    ``assigned_settled`` is authoritative and comes first; ``inferred`` is the
    fallback for an event still in play. Combined with ``or``, never substituted,
    so this can only ever make a child MORE settled and never less.

    Do not "simplify" this to an inline ``or`` at the call sites. It was inline at
    six of them, which is how three adapters ended up never adding the term at
    all, and how the two that did ended up with a test that *transcribed* the
    expression instead of binding the source.
    """
    return bool(assigned_settled) or bool(inferred)
