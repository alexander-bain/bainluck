"""Precompute heavy admin health endpoints into Redis (L2-90 async-cache).

Two admin reads — ``/api/admin/audit/all`` and
``/api/admin/prediction-markets/link-rate`` — computed ~25s synchronously and
were intermittently 503ing at the 30s router limit under load (the same disease
``/api/calibration`` had). These tasks compute the payloads on the background
worker and cache them in Redis so the GET handlers serve instantly. The routes
still fall back to computing inline on a cold cache or ``?bust=1``, so nothing
depends on the task having run — the beat just keeps the cache warm.

Redis keys / TTL are shared with the routes:
- ``bainluck:admin:audit_all``        (ex=3600)
- ``bainluck:admin:link_rate``        (ex=3600)
- ``bainluck:admin:matured_linkage``  (ex=3600)  # Queue #220/221 Item 2
- ``bainluck:admin:event_source_coverage:v1``     # #847, see the section at the end
- ``bainluck:admin:schedule_accuracy:14d:v1``     # #847, the last section

The #847 event-source-coverage section is different from the three above in two
ways that matter: its GET is CACHE-ONLY (no inline fallback, ever), and its
producer is deliberately INERT — implemented and tested, but registered as no
task, scheduled by no beat and called by nothing. The #847 14-day sport-card
producer in the last section is inert in the same way.
"""

import asyncio
import json
import logging
import math
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

_ADMIN_HEALTH_CACHE_TTL = 3600  # 1h — generous so a few skipped beats never empty it


async def _precompute_admin_audit_all():
    """Compute the all-grids matching audit and cache it in Redis."""
    from app.routes.admin_data_quality import _compute_audit_all_grids
    from app.tasks.redis_state import get_redis_client

    payload = await _compute_audit_all_grids()
    rc = get_redis_client()
    rc.set(
        "bainluck:admin:audit_all",
        json.dumps(payload),
        ex=_ADMIN_HEALTH_CACHE_TTL,
    )
    logger.info(
        "Cached admin audit/all in Redis (avg_score=%s)",
        payload.get("avg_score"),
    )
    return {"status": "ok", "avg_score": payload.get("avg_score")}


async def _precompute_admin_link_rate():
    """Compute the prediction-market link-rate and cache it in Redis."""
    from app.routes.admin_matching import _compute_link_rate
    from app.tasks.base import get_task_session
    from app.tasks.redis_state import get_redis_client

    async with get_task_session() as db:
        # Runs off the request path (soft_time_limit=120s), so give the compute
        # a generous per-query statement_timeout rather than the route's tight
        # 20s router-limit budget (Queue #250 Item 3c).
        payload = await _compute_link_rate(db, stmt_timeout_s=90)

    rc = get_redis_client()
    rc.set(
        "bainluck:admin:link_rate",
        json.dumps(payload),
        ex=_ADMIN_HEALTH_CACHE_TTL,
    )
    overall = payload.get("overall", {})
    logger.info(
        "Cached admin link-rate in Redis (link_rate_pct=%s, total=%s)",
        overall.get("link_rate_pct"),
        overall.get("total_game_markets"),
    )
    return {"status": "ok", "link_rate_pct": overall.get("link_rate_pct")}


async def _precompute_admin_matured_linkage():
    """Compute the matured-linkage metric and cache it in Redis (Item 2)."""
    from app.routes.admin_matching import _compute_matured_linkage
    from app.tasks.base import get_task_session
    from app.tasks.redis_state import get_redis_client

    async with get_task_session() as db:
        payload = await _compute_matured_linkage(db)

    rc = get_redis_client()
    rc.set(
        "bainluck:admin:matured_linkage",
        json.dumps(payload),
        ex=_ADMIN_HEALTH_CACHE_TTL,
    )
    logger.info(
        "Cached admin matured-linkage in Redis (headline_pct=%s, phantom=%s, checkable=%s)",
        payload.get("headline_pct"),
        payload.get("phantom"),
        payload.get("checkable_pairs"),
    )
    return {"status": "ok", "headline_pct": payload.get("headline_pct")}


# ---------------------------------------------------------------------------
# #847 — event-source coverage for the Correctness Console, from saved evidence.
#
# The console must open without starting the live dashboard's coverage query,
# so the GET reads ONE key and nothing else: no SQL, no session, no producer,
# no enqueue, no cache write, no dashboard fallback. A cold or broken cache is
# reported as exactly that — never filled in on the request path.
#
# THE PRODUCER IS INERT. ``_precompute_admin_event_source_coverage`` is not a
# Celery task, is in no beat schedule and has no caller. Running it against
# production needs its own admission (statement cost, cadence, quiet window,
# and a single publisher — nothing here stops two overlapping runs from racing
# their SETs). Until then only fake sessions and fake Redis ever execute it.
#
# Freshness is judged from the OBSERVATION, never from when the envelope was
# written or read: fresh for 1800 s from ``observation_started_at``, usable
# until that same start + 3600 s. A later failed run keeps the earlier
# observation byte-for-byte with its original ``retained_until`` — a recent
# error is not new evidence and cannot extend old evidence.
# ---------------------------------------------------------------------------

