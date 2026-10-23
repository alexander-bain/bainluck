"""#11315 — grade ONE finished DataGolf winner market from its own stored final board.

THE SHIP: the finished Baycurrent Classic chart ends on its real winner. Market
``64266833`` (``datagolf:pga:527:win``) reads ``resolved`` with none of its 155
outcomes graded, so Michael Brennan (outcome ``241857512``) is not a winner anywhere
a reader looks. This script is the grade half of that ship and ONLY the grade half:
the chart's post-decision reset at 2026-10-11T22:08:55Z is not removed by a grade
(the history half is a separate proposal; see the #11315 artifacts).

WHY NOT THE EXISTING #1152 RAILS
--------------------------------

``POST /api/admin/backfill-winners/datagolf-regrade-1152`` and
``scripts/regrade_datagolf_winners_1152.py --apply`` both call
``_backfill_datagolf_winners``, which writes across EVERY eligible resolved DataGolf
market (``--since`` bounds only that script's report, never its apply). That grader
also turns every player absent from a win/top-N board into a ``did_not_play`` loss.
Here the stored board holds 72 rows and the market 155 outcomes, so that inference
is not licensed. Neither rail is invoked or imported for its write.

What IS reused is the stored-board mechanism's own placement rule:
``_datagolf_check_placement`` is imported from the running source, and the two
``resolution_source`` labels it pairs with (``leaderboard``/``withdrew``) are the
grader's own.

WHAT IT DOES
------------

One market, pinned by id, source, external id, DataGolf event id, tour and calendar
end date. One winner, pinned by outcome id AND provider identity ``dg_29197``. The
run reads the market row and at most ``OUTCOME_READ_CAP`` of its outcomes (a read at
the cap refuses as possibly truncated), admits the stored board, and gives every
outcome exactly one verdict:

``write``                on the board, placement parses, row ungraded (NULL, NULL)
``already``              row already holds exactly the board's grade
``unknown_absent``       provider identity not on the board — NEVER graded a loss
``unknown_no_identity``  no ``dg_<digits>`` external id — never joined by name
``unknown_unparseable``  board position the placement rule cannot read
``unknown_board_unadmitted``  the stored board failed admission (the run refuses)
``conflict``             row holds a different grade or source → BLOCKS

ADMISSION — every clause a named refusal, nothing written on any
-----------------------------------------------------------------

* the market row exists, matches every pin and reads ``resolved``;
* edition: ``market_metadata.datagolf_event_id`` is the pinned event id, a stored
  ``tour`` (when present) is the pinned tour, and ``resolution_date`` falls on the
  pinned end date. The id 527 alone is not an edition witness; the date is;
* the stored board is FINAL: every placed entry is in round ``FINAL_ROUND`` with
  ``thru`` 18/F (cut/withdrawn entries exempt), positions parse, ``dg_id`` values
  are unique, exactly one entry holds position ``1`` (a ``T1`` refuses);
* the board's position-1 ``dg_id`` is the pinned winner's, and the pinned winner
  outcome exists in this market with external id ``dg_29197``. A name match never
  substitutes; a missing or different identity refuses;
* outcome external ids are unique, no outcome other than the pinned winner already
  reads ``is_winner = TRUE``, and the plan crowns exactly the pinned winner.

THE BINDING — the plan reviewed is the plan written
---------------------------------------------------

``plan_hash`` covers the market's row version, the board's sha256, every outcome's
(id, external id, grade, source, row version) and every planned write. Any write to
the market or to ANY of its outcomes after the reviewed dry run moves ``xmin`` and
the hash, and the apply refuses. Each outcome UPDATE re-states identity, the NULL
before-state and the row version. Each statement must change exactly one row,
``last_updated`` must not move (only ``is_winner`` and ``resolution_source`` are
written), and the count must equal the plan. Any refusal rolls the whole transaction
back: all writes or none.

THE ROSTER — every row admission read stays as read until COMMIT
----------------------------------------------------------------

Admission reads the WHOLE roster: "no other winner" is decided on rows the plan
never writes (``unknown_absent``, ``already``). A CAS on the written rows cannot
see a concurrent writer crown an absent player, clear an ``already`` winner, or
insert a new outcome. So the apply locks the roster, not just its targets:

* the market row ``FOR UPDATE``. A child INSERT (or an UPDATE moving an outcome
  INTO this market) runs the foreign key's check, which takes ``FOR KEY SHARE``
  on this row; ``FOR UPDATE`` is the one row lock that conflicts with it
  (``FOR SHARE``/``FOR NO KEY UPDATE`` do not), so no outcome can join the
  market until this transaction ends. It also blocks a market UPDATE/DELETE;
* every outcome read ``FOR SHARE``, taken AFTER the market lock, in id order. It
  conflicts with the ``FOR NO KEY UPDATE``/``FOR UPDATE`` that any UPDATE or
  DELETE of that row needs, so no read row can change or leave until COMMIT.
  Under READ COMMITTED a row a concurrent writer committed while we waited comes
  back as its NEW version (new ``xmin``), so the hash refuses it;
* the insert half rests on the foreign key existing. The run reads
  ``pg_constraint`` for it and an apply refuses without it
  (``roster_lock_premise``); the dry run reports it;
* immediately before COMMIT the apply re-reads the roster inside the same
  transaction and refuses unless every row is exactly the row admitted (or the
  version this run wrote) and none has joined.

A writer that wants a locked row waits for this transaction (it cannot commit
first); one already holding a lock makes this run wait at most
``LOCK_TIMEOUT_MS`` and then refuse. Locks are row locks on one market and its
outcomes; nothing table-wide, no retry.

THE UNDO — reviewable, never automatic
--------------------------------------

The apply prints every written ``OUTCOME:VERSION``. ``--restore --written ...``
returns exactly those rows to (NULL, NULL), and only while each still carries the
version the apply wrote: any later write, even one of the same values, refuses that
row. Without ``--expect-plan-hash`` the restore only plans. No backup table and no
DDL: the dry run's before-image (every row NULL, NULL) and the written versions are
the backup, so this is a data write, not notice 47(c) runtime DDL.

A COMMIT THAT DOES NOT RETURN IS UNKNOWN (exit 3) — same shape as #11234/#2169:
no rollback claim, no retry, no restore; read back with the dry run.

DELIBERATELY NOT TOUCHED
------------------------

Every other market (including this event's top-N and make-cut siblings), absent
players, ``last_updated``, prices, snapshots, history, ``status``, ``settled_at``,
metadata. The dry run's ``evidence`` block also reports the scalars the history
proposal needs (``settled_at``, ``leaderboard_updated_at``, ``round_history``) so the
same reviewed read serves both halves; it decides nothing about history.

    python3 scripts/repair_11315_datagolf_exact_market_grade.py              # dry run
    python3 scripts/repair_11315_datagolf_exact_market_grade.py --apply --expect-plan-hash H
    python3 scripts/repair_11315_datagolf_exact_market_grade.py --restore --written ID:V,...
    python3 scripts/repair_11315_datagolf_exact_market_grade.py --restore --written ID:V,... --expect-plan-hash H

Source only. Running it — even the dry run — is a separate, explicitly admitted step.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import sys
from typing import NamedTuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

PRODUCTION_APPS = frozenset({"bainluck", "bainluck-heavy"})


class MarketPin(NamedTuple):
    id: int
    source: str
    external_id: str
    event_id: str
    tour: str
    end_date: str
    market_type: str


class WinnerPin(NamedTuple):
    outcome_id: int
    external_id: str
    dg_id: str
    name: str


#: Read off the retained capture (``golfJourney.json``, sha256 1bdd575d…, captured
#: 2026-10-12T23:53:53Z) and the #11315 issue body. The pins are the whole scope.
MARKET = MarketPin(
    id=64266833,
    source="datagolf",
    external_id="datagolf:pga:527:win",
    event_id="527",
    tour="pga",
    end_date="2026-10-11",
    market_type="win",
)

#: The winner's provider identity is the join the stored board grades by. The
#: capture proves the board's ``dg_id=29197``; that outcome 241857512 carries
#: ``dg_29197`` is NOT yet admitted evidence, and the dry run is what reads it.
WINNER = WinnerPin(
    outcome_id=241857512,
    external_id="dg_29197",
    dg_id="29197",
    name="Michael Brennan",
)

#: The retained capture's market lists 155 outcomes. A read that returns this many
#: is refused as possibly truncated.
OUTCOME_READ_CAP = 156

#: A four-round stroke-play event; a board that has not finished round 4 is not final.
FINAL_ROUND = 4
FINAL_THRU = frozenset({"18", "F"})

#: ``_datagolf_check_placement``'s own non-numeric statuses (exempt from the
#: round/thru finality clause) and the subset the grader labels ``withdrew``.
CUT_STATUSES = frozenset({"CUT", "MC", "MDF", "WD", "DQ", "DNS", "W/D"})
WITHDRAWN = frozenset({"WD", "DNS", "W/D"})

_DG_EXT = re.compile(r"^dg_(\d+)$")
_POSITION = re.compile(r"^T?\d+$")

UNGRADED = (None, None)

#: Verdicts that stop the apply as a whole.
BLOCKING = frozenset({"conflict"})

#: Restore verdicts that stop the restore as a whole.
RESTORE_BLOCKING = frozenset({"missing", "moved_since_apply", "not_a_written_grade"})

#: The grades this script can have written; a restore touches nothing else.
WRITTEN_GRADES = frozenset({(True, "leaderboard"), (False, "leaderboard"), (False, "withdrew")})

LOCK_TIMEOUT_MS = 5000
STATEMENT_TIMEOUT_MS = 10000


class Refused(RuntimeError):
    """The run stops before any write is committed."""


class Unknown(RuntimeError):
    """The COMMIT was sent and never acknowledged: its writes may or may not be durable."""

    def __init__(self, report: dict):
        super().__init__(report["unknown"])
        self.report = report


def refuse_unless_production(env: dict) -> None:
    app = env.get("HEROKU_APP_NAME", "")
    if app not in PRODUCTION_APPS:
        raise Refused(
            f"HEROKU_APP_NAME={app!r} is not a production app "
            f"({sorted(PRODUCTION_APPS)}); refusing"
        )


def parse_written(raw: str) -> dict[int, str]:
    """``--written 241857512:123,...`` → {outcome id: version}."""
    out: dict[int, str] = {}
    for part in (p.strip() for p in raw.split(",")):
        if not part:
            continue
        oid, sep, version = part.partition(":")
        if not sep or not oid.strip().isdigit() or not version.strip().isdigit():
            raise Refused(f"--written entry {part!r} is not ID:VERSION")
        out[int(oid)] = version.strip()
    if not out:
        raise Refused("--written is empty")
    return out


def canonical_sha256(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _metadata(raw) -> dict:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return {}
    return raw if isinstance(raw, dict) else {}


def _day(value) -> str | None:
    if value is None:
        return None
    iso = value.isoformat() if hasattr(value, "isoformat") else str(value)
    return iso[:10]


def admit_board(board) -> tuple[dict[str, str], str | None, list[str]]:
    """The stored board → ({dg_id: position}, position-1 dg_id, refusal reasons).

    Admission only: it grades nothing. A board that is absent, malformed, carries a
    duplicate ``dg_id``, has a placed entry not finished in ``FINAL_ROUND`` or does
    not name exactly one outright position-1 entry is refused whole.
    """
    if not isinstance(board, list) or not board:
        return {}, None, ["board_missing: the market stores no leaderboard"]
    reasons: list[str] = []
    positions: dict[str, str] = {}
    unfinished: list[str] = []
    leaders: list[str] = []
    tied_leaders: list[str] = []
    for i, entry in enumerate(board):
        dg_raw = entry.get("dg_id") if isinstance(entry, dict) else None
        pos_raw = entry.get("position") if isinstance(entry, dict) else None
        dg = str(dg_raw).strip() if dg_raw is not None else ""
        pos = str(pos_raw).strip().upper() if pos_raw is not None else ""
        if not dg.isdigit() or not pos:
            reasons.append(f"board_malformed: entry {i} has dg_id={dg_raw!r} position={pos_raw!r}")
            continue
        if dg in positions:
            reasons.append(f"board_duplicate_dg_id: {dg}")
            continue
        positions[dg] = pos
        if pos in CUT_STATUSES:
            continue
        if not _POSITION.match(pos):
            reasons.append(f"board_malformed: dg_id {dg} position {pos_raw!r}")
            continue
        thru = str(entry.get("thru")).strip().upper()
        if entry.get("current_round") != FINAL_ROUND or thru not in FINAL_THRU:
            unfinished.append(dg)
        if pos == "1":
            leaders.append(dg)
        elif pos == "T1":
            tied_leaders.append(dg)
    if unfinished:
        reasons.append(
            f"board_not_final: {len(unfinished)} placed entries not finished in round "
            f"{FINAL_ROUND} (first: {unfinished[:5]})"
        )
    if len(leaders) != 1 or tied_leaders:
        reasons.append(
            f"winner_not_unique: position '1' held by {leaders}, 'T1' by {tied_leaders}"
        )
    return positions, (leaders[0] if len(leaders) == 1 and not tied_leaders else None), reasons


def plan_hash(mode: str, market_version, board_sha: str, rows: list, writes: list) -> str:
    """The identity of what this run would write, and of every row it read."""
    return canonical_sha256(
        {
            "mode": mode,
            "market": [MARKET.id, market_version],
            "board": board_sha,
            "rows": sorted(
                [r["id"], r["external_id"], r["is_winner"], r["resolution_source"], r["row_version"]]
                for r in rows
            ),
            "write": sorted([w["id"], w["to"][0], w["to"][1], w["version"]] for w in writes),
        }
    )[:16]


def _market_reasons(market: dict, md: dict) -> list[str]:
    reasons = [
        f"foreign: {field}={market.get(field)!r} (pinned {expected!r})"
        for field, expected in (
            ("source", MARKET.source),
            ("external_id", MARKET.external_id),
        )
        if market.get(field) != expected
    ]
    if market.get("status") != "resolved":
        reasons.append(f"status: market reads {market.get('status')!r}, not 'resolved'")
    if str(md.get("datagolf_event_id")) != MARKET.event_id:
        reasons.append(
            f"edition: datagolf_event_id={md.get('datagolf_event_id')!r} "
            f"(pinned {MARKET.event_id!r})"
        )
    if md.get("tour") is not None and md.get("tour") != MARKET.tour:
        reasons.append(f"edition: tour={md.get('tour')!r} (pinned {MARKET.tour!r})")
    if _day(market.get("resolution_date")) != MARKET.end_date:
        reasons.append(
            f"edition: resolution_date={market.get('resolution_date')!r} "
            f"(pinned end date {MARKET.end_date})"
        )
    return reasons


def plan(market: dict | None, outcomes: list[dict], placement) -> dict:
    """Decide every outcome's verdict and the writes. Pure: reads nothing, writes nothing."""
    if market is None:
        return {
            "mode": "apply",
            "admissible": False,
            "refusal_reasons": [f"missing: no futures_markets row {MARKET.id}"],
            "accounting": {},
            "write": [],
            "plan_hash": None,
        }
    md = _metadata(market.get("market_metadata"))
    reasons = _market_reasons(market, md)
    board = md.get("leaderboard")
    positions, leader, board_reasons = admit_board(board)
    reasons += board_reasons
    if leader is not None and leader != WINNER.dg_id:
        reasons.append(f"winner_mismatch: board position 1 is dg_id {leader}, pinned {WINNER.dg_id}")
    if len(outcomes) >= OUTCOME_READ_CAP:
        reasons.append(f"outcome read reached its cap ({OUTCOME_READ_CAP}); not a whole-market read")

    by_ext: dict[str, list[int]] = {}
    for o in outcomes:
        if o.get("external_id"):
            by_ext.setdefault(o["external_id"], []).append(o["id"])
    dupes = sorted(ext for ext, ids in by_ext.items() if len(ids) > 1)
    if dupes:
        reasons.append(f"duplicate_outcome_identity: {dupes[:5]}")
    winner_row = next((o for o in outcomes if o["id"] == WINNER.outcome_id), None)
    if winner_row is None:
        reasons.append(f"winner_outcome_missing: outcome {WINNER.outcome_id} is not in market {MARKET.id}")
    elif winner_row.get("external_id") != WINNER.external_id:
        reasons.append(
            f"winner_identity: outcome {WINNER.outcome_id} external_id="
            f"{winner_row.get('external_id')!r} (pinned {WINNER.external_id!r}); a name "
            "match does not substitute"
        )
    crowned = sorted(
        o["id"] for o in outcomes if o.get("is_winner") is True and o["id"] != WINNER.outcome_id
    )
    if crowned:
        reasons.append(f"conflicting_winner: outcomes {crowned} already read is_winner=TRUE")

    accounting: dict[str, list[int]] = {}
    writes: list[dict] = []
    crowns: list[int] = []
    board_ok = not board_reasons
    for o in sorted(outcomes, key=lambda r: r["id"]):
        current = (o.get("is_winner"), o.get("resolution_source"))
        m = _DG_EXT.match(o.get("external_id") or "")
        target = None
        if m is None:
            verdict = "unknown_no_identity"
        elif not board_ok:
            verdict = "unknown_board_unadmitted"
        elif m.group(1) not in positions:
            verdict = "unknown_absent"
        else:
            pos = positions[m.group(1)]
            won = placement(pos, MARKET.market_type)
            if won is None:
                verdict = "unknown_unparseable"
            else:
                target = (won, "withdrew" if pos in WITHDRAWN else "leaderboard")
                if current == target:
                    verdict = "already"
                elif current == UNGRADED:
                    verdict = "write"
                    writes.append(
                        {
                            "id": o["id"],
                            "external_id": o["external_id"],
                            "position": pos,
                            "from": list(UNGRADED),
                            "to": list(target),
                            "version": o["row_version"],
                            "last_updated": o.get("last_updated"),
                        }
                    )
                else:
                    verdict = "conflict"
        if target is not None and target[0] is True and verdict in ("write", "already"):
            crowns.append(o["id"])
        accounting.setdefault(verdict, []).append(o["id"])

    blocking = {v: ids for v, ids in accounting.items() if v in BLOCKING}
    if blocking:
        reasons.append(f"blocking verdicts: {blocking}")
    if not reasons and crowns != [WINNER.outcome_id]:
        reasons.append(f"winner_plan: the plan crowns {crowns}, pinned [{WINNER.outcome_id}]")

    board_sha = canonical_sha256(board) if board is not None else None
    round_history = md.get("round_history")
    return {
        "mode": "apply",
        "market_id": MARKET.id,
        "evidence": {
            "market_version": market.get("row_version"),
            "status": market.get("status"),
            "resolution_date": market.get("resolution_date"),
            "settled_at": market.get("settled_at"),
            "datagolf_event_id": md.get("datagolf_event_id"),
            "tour": md.get("tour"),
            "leaderboard_sha256": board_sha,
            "leaderboard_size": len(board) if isinstance(board, list) else None,
            "leaderboard_updated_at": md.get("leaderboard_updated_at"),
            "round_history": round_history[:10] if isinstance(round_history, list) else None,
            "board_position_1_dg_id": leader,
            "winner_external_id": winner_row.get("external_id") if winner_row else None,
            "outcomes_read": len(outcomes),
        },
        "accounting": accounting,
        "counts": {v: len(ids) for v, ids in sorted(accounting.items())},
        "write": writes,
        "admissible": not reasons,
        "refusal_reasons": reasons,
        "plan_hash": plan_hash(
            "apply", market.get("row_version"), board_sha, outcomes, writes
        ),
    }


