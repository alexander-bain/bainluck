"""#2000's first repair — put the May 9 first-half market back on the May 9 game.

THE SHIP: the Real Sociedad v Real Betis page for **2026-08-26** stops showing a
market from a **different fixture five weeks earlier**, graded with that other
fixture's result. A reader who opens event `15011303` today is served
`Real Sociedad vs Real Betis: First Half Winner` with `Real Betis` graded
`is_winner: true` at 0.995 — a verdict from the **May 9** match (2-2), printed on
the page for the **Aug 26** match (4-1). The market moves to the game it is
actually about, where it is correct and where its four siblings already sit.

THE DEFECT IS ONE ROW, AND IT IS THE PROVIDER'S OWN IDENTITY THAT NAMES IT.
`futures_markets` 15207269 carries the ticker `KXLALIGA1H-26MAY09RSORBB`. The
`26MAY09` token is Kalshi's statement of which fixture the market is about, and
gotcha #14 says to trust it over `commence_time`. It is linked to event
15011303, whose kick-off is 2026-08-26.

------------------------------------------------------------------------------
THE CORRESPONDENCE, FROM TWO INDEPENDENT STATEMENTS PLUS A PINNED TABLE
------------------------------------------------------------------------------

Nothing here fuzzy-matches a title, and nothing here parses a name. Both arms
are re-derived on every run and BOTH must agree with :data:`EXPECTED` before a
byte is written. Either alone is a single point of failure: the table cannot
notice the world moved, a derivation cannot notice it was pointed at the wrong
row.

**ARM A — the four siblings already answer it.** Every Kalshi market whose
ticker carries the same trailing token, measured on production 2026-09-22:

    15207257  KXLALIGATOTAL-26MAY09RSORBB   -> 14623338
    15207258  KXLALIGASPREAD-26MAY09RSORBB  -> 14623338
    15207259  KXLALIGABTTS-26MAY09RSORBB    -> 14623338
    15207268  KXLALIGAGAME-26MAY09RSORBB    -> 14623338
    15207269  KXLALIGA1H-26MAY09RSORBB      -> 15011303   <- the defect

Four of five on one event. This is #5621's standard: a rule that reproduces what
a healthy writer did on the siblings is evidence, where a rule tested only on the
row it wants to move is a restatement of the answer.

🔴 THE SIBLING QUERY MATCHES ON `split_part(external_id, '-', 2)`, NOT ON A
SUBSTRING. calibration/2748 measured the trap on 2026-09-22 and it is one dash
away from this script: of 10,833 Kalshi rows whose ticker CONTAINS `btts`, three
are basketball moneylines that hit it inside their trailing **team-code pair**
(`KXBSLGAME-26MAR220830MBBTTS`). A substring test on a Kalshi ticker hits team
codes. `RSORBB` is a team-code pair too — `LIKE '%RSORBB'` would be the same
class of mistake — so the token is compared whole, anchored on the dash the
series prefix ends at.

**ARM B — the shipped identity predicate, not a rule written here.**
:func:`app.utils.market_identity.market_identity_disputed` is production code
(`kalshi_resolution_sweep`, `container_assembly` both read this module) and it
answers exactly the question this repair asks:

    market_identity_disputed('KXLALIGA1H-26MAY09RSORBB', <15011303 2026-08-26>)
        -> True    the link on the page today is disputed
    market_identity_disputed('KXLALIGA1H-26MAY09RSORBB', <14623338 2026-05-09>)
        -> False   the target agrees with the ticker

It compares the ticker's own date against the event's game-date in US/Eastern —
the calendar the ticker uses — so a 20:20 ET kick-off that is the next day in UTC
is not a manufactured disagreement.

**WHOLE-POPULATION CONTROL, production 2026-09-22.** Arm B was driven over every
Kalshi `KXLALIGA*` market that carries a link — 1,510 rows, exported and run
through the shipped function locally:

    undisputed (the rule reproduces the stored link)   1327    87.9%
    disputed   (the rule contradicts the stored link)   183
    unparseable ticker                                    0

The 1,327 are the control that matters. The 183 are a real defect population and
they are **#6720**, not this ship — see the scope note below.

------------------------------------------------------------------------------
THE POPULATION IS FROZEN, AND THAT WAS CHECKED RATHER THAN ASSUMED
------------------------------------------------------------------------------

A one-shot repair of a value a live loop re-derives loses the race and lands
somewhere worse than it started (#7739, this lane, 2026-09-22). So:

*In code.* Every path that links a Kalshi game market filters
`FuturesMarket.event_id.is_(None)` — the three Phase 2 selectors
(`prediction_market_matching.py` 2682 / 2731 / 2933 / 3123) and the historical
backfill (9987 / 10009). Gotcha #15 is the rule they implement: a linked market
never re-enters the scan. The row is non-null before this repair and non-null
after it, so it is outside every one of them in both states.

*On the rows.* The four healthy siblings were last written 2026-09-15 11:31:59Z,
all four in the same transaction. The defect row was last written **2026-07-11
02:15:00Z** and has not moved in 73 days. The cohort's own freshness was read,
not a superset prefilter's.

*The one writer that could touch it is the one that makes this safe.* Phase 2
carries a "wrong-game unlink" (6264 / 6388) that NULLs a market whose ticker date
is far from its event's. It has never reached this row — it is settled and out of
the scan — but if it ever did, it would fire on the state BEFORE this repair and
not after: once the market is on 14623338 the ticker and the event agree, so the
unlink condition is false. This repair moves the row from the only state that
writer would object to into the state it would leave alone.

------------------------------------------------------------------------------
WHAT IS WRITTEN — ONE COLUMN, ONE ROW, NO CHILD
------------------------------------------------------------------------------

    futures_markets.event_id   15011303 -> 14623338

Nothing else. No outcome, no price, no `is_winner`, no `opening_probability`, no
settlement, no event row, no blend key, nothing deleted. The three
`futures_outcomes` rows are counted before and after and the apply refuses if the
number moved.

This is an OVERWRITE of a non-null link, which the sibling repair (#5621) never
did — its rows were NULL. So the compare-and-set names the value being replaced:

    UPDATE futures_markets SET event_id = :to_eid
     WHERE id = :mid AND external_id = :ticker AND event_id = :from_eid

If anything relinks the row between the plan and the apply, this matches zero
rows and the run refuses and rolls back rather than overwriting a decision it
never read.

TARGET COLLISION, checked every run: 14623338 holds four markets and **no other
`KXLALIGA1H`**, so this adds rather than collides. That check is anchored on
`split_part(external_id, '-', 1)` — the series prefix — for the same reason Arm A
is.

------------------------------------------------------------------------------
WHAT IT REFUSES
------------------------------------------------------------------------------

  * `ALREADY_RELINKED`     already on the target — no-op, and the run is
                           idempotent through it.
  * `UNEXPECTED_LINKAGE`   it points at neither the registered wrong event nor
                           the target. Never overwritten: a link this script did
                           not predict is a decision by something it cannot see.
  * `IDENTITY_CHANGED`     the id and the ticker no longer name the same single
                           row.
  * `RESPORTED`            no longer resolved tier-5 Kalshi La Liga.
  * `CHILD_COUNT_MOVED`    the outcome count is not the 3 that were measured.
  * `SIBLINGS_DISAGREE`    Arm A no longer returns exactly one event with the
                           four siblings on it.
  * `NOT_DISPUTED`         Arm B says the CURRENT link is fine. The premise of
                           the repair is gone; stop and look.
  * `TARGET_DISPUTED`      Arm B says the TARGET would be wrong too.
  * `TARGET_UNFIT`         the target is missing, not ESPN-anchored, not
                           completed, or already holds a `KXLALIGA1H`.
  * `PLAN_DISAGREES`       a derivation and `EXPECTED` name different rows.

------------------------------------------------------------------------------
SCOPE — WHAT THIS IS NOT
------------------------------------------------------------------------------

**It is not #6720.** 183 linked `KXLALIGA*` markets fail Arm B. The sample is
dominated by a different shape — a real event plus a `voided` duplicate of the
SAME fixture with the markets scattered between them, many on events whose
`commence_time` is a uniform ingest stamp (`2026-07-10 20:50:02.209454Z`) rather
than a kick-off. #2000's specimen is the rarer shape: two genuinely different
fixtures, five weeks apart, both with real kick-off times and real scores. This
script's population is one pinned market id and one pinned ticker; it makes no
claim about the other 182 and cannot touch them.

**It is not the whole of #2000.** Event 15011303 also carries a frozen `kalshi`
source at 0.01 in `win_probability_sources`, which surfaces as a chart legend
offering "Kalshi" with no line drawn. Moving this market does not clear that key
— it is a stored bag, not a recomputation. That is a SEPARATE ship (check
`utils/hero_probability.py:147` first: removing the key leaves the bag holding
only `betting_book_count: 1`). Until it lands, this repair strictly improves the
page — it removes wrong content and leaves a known, filed defect — and the after
-check must not be read as closing #2000.

------------------------------------------------------------------------------
D51 — BACKUP FIRST, ONE-COMMAND RESTORE
------------------------------------------------------------------------------

`--apply` REFUSES until `--backup` has copied the row into :data:`BACKUP_TABLE`
and the reconciliation is CONTENT-exact, not existence-exact: a backup taken
before an unrelated writer moved the row would otherwise stay stale, satisfy the
gate, and have the undo restore a value that was never overwritten. The insert
refreshes on conflict and the gate compares with `IS NOT DISTINCT FROM`.

The reconciliation survives its own precondition: before `--backup` has ever run
the table does not exist, and `to_regclass` reads that as "every row is unbacked"
rather than raising `UndefinedTable` on the first dry run — which is the run the
runbook's step 1 is.

    UNDO:  python3 scripts/restore_2000_1h_relink.py --apply

USAGE

    python3 scripts/repair_2000_1h_relink.py            # dry run
    python3 scripts/repair_2000_1h_relink.py --backup
    python3 scripts/repair_2000_1h_relink.py --apply

RUNBOOK — attended, and the app gate is not advice. `match_prediction_markets`
and `poll_kalshi_markets` are `HEAVY_TASKS`, so the code that owns `event_id` on
this row is what is deployed to `bainluck-heavy`, released separately from the
web app and routinely behind it (standing notice 48). `--backup` and `--apply`
refuse anywhere else.

    1.  this merges, and `bainluck-heavy` carries the sha
        (`heroku releases -a bainluck-heavy`).
    2.  heroku run:detached -a bainluck-heavy -- \\
            python3 scripts/repair_2000_1h_relink.py
    3.  heroku run:detached -a bainluck-heavy -- \\
            python3 scripts/repair_2000_1h_relink.py --backup
    4.  heroku run:detached -a bainluck-heavy -- \\
            python3 scripts/repair_2000_1h_relink.py --apply

Non-detached `heroku run` fails silently in the sandbox (gotcha #48): use
`run:detached` and verify the side effect ~60s later. The after-check is a
`db-query` read of `futures_markets.event_id` for 15207269 plus the outcome
count, AND a LOOK at both event pages — unlike the sibling repair this one IS
reader-visible on both ends, though `game-markets` caches a completed event for
`FRESH_TTL_FINAL` so the LOOK may need the wait.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# The shipped identity predicate, imported rather than restated. A repair that
# re-implements the rule it is enforcing is a third opinion (#6295).
from app.utils.market_identity import (  # noqa: E402
    eastern_game_date,
    market_identity_disputed,
    ticker_game_date,
)

#: The one market this script may touch. Pinned by BOTH id and ticker.
TICKER = "KXLALIGA1H-26MAY09RSORBB"
MARKET_ID = 15207269

#: The link being replaced, and the link replacing it.
FROM_EVENT_ID = 15011303
TO_EVENT_ID = 14623338

#: Everything else that was measured on production 2026-09-22 and must still
#: hold. Each is CHECKED, none is trusted.
TARGET_ESPN_ID = "748485"
OUTCOME_COUNT = 3
SIBLING_COUNT = 4
TARGET_SPORT_KEY = "soccer_spain_la_liga"
TARGET_CATEGORY = "game_prop"
TARGET_TIER = 5

BACKUP_TABLE = "backup_2000_1h_relink_markets"

#: The app the PRODUCER runs on — see the runbook. This is what makes the guard
#: a statement about the interpreter that can actually re-write this row.
PRODUCER_APP = "bainluck-heavy"

#: The ticker's two anchored tokens. Derived from :data:`TICKER` rather than
#: written out, so the constant and the queries can never drift apart.
SERIES_PREFIX = TICKER.split("-", 1)[0]  # 'KXLALIGA1H'
GAME_TOKEN = TICKER.split("-", 1)[1]  # '26MAY09RSORBB'

#: Verdicts. `RELINK` is the only one that writes.
RELINK = "RELINK"
ALREADY_RELINKED = "ALREADY_RELINKED"
UNEXPECTED_LINKAGE = "UNEXPECTED_LINKAGE"
IDENTITY_CHANGED = "IDENTITY_CHANGED"
RESPORTED = "RESPORTED"
CHILD_COUNT_MOVED = "CHILD_COUNT_MOVED"
SIBLINGS_DISAGREE = "SIBLINGS_DISAGREE"
NOT_DISPUTED = "NOT_DISPUTED"
TARGET_DISPUTED = "TARGET_DISPUTED"
TARGET_UNFIT = "TARGET_UNFIT"
PLAN_DISAGREES = "PLAN_DISAGREES"

#: Verdicts that mean "stop", as opposed to "nothing to do here".
BLOCKING = (
    UNEXPECTED_LINKAGE,
    IDENTITY_CHANGED,
    RESPORTED,
    CHILD_COUNT_MOVED,
    SIBLINGS_DISAGREE,
    NOT_DISPUTED,
    TARGET_DISPUTED,
    TARGET_UNFIT,
    PLAN_DISAGREES,
)

#: The market row, read by ID and by TICKER together. Both must name the same
#: single row or this is not the row the plan was built on.
_MARKET_SQL = """
SELECT f.id,
       f.external_id,
       f.event_id,
       f.source,
       f.status,
       f.market_tier,
       f.llm_sport_category,
       s.key AS sport_key,
       (SELECT count(*) FROM futures_outcomes o WHERE o.market_id = f.id)
           AS outcome_count
  FROM futures_markets f
  LEFT JOIN sports s ON s.id = f.sport_id
 WHERE f.id = :mid OR f.external_id = :ticker