EVENT_SOURCE_COVERAGE_CACHE_KEY = "bainluck:admin:event_source_coverage:v1"
EVENT_SOURCE_COVERAGE_SCHEMA_VERSION = 1
EVENT_SOURCE_COVERAGE_FRESH_FOR_SECONDS = 1800
EVENT_SOURCE_COVERAGE_RETAIN_SECONDS = _ADMIN_HEALTH_CACHE_TTL
# The accepted semantics of the helper (#847 union fix). A REFERENCE: it says
# which query the numbers mean, never which release produced them.
EVENT_SOURCE_COVERAGE_ACCEPTED_REFERENCE = "9ec74723560809a09674872b534376cca72d0a41"
# The cache reader's whole share of the console's 3 s page budget: client
# construction, pool wait, connect, health-check PING, GET and its retry. The
# request-path client below still carries the default 5 s CONNECT timeout, so
# its own socket bounds cannot keep a read under budget — this deadline does.
EVENT_SOURCE_COVERAGE_READ_DEADLINE_S = 1.0

COVERAGE_SOURCE_KEYS = (
    "odds_api", "espn", "statpal", "espn_wp", "model", "mlb", "kalshi", "polymarket",
)
_COVERAGE_ROW_KEYS = frozenset({"sport", "total", "live", "expected_sources", *COVERAGE_SOURCE_KEYS})
_COVERAGE_ROWS_SCOPE = "all sports returned by the accepted helper"
_COVERAGE_ERROR_KINDS = frozenset({
    "statement_timeout", "query_error", "malformed_result",
    "provenance_error", "cache_read_error", "cache_publish_error",
})
_SAFE_CODE = re.compile(r"^[a-z0-9_]{1,64}$")
_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")

# Window provenance, read in the SAME transaction as the helper so the bounds
# are exactly the ones its NOW() used (transaction_timestamp() is NOW()).
_COVERAGE_WINDOW_SQL = """
SELECT transaction_timestamp() AS window_anchor,
       transaction_timestamp() - INTERVAL '7 days' AS window_start,
       transaction_timestamp() + INTERVAL '2 days' AS window_end,
       current_setting('TimeZone') AS database_timezone,
       current_setting('transaction_isolation') AS transaction_isolation
"""


class CoverageEnvelopeInvalid(ValueError):
    """A stored envelope that cannot be used. ``state`` is malformed or partial."""

    def __init__(self, state: str, reason: str):
        super().__init__(f"{state}:{reason}")
        self.state = state
        self.reason = reason


def _coverage_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse_ts(value: Any, reason: str = "invalid_timestamp") -> datetime:
    if not isinstance(value, str):
        raise CoverageEnvelopeInvalid("malformed", reason)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise CoverageEnvelopeInvalid("malformed", reason) from None
    if parsed.tzinfo is None:
        raise CoverageEnvelopeInvalid("malformed", reason)
    return parsed


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _exact_keys(obj: Any, keys: set | frozenset, reason: str) -> dict:
    if not isinstance(obj, dict) or set(obj) != set(keys):
        raise CoverageEnvelopeInvalid("malformed", reason)
    return obj


def validate_coverage_rows(rows: Any) -> list[dict]:
    """Validate a whole helper result; any defect refuses the whole result.

    Malformed (a wrong value) outranks partial (a missing or null one), and a
    supplied null (``supplied_unknown``) is kept distinct from an absent key
    (``missing_field``). Nothing is defaulted — in particular nothing becomes 0.
    An empty list is a complete answer: no events in the window.
    """
    if not isinstance(rows, list):
        raise CoverageEnvelopeInvalid("malformed", "rows_not_a_list")
    partial: str | None = None
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise CoverageEnvelopeInvalid("malformed", "row_not_an_object")
        if set(row) - _COVERAGE_ROW_KEYS:
            raise CoverageEnvelopeInvalid("malformed", "unexpected_field")
        sport = row.get("sport")
        if "sport" not in row:
            partial = partial or "missing_field"
        elif sport is None:
            partial = partial or "supplied_unknown"
        elif not isinstance(sport, str) or not sport:
            raise CoverageEnvelopeInvalid("malformed", "invalid_sport")
        elif sport in seen:
            raise CoverageEnvelopeInvalid("malformed", "duplicate_sport")
        else:
            seen.add(sport)
        total = row.get("total")
        if "total" not in row:
            partial = partial or "missing_field"
        elif total is None:
            partial = partial or "supplied_unknown"
        elif not _is_int(total) or total <= 0:
            raise CoverageEnvelopeInvalid("malformed", "invalid_denominator")
        for key in ("live", *COVERAGE_SOURCE_KEYS):
            if key not in row:
                partial = partial or "missing_field"
                continue
            value = row[key]
            if value is None:
                partial = partial or "supplied_unknown"
            elif not _is_int(value) or value < 0:
                raise CoverageEnvelopeInvalid("malformed", "invalid_count")
            elif _is_int(total) and total > 0 and value > total:
                raise CoverageEnvelopeInvalid("malformed", "count_exceeds_total")
        if "expected_sources" not in row:
            partial = partial or "missing_field"
            continue
        expected = row["expected_sources"]
        if expected is None:
            partial = partial or "supplied_unknown"
            continue
        if not isinstance(expected, dict) or set(expected) - set(COVERAGE_SOURCE_KEYS):
            raise CoverageEnvelopeInvalid("malformed", "invalid_expected_sources")
        for key in COVERAGE_SOURCE_KEYS:
            if key not in expected:
                partial = partial or "missing_field"
            elif expected[key] is None:
                partial = partial or "supplied_unknown"
            elif not isinstance(expected[key], bool):
                raise CoverageEnvelopeInvalid("malformed", "invalid_expected_sources")
    if partial:
        raise CoverageEnvelopeInvalid("partial", partial)
    return rows


