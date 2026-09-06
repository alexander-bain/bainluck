"""#3672 acceptance 4 — take the NBA's nicknames off the events that never earned them.

THE SHIP: a WTA Challenger match on the WTA tour page stops being called
`Nuggets vs Clippers`. Today `/sport/tennis/wta` renders a card reading

    Timberwolves   vs   Hornets          (KXWTACHALLENGERMATCH-26JUN02MINCHA)

for a match whose Kalshi market is titled "Minnen vs Charaeva". A rugby fixture
reads `Bulls vs Seahawks`, an AHL game reads `Avalanche vs Bulls`, and a World
Cup fixture reads `Avalanche vs Trail Blazers`. The forward fix (#3672, live at
`8c2d2b82`) stops the next one being minted; this is the owed repair for the
ones already written, and acceptance 4 says so in as many words.

THE NET IS THE FIX'S NET, NOT A SECOND OPINION.
Nothing here re-derives a name with a regex written for this script:

  * The candidate NAME SET is DERIVED at import from the bare keys of
    `_KALSHI_TEAM_ABBREVS` — the very table the bug read. A hand-typed blocklist
    would be as complete as the last person who remembered it, which is the
    failure mode #3672 was, one layer up. (It is 74 names, and it is NOT just the
    NBA: the bare namespace also holds NFL, MLB and NHL nicknames, so an
    "NBA nickname" predicate — the one the issue body uses — under-reports.)

  * The PROOF a row was minted by this bug is a replay of the fix's own parser
    in the namespace it used to read:
    `extract_team_codes_from_ticker(ticker, sport_suffix_override="")`. That
    override exists for this script and has one caller, this script. If the
    replay does not reproduce the stored pair, the row merely RESEMBLES the bug
    and is left alone.

  * The NEW name is `extract_matchup_with_ticker_fallback(...)` — literally what
    the matcher would write for this market today. Not the market title alone:
    for the 20 NFL quarter markets in the population the title says "Detroit vs
    Cincinnati" while the matcher says "Lions vs Bengals", and the matcher is
    right. A repair whose answer differs from the fix's is a third opinion.

ORIENTATION IS PRESERVED, NOT ASSUMED. Two rows store the pair in the opposite
order to their ticker (`KXITFWMATCH-26MAY20VANCHA` stored as `Hornets vs
Canucks`). The replay is checked BOTH ways and a swapped row has its new names
swapped to match, so home stays home. Refusing them instead would leave two
known-broken rows behind for no reason; renaming them un-swapped would silently
reverse a fixture.

WHAT IT WILL NOT TOUCH, each a deliberate refusal:

  * A row whose replay does not reconstruct the stored pair, in either order.
  * A row whose clean name would COLLIDE — with another row in this same plan
    (18 rows, 9 groups: four separate prop markets each minted their own
    "Colombia vs Portugal" event) or with a clean event that already exists
    (8 rows). Renaming both halves of a collision turns two obviously-broken
    rows into two convincing identical ones — the CERT-880 failure, and #2693's
    twins are exactly this population. The twin is a MATCHING bug and it is not
    this script's to fix; making it invisible would be actively worse.
  * Anything outside `events.home_team_name` / `.away_team_name`. Measured on
    production 2026-09-06: all 96 planned rows have NULL `home_team_id` and
    `away_team_id`, and `team_identity_mapping` holds ZERO kalshi rows pointing
    at an NBA team under a non-NBA `sport_key` — so there is no crest to unpick,
    contrary to the note this queue was restocked with. No market moves, no
    blend is touched, nothing is deleted.

  * The 114 kalshi-minted rows whose Kalshi market has since PURGED (gotcha #35,
    market data goes at >=74/<86 days). Their ticker and title are gone, so
    there is no evidence left to rename them from. They are reported as
    NO_KALSHI_MARKET by `--census`, never guessed at. A further 116 rows in the
    same name set are polymarket-provenance and were never minted by this
    mechanism at all.

THE DISPOSITION IS PRE-REGISTERED AND THE SCRIPT REFUSES TO DISAGREE WITH IT.
`EXPECTED` is what a production replay of THIS code measured on 2026-09-06
against `8c2d2b82`. `--apply` refuses if the live plan differs, so this docstring
and the dyno cannot silently drift apart; restating it takes `--expect-plan N`.

D51 UNDO. `--backup` writes every pre-repair (id, home, away) plus the intended
new pair to `bak_3672_event_names` before a single row changes, and
`restore_3672_bare_namespace_event_names.py --apply` is the one command that puts
them back. RUN BOTH FLAGS IN ONE INVOCATION —

    heroku run:detached -a bainluck \
      "python3 scripts/repair_3672_bare_namespace_event_names.py --backup --apply"

— because the population can grow between two invocations (lane1b/029 paid for
that). The backup is an idempotent `NOT EXISTS` top-up, so a refusal is fixed by
re-running that same one command.

The `bak_3672_*` table is NOT Alembic-managed. `alembic revision --autogenerate`
will propose DROPping it; delete that from the generated migration rather than
accepting it. Drop it deliberately with the restore script's `--drop-backups`
once the repair is trusted.

Without `--apply` this prints the full plan and writes nothing.
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# The fix itself. Imported, never restated — see the module docstring.
from app.utils.prediction_market_matching import (  # noqa: E402
    _KALSHI_TEAM_ABBREVS,
    extract_matchup_with_ticker_fallback,
    extract_team_codes_from_ticker,
)

#: Every name the BARE namespace could produce, derived from the table the bug
#: read. A stored pair drawn from anywhere else was not minted by this bug.
BARE_NAMESPACE_NAMES = sorted(
    {name for abbrev, name in _KALSHI_TEAM_ABBREVS.items() if "_" not in abbrev}
)

#: The bare namespace, spelled as `extract_team_codes_from_ticker` wants it. This
#: is the pre-#3672 default that every unmapped ticker prefix silently received.
_PRE_FIX_NAMESPACE = ""

#: The bug shipped in #2706 and the events it minted start here. Earlier rows are
#: out of scope: their markets have purged, so nothing can be proved about them.
SINCE = "2026-06-01"

BAK_TABLE = "bak_3672_event_names"

# Sanity floor. A repair that finds nothing and reports success is the worst
# outcome there is (gotcha #53 — an empty result is a response shape, not an
# absence). Measured candidate population 2026-09-06 was 126; under this floor
# means the predicate broke, not that the work is done.
MIN_EXPECTED_POPULATION = 100

# Pre-registered disposition — production replay of this code, 2026-09-06,
# against master `8c2d2b82`.
EXPECTED = {
    "candidates": 126,
    "plan": 96,
    "no_reconstruct": 0,
    "already_correct": 4,
    "twin_within_plan": 18,
    "clean_counterpart": 8,
}

CHUNK = 200


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


def disposition_drift(measured: dict, expect_plan=None) -> dict:
    """Buckets that disagree with the pre-registered disposition.

    Returns {bucket: (expected, measured)} — empty means the run matches the
    claim in the docstring and may proceed. `expect_plan` restates ONE number
    deliberately; it never relaxes the other buckets.
    """
    expected = dict(EXPECTED)
    if expect_plan is not None:
        expected["plan"] = expect_plan
    return {k: (expected[k], v) for k, v in measured.items() if expected[k] != v}


def replay_pre_fix_names(ticker: str):
    """What this ticker resolved to BEFORE the default flipped, or None.

    One line, but it is the whole evidentiary basis of the repair, so it is named:
    every claim that a row "was minted by #3672" reduces to this call.
    """
    pair = extract_team_codes_from_ticker(ticker, sport_suffix_override=_PRE_FIX_NAMESPACE)
    return (pair[0][1], pair[1][1]) if pair else None


def orientation(stored_home: str, stored_away: str, replay: tuple):
    """`False` (as-is), `True` (swapped), or None when the replay does not fit.

    A row is proof of the bug only if the pre-fix replay reproduces the pair it
    actually stores. Checking both orders is not laxity: two measured rows store
    home/away opposite to their ticker, and the alternative to handling them is
    either abandoning them or reversing a fixture.
    """
    stored = (stored_home.casefold(), stored_away.casefold())
    a, b = replay[0].casefold(), replay[1].casefold()
    if stored == (a, b):
        return False
    if stored == (b, a):
        return True
    return None


def plan_row(event_id, stored_home, stored_away, ticker, market_name):
    """One row's verdict: a plan dict, or (None, reason)."""
    replay = replay_pre_fix_names(ticker)
    if not replay:
        return None, "NO_RECONSTRUCT"
    swapped = orientation(stored_home, stored_away, replay)
    if swapped is None:
        return None, "NO_RECONSTRUCT"

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


