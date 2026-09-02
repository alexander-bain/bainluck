"""Preserve Kalshi's legal backstop in its own column: `futures_markets.expiration_time`.

CAL-P989 (#2660, #1818). One nullable timestamp column, no backfill, no index, no
data touched. The column is created EMPTY and stays empty until the Kalshi poller
next writes each row.

## What this unblocks

The poller wrote `resolution_date = max(expiration_time)` — Kalshi's LATEST
POSSIBLE expiry, a legal backstop, not a schedule. Measured live 2026-09-02 over a
179-event sample of the 10,187 Kalshi rows that are `status='open'` with a future
`resolution_date`: of the 49 already finalized at the venue, **0** have a stored
date in the past. That is why `status != 'resolved' AND past resolution_date`
selects none of them, and why Discover kept selling a golf round that settled five
days earlier. Switching `resolution_date` to `max(close_time)` makes 39 of those 49
visible and moves **zero** still-active markets into the past.

This revision is the "no data loss" half of that switch: the backstop keeps its own
column, so consumers that genuinely want "the last date this could possibly
resolve" still have it and CAL-P061's 421/421 provenance reproduction stays
checkable. Rationale and the full measurement live in
`app/utils/kalshi_resolution_window.py`.

## Why this is a safe release-phase migration

`ADD COLUMN ... NULL` with **no** default is a catalogue-only change in
PostgreSQL — it does not rewrite `futures_markets` (~268k rows) and does not scan
it. No index is created, so gotcha #31 (Heroku's ~5 min release timeout on
`CREATE INDEX`) is not in play at all. Nothing here backfills; populating the
column is the poller's job on its ordinary 2h cadence, and the one-off catch-up
for existing rows is a separate attended script, deliberately not a migration.

Gotcha #1: revision id is 27 characters, under the 32-char Alembic limit.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "kalshi_expiration_backstop"
down_revision = "add_image_dimensions"  # re-read from `alembic heads` against origin/master 9e8d6ea6
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "futures_markets",
        sa.Column("expiration_time", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("futures_markets", "expiration_time")
