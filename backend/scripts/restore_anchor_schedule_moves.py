#!/usr/bin/env python3
"""Put back exactly the kickoffs one anchor-schedule apply moved.

    python3 scripts/restore_anchor_schedule_moves.py --identity <id>
    python3 scripts/restore_anchor_schedule_moves.py --identity <id> --apply

This is the "one-command restore" half of D51: the schedule repair may be
applied without Alex watching *because* every apply writes a dated record before
it moves a single row, and this command reads that record back. The identity is
printed by the apply itself, as ``undo_identity`` and as a ready-to-run
``undo_command``.

    --list   show the records on file, newest first, and exit

Dry-run by DEFAULT. Without ``--apply`` it prints the rows it would put back and
writes nothing — the same posture as the repair it reverses.

**It restores what the apply MOVED, not what it planned to move.** A planned
move whose row had changed under the run is reported ``stale``, writes nothing,
and is therefore not in the receipt. A record naming fewer rows than the plan is
normal, and the counts below say which is which.

**What it will decline to do.** A row whose kickoff is no longer the one this
rail wrote has been moved by something else since — ingest, a later apply, a
person. Dragging it back to a value that is now two edits old would make the
undo cause the corruption it exists to reverse, so it is reported
``CLOCK_MOVED_ON`` and left alone. A restore that reports some of these is
working, not failing.

Needs ``BAINLUCK_API``, ``ADMIN_TOKEN`` and — because the restore is a write —
``ADMIN_TOKEN_DESTRUCTIVE`` in the environment (``source ~/.claude/.env``).
Talks to the admin rail over HTTPS rather than to Postgres directly, because
5432 egress is blocked from the sandbox and because the write then goes through
the same gate as the apply.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

REPAIR_PATH = "/api/admin/events/reconcile-anchor-schedule"
LIST_PATH = "/api/admin/db-query"
TIMEOUT_S = 120

#: The identities the rail writes all start with this. Kept in sync with
#: ``UNDO_IDENTITY_PREFIX`` in app/tasks/reconcile_anchor_schedule.py; the guard
#: test asserts the two agree, so a rename cannot silently orphan --list.
UNDO_IDENTITY_PREFIX = "repair:anchor_schedule:undo"


def _env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        sys.exit(
            f"{name} is not set. Run `source ~/.claude/.env` in the SAME command "
            f"as this script."
        )
    return value.rstrip("/")


#: The destructive second token travels as a HEADER, never in the URL — a
#: secret in a query string leaks through logs and Referer (Queue #252).
DESTRUCTIVE_TOKEN_HEADER = "X-Admin-Destructive-Token"


def _post(
    url: str, token: str, body: dict | None = None, destructive: str | None = None
) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            **({"Content-Type": "application/json"} if data else {}),
            **({DESTRUCTIVE_TOKEN_HEADER: destructive} if destructive else {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()[:500]
        sys.exit(f"HTTP {exc.code} from {url.split('?')[0]}: {detail}")
    except urllib.error.URLError as exc:
        sys.exit(f"could not reach {url.split('?')[0]}: {exc.reason}")


def _list_records(api: str, token: str) -> int:
    """Show the records on file. A read, through db-query."""
    # `rows` is the RECEIPT (moved) and `rows_planned` the intent; both are
    # shown because a gap between them is normal (a stale row) and an operator
    # who sees only the smaller number will think rows went missing.
    sql = (
        "SELECT identity, generated_at, "
        "jsonb_array_length(payload->'rows') AS rows, "
        "jsonb_array_length(payload->'rows_planned') AS planned, "
        "payload->>'sport' AS sport, payload->>'receipt_complete' AS sealed "
        "FROM durable_state_snapshots "
        f"WHERE identity LIKE '{UNDO_IDENTITY_PREFIX}%' "
        "ORDER BY generated_at DESC"
    )
    got = _post(f"{api}{LIST_PATH}", token, {"sql": sql, "limit": 200})
    rows = got.get("rows") or []
    if not rows:
        print("No anchor-schedule undo records on file.")
        print(
            "That means no apply has run since this rail shipped — NOT that an "
            "earlier apply is unrecoverable in some other way."
        )
        return 0
    print(f"{len(rows)} record(s), newest first:\n")
    print("  the count is moves RESTORABLE (landed) / moves PLANNED\n")
    # db-query returns rows as ARRAYS, not dicts.
    for r in rows:
        identity, generated_at, n_rows = r[0], r[1], r[2]
        planned, sport, sealed = r[3], r[4], r[5]
        counts = f"{n_rows}/{planned if planned is not None else '?'}"
        flag = "" if str(sealed).lower() == "true" else "  [UNSEALED]"
        print(
            f"  {generated_at}  {counts:>9} move(s)  "
            f"{sport or 'all sports':<24} {identity}{flag}"
        )
    print("\nRestore one with:  --identity <identity> --apply")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Reverse one anchor-schedule apply.",
        epilog="Dry-run by default; pass --apply to write.",
    )
    ap.add_argument(
        "--identity", help="the record to restore (from the apply's undo_identity)"
    )
    ap.add_argument("--list", action="store_true", help="list records on file and exit")
    ap.add_argument("--apply", action="store_true", help="actually put the clocks back")
    ap.add_argument("--json", action="store_true", help="print the raw response")
    args = ap.parse_args()

    api, token = _env("BAINLUCK_API"), os.environ.get("ADMIN_TOKEN")
    if not token:
        sys.exit(
            "ADMIN_TOKEN is not set. Run `source ~/.claude/.env` in the SAME command."
        )

    if args.list:
        return _list_records(api, token)
    if not args.identity:
        ap.error("one of --identity or --list is required")

    params = {
        "undo_identity": args.identity,
        "apply": "true" if args.apply else "false",
    }
    destructive = None
    if args.apply:
        # The restore is a write and the endpoint gates writes on the
        # destructive check, not merely the read token. Said here rather than
        # left to a 403 an operator has to decode.
        destructive = os.environ.get("ADMIN_TOKEN_DESTRUCTIVE")
        if not destructive:
            sys.exit(
                "ADMIN_TOKEN_DESTRUCTIVE is not set, and --apply is a write. Run "
                "`source ~/.claude/.env` in the SAME command, or drop --apply to "
                "see the dry run."
            )

    got = _post(
        f"{api}{REPAIR_PATH}?{urllib.parse.urlencode(params)}",
        token,
        destructive=destructive,
    )
    result = got.get("result", got)

    if args.json:
        print(json.dumps(got, indent=2))
        return 0 if result.get("terminal") != "refused" else 1

    if result.get("terminal") == "refused":
        print(f"REFUSED: {', '.join(result.get('reason_codes') or ['unknown'])}")
        print(result.get("reason", ""))
        return 1

    if not args.apply:
        planned = result.get("rows_planned_in_record")
        print(f"DRY RUN — nothing written. Record {args.identity}")
        print(f"  taken at    : {result.get('taken_at')}")
        print(f"  would revert: {result.get('rows_in_record')} move(s) — moves that")
        print("                apply actually landed, the only list replayed")
        if planned is not None:
            print(f"  that apply planned: {planned} move(s)")
        if result.get("receipt_complete") is False:
            print("  [UNSEALED] that apply did not seal its receipt — see the note")
        print()
        for row in result.get("rows") or []:
            before = (row.get("before") or {}).get("commence_time")
            after = (row.get("after") or {}).get("commence_time")
            print(
                f"    event {row.get('event_id')}  {after} -> {before}"
                f"   {row.get('matchup') or ''}"
            )
        print(f"\n{result.get('reason', '')}")
        print("\nRe-run with --apply to put these back.")
        return 0

    print(f"REVERTED {result.get('reverted')} of {result.get('rows_in_record')} move(s).")
    for row in result.get("moved_on") or []:
        print(
            f"  left alone: event {row.get('event_id')} no longer wears the clock this "
            f"rail wrote (CLOCK_MOVED_ON) — something moved it since, and it was "
            f"not dragged back"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
