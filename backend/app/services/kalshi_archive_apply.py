"""#683 archive import: dry-run by default, exact-plan apply, own-rows restore.

PILLAR: TRUTH. SHIP: a settled Kalshi question with missing history gains its
real recoverable pre-resolution probability journey on web and native, with
archive provenance and honest forecast eligibility.

This is the only writer of the archive store (``kalshi_archive_*``, see the
models and migration ``kalshi_archive_store_683``). Nothing schedules it. It is
run by a person through ``scripts/kalshi_archive_import.py``, and it writes only
when told ``write=True`` AND handed the plan's own digest.

WHAT AN APPLY CHECKS BEFORE IT WRITES A ROW

1. **The plan is the plan that was reviewed.** ``plan_digest`` is recomputed
   from the points in the file and must equal both the file's own digest and
   the digest the operator typed. One edited point changes it.
2. **Every point follows from the provider's bytes.** Each read window carries
   its exact response text. The apply re-verifies the SHA-256, re-checks the
   echoed ticker, re-runs the planner's own classifier over those candles, and
   refuses an outcome whose planned points are not exactly what the bytes say.
3. **The stored inputs have not moved.** The outcome's identity and its
   forecast-cutoff inputs are re-read and fingerprinted
   (:func:`~app.utils.kalshi_archive_history.input_fingerprint`). A different
   fingerprint refuses that outcome (``input_drift``); it is not re-planned here.
4. **Forecast admission is re-decided, never inherited.** The cutoff is
   recomputed from the CURRENT event row. A point stays ``forecast`` only when
   the plan said so AND the apply says so. Any disagreement demotes it to
   ``reader_only`` and is counted. Nothing is promoted.
5. **An existing interval is never overwritten.** The unique key
   ``uq_kai_interval`` decides. An identical existing row is counted as
   identical. A different one is reported as a conflict and left as it is.

HOW PROGRESS IS KEPT. One transaction per outcome: the evidence row, its
intervals and the import's running ``inserted_ids`` commit together, and are
read back immediately after the commit. A failure inside one outcome rolls
back only that outcome; earlier outcomes stay committed and accounted for
(gotcha #42). Nothing is rolled back automatically across outcomes.

RESTORE removes exactly the rows one import inserted: the ids in its own
``inserted_ids``, which must equal the rows that carry its ``import_id``. Any
difference refuses the restore. There is no broad delete.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict
from types import SimpleNamespace
from typing import Any, Callable, Optional

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB

from app.utils.kalshi_archive_history import (
    ADMIT_FORECAST,
    ADMIT_READER_ONLY,
    ROUTE_ARCHIVE,
    PlannedPoint,
    classify_candles,
    forecast_cutoff,
    identity_refusal,
    importable,
    input_fingerprint,
    parse_instant,
    plan_digest,
)

logger = logging.getLogger(__name__)

ARCHIVE_STORE_PRESENT_SQL = (
    "SELECT to_regclass('public.kalshi_archive_intervals') IS NOT NULL"
)

#: Two probabilities this close are the same observation (NUMERIC(7,6) storage).
SAME_PROBABILITY = 5e-7

CURRENT_INPUT_SQL = """
    SELECT fo.id AS outcome_id,
           fo.external_id AS ticker,
           fm.external_id AS event_ticker,
           fo.market_id AS market_id,
           fm.event_id AS event_id,
           fo.resolution_source AS resolution_source,
           (e.id IS NOT NULL) AS has_event,
           e.commence_time AS commence_time,
           e.commence_time_source AS commence_time_source,
           e.created_at AS created_at,
           e.completed_at AS completed_at,
           fo.xmin::text AS outcome_xmin,
           fm.xmin::text AS market_xmin,
           e.xmin::text AS event_xmin
    FROM futures_outcomes fo
    JOIN futures_markets fm ON fm.id = fo.market_id
    LEFT JOIN events e ON e.id = fm.event_id
    WHERE fo.id = :oid AND fm.source = 'kalshi'
