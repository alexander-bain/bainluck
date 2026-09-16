"""#6590 — un-say the Draw we crowned on a match that finished 3-0.

WHAT A READER SEES TODAY. `/futures/60015154` prints **"Settled — SK Beveren
won."** and then, directly beneath it, a Final Results card that badges BOTH
`SK Beveren` **and** `Draw (SK Beveren vs. Oud-Heverlee Leuven)` as
`Won · 100% Settled`. One settled question, two winners, one of them the draw in
a match that finished 3-0. Photographed at 390px in
`artifacts/lane1b-draw-crowning/BEFORE-futures-60015154-two-winners-390-1755Z.png`.

THE ROW REFUTES ITSELF, which is why no ground-truth fetch is needed to convict
it. Outcome `223837849` stores `is_winner = TRUE` beside its own
`current_probability = 0.000500` — the market priced that draw at five
hundredths of one percent and we graded it a winner anyway. The linked event
`15298068` is `completed`, `SK Beveren 3 - Leuven 0`, `completed_at`
2026-09-07 00:01:16Z.

WHERE IT CAME FROM. Both two-outcome team-vs-team loops in
`app/tasks/backfill_winners.py` side a leg by whitespace-token intersection, and
`.split()` leaves punctuation attached to the token: `"leuven)"` is not
`"leuven"`, so the away-exclusion test misses while `beveren` matches the home
team cleanly, and the Draw leg inherits the home team's win. The producer is
fixed in the commit this script ships with.

🔴 WHY A REPAIR IS NEEDED AT ALL, AND WHY THE PRODUCER FIX CANNOT DO IT.
`game_score` is not in `OVERWRITABLE_WINNER_SOURCES_SQL`, and both changed
resolvers admit a market only when it holds NO non-overwritable TRUE winner.
This market holds two. So the fixed producer is locked out of this row
permanently: it will never re-grade it, and the page keeps printing two winners
for as long as the row stands. That is CERT-2976's finding and this script is
its answer — the forward fix stops the next one, this stops the live one.

THE COHORT, derived on production 2026-09-16 18:5xZ by running this script's own
predicate — "a draw/tie leg stored TRUE by `game_score` on a completed event
whose final score is NOT level":

    market_type   source      rows   whose repair
    duel          polymarket     1   THIS ONE  (outcome 223837849)
    field         kalshi        14   #5221's, and this script refuses them
    ----------------------------------------------------------------
    total                       15

🔴 THE FOURTEEN ARE NOT OURS AND MUST NOT BE TOUCHED. Every one of them is a
`First Half Winner` / `Second Half Winner` market whose outcome is `Tie` — and a
half CAN genuinely be tied on a game that ended 91-84. The EVENT's final score
does not adjudicate a SEGMENT market, so a filter that judges them by it is
wrong about all fourteen. They come from the `period_scores[0]` substitution and
belong to `repair_5221_second_half_graded_from_the_first_quarter.py`, which is
built and awaiting its attended run over a 1,558-row cohort. A second repair
over those rows would collide with it.

So this script refuses a segment market TWICE, by two independent tests: the
market name must carry no period token, AND `market_type` must be `duel`. Either
alone excludes all fourteen; requiring both means a change to one recogniser
cannot silently widen the write.

WHAT IT WRITES. One column of one row: `futures_outcomes.is_winner` TRUE → FALSE
on outcome `223837849`. `resolution_source` stays `game_score` — the game score
IS what graded this leg, and it grades it a loser; rewriting the provenance
would lose the fact that we now agree with it. The sibling `SK Beveren` leg is
left TRUE because it is correct, which is the whole postcondition: after the
write the market holds EXACTLY ONE winner, not zero.

🔴 CLEARING THE WRONG LEG WITHOUT CHECKING THE SURVIVOR IS HOW THIS GOES WRONG.
CERT-2631 blocked #5221's first presentation for turning "the wrong verdict"
into "no verdict, for good". `--apply` here refuses unless exactly one TRUE leg
survives on every market it touches, computed BEFORE the write from the market's
full leg set.

D51(b) — `--apply` REFUSES until `--backup` has copied the row, and the undo is
one command:

    python3 scripts/repair_6590_a_draw_crowned_as_a_team.py             # plan only
    python3 scripts/repair_6590_a_draw_crowned_as_a_team.py --backup    # copy + reconcile
    python3 scripts/repair_6590_a_draw_crowned_as_a_team.py --apply
    python3 scripts/repair_6590_a_draw_crowned_as_a_team.py --restore   # the undo

Heroku one-off (gotcha #48 — a non-detached run returns empty stdout that reads
like success; PROJECT_PATH=backend puts scripts at /app, so NO `cd backend`):

    heroku run:detached -a bainluck-heavy \\
      "python3 scripts/repair_6590_a_draw_crowned_as_a_team.py --backup"

Standing notice 47(c): this creates its backup table at runtime and rewrites a
served column, so the invocation IS the attended step and it happens on one
named app.
"""
import argparse
import asyncio
import os
import re
import sys
from typing import NamedTuple, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

