"""#10960 — a Kalshi MLB game question moves onto the game its ticker names.

THE SHIP: an MLB team-total question appears on, and is graded from, the game
its ticker names — not another game between the same two clubs.

WHY (production read 2026-10-12 23:4xZ, ESPN boards read the same hour)
------------------------------------------------------------------------

A Kalshi MLB game ticker carries the game's own start, US Eastern:
``KXMLBTEAMTOTAL-26MAY052140ATLSEA`` is Atlanta at Seattle, 2026-05-05 21:40 ET
(2026-05-06 01:40Z). 463 of 2,332 linked ``KXMLBTEAMTOTAL`` rows sit on an
event more than an hour from that start, and every other KXMLB game series
looks the same (GAME 385, RFI 484, F5 483 …). For ~356 team totals the
ticker's own game IS a row of ours — same two clubs, within 20 minutes of the
ticker — and the market sits on a different game of the series, up to weeks
away (``KXMLBTEAMTOTAL-26JUN222210ATLSD`` sat on the July 22 Padres v Braves
game). The links were written April–August: by the July historical backfill,
which attached settled markets to the nearest game of the pair while many of
those games had no row yet (the Aug 20 schedule fill created them), and by
retired twin merges. None has been written since Aug 21: every newer >1h
case has no row at the ticker's time (a changed start, e.g. the PHI@ATL
wild-card game ticketed 14:00 ET, played 20:00 ET — the same game, correctly
linked). So this is the debt; the forward matcher already refuses >3h
(``_ticker_date_conflicts_with_event``).

THE RULE (id-anchored, ruling 048)
----------------------------------

A market moves only when ALL hold:

1. its ticker names an HHMM start and its current event is outside the
   matcher's own window of it (``_ticker_date_conflicts_with_event``, ±3h) —
   a market the matcher would keep is never touched;
2. exactly one row of ours, with the SAME two clubs (team ids) as the row it
   sits on, starts within that window of the ticker — and it carries an ESPN id;
3. ESPN's own MLB board for the ticker's Eastern date lists that ESPN id,
   starting within the same window. That dereference is the anchor: ESPN, not
   our clock, says the target is the game played (or postponed) at the time the
   ticker names.

Anything else is reported and left where it is: ``no_candidate`` (no row of
ours is the ticker's game — e.g. TB@NYY 05-23, postponed; ESPN's id 401815462
is held by no row), ``ambiguous`` (two rows in the window), ``no_espn_id``,
``espn_dark`` (the board could not be read), ``espn_disagrees`` and
``retired_target`` (the ticker's game is a ``merged``/``voided`` row — a
wrongly retired real game is a separate repair, never a link onto a hidden row).

WHAT IS WRITTEN
---------------

``futures_markets.event_id`` only, compare-and-swap on the value read, for the
moves in the plan. Every move then appends a ``market_link_changes`` history row
(actor ``admin_repair``, phase ``repair_10960``). Nothing else: no event, score,
outcome or price is touched.

THE REVIEWED PLAN IS THE ONLY PLAN APPLIED
------------------------------------------

``--apply`` re-reads the rows and ESPN's boards, so the plan it builds can differ
from the dry run a person read — a changed board, a new row, a moved market —
with the SAME count. A count ceiling cannot see that. So the dry run prints
``plan_digest``: sha256 over the scope and every move's ``(market_id,
external_id, from_event_id, to_event_id)`` with its witness (ticker start,
target start, ESPN id, ESPN start and status). ``--apply`` requires
``--plan-digest`` and refuses, before the backup, unless the plan it just built
hashes to exactly that value. The digest covers every move even when the
printed sample is cut to 40 (``--full`` prints all of them). A team-total
digest never authorises an all-series plan: the scope is hashed.

ALL OR NOTHING
--------------

The moves are one transaction: every row must pass its compare-and-swap, or the
whole write rolls back and nothing moves (``ROLLED_BACK_CHANGED_UNDER_RUN``,
naming the rows that drifted). The bank is marked ``applied_at`` inside that
same transaction, so a rolled-back apply leaves bank rows that ``--restore``
never acts on. After the commit, a short receipt count or a row read back off
its target is reported by id with its own outcome and a non-zero exit — never
as a clean whole-cohort apply.

THE BACKUP AND THE UNDO
-----------------------

``--apply`` banks every planned ``(market_id, event_id_before, event_id_after)``
in ``bak_10960_market_links`` and refuses to write if the bank is short.
``--restore`` moves every APPLIED banked market still on its ``event_id_after``
back to ``event_id_before``. ``CREATE TABLE IF NOT EXISTS`` is runtime DDL
behind a person's invocation on a named app: notice 47(c), not migration-class.

    heroku run:detached -a bainluck -- python3 scripts/repair_10960_mlb_markets_on_another_game.py --full                   # dry run, team totals; prints plan_digest
    heroku run:detached -a bainluck -- python3 scripts/repair_10960_mlb_markets_on_another_game.py --apply --plan-digest <sha256>  # backup + move THAT plan
    heroku run:detached -a bainluck -- python3 scripts/repair_10960_mlb_markets_on_another_game.py --restore                # undo
    ... --series KXMLBGAME                 # another series (its own dry run, its own digest)
    ... --all-series                       # every KXMLB ticker with an HHMM start (its own digest)

Refuses unless ``HEROKU_APP_NAME`` is ``bainluck`` or ``bainluck-heavy``.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

PRODUCTION_APPS = frozenset({"bainluck", "bainluck-heavy"})

BACKUP_TABLE = "bak_10960_market_links"
PHASE = "repair_10960"
SPORT_KEY = "baseball_mlb"
DEFAULT_SERIES = "KXMLBTEAMTOTAL"

#: Ceiling on one apply. The team-total plan reads ~360; a pairing regression
#: that starts moving correctly linked markets shows up here first.
DEFAULT_MAX_MOVES = 600

RETIRED = frozenset({"merged", "voided"})

MOVE = "move"
NO_CANDIDATE = "no_candidate"
AMBIGUOUS = "ambiguous"
NO_ESPN_ID = "no_espn_id"
ESPN_DARK = "espn_dark"
ESPN_DISAGREES = "espn_disagrees"
RETIRED_TARGET = "retired_target"

#: Run outcomes. Anything but DRY_RUN / NOTHING_TO_MOVE / APPLIED exits non-zero.
DRY_RUN = "DRY_RUN"
NOTHING_TO_MOVE = "NOTHING_TO_MOVE"
APPLIED = "APPLIED"
ROLLED_BACK_CHANGED_UNDER_RUN = "ROLLED_BACK_CHANGED_UNDER_RUN"
ROLLED_BACK_ERROR = "ROLLED_BACK_ERROR"
APPLIED_RECEIPTS_SHORT = "APPLIED_RECEIPTS_SHORT"
APPLIED_READBACK_SHORT = "APPLIED_READBACK_SHORT"
RESTORED = "RESTORED"
RESTORE_SHORT = "RESTORE_SHORT"
CLEAN_OUTCOMES = frozenset({DRY_RUN, NOTHING_TO_MOVE, APPLIED, RESTORED})

#: The fields of one move that the digest binds: the write and its witness.
DIGEST_FIELDS = (
    "market_id", "external_id", "from_event_id", "to_event_id",
    "ticker_start", "target_start", "espn_id", "espn_start", "espn_status",
)

UNDO_LINE = (
    "heroku run:detached -a bainluck -- "
    "python3 scripts/repair_10960_mlb_markets_on_another_game.py --restore"
)


class Refused(RuntimeError):
    """The run stops before any write."""


def refuse_unless_production(env: dict) -> None:
    app = env.get("HEROKU_APP_NAME", "")
    if app not in PRODUCTION_APPS:
        raise Refused(
            f"HEROKU_APP_NAME={app!r} is not a production app "
            f"({sorted(PRODUCTION_APPS)}); refusing"
        )


def series_bounds(series: str) -> tuple[str, str]:
    """A btree range for ``external_id LIKE '<series>-%'``.

    The upper bound bumps the LAST LETTER, never appends punctuation: the
    column's collation ignores a trailing ``-``/``.`` in a range bound and the
    range comes back empty (measured on this repair's own population query).
    """
    if not series or not series.isalnum():
        raise Refused(f"series {series!r} must be alphanumeric")
    return series, series[:-1] + chr(ord(series[-1]) + 1)


@dataclass(frozen=True)
class Market:
    market_id: int
    external_id: str
    name: Optional[str]
    event_id: int
    event_start: datetime
    home_team_id: Optional[int]
    away_team_id: Optional[int]


@dataclass(frozen=True)
class Candidate:
    event_id: int
    start: datetime
    home_team_id: Optional[int]
    away_team_id: Optional[int]
    espn_id: Optional[str]
    status: str


@dataclass(frozen=True)
class BoardEntry:
    espn_id: str
    start: datetime
    status: Optional[str]


@dataclass
class Plan:
    moves: list[dict] = field(default_factory=list)
    kept: list[dict] = field(default_factory=list)
    examined: int = 0
    in_window: int = 0

    def counts(self) -> dict:
        out = Counter(k["verdict"] for k in self.kept)
        out[MOVE] = len(self.moves)
        out["examined"] = self.examined
        out["already_in_window"] = self.in_window
        return dict(sorted(out.items()))


def ticker_start(external_id: str) -> Optional[datetime]:
    """The UTC instant the ticker's HHMM names (the matcher's own parser)."""
    from app.tasks.prediction_market_matching import ticker_start_utc
    from app.utils.prediction_market_matching import extract_game_date_from_ticker

    return ticker_start_utc(extract_game_date_from_ticker(external_id))


def window_hours(external_id: str) -> int:
    from app.tasks.prediction_market_matching import _event_date_max_diff_hours

    return _event_date_max_diff_hours(external_id.split("-", 1)[0].lower())


def outside_window(external_id: str, start: datetime) -> bool:
    """The matcher's own refusal: True when ``start`` cannot be the ticker's game."""
    from app.tasks.prediction_market_matching import _ticker_date_conflicts_with_event
    from app.utils.prediction_market_matching import extract_game_date_from_ticker

    return _ticker_date_conflicts_with_event(
        extract_game_date_from_ticker(external_id),
        start,
        external_id.split("-", 1)[0].lower(),
    )


def eastern_date(moment: datetime) -> date:
    from app.utils.mlb_reschedule_ghosts import local_date

    return local_date(moment)


def _same_clubs(market: Market, cand: Candidate) -> bool:
    if market.home_team_id is None or market.away_team_id is None:
        return False
    return {cand.home_team_id, cand.away_team_id} == {
        market.home_team_id, market.away_team_id
    }


def decide(
    market: Market,
    candidates: list[Candidate],
    boards: dict[date, Optional[dict[str, BoardEntry]]],
) -> tuple[str, Optional[Candidate], dict]:
    """One market's verdict. Pure — the unit file drives it.

    ``candidates`` are rows near the ticker's start; this re-applies every
    condition on them so a loose candidate query can never widen a move.
    """
    start = ticker_start(market.external_id)
    hours = window_hours(market.external_id)
    near = [
        c for c in candidates
        if c.event_id != market.event_id
        and _same_clubs(market, c)
        and start is not None
        and abs((c.start - start).total_seconds()) <= hours * 3600
    ]
    detail = {"ticker_start": start.isoformat() if start else None}
    if not near:
        return NO_CANDIDATE, None, detail
    if len(near) > 1:
        detail["candidates"] = sorted(c.event_id for c in near)
        return AMBIGUOUS, None, detail
    target = near[0]
    detail["target_start"] = target.start.isoformat()
    if target.status in RETIRED:
        detail["target_status"] = target.status
        return RETIRED_TARGET, target, detail
    if not target.espn_id:
        return NO_ESPN_ID, target, detail
    board = boards.get(eastern_date(start))
    if board is None:
        return ESPN_DARK, target, detail
    entry = board.get(str(target.espn_id))
    if entry is None or abs((entry.start - start).total_seconds()) > hours * 3600:
        detail["espn_id"] = target.espn_id
        detail["espn_start"] = entry.start.isoformat() if entry else None
        return ESPN_DISAGREES, target, detail
    detail["espn_id"] = target.espn_id
    detail["espn_start"] = entry.start.isoformat()
    detail["espn_status"] = entry.status
    return MOVE, target, detail


def plan_moves(
    markets: list[Market],
    candidates: dict[int, list[Candidate]],
    boards: dict[date, Optional[dict[str, BoardEntry]]],
) -> Plan:
    plan = Plan()
    for market in markets:
        plan.examined += 1
        if ticker_start(market.external_id) is None:
            continue
        if not outside_window(market.external_id, market.event_start):
            plan.in_window += 1
            continue
        verdict, target, detail = decide(
            market, candidates.get(market.market_id, []), boards
        )
        row = {
            "market_id": market.market_id,
            "external_id": market.external_id,
            "from_event_id": market.event_id,
            "from_start": market.event_start.isoformat(),
            "verdict": verdict,
            **detail,
        }
        if verdict == MOVE:
            row["to_event_id"] = target.event_id
            plan.moves.append(row)
        else:
            if target is not None:
                row["target_event_id"] = target.event_id
            plan.kept.append(row)
    return plan


def plan_digest(series_list: list[str], moves: list[dict]) -> str:
    """sha256 of the scope and every move with its witness, order-free.

    Canonical JSON (sorted keys, moves sorted by market id) so the same plan
    hashes the same on the dry run and the apply, and any changed field — a
    target, a from-row, an ESPN start — changes the digest.
    """
    body = {
        "phase": PHASE,
        "series": sorted(series_list),
        "moves": sorted(
            ({k: m.get(k) for k in DIGEST_FIELDS} for m in moves),
            key=lambda m: m["market_id"],
        ),
    }
    blob = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


def board_from_espn(body: Optional[dict]) -> Optional[dict[str, BoardEntry]]:
    # An empty answer is not an empty MLB day: a day this repair reads has a
    # candidate game on it, so "no events" is dark, never "ESPN disagrees".
    if not body or not body.get("events"):
        return None
    out: dict[str, BoardEntry] = {}
    for event in body.get("events") or []:
        try:
            espn_id = str(event["id"])
            start = datetime.fromisoformat(str(event["date"]).replace("Z", "+00:00"))
        except (KeyError, TypeError, ValueError):
            continue
        status = ((event.get("status") or {}).get("type") or {}).get("name")
        out[espn_id] = BoardEntry(espn_id, start, str(status) if status else None)
    return out


_MARKETS_SQL = """
SELECT fm.id, fm.external_id, fm.name, fm.event_id,
       e.commence_time, e.home_team_id, e.away_team_id
  FROM futures_markets fm
  JOIN events e ON e.id = fm.event_id
  JOIN sports s ON s.id = e.sport_id
 WHERE fm.source = 'kalshi'
   AND fm.external_id >= :lo AND fm.external_id < :hi
   AND fm.external_id LIKE :pattern
   AND s.key = :sport
 ORDER BY fm.id
