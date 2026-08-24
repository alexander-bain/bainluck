"""Add ``users.is_admin`` — a server-side admin role on the user row.

Queue 386 Item 2, Alex ruling 2026-08-20: *Alex's Google-authenticated session
should unlock `/admin/labeling` without the pasted admin secret.*

**AMENDED IN PLACE 2026-08-21 (Queue 390): the column went from ``BOOLEAN NOT
NULL DEFAULT false`` to nullable, and the three-valued reading below is the
amended one, not the original.** Legitimate because this revision has never run
in production — gotcha #8 binds revisions that HAVE run. Full reasoning, and the
by-command evidence for "never run", are in the ``## AMENDED`` section further
down. Read that section before reasoning about why this column has no default.
Blessed by Fable, queue 391 item 2a, 2026-08-22.

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

``BOOLEAN NULL``, no server default. On PostgreSQL 11+ an ``ADD COLUMN`` that is
nullable with no default is a catalog-only change — no table rewrite, no scan —
so this is safe inside Heroku's ~5-minute release phase even though ``users`` is
a live table (gotcha #31's concern is index builds and rewrites; this is neither).

## AMENDED 2026-08-21 (Queue 390) — this column was ``BOOLEAN NOT NULL DEFAULT
false`` and had to become nullable

The original argued: *"a three-valued admin flag has a NULL state that reads as
'unknown', and the only safe reading of an unknown privilege is denied — which is
what false already says."* That reasoning is correct about a column read ALONE,
and wrong about this one, because ``_user_is_admin`` OR-s the legacy allowlists
after it. ``C-2063-REVIEW`` finding 2 (P1) executed the consequence: with
``DEFAULT_ADMIN_USER_IDS = {364}``, a row at ``id=364, is_admin=False`` still
resolved to ``{is_admin: true, via: "identity"}``. The documented revoke
statement — the entire justification for preferring a column over an env var —
did nothing to the only row anyone would ever run it on.

Two states cannot fix that. Make ``false`` terminal and every pre-existing row
reads ``false`` on release day, which locks out the legacy admins during exactly
the rollout window the allowlists were kept for. So the column carries three
states and ``NULL`` is load-bearing:

* ``true``  — granted.
* ``false`` — REVOKED; the allowlists do not get a vote.
* ``NULL``  — no decision recorded; the allowlists still apply.

No coalesce is forgettable here because there is exactly one reader,
``_user_is_admin``, and its three branches are pinned by
``tests/test_admin_identity_auth_q390_r2.py`` in both directions.

**This revision has never run in production** — ``SELECT is_admin FROM users``
answers ``undefined_column`` against the live database, checked by command on
2026-08-21 — so it is amended in place rather than superseded by a follow-up
``ALTER``. Gotcha #8 bans deleting or rewriting migrations that have ALREADY run;
this one has not, and shipping an ``ALTER`` to fix a column the same PR
introduces would be archaeology for a future reader.

No index. The column is only ever read by primary key or by ``firebase_uid``
lookup, both of which are already indexed; an index on a boolean whose
selectivity is "one row out of all of them" would never be chosen anyway.

## RE-POINTED 2026-08-24 (queue 395) — ``down_revision`` moved from
## ``add_prov_play_value`` to ``anchors_and_captures``

This revision and ``anchors_and_captures`` (PR #2119, the folded #1946 slot) both
declared ``down_revision = "add_prov_play_value"``. Each is a valid single-head
extension **in isolation**, which is exactly why both CIs were green and neither
could see the other: CI runs one branch's tree, and one branch's tree contains
one of these files. Merging both leaves two heads, and Alembic refuses to
upgrade from an ambiguous head — so the second PR to merge would have failed the
**Heroku release phase**. That is an outage, not a red build, and it would have
arrived at merge time with nothing on either PR predicting it. Measured, not
reasoned about: with both files in one tree at ``origin/master``,
``pytest tests/test_alembic.py`` exits **1** with
``Multiple alembic heads detected: ['add_users_is_admin', 'anchors_and_captures']``
(queue 394, REPORT 394 item 5).

**Why this file moved and not the other one.** The re-point decides merge ORDER,
and the order is not a preference here — ``anchors_and_captures`` is under a hard
external date. Kalshi retention (``app/utils/kalshi_retention.py``) makes 1,202
markets permanently unverifiable on **2026-08-28**, and the settlement-capture
sweep cannot write a row until its table exists. This column is under no clock at
all. So #2119 goes first and this revision chains behind it.

**The consequence, stated plainly so a future reader is not surprised:** this
revision now has a parent that only exists on PR #2119. It is **unrunnable until
#2119 merges** — that is the intended coupling, not an accident, and it is the
cheaper failure of the two (a migration that cannot start is visible before it
runs; two heads are discovered by the release phase in production). If #2119 is
ever abandoned rather than merged, this ``down_revision`` must be moved back to
whatever master's head is at that time — do **not** merge this PR first and fix
it afterwards.

Revision ID: add_users_is_admin
Revises: anchors_and_captures
Create Date: 2026-08-20
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic. (<=32 chars — gotcha #1.)
revision = "add_users_is_admin"
# RE-POINTED 2026-08-24 (queue 395): was "add_prov_play_value", which collided with
# `anchors_and_captures` (#2119) on the same parent. See the RE-POINTED section above.
# This revision cannot run until #2119 merges — deliberate.
down_revision = "anchors_and_captures"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "is_admin",
            sa.Boolean(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "is_admin")