"""

EXISTING_SQL = text(
    """
    SELECT id, interval_end, probability, price_basis, raw_response_sha256
    FROM kalshi_archive_intervals
    WHERE outcome_id = :oid
      AND period_minutes = :period
      AND interval_end = ANY(:ends)
    """
)

CREATE_IMPORT_SQL = text(
    """
    INSERT INTO kalshi_archive_imports
        (import_key, plan_digest, archive_cutoff, status, report)
    VALUES (:key, :digest, :cutoff, 'applying', CAST(:report AS jsonb))
    RETURNING id
    """
)

EVIDENCE_SQL = text(
    """
    INSERT INTO kalshi_archive_outcome_evidence
        (import_id, outcome_id, market_ticker, event_ticker, period_minutes,
         venue_open_ts, venue_settlement_ts, archive_cutoff, coverage,
         input_fingerprint, cutoff_inputs, forecast_cutoff_ts, cutoff_refusal,
         plan_forecast_cutoff_ts, plan_cutoff_refusal, windows, owed_windows)
    VALUES
        (:import_id, :oid, :ticker, :event_ticker, :period,
         :open_ts, :settled, :cutoff, :coverage,
         :fingerprint, :cutoff_inputs, :forecast_cutoff, :cutoff_refusal,
         :plan_forecast_cutoff, :plan_cutoff_refusal, :windows, :owed)
    RETURNING id
    """
).bindparams(
    bindparam("cutoff_inputs", type_=JSONB),
    bindparam("windows", type_=JSONB),
    bindparam("owed", type_=JSONB),
)

INTERVAL_SQL = text(
    """
    INSERT INTO kalshi_archive_intervals
        (import_id, evidence_id, outcome_id, market_ticker, event_ticker,
         period_minutes, interval_start, interval_end, venue_settlement_ts,
         probability, price_basis, volume, echoed_ticker, raw_response_sha256,
         retrieved_at, admission_at_plan, admission_at_apply)
    VALUES
        (:import_id, :evidence_id, :oid, :ticker, :event_ticker,
         :period, :start, :end, :settled,
         :probability, :basis, :volume, :echoed, :sha,
         :retrieved, :plan_adm, :apply_adm)
    ON CONFLICT ON CONSTRAINT uq_kai_interval DO NOTHING
    RETURNING id
    """
)

PROGRESS_SQL = text(
    """
    UPDATE kalshi_archive_imports
    SET inserted_ids = inserted_ids || CAST(:ids AS bigint[]),
        outcome_ids = array_append(outcome_ids, CAST(:oid AS integer))
    WHERE id = :import_id AND status = 'applying'
    """
)

READBACK_SQL = text(
    """
    SELECT id FROM kalshi_archive_intervals
    WHERE import_id = :import_id AND outcome_id = :oid
    """
)

FINISH_SQL = text(
    """
    UPDATE kalshi_archive_imports
    SET status = :status, finished_at = now(), report = :report
    WHERE id = :import_id AND status = 'applying'
    """
).bindparams(bindparam("report", type_=JSONB))


class PlanRefused(Exception):
    """The plan as a whole may not be applied. ``reason`` says why."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _default_session_factory():
    from app.tasks.base import get_task_session

    return get_task_session()


def _points(plan: dict) -> list[PlannedPoint]:
    return [PlannedPoint(**p) for p in plan.get("points") or ()]


