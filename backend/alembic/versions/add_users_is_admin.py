"""Add ``users.is_admin`` — a server-side admin role on the user row.

Queue 386 Item 2, Alex ruling 2026-08-20: *Alex's Google-authenticated session
should unlock `/admin/labeling` without the pasted admin secret.*

## Why a column and not another env var

Admin identity already existed before this revision, but it lived in
``DEFAULT_ADMIN_USER_IDS = {364}`` in ``app/routes/admin_utils.py`` plus the
``ADMIN_USER_IDS`` / ``ADMIN_USER_EMAILS`` env vars. Three problems with that
shape, all of which a column removes:

1. **A hardcoded integer is a grant nobody can audit.** ``{364}`` is a user id in
   a Python set in a routes module. There is no query that answers *who is an
   admin right now* — you have to read source and env at the same time.
2. **Env config drifts per-dyno.** ``ADMIN_USER_IDS`` is read at request time by
   whichever process serves the request. The web dyno and a worker can disagree
   about who is an admin, and nothing surfaces the disagreement.
3. **Revocation is a deploy.** Removing an id from a set means shipping code;
   removing a row's flag is one UPDATE that takes effect on the next request.

The legacy allowlists are deliberately KEPT as a fallback in
``_user_is_admin`` — this revision must not be able to lock Alex out of the
admin UI in the window between the release and the grant.

## Why the grant is NOT in this migration

There is no ``UPDATE users SET is_admin = true`` below, and that absence is the
point. A migration that writes a privilege grant is a privilege escalation
shipped inside a diff reviewed as schema. It would also be wrong in the ordinary
way: migrations run against every environment, so a hardcoded user id would
grant admin to whatever row happens to hold that id in a restored or seeded
database.

Alex grants it with one statement, documented in ``docs/admin-identity.md``:

    UPDATE users SET is_admin = true WHERE lower(email) = lower('<his email>');

## Shape of the column

``BOOLEAN NOT NULL DEFAULT false``. On PostgreSQL 11+ an ``ADD COLUMN`` with a
non-volatile default is a catalog-only change — no table rewrite, no scan — so
this is safe inside Heroku's ~5-minute release phase even though ``users`` is a
live table (gotcha #31's concern is index builds and rewrites; this is neither).

``NOT NULL`` rather than nullable-with-default: a three-valued admin flag has a
``NULL`` state that reads as "unknown", and the only safe reading of an unknown
privilege is *denied* — which is what ``false`` already says, unambiguously, at
every call site without a coalesce anyone can forget.

No index. The column is only ever read by primary key or by ``firebase_uid``
lookup, both of which are already indexed; an index on a boolean whose
selectivity is "one row out of all of them" would never be chosen anyway.

Revision ID: add_users_is_admin
Revises: add_prov_play_value
Create Date: 2026-08-20
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic. (<=32 chars — gotcha #1.)
revision = "add_users_is_admin"
down_revision = "add_prov_play_value"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "is_admin",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "is_admin")
