"""#6295's owed repair — take Bayer Leverkusen off the La Liga fixtures it never played.

THE SHIP: `/sports/soccer_spain_la_liga` stops carrying a card for a fixture that
does not exist. The forward gate (this branch's `_SOC_ABBREV_LEAGUE_OWNER`) stops
the NEXT one being minted; it cannot move a row already written, and CERT-3000
blocked the pair for exactly that — three rows are on production today:

    15312871  "Bayer Leverkusen v Athletic Club"  KXLALIGAGAME-26SEP16LEVATH
    15312872  "Villarreal v Bayer Leverkusen"     KXLALIGAGAME-26SEP20VILLEV
    15312896  "Paris Saint-Germain v Genoa"       KXSERIEAGAME-26SEP20PARGEN

Six soccer competitions share the one `_soc` abbreviation suffix, so `lev_soc`
(the Bundesliga block's Bayer Leverkusen) answered La Liga tickers meaning
Levante, and `par_soc` (the Champions League block's PSG) answered a Serie A
ticker meaning Parma. Each market's own title carried the right answer all along:
"Levante vs Bilbao", "Villarreal vs Levante", "Parma Calcio vs Genoa".

THE NET IS THE FIX'S NET, NOT A SECOND OPINION. Nothing here re-derives a name
with a regex written for this script:

  * A row is proof of the bug only if the PRE-fix resolver reproduces the pair it
    actually stores. That replay is
    `extract_team_codes_from_ticker(ticker, sport_suffix_override=_SOC_ABBREV_SUFFIX)`
    — the override is the fix's own documented seam, and it exists because a
    caller replaying a historical resolution must not have it re-decided by a
    rule that postdates the row (see `extract_team_codes_from_ticker`).
  * The row must also be one the SHIPPED resolver now answers differently. If
    today's code would have minted the same pair, this defect did not write it.
  * The NEW name is `extract_matchup_with_ticker_fallback(...)` — literally what
    the matcher writes for this market today. Not the title alone and not a
    hand-typed table: a repair whose answer differs from the fix's is a third
    opinion, and #3672's repair is the precedent this follows line for line.

MEASURED ON PRODUCTION 2026-09-17 over 1,894 soccer events carrying a Kalshi
market, by driving the shipped resolver with #6295's predicate off and on:

    tickers the fix resolves differently          9
      of those, rows that STORE the pre-fix pair  3   <- the plan
      rows whose stored names came from elsewhere 6   <- ESPN-anchored, correct

Those 6 are the control that matters: `15298072` really is "Levante v Barcelona"
and `15291307` really is "Parma v Monza" — ESPN named them, the ticker did not,
and the replay test refuses them rather than renaming rows that are already right.

WHAT THE RENAME IS WORTH, MEASURED THROUGH THE SHIPPING FOLD RATHER THAN ASSUMED.
Each phantom has a real counterpart already on the page, so the question "does a
reader stop seeing a fixture that never existed, or merely see a better-named
duplicate" has an answer. Driving `fold_twin_events` over all 40 La Liga and
Serie A rows in `[2026-09-16, 2026-09-22]`, before and after the rename:

    soccer_italy_serie_a   11 rows  11 cards -> 10 cards   15312896 folds onto 15306081
    soccer_spain_la_liga   29 rows  20 cards -> 19 cards   15312872 folds onto 15312073

**Both SCHEDULED phantoms — the two CERT-3000 named as still rendering — stop
being served at all**, because once the name is true the twin fold pairs them
with their ESPN-anchored row and elects the anchor (`twin_identity_rank`), which
carries the score, the crest and the event page.

`15312871` is the honest exception and it is stated here rather than discovered:
it does NOT fold. Its stored hour is 23:30Z against ESPN's 19:30Z kick-off — four
hours, not the exact three-hour `KALSHI_EXPECTED_EXPIRATION_PAD` that
`recover_kalshi_occurrence_starts` knows how to undo — so it lands 60 minutes
from its twin and the 5-minute drift bound refuses it, correctly. After this
repair it reads "Levante vs Bilbao", which is a true name for a real fixture at a
wrong hour: a duplicate under #2693 instead of a fixture between two clubs in
different countries. That is the trade this script makes and it is deliberate.

WHAT IT WILL NOT TOUCH, each a refusal rather than an omission:

  * A row whose pre-fix replay does not reconstruct the stored pair, in either
    order — reported `NOT_MINTED_BY_THIS`, six of them today.
  * A ticker the fix resolves the same way it always did (`FIX_AGREES`).
  * A row whose market title yields no matchup (`NO_NEW_NAME`) — nothing is
    guessed from the ticker's letters.
  * Anything but `events.home_team_name` / `.away_team_name`. All three planned
    rows carry NULL `home_team_id` / `away_team_id`, so there is no crest to
    unpick; no market moves, no blend is touched, no row is deleted, and the
    events keep their markets (gotcha #15 — a linked market stays linked).

THE DISPOSITION IS PRE-REGISTERED AND `--apply` REFUSES TO DISAGREE WITH IT.
`EXPECTED_IDS` is what a production replay of this code measured on 2026-09-17.
The population is still minting — the gate is not live until this merges — so a
fourth phantom appearing is expected rather than alarming: the guard prints it
and `--expect-plan N` restates the claim deliberately. It never relaxes itself.

RUNBOOK (the only supported sequence):

    1.  Merge, and wait for `bainluck-heavy` to carry the sha (standing notice 48
        — `match_prediction_markets` is a HEAVY task, so until heavy has the gate
        the producer is still minting these rows and a repair races it).
    2.  heroku run:detached -a bainluck-heavy -- \
            python3 scripts/repair_6295_soc_league_names.py
    3.  heroku run:detached -a bainluck-heavy -- \
            python3 scripts/repair_6295_soc_league_names.py --backup --apply

Undo, one command (D51(b)):

    heroku run:detached -a bainluck-heavy -- \
        python3 scripts/restore_6295_soc_league_names.py --apply

Steps 2 and 3 are not advice: `--backup` and `--apply` refuse unless
`HEROKU_APP_NAME` is `bainluck-heavy`, and `--apply` refuses without `--backup`.

`CREATE TABLE IF NOT EXISTS backup_6295_event_names` is runtime DDL that executes
only when a person invokes `--backup` on that named app — standing notice 47(c),
NOT migration-class. The invocation is the attended step. The table is not
Alembic-managed: `alembic revision --autogenerate` will propose DROPping it, and
that line is to be deleted from the generated migration rather than accepted.

Without `--apply` this prints the full plan and writes nothing.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# The fix itself. Imported, never restated — see the module docstring.
from app.utils.prediction_market_matching import (  # noqa: E402
    _SOC_ABBREV_SUFFIX,
    extract_matchup_with_ticker_fallback,
    extract_team_codes_from_ticker,
)

#: The app whose code can put the defect back. `match_prediction_markets` mints
#: these rows and is in `HEAVY_TASKS`, so since the heavy split that is
#: `bainluck-heavy` — released separately from the web app and routinely behind
#: it (standing notice 48). Repairing from the web app would race a producer
#: still running the unfixed namespace.
PRODUCER_APP = "bainluck-heavy"

BACKUP_TABLE = "backup_6295_event_names"

#: Kalshi MARKET data purges at >=74/<86 days (gotcha #35), and this script's
#: whole evidentiary basis is the ticker and the title of a live market. Older
#: rows have nothing left to prove anything with, so they are out of scope by
#: construction rather than by preference.
#:
#: A `datetime`, NOT an ISO string: it binds into `CAST(:since AS timestamptz)`
#: and **asyncpg refuses a `str` there rather than casting it** — the failure
#: that stopped `repair_3672` on its first statement (CERT-2139).
SINCE = datetime(2026, 8, 1, tzinfo=timezone.utc)

#: Sanity floor on the CANDIDATE population, not on the plan. A repair that finds
#: nothing and reports success is the worst outcome there is (gotcha #53 — an
#: empty result is a response shape, not an absence). Measured 2026-09-17: 1,894
#: soccer events carry a Kalshi market inside this window. Under this floor means
#: the join or the window broke, not that the work is done.
MIN_EXPECTED_POPULATION = 500

#: Pre-registered disposition — production replay of this code, 2026-09-17.
EXPECTED_IDS = (15312871, 15312872, 15312896)


def wrong_app_refusal(args) -> str | None:
    """Why this invocation may not write, or `None`.

    `getattr`, because the undo's parser has no `--backup`: one refusal serving
    two programs must not raise on reading a flag only one of them defines.

    UNSET refuses too, rather than falling through. Unset means a laptop pointed
    at the production database with whatever happens to be checked out, which is
    precisely the case this gate exists to stop.
    """
    if not (getattr(args, "apply", False) or getattr(args, "backup", False)):
        return None

    app = os.environ.get("HEROKU_APP_NAME")
    if app == PRODUCER_APP:
        return None

    where = f"'{app}'" if app else "not a Heroku dyno (HEROKU_APP_NAME is unset)"
    return (
        f"REFUSING to write: this is {where}, not '{PRODUCER_APP}'. "
        "`match_prediction_markets` — the task that mints these rows off the "
        "shared `_soc` namespace — is in HEAVY_TASKS, so the code that can put "
        f"the defect back is what is deployed to '{PRODUCER_APP}', an app "
        "released separately from the web app and routinely behind it "
        f"(standing notice 48). Re-run with `heroku run:detached -a {PRODUCER_APP}`."
    )


def _session_factory():
    """The app's real async session factory.

    Behind a named function so a test can substitute it AND prove the real one
    resolves. `repair_2947` shipped importing `app.database`, a module that has
    never existed, so `run()` crashed before planning a row while every unit test
    passed against a fake session (CERT-903). An entrypoint that dies on import
    is not a repair, it is a file.
    """
    from app.services.database import async_session_maker

    return async_session_maker


def replay_pre_fix_names(ticker: str):
    """What this ticker resolved to BEFORE #6295, or `None`.

    One call, but it is the whole evidentiary basis of the repair, so it is
    named: every claim that a row "was minted by #6295" reduces to it. The
    override pins the shared soccer namespace and leaves `sport_key` unset, which
    is exactly the pre-fix state — `_soc_key_belongs_to_another_competition`
    cannot fire without a competition to compare against.
    """
    pair = extract_team_codes_from_ticker(
        ticker, sport_suffix_override=_SOC_ABBREV_SUFFIX
    )
    return (pair[0][1], pair[1][1]) if pair else None


def shipped_names(ticker: str):
    """What the resolver answers TODAY, gate included, or `None`."""
    pair = extract_team_codes_from_ticker(ticker)
    return (pair[0][1], pair[1][1]) if pair else None


def orientation(stored_home: str, stored_away: str, replay: tuple):
    """`False` (as-is), `True` (swapped), or `None` when the replay does not fit.

    A row is proof of the bug only if the pre-fix replay reproduces the pair it
    actually stores. Both orders are checked so that a row stored opposite to its
    ticker is repaired with its orientation preserved rather than reversed — the
    same reasoning, and the same failure avoided, as `repair_3672`.
    """
    stored = (stored_home.casefold(), stored_away.casefold())
    a, b = replay[0].casefold(), replay[1].casefold()
    if stored == (a, b):
        return False
    if stored == (b, a):
        return True
    return None


def plan_row(event_id, stored_home, stored_away, ticker, market_name):
    """One row's verdict: a plan dict, or `(None, reason)`."""
    if not ticker or not stored_home or not stored_away:
        return None, "NO_TICKER"

    pre = replay_pre_fix_names(ticker)
    if not pre:
        return None, "NO_RECONSTRUCT"
    if pre == shipped_names(ticker):
        # The gate does not move this ticker, so whatever is stored here, this
        # defect did not write it.
        return None, "FIX_AGREES"

    swapped = orientation(stored_home, stored_away, pre)
    if swapped is None:
        return None, "NOT_MINTED_BY_THIS"

    matchup = extract_matchup_with_ticker_fallback(market_name, external_id=ticker)
    if not matchup or not matchup.team_a or not matchup.team_b:
        return None, "NO_NEW_NAME"
    new_home, new_away = matchup.team_a.strip(), matchup.team_b.strip()
    if swapped:
        new_home, new_away = new_away, new_home

    if (new_home.casefold(), new_away.casefold()) == (
        stored_home.casefold(),
        stored_away.casefold(),
    ):
        return None, "ALREADY_CORRECT"

    return {
        "id": event_id,
        "old_home": stored_home,
        "old_away": stored_away,
        "new_home": new_home,
        "new_away": new_away,
        "ticker": ticker,
        "swapped": swapped,
    }, None


