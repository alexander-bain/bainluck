"""#10090: build the two operator plans for a LIMITS-ONLY preview reservation change.

PILLAR: TRUTH / FORMATTING. SHIP: busy live games in the "Other" reservation
stop having their sub-second price previews refused for want of a slot.

The reservation sizes are part of the policy fingerprint. A ready v3 authority
binds that fingerprint in PostgreSQL, in its Redis guard token and in its ledger,
and a producer whose configured sizes differ refuses to bind (fail closed). So a
size change is never an in-place edit: it is the existing reviewed recovery
sequence (prepare, arm, initialize, ready, then retire the predecessor) with a
fresh incarnation whose fingerprint differs ONLY in its sizes. This script adds
no mutation primitive; it builds and validates plans for
`python -m app.services.dnpl_activation_operator execute-plan`, which keeps its
writer verifier, desk hold, single-send records and fences unchanged.

Offline and read-only: no network, database or Redis. It refuses unless

- the expected authority is ready, on the given primary (normal retirement);
- its fingerprint is `<version>-six-hour-<map>:<six sizes>` with the SAME
  league-map hash this checkout computes (a map change is not limits-only) and
  the version its sizes imply. The version may change: v2 is v1's semantics at
  the larger ledger cap, chosen only when the target total exceeds v1's 512, so
  a change across 512 is still limits-only. A v1-only writer refuses a v2
  ledger (`policy_mismatch`); the release carrying v2 must therefore be live,
  and every old writer stopped, before the activate plan runs;
- the target sizes differ, are valid, and equal what the app would parse from
  `--configured` (the exact `LIVE_BLEND_PREVIEW_RESERVATIONS` read back from the
  app; an empty string means unset, i.e. the defaults).

Rollback is the same command with `--to default` against the new authority
(`next-expected-authority.json`). Building a plan is not permission to run it.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import json
import os
from pathlib import Path
import re
import sys
from uuid import uuid4

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.dnpl_activation_command import parse_authority, parse_primary  # noqa: E402
from app.services.dnpl_activation_operator import APPS, parse_plan  # noqa: E402
from app.services.dnpl_authority import Authority, preparing_candidate  # noqa: E402
from app.utils.dnpl_redis_authority import namespace_keys  # noqa: E402
from app.utils.preview_reservations import (  # noqa: E402
    DEFAULT_LIMITS,
    RESERVATIONS_ENV,
    ReservationPolicy,
)

_FINGERPRINT = re.compile(r"(v[12])-six-hour-([0-9a-f]{16}):([0-9]+(?:,[0-9]+){5})\Z")


class RelimitRefused(ValueError):
    """The requested change is not a valid limits-only re-fingerprint."""


def split_fingerprint(fingerprint: str) -> tuple[str, str, tuple[int, ...]]:
    """(version, league-map hash, sizes) of a six-hour policy fingerprint."""
    match = _FINGERPRINT.fullmatch(fingerprint)
    if match is None:
        raise RelimitRefused("authority fingerprint is not a v1/v2 six-hour policy")
    limits = tuple(int(n) for n in match.group(3).split(","))
    if match.group(3) != ",".join(str(n) for n in limits):
        raise RelimitRefused("authority fingerprint sizes are not canonical")
    return match.group(1), match.group(2), limits


def parse_limits(value: str) -> tuple[int, ...]:
    if value == "default":
        return DEFAULT_LIMITS
    return configured_policy(value).limits


def configured_policy(value: str) -> ReservationPolicy:
    """Exactly what `ReservationPolicy.configured()` builds from this value."""
    saved = os.environ.get(RESERVATIONS_ENV)
    try:
        if value == "":
            os.environ.pop(RESERVATIONS_ENV, None)
        else:
            os.environ[RESERVATIONS_ENV] = value
        return ReservationPolicy.configured()
    finally:
        if saved is None:
            os.environ.pop(RESERVATIONS_ENV, None)
        else:
            os.environ[RESERVATIONS_ENV] = saved


def target_policy(expected: Authority, limits: tuple[int, ...], configured: str) -> ReservationPolicy:
    version, mapping, current = split_fingerprint(expected.policy_fingerprint)
    # The ledger itself refuses an invalid allocation, or one under the wrong version.
    if ReservationPolicy(current).version != version:
        raise RelimitRefused("authority fingerprint version does not match its sizes")
    target = ReservationPolicy(tuple(limits))
    _, target_mapping, _ = split_fingerprint(target.fingerprint)
    if target_mapping != mapping:
        raise RelimitRefused(
            "league map or semantics version differs from the authority; not limits-only"
        )
    if target.limits == current:
        raise RelimitRefused("target sizes equal the authority's sizes")
    if configured_policy(configured) != target:
        raise RelimitRefused(
            f"{RESERVATIONS_ENV} read back from the app does not produce the target sizes"
        )
    return target


def authority_json(authority: Authority) -> dict:
    return json.loads(json.dumps(asdict(authority), default=str))


def build(
    expected: Authority,
    primary: tuple[str, str],
    apps: dict,
    limits: tuple[int, ...],
    configured: str,
    *,
    namespace=None,
    operation_id=None,
    run_ids=None,
) -> dict:
    if expected.state != "ready" or expected.incarnation < 1:
        raise RelimitRefused("expected authority must be a ready allocated incarnation")
    if (expected.redis_run_id, expected.redis_master_replid) != primary:
        raise RelimitRefused("authority primary differs; this is not the normal route")
    target = target_policy(expected, limits, configured)
    candidate = preparing_candidate(
        expected,
        namespace=namespace or uuid4(),
        operation_id=operation_id or uuid4(),
        redis_run_id=primary[0],
        redis_master_replid=primary[1],
        policy_fingerprint=target.fingerprint,
    )
    ready = replace(candidate, state="ready")
    run_ids = run_ids or (uuid4(), uuid4())

    def plan(run_id, steps):
        data = {
            "run_id": str(run_id),
            "primary": primary[0] + ":" + primary[1],
            "apps": apps,
            "steps": [
                {
                    "step": step,
                    "expected": authority_json(before),
                    "candidate": None if after is None else authority_json(after),
                }
                for step, before, after in steps
            ],
        }
        parse_plan(json.dumps(data).encode())  # The operator's own validation.
        return data

    activate = plan(
        run_ids[0],
        (
            ("prepare", expected, candidate),
            ("arm", candidate, None),
            ("initialize", candidate, None),
            ("ready", candidate, None),
        ),
    )
    retire = plan(run_ids[1], (("retire", ready, None),))
    return {
        "activate": activate,
        "retire": retire,
        "next_expected_authority": authority_json(ready),
        "summary": {
            "from_fingerprint": expected.policy_fingerprint,
            "to_fingerprint": target.fingerprint,
            "to_ledger_cap": target.cap,
            "from_incarnation": expected.incarnation,
            "to_incarnation": candidate.incarnation,
            "from_ledger_key": namespace_keys(expected)[0],
            "to_ledger_key": namespace_keys(candidate)[0],
            "configured_value": configured,
            "rollback": "rerun with --to default --expected-authority next-expected-authority.json",
            "mutation_permitted": False,
        },
    }


def _write_private(directory: Path, name: str, data: dict) -> None:
    fd = os.open(directory / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as out:
        json.dump(data, out, indent=2, sort_keys=True)
        out.write("\n")
        out.flush()
        os.fsync(out.fileno())


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--expected-authority", type=Path, required=True,
                        help="the current ready dnpl_authority row: exactly its eight fields as JSON")
    parser.add_argument("--primary", required=True, help="run_id:master_replid of the Redis primary")
    parser.add_argument("--apps", type=Path, required=True,
                        help="JSON {bainluck: {release, slug, commit}, bainluck-heavy: {...}}")
    parser.add_argument("--to", required=True, help="six sizes, e.g. 128,48,96,48,160,32, or 'default'")
    parser.add_argument("--configured", required=True,
                        help=f"exact {RESERVATIONS_ENV} read back from the app ('' when unset)")
    parser.add_argument("--out-dir", type=Path, required=True, help="new directory; must not exist")
    args = parser.parse_args(argv)
    try:
        expected = parse_authority(args.expected_authority.read_text())
        apps = json.loads(args.apps.read_text())
        if not isinstance(apps, dict) or set(apps) != set(APPS):
            raise RelimitRefused("exact app bindings required")
        result = build(expected, parse_primary(args.primary), apps,
                       parse_limits(args.to), args.configured)
        args.out_dir.mkdir(mode=0o700)
        _write_private(args.out_dir, "activate-plan.json", result["activate"])
        _write_private(args.out_dir, "retire-plan.json", result["retire"])
        _write_private(args.out_dir, "next-expected-authority.json", result["next_expected_authority"])
        _write_private(args.out_dir, "RELIMIT-SUMMARY.json", result["summary"])
    except Exception as exc:
        reason = str(exc) if isinstance(exc, RelimitRefused) else type(exc).__name__
        print(json.dumps({"status": "REFUSED", "reason": reason}))
        return 2
    print(json.dumps({"status": "PLANS_WRITTEN", **result["summary"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
