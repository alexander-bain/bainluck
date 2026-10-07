"""#10693: guarded per-statement Kalshi execution on a caller-owned engine.

This utility owns no session, transaction, retry, counters or quote policy.
Singleton-only phases use ordinary factory execution without compatibility work.
A qualifying phase selects compatibility before its first price write. Submitted
work never falls back or replays: the caller retains rollback and retry policy.
"""

from __future__ import annotations

from collections import deque
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
import importlib
import importlib.metadata
from itertools import groupby
from typing import Any

from sqlalchemy import event
from sqlalchemy.exc import CompileError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.utils.kalshi_price_statement import (
    KALSHI_PRICE_STATEMENTS,
    kalshi_price_parameters,
)

_SUPPORTED = ("2.0.50", "0.31.0")
_TAG = "_kalshi_price_pipeline_10693"
_OWNER = "_kalshi_price_pipeline_10693_owner"
PriceInput = tuple[float, float | None, float | None]


@dataclass(frozen=True)
class PriceRunResult:
    """One completed run; failed runs expose no partial diagnostic prefix."""

    attempted: int
    rows: tuple[Any, ...]

    @property
    def rowcount(self) -> int:
        return len(self.rows)

    def all(self) -> list[Any]:
        return list(self.rows)


@dataclass(frozen=True)
class _Template:
    sql: str
    positions: tuple[str, ...]
    defaults: Mapping[str, Any]
    processors: Mapping[str, Any]

    def args(self, outcome_id: int, values: PriceInput) -> tuple[Any, ...]:
        supplied = kalshi_price_parameters(outcome_id, *values)
        return tuple(
            self.processors[key](value) if key in self.processors else value
            for key in self.positions
            for value in [supplied[key] if key in supplied else self.defaults[key]]
        )


def _load_compatibility():
    """Only absence of the declared compatibility surface selects fallback."""
    try:
        versions = tuple(
            importlib.metadata.version(name) for name in ("sqlalchemy", "asyncpg")
        )
        if versions != _SUPPORTED:
            return None
        dialect = importlib.import_module("sqlalchemy.dialects.postgresql.asyncpg")
        driver = importlib.import_module("asyncpg")
        return (
            dialect.AsyncAdapt_asyncpg_cursor,
            dialect.AsyncAdapt_asyncpg_connection,
            driver.Connection,
            dialect.dialect,
        )
    except (ImportError, AttributeError):
        return None


def _templates(dialect_factory) -> dict[bool, _Template] | None:
    try:
        result = {}
        for book, statement in KALSHI_PRICE_STATEMENTS.items():
            compiled = statement.compile(dialect=dialect_factory())
            expanded = compiled.construct_expanded_state(
                kalshi_price_parameters(
                    1, 0.3, 0.2 if book else None, 0.4 if book else None
                )
            )
            if not expanded.positiontup or not isinstance(expanded.statement, str):
                return None
            result[book] = _Template(
                expanded.statement,
                tuple(expanded.positiontup),
                dict(expanded.parameters),
                dict(expanded.processors),
            )
        return result
    except (AttributeError, TypeError, CompileError, NotImplementedError):
        return None


def _cursor_supported(cursor, parameters, compatibility) -> bool:
    cursor_type, adapter_type, connection_type, _dialect = compatibility
    if type(cursor) is not cursor_type:
        return False
    adapter = getattr(cursor, "_adapt_connection", None)
    if (
        type(adapter) is not adapter_type
        or type(getattr(adapter, "_connection", None)) is not connection_type
    ):
        return False
    if not isinstance(getattr(cursor, "_rows", None), deque):
        return False
    if not isinstance(
        getattr(cursor, "_invalidate_schema_cache_asof", None), (int, float)
    ):
        return False
    if not isinstance(getattr(adapter, "_started", None), bool):
        return False
    if not all(
        callable(getattr(adapter, name, None))
        for name in (
            "await_",
            "_check_type_cache_invalidation",
            "_start_transaction",
            "_prepare",
            "_handle_exception",
        )
    ):
        return False
    if not callable(getattr(adapter._connection, "fetchmany", None)):
        return False
    mutex = getattr(adapter, "_execute_mutex", None)
    if not all(
        callable(getattr(mutex, name, None)) for name in ("__aenter__", "__aexit__")
    ):
        return False
    return (
        isinstance(parameters, list)
        and len(parameters) > 1
        and all(
            isinstance(row, tuple) and len(row) == len(parameters[0])
            for row in parameters
        )
    )


async def _adapted_fetchmany(cursor, statement, parameters):
    """Retained e1d70749 await/mutex/cache/error path, without lab telemetry."""
    adapter = cursor._adapt_connection
    cursor.description = None
    async with adapter._execute_mutex:
        await adapter._check_type_cache_invalidation(
            cursor._invalidate_schema_cache_asof
        )
        if not adapter._started:
            await adapter._start_transaction()
        try:
            _, attributes = await adapter._prepare(
                statement, cursor._invalidate_schema_cache_asof
            )
            cursor.description = [
                (attr.name, attr.type.oid, None, None, None, None, None)
                for attr in attributes
            ]
            cursor._rows = deque(
                await adapter._connection.fetchmany(statement, parameters)
            )
            cursor.rowcount = len(cursor._rows)
        except Exception as error:
            cursor._handle_exception(error)


