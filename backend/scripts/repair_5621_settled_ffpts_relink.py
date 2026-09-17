"""#5621's residual — put the two settled NFL fantasy-points props back on their games.

THE SHIP: `KXNFLFFPTS-26SEP09NESEA` and `KXNFLFFPTS-26SEP10SFLAR` stop belonging
to nothing. Each is a settled Kalshi fantasy-points prop for a real Week 1 NFL
game — Patriots at Seahawks, 49ers at Rams — carrying 27 graded outcomes between
them with their opening prices, their current prices and `api_settlement`
verdicts. Both point at no event at all.

WHY THEY ARE LOOSE, AND WHY NOTHING WILL PICK THEM UP. `repair_5621_phantom_ffpts_events.py`
cleared `event_id` on these two, correctly: the rows they pointed at were phantom
basketball games this series minted, and a wrong link is worse than no link
because gotcha #15 says the matcher never re-times an already-linked market. That
script's header then predicted "Pass 1 links it to the real Week 1 fixture on the
next run". It did not, and authority's after-check (2026-09-17, issue #5621
clause 5) measured why: both markets settled BEFORE the repair ran, and the
settled sweep receipted them out of the scan eleven minutes after the apply —

    60617215 | settled_sweep | settled | 2026-09-16 23:50:00Z
    60617788 | settled_sweep | settled | 2026-09-16 23:50:00Z

so the population the matcher walks no longer contains them. They are correctly
SPORTED and permanently UNATTACHED. A forward-only mechanism cannot reach a row
it has already retired from its own scan, which is why this is a targeted relink
and not a matcher change.

------------------------------------------------------------------------------
THE CORRESPONDENCE IS PROVEN FROM PROVIDER IDENTITY, NOT FROM NAMES AND TIMES
------------------------------------------------------------------------------

Nothing here fuzzy-matches a title. The ticker IS the provider's statement of
which fixture the market is about, and it is read with the shipped resolver —
`extract_team_codes_from_ticker`, the same function the matcher uses — rather
than a regex written for this script. #6295's repair is the precedent followed
line for line: a repair whose parser differs from the fix's either leaves rows
behind or eats rows the fix would never have written.

    KXNFLFFPTS-26SEP09NESEA -> (('ne', 'Patriots'), ('sea', 'Seahawks'))
    KXNFLFFPTS-26SEP10SFLAR -> (('sf',  '49ers'),   ('lar', 'Rams'))

Kalshi writes the AWAY side first. That is not assumed, it is MEASURED on the
fourteen siblings of this exact series that the matcher linked itself — every
one of them stores the ticker's first code as the away team and its second as
the home team (see the control table below). A target must then also be
ESPN-anchored, NFL, played, and kicking off on the ticker's own calendar date in
US/Eastern — the venue's date, since a 20:20 ET kick-off is the NEXT day in UTC
and `26SEP09` would otherwise miss it.

WHOLE-POPULATION CONTROL, production 2026-09-17. The predicate below was driven
over all sixteen `KXNFLFFPTS` markets against every ESPN-anchored NFL event in
2026-09-08..2026-09-17 (16 candidates). For each ticker it returned EXACTLY ONE
candidate event, and for the fourteen the matcher had already linked it returned
the event those rows actually store:

    attached siblings   14    agree 14    disagree 0
    unattached          2     resolved 14780138 and 14632820

The fourteen are the control that matters. A rule that reproduces what a healthy
writer did on fourteen rows, with no disagreement and no ambiguity, is evidence;
a rule tested only on the two rows it wants to move is a restatement of the
answer. Both residuals resolve uniquely under the same predicate.

------------------------------------------------------------------------------
THE DIRECTIVE'S OWN PAIRING WAS TRANSPOSED, AND THAT IS WHY THE PLAN IS DERIVED
------------------------------------------------------------------------------

The assignment that commissioned this script named the pairs as

    60617215  KXNFLFFPTS-26SEP09NESEA -> 14780138
    60617788  KXNFLFFPTS-26SEP10SFLAR -> 14632820

and production says the market ids are the other way round: `60617215` IS
`-26SEP10SFLAR` and `60617788` IS `-26SEP09NESEA`. The TICKER->EVENT half was
right; the MARKET-ID->TICKER labels were swapped, inherited from a prior report
that listed tickers and ids in different orders. Acting on the ids alone would
have put each prop on the other game — two wrong links where there are currently
two absent ones, and gotcha #15 means the matcher would then never correct
either.

So the plan is DERIVED from the ticker every run and merely CHECKED against
:data:`EXPECTED`. Two independent statements must agree before anything is
written, and `EXPECTED` pins the market id to its ticker precisely so a
transposition is a refusal instead of a silent swap
(`TestIdentityIsPinnedToTheTicker`). A pre-registered table that is never
re-derived is a note; one that must agree with a live derivation is a gate.

------------------------------------------------------------------------------
WHAT IS WRITTEN — ONE COLUMN, TWO ROWS, NO CHILD
------------------------------------------------------------------------------

    futures_markets.event_id   NULL -> the event resolved above

Nothing else. No outcome is touched, no price, no `is_winner`, no
`opening_probability`, no settlement, no event row, no blend, nothing deleted.
The 27 `futures_outcomes` rows are counted before and after and the apply
refuses if the number moved. The two target events keep every market they
already have — this adds one each — and the sixteen real counterpart games the
phantom cleanup preserved are not in this script's reach at all: its population
is two market ids and two tickers, pinned.

The write itself is a compare-and-set:

    UPDATE futures_markets SET event_id = :eid
     WHERE id = :mid AND external_id = :ticker AND event_id IS NULL

so if another writer links the row between the plan and the apply, the UPDATE
matches zero rows, the run refuses and rolls back rather than overwriting a
decision it never read.

------------------------------------------------------------------------------
WHAT IT REFUSES, EACH A STATE THE DIRECTIVE NAMED
------------------------------------------------------------------------------

  * `ALREADY_LINKED`      the market already points at the right event — no-op,
                          and the whole run is idempotent through it.
  * `UNEXPECTED_LINKAGE`  it points somewhere ELSE. Never overwritten: a link
                          this script did not predict is a decision by something
                          it cannot see.
  * `IDENTITY_CHANGED`    the id registered for this ticker now carries a
                          different ticker, or the row is gone. The transposition
                          above is exactly this shape.
  * `NO_TARGET` /
    `AMBIGUOUS_TARGET`    zero, or more than one, candidate event. A relink with
                          two candidates is a guess.
  * `PLAN_DISAGREES`      the derivation and `EXPECTED` name different events.
                          Both are checked; agreement is the gate.
  * `RESPORTED`           the market is no longer NFL/football/tier-5/resolved
                          Kalshi. The phantom repair put it in that state; if
                          something moved it, stop and look.
  * `CHILD_COUNT_MOVED`   its outcome count is not the one measured. These rows
                          are settled and out of every scan, so a change means
                          the row is not the one this plan was built on.

------------------------------------------------------------------------------
THE RELINK IS NECESSARY AND IT IS NOT SUFFICIENT — SAID HERE, NOT DISCOVERED
------------------------------------------------------------------------------

Measured on production 2026-09-17, BEFORE this repair: of the fourteen
`KXNFLFFPTS` markets that are ALREADY correctly linked, **zero** reach a
reader on their game page. Both serve paths were read for seven of them —
`/api/events/{id}/related-futures` and `/api/events/{id}/game-markets` — and
neither payload contains the market or the word "Fantasy", while sibling prop
families on the same events (Passing Yards, Rushing Yards, Touchdowns) render
as settled Won/Lost cards.

The cause is in the serve path, not the link. `_classify_game_market` files this
series as `player_prop` (its siblings are `team_total`, which is why they show).
In the `player_prop` branch every leg of a settled market has priced out to 0.0
or 1.0, so none survives the 0.05–0.95 "interesting" band; the carve-out that is
supposed to catch exactly that cohort routes a leg onward only if
`prop_window_closed(...)` is true, and for this series it returns False. The legs
are therefore in neither list and leave the payload silently.

That is a second, separate defect, it lives in `routes/events.py` and
`utils/prop_window.py` which this lane does not own (standing notice 41), and it
is filed and routed rather than fixed here. This script is still the right and
necessary first half: while `event_id` is NULL no serve path can ever show these
markets, and the fix to the display half would leave them behind. What it
delivers on its own is a TRUTH repair — the prop belongs to the game, and the
database will say so.

------------------------------------------------------------------------------
D51 — BACKUP FIRST, ONE-COMMAND RESTORE
------------------------------------------------------------------------------

`--apply` REFUSES until `--backup` has copied both rows into
:data:`BACKUP_TABLE` and the reconciliation is CONTENT-exact, not
existence-exact — the `5621-BACKUP-RECONCILIATION-MUST-BE-CONTENT-EXACT` lesson
from the sibling repair, where a backup taken before an unrelated writer moved a
row stayed stale, satisfied the gate, and would have had the undo restore a value
that was never overwritten. The insert refreshes on conflict and the gate
compares with `IS NOT DISTINCT FROM`, so a stale backup FAILS.

The reconciliation also survives its own precondition: before `--backup` has ever
run the table does not exist, and `to_regclass` reads that as "every row is
unbacked" rather than raising `UndefinedTable` on the first dry run — which is
the run the runbook's step 0 is. Alex hit that crash on the sibling script
(`bainluck-heavy` run.9689) and his command was correct.

    UNDO:  python3 scripts/restore_5621_settled_ffpts_relink.py --apply

USAGE

    python3 scripts/repair_5621_settled_ffpts_relink.py            # dry run
    python3 scripts/repair_5621_settled_ffpts_relink.py --backup
    python3 scripts/repair_5621_settled_ffpts_relink.py --apply

RUNBOOK — attended, and the app gate is not advice. `match_prediction_markets`
and `poll_kalshi_markets` are HEAVY_TASKS, so the code that owns `event_id` on
these rows is what is deployed to `bainluck-heavy`, released separately from the
web app and routinely behind it (standing notice 48). `--backup`/`--apply` refuse
anywhere else, and `tap_is_off()` then inspects the producer's own ticker map: if
`kxnflffpts` is missing there, the prevention is not live on the app that writes,
these rows would be re-categorised basketball, and linking them now would be
building on a floor that is about to move.

    1.  this merges, and `bainluck-heavy` carries the sha
        (`heroku releases -a bainluck-heavy`).
    2.  heroku run:detached -a bainluck-heavy -- \\
            python3 scripts/repair_5621_settled_ffpts_relink.py
    3.  heroku run:detached -a bainluck-heavy -- \\
            python3 scripts/repair_5621_settled_ffpts_relink.py --backup
    4.  heroku run:detached -a bainluck-heavy -- \\
            python3 scripts/repair_5621_settled_ffpts_relink.py --apply

Non-detached `heroku run` fails silently in the sandbox (gotcha #48): use
`run:detached` and verify the side effect ~60s later. The after-check is a
`db-query` read of `futures_markets.event_id` for the two ids, plus the outcome
count — NOT a page LOOK, which cannot pay while the serve-path defect above is
open, and which the game-markets cache would hold for `FRESH_TTL_FINAL` (3600s)
anyway.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# The tap's own vocabulary and the matcher's own parser, imported rather than
# restated. A repair that re-implements either is a third opinion.
from app.utils.prediction_market_matching import (  # noqa: E402
    extract_team_codes_from_ticker,
)
from app.utils.sport_keys import KALSHI_TICKER_TO_SPORT_KEY  # noqa: E402

TICKER_PREFIX = "kxnflffpts"
TARGET_SPORT_KEY = "americanfootball_nfl"
TARGET_CATEGORY = "football"
BACKUP_TABLE = "backup_5621_relink_markets"

#: The app the PRODUCER runs on. See the runbook in the header — this is what
#: makes `tap_is_off()` a statement about the interpreter that can actually
#: re-write these rows rather than about whichever one happens to be running.
PRODUCER_APP = "bainluck-heavy"

#: Pre-registered disposition, measured on production 2026-09-17:
#: ``ticker -> (market_id, event_id, espn_id, outcome_count)``.
#:
#: KEYED ON THE TICKER, because the ticker is the provider's identity and the
#: market id is only our row for it. The commissioning directive paired these ids
#: with the opposite tickers (header), so a table keyed the other way would have
#: encoded the transposition as the plan. `IDENTITY_CHANGED` is the refusal that
#: catches it, and it can only exist because this mapping runs ticker-first.
#:
#: Every field is CHECKED, none is trusted: the event id is re-derived from the
#: ticker each run and must agree (`PLAN_DISAGREES`), the espn id must be the one
#: measured, and the outcome count must not have moved (`CHILD_COUNT_MOVED`).
EXPECTED: dict[str, tuple[int, int, str, int]] = {
    "KXNFLFFPTS-26SEP09NESEA": (60617788, 14780138, "401872656", 14),
    "KXNFLFFPTS-26SEP10SFLAR": (60617215, 14632820, "401872657", 13),
}

#: Verdicts. `RELINK` is the only one that writes.
RELINK = "RELINK"
ALREADY_LINKED = "ALREADY_LINKED"
UNEXPECTED_LINKAGE = "UNEXPECTED_LINKAGE"
IDENTITY_CHANGED = "IDENTITY_CHANGED"
NO_TARGET = "NO_TARGET"
AMBIGUOUS_TARGET = "AMBIGUOUS_TARGET"
PLAN_DISAGREES = "PLAN_DISAGREES"
RESPORTED = "RESPORTED"
CHILD_COUNT_MOVED = "CHILD_COUNT_MOVED"

#: Verdicts that mean "stop", as opposed to "nothing to do here". `--apply`
#: refuses the whole run on any of them rather than writing the rows that did
#: pass: two rows measured together are one claim about one state of the world,
#: and half of a plan whose other half surprised us is not a safer write.
BLOCKING = (
    UNEXPECTED_LINKAGE,
    IDENTITY_CHANGED,
    NO_TARGET,
    AMBIGUOUS_TARGET,
    PLAN_DISAGREES,
    RESPORTED,
    CHILD_COUNT_MOVED,
)

#: The market row, read by ID and by TICKER together. Both must be the
#: registered pair or the row is not the one this plan was built on.
_MARKET_SQL = """
SELECT f.id,
       f.external_id,
       f.event_id,
       f.source,
       f.status,
       f.market_tier,
       f.llm_sport_category,
       f.sport_id,
       s.key AS sport_key,
       (SELECT count(*) FROM futures_outcomes o WHERE o.market_id = f.id)
           AS outcome_count
  FROM futures_markets f
  LEFT JOIN sports s ON s.id = f.sport_id
 WHERE f.id = :mid OR f.external_id = :ticker