async def build_plan(session, limit=0):
    """Re-derive clean names for the population. Returns (plan, skipped)."""
    from sqlalchemy import text

    rows = (
        await session.execute(
            text(
                "SELECT e.id, e.home_team_name, e.away_team_name, e.commence_time, "
                "       fm.external_id, fm.name "
                "FROM events e "
                # LATERAL, not a correlated scalar subquery per column: one market
                # row supplies BOTH the ticker and the title, so they can never
                # come from two different markets hanging off the same event.
                "JOIN LATERAL ("
                "  SELECT fm.external_id, fm.name FROM futures_markets fm "
                "  WHERE fm.event_id = e.id AND fm.source = 'kalshi' "
                "  ORDER BY fm.id LIMIT 1"
                ") fm ON true "
                "WHERE e.commence_time >= CAST(:since AS timestamptz) "
                "  AND e.home_team_name = ANY(:names) "
                "  AND e.away_team_name = ANY(:names) "
                "ORDER BY e.id" + (" LIMIT :lim" if limit else "")
            ),
            {
                "since": SINCE,
                "names": BARE_NAMESPACE_NAMES,
                **({"lim": limit} if limit else {}),
            },
        )
    ).all()

    plan, skipped = [], []
    for event_id, home, away, commence, ticker, market_name in rows:
        row, reason = plan_row(event_id, home, away, ticker, market_name)
        if row is None:
            skipped.append((event_id, home, away, reason))
        else:
            row["commence"] = commence
            plan.append(row)
    return plan, skipped