#: The one row this repair exists for. The screen DERIVES its plan from the
#: predicate rather than reading this set, and then the plan is checked against
#: it: a derivation that finds something else means production moved under the
#: measurement, which is a stop, not a licence to write.
EXPECTED_OUTCOME_IDS = frozenset({223837849})

BAK_TABLE = "bak_6590_futures_outcomes"

#: Notice 47(c) — the one app an attended write may happen on.
PRODUCER_APP = "bainluck-heavy"

#: The only market family whose result the EVENT's final score adjudicates: a
#: whole-game, two-team result market. Fail-closed — anything else is refused
#: rather than reasoned about.
WHOLE_GAME_MARKET_TYPES = frozenset({"duel"})

#: A market that asks about part of a game. The event's final score says nothing
#: about it, so this repair must never judge one. `\b` on both ends so a club
#: called "Halftime FC" would need the word alone to trip it, and `1h`/`2h` are
#: matched only as standalone tokens ("1H Winner"), never inside a word.
_SEGMENT_TOKENS = re.compile(
    r"\b("
    r"first half|second half|1st half|2nd half|halftime|half time|"
    r"quarter|period|inning|frame|"
    r"[12]h|q[1-4]|p[1-3]"
    r")\b",
    re.IGNORECASE,
)

#: The draw/tie leg recogniser. Deliberately NOT a bare substring test: "Tied
#: Ends" and a club whose name contains "drawn" are not draw legs, so the token
#: has to stand alone.
_DRAW_TOKENS = re.compile(r"(^|[^a-z])(draw|tie|tied|level)([^a-z]|$)", re.IGNORECASE)


def is_draw_outcome(name: Optional[str]) -> bool:
    """Is this leg the DRAW leg of its market?"""
    return bool(name) and bool(_DRAW_TOKENS.search(name))


def names_a_segment(*names: Optional[str]) -> bool:
    """Does any of these names say the market is about PART of a game?"""
    return any(bool(n) and bool(_SEGMENT_TOKENS.search(n)) for n in names)


class Refusal(NamedTuple):
    outcome_id: int
    reason: str


class Screen(NamedTuple):
    plan: list          # outcome ids this repair will demote
    refuse: list        # Refusal, one per row left alone, with its reason
    markets: dict       # market_id -> outcome ids planned on that market


def screen_candidates(rows) -> Screen:
    """Which rows may be demoted, and WHY each of the others may not.

    Every clause is a refusal with a reason rather than a silent filter: the
    fourteen rows this must not touch are the point of the script, so they have
    to come out the other end NAMED, not merely absent.
    """
    plan: list = []
    refuse: list = []
    markets: dict = {}

    for r in rows:
        oid = r["outcome_id"]

        if not r.get("is_winner"):
            refuse.append(Refusal(oid, "not stored as a winner — nothing to un-say"))
            continue
        if r.get("resolution_source") != "game_score":
            refuse.append(Refusal(
                oid, f"graded by {r.get('resolution_source')!r}, not 'game_score' — "
                     f"a different writer owns this verdict"))
            continue
        if not is_draw_outcome(r.get("outcome_name")):
            refuse.append(Refusal(oid, "not a draw leg — a team leg crowned wrongly "
                                       "is a different defect"))
            continue
        if names_a_segment(r.get("market_name"), r.get("outcome_name")):
            refuse.append(Refusal(
                oid, "SEGMENT market — a half/quarter can genuinely be tied on a "
                     "game that was not; #5221 owns these"))
            continue
        if r.get("market_type") not in WHOLE_GAME_MARKET_TYPES:
            refuse.append(Refusal(
                oid, f"market_type {r.get('market_type')!r} is not a whole-game "
                     f"result market — the final score does not adjudicate it"))
            continue
        if r.get("event_status") != "completed":
            refuse.append(Refusal(oid, f"event is {r.get('event_status')!r}, not "
                                       f"completed — the final score is not final"))
            continue
        if r.get("home_score") is None or r.get("away_score") is None:
            refuse.append(Refusal(oid, "event has no final score — nothing refutes "
                                       "the stored verdict"))
            continue
        if r["home_score"] == r["away_score"]:
            refuse.append(Refusal(oid, "the match WAS level — this draw leg is "
                                       "correct and must stand"))
            continue

        plan.append(oid)
        markets.setdefault(r["market_id"], []).append(oid)

    return Screen(plan=plan, refuse=refuse, markets=markets)