"""

#: ARM A. The siblings' own answer, grouped. `split_part(..., '-', 2)` compares
#: the game token WHOLE — see the header on why a substring here is a bug.
_SIBLINGS_SQL = """
SELECT f.event_id, count(*) AS n
  FROM futures_markets f
 WHERE split_part(f.external_id, '-', 2) = :token
   AND f.source = 'kalshi'
   AND f.id <> :mid
 GROUP BY f.event_id
 ORDER BY n DESC
"""

#: Both events, so Arm B can be asked about each. No name is matched.
_EVENTS_SQL = """
SELECT e.id, e.espn_id, e.home_team_name, e.away_team_name,
       e.commence_time, e.status, e.home_score, e.away_score,
       s.key AS sport_key
  FROM events e
  LEFT JOIN sports s ON s.id = e.sport_id
 WHERE e.id = ANY(:ids)
"""

#: The collision control, anchored on the SERIES prefix.
_COLLISION_SQL = """
SELECT f.id, f.external_id
  FROM futures_markets f
 WHERE f.event_id = :eid
   AND split_part(f.external_id, '-', 1) = :prefix
   AND f.id <> :mid
"""


def shipped_predicate_is_sane() -> bool:
    """The imported predicate still answers the two questions this plan rests on.

    The analogue of the sibling repair's `tap_is_off()`: a statement about THIS
    interpreter, made before it writes. `market_identity_disputed` is shipped
    code owned elsewhere; if its semantics move under this script, both arms of
    the derivation would move with it silently and the pinned table would be the
    only thing left. Pure function calls on literal datetimes — no database, no
    network, and it runs on every invocation including the dry run.
    """
    aug = datetime(2026, 8, 26, 19, 0, tzinfo=timezone.utc)
    may = datetime(2026, 5, 9, 19, 0, tzinfo=timezone.utc)
    return (
        ticker_game_date(TICKER) is not None
        and market_identity_disputed(TICKER, aug) is True
        and market_identity_disputed(TICKER, may) is False
    )


def wrong_app_refusal(args) -> str | None:
    """Why this invocation may not write, or `None`.

    `getattr`, because the undo's parser defines no `--backup`: one refusal
    serving two programs must not raise on a flag only one of them has.

    UNSET refuses too. Unset means a laptop pointed at the production database
    with whatever happens to be checked out, which is the case this gate is for.
    """
    if not (getattr(args, "apply", False) or getattr(args, "backup", False)):
        return None

    app = os.environ.get("HEROKU_APP_NAME")
    if app == PRODUCER_APP:
        return None

    where = f"'{app}'" if app else "not a Heroku dyno (HEROKU_APP_NAME is unset)"
    return (
        f"REFUSING to write: this is {where}, not '{PRODUCER_APP}'. "
        "`match_prediction_markets` and `poll_kalshi_markets` are HEAVY_TASKS, so "
        "the code that owns `event_id` on this row is what is deployed to "
        f"'{PRODUCER_APP}', an app released separately from the web app and "
        "routinely behind it (standing notice 48). Re-run with "
        f"`heroku run:detached -a {PRODUCER_APP}`."
    )


def _session_factory():
    """The app's real async session factory.

    Behind a named function so a test can substitute it AND prove the real one
    resolves. `repair_2947` shipped importing `app.database`, a module that has
    never existed, so it died on import while every unit test passed against a
    fake session (CERT-903). An entrypoint that cannot start is not a repair.
    """
    from app.services.database import async_session_maker

    return async_session_maker


async def plan(session):
    """The verdict for the one row. Returns `(verdict, detail)`.

    Deliberately one function: these checks are a single claim about a single
    row, and splitting them is how a caller ends up running six of ten.
    """
    from sqlalchemy import text

    rows = (
        await session.execute(text(_MARKET_SQL), {"mid": MARKET_ID, "ticker": TICKER})
    ).all()

    # The id and the ticker must name the SAME single row. Two rows means the
    # registered id now carries a different ticker.
    if len(rows) != 1:
        return (
            IDENTITY_CHANGED,
            f"id {MARKET_ID} and ticker {TICKER} match {len(rows)} rows, expected 1",
        )
    m = rows[0]
    if m.id != MARKET_ID or m.external_id != TICKER:
        return (
            IDENTITY_CHANGED,
            f"row {m.id} carries {m.external_id!r}, registered {MARKET_ID} / {TICKER!r}",
        )

    if (
        m.source != "kalshi"
        or m.status != "resolved"
        or m.market_tier != TARGET_TIER
        or m.llm_sport_category != TARGET_CATEGORY
        or m.sport_key != TARGET_SPORT_KEY
    ):
        return (
            RESPORTED,
            f"source={m.source} status={m.status} tier={m.market_tier} "
            f"category={m.llm_sport_category} sport={m.sport_key}",
        )

    if m.outcome_count != OUTCOME_COUNT:
        return (
            CHILD_COUNT_MOVED,
            f"{m.outcome_count} outcomes, measured {OUTCOME_COUNT}",
        )

    # Idempotence, and it must come before the dispute arms: once the row is on
    # the target, "the current link is disputed" is correctly false and would
    # otherwise read as NOT_DISPUTED on a run that has simply already happened.
    if m.event_id == TO_EVENT_ID:
        return (ALREADY_RELINKED, f"already on {TO_EVENT_ID} — nothing to do")
    if m.event_id != FROM_EVENT_ID:
        return (
            UNEXPECTED_LINKAGE,
            f"linked to {m.event_id}, this plan expects {FROM_EVENT_ID} "
            f"or {TO_EVENT_ID} — not overwritten",
        )

    # ── ARM A — the siblings' own answer ───────────────────────────────────
    sib = (
        await session.execute(
            text(_SIBLINGS_SQL), {"token": GAME_TOKEN, "mid": MARKET_ID}
        )
    ).all()
    if len(sib) != 1:
        spread = ", ".join(f"{r.event_id}x{r.n}" for r in sib) or "none"
        return (
            SIBLINGS_DISAGREE,
            f"token {GAME_TOKEN} siblings span {len(sib)} events ({spread}), expected 1",
        )
    if sib[0].n != SIBLING_COUNT:
        return (
            SIBLINGS_DISAGREE,
            f"{sib[0].n} siblings on {sib[0].event_id}, measured {SIBLING_COUNT}",
        )
    derived_target = sib[0].event_id

    # ── the two events ─────────────────────────────────────────────────────
    evs = {
        e.id: e
        for e in (
            await session.execute(
                text(_EVENTS_SQL), {"ids": [FROM_EVENT_ID, derived_target]}
            )
        ).all()
    }
    cur = evs.get(FROM_EVENT_ID)
    tgt = evs.get(derived_target)
    if cur is None:
        return (UNEXPECTED_LINKAGE, f"current event {FROM_EVENT_ID} no longer exists")
    if tgt is None:
        return (TARGET_UNFIT, f"derived target {derived_target} does not exist")

    # ── ARM B — the shipped predicate, on each event ───────────────────────
    if not market_identity_disputed(TICKER, cur.commence_time):
        return (
            NOT_DISPUTED,
            f"the shipped predicate does NOT dispute {TICKER} on event "
            f"{FROM_EVENT_ID} ({str(cur.commence_time)[:16]}) — the premise of "
            "this repair is gone",
        )
    if market_identity_disputed(TICKER, tgt.commence_time):
        return (
            TARGET_DISPUTED,
            f"the shipped predicate disputes {TICKER} on the target "
            f"{derived_target} ({str(tgt.commence_time)[:16]}) too",
        )

    # ── the target must be fit to receive it ───────────────────────────────
    # `espn_id IS NOT NULL` is the anchor requirement: an id-less row may never
    # be a relink target (gotcha #32 / ruling 048).
    if not tgt.espn_id:
        return (TARGET_UNFIT, f"target {derived_target} has no espn_id (unanchored)")
    if tgt.status not in ("completed", "closed"):
        return (TARGET_UNFIT, f"target {derived_target} is {tgt.status}, not completed")
    if tgt.sport_key != TARGET_SPORT_KEY:
        return (TARGET_UNFIT, f"target {derived_target} is {tgt.sport_key}")

    collide = (
        await session.execute(
            text(_COLLISION_SQL),
            {"eid": derived_target, "prefix": SERIES_PREFIX, "mid": MARKET_ID},
        )
    ).all()
    if collide:
        ids = ", ".join(f"{c.id}/{c.external_id}" for c in collide)
        return (
            TARGET_UNFIT,
            f"target {derived_target} already holds a {SERIES_PREFIX} market ({ids})",
        )

    # ── the derivations and the pinned table must agree ────────────────────
    if derived_target != TO_EVENT_ID or str(tgt.espn_id) != str(TARGET_ESPN_ID):
        return (
            PLAN_DISAGREES,
            f"derived {derived_target} espn={tgt.espn_id}, "
            f"registered {TO_EVENT_ID} espn={TARGET_ESPN_ID}",
        )

    return (
        RELINK,
        f"{TICKER} ({ticker_game_date(TICKER)}) {FROM_EVENT_ID} "
        f"[{eastern_game_date(cur.commence_time)}, {cur.away_score}-{cur.home_score}] "
        f"-> {TO_EVENT_ID} espn={tgt.espn_id} "
        f"[{eastern_game_date(tgt.commence_time)}, {tgt.away_score}-{tgt.home_score}, "
        f"{tgt.away_team_name} @ {tgt.home_team_name}]",
    )


async def run(args) -> int:
    from sqlalchemy import text

    if not shipped_predicate_is_sane():
        print(
            "REFUSING: `app.utils.market_identity.market_identity_disputed` does "
            "not answer this plan's two pinned questions on this deploy. Both "
            "arms of the derivation read that module, so a change in it moves "
            "this repair silently. Look before writing."
        )
        return 2

    refusal = wrong_app_refusal(args)
    if refusal:
        print(refusal)
        return 2

    session_factory = _session_factory()

    async with session_factory() as session:
        print("=== #2000 — the May 9 first-half market goes back on the May 9 game ===")
        verdict, detail = await plan(session)
        print(f"  {MARKET_ID} {TICKER}")
        print(f"  {verdict:<18} {detail}")

        if verdict in BLOCKING:
            print(f"\nREFUSING: {verdict}. Nothing was written.")
            return 2

        if args.backup:
            print("\n=== backup ===")
            await session.execute(
                text(
                    f"CREATE TABLE IF NOT EXISTS {BACKUP_TABLE} "
                    "(id bigint PRIMARY KEY, external_id text, event_id bigint)"
                )
            )
            await session.execute(
                text(
                    # DO UPDATE, not DO NOTHING: a second --backup after anything
                    # moved the row must REFRESH it, or the undo restores a value
                    # that was never the one we overwrote.
                    f"INSERT INTO {BACKUP_TABLE} (id, external_id, event_id) "
                    "SELECT id, external_id, event_id FROM futures_markets "
                    "WHERE id = :mid "
                    "ON CONFLICT (id) DO UPDATE SET "
                    "external_id = EXCLUDED.external_id, "
                    "event_id = EXCLUDED.event_id"
                ),
                {"mid": MARKET_ID},
            )
            await session.commit()
            print(f"  copied market {MARKET_ID} into {BACKUP_TABLE}")

        # THE RECONCILIATION MUST NOT ASSUME ITS OWN TABLE EXISTS — the first dry
        # run is the runbook's step 1, and it happens before any --backup.
        backup_exists = bool(
            (
                await session.execute(
                    text(f"SELECT to_regclass('public.{BACKUP_TABLE}') IS NOT NULL")
                )
            ).scalar()
        )
        if not backup_exists:
            # FAILS TOWARD REFUSING. An absent table means the row is unbacked,
            # which is the strongest reading and the one that stops `--apply`.
            unbacked = 1
            print(
                f"\n=== backup reconciliation (content-exact) === no {BACKUP_TABLE} "
                f"yet — unbacked-or-stale={unbacked}. Run --backup before --apply."
            )
        else:
            unbacked = (
                await session.execute(
                    text(
                        "SELECT count(*) FROM futures_markets f "
                        "WHERE f.id = :mid AND NOT EXISTS ("
                        f"  SELECT 1 FROM {BACKUP_TABLE} b WHERE b.id = f.id "
                        "   AND b.external_id IS NOT DISTINCT FROM f.external_id "
                        "   AND b.event_id IS NOT DISTINCT FROM f.event_id)"
                    ),
                    {"mid": MARKET_ID},
                )
            ).scalar()
            print(
                "\n=== backup reconciliation (content-exact) === "
                f"unbacked-or-stale={unbacked}"
            )

        if not args.apply:
            would = (
                f"{MARKET_ID}: {FROM_EVENT_ID} -> {TO_EVENT_ID}"
                if verdict == RELINK
                else "nothing"
            )
            print(f"\nDRY RUN — nothing written. Would set event_id on {would}.")
            return 0

        if unbacked:
            print(
                "\nREFUSING --apply: the backup does not match the row about to be "
                "written — either it is unbacked, or it MOVED since the backup was "
                "taken and the undo would restore a value that was never "
                "overwritten. Re-run --backup."
            )
            return 2

        if verdict != RELINK:
            print(f"\nNothing to write ({verdict}) — no-op.")
            return 0

        before = (
            await session.execute(
                text("SELECT count(*) FROM futures_outcomes WHERE market_id = :mid"),
                {"mid": MARKET_ID},
            )
        ).scalar()

        # Compare-and-set, naming the value being REPLACED. Unlike #5621 this is
        # an overwrite of a non-null link, so `event_id IS NULL` would be the
        # wrong guard and `id = :mid` alone would be no guard at all.
        result = await session.execute(
            text(
                "UPDATE futures_markets SET event_id = :to_eid "
                "WHERE id = :mid AND external_id = :ticker AND event_id = :from_eid"
            ),
            {
                "to_eid": TO_EVENT_ID,
                "mid": MARKET_ID,
                "ticker": TICKER,
                "from_eid": FROM_EVENT_ID,
            },
        )
        if result.rowcount != 1:
            await session.rollback()
            print(
                f"\nREFUSING --apply: the guarded UPDATE matched {result.rowcount} "
                "rows, not 1. The row changed between the plan and the write. "
                "Nothing was committed."
            )
            return 2

        after = (
            await session.execute(
                text("SELECT count(*) FROM futures_outcomes WHERE market_id = :mid"),
                {"mid": MARKET_ID},
            )
        ).scalar()
        if after != before:
            await session.rollback()
            print(
                f"\nREFUSING --apply: outcome count moved {before} -> {after} "
                "inside the transaction. Nothing was committed."
            )
            return 2

        await session.commit()
        print(
            f"\nAPPLIED: market {MARKET_ID} moved {FROM_EVENT_ID} -> {TO_EVENT_ID}; "
            f"{after} outcomes preserved (no child row written)."
        )
        print("UNDO: python3 scripts/restore_2000_1h_relink.py --apply")
        return 0


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--backup", action="store_true", help="top up the D51 backup table")
    p.add_argument(
        "--apply", action="store_true", help="write the relink (needs --backup)"
    )
    args = p.parse_args()
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
