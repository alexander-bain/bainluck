"""#2993 — the historical cleanup: unmake the events a bracket minted.

THE SHIP: an esports card stops presenting a tournament bracket as a game.
Event 15301525 rendered on 2026-09-03 as a live card reading "Europe vs
Finals", with a League of Legends MVP prop attached to it. There is no game
there: "FNCS Major 2" is the tournament, "Europe" the region and "Grand Finals"
the stage.

PREVENTION SHIPS WITH THIS. `bracket_refusal_reason()` refuses auto-create for
both shapes, so no NEW row is minted. This script is the owed DATA REPAIR for
the 17 rows written before it landed. The predicate is IMPORTED, never
restated: the repair's population is by construction exactly the set the guard
would now refuse.

------------------------------------------------------------------------------
THE POPULATION — 17 rows, two shapes, measured on production 2026-09-04
------------------------------------------------------------------------------

  15  "VALORANT Masters" / "Masters Santiago (Playoffs"   THE CUT
   2  "FNCS Major 2: <region>" / "Grand Finals"           THE STAGE

Of 231,419 events ever created, exactly these 17 carry a name the guard
refuses. Zero collateral — the repair is as wide as the defect and no wider.

------------------------------------------------------------------------------
WHY THIS DELETES WHERE #2871 REFUSED TO
------------------------------------------------------------------------------

#2871 rejected `DELETE FROM events` because 68% of its rows were the ONLY
record of a real fixture: their home name was clean and only the away name
carried a market-type suffix, so normalizing recovered a findable game.

That is measurably not true here. These rows name no fixture at all — home is a
TOURNAMENT and away is a STAGE or a string cut mid-token. No user can find a
match through them, so deleting one loses nothing a rename could have kept.
The exception is handled rather than assumed:

  **RENAME (1 row).** Event 14546060 carries external_id
  `pm_kalshi_KXVALORANTMAP-26MAR14PRNRG-1`. That ticker's market is named
  "… (Playoffs: Playoffs): Paper Rex vs. NRG Map 1" and commences at the
  event's own commence_time, and NO clean event for Paper Rex v NRG exists on
  2026-03-28 (checked across every esports row that day). It is the sole trace
  of a real match and its identity is reconstructible from its own provenance,
  so it is renamed, not deleted — #2947's Branch B.

  **DELETE (16 rows).** Everything else: either no reconstructible identity
  (10 rows carry no external_id at all), or a clean counterpart already exists,
  in which case the row is a duplicate of a game we already hold correctly.

A rename is only ever taken when BOTH hold — identity reconstructible AND no
clean counterpart — so the repair can never mint a lookalike of a row that
already exists.

------------------------------------------------------------------------------
CHILDREN — all 11 FK tables counted, not the four that came to mind
------------------------------------------------------------------------------

    futures_markets          32   NO ACTION   → UNLINKED (event_id = NULL)
    line_movement_analyses    1   NO ACTION   → DELETED (a taxonomy cache row)
    event_provider_anchors    1   CASCADE     → goes with the row
    the other eight           0

`futures_markets` is UNLINKED rather than re-pointed. 30 of the 32 are settled
Kalshi map markets from 14 distinct real matches, all glued onto one fictional
event (14654135) — a market cannot belong to the event it is being detached
from, and 12 of those 14 matches already have a clean event of their own.
Re-pointing settled derivative markets onto their real matches is a genuine
improvement and a DIFFERENT decision (it is matching work, D39); it is filed,
not smuggled in here. The remaining 2 are the FNCS bracket-winner markets,
which are legitimate 50-outcome championship futures and belong on a category
page with no event at all.

TWO MATCHES STAY UNRECORDED and this is said out loud rather than papered over:
G2 Esports v Paper Rex (2026-03-27 20:00) and the 3/28 Paper Rex v NRG row's
sibling have no clean event, and only the latter has a row whose provenance
identifies it. Inventing the other from a market name would be a guess.

------------------------------------------------------------------------------
D51 — BACKUP FIRST, ONE-COMMAND RESTORE
------------------------------------------------------------------------------

    bak_2993_bracket_events   full event rows (to_jsonb) + the lma rows
    bak_2993_market_links     (market_id, old event_id) for all 32

Undo:  python3 scripts/restore_2993_bracket_events.py --apply

USAGE
    python3 scripts/repair_2993_bracket_events.py                 # dry run
    python3 scripts/repair_2993_bracket_events.py --backup        # top up backup
    python3 scripts/repair_2993_bracket_events.py --backup --apply
"""

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# The fix itself. Imported, never restated — the repair's population IS the set
# the shipped guard refuses, so the two cannot drift apart.
from app.utils.prediction_market_matching import (  # noqa: E402
    _TOURNAMENT_STAGE_RE,
    bracket_refusal_reason,
    extract_matchup,
)

