"""SQLite adapter for price-predicate tests, not database-clock certification.

These tests execute the production UPDATE and inspect stored prices/row counts.
PostgreSQL clock authority and transaction timing belong to the real-PG tests.
"""

from sqlalchemy import event
from sqlalchemy.engine import Engine

FIXED_DATABASE_CLOCK = "2026-01-01T12:00:00+00:00"


def install_returned_clock(engine: Engine) -> None:
    """Add only the missing function to this fixture's SQLite connections."""
    assert engine.dialect.name == "sqlite"

    @event.listens_for(engine, "connect")
    def register_clock(connection, _record):
        connection.create_function(
            "clock_timestamp", 0, lambda: FIXED_DATABASE_CLOCK
        )
