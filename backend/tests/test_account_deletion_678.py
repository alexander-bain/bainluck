"""#678 — "delete my account" has to delete the account, and all of it.

## What was wrong

App Review rejected version 1.0(7) on 2026-05-25 (Guideline 5.1.1(v)) because
no option to initiate account deletion could be found. The iOS half of that is
fixed in `MyStuffView`. This file gates the server half, which was worse than
undiscoverable — it did not work.

`DELETE /api/auth/me` was one line, ``await db.delete(user)``. Measured on real
PostgreSQL (`tests/integration/test_account_deletion_678_pg.py` runs it):

    user with preferences   -> NotNullViolationError   (500)
    user with a pin         -> NotNullViolationError   (500)
    user with a device token-> ForeignKeyViolationError(500)
    user with predictions   -> deleted, predictions left behind
    user with nothing       -> deleted

Two independent causes. ``User.favorites`` / ``.preferences`` / ``.pins``
declare no delete cascade, so the ORM's delete cascade NULLs a NOT NULL
``user_id``; and ``device_tokens`` / ``oscars_pool_members`` /
``prediction_challenges`` hold a NO ACTION foreign key the ORM never sees, so
PostgreSQL refuses the DELETE outright. Every signed-in iOS account has
preferences (onboarding writes them) and a device token, so in practice the
endpoint 500'd for every real account — and the app swallowed the error.

## What this file gates

The COVERAGE question, which is the one that rots: every column in the schema
that points at a user must be accounted for by the endpoint. A table added six
months from now either blocks account deletion with a foreign key or quietly
keeps a deleted person's rows, and both failures are silent — the endpoint
still returns ``{"status": "deleted"}``.

So this test derives the population from the model metadata rather than from a
list a human keeps up to date, and fails if anything in it is unclassified.
The behaviour (rows actually gone, rows actually de-identified, other accounts
untouched) is gated on real PostgreSQL in the integration test; a mock session
returns whatever it was handed and cannot see a constraint.
"""

import pytest
from sqlalchemy import inspect

from app.models.models import Base, User
from app.routes.auth import _ACCOUNT_DEIDENTIFIED_ROWS, _ACCOUNT_OWNED_ROWS

# Columns that name a user but are NOT a link to `users.id`: free-text session
# identifiers, and the friend side of a challenge, which belongs to whoever
# holds the link and is not this user's row.
_NOT_A_USER_LINK = {
    ("prediction_challenges", "creator_session_id"),
    ("prediction_challenges", "friend_session_id"),
}


def _user_linked_columns():
    """Every column in the schema that identifies a user.

    Two ways a column can qualify, because the schema uses both and only one
    of them is enforced by the database:

    * a real foreign key to ``users.id`` (user_favorites, device_tokens, ...);
    * a bare integer named ``user_id`` with no constraint at all
      (user_predictions, user_seen_markets, discover_interactions,
      search_query_logs, bug_reports) — invisible to the database, and so
      invisible to anyone reasoning about deletion from constraints alone.
      These are exactly the rows that survived deletion.
    """
    found = set()
    for table in Base.metadata.tables.values():
        if table.name == "users":
            continue
        for column in table.columns:
            if (table.name, column.name) in _NOT_A_USER_LINK:
                continue
            points_at_users = any(
                fk.column.table.name == "users" for fk in column.foreign_keys
            )
            named_for_a_user = column.name in {
                "user_id",
                "creator_user_id",
                "owner_user_id",
                "created_by_user_id",
            }
            if points_at_users or named_for_a_user:
                found.add((table.name, column.name))
    return found


def _handled_columns():
    handled = set()
    for model, column in _ACCOUNT_OWNED_ROWS:
        handled.add((inspect(model).local_table.name, column.key))
    for model, column, _blanked in _ACCOUNT_DEIDENTIFIED_ROWS:
        handled.add((inspect(model).local_table.name, column.key))
    return handled


def test_every_user_linked_column_is_classified():
    """The guard. A new user-linked table must be deleted or de-identified.

    If this fails, add the table to ``_ACCOUNT_OWNED_ROWS`` (it is the user's
    own data) or ``_ACCOUNT_DEIDENTIFIED_ROWS`` (it is a shared or operational
    record that outlives the account). Do not delete the assertion — an
    unclassified table is either a 500 on deletion or personal data kept after
    a person asked for it to go.
    """
    missing = _user_linked_columns() - _handled_columns()
    assert not missing, (
        "these columns point at a user and account deletion ignores them: "
        f"{sorted(missing)}"
    )


