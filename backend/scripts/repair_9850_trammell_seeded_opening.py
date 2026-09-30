"""#9850 — withdraw the seeded 47% opening on Taylor Trammell's 1+ home runs (market 63386735).

THE SHIP: "The script" on /events/15321836 (White Sox @ Astros, WC Game 2) stops
leading with "Trammell's 1+ home runs opened at 47% — it's 5% now", a move nobody
made.

WHY (read from production 2026-09-30 14:5xZ)
--------------------------------------------

The listing snapshot, 06:16:11Z, holds price 0.475 / 0.525 beside a 0.01 / 0.99
book with no trade. The decomposed sub-market writer took the 1c bid as trading
and stamped Gamma's untraded price as the opening on both legs:

    outcome 238837724  Over   opening 0.475000  +111  2026-09-30 06:16:11.708357Z  source NULL
    outcome 238837725  Under  opening 0.525000  -111  2026-09-30 06:16:11.708357Z  source NULL

The Script reads ``_resolve_pregame_mark`` (``routes/events.py``), which falls
back to ``opening_probability`` until a pregame commence pin exists, so the 0.475
is the page's first line. PR #9852 stops the writer stamping this shape; its
COALESCE upserts cannot remove a value already stored, so this row needs its own
repair (CERT-3877's required repair ``9850-EXISTING-OPENING-REPAIR``).

WHAT IS WRITTEN
---------------

Both legs, one transaction: ``opening_probability``, ``opening_american_odds``
and ``opening_captured_at`` -> NULL. Nothing else moves: current price, book and
snapshots stay. With no opening, The script's mark is NULL and the frontend drops
the prop (``no_real_price``) instead of printing a travel nobody made.

The run acts only when the market still reads as pinned (Polymarket, this name,
this event) and BOTH legs are exactly in the BEFORE state; both exactly AFTER is a
no-op; anything else refuses the whole run and prints what it found. Either leg
carrying a grade (``is_winner``) or a ``calibration_probability`` also refuses:
the repair is only this small while no published number depends on the opening.
Every UPDATE compare-and-swaps on the full state it expects.

THE BACKUP AND THE UNDO
-----------------------

``--apply`` first banks both legs' BEFORE opening columns in
``backup_9850_opening`` and refuses to write if the bank is short or holds any
other state. ``--restore`` writes the pinned BEFORE values back, only while both
legs are exactly AFTER. ``CREATE TABLE IF NOT EXISTS`` is runtime DDL behind a
person's invocation on a named app: notice 47(c), not migration-class.

    heroku run:detached -a bainluck -- python3 scripts/repair_9850_trammell_seeded_opening.py            # dry run
    heroku run:detached -a bainluck -- python3 scripts/repair_9850_trammell_seeded_opening.py --apply    # backup + clear
    heroku run:detached -a bainluck -- python3 scripts/repair_9850_trammell_seeded_opening.py --restore  # undo

Refuses unless ``HEROKU_APP_NAME`` is ``bainluck`` or ``bainluck-heavy``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

PRODUCTION_APPS = frozenset({"bainluck", "bainluck-heavy"})

BACKUP_TABLE = "backup_9850_opening"

MARKET_ID = 63386735
#: (source, name, event_id) — identity the ids alone cannot vouch for.
PINNED_MARKET = ("polymarket", "Taylor Trammell: Home Runs O/U 0.5", 15321836)

OVER = 238837724
UNDER = 238837725

_LISTED_AT = datetime(2026, 9, 30, 6, 16, 11, 708357, tzinfo=timezone.utc)

#: outcome id -> (name, opening_probability, opening_american_odds, opening_captured_at)
BEFORE: dict[int, tuple[str, Decimal | None, int | None, datetime | None]] = {
    OVER: ("Over", Decimal("0.475000"), 111, _LISTED_AT),
    UNDER: ("Under", Decimal("0.525000"), -111, _LISTED_AT),
}
AFTER: dict[int, tuple[str, None, None, None]] = {
    OVER: ("Over", None, None, None),
    UNDER: ("Under", None, None, None),
}


class Refused(RuntimeError):
    """The run stops before any write."""


def refuse_unless_production(env: dict) -> None:
    app = env.get("HEROKU_APP_NAME", "")
    if app not in PRODUCTION_APPS:
        raise Refused(
            f"HEROKU_APP_NAME={app!r} is not a production app "
            f"({sorted(PRODUCTION_APPS)}); refusing"
        )


def _state(row: tuple) -> tuple:
    """(name, opening_probability, opening_american_odds, opening_captured_at), normalised."""
    name, prob, odds, at = row[:4]
    return (
        name,
        None if prob is None else Decimal(str(prob)).quantize(Decimal("0.000001")),
        None if odds is None else int(odds),
        at,
    )


def plan(
    market: tuple | None,
    legs: dict[int, tuple],
    *,
    restore: bool,
) -> list[tuple[int, tuple, tuple]]:
    """Return ``[(outcome_id, from_state, to_state), ...]``. Pure, so the unit file drives it.

    ``market`` is ``(source, name, event_id)`` or None when the row is gone.
    ``legs`` maps each outcome id of the market to
    ``(name, opening_probability, opening_american_odds, opening_captured_at,
    opening_source, is_winner, calibration_probability)``.
    """
    if market is None:
        raise Refused(f"market {MARKET_ID} missing; refusing")
    if tuple(market) != PINNED_MARKET:
        raise Refused(f"market {MARKET_ID} reads {tuple(market)}, pinned {PINNED_MARKET}; refusing")
    if set(legs) != set(BEFORE):
        raise Refused(
            f"market {MARKET_ID} holds outcomes {sorted(legs)}, pinned {sorted(BEFORE)}; refusing"
        )
    for oid, row in legs.items():
        opening_source, is_winner, calibration = row[4], row[5], row[6]
        if opening_source is not None:
            raise Refused(f"outcome {oid} opening_source={opening_source!r}, pinned NULL; refusing")
        if is_winner is not None or calibration is not None:
            raise Refused(
                f"outcome {oid} is graded (is_winner={is_winner!r}) or carries "
                f"calibration_probability={calibration!r}; a published number now depends "
                "on the opening — refusing, decide by hand"
            )

    state = {oid: _state(row) for oid, row in legs.items()}
    source, target = (AFTER, BEFORE) if restore else (BEFORE, AFTER)
    if state == target:
        return []
    if state != source:
        raise Refused(
            f"state {state} is neither {source} nor {target}; refusing — read both "
            "legs before deciding by hand"
        )
    return [(oid, source[oid], target[oid]) for oid in (OVER, UNDER)]


async def _read(session) -> tuple[tuple | None, dict[int, tuple]]:
    got = await session.execute(
        text("SELECT source, name, event_id FROM futures_markets WHERE id = :mid"),
        {"mid": MARKET_ID},
    )
    m = got.first()
    market = None if m is None else (m.source, m.name, m.event_id)
    rows = await session.execute(
        text(
            "SELECT id, name, opening_probability, opening_american_odds, "
            "opening_captured_at, opening_source, is_winner, calibration_probability "
            "FROM futures_outcomes WHERE market_id = :mid"
        ),
        {"mid": MARKET_ID},
    )
    legs = {
        int(r.id): (
            r.name,
            r.opening_probability,
            r.opening_american_odds,
            r.opening_captured_at,
            r.opening_source,
            r.is_winner,
            r.calibration_probability,
        )
        for r in rows
    }
    return market, legs


async def _backup(session) -> int:
    await session.execute(
        text(
            f"CREATE TABLE IF NOT EXISTS {BACKUP_TABLE} ("
            " outcome_id integer PRIMARY KEY,"
            " name text,"
            " opening_probability numeric(7,6),"
            " opening_american_odds integer,"
            " opening_captured_at timestamptz,"
            " taken_at timestamptz NOT NULL DEFAULT now())"
        )
    )
    await session.execute(
        text(
            f"INSERT INTO {BACKUP_TABLE} (outcome_id, name, opening_probability, "
            "opening_american_odds, opening_captured_at) "
            "SELECT id, name, opening_probability, opening_american_odds, opening_captured_at "
            "FROM futures_outcomes WHERE market_id = :mid AND id = ANY(:ids) "
            "ON CONFLICT (outcome_id) DO NOTHING"
        ),
        {"mid": MARKET_ID, "ids": sorted(BEFORE)},
    )
    await session.commit()
    banked = await session.execute(
        text(
            f"SELECT outcome_id, name, opening_probability, opening_american_odds, "
            f"opening_captured_at FROM {BACKUP_TABLE} WHERE outcome_id = ANY(:ids)"
        ),
        {"ids": sorted(BEFORE)},
    )
    # Count only rows that banked the BEFORE state — a bank of the wrong state
    # would make the undo evidence lie.
    return sum(
        1
        for r in banked
        if _state(
            (r.name, r.opening_probability, r.opening_american_odds, r.opening_captured_at)
        )
        == BEFORE[int(r.outcome_id)]
    )


_CLEAR = text(
    "UPDATE futures_outcomes SET opening_probability = NULL, "
    "opening_american_odds = NULL, opening_captured_at = NULL "
    "WHERE id = :id AND market_id = :mid AND opening_source IS NULL "
    "AND is_winner IS NULL AND calibration_probability IS NULL "
    "AND opening_probability = :prob AND opening_american_odds = :odds "
    "AND opening_captured_at = :at"
)

_RESTORE = text(
    "UPDATE futures_outcomes SET opening_probability = :prob, "
    "opening_american_odds = :odds, opening_captured_at = :at "
    "WHERE id = :id AND market_id = :mid AND opening_source IS NULL "
    "AND is_winner IS NULL AND calibration_probability IS NULL "
    "AND opening_probability IS NULL AND opening_american_odds IS NULL "
    "AND opening_captured_at IS NULL"
)


async def run(session, *, apply: bool, restore: bool) -> dict:
    market, legs = await _read(session)
    writes = plan(market, legs, restore=restore)
    written = 0
    if writes and (apply or restore):
        if apply:
            banked = await _backup(session)
            if banked < len(BEFORE):
                raise Refused(f"backup holds {banked} of {len(BEFORE)} legs; refusing to clear")
        for oid, _from, _to in writes:
            # Both directions bind the pinned BEFORE values: the clear matches on
            # them, the restore writes them.
            _name, prob, odds, at = BEFORE[oid]
            result = await session.execute(
                _RESTORE if restore else _CLEAR,
                {"id": oid, "mid": MARKET_ID, "prob": prob, "odds": odds, "at": at},
            )
            if result.rowcount != 1:
                await session.rollback()
                raise Refused(
                    f"outcome {oid} changed under the run; rolled back, nothing written"
                )
            written += 1
        await session.commit()
    # Read back from disk rather than trusting rowcount (gotcha #53).
    _m, after = await _read(session)
    return {
        "mode": "restore" if restore else ("apply" if apply else "dry-run"),
        "planned": [
            {"outcome_id": oid, "from": str(frm), "to": str(to)} for oid, frm, to in writes
        ],
        "written": written,
        "now": {str(oid): str(_state(row)) for oid, row in sorted(after.items())},
    }


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--apply", action="store_true")
    group.add_argument("--restore", action="store_true")
    args = ap.parse_args()

    try:
        refuse_unless_production(dict(os.environ))
    except Refused as exc:
        print(f"REFUSED: {exc}")
        return 2

    from app.tasks.base import get_task_session

    async with get_task_session() as session:
        try:
            out = await run(session, apply=args.apply, restore=args.restore)
        except Refused as exc:
            await session.rollback()
            print(f"REFUSED: {exc}")
            return 2
    print(json.dumps(out, indent=2, ensure_ascii=False))
    if out["mode"] == "apply":
        print(
            "UNDO: heroku run:detached -a bainluck -- "
            "python3 scripts/repair_9850_trammell_seeded_opening.py --restore"
        )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