def _validate_attempt(attempt: Any) -> tuple[dict, datetime, datetime]:
    _exact_keys(attempt, {"outcome", "started_at", "finished_at", "error"}, "invalid_latest_attempt")
    started = _parse_ts(attempt["started_at"])
    finished = _parse_ts(attempt["finished_at"])
    if finished < started:
        raise CoverageEnvelopeInvalid("malformed", "invalid_latest_attempt")
    if attempt["outcome"] == "ok":
        if attempt["error"] is not None:
            raise CoverageEnvelopeInvalid("malformed", "invalid_latest_attempt")
    elif attempt["outcome"] == "error":
        error = _exact_keys(attempt["error"], {"kind", "code"}, "invalid_latest_attempt")
        # Type first: a saved list or object is unhashable and would escape the
        # membership test as a TypeError instead of a typed refusal.
        if not isinstance(error["kind"], str) or error["kind"] not in _COVERAGE_ERROR_KINDS \
                or not isinstance(error["code"], str) or not _SAFE_CODE.match(error["code"]):
            raise CoverageEnvelopeInvalid("malformed", "invalid_latest_attempt")
    else:
        raise CoverageEnvelopeInvalid("malformed", "invalid_latest_attempt")
    return attempt, started, finished


def _validate_last_good(last_good: Any) -> tuple[dict, datetime]:
    _exact_keys(last_good, {
        "complete", "rows", "unit", "rows_scope",
        "observation_started_at", "observation_finished_at", "computed_at", "published_at",
        "window", "source_provenance", "fresh_for_seconds", "freshness_policy_status",
        "retained_until",
    }, "invalid_last_good")
    if last_good["complete"] is not True or last_good["unit"] != "events" \
            or last_good["rows_scope"] != _COVERAGE_ROWS_SCOPE:
        raise CoverageEnvelopeInvalid("malformed", "invalid_last_good")
    observed = _parse_ts(last_good["observation_started_at"])
    stamps = [observed] + [
        _parse_ts(last_good[k])
        for k in ("observation_finished_at", "computed_at", "published_at")
    ]
    if stamps != sorted(stamps):
        raise CoverageEnvelopeInvalid("malformed", "timestamps_out_of_order")
    retained = _parse_ts(last_good["retained_until"])
    try:
        retain_end = observed + timedelta(seconds=EVENT_SOURCE_COVERAGE_RETAIN_SECONDS)
    except OverflowError:
        # A parseable stamp so late that no retention window fits after it.
        raise CoverageEnvelopeInvalid("malformed", "invalid_timestamp") from None
    if retained != retain_end:
        raise CoverageEnvelopeInvalid("malformed", "retention_not_from_observation")
    fresh, policy = last_good["fresh_for_seconds"], last_good["freshness_policy_status"]
    if policy == "approved" and _is_int(fresh) and fresh > 0:
        # "approved" means the REVIEWED horizon and nothing else. Any other saved
        # number is a policy nobody reviewed and would misstate how long this
        # evidence is fresh; it is refused, never trusted or rewritten.
        if fresh != EVENT_SOURCE_COVERAGE_FRESH_FOR_SECONDS:
            raise CoverageEnvelopeInvalid("malformed", "incompatible_freshness_policy")
    elif not (policy == "unreviewed" and fresh is None):
        raise CoverageEnvelopeInvalid("malformed", "invalid_freshness_policy")

    window = _exact_keys(last_good["window"], {
        "window_anchor", "window_start", "window_end", "database_timezone",
        "transaction_isolation", "start_inclusive", "end_inclusive",
    }, "invalid_window")
    start, anchor, end = (
        _parse_ts(window[k], "invalid_window") for k in ("window_start", "window_anchor", "window_end")
    )
    if not (start < anchor < end) or window["start_inclusive"] is not True \
            or window["end_inclusive"] is not True:
        raise CoverageEnvelopeInvalid("malformed", "invalid_window")
    for key in ("database_timezone", "transaction_isolation"):
        if not isinstance(window[key], str) or not window[key]:
            raise CoverageEnvelopeInvalid("malformed", "invalid_window")

    prov = _exact_keys(last_good["source_provenance"], {
        "accepted_semantic_reference", "reference_is_production_adoption",
        "executing_source_revision", "executing_release_version", "provenance_status",
        "helper_file_sha256", "sql_literal_sha256", "expected_source_mapping_sha256",
        "source_last_updated_at", "source_last_updated_status",
    }, "invalid_provenance")
    revision = prov["executing_source_revision"]
    if prov["accepted_semantic_reference"] != EVENT_SOURCE_COVERAGE_ACCEPTED_REFERENCE \
            or prov["reference_is_production_adoption"] is not False \
            or prov["source_last_updated_at"] is not None \
            or prov["source_last_updated_status"] != "not_supplied_by_helper" \
            or not (revision is None or (isinstance(revision, str) and revision)) \
            or prov["provenance_status"] != ("unknown" if revision is None else "deployment_reported") \
            or not (prov["executing_release_version"] is None
                    or isinstance(prov["executing_release_version"], str)):
        raise CoverageEnvelopeInvalid("malformed", "invalid_provenance")
    for key in ("helper_file_sha256", "sql_literal_sha256", "expected_source_mapping_sha256"):
        if prov[key] is not None and not (isinstance(prov[key], str) and _SHA256_HEX.match(prov[key])):
            raise CoverageEnvelopeInvalid("malformed", "invalid_provenance")

    validate_coverage_rows(last_good["rows"])
    return last_good, observed