def verify_plan_document(report: Any, expected_digest: str) -> list[dict]:
    """Every outcome plan that has something to import, once the file is proven.

    Raises :class:`PlanRefused` when the file is not a dry-run plan, carries no
    provider cutoff, or its digest is not the one recomputed from its points
    and typed by the operator.
    """
    if not isinstance(report, dict) or report.get("mode") != "dry_run":
        raise PlanRefused("not_a_dry_run_plan")
    if parse_instant(report.get("archive_cutoff")) is None:
        raise PlanRefused("archive_cutoff_missing")
    plans = report.get("plans")
    if not isinstance(plans, list):
        raise PlanRefused("plans_missing")
    try:
        recomputed = plan_digest(p for plan in plans for p in _points(plan))
    except TypeError:
        raise PlanRefused("plan_points_malformed") from None
    if recomputed != report.get("plan_digest"):
        raise PlanRefused("plan_digest_mismatch")
    if not expected_digest or expected_digest != recomputed:
        raise PlanRefused("expected_digest_mismatch")
    return [plan for plan in plans if importable(_points(plan))]


def rederivation_refusal(plan: dict, archive_cutoff: Any) -> Optional[str]:
    """``None`` when the plan's importable points follow exactly from its bytes."""
    from app.services.kalshi_archive_recovery import _payload_from_entry

    ticker = plan.get("ticker")
    market = plan.get("market")
    if plan.get("route") != ROUTE_ARCHIVE or plan.get("refusal") is not None:
        return "plan_not_archive_route"
    if identity_refusal(ticker, plan.get("event_ticker"), market) is not None:
        return "plan_market_identity"
    settled_at = parse_instant(plan.get("settled_at"))
    if settled_at is None or settled_at != parse_instant(market.get("settlement_ts")):
        return "plan_settlement_mismatch"
    cutoff = parse_instant(archive_cutoff)
    if cutoff is None or settled_at >= cutoff:
        return "plan_not_archive_tier"
    candles: list = []
    lineage: list = []
    for entry in plan.get("windows") or ():
        if entry.get("period_minutes") != plan.get("period_minutes"):
            return "window_period_mismatch"
        try:
            payload = _payload_from_entry(ticker, entry)
        except Exception as e:  # digest, echo or shape: the bytes do not verify
            return f"window_raw:{getattr(e, 'reason', type(e).__name__)}"
        if payload.echoed_ticker != entry.get("echoed_ticker"):
            return "window_echo_mismatch"
        candles.extend(payload.candles)
        lineage.extend([payload.raw_sha256] * len(payload.candles))
    derived, _ = classify_candles(
        outcome_id=int(plan["outcome_id"]),
        ticker=ticker,
        candles=candles,
        period_minutes=int(plan["period_minutes"]),
        settled_at=settled_at,
        cutoff=parse_instant(plan.get("forecast_cutoff")),
        cutoff_refusal=plan.get("cutoff_refusal"),
        candle_lineage=lineage,
    )

    def key(p: PlannedPoint) -> tuple:
        row = asdict(p)
        row.pop("already_stored")
        return tuple(sorted(row.items()))

    derived_keys = {key(p) for p in importable(derived)}
    if not all(key(p) in derived_keys for p in importable(_points(plan))):
        return "points_do_not_follow_from_raw"
    return None


def _event_of(row: Any) -> Optional[SimpleNamespace]:
    if not row.has_event:
        return None
    return SimpleNamespace(
        commence_time=row.commence_time,
        commence_time_source=row.commence_time_source,
        created_at=row.created_at,
        completed_at=row.completed_at,
    )


def _iso(value: Any) -> Optional[str]:
    parsed = parse_instant(value)
    return parsed.isoformat() if parsed else None


