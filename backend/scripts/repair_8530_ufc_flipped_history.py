"""#8530 step 3 — put the UFC Fight Night 2026-09-26 chart history back on the right fighter.

WHAT A READER SEES TODAY. `https://bainluck.com/events/15314293` at 390px: the
hero is right since #8534 (Vieira 59% – 41% Bryczek), but the Win Probability
chart sits at ~41% for Vieira for four days and then leaps to 59% at 05:37Z on
2026-09-25 under an "Odds flipped (1)" marker. That leap is not a market move.
It is the moment the sportsbook writer started pricing each side under the
row's name (`6fc56a091a`, main app v5033). Every reading before it, back to the
feed's flip, is the other fighter's price. Screenshot:
`artifacts/614-8530/8530-AFTER-LOOK-15314293-390-0543Z.png` (lane1b worktree).

THE PRODUCERS ARE FIXED AND THIS IS THE RESIDUE.
  * Sportsbooks: #8534 orients each Odds API payload to the row's names. First
    correctly oriented pass 2026-09-25 05:37:14Z; all six fights read the
    DraftKings favourite since (after-check on #8530, 05:45Z).
  * Kalshi: authority/1121 (#8530, 05:35Z) found Kalshi's own reading was
    always right and the inversion guard flipped it to agree with the inverted
    sportsbook number. With the sportsbook number fixed the guard stands down:
    15314294 read 0.125 for Demopoulos at 05:42:53Z, 15314291 0.665 for Jackson
    at 05:43:11Z.

── TWO TABLES, TWO KINDS OF EVIDENCE ────────────────────────────────────────────

`/api/events/{id}/history` draws the chart from `odds_snapshots` (the sportsbook
consensus) and `win_prob_snapshots` (one line per source, here Kalshi). Both are
repaired; nothing else on this card is.

`odds_snapshots` rows carry no names, so the evidence is WHEN. Measured on
production 2026-09-25 ~05:5xZ, hourly per event: every one of the six fights'
moneylines changes sign in the same hour, and the first inverted row on each is
at 2026-09-21 08:36:07Z (the feed's flip; 15314294 goes +575 -> -910 at that
pass). Nothing before it is inverted and nothing after 05:37:14Z on 09-25 is.
So the plan is the window [FLIP_AT, FIXED_AT). The window is an inference, so it
is CHECKED, not trusted: after the swap every row must land on the side the
corrected consensus stands on (`EXPECTED_HOME_FAVOURED`). A windowed row already
on that side contradicts the inference, and `--apply` refuses while any exists.

`win_prob_snapshots` Kalshi rows record their own write-time truth in
`game_state`: which fighter's contract was read (`outcome_name`) and its price
(`yes_probability`). So each row is judged by itself, with no window and no
threshold: the correct home probability is `yes_probability` when the outcome
names the row's home fighter and `1 - yes_probability` when it names the away
fighter. A stored value equal to the complement of that is FLIP; equal to it is
OK; anything else is UNEXPLAINED and left alone. A row with no recorded outcome
is NO_EVIDENCE and left alone (fail-open on absence, the #5432 asymmetry). This
matters on 15314291, whose Kalshi rows alternate right/inverted through the
window. A time window would flip the right ones.

WHAT IS NOT TOUCHED, each with a reason:
  * `events.opening_*` — `_maybe_set_opening_odds` rewrites them on every full
    odds pass until the fight starts, and #8534 makes that pass write the right
    side. The dry run prints them so the after-check can see them move.
  * `events.win_probability_sources` — the live reading, already right.
  * `over_under` / `over_odds` / `under_odds` — a total has no side.
  * any event but the six below, and any source but Kalshi.

RESTORE, one command (D51(b)):

    python3 scripts/repair_8530_ufc_flipped_history.py --restore

  Puts back, from the full-row backups `bak_8530_odds_snapshots` and
  `bak_8530_win_prob_snapshots`, only rows that are still exactly in their
  repaired form, so a restore can never clobber a later write.

USAGE (runs only on bainluck-heavy, notice 47(c)):

    python3 scripts/repair_8530_ufc_flipped_history.py --dry-run   # gates, no DB
    python3 scripts/repair_8530_ufc_flipped_history.py             # plan, no writes
    python3 scripts/repair_8530_ufc_flipped_history.py --apply     # backup, then swap
    python3 scripts/repair_8530_ufc_flipped_history.py --restore
"""

