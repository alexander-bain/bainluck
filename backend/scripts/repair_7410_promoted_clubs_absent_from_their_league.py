"""#7410 — 10 event sides bound to Manchester City because their own club has no row in the league.

------------------------------------------------------------------------------
WHAT A READER SEES
------------------------------------------------------------------------------
`https://bainluck.com`, Manchester City's team page, measured 2026-09-20.
`GET /api/teams/188` returns five `recent_events` and **three of them are other
clubs' matches** — Nottingham Forest v Coventry City, Newcastle United v Hull
City, Coventry City v Brighton. One of them wears our own "Upset — beat 83%
odds". Three is what fits in the rendered window; the table holds **9 events,
10 sides**, all of them Coventry City or Hull City wearing team id 188:

    15305209 away  'Coventry City'  -> 188 Manchester City   2026-09-19
    15305235 away  'Hull City'      -> 188 Manchester City   2026-09-19
    15297680 home  'Coventry City'  -> 188 Manchester City   2026-09-13
    15297675 away  'Hull City'      -> 188 Manchester City   2026-09-12
    15291111 home  'Hull City'      -> 188 Manchester City   2026-09-05
    15291105 away  'Coventry City'  -> 188 Manchester City   2026-09-05
    15290889 home  'Coventry City'  -> 188 Manchester City   2026-08-29
    15290889 away  'Hull City'      -> 188 Manchester City   2026-08-29
    14961187 home  'Hull City'      -> 188 Manchester City   2026-08-22
    14961186 away  'Coventry City'  -> 188 Manchester City   2026-08-21

Two of those events — 15290889 and 15291105 — have `home_team_id ==
away_team_id`, i.e. Manchester City recorded as playing itself.

Every side's own `*_team_name` is CORRECT. The name is right and the id is
wrong, so every name-based check in the codebase passes them: #1798's whole
lesson, and why this is invisible to anything that does not dereference.

------------------------------------------------------------------------------
THE WRITER IS ALREADY FIXED. THIS IS THE ROWS IT ALREADY WROTE.
------------------------------------------------------------------------------
PR #7409 (#7157, released v4806) stopped the writer: `Coventry City` scored
exactly 0.50 against `Manchester City` and was being adopted as a sole
candidate with the `shared_token_rivals` veto unwired on that rail. No NEW side
of this shape is produced. These ten are residue, and they do not self-heal:

* the scheduled ESPN pass rebinds from `upsert_team` on every sync — but it
  admits a fixture only once `commence_time` has passed, and these are done;
* the score-backfill pass also rebinds — but it selects rows MISSING a score,
  and these have scores.

------------------------------------------------------------------------------
🔴 WHY THE #1798 RAIL CANNOT DO THIS, AND WHAT THIS SCRIPT ADDS
------------------------------------------------------------------------------
`app/tasks/repair_event_team_binding` re-derives the id from the row's own
`*_team_name` **within the event's own `sport_id`**, exactly one match required.
Run against this league on production 2026-09-20 it returns these ten sides,
all ten, and only these ten, in its `review` bucket with one identical reason:

    "0 exact name matches in sport_id=1298 — refusing to guess"

That refusal is CORRECT and is not loosened here. The rail finds zero candidates
because **there is no `Coventry City` and no `Hull City` row under
`soccer_epl` at all**. Both clubs were promoted; our rows 1813 and 1804 still
sit under `soccer_efl_champ` (1294) with `espn_id IS NULL`, last season's
Championship rows, never updated on promotion.

So this script's population is precisely the rail's refusal bucket, and the only
thing it does that the rail cannot is **create the missing club under the league
it actually plays in** — after which the binding is the rail's own arithmetic.

It is deliberately NOT implemented by widening the rail. Pointed at this league
the rail's plan also carries 15 writes on unrelated rows (`soccer_epl` is
polluted with several hundred South American, youth and women's fixtures), and
`apply=true` applies a whole plan. Approving 25 writes to make 10 is not a
scoped repair.

------------------------------------------------------------------------------
🔴 THE POPULATION IS DERIVED, AND ESPN'S OWN DIRECTORY IS WHAT MAKES IT SAFE
------------------------------------------------------------------------------
Nothing here is a typed list of event ids. A side qualifies when ALL FOUR hold:

1. it is under this league's `sport_id`;
2. its bound club's name DISAGREES with the side's own name — `binding_defect`
   returns `CROSS_CLUB`, the same predicate the write-time guard uses;
3. **zero** teams under that `sport_id` carry the side's own name — the rail's
   refusal, restated. One or more candidates and this is the rail's job, not
   ours, so we do not touch it;
4. **ESPN's own team directory for the league names that club.**

Clause 4 is the load-bearing one and it is an INDEPENDENT authority (D27), not
our tables agreeing with themselves. Clauses 1–3 alone match 500+ distinct name
pairs under this `sport_id`, nearly all of them junk unrelated to the Premier
League. ESPN's `eng.1` directory is 20 clubs, and intersecting against it cuts
the population to exactly the ten sides above. Measured, production+ESPN,
2026-09-20.

🔴 MATCH FULL NAMES ONLY — NEVER `short_name`. Admitting ESPN's `short_name`
adds two false positives that are not defects at all: event 6642197 stores
`'Ipswich'` and `'Hull'`, which are bound to `Ipswich Town` (1819) and `Hull
City` (1804) — the RIGHT clubs under their full names. Clause 2 flags the name
disagreement, clause 3 sees no `Ipswich` row, and the repair would then mint a
junk club literally named `Ipswich` and bind a correct side to it. The short
forms are excluded structurally, in `league_name_tokens`, not by a comment.

------------------------------------------------------------------------------
🔴 THE MINT GOES THROUGH `upsert_team`, WHICH IS THE POINT
------------------------------------------------------------------------------
The club is not hand-built. It is created by the same `upsert_team` the ESPN
sync calls, handed the real `ESPNTeam` from the live directory, so the row is
byte-for-byte what the forward path would have produced — crest, colours,
abbreviation, aliases, `espn_id` — and the two paths CONVERGE rather than race:
when the sync finally admits a Coventry fixture it finds this row by exact name
and enriches it, instead of minting a second one.

It also means the repair inherits `upsert_team`'s own mint refusal (#6215) for
free: a payload whose names do not correspond mints nothing, so a wrong
directory entry cannot create a club under the wrong league here either.

WHAT IS DELIBERATELY NOT MINTED: rows 1813/1804 are not moved. Changing a team's
`sport_id` would relabel that club's whole Championship history. A club that
plays in two competitions gets a row per competition — that is already this
codebase's shape, not a new idea: Manchester City holds four (188 `soccer_epl`,
1827 EFL Cup, 1884 FA Cup, 6318 UCL).

------------------------------------------------------------------------------
🔴 WHAT THIS DOES NOT TOUCH
------------------------------------------------------------------------------
**The four upcoming fixtures 15311089, 15311105, 15315506 and 15315512.** Each
carries NULL on its Coventry/Hull side, and that NULL is #7157's forward-path
RECEIPT: when the sync admits them at kickoff on 11 October the correct outcome
is a `soccer_epl` Coventry/Hull binding, and any of them turning into 188 is
that fix having failed. Binding them here would spend the receipt and leave
nothing to read. Clause 2 excludes them structurally — a NULL side has no bound
club to disagree with, so they cannot enter the plan even by accident.

(The mint does change what the sync DOES at that kickoff — it will match this
row rather than create one. The receipt's pass condition is unchanged: a
`soccer_epl` Coventry/Hull row, never 188.)

**The 500+ other cross-club pairs under `soccer_epl`**, and the league-key
pollution that put Colombian and Paraguayan fixtures there. Real, filed
separately, not this ship.

**`home_team_id = away_team_id` as a standing invariant.** Two of these events
have it and both are repaired here, but 17 more elsewhere have other causes.
Nothing asserts that invariant anywhere; that is worth a guard and it is not
this script.

------------------------------------------------------------------------------
🔴 THE BANK IS THE PLAN, AND IT IS WRITTEN BEFORE THE MINT (CERT-3166)
------------------------------------------------------------------------------
The first version of this script derived its plan freshly on every run and
minted the clubs before banking anything. Both halves of that were wrong, and
together they made the runbook below **unable to reach its third line**:

* clause 3 selects sides with **no club of their own name in the league**. The
  `--backup` run creates exactly such a club. So the `--backup --apply` run
  re-derived, matched zero sides, and hit the empty-plan refusal — the apply
  could never happen;
* and any crash between the mint's commit and anything after it left the same
  unrecoverable state, because the evidence of what was about to be repaired
  lived only in the dead process's memory.

The population is therefore derived EXACTLY ONCE, before anything is created,
and persisted in `backup_7410_promoted_club_binding` — which already had to hold
every field a plan needs, because it is what the undo reads. Two consequences:

1. **The bank is written first**, with `team_id_after` NULL, and filled in once
   the mint commits. There is no window in which a club exists and the plan that
   justified it does not. A NULL `team_id_after` is a row the repair never wrote,
   and the undo's `= team_id_after` join skips it, which is the correct reading.
2. **A run that finds a bank reconstructs its plan from it and never re-derives.**
   Reconstruction is not trust: every banked row is re-read against the live
   side and dropped unless the side still carries the banked name, is still bound
   to the banked before-id, still reads as `CROSS_CLUB`, and is still named by
   ESPN's directory. A side already carrying the repair is counted as done, not
   rewritten; anything else is an anomaly printed by id and left alone.

This is why the fix is NOT "widen clause 3 to also admit a single name match".
That spelling would make the population the #1798 rail's — the 25-writes-to-
make-10 shape this script exists to avoid (see above) — and it would do it
silently, on the retry path, where nobody is reading the plan a third time.

The mint is also tied to the bank: if `upsert_team` resolves a club to an id
other than the one already banked as `team_id_after`, the run refuses. Writing a
different id would leave rows the undo cannot reach.

------------------------------------------------------------------------------
RUNBOOK
------------------------------------------------------------------------------
Attended, D51(b), in this order. Read the plan before applying it. Every line is
re-runnable: the plan is banked, so a repeat resumes rather than starting over.

    heroku run:detached -a bainluck -- python3 scripts/repair_7410_promoted_clubs_absent_from_their_league.py
    heroku run:detached -a bainluck -- python3 scripts/repair_7410_promoted_clubs_absent_from_their_league.py --backup
    heroku run:detached -a bainluck -- python3 scripts/repair_7410_promoted_clubs_absent_from_their_league.py --backup --apply

Undo, one command:

    heroku run:detached -a bainluck -- python3 scripts/restore_7410_promoted_clubs_absent_from_their_league.py --apply

`heroku run` without `:detached` fails silently in the sandbox (gotcha #48) —
verify by re-reading the rows about sixty seconds later, never by trusting an
empty stdout.

Writes refuse anywhere but ``bainluck``. The ESPN sync runs on the main app and
`sync_scheduled_events` is not a heavy task, so there is no heavy-release
precondition (notice 48).

`CREATE TABLE IF NOT EXISTS backup_7410_promoted_club_binding` is runtime DDL
behind `--backup`, invoked by a person, on a named app. Notice 47(c): the
invocation is the attended step, so this is NOT migration-class. Its column
types are derived from `events` by `CREATE TABLE AS SELECT ... WHERE false`
rather than declared by hand — #6215's backup was unrunnable for a week because
one hand-typed column disagreed with the model.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.team_binding_invariant import (  # noqa: E402
    CROSS_CLUB,
    accept_team_binding,
    binding_defect,
    normalize_club_name,
)

#: The app whose deploy carries the ESPN sync. See the header on notice 48.
PRODUCER_APP = "bainluck"

BACKUP_TABLE = "backup_7410_promoted_club_binding"

#: The league this repair is scoped to, as it is spelled in `sports.key`. The
#: `sport_id` is LOOKED UP from it at run time rather than typed: an id is a
#: number that is right until the day it is not, and a name that does not
#: resolve is a loud refusal.
#:
#: The name avoids the suffix that gitleaks treats as a credential hint. It
#: scans constant names, so a string constant named for a key reds the whole
#: check-run over a value that is not a credential and never was — and the
#: scanner reads comments too, which is why this one only describes the shape.
LEAGUE_SPORT = "soccer_epl"


def league_name_tokens(espn_teams) -> set[str]:
    """Normalized FULL names of every club ESPN lists for the league.

    🔴 `display_name` and `name` ONLY. `short_name` is deliberately excluded —
    see the header: admitting `'Ipswich'`/`'Hull'` turns two correctly-bound
    sides into mint candidates and would create junk clubs named after a
    truncation. The exclusion lives here, where the set is built, so a caller
    cannot opt back into it.
    """
    tokens: set[str] = set()
    for team in espn_teams:
        for name in (team.display_name, team.name):
            token = normalize_club_name(name)
            if token:
                tokens.add(token)
    return tokens


def espn_entry_for(espn_teams, row_name: str):
    """The single directory entry whose full name IS ``row_name``. Else None.

    Exact on normalized full names, and requires exactly one — two entries
    normalizing the same way is a directory we do not understand, and guessing
    between them is the failure mode this whole class comes from.
    """
    target = normalize_club_name(row_name)
    if not target:
        return None
    hits = [
        team
        for team in espn_teams
        if target in {normalize_club_name(team.display_name), normalize_club_name(team.name)}
    ]
    return hits[0] if len(hits) == 1 else None


def plan_sides(rows, tokens: set[str]):
    """Apply clauses 2 and 4 to the rows clauses 1 and 3 already selected.

    Returns ``(plan, skipped_not_cross_club, skipped_not_in_directory)``.

    Kept out of :func:`run` and given no database of its own so the decision can
    be tested on real production shapes rather than inferred from a dry-run.
    Clause 2 is ``binding_defect``, IMPORTED and not re-expressed: the #1798
    detector, the #1918 write-time guard and this repair have to agree on what
    "wrong club" means, and a second spelling of the predicate is how a repair
    ends up laundering the error it was written to undo.
    """
    plan: list[dict] = []
    skipped_not_cross_club = 0
    skipped_not_in_directory: set[str] = set()

    for row in rows:
        defect = binding_defect(
            row.row_name, row.bound_name, row.bound_sport_id, row.sport_id
        )
        if defect != CROSS_CLUB:
            skipped_not_cross_club += 1
            continue
        if normalize_club_name(row.row_name) not in tokens:
            skipped_not_in_directory.add(row.row_name)
            continue
        plan.append(
            {
                "event_id": row.event_id,
                "side": row.side,
                "row_name": row.row_name,
                "before_id": row.bound_id,
                "before_name": row.bound_name,
                "commence_time": row.commence_time,
                "status": row.status,
            }
        )

    return plan, skipped_not_cross_club, skipped_not_in_directory


def reconcile_banked_plan(banked, live_sides, tokens: set[str]):
    """Rebuild the plan from the bank, re-validated against the live sides.

    Returns ``(plan, already_applied, anomalies)``.

    This is the path every run after the first one takes, and it exists because
    the fresh derivation is DELIBERATELY unable to see its own work: clause 3
    selects sides whose club does not exist, and the first write creates it.
    See the header.

    The bank is evidence, not authority. A banked row only becomes a plan entry
    when the live side still agrees with it on all four counts that admitted it:

    * the side still carries the banked name (normalized — the bank stores what
      the row said, and a row whose name has since changed is a different fact);
    * it is still bound to the banked ``team_id_before``. Bound to
      ``team_id_after`` instead means the repair already wrote it, which is
      ``already_applied`` and not an error — that is what makes a re-run safe;
    * ``binding_defect`` still reads ``CROSS_CLUB``, so a side something else
      has since corrected is left alone rather than rewritten;
    * ESPN's directory still names the club (clause 4, unchanged).

    Everything else is an anomaly, reported by ``event:side`` and dropped. None
    of these drops is silent and none of them is a write.
    """
    live = {(row.event_id, row.side): row for row in live_sides}
    plan: list[dict] = []
    already_applied: list[tuple] = []
    anomalies: list[str] = []

    for bank_row in banked:
        key = (bank_row.event_id, bank_row.side)
        row = live.get(key)
        if row is None:
            anomalies.append(
                f"{key[0]}:{key[1]} is banked but no live side reads back "
                "(deleted event, or a side whose team FK no longer resolves)"
            )
            continue
        if normalize_club_name(row.row_name) != normalize_club_name(bank_row.row_name):
            anomalies.append(
                f"{key[0]}:{key[1]} the side's own name changed since the bank: "
                f"{bank_row.row_name!r} -> {row.row_name!r}"
            )
            continue
        if bank_row.team_id_after is not None and row.bound_id == bank_row.team_id_after:
            already_applied.append(key)
            continue
        if row.bound_id != bank_row.team_id_before:
            anomalies.append(
                f"{key[0]}:{key[1]} is bound to {row.bound_id}, which is neither "
                f"the banked before ({bank_row.team_id_before}) nor after "
                f"({bank_row.team_id_after}) — something else moved it"
            )
            continue
        if (
            binding_defect(row.row_name, row.bound_name, row.bound_sport_id, row.sport_id)
            != CROSS_CLUB
        ):
            anomalies.append(
                f"{key[0]}:{key[1]} no longer reads as cross-club — left alone"
            )
            continue
        if normalize_club_name(row.row_name) not in tokens:
            anomalies.append(
                f"{key[0]}:{key[1]} {row.row_name!r} is no longer in ESPN's directory"
            )
            continue
        plan.append(
            {
                "event_id": row.event_id,
                "side": row.side,
                "row_name": row.row_name,
                "before_id": row.bound_id,
                "before_name": row.bound_name,
                "commence_time": row.commence_time,
                "status": row.status,
                # NULL until the mint commits. Carried so the mint can be checked
                # against what the undo will look for.
                "after_id": bank_row.team_id_after,
            }
        )

    return plan, already_applied, anomalies


def wrong_app_refusal(args) -> str | None:
    """Refuse a write from anywhere but the producer app.

    THE UNDO IMPORTS THIS, so a restore — a production write in the opposite
    direction, and the one most likely to be typed in a hurry — earns the
    identical gate. ``getattr`` because the undo's parser defines no
    ``--backup``.

    UNSET refuses too. Unset means a laptop pointed at the production database
    with whatever happens to be checked out, which is the case this exists for.
    """
    if not (getattr(args, "apply", False) or getattr(args, "backup", False)):
        return None

    app = os.environ.get("HEROKU_APP_NAME")
    if app == PRODUCER_APP:
        return None

    where = f"'{app}'" if app else "not a Heroku dyno (HEROKU_APP_NAME is unset)"
    return (
        f"REFUSING to write: this is {where}, not '{PRODUCER_APP}'. "
        f"Re-run with `heroku run:detached -a {PRODUCER_APP}`."
    )


#: Clauses 1-3 of the population (the header's four). Clause 4 — ESPN's
#: directory — is applied in Python, because the authority is a network read and
#: a SQL IN-list built from it would hide which clause rejected a row.
#:
#: `bound_name IS NOT NULL` falls out of the INNER JOIN: a side whose FK
#: dereferences to nothing is an unresolvable id, a different defect, and
#: `binding_defect` deliberately returns None for it.
_CANDIDATE_SQL = """
WITH sides AS (
  SELECT e.id AS event_id, e.sport_id, 'home' AS side,
         e.home_team_name AS row_name, e.home_team_id AS bound_id,
         ht.name AS bound_name, ht.sport_id AS bound_sport_id,
         e.commence_time, e.status
    FROM events e
    JOIN teams ht ON ht.id = e.home_team_id
   WHERE e.sport_id = :sport_id
  UNION ALL
  SELECT e.id, e.sport_id, 'away',
         e.away_team_name, e.away_team_id,
         at.name, at.sport_id,
         e.commence_time, e.status
    FROM events e
    JOIN teams at ON at.id = e.away_team_id
   WHERE e.sport_id = :sport_id
)
SELECT s.*
  FROM sides s
 WHERE NOT EXISTS (
         SELECT 1 FROM teams t
          WHERE t.sport_id = s.sport_id
            AND lower(regexp_replace(t.name, '[^a-zA-Z0-9]', '', 'g'))
              = lower(regexp_replace(s.row_name, '[^a-zA-Z0-9]', '', 'g'))
       )
 ORDER BY s.commence_time DESC, s.event_id, s.side