def plan_restore(market: dict | None, outcomes: list[dict], written: dict[int, str]) -> dict:
    """The inverse: every named row back to (NULL, NULL), only at the version written."""
    reasons: list[str] = []
    if market is None:
        reasons.append(f"missing: no futures_markets row {MARKET.id}")
    else:
        reasons += [
            f"foreign: {field}={market.get(field)!r} (pinned {expected!r})"
            for field, expected in (("source", MARKET.source), ("external_id", MARKET.external_id))
            if market.get(field) != expected
        ]
    rows = {o["id"]: o for o in outcomes}
    accounting: dict[str, list[int]] = {}
    writes: list[dict] = []
    for oid, version in sorted(written.items()):
        row = rows.get(oid)
        current = (row.get("is_winner"), row.get("resolution_source")) if row else None
        if row is None:
            verdict = "missing"
        elif row["row_version"] != version:
            verdict = "moved_since_apply"
        elif current not in WRITTEN_GRADES:
            verdict = "not_a_written_grade"
        else:
            verdict = "write"
            writes.append(
                {
                    "id": oid,
                    "external_id": row.get("external_id"),
                    "from": list(current),
                    "to": list(UNGRADED),
                    "version": version,
                    "last_updated": row.get("last_updated"),
                }
            )
        accounting.setdefault(verdict, []).append(oid)
    blocking = {v: ids for v, ids in accounting.items() if v in RESTORE_BLOCKING}
    if blocking:
        reasons.append(f"blocking verdicts: {blocking}")
    return {
        "mode": "restore",
        "market_id": MARKET.id,
        "accounting": accounting,
        "counts": {v: len(ids) for v, ids in sorted(accounting.items())},
        "write": writes,
        "admissible": not reasons,
        "refusal_reasons": reasons,
        "plan_hash": plan_hash(
            "restore",
            market.get("row_version") if market else None,
            "",
            [o for o in outcomes if o["id"] in written],
            writes,
        ),
    }


