"""#3026 — the historical cleanup: unmake the events a question minted.

THE SHIP: seven live cards stop existing. `https://bainluck.com/events/15301524`
rendered on 2026-09-03 as a *suspended* — not terminal — head-to-head between
"Will Greg Mueller Finish Top 3" and "the 2026 WSOP Main Event": a 33%/67% hero,
a win-probability curve drawn over 472 snapshots of a fixture that does not
exist, and a BLAST Open Porto award list standing in for the two teams' panels.
Six siblings (15301518–15301523) were live beside it.

PREVENTION ALREADY SHIPPED. `question_refusal_reason()` refuses the mint for
both shapes, so no NEW row is minted. This script is the owed DATA REPAIR for
the rows written before it landed. The predicate is IMPORTED, never restated:
the population is by construction exactly the set the shipped guard refuses.

------------------------------------------------------------------------------
THE POPULATION — 274 rows, measured on production 2026-09-04
------------------------------------------------------------------------------

Every one of them is a *broadcast-mention or question* market that the matchup
parse beheaded into two "teams":

    163  "Announcers" / "Denver vs Golden State Professional Basketball Game"
     96  "What will the announcers say during PSG" / "Arsenal"
     15  the same shapes, but the row has since absorbed REAL derivatives

None of them is a game, and the measurement says so without appeal:

    0 of 274 has ever carried a score
    0 of 274 has ever carried a single odds snapshot

A fixture we actually hold is priced. These never were.

------------------------------------------------------------------------------
RENAME OR DELETE — the question #3026 parked, answered PER ROW
------------------------------------------------------------------------------

262 of the 274 reconstruct into a real matchup ("Announcers" / "Duke vs
Virginia" → "Duke" / "Virginia"), so #2871's rule — never delete the only record
of a real fixture — has to be answered row by row rather than waved away. It is
answered by asking what a delete would actually LOSE, and the answer splits four
ways. Nothing is renamed: renaming a mention prop mints a game card with no
odds, no score and (for 167 rows) no markets — a blank lookalike of a fixture,
and where the real fixture exists, a twin of it. That is the failure mode D39
and #2693 are fighting, so the repair refuses to manufacture it.

  DELETE — a clean counterpart already exists (156).  The reconstructed matchup
  resolves to a real event we hold, in either orientation, in a window anchored
  on the Kalshi ticker's own date where the row has one. The row is a duplicate
  of a game we already present correctly; deleting it loses nothing.

  DELETE — the trace survives in the market (57).  The row owns the very market
  whose title minted it, and that title still names the fixture in full
  ("Announcers at UConn vs St. John's"). The market is UNLINKED, never deleted,
  so after the repair the fixture is still named in `futures_markets` — only the
  fictional head-to-head goes.

  DELETE — the row names no fixture at all (12).  "Will Greg Mueller Finish
  Top 3" / "the 2026 WSOP Main Event" is a poker prop and a tournament; there is
  no matchup in it to preserve. ALL SEVEN LIVE ROWS ARE HERE.

  HOLD — the row is the last trace (34).  Reconstructible, no clean counterpart,
  and no surviving market: deleting it really would be the only record of a real
  fixture going away. Every one is an NCAAB/WBC mention prop for a game our
  coverage never picked up. They are reported by id and left exactly as they
  are; the rename-or-delete call on them is a product decision, not a repair.

  HOLD — the row absorbed REAL derivatives (15).  Event 15195405 ("What will the
  announcers say during New Zealand" / "Egypt") owns "New Zealand vs Egypt:
  Correct Score", ": Total Corners" and six more genuine soccer props. Unlinking
  those degrades a real market's attachment rather than fixing it, and
  re-pointing them is matching work — D39, lane1, #2693. Filed, not smuggled in.

225 deleted, 49 held, and every held row is printed with its reason.

------------------------------------------------------------------------------
CHILDREN — all 11 FK tables counted, not the four that come to mind
------------------------------------------------------------------------------

    futures_markets          104   NO ACTION   → UNLINKED (event_id = NULL)
    line_movement_analyses    21   NO ACTION   → DELETED (a taxonomy cache row)
    win_prob_snapshots      1156   CASCADE     → banked, then goes with the row
    event_provider_anchors     8   CASCADE     → banked, then goes with the row
    the other seven            0   pre-registered as 0; a nonzero count REFUSES

The 8 anchors are all `id_kind = 'market'` — a Polymarket condition id, not a
fixture id. The anchor asserts "this market IS this event", which is precisely
the false correspondence being removed.

------------------------------------------------------------------------------
D51 — BACKUP FIRST, ONE-COMMAND RESTORE
------------------------------------------------------------------------------

    bak_3026_question_events   full event rows (to_jsonb) + every CASCADE child
    bak_3026_market_links      (market_id, old event_id) for all 104

Undo:  python3 scripts/restore_3026_question_events.py --apply

USAGE
    python3 scripts/repair_3026_question_events.py                 # dry run
    python3 scripts/repair_3026_question_events.py --backup        # top up backup
    python3 scripts/repair_3026_question_events.py --backup --apply
"""

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# The fix itself. Imported, never restated — the repair's population IS the set
# the shipped guard refuses, so the two cannot drift apart.
from app.utils.prediction_market_matching import (  # noqa: E402
    _EMBEDDED_MATCHUP_RE,
    _QUESTION_OPENER_RE,
    _WILL_CLAUSE_RE,
    bracket_refusal_reason,
    extract_matchup,
    name_embeds_a_matchup,
    question_refusal_reason,
)