async def apply_archive_plan(
    report: dict,
    *,
    expected_digest: str,
    write: bool = False,
    session_factory: Callable[[], Any] = _default_session_factory,
    import_key: Optional[str] = None,
) -> dict:
    """Dry-run (default) or apply one reviewed plan. See the module doc."""
    plans = verify_plan_document(report, expected_digest)
    archive_cutoff = parse_instant(report["archive_cutoff"])
    async with session_factory() as session:
        await session.execute(text("SET TRANSACTION READ ONLY"))
        present = (await session.execute(text(ARCHIVE_STORE_PRESENT_SQL))).scalar()
    if not present:
        raise PlanRefused("archive_store_absent")
    key = import_key or uuid.uuid4().hex
    result: dict = {
        "mode": "apply" if write else "dry_run",
        "plan_digest": report["plan_digest"],
        "import_key": key if write else None,
        "import_id": None,
        "archive_cutoff": archive_cutoff.isoformat(),
        "outcomes": [],
        "inserted": 0,
        "identical": 0,
        "conflicts": [],
        "refused": [],
        "errors": [],
        "demoted_to_reader_only": 0,
        "status": None,
    }
    import_id: Optional[int] = None
    if write:
        async with session_factory() as session:
            import_id = (
                await session.execute(
                    CREATE_IMPORT_SQL,
                    {
                        "key": key,
                        "digest": report["plan_digest"],
                        "cutoff": archive_cutoff,
                        "report": json.dumps({"outcomes_planned": len(plans)}),
                    },
                )
            ).scalar_one()
            await session.commit()
        result["import_id"] = import_id

    stopped: Optional[str] = None
    for plan in plans:
        oid = int(plan["outcome_id"])
        try:
            outcome = await _apply_outcome(
                plan,
                archive_cutoff=archive_cutoff,
                write=write,
                import_id=import_id,
                session_factory=session_factory,
            )
        except Exception as e:  # one outcome never wipes the pass (gotcha #42)
            logger.warning("archive import: outcome %s failed: %s", oid, str(e)[:200])
            result["errors"].append({"outcome_id": oid, "error": str(e)[:200]})
            continue
        result["outcomes"].append(outcome)
        if outcome.get("refused"):
            result["refused"].append(
                {"outcome_id": oid, "reason": outcome["refused"]}
            )
            continue
        result["inserted"] += outcome["inserted"]
        result["identical"] += outcome["identical"]
        result["demoted_to_reader_only"] += outcome["demoted_to_reader_only"]
        result["conflicts"].extend(outcome["conflicts"])
        if outcome.get("readback") == "mismatch":
            stopped = f"readback_mismatch:{oid}"
            break

    clean = not (result["refused"] or result["errors"] or result["conflicts"] or stopped)
    result["status"] = "applied" if clean else "partial"
    if stopped:
        result["stopped"] = stopped
    result["gained_history_outcome_ids"] = sorted(
        o["outcome_id"] for o in result["outcomes"] if o.get("inserted")
    )
    result["zero_snapshot_cohort_gained_ids"] = sorted(
        o["outcome_id"]
        for o in result["outcomes"]
        if o.get("inserted") and o.get("live_snapshots_at_plan") == 0
    )
    if write:
        async with session_factory() as session:
            await session.execute(
                FINISH_SQL,
                {
                    "status": result["status"],
                    "report": _summary(result),
                    "import_id": import_id,
                },
            )
            await session.commit()
    return result


def _summary(result: dict) -> dict:
    """What the import row keeps: counts and ids, never the raw bodies."""
    return {
        k: result[k]
        for k in (
            "plan_digest",
            "inserted",
            "identical",
            "conflicts",
            "refused",
            "errors",
            "demoted_to_reader_only",
            "status",
            "gained_history_outcome_ids",
            "zero_snapshot_cohort_gained_ids",
        )
    } | ({"stopped": result["stopped"]} if result.get("stopped") else {})


