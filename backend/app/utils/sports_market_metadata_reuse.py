"""Share unchanged Sports market metadata; prices and reader state stay fresh.

The cache stores only MARKET_COLUMNS. A PostgreSQL MVCC probe selects the
current metadata identity before any reuse. Outcomes, Sport rows, withholding,
and the personalized scoring/display chain are never part of this artifact.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from types import SimpleNamespace
from typing import Any

from sqlalchemy import JSON, func, literal_column, select
from sqlalchemy.orm import load_only

from app.models.models import FuturesMarket, FuturesOutcome, Sport
from app.utils import principal_independent_cache as cache
from app.utils.futures_market_snapshot import (
    MARKET_COLUMNS,
    OUTCOME_COLUMNS,
    OUTCOME_LOAD_ONLY_EXTRA,
    SPORT_COLUMNS,
)

logger = logging.getLogger(__name__)
NAMESPACE = "sports_metadata"
FORMAT_VERSION = 1


class _MetadataMoved(Exception):
    """A fresh read changed after the probe; return it without caching it."""

    def __init__(self, payload: dict[str, Any]):
        super().__init__("market metadata changed during the read")
        self.payload = payload


def _proof_columns() -> tuple[Any, ...]:
    return (
        func.current_database().label("metadata_database"),
        func.pg_postmaster_start_time().label("metadata_server_start"),
        literal_column("futures_markets.tableoid::text").label("metadata_table"),
        literal_column("futures_markets.xmin::text").label("metadata_xmin"),
        literal_column("futures_markets.ctid::text").label("metadata_ctid"),
    )


def _identity(rows: list[Any], width: int) -> tuple[tuple[str, str], tuple]:
    scope = None
    versions = []
    for row in rows:
        if len(row) != width + 5 or type(row[0]) is not int:
            raise ValueError("invalid market metadata row")
        database, started, table, xmin, ctid = row[width:]
        if not isinstance(database, str) or not isinstance(started, datetime):
            raise ValueError("invalid database identity")
        if not all(isinstance(value, str) and value for value in (table, xmin, ctid)):
            raise ValueError("invalid market row version")
        row_scope = (database, started.isoformat())
        if scope is not None and scope != row_scope:
            raise ValueError("mixed database identities")
        scope = row_scope
        versions.append((row[0], table, xmin, ctid))
    if scope is None or len({version[0] for version in versions}) != len(versions):
        raise ValueError("missing or duplicate market versions")
    return scope, tuple(sorted(versions))


def _json_value(value: Any) -> bool:
    if value is None or type(value) in (bool, int, float, str):
        return True
    if isinstance(value, list):
        return all(_json_value(item) for item in value)
    if isinstance(value, dict):
        return all(
            type(key) is str and _json_value(item) for key, item in value.items()
        )
    return False


def _column_value(name: str, value: Any) -> None:
    """Refuse cache values that cannot have come from the selected column."""
    column = FuturesMarket.__table__.c[name]
    if value is None:
        if not column.nullable:
            raise ValueError("null in required metadata column")
        return
    if isinstance(column.type, JSON):
        if not _json_value(value):
            raise ValueError("invalid metadata JSON")
        return
    expected_type = column.type.python_type
    if expected_type is datetime:
        if not isinstance(value, datetime):
            raise ValueError("invalid metadata datetime")
        if column.type.timezone and value.utcoffset() is None:
            raise ValueError("metadata datetime lost its timezone")
    elif type(value) is not expected_type:
        # bool is not an integer column, nor is a string a timestamp/number.
        raise ValueError("invalid metadata column type")
    if (
        isinstance(value, str)
        and column.type.length
        and len(value) > column.type.length
    ):
        raise ValueError("metadata string exceeds its column")


def _payload_rows(payload: Any, expected: tuple | None) -> list[list[Any]]:
    if not isinstance(payload, dict) or type(payload.get("format")) is not int:
        raise ValueError("invalid metadata payload")
    if payload["format"] != FORMAT_VERSION or payload.get("columns") != MARKET_COLUMNS:
        raise ValueError("unsupported metadata columns")
    rows = payload.get("rows")
    versions = payload.get("versions")
    if not isinstance(rows, list) or not isinstance(versions, tuple):
        raise ValueError("invalid metadata rows or versions")
    ids = []
    for row in rows:
        if not isinstance(row, list) or len(row) != len(MARKET_COLUMNS):
            raise ValueError("invalid metadata width")
        if type(row[0]) is not int:
            raise ValueError("invalid metadata id")
        for name, value in zip(MARKET_COLUMNS, row):
            _column_value(name, value)
        ids.append(row[0])
    if len(set(ids)) != len(ids) or set(ids) != {version[0] for version in versions}:
        raise ValueError("metadata membership differs from its proof")
    if expected is not None and (payload.get("scope"), versions) != expected:
        raise ValueError("metadata does not match the current probe")
    return rows


async def load_sports_markets(
    db: Any, market_ids: list[int]
) -> list[SimpleNamespace] | None:
    """Return ready rows, or None to use the unchanged direct loader.

    A cache hit describes the probe snapshot, matching the existing separate
    market/outcome reads; it does not promise an atomic page. Added SQL is in
    a savepoint so a failed fingerprint cannot poison the fallback transaction.
    """
    if os.getenv("FEED_SPORTS_METADATA_REUSE", "0").strip() != "1":
        return None
    if cache.shared_build_ttl_s(NAMESPACE) <= 0:
        return None
    try:
        if db.get_bind().dialect.name != "postgresql":
            return None
    except (AttributeError, TypeError):
        return None
    if not market_ids:
        return []

    names: list[str] = []
    tiers: list[str] = []
    ages: list[float] = []
    strict_ages: list[float] = []
    observed_at = time.monotonic()
    reused = False
    try:
        async with db.begin_nested():
            probe = await db.execute(
                select(FuturesMarket.id, *_proof_columns()).where(
                    FuturesMarket.id.in_(market_ids)
                )
            )
            probe_rows = list(probe.all())
            if not probe_rows:
                return []
            expected = _identity(probe_rows, 1)
            key = (FORMAT_VERSION, MARKET_COLUMNS, *expected)

            async def build() -> dict[str, Any]:
                fresh = await db.execute(
                    select(
                        *(getattr(FuturesMarket, name) for name in MARKET_COLUMNS),
                        *_proof_columns(),
                    ).where(FuturesMarket.id.in_(market_ids))
                )
                fresh_rows = list(fresh.all())
                # No ORM identity-map read and no outcome-derived values.
                if not fresh_rows:
                    raise _MetadataMoved(
                        {
                            "format": FORMAT_VERSION,
                            "columns": MARKET_COLUMNS,
                            "scope": expected[0],
                            "versions": (),
                            "rows": [],
                        }
                    )
                scope, versions = _identity(fresh_rows, len(MARKET_COLUMNS))
                payload = {
                    "format": FORMAT_VERSION,
                    "columns": MARKET_COLUMNS,
                    "scope": scope,
                    "versions": versions,
                    "rows": [list(row[: len(MARKET_COLUMNS)]) for row in fresh_rows],
                }
                if (scope, versions) != expected:
                    raise _MetadataMoved(payload)
                return payload

            # Cache accounting is provisional until the complete proof passes.
            with cache.reuse_scope(names, tiers, ages, strict_ages):
                try:
                    payload = await cache.get_or_build(NAMESPACE, key, build)
                    rows = _payload_rows(payload, expected)
                    reused = NAMESPACE in names
                except _MetadataMoved as moved:
                    rows = _payload_rows(moved.payload, None)
                    reused = False

            if not rows:
                return []
            by_id = {
                row[0]: SimpleNamespace(**dict(zip(MARKET_COLUMNS, row)))
                for row in rows
            }
            # Only the selected IDs/order drive the personalized pass.
            markets = [by_id[mid] for mid in market_ids if mid in by_id]
            ids = [row[0] for row in rows]
            outcome_columns = tuple(
                dict.fromkeys(
                    ("market_id",) + OUTCOME_COLUMNS + OUTCOME_LOAD_ONLY_EXTRA
                )
            )
            outcome_result = await db.execute(
                select(FuturesOutcome)
                .options(
                    load_only(
                        *(getattr(FuturesOutcome, name) for name in outcome_columns)
                    )
                )
                .where(FuturesOutcome.market_id.in_(ids))
                .execution_options(populate_existing=True)
            )
            outcomes: dict[int, list[Any]] = {}
            for outcome in outcome_result.scalars().unique().all():
                outcomes.setdefault(outcome.market_id, []).append(outcome)
            sport_ids = {
                market.sport_id for market in markets if market.sport_id is not None
            }
            sports = {}
            if sport_ids:
                sport_result = await db.execute(
                    select(Sport)
                    .options(
                        load_only(*(getattr(Sport, name) for name in SPORT_COLUMNS))
                    )
                    .where(Sport.id.in_(sport_ids))
                    .execution_options(populate_existing=True)
                )
                sports = {sport.id: sport for sport in sport_result.scalars().all()}
            for market in markets:
                market.outcomes = outcomes.get(market.id, [])
                market.sport = sports.get(market.sport_id)
        if reused:
            cache.note_validated_metadata_reuse(tiers, observed_at)
        logger.info(
            "sports_metadata_reuse reused=%s tier=%s markets=%s",
            int(reused),
            ",".join(tiers) if reused else "built",
            len(markets),
        )
        return markets
    except Exception as exc:
        # begin_nested has restored SQL state before the original loader runs.
        # Cancellation (BaseException) remains cancellation.
        logger.debug("sports metadata reuse fell back (%s)", type(exc).__name__)
        return None
