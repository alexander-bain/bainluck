"""#2869: two real NFL games do not exist, because their rows say they already finished.

Two regular-season fixtures carry a `commence_time` in the August preseason
window, `status='closed'` and a `completed_at` — with **no score**. So the site
shows them as settled-with-a-blank-result at a date they were never played on,
and their real Week 6 / Week 17 fixtures have no row at all. Polymarket already
lists one of them (`'Chargers vs. Chiefs'`, `event_id = NULL`) and the matcher
fails on it every pass, because the event it needs does not exist at the right
date (standing notice 27, the marquee axiom).

Measured by authority/153 and re-derived here independently; see #2869.

═══ WHY THE COHORT IS A SIGNATURE AND NOT TWO IDS ═══

The cohort SQL selects NFL rows that **refute themselves**: `status='closed'`
with both scores NULL. A finished football game with no score is decidably
wrong from the row alone — no ground truth needed to know something is broken.

Two ids would have been shorter and worse. A literal pair cannot find a third
occurrence, and it cannot notice that the two it names have since been fixed by
someone else; it would happily re-apply to whatever those ids point at. The
signature re-asks the question every run.

It is deliberately NOT "every NFL row whose date disagrees with ESPN". That
cohort is enormous and mostly benign (ESPN moves kickoffs), and it would put
this script in the business of re-timing the schedule. The defect here is the
false COMPLETION; the wrong date is its passenger.

Today the signature yields exactly 2 rows. The third NFL `status='closed'` row
(`15292757`, Titans/Bears) carries a real 15-24 score and is correctly excluded
— which is the check that the signature discriminates rather than sweeping.

═══ WHY ESPN DECIDES THE NEW DATE, AT RUN TIME ═══

The corrected kickoffs are not constants in this file. Each row's `espn_id` is
dereferenced against ESPN's summary API when the script runs, and the row is
repaired only if ESPN says all of:

  * `season.type == 2` — a REGULAR-season game. A preseason id would mean the
    row is something else entirely and the date swap would be wrong.
  * `STATUS_SCHEDULED` — the game has not been played. If ESPN says it finished,
    our `closed` was right and the scores are what is missing; that is a
    different repair and this script must not touch it.
  * neither competitor carries a score.
  * both team names match the row's own `home_team_name` / `away_team_name`.

The last one is not ceremony. An id from the wrong provider resolves to a
different entity and returns HTTP 200, not an error — the failure mode is a
confident repair that points a row at someone else's game. Matching the names
we already hold is what makes the dereference falsifiable.

A row ESPN refuses is REFUSED and reported, never written and never silently
dropped. A run that confirms nothing says so loudly: a zero-yield pass is
otherwise indistinguishable from a clean one (gotcha #53).

═══ WHAT IS WRITTEN, AND WHY EXACTLY THESE FOUR FIELDS ═══

Measured against the 268 future NFL fixtures on production (2026-09-12):

    with box_score_data   0 / 268
    with completed_at     0 / 268
    with win_prob_sources 267 / 268

So the target state is not invented, it is the norm this row departed from:

    commence_time  -> ESPN's kickoff
    status         -> 'scheduled'
    completed_at   -> NULL
    box_score_data -> NULL

`win_probability_sources` is deliberately LEFT ALONE. It is present on 267 of
268 healthy scheduled fixtures, so clearing it would move the row further from
the norm, not closer. Both rows hold `{"betting_book_count": 2}`.

`completed_at` is not optional housekeeping. Gotcha #46 makes
`completed_at >= commence_time` an invariant whose violation means a
cross-event data merge and is a matching-layer P1. Moving `commence_time`
forward to October while leaving a `completed_at` in August would CREATE that
violation — the repair would file its own P1. Clearing it is what keeps the
two-field fix from being a three-field bug.

`box_score_data` on both rows is `{"error": "not_available", "source": "espn"}`
— a failed fetch, which is the fingerprint of the bad write rather than data in
its own right: something believed the game had ended and went looking for a box
score that could not exist yet.

═══ THE UNDO (D51(b)) ═══

`--backup` stages a full-row copy in `bak_2869_events` plus an id manifest in
`bak_2869_repair_manifest`, and `--apply` REFUSES unless every planned row is
covered. Two tables, not one: a full-row backup records what a row WAS, but
cannot record that THIS script is what moved it, so a restore could not tell a
row this script wrote from one a poller has legitimately re-timed since. The
manifest is what makes the undo attributable (the CERT-2439 lesson, inherited
via #5221 and its own #5246 repair).

The one-command restore is printed by `--apply` and is exactly:

    UPDATE events e SET commence_time = b.commence_time, status = b.status,
           completed_at = b.completed_at, box_score_data = b.box_score_data
      FROM bak_2869_events b
     WHERE e.id = b.id AND e.id IN (SELECT event_id FROM bak_2869_repair_manifest);

Usage:

    python3 scripts/repair_2869_nfl_backwards_stamped_fixtures.py
    python3 scripts/repair_2869_nfl_backwards_stamped_fixtures.py --backup
    python3 scripts/repair_2869_nfl_backwards_stamped_fixtures.py --backup --apply
"""