import argparse
import asyncio
import collections
import os
import sys
from datetime import datetime, timezone
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REQUIRED_APP = "bainluck-heavy"

#: UFC Fight Night 2026-09-26, all six rows created by odds_api 2026-09-17 23:35Z.
#: Value = does the corrected consensus favour the row's HOME fighter? Measured
#: on production after #8534's first pass (2026-09-25 05:37-05:41Z), each
#: matching DraftKings on the ESPN core odds and the venue table in #8530.
EXPECTED_HOME_FAVOURED: dict[int, bool] = {
    15314286: False,  # Hiestand v Nakamura    betting 0.2375, DK Nakamura -395
    15314287: True,   # Bellato v Edwards      betting 0.6179, DK Bellato -180
    15314291: True,   # Jackson v Simon        betting 0.6532, DK Jackson -205
    15314292: True,   # Rosas Jr v Barcelos    betting 0.5881, DK Rosas Jr -155
    15314293: True,   # Vieira v Bryczek       betting 0.5909, DK Vieira -162
    15314294: False,  # Demopoulos v Jauregui  betting 0.1339, DK Jauregui -950
}
EVENT_IDS = tuple(sorted(EXPECTED_HOME_FAVOURED))

#: First inverted odds_snapshots row on every one of the six (08:36:07Z).
FLIP_AT = datetime(2026, 9, 21, 8, 36, tzinfo=timezone.utc)
#: #8534's first oriented pass wrote at 05:37:14Z; the pass before it at 04:38Z.
FIXED_AT = datetime(2026, 9, 25, 5, 37, tzinfo=timezone.utc)

BAK_ODDS = "bak_8530_odds_snapshots"
BAK_WP = "bak_8530_win_prob_snapshots"

#: Numeric(5, 4) stores four places; a complement is exact at that precision.
_EPS = 0.00005

# odds_snapshots columns that carry a side, as (column, value-after-repair)
# expressed over the backup row `b`. The swap is an involution, which is what
# makes the restore guard and the idempotency guard the same comparison.
ODDS_SWAP = (
    ("home_moneyline", "b.away_moneyline"),
    ("away_moneyline", "b.home_moneyline"),
    ("home_win_probability", "b.away_win_probability"),
    ("away_win_probability", "b.home_win_probability"),
    ("home_spread", "-b.home_spread"),
    ("home_spread_odds", "b.away_spread_odds"),
    ("away_spread_odds", "b.home_spread_odds"),
    ("projected_home_score", "b.projected_away_score"),
    ("projected_away_score", "b.projected_home_score"),
)
WP_SWAP = (
    ("home_win_probability", "b.away_win_probability"),
    ("away_win_probability", "b.home_win_probability"),
)


def _matches(swap: tuple, repaired: bool) -> str:
    """`s` equals the backup (repaired=False) or the backup swapped (True)."""
    live = ", ".join(f"s.{c}" for c, _ in swap)
    other = ", ".join(expr if repaired else f"b.{c}" for c, expr in swap)
    return f"({live}) IS NOT DISTINCT FROM ({other})"


def _set(swap: tuple, repaired: bool) -> str:
    return ", ".join(f"{c} = {expr if repaired else 'b.' + c}" for c, expr in swap)


def _update(table: str, bak: str, swap: tuple, *, to_repaired: bool) -> str:
    """Swap rows that still equal their backup, or un-swap rows still repaired."""
    return f"""
        UPDATE {table} s SET {_set(swap, to_repaired)}
          FROM {bak} b
         WHERE s.id = b.id
           AND s.id = ANY(:ids)
           AND {_matches(swap, repaired=not to_repaired)}
    """


