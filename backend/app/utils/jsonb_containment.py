"""One correct way to write a JSONB ``@>`` containment filter.

## The defect this module exists to prevent

Every taxonomy-tag filter in the app was silently matching nothing. The
expression looked right:

    Event.event_tags.op("@>")(cast(json.dumps(["sport:soccer"]), JSONB))

`cast()` with a bare Python value builds a ``BindParameter`` whose *type* is
the cast target — here ``JSONB`` — and ``JSONB`` has a bind processor that
serializes the value with ``json.dumps``. The value handed to it was ALREADY a
JSON string, so it was serialized a second time and went on the wire as::

    '"[\\"sport:soccer\\"]"'

which is not a JSON *array* at all, but a JSON *string scalar* whose text
happens to look like an array. PostgreSQL then evaluated::

    '["sport:soccer"]'::jsonb @> '"[\\"sport:soccer\\"]"'::jsonb   -->  false

`@>` is total on well-formed JSONB, so there is no error, no warning and no
log line — just zero rows, forever, for every tag in every namespace.

## Why it was invisible

The statement is valid SQL over real columns, the tags really are on the rows
(48,834 open futures carry a ``sport:*`` tag; every active event carries one),
and the identical predicate typed by hand into a SQL console returns the rows.
Nothing short of inspecting the *post-bind-processor* wire value shows it.

What it cost: `/api/feed?tags=[...]` served zero events and zero futures for
every static tag, so all 29 `/categories/<slug>` pages rendered empty while the
`/categories` index card above them advertised up to 9,191 markets, and the
"More Like This" section never appeared on any event or futures detail page.

## The fix, and the two ways to spell it

Both of these put the correct bytes on the wire:

    cast(literal(json.dumps(value)), JSONB)   # text -> PG parses it
    cast(value, JSONB)                        # list -> serialized ONCE

``literal()`` is what makes the first one work: it pins the bind's type to
``String``, so the JSONB bind processor never runs. That is the idiom already
used correctly elsewhere in the repo (``tasks/entity_seed.py``,
``services/entity_registry.py``), which is why this helper spells it that way.

Callers should use `jsonb_contains()` rather than either spelling by hand — the
difference between the working and broken forms is one function call, and it is
not visible at a glance.

Guards: `tests/test_jsonb_containment_bind.py` (this helper's wire value, plus
the repo-wide static net for the broken spelling) and
`tests/integration/test_feed_static_tag_filter.py` (the route arm — a pure-lib
guard stays green if someone deletes the call site).
"""

import json
from typing import Any

from sqlalchemy import cast, literal
from sqlalchemy.dialects.postgresql import JSONB


def jsonb_contains(column: Any, value: Any) -> Any:
    """Build ``column @> <value>`` with a correctly-encoded JSONB bind.

    ``value`` is a plain Python object (typically a list of tag strings). It is
    serialized exactly once — see the module docstring for what happens when it
    is serialized twice.
    """
    return column.op("@>")(cast(literal(json.dumps(value)), JSONB))