_READ_MARKET_SQL = (
    "SELECT id, source, external_id, status, resolution_date, settled_at, "
    "market_metadata, xmin::text AS row_version FROM futures_markets WHERE id = :id"
)

_READ_OUTCOMES_SQL = (
    "SELECT id, external_id, is_winner, resolution_source, last_updated, "
    "xmin::text AS row_version FROM futures_outcomes "
    "WHERE market_id = :mid ORDER BY id LIMIT :cap"
)

# The roster locks (see THE ROSTER above). Only a write run takes them; the dry run
# locks nothing. The market lock must be FOR UPDATE: it is the only row lock that
# conflicts with the FOR KEY SHARE a child INSERT's foreign-key check takes.
_MARKET_LOCK = " FOR UPDATE"
_ROSTER_LOCK = " FOR SHARE"

# The insert half of the roster lock exists only if this foreign key does.
_OUTCOME_MARKET_FK_SQL = (
    "SELECT count(*) AS n FROM pg_constraint c "
    "JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey) "
    "WHERE c.contype = 'f' "
    "AND c.conrelid = 'futures_outcomes'::regclass "
    "AND c.confrelid = 'futures_markets'::regclass "
    "AND array_length(c.conkey, 1) = 1 AND a.attname = 'market_id'"
)