"""

#: The candidate events for one ticker, from the resolver's own output.
#:
#: `AT TIME ZONE 'America/New_York'` rather than an offset: the venue's calendar
#: date is what the ticker encodes, a 20:20 ET kick-off is the NEXT day in UTC,
#: and Postgres knows about DST where a hardcoded -4 would be wrong in November.
#:
#: The team clauses are ends-with on the nickname the resolver returned, which is
#: what the 14-sibling control was measured with. `espn_id IS NOT NULL` is the
#: anchor requirement — an id-less row may never be a relink target (gotcha #32 /
#: ruling 048) — and the status clause keeps a settled prop off a game that has
#: not been played.
_TARGET_SQL = """
SELECT e.id, e.espn_id, e.home_team_name, e.away_team_name,
       e.commence_time, e.status
  FROM events e
  JOIN sports s ON s.id = e.sport_id
 WHERE s.key = :target_sport
   AND e.espn_id IS NOT NULL
   AND lower(e.home_team_name) LIKE '%' || lower(:home_nick)
   AND lower(e.away_team_name) LIKE '%' || lower(:away_nick)
   AND (e.commence_time AT TIME ZONE 'America/New_York')::date = :game_date
   AND e.status IN ('completed', 'closed')
 ORDER BY e.id
"""

_MONTHS = {
    m: i + 1
    for i, m in enumerate("JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split())
}


def ticker_game_date(ticker: str):
    """The venue's calendar date for this ticker, or `None`.

    `KXNFLFFPTS-26SEP09NESEA` -> `date(2026, 9, 9)`. Deliberately strict: a
    ticker this cannot parse is not silently given today's date, it drops out of
    the population and is reported.
    """
    from datetime import date

    parts = ticker.split("-")
    if len(parts) < 2 or len(parts[1]) < 7:
        return None
    stamp = parts[1][:7]
    try:
        return date(2000 + int(stamp[:2]), _MONTHS[stamp[2:5].upper()], int(stamp[5:7]))
    except (KeyError, ValueError):
        return None


def tap_is_off() -> bool:
    """The prevention is deployed *in this interpreter*.

    Narrow on purpose: it can only answer for the process it runs in, which is
    what `wrong_app_refusal` exists to make the right one. If `kxnflffpts` is
    unmapped here, `_categorize_kalshi_market` still reads this series as
    basketball, and a relink would be attaching a row that is about to be
    re-sported underneath it.
    """
    return KALSHI_TICKER_TO_SPORT_KEY.get(TICKER_PREFIX, "").startswith(
        "americanfootball"
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
        "the code that owns `event_id` on these rows — and the ticker map "
        "`tap_is_off()` inspects — is what is deployed to "
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


async def plan_one(session, ticker: str, registered: tuple[int, int, str, int]):
    """One ticker's verdict. Returns `(verdict, detail, market_id, event_id)`.

    The whole correspondence argument is in here, and it is deliberately one
    function: the checks are a single claim about a single row, and splitting
    them is how a caller ends up running three of five.
    """
    from sqlalchemy import text

    reg_mid, reg_eid, reg_espn, reg_outcomes = registered

    rows = (
        await session.execute(text(_MARKET_SQL), {"mid": reg_mid, "ticker": ticker})
    ).all()

    # The id and the ticker must name the SAME single row. Two rows means the
    # registered id now carries a different ticker — the transposition shape.
    if len(rows) != 1:
        return (
            IDENTITY_CHANGED,
            f"id {reg_mid} and ticker {ticker} match {len(rows)} rows, expected 1",
            reg_mid,
            None,
        )
    m = rows[0]
    if m.id != reg_mid or m.external_id != ticker:
        return (
            IDENTITY_CHANGED,
            f"row {m.id} carries {m.external_id!r}, registered {reg_mid} / {ticker!r}",
            m.id,
            None,
        )

    if (
        m.source != "kalshi"
        or m.status != "resolved"
        or m.market_tier != 5
        or m.llm_sport_category != TARGET_CATEGORY
        or m.sport_key != TARGET_SPORT_KEY
    ):
        return (
            RESPORTED,
            f"source={m.source} status={m.status} tier={m.market_tier} "
            f"category={m.llm_sport_category} sport={m.sport_key}",
            m.id,
            None,
        )

    if m.outcome_count != reg_outcomes:
        return (
            CHILD_COUNT_MOVED,
            f"{m.outcome_count} outcomes, measured {reg_outcomes}",
            m.id,
            None,
        )

    # Derive the target from the ticker, with the matcher's own parser.
    codes = extract_team_codes_from_ticker(ticker)
    game_date = ticker_game_date(ticker)
    if not codes or game_date is None:
        return (
            NO_TARGET,
            f"the shipped resolver cannot read {ticker!r}",
            m.id,
            None,
        )
    (away_ab, away_nick), (home_ab, home_nick) = codes

    targets = (
        await session.execute(
            text(_TARGET_SQL),
            {
                "target_sport": TARGET_SPORT_KEY,
                "home_nick": home_nick,
                "away_nick": away_nick,
                "game_date": game_date,
            },
        )
    ).all()

    label = f"{away_ab}/{away_nick} @ {home_ab}/{home_nick} {game_date}"
    if not targets:
        return (NO_TARGET, f"no anchored NFL event for {label}", m.id, None)
    if len(targets) > 1:
        ids = ", ".join(str(t.id) for t in targets)
        return (
            AMBIGUOUS_TARGET,
            f"{label} -> {len(targets)} events: {ids}",
            m.id,
            None,
        )

    t = targets[0]
    # The derivation and the pre-registered disposition are two independent
    # statements and BOTH must hold. Either alone is a single point of failure:
    # the table cannot notice the world moved, the derivation cannot notice it
    # was pointed at the wrong row.
    if t.id != reg_eid or str(t.espn_id) != str(reg_espn):
        return (
            PLAN_DISAGREES,
            f"{label} resolves to {t.id} espn={t.espn_id}, "
            f"registered {reg_eid} espn={reg_espn}",
            m.id,
            None,
        )

    if m.event_id == t.id:
        return (ALREADY_LINKED, f"already on {t.id}", m.id, t.id)
    if m.event_id is not None:
        return (
            UNEXPECTED_LINKAGE,
            f"linked to {m.event_id}, this plan expects {t.id} — not overwritten",
            m.id,
            None,
        )

    return (
        RELINK,
        f"{label} -> {t.id} espn={t.espn_id} "
        f"({t.away_team_name} @ {t.home_team_name}, {str(t.commence_time)[:16]})",
        m.id,
        t.id,
    )


async def run(args) -> int:
    from sqlalchemy import text

    if not tap_is_off():
        print(
            f"REFUSING: '{TICKER_PREFIX}' is not in KALSHI_TICKER_TO_SPORT_KEY on "
            "this deploy, so the prevention (PR #5624) is not live here and this "
            "series still reads as basketball. Linking these rows now builds on a "
            "sport assignment that is about to move. Land/release the map first."
        )
        return 2

    refusal = wrong_app_refusal(args)
    if refusal:
        print(refusal)
        return 2

    session_factory = _session_factory()

    async with session_factory() as session:
        print("=== #5621 residual — settled KXNFLFFPTS relink ===")
        plans = []
        for ticker in sorted(EXPECTED):
            verdict, detail, mid, eid = await plan_one(
                session, ticker, EXPECTED[ticker]
            )
            plans.append((ticker, verdict, detail, mid, eid))
            print(f"  {ticker:<26} {verdict:<18} {detail}")

        writable = [(mid, eid) for _, v, _, mid, eid in plans if v == RELINK]
        blocked = [(t, v, d) for t, v, d, _, _ in plans if v in BLOCKING]
        print(
            f"  planned={len(writable)}  already-linked="
            f"{sum(1 for _, v, _, _, _ in plans if v == ALREADY_LINKED)}  "
            f"blocked={len(blocked)}"
        )

        if blocked:
            print(
                "\nREFUSING: "
                + "; ".join(f"{t} {v}" for t, v, _ in blocked)
                + ". These two rows were measured as one state of the world; a "
                "surprise on either is a reason to look, not to write the other "
                "half."
            )
            return 2

        market_ids = [mid for _, _, _, mid, _ in plans if mid is not None]

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
                    # moved a row must REFRESH it, or the undo restores a value
                    # that was never the one we overwrote.
                    f"INSERT INTO {BACKUP_TABLE} (id, external_id, event_id) "
                    "SELECT id, external_id, event_id FROM futures_markets "
                    "WHERE id = ANY(:ids) "
                    "ON CONFLICT (id) DO UPDATE SET "
                    "external_id = EXCLUDED.external_id, "
                    "event_id = EXCLUDED.event_id"
                ),
                {"ids": market_ids},
            )
            await session.commit()
            print(f"  copied {len(market_ids)} markets into {BACKUP_TABLE}")

        # THE RECONCILIATION MUST NOT ASSUME ITS OWN TABLE EXISTS — the sibling
        # script crashed here on the very first dry run, which is the one the
        # runbook's step 0 is. `to_regclass` answers without touching the table.
        backup_exists = bool(
            (
                await session.execute(
                    text(f"SELECT to_regclass('public.{BACKUP_TABLE}') IS NOT NULL")
                )
            ).scalar()
        )
        if not backup_exists:
            # FAILS TOWARD REFUSING. An absent table means every row is unbacked,
            # which is the strongest reading and the one that stops `--apply`.
            unbacked = len(market_ids)
            print(
                f"\n=== backup reconciliation (content-exact) === no {BACKUP_TABLE} "
                f"yet — unbacked-or-stale={unbacked}. Run --backup before --apply."
            )
        else:
            unbacked = (
                await session.execute(
                    text(
                        "SELECT count(*) FROM futures_markets f "
                        "WHERE f.id = ANY(:ids) AND NOT EXISTS ("
                        f"  SELECT 1 FROM {BACKUP_TABLE} b WHERE b.id = f.id "
                        "   AND b.external_id IS NOT DISTINCT FROM f.external_id "
                        "   AND b.event_id IS NOT DISTINCT FROM f.event_id)"
                    ),
                    {"ids": market_ids},
                )
            ).scalar()
            print(
                "\n=== backup reconciliation (content-exact) === "
                f"unbacked-or-stale={unbacked}"
            )

        if not args.apply:
            print(
                f"\nDRY RUN — nothing written. Would set event_id on "
                f"{len(writable)} market(s): "
                + (", ".join(f"{m}->{e}" for m, e in writable) or "none")
            )
            return 0

        if unbacked:
            print(
                "\nREFUSING --apply: the backup does not match the rows about to "
                "be written — either a row is unbacked, or it MOVED since the "
                "backup was taken and the undo would restore a value that was "
                "never overwritten. Re-run --backup."
            )
            return 2

        if not writable:
            print("\nNothing to write — every row is already linked (no-op).")
            return 0

        before = (
            await session.execute(
                text(
                    "SELECT count(*) FROM futures_outcomes WHERE market_id = ANY(:ids)"
                ),
                {"ids": market_ids},
            )
        ).scalar()

        written = 0
        for mid, eid in writable:
            ticker = next(t for t, (m, *_rest) in EXPECTED.items() if m == mid)
            # Compare-and-set: if anything linked this row between the plan and
            # now, this matches zero rows and the run refuses rather than
            # overwriting a decision it never read.
            result = await session.execute(
                text(
                    "UPDATE futures_markets SET event_id = :eid "
                    "WHERE id = :mid AND external_id = :ticker AND event_id IS NULL"
                ),
                {"eid": eid, "mid": mid, "ticker": ticker},
            )
            if result.rowcount != 1:
                await session.rollback()
                print(
                    f"\nREFUSING --apply: the guarded UPDATE for {mid} ({ticker}) "
                    f"matched {result.rowcount} rows, not 1. The row changed "
                    "between the plan and the write. Nothing was committed."
                )
                return 2
            written += 1

        after = (
            await session.execute(
                text(
                    "SELECT count(*) FROM futures_outcomes WHERE market_id = ANY(:ids)"
                ),
                {"ids": market_ids},
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
            f"\nAPPLIED: linked {written} market(s); {after} outcomes preserved "
            "(no child row written)."
        )
        print("UNDO: python3 scripts/restore_5621_settled_ffpts_relink.py --apply")
        return 0


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--backup", action="store_true", help="top up the D51 backup table")
    p.add_argument(
        "--apply", action="store_true", help="write the relinks (needs --backup)"
    )
    args = p.parse_args()
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
