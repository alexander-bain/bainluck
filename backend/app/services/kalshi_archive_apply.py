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
   On a write the re-read takes ``FOR SHARE`` on the outcome, market and event
   rows inside the outcome's own transaction (bounded by the archive
   ``lock_timeout``), so those inputs cannot change between the fingerprint
   check and the commit. The fingerprint alone is a field comparison: a
   non-fingerprint column may have changed since planning and still pass.
3a. **The attended path also fences row versions.** The operator's reviewed
   input-versions document (:func:`seal_input_versions`) names, per outcome,
   the exact identity, the fingerprint and the ``xmin`` of the outcome, its
   market and its event (``null`` only when the market has no event). It is
   sealed, typed by the operator like the plan digest, and bound to the plan
   digest and to every importable outcome of the plan, so it cannot be paired
   with another plan. After the ``FOR SHARE`` locks, in the transaction that
   writes the outcome's evidence and intervals, any identity, fingerprint or
   version difference refuses that outcome (``input_identity_drift``,
   ``input_drift``, ``input_version_drift:<row>``, ``input_event_missing``)
   and nothing of it is written. Drift is never resealed here. The attended
   CLI write requires this document; without it the run is refused whole.
   Callers that pass no document keep the fingerprint-only fence
   (``input_fence: fingerprint_only`` on the receipt).
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

WHAT A RECEIPT MAY CLAIM. Every acknowledged commit is recorded in
``committed_outcomes`` the moment it returns, so a later failure (the readback,
a sibling, the wall) cannot hide rows that are already durable. A commit whose
acknowledgement never arrived (transport error, cancellation) is
``uncertain_commits`` / ``commit_in_flight``: it MAY be durable, the run stops,
and the receipt names the read-only readback that settles it. It is never
reported as nothing written, never retried, never restored automatically. A
plan that is not complete history (a stopped or partial planner run, an
outcome with owed windows, no importable point at all) is never ``applied``:
it is ``partial`` with ``incomplete_reasons``. The caller's operation wall and
progress receipt come from :mod:`app.services.kalshi_archive_bounds`.

RESTORE removes exactly the rows one import inserted, and only as they were
written. The apply reads each inserted interval back INSIDE its inserting
transaction and records its ``xmin`` (row version) and a content seal (SHA-256
over every column) in ``inserted_seals``; evidence rows record their ``xmin``
in ``evidence_versions``. A restore locks the import and every one of its rows
(``FOR UPDATE``, so a concurrent writer waits or has already committed), then
refuses unless the rows carrying its ``import_id`` are exactly its recorded ids
AND each row's version and seal still match. A row changed after the import
(a corrected value, rewritten lineage, even an identical-content UPDATE) is
therefore never deleted by it. The delete runs only under those locks, so
nothing can change between the check and the delete. There is no broad delete
and no force mode.
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