# Everything the plan decided on, re-stated: identity, before-state and row version.
# `xmin` moves on ANY update of the row, including one that writes the same values,
# so a writer landing between this run's read and its UPDATE matches zero rows.
# Only the two grade columns are SET; `last_updated` is returned to prove it stayed.
_CAS_SQL = (
    "UPDATE futures_outcomes SET is_winner = :to_won, resolution_source = :to_src "
    "WHERE id = :id AND market_id = :mid AND external_id IS NOT DISTINCT FROM :ext "
    "AND is_winner IS NOT DISTINCT FROM :from_won "
    "AND resolution_source IS NOT DISTINCT FROM :from_src "
    "AND xmin::text = :version "
    "RETURNING xmin::text AS row_version, last_updated"
)


async def _read(session, *, lock: bool) -> tuple[dict | None, list[dict]]:
    # Market first: once it is held no outcome can join, so the outcome read (a
    # fresh READ COMMITTED snapshot) sees every row that will exist before COMMIT.
    sql = _READ_MARKET_SQL + (_MARKET_LOCK if lock else "")
    got = [dict(r._mapping) for r in await session.execute(text(sql), {"id": MARKET.id})]
    return (got[0] if got else None), await _read_outcomes(session, lock=lock)


async def _read_outcomes(session, *, lock: bool) -> list[dict]:
    sql = _READ_OUTCOMES_SQL + (_ROSTER_LOCK if lock else "")
    outcomes = await session.execute(text(sql), {"mid": MARKET.id, "cap": OUTCOME_READ_CAP})
    return [dict(r._mapping) for r in outcomes]