BAK_EVENTS = "bak_3026_question_events"
BAK_LINKS = "bak_3026_market_links"

# Postgres ARE understands `(?:`, but SQLAlchemy `text()` reads the `:` that
# follows as a bind parameter (gotcha #45). The patterns travel as VALUES and
# the groups are made capturing so both engines match the same strings.
EMBED_RE_SQL = _EMBEDDED_MATCHUP_RE.pattern.replace("(?:", "(")
OPENER_RE_SQL = _QUESTION_OPENER_RE.pattern.replace("(?:", "(")
WILL_RE_SQL = _WILL_CLAUSE_RE.pattern.replace("(?:", "(")

# Sanity floor. A repair that finds nothing and reports success is the worst
# outcome there is (gotcha #53 — an empty result is a response shape, not an
# absence).
MIN_EXPECTED_POPULATION = 200

# The pre-registered disposition, measured against production 2026-09-04.
# `--apply` refuses unless the live plan matches, so this docstring's claims and
# the dyno's result cannot drift apart unnoticed.
EXPECTED = {
    "population": 274,
    "delete_duplicate": 156,
    "delete_trace_survives": 57,
    "delete_no_fixture_named": 12,
    "hold_last_trace": 34,
    "hold_owns_real_markets": 15,
    "markets_unlinked": 104,
    "lma_deleted": 21,
}

# Tables that hold a NO ACTION FK to `events` and are NOT cleared by this
# repair. Every one measured 0 on the delete set; a nonzero count means the
# population has grown a shape this repair was never sized for, so it REFUSES
# rather than discovering it as a failed DELETE mid-loop.
UNHANDLED_CHILD_TABLES = (
    "odds_snapshots",
    "odds_aggregated",
    "ranking_judgments",
    "score_snapshots",
    "scoring_plays",
)

# CASCADE children, banked before the row goes so the undo is a real undo.
CASCADE_CHILD_TABLES = (
    "event_provider_anchors",
    "win_prob_snapshots",
    "espn_snapshots",
    "game_moments",
)

_VS_SPLIT_RE = re.compile(r"\s+vs\.?\s+", re.IGNORECASE)

# The question openers are formulaic provider titles, so stripping one is a
# deterministic edit rather than a guess: 76 rows say "What will the announcers
# say during X" / "Y" and 11 say "Who will win X" / "Y". A shape not listed here
# is NOT reconstructed — a reconstruction that has to guess is not one.
_QUESTION_PREFIX_RE = re.compile(
    r"^(?:what will the announcers say during"
    r"|who will win"
    r"|who will score more points in)\s+",
    re.IGNORECASE,
)

# Sport/format descriptors the providers append to the tail slot:
# "Denver vs Golden State Professional Basketball Game", "… UFC Fight".
_DESCRIPTOR_RE = re.compile(
    r"\s+(?:"
    r"(?:professional|college|mens|womens|men's|women's)?\s*"
    r"(?:champions league\s+)?"
    r"(?:basketball|football|baseball|hockey|soccer|tennis)\s+(?:game|match)"
    r"|ufc\s+fight"
    r"|game"
    r")\s*$",
    re.IGNORECASE,
)
_TRAILING_GAME_NUMBER_RE = re.compile(r"\s*[:,-]\s*game\s+\d+\s*\??$", re.IGNORECASE)

# A name shorter than this is not specific enough to look a counterpart up with:
# ILIKE '%Sy%' matches most of the table.
_MIN_NAME_LEN = 3

