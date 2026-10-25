"""Recovery tables coexist with the SQLite compatibility test schema.

PostgreSQL identity constraints stay in the real migrations and PostgreSQL DDL;
SQLite cannot parse UUID casts or PostgreSQL regular-expression operators.
"""

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateTable

from app.models.models import DnplAuthority, DnplNamespaceRetirement


@pytest.mark.parametrize("model", [DnplAuthority, DnplNamespaceRetirement])
def test_control_model_creates_on_sqlite_and_preserves_postgres_identity(model):
    engine = create_engine("sqlite://")
    try:
        model.__table__.create(engine)
        with engine.begin() as connection:
            # The portable singleton constraint remains enforced. This is not
            # a SQLite substitute for the real PG identity-constraint controls.
            with pytest.raises(IntegrityError):
                connection.execute(text(
                    f"INSERT INTO {model.__tablename__} "
                    "(id,protocol,incarnation,namespace,operation_id,state,"
                    "redis_run_id,redis_master_replid,policy_fingerprint) "
                    "VALUES (2,3,1,'a','b','ready','c','d','e')"
                ))
        ddl = str(CreateTable(model.__table__).compile(dialect=postgresql.dialect()))
        assert "CONSTRAINT dnpl_authority_identity CHECK" in ddl
        assert "redis_run_id ~ '^[0-9a-f]{40}$'" in ddl
        assert "::uuid" in ddl
    finally:
        engine.dispose()
