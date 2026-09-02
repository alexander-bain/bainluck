"""Precompute heavy calibration queries and cache results in Redis.

These queries time out during Heroku's 30-second request window on production
data volumes (500K+ snapshot rows). Running them as background Celery tasks
with results cached in Redis lets the API endpoints serve instantly.
"""

import contextlib
import json
import logging
import math
import random
import re
import time
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

from sqlalchemy import text

from app.utils.calibration_coverage_bridge import RUNG_KEYS as _COVERAGE_RUNG_KEYS
from app.utils.calibration_coverage_bridge import (
    build_coverage_census as _build_coverage_census,
)
# CAL-P168 (#1978): R2's tolerance is the SHIPPED writer-side one, imported
# rather than restated — the read-side exclusion and the write-side coherence
# rule must not be able to disagree about what "the pair sums to 1" means.
from app.utils.pair_opening_coherence import PAIR_SUM_TOLERANCE
from app.utils.resolution_authority import (
    CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL,
    CALIBRATION_TRUTH_INELIGIBLE_SOURCES_SQL,
    PRICE_DERIVED_SOURCES_SQL,
)

logger = logging.getLogger(__name__)

# Redis cache TTL: 24 hours (results don't change quickly)
_CACHE_TTL = 86400

# Main calibration cache TTL: 2 hours (refreshed every 1h by beat)
_MAIN_CACHE_TTL = 7200

# Queue 272 (#1459): the DURABLE last-good key. The main key (`bainluck:
# calibration:main`, 2h TTL) is the FRESH surface; this parallel key is the
# survivor. It is written on every successful publish with a long TTL so a streak
# of compute timeouts — the observed failure mode (SoftTimeLimitExceeded at ~605s,
# 3 consecutive fails, last success 605.8s at the 600s soft limit) — can never
# blank the /api/calibration route: the main key expires after 2h but the route
# falls back to this last-good payload (served `stale`, its own generated_at kept)
# until a complete replacement is ready. Both keys are SET-only (never DEL), so a
# failed/partial publish can never destroy a usable prior payload (Item 1).
_MAIN_LAST_GOOD_KEY = "bainluck:calibration:main:last_good"
_MAIN_KEY = "bainluck:calibration:main"

# D21 (#1978, CAL-P150). The per-bookmaker curve arrives through Redis rather
# than through this module's SQL — written by `precompute_bookmaker_calibration`
# (backfill_winners.py, every 6 h, 24 h TTL, fails closed) and read in Phase 3
# below. It is ~96,026 outcomes and it is concatenated into `all_rows`, so it is
# part of the PUBLISHED population and not, as its phase heading implies, a
# transparency read.
#
# The reason all three of these are named constants rather than literals is the
# outage they are named after: the reader swallowed an absent key with
# `except: pass`, so the one string that identifies the failure appeared nowhere
# in the evidence. A refusal whose reason is a bare literal buried in a string
# is a refusal nobody can grep for.
BOOKMAKER_CURVE_REDIS_KEY = "bainluck:bookmaker_calibration"
BOOKMAKER_CURVE_ABSENT_REFUSAL = "bookmaker_curve_key_absent"
BOOKMAKER_CURVE_UNREADABLE_REFUSAL = "bookmaker_curve_key_unreadable"

#: CERT-502 P1. The ONLY value `source` may hold in a row under
#: `BOOKMAKER_CURVE_REDIS_KEY` — `_precompute_bookmaker_calibration` emits it as a
#: literal, once, for every bucket it writes.
#:
#: This is a provenance check, not a type check, and it is the difference between
#: the two that CERT-502 found. `r.source` is part of the merge KEY, so a
#: complete, type-correct row carrying `source="kalshi"` was admitted with
#: `degraded=None` and merged into KALSHI's published curve — moving bookmaker
#: mass into another source's calibration while keeping the outcome COUNT
#: identical, which is precisely the shape the population gate cannot see.
#: Proving a row is well-formed is not proving it came from its only writer.
BOOKMAKER_CURVE_SOURCE = "odds_api_bookmaker"

#: What the reader expects to find, for the refusal message only. Approximate by
#: construction — it is the magnitude the outage was measured at
#: (alex-inbox/calibration-907 §"what you will need to do after it deploys"), and
#: it is quoted so an operator reading the refusal knows what "short" means
#: without having to go and find the number. Nothing branches on it.
BOOKMAKER_CURVE_EXPECTED_OUTCOMES = 96_026


def _shape_of(value) -> str:
    """Describe a parsed JSON value's SHAPE for a refusal message.

    CERT-485 P1-b. An operator told only "wrong shape" has to go and fetch the
    key themselves; an operator told "a list of 3 items, first is int" can act.
    So the shape is named — and ONLY the shape.

    The VALUE is deliberately never interpolated. This string goes to the logs
    and into the served payload's degraded reason, and the key can hold ~96K
    outcomes' worth of rows: echoing it would turn a diagnostic into a log flood
    on the one path that is already having a bad day. Type and cardinality are
    what distinguish the four failure modes; the contents distinguish nothing.
    """
    if isinstance(value, list):
        if not value:
            return "an empty list"
        kinds = sorted({type(v).__name__ for v in value})
        return f"a list of {len(value)} item(s) of type {'/'.join(kinds)}"
    return f"a bare {type(value).__name__}"


# CERT-497 P1. The set of keys the CONSUMER dereferences, derived by reading it
# rather than by copying the writer's literal. `_precompute_bookmaker_calibration`
# (backfill_winners.py) emits nine keys; eight of them are read as bare
# attributes on the merge path — `r.bucket_idx`, `r.source`, `r.category` are the
# merge KEY, `r.n`/`r.winners` are summed, `r.sum_prob`/`r.sum_sq_err` are
# `float()`d, `r.avg_prob` is read once — so a row missing any of them raises
# AttributeError AFTER the refusal boundary, which kills the scheduled build
# instead of degrading it.
#
# `price_moved` is deliberately NOT required: the merge path already reads it as
# `getattr(r, "price_moved", None)`, so its absence is handled by construction
# and demanding it would refuse a payload the consumer can in fact read.
_BOOKMAKER_ROW_REQUIRED_KEYS = (
    "bucket_idx",
    "source",
    "category",
    "n",
    "winners",
    "avg_prob",
    "sum_prob",
    "sum_sq_err",
)


def _is_real_number(value) -> bool:
    """A JSON number this reader can do arithmetic on.

    `bool` is excluded ON PURPOSE. `isinstance(True, int)` is True in Python, so
    a naive int check admits `{"n": true}` and then `acc["n"] += True` counts a
    bucket of ONE outcome — a silent miscount, which is the exact class this
    validator exists to stop. NaN/inf are excluded for the same reason: they
    propagate through the sums and surface as a `null` avg_prob in the payload
    rather than as a refusal.
    """
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _bookmaker_row_defect(row: dict) -> str | None:
    """Name the first schema defect in one bookmaker row, or None if it is sound.

    CERT-497 P1. The container gate below proves `raw` is a non-empty list of
    dicts. It does NOT prove the dicts are bookmaker rows, and CERT-497
    constructed three payloads that pass it and still reproduce the two failure
    modes D21 exists to end:

      [{"category": "soccer_epl"}]   the soccer filter drops it on the way past,
                                     `rows` comes back empty and the reader
                                     returns ([], 0, None) — a SILENT zero with
                                     no reason in the payload, which is the
                                     96K-outcome shortfall re-entered a second
                                     time through a second unchecked shape.
      [{}]                           survives the filter as SimpleNamespace(),
                                     returns degraded=None, then AttributeError
                                     on `r.n` — a crash the refusal boundary has
                                     already been passed, so the producer dies
                                     instead of preserving the prior snapshot.
      [{"category": ..., "n": ...}]  same crash one key later, on `r.winners`.

    Returned as a description rather than raised so the caller can put it on the
    EXISTING degradation contract (producer raises by name, serve path reports
    the reason in the payload) instead of introducing a second one.

    Only key names and type names are ever named — never a value. `_shape_of`
    explains why: this string reaches the logs and the served payload, and the
    key can hold ~96K outcomes' worth of rows.
    """
    missing = [k for k in _BOOKMAKER_ROW_REQUIRED_KEYS if k not in row]
    if missing:
        return "missing required key(s) %s" % ", ".join(repr(k) for k in missing)

    if not isinstance(row["bucket_idx"], int) or isinstance(row["bucket_idx"], bool):
        return "'bucket_idx' is %s, not an int" % type(row["bucket_idx"]).__name__
    for key in ("source", "category"):
        if not isinstance(row[key], str):
            return "%r is %s, not a str" % (key, type(row[key]).__name__)

    # 🔴 CERT-502 P1 — PROVENANCE, not shape, and the distinction is the finding.
    # Every check around this one proves the row is WELL-FORMED. None of them
    # proves it came from its only writer, and `r.source` is part of the merge
    # KEY: a complete, type-correct row carrying `source="kalshi"` was admitted
    # with `degraded=None` and merged into KALSHI's published curve. The outcome
    # COUNT is unchanged by that, so the population gate cannot see it either —
    # bookmaker mass silently becomes another source's calibration.
    #
    # The expected value is NOT interpolated (`_shape_of`'s discipline applies to
    # the constant too): the message names the offending key, and the fixed prose
    # below already tells an operator which curve this key carries.
    if row["source"] != BOOKMAKER_CURVE_SOURCE:
        return (
            "'source' is not the one this key's only writer emits — the row "
            "claims a different source and would be merged under it"
        )
    for key in ("n", "winners"):
        if not isinstance(row[key], int) or isinstance(row[key], bool):
            return "%r is %s, not an int" % (key, type(row[key]).__name__)
    for key in ("avg_prob", "sum_prob", "sum_sq_err"):
        if not _is_real_number(row[key]):
            return "%r is %s, not a finite number" % (key, type(row[key]).__name__)

    # Domain checks, and only the two the writer makes structurally impossible.
    # `n` counts every outcome in the bucket and `winners` increments a subset of
    # the same loop, so `1 <= n` and `0 <= winners <= n` hold by construction.
    # A row outside them is corrupt in a way that stays SILENT if admitted:
    # `n <= 0` contributes nothing but drags the `avg_prob` denominator, and
    # `winners > n` hands `_wilson_ci` an impossible rate and publishes a
    # calibration point above 100%. Nothing looser is asserted — `avg_prob` is
    # NOT cross-checked against `sum_prob / n`, because the writer rounds and a
    # float-equality refusal would be a false alarm on a healthy sweep.
    if row["n"] < 1:
        return "'n' is not a positive count"
    if not 0 <= row["winners"] <= row["n"]:
        return "'winners' is outside 0..n"

    # Optional by consumer contract, but if it IS present it becomes part of the
    # merge key, so it has to be hashable and of the writer's type.
    if "price_moved" in row and not (
        row["price_moved"] is None or isinstance(row["price_moved"], bool)
    ):
        return "'price_moved' is %s, not a bool or null" % type(
            row["price_moved"]
        ).__name__

    return None


def read_bookmaker_curve_rows(rc, *, refuse: bool, json_module=None):
    """The per-bookmaker curve, or a NAMED refusal. Never a silent zero.

    D21 (#1978, CAL-P150) — freeze exception GRANTED by Alex 2026-08-30, and
    lifted out of Phase 3 so the refusal can be exercised without standing up
    the whole build.

    THE DEFECT THIS REPLACES, and it is worth the paragraph because the shape
    recurs. The call site read this key inside a ``try: ... except Exception:
    pass``. ``_precompute_bookmaker_calibration`` stopped finishing inside its
    soft time limit, so it stopped writing the key; the key aged out of its 24 h
    TTL; this reader turned the absence into ZERO rows; and the rows are
    concatenated into ``all_rows``, so the candidate went out ~96,026 outcomes
    short. The publish gate then rightly refused it, every beat, naming the
    SYMPTOM (a population move) and unable to name the CAUSE. Silent
    non-publish from 2026-08-29T00:36:47Z until it was run by hand.

    Returns ``(rows, soccer_excluded_n, degraded_reason)``. ``degraded_reason``
    is ``None`` on a good read and one of the two reason codes otherwise; it is
    only ever non-None when ``refuse`` is False.

    Raises :class:`RuntimeError` naming :data:`BOOKMAKER_CURVE_ABSENT_REFUSAL`
    or :data:`BOOKMAKER_CURVE_UNREADABLE_REFUSAL` when ``refuse`` is True.

    🔴 ``refuse`` IS NOT A CONVENIENCE FLAG, AND ITS ABSENCE WAS A REAL DEFECT
    IN THE FIRST CUT OF THIS FIX. ``compute_calibration_payload`` has TWO
    callers: the scheduled producer, and ``/api/calibration``'s in-request
    cold-cache fallback. Refusing unconditionally turned "Redis is unreachable"
    into a 500 on the PUBLIC endpoint — a user-visible regression, on exactly
    the path that exists because Redis is unavailable. Caught by 95 failures in
    the calibration suite, 55 of them in ``test_route_calibration.py``, on the
    first full run after the fix.

    So the refusal is scoped to the producer, which is the only caller that can
    PUBLISH a short candidate and therefore the only one for which "short" is a
    correctness question. The serve path keeps the behaviour its docstring
    promises (``behaves EXACTLY as it did before``) and reports the degradation
    in the payload instead of swallowing it. That is still the whole point of
    D21: the absence is named either way, and the difference is only whether
    naming it stops the beat or annotates the response.

    🔴 THIS DOES NOT MAKE THE PRODUCER'S OUTCOME WORSE, and that is the argument
    for taking it inside a freeze. The gate already refused the short candidate,
    so nothing that used to publish stops publishing; an unattributable refusal
    is replaced by one that says which key, which writer, and how much is
    missing. What it must NOT become is a reason to publish anyway — a partial
    curve is not a smaller right answer, it is the exact shape that caused the
    outage.

    All three failure modes are one class on purpose (gotcha #53 — an empty
    answer is a response shape, not an absence): absent, unreachable and
    unparseable were indistinguishable under ``pass``, and the fix that
    distinguishes them from SUCCESS is the whole point. They are still told
    apart from each other, by two distinct reason codes, because "Redis is down"
    and "the writer has not landed a sweep" want different operators.
    """
    _json = json_module or json

    # 🔴 THIS QUEUE RAISED A PINNED TRIPWIRE — `uncovered_sql_shaping` 21 -> 22 —
    # AND THE REASON BELONGS BESIDE THE LINE THAT DID IT.
    #
    # `scripts/evals/calibration_fingerprint_derived_map.py` marks a
    # module-level name `sql_shaping` when it is interpolated into a string by
    # an f-string, a `+` or a `%` (CAL-P032 widened it past f-strings precisely
    # because this module builds SQL all three ways). Naming
    # `BOOKMAKER_CURVE_REDIS_KEY` inside a refusal message therefore counts it,
    # and there is no way to put the key in the message that the detector will
    # not see — a `.join` or a local alias would hide it, which is gaming a
    # tripwire rather than satisfying it.
    #
    # So the pin is RAISED, with the argument written into the guard: this key
    # is not SQL, but under the guard's own stated purpose — "the only class
    # that can silently change the published population" — it qualifies in
    # substance. Change it and the build reads a different curve and publishes
    # ~96K fewer outcomes. What it is NOT is silent, and D21 is the reason: on
    # the producer path a key that resolves to nothing is now a named refusal,
    # not a shortfall. It is the first entry in this count whose failure mode is
    # loud by construction.
    #
    # The other three BOOKMAKER_CURVE_* constants stay OUT of the count and are
    # not being hidden from it: the reason codes are passed to `_degrade` as
    # arguments and never interpolated, and the expected-outcomes figure is
    # rendered by `format()` — a call, which the detector does not treat as
    # string building because a call is not how this module writes SQL.
    _expected = format(BOOKMAKER_CURVE_EXPECTED_OUTCOMES, ",")

    def _degrade(reason: str, message: str, cause: Exception | None = None):
        if refuse:
            raise RuntimeError(f"{reason}: {message}") from cause
        # Not swallowed: logged with the traceback where there is one, and
        # returned so the caller can put the reason IN the payload. A serve that
        # is short 96K outcomes and does not say so is the original defect with
        # a different caller.
        logger.warning(
            "calibration serve degraded — %s: %s", reason, message,
            exc_info=cause is not None,
        )
        return [], 0, reason

    try:
        cached = rc.get(BOOKMAKER_CURVE_REDIS_KEY)
    except Exception as exc:
        return _degrade(
            BOOKMAKER_CURVE_UNREADABLE_REFUSAL,
            "could not read %s from Redis, so the per-bookmaker curve (~%s "
            "outcomes, source odds_api_bookmaker) cannot be assembled. Nothing "
            "published, prior snapshot preserved."
            % (BOOKMAKER_CURVE_REDIS_KEY, _expected),
            exc,
        )

    if not cached:
        return _degrade(
            BOOKMAKER_CURVE_ABSENT_REFUSAL,
            "%s is absent, so the candidate would publish ~%s outcomes short. "
            "Its only writer is precompute_bookmaker_calibration "
            "(backfill_winners.py, every 6 h, 24 h TTL, fails closed), so an "
            "absent key means that task has not landed a COMPLETE sweep inside "
            "one TTL. Fire it detached and confirm by_source carries "
            "odds_api_bookmaker before expecting this build to publish. "
            "Nothing published, prior snapshot preserved."
            % (BOOKMAKER_CURVE_REDIS_KEY, _expected),
        )

    try:
        raw = _json.loads(cached)
    except Exception as exc:
        return _degrade(
            BOOKMAKER_CURVE_UNREADABLE_REFUSAL,
            "%s is present but is not JSON this reader can parse. Nothing "
            "published, prior snapshot preserved." % (BOOKMAKER_CURVE_REDIS_KEY,),
            exc,
        )

    # 🔴 CERT-485 P1-b. `json.loads` returning is proof the bytes were JSON. It
    # is NOT proof they are a list of bookmaker rows, and until this check
    # existed the reader went straight from the parse into `for row in raw` /
    # `row.get(...)`. Three shapes got through, and the first is the worst:
    #
    #   {}     iterated zero keys and returned ([], 0, None) — SILENT, no
    #          reason in the payload. That is the 96K-outcome shortfall D21 was
    #          written to end, re-entered through a shape nobody checked.
    #   null   TypeError: 'NoneType' object is not iterable
    #   [1]    AttributeError: 'int' object has no attribute 'get'
    #
    # and the two exceptions escaped the `refuse=False` arm as well, so they
    # 500'd `/api/calibration`'s cold-cache fallback — the same defect D21's
    # first cut had (two callers, one of them unconsidered), one layer in.
    #
    # `[]` is refused too, and that is a deliberate reversal. The writer CANNOT
    # produce it: `backfill_winners.py`'s `elif not buckets:` arm sets
    # `terminal = "no_work"` and returns without ever reaching the `setex`, so
    # the only value that can be written is a non-empty list. An empty list is
    # therefore corrupt, not "no rows this cycle", and gotcha #53 says the two
    # must not share an answer.
    #
    # Everything lands on the EXISTING degradation contract rather than a new
    # one: producer raises by name, serve path logs and returns the reason so it
    # reaches the payload.
    if not isinstance(raw, list) or not raw or not all(
        isinstance(row, dict) for row in raw
    ):
        return _degrade(
            BOOKMAKER_CURVE_UNREADABLE_REFUSAL,
            "%s parsed as JSON but is not a non-empty list of bookmaker rows "
            "(got %s), so the per-bookmaker curve (~%s outcomes, source "
            "odds_api_bookmaker) cannot be assembled. Its only writer never "
            "writes an empty list — it reports no_work and writes nothing — so "
            "this value did not come from a healthy sweep. Nothing published, "
            "prior snapshot preserved."
            % (BOOKMAKER_CURVE_REDIS_KEY, _shape_of(raw), _expected),
        )

    # 🔴 CERT-497 P1. The gate above proves the CONTAINER; this one proves the
    # ROWS. Splitting them is the point of the fix: a list of dicts was treated
    # as a list of bookmaker rows, and "dict-shaped" is not "readable" — the
    # three payloads named in `_bookmaker_row_defect` all clear the container
    # check and then either publish a silent zero or crash the build past the
    # refusal boundary. That is gotcha #53 one level down from where D21 caught
    # it the first time: same defect, same reader, narrower shape.
    #
    # THE WHOLE PAYLOAD IS REFUSED, one bad row or all of them, and the rows are
    # NOT filtered down to the sound ones. Dropping the bad rows and publishing
    # the rest is precisely the unattributed shortfall this reader exists to
    # prevent — it would put a curve short by an unknown count on the board with
    # nothing in the payload saying so. The refusal is loud and the prior
    # snapshot survives; a quiet partial is neither.
    #
    # The first defect is reported with its row index, not a tally: the writer
    # emits every row from one loop over one aggregate, so rows do not go wrong
    # independently, and the first one is enough for an operator to read the key
    # and see what happened.
    for _idx, _row in enumerate(raw):
        _defect = _bookmaker_row_defect(_row)
        if _defect is not None:
            return _degrade(
                BOOKMAKER_CURVE_UNREADABLE_REFUSAL,
                "%s parsed as a list of %d dict(s), but row %d is not a "
                "bookmaker row: %s. So the per-bookmaker curve (~%s outcomes, "
                "source odds_api_bookmaker) cannot be assembled. Its only "
                "writer emits every required key from a single aggregate under "
                "one hard-coded source, so a row that fails this check did not "
                "come from a healthy sweep. Nothing published, prior snapshot "
                "preserved."
                % (
                    BOOKMAKER_CURVE_REDIS_KEY,
                    len(raw),
                    _idx,
                    _defect,
                    _expected,
                ),
            )

    # Queue #158 (#1011): the per-bookmaker calibration devigs soccer moneyline
    # as home_prob/(home_prob+away_prob) — the SAME 2-way draw-omission bug as
    # the events curve (`_precompute_bookmaker_calibration` has no draw term).
    # Left in, it dominates the soccer_* by_category lines (~40K draw-inflated
    # outcomes). Dropped here, read-side, so the exclusion holds even though the
    # 6 h source keeps writing them.
    rows = []
    soccer_excluded = 0
    for row in raw:
        if category_is_soccer_2way_excluded(row.get("category")):
            soccer_excluded += int(row.get("n") or 0)
            continue
        rows.append(SimpleNamespace(**row))
    return rows, soccer_excluded, None

# Queue 298 (#1512): both keys above live in the SAME 50MB allkeys-lru Redis, so
# "durable last_good" was only ever durable against TTL, never against eviction
# or a dead store — and a fresh web dyno has no process cache either. The real
# survivor is now a row in `durable_state_snapshots` under this identity, written
# BEFORE either Redis key. The Redis pair stays exactly as it is: accelerators.
_DURABLE_IDENTITY = "calibration:main"
# 7 days: long enough to bridge any realistic compute-perf incident while the
# underlying query cost is worked separately, short enough to self-expire if the
# beat is fully retired.
_MAIN_LAST_GOOD_TTL = 604800

# Queue 274 (#1479): DB-level statement_timeout for the main compute session.
# The beat's ONLY prior bound was Celery's hard time_limit=1560s, whose SIGKILL of
# the worker BYPASSES get_task_session()'s finally (rollback/close/dispose), so the
# Postgres backend running the heavy CTE is ORPHANED (client-disconnect is not
# detected — client_connection_check_interval=0) and runs unbounded. A measured
# 28h41m orphan (pid 3537972, 2026-07-28) pinned the global xmin horizon
# (backend_xmin 13755940, ~29,200 txns behind the next holder) so autovacuum could
# not reclaim dead tuples: futures_markets reached 663K dead > 591K live (>52%
# bloat), roughly DOUBLING every scan and pushing the healthy ~905s compute past
# the 1500s window. This SET LOCAL is the DB-level backstop the horizon precompute
# and backfill_winners already carry (gotchas #38/#39 — a native asyncpg socket
# read can outlive a Python-level signal). Set at the soft limit (< the 1560s hard
# limit) so a wedged statement is cancelled by Postgres — RELEASING its xmin — well
# before Celery SIGKILLs the worker into an orphan. A healthy sub-limit compute is
# unaffected and byte-identical; a cancelled one raises QueryCanceledError mid-CTE
# -> unpublishable -> fail-closed (last-good preserved), never a partial publish.
_MAIN_COMPUTE_STMT_TIMEOUT_MS = 1500 * 1000


def _sql_str_tuple(values) -> str:
    """Render a set/iterable of plain strings as a deterministic SQL IN-list.

    Sorted so the emitted SQL (and therefore the query plan cache key) is stable
    across runs. Values are constants defined in this module — never user input —
    and any embedded quote is doubled defensively so the fragment can't break out
    of its literal.
    """
    return "(" + ", ".join(f"'{v.replace(chr(39), chr(39) * 2)}'" for v in sorted(values)) + ")"


def _sql_pair_tuple(pairs) -> str:
    """Render (source, category) pairs as a deterministic SQL row-value IN-list.

    D12 (#1978, CAL-P150). The sibling of :func:`_sql_str_tuple` for a predicate
    that must be scoped by BOTH dimensions. Sorted for a stable plan cache key,
    same defensive quote-doubling, same module-constants-only contract.

    Row-value syntax — ``(a, b) IN ((x, y))`` — rather than an OR-chain, because
    an OR-chain of two-column tests is where a scoping bug hides in plain sight:
    a missing pair of brackets turns "kalshi AND crypto" into "kalshi OR crypto"
    and the predicate silently swallows every Kalshi cell on the board.
    """
    rendered = ", ".join(
        "(" + ", ".join(f"'{v.replace(chr(39), chr(39) * 2)}'" for v in pair) + ")"
        for pair in sorted(pairs)
    )
    return "(" + rendered + ")"


def _main_payload_is_publishable(response: Any) -> bool:
    """True if a computed calibration payload is complete enough to publish (Queue 272).

    A partial/empty payload must never replace a valid cache entry (Item 1). The
    canonical calibration compute always returns non-empty ``buckets`` and a
    positive ``total_outcomes`` on the production population, so an empty/zero
    result is a degraded compute (statement_timeout mid-CTE, cancelled build) that
    is NOT written to either key. Read-side/publish-side only — never mutates data.
    """
    return (
        isinstance(response, dict)
        and bool(response.get("buckets"))
        and (response.get("total_outcomes") or 0) > 0
    )

# Queue #262: canonical calibration-population fingerprint. Surfaced on every
# population-derived surface (horizon diagnostics, /calibration/examples,
# bucket-debug, snapshot-health) so a future population change is VISIBLE across
# all consumers. Bump when _calibration_population_ctes changes materially.
# q267 (C44 #1): the crude volume=0 eligibility gate was retired in favor of the
# bid/trade evidence predicate, so bid-bearing zero-volume Kalshi rows now enter
# the population and no-evidence phantoms are counted (not silently pre-dropped).
# Queue 299 (#1012): result-authority + exclusivity-evidence repair. Four
# read-side rungs change the published population, so the version is bumped and
# the publish gate's ±5% population / 20% per-category drift guard is told this
# drift is INTENTIONAL rather than a collapse:
#   1. no-winner markets (a market that graded NOBODY is UNKNOWN, not a set of
#      losses) — "draw graded as two losses", all-loser markets, ungraded rows,
#   2. draw-authority (a draw-capable duel captured without a draw member),
#   3. orphan partitions (a 'field' with <=1 captured member), and
#   4. exclusivity EVIDENCE gating normalization — the default-true
#      ``mutually_exclusive`` flag is no longer accepted as proof of a partition.
#
# The sequence Queue 299 chose — land the population change under the CURRENT
# version, let the publish gate MEASURE the drift against the published q267
# baseline, then bump as a deliberate follow-up once the numbers were reviewed —
# ran to completion. The gate's rejection report was the exact-SHA census it was
# supposed to be (#1954/#1956/#1959-#1968, one per hourly beat), the numbers were
# reviewed, and this is that follow-up.
#
# q268 (CAL-P070, Fable directive 2026-08-18; #1680 / #1955). Ruling 009's freeze
# on this file lifts for exactly this commit.
#
# READ THIS BEFORE BUMPING AGAIN — q268 IS THE LAST BUMP THAT MAY MEAN "TIME
# PASSED", AND IT ONLY MEANS THAT BECAUSE THE ALTERNATIVE DID NOT EXIST YET.
#
# What actually changed on 2026-08-18: nothing about the methodology. The
# population CTEs, the truth allowlist, the liquidity filter, the normalization
# and the metrics are byte-identical to q267. The build simply took sixteen days,
# during which the season backfill and the never-graded drains graded whole
# cohorts underneath it, so the completed candidate came in +17.9% (706,290 ->
# 832,650) and the gate's symmetric ±5% band refused it — every hour, more
# certainly the longer the build ran, because the guard could not tell "we
# changed which rows qualify" from "sixteen days happened" (#1955).
#
# Answering ordinary time with a version bump is how a guard is drained of
# meaning, so the bump does not ship alone: the same commit gives the gate the
# discriminator it was missing. ``population_predicate_fingerprint`` states, on
# the artifact itself, WHICH RULE produced it; growth on a provably identical
# predicate is now admitted and recorded rather than refused. The next long build
# publishes with no bump at all, which is the only reason this one is defensible.
#
# And it does NOT repeat 2026-08-02. That attempt was reverted within the hour
# because ``snapshot_verdict`` refuses an artifact whose version is not the one
# the deployed build expects, so the instant the dyno booted expecting the new
# version BOTH the live key and the 7-day last-good became ``wrong_version`` and
# /calibration went dark until the next successful build — unbounded, on a task
# known to overrun its window (#1479/#1513), on the exact page #1517 exists to
# keep lit. That hole is closed below by
# ``COMPATIBLE_PREVIOUS_POPULATION_VERSIONS``.
#
# COSTS, stated plainly rather than discovered later: this bump moves
# ``_main_input_fingerprint`` (the version is one of its inputs), so the 128-unit
# staged-futures bank is discarded and the first q268 build climbs ~14 hourly
# beats from zero. Fable ruled that spend acceptable and the bank was worth
# little: 119 of its 125 checkable units were censuses of an older population, so
# publishing it would have published a sixteen-day smear.
#
# ---------------------------------------------------------------------------
# q268 -> q269 (CAL-P211, 2026-09-01): THE FREEZE-LIFT BATCH MOVED THE
# METHODOLOGY, SO THE VERSION HAS TO SAY SO.
#
# The batch that is already on master and deployed (D5 dedup, D21, D22, D13
# per-market, D12 crypto tuple, RULE E) does not count the same rows q268
# counted. Measured on the completed 128-unit rebuild of 2026-09-01, it removes
# 201,508 outcomes: 930,149 -> 728,641, i.e. -21.7%, with crypto going 4,625 ->
# 0 (D12) and economics 43,270 -> 10,501 (RULE E).
#
# Under an UNBUMPED q268 the publish gate reads that as unexplained data loss
# and refuses — ``population_shrink`` at -21.7% against a -5% limit, plus ten
# ``category_collapse`` codes — and a refusal CLEARS THE CHECKPOINT, so the
# rebuild that earned the refusal is binned and the next beat starts from zero.
# That is not a flaky gate to be waited out: the drift is a deterministic
# property of the deployed predicate, so every future rebuild is refused for the
# same reason, forever, while burning a full Postgres-saturating build each
# time. The gate is RIGHT — the only lawful way to publish a deliberate
# methodology shrink is to declare it, which is what this bump does.
# ``evaluate_publish`` returns before Rule 2 and Rule 3 when the version is
# bumped (``calibration_publish_gate.py``, "if verdict.version_bumped").
CALIBRATION_POPULATION_VERSION = "q269"

#: The predecessor versions whose PUBLISHED artifacts this build declares
#: comparable with its own — the explicit, bounded rollover window that the
#: ratified version-rollover contract
#: (``tests/evals/fixtures/calibration_version_rollover_contract.json``, cases
#: ``deploy-before-candidate`` / ``previous-complete-bounded``) has always
#: required and that no code has ever supplied. The route serves an artifact on
#: this list DATED, DEGRADED, PROVENANCED and READ-ONLY — never as the current
#: curve, never seeding the new version — for as long as it stays inside the
#: ordinary serve age bound, and refuses it after (``previous-expired-refused``).
#:
#: THE ENTRY BAR IS A PROOF, NOT A PREFERENCE. ``q267`` is listed because q268
#: changes no methodology whatsoever: same CTEs, same truth allowlist, same
#: filters, same metrics, same population *unit* (so the contract's
#: ``POPULATION_UNIT_NEEDS_RULING`` does not arise). Its numbers therefore mean
#: exactly what the page says they mean, which is the whole of CAL-P017's
#: objection to serving a cross-version artifact — that ruling is honoured here,
#: not overridden. **A bump that DOES move the methodology must ship this list
#: EMPTY and accept the dark window**, because then the banner really would be
#: papering over numbers that mean something else.
#:
#: CAL-P211 IS EXACTLY THAT CASE, so the list is now EMPTY and stays empty. The
#: q268 artifact counts 201,508 outcomes that q269's predicate excludes on
#: purpose; serving it dated-and-degraded under a q269 label would be the
#: papering-over this docstring names, not a kindness to the page. The list is
#: not a dial to be turned down when the dark window is inconvenient — its entry
#: bar is a proof of methodological identity, and q268 cannot meet it.
COMPATIBLE_PREVIOUS_POPULATION_VERSIONS: tuple[str, ...] = ()

#: The version carried by the artifact /calibration is ACTUALLY serving — the
#: one a rollover has to keep servable to stay lit. Measured, not assumed:
#: ``GET /api/calibration`` returned ``population_version: "q268"`` with
#: ``generated_at 2026-08-31T04:37:36.703361+00:00`` at 2026-09-01 22:51 PT.
#:
#: It is separate from :data:`CALIBRATION_POPULATION_VERSION` because the two
#: genuinely differ during a rollover — that gap IS the dark window — and the
#: guard that checks the lit path needs to name the outgoing version without
#: hard-coding a literal that goes stale one bump later.
PREVIOUS_PUBLISHED_POPULATION_VERSION = "q268"

#: The population version for which an EMPTY
#: :data:`COMPATIBLE_PREVIOUS_POPULATION_VERSIONS` — and therefore a DELIBERATE,
#: user-visible dark window on /calibration — was consciously accepted.
#:
#: This exists so the dark window can never be inherited. Emptying the
#: compatibility list is the one edit in this module that takes a live page down,
#: and the previous guard could not tell "we accepted this cost" from "the list
#: happens to be empty" — a distinction worth nothing until the NEXT bump, when
#: an empty list left lying around would take the page dark again with nobody
#: having decided it. Naming the exact version it was accepted FOR makes the
#: acceptance expire on its own: bump to q270 without re-declaring and the guard
#: in ``tests/test_calibration_result_authority_299.py`` fails closed.
#:
#: 🔴 STAGED, NOT YET ACCEPTED. As of 2026-09-01 22:5x PT this branch is built
#: and gated but UNMERGED, and the acceptance it records is Alex's to give (it is
#: on his desk as ``alex-inbox/calibration-020`` + ``-021``). Do not merge this
#: branch until he has said go. What the decision buys: the alternative is not
#: "a lit page" but a page frozen forever at 2026-08-31, because under q268 every
#: rebuild is refused and binned.
#:
#: MEASURED COST (phase ledger ``calibration:main:phase_ledger``, generation
#: 1788326490717): ``staged:unit_ms_mean`` 91,844 ms over 128 units = ~3.3 h of
#: build, and the plan's own ``units_per_beat`` 13 puts an UNASSISTED recovery at
#: ceil(128/13) = 10 hourly beats. The attended one-off drain lands between the
#: two. It is a window measured in hours, not the ~26 h first estimated.
POPULATION_VERSION_DARK_WINDOW_ACCEPTED: str | None = "q269"

#: Queue 300D Item 1 — the REPRESENTATIVE TIE AUTHORITY, versioned separately
#: from the population.
#:
#: C126 proved the representative window had no deterministic tie-break: two
#: complementary binary sides equidistant from 50% could each be chosen across
#: plans or rebuilds, so a published observation's identity, winner and bucket
#: were free to move with no data change. Alex's 2026-08-03 ruling settles it —
#: after distance from 50%, the immutable canonical outcome ID breaks the tie,
#: with no Yes/No preference.
#:
#: This is NOT a population-version bump, and the distinction is the point. The
#: population's METHODOLOGY (eligibility, truth, liquidity, normalization,
#: metrics) is untouched; the same questions with the same count publish. What
#: moves is WHICH side of an exactly-tied book represents a handful of them —
#: a one-time identity delta, reported on its own census rung rather than
#: hidden inside a population change. It rides in the INPUT FINGERPRINT so any
#: future change to the authority invalidates every carried read, exactly as a
#: query edit does.
REPRESENTATIVE_TIE_AUTHORITY = "canonical-outcome-id/v1"

# L2-73 (#999 §E): the corrections log — "what we found and fixed" — served in the
# payload so web + native render the same trust panel. Static seed from the #997
# record; each entry is a real, dated data-quality fix. When a new class is fixed,
# add a row here (single source of truth for the panel).
CALIBRATION_CORRECTIONS = [
    {
        "date": "2026-07-09",
        "title": "Polymarket hockey sign-flip",
        "rows": 36207,
        "description": "Player-threshold props stored the OVER probability against "
                       "the Under/No side (gotcha #17). Re-graded the Polymarket half "
                       "(poly MCE 4.68 → 4.01).",
    },
    {
        "date": "2026-07-08",
        "title": "Premature golf resolutions",
        "rows": 230,
        "description": "Golf markets resolved at cp=1.0 with future dates were "
                       "un-resolved so they grade against the real result.",
    },
    {
        "date": "2026-07-09",
        "title": "DataGolf survivorship exclusion",
        "rows": None,
        "description": "Symmetric exclusion of did-not-play / withdrew outcomes so the "
                       "golf curve isn't inflated by non-participants.",
    },
    {
        "date": "2026-07-09",
        "title": "Polymarket no-bid placeholder exclusion",
        "rows": None,  # live count in payload.poly_placeholder_filter.excluded
        "description": "Illiquid poly props stamped a no-signal ~0.50 midpoint "
                       "(Gamma synthetic prices, gotcha #19). #151's census proved "
                       "no-bid near-0.50 outcomes resolve at 0.10–0.28 (placeholders) "
                       "vs 0.43–0.55 for has-bid coin-flips. Now excluded from the "
                       "curve by bid presence — read-side only, no regrade.",
    },
    {
        "date": "2026-07-09",
        "title": "Malformed-binary exclusion",
        "rows": None,  # live count in payload.malformed_binary_filter
        "description": "Resolved 2-outcome mutually-exclusive markets must have "
                       "exactly one winner. Zero-winner (void) and two-winner "
                       "(impossible) markets are data artifacts, not scoreable "
                       "outcomes — now excluded from the curve. Census: ~43K "
                       "both-false + ~1.5K both-winner across all categories. "
                       "Read-side only, no regrade.",
    },
    {
        "date": "2026-07-09",
        "title": "Golf FIELD one-sided-ask placeholder exclusion",
        "rows": None,  # live count in payload.golf_placeholder_filter.excluded
        "description": "Golf winner/round-leader outcomes priced >=0.80 in a "
                       "mutually-exclusive market with >=2 such outcomes are "
                       "Kalshi one-sided-ask placeholders (mex probs can't have "
                       "two 80%+ outcomes; 98.6% lose). Excluded; genuine single "
                       "leaders (82% win) stay in. Read-side only, no regrade.",
    },
    {
        "date": "2026-07-10",
        "title": "Multi-candidate probability normalization",
        "rows": None,  # live count in payload.mex_normalization.normalized_outcomes
        "description": "Mutually-exclusive markets with >=3 outcomes are one "
                       "question and must sum to ~1.0, but sources stamp each "
                       "candidate at its one-sided ask so the sum inflated to "
                       "2.4-5.3 (census 2026-07-09). Now each such market's "
                       "probabilities are divided by the per-market sum. Only "
                       "genuine single-winner partitions are touched; multi-winner "
                       "ladders/independent binaries and voids are excluded. "
                       "Read-side only, no regrade.",
    },
    {
        "date": "2026-07-11",
        "title": "Soccer 2-way (draw-omission) historical exclusion",
        "rows": None,  # live count in payload.soccer_2way_filter.excluded
        "description": "Soccer game-odds were captured 2-way (home/away only) — "
                       "no draw column — so every soccer moneyline row summed to "
                       "~1.0 and structurally dropped the ~25% draw mass (#1011), "
                       "in BOTH the events aggregate and the per-bookmaker curve. "
                       "That over-predicted home/away uniformly across all ~20 "
                       "leagues (EPL 17.6pp, Switzerland 15.0pp, Turkey 7.6pp). "
                       "The draw was never stored so these rows can't be "
                       "reconstructed — historical soccer moneyline is excluded "
                       "from the curve (league-scoped by the soccer_* key); soccer "
                       "spreads/totals are kept. Forward fix = 3-way capture "
                       "(#1011 draw column). Read-side only, no regrade.",
    },
    {
        "date": "2026-07-12",
        "title": "Esports match-bundle exclusion",
        "rows": None,  # live count in payload.esports_multi_bundle_filter.excluded
        "description": "Polymarket packs a whole esports match (cumulative "
                       "Total-Kills Over/Under ladders per game, per-game winners, "
                       "first-blood props) into one non-partition market with >=3 "
                       "outcomes. Cumulative Over rungs legitimately resolve many "
                       "YES at once (gotcha #17), so the market has >=2 winners and "
                       "its prices neither sum to ~1.0 (can't be normalized) nor "
                       "bucket as a clean prediction — the counter-class #157 "
                       "refuses to normalize (OPS-557: 93,629 outcomes over-predict "
                       "+9.2pp, avg cp-sum 17.9). The >=3-outcome sibling of the "
                       "malformed-binary filter; excluded from the curve, never "
                       "re-graded (the many-YES grading is correct). Read-side "
                       "only, no regrade.",
    },
    {
        "date": "2026-07-13",
        "title": "Kalshi player-prop threshold exclusion — corrected discriminator (Queue #186)",
        "rows": None,  # live count in payload.kalshi_prop_threshold_filter.excluded
        "description": "Kalshi player-prop 'Player: N+' OVER markets (points/"
                       "assists/goals/total-bases/hits/HR/strikeouts/rebounds/"
                       "blocks) capture a settled post-game quote as the closing "
                       "line (Kalshi commence_time ≈ resolution time, gotcha #14) "
                       "— '6+ total bases' at 0.96, impossible as a real OVER. "
                       "Queue #186 (2026-07-13) corrects the Queue #167 filter: a "
                       "snapshot-level verify over the Calibration Sentinel's "
                       "flagged series (#1069–#1073) disproved #167's 'keep the "
                       "real-bid rows' rule — real-bid rows are corrupt too (a "
                       "scorer and a non-scorer in one market both carry cp 0.995 "
                       "with a live 0.99 bid). The honest discriminator is the "
                       "CURVE PRICE, not the bid. Now excluded: (A) rows in the "
                       "degenerate settlement-collapse band (curve price >= 0.90, "
                       "which resolves 0.11–0.48 across every series), and (B) the "
                       "whole NHL goal-family (category='hockey'), corrupt at every "
                       "band (opening 0.82→winrate 0.05) though its resolution is "
                       "verified sane (5.24 scorers/game) — an illiquid degenerate "
                       "capture, not a sign-flip. Below the band the liquid NBA/MLB "
                       "series are an honest diagonal and are KEPT, bringing their "
                       "high-band actual within ~10pp of predicted (NBAPTS -2pp, "
                       "MLBKS -2pp). No regrade: the sign-flip premise is disproven "
                       "and no honest price exists to recover (gotcha #21). "
                       "Read-side only.",
    },
]

# Horizons: (label, days_before_resolution)
_HORIZONS = [
    ("T-30", 30),
    ("T-7", 7),
    ("T-1", 1),
    ("T-0", 0),
]

_MIN_OUTCOMES_PER_HORIZON = 50

# Item 1 (Queue #220/221): the time-horizon task ran all 4 horizons in one
# process and blew the 600s soft limit (0/27 successes over 3 days; last success
# 2026-07-18, then 12 consecutive SoftTimeLimitExceeded at 600.9s). Each horizon
# is a LATERAL last-snapshot probe over ~539K eligible resolved non-event
# outcomes against the largest table — ~150s each, so 4 in one run overrun the
# limit. Fix = bound + chunk + resumable cursor:
#   * per-horizon statement_timeout bounds any single query (never runs away);
#   * completed horizons are persisted to a WIP accumulator keyed by label, so a
#     later horizon's slowness never discards an already-computed one;
#   * an internal wall-clock deadline (well under the 600s soft limit, sized so a
#     freshly-started horizon can run its full statement_timeout and still finish
#     before the limit) stops the run cleanly and resumes the remaining horizons
#     on the next beat. The full 4-horizon payload assembles across 1-2 runs and
#     is only published (and the WIP cleared) once every horizon is present.
# Runs every 6h; a full refresh lands within ~12h, comfortably inside the 24h TTL.
_TIME_HORIZON_WIP_KEY = "bainluck:calibration:time_horizon:wip"
# Per-horizon statement_timeout (seconds). Bounds a single LATERAL probe.
_HORIZON_STMT_TIMEOUT_S = 300
# Internal deadline (seconds). A horizon is only started if it can run its full
# statement_timeout and still finish before this deadline, which itself sits far
# enough under the 600s soft limit that the run always returns cleanly.
_HORIZON_DEADLINE_S = 560

# #997 App Store ship-gate: a per-category / per-sport reliability chart below
# this many resolved outcomes is statistical noise (a handful of resolutions
# swings MCE by tens of points), not a calibration signal. The gate is enforced
# server-side so web AND future native both inherit it — the published
# by_category / by_sport lists are pre-filtered, and the threshold itself is
# shipped in the payload so clients don't hardcode their own bar. Tunable at
# runtime via the Redis key ``calibration:min_category_outcomes`` (no deploy).
_DEFAULT_MIN_CATEGORY_OUTCOMES = 1000


def _get_min_category_outcomes(rc) -> int:
    """Redis-tunable minimum resolved-outcome count for a chartable sub-category.

    Falls back to _DEFAULT_MIN_CATEGORY_OUTCOMES on any miss/parse error so the
    gate can never silently disable itself (a malformed key must not open the
    thin-sample floodgates)."""
    try:
        raw = rc.get("calibration:min_category_outcomes") if rc is not None else None
        if raw is None:
            return _DEFAULT_MIN_CATEGORY_OUTCOMES
        val = int(raw)
        return val if val >= 0 else _DEFAULT_MIN_CATEGORY_OUTCOMES
    except Exception:
        return _DEFAULT_MIN_CATEGORY_OUTCOMES


# ---------------------------------------------------------------------------
# #940 phase-1: published-calibration liquidity filter (Kalshi-first).
#
# A resolved outcome counts toward the PUBLISHED calibration numbers only if at
# least one snapshot ever showed a real bid (yes_bid > 0) OR a trade
# (last_price > 0). A pure one-sided, never-traded placeholder price (no bid and
# no trade, ever) is a price we never actually discovered, so it is excluded
# from the calibration denominator. This is a READ-SIDE filter only — it never
# mutates is_winner or calibration_probability (gotcha #21).
#
# Kalshi-only for now: Polymarket's per-outcome volume backfill is still sparse
# (phase-2, deferred + Alex-gated). The /calibration page surfaces the
# included/excluded counts + this rule so the filter is transparent, never silent.
#
# KALSHI_LIQUIDITY_EXISTS is the production SQL form (embedded in the main
# calibration query, where ``fo`` is futures_outcomes and ``vm`` carries source).
# outcome_is_calibration_liquid() is the canonical, unit-tested Python definition
# of the same predicate — keep the two in sync.
#
# Queue #267 (C44 #1): this evidence predicate is ALSO the canonical Kalshi
# ELIGIBILITY boundary. It supersedes the crude ``COALESCE(fo.volume,-1) != 0``
# proxy (#827) which excluded confirmed-zero-volume rows BEFORE this predicate
# could run — silently dropping the bid-bearing ``volume=0`` rows this contract
# promises to keep (the fixture ``outcome_is_calibration_liquid(0.3, 0) is True``).
# ``kalshi_liquidity_exists_sql()`` re-emits the predicate against an arbitrary
# source/outcome-id alias so the population scans that DON'T compute ``is_liquid``
# as a column (field candidates/divisor, golf over-subscription, fair-fight) apply
# the SAME evidence contract instead of the volume proxy. It evaluates to TRUE for
# every non-Kalshi source (poly keeps its own placeholder-band policy downstream)
# and for Kalshi rows with real bid/trade evidence; FALSE only for Kalshi rows
# that NEVER showed a bid or trade — the true no-evidence phantoms.
# ---------------------------------------------------------------------------
def kalshi_liquidity_exists_sql(
    source: str = "vm.source", outcome_id: str = "fo.id"
) -> str:
    """Source-aware Kalshi bid/trade evidence predicate (Queue #267).

    Returns the SQL boolean that is TRUE unless ``source`` is Kalshi AND no
    snapshot ever showed ``yes_bid > 0`` or ``last_price > 0`` for ``outcome_id``.
    Non-Kalshi sources are always TRUE here (their liquidity policy is applied
    elsewhere); the caller keeps the volume column out of eligibility entirely.
    """
    return (
        f"({source} <> 'kalshi' OR EXISTS (\n"
        f"        SELECT 1 FROM futures_odds_snapshots fos\n"
        f"        WHERE fos.outcome_id = {outcome_id}\n"
        f"          AND (fos.yes_bid > 0 OR fos.last_price > 0)))"
    )


KALSHI_LIQUIDITY_EXISTS = kalshi_liquidity_exists_sql()

KALSHI_LIQUIDITY_RULE_TEXT = (
    "Excludes outcomes that never showed a real bid (yes_bid > 0) or trade "
    "(last_price > 0) in any snapshot — pure one-sided, never-traded placeholder "
    "prices. Applied to Kalshi only; never mutates resolutions."
)

# L2-76 (#151/#997): curve-side exclusion of the Polymarket no-bid PLACEHOLDER
# class. Gamma stamps synthetic `outcomePrices` at ~0.50 with no orderbook, so an
# illiquid poly outcome sits near 0.50 but is not a real 50/50. #151's census
# proved the discriminator is BID PRESENCE: near-0.50 poly outcomes that NEVER
# showed a bid/trade resolve at 0.10–0.28 (placeholders), while has-bid ones
# resolve at 0.43–0.55 (genuine coin-flips — MUST stay in). So exclude poly
# outcomes in the [0.45, 0.55] band with NO snapshot bid/trade evidence at all.
# Read-side only (gotcha #21) — never mutates is_winner / calibration_probability.
# The bid check uses SNAPSHOT provenance (evidence captured over the outcome's
# life), not the current bid — live bids can clear on resolution.
POLY_PLACEHOLDER_EXCLUDE = (
    "(vm.source = 'polymarket'\n"
    "     AND COALESCE(fo.calibration_probability, fo.opening_probability) >= 0.45\n"
    "     AND COALESCE(fo.calibration_probability, fo.opening_probability) <= 0.55\n"
    "     AND NOT EXISTS (\n"
    "        SELECT 1 FROM futures_odds_snapshots fos\n"
    "        WHERE fos.outcome_id = fo.id\n"
    "          AND (fos.yes_bid > 0 OR fos.last_price > 0)))"
)

POLY_PLACEHOLDER_RULE_TEXT = (
    "Excludes Polymarket outcomes near 0.50 (cp in [0.45, 0.55]) that never showed "
    "a real bid or trade in any snapshot — Gamma synthetic placeholder prices, not "
    "genuine coin-flips (#151 census: no-bid near-0.50 resolve at 0.10–0.28 vs "
    "has-bid at 0.43–0.55). Read-side only; never mutates resolutions."
)

# Queue #220/221 Item 3 — the EXCLUSION-SYMMETRY census.
#
# The never-traded liquidity filter is ASYMMETRIC across sources: Kalshi excludes
# EVERY never-bid/never-traded outcome (all price bands, KALSHI_LIQUIDITY_EXISTS),
# but Polymarket only excludes never-traded outcomes in the near-0.50 placeholder
# band (POLY_PLACEHOLDER_EXCLUDE). A Polymarket outcome that NEVER traded but sits
# outside [0.45, 0.55] (e.g. a 0.10 or 0.92 Gamma synthetic) is therefore still
# counted in the published curve — an asymmetry that Kalshi does not have.
#
# This queue MEASURES that asymmetry (it does not change curve behavior — closing
# the asymmetry by excluding all poly never-traded is a separate, Alex-gated
# decision; gotcha #21 keeps everything read-side). POLY_NEVER_TRADED is the
# all-bands never-traded predicate; the census counts the cohort still IN the
# curve (never traded AND outside the placeholder band).
POLY_NEVER_TRADED = (
    "(vm.source = 'polymarket'\n"
    "     AND NOT EXISTS (\n"
    "        SELECT 1 FROM futures_odds_snapshots fos\n"
    "        WHERE fos.outcome_id = fo.id\n"
    "          AND (fos.yes_bid > 0 OR fos.last_price > 0)))"
)

# Per-source liquidity/never-traded exclusion policy — the parameterization the
# queue asked for. Declaring each source's policy in one structure (instead of
# two ad-hoc SQL fragments) makes the asymmetry explicit, surfaces it in the
# /calibration payload, and turns "close the asymmetry" into a one-field change.
SOURCE_LIQUIDITY_EXCLUSIONS: dict[str, dict[str, Any]] = {
    "kalshi": {
        "never_traded_excluded": "all_bands",
        "rule": KALSHI_LIQUIDITY_RULE_TEXT,
    },
    "polymarket": {
        "never_traded_excluded": "placeholder_band_0.45_0.55",
        "rule": POLY_PLACEHOLDER_RULE_TEXT,
        "asymmetry_note": (
            "Unlike Kalshi (all-bands), Polymarket only excludes never-traded "
            "outcomes in the near-0.50 placeholder band; never-traded outcomes "
            "outside that band are still counted (see poly_never_traded_in_curve)."
        ),
    },
}

# L2-79 Item 1 (#997/#1010): curve-side exclusion of MALFORMED BINARIES. A
# resolved, mutually-exclusive 2-outcome market must have exactly ONE winner.
# Zero winners (both-false = a void/malformed resolution) or two winners
# (both-winner = impossible / double-graded) is a data artifact, not a real
# outcome to score — leaving it in either drags the curve down (both-false
# losers) or fakes a perfect winner (both-winner). The census (2026-07-09) found
# ~43K both-false + ~1.5K both-winner such markets across every category
# (tennis 17.4K, soccer 8.2K, esports 8.1K the largest). Standalone both-false
# markets are already dropped by the clean_vms has_winner>=1 gate; this catches
# the GROUPED both-false losers that leak in via a group/event virtual-market
# AND every both-winner market (which clean_vms keeps, has_winner>=1). Read-side
# only (gotcha #21) — never mutates is_winner / calibration_probability.
MALFORMED_BINARY_RULE_TEXT = (
    "Excludes resolved 2-outcome mutually-exclusive markets whose winner count is "
    "not exactly 1 — zero winners (void/malformed resolution) or two winners "
    "(impossible / double-graded). These are data artifacts, not scoreable "
    "outcomes. Read-side only; never mutates resolutions."
)

# L2-79 Item 2 (#940/#762): curve-side exclusion of golf FIELD/winner ONE-SIDED-
# ASK PLACEHOLDERS. In a mutually-exclusive golf winner/round-leader market, at
# most ONE outcome can legitimately price >=0.80 (mex probabilities must sum to
# ~1). Kalshi stamps illiquid player-winner outcomes at the high ASK (~0.88–0.99)
# with no real two-sided book, so many outcomes in the same market cluster at
# >=0.80 and ~98.6% resolve as losers. The census (2026-07-09) confirmed the
# discriminator: markets with >=2 outcomes in the >=0.80 band produce 954 losers
# vs 14 winners (98.6% loss @ cp 0.93 — placeholder), while markets with exactly
# ONE outcome >=0.80 (a genuine leader/heavy favorite) produce 304 winners vs 65
# losers (82% win @ cp 0.88 — well-calibrated, MUST stay in). So exclude the
# high band ONLY in over-subscribed markets; the low-priced field and genuine
# single leaders are untouched. Read-side only (gotcha #21).
GOLF_PLACEHOLDER_HIGH_BAND = 0.80

GOLF_PLACEHOLDER_RULE_TEXT = (
    "Excludes golf winner/round-leader outcomes priced >=0.80 in mutually-exclusive "
    "markets that have >=2 outcomes in that band — one-sided-ask placeholder prices "
    "(mex probabilities can't have two 80%+ outcomes; ~98.6% resolve as losers). "
    "Genuine single-leader markets (one outcome >=0.80, 82% win) stay in. "
    "Read-side only; never mutates resolutions."
)

# Queue #157 (#1012): curve-side MULTI-CANDIDATE NORMALIZATION.
#
# A resolved, mutually-exclusive market with >=3 outcomes is a partition of ONE
# question — its outcome probabilities MUST sum to ~1.0. But Kalshi/Polymarket
# stamp each candidate at its one-sided ASK, so the per-market cp sum inflates
# well past 1 (census 2026-07-09, mex >=3 markets, cp = COALESCE(cal_prob,
# opening): economics avg 2.37, entertainment 3.09, tech 2.23, football 4.63,
# cricket 1.50, esports 1.91). Leaving the raw over-confident prices in drags ECE
# hard (isolated per-category sim, raw->normalized: football 17.98->10.50,
# entertainment 11.80->4.73, cricket 10.62->6.31, tech 6.91->5.00, economics
# 3.28->2.64 — no category got worse). The fix: divide each eligible outcome's cp
# by the per-market cp sum when that sum exceeds MEX_NORMALIZE_THRESHOLD, so the
# market sums to 1. Markets already ~1.0 (sum <= threshold) are left untouched.
#
# COUNTER-CLASS GUARD (the critical safety): a genuine mex partition resolves with
# EXACTLY ONE winner. Cumulative-threshold ladders ("Over 3.5 maps" + "Over 4.5
# maps") and independent binaries mislabeled mutually_exclusive resolve with 2+
# winners — their probabilities legitimately sum >1 and must NOT be normalized
# (#155 pass3 ladder lesson; gotcha #23's own caveat). The census confirmed the
# discriminator at scale: of the >1.15-sum mex >=3 markets, 6,892 have EXACTLY one
# winner (normalize) vs ~391 multi-winner (ladders/independent — untouched) and
# 336 zero-winner (voids — already excluded). Winner count is taken over ALL
# outcomes, mirroring the malformed_binaries CTE's structure test. Read-side only
# (gotcha #21) — never mutates is_winner / calibration_probability. Writer-side
# durable normalization (stamp at capture) is follow-up scope on #1012.
MEX_NORMALIZE_THRESHOLD = 1.15

MEX_NORMALIZE_RULE_TEXT = (
    "Normalizes resolved mutually-exclusive markets with >=3 outcomes and exactly "
    "one winner whose per-market probability sum exceeds 1.15 — each outcome's "
    "probability is divided by the market sum so the partition sums to ~1.0 (fixes "
    "one-sided-ask over-confidence; census 2026-07-09 found sums of 2.4-5.3 in "
    "economics/entertainment/tech/football). Multi-winner ladders / independent "
    "binaries (2+ winners) and voids (0 winners) are the counter-class and left "
    "untouched, as are markets already summing to ~1.0. Read-side only; never "
    "mutates resolutions."
)


def market_needs_mex_normalization(
    n_eligible: int, n_winners: int, cp_sum: float | None
) -> bool:
    """True if a mutually-exclusive market's curve prices should be normalized (Queue #157).

    Canonical, unit-tested definition mirroring the ``mex_norm_markets`` CTE: a
    resolved mutually-exclusive market qualifies for per-market probability
    normalization iff it has >=3 eligible outcomes, EXACTLY one winner (a genuine
    single-winner partition — not a multi-winner ladder / independent-binary set,
    not a zero-winner void), and its eligible cp sum exceeds
    ``MEX_NORMALIZE_THRESHOLD`` (a sum already ~1.0 needs no correction). The
    caller must have already confirmed the market is a single-winner partition —
    ``mutually_exclusive=true`` OR ``market_type='field'`` (#254: 65K field
    markets carry the mutually_exclusive flag unset yet are definitionally one
    winner among >2 competitors). Read-side only (gotcha #21) — the divisor is
    the eligible cp sum; each outcome's normalized probability is ``cp / cp_sum``.
    """
    return (
        n_eligible >= 3
        and n_winners == 1
        and cp_sum is not None
        and cp_sum > MEX_NORMALIZE_THRESHOLD
    )


# Queue #257 Item 1 — the FIELD-COMPLETENESS invariant before normalization.
#
# market_needs_mex_normalization decides a market is a *candidate* for per-market
# normalization (>=3 eligible, one winner over ALL outcomes, over-confident sum).
# But normalizing divides each survivor's cp by the per-market cp sum so the
# published partition sums to ~1.0 — and that is only correct when the survivors
# ARE the whole field. If a published per-outcome exclusion (liquidity, poly
# placeholder, esports bundle, golf placeholder, Kalshi prop threshold, weather
# wide-spread) removed one or more members, the surviving cp sum is smaller than
# the true full-field sum, so dividing the survivors by it INFLATES them (the
# winner's true share is smaller than survivor_cp / survivor_sum). Worse, if the
# excluded member WAS the winner, normalizing the losers to sum 1.0 is pure
# fiction. Such a PARTIAL field must be EXCLUDED from the curve with a
# machine-readable reason, never "normalized over survivors".
#
# Completeness is proven STRUCTURALLY: there is no stored expected-member count
# (market_type='field' is a shape from app.utils.market_shape — ">2 competitors,
# one wins" — with no member cardinality), so the source-backed invariant is "no
# eligible member of this field was excluded" (survivor_n == eligible_n) AND "the
# winner survived" (survivor_win_n == 1) AND "still a partition" (survivor_n >= 3).
# When that holds, the survivor cp sum equals the divisor, so the bucketed field
# sums to ~1.0 by construction; otherwise the field is excluded. (This detects
# EXCLUSION-INDUCED partiality, which is what the curve controls; members that
# were never ingested at all are undetectable without an expected-member count —
# a documented forward limitation, not fabricated here.) Read-side only (gotcha
# #21) — never mutates is_winner / calibration_probability.
FIELD_COMPLETENESS_RULE_TEXT = (
    "A resolved mutually-exclusive / field market is normalized (each outcome's "
    "probability divided by the per-market sum) ONLY when its captured partition "
    "is COMPLETE — every eligible member survives every per-outcome exclusion and "
    "the winner is among the survivors — so the published field sums to ~1.0. If a "
    "published exclusion removed any member, the field is PARTIAL: normalizing the "
    "survivors would inflate them (their true combined share is < 1.0), so the "
    "whole market is excluded from the curve with a repair reason instead of being "
    "normalized over survivors. Completeness is structural (no stored expected-"
    "member count exists); exclusion-induced partiality is what is detected. "
    "Read-side only; never mutates resolutions."
)


def field_is_complete_for_normalization(
    eligible_n: int, survivor_n: int, survivor_win_n: int
) -> bool:
    """True if a normalization-candidate field is COMPLETE enough to normalize (Queue #257).

    Canonical, unit-tested mirror of the ``field_completeness`` CTE gate. Given a
    market already confirmed a normalization candidate by
    ``market_needs_mex_normalization`` (>=3 eligible, one winner over all
    outcomes, sum > threshold), it is normalized over its survivors ONLY when:

      * ``survivor_n == eligible_n`` — NO eligible member was removed by a
        published per-outcome exclusion (the survivor cp sum therefore equals the
        full-field divisor, so the normalized partition sums to ~1.0), AND
      * ``survivor_win_n == 1`` — the winner itself survived (normalizing losers
        to sum 1.0 when the winner was excluded would be fiction), AND
      * ``survivor_n >= 3`` — the survivor set is still a partition, not a
        collapsed 1-2 outcome remnant.

    When this is False for a candidate, the market is a PARTIAL field and its
    outcomes are EXCLUDED from the published curve (``is_field_incomplete``) with
    a machine-readable reason — never normalized over the survivors. Read-side
    only (gotcha #21).
    """
    return (
        survivor_n == eligible_n
        and survivor_win_n == 1
        and survivor_n >= 3
    )


# Queue #259 Item 1 — the sum-to-1 INVARIANT for a published normalized field.
#
# field_is_complete_for_normalization decides a candidate field is complete enough
# to normalize (cp / per-market sum). But the ``deduped`` CTE then applies two MORE
# filters to every ``is_multi`` row: an extreme-tail cut (adj > 0.005 AND adj < 0.98)
# and a mode-price cut (drop a price shared by > max(eligible*0.5, 2) members). A
# complete normalized field IS ``is_multi`` (>=3 eligible), so before this fix those
# filters ran AFTER normalization and could delete a member the completeness gate
# had already counted — publishing < 1.0 (C14's 0.99/0.20/0.001 -> tail dropped ->
# ~99.9%; a uniform field -> its modal price wipes every member). The tail/mode cuts
# are placeholder heuristics for the NON-partition multi pool, so the fix EXEMPTS
# ``is_mex_normalized`` rows: a complete field publishes ALL its members and the
# partition still sums to ~1.0. This is the executable mirror of that ``deduped``
# decision. Read-side only (gotcha #21).
def published_normalized_field_probabilities(
    raw_cps: list[float], *, apply_tail_mode_filters: bool = False
) -> list[float]:
    """Published normalized probabilities for a COMPLETE single-winner field (Queue #259).

    ``raw_cps`` are the raw curve prices of the field's members (already confirmed a
    complete normalization candidate by ``market_needs_mex_normalization`` +
    ``field_is_complete_for_normalization``). Returns each member's PUBLISHED
    probability = ``cp / sum(cp)``.

    With ``apply_tail_mode_filters=False`` (the shipped ``deduped`` behavior after the
    Queue #259 invariant fix) EVERY member is published, so the returned list sums to
    ~1.0. ``apply_tail_mode_filters=True`` reproduces the OLD pre-fix behavior — the
    extreme-tail (>0.005 AND <0.98) and mode-price cuts run after normalization and
    can drop members, so the sum falls below 1.0. Tests assert the fixed path holds
    the invariant and the old path violates it (the counterexamples).
    """
    cp_sum = sum(raw_cps)
    if cp_sum <= 0:
        return []
    normalized = [cp / cp_sum for cp in raw_cps]
    if not apply_tail_mode_filters:
        # Queue #259 invariant fix: a complete partition is published whole.
        return normalized
    # Legacy (buggy) behavior kept for contrast: drop extreme tails + modal prices.
    from collections import Counter

    counts = Counter(normalized)
    eligible = len(normalized)
    mode_threshold = max(eligible * 0.5, 2)
    mode_prices = {p for p, c in counts.items() if c > mode_threshold}
    return [
        p
        for p in normalized
        if 0.005 < p < 0.98 and p not in mode_prices
    ]


# #762: void-resolution filter (mostly DataGolf "Make the Cut" markets).
#
# A resolved outcome whose resolution_source is did_not_play / withdrew is a
# VOID — the player never teed off, so there was no cut outcome to score. These
# are all graded is_winner=False by the resolver, but counting them as
# "predicted X% and lost" dragged DataGolf's actual rate down across every bin
# (~49% of resolved DataGolf outcomes were did_not_play, inflating MCE to
# ~13.7pp). The main calibration query already drops these from the denominator
# (resolution_source NOT IN (...)); this surfaces the count + rule so the
# exclusion is transparent, never silent — the same contract as the #940
# liquidity_filter. Read-side only; never mutates is_winner (gotcha #21).
VOID_RESOLUTION_SOURCES = ("did_not_play", "withdrew")

VOID_FILTER_RULE_TEXT = (
    "Excludes resolved outcomes for players who never participated "
    "(did_not_play / withdrew) — VOIDs with no real outcome to score, not "
    "losses. Mostly DataGolf 'Make the Cut' markets; never mutates resolutions."
)


def outcome_is_calibration_void(resolution_source: str | None) -> bool:
    """True if an outcome is a VOID excluded from the published calibration set.

    Canonical, unit-tested definition of the #762 rule: an outcome whose
    ``resolution_source`` marks non-participation (did_not_play / withdrew) is a
    void — the underlying event never occurred for that player — so it is dropped
    from the calibration denominator. Read-side only (gotcha #21); the inverse of
    "counts toward calibration" for this dimension.
    """
    return resolution_source in VOID_RESOLUTION_SOURCES


# Queue #158 (#1011): curve-side exclusion of HISTORICAL SOCCER GAME-ODDS captured
# 2-way (draw omitted). The Odds API soccer h2h is 3-way (home/draw/away) but the
# events table has NO draw column, so every soccer game-odds row was stored as a
# 2-way home/away split summing to ~1.0 — structurally omitting the ~25% draw mass.
# That over-predicts home/away systematically (ops-lane census #1010/#1011: EPL
# predicted 0.573 home vs ACTUAL 0.397 = 17.6pp over; Switzerland 15.0pp; Turkey
# 7.6pp; uniform across all ~20 leagues = one mechanism, not model bias). The draw
# was never captured, so these historical rows cannot be reconstructed/re-graded —
# they are excluded from the published curve, league-scoped by the ``soccer_*``
# sport key. The forward fix (3-way capture into a new draw column) is #1011's
# separate schema+ingest step. Read-side only (gotcha #21) — never mutates
# scores or probabilities.
SOCCER_2WAY_EXCLUDE_PATTERN = "soccer_%"

SOCCER_2WAY_RULE_TEXT = (
    "Excludes historical soccer game-odds (moneyline) from the curve — BOTH the "
    "events aggregate (odds_api) and the per-bookmaker (odds_api_bookmaker) sources. "
    "Soccer h2h is 3-way (home/draw/away) but both stored only a 2-way home/away "
    "split summing to ~1.0, dropping the ~25% draw mass and over-predicting "
    "home/away by 7-18pp uniformly across ~20 leagues (#1011). The draw was never "
    "captured so these rows can't be re-graded; league-scoped by the soccer_* key. "
    "Soccer spreads/totals (genuinely 2-way) are kept. Forward fix = 3-way capture. "
    "Read-side only; never mutates resolutions."
)


def category_is_soccer_2way_excluded(category: str | None) -> bool:
    """True if an events-table category (sport key) is an excluded soccer league.

    Canonical, unit-tested definition of the Queue #158 (#1011) rule mirroring the
    ``s.key NOT LIKE 'soccer_%'`` events-curve filter: every soccer league game-odds
    row was captured 2-way (draw dropped at ingest), so it is excluded from the
    published moneyline curve. Read-side only (gotcha #21).
    """
    return bool(category) and category.startswith("soccer_")


# Queue #159 (#1010): esports malformed-MULTI "match bundle" curve exclusion.
#
# Polymarket packs a whole esports match into ONE non-partition market —
# cumulative "Total Kills Over/Under X.5 in Game N" ladders (Over 17.5, 18.5,
# ... 54.5), per-game winners, first-blood props, series totals — flattened into
# a single market with dozens of outcomes (market 128754: 73 outcomes). Because
# the Over rungs are CUMULATIVE, a high-kill game legitimately resolves many YES
# at once (gotcha #17), so the market resolves with >=2 winners. That makes it
# the exact counter-class #157's normalization deliberately REFUSES: the prices
# neither sum to ~1.0 (multiple partitions mashed together — can't be normalized
# by one per-market divisor) nor bucket as a clean single prediction. OPS-557
# census (2026-07-11): n=93,629 poly outcomes, winrate 0.395 vs cp 0.487
# (+9.2pp), avg per-market cp-sum 17.9; sub-bands <25%-win +23.7pp (longshot Over
# rungs that missed) / 25-50% +10.1pp / >50% -4.1pp (near-certain Over rungs that
# hit). The >=2-winner grading is CORRECT for cumulative ladders, so these rows
# are EXCLUDED from the curve, never re-graded — the >=3-outcome sibling of the
# malformed-binary filter. Read-side only (gotcha #21). esports-scoped: the same
# poly bundle shape is well-calibrated in basketball/tennis/hockey (~+1.5pp), so
# a blanket exclusion would drop good data; the general sweep is #160's sentinel.
ESPORTS_MULTI_BUNDLE_CATEGORY = "esports"

# D12 (#1978, CAL-P150) — the ruled non-exclusive-bundle exclusion gains ONE
# (source, category) tuple. Freeze exception GRANTED by Alex 2026-08-30
# (RULINGS-BATCH, D12: "delete via the approved exclusion list; the two OUR-bugs
# it was hiding stay filed"), on the design banked in
# artifacts/cal-p121/RULE-DESIGN-kalshi-crypto.md §4 (RULE C).
#
# WHY THIS CELL. `kalshi/crypto` is 4,566 published rows at ECE 7.61 pp against
# a 3.0 bar — rank 6, 20,999 excess-outcomes — and 99.9% of it is the
# non-exclusive bundle shape this predicate already names. 625 markets produce
# 4,566 rows, so one gold print is counted 7.31 times, and the rungs of one
# ladder are near-deterministically related: if gold is above $3,360 it is above
# $3,350. Both arms of the ruled gate — the realization test (>=2 winners) and
# the structural test (published prices summing past 1.15) — condemn the same
# 4,563 rows, so there is no version of this that leaves a material cell behind.
#
# 🔴 SO THIS DOES NOT FIX RANK 6, IT DELETES IT — 4,563 rows out, 3 left, the
# cell becomes an absence. Said here rather than discovered after deploy. It is
# seventeen times larger than the same outcome already accepted for kalshi/tech
# and it is why the exception was asked for by name.
#
# 🔴 THE LABEL IS WRONG AND DELETING THE CELL DOES NOT FIX THAT. The cell is
# 99.5% METALS — gold, silver, palladium, copper, lithium, nickel — and exactly
# ONE row of it is cryptocurrency. The page today tells a reader we made 4,565
# forecasts about crypto; we made ~625 about the price of metal and one about
# Hyperliquid. This tuple fixes the first half of that sentence only. The relabel
# is RULE-DESIGN §5, it is a WRITER fix, and it stays filed.
#
# 🔴 AND DO NOT REACH FOR THE ADMIN BUTTON. `_cleanup_crypto_impl`
# (app/tasks/retention.py, exposed at app/routes/admin_data_quality.py) deletes
# futures_markets / futures_outcomes / futures_odds_snapshots
# `WHERE llm_sport_category = 'crypto'`. Its predicate is exactly the label that
# is wrong. Pressing it to "clean up rank 6" would permanently destroy 3,922
# legitimate commodities markets and all their price history because an LLM
# called them crypto. It is not on the beat schedule, which is the only reason
# those rows are still alive.
#
# SCOPED BY SOURCE AS WELL AS CATEGORY, deliberately. A bare category allowlist
# entry would also act on `polymarket/crypto`, and CAL-P112 item 3 is the
# standing warning about exactly that: RULE T's category-only widening moved
# `polymarket/tech` 8.04 -> 12.62, WORSE, and that cell is still UNMEASURED. A
# (source, category) tuple cannot reach a cell nobody has folded.
# CAL-P162 (#1978) — RANK 2 lands. `(kalshi, economics)` is added on Alex's
# ruling of 2026-08-28, option (b) APPROVED WITH DISCLOSURE
# (`artifacts/cal-p114/RULE-DESIGN-kalshi-economics.md` §9, scorecard §6d):
# "the correlated intraday index-ladder rungs stop entering the published curve
# (5.29 -> 2.61pp, cell stays material and PASSES), AND the removed rows are
# disclosed on the page as a named, counted exclusion."
#
# WHY THIS CELL. 99.7% of `kalshi/economics` is cumulative intraday index and
# commodity ladders — KXNASDAQ100U, KXINXU, KXDJI — published as N independent
# rungs. `KXDJI-26JUL2814` is 76 outcomes, 76 winners, published price sum
# 72.48; the median KXDJI market is 35 rungs / 24.5 winners / sum 21.66. These
# rows were never competing answers to one question.
#
# 🔴 THIS TUPLE IS INERT — AND WORSE THAN INERT — WITHOUT RULE E'S SUM ARM.
# 86.3% of the cell is caught by the >=2-winner arm, but the 13.4% remainder is
# THE SAME LADDERS on a day the index landed on one rung. Excluding only the
# multi-winner half takes the cell 5.29 -> 5.73: measurably WORSE THAN DOING
# NOTHING (§6b policy B, "RULE T alone"). The `(source, category)` allowlist and
# the structural sum arm are ONE deliverable and must never be split across two
# deploys. `test_rank2_tuple_never_ships_without_the_structural_arm` is the
# guard that says so in the suite rather than in a comment.
#
# 🔴 AND THE CELL LANDS *AT* ITS BAR, NOT UNDER IT. RULE E alone measures 3.00
# against a 3.0 bar (§6b policy C). E+E2+E3 would land it at 2.61 — but E2 is
# under scorecard §6i's **13-CAL HOLD** ("E2 must not land before 12-CAL is
# decided") and is deliberately absent here, so this cell crosses off by 0.00 pp
# of margin. Said before deploy, not discovered after.
#
# SCOPED BY SOURCE AS WELL AS CATEGORY, and this cell is the specimen that
# proved the column is needed: under a category-only allowlist the same rule
# takes `polymarket/economics` 3.91 -> 17.75 (CAL-P114 §5). One extra column in
# a tuple is the difference between crossing rank 2 off and silently destroying
# rank 15.
NONEXCLUSIVE_BUNDLE_EXCLUDED_CELLS = (
    ("kalshi", "crypto"),
    ("kalshi", "economics"),
)


# ---------------------------------------------------------------------------
# CAL-P168 (#1978) — RANK 1, `polymarket/baseball`. K' = R1 + R2 + R3 + M1.
#
# Design + ruling: `artifacts/cal-p117/RULE-DESIGN-polymarket-baseball.md`
# (Alex, 2026-08-28: **EXCLUDE NOW + FIX WRITER**). Port scope:
# `artifacts/cal-p165/PORT-SCOPE-rank1-polymarket-baseball.md`. Prediction
# recorded BEFORE this code: `artifacts/cal-p168/PREDICTION.md`.
#
# 🔴 THIS IS NOT RULE E AND MUST NEVER BE WIRED INTO IT. The two filters share a
# payload key and a disclosure bullet; they share NO predicate. Extending RULE E
# to this cell was MEASURED AND REFUSED: `is_nonexclusive_bundle` on
# polymarket/baseball reads **8.35** and RULE E's own sum arm reads **9.02**
# against a 4.71 control — nearly double the error (design §2). The sum ladder
# here is not monotone: the best-calibrated class in this cell is the one that
# is NOT a partition (sum 2-5, 2.28 pp) and the worst is the one that looks most
# like one (sum <= 1.15, 9.02 pp). **Whatever is wrong here is not the bundle
# shape**, so `('polymarket','baseball')` is deliberately ABSENT from
# NONEXCLUSIVE_BUNDLE_EXCLUDED_CELLS above and carries its own allowlist below.
#
# WHAT IS WRONG IS OUR WRITER, NOT THE MARKET (design §3). Market 56675315,
# `Miami Marlins vs. Houston Astros - Player Props`, 37 legs, published sum
# 19.13: `Yordan Alvarez: Home Runs O/U 1.5` was quoted 0.0355 by the market and
# PUBLISHED by us at 0.5005. The opening column is a coherent monotone prop
# ladder; the published column is a spray of 0.5000/0.5005/0.5050/0.9050/0.0950
# that carries no relationship to it. Cell-wide, corr(published, open) falls
# 0.897 -> 0.677 inside these containers, and 242 legs are published in
# [0.45,0.55] where only 39 OPENED there — a **6.2x manufacture of coin flips**
# on a population whose realized base rate is 0.18. The curve publishes
# COALESCE(calibration_probability, opening_probability) (gotcha #144 /
# ruling 103), so the curve publishes the spray.
#
# 🔴 THE CONTROL EARNS THE RULE THE RIGHT TO EXIST. Rows that moved just as far
# from their open but landed somewhere OTHER than 0.50 read ECE 12.62 with a
# TWO-SIDED -2.92 gap, while rows forced INTO [0.45,0.55] read 44.36 with
# ECE == gap (every bin errs one way: published ~0.50, loses). Ordinary line
# movement and a placeholder overwrite are distinguishable, so M1 may name one
# without deleting the other. Do not widen M1's band or drop its drift floor
# without re-folding that control.
#
# EVERY ARM IS LOAD-BEARING; ONLY THE CONJUNCTION PASSES (design §4/§7):
#
#     policy                       n        ECE    holdout OLD / NEW
#     control                      41,127   4.71   6.83 / 4.96
#     R1+R2 (the banked pair)      39,878   4.19   fails
#     R1+R2+R3                     17,961   2.79   2.99 / 2.56
#     K' = R1+R2+R3+M1             17,827   2.71   2.90 / 2.63   <- ships
#
# 🔴 DROPPING R2 ALONE PUTS THE CELL BACK OVER THE BAR AT 3.10, even though R2's
# solo delta is -0.11 pp. A rule whose solo delta is a rounding error can still
# be the arm that decides a pass — CAL-P112's "T and E ship together" on a new
# cell. Do not prune an arm because it looks inert in isolation.
#
# 🔴 AND THE HOLDOUT REFUSED FOUR POLICIES THE POOLED NUMBER ADMITTED. R1+R2+M1
# reads **2.16** — the best pooled ECE in the whole design — and leaves the OLD
# half at 5.13, because M1 is a FORWARD signature (1,525 of its 1,739 props rows
# are in the NEW half). Shipping the best pooled number would have fixed nothing
# about the back catalogue. Likewise M2 (the >0.10 rung) pushes OLD back over at
# 3.06 and is deliberately NOT an arm, and R3-restricted-to-sum>15 passes pooled
# at 2.94 while failing BOTH halves. **Never re-tune these on a pooled number.**
#
# THE HONEST EDGE, carried from design §4 rather than discovered after deploy:
# 2.71 against a 3.0 bar is **0.77σ under it** (σ = 50/√17,827 = 0.37). A pass,
# and not a comfortable one. And because the excluded population is expected to
# RETURN (see the temporary map below), this cell will be re-scored when it does.

#: K''s own `(source, category)` allowlist — NOT RULE E's, for the measured
#: reason above. Scoped by SOURCE as well as category: CAL-P114 measured what
#: category-only scoping costs (`polymarket/economics` 3.91 -> 17.75), and that
#: correction is inherited here rather than re-derived.
PLAYER_PROPS_PLACEHOLDER_EXCLUDED_CELLS = (("polymarket", "baseball"),)

#: R1's exact value. Scoped to 0.5000 and deliberately NOT a tolerance band: the
#: neighbouring 0.5005 has the identical signature at 1/18th the size, and
#: widening to a band turns a self-evidencing exact match into a judgement call
#: (CAL-P094). That widening is a separate ruling with its own census.
PLAYER_PROPS_HALF_SPIKE_EXACT_VALUE = "0.5000"

#: R3's title match. A rule keyed on a provider's market TITLE is a real
#: weakness, named in design §6.1: it breaks the day Polymarket renames the
#: container. §7 measured the candidate successor (M1) and found it a
#: COMPLEMENT, not a replacement — M1 removes 168 rows the name arm cannot see
#: (ECE 12.87, forced-to-half legs in non-props markets) and R3 removes 19,980
#: rows M1 cannot see (the props residual, 28.36 on the OLD half). The weakness
#: is reduced, not removed, and the design ships with it stated.
PLAYER_PROPS_NAME_PATTERN = "%player props%"

#: M1's band and drift floor (design §7). The band is where the writer parks a
#: manufactured price; the floor is what separates it from ordinary line
#: movement. Both are pinned by the control class described above.
PLAYER_PROPS_MIDPOINT_BAND_LO = 0.45
PLAYER_PROPS_MIDPOINT_BAND_HI = 0.55
PLAYER_PROPS_FORCED_DRIFT_MIN = 0.25


def player_props_pair_shape_columns(outcome_alias: str = "fo") -> str:
    """R1/R2's per-market pair aggregates, as a SELECT column list. Pure.

    Aggregated over ALL outcomes of the market — the same basis
    ``market_result_shape`` always used, so the shape reflects the market as
    CAPTURED rather than as published. This mirrors the ``pr`` rollup in
    ``scripts/calibration_cell_exact.py`` that measured the design, and
    ``test_player_props_placeholder_kprime.py`` asserts the two agree.
    """
    o = outcome_alias
    return (
        f"COUNT(*) FILTER (WHERE lower(btrim({o}.name)) = 'over') AS pp_named_over,\n"
        "                    "
        f"COUNT(*) FILTER (WHERE lower(btrim({o}.name)) = 'under') AS pp_named_under,\n"
        "                    "
        f"COUNT(*) FILTER (WHERE ROUND({o}.opening_probability, 4) "
        f"= {PLAYER_PROPS_HALF_SPIKE_EXACT_VALUE}) AS pp_half_legs,\n"
        "                    "
        f"SUM({o}.opening_probability) AS pp_open_sum,\n"
        "                    "
        f"COUNT(*) FILTER (WHERE {o}.opening_probability IS NOT NULL) "
        "AS pp_open_legs,\n"
        "                    "
        f"SUM(COALESCE({o}.calibration_probability, {o}.opening_probability)) "
        "AS pp_pub_sum,\n"
        "                    "
        f"COUNT(*) FILTER (WHERE COALESCE({o}.calibration_probability, "
        f"{o}.opening_probability) IS NOT NULL) AS pp_pub_legs"
    )


def two_leg_over_under_clauses(shape_alias: str = "mrs") -> str:
    """The shape half of BOTH pair arms: exactly two legs, named Over/Under.

    Hoisted because R1 and R2 agree on what an O/U pair IS and two copies of
    one predicate in one query is how a mirror stops mirroring (CERT-403B, at
    the shape level). Rendered without its own parentheses so each arm appends
    its value clauses inside one bracket.
    """
    a = shape_alias
    return (
        f"{a}.n_outcomes = 2 AND {a}.pp_named_over = 1 AND {a}.pp_named_under = 1"
    )


def half_spike_pair_predicate(shape_alias: str = "mrs") -> str:
    """R1 — TRUE when BOTH legs of an O/U pair open at exactly 0.5000. Pure.

    ``pp_half_legs = 2`` with ``n_outcomes = 2`` says *every* leg of this market
    is exactly 0.5000, which is the arithmetic signature of the writer defect:
    the Over leg took 0.5 from an untraded market's precomputed price and the
    Under leg was written as its complement ``1 - 0.5`` (CAL-P094: 924/924 such
    Under legs carry neither a bid nor an ask). **A market with ONE 0.5000 leg
    is an ordinary even-money price and is KEPT** — that criterion lives in the
    predicate rather than in prose.
    """
    a = shape_alias
    return f"({two_leg_over_under_clauses(a)} AND {a}.pp_half_legs = 2)"


def published_pair_coherence_predicate(shape_alias: str = "mrs") -> str:
    """R2 — the OPENING pair sums to 1 but the PUBLISHED pair does not. Pure.

    Both legs leave. The opening pair being coherent is what makes this a
    statement about our publication rather than about the market: the market
    quoted a consistent two-sided price and the published copy of it does not
    add up. Tolerance is the shipped ``PAIR_SUM_TOLERANCE`` (0.02), imported
    rather than restated so it cannot drift from the writer-side rule.
    """
    a = shape_alias
    return (
        f"({two_leg_over_under_clauses(a)}\n"
        f"                        AND {a}.pp_open_legs = 2 AND {a}.pp_pub_legs = 2\n"
        f"                        AND ABS({a}.pp_open_sum - 1) <= {PAIR_SUM_TOLERANCE}\n"
        f"                        AND ABS({a}.pp_pub_sum - 1) > {PAIR_SUM_TOLERANCE})"
    )


def player_props_container_predicate(
    name_expr: str = "mi.market_name", sum_expr: str = "bps.cp_sum"
) -> str:
    """R3 — a Player Props container whose published prices sum past 1.15. Pure.

    🔴 THE THRESHOLD IS RULE E'S OWN CONSTANT (``MEX_NORMALIZE_THRESHOLD``), NOT
    A FITTED ONE, and that is the single most useful fact in the design: the
    holdout REFUSED sum > 15 (passes pooled 2.94, fails both halves) and sum > 5
    (OLD 3.06, over the bar) and admitted the threshold that was already in the
    codebase. It is doing real work rather than passing everything — the props
    containers BELOW it (1,077 rows) read 2.15 and 2.61 and are left in.
    """
    return f"({name_expr} ILIKE '{PLAYER_PROPS_NAME_PATTERN}' AND {sum_expr} > {MEX_NORMALIZE_THRESHOLD})"


def forced_midpoint_predicate(outcome_alias: str = "fo") -> str:
    """M1 — the published price landed in [0.45,0.55] from an open >0.25 away.

    Reads ``calibration_probability`` DIRECTLY rather than ``{curve_price}``,
    and that is deliberate on two counts. Whether our writer overwrote a price
    is a property of THAT column, not of whichever horizon a reader is on — so
    M1 is horizon-invariant, and a row's membership cannot change because the
    curve is being re-expressed at a different snapshot. And a row with no
    ``calibration_probability`` at all was never overwritten: it is the
    ``opening_probability`` FALLBACK (design §3's 123-row class, ECE 2.78), it
    is KEPT, and a NULL here yields NULL from BETWEEN and falls through.
    """
    o = outcome_alias
    return (
        f"({o}.calibration_probability BETWEEN {PLAYER_PROPS_MIDPOINT_BAND_LO} "
        f"AND {PLAYER_PROPS_MIDPOINT_BAND_HI}\n"
        f"                     AND ABS({o}.calibration_probability - "
        f"{o}.opening_probability) > {PLAYER_PROPS_FORCED_DRIFT_MIN})"
    )


PLAYER_PROPS_PLACEHOLDER_RULE_TEXT = (
    "Excludes Polymarket baseball rows whose PUBLISHED price is ours rather than "
    "the market's. Four arms, every one load-bearing: both legs of a two-leg "
    "Over/Under market opening at exactly 0.5000 (the placeholder pair, where the "
    "Under leg was written as 1 minus a price the Over leg never traded); a "
    "two-leg pair whose OPENING prices sum to 1 but whose PUBLISHED prices do "
    "not; a 'Player Props' container whose published prices sum past 1.15; and "
    "any row published into [0.45, 0.55] having opened more than 0.25 away. That "
    "last arm is separated from ordinary line movement by measurement, not "
    "assertion: rows that moved as far but landed elsewhere error two-sidedly "
    "and are KEPT. The market's own quote is intact in every case — only our "
    "copy of it is wrong. Read-side only; never mutates resolutions."
)

#: The cells whose exclusion ENDS when a named defect elsewhere is repaired, and
#: the condition that ends it. Rendered by the page as
#: "<cell> — returns when <condition>", so the value is a lowercase clause.
#:
#: 🔴 TEMPORARY BY DESIGN (design §9.2), and the four clauses of Alex's ruling
#: that depend on it:
#:   1. this allowlist entry is EXPECTED TO BE REMOVED — it is a hold placed on
#:      a cell while a named defect elsewhere is repaired, not permanent scope;
#:   2. the rows return as GOOD DATA — not deleted, not re-graded, not written
#:      off. When the writer publishes the market's own quote again, M1 stops
#:      matching, R3 stops carrying them, and the count falls on its own;
#:   3. the disclosure is RENDERED FROM THIS MAP, never hard-coded — when the
#:      backend stops emitting the cell the sentence leaves the page without a
#:      copy change. A hard-coded line would still be there a year after the fix;
#:   4. 🔴 THE FALSIFIER: if the writer fix lands and the TEMPORARY count does
#:      NOT empty, then design §3 was WRONG — the near-0.50 spray was not the
#:      writer — and the exclusion must be **re-argued from scratch, never
#:      extended**. An exclusion that outlives its stated cause is one with no
#:      stated cause.
#:
#: Note what this does NOT promise. R1 and R2 are the HISTORICAL residue of the
#: same family — 1,258 of their 1,284 rows sit in the OLD holdout half — and
#: fixing the writer forward does not un-write the back catalogue, so those arms
#: are expected to STAY. What empties is the M1/R3 population.
#:
#: 🔴 CERT-647 (CAL-P170) — THAT PARAGRAPH WAS TRUE AND THE SHIP DID NOT OBEY IT.
#: This map was emitted unconditionally from the constant and `temporary_excluded`
#: carried the full four-arm union, so the page rendered clause 2's promise over
#: a population whose majority the paragraph above says will not return, and
#: clauses 3 and 4 were unreachable: a constant map never stops being emitted, so
#: the sentence could not leave the page and the falsifier could not fire. The
#: emission is now gated on the temporary count and the payload publishes the
#: temporary and historical cohorts separately. Clause 3 and clause 4 became
#: TRUE STATEMENTS at that commit; before it they were intentions.
#:
#: Nobody should promise the count reaches literally zero until it is measured;
#: what is promised is that the M1/R3 rows come back and THAT count falls.
PLAYER_PROPS_PLACEHOLDER_TEMPORARY_BY_CELL: dict[str, str] = {
    "polymarket/baseball": (
        "the Polymarket player-prop writer stops overwriting the market's own "
        "quote with a near-0.50 placeholder, and those forecasts are scored on "
        "the price the market actually made"
    ),
}


def nonexclusive_bundle_cell_labels() -> tuple[tuple[str, str], ...]:
    """The disclosed cells, as ``(payload label, aggregate column)`` pairs.

    CAL-P162 (#1978), Alex's ruling of 2026-08-28 on rank 2: *"the removed rows
    are disclosed on the page as a named, counted exclusion"* — and per-cell,
    because the filter is allowlisted per cell and one total would hide WHICH
    cell shrank. That is a clause of the ruling, not a nicety.

    Derived from ``NONEXCLUSIVE_BUNDLE_EXCLUDED_CELLS`` rather than restated, so
    the labels cannot drift from the tuples they describe. The esports entry is
    category-only on purpose: that arm has never been source-scoped.
    """
    labels: list[tuple[str, str]] = [(ESPORTS_MULTI_BUNDLE_CATEGORY, "nxb_cell_esports")]
    labels += [
        (f"{src}/{cat}", f"nxb_cell_{idx}")
        for idx, (src, cat) in enumerate(NONEXCLUSIVE_BUNDLE_EXCLUDED_CELLS)
    ]
    # CAL-P168 (#1978): rank 1's cells report through the SAME per-cell map,
    # because the page renders one filter as one bullet and a reader who meets
    # "N rows were removed" must meet "and part of that is coming back" in the
    # same breath rather than two bullets later (design §9.4). The LABEL is
    # shared; the PREDICATE behind it is not — these columns count
    # `is_player_props_placeholder`, never `is_esports_bundle`.
    labels += [
        (f"{src}/{cat}", f"pp_cell_{idx}")
        for idx, (src, cat) in enumerate(PLAYER_PROPS_PLACEHOLDER_EXCLUDED_CELLS)
    ]
    return tuple(labels)


#: The aggregate columns those labels name, in emission order (CAL-P164).
#:
#: Named because THREE places need this set and deriving it three times is how
#: they drift: the statement that emits the columns, the staged merge that has
#: to be TOLD they are census columns before it will accept a row carrying
#: them, and the bank-time mirror in ``calibration_staged_futures``. CAL-P162
#: emitted the columns and told neither consumer, so the first unit that
#: returned a row raised ``UndeclaredColumnError`` and no generation could bank
#: — a fail-closed merge doing exactly its job. The mirror is pinned against
#: this tuple by a characterization test; adding a cell to
#: ``NONEXCLUSIVE_BUNDLE_EXCLUDED_CELLS`` reds that pin rather than production.
NONEXCLUSIVE_BUNDLE_CELL_COLUMNS: tuple[str, ...] = tuple(
    column for _, column in nonexclusive_bundle_cell_labels()
)


def nonexclusive_bundle_cell_columns_sql() -> str:
    """One ``COUNT(*) FILTER`` per disclosed cell, for the summary aggregate.

    The aggregate this lands in is a single flat row, so the per-cell map is
    rendered as N scalar columns rather than by re-shaping the query into a
    GROUP BY — a grouped variant of this scan is the shape that times out
    (see the row-path notes in the db-query rules).
    """
    parts = [
        "COUNT(*) FILTER (WHERE is_esports_bundle AND category = "
        f"'{ESPORTS_MULTI_BUNDLE_CATEGORY}') AS nxb_cell_esports"
    ]
    for idx, (src, cat) in enumerate(NONEXCLUSIVE_BUNDLE_EXCLUDED_CELLS):
        parts.append(
            "COUNT(*) FILTER (WHERE is_esports_bundle "
            f"AND source = '{src}' AND category = '{cat}') AS nxb_cell_{idx}"
        )
    # CAL-P168 (#1978): rank 1's per-cell counts. A DIFFERENT flag on the same
    # row shape — the cell conjunct is kept anyway so the column counts what its
    # label says even if the flag's own scope is ever widened.
    for idx, (src, cat) in enumerate(PLAYER_PROPS_PLACEHOLDER_EXCLUDED_CELLS):
        parts.append(
            "COUNT(*) FILTER (WHERE is_player_props_placeholder "
            f"AND source = '{src}' AND category = '{cat}') AS pp_cell_{idx}"
        )
    return ",\n                    ".join(parts)


def _nonexclusive_bundle_cell_passthrough_sql(alias: str = "ls") -> str:
    """``MAX(...)`` pass-through of the per-cell columns for the outer aggregate."""
    return ",\n                ".join(
        f"MAX({alias}.{col}) AS {col}" for _, col in nonexclusive_bundle_cell_labels()
    )


NONEXCLUSIVE_BUNDLE_FILTER_RULE_TEXT = (
    "Excludes non-exclusive BUNDLES — markets of >=3 outcomes that are not proved "
    "single-winner partitions, where independent questions were packed into one "
    "market. A market qualifies when it resolved with >=2 winners OR when its "
    "published prices sum past 1.15: a genuine partition sums to ~1 whatever it "
    "resolves to, so the sum identifies a bundle even on a day it happened to "
    "land on a single rung. Scoped per ruled (source, category) cell — never by "
    "category alone, which was measured to take polymarket/economics from 3.91 to "
    "17.75 pp. The rows are dropped from the curve, never re-graded: the many-YES "
    "grading of a cumulative ladder is correct. Read-side only; never mutates "
    "resolutions."
)

# CAL-P162 (#1978): clause 3 of Alex's ruling — "nobody later reads the smaller
# curve as a fixed one" — is NOT carried here. It is page copy, hard-coded in
# `frontend/app/calibration/page.tsx` and pinned by
# `calibrationNonexclusiveBundleDisclosure.test.tsx` (6 tests, mutation-checked:
# softening the closing clause reds it). A backend copy of the same sentence
# would be a second hand-maintained rendering of one fact, which is the defect
# this file's own D12 comment warns about — and the backend copy would be the
# one nobody notices has drifted, because nothing renders it.


ESPORTS_MULTI_BUNDLE_RULE_TEXT = (
    "Excludes esports 'match bundle' markets — Polymarket packs a whole match "
    "(cumulative Total-Kills Over/Under ladders per game, per-game winners, "
    "first-blood props) into one non-partition market with >=3 outcomes that "
    "resolves with >=2 winners. Because the Over rungs are cumulative, many "
    "resolve YES at once (gotcha #17), so the prices neither sum to ~1.0 (can't "
    "be normalized — multiple partitions mashed) nor bucket as a clean prediction "
    "(OPS-557 census: 93,629 outcomes, winrate 0.395 vs cp 0.487 = +9.2pp, avg "
    "per-market cp-sum 17.9). The >=3-outcome sibling of the malformed-binary "
    "filter and the exclusion complement of #157's counter-class guard. The "
    "many-YES ladder grading is correct, so these are excluded from the curve, "
    "never re-graded. Read-side only; never mutates resolutions. "
    # D12 (#1978, CAL-P150). The published text has to say the filter is no
    # longer esports-only, or the page describes a rule that has not been in
    # force since this shipped. Kept generic and pointed at `excluded_cells`
    # rather than naming the cell twice: the list is derived from the constant,
    # this sentence is not, and two hand-maintained copies of one fact is how
    # the comment that hid D5 for months came to exist.
    "Since 2026-08-30 the same structural test also removes individually ruled "
    "(source, category) cells that are dominated by this shape — see "
    "`excluded_cells` for the current list, each of which is a separate ruling "
    "with its own measured evidence, not a widening of the esports rule. "
    # CAL-P162 (#1978) RULE E. The published text has to say the test is no
    # longer a realization test, because a reader who assumes ">=2 winners"
    # cannot account for the rows that left.
    "Since 2026-08-31 the shape test is STRUCTURAL as well as realized: a market "
    "of >=3 outcomes that is not a proved-exclusive partition is excluded when it "
    "resolved with >=2 winners OR when its published prices sum past 1.15. A "
    "genuine partition sums to ~1 whatever it resolves to, so the sum is what "
    "identifies a bundle that happened to land on a single rung — the class the "
    ">=2-winner test could never see. Read-side only; never mutates resolutions."
)


def market_is_esports_multi_bundle(
    category: str | None,
    n_outcomes: int,
    n_winners: int,
    *,
    source: str | None = None,
    cp_sum: float | None = None,
    exclusivity_proved: bool = False,
) -> bool:
    """True if a resolved market is an esports match-bundle excluded from the curve (Queue #159).

    Canonical, unit-tested definition mirroring the ``esports_multi_bundles`` CTE:
    an esports market with >=3 outcomes that resolved with >=2 winners is a
    Polymarket match bundle (cumulative Total-Kills Over ladders + per-game
    winners + props mashed into one non-partition market; gotcha #17/#23). The
    >=2-winner test is the discriminator — a genuine single-winner partition
    resolves with EXACTLY one winner — the same signal #157's counter-class guard
    uses to REFUSE normalization, here used to EXCLUDE from the published curve.
    Outcome/winner counts are over ALL outcomes of the market, mirroring the
    malformed_binaries CTE. Read-side only (gotcha #21) — never mutates is_winner;
    the many-YES cumulative-ladder grading is correct, so the rows are dropped
    from the curve rather than re-graded.
    """
    # CAL-P162 (#1978) RULE E: the shape test is now STRUCTURAL. The old call
    # was `market_is_nonexclusive_bundle(n_outcomes, n_winners)` — realization
    # only — and the 1-winner tail it could not see is the entire published
    # residue of `polymarket/esports` and 13.4% of `kalshi/economics`. The
    # >=2-winner arm is preserved verbatim inside the structural test, so every
    # market the old rendering caught is still caught.
    #
    # `cp_sum` / `exclusivity_proved` are keyword-only WITH defaults for the same
    # reason `source` is: a caller that did not say must not be able to trip a
    # wider rule by accident. The defaults reproduce the OLD behaviour exactly
    # (no sum => realization arm only; not proved => nothing suppressed), which
    # is what keeps the four pre-existing call sites honest.
    if not market_is_nonexclusive_bundle_structural(
        n_outcomes, n_winners, cp_sum, exclusivity_proved=exclusivity_proved
    ):
        return False
    if category == ESPORTS_MULTI_BUNDLE_CATEGORY:
        return True
    # D12 (#1978, CAL-P150). The mirror has to move with the CTE or it stops
    # being a mirror — and a mirror that has silently stopped mirroring is the
    # defect this whole queue keeps finding (D5's comment said the join carried
    # two columns; it said so for months).
    #
    # ``source`` is keyword-only WITH a default so the four existing call sites
    # keep working, and the default is None rather than a source string: None
    # means "the caller did not say", and a caller that did not say must not be
    # able to trip a (source, category) rule by accident. The cost is that a
    # caller which SHOULD pass a source and does not gets the old answer, which
    # is why `test_the_mirror_and_the_cte_agree_on_the_ruled_cells` reads the
    # ruled tuples out of the constant rather than restating them.
    return source is not None and (source, category) in NONEXCLUSIVE_BUNDLE_EXCLUDED_CELLS


# ---------------------------------------------------------------------------
# Queue 299 (#1012) — RESULT AUTHORITY and EXCLUSIVITY EVIDENCE.
#
# r339's cricket ladder found the first failing layer is NOT "the market is bad
# at cricket" (rung 5, never reached) but two structural layers above it:
# markets whose RESULT was never established, and markets treated as
# mutually-exclusive partitions on no evidence beyond a column whose default is
# True. C119's 20-case corpus fixed the contract: exclusivity is decided by
# EVIDENCE, never by a category label and never by the observed winner count
# alone; where evidence cannot distinguish a loss from a draw / no-result /
# ungraded row, the row is excluded as UNKNOWN, never published as False.
#
# All four rungs below are READ-SIDE ONLY (gotcha #21) — no stored is_winner or
# calibration_probability is mutated, nothing is re-graded, and no capture
# backfill is triggered. Each carries a rule text + live count in the payload so
# the population change is transparent, never silent.
# ---------------------------------------------------------------------------

# Rung 1 — a resolved market that graded NOBODY a winner.
#
# ``is_winner`` is NULLABLE in production (``is_nullable = YES``) but that is
# very nearly a technicality: **measured 2026-08-31, of 3,893,126 outcomes only
# 2,536 have ``is_winner IS NULL``, and EVERY ONE of them also has
# ``resolution_source IS NULL``.** The real "nobody graded this" shape is
# ``is_winner = false, resolution_source = NULL`` (778,306 rows) — which is why
# `` resolution_source IS NOT NULL`` and not ``is_winner IS NOT NULL`` is this
# repository's canonical grade predicate (`calibration_graded_share.
# GRADED_PREDICATE`). An ungraded outcome is therefore stored exactly like a
# genuine loser, and it is the truth-eligibility allowlist in
# ``ranked_outcomes`` — not any rung here — that keeps it out of the curve.
# (This comment read "is NOT NULL" until CAL-P156, which was flatly wrong; the
# measurement above replaced both that claim and the over-correction that
# followed it. See CERT-520 [P2].)
# The market-level discriminator is
# winner cardinality: a resolved multi-outcome question whose every member is
# False either (a) never had its winner captured — the omitted-draw class, where
# a drawn match makes both named sides lose (#1011), (b) is an orphan half of a
# decomposed question whose winning half lives in another market, or (c) was
# never graded at all. In every case the TRUTH IS UNKNOWN, and publishing the
# members as confident losses drags the curve down with rows that were never
# scoreable. ``malformed_binaries`` already caught this for 2-outcome
# mutually-exclusive markets; the defect is not shape-specific, so this
# generalizes the both-false leg to every shape and size (r339 census: cricket
# 240 markets / 237 eligible outcomes, soccer 4,282 / 6,920, tennis 1,141 /
# 2,397, hockey 307 / 1,475 — all-loser markets in every category).
#
# 🔴 THE ``>= 2`` FLOOR IS DELIBERATE AND THERE IS NO RUNG BELOW IT. At ONE
# outcome "nobody won" is the ordinary result of a claim that resolved No, so
# winner cardinality stops discriminating — and nothing else here needs to,
# because a lone claim nothing ever graded carries ``resolution_source = NULL``
# and never reaches ``ranked_outcomes`` at all (the allowlist at the eligibility
# filter). CAL-P156 briefly added a "rung 1b" on ``is_winner IS NULL`` to cover
# this shape; CERT-520 blocked it and the measurement above is why — the
# predicate selected a 2,536-row cohort that the eligibility filter had already
# removed, so the rung was dead code and its census would have published a
# permanent zero. **Do not re-add it.** If the ungraded lone-claim class ever
# needs to be COUNTED, that is a census before the eligibility filter, not a
# rung after it.
NO_WINNER_RULE_TEXT = (
    "Excludes every resolved market with >=2 outcomes that graded NOBODY a "
    "winner. is_winner has a False default, so an ungraded or never-captured "
    "result is stored exactly like a real loss — an all-loser market is "
    "therefore UNKNOWN truth (an omitted draw where both sides lose, an orphan "
    "half whose winner lives in another market, or a market nothing ever "
    "graded), not a set of confident losses. Generalizes the malformed-binary "
    "both-false rule from 2-outcome mutually-exclusive markets to every shape. "
    "Read-side only; never re-grades, never mutates resolutions."
)


def market_has_no_winner_authority(n_outcomes: int, n_winners: int) -> bool:
    """True if a resolved market's result was never established (Queue 299).

    Canonical, unit-tested mirror of the ``no_winner_markets`` CTE: a market
    with >=2 outcomes and ZERO winners has no captured result, so its members
    are excluded as UNKNOWN rather than published as losses. A 1-outcome market
    is judged by :func:`market_is_orphan_partition` instead (a lone Yes/No claim
    that legitimately resolved No is not an authority failure). Read-side only
    (gotcha #21).
    """
    return n_outcomes >= 2 and n_winners == 0


# Rung 2 — draw authority on a draw-capable question.
#
# A draw is a real result in soccer and cricket, so a match-winner question in
# those sports is a THREE-way partition. #1011 established the defect for the
# events curve (Odds API h2h stored 2-way home/away, dropping ~25% draw mass and
# over-predicting the named sides by 7-18pp uniformly across ~20 leagues), and
# the exclusion has been live there since Queue #158 — but scoped to the
# ``soccer_*`` sport key on ``odds_api`` / ``odds_api_bookmaker`` only. The same
# omission exists on the FUTURES curve (Kalshi/Polymarket duels), where r339
# found soccer leagues (EPL 737, FIFA_WC 631, UCL 207 outcomes) sitting inside
# the cricket cohort with no draw member at all.
#
# The predicate is SPORT-RULES authority, not category-as-shape: the category is
# consulted only to answer "can this real-world contest end in a draw?", exactly
# as the events-curve rule already does. Shape is still decided by evidence —
# only a two-competitor ``duel`` qualifies, so threshold ladders, Yes/No claims
# and genuinely 2-way questions (knockout advance, spreads, totals) are
# untouched. A duel that DOES carry a draw/tie member has complete authority and
# stays in. Census (2026-08-01): cricket 854 markets, soccer 712 — bounded.
DRAW_CAPABLE_CATEGORIES = frozenset({"soccer", "cricket"})

# Outcome names that constitute captured draw/no-result authority. Kept lowercase
# and stripped; mirrors the SQL ``lower(btrim(fo.name)) IN (...)`` membership test.
DRAW_AUTHORITY_OUTCOME_NAMES = frozenset(
    {"draw", "tie", "tied", "drawn", "no result", "no-result", "abandoned"}
)

DRAW_AUTHORITY_RULE_TEXT = (
    "Excludes two-competitor duels on draw-capable questions (soccer, cricket) "
    "that captured no draw/tie member. A draw is a real result in those sports, "
    "so the question is a three-way partition; storing only the two named sides "
    "drops the draw mass and grades a drawn match as two losses (#1011: 7-18pp "
    "over-prediction of the named sides across ~20 leagues). The draw was never "
    "captured, so these rows cannot be re-graded — they are excluded as UNKNOWN. "
    "Extends the events-curve soccer 2-way rule to the Kalshi/Polymarket futures "
    "curve. The category answers only 'can this contest be drawn?'; shape is "
    "still decided by evidence (duel), so ladders, Yes/No claims and genuinely "
    "2-way questions stay in, as do duels that DO carry a draw member. "
    "Read-side only; never mutates resolutions."
)


def market_omits_draw_authority(
    category: str | None,
    market_type: str | None,
    n_outcomes: int,
    draw_member_count: int,
) -> bool:
    """True if a draw-capable duel lacks the draw member it needs (Queue 299).

    Canonical, unit-tested mirror of the ``draw_authority_markets`` CTE. The
    contest must be draw-capable by the rules of the sport
    (:data:`DRAW_CAPABLE_CATEGORIES`), the market must be a two-competitor
    ``duel`` with exactly 2 outcomes, and NO outcome may name a draw/tie. A duel
    carrying a draw member has complete authority and returns False, as does any
    non-duel shape (ladders/claims are not match-winner questions). Read-side
    only (gotcha #21).
    """
    return (
        category in DRAW_CAPABLE_CATEGORIES
        and market_type == "duel"
        and n_outcomes == 2
        and draw_member_count == 0
    )


# Rung 3 — orphan partitions.
#
# ``market_type='field'`` is the shape classifier's verdict ">2 named
# competitors, one wins". A field that captured ONE member (or none) is a
# partition with its siblings missing: its lone member's price is a fragment of
# a distribution we never saw, and its result cannot be checked against the rest
# of the field. r339 found 278 such Polymarket markets in cricket alone (avg
# probability sum 0.514, 127 with zero winners). Deliberately narrow: a 1-outcome
# CLAIM (a Kalshi/Poly Yes/No question) is a complete, scoreable prediction and
# is NOT touched — only a market whose own declared shape is a field is judged
# incomplete at <=1 member.
ORPHAN_PARTITION_RULE_TEXT = (
    "Excludes 'field' markets (>2 named competitors, one wins) that captured "
    "<=1 member — an orphan half of a partition whose siblings are missing, so "
    "its lone price is a fragment of a distribution never observed and its "
    "result cannot be checked against the rest of the field. Scoped to the field "
    "shape only: a standalone Yes/No claim with one outcome is a complete "
    "prediction and stays in. Read-side only; never mutates resolutions."
)


def market_is_orphan_partition(market_type: str | None, n_outcomes: int) -> bool:
    """True if a declared partition captured <=1 member (Queue 299).

    Canonical, unit-tested mirror of the ``orphan_partition_markets`` CTE.
    Read-side only (gotcha #21).
    """
    return market_type == "field" and n_outcomes <= 1


# Rung 4 — EXCLUSIVITY EVIDENCE gates normalization.
#
# THE cricket finding, and the one with the widest blast radius. Normalization
# divides every member of a market by the market's own probability sum, which is
# only meaningful when the members really are one exhaustive partition. Until now
# the gate was ``mutually_exclusive = true OR market_type = 'field'`` — and
# ``futures_markets.mutually_exclusive`` DEFAULTS TO TRUE (app.utils.market_shape's
# own docstring: "mutually_exclusive is TRUE for both yes/no claims AND
# two-competitor duels", which is why the shape classifier exists at all). So the
# flag is not evidence of anything. Census 2026-08-01 over resolved >=3-outcome
# markets shows what that admitted:
#
#   * 51,424 markets  market_type='field', outcome_relation='unknown', exhaustive
#                     NULL — the classifier explicitly declined to prove a partition,
#   * 27,958 markets  cumulative-threshold ladders (exhaustive=false) — gotcha #17
#                     co-winning Over rungs, divided by their own sibling sum,
#   * 31,197 markets  field/competitors/exhaustive=true/expected_winners=1 — the
#                     only class that ever had proof.
#
# The shape classifier already persists that proof per market in
# ``market_metadata->'shape'`` (Queue #260 semantics v2), and its own Item 3 guard
# only sets ``exhaustive`` when the source proves it — never inferred from ">2
# named outcomes". So the fix is to require the POSITIVE verdict and stop
# accepting the default-true flag. This is exactly C119's contract ("exclusivity
# evidence, not category labels or observed one-winner count, authoritative") and
# it is what stops an independent-binary bundle being divided by its sibling sum.
#
# A market that loses candidacy is NOT excluded from the curve — it simply flows
# to the multi pool un-normalized, carrying its raw captured price. Nothing is
# deleted by this rung; a price stops being rewritten on an unproven premise.
EXCLUSIVITY_PROVED_RELATIONS = frozenset({"competitors", "exclusive_ranges"})

EXCLUSIVITY_EVIDENCE_RULE_TEXT = (
    "Per-market probability normalization now requires PROVED exclusivity from "
    "the persisted shape classifier (market_type='field' AND shape.exhaustive=true "
    "AND shape.expected_winners=1 AND an exclusive outcome relation), not the "
    "futures_markets.mutually_exclusive column — whose default is True and which "
    "the classifier's own docstring records as set for Yes/No claims and duels "
    "alike, so it is not evidence. Census 2026-08-01: the old gate admitted 51,424 "
    "markets whose relation the classifier declined to resolve and 27,958 "
    "cumulative-threshold ladders (gotcha #17 co-winners) into a rule that divides "
    "every member by the market's own sibling sum. Category is never consulted: "
    "the same structure is judged identically in cricket, esports and "
    "entertainment. A market that loses candidacy is NOT dropped — it flows to the "
    "multi pool with its raw captured price. Read-side only; never mutates "
    "resolutions."
)


def market_exclusivity_is_proved(
    market_type: str | None,
    exhaustive: object,
    expected_winners: object,
    outcome_relation: str | None,
) -> bool:
    """True if a market is a PROVED single-winner exhaustive partition (Queue 299).

    Canonical, unit-tested mirror of the ``mex_field_candidates`` exclusivity
    gate. Evidence comes from the persisted shape classifier
    (``market_metadata->'shape'``), never from the default-true
    ``mutually_exclusive`` column and never from the category:

      * ``market_type == 'field'`` — the classifier's ">2 competitors, one wins"
        display verdict, AND
      * ``exhaustive`` is true — the classifier's Item 3 guard only sets this
        when the SOURCE proves it, AND
      * ``expected_winners == 1`` — a single-winner partition, not a Top-N /
        participation contract, AND
      * ``outcome_relation`` is an exclusive relation (named competitors or
        exclusive ranges) — never ``cumulative_thresholds`` (co-winning ladder
        rungs, gotcha #17), ``independent_participation`` or ``unknown``.

    Values arrive from JSONB as strings on the SQL path, so ``'true'`` / ``'1'``
    are accepted alongside the native ``True`` / ``1``. Anything unrecognised
    fails closed. Read-side only (gotcha #21).
    """
    if market_type != "field":
        return False
    if str(exhaustive).strip().lower() != "true":
        return False
    if str(expected_winners).strip() != "1":
        return False
    return (outcome_relation or "") in EXCLUSIVITY_PROVED_RELATIONS


def exclusivity_proved_sql(info_alias: str = "mi", shape_alias: str = "mrs") -> str:
    """Render :func:`market_exclusivity_is_proved` as a SQL predicate.

    CAL-P162 (#1978), RULE E. The proved-exclusivity test had exactly one SQL
    rendering — inline in ``mex_field_candidates`` — and RULE E needs the same
    test in a second place (a bundle must never be a proved-exclusive field).
    Extracted rather than copied: two hand-maintained copies of one predicate is
    the defect D12's own comment warns about, and here the copies would sit 80
    lines apart in the same query. ``mex_field_candidates`` now calls this too,
    so there is one rendering and ``test_exclusivity_proved_sql_mirrors_python``
    pins it against the Python mirror rather than against a restatement.
    """
    return (
        f"{info_alias}.market_type = 'field'"
        f" AND {info_alias}.shape_exhaustive = 'true'"
        f" AND {info_alias}.shape_expected_winners = '1'"
        f" AND {info_alias}.shape_relation IN {_sql_str_tuple(EXCLUSIVITY_PROVED_RELATIONS)}"
        f" AND {shape_alias}.win_count = 1"
    )


# Rung 4b — the category-independent non-exclusive bundle, MEASURED not excluded.
#
# ``market_is_esports_multi_bundle`` is the same structural test wearing a
# category allowlist, and C119 is right that the allowlist is not principled.
# But the census that would justify deleting the class category-wide says the
# opposite of what the esports evidence says: a blanket >=3-outcome / >=2-winner
# exclusion removes 27,942 of hockey's 34,368 published outcomes (81%) and
# 20,511 of tennis's 43,460 (47%) — two of the best-calibrated cohorts we have
# (hockey ECE 0.87pp, tennis 2.42pp). Deleting well-calibrated data to satisfy a
# shape rule would be a bigger error than the one being fixed, and Queue 299's
# own Item 2 requires n/ECE be recomputed after each rung before it is believed.
#
# So the structural test is generalized as a MEASUREMENT: every category gets the
# flag, the artifact publishes the in-curve n and ECE of the bundle cohort and of
# the remainder per category, and the esports EXCLUSION stays exactly as it was
# (its +9.2pp defect is measured, OPS-557). The next queue can then exclude on
# evidence per cohort instead of guessing. Nothing is silently capped: the
# census is published, and this comment is the reason the rung stopped here.
NONEXCLUSIVE_BUNDLE_CENSUS_RULE_TEXT = (
    "Category-independent census of the non-exclusive bundle shape (>=3 outcomes "
    "resolving with >=2 winners — independent binaries packed into one market, so "
    "not a partition at any price). The esports cohort is EXCLUDED from the curve "
    "(OPS-557 measured +9.2pp there); every other category is MEASURED ONLY, "
    "because a blanket exclusion would delete 81% of hockey (ECE 0.87pp) and 47% "
    "of tennis (ECE 2.42pp) — well-calibrated cohorts with no evidence of the "
    "esports defect. Publishing the per-category n/ECE of the bundle cohort vs the "
    "remainder is what lets the exclusion decision be made on evidence rather than "
    "on the shape label alone. Measurement only; changes no curve row."
)


def market_is_nonexclusive_bundle(n_outcomes: int, n_winners: int) -> bool:
    """True if a market's members cannot be mutually exclusive (Queue 299).

    Category-independent structural test: >=3 outcomes resolving with >=2
    winners is direct evidence the members are independent questions packed into
    one market, not a single-winner partition. Used to (a) keep such a market out
    of normalization in EVERY category and (b) drive the published bundle census.
    The esports curve exclusion (:func:`market_is_esports_multi_bundle`) is this
    same predicate under its measured category scope. Read-side only (gotcha #21).
    """
    return n_outcomes >= 3 and n_winners >= 2


def market_is_nonexclusive_bundle_structural(
    n_outcomes: int,
    n_winners: int,
    cp_sum: float | None,
    *,
    exclusivity_proved: bool,
) -> bool:
    """RULE E: the bundle test as a STRUCTURE, not only as a realization.

    CAL-P162 (#1978), on the design banked in
    ``artifacts/cal-p112/RULE-DESIGN-polymarket-esports.md`` §4 and re-confirmed
    on the exact rail by CAL-P114 §5c. A market with >=3 captured outcomes that
    is **not** a proved-exclusive field is a non-exclusive bundle when EITHER

      * it resolved with >=2 winners — :func:`market_is_nonexclusive_bundle`,
        the shipped test, unchanged; OR
      * its published price sum exceeds ``MEX_NORMALIZE_THRESHOLD`` (1.15).

    **Why the second arm exists.** The shipped test is a REALIZATION and the
    defect is a STRUCTURE: a genuine partition sums to ~1 whatever it resolves
    to, while independent binaries packed into one market sum to N x p. A bundle
    that happened to land on exactly one rung therefore escapes the >=2-winner
    test entirely, and that 1-winner tail is the whole of what survives in
    ``polymarket/esports`` (7.59 pp) and 99.7% of ``kalshi/economics`` (5.29 pp).
    The threshold is not fitted here — it is the normalizer's own constant.

    **``exclusivity_proved`` is load-bearing, not belt-and-braces.** Complete
    proved-exclusive fields are the ``mex_field_candidates`` population and are
    NORMALIZED, never excluded; the two sets must not overlap or an exclusion
    would silently eat the normalizer's input. An INCOMPLETE proved field can sum
    past 1.15 without being a bundle, which is exactly the row this clause saves.

    ``cp_sum`` is None when the market contributed no eligible priced outcome; a
    market with no sum cannot be shown to be structurally non-exclusive, so it
    falls back to the realization arm alone (fails closed). Read-side only
    (gotcha #21) — the many-YES ladder grading is correct, so these rows are
    dropped from the curve, never re-graded.
    """
    if n_outcomes < 3:
        return False
    if exclusivity_proved:
        return False
    if n_winners >= 2:
        return True
    return cp_sum is not None and cp_sum > MEX_NORMALIZE_THRESHOLD


# Queue #186 (#941, corrects #167): Kalshi player-prop threshold curve exclusion.
#
# Kalshi player-prop markets are single-sided "Player: N+" OVER outcomes (points,
# assists, goals, total bases, hits, HR, strikeouts, rebounds, blocks, ...). A
# large slice of their captured calibration_probability is corrupt: these markets
# are polled near/after game time (Kalshi commence_time ≈ resolution time,
# gotcha #14), so a settled post-game quote (yes_ask≈1.00) gets stamped as the
# "closing line" — e.g. "6+ total bases" at 0.96, physically impossible as a real
# OVER. It is the settlement artifact, not a prediction.
#
# Queue #167 (2026-07-12) tried to keep the "real-bid" rows, believing only the
# no-live-bid rows were poison. The Queue #186 forensic verify (2026-07-13,
# snapshot-level trace over the exact series the Calibration Sentinel flagged in
# #1069–#1073) DISPROVED that: real-bid rows are corrupt too. In one market a
# scorer and a non-scorer BOTH carry cp 0.995 with a live 0.99 bid (Kapanen 1+ did
# not score / Caufield 1+ did — same stamped closing line). The live bid is a
# stale settlement quote, not price discovery. The honest discriminator is the
# CURVE PRICE, not the bid.
#
# The corrected diagnosis has two distinct sub-populations (verified by an
# opening-decile trace, prod 2026-07-13):
#   * DEGENERATE SETTLEMENT-COLLAPSE BAND (curve price >= 0.90): corrupt for EVERY
#       series — it resolves 0.11–0.48, never near 0.90 (NBA 0.983→0.445, NHL
#       0.979→0.117). Excluded. Below the band the liquid series are an honest
#       diagonal (NBAPTS 0.647→0.600, 0.749→0.734; MLBTB 0.639→0.791) and are
#       KEPT ("SAVE all possible", gotcha #21) — excluding only the band brings
#       their high-band actual within ~10pp of predicted (NBAPTS -2pp, MLBKS -2pp).
#   * NHL GOAL-FAMILY (llm_sport_category='hockey', KXNHLGOAL/PTS/AST): corrupt at
#       EVERY band (opening 0.69→0.21, 0.82→0.05) while its RESOLUTION is verified
#       SANE (5.24 scorers credited/game, min 1 max 25, 0 zero-scorer games; api
#       and box_score agree at ~0.09 winrate). So this is an illiquid degenerate
#       CAPTURE, not a resolution bug and NOT a sign-flip (low prices resolve low,
#       honestly — there is no side to flip). No honest price to recover → the
#       whole class is dropped.
#
# No regrade (the sign-flip premise from the Sentinel writeup is disproven; gotcha
# #21). Read-side only; never mutates is_winner or probabilities. Consistent with
# the writer-side guard in backfill_winners._compute_calibration_prices that
# refuses to stamp a no-bid snapshot as the closing line for these props.
#
# POSIX form for the SQL ``~`` operator ([+] is a literal plus in a bracket
# expression so no backslash escaping is needed inside the f-string).
KALSHI_PROP_THRESHOLD_NAME_RE = r"^.+:[[:space:]]*[0-9]+[+][[:space:]]*$"

# Python mirror of the SQL regex for the unit-tested helper.
_KALSHI_PROP_THRESHOLD_RE = re.compile(r"^.+:\s*\d+\+\s*$")

# Queue #186 (#941) DEGENERATE SETTLEMENT-COLLAPSE BAND. The corrected verify
# pass (2026-07-13, forensic snapshot trace) proved the #167 "keep the real-bid
# rows" discriminator was itself an artifact: real-bid rows are corrupt too. Per
# outcome, both a scorer and a non-scorer in the same market get the same
# post-settlement quote stamped as the closing line (e.g. Kapanen 1+ ybid 0.99
# cp 0.995 DID NOT score, next to Caufield 1+ ybid 0.99 cp 0.995 who DID). The
# honest discriminator is the CURVE PRICE, not the bid: an opening-decile trace
# shows opening_probability is a clean diagonal through decile 8 for the liquid
# series (NBA points/reb/ast/3pt, MLB TB/HIT/HR/KS: e.g. NBAPTS 0.647→0.600,
# 0.749→0.734) and ONLY the >=0.90 band is degenerate (0.983→0.445 for NBA,
# 0.979→0.117 for NHL — it never resolves anywhere near 0.90 for ANY series).
# Excluding that band brings every liquid series' high-band (0.6–0.9) actual to
# within ~10pp of predicted (NBAPTS -2pp, NBAAST -4pp, MLBKS -2pp, MLBHIT -6pp).
KALSHI_PROP_THRESHOLD_DEGENERATE_BAND = 0.90

# Queue #194 Item 3 (#1089) — NHL GOAL-FAMILY HONEST-BAND RECOVERY. The #941
# "corrupt at EVERY band" premise was an overstatement (it only sampled the high
# deciles). A fresh forensic (prod 2026-07-14, curve-price calibration of all
# resolved KXNHLGOAL/PTS/AST, n=26,436) shows the goal-family is corrupt only in
# the HIGH band and WELL-CALIBRATED in the low band — so the wholesale hockey drop
# needlessly discarded ~16.7K honest rows. Curve-price bands (pred → actual):
#     <0.30      n=13,285   0.127 → 0.096   gap  3.1pp   HONEST
#     0.30–0.40  n= 2,000   0.345 → 0.323   gap  2.2pp   HONEST
#     0.40–0.50  n= 1,411   0.445 → 0.405   gap  4.0pp   HONEST
#     0.50–0.70  n= 3,745   0.637 → 0.311   gap 32.6pp   DEGENERATE
#     0.70–0.90  n= 1,916   0.795 → 0.189   gap 60.6pp   DEGENERATE
#     >=0.90     n= 4,079   0.975 → 0.182   gap 79.3pp   DEGENERATE
# Calibration breaks hard at 0.50 (gap jumps 4pp → 33pp), so the honest cutoff is
# 0.50: RECOVER (include) hockey goal-family rows below 0.50 — 16,696 well-
# calibrated outcomes — and EXCLUDE the 9,740 at/above it permanently (the
# earliest snapshot is also degenerate there — an illiquid one-sided-ask capture,
# gotcha #14 — so there is genuinely no honest price to recover for that split;
# the issue's "re-stamp from the first snapshot" premise is disproven). Read-side
# only (gotcha #21) — never mutates is_winner or probabilities.
KALSHI_HOCKEY_HONEST_BAND_MAX = 0.50

KALSHI_PROP_THRESHOLD_RULE_TEXT = (
    "Excludes the corrupt slice of Kalshi player-prop threshold outcomes "
    "(single-sided 'Player: N+' OVER markets — points/assists/goals/total-bases/"
    "hits/HR/strikeouts/rebounds/blocks). Two exclusions: (A) the NHL goal-family "
    "(llm_sport_category='hockey') at/above 0.50, whose prices are degenerate in "
    "the high band (0.50–0.70 winrate 0.31, >=0.90 winrate 0.18) — an illiquid "
    "capture (gotcha #14), not a sign-flip or resolution bug — while its honest "
    "low band (<0.50, ~3pp calibrated) is RECOVERED (Queue #194/#1089, correcting "
    "#941's over-broad wholesale drop); and (B) any row whose curve price "
    "(closing line, else opening) sits in the degenerate settlement-collapse band "
    "(>= 0.90), which resolves 0.11–0.48 across every series — the settled "
    "post-game quote stamped as the line ('6+ total bases' at 0.96, physically "
    "impossible as a real OVER). Below that band the liquid series (NBA points/reb/"
    "ast/3pt, MLB TB/HIT/HR/KS) are an honest diagonal and are KEPT, bringing their "
    "high-band actual within ~10pp of predicted. Queue #186 (2026-07-13) corrects "
    "#167: its no-live-bid discriminator was itself an artifact — real-bid rows are "
    "corrupt too (a scorer and a non-scorer in one market both carry cp 0.995 with "
    "ybid 0.99), so the curve price, not the bid, is the honest discriminator. No "
    "regrade: the sign-flip premise is disproven (low prices resolve low, honestly) "
    "and there is no honest price to recover for the excluded rows (gotcha #21). "
    "Read-side only; never mutates resolutions or probabilities."
)


def kalshi_prop_threshold_exclude_sql(
    *,
    source: str,
    name: str,
    category: str,
    calibration_probability: str,
    opening_probability: str,
    curve_price: str | None = None,
) -> str:
    """Canonical SQL boolean for the Queue #186/#941 Kalshi prop-threshold exclusion.

    Single source of truth mirrored by ``outcome_is_kalshi_prop_threshold`` (the
    Python helper). Renders the exact ``is_kalshi_prop_threshold`` predicate used
    by the calibration curve so every SQL read-path honours the same rule and
    cannot silently diverge — the calibration precompute task, the
    ``/api/calibration`` cold-cache fallback serve, AND the source-intelligence
    fair-fight MCE (Queue #188 Item 3: ``source_intelligence.py`` was reading the
    corrupt NHL cal prices raw, unguarded). Callers pass the column expressions for
    their own table aliases; the regex and degenerate band come from the module
    constants so a hand-typed literal can never drift out of sync (the route used
    to hardcode ``0.90``).

    Excluded when source='kalshi', ``name`` matches the 'Player: N+' OVER pattern,
    and EITHER category='hockey' OR the price sits in the degenerate band.

    Queue #263 Item 1 (horizon-honest band classification): the band decision is a
    PRICE-STATE decision, so it must read the same price expression the surface is
    finalized on. ``curve_price`` overrides the price expression used for BOTH the
    hockey (>= 0.50) and general (>= 0.90) band comparisons; the headline path
    leaves it None and falls back to ``COALESCE(cp, opening)`` (identical to the
    old literal), while a horizon passes its snapshot price so each horizon
    classifies a threshold outcome on ITS OWN price, not the terminal probability.
    The hockey vs general split is preserved mechanically — only the price the two
    bands read changes. Read-side only (gotcha #21) — never mutates resolutions.
    """
    price_expr = (
        curve_price
        if curve_price is not None
        else f"COALESCE({calibration_probability}, {opening_probability})"
    )
    return (
        f"({source} = 'kalshi'\n"
        f"     AND {name} ~ '{KALSHI_PROP_THRESHOLD_NAME_RE}'\n"
        f"     AND (({category} = 'hockey'\n"
        f"            AND {price_expr}\n"
        f"                >= {KALSHI_HOCKEY_HONEST_BAND_MAX})\n"
        f"          OR {price_expr}\n"
        f"             >= {KALSHI_PROP_THRESHOLD_DEGENERATE_BAND}))"
    )

# Queue #183 Item 4 (#182 historical twin): curve-side exclusion of WEATHER
# WIDE-SPREAD FABRICATED MIDPOINTS. #182 proved a WIDE Kalshi book
# (yes_ask - yes_bid >= 0.50) with no trade has NO real price discovery at its
# midpoint — the captured cal_prob is a fabricated number, not a market line. #182
# fixed this FORWARD (_kalshi_yes_probability now skips wide/one-sided no-trade
# books, _KALSHI_TIGHT_SPREAD_MAX = 0.50); this is the read-side HISTORICAL twin
# for the rows captured before that guard shipped. WEATHER-GATED ONLY: #182's
# census confirmed weather's ~65 wide-spread rows are the disease, while tech's
# miscalibration is genuine (NOT wide-book noise, ~10pp is real), so tech is
# deliberately left in (its census is parked — do NOT extend this to tech). These
# rows carry a live bid (bid > 0), so the #940 liquidity filter KEEPS them — the
# SPREAD is the discriminator the liquidity filter misses. Read-side only (gotcha
# #21) — never mutates is_winner / calibration_probability.
WEATHER_WIDE_SPREAD_MIN = 0.50  # mirrors kalshi.py _KALSHI_TIGHT_SPREAD_MAX

WEATHER_WIDE_SPREAD_EXCLUDE = (
    "(vm.source = 'kalshi'\n"
    "     AND cv.category = 'weather'\n"
    "     AND fo.current_yes_bid IS NOT NULL AND fo.current_yes_ask IS NOT NULL\n"
    f"     AND (fo.current_yes_ask - fo.current_yes_bid) >= {WEATHER_WIDE_SPREAD_MIN}\n"
    "     AND NOT EXISTS (\n"
    "        SELECT 1 FROM futures_odds_snapshots fos\n"
    "        WHERE fos.outcome_id = fo.id AND fos.last_price > 0))"
)

WEATHER_WIDE_SPREAD_RULE_TEXT = (
    "Excludes Kalshi WEATHER outcomes whose captured price is a fabricated wide-book "
    "midpoint: a book with yes_ask - yes_bid >= 0.50 and NO trade in any snapshot has "
    "no real price discovery at its midpoint (#182). These rows carry a live bid so "
    "the #940 liquidity filter keeps them — the wide spread is the discriminator. "
    "WEATHER ONLY: #182's census showed tech's miscalibration is genuine, not "
    "wide-book noise, so tech is left in. Read-side only; never mutates resolutions."
)


def outcome_is_weather_wide_spread(
    source: str | None,
    category: str | None,
    current_yes_bid: float | None,
    current_yes_ask: float | None,
    ever_last_price: float | None = None,
) -> bool:
    """True if a Kalshi WEATHER outcome is a fabricated wide-book midpoint (Queue #183 Item 4).

    Canonical, unit-tested definition mirroring the ``WEATHER_WIDE_SPREAD_EXCLUDE``
    SQL flag. Excluded only when ALL hold:
      1. source == 'kalshi' AND category == 'weather' (weather-gated — tech's
         miscalibration is genuine per #182's census and is NOT excluded here)
      2. a two-sided book is present with a WIDE spread
         (yes_ask - yes_bid >= WEATHER_WIDE_SPREAD_MIN, i.e. 0.50)
      3. no trade evidence (``ever_last_price`` is None or 0) — a wide book that
         actually traded has real evidence and is KEPT (#182 uses last_price then)

    Read-side only (gotcha #21) — never mutates resolutions.
    """
    if source != "kalshi" or category != "weather":
        return False
    if current_yes_bid is None or current_yes_ask is None:
        return False
    # Bid/ask live in Numeric(5,4) columns, so Postgres computes the spread in
    # EXACT decimal arithmetic. Round to 4 dp here so the Python mirror agrees
    # with the SQL flag at the 0.50 boundary (binary float would make e.g.
    # 0.70 - 0.20 = 0.4999… and silently disagree with the DB).
    spread = round(float(current_yes_ask) - float(current_yes_bid), 4)
    if spread < WEATHER_WIDE_SPREAD_MIN:
        return False
    return (ever_last_price or 0) <= 0


def outcome_is_kalshi_prop_threshold(
    source: str | None,
    name: str | None,
    curve_price: float | None = None,
    category: str | None = None,
) -> bool:
    """True if a Kalshi player-prop threshold outcome is EXCLUDED from the curve (Queue #186/#941).

    Canonical, unit-tested definition mirroring the ``is_kalshi_prop_threshold``
    flag in the main outcome scan. A row is a "<subject>: N+" OVER threshold when
    source == 'kalshi' and the name matches the single-sided threshold pattern
    (points/assists/goals/total-bases/hits/HR/strikeouts/rebounds/... player
    props). Such a row is EXCLUDED when EITHER:

      A. ``category == 'hockey'`` AND ``curve_price`` >= 0.50 — the NHL goal-family
         (KXNHLGOAL/PTS/AST) is degenerate ONLY in the high band. Queue #194 (#1089)
         forensic (n=26,436) showed it is well-calibrated below 0.50 (<0.30 gap
         3.1pp, 0.30–0.40 2.2pp, 0.40–0.50 4.0pp) and breaks hard at/above it
         (0.50–0.70 gap 32.6pp, >=0.90 79.3pp). So the honest low band is RECOVERED
         (kept) and only the degenerate >=0.50 split is dropped (its earliest
         snapshot is also degenerate — an illiquid one-sided-ask capture, gotcha
         #14 — no honest price to recover). This corrects #941's over-broad
         wholesale hockey drop.
      B. ``curve_price`` (= COALESCE(calibration_probability, opening_probability))
         is in the DEGENERATE SETTLEMENT-COLLAPSE BAND (>= 0.90). Across every
         series this band resolves at 0.11–0.48, never near 0.90 — it is the
         settled post-game quote stamped as the closing line, not a prediction.
         Below the band the liquid series (NBA/MLB) are an honest diagonal and
         are KEPT ("SAVE all possible", gotcha #21).

    NOTE (Queue #186 correction): the earlier #167 discriminator keyed on live YES
    bid (keep rows with ``current_yes_bid`` > 0). The 2026-07-13 forensic verify
    disproved it — real-bid rows are corrupted too (a scorer and a non-scorer in
    the same market both carry cp 0.995 with ybid 0.99). The curve price, not the
    bid, is the honest discriminator. Read-side only — never mutates is_winner /
    calibration_probability (no regrade; the sign-flip premise is disproven).
    """
    if source != "kalshi" or not name:
        return False
    if not _KALSHI_PROP_THRESHOLD_RE.match(name):
        return False
    if curve_price is None:
        # Unknown price → conservatively excluded (the SQL path always has a
        # curve price via COALESCE, so this only affects defensive callers).
        return True
    if category == "hockey":
        # #1089 recovery: the goal-family is honest below 0.50 and degenerate
        # at/above it — exclude only the degenerate high band, recover the rest.
        return curve_price >= KALSHI_HOCKEY_HONEST_BAND_MAX
    return curve_price >= KALSHI_PROP_THRESHOLD_DEGENERATE_BAND


def outcome_is_calibration_liquid(
    ever_yes_bid: float | None, ever_last_price: float | None
) -> bool:
    """True if an outcome qualifies for the published calibration set.

    Canonical definition of the #940 phase-1 rule, mirroring
    ``KALSHI_LIQUIDITY_EXISTS``: an outcome is liquid (included) iff some
    snapshot ever showed a real bid (``yes_bid > 0``) OR a trade
    (``last_price > 0``). Never-bid AND never-traded -> excluded. Read-side
    only (gotcha #21). ``ever_yes_bid`` / ``ever_last_price`` are the max
    bid / max last_price observed across an outcome's snapshots (NULL if none).
    """
    return (ever_yes_bid or 0) > 0 or (ever_last_price or 0) > 0


def binary_is_malformed(n_outcomes: int, n_winners: int) -> bool:
    """True if a 2-outcome mutually-exclusive market is malformed (L2-79 Item 1).

    Canonical, unit-tested definition mirroring the ``malformed_binaries`` CTE: a
    resolved binary must have exactly one winner. Zero winners (void/malformed) or
    two winners (impossible / double-graded) is a data artifact excluded from the
    published curve. Only applies to 2-outcome markets; anything else is not a
    binary and returns False. Read-side only (gotcha #21).
    """
    return n_outcomes == 2 and n_winners != 1


def outcome_in_golf_high_band(cp: float | None) -> bool:
    """True if a golf outcome's price sits in the placeholder high band (L2-79 Item 2).

    The band-membership half of the ``golf_placeholder_markets`` rule: an outcome
    priced at/above GOLF_PLACEHOLDER_HIGH_BAND is a candidate one-sided-ask
    placeholder. The full exclusion additionally requires the market to be
    over-subscribed (>=2 outcomes in this band) — that market-level check lives in
    the SQL CTE. Read-side only (gotcha #21).
    """
    return cp is not None and cp >= GOLF_PLACEHOLDER_HIGH_BAND


def _wilson_ci(wins: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total == 0:
        return (0.0, 0.0)
    p = wins / total
    denom = 1 + z**2 / total
    center = (p + z**2 / (2 * total)) / denom
    spread = z * math.sqrt((p * (1 - p) + z**2 / (4 * total)) / total) / denom
    return (max(0.0, center - spread), min(1.0, center + spread))


def _bootstrap_mce_ci(
    bucket_list: list[dict],
    n_boot: int = 1000,
    seed: int = 42,
) -> tuple[float, float]:
    if not bucket_list:
        return (0.0, 0.0)
    rng = random.Random(seed)
    k = len(bucket_list)
    mce_samples: list[float] = []
    for _ in range(n_boot):
        sample = rng.choices(bucket_list, k=k)
        # n-weighted to match the #137 weighted point estimate.
        total_abs_err = 0.0
        total_w = 0.0
        for b in sample:
            actual = b["winners"] / b["n"] if b["n"] else 0.0
            w = b["n"]
            total_abs_err += abs(actual - b["avg_prob"]) * w
            total_w += w
        mce_samples.append(total_abs_err / total_w if total_w else 0.0)
    mce_samples.sort()
    lo = mce_samples[int(n_boot * 0.025)]
    hi = mce_samples[int(n_boot * 0.975)]
    return (lo, hi)


def _compute_horizon_mce(buckets: list[dict], weighted: bool = True) -> float | None:
    """Mean per-bucket calibration error, in percentage points.

    #137 Item 3: `weighted=True` (the default) weights each probability bucket's
    |actual - predicted| by the bucket's sample size (n). The old equal-weighted
    mean (weighted=False) let a tail bucket of n=2-13 dominate a category whose
    bulk (n=1000s) was well-calibrated — the r108 "mlb spreads 16.4pp" artifact
    class. n-weighting makes the number reflect the outcomes users actually see.
    Pass weighted=False to reproduce the legacy number (kept as `mce_unweighted`
    during the transition for comparison).
    """
    if not buckets:
        return None
    total_abs_err = 0.0
    total_w = 0.0
    for b in buckets:
        if b["n"] == 0:
            continue
        avg_prob = b["sum_prob"] / b["n"]
        actual = b["winners"] / b["n"]
        w = b["n"] if weighted else 1
        total_abs_err += abs(actual - avg_prob) * w
        total_w += w
    if total_w == 0:
        return None
    return round(total_abs_err / total_w * 100, 2)


#: Queue 300D Item 0 — the bind-parameter names the frozen generation roster
#: travels under. One array per column, ``unnest``-ed into a CTE, so a chunk of
#: several thousand markets costs three bind params instead of a megabyte of
#: inlined VALUES text.
#:
#: Every one is read through ``CAST(:p AS t[])`` rather than ``:p::t[]``:
#: SQLAlchemy's ``text()`` silently drops a bind parameter immediately followed
#: by a ``::`` cast, which produces a query that raises on every run (the
#: asyncpg bind gotcha that killed ``_fix_golf_commence_times`` for months —
#: gotcha #45's cousin).
VM_ROSTER_MARKET_IDS_PARAM = "vm_roster_market_ids"
VM_ROSTER_VM_IDS_PARAM = "vm_roster_vm_ids"
VM_ROSTER_IS_GROUPED_PARAM = "vm_roster_is_grouped"

#: The extra ``market_info`` predicate that scopes the base scan to one chunk.
VM_ROSTER_MARKET_INFO_EXTRA = (
    f"AND fm.id = ANY(CAST(:{VM_ROSTER_MARKET_IDS_PARAM} AS bigint[]))"
)


def _virtual_market_ctes(frozen_vm_roster: bool) -> str:
    """``group_sizes`` / ``event_sizes`` / ``virtual_market``, in one of two forms.

    **Global (default).** Virtual-question identity is DERIVED here: a market
    belongs to ``g:<group_id>`` when its group has >=3 eligible markets in the
    same source, else ``e:<event_id>`` when its event does, else it is its own
    ``m:<market_id>``. The two cardinality CTEs count over the WHOLE population,
    which is what makes the >=3 gate meaningful.

    **Frozen (Queue 300D Item 0).** The staged build has already computed that
    same assignment once, for the whole population, and is now replaying it over
    one chunk. So the roster is INJECTED and the cardinality CTEs disappear.

    That substitution is not an optimization, it is the only correct way to
    chunk this chain, and the reason is worth stating precisely: group and event
    sizes are counted over ``market_info``, so re-deriving them from a FILTERED
    ``market_info`` silently changes them. Concretely — an event with 4 eligible
    markets where one sits in a >=3 group has three markets in ``e:<event_id>``
    and one in ``g:<group_id>``. Chunk by virtual question and re-derive, and
    the ``e:`` chunk now sees only 3 of the event's 4 markets... and a chunk
    holding fewer than 3 would see the event collapse below the gate entirely,
    silently re-assigning every one of its markets to ``m:`` — a different
    question identity, a different representative, a different bucket. Freezing
    the assignment makes the chunk a REPLAY of the global derivation rather than
    a re-derivation over a subset, so every chunk's rows are exactly the global
    rows restricted to that chunk.
    """
    if not frozen_vm_roster:
        return """            group_sizes AS (
                SELECT group_id, source, COUNT(*) AS group_size
                FROM market_info
                WHERE group_id IS NOT NULL
                GROUP BY group_id, source
            ),
            event_sizes AS (
                SELECT event_id, source, COUNT(*) AS event_size
                FROM market_info
                WHERE event_id IS NOT NULL
                GROUP BY event_id, source
            ),
            virtual_market AS (
                SELECT
                    mi.market_id, mi.source, mi.category, mi.event_id,
                    CASE WHEN gs.group_size >= 3
                         THEN 'g:' || mi.group_id
                         WHEN es.event_size >= 3
                         THEN 'e:' || mi.event_id::text
                         ELSE 'm:' || mi.market_id::text
                    END AS vm_id,
                    COALESCE(gs.group_size >= 3, false)
                      OR COALESCE(es.event_size >= 3, false) AS is_grouped,
                    mi.mutually_exclusive,
                    mi.market_type,
                    mi.llm_league
                FROM market_info mi
                LEFT JOIN group_sizes gs
                  ON gs.group_id = mi.group_id AND gs.source = mi.source
                LEFT JOIN event_sizes es
                  ON es.event_id = mi.event_id AND es.source = mi.source
            ),"""

    return f"""            frozen_vm_roster AS (
                SELECT * FROM unnest(
                    CAST(:{VM_ROSTER_MARKET_IDS_PARAM} AS bigint[]),
                    CAST(:{VM_ROSTER_VM_IDS_PARAM} AS text[]),
                    CAST(:{VM_ROSTER_IS_GROUPED_PARAM} AS boolean[])
                ) AS t(market_id, vm_id, is_grouped)
            ),
            virtual_market AS (
                SELECT
                    mi.market_id, mi.source, mi.category, mi.event_id,
                    vr.vm_id,
                    vr.is_grouped,
                    mi.mutually_exclusive,
                    mi.market_type,
                    mi.llm_league
                FROM market_info mi
                -- INNER, not LEFT: a market inside the chunk's scan that the
                -- frozen generation does not name is a market that arrived
                -- after the generation was taken. Dropping it here is what
                -- makes the chunk a replay of one coherent generation; the
                -- roster-digest check at finalization is what NOTICES that it
                -- happened and invalidates the whole build rather than
                -- publishing a population assembled from two generations.
                JOIN frozen_vm_roster vr ON vr.market_id = mi.market_id
            ),"""


def _futures_generation_sql() -> str:
    """The Stage A roster read: one row per eligible market, and nothing else.

    This is the "immutable input generation" Queue 300D Item 0 names — market
    metadata plus source-scoped group/event cardinality, resolved into the
    virtual-question assignment. It runs ONCE per beat and is the only part of
    the chain that has to see the whole population.

    It reuses :func:`_calibration_population_ctes` VERBATIM rather than carrying
    its own copy of ``market_info``, and that is the load-bearing detail. A
    second, hand-written copy of the eligibility predicate is exactly the drift
    C14 found (the cohort sweep measuring rows the curve drops), and here it
    would be worse than drift: the roster IS the chunk boundary, so a generation
    that disagreed with the population about which markets are eligible would
    hand every chunk a subtly different universe than the monolith had.

    Selecting only from ``virtual_market`` is what makes it cheap. PostgreSQL
    does not execute an unreferenced ``WITH`` subquery, so naming the full chain
    costs nothing: everything downstream of ``virtual_market`` —
    ``ranked_outcomes`` and its representative sort, the price joins, the whole
    per-outcome universe — is planned away. What actually runs is one pass over
    the eligible futures markets, which the monolith pays anyway.
    """
    return (
        "WITH "
        + _calibration_population_ctes()
        + """
            SELECT market_id, source, vm_id, is_grouped
            FROM virtual_market
            ORDER BY market_id
        """
    )


def _calibration_population_ctes(
    *,
    curve_price: str = "COALESCE(fo.calibration_probability, fo.opening_probability)",
    curve_price_join: str = "",
    rn_order: str = "ABS(fo.opening_probability - 0.5)",
    market_info_extra: str = "",
    leading_ctes: str = "",
    frozen_vm_roster: bool = False,
) -> str:
    """The ONE canonical eligible -> final-published-row CTE chain (Queue #259 Item 1/2).

    Queue #262 Item 1: the finalizer is PARAMETERIZED by the "curve price" so the
    time-horizon surface can reuse the SAME resolved-question identity, independent-
    truth allowlist, and artifact exclusions while finalizing on a horizon snapshot
    instead of the terminal price. The defaults reproduce the headline population
    semantically (curve_price = terminal ``calibration_probability`` fallback,
    no extra joins), so the serve/cohort-sweep row parity (#259) and partition-sum
    invariant are preserved; existing tests pin that behavior.

      * ``curve_price``      — SQL expression for the bucketed/normalized price.
                               Headline: terminal cp. Horizon: the snapshot value.
      * ``curve_price_join`` — extra INNER JOIN injected into the price-bearing CTEs
                               (``ranked_outcomes`` + ``mex_field_divisor``); for a
                               horizon this joins ``horizon_price`` so ONLY outcomes
                               with a snapshot at the horizon cutoff survive.
      * ``rn_order``         — representative-side ORDER BY for the single-market
                               binary branch (headline: opening; horizon: snapshot).
      * ``market_info_extra``— extra WHERE on ``market_info`` (horizon scopes to
                               non-event, resolution-date-bearing markets so the
                               whole chain runs on the small horizon universe).
      * ``leading_ctes``     — CTE(s) prepended to the WITH-body (the horizon-price
                               LATERAL lookup), WITH a trailing comma.

    NORMALIZATION / FIELD-COMPLETENESS ARE HORIZON-HONEST (Queue #262 + #263 Item 1):
    ROSTER IDENTITY is structural — a market is a partition field regardless of the
    horizon, so ``mex_field_candidates`` detects it on the TERMINAL structure (mex/
    field, single winner, >=3 eligible) and carries the full terminal-eligible member
    count. EVERY PRICE-STATE decision is evaluated on the price expression: the
    normalization divisor (``mex_field_divisor`` sum over ``{curve_price}``), the
    field-sum > threshold qualification (moved out of candidate detection into the
    ``normalized`` gate, keyed on ``mnm_cp_sum``), and the Kalshi prop-threshold band
    (``{curve_price}`` passed to ``kalshi_prop_threshold_exclude_sql``). A field is
    published only when EVERY terminal-eligible member is present at the horizon AND
    survives every exclusion (survivor_n == terminal_eligible_n) AND its price-sum
    clears the threshold, else it is dropped WHOLE. On the headline path present ==
    terminal and ``{curve_price}`` == terminal cp, so this reduces to the old single
    ``mex_norm_markets`` behavior exactly.

    Returns the WITH-body (``market_info`` ... ``deduped``, WITHOUT the leading
    ``WITH`` and WITHOUT a trailing comma) that BOTH serve/audit consumers build
    on, so their populations cannot silently drift (the C14 finding: the cohort
    sweep measured rows the curve drops because it re-implemented the population):

      * ``compute_calibration_payload`` appends ``liq_summary`` / ``published_summary``
        / ``bucketed`` and aggregates ``deduped`` into curve buckets, and
      * ``scripts/evals/cohort_sweep.load_from_session`` selects the ``deduped``
        rows verbatim (same outcome ids, probabilities, question ids, source).

    ``deduped`` IS the final published population: eligible -> per-outcome
    exclusions -> field-completeness normalization -> mode/tail dedup -> rn=1
    binary side. Queue #259 Item 1 fix: a COMPLETE normalized field
    (``is_mex_normalized``) is EXEMPT from the mode-price and extreme-tail
    (``>0.005 AND <0.98``) filters — those are placeholder heuristics for the
    NON-partition multi pool, and applying them after normalization would drop a
    member (a tiny normalized tail, or a uniform field's modal price) and break
    the sum-to-1 invariant the completeness gate guarantees. Read-side only
    (gotcha #21) — never mutates is_winner / calibration_probability.

    Carries every column both consumers need (``outcome_id`` / ``outcome_name`` /
    ``market_type`` / ``llm_league`` for the sweep's cohort keys; ``vm_id`` is the
    production virtual-question identity WITH the source + >=3 group/event size
    gate, so the sweep can no longer collapse unrelated same-event props or split
    a two-market group).
    """
    # CAL-P039 measured it; CAL-P040 applies it under the ruling-009 exception
    # granted in `.claude/handoff/GO-CAL-P039-EXCEPTION.md` (Fable, 2026-08-11).
    #
    # `vm_stats` joins `futures_outcomes` to `virtual_market` with NO predicate on
    # the outcomes table at all. `virtual_market` is referenced 7 times, so PG12+
    # auto-materializes it, and a CTE Scan carries no index and no ordering — so
    # the planner's only options are hash+seqscan or N blind index lookups, and it
    # prices the seq scan lower. Every chunk therefore paid a full 3.3M-row scan of
    # `futures_outcomes`. Measured against production at the real unit size (5,302
    # markets, `backend/scripts/probe_chunk_unit_plan.py`, with act/loops per
    # CAL-P035's rule, NOT a cost delta):
    #
    #     production shape    Seq Scan    act=3,302,680   8,378.8 ms   total 9,104.5 ms
    #     + this predicate    Index Scan  act=   40,696     289.2 ms   total   477.1 ms
    #
    # 19.1x on the QUERY, and both produce the identical aggregate (3,107 groups
    # over 40,696 joined rows). ⚠️ Do NOT quote 19.1x as a beat-level number: a
    # unit costs ~62.9 s measured, so this is ~13.3% of a unit. It buys throughput.
    # It does not make the build converge, and CAL-P039 said so against itself.
    #
    # SOUNDNESS is by construction, not by measurement, and only under
    # `frozen_vm_roster=True`: `frozen_vm_roster` is `unnest` of exactly this array
    # into `market_id`, and `virtual_market` INNER-joins `market_info` against that
    # roster on `market_id` — so every `vm.market_id` is literally an element of the
    # array, and `fo.market_id = vm.market_id` already implies this conjunct. It is
    # a planner hint spelled as a predicate. That premise is guarded structurally
    # (not by string-matching today's SQL) in
    # `tests/test_calibration_unit_scan_redundancy_p039.py`, which fails loudly and
    # by name if any of the three inferences it rests on is changed.
    #
    # On the GLOBAL path it is omitted, and that is load-bearing rather than
    # tidy: there is no roster array bound there, and adding one would filter the
    # whole population down to a chunk — silently, with every downstream row count
    # still looking self-consistent. Pinned by `TestPredicateMustNotLeakIntoGlobal`.
    vm_stats_roster_predicate = (
        f"\n                  AND fo.market_id "
        f"= ANY(CAST(:{VM_ROSTER_MARKET_IDS_PARAM} AS bigint[]))"
        if frozen_vm_roster
        else ""
    )
    return f"""{leading_ctes}market_info AS (
                SELECT fm.id AS market_id, fm.source, fm.event_id, fm.group_id,
                    fm.commence_time,
                    -- CAL-P168 (#1978): R3 matches the market's own TITLE. Named
                    -- `market_name` rather than `name` because `futures_outcomes`
                    -- also has a `name` and an unqualified one in a downstream
                    -- join would resolve to whichever the planner reached first.
                    fm.name AS market_name,
                    COALESCE(fm.llm_sport_category, 'uncategorized') AS category,
                    fm.mutually_exclusive,
                    fm.market_type,
                    fm.llm_league,
                    -- Queue 299 rung 4: the shape classifier's PERSISTED
                    -- exclusivity evidence (app.utils.market_shape semantics v2,
                    -- Queue #260). These three carry the only proof a market is
                    -- a single-winner exhaustive partition; the
                    -- ``mutually_exclusive`` column above defaults to True and
                    -- is set for Yes/No claims and duels alike, so it is not
                    -- evidence and no longer gates normalization.
                    fm.market_metadata->'shape'->>'exhaustive' AS shape_exhaustive,
                    fm.market_metadata->'shape'->>'expected_winners' AS shape_expected_winners,
                    fm.market_metadata->'shape'->>'outcome_relation' AS shape_relation
                FROM futures_markets fm
                WHERE fm.status = 'resolved'
                  {market_info_extra}
                  -- #994 symmetric exclusion: DataGolf markets whose full field
                  -- the historical API genuinely can't return (event not found)
                  -- are dropped ENTIRELY — winners AND losers — so participation
                  -- can never be one-sidedly assumed. Recovery flags these; the
                  -- residual is expected to be ~0 (golf history never ages out).
                  AND NOT COALESCE(
                      (fm.market_metadata->>'datagolf_recovery_residual')::boolean,
                      false)
            ),
            -- Queue 299: ONE per-market structural scan feeding every shape and
            -- result-authority rung. Counts are over ALL outcomes of the market
            -- (never the eligibility-filtered subset) — the same basis the
            -- malformed-binary rule always used, so the shape and winner
            -- cardinality reflect the market as captured, not as published.
            -- Replaces the three separate full scans that previously computed
            -- malformed_binaries / esports_multi_bundles / mex_win_counts.
            market_result_shape AS (
                SELECT fo.market_id,
                    mi.category,
                    mi.market_type,
                    COUNT(*) AS n_outcomes,
                    COUNT(*) FILTER (WHERE fo.is_winner = true) AS win_count,
                    -- Queue 299 rung 2: captured draw/no-result authority.
                    COUNT(*) FILTER (
                        WHERE lower(btrim(fo.name)) IN {_sql_str_tuple(DRAW_AUTHORITY_OUTCOME_NAMES)}
                    ) AS draw_member_count,
                    -- CAL-P168 (#1978): K''s pair arms (R1, R2). Aggregated here
                    -- rather than in their own scan for the reason this CTE
                    -- exists at all — one per-market structural pass feeds every
                    -- shape rung. Same ALL-outcomes basis as n_outcomes/win_count,
                    -- which is what the design's fold measured.
                    {player_props_pair_shape_columns('fo')}
                FROM futures_outcomes fo
                JOIN market_info mi ON mi.market_id = fo.market_id
                GROUP BY fo.market_id, mi.category, mi.market_type
            ),
            -- L2-79 Item 1: malformed 2-outcome mex binaries (winner count != 1).
            malformed_binaries AS (
                SELECT mrs.market_id, mrs.win_count
                FROM market_result_shape mrs
                JOIN market_info mi ON mi.market_id = mrs.market_id
                WHERE mi.mutually_exclusive = true
                  AND mrs.n_outcomes = 2
                  AND mrs.win_count <> 1
            ),
            -- Queue 299 rung 1: markets that graded NOBODY a winner. is_winner
            -- has a False default, so an all-loser market is UNKNOWN truth (an
            -- omitted draw graded as two losses, an orphan half, or a market
            -- nothing ever graded) — not a set of confident losses. Generalizes
            -- the malformed-binary both-false leg to every shape and size.
            no_winner_markets AS (
                SELECT mrs.market_id
                FROM market_result_shape mrs
                WHERE mrs.n_outcomes >= 2 AND mrs.win_count = 0
            ),
            -- Queue 299 rung 2: draw-capable duels with no draw member. The
            -- category answers only "can this contest be drawn?" (sport rules,
            -- exactly as the events-curve soccer rule does); the SHAPE test is
            -- evidence-based, so ladders, Yes/No claims and genuinely 2-way
            -- questions are untouched, as are duels that DO carry a draw.
            draw_authority_markets AS (
                SELECT mrs.market_id
                FROM market_result_shape mrs
                WHERE mrs.category IN {_sql_str_tuple(DRAW_CAPABLE_CATEGORIES)}
                  AND mrs.market_type = 'duel'
                  AND mrs.n_outcomes = 2
                  AND mrs.draw_member_count = 0
            ),
            -- Queue 299 rung 3: a declared partition that captured <=1 member.
            -- Field-shape only — a standalone Yes/No claim with one outcome is a
            -- complete, scoreable prediction and is deliberately NOT caught.
            orphan_partition_markets AS (
                SELECT mrs.market_id
                FROM market_result_shape mrs
                WHERE mrs.market_type = 'field' AND mrs.n_outcomes <= 1
            ),
            -- Queue 299 rung 4b: the category-independent non-exclusive bundle
            -- (>=3 outcomes, >=2 winners). MEASUREMENT ONLY outside esports —
            -- see NONEXCLUSIVE_BUNDLE_CENSUS_RULE_TEXT for why a blanket
            -- exclusion is not shipped (it would delete 81% of hockey and 47%
            -- of tennis, both well-calibrated).
            nonexclusive_bundle_markets AS (
                SELECT mrs.market_id
                FROM market_result_shape mrs
                WHERE mrs.n_outcomes >= 3 AND mrs.win_count >= 2
            ),
            -- Queue #159 (#1010): esports malformed-MULTI "match bundle" markets —
            -- the >=3-outcome sibling of malformed_binaries and the exclusion-side
            -- complement of #157's counter-class guard. Polymarket flattens a whole
            -- match (cumulative Total-Kills Over ladders per game, per-game winners,
            -- first-blood props) into one non-partition market; because the Over
            -- rungs are cumulative, a high-kill game legitimately resolves many YES
            -- (gotcha #17), so the market has >=2 winners and its prices neither
            -- sum to 1 (multiple partitions mashed — can't be normalized) nor
            -- bucket as a clean prediction (OPS-557: n=93,629, winrate 0.395 vs cp
            -- 0.487 = +9.2pp, avg per-market cp-sum 17.9). Counts ALL outcomes,
            -- mirroring malformed_binaries. Read-side only (gotcha #21) — the
            -- many-YES ladder grading is CORRECT, so exclude, never re-grade.
            -- Queue 299: re-expressed over the shared market_result_shape scan
            -- (identical membership) so the esports EXCLUSION and the
            -- category-independent bundle CENSUS derive from one structural
            -- test rather than two copies of it.
            -- ⚠️ THE NAME IS NARROWER THAN THE CTE SINCE D12 (#1978, CAL-P150).
            -- This is the non-exclusive-bundle CURVE EXCLUSION, and it now
            -- covers the esports category on any source PLUS the cells named in
            -- NONEXCLUSIVE_BUNDLE_EXCLUDED_CELLS. The identifiers and the
            -- payload key keep their esports names deliberately: the key is a
            -- public contract on /api/calibration, and the freeze exception
            -- granted was for one tuple, not for a rename. What a reader needs
            -- is WHICH cells were excluded, and that is published as
            -- `excluded_by_cell` rather than inferred from a CTE name.
            -- CAL-P162 (#1978) RULE E: the per-market published price sum, for
            -- markets that are NOT the normalizer's proved-exclusive input.
            -- `mex_field_divisor` below computes the same sum but only over
            -- `mex_field_candidates`, which is by definition the set RULE E must
            -- never touch — so the bundle arm cannot reuse it and needs its own.
            -- The eligibility predicate is copied from `mex_field_divisor`
            -- deliberately and must stay identical to it: the sum has to be over
            -- the rows the curve PUBLISHES, or a market's structure is judged on
            -- a population the reader never sees.
            bundle_price_sum AS (
                SELECT fo.market_id,
                    SUM({curve_price}) AS cp_sum
                FROM futures_outcomes fo
                JOIN market_info mi ON mi.market_id = fo.market_id
                {curve_price_join}
                WHERE fo.opening_probability IS NOT NULL
                  AND fo.opening_probability > 0 AND fo.opening_probability < 1
                  AND fo.resolution_source IN {CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL}
                  AND {kalshi_liquidity_exists_sql(source='mi.source')}
                GROUP BY fo.market_id
            ),
            esports_multi_bundles AS (
                SELECT mrs.market_id
                FROM market_result_shape mrs
                JOIN market_info mi ON mi.market_id = mrs.market_id
                LEFT JOIN bundle_price_sum bps ON bps.market_id = mrs.market_id
                WHERE mrs.n_outcomes >= 3
                  -- RULE E, arm 1 of 2: the shipped REALIZATION test, unchanged.
                  -- Arm 2 is the STRUCTURE — a partition sums to ~1 whatever it
                  -- resolves to, a bundle of independent binaries sums to N x p —
                  -- and it is the only arm that can see a bundle which happened
                  -- to land on one rung. That 1-winner tail is the whole published
                  -- residue of `polymarket/esports` and 13.4% of
                  -- `kalshi/economics`. Mirrors
                  -- market_is_nonexclusive_bundle_structural().
                  AND (
                        mrs.win_count >= 2
                        OR bps.cp_sum > {MEX_NORMALIZE_THRESHOLD}
                  )
                  -- RULE E's disjointness clause, load-bearing: proved-exclusive
                  -- fields are the normalizer's input and are NORMALIZED, never
                  -- excluded. An INCOMPLETE proved field can sum past 1.15
                  -- without being a bundle; this is the row it saves.
                  AND NOT ({exclusivity_proved_sql('mi', 'mrs')})
                  AND (
                        mrs.category = '{ESPORTS_MULTI_BUNDLE_CATEGORY}'
                        OR (mi.source, mrs.category)
                            IN {_sql_pair_tuple(NONEXCLUSIVE_BUNDLE_EXCLUDED_CELLS)}
                  )
            ),
            -- CAL-P168 (#1978) RANK 1 — K''s three MARKET-level arms.
            --
            -- 🔴 READ THE CONSTANTS BLOCK BEFORE TOUCHING THIS. This is NOT
            -- RULE E. It sits directly below `esports_multi_bundles` because
            -- the two report through one payload key, and that adjacency is
            -- exactly what makes it easy to "tidy" them into one CTE. Doing so
            -- would apply RULE E's bundle test to polymarket/baseball, which
            -- was MEASURED at 8.35 against a 4.71 control. They share a
            -- disclosure and nothing else.
            --
            -- M1 is deliberately ABSENT here: it is a ROW-level arm (one leg
            -- leaves, not the market) and is applied in `ranked_outcomes`. R1
            -- and R2 take BOTH legs of a pair; R3 takes the whole container.
            --
            -- The sum for R3 is `bundle_price_sum`, the shipped rendering of
            -- "the per-market published price sum", because R3's threshold IS
            -- RULE E's constant and must be evaluated on the quantity that
            -- constant is defined against. The design's fold summed over
            -- `deduped` instead — a post-dedup, post-normalization sum which
            -- cannot be referenced from here without a cycle. The two bases
            -- differ; at a props container's measured sum of 15-19 against a
            -- threshold of 1.15 the difference cannot change membership, and
            -- `test_player_props_placeholder_kprime.py` pins that reasoning
            -- rather than leaving it as a comment.
            --
            -- CERT-647 (CAL-P170): the arms are carried out of this CTE
            -- SEPARATELY, because the page makes a PROMISE about them that is
            -- only true of two of the four. R3 and M1 are the arms the writer
            -- repair ends: when the writer stops manufacturing a near-0.50
            -- price, the container stops summing past 1.15 and the forced
            -- midpoint stops matching, so those rows re-enter on their own. R1
            -- and R2 are the HISTORICAL residue of the same defect already
            -- written to the back catalogue — 1,258 of their 1,284 rows sit in
            -- the OLD holdout half — and fixing the writer FORWARD does not
            -- un-write them. Publishing one count under one temporary promise
            -- told a reader the whole exclusion empties itself; it does not.
            -- Each arm is evaluated EXACTLY ONCE, in the inner SELECT, and
            -- membership is filtered on the results outside it. Writing the
            -- predicates a second time in a WHERE would be two copies of one
            -- rule in one query — how a mirror stops mirroring — and it would
            -- also put R3's sum test in the CTE twice, which is the shape
            -- `test_the_props_cte_never_tests_the_bundle_shape` reads as RULE E
            -- leaking in by the back door. Membership is unchanged: COALESCE
            -- only turns a NULL into false, and a NULL never matched anyway.
            player_props_placeholder_markets AS (
                SELECT arms.market_id,
                    arms.ppp_historical_arm,
                    arms.ppp_temporary_arm
                FROM (
                    SELECT mrs.market_id,
                        -- R1/R2 — the arms that STAY after the writer repair.
                        COALESCE(
                            {half_spike_pair_predicate('mrs')}
                            OR {published_pair_coherence_predicate('mrs')}, false
                        ) AS ppp_historical_arm,
                        -- R3 — the arm the writer repair ends. COALESCE because
                        -- `bps.cp_sum` arrives on a LEFT JOIN and a NULL sum
                        -- must read as "did not match", never as NULL.
                        COALESCE({player_props_container_predicate(
                                    'mi.market_name', 'bps.cp_sum')}, false
                        ) AS ppp_temporary_arm
                    FROM market_result_shape mrs
                    JOIN market_info mi ON mi.market_id = mrs.market_id
                    LEFT JOIN bundle_price_sum bps ON bps.market_id = mrs.market_id
                    WHERE (mi.source, mrs.category)
                            IN {_sql_pair_tuple(PLAYER_PROPS_PLACEHOLDER_EXCLUDED_CELLS)}
                ) arms
                WHERE arms.ppp_historical_arm OR arms.ppp_temporary_arm
            ),
            -- L2-79 Item 2: golf FIELD/winner one-sided-ask placeholder markets —
            -- mutually-exclusive golf markets with >=2 outcomes in the >=0.80 band
            -- (structurally impossible for genuine mex probabilities). Same
            -- eligibility predicate as the main outcome scan so the band count
            -- reflects the published population.
            golf_placeholder_markets AS (
                SELECT fo.market_id
                FROM futures_outcomes fo
                JOIN market_info mi ON mi.market_id = fo.market_id
                WHERE mi.category = 'golf'
                  AND mi.mutually_exclusive = true
                  AND mi.event_id IS NULL
                  AND COALESCE(fo.calibration_probability, fo.opening_probability) >= {GOLF_PLACEHOLDER_HIGH_BAND}
                  AND fo.opening_probability IS NOT NULL
                  AND fo.opening_probability > 0 AND fo.opening_probability < 1
                  -- Queue #261 Item 1: calibration-truth eligibility (allowlist).
                  -- Only sources whose winner is established INDEPENDENTLY of the
                  -- market's own price may grade a published forecast; guess,
                  -- structural-void, price-derived (clean_resolution /
                  -- settlement_sync) and unknown sources fail closed. Single
                  -- source of truth = resolution_authority.
                  AND fo.resolution_source IN {CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL}
                  -- Queue #267 (C44 #1): evidence-backed liquidity, not the volume
                  -- proxy. A never-bid/never-traded Kalshi placeholder is not a real
                  -- band member, so it must not inflate the >=2 over-subscription
                  -- count; a bid-bearing volume=0 outcome IS real and must count.
                  AND {kalshi_liquidity_exists_sql(source='mi.source')}
                GROUP BY fo.market_id
                HAVING COUNT(*) >= 2
            ),
            -- Queue #157 (#1012): multi-candidate normalization support.
            -- mex_win_counts: winner count over ALL outcomes of each mex market
            -- (the structure test — genuine partitions have exactly 1 winner;
            -- multi-winner = ladder/independent, zero-winner = void).
            -- #254: also trust market_type='field' (the shape classifier's
            -- ">2 outcomes, one winner" signal) — 65K field markets have the
            -- mutually_exclusive flag UNSET and were escaping this gate raw
            -- (sum ~4.56). The win_count=1 / >=3 / sum>1.15 guards below keep a
            -- mis-shaped or multi-winner field from being normalized anyway.
            -- Queue 299: the winner cardinality now comes from the shared
            -- market_result_shape scan (same count over ALL outcomes), and the
            -- ``mutually_exclusive = true OR market_type = 'field'`` admission
            -- test is REPLACED by proved exclusivity in mex_field_candidates
            -- below — the column defaults to True and is set for Yes/No claims
            -- and duels alike, so it never was evidence of a partition.
            -- Queue #262 Item 1: split the old single mex_norm_markets into a
            -- structural CANDIDATE detection (terminal price) + a price-expression
            -- DIVISOR, so a horizon can normalize on its snapshot yet still measure
            -- completeness against the FULL terminal field.
            --
            -- mex_field_candidates: markets that are genuine partition FIELDS — a
            -- STRUCTURAL roster identity independent of the horizon (mex/field,
            -- exactly one winner, >=3 terminal-eligible outcomes). Carries the full
            -- terminal-eligible member count so horizon completeness can require
            -- every member to be present.
            --
            -- Queue #263 Item 1: the cp-SUM > threshold gate is a PRICE-STATE
            -- decision, not a roster identity, so it MUST be evaluated on the price
            -- expression the surface finalizes on — NOT the terminal probability.
            -- It moved out of candidate detection and into ``normalized`` below,
            -- gated on ``mnm_cp_sum`` (the mex_field_divisor sum over {curve_price}).
            -- This makes field qualification horizon-honest: a terminal-low/horizon-
            -- high field qualifies at the horizon, a terminal-high/horizon-low field
            -- does not. On the headline path {curve_price} == terminal cp, so
            -- mnm_cp_sum == the old terminal SUM and the qualified set + count equal
            -- the old mex_norm_markets membership + COUNT exactly.
            mex_field_candidates AS (
                SELECT fo.market_id,
                    COUNT(*) AS terminal_eligible_n
                FROM futures_outcomes fo
                JOIN market_info mi ON mi.market_id = fo.market_id
                JOIN market_result_shape mrs ON mrs.market_id = fo.market_id
                -- Queue 299 rung 4: PROVED exclusivity only. The persisted shape
                -- classifier must positively assert an exhaustive single-winner
                -- field with an exclusive outcome relation; a default-true
                -- ``mutually_exclusive`` flag, an ``unknown`` relation and a
                -- cumulative-threshold ladder (gotcha #17 co-winners) are all
                -- refused. Mirrors market_exclusivity_is_proved().
                -- CAL-P162 (#1978): rendered by exclusivity_proved_sql() rather
                -- than inline, because RULE E's bundle arm needs the SAME test
                -- 80 lines above and two copies of one predicate in one query is
                -- how a mirror stops mirroring.
                WHERE {exclusivity_proved_sql('mi', 'mrs')}
                  AND fo.opening_probability IS NOT NULL
                  AND fo.opening_probability > 0 AND fo.opening_probability < 1
                  -- Queue #261 Item 1: calibration-truth eligibility (allowlist),
                  -- identical to the ranked_outcomes / golf-placeholder scans so
                  -- candidate detection matches the published population.
                  AND fo.resolution_source IN {CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL}
                  -- Queue #267 (C44 #1): the field ROSTER counts evidence-bearing
                  -- members only (matching the is_liquid survivor gate), so a
                  -- bid-bearing volume=0 member is part of the partition and a
                  -- never-bid/never-traded Kalshi phantom is not — instead of the
                  -- volume proxy that dropped real bid-bearing volume=0 members.
                  AND {kalshi_liquidity_exists_sql(source='mi.source')}
                GROUP BY fo.market_id
                HAVING COUNT(*) >= 3
            ),
            -- mex_field_divisor: per-market normalization divisor = sum of the
            -- CURVE PRICE over the eligible members PRESENT at this price
            -- expression (all terminal members on the headline; only members with
            -- a horizon snapshot when curve_price_join joins horizon_price). On the
            -- headline path cp_sum equals the old mex_norm_markets cp_sum exactly.
            mex_field_divisor AS (
                SELECT fo.market_id,
                    SUM({curve_price}) AS cp_sum,
                    COUNT(*) AS present_eligible_n
                FROM futures_outcomes fo
                JOIN mex_field_candidates mfc ON mfc.market_id = fo.market_id
                JOIN market_info mi ON mi.market_id = fo.market_id
                {curve_price_join}
                WHERE fo.opening_probability IS NOT NULL
                  AND fo.opening_probability > 0 AND fo.opening_probability < 1
                  AND fo.resolution_source IN {CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL}
                  -- Queue #267 (C44 #1): the divisor sums the SAME evidence-bearing
                  -- roster as mex_field_candidates / the is_liquid survivors, so for
                  -- a COMPLETE field the divisor equals the survivor sum and the
                  -- normalized partition still sums to ~1.0 (a phantom's price can
                  -- never inflate the divisor). Replaces the volume proxy.
                  AND {kalshi_liquidity_exists_sql(source='mi.source')}
                GROUP BY fo.market_id
            ),
{_virtual_market_ctes(frozen_vm_roster)}
            vm_stats AS (
                SELECT
                    vm.vm_id, vm.source, vm.category, vm.is_grouped,
                    vm.mutually_exclusive,
                    COUNT(DISTINCT vm.market_id) AS market_count,
                    COUNT(*) AS total_outcomes,
                    COUNT(*) FILTER (WHERE fo.is_winner = true) AS has_winner,
                    -- 12-CAL: an AFFIRMATIVE grade, which is NOT the complement
                    -- of has_winner. ``is_winner`` is nullable with a False
                    -- default, so "not a winner" spans a graded loss and a row
                    -- nothing ever graded. Only the first may be published as a
                    -- loss (gotcha #21), and until the lone-claim arm below,
                    -- nothing in this chain ever had to tell them apart.
                    COUNT(*) FILTER (WHERE fo.is_winner IS NOT NULL) AS graded,
                    COUNT(*) FILTER (WHERE fo.opening_probability IS NOT NULL
                                      AND fo.opening_probability > 0
                                      AND fo.opening_probability < 1) AS eligible,
                    -- D13 option A (Alex 2026-08-30, CAL-P155): the lone-claim
                    -- counts, PER MEMBER MARKET. Every other column here is a
                    -- fact about the VARIANT, and that is exactly why the arm
                    -- below could not be written correctly before these
                    -- existed: ``market_count = 1 AND total_outcomes = 1`` is
                    -- the only way a variant-grained aggregate can say "this
                    -- holds one lone claim", and it says it by ALSO requiring
                    -- that nothing else shares the variant.
                    --
                    -- ``mrs.n_outcomes`` is the market's outcome count AS
                    -- CAPTURED -- the same basis Queue 299 rung 1 counts on --
                    -- so "lone claim" means the same thing in both places.
                    -- ``COUNT(DISTINCT fo.market_id)`` because a market with
                    -- ``n_outcomes = 1`` contributes exactly one row and the
                    -- DISTINCT costs nothing, while making the column's grain
                    -- unmistakable to the next reader.
                    COUNT(DISTINCT fo.market_id) FILTER (
                        WHERE mrs.n_outcomes = 1
                          AND fo.is_winner IS NOT NULL) AS graded_lone_claims,
                    COUNT(DISTINCT fo.market_id) FILTER (
                        WHERE mrs.n_outcomes = 1
                          AND fo.is_winner IS NULL) AS ungraded_lone_claims
                FROM virtual_market vm
                JOIN futures_outcomes fo ON fo.market_id = vm.market_id{vm_stats_roster_predicate}
                -- LEFT, and ruling 125 is why. ``market_result_shape`` is one
                -- row per ``market_id`` and every market reaching this join has
                -- one (both relations are built over ``market_info`` joined to
                -- ``futures_outcomes``), so an inner join would be equivalent
                -- TODAY. A join added to a population CTE to compute a new
                -- column must not be able to change which rows that CTE
                -- aggregates over, and only the outer form guarantees that
                -- without depending on an argument. The two FILTERs above are
                -- NULL-safe by construction: a missing ``mrs`` row fails
                -- ``mrs.n_outcomes = 1`` and counts toward neither column.
                LEFT JOIN market_result_shape mrs ON mrs.market_id = vm.market_id
                GROUP BY vm.vm_id, vm.source, vm.category, vm.is_grouped,
                         vm.mutually_exclusive
            ),
            clean_vms AS (
                SELECT * FROM vm_stats
                WHERE eligible >= 1
                  AND (
                        has_winner >= 1
                        -- 12-CAL (YOUR-TURN D13). A LONE CLAIM -- one market,
                        -- one captured outcome, ungrouped -- is a complete,
                        -- scoreable prediction, and under the bare
                        -- ``has_winner >= 1`` gate it published if and ONLY if
                        -- it WON. Queue 299 rung 1 declines to exclude it on
                        -- purpose ("a lone Yes/No claim that legitimately
                        -- resolved No is not an authority failure" -- it
                        -- requires n_outcomes >= 2) and rung 3 declines it too
                        -- (market_type = 'field' only). BOTH carve-outs were
                        -- dead letters: this gate predates Queue 299 by three
                        -- months (#691, 2026-05-28) and deleted the row three
                        -- CTEs before either predicate could be evaluated.
                        --
                        -- This does NOT admit unknown truth. A >=2-outcome vm
                        -- that graded nobody still fails this predicate, and is
                        -- still removed downstream by ``no_winner_markets``,
                        -- exactly as rung 1 intends. ``graded >= 1`` refuses a
                        -- row whose ``is_winner`` was never written at all.
                        --
                        -- 🔴 THE ARM COUNTS PER MARKET. ALEX RULED IT (option A,
                        -- alex-inbox/calibration-919, 2026-08-30; #1978
                        -- CAL-P155), REVERSING CAL-P151's option B.
                        --
                        -- The retired form was ``market_count = 1 AND
                        -- total_outcomes = 1 AND graded >= 1``, and those counts
                        -- are per VARIANT. So TWO independently-graded lone
                        -- claims landing in the SAME variant carried
                        -- ``market_count = 2`` and the arm refused BOTH; with no
                        -- winner anywhere in the variant the first arm refused
                        -- them too, and every one of those rows is individually
                        -- the thing this arm calls "a complete, scoreable
                        -- prediction". They were excluded only because they were
                        -- counted together. CERT-485 found it as a row loss
                        -- (P1-a) — before D5 they published anyway, by matching
                        -- a SIBLING variant's admission row through the
                        -- two-column join; D5 did not create the exclusion, it
                        -- removed the accident that hid it. Alex was given both
                        -- options with the population cost declared UNMEASURED
                        -- and chose A knowingly.
                        --
                        -- 🔴 THERE IS NO ``ungraded_lone_claims = 0`` CONJUNCT
                        -- HERE ANY MORE, AND REMOVING IT IS THE POINT (CERT-514).
                        -- CAL-P155 shipped one as a fail-closed residue and the
                        -- cert blocked it: admission is variant-grained —
                        -- ``ranked_outcomes`` joins ONE ``clean_vms`` row per
                        -- variant — so refusing the variant to keep ONE ungraded
                        -- lone claim out ALSO withheld every independently graded
                        -- claim beside it. That is the sibling coupling option A
                        -- exists to remove; a narrower version of the same defect
                        -- is still the defect.
                        --
                        -- 🔴 AND NOTHING REPLACES IT, BECAUSE NOTHING HAS TO.
                        -- CAL-P156 first "fixed" this by moving the refusal down
                        -- a grain into a new rung 1b on ``is_winner IS NULL``.
                        -- CERT-520 blocked that, and the measurement settles it:
                        -- of 3,893,126 outcomes only 2,536 have ``is_winner IS
                        -- NULL`` and EVERY one also has ``resolution_source IS
                        -- NULL``, so the eligibility allowlist in
                        -- ``ranked_outcomes`` had already removed all of them.
                        -- The rung was dead code selecting a cohort that could
                        -- not reach it.
                        --
                        -- So the premise this conjunct was built on ("a
                        -- single-outcome member nothing ever graded has NO rung")
                        -- was simply false. It has one, and it always did: an
                        -- ungraded outcome carries ``resolution_source = NULL``
                        -- and is refused by truth eligibility, which is this
                        -- repository's canonical grade authority
                        -- (``calibration_graded_share.GRADED_PREDICATE``).
                        -- Admitting a variant still admits every member's
                        -- outcomes, and every member is still individually
                        -- answerable: ``n_outcomes >= 2`` members to rung 1 (this
                        -- arm only ever fires with ``has_winner = 0``, so each has
                        -- ``win_count = 0``), and ungraded members to the
                        -- eligibility filter. Nothing published here is unknown
                        -- truth, and nothing scoreable is held back for a
                        -- sibling's sake.
                        --
                        -- Pinned both directions by ``tests/integration/
                        -- test_calibration_vm_variant_join_pg.py`` (the
                        -- asymmetric fixture, whose MIXED variant seeds exactly
                        -- the graded-beside-ungraded case this must now split)
                        -- and by ``tests/test_calibration_lost_losses_12cal.py``.
                        OR graded_lone_claims >= 1
                  )
            ),
            ranked_outcomes AS MATERIALIZED (
                SELECT
                    -- Queue #157 (#1012): raw curve price + the per-market
                    -- normalization divisor. The actual normalization (cp /
                    -- mnm.cp_sum) is DEFERRED to the ``normalized`` CTE below,
                    -- because it is gated on FIELD COMPLETENESS (Queue #257 Item
                    -- 1) which can only be aggregated once these per-outcome
                    -- exclusion flags exist. Carry market_id so completeness can
                    -- be computed per market.
                    {curve_price} AS raw_cp,
                    -- Queue #262 Item 1: candidate membership (structural, terminal)
                    -- vs divisor (price-expression). is_mex_normalized keys on the
                    -- candidate so an incomplete horizon field is dropped WHOLE even
                    -- when <3 members are present at the snapshot.
                    mfc.market_id AS candidate_market_id,
                    mfd.cp_sum AS mnm_cp_sum,
                    fo.market_id AS market_id,
                    -- Queue #259 Item 2: carry outcome identity + per-market shape
                    -- so the cohort sweep selects the SAME final rows (row identity)
                    -- with its cohort keys, instead of re-deriving the population.
                    fo.id AS outcome_id,
                    fo.name AS outcome_name,
                    vm.market_type AS market_type,
                    vm.llm_league AS llm_league,
                    fo.is_winner AS is_winner,
                    (fo.calibration_probability IS NOT NULL
                     AND fo.calibration_probability IS DISTINCT FROM fo.opening_probability) AS price_moved,
                    cv.vm_id, cv.source, cv.category,
                    cv.eligible, cv.is_grouped,
                    (cv.is_grouped OR cv.eligible >= 3) AS is_multi,
                    -- #940 phase-1: never-bid/never-traded Kalshi placeholders are
                    -- excluded from the published set (read-side only, gotcha #21).
                    {KALSHI_LIQUIDITY_EXISTS} AS is_liquid,
                    {POLY_PLACEHOLDER_EXCLUDE} AS is_poly_placeholder,
                    -- Queue #220/221 Item 3: all-bands poly never-traded flag (for
                    -- the exclusion-symmetry census; does NOT gate the curve).
                    {POLY_NEVER_TRADED} AS is_poly_never_traded,
                    -- L2-79 Item 1: malformed 2-outcome mex binary (winner count
                    -- 0 = void, or 2 = impossible). mb.win_count carries which.
                    (mb.market_id IS NOT NULL) AS is_malformed_binary,
                    mb.win_count AS malformed_win_count,
                    -- Queue #159 (#1010): esports match-bundle exclusion flag.
                    (emb.market_id IS NOT NULL) AS is_esports_bundle,
                    -- CAL-P168 (#1978) RANK 1: K' = R1 + R2 + R3 + M1.
                    -- R1/R2/R3 arrive market-level via the join; M1 is the
                    -- ROW-level arm and is evaluated here, cell-scoped in its
                    -- own right so the flag can never act outside the ruled
                    -- allowlist even though it does not go through the CTE.
                    -- M1 is ADDITIVE, not a successor to R3: it removes 168
                    -- forced-to-half legs in markets that are NOT props
                    -- containers (ECE 12.87) which the name arm cannot see,
                    -- while R3 removes 19,980 rows M1 cannot see. Both stay.
                    (
                        ppp.market_id IS NOT NULL
                        OR (
                            (cv.source, cv.category)
                                IN {_sql_pair_tuple(PLAYER_PROPS_PLACEHOLDER_EXCLUDED_CELLS)}
                            AND {forced_midpoint_predicate('fo')}
                        )
                    ) AS is_player_props_placeholder,
                    -- CERT-647 (CAL-P170): the TEMPORARY subset of the flag
                    -- above — the rows that actually re-enter when the writer
                    -- is repaired, which is what the page promises.
                    --
                    -- 🔴 THE `AND NOT historical` IS THE WHOLE POINT, not a
                    -- tidy-up. A row held by R3 or M1 *and also* by R1 or R2
                    -- does NOT come back: the temporary arms release it and the
                    -- historical arms keep holding it. Counting it as temporary
                    -- would promise a return that never happens, which is the
                    -- same class of lie CERT-647 blocked, one level down. So
                    -- "temporary" means held ONLY by arms that end.
                    --
                    -- Subset by construction: every disjunct here implies a
                    -- disjunct of `is_player_props_placeholder`, so the
                    -- temporary count can never exceed the total.
                    -- `test_player_props_placeholder_kprime.py` asserts the
                    -- containment on rows rather than trusting the reading.
                    (
                        (
                            COALESCE(ppp.ppp_temporary_arm, false)
                            OR (
                                (cv.source, cv.category)
                                    IN {_sql_pair_tuple(PLAYER_PROPS_PLACEHOLDER_EXCLUDED_CELLS)}
                                AND {forced_midpoint_predicate('fo')}
                            )
                        )
                        AND NOT COALESCE(ppp.ppp_historical_arm, false)
                    ) AS is_player_props_placeholder_temporary,
                    -- Queue 299 rung 1: the market graded NOBODY — UNKNOWN truth,
                    -- not a set of losses (is_winner's default is False).
                    (nwm.market_id IS NOT NULL) AS is_no_winner_market,
                    -- Queue 299 rung 2: draw-capable duel with no draw member.
                    (dam.market_id IS NOT NULL) AS is_draw_authority_missing,
                    -- Queue 299 rung 3: a 'field' that captured <=1 member.
                    (opm.market_id IS NOT NULL) AS is_orphan_partition,
                    -- Queue 299 rung 4b: category-independent non-exclusive
                    -- bundle. CENSUS ONLY — this flag does NOT gate ``deduped``
                    -- outside esports (which keeps its own measured exclusion).
                    (nbm.market_id IS NOT NULL) AS is_nonexclusive_bundle,
                    -- L2-79 Item 2: golf one-sided-ask placeholder — this outcome
                    -- sits in the >=0.80 band of an over-subscribed golf mex market.
                    (gpm.market_id IS NOT NULL
                     AND COALESCE(fo.calibration_probability, fo.opening_probability)
                         >= {GOLF_PLACEHOLDER_HIGH_BAND}) AS is_golf_placeholder,
                    -- Queue #186 (#941, corrects #167): Kalshi player-prop
                    -- threshold "<subject>: N+" OVER captures. EXCLUDED when
                    -- (A) category='hockey' (NHL goal-family is corrupt at every
                    -- price band — illiquid degenerate capture, resolution sane)
                    -- or (B) the curve price is in the degenerate settlement-
                    -- collapse band (>= 0.90), which resolves 0.11–0.48 across
                    -- every series (gotcha #14/#21). Queue #263 Item 1: the band
                    -- reads {curve_price} (terminal COALESCE(cp, opening) on the
                    -- headline, the horizon snapshot on a horizon) so each horizon
                    -- classifies on its OWN price, not the terminal probability.
                    -- The 2026-07-13 verify disproved #167's no-live-bid keep:
                    -- real-bid rows are corrupt too (scorer + non-scorer both cp
                    -- 0.995). Curve price, not bid, is the honest discriminator;
                    -- below-band liquid series stay (SAVE all possible). Read-side
                    -- only, no regrade (sign-flip premise disproven).
                    {kalshi_prop_threshold_exclude_sql(
                        source='cv.source',
                        name='fo.name',
                        category='cv.category',
                        calibration_probability='fo.calibration_probability',
                        opening_probability='fo.opening_probability',
                        curve_price=curve_price,
                    )} AS is_kalshi_prop_threshold,
                    -- Queue #183 Item 4 (#182 twin): weather wide-spread fabricated
                    -- midpoint. A wide Kalshi weather book (ask-bid >= 0.50) with no
                    -- trade has no real price discovery at its midpoint. Weather-gated
                    -- (tech miscalibration is genuine per #182 census — kept).
                    {WEATHER_WIDE_SPREAD_EXCLUDE} AS is_weather_wide_spread,
                    -- Queue 300D Item 1 (C126 P1). Distance from 50% ALONE is not
                    -- a total order: complementary binary sides are routinely
                    -- equidistant (0.40 / 0.60), and with no secondary key
                    -- PostgreSQL may return either tied row across plans or
                    -- rebuilds. ``deduped`` publishes only ``rn = 1``, so the
                    -- observation identity, its winner label and its bucket could
                    -- all move with no source-data or methodology change — and a
                    -- staged execution can never be proved equivalent to an
                    -- oracle that is itself unstable.
                    --
                    -- Alex's 2026-08-03 ruling is the tie AUTHORITY: after
                    -- distance from 50%, break exact ties by the immutable
                    -- canonical outcome ID. Deliberately NOT a Yes/No or
                    -- favourite/underdog preference — any side preference would be
                    -- a product decision about which half of a book we believe,
                    -- and this is only a determinism rule.
                    ROW_NUMBER() OVER (
                        PARTITION BY cv.vm_id
                        ORDER BY {rn_order}, fo.id
                    ) AS rn,
                    -- The one-time delta instrument. RANK over the DISTANCE ONLY
                    -- is 1 for every row tied at the minimum, so ``rn = 2 AND
                    -- rn_distance_rank = 1`` marks exactly those questions whose
                    -- representative the new authority had to choose. Its ORDER BY
                    -- is a prefix of ``rn``'s, so PostgreSQL satisfies both windows
                    -- from one sort and this costs no extra pass over the heaviest
                    -- CTE in the product.
                    RANK() OVER (
                        PARTITION BY cv.vm_id
                        ORDER BY {rn_order}
                    ) AS rn_distance_rank
                FROM futures_outcomes fo
                JOIN virtual_market vm ON vm.market_id = fo.market_id
                -- D5 / ruling 125 (the sign reversed) — #1978, CAL-P150.
                -- ``vm_stats`` GROUPs BY FIVE columns; this join carried TWO.
                -- A virtual market whose members disagree on ``category``,
                -- ``is_grouped`` or ``mutually_exclusive`` therefore holds one
                -- ``clean_vms`` row PER VARIANT, and a two-column join matched
                -- every one of them: every outcome in that virtual market was
                -- emitted once per variant. Measured (alex-inbox/calibration-911,
                -- artifacts/cal-p139 + cal-p141 + cal-p142): 18,363 of 18,378
                -- groups of >=3 resolved markets (99.9%) carry mixed identity,
                -- and on the 13 cells folded exactly, 420,081 published rows
                -- are 266,137 distinct — 36.65% phantom, 1.5784x.
                --
                -- Ruling 125 says a join that can DELETE a row must carry every
                -- dimension that identifies the row. The same coarse key three
                -- CTEs earlier MULTIPLIES instead, and the remedy is the same:
                -- carry every dimension the aggregate is grouped on.
                --
                -- ``IS NOT DISTINCT FROM``, not ``=``, on the two nullable
                -- dimensions. ``GROUP BY`` puts NULLs in one group, so a plain
                -- equality join would match NO variant for those rows and turn
                -- this de-duplication into a silent row LOSS — the failure mode
                -- that is strictly worse than the defect. ``category`` is
                -- COALESCEd to 'uncategorized' in ``market_info`` and
                -- ``is_grouped`` is a COALESCEd boolean expression, so neither
                -- is nullable today; they are written NULL-safe anyway because
                -- the guarantee lives in another function.
                JOIN clean_vms cv
                  ON cv.vm_id = vm.vm_id
                 AND cv.source = vm.source
                 AND cv.category IS NOT DISTINCT FROM vm.category
                 AND cv.is_grouped IS NOT DISTINCT FROM vm.is_grouped
                 AND cv.mutually_exclusive IS NOT DISTINCT FROM vm.mutually_exclusive
                {curve_price_join}
                LEFT JOIN malformed_binaries mb ON mb.market_id = fo.market_id
                LEFT JOIN esports_multi_bundles emb ON emb.market_id = fo.market_id
                LEFT JOIN player_props_placeholder_markets ppp
                    ON ppp.market_id = fo.market_id
                LEFT JOIN no_winner_markets nwm ON nwm.market_id = fo.market_id
                LEFT JOIN draw_authority_markets dam ON dam.market_id = fo.market_id
                LEFT JOIN orphan_partition_markets opm ON opm.market_id = fo.market_id
                LEFT JOIN nonexclusive_bundle_markets nbm ON nbm.market_id = fo.market_id
                LEFT JOIN golf_placeholder_markets gpm ON gpm.market_id = fo.market_id
                LEFT JOIN mex_field_candidates mfc ON mfc.market_id = fo.market_id
                LEFT JOIN mex_field_divisor mfd ON mfd.market_id = fo.market_id
                WHERE fo.opening_probability IS NOT NULL
                  AND fo.opening_probability > 0 AND fo.opening_probability < 1
                  -- Queue #261 Item 1: calibration-truth eligibility (allowlist).
                  -- Replaces the scattered NOT-IN denylist with the single
                  -- resolution_authority contract: price-derived (clean_resolution
                  -- / settlement_sync) can no longer grade its own forecast, all
                  -- guess-family is excluded, and unknown sources fail closed.
                  AND fo.resolution_source IN {CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL}
                  -- Queue #267 (C44 #1): NO standalone volume gate here. The Kalshi
                  -- evidence predicate (is_liquid = KALSHI_LIQUIDITY_EXISTS) is
                  -- computed as a per-outcome flag above and filtered in ``deduped``
                  -- (WHERE ro.is_liquid). Keeping ALL candidates in ranked_outcomes
                  -- is what makes kalshi_included / kalshi_excluded honest: a
                  -- never-bid/never-traded phantom is COUNTED as excluded here, not
                  -- silently removed at eligibility; a bid-bearing volume=0 row now
                  -- survives is_liquid and reaches the curve (the C44 #1 fix).
            ),
            -- Queue #257 Item 1: FIELD-COMPLETENESS aggregation. For each
            -- normalization CANDIDATE market (mex/field, single winner over all
            -- outcomes, >=3 eligible, sum > threshold), count eligible members,
            -- survivors (those passing EVERY per-outcome published exclusion), and
            -- whether the winner survived. Queue #262 Item 1: eligible_n is the FULL
            -- terminal-eligible member count (mfc.terminal_eligible_n), NOT the
            -- present-outcome COUNT — so a horizon field with a member missing at
            -- the snapshot (present < terminal) is INCOMPLETE and dropped whole. On
            -- the headline path present == terminal, so eligible_n equals the old
            -- COUNT(*) over ranked_outcomes exactly and behavior is unchanged.
            field_completeness AS (
                SELECT ro.market_id,
                    MAX(mfc.terminal_eligible_n) AS eligible_n,
                    COUNT(*) FILTER (
                        WHERE ro.is_liquid AND NOT ro.is_poly_placeholder
                          AND NOT ro.is_malformed_binary
                          AND NOT ro.is_esports_bundle
                          -- CAL-P168: K' is a published per-outcome exclusion
                          -- too, so a field that loses a member to it is PARTIAL
                          -- and must be dropped whole rather than normalized
                          -- over its survivors.
                          AND NOT ro.is_player_props_placeholder
                          AND NOT ro.is_golf_placeholder
                          AND NOT ro.is_kalshi_prop_threshold
                          AND NOT ro.is_weather_wide_spread
                          -- Queue 299: the new rungs are published per-outcome
                          -- exclusions too, so a field that loses a member to
                          -- one of them is PARTIAL and must be dropped whole
                          -- rather than normalized over its survivors.
                          AND NOT ro.is_no_winner_market
                          AND NOT ro.is_draw_authority_missing
                          AND NOT ro.is_orphan_partition
                    ) AS survivor_n,
                    COUNT(*) FILTER (
                        WHERE ro.is_winner
                          AND ro.is_liquid AND NOT ro.is_poly_placeholder
                          AND NOT ro.is_malformed_binary
                          AND NOT ro.is_esports_bundle
                          AND NOT ro.is_player_props_placeholder
                          AND NOT ro.is_golf_placeholder
                          AND NOT ro.is_kalshi_prop_threshold
                          AND NOT ro.is_weather_wide_spread
                          AND NOT ro.is_no_winner_market
                          AND NOT ro.is_draw_authority_missing
                          AND NOT ro.is_orphan_partition
                    ) AS survivor_win_n
                FROM ranked_outcomes ro
                JOIN mex_field_candidates mfc ON mfc.market_id = ro.market_id
                GROUP BY ro.market_id
            ),
            -- Queue #257 Item 1: apply normalization ONLY to COMPLETE candidate
            -- fields (survivor_n = eligible_n AND winner survived AND >=3), so a
            -- published field sums to ~1.0 over its survivors. A candidate whose
            -- field is PARTIAL (a member was excluded) is flagged
            -- is_field_incomplete and dropped from the curve by ``deduped`` —
            -- never normalized over survivors. mnm.cp_sum equals the survivor sum
            -- exactly when complete, so cp / mnm_cp_sum normalizes to ~1.
            -- Queue #263 Item 1: a market is a genuine normalization FIELD when it
            -- is a structural partition candidate (mex_field_candidates) AND its
            -- curve-price sum clears the field threshold ON THE PRICE EXPRESSION
            -- (mnm_cp_sum = mex_field_divisor's SUM over {curve_price}: terminal cp
            -- on the headline, the horizon snapshot on a horizon). Moving the sum
            -- gate off terminal candidate detection makes qualification horizon-
            -- honest. On the headline mnm_cp_sum == the old terminal SUM, so
            -- ``is_field`` reduces to the old candidate membership exactly and a
            -- structural-but-below-threshold market keeps flowing to the multi pool
            -- (neither normalized nor dropped) exactly as before.
            normalized AS (
                SELECT ro.*,
                    (ro.candidate_market_id IS NOT NULL
                     AND ro.mnm_cp_sum > {MEX_NORMALIZE_THRESHOLD}
                     AND fc.survivor_n = fc.eligible_n
                     AND fc.survivor_win_n = 1
                     AND fc.survivor_n >= 3) AS is_mex_normalized,
                    (ro.candidate_market_id IS NOT NULL
                     AND ro.mnm_cp_sum > {MEX_NORMALIZE_THRESHOLD}
                     AND NOT (fc.survivor_n = fc.eligible_n
                              AND fc.survivor_win_n = 1
                              AND fc.survivor_n >= 3)) AS is_field_incomplete,
                    CASE WHEN ro.candidate_market_id IS NOT NULL
                              AND ro.mnm_cp_sum > {MEX_NORMALIZE_THRESHOLD}
                              AND fc.survivor_n = fc.eligible_n
                              AND fc.survivor_win_n = 1
                              AND fc.survivor_n >= 3
                         THEN ro.raw_cp / ro.mnm_cp_sum
                         ELSE ro.raw_cp
                    END AS adj_opening_probability
                FROM ranked_outcomes ro
                LEFT JOIN field_completeness fc ON fc.market_id = ro.market_id
            ),
            -- Queue #259 Item 1: mode-price detection is a PLACEHOLDER heuristic
            -- for the non-partition multi pool; a COMPLETE normalized field
            -- (is_mex_normalized) is a genuine partition summing to ~1.0, so its
            -- prices must NOT drive (nor be removed by) mode detection — else a
            -- uniform field (10 members @ 0.10) would be wiped. Incomplete fields
            -- are dropped anyway; exclude both so only publishable rows vote.
            --
            -- #2098 / RULING 125 — the mode is a fact about ONE SOURCE's legs,
            -- so it may only delete THAT source's legs.
            --
            -- ``vm_id`` is source-blind on its ``e:`` arm (``'e:' || event_id``,
            -- while ``event_sizes`` counts per ``(event_id, source)``), so two
            -- sources carrying >=3 resolved markets on one event share a vm_id.
            -- Every neighbouring aggregate is source-scoped deliberately —
            -- ``vm_stats`` GROUPs BY ``(vm_id, source, category, is_grouped,
            -- mutually_exclusive)`` and ``clean_vms`` JOINs on all five —
            -- 🔴 CORRECTED 2026-08-30 (D5, CAL-P150): this sentence used to read
            -- "GROUPs BY ``(vm_id, source)``, ``clean_vms`` JOINs on both", and
            -- it was false in BOTH halves. The aggregate always grouped on five;
            -- the join carried two. The comment cited the pair as the model
            -- citizen, ruling 125's own text repeated it, and a dedicated audit
            -- read the first two columns of the ``GROUP BY`` and stopped — which
            -- is how a 36.65% row duplication survived directly under a ruling
            -- written about coarse join keys. The join is fixed above; this
            -- correction stays because the wrong sentence is what hid it.
            -- — and this one was not: it grouped on ``vm_id`` alone and the
            -- join below matched on ``vm_id`` alone. A mode detected among one
            -- source's legs therefore DELETED the other source's legs sitting at
            -- the same price. Measured whole-domain (CAL-P087,
            -- ``artifacts/cal-p087/ARTIFACT-CAL-P087-2098-CROSS-SUPPRESSION.json``):
            -- 35 rows over 2 vm_ids; on ``e:14887630`` FOUR Polymarket legs
            -- deleted TWENTY-THREE Kalshi legs.
            --
            -- Ruling 125: a join that can DELETE a row must carry every
            -- dimension that identifies the row. Note this is three lines, not
            -- the two the staged spec named — ``mode_prices`` must also PROJECT
            -- ``source``, or the new join conjunct cannot be written.
            --
            -- Guarded by ``tests/integration/
            -- test_calibration_mode_price_source_scope_pg.py`` against a real
            -- Postgres, two-armed: it also executes the REVERTED SQL and asserts
            -- the suppression comes back, so green means red-first was proved
            -- rather than that nothing objected.
            mode_prices AS (
                SELECT vm_id, source, adj_opening_probability AS mode_price
                FROM normalized
                WHERE is_multi AND eligible >= 3 AND is_liquid
                  AND NOT is_mex_normalized AND NOT is_field_incomplete
                GROUP BY vm_id, source, adj_opening_probability, eligible
                HAVING COUNT(*) > GREATEST(eligible * 0.5, 2)
            ),
            deduped AS (
                SELECT ro.* FROM normalized ro
                LEFT JOIN mode_prices mp
                  ON mp.vm_id = ro.vm_id
                  AND mp.source = ro.source
                  AND mp.mode_price = ro.adj_opening_probability
                WHERE ro.is_liquid AND NOT ro.is_poly_placeholder
                    AND NOT ro.is_malformed_binary
                    AND NOT ro.is_esports_bundle
                    -- CAL-P168 (#1978) RANK 1: K' leaves the published curve.
                    -- Read-side only (gotcha #21) — the rows are dropped, never
                    -- re-graded. `is_winner` is truth and stays untouched; what
                    -- is wrong is the PRICE WE PUBLISHED, and the market's own
                    -- quote is still sitting in `opening_probability`.
                    AND NOT ro.is_player_props_placeholder
                    AND NOT ro.is_golf_placeholder
                    AND NOT ro.is_kalshi_prop_threshold
                    AND NOT ro.is_weather_wide_spread
                    -- Queue 299 rungs 1-3 (#1012): result authority before
                    -- shape. A market that graded nobody, a draw-capable duel
                    -- with no draw member, and a 'field' with <=1 captured
                    -- member are all UNKNOWN truth — excluded, never published
                    -- as confident losses and never re-graded (gotcha #21).
                    AND NOT ro.is_no_winner_market
                    AND NOT ro.is_draw_authority_missing
                    AND NOT ro.is_orphan_partition
                    AND NOT ro.is_field_incomplete
                    AND
                    CASE
                        -- Queue #259 Item 1 INVARIANT FIX: a COMPLETE normalized
                        -- field is a partition that sums to ~1.0 over EXACTLY its
                        -- survivor members (field_completeness proved every eligible
                        -- member survived every per-outcome exclusion). The mode /
                        -- extreme-tail filters below are placeholder heuristics for
                        -- the NON-partition multi pool; applying them here would drop
                        -- a member (a 0.001-normalized tail, or a uniform field's
                        -- modal price) and publish <1.0 — the exact defect C14 found
                        -- (0.99/0.20/0.001 -> tail dropped -> ~99.9%). Publish every
                        -- member of a complete field so the partition still sums to 1.
                        WHEN ro.is_mex_normalized THEN true
                        WHEN ro.is_multi
                            THEN ro.adj_opening_probability > 0.005
                             AND ro.adj_opening_probability < 0.98
                             AND mp.vm_id IS NULL
                        ELSE ro.rn = 1
                    END
            )"""


# =============================================================================
# Queue 300C — the coverage census + additive bridge (Alex's 2026-08-02 ruling).
#
# The public headline unit is PUBLISHED CURVE OBSERVATIONS (~653K). The much
# larger "outcomes with calibration-price coverage" (~1.28M) may only appear as
# a separately labelled census joined to the plotted rows by an additive bridge.
# The contract — units, rung order, unknown-vs-checked-zero — lives in
# ``app.utils.calibration_coverage_bridge``; this block is the one place that
# MEASURES it, and it measures it from the canonical population CTEs rather than
# from a second copy of the population (the C14 drift lesson).
#
# Precedence, not labels. An excluded outcome routinely trips several filters at
# once, so the per-filter counters the payload already publishes cannot be
# summed — they double-count. Each coverage outcome is assigned to the FIRST
# rung it matches, which makes the rungs a partition and the bridge exact.
#
# WHY THIS SHIPS OFF (2026-08-03).
# The census is measured inside the ``futures`` phase because that is the only
# place the population is already materialized — recomputing it costs the whole
# build. But the phase ledger read on deploy day says that phase is already
# past its budget WITHOUT the census:
#
#     plan status "infeasible", infeasible_phases ["futures"]
#     futures floors  1351697 / 1351955 / 1299533 ms   deadline 1380000 ms
#     last run: futures CANCELLED at 1299533 ms, nothing committed, nothing
#     published — which is why /api/calibration was serving a 26h-stale
#     last-good copy.
#
# The futures read alone wants ~22 minutes of a 23-minute deadline, so the four
# phases after it never start. Adding a scan of the coverage universe to that
# statement makes a build that already cannot finish finish less. So the switch
# below defaults OFF: the contract, the payload key, the serving-tier honesty
# and the Lane 2 fixture all ship now, and the census reports itself
# ``unavailable`` (never zero) until the phase has room.
#
# QUEUE 300D UPDATE (2026-08-03) — IT IS NO LONGER ONE CONSTANT.
#
# Queue 300D gave the futures phase a way to fit (staged, resumable chunks of
# whole virtual questions), which was the budget half of the blocker above. But
# staging exposed a SECOND blocker that a flag flip cannot clear:
#
#   ``coverage_universe`` scans every resolved futures outcome with a usable
#   price. That universe is not vm-scoped, so under chunking each chunk rescans
#   ALL of it and classifies every out-of-chunk outcome as
#   ``market_result_unavailable`` / ``question_ungraded``. Summed across N
#   chunks the total is ~N times the truth with the rungs skewed — a census
#   that is wrong in the CONFIDENT direction, which is precisely what this
#   bridge exists to prevent.
#
# So flipping this constant now requires splitting the census in two: the part
# attributable to a chunk (its own markets' outcomes) and ONE global pass for
# the rungs that belong to no chunk at all (``market_result_unavailable`` and
# the truth rungs — their outcomes are not in ``market_info``, so they are in no
# virtual market). ``_main_futures_sql`` REFUSES to build the staged statement
# with the census on rather than let that ship silently.
#
# Until then the census stays ``unavailable`` — never zero, never inferred,
# which is what Queue 300D Item 2's own acceptance asks for. With it False the
# emitted SQL is byte-identical to the pre-census statement, so the off state
# costs the build exactly nothing.
# =============================================================================

#: CAL-P020 (2026-08-09) turned this ON. CAL-P024 (2026-08-09, same day) turned
#: it back OFF, and this comment is the MEASUREMENT rather than an opinion,
#: because the pre-CAL-P020 version of it said only "off pending the chunk-scoped
#: universe" — which reads as unfinished work, so the next window finished the
#: work and flipped the switch. It was not the scoping that was missing. It was
#: the budget, and the budget was never re-measured.
#:
#: WHAT PRODUCTION SAID, from two consecutive beats of the staged futures build
#: (``calibration:main:phase_ledger``, read 2026-08-09 19:11-19:18Z):
#:
#: * 16:15:00Z, census OFF (master ``b4aa0039``): ``read:futures_unit`` 626,242 ms
#:   for **10 units committed** — **62.6 s/unit**.
#: * 18:15:00Z, census ON (master ``75dfee56``, CAL-P020 deployed ~17:11Z):
#:   ``read:futures_unit`` 632,103 ms for **1 unit committed** — **632 s/unit**.
#:
#: Same population, same ``STAGED_FUTURES_BUCKETS`` partition, same statement
#: except the census. **~10x per unit.** A beat's usable window is ~687 s
#: (726 s cancelled, less ~39 s to freeze the generation), so:
#:
#: * OFF: 128 units x 62.6 s = ~2.2 h of compute = **~13 beats**.
#: * ON:  128 units x 632 s  = ~22.5 h of compute = **~128 beats**, i.e. more
#:   than five days of uninterrupted hourly beats.
#:
#: It cannot get five days. ``_main_input_fingerprint`` hashes the SOURCE of the
#: build's SQL functions, so any deploy touching one resets the cursor to zero —
#: and this file took **25 commits in the 14 days** to 2026-08-09 (~1.8/day). The
#: build's convergence time exceeded the lane's own edit interval by an order of
#: magnitude. That is a RATE MISMATCH, not a cursor bug: CAL-P016's per-unit
#: retention works exactly as designed and cannot help while a unit costs ten
#: minutes.
#:
#: Note what this is NOT. Nothing of CAL-P020 is reverted — the chunk-scoped
#: universe, the global rung pass and the narrowed refusal are correct, tested,
#: and exactly what the census needs. Only the switch moved. The ordering is the
#: whole point: **the census EXPLAINS the curve, so it cannot come before the
#: curve publishes.** Turn it back on when the build is publishing AND a unit's
#: cost with it on has been measured against the beat window - not when the
#: surrounding code merely looks finished.
COVERAGE_CENSUS_ENABLED = False

#: The reason string a disabled census reports, so the page and any operator can
#: tell "we chose not to measure this yet" from "we measured nothing".
COVERAGE_CENSUS_DISABLED_REASON = "census_disabled_pending_futures_phase_budget"

#: rung key -> the SQL predicate that claims it, evaluated in
#: ``_COVERAGE_RUNG_KEYS`` order. Every flag is COALESCE-guarded to false
#: so a NULL flag routes exactly the way ``deduped``'s WHERE would treat it
#: (NULL is not true, so the row is not published) instead of falling through to
#: the catch-all and being mislabelled a representative loss.
_COVERAGE_RUNG_PREDICATES: tuple[tuple[str, str], ...] = (
    ("plotted_on_curve", "d.outcome_id IS NOT NULL"),
    ("market_result_unavailable", "mi.market_id IS NULL"),
    ("truth_source_missing", "cu.resolution_source IS NULL"),
    (
        "truth_ineligible_source",
        f"cu.resolution_source NOT IN {CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL}",
    ),
    ("question_ungraded", "n.outcome_id IS NULL"),
    (
        "malformed_or_unknown_truth",
        "COALESCE(n.is_no_winner_market, false) "
        "OR COALESCE(n.is_malformed_binary, false) "
        "OR COALESCE(n.is_draw_authority_missing, false) "
        "OR COALESCE(n.is_orphan_partition, false)",
    ),
    (
        "phantom_liquidity",
        "NOT COALESCE(n.is_liquid, false) OR COALESCE(n.is_poly_placeholder, false)",
    ),
    (
        "structural_artifact",
        "COALESCE(n.is_esports_bundle, false) "
        "OR COALESCE(n.is_golf_placeholder, false) "
        "OR COALESCE(n.is_kalshi_prop_threshold, false) "
        "OR COALESCE(n.is_weather_wide_spread, false)",
    ),
    ("field_incomplete", "COALESCE(n.is_field_incomplete, false)"),
    # No predicate: the terminal ELSE. A row that reached ``normalized``, was
    # refused by none of the rungs above, and still did not reach ``deduped``
    # was dropped by the representative rules (rn != 1, modal placeholder price,
    # extreme tail in a non-partition multi pool). NOTE: this catch-all is also
    # where a NEWLY ADDED ``deduped`` filter would silently land — the eval
    # corpus pins the rung set so adding one without a rung fails the contract.
    ("representative_not_selected", ""),
)


def _coverage_bridge_column(rung: str) -> str:
    """The one-row summary column name carrying ``rung``'s count."""
    return f"cb_{rung}"


def _coverage_universe_cte(*, chunk_scoped: bool) -> str:
    """The COVERAGE population — one definition, in one of two scopes.

    **Global** (``chunk_scoped=False``): every resolved futures outcome carrying
    a usable calibration price. Joined to ``futures_markets`` directly rather
    than to ``market_info`` so the symmetric DataGolf-residual withholding stays
    a VISIBLE rung (``market_result_unavailable``) instead of an invisible
    pre-filter.

    **Chunk-scoped** (``chunk_scoped=True``, CAL-P020): the same population
    restricted to the outcomes of THIS chunk's markets, by an INNER JOIN onto
    the roster-scoped ``market_info``. Additive across chunks because a market —
    and therefore its ``vm_id`` — never straddles a chunk boundary; that is the
    invariant ``plan_units`` exists to protect and that
    ``_STAGED_COUNT_DISTINCT_COLUMNS`` already records a dependency on.

    Under the chunk scope ``market_result_unavailable`` can never fire, because
    every row in the universe joined ``market_info`` to get here. Its members
    belong to no chunk at all, so they are counted exactly once by
    :func:`_coverage_global_rung_sql`. The rung is deliberately NOT dropped from
    the ladder in this scope — one ladder, counted zero, is a far smaller thing
    to keep honest than two ladders that agree today.
    """
    if chunk_scoped:
        return """
            coverage_universe AS (
                SELECT fo.id AS outcome_id,
                    fo.market_id AS market_id,
                    fo.resolution_source AS resolution_source,
                    (fo.calibration_probability IS NOT NULL) AS has_terminal_cal_price
                FROM futures_outcomes fo
                JOIN market_info mi ON mi.market_id = fo.market_id
                WHERE fo.opening_probability IS NOT NULL
                  AND fo.opening_probability > 0 AND fo.opening_probability < 1
            )"""
    return """
            coverage_universe AS (
                SELECT fo.id AS outcome_id,
                    fo.market_id AS market_id,
                    fo.resolution_source AS resolution_source,
                    (fo.calibration_probability IS NOT NULL) AS has_terminal_cal_price
                FROM futures_outcomes fo
                JOIN futures_markets fm ON fm.id = fo.market_id
                WHERE fm.status = 'resolved'
                  AND fo.opening_probability IS NOT NULL
                  AND fo.opening_probability > 0 AND fo.opening_probability < 1
            )"""


def _coverage_global_rung_sql() -> str:
    """CAL-P020: the ONE rung whose members belong to no chunk, counted once.

    ``market_result_unavailable`` is ``mi.market_id IS NULL`` — an outcome in the
    coverage universe whose market ``market_info`` dropped. Globally that is
    exactly the DataGolf residual cohort; under the staged scope it would
    otherwise be every out-of-chunk outcome, summed ~N times. So the staged path
    counts it here instead: once per generation, against the UNSCOPED
    ``market_info``.

    Reuses :func:`_calibration_population_ctes` VERBATIM for the same
    load-bearing reason :func:`_futures_generation_sql` does — a hand-written
    second copy of the eligibility predicate is the C14 drift, and here it would
    put the census and the curve on different definitions of "eligible market".
    Naming the full chain is free: PostgreSQL does not execute an unreferenced
    ``WITH`` subquery, so everything downstream of ``market_info`` is planned
    away and what runs is one pass over the coverage universe plus a hash
    anti-join.
    """
    return (
        "WITH "
        + _calibration_population_ctes()
        + ","
        + _coverage_universe_cte(chunk_scoped=False)
        + f"""
            SELECT COUNT(*) AS {_coverage_bridge_column('market_result_unavailable')},
                COUNT(*) AS cb_coverage_total,
                COUNT(*) FILTER (WHERE cu.has_terminal_cal_price)
                    AS cb_with_terminal_cal_price
            FROM coverage_universe cu
            LEFT JOIN market_info mi ON mi.market_id = cu.market_id
            WHERE mi.market_id IS NULL
        """
    )


def _coverage_bridge_ctes(*, frozen: bool = False) -> str:
    """The census CTEs, appended to the canonical population chain.

    Deliberately built ON TOP of ``market_info`` / ``normalized`` / ``deduped``
    inside the SAME statement rather than as a second read: the population is
    already materialized, so this costs one scan of the coverage universe plus
    hash joins, it cannot drift from the curve it explains, and both ends of the
    bridge are guaranteed to come from ONE generation of one transaction.

    ``frozen`` scopes the universe to the chunk (CAL-P020). The rung ladder below
    is IDENTICAL in both scopes — only the universe narrows.
    """
    if not COVERAGE_CENSUS_ENABLED:
        # Emit nothing at all — including the separating comma, which this block
        # owns — so the statement is byte-identical to the pre-census one rather
        # than merely equivalent to it.
        return ""

    predicate_keys = tuple(key for key, _sql in _COVERAGE_RUNG_PREDICATES)
    if predicate_keys != _COVERAGE_RUNG_KEYS:
        # A rung added to the contract with no predicate here (or vice versa)
        # would quietly land its outcomes in the catch-all. Refuse to build SQL
        # that cannot reconcile rather than publish a census that lies.
        raise ValueError(
            "coverage bridge rung drift: "
            f"contract={_COVERAGE_RUNG_KEYS} sql={predicate_keys}"
        )

    branches = "\n                        ".join(
        f"WHEN {sql} THEN '{key}'"
        for key, sql in _COVERAGE_RUNG_PREDICATES
        if sql
    )
    terminal = _COVERAGE_RUNG_PREDICATES[-1][0]
    filters = ",\n                    ".join(
        f"COUNT(*) FILTER (WHERE rung = '{key}') AS {_coverage_bridge_column(key)}"
        for key in _COVERAGE_RUNG_KEYS
    )
    return (
        ","
        + _coverage_universe_cte(chunk_scoped=frozen)
        + f""",
            -- FIRST MATCH WINS. The order is the contract's rung order; changing
            -- it moves outcomes between rungs and is a contract change.
            coverage_bridge AS (
                SELECT cu.has_terminal_cal_price,
                    CASE
                        {branches}
                        ELSE '{terminal}'
                    END AS rung
                FROM coverage_universe cu
                LEFT JOIN market_info mi ON mi.market_id = cu.market_id
                LEFT JOIN normalized n ON n.outcome_id = cu.outcome_id
                LEFT JOIN deduped d ON d.outcome_id = cu.outcome_id
            ),
            coverage_bridge_summary AS (
                SELECT
                    {filters},
                    COUNT(*) AS cb_coverage_total,
                    COUNT(*) FILTER (WHERE has_terminal_cal_price)
                        AS cb_with_terminal_cal_price
                FROM coverage_bridge
            )"""
    )


# Queue 300D Item 0: ONE statement text, built in one of two scopes.
#
# ``frozen=False`` is the monolith and is byte-identical to what this
# build has always issued. ``frozen=True`` is the same statement over
# one chunk of whole virtual questions, with the vm assignment injected
# from the generation roster instead of re-derived (see
# ``_virtual_market_ctes`` for why re-deriving over a subset is wrong).
#
# Deliberately ONE builder rather than two: a second copy of this
# 150-line SELECT is how the staged path and the monolith would drift
# apart on the first exclusion rung anybody added to only one of them.
def _main_futures_sql(*, frozen: bool = False) -> str:
    # Queue 300D Item 2 refused this combination outright, because
    # ``coverage_universe`` scanned EVERY resolved priced futures outcome. Under
    # chunking each chunk rescanned all of it and LEFT JOINed it against only its
    # own ``normalized`` / ``deduped``, classifying every out-of-chunk outcome as
    # ``market_result_unavailable`` — so ``cb_coverage_total`` came out ~N times
    # the real figure with the rungs badly skewed. A census wrong in the
    # CONFIDENT direction is the one thing the 300C bridge exists to prevent.
    #
    # CAL-P020 does the work that refusal was standing in for, so the guard
    # narrows to the invariant rather than the combination: under a frozen scope
    # the universe MUST be chunk-scoped. The blanket refusal cannot stay — since
    # CAL-P016 the staged path is the only one that can finish, so "census XOR
    # publish" had quietly become "never census".
    if frozen and COVERAGE_CENSUS_ENABLED:
        universe = _coverage_universe_cte(chunk_scoped=True)
        if "JOIN market_info" not in universe:
            raise ValueError(
                "coverage census is not chunk-scoped: enabling it under the "
                "staged futures path would multiply the census by the chunk "
                "count. Scope coverage_universe per chunk (plus one global pass "
                "for the out-of-population rungs) before flipping "
                "COVERAGE_CENSUS_ENABLED."
            )
    return (
            "WITH "
            + _calibration_population_ctes(
                frozen_vm_roster=frozen,
                market_info_extra=VM_ROSTER_MARKET_INFO_EXTRA if frozen else "",
            )
            # deduped is the LAST shared population CTE; liq_summary /
            # published_summary / bucketed + the bucket aggregation are
            # payload-only (the sweep selects deduped rows verbatim).
            + """,
            -- #940 phase-1 transparency: how many Kalshi outcomes the liquidity
            -- filter keeps vs drops (computed once from the materialized CTE).
            liq_summary AS (
                SELECT
                    COUNT(*) FILTER (WHERE source = 'kalshi' AND is_liquid) AS kalshi_included,
                    COUNT(*) FILTER (WHERE source = 'kalshi' AND NOT is_liquid) AS kalshi_excluded,
                    COUNT(*) FILTER (WHERE source = 'polymarket' AND is_poly_placeholder) AS poly_placeholder_excluded,
                    COUNT(*) FILTER (WHERE source = 'polymarket' AND NOT is_poly_placeholder) AS poly_included,
                    -- Queue #220/221 Item 3: exclusion-symmetry census. Poly
                    -- never-traded across ALL bands, and the asymmetry cohort
                    -- (never traded but outside the placeholder band, so still
                    -- IN the curve — the thing Kalshi excludes but poly does not).
                    COUNT(*) FILTER (WHERE source = 'polymarket' AND is_poly_never_traded) AS poly_never_traded_total,
                    COUNT(*) FILTER (WHERE source = 'polymarket' AND is_poly_never_traded AND NOT is_poly_placeholder) AS poly_never_traded_in_curve,
                    -- L2-79 Item 1: malformed-binary exclusion counts (eligible
                    -- outcomes flagged in ranked_outcomes, split by winner count).
                    COUNT(*) FILTER (WHERE is_malformed_binary AND malformed_win_count = 0) AS both_false_excluded,
                    COUNT(*) FILTER (WHERE is_malformed_binary AND malformed_win_count = 2) AS both_winner_excluded,
                    -- L2-79 Item 2: golf one-sided-ask placeholder exclusion count.
                    COUNT(*) FILTER (WHERE is_golf_placeholder) AS golf_placeholder_excluded,
                    -- Queue #157: multi-candidate normalization transparency —
                    -- how many curve outcomes had their probability normalized.
                    COUNT(*) FILTER (WHERE is_mex_normalized) AS mex_normalized_outcomes,
                    -- Queue #257 Item 1: field-completeness transparency. A
                    -- normalization CANDIDATE is a mex/field market that hit the
                    -- >=3 / one-winner / sum>threshold gate; it is PUBLISHED
                    -- (normalized) only if its field is complete, else EXCLUDED as
                    -- a partial field. Report the candidate vs published split so
                    -- the population change is honest, never silent.
                    COUNT(DISTINCT market_id) FILTER (
                        WHERE is_mex_normalized OR is_field_incomplete
                    ) AS mex_candidate_markets,
                    COUNT(DISTINCT market_id) FILTER (WHERE is_mex_normalized) AS mex_normalized_markets,
                    COUNT(DISTINCT market_id) FILTER (WHERE is_field_incomplete) AS field_incomplete_markets,
                    COUNT(*) FILTER (WHERE is_field_incomplete) AS field_incomplete_outcomes,
                    -- Queue #159: esports match-bundle exclusion count (eligible
                    -- outcomes flagged in ranked_outcomes that the filter drops).
                    COUNT(*) FILTER (WHERE is_esports_bundle) AS esports_bundle_excluded,
                    -- CAL-P168 (#1978): rank 1's total, counted separately from
                    -- the bundle total because they are different rules. The
                    -- payload ADDS them for `nonexclusive_bundle_filter.excluded`
                    -- (one bullet, one number the per-cell map must sum to) and
                    -- keeps `esports_multi_bundle_filter.excluded` on the bundle
                    -- count alone — that key is a live public contract about the
                    -- bundle rule and must not silently start meaning something
                    -- broader.
                    COUNT(*) FILTER (WHERE is_player_props_placeholder)
                        AS player_props_placeholder_excluded,
                    COUNT(DISTINCT market_id) FILTER (WHERE is_player_props_placeholder)
                        AS player_props_placeholder_markets,
                    -- CERT-647 (CAL-P170): the temporary SUBSET of the pair
                    -- above. Emitted as its own count rather than derived on
                    -- the Python side, because the historical remainder is
                    -- published as `total - temporary` and a derived total is
                    -- how the two halves stop summing to the whole.
                    COUNT(*) FILTER (WHERE is_player_props_placeholder_temporary)
                        AS player_props_placeholder_temporary_excluded,
                    COUNT(DISTINCT market_id)
                        FILTER (WHERE is_player_props_placeholder_temporary)
                        AS player_props_placeholder_temporary_markets,
                    -- CAL-P162 (#1978): the PER-CELL split of the same count.
                    -- Alex's rank-2 ruling requires the disclosure name which
                    -- cell shrank; one total cannot, because the filter is
                    -- allowlisted per cell. Columns are generated from the
                    -- constant, so they cannot drift from the cells they count.
                    """
            + nonexclusive_bundle_cell_columns_sql()
            + """,
                    -- Queue 299 (#1012): result-authority + shape rung counts.
                    -- Candidate-side (pre-dedup) counts, matching every other
                    -- exclusion block, so each rung's size is transparent.
                    COUNT(*) FILTER (WHERE is_no_winner_market) AS no_winner_excluded,
                    COUNT(DISTINCT market_id) FILTER (WHERE is_no_winner_market) AS no_winner_markets,
                    COUNT(*) FILTER (WHERE is_draw_authority_missing) AS draw_authority_excluded,
                    COUNT(DISTINCT market_id) FILTER (WHERE is_draw_authority_missing) AS draw_authority_markets,
                    COUNT(*) FILTER (WHERE is_orphan_partition) AS orphan_partition_excluded,
                    COUNT(DISTINCT market_id) FILTER (WHERE is_orphan_partition) AS orphan_partition_markets,
                    -- Census only (never gates the curve outside esports).
                    COUNT(*) FILTER (WHERE is_nonexclusive_bundle) AS nonexclusive_bundle_candidates,
                    COUNT(DISTINCT market_id) FILTER (WHERE is_nonexclusive_bundle) AS nonexclusive_bundle_markets,
                    -- Queue #167 (#941/#1054): Kalshi player-prop threshold count.
                    COUNT(*) FILTER (WHERE is_kalshi_prop_threshold) AS kalshi_prop_threshold_excluded,
                    -- Queue #183 Item 4: weather wide-spread exclusion count.
                    COUNT(*) FILTER (WHERE is_weather_wide_spread) AS weather_wide_spread_excluded,
                    -- Queue 300D Item 1: the one-time representative tie delta.
                    -- ``rn_distance_rank = 1`` is every row tied at the minimum
                    -- distance from 50%; a SECOND such row (``rn = 2``) proves the
                    -- rn=1 representative was picked out of an exact tie rather
                    -- than won outright. Scoped to the branch that actually
                    -- consumes ``rn`` — ``deduped`` uses it only for the non-multi,
                    -- non-normalized-field case — so this counts questions whose
                    -- published side the new authority decides, and nothing else.
                    -- Reported on its own rung: an identity delta must never be
                    -- readable as a population change.
                    COUNT(*) FILTER (
                        WHERE rn = 2 AND rn_distance_rank = 1
                          AND NOT is_multi AND NOT is_mex_normalized
                    ) AS representative_tie_broken
                FROM normalized
            ),
            -- Queue #259 Item 1 (C14 P2): PUBLISHED counts from ``deduped`` (the
            -- rows that actually reach the curve), distinct from ``liq_summary``'s
            -- CANDIDATE counts over ``normalized`` (pre-dedup). Before the invariant
            -- fix a normalized field could be counted as published in liq_summary
            -- yet lose a member in deduped; reporting both makes the population
            -- change honest. With the fix these two normalized-market counts are
            -- equal (every complete field publishes intact) — a regression guard.
            published_summary AS (
                SELECT
                    COUNT(DISTINCT market_id) FILTER (WHERE is_mex_normalized) AS mex_published_markets,
                    COUNT(*) FILTER (WHERE is_mex_normalized) AS mex_published_outcomes,
                    COUNT(*) AS published_outcomes,
                    COUNT(DISTINCT vm_id) AS published_questions
                FROM deduped
            )"""
            + _coverage_bridge_ctes(frozen=frozen)
            + """,
            bucketed AS (
                SELECT *, LEAST(FLOOR(adj_opening_probability * 10)::int, 9) AS bucket_idx
                FROM deduped
            )
            SELECT bucket_idx, source, category, price_moved,
                -- Queue 299 rung 4b: carried as a GROUPING dimension (not a
                -- filter) so the published bundle census can report the cohort's
                -- own n/ECE against the remainder, per category. The Python
                -- side merges these rows back on the original four keys, so the
                -- served ``buckets`` list keeps its exact prior shape and size.
                is_nonexclusive_bundle,
                """
            # Queue 300D Item 0: COUNT(*) counts the null-extended row that the
            # staged path's LEFT JOIN produces for an EMPTY chunk, which would
            # publish a phantom bucket of size 1. Counting a column that is
            # never NULL on a real row (``bucket_idx`` is a FLOOR expression)
            # gives 0 there and is otherwise identical to COUNT(*).
            + ("COUNT(bucketed.bucket_idx)" if frozen else "COUNT(*)")
            + """ AS n,
                SUM(CASE WHEN is_winner THEN 1 ELSE 0 END) AS winners,
                AVG(adj_opening_probability) AS avg_prob,
                SUM(adj_opening_probability::float) AS sum_prob,
                SUM((adj_opening_probability::float - CASE WHEN is_winner THEN 1.0 ELSE 0.0 END)^2) AS sum_sq_err,
                MAX(ls.kalshi_included) AS kalshi_included,
                MAX(ls.kalshi_excluded) AS kalshi_excluded,
                MAX(ls.poly_placeholder_excluded) AS poly_placeholder_excluded,
                MAX(ls.poly_included) AS poly_included,
                MAX(ls.poly_never_traded_total) AS poly_never_traded_total,
                MAX(ls.poly_never_traded_in_curve) AS poly_never_traded_in_curve,
                MAX(ls.both_false_excluded) AS both_false_excluded,
                MAX(ls.both_winner_excluded) AS both_winner_excluded,
                MAX(ls.golf_placeholder_excluded) AS golf_placeholder_excluded,
                MAX(ls.mex_normalized_outcomes) AS mex_normalized_outcomes,
                MAX(ls.mex_candidate_markets) AS mex_candidate_markets,
                MAX(ls.mex_normalized_markets) AS mex_normalized_markets,
                MAX(ls.field_incomplete_markets) AS field_incomplete_markets,
                MAX(ls.field_incomplete_outcomes) AS field_incomplete_outcomes,
                MAX(ls.esports_bundle_excluded) AS esports_bundle_excluded,
                -- CAL-P168 (#1978) rank 1: the same carry for K''s totals. A
                -- column emitted by the inner scan and dropped here reads as a
                -- missing attribute at runtime and a silently absent disclosure
                -- on the page — the exclusion failing OPEN. Caught in build by
                -- `test_no_column_is_declared_that_the_statement_never_emits`.
                MAX(ls.player_props_placeholder_excluded)
                    AS player_props_placeholder_excluded,
                MAX(ls.player_props_placeholder_markets)
                    AS player_props_placeholder_markets,
                -- CERT-647 (CAL-P170): same carry for the temporary subset.
                MAX(ls.player_props_placeholder_temporary_excluded)
                    AS player_props_placeholder_temporary_excluded,
                MAX(ls.player_props_placeholder_temporary_markets)
                    AS player_props_placeholder_temporary_markets,
                -- CAL-P162 (#1978): carry the per-cell split through the outer
                -- aggregate, generated from the same constant as the inner one.
                """
            + _nonexclusive_bundle_cell_passthrough_sql()
            + """,
                MAX(ls.no_winner_excluded) AS no_winner_excluded,
                MAX(ls.no_winner_markets) AS no_winner_markets,
                MAX(ls.draw_authority_excluded) AS draw_authority_excluded,
                MAX(ls.draw_authority_markets) AS draw_authority_markets,
                MAX(ls.orphan_partition_excluded) AS orphan_partition_excluded,
                MAX(ls.orphan_partition_markets) AS orphan_partition_markets,
                MAX(ls.nonexclusive_bundle_candidates) AS nonexclusive_bundle_candidates,
                MAX(ls.nonexclusive_bundle_markets) AS nonexclusive_bundle_markets,
                MAX(ls.kalshi_prop_threshold_excluded) AS kalshi_prop_threshold_excluded,
                MAX(ls.weather_wide_spread_excluded) AS weather_wide_spread_excluded,
                MAX(ls.representative_tie_broken) AS representative_tie_broken,
                -- Queue #259 Item 1 (C14 P2): published (post-dedup) counts.
                MAX(ps.mex_published_markets) AS mex_published_markets,
                MAX(ps.mex_published_outcomes) AS mex_published_outcomes,
                MAX(ps.published_outcomes) AS published_outcomes,
                MAX(ps.published_questions) AS published_questions"""
            # Queue 300C: the coverage census rides along as constant 1-row
            # columns, exactly like liq_summary / published_summary above. The
            # GROUP BY is untouched, so every published bucket keeps its shape.
            + _coverage_bridge_select_columns()
            # Queue 300D Item 0: the staged path drives from the 1-row censuses
            # and LEFT JOINs the buckets, so a chunk whose every question is
            # excluded still returns its candidate-side counts (``liq_summary``
            # is computed over ``normalized``, PRE-dedup) on a single
            # null-keyed row instead of returning nothing and silently dropping
            # them from the total. The merge routes that row to the census and
            # never to a bucket. With buckets present the two forms produce the
            # same rows, so the monolith keeps the original CROSS JOIN and stays
            # byte-identical.
            + ("""
            FROM liq_summary ls
            CROSS JOIN published_summary ps
            LEFT JOIN bucketed ON true""" if frozen else """
            FROM bucketed
            CROSS JOIN liq_summary ls
            CROSS JOIN published_summary ps""")
            + _coverage_bridge_join()
            + """
            GROUP BY bucket_idx, source, category, price_moved, is_nonexclusive_bundle
            ORDER BY bucket_idx, source, category, price_moved, is_nonexclusive_bundle
        """)


#: How much of the WORST unit observed this beat must still be on the clock
#: before the loop is allowed to start another one (CAL-P038, #1597).
#:
#: The loop's only prior gate was ``deadline_exceeded()`` — "is there any time
#: left" — which is not the question. A unit takes ~70s; a beat that starts one
#: with 30s left hands it a ``statement_timeout`` of 27s (see
#: :func:`~app.utils.calibration_phase_ledger._statement_timeout_for`, which
#: scales the inner margin down proportionally rather than refusing), Postgres
#: cancels it, and ``QueryCanceledError`` propagates out of the phase. So the
#: LAST unit of every deadline-reaching beat was guaranteed to be cancelled, and
#: the beat's terminal was ``timeout``/``DBAPIError`` instead of the honest
#: partial the design already has a type for.
#:
#: That is not cosmetic. :class:`~app.tasks.calibration_main_build.StagedFuturesIncomplete`
#: classifies to ``cancelled``, NOT ``failed`` — precisely "a working build must
#: not page anybody RED for doing what it was designed to do". Production has
#: ``incompletes_24h = 0`` against ``consecutive_failures = 199``: the clean path
#: exists and has never once been reached, because the cancellation always won
#: the race. It also costs the ledger its convergence projection, since
#: :func:`_record_convergence_projection` runs AFTER the loop and a throw skips
#: it — which is why ``staged:beats_to_publish`` is absent from every ledger.
#:
#: 1.25 rather than 1.0 because the bound is the worst unit SO FAR, and the next
#: unit may be worse. The cost of the margin is at most one unit of window per
#: beat (~5%); the cost of omitting it is a guaranteed hard failure per beat.
STAGED_UNIT_WINDOW_SAFETY = 1.25


def _unit_fits_in_window(
    remaining_ms: int, worst_unit_ms: float, prior_unit_ms: float = 0.0
) -> bool:
    """Whether another unit may be STARTED, not merely whether time remains.

    ``worst_unit_ms <= 0`` means this beat has not completed a unit yet.
    ``prior_unit_ms`` is CAL-P081's answer to that (#2052): the PREVIOUS beat's
    measured ``unit_ms``, carried on the plan, which exists before this beat has
    completed anything. It closes the residual the paragraph below used to end
    on — "a beat whose FIRST unit does not fit still ends in a cancellation" —
    without inventing a constant, because it is a measurement the build has been
    taking all along and the loop simply never read.

    Both are consulted and the LARGER wins. They are different evidence, not
    rival estimates: ``worst_unit_ms`` is this beat's own worst observation and
    ``prior_unit_ms`` is last beat's mean, so taking the max is the conservative
    reading in every combination, and the fence never loosens because a good
    beat followed a bad one.

    With neither the answer is still True — a beat must be allowed to attempt one
    unit or the build can never progress, and refusing on a number we do not have
    would be exactly the invented constant this module keeps refusing to write.

    **This predicate was NOT the hole #2052 fell through, and saying so is the
    point.** On the 18:37:31Z beat it admitted the sixth unit correctly: ~914,000
    ms remained against a worst-so-far of at most 361,010 ms. The unit then cost
    901,266 ms. No admission rule reading past cost can refuse an admission that
    past cost endorses; what was missing is a bound on the unit ONCE STARTED, and
    that lives in ``statement_timeout_for_unit``, not here.
    """
    if remaining_ms <= 0:
        return False
    reference = max(float(worst_unit_ms or 0.0), float(prior_unit_ms or 0.0))
    if reference <= 0:
        return True
    return remaining_ms >= reference * STAGED_UNIT_WINDOW_SAFETY


def _record_convergence_projection(
    runner,
    *,
    done: int,
    planned: int,
    ran_this_beat: int,
    unit_ms_this_beat: float,
    worst_unit_ms: float = 0.0,
) -> None:
    """Say, in the ledger, how many more beats this build needs to publish.

    CAL-P024. The ledger already recorded ``read:futures_unit`` and the cursor
    already recorded ``committed_units``; nothing divided one by the other, so
    the single most important fact about the build — **will it ever finish** —
    lived in two rows of two different snapshots and had to be reconstructed by
    hand, a day late, by someone who thought to look.

    Both times that reconstruction was done it changed the plan. On 2026-08-09
    it turned "the staged build is working, ~13 beats out" into "~128 beats out,
    i.e. never, because a deploy resets it roughly every 13 hours". A build that
    needs 128 more beats should say 128 on its own first beat.

    Deliberately recorded even when ``ran_this_beat`` is 0: a beat that banked
    nothing is the most important one to be able to see, and an absent stage
    reads as "fine" (gotcha #53). ``unit_ms_mean`` is then omitted rather than
    guessed, because there is no sample to average.
    """
    remaining = max(0, planned - done)
    runner.ledger.record_stage("staged:units_done", done)
    runner.ledger.record_stage("staged:units_planned", planned)
    runner.ledger.record_stage("staged:units_this_beat", ran_this_beat)
    if not ran_this_beat:
        return
    unit_ms_mean = unit_ms_this_beat / ran_this_beat
    runner.ledger.record_stage("staged:unit_ms_mean", int(unit_ms_mean))
    # CAL-P038: the mean sizes the build, the WORST unit sizes the window check
    # that decides whether the beat ends honest or cancelled. Both are recorded
    # because a large gap between them is itself the diagnosis — it says the
    # units are unevenly sized, which is a plan/partition problem, not a budget
    # one, and no timeout change can fix it.
    if worst_unit_ms > 0:
        runner.ledger.record_gauge("staged:unit_ms_worst", int(worst_unit_ms))
    # The window a FUTURE beat gets for units is the phase budget less what
    # freezing the generation costs — measured from this beat rather than
    # assumed, since the freeze is the one cost every beat pays again.
    window_ms = runner.ledger.remaining_ms(elapsed_ms=0)
    usable_ms = max(0.0, window_ms - (runner.elapsed_ms() - unit_ms_this_beat))
    units_per_beat = usable_ms / unit_ms_mean if unit_ms_mean > 0 else 0.0
    beats = math.ceil(remaining / units_per_beat) if units_per_beat >= 1 else -1
    # -1 is NOT "unknown": it is "this beat could not complete a single unit in
    # its whole window", which is a different and worse fact than a large count.
    runner.ledger.record_stage("staged:beats_to_publish", beats)
    logger.info(
        "calibration staged futures: %d/%d units, %.1f s/unit, ~%.1f units/beat "
        "=> %s beats to publish",
        done, planned, unit_ms_mean / 1000.0, units_per_beat,
        "MORE THAN ONE BEAT PER UNIT" if beats < 0 else beats,
    )


async def _run_staged_futures(db, runner, sql_builder):
    """Read the futures population one chunk of whole virtual questions at a time.

    Queue 300D Item 0. Three stages, in the order C126's consumption note fixed:

    1. **Freeze one generation.** :func:`_futures_generation_sql` resolves the
       whole population's virtual-question assignment once. Its digest is the
       generation identity — if the roster changes under us (a late arrival, a
       deploy, a settled market entering the population) the digest moves and
       every banked unit from the old roster is refused rather than mixed in.
    2. **Process whole units.** Each chunk replays the frozen assignment over
       its own markets, commits, and only THEN advances the cursor. A beat that
       runs out of window stops between chunks with everything it proved banked.
    3. **Finalize globally, or not at all.** Distinct-question counts, exclusion
       censuses and canonical buckets are folded from ALL units of ONE
       generation. Until every planned unit is in, this returns ``None`` and the
       caller publishes nothing — partial is not done.

    Returns the merged row list on completion, or ``None`` when the generation
    is still incomplete. ``None`` is not an error: it is a beat's honest report
    that it made progress and the next one will finish.
    """
    from app.tasks.calibration_main_build import (
        STAGED_FUTURES_BUCKETS,
        is_statement_timeout,
        load_staged_cursor,
        save_staged_cursor,
        staged_lease,
    )
    from app.utils.calibration_staged_futures import (
        DEFAULT_CENSUS_COLUMNS,
        advance,
        collect_unit_results,
        generation_fingerprint,
        is_complete,
        merge_futures_rows,
        plan_units,
        retain_planned_units,
    )

    # The merge refuses a column it was not told the KIND of, on purpose — a
    # passthrough summed is double-counted, an additive broadcast is frozen at
    # one chunk's mass, and a dropped one silently disappears from the payload.
    # So the statement's census set is declared HERE, next to the statement that
    # emits it, rather than left to a default in the pure module that cannot see
    # a column this build added. Three extras beyond the default set:
    #   * ``representative_tie_broken`` — Queue 300D Item 1, always emitted.
    #   * ``nxb_cell_*`` — CAL-P162's per-cell disclosure, always emitted, and
    #     generated from the constant so a new cell arrives here automatically
    #     rather than being remembered (CAL-P164).
    #   * ``cb_*`` — Queue 300C's coverage census, only when it is switched on.
    census_columns = (
        tuple(DEFAULT_CENSUS_COLUMNS)
        + ("representative_tie_broken",)
        + NONEXCLUSIVE_BUNDLE_CELL_COLUMNS
    )
    if COVERAGE_CENSUS_ENABLED:
        census_columns += tuple(
            _coverage_bridge_column(key) for key in _COVERAGE_RUNG_KEYS
        ) + ("cb_coverage_total", "cb_with_terminal_cal_price")
    from app.utils.calibration_phase_ledger import (
        PHASE_FUTURES,
        REFUSE,
        STAGED_UNIT_MAX_CANCELLATIONS,
        TERMINAL_PARTIAL,
    )

    # -- Stage 1: freeze the generation ---------------------------------------
    with runner.stage("read:futures_generation"):
        roster = (await db.execute(text(_futures_generation_sql()))).all()
    await runner.commit(db)

    gen_digest = generation_fingerprint(roster)
    chunks = plan_units(roster, buckets=STAGED_FUTURES_BUCKETS)
    # market_id -> its FROZEN assignment. The chunk knows which markets it owns;
    # this is what each one was assigned to when the generation was taken, and
    # it is what gets replayed into the chunk statement instead of re-derived.
    assignment = {
        int(row.market_id): (str(row.vm_id), bool(row.is_grouped)) for row in roster
    }
    logger.info(
        "calibration staged futures: generation %s — %d markets in %d units",
        gen_digest, len(roster), len(chunks),
    )
    if not chunks:
        # An empty population is a real answer, not a failure, and it is
        # complete by definition. Returning [] lets the build publish the
        # honest empty curve rather than stalling forever on zero units.
        return []

    cursor, action, reason = await load_staged_cursor(
        population_version=runner.population_version,
        # CAL-P205 (#2052), layer 1. The STAGED CURSOR keys off the statement its
        # units actually ran, not off four functions' source text. A banked unit
        # is rows produced by one statement, so an edit to the renderer — which
        # moves ``runner.fingerprint`` and today discards a ~26-hour rebuild —
        # cannot change what those rows ARE and must not discard them.
        #
        # ``runner.fingerprint`` (the wide digest) is UNCHANGED and still governs
        # the carried PHASE outputs via ``decode_main_checkpoint``; the two
        # digests answer different questions and are deliberately not merged.
        input_fingerprint=staged_unit_fingerprint(),
        generation_fingerprint=gen_digest,
        owner=runner.owner,
        generation=runner.generation,
        # The cutover, and it must cost ZERO banked units — this change exists to
        # stop the bank being thrown away, so paying one wipe to install it would
        # be self-defeating. The cursor on disk right now is stamped wide.
        legacy_input_fingerprint=runner.fingerprint,
    )
    if action == REFUSE:
        # Another beat holds an unexpired lease on this generation. Two workers
        # each advancing half a cursor is the one way this design corrupts, so
        # standing down is the correct behaviour, not a degraded one.
        logger.info("calibration staged futures: cursor held by another run — standing down")
        return None
    runner.ledger.record_stage(f"staged:cursor_{action}", 0)
    # CAL-P024: the action alone is not diagnostic. Five distinct causes produce
    # INVALIDATE, and on 2026-08-09 the one that fired (a deploy moving
    # ``_main_input_fingerprint``) cost the build all ten units it had banked —
    # a fact that took source reading and `git show` across two merges to
    # establish, because the ledger recorded only "invalidate".
    runner.ledger.record_stage(f"staged:cursor_reason:{reason}", 0)
    logger.info("calibration staged futures: cursor %s (%s)", action, reason)

    # CAL-P016: the roster moves between every pair of hourly beats, so a cursor
    # is now kept and pruned per unit instead of discarded whole. Only units the
    # new plan still asks for survive; the rest are recomputed. ``dropped`` is
    # the drift cost of this beat and is recorded, because "how many units did
    # the arrival cost us" is exactly the number that says whether the build is
    # converging or thrashing.
    cursor, dropped = retain_planned_units(cursor, chunks)
    if dropped:
        runner.ledger.record_stage("staged:units_dropped", len(dropped))
        logger.info(
            "calibration staged futures: roster drift dropped %d/%d banked units",
            len(dropped), len(dropped) + len(cursor.committed_units),
        )

    # -- Stage 2: process whole units -----------------------------------------
    chunk_sql = text(sql_builder(frozen=True))
    done = 0
    ran_this_beat = 0
    unit_ms_this_beat = 0.0
    worst_unit_ms = 0.0
    # CAL-P081 (#2052): the PREVIOUS beat's measured unit cost, carried on the
    # plan. Read once, outside the loop, because it does not change within a
    # beat — and read at all because until now the loop's only evidence was
    # evidence this beat had generated, which on the first unit is none.
    cancelled_this_beat = 0
    prior_unit_ms = float(runner.measured_unit_ms(PHASE_FUTURES) or 0.0)
    if prior_unit_ms > 0:
        runner.ledger.record_gauge("staged:prior_unit_ms", int(prior_unit_ms))
    else:
        # Ruling 075, second clause: "we have no carried cost" must not render
        # identically to "the carried cost is zero".
        runner.ledger.record_gauge("staged:prior_unit_reason:unmeasured", 1)
    for chunk in chunks:
        if cursor.has(chunk.key):
            done += 1
            continue
        remaining_ms = runner.ledger.remaining_ms(elapsed_ms=runner.elapsed_ms())
        if not _unit_fits_in_window(remaining_ms, worst_unit_ms, prior_unit_ms):
            # CAL-P038 (#1597): STOP BEFORE the window runs out, not after. The
            # two cases are recorded apart because they mean different things —
            # ``deadline`` is the window genuinely gone, ``unit_too_large`` is
            # time left that provably cannot hold a unit. An absent stage reads
            # as "fine" (gotcha #53), and this is the branch that decides whether
            # the beat ends honest or ends RED.
            stop_reason = "deadline" if remaining_ms <= 0 else "unit_too_large"
            runner.ledger.record_stage(f"staged:window_stop:{stop_reason}", 0)
            runner.ledger.record_gauge("staged:window_left_ms", max(0, remaining_ms))
            logger.info(
                "calibration staged futures: out of window (%s) with %d/%d units "
                "banked — %d ms left, worst unit %d ms",
                stop_reason, done, len(chunks), max(0, remaining_ms), int(worst_unit_ms),
            )
            break
        unit_started = time.monotonic()
        # Re-armed every unit: ``SET LOCAL`` dies with the transaction that the
        # previous unit's commit ended, so without this the next unit would run
        # with no statement timeout and no session identity (Queue 300B).
        #
        # CAL-P081 (#2052): the UNIT bound, not the phase bound. Handed this
        # beat's own worst observation when it has one, falling back inside the
        # ledger to the carried mean. Strictly tighter than the phase bound in
        # every case, so it can only stop a unit outliving its measured cost —
        # never let one outlive the beat.
        await runner.apply_unit_statement_timeout(
            db, PHASE_FUTURES, unit_ms=worst_unit_ms or prior_unit_ms or None
        )
        # Three PARALLEL arrays, one entry per market, unnest-ed back into the
        # (market_id, vm_id, is_grouped) roster the chunk statement joins to.
        market_ids = list(chunk.market_ids)
        try:
            with runner.stage("read:futures_unit"):
                result = await db.execute(
                    chunk_sql,
                    {
                        VM_ROSTER_MARKET_IDS_PARAM: market_ids,
                        VM_ROSTER_VM_IDS_PARAM: [assignment[m][0] for m in market_ids],
                        VM_ROSTER_IS_GROUPED_PARAM: [assignment[m][1] for m in market_ids],
                    },
                )
                unit_rows = result.all()
        except Exception as exc:  # noqa: BLE001 — re-raised unless it is OUR backstop
            if not is_statement_timeout(exc):
                raise
            # CAL-P081 (#2052): a unit cancelled at its OWN backstop is a known
            # outcome of this loop, not a fault of the build. Before this, the
            # cancellation propagated out of the phase and the beat terminated
            # ``thrown``/``DBAPIError`` = ``failed`` — a RED verdict on a beat
            # that had just banked five units durably, with
            # ``consecutive_failures`` climbing against a build that was working.
            # That is the false-RED twin of the false-GREEN ``task_verdict.py``
            # exists to prevent.
            #
            # SKIP THE UNIT, DO NOT END THE BEAT. Ending it is the intuitive
            # response and the more dangerous one: the loop skips units the
            # cursor already holds, so a unit that cancels reproducibly is the
            # FIRST one every later beat attempts, and a beat that stops there
            # banks nothing at all — worse than the failure being fixed. Skipping
            # banks the other units and leaves the blocker named.
            #
            # Nothing is lost by skipping: the cursor checkpointed before this
            # unit started, so the cancellation costs exactly this unit, and the
            # generation stays incomplete until some beat banks it.
            cancelled_this_beat += 1
            cancelled_after_ms = int((time.monotonic() - unit_started) * 1000.0)
            runner.ledger.record_stage("staged:units_cancelled", 1)
            runner.ledger.record_gauge("staged:unit_cancelled_after_ms", cancelled_after_ms)
            runner.ledger.record_gauge(f"staged:unit_cancelled:{chunk.key}", cancelled_after_ms)
            # The session is poisoned by the cancelled statement; roll it back so
            # the next unit's ``SET LOCAL`` runs on a clean transaction rather
            # than raising ``InFailedSQLTransaction`` on top of a failure we have
            # already classified (gotcha #6).
            with contextlib.suppress(Exception):
                await db.rollback()
            if cancelled_this_beat >= STAGED_UNIT_MAX_CANCELLATIONS:
                # The third one says the slowness belongs to the BEAT, not to a
                # unit, and continuing cannot help. Recorded under its own name:
                # "stopped because units keep cancelling" and "stopped because
                # the window ran out" are different diagnoses (gotcha #53).
                runner.ledger.record_stage("staged:window_stop:units_cancelling", 0)
                logger.warning(
                    "calibration staged futures: %d units cancelled at their own bound "
                    "(last %s after %d ms) with %d/%d banked — ending the beat partial, "
                    "not failed", cancelled_this_beat, chunk.key, cancelled_after_ms,
                    done, len(chunks),
                )
                break
            logger.warning(
                "calibration staged futures: unit %s cancelled at its own bound after "
                "%d ms with %d/%d units banked — skipping it, the beat continues",
                chunk.key, cancelled_after_ms, done, len(chunks),
            )
            continue
        # COMMIT, then advance. The other order records a cursor for work the
        # database may still roll back (``CHECKPOINT_BEFORE_COMMIT``).
        await runner.commit(db)
        cursor = advance(
            cursor, chunk.key, unit_rows, owner=runner.owner, lease_expires_at=staged_lease()
        )
        if not await save_staged_cursor(cursor, terminal=TERMINAL_PARTIAL):
            # The unit's read committed but its cursor did not persist. The work
            # is not banked, so stop rather than press on: continuing would let
            # this beat finish a generation whose earlier units the NEXT beat
            # cannot see, and re-doing one unit is cheap next to that.
            logger.warning("calibration staged futures: cursor write failed — stopping")
            return None
        done += 1
        ran_this_beat += 1
        unit_ms = (time.monotonic() - unit_started) * 1000.0
        unit_ms_this_beat += unit_ms
        # The WORST unit, not the mean: the mean is what the build costs, the
        # worst is what the next unit might cost, and it is the next unit the
        # window has to hold. A mean-based bound admits exactly the above-average
        # unit that then gets cancelled.
        worst_unit_ms = max(worst_unit_ms, unit_ms)

    _record_convergence_projection(
        runner,
        done=done,
        planned=len(chunks),
        ran_this_beat=ran_this_beat,
        unit_ms_this_beat=unit_ms_this_beat,
        worst_unit_ms=worst_unit_ms,
    )

    # -- Stage 3: finalize globally, or not at all ----------------------------
    if not is_complete(cursor, chunks):
        logger.info(
            "calibration staged futures: generation %s incomplete (%d/%d units) — "
            "banked, publishing nothing", gen_digest, done, len(chunks),
        )
        return None

    # CAL-P020: the one rung that belongs to no chunk. Counted here rather than
    # per unit, ONCE, against the unscoped ``market_info`` — and only now that
    # every unit is banked, so an incomplete beat never pays for it.
    global_census: list[dict] = []
    if COVERAGE_CENSUS_ENABLED:
        await runner.apply_statement_timeout(db, PHASE_FUTURES)
        with runner.stage("read:coverage_global_rung"):
            global_row = (await db.execute(text(_coverage_global_rung_sql()))).one()
        await runner.commit(db)
        # Same accessor the unit rows use below: a driver Row exposes
        # ``_mapping``, a plain object does not. ``.one()`` rather than
        # ``.first()`` on purpose — this is an ungrouped aggregate, so exactly
        # one row is guaranteed, and a missing one must abort the build loudly.
        # Skipping it quietly would publish the rung as the sum of the chunks'
        # zeros, i.e. a confident 0 for a rung nobody counted (gotcha #53).
        global_census.append(
            dict(global_row._mapping)
            if hasattr(global_row, "_mapping")
            else dict(vars(global_row))
        )

    with runner.stage("staged:finalize"):
        banked = collect_unit_results(cursor, chunks)
        # A null-keyed row is an empty chunk's census carrier, not a bucket (see
        # the LEFT JOIN note in the statement builder). Route it to the census
        # so its candidate-side counts survive, and keep it out of the buckets.
        census_only: list[dict] = []
        bucket_rows: list[list] = []
        for unit in banked:
            keep = []
            for row in unit:
                mapping = dict(row._mapping) if hasattr(row, "_mapping") else dict(vars(row))
                if mapping.get("bucket_idx") is None:
                    census_only.append(mapping)
                else:
                    keep.append(row)
            bucket_rows.append(keep)
        merged = merge_futures_rows(
            bucket_rows,
            census_columns=census_columns,
            extra_censuses=census_only + global_census,
        )
    logger.info(
        "calibration staged futures: generation %s COMPLETE — %d units, %d merged buckets",
        gen_digest, len(chunks), len(merged),
    )
    return merged


def _coverage_census_or_disabled(**kwargs):
    """The census, or an honest ``unavailable`` one while the switch is off.

    Disabled is a THIRD state, distinct from both "measured zero" and "the build
    broke": the counts were never asked for, on purpose, and the reason says so.
    """
    if not COVERAGE_CENSUS_ENABLED:
        from app.utils.calibration_coverage_bridge import unavailable_census

        return unavailable_census(
            COVERAGE_CENSUS_DISABLED_REASON,
            population_version=kwargs.get("population_version"),
            generation=kwargs.get("generation"),
        )
    return _build_coverage_census(**kwargs)


def _coverage_bridge_join() -> str:
    """The CROSS JOIN onto the 1-row census, or nothing when it is disabled."""
    if not COVERAGE_CENSUS_ENABLED:
        return ""
    return "\n            CROSS JOIN coverage_bridge_summary cbs"


def _coverage_bridge_select_columns() -> str:
    """``MAX(...)`` passthrough columns for the 1-row census, CROSS JOINed in.

    Same shape as ``liq_summary`` / ``published_summary``: constant across every
    returned bucket row, so the served ``buckets`` list is unchanged.
    """
    if not COVERAGE_CENSUS_ENABLED:
        return ""

    names = [_coverage_bridge_column(key) for key in _COVERAGE_RUNG_KEYS] + [
        "cb_coverage_total",
        "cb_with_terminal_cal_price",
    ]
    return "".join(f",\n                MAX(cbs.{name}) AS {name}" for name in names)


def _ece_from_buckets(buckets: dict[int, dict]) -> float | None:
    """Equal-weight-per-bucket |actual − predicted|, in percentage points.

    The same definition ``_compute_horizon_mce(weighted=False)`` uses, expressed
    over a ``{bucket_idx: {n, winners, sum_prob}}`` accumulator so the bundle
    census can score a cohort without rebuilding bucket dicts. Returns None for
    an empty cohort rather than a misleading 0.0.
    """
    live = [v for v in buckets.values() if v["n"] > 0]
    if not live:
        return None
    total = 0.0
    for v in live:
        total += abs(v["winners"] / v["n"] - v["sum_prob"] / v["n"])
    return round(total / len(live) * 100, 2)


def _build_nonexclusive_bundle_census(futures_rows) -> dict:
    """Per-category n/ECE for the non-exclusive bundle cohort (Queue 299 rung 4b).

    ``futures_rows`` are the main futures buckets, grouped by
    ``(bucket_idx, source, category, price_moved, is_nonexclusive_bundle)``.
    Splits each category's PUBLISHED rows into the bundle cohort (>=3 outcomes
    resolving with >=2 winners — structurally not a partition) and the
    remainder, and scores both.

    This is the evidence Item 2 asks for before the exclusion is generalized:
    ``would_exclude_*`` is exactly what a category-independent exclusion would
    remove, ``remainder_*`` is what the category's curve would become. Esports is
    reported too, but its cohort is already excluded from the curve, so its
    in-curve numbers are 0 by construction. Measurement only — no row moves.
    """
    per_cat: dict[str, dict[str, dict[int, dict]]] = {}
    for r in futures_rows:
        cat = r.category
        cohort = "bundle" if getattr(r, "is_nonexclusive_bundle", False) else "remainder"
        slot = per_cat.setdefault(cat, {"bundle": {}, "remainder": {}})[cohort]
        acc = slot.setdefault(r.bucket_idx, {"n": 0, "winners": 0, "sum_prob": 0.0})
        acc["n"] += r.n
        acc["winners"] += r.winners
        acc["sum_prob"] += float(r.sum_prob)

    by_category = []
    for cat in sorted(per_cat):
        bundle, remainder = per_cat[cat]["bundle"], per_cat[cat]["remainder"]
        bundle_n = sum(v["n"] for v in bundle.values())
        remainder_n = sum(v["n"] for v in remainder.values())
        if bundle_n == 0:
            continue
        by_category.append({
            "category": cat,
            "published_n": bundle_n + remainder_n,
            "would_exclude_n": bundle_n,
            "would_exclude_ece": _ece_from_buckets(bundle),
            "remainder_n": remainder_n,
            "remainder_ece": _ece_from_buckets(remainder),
            # The publish bar the remainder would have to clear to stay charted.
            "remainder_clears_sample_bar": remainder_n >= _DEFAULT_MIN_CATEGORY_OUTCOMES,
        })
    by_category.sort(key=lambda x: -x["would_exclude_n"])
    return {
        "rule": NONEXCLUSIVE_BUNDLE_CENSUS_RULE_TEXT,
        "excluded_from_curve_for": [ESPORTS_MULTI_BUNDLE_CATEGORY],
        "measured_only_for": "all other categories",
        "by_category": by_category,
    }


async def compute_calibration_payload(db, *, runner=None) -> dict:
    """The single canonical /api/calibration payload computation (Queue #257 Item 1).

    ONE eligible population + ONE normalization divisor, shared by BOTH serve
    paths so a cold-cache fallback can never diverge from the precomputed serve:
      * the scheduled ``precompute_calibration_main`` task (writes Redis), and
      * ``routes/calibration.public_calibration``'s in-request fallback.

    Previously each site carried its own copy of the CTE chain + Python
    post-processing and they had drifted in ~11 material ways — the route's
    cold-cache path was missing the liquidity / poly-placeholder / malformed-
    binary / golf-placeholder exclusions and the DataGolf-residual guard, used a
    looser resolution-source filter (kept ``pass2_loser`` / ``all_losers`` and
    NULL-source rows), and computed equal-weighted MCE where the task used
    n-weighted — so a cold serve showed a materially different curve. This
    function is that ONE population, imported by both.

    ``db`` is a live session supplied by the caller (task session or request
    session); all reads run on it and the response dict is returned WITHOUT
    writing Redis (the caching wrapper does that). Read-side only — never mutates
    is_winner / calibration_probability (gotcha #21).

    Queue 300M (#1479/#1513) — ``runner``. Optional; when absent (the route's
    in-request cold-cache fallback) this function behaves EXACTLY as it did
    before: one transaction, eleven reads, no timing, no resume. When the
    scheduled build passes a :class:`~app.tasks.calibration_main_build.PhaseRunner`
    the same eleven reads are grouped into three measured, separately-committed
    phases — ``futures`` (the population CTE), ``sports`` (the three events
    reads) and ``diagnostics`` (the seven transparency reads) — each of which
    can be carried forward by the next beat if this one runs out of window.
    The population filters, grouping, metrics and thresholds are untouched;
    what changes is only WHEN each read's transaction ends and whether its
    result has to be recomputed from scratch after an interruption.
    """
    from sqlalchemy import func, select

    from app.models import FuturesMarket
    from app.tasks.calibration_main_build import NULL_RUNNER, StagedFuturesIncomplete
    from app.tasks.redis_state import get_redis_client
    from app.utils.calibration_phase_ledger import (
        PHASE_AGGREGATE,
        PHASE_DIAGNOSTICS,
        PHASE_FUTURES,
        PHASE_SPORTS,
    )

    # D21 (#1978, CAL-P150). Captured BEFORE the NULL_RUNNER substitution below,
    # because after it `runner` can no longer answer the question. This is the
    # only place in the body that can tell the two callers apart, and one of the
    # reads downstream must: the scheduled build may REFUSE to publish a
    # candidate missing its per-bookmaker curve, and the route's in-request
    # cold-cache fallback must not — refusing there is a 500 on the public
    # endpoint, on the path that exists precisely because Redis is unreachable.
    is_producer_build = runner is not None

    runner = runner or NULL_RUNNER

    # nullcontext preserves the historical block structure (the queries below
    # keep their original indentation) while running on the caller-provided
    # session instead of opening its own — so both serve paths share one body.
    with contextlib.nullcontext():
        # -----------------------------------------------------------
        # PHASE 1 (futures) — Query 1: Main futures calibration buckets
        # -----------------------------------------------------------

        rows = runner.reuse(PHASE_FUTURES, "rows")
        if rows is None:
            runner.begin(PHASE_FUTURES)
            await runner.apply_statement_timeout(db, PHASE_FUTURES)
            if runner.staged_futures:
                # Queue 300D Item 0. The monolith cannot bank partial credit: it
                # is one statement, so a beat that dies at minute 22 of a 23
                # minute window loses 100% of its work and the next beat starts
                # from zero. That is why /calibration served a day-old curve
                # while the task "ran" every hour. The staged path commits whole
                # virtual questions as it goes, so an interrupted beat keeps
                # what it proved and the next one finishes the remainder.
                rows = await _run_staged_futures(db, runner, _main_futures_sql)
                if rows is None:
                    # The generation is banked but not finished. Deliberately
                    # NOT ``runner.complete()``: the phase did not complete, so
                    # it stays out of ``completed_required``, the run's terminal
                    # is ``partial``, health is not GREEN and the publish gate
                    # never sees a payload. The old complete last-good keeps
                    # serving and the next beat resumes from the cursor.
                    raise StagedFuturesIncomplete(
                        "futures generation incomplete — units banked, nothing published"
                    )
            else:
                with runner.stage("read:futures_population"):
                    result = await db.execute(text(_main_futures_sql()))
                    rows = result.all()
            await runner.commit(db)
            runner.record(PHASE_FUTURES, "rows", rows, kind="rows")
            runner.complete(PHASE_FUTURES)

        # #940 phase-1 transparency: included/excluded counts are constant across
        # every returned row (CROSS JOIN to the 1-row liq_summary).
        kalshi_included = (
            int(rows[0].kalshi_included)
            if rows and rows[0].kalshi_included is not None
            else 0
        )
        kalshi_excluded = (
            int(rows[0].kalshi_excluded)
            if rows and rows[0].kalshi_excluded is not None
            else 0
        )
        # L2-76: Polymarket no-bid placeholder exclusion transparency counts.
        poly_placeholder_excluded = (
            int(rows[0].poly_placeholder_excluded)
            if rows and rows[0].poly_placeholder_excluded is not None
            else 0
        )
        poly_included = (
            int(rows[0].poly_included)
            if rows and rows[0].poly_included is not None
            else 0
        )
        # Queue #220/221 Item 3: exclusion-symmetry census counts.
        poly_never_traded_total = (
            int(rows[0].poly_never_traded_total)
            if rows and rows[0].poly_never_traded_total is not None
            else 0
        )
        poly_never_traded_in_curve = (
            int(rows[0].poly_never_traded_in_curve)
            if rows and rows[0].poly_never_traded_in_curve is not None
            else 0
        )
        # L2-79 Item 1: malformed-binary exclusion transparency counts.
        both_false_excluded = (
            int(rows[0].both_false_excluded)
            if rows and rows[0].both_false_excluded is not None
            else 0
        )
        both_winner_excluded = (
            int(rows[0].both_winner_excluded)
            if rows and rows[0].both_winner_excluded is not None
            else 0
        )
        # L2-79 Item 2: golf one-sided-ask placeholder exclusion count.
        golf_placeholder_excluded = (
            int(rows[0].golf_placeholder_excluded)
            if rows and rows[0].golf_placeholder_excluded is not None
            else 0
        )
        # Queue #157: multi-candidate normalization transparency count.
        mex_normalized_outcomes = (
            int(rows[0].mex_normalized_outcomes)
            if rows and rows[0].mex_normalized_outcomes is not None
            else 0
        )

        # Queue #257 Item 1: field-completeness candidate/published split. A
        # candidate is a mex/field market that hit the normalization gate; it is
        # PUBLISHED (normalized) only if complete, else excluded as a partial
        # field. Reported separately so the population change is truthful.
        def _int0(attr):
            return (
                int(getattr(rows[0], attr))
                if rows and getattr(rows[0], attr, None) is not None
                else 0
            )

        # Queue 299 (#1012): result-authority + shape rung counts.
        no_winner_excluded = _int0("no_winner_excluded")
        no_winner_markets_count = _int0("no_winner_markets")
        draw_authority_excluded = _int0("draw_authority_excluded")
        draw_authority_markets_count = _int0("draw_authority_markets")
        orphan_partition_excluded = _int0("orphan_partition_excluded")
        orphan_partition_markets_count = _int0("orphan_partition_markets")
        nonexclusive_bundle_candidates = _int0("nonexclusive_bundle_candidates")
        nonexclusive_bundle_markets_count = _int0("nonexclusive_bundle_markets")

        mex_candidate_markets = _int0("mex_candidate_markets")
        mex_normalized_markets = _int0("mex_normalized_markets")
        field_incomplete_markets = _int0("field_incomplete_markets")
        field_incomplete_outcomes = _int0("field_incomplete_outcomes")
        # Queue #259 Item 1 (C14 P2): PUBLISHED (post-dedup) normalized markets —
        # the ones that actually reach the curve, vs the candidate/normalized
        # counts above which are computed pre-dedup over ``normalized``. With the
        # invariant fix these equal mex_normalized_markets (a complete field
        # publishes intact); a divergence means a post-normalization filter is
        # silently dropping members again.
        mex_published_markets = _int0("mex_published_markets")
        mex_published_outcomes = _int0("mex_published_outcomes")
        published_outcomes = _int0("published_outcomes")
        published_questions = _int0("published_questions")

        # Queue 300C: the coverage-bridge rungs. Deliberately NOT ``_int0`` —
        # a missing column must read UNKNOWN, never zero. It can genuinely be
        # missing: ``rows`` may be carried forward from a checkpoint written by
        # a beat that ran before this census shipped (the population version is
        # unchanged, by design, so that checkpoint stays valid for the curve).
        # Zero there would claim "no outcomes were excluded for this reason",
        # which is the one lie this census exists to prevent.
        def _int_or_none(attr):
            if not rows:
                return None
            value = getattr(rows[0], attr, None)
            return int(value) if value is not None else None

        coverage_rung_counts = {
            key: _int_or_none(_coverage_bridge_column(key))
            for key in _COVERAGE_RUNG_KEYS
        }
        coverage_total_measured = _int_or_none("cb_coverage_total")
        coverage_with_terminal_price = _int_or_none("cb_with_terminal_cal_price")

        # Queue #159 (#1010): esports match-bundle exclusion transparency count.
        esports_bundle_excluded = (
            int(rows[0].esports_bundle_excluded)
            if rows and rows[0].esports_bundle_excluded is not None
            else 0
        )
        # CAL-P168 (#1978) RANK 1: K''s total, read the same way.
        player_props_placeholder_excluded = (
            int(rows[0].player_props_placeholder_excluded)
            if rows and rows[0].player_props_placeholder_excluded is not None
            else 0
        )
        # `player_props_placeholder_markets` is deliberately NOT read here any
        # more. It was the value published as `temporary_excluded_markets`, and
        # CERT-647 is the finding that the union is not the temporary cohort —
        # so the payload now carries the temporary market count below and the
        # union market count has no honest consumer in this bullet. The COLUMN
        # stays emitted and declared: it is banked census like its neighbours,
        # and dropping it would change the declared census set and invalidate
        # every banked unit for a cosmetic saving.
        #
        # CERT-647 (CAL-P170): the temporary subset, read the same way. Defaults
        # to 0 — and 0 is the SAFE default here in the direction that matters:
        # a missing count renders NO temporary promise rather than promising a
        # return for rows nobody counted.
        player_props_placeholder_temporary_excluded = (
            int(rows[0].player_props_placeholder_temporary_excluded)
            if rows and rows[0].player_props_placeholder_temporary_excluded is not None
            else 0
        )
        player_props_placeholder_temporary_markets = (
            int(rows[0].player_props_placeholder_temporary_markets)
            if rows and rows[0].player_props_placeholder_temporary_markets is not None
            else 0
        )
        # CAL-P162 (#1978): the per-cell split behind the same total. Alex's
        # rank-2 ruling makes the per-cell map a clause of the exclusion, so it
        # is read from the aggregate rather than reconstructed — and it is built
        # from `nonexclusive_bundle_cell_labels()`, the same function that
        # generated the columns, so a new ruled tuple adds a column AND a key
        # together or neither.
        nonexclusive_bundle_by_cell: dict[str, int] = {}
        if rows:
            for label, column in nonexclusive_bundle_cell_labels():
                value = getattr(rows[0], column, None)
                nonexclusive_bundle_by_cell[label] = int(value) if value is not None else 0
        # Queue #167 (#941/#1054): Kalshi player-prop threshold exclusion count.
        kalshi_prop_threshold_excluded = (
            int(rows[0].kalshi_prop_threshold_excluded)
            if rows and rows[0].kalshi_prop_threshold_excluded is not None
            else 0
        )
        # Queue #183 Item 4 (#182 twin): weather wide-spread exclusion count.
        weather_wide_spread_excluded = (
            int(rows[0].weather_wide_spread_excluded)
            if rows and rows[0].weather_wide_spread_excluded is not None
            else 0
        )
        # Queue 300D Item 1: the representative tie delta. ``_int_or_none``, not
        # ``_int0`` — like the coverage rungs, this column is genuinely absent
        # from a checkpoint written by a beat that predates it, and reporting
        # zero there would claim "no question's representative was tie-broken"
        # when the honest answer is that nobody looked.
        representative_tie_broken = _int_or_none("representative_tie_broken")

        # -----------------------------------------------------------
        # PHASE 2 (sports) — Queries 2-4: ground-truth events calibration.
        # Grouped as one phase because all three read the same table under the
        # same eligibility shape; splitting them further would buy nothing and
        # cost three extra checkpoint writes.
        # -----------------------------------------------------------
        _sports_carried = runner.is_carried(PHASE_SPORTS)
        if not _sports_carried:
            runner.begin(PHASE_SPORTS)

        # Query 2: Ground-truth sports calibration from events table
        events_sql = text("""
            SELECT
                LEAST(FLOOR(prob * 10)::int, 9) AS bucket_idx,
                'odds_api' AS source,
                s.key AS category,
                COUNT(*) AS n,
                SUM(CASE WHEN won THEN 1 ELSE 0 END) AS winners,
                AVG(prob) AS avg_prob,
                SUM(prob::float) AS sum_prob,
                SUM((prob::float - CASE WHEN won THEN 1.0 ELSE 0.0 END)^2) AS sum_sq_err
            FROM (
                SELECT COALESCE(closing_home_probability, opening_home_probability) AS prob,
                       (home_score > away_score) AS won, sport_id
                FROM events
                WHERE status IN ('completed', 'closed')
                  AND COALESCE(closing_home_probability, opening_home_probability) IS NOT NULL
                  AND COALESCE(closing_home_probability, opening_home_probability) > 0
                  AND COALESCE(closing_home_probability, opening_home_probability) < 1
                  AND home_score IS NOT NULL AND away_score IS NOT NULL
                  AND home_score != away_score
                UNION ALL
                SELECT COALESCE(closing_away_probability, opening_away_probability) AS prob,
                       (away_score > home_score) AS won, sport_id
                FROM events
                WHERE status IN ('completed', 'closed')
                  AND COALESCE(closing_away_probability, opening_away_probability) IS NOT NULL
                  AND COALESCE(closing_away_probability, opening_away_probability) > 0
                  AND COALESCE(closing_away_probability, opening_away_probability) < 1
                  AND home_score IS NOT NULL AND away_score IS NOT NULL
                  AND home_score != away_score
            ) outcomes
            JOIN sports s ON s.id = outcomes.sport_id
            -- Queue #158 (#1011): soccer game-odds were captured 2-way (draw
            -- dropped at ingest — no draw column) so every soccer moneyline row
            -- sums to ~1.0 and over-predicts home/away by 7-18pp. Excluded from
            -- the published curve, league-scoped by the soccer_* key. Read-side
            -- only (gotcha #21); forward fix = 3-way capture (#1011).
            WHERE s.key NOT LIKE 'soccer_%'
            GROUP BY bucket_idx, s.key
            ORDER BY bucket_idx, s.key
        """)
        events_rows = runner.reuse(PHASE_SPORTS, "events_rows")
        if events_rows is None:
            await runner.apply_statement_timeout(db, PHASE_SPORTS)
            with runner.stage("read:events"):
                events_result = await db.execute(events_sql)
                events_rows = events_result.all()
            runner.record(PHASE_SPORTS, "events_rows", events_rows, kind="rows")

        # -----------------------------------------------------------
        # Query 3: Spread calibration
        # -----------------------------------------------------------
        spreads_sql = text("""
            SELECT
                LEAST(FLOOR(prob * 10)::int, 9) AS bucket_idx,
                'odds_api_spreads' AS source,
                s.key AS category,
                COUNT(*) AS n,
                SUM(CASE WHEN won THEN 1 ELSE 0 END) AS winners,
                AVG(prob) AS avg_prob,
                SUM(prob::float) AS sum_prob,
                SUM((prob::float - CASE WHEN won THEN 1.0 ELSE 0.0 END)^2) AS sum_sq_err
            FROM (
                SELECT
                    (CASE WHEN closing_home_spread_odds < 0
                          THEN ABS(closing_home_spread_odds)::numeric / (ABS(closing_home_spread_odds) + 100.0)
                          ELSE 100.0 / (closing_home_spread_odds + 100.0) END)
                    /
                    ((CASE WHEN closing_home_spread_odds < 0
                           THEN ABS(closing_home_spread_odds)::numeric / (ABS(closing_home_spread_odds) + 100.0)
                           ELSE 100.0 / (closing_home_spread_odds + 100.0) END)
                     +
                     (CASE WHEN closing_away_spread_odds < 0
                           THEN ABS(closing_away_spread_odds)::numeric / (ABS(closing_away_spread_odds) + 100.0)
                           ELSE 100.0 / (closing_away_spread_odds + 100.0) END))
                    AS prob,
                    ((home_score - away_score) + closing_home_spread > 0) AS won,
                    sport_id
                FROM events
                WHERE status IN ('completed', 'closed')
                  AND closing_home_spread IS NOT NULL
                  AND closing_home_spread_odds IS NOT NULL
                  AND closing_away_spread_odds IS NOT NULL
                  AND home_score IS NOT NULL AND away_score IS NOT NULL
                  AND (home_score - away_score) + closing_home_spread != 0
            ) outcomes
            JOIN sports s ON s.id = outcomes.sport_id
            WHERE prob > 0 AND prob < 1
            GROUP BY bucket_idx, s.key
            ORDER BY bucket_idx, s.key
        """)
        spreads_rows = runner.reuse(PHASE_SPORTS, "spreads_rows")
        if spreads_rows is None:
            with runner.stage("read:spreads"):
                spreads_result = await db.execute(spreads_sql)
                spreads_rows = spreads_result.all()
            runner.record(PHASE_SPORTS, "spreads_rows", spreads_rows, kind="rows")

        # -----------------------------------------------------------
        # Query 4: Totals calibration
        # -----------------------------------------------------------
        totals_sql = text("""
            SELECT
                LEAST(FLOOR(prob * 10)::int, 9) AS bucket_idx,
                'odds_api_totals' AS source,
                s.key AS category,
                COUNT(*) AS n,
                SUM(CASE WHEN won THEN 1 ELSE 0 END) AS winners,
                AVG(prob) AS avg_prob,
                SUM(prob::float) AS sum_prob,
                SUM((prob::float - CASE WHEN won THEN 1.0 ELSE 0.0 END)^2) AS sum_sq_err
            FROM (
                SELECT
                    (CASE WHEN closing_over_odds < 0
                          THEN ABS(closing_over_odds)::numeric / (ABS(closing_over_odds) + 100.0)
                          ELSE 100.0 / (closing_over_odds + 100.0) END)
                    /
                    ((CASE WHEN closing_over_odds < 0
                           THEN ABS(closing_over_odds)::numeric / (ABS(closing_over_odds) + 100.0)
                           ELSE 100.0 / (closing_over_odds + 100.0) END)
                     +
                     (CASE WHEN closing_under_odds < 0
                           THEN ABS(closing_under_odds)::numeric / (ABS(closing_under_odds) + 100.0)
                           ELSE 100.0 / (closing_under_odds + 100.0) END))
                    AS prob,
                    ((home_score + away_score) > closing_over_under) AS won,
                    sport_id
                FROM events
                WHERE status IN ('completed', 'closed')
                  AND closing_over_under IS NOT NULL
                  AND closing_over_odds IS NOT NULL
                  AND closing_under_odds IS NOT NULL
                  AND home_score IS NOT NULL AND away_score IS NOT NULL
                  AND (home_score + away_score) != closing_over_under
            ) outcomes
            JOIN sports s ON s.id = outcomes.sport_id
            WHERE prob > 0 AND prob < 1
            GROUP BY bucket_idx, s.key
            ORDER BY bucket_idx, s.key
        """)
        totals_rows = runner.reuse(PHASE_SPORTS, "totals_rows")
        if totals_rows is None:
            with runner.stage("read:totals"):
                totals_result = await db.execute(totals_sql)
                totals_rows = totals_result.all()
            runner.record(PHASE_SPORTS, "totals_rows", totals_rows, kind="rows")

        if not _sports_carried:
            await runner.commit(db)
            runner.complete(PHASE_SPORTS)

        # -----------------------------------------------------------
        # PHASE 3 (diagnostics) — Queries 5-11: the transparency reads. Every
        # one is a small aggregate, and none of them feeds the published
        # buckets, so they share one phase and one checkpoint.
        # -----------------------------------------------------------
        _diagnostics_carried = runner.is_carried(PHASE_DIAGNOSTICS)
        if not _diagnostics_carried:
            runner.begin(PHASE_DIAGNOSTICS)

        # -----------------------------------------------------------
        # Query 5: Per-bookmaker calibration from Redis
        # -----------------------------------------------------------
        # D21 (#1978, CAL-P150) — freeze exception GRANTED by Alex 2026-08-30.
        # These two lines used to be a `try: ... except Exception: pass` around
        # the read, and that is what a 23-hour silent publish outage looked like
        # from the inside. An absent, unreachable or unparseable key is now a
        # NAMED refusal; the reasoning, the measured chain and the argument for
        # why refusing loudly is not a worse outcome are all on
        # `read_bookmaker_curve_rows`.
        #
        # 🔴 These rows are NOT diagnostics, despite the phase heading above.
        # They are concatenated into `all_rows`, so they are part of the
        # PUBLISHED population — which is why their silent absence took ~96,026
        # outcomes out of the candidate rather than out of a transparency read.
        #
        # 🔴 `refuse` IS SCOPED TO THE PRODUCER, and the first cut of this fix
        # got that wrong. `runner` is the discriminator this function already
        # documents: present for the scheduled build, absent for
        # `routes/calibration.public_calibration`'s in-request cold-cache
        # fallback. Refusing on BOTH turned "Redis is unreachable" into a 500 on
        # the public endpoint — on the very path that exists because Redis is
        # unavailable. The producer is the only caller that can PUBLISH a short
        # candidate, so it is the only one for which short is a correctness
        # question; the serve path reports the degradation in the payload.
        (
            bookmaker_rows,
            bookmaker_soccer_excluded,
            bookmaker_curve_degraded,
        ) = read_bookmaker_curve_rows(
            get_redis_client(), refuse=is_producer_build
        )

        # -----------------------------------------------------------
        # Query 6: Total resolved markets count
        # -----------------------------------------------------------
        total_markets = runner.reuse(PHASE_DIAGNOSTICS, "total_markets")
        if total_markets is None:
            await runner.apply_statement_timeout(db, PHASE_DIAGNOSTICS)
            with runner.stage("read:total_markets"):
                total_markets_result = await db.execute(
                    select(func.count()).select_from(FuturesMarket).where(
                        FuturesMarket.status == "resolved"
                    )
                )
                total_markets = total_markets_result.scalar()
            runner.record(PHASE_DIAGNOSTICS, "total_markets", total_markets)

        # -----------------------------------------------------------
        # Query 7: Closing line coverage
        # -----------------------------------------------------------
        closing_sql = text("""
            SELECT
                COUNT(*) FILTER (WHERE closing_home_probability IS NOT NULL) AS has_closing,
                COUNT(*) FILTER (WHERE closing_home_probability IS NULL
                                 AND commence_time IS NOT NULL) AS needs_closing,
                COUNT(*) AS total_completed
            FROM events
            WHERE status IN ('completed', 'closed')
              AND home_score IS NOT NULL AND away_score IS NOT NULL
        """)
        closing_row = runner.reuse(PHASE_DIAGNOSTICS, "closing_row")
        if closing_row is None:
            with runner.stage("read:closing"):
                closing_result = await db.execute(closing_sql)
                closing_row = closing_result.one()
            runner.record(PHASE_DIAGNOSTICS, "closing_row", closing_row, kind="row")

        # -----------------------------------------------------------
        # Query 8: #762 void-filter transparency — how many eligible resolved
        # outcomes the void rule (did_not_play / withdrew) drops from the
        # published denominator. Mirrors the #940 liquidity_filter count so the
        # exclusion is surfaced, never silent. Same eligibility predicate as the
        # main query (resolved + opening_probability in (0,1)).
        # -----------------------------------------------------------
        void_sql = text("""
            SELECT COUNT(*) AS excluded
            FROM futures_outcomes fo
            JOIN futures_markets fm ON fm.id = fo.market_id
            WHERE fm.status = 'resolved'
              AND fo.resolution_source IN ('did_not_play', 'withdrew')
              AND fo.opening_probability IS NOT NULL
              AND fo.opening_probability > 0 AND fo.opening_probability < 1
        """)
        void_excluded = runner.reuse(PHASE_DIAGNOSTICS, "void_excluded")
        if void_excluded is None:
            with runner.stage("read:void"):
                void_result = await db.execute(void_sql)
                void_excluded = int(void_result.scalar() or 0)
            runner.record(PHASE_DIAGNOSTICS, "void_excluded", void_excluded)

        # -----------------------------------------------------------
        # Query 9: #754-curve heuristic-exclusion transparency — how many
        # eligible resolved outcomes the heuristic rule (pass2_loser /
        # all_losers, alongside the long-standing pass2_guess) drops from the
        # published curve. Lane-2 L2-30 measured poly pass2_loser = 41,069
        # outcomes @ 0.0% winrate (23,240 priced 0.5-0.9 — statistically
        # impossible if correct); leaving them in dragged poly MCE to ~10.84pp.
        # Read-side exclusion only — markets stay resolved, never re-graded
        # (gotcha #21). 97% lack a polymarket_event_id so Gamma/CLOB re-resolution
        # is infeasible by construction; exclusion is the correct durable fix.
        # Surfaced here so the exclusion is transparent, never silent.
        heur_sql = text("""
            SELECT fm.source, COUNT(*) AS excluded
            FROM futures_outcomes fo
            JOIN futures_markets fm ON fm.id = fo.market_id
            WHERE fm.status = 'resolved'
              AND fo.resolution_source IN ('pass2_loser', 'all_losers')
              AND fo.opening_probability IS NOT NULL
              AND fo.opening_probability > 0 AND fo.opening_probability < 1
            GROUP BY fm.source
        """)
        heuristic_excluded = runner.reuse(PHASE_DIAGNOSTICS, "heuristic_excluded")
        if heuristic_excluded is None:
            with runner.stage("read:heuristic_excluded"):
                heur_result = await db.execute(heur_sql)
                heuristic_excluded = {r.source: int(r.excluded) for r in heur_result.all()}
            runner.record(PHASE_DIAGNOSTICS, "heuristic_excluded", heuristic_excluded)

        # -----------------------------------------------------------
        # Query 10: Queue #158 (#1011) soccer 2-way exclusion transparency —
        # how many events-table soccer moneyline outcomes the draw-omission rule
        # drops from the published curve. Mirrors the events_sql population
        # (same eligibility, both home + away outcomes) so the count is honest,
        # never silent — the same contract as the #762 void_filter count.
        # -----------------------------------------------------------
        soccer_2way_sql = text("""
            SELECT COUNT(*) AS excluded
            FROM (
                SELECT sport_id
                FROM events
                WHERE status IN ('completed', 'closed')
                  AND COALESCE(closing_home_probability, opening_home_probability) IS NOT NULL
                  AND COALESCE(closing_home_probability, opening_home_probability) > 0
                  AND COALESCE(closing_home_probability, opening_home_probability) < 1
                  AND home_score IS NOT NULL AND away_score IS NOT NULL
                  AND home_score != away_score
                UNION ALL
                SELECT sport_id
                FROM events
                WHERE status IN ('completed', 'closed')
                  AND COALESCE(closing_away_probability, opening_away_probability) IS NOT NULL
                  AND COALESCE(closing_away_probability, opening_away_probability) > 0
                  AND COALESCE(closing_away_probability, opening_away_probability) < 1
                  AND home_score IS NOT NULL AND away_score IS NOT NULL
                  AND home_score != away_score
            ) outcomes
            JOIN sports s ON s.id = outcomes.sport_id
            WHERE s.key LIKE 'soccer_%'
        """)
        soccer_2way_excluded = runner.reuse(PHASE_DIAGNOSTICS, "soccer_2way_excluded")
        if soccer_2way_excluded is None:
            with runner.stage("read:soccer_2way"):
                soccer_2way_result = await db.execute(soccer_2way_sql)
                soccer_2way_excluded = int(soccer_2way_result.scalar() or 0)
            runner.record(PHASE_DIAGNOSTICS, "soccer_2way_excluded", soccer_2way_excluded)

        # -----------------------------------------------------------
        # Query 11: Queue #261 Item 3 — truth-evidence census. Over the SAME
        # resolved + opening-in-(0,1) eligibility shape the population scans,
        # classify every futures outcome by calibration-truth class so the
        # population change (Item 1) is visible, never silent: how many rows are
        # eligible (independent authority grades the forecast), how many are
        # price-derived (now excluded — the leakage containment), and — the hard
        # contract violation — how many carry an UNKNOWN source (must be 0).
        # No source-bias interpretation; just the counts + the two RED invariants.
        # -----------------------------------------------------------
        truth_sql = text(f"""
            SELECT
                CASE
                    WHEN fo.resolution_source IS NULL THEN 'missing'
                    WHEN fo.resolution_source IN {CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL} THEN 'eligible'
                    WHEN fo.resolution_source IN {PRICE_DERIVED_SOURCES_SQL} THEN 'price_derived'
                    WHEN fo.resolution_source IN {CALIBRATION_TRUTH_INELIGIBLE_SOURCES_SQL} THEN 'ineligible_other'
                    ELSE 'unknown'
                END AS truth_class,
                COUNT(*) AS outcomes,
                COUNT(DISTINCT fo.market_id) AS markets
            FROM futures_outcomes fo
            JOIN futures_markets fm ON fm.id = fo.market_id
            WHERE fm.status = 'resolved'
              AND fo.opening_probability IS NOT NULL
              AND fo.opening_probability > 0 AND fo.opening_probability < 1
              -- Queue #267 (C44 #1): the truth census measures the resolution-source
              -- contract over the documented "resolved + opening-in-(0,1)" shape;
              -- the crude volume gate was never part of that shape (liquidity is a
              -- per-source, evidence-based, downstream decision) and dropping it
              -- keeps the census a faithful pre-liquidity classification.
            GROUP BY 1
        """)
        truth_by_class = runner.reuse(PHASE_DIAGNOSTICS, "truth_by_class")
        if truth_by_class is None:
            # D22: SOFT. This census is a pure diagnostic by its own comment
            # above ("no source-bias interpretation; just the counts") and the
            # publish gate reads none of it, yet it is an unbounded scan over
            # every resolved futures row sitting in a required phase AHEAD of
            # the publish. When the futures rebuild has a heavy beat it is
            # squeezed under the ~104 s it needs and the whole publish dies.
            # It now degrades to UNOBSERVED instead, and says so in the payload.
            async with runner.soft_stage(db, "read:truth_census") as soft:
                truth_result = await db.execute(truth_sql)
                truth_by_class = {
                    r.truth_class: {"outcomes": int(r.outcomes), "markets": int(r.markets)}
                    for r in truth_result.all()
                }
            if soft.failed:
                # Left as None on purpose: ``_build_truth_evidence`` reports
                # None as UNOBSERVED, and an empty dict would report a clean
                # contract on no evidence. Not recorded either, so the phase's
                # carried key set no longer matches and the NEXT beat re-reads
                # it rather than inheriting a hole.
                truth_by_class = None
            else:
                runner.record(PHASE_DIAGNOSTICS, "truth_by_class", truth_by_class)

        # -----------------------------------------------------------
        # Query 12: L2-78 Item 0 (flagged since L2-73) — the true resolved-data
        # span for the calibration hero. Cheap MIN/MAX over resolved futures
        # resolution_date (the Kalshi/Polymarket bulk of the curve), but BOUNDED
        # to a sane window so data-quality artifacts can't define the hero: a
        # resolved market must have resolved in the past (resolution_date <=
        # NOW() — a future date on a 'resolved' row is a bad date) and within the
        # last 5 years (these sources are all recent; a 2011 date is a parse
        # artifact, seen live). Without the bound the raw MIN/MAX read
        # Jul-2011–Jul-2029. None-safe; the hero falls back to generated_at.
        #
        # Queue 300M moved this read UP from the post-processing block into the
        # diagnostics phase. It had been the one read outside every measured
        # boundary — the twelfth of what the queue called eleven — so it was
        # neither timed, bounded by a phase statement timeout, nor resumable.
        # Nothing about the query changed; only where it is accounted for.
        date_range = runner.reuse(PHASE_DIAGNOSTICS, "date_range")
        if date_range is None:
            # D22: this was a bare ``try``, and it cannot survive the failure
            # it was written for. A statement timeout aborts the whole
            # transaction, so the ``except`` caught the error and the phase's own
            # commit raised anyway — the beat died with the handler right there.
            # Same intent, now with the savepoint that makes it true. The
            # ``if`` stays INSIDE: on a degraded read ``dr`` is never bound.
            async with runner.soft_stage(db, "read:date_range"):
                dr = (
                    await db.execute(
                        text(
                            "SELECT MIN(resolution_date) AS lo, MAX(resolution_date) AS hi "
                            "FROM futures_markets "
                            "WHERE status = 'resolved' AND resolution_date IS NOT NULL "
                            "AND resolution_date <= NOW() "
                            "AND resolution_date >= NOW() - INTERVAL '5 years'"
                        )
                    )
                ).one()
                if dr.lo and dr.hi:
                    date_range = {"start": dr.lo.isoformat(), "end": dr.hi.isoformat()}
            runner.record(PHASE_DIAGNOSTICS, "date_range", date_range)

        if not _diagnostics_carried:
            await runner.commit(db)
            runner.complete(PHASE_DIAGNOSTICS)

    # -----------------------------------------------------------
    # PHASE 4 (aggregate) — post-processing, outside the DB session. Row
    # materialization, bucket assembly, Wilson CIs and the bootstrap MCE. Never
    # resumable (it consumes every read above), but very much measurable: until
    # Queue 300M it was the one stretch of the build no budget could see.
    # -----------------------------------------------------------
    runner.begin(PHASE_AGGREGATE)
    all_rows = list(rows) + list(events_rows) + list(spreads_rows) + list(totals_rows) + list(bookmaker_rows)
    total_outcomes = sum(r.n for r in all_rows)
    total_winners = sum(r.winners for r in all_rows)

    # Queue 300C: the OBSERVATION side of the bridge. ``total_outcomes`` is the
    # published-curve unit (curve observations, ~653K); the futures outcomes are
    # only part of it, and the sportsbook curves — Odds API moneyline, spreads,
    # totals and the per-bookmaker moneyline — supply the rest. Counted directly
    # from the same rows the curve is built from, not derived by subtraction, so
    # a miscount surfaces as a residual instead of reconciling by construction.
    sportsbook_curve_legs = sum(
        r.n
        for r in list(events_rows)
        + list(spreads_rows)
        + list(totals_rows)
        + list(bookmaker_rows)
    )
    # CAL-P012: the reachability total, read (never computed) here. Wrapped
    # because a supporting census must not be able to break the payload it
    # supports — see the fail-open note on the kwarg below.
    try:
        from app.tasks.census_reachability import read_published_counts
        from app.tasks.redis_state import get_redis_client

        _reachability_counts = read_published_counts(get_redis_client())
    except Exception:
        _reachability_counts = None

    coverage_census = _coverage_census_or_disabled(
        rung_counts=coverage_rung_counts,
        sportsbook_curve_legs=sportsbook_curve_legs,
        published_curve_observations=total_outcomes,
        # The hinge, counted independently by the population chain itself.
        published_outcomes_crosscheck=published_outcomes,
        population_version=CALIBRATION_POPULATION_VERSION,
        generation=getattr(runner, "generation", None),
        with_terminal_calibration_price=coverage_with_terminal_price,
        # CAL-P011 contracted the reachability tier; CAL-P012 counts it. The
        # count is NOT computed here on purpose: its population is outside the
        # coverage CTE chain, and #1479 already has this task exceeding its
        # hourly window under backfill contention, so a heavy join here is
        # exactly how a census makes the curve it reports on late. Instead the
        # bounded census (``app/tasks/census_reachability``) publishes a total
        # and this reads it — an O(1) Redis GET on the critical path.
        #
        # Fail-open at every step: no cache, unreadable cache, malformed cache
        # or a partial walk all yield None, which routes to the explicit
        # ``unavailable`` section. A supporting census must never be able to
        # break the payload it supports, and a partial number presented as a
        # total is worse than no number.
        reachability_tier_counts=_reachability_counts,
        reachability_unavailable_reason=(
            None
            if _reachability_counts
            else (
                "no complete reachability census published yet — run "
                "POST /api/admin/repairs/reachability-census to walk it, or "
                "publish_full_census() to cache a total"
            )
        ),
    )
    # The measured universe total and the summed partition are two reads of the
    # same CTE, so they must agree exactly; if they ever do not, the CASE stopped
    # being a partition and the census must say so rather than publish a number.
    _measured_coverage = (coverage_census.get("units") or {}).get(
        "outcomes_with_calibration_coverage"
    ) or {}
    if (
        coverage_total_measured is not None
        and _measured_coverage.get("value") is not None
        and coverage_total_measured != _measured_coverage["value"]
    ):
        coverage_census["status"] = "incomplete"
        coverage_census["invariants"]["ok"] = False
        coverage_census["invariants"]["violations"].append("COVERAGE_PARTITION_RESIDUAL")
        coverage_census["invariants"]["coverage_total_measured"] = coverage_total_measured

    # Queue 299 rung 4b: the futures query now groups by is_nonexclusive_bundle as
    # well, purely so the bundle cohort can be measured. Build the census from the
    # split rows FIRST, then merge them back on the original four keys so the
    # served ``buckets`` list is byte-for-byte the shape it was before — the
    # census must not cost payload size or change any published bucket.
    nonexclusive_bundle_census = _build_nonexclusive_bundle_census(rows)

    # Build bucket dicts with Wilson CIs
    merged: dict[tuple, dict] = {}
    merged_order: list[tuple] = []
    for r in all_rows:
        key = (r.bucket_idx, r.source, r.category, getattr(r, "price_moved", None))
        acc = merged.get(key)
        if acc is None:
            acc = {"n": 0, "winners": 0, "sum_prob": 0.0, "sum_sq_err": 0.0}
            merged[key] = acc
            merged_order.append(key)
        acc["n"] += r.n
        acc["winners"] += r.winners
        acc["sum_prob"] += float(r.sum_prob)
        acc["sum_sq_err"] += float(r.sum_sq_err)

    bucket_dicts = []
    for key in merged_order:
        acc = merged[key]
        bucket_idx, source, category, price_moved = key
        ci_lo, ci_hi = _wilson_ci(acc["winners"], acc["n"])
        bucket_dicts.append({
            "bucket_idx": bucket_idx, "source": source, "category": category,
            "price_moved": price_moved,
            "n": acc["n"], "winners": acc["winners"],
            # avg_prob is recomputed from the merged mass (sum_prob / n) rather
            # than averaged across split rows, so it stays exact.
            "avg_prob": round(acc["sum_prob"] / acc["n"], 4) if acc["n"] else 0.0,
            "sum_prob": round(acc["sum_prob"], 4),
            "sum_sq_err": round(acc["sum_sq_err"], 4),
            "ci_lower": round(ci_lo, 4),
            "ci_upper": round(ci_hi, 4),
        })

    # Aggregate buckets for MCE bootstrap CI
    agg: dict[int, dict] = {}
    for b in bucket_dicts:
        idx = b["bucket_idx"]
        if idx not in agg:
            agg[idx] = {"n": 0, "winners": 0, "sum_prob": 0.0}
        agg[idx]["n"] += b["n"]
        agg[idx]["winners"] += b["winners"]
        agg[idx]["sum_prob"] += b["sum_prob"]
    agg_list = [
        {"n": v["n"], "winners": v["winners"], "avg_prob": v["sum_prob"] / v["n"]}
        for v in agg.values()
        if v["n"] > 0
    ]
    mce_ci_lo, mce_ci_hi = _bootstrap_mce_ci(agg_list)

    # Cohort-level MCE: closing line vs opening price
    def _cohort_mce(buckets: list[dict], pred: object) -> float | None:
        cohort_agg: dict[int, dict] = {}
        for b in buckets:
            if b.get("price_moved") != pred:
                continue
            idx = b["bucket_idx"]
            if idx not in cohort_agg:
                cohort_agg[idx] = {"n": 0, "winners": 0, "sum_prob": 0.0}
            cohort_agg[idx]["n"] += b["n"]
            cohort_agg[idx]["winners"] += b["winners"]
            cohort_agg[idx]["sum_prob"] += b["sum_prob"]
        if not cohort_agg:
            return None
        total_abs_err = 0.0
        for v in cohort_agg.values():
            if v["n"] == 0:
                continue
            avg_prob = v["sum_prob"] / v["n"]
            actual = v["winners"] / v["n"]
            total_abs_err += abs(actual - avg_prob)
        return round(total_abs_err / len(cohort_agg) * 100, 2)

    mce_closing_line = _cohort_mce(bucket_dicts, True)
    mce_opening_price = _cohort_mce(bucket_dicts, False)

    # Per-category MCE breakdown
    cat_agg: dict[str, dict[int, dict]] = {}
    cat_outcomes: dict[str, int] = {}
    for b in bucket_dicts:
        cat = b["category"]
        idx = b["bucket_idx"]
        if cat not in cat_agg:
            cat_agg[cat] = {}
            cat_outcomes[cat] = 0
        if idx not in cat_agg[cat]:
            cat_agg[cat][idx] = {"n": 0, "winners": 0, "sum_prob": 0.0}
        cat_agg[cat][idx]["n"] += b["n"]
        cat_agg[cat][idx]["winners"] += b["winners"]
        cat_agg[cat][idx]["sum_prob"] += b["sum_prob"]
        cat_outcomes[cat] += b["n"]

    # #997: minimum-sample gate — a sub-category chart below this many resolved
    # outcomes is noise. Enforced here (server-side) so web + native inherit it.
    _min_cat_outcomes = _get_min_category_outcomes(get_redis_client())

    by_category = []
    small_sample_categories = []
    for cat, buckets_by_idx in sorted(cat_agg.items()):
        total_n = cat_outcomes[cat]
        if total_n == 0:
            continue
        if total_n < _min_cat_outcomes:
            # Below the bar: excluded from the published chart list, but
            # recorded (with its count) so the exclusion is transparent, never
            # silent. It still counts toward the overall/per-source curves.
            #
            # Queue 299 Item 3 (#1012): the disposition is now machine-readable.
            # A cohort whose defective rows have been excluded can legitimately
            # fall under the sample bar — the honest answer then is "parked",
            # not a quietly missing chart and not a rescued-looking curve. This
            # is the exact case r339 predicted for cricket.
            small_sample_categories.append({
                "category": cat,
                "outcomes": total_n,
                "disposition": "parked_below_publish_bar",
                "publish_bar": _min_cat_outcomes,
                "ece": _compute_horizon_mce([
                    {"n": v["n"], "winners": v["winners"], "sum_prob": v["sum_prob"]}
                    for v in buckets_by_idx.values()
                ]),
            })
            continue
        _cat_buckets = [
            {"n": v["n"], "winners": v["winners"], "sum_prob": v["sum_prob"]}
            for v in buckets_by_idx.values()
        ]
        cat_mce = _compute_horizon_mce(_cat_buckets)
        cat_mce_unweighted = _compute_horizon_mce(_cat_buckets, weighted=False)
        by_category.append({
            "category": cat,
            "mce": cat_mce,
            "mce_unweighted": cat_mce_unweighted,
            "outcomes": total_n,
            # L2-73 payload v2 (#999 §F): explicit display semantics so web +
            # native render the same story. ece = n-weighted (headline);
            # mce (worst-bucket) = the equal-weighted number, for the secondary col.
            "ece": cat_mce,
            "mce_worst": cat_mce_unweighted,
            "n": total_n,
            "gated": False,  # published entries are already above the sample floor
        })
    by_category.sort(key=lambda x: x["outcomes"], reverse=True)
    small_sample_categories.sort(key=lambda x: x["outcomes"], reverse=True)

    # Per-source MCE breakdown
    src_agg: dict[str, dict[int, dict]] = {}
    src_outcomes: dict[str, int] = {}
    for b in bucket_dicts:
        src = b["source"]
        idx = b["bucket_idx"]
        if src not in src_agg:
            src_agg[src] = {}
            src_outcomes[src] = 0
        if idx not in src_agg[src]:
            src_agg[src][idx] = {"n": 0, "winners": 0, "sum_prob": 0.0}
        src_agg[src][idx]["n"] += b["n"]
        src_agg[src][idx]["winners"] += b["winners"]
        src_agg[src][idx]["sum_prob"] += b["sum_prob"]
        src_outcomes[src] += b["n"]

    by_source = []
    for src, buckets_by_idx in sorted(src_agg.items()):
        total_n = src_outcomes[src]
        if total_n == 0:
            continue
        _src_buckets = [
            {"n": v["n"], "winners": v["winners"], "sum_prob": v["sum_prob"]}
            for v in buckets_by_idx.values()
        ]
        src_mce = _compute_horizon_mce(_src_buckets)
        src_mce_unweighted = _compute_horizon_mce(_src_buckets, weighted=False)
        by_source.append({
            "source": src,
            "mce": src_mce,
            "mce_unweighted": src_mce_unweighted,
            "outcomes": total_n,
            # L2-73 payload v2 (#999 §F): explicit ECE (n-weighted headline) +
            # worst-bucket MCE + n for native/web parity.
            "ece": src_mce,
            "mce_worst": src_mce_unweighted,
            "n": total_n,
            "gated": False,
        })
    by_source.sort(key=lambda x: x["outcomes"], reverse=True)

    # Spread / Total summaries
    def _source_summary(source_key: str) -> dict:
        sport_agg: dict[str, dict[int, dict]] = {}
        sport_outcomes: dict[str, int] = {}
        total_n = 0
        total_w = 0
        for b in bucket_dicts:
            if b["source"] != source_key:
                continue
            sport = b["category"]
            idx = b["bucket_idx"]
            if sport not in sport_agg:
                sport_agg[sport] = {}
                sport_outcomes[sport] = 0
            if idx not in sport_agg[sport]:
                sport_agg[sport][idx] = {"n": 0, "winners": 0, "sum_prob": 0.0}
            sport_agg[sport][idx]["n"] += b["n"]
            sport_agg[sport][idx]["winners"] += b["winners"]
            sport_agg[sport][idx]["sum_prob"] += b["sum_prob"]
            sport_outcomes[sport] += b["n"]
            total_n += b["n"]
            total_w += b["winners"]

        by_sport = []
        for sport, buckets_by_idx in sorted(sport_agg.items()):
            sn = sport_outcomes[sport]
            if sn == 0:
                continue
            # #997: same minimum-sample gate as by_category — a per-sport
            # spread/total chart below the bar is thin-sample noise.
            if sn < _min_cat_outcomes:
                continue
            sport_mce = _compute_horizon_mce([
                {"n": v["n"], "winners": v["winners"], "sum_prob": v["sum_prob"]}
                for v in buckets_by_idx.values()
            ])
            by_sport.append({"sport": sport, "mce": sport_mce, "outcomes": sn})
        by_sport.sort(key=lambda x: x["outcomes"], reverse=True)

        all_agg: dict[int, dict] = {}
        for b in bucket_dicts:
            if b["source"] != source_key:
                continue
            idx = b["bucket_idx"]
            if idx not in all_agg:
                all_agg[idx] = {"n": 0, "winners": 0, "sum_prob": 0.0}
            all_agg[idx]["n"] += b["n"]
            all_agg[idx]["winners"] += b["winners"]
            all_agg[idx]["sum_prob"] += b["sum_prob"]
        overall_mce = _compute_horizon_mce([
            {"n": v["n"], "winners": v["winners"], "sum_prob": v["sum_prob"]}
            for v in all_agg.values()
        ])

        return {
            "mce": overall_mce,
            "outcomes": total_n,
            "winners": total_w,
            "by_sport": by_sport,
        }

    spreads_summary = _source_summary("odds_api_spreads")
    totals_summary = _source_summary("odds_api_totals")

    # ``date_range`` is read in the diagnostics phase above (Queue 300M) so it
    # sits inside a measured, bounded, resumable boundary like every other read.

    response = {
        "closing_line_coverage": {
            "has_closing": closing_row.has_closing,
            "needs_closing": closing_row.needs_closing,
            "total": closing_row.total_completed,
        },
        "buckets": bucket_dicts,
        "by_category": by_category,
        "by_source": by_source,
        "date_range": date_range,  # L2-78 Item 0: resolved-data span for the hero
        "corrections": CALIBRATION_CORRECTIONS,  # L2-73 §E trust panel
        # #997 App Store ship-gate: the minimum resolved-outcome count for a
        # chartable sub-category. Shipped so web + native gate on the SAME bar
        # instead of hardcoding their own; by_category / by_sport above are
        # already filtered to it. small_sample_categories lists what was gated
        # out (with counts) so the exclusion is transparent.
        "min_category_outcomes": _min_cat_outcomes,
        "small_sample_categories": small_sample_categories,
        "spreads_summary": spreads_summary,
        "totals_summary": totals_summary,
        "total_markets": total_markets,
        "total_outcomes": total_outcomes,
        "total_winners": total_winners,
        # C111 P2 / Queue 297 Item 3: the PUBLIC artifact must name its own
        # population contract. The version constant already guarded the horizon /
        # examples / bucket-debug consumers, but not the payload the page itself
        # renders — so an older last-good could be served under current UI labels
        # and no consumer could tell. It is also what makes an intended population
        # change expressible: the publish gate waives a drift/collapse rejection
        # only when this value is explicitly bumped.
        "population_version": CALIBRATION_POPULATION_VERSION,
        # #1955: the version says what an operator DECLARED; this says what the
        # code DID. The publish gate compares these two strings to tell a
        # methodology change from sixteen days of resolutions, which a count
        # cannot do and a recount cannot afford.
        "population_predicate_fingerprint": population_predicate_fingerprint(),
        "mce_ci_lower": round(mce_ci_lo * 100, 2),
        "mce_ci_upper": round(mce_ci_hi * 100, 2),
        "mce_closing_line": mce_closing_line,
        "mce_opening_price": mce_opening_price,
        "liquidity_filter": {
            "applies_to": "kalshi",
            "rule": KALSHI_LIQUIDITY_RULE_TEXT,
            "kalshi_included": kalshi_included,
            "kalshi_excluded": kalshi_excluded,
        },
        "poly_placeholder_filter": {  # L2-76 (#151/#997)
            "applies_to": "polymarket",
            "rule": POLY_PLACEHOLDER_RULE_TEXT,
            "included": poly_included,
            "excluded": poly_placeholder_excluded,
        },
        "exclusion_symmetry": {  # Queue #220/221 Item 3
            "note": (
                "The never-traded liquidity filter is asymmetric across sources. "
                "Kalshi excludes every never-traded outcome (all price bands); "
                "Polymarket only excludes never-traded outcomes in the near-0.50 "
                "placeholder band. poly_never_traded_in_curve is the cohort that "
                "never traded but sits outside that band, so it is STILL counted "
                "in the curve — the residual asymmetry. Measurement only; closing "
                "it (excluding all poly never-traded) is a separate Alex-gated "
                "decision (gotcha #21 keeps this read-side)."
            ),
            "per_source": SOURCE_LIQUIDITY_EXCLUSIONS,
            "poly_never_traded_total": poly_never_traded_total,
            "poly_never_traded_in_curve": poly_never_traded_in_curve,
            "poly_never_traded_excluded_by_band": max(
                poly_never_traded_total - poly_never_traded_in_curve, 0
            ),
        },
        "malformed_binary_filter": {  # L2-79 Item 1 (#997/#1010)
            "applies_to": "all",
            "rule": MALFORMED_BINARY_RULE_TEXT,
            "both_false_excluded": both_false_excluded,
            "both_winner_excluded": both_winner_excluded,
            "excluded": both_false_excluded + both_winner_excluded,
        },
        "golf_placeholder_filter": {  # L2-79 Item 2 (#940/#762)
            "applies_to": "golf",
            "rule": GOLF_PLACEHOLDER_RULE_TEXT,
            "excluded": golf_placeholder_excluded,
        },
        "mex_normalization": {  # Queue #157 (#1012) + Queue #257 Item 1
            "applies_to": "all",
            "rule": MEX_NORMALIZE_RULE_TEXT,
            "threshold": MEX_NORMALIZE_THRESHOLD,
            "normalized_outcomes": mex_normalized_outcomes,
            # Queue #257 Item 1: the field-completeness invariant. candidate =
            # markets that hit the normalization gate; published = those complete
            # enough to normalize (each sums ~1.0 over its survivors); the rest
            # are partial fields excluded from the curve with a repair reason,
            # never normalized over survivors.
            "field_completeness": {
                "rule": FIELD_COMPLETENESS_RULE_TEXT,
                "candidate_markets": mex_candidate_markets,
                # Queue #257 pre-dedup normalized-candidate count (over ``normalized``).
                "published_normalized_markets": mex_normalized_markets,
                # Queue #259 Item 1 (C14 P2): the counts computed over ``deduped`` —
                # markets/outcomes that actually reach the published curve. Equal to
                # the normalized-candidate count above once the sum-to-1 invariant
                # holds (a complete field publishes every member); reported so the
                # candidate -> published split is never silent.
                "published_normalized_markets_post_dedup": mex_published_markets,
                "published_normalized_outcomes_post_dedup": mex_published_outcomes,
                "field_incomplete_excluded_markets": field_incomplete_markets,
                "field_incomplete_excluded_outcomes": field_incomplete_outcomes,
            },
        },
        "esports_multi_bundle_filter": {  # Queue #159 (#1010)
            # D12 (#1978, CAL-P150): `applies_to` was the literal "esports" and
            # is now derived, because the filter stopped being esports-only the
            # moment the first (source, category) tuple was ruled onto it. The
            # KEY keeps its name — it is a public contract on /api/calibration —
            # so this list is the only place a reader can see that a second cell
            # is being deleted here. Hard-coding it would have restated the
            # constant and could not have drifted from the constant it restated.
            "applies_to": ", ".join(
                [ESPORTS_MULTI_BUNDLE_CATEGORY]
                + [f"{src}/{cat}" for src, cat in NONEXCLUSIVE_BUNDLE_EXCLUDED_CELLS]
            ),
            "excluded_cells": [
                list(pair) for pair in NONEXCLUSIVE_BUNDLE_EXCLUDED_CELLS
            ],
            "rule": ESPORTS_MULTI_BUNDLE_RULE_TEXT,
            "excluded": esports_bundle_excluded,
        },
        # CAL-P162 (#1978) — the disclosure half of Alex's rank-2 ruling
        # (2026-08-28, option (b) APPROVED WITH DISCLOSURE). A NEW key, so the
        # live `esports_multi_bundle_filter` contract does not change shape or
        # meaning under existing consumers; the frontend half has been built and
        # green since CAL-P114 and has rendered nothing until now because it is
        # gated on `excluded > 0`.
        #
        # CAL-P168 (#1978) — RANK 1 LANDS, and `temporary_by_cell` is no longer
        # empty. It shipped as `{}` from CAL-P162 until now because the only
        # temporary cell was `polymarket/baseball`, which was ruled but unbuilt;
        # the page is gated on this map being non-empty, so THIS is the payload
        # that first renders "part of this is temporary by design" to a reader.
        #
        # 🔴 `excluded` IS THE SUM OF TWO DIFFERENT RULES and has to be, because
        # the page prints one total followed by the per-cell map and a reader
        # must be able to add the cells up and get the total. `rule` therefore
        # describes BOTH predicates — a single rule sentence over a two-rule
        # total would be the one lie this bullet cannot afford. What keeps them
        # honest is that no row can be counted twice: the cells are disjoint by
        # construction (RULE E's allowlist and K''s share no tuple), and
        # `test_player_props_placeholder_kprime.py` asserts that disjointness
        # rather than trusting it.
        "nonexclusive_bundle_filter": {
            "applies_to": ", ".join(
                label for label, _ in nonexclusive_bundle_cell_labels()
            ),
            # `join`, not `A + " " + B`, and the reason is worth a line: the
            # fingerprint-coverage detector classifies any name appearing beside
            # a string constant in a `+` expression as SQL-INTERPOLATED, so the
            # concatenated form silently moved `NONEXCLUSIVE_BUNDLE_FILTER_RULE_TEXT`
            # into `uncovered_sql_shaping` — a rule sentence counted as a value
            # that shapes the population. That is CERT-502's finding exactly
            # ("a tripwire you widen the definition of is not a tripwire"), so
            # the prose is joined rather than the pin raised on a miscount.
            "rule": " ".join(
                (
                    NONEXCLUSIVE_BUNDLE_FILTER_RULE_TEXT,
                    PLAYER_PROPS_PLACEHOLDER_RULE_TEXT,
                )
            ),
            "excluded": esports_bundle_excluded + player_props_placeholder_excluded,
            "excluded_by_cell": nonexclusive_bundle_by_cell,
            # 🔴 CERT-647 (CAL-P170) — THIS MAP IS NO LONGER A CONSTANT.
            #
            # It shipped as `dict(...)` of a module constant, so the sentence
            # "part of this is temporary" was rendered whenever the cell was
            # excluded AT ALL — including after the writer repair, when the only
            # rows left would be the historical R1/R2 residue that never returns.
            # The disclosure's own clause 3 promises the sentence "leaves the
            # page without a copy change when the backend stops emitting the
            # cell", and a constant can never stop emitting. The falsifier in
            # clause 4 was therefore unfalsifiable by construction.
            #
            # Gated on the TEMPORARY count, which is what the sentence is about.
            # When the writer is fixed and M1/R3 fall to zero the map empties,
            # the sentence disappears, and the historical remainder stays
            # excluded and stays disclosed by the per-cell count above — which
            # is exactly the behaviour clause 4 says to look for.
            "temporary_by_cell": (
                dict(PLAYER_PROPS_PLACEHOLDER_TEMPORARY_BY_CELL)
                if player_props_placeholder_temporary_excluded > 0
                else {}
            ),
            # Rank 1's own numbers, so the temporary half of the bullet is
            # checkable on its own rather than only as part of a sum.
            #
            # 🔴 `temporary_excluded` counts the M1/R3 cohort ONLY. It shipped
            # as the full R1+R2+R3+M1 union, which made the field's NAME false:
            # it said "this many rows are coming back" over a population whose
            # majority is historical residue that is not. The two halves below
            # sum to the per-cell total, so a reader can still add the bullet up.
            "temporary_excluded": player_props_placeholder_temporary_excluded,
            "temporary_excluded_markets": player_props_placeholder_temporary_markets,
            # The complement, published rather than left to subtraction: the
            # rows excluded for good unless separately repaired or re-ruled.
            "historical_excluded": (
                player_props_placeholder_excluded
                - player_props_placeholder_temporary_excluded
            ),
        },
        # Queue 299 rung 1 (#1012): result authority before anything else.
        "no_winner_filter": {
            "applies_to": "all",
            "rule": NO_WINNER_RULE_TEXT,
            "excluded": no_winner_excluded,
            "excluded_markets": no_winner_markets_count,
        },
        # Queue 299 rung 2 (#1012): draw authority on draw-capable questions.
        "draw_authority_filter": {
            "applies_to": ", ".join(sorted(DRAW_CAPABLE_CATEGORIES)),
            "rule": DRAW_AUTHORITY_RULE_TEXT,
            "excluded": draw_authority_excluded,
            "excluded_markets": draw_authority_markets_count,
            "draw_member_names": sorted(DRAW_AUTHORITY_OUTCOME_NAMES),
        },
        # Queue 299 rung 3 (#1012): orphan partitions.
        "orphan_partition_filter": {
            "applies_to": "all (field shape only)",
            "rule": ORPHAN_PARTITION_RULE_TEXT,
            "excluded": orphan_partition_excluded,
            "excluded_markets": orphan_partition_markets_count,
        },
        # Queue 299 rung 4 (#1012): what now counts as proof of exclusivity.
        "exclusivity_evidence": {
            "applies_to": "all",
            "rule": EXCLUSIVITY_EVIDENCE_RULE_TEXT,
            "required_market_type": "field",
            "required_relations": sorted(EXCLUSIVITY_PROVED_RELATIONS),
            "mutually_exclusive_column_accepted": False,
            "category_consulted_for_shape": False,
        },
        # Queue 299 rung 4b (#1012): measured, not excluded — see the rule text.
        "nonexclusive_bundle_census": {
            **nonexclusive_bundle_census,
            "candidate_outcomes": nonexclusive_bundle_candidates,
            "candidate_markets": nonexclusive_bundle_markets_count,
        },
        "kalshi_prop_threshold_filter": {  # Queue #186 (#941, corrects #167)
            "applies_to": "kalshi",
            "rule": KALSHI_PROP_THRESHOLD_RULE_TEXT,
            "excluded": kalshi_prop_threshold_excluded,
        },
        "weather_wide_spread_filter": {  # Queue #183 Item 4 (#182 twin)
            "applies_to": "kalshi (weather only)",
            "rule": WEATHER_WIDE_SPREAD_RULE_TEXT,
            "excluded": weather_wide_spread_excluded,
        },
        # Queue 300D Item 1: NOT a filter and deliberately not filed with them —
        # nothing here is excluded. This is the one-time representative IDENTITY
        # delta from adopting a deterministic tie authority, reported on its own
        # so it can never be read as a population change. ``questions`` is null
        # when the census predates the instrument (unknown), never 0.
        "representative_tie_authority": {
            "authority": REPRESENTATIVE_TIE_AUTHORITY,
            "rule": (
                "Representative side is the outcome closest to 50%; exact ties "
                "break by immutable canonical outcome ID. No Yes/No or "
                "favourite/underdog preference."
            ),
            "questions": representative_tie_broken,
            "changes_population_count": False,
        },
        "void_filter": {
            "applies_to": "datagolf",
            "rule": VOID_FILTER_RULE_TEXT,
            "excluded": void_excluded,
        },
        "soccer_2way_filter": {  # Queue #158 (#1011)
            "applies_to": "odds_api, odds_api_bookmaker",
            "rule": SOCCER_2WAY_RULE_TEXT,
            "excluded": soccer_2way_excluded + bookmaker_soccer_excluded,
            "events_excluded": soccer_2way_excluded,
            "bookmaker_excluded": bookmaker_soccer_excluded,
            # D21 (#1978, CAL-P150). None on a normal read; one of the two
            # reason codes when the per-bookmaker curve could not be assembled
            # and this response was served anyway. Only the serve path can ever
            # set it — the producer refuses instead — and it is here rather than
            # nowhere because a payload that is short ~96K outcomes and does not
            # say so is the original defect with a different caller. A zero that
            # cannot be told from an absence is a response shape, not an answer
            # (gotcha #53).
            "bookmaker_curve_degraded": bookmaker_curve_degraded,
        },
        "heuristic_filter": {
            "applies_to": "polymarket",
            "rule": (
                "Outcomes resolved by legacy heuristic passes (pass2_guess, "
                "pass2_loser, all_losers) are excluded from the published curve: "
                "they were guessed, not authoritatively settled (Lane-2 #754 "
                "measured pass2_loser at 0.0% winrate even at 0.5-0.9 prices), and "
                "97% lack a polymarket_event_id so authoritative re-resolution is "
                "infeasible. Read-side exclusion only; markets stay resolved, "
                "never re-graded (gotcha #21)."
            ),
            "excluded_by_source": heuristic_excluded,
        },
        "truth_evidence": _build_truth_evidence(
            truth_by_class,
            mex_normalized_markets=mex_normalized_markets,
            mex_published_markets=mex_published_markets,
            published_outcomes=published_outcomes,
            published_questions=published_questions,
        ),
        # Queue 300C (Alex 2026-08-02): the supporting census. ADDITIVE — nothing
        # above this line changed, the plotted population is untouched, and the
        # population version is unchanged. ``total_outcomes`` remains THE headline
        # unit (published curve observations); the far larger coverage number
        # lives in here, labelled as coverage, with the rung-by-rung account of
        # why the two differ.
        "calibration_coverage_census": coverage_census,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    runner.complete(PHASE_AGGREGATE)
    return response


def _build_truth_evidence(
    truth_by_class: dict | None,
    *,
    mex_normalized_markets: int,
    mex_published_markets: int,
    published_outcomes: int,
    published_questions: int,
) -> dict:
    """Queue #261 Item 3: the calibration-truth regression-visibility artifact.

    Reports the truth-evidence census (outcomes/markets by class over the
    resolved eligibility shape), the price-derived rows now excluded (the
    leakage containment), any unknown-source rows, and the two contract
    invariants. ``contract_ok`` goes RED ONLY on a real contract violation —
    an unknown resolution_source in the resolved population, or the Queue #259
    candidate==published partition breaking — never on a source-mix ratio.
    """
    # D22: ``None`` means the census did not run this beat (its statement was
    # cancelled and the beat published anyway). That is NOT the same as a census
    # that ran and found nothing: with an empty dict every ``.get`` default is
    # zero and ``contract_ok`` would come back True on no evidence at all. The
    # distinction is carried all the way into the payload.
    observed = truth_by_class is not None
    truth_by_class = truth_by_class or {}
    unknown = truth_by_class.get("unknown", {"outcomes": 0, "markets": 0})
    price_derived = truth_by_class.get("price_derived", {"outcomes": 0, "markets": 0})
    partition_ok = mex_normalized_markets == mex_published_markets
    violations = []
    if unknown["outcomes"] > 0:
        violations.append(
            f"unknown resolution_source in {unknown['outcomes']} resolved outcomes "
            f"(fail-closed: excluded from the curve, but classify them in "
            f"resolution_authority)"
        )
    if not partition_ok:
        violations.append(
            f"Queue #259 partition invariant broken: normalized "
            f"{mex_normalized_markets} != published {mex_published_markets} markets "
            f"(a post-normalization filter is dropping field members)"
        )
    return {
        "rule": (
            "A source may grade a published forecast only if its winner is "
            "established INDEPENDENTLY of the market's own price (venue/API "
            "settlement or deterministic public-data). Price-derived truth "
            "(clean_resolution / settlement_sync) is excluded — Queue #261."
        ),
        "by_class": truth_by_class,
        "price_derived_excluded": price_derived,
        "unknown_sources": unknown,
        "published_outcomes": published_outcomes,
        "published_questions": published_questions,
        "partition_invariant": {
            "normalized_markets": mex_normalized_markets,
            "published_markets": mex_published_markets,
            "ok": partition_ok,
        },
        # D22. THREE fields, and they move together — a reader that checks only
        # ``contract_ok`` must not be able to read an unobserved beat as a clean
        # one, so it is ``None`` (not True, not False) when the census did not
        # run: there is no violation, and there is also no evidence.
        #
        # A VIOLATION OUTRANKS UNOBSERVED, and the order of these branches is
        # the whole reason to write them out. ``partition_invariant`` is derived
        # from the aggregate, not from the census, so it still answers on a
        # degraded beat — and a beat that FOUND a broken partition must report
        # RED even though the other half of the artifact is missing. Ranking
        # unobserved first would have hidden it.
        "census_observed": observed,
        "contract_status": (
            "violated" if violations
            else "ok" if observed
            else "unobserved"
        ),
        "contract_ok": (
            False if violations
            else True if observed
            else None
        ),
        "contract_violations": violations,
    }


def _read_published_baseline(rc) -> Any:
    """The artifact a candidate must be judged against, or ``None``.

    Prefers the fresh ``main`` key and falls back to the durable ``last_good``.
    The fallback matters: on a 50MB ``allkeys-lru`` instance ``main`` (2h TTL) is
    evicted long before ``last_good`` (7d), and without it the gate would read
    "no prior artifact", call the build a first publish, and wave through exactly
    the collapsed population it exists to stop.

    Every failure here is non-fatal and degrades to ``None`` (publish allowed) —
    an unreadable cache is a cache problem, never a reason to stop publishing.
    """
    for key in (_MAIN_KEY, _MAIN_LAST_GOOD_KEY):
        try:
            raw = rc.get(key)
        except Exception as exc:  # noqa: BLE001 — baseline is best-effort
            logger.warning("calibration gate: baseline read of %s failed: %s", key, exc)
            continue
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except Exception:  # noqa: BLE001 — a corrupt prior value is not a baseline
            logger.warning("calibration gate: baseline at %s is not valid JSON", key)
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _file_publish_gate_rejection(verdict, *, marker: str = "calibration-publish-gate") -> dict:
    """File (or comment on) ONE deduped P2 issue carrying the rejection diff.

    Best-effort and fully contained: the rejection itself is already recorded by
    the raising caller, so a GitHub outage must never turn a preserved-last-good
    into an unhandled exception. Dedup is by the verdict's failure-class
    fingerprint, so an hourly beat reproducing the same bad shape comments once
    per run on one issue instead of filing a new issue every hour.
    """
    try:
        from app.tasks.sentinel_filing import reconcile_issue
        from app.utils.calibration_publish_gate import rejection_issue_body

        return reconcile_issue(
            red=True,
            fingerprint=verdict.fingerprint,
            marker_key=marker,
            labels=["type:bug", "area:calibration", "priority:p2", "needs-triage"],
            title=(
                "Calibration publish gate rejected a candidate build "
                f"({', '.join(verdict.codes)})"
            ),
            body=rejection_issue_body(verdict, fingerprint_marker=marker),
            title_prefix="Calibration publish gate",
            red_comment=(
                "The publish gate rejected another candidate with the same "
                f"failure class (`{', '.join(verdict.codes)}`). "
                f"{verdict.summary()} The last published snapshot is still being served."
            ),
        )
    except Exception as exc:  # noqa: BLE001 — alerting must never mask the rejection
        logger.warning("calibration gate: rejection filing failed: %s", exc)
        return {"action": "error", "error": str(exc)[:200]}


def _publish_calibration_main(rc, payload_json: str) -> dict:
    """Publish the serialized main payload to the durable + fresh keys (Queue 272).

    Writes the durable ``last_good`` key FIRST (the survivor) then the fresh
    ``main`` key. Both are bounded SETs (the sync client carries a 5s socket
    timeout — gotcha #39 — so a Redis stall terminates in seconds, never blocking
    the heavy worker to its hard limit) and both are SET-only (never DEL), so a
    failed write can never destroy a usable prior payload. Returns per-key stage
    results so the terminal task metric can distinguish a compute success from a
    publication failure (Item 1)."""
    stages: dict = {}
    for label, key, ttl in (
        ("last_good", _MAIN_LAST_GOOD_KEY, _MAIN_LAST_GOOD_TTL),
        ("main", _MAIN_KEY, _MAIN_CACHE_TTL),
    ):
        try:
            rc.set(key, payload_json, ex=ttl)
            stages[label] = "ok"
        except Exception as exc:  # noqa: BLE001 — captured, never destroys prior value
            stages[label] = "error"
            stages[f"{label}_error"] = str(exc)[:200]
            logger.warning("calibration publish: %s SET failed: %s", label, exc)
    return stages


def population_predicate_fingerprint() -> str:
    """WHICH ROWS QUALIFY, in one digest — stamped on every published artifact.

    #1955. The publish gate could not tell "we changed the methodology" (the
    hazard it exists for) from "the build took sixteen days" (unavoidable),
    because both present as a population delta and a count cannot say which one
    it is. The count is also the aggregate that times out, so recounting the
    baseline's own predicate at compare time — the obvious answer — is the one
    that cannot be afforded on the request path.

    So the artifact states its predicate instead, and the comparison becomes an
    equality of two strings the gate already has in hand. Same digest ⇒ the rule
    did not move ⇒ every row of difference is data movement (new resolutions,
    backfills, drains) and growth is admitted. Different or absent ⇒ the strict
    symmetric band, exactly as before.

    DELIBERATELY NARROWER THAN :func:`_main_input_fingerprint`, and the two must
    not be merged:

    * that one answers "may a carried phase output be resumed", so it hashes
      everything the OUTPUT depends on — including
      ``compute_calibration_payload`` (metrics, rendering, bucket shaping) and
      :data:`CALIBRATION_POPULATION_VERSION` itself. Using it here would make
      every ordinary edit to the payload builder, and every version bump, read
      as "the predicate changed" — re-arming the strict band on the builds that
      most need the relaxation, which is the defect this function exists to end;
    * this one answers "did the set of qualifying rows change", so it hashes only
      the two functions that DEFINE that set. It excludes the version string on
      purpose: the version is what an operator DECLARES, this is what the code
      DOES, and #1955 is precisely the gap between them.

    Hashing a function's source covers that function and never its callees (the
    lesson :func:`_main_input_fingerprint` keeps re-teaching). A new SQL-shaping
    input to the POPULATION belongs on this list explicitly — and a change here
    is a methodology change: it will refuse the next candidate until an operator
    bumps the version, which is the correct and intended consequence.
    """
    from app.utils.calibration_phase_ledger import input_fingerprint

    try:
        import inspect

        source = inspect.getsource(_calibration_population_ctes) + inspect.getsource(
            _virtual_market_ctes
        )
    except Exception:  # noqa: BLE001 — no source => never claim a match
        # A digest nothing can equal (``_same_predicate`` requires equality), so
        # an unreadable predicate falls back to the strict band instead of
        # silently excusing a drift it could not check.
        return f"unavailable:{time.time()}"
    return input_fingerprint("population-predicate/v1", source)


def _main_input_fingerprint() -> str:
    """Everything a carried phase output depends on, in one 32-char digest.

    The population version alone is not enough: it is bumped deliberately and
    rarely, while the eleven queries change under it all the time (four rungs
    landed under q267 in Queue 299 alone). So the fingerprint hashes the SOURCE
    of the compute function itself. Any edit to any query invalidates every
    carried read, which is the only safe default — a payload half-built by the
    old code and half by the new is worse than one that took an extra beat.

    Queue 300D Item 1 adds the two inputs that were NOT covered by hashing
    ``compute_calibration_payload`` alone, and both omissions were real holes:

    * ``_calibration_population_ctes`` — the CTE chain is built by a *different*
      function, so until now an edit to the population itself (the heaviest and
      most consequential SQL in the build) did not invalidate a carried read.
    * ``_main_futures_sql`` — Queue 300D hoisted the bucket SELECT out of
      ``compute_calibration_payload`` so both of its scopes could be parsed and
      tested. That move would otherwise have QUIETLY REMOVED the main futures
      statement from this digest, which is the sort of hole a refactor opens and
      nobody notices until a resumed beat publishes a half-old payload.
    * :data:`REPRESENTATIVE_TIE_AUTHORITY` — hashed explicitly rather than left
      implicit in the SQL text, so the authority is a named, greppable input to
      the fingerprint instead of an incidental substring of it.

    CAL-P024 adds :data:`COVERAGE_CENSUS_ENABLED`, and it is the same class of
    hole as the two above — found, this time, by flipping the switch and noticing
    the digest did not move. The switch is read inside
    ``_coverage_bridge_ctes`` / ``_coverage_bridge_join`` /
    ``_coverage_bridge_select_columns``, which ``_main_futures_sql`` CALLS but
    which are not themselves hashed; ``inspect.getsource`` returns a function's
    own text, not its callees'. So the census switch changed the emitted
    statement while leaving the fingerprint identical, and a cursor banked with
    the census ON was resumable by code with it OFF — units built from two
    different statements merged into one payload, which is exactly what this
    digest exists to make impossible.

    Hashed by VALUE and by name for the same reason
    :data:`REPRESENTATIVE_TIE_AUTHORITY` is: a greppable input beats an
    incidental substring. The general rule this keeps re-teaching — hashing a
    function's source covers that function, never what it calls — is why new
    SQL-shaping inputs belong on this list explicitly rather than being assumed
    covered.
    """
    from app.utils.calibration_phase_ledger import input_fingerprint

    try:
        import inspect

        source = (
            inspect.getsource(compute_calibration_payload)
            + inspect.getsource(_calibration_population_ctes)
            + inspect.getsource(_virtual_market_ctes)
            + inspect.getsource(_main_futures_sql)
        )
    except Exception:  # noqa: BLE001 — no source (frozen/optimized) => never carry
        source = f"unavailable:{time.time()}"
    return input_fingerprint(
        CALIBRATION_POPULATION_VERSION,
        REPRESENTATIVE_TIE_AUTHORITY,
        f"coverage_census={COVERAGE_CENSUS_ENABLED}",
        # D12 (#1978, CAL-P150) — the fourth instance of the hole this docstring
        # keeps describing, and it was found the way CAL-P024 found the census
        # switch: by asking what would happen if the value changed.
        # `NONEXCLUSIVE_BUNDLE_EXCLUDED_CELLS` is INTERPOLATED into the emitted
        # SQL, but `inspect.getsource(_calibration_population_ctes)` hashes the
        # f-string TEMPLATE, not the value substituted into it. So adding or
        # removing a ruled cell would have changed which rows the curve
        # publishes while leaving this digest identical — and a cursor banked
        # under one exclusion list would have stayed resumable by code with a
        # different one, merging units built from two populations into one
        # payload. That is precisely what this digest exists to make impossible.
        #
        # Hashed by NAME as well as value, like its two neighbours above, so it
        # is greppable rather than an incidental substring.
        f"nonexclusive_bundle_cells={sorted(NONEXCLUSIVE_BUNDLE_EXCLUDED_CELLS)}",
        # CAL-P162 (#1978) — the FIFTH instance of the same hole, found by the
        # same question the comment above prescribes. `MEX_NORMALIZE_THRESHOLD`
        # was already interpolated into the emitted SQL (so the template hash
        # cannot see its value), but until RULE E it only chose how a row was
        # PRICED. It now also decides whether a row is PUBLISHED at all: it is
        # the sum arm of the bundle exclusion. A change from 1.15 would silently
        # move the published population while leaving this digest identical.
        #
        # Added on the deploy that made it curve-shaping, deliberately: closing
        # this costs a full rebuild on any other day, and today the fingerprint
        # is moving anyway.
        f"mex_normalize_threshold={MEX_NORMALIZE_THRESHOLD}",
        # CAL-P168 (#1978) — the SIXTH instance, and the largest single batch of
        # it, closed on the deploy that creates it rather than left for the
        # tripwire to count. Every one of these is INTERPOLATED into the emitted
        # SQL by a helper that ``inspect.getsource`` cannot see through (it
        # returns a function's own text, never its callees'), and every one of
        # them decides WHICH ROWS THE CURVE PUBLISHES:
        #
        #   * the allowlist decides which cell K' acts on at all;
        #   * 0.5000 is R1's exact spike — widening it to a band is a separate
        #     ruling with its own census, and this digest is what would make
        #     such a widening visible instead of silent;
        #   * the tolerance is R2's coherence window (imported from the
        #     writer-side rule, so it can move without this file changing —
        #     which is exactly why hashing the template text is not enough);
        #   * the name pattern is R3's title match, the arm the design already
        #     records as its weakest link;
        #   * the band and drift floor are M1, and they are the numbers that
        #     separate a manufactured coin flip from ordinary line movement.
        #
        # Change any of them and a cursor banked under the old value would
        # otherwise stay resumable by code carrying the new one, merging units
        # built from two different populations into one published payload.
        f"player_props_cells={sorted(PLAYER_PROPS_PLACEHOLDER_EXCLUDED_CELLS)}",
        f"player_props_half_spike={PLAYER_PROPS_HALF_SPIKE_EXACT_VALUE}",
        f"player_props_pair_tolerance={PAIR_SUM_TOLERANCE}",
        f"player_props_name_pattern={PLAYER_PROPS_NAME_PATTERN}",
        f"player_props_band={PLAYER_PROPS_MIDPOINT_BAND_LO},{PLAYER_PROPS_MIDPOINT_BAND_HI}",
        f"player_props_forced_drift={PLAYER_PROPS_FORCED_DRIFT_MIN}",
        source,
    )


def staged_unit_fingerprint() -> str:
    """The BYTES the staged units actually ran, in one digest.

    CAL-P205 (#2052), layer 1 of
    ``artifacts/cal-p190/DESIGN-THE-REBUILD-SURVIVES-A-DEPLOY.md``.

    Not a proxy for the statement — the statement. ``inspect.getsource`` covers
    a function and never its callees, which is the hole
    :func:`_main_input_fingerprint`'s own docstring keeps re-teaching: SIX
    separate incidents have each been closed by bolting one more interpolated
    value onto that digest by hand, after the fact. A digest of the emitted text
    cannot have a seventh, because an interpolated value that changes the
    published rows necessarily changes the bytes.

    DELIBERATELY NOT MERGED with the other two digests, for the same reason
    :func:`population_predicate_fingerprint` gives for staying narrower: the
    three answer different questions.

    * :func:`_main_input_fingerprint` answers "may a carried PHASE OUTPUT be
      resumed", so it hashes the source of everything the output depends on,
      including ``compute_calibration_payload`` (metrics, rendering, bucket
      shaping). :func:`~app.utils.calibration_staged_futures.decode_main_checkpoint`
      keeps it. An edit to the renderer must still discard a carried phase.
    * THIS one answers "may a banked staged UNIT be resumed". A staged unit is
      rows produced by one statement. Nothing outside that statement can change
      what those rows ARE — so an edit to the renderer, which today throws away
      a 26-hour rebuild, correctly does not.

    The two values below are hashed separately because they are the only two of
    the twelve that do NOT reach the statement text — measured by mutation, not
    assumed, and pinned in both directions by
    ``test_which_fingerprint_inputs_the_emitted_statement_actually_covers``:

    * :data:`CALIBRATION_POPULATION_VERSION` — already its own branch in
      ``decode_staged_cursor`` (``REASON_POPULATION_VERSION``). Hashed here too
      so this digest is self-contained rather than relying on a sibling check;
    * :data:`REPRESENTATIVE_TIE_AUTHORITY` — stamped on the published artifact,
      so it is a DISCLOSURE input rather than a row input. Named here instead of
      being smuggled in beside the row-shaping ones.
    """
    import hashlib

    from app.utils.calibration_phase_ledger import input_fingerprint

    try:
        statement = _main_futures_sql(frozen=True)
    except Exception:  # noqa: BLE001 — no statement => never claim a match
        # Same discipline as ``population_predicate_fingerprint``: a digest
        # nothing can equal, so an unbuildable statement invalidates rather than
        # silently resuming units it could not describe.
        return f"unavailable:{time.time()}"
    return input_fingerprint(
        "staged-unit/v1",
        CALIBRATION_POPULATION_VERSION,
        REPRESENTATIVE_TIE_AUTHORITY,
        hashlib.md5(statement.encode()).hexdigest(),
    )


#: A carried read older than the FRESH key's own TTL cannot make the page any
#: fresher than serving that key would have, so there is no reason to keep it.
#: Derived from ``_MAIN_CACHE_TTL`` rather than chosen, so the two cannot drift.
_CARRY_MAX_AGE_S = _MAIN_CACHE_TTL


async def _run_calibration_main_build(runner=None):
    """Precompute the main /api/calibration payload and cache it in Redis.

    Thin caching wrapper over the shared ``compute_calibration_payload`` (Queue
    #257 Item 1): opens a task session, computes the ONE canonical payload, and
    publishes it so the HTTP endpoint serves it instantly instead of running the
    heavy queries in-request.

    Queue 272 (#1459) — truthful terminal + durable publication:
      * A partial/empty compute (statement_timeout mid-CTE, cancellation) is
        NEVER published — it cannot replace a valid cache entry.
      * The payload is published to BOTH the fresh ``main`` key (2h TTL) and the
        durable ``last_good`` key (7d TTL) so a streak of compute timeouts — the
        observed failure — can never blank the route.
      * Terminal metrics distinguish the compute, serialize, and publish stages
        (with generated_at + payload size) so a publication failure is visible
        and can never masquerade as success. A failed ``main`` publish RAISES so
        ``_tracked_run`` records a failure, while the SET-only writes leave any
        prior last-good intact.
    """
    from app.tasks.base import get_task_session
    from app.tasks.calibration_main_build import NULL_RUNNER
    from app.tasks.redis_state import get_redis_client
    from app.tasks.task_checkpoint import release_overlap_lock, try_acquire_overlap_lock
    from app.utils.calibration_phase_ledger import MAIN_BUILD_TASK, PHASE_PUBLISH

    runner = runner or NULL_RUNNER

    t0 = time.monotonic()
    async with get_task_session() as db:
        # Queue 300M: one writer at a time. A second beat starting while the
        # first is still building would advance the same checkpoint from two
        # directions; a PostgreSQL session advisory lock is the right primitive
        # because it cannot be evicted and it dies WITH the session — including
        # on SIGKILL, which a Redis ``SET NX EX`` lock survives as a stale lock
        # that blocks every subsequent beat.
        if not await try_acquire_overlap_lock(db, MAIN_BUILD_TASK):
            logger.info(
                "calibration main build: another run holds the lock — skipping"
            )
            return {"status": "skipped", "reason": "overlap_lock_not_acquired"}

        # Queue 274 (#1479): bound EVERY query of this compute at the DB level so a
        # wedged/bloat-slow statement self-cancels at ~the Celery soft limit and
        # RELEASES its xmin, instead of being SIGKILLed at the hard limit into an
        # orphaned backend that pins autovacuum and drives the bloat spiral that
        # broke organic recurrence.
        #
        # Queue 300M refines WHERE that bound comes from. This up-front SET LOCAL
        # remains the floor for the no-runner path; with a runner, each phase
        # re-applies a tighter bound derived from the time actually left before
        # the absolute deadline (see PhaseRunner.apply_statement_timeout), so the
        # backstop keeps shrinking as the window closes instead of staying at a
        # value only the first read could ever have used.
        await db.execute(
            text(f"SET LOCAL statement_timeout = {_MAIN_COMPUTE_STMT_TIMEOUT_MS}")
        )

        # Queue 300B Item 1: name the backend BEFORE the first heavy read, not
        # after. The window this covers is the one that matters — a build that
        # wedges inside phase 1 never reaches a later re-tag, and a wedged phase-1
        # backend with no ``application_name`` is precisely the pair of orphans
        # #1479 is still stuck on. With a runner, each phase re-arms this after
        # its commit clears the transaction-local setting.
        await runner.tag_session(db)

        try:
            response = await compute_calibration_payload(db, runner=runner)
        finally:
            await release_overlap_lock(db, MAIN_BUILD_TASK)
    # ^ the `async with` exit rolls back, closes and DISPOSES the per-task
    # engine. That teardown is real wall-clock the old `compute_ms` swallowed.
    compute_ms = round((time.monotonic() - t0) * 1000)

    # A partial/empty compute must never overwrite a valid cache entry (Item 1).
    if not _main_payload_is_publishable(response):
        raise RuntimeError(
            f"calibration compute produced an unpublishable payload "
            f"(buckets={len(response.get('buckets') or []) if isinstance(response, dict) else 'n/a'}, "
            f"outcomes={response.get('total_outcomes') if isinstance(response, dict) else 'n/a'}) "
            f"after {compute_ms}ms — not published"
        )

    # PHASE 4 (serialize_gate_publish). Deliberately NOT resumable: it consumes
    # every other phase's output and must run against the run that publishes.
    runner.begin(PHASE_PUBLISH)

    t1 = time.monotonic()
    with runner.stage("serialize"):
        payload_json = json.dumps(response)
    serialize_ms = round((time.monotonic() - t1) * 1000)
    payload_bytes = len(payload_json)

    with runner.stage("redis_client"):
        rc = get_redis_client()

    # Queue 297 Item 3: the ATOMIC PUBLISH GATE. Everything above built a
    # *candidate*; nothing published yet. Compare it against the currently
    # published artifact and only then perform one publication of main +
    # last_good. Queue 272's `_main_payload_is_publishable` already refused an
    # EMPTY payload; it could not refuse a complete-looking but wrong one — a
    # build that lost two thirds of the population, or whose well-traded/thin
    # ordering inverted, replaced the good copy silently. A rejected candidate
    # touches neither key, so the last published snapshot keeps serving.
    from app.utils.calibration_publish_gate import evaluate_publish

    # Queue 300M Item 0: THIS is the stretch r343's arithmetic could not see.
    # Its last success ran 1,502.5s total against compute_ms=534.9s,
    # serialize_ms=6 and publish_ms=113 — leaving 967.5s (64% of the whole
    # window) in code that no timer covered, of which this baseline read and
    # gate are the only substantial part. The baseline read pulls up to two
    # ~376KB Redis values and `json.loads` each (a C-level decode that holds
    # the GIL for its whole duration — gotcha #38), then the gate builds a
    # census over BOTH payloads. Timed separately from here on, so the next
    # organic beat attributes those 967s instead of leaving them a mystery.
    with runner.stage("baseline_read"):
        baseline = _read_published_baseline(rc)
    with runner.stage("publish_gate"):
        verdict = evaluate_publish(response, baseline)
    gate = {
        "ok": verdict.ok,
        "first_publish": verdict.first_publish,
        "version_bumped": verdict.version_bumped,
        "codes": verdict.codes,
        "fingerprint": verdict.fingerprint,
        "candidate_population": verdict.candidate.get("population"),
        "published_population": verdict.published.get("population"),
        "candidate_version": verdict.candidate.get("population_version"),
        "published_version": verdict.published.get("population_version"),
        # C-RV-3 [P2], CAL-P042/#1768 follow-up. WHICH baseline answered is the
        # whole point of the durable probe, and it was observable only on the
        # rejection path — a REJECTED build carries its codes and detail into a
        # deduped issue, so `durable` vs `provided` could be read off that. A
        # build that PASSED after recovering its baseline from durable history
        # was byte-identical in telemetry to one that read Redis normally. The
        # branch exists to make `found` / `cold_start` / `indeterminate`
        # distinguishable, and the success case is exactly where the new safety
        # path is exercised silently.
        "baseline_source": verdict.baseline_source,
        "baseline_probe": verdict.baseline_probe,
        # CAL-P070 / #1955. A PASS that admitted a +17.9% population move and a
        # pass on a 0.1% beat were about to be byte-identical here, which is the
        # same hole the line above closes for ``baseline_source`` and the fourth
        # instance of it this program has found. The gate records what it
        # excused; the run evidence has to carry it or nobody can read it.
        "observations": verdict.observation_codes,
        "observation_details": [o["detail"] for o in verdict.observations],
    }

    runner.outcome["gate"] = "pass" if verdict.ok else "refuse"
    runner.outcome["gate_observations"] = verdict.observation_codes
    # Also on the run OUTCOME, not just the summary: `outcome` is what
    # `save_phase_ledger` persists, so this survives into the durable run
    # evidence a later reader actually queries. Written before the rejection
    # branch below, so a refused run records which baseline refused it.
    runner.outcome["baseline_source"] = verdict.baseline_source
    runner.outcome["baseline_probe"] = verdict.baseline_probe

    if not verdict.ok:
        with runner.stage("gate_rejection_filing"):
            filing = _file_publish_gate_rejection(verdict)
        logger.error(
            "calibration publish gate REJECTED candidate (%s): %s [filing=%s]",
            ", ".join(verdict.codes), verdict.summary(), filing.get("action"),
        )
        raise RuntimeError(
            f"calibration publish gate rejected the candidate "
            f"({', '.join(verdict.codes)}): {verdict.summary()} — "
            f"nothing published, prior snapshot preserved "
            f"(fingerprint {verdict.fingerprint}, filing {filing.get('action')})"
        )

    for observation in verdict.observations:
        # WARNING, not INFO: this is a fact that decided a publish, and a
        # publish that moved the population by more than the standing band is
        # exactly what an operator should be able to find without knowing to
        # look. It is not a failure, and the message says so by describing what
        # was admitted and on what evidence.
        logger.warning(
            "calibration publish gate ADMITTED a candidate on an explicit "
            "observation (%s): %s",
            observation["code"], observation["detail"],
        )

    t2 = time.monotonic()

    # Queue 298 Item 2: DURABLE FIRST. The candidate passed the gate, so publish
    # the survivor before touching either accelerator. Ordering is the contract:
    # if we wrote Redis first and the durable write then failed, the volatile
    # copy would be AHEAD of the durable one — a torn pair the readers must treat
    # as untrustworthy. Writing durable first makes that state unreachable in the
    # happy path and diagnosable when it does appear.
    from app.services.durable_snapshots import publish_snapshot_standalone
    from app.utils.calibration_publish_gate import _parse_generated_at
    from app.utils.durable_state import DurableEnvelope, evaluate_publication

    envelope = DurableEnvelope.build(
        identity=_DURABLE_IDENTITY,
        schema_version=CALIBRATION_POPULATION_VERSION,
        payload=response,
        # Generation is derived from the build's OWN stamp, so ordering survives
        # a retry and matches what the route reads back.
        generated_at=_parse_generated_at(response.get("generated_at")),
        source="precompute_calibration",
    )
    with runner.stage("durable_publish"):
        durable_stage = await publish_snapshot_standalone(envelope)

    # A durable write that lost the generation race is still a good copy on disk.
    durable_ok = durable_stage["status"] in ("ok", "superseded")

    # Never publish a volatile copy the durable store does not back: that is the
    # torn pair, and it is worse than having no accelerator at all.
    stages: dict = {}
    if durable_ok:
        with runner.stage("redis_accelerate"):
            stages = _publish_calibration_main(rc, payload_json)
    else:
        logger.error(
            "calibration publish: durable write FAILED (%s) — skipping the Redis "
            "accelerators so volatile can never lead durable; prior last-good preserved",
            durable_stage.get("error") or durable_stage["status"],
        )
    stages["durable"] = durable_stage["status"]
    if durable_stage.get("error"):
        stages["durable_error"] = durable_stage["error"]
    stages["durable_generation"] = envelope.generation
    publish_ms = round((time.monotonic() - t2) * 1000)

    runner.outcome["durable"] = durable_stage["status"]
    runner.outcome["volatile"] = (
        "ok" if stages.get("main") == "ok"
        else "not_attempted" if "main" not in stages
        else "error"
    )
    runner.outcome["published"] = bool(durable_ok)
    runner.outcome["artifact_generation"] = envelope.generation if durable_ok else None

    summary = {
        "buckets": len(response["buckets"]),
        "outcomes": response["total_outcomes"],
        "generated_at": response.get("generated_at"),
        "payload_bytes": payload_bytes,
        "compute_ms": compute_ms,
        "serialize_ms": serialize_ms,
        "publish_ms": publish_ms,
        "publish": stages,
        "gate": gate,
    }

    # Queue 298 Item 2: the DURABLE write is what makes a run a success, not the
    # accelerator. Before this, a failed ``main`` SET raised while a failed
    # last_good SET was merely logged — exactly backwards once the survivor moved
    # off Redis. A run that saved the payload durably has done its job even if
    # Redis is unreachable; a run that did NOT must never report success, or the
    # task metric (and any Review/Verify evidence citing it) claims a completed
    # run that persisted nothing.
    outcome = evaluate_publication(
        compute_complete=True,
        durable_write="ok" if durable_ok else "error",
        volatile_write=(
            "ok" if stages.get("main") == "ok"
            else "not_attempted" if "main" not in stages
            else "error"
        ),
        stages=stages,
    )
    summary["publication"] = {
        "success": outcome.success,
        "errors": outcome.errors,
        "durable": durable_stage["status"],
        "durable_generation": envelope.generation,
    }
    outcome.raise_if_failed("calibration publish")

    if stages.get("main") != "ok":
        # Durable landed, so this is a degraded-but-successful publish: the route
        # will serve the durable copy with an honest dated marker until Redis
        # recovers. Loud, but not a task failure.
        logger.warning(
            "calibration publish: durable OK but Redis accelerator failed "
            "(last_good=%s, main=%s, err=%s) — route will serve the durable copy",
            stages.get("last_good"), stages.get("main"), stages.get("main_error"),
        )

    logger.info(
        "Cached main calibration in Redis (%d buckets, %d outcomes, %d bytes; "
        "compute=%dms publish=%dms; last_good=%s)",
        summary["buckets"], summary["outcomes"], payload_bytes,
        compute_ms, publish_ms, stages.get("last_good"),
    )
    runner.complete(PHASE_PUBLISH)
    summary["status"] = "ok"
    return summary


async def _precompute_calibration_main():
    """Run ONE main calibration build, and make its progress durable (Queue 300M).

    Everything about the build itself lives in :func:`_run_calibration_main_build`.
    This wrapper exists for the two things that must happen whether that build
    finished, timed out, was cancelled, or blew up:

    **Bank what was earned.** The build's three read phases each commit and hand
    their output to a durable checkpoint. A run that dies at the diagnostics
    read no longer throws away the population CTE it spent most of its window
    computing — the next beat carries it and starts where this one stopped.
    That is the whole visible payoff: durable progress across runs, instead of
    repeating the same 25 minutes and leaving the public page on yesterday's
    snapshot.

    **Write the ledger, always.** The phase ledger is the measurement rail Item
    0 exists to build, and the runs whose timings matter most are precisely the
    ones that failed. It records what every phase actually cost, and the NEXT
    run's budgets are derived from it — which is why no budget is invented here.
    A ledger write failure makes this run's progress UNKNOWN, never GREEN.

    Three deliberate asymmetries in what happens to the checkpoint:

    * A **complete publish** clears it. There is nothing left to resume.
    * A **gate refusal** clears it too. The candidate was rejected for what it
      contained, so carrying the same reads forward would rebuild the identical
      rejected candidate every hour, forever. Refusal must force fresh reads.
    * A **durable/Redis publication failure** keeps it. The payload was fine;
      only persisting it failed, so the next beat should re-publish from the
      carried reads rather than re-earn them.
    """
    from app.tasks.calibration_main_build import (
        build_runner,
        checkpoint_terminal,
        clear_main_checkpoint,
        save_main_checkpoint,
        save_phase_ledger,
    )
    from app.utils.calibration_phase_ledger import (
        RESUMABLE_PHASES,
        REFUSE,
        health_for,
        phase_ledger_row,
        terminal_for,
    )

    fingerprint = _main_input_fingerprint()
    # The two durable reads below are the only work outside the runner's own
    # accounting, so they are the only thing left in unmeasured_overhead.
    runner, action = await build_runner(
        population_version=CALIBRATION_POPULATION_VERSION,
        fingerprint=fingerprint,
        carry_max_age_s=_CARRY_MAX_AGE_S,
    )

    if action == REFUSE:
        # Another worker holds an unexpired lease on the checkpoint. Running a
        # second build against it is how two workers each advance half of one.
        logger.info(
            "calibration main build: checkpoint leased by %s — skipping",
            runner.checkpoint.owner,
        )
        runner.ledger.elapsed_ms = 0
        ledger_write = await save_phase_ledger(
            runner, {"terminal": "overlap_refused", "checkpoint_action": action}
        )
        return {
            "status": "skipped",
            "reason": "checkpoint_leased",
            "owner": runner.checkpoint.owner,
            "ledger_write": ledger_write,
        }

    summary: dict = {}
    failure: BaseException | None = None
    cancelled = False
    try:
        summary = await _run_calibration_main_build(runner)
    except BaseException as exc:  # noqa: BLE001 — CancelledError must be recorded too
        failure = exc
        status = runner.abort(exc)
        cancelled = status == "cancelled"
        logger.error(
            "calibration main build ended %s after %dms in phase group %s: %s",
            status, runner.elapsed_ms(), list(runner.ledger.completed_required), exc,
        )

    runner.ledger.elapsed_ms = runner.elapsed_ms()
    measured = sum(r.duration_ms for r in runner.ledger.records.values())
    runner.ledger.unmeasured_overhead_ms = max(0, runner.ledger.elapsed_ms - measured)

    published = bool(runner.outcome.get("published"))
    gate_state = runner.outcome.get("gate")
    terminal = terminal_for(
        all_required_done=runner.ledger.all_required_done,
        published=published,
        error=failure is not None and not cancelled,
        cancelled=cancelled,
    )

    # --- checkpoint -----------------------------------------------------------
    checkpoint_write = "not_attempted"
    checkpoint_advanced = False
    banked: dict[str, str] = {}
    try:
        if terminal == "complete" or gate_state == "refuse":
            ok = await clear_main_checkpoint(
                population_version=CALIBRATION_POPULATION_VERSION,
                fingerprint=fingerprint,
                owner=runner.owner,
            )
            checkpoint_write = "ok" if ok else "error"
        else:
            checkpoint, banked = runner.build_checkpoint()
            if checkpoint.completed_phases:
                ok = await save_main_checkpoint(
                    checkpoint, terminal=checkpoint_terminal(runner)
                )
                checkpoint_write = "ok" if ok else "error"
                checkpoint_advanced = ok
            else:
                checkpoint_write = "nothing_to_bank"
    except Exception as exc:  # noqa: BLE001 — a lost checkpoint is not a lost build
        checkpoint_write = "error"
        logger.warning("calibration main checkpoint write failed: %s", exc)

    for phase in RESUMABLE_PHASES:
        runner.ledger.note_checkpoint(
            phase,
            write=checkpoint_write if banked.get(phase) == "stored" else "not_attempted",
            advanced=checkpoint_advanced and banked.get(phase) == "stored",
        )

    # --- ledger ---------------------------------------------------------------
    ledger_write = await save_phase_ledger(
        runner,
        {
            "terminal": terminal,
            "checkpoint_action": action,
            "checkpoint_write": checkpoint_write,
            "banked": banked,
            "carried": list(runner.carried_phases),
            "outcome": runner.outcome,
            # Queue 300B Item 1: the server-side identity of the backend that ran
            # this build. Written on EVERY terminal, including the timeouts and
            # cancellations — those are the runs whose backend might still be
            # sitting there, and this row is what names it afterwards.
            "session_identity": runner.session_identity,
        },
    )
    health = health_for(
        terminal=terminal,
        ledger_write=ledger_write,
        artifact_fresh=published,
        artifact_generation=runner.outcome.get("artifact_generation"),
    )

    contract = phase_ledger_row(
        runner.ledger,
        terminal=terminal,
        published=published,
        durable=str(runner.outcome.get("durable")),
        volatile=str(runner.outcome.get("volatile")),
        artifact_generation=runner.outcome.get("artifact_generation"),
        gate=str(gate_state),
        checkpoint_action=action,
        checkpoint_owner=runner.owner,
        checkpoint_version=CALIBRATION_POPULATION_VERSION,
        checkpoint_advanced=checkpoint_advanced,
        # Nothing is published unless the whole build completed, so a run that
        # did not complete has, by construction, left the prior artifact alone.
        previous_preserved=True,
        health_verdict=health,
        artifact_fresh=published,
        health_generation=runner.outcome.get("artifact_generation"),
        cancellation=(
            {"raised": True, "terminal_recorded": True, "swallowed": False}
            if cancelled
            else None
        ),
    )

    if failure is not None:
        # The build's own failure is the story; the ledger above is why the next
        # beat will be cheaper. Re-raise so ``_tracked_run`` records a failure
        # rather than a success with an empty summary.
        raise failure

    summary["phase_ledger"] = {
        "terminal": terminal,
        "health": health,
        "plan": runner.ledger.plan.as_payload()["status"],
        "infeasible_phases": list(runner.ledger.plan.infeasible_phases),
        "checkpoint_action": action,
        "checkpoint_write": checkpoint_write,
        "ledger_write": ledger_write,
        "carried": list(runner.carried_phases),
        "banked": banked,
        # Item 0's reconciliation surface: every named stretch of the build,
        # so the r343-style "where did 967s go?" question is answered by
        # reading one field instead of subtracting three.
        "stages": dict(sorted(runner.ledger.stages.items())),
        "unmeasured_overhead_ms": runner.ledger.unmeasured_overhead_ms,
        "elapsed_ms": runner.ledger.elapsed_ms,
        "phases": {
            name: {
                "status": record.status,
                "duration_ms": record.duration_ms,
                "budget_ms": record.budget_ms,
            }
            for name, record in runner.ledger.records.items()
        },
        "contract": contract,
    }
    return summary


def _time_horizon_payload(horizons_result: dict) -> dict:
    """Assemble the served time-horizon payload from whatever horizons are computed.

    Additive over the historical shape (``horizons`` + ``description`` +
    ``generated_at``): also carries ``complete`` and ``missing`` so the endpoint can
    serve a PARTIAL result (e.g. 3/4 horizons) instead of the "computing" placeholder
    when one horizon is slow/poison — the #1171 fix (never publish nothing)."""
    missing = [label for label, _ in _HORIZONS if label not in horizons_result]
    return {
        "horizons": horizons_result,
        "complete": not missing,
        "missing": missing,
        "description": (
            "Calibration at multiple time horizons for non-event markets "
            "(elections, economics, entertainment, etc.). Each horizon shows "
            "prediction accuracy using the last available snapshot N days "
            "before market resolution."
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _publish_time_horizon(rc, horizons_result: dict) -> None:
    """Publish the currently-computed horizons to the served main key. Safe to call
    after every horizon: an OOM SIGKILL or statement_timeout on a LATER horizon can
    then never strand the endpoint on "computing" — it serves the horizons done so
    far (#1171: the main key was previously written ONLY after all 4 completed, so a
    single poison horizon blocked the whole payload forever)."""
    if not horizons_result:
        return
    try:
        rc.set(
            "bainluck:calibration:time_horizon",
            json.dumps(_time_horizon_payload(horizons_result)),
            ex=_CACHE_TTL,
        )
    except Exception as exc:  # noqa: BLE001 — publish is best-effort, never fatal
        logger.warning("time-horizon: main-key publish failed: %s", exc)


def _load_time_horizon_wip(rc) -> dict:
    """Load the resumable horizon WIP accumulator, rejecting stale populations.

    Queue #263 Item 2: the WIP is version-wrapped
    (``{"population_version": <v>, "horizons": {...}}``). A resume MUST discard:
      * a LEGACY unwrapped accumulator (a bare ``{label: data}`` dict with no
        wrapper — the pre-#263 shape),
      * corrupt JSON, and
      * any wrapper whose ``population_version`` != the current version,
    so a horizon computed under an older population is never resumed (skipping its
    recompute) nor republished under the new version. Returns ``{label: data}`` for
    ONLY the current-version horizons, so the caller recomputes everything else.
    """
    wip_raw = rc.get(_TIME_HORIZON_WIP_KEY)
    if not wip_raw:
        return {}
    try:
        parsed = json.loads(wip_raw)
    except (ValueError, TypeError):
        return {}
    if (
        not isinstance(parsed, dict)
        or parsed.get("population_version") != CALIBRATION_POPULATION_VERSION
    ):
        # Legacy unwrapped or version-mismatched accumulator — recompute from scratch.
        return {}
    horizons = parsed.get("horizons")
    if not isinstance(horizons, dict):
        return {}
    valid_labels = {label for label, _ in _HORIZONS}
    # Defense in depth: keep only current-version horizon entries. A mixed-version
    # wrapper should be impossible (writes always stamp the current version on both
    # the wrapper and every horizon's diag), but a stale horizon must never resume.
    return {
        k: v
        for k, v in horizons.items()
        if k in valid_labels
        and isinstance(v, dict)
        and v.get("population_version") == CALIBRATION_POPULATION_VERSION
    }


def _save_time_horizon_wip(rc, horizons_result: dict) -> None:
    """Persist the horizon WIP accumulator wrapped with the current population
    version (Queue #263 Item 2), so a later run can only resume horizons computed
    under the SAME population. Best-effort, mirroring the publish helper."""
    try:
        rc.set(
            _TIME_HORIZON_WIP_KEY,
            json.dumps({
                "population_version": CALIBRATION_POPULATION_VERSION,
                "horizons": horizons_result,
            }),
            ex=_CACHE_TTL,
        )
    except Exception as exc:  # noqa: BLE001 — WIP persistence is best-effort
        logger.warning("time-horizon: WIP persist failed: %s", exc)


def _build_time_horizon_sql(days: int) -> tuple[str, dict]:
    """Build the horizon calibration SQL for one horizon (Queue #262 Item 1).

    Pure string builder (no DB) so it is unit-testable. The horizon population
    REUSES the canonical ``_calibration_population_ctes`` resolved-question
    identity + independent-truth allowlist + artifact exclusions, finalized on the
    horizon SNAPSHOT as the curve price — NOT the terminal ``deduped`` scalar.
    Normalization, field completeness, mode/tail, and bucket assignment are all
    evaluated on this horizon's price. ``market_info`` is scoped to the non-event,
    resolution-date universe so the whole chain runs on the small horizon set;
    ``horizon_price`` is a leading LATERAL selecting each outcome's last snapshot
    at/under the cutoff, INNER-joined into the price-bearing CTEs so ONLY outcomes
    actually priced at this horizon survive. Returns ``(sql, params)``.
    """
    cutoff_expr = (
        "fm.resolution_date"
        if days == 0
        else "fm.resolution_date - make_interval(days => :days)"
    )
    horizon_price_cte = f"""horizon_price AS (
                    SELECT fo.id AS outcome_id, horizon.probability AS horizon_prob
                    FROM futures_outcomes fo
                    JOIN futures_markets fm ON fm.id = fo.market_id
                    LEFT JOIN LATERAL (
                        SELECT fos.probability
                        FROM futures_odds_snapshots fos
                        WHERE fos.outcome_id = fo.id
                          AND fos.captured_at <= {cutoff_expr}
                          AND fos.probability > 0 AND fos.probability < 1
                        ORDER BY fos.captured_at DESC
                        LIMIT 1
                    ) horizon ON true
                    WHERE fm.status = 'resolved'
                      AND fm.event_id IS NULL
                      AND fm.resolution_date IS NOT NULL
                      AND horizon.probability IS NOT NULL
                ),
            """
    population = _calibration_population_ctes(
        curve_price="hp.horizon_prob",
        curve_price_join="JOIN horizon_price hp ON hp.outcome_id = fo.id",
        rn_order="ABS(hp.horizon_prob - 0.5)",
        market_info_extra=(
            "AND fm.event_id IS NULL AND fm.resolution_date IS NOT NULL"
        ),
        leading_ctes=horizon_price_cte,
    )
    sql = (
        "WITH " + population + """,
                h_diag AS (
                    SELECT
                        (SELECT COUNT(*) FROM ranked_outcomes) AS candidate_n,
                        (SELECT COUNT(*) FROM deduped) AS final_n,
                        (SELECT COUNT(DISTINCT vm_id) FROM deduped) AS distinct_questions,
                        (SELECT COUNT(*) FROM ranked_outcomes WHERE NOT is_liquid) AS excl_illiquid,
                        (SELECT COUNT(*) FROM ranked_outcomes WHERE is_poly_placeholder) AS excl_poly_placeholder,
                        (SELECT COUNT(*) FROM ranked_outcomes WHERE is_malformed_binary) AS excl_malformed_binary,
                        (SELECT COUNT(*) FROM ranked_outcomes WHERE is_esports_bundle) AS excl_esports_bundle,
                        (SELECT COUNT(*) FROM ranked_outcomes WHERE is_golf_placeholder) AS excl_golf_placeholder,
                        (SELECT COUNT(*) FROM ranked_outcomes WHERE is_kalshi_prop_threshold) AS excl_kalshi_prop_threshold,
                        (SELECT COUNT(*) FROM ranked_outcomes WHERE is_weather_wide_spread) AS excl_weather_wide_spread,
                        (SELECT COUNT(*) FROM normalized WHERE is_field_incomplete) AS excl_field_incomplete
                ),
                h_buckets AS (
                    SELECT
                        LEAST(FLOOR(adj_opening_probability * 10)::int, 9) AS bucket_idx,
                        source, category,
                        COUNT(*) AS n,
                        SUM(CASE WHEN is_winner THEN 1 ELSE 0 END) AS winners,
                        AVG(adj_opening_probability) AS avg_prob,
                        SUM(adj_opening_probability::float) AS sum_prob,
                        SUM((adj_opening_probability::float - CASE WHEN is_winner THEN 1.0 ELSE 0.0 END)^2) AS sum_sq_err
                    FROM deduped
                    GROUP BY 1, 2, 3
                )
                SELECT b.bucket_idx, b.source, b.category, b.n, b.winners,
                    b.avg_prob, b.sum_prob, b.sum_sq_err,
                    d.candidate_n, d.final_n, d.distinct_questions,
                    d.excl_illiquid, d.excl_poly_placeholder, d.excl_malformed_binary,
                    d.excl_esports_bundle, d.excl_golf_placeholder,
                    d.excl_kalshi_prop_threshold, d.excl_weather_wide_spread,
                    d.excl_field_incomplete
                FROM h_diag d
                LEFT JOIN h_buckets b ON true
                ORDER BY b.bucket_idx, b.source, b.category
            """
    )
    params: dict = {"days": days} if days > 0 else {}
    return sql, params


async def _compute_time_horizon_calibration():
    """Compute time-horizon calibration and store in Redis.

    Bounded + chunked + resumable (Item 1, Queue #220/221): each horizon runs
    under a per-query statement_timeout, completed horizons are persisted to a
    WIP accumulator, and an internal deadline stops the run cleanly (resuming the
    remaining horizons next beat) so it never hits the 600s soft limit again.

    #1171 (Queue #228): each horizon is ISOLATED (a statement_timeout / OOM-adjacent
    DB error on one horizon rolls back and continues — one poison horizon never
    kills the task, gotcha #42), and the served main key is published after EVERY
    completed horizon (partial-first) so the endpoint serves 3/4 horizons instead of
    "computing" forever when one horizon is persistently slow. The WIP cursor is
    only cleared once all four are present."""
    from app.tasks.base import get_task_session
    from app.tasks.redis_state import get_redis_client

    rc = get_redis_client()
    start = time.monotonic()

    # Resume from any WIP accumulator left by a prior (deadline-truncated) run.
    # Queue #263 Item 2: the loader rejects legacy-unwrapped / corrupt / version-
    # mismatched accumulators, so a horizon computed under an older population is
    # recomputed rather than resumed or republished under the current version.
    horizons_result: dict = _load_time_horizon_wip(rc)

    from app.tasks.calibration_main_build import tag_scheduled_session

    async with get_task_session() as db:
        # Queue 300B Item 1: name this backend before its first LATERAL probe.
        await tag_scheduled_session(db, task="compute_time_horizon_calibration")

        for label, days in _HORIZONS:
            if label in horizons_result:
                continue  # already computed in an earlier run — resumable cursor

            # Deadline guard: only start a horizon if it can run its full
            # statement_timeout and still finish before the internal deadline.
            # Bounds the longest single uninterrupted op (not just loop
            # boundaries — the budget-guard lesson), so the run always returns
            # cleanly under the 600s soft limit.
            elapsed = time.monotonic() - start
            if elapsed + _HORIZON_STMT_TIMEOUT_S > _HORIZON_DEADLINE_S:
                _save_time_horizon_wip(rc, horizons_result)
                _publish_time_horizon(rc, horizons_result)  # serve partial now (#1171)
                logger.info(
                    "time-horizon: deadline at %.0fs, %d/%d horizons done — "
                    "persisted WIP + published partial, resuming next run",
                    elapsed, len(horizons_result), len(_HORIZONS),
                )
                return {
                    "status": "partial",
                    "horizons_done": len(horizons_result),
                    "total": len(_HORIZONS),
                }

            # Fresh bounded transaction per horizon (mirror _begin_census): roll
            # back any aborted state, then arm the per-query statement_timeout.
            try:
                await db.rollback()
            except Exception:
                pass
            try:
                await db.execute(
                    text(f"SET LOCAL statement_timeout = '{_HORIZON_STMT_TIMEOUT_S}s'")
                )
            except Exception:
                pass

            horizon_sql_str, params = _build_time_horizon_sql(days)
            horizon_sql = text(horizon_sql_str)

            # ISOLATE the one risky op (#1171): the LATERAL probe is what hits the
            # per-horizon statement_timeout — a QueryCanceledError here was
            # previously UNCAUGHT and killed the whole task, so one persistently
            # slow horizon (the poison T-0) blocked all four from ever publishing.
            # Catch, roll back, and DEFER this horizon to the next run; the horizons
            # already computed stay in WIP and are served (gotcha #42: one bad item
            # must never wipe the whole pass).
            try:
                result = await db.execute(horizon_sql, params)
                rows = result.all()
            except Exception as exc:  # noqa: BLE001 — statement_timeout / transient DB
                logger.warning(
                    "time-horizon: horizon %s failed (%s) — rolled back, deferring "
                    "to next run; %d/%d horizons already computed are unaffected",
                    label, type(exc).__name__, len(horizons_result), len(_HORIZONS),
                )
                try:
                    await db.rollback()
                except Exception:
                    pass
                continue

            # Queue #262 Item 1: every row carries the same horizon diagnostics
            # (candidate/final/distinct-question counts + per-reason exclusion
            # counts) via a CROSS-shaped LEFT JOIN, and a diag-only row (bucket_idx
            # NULL) is always present even when no rows survive to a bucket.
            bucket_dicts = []
            diag: dict = {}
            for r in rows:
                if not diag:
                    diag = {
                        "population_version": CALIBRATION_POPULATION_VERSION,
                        "candidate_outcomes": int(r.candidate_n or 0),
                        "final_outcomes": int(r.final_n or 0),
                        "distinct_questions": int(r.distinct_questions or 0),
                        "excluded": {
                            "illiquid": int(r.excl_illiquid or 0),
                            "poly_placeholder": int(r.excl_poly_placeholder or 0),
                            "malformed_binary": int(r.excl_malformed_binary or 0),
                            "esports_bundle": int(r.excl_esports_bundle or 0),
                            "golf_placeholder": int(r.excl_golf_placeholder or 0),
                            "kalshi_prop_threshold": int(r.excl_kalshi_prop_threshold or 0),
                            "weather_wide_spread": int(r.excl_weather_wide_spread or 0),
                            "field_incomplete": int(r.excl_field_incomplete or 0),
                        },
                    }
                if r.bucket_idx is None:
                    continue  # diag-only row — no surviving buckets this horizon
                ci_lo, ci_hi = _wilson_ci(r.winners, r.n)
                bucket_dicts.append({
                    "bucket_idx": r.bucket_idx,
                    "source": r.source,
                    "category": r.category,
                    "n": r.n,
                    "winners": r.winners,
                    "avg_prob": round(float(r.avg_prob), 4),
                    "sum_prob": round(float(r.sum_prob), 4),
                    "sum_sq_err": round(float(r.sum_sq_err), 4),
                    "ci_lower": round(ci_lo, 4),
                    "ci_upper": round(ci_hi, 4),
                })

            total_n = sum(b["n"] for b in bucket_dicts)
            total_winners = sum(b["winners"] for b in bucket_dicts)

            if total_n < _MIN_OUTCOMES_PER_HORIZON:
                horizons_result[label] = {
                    "buckets": bucket_dicts,
                    "total_outcomes": total_n,
                    "total_winners": total_winners,
                    "mce": None,
                    "mce_ci_lower": None,
                    "mce_ci_upper": None,
                    "skipped": True,
                    "skip_reason": f"Only {total_n} outcomes (minimum {_MIN_OUTCOMES_PER_HORIZON})",
                    **diag,
                }
                _save_time_horizon_wip(rc, horizons_result)
                _publish_time_horizon(rc, horizons_result)  # serve partial (#1171)
                continue

            # Aggregate for MCE
            agg: dict[int, dict] = {}
            for b in bucket_dicts:
                idx = b["bucket_idx"]
                if idx not in agg:
                    agg[idx] = {"n": 0, "winners": 0, "sum_prob": 0.0}
                agg[idx]["n"] += b["n"]
                agg[idx]["winners"] += b["winners"]
                agg[idx]["sum_prob"] += b["sum_prob"]

            mce = _compute_horizon_mce([
                {"n": v["n"], "winners": v["winners"], "sum_prob": v["sum_prob"]}
                for v in agg.values()
            ])

            # Bootstrap CI
            agg_list = [
                {"n": v["n"], "winners": v["winners"],
                 "avg_prob": v["sum_prob"] / v["n"]}
                for v in agg.values() if v["n"] > 0
            ]
            mce_ci_lo, mce_ci_hi = _bootstrap_mce_ci(agg_list)

            # Per-source MCE
            by_source: dict[str, dict[int, dict]] = {}
            for b in bucket_dicts:
                src = b["source"]
                idx = b["bucket_idx"]
                if src not in by_source:
                    by_source[src] = {}
                if idx not in by_source[src]:
                    by_source[src][idx] = {"n": 0, "winners": 0, "sum_prob": 0.0}
                by_source[src][idx]["n"] += b["n"]
                by_source[src][idx]["winners"] += b["winners"]
                by_source[src][idx]["sum_prob"] += b["sum_prob"]
            mce_by_source = {}
            for src, src_agg in by_source.items():
                src_total = sum(v["n"] for v in src_agg.values())
                if src_total >= _MIN_OUTCOMES_PER_HORIZON:
                    mce_by_source[src] = _compute_horizon_mce([
                        {"n": v["n"], "winners": v["winners"], "sum_prob": v["sum_prob"]}
                        for v in src_agg.values()
                    ])

            # Per-category MCE
            by_cat: dict[str, dict[int, dict]] = {}
            for b in bucket_dicts:
                cat = b["category"]
                idx = b["bucket_idx"]
                if cat not in by_cat:
                    by_cat[cat] = {}
                if idx not in by_cat[cat]:
                    by_cat[cat][idx] = {"n": 0, "winners": 0, "sum_prob": 0.0}
                by_cat[cat][idx]["n"] += b["n"]
                by_cat[cat][idx]["winners"] += b["winners"]
                by_cat[cat][idx]["sum_prob"] += b["sum_prob"]
            mce_by_category = {}
            for cat, cat_agg in by_cat.items():
                cat_total = sum(v["n"] for v in cat_agg.values())
                if cat_total >= _MIN_OUTCOMES_PER_HORIZON:
                    mce_by_category[cat] = _compute_horizon_mce([
                        {"n": v["n"], "winners": v["winners"], "sum_prob": v["sum_prob"]}
                        for v in cat_agg.values()
                    ])

            horizons_result[label] = {
                "buckets": bucket_dicts,
                "total_outcomes": total_n,
                "total_winners": total_winners,
                "mce": mce,
                "mce_ci_lower": round(mce_ci_lo * 100, 2),
                "mce_ci_upper": round(mce_ci_hi * 100, 2),
                "mce_by_source": mce_by_source,
                "mce_by_category": mce_by_category,
                **diag,
            }
            # Persist immediately so a later horizon's slowness (or the deadline
            # guard firing next iteration) can never discard this one — and publish
            # the served main key NOW so the endpoint reflects each horizon as it
            # lands, never stranded on "computing" if a later horizon dies (#1171).
            _save_time_horizon_wip(rc, horizons_result)
            _publish_time_horizon(rc, horizons_result)

    # Publish whatever is computed. When all four are present this is the full
    # payload and the WIP cursor is cleared; otherwise it is an honest PARTIAL
    # (``complete: false``, ``missing: [...]``) that the endpoint still serves —
    # the missing horizon(s) retry next run (#1171: never publish nothing).
    _publish_time_horizon(rc, horizons_result)
    # Queue #263 Item 2: complete requires all four named horizons AND every one to
    # carry the current population version — so a run that somehow still holds a
    # stale-version horizon is reported partial (and its WIP is NOT cleared) rather
    # than declared done. In practice the loader already drops off-version horizons,
    # so this is a belt-and-braces invariant on the exit path.
    complete = len(horizons_result) == len(_HORIZONS) and all(
        isinstance(horizons_result.get(label), dict)
        and horizons_result[label].get("population_version")
        == CALIBRATION_POPULATION_VERSION
        for label, _ in _HORIZONS
    )
    if complete:
        rc.delete(_TIME_HORIZON_WIP_KEY)
    logger.info(
        "time-horizon: published %d/%d horizons (%s)",
        len(horizons_result), len(_HORIZONS), "complete" if complete else "partial",
    )
    return {
        "status": "ok" if complete else "partial",
        "horizons": len(horizons_result),
        "total": len(_HORIZONS),
    }


# ---------------------------------------------------------------------------
# Fair-fight comparison precomputation
# ---------------------------------------------------------------------------

# Minimum shared markets to report a pair
_MIN_SHARED = 100


def _compute_mce(probs: list[float], outcomes: list[bool]) -> float | None:
    if not probs:
        return None
    bucket_n: dict[int, int] = {}
    bucket_sum_prob: dict[int, float] = {}
    bucket_winners: dict[int, int] = {}
    for p, won in zip(probs, outcomes):
        idx = min(int(p * 10), 9)
        bucket_n[idx] = bucket_n.get(idx, 0) + 1
        bucket_sum_prob[idx] = bucket_sum_prob.get(idx, 0.0) + p
        bucket_winners[idx] = bucket_winners.get(idx, 0) + (1 if won else 0)
    if not bucket_n:
        return None
    total_abs_err = 0.0
    k = 0
    for idx in bucket_n:
        n = bucket_n[idx]
        avg_prob = bucket_sum_prob[idx] / n
        actual = bucket_winners[idx] / n
        total_abs_err += abs(actual - avg_prob)
        k += 1
    return round(total_abs_err / k * 100, 2) if k > 0 else None


# Kalshi prop filter — same as source_intelligence.py
_KALSHI_PROP_FILTER = """
    AND NOT (
        wp.source = 'kalshi'
        AND wp.game_state->>'market_name' IS NOT NULL
        AND (
            wp.game_state->>'market_name' ILIKE '%spread%'
            OR wp.game_state->>'market_name' ILIKE '%total%'
            OR wp.game_state->>'market_name' ILIKE '%overtime%'
            OR wp.game_state->>'market_name' ILIKE '%half winner%'
            OR wp.game_state->>'market_name' ILIKE '%half total%'
            OR wp.game_state->>'market_name' ILIKE '%half spread%'
            OR wp.game_state->>'market_name' ILIKE '% points%'
            OR wp.game_state->>'market_name' ILIKE '% rebounds%'
            OR wp.game_state->>'market_name' ILIKE '% assists%'
            OR wp.game_state->>'market_name' ILIKE '% steals%'
            OR wp.game_state->>'market_name' ILIKE '% blocks%'
            OR wp.game_state->>'market_name' ILIKE '%three pointer%'
            OR wp.game_state->>'market_name' ILIKE '%double double%'
            OR wp.game_state->>'market_name' ILIKE '%triple double%'
            OR wp.game_state->>'market_name' ILIKE '%leader%'
            OR wp.game_state->>'market_name' ILIKE '%strikeout%'
            OR wp.game_state->>'market_name' ILIKE '%home run%'
        )
    )
"""


async def _query_futures_fair_fight_impl(db):
    """Paired MCE comparison for Kalshi vs Polymarket on futures markets.

    Rewrite (#197 fair-fight profile): the previous version built a 432K-row
    ``source_questions`` CTE, then SELF-JOINED it three ways (group_pairs,
    key_pairs, and a correlated NOT EXISTS). Because the CTE is referenced
    multiple times, Postgres MATERIALIZES it — so those self-joins run over an
    UN-INDEXED 432K-row spool and blow the soft limit (0 successes / 12 consec
    timeouts). Prod profiling (2026-07-14) proved two things:

      1. The ``group_id`` arm matches NOTHING and never can: kalshi group_ids are
         prefixed ``kalshi:...`` and polymarket ``polymarket:<event_id>`` — the
         namespaces are structurally disjoint (0 cross-source matches). The arm
         (and the NOT EXISTS that references it) was pure dead weight.
      2. The composite index the pairing wants already exists
         (``ix_fm_canonical_source_count (canonical_market_key, source) WHERE
         canonical_market_key IS NOT NULL``).

    So we drop the dead group arm and discover shared canonical keys with a
    single index-driven GROUP BY on the base table (measured ~0.3s vs the old
    self-join blowup). Output is identical to the old key arm (the group arm
    contributed nothing). Pair-discovery is now sub-second; the join to
    futures_outcomes is the only remaining cost.

    NOTE for maintainers: shared canonical keys are dominated by GENERIC bucket
    keys (e.g. ``basketball::championship:2026`` is shared by ~47K markets), so
    this pairs broad category buckets, not one-question-to-one-question. That is
    a pre-existing pairing-granularity concern for the fair-fight surface, not
    something this perf rewrite changes.
    """
    sql = text("""
        WITH key_pairs AS (
            -- Shared canonical keys covered by BOTH sources. Index-driven
            -- aggregation on the base table (ix_fm_canonical_source_count),
            -- replacing the materialized-CTE self-join. Category is taken from
            -- the kalshi side, matching the old sq1.category semantics.
            SELECT
                fm.canonical_market_key AS match_key,
                MIN(COALESCE(fm.llm_sport_category, 'uncategorized'))
                    FILTER (WHERE fm.source = 'kalshi') AS category
            FROM futures_markets fm
            WHERE fm.status = 'resolved'
              AND fm.source IN ('kalshi', 'polymarket')
              AND fm.canonical_market_key IS NOT NULL
            GROUP BY fm.canonical_market_key
            HAVING COUNT(*) FILTER (WHERE fm.source = 'kalshi') > 0
               AND COUNT(*) FILTER (WHERE fm.source = 'polymarket') > 0
        ),
        matched_outcomes AS (
            SELECT
                kp.category,
                fm.source,
                COALESCE(fo.calibration_probability, fo.opening_probability) AS prob,
                fo.is_winner
            FROM key_pairs kp
            JOIN futures_markets fm ON fm.canonical_market_key = kp.match_key
            JOIN futures_outcomes fo ON fo.market_id = fm.id
            WHERE fm.status = 'resolved'
              AND fm.source IN ('kalshi', 'polymarket')
              AND fo.opening_probability IS NOT NULL
              AND fo.opening_probability > 0 AND fo.opening_probability < 1
              -- Queue #262 Item 3: replace the legacy NOT-IN denylist with the
              -- single independent-truth allowlist (resolution_authority) so a
              -- price-derived (clean_resolution / settlement_sync), guess, void, or
              -- unknown winner can never grade a fair-fight row either. Read-side
              -- only (gotcha #21).
              AND fo.resolution_source IN """ + CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL + """
              -- Queue #267 (C44 #1): fair-fight has no downstream is_liquid gate, so
              -- the Kalshi evidence predicate IS its liquidity boundary here — the
              -- same contract as the headline (bid-bearing volume=0 kept, never-bid/
              -- never-traded phantoms excluded), replacing the volume proxy.
              AND """ + kalshi_liquidity_exists_sql(source="fm.source") + """
        )
        SELECT source, category, prob, is_winner
        FROM matched_outcomes
        WHERE prob IS NOT NULL AND prob > 0 AND prob < 1
        ORDER BY source, category
    """)
    result = await db.execute(sql)
    rows = result.all()

    by_cat: dict[str, dict[str, tuple[list[float], list[bool]]]] = {}
    for r in rows:
        cat = r.category
        src = r.source
        if cat not in by_cat:
            by_cat[cat] = {}
        if src not in by_cat[cat]:
            by_cat[cat][src] = ([], [])
        by_cat[cat][src][0].append(float(r.prob))
        by_cat[cat][src][1].append(bool(r.is_winner))

    all_kalshi_probs: list[float] = []
    all_kalshi_outcomes: list[bool] = []
    all_poly_probs: list[float] = []
    all_poly_outcomes: list[bool] = []
    by_category: list[dict] = []

    for cat, sources in sorted(by_cat.items()):
        k_data = sources.get("kalshi")
        p_data = sources.get("polymarket")
        if not k_data or not p_data:
            continue
        k_probs, k_wins = k_data
        p_probs, p_wins = p_data
        shared_n = min(len(k_probs), len(p_probs))
        if shared_n < 10:
            continue
        all_kalshi_probs.extend(k_probs)
        all_kalshi_outcomes.extend(k_wins)
        all_poly_probs.extend(p_probs)
        all_poly_outcomes.extend(p_wins)
        k_mce = _compute_mce(k_probs, k_wins)
        p_mce = _compute_mce(p_probs, p_wins)
        if k_mce is not None and p_mce is not None:
            by_category.append({
                "category": cat,
                "kalshi_n": len(k_probs),
                "polymarket_n": len(p_probs),
                "mce_kalshi": k_mce,
                "mce_polymarket": p_mce,
            })

    pairs = []
    # Queue #262 Item 3: min(row counts) is NOT a matched-market count, and the
    # canonical keys are dominated by generic category buckets (not one-question-
    # to-one-question), so NO winner/advantage is emitted — that claim would reflect
    # population + weighting, not source skill. The per-source MCEs stay as clearly-
    # labeled diagnostics with an explicit unavailable reason. min-count still gates
    # whether there is enough data to bother reporting the diagnostic.
    total_pooled = min(len(all_kalshi_probs), len(all_poly_probs))
    if total_pooled >= _MIN_SHARED:
        mce_k = _compute_mce(all_kalshi_probs, all_kalshi_outcomes)
        mce_p = _compute_mce(all_poly_probs, all_poly_outcomes)
        if mce_k is not None and mce_p is not None:
            pairs.append({
                "source_a": "kalshi",
                "source_b": "polymarket",
                "comparison_available": False,
                "reason": (
                    "canonical keys are generic category buckets, not "
                    "one-question-to-one-question matches; winner withheld"
                ),
                # honest per-source pooled counts — NOT a matched-market count.
                "kalshi_rows": len(all_kalshi_probs),
                "polymarket_rows": len(all_poly_probs),
                "mce_a": mce_k,
                "mce_b": mce_p,
                "by_category": [c for c in by_category if c["kalshi_n"] >= 20],
            })
    return pairs


async def _query_sports_fair_fight_impl(db):
    """Paired MCE comparison for prediction markets vs Odds API on sports events."""
    sql = text(f"""
        WITH wp_closing AS (
            SELECT DISTINCT ON (wp.event_id, wp.source)
                wp.event_id, wp.source, wp.home_win_probability
            FROM win_prob_snapshots wp
            JOIN events e ON e.id = wp.event_id
            WHERE e.status IN ('completed', 'closed')
              AND e.home_score IS NOT NULL AND e.away_score IS NOT NULL
              AND e.home_score != e.away_score
              AND wp.source IN ('kalshi', 'polymarket')
              AND wp.home_win_probability IS NOT NULL
              AND wp.home_win_probability > 0
              AND wp.home_win_probability < 1
              {_KALSHI_PROP_FILTER}
            ORDER BY wp.event_id, wp.source, wp.captured_at DESC
        )
        SELECT
            wc.event_id, wc.source AS pm_source,
            wc.home_win_probability AS pm_prob,
            COALESCE(e.closing_home_probability, e.opening_home_probability) AS odds_prob,
            (e.home_score > e.away_score) AS home_won,
            s.key AS sport
        FROM wp_closing wc
        JOIN events e ON e.id = wc.event_id
        JOIN sports s ON s.id = e.sport_id
        WHERE COALESCE(e.closing_home_probability, e.opening_home_probability) IS NOT NULL
          AND COALESCE(e.closing_home_probability, e.opening_home_probability) > 0
          AND COALESCE(e.closing_home_probability, e.opening_home_probability) < 1
        ORDER BY wc.source, s.key
    """)
    result = await db.execute(sql)
    rows = result.all()

    by_src: dict[str, dict[str, dict]] = {}
    for r in rows:
        src = r.pm_source
        sport = r.sport
        if src not in by_src:
            by_src[src] = {}
        if sport not in by_src[src]:
            by_src[src][sport] = {
                "pm_probs": [], "pm_outcomes": [],
                "odds_probs": [], "odds_outcomes": [],
            }
        won = bool(r.home_won)
        by_src[src][sport]["pm_probs"].append(float(r.pm_prob))
        by_src[src][sport]["pm_outcomes"].append(won)
        by_src[src][sport]["odds_probs"].append(float(r.odds_prob))
        by_src[src][sport]["odds_outcomes"].append(won)

    pairs = []
    for pm_source, sports_data in sorted(by_src.items()):
        all_pm_probs: list[float] = []
        all_pm_outcomes: list[bool] = []
        all_odds_probs: list[float] = []
        all_odds_outcomes: list[bool] = []
        by_sport: list[dict] = []

        for sport, data in sorted(sports_data.items()):
            n = len(data["pm_probs"])
            if n < 10:
                continue
            all_pm_probs.extend(data["pm_probs"])
            all_pm_outcomes.extend(data["pm_outcomes"])
            all_odds_probs.extend(data["odds_probs"])
            all_odds_outcomes.extend(data["odds_outcomes"])
            mce_pm = _compute_mce(data["pm_probs"], data["pm_outcomes"])
            mce_odds = _compute_mce(data["odds_probs"], data["odds_outcomes"])
            if mce_pm is not None and mce_odds is not None:
                by_sport.append({
                    "category": sport,
                    f"{pm_source}_n": n,
                    "odds_api_n": n,
                    f"mce_{pm_source}": mce_pm,
                    "mce_odds_api": mce_odds,
                })

        total = len(all_pm_probs)
        if total >= _MIN_SHARED:
            mce_pm = _compute_mce(all_pm_probs, all_pm_outcomes)
            mce_odds = _compute_mce(all_odds_probs, all_odds_outcomes)
            if mce_pm is not None and mce_odds is not None:
                # Queue #262 Item 3: these ARE per-event matched questions (same
                # game), so matched_questions is honest — but the MCE here is
                # equal-per-bucket, NOT the outcome-weighted headline metric, so a
                # winner would use a metric different from the headline definition.
                # Winner withheld until the comparison reuses the headline metric
                # (deliberately NOT rebuilt in this containment queue).
                pairs.append({
                    "source_a": pm_source,
                    "source_b": "odds_api",
                    "comparison_available": False,
                    "reason": (
                        "MCE is equal-per-bucket, not the outcome-weighted headline "
                        "metric; winner withheld"
                    ),
                    "matched_questions": total,
                    "mce_a": mce_pm,
                    "mce_b": mce_odds,
                    "by_category": [s for s in by_sport if s.get(f"{pm_source}_n", 0) >= 20],
                })
    return pairs


async def _compute_fair_fight_comparison():
    """Compute fair-fight comparison and store in Redis."""
    from app.tasks.base import get_task_session
    from app.tasks.redis_state import get_redis_client

    # Each MCE query runs in its OWN session with a per-statement timeout. The
    # task was tripping its 600s soft limit (SoftTimeLimitExceeded, consec 12):
    # the heavy paired-coverage scans ran away, and a shared session meant one
    # aborted transaction poisoned the other query's commit-on-exit. Own-session
    # + 240s statement_timeout bounds each scan well under the soft limit and
    # isolates failures so a slow half degrades to [] instead of failing the
    # whole task (advisory Redis surface — partial > red).
    from app.tasks.calibration_main_build import tag_scheduled_session

    async def _run_bounded(impl, label):
        try:
            async with get_task_session() as db:
                await db.execute(text("SET LOCAL statement_timeout = '240s'"))
                # Queue 300B Item 1: paired with the timeout, same lifetime.
                await tag_scheduled_session(
                    db, task=f"fair_fight_comparison.{label}"
                )
                return await impl(db)
        except Exception:
            logger.exception("fair-fight precompute: %s query failed", label)
            return []

    futures_pairs = await _run_bounded(_query_futures_fair_fight_impl, "futures")
    sports_pairs = await _run_bounded(_query_sports_fair_fight_impl, "sports")

    response = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        # Queue #262 Item 3: the winner claim is CONTAINED. A source winner is only
        # meaningful when both sources are scored on the SAME one-question-to-one-
        # question set with the headline metric. The futures pairing is generic
        # canonical-key buckets (not question-paired) and both paths use a
        # non-headline equal-per-bucket MCE, so no winner/advantage is emitted —
        # only clearly-labeled diagnostic MCEs. Callers must treat this surface as
        # comparison-unavailable until an exact matched-question rebuild lands.
        "comparison_available": False,
        "unavailable_reason": (
            "Source winner withheld: fair-fight is not yet one-question-to-one-"
            "question with the headline metric (Queue #262 Item 3 containment)."
        ),
        "population_version": CALIBRATION_POPULATION_VERSION,
        "methodology": (
            "Diagnostic per-source MCE only. Winner/advantage are intentionally "
            "absent: the futures pairing groups generic canonical-key buckets (not "
            "matched questions), and the MCE is equal-per-bucket, not the outcome-"
            "weighted headline metric. Do not present these numbers as a source "
            "ranking."
        ),
        "min_shared_threshold": _MIN_SHARED,
        "pairs": futures_pairs + sports_pairs,
    }

    rc = get_redis_client()
    rc.set("bainluck:calibration:fair_fight", json.dumps(response), ex=_CACHE_TTL)
    logger.info("Cached fair-fight comparison in Redis")
    return {"status": "ok", "pairs": len(futures_pairs) + len(sports_pairs)}


#: Half-open id window per chunk of the coverage sweep. Sized so ONE statement
#: — the per-outcome LATERAL snapshot count, which is what actually costs — has
#: to finish well inside :data:`_COVERAGE_CHUNK_TIMEOUT_MS`, rather than sized
#: to "feels small". Bounding the loop was never the problem; bounding the
#: single longest uninterrupted op is (the budget-guard-inner-op lesson).
_COVERAGE_CHUNK_IDS = 50_000
_COVERAGE_CHUNK_TIMEOUT_MS = 45_000
#: soft_time_limit=600 on the task; stop planning new chunks with room to spare
#: for the final publish + checkpoint write.
_COVERAGE_DEADLINE_S = 480.0
_COVERAGE_TASK = "coverage_metrics"


def _merge_coverage_groups(
    accumulator: dict[str, Any], rows: list[Any]
) -> dict[str, Any]:
    """Fold one chunk's GROUP BY result into the running accumulator.

    Counts sum. ``avg_snapshots`` cannot be averaged across chunks, so the
    accumulator carries ``snap_sum``/``snap_n`` and the average is derived once
    at publication — averaging the per-chunk averages would silently weight a
    500-outcome chunk the same as a 50,000-outcome one.
    """
    merged = dict(accumulator)
    for r in rows:
        key = f"{r.source}\x1f{r.age_bucket}\x1f{r.league or 'unknown'}"
        cell = merged.get(key) or {
            "source": r.source,
            "age": r.age_bucket,
            "league": r.league or "unknown",
            "total": 0,
            "has_opening": 0,
            "has_cal_prob": 0,
            "has_winner": 0,
            "snap_sum": 0,
            "snap_n": 0,
        }
        cell["total"] += int(r.total_resolved or 0)
        cell["has_opening"] += int(r.has_opening or 0)
        cell["has_cal_prob"] += int(r.has_cal_prob or 0)
        cell["has_winner"] += int(r.has_winner or 0)
        cell["snap_sum"] += int(r.snap_sum or 0)
        cell["snap_n"] += int(r.snap_n or 0)
        merged[key] = cell
    return merged


def _coverage_snapshot_from(accumulator: dict[str, Any]) -> dict:
    """Build the published snapshot from a COMPLETE accumulator.

    Same shape the single-statement version emitted — the sweep changed, the
    metric did not.
    """
    from collections import defaultdict

    cells = sorted(
        accumulator.values(),
        key=lambda c: (c["source"] or "", c["age"] or "", -c["total"]),
    )
    snapshot = {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "by_source_age_league": [
            {
                "source": c["source"],
                "age": c["age"],
                "league": c["league"],
                "total": c["total"],
                "has_opening": c["has_opening"],
                "has_cal_prob": c["has_cal_prob"],
                "has_winner": c["has_winner"],
                "avg_snapshots": int(c["snap_sum"] / c["snap_n"]) if c["snap_n"] else 0,
            }
            for c in cells
        ],
        "totals": {},
    }

    by_source = defaultdict(lambda: {"total": 0, "opening": 0, "cal_prob": 0, "winner": 0})
    for c in cells:
        by_source[c["source"]]["total"] += c["total"]
        by_source[c["source"]]["opening"] += c["has_opening"]
        by_source[c["source"]]["cal_prob"] += c["has_cal_prob"]
        by_source[c["source"]]["winner"] += c["has_winner"]

    snapshot["totals"] = {
        src: {
            "total": s["total"],
            "opening_pct": round(100 * s["opening"] / max(s["total"], 1), 1),
            "cal_prob_pct": round(100 * s["cal_prob"] / max(s["total"], 1), 1),
            "winner_pct": round(100 * s["winner"] / max(s["total"], 1), 1),
        }
        for src, s in by_source.items()
    }
    return snapshot


_COVERAGE_CHUNK_SQL = text("""
    SELECT
        fm.source,
        CASE
            WHEN fm.resolution_date >= NOW() - INTERVAL '7 days' THEN '7d'
            WHEN fm.resolution_date >= NOW() - INTERVAL '30 days' THEN '30d'
            ELSE '90d+'
        END AS age_bucket,
        s.key AS league,
        COUNT(*) AS total_resolved,
        COUNT(fo.opening_probability) AS has_opening,
        COUNT(fo.calibration_probability) AS has_cal_prob,
        COUNT(CASE WHEN fo.is_winner IS NOT NULL THEN 1 END) AS has_winner,
        SUM(COALESCE(snap_counts.cnt, 0)) AS snap_sum,
        COUNT(*) AS snap_n
    FROM futures_outcomes fo
    JOIN futures_markets fm ON fo.market_id = fm.id
    LEFT JOIN sports s ON s.id = fm.sport_id
    LEFT JOIN LATERAL (
        SELECT COUNT(*) AS cnt
        FROM futures_odds_snapshots fos
        WHERE fos.outcome_id = fo.id
    ) snap_counts ON true
    WHERE fo.id >= :start AND fo.id < :end
      AND fm.status = 'resolved'
      AND fm.resolution_date IS NOT NULL
    GROUP BY fm.source, age_bucket, s.key
""")
# NOTE (#1199): the backfill-winners/status cache (key
# `bainluck:backfill_winners_status`) used to be piggybacked onto this task as a
# second heavy `market_status` CTE. That block was removed — the dedicated
# `precompute_backfill_winners_status` task owns that key, runs HOURLY at :35
# with a 2h TTL, and writes the exact same shape. Running the CTE again here was
# pure duplicate compute and was the second heavy query pushing this snapshot
# over its soft_time_limit. Do NOT re-add it here.


async def _snapshot_coverage_metrics():
    """Daily snapshot of coverage metrics for tracking progress over time.

    Captures opening_probability, is_winner, and calibration_probability
    coverage per source, age window, and league, so we can answer "is coverage
    improving?" without re-running heavy queries.

    Queue 300 (#1513) — resumability. This was ONE statement: a per-outcome
    ``LATERAL`` count over ``futures_odds_snapshots`` across every resolved
    outcome. It had grown past the 600s soft limit, and because it was a single
    statement there was no partial credit — every run lost 100% of its work.
    Production at the time of the rewrite: ``coverage_metrics`` had **7
    consecutive failures, 0 successes in 24h, health=critical**, every one of
    them ``SoftTimeLimitExceeded`` at ~600s. The daily coverage rail had simply
    been dark, while the beat kept firing and the task kept "running".

    Now it is a stable ascending sweep over ``futures_outcomes.id`` in bounded
    chunks, each with its own ``statement_timeout``, each folded into a
    checkpoint that is written to the DURABLE store only after its chunk's read
    committed. Consequences that matter:

    * A soft limit stops the sweep where it is. The next beat resumes at the
      cursor instead of starting over — monotonic progress across beats.
    * Ascending id order means the oldest outcomes are reached FIRST, so a
      bounded run can never be pinned to the head (gotcha #41).
    * A chunk that times out twice is recorded by id range and the sweep
      continues past it; the healthy siblings survive (gotcha #42) but the run
      terminates ``partial`` and **does not publish**, because a snapshot with a
      hole in it is not a coverage snapshot.
    * Only a sweep that reaches the end of the population with no failed chunk
      publishes anything. Partial progress cannot masquerade as a complete
      artifact, which is the whole point of the C118 contract this conforms to.
    """
    import time as _cov_time

    from app.tasks.base import get_task_session
    from app.tasks.redis_state import get_redis_client
    from app.tasks.task_checkpoint import (
        clear_checkpoint,
        load_checkpoint,
        release_overlap_lock,
        save_checkpoint,
        try_acquire_overlap_lock,
    )
    from app.utils.task_resumability import (
        COMPLETE,
        apply_chunk,
        contract_row,
        may_publish,
        plan_chunks,
        terminal_state,
    )

    started = _cov_time.monotonic()
    stats: dict[str, Any] = {
        "snapshots": 0,
        "errors": [],
        "terminal": "failed",
        "chunks_this_run": 0,
        "cursor_before": 0,
        "cursor_after": 0,
        "failed_chunks": [],
        "published": False,
        "ownership": "denied",
        "version_action": "fresh",
    }

    def _remaining() -> float:
        return _COVERAGE_DEADLINE_S - (_cov_time.monotonic() - started)

    checkpoint, action = await load_checkpoint(
        _COVERAGE_TASK, CALIBRATION_POPULATION_VERSION
    )
    stats["version_action"] = "invalidate" if action == "invalidate" else "reuse"
    stats["cursor_before"] = checkpoint.cursor
    stats["cursor_after"] = checkpoint.cursor
    durable_ok = False
    interrupted = False
    exhausted = False
    last_chunk = None
    last_committed = False
    rows_this_run = 0

    try:
        from app.tasks.calibration_main_build import tag_scheduled_session

        async with get_task_session() as session:
            # Queue 300B Item 1: before the lock, so even a session stuck WAITING
            # on the advisory lock identifies itself.
            await tag_scheduled_session(session, task=_COVERAGE_TASK)

            if not await try_acquire_overlap_lock(session, _COVERAGE_TASK):
                # Another beat owns the sweep. Doing nothing is the correct
                # behaviour; running a second sweep against the same cursor is
                # how duplicate work becomes double-counted coverage.
                stats["terminal"] = "partial"
                stats["skipped"] = "overlap_lock_not_acquired"
                logger.info("Coverage snapshot: another run holds the lock — skipping")
                return stats
            stats["ownership"] = "acquired"

            upper = (
                await session.execute(
                    text("SELECT COALESCE(MAX(id), 0) + 1 FROM futures_outcomes")
                )
            ).scalar() or 1

            for chunk in plan_chunks(
                cursor=checkpoint.cursor,
                upper_bound=int(upper),
                chunk_size=_COVERAGE_CHUNK_IDS,
            ):
                if _remaining() <= 0:
                    interrupted = True
                    break

                rows = None
                failed = False
                for attempt in (1, 2):
                    try:
                        await session.execute(
                            text(
                                f"SET LOCAL statement_timeout = {_COVERAGE_CHUNK_TIMEOUT_MS}"
                            )
                        )
                        result = await session.execute(
                            _COVERAGE_CHUNK_SQL, {"start": chunk.start, "end": chunk.end}
                        )
                        rows = result.fetchall()
                        await session.commit()
                        break
                    except Exception as exc:  # noqa: BLE001 — poison containment
                        await session.rollback()
                        if attempt == 2:
                            failed = True
                            stats["failed_chunks"].append(chunk.id)
                            stats["errors"].append(f"{chunk.id}: {str(exc)[:120]}")
                            logger.warning(
                                "Coverage snapshot: chunk %s failed twice (%s) — "
                                "continuing so the rest of the sweep survives",
                                chunk.id,
                                str(exc)[:120],
                            )

                last_chunk = chunk
                last_committed = not failed
                if failed:
                    checkpoint = apply_chunk(checkpoint, chunk, committed=False, failed=True)
                else:
                    rows_this_run += len(rows or [])
                    checkpoint = apply_chunk(
                        checkpoint,
                        chunk,
                        committed=True,
                        rows_committed=len(rows or []),
                        accumulator=_merge_coverage_groups(
                            checkpoint.accumulator, rows or []
                        ),
                    )
                stats["chunks_this_run"] += 1
                stats["cursor_after"] = checkpoint.cursor

                # The cursor is persisted only AFTER the chunk's read committed.
                durable_ok = await save_checkpoint(
                    _COVERAGE_TASK,
                    checkpoint,
                    terminal="partial",
                    extra={"upper_bound": int(upper)},
                )
            else:
                exhausted = checkpoint.cursor >= int(upper)

            stats["terminal"] = terminal_state(
                exhausted=exhausted,
                failed_chunks=checkpoint.failed_chunks,
                interrupted=interrupted,
            )

            if may_publish(
                terminal=stats["terminal"],
                durable_generation_committed=durable_ok or not stats["chunks_this_run"],
                interrupted=interrupted,
            ):
                snapshot = _coverage_snapshot_from(checkpoint.accumulator)
                rc = get_redis_client()
                rc.hset(
                    "bainluck:coverage_snapshots",
                    snapshot["date"],
                    json.dumps(snapshot),
                )
                rc.expire("bainluck:coverage_snapshots", 90 * 86400)
                stats["snapshots"] = len(snapshot["by_source_age_league"])
                stats["published"] = True
                await clear_checkpoint(_COVERAGE_TASK, CALIBRATION_POPULATION_VERSION)
                logger.info(
                    "Coverage snapshot: %s — %s",
                    snapshot["date"],
                    {
                        src: f'{s["cal_prob_pct"]}% cal_prob'
                        for src, s in snapshot["totals"].items()
                    },
                )
            else:
                logger.info(
                    "Coverage snapshot: %s at cursor %d/%d (%d chunks this run, "
                    "%d failed) — not publishing a partial artifact",
                    stats["terminal"],
                    checkpoint.cursor,
                    int(upper),
                    stats["chunks_this_run"],
                    len(checkpoint.failed_chunks),
                )

            await release_overlap_lock(session, _COVERAGE_TASK)

    except Exception as e:
        stats["errors"].append(str(e)[:200])
        stats["terminal"] = "failed"
        logger.error("Coverage snapshot error: %s", e)

    if last_chunk is not None:
        stats["contract"] = contract_row(
            task=_COVERAGE_TASK,
            population_version=CALIBRATION_POPULATION_VERSION,
            checkpoint_version=CALIBRATION_POPULATION_VERSION,
            version_action=stats["version_action"],
            cursor_before=last_chunk.start,
            chunk=last_chunk,
            committed=last_committed,
            rows_attempted=last_chunk.end - last_chunk.start,
            rows_committed=last_chunk.end - last_chunk.start if last_committed else 0,
            rows_failed=0 if last_committed else last_chunk.end - last_chunk.start,
            interruption="soft_after_commit" if interrupted else "none",
            ownership=stats["ownership"],
            terminal=stats["terminal"],
            published=stats["published"],
            durable_generation_committed=durable_ok,
            all_phases_complete=stats["terminal"] == COMPLETE,
            metrics_available=True,
            checked=rows_this_run,
            healthy_siblings_survive=True,
        )
    stats["elapsed_s"] = round(_cov_time.monotonic() - started, 1)
    return stats


