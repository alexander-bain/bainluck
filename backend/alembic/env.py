"""Alembic migration environment."""

import logging
import os
from logging.config import fileConfig

from pathlib import Path

from alembic import context
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, pool, text

from app.services.database import Base
from app.utils.migration_lock_budget import (
    MigrationLockSettings,
    batch_is_retryable,
    contention_kind,
    lock_timeout_option,
    psycopg2_url,
    resolve_settings,
    run_with_lock_retry,
)
from app.models import *  # noqa: Import all models

# Alembic Config object
config = context.config

# Set up logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Model metadata for autogenerate
target_metadata = Base.metadata

# Get database URL from environment. Normalising Heroku's postgres:// and
# stripping +asyncpg (migrations run on psycopg2) is shared with the
# release-phase guard `scripts/assert_migrations_applied.py` -- two copies could
# drift, and a guard that checks a DIFFERENT database than the migration ran on
# is worse than no guard.
DATABASE_URL = psycopg2_url(
    os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/bainluck")
)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def _base_connect_args() -> dict:
    connect_args = {}
    if "localhost" not in DATABASE_URL and "127.0.0.1" not in DATABASE_URL:
        connect_args["sslmode"] = "require"
    return connect_args


def _make_engine(connect_args: dict):
    return create_engine(
        DATABASE_URL,
        poolclass=pool.NullPool,
        connect_args=connect_args,
    )


def _read_alembic_version(probe_timeout_ms: int = 5_000):
    """The recorded revision, read on a connection of its own.

    Called after a failed attempt, when the migration's own connection is in an
    aborted transaction and can answer nothing. Any failure to read is reported
    as ``None`` rather than raised: this runs on the error path, and a probe
    that can itself explode would replace a legible lock timeout with a
    confusing secondary error.

    It carries its own ``lock_timeout`` AND ``statement_timeout`` because it
    runs during exactly the contention it is reporting on. An unbounded probe
    would be free to hang for the minutes this whole change exists to prevent —
    the diagnostic reintroducing the defect it diagnoses.
    """
    connect_args = _base_connect_args()
    connect_args["options"] = (
        f"{lock_timeout_option(probe_timeout_ms)} "
        f"-c statement_timeout={int(probe_timeout_ms)}"
    )
    engine = _make_engine(connect_args)
    try:
        with engine.connect() as connection:
            row = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).first()
            return row[0] if row else None
    except Exception:  # noqa: BLE001 - see docstring; the error path must not raise
        return None
    finally:
        engine.dispose()


def _pending_migration_sources(current_revision):
    """Source text of every migration this run would apply, or None if unknown.

    ``None`` is a real answer, not an error swallowed: :func:`batch_is_retryable`
    treats "cannot tell" as "do not retry". Failing closed here is deliberate —
    the retry is a convenience, and the safety it depends on is not.
    """
    try:
        script = ScriptDirectory.from_config(config)
        return [
            Path(revision.path).read_text(encoding="utf-8")
            for revision in script.iterate_revisions("heads", current_revision)
            if revision.path
        ]
    except Exception:  # noqa: BLE001 - see docstring; unknown must not raise
        return None


def run_migrations_online() -> None:
    """Run migrations in 'online' mode using synchronous psycopg2.

    Migrations run under a bounded ``lock_timeout`` so that an ``ALTER TABLE``
    which cannot get its lock aborts instead of queueing — a pending
    ``ACCESS EXCLUSIVE`` blocks every later reader of that table, which is how
    one contended migration blanked Discover for seven minutes (#2724). A
    deadlock is retried on the same terms as a timeout — Postgres rolls the
    victim's whole transaction back, so the same "nothing committed" proof
    applies — but the cure for one is the ORDER, enforced by
    ``app/utils/migration_lock_order`` (#2782). Full mechanism and the retry's
    safety argument: ``app/utils/migration_lock_budget``.
    """
    settings = resolve_settings(os.environ)
    if not batch_is_retryable(_pending_migration_sources(_read_alembic_version())):
        # A pending script commits before Alembic stamps the version, or we
        # could not tell. Either way the version-unchanged check cannot prove
        # nothing landed, so the retry is dropped rather than trusted.
        settings = MigrationLockSettings(
            lock_timeout_ms=settings.lock_timeout_ms, attempts=1, backoff_ms=0
        )

    connect_args = _base_connect_args()
    connect_args["options"] = lock_timeout_option(settings.lock_timeout_ms)

    def attempt_once() -> None:
        connectable = _make_engine(connect_args)
        try:
            with connectable.connect() as connection:
                context.configure(
                    connection=connection, target_metadata=target_metadata
                )

                with context.begin_transaction():
                    context.run_migrations()
        finally:
            connectable.dispose()

    def on_retry(attempt: int, version, exc: BaseException) -> None:
        # Naming the kind is the point: `lock_timeout` is a straggler and the
        # next attempt may well win, `deadlock` is a lock-order inversion in the
        # migration itself (#2782) and the retry is only buying time.
        logging.getLogger("alembic.runtime.migration").warning(
            "#2724 migration attempt %s/%s hit %s (lock_timeout=%sms) with "
            "alembic_version unchanged at %s; retrying in %.1fs",
            attempt,
            settings.attempts,
            contention_kind(exc),
            settings.lock_timeout_ms,
            version,
            settings.backoff_s,
        )

    run_with_lock_retry(
        attempt_once,
        settings,
        read_version=_read_alembic_version,
        on_retry=on_retry,
    )


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
