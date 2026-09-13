"""#5821 — collapse an EXISTING split Polymarket container family onto one event.

------------------------------------------------------------------------------
WHAT A READER SEES, AND WHY THE DATE REPAIR ALONE IS NOT ENOUGH
------------------------------------------------------------------------------
Polymarket publishes one fixture as TWO Gamma containers — the base (the 3-way
moneyline) and a companion carrying the derivatives — so we hold two events for
one match. `repair_5821_polymarket_listing_dates.py` corrects both rows' clocks
to the venue kickoff, and the twin fold then serves ONE card. That is the ship
#5821 names, and it works.

It is also, on its own, a REGRESSION, and this script is why. Measured on
production 2026-09-13 11:2xZ, on the issue's own specimen:

    15311506  the base       1 market  (the moneyline)   sources: polymarket
    15311503  the companion 16 markets (the derivatives) sources: none

`fold_twin_events` elects its survivor on
`(score, espn_id, external_id, source_count, -id)` and unions only
`win_probability_sources`. The loser's LINKED MARKETS are not moved — and
`/api/events/{id}/game-markets` loads props strictly by `event_id`. So the base
wins on its one source, and the served payloads are:

    15311506 (survives)  totals 0  spreads 0  periods 0
    15311503 (dropped)   totals 6  spreads 4  periods 3

One card, zero props. Today the reader can at least reach those props on the
duplicate card; after a date-only repair they sit on an event nothing serves.

    125  future split container families
    119  lose their PROPS to the fold  (597 tier-5 markets)
      6  carry no props on either side
      0  keep everything

    603  Polymarket markets this repair re-points — every market on the losing
         row, not only the props: in the 29 families where the COMPANION wins
         the election it is the base's moneyline that would otherwise strand.
     96  of the 125 are won by the base, 29 by the companion.

🔴 BOTH REFUSALS BELOW ARE INERT ON TODAY'S POPULATION, and that is said here
rather than left for a reader to assume otherwise: removing `n_bases = 1` AND
the fold-identity equality leaves the count at 125 — measured, not reasoned.
They exclude nothing today. They are kept because this repair MOVES links that
already have a home, so the day the venue reuses a base title at one kickoff, or
two rows share a title without sharing a fixture, the honest answer is to refuse
rather than to pick.

So the date repair is the SERVING dedupe and this is the LINKED-ROW repair that
must precede it. Run this first, then the dates: re-point the family's markets
onto the row the fold is going to elect, and the row it hides then carries
nothing. The end state is the one the PREVENTION already produces for every
family minted from now on (PR #5864, `_polymarket_container_sibling_event_id`) —
one event holding the moneyline and the derivatives together.

------------------------------------------------------------------------------
THE SURVIVOR IS NOT THIS SCRIPT'S CHOICE
------------------------------------------------------------------------------
It is `twin_identity_rank`, imported from the serving layer rather than
re-spelled here. A repair that picked its own winner would move markets onto the
row the fold then hides, which is the defect with extra steps — and the two
would drift the first time the election changes. The rank reads
`win_probability_sources`, `espn_id`, `external_id` and the row id; this script
writes none of them, so the election it computes is the one the fold computes.

------------------------------------------------------------------------------
MEMBERSHIP — THE PREVENTION'S TWO SIGNALS, PLUS THE FOLD'S OWN IDENTITY
------------------------------------------------------------------------------
A family is confirmed, never guessed (notice 40):

1. **The title**, exactly. The companion's name is the base name plus a suffix
   the venue composes, so `_strip_more_markets` recovers the base by string
   equality. The suffix list is IMPORTED from the matcher, so a suffix added
   there cannot leave this repair reading a base name nothing looks up.
2. **`venue_game_start`**, identical across the pair — the kickoff the venue
   publishes, which is the signal the prevention already trusts.
3. **The fold's own identity**, additionally: same `sport_id` and the same two
   team names. This is the guard the prevention does not need and a repair does.
   The prevention decides where a NEW market attaches; this MOVES markets that
   already have a home, so it refuses unless the two rows are the pair the fold
   would itself collapse once their clocks agree.

Refused rather than guessed at: a base title that resolves to more than one base
event at the same kickoff (`n_bases = 1`), and any family whose kickoff is in the
PAST. Past families are excluded for the reason the date repair excludes them —
settled rows feed settlement and calibration windows, and the reader-visible
defect is not there.

------------------------------------------------------------------------------
WHAT THIS DOES NOT DO
------------------------------------------------------------------------------
It does not retire, merge or delete the loser event. After the move that row
holds no Polymarket markets, and once the date repair lands its clock the fold
hides it. Retiring an event is a wider blast radius than this ship needs, and an
empty hidden row costs a reader nothing.

It does not touch a market whose family is already collapsed — both sides on one
event is the outcome this makes the rule, and such a family is not in the
population at all. The script is therefore idempotent and re-runnable.

------------------------------------------------------------------------------
D51 — BACKUP FIRST, ONE-COMMAND RESTORE
------------------------------------------------------------------------------
`--backup` copies each in-scope market's CURRENT `event_id` into
`backup_5821_split_container_markets`, and `--apply` refuses unless every row it
is about to write is backed content-exact. The backup is also the RECEIPT: a
successful compare-and-set stamps `applied_event_id` in the same transaction, and
the undo reverts only stamped rows, by CAS against the value this run wrote.

The write gate is the sibling repair's `wrong_app_refusal`, IMPORTED rather than
re-spelled — same producer task, same reason, one gate to keep honest.

    heroku run:detached -a bainluck-heavy -- \
        python3 scripts/repair_5821_split_container_markets.py            # dry run
    … --backup
    … --backup --apply
    UNDO: … python3 scripts/restore_5821_split_container_markets.py --apply

Refs #5821, #2693, #4457. Required repair `5821-EXISTING-SPLIT-CONTAINERS-COLLAPSE`.
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# …and this file's OWN directory, so the sibling import below resolves however
# the module is loaded — by `python3 scripts/repair_….py` (which puts `scripts/`
# on the path for free) or by path, which a guard test does and which would
# otherwise raise ImportError nowhere but CI.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

#: The write gate, imported rather than re-spelled. Same producer task, same
#: reason, one gate: `match_prediction_markets` is in HEAVY_TASKS, so the app
#: whose deployed code could put the defect back while we write is the app the
#: write must happen on.
from repair_5821_polymarket_listing_dates import (  # noqa: E402
    PRODUCER_APP,  # noqa: F401 — re-exported so the undo takes one gate, not two
    wrong_app_refusal,
)

#: Ceiling on the number of MARKETS one run may move. The measured population is
#: 603 markets across 125 families; a predicate that has gone wide should stop
#: and be looked at rather than re-point thousands of links.
MAX_MARKETS = 1500

#: THE POPULATION. One row per market that must move, with the family it belongs
#: to. Every clause is an exclusion with a reason:
#:
#:   `source = 'polymarket'`      only this venue publishes split containers
#:   `event_id IS NOT NULL`       an unlinked market is the PREVENTION's job, not
#:                                this one — it has no wrong home to move it out
#:                                of, and the matcher will attach it correctly
#:   `vgs > now()`                future fixtures only (see WHAT A READER SEES)
#:   `n_bases = 1`                the base title resolves to exactly ONE base
#:                                event at this kickoff; more than one is
#:                                ambiguous and is refused, never picked between
#:   `sport_id`/team equality     the two rows are the pair the fold would itself
#:                                collapse — see MEMBERSHIP
#:   `base_event <> cont_event`   already-collapsed families are not a defect
#:
#: The suffix alternation is built from the matcher's own tuple at import time,
#: never spelled here, so the two cannot drift.
_POPULATION_SQL_TEMPLATE = """
WITH containers AS (
    SELECT m.id                                            AS market_id,
           m.event_id                                      AS cont_event,
           regexp_replace(m.name, :suffix_re, '')          AS base_name,
           (m.market_metadata->>'venue_game_start')::timestamptz AS vgs
      FROM futures_markets m
     WHERE m.source = 'polymarket'
       AND m.event_id IS NOT NULL
       AND m.name ~ :suffix_re
       AND (m.market_metadata->>'venue_game_start')::timestamptz > now()
),
bases AS (
    SELECT DISTINCT
           m.event_id                                      AS base_event,
           m.name                                          AS base_name,
           (m.market_metadata->>'venue_game_start')::timestamptz AS vgs
      FROM futures_markets m
     WHERE m.source = 'polymarket'
       AND m.event_id IS NOT NULL
       AND (m.market_metadata->>'venue_game_start')::timestamptz > now()
),
families AS (
    SELECT c.base_name,
           c.vgs,
           c.cont_event,
           b.base_event,
           count(*) OVER (PARTITION BY c.base_name, c.vgs, c.cont_event) AS n_bases
      FROM containers c
      JOIN bases b
        ON b.base_name = c.base_name
       AND b.vgs       = c.vgs
       AND b.base_event <> c.cont_event
     GROUP BY c.base_name, c.vgs, c.cont_event, b.base_event
)
SELECT f.base_name,
       f.vgs,
       f.cont_event,
       f.base_event,
       ce.home_team_name AS cont_home, ce.away_team_name AS cont_away,
       be.home_team_name AS base_home, be.away_team_name AS base_away
  FROM families f
  JOIN events ce ON ce.id = f.cont_event
  JOIN events be ON be.id = f.base_event
 WHERE f.n_bases = 1
   AND ce.sport_id IS NOT DISTINCT FROM be.sport_id
   AND ce.home_team_name = be.home_team_name
   AND ce.away_team_name = be.away_team_name
 ORDER BY f.cont_event
