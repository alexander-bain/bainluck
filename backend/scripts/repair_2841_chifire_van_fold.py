"""#2841 — Chicago Fire v Vancouver (Oct 6) shows once, at 5:30 PM PT, with its Kalshi market.

THE SHIP: ``/search?q=whitecaps`` stops showing this match twice with two
different answers — "Oct 6 11:00 AM · 50%" beside "Oct 6 5:30 PM · 29%" — and
the one card it keeps is at ESPN's kickoff and carries the Kalshi game market.

WHAT EACH ROW IS, measured 2026-09-27 ~06:30Z
--------------------------------------------

* ``14969919`` — created 2026-06-30 from Odds API id ``1d13bd27…``, which the
  provider no longer lists (it re-issued the fixture). Kickoff 2026-10-06 18:00Z,
  6h30m early. Holds ESPN ``761660``, the Kalshi game market
  ``KXMLSGAME-26OCT06CHIVAN`` (62383846), a bare ``betting: 0.5`` placeholder,
  and three RESOLVED Kalshi markets for the July 16 meeting of these clubs.
  It has NO ``event_provider_anchors`` row — it predates the anchor channel — so
  the #8422 re-issue sweep, whose population joins that table, never reads it.
* ``15316563`` — created 2026-09-21 from Odds API id ``0d9ff865…``, which the
  provider lists. Kickoff 2026-10-07 00:30Z, which is what ESPN's own record for
  ``761660`` says. Three sportsbooks, the two Polymarket Starting 11 markets.

Of the six open rows in the next 60 days that hold an ESPN id and are twinned by
an id-less row of the same pair, the other five share an exact kickoff and the
serve-time fold already shows them once. This is the only one a reader sees
twice, which is why it is a pinned repair and not a sweep arm.

WHY THIS IS ID-ANCHORED, NOT NAME-AND-TIME (ruling 048)
-------------------------------------------------------

The script writes nothing unless TWO providers' own records agree, read live on
the run, keyed on their own ids:

* ESPN: ``761660`` dereferences (``summary?event=761660``) to Chicago v Vancouver
  at ``15316563``'s kickoff, with ``timeValid`` — not at ``14969919``'s;
* the Odds API: ``/events`` for MLS lists ``15316563``'s id and not
  ``14969919``'s (gotcha #32's second arm, read in the negative, as #8422 does).

WHAT IT WRITES (one transaction, compare-and-swap on every statement)
---------------------------------------------------------------------

1. ESPN ``761660`` moves from ``14969919`` to ``15316563`` (cleared first:
   ``uq_events_espn_id``), so ESPN's scores and status land on the card a reader
   can see;
2. market 62383846 moves to ``15316563``, with an immutable ``market_link_changes``
   row (actor/phase ``admin_repair``) through ``MatchReceipt.supersede()``;
3. ``14969919`` gains ``provenance:duplicate-of:15316563``, whose read side
   (``not_a_proven_duplicate``) hides it on search, the rails and the feed.

NOT DONE HERE, said rather than implied: the three July 16 markets stay on the
hidden row (they are not this match's, and no July 16 row exists to take them);
no ``win_probability_sources`` value is copied — the Kalshi reading reaches
``15316563`` from the live-blend writer on the market's next price, never from a
stale 9/25 value carried over by hand; neither row's kickoff is edited.

D51 — banked first, undone by one command, and the undo reverts only what is
still where this repair put it:

    python3 scripts/repair_2841_chifire_van_fold.py            # dry run
    python3 scripts/repair_2841_chifire_van_fold.py --apply    # bank, move, tag
    python3 scripts/repair_2841_chifire_van_fold.py --restore  # undo

Runs only on ``bainluck-heavy`` (notice 47(c): runtime DDL, attended invocation).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

PRODUCER_APP = "bainluck-heavy"
SPORT_KEY = "soccer_usa_mls"

GHOST = 14969919
CANON = 15316563
ESPN_ID = "761660"
HOME_TEAM_ID, AWAY_TEAM_ID = 16, 23
GHOST_KICKOFF = datetime(2026, 10, 6, 18, 0, tzinfo=timezone.utc)
CANON_KICKOFF = datetime(2026, 10, 7, 0, 30, tzinfo=timezone.utc)
GHOST_ODDS_ID = "1d13bd275c7b67b77bea8ff4d03850cc"
CANON_ODDS_ID = "0d9ff865c4599c72a746da08260279b3"
GAME_MARKET = 62383846
GAME_TICKER = "KXMLSGAME-26OCT06CHIVAN"

#: ESPN's names for the two clubs contain these; a summary that names anyone
#: else is a different match and the run refuses.
HOME_WORD, AWAY_WORD = "chicago", "vancouver"

#: Not within an hour of the kickoff: Kalshi and ESPN write to these rows while
#: the match is on, and a move mid-write is the one race this cannot CAS away.
MIN_LEAD = timedelta(hours=1)

BACKUP = "backup_2841_chifire_van"

TAG = f"provenance:duplicate-of:{CANON}"

REFUSED = 2


def wrong_app_refusal() -> str | None:
    app = os.environ.get("HEROKU_APP_NAME")
    if app == PRODUCER_APP:
        return None
    return (
        f"refusing to run on HEROKU_APP_NAME={app!r}: this repair writes "
        f"production rows and runs only on {PRODUCER_APP!r}"
    )


def _aware(value):
    if isinstance(value, datetime) and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _tagged(tags) -> bool:
    return "duplicate-of" in (tags or "")


def rows_refusal(rows: dict[int, dict], market: dict | None, holders: list[int]) -> str | None:
    """Why the database is not in the state this repair was written for. Pure."""
    for eid in (GHOST, CANON):
        if eid not in rows:
            return f"event {eid} is gone"
    g, c = rows[GHOST], rows[CANON]
    for eid, r in ((GHOST, g), (CANON, c)):
        if r["sport_key"] != SPORT_KEY:
            return f"{eid} is {r['sport_key']!r}, not {SPORT_KEY!r}"
        if (r["home_team_id"], r["away_team_id"]) != (HOME_TEAM_ID, AWAY_TEAM_ID):
            return f"{eid} names teams {r['home_team_id']}/{r['away_team_id']}"
        if r["status"] != "scheduled":
            return f"{eid} is {r['status']!r}, not 'scheduled'"
        if _tagged(r["event_tags"]):
            return f"{eid} already carries a duplicate-of label"
    if _aware(g["commence_time"]) != GHOST_KICKOFF:
        return f"{GHOST} kickoff moved to {g['commence_time']}"
    if _aware(c["commence_time"]) != CANON_KICKOFF:
        return f"{CANON} kickoff moved to {c['commence_time']}"
    if g["espn_id"] != ESPN_ID:
        return f"{GHOST} holds ESPN {g['espn_id']!r}, not {ESPN_ID!r}"
    if c["espn_id"] is not None:
        return f"{CANON} already holds ESPN {c['espn_id']!r}"
    if sorted(holders) != [GHOST]:
        return f"ESPN {ESPN_ID} is held by {sorted(holders)}"
    if g["external_id"] != GHOST_ODDS_ID or c["external_id"] != CANON_ODDS_ID:
        return f"Odds API ids changed: {g['external_id']!r} / {c['external_id']!r}"
    if market is None:
        return f"market {GAME_MARKET} is gone"
    if (market["source"], market["external_id"]) != ("kalshi", GAME_TICKER):
        return f"market {GAME_MARKET} is {market['source']}:{market['external_id']}"
    if market["event_id"] != GHOST:
        return f"market {GAME_MARKET} is linked to {market['event_id']}, not {GHOST}"
    if market["status"] != "open":
        return f"market {GAME_MARKET} is {market['status']!r}"
    return None


def evidence_refusal(espn_event, odds_listed: set[str] | None) -> str | None:
    """Both providers, keyed on their own ids, must place the match at CANON. Pure."""
    if espn_event is None:
        return f"ESPN did not answer for {ESPN_ID} (absent or dark) — nothing to anchor on"
    if not getattr(espn_event, "time_valid", False):
        return f"ESPN's time for {ESPN_ID} is a date-only placeholder (timeValid false)"
    if _aware(espn_event.date) != CANON_KICKOFF:
        return f"ESPN places {ESPN_ID} at {espn_event.date}, not {CANON_KICKOFF}"
    home = (getattr(espn_event.home_team, "name", "") or "").lower()
    away = (getattr(espn_event.away_team, "name", "") or "").lower()
    if HOME_WORD not in home or AWAY_WORD not in away:
        return f"ESPN {ESPN_ID} is {home!r} v {away!r}"
    if odds_listed is None:
        return "the Odds API schedule was not read"
    if CANON_ODDS_ID not in odds_listed:
        return f"the Odds API no longer lists {CANON}'s id {CANON_ODDS_ID}"
    if GHOST_ODDS_ID in odds_listed:
        return f"the Odds API still lists {GHOST}'s id {GHOST_ODDS_ID} — not a re-issue"
    return None


def lead_refusal(now: datetime) -> str | None:
    if now > CANON_KICKOFF - MIN_LEAD:
        return f"within {MIN_LEAD} of the kickoff ({CANON_KICKOFF}) — run it before, or not at all"
    return None


_ROWS_SQL = """
SELECT e.id, s.key AS sport_key, e.home_team_id, e.away_team_id, e.status,
       e.commence_time, e.espn_id, e.external_id,
       CAST(e.event_tags AS text) AS event_tags