class KalshiPricePipeline:
    """Engine-local listener and lazy compatibility, owned by its consumer."""

    def __init__(self, engine: AsyncEngine):
        if getattr(engine.sync_engine, _OWNER, None) is not None:
            raise RuntimeError("Kalshi price pipeline is already installed")
        self.engine = engine
        self._token = object()
        self._closed = False
        self._active = 0
        self._compatibility_checked = False
        self._compatibility = None
        self._templates = None
        self._listener = self._do_executemany
        event.listen(engine.sync_engine, "do_executemany", self._listener)
        setattr(engine.sync_engine, _OWNER, self)

    def close(self) -> None:
        if self._closed:
            return
        if self._active:
            raise RuntimeError(
                "finish or cancel Kalshi price phases before listener cleanup"
            )
        if getattr(self.engine.sync_engine, _OWNER, None) is not self:
            raise RuntimeError("Kalshi price listener ownership changed")
        event.remove(self.engine.sync_engine, "do_executemany", self._listener)
        delattr(self.engine.sync_engine, _OWNER)
        self._closed = True

    def _do_executemany(self, cursor, statement, parameters, context):
        if _TAG not in context.execution_options:
            return None
        if (
            self._closed
            or context.execution_options[_TAG] is not self._token
            or self._compatibility is None
            or self._templates is None
        ):
            raise RuntimeError(
                "refused unowned tagged Kalshi price operation; no replay"
            )
        template = next(
            (t for t in self._templates.values() if t.sql == statement), None
        )
        if (
            template is None
            or not _cursor_supported(cursor, parameters, self._compatibility)
            or any(len(row) != len(template.positions) for row in parameters)
        ):
            raise RuntimeError(
                "refused unexpected tagged Kalshi SQL/cursor/parameters; no replay"
            )
        cursor._adapt_connection.await_(
            _adapted_fetchmany(cursor, statement, parameters)
        )
        return True

    async def _preflight(self, session, runs):
        if not self._compatibility_checked:
            self._compatibility = _load_compatibility()
            if self._compatibility is not None:
                self._templates = _templates(self._compatibility[3])
            self._compatibility_checked = True
        if self._compatibility is None or self._templates is None:
            return None
        # Checkout and real connection errors are outside compatibility catches.
        connection = await session.connection()
        raw = await connection.get_raw_connection()
        cursor_factory = getattr(raw.dbapi_connection, "cursor", None)
        if not callable(cursor_factory):
            return None
        try:
            cursor = cursor_factory()
        except (AttributeError, TypeError):
            return None
        try:
            for book, items in runs:
                if len(items) > 1:
                    args = [
                        self._templates[book].args(oid, values) for oid, values in items
                    ]
                    if not _cursor_supported(cursor, args, self._compatibility):
                        return None
        finally:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()
        return connection

    async def iter_phase(
        self,
        session: AsyncSession,
        phase: Mapping[int, PriceInput],
    ) -> AsyncIterator[PriceRunResult]:
        """Consume in contextlib.aclosing; caller errors must close the iterator.

        The caller must exhaust a successful phase. Early exit requires its
        normal transaction rollback, not committing an incomplete price phase.
        """
        if self._closed:
            raise RuntimeError("Kalshi price pipeline is closed")
        bind = session.bind
        if bind is not self.engine and getattr(bind, "engine", None) is not self.engine:
            raise RuntimeError("Kalshi price phase belongs to a different engine")
        runs = [
            (book, list(items))
            for book, items in groupby(
                tuple(phase.items()),
                key=lambda item: item[1][1] is not None and item[1][2] is not None,
            )
        ]
        self._active += 1
        try:
            connection = (
                await self._preflight(session, runs)
                if any(len(items) > 1 for _, items in runs)
                else None
            )
            for book, items in runs:
                if connection is None or len(items) == 1:
                    for oid, values in items:
                        result = await session.execute(
                            KALSHI_PRICE_STATEMENTS[book],
                            kalshi_price_parameters(oid, *values),
                        )
                        yield PriceRunResult(1, tuple(result.all()))
                else:
                    template = self._templates[book]
                    result = await connection.exec_driver_sql(
                        template.sql,
                        [template.args(oid, values) for oid, values in items],
                        execution_options={_TAG: self._token},
                    )
                    yield PriceRunResult(len(items), tuple(result.all()))
        finally:
            self._active -= 1


def install_kalshi_price_pipeline(engine: AsyncEngine) -> KalshiPricePipeline:
    """Install once, without private imports, version probes or compilation."""
    existing = getattr(engine.sync_engine, _OWNER, None)
    if existing is not None:
        if not isinstance(existing, KalshiPricePipeline):
            raise RuntimeError("Kalshi price pipeline owner attribute is occupied")
        return existing
    return KalshiPricePipeline(engine)