async def drop_collisions(session, plan):
    """Remove rows whose clean name would land on top of another fixture."""
    from sqlalchemy import text

    def key(row):
        return (
            row["new_home"].casefold(),
            row["new_away"].casefold(),
            row["commence"].date(),
        )

    seen = {}
    for row in plan:
        seen.setdefault(key(row), []).append(row)

    kept, dropped = [], []
    for group in seen.values():
        if len(group) > 1:
            # Several prop markets on ONE game each minted their own event
            # (#2693's twins). Renaming them all to the same clean name would
            # turn a visibly-broken cluster into a convincing duplicate set.
            dropped.extend((r, "TWIN_WITHIN_PLAN") for r in group)
            continue
        row = group[0]
        clash = (
            await session.execute(
                text(
                    "SELECT id FROM events WHERE id <> :eid "
                    "AND lower(home_team_name) = lower(:h) "
                    "AND lower(away_team_name) = lower(:a) "
                    # CAST IS LOAD-BEARING. A bare `:c - interval '2 days'` sends
                    # an UNTYPED parameter and Postgres resolves the subtraction
                    # before it looks at `commence_time`: the only `? - interval`
                    # operator available is `interval - interval`, so `:c` becomes
                    # an interval and the predicate dies as `operator does not
                    # exist: timestamp with time zone >= interval`. Measured on
                    # the dyno by repair_2947; sqlglot parses the uncast version
                    # happily, only type resolution rejects it.
                    "AND commence_time BETWEEN CAST(:c AS timestamptz) - interval '2 days' "
                    "                      AND CAST(:c AS timestamptz) + interval '2 days' LIMIT 1"
                ),
                {
                    "eid": row["id"],
                    "h": row["new_home"],
                    "a": row["new_away"],
                    "c": row["commence"],
                },
            )
        ).first()
        if clash:
            dropped.append((row, f"CLEAN_COUNTERPART_EXISTS:{clash[0]}"))
        else:
            kept.append(row)
    return kept, dropped


