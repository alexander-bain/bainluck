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
from datetime import date, datetime
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
    "ACCUMULATOR_SCHEMA",
    "DECLARED_CENSUS_COLUMNS",
    "DEFAULT_CENSUS_COLUMNS",
    "DISTINCT_CENSUS_COLUMNS",
    "GROUP_KEY_COLUMNS",
    "INTEGER_ADDITIVE_COLUMNS",
    "REPRESENTATIVE_TIE_COLUMN",
    "STAGED_FUTURES_SCHEMA",
    "UNIT_KEY_VM_ID",
    "StagedFuturesCursor",
    "UnencodableValueError",
    "UnitChunk",
    "advance",
    "bucket_of",
    "can_advance",
    "collect_unit_results",
    "decode_accumulator",
    "decode_staged_cursor",
    "decode_staged_cursor_detailed",
    "decode_unit_rows",
    "encode_accumulator",
    "encode_unit_rows",
    "fold_unit_rows",
    "generation_fingerprint",
    "is_complete",
    "is_encoded_accumulator",
    "is_encoded_unit_rows",
    "merge_futures_rows",
    "split_unit_rows",
    "new_staged_cursor",
    "plan_units",
    "retain_planned_units",
    "roster_drift",
    "unit_key",
]

#: The partition key. Named, because ``UNSAFE_PARTITION_KEY`` in the C126
#: corpus accepts exactly two: ``source`` and ``virtual_question``. This is the
#: latter.
UNIT_KEY_VM_ID = "vm_id"

STAGED_FUTURES_SCHEMA = "calibration-staged-futures/v1"

#: The accumulator envelope's own version, carried INSIDE the cursor rather than
#: bumping :data:`STAGED_FUTURES_SCHEMA`. The cursor contract — task, unit key,
#: population version, fingerprint — is unchanged by CAL-P034; only what it
#: retains changed, and a reader that finds an unfolded cursor reports
#: :data:`REASON_UNFOLDED_UNITS`, which says more than ``schema_mismatch`` would.
ACCUMULATOR_SCHEMA = "calibration-staged-accumulator/v1"

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
#: CAL-P033. The banked rows are not the encoded envelope :func:`encode_unit_rows`
#: writes — i.e. a cursor written before rows were encoded, whose rows came back
#: from JSON as ``repr()`` STRINGS. Its own reason token rather than
#: ``malformed_units`` because it is not corruption: it is a cursor written by
#: code that could not round-trip, and it will be the ONLY cause that fires for
#: one generation after this ships. Folding it into ``malformed_units`` would
#: make that one expected reset indistinguishable from a real one.
REASON_UNENCODED_UNITS = "unencoded_units"
#: CAL-P034. A cursor holding per-unit rows rather than the running fold — i.e.
#: written by CAL-P033-era code, whose rows were encoded and therefore readable,
#: just not folded. Distinct from ``unencoded_units`` for the same reason that
#: one is distinct from ``malformed_units``: it is the ONE expected reset when
#: this ships, and an expected reset that cannot be told from a real one is not
#: an observation. If both queues deploy together — they are one stack —
#: production sees ``unencoded_units`` once and this token never.
REASON_UNFOLDED_UNITS = "unfolded_units"
REASON_LEASE_HELD = "lease_held_by_other"
#: The snapshot read itself threw — an unreadable cursor is a fresh one.
REASON_READ_FAILED = "read_failed"
REASON_RESUMABLE = "resumable"
REASON_NOTHING_BANKED = "nothing_banked"

# --- The row shape Stage B returns and Stage C merges -------------------------
#
# Read off the production SELECT list in ``precompute_calibration``'s futures
# query (its GROUP BY / ORDER BY are the same five columns, in this order).

