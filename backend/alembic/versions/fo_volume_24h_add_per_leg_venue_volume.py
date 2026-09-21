"""#7747 step 1: `futures_outcomes.volume_24h` / `.volume_24h_at` — per-leg venue trade activity. ADDITIVE ONLY.

WHY THIS COLUMN EXISTS, and it is the answer to two graded BLOCKs rather than a
design preference. #7747's ship is *"the board stops crowning Jakub Mensik at 74%
— a price whose own book bids four cents and whose venue reports zero 24-hour
volume — while every leg someone is ACTUALLY trading at its ask keeps its
number."* Two serve-time-only attempts at that sentence were falsified against
the venue:

* **CERT-3242** — the first cut refused every price printing at its own ask over
  a wide spread. The grader read Kalshi and found four such legs being traded at
  that ask right then (Tunisia 0.79 / $87.67 24h, Gambia 0.80 / $54.43, Cameron
  Dicker 0.52 / $9.30, Davante Adams 0.85 / $6.10). A price at the ask is not
  evidence of nothing.
* **CERT-3244** — the repair substituted *price-movement* recency
  (``last_updated - price_changed_at``) for *execution* recency. The grader
  falsified that too: a market can trade repeatedly at an unchanged price.
  Egypt 70% (48.5h static, $8.73 of 24h volume), Arch Manning 60% (308h static,
  $3.24) and Congo Republic 70% (48.5h, $0.04) are all traded and all would have
  been withheld.

🔴 THE REASON BOTH FAILED IS A MISSING COLUMN, NOT A BADLY CHOSEN THRESHOLD, and
that was established by measurement rather than inferred. On production
2026-09-21 the specimen and all three counterexamples are near-identical in every
column we store — ``KXATP-27USO-MEN`` 0.04/0.74, ``…EGYANG-EGY`` 0.10/0.70,
``…NAMCOG-COG`` 0.10/0.70, ``…TEXAMAN`` 0.00/0.60, every one of them at its own
ask across a wide spread, every ``futures_outcomes.volume`` NULL. Time does not
separate them either: Manning is 308h static and trading, Mensik 70h static and
not. **No stored field distinguishes a leg that is being traded at its ask from
one that is not**, so no serve-time predicate over existing columns can express
the ship's own criterion. The evidence exists only at the venue, and
``KalshiMarket.volume_24h`` already parses it (``services/kalshi_api.py``,
including the ``volume_24h_fp`` form) — it is fetched on every poll today and
then dropped on the floor.

Neither existing volume column answers it, also measured rather than assumed:

* ``futures_outcomes.volume`` is LIFETIME volume in contracts, written only on
  the ingest INSERT (``tasks/kalshi.py``; the conflict path is "a RESOLUTION
  write or it is nothing"), so it is NULL on all four legs and never refreshed.
  A lifetime figure cannot answer a 24-hour question in any case.
* ``futures_markets.volume_24h`` is the BOARD's figure, and it does not separate
  the cases: Mensik's board reads **1** (stamped fresh, 10:52Z) while Egypt's and
  Congo's read **NULL**. A board aggregates every leg on it, so a quiet leg on a
  busy field is invisible to it — which is exactly the specimen's shape.

🔴 AND IT IS ``Numeric(14, 2)``, NOT AN INTEGER, WHICH IS NOT A TASTE CALL —
AN INTEGER COLUMN WOULD CONVERT ONE OF THE COUNTEREXAMPLES INTO A WITHHOLD. Kalshi
reports this figure as a two-decimal fixed-point string (``volume_24h_fp``), and
the smallest non-zero value in the falsifying set is Congo Republic's **$0.04**.
Rounded or truncated to an integer that is **0** — which is precisely the value
the consumer treats as proof that nobody is trading the leg. So the narrow column
does not merely lose precision; it manufactures the exact false reading CERT-3244
BLOCKed this ship for. The scale and precision follow
``FuturesMarket.liquidity``'s ``Numeric(14, 2)``, the existing column for a
two-decimal venue money figure. (``FuturesMarket.volume_24h`` is BigInteger and
is a different thing — a per-board SUM used only for internal ranking, where a
sub-unit remainder changes nothing and a false zero harms no reader.)

WHAT THIS DOES, EXHAUSTIVELY. Adds TWO nullable columns with no server default to
``futures_outcomes``: ``volume_24h`` (``Numeric(14, 2)``) and ``volume_24h_at``
(timestamptz). **Nothing is altered. Nothing is dropped. No existing column
changes type, nullability or default. No data is written, moved or backfilled.
No index is created.** Nothing in the application reads or writes either one yet
— the capture (``tasks/futures_price_refresh``) and the read
(``utils/futures_unsupported_price``) are a separate, non-DDL ship that follows
this one.

WHY IT IS ALONE IN ITS COMMIT. Exactly the ``search_log_origin`` precedent
(#1916 step 2): D45 makes any ``alembic/`` diff attended, and the code halves
must not wait on Alex's clock. The follow-up ship is ordinary Tier-2 work the
moment the column exists.

WHY TWO COLUMNS AND NOT ONE. The stamp is not decoration, and the whole BLOCK
chain above is the argument for it. ``volume_24h`` alone would have to borrow
``last_updated`` as its freshness, and ``last_updated`` is a touch-stamp several
writers move for reasons that have nothing to do with a volume read (the
resolution writes in ``tasks/kalshi.py``, the withdrawal clears). A zero volume
read three days ago sitting under a ``last_updated`` advanced this morning by a
different writer reads as *"the venue says nobody is trading this, measured
minutes ago"* — a self-sealing lie in the withholding direction. #2024 added
``price_changed_at`` for precisely this conflation and this ship was BLOCKed
twice for committing versions of it; the stamp records when the volume figure was
OBSERVED and nothing else.

🔴 INSTANT ON A 5,079,690-ROW TABLE, and that is worth stating because the row
count invites the opposite assumption. ``ADD COLUMN ... NULL`` with **no default**
is a catalog-only change in PostgreSQL 11+ — no table rewrite, no backfill, no
full-table lock held for the scan — so this does not approach the ~5-minute
Heroku release timeout that gotcha #31 exists for. That gotcha is about
``CREATE INDEX``; no index is created here, and if one is ever wanted it goes via
``psql`` CONCURRENTLY, never from this file.

Reversible. The D51 undo line, which drops exactly the two columns this adds and
nothing else:

    alembic downgrade search_log_origin

Revision ID: fo_volume_24h
Revises: search_log_origin
Create Date: 2026-09-21
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
# Gotcha #1: revision ids stay <= 32 characters.
revision = "fo_volume_24h"
down_revision = "search_log_origin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "futures_outcomes",
        sa.Column("volume_24h", sa.Numeric(14, 2), nullable=True),
    )
    op.add_column(
        "futures_outcomes",
        sa.Column("volume_24h_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("futures_outcomes", "volume_24h_at")
    op.drop_column("futures_outcomes", "volume_24h")