BAK_EVENTS = "bak_2993_bracket_events"
BAK_LINKS = "bak_2993_market_links"

# Postgres ARE understands `(?:`, but SQLAlchemy `text()` reads the `:` that
# follows as a bind parameter (gotcha #45). The pattern travels as a VALUE, and
# the groups are made capturing so the two engines match the same strings.
STAGE_RE_SQL = _TOURNAMENT_STAGE_RE.pattern.replace("(?:", "(")

# A parse-cut name is only reconstructible when the market name still carries
# the matchup the cut threw away: "…(Playoffs: Playoffs): Paper Rex vs. NRG Map 1".
_TAIL_RE = re.compile(r"\):\s*(.+?)(?:\s+Map\s+\d+)?\s*$", re.IGNORECASE)

# Sanity floor. A repair that finds nothing and reports success is the worst
# outcome there is (gotcha #53 — an empty result is a response shape, not an
# absence).
MIN_EXPECTED_POPULATION = 10

# How far from a bogus row's commence_time a clean counterpart may sit. The
# markets carry the same commence as the events they name, so this is slack,
# not a search: a wider net pairs teams that played twice in a weekend.
_WINDOW = timedelta(hours=6)

# The pre-registered disposition, measured against production 2026-09-04.
# `--apply` refuses unless the live plan matches, so this docstring's claims and
# the dyno's result cannot drift apart unnoticed. `matches_without_counterpart`
# is registered deliberately even though nothing gates on its VALUE being
# comfortable: it is the number the delete branch is justified by.
EXPECTED = {
    "population": 17,
    "rename": 1,
    "delete": 16,
    "markets_unlinked": 32,
    "lma_deleted": 1,
    "matches_without_counterpart": 2,
}


def _session_factory():
    """The app's real async session factory.

    Behind a named function so a test can substitute it AND prove the real one
    resolves: #2947's repair shipped importing a module that has never existed
    and died before planning a row while every unit test passed (CERT-903). An
    entrypoint that dies on import is not a repair, it is a file.
    """
    from app.services.database import async_session_maker

    return async_session_maker


def disposition_drift(measured: dict) -> dict:
    """Buckets that disagree with the pre-registered disposition."""
    return {
        k: (EXPECTED[k], v)
        for k, v in measured.items()
        if k in EXPECTED and EXPECTED[k] != v
    }


def reconstruct_matchup(market_name: str):
    """The real (home, away) a cut market name still carries, or None.

    "VALORANT Masters - Masters Santiago (Playoffs: Playoffs): Paper Rex vs. NRG Map 1"
        → ("Paper Rex", "NRG")

    Returns None when the tail is not itself a clean matchup — a reconstruction
    that has to guess is not a reconstruction.
    """
    tail = _TAIL_RE.search(market_name or "")
    if not tail:
        return None
    result = extract_matchup(tail.group(1))
    if not result or not result.team_a or not result.team_b:
        return None
    if bracket_refusal_reason(result.team_a, result.team_b):
        return None  # the tail is another bracket, not a matchup
    return result.team_a, result.team_b


async def _clean_counterpart(session, home, away, commence, self_id):
    """A real event for this matchup, in either orientation, or None."""
    from sqlalchemy import text

    row = (
        await session.execute(
            text(
                "SELECT id FROM events WHERE id <> :self "
                "AND commence_time BETWEEN :lo AND :hi "
                "AND ((lower(home_team_name) = lower(:h) "
                "      AND lower(away_team_name) = lower(:a)) "
                "  OR (lower(home_team_name) = lower(:a) "
                "      AND lower(away_team_name) = lower(:h))) "
                "ORDER BY id LIMIT 1"
            ),
            {
                "self": self_id,
                "h": home,
                "a": away,
                "lo": commence - _WINDOW,
                "hi": commence + _WINDOW,
            },
        )
    ).first()
    return row[0] if row else None


