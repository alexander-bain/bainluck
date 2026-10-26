"""Explicit invocation of the reviewed recovery runner; never a startup hook.

An operation owner supplies a bounded plan after separately qualifying P-EXCL,
deployed source/migrations, storage cutover and provider assumptions. This CLI
neither establishes those premises nor stops/starts workers. No retry or resume
is automatic; uncertain outcomes stop the plan with send records intact.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict, dataclass, replace
import json
import os
from pathlib import Path
import re
import stat
from uuid import UUID

from app.services.dnpl_activation import ActivationController
from app.services.dnpl_activation_command import (
    _unique_object,
    parse_authority,
    parse_primary,
)
from app.services.dnpl_activation_runner import STEPS, run_step
from app.services.dnpl_authority import Authority, AuthorityStore, preparing_candidate
from app.services.dnpl_operation_hold import DeskHold, _write_once
from app.services.dnpl_writer_observations import APPS

MAX_PLAN_BYTES = 65536
MAX_STEPS = 8


@dataclass(frozen=True)
class PlannedStep:
    step: str
    expected: Authority
    candidate: Authority | None


@dataclass(frozen=True)
class Plan:
    run_id: str
    primary: tuple[str, str]
    apps: dict
    steps: tuple[PlannedStep, ...]
    encoded: bytes


def parse_plan(encoded: bytes) -> Plan:
    """Validate the entire plan before acquiring clients or sending anything."""
    if len(encoded) > MAX_PLAN_BYTES:
        raise ValueError("plan too large")
    data = json.loads(encoded, object_pairs_hook=_unique_object)
    if not isinstance(data, dict) or set(data) != {
        "run_id",
        "primary",
        "apps",
        "steps",
    }:
        raise ValueError("exact plan fields required")
    run_id = UUID(data["run_id"])
    if not run_id.int or str(run_id) != data["run_id"]:
        raise ValueError("canonical nonzero run identity required")
    primary = parse_primary(data["primary"])
    apps = data["apps"]
    if not isinstance(apps, dict) or set(apps) != set(APPS):
        raise ValueError("exact app bindings required")
    for binding in apps.values():
        if not isinstance(binding, dict) or set(binding) != {
            "release",
            "slug",
            "commit",
        }:
            raise ValueError("exact release binding required")
        if type(binding["release"]) is not int or binding["release"] <= 0:
            raise ValueError("positive release required")
        if str(UUID(binding["slug"])) != binding["slug"]:
            raise ValueError("canonical slug required")
        if re.fullmatch(r"[0-9a-f]{40}", binding["commit"]) is None:
            raise ValueError("exact commit required")
    if len({binding["commit"] for binding in apps.values()}) != 1:
        raise ValueError("converged source required")
    if not isinstance(data["steps"], list) or not 1 <= len(data["steps"]) <= MAX_STEPS:
        raise ValueError("bounded nonempty step list required")
    steps, seen, following = [], set(), None
    for item in data["steps"]:
        if not isinstance(item, dict) or set(item) != {"step", "expected", "candidate"}:
            raise ValueError("exact step fields required")
        step = item["step"]
        if step not in STEPS:
            raise ValueError("unknown recovery step")
        expected = parse_authority(json.dumps(item["expected"]))
        candidate = (
            None
            if item["candidate"] is None
            else parse_authority(json.dumps(item["candidate"]))
        )
        if (step == "prepare") != (candidate is not None):
            raise ValueError("only prepare requires a candidate")
        if following is not None and following != expected:
            raise ValueError("plan authority discontinuity")
        if candidate is not None:
            if candidate != preparing_candidate(
                expected,
                namespace=candidate.namespace,
                operation_id=candidate.operation_id,
                redis_run_id=primary[0],
                redis_master_replid=primary[1],
                policy_fingerprint=candidate.policy_fingerprint,
            ):
                raise ValueError("candidate must be the exact next allocation")
        identity = (step, expected, candidate)
        if identity in seen:
            raise ValueError("duplicate operation in plan")
        seen.add(identity)
        steps.append(PlannedStep(step, expected, candidate))
        following = (
            candidate
            if candidate is not None
            else replace(expected, state="ready") if step == "ready" else expected
        )
    canonical = json.dumps(
        data, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    return Plan(str(run_id), primary, apps, tuple(steps), canonical)


def read_plan(path: Path) -> Plan:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_mode & 0o077
        ):
            raise ValueError("private owned regular plan file required")
        with os.fdopen(os.dup(fd), "rb") as source:
            encoded = source.read(MAX_PLAN_BYTES + 1)
    finally:
        os.close(fd)
    return parse_plan(encoded)


async def execute_plan(plan, controller, *, lock_path, identity, run_dir):
    """One uninterrupted local hold; every step retains the reviewed verifier."""
    _write_once(run_dir, "plan.json", plan.encoded)
    outcomes = []
    with DeskHold.capture(lock_path, identity, run_dir) as hold:
        for item in plan.steps:
            result = await run_step(
                hold=hold,
                controller=controller,
                run_dir=run_dir,
                run_id=plan.run_id,
                primary=plan.primary,
                apps=plan.apps,
                step=item.step,
                expected=item.expected,
                candidate=item.candidate,
            )
            outcomes.append(asdict(result))
            if result.status != "DONE":
                return {"status": result.status, "steps": outcomes}
        if plan.steps[-1].step == "ready":
            hold.check()
            if not await controller.read_ready(plan.steps[-1].expected):
                return {
                    "status": "UNCERTAIN",
                    "steps": outcomes,
                    "ready_readback": False,
                }
            hold.check()
    return {"status": "PLAN_DONE", "steps": outcomes}


async def configured_plan(plan, **kwargs):
    from redis.asyncio import Redis
    from redis.backoff import NoBackoff
    from redis.retry import Retry
    from sqlalchemy.engine import make_url
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    # Targets are explicit. Application credential defaults are never consulted.
    url = make_url(os.environ["DNPL_COMMAND_DATABASE_URL"])
    if url.get_backend_name() not in ("postgres", "postgresql"):
        raise ValueError("PostgreSQL required")
    redis_url = os.environ["DNPL_COMMAND_REDIS_URL"]
    engine = create_async_engine(
        url.set(drivername="postgresql+asyncpg"),
        poolclass=NullPool,
        connect_args={
            "timeout": 1.0,
            "server_settings": {
                "statement_timeout": "150",
                "lock_timeout": "150",
            },
        },
    )
    client = None
    try:
        client = Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_timeout=0.150,
            socket_connect_timeout=0.150,
            retry=Retry(NoBackoff(), 0),
        )
        controller = ActivationController(
            AuthorityStore(async_sessionmaker(engine, expire_on_commit=False)),
            client,
        )
        return await execute_plan(plan, controller, **kwargs)
    finally:
        try:
            if client is not None:
                await client.aclose()
        finally:
            await engine.dispose()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("execute-plan",))
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        plan = read_plan(args.plan)
    except Exception as exc:
        print(json.dumps({"status": "REFUSED", "error_type": type(exc).__name__}))
        return 2
    try:
        result = asyncio.run(
            configured_plan(
                plan,
                lock_path=args.lock,
                identity=args.owner,
                run_dir=args.run_dir,
            )
        )
    except Exception as exc:
        # A late local error can follow a completed send. Never label it unsent
        # or expose connection exception text, which may contain credentials.
        print(
            json.dumps(
                {
                    "status": "STOPPED",
                    "may_have_sent": True,
                    "error_type": type(exc).__name__,
                }
            )
        )
        return 3
    print(json.dumps(result, default=str, sort_keys=True))
    return 0 if result["status"] == "PLAN_DONE" else 3


if __name__ == "__main__":
    raise SystemExit(main())