def identity_refusal(plan, allow_new: bool) -> Optional[str]:
    """Does the derived plan match the cohort this repair was measured on?"""
    found = frozenset(plan)
    if found == EXPECTED_OUTCOME_IDS:
        return None
    if allow_new:
        return None
    extra = sorted(found - EXPECTED_OUTCOME_IDS)
    missing = sorted(EXPECTED_OUTCOME_IDS - found)
    parts = []
    if extra:
        parts.append(f"{len(extra)} row(s) this repair never measured: {extra}")
    if missing:
        parts.append(f"{len(missing)} expected row(s) already gone: {missing}")
    return (
        "REFUSING: the derived plan is not the measured cohort — "
        + "; ".join(parts)
        + ". Production moved under the measurement. Re-measure and re-present; "
          "pass --allow-new only once you have read the new rows yourself."
    )


class Survivor(NamedTuple):
    market_id: int
    surviving: list
    ok: bool


def check_survivors(market_legs, markets) -> list:
    """After demoting the planned legs, does each market keep EXACTLY ONE winner?

    Computed BEFORE the write, from the market's full leg set, because the
    failure this guards is the one CERT-2631 caught on #5221: clearing a wrong
    verdict and leaving the market with no verdict at all is worse than what it
    found.
    """
    out = []
    for market_id, planned in markets.items():
        legs = market_legs.get(market_id, [])
        surviving = [
            leg["outcome_id"] for leg in legs
            if leg.get("is_winner") and leg["outcome_id"] not in planned
        ]
        out.append(Survivor(market_id, surviving, len(surviving) == 1))
    return out


def backup_is_exact(recon) -> bool:
    """The D51 gate: every planned row is in the backup, and something was checked.

    `all()` over an empty mapping is True, so the emptiness test is not
    decoration — without it a reconciliation that inspected nothing reads as a
    clean pass and `--apply` proceeds with no undo (gotcha #53).
    """
    return bool(recon) and all(n == 0 for n in recon.values())


def wrong_app_refusal(args) -> Optional[str]:
    """Why this invocation may not WRITE, or None if it may.

    A dry run only reads, so it runs anywhere. A write must be the attended
    invocation standing notice 47(c) describes, and the only thing separating an
    attended `heroku run:detached` from a laptop holding production credentials
    is which dyno it is on. Unset means not a dyno at all — precisely the case
    this exists to stop — so it refuses too rather than falling through.
    """
    if not (args.apply or args.backup or args.restore):
        return None

    app = os.environ.get("HEROKU_APP_NAME")
    if app == PRODUCER_APP:
        return None

    where = f"'{app}'" if app else "not a Heroku dyno (HEROKU_APP_NAME is unset)"
    return (
        f"REFUSING to write: this is {where}, not '{PRODUCER_APP}'. This script "
        f"creates its backup table at runtime and rewrites a served column, so "
        f"the invocation IS the attended step (standing notice 47(c)) and it "
        f"happens on one named app. Re-run with `heroku run:detached -a "
        f"{PRODUCER_APP} \"python3 scripts/{os.path.basename(__file__)} ...\"`."
    )


# ── the store seam ───────────────────────────────────────────────────────────
# Every statement this repair issues lives behind these six methods, so the
# behavioural test can drive the REAL sequence — dry-run, backup, apply, restore
# — over seeded rows. The alternative, a Postgres-backed test, is env-gated and
# SKIPS in CI, and a skipped guard is not a guard.