"""

#: The banked plan, in the order it will be read back and applied. Deliberately
#: unfiltered: this table belongs to this repair alone, so every row in it is a
#: row this repair banked, and scoping the read would hide a row rather than
#: report it.
_BANKED_SQL = f"""
SELECT event_id, side, row_name, team_id_before, team_id_after
  FROM {BACKUP_TABLE}
 ORDER BY event_id, side
"""

#: The CURRENT state of the banked sides. `_CANDIDATE_SQL` cannot serve here:
#: its `NOT EXISTS` is the clause the mint invalidates, which is the whole
#: defect CERT-3166 found. This one selects by id and applies no clause at all —
#: every judgement about these rows is made in `reconcile_banked_plan`, where it
#: can be attributed and tested.
_LIVE_SIDES_SQL = """
SELECT e.id AS event_id, e.sport_id, 'home' AS side,
       e.home_team_name AS row_name, e.home_team_id AS bound_id,
       ht.name AS bound_name, ht.sport_id AS bound_sport_id,
       e.commence_time, e.status
  FROM events e
  JOIN teams ht ON ht.id = e.home_team_id
 WHERE e.id = ANY(:ids)
UNION ALL
SELECT e.id, e.sport_id, 'away',
       e.away_team_name, e.away_team_id,
       at.name, at.sport_id,
       e.commence_time, e.status
  FROM events e
  JOIN teams at ON at.id = e.away_team_id
 WHERE e.id = ANY(:ids)
