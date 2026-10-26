"""Explicit read-only preparation for the #10090 attended recovery command.

No mutating command is exposed until the all-writer interlock is implemented
and reviewed. A matching preview is a snapshot, never permission to activate.
Credentials are explicit environment inputs, not inherited application defaults.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
import json
import os
import re
from uuid import UUID

from app.services.dnpl_authority import Authority, AuthorityConflict, AuthorityStore

READ_BUDGET_S = 1.0
_PRIMARY = re.compile(r"([0-9a-f]{40}):([0-9a-f]{40})\Z")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate authority field")
        result[key] = value
    return result


def parse_authority(value: str) -> Authority:
    """An exact comparison target, explicitly NOT writer-stop evidence."""
    if len(value) > 2048:
        raise ValueError("authority input too large")
    fields = json.loads(value, object_pairs_hook=_unique_object)
    if not isinstance(fields, dict) or set(fields) != set(
        Authority.__dataclass_fields__
    ):
        raise ValueError("exact authority fields required")
    for key in ("namespace", "operation_id"):
        fields[key] = UUID(fields[key])
    return Authority(**fields)


def parse_primary(value: str) -> tuple[str, str]:
    match = _PRIMARY.fullmatch(value)
    if match is None:
        raise ValueError("primary must be run_id:master_replid")
    return match.group(1), match.group(2)


async def preview(store, redis, expected: Authority, primary: tuple[str, str]) -> dict:
    """Bounded reads; changes during the sample refuse instead of inferring readiness.

    INFO returns both identities in one command. The authority, activation step
    and predecessor are checked again after it. This detects observed change;
    it does not establish a distributed snapshot or fence a subsequent command.
    """
    async with asyncio.timeout(READ_BUDGET_S):
        current = await store.read()
        if current != expected:
            raise AuthorityConflict("expected authority differs")
        step = await store.activation_step(expected)
        retired = await store.read_retirement()
        info = await redis.info("all")
        if (
            info.get("role") != "master"
            or (info.get("run_id"), info.get("master_replid")) != primary
        ):
            raise AuthorityConflict("expected Redis primary differs")
        if (
            await store.read() != expected
            or await store.activation_step(expected) != step
            or await store.read_retirement() != retired
        ):
            raise AuthorityConflict("authority changed during preview")
        return {
            "status": "SNAPSHOT_MATCH",
            "authority": asdict(current),
            "activation_step": step,
            "retirement": None if retired is None else asdict(retired),
            "primary": {"run_id": primary[0], "master_replid": primary[1]},
            "primary_matches_authority": primary
            == (current.redis_run_id, current.redis_master_replid),
            "mutation_permitted": False,
            "interlock": "UNIMPLEMENTED",
            "qualification": "snapshot only; no activation, provider or reader acceptance",
        }


async def _configured_preview(expected, primary):
    from redis.asyncio import Redis
    from redis.backoff import NoBackoff
    from redis.retry import Retry
    from sqlalchemy.engine import make_url
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    # No DATABASE_URL / REDIS_URL fallback: invocation must select its targets.
    url = make_url(os.environ["DNPL_COMMAND_DATABASE_URL"])
    if url.get_backend_name() not in ("postgres", "postgresql"):
        raise ValueError("PostgreSQL required")
    url = url.set(drivername="postgresql+asyncpg")
    redis_url = os.environ["DNPL_COMMAND_REDIS_URL"]
    engine = create_async_engine(
        url,
        poolclass=NullPool,
        connect_args={
            "timeout": READ_BUDGET_S,
            "server_settings": {
                "default_transaction_read_only": "on",
                "statement_timeout": "150",
                "lock_timeout": "150",
            },
        },
    )
    client = Redis.from_url(
        redis_url,
        decode_responses=True,
        socket_timeout=0.150,
        socket_connect_timeout=0.150,
        retry=Retry(NoBackoff(), 0),
    )
    try:
        return await preview(
            AuthorityStore(async_sessionmaker(engine, expire_on_commit=False)),
            client,
            expected,
            primary,
        )
    finally:
        await client.aclose()
        await engine.dispose()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("preview",))
    parser.add_argument("--expected-authority", required=True)
    parser.add_argument("--expected-primary", required=True)
    args = parser.parse_args(argv)
    try:
        expected = parse_authority(args.expected_authority)
        primary = parse_primary(args.expected_primary)
        result = asyncio.run(_configured_preview(expected, primary))
    except Exception as exc:
        # Connection errors can contain URLs/credentials; never emit their text.
        print(json.dumps({"status": "REFUSED", "error_type": type(exc).__name__}))
        return 2
    print(json.dumps(result, default=str, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