import argparse
import asyncio
import os
import sys
from typing import NamedTuple, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BAK_TABLE = "bak_2869_events"
MANIFEST_TABLE = "bak_2869_repair_manifest"

ESPN_SUMMARY = (
    "https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary?event={espn_id}"
)

#: ESPN's `season.type` for the regular season. 1 is preseason, 3 postseason.
REGULAR_SEASON = 2

#: The self-refuting signature: a finished game with no score. `sports.key` is
#: joined rather than a literal `sport_id`, because the integer is a local
#: surrogate and the key is the name the rest of the system uses.
SCAN_SQL = """
    SELECT e.id, e.home_team_name, e.away_team_name, e.commence_time,
           e.status, e.completed_at, e.espn_id
      FROM events e
      JOIN sports s ON s.id = e.sport_id
     WHERE s.key = 'americanfootball_nfl'
       AND e.status = 'closed'
       AND e.home_score IS NULL
       AND e.away_score IS NULL
       AND e.espn_id IS NOT NULL
     ORDER BY e.commence_time
"""


class Verdict(NamedTuple):
    event_id: int
    ok: bool
    reason: str
    new_commence: Optional[str] = None


def _norm(name: str) -> str:
    return "".join(ch for ch in (name or "").lower() if ch.isalnum())


def judge(row, payload) -> Verdict:
    """Decide whether ESPN confirms this row is an unplayed regular-season game.

    Pure, so the whole refusal table is testable without a network.
    """
    event_id = row["id"]

    if not payload:
        return Verdict(event_id, False, "ESPN returned nothing")

    header = payload.get("header") or {}
    season = header.get("season") or {}
    if season.get("type") != REGULAR_SEASON:
        return Verdict(
            event_id, False, f"ESPN season.type={season.get('type')!r}, not regular"
        )

    comps = header.get("competitions") or []
    if not comps:
        return Verdict(event_id, False, "ESPN payload carries no competition")
    comp = comps[0]

    state = ((comp.get("status") or {}).get("type") or {}).get("name")
    if state != "STATUS_SCHEDULED":
        return Verdict(
            event_id, False, f"ESPN status={state!r} — the game is not unplayed"
        )

    competitors = comp.get("competitors") or []
    if any(c.get("score") not in (None, "") for c in competitors):
        return Verdict(event_id, False, "ESPN carries a score — not an unplayed game")

    sides = {
        c.get("homeAway"): ((c.get("team") or {}).get("displayName") or "")
        for c in competitors
    }
    # An id from the WRONG provider resolves to a different entity and returns
    # 200. Matching the names we already hold is what makes this falsifiable.
    for side, ours in (("home", row["home_team_name"]), ("away", row["away_team_name"])):
        theirs = sides.get(side)
        if theirs is None:
            return Verdict(event_id, False, f"ESPN payload has no {side} competitor")
        if _norm(theirs) != _norm(ours):
            return Verdict(
                event_id,
                False,
                f"{side} team disagrees: ours {ours!r} vs ESPN {theirs!r}",
            )

    date = comp.get("date")
    if not date:
        return Verdict(event_id, False, "ESPN competition carries no date")

    return Verdict(event_id, True, "confirmed unplayed regular-season game", date)


async def fetch_espn(espn_id: str) -> Optional[dict]:
    import httpx

    url = ESPN_SUMMARY.format(espn_id=espn_id)
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return None
            return resp.json()
    except Exception:
        return None


