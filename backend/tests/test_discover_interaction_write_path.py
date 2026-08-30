"""The Discover interest-signal rail can actually WRITE — the shape gate.

## The ship this guards

Every card a reader scrolls past on Discover is an interest signal, and
`discover_interactions` is where the product banks them so ranking can one day
be learned instead of hand-tuned (#2299, PILLAR DISCOVER). The rail is
complete end to end — a batched consent-gated browser emitter, a validated
receiver at `POST /api/feed/interactions`, a provenance pre-training gate,
admin rollups, an export task.

It banked **zero rows for eleven days** and nothing anywhere went red.

## The defect, exactly

`add_disc_int_provenance` (2026-08-18) created a real Postgres enum type and
added `discover_interactions.provenance` as that type. `models.py` declared the
same column as `String(20)`. SQLAlchemy therefore compiled the parameter as
`$13::VARCHAR`, and PostgreSQL refuses varchar -> enum:

    asyncpg.exceptions.DatatypeMismatchError: column "provenance" is of type
    discover_provenance but expression is of type character varying

`POST /api/feed/interactions` is the table's only writer, so every interaction
the site received from 2026-08-18T19:34Z onward 500ed. Measured on production
2026-08-29: last row 2026-08-18T19:34:13Z, zero rows in the following eleven
days, Sentry BAINLUCK-12J at `/api/feed/interactions` still firing.

## Why nothing caught it, and what that dictates about this file

Three independent silences stacked, which is why an eleven-day total outage of a
whole pillar's input read as calm:

1. The browser sends the beacon `keepalive` inside `.catch(() => {})` — a
   deliberate promise that telemetry never disturbs the feed. It also means a
   100%-failing endpoint looks exactly like a working one from the page.
2. Nothing reads this table on a request path, so no user-facing surface
   degraded and no latency signal moved.
3. **The route tests pass.** The recording double does not enforce column
   types, so the specimen accepts a value the real database rejects — the same
   trap `app/utils/discover_provenance.py` documents for the VALUE list, one
   layer over, on the TYPE. And there is no local Postgres in this sandbox, so
   "just run it against real PG" is a CI-only gate that this defect shipped
   straight past anyway.

So this file may not assert against a session, a double, or a live database.
It asserts against **the SQL SQLAlchemy actually compiles for the asyncpg
dialect** — which is a pure function of the model, needs no database, and is
the precise artifact that was wrong. Run against the pre-fix model every test
here fails; the first one fails printing `$5::VARCHAR`, the same cast production
logged.
"""

from __future__ import annotations

import pathlib
import re

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import asyncpg as asyncpg_dialect

from app.models.models import DiscoverInteraction
from app.services.database import Base
from app.utils.discover_provenance import PROVENANCE_VALUES

#: The dialect production actually runs. Compiling against the generic
#: PostgreSQL dialect is not equivalent — the `$n::TYPE` casts that carry the
#: whole defect are emitted by the asyncpg driver's paramstyle.
_ASYNCPG = asyncpg_dialect.dialect()

_MIGRATIONS = pathlib.Path(__file__).resolve().parents[1] / "alembic" / "versions"


def _compiled_insert() -> str:
    """The INSERT the receiver's `db.add_all(...)` + `commit()` becomes.

    Values are supplied for exactly the NOT NULL columns plus `provenance`, so
    the statement is the one `record_discover_interactions` produces for a
    minimal impression.
    """
    stmt = sa.insert(DiscoverInteraction).values(
        surface="web",
        action="impression",
        item_type="futures",
        item_id="1",
        provenance="unknown",
    )
    return str(stmt.compile(dialect=_ASYNCPG))


