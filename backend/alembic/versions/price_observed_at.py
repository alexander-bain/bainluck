"""`futures_outcomes.price_observed_at` — the last SUCCESSFUL price observation.

#3879. ADDITIVE ONLY: one nullable column, no index, no data written.

WHY A THIRD CLOCK, WHEN THE ROW ALREADY HAS TWO. Because neither of the two
answers the question the staleness ship has to be measured on, and the audit
that proves it is already in the tree:

* ``last_updated`` is the TOUCH stamp — "a writer last wrote this row". Its
  writers include ``backfill_winners`` (seven ``last_updated = NOW()`` sites
  accompanying ``is_winner`` / ``resolution_source``), so a leg whose price has
  not been read since August reads FRESH the moment a settlement sweep grades
  it. ``routes/playoffs.py`` gates the playoff grid on this column and
  ``tests/test_futures_stamp_semantics.py`` pins that coupling: it may not be
  narrowed.
* ``price_changed_at`` (#2024) is the MOVEMENT stamp — "the stored number last
  became a different number". A price correctly read from the venue every two
  minutes and correctly unchanged all week leaves it a week old. Read as
  freshness it condemns the healthiest rows on the board.

So freshness is a third question and it gets a third column, for the same
reason #2024 refused to narrow ``last_updated``: two readings of one column is
the disease, not the cure.

WHAT THE COLUMN MEANS, EXACTLY. The instant at which a writer last held a
REAL price for this outcome, obtained from the venue. Not "a poll ran", not
"the number moved" — "we looked, and there was a price, and this is when".
``app/utils/price_change_stamp.py`` owns the one expression that maintains it
and states the three refusals (no price is not an observation; the stamp is the
instant OBSERVED, not the instant WRITTEN; it never moves backwards).

🔴 NULL MEANS UNKNOWN AND IS NEVER BACKFILLED — gotcha #53, and here the
refusal is also the instrument. The obvious backfill is
``MAX(futures_odds_snapshots.captured_at)`` per outcome, which is what
``routes/tournaments._price_observed_at`` already maxes at serve time for the
462 register-pinned markets. Two reasons it is not run here:

  1. ``futures_odds_snapshots`` is **202,149,344 rows / 53 GB** (measured
     2026-09-08). A grouped scan of it is not a release-phase operation and is
     not an unattended one either.
  2. It would destroy the measurement. The column populates FORWARD from the
     price writers, so after one full poll cycle (Kalshi 2 h, Polymarket 1 h)
     a leg still reading NULL is precisely a leg **no price rail reaches** —
     which is #3879's entire finding, stated by the data instead of inferred
     from it. A backfilled value would paper exactly that population over.

Consumers must therefore read NULL as "not observed since 2026-09-08", never as
"stale forever" and never as "fresh".

NO INDEX, DELIBERATELY (gotcha #31, the May 22 outage). ``futures_outcomes`` is
**5,457,987 rows / 5,557 MB** (measured 2026-09-08). A non-concurrent
``CREATE INDEX`` on it takes an ACCESS EXCLUSIVE lock for minutes and the
Heroku release phase times out at ~5. ``CONCURRENTLY`` is forbidden in Alembic
for the same reason. The consumer this column is built for is a periodic census
run by the measurement lane, for which a parallel seq scan measured 3.2 s — an
index buys nothing that is needed and costs an outage to install. If a
latency-sensitive reader ever appears, the index goes in by ``psql``, which is
the documented path.

DEPLOY SAFETY. One ``ADD COLUMN`` of a NULLABLE ``timestamptz`` with **no
default**, which in Postgres 11+ is a catalogue-only update — no table rewrite,
no matter the row count. The ACCESS EXCLUSIVE lock is held for the catalogue
write alone; the price polls that upsert this table will block for
milliseconds.

THE UNDO LINE, which ships with it (D51):

    alembic downgrade containers_phase1

and what that runs is exactly ``DROP COLUMN futures_outcomes.price_observed_at``.
Because the column is new and every value in it is written by this program's own
writers, the downgrade destroys no pre-existing data.

Revision ID: price_observed_at
Revises: containers_phase1
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic. Gotcha #1: <=32 characters.
revision: str = "price_observed_at"
down_revision: str = "containers_phase1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "futures_outcomes",
        sa.Column("price_observed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("futures_outcomes", "price_observed_at")