async def _apply_outcome(
    plan: dict,
    *,
    archive_cutoff,
    write: bool,
    import_id: Optional[int],
    session_factory: Callable[[], Any],
) -> dict:
    oid = int(plan["outcome_id"])
    period = int(plan["period_minutes"])
    settled_at = parse_instant(plan["settled_at"])
    out: dict = {
        "outcome_id": oid,
        "ticker": plan.get("ticker"),
        "live_snapshots_at_plan": int(plan.get("live_snapshots") or 0),
        "coverage": plan.get("coverage"),
        "planned": 0,
        "inserted": 0,
        "inserted_ids": [],
        "identical": 0,
        "conflicts": [],
        "demoted_to_reader_only": 0,
        "refused": None,
    }
    why = rederivation_refusal(plan, archive_cutoff)
    if why:
        out["refused"] = why
        return out
    points = importable(_points(plan))
    out["planned"] = len(points)
    lineage = {w["raw_sha256"]: w for w in plan.get("windows") or ()}

    async with session_factory() as session:
        if not write:
            await session.execute(text("SET TRANSACTION READ ONLY"))
        row = (await session.execute(text(CURRENT_INPUT_SQL), {"oid": oid})).first()
        if row is None:
            out["refused"] = "outcome_missing"
            return out
        if input_fingerprint(row) != plan.get("input_fingerprint"):
            out["refused"] = "input_drift"
            return out
        cutoff, cutoff_refusal = forecast_cutoff(_event_of(row), settled_at)
        existing = {
            parse_instant(r.interval_end): r
            for r in (
                await session.execute(
                    EXISTING_SQL,
                    {
                        "oid": oid,
                        "period": period,
                        "ends": [parse_instant(p.interval_end) for p in points],
                    },
                )
            ).fetchall()
        }
        fresh: list[tuple[PlannedPoint, str]] = []
        for p in points:
            end = parse_instant(p.interval_end)
            apply_says = (
                ADMIT_FORECAST if cutoff is not None and end <= cutoff else ADMIT_READER_ONLY
            )
            admission = (
                ADMIT_FORECAST
                if p.admission == ADMIT_FORECAST and apply_says == ADMIT_FORECAST
                else ADMIT_READER_ONLY
            )
            if p.admission == ADMIT_FORECAST and admission != ADMIT_FORECAST:
                out["demoted_to_reader_only"] += 1
            prior = existing.get(end)
            if prior is not None:
                same = (
                    abs(float(prior.probability) - float(p.probability)) <= SAME_PROBABILITY
                    and prior.price_basis == p.price_basis
                )
                if same:
                    out["identical"] += 1
                else:
                    out["conflicts"].append(_conflict(oid, p, prior))
                continue
            fresh.append((p, admission))
        if not fresh or not write:
            out["would_insert"] = len(fresh)
            return out

        market = plan["market"]
        evidence_id = (
            await session.execute(
                EVIDENCE_SQL,
                {
                    "import_id": import_id,
                    "oid": oid,
                    "ticker": plan["ticker"],
                    "event_ticker": plan["event_ticker"],
                    "period": period,
                    "open_ts": parse_instant(market.get("open_time")),
                    "settled": settled_at,
                    "cutoff": archive_cutoff,
                    "coverage": plan.get("coverage") or "incomplete",
                    "fingerprint": plan["input_fingerprint"],
                    "cutoff_inputs": {
                        "event_id": row.event_id,
                        "commence_time": _iso(row.commence_time),
                        "commence_time_source": row.commence_time_source,
                        "completed_at": _iso(row.completed_at),
                        "outcome_xmin": row.outcome_xmin,
                        "market_xmin": row.market_xmin,
                        "event_xmin": row.event_xmin,
                    },
                    "forecast_cutoff": cutoff,
                    "cutoff_refusal": cutoff_refusal,
                    "plan_forecast_cutoff": parse_instant(plan.get("forecast_cutoff")),
                    "plan_cutoff_refusal": plan.get("cutoff_refusal"),
                    "windows": [
                        {k: v for k, v in w.items() if k != "raw_body"}
                        for w in plan.get("windows") or ()
                    ],
                    "owed": list(plan.get("owed_windows") or ()),
                },
            )
        ).scalar_one()
        inserted: list[int] = []
        raced: list[PlannedPoint] = []
        for p, admission in fresh:
            window = lineage.get(p.raw_sha256) or {}
            new_id = (
                await session.execute(
                    INTERVAL_SQL,
                    {
                        "import_id": import_id,
                        "evidence_id": evidence_id,
                        "oid": oid,
                        "ticker": plan["ticker"],
                        "event_ticker": plan["event_ticker"],
                        "period": period,
                        "start": parse_instant(p.interval_start),
                        "end": parse_instant(p.interval_end),
                        "settled": settled_at,
                        "probability": p.probability,
                        "basis": p.price_basis,
                        "volume": p.volume,
                        "echoed": window.get("echoed_ticker"),
                        "sha": p.raw_sha256,
                        "retrieved": parse_instant(window.get("retrieved_at")),
                        "plan_adm": p.admission,
                        "apply_adm": admission,
                    },
                )
            ).scalar()
            if new_id is None:
                raced.append(p)  # another writer took the key since the read
            else:
                inserted.append(int(new_id))
        if raced:
            out["conflicts"].extend(
                {"outcome_id": oid, "interval_end": p.interval_end, "reason": "raced"}
                for p in raced
            )
        await session.execute(
            PROGRESS_SQL, {"ids": inserted, "oid": oid, "import_id": import_id}
        )
        await session.commit()

    out["inserted"] = len(inserted)
    out["inserted_ids"] = inserted
    async with session_factory() as session:
        back = {
            int(r.id)
            for r in (
                await session.execute(READBACK_SQL, {"import_id": import_id, "oid": oid})
            ).fetchall()
        }
    out["readback"] = "ok" if back == set(inserted) else "mismatch"
    return out


