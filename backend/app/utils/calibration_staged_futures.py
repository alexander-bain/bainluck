"""Pure staging + global finalization for the futures population (Queue 300D).

C126 committed the ORACLE for this behaviour
(``scripts/evals/futures_population_subdivision_contract.py`` + its 44-case
corpus). That evaluator grades a *plan/monolith/staged/lifecycle* row; nothing
in the codebase could produce one, because the futures population is still ONE
statement. This module is the pure half of the subdivision: how the population
is cut into units, how the pieces are put back together, and what a cursor is
allowed to claim about work a previous beat did.

The runtime half (the Stage A roster query, the per-chunk Stage B statement,
durable persistence, the lease) lives in ``app.tasks.precompute_calibration`` /
``app.tasks.calibration_main_build``. Everything here is I/O-free — no DB, no
Redis, no clock except values passed in — so the rules stay testable without
either.

Why this exists at all: the ``futures`` phase is a single ~22-minute read
against a ~23-minute deadline (the phase ledger's own floors: 1,351,697 /
1,351,955 / 1,299,533 ms against a 1,380,000 ms window). There is no partial
credit — the last recorded beat was CANCELLED at 1,299,533 ms with nothing
committed and nothing published, which is why ``/api/calibration`` served a
26h-stale copy while the beat "ran" every hour. Queue 300M made the phase
*measurable*; Queue 300D makes it *resumable*, by cutting it into units that can
each finish inside one beat and be banked.

The three stages, and the one fact that makes them safe:

* **Stage A — the roster.** Once per beat, a cheap query returns one row per
  eligible futures market: ``(market_id, source, vm_id, is_grouped)``. That
  roster IS the generation. :func:`generation_fingerprint` digests it, and any
  change to it mid-build invalidates every banked unit
  (``LATE_ARRIVAL_NOT_INVALIDATED``): half the buckets computed against
  yesterday's roster and half against today's is not a population, it is a
  blend of two.
* **Stage B — one chunk.** The heavy population statement runs restricted to
  one chunk of WHOLE ``vm_id``s, and returns that chunk's bucket rows.
* **Stage C — global finalization.** :func:`merge_futures_rows` folds every
  chunk's rows into one list byte-compatible with the monolith's
  (``GLOBAL_FINALIZATION_MISSING``). Nothing publishes until every planned
  chunk is in (``PARTIAL_GENERATION_PUBLISHED``).

The subtlest fact in this module, stated once here and again on
:func:`plan_units`: **the unit is ``vm_id``, WITHOUT source.** The population's
``mode_prices`` CTE groups by ``vm_id`` alone, and the representative window is
``ROW_NUMBER() OVER (PARTITION BY cv.vm_id ORDER BY ...)`` — also ``vm_id``
alone. So two sources that share one virtual question (``e:123`` present on both
Kalshi and Polymarket) are PEERS: they vote in the same mode-price election and
compete for the same representative row. Splitting them across chunks changes
which row wins and which prices count as a mode — a silent semantic change, and
exactly the ``CROSS_CHUNK_PEER_SPLIT`` / ``FIELD_ROSTER_SPLIT`` refusals the
corpus grades. Chunking by ``(vm_id, source)`` would look more balanced and
would be wrong.

What this module deliberately does NOT do: change any population semantics. The
filters, the normalization, the bucket assignment and the thresholds are the
SQL's business and are untouched (``SEMANTIC_CHANGE_NEEDS_ALEX_RULING``). Where
something is genuinely undetermined — an undeclared column, an oversized unit, a
census a chunk never reported — this module takes the refusing branch and says
so, rather than guessing.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, Iterable, Optional, Sequence

from app.utils.calibration_phase_ledger import (
    FRESH,
    INVALIDATE,
    MAIN_BUILD_TASK,
    REFUSE,
    RESUME,
    TERMINAL_PARTIAL,
    input_fingerprint,
)

__all__ = [
    "ADDITIVE_COLUMNS",
    "AVG_PROB_COLUMN",
    "DEFAULT_CENSUS_COLUMNS",
    "DISTINCT_CENSUS_COLUMNS",
    "GROUP_KEY_COLUMNS",
    "INTEGER_ADDITIVE_COLUMNS",
    "STAGED_FUTURES_SCHEMA",
    "UNIT_KEY_VM_ID",
    "StagedFuturesCursor",
    "UnitChunk",
    "advance",
    "bucket_of",
    "can_advance",
    "collect_unit_results",
    "decode_staged_cursor",
    "decode_staged_cursor_detailed",
    "generation_fingerprint",
    "is_complete",
    "merge_futures_rows",
    "new_staged_cursor",
    "plan_units",
    "retain_planned_units",
    "unit_key",
]

#: The partition key. Named, because ``UNSAFE_PARTITION_KEY`` in the C126
#: corpus accepts exactly two: ``source`` and ``virtual_question``. This is the
#: latter.
UNIT_KEY_VM_ID = "vm_id"

STAGED_FUTURES_SCHEMA = "calibration-staged-futures/v1"

# --- Why a cursor was not resumed (CAL-P024) ---------------------------------
#
# Short stable tokens, deliberately not prose: they are recorded on every beat
# and the question worth asking is never "why did this one reset" but "which
# cause resets us every time". Five of them used to be one indistinguishable
# ``staged:cursor_invalidate``.
REASON_ABSENT = "absent"
REASON_MALFORMED = "malformed"
REASON_SCHEMA = "schema_mismatch"
REASON_TASK = "task_mismatch"
REASON_UNIT_KEY = "unit_key_mismatch"
REASON_POPULATION_VERSION = "population_version_changed"
#: A deploy touching any SQL function hashed by ``_main_input_fingerprint``.
REASON_INPUT_FINGERPRINT = "input_fingerprint_changed"
REASON_MALFORMED_UNITS = "malformed_units"
REASON_LEASE_HELD = "lease_held_by_other"
#: The snapshot read itself threw — an unreadable cursor is a fresh one.
REASON_READ_FAILED = "read_failed"
REASON_RESUMABLE = "resumable"
REASON_NOTHING_BANKED = "nothing_banked"

# --- The row shape Stage B returns and Stage C merges -------------------------
#
# Read off the production SELECT list in ``precompute_calibration``'s futures
# query (its GROUP BY / ORDER BY are the same five columns, in this order).

#: ``GROUP BY bucket_idx, source, category, price_moved, is_nonexclusive_bundle``
#: — and the identical ``ORDER BY``. Rows sharing this key merge into one.
GROUP_KEY_COLUMNS: tuple[str, ...] = (
    "bucket_idx",
    "source",
    "category",
    "price_moved",
    "is_nonexclusive_bundle",
)

#: The bucket mass. Summed across chunks; each is a plain per-group aggregate,
#: so summing partial groups is exact for the integers and associative-modulo-
#: floating-point for the two doubles (see :func:`merge_futures_rows`).
ADDITIVE_COLUMNS: tuple[str, ...] = ("n", "winners", "sum_prob", "sum_sq_err")

#: Counts, not masses. Kept integral so a merged row is indistinguishable from
#: a monolith row on type as well as value.
INTEGER_ADDITIVE_COLUMNS = frozenset({"n", "winners"})

#: Derived, never summed. See :func:`merge_futures_rows`.
AVG_PROB_COLUMN = "avg_prob"

#: The ``MAX(...)`` passthrough columns: constant across every returned row in
#: the monolith because they are CROSS JOINed off 1-row summaries
#: (``liq_summary`` over ``normalized``, ``published_summary`` over ``deduped``),
#: and read by the consumer off ``rows[0]`` ONLY.
#:
#: This list mirrors the statement as of Queue 300D. The coverage-bridge census
#: (``cb_*``, gated behind ``COVERAGE_CENSUS_ENABLED``) is deliberately absent:
#: its column set is built at runtime from the rung keys, so the caller appends
#: it when the switch is on. Every column a chunk returns must be declared —
#: :func:`merge_futures_rows` refuses rather than silently dropping one.
DEFAULT_CENSUS_COLUMNS: tuple[str, ...] = (
    "kalshi_included",
    "kalshi_excluded",
    "poly_placeholder_excluded",
    "poly_included",
    "poly_never_traded_total",
    "poly_never_traded_in_curve",
    "both_false_excluded",
    "both_winner_excluded",
    "golf_placeholder_excluded",
    "mex_normalized_outcomes",
    "mex_candidate_markets",
    "mex_normalized_markets",
    "field_incomplete_markets",
    "field_incomplete_outcomes",
    "esports_bundle_excluded",
    "no_winner_excluded",
    "no_winner_markets",
    "draw_authority_excluded",
    "draw_authority_markets",
    "orphan_partition_excluded",
    "orphan_partition_markets",
    "nonexclusive_bundle_candidates",
    "nonexclusive_bundle_markets",
    "kalshi_prop_threshold_excluded",
    "weather_wide_spread_excluded",
    "mex_published_markets",
    "mex_published_outcomes",
    "published_outcomes",
    "published_questions",
)

#: The census columns that are ``COUNT(DISTINCT ...)`` rather than ``COUNT(*)``.
#:
#: These sum across chunks correctly ONLY because a market — and therefore its
#: ``vm_id`` — never straddles a chunk boundary. ``COUNT(DISTINCT market_id)``
#: is additive over a partition of markets; ``COUNT(DISTINCT vm_id)``
#: (``published_questions``) is additive over a partition of virtual questions.
#: Chunk by ``(vm_id, source)`` instead and a two-source question is counted
#: twice — the census silently inflates and nothing else changes, which is the
#: worst kind of wrong. :func:`plan_units` is what guarantees the partition;
#: this constant is the dependency written down.
DISTINCT_CENSUS_COLUMNS = frozenset(
    {
        "mex_candidate_markets",
        "mex_normalized_markets",
        "field_incomplete_markets",
        "no_winner_markets",
        "draw_authority_markets",
        "orphan_partition_markets",
        "nonexclusive_bundle_markets",
        "mex_published_markets",
        "published_questions",
    }
)


# =============================================================================
# Row access
# =============================================================================


def _row_mapping(row: Any) -> Mapping[str, Any]:
    """Column name -> value for a SQLAlchemy ``Row``, namespace, or mapping.

    Stage B's rows come back as SQLAlchemy ``Row`` objects in production and as
    ``SimpleNamespace`` in tests and after a checkpoint round-trip
    (``calibration_main_build.decode_rows``). Both are attribute-access, and
    both must merge identically.
    """
    mapping = getattr(row, "_mapping", None)
    if mapping is not None:
        return mapping
    if isinstance(row, Mapping):
        return row
    data = getattr(row, "__dict__", None)
    if isinstance(data, dict):
        return data
    fields = getattr(row, "_fields", None)
    if fields:
        return {name: getattr(row, name) for name in fields}
    raise TypeError(f"cannot read columns off a {type(row).__name__}")


def _get(row: Any, name: str, default: Any = None) -> Any:
    mapping = getattr(row, "_mapping", None)
    if mapping is not None:
        return mapping.get(name, default) if hasattr(mapping, "get") else default
    if isinstance(row, Mapping):
        return row.get(name, default)
    return getattr(row, name, default)


def _as_float(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _as_int(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, Decimal):
        return int(value)
    return int(value)


def _order_key(value: Any) -> tuple[int, int, float, str]:
    """None-safe ordering that mirrors ``ORDER BY <col>`` in Postgres.

    ``category`` and ``source`` are genuinely NULLable in the population, and
    Postgres's ASC default sorts NULLs LAST — so ``None`` sorts last here too,
    and never raises a ``TypeError`` mid-finalization.

    Not exactly Postgres: text ordering here is codepoint order, while Postgres
    uses the database collation. For the values these columns actually carry
    (lowercase ASCII source and category slugs) the two agree; for anything else
    they could differ, and that is stated rather than papered over.
    """
    if value is None:
        return (1, 0, 0.0, "")
    if isinstance(value, bool):
        return (0, 0, float(value), "")
    if isinstance(value, (int, float, Decimal)):
        return (0, 0, float(value), "")
    return (0, 1, 0.0, str(value))


# =============================================================================
# Stage A — the generation
# =============================================================================


def generation_fingerprint(rows: Iterable[Any]) -> str:
    """Stable digest of the Stage A roster: what this generation is ABOUT.

    Computed over sorted ``(market_id, source, vm_id, is_grouped)`` tuples, so
    it is independent of the order the roster query happens to return and
    identical for two beats that see the same population.

    This is the late-arrival detector. A market that resolves (or a group that
    crosses the ``>= 3`` threshold and changes a ``vm_id``) between Stage A and
    the last chunk moves this digest, every banked unit is invalidated, and the
    build restarts against one coherent roster. Mixing a chunk computed against
    the old roster with a chunk computed against the new one is
    ``LATE_ARRIVAL_NOT_INVALIDATED``: the merged census would count questions
    that no longer exist alongside buckets that did not exist when the census
    was taken.

    ``is_grouped`` is part of the digest even though it never affects chunking —
    it changes the population's ``is_multi`` branch, so a flip is a different
    build even when the roster's membership is identical.
    """
    parts = sorted(
        "\x1e".join(
            (
                str(_get(row, "market_id", "")),
                _text(_get(row, "source")),
                _text(_get(row, UNIT_KEY_VM_ID)),
                _flag(_get(row, "is_grouped")),
            )
        )
        for row in rows
    )
    return input_fingerprint(STAGED_FUTURES_SCHEMA, UNIT_KEY_VM_ID, *parts)


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _flag(value: Any) -> str:
    if value is None:
        return ""
    return "1" if value else "0"


# =============================================================================
# Stage B — the plan
# =============================================================================


def bucket_of(vm_id: Any, buckets: int) -> int:
    """Which unit a ``vm_id`` belongs to — from the ``vm_id`` ALONE.

    CAL-P016. This is the whole convergence fix in one function. The unit a
    question lands in is a property of that question and nothing else, so a
    market resolving into the population cannot move any OTHER question between
    units. Contrast the positional accumulator this replaced, where one new
    ``vm_id`` early in sort order pushed every later boundary along and changed
    every downstream unit key — which invalidated the entire cursor by a second
    route even after the key itself was made per-unit.

    SHA-256 rather than :func:`hash`: the bucket must be identical in the next
    beat, in another dyno, and after a deploy. ``PYTHONHASHSEED`` is randomised
    per process, so the builtin would re-partition the population on every
    restart — silently, and only in production.
    """
    if not isinstance(buckets, int) or isinstance(buckets, bool):
        raise ValueError("buckets must be an int")
    if buckets < 1:
        raise ValueError("buckets must be >= 1")
    digest = hashlib.sha256(str(vm_id).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % buckets


@dataclass(frozen=True)
class UnitChunk:
    """One Stage B unit: whole virtual questions and the markets inside them."""

    index: int
    vm_ids: tuple[str, ...]
    market_ids: tuple[int, ...]
    #: Sorted ``(market_id, source, vm_id, is_grouped)`` roster tuples for THIS
    #: unit's markets — the same tuple :func:`generation_fingerprint` digests
    #: globally, scoped to the unit. Defaulted so a hand-built chunk in a test
    #: stays valid; the planner always fills it.
    members: tuple[str, ...] = ()

    @property
    def key(self) -> str:
        """Short stable digest of everything this chunk is ABOUT.

        A cursor entry names a chunk by this key rather than by index, so a
        banked unit can be VALIDATED against the chunk it claims: change what
        the unit contains and the key moves, and a stale unit simply stops
        matching any planned chunk instead of being silently mapped onto
        whatever now sits at index 3.

        CAL-P016 widened this from the ``vm_id`` set to the unit's full roster
        MEMBERSHIP. Digesting only ``vm_id``s left the inverse hole to the
        boundary-shift one: a market resolving INTO an existing ``vm_id`` left
        the key unchanged while making the banked rows stale, so a unit computed
        without that market would have been resumed as though it were current.
        ``vm_ids`` and ``market_ids`` stay in the digest so a chunk constructed
        without ``members`` is still distinguished rather than colliding.
        """
        parts = (
            [f"vm:{vm}" for vm in self.vm_ids]
            + [f"mk:{market}" for market in self.market_ids]
            + [f"mb:{member}" for member in self.members]
        )
        return input_fingerprint(UNIT_KEY_VM_ID, *parts)[:16]

    @property
    def market_count(self) -> int:
        return len(self.market_ids)

    def as_payload(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "key": self.key,
            "vm_ids": list(self.vm_ids),
            "market_ids": list(self.market_ids),
            "market_count": self.market_count,
        }


def plan_units(rows: Iterable[Any], *, buckets: int) -> tuple[UnitChunk, ...]:
    """Cut the Stage A roster into chunks of WHOLE virtual questions.

    **A ``vm_id`` is never split.** The population keys two things on ``vm_id``
    without source — the ``mode_prices`` CTE (``GROUP BY vm_id,
    adj_opening_probability, eligible``) and the representative window
    (``ROW_NUMBER() OVER (PARTITION BY cv.vm_id ...)``) — so every market
    sharing a ``vm_id`` is a peer of every other, ACROSS sources. ``e:123`` on
    Kalshi and ``e:123`` on Polymarket vote in the same mode-price election and
    compete for the same ``rn = 1`` representative. Put them in different chunks
    and each chunk elects its own representative and detects its own modes:
    ``CROSS_CHUNK_PEER_SPLIT`` and ``FIELD_ROSTER_SPLIT``, and the merged output
    is quietly not the monolith's. The same argument covers a normalized field:
    completeness is a per-market property, and a market lives in exactly one
    ``vm_id``, so keeping ``vm_id``s whole keeps fields whole.

    Deterministic by construction: a ``vm_id``'s unit is :func:`bucket_of` that
    ``vm_id``, so the same roster always yields the same chunks, in the same
    order, with the same keys. The cursor depends on that — a re-plan that
    shuffled units would orphan every banked one.

    **CAL-P016: the partition is CONTENT-ADDRESSED, not positional.** ``buckets``
    fixes how many units the population is cut into, and membership is decided
    per ``vm_id`` by hash. This is what lets units accumulate ACROSS beats. The
    positional accumulator it replaces cut on a running market count over sorted
    ``vm_id``s, so a single market resolving into the population shifted every
    later boundary and re-keyed every later unit; the cursor then discarded all
    of them, and a build that banks 1-2 units of 40+ per beat could never finish.
    That is measured, not theorised — the 2026-08-03 flip banked one unit at
    19:15Z and threw it away at 20:15Z, and ``/api/calibration`` went dark on
    2026-08-09 as a direct consequence.

    Unit SIZE is therefore a distribution rather than a cap, which is the price
    of stability and is deliberate: a bucket's cost varies, and the beat's
    deadline — not the planner — is what stops a run mid-plan. **A single
    ``vm_id`` is still never split**, so an oversized unit (a large Polymarket
    group) still gets processed whole; splitting it would produce a chunk that
    fits and is wrong.

    Empty buckets produce no chunk at all, so :func:`is_complete` compares
    against real work rather than against a fixed grid of mostly-nothing.

    Raises ``ValueError`` on a roster row with no ``vm_id`` or no ``market_id``:
    such a row cannot be placed in any unit, and silently skipping it would drop
    real markets out of the population while every count still looked plausible.
    """
    if not isinstance(buckets, int) or isinstance(buckets, bool):
        raise ValueError("buckets must be an int")
    if buckets < 1:
        raise ValueError("buckets must be >= 1")

    by_vm: dict[str, list[int]] = {}
    seen: dict[str, set[int]] = {}
    members_by_vm: dict[str, set[str]] = {}
    for row in rows:
        raw_vm = _get(row, UNIT_KEY_VM_ID)
        raw_market = _get(row, "market_id")
        if raw_vm is None or str(raw_vm) == "" or raw_market is None:
            raise ValueError("roster row is missing vm_id or market_id; cannot plan units")
        vm_id = str(raw_vm)
        market_id = int(raw_market)
        bucket = by_vm.setdefault(vm_id, [])
        market_seen = seen.setdefault(vm_id, set())
        # One market belongs to exactly one vm_id, but the roster carries a row
        # per (market, source) and a defensive dedupe keeps the market_ids list
        # a true set — the chunk restriction predicate is built from it.
        if market_id not in market_seen:
            market_seen.add(market_id)
            bucket.append(market_id)
        # The membership digest is per ROSTER ROW, not per market: source and
        # is_grouped are exactly what generation_fingerprint watches globally,
        # and a unit that resumes must be able to see them change.
        members_by_vm.setdefault(vm_id, set()).add(
            "\x1e".join(
                (
                    str(market_id),
                    _text(_get(row, "source")),
                    vm_id,
                    _flag(_get(row, "is_grouped")),
                )
            )
        )

    grouped: dict[int, list[str]] = {}
    for vm_id in sorted(by_vm):
        grouped.setdefault(bucket_of(vm_id, buckets), []).append(vm_id)

    chunks: list[UnitChunk] = []
    for index in sorted(grouped):
        vm_ids = grouped[index]
        market_ids: list[int] = []
        members: set[str] = set()
        for vm_id in vm_ids:
            market_ids.extend(by_vm[vm_id])
            members |= members_by_vm[vm_id]
        chunks.append(
            UnitChunk(
                index=index,
                vm_ids=tuple(vm_ids),
                market_ids=tuple(sorted(market_ids)),
                members=tuple(sorted(members)),
            )
        )
    return tuple(chunks)


# =============================================================================
# Stage C — global finalization
# =============================================================================


class UndeclaredColumnError(ValueError):
    """A chunk returned a column the merge was not told how to treat.

    Deliberately fatal. The three treatments are mutually exclusive and there is
    no safe default: summing a census column that is really a per-group
    aggregate double-counts it, broadcasting an additive column freezes one
    chunk's mass onto every row, and dropping the column removes a field the
    payload consumer may read off ``rows[0]``. When the population statement
    grows a column, the merge must be told which kind it is.
    """


def merge_futures_rows(
    chunk_results: Sequence[Sequence[Any]],
    *,
    census_columns: Sequence[str] = DEFAULT_CENSUS_COLUMNS,
    additive_columns: Sequence[str] = ADDITIVE_COLUMNS,
    group_key_columns: Sequence[str] = GROUP_KEY_COLUMNS,
    extra_censuses: Optional[Sequence[Mapping[str, Any]]] = None,
) -> list[SimpleNamespace]:
    """Fold every chunk's bucket rows into the one list the monolith would emit.

    ``chunk_results`` is a list of per-chunk row lists. Rows are attribute-access
    objects (SQLAlchemy ``Row`` or ``SimpleNamespace``); ``SimpleNamespace`` rows
    come back out, so downstream attribute access is unchanged.

    Three kinds of column, three treatments:

    * **Group key** — ``bucket_idx, source, category, price_moved,
      is_nonexclusive_bundle``. Rows sharing a key merge into one. A group can
      legitimately appear in several chunks: the bucket is a price band, not a
      question, so the same band is populated by questions in different chunks.
    * **Additive** — ``n``, ``winners`` (ints) and ``sum_prob``, ``sum_sq_err``
      (floats) are summed. This is exact for the integers. For the two floats it
      is a REASSOCIATION of the same addends, so a merged value can differ from
      the monolith's in the last bits; the payload rounds both to 4 decimals, so
      the published number is the same in practice, but "bit-identical" is not a
      promise this function can make and does not pretend to.
    * **Census** — the ``MAX(...)`` one-row passthroughs. In the monolith these
      are CROSS JOINed off a 1-row summary and are therefore constant across
      every returned row; the consumer reads them off ``rows[0]`` ONLY. Per
      chunk they are chunk-local COUNTs, so finalization SUMS them across chunks
      and broadcasts the identical total onto every merged row — restoring both
      the value and the "constant across every row" property the consumer
      relies on.

    ``avg_prob`` is recomputed as ``sum_prob / n`` (0.0 when ``n`` is 0, which a
    real bucket row never is). Belt and braces, not a semantic change: the
    payload builder in ``precompute_calibration`` already recomputes it from the
    merged mass and never reads the SQL's ``AVG()`` column. Recomputing here too
    means a merged row is self-consistent even if some future reader trusts it.

    **Two census rules that matter.**

    ``COUNT(DISTINCT ...)`` census columns (:data:`DISTINCT_CENSUS_COLUMNS` —
    ``published_questions`` and the ``*_markets`` counts) sum correctly ONLY
    because a ``vm_id``, and therefore a market, never straddles a chunk. That
    dependency is discharged by :func:`plan_units` and by nothing else.

    A census column that is ``None`` in a chunk stays distinguishable from zero.
    If EVERY chunk reports ``None``, the merged value is ``None`` — unknown. If
    some chunks report numbers, those are summed and the ``None`` chunks
    contribute nothing. Unknown is never turned into 0: that is the exact lie the
    300C coverage census exists to prevent (an unmeasured census reporting
    ``unavailable``, never a confident zero).

    ``extra_censuses`` closes the one hole this shape leaves. A chunk whose
    ``vm_id``s all get filtered out of ``deduped`` returns ZERO rows, and a
    chunk with zero rows carries no census — so its candidate-side counts
    (``liq_summary`` is computed over ``normalized``, pre-dedup) would be lost.
    The runtime half can capture such a chunk's census separately and pass it
    here. If it does not, the merged census undercounts by exactly those chunks;
    stated plainly rather than hidden.

    Empty input returns ``[]``.

    Ordering matches the SQL's ``ORDER BY bucket_idx, source, category,
    price_moved, is_nonexclusive_bundle``, None-safe (see :func:`_order_key`).

    Raises :class:`UndeclaredColumnError` if a chunk row carries a column that is
    not a group key, not additive, not ``avg_prob`` and not declared census.
    """
    group_key_columns = tuple(group_key_columns)
    additive_columns = tuple(additive_columns)
    census_columns = tuple(census_columns)
    known = set(group_key_columns) | set(additive_columns) | set(census_columns) | {
        AVG_PROB_COLUMN
    }

    merged: dict[tuple, dict[str, Any]] = {}
    order: list[tuple] = []
    census_seen: dict[str, list[Any]] = {name: [] for name in census_columns}
    any_rows = False

    for chunk in chunk_results or ():
        chunk_census_taken = False
        for row in chunk or ():
            mapping = _row_mapping(row)
            undeclared = sorted(set(mapping.keys()) - known)
            if undeclared:
                raise UndeclaredColumnError(
                    "undeclared column(s) in a chunk result: " + ", ".join(undeclared)
                )
            any_rows = True
            if not chunk_census_taken:
                # Constant across the chunk (CROSS JOIN onto its 1-row summary),
                # so the first row is the whole chunk's census. A column the
                # chunk never returned is not "zero", it is "not reported" — it
                # simply does not join the vote.
                for name in census_columns:
                    if name in mapping:
                        census_seen[name].append(mapping[name])
                chunk_census_taken = True

            key = tuple(mapping.get(name) for name in group_key_columns)
            acc = merged.get(key)
            if acc is None:
                acc = {name: 0 for name in additive_columns}
                merged[key] = acc
                order.append(key)
            for name in additive_columns:
                value = mapping.get(name)
                if name in INTEGER_ADDITIVE_COLUMNS:
                    acc[name] = _as_int(acc[name]) + _as_int(value)
                else:
                    acc[name] = _as_float(acc[name]) + _as_float(value)

    for extra in extra_censuses or ():
        for name in census_columns:
            if name in extra:
                census_seen[name].append(extra[name])

    if not any_rows:
        return []

    census_total: dict[str, Any] = {}
    for name in census_columns:
        reported = census_seen[name]
        known_values = [value for value in reported if value is not None]
        if not known_values:
            # Either nobody reported it, or everybody reported unknown. Both are
            # unknown, and unknown is None.
            census_total[name] = None
        elif all(
            isinstance(value, int) and not isinstance(value, bool) for value in known_values
        ):
            census_total[name] = sum(known_values)
        else:
            census_total[name] = sum(_as_float(value) for value in known_values)

    out: list[SimpleNamespace] = []
    for key in order:
        acc = merged[key]
        fields: dict[str, Any] = dict(zip(group_key_columns, key))
        for name in additive_columns:
            fields[name] = (
                _as_int(acc[name]) if name in INTEGER_ADDITIVE_COLUMNS else _as_float(acc[name])
            )
        n = _as_int(acc.get("n", 0))
        sum_prob = _as_float(acc.get("sum_prob", 0.0))
        fields[AVG_PROB_COLUMN] = (sum_prob / n) if n else 0.0
        fields.update(census_total)
        out.append(SimpleNamespace(**fields))

    out.sort(key=lambda row: tuple(_order_key(getattr(row, name)) for name in group_key_columns))
    return out


# =============================================================================
# The cursor
# =============================================================================


def unit_key(value: Any) -> str:
    """A chunk key, from either a :class:`UnitChunk` or the key itself."""
    if isinstance(value, UnitChunk):
        return value.key
    return str(value)


@dataclass(frozen=True)
class StagedFuturesCursor:
    """What a prior beat proved it had, per unit, and who may advance it.

    The sibling ``MainBuildCheckpoint`` banks whole PHASES; this banks whole
    UNITS inside one phase. Same discipline, one level finer: a unit is recorded
    only after its own chunk statement committed AND the cursor write succeeded
    (``CHECKPOINT_BEFORE_COMMIT``), only its owner may advance it
    (``NON_OWNER_ADVANCES_CHECKPOINT``), and nothing publishes until every
    planned unit is in (``PARTIAL_GENERATION_PUBLISHED``).
    """

    population_version: str
    input_fingerprint: str = ""
    generation_fingerprint: str = ""
    generation: int = 0
    owner: str = ""
    lease_expires_at: float = 0.0
    committed_units: tuple[str, ...] = ()
    unit_results: dict[str, Any] = field(default_factory=dict)
    terminal: str = TERMINAL_PARTIAL

    def has(self, key: Any) -> bool:
        name = unit_key(key)
        return name in self.committed_units and name in self.unit_results

    def result(self, key: Any) -> Optional[list]:
        name = unit_key(key)
        if not self.has(name):
            return None
        stored = self.unit_results.get(name)
        return list(stored) if isinstance(stored, (list, tuple)) else None

    def as_payload(self) -> dict[str, Any]:
        return {
            "schema": STAGED_FUTURES_SCHEMA,
            "task": MAIN_BUILD_TASK,
            "unit_key": UNIT_KEY_VM_ID,
            "population_version": self.population_version,
            "input_fingerprint": self.input_fingerprint,
            "generation_fingerprint": self.generation_fingerprint,
            "generation": self.generation,
            "owner": self.owner,
            "lease_expires_at": self.lease_expires_at,
            "committed_units": list(self.committed_units),
            "unit_results": self.unit_results,
            "terminal": self.terminal,
        }


def new_staged_cursor(
    *,
    population_version: str,
    input_fingerprint: str,
    generation_fingerprint: str,
    owner: str,
    generation: int,
) -> StagedFuturesCursor:
    return StagedFuturesCursor(
        population_version=population_version,
        input_fingerprint=input_fingerprint,
        generation_fingerprint=generation_fingerprint,
        generation=generation,
        owner=owner,
    )


def decode_staged_cursor(
    raw: Any,
    *,
    expected_population_version: str,
    expected_input_fingerprint: str,
    expected_generation_fingerprint: str,
    owner: str,
    generation: int,
    now: float,
) -> tuple[StagedFuturesCursor, str]:
    """``(cursor, action)`` — :func:`decode_staged_cursor_detailed` without the reason.

    Kept as the two-value form because that is what every caller that does not
    log wants. The predicate chain lives in the detailed function ONLY; a second
    copy of "why is this cursor unusable" is the C14 drift this module already
    refuses elsewhere.
    """
    cursor, action, _reason = decode_staged_cursor_detailed(
        raw,
        expected_population_version=expected_population_version,
        expected_input_fingerprint=expected_input_fingerprint,
        expected_generation_fingerprint=expected_generation_fingerprint,
        owner=owner,
        generation=generation,
        now=now,
    )
    return cursor, action


def decode_staged_cursor_detailed(
    raw: Any,
    *,
    expected_population_version: str,
    expected_input_fingerprint: str,
    expected_generation_fingerprint: str,
    owner: str,
    generation: int,
    now: float,
) -> tuple[StagedFuturesCursor, str, str]:
    """Load a persisted cursor, refusing anything not provably resumable.

    Returns ``(cursor, action, reason)``. CAL-P024 added the third value, and the
    reason it exists is worth stating: **five distinct causes below all produce
    the same** ``INVALIDATE``, and the caller records only
    ``staged:cursor_invalidate``. When the 2026-08-09 18:15Z beat discarded the
    ten units the 16:15Z beat had banked, establishing WHICH cause fired took a
    source read plus ``git show`` across two merges — and the cycle before that
    could not establish it at all and mis-attributed the stall to beat delivery.

    A cursor reset is the most consequential event in this build's life: it is
    the difference between a build that is slow and one that can never finish.
    "It reset" without "because the input fingerprint moved" is gotcha #53's
    shape — one observable standing in for several different facts.

    The reason is a short stable token, not prose, so it can be counted across
    beats: the useful question is never "why did this one reset" but "which
    cause is resetting us every time".

    Returns ``(cursor, action)`` using the sibling's four actions, imported from
    ``calibration_phase_ledger`` rather than redefined so the two halves of the
    build cannot drift apart:

    * :data:`~app.utils.calibration_phase_ledger.FRESH` — nothing there, or
      nothing there that is usable. Start over; that is not an error.
    * :data:`~app.utils.calibration_phase_ledger.INVALIDATE` — something is
      there but we cannot vouch for it: wrong schema, wrong task, wrong
      population version, wrong input fingerprint, or a malformed shape.

      **CAL-P016 removed the generation fingerprint from this list**, and that
      is the convergence fix. A moved roster used to invalidate the WHOLE
      cursor: the digest covers every ``(market_id, source, vm_id, is_grouped)``
      in the population, markets resolve continuously, so it moved between every
      pair of hourly beats and threw away everything banked. Units could only
      accumulate if the population held still, and it never does — so the build
      could never finish, and ``/api/calibration`` went dark.

      ``LATE_ARRIVAL_NOT_INVALIDATED`` is **preserved and made finer**, not
      weakened. It now holds per UNIT via :func:`retain_planned_units`: a banked
      unit survives only if its key still matches a planned chunk, and the key
      digests that unit's own roster membership. A unit whose contents changed
      stops matching and is recomputed; a unit untouched by the arrival is still
      exactly the census it always was. What may never happen — mixing rows
      computed against two different definitions of the SAME unit — still cannot.
      The population version and input fingerprint remain wholesale invalidators,
      because those change what a unit MEANS rather than which markets are in it.
    * :data:`~app.utils.calibration_phase_ledger.REFUSE` — a DIFFERENT owner
      holds an UNEXPIRED lease. Another beat is mid-build; two workers each
      advancing half a cursor is how a generation gets mixed. Doing nothing is
      correct.
    * :data:`~app.utils.calibration_phase_ledger.RESUME` — same population, same
      inputs, same roster, lease ours or expired. Carry the committed units.

    Checked in that order deliberately: a cursor we cannot vouch for is
    invalidated whether or not somebody holds its lease, because there is
    nothing there worth protecting.
    """
    blank = new_staged_cursor(
        population_version=expected_population_version,
        input_fingerprint=expected_input_fingerprint,
        generation_fingerprint=expected_generation_fingerprint,
        owner=owner,
        generation=generation,
    )
    if raw is None:
        return blank, FRESH, REASON_ABSENT
    if not isinstance(raw, dict):
        return blank, INVALIDATE, REASON_MALFORMED
    if raw.get("schema") != STAGED_FUTURES_SCHEMA:
        return blank, INVALIDATE, REASON_SCHEMA
    if raw.get("task") != MAIN_BUILD_TASK:
        # Split from the schema check purely so the two report separately: a
        # foreign task's cursor and a stale schema are different operational
        # stories, and they were indistinguishable while they shared a branch.
        return blank, INVALIDATE, REASON_TASK
    if raw.get("unit_key") != UNIT_KEY_VM_ID:
        # A cursor cut on a different partition key is not a cursor for this
        # plan; its unit keys mean something else entirely.
        return blank, INVALIDATE, REASON_UNIT_KEY
    if raw.get("population_version") != expected_population_version:
        return blank, INVALIDATE, REASON_POPULATION_VERSION
    if raw.get("input_fingerprint") != expected_input_fingerprint:
        # THE one that fires in practice. A deploy touching any SQL function in
        # ``_main_input_fingerprint`` lands here and costs every banked unit.
        return blank, INVALIDATE, REASON_INPUT_FINGERPRINT
    # NOTE: generation_fingerprint is deliberately NOT checked here (CAL-P016).
    # It is still carried and still written, because it names which roster a
    # cursor was last advanced against and that is worth having in the payload —
    # but a mismatch is now handled per-unit by retain_planned_units, not by
    # discarding the cursor. See this function's docstring for why.

    held_by = raw.get("owner") or ""
    lease = raw.get("lease_expires_at")
    lease_expires_at = (
        float(lease) if isinstance(lease, (int, float)) and not isinstance(lease, bool) else 0.0
    )
    if held_by and held_by != owner and lease_expires_at > now:
        return (
            replace(blank, owner=held_by, lease_expires_at=lease_expires_at),
            REFUSE,
            REASON_LEASE_HELD,
        )

    committed = raw.get("committed_units")
    results = raw.get("unit_results")
    if not isinstance(committed, list) or not isinstance(results, dict):
        return blank, INVALIDATE, REASON_MALFORMED_UNITS

    # A unit is resumable only if it is BOTH declared committed and carries a
    # stored row list. A unit marked done with no rows is a bookkeeping error,
    # and treating it as done would silently drop its buckets from the merge —
    # a payload that is quietly missing a slice of the population is worse than
    # one that has to be recomputed.
    resumable = tuple(
        name
        for name in committed
        if isinstance(name, str) and isinstance(results.get(name), (list, tuple))
    )
    return (
        StagedFuturesCursor(
            population_version=expected_population_version,
            input_fingerprint=expected_input_fingerprint,
            generation_fingerprint=expected_generation_fingerprint,
            generation=generation,
            owner=owner,
            lease_expires_at=lease_expires_at,
            committed_units=resumable,
            unit_results={name: list(results[name]) for name in resumable},
            terminal=str(raw.get("terminal") or TERMINAL_PARTIAL),
        ),
        RESUME if resumable else FRESH,
        REASON_RESUMABLE if resumable else REASON_NOTHING_BANKED,
    )


def retain_planned_units(
    cursor: StagedFuturesCursor, chunks: Iterable[Any]
) -> tuple[StagedFuturesCursor, tuple[str, ...]]:
    """Drop banked units that no longer match a planned chunk.

    CAL-P016. This is where ``LATE_ARRIVAL_NOT_INVALIDATED`` is enforced now
    that :func:`decode_staged_cursor` no longer discards a whole cursor when the
    roster moves. Returns ``(cursor, dropped_keys)`` — the keys are returned
    rather than merely logged so a caller can record how much drift a beat
    actually cost, which is the number that says whether the build is
    converging.

    A unit is kept iff its key is in the plan. Because a chunk key digests that
    chunk's full roster membership, "in the plan" means *this exact set of
    questions, markets, sources and grouping flags* — so a kept unit's rows are
    still a census of precisely what the new plan asks that unit for. A unit
    whose contents changed re-keys, matches nothing, and is recomputed.

    Idempotent, and a no-op in the common case where nothing drifted.
    """
    planned = {unit_key(chunk) for chunk in chunks}
    kept = tuple(name for name in cursor.committed_units if name in planned)
    dropped = tuple(name for name in cursor.committed_units if name not in planned)
    if not dropped:
        return cursor, ()
    return (
        replace(
            cursor,
            committed_units=kept,
            unit_results={name: cursor.unit_results[name] for name in kept},
        ),
        dropped,
    )


def can_advance(cursor: StagedFuturesCursor, owner: str) -> bool:
    """Whether ``owner`` may bank a unit onto this cursor.

    A cursor with no owner is unclaimed and anyone may take it; otherwise only
    the recorded owner. Exposed so a call site can LOG a refusal rather than
    discover it as a silent no-op.
    """
    return not cursor.owner or cursor.owner == owner


def advance(
    cursor: StagedFuturesCursor,
    chunk_key: Any,
    rows: Sequence[Any],
    *,
    owner: str,
    lease_expires_at: float,
) -> StagedFuturesCursor:
    """Bank one unit's rows, returning a NEW cursor.

    **Idempotent.** Advancing the same unit key twice is a no-op: the key is not
    duplicated in ``committed_units`` and the FIRST stored result is kept. A
    retry of a unit that already committed must not change the merge output —
    that is ``RETRY_NOT_IDEMPOTENT`` — and keeping the first result is the
    conservative reading: within one generation a chunk's rows are deterministic,
    so a second, different result means something is wrong and the banked,
    already-validated one is the one to trust.

    **A non-owner cannot advance.** Enforced here rather than trusted to call
    sites, exactly as ``PhaseLedger.note_checkpoint`` enforces its two refusals.
    Like that method, the refusal is a NO-OP rather than an exception — the
    cursor comes back unchanged, so the unit is simply not committed and
    :func:`is_complete` stays False, which means nothing publishes. Use
    :func:`can_advance` first if you want to say so out loud.
    """
    if not can_advance(cursor, owner):
        return cursor
    key = unit_key(chunk_key)
    if key in cursor.committed_units:
        return replace(cursor, owner=owner, lease_expires_at=lease_expires_at)
    return replace(
        cursor,
        owner=owner,
        lease_expires_at=lease_expires_at,
        committed_units=tuple(list(cursor.committed_units) + [key]),
        unit_results={**cursor.unit_results, key: list(rows)},
    )


def is_complete(cursor: StagedFuturesCursor, chunks: Iterable[Any]) -> bool:
    """True only when EVERY planned unit is banked, and no stranger is banked.

    Finalization and publication gate on this. Partial is not done: a merge over
    some of the chunks is a population with a slice missing, and publishing it
    is ``PARTIAL_GENERATION_PUBLISHED`` (and ``GLOBAL_FINALIZATION_MISSING`` if
    the merge never runs at all).

    An empty plan is vacuously complete — a roster with no eligible markets has
    nothing to compute, and that is a real, if rare, state rather than a stuck
    build.

    A committed unit that matches NO planned chunk makes this False. Callers run
    :func:`retain_planned_units` first, which removes exactly those, so reaching
    here with one means the plan and the cursor disagree about what the
    population is — and refusing to publish is the only safe answer. Kept as a
    belt-and-braces check rather than relaxed to a subset test: "every planned
    unit is banked" and "nothing unplanned is banked" are both required, and the
    second is what catches a retention step that was skipped.
    """
    planned = {unit_key(chunk) for chunk in chunks}
    committed = {name for name in cursor.committed_units if name in cursor.unit_results}
    return planned == committed


def collect_unit_results(
    cursor: StagedFuturesCursor, chunks: Sequence[Any]
) -> list[list[Any]]:
    """Banked rows, in plan order, ready for :func:`merge_futures_rows`.

    Plan order rather than commit order so the merge sees the same sequence
    however the beats interleaved. A unit with nothing banked contributes an
    empty list — which is also what a chunk that legitimately published no
    buckets looks like, so callers must gate on :func:`is_complete` first rather
    than inferring completeness from this.
    """
    return [list(cursor.result(chunk) or []) for chunk in chunks]