# How far from the row's anchor a clean counterpart may sit. Kalshi tickers
# carry the game's own date, so those get the day itself plus a day either side;
# a row with no ticker is anchored on a commence_time that is often an ingestion
# stamp, so it gets a wider net.
_TICKER_WINDOW_BEFORE = timedelta(days=1)
_TICKER_WINDOW_AFTER = timedelta(days=2)
_COMMENCE_WINDOW = timedelta(hours=36)

_TICKER_DATE_RE = re.compile(r"-(\d{2})([A-Z]{3})(\d{2})", re.IGNORECASE)
_MONTHS = {
    month: index + 1
    for index, month in enumerate(
        ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
         "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
    )
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


def _strip_descriptors(part: str) -> str:
    """Drop the provider's trailing sport/format words from one name slot."""
    name = (part or "").strip()
    name = _TRAILING_GAME_NUMBER_RE.sub("", name)
    previous = None
    while previous != name:
        previous = name
        name = _DESCRIPTOR_RE.sub("", name).strip()
    return name.strip(" ?:-")


def reconstruct_matchup(home: str, away: str):
    """The real (X, Y) this fictional row still names, or None if it names none.

    Examples:
        "Announcers" / "Duke vs Virginia"                  → ("Duke", "Virginia")
        "What will the announcers say during PSG" / "Arsenal"
                                                           → ("PSG", "Arsenal")
        "Will Greg Mueller Finish Top 3" / "the 2026 WSOP Main Event"
                                                           → None
    """
    for slot in (away or "", home or ""):
        if name_embeds_a_matchup(slot):
            parts = _VS_SPLIT_RE.split(slot)
            if len(parts) != 2:
                return None  # three names is not a matchup either
            first, second = _strip_descriptors(parts[0]), _strip_descriptors(parts[1])
            if len(first) < _MIN_NAME_LEN or len(second) < _MIN_NAME_LEN:
                return None
            return first, second

    opener = _QUESTION_PREFIX_RE.match((home or "").strip())
    if opener:
        head = _strip_descriptors((home or "").strip()[opener.end():])
        tail = _strip_descriptors(away or "")
        if len(head) < _MIN_NAME_LEN or len(tail) < _MIN_NAME_LEN:
            return None
        return head, tail
    return None


def ticker_date(external_id: str):
    """The date a Kalshi ticker encodes, or None.

    `pm_kalshi_KXNBAMENTION-26FEB22DENGSW` → 2026-02-22. The ticker is the row's
    own provenance, so it beats a `commence_time` that is often the moment we
    ingested the market rather than the moment the game started.
    """
    match = _TICKER_DATE_RE.search(external_id or "")
    if not match:
        return None
    year, month, day = match.group(1), match.group(2).upper(), match.group(3)
    if month not in _MONTHS:
        return None
    try:
        return datetime(2000 + int(year), _MONTHS[month], int(day))
    except ValueError:
        return None


def _ilike_term(name: str) -> str:
    """A containment pattern that cannot smuggle its own wildcards.

    "Denver" → "%Denver%", and it matches the real row's "Denver Nuggets".
    """
    escaped = (name or "").replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def counterpart_window(commence, external_id):
    """(lo, hi) to look for a clean counterpart in."""
    dated = ticker_date(external_id)
    if dated is not None:
        if commence is not None and commence.tzinfo is not None:
            dated = dated.replace(tzinfo=commence.tzinfo)
        return dated - _TICKER_WINDOW_BEFORE, dated + _TICKER_WINDOW_AFTER
    return commence - _COMMENCE_WINDOW, commence + _COMMENCE_WINDOW


async def find_clean_counterpart(session, first, second, commence, external_id, self_id):
    """A REAL event for this matchup, in either orientation, or None.

    "Clean" is load-bearing: two mention props for one fixture would otherwise
    vouch for each other, so a candidate that either shipped predicate refuses
    is not a counterpart — it is another row this repair is deleting.
    """
    from sqlalchemy import text

    if commence is None:
        return None
    low, high = counterpart_window(commence, external_id)
    rows = (
        await session.execute(
            text(
                "SELECT id, home_team_name, away_team_name FROM events "
                "WHERE id <> :self AND commence_time >= :lo AND commence_time < :hi "
                "AND ((home_team_name ILIKE :first AND away_team_name ILIKE :second) "
                "  OR (home_team_name ILIKE :second AND away_team_name ILIKE :first)) "
                "ORDER BY id LIMIT 8"
            ),
            {
                "self": self_id,
                "lo": low,
                "hi": high,
                "first": _ilike_term(first),
                "second": _ilike_term(second),
            },
        )
    ).all()
    for candidate_id, home, away in rows:
        if question_refusal_reason(home or "", away or ""):
            continue
        if bracket_refusal_reason(home or "", away or ""):
            continue
        return candidate_id
    return None


def market_still_names_the_fixture(market_names, recovered) -> bool:
    """True when a market this row owns still carries the whole matchup.

    "Announcers at UConn vs St. John's" carries both names, so unlinking it
    keeps the fixture named in `futures_markets` after the event row is gone.
    """
    first, second = recovered
    for name in market_names:
        lowered = (name or "").lower()
        if first.lower() in lowered and second.lower() in lowered:
            return True
    return False


def market_is_the_fiction(name: str) -> bool:
    """True when this market's own title is what minted the fictional event."""
    parsed = extract_matchup(name or "")
    if not parsed or not parsed.team_a or not parsed.team_b:
        return False
    return question_refusal_reason(parsed.team_a, parsed.team_b) is not None


async def build_plan(session):
    """Classify every event the shipped guard would refuse today."""
    from sqlalchemy import text

    rows = (
        await session.execute(
            text(
                "SELECT e.id, e.home_team_name, e.away_team_name, e.commence_time, "
                "       e.external_id, e.status "
                "FROM events e WHERE "
                "  e.home_team_name ~* :embed_re OR e.away_team_name ~* :embed_re "
                "  OR e.home_team_name ~* :opener_re OR e.away_team_name ~* :opener_re "
                "  OR e.home_team_name ~* :will_re OR e.away_team_name ~* :will_re "
                "ORDER BY e.id"
            ),
            {
                "embed_re": EMBED_RE_SQL,
                "opener_re": OPENER_RE_SQL,
                "will_re": WILL_RE_SQL,
            },
        )
    ).all()

    plan = []
    for event_id, home, away, commence, external_id, status in rows:
        # The SQL above is only a PREFILTER. The shipped predicate decides.
        reason = question_refusal_reason(home or "", away or "")
        if not reason:
            continue

        markets = (
            await session.execute(
                text(
                    "SELECT id, name FROM futures_markets "
                    "WHERE event_id = :eid ORDER BY id"
                ),
                {"eid": event_id},
            )
        ).all()
        market_ids = [row[0] for row in markets]
        market_names = [row[1] for row in markets]

        entry = {
            "id": event_id,
            "old_home": home,
            "old_away": away,
            "status": status,
            "reason": reason,
            "market_ids": market_ids,
            "recovered": None,
            "counterpart": None,
            "action": None,
            "why": None,
        }

        # A row that has absorbed a market belonging to a REAL fixture is not
        # this repair's to move. Unlinking it would degrade a genuine prop's
        # attachment rather than fix it — that is matching work (D39, #2693).
        if any(not market_is_the_fiction(name) for name in market_names):
            entry["action"], entry["why"] = "hold", "owns_real_markets"
            plan.append(entry)
            continue

        recovered = reconstruct_matchup(home or "", away or "")
        entry["recovered"] = recovered

        if recovered is None:
            entry["action"], entry["why"] = "delete", "no_fixture_named"
            plan.append(entry)
            continue

        entry["counterpart"] = await find_clean_counterpart(
            session, recovered[0], recovered[1], commence, external_id, event_id
        )
        if entry["counterpart"] is not None:
            entry["action"], entry["why"] = "delete", "duplicate"
        elif market_still_names_the_fixture(market_names, recovered):
            entry["action"], entry["why"] = "delete", "trace_survives"
        else:
            # No counterpart, no surviving market: this row IS the last record
            # of a real fixture, which is exactly what #2871 forbids deleting.
            entry["action"], entry["why"] = "hold", "last_trace"
        plan.append(entry)
    return plan


async def unhandled_child_rows(session, delete_ids):
    """Rows in the NO ACTION tables this repair does not clear. Must be empty."""
    from sqlalchemy import text

    if not delete_ids:
        return {}
    found = {}
    for table in UNHANDLED_CHILD_TABLES:
        count = (
            await session.execute(
                text(f"SELECT count(*) FROM {table} WHERE event_id = ANY(:ids)"),
                {"ids": delete_ids},
            )
        ).scalar() or 0
        if count:
            found[table] = count
    return found


async def ensure_backup(session, plan):
    """Create the D51 backup tables and top them up. Returns rows banked."""
    from sqlalchemy import text

    await session.execute(
        text(
            f"CREATE TABLE IF NOT EXISTS {BAK_EVENTS} ("
            "  event_id bigint PRIMARY KEY,"
            "  why text NOT NULL,"
            "  event_row jsonb NOT NULL,"
            "  lma_rows jsonb NOT NULL DEFAULT '[]'::jsonb,"
            "  cascade_rows jsonb NOT NULL DEFAULT '{}'::jsonb,"
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

    # Every CASCADE child is banked by name, so the undo puts back the
    # win-probability series and the anchors as well as the row itself.
    cascade_sql = ", ".join(
        f"'{table}', COALESCE((SELECT jsonb_agg(to_jsonb(c)) FROM {table} c "
        f"WHERE c.event_id = e.id), '[]'::jsonb)"
        for table in CASCADE_CHILD_TABLES
    )

    for entry in plan:
        if entry["action"] != "delete":
            continue
        await session.execute(
            text(
                f"INSERT INTO {BAK_EVENTS} "
                "(event_id, why, event_row, lma_rows, cascade_rows) "
                "SELECT e.id, :why, to_jsonb(e), "
                "  COALESCE((SELECT jsonb_agg(to_jsonb(l)) FROM line_movement_analyses l "
                "            WHERE l.event_id = e.id), '[]'::jsonb), "
                f"  jsonb_build_object({cascade_sql}) "
                "FROM events e WHERE e.id = :eid "
                "ON CONFLICT (event_id) DO NOTHING"
            ),
            {"eid": entry["id"], "why": entry["why"]},
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
    """Unlink, then delete. Returns what was actually written."""
    from sqlalchemy import text

    written = {"deleted": 0, "held": 0, "markets_unlinked": 0, "lma_deleted": 0}

    for entry in plan:
        if entry["action"] != "delete":
            written["held"] += 1
            continue

        if entry["market_ids"]:
            result = await session.execute(
                text(
                    "UPDATE futures_markets SET event_id = NULL "
                    "WHERE id = ANY(:ids) AND event_id = :eid"
                ),
                {"ids": entry["market_ids"], "eid": entry["id"]},
            )
            written["markets_unlinked"] += result.rowcount or 0

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


def measure(plan, lma_on_delete_set):
    """The numbers the pre-registered disposition is checked against."""
    def count(action, why):
        return sum(1 for e in plan if e["action"] == action and e["why"] == why)

    return {
        "population": len(plan),
        "delete_duplicate": count("delete", "duplicate"),
        "delete_trace_survives": count("delete", "trace_survives"),
        "delete_no_fixture_named": count("delete", "no_fixture_named"),
        "hold_last_trace": count("hold", "last_trace"),
        "hold_owns_real_markets": count("hold", "owns_real_markets"),
        "markets_unlinked": sum(
            len(e["market_ids"]) for e in plan if e["action"] == "delete"
        ),
        "lma_deleted": lma_on_delete_set,
    }


async def run(args):
    from sqlalchemy import text

    session_maker = _session_factory()
    async with session_maker() as session:
        plan = await build_plan(session)
        delete_ids = [e["id"] for e in plan if e["action"] == "delete"]

        lma_on_delete_set = (
            await session.execute(
                text(
                    "SELECT count(*) FROM line_movement_analyses "
                    "WHERE event_id = ANY(:ids)"
                ),
                {"ids": delete_ids},
            )
        ).scalar() or 0

        measured = measure(plan, lma_on_delete_set)
        print(json.dumps({"measured": measured}, indent=2))

        for entry in plan:
            recovered = entry["recovered"]
            print(
                f"  {entry['id']}  {entry['action']:6} {entry['why']:20}  "
                f"[{entry['status']}]  "
                f"{(entry['old_home'] or '')[:38]!r} / {(entry['old_away'] or '')[:38]!r}"
                + (f"  → {recovered[0]!r} v {recovered[1]!r}" if recovered else "")
                + (f"  (counterpart {entry['counterpart']})" if entry["counterpart"] else "")
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

        unhandled = await unhandled_child_rows(session, delete_ids)
        if unhandled:
            print(
                f"REFUSING: rows in tables this repair does not clear: {unhandled}. "
                "The population has grown a shape this repair was not sized for."
            )
            return 6

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
        # result). Re-derive from scratch: only the held rows may remain.
        residue = await build_plan(session)
        remaining = {"total": len(residue),
                     "still_deletable": sum(1 for e in residue if e["action"] == "delete")}
        print(json.dumps({"residue_after": remaining}, indent=2))
        return 0 if remaining["still_deletable"] == 0 else 5


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--backup", action="store_true", help="top up the D51 backup tables")
    p.add_argument("--apply", action="store_true", help="write the repair (needs --backup)")
    p.add_argument("--allow-small", action="store_true", help="bypass the population floor")
    p.add_argument("--allow-drift", action="store_true", help="bypass the disposition gate")
    sys.exit(asyncio.run(run(p.parse_args())))


if __name__ == "__main__":
    main()