def _conflict(oid: int, planned: PlannedPoint, prior: Any) -> dict:
    return {
        "outcome_id": oid,
        "interval_end": planned.interval_end,
        "existing_id": int(prior.id),
        "existing_probability": float(prior.probability),
        "existing_basis": prior.price_basis,
        "existing_sha256": prior.raw_response_sha256,
        "planned_probability": planned.probability,
        "planned_basis": planned.price_basis,
        "planned_sha256": planned.raw_sha256,
    }


RESTORE_READ_SQL = text(
    """
    SELECT id, status, inserted_ids
    FROM kalshi_archive_imports
    WHERE import_key = :key
    """
)
RESTORE_LOCK_SQL = text(
    "SELECT id FROM kalshi_archive_imports WHERE id = :import_id FOR UPDATE"
)
RESTORE_ROWS_SQL = text("SELECT id FROM kalshi_archive_intervals WHERE import_id = :import_id")
RESTORE_DELETE_SQL = text(
    """
    DELETE FROM kalshi_archive_intervals
    WHERE import_id = :import_id AND id = ANY(:ids)
    RETURNING id
    """
)
RESTORE_EVIDENCE_SQL = text(
    """
    DELETE FROM kalshi_archive_outcome_evidence ev
    WHERE ev.import_id = :import_id
      AND NOT EXISTS (
          SELECT 1 FROM kalshi_archive_intervals k WHERE k.evidence_id = ev.id
      )
    RETURNING ev.id
    """
)
RESTORE_MARK_SQL = text(
    """
    UPDATE kalshi_archive_imports
    SET status = 'restored', restored_at = now()
    WHERE id = :import_id
    """
)