def validate_coverage_envelope(envelope: Any) -> dict:
    """Validate a whole stored envelope, including its two halves' consistency."""
    _exact_keys(envelope, {"schema_version", "last_good", "latest_attempt"}, "invalid_envelope")
    version = envelope["schema_version"]
    if not _is_int(version) or version != EVENT_SOURCE_COVERAGE_SCHEMA_VERSION:
        raise CoverageEnvelopeInvalid("malformed", "unsupported_schema_version")
    if envelope["latest_attempt"] is None:
        raise CoverageEnvelopeInvalid("malformed", "missing_latest_attempt")
    attempt, a_started, a_finished = _validate_attempt(envelope["latest_attempt"])
    last_good = envelope["last_good"]
    if last_good is not None:
        _validate_last_good(last_good)
        obs_start = _parse_ts(last_good["observation_started_at"])
        obs_end = _parse_ts(last_good["observation_finished_at"])
    if attempt["outcome"] == "ok":
        # A success envelope carries the observation that attempt made.
        if last_good is None or not (a_started <= obs_start and obs_end <= a_finished):
            raise CoverageEnvelopeInvalid("malformed", "inconsistent_success_envelope")
    elif last_good is not None and obs_end > a_started:
        # Retained evidence must predate the failed attempt that kept it.
        raise CoverageEnvelopeInvalid("malformed", "inconsistent_error_envelope")
    return envelope


# ---------------------------------------------------------------------------
# GET side: one bounded, off-loop read and a typed answer.
# ---------------------------------------------------------------------------


class _CoverageCacheReadError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _coverage_cache_client():
    """The request-path client: the latency sampler's exact signature (#1197).

    ``socket_timeout=0.5, fast_fail=True`` is an existing signature, so this is a
    lookup in the per-process client cache — no new pool against the shared
    80-connection budget, and no change to the shared Redis policy.
    """
    from app.tasks.redis_state import get_redis_client

    return get_redis_client(socket_timeout=0.5, fast_fail=True)


def _blocking_coverage_get():
    return _coverage_cache_client().get(EVENT_SOURCE_COVERAGE_CACHE_KEY)


def _discard_late_result(future) -> None:
    # The read outlived its deadline; its result (or error) has no reader.
    if not future.cancelled():
        future.exception()


async def _read_coverage_cache_raw():
    """One GET of the coverage key, off the event loop, under a total deadline.

    ``asyncio.wait`` rather than ``wait_for``: the deadline must bound THIS
    request's wait, and an executor thread cannot be cancelled — it finishes
    under the client's own socket bounds and its late result is discarded.
    """
    loop = asyncio.get_running_loop()
    future = loop.run_in_executor(None, _blocking_coverage_get)
    done, _ = await asyncio.wait({future}, timeout=EVENT_SOURCE_COVERAGE_READ_DEADLINE_S)
    if not done:
        future.add_done_callback(_discard_late_result)
        raise _CoverageCacheReadError("read_deadline_exceeded")
    try:
        return future.result()
    except Exception:
        raise _CoverageCacheReadError("redis_unavailable") from None


def _tier1_projection(rows: list[dict] | None) -> list[dict]:
    """Every Tier-1 sport, golf included, each over its OWN denominator.

    A sport absent from a complete result had no events in the window; a sport
    with no usable result is missing evidence. Neither becomes a zero row, and
    no row carries a health colour — no source threshold has been approved.
    """
    from app.utils.admin_dashboard import _TIER1_SPORTS

    by_sport = {row["sport"]: row for row in rows or []}
    out = []
    for sport in _TIER1_SPORTS:
        row = by_sport.get(sport)
        if rows is None or row is None:
            out.append({
                "sport": sport,
                "row_state": "missing_evidence" if rows is None else "no_in_window_events",
                "denominator": None,
                "sources": None,
                "health_verdict": "unverified",
            })
            continue
        out.append({
            "sport": sport,
            "row_state": "observed",
            "denominator": row["total"],
            "sources": {
                key: {
                    "count": row[key],
                    "expected": row["expected_sources"][key],
                    "share": row[key] / row["total"],
                }
                for key in COVERAGE_SOURCE_KEYS
            },
            "health_verdict": "unverified",
        })
    return out