async def _roster_lock_premise(session) -> bool:
    got = [dict(r._mapping) for r in await session.execute(text(_OUTCOME_MARKET_FK_SQL), {})]
    return bool(got) and got[0].get("n", 0) >= 1


def _roster_drift(admitted: list[dict], returned: dict[int, str], now: list[dict]) -> list[str]:
    """What moved between admission and COMMIT, read inside this transaction.

    Every admitted row must still be there at the version read (or, for a row this
    run wrote, the version its UPDATE returned) and no row may have joined. That is
    the whole check: a row at its admitted ``xmin`` holds its admitted grade, and
    admission already refused any winner but the pinned one.
    """
    expected = {o["id"]: returned.get(o["id"], o["row_version"]) for o in admitted}
    seen = {o["id"]: o["row_version"] for o in now}
    reasons = []
    joined = sorted(set(seen) - set(expected))
    left = sorted(set(expected) - set(seen))
    moved = sorted(i for i in set(seen) & set(expected) if seen[i] != expected[i])
    if joined:
        reasons.append(f"outcomes {joined[:5]} joined the market")
    if left:
        reasons.append(f"outcomes {left[:5]} left the market")
    if moved:
        reasons.append(f"outcomes {moved[:5]} changed")
    return reasons


def _unknown_report(decided: dict, returned: dict, written: int, exc: BaseException) -> dict:
    orig = getattr(exc, "orig", None)
    code = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    return {
        "outcome": "UNKNOWN",
        "mode": decided["mode"],
        "plan_hash": decided["plan_hash"],
        "write": decided["write"],
        "returned_versions": returned,
        "statements_changed": written,
        "unknown": (
            f"the {decided['mode']} COMMIT was sent and not acknowledged "
            f"({type(orig or exc).__name__}, sqlstate {code}); these writes may or may "
            "not be durable. Not retried, not restored — read the market back with the "
            "dry run and an independent read before any further step"
        ),
    }


