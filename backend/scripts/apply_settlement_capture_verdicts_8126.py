"""#8126 — write the per-leg verdicts protocol-2 settlement captures banked into futures_outcomes.

THE SHIP: a settled Kalshi board whose venue declared each leg stops showing a
blank result, because ``futures_outcomes.is_winner`` carries what the capture read.

Every decision is made by :mod:`app.utils.settlement_capture_consumer` (pure,
unit-tested); this script only reads its inputs and executes its plan. Read that
module's docstring for what licenses a write. In one line: only a leg the venue
itself declared ``settled`` with a bool verdict, joined by exact ticker to an
outcome of the capture's own Kalshi market, written only where the result is
still blank (``resolution_source IS NULL``).

SELECTION — always bounded
--------------------------

* ``--capture-id N`` (repeatable, at most 500): exactly those captures, whatever
  they are — a v1 or malformed capture is read and REFUSED visibly.
* otherwise the newest Kalshi captures carrying ``_derived`` since ``--since``
  (default 3 days ago), at most ``--limit`` (default 50, max 500).

Every other ``_derived`` capture of the same markets is read too, so a re-probe
that disagrees is seen and fails closed instead of being outvoted by omission.

THE WRITE, THE BACKUP AND THE UNDO
----------------------------------

Default is a dry run: the plan and its tallies, nothing written. ``--apply``, in
ONE transaction:

1. ``SET LOCAL lock_timeout`` so a busy row refuses the run instead of wedging it;
2. locks the planned outcome rows ``FOR UPDATE`` (id order) and refuses the whole
   run if any no longer reads the planned pre-image;
3. banks the pre-image FROM THE LOCKED ROWS into ``backup_8126_capture_verdicts``
   under a fresh ``run_id`` and refuses unless the bank holds every planned row
   in exactly that state;
4. writes ``is_winner`` + ``resolution_source='api_settlement'``, each row
   compare-and-swapped on ``resolution_source IS NULL`` and its pre-image
   ``is_winner``; a short rowcount rolls everything back;
5. commits, then reads the rows back from disk.

``CREATE TABLE IF NOT EXISTS`` is runtime DDL behind a person's invocation on a
named app — notice 47(c), not migration-class.

    heroku run:detached -a bainluck -- python3 scripts/apply_settlement_capture_verdicts_8126.py --capture-id 107429            # dry run
    heroku run:detached -a bainluck -- python3 scripts/apply_settlement_capture_verdicts_8126.py --capture-id 107429 --apply    # backup + write
    heroku run:detached -a bainluck -- python3 scripts/restore_settlement_capture_verdicts_8126.py --run-id <RUN_ID> --apply     # undo

Refuses unless ``HEROKU_APP_NAME`` is ``bainluck`` or ``bainluck-heavy``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from app.utils.settlement_capture_consumer import (  # noqa: E402
    KALSHI,
    REPAIR_BACKUP_TABLE,
    WRITE_RESOLUTION_SOURCE,
    CaptureRow,
    LegWrite,
    OutcomeRow,
    plan_writes,
)

PRODUCTION_APPS = frozenset({"bainluck", "bainluck-heavy"})

DEFAULT_WINDOW_DAYS = 3
DEFAULT_LIMIT = 50
MAX_CAPTURES = 500
#: A run planning more writes than this refuses; lower ``--limit``. Bounds the
#: transaction and the row locks it holds.
DEFAULT_MAX_WRITES = 5_000
LOCK_TIMEOUT = "5s"


class Refused(RuntimeError):
    """The run stops; nothing is written."""


def refuse_unless_production(env: dict) -> None:
    app = env.get("HEROKU_APP_NAME", "")
    if app not in PRODUCTION_APPS:
        raise Refused(
            f"HEROKU_APP_NAME={app!r} is not a production app "
            f"({sorted(PRODUCTION_APPS)}); refusing"
        )


def new_run_id(now: datetime) -> str:
    return f"8126-{now.astimezone(timezone.utc):%Y%m%dT%H%M%S%fZ}"


def _derived(value: Any) -> Any:
    # A driver without a JSONB codec hands back text; parse it, never guess.
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


_CAPTURE_COLS = (
    "id, market_id, source, protocol_version, disposition, winning_outcome, "
    "raw_response->'_derived' AS derived, captured_at"
)


def _capture(r: Any) -> CaptureRow:
    return CaptureRow(
        id=int(r.id),
        market_id=int(r.market_id),
        source=r.source,
        protocol_version=r.protocol_version,
        disposition=r.disposition,
        winning_outcome=r.winning_outcome,
        derived=_derived(r.derived),
        captured_at=r.captured_at,
    )


async def select_captures(
    session,
    *,
    capture_ids: list[int] | None,
    since: datetime | None,
    limit: int,
) -> tuple[list[CaptureRow], list[int]]:
    """Return ``(captures, missing_ids)``. Bounded in both modes."""
    if capture_ids:
        ids = sorted(set(int(i) for i in capture_ids))
        if len(ids) > MAX_CAPTURES:
            raise Refused(f"{len(ids)} capture ids > {MAX_CAPTURES}; refusing")
        rows = await session.execute(
            text(f"SELECT {_CAPTURE_COLS} FROM settlement_captures WHERE id = ANY(:ids)"),
            {"ids": ids},
        )
        got = [_capture(r) for r in rows]
        found = {c.id for c in got}
        return got, [i for i in ids if i not in found]
    if not 1 <= limit <= MAX_CAPTURES:
        raise Refused(f"--limit {limit} outside 1..{MAX_CAPTURES}; refusing")
    rows = await session.execute(
        text(
            f"SELECT {_CAPTURE_COLS} FROM settlement_captures "
            "WHERE source = :src AND captured_at >= :since "
            "AND raw_response->'_derived' IS NOT NULL "
            "ORDER BY captured_at DESC, id DESC LIMIT :lim"
        ),
        {"src": KALSHI, "since": since, "lim": limit},
    )
    return [_capture(r) for r in rows], []


async def load_history(session, market_ids: list[int], exclude: list[int]) -> list[CaptureRow]:
    """Every other ``_derived`` capture of these markets — the re-probe evidence."""
    if not market_ids:
        return []
    rows = await session.execute(
        text(
            f"SELECT {_CAPTURE_COLS} FROM settlement_captures "
            "WHERE market_id = ANY(:mids) AND raw_response->'_derived' IS NOT NULL "
            "AND NOT (id = ANY(:ex))"
        ),
        {"mids": market_ids, "ex": exclude or [0]},
    )
    return [_capture(r) for r in rows]


async def load_outcomes(session, market_ids: list[int]) -> list[OutcomeRow]:
    if not market_ids:
        return []
    rows = await session.execute(
        text(
            "SELECT o.id, o.market_id, o.external_id, o.is_winner, o.resolution_source, "
            "m.source AS market_source FROM futures_outcomes o "
            "JOIN futures_markets m ON m.id = o.market_id WHERE o.market_id = ANY(:mids)"
        ),
        {"mids": market_ids},
    )
    return [
        OutcomeRow(
            id=int(r.id),
            market_id=int(r.market_id),
            external_id=r.external_id,
            is_winner=r.is_winner,
            resolution_source=r.resolution_source,
            market_source=r.market_source,
        )
        for r in rows
    ]


_BACKUP_DDL = (
    f"CREATE TABLE IF NOT EXISTS {REPAIR_BACKUP_TABLE} ("
    " run_id text NOT NULL,"
    " outcome_id bigint NOT NULL,"
    " market_id bigint NOT NULL,"
    " capture_id bigint NOT NULL,"
    " external_id text NOT NULL,"
    " pre_is_winner boolean,"
    " pre_resolution_source text,"
    " post_is_winner boolean NOT NULL,"
    " post_resolution_source text NOT NULL,"
    " taken_at timestamptz NOT NULL DEFAULT now(),"
    " restored_at timestamptz,"
    " PRIMARY KEY (run_id, outcome_id))"
)

_PLAN_UNNEST = (
    "unnest(CAST(:ids AS bigint[]), CAST(:caps AS bigint[]), "
    "CAST(:posts AS boolean[]), CAST(:pres AS boolean[])) "
    "AS p(outcome_id, capture_id, post_is_winner, pre_is_winner)"
)


def _arrays(writes: list[LegWrite]) -> dict[str, list]:
    return {
        "ids": [w.outcome_id for w in writes],
        "caps": [w.capture_id for w in writes],
        "posts": [w.new_is_winner for w in writes],
        "pres": [w.pre_is_winner for w in writes],
    }


async def _lock_and_verify(session, writes: list[LegWrite]) -> None:
    rows = await session.execute(
        text(
            "SELECT id, market_id, external_id, is_winner, resolution_source "
            "FROM futures_outcomes WHERE id = ANY(:ids) ORDER BY id FOR UPDATE"
        ),
        {"ids": [w.outcome_id for w in writes]},
    )
    locked = {int(r.id): r for r in rows}
    for w in writes:
        r = locked.get(w.outcome_id)
        state = (
            None
            if r is None
            else (int(r.market_id), r.external_id, r.is_winner, r.resolution_source)
        )
        want = (w.market_id, w.external_id, w.pre_is_winner, w.pre_resolution_source)
        if state != want:
            raise Refused(
                f"outcome {w.outcome_id} reads {state} under lock, planned {want}; "
                "rolled back, nothing written"
            )


async def _bank(session, run_id: str, writes: list[LegWrite]) -> None:
    await session.execute(text(_BACKUP_DDL))
    await session.execute(
        text(
            f"INSERT INTO {REPAIR_BACKUP_TABLE} (run_id, outcome_id, market_id, capture_id, "
            "external_id, pre_is_winner, pre_resolution_source, post_is_winner, "
            "post_resolution_source) "
            f"SELECT :run_id, o.id, o.market_id, p.capture_id, o.external_id, o.is_winner, "
            f"o.resolution_source, p.post_is_winner, :post_src "
            f"FROM futures_outcomes o JOIN {_PLAN_UNNEST} ON p.outcome_id = o.id"
        ),
        {"run_id": run_id, "post_src": WRITE_RESOLUTION_SOURCE, **_arrays(writes)},
    )
    banked = await session.execute(
        text(
            f"SELECT outcome_id, market_id, capture_id, external_id, pre_is_winner, "
            f"pre_resolution_source, post_is_winner, post_resolution_source "
            f"FROM {REPAIR_BACKUP_TABLE} WHERE run_id = :run_id"
        ),
        {"run_id": run_id},
    )
    got = {
        int(r.outcome_id): (
            int(r.market_id),
            int(r.capture_id),
            r.external_id,
            r.pre_is_winner,
            r.pre_resolution_source,
            r.post_is_winner,
            r.post_resolution_source,
        )
        for r in banked
    }
    want = {
        w.outcome_id: (
            w.market_id,
            w.capture_id,
            w.external_id,
            w.pre_is_winner,
            w.pre_resolution_source,
            w.new_is_winner,
            w.new_resolution_source,
        )
        for w in writes
    }
    if got != want:
        raise Refused(
            f"backup for {run_id} holds {len(got)} rows, {len(want)} planned, or a "
            "different pre-image; rolled back, nothing written"
        )


async def _write(session, writes: list[LegWrite]) -> int:
    result = await session.execute(
        text(
            "UPDATE futures_outcomes o SET is_winner = p.post_is_winner, "
            "resolution_source = :post_src "
            f"FROM {_PLAN_UNNEST} "
            "WHERE o.id = p.outcome_id AND o.resolution_source IS NULL "
            "AND o.is_winner IS NOT DISTINCT FROM p.pre_is_winner"
        ),
        {"post_src": WRITE_RESOLUTION_SOURCE, **_arrays(writes)},
    )
    return int(result.rowcount)


def _summary(plan, *, sample: int = 25) -> dict[str, Any]:
    return {
        "tallies": plan.tallies(),
        "refused": {str(k): f"{plan.refused[k]}: {plan.refused_detail[k]}" for k in sorted(plan.refused)},
        "skipped_sample": {k: v[:sample] for k, v in sorted(plan.skipped.items())},
        "writes_sample": [
            {
                "outcome_id": w.outcome_id,
                "market_id": w.market_id,
                "external_id": w.external_id,
                "capture_id": w.capture_id,
                "pre": [w.pre_is_winner, w.pre_resolution_source],
                "post": [w.new_is_winner, w.new_resolution_source],
            }
            for w in plan.writes[:sample]
        ],
    }


async def run(
    session,
    *,
    capture_ids: list[int] | None = None,
    since: datetime | None = None,
    limit: int = DEFAULT_LIMIT,
    apply: bool = False,
    run_id: str | None = None,
    max_writes: int = DEFAULT_MAX_WRITES,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    if since is None:
        since = now - timedelta(days=DEFAULT_WINDOW_DAYS)
    if apply:
        await session.execute(text(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'"))

    selected, missing = await select_captures(
        session, capture_ids=capture_ids, since=since, limit=limit
    )
    market_ids = sorted({c.market_id for c in selected})
    history = await load_history(session, market_ids, [c.id for c in selected])
    outcomes = await load_outcomes(session, market_ids)
    plan = plan_writes([*selected, *history], outcomes)

    out: dict[str, Any] = {
        "mode": "apply" if apply else "dry-run",
        "selected_captures": len(selected),
        "history_captures": len(history),
        "missing_capture_ids": missing,
        "markets": len(market_ids),
        **_summary(plan),
    }
    if len(plan.writes) > max_writes:
        raise Refused(
            f"{len(plan.writes)} planned writes > --max-writes {max_writes}; lower --limit"
        )
    if not apply or not plan.writes:
        out["written"] = 0
        return out

    run_id = run_id or new_run_id(now)
    await _lock_and_verify(session, plan.writes)
    await _bank(session, run_id, plan.writes)
    written = await _write(session, plan.writes)
    if written != len(plan.writes):
        await session.rollback()
        raise Refused(
            f"wrote {written} of {len(plan.writes)} under compare-and-swap; "
            "rolled back, nothing written"
        )
    await session.commit()

    # Read back from disk rather than trusting rowcount (gotcha #53).
    rows = await session.execute(
        text(
            "SELECT id, is_winner, resolution_source FROM futures_outcomes "
            "WHERE id = ANY(:ids)"
        ),
        {"ids": [w.outcome_id for w in plan.writes]},
    )
    now_state = {int(r.id): (r.is_winner, r.resolution_source) for r in rows}
    out["run_id"] = run_id
    out["written"] = written
    out["read_back_matches"] = sum(
        1
        for w in plan.writes
        if now_state.get(w.outcome_id) == (w.new_is_winner, w.new_resolution_source)
    )
    return out


def _parse_since(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise argparse.ArgumentTypeError("--since needs a timezone (e.g. 2026-09-28T00:00Z)")
    return dt


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--capture-id", type=int, action="append", dest="capture_ids")
    ap.add_argument("--since", type=_parse_since)
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    ap.add_argument("--max-writes", type=int, default=DEFAULT_MAX_WRITES)
    ap.add_argument("--apply", action="store_true")
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
                capture_ids=args.capture_ids,
                since=args.since,
                limit=args.limit,
                apply=args.apply,
                max_writes=args.max_writes,
            )
        except Refused as exc:
            await session.rollback()
            print(f"REFUSED: {exc}")
            return 2
    print(json.dumps(out, indent=2, default=str, ensure_ascii=False))
    if out.get("run_id"):
        app = os.environ.get("HEROKU_APP_NAME", "bainluck")
        print(
            f"UNDO: heroku run:detached -a {app} -- python3 "
            f"scripts/restore_settlement_capture_verdicts_8126.py --run-id {out['run_id']} --apply"
        )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