def test_no_handled_column_is_stale():
    """The other direction: the lists may not name a column the schema lost.

    A stale entry issues a DELETE against a column that no longer exists, so
    account deletion starts failing at runtime while every unit test that
    mocks the session stays green.
    """
    stale = _handled_columns() - _user_linked_columns()
    assert not stale, f"these are handled but no longer exist in the schema: {sorted(stale)}"


def test_the_two_lists_do_not_overlap():
    """A table is the user's own data or it is not. It cannot be both — a row
    that is deleted and then updated is a silent no-op that reads as coverage.
    """
    owned = {inspect(m).local_table.name for m, _ in _ACCOUNT_OWNED_ROWS}
    deidentified = {
        inspect(m).local_table.name for m, _, _ in _ACCOUNT_DEIDENTIFIED_ROWS
    }
    assert not (owned & deidentified), f"classified twice: {sorted(owned & deidentified)}"


def test_owned_rows_are_ordered_children_first():
    """Foreign keys without ON DELETE CASCADE must be gone before the user row.

    ``user_favorites``, ``device_tokens``, ``oscars_pool_members`` and
    ``prediction_challenges`` are NO ACTION in production (read from
    `pg_constraint` 2026-09-14), so PostgreSQL rejects the DELETE if any of
    their rows still point at the user. The endpoint deletes every owned table
    before it touches ``users``; this asserts the lists it iterates actually
    contain those tables rather than relying on a cascade that is not there.
    """
    owned = {inspect(m).local_table.name for m, _ in _ACCOUNT_OWNED_ROWS}
    deidentified = {
        inspect(m).local_table.name for m, _, _ in _ACCOUNT_DEIDENTIFIED_ROWS
    }
    for blocking in [
        "user_favorites",
        "device_tokens",
        "oscars_pool_members",
        "prediction_challenges",
    ]:
        assert blocking in owned | deidentified, (
            f"{blocking} holds a NO ACTION foreign key to users.id — if account "
            "deletion does not clear it first, the DELETE is refused by PostgreSQL"
        )


def test_deidentification_blanks_every_identifying_field_not_just_the_link():
    """A de-identified row must keep nothing that names the person.

    ``bug_reports`` copies the profile email into ``user_email`` at submission
    time, so nulling ``user_id`` alone would leave the address behind on a row
    belonging to an account that no longer exists.
    """
    by_table = {
        inspect(model).local_table.name: (column, blanked)
        for model, column, blanked in _ACCOUNT_DEIDENTIFIED_ROWS
    }

    assert "bug_reports" in by_table
    _column, blanked = by_table["bug_reports"]
    assert blanked.get("user_email", "sentinel") is None, (
        "bug_reports.user_email is a direct identifier copied from the profile "
        "and must be blanked alongside user_id"
    )

    for table, (_column, blanked) in by_table.items():
        assert blanked, f"{table} is listed as de-identified but blanks nothing"
        for field, value in blanked.items():
            assert value is None, (
                f"{table}.{field} is set to {value!r}; de-identification blanks "
                "fields, it does not write a placeholder that still groups rows "
                "by former account"
            )


def test_the_user_row_itself_is_not_in_either_list():
    """``users`` is deleted last by the endpoint directly. Listing it as an
    'owned row' would delete it before its children and reintroduce exactly
    the foreign key failure this ship fixes.
    """
    listed = {inspect(m).local_table.name for m, _ in _ACCOUNT_OWNED_ROWS} | {
        inspect(m).local_table.name for m, _, _ in _ACCOUNT_DEIDENTIFIED_ROWS
    }
    assert inspect(User).local_table.name not in listed


@pytest.mark.parametrize(
    "table",
    [
        "user_preferences",
        "user_pins",
        "user_favorites",
        "device_tokens",
        "user_predictions",
        "user_seen_markets",
        "discover_interactions",
        "oscars_pool_members",
    ],
)
def test_personal_tables_are_deleted_not_merely_unlinked(table):
    """Named one by one so a future edit cannot quietly move a table carrying
    a person's own activity into the de-identified list, where the rows would
    survive the deletion request.
    """
    owned = {inspect(m).local_table.name for m, _ in _ACCOUNT_OWNED_ROWS}
    assert table in owned, f"{table} is the user's own data and must be deleted outright"