async def build_plan(session, limit: int = 0):
    """Re-derive true names for the population. Returns `(plan, skipped)`."""
    from sqlalchemy import text

    rows = (
        await session.execute(
            text(
                "SELECT e.id, e.home_team_name, e.away_team_name, "
                "       fm.external_id, fm.name "
                "FROM events e "
                "JOIN sports s ON s.id = e.sport_id "
                # LATERAL, not two correlated scalar subqueries: one market row
                # supplies BOTH the ticker and the title, so they can never come
                # from two different markets hanging off the same event.
                "JOIN LATERAL ("
                "  SELECT fm.external_id, fm.name FROM futures_markets fm "
                "  WHERE fm.event_id = e.id AND fm.source = 'kalshi' "
                "  ORDER BY fm.id LIMIT 1"
                ") fm ON true "
                "WHERE s.key LIKE 'soccer%' "
                "  AND e.commence_time >= CAST(:since AS timestamptz) "
                "ORDER BY e.id" + (" LIMIT :lim" if limit else "")
            ),
            {"since": SINCE, **({"lim": limit} if limit else {})},
        )
    ).all()

    plan, skipped = [], []
    for event_id, home, away, ticker, market_name in rows:
        row, reason = plan_row(event_id, home, away, ticker, market_name)
        if row is None:
            skipped.append((event_id, home, away, reason))
        else:
            plan.append(row)
    return plan, skipped