async def restore_archive_import(
    import_key: str,
    *,
    write: bool = False,
    allow_applying: bool = False,
    session_factory: Callable[[], Any] = _default_session_factory,
) -> dict:
    """Remove exactly one import's own rows. Dry-run unless ``write``."""
    result: dict = {
        "mode": "restore" if write else "dry_run",
        "import_key": import_key,
        "import_id": None,
        "would_delete": 0,
        "deleted": 0,
        "evidence_deleted": 0,
        "refused": None,
        "readback_remaining": None,
    }
    async with session_factory() as session:
        if not write:
            await session.execute(text("SET TRANSACTION READ ONLY"))
        found = (await session.execute(RESTORE_READ_SQL, {"key": import_key})).first()
        if found is None:
            result["refused"] = "import_unknown"
            return result
        import_id = int(found.id)
        result["import_id"] = import_id
        if write:
            await session.execute(RESTORE_LOCK_SQL, {"import_id": import_id})
        if found.status == "restored":
            result["refused"] = "already_restored"
            return result
        if found.status == "applying" and not allow_applying:
            result["refused"] = "import_still_applying"
            return result
        recorded = {int(i) for i in (found.inserted_ids or ())}
        actual = {
            int(r.id)
            for r in (
                await session.execute(RESTORE_ROWS_SQL, {"import_id": import_id})
            ).fetchall()
        }
        if actual != recorded:
            result["refused"] = (
                "rows_not_recorded_by_import"
                if actual - recorded
                else "recorded_rows_missing"
            )
            result["unrecorded"] = sorted(actual - recorded)[:50]
            result["missing"] = sorted(recorded - actual)[:50]
            return result
        result["would_delete"] = len(recorded)
        if not write:
            return result
        deleted = (
            await session.execute(
                RESTORE_DELETE_SQL, {"import_id": import_id, "ids": sorted(recorded)}
            )
        ).fetchall()
        if len(deleted) != len(recorded):
            await session.rollback()
            result["refused"] = "delete_count_mismatch"
            return result
        evidence = (
            await session.execute(RESTORE_EVIDENCE_SQL, {"import_id": import_id})
        ).fetchall()
        await session.execute(RESTORE_MARK_SQL, {"import_id": import_id})
        await session.commit()
        result["deleted"] = len(deleted)
        result["evidence_deleted"] = len(evidence)
    async with session_factory() as session:
        remaining = (
            await session.execute(RESTORE_ROWS_SQL, {"import_id": import_id})
        ).fetchall()
    result["readback_remaining"] = len(remaining)
    return result


COHORT_SQL = text(
    """
    SELECT fo.id AS outcome_id,
           NOT EXISTS (
               SELECT 1 FROM futures_odds_snapshots s WHERE s.outcome_id = fo.id
           ) AS zero_snapshot,
           (SELECT COUNT(*) FROM kalshi_archive_intervals k
             WHERE k.outcome_id = fo.id) AS archive_intervals,
           (SELECT COUNT(*) FROM kalshi_archive_intervals k
             WHERE k.outcome_id = fo.id
               AND k.admission_at_apply = 'forecast') AS forecast_intervals
    FROM futures_outcomes fo
    WHERE fo.id = ANY(:ids)
    ORDER BY fo.id
    """
)


async def archive_cohort(
    outcome_ids: list[int],
    *,
    session_factory: Callable[[], Any] = _default_session_factory,
) -> dict:
    """For named outcomes: zero-snapshot cohort membership vs archive history held.

    Read-only. The two populations are reported side by side and never merged:
    an outcome that gained archive intervals is STILL a zero-snapshot outcome in
    the original #683 cohort, so archive rows cannot silently shrink that count.
    """
    ids = sorted({int(i) for i in outcome_ids})[:10_000]
    async with session_factory() as session:
        await session.execute(text("SET TRANSACTION READ ONLY"))
        rows = (await session.execute(COHORT_SQL, {"ids": ids})).fetchall()
    found = [
        {
            "outcome_id": int(r.outcome_id),
            "zero_snapshot": bool(r.zero_snapshot),
            "archive_intervals": int(r.archive_intervals),
            "forecast_intervals": int(r.forecast_intervals),
        }
        for r in rows
    ]
    return {
        "asked": len(ids),
        "found": len(found),
        "zero_snapshot": sum(1 for r in found if r["zero_snapshot"]),
        "zero_snapshot_with_archive_history": sorted(
            r["outcome_id"] for r in found if r["zero_snapshot"] and r["archive_intervals"]
        ),
        "with_forecast_intervals": sorted(
            r["outcome_id"] for r in found if r["forecast_intervals"]
        ),
        "rows": found,
    }