"""

_CANDIDATES_SQL = """
SELECT q.market_id, e.id, e.commence_time, e.home_team_id, e.away_team_id,
       e.espn_id, e.status
  FROM unnest(CAST(:mids AS bigint[]), CAST(:starts AS timestamptz[]),
              CAST(:hours AS int[]), CAST(:homes AS int[]), CAST(:aways AS int[]))
       AS q(market_id, ts, hrs, h, a)
  JOIN events e
    ON e.sport_id = (SELECT id FROM sports WHERE key = :sport)
   AND e.commence_time BETWEEN q.ts - make_interval(hours => q.hrs)
                           AND q.ts + make_interval(hours => q.hrs)
   AND ((e.home_team_id = q.h AND e.away_team_id = q.a)
        OR (e.home_team_id = q.a AND e.away_team_id = q.h))
"""


async def read_markets(session, series_list: list[str]) -> list[Market]:
    out: list[Market] = []
    for series in series_list:
        lo, hi = series_bounds(series)
        rows = await session.execute(
            text(_MARKETS_SQL),
            {"lo": lo, "hi": hi, "sport": SPORT_KEY,
             "pattern": "KXMLB%" if series == ALL_SERIES else f"{series}-%"},
        )
        out.extend(
            Market(int(r.id), r.external_id, r.name, int(r.event_id), r.commence_time,
                   r.home_team_id, r.away_team_id)
            for r in rows
        )
    return out


async def read_candidates(session, markets: list[Market]) -> dict[int, list[Candidate]]:
    asks = []
    for m in markets:
        start = ticker_start(m.external_id)
        if start is None or m.home_team_id is None or m.away_team_id is None:
            continue
        if not outside_window(m.external_id, m.event_start):
            continue
        asks.append((m.market_id, start, window_hours(m.external_id),
                     m.home_team_id, m.away_team_id))
    out: dict[int, list[Candidate]] = defaultdict(list)
    for i in range(0, len(asks), 500):
        chunk = asks[i:i + 500]
        rows = await session.execute(
            text(_CANDIDATES_SQL),
            {
                "mids": [a[0] for a in chunk],
                "starts": [a[1] for a in chunk],
                "hours": [a[2] for a in chunk],
                "homes": [a[3] for a in chunk],
                "aways": [a[4] for a in chunk],
                "sport": SPORT_KEY,
            },
        )
        for r in rows:
            out[int(r.market_id)].append(
                Candidate(int(r.id), r.commence_time, r.home_team_id, r.away_team_id,
                          str(r.espn_id) if r.espn_id else None, str(r.status))
            )
    return out


async def read_boards(days: set[date]) -> dict[date, Optional[dict[str, BoardEntry]]]:
    from app.services.espn_api import get_espn_service

    service = get_espn_service()
    boards: dict[date, Optional[dict[str, BoardEntry]]] = {}
    for day in sorted(days):
        try:
            body = await service.get_combat_card_board(
                SPORT_KEY, dates=day.strftime("%Y%m%d")
            )
        except Exception:  # a dark day refuses its own markets, never the run
            body = None
        boards[day] = board_from_espn(body)
    return boards


def board_days(markets: list[Market], candidates: dict[int, list[Candidate]]) -> set[date]:
    days = set()
    for m in markets:
        if candidates.get(m.market_id):
            start = ticker_start(m.external_id)
            if start is not None:
                days.add(eastern_date(start))
    return days


async def _backup(session, moves: list[dict]) -> int:
    await session.execute(
        text(
            f"CREATE TABLE IF NOT EXISTS {BACKUP_TABLE} ("
            " market_id bigint PRIMARY KEY,"
            " event_id_before integer NOT NULL,"
            " event_id_after integer NOT NULL,"
            " taken_at timestamptz NOT NULL DEFAULT now(),"
            " applied_at timestamptz)"
        )
    )
    ids = [m["market_id"] for m in moves]
    await session.execute(
        text(
            f"INSERT INTO {BACKUP_TABLE} (market_id, event_id_before, event_id_after) "
            "SELECT * FROM unnest(CAST(:ids AS bigint[]), CAST(:befores AS int[]), "
            "CAST(:afters AS int[])) ON CONFLICT (market_id) DO NOTHING"
        ),
        {
            "ids": ids,
            "befores": [m["from_event_id"] for m in moves],
            "afters": [m["to_event_id"] for m in moves],
        },
    )
    await session.commit()
    banked = await session.execute(
        text(
            f"SELECT market_id, event_id_before, event_id_after FROM {BACKUP_TABLE} "
            "WHERE market_id = ANY(:ids)"
        ),
        {"ids": ids},
    )
    want = {m["market_id"]: (m["from_event_id"], m["to_event_id"]) for m in moves}
    # Count only rows banking THIS plan's pair — a bank from an earlier, different
    # plan would make the undo write the wrong event back.
    return sum(
        1 for r in banked
        if want.get(int(r.market_id)) == (int(r.event_id_before), int(r.event_id_after))
    )


async def _cas(session, triples: list[tuple[int, int, int]]) -> tuple[list, list]:
    """CAS each ``(market_id, old, new)`` in the open transaction.

    A row also misses when ``new`` was retired since the read — a link onto a
    ``merged``/``voided`` row is never written. Returns ``(landed, missed)``;
    commits nothing — the caller decides.
    """
    landed, missed = [], []
    for market_id, old, new in triples:
        result = await session.execute(
            text(
                "UPDATE futures_markets SET event_id = :new "
                "WHERE id = :id AND event_id = :old "
                "AND EXISTS (SELECT 1 FROM events WHERE id = :new "
                "AND status NOT IN ('merged', 'voided'))"
            ),
            {"id": market_id, "old": old, "new": new},
        )
        (landed if result.rowcount == 1 else missed).append((market_id, old, new))
    return landed, missed


async def _write_all_or_nothing(session, triples: list[tuple[int, int, int]]) -> dict:
    """Move every triple and mark its bank row applied, in ONE transaction.

    One missed compare-and-swap rolls the whole transaction back: an attended
    repair lands the cohort the operator reviewed or none of it, never a part.
    """
    try:
        landed, missed = await _cas(session, triples)
        if missed:
            await session.rollback()
            return {"outcome": ROLLED_BACK_CHANGED_UNDER_RUN, "landed": [],
                    "changed_under_run": sorted(t[0] for t in missed)}
        marked = await session.execute(
            text(
                f"UPDATE {BACKUP_TABLE} b SET applied_at = now() "
                "FROM unnest(CAST(:ids AS bigint[]), CAST(:befores AS int[]), "
                "CAST(:afters AS int[])) AS q(id, bef, aft) "
                "WHERE b.market_id = q.id AND b.event_id_before = q.bef "
                "AND b.event_id_after = q.aft"
            ),
            {"ids": [t[0] for t in landed], "befores": [t[1] for t in landed],
             "afters": [t[2] for t in landed]},
        )
        if marked.rowcount != len(landed):
            await session.rollback()
            return {"outcome": ROLLED_BACK_ERROR, "landed": [], "changed_under_run": [],
                    "error": f"bank marked {marked.rowcount} of {len(landed)} rows applied"}
        await session.commit()
    except Exception as exc:  # nothing has committed: the transaction is the unit
        await session.rollback()
        return {"outcome": ROLLED_BACK_ERROR, "landed": [], "changed_under_run": [],
                "error": f"{type(exc).__name__}: {exc}"}
    return {"outcome": APPLIED, "landed": landed, "changed_under_run": []}


async def _receipt(landed: list[tuple[int, int, int]], names: dict[int, tuple]) -> int:
    from app.utils.match_receipts import ACTOR_ADMIN_REPAIR, record_link_change_receipts

    groups: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for market_id, old, new in landed:
        ext, name = names.get(market_id, (None, None))
        groups[(old, new)].append(
            {"id": market_id, "source": "kalshi", "external_id": ext, "name": name}
        )
    written = 0
    for (old, new), rows in groups.items():
        written += await record_link_change_receipts(
            rows, previous_event_id=old, new_event_id=new,
            actor=ACTOR_ADMIN_REPAIR, phase=PHASE,
        )
    return written


async def run(session, *, series_list: list[str], apply: bool, max_moves: int,
              expected_digest: Optional[str] = None, boards_reader=read_boards) -> dict:
    markets = await read_markets(session, series_list)
    candidates = await read_candidates(session, markets)
    boards = await boards_reader(board_days(markets, candidates))
    plan = plan_moves(markets, candidates, boards)
    digest = plan_digest(series_list, plan.moves)
    out = {
        "mode": "apply" if apply else "dry-run",
        "outcome": DRY_RUN,
        "series": series_list,
        "plan_digest": digest,
        "counts": plan.counts(),
        "espn_days_read": len(boards),
        "espn_days_dark": sorted(d.isoformat() for d, b in boards.items() if b is None),
        "moves": plan.moves,
        "kept": plan.kept,
    }
    if not apply:
        return out
    if not plan.moves:
        out["outcome"] = NOTHING_TO_MOVE
        return out
    # Every refusal below happens before the backup, so a refused apply leaves
    # no trace at all.
    if not expected_digest:
        raise Refused(
            "--apply needs --plan-digest: run the dry run, read the plan, and pass "
            "the plan_digest it printed"
        )
    if expected_digest.strip().lower() != digest:
        raise Refused(
            f"the plan built now hashes to {digest}, not the reviewed {expected_digest}; "
            "the rows or ESPN's boards changed since the dry run — read a fresh dry run"
        )
    if len(plan.moves) > max_moves:
        raise Refused(
            f"plan moves {len(plan.moves)} markets, above the ceiling {max_moves}; "
            "read the dry run, then pass --max-moves if it is right"
        )
    planned = sorted(m["market_id"] for m in plan.moves)
    banked = await _backup(session, plan.moves)
    if banked < len(plan.moves):
        raise Refused(f"backup holds {banked} of {len(plan.moves)} moves; refusing to move")
    out["banked_ids"] = planned
    write = await _write_all_or_nothing(
        session, [(m["market_id"], m["from_event_id"], m["to_event_id"]) for m in plan.moves]
    )
    landed = write["landed"]
    out["outcome"] = write["outcome"]
    out["landed_ids"] = sorted(t[0] for t in landed)
    out["remaining_ids"] = sorted(set(planned) - set(out["landed_ids"]))
    out["changed_under_run"] = write["changed_under_run"]
    if "error" in write:
        out["error"] = write["error"]
    out["written"] = len(landed)
    if write["outcome"] != APPLIED:
        # Rolled back: nothing moved and no bank row is marked applied, so
        # --restore has nothing to undo. The bank rows stay for the record.
        out["undo"] = "nothing moved; no restore needed"
        return out
    names = {m.market_id: (m.external_id, m.name) for m in markets}
    out["receipts"] = await _receipt(landed, names)
    on_target = await _ids_on(session, landed)
    out["readback_on_target"] = len(on_target)
    out["readback_off_target_ids"] = sorted(set(out["landed_ids"]) - on_target)
    if out["readback_off_target_ids"]:
        out["outcome"] = APPLIED_READBACK_SHORT
    elif out["receipts"] < len(landed):
        out["outcome"] = APPLIED_RECEIPTS_SHORT
    out["undo"] = UNDO_LINE
    return out


async def _ids_on(session, triples: list[tuple[int, int, int]]) -> set[int]:
    """Ids read back on their ``new`` event — from disk, not rowcount (gotcha #53)."""
    if not triples:
        return set()
    got = await session.execute(
        text(
            "SELECT fm.id FROM futures_markets fm "
            "JOIN unnest(CAST(:ids AS bigint[]), CAST(:evs AS int[])) AS q(id, ev) "
            "ON fm.id = q.id AND fm.event_id = q.ev"
        ),
        {"ids": [t[0] for t in triples], "evs": [t[2] for t in triples]},
    )
    return {int(r[0]) for r in got}


async def restore(session) -> dict:
    exists = await session.execute(text("SELECT to_regclass(:t)"), {"t": BACKUP_TABLE})
    if exists.scalar() is None:
        raise Refused(f"{BACKUP_TABLE} does not exist; nothing to restore")
    rows = await session.execute(
        text(
            f"SELECT b.market_id, b.event_id_before, b.event_id_after, b.applied_at, "
            f"fm.event_id, fm.external_id, fm.name FROM {BACKUP_TABLE} b "
            "LEFT JOIN futures_markets fm ON fm.id = b.market_id ORDER BY b.market_id"
        )
    )
    rows = rows.all()
    applied = [r for r in rows if r.applied_at is not None]
    # A bank row whose apply rolled back never moved its market: undoing it
    # would move a market the repair never touched.
    never_applied = sorted(int(r.market_id) for r in rows if r.applied_at is None)
    back = [(int(r.market_id), int(r.event_id_after), int(r.event_id_before))
            for r in applied
            if r.event_id is not None and int(r.event_id) == int(r.event_id_after)]
    moved_since = sorted(int(r.market_id) for r in applied
                         if r.event_id is None or int(r.event_id) != int(r.event_id_after))
    # The undo lands what it can: a market that moved between the read and the
    # write is reported by id, not forced.
    landed, missed = await _cas(session, back)
    await session.commit()
    names = {int(r.market_id): (r.external_id, r.name) for r in rows}
    on_before = await _ids_on(session, landed)
    receipts = await _receipt(landed, names)
    short = missed or len(on_before) < len(landed) or receipts < len(landed)
    return {
        "mode": "restore",
        "outcome": RESTORE_SHORT if short else RESTORED,
        "banked": len(rows),
        "written": len(landed),
        "restored_ids": sorted(t[0] for t in landed),
        "not_on_after_left_alone": moved_since,
        "never_applied_left_alone": never_applied,
        "changed_under_restore": sorted(t[0] for t in missed),
        "receipts": receipts,
        "readback_on_before": len(on_before),
    }


#: ``--all-series`` reads the whole KXMLB range. Non-game tickers (futures,
#: date-only mention markets) carry no HHMM start and drop out at
#: ``ticker_start() is None``, so no list of game series has to be kept here.
ALL_SERIES = "KXMLB"


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--restore", action="store_true")
    which = ap.add_mutually_exclusive_group()
    which.add_argument("--series", default=DEFAULT_SERIES)
    which.add_argument("--all-series", action="store_true")
    ap.add_argument("--max-moves", type=int, default=DEFAULT_MAX_MOVES)
    ap.add_argument("--plan-digest", default=None,
                    help="with --apply: the plan_digest the reviewed dry run printed")
    ap.add_argument("--full", action="store_true", help="print every row, not a sample")
    args = ap.parse_args()
    if args.apply and not args.plan_digest:
        print("REFUSED: --apply needs --plan-digest (the plan_digest of the dry run you read)")
        return 2

    try:
        refuse_unless_production(dict(os.environ))
    except Refused as exc:
        print(f"REFUSED: {exc}")
        return 2

    from app.tasks.base import get_task_session

    series_list = [ALL_SERIES] if args.all_series else [args.series]
    async with get_task_session() as session:
        try:
            if args.restore:
                out = await restore(session)
            else:
                out = await run(session, series_list=series_list, apply=args.apply,
                                max_moves=args.max_moves,
                                expected_digest=args.plan_digest)
        except Refused as exc:
            await session.rollback()
            print(f"REFUSED: {exc}")
            return 2
    if not args.full:
        for key in ("moves", "kept"):
            if key in out and len(out[key]) > 40:
                out[f"{key}_total"] = len(out[key])
                out[f"{key}_shown"] = 40
                out[key] = out[key][:40]
        if "moves_total" in out:
            out["full_plan"] = (
                "plan_digest covers all moves_total moves; rerun with --full to read every one"
            )
    print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    if out["mode"] == "dry-run" and out["counts"].get(MOVE):
        scope = "--all-series" if args.all_series else f"--series {args.series}"
        print(
            "APPLY THIS PLAN: heroku run:detached -a bainluck -- python3 "
            f"scripts/repair_10960_mlb_markets_on_another_game.py {scope} "
            f"--apply --plan-digest {out['plan_digest']}"
        )
    if out["mode"] == "apply" and out.get("written"):
        print(f"UNDO: {UNDO_LINE}")
    return 0 if out.get("outcome", DRY_RUN) in CLEAN_OUTCOMES else 3


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
