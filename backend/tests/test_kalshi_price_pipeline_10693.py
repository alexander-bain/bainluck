"""#10693 routing/compatibility guards; database semantics have a separate rail."""

import asyncio
from contextlib import aclosing
from importlib.metadata import PackageNotFoundError
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest
from sqlalchemy import event
from sqlalchemy.exc import CompileError, DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

from app.utils import kalshi_price_pipeline as m
from app.utils.kalshi_price_statement import (
    KALSHI_PRICE_STATEMENTS,
    kalshi_price_parameters,
)
from tests.kalshi_price_statement_support import compiled_signature


@pytest.fixture(autouse=True)
def modeled_supported_versions(monkeypatch):
    # Structural unit checks model the accepted envelope. The dedicated PG CI
    # environment verifies actual installed versions and real private behavior.
    monkeypatch.setattr(
        m.importlib.metadata,
        "version",
        lambda name: dict(sqlalchemy="2.0.50", asyncpg="0.31.0")[name],
    )


@pytest.fixture
def owner():
    engine = create_async_engine("postgresql+asyncpg://localhost/private_unused")
    pipeline = m.install_kalshi_price_pipeline(engine)
    yield pipeline
    pipeline.close()


class Session:
    def __init__(self, owner, connection=None):
        self.bind = owner.engine
        self.connection_value = connection
        self.calls = []

    async def execute(self, statement, parameters):
        self.calls.append((statement, parameters))
        return SimpleNamespace(all=lambda: [parameters["kalshi_outcome_id"]])

    async def connection(self):
        if isinstance(self.connection_value, BaseException):
            raise self.connection_value
        if self.connection_value is None:
            raise AssertionError("cheap ordinary route must not checkout for preflight")
        return self.connection_value


async def collected(owner, session, phase):
    return [result async for result in owner.iter_phase(session, phase)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "phase",
    [
        {},
        {1: (0.3, 0.2, 0.4)},
        {1: (0.3, 0.2, 0.4), 2: (0.3, None, 0.9), 3: (0.3, 0.2, 0.4)},
    ],
)
async def test_singleton_only_route_has_no_compatibility_template_or_checkout(
    owner, monkeypatch, phase
):
    def forbidden():
        raise AssertionError("singleton-only compatibility work")

    monkeypatch.setattr(m, "_load_compatibility", forbidden)
    session = Session(owner)
    results = await collected(owner, session, phase)
    assert [r.attempted for r in results] == [1] * len(phase)
    assert [p["kalshi_outcome_id"] for _, p in session.calls] == list(phase)
    assert not owner._compatibility_checked


@pytest.mark.parametrize(
    "failure", ["version", "missing-package", "private-import", "private-attribute"]
)
def test_lazy_compatibility_refusal(failure, monkeypatch):
    original = m.importlib.import_module

    def version(name):
        if failure == "missing-package":
            raise PackageNotFoundError(name)
        return (
            "unknown"
            if failure == "version"
            else dict(sqlalchemy="2.0.50", asyncpg="0.31.0")[name]
        )

    def load(name):
        if failure == "private-import":
            raise ImportError("unsupported private adapter")
        if failure == "private-attribute":
            return SimpleNamespace()
        return original(name)

    monkeypatch.setattr(m.importlib.metadata, "version", version)
    monkeypatch.setattr(m.importlib, "import_module", load)
    assert m._load_compatibility() is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "refusal", ["versions", "template", "cursor-factory", "cursor"]
)
async def test_entire_phase_refuses_before_leading_singleton_price(
    owner, monkeypatch, refusal
):
    log = []
    original = m._load_compatibility

    def load():
        log.append("compatibility")
        return None if refusal == "versions" else original()

    monkeypatch.setattr(m, "_load_compatibility", load)
    if refusal == "template":
        monkeypatch.setattr(m, "_templates", lambda _: None)
    raw = SimpleNamespace(dbapi_connection=SimpleNamespace())
    if refusal == "cursor":
        raw.dbapi_connection.cursor = lambda: SimpleNamespace(
            close=lambda: log.append("cursor-close")
        )

    class Connection:
        async def get_raw_connection(self):
            log.append("cursor-preflight")
            return raw

    session = Session(owner, Connection())
    original_execute = session.execute

    async def execute(*args):
        assert log[0] == "compatibility"
        log.append("price")
        return await original_execute(*args)

    session.execute = execute
    phase = {1: (0.3, None, None), 2: (0.3, 0.2, 0.4), 3: (0.3, 0.2, 0.4)}
    results = await collected(owner, session, phase)
    assert [r.attempted for r in results] == [1, 1, 1]
    assert [p["kalshi_outcome_id"] for _, p in session.calls] == [1, 2, 3]
    assert log.index("compatibility") < log.index("price")
    if refusal.startswith("cursor"):
        assert log.index("cursor-preflight") < log.index("price")


@pytest.mark.parametrize(
    "error", [AttributeError("shape"), TypeError("shape"), CompileError("shape")]
)
def test_template_acquisition_refuses_declared_shape_failures(monkeypatch, error):
    class Statement:
        def compile(self, **_kw):
            raise error

    monkeypatch.setattr(m, "KALSHI_PRICE_STATEMENTS", {True: Statement()})
    assert m._templates(lambda: None) is None


