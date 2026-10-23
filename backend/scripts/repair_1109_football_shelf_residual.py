"""#1109 — non-football Kalshi markets already stored as football move to their own sport.

PILLAR: TRUTH. SHIP: tennis and basketball questions that a generic football name
rule (or the retired calendar guess) once labelled football stop appearing on the
Football shelf, and stay off it after Kalshi re-ingest.

WHY THESE ROWS STAY WRONG WITHOUT A WRITE
-----------------------------------------

The writer half is fixed: ITF tickers map to tennis (65b0797a), the calendar guess
is gone (#1888), and a generic football-only phrase on an unmapped ticker is no
longer an answer (7a32d83267). None of that moves a stored row. The Kalshi upsert
writes the tag through ``coalesce(nullif(llm_sport_category, 'other'), new)``, so a
real tag, wrong or not, is never overwritten — and that same rail is what makes this
repair durable: once a row reads ``tennis``, no poll puts ``football`` back.

Neither sibling rail reaches the residual. ``repair_kalshi_series_tag_category``
writes nothing for a MAPPED ticker (gate 2), which is every ITF row; the old
``fix_misclassified_*`` scripts re-select their population at run time and write
without a plan, a compare-and-set or a row-version check.

THE POPULATION — a reviewed artifact, not a query
-------------------------------------------------

The August census (24,265 ITF rows across four shelves) is two months stale and was
never an apply plan. This script does not census. It applies an exact-id ARTIFACT
produced by a fresh read in the measurement lane, after ``bainluck-heavy`` carries
the writer guard (notice 48 — before that, the poll can still mint new rows):

    {"schema": "kalshi-football-shelf-residual-plan/v1", "issue": 1109,
     "rows": [{"id": 123, "external_id": "KXITFMATCH-26JUL19VELKIM",
               "name": "Velcz vs Kimhi", "before": "football", "after": "tennis",
               "row_updated_at": "2026-07-19T14:02:11.123456+00:00",
               "venue": {"series_ticker": "KXITFMATCH", "resolved": true,
                         "tags": ["Tennis"], "series_category": "Sports",
                         "event_category": "Sports",
                         "read_at": "2026-10-14T03:00:00+00:00"}}]}

``name``, ``before`` and ``row_updated_at`` are the row exactly as the read saw it.
``venue`` is Kalshi's own ``/series/{series_ticker}`` answer for that row, read at
``read_at``.

THE ARTIFACT GATES — any failure refuses the whole run, nothing is written
--------------------------------------------------------------------------

An artifact whose own evidence does not support its own target is not a plan with one
bad row. It is a plan nobody can trust:

* schema/issue mismatch, no rows, more than ``MAX_ROWS``, a repeated id, a missing or
  mistyped field;
* ``before`` is not ``football`` — this rail moves rows OFF the Football shelf and
  nowhere else (it also makes the rail disjoint from #2169's pinned rows, none of
  which start on football);
* ``after`` is ``football``, ``other``, or not a sport the maps know. ``other`` is
  the honest blank a later poll may upgrade, but writing it is a claim that we know
  the row is not football without knowing what it is, and that is the ambiguous
  ``KXNDJOINCONF`` shape the issue deliberately left alone;
* ``series_ticker`` is not the series of ``external_id`` — the venue answer belongs
  to another market;
* ``venue.resolved`` is false — a 429/5xx is not an answer (#36, CERT-2737);
* the venue read is older than ``MAX_EVIDENCE_AGE`` or in the future;
* the target rests on the NAME alone. The only evidence accepted is structural: the
  ticker map (``get_sport_key_from_ticker``, step 1 of the cascade) or the sport tag
  the venue publishes (step 1b). A league word, a venue category or a name rule is a
  candidate, not evidence (notice 40);
* the ticker map and the venue's sport tag name DIFFERENT sports;
* the SHIPPED cascade, given the artifact's name and venue evidence, does not answer
  ``after``. This rail carries no sport vocabulary of its own: it asks the writer, so
  the writer and the repair cannot disagree about a row and the next poll agrees with
  what this wrote.

THE ROW GATES — a row that moved since the read retires alone, never written
----------------------------------------------------------------------------

The pipeline touching a row between the read and the run is the system working, not
a fault (``CONCURRENT_ROW_DRIFT`` in ``repair_apply_plan``), so these skip one row and
the dry run names it: row missing; not a Kalshi row or its ``external_id`` changed;
already holds ``after`` (idempotent repeat); holds neither ``before`` nor ``after``;
name changed; ``updated_at`` changed (the row version — an open row the poller
touched retires and waits for a fresh read).

THE WRITE
---------

One transaction, one compare-and-set per row. The UPDATE re-states every value the
plan decided on — id, source, external_id, category, name (null-safe) and
``updated_at`` — so a writer landing between the read and the write makes it change
zero rows and the whole run rolls back. ``llm_sport_category`` is the only column
set; ``updated_at`` is left alone (the ORM ``onupdate`` does not fire for Core SQL),
as are ``canonical_market_key`` (#2163's), ``llm_league`` and ``category_tags``.
The run carries its own short lock and statement budgets.

``--apply`` needs ``--expect-plan-hash``: the hash of the artifact's content AND the
writes this run decided, printed by the dry run. A different artifact, an edited one,
or a population that moved since the dry run is a different hash, and the apply
refuses.

BACKUP, UNDO AND READBACK
-------------------------

**No backup table, by proof** (``repair_2169_misfiled_sport_category``'s argument):
every write is a compare-and-set from the artifact's ``before``, so a changed row held
exactly that value a moment earlier, and the artifact restores it. Keep the artifact.

* ``--restore --ids …`` is the inverse compare-and-set (``after`` back to
  ``before``) over exactly the ids the apply printed. It checks neither freshness nor
  ``updated_at``: an undo must still work days later and after a poll.
* ``--readback`` reads every artifact row and reports which hold ``after``, which
  still hold ``before``, which hold something else and which are missing. Read-only.

A COMMIT THAT DOES NOT RETURN IS UNKNOWN (exit 3)
-------------------------------------------------

The server can make the COMMIT durable and its acknowledgement still be lost
(SQLSTATE 08006), and a rollback sent afterwards proves nothing about it. So once
an apply or restore COMMIT has been sent and not acknowledged, the run prints
``"outcome": "UNKNOWN"`` with its mode, artifact, plan hash and the exact writes
the transaction carried, plus the ``--readback`` command, and stops: no rollback
claim, no retry, no undo line. The readback answers it without a write. A cancel
or interrupt that lands on the COMMIT prints the same report and keeps
propagating as itself.

Only a refusal BEFORE the COMMIT was sent (a gate, a moved row, a budget firing)
says "nothing committed", and it says it before anything rolls back, so a
rollback failing on a dead connection never replaces it or its exit 2. After an
UNKNOWN the session leaves ``get_task_session`` by its exception path, so the
wrapper's normal-exit COMMIT is never sent behind the unacknowledged one. A
failure in the wrapper's cleanup — after a refusal, an UNKNOWN, or an
acknowledged COMMIT — is noted on stderr and changes neither the printed result,
its undo line nor its exit; an interrupt there still propagates as itself.

The dry run also prints ``movement`` — the per-shelf counts the apply would move
(``football->tennis: n``). These are graded cohorts (ruling 060): the after-check
reads both curves against that declared movement.

    python3 scripts/repair_1109_football_shelf_residual.py --plan - < plan.json                 # dry run
    python3 scripts/repair_1109_football_shelf_residual.py --plan - --apply --expect-plan-hash H < plan.json
    python3 scripts/repair_1109_football_shelf_residual.py --plan - --readback < plan.json
    python3 scripts/repair_1109_football_shelf_residual.py --plan - --restore --ids 1,2 < plan.json
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

PRODUCTION_APPS = frozenset({"bainluck", "bainluck-heavy"})

SCHEMA = "kalshi-football-shelf-residual-plan/v1"
ISSUE = 1109
BEFORE = "football"
#: One attended transaction stays short; a larger residual is several artifacts.
MAX_ROWS = 500
#: The venue's answer and the row's version must be this fresh at run time.
MAX_EVIDENCE_AGE = timedelta(hours=24)
#: Clock skew between the measurement host and the dyno.
FUTURE_SKEW = timedelta(minutes=5)

LOCK_TIMEOUT_MS = 5000
STATEMENT_TIMEOUT_MS = 10000

_ROW_FIELDS = {
    "id": int,
    "external_id": str,
    "before": str,
    "after": str,
    "row_updated_at": str,
    "venue": dict,
}
_VENUE_FIELDS = {"series_ticker": str, "resolved": bool, "tags": list, "read_at": str}


class Refused(RuntimeError):
    """The run stops before any write."""


class Unknown(RuntimeError):
    """The COMMIT was sent and never acknowledged: its writes may or may not be durable."""

    def __init__(self, report: dict):
        super().__init__(report["unknown"])
        self.report = report


def _unknown_report(decided: dict, mode: str, written: int, exc: BaseException) -> dict:
    orig = getattr(exc, "orig", None)
    code = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    return {
        "outcome": "UNKNOWN",
        "mode": mode,
        "artifact": decided["artifact"],
        "plan_hash": decided["plan_hash"],
        "write": decided["write"],
        "statements_changed": written,
        "unknown": (
            f"the {mode} COMMIT was sent and not acknowledged "
            f"({type(orig or exc).__name__}, sqlstate {code}); these writes may or may "
            "not be durable. Not retried, not undone — read the artifact rows back "
            "with --readback before any further step"
        ),
    }


def refuse_unless_production(env: dict) -> None:
    app = env.get("HEROKU_APP_NAME", "")
    if app not in PRODUCTION_APPS:
        raise Refused(
            f"HEROKU_APP_NAME={app!r} is not a production app "
            f"({sorted(PRODUCTION_APPS)}); refusing"
        )


def _instant(value: str, where: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise Refused(f"{where}: {value!r} is not an ISO-8601 instant")
    if parsed.tzinfo is None:
        raise Refused(f"{where}: {value!r} carries no UTC offset")
    return parsed


def _canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def artifact_address(artifact: dict) -> str:
    """The content address of the artifact: every field of every row, order-free."""
    rows = sorted(artifact["rows"], key=lambda r: r["id"])
    body = {"schema": artifact["schema"], "issue": artifact["issue"], "rows": rows}
    return hashlib.sha256(_canonical(body)).hexdigest()


def plan_hash(address: str, writes: list[tuple[int, str, str]]) -> str:
    """What the apply must be told: this artifact AND exactly these writes."""
    canon = _canonical(
        {"artifact": address, "write": sorted([int(i), f, t] for i, f, t in writes)}
    )
    return hashlib.sha256(canon).hexdigest()[:16]


def structural_evidence(external_id: str, tags: list) -> tuple[str | None, str | None]:
    """(category the ticker map names, category the venue's sport tag names)."""
    from app.tasks.kalshi import _pick_series_tag, series_tag_to_category
    from app.utils.sport_keys import (
        SPORT_PREFIX_TO_LLM_CATEGORY,
        get_sport_key_from_ticker,
    )

    sport_key = get_sport_key_from_ticker(external_id)
    ticker_cat = (
        SPORT_PREFIX_TO_LLM_CATEGORY.get(sport_key.split("_")[0]) if sport_key else None
    )
    return ticker_cat, series_tag_to_category(_pick_series_tag(tags))


def validate_artifact(
    raw, *, now: datetime | None, evidence: bool = True
) -> list[dict]:
    """The artifact gates. Pure. Raises :class:`Refused`; returns the rows.

    ``evidence=False`` (restore, readback) keeps the shape gates and drops the
    freshness and evidence gates: an undo must work whatever the clock or the
    deployed maps say now.
    """
    from app.services.kalshi_api import event_series_ticker
    from app.tasks.kalshi import _categorize_kalshi_market, _pick_series_tag
    from app.utils.sport_keys import SPORT_PREFIX_TO_LLM_CATEGORY

    if not isinstance(raw, dict) or raw.get("schema") != SCHEMA:
        raise Refused(f"artifact schema is not {SCHEMA!r}")
    if raw.get("issue") != ISSUE:
        raise Refused(f"artifact is for issue {raw.get('issue')!r}, not {ISSUE}")
    rows = raw.get("rows")
    if not isinstance(rows, list) or not rows:
        raise Refused("artifact has no rows")
    if len(rows) > MAX_ROWS:
        raise Refused(f"artifact has {len(rows)} rows; the bound is {MAX_ROWS}")

    sports = set(SPORT_PREFIX_TO_LLM_CATEGORY.values()) - {BEFORE}
    seen: set[int] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise Refused("artifact row is not an object")
        for key, kind in _ROW_FIELDS.items():
            # bool is an int; an id of `true` is not an id.
            if not isinstance(row.get(key), kind) or isinstance(row.get(key), bool):
                raise Refused(
                    f"row {row.get('id')!r}: {key} missing or not {kind.__name__}"
                )
        if "name" not in row or not (
            row["name"] is None or isinstance(row["name"], str)
        ):
            raise Refused(f"row {row['id']}: name missing or not a string/null")
        venue = row["venue"]
        for key, kind in _VENUE_FIELDS.items():
            if not isinstance(venue.get(key), kind):
                raise Refused(
                    f"row {row['id']}: venue.{key} missing or not {kind.__name__}"
                )
        if not all(isinstance(tag, str) for tag in venue["tags"]):
            raise Refused(f"row {row['id']}: venue.tags holds a non-string")
        for key in ("series_category", "event_category"):
            if not (venue.get(key) is None or isinstance(venue.get(key), str)):
                raise Refused(f"row {row['id']}: venue.{key} not a string/null")
        market_id = row["id"]
        if market_id in seen:
            raise Refused(f"row {market_id} appears twice")
        seen.add(market_id)
        if row["before"] != BEFORE:
            raise Refused(
                f"row {market_id}: before is {row['before']!r}; this rail moves rows "
                f"off {BEFORE!r} only"
            )
        if row["after"] not in sports:
            raise Refused(
                f"row {market_id}: after {row['after']!r} is not a non-football sport"
            )
        _instant(row["row_updated_at"], f"row {market_id} row_updated_at")
        read_at = _instant(venue["read_at"], f"row {market_id} venue.read_at")
        if venue["series_ticker"] != event_series_ticker(row["external_id"]):
            raise Refused(
                f"row {market_id}: venue series {venue['series_ticker']!r} is not the "
                f"series of {row['external_id']!r}"
            )
        if not evidence:
            continue

        if now is not None:
            if read_at < now - MAX_EVIDENCE_AGE:
                raise Refused(
                    f"row {market_id}: venue read {venue['read_at']} is older than "
                    f"{MAX_EVIDENCE_AGE}; re-read before applying"
                )
            if read_at > now + FUTURE_SKEW:
                raise Refused(
                    f"row {market_id}: venue read {venue['read_at']} is in the future"
                )
        if not venue["resolved"]:
            raise Refused(f"row {market_id}: the venue did not answer; not evidence")
        ticker_cat, tag_cat = structural_evidence(row["external_id"], venue["tags"])
        if ticker_cat and tag_cat and ticker_cat != tag_cat:
            raise Refused(
                f"row {market_id}: the ticker map says {ticker_cat!r} and the venue's "
                f"tag says {tag_cat!r}"
            )
        if row["after"] not in (ticker_cat, tag_cat):
            raise Refused(
                f"row {market_id}: neither the ticker map ({ticker_cat!r}) nor the "
                f"venue's sport tag ({tag_cat!r}) names {row['after']!r}; a name is "
                "not evidence"
            )
        answer = _categorize_kalshi_market(
            row["name"] or "",
            venue.get("event_category"),
            row["external_id"],
            series_tag=_pick_series_tag(venue["tags"]),
            series_category=venue.get("series_category"),
        )
        if answer != row["after"]:
            raise Refused(
                f"row {market_id}: the shipped cascade answers {answer!r} on this "
                f"evidence, not {row['after']!r}"
            )
    return rows


def plan(
    rows: list[dict],
    live: dict[int, tuple],
    address: str,
    *,
    restore_ids: frozenset[int] | None = None,
) -> dict:
    """The row gates. Pure.

    ``live`` maps each id that EXISTS to ``(source, external_id,
    llm_sport_category, name, updated_at)``. ``restore_ids`` set ⇒ undo mode over
    exactly those ids, gated on identity and category only.
    """
    restore = restore_ids is not None
    by_id = {r["id"]: r for r in rows}
    write, skip = [], []
    for market_id in sorted(restore_ids) if restore else sorted(by_id):
        row = by_id[market_id]
        if market_id not in live:
            skip.append((market_id, "row missing"))
            continue
        source, external_id, current, name, updated_at = live[market_id]
        if source != "kalshi" or external_id != row["external_id"]:
            skip.append(
                (
                    market_id,
                    f"identity moved: {source!r} {external_id!r}, not kalshi "
                    f"{row['external_id']!r}",
                )
            )
            continue
        frm, to = (
            (row["after"], row["before"]) if restore else (row["before"], row["after"])
        )
        if current == to:
            skip.append((market_id, f"already {to!r}"))
            continue
        if current != frm:
            skip.append(
                (
                    market_id,
                    f"holds {current!r}, neither {frm!r} nor {to!r} — another "
                    "writer decided since the read",
                )
            )
            continue
        if not restore:
            if name != row["name"]:
                skip.append((market_id, "name changed since the read"))
                continue
            if updated_at != _instant(row["row_updated_at"], "row_updated_at"):
                skip.append(
                    (
                        market_id,
                        f"row version moved: updated_at {updated_at} since the "
                        f"read's {row['row_updated_at']}",
                    )
                )
                continue
        write.append((market_id, frm, to))
    movement: dict[str, int] = {}
    for _, frm, to in write:
        movement[f"{frm}->{to}"] = movement.get(f"{frm}->{to}", 0) + 1
    return {
        "write": write,
        "skip": skip,
        "movement": movement,
        "artifact": address,
        "plan_hash": plan_hash(address, write),
    }


def readback(rows: list[dict], live: dict[int, tuple]) -> dict:
    """Which artifact rows hold their ``after`` now. Pure, read-only."""
    holds: dict[str, list[int]] = {
        "after": [],
        "before": [],
        "other": [],
        "missing": [],
    }
    for row in sorted(rows, key=lambda r: r["id"]):
        got = live.get(row["id"])
        if got is None or got[0] != "kalshi" or got[1] != row["external_id"]:
            holds["missing"].append(row["id"])
        elif got[2] == row["after"]:
            holds["after"].append(row["id"])
        elif got[2] == row["before"]:
            holds["before"].append(row["id"])
        else:
            holds["other"].append(row["id"])
    return {"counts": {k: len(v) for k, v in holds.items()}, "ids": holds}


async def _read(session, ids: list[int]) -> dict[int, tuple]:
    got = await session.execute(
        text(
            "SELECT id, source, external_id, llm_sport_category, name, updated_at "
            "FROM futures_markets WHERE id = ANY(:ids)"
        ),
        {"ids": ids},
    )
    return {
        int(r.id): (r.source, r.external_id, r.llm_sport_category, r.name, r.updated_at)
        for r in got
    }


# Every value the plan decided on is re-stated, so a writer landing between the read
# and the write changes zero rows and the run refuses rather than overwriting it.
# `name` is null-safe because it is the one compared value that can be NULL.
_CAS_SQL = (
    "UPDATE futures_markets SET llm_sport_category = :target "
    "WHERE id = :id AND source = 'kalshi' AND external_id = :external_id "
    "AND llm_sport_category = :source_category "
    "AND name IS NOT DISTINCT FROM :name AND updated_at = :row_updated_at"
)

# The undo gates on identity and category only: a poll may have moved
# `updated_at` since the apply, and the undo must still land.
_RESTORE_SQL = (
    "UPDATE futures_markets SET llm_sport_category = :target "
    "WHERE id = :id AND source = 'kalshi' AND external_id = :external_id "
    "AND llm_sport_category = :source_category"
)


def parse_ids(raw: str, rows: list[dict]) -> frozenset[int]:
    try:
        ids = frozenset(int(x) for x in raw.split(",") if x.strip())
    except ValueError:
        raise Refused(f"--ids {raw!r} is not a comma-separated id list")
    if not ids:
        raise Refused("--ids is empty")
    stray = sorted(ids - {r["id"] for r in rows})
    if stray:
        raise Refused(f"--ids names ids that are not in the artifact: {stray}")
    return ids


async def run(
    session,
    artifact: dict,
    *,
    mode: str,
    now: datetime | None,
    expect_plan_hash: str | None = None,
    restore_ids: frozenset[int] | None = None,
) -> dict:
    rows = validate_artifact(artifact, now=now, evidence=mode in ("dry-run", "apply"))
    address = artifact_address(artifact)
    live = await _read(session, sorted(r["id"] for r in rows))
    if mode == "readback":
        return {"mode": mode, "artifact": address, **readback(rows, live)}

    decided = plan(rows, live, address, restore_ids=restore_ids)
    if mode == "apply" and expect_plan_hash != decided["plan_hash"]:
        raise Refused(
            f"plan hash is {decided['plan_hash']}, expected {expect_plan_hash!r} — the "
            "artifact or the population moved since the dry run; re-read it"
        )
    by_id = {r["id"]: r for r in rows}
    written = 0
    if mode in ("apply", "restore"):
        for market_id, frm, to in decided["write"]:
            row = by_id[market_id]
            params = {
                "id": market_id,
                "external_id": row["external_id"],
                "source_category": frm,
                "target": to,
            }
            if mode == "apply":
                params["name"] = row["name"]
                params["row_updated_at"] = _instant(
                    row["row_updated_at"], "row_updated_at"
                )
            result = await session.execute(
                text(_CAS_SQL if mode == "apply" else _RESTORE_SQL), params
            )
            if result.rowcount != 1:
                raise Refused(
                    f"market {market_id}: expected to change 1 row, changed "
                    f"{result.rowcount} — it moved since the read"
                )
            written += 1
        try:
            await session.commit()
        except Exception as exc:
            raise Unknown(_unknown_report(decided, mode, written, exc)) from exc
        except BaseException as exc:
            # A cancel or interrupt landing on the COMMIT is just as unknowable. It
            # keeps its own type and propagates; the report rides it to main().
            exc.commit_unknown = _unknown_report(decided, mode, written, exc)
            raise
    return {"mode": mode, **decided, "written": written}


def load_artifact(path: str):
    try:
        if path == "-":
            return json.load(sys.stdin)
        with open(path) as fh:
            return json.load(fh)
    except (OSError, ValueError) as exc:
        raise Refused(f"cannot read the artifact at {path!r}: {exc}")


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--plan", required=True, help="artifact path, or - for stdin")
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--apply", action="store_true")
    group.add_argument("--restore", action="store_true")
    group.add_argument("--readback", action="store_true")
    ap.add_argument("--expect-plan-hash", default=None)
    ap.add_argument(
        "--ids", default=None, help="restore only: the ids the apply printed"
    )
    args = ap.parse_args()
    mode = (
        "apply"
        if args.apply
        else "restore" if args.restore else "readback" if args.readback else "dry-run"
    )

    try:
        refuse_unless_production(dict(os.environ))
        if args.apply and not args.expect_plan_hash:
            raise Refused("--apply needs --expect-plan-hash (printed by the dry run)")
        if args.expect_plan_hash and not args.apply:
            raise Refused("--expect-plan-hash is for --apply only")
        if args.restore and not args.ids:
            raise Refused("--restore needs --ids (printed by the apply)")
        if args.ids and not args.restore:
            raise Refused("--ids is for --restore only")
        artifact = load_artifact(args.plan)
        restore_ids = None
        if args.restore:
            restore_ids = parse_ids(
                args.ids, validate_artifact(artifact, now=None, evidence=False)
            )
    except Refused as exc:
        print(f"REFUSED: {exc}")
        return 2

    from sqlalchemy.exc import DBAPIError

    from app.tasks.base import get_task_session

    readback = (
        f"heroku run --no-tty -a {os.environ['HEROKU_APP_NAME']} -- python3 "
        "scripts/repair_1109_football_shelf_residual.py --plan - --readback "
        "< <the same artifact>"
    )
    # Every way out of the session is decided INSIDE it, and nothing the session
    # wrapper's cleanup raises afterwards (its rollback, its normal-exit COMMIT,
    # close or dispose on a dead connection) changes the decision:
    # * a refusal comes before any COMMIT was sent, and is printed before the
    #   rollback, so a failing rollback can replace neither it nor its exit 2;
    # * an unacknowledged COMMIT is UNKNOWN and leaves the block by RAISING. A
    #   ``return`` is a normal exit, and the wrapper's normal exit runs
    #   ``await session.commit()`` again — a second COMMIT behind the one nobody
    #   heard back from;
    # * an acknowledged COMMIT is the result, printed with its undo line even if
    #   the wrapper's exit then raises.
    out: dict | None = None
    refused = False
    unknown: dict | None = None
    carried: BaseException | None = None
    try:
        async with get_task_session(
            statement_timeout_ms=STATEMENT_TIMEOUT_MS, lock_timeout_ms=LOCK_TIMEOUT_MS
        ) as session:
            try:
                out = await run(
                    session,
                    artifact,
                    mode=mode,
                    now=datetime.now(timezone.utc),
                    expect_plan_hash=args.expect_plan_hash,
                    restore_ids=restore_ids,
                )
            except Refused as exc:
                refused = True
                print(f"REFUSED: {exc}")
                await session.rollback()
                return 2
            except DBAPIError as exc:
                # A budget firing (lock_timeout 55P03, statement_timeout 57014) or
                # any other server refusal BEFORE the COMMIT was sent (``run`` turns
                # a failure at the COMMIT into ``Unknown``): the transaction never
                # committed, so no row of the plan is durable, and the run says so.
                refused = True
                code = getattr(exc.orig, "sqlstate", None) or getattr(
                    exc.orig, "pgcode", None
                )
                print(
                    f"REFUSED: the database stopped the run ({type(exc.orig).__name__}, "
                    f"sqlstate {code}) before its COMMIT was sent; nothing committed — "
                    "re-run the dry run when production is quieter"
                )
                await session.rollback()
                return 2
            except BaseException as exc:
                # ``Unknown`` (a failure at the COMMIT), or a cancel/interrupt that
                # landed on it and carries the same report. Anything else is not ours.
                report = (
                    exc.report
                    if isinstance(exc, Unknown)
                    else getattr(exc, "commit_unknown", None)
                )
                if report is not None:
                    unknown, carried = dict(report, readback=readback), exc
                    print(json.dumps(unknown, indent=2, default=str))
                raise
    except BaseException as exc:
        if refused:
            _cleanup_note(exc, "after the refusal above; no COMMIT was sent")
            if not isinstance(exc, Exception):
                raise
            return 2
        if unknown is not None:
            if exc is not carried:
                _cleanup_note(exc, "after the UNKNOWN report above")
            if isinstance(carried, Unknown):
                if not isinstance(exc, Exception):
                    raise  # an interrupt during the cleanup keeps propagating as itself
                return 3
            if exc is carried:
                raise
            # A cancel or interrupt on the COMMIT keeps its own type even when the
            # cleanup raised something else on the way out.
            raise carried
        if out is None:
            raise
        _print_result(out)
        _cleanup_note(
            exc,
            f"after the {out['mode']} above "
            + (
                "had its COMMIT acknowledged"
                if out["mode"] in ("apply", "restore")
                else "completed"
            ),
        )
        if not isinstance(exc, Exception):
            raise
        return 0
    _print_result(out)
    return 0


def _cleanup_note(exc: BaseException, after: str) -> None:
    print(
        f"note: the task session's cleanup raised {type(exc).__name__} {after}; "
        "it changes none of it",
        file=sys.stderr,
    )


def _print_result(out: dict) -> None:
    print(json.dumps(out, indent=2, default=str))
    if out["mode"] == "apply" and out["written"]:
        ids = ",".join(str(i) for i, _, _ in out["write"])
        print(
            "UNDO (keep the artifact): heroku run --no-tty -a bainluck -- python3 "
            "scripts/repair_1109_football_shelf_residual.py --plan - --restore "
            f"--ids {ids} < <the same artifact>"
        )


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
