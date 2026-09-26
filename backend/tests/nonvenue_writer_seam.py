"""Portable write seam for existing SQLite/recording-session producer rule tests.

The atomic PostgreSQL write, transaction fanout and clock chain are exercised
without this seam in integration/test_nonvenue_live_push_pg_8761.py.
"""

from sqlalchemy import inspect, update
from sqlalchemy.orm.attributes import set_committed_value

from app.models.models import Event
from app.utils.aggregation import stamp_source_reading


async def portable_nonvenue_write(
    session, event, source, value, *, metadata=None, values=None
):
    if value is None:
        sources = dict(event.win_probability_sources or {})
        sources.pop(source, None)
    else:
        sources = stamp_source_reading(event.win_probability_sources, source, value)
    sources.update(metadata or {})
    await session.execute(
        update(Event)
        .where(Event.id == event.id)
        .values(
            win_probability_sources=sources,
            **(values or {}),
        )
    )
    if inspect(event, raiseerr=False) is not None:
        set_committed_value(event, "win_probability_sources", sources)
    else:
        event.win_probability_sources = sources
    return sources
