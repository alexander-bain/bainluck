"""Exercise only the #10319 seed/undo in an isolated real-Postgres schema."""

import importlib.util
import os
from pathlib import Path
import uuid

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
import sqlalchemy as sa

RAW_URL = os.getenv("MIGRATION_TEST_DATABASE_URL") or os.getenv(
    "SEARCH_TEST_DATABASE_URL"
)
pytestmark = pytest.mark.skipif(
    not RAW_URL, reason="requires explicit local/CI PostgreSQL test URL"
)
REFERENCING_TABLES = (
    "teams",
    "events",
    "tournaments",
    "futures_markets",
    "entities",
    "containers",
)


@pytest.fixture
def seed_db(monkeypatch):
    url = sa.engine.make_url(RAW_URL).set(drivername="postgresql+psycopg2")
    engine = sa.create_engine(url)
    schema = "serie_a_seed_" + uuid.uuid4().hex[:12]
    connection = engine.connect()
    connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
    connection.execute(sa.text(f'SET search_path TO "{schema}"'))
    connection.execute(sa.text("""
        CREATE TABLE sports (
            id SERIAL PRIMARY KEY, key VARCHAR(50) UNIQUE NOT NULL,
            name VARCHAR(100) NOT NULL, "group" VARCHAR(50), active BOOLEAN
        )
    """))
    for table in REFERENCING_TABLES:
        connection.execute(sa.text(f"""
            CREATE TABLE {table} (
                id SERIAL PRIMARY KEY,
                sport_id INTEGER REFERENCES sports(id) ON DELETE CASCADE
            )
        """))
    connection.execute(sa.text("""
        CREATE TABLE key_reference (
            sport_key VARCHAR(50) REFERENCES sports(key) ON DELETE CASCADE
        )
    """))
    connection.execute(sa.text("""
        INSERT INTO sports (key, name, "group", active)
        VALUES ('soccer_italy_serie_a', 'Serie A - Italy', 'Soccer', TRUE)
    """))
    connection.commit()
    migration = (
        Path(__file__).resolve().parents[2]
        / "alembic/versions/serie_a_femminile_sport.py"
    )
    spec = importlib.util.spec_from_file_location(
        "serie_a_femminile_seed_10319", migration
    )
    seed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed)
    monkeypatch.setattr(seed, "op", Operations(MigrationContext.configure(connection)))
    try:
        yield connection, seed
    finally:
        connection.rollback()
        connection.close()
        with engine.begin() as cleanup:
            cleanup.execute(sa.text(f'DROP SCHEMA "{schema}" CASCADE'))
        engine.dispose()


def _rows(connection):
    return connection.execute(
        sa.text('SELECT id, key, name, "group", active FROM sports ORDER BY id')
    ).all()


def test_seed_is_exact_and_idempotent_without_touching_mens_sport(seed_db):
    connection, seed = seed_db
    before = _rows(connection)
    seed.upgrade()
    seeded = _rows(connection)
    seed.upgrade()
    assert _rows(connection) == seeded
    assert seeded[:-1] == before
    assert tuple(seeded[-1][1:]) == (
        "soccer_italy_serie_a_women",
        "Serie A Femminile - Italy (Women)",
        "Soccer",
        True,
    )
    assert len(seed.revision) <= 32
    assert seed.down_revision == "score_observation_stamp"


@pytest.mark.parametrize(
    "name,group,active",
    [
        ("Serie A - Italy", "Soccer", True),
        ("Serie A Femminile - Italy (Women)", "Basketball", True),
        ("Serie A Femminile - Italy (Women)", "Soccer", False),
    ],
)
def test_conflicting_existing_key_refuses_without_renaming(
    seed_db, name, group, active
):
    connection, seed = seed_db
    connection.execute(
        sa.text(
            'INSERT INTO sports (key, name, "group", active) VALUES (:key, :name, :group, :active)'
        ),
        {"key": seed.SPORT_KEY, "name": name, "group": group, "active": active},
    )
    before = _rows(connection)
    with pytest.raises(RuntimeError, match="conflicts"):
        seed.upgrade()
    assert _rows(connection) == before


def test_unreferenced_downgrade_restores_prior_sports(seed_db):
    connection, seed = seed_db
    before = _rows(connection)
    seed.upgrade()
    seed.downgrade()
    assert _rows(connection) == before
    seed.downgrade()  # Absent is a no-op.
    assert _rows(connection) == before


@pytest.mark.parametrize("table", REFERENCING_TABLES)
def test_downgrade_preserves_seed_and_referenced_row_even_with_cascade(seed_db, table):
    connection, seed = seed_db
    seed.upgrade()
    sid = connection.execute(
        sa.text("SELECT id FROM sports WHERE key = :key"), {"key": seed.SPORT_KEY}
    ).scalar_one()
    # These deliberately minimal FK children are not the full ORM tables.
    # Reflect their actual test schema so their columns remain SQL-checked.
    child = sa.Table(table, sa.MetaData(), autoload_with=connection)
    connection.execute(child.insert().values(sport_id=sid))
    before = _rows(connection)
    seed.downgrade()
    assert _rows(connection) == before
    assert (
        connection.execute(sa.text(f"SELECT sport_id FROM {table}")).scalar_one() == sid
    )


def test_downgrade_also_preserves_a_key_foreign_reference(seed_db):
    connection, seed = seed_db
    seed.upgrade()
    child = sa.Table("key_reference", sa.MetaData(), autoload_with=connection)
    connection.execute(child.insert().values(sport_key=seed.SPORT_KEY))
    before = _rows(connection)
    seed.downgrade()
    assert _rows(connection) == before
    assert (
        connection.execute(sa.text("SELECT sport_key FROM key_reference")).scalar_one()
        == seed.SPORT_KEY
    )


def test_downgrade_does_not_delete_an_identity_changed_after_seed(seed_db):
    connection, seed = seed_db
    seed.upgrade()
    connection.execute(
        sa.text("UPDATE sports SET name = 'Owner corrected label' WHERE key = :key"),
        {"key": seed.SPORT_KEY},
    )
    before = _rows(connection)
    seed.downgrade()
    assert _rows(connection) == before
