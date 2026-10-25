"""#11234 — two Spanish council elections stored as esports move to politics.

THE SHIP: "Valladolid municipal election winner?" and "Valencia municipal election
winner?" stop appearing under **More Esports** (and in the public feed asked for
``tags=["sport:esports"]``) and are found as politics questions instead.

WHY THESE TWO ROWS STAY WRONG WITHOUT A WRITE
---------------------------------------------

The legacy esports stem ``kxval`` claimed KXVALLADOLIDCOUNCIL and KXVALENCIACOUNCIL
by prefix. PR #11237 (``3315cf8a56``) carves both series out of it, so a row minted
after that source is deployed is not esports. It moves no stored row: the Kalshi
upsert keeps any stored category other than ``other``
(``coalesce(nullif(llm_sport_category, 'other'), ...)``, ``tasks/kalshi.py``). So
the two rows the Measurement before-image read on 2026-10-18 19:48:36Z hold
``esports`` until something writes them.

The broad ``fix_misclassified_kalshi_categories.py`` sweep is NOT this route: it
scans a whole cohort, skips rows whose sport lookup answers None (exactly these
two, once the fix is deployed), carries no id/version gate, and its ORM write moves
``updated_at``. #2169's operator is not reused either: its pinned table is that
issue's frozen cohort, and it compares category and name only, so a same-value
write landing between its read and its UPDATE would go unseen. This one adds the row
version to the compare.

WHAT IT DOES
------------

One transaction. For each of the two pinned ids it runs a compare-and-set of
``llm_sport_category`` from ``esports`` to ``politics``. The WHERE clause re-states
the row's identity (source, external_id, group_id, name), its category and its row
version (``xmin``) as read in the same run. No other column moves. ``updated_at``
stays as it was: the ORM ``onupdate`` does not fire for ``text()`` SQL and no
database trigger touches ``futures_markets``. Every UPDATE returns the row's
``updated_at`` and the run refuses if that changed. Each statement must change
exactly one row, and the number written must equal the plan. Any refusal rolls the
whole transaction back, so both reviewed writes commit or neither does.

THE GROUP GUARD — the two before-images are not a group read
-------------------------------------------------------------

Each row is the Kalshi parent of its event group (``kalshi:<event ticker>``). The
ingest mints one row per event, but the before-image read only the two ids. Every
run therefore also reads EVERY row in both groups (``group_id`` is indexed; capped,
and a read at the cap refuses). That makes the dry run the first whole-group read.

* A sibling (any row in either group other than the two ids) is never written.
* A sibling holding ``esports`` is ``group_residual``, and the apply refuses. These
  two writes could not then pay the reader acceptance, and widening the cohort
  needs its own reviewed packet.
* A sibling holding anything else is reported but does not block. The plan hash
  carries each sibling's (id, category), so the group the reviewer read is the
  group the apply sees.

PER-ROW ACCOUNTING — every pinned id reports exactly one verdict
---------------------------------------------------------------

``write``    holds ``esports``, identity matches, evidence holds → written by the apply
``already``  holds ``politics`` → nothing to write; the apply goes on with the other
``missing``  no row with the id                                      → BLOCKS the apply
``foreign``  source / external_id / group_id / name differ from the pin → BLOCKS
``drifted``  holds neither ``esports`` nor ``politics``             → BLOCKS
``evidence`` the running source does not support the move           → BLOCKS

No verdict ever adds a row to the cohort or swaps one id for another. ``evidence``
asks the code that is running: ``categorize_by_rules(name)`` must answer
``politics``, and ``get_sport_key_from_ticker(external_id)`` must answer None, i.e.
the dyno carries the forward fix. A dry run on a release without #11237 therefore
reports both rows ``evidence`` and is not admissible. That is the main-app half of
the carriage check. The heavy half is the attended packet's ``heroku releases -a
bainluck-heavy`` line, because this script cannot see the other app.

Each row also reports ``version_matches_before_image``, i.e. whether its ``xmin``
still equals the Measurement read's ``54301846``. This is a report, not a gate. What
the apply enforces is the version read in the reviewed dry run, which the plan hash
binds. A same-value write landing after that dry run changes ``xmin``, the hash
moves, and the apply refuses. A write landing between the apply's own read and its
UPDATE matches zero rows, and the transaction rolls back.

THE UNDO — reviewable, never automatic
--------------------------------------

The apply prints each row's before-image, the version it read, and the version it
wrote (``RETURNING xmin``). ``--restore --written ID:VERSION,...`` is the inverse
compare-and-set (``politics`` back to ``esports``). It holds only while a row still
carries exactly the version the apply wrote. Any later write, even one that writes
the same value back, moves ``xmin``, and the restore refuses that row. A restore
with no ``--expect-plan-hash`` is a read-only restore PLAN. With the hash it
executes, in one transaction, under the same row-count and both-or-neither rules.
The run never invokes it on its own, including after an UNKNOWN outcome.

No backup table and no DDL. The pins, the printed before-images and the written
versions are the backup, so this is a data write, not notice 47(c) runtime DDL.

REFUSALS (exit 2, nothing written)
----------------------------------

* not on a production app (``HEROKU_APP_NAME`` must be ``bainluck`` or
  ``bainluck-heavy``);
* ``--apply`` without ``--expect-plan-hash``, or whose hash is not this run's plan;
* any blocking verdict or ``group_residual``, or a group read at its cap;
* a statement that changes other than exactly one row, or that moved ``updated_at``;
* the database stopping a statement. The session runs under 5 s lock and 10 s
  statement budgets, so a contended row refuses in seconds with the whole
  transaction rolled back.

A COMMIT THAT DOES NOT RETURN IS UNKNOWN (exit 3)
-------------------------------------------------

The COMMIT can become durable while its acknowledgement is lost (SQLSTATE 08006),
and a rollback sent afterwards proves nothing. The run then prints ``"outcome":
"UNKNOWN"`` with its mode, plan hash, the writes and the versions the UPDATEs
returned, and stops: no rollback claim, no retry, no reconnect-write, no restore.
The session leaves ``get_task_session`` by its exception path, so the wrapper never
sends a second COMMIT (#2169's ``fa00235b16`` lesson, kept verbatim in shape). Read
back with the dry run. A row that landed reads ``already`` and its ``xmin`` equals
the returned version.

DELIBERATELY NOT TOUCHED
------------------------

``canonical_market_key``, ``category_tags``, ``llm_league``, ``status``, names,
outcomes, winners, probabilities, history, every sibling row, #2169's frozen cohort
and its documented no-op ``38277227``.

    python3 scripts/repair_11234_council_elections_filed_as_esports.py              # dry run
    python3 scripts/repair_11234_council_elections_filed_as_esports.py --apply --expect-plan-hash H
    python3 scripts/repair_11234_council_elections_filed_as_esports.py --restore --written ID:V,ID:V
    python3 scripts/repair_11234_council_elections_filed_as_esports.py --restore --written ID:V,ID:V --expect-plan-hash H
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from typing import NamedTuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

PRODUCTION_APPS = frozenset({"bainluck", "bainluck-heavy"})

BEFORE = "esports"
AFTER = "politics"

#: The Measurement before-image's row version for both rows (2026-10-18 19:48:36Z,
#: ``artifacts/calibration-esports-election-20261018/BEFORE-IMAGE/RESULT.json``).
#: Reported against, never enforced: the reviewed dry run's own read is the gate.
BEFORE_IMAGE_VERSION = "54301846"


class Pin(NamedTuple):
    source: str
    external_id: str
    group_id: str
    name: str


#: The whole cohort: the two ids the served feed and the before-image named. The backup.
PINNED: dict[int, Pin] = {
    65521811: Pin(
        "kalshi",
        "KXVALLADOLIDCOUNCIL-27MAY23",
        "kalshi:KXVALLADOLIDCOUNCIL-27MAY23",
        "Valladolid municipal election winner?",
    ),
    65521812: Pin(
        "kalshi",
        "KXVALENCIACOUNCIL-27MAY23",
        "kalshi:KXVALENCIACOUNCIL-27MAY23",
        "Valencia municipal election winner?",
    ),
}

GROUPS: tuple[str, ...] = tuple(sorted({p.group_id for p in PINNED.values()}))

#: A group read that returns this many rows is refused as possibly truncated. The
#: ingest mints one row per event, so anything near it is not the population the
#: packet was reviewed on.
GROUP_READ_CAP = 50

#: Verdicts that stop the apply (and the restore) as a whole.
BLOCKING = frozenset({"missing", "foreign", "drifted", "evidence", "moved_since_apply"})

#: Per-connection budgets (``get_task_session`` kwargs, #4482), same values as the
#: sibling attended repairs (``repair_2169_misfiled_sport_category``).
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
    """``--written 65521811:123,65521812:123`` → {id: version}. Pinned ids only."""
    out: dict[int, str] = {}
    for part in (p.strip() for p in raw.split(",")):
        if not part:
            continue
        market_id, sep, version = part.partition(":")
        if not sep or not version.strip().isdigit():
            raise Refused(f"--written entry {part!r} is not ID:VERSION")
        out[int(market_id)] = version.strip()
    if not out:
        raise Refused("--written is empty")
    stray = sorted(set(out) - set(PINNED))
    if stray:
        raise Refused(f"--written names ids that are not pinned: {stray}")
    return out


def plan_hash(mode: str, writes: list[dict], siblings: list[tuple[int, str]]) -> str:
    """The identity of what this run would write, and of the group it read."""
    canon = json.dumps(
        {
            "mode": mode,
            "write": sorted(
                [w["id"], w["from"], w["to"], w["version"]] for w in writes
            ),
            "siblings": sorted([int(i), c] for i, c in siblings),
        },
        sort_keys=True,
    )
    return hashlib.sha256(canon.encode()).hexdigest()[:16]


def _identity_mismatch(pin: Pin, row: dict) -> list[str]:
    return [
        f"{field}={row.get(field)!r} (pinned {getattr(pin, field)!r})"
        for field in ("source", "external_id", "group_id", "name")
        if row.get(field) != getattr(pin, field)
    ]


def plan(
    rows: dict[int, dict],
    group_rows: list[dict],
    classify,
    ticker_sport,
    *,
    written: dict[int, str] | None = None,
) -> dict:
    """Decide per pinned id from what was read. Pure, so the unit file drives it.

    ``rows`` maps each pinned id that EXISTS to its read (``source``, ``external_id``,
    ``group_id``, ``name``, ``llm_sport_category``, ``status``, ``updated_at``,
    ``row_version``). ``group_rows`` is every row read in the two groups (``id``,
    ``llm_sport_category``, ``group_id``). ``classify`` / ``ticker_sport`` are the
    running source's ``categorize_by_rules`` / ``get_sport_key_from_ticker``.
    ``written`` set ⇒ restore mode over exactly those ids and versions.
    """
    restore = written is not None
    mode = "restore" if restore else "apply"
    source, target = (AFTER, BEFORE) if restore else (BEFORE, AFTER)
    accounting, writes = [], []
    for market_id in sorted(written) if restore else sorted(PINNED):
        pin = PINNED[market_id]
        row = rows.get(market_id)
        entry: dict = {"id": market_id}
        if row is None:
            accounting.append(dict(entry, verdict="missing"))
            continue
        entry["before_image"] = {
            k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in row.items()
        }
        entry["version_matches_before_image"] = (
            row["row_version"] == BEFORE_IMAGE_VERSION
        )
        mismatch = _identity_mismatch(pin, row)
        current = row["llm_sport_category"]
        if mismatch:
            verdict, why = "foreign", "; ".join(mismatch)
        elif current == target:
            verdict, why = "already", f"holds {target!r}"
        elif current != source:
            verdict = "drifted"
            why = f"holds {current!r}, neither {source!r} nor {target!r}"
        elif restore and row["row_version"] != written[market_id]:
            verdict = "moved_since_apply"
            why = (
                f"version {row['row_version']} is not the {written[market_id]} the "
                "apply wrote: a later write landed, and the undo is not ours to make"
            )
        elif not restore and classify(pin.name) != AFTER:
            verdict = "evidence"
            why = f"categorize_by_rules answers {classify(pin.name)!r} for the pinned name"
        elif not restore and ticker_sport(pin.external_id) is not None:
            verdict = "evidence"
            why = (
                f"get_sport_key_from_ticker still answers "
                f"{ticker_sport(pin.external_id)!r}: this release does not carry "
                "the forward fix (#11237)"
            )
        else:
            verdict, why = "write", f"{source!r} → {target!r}"
            writes.append(
                {
                    "id": market_id,
                    "from": source,
                    "to": target,
                    "version": row["row_version"],
                }
            )
        accounting.append(dict(entry, verdict=verdict, why=why))

    siblings = sorted(
        (int(r["id"]), r["llm_sport_category"])
        for r in group_rows
        if int(r["id"]) not in PINNED
    )
    residual = [i for i, c in siblings if c == BEFORE]
    blocking = [a["id"] for a in accounting if a["verdict"] in BLOCKING]
    reasons = []
    if blocking:
        reasons.append(f"blocking verdicts on {blocking}")
    if residual and not restore:
        reasons.append(
            f"group_residual: siblings {residual} also hold {BEFORE!r}; these two "
            "writes cannot pay the acceptance and widening needs its own packet"
        )
    if len(group_rows) >= GROUP_READ_CAP:
        reasons.append(
            f"group read reached its cap ({GROUP_READ_CAP}); not a whole-group read"
        )
    return {
        "mode": mode,
        "accounting": accounting,
        "write": writes,
        "siblings": siblings,
        "group_residual": residual,
        "admissible": not reasons,
        "refusal_reasons": reasons,
        "plan_hash": plan_hash(mode, writes, siblings),
    }


_READ_ROWS_SQL = (
    "SELECT id, source, external_id, group_id, name, llm_sport_category, status, "
    "updated_at, xmin::text AS row_version FROM futures_markets WHERE id = ANY(:ids)"
)

_READ_GROUPS_SQL = (
    "SELECT id, group_id, llm_sport_category FROM futures_markets "
    "WHERE group_id = ANY(:groups) ORDER BY id LIMIT :cap"
)

# Everything the plan decided on, re-stated: identity, category and row version.
# `xmin` moves on ANY update of the row, including one that writes the same values,
# so a writer landing between this run's read and its UPDATE makes the statement
# match zero rows. `xmin::text` keeps the bind a plain string (no xid codec).
# `name` is null-safe by habit; the pins are non-null, so plain `=` would also do.
_CAS_SQL = (
    "UPDATE futures_markets SET llm_sport_category = :target "
    "WHERE id = :id AND llm_sport_category = :source AND xmin::text = :version "
    "AND source = :src AND external_id = :ext AND group_id = :grp "
    "AND name IS NOT DISTINCT FROM :name "
    "RETURNING xmin::text AS row_version, updated_at"
)


async def _read(session) -> tuple[dict[int, dict], list[dict]]:
    got = await session.execute(text(_READ_ROWS_SQL), {"ids": sorted(PINNED)})
    rows = {int(r.id): dict(r._mapping) for r in got}
    for r in rows.values():
        r.pop("id", None)
    grp = await session.execute(
        text(_READ_GROUPS_SQL), {"groups": list(GROUPS), "cap": GROUP_READ_CAP}
    )
    return rows, [dict(r._mapping) for r in grp]


def _unknown_report(
    decided: dict, returned: dict, written: int, exc: BaseException
) -> dict:
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
            "not be durable. Not retried, not restored — read the two rows back with "
            "the dry run and an independent read before any further step"
        ),
    }


async def run(
    session,
    classify,
    ticker_sport,
    *,
    execute: bool,
    expect_plan_hash: str | None = None,
    written: dict[int, str] | None = None,
) -> dict:
    """Read, decide, and — when ``execute`` — write the plan in this transaction."""
    rows, group_rows = await _read(session)
    decided = plan(rows, group_rows, classify, ticker_sport, written=written)
    returned: dict[int, str] = {}
    count = 0
    if execute:
        if expect_plan_hash != decided["plan_hash"]:
            raise Refused(
                f"plan hash is {decided['plan_hash']}, expected {expect_plan_hash!r} — "
                "the rows or their groups moved since the reviewed dry run; re-read"
            )
        if not decided["admissible"]:
            raise Refused("; ".join(decided["refusal_reasons"]))
        for w in decided["write"]:
            pin, read = PINNED[w["id"]], rows[w["id"]]
            result = await session.execute(
                text(_CAS_SQL),
                {
                    "id": w["id"],
                    "source": w["from"],
                    "target": w["to"],
                    "version": w["version"],
                    "src": pin.source,
                    "ext": pin.external_id,
                    "grp": pin.group_id,
                    "name": pin.name,
                },
            )
            got = list(result)
            if len(got) != 1:
                raise Refused(
                    f"market {w['id']}: expected to change 1 row, changed {len(got)} — "
                    "its identity, category or version moved since the read"
                )
            if got[0].updated_at != read["updated_at"]:
                raise Refused(
                    f"market {w['id']}: updated_at moved ({read['updated_at']} → "
                    f"{got[0].updated_at}); this write must leave it alone"
                )
            returned[w["id"]] = got[0].row_version
            count += 1
        if count != len(decided["write"]):
            raise Refused(
                f"changed {count} rows, the plan holds {len(decided['write'])}"
            )
        if count:
            try:
                await session.commit()
            except Exception as exc:
                raise Unknown(_unknown_report(decided, returned, count, exc)) from exc
            except BaseException as exc:
                exc.commit_unknown = _unknown_report(decided, returned, count, exc)
                raise
    out = dict(decided, executed=execute, written=count, written_versions=returned)
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
        "--written",
        default=None,
        help="restore only: ID:VERSION pairs the apply printed",
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

    from sqlalchemy.exc import DBAPIError

    from app.tasks.base import get_task_session
    from app.utils.futures_categorization import categorize_by_rules
    from app.utils.sport_keys import get_sport_key_from_ticker

    execute = bool(args.apply or (args.restore and args.expect_plan_hash))
    readback = (
        f"heroku run:detached -a {os.environ['HEROKU_APP_NAME']} -- "
        "python3 scripts/repair_11234_council_elections_filed_as_esports.py"
    )
    # After an unacknowledged COMMIT the session must leave ``get_task_session`` by
    # its EXCEPTION path: its normal exit COMMITs again. Same shape as #2169's.
    unknown: dict | None = None
    carried: BaseException | None = None
    try:
        async with get_task_session(
            statement_timeout_ms=STATEMENT_TIMEOUT_MS, lock_timeout_ms=LOCK_TIMEOUT_MS
        ) as session:
            try:
                out = await run(
                    session,
                    categorize_by_rules,
                    get_sport_key_from_ticker,
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
                # A budget firing (55P03 / 57014) or any server refusal BEFORE the
                # COMMIT was sent: the transaction rolls back whole.
                await session.rollback()
                code = getattr(exc.orig, "sqlstate", None) or getattr(
                    exc.orig, "pgcode", None
                )
                print(
                    f"REFUSED: the database stopped the run ({type(exc.orig).__name__}, "
                    f"sqlstate {code}); rolled back, nothing committed"
                )
                return 2
            except BaseException as exc:
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
            "scripts/repair_11234_council_elections_filed_as_esports.py "
            f"--restore --written {pairs}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
