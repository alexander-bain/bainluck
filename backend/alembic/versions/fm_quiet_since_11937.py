"""#11937: `futures_markets.quiet_since` and the trigger that keeps it. ADDITIVE ONLY.

THE SHIP. A market that is not trading is not featured on Discover or in a
round-up (Alex, 7:42 AM PT Fri Nov 13: "If they're stale because of illiquid
trading, we just shouldn't be featuring the market").

WHY A COLUMN. Nothing stored answers "when did this market last trade":
`futures_outcomes.volume_24h` is a 24-hour figure written for Kalshi legs only,
and Polymarket rows (194 of the 236 markets on Discover on Nov 13) store no trade
activity at all. `price_changed_at` moves on mid-book changes, so it is no trade
clock. Every poll already writes the venue's 24-hour volume to
`futures_markets.volume_24h`; the first zero with no non-zero since is the
start of a quiet spell, and a spell of six days means no trade for a week.

WHAT THIS DOES, EXHAUSTIVELY:

* Adds `futures_markets.quiet_since timestamptz NULL`. Nullable with no default:
  catalog-only, no table rewrite, no backfill. Every existing row reads NULL
  (= trading or not yet observed, never stale).
* Creates the plpgsql function `keep_futures_market_quiet_since()`: on a write of
  `volume_24h`, > 0 clears the stamp, 0 keeps the first stamp or takes now(),
  NULL leaves it unchanged.
* Creates `BEFORE INSERT OR UPDATE OF volume_24h ... FOR EACH ROW` on
  `futures_markets`, so every writer is covered, including ones nobody listed.

Nothing is dropped. No existing column changes. No data is written. No index is
created (gotcha #31 does not apply).

LOCKS. `ADD COLUMN` and `CREATE TRIGGER` each take a brief lock on
`futures_markets`; neither scans the table. `alembic/env.py` sets the
connection's `lock_timeout` and wraps the batch in `run_with_lock_retry`.

The statements live in `app/utils/not_trading.py`, which the model's
`after_create` hook also runs.

MIGRATION-CLASS (D45 / notice 47b): merged only on Alex's word, and no default
fires on silence.

Reversible. The D51 undo line, which drops exactly what this adds:

    alembic downgrade open_futures_outcomes_4437

Revision ID: fm_quiet_since_11937
Revises: open_futures_outcomes_4437
Create Date: 2026-11-13
"""

from alembic import op
import sqlalchemy as sa

from app.utils.not_trading import (
    CREATE_FUNCTION_SQL,
    CREATE_TRIGGER_SQL,
    DROP_FUNCTION_SQL,
    DROP_TRIGGER_SQL,
    QUIET_COLUMN,
)

# revision identifiers, used by Alembic.
# Gotcha #1: revision ids stay <= 32 characters.
revision = "fm_quiet_since_11937"
down_revision = "open_futures_outcomes_4437"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "futures_markets",
        sa.Column(QUIET_COLUMN, sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(CREATE_FUNCTION_SQL)
    op.execute(DROP_TRIGGER_SQL)
    op.execute(CREATE_TRIGGER_SQL)


def downgrade() -> None:
    op.execute(DROP_TRIGGER_SQL)
    op.execute(DROP_FUNCTION_SQL)
    op.drop_column("futures_markets", QUIET_COLUMN)
