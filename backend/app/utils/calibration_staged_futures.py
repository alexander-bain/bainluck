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
    "can_advance",
    "collect_unit_results",
    "decode_staged_cursor",
    "generation_fingerprint",
    "is_complete",
    "merge_futures_rows",
    "new_staged_cursor",
    "plan_units",
    "unit_key",
]

#: The partition key. Named, because ``UNSAFE_PARTITION_KEY`` in the C126
#: corpus accepts exactly two: ``source`` and ``virtual_question``. This is the
#: latter.
UNIT_KEY_VM_ID = "vm_id"

STAGED_FUTURES_SCHEMA = "calibration-staged-futures/v1"

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


@dataclass(frozen=True)
class UnitChunk:
    """One Stage B unit: whole virtual questions and the markets inside them."""

    index: int
    vm_ids: tuple[str, ...]
    market_ids: tuple[int, ...]

    @property
    def key(self) -> str:
        """Short stable digest of this chunk's ``vm_id`` set.

        A cursor entry names a chunk by this key rather than by index, so a
        banked unit can be VALIDATED against the chunk it claims: change the
        roster or the chunk size and the keys move, and a stale unit simply
        stops matching any planned chunk instead of being silently mapped onto
        whatever now sits at index 3.
        """
        return input_fingerprint(UNIT_KEY_VM_ID, *self.vm_ids)[:16]

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


def plan_units(rows: Iterable[Any], *, max_markets_per_chunk: int) -> tuple[UnitChunk, ...]:
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

    Deterministic by construction: ``vm_id``s are placed in sorted order, so the
    same roster always yields the same chunks, in the same order, with the same
    keys. The cursor depends on that — a re-plan that shuffled units would orphan
    every banked one.

    ``max_markets_per_chunk`` is a target, not a ceiling. **A single ``vm_id``
    holding more markets than the target still gets its own whole chunk** — it
    is never truncated, and it is never merged with a neighbour. An oversized
    unit is a real thing (a large Polymarket group), and the honest response is
    one big chunk that may not fit the beat; splitting it would produce a chunk
    that fits and is wrong.

    Raises ``ValueError`` on a roster row with no ``vm_id`` or no ``market_id``:
    such a row cannot be placed in any unit, and silently skipping it would drop
    real markets out of the population while every count still looked plausible.
    """
    if not isinstance(max_markets_per_chunk, int) or isinstance(max_markets_per_chunk, bool):
        raise ValueError("max_markets_per_chunk must be an int")
    if max_markets_per_chunk < 1:
        raise ValueError("max_markets_per_chunk must be >= 1")

    by_vm: dict[str, list[int]] = {}
    seen: dict[str, set[int]] = {}
    for row in rows:
        raw_vm = _get(row, UNIT_KEY_VM_ID)
        raw_market = _get(row, "market_id")
        if raw_vm is None or str(raw_vm) == "" or raw_market is None:
            raise ValueError("roster row is missing vm_id or market_id; cannot plan units")
        vm_id = str(raw_vm)
        market_id = int(raw_market)
        bucket = by_vm.setdefault(vm_id, [])
        members = seen.setdefault(vm_id, set())
        # One market belongs to exactly one vm_id, but the roster carries a row
        # per (market, source) and a defensive dedupe keeps the market_ids list
        # a true set — the chunk restriction predicate is built from it.
        if market_id not in members:
            members.add(market_id)
            bucket.append(market_id)

    chunks: list[UnitChunk] = []
    current_vms: list[str] = []
    current_markets: list[int] = []
    for vm_id in sorted(by_vm):
        markets = by_vm[vm_id]
        if current_vms and len(current_markets) + len(markets) > max_markets_per_chunk:
            chunks.append(
                UnitChunk(
                    index=len(chunks),
                    vm_ids=tuple(current_vms),
                    market_ids=tuple(sorted(current_markets)),
                )
            )
            current_vms, current_markets = [], []
        current_vms.append(vm_id)
        current_markets.extend(markets)
    if current_vms:
        chunks.append(
            UnitChunk(
                index=len(chunks),
                vm_ids=tuple(current_vms),
                market_ids=tuple(sorted(current_markets)),
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
    """Load a persisted cursor, refusing anything not provably resumable.

    Returns ``(cursor, action)`` using the sibling's four actions, imported from
    ``calibration_phase_ledger`` rather than redefined so the two halves of the
    build cannot drift apart:

    * :data:`~app.utils.calibration_phase_ledger.FRESH` — nothing there, or
      nothing there that is usable. Start over; that is not an error.
    * :data:`~app.utils.calibration_phase_ledger.INVALIDATE` — something is
      there but we cannot vouch for it: wrong schema, wrong task, wrong
      population version, wrong input fingerprint, **wrong generation
      fingerprint**, or a malformed shape. The generation-fingerprint case is
      the LATE ARRIVAL: the roster moved under us, so every banked unit
      describes a population that no longer exists and mixing it with fresh
      chunks is ``LATE_ARRIVAL_NOT_INVALIDATED``.
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
        return blank, FRESH
    if not isinstance(raw, dict):
        return blank, INVALIDATE
    if raw.get("schema") != STAGED_FUTURES_SCHEMA or raw.get("task") != MAIN_BUILD_TASK:
        return blank, INVALIDATE
    if raw.get("unit_key") != UNIT_KEY_VM_ID:
        # A cursor cut on a different partition key is not a cursor for this
        # plan; its unit keys mean something else entirely.
        return blank, INVALIDATE
    if raw.get("population_version") != expected_population_version:
        return blank, INVALIDATE
    if raw.get("input_fingerprint") != expected_input_fingerprint:
        return blank, INVALIDATE
    if raw.get("generation_fingerprint") != expected_generation_fingerprint:
        return blank, INVALIDATE

    held_by = raw.get("owner") or ""
    lease = raw.get("lease_expires_at")
    lease_expires_at = (
        float(lease) if isinstance(lease, (int, float)) and not isinstance(lease, bool) else 0.0
    )
    if held_by and held_by != owner and lease_expires_at > now:
        return replace(blank, owner=held_by, lease_expires_at=lease_expires_at), REFUSE

    committed = raw.get("committed_units")
    results = raw.get("unit_results")
    if not isinstance(committed, list) or not isinstance(results, dict):
        return blank, INVALIDATE

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

    A committed unit that matches NO planned chunk makes this False. That should
    be unreachable (the generation fingerprint invalidates a cursor whose roster
    moved), so if it happens the plan and the cursor disagree about what the
    population is, and refusing to publish is the only safe answer.
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
