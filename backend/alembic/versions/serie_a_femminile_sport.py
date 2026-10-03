"""Seed only the evidenced Serie A Femminile Sport identity (#10319).

No existing events, teams or markets are changed. Downgrade retains the seed
if it has acquired a reference (including a cascading foreign key).
"""

from alembic import op
import sqlalchemy as sa

revision = "serie_a_femminile_sport"
down_revision = "score_observation_stamp"
branch_labels = None
depends_on = None

SPORT_KEY = "soccer_italy_serie_a_women"
SPORT_NAME = "Serie A Femminile - Italy (Women)"
SPORT_GROUP = "Soccer"


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            'INSERT INTO sports (key, name, "group", active) '
            "VALUES (:key, :name, :group, TRUE) ON CONFLICT (key) DO NOTHING"
        ),
        {"key": SPORT_KEY, "name": SPORT_NAME, "group": SPORT_GROUP},
    )
    row = bind.execute(
        sa.text('SELECT name, "group", active FROM sports WHERE key = :key FOR UPDATE'),
        {"key": SPORT_KEY},
    ).one()
    if tuple(row) != (SPORT_NAME, SPORT_GROUP, True):
        raise RuntimeError(
            "#10319: existing Serie A Femminile Sport conflicts; refusing to rename it"
        )


def downgrade() -> None:
    bind = op.get_bind()
    # Lock the parent before checking children: a concurrent FK insertion must
    # wait rather than enter a cascading delete after the reference check.
    row = (
        bind.execute(
            sa.text(
                'SELECT id, key, name, "group", active FROM sports WHERE key = :key FOR UPDATE'
            ),
            {"key": SPORT_KEY},
        )
        .mappings()
        .one_or_none()
    )
    if row is None or (row["name"], row["group"], row["active"]) != (
        SPORT_NAME,
        SPORT_GROUP,
        True,
    ):
        return

    # Read actual constraints, not a table list that can miss a later consumer.
    # Composite references are checked together; both id and key FKs are safe.
    references = bind.execute(sa.text("""
        SELECT c.oid, n.nspname AS child_schema, t.relname AS child_table,
               a.attname AS child_column, p.attname AS parent_column
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        CROSS JOIN LATERAL generate_subscripts(c.conkey, 1) s(i)
        JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[s.i]
        JOIN pg_attribute p ON p.attrelid = c.confrelid AND p.attnum = c.confkey[s.i]
        WHERE c.contype = 'f' AND c.confrelid = 'sports'::regclass
        ORDER BY c.oid, s.i
    """)).mappings().all()
    constraints = {}
    for reference in references:
        constraints.setdefault(reference["oid"], []).append(reference)
    quote = bind.dialect.identifier_preparer.quote
    for columns in constraints.values():
        first = columns[0]
        table = f'{quote(first["child_schema"])}.{quote(first["child_table"])}'
        predicates, values = [], {}
        for index, column in enumerate(columns):
            parameter = f"parent_{index}"
            predicates.append(f'{quote(column["child_column"])} = :{parameter}')
            values[parameter] = row[column["parent_column"]]
        if (
            bind.execute(
                sa.text(
                    f'SELECT 1 FROM {table} WHERE {" AND ".join(predicates)} LIMIT 1'
                ),
                values,
            ).first()
            is not None
        ):
            return
    bind.execute(sa.text("DELETE FROM sports WHERE id = :id"), {"id": row["id"]})