#: Write mode: the same identity, locked for the outcome's own transaction. The
#: event is locked by a second statement because ``FOR SHARE`` cannot reach the
#: nullable side of the outer join.
CURRENT_INPUT_LOCK_SQL = """
    SELECT fo.id AS outcome_id,
           fo.external_id AS ticker,
           fm.external_id AS event_ticker,
           fo.market_id AS market_id,
           fm.event_id AS event_id,
           fo.resolution_source AS resolution_source,
           fo.xmin::text AS outcome_xmin,
           fm.xmin::text AS market_xmin
    FROM futures_outcomes fo
    JOIN futures_markets fm ON fm.id = fo.market_id
    WHERE fo.id = :oid AND fm.source = 'kalshi'
    FOR SHARE OF fo, fm
"""
EVENT_LOCK_SQL = """
    SELECT e.commence_time AS commence_time,
           e.commence_time_source AS commence_time_source,
           e.created_at AS created_at,
           e.completed_at AS completed_at,
           e.xmin::text AS event_xmin
    FROM events e
    WHERE e.id = :eid
    FOR SHARE
"""

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
    RETURNING id, xmin::text AS version
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
        outcome_ids = array_append(outcome_ids, CAST(:oid AS integer)),
        inserted_seals = inserted_seals || :seals,
        evidence_versions = evidence_versions || :evidence
    WHERE id = :import_id AND status = 'applying'
    """
).bindparams(bindparam("seals", type_=JSONB), bindparam("evidence", type_=JSONB))

#: Every stored column of an interval, in seal order. The seal is computed from
#: the row AS STORED (read back), never from the values we meant to write.
SEAL_COLUMNS = (
    "id",
    "import_id",
    "evidence_id",
    "outcome_id",
    "market_ticker",
    "event_ticker",
    "period_minutes",
    "interval_start",
    "interval_end",
    "venue_settlement_ts",
    "probability",
    "price_basis",
    "volume",
    "echoed_ticker",
    "raw_response_sha256",
    "retrieved_at",
    "admission_at_plan",
    "admission_at_apply",
    "created_at",
)
_SEAL_SELECT = ", ".join(SEAL_COLUMNS) + ", xmin::text AS version"
SEAL_READ_SQL = text(
    f"SELECT {_SEAL_SELECT} FROM kalshi_archive_intervals WHERE id = ANY(:ids)"
)


def row_seal(row: Any) -> str:
    """SHA-256 over :data:`SEAL_COLUMNS` of a stored interval row."""
    import hashlib
    from decimal import Decimal

    def canon(v: Any) -> Any:
        if hasattr(v, "isoformat"):
            return parse_instant(v).isoformat()
        if isinstance(v, (Decimal, float)):
            return format(Decimal(str(v)).normalize(), "f")
        return v

    blob = json.dumps(
        [canon(getattr(row, c)) for c in SEAL_COLUMNS], separators=(",", ":")
    )
    return hashlib.sha256(blob.encode()).hexdigest()

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


class CommitUnacknowledged(Exception):
    """A COMMIT was sent and its answer never arrived. Its rows MAY be durable."""

    def __init__(self, what: dict):
        super().__init__(f"commit_unacknowledged:{what.get('step')}")
        self.what = what


def _default_session_factory():
    """Every connection carries the archive statement/lock bounds (and proves it)."""
    from app.services.kalshi_archive_bounds import archive_session

    return archive_session()


async def _commit(session: Any, ledger: dict, what: dict) -> None:
    """Commit, recording what is at stake until the server's answer arrives.

    ``ledger["commit_in_flight"]`` names the step while the COMMIT is out; a
    cancellation leaves it set, which is exactly what the caller reports. A
    transport error moves it to ``uncertain_commits`` and raises
    :class:`CommitUnacknowledged`: the outcome of that COMMIT is unknown.
    """
    ledger["commit_in_flight"] = what
    try:
        await session.commit()
    except Exception as e:
        ledger["commit_in_flight"] = None
        ledger.setdefault("uncertain_commits", []).append(
            {**what, "error": f"{type(e).__name__}: {str(e)[:160]}"}
        )
        raise CommitUnacknowledged(what) from e
    ledger["commit_in_flight"] = None


def _uncertain(ledger: dict, step: str, outcome_id: Optional[int] = None) -> bool:
    """Did ``step`` leave an unacknowledged COMMIT? Read from the ledger, not the
    exception: a session's own rollback on a dead connection can raise something
    else on top of :class:`CommitUnacknowledged`."""
    return any(
        c.get("step") == step
        and (outcome_id is None or c.get("outcome_id") == outcome_id)
        for c in ledger.get("uncertain_commits") or ()
    )


def _sync(wall: Any, phase: str):
    """The wall's synchronous-phase guard, or nothing when no wall was given."""
    from contextlib import nullcontext

    return nullcontext() if wall is None else wall.sync_phase(phase)


def _phase(ledger: dict, phase: str) -> None:
    ledger["phase"] = phase


def plan_completeness(report: dict, plans: list[dict]) -> list[str]:
    """Why this plan is NOT complete history for what it would import; ``[]`` if it is.

    The importer accepts a subset plan, but a subset is never sold as the
    whole: a planner run that stopped or owed anything, an imported outcome
    with owed windows, or a plan with no importable point is reported here.
    """
    reasons: list[str] = []
    if report.get("terminal") != "complete":
        reasons.append(f"plan_terminal:{report.get('terminal')}")
    for key in ("owed_ids", "incomplete_ids", "errors"):
        if report.get(key):
            reasons.append(f"plan_{key}")
    if report.get("held_outcome"):
        reasons.append("plan_held_outcome")
    if report.get("budget_stop"):
        reasons.append(f"plan_budget_stop:{report.get('budget_stop')}")
    for plan in plans:
        if plan.get("coverage") != "complete" or plan.get("owed_windows"):
            reasons.append(f"outcome_coverage_incomplete:{plan.get('outcome_id')}")
    if not plans:
        reasons.append("plan_has_no_importable_points")
    return reasons


