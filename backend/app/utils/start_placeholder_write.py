"""The one writer of start-placeholder tags on ``events.event_tags`` (#8841).

Split out of ``tasks/statpal_sync`` so ESPN's rails can retire the tag without
importing a task module: StatPal writes it (its placeholder), ESPN retires it
(an announced start at the same instant). One SQL statement for both.
"""

from __future__ import annotations

import json
from typing import Iterable

from sqlalchemy import text

from app.utils.start_placeholder import START_PLACEHOLDER_TAG_PREFIX


async def write_start_placeholder_tags(session, event_id: int, desired: Iterable[str]) -> None:
    """Replace a row's start-placeholder tags with ``desired``.

    Core SQL with a server-side rewrite, never an ORM assignment: `event_tags`
    is JSONB (gotcha #4) and the taxonomy task replaces it wholesale, so this
    touches only elements carrying the prefix and leaves every other tag as the
    database holds it now, not as this session read it. The prefix is compared
    with `left()` and a bound value rather than `LIKE`, whose `%` inside
    `text()` is a bind-parameter trap (gotcha #45).
    """
    await session.execute(
        text(
            "UPDATE events SET event_tags = COALESCE(("
            "  SELECT jsonb_agg(t) FROM jsonb_array_elements("
            "    COALESCE(event_tags, '[]'::jsonb)) AS t"
            "  WHERE NOT (jsonb_typeof(t) = 'string'"
            "             AND left(t #>> '{}', :plen) = :prefix)"
            "), '[]'::jsonb) || CAST(:add AS jsonb) "
            "WHERE id = :eid"
        ),
        {
            "plen": len(START_PLACEHOLDER_TAG_PREFIX),
            "prefix": START_PLACEHOLDER_TAG_PREFIX,
            "add": json.dumps(list(desired)),
            "eid": event_id,
        },
    )


async def retire_start_placeholder_tags(session, event_id: int) -> None:
    """Drop every start-placeholder tag from the row; every other tag stays."""
    await write_start_placeholder_tags(session, event_id, [])