async def build_plan(session):
    """Classify every event the shipped guard would refuse today."""
    from sqlalchemy import text

    rows = (
        await session.execute(
            text(
                "SELECT e.id, e.home_team_name, e.away_team_name, e.commence_time, "
                "       e.external_id, e.status "
                "FROM events e WHERE "
                "  (length(e.home_team_name) - length(replace(e.home_team_name,'(',''))) "
                "  <> (length(e.home_team_name) - length(replace(e.home_team_name,')',''))) "
                "  OR (length(e.away_team_name) - length(replace(e.away_team_name,'(',''))) "
                "  <> (length(e.away_team_name) - length(replace(e.away_team_name,')',''))) "
                "  OR e.home_team_name ~* :stage_re OR e.away_team_name ~* :stage_re "
                "ORDER BY e.id"
            ),
            {"stage_re": STAGE_RE_SQL},
        )
    ).all()

    plan = []
    for event_id, home, away, commence, external_id, status in rows:
        # The SQL above is only a PREFILTER. The shipped predicate decides.
        reason = bracket_refusal_reason(home or "", away or "")
        if not reason:
            continue

        market_ids = (
            await session.execute(
                text("SELECT id FROM futures_markets WHERE event_id = :eid ORDER BY id"),
                {"eid": event_id},
            )
        ).scalars().all()

        entry = {
            "id": event_id,
            "old_home": home,
            "old_away": away,
            "status": status,
            "reason": reason,
            "market_ids": list(market_ids),
            "action": "delete",
            "new_home": None,
            "new_away": None,
            "counterpart": None,
        }

        # RENAME is earned by provenance, never by resemblance: the event's own
        # external_id must name a market whose title still carries the matchup.
        if external_id and external_id.startswith("pm_kalshi_"):
            market_name = (
                await session.execute(
                    text(
                        "SELECT name FROM futures_markets "
                        "WHERE source = 'kalshi' AND external_id = :mid"
                    ),
                    {"mid": external_id[len("pm_kalshi_"):]},
                )
            ).scalar()
            recovered = reconstruct_matchup(market_name or "")
            if recovered:
                counterpart = await _clean_counterpart(
                    session, recovered[0], recovered[1], commence, event_id
                )
                entry["counterpart"] = counterpart
                if counterpart is None:
                    entry["action"] = "rename"
                    entry["new_home"], entry["new_away"] = recovered

        plan.append(entry)
    return plan


async def count_matches_without_counterpart(session, plan):
    """How many real matches behind the unlinked markets have no clean event.

    The number the DELETE branch is justified by, so it is measured rather than
    asserted. A match is counted once, by (home, away, commence).
    """
    from sqlalchemy import text

    market_ids = [mid for entry in plan for mid in entry["market_ids"]]
    if not market_ids:
        return 0

    rows = (
        await session.execute(
            text(
                "SELECT name, commence_time FROM futures_markets "
                "WHERE id = ANY(:ids)"
            ),
            {"ids": market_ids},
        )
    ).all()

    seen, missing = set(), set()
    for name, commence in rows:
        recovered = reconstruct_matchup(name or "")
        if not recovered or commence is None:
            continue
        key = (recovered[0].lower(), recovered[1].lower(), commence)
        if key in seen:
            continue
        seen.add(key)
        if await _clean_counterpart(
            session, recovered[0], recovered[1], commence, -1
        ) is None:
            missing.add(key)
    return len(missing)


async def ensure_backup(session, plan):
    """Create the D51 backup tables and top them up. Returns rows banked."""
    from sqlalchemy import text

    await session.execute(
        text(
            f"CREATE TABLE IF NOT EXISTS {BAK_EVENTS} ("
            "  event_id bigint PRIMARY KEY,"
            "  action text NOT NULL,"
            "  event_row jsonb NOT NULL,"
            "  lma_rows jsonb NOT NULL DEFAULT '[]'::jsonb,"
            "  anchor_rows jsonb NOT NULL DEFAULT '[]'::jsonb,"
            # What the repair WROTE, so the undo can tell "still as I left it"
            # from "something else has moved this on since".
            "  applied_names jsonb,"
            "  banked_at timestamptz NOT NULL DEFAULT now())"
        )
    )
    await session.execute(
        text(
            f"CREATE TABLE IF NOT EXISTS {BAK_LINKS} ("
            "  market_id bigint PRIMARY KEY,"
            "  old_event_id bigint NOT NULL,"
            "  banked_at timestamptz NOT NULL DEFAULT now())"
        )
    )

    for entry in plan:
        await session.execute(
            text(
                f"INSERT INTO {BAK_EVENTS} "
                "(event_id, action, event_row, lma_rows, anchor_rows, applied_names) "
                "SELECT e.id, :action, to_jsonb(e), "
                "  COALESCE((SELECT jsonb_agg(to_jsonb(l)) FROM line_movement_analyses l "
                "            WHERE l.event_id = e.id), '[]'::jsonb), "
                "  COALESCE((SELECT jsonb_agg(to_jsonb(a)) FROM event_provider_anchors a "
                "            WHERE a.event_id = e.id), '[]'::jsonb), "
                "  CAST(:applied AS jsonb) "
                "FROM events e WHERE e.id = :eid "
                "ON CONFLICT (event_id) DO NOTHING"
            ),
            {
                "eid": entry["id"],
                "action": entry["action"],
                "applied": (
                    json.dumps(
                        {"home": entry["new_home"], "away": entry["new_away"]}
                    )
                    if entry["action"] == "rename"
                    else None
                ),
            },
        )
        for market_id in entry["market_ids"]:
            await session.execute(
                text(
                    f"INSERT INTO {BAK_LINKS} (market_id, old_event_id) "
                    "VALUES (:mid, :eid) ON CONFLICT (market_id) DO NOTHING"
                ),
                {"mid": market_id, "eid": entry["id"]},
            )
    await session.commit()

    banked = (
        await session.execute(text(f"SELECT count(*) FROM {BAK_EVENTS}"))
    ).scalar()
    banked_links = (
        await session.execute(text(f"SELECT count(*) FROM {BAK_LINKS}"))
    ).scalar()
    return banked, banked_links