async def ensure_backup(session, plan):
    """Idempotent `NOT EXISTS` top-up of the pre-repair names."""
    from sqlalchemy import text

    await session.execute(
        text(
            f"CREATE TABLE IF NOT EXISTS {BAK_TABLE} ("
            "  event_id bigint PRIMARY KEY,"
            "  home_team_name text NOT NULL,"
            "  away_team_name text NOT NULL,"
            # What the repair intends to write, so the undo can guard on the
            # exact value rather than infer it. Without this a restore has to
            # guess whether a differing current name is the repair's or someone
            # else's, and guessing is how an undo stomps a later decision.
            "  new_home_team_name text NOT NULL,"
            "  new_away_team_name text NOT NULL,"
            "  backed_up_at timestamptz NOT NULL DEFAULT now())"
        )
    )
    for chunk in [plan[i : i + CHUNK] for i in range(0, len(plan), CHUNK)]:
        for row in chunk:
            await session.execute(
                text(
                    f"INSERT INTO {BAK_TABLE} (event_id, home_team_name, away_team_name,"
                    "                          new_home_team_name, new_away_team_name) "
                    "SELECT :eid, :h, :a, :nh, :na WHERE NOT EXISTS "
                    f"(SELECT 1 FROM {BAK_TABLE} WHERE event_id = :eid)"
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

    covered = (
        await session.execute(
            text(f"SELECT count(*) FROM {BAK_TABLE} WHERE event_id = ANY(:ids)"),
            {"ids": [r["id"] for r in plan]},
        )
    ).scalar_one()
    return covered


async def apply_plan(session, plan):
    from sqlalchemy import text

    written = 0
    for chunk in [plan[i : i + CHUNK] for i in range(0, len(plan), CHUNK)]:
        for row in chunk:
            # Guarded on the OLD values: a row something else has since renamed
            # is left alone rather than stomped.
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


async def run(args):
    session_factory = _session_factory()

    async with session_factory() as session:
        plan, skipped = await build_plan(session, limit=args.limit)
        candidates = len(plan) + len(skipped)
        print(f"candidates (both names in the bare namespace, kalshi market live): {candidates}")
        print(f"  replay reconstructs the stored pair : {len(plan)}")
        print(f"  skipped                             : {len(skipped)}")

        if candidates < MIN_EXPECTED_POPULATION and not args.allow_small and not args.limit:
            print(
                f"REFUSING: candidates {candidates} < floor {MIN_EXPECTED_POPULATION}. "
                "The predicate probably broke. Re-run with --allow-small if the "
                "repair really has already run."
            )
            return 2

        plan, dropped = await drop_collisions(session, plan)
        print(f"  dropped as collisions               : {len(dropped)}")
        print(f"  TO RENAME                           : {len(plan)}")

        measured = {
            "candidates": candidates,
            "plan": len(plan),
            "no_reconstruct": sum(1 for *_, why in skipped if why == "NO_RECONSTRUCT"),
            "already_correct": sum(1 for *_, why in skipped if why == "ALREADY_CORRECT"),
            "twin_within_plan": sum(1 for _, why in dropped if why == "TWIN_WITHIN_PLAN"),
            "clean_counterpart": sum(
                1 for _, why in dropped if why.startswith("CLEAN_COUNTERPART_EXISTS")
            ),
        }
        drift = disposition_drift(measured, args.expect_plan)
        print("disposition (expected -> measured):")
        for key, value in measured.items():
            expected_value, flag = (
                (drift[key][0], "  <- DRIFT") if key in drift else (value, "")
            )
            print(f"    {key:20} {expected_value:>5} -> {value:>5}{flag}")

        for row, why in dropped:
            print(f"    SKIP {row['id']}  {why}  -> {row['new_home']} vs {row['new_away']}")
        for event_id, home, away, why in skipped[:20]:
            print(f"    SKIP {event_id}  {why}  {home} vs {away}")

        for row in plan[:15]:
            swap = "  (orientation preserved)" if row["swapped"] else ""
            print(
                f"    {row['id']}  {row['old_home']} vs {row['old_away']}"
                f"\n         -> {row['new_home']} vs {row['new_away']}{swap}"
            )
        if len(plan) > 15:
            print(f"    ... and {len(plan) - 15} more")

        if not plan:
            print("nothing to do")
            return 0

        # EVERY refusal that can stop an apply is decided here, before the first
        # write of the run — the backup table included. In repair_2947 the drift
        # guard sat below `ensure_backup` and below an `args.limit` exemption, so
        # a `--limit N --backup --apply` run wrote a backup and renamed rows while
        # disagreeing with its own claim, then exited 0 (CERT-903).
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
            if drift:
                print(
                    "REFUSING: the plan does not match the pre-registered disposition — "
                    + ", ".join(f"{k} {exp}->{got}" for k, (exp, got) in drift.items())
                    + ".\nThis is the guard working, not a bug: the population moved, or "
                    "a claim in the docstring is wrong. Read the rows above, decide which, "
                    "then re-run with --expect-plan N to restate the claim deliberately."
                )
                return 6

        if args.backup:
            covered = await ensure_backup(session, plan)
            print(f"backup: {covered}/{len(plan)} of the plan is in {BAK_TABLE}")
            if covered < len(plan):
                print("REFUSING: backup does not cover the plan.")
                return 3

        if not args.apply:
            print("DRY RUN — nothing written. Re-run with --backup --apply.")
            return 0

        written = await apply_plan(session, plan)
        print(f"APPLIED: {written} events renamed (planned {len(plan)})")
        print(
            "undo: heroku run:detached -a bainluck "
            '"python3 scripts/restore_3672_bare_namespace_event_names.py --apply"'
        )
        return 0 if written == len(plan) else 5


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--backup", action="store_true", help="top up the D51 backup table")
    p.add_argument("--apply", action="store_true", help="write the renames (needs --backup)")
    p.add_argument(
        "--limit",
        type=int,
        default=0,
        help="plan at most N events — a dry-run tool, REFUSED together with --apply "
        "because a subset can never match the pre-registered disposition",
    )
    p.add_argument("--allow-small", action="store_true", help="bypass the population floor")
    p.add_argument(
        "--expect-plan",
        type=int,
        default=None,
        help="restate the expected rename count when the population has legitimately "
        "moved; without it a plan differing from EXPECTED refuses to apply",
    )
    args = p.parse_args()
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
