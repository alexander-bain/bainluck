"""The read side of ``provenance:duplicate-of:`` — one predicate, one meaning.

#2263. The registry has been able to write this tag since queue 413 and, in the
words of its own docstring, *"the drain that consumes these tags is #1946 Item 8
and does not exist yet. A tag that outruns its consumer is still the right thing
to write."* This module is the consumer that arrived first, and it is
deliberately the cheap half: it does not drain anything, it declines to PRINT a
row that has been proven to duplicate another.

That split is the point. Deleting a row is irreversible and needs a repair rail
with its own gates; declining to render a second card for one game is reversible
by reverting one predicate, and it is the whole of what the user is complaining
about. A user does not care that two rows exist. They care that tonight's
Dodgers–Tigers game is printed twice, once with a probability and once blank.

## Why a string match and not a JSONB operator

The tag is ``provenance:duplicate-of:<canonical event id>`` — the canonical id
is IN the tag, so there is no single fixed value to test containment against and
``@>`` cannot express "carries any tag with this prefix". The alternatives are
``jsonb_array_elements_text`` in a lateral, which is Postgres-only and would take
the whole guard suite off SQLite, or a cast to text and a prefix match, which is
portable and which this codebase already does for exactly this reason
(``survivor_order()`` in ``feed_event_candidates`` casts
``win_probability_sources`` to ``String`` rather than reach for a JSON operator).

The prefix cannot collide. ``provenance:duplicate-of:`` is written by one
function, :func:`app.services.anchor_channel.duplicate_tag`, and every other tag
in the vocabulary is a fixed string with no free tail.

## What this does NOT do

It does not decide anything. Every judgement about whether two rows are one game
lives at the WRITE side, in ``event_registry._proven_duplicates``, where the
evidence is. This module trusts the tag completely and by design: a reader that
re-litigates the writer's finding is a second matching implementation, and two
matchers that disagree is the failure ruling 048 exists to end.
"""

from __future__ import annotations

from sqlalchemy import String, func, or_

from app.models.models import Event
from app.services.anchor_channel import DUPLICATE_TAG_PREFIX

#: The LIKE pattern matching any `provenance:duplicate-of:<id>` element inside
#: the serialised `event_tags` array.
_DUPLICATE_TAG_LIKE = f"%{DUPLICATE_TAG_PREFIX}%"


def not_a_proven_duplicate():
    """A predicate admitting every row NOT proven to duplicate another.

    Use it in any surface that renders one card per game. It is a plain
    ``WHERE`` clause, so it composes with whatever else the surface already
    filters on and costs no join.

    ``event_tags`` is nullable and the overwhelming majority of rows carry no
    tags at all, so the NULL arm is the common case and is stated first. A bare
    ``NOT LIKE`` would drop every untagged row on the floor — ``NULL NOT LIKE x``
    is NULL, not TRUE — which would empty every rail this is added to. That is
    the whole reason this is a function and not an expression pasted into four
    call sites.
    """
    return or_(
        Event.event_tags.is_(None),
        func.cast(Event.event_tags, String).notlike(_DUPLICATE_TAG_LIKE),
    )