_PLAN_SQL = """
SELECT fo.id AS outcome_id, fm.id AS market_id, fm.market_type,
       fm.name AS market_name, fo.name AS outcome_name,
       fo.is_winner, fo.resolution_source,
       e.id AS event_id, e.status AS event_status,
       e.home_score, e.away_score
  FROM futures_outcomes fo
  JOIN futures_markets fm ON fm.id = fo.market_id
  JOIN events e ON e.id = fm.event_id
 WHERE fo.is_winner IS TRUE
   AND fo.resolution_source = 'game_score'
   AND LOWER(fo.name) ~ '(^|[^a-z])(draw|tie|tied|level)([^a-z]|$)'
   AND e.status = 'completed'
   AND e.home_score IS NOT NULL
   AND e.away_score IS NOT NULL
   AND e.home_score <> e.away_score
 ORDER BY fo.id
"""

_LEGS_SQL = """
SELECT id AS outcome_id, market_id, name, is_winner
  FROM futures_outcomes
 WHERE market_id = ANY(CAST(:market_ids AS int[]))
 ORDER BY id
"""

SQL = {
    # LIKE copies columns and types but NOT the foreign keys — a backup that
    # cascaded with its source would be no backup at all.
    "bak_create": f"CREATE TABLE IF NOT EXISTS {BAK_TABLE} "
                  f"(LIKE futures_outcomes INCLUDING DEFAULTS)",
    "bak_index": f"CREATE UNIQUE INDEX IF NOT EXISTS {BAK_TABLE}_pk "
                 f"ON {BAK_TABLE} (id)",
    "bak_copy": f"INSERT INTO {BAK_TABLE} SELECT s.* FROM futures_outcomes s "
                f"WHERE s.id = ANY(CAST(:ids AS int[])) "
                f"AND NOT EXISTS (SELECT 1 FROM {BAK_TABLE} b WHERE b.id = s.id)",
    "bak_missing": f"SELECT count(*) FROM futures_outcomes s "
                   f"WHERE s.id = ANY(CAST(:ids AS int[])) "
                   f"AND NOT EXISTS (SELECT 1 FROM {BAK_TABLE} b WHERE b.id = s.id)",
    # Asked BEFORE `bak_missing`, never instead: that statement names the backup
    # table in a subquery and raises UndefinedTable on a database that has never
    # been backed up — which is every database on the documented plan-only first
    # run (gotcha #53).
    "bak_exists": f"SELECT to_regclass('{BAK_TABLE}') IS NOT NULL",
    # A compare-and-swap on the value this repair exists to remove. If the fixed
    # producer or a settlement pass re-graded the row between the plan and the
    # write, `is_winner` is no longer TRUE and this updates nothing.
    "demote": "UPDATE futures_outcomes SET is_winner = FALSE "
              "WHERE id = ANY(CAST(:ids AS int[])) AND is_winner IS TRUE",
    "restore": f"UPDATE futures_outcomes f SET is_winner = b.is_winner "
               f"FROM {BAK_TABLE} b WHERE b.id = f.id",
}


class PgStore:
    """The production store. Every statement this repair issues is here."""

    def __init__(self, session):
        self.session = session

    async def _scalar(self, sql, **params):
        from sqlalchemy import text
        return (await self.session.execute(text(sql), params or None)).scalar()

    async def fetch_candidates(self):
        from sqlalchemy import text
        rows = (await self.session.execute(text(_PLAN_SQL))).mappings().all()
        return [dict(r) for r in rows]

    async def fetch_market_legs(self, market_ids):
        from sqlalchemy import text
        rows = (await self.session.execute(
            text(_LEGS_SQL), {"market_ids": list(market_ids)}
        )).mappings().all()
        legs: dict = {}
        for r in rows:
            legs.setdefault(r["market_id"], []).append(dict(r))
        return legs

    async def copy_to_backup(self, ids):
        from sqlalchemy import text
        await self.session.execute(text(SQL["bak_create"]))
        await self.session.execute(text(SQL["bak_index"]))
        await self.session.execute(text(SQL["bak_copy"]), {"ids": list(ids)})
        await self.session.commit()

    async def backup_missing(self, ids):
        """{outcome_id_count: missing} — empty when the table does not exist."""
        if not await self._scalar(SQL["bak_exists"]):
            return {}
        return {"missing": await self._scalar(SQL["bak_missing"], ids=list(ids))}

    async def demote(self, ids):
        from sqlalchemy import text
        res = await self.session.execute(text(SQL["demote"]), {"ids": list(ids)})
        await self.session.commit()
        return res.rowcount

    async def restore(self):
        from sqlalchemy import text
        if not await self._scalar(SQL["bak_exists"]):
            return 0
        res = await self.session.execute(text(SQL["restore"]))
        await self.session.commit()
        return res.rowcount