def disposition_drift(plan, expect_plan=None):
    """Why this plan disagrees with the pre-registered one, or `None`.

    The ids are the claim, not just the count: CERT-3000 named these three rows,
    so a plan holding a different row is a different repair and says so out loud.
    `--expect-plan N` restates the COUNT deliberately, which is the escape hatch
    for the fourth phantom the un-gated producer may mint before this runs.
    """
    ids = tuple(sorted(row["id"] for row in plan))
    if expect_plan is not None:
        return (
            None
            if len(plan) == expect_plan
            else f"--expect-plan {expect_plan} but the plan holds {len(plan)}: {ids}"
        )
    if ids == tuple(sorted(EXPECTED_IDS)):
        return None
    return (
        f"the plan is {ids}, the pre-registered disposition is "
        f"{tuple(sorted(EXPECTED_IDS))}"
    )


async def ensure_backup(session, plan):
    """Idempotent `NOT EXISTS` top-up of the pre-repair names."""
    from sqlalchemy import text

    await session.execute(
        text(
            f"CREATE TABLE IF NOT EXISTS {BACKUP_TABLE} ("
            "  event_id bigint PRIMARY KEY,"
            "  home_team_name text NOT NULL,"
            "  away_team_name text NOT NULL,"
            # What the repair intends to write, so the undo can guard on the
            # exact value rather than infer it. Without this a restore has to
            # guess whether a differing current name is the repair's or somebody
            # else's, and guessing is how an undo stomps a later decision.
            "  new_home_team_name text NOT NULL,"
            "  new_away_team_name text NOT NULL,"
            "  backed_up_at timestamptz NOT NULL DEFAULT now())"
        )
    )
    for row in plan:
        await session.execute(
            text(
                f"INSERT INTO {BACKUP_TABLE} (event_id, home_team_name, away_team_name,"
                "                             new_home_team_name, new_away_team_name) "
                "SELECT :eid, :h, :a, :nh, :na WHERE NOT EXISTS "
                f"(SELECT 1 FROM {BACKUP_TABLE} WHERE event_id = :eid)"
            ),
            {
                "eid": row["id"],
                "h": row["old_home"],
                "a": row["old_away"],
                "nh": row["new_home"],
                "na": row["new_away"],
            },
        )
    await session.commit()

    return (
        await session.execute(
            text(f"SELECT count(*) FROM {BACKUP_TABLE} WHERE event_id = ANY(:ids)"),
            {"ids": [row["id"] for row in plan]},
        )
    ).scalar_one()