SQL = {
    "odds_candidates": """
        SELECT id, event_id, captured_at, home_win_probability
          FROM odds_snapshots
         WHERE event_id = ANY(:events)
           AND captured_at >= :flip_at AND captured_at < :fixed_at
         ORDER BY event_id, captured_at
    """,
    "kalshi_candidates": """
        SELECT w.id, w.event_id, w.captured_at, w.home_win_probability,
               w.game_state->>'outcome_name'    AS outcome_name,
               w.game_state->>'yes_probability' AS yes_probability,
               e.home_team_name, e.away_team_name
          FROM win_prob_snapshots w JOIN events e ON e.id = w.event_id
         WHERE w.source = 'kalshi' AND w.event_id = ANY(:events)
         ORDER BY w.event_id, w.captured_at
    """,
    "openings": """
        SELECT id, opening_home_probability, opening_favorite
          FROM events WHERE id = ANY(:events) ORDER BY id
    """,
    "bak_exists": "SELECT to_regclass(:name) IS NOT NULL",
    "bak_odds_create": f"CREATE TABLE IF NOT EXISTS {BAK_ODDS} (LIKE odds_snapshots)",
    "bak_wp_create": f"CREATE TABLE IF NOT EXISTS {BAK_WP} (LIKE win_prob_snapshots)",
    "bak_odds_fill": f"""
        INSERT INTO {BAK_ODDS} SELECT s.* FROM odds_snapshots s
         WHERE s.id = ANY(:ids)
           AND NOT EXISTS (SELECT 1 FROM {BAK_ODDS} b WHERE b.id = s.id)
    """,
    "bak_wp_fill": f"""
        INSERT INTO {BAK_WP} SELECT s.* FROM win_prob_snapshots s
         WHERE s.id = ANY(:ids)
           AND NOT EXISTS (SELECT 1 FROM {BAK_WP} b WHERE b.id = s.id)
    """,
    # Rows this repair already swapped: in the backup, live == swap(backup).
    "odds_already": f"""
        SELECT s.id FROM odds_snapshots s JOIN {BAK_ODDS} b ON b.id = s.id
         WHERE s.event_id = ANY(:events) AND {_matches(ODDS_SWAP, repaired=True)}
    """,
    "odds_unbacked": f"""
        SELECT count(*) FROM unnest(CAST(:ids AS bigint[])) AS p(id)
         WHERE NOT EXISTS (SELECT 1 FROM {BAK_ODDS} b WHERE b.id = p.id)
    """,
    "wp_unbacked": f"""
        SELECT count(*) FROM unnest(CAST(:ids AS bigint[])) AS p(id)
         WHERE NOT EXISTS (SELECT 1 FROM {BAK_WP} b WHERE b.id = p.id)
    """,
    "odds_apply": _update("odds_snapshots", BAK_ODDS, ODDS_SWAP, to_repaired=True),
    "wp_apply": _update("win_prob_snapshots", BAK_WP, WP_SWAP, to_repaired=True),
    "odds_restore": _update("odds_snapshots", BAK_ODDS, ODDS_SWAP, to_repaired=False),
    "wp_restore": _update("win_prob_snapshots", BAK_WP, WP_SWAP, to_repaired=False),
    "bak_ids": "SELECT id FROM {table}",
}


def app_is_permitted(app_name: Optional[str]) -> tuple[bool, str]:
    """Only the named app, so no scheduler can ever reach this (notice 47(c))."""
    if app_name == REQUIRED_APP:
        return True, ""
    return False, (
        f"HEROKU_APP_NAME is {app_name!r}, not {REQUIRED_APP!r}. This script "
        f"writes production data and runs only where a person put it."
    )


def writer_is_corrected() -> tuple[bool, str]:
    """The running image carries #8534, or new inverted rows would follow the repair."""
    try:
        from app.tasks.odds_polling import _orient_feed_to_row
    except ImportError:
        return False, "app.tasks.odds_polling has no _orient_feed_to_row (#8534 absent)"
    probe = _orient_feed_to_row(
        {"home_team": "Robert Bryczek", "away_team": "Rodolfo Vieira"},
        "Rodolfo Vieira", "Robert Bryczek",
    )
    if probe.get("home_team") != "Rodolfo Vieira":
        return False, "_orient_feed_to_row is present but did not orient a flipped probe"
    return True, ""


def odds_row_verdict(event_id: int, home_prob) -> str:
    """FLIP when the swap lands the row on the corrected favourite's side.

    NO_PROB (a row with no home probability) is flipped too: its moneylines
    are just as inverted, and the window, not the side, is what planned it.
    """
    if home_prob is None:
        return "NO_PROB"
    p = float(home_prob)
    if abs(p - 0.5) < _EPS:
        return "EVEN"
    home_favoured_now = p > 0.5
    return "UNEXPLAINED" if home_favoured_now == EXPECTED_HOME_FAVOURED[event_id] else "FLIP"


