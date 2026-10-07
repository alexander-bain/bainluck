"""#10664 test adapters: decode price binds; isolate real PostgreSQL rigs."""

import os
import uuid

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import make_url
from sqlalchemy.sql.dml import Update

_ENGINES = []


def statement_params(stmt, params=None):
    """#10689: a statement's own bound values plus those supplied at execute.

    The Kalshi price write reuses one prepared template and passes its row's
    values to `session.execute` beside it, so a fake that reads only the
    compiled statement sees every price bind as None.
    """
    merged = dict(stmt.compile(dialect=postgresql.dialect()).params)
    merged.update(params or {})
    return merged


def price_writes(stmt, params=None):
    """Return supplied price pairs only; other statements return no pairs.

    Recording fakes deliberately return no database rows. Transaction and
    publication coverage belongs to the separate real PostgreSQL rigs.
    """
    if not isinstance(stmt, Update) or stmt.table.name != "futures_outcomes":
        return []
    params = statement_params(stmt, params)
    if "kalshi_outcome_id" in params:  # #10689 typed Kalshi template
        return [(params["kalshi_outcome_id"], params["kalshi_stored_probability"])]
    if "chunk_ids" in params:
        ids, prices = params["chunk_ids"], params["chunk_prices"]
        assert len(ids) == len(prices)
        return list(zip(ids, prices))
    if "current_probability" in params:
        return [(params["id_1"], params["current_probability"])]
    return []


def pg_engine():
    """A per-test schema, visible to every independent connection in the rig."""
    url = os.environ.get("SEARCH_TEST_DATABASE_URL")
    if not url:
        pytest.skip("#10664 real transaction rig needs SEARCH_TEST_DATABASE_URL")
    url = make_url(url).set(drivername="postgresql+psycopg2")
    admin = create_engine(url)
    schema = "pm10664_" + uuid.uuid4().hex
    with admin.begin() as conn:
        conn.execute(text(f"CREATE SCHEMA {schema}"))
    engine = create_engine(url)

    @event.listens_for(engine, "connect")
    def search_path(dbapi, _record):
        old = dbapi.autocommit
        dbapi.autocommit = True
        with dbapi.cursor() as cur:
            cur.execute(f"SET search_path TO {schema}")
        dbapi.autocommit = old

    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE teams (id INTEGER PRIMARY KEY)"))
    _ENGINES.append((engine, admin, schema))
    return engine


@pytest.fixture(autouse=True)
def cleanup_pg_engines():
    start = len(_ENGINES)
    yield
    for engine, admin, schema in _ENGINES[start:]:
        engine.dispose()
        try:
            with admin.begin() as conn:
                conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        finally:
            admin.dispose()
    del _ENGINES[start:]


def fail_price_trigger(conn, name, outcome_id, message):
    """Abort a real PostgreSQL statement on the deliberate failing leg."""
    assert name.isidentifier()
    assert message in {"boom", "second leg"}
    conn.execute(text(f"""CREATE FUNCTION {name}_fail() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
        IF NEW.id = {int(outcome_id)} THEN RAISE EXCEPTION '{message}'; END IF;
        RETURN NEW; END $$"""))
    conn.execute(
        text(
            f"CREATE TRIGGER {name} BEFORE UPDATE ON futures_outcomes "
            f"FOR EACH ROW EXECUTE FUNCTION {name}_fail()"
        )
    )
