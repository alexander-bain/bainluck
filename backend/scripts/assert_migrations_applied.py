"""Fail the release if the database is not at Alembic head (#2741, #2724).

WHY THIS EXISTS

``backend/Procfile``'s release command is::

    python3 -c "import check" && (alembic upgrade heads || echo "…") && THIS

The ``|| echo`` swallows **every** Alembic failure, not just the multiple-heads
case its message names (#2741, found by CERT-784). A migration that raises,
deadlocks, hits a constraint violation — or, since #2724, **exhausts its
lock_timeout retries** — prints one line and the release SUCCEEDS. The web dyno
then boots new code against the old schema, and the reader gets
``UndefinedColumn`` on every request: the same blank page the lock work exists
to prevent, except this one does not clear on its own.

That trade is why CERT-789 blocked the lock_timeout work. Bounding the wait
makes exhaustion the *expected* outcome of exactly the 377–440 s contention
being fixed, so the swallowed-failure path stops being theoretical.

WHY A SEPARATE STEP RATHER THAN DELETING THE ``|| echo``

Deleting it changes deploy behaviour for every lane and #2741 asks for a ruling
before that happens. This step needs no ruling to be safe: it is purely
additive, it cannot fail a release whose migrations actually applied, and it
leaves Alembic's own error text on stdout for context before failing. If the
ruling later removes the ``|| echo``, this stays useful — it is the assertion
that the release ACTUALLY reached head, which an exit code alone does not give.

WHAT IT CHECKS

The revision recorded in ``alembic_version`` against the head(s) of the script
directory. Equal ⇒ exit 0. Anything else ⇒ exit 1, naming both sides.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from alembic.config import Config  # noqa: E402
from alembic.runtime.migration import MigrationContext  # noqa: E402
from alembic.script import ScriptDirectory  # noqa: E402
from sqlalchemy import create_engine, pool  # noqa: E402

from app.utils.migration_lock_budget import (  # noqa: E402
    lock_timeout_option,
    psycopg2_url,
)

#: The guard runs immediately after a migration that may have been fighting for
#: locks. It gets its own bounded timeouts so a release can never hang HERE —
#: a watchdog that can wedge is the defect it was written to catch.
PROBE_TIMEOUT_MS = 10_000


def _database_url() -> str:
    return psycopg2_url(
        os.getenv(
            "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/bainluck"
        )
    )


def _connect_args(url: str) -> dict:
    connect_args = {
        "options": (
            f"{lock_timeout_option(PROBE_TIMEOUT_MS)} "
            f"-c statement_timeout={PROBE_TIMEOUT_MS}"
        )
    }
    if "localhost" not in url and "127.0.0.1" not in url:
        connect_args["sslmode"] = "require"
    return connect_args


def script_heads(alembic_ini: str) -> set[str]:
    """The head revision(s) Alembic's script directory declares."""
    config = Config(alembic_ini)
    return set(ScriptDirectory.from_config(config).get_heads())


def database_revisions(url: str) -> set[str]:
    """The revision(s) the database records as applied."""
    engine = create_engine(url, poolclass=pool.NullPool, connect_args=_connect_args(url))
    try:
        with engine.connect() as connection:
            return set(MigrationContext.configure(connection).get_current_heads())
    finally:
        engine.dispose()


def describe(applied: set[str], heads: set[str]) -> str:
    """The operator-facing verdict. Names BOTH sides, always."""
    if applied == heads:
        return f"OK: database is at Alembic head ({', '.join(sorted(heads)) or 'none'})"
    missing = sorted(heads - applied)
    extra = sorted(applied - heads)
    lines = [
        "RELEASE FAILED: the database is NOT at Alembic head.",
        f"  script head(s): {', '.join(sorted(heads)) or '(none)'}",
        f"  database has:   {', '.join(sorted(applied)) or '(none)'}",
    ]
    if missing:
        lines.append(f"  never applied:  {', '.join(missing)}")
    if extra:
        lines.append(f"  unknown to this build: {', '.join(extra)}")
    lines.append("")
    lines.append(
        "The `alembic upgrade heads` above did not finish. Its error is printed "
        "there; the `|| echo` in the Procfile hid its exit code (#2741), so this "
        "step is what stops new code booting against the old schema."
    )
    lines.append(
        "If it exhausted its lock retries (#2724), a long-running transaction "
        "held the table. Re-run the deploy; raise ALEMBIC_LOCK_TIMEOUT_MS or "
        "ALEMBIC_LOCK_ATTEMPTS only if it keeps losing the race."
    )
    return "\n".join(lines)


def main() -> int:
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    applied = database_revisions(_database_url())
    heads = script_heads(os.path.join(here, "alembic.ini"))
    message = describe(applied, heads)
    print(message)
    return 0 if applied == heads else 1


if __name__ == "__main__":
    sys.exit(main())