def _coverage_response(status: int, cache_state: str, freshness: str, reason: str, **extra) -> tuple[int, dict]:
    last_good = extra.get("last_good")
    body = {
        "schema_version": EVENT_SOURCE_COVERAGE_SCHEMA_VERSION,
        "cache_state": cache_state,
        "freshness": freshness,
        "reason": reason,
        "producer_error": extra.get("producer_error"),
        "age_seconds": extra.get("age_seconds"),
        "fresh_until": extra.get("fresh_until"),
        "retained_until": extra.get("retained_until"),
        "expired_observation": extra.get("expired_observation"),
        "last_good": last_good,
        "latest_attempt": extra.get("latest_attempt"),
        "tier1": _tier1_projection(last_good["rows"] if last_good else None),
        "accepted_semantic_reference": EVENT_SOURCE_COVERAGE_ACCEPTED_REFERENCE,
    }
    return status, body


async def read_event_source_coverage_cache() -> tuple[int, dict]:
    """The whole cache-only GET: ``(http_status, body)``. Never computes coverage.

    The request clock is used ONLY to age the stored observation; no stored
    timestamp is replaced by it and nothing is written back.
    """
    try:
        raw = await _read_coverage_cache_raw()
    except _CoverageCacheReadError as exc:
        return _coverage_response(503, "error", "unknown", exc.code)
    if raw is None:
        return _coverage_response(202, "miss", "unknown", "no_cached_observation")
    try:
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8")
        envelope = json.loads(raw)
    except (UnicodeDecodeError, ValueError, TypeError, RecursionError):
        # RecursionError: the C decoder's answer to valid but absurdly nested JSON.
        return _coverage_response(503, "malformed", "unknown", "not_json")
    try:
        validate_coverage_envelope(envelope)
    except CoverageEnvelopeInvalid as exc:
        return _coverage_response(503, exc.state, "unknown", exc.reason)

    attempt = envelope["latest_attempt"]
    producer_error = attempt["error"] if attempt["outcome"] == "error" else None
    last_good = envelope["last_good"]
    if last_good is None:
        return _coverage_response(
            503, "producer_error", "unknown", "producer_failed_without_evidence",
            producer_error=producer_error, latest_attempt=attempt,
        )

    now = _coverage_now()
    observed = _parse_ts(last_good["observation_started_at"])
    retained = _parse_ts(last_good["retained_until"])
    if now >= retained:
        return _coverage_response(
            202, "expired", "unknown", "retained_evidence_expired",
            producer_error=producer_error, latest_attempt=attempt,
            retained_until=last_good["retained_until"],
            expired_observation={
                "observation_started_at": last_good["observation_started_at"],
                "retained_until": last_good["retained_until"],
            },
        )

    age = (now - observed).total_seconds()
    fresh_for = last_good["fresh_for_seconds"]
    fresh_until = None
    if age < 0:
        freshness, reason = "unknown", "observation_clock_in_future"
    elif last_good["freshness_policy_status"] != "approved":
        freshness, reason = "unknown", "freshness_policy_unreviewed"
    elif last_good["source_provenance"]["provenance_status"] != "deployment_reported":
        freshness, reason = "unknown", "source_identity_unknown"
    else:
        fresh_until = _iso(observed + timedelta(seconds=fresh_for))
        freshness = "fresh" if age < fresh_for else "stale"
        reason = "observed" if freshness == "fresh" else "observation_older_than_horizon"
    if producer_error is not None:
        reason = "latest_attempt_failed"
    return _coverage_response(
        200, "hit", freshness, reason,
        producer_error=producer_error, latest_attempt=attempt,
        age_seconds=age, fresh_until=fresh_until,
        retained_until=last_good["retained_until"], last_good=last_good,
    )


# ---------------------------------------------------------------------------
# Producer: implemented, tested against fakes, and reachable from nowhere.
# ---------------------------------------------------------------------------


def _classify_db_error(exc: BaseException) -> dict:
    """A fixed safe ``{kind, code}`` — never the exception text, SQL or DSN."""
    seen = 0
    node: BaseException | None = exc
    while node is not None and seen < 8:
        if type(node).__name__ == "QueryCanceledError" or getattr(node, "sqlstate", None) == "57014":
            return {"kind": "statement_timeout", "code": "query_canceled"}
        node = getattr(node, "orig", None) or node.__cause__
        seen += 1
    return {"kind": "query_error", "code": "database_error"}