def _points(plan: dict) -> list[PlannedPoint]:
    return [PlannedPoint(**p) for p in plan.get("points") or ()]


# ── the attended input fence: reviewed identity + row versions ────────────

INPUT_VERSIONS_KIND = "kalshi_archive_input_versions"
INPUT_VERSIONS_VERSION = 1
#: One reviewed outcome, exactly these keys. The three ``*_xmin`` are the
#: ``xmin::text`` row versions as the operator's reviewed read returned them.
INPUT_VERSION_FIELDS = (
    "outcome_id",
    "ticker",
    "event_ticker",
    "market_id",
    "event_id",
    "input_fingerprint",
    "outcome_xmin",
    "market_xmin",
    "event_xmin",
)
_IDENTITY_FIELDS = ("outcome_id", "ticker", "event_ticker", "market_id", "event_id")


def input_versions_digest(doc: dict) -> str:
    """SHA-256 over the document, everything but its own ``digest``."""
    import hashlib

    blob = json.dumps(
        {k: v for k, v in doc.items() if k != "digest"},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(blob.encode()).hexdigest()


def seal_input_versions(plan_digest_value: str, outcomes: list[dict]) -> dict:
    """The document an operator reviews and types the digest of. Pure, no reads."""
    doc = {
        "kind": INPUT_VERSIONS_KIND,
        "version": INPUT_VERSIONS_VERSION,
        "plan_digest": plan_digest_value,
        "outcomes": [{k: o.get(k) for k in INPUT_VERSION_FIELDS} for o in outcomes],
    }
    doc["digest"] = input_versions_digest(doc)
    return doc


def _is_id(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and v > 0


def _is_xid(v: Any) -> bool:
    return isinstance(v, str) and v.isascii() and v.isdigit()


def _entry_malformed(entry: Any) -> Optional[str]:
    if not isinstance(entry, dict) or set(entry) != set(INPUT_VERSION_FIELDS):
        return "keys"
    if not _is_id(entry["outcome_id"]) or not _is_id(entry["market_id"]):
        return "ids"
    if not (isinstance(entry["ticker"], str) and entry["ticker"]):
        return "ticker"
    if not (isinstance(entry["event_ticker"], str) and entry["event_ticker"]):
        return "event_ticker"
    fp = entry["input_fingerprint"]
    if not (
        isinstance(fp, str) and len(fp) == 64 and all(c in "0123456789abcdef" for c in fp)
    ):
        return "input_fingerprint"
    if not _is_xid(entry["outcome_xmin"]) or not _is_xid(entry["market_xmin"]):
        return "xmin"
    # An absent event is stated, never a wildcard: no event id ⇔ no event version.
    if entry["event_id"] is None:
        if entry["event_xmin"] is not None:
            return "event_xmin_without_event"
    elif not _is_id(entry["event_id"]) or not _is_xid(entry["event_xmin"]):
        return "event"
    return None


def verify_input_versions(
    doc: Any, expected_input_digest: Optional[str], plans: list[dict], plan_digest_value: str
) -> dict[int, dict]:
    """The reviewed expectation for every importable outcome, once the document is proven.

    Raises :class:`PlanRefused` unless the document is well formed, sealed,
    typed by the operator, bound to THIS plan's digest, and names exactly the
    plan's importable outcomes with the plan's own identity and fingerprint.
    """
    if doc is None or not expected_input_digest:
        raise PlanRefused("input_versions_missing")
    if (
        not isinstance(doc, dict)
        or doc.get("kind") != INPUT_VERSIONS_KIND
        or doc.get("version") != INPUT_VERSIONS_VERSION
        or set(doc) != {"kind", "version", "plan_digest", "outcomes", "digest"}
        or not isinstance(doc.get("outcomes"), list)
    ):
        raise PlanRefused("input_versions_malformed")
    recomputed = input_versions_digest(doc)
    if doc.get("digest") != recomputed:
        raise PlanRefused("input_versions_digest_mismatch")
    if expected_input_digest != recomputed:
        raise PlanRefused("expected_input_digest_mismatch")
    if doc.get("plan_digest") != plan_digest_value:
        raise PlanRefused("input_versions_plan_mismatch")
    expected: dict[int, dict] = {}
    for entry in doc["outcomes"]:
        why = _entry_malformed(entry)
        if why:
            raise PlanRefused(f"input_versions_malformed:{why}")
        if entry["outcome_id"] in expected:
            raise PlanRefused("input_versions_duplicate_outcome")
        expected[entry["outcome_id"]] = entry
    planned = [int(plan["outcome_id"]) for plan in plans]
    if len(set(planned)) != len(planned) or set(planned) != set(expected):
        raise PlanRefused("input_versions_outcomes_mismatch")
    for plan in plans:
        entry = expected[int(plan["outcome_id"])]
        if (
            entry["ticker"] != plan.get("ticker")
            or entry["event_ticker"] != plan.get("event_ticker")
            or entry["input_fingerprint"] != plan.get("input_fingerprint")
        ):
            raise PlanRefused(f"input_versions_identity_mismatch:{entry['outcome_id']}")
    return expected


def _observed_versions(row: Any) -> dict:
    return {
        "outcome_id": row.outcome_id,
        "ticker": row.ticker,
        "event_ticker": row.event_ticker,
        "market_id": row.market_id,
        "event_id": row.event_id,
        "has_event": bool(row.has_event),
        "outcome_xmin": row.outcome_xmin,
        "market_xmin": row.market_xmin,
        "event_xmin": row.event_xmin,
    }


def input_version_refusal(row: Any, expected: dict) -> Optional[str]:
    """``None`` when the stored row is exactly the reviewed identity AND versions.

    Identity first (an absent event is part of it: a ``null`` expectation is
    never a wildcard for a present event, and a reviewed event must still be
    there), then the fingerprint (the reviewed one, which the document proved
    equal to the plan's), then the versions: an outcome, market or event row
    rewritten in ANY column since review has a different ``xmin`` and is
    refused, whatever its fingerprint says.
    """
    if any(getattr(row, k) != expected[k] for k in _IDENTITY_FIELDS):
        return "input_identity_drift"
    if expected["event_id"] is None:
        if row.has_event or row.event_xmin is not None:
            return "input_identity_drift"
    elif not row.has_event:
        return "input_event_missing"
    if input_fingerprint(row) != expected["input_fingerprint"]:
        return "input_drift"
    if row.outcome_xmin != expected["outcome_xmin"]:
        return "input_version_drift:outcome"
    if row.market_xmin != expected["market_xmin"]:
        return "input_version_drift:market"
    if row.event_xmin != expected["event_xmin"]:
        return "input_version_drift:event"
    return None


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
    max_outcomes: Optional[int] = None,
    max_points: Optional[int] = None,
    wall: Any = None,
    progress: Optional[dict] = None,
    input_versions: Optional[dict] = None,
    expected_input_digest: Optional[str] = None,
    require_input_versions: bool = False,
) -> dict:
    """Dry-run (default) or apply one reviewed plan. See the module doc.

    ``max_outcomes`` / ``max_points`` refuse a plan larger than the reviewed
    invocation named. ``wall`` (an
    :class:`~app.services.kalshi_archive_bounds.OperationWall`) interrupts the
    synchronous validation; the caller cancels the async work at the wall.
    ``progress``, when given, IS the receipt: it is filled as the run goes, so
    a caller whose wall expired still holds every acknowledged commit, the
    commit in flight, and the phase it stopped in.

    ``input_versions`` + ``expected_input_digest`` turn on the attended
    row-version fence (module doc, 3a). ``require_input_versions`` (the
    attended CLI write) refuses the whole plan when they are absent, so the
    attended path can never fall back to the fingerprint-only fence.
    """
    result: dict = progress if progress is not None else {}
    result.update(
        {
            "mode": "apply" if write else "dry_run",
            "phase": "verify_plan",
            "plan_digest": None,
            "import_key": None,
            "import_id": None,
            "archive_cutoff": None,
            "outcomes": [],
            "committed_outcomes": [],
            "commit_in_flight": None,
            "uncertain_commits": [],
            "import_row": None,
            "inserted": 0,
            "identical": 0,
            "conflicts": [],
            "refused": [],
            "errors": [],
            "demoted_to_reader_only": 0,
            "incomplete_reasons": [],
            "status": None,
            "input_fence": None,
        }
    )
    with _sync(wall, "verify_plan"):
        plans = verify_plan_document(report, expected_digest)
        points_total = sum(len(importable(_points(plan))) for plan in plans)
    if max_outcomes is not None and len(plans) > int(max_outcomes):
        raise PlanRefused(f"plan_exceeds_max_outcomes:{len(plans)}>{int(max_outcomes)}")
    if max_points is not None and points_total > int(max_points):
        raise PlanRefused(f"plan_exceeds_max_points:{points_total}>{int(max_points)}")
    expected_inputs: Optional[dict[int, dict]] = None
    if require_input_versions or input_versions is not None or expected_input_digest:
        with _sync(wall, "verify_input_versions"):
            expected_inputs = verify_input_versions(
                input_versions, expected_input_digest, plans, report["plan_digest"]
            )
        result["input_fence"] = "rowversion"
        result["input_versions_digest"] = input_versions["digest"]
    else:
        result["input_fence"] = "fingerprint_only"
    archive_cutoff = parse_instant(report["archive_cutoff"])
    result["plan_digest"] = report["plan_digest"]
    result["archive_cutoff"] = archive_cutoff.isoformat()
    result["planned_outcomes"] = len(plans)
    result["planned_points"] = points_total
    result["incomplete_reasons"] = plan_completeness(report, plans)
    _phase(result, "store_check")
    async with session_factory() as session:
        await session.execute(text("SET TRANSACTION READ ONLY"))
        present = (await session.execute(text(ARCHIVE_STORE_PRESENT_SQL))).scalar()
    if not present:
        raise PlanRefused("archive_store_absent")
    key = import_key or uuid.uuid4().hex
    result["import_key"] = key if write else None
    import_id: Optional[int] = None
    stopped: Optional[str] = None
    if write:
        _phase(result, "create_import")
        # The key is the receipt's handle BEFORE the row exists: if this commit
        # is never acknowledged, the import row may or may not be there.
        result["import_row"] = "unknown"
        try:
            async with session_factory() as session:
                import_id = (
                    await session.execute(
                        CREATE_IMPORT_SQL,
                        {
                            "key": key,
                            "digest": report["plan_digest"],
                            "cutoff": archive_cutoff,
                            "report": json.dumps(
                                {
                                    "outcomes_planned": len(plans),
                                    "input_fence": result["input_fence"],
                                    "input_versions_digest": result.get(
                                        "input_versions_digest"
                                    ),
                                }
                            ),
                        },
                    )
                ).scalar_one()
                await _commit(
                    session, result, {"step": "create_import", "import_key": key}
                )
        except Exception:
            if not _uncertain(result, "create_import"):
                raise  # no COMMIT was sent: nothing exists; the plan is refused whole
            stopped = "commit_unacknowledged:create_import"
        if stopped is None:
            result["import_id"] = import_id
            result["import_row"] = "applying"

    for plan in plans if stopped is None else ():
        oid = int(plan["outcome_id"])
        _phase(result, f"outcome:{oid}")
        try:
            outcome = await _apply_outcome(
                plan,
                archive_cutoff=archive_cutoff,
                write=write,
                import_id=import_id,
                session_factory=session_factory,
                ledger=result,
                wall=wall,
                expected_input=(
                    None if expected_inputs is None else expected_inputs[oid]
                ),
            )
        except Exception as e:  # one outcome never wipes the pass (gotcha #42)
            if _uncertain(result, "outcome", oid):
                # Its rows may be durable: stop, never call that "nothing written".
                stopped = f"commit_unacknowledged:{oid}"
                break
            logger.warning("archive import: outcome %s failed: %s", oid, str(e)[:200])
            committed = next(
                (c for c in result["committed_outcomes"] if c["outcome_id"] == oid),
                None,
            )
            result["errors"].append(
                {
                    "outcome_id": oid,
                    "error": str(e)[:200],
                    # Acknowledged before the failure ⇒ durable; else no COMMIT
                    # was sent for it and the server rolled it back.
                    "committed": committed is not None,
                    "inserted_ids": committed["inserted_ids"] if committed else [],
                }
            )
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

    clean = not (
        result["refused"]
        or result["errors"]
        or result["conflicts"]
        or stopped
        or result["incomplete_reasons"]
    )
    result["status"] = "applied" if clean else "partial"
    if stopped:
        result["stopped"] = stopped
    durable = {c["outcome_id"]: c for c in result["committed_outcomes"]}
    result["gained_history_outcome_ids"] = sorted(
        oid for oid, c in durable.items() if c["inserted_ids"]
    )
    result["zero_snapshot_cohort_gained_ids"] = sorted(
        oid
        for oid, c in durable.items()
        if c["inserted_ids"] and c.get("live_snapshots_at_plan") == 0
    )
    if result["uncertain_commits"]:
        result["readback_owed"] = _readback_owed(result)
    if write and import_id is not None and not stopped:
        _phase(result, "finish")
        try:
            async with session_factory() as session:
                await session.execute(
                    FINISH_SQL,
                    {
                        "status": result["status"],
                        "report": _summary(result),
                        "import_id": import_id,
                    },
                )
                await _commit(
                    session, result, {"step": "finish", "import_id": import_id}
                )
        except Exception as e:
            # The rows are as committed_outcomes says; only the import row's
            # final status is in doubt (or still 'applying' if no COMMIT left).
            result["import_row"] = (
                "unknown" if _uncertain(result, "finish") else "applying"
            )
            result["finish_error"] = f"{type(e).__name__}: {str(e)[:160]}"
            result["status"] = "partial"
            result["readback_owed"] = _readback_owed(result)
        else:
            result["import_row"] = result["status"]
    _phase(result, "done")
    return result


def _readback_owed(result: dict) -> dict:
    """The read-only commands that settle an unacknowledged commit. Never automatic."""
    key = result.get("import_key")
    oids = sorted(
        {int(c["outcome_id"]) for c in result.get("uncertain_commits") or () if c.get("outcome_id")}
        | {int(c["outcome_id"]) for c in result.get("committed_outcomes") or ()}
    )
    return {
        "durability": "unknown",
        "import_key": key,
        "commands": [
            f"scripts/kalshi_archive_import.py restore --import-key {key} --deadline <s>",
            "scripts/kalshi_archive_import.py cohort --outcome-ids "
            + (",".join(str(i) for i in oids) or "<ids>")
            + " --deadline <s>",
        ],
        "never": ["retry the apply", "restore automatically", "assume zero rows"],
    }


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
            "incomplete_reasons",
            "input_fence",
        )
    } | ({"stopped": result["stopped"]} if result.get("stopped") else {})