"""


def suffix_regex() -> str:
    """The POSIX alternation matching every container suffix, from the matcher.

    Built from `_POLYMARKET_CONTAINER_SUFFIXES` at call time rather than written
    out, so a suffix added to the matcher is in scope here the same day. The
    literal is escaped: the suffixes contain no regex metacharacters today, and
    a future one that does must not quietly widen this population.
    """
    import re

    from app.tasks.prediction_market_matching import _POLYMARKET_CONTAINER_SUFFIXES

    return "(" + "|".join(re.escape(s) for s in _POLYMARKET_CONTAINER_SUFFIXES) + ")$"


def elect_survivor(container_event, base_event):
    """Which of the pair the SERVING fold will keep. Pure: no DB, no clock.

    `twin_identity_rank` is imported, not re-spelled: this repair must move
    markets ONTO the row the fold elects, and a second opinion here would move
    them onto the row it hides. Returns `(survivor, loser)`.
    """
    from app.utils.event_twin_fold import twin_identity_rank

    ranked = sorted(
        (container_event, base_event), key=twin_identity_rank, reverse=True
    )
    return ranked[0], ranked[1]


async def run(args):
    from sqlalchemy import text

    from app.tasks.base import get_task_session

    refusal = wrong_app_refusal(args)
    if refusal:
        print(refusal)
        return 2

    async with get_task_session() as s:
        families = (
            await s.execute(
                text(_POPULATION_SQL_TEMPLATE), {"suffix_re": suffix_regex()}
            )
        ).all()

        print("=== #5821 split Polymarket container families — population ===")
        if not families:
            print("Nothing to collapse — population is 0 (idempotent no-op).")
            return 0

        from app.models.models import Event, FuturesMarket
        from sqlalchemy import select

        # One plan per family: every Polymarket market on the LOSER moves to the
        # SURVIVOR. Read the two event rows in full, because the election reads
        # columns the population query has no business projecting.
        event_ids = sorted(
            {f.cont_event for f in families} | {f.base_event for f in families}
        )
        rows = (
            await s.execute(select(Event).where(Event.id.in_(event_ids)))
        ).scalars().all()
        by_id = {e.id: e for e in rows}

        moves = []  # (market_id, from_event, to_event)
        per_family = []
        for f in families:
            container, base = by_id.get(f.cont_event), by_id.get(f.base_event)
            if container is None or base is None:
                continue
            survivor, loser = elect_survivor(container, base)
            stranded = (
                await s.execute(
                    select(FuturesMarket.id).where(
                        FuturesMarket.source == "polymarket",
                        FuturesMarket.event_id == loser.id,
                    )
                )
            ).scalars().all()
            if not stranded:
                continue
            per_family.append((f.base_name, loser.id, survivor.id, len(stranded)))
            moves.extend((mid, loser.id, survivor.id) for mid in stranded)

        for name, loser, survivor, n in per_family[:40]:
            print(
                f"  {str(name)[:52]:<52} {n:>3} market(s)  {loser} -> {survivor}"
            )
        if len(per_family) > 40:
            print(
                f"  … and {len(per_family) - 40} more (this is a SAMPLE, not the set)"
            )
        print(
            f"  {len(per_family)} split families, {len(moves)} markets to re-point"
        )

        if len(moves) > MAX_MARKETS:
            print(
                f"\nREFUSING: {len(moves)} markets exceeds the {MAX_MARKETS} "
                "ceiling. Measured population is 603; a jump this size means the "
                "population predicate is not selecting what this repair believes."
            )
            return 2

        market_ids = [m[0] for m in moves]

        if args.backup:
            print("\n=== backup ===")
            await s.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS backup_5821_split_container_markets ("
                    "market_id bigint PRIMARY KEY, "
                    "event_id bigint, "
                    # The RECEIPT half: written by --apply, never by --backup.
                    "applied_event_id bigint)"
                )
            )
            await s.execute(
                text(
                    # DO UPDATE for the sibling script's reason: a second backup
                    # after another writer moved a link must REFRESH it, clearing
                    # the receipt, or the undo restores a value we never wrote over.
                    "INSERT INTO backup_5821_split_container_markets "
                    "(market_id, event_id) "
                    "SELECT id, event_id FROM futures_markets "
                    "WHERE id = ANY(:ids) "
                    "ON CONFLICT (market_id) DO UPDATE SET "
                    "event_id = EXCLUDED.event_id, "
                    "applied_event_id = NULL"
                ),
                {"ids": market_ids},
            )
            await s.commit()
            print(f"  copied {len(market_ids)} market links")

        # Ask whether the relation exists before asking it a question — the
        # sibling's `5821-FIRST-DRY-RUN-WITHOUT-BACKUP-TABLE`, which this script
        # would otherwise reproduce on its own documented step 0.
        backup_exists = (
            await s.execute(
                text(
                    "SELECT to_regclass("
                    "'public.backup_5821_split_container_markets') IS NOT NULL"
                )
            )
        ).scalar()

        if not backup_exists:
            stale = len(market_ids)
            print(
                "\n=== backup reconciliation === no backup table yet — every one "
                f"of the {stale} in-scope markets is unbacked (this is the "
                "expected reading on a first dry run)"
            )
        else:
            stale = (
                await s.execute(
                    text(
                        "SELECT count(*) FROM futures_markets m "
                        "WHERE m.id = ANY(:ids) AND NOT EXISTS ("
                        "SELECT 1 FROM backup_5821_split_container_markets b "
                        "WHERE b.market_id = m.id "
                        "AND b.event_id IS NOT DISTINCT FROM m.event_id)"
                    ),
                    {"ids": market_ids},
                )
            ).scalar()
            print(
                f"\n=== backup reconciliation (content-exact) === "
                f"unbacked-or-stale={stale}"
            )

        if not args.apply:
            print(
                f"\nDRY RUN — nothing written. Would re-point {len(moves)} "
                f"markets across {len(per_family)} families onto the event the "
                "twin fold elects, so the row it hides carries nothing."
            )
            return 0

        if stale:
            print(
                "\nREFUSING --apply: the backup does not match the rows about to "
                "be written — either a market is unbacked, or its link MOVED "
                "since the backup was taken and the undo would restore a value "
                "that was never overwritten. Re-run --backup."
            )
            return 2

        written = 0
        skipped = []
        for market_id, from_event, to_event in moves:
            result = await s.execute(
                text(
                    "UPDATE futures_markets SET event_id = :to_event "
                    "WHERE id = :id AND event_id = :from_event"
                ),
                {"to_event": to_event, "id": market_id, "from_event": from_event},
            )
            if result.rowcount:
                written += 1
                await s.execute(
                    text(
                        "UPDATE backup_5821_split_container_markets "
                        "SET applied_event_id = :to_event WHERE market_id = :id"
                    ),
                    {"to_event": to_event, "id": market_id},
                )
            else:
                skipped.append(market_id)
        await s.commit()

        # Counted on the LANDING, not on the plan — the sibling's
        # `5821-REPORT-ACTUAL-LIFTED-COUNT`, which is the same trap here: a
        # market whose compare-and-set lost a race is still on the hidden row.
        print(f"\nAPPLIED: re-pointed {written} of {len(moves)} markets.")
        if skipped:
            print(
                f"  SKIPPED {len(skipped)} whose link moved between the read and "
                f"the write: {skipped[:20]}"
            )
        print(
            "NEXT: run repair_5821_polymarket_listing_dates.py so the emptied "
            "row's clock agrees and the fold hides it."
        )
        print("UNDO: python3 scripts/restore_5821_split_container_markets.py --apply")
        return 0


def main():
    p = argparse.ArgumentParser(
        description="#5821 collapse split Polymarket container families"
    )
    p.add_argument("--backup", action="store_true", help="copy in-scope links")
    p.add_argument("--apply", action="store_true", help="write (needs a backup)")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="explicit no-op form of the default; reads only",
    )
    args = p.parse_args()
    sys.exit(asyncio.run(run(args)) or 0)


if __name__ == "__main__":
    main()