def _executing_source_identity() -> dict:
    """What the deployment reports about itself, or unknown — never the reference.

    Reads the same Heroku dyno-metadata variables the release tags already use;
    no network, no credential. The source hashes are of the bytes this process
    imported its helper from, by the method the #847 packet pinned its
    reference values with, so the two can be compared but never confused.
    """
    import ast
    import hashlib
    import inspect

    revision = os.getenv("HEROKU_SLUG_COMMIT") or None
    identity: dict[str, Any] = {
        "executing_source_revision": revision,
        "executing_release_version": os.getenv("HEROKU_RELEASE_VERSION") or None,
        "provenance_status": "deployment_reported" if revision else "unknown",
        "helper_file_sha256": None,
        "sql_literal_sha256": None,
        "expected_source_mapping_sha256": None,
    }
    try:
        from app.utils import admin_dashboard

        source = open(inspect.getsourcefile(admin_dashboard), "rb").read()
        identity["helper_file_sha256"] = hashlib.sha256(source).hexdigest()
        literals = [
            call.args[0].value
            for fn in ast.walk(ast.parse(source))
            if isinstance(fn, ast.AsyncFunctionDef) and fn.name == "_query_event_source_coverage"
            for call in ast.walk(fn)
            if isinstance(call, ast.Call) and getattr(call.func, "id", None) == "text"
            and call.args and isinstance(call.args[0], ast.Constant)
        ]
        if len(literals) == 1:
            identity["sql_literal_sha256"] = hashlib.sha256(literals[0].encode()).hexdigest()
    except Exception:  # noqa: BLE001 — unknown is an honest answer; failing the run is not
        logger.warning("event-source coverage: helper source identity unavailable")
    try:
        from app.utils import admin_dashboard
        from app.utils.sport_keys import ESPN_SPORT_MAPPING, STATPAL_SPORT_MAPPING

        mapping = {
            "espn_sport_keys": sorted(ESPN_SPORT_MAPPING),
            "statpal_sport_keys": sorted(STATPAL_SPORT_MAPPING),
            "rule_source": inspect.getsource(admin_dashboard._expected_sources_for_sport),
        }
        identity["expected_source_mapping_sha256"] = hashlib.sha256(
            json.dumps(mapping, sort_keys=True).encode()
        ).hexdigest()
    except Exception:  # noqa: BLE001
        logger.warning("event-source coverage: expected-source mapping identity unavailable")
    return identity


def _window_from_metadata(meta: Any) -> dict:
    try:
        anchor, start, end = meta.window_anchor, meta.window_start, meta.window_end
        tz_name, isolation = meta.database_timezone, meta.transaction_isolation
    except AttributeError:
        raise CoverageEnvelopeInvalid("malformed", "window_metadata_missing") from None
    if not all(isinstance(v, datetime) and v.tzinfo is not None for v in (anchor, start, end)) \
            or not (start < anchor < end) \
            or not all(isinstance(v, str) and v for v in (tz_name, isolation)):
        raise CoverageEnvelopeInvalid("malformed", "window_metadata_invalid")
    return {
        "window_anchor": _iso(anchor),
        "window_start": _iso(start),
        "window_end": _iso(end),
        "database_timezone": tz_name,
        "transaction_isolation": isolation,
        "start_inclusive": True,
        "end_inclusive": True,
    }


def _dump_envelope(envelope: dict) -> str:
    return json.dumps(envelope, sort_keys=True, separators=(",", ":"))