def kalshi_row_verdict(
    home_name: Optional[str],
    away_name: Optional[str],
    stored_home,
    outcome_name: Optional[str],
    yes_probability,
) -> str:
    """Judge one Kalshi row by the outcome and price it recorded at write time."""
    from app.utils.name_normalization import normalize_name

    if not outcome_name or yes_probability in (None, "") or stored_home is None:
        return "NO_EVIDENCE"
    try:
        yes = float(yes_probability)
    except (TypeError, ValueError):
        return "NO_EVIDENCE"
    outcome = normalize_name(outcome_name)
    if home_name and outcome == normalize_name(home_name):
        correct = yes
    elif away_name and outcome == normalize_name(away_name):
        correct = 1.0 - yes
    else:
        return "NO_EVIDENCE"
    stored = float(stored_home)
    if abs(stored - correct) < _EPS:
        return "OK"
    if abs(stored - (1.0 - correct)) < _EPS:
        return "FLIP"
    return "UNEXPLAINED"


async def _scalar(session, sql: str, **params):
    from sqlalchemy import text

    return (await session.execute(text(sql), params)).scalar()


async def _rows(session, sql: str, **params) -> list[dict]:
    from sqlalchemy import text

    return [dict(r._mapping) for r in (await session.execute(text(sql), params)).fetchall()]


async def build_plan(session) -> dict:
    events = list(EVENT_IDS)
    already: set[int] = set()
    if await _scalar(session, SQL["bak_exists"], name=BAK_ODDS):
        already = {r["id"] for r in await _rows(session, SQL["odds_already"], events=events)}

    odds = collections.defaultdict(list)
    for r in await _rows(session, SQL["odds_candidates"],
                         events=events, flip_at=FLIP_AT, fixed_at=FIXED_AT):
        verdict = "ALREADY" if r["id"] in already else odds_row_verdict(
            r["event_id"], r["home_win_probability"])
        odds[verdict].append(r)

    kalshi = collections.defaultdict(list)
    for r in await _rows(session, SQL["kalshi_candidates"], events=events):
        kalshi[kalshi_row_verdict(r["home_team_name"], r["away_team_name"],
                                  r["home_win_probability"], r["outcome_name"],
                                  r["yes_probability"])].append(r)

    return {
        "odds": odds,
        "kalshi": kalshi,
        "odds_ids": [r["id"] for v in ("FLIP", "NO_PROB") for r in odds[v]],
        "kalshi_ids": [r["id"] for r in kalshi["FLIP"]],
        "openings": await _rows(session, SQL["openings"], events=events),
    }


def print_plan(plan: dict) -> None:
    print("odds_snapshots in the window "
          f"[{FLIP_AT:%Y-%m-%d %H:%MZ}, {FIXED_AT:%Y-%m-%d %H:%MZ}):")
    for verdict, rows in sorted(plan["odds"].items()):
        by_event = collections.Counter(r["event_id"] for r in rows)
        print(f"  {verdict:<12} {len(rows):>5}  {dict(sorted(by_event.items()))}")
    print("win_prob_snapshots, source=kalshi, judged by their own game_state:")
    for verdict, rows in sorted(plan["kalshi"].items()):
        by_event = collections.Counter(r["event_id"] for r in rows)
        print(f"  {verdict:<12} {len(rows):>5}  {dict(sorted(by_event.items()))}")
    print("events.opening_* (not repaired; the next full odds pass rewrites them):")
    for r in plan["openings"]:
        print(f"  {r['id']}: opening_home {r['opening_home_probability']} "
              f"favourite {r['opening_favorite']} "
              f"(expected {'home' if EXPECTED_HOME_FAVOURED[r['id']] else 'away'})")
    print(f"PLAN: swap {len(plan['odds_ids'])} odds_snapshots rows, "
          f"{len(plan['kalshi_ids'])} kalshi rows")


def apply_refusal(plan: dict) -> Optional[str]:
    """Why --apply must not write, or None. The window inference must hold on every row."""
    unexplained = len(plan["odds"].get("UNEXPLAINED", ())) + len(plan["odds"].get("EVEN", ()))
    if unexplained:
        return (f"{unexplained} odds_snapshots row(s) in the window already sit on "
                f"the corrected favourite's side — the flip window is wrong; not writing.")
    return None


