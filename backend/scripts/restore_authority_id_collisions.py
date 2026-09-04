#!/usr/bin/env python3
"""Put back exactly the ESPN ids one authority-id-collisions apply cleared.

    python3 scripts/restore_authority_id_collisions.py --identity <id>
    python3 scripts/restore_authority_id_collisions.py --identity <id> --apply

This is the "one-command restore" half of D51: the drain may be applied without
Alex watching *because* every apply writes a dated undo record before it writes
anything else, and this command reads that record back. The identity is printed
by the apply itself, as ``undo_identity`` and as a ready-to-run ``undo_command``.

    --list   show the undo records on file, newest first, and exit

Dry-run by DEFAULT. Without ``--apply`` it prints the rows it would restamp and
writes nothing — the same posture as the repair it reverses.

**What a restore does to the census, stated up front.** Putting ids back
re-creates the collisions the apply removed. That is what an undo is. The
``uq_event_espn_id`` pre-check will RISE by the number restored, and it is
supposed to.

**What it will decline to do.** A row that `espn_sync` has re-anchored since the
apply wears a current, correct id. Overwriting that with yesterday's value would
make the undo cause the corruption it exists to reverse, so such a row is
reported ``ESPN_ID_REOCCUPIED`` and left alone. A restore that reports some of
these is working, not failing.

**It restores what the apply CLEARED, not what it planned to clear** (CERT-846).
An apply reports ``ESPN_ID_MOVED`` for a planned row whose id changed between the
review and the run; it wrote nothing to that row, so its id is not put back. A
record therefore often names fewer rows than the plan did, and the counts printed
below say which is which. Restoring a row the apply never touched would re-create
a collision somebody else had just resolved.

Needs ``BAINLUCK_API`` and ``ADMIN_TOKEN`` in the environment
(``source ~/.claude/.env``). Talks to the admin rail over HTTPS rather than to
Postgres directly, because 5432 egress is blocked from the sandbox and because
the write then goes through the same ``_check_admin_secret`` gate as the apply.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

REPAIR_PATH = "/api/admin/repairs/authority-id-collisions"
LIST_PATH = "/api/admin/db-query"
TIMEOUT_S = 120

#: The undo identities the rail writes all start with this. Kept in sync with
#: ``UNDO_IDENTITY_PREFIX`` in app/tasks/repair_authority_id_collisions.py; the
#: guard test asserts the two agree, so a rename cannot silently orphan --list.
UNDO_IDENTITY_PREFIX = "repair:authority_id_collisions:undo"


def _env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        sys.exit(
            f"{name} is not set. Run `source ~/.claude/.env` in the SAME command "
            f"as this script."
        )
    return value.rstrip("/")


def _post(url: str, token: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            **({"Content-Type": "application/json"} if data else {}),
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
    """Show the undo records on file. A read, through db-query."""
    # `rows` is the RECEIPT (cleared) and `rows_planned` the intent; both are
    # shown because a gap between them is normal (ESPN_ID_MOVED) and an operator
    # who sees only the smaller number will think rows went missing.
    sql = (
        "SELECT identity, generated_at, "
        "jsonb_array_length(payload->'rows') AS rows, payload->>'sport' AS sport, "
        "jsonb_array_length(payload->'rows_planned') AS planned, "
        "payload->>'receipt_complete' AS sealed "
        "FROM durable_state_snapshots "
        f"WHERE identity LIKE '{UNDO_IDENTITY_PREFIX}%' "
        "ORDER BY generated_at DESC"
    )
    got = _post(f"{api}{LIST_PATH}", token, {"sql": sql, "limit": 200})
    rows = got.get("rows") or []
    if not rows:
        print("No undo records on file.")
        print(
            "That means no apply has run since this rail shipped — NOT that an "
            "earlier apply is unrecoverable in some other way."
        )
        return 0
    print(f"{len(rows)} undo record(s), newest first:\n")
    print("  the count is rows RESTORABLE (cleared) / rows PLANNED\n")
    # db-query returns rows as ARRAYS, not dicts.
    for r in rows:
        identity, generated_at, n_rows, sport = r[0], r[1], r[2], r[3]
        planned, sealed = (r[4] if len(r) > 4 else None), (r[5] if len(r) > 5 else None)
        counts = f"{n_rows}/{planned if planned is not None else '?'}"
        # `sealed` is the JSON text of receipt_complete: "false" means that apply
        # stopped part-way and may have cleared one row more than it receipted.
        flag = "" if str(sealed).lower() == "true" else "  [UNSEALED]"
        print(
            f"  {generated_at}  {counts:>9} row(s)  "
            f"{sport or 'all sports':<24} {identity}{flag}"
        )
    print("\nRestore one with:  --identity <identity> --apply")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Reverse one authority-id-collisions apply.",
        epilog="Dry-run by default; pass --apply to write.",
    )
    ap.add_argument(
        "--identity", help="the undo record to restore (from the apply's undo_identity)"
    )
    ap.add_argument(
        "--list", action="store_true", help="list undo records on file and exit"
    )
    ap.add_argument("--apply", action="store_true", help="actually put the ids back")
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

    params = urllib.parse.urlencode(
        {"undo_identity": args.identity, "apply": "true" if args.apply else "false"}
    )
    got = _post(f"{api}{REPAIR_PATH}?{params}", token)
    result = got.get("result", got)

    if args.json:
        print(json.dumps(got, indent=2))
        return 0 if not result.get("refused") else 1

    if result.get("refused"):
        print(f"REFUSED: {', '.join(result.get('reason_codes') or ['unknown'])}")
        print(result.get("note", ""))
        return 1

    if not args.apply:
        planned = result.get("rows_planned_in_record")
        print(f"DRY RUN — nothing written. Record {args.identity}")
        print(f"  planned by  : {result.get('plan_hash')}")
        print(f"  taken at    : {result.get('taken_at')}")
        print(f"  would restore: {result.get('rows_in_record')} row(s) — rows that apply")
        print("                 actually cleared, which is the only list replayed")
        if planned is not None:
            print(f"  that apply planned: {planned} row(s)")
        if result.get("receipt_complete") is False:
            print("  [UNSEALED] that apply stopped part-way — see the note below")
        print()
        for row in result.get("rows") or []:
            print(
                f"    event {row.get('event_id')}  <- espn_id {row.get('prior_espn_id')}"
                f"   {row.get('matchup') or ''}"
            )
        print(f"\n{result.get('note', '')}")
        print("\nRe-run with --apply to put these back.")
        return 0

    before, after = result.get("before") or {}, result.get("after") or {}
    print(
        f"RESTORED {result.get('restamped')} of {result.get('rows_in_record')} row(s)."
    )
    print(
        f"  contested ids {before.get('contested_ids')} -> {after.get('contested_ids')}"
        f"   (a restore RAISES this on purpose)"
    )
    for row in result.get("reoccupied") or []:
        print(
            f"  left alone: event {row.get('event_id')} has been re-anchored since "
            f"the apply (ESPN_ID_REOCCUPIED) — its current id was not overwritten"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