"""

#: COMPARE-AND-SET, the same shape the #1798 rail writes with. The
#: `AND <side>_team_id = :expected` half is the whole point: it asserts the
#: plan's before-image at write time, so a side that moved between the plan and
#: the apply updates ZERO rows instead of being clobbered with a decision made
#: about a state that no longer exists. `rowcount == 0` is a finding.
_UPDATE_SQL = {
    "home": "UPDATE events SET home_team_id = :tid WHERE id = :eid AND home_team_id = :expected",
    "away": "UPDATE events SET away_team_id = :tid WHERE id = :eid AND away_team_id = :expected",
}


def print_plan(plan, minted) -> None:
    """One line per side, in both modes. ``?`` where nothing is minted yet."""
    print("\nplan:")
    for p in plan:
        target = minted.get(p["row_name"])
        tid = getattr(target, "id", "?")
        print(
            f"  {p['event_id']:>9} {p['side']:<4} {p['row_name']!r:<16} "
            f"{p['before_id']} {p['before_name']!r} -> {tid}   "
            f"[{p['status']}] {p['commence_time']}"
        )


async def ensure_bank(s) -> None:
    """Create the backup table and its key. Idempotent; safe to call every run.

    Every column that MIRRORS an `events` column takes its type from that column
    rather than being declared (#6215's lesson: one hand-typed column made that
    backup unrunnable, which made --apply refuse forever). Both id columns are
    the team FK, so both are selected from `home_team_id`; `row_name` mirrors
    `home_team_name`.

    `side` is the one column this repair INVENTS — it mirrors nothing, so
    deriving it from an unrelated column would be cargo, not care. `text`
    because an invented column has no reason to carry a length limit it could
    one day truncate against.
    """
    from sqlalchemy import text

    await s.execute(
        text(
            f"CREATE TABLE IF NOT EXISTS {BACKUP_TABLE} AS "
            "SELECT id AS event_id, "
            " CAST(NULL AS text) AS side, "
            " home_team_name AS row_name, "
            " home_team_id AS team_id_before, home_team_id AS team_id_after, "
            " now() AS taken_at "
            "FROM events WHERE false"
        )
    )
    # CTAS carries no constraints, so the ON CONFLICT below needs this.
    # Idempotent: re-running --backup is safe. The key is (event, side) because
    # 15290889 is in the plan TWICE — both of its sides are bound to 188 — and
    # an event-only key would bank one and lose the other, leaving half the
    # repair un-undoable.
    await s.execute(
        text(
            f"CREATE UNIQUE INDEX IF NOT EXISTS {BACKUP_TABLE}_pk "
            f"ON {BACKUP_TABLE} (event_id, side)"
        )
    )


async def run(args) -> int:  # noqa: C901 - a runbook, read top to bottom
    from sqlalchemy import text

    from app.services.espn_api import ESPNAPIService
    from app.tasks.base import get_task_session
    from app.utils.espn_helpers import upsert_team

    refusal = wrong_app_refusal(args)
    if refusal:
        print(refusal)
        return 2

    if args.apply and not args.backup:
        print(
            "REFUSING: --apply without --backup. D51 makes the backup the price "
            f"of an unattended write, and the undo reads {BACKUP_TABLE}."
        )
        return 2

    # THE AUTHORITY FIRST, and before any row is read. `get_teams` returns None
    # when ESPN did not answer and [] when it answered with nothing — gotcha
    # #53, an absence and a refusal must not share a reading. Either one stops
    # the run: a repair that mints clubs while its own authority is dark is
    # minting on our tables' say-so, which is the thing it exists to avoid.
    espn_teams = await ESPNAPIService().get_teams(LEAGUE_SPORT)
    if espn_teams is None:
        print(
            f"REFUSING: ESPN did not answer for {LEAGUE_SPORT} (authority "
            "dark). Nothing is minted or rebound without the directory."
        )
        return 2
    if not espn_teams:
        print(
            f"REFUSING: ESPN lists zero teams for {LEAGUE_SPORT}. A clean "
            "empty directory is a broken read, not an empty league."
        )
        return 2

    tokens = league_name_tokens(espn_teams)
    print(f"ESPN {LEAGUE_SPORT} directory: {len(espn_teams)} clubs, {len(tokens)} name tokens")

    async with get_task_session() as s:
        sport_id = (
            await s.execute(
                text("SELECT id FROM sports WHERE key = :k"), {"k": LEAGUE_SPORT}
            )
        ).scalar_one_or_none()
        if sport_id is None:
            print(f"REFUSING: no sports row for key {LEAGUE_SPORT!r}.")
            return 2
        print(f"{LEAGUE_SPORT} -> sport_id {sport_id}")

        # ------------------------------------------------------------------
        # THE PLAN. Derived freshly EXACTLY ONCE, and read back from the bank
        # on every run after that — the fresh derivation is structurally unable
        # to see its own work, because clause 3 selects sides whose club does
        # not exist and the first write creates it (CERT-3166, see the header).
        # ------------------------------------------------------------------
        bank_exists = (
            await s.execute(text("SELECT to_regclass(:t)"), {"t": BACKUP_TABLE})
        ).scalar_one() is not None
        banked = (await s.execute(text(_BANKED_SQL))).all() if bank_exists else []

        if banked:
            live = (
                await s.execute(
                    text(_LIVE_SIDES_SQL),
                    {"ids": sorted({b.event_id for b in banked})},
                )
            ).all()
            plan, already_applied, anomalies = reconcile_banked_plan(banked, live, tokens)
            print(
                f"\n{BACKUP_TABLE} holds {len(banked)} banked sides — this run's plan "
                "is THE BANK, re-validated against the live rows, not a fresh "
                "derivation."
                f"\n  already carrying the repair: {len(already_applied)}"
                f"\n  still to write:              {len(plan)}"
                f"\n  anomalies (left alone):      {len(anomalies)}"
            )
            for note in anomalies:
                print(f"    ! {note}")

            if not plan:
                if already_applied and not anomalies:
                    print(
                        f"\nNothing to do: all {len(already_applied)} banked sides "
                        "already carry the repair. Re-running is a no-op by design."
                    )
                    return 0
                print(
                    "\nREFUSING: the bank holds rows and not one of them can be "
                    "written. Every anomaly above is a live row disagreeing with "
                    "what was banked — read them before touching this by hand."
                )
                return 2
        else:
            rows = (
                await s.execute(text(_CANDIDATE_SQL), {"sport_id": sport_id})
            ).all()

            # Clauses 2 (CROSS_CLUB) and 4 (ESPN names it), applied in Python so
            # each rejection is attributable to the clause that made it.
            plan, skipped_not_cross_club, skipped_not_in_directory = plan_sides(rows, tokens)

            print(
                f"\ncandidates with no club of their own name in the league: {len(rows)}"
                f"\n  not cross-club (right club, other defect): {skipped_not_cross_club}"
                f"\n  cross-club but NOT in ESPN's directory:    {len(skipped_not_in_directory)} names"
                f"\n  in plan:                                   {len(plan)} sides"
            )

            if not plan:
                print(
                    "\nREFUSING: zero sides to rebind, and no bank to resume from. "
                    "Either the query no longer matches the schema or this league "
                    "never had the defect — a clean zero here is a broken read, "
                    "not a healthy table."
                )
                return 2

        # The directory entry for each distinct club, resolved in EVERY mode so
        # a plan-only run surfaces the refusal an apply would hit.
        clubs = sorted({p["row_name"] for p in plan})
        entries: dict[str, object] = {}
        for club in clubs:
            entry = espn_entry_for(espn_teams, club)
            if entry is None:
                print(f"REFUSING: {club!r} is not a single exact entry in the directory.")
                return 2
            entries[club] = entry

        if not (args.backup or args.apply):
            for club in clubs:
                print(
                    f"  would mint/resolve {club!r} under sport_id {sport_id} "
                    f"from ESPN {entries[club].espn_id} ({entries[club].display_name})"
                )
            print_plan(plan, {})
            print("\nplan only. Re-run with --backup, then --backup --apply.")
            return 0

        # ------------------------------------------------------------------
        # BANK BEFORE MINT. `--apply` refuses without `--backup`, so from here
        # `args.backup` is always true and the bank is unconditional. Writing it
        # first is what makes every later line of the runbook re-runnable:
        # there is no state in which a club has been created and the plan that
        # justified creating it exists only in this process's memory.
        # `team_id_after` is NULL until the mint is durable, and the undo's
        # `= team_id_after` join reads NULL as "never written", correctly.
        # ------------------------------------------------------------------
        await ensure_bank(s)
        for p in plan:
            await s.execute(
                text(
                    f"INSERT INTO {BACKUP_TABLE} "
                    "(event_id, side, row_name, team_id_before, team_id_after, taken_at) "
                    "VALUES (:eid, :side, :row_name, :before, NULL, now()) "
                    "ON CONFLICT (event_id, side) DO NOTHING"
                ),
                {
                    "eid": p["event_id"],
                    "side": p["side"],
                    "row_name": p["row_name"],
                    "before": p["before_id"],
                },
            )
        await s.commit()

        # Read the bank back rather than trusting rowcounts (gotcha #53), and
        # check the PLAN's own (event, side) keys rather than counting rows —
        # a count passes vacuously once the bank holds more rows than the plan.
        have = {
            (r.event_id, r.side)
            for r in (
                await s.execute(text(f"SELECT event_id, side FROM {BACKUP_TABLE}"))
            ).all()
        }
        unbanked = [
            f"{p['event_id']}:{p['side']}"
            for p in plan
            if (p["event_id"], p["side"]) not in have
        ]
        print(f"\nbanked: {len(plan) - len(unbanked)} of {len(plan)} planned sides in {BACKUP_TABLE}")
        if unbanked:
            print(
                "REFUSING: these planned sides are not in the backup — "
                f"{', '.join(unbanked)}. An undo that cannot restore every row it "
                "is about to change is not an undo."
            )
            return 2

        # One mint per distinct club, through the forward path's own function.
        # `upsert_team` finds an existing row by exact name + sport before it
        # creates anything, so on a resumed run this RESOLVES rather than mints.
        minted: dict[str, object] = {}
        for club in clubs:
            team = await upsert_team(s, club, entries[club], sport_id)
            if team is None:
                # `upsert_team`'s own #6215 refusal. It returns None rather than
                # creating a club under a league its payload does not support.
                print(
                    f"REFUSING: upsert_team refused to mint {club!r} under "
                    f"sport_id {sport_id} from ESPN {entries[club].espn_id} — the "
                    "payload does not correspond. Nothing written."
                )
                await s.rollback()
                return 2
            minted[club] = team
            print(
                f"  {club!r} -> team {team.id} sport_id {team.sport_id} "
                f"espn_id {team.espn_id}"
            )

        print_plan(plan, minted)

        # THE MINT MUST AGREE WITH WHAT THE UNDO LOOKS FOR. On a resumed run the
        # bank already names the target; resolving to a different id would write
        # rows `restore_...py` can never reach, because it joins on
        # `team_id_after`.
        for p in plan:
            expected_after = p.get("after_id")
            resolved = getattr(minted[p["row_name"]], "id", None)
            if expected_after is not None and resolved != expected_after:
                print(
                    f"REFUSING: {p['row_name']!r} now resolves to team {resolved}, "
                    f"but the bank names {expected_after} as this repair's target. "
                    "Writing a different id would put the row out of the undo's "
                    "reach. Nothing written."
                )
                await s.rollback()
                return 2

        # THE GUARD THAT MAKES THE WRITE UNABLE TO REPEAT THE DEFECT. Every
        # target is put through the same gate the write-time rails use: the
        # club's name must match the side's own name, within the event's own
        # sport. A mint that came back wrong cannot be written from here.
        for p in plan:
            target = minted[p["row_name"]]
            if not accept_team_binding(
                side=p["side"],
                row_name=p["row_name"],
                team=target,
                event_sport_id=sport_id,
                source="repair_7410",
                event_id=p["event_id"],
            ):
                print(
                    f"REFUSING: the binding gate rejected event {p['event_id']} "
                    f"{p['side']} {p['row_name']!r} -> team "
                    f"{getattr(target, 'id', None)}. Nothing written."
                )
                await s.rollback()
                return 2
            if getattr(target, "id", None) == p["before_id"]:
                print(
                    f"REFUSING: event {p['event_id']} {p['side']} would be "
                    "rebound to the id it already has. Nothing written."
                )
                await s.rollback()
                return 2

        # The mints must be durable BEFORE the bank names their ids, or an undo
        # would restore rows pointing at teams that were rolled back.
        await s.commit()

        # Now the bank can say what the repair's target IS. Until this runs the
        # row reads `team_id_after IS NULL`, i.e. "banked, never written" — which
        # is exactly true, and is what lets a crashed run resume.
        for p in plan:
            await s.execute(
                text(
                    f"UPDATE {BACKUP_TABLE} SET team_id_after = :after "
                    "WHERE event_id = :eid AND side = :side"
                ),
                {
                    "after": minted[p["row_name"]].id,
                    "eid": p["event_id"],
                    "side": p["side"],
                },
            )
        await s.commit()

        # Read it back rather than trusting rowcounts (gotcha #53), and scope the
        # check to the PLAN's own (event, side) keys. An event-id scope would
        # also sweep in a banked side this run left alone as an anomaly, and
        # refuse the nine good writes on account of the one we already decided
        # not to touch.
        planned_keys = {(p["event_id"], p["side"]) for p in plan}
        unresolved = sorted(
            f"{r.event_id}:{r.side}"
            for r in (
                await s.execute(
                    text(
                        f"SELECT event_id, side FROM {BACKUP_TABLE} "
                        "WHERE team_id_after IS NULL"
                    )
                )
            ).all()
            if (r.event_id, r.side) in planned_keys
        )
        if unresolved:
            print(
                f"REFUSING to apply: {len(unresolved)} planned side(s) still have "
                f"no target id in the bank — {', '.join(unresolved)}. The undo "
                "joins on that column, so writing now would put those rows out "
                "of its reach."
            )
            return 2

        ids = sorted({p["event_id"] for p in plan})

        if args.apply:
            moved = 0
            drifted: list[str] = []
            for p in plan:
                result = await s.execute(
                    text(_UPDATE_SQL[p["side"]]),
                    {
                        "tid": minted[p["row_name"]].id,
                        "eid": p["event_id"],
                        "expected": p["before_id"],
                    },
                )
                if result.rowcount:
                    moved += result.rowcount
                else:
                    drifted.append(f"{p['event_id']}:{p['side']}")
            await s.commit()

            if drifted:
                print(f"\nCONCURRENT_ROW_DRIFT, not written: {', '.join(drifted)}")

            # Read back from disk rather than trusting rowcount (gotcha #53),
            # and re-read the PLAN's own sides rather than re-measuring the
            # population — a fresh census is what produces false comfort.
            stale = (
                await s.execute(
                    text(
                        """
                        SELECT count(*) FROM (
                          SELECT e.id, e.home_team_name AS rn, ht.name AS bn
                            FROM events e JOIN teams ht ON ht.id = e.home_team_id
                           WHERE e.id = ANY(:ids)
                          UNION ALL
                          SELECT e.id, e.away_team_name, at.name
                            FROM events e JOIN teams at ON at.id = e.away_team_id
                           WHERE e.id = ANY(:ids)
                        ) x
                        WHERE lower(regexp_replace(x.bn, '[^a-zA-Z0-9]', '', 'g'))
                           <> lower(regexp_replace(x.rn, '[^a-zA-Z0-9]', '', 'g'))
                        """
                    ),
                    {"ids": ids},
                )
            ).scalar_one()
            print(f"\napplied: {moved} sides; still cross-club on these events: {stale}")
            return 0 if stale == 0 and not drifted else 1

    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--backup", action="store_true", help="bank the current bindings")
    p.add_argument("--apply", action="store_true", help="write the repair")
    args = p.parse_args()
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
