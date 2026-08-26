#!/usr/bin/env python3
"""CAL-P098 — the DB-DIRECT G1/G3 runner for the fold-narrowing rewrite.

WHAT CHANGED AND WHY, because this file is the subject of two of
`C-FOLD-REWRITE-1`'s four BLOCK findings.

CAL-P096 shipped this script as an **admin-rail** instrument: it POSTed the OLD
chain to ``/api/admin/db-query``, POSTed the NEW chain, and compared one MD5 per
side. Codex found three defects in that shape and every one of them is fatal to
the frozen gate rather than cosmetic:

1. **Two POSTs are two transactions.** Each request gets its own ``get_db``
   session; no snapshot spans the pair. The artifact nevertheless said "same
   session". On a population that ingests continuously, matching digests from
   two snapshots do not mean the two statements select the same rows — they
   mean nobody wrote in between, which is a fact about the clock.
2. **An MD5 is not ``EXCEPT ALL``.** A digest tells you *that* two row sets
   differ, never *which* rows, never how many, and never whether duplicate
   cardinality moved. The frozen G1 asks for bilateral ``EXCEPT ALL`` plus a
   duplicate check, and reserves aggregate agreement for a secondary line.
3. **MOD 997/9973 is not the frozen sample.** G1 pins ``MOD(fm.id, 64)`` and
   ``MOD(fm.id, 257)``, ≥8 non-adjacent residues, residue 0 and both edges. The
   old script could not reach that sample because the rail's row path is fixed
   at a 10 s statement timeout — an instrument ceiling reported as a sampling
   choice.

And the fourth finding: **G3 was never measured at all**, because the rail
composes ``EXPLAIN`` without ``ANALYZE``, so the only number available was
planner cost — which the frozen gate names, by itself, as insufficient.

So the instrument moved next to the database. This script runs on a one-off
dyno or a worker (the agent sandbox has no route to TCP 5432), opens **one**
``REPEATABLE READ, READ ONLY`` transaction, and runs every G1 residue and every
G3 plan inside it. The comparator lives in
``app/utils/fold_narrowing_gate.py`` so that the CI gate on a seeded Postgres
executes the identical statements — the harness is proved runnable before
production is asked to run it.

Usage (one-off dyno; scripts live at /app, there is no ``cd backend``)::

    heroku run:detached -a bainluck \
      "python3 scripts/verify_fold_narrowing_row_identity.py --gate both --bank"

    # ~N minutes later, read the durable row back — never trust the dyno's
    # stdout, which is EPERM-blocked from the agent sandbox (gotcha #48):
    curl -s -H "Authorization: Bearer $ADMIN_TOKEN" \
      "$BAINLUCK_API/api/admin/fold-narrowing-gate/last" | python3 -m json.tool

Local / CI (a throwaway Postgres, small population)::

    python3 scripts/verify_fold_narrowing_row_identity.py \
      --dsn postgresql://... --gate both --mod 8 --residue 0

Exit codes follow gotcha #54's amendment — ``1`` is a RESULT, anything else is a
story about the harness:

    0  every requested gate PASSED
    1  a gate FAILED (a real row/value/node difference)
    3  a gate could not be measured (timeout, empty sample, missing actuals)
    4  usage / configuration error
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.tasks.precompute_calibration import (  # noqa: E402
    _calibration_population_ctes,
)
from app.utils.fold_narrowing_gate import (  # noqa: E402
    G1_COLUMNS,
    G1_REQUIRED_COLUMNS,
    NEW_WINDOW_CTE,
    OLD_WINDOW_CTE,
    RESIDUE_PLAN,
    final_rows,
    g1_statement,
    g1_verdict,
    g3_statement,
    g3_verdict,
    named_node_metrics,
    residues_are_non_adjacent,
    sample_predicate,
)

#: The frozen pre-split emission. It is the OLD side of every comparison, and it
#: is an oracle only while the untouched parts of the chain still match it —
#: ``TestEmittedRelationIsUnchanged`` in
#: ``tests/test_calibration_fold_narrowing_p096.py`` is that staleness alarm.
FUSED = BACKEND / "tests" / "fixtures" / "cal_p096_fused_population_ctes.sql"

#: The durable identity this runner banks under, read back by
#: ``GET /api/admin/fold-narrowing-gate/last``.
GATE_IDENTITY = "calibration:fold_narrowing_gate"
GATE_SCHEMA = "calibration-fold-narrowing-gate/v1"

#: ``market_info``'s status filter — the one splice point for the G1 sample.
#: The generator writes ``market_info_extra`` directly beneath it, so the frozen
#: oracle is spliced at the same slot rather than a lookalike.
_ANCHOR = "WHERE fm.status = 'resolved'"


def old_chain(extra: str) -> str:
    body = FUSED.read_text()
    if not extra:
        return body
    if _ANCHOR not in body:
        raise SystemExit(
            "cannot find market_info's status filter in the frozen oracle — "
            "the splice point moved and the sample would land somewhere else"
        )
    return body.replace(_ANCHOR, f"{_ANCHOR}\n                  {extra}", 1)


def new_chain(extra: str) -> str:
    return _calibration_population_ctes(market_info_extra=extra)


async def _connect(dsn: str):
    import asyncpg

    kwargs: dict = {}
    if "localhost" not in dsn and "127.0.0.1" not in dsn:
        kwargs["ssl"] = "require"
    # asyncpg speaks postgres:// and postgresql:// but not SQLAlchemy's
    # +asyncpg suffix, which is what DATABASE_URL carries in some envs.
    dsn = dsn.replace("postgresql+asyncpg://", "postgresql://").replace(
        "postgres+asyncpg://", "postgres://"
    )
    return await asyncpg.connect(dsn, **kwargs)


async def _deduped_columns(conn, chain: str) -> list[str]:
    """Column names of ``deduped``, read from the relation rather than assumed."""
    from app.utils.sql_comment_strip import strip_sql_comments

    stmt = await conn.prepare(
        strip_sql_comments(f"WITH {chain}\nSELECT * FROM deduped LIMIT 0")
    )
    return [a.name for a in stmt.get_attributes()]


def _fingerprint(sql: str) -> str:
    """SHA-256 of the exact statement sent, first 16 hex.

    G1 asks for the fingerprint of every run alongside k, residue, market count,
    duration and timeout. It is the cheap way to prove afterwards that eight
    samples differed ONLY in their residue — a harness that quietly re-sent one
    statement eight times would otherwise produce eight agreeing rows and look
    thorough.
    """
    return hashlib.sha256(sql.encode()).hexdigest()[:16]


async def run_g1(conn, plan, *, timeout_ms: int) -> dict:
    samples = []
    for mod, residue in plan:
        label = f"MOD {mod}={residue}"
        extra = sample_predicate(mod, residue)
        sql = g1_statement(old_chain=old_chain(extra), new_chain=new_chain(extra))
        fingerprint = _fingerprint(sql)
        started = time.monotonic()
        try:
            # A nested ``conn.transaction()`` is a SAVEPOINT, and it is what
            # keeps one slow residue from destroying the run: a statement
            # timeout aborts the transaction, and every later statement in an
            # aborted transaction fails with InFailedSQLTransaction — so
            # without this, residue 1 timing out would report residues 2..8 as
            # errors that never ran. Rolling back to a savepoint leaves the
            # OUTER transaction, and therefore the single REPEATABLE READ
            # snapshot, entirely intact.
            async with conn.transaction():
                await conn.execute(f"SET LOCAL statement_timeout = {int(timeout_ms)}")
                record = await conn.fetchrow(sql)
        except Exception as exc:  # noqa: BLE001 — a refusal is data, not a crash
            samples.append(
                {
                    "label": label,
                    "mod": mod,
                    "residue": residue,
                    "verdict": "NOT_MEASURED",
                    "reasons": [f"{type(exc).__name__}: {exc}"],
                    "sql_fingerprint": fingerprint,
                    "timeout_ms": int(timeout_ms),
                    "duration_s": round(time.monotonic() - started, 3),
                }
            )
            continue
        if record is None:
            # The comparator always returns exactly one row, so this cannot
            # happen — which is precisely why it must not be read as zeros.
            samples.append(
                {
                    "label": label,
                    "mod": mod,
                    "residue": residue,
                    "verdict": "NOT_MEASURED",
                    "reasons": ["the comparator returned no row at all"],
                    "sql_fingerprint": fingerprint,
                    "timeout_ms": int(timeout_ms),
                    "duration_s": round(time.monotonic() - started, 3),
                }
            )
            continue
        row = {k: record[k] for k in G1_COLUMNS}
        verdict, reasons = g1_verdict(row)
        samples.append(
            {
                "label": label,
                "mod": mod,
                "residue": residue,
                "verdict": verdict,
                "reasons": reasons,
                "counters": {k: int(v) for k, v in row.items()},
                "sql_fingerprint": fingerprint,
                "timeout_ms": int(timeout_ms),
                "duration_s": round(time.monotonic() - started, 3),
            }
        )
        print(
            f"  G1 {label:<14} {verdict:<12} n={row['n_old']}/{row['n_new']} "
            f"old_only={row['old_only_rows']} new_only={row['new_only_rows']} "
            f"buckets={row['bucket_old_only']}/{row['bucket_new_only']} "
            f"({samples[-1]['duration_s']} s)",
            flush=True,
        )
        for reason in reasons:
            print(f"       - {reason}", flush=True)

    verdicts = {s["verdict"] for s in samples}
    if "FAIL" in verdicts:
        gate = "FAIL"
    elif "NOT_MEASURED" in verdicts or not samples:
        gate = "NOT_MEASURED"
    else:
        gate = "PASS"
    return {"gate": "G1", "verdict": gate, "samples": samples}


async def run_g3(conn, plan, *, timeout_ms: int) -> dict:
    samples = []
    for index, (mod, residue) in enumerate(plan):
        label = f"MOD {mod}={residue}"
        extra = sample_predicate(mod, residue)
        statements = {
            "old": g3_statement(old_chain(extra)),
            "new": g3_statement(new_chain(extra)),
        }
        # Alternate run order so cache warmth cannot manufacture the win: the
        # second statement of a pair always reads a warmer buffer pool, so if
        # NEW always ran second, NEW would always look faster.
        order = ("old", "new") if index % 2 == 0 else ("new", "old")
        sample: dict = {
            "label": label,
            "mod": mod,
            "residue": residue,
            "order": order,
            "timeout_ms": int(timeout_ms),
            "sql_fingerprint": {
                side: _fingerprint(text) for side, text in statements.items()
            },
        }
        for side in order:
            cte = OLD_WINDOW_CTE if side == "old" else NEW_WINDOW_CTE
            try:
                # Savepoint per plan, same reason as G1: an EXPLAIN ANALYZE
                # that hits the statement timeout must cost its own sample and
                # nothing else.
                async with conn.transaction():
                    await conn.execute(
                        f"SET LOCAL statement_timeout = {int(timeout_ms)}"
                    )
                    raw = await conn.fetchval(statements[side])
            except Exception as exc:  # noqa: BLE001
                sample[side] = {
                    "measured": False,
                    "reason": f"{type(exc).__name__}: {exc}",
                }
                continue
            try:
                plan_json = json.loads(raw) if isinstance(raw, str) else raw
                root = plan_json[0]["Plan"]
            except Exception as exc:  # noqa: BLE001
                # A plan we cannot parse is a gate we did not measure. It is
                # NOT a gate that agreed, and it must not take the run down
                # either — the other seven residues are still worth having.
                sample[side] = {
                    "measured": False,
                    "reason": f"unparseable EXPLAIN output: {type(exc).__name__}",
                }
                continue
            sample[side] = named_node_metrics(root, cte)
            sample[f"final_rows_{side}"] = final_rows(root)
            sample[f"execution_ms_{side}"] = plan_json[0].get("Execution Time")
        samples.append(sample)
        print(
            f"  G3 {label:<14} order={'->'.join(order)} "
            f"old_width={sample.get('old', {}).get('sort_plan_width')} "
            f"new_width={sample.get('new', {}).get('sort_plan_width')} "
            f"old_rows={sample.get('old', {}).get('sort_input_rows')} "
            f"new_rows={sample.get('new', {}).get('sort_input_rows')}",
            flush=True,
        )

    verdict, reasons, summary = g3_verdict(samples)
    for reason in reasons:
        print(f"       - {reason}", flush=True)
    return {
        "gate": "G3",
        "verdict": verdict,
        "reasons": reasons,
        "summary": summary,
        "samples": samples,
    }


async def bank(report: dict) -> str:
    from app.services.durable_snapshots import publish_snapshot_standalone
    from app.utils.durable_state import DurableEnvelope

    envelope = DurableEnvelope.build(
        identity=GATE_IDENTITY,
        schema_version=GATE_SCHEMA,
        payload=report,
        # ``complete`` means "this artifact is a verdict a reader may serve".
        # A gate that could not measure is not one (gotcha #53), and the reader
        # surfaces it under ``measured: false`` rather than as a clean zero.
        complete=report.get("verdict") in {"PASS", "FAIL"},
        source="scripts/verify_fold_narrowing_row_identity.py",
    )
    result = await publish_snapshot_standalone(envelope)
    return str(result.get("status"))


async def main_async(args) -> int:
    dsn = args.dsn or os.environ.get("DATABASE_URL")
    if not dsn:
        print("no --dsn and no DATABASE_URL — this runner is DB-direct", flush=True)
        return 4

    plan = list(RESIDUE_PLAN)
    if args.mod or args.residue:
        if not (args.mod and args.residue) or len(args.mod) != len(args.residue):
            print("--mod and --residue must be given in matching pairs", flush=True)
            return 4
        plan = list(zip(args.mod, args.residue))
    if args.full:
        plan = [(None, 0)]

    report: dict = {
        "schema": GATE_SCHEMA,
        "cert": "C-FOLD-REWRITE-1",
        "gates_requested": args.gate,
        "residue_plan": [{"mod": m, "residue": r} for m, r in plan],
        "residue_plan_frozen": plan == list(RESIDUE_PLAN),
        "residues_non_adjacent": residues_are_non_adjacent(
            [(m, r) for m, r in plan if m]
        ),
        "statement_timeout_ms": args.timeout_ms,
        "isolation": "REPEATABLE READ, READ ONLY (one transaction spans every gate)",
    }

    conn = await _connect(dsn)
    try:
        tx = conn.transaction(isolation="repeatable_read", readonly=True)
        await tx.start()
        try:
            # ``now()`` is transaction-start time, so recording it once and
            # again at the end is the proof that every gate below ran inside
            # ONE snapshot — the thing CAL-P096's two-POST harness asserted in
            # prose and could not demonstrate.
            report["snapshot_started_at"] = str(await conn.fetchval("SELECT now()"))
            try:
                # Savepointed: on a pooled or standby connection this can fail,
                # and a bare failure would abort the transaction we are about to
                # run every gate inside. It is a nice-to-have, not the proof.
                async with conn.transaction():
                    report["snapshot_id"] = await conn.fetchval(
                        "SELECT pg_export_snapshot()"
                    )
            except Exception as exc:  # noqa: BLE001
                report["snapshot_id"] = f"unavailable: {type(exc).__name__}"

            columns = await _deduped_columns(conn, new_chain(""))
            report["deduped_columns"] = columns
            missing = [c for c in G1_REQUIRED_COLUMNS if c not in columns]
            report["g1_required_columns_missing"] = missing
            if missing:
                print(
                    f"deduped is missing G1-named columns {missing} — the "
                    "comparison would silently not cover them",
                    flush=True,
                )
                report["verdict"] = "NOT_MEASURED"
                return 3

            if args.gate in ("g1", "both"):
                print("== G1 — bilateral EXCEPT ALL, one snapshot ==", flush=True)
                report["g1"] = await run_g1(conn, plan, timeout_ms=args.timeout_ms)
            if args.gate in ("g3", "both"):
                print("== G3 — EXPLAIN (ANALYZE, BUFFERS, VERBOSE) ==", flush=True)
                report["g3"] = await run_g3(conn, plan, timeout_ms=args.timeout_ms)
            report["snapshot_still_open_at"] = str(
                await conn.fetchval("SELECT now()")
            )
            report["one_snapshot"] = (
                report["snapshot_still_open_at"] == report["snapshot_started_at"]
            )
        finally:
            await tx.rollback()
    finally:
        await conn.close()

    verdicts = [report[k]["verdict"] for k in ("g1", "g3") if k in report]
    if "FAIL" in verdicts:
        report["verdict"] = "FAIL"
        code = 1
    elif "NOT_MEASURED" in verdicts or not verdicts:
        report["verdict"] = "NOT_MEASURED"
        code = 3
    else:
        report["verdict"] = "PASS"
        code = 0

    if args.bank:
        try:
            report["durable"] = await bank(report)
        except Exception as exc:  # noqa: BLE001
            report["durable"] = f"error: {type(exc).__name__}: {exc}"

    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps(report, indent=2, sort_keys=True, default=str), flush=True)
    print(f"VERDICT: {report['verdict']}  EXIT: {code}", flush=True)
    return code


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gate", choices=("g1", "g3", "both"), default="both")
    parser.add_argument("--dsn", default=None)
    parser.add_argument("--mod", action="append", type=int, default=None)
    parser.add_argument("--residue", action="append", type=int, default=None)
    parser.add_argument(
        "--full",
        action="store_true",
        help="unsampled population — G5-shaped, expect the 5,400 s ceiling",
    )
    parser.add_argument(
        "--timeout-ms",
        dest="timeout_ms",
        type=int,
        default=300_000,
        help="per-statement timeout; G3 freezes this at 60-300 s",
    )
    parser.add_argument("--bank", action="store_true", help="write the durable row")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