async def _precompute_admin_event_source_coverage() -> dict:
    """Observe event-source coverage once and publish it. INERT — see above.

    One transaction, in this order: ``SET LOCAL statement_timeout = '10s'``
    (``run_db_panel``), ``SET TRANSACTION READ ONLY``, the window metadata
    SELECT, then the accepted helper ``_query_event_source_coverage`` exactly
    once, unchanged. ``run_db_panel`` rolls back on success and on error. The
    whole result is validated before anything is published; a failure keeps
    the previous good observation untouched and records only the attempt.
    """
    from app.tasks.base import get_task_session
    from app.tasks.redis_state import get_redis_client
    from app.utils.admin_dashboard import (
        _PANEL_STATEMENT_TIMEOUT,
        _query_event_source_coverage,
        run_db_panel,
    )
    from sqlalchemy import text

    attempt_started = _coverage_now()
    captured: dict[str, Any] = {}

    async def _observe(db):
        try:
            await db.execute(text("SET TRANSACTION READ ONLY"))
            meta = (await db.execute(text(_COVERAGE_WINDOW_SQL))).one()
            observation_started = _coverage_now()
            rows = await _query_event_source_coverage(db)
            observation_finished = _coverage_now()
        except Exception as exc:
            captured["exc"] = exc
            raise
        return meta, rows, observation_started, observation_finished

    error: dict | None = None
    observed = None
    try:
        async with get_task_session() as db:
            observed = await run_db_panel(
                db, "event_source_coverage", lambda: _observe(db),
                on_error=lambda _msg: None,
                statement_timeout=_PANEL_STATEMENT_TIMEOUT,
            )
    except Exception as exc:  # noqa: BLE001 — session open/close failure
        captured.setdefault("exc", exc)
        observed = None
    if observed is None:
        error = _classify_db_error(captured.get("exc") or RuntimeError())

    last_good = None
    if error is None:
        meta, rows, observation_started, observation_finished = observed
        try:
            window = _window_from_metadata(meta)
        except CoverageEnvelopeInvalid as exc:
            error = {"kind": "provenance_error", "code": exc.reason}
        else:
            try:
                validate_coverage_rows(rows)
            except CoverageEnvelopeInvalid as exc:
                error = {"kind": "malformed_result", "code": f"{exc.state}_{exc.reason}"}
            else:
                computed_at = _coverage_now()
                provenance = {
                    "accepted_semantic_reference": EVENT_SOURCE_COVERAGE_ACCEPTED_REFERENCE,
                    "reference_is_production_adoption": False,
                    **_executing_source_identity(),
                    "source_last_updated_at": None,
                    "source_last_updated_status": "not_supplied_by_helper",
                }
                last_good = {
                    "complete": True,
                    "rows": rows,
                    "unit": "events",
                    "rows_scope": _COVERAGE_ROWS_SCOPE,
                    "observation_started_at": _iso(observation_started),
                    "observation_finished_at": _iso(observation_finished),
                    "computed_at": _iso(computed_at),
                    "published_at": _iso(_coverage_now()),
                    "window": window,
                    "source_provenance": provenance,
                    "fresh_for_seconds": EVENT_SOURCE_COVERAGE_FRESH_FOR_SECONDS,
                    "freshness_policy_status": "approved",
                    "retained_until": _iso(
                        observation_started + timedelta(seconds=EVENT_SOURCE_COVERAGE_RETAIN_SECONDS)
                    ),
                }

    rc = get_redis_client()
    attempt_finished = _coverage_now()
    if error is None:
        envelope = {
            "schema_version": EVENT_SOURCE_COVERAGE_SCHEMA_VERSION,
            "last_good": last_good,
            "latest_attempt": {
                "outcome": "ok",
                "started_at": _iso(attempt_started),
                "finished_at": _iso(attempt_finished),
                "error": None,
            },
        }
        ttl = math.ceil(
            (_parse_ts(last_good["retained_until"]) - attempt_finished).total_seconds()
        )
    else:
        # Keep the previous good observation exactly as stored, or none at all.
        try:
            prior_raw = await asyncio.to_thread(rc.get, EVENT_SOURCE_COVERAGE_CACHE_KEY)
        except Exception:  # noqa: BLE001
            # The stored last-good is now UNKNOWN; overwriting it with an
            # evidence-free failure could destroy good evidence we cannot see.
            logger.warning("event-source coverage run failed (%s/%s); prior envelope unreadable, not publishing",
                           error["kind"], error["code"])
            return {"status": "error", "error": error, "published": False,
                    "publish_error": {"kind": "cache_read_error", "code": "prior_envelope_unreadable"}}
        retained_good = None
        try:
            prior = json.loads(prior_raw) if prior_raw is not None else None
            if prior is not None:
                validate_coverage_envelope(prior)
                candidate = prior["last_good"]
                if candidate is not None and _parse_ts(candidate["retained_until"]) > attempt_finished:
                    retained_good = candidate
        except (CoverageEnvelopeInvalid, ValueError, TypeError, RecursionError):
            retained_good = None  # unusable evidence is not last-good evidence
        envelope = {
            "schema_version": EVENT_SOURCE_COVERAGE_SCHEMA_VERSION,
            "last_good": retained_good,
            "latest_attempt": {
                "outcome": "error",
                "started_at": _iso(attempt_started),
                "finished_at": _iso(attempt_finished),
                "error": error,
            },
        }
        # Never extend retained evidence: the key lives only as long as the
        # observation it carries. An evidence-free failure keeps the module TTL.
        ttl = (
            math.ceil((_parse_ts(retained_good["retained_until"]) - attempt_finished).total_seconds())
            if retained_good is not None
            else EVENT_SOURCE_COVERAGE_RETAIN_SECONDS
        )

    try:
        validate_coverage_envelope(envelope)
    except CoverageEnvelopeInvalid as exc:
        logger.warning("event-source coverage envelope refused before publication: %s", exc.reason)
        return {"status": "error", "error": {"kind": "malformed_result", "code": exc.reason},
                "published": False}
    try:
        await asyncio.to_thread(
            rc.set, EVENT_SOURCE_COVERAGE_CACHE_KEY, _dump_envelope(envelope), ex=max(1, ttl)
        )
    except Exception:  # noqa: BLE001
        # The failed SET cannot record itself in the key it failed to write;
        # readers keep seeing whatever was there before. Say so here instead.
        logger.warning("event-source coverage publication failed; cache unchanged")
        return {"status": "error", "error": error, "published": False,
                "publish_error": {"kind": "cache_publish_error", "code": "redis_set_failed"}}
    logger.info("Cached admin event-source coverage (outcome=%s, retained_last_good=%s)",
                envelope["latest_attempt"]["outcome"], envelope["last_good"] is not None)
    return {
        "status": "ok" if error is None else "error",
        "error": error,
        "published": True,
        "rows": len(envelope["last_good"]["rows"]) if envelope["last_good"] else None,
    }


# ---------------------------------------------------------------------------
# #847 — the 14-day sport cards for the Correctness Console's Matching tab.
#
# THE PRODUCER IS INERT, like the coverage producer above: not a Celery task,
# in no beat schedule, called by nothing. Only fake sessions and fake Redis
# ever execute it. The reader and the snapshot contract live beside the legacy
# route in ``app.routes.admin_events``.
#
# One transaction, in this order: ``SET LOCAL statement_timeout = '10s'``
# (``run_db_panel``), ``SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ
# ONLY`` (so the legacy calculation's two grouped counts read ONE snapshot), a
# settings read that proves both took, then ``_compute_schedule_accuracy(db,
# days=14, now=as_of)`` exactly once and unchanged. ``run_db_panel`` rolls back
# on success and on error.
#
# A failed run publishes NOTHING: the earlier snapshot keeps its own bytes and
# its own expiry, so a failure can neither replace it with an empty or partial
# result nor make it look newer. The run's return value says what failed.
#
# Owed before activation, and not decided here: statement cost/plan, cadence,
# retention (``SCHEDULE_ACCURACY_RETAIN_SECONDS`` is a placeholder equal to
# this module's TTL), and a single publisher — nothing here stops two
# overlapping runs from racing their SETs, so one beat entry must be the only
# writer.
# ---------------------------------------------------------------------------