#: ``GROUP BY bucket_idx, source, category, price_moved, is_nonexclusive_bundle,
#: trade_evidence`` — and the identical ``ORDER BY``. Rows sharing this key merge
#: into one.
#:
#: ``trade_evidence`` joined the key in CAL-P044 (#1530) and it MUST be a key
#: rather than a passthrough: it is a per-outcome classification, so folding two
#: chunks' rows across it would silently blend traded and untraded mass into one
#: bucket and the census built from the merged rows would read a single blurred
#: class. A passthrough would be worse still — the fold would freeze one chunk's
#: value and broadcast it over every other chunk's outcomes.
GROUP_KEY_COLUMNS: tuple[str, ...] = (
    "bucket_idx",
    "source",
    "category",
    "price_moved",
    "is_nonexclusive_bundle",
    "trade_evidence",
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

#: Always emitted by the statement (Queue 300D Item 1), so unlike the ``cb_*``
#: rungs it is not conditional and belongs in the default declared set.
REPRESENTATIVE_TIE_COLUMN = "representative_tie_broken"

#: Field separator inside one encoded roster-membership row —
#: ``market_id | source | vm_id | is_grouped``. ASCII RECORD SEPARATOR, chosen
#: because it cannot occur in the values in practice.
#:
#: Named (CAL-P036) rather than repeated as a literal because it is now load
#: bearing in two directions: :func:`generation_fingerprint` and
#: :func:`plan_units` both BUILD these rows, and ``plan_units`` also SPLITS them
#: back apart to recover ``market_ids``. Two copies of a separator is how the
#: reader and the writer drift.
MEMBER_SEPARATOR = "\x1e"

#: **The census set the build actually declares, reconstructed here** (CAL-P034).
#:
#: :func:`fold_unit_rows` runs the ``UndeclaredColumnError`` guard at BANK time,
#: because that is where a unit's rows are last seen whole. The declared set
#: lives in the frozen ``precompute_calibration`` next to the statement that
#: emits it, and ruling 009 bars importing that module at runtime — so it is
#: mirrored here and the mirror is PINNED: a characterization test reads the
#: frozen file as TEXT and fails if its expression and this constant disagree,
#: in either direction. Before CAL-P034 :data:`DEFAULT_CENSUS_COLUMNS` mirrored
#: the same statement "as of Queue 300D" with nothing checking it at all.
#:
#: The conditional ``cb_*`` half is deliberately absent. ``COVERAGE_CENSUS_ENABLED``
#: is ``False`` and — this is the part that makes a default safe rather than a
#: guess — it is hashed BY VALUE into ``_main_input_fingerprint``
#: (``f"coverage_census={COVERAGE_CENSUS_ENABLED}"``), so flipping it invalidates
#: every banked unit wholesale. **A cursor therefore only ever sees ONE census
#: set in its lifetime**, and a caller that turns the switch on must pass
#: ``census_columns`` explicitly; the pinning test fails until it does.
DECLARED_CENSUS_COLUMNS: tuple[str, ...] = tuple(DEFAULT_CENSUS_COLUMNS) + (
    REPRESENTATIVE_TIE_COLUMN,
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


class UnencodableValueError(TypeError):
    """A banked value has no declared JSON encoding.

    Deliberately fatal, and this module's most expensive lesson (CAL-P033). The
    durable writer is ``json.dumps(..., default=str)``, so an undeclared type is
    not rejected there — it is silently stringified, banked, and only discovered
    when the merge tries to read columns off it. ``str()`` as a fallback is the
    exact behaviour this class exists to replace, so it is not offered here.
    """


#: Tag keys for the two non-JSON scalars the population statement returns.
#: Objects rather than bare strings so an encoded value can never be confused
#: with a genuine string column (``source``, ``category``).
DECIMAL_TAG = "__decimal__"
DATETIME_TAG = "__isotime__"


def _encode_scalar(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, Decimal):
        # str(), not float(): the SQL returns NUMERIC for the probability sums
        # and this round-trip must not quietly change the addends the merge
        # sums. Rounding is the payload builder's decision, not the cursor's.
        return {DECIMAL_TAG: str(value)}
    if isinstance(value, (datetime, date)):
        return {DATETIME_TAG: value.isoformat()}
    raise UnencodableValueError(
        f"no declared encoding for a {type(value).__name__} banked into a unit"
    )


def _decode_scalar(value: Any) -> Any:
    if isinstance(value, Mapping):
        if DECIMAL_TAG in value:
            return Decimal(str(value[DECIMAL_TAG]))
        if DATETIME_TAG in value:
            return datetime.fromisoformat(str(value[DATETIME_TAG]))
    return value


def encode_unit_rows(rows: Iterable[Any]) -> dict[str, Any]:
    """One unit's rows as a JSON-safe, losslessly decodable envelope.

    **This is CAL-P033's fix, and the bug it closes had nothing to do with the
    encoding being wrong — it was that there was none.** :func:`advance` used to
    bank the driver's ``Row`` objects as-is. Within the beat that produced them
    that works, because a ``Row`` is attribute-access and the merge reads it
    happily. But the cursor is written durably through
    ``durable_state.canonical_json``, which is ``json.dumps(..., default=str)``,
    so every banked row reached Postgres as its ``repr()``::

        "(0, 'kalshi', 'baseball', False, False, 14, 0, Decimal('0.0307...'), ...)"

    and came back on the next beat as a ``str``. The cursor still vouched for
    those units — they are a list, so ``RESUME``/``resumable`` — and the failure
    surfaced only at the very end, in finalization, on the first resumed row.
    Since a beat banks ~19 of 128 units, **every completed build necessarily
    contains resumed units, so the completion path could never run.** It had
    never run: the build has not published since 2026-08-02.

    Why the tests did not catch it: they pass ``SimpleNamespace`` rows straight
    from :func:`advance` to :func:`merge_futures_rows` in one process. **The
    round trip was the untested edge, and it is the only edge production uses.**

    Columnar — names once, then a value array per row — rather than a dict per
    row. Not a micro-optimisation: at 547 rows and 38 columns a dict-per-row
    envelope is ~4x the bytes, the whole cursor is re-serialised after EVERY
    unit, and the worker peaks at 505 MB against a 512 MB dyno (measured
    2026-08-11). The compact form keeps the fix from costing what it buys.

    Rows from one unit come from one SELECT and so share a column tuple. If they
    ever do not, the envelope falls back to presence-preserving pairs, because
    the merge distinguishes a census column that is *absent* from one that is
    ``None`` and a columnar form would flatten that distinction into a
    confident ``None``.
    """
    mappings = [_row_mapping(row) for row in (rows or ())]
    if not mappings:
        return {"cols": [], "rows": []}
    columns = tuple(mappings[0].keys())
    if any(tuple(mapping.keys()) != columns for mapping in mappings[1:]):
        return {
            "cols": None,
            "rows": [
                {str(name): _encode_scalar(value) for name, value in mapping.items()}
                for mapping in mappings
            ],
        }
    names = [str(name) for name in columns]
    return {
        "cols": names,
        "rows": [[_encode_scalar(mapping[name]) for name in columns] for mapping in mappings],
    }


def is_encoded_unit_rows(stored: Any) -> bool:
    """Whether ``stored`` is an :func:`encode_unit_rows` envelope.

    The guard that makes a pre-CAL-P033 cursor refusable. A legacy cursor's
    units are ``list[str]`` — structurally a perfectly good list, which is
    exactly why the resumability filter accepted them for nine days.
    """
    return (
        isinstance(stored, Mapping)
        and isinstance(stored.get("rows"), list)
        and (stored.get("cols") is None or isinstance(stored.get("cols"), list))
    )


def decode_unit_rows(stored: Any) -> list[SimpleNamespace]:
    """An encoded envelope back to attribute-access rows the merge accepts.

    ``SimpleNamespace``, the same shape ``calibration_main_build.decode_rows``
    produces, so a resumed unit and a unit banked this beat are the SAME TYPE.
    That identity is the invariant whose absence was the bug — not the encoding
    itself. :func:`advance` therefore encodes on the way IN, so no unit is ever
    held in a representation that only survives inside one process.
    """
    if not is_encoded_unit_rows(stored):
        return []
    cols = stored.get("cols")
    rows = stored.get("rows") or []
    if cols is None:
        return [
            SimpleNamespace(**{str(k): _decode_scalar(v) for k, v in item.items()})
            for item in rows
            if isinstance(item, Mapping)
        ]
    names = [str(name) for name in cols]
    return [
        SimpleNamespace(**{name: _decode_scalar(value) for name, value in zip(names, item)})
        for item in rows
        if isinstance(item, (list, tuple))
    ]


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
        MEMBER_SEPARATOR.join(
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
    #: stays valid.
    #:
    #: **CAL-P037: the planner no longer fills this.** It is populated only
    #: transiently, inside :func:`plan_units`, long enough to compute
    #: :attr:`stored_member_digest`; the chunk that escapes the planner carries
    #: the digest and an empty tuple. See that attribute for the measurement.
    members: tuple[str, ...] = ()
    #: The partition size this chunk was cut with. Part of :attr:`key` so a
    #: cursor banked under one bucket count can never be resumed under another —
    #: the one cross-partition confusion the old membership digest ruled out for
    #: free and a positional key would reintroduce silently.
    buckets: int = 0
    #: The value of :attr:`member_digest`, computed at plan time while
    #: :attr:`members` was still in hand — so that the members need not be kept.
    #:
    #: **CAL-P037, and the reason is a measurement.** ``members`` holds one
    #: string per ROSTER ROW: ~669,383 of them across the partition, **57.9 MB,
    #: retained for the whole ~23-minute beat** — including the moment
    #: ``rss:at:read:futures_unit`` samples 466 MB on a 512 MB worker. Its only
    #: consumer in the entire application is :attr:`member_digest`, which turns
    #: it into **sixteen characters**. Holding 57.9 MB all beat to feed one hash
    #: is the largest remaining term this lane can reach without touching the
    #: ruling-009-frozen build module.
    #:
    #: **Precedence, stated rather than implied:** when this is non-empty it IS
    #: the digest and ``members`` is not consulted; when it is empty the digest
    #: is computed from ``members`` as before. The empty case exists for chunks
    #: built by hand in tests, which is why ``members`` remains an accepted
    #: field rather than being deleted outright.
    stored_member_digest: str = ""

    @property
    def key(self) -> str:
        """Stable identity of this unit's SLOT in the partition.

        ``(buckets, index)`` and nothing else. A ``vm_id``'s bucket is
        :func:`bucket_of` that ``vm_id`` alone, so slot ``i`` of a 128-way
        partition means the same thing in every beat, in every dyno, and after
        every deploy — which is precisely what lets a banked unit survive to the
        next beat.

        **CAL-P028 narrowed this from the unit's full roster MEMBERSHIP, and
        that is the convergence fix.** CAL-P016 had widened it to membership to
        close a real hole (a market resolving INTO an existing ``vm_id`` left a
        ``vm_id``-only key unchanged while making the banked rows stale). The
        hole was real; the remedy was fatal. Measured on 2026-08-10, one
        fully productive beat:

        * 14:15:33Z — 20 units banked
        * 14:17:19Z — :func:`retain_planned_units` dropped **16 of 20**
        * 14:33:48Z — 15 fresh units banked at 65.9 s each, ending at **19**

        **Net across a beat that completed 15 units: minus one.** ~20 markets
        enter the eligible roster every hour, each re-keying its whole unit, so
        the beat destroyed 16 units to build 15. At 128 planned units and −1 per
        beat the build cannot finish, and ``/api/calibration`` served a payload
        8.44 days stale with 181 consecutive failed beats behind it.

        Staleness is not ignored, it is DEMOTED from an invalidator to a
        measurement: :attr:`member_digest` still digests the full membership,
        the cursor stores it per banked unit, and :func:`roster_drift` counts
        how many banked units the roster has moved under. A unit whose
        membership changed after it ran contributes rows computed without that
        market — bounded at roughly 20 arrivals/hour against a ~110K roster
        (~0.1% for a six-beat build) and picked up whole by the next
        generation. Late inclusion, not a wrong number, and it is published
        rather than assumed (Alex ruling, 2026-08-10).
        """
        return input_fingerprint(UNIT_KEY_VM_ID, f"b={self.buckets}", f"i={self.index}")[:16]

    @property
    def member_digest(self) -> str:
        """Digest of this unit's full roster membership.

        What :attr:`key` used to be. It is still computed and still stored per
        banked unit — it simply no longer decides whether work is thrown away.
        Its job now is to answer "how much has the roster moved under the units
        we are holding", which is the honest version of the question CAL-P016
        was trying to answer by discarding them.

        **CAL-P037: returns :attr:`stored_member_digest` when the planner filled
        it**, which is always the case for a chunk that came out of
        :func:`plan_units`. The value is unchanged either way — the planner
        obtains it by calling this very property on a chunk that still holds its
        members, so the two paths are the same code and not two derivations of
        one fact. The stored value is load-bearing beyond this beat: the cursor
        keeps it per banked unit in ``unit_digests`` and :func:`roster_drift`
        compares against it, so a digest that MOVED would report all 128 banked
        units as drifted.
        """
        if self.stored_member_digest:
            return self.stored_member_digest
        return self._digest_of_members()

    def _digest_of_members(self) -> str:
        """:attr:`member_digest` computed from :attr:`members`, ignoring the store.

        Separated only so :func:`plan_units` can compute the digest and then
        discard the members without the property short-circuiting on a value it
        is in the middle of producing.
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

    # CAL-P036: accumulate per BUCKET, never per ``vm_id``. The output is
    # byte-identical to the per-``vm_id`` accumulator this replaces; the reason
    # to replace it is that the intermediates dominated the beat's peak RSS.
    #
    # The old shape allocated one container per DISTINCT ``vm_id`` in each of
    # three dicts, and ``vm_id`` is near-unique in this population: an ungrouped
    # market's virtual question is ``m:<market_id>``, so a 669,383-row roster
    # carries ~669,383 distinct ``vm_id``s, not the ~1,600 a "group" key
    # suggests. An empty CPython ``set`` costs 216 bytes whether it holds one
    # element or none, so ``seen`` and ``members_by_vm`` alone reserved
    #
    #     669,383 x 216 x 2  =  276 MB of container headers
    #
    # before a single byte of payload, plus ~41 MB for ``by_vm``'s one-element
    # lists. Measured on a synthetic roster at the production cardinality, the
    # transient peak inside this function was ~440 MB over and above the roster
    # itself, on a worker with a 512 MB limit — i.e. THIS FUNCTION was the
    # capacity wall, not the retained cursor and not the retained roster.
    #
    # ``buckets`` is fixed (128 in production), so keying the accumulators on the
    # bucket index instead turns ~2.0M containers into ~384 and makes the
    # overhead independent of population size. The payload is unchanged; only the
    # boxes holding it are.
    #
    # TWO accumulators, not three. An earlier draft of this change also kept a
    # per-bucket set of ``(vm_id, market_id)`` pairs to preserve the dedupe, and
    # that set costs one tuple PER ROW — which made the whole change a
    # REGRESSION whenever the roster is heavily grouped, because the shape it
    # replaces costs per DISTINCT ``vm_id``. Measured across grouping regimes at
    # 669,383 rows, the pair-set draft ran 84 MB WORSE than the old code at an
    # average group size of 4. Since the production group-size distribution is
    # not measurable from here (the roster read alone exceeds the read rail's
    # 25 s ceiling), a change whose SIGN depends on it is not shippable.
    # ``market_ids`` is therefore derived from the members below, which the
    # chunk has to carry anyway.
    by_bucket_vm: dict[int, set[str]] = {}
    by_bucket_members: dict[int, set[str]] = {}
    for row in rows:
        raw_vm = _get(row, UNIT_KEY_VM_ID)
        raw_market = _get(row, "market_id")
        if raw_vm is None or str(raw_vm) == "" or raw_market is None:
            raise ValueError("roster row is missing vm_id or market_id; cannot plan units")
        vm_id = str(raw_vm)
        market_id = int(raw_market)
        source = _text(_get(row, "source"))
        # ``market_ids`` is recovered by splitting these members apart again, so
        # a separator inside a field would make the member row ambiguous. Refuse
        # loudly rather than mis-parse. This is not only a parsing concern: two
        # different rosters could already collide on ``member_digest`` this way,
        # so the encoding was always relying on it and nothing said so.
        if MEMBER_SEPARATOR in vm_id or MEMBER_SEPARATOR in source:
            raise ValueError(
                "roster row has a record separator inside vm_id or source; "
                "the membership encoding cannot represent it unambiguously"
            )
        # Computed per ROW rather than memoised per ``vm_id``: a memo dict would
        # reintroduce exactly the per-``vm_id`` entry this change removes. It is
        # one short-string hash, and the beat is minutes long.
        index = bucket_of(vm_id, buckets)
        by_bucket_vm.setdefault(index, set()).add(vm_id)
        # The membership digest is per ROSTER ROW, not per market: source and
        # is_grouped are exactly what generation_fingerprint watches globally,
        # and a unit that resumes must be able to see them change.
        by_bucket_members.setdefault(index, set()).add(
            MEMBER_SEPARATOR.join(
                (
                    str(market_id),
                    source,
                    vm_id,
                    _flag(_get(row, "is_grouped")),
                )
            )
        )

    chunks: list[UnitChunk] = []
    # ``sorted`` materialises the key list, so popping inside the loop is safe.
    # CAL-P037: pop rather than read. A bucket's members are dead the moment its
    # digest exists, and holding all 128 buckets' sets until the function
    # returns keeps the whole 57.9 MB alive across the chunk-building pass for
    # no reason. Popping frees each bucket as it is consumed.
    for index in sorted(by_bucket_vm):
        members = by_bucket_members.pop(index)
        # The dedupe is per ``vm_id`` and deliberately NOT global. The roster
        # carries a row per (market, source), and ``vm_id`` is derived with
        # source-scoped group/event sizes, so one ``market_id`` can legitimately
        # sit under two different ``vm_id``s — both are real memberships and the
        # chunk's restriction predicate needs both. Collapsing over SOURCE only
        # is what reproduces the old per-``vm_id`` list exactly.
        pairs = set()
        for member in members:
            market_text, _source, member_vm, _flagged = member.split(MEMBER_SEPARATOR)
            pairs.add((member_vm, int(market_text)))
        # ``sorted`` on each set reproduces the old ordering: the previous code
        # appended ``vm_id``s in ``sorted(by_vm)`` order and sorted both
        # ``market_ids`` and ``members`` on the way into the chunk.
        #
        # CAL-P037: the chunk is built WITH its members, its digest is taken,
        # and the members are then dropped. The digest is therefore produced by
        # the same property every other caller reads, on a chunk holding the
        # same tuple the old planner returned — so byte-identity is structural
        # here rather than a claim a test has to be trusted to police (one
        # polices it anyway, against the pre-CAL-P036 accumulator).
        complete = UnitChunk(
            index=index,
            vm_ids=tuple(sorted(by_bucket_vm.pop(index))),
            market_ids=tuple(sorted(market for _vm, market in pairs)),
            members=tuple(sorted(members)),
            buckets=buckets,
        )
        # ``complete`` has no stored digest, so this is the members-based path
        # of the public property — not a second derivation reached around it.
        chunks.append(
            replace(complete, members=(), stored_member_digest=complete.member_digest)
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
# The running fold (CAL-P034)
# =============================================================================


def _known_columns(census_columns: Sequence[str]) -> set[str]:
    return (
        set(GROUP_KEY_COLUMNS)
        | set(ADDITIVE_COLUMNS)
        | set(census_columns)
        | {AVG_PROB_COLUMN}
    )


def split_unit_rows(
    rows: Iterable[Any],
    *,
    census_columns: Sequence[str] = DECLARED_CENSUS_COLUMNS,
) -> tuple[list[tuple[tuple, dict[str, Any]]], list[dict[str, Any]]]:
    """One unit's rows as ``(bucket mass, census carriers)``.

    The split :func:`merge_futures_rows` performs implicitly, hoisted to bank
    time so the mass can be folded and the rows thrown away.

    **Bucket mass** is ``(group key, additive values)`` — the only part of a row
    that survives a merge. Everything else about a bucket row is either derived
    (``avg_prob``, recomputed from the sums) or constant across the chunk (the
    census passthroughs).

    **Census carriers** are rows the finalizer must see individually, and there
    are two kinds, matching what the frozen call site already does with them:

    * a genuinely null-keyed row — an empty chunk's carrier, kept whole; and
    * a synthetic carrier holding the census read off this unit's FIRST bucket
      row, which is where :func:`merge_futures_rows` takes a chunk's census
      from today. Marked ``bucket_idx=None`` so the finalizer routes it into
      ``extra_censuses``, which contributes it exactly once — the same arity as
      the per-chunk census it replaces.

    A unit with both kinds yields both, because that is what happens today: the
    finalizer strips null-keyed rows into ``extra_censuses`` and
    :func:`merge_futures_rows` still takes a census off the first surviving
    bucket row. Replicated rather than tidied, because "tidier" here would mean
    a different census total.

    Raises :class:`UndeclaredColumnError` on a column that is not a group key,
    not additive, not ``avg_prob`` and not declared census — the same refusal
    :func:`merge_futures_rows` makes, moved to the last point where a unit's
    rows are seen whole. Without it here the fold would route an undeclared
    column into the carrier and BROADCAST it, which is precisely the
    "freezes one chunk's mass onto every row" failure that guard exists for.
    """
    known = _known_columns(census_columns)
    mass: list[tuple[tuple, dict[str, Any]]] = []
    carriers: list[dict[str, Any]] = []
    census_taken = False
    for row in rows or ():
        mapping = _row_mapping(row)
        undeclared = sorted(set(mapping.keys()) - known)
        if undeclared:
            raise UndeclaredColumnError(
                "undeclared column(s) in a chunk result: " + ", ".join(undeclared)
            )
        if mapping.get("bucket_idx") is None:
            carriers.append(dict(mapping))
            continue
        if not census_taken:
            carrier = {name: mapping[name] for name in census_columns if name in mapping}
            carrier["bucket_idx"] = None
            carriers.append(carrier)
            census_taken = True
        mass.append(
            (
                tuple(mapping.get(name) for name in GROUP_KEY_COLUMNS),
                {name: mapping.get(name) for name in ADDITIVE_COLUMNS},
            )
        )
    return mass, carriers


def fold_unit_rows(
    accumulated: Iterable[Any],
    carried: Iterable[Any],
    rows: Iterable[Any],
    *,
    census_columns: Sequence[str] = DECLARED_CENSUS_COLUMNS,
) -> tuple[list[SimpleNamespace], list[SimpleNamespace]]:
    """Add one unit to the running total. Returns ``(buckets, carriers)``.

    **This is the change CAL-P034 exists for.** The cursor used to retain every
    banked row so finalization could fold them all at the end. Measured on the
    live cursor at 91/128 units: 44,272 retained rows carrying **1,586** distinct
    group keys — 27.9x redundancy, rising with every unit because rows grow
    linearly while the group space saturates (469 groups at one unit, 1,586 at
    ninety-one). At 128 units it is ~62,300 rows for ~1,650 groups.

    Retaining the fold instead makes the cursor **bounded by the group space**
    rather than by the number of units — and the cursor is re-serialised in FULL
    after every unit (per-unit ``save_staged_cursor``, which is what caps a
    SIGKILL's cost at one unit), so the old shape spent O(units²) bytes in
    ``json.dumps``: ~960 MB across a full walk, against ~51 MB for this one.

    The arithmetic is :func:`merge_futures_rows`' own, deliberately identical:
    integers summed as integers, the two doubles through :func:`_as_float`.
    Reusing that function directly is not possible — it needs the declared
    census set to broadcast, and broadcasting a running total onto its own rows
    every unit would re-observe it as a fresh census each time.

    **One declared difference, and it is the existing one.** Folding happens in
    COMMIT order; the old shape summed in PLAN order at the end. For ``n`` and
    ``winners`` that is exact either way. For ``sum_prob`` and ``sum_sq_err`` it
    is a reassociation of the same addends — the difference this module's own
    merge docstring already declines to promise away, bounded well below the
    payload's 4-decimal rounding.
    """
    acc: dict[tuple, dict[str, Any]] = {}
    order: list[tuple] = []
    for row in accumulated or ():
        mapping = _row_mapping(row)
        key = tuple(mapping.get(name) for name in GROUP_KEY_COLUMNS)
        if key not in acc:
            acc[key] = {name: mapping.get(name) for name in ADDITIVE_COLUMNS}
            order.append(key)

    mass, new_carriers = split_unit_rows(rows, census_columns=census_columns)
    for key, values in mass:
        entry = acc.get(key)
        if entry is None:
            entry = {name: 0 for name in ADDITIVE_COLUMNS}
            acc[key] = entry
            order.append(key)
        for name in ADDITIVE_COLUMNS:
            value = values.get(name)
            if name in INTEGER_ADDITIVE_COLUMNS:
                entry[name] = _as_int(entry[name]) + _as_int(value)
            else:
                entry[name] = _as_float(entry[name]) + _as_float(value)

    buckets = [
        SimpleNamespace(
            **dict(zip(GROUP_KEY_COLUMNS, key)),
            **{
                name: (
                    _as_int(acc[key][name])
                    if name in INTEGER_ADDITIVE_COLUMNS
                    else _as_float(acc[key][name])
                )
                for name in ADDITIVE_COLUMNS
            },
        )
        for key in order
    ]
    carriers = [
        row if isinstance(row, SimpleNamespace) else SimpleNamespace(**_row_mapping(row))
        for row in list(carried or ())
    ] + [SimpleNamespace(**item) for item in new_carriers]
    return buckets, carriers


def encode_accumulator(
    buckets: Iterable[Any], carriers: Iterable[Any]
) -> dict[str, Any]:
    """The running fold, JSON-safe, through CAL-P033's envelope.

    Reusing :func:`encode_unit_rows` rather than inventing a second encoding is
    the whole of CAL-P033's lesson applied one level up: the bug it fixed was
    two representations of a banked row, not a wrong one.
    """
    return {
        "schema": ACCUMULATOR_SCHEMA,
        "buckets": encode_unit_rows(buckets),
        "carriers": encode_unit_rows(carriers),
    }


def is_encoded_accumulator(stored: Any) -> bool:
    """Whether ``stored`` is an :func:`encode_accumulator` envelope."""
    return (
        isinstance(stored, Mapping)
        and stored.get("schema") == ACCUMULATOR_SCHEMA
        and is_encoded_unit_rows(stored.get("buckets"))
        and is_encoded_unit_rows(stored.get("carriers"))
    )


def decode_accumulator(stored: Any) -> tuple[list[SimpleNamespace], list[SimpleNamespace]]:
    """An accumulator envelope back to ``(buckets, carriers)``."""
    if not is_encoded_accumulator(stored):
        return [], []
    return (
        decode_unit_rows(stored.get("buckets")),
        decode_unit_rows(stored.get("carriers")),
    )


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
    #: **The running fold, not the banked rows** (CAL-P034). An
    #: :func:`encode_accumulator` envelope, or ``None`` when nothing is banked.
    #: Bounded by the group space (~1,650 rows) instead of by units (~62,300 at
    #: 128), because a bucket is a price band and every unit re-states the same
    #: bands. The rows themselves are gone by design: their only consumer was a
    #: merge that immediately summed them.
    accumulator: Optional[dict[str, Any]] = None
    terminal: str = TERMINAL_PARTIAL
    #: unit key -> the :attr:`UnitChunk.member_digest` that unit was BANKED
    #: against (CAL-P028). Compared against the current plan by
    #: :func:`roster_drift` to count how many held units the roster has moved
    #: under. Empty on a cursor written before CAL-P028, which reads as
    #: "unknown", never as "no drift".
    unit_digests: dict[str, str] = field(default_factory=dict)
    #: Units the roster moved under, measured at the START of the beat that
    #: wrote this cursor, BEFORE the digests were re-stamped. Carried on the
    #: cursor rather than only in the ledger because the run that would report
    #: it is exactly the run most likely to die before reporting anything
    #: (gotcha #53) — 181 consecutive beats did.
    roster_drift_units: int = 0

    def has(self, key: Any) -> bool:
        """Whether this unit is banked.

        CAL-P034: a unit's rows no longer exist separately — they are summed
        into :attr:`accumulator` — so the key IS the evidence. The old
        "committed AND carries rows" check has moved to
        :func:`decode_staged_cursor_detailed`, which refuses a cursor claiming
        committed units with no accumulator behind them.
        """
        return unit_key(key) in self.committed_units

    def folded(self) -> tuple[list[SimpleNamespace], list[SimpleNamespace]]:
        """The running fold as ``(buckets, carriers)``, decoded."""
        return decode_accumulator(self.accumulator)

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
            "accumulator": self.accumulator,
            "terminal": self.terminal,
            "unit_digests": dict(self.unit_digests),
            "roster_drift_units": self.roster_drift_units,
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
    if not isinstance(committed, list):
        return blank, INVALIDATE, REASON_MALFORMED_UNITS

    # CAL-P034. A cursor from before the fold holds ``unit_results`` — either
    # CAL-P033's per-unit envelopes or, older still, the ``list[str]`` reprs
    # CAL-P033 refuses. Both are refused HERE, whole, ahead of the accumulator
    # check, so the operator sees which shape they had rather than a generic
    # "malformed". Folding them on read was considered and rejected: it would
    # mean holding a third accepted representation (CAL-P033's lesson was that
    # two is already one too many) and the fold-on-resume would materialise
    # every banked row at once — the very peak this queue removes.
    if raw.get("unit_results"):
        legacy = raw.get("unit_results")
        unencoded = isinstance(legacy, dict) and any(
            not is_encoded_unit_rows(value) for value in legacy.values()
        )
        return (
            blank,
            INVALIDATE,
            REASON_UNENCODED_UNITS if unencoded else REASON_UNFOLDED_UNITS,
        )

    stored_accumulator = raw.get("accumulator")
    if committed and not is_encoded_accumulator(stored_accumulator):
        # Units claimed with no fold behind them. The pre-CAL-P034 filter made
        # the same refusal per unit ("marked done with no rows is a bookkeeping
        # error"); with one shared accumulator it is necessarily all-or-nothing.
        return blank, INVALIDATE, REASON_MALFORMED_UNITS

    # CAL-P034: the per-unit resumability filter that stood here is gone with
    # the per-unit rows. Its job — never treat a unit as done when its mass is
    # not actually carried — is now done by the accumulator check above, which
    # is all-or-nothing because the fold is shared. A name that is not a string
    # is still no kind of unit key.
    resumable = tuple(name for name in committed if isinstance(name, str))
    stored_digests = raw.get("unit_digests")
    if not isinstance(stored_digests, dict):
        # Absent (a pre-CAL-P028 cursor) or malformed. Both mean "we cannot say
        # what these units were banked against", which is unknown drift — the
        # empty mapping makes roster_drift report 0 measured, never 0 actual.
        stored_digests = {}
    return (
        StagedFuturesCursor(
            population_version=expected_population_version,
            input_fingerprint=expected_input_fingerprint,
            generation_fingerprint=expected_generation_fingerprint,
            generation=generation,
            owner=owner,
            lease_expires_at=lease_expires_at,
            committed_units=resumable,
            # Carried through verbatim. Re-encoding it here would decode and
            # re-encode ~1,650 rows on every beat's first read for no gain, and
            # a reshaping step is exactly what this module keeps being bitten
            # by.
            accumulator=stored_accumulator if resumable else None,
            terminal=str(raw.get("terminal") or TERMINAL_PARTIAL),
            # Only for units we are actually resuming. A digest for a unit whose
            # rows did not survive the resumability filter describes work this
            # cursor is not carrying, and keeping it would let a later drift
            # count include units nobody is holding.
            unit_digests={
                name: str(digest)
                for name, digest in (stored_digests or {}).items()
                if name in set(resumable) and isinstance(digest, str)
            },
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

    A unit is kept iff its key is in the plan. **CAL-P028 made the key the unit's
    SLOT rather than its membership**, so in normal operation nothing is dropped:
    slot ``i`` of a 128-way partition is still slot ``i`` after a market arrives.
    What remains droppable is a unit that is genuinely not in the plan — a
    changed bucket count, or a slot that emptied out — and those must still go,
    because resuming them would merge rows for questions the plan no longer asks
    about.

    It also STAMPS each kept unit with the digest of what the plan now says that
    unit contains, having first counted how many disagreed with what was banked
    (:func:`roster_drift`). Order matters and is the whole point: measure, then
    re-stamp. Re-stamping first would make every beat report zero drift forever,
    which is the comfortable answer and a false one.

    Idempotent in the sense that matters — running it twice against the same
    plan drops the same units and lands on the same digests. The second run
    reports zero drift, correctly: by then nothing is banked that the plan
    disagrees with.
    """
    chunk_list = list(chunks)
    planned = {unit_key(chunk) for chunk in chunk_list}
    drift = roster_drift(cursor, chunk_list)
    digests = {
        unit_key(chunk): chunk.member_digest
        for chunk in chunk_list
        if isinstance(chunk, UnitChunk)
    }
    kept = tuple(name for name in cursor.committed_units if name in planned)
    dropped = tuple(name for name in cursor.committed_units if name not in planned)
    if dropped:
        # CAL-P034 — FAIL CLOSED. A fold cannot be inverted: the dropped unit's
        # mass is already summed into the accumulator and there is no way to
        # subtract it, so keeping the accumulator would publish rows for
        # questions the plan no longer asks about — ``LATE_ARRIVAL_NOT_
        # INVALIDATED``, the exact failure this function exists to prevent.
        # Everything goes, and the walk restarts.
        #
        # This does not fire today and is not expected to: CAL-P028 made the
        # unit key the SLOT ``(buckets, index)``, every slot is planned every
        # beat, and CAL-P033 settled from source that nothing is ever dropped.
        # It is written because "cannot happen today" and "is safe if it
        # happens" are different claims, and only the second one is checkable.
        return (
            replace(
                cursor,
                committed_units=(),
                accumulator=None,
                unit_digests={},
                roster_drift_units=drift,
            ),
            dropped,
        )
    return (
        replace(
            cursor,
            committed_units=kept,
            unit_digests={name: digests[name] for name in kept if name in digests},
            roster_drift_units=drift,
        ),
        dropped,
    )


def roster_drift(cursor: StagedFuturesCursor, chunks: Iterable[Any]) -> int:
    """How many BANKED units the roster has moved under since they were banked.

    The number CAL-P016 was reaching for when it threw the units away instead of
    counting them. A unit drifts when the plan's current membership digest for
    its slot differs from the digest stored when the unit ran: some market
    entered or left that slot afterwards, so the banked rows are a census of a
    slightly older population.

    Counts only units that are BOTH banked and carry a stored digest. A unit
    with no stored digest (a pre-CAL-P028 cursor) is not counted, because
    "we cannot tell" must not be published as "it did not drift" — that is the
    empty-200 mistake of gotcha #53 one table over. A unit the plan no longer
    contains is likewise not counted here: it is not drift, it is a drop, and
    :func:`retain_planned_units` reports it as one.
    """
    current = {
        unit_key(chunk): chunk.member_digest
        for chunk in chunks
        if isinstance(chunk, UnitChunk)
    }
    return sum(
        1
        for name in cursor.committed_units
        if name in cursor.unit_digests
        and name in current
        and current[name] != cursor.unit_digests[name]
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
    census_columns: Sequence[str] = DECLARED_CENSUS_COLUMNS,
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
    # CAL-P034: fold, do not bank. The idempotence guard above is what makes
    # this safe — a fold cannot be un-added, so banking the same unit twice
    # would double its mass silently. That guard predates this change and was
    # merely a tidiness rule before; it is load-bearing now.
    accumulated, carried = cursor.folded()
    buckets, carriers = fold_unit_rows(
        accumulated, carried, rows, census_columns=census_columns
    )
    return replace(
        cursor,
        owner=owner,
        lease_expires_at=lease_expires_at,
        committed_units=tuple(list(cursor.committed_units) + [key]),
        # CAL-P033: encode on the way IN, so a unit's representation never
        # depends on whether the process that computed it is still alive.
        accumulator=encode_accumulator(buckets, carriers),
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
    return planned == set(cursor.committed_units)


def collect_unit_results(
    cursor: StagedFuturesCursor, chunks: Sequence[Any]
) -> list[list[Any]]:
    """The running fold, shaped as the chunk list the finalizer expects.

    **The signature and the consumer are unchanged on purpose.** The only call
    site is in ``precompute_calibration``, which ruling 009 bars this lane from
    editing, and it does its own census/bucket split on whatever comes back:
    null-keyed rows go to ``extra_censuses``, the rest to
    :func:`merge_futures_rows`. So this returns ONE chunk carrying the folded
    bucket rows plus every retained carrier, and the finalizer separates them
    exactly as it always has.

    ``chunks`` is now only a completeness signal — the plan order it used to
    impose is already baked into the fold. It stays in the signature because the
    caller passes it and this lane cannot change that call.

    **Re-merging an already-folded set must be a no-op**, and that is the
    property this whole change rests on: each group appears once, so the sums
    pass through; ``avg_prob`` is recomputed from those sums either way; the
    census arrives entirely through the carriers, so the folded rows contribute
    no census observation of their own and nothing is double-counted; and the
    output is re-sorted by the same key. Asserted directly by
    ``test_refolding_a_folded_set_changes_nothing``, not assumed.
    """
    buckets, carriers = cursor.folded()
    return [list(buckets) + list(carriers)]
