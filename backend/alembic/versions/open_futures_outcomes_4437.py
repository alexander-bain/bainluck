"""#4437 Decide 89-A: a narrow table of OPEN markets' outcome names, with a trigram index.

THE SHIP. A first keystroke whose letters appear in outcome names ("chi",
"mid") stops reading ``futures_outcomes`` — 9.4 GB, 8.8 M rows, about 95% of
them on closed markets — so the dropdown and the Search page can answer it in
under a second. Alex ruled 89-A on Sun Nov 8, 5:57 AM PT.

WHAT THIS DOES, EXHAUSTIVELY.

* Creates one new, empty table ``open_futures_outcomes``: one row per outcome of
  a market whose status is ``open`` — the outcome's id, its market's id and its
  name, nothing else. ``app.tasks.open_futures_outcomes`` fills and maintains it.
* Creates its b-tree index on ``market_id`` and its pg_trgm GIN on ``name``
  (``pg_trgm`` is already installed: ``ix_futures_outcomes_name_trgm``). Both are
  built on an EMPTY table, so gotcha #31 has nothing to apply to.

No existing table, column or index changes. No foreign key: the maintainer
deletes rows whose market closed, and readers re-check every market against
``futures_markets`` exactly as before.

READERS FALL BACK. The dropdown and the Search page read this table only while
the maintainer has completed a full pass recently (its Redis state, see
``app.utils.open_futures_outcomes``); stale, empty or absent, they use today's
``futures_outcomes`` lookup unchanged.

MIGRATION-CLASS (D45 / notice 47b): landed on Alex's 89-A.

Reversible. The undo line is

    alembic downgrade ranking_slates_12095

which drops the table and its two indexes. Set ``OPEN_FUTURES_OUTCOMES_READ=0``
first, so no request is mid-read when it goes.

Revision ID: open_futures_outcomes_4437
Revises: ranking_slates_12095
Create Date: 2026-11-08
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
# Gotcha #1: revision ids stay <= 32 characters.
revision = "open_futures_outcomes_4437"
down_revision = "ranking_slates_12095"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "open_futures_outcomes",
        sa.Column("outcome_id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
    )
    op.create_index(
        "ix_open_futures_outcomes_market_id", "open_futures_outcomes", ["market_id"]
    )
    op.create_index(
        "ix_open_futures_outcomes_name_trgm",
        "open_futures_outcomes",
        ["name"],
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
        # Light writes, hot reads: no pending list to sawtooth the reads
        # (lat-p109's measurement on `futures_outcomes`).
        postgresql_with={"fastupdate": "off"},
    )


def downgrade() -> None:
    op.drop_index("ix_open_futures_outcomes_name_trgm", table_name="open_futures_outcomes")
    op.drop_index("ix_open_futures_outcomes_market_id", table_name="open_futures_outcomes")
    op.drop_table("open_futures_outcomes")
