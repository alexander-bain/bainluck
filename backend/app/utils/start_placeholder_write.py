"""The one writer of start-placeholder tags on ``events.event_tags`` (#8841).

Split out of ``tasks/statpal_sync`` so ESPN's rails can retire the tag without
importing a task module: StatPal writes it (its placeholder), ESPN retires it
(an announced start at the same instant). One SQL statement for both.
"""

from __future__ import annotations

import json
from typing import Iterable

from sqlalchemy import text

from app.utils.start_placeholder import (
    ESPN_START_PLACEHOLDER_TAG_PREFIX,
    START_PLACEHOLDER_TAG_PREFIX,
)


#: ``event_tags`` minus every string element starting with ``:prefix`` (length
#: ``:plen``), as the database holds it at write time.
_TAGS_WITHOUT_PREFIX_SQL = (
    "COALESCE(("
    "  SELECT jsonb_agg(t) FROM jsonb_array_elements("
    "    COALESCE(event_tags, '[]'::jsonb)) AS t"
    "  WHERE NOT (jsonb_typeof(t) = 'string'"
    "             AND left(t #>> '{}', :plen) = :prefix)"
    "), '[]'::jsonb)"
)


async def write_start_placeholder_tags(
    session,
    event_id: int,
    desired: Iterable[str],
    prefix: str = START_PLACEHOLDER_TAG_PREFIX,
) -> None:
    """Replace a row's start-placeholder tags carrying ``prefix`` with ``desired``.

    ``prefix`` defaults to StatPal's; ESPN's writer passes its own (#8981), so
    each provider rewrites only its own marks.

    Core SQL with a server-side rewrite, never an ORM assignment: `event_tags`
    is JSONB (gotcha #4) and the taxonomy task replaces it wholesale, so this
    touches only elements carrying the prefix and leaves every other tag as the
    database holds it now, not as this session read it. The prefix is compared
    with `left()` and a bound value rather than `LIKE`, whose `%` inside
    `text()` is a bind-parameter trap (gotcha #45).
    """
    await session.execute(
        text(
            "UPDATE events SET event_tags = " + _TAGS_WITHOUT_PREFIX_SQL
            + " || CAST(:add AS jsonb) WHERE id = :eid"
        ),
        {
            "plen": len(prefix),
            "prefix": prefix,
            "add": json.dumps(list(desired)),
            "eid": event_id,
        },
    )


async def retire_start_placeholder_tags(session, event_id: int) -> None:
    """Drop every start-placeholder tag from the row; every other tag stays."""
    await write_start_placeholder_tags(session, event_id, [])


async def write_espn_start_placeholder_tags(
    session, event_id: int, desired: Iterable[str]
) -> None:
    """Replace a row's ESPN start-placeholder tags with ``desired`` (#8981)."""
    await write_start_placeholder_tags(
        session, event_id, desired, prefix=ESPN_START_PLACEHOLDER_TAG_PREFIX
    )


async def write_announced_start(session, event_id: int, placeholder, announced) -> bool:
    """Replace a placeholder start with ESPN's announced one (#8841).

    Compare-and-write: moves the row only while it is still scheduled and still
    carries ``placeholder``, so a rail that moved it between the read and this
    write keeps its answer. Returns whether the row moved.
    """
    result = await session.execute(
        text(
            "UPDATE events SET commence_time = :announced, "
            "commence_time_source = 'espn' "
            "WHERE id = :eid AND commence_time = :placeholder "
            "AND status = 'scheduled'"
        ),
        {"announced": announced, "placeholder": placeholder, "eid": event_id},
    )
    return (getattr(result, "rowcount", 0) or 0) == 1


async def confirm_announced_placeholder(
    session, event_id: int, instant, *, take_source: bool
) -> bool:
    """Retire StatPal's mark on a row whose stamp ESPN announced to the minute (#8841).

    Compare-and-write: lands only while the row is still scheduled at
    ``instant``, so a rail that moved it between the read and this write keeps
    its answer. ``take_source`` stamps ``commence_time_source = 'espn'`` (where
    the registry ranking lets ESPN), which is also what stops StatPal's schedule
    pass writing the mark back. Returns whether the row was written.
    """
    result = await session.execute(
        text(
            "UPDATE events SET event_tags = " + _TAGS_WITHOUT_PREFIX_SQL + ", "
            "commence_time_source = CASE WHEN :take THEN 'espn' "
            "ELSE commence_time_source END "
            "WHERE id = :eid AND commence_time = :instant "
            "AND status = 'scheduled'"
        ),
        {
            "plen": len(START_PLACEHOLDER_TAG_PREFIX),
            "prefix": START_PLACEHOLDER_TAG_PREFIX,
            "take": bool(take_source),
            "instant": instant,
            "eid": event_id,
        },
    )
    return (getattr(result, "rowcount", 0) or 0) == 1