async def _apply_outcome(
    plan: dict,
    *,
    archive_cutoff,
    write: bool,
    import_id: Optional[int],
    session_factory: Callable[[], Any],
    ledger: Optional[dict] = None,
    wall: Any = None,
    expected_input: Optional[dict] = None,
) -> dict:
    ledger = {} if ledger is None else ledger
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
    with _sync(wall, f"rederive:{oid}"):
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
        else:
            row = await _locked_input(session, oid)
        if row is None:
            out["refused"] = "outcome_missing"
            return out
        if expected_input is not None:
            # Under the locks just taken, in the transaction that would write:
            # a refusal returns before any evidence or interval exists, and the
            # rollback releases the locks.
            why = input_version_refusal(row, expected_input)
            if why:
                out["refused"] = why
                out["input_fence"] = {
                    "expected": {
                        k: v for k, v in expected_input.items() if k != "input_fingerprint"
                    },
                    "observed": _observed_versions(row),
                }
                return out
        elif input_fingerprint(row) != plan.get("input_fingerprint"):
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
        evidence = (
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
        ).one()
        evidence_id, evidence_version = int(evidence.id), evidence.version
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
        seals = {
            str(int(r.id)): [r.version, row_seal(r)]
            for r in (await session.execute(SEAL_READ_SQL, {"ids": inserted})).fetchall()
        }
        await session.execute(
            PROGRESS_SQL,
            {
                "ids": inserted,
                "oid": oid,
                "import_id": import_id,
                "seals": seals,
                "evidence": {str(evidence_id): evidence_version},
            },
        )
        await _commit(
            session,
            ledger,
            {
                "step": "outcome",
                "outcome_id": oid,
                "import_id": import_id,
                "evidence_id": evidence_id,
                "inserted_ids": list(inserted),
            },
        )
        # Durable from here, whatever happens next (readback, sibling, wall).
        ledger.setdefault("committed_outcomes", []).append(
            {
                "outcome_id": oid,
                "evidence_id": evidence_id,
                "inserted_ids": list(inserted),
                "live_snapshots_at_plan": out["live_snapshots_at_plan"],
            }
        )

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