async def run(
    session,
    placement,
    *,
    execute: bool,
    expect_plan_hash: str | None = None,
    written: dict[int, str] | None = None,
) -> dict:
    """Read, decide, and — when ``execute`` — write the plan in this transaction."""
    premise = await _roster_lock_premise(session)
    # Only the apply decides on the whole roster; a restore's inverse CAS is per row.
    if execute and written is None and not premise:
        raise Refused(
            "roster_lock_premise: no foreign key futures_outcomes(market_id) → "
            "futures_markets(id), so the market lock cannot keep an outcome from "
            "joining mid-run"
        )
    market, outcomes = await _read(session, lock=execute)
    if written is not None:
        decided = plan_restore(market, outcomes, written)
    else:
        decided = plan(market, outcomes, placement)
    returned: dict[int, str] = {}
    count = 0
    if execute:
        if expect_plan_hash != decided["plan_hash"]:
            raise Refused(
                f"plan hash is {decided['plan_hash']}, expected {expect_plan_hash!r} — "
                "the market or its outcomes moved since the reviewed dry run; re-read"
            )
        if not decided["admissible"]:
            raise Refused("; ".join(decided["refusal_reasons"]))
        for w in decided["write"]:
            result = await session.execute(
                text(_CAS_SQL),
                {
                    "id": w["id"],
                    "mid": MARKET.id,
                    "ext": w["external_id"],
                    "from_won": w["from"][0],
                    "from_src": w["from"][1],
                    "to_won": w["to"][0],
                    "to_src": w["to"][1],
                    "version": w["version"],
                },
            )
            got = list(result)
            if len(got) != 1:
                raise Refused(
                    f"outcome {w['id']}: expected to change 1 row, changed {len(got)} — "
                    "its identity, grade or version moved since the read"
                )
            if got[0].last_updated != w["last_updated"]:
                raise Refused(
                    f"outcome {w['id']}: last_updated moved ({w['last_updated']} → "
                    f"{got[0].last_updated}); this write must leave it alone"
                )
            returned[w["id"]] = got[0].row_version
            count += 1
        if count != len(decided["write"]):
            raise Refused(f"changed {count} rows, the plan holds {len(decided['write'])}")
        if count and written is None:
            # The locks are the guarantee; this is the same transaction checking it
            # held, so a missing lock refuses instead of committing a second winner.
            drift = _roster_drift(outcomes, returned, await _read_outcomes(session, lock=False))
            if drift:
                raise Refused("roster moved inside the transaction: " + "; ".join(drift))
        if count:
            try:
                await session.commit()
            except Exception as exc:
                raise Unknown(_unknown_report(decided, returned, count, exc)) from exc
            except BaseException as exc:
                exc.commit_unknown = _unknown_report(decided, returned, count, exc)
                raise
    out = dict(
        decided,
        executed=execute,
        written=count,
        written_versions=returned,
        roster_lock_premise=premise,
    )
    if not execute:
        out["mode"] = f"{decided['mode']}-plan"
    return out


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--apply", action="store_true")
    group.add_argument("--restore", action="store_true")
    ap.add_argument("--expect-plan-hash", default=None)
    ap.add_argument(
        "--written", default=None, help="restore only: OUTCOME:VERSION pairs the apply printed"
    )
    args = ap.parse_args()

    try:
        refuse_unless_production(dict(os.environ))
        if args.apply and not args.expect_plan_hash:
            raise Refused("--apply needs --expect-plan-hash (printed by the dry run)")
        if args.restore and not args.written:
            raise Refused("--restore needs --written (printed by the apply)")
        if args.written and not args.restore:
            raise Refused("--written is for --restore only")
        if args.expect_plan_hash and not (args.apply or args.restore):
            raise Refused("--expect-plan-hash without --apply or --restore")
        written = parse_written(args.written) if args.restore else None
    except Refused as exc:
        print(f"REFUSED: {exc}")
        return 2

    import importlib

    from sqlalchemy.exc import DBAPIError

    from app.tasks.base import get_task_session

    # `from app.tasks import backfill_winners` yields the registered Celery TASK.
    placement = importlib.import_module("app.tasks.backfill_winners")._datagolf_check_placement

    execute = bool(args.apply or (args.restore and args.expect_plan_hash))
    readback = (
        f"heroku run:detached -a {os.environ['HEROKU_APP_NAME']} -- "
        "python3 scripts/repair_11315_datagolf_exact_market_grade.py"
    )
    # After an unacknowledged COMMIT the session must leave ``get_task_session`` by
    # its EXCEPTION path: its normal exit COMMITs again. Same shape as #11234's.
    unknown: dict | None = None
    carried: BaseException | None = None
    try:
        async with get_task_session(
            statement_timeout_ms=STATEMENT_TIMEOUT_MS, lock_timeout_ms=LOCK_TIMEOUT_MS
        ) as session:
            try:
                out = await run(
                    session,
                    placement,
                    execute=execute,
                    expect_plan_hash=args.expect_plan_hash,
                    written=written,
                )
                if not execute:
                    await session.rollback()
            except Refused as exc:
                await session.rollback()
                print(f"REFUSED: {exc}; rolled back, nothing committed")
                return 2
            except DBAPIError as exc:
                await session.rollback()
                code = getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None)
                print(
                    f"REFUSED: the database stopped the run ({type(exc.orig).__name__}, "
                    f"sqlstate {code}); rolled back, nothing committed"
                )
                return 2
            except BaseException as exc:
                report = (
                    exc.report if isinstance(exc, Unknown) else getattr(exc, "commit_unknown", None)
                )
                if report is not None:
                    unknown, carried = dict(report, readback=readback), exc
                    print(json.dumps(unknown, indent=2, default=str))
                raise
    except BaseException as exc:
        if unknown is None:
            raise
        if exc is not carried:
            print(
                f"note: the session's cleanup after the UNKNOWN report raised "
                f"{type(exc).__name__}; it proves nothing about the COMMIT above",
                file=sys.stderr,
            )
        if isinstance(carried, Unknown):
            if not isinstance(exc, Exception):
                raise
            return 3
        if exc is carried:
            raise
        raise carried
    print(json.dumps(out, indent=2, default=str))
    if out["mode"] == "apply" and out["written"]:
        pairs = ",".join(f"{i}:{v}" for i, v in sorted(out["written_versions"].items()))
        print(
            "UNDO (reviewed plan first, never automatic): heroku run:detached -a "
            f"{os.environ['HEROKU_APP_NAME']} -- python3 "
            "scripts/repair_11315_datagolf_exact_market_grade.py "
            f"--restore --written {pairs}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