async def apply_plan(session, plan):
    """Unlink, rename, delete. Returns what was actually written."""
    from sqlalchemy import text

    written = {"renamed": 0, "deleted": 0, "markets_unlinked": 0, "lma_deleted": 0}

    for entry in plan:
        if entry["market_ids"]:
            result = await session.execute(
                text(
                    "UPDATE futures_markets SET event_id = NULL "
                    "WHERE id = ANY(:ids) AND event_id = :eid"
                ),
                {"ids": entry["market_ids"], "eid": entry["id"]},
            )
            written["markets_unlinked"] += result.rowcount or 0

        if entry["action"] == "rename":
            result = await session.execute(
                text(
                    "UPDATE events SET home_team_name = :h, away_team_name = :a "
                    "WHERE id = :eid"
                ),
                {"h": entry["new_home"], "a": entry["new_away"], "eid": entry["id"]},
            )
            written["renamed"] += result.rowcount or 0
        else:
            result = await session.execute(
                text("DELETE FROM line_movement_analyses WHERE event_id = :eid"),
                {"eid": entry["id"]},
            )
            written["lma_deleted"] += result.rowcount or 0
            result = await session.execute(
                text("DELETE FROM events WHERE id = :eid"), {"eid": entry["id"]}
            )
            written["deleted"] += result.rowcount or 0
        await session.commit()

    return written


async def run(args):
    from sqlalchemy import text

    session_maker = _session_factory()
    async with session_maker() as session:
        plan = await build_plan(session)
        without_counterpart = await count_matches_without_counterpart(session, plan)

        measured = {
            "population": len(plan),
            "rename": sum(1 for e in plan if e["action"] == "rename"),
            "delete": sum(1 for e in plan if e["action"] == "delete"),
            "markets_unlinked": sum(len(e["market_ids"]) for e in plan),
            "lma_deleted": (
                await session.execute(
                    text(
                        "SELECT count(*) FROM line_movement_analyses "
                        "WHERE event_id = ANY(:ids)"
                    ),
                    {"ids": [e["id"] for e in plan if e["action"] == "delete"]},
                )
            ).scalar() or 0,
            "matches_without_counterpart": without_counterpart,
        }

        print(json.dumps({"measured": measured}, indent=2))
        for entry in plan:
            print(
                f"  {entry['id']}  {entry['action']:6}  "
                f"{entry['old_home']!r} / {entry['old_away']!r}"
                + (
                    f"  →  {entry['new_home']!r} / {entry['new_away']!r}"
                    if entry["action"] == "rename"
                    else (
                        f"  (counterpart {entry['counterpart']})"
                        if entry["counterpart"]
                        else ""
                    )
                )
                + (f"  [{len(entry['market_ids'])} markets]" if entry["market_ids"] else "")
            )

        if len(plan) < MIN_EXPECTED_POPULATION and not args.allow_small:
            print(
                f"REFUSING: population {len(plan)} is under the floor "
                f"{MIN_EXPECTED_POPULATION} — the predicate probably broke. "
                "Pass --allow-small if the work really is done."
            )
            return 2

        drift = disposition_drift(measured)
        if drift and not args.allow_drift:
            print(f"REFUSING: disposition drift {drift}")
            return 3

        if args.backup:
            banked, banked_links = await ensure_backup(session, plan)
            print(f"BACKUP: {banked} event rows, {banked_links} market links banked")

        if not args.apply:
            print("DRY RUN — nothing written. Re-run with --backup --apply.")
            return 0

        if not args.backup:
            print("REFUSING: --apply requires --backup in the same run (D51)")
            return 4

        written = await apply_plan(session, plan)
        print(json.dumps({"written": written}, indent=2))

        # Verify by SIDE EFFECT, never by exit code (a detached run's 0 is not a
        # result). Re-derive the population from scratch: it must be empty.
        residue = await build_plan(session)
        print(json.dumps({"residue_after": len(residue)}, indent=2))
        return 0 if not residue else 5


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--backup", action="store_true", help="top up the D51 backup tables")
    p.add_argument("--apply", action="store_true", help="write the repair (needs --backup)")
    p.add_argument("--allow-small", action="store_true", help="bypass the population floor")
    p.add_argument("--allow-drift", action="store_true", help="bypass the disposition gate")
    sys.exit(asyncio.run(run(p.parse_args())))


if __name__ == "__main__":
    main()