async def _locked_input(session: Any, oid: int) -> Optional[SimpleNamespace]:
    """The outcome's current identity, row-locked ``FOR SHARE`` until this commit.

    Same fields as :data:`CURRENT_INPUT_SQL`, so the fingerprint is computed
    identically. A writer already holding one of these rows makes this wait at
    most the archive ``lock_timeout`` and then fail the outcome before any row
    is written.
    """
    head = (await session.execute(text(CURRENT_INPUT_LOCK_SQL), {"oid": oid})).first()
    if head is None:
        return None
    event = None
    if head.event_id is not None:
        event = (
            await session.execute(text(EVENT_LOCK_SQL), {"eid": head.event_id})
        ).first()
    return SimpleNamespace(
        outcome_id=head.outcome_id,
        ticker=head.ticker,
        event_ticker=head.event_ticker,
        market_id=head.market_id,
        event_id=head.event_id,
        resolution_source=head.resolution_source,
        has_event=event is not None,
        commence_time=getattr(event, "commence_time", None),
        commence_time_source=getattr(event, "commence_time_source", None),
        created_at=getattr(event, "created_at", None),
        completed_at=getattr(event, "completed_at", None),
        outcome_xmin=head.outcome_xmin,
        market_xmin=head.market_xmin,
        event_xmin=getattr(event, "event_xmin", None),
    )


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
    SELECT id, status, inserted_ids, inserted_seals, evidence_versions
    FROM kalshi_archive_imports
    WHERE import_key = :key
    """
)
RESTORE_LOCK_SQL = text(
    "SELECT id FROM kalshi_archive_imports WHERE id = :import_id FOR UPDATE"
)
RESTORE_ROWS_SQL = text(
    f"SELECT {_SEAL_SELECT} FROM kalshi_archive_intervals WHERE import_id = :import_id"
)
RESTORE_ROWS_LOCK_SQL = text(
    f"SELECT {_SEAL_SELECT} FROM kalshi_archive_intervals"
    " WHERE import_id = :import_id ORDER BY id FOR UPDATE"
)
RESTORE_EVIDENCE_ROWS_SQL = text(
    "SELECT id, xmin::text AS version FROM kalshi_archive_outcome_evidence"
    " WHERE import_id = :import_id ORDER BY id"
)
RESTORE_EVIDENCE_LOCK_SQL = text(
    "SELECT id, xmin::text AS version FROM kalshi_archive_outcome_evidence"
    " WHERE import_id = :import_id ORDER BY id FOR UPDATE"
)
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
      AND ev.id = ANY(:ids)
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


def restore_drift(found: Any, rows: list, evidence: list) -> Optional[dict]:
    """``None`` when the stored rows are exactly what this import wrote; else why not."""
    recorded = {int(i) for i in (found.inserted_ids or ())}
    seals = {int(k): v for k, v in (found.inserted_seals or {}).items()}
    versions = {int(k): v for k, v in (found.evidence_versions or {}).items()}
    actual = {int(r.id) for r in rows}
    if actual != recorded:
        return {
            "reason": (
                "rows_not_recorded_by_import"
                if actual - recorded
                else "recorded_rows_missing"
            ),
            "unrecorded": sorted(actual - recorded)[:50],
            "missing": sorted(recorded - actual)[:50],
        }
    if set(seals) != recorded:
        return {"reason": "seals_do_not_cover_recorded_rows"}
    changed_version = [int(r.id) for r in rows if seals[int(r.id)][0] != r.version]
    changed_content = [int(r.id) for r in rows if seals[int(r.id)][1] != row_seal(r)]
    if changed_content:
        return {"reason": "row_content_changed_since_import", "ids": changed_content[:50]}
    if changed_version:
        return {"reason": "row_version_changed_since_import", "ids": changed_version[:50]}
    if {int(e.id): e.version for e in evidence} != versions:
        return {"reason": "evidence_changed_since_import"}
    return None


async def restore_archive_import(
    import_key: str,
    *,
    write: bool = False,
    allow_applying: bool = False,
    session_factory: Callable[[], Any] = _default_session_factory,
    progress: Optional[dict] = None,
) -> dict:
    """Remove exactly one import's own, unchanged rows. Dry-run unless ``write``.

    ``progress``, when given, IS the receipt (see :func:`apply_archive_plan`):
    a restore whose COMMIT was never acknowledged reports ``commit_in_flight``
    or ``uncertain_commits`` and ``deleted: "unknown"``, never 0.
    """
    result: dict = progress if progress is not None else {}
    result.update(
        {
            "mode": "restore" if write else "dry_run",
            "phase": "read_import",
            "import_key": import_key,
            "import_id": None,
            "would_delete": 0,
            "deleted": 0,
            "evidence_deleted": 0,
            "refused": None,
            "readback_remaining": None,
            "commit_in_flight": None,
            "uncertain_commits": [],
        }
    )
    try:
        done = await _restore_body(
            import_key,
            write=write,
            allow_applying=allow_applying,
            session_factory=session_factory,
            result=result,
        )
    except Exception:
        if not _uncertain(result, "restore"):
            raise  # no COMMIT was sent: nothing was deleted
        result["refused"] = "commit_unacknowledged"
        result["deleted"] = "unknown"
        result["readback_owed"] = {
            "durability": "unknown",
            "commands": [
                f"scripts/kalshi_archive_import.py restore --import-key {import_key} --deadline <s>"
            ],
            "never": ["retry the restore", "assume nothing was deleted"],
        }
        return result
    if not done:
        return result
    import_id = result["import_id"]
    result["phase"] = "readback"
    async with session_factory() as session:
        remaining = (
            await session.execute(RESTORE_ROWS_SQL, {"import_id": import_id})
        ).fetchall()
    result["readback_remaining"] = len(remaining)
    result["phase"] = "done"
    return result


async def _restore_body(
    import_key: str,
    *,
    write: bool,
    allow_applying: bool,
    session_factory: Callable[[], Any],
    result: dict,
) -> bool:
    """The locked check-and-delete. ``True`` when the readback should follow."""
    async with session_factory() as session:
        if not write:
            await session.execute(text("SET TRANSACTION READ ONLY"))
        found = (await session.execute(RESTORE_READ_SQL, {"key": import_key})).first()
        if found is None:
            result["refused"] = "import_unknown"
            return False
        import_id = int(found.id)
        result["import_id"] = import_id
        if write:
            await session.execute(RESTORE_LOCK_SQL, {"import_id": import_id})
            # Re-read under the lock: the record may have moved while we waited.
            found = (await session.execute(RESTORE_READ_SQL, {"key": import_key})).first()
        if found.status == "restored":
            result["refused"] = "already_restored"
            return False
        if found.status == "applying" and not allow_applying:
            result["refused"] = "import_still_applying"
            return False
        params = {"import_id": import_id}
        rows = (
            await session.execute(
                RESTORE_ROWS_LOCK_SQL if write else RESTORE_ROWS_SQL, params
            )
        ).fetchall()
        evidence = (
            await session.execute(
                RESTORE_EVIDENCE_LOCK_SQL if write else RESTORE_EVIDENCE_ROWS_SQL, params
            )
        ).fetchall()
        drift = restore_drift(found, rows, evidence)
        if drift is not None:
            result["refused"] = drift.pop("reason")
            result.update(drift)
            return False
        recorded = sorted(int(r.id) for r in rows)
        result["would_delete"] = len(recorded)
        if not write:
            return False
        deleted = (
            await session.execute(
                RESTORE_DELETE_SQL, {"import_id": import_id, "ids": recorded}
            )
        ).fetchall()
        if len(deleted) != len(recorded):
            await session.rollback()
            result["refused"] = "delete_count_mismatch"
            return False
        removed_evidence = (
            await session.execute(
                RESTORE_EVIDENCE_SQL,
                {"import_id": import_id, "ids": [int(e.id) for e in evidence]},
            )
        ).fetchall()
        await session.execute(RESTORE_MARK_SQL, {"import_id": import_id})
        result["phase"] = "commit"
        result["deleted"] = "unknown"
        await _commit(
            session,
            result,
            {"step": "restore", "import_id": import_id, "would_delete_ids": recorded},
        )
        result["deleted"] = len(deleted)
        result["evidence_deleted"] = len(removed_evidence)
    return True


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
