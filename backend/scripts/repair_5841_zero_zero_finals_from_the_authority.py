"""#5841 — a search for "Yankees" stops answering with a baseball game that FINISHED 0 - 0.

THE SHIP. `bainluck://search?q=Yankees` and `https://bainluck.com` search, phone
and iPad, first screen, measured on production 2026-09-16 06:5xZ:

    New York Yankees vs Boston Red Sox        0 - 0      MLB  FINAL
    Baltimore Orioles vs New York Yankees     0 - 0      MLB  FINAL

A nine-inning baseball game cannot end 0 - 0. The clients render our row
faithfully — `SearchView.swift` already declines to print an ABSENT score — so
both cards are a database row asserting a result that never happened, on the
dogfood path of the launch candidate (native/140, native/178).

------------------------------------------------------------------------------
THE POPULATION, MEASURED ON PRODUCTION 2026-09-16 06:4xZ
------------------------------------------------------------------------------

Settled rows (`closed`/`completed`) scored `0 - 0`, excluding the sports where a
scoreless draw is a REAL result (see :data:`DRAW_CAPABLE_PREFIXES`):

    45-day window        18 rows     7 MLB · 11 tennis
    all time             98 rows     65 baseball_ncaa · 15 baseball_mlb ·
                                     11 tennis · 7 assorted

The 18 are the same 18 native/140 measured on 09-13 and native/178 re-measured
on 09-15: the cohort is frozen, finite, and none of it is new.

THREE SHAPES, AND ONLY ONE OF THEM IS THIS SCRIPT'S:

  A. **An ESPN anchor nobody ever cashed** — 4 rows, all 2026-08-18
     (`15201192/93/94/95`). `status='closed'`, `completed_at IS NULL`,
     `period='Scheduled'`, `external_id IS NULL`, and an `espn_id` whose summary
     is a `STATUS_FINAL` between the same two clubs on the same UTC date:
     Orioles 1 – Yankees 3, Guardians 8 – Giants 1, Rays 5 – Blue Jays 10,
     Brewers 22 – Mariners 0. **The result was always one fetch away.**
     ⇒ THIS SCRIPT. The authority is asked, and only the authority writes.

  B. **A twin whose sibling already holds the result** — 3 rows
     (`15198906`, `15228871`, `14877917`). Each has a row at the SAME COMMENCE
     MINUTE carrying the real score (2–1, 0–1, 0–6), all three ESPN-anchored and
     `completed`. Two of the three are already invisible: `fold_twin_events`
     elects the anchored sibling. The third (`14877917`) is the one a reader
     meets, and it is a SERVE-TIME election defect, not a data one — routed to
     lane1 with a reproduction (D39: lane1 owns twins).
     ⇒ REFUSED HERE, BY NAME, as `scored_twin_exists`. Writing a second scored
     copy of one game is a worse lie than the one it replaces.

  C. **Tennis** — 11 rows, `completed`, no `espn_id`, no StatPal id. `completed`
     is the AUTHORITY's word and there is no anchor to ask, so nothing here can
     adjudicate them. They are #2772's, unchanged.
     ⇒ NOT EVEN A CANDIDATE (no `espn_id`).

------------------------------------------------------------------------------
WHY A SCRIPT AND NOT A PRODUCER FIX — MEASURED BEFORE IT WAS WRITTEN
------------------------------------------------------------------------------

Both of the obvious "just re-run the pipeline" answers are structurally blind to
this cohort, and neither is a bug that repairing would fix:

  * :func:`app.utils.espn_helpers.backfill_missing_scores` — the fifth ESPN pass,
    the thing whose whole job is "a finished row with no score" — selects
    ``home_score IS NULL AND away_score IS NULL``. These rows carry a `0`. It has
    never been able to see them and a widening is a live-task change to a score
    WRITER, which is not what a residual of 98 frozen rows is worth.
  * The 90-minute closer of **#2480**, which stamped shape B, is FIXED:
    `b90f97fa` is an ancestor of master, `detect_and_close_stale_events` calls
    `get_max_duration_for_sport` and `game_may_still_be_running`, and its
    elapsed-time arm SUSPENDS. Recurrence measured by native/179: 270 MLB rows
    finished in September, **0** in the 80–100 minute band, **0** scored 0–0.

So the producer is not writing new ones. What is left is the rows it already
wrote, and nothing that runs today will find them again.

------------------------------------------------------------------------------
🔴 THE AUTHORITY DECIDES EVERY WRITE — THE "0-0 IS IMPOSSIBLE" READ DECIDES NONE
------------------------------------------------------------------------------

:data:`DRAW_CAPABLE_PREFIXES` only keeps soccer's real nil-nils out of the
CANDIDATE set so the pass does not make thousands of pointless ESPN calls. It is
not load-bearing for a single write: a row is written only when ESPN's own
summary for the row's own `espn_id` says FINAL with a score that is not 0 - 0.
If ESPN says the game really finished 0 - 0, this script writes NOTHING and says
so (`authority_confirms_0_0`). Get the prefix list wrong in either direction and
the worst outcome is a wasted fetch.

Five refusals stand between a candidate and a write, and the FIRST TWO EXIST
BECAUSE OF ONE REAL ROW. `14877917` — the Yankees–Red Sox card on the first
screen — carries `espn_id='401815659'`, whose summary is a **2026-06-07** game
(Yankees 6, Red Sox 1) while the row's own `commence_time` is **2026-08-29**.
Its stored box score's period scores sum to that June game, to the run. A repair
that trusted the stamped anchor would have written a June scoreline onto an
August card and called it a fix.

    anchor_is_a_different_date   |Δt| between the row's start and ESPN's start
                                 must be ≤ 12h (the four shape-A rows are 4h
                                 out; the June anchor is 83 DAYS out)
    anchor_is_a_different_game   both clubs must correspond, in the same
                                 home/away orientation
    anchor_is_not_final          ESPN must say the competition is over AND
                                 finished — `stopped_without_result` (a
                                 postponement, #3397) is refused by name
    authority_confirms_0_0       nothing to write
    scored_twin_exists           another row at the same minute, or another row
                                 holding the same `espn_id`, already carries the
                                 result — shape B above

------------------------------------------------------------------------------
WHAT IT WRITES, AND THE THREE COLUMNS IT KNOWINGLY LEAVES
------------------------------------------------------------------------------

`home_score` and `away_score`. Nothing else.

  * **`status` stays.** These rows are already a settled word, and the card the
    reader is complaining about says FINAL over a WRONG NUMBER, not over no
    number. Writing the right number is the whole repair; re-litigating the
    status is #3780's question about a different population.
  * **`completed_at` stays NULL.** It records when WE NOTICED, not when the game
    ended (a September `now()` on an August game is a new false statement), and
    ESPN's summary header carries no end time to use instead. No reader sees it.
  * **`period` stays.** `'Scheduled'` on a settled row is wrong and is #5390's
    sanitiser's business; it is not on the card and this script has no authority
    for it.

------------------------------------------------------------------------------
RUNNING IT (D51 — backup first, one-command restore)
------------------------------------------------------------------------------

    python3 scripts/repair_5841_zero_zero_finals_from_the_authority.py --selftest
    python3 scripts/repair_5841_zero_zero_finals_from_the_authority.py            # dry run
    python3 scripts/repair_5841_zero_zero_finals_from_the_authority.py --backup --apply

Heroku one-off (gotcha #48 — detached, and PROJECT_PATH=backend puts scripts at
/app, so NO `cd backend`; the script must be on the DEPLOYED SLUG to run):

    heroku run:detached "python3 scripts/repair_5841_zero_zero_finals_from_the_authority.py" -a bainluck
    heroku run:detached "python3 scripts/repair_5841_zero_zero_finals_from_the_authority.py --backup --apply" -a bainluck

Undo:

    heroku run:detached "python3 scripts/restore_5841_zero_zero_finals_from_the_authority.py --apply" -a bainluck
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import DateTime, Integer, String, bindparam, text  # noqa: E402

# IMPORTED, never restated: if `closed` or `completed` stops meaning "this card
# says FINAL", this script's subject has moved and it should stop importing
# rather than keep writing scores onto rows nobody reads as finished.
from app.utils.event_completion import SETTLED_STATUSES  # noqa: E402

# The repo's existing lazy-safe `event.sport.key` read, so the pure predicate
# below answers for an ORM row exactly as it does for the joined row the plan
# query builds. Two spellings of "which sport is this" is how one of them rots.
from app.utils.kalshi_occurrence_start import loaded_sport_key  # noqa: E402

#: The sports where `0 - 0` is a real, reportable result. Candidate-set scoping
#: only — see the docstring: the authority decides every write, this list only
#: decides who gets asked.
DRAW_CAPABLE_PREFIXES: tuple[str, ...] = ("soccer", "rugby", "cricket")

#: How far the row's own kick-off may sit from the ESPN anchor's before the
#: anchor is judged to be a different game. The four shape-A rows are 4h out
#: (their `commence_time` holds an Eastern wall clock where UTC belongs, which is
#: its own defect and is NOT repaired here); `14877917`'s borrowed anchor is 83
#: days out. Nothing measured sits between 4h and 12h, and under-reach is the
#: safe direction: a missed row keeps a wrong score a reader can report, a false
#: match writes a DIFFERENT GAME's score and looks right.
ANCHOR_MAX_HOURS = 12

#: The window in which another row is looking at the same fixture. Deliberately
#: the same number as :data:`ANCHOR_MAX_HOURS`: a row this script would repair
#: from an anchor and a row holding that fixture's result are the same claim, so
#: they cannot be allowed to disagree about what "the same game" means.
TWIN_MAX_HOURS = ANCHOR_MAX_HOURS

#: Default window. The 45 days #5841 measured on, which is also the horizon in
#: which every one of its rows was found. `--lookback-days 0` sweeps all time
#: (98 rows); the band below is only checked on the default.
DEFAULT_LOOKBACK_DAYS = 45

#: Sanity band on the DEFAULT window, measured 2026-09-16 06:4xZ. A repair that
#: finds nothing and reports success is the worst outcome there is (gotcha #53);
#: one that finds an order of magnitude more has had its premise change.
MIN_EXPECTED_POPULATION = 3
MAX_EXPECTED_POPULATION = 40

BAK_TABLE = "bak_5841_zero_zero_scores"

assert SETTLED_STATUSES, "SETTLED_STATUSES is empty — this script has no subject"


def horizon_floor(now: datetime, lookback_days: int = DEFAULT_LOOKBACK_DAYS):
    """The oldest `commence_time` this repair will look at.

    Offset from an injected anchor, never a branch on the clock (gotcha #44), so
    the guard can sweep a matrix and the SQL and the Python predicate can be
    handed the same bound. `lookback_days=0` means "all time".
    """
    if not lookback_days:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
    return now - timedelta(days=lookback_days)


def as_aware(value):
    """Coerce a timestamp to a UTC-aware datetime, or ``None``.

    Three callers hand this three shapes and the adjudication is only worth
    having if it survives all three: production (asyncpg, aware), the guard's
    sqlite corpus (naive — the dialect drops the offset), and
    `POST /api/admin/db-query` (an ISO **string**, which is what lets the plan be
    replayed over production rows before any write). A naive value is read as
    UTC rather than rejected: every one of these columns is written in UTC, and
    the alternative is a `TypeError` deep inside a comparison, which is how a
    pre-flight silently stops covering the rows it was run for.
    """
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def row_sport_key(row):
    """This row's sport key, from the joined column or the loaded relationship.

    The plan query selects `s.key AS sport_key`; an ORM `Event` handed to the
    same predicate by the guard carries `sport`. Both answer here so the pure
    rule is one rule.
    """
    return getattr(row, "sport_key", None) or loaded_sport_key(row)


def is_draw_capable(sport_key) -> bool:
    """Is `0 - 0` a real result in this sport? Candidate scoping only."""
    if not sport_key:
        return False
    return str(sport_key).split("_", 1)[0].lower() in DRAW_CAPABLE_PREFIXES


def _squash(name) -> str:
    """Case- and whitespace-insensitive form of a club name, punctuation dropped.

    `St. Louis` and `St.Louis` are one club and production holds both spellings
    at the same minute (the fold's own docstring records the pair). Deliberately
    NOT a fuzzy match: this decides whether an ESPN payload is about the same two
    clubs as our row, and a loose rule here writes another game's score.
    """
    if not name:
        return ""
    return "".join(ch for ch in str(name).lower() if ch.isalnum())


def candidate_refusal_reason(row, *, floor) -> str | None:
    """Why this row is not even a candidate, or ``None`` if it is one.

    PURE, and the single definition of the population: :data:`_TARGET_WHERE` is
    the same rule in SQL and `tests/test_a_zero_zero_final_is_repaired_only_by_
    the_authority_5841.py` executes both over one corpus and fails on any
    disagreement. A repair whose plan and whose UPDATE are two independent
    readings of "which rows" is how a sweep quietly moves a row nobody
    adjudicated.

    ``row`` is anything carrying the seven attributes below — an ORM `Event`, a
    `Row`, or a plain object built from a `db-query` result.
    """
    if row.status not in SETTLED_STATUSES:
        return (
            f"status is {row.status!r}, which is not one of "
            f"{sorted(SETTLED_STATUSES)} — this card is not claiming a Final, so "
            "there is no false result on it to repair"
        )
    if row.home_score != 0 or row.away_score != 0:
        return (
            "the scoreline is not 0 - 0 — every other wrong score is a different "
            "defect with a different authority question, and #5841 is this one"
        )
    if is_draw_capable(row_sport_key(row)):
        return (
            f"{row_sport_key(row)!r} can really finish 0 - 0 — a scoreless draw "
            "is a result, not an absence"
        )
    if not row.espn_id:
        return (
            "no ESPN anchor — there is nothing to ask. The 11 tennis rows in this "
            "cohort are exactly this shape and are #2772's"
        )
    commence_time = as_aware(row.commence_time)
    if commence_time is None:
        return (
            "no commence_time — a row we cannot place on the clock is one whose "
            "anchor we cannot date-check, and the date check is the guard that "
            "stops a borrowed anchor writing another game's score"
        )
    if commence_time < as_aware(floor):
        return "older than the window this pass was asked for"
    return None


#: The SQL twin of :func:`candidate_refusal_reason`. Bind-parameterised on the
#: bound rather than spelling `now() - interval '45 days'`: the guard executes
#: this exact string against sqlite, and a repair that reads the clock inside its
#: own WHERE cannot be handed the same anchor its plan was built on.
#:
#: The draw-capable clause is spelled as a LIKE per prefix rather than a join on
#: a computed family, so the statement runs unchanged on sqlite.
_DRAW_CAPABLE_SQL = " ".join(
    f"AND COALESCE(s.key, '') NOT LIKE '{prefix}%'" for prefix in DRAW_CAPABLE_PREFIXES
)

_TARGET_WHERE = f"""
       e.status IN :settled
   AND e.home_score = 0
   AND e.away_score = 0
   AND e.espn_id IS NOT NULL
   AND e.commence_time IS NOT NULL
   AND e.commence_time >= :floor
   {_DRAW_CAPABLE_SQL}
"""

_CANDIDATES_SQL = f"""
SELECT e.id, e.status, e.home_score, e.away_score, e.espn_id,
       e.home_team_name, e.away_team_name, e.commence_time, e.sport_id,
       s.key AS sport_key
  FROM events e
  JOIN sports s ON s.id = e.sport_id
 WHERE {_TARGET_WHERE}
 ORDER BY e.commence_time, e.id
"""

#: Another row that already holds this fixture's result: same sport, same two
#: clubs in the same orientation, inside :data:`TWIN_MAX_HOURS`.
#:
#: `0 - 0` on the sibling does NOT count as holding the result — otherwise two
#: rows of this very cohort would veto each other and the pass would refuse the
#: population it exists for.
#:
#: 🔴 THE OBVIOUS SECOND ARM — "or another row stamped with the same `espn_id`",
#: the borrowed-identity shape of #6215 — IS NOT HERE, because it cannot match.
#: `uq_events_espn_id` is a UNIQUE index over every non-null `espn_id`
#: (`models.py`: "a row may hold an authority id; it may not SHARE one"), so two
#: rows holding one anchor is a state the database refuses. Measured on
#: production 2026-09-16 06:5xZ rather than read off the model: the index is
#: present and **0** espn_ids sit on more than one row. It was written, then
#: removed: an inert term is not free, and an inert term on the SUPPRESSING side
#: of a repair is a widening no test can reach.
_SCORED_TWIN_SQL = """
SELECT t.id, t.home_score, t.away_score, t.status, t.commence_time
  FROM events t
 WHERE t.id <> :eid
   AND t.sport_id = :sport_id
   AND t.commence_time BETWEEN :lo AND :hi
   AND lower(t.home_team_name) = lower(:home)
   AND lower(t.away_team_name) = lower(:away)
   AND (t.home_score IS NOT NULL OR t.away_score IS NOT NULL)
   AND NOT (t.home_score = 0 AND t.away_score = 0)
 ORDER BY t.id
"""

#: The write itself, as ONE string two callers spend: :func:`write_scores` on
#: production and the guard against a sqlite corpus. A test that retypes the
#: UPDATE proves a statement nobody runs.
#:
#: 🔴 IT RE-CHECKS THE ROW IT ADJUDICATED, NOT JUST THE ID. The plan is built
#: once — one ESPN fetch per row — and the sweep then takes minutes on a
#: write-hot table. A real score arriving in that window from the live pass, or
#: the row being unsettled by a replay (`espn_helpers` writes `status='live',
#: completed_at=NULL` when ESPN reports `in` on a settled row), leaves a narrow
#: `WHERE id = :eid` matching and overwrites an authority's own fresh write with
#: this pass's older reading. Re-stating the scoreline, the status and the
#: anchor makes that impossible: anything that moved, this touches 0 rows.
_WRITE_SQL = """
UPDATE events
   SET home_score = :home_score, away_score = :away_score
 WHERE id = :eid
   AND home_score = 0
   AND away_score = 0
   AND status = :status
   AND espn_id = :espn_id
"""


def statement(sql: str):
    """`text(sql)` with the shared binds TYPED, and `:settled` expanded.

    The types are not decoration. `:floor` is a timezone-aware datetime and an
    untyped `text()` bind hands it straight to the driver: asyncpg takes it, and
    the guard's sqlite renders it in a format that does not compare against the
    column's own storage — so the SQL half of the rule would silently select
    nothing and "plan and SQL agree" would pass over two empty sets.
    """
    return text(sql).bindparams(
        bindparam("settled", expanding=True, type_=String),
        bindparam("floor", type_=DateTime(timezone=True)),
    )


def write_statement():
    return text(_WRITE_SQL).bindparams(
        bindparam("home_score", type_=Integer),
        bindparam("away_score", type_=Integer),
        bindparam("status", type_=String),
        bindparam("espn_id", type_=String),
    )


def anchor_refusal_reason(row, anchor, *, max_hours: int = ANCHOR_MAX_HOURS) -> str | None:
    """Why the ESPN summary stamped on this row must NOT be cashed, or ``None``.

    PURE and offline: ``anchor`` is an
    :class:`app.services.espn_api.ESPNEvent`-shaped object, so every clause is
    unit-testable against the real specimens without a network.

    Order matters for the OPERATOR, not for correctness: the date and identity
    clauses come first because they are the ones that answer "is this even the
    same game", and a run whose refusals are dominated by them is a run that has
    found a matching defect rather than a scoring one.
    """
    if anchor is None:
        return (
            "espn_unreachable — ESPN did not answer for this anchor. NOT the same "
            "as 'the game does not exist': an empty answer is a response shape "
            "(gotcha #53), so the row is left exactly as it is and this pass "
            "reports a refusal rather than a repair"
        )

    anchor_start = as_aware(getattr(anchor, "date", None))
    row_start = as_aware(row.commence_time)
    if anchor_start is None:
        return "anchor_has_no_date — nothing to date-check against, so nothing to trust"
    delta_hours = abs((anchor_start - row_start).total_seconds()) / 3600.0
    if delta_hours > max_hours:
        return (
            f"anchor_is_a_different_date — the row starts {row_start.isoformat()} "
            f"and ESPN's game starts {anchor_start.isoformat()}, {delta_hours:.1f}h "
            f"apart (limit {max_hours}h). A stamped id is not a correspondence"
        )

    anchor_home = _squash(getattr(getattr(anchor, "home_team", None), "display_name", None)
                          or getattr(getattr(anchor, "home_team", None), "name", None))
    anchor_away = _squash(getattr(getattr(anchor, "away_team", None), "display_name", None)
                          or getattr(getattr(anchor, "away_team", None), "name", None))
    row_home, row_away = _squash(row.home_team_name), _squash(row.away_team_name)
    if not anchor_home or not anchor_away:
        return "anchor_has_no_teams — an unparseable payload adjudicates nothing"
    if anchor_home != row_home or anchor_away != row_away:
        return (
            "anchor_is_a_different_game — ESPN says "
            f"{anchor_home!r} v {anchor_away!r}, the row says {row_home!r} v "
            f"{row_away!r}. Orientation is part of the test: the same two clubs "
            "the other way round is the other half of a home-and-away pair"
        )

    if getattr(anchor, "stopped_without_result", False):
        return (
            "anchor_is_not_final — ESPN reports this competition over and NOT "
            "finished (postponed/abandoned, #3397). A score exists in the payload "
            "and it is the score of a game nobody completed"
        )
    if getattr(anchor, "status", None) != "post":
        return f"anchor_is_not_final — ESPN status is {getattr(anchor, 'status', None)!r}, not a Final"

    home_score = getattr(anchor, "home_score", None)
    away_score = getattr(anchor, "away_score", None)
    if home_score is None or away_score is None:
        return "anchor_has_no_score — a Final with no numbers adjudicates nothing"
    if home_score == 0 and away_score == 0:
        return (
            "authority_confirms_0_0 — the row is RIGHT. Nothing is written and "
            "this is not a failure: it is the only answer that can distinguish a "
            "fabricated 0 - 0 from a real one"
        )
    return None


async def scored_twin(session, row) -> dict | None:
    """The row that already holds this fixture's result, or ``None``.

    A read, and the only clause of this repair that looks outside the row and
    its anchor. Shape B of the cohort — three MLB rows whose sibling at the same
    minute carries the real score — is refused here rather than repaired,
    because a second scored copy of one game is a worse defect than the one it
    would replace and the survivor election that serves the right one is
    `fold_twin_events`, which is a serve-time decision in another lane's file.
    """
    row_start = as_aware(row.commence_time)
    found = (
        await session.execute(
            text(_SCORED_TWIN_SQL),
            {
                "eid": row.id,
                "sport_id": row.sport_id,
                "lo": row_start - timedelta(hours=TWIN_MAX_HOURS),
                "hi": row_start + timedelta(hours=TWIN_MAX_HOURS),
                "home": row.home_team_name,
                "away": row.away_team_name,
            },
        )
    ).first()
    if not found:
        return None
    return {
        "id": found.id,
        "score": f"{found.home_score}-{found.away_score}",
        "status": found.status,
    }


async def adjudicate(session, espn, row) -> dict:
    """One row's verdict: ``{"id", "verdict", "reason"|"home_score"/"away_score"}``.

    The ESPN fetch is the expensive half and it is deliberately LAST: a row with
    a scored twin is refused without spending a request on it.
    """
    twin = await scored_twin(session, row)
    if twin:
        return {
            "id": row.id,
            "verdict": "REFUSED",
            "reason": (
                f"scored_twin_exists — event {twin['id']} ({twin['status']}) already "
                f"holds this fixture at {twin['score']}. Repairing this row would "
                "publish one game twice"
            ),
        }

    anchor = await espn.get_event(row.sport_key, row.espn_id)
    reason = anchor_refusal_reason(row, anchor)
    if reason:
        return {"id": row.id, "verdict": "REFUSED", "reason": reason}
    return {
        "id": row.id,
        "verdict": "WRITE",
        "home_score": anchor.home_score,
        "away_score": anchor.away_score,
        "anchor_date": as_aware(anchor.date).isoformat(),
    }


def population_refusal_reason(population: int, *, default_window: bool) -> str | None:
    """Why the measured population must NOT be swept, or ``None``. Pure."""
    if not default_window:
        return None
    if population < MIN_EXPECTED_POPULATION:
        return (
            f"population {population} is below the floor {MIN_EXPECTED_POPULATION} "
            "— either this repair has already run, or the cohort it was built on "
            "no longer describes production. Re-measure before writing anything; "
            "a sweep that finds nothing and exits 0 is the failure this floor is "
            "here to make loud"
        )
    if population > MAX_EXPECTED_POPULATION:
        return (
            f"population {population} exceeds the ceiling {MAX_EXPECTED_POPULATION} "
            "— this cohort is supposed to be FROZEN (270 MLB rows finished in "
            "September, 0 scored 0 - 0). A growing cohort means a writer is "
            "producing them again; find it before sweeping"
        )
    return None


async def ensure_backup(session, plans: list[dict], rows_by_id: dict) -> int:
    """Create the D51 backup table and bank the CURRENT scoreline and status.

    Only the rows about to be written — a backup of rows nobody touched is a
    restore script that can undo a repair it did not make.

    `ON CONFLICT DO NOTHING` keeps the FIRST banked tuple, which is the
    pre-repair one: a re-run after a partial apply must not bank the score this
    pass just wrote as the thing to restore to.
    """
    await session.execute(
        text(
            f"CREATE TABLE IF NOT EXISTS {BAK_TABLE} ("
            "  event_id bigint PRIMARY KEY,"
            "  old_home_score integer,"
            "  old_away_score integer,"
            "  old_status text NOT NULL,"
            "  banked_at timestamptz NOT NULL DEFAULT now())"
        )
    )
    await session.commit()

    banked = 0
    for plan in plans:
        row = rows_by_id[plan["id"]]
        result = await session.execute(
            text(
                f"INSERT INTO {BAK_TABLE} "
                "(event_id, old_home_score, old_away_score, old_status) "
                "VALUES (:eid, :h, :a, :status) ON CONFLICT (event_id) DO NOTHING"
            ),
            {"eid": row.id, "h": row.home_score, "a": row.away_score, "status": row.status},
        )
        banked += result.rowcount or 0
    await session.commit()
    return banked


async def write_scores(session, plans: list[dict], rows_by_id: dict) -> tuple[int, list[int], list[int]]:
    """Write the authority's scoreline, ONE ROW PER TRANSACTION.

    Deliberately not a batch UPDATE: `events` is write-hot (constant poller and
    backfill locks) and a batched one-off rolls back on every row.

    Returns ``(written, skipped_ids, failed_ids)``. A rowcount of 0 is SKIPPED,
    not written and not failed — it means the row moved between plan and write
    and the re-checked WHERE correctly declined. Both lists are RETAINED rather
    than only printed: on a detached dyno whose stdout nobody reads, a printed
    line that does not reach the exit code is indistinguishable from a clean run
    (gotcha #53).
    """
    written, skipped, failed = 0, [], []
    for plan in plans:
        row = rows_by_id[plan["id"]]
        params = {
            "eid": row.id,
            "home_score": plan["home_score"],
            "away_score": plan["away_score"],
            "status": row.status,
            "espn_id": row.espn_id,
        }
        for attempt in (1, 2, 3):
            try:
                result = await session.execute(write_statement(), params)
                await session.commit()
                if result.rowcount:
                    written += result.rowcount
                else:
                    skipped.append(row.id)
                break
            except Exception as exc:  # noqa: BLE001 — retry, then surface
                await session.rollback()
                if attempt == 3:
                    print(f"  FAILED event {row.id} after 3 attempts: {exc}")
                    failed.append(row.id)
                else:
                    await asyncio.sleep(attempt)
    return written, skipped, failed


async def run(*, backup: bool, apply: bool, lookback_days: int, only_ids: list[int] | None) -> int:
    from app.services.espn_api import get_espn_service

    now = datetime.now(timezone.utc)
    floor = horizon_floor(now, lookback_days)
    default_window = lookback_days == DEFAULT_LOOKBACK_DAYS and not only_ids
    params = {"settled": sorted(SETTLED_STATUSES), "floor": floor}

    print(f"=== #5841 · settled rows scored 0 - 0, {lookback_days or 'all'}-day window ===")
    print(f"horizon floor: {floor.isoformat()}")

    espn = get_espn_service()
    # `try/finally`, not a trailing `await espn.close()`: THREE of the paths
    # below RETURN from inside the session block (the band refusal, the dry run,
    # the empty plan), so a close on the last line runs on the one path that
    # needs it least and leaks the httpx client on every path a dry run takes.
    try:
        exit_code = await _run_inner(
            espn=espn, params=params, only_ids=only_ids, apply=apply,
            backup=backup, default_window=default_window,
        )
    finally:
        await espn.close()
    return exit_code


async def _run_inner(*, espn, params, only_ids, apply, backup, default_window) -> int:
    from app.tasks.base import get_task_session

    exit_code = 0
    async with get_task_session() as session:
        rows = (await session.execute(statement(_CANDIDATES_SQL), params)).all()
        if only_ids:
            rows = [r for r in rows if r.id in set(only_ids)]
        rows_by_id = {r.id: r for r in rows}
        print(f"candidates: {len(rows)}")

        band = population_refusal_reason(len(rows), default_window=default_window)
        if band and apply:
            print(f"\n🔴 REFUSING TO APPLY: {band}")
            return 2
        if band:
            print(f"\n⚠️  band: {band}")

        verdicts = []
        for row in rows:
            verdict = await adjudicate(session, espn, row)
            verdicts.append(verdict)
            fixture = f"{row.home_team_name} v {row.away_team_name}"
            when = as_aware(row.commence_time).isoformat()
            if verdict["verdict"] == "WRITE":
                print(
                    f"  WRITE   {row.id} [{row.sport_key}] {fixture} {when} "
                    f"0-0 → {verdict['home_score']}-{verdict['away_score']} "
                    f"(anchor {row.espn_id} @ {verdict['anchor_date']})"
                )
            else:
                print(f"  REFUSE  {row.id} [{row.sport_key}] {fixture} {when} — {verdict['reason']}")

        plans = [v for v in verdicts if v["verdict"] == "WRITE"]
        refusals = [v for v in verdicts if v["verdict"] != "WRITE"]
        print(f"\nplanned writes: {len(plans)} · refusals: {len(refusals)}")

        if not apply:
            print("\nDRY RUN — nothing written. Add --backup --apply to write.")
            return 0
        if not plans:
            print("\nNothing to write.")
            return 0

        if backup:
            banked = await ensure_backup(session, plans, rows_by_id)
            print(f"backed up {banked} row(s) into {BAK_TABLE}")
        else:
            print("⚠️  --apply without --backup: no restore point is being written")

        written, skipped, failed = await write_scores(session, plans, rows_by_id)
        print(f"\nwritten: {written} · skipped (row moved since the plan): {len(skipped)} · failed: {len(failed)}")
        if skipped:
            print(f"  skipped ids: {skipped}")
        if failed:
            print(f"  FAILED ids: {failed}")
            exit_code = 1
    return exit_code


def _selftest() -> int:
    """Offline arm: every refusal, on the real specimens, with no database.

    Run by `--selftest` and by CI through the guard file; the point of having it
    here too is that the operator on the dyno can prove the adjudicator before
    spending a production read.
    """
    from types import SimpleNamespace as NS

    def row(**kw):
        base = dict(
            id=1, status="closed", home_score=0, away_score=0, espn_id="401816574",
            home_team_name="Baltimore Orioles", away_team_name="New York Yankees",
            commence_time=datetime(2026, 8, 18, 18, 35, tzinfo=timezone.utc),
            sport_id=53232, sport_key="baseball_mlb",
        )
        base.update(kw)
        return NS(**base)

    def anchor(**kw):
        base = dict(
            date=datetime(2026, 8, 18, 22, 35, tzinfo=timezone.utc), status="post",
            home_team=NS(display_name="Baltimore Orioles", name="Orioles"),
            away_team=NS(display_name="New York Yankees", name="Yankees"),
            home_score=1, away_score=3, stopped_without_result=False,
        )
        base.update(kw)
        return NS(**base)

    floor = horizon_floor(datetime(2026, 9, 16, tzinfo=timezone.utc))
    checks: list[tuple[str, bool]] = []

    # The real shape-A specimen: 4h between the row's clock and ESPN's, same
    # clubs, a Final that is not 0-0 ⇒ the only WRITE this script makes.
    checks.append(("15201192 is a candidate", candidate_refusal_reason(row(), floor=floor) is None))
    checks.append(("15201192's anchor is cashable", anchor_refusal_reason(row(), anchor()) is None))

    # 14877917's BORROWED anchor: the row is 2026-08-29, the summary is
    # 2026-06-07. This is the clause the whole script exists behind.
    borrowed = anchor(
        date=datetime(2026, 6, 7, 17, 35, tzinfo=timezone.utc),
        home_team=NS(display_name="New York Yankees", name="Yankees"),
        away_team=NS(display_name="Boston Red Sox", name="Red Sox"),
        home_score=6, away_score=1,
    )
    borrowed_row = row(
        id=14877917, home_team_name="New York Yankees", away_team_name="Boston Red Sox",
        espn_id="401815659", commence_time=datetime(2026, 8, 29, 17, 5, tzinfo=timezone.utc),
    )
    reason = anchor_refusal_reason(borrowed_row, borrowed)
    checks.append(("a borrowed anchor is refused on its DATE", bool(reason) and "different_date" in reason))

    # Same date, wrong clubs.
    reason = anchor_refusal_reason(row(), anchor(home_team=NS(display_name="Detroit Tigers", name="Tigers")))
    checks.append(("a different fixture is refused", bool(reason) and "different_game" in reason))

    # Same clubs, reversed orientation — the other half of a home-and-away pair.
    reason = anchor_refusal_reason(
        row(),
        anchor(home_team=NS(display_name="New York Yankees", name="Yankees"),
               away_team=NS(display_name="Baltimore Orioles", name="Orioles")),
    )
    checks.append(("a reversed fixture is refused", bool(reason) and "different_game" in reason))

    # A postponement carries a score and is not a result (#3397).
    reason = anchor_refusal_reason(row(), anchor(stopped_without_result=True))
    checks.append(("a postponement is refused", bool(reason) and "not_final" in reason))

    reason = anchor_refusal_reason(row(), anchor(status="in"))
    checks.append(("a live game is refused", bool(reason) and "not_final" in reason))

    # The authority agreeing with the row is the answer that makes the 0-0
    # question decidable at all.
    reason = anchor_refusal_reason(row(), anchor(home_score=0, away_score=0))
    checks.append(("a real 0 - 0 is left alone", bool(reason) and "confirms_0_0" in reason))

    reason = anchor_refusal_reason(row(), None)
    checks.append(("an unreachable authority writes nothing", bool(reason) and "unreachable" in reason))

    # Candidate scoping.
    checks.append(("soccer is not a candidate",
                   bool(candidate_refusal_reason(row(sport_key="soccer_epl"), floor=floor))))
    checks.append(("a scoreless tennis row with no anchor is not a candidate",
                   bool(candidate_refusal_reason(row(sport_key="tennis_atp_us_open", espn_id=None), floor=floor))))
    checks.append(("a scheduled row is not a candidate",
                   bool(candidate_refusal_reason(row(status="scheduled"), floor=floor))))
    checks.append(("a scored row is not a candidate",
                   bool(candidate_refusal_reason(row(home_score=3), floor=floor))))

    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'ok  ' if ok else 'FAIL'} {name}")
    print(f"\nselftest: {len(checks) - len(failed)}/{len(checks)}")
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write (default is a dry run)")
    parser.add_argument("--backup", action="store_true", help=f"bank the old scores into {BAK_TABLE} first")
    parser.add_argument("--lookback-days", type=int, default=DEFAULT_LOOKBACK_DAYS,
                        help="0 sweeps all time; the sanity band only applies to the default")
    parser.add_argument("--ids", type=str, default=None, help="comma-separated event ids to restrict to")
    parser.add_argument("--selftest", action="store_true", help="offline adjudicator check, no database")
    args = parser.parse_args()

    if args.selftest:
        return _selftest()

    only_ids = [int(x) for x in args.ids.split(",")] if args.ids else None
    return asyncio.run(
        run(backup=args.backup, apply=args.apply,
            lookback_days=args.lookback_days, only_ids=only_ids)
    )


if __name__ == "__main__":
    sys.exit(main())
