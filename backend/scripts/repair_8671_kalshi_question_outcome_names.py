"""#8671 — settled Kalshi options stop wearing their market's question as a name.

THE SHIP: a settled Kalshi market names its options. Search "Fed chair" read
"How many Senators vote to confirm  as Chair… >99%" (#8671); a settled leg
named "Will exactly 0 people be pardoned in Aug 2026?" should read "0". The
same name is on every card, rail and market page that prints the leg.

WHY (read from production 2026-09-26 23:30Z)
--------------------------------------------

Kalshi legs whose stored ``futures_outcomes.name`` ends in ``?``: 1,290 rows —
1,168 on 965 ``resolved`` markets, 122 on 21 ``open`` ones. The ones that are
the market's own QUESTION are what ``_kalshi_outcome_name`` step 5 handed back
before #4246 (merged 2026-09-09) refused a question as a contender's name.

#4246 fixed the ladder, and the poll re-derives names on every pass, so every
leg the poll still visits reads right today (open count markets were checked:
"At least 10", "Above 0", "3 to 9"). What it cannot reach is a leg the poll no
longer visits — every settled market, and the few open ones that dropped out of
the poll's scope before 9/9. Their names are frozen at the pre-#4246 answer.
The only open markets carrying a question-named leg were last polled before
9/9 (newest: ``KXALBUMRELEASEDATEFRANK``, 9/6), and the settled-events grader
writes ``is_winner`` and the settled price but never ``name``, so the
population is a finite backlog: nothing that runs today adds to it.

WHAT IS WRITTEN
---------------

For each market holding a ``?``-named leg, the venue's event is read fresh
(``GET /events/{ticker}?with_nested_markets=true``) and the legs are named by
THE ONE LADDER — ``kalshi_outcome_names`` — exactly as the poll would name them
today. A leg is renamed only when all of these hold:

* the stored name IS the venue market's own ``title`` (the step-5 fallback) —
  so a real name that happens to end in ``?`` ("Is It Cool?", "GATO PENSANTE?",
  a ``yes_sub_title`` the venue wrote with a ``?``) is never touched;
* the ladder's answer differs from the stored name (the collision rescue may
  hand the title back verbatim; then there is nothing better to write).

The answer is NOT refused for ending in ``?``: a ``yes_sub_title`` such as
"Is It Cool?" is a real name, and the ladder is the authority on it.

An event whose markets Kalshi has purged (market data purges at 74–86 days,
gotcha #35; ``KXFEDCHAIRCOUNT-27``, the issue's specimen, is one) is REPORTED
and left alone. Nothing is inferred from a ticker leg: ``B54`` means "exactly
54" on that market and "85° to 86°" on a weather one, and the venue is not
there to say which.

The UPDATE is a compare-and-swap on the stored name. ``last_updated`` is not
touched: the price did not change, and staleness gates read that column.

THE BACKUP AND THE UNDO
-----------------------

``--apply`` first banks each row's BEFORE and AFTER name in
``backup_8671_kalshi_outcome_names`` and refuses to write if the bank is short.
``--restore`` writes BEFORE back only where the row still carries the name this
repair wrote. ``CREATE TABLE IF NOT EXISTS`` is runtime DDL behind a person's
invocation on a named app: notice 47(c), not migration-class.

    heroku run:detached -a bainluck-heavy -- python3 scripts/repair_8671_kalshi_question_outcome_names.py            # dry run
    heroku run:detached -a bainluck-heavy -- python3 scripts/repair_8671_kalshi_question_outcome_names.py --apply    # backup + rename
    heroku run:detached -a bainluck-heavy -- python3 scripts/repair_8671_kalshi_question_outcome_names.py --restore  # undo

Refuses unless ``HEROKU_APP_NAME`` is ``bainluck`` or ``bainluck-heavy``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import Counter
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

PRODUCTION_APPS = frozenset({"bainluck", "bainluck-heavy"})

BACKUP_TABLE = "backup_8671_kalshi_outcome_names"

#: ``futures_outcomes.name`` is VARCHAR(300); every writer truncates to it.
NAME_MAX = 300

#: Seconds between venue reads — ~900 events, well inside Kalshi's public rate.
VENUE_PAUSE_S = 0.15


class Refused(RuntimeError):
    """The run stops before any write."""


@dataclass(frozen=True)
class StoredLeg:
    outcome_id: int
    market_id: int
    event_ticker: str
    ticker: str
    name: str


def refuse_unless_production(env: dict) -> None:
    app = env.get("HEROKU_APP_NAME", "")
    if app not in PRODUCTION_APPS:
        raise Refused(
            f"HEROKU_APP_NAME={app!r} is not a production app "
            f"({sorted(PRODUCTION_APPS)}); refusing"
        )


def plan_event(legs: list[StoredLeg], venue_event) -> tuple[list[tuple], list[tuple]]:
    """Decide every stored leg of ONE event. Pure, so the unit file drives it.

    ``venue_event`` is the parsed ``KalshiEvent`` (or None when the venue read
    failed). Returns ``(renames, skips)``: ``renames`` holds
    ``(outcome_id, before, after)``, ``skips`` holds ``(outcome_id, reason)``.
    """
    from app.tasks.kalshi import kalshi_outcome_names

    if venue_event is None:
        return [], [(leg.outcome_id, "venue unreadable") for leg in legs]
    if not venue_event.markets:
        return [], [(leg.outcome_id, "venue purged its markets") for leg in legs]

    ladder = kalshi_outcome_names(venue_event.title, venue_event.markets)
    titles = {m.ticker: (m.title or "").strip()[:NAME_MAX] for m in venue_event.markets}
    renames, skips = [], []
    for leg in legs:
        if leg.ticker not in ladder:
            skips.append((leg.outcome_id, "leg not listed by the venue"))
            continue
        if leg.name.strip() != titles[leg.ticker]:
            skips.append((leg.outcome_id, "stored name is not the market's question"))
            continue
        after = (ladder[leg.ticker] or "").strip()[:NAME_MAX]
        if not after or after == leg.name:
            skips.append((leg.outcome_id, "ladder gives the same name"))
            continue
        renames.append((leg.outcome_id, leg.name, after))
    return renames, skips


async def _read_candidates(session) -> dict[str, list[StoredLeg]]:
    got = await session.execute(
        text(
            "SELECT fo.id, fo.market_id, fm.external_id AS event_ticker, "
            "fo.external_id AS ticker, fo.name "
            "FROM futures_outcomes fo JOIN futures_markets fm ON fm.id = fo.market_id "
            "WHERE fm.source = 'kalshi' AND fo.name LIKE '%?' "
            "ORDER BY fm.external_id, fo.external_id"
        )
    )
    by_event: dict[str, list[StoredLeg]] = {}
    for r in got:
        by_event.setdefault(r.event_ticker, []).append(
            StoredLeg(int(r.id), int(r.market_id), r.event_ticker, r.ticker, r.name)
        )
    return by_event


async def _backup(session, renames: list[tuple]) -> int:
    await session.execute(
        text(
            f"CREATE TABLE IF NOT EXISTS {BACKUP_TABLE} ("
            " outcome_id integer PRIMARY KEY,"
            " before_name varchar(300) NOT NULL,"
            " after_name varchar(300) NOT NULL,"
            " taken_at timestamptz NOT NULL DEFAULT now())"
        )
    )
    for outcome_id, before, after in renames:
        await session.execute(
            text(
                f"INSERT INTO {BACKUP_TABLE} (outcome_id, before_name, after_name) "
                "VALUES (:id, :before, :after) ON CONFLICT (outcome_id) DO NOTHING"
            ),
            {"id": outcome_id, "before": before, "after": after},
        )
    await session.commit()
    banked = await session.execute(
        text(
            f"SELECT count(*) FROM {BACKUP_TABLE} "
            "WHERE outcome_id = ANY(:ids)"
        ),
        {"ids": [r[0] for r in renames]},
    )
    return int(banked.scalar_one())


async def _restore(session) -> dict:
    result = await session.execute(
        text(
            f"UPDATE futures_outcomes fo SET name = b.before_name FROM {BACKUP_TABLE} b "
            "WHERE fo.id = b.outcome_id AND fo.name = b.after_name"
        )
    )
    await session.commit()
    total = await session.execute(text(f"SELECT count(*) FROM {BACKUP_TABLE}"))
    return {"mode": "restore", "banked": int(total.scalar_one()), "written": result.rowcount}


async def run(session, service, *, apply: bool) -> dict:
    by_event = await _read_candidates(session)
    renames: list[tuple] = []
    reasons: Counter = Counter()
    purged_events: list[str] = []
    for i, (event_ticker, legs) in enumerate(by_event.items()):
        if i:
            await asyncio.sleep(VENUE_PAUSE_S)
        raw = await service.get_event(event_ticker, with_nested_markets=True)
        venue_event = service._parse_event(raw) if raw is not None else None
        got, skips = plan_event(legs, venue_event)
        renames.extend(got)
        for _, reason in skips:
            reasons[reason] += 1
        if venue_event is not None and not venue_event.markets:
            purged_events.append(event_ticker)

    written = 0
    if apply and renames:
        banked = await _backup(session, renames)
        if banked < len(renames):
            raise Refused(f"backup holds {banked} of {len(renames)} rows; refusing to rename")
        for outcome_id, before, after in renames:
            result = await session.execute(
                text("UPDATE futures_outcomes SET name = :after WHERE id = :id AND name = :before"),
                {"id": outcome_id, "before": before, "after": after},
            )
            written += result.rowcount
        await session.commit()

    # Read back from disk rather than trusting rowcount (gotcha #53).
    reads_after = 0
    if renames:
        got = await session.execute(
            text("SELECT count(*) FROM futures_outcomes WHERE id = ANY(:ids) AND name LIKE '%?'"),
            {"ids": [r[0] for r in renames]},
        )
        reads_after = int(got.scalar_one())
    return {
        "mode": "apply" if apply else "dry-run",
        "events_read": len(by_event),
        "legs_read": sum(len(v) for v in by_event.values()),
        "planned": len(renames),
        "written": written,
        "planned_still_ending_in_question_mark": reads_after,
        "skipped_by_reason": dict(reasons.most_common()),
        "purged_events_sample": purged_events[:25],
        "sample": [
            {"outcome_id": o, "before": b, "after": a} for o, b, a in renames[:40]
        ],
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

    from app.services.kalshi_api import KalshiAPIService
    from app.tasks.base import get_task_session

    service = KalshiAPIService()
    try:
        async with get_task_session() as session:
            try:
                if args.restore:
                    out = await _restore(session)
                else:
                    out = await run(session, service, apply=args.apply)
            except Refused as exc:
                await session.rollback()
                print(f"REFUSED: {exc}")
                return 2
    finally:
        await service.close()
    print(json.dumps(out, indent=2, ensure_ascii=False))
    if out["mode"] == "apply":
        print(
            "UNDO: heroku run:detached -a bainluck-heavy -- "
            "python3 scripts/repair_8671_kalshi_question_outcome_names.py --restore"
        )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