async def repair(session, apply: bool) -> int:
    from sqlalchemy import text

    plan = await build_plan(session)
    print_plan(plan)
    if not apply:
        print("plan only — nothing written. --apply to back up and swap.")
        return 0
    refusal = apply_refusal(plan)
    if refusal:
        print(f"REFUSING: {refusal}")
        return 2
    odds_ids, wp_ids = plan["odds_ids"], plan["kalshi_ids"]
    if not odds_ids and not wp_ids:
        print("nothing to repair.")
        return 0

    await session.execute(text(SQL["bak_odds_create"]))
    await session.execute(text(SQL["bak_wp_create"]))
    await session.execute(text(SQL["bak_odds_fill"]), {"ids": odds_ids})
    await session.execute(text(SQL["bak_wp_fill"]), {"ids": wp_ids})
    unbacked = (await _scalar(session, SQL["odds_unbacked"], ids=odds_ids)
                + await _scalar(session, SQL["wp_unbacked"], ids=wp_ids))
    if unbacked:
        await session.rollback()
        print(f"REFUSING: {unbacked} planned row(s) have no backup; rolled back.")
        return 2
    await session.commit()
    print(f"backed up into {BAK_ODDS} / {BAK_WP} (committed)")

    odds_n = (await session.execute(text(SQL["odds_apply"]), {"ids": odds_ids})).rowcount
    wp_n = (await session.execute(text(SQL["wp_apply"]), {"ids": wp_ids})).rowcount
    await session.commit()
    print(f"swapped {odds_n}/{len(odds_ids)} odds_snapshots rows, "
          f"{wp_n}/{len(wp_ids)} kalshi rows "
          f"(a shortfall is a row that moved since its backup: declined, not written)")
    print(f"undo: python3 scripts/{os.path.basename(__file__)} --restore")
    return 0


async def restore(session) -> int:
    from sqlalchemy import text

    total = 0
    for table, bak, key in (("odds_snapshots", BAK_ODDS, "odds_restore"),
                            ("win_prob_snapshots", BAK_WP, "wp_restore")):
        if not await _scalar(session, SQL["bak_exists"], name=bak):
            print(f"{bak}: absent — nothing of {table} was repaired.")
            continue
        ids = [r["id"] for r in await _rows(session, SQL["bak_ids"].format(table=bak))]
        n = (await session.execute(text(SQL[key]), {"ids": ids})).rowcount
        total += n
        print(f"{table}: restored {n} of {len(ids)} backed-up rows "
              f"(the rest were not in their repaired form)")
    await session.commit()
    print(f"restored {total} rows")
    return 0


async def _with_session(fn, *args) -> int:
    from app.tasks.base import get_task_session

    async with get_task_session() as session:
        return await fn(session, *args)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true",
                      help="back up, then swap (production write)")
    mode.add_argument("--restore", action="store_true",
                      help="the undo: put every repaired row back")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the gate decisions and exit; opens no DB connection")
    args = parser.parse_args()

    ok_app, app_why = app_is_permitted(os.environ.get("HEROKU_APP_NAME"))
    ok_writer, writer_why = writer_is_corrected()

    if args.dry_run:
        print("#8530 history repair — dry run, no database connection opened")
        print(f"  app gate     : {'PASS' if ok_app else 'REFUSE'} ({app_why or REQUIRED_APP})")
        print(f"  writer gate  : {'PASS' if ok_writer else 'REFUSE'} "
              f"({writer_why or 'the running image orients the feed to the row (#8534)'})")
        print(f"  mode         : {'restore' if args.restore else 'apply' if args.apply else 'plan'}")
        print(f"  events       : {', '.join(map(str, EVENT_IDS))}")
        print(f"  odds window  : [{FLIP_AT.isoformat()}, {FIXED_AT.isoformat()})")
        print(f"  backups      : {BAK_ODDS}, {BAK_WP}")
        return 0

    if (args.apply or args.restore) and not ok_app:
        print(f"REFUSING: {app_why}")
        return 2
    if args.apply and not ok_writer:
        print(f"REFUSING: {writer_why}")
        return 2

    return asyncio.run(_with_session(restore) if args.restore
                       else _with_session(repair, args.apply))


if __name__ == "__main__":
    sys.exit(main())
