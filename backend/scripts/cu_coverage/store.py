"""Atomic before-images for the attended #1809 coverage run."""

from __future__ import annotations

from hashlib import sha256
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.durable_snapshots import publish_cas_snapshot_in_txn, read_snapshot
from app.utils.durable_state import DurableEnvelope, canonical_json

RUN_ID = "cu-coverage-20261127-full"
UNDO_SCHEMA = "cu-coverage-undo-v1"
WRITER_REV = 10
JOURNAL_MAX_AGE_SECONDS = 365 * 24 * 60 * 60

_MARKET_FOR_UPDATE = text(
    """
    SELECT source, status, name, updated_at, story_key,
           jsonb_typeof(market_metadata) AS metadata_type,
           CAST(market_metadata -> 'discover_llm' AS text) AS profile_json
    FROM futures_markets
    WHERE id = :market_id
    FOR UPDATE
    """
)

_REPLACE_PROFILE = text(
    """
    UPDATE futures_markets
    SET market_metadata = jsonb_set(
        CASE WHEN jsonb_typeof(market_metadata) = 'object'
             THEN market_metadata ELSE '{}'::jsonb END,
        '{discover_llm}',
        (CAST(:new_profile AS jsonb) - 'story_key') ||
        CASE WHEN jsonb_typeof(market_metadata -> 'discover_llm') = 'object'
                  AND (market_metadata -> 'discover_llm') ? 'story_key'
             THEN jsonb_build_object('story_key', market_metadata #> '{discover_llm,story_key}')
             ELSE '{}'::jsonb END
    )
    WHERE id = :market_id
    RETURNING updated_at, story_key,
              CAST(market_metadata -> 'discover_llm' AS text) AS profile_json
    """
)

_PROFILE_STORY_KEY = text(
    """
    SELECT CAST(CAST(:before_profile AS jsonb) -> 'story_key' AS text) AS before_key,
           CAST(CAST(:after_profile AS jsonb) -> 'story_key' AS text) AS after_key
    """
)


class CoverageStoreError(RuntimeError):
    """An invariant failed in the same transaction as the profile write."""


def undo_identity(market_id: int) -> str:
    return f"{RUN_ID}:undo:{market_id}"


def profile_hash(profile_json: str | None) -> str | None:
    return None if profile_json is None else sha256(profile_json.encode()).hexdigest()


async def _lock_market(db: AsyncSession, market_id: int):
    await db.execute(text("SET LOCAL statement_timeout = '5s'"))
    await db.execute(text("SET LOCAL lock_timeout = '250ms'"))
    return (
        (await db.execute(_MARKET_FOR_UPDATE, {"market_id": market_id}))
        .mappings()
        .one_or_none()
    )


async def _read_undo(db: AsyncSession, market_id: int) -> dict[str, Any] | None:
    result = await read_snapshot(
        db,
        undo_identity(market_id),
        expected_version=UNDO_SCHEMA,
        max_age_s=JOURNAL_MAX_AGE_SECONDS,
    )
    if result.missing:
        return None
    if not result.ok or result.envelope is None:
        raise CoverageStoreError(f"before-image read {market_id}: {result.status}")
    payload = result.envelope.payload
    if payload["market_id"] != market_id or payload["run_id"] != RUN_ID:
        raise CoverageStoreError(f"before-image identity mismatch for {market_id}")
    return payload


async def write_profile(
    db: AsyncSession,
    market_id: int,
    *,
    expected_source: str,
    expected_title: str,
    expected_profile_json: str | None,
    profile: dict[str, Any],
    pilot_source: dict[str, Any] | None = None,
) -> str:
    """Update one market and retain its exact before-image in the same commit."""
    if profile.get("writer_rev") != WRITER_REV or profile.get("schema_version") != 2:
        raise CoverageStoreError(
            f"expected Content Understanding writer revision {WRITER_REV}"
        )

    async with db.begin():
        row = await _lock_market(db, market_id)
        if row is None:
            return "missing"
        undo = await _read_undo(db, market_id)
        if undo is not None:
            if profile_hash(row["profile_json"]) == undo["written_sha256"]:
                return "already_written"
            return "profile_changed_since_write"
        if (
            row["status"] != "open"
            or row["source"] != expected_source
            or row["name"] != expected_title
            or row["profile_json"] != expected_profile_json
        ):
            return "input_changed"
        if row["metadata_type"] not in (None, "null", "object"):
            return "unsupported_metadata"

        after = (
            (
                await db.execute(
                    _REPLACE_PROFILE,
                    {"market_id": market_id, "new_profile": canonical_json(profile)},
                )
            )
            .mappings()
            .one()
        )
        before_json = row["profile_json"]
        after_json = after["profile_json"]
        story = (
            (
                await db.execute(
                    _PROFILE_STORY_KEY,
                    {"before_profile": before_json, "after_profile": after_json},
                )
            )
            .mappings()
            .one()
        )
        if (
            after_json is None
            or after["updated_at"] != row["updated_at"]
            or after["story_key"] != row["story_key"]
            or story["after_key"] != story["before_key"]
        ):
            raise CoverageStoreError(
                f"profile write changed reader state for {market_id}"
            )

        payload = {
            "run_id": RUN_ID,
            "market_id": market_id,
            "previous_metadata_type": row["metadata_type"] or "sql_null",
            "previous_profile_json": before_json,
            "written_sha256": profile_hash(after_json),
            "unchanged_updated_at": row["updated_at"],
            "unchanged_column_story_key": row["story_key"],
            "unchanged_profile_story_key": story["before_key"],
        }
        if pilot_source is not None:
            payload["pilot_source"] = pilot_source
            payload["pilot_profile_json"] = after_json

        envelope = DurableEnvelope.build(
            identity=undo_identity(market_id),
            schema_version=UNDO_SCHEMA,
            generation=1,
            payload=payload,
            source=RUN_ID,
        )
        result = await publish_cas_snapshot_in_txn(
            db, envelope, expected_generation=None
        )
        if result.get("status") != "ok":
            raise CoverageStoreError(f"could not stage before-image for {market_id}")
        found = await _read_undo(db, market_id)
        if found is None or found["written_sha256"] != payload["written_sha256"]:
            raise CoverageStoreError(
                f"before-image verification failed for {market_id}"
            )
        return "written"