SCHEDULE_ACCURACY_RETAIN_SECONDS = _ADMIN_HEALTH_CACHE_TTL
_SCHEDULE_ACCURACY_TRANSACTION_SQL = (
    "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
)
_SCHEDULE_ACCURACY_SETTINGS_SQL = (
    "SELECT current_setting('transaction_isolation') AS isolation, "
    "current_setting('transaction_read_only') AS read_only"
)


def _schedule_accuracy_now() -> datetime:
    return datetime.now(timezone.utc)


async def _precompute_admin_schedule_accuracy() -> dict:
    """Observe the 14-day sport cards once and publish them. INERT — see above."""
    from app.routes.admin_events import (
        SCHEDULE_ACCURACY_CACHE_KEY,
        SCHEDULE_ACCURACY_DAYS,
        SCHEDULE_ACCURACY_MAX_BYTES,
        SCHEDULE_ACCURACY_SNAPSHOT_VERSION,
        SCHEDULE_ACCURACY_WINDOW_COLUMN,
        _compute_schedule_accuracy,
        check_schedule_accuracy_snapshot,
    )
    from app.tasks.base import get_task_session
    from app.tasks.redis_state import get_redis_client
    from app.utils.admin_dashboard import _PANEL_STATEMENT_TIMEOUT, run_db_panel
    from app.utils.saved_snapshot_read import SavedPayloadInvalid, strict_loads
    from sqlalchemy import text

    captured: dict[str, Any] = {}

    async def _observe(db):
        try:
            await db.execute(text(_SCHEDULE_ACCURACY_TRANSACTION_SQL))
            as_of = _schedule_accuracy_now()
            settings = (await db.execute(text(_SCHEDULE_ACCURACY_SETTINGS_SQL))).one()
            accuracy = await _compute_schedule_accuracy(db, days=SCHEDULE_ACCURACY_DAYS, now=as_of)
            finished = _schedule_accuracy_now()
        except Exception as exc:
            captured["exc"] = exc
            raise
        return as_of, settings, accuracy, finished

    def _refused(error: dict) -> dict:
        logger.warning("schedule-accuracy snapshot not published (%s/%s)", error["kind"], error["code"])
        return {"status": "error", "error": error, "published": False}

    observed = None
    try:
        async with get_task_session() as db:
            observed = await run_db_panel(
                db, "schedule_accuracy_14d", lambda: _observe(db),
                on_error=lambda _msg: None,
                statement_timeout=_PANEL_STATEMENT_TIMEOUT,
            )
    except Exception as exc:  # noqa: BLE001 — session open/close failure
        captured.setdefault("exc", exc)
        observed = None
    if observed is None:
        return _refused(_classify_db_error(captured.get("exc") or RuntimeError()))

    as_of, settings, accuracy, finished = observed
    snapshot = {
        "schema_version": SCHEDULE_ACCURACY_SNAPSHOT_VERSION,
        "generated_at": _iso(as_of),
        "as_of": _iso(as_of),
        "observation_finished_at": _iso(finished),
        "window": {
            "column": SCHEDULE_ACCURACY_WINDOW_COLUMN,
            "days": SCHEDULE_ACCURACY_DAYS,
            "start": _iso(as_of - timedelta(days=SCHEDULE_ACCURACY_DAYS)),
            "start_inclusive": True,
            "end": None,
        },
        "transaction": {
            "isolation": getattr(settings, "isolation", None),
            "read_only": getattr(settings, "read_only", None) == "on",
        },
        "accuracy": accuracy,
    }
    try:
        # NOT sort_keys: the legacy payload's sport order is part of it.
        raw = json.dumps(snapshot, separators=(",", ":"), allow_nan=False)
        # The reader's own contract, on the exact bytes a reader would get.
        check_schedule_accuracy_snapshot(strict_loads(raw))
    except SavedPayloadInvalid as exc:
        return _refused({"kind": "malformed_result", "code": exc.reason})
    except (TypeError, ValueError):
        return _refused({"kind": "malformed_result", "code": "not_serializable"})
    if len(raw.encode("utf-8")) > SCHEDULE_ACCURACY_MAX_BYTES:
        return _refused({"kind": "malformed_result", "code": "exceeds_read_bound"})
    # The key lives only as long as the observation it carries, from as_of.
    ttl = math.ceil(
        (as_of + timedelta(seconds=SCHEDULE_ACCURACY_RETAIN_SECONDS) - _schedule_accuracy_now())
        .total_seconds()
    )
    if ttl <= 0:
        return _refused({"kind": "malformed_result", "code": "observation_outlived_retention"})
    try:
        await asyncio.to_thread(get_redis_client().set, SCHEDULE_ACCURACY_CACHE_KEY, raw, ex=ttl)
    except Exception:  # noqa: BLE001
        # Readers keep seeing whatever was there before. Say so here instead.
        return _refused({"kind": "cache_publish_error", "code": "redis_set_failed"})
    logger.info("Cached admin schedule-accuracy 14d snapshot (sports=%d)", len(accuracy["sports"]))
    return {"status": "ok", "error": None, "published": True, "sports": len(accuracy["sports"])}