async def stage_backup(s, event_ids) -> None:
    from sqlalchemy import text

    # LIKE copies columns and types but NOT the foreign keys — a backup that
    # cascaded with its source would be no backup at all.
    await s.execute(
        text(f"CREATE TABLE IF NOT EXISTS {BAK_TABLE} (LIKE events)")
    )
    await s.execute(
        text(
            f"CREATE TABLE IF NOT EXISTS {MANIFEST_TABLE} ("
            " event_id INTEGER NOT NULL,"
            " repaired_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
    )
    for event_id in event_ids:
        await s.execute(
            text(
                f"INSERT INTO {BAK_TABLE} SELECT * FROM events WHERE id = :i"
                f" AND NOT EXISTS (SELECT 1 FROM {BAK_TABLE} WHERE id = :i)"
            ),
            {"i": event_id},
        )
    await s.commit()


async def backup_covers(s, event_ids) -> bool:
    """The D51 gate: refuse `--apply` unless every planned row has an undo."""
    from sqlalchemy import text

    if not event_ids:
        return False
    rows = (
        await s.execute(
            text(f"SELECT id FROM {BAK_TABLE} WHERE id = ANY(:ids)"),
            {"ids": list(event_ids)},
        )
    ).fetchall()
    return {r[0] for r in rows} == set(event_ids)


async def run(args) -> None:
    from sqlalchemy import text

    from app.tasks.base import get_task_session

    async with get_task_session() as s:
        rows = [
            dict(r._mapping) for r in (await s.execute(text(SCAN_SQL))).fetchall()
        ]
        print(f"candidates : {len(rows)} NFL row(s) closed with no score")
        for r in rows:
            print(
                f"  {r['id']}  {r['away_team_name']} @ {r['home_team_name']}"
                f"  ours={r['commence_time']}  espn_id={r['espn_id']}"
            )

        if not rows:
            print(
                "\n⚠️  ZERO CANDIDATES — the signature matched nothing. That is a "
                "finding about the cohort SQL or an already-completed repair, "
                "not a clean run."
            )
            return

        print()
        confirmed, refused = [], []
        for r in rows:
            verdict = judge(r, await fetch_espn(r["espn_id"]))
            (confirmed if verdict.ok else refused).append((r, verdict))
            mark = "CONFIRMED" if verdict.ok else "REFUSED  "
            extra = f" -> {verdict.new_commence}" if verdict.new_commence else ""
            print(f"  {mark} {r['id']}  {verdict.reason}{extra}")

        print(f"\nESPN confirms {len(confirmed)} of {len(rows)}; refuses {len(refused)}.")
        if not confirmed:
            print(
                "⚠️  ZERO YIELD — ESPN confirmed none of the candidates. That is a "
                "finding about the rows, not an idle run."
            )
            return

        if not args.backup and not args.apply:
            print("\nplan only — pass --backup to stage an undo, then --apply.")
            return

        event_ids = [r["id"] for r, _ in confirmed]

        if args.backup:
            await stage_backup(s, event_ids)
            print(f"\nbackup staged in {BAK_TABLE} ({len(event_ids)} row(s)).")

        if not await backup_covers(s, event_ids):
            print(
                f"\nREFUSING --apply: {BAK_TABLE} does not cover every planned row. "
                "Re-run with --backup."
            )
            return

        if not args.apply:
            print("\nbackup staged — re-run with --apply to write.")
            return

        for r, verdict in confirmed:
            await s.execute(
                text(
                    "UPDATE events SET commence_time = CAST(:c AS timestamptz),"
                    " status = 'scheduled', completed_at = NULL,"
                    " box_score_data = NULL WHERE id = :i"
                ),
                {"c": verdict.new_commence, "i": r["id"]},
            )
            await s.execute(
                text(f"INSERT INTO {MANIFEST_TABLE} (event_id) VALUES (:i)"),
                {"i": r["id"]},
            )
        await s.commit()

        print(f"\napplied to {len(confirmed)} row(s). Undo, one command:\n")
        print(
            f"  UPDATE events e SET commence_time = b.commence_time,"
            f" status = b.status, completed_at = b.completed_at,"
            f" box_score_data = b.box_score_data\n"
            f"    FROM {BAK_TABLE} b\n"
            f"   WHERE e.id = b.id AND e.id IN"
            f" (SELECT event_id FROM {MANIFEST_TABLE});"
        )


def main():
    p = argparse.ArgumentParser(description="#2869 NFL backwards-stamped fixtures")
    p.add_argument("--backup", action="store_true", help="stage the undo tables")
    p.add_argument("--apply", action="store_true", help="write (requires a backup)")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="print the plan and exit without touching the database",
    )
    args = p.parse_args()

    if args.dry_run:
        # The notice-10 SCRIPTS/LAUNCHER proof line: exercises argument parsing,
        # the cohort SQL and the pure verdict logic with no database and no
        # network, so it is safe to quote on any sha.
        print("#2869 repair — dry run, no database and no network.")
        print(f"backup table   : {BAK_TABLE}")
        print(f"manifest table : {MANIFEST_TABLE}")
        print("cohort SQL     :")
        print(SCAN_SQL.strip())
        specimen = {
            "id": 0,
            "home_team_name": "Kansas City Chiefs",
            "away_team_name": "Los Angeles Chargers",
        }
        good = {
            "header": {
                "season": {"type": REGULAR_SEASON},
                "competitions": [
                    {
                        "date": "2026-10-18T20:25Z",
                        "status": {"type": {"name": "STATUS_SCHEDULED"}},
                        "competitors": [
                            {
                                "homeAway": "home",
                                "team": {"displayName": "Kansas City Chiefs"},
                                "score": None,
                            },
                            {
                                "homeAway": "away",
                                "team": {"displayName": "Los Angeles Chargers"},
                                "score": None,
                            },
                        ],
                    }
                ],
            }
        }
        print(f"\nself-check confirm : {judge(specimen, good)}")
        print(f"self-check refuse  : {judge(specimen, None)}")
        return

    asyncio.run(run(args))


if __name__ == "__main__":
    main()
