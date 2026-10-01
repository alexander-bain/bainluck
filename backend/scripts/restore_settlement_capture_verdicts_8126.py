"""#8126 — undo one apply run of the capture-verdict consumer, from its own backup.

Reads ``backup_8126_capture_verdicts`` for ``--run-id`` and writes each banked
pre-image (``is_winner``, ``resolution_source``) back — but ONLY onto a row that
still reads exactly the post-image that run wrote, on the SAME leg it wrote it to
(the banked ``market_id`` and ``external_id``). A row anything else has moved
since — its grade, its market or its ticker — is DRIFT: a change this undo must
not destroy, and a repointed row's pre-image belongs to a leg it no longer is.

* Default is a dry run: what would be restored and what has drifted.
* ``--apply`` with any drift REFUSES the whole restore; nothing is written.
* ``--apply --restore-undrifted`` restores the rows still at the post-image,
  leaves every drifted row exactly as it is, and leaves those backup rows open
  (``restored_at`` NULL) so a later decision can still reach them.
* A row already back at its pre-image, on the same leg, is counted and closed,
  not rewritten.

One transaction: rows locked ``FOR UPDATE`` in id order, each UPDATE
compare-and-swapped on the banked identity and the post-image, a short rowcount rolls everything back.
A run already fully restored is a no-op; an unknown run refuses.

    heroku run:detached -a bainluck -- python3 scripts/restore_settlement_capture_verdicts_8126.py --run-id <RUN_ID>          # dry run
    heroku run:detached -a bainluck -- python3 scripts/restore_settlement_capture_verdicts_8126.py --run-id <RUN_ID> --apply  # undo

Refuses unless ``HEROKU_APP_NAME`` is ``bainluck`` or ``bainluck-heavy``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from app.utils.settlement_capture_consumer import REPAIR_BACKUP_TABLE  # noqa: E402

PRODUCTION_APPS = frozenset({"bainluck", "bainluck-heavy"})
LOCK_TIMEOUT = "5s"


class Refused(RuntimeError):
    """The restore stops; nothing is written."""


def refuse_unless_production(env: dict) -> None:
    app = env.get("HEROKU_APP_NAME", "")
    if app not in PRODUCTION_APPS:
        raise Refused(
            f"HEROKU_APP_NAME={app!r} is not a production app "
            f"({sorted(PRODUCTION_APPS)}); refusing"
        )


Grade = tuple[bool | None, str | None]
Identity = tuple[int, str]


@dataclass(frozen=True)
class Banked:
    outcome_id: int
    identity: Identity  # (market_id, external_id) the run wrote to
    pre: Grade
    post: Grade


def classify(
    banked: list[Banked], current: dict[int, tuple[Identity, Grade]]
) -> tuple[list[Banked], list[Banked], list[tuple[Banked, Any]]]:
    """Split banked rows into ``(restorable, already_pre, drifted)``. Pure.

    ``current`` maps outcome id -> ``((market_id, external_id), (is_winner,
    resolution_source))``. An id absent from it is a deleted row, and a row
    whose market or ticker is not the banked one is a different leg — both are
    drift, whatever its grade reads.
    """
    restorable: list[Banked] = []
    already: list[Banked] = []
    drifted: list[tuple[Banked, Any]] = []
    for b in banked:
        now = current.get(b.outcome_id)
        if now is None or now[0] != b.identity:
            drifted.append((b, now))
        elif now[1] == b.post:
            restorable.append(b)
        elif now[1] == b.pre:
            already.append(b)
        else:
            drifted.append((b, now))
    return restorable, already, drifted


async def run(
    session, *, run_id: str, apply: bool = False, restore_undrifted: bool = False
) -> dict[str, Any]:
    exists = await session.execute(
        text("SELECT to_regclass(:t) IS NOT NULL"), {"t": REPAIR_BACKUP_TABLE}
    )
    if not exists.scalar():
        raise Refused(f"{REPAIR_BACKUP_TABLE} does not exist; nothing was ever banked")
    if apply:
        await session.execute(text(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'"))

    total = await session.execute(
        text(f"SELECT count(*) FROM {REPAIR_BACKUP_TABLE} WHERE run_id = :r"), {"r": run_id}
    )
    if not total.scalar():
        raise Refused(f"no backup rows for run_id={run_id!r}; refusing")

    rows = await session.execute(
        text(
            f"SELECT outcome_id, market_id, external_id, pre_is_winner, pre_resolution_source, "
            f"post_is_winner, post_resolution_source FROM {REPAIR_BACKUP_TABLE} "
            "WHERE run_id = :r AND restored_at IS NULL ORDER BY outcome_id"
        ),
        {"r": run_id},
    )
    banked = [
        Banked(
            int(r.outcome_id),
            (int(r.market_id), r.external_id),
            (r.pre_is_winner, r.pre_resolution_source),
            (r.post_is_winner, r.post_resolution_source),
        )
        for r in rows
    ]
    out: dict[str, Any] = {
        "mode": "restore" if apply else "dry-run",
        "run_id": run_id,
        "open_backup_rows": len(banked),
    }
    if not banked:
        out.update(restored=0, already_pre=0, drifted=[], note="run already fully restored")
        return out

    lock = " FOR UPDATE" if apply else ""
    cur = await session.execute(
        text(
            "SELECT id, market_id, external_id, is_winner, resolution_source "
            f"FROM futures_outcomes WHERE id = ANY(:ids) ORDER BY id{lock}"
        ),
        {"ids": [b.outcome_id for b in banked]},
    )
    current = {
        int(r.id): ((int(r.market_id), r.external_id), (r.is_winner, r.resolution_source))
        for r in cur
    }
    restorable, already, drifted = classify(banked, current)
    out["restorable"] = len(restorable)
    out["already_pre"] = len(already)
    out["drifted"] = [
        {
            "outcome_id": b.outcome_id,
            "post": [*b.identity, *b.post],
            "now": None if n is None else [*n[0], *n[1]],
        }
        for b, n in drifted
    ]

    if not apply:
        out["restored"] = 0
        return out
    if drifted and not restore_undrifted:
        raise Refused(
            f"{len(drifted)} row(s) drifted since run {run_id} "
            f"(first: {out['drifted'][:3]}); nothing written. Re-run with "
            "--restore-undrifted to restore the rest and leave those as they are"
        )

    restored = 0
    if restorable:
        result = await session.execute(
            text(
                "UPDATE futures_outcomes o SET is_winner = b.pre_is_winner, "
                "resolution_source = b.pre_resolution_source "
                f"FROM {REPAIR_BACKUP_TABLE} b "
                "WHERE b.run_id = :r AND b.outcome_id = o.id AND b.restored_at IS NULL "
                "AND o.id = ANY(:ids) "
                "AND o.market_id = b.market_id "
                "AND o.external_id IS NOT DISTINCT FROM b.external_id "
                "AND o.is_winner IS NOT DISTINCT FROM b.post_is_winner "
                "AND o.resolution_source IS NOT DISTINCT FROM b.post_resolution_source"
            ),
            {"r": run_id, "ids": [b.outcome_id for b in restorable]},
        )
        restored = int(result.rowcount)
        if restored != len(restorable):
            await session.rollback()
            raise Refused(
                f"restored {restored} of {len(restorable)} under compare-and-swap; "
                "rolled back, nothing written"
            )
    closed = [b.outcome_id for b in (*restorable, *already)]
    if closed:
        await session.execute(
            text(
                f"UPDATE {REPAIR_BACKUP_TABLE} SET restored_at = now() "
                "WHERE run_id = :r AND outcome_id = ANY(:ids) AND restored_at IS NULL"
            ),
            {"r": run_id, "ids": closed},
        )
    await session.commit()
    out["restored"] = restored
    return out


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--restore-undrifted", action="store_true")
    args = ap.parse_args()

    try:
        refuse_unless_production(dict(os.environ))
    except Refused as exc:
        print(f"REFUSED: {exc}")
        return 2

    from app.tasks.base import get_task_session

    async with get_task_session() as session:
        try:
            out = await run(
                session,
                run_id=args.run_id,
                apply=args.apply,
                restore_undrifted=args.restore_undrifted,
            )
        except Refused as exc:
            await session.rollback()
            print(f"REFUSED: {exc}")
            return 2
    print(json.dumps(out, indent=2, default=str, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