class Report(NamedTuple):
    planned: list
    refused: list
    survivors: list
    wrote: int
    restored: int
    blocked: Optional[str]
    lines: list


async def execute_repair(store, args) -> Report:
    """Plan, and then do exactly as much as the flags and the gates allow."""
    lines: list = []

    def say(s):
        lines.append(s)

    if args.restore:
        n = await store.restore()
        say(f"RESTORED {n} row(s) from {BAK_TABLE} — the stored verdicts are "
            f"back as they were before --apply.")
        return Report([], [], [], 0, n, None, lines)

    rows = await store.fetch_candidates()
    screen = screen_candidates(rows)
    say(f"=== #6590 draw-crowned-as-a-team: {len(rows)} candidate(s) ===")
    say(f"  will demote                       : {len(screen.plan)}")
    say(f"  left alone, with reason            : {len(screen.refuse)}")
    for r in screen.refuse:
        say(f"    - outcome {r.outcome_id}: {r.reason}")

    blocked = identity_refusal(screen.plan, args.allow_new)
    if blocked:
        say(blocked)
        return Report(screen.plan, screen.refuse, [], 0, 0, blocked, lines)

    legs = await store.fetch_market_legs(screen.markets.keys())
    survivors = check_survivors(legs, screen.markets)
    for s in survivors:
        say(f"  market {s.market_id}: {len(s.surviving)} winner(s) survive "
            f"{s.surviving} — {'OK' if s.ok else 'REFUSED'}")
    if not all(s.ok for s in survivors):
        blocked = ("REFUSING: a touched market would not be left with exactly one "
                   "winner. Clearing the wrong verdict into NO verdict is worse "
                   "than what this found (CERT-2631).")
        say(blocked)
        return Report(screen.plan, screen.refuse, survivors, 0, 0, blocked, lines)

    if args.backup:
        await store.copy_to_backup(screen.plan)
        say(f"BACKED UP {len(screen.plan)} row(s) into {BAK_TABLE}.")

    if not args.apply:
        say("DRY-RUN — no writes. Pass --backup to copy, then --apply to write; "
            "the undo is --restore.")
        return Report(screen.plan, screen.refuse, survivors, 0, 0, None, lines)

    recon = await store.backup_missing(screen.plan)
    if not backup_is_exact(recon):
        blocked = (f"REFUSING --apply: the backup does not cover the plan "
                   f"({recon or 'no backup table at all'}). Run --backup first "
                   f"(D51(b): a write without an undo is a one-way action).")
        say(blocked)
        return Report(screen.plan, screen.refuse, survivors, 0, 0, blocked, lines)

    wrote = await store.demote(screen.plan)
    say(f"APPLIED — demoted {wrote} row(s). Undo: "
        f"python3 scripts/{os.path.basename(__file__)} --restore")
    return Report(screen.plan, screen.refuse, survivors, wrote, 0, None, lines)


async def run(args) -> None:
    from app.tasks.base import get_task_session

    async with get_task_session() as session:
        report = await execute_repair(PgStore(session), args)

    for line in report.lines:
        print(line)
    if report.blocked:
        sys.exit(1)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--backup", action="store_true",
                   help="copy the planned rows into the backup table")
    p.add_argument("--apply", action="store_true",
                   help="write; refuses unless --backup has covered the plan")
    p.add_argument("--restore", action="store_true",
                   help="the undo — put the backed-up verdicts back")
    p.add_argument("--allow-new", action="store_true",
                   help="proceed even though the derived plan is not the "
                        "measured cohort; read the new rows first")
    args = p.parse_args()

    refusal = wrong_app_refusal(args)
    if refusal:
        print(refusal)
        sys.exit(2)

    asyncio.run(run(args))


if __name__ == "__main__":
    main()