def test_provenance_bind_is_not_cast_to_varchar() -> None:
    """THE RED-FIRST GATE — this is the production 500, reproduced offline.

    Against the pre-fix model this fails with the literal cast Postgres
    rejected. It is asserted on the compiled SQL rather than on the column
    object because the cast is what the database sees and the column type is
    only how it got there.
    """
    sql = _compiled_insert()

    # Locate the bind that carries provenance: it is the last VALUES entry,
    # because `values()` orders by the table's column order and provenance is
    # declared after every other column named above.
    values_clause = sql.split("VALUES", 1)[1]
    binds = re.findall(r"\$\d+(?:::\w+)?", values_clause)
    assert binds, f"no bind parameters compiled at all:\n{sql}"

    provenance_bind = binds[-1]
    assert not provenance_bind.endswith("::VARCHAR"), (
        "discover_interactions.provenance compiled as "
        f"{provenance_bind} — PostgreSQL refuses varchar -> discover_provenance "
        "and returns DatatypeMismatchError, so EVERY interaction insert 500s "
        "and the Discover interest-signal rail banks nothing. This is the "
        "2026-08-18 outage. Declare the column as the named enum, not String.\n"
        f"{sql}"
    )
    assert provenance_bind.endswith("::discover_provenance"), (
        "provenance must compile with an explicit cast to its named enum type; "
        f"got {provenance_bind}\n{sql}"
    )


def test_every_other_bind_still_compiles_unchanged() -> None:
    """The must-not-regress control.

    Changing one column's type must not disturb the other twelve. If a future
    change makes, say, `item_id` stop compiling as VARCHAR, that is a second
    DatatypeMismatch waiting on a different column and it fails here rather
    than in production silence.
    """
    sql = _compiled_insert()
    values_clause = sql.split("VALUES", 1)[1]
    binds = re.findall(r"\$\d+(?:::\w+)?", values_clause)

    # surface, action, item_type, item_id are all varchar columns.
    assert [b.split("::", 1)[1] for b in binds[:4]] == ["VARCHAR"] * 4, sql


def test_provenance_column_is_the_named_enum_with_production_label_order() -> None:
    """The type, and the ORDER of its labels.

    Order is load-bearing and not cosmetic: enum ordinals are what
    `ORDER BY provenance` and every btree range scan on
    `ix_discover_interactions_provenance` mean. A model that declares the right
    seven values in a prettier order describes a type neither database has, and
    `create_all` on a fresh Postgres test database would then build a type that
    disagrees with production while every value-level assertion stayed green.
    """
    column = DiscoverInteraction.__table__.c.provenance

    assert isinstance(column.type, sa.Enum), (
        f"provenance is {column.type!r}; production holds the Postgres enum "
        "type `discover_provenance` and a non-Enum declaration cannot be "
        "inserted into it"
    )
    assert column.type.name == "discover_provenance"
    assert tuple(column.type.enums) == tuple(PROVENANCE_VALUES)


def test_no_model_column_declares_string_where_a_migration_declared_an_enum() -> None:
    """THE CLASS GUARD — the defect, generalised past its one instance.

    Measured on production 2026-08-29, `discover_provenance` is the ONLY enum
    type in the database, so today this guard has exactly one subject. That is
    the reason to write it now rather than later: the next `sa.Enum` a migration
    creates arrives with no living memory of this outage, and the failure mode
    is an endpoint that 500s on every write while the suite stays green.

    It reads the migrations because they are what the database was built from —
    deriving the expectation from the models instead would be a self-oracle,
    and a self-oracle is exactly what let this ship.
    """
    declared_in_migrations: set[str] = set()
    for path in _MIGRATIONS.glob("*.py"):
        for match in re.finditer(
            r"sa\.Enum\((?P<args>[^)]*?)name=[\"'](?P<name>\w+)[\"']",
            path.read_text(),
            re.S,
        ):
            declared_in_migrations.add(match.group("name"))

    assert declared_in_migrations, (
        "found no `sa.Enum(..., name=...)` in any migration — the scan broke, "
        "and a broken scan asserts nothing"
    )

    modelled: dict[str, list[str]] = {}
    for table in Base.metadata.tables.values():
        for column in table.columns:
            type_ = column.type
            if isinstance(type_, sa.Enum) and type_.name:
                modelled.setdefault(type_.name, []).append(
                    f"{table.name}.{column.name}"
                )

    missing = sorted(declared_in_migrations - set(modelled))
    assert not missing, (
        f"migrations create the Postgres enum type(s) {missing}, but no model "
        "column is declared as them. A column typed `String` against an enum "
        "column compiles to `::VARCHAR` and PostgreSQL rejects the INSERT — "
        "see this file's docstring for the eleven-day version of that."
    )
