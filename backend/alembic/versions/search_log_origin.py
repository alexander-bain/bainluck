"""#1916 step 2: `search_query_logs.origin` — provenance recorded at write time. ADDITIVE ONLY.

Design is #1916's own §Design item 2, and the column name was agreed in writing
with the latency lane (`runner-inbox/latency/FROM-lane1-219-agreed-the-column-is-origin-…`)
before anything was built: **`origin`**, not `agent`, because the channel that
feeds it is already named that everywhere it exists — `_ORIGIN_HEADER =
"x-bainluck-origin"` (`app/routes/events.py`), `_ORIGIN_USER`, LAT-P118's
"ORIGIN CHANNEL". A second name for a shipped channel is a second thing to learn.

WHAT THIS DOES, EXHAUSTIVELY. Adds TWO nullable columns with no server default to
``search_query_logs`` — ``origin`` (#1916) and ``top_result_kind`` (#4836).
**Nothing is altered. Nothing is dropped. No existing column changes type,
nullability or default. No data is written, moved or backfilled.** No index is
created. Nothing in the application reads or writes either one yet — both write
sites are separate, non-DDL ships that follow this one (#1916 step 1 for
``origin``; latency's #4836 for ``top_result_kind``), which is why this migration
is alone in its commit: D45 makes an ``alembic/`` diff attended, and the code
halves must not wait on Alex's clock.

WHY TWO COLUMNS IN ONE MIGRATION, when #1916's column was built alone. latency/313
asked for ``top_result_kind`` at 2026-09-10 10:25 PT, while this migration was
still open and attended
(``runner-inbox/lane1/FROM-latency-313-1025PT-…``). Two additive columns on ONE
table, landed separately, cost two Alembic heads and — because D45 makes every
``alembic/`` diff attended — **two of Alex's attended merge slots for one table**.
One migration is strictly cheaper for the same result, and folding it in hides
nothing: this sha is attended either way, so Alex sees both columns before it
merges. The split of work is latency's proposal and notice 6's rule — the DDL is
on #1916, so it is lane1's; the write site in
``routes/events.py::_record_search_query`` is latency's follow-up.

WHY ``top_result_kind`` IS ITS OWN COLUMN AND NOT A WIDER ``top_result_id``.
``top_result_id`` reads ``results[0].id``, and ``results`` is the EVENTS array
only. Search answers out of four sections, so a search led by a team or a futures
market records no top result at all — **556 of 1,261 answered searches (44%) over
7 days carry a NULL ``top_result_id``** (latency, measured on production).
LAT-P117 left it that way on purpose: writing a ``futures_markets`` id into a
column that otherwise holds ``events`` ids is ambiguous across two tables, which
is worse than the NULL. A discriminator column ends the ambiguity instead of
deepening it. ``String(32)`` comfortably holds the longest planned value,
``'event_concept'`` (13).

THE UNDO LINE, which ships with it (D51):

    alembic downgrade containers_phase1

and what that runs is exactly ``ALTER TABLE search_query_logs DROP COLUMN
top_result_kind`` then ``… DROP COLUMN origin``. Both columns are new and every
row's value is NULL until the stamps ship, so the downgrade destroys no
pre-existing data.

WHY NULLABLE WITH NO SERVER DEFAULT, AND WHY NO BACKFILL — this is gotcha #53's
shape and it is the whole point of the column. #1916's acceptance is that
"``user`` is a positive assertion, not a default-by-absence". A server default of
``'user'`` would stamp every pre-existing row — and every future unstamped writer
— as a human, which is precisely the false reading the issue exists to end. So:

    NULL   = "written before the stamp existed, or by a writer that does not
              stamp" — unknown, and readable as unknown.
    'user' = a request that arrived with no automation assertion on a path that
              stamps — an assertion this system made, deliberately.

The existing consumer proxy is ``session_id IS NOT NULL OR user_id IS NOT NULL``
(``tasks/search_head_warmer.py``'s ``_USER_HEAD_SQL``). That is attestation
inferred from a side effect of client code, not provenance; it is why LAT-P102
could only say 13 of 4,257 rows were attested. This column replaces the inference
with a record. Nothing switches over in this commit.

DEPLOY SAFETY (gotcha #31, the May 22 outage). Two ``ADD COLUMN``s, each of a
NULLABLE column with **no default**, which in Postgres 11+ is a catalogue-only
update — no table rewrite, no scan, and both run inside the one migration's
single transaction. ``search_query_logs`` held 6,725 rows when this was
written (measured 2026-09-10 00:56Z), so even a rewrite would be trivial; the
real cost is an ACCESS EXCLUSIVE lock held for the catalogue update alone. The
table's only writer is ``/search``'s fire-and-forget logger, which swallows its
own errors, so a blocked write for milliseconds cannot surface to a user. The
Heroku release phase's ~5-minute timeout is not in play and no ``CONCURRENTLY``
is needed or permitted.

WHY ``String(64)`` AND NO INDEX. 64 is the truncation bound the stamp will apply
to the verbatim header value, so the column cannot refuse a write the route
accepted (a guard that refuses to store freezes the old value — the opposite of
what an append-only log is for). No index: the consumers group over a 30-day
window on a 6.7k-row table and already scan it; an index here would be a cost
with no measured reader.

Revision ID: search_log_origin
Revises: containers_phase1
Create Date: 2026-09-10
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic. `search_log_origin` is 17 characters,
# inside the 32-character limit (gotcha #1).
revision = "search_log_origin"
down_revision = "containers_phase1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "search_query_logs",
        sa.Column("origin", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "search_query_logs",
        sa.Column("top_result_kind", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("search_query_logs", "top_result_kind")
    op.drop_column("search_query_logs", "origin")