async def apply_plan(session, plan):
    from sqlalchemy import text

    written = 0
    for row in plan:
        # Guarded on the OLD values: a row something else has since renamed is
        # left alone rather than stomped.
        result = await session.execute(
            text(
                "UPDATE events SET home_team_name = :nh, away_team_name = :na "
                "WHERE id = :eid AND home_team_name = :oh AND away_team_name = :oa"
            ),
            {
                "eid": row["id"],
                "nh": row["new_home"],
                "na": row["new_away"],
                "oh": row["old_home"],
                "oa": row["old_away"],
            },
        )
        written += result.rowcount or 0
    await session.commit()
    return written


async def run(args) -> int:
    refusal = wrong_app_refusal(args)
    if refusal:
        print(refusal)
        return 2

    session_factory = _session_factory()

    async with session_factory() as session:
        plan, skipped = await build_plan(session, limit=args.limit)
        candidates = len(plan) + len(skipped)
        print(
            f"soccer events carrying a Kalshi market since {SINCE:%Y-%m-%d}: {candidates}"
        )

        reasons: dict[str, int] = {}
        for *_, why in skipped:
            reasons[why] = reasons.get(why, 0) + 1
        for why, count in sorted(reasons.items(), key=lambda kv: -kv[1]):
            print(f"    {why:20} {count:>6}")
        print(f"    TO RENAME            {len(plan):>6}")

        for row in plan:
            swap = "  (orientation preserved)" if row["swapped"] else ""
            print(
                f"    {row['id']}  {row['old_home']} vs {row['old_away']}"
                f"\n         -> {row['new_home']} vs {row['new_away']}"
                f"   [{row['ticker']}]{swap}"
            )

        if candidates < MIN_EXPECTED_POPULATION and not args.limit:
            print(
                f"REFUSING: {candidates} candidates < floor {MIN_EXPECTED_POPULATION}. "
                "The join or the window broke — an empty result is a response "
                "shape, not an absence (gotcha #53)."
            )
            return 2

        if not plan:
            print("nothing to do")
            return 0

        # EVERY refusal that can stop an apply is decided here, before the first
        # write of the run — the backup table included. In `repair_2947` the
        # drift guard sat below `ensure_backup` and below a `--limit` exemption,
        # so a `--limit N --backup --apply` run wrote a backup and renamed rows
        # while disagreeing with its own claim, then exited 0 (CERT-903).
        if args.apply:
            if args.limit:
                print(
                    "REFUSING: --limit plans a subset, so it cannot satisfy the "
                    "pre-registered disposition. It is a dry-run tool — drop "
                    "--apply, or drop --limit and repair the whole population."
                )
                return 7
            if not args.backup:
                print("REFUSING: --apply without --backup. Run both in one invocation.")
                return 4
            drift = disposition_drift(plan, args.expect_plan)
            if drift:
                print(
                    f"REFUSING: {drift}.\nThis is the guard working, not a bug: the "
                    "producer is still minting until heavy carries the gate. Read "
                    "the rows above, confirm each is the same defect, then re-run "
                    "with --expect-plan N to restate the claim deliberately."
                )
                return 6

        if args.backup:
            covered = await ensure_backup(session, plan)
            print(f"backup: {covered}/{len(plan)} of the plan is in {BACKUP_TABLE}")
            if covered < len(plan):
                print("REFUSING: backup does not cover the plan.")
                return 3

        if not args.apply:
            print("DRY RUN — nothing written. Re-run with --backup --apply.")
            return 0

        written = await apply_plan(session, plan)
        print(f"APPLIED: {written} events renamed (planned {len(plan)})")
        print(
            f"undo: heroku run:detached -a {PRODUCER_APP} -- "
            "python3 scripts/restore_6295_soc_league_names.py --apply"
        )
        return 0 if written == len(plan) else 5


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--backup", action="store_true", help="top up the D51 backup table")
    p.add_argument(
        "--apply", action="store_true", help="write the renames (needs --backup)"
    )
    p.add_argument(
        "--limit",
        type=int,
        default=0,
        help="plan over at most N events — a dry-run tool, REFUSED together with "
        "--apply because a subset can never match the pre-registered disposition",
    )
    p.add_argument(
        "--expect-plan",
        type=int,
        default=None,
        help="restate the expected rename count when the population has "
        "legitimately moved; without it a plan differing from the pre-registered "
        "ids refuses to apply",
    )
    args = p.parse_args()
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