FROM events e JOIN sports s ON s.id = e.sport_id
WHERE e.id IN (:g, :c)
"""


async def _read(session) -> tuple[dict[int, dict], dict | None, list[int]]:
    res = await session.execute(text(_ROWS_SQL), {"g": GHOST, "c": CANON})
    rows = {int(r.id): dict(r._mapping) for r in res}
    mres = await session.execute(
        text(
            "SELECT id, event_id, source, external_id, name, status "
            "FROM futures_markets WHERE id = :m"
        ),
        {"m": GAME_MARKET},
    )
    mrow = mres.first()
    market = dict(mrow._mapping) if mrow else None
    hres = await session.execute(
        text("SELECT id FROM events WHERE espn_id = :e"), {"e": ESPN_ID}
    )
    return rows, market, [int(r.id) for r in hres]


async def _backup_exists(session) -> bool:
    res = await session.execute(text("SELECT to_regclass(:t)"), {"t": BACKUP})
    return res.scalar_one() is not None


async def _bank(session, rows: dict[int, dict], market: dict) -> None:
    """First pre-image wins: a second run never overwrites what was banked."""
    await session.execute(
        text(
            f"CREATE TABLE IF NOT EXISTS {BACKUP} (item text PRIMARY KEY, "
            "row_id bigint NOT NULL, before text, banked_at timestamptz NOT NULL DEFAULT now())"
        )
    )
    items = (
        ("ghost_espn_id", GHOST, rows[GHOST]["espn_id"]),
        ("canon_espn_id", CANON, rows[CANON]["espn_id"]),
        ("ghost_event_tags", GHOST, rows[GHOST]["event_tags"]),
        ("market_event_id", GAME_MARKET, str(market["event_id"])),
    )
    for item, row_id, before in items:
        await session.execute(
            text(
                f"INSERT INTO {BACKUP} (item, row_id, before) "
                "VALUES (:item, :row_id, :before) ON CONFLICT (item) DO NOTHING"
            ),
            {"item": item, "row_id": row_id, "before": before},
        )


async def _cas(session, sql: str, what: str, **params) -> None:
    res = await session.execute(text(sql), params)
    if (res.rowcount or 0) != 1:
        raise RuntimeError(f"{what}: {res.rowcount} rows (expected 1) — moved since the read")


def _receipt(market: dict, previous: int, new: int, now: datetime, direction: str):
    from app.utils.match_receipts import (
        ACTOR_ADMIN_REPAIR,
        PHASE_ADMIN_REPAIR,
        MatchReceipt,
    )

    return MatchReceipt(
        market_id=int(market["id"]),
        source=market["source"],
        external_id=market["external_id"],
        market_name=market["name"],
        phase=PHASE_ADMIN_REPAIR,
        attempted_at=now,
    ).supersede(
        previous,
        new,
        actor=ACTOR_ADMIN_REPAIR,
        issue="2841",
        gate=f"{direction}: ESPN {ESPN_ID} + Odds API /events both place the match at {CANON}",
    )


_ADD_TAG = (
    "UPDATE events SET event_tags = "
    "COALESCE(event_tags, CAST('[]' AS jsonb)) || jsonb_build_array(CAST(:tag AS text)) "
    "WHERE id = :g AND NOT (COALESCE(event_tags, CAST('[]' AS jsonb)) @> "
    "jsonb_build_array(CAST(:tag AS text)))"
)

_DROP_TAG = (
    "UPDATE events SET event_tags = (SELECT COALESCE(jsonb_agg(x), CAST('[]' AS jsonb)) "
    "FROM jsonb_array_elements(event_tags) AS x WHERE x <> to_jsonb(CAST(:tag AS text))) "
    "WHERE id = :g AND event_tags @> jsonb_build_array(CAST(:tag AS text))"
)


async def _apply(session, market: dict, now: datetime) -> None:
    from app.utils.match_receipts import flush_receipts

    await _cas(
        session,
        "UPDATE events SET espn_id = NULL WHERE id = :g AND espn_id = :e",
        "clear ESPN on the stale row",
        g=GHOST,
        e=ESPN_ID,
    )
    await _cas(
        session,
        "UPDATE events SET espn_id = :e WHERE id = :c AND espn_id IS NULL",
        "set ESPN on the kept row",
        c=CANON,
        e=ESPN_ID,
    )
    await _cas(
        session,
        "UPDATE futures_markets SET event_id = :c WHERE id = :m AND event_id = :g",
        "move the Kalshi game market",
        c=CANON,
        m=GAME_MARKET,
        g=GHOST,
    )
    await _cas(session, _ADD_TAG, "label the stale row", tag=TAG, g=GHOST)
    await flush_receipts(session, [_receipt(market, GHOST, CANON, now, "apply")])


async def _landed(session) -> str | None:
    rows, market, holders = await _read(session)
    g, c = rows.get(GHOST), rows.get(CANON)
    if not g or not c:
        return "a row vanished mid-repair"
    if g["espn_id"] is not None or c["espn_id"] != ESPN_ID or holders != [CANON]:
        return f"ESPN readback: stale {g['espn_id']!r}, kept {c['espn_id']!r}, holders {holders}"
    if not market or market["event_id"] != CANON:
        return f"market readback: {market and market['event_id']}"
    if TAG not in (g["event_tags"] or ""):
        return f"label readback: {g['event_tags']!r}"
    return None


async def _restore(session, now: datetime) -> dict[str, int]:
    """Undo only what is still where this repair put it. Never forces."""
    from app.utils.match_receipts import flush_receipts

    if not await _backup_exists(session):
        raise RuntimeError(f"{BACKUP} does not exist — nothing was applied here")
    tag = await session.execute(text(_DROP_TAG), {"tag": TAG, "g": GHOST})
    market_res = await session.execute(
        text("UPDATE futures_markets SET event_id = :g WHERE id = :m AND event_id = :c"),
        {"g": GHOST, "m": GAME_MARKET, "c": CANON},
    )
    moved_back = market_res.rowcount or 0
    if moved_back:
        _, market, _ = await _read(session)
        await flush_receipts(session, [_receipt(market, CANON, GHOST, now, "restore")])
    espn = 0
    cleared = await session.execute(
        text("UPDATE events SET espn_id = NULL WHERE id = :c AND espn_id = :e"),
        {"c": CANON, "e": ESPN_ID},
    )
    if cleared.rowcount:
        back = await session.execute(
            text("UPDATE events SET espn_id = :e WHERE id = :g AND espn_id IS NULL"),
            {"g": GHOST, "e": ESPN_ID},
        )
        espn = back.rowcount or 0
    return {"label": tag.rowcount or 0, "market": moved_back, "espn": espn}


async def repair(session, mode: str, *, evidence: str | None, now: datetime) -> tuple[int, list[str]]:
    """``mode`` is ``dry``, ``apply`` or ``restore``. Returns (exit code, lines).

    ``evidence`` is :func:`evidence_refusal`'s answer, read before the session
    opens. Commits only on a clean apply or restore; every refusal writes nothing.
    """
    out: list[str] = []
    if mode == "restore":
        try:
            restored = await _restore(session, now)
        except Exception as exc:
            await session.rollback()
            out.append(f"ROLLED BACK: {exc}")
            return 1, out
        await session.commit()
        out.append(f"  restored: {json.dumps(restored)}")
        return 0, out

    rows, market, holders = await _read(session)
    if (
        GHOST in rows
        and TAG in (rows[GHOST]["event_tags"] or "")
        and market is not None
        and market["event_id"] == CANON
        and await _backup_exists(session)
    ):
        out.append(f"already applied: {GHOST} carries {TAG} and {BACKUP} holds the pre-image.")
        return 0, out
    for label, refusal in (
        ("rows", rows_refusal(rows, market, holders)),
        ("evidence", evidence),
        ("clock", lead_refusal(now)),
    ):
        if refusal:
            out.append(f"REFUSED ({label}): {refusal}")
            return REFUSED, out
    out.append(
        f"  {GHOST} (ESPN {ESPN_ID}, {GHOST_KICKOFF:%m-%d %H:%MZ}) -> {CANON} ({CANON_KICKOFF:%m-%d %H:%MZ})"
    )
    out.append(f"  market {GAME_MARKET} {GAME_TICKER}: {GHOST} -> {CANON}")
    if mode != "apply":
        out.append(
            f"\ndry run — nothing written. Would bank into {BACKUP}, move ESPN {ESPN_ID} "
            f"and market {GAME_MARKET} to {CANON}, and label {GHOST} {TAG}."
        )
        return 0, out
    try:
        await _bank(session, rows, market)
        await _apply(session, market, now)
        stray = await _landed(session)
        if stray:
            raise RuntimeError(stray)
    except Exception as exc:  # one transaction: any failure undoes all of it
        await session.rollback()
        out.append(f"ROLLED BACK: {exc}")
        return 1, out
    await session.commit()
    out.append(f"\n  applied: banked in {BACKUP}; ESPN, market and label moved.")
    out.append("undo: python3 scripts/repair_2841_chifire_van_fold.py --restore")
    return 0, out


async def read_evidence() -> str | None:
    from app.services.espn_api import ESPNAPIService
    from app.tasks.odds_api_reissued_twin_sweep import read_schedules

    espn = ESPNAPIService()
    try:
        event = await espn.get_event(SPORT_KEY, ESPN_ID)
    finally:
        await espn.close()
    schedules, errors = await read_schedules({SPORT_KEY})
    if errors:
        return f"the Odds API schedule read failed: {errors}"
    return evidence_refusal(event, schedules.get(SPORT_KEY))


async def run(mode: str) -> int:
    refusal = wrong_app_refusal()
    if refusal:
        print(f"REFUSED: {refusal}")
        return REFUSED
    from app.tasks.base import get_task_session
    from app.tasks.odds_api_reissued_twin_sweep import consumer_is_live

    if mode != "restore" and not consumer_is_live():
        print("REFUSED: search no longer calls not_a_proven_duplicate — the label would hide nothing")
        return REFUSED
    evidence = None if mode == "restore" else await read_evidence()
    print(f"#2841 Chicago Fire v Vancouver — {mode.upper()}")
    async with get_task_session() as session:
        code, lines = await repair(session, mode, evidence=evidence, now=datetime.now(timezone.utc))
    for line in lines:
        print(line)
    return code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--apply", action="store_true", help="bank, move, label (default: dry run)")
    group.add_argument("--restore", action="store_true", help="undo what is still where the repair put it")
    args = parser.parse_args()
    mode = "restore" if args.restore else ("apply" if args.apply else "dry")
    return asyncio.run(run(mode))


if __name__ == "__main__":
    raise SystemExit(main())