@pytest.mark.parametrize(
    "values",
    [
        (0.3, 0.2, 0.4),
        (0.3, 0.3, 0.3),
        (0.0512345678, 0.123456, 0.123457),
        (0.0, 0.0, 0.0),
        (1.0, 1.0, 1.0),
        (0.3, None, 0.9),
        (0.3, 0.8, None),
        (0.3, None, None),
    ],
)
def test_expanded_factory_sql_positions_and_processed_arguments(values):
    compatibility = m._load_compatibility()
    templates = m._templates(compatibility[3])
    book = values[1] is not None and values[2] is not None
    expected_sql, _types, expected_values = compiled_signature(
        KALSHI_PRICE_STATEMENTS[book], kalshi_price_parameters(2147483647, *values)
    )
    assert templates[book].sql == expected_sql
    assert templates[book].args(2147483647, values) == tuple(expected_values)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error", [RuntimeError("checkout failed"), asyncio.CancelledError()]
)
async def test_checkout_and_cancellation_are_not_compatibility_fallback(owner, error):
    session = Session(owner, error)
    with pytest.raises(type(error)):
        await collected(
            owner,
            session,
            {1: (0.3, None, None), 2: (0.3, 0.2, 0.4), 3: (0.3, 0.2, 0.4)},
        )
    assert not session.calls and owner._active == 0


@pytest.mark.asyncio
async def test_submitted_fault_never_replays_even_after_leading_scalar(
    owner, monkeypatch
):
    owner._templates = m._templates(m._load_compatibility()[3])
    sent = []
    fault = DBAPIError("price", [], RuntimeError("sent query failed"))

    class Connection:
        async def exec_driver_sql(self, sql, parameters, **_kw):
            sent.append((sql, parameters))
            raise fault

    async def preflight(_session, _runs):
        return Connection()

    monkeypatch.setattr(owner, "_preflight", preflight)
    session = Session(owner)
    with pytest.raises(DBAPIError) as failed:
        await collected(
            owner,
            session,
            {
                1: (0.3, None, None),
                2: (0.3, 0.2, 0.4),
                3: (0.3, 0.2, 0.4),
                4: (0.3, None, None),
            },
        )
    assert failed.value is fault and len(sent) == 1
    assert [p["kalshi_outcome_id"] for _, p in session.calls] == [1]
    assert owner._active == 0


def test_owned_install_once_untagged_and_cleanup(owner):
    assert m.install_kalshi_price_pipeline(owner.engine) is owner
    assert event.contains(owner.engine.sync_engine, "do_executemany", owner._listener)
    assert (
        owner._listener(
            object(), "other SQL", [], SimpleNamespace(execution_options={})
        )
        is None
    )
    owner.close()
    assert not event.contains(
        owner.engine.sync_engine, "do_executemany", owner._listener
    )
    owner.close()
    replacement = m.install_kalshi_price_pipeline(owner.engine)
    assert replacement is not owner
    replacement.close()


@pytest.mark.asyncio
async def test_cleanup_cannot_remove_listener_during_a_live_phase(owner):
    iterator = owner.iter_phase(Session(owner), {1: (0.3, 0.2, 0.4)})
    await anext(iterator)
    with pytest.raises(RuntimeError, match="finish or cancel"):
        owner.close()
    await iterator.aclose()
    owner.close()
    with pytest.raises(RuntimeError, match="closed"):
        await collected(owner, Session(owner), {})


def test_unexpected_private_tag_sql_and_cursor_stay_refused_under_optimization():
    code = """
from types import SimpleNamespace
from sqlalchemy.ext.asyncio import create_async_engine
from app.utils import kalshi_price_pipeline as m
owner = m.install_kalshi_price_pipeline(create_async_engine("postgresql+asyncpg://localhost/private_unused"))
m.importlib.metadata.version = lambda name: dict(sqlalchemy="2.0.50", asyncpg="0.31.0")[name]
owner._compatibility = m._load_compatibility()
owner._templates = m._templates(owner._compatibility[3])
refused = 0
for token, sql in ((object(), "other SQL"), (owner._token, "other SQL"), (owner._token, owner._templates[True].sql)):
    try:
        owner._listener(object(), sql, [(1,), (2,)], SimpleNamespace(execution_options={m._TAG: token}))
    except RuntimeError:
        refused += 1
    else:
        raise RuntimeError("optimized runtime guard vanished")
if refused != 3:
    raise RuntimeError("missing refusal")
owner.close()
print("three optimized refusals")
"""
    result = subprocess.run(
        [sys.executable, "-O", "-c", code],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "three optimized refusals"


@pytest.mark.asyncio
@pytest.mark.parametrize("exit_kind", ["caller-error", "early-break"])
async def test_scoped_iteration_closes_on_caller_error_or_early_exit(owner, exit_kind):
    session = Session(owner)
    phase = {1: (0.3, 0.2, 0.4), 2: (0.3, None, None), 3: (0.3, 0.2, 0.4)}
    try:
        async with aclosing(owner.iter_phase(session, phase)) as results:
            async for _result in results:
                assert owner._active == 1
                if exit_kind == "caller-error":
                    raise LookupError("caller result processing failed")
                break
    except LookupError:
        assert exit_kind == "caller-error"
    assert owner._active == 0
    assert [parameters["kalshi_outcome_id"] for _, parameters in session.calls] == [1]
    owner.close()


def test_utility_import_adds_no_private_requirements_to_initialized_factory():
    code = """
import sys
from importlib.abc import MetaPathFinder
# The public factory initializes the normal application engine independently.
from app.utils import kalshi_price_statement
for name in tuple(sys.modules):
    if name == "asyncpg" or name.startswith("asyncpg."):
        del sys.modules[name]
from sqlalchemy.dialects.postgresql import asyncpg as dialect
del dialect.AsyncAdapt_asyncpg_cursor
del dialect.AsyncAdapt_asyncpg_connection
class Block(MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname == "asyncpg":
            raise ImportError("private adapter deliberately unavailable")
sys.meta_path.insert(0, Block())
from app.utils import kalshi_price_pipeline
print("lazy module import")
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "lazy module import"
