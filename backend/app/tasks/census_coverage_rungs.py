"""CAL-P1214 (#997, #1544) — the coverage census as BOUNDED ADDITIVE work.

Codex authorization 2026-09-14T13:24Z, shape (b), as substrate of the already
queued milestone-4 ship: *the accuracy page explains which outcomes are included
and which are excluded.* The eleven rungs already exist as a contract
(:mod:`app.utils.calibration_coverage_bridge`) and as SQL
(``precompute_calibration._COVERAGE_RUNG_PREDICATES``). What did not exist is a
way to COUNT them without paying for it with the curve.

WHY A SECOND PASS AND NOT THE SWITCH THAT IS ALREADY THERE
----------------------------------------------------------
``precompute_calibration.COVERAGE_CENSUS_ENABLED`` fuses the rung columns into
the staged unit statement. That is the cheaper *arithmetic* — the population is
already materialized, so the extra columns cost one scan plus hash joins, and a
plan-only read on 2026-09-14 put it at **+32.1% planner units per unit**
(253,792 -> 335,247; planner units, NOT milliseconds, and not a runtime
measurement). It is nonetheless the wrong lever, for a reason that has nothing
to do with arithmetic:

``staged_unit_fingerprint()`` hashes the EMITTED STATEMENT TEXT, by design — "a
staged unit is rows produced by one statement". Flipping the flag therefore
changes every unit's fingerprint, invalidates the entire served bank, and the
curve stops publishing until 128 units have been rebuilt from scratch. That is
the contract working correctly, not a bug to route around: the alternative is a
payload whose buckets came from one statement shape and whose census came from
another.

So the census is built HERE instead, as its own bounded, resumable, separately
versioned state that:

* never appears in the curve's statement, so ``staged_unit_fingerprint()`` does
  not move and **not one banked unit is thrown away**;
* walks the SAME chunks, in the SAME partition, over the SAME roster, using the
  SAME eleven predicates — imported, never restated (see the drift guard below);
* publishes only a COMPLETE walk of ONE roster, stamped with that roster's
  digest, so a reader can prove the census and the curve describe one world;
* cannot make the curve late, because nothing on the publish path waits for it.

WHAT THIS MODULE DELIBERATELY IS NOT
------------------------------------
It is **not a second staged bank.** There is no accumulator, no fold, no lease,
no per-unit row storage — a walk's whole state is thirteen integers, a roster
digest and the set of slots already counted. The curve's bank exists because a
unit produces BUCKET ROWS that must be merged; a coverage unit produces one row
of counts, which sums. Building the heavier machinery again would be the "new
generalized infrastructure" the authorization rules out.

It is **not wired to a beat** (Invariant 6: a beat edit is a declared,
serialized Integrator review), and nothing in the publish path calls it. Until
an operator or a later rung invokes it, the payload keeps saying
``unavailable``, which is the honest state rather than a stale one. This follows
:mod:`app.tasks.census_reachability`, which made exactly the same call for
exactly the same reason.

ONE DEFINITION OF A RUNG
------------------------
:func:`coverage_bridge_ctes` re-assembles the census CTEs because the canonical
builder is gated behind ``COVERAGE_CENSUS_ENABLED`` and returns ``""`` while the
flag is off — it cannot be called from here without flipping the very switch
this module exists to avoid. The PREDICATES themselves are imported, so the
contract has one home. The assembly is pinned by
``test_census_coverage_rungs_p1214.py::test_ctes_are_byte_identical_to_the_canonical_builder``,
which patches the flag on and asserts the two texts are character-for-character
equal. That test is the reason a copy is safe here: if either side moves, it
reddens, which is strictly louder than a shared helper that silently accepts a
new argument.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from typing import Any, Iterable, Mapping, Sequence

from sqlalchemy import text

from app.utils.calibration_coverage_bridge import PLOTTED_RUNG, RUNG_KEYS

#: This state's OWN version, deliberately separate from
#: ``STAGED_FUTURES_SCHEMA``. The curve's bank and this walk invalidate on
#: different things and must be able to move independently: a change to the rung
#: ladder invalidates the census and must NOT invalidate the curve, which is the
#: whole point of the split.
COVERAGE_RUNG_SCHEMA = "calibration-coverage-rungs/v1"

#: Redis key holding the last COMPLETE, roster-stamped walk.
PUBLISHED_KEY = "calibration:coverage_rung_census"

#: Redis key holding an IN-PROGRESS walk. Separate from the published key on
#: purpose: a partial walk must never be one malformed read away from being
#: served as a total (gotcha #53 — an empty 200 is not an absence).
WORKING_KEY = "calibration:coverage_rung_census:working"

#: The published census goes stale rather than silently ageing. A roster moves
#: whenever a market resolves, so a census whose roster digest no longer matches
#: is refused by :func:`reconcile` long before this expires; the TTL is the
#: backstop for the case where nothing is running at all.
PUBLISHED_TTL_SECONDS = 60 * 60 * 30  # 30h — survives a missed refresh, not a missed week

#: An in-progress walk is worth resuming for a few hours and no longer: past
#: that the roster has almost certainly moved and the work would be discarded by
#: :func:`resume_or_restart` anyway.
WORKING_TTL_SECONDS = 60 * 60 * 6

#: Per-statement timeout for one chunk. Fail this unit fast and resume it next
#: call rather than hold a connection open — the walk is resumable precisely so
#: that a slow unit costs one unit, not the walk.
DEFAULT_UNIT_TIMEOUT = "20s"

#: Per-statement timeout for the single global rung. It is one pass over the
#: coverage universe plus a hash anti-join, but over the UNSCOPED population, so
#: it is the one statement here that is not chunk-bounded.
DEFAULT_GLOBAL_TIMEOUT = "60s"

#: The extra columns the summary carries beside the eleven rungs. Named rather
#: than discovered, so a walk that loses one is a KeyError here and not a
#: plausible wrong total downstream.
TOTAL_COLUMN = "cb_coverage_total"
TERMINAL_PRICE_COLUMN = "cb_with_terminal_cal_price"

# --- Why a walk was not resumed. Short stable tokens, following the staged
# cursor's convention: the question worth asking is never "why did this one
# reset" but "which cause resets us every time".
REASON_ABSENT = "absent"
REASON_MALFORMED = "malformed"
REASON_SCHEMA = "schema_mismatch"
REASON_POPULATION_VERSION = "population_version_changed"
REASON_ROSTER_MOVED = "roster_digest_changed"
REASON_PARTITION = "partition_size_changed"

# --- Why a published census was not attached to a payload.
REASON_NO_CENSUS = "no_complete_coverage_census_published"
REASON_CENSUS_STALE_ROSTER = "coverage_census_roster_predates_current_build"
REASON_PAYLOAD_NOT_CURRENT = "payload_generation_is_not_the_current_build"
REASON_VERSION_MISMATCH = "population_version_mismatch"


def coverage_bridge_column(rung: str) -> str:
    """The summary column name carrying ``rung``'s count.

    Restated rather than imported so this module's SQL can be built without
    importing the 550 KB producer; the drift guard asserts the two agree.
    """
    return f"cb_{rung}"


# ---------------------------------------------------------------------------
# THE STATEMENTS
# ---------------------------------------------------------------------------


def coverage_bridge_ctes(*, roster_predicate: str) -> str:
    """The census CTEs, chunk-scoped, byte-identical to the canonical builder.

    See the module docstring for why this is re-assembled rather than called.
    The predicates and the rung ORDER come from the producer; only the assembly
    is here, and the assembly is pinned by a byte-equality test.
    """
    from app.tasks.precompute_calibration import (  # local: 550 KB module
        _COVERAGE_RUNG_PREDICATES,
        _coverage_universe_cte,
    )

    branches = "\n                        ".join(
        f"WHEN {sql} THEN '{key}'"
        for key, sql in _COVERAGE_RUNG_PREDICATES
        if sql
    )
    terminal = _COVERAGE_RUNG_PREDICATES[-1][0]
    filters = ",\n                    ".join(
        f"COUNT(*) FILTER (WHERE rung = '{key}') AS {coverage_bridge_column(key)}"
        for key in RUNG_KEYS
    )
    return (
        ","
        + _coverage_universe_cte(chunk_scoped=True, roster_predicate=roster_predicate)
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
                -- D112 (#997, CAL-P1138): market shape for the
                -- ``truth_ineligible_source`` rung, so the bridge's negation
                -- reads the same eligibility the population scan applies.
                -- LEFT and one-row-per-market, for ruling 125's reason: a join
                -- added to supply a new column must not be able to change which
                -- rows the relation carries. ``market_result_shape`` groups by
                -- market_id (plus two per-market columns), so it cannot
                -- multiply; LEFT so a market without a shape row keeps its row
                -- here instead of vanishing from the coverage total.
                LEFT JOIN market_result_shape mrs_cov
                    ON mrs_cov.market_id = cu.market_id
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


def chunk_rung_sql() -> str:
    """One chunk's eleven rung counts, and nothing else.

    The population chain is named in full and the statement selects only from
    ``coverage_bridge_summary``: PostgreSQL does not execute an unreferenced
    ``WITH`` subquery, so the bucket aggregation, the liquidity summary and the
    published summary — everything the curve needs and the census does not — are
    planned away. What runs is the population chain restricted to this chunk's
    roster, plus one pass over its coverage universe.

    The roster is bound by the SAME three array parameters the curve's chunk
    statement uses, so a caller cannot accidentally scope the two differently.
    """
    from app.tasks.precompute_calibration import (
        VM_ROSTER_MARKET_INFO_EXTRA,
        _calibration_population_ctes,
        _roster_pushdown_predicates,
    )

    _vm_pred, mi_roster_predicate = _roster_pushdown_predicates(
        frozen_vm_roster=True,
        market_info_extra=VM_ROSTER_MARKET_INFO_EXTRA,
    )
    universe = _coverage_universe_is_chunk_scoped(mi_roster_predicate)
    return (
        "WITH "
        + _calibration_population_ctes(
            frozen_vm_roster=True,
            market_info_extra=VM_ROSTER_MARKET_INFO_EXTRA,
        )
        + universe
        + """
            SELECT * FROM coverage_bridge_summary
        """
    )


def _coverage_universe_is_chunk_scoped(roster_predicate: str) -> str:
    """Build the census CTEs and REFUSE if the universe escaped its chunk.

    The same guard the canonical builder carries, for the same measured reason:
    under a frozen scope an unscoped ``coverage_universe`` rescans every resolved
    priced outcome in every chunk and LEFT JOINs it against only that chunk's
    ``normalized``/``deduped``, so ``cb_coverage_total`` comes out ~N times the
    real figure with the rungs badly skewed. A census wrong in the CONFIDENT
    direction is the one thing the 300C bridge exists to prevent.
    """
    ctes = coverage_bridge_ctes(roster_predicate=roster_predicate)
    if "JOIN market_info" not in ctes:
        raise ValueError(
            "coverage rung walk is not chunk-scoped: its universe would be "
            "rescanned once per chunk and the census multiplied by the chunk "
            "count. Refusing to build the statement."
        )
    return ctes


def global_rung_sql() -> str:
    """The one rung whose members belong to no chunk, counted once per roster.

    Imported verbatim from the producer rather than restated: this is the
    DataGolf-residual cohort (``mi.market_id IS NULL``), and a second copy of
    the predicate would put the census and the curve on different definitions
    of "eligible market".
    """
    from app.tasks.precompute_calibration import _coverage_global_rung_sql

    return _coverage_global_rung_sql()


# ---------------------------------------------------------------------------
# THE STATE — thirteen integers, a roster digest, and which slots are done
# ---------------------------------------------------------------------------

#: Every column a walk accumulates: the eleven rungs plus the two totals.
ACCUMULATED_COLUMNS: tuple[str, ...] = tuple(
    coverage_bridge_column(key) for key in RUNG_KEYS
) + (TOTAL_COLUMN, TERMINAL_PRICE_COLUMN)


@dataclass(frozen=True)
class CoverageWalkState:
    """One roster's partial or complete coverage walk.

    ``done_units`` holds chunk KEYS (``buckets:index``), not indices, so a walk
    banked under one partition size can never be resumed under another — the
    same protection ``UnitChunk.key`` gives the curve's bank.
    """

    population_version: str
    roster_digest: str
    buckets: int
    total_units: int
    done_units: tuple[str, ...] = ()
    global_done: bool = False
    totals: Mapping[str, int] = field(default_factory=dict)
    schema: str = COVERAGE_RUNG_SCHEMA

    @property
    def units_remaining(self) -> int:
        return max(0, self.total_units - len(self.done_units))

    @property
    def complete(self) -> bool:
        """Every planned unit AND the global rung, or it is not a total.

        A partial walk's counts are real but its denominator is not the
        population, and a number that looks like a total while covering 60% of
        the rows is worse than no number at all.
        """
        return self.global_done and len(self.done_units) >= self.total_units > 0


def new_state(
    *, population_version: str, roster_digest: str, buckets: int, total_units: int
) -> CoverageWalkState:
    """A fresh walk with every accumulated column at a CHECKED zero."""
    return CoverageWalkState(
        population_version=population_version,
        roster_digest=roster_digest,
        buckets=int(buckets),
        total_units=int(total_units),
        totals={column: 0 for column in ACCUMULATED_COLUMNS},
    )


def absorb_unit(
    state: CoverageWalkState, *, unit_key: str, row: Mapping[str, Any]
) -> CoverageWalkState:
    """Add one chunk's counts. Idempotent — a replayed unit is not double-counted.

    Idempotence is not a nicety here: the walk is resumable, so a unit whose
    statement committed and whose state write did not WILL be replayed, and a
    census that grew every time a call was retried would reconcile to nothing.
    """
    if unit_key in state.done_units:
        return state
    return replace(
        state,
        done_units=state.done_units + (unit_key,),
        totals=_add(state.totals, row),
    )


def absorb_global(
    state: CoverageWalkState, *, row: Mapping[str, Any]
) -> CoverageWalkState:
    """Add the out-of-chunk cohort. Idempotent, for the same reason."""
    if state.global_done:
        return state
    return replace(state, global_done=True, totals=_add(state.totals, row))


def _add(totals: Mapping[str, int], row: Mapping[str, Any]) -> dict[str, int]:
    """Sum a summary row into the accumulator.

    A column the row does not carry contributes 0 rather than raising, because
    the global statement legitimately emits only three of the thirteen. A column
    that is present but not an int is a malformed read and DOES raise — that is
    the difference between "this statement does not measure that" and "this
    statement measured it wrong".
    """
    out = dict(totals)
    for column in ACCUMULATED_COLUMNS:
        if column not in row:
            continue
        value = row[column]
        if value is None:
            value = 0
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(
                f"coverage rung walk: column {column} is {value!r}, not an int"
            )
        out[column] = out.get(column, 0) + int(value)
    return out


def rung_counts_for_bridge(state: CoverageWalkState) -> dict[str, int] | None:
    """The mapping :func:`build_coverage_census` wants, or None if unpublishable.

    Fail-closed on an incomplete walk and on a partition that does not add up.
    ``None`` routes the payload to the explicit ``unavailable`` section, which is
    the honest answer; a partial total is not.
    """
    if not state.complete:
        return None
    counts = {key: int(state.totals.get(coverage_bridge_column(key), 0)) for key in RUNG_KEYS}
    # The rungs are a PARTITION of the coverage universe, so they must sum to
    # the universe's own count. The two are different reads of the same CTE; if
    # they ever disagree the CASE stopped being a partition and the census must
    # refuse rather than publish a number.
    if sum(counts.values()) != int(state.totals.get(TOTAL_COLUMN, -1)):
        return None
    # The terminal rung cannot exceed the whole it is a part of.
    if counts[PLOTTED_RUNG] > sum(counts.values()):
        return None
    return counts


# ---------------------------------------------------------------------------
# RESUME / PUBLISH / READ
# ---------------------------------------------------------------------------


def resume_or_restart(
    stored: Any,
    *,
    population_version: str,
    roster_digest: str,
    buckets: int,
    total_units: int,
) -> tuple[CoverageWalkState, str | None]:
    """Continue a banked walk, or start a fresh one and say why.

    Returns ``(state, reason)`` where ``reason`` is ``None`` for a clean resume
    and one of the ``REASON_*`` tokens otherwise. The reason is returned rather
    than logged so the caller can record WHICH cause resets the walk — the
    question worth asking is never why one walk reset.
    """
    fresh = new_state(
        population_version=population_version,
        roster_digest=roster_digest,
        buckets=buckets,
        total_units=total_units,
    )
    decoded = decode_state(stored)
    if decoded is None:
        return fresh, (REASON_ABSENT if stored in (None, "", b"") else REASON_MALFORMED)
    if decoded.schema != COVERAGE_RUNG_SCHEMA:
        return fresh, REASON_SCHEMA
    if decoded.population_version != population_version:
        return fresh, REASON_POPULATION_VERSION
    if decoded.roster_digest != roster_digest:
        # The roster moved under the walk. Its banked counts describe a
        # population that no longer exists; mixing them with the new one is the
        # LATE_ARRIVAL error the curve's own generation digest exists to catch.
        return fresh, REASON_ROSTER_MOVED
    if decoded.buckets != int(buckets) or decoded.total_units != int(total_units):
        return fresh, REASON_PARTITION
    return decoded, None


def encode_state(state: CoverageWalkState) -> str:
    return json.dumps(
        {
            "schema": state.schema,
            "population_version": state.population_version,
            "roster_digest": state.roster_digest,
            "buckets": state.buckets,
            "total_units": state.total_units,
            "done_units": list(state.done_units),
            "global_done": state.global_done,
            "totals": dict(state.totals),
        },
        sort_keys=True,
    )


def decode_state(stored: Any) -> CoverageWalkState | None:
    """A banked walk, or None for absent/malformed. Never raises."""
    if not stored:
        return None
    try:
        data = json.loads(stored)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    try:
        totals = data.get("totals")
        if not isinstance(totals, dict):
            return None
        clean: dict[str, int] = {}
        for column in ACCUMULATED_COLUMNS:
            value = totals.get(column, 0)
            if isinstance(value, bool) or not isinstance(value, int):
                return None
            clean[column] = value
        done = data.get("done_units") or []
        if not isinstance(done, list) or not all(isinstance(k, str) for k in done):
            return None
        return CoverageWalkState(
            schema=str(data.get("schema") or ""),
            population_version=str(data.get("population_version") or ""),
            roster_digest=str(data.get("roster_digest") or ""),
            buckets=int(data.get("buckets") or 0),
            total_units=int(data.get("total_units") or 0),
            done_units=tuple(done),
            global_done=bool(data.get("global_done")),
            totals=clean,
        )
    except Exception:
        return None


def publish(redis_client, state: CoverageWalkState) -> bool:
    """Write a COMPLETE, reconciled walk to the published key. All or nothing.

    A walk that is incomplete, or whose partition does not sum, writes nothing
    and returns False: the published key is the one place a reader is entitled
    to assume it found a total.
    """
    counts = rung_counts_for_bridge(state)
    if counts is None or redis_client is None:
        return False
    try:
        redis_client.setex(
            PUBLISHED_KEY,
            PUBLISHED_TTL_SECONDS,
            json.dumps(
                {
                    "schema": COVERAGE_RUNG_SCHEMA,
                    "population_version": state.population_version,
                    "roster_digest": state.roster_digest,
                    "counts": counts,
                    "coverage_total": int(state.totals.get(TOTAL_COLUMN, 0)),
                    "with_terminal_calibration_price": int(
                        state.totals.get(TERMINAL_PRICE_COLUMN, 0)
                    ),
                },
                sort_keys=True,
            ),
        )
        return True
    except Exception:
        return False


def read_published(redis_client) -> dict[str, Any] | None:
    """The published census, or None. Never raises into a caller's critical path.

    Fail-open by design: a missing, unreadable, malformed or short-of-a-rung
    cache all return None, which routes the payload to the explicit
    ``unavailable`` section. The one thing this must never do is hand back a
    number it cannot stand behind.
    """
    if redis_client is None:
        return None
    try:
        raw = redis_client.get(PUBLISHED_KEY)
    except Exception:
        return None
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except Exception:
        return None
    if not isinstance(data, dict) or data.get("schema") != COVERAGE_RUNG_SCHEMA:
        return None
    counts = data.get("counts")
    if not isinstance(counts, dict):
        return None
    clean: dict[str, int] = {}
    for key in RUNG_KEYS:
        value = counts.get(key)
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        clean[key] = value
    if not isinstance(data.get("roster_digest"), str) or not data["roster_digest"]:
        return None
    return {
        "population_version": str(data.get("population_version") or ""),
        "roster_digest": data["roster_digest"],
        "counts": clean,
        "with_terminal_calibration_price": (
            data.get("with_terminal_calibration_price")
            if isinstance(data.get("with_terminal_calibration_price"), int)
            else None
        ),
    }


# ---------------------------------------------------------------------------
# THE RECONCILIATION — the clause this whole shape exists to satisfy
# ---------------------------------------------------------------------------


def reconcile(
    published: Mapping[str, Any] | None,
    *,
    cursor_population_version: str | None,
    cursor_roster_digest: str | None,
    cursor_generation: int | None,
    payload_population_version: str | None,
    payload_generation: int | None,
) -> tuple[dict[str, int] | None, str | None]:
    """Attach the census to THIS payload, or refuse and say why.

    Returns ``(counts, reason)``: exactly one is ``None``.

    The authorization's words are "coverage must reconcile to a named published
    generation/roster, never silently join today's coverage to yesterday's
    curve". Two identities are in play and neither alone is sufficient:

    * the **roster digest** is the POPULATION's identity — what the counts are
      about. It is what the walk stamps itself with.
    * the **generation** is the BUILD's identity — which beat produced the
      payload a reader is holding. It is what the payload carries.

    The staged cursor is the only place both are recorded together, so it is the
    hinge. The chain below says: *the census walked the roster the current
    cursor holds, and the current cursor is the one that produced the payload
    being served.* Break any link and the answer is ``unavailable`` with a
    reason — never a number.

    This is why a stale, last-good or durable payload gets no census: its
    generation is not the cursor's, so the chain breaks at the second link and
    the refusal is automatic rather than remembered.
    """
    if not published:
        return None, REASON_NO_CENSUS
    if (
        payload_population_version is None
        or published.get("population_version") != payload_population_version
        or cursor_population_version != payload_population_version
    ):
        return None, REASON_VERSION_MISMATCH
    if not cursor_roster_digest or published.get("roster_digest") != cursor_roster_digest:
        return None, REASON_CENSUS_STALE_ROSTER
    if (
        payload_generation is None
        or cursor_generation is None
        or int(cursor_generation) != int(payload_generation)
    ):
        return None, REASON_PAYLOAD_NOT_CURRENT
    counts = published.get("counts")
    if not isinstance(counts, dict):
        return None, REASON_NO_CENSUS
    return dict(counts), None


# ---------------------------------------------------------------------------
# THE WALK
# ---------------------------------------------------------------------------


async def walk_one_unit(
    session,
    *,
    chunk,
    assignment: Mapping[int, tuple[str, bool]],
    statement_timeout: str = DEFAULT_UNIT_TIMEOUT,
) -> dict[str, int]:
    """Count one chunk's rungs. One statement, one row, bounded by its own timeout."""
    from app.tasks.precompute_calibration import (
        VM_ROSTER_IS_GROUPED_PARAM,
        VM_ROSTER_MARKET_IDS_PARAM,
        VM_ROSTER_VM_IDS_PARAM,
    )

    await session.execute(text(f"SET LOCAL statement_timeout = '{statement_timeout}'"))
    market_ids = list(chunk.market_ids)
    row = (
        await session.execute(
            text(chunk_rung_sql()),
            {
                VM_ROSTER_MARKET_IDS_PARAM: market_ids,
                VM_ROSTER_VM_IDS_PARAM: [assignment[m][0] for m in market_ids],
                VM_ROSTER_IS_GROUPED_PARAM: [assignment[m][1] for m in market_ids],
            },
        )
    ).mappings().first()
    if row is None:
        # An ungrouped aggregate always returns exactly one row. A missing one
        # must abort loudly: absorbing it as zeros would publish a confident 0
        # for a chunk nobody counted (gotcha #53).
        raise ValueError(f"coverage rung walk: unit {chunk.key} returned no summary row")
    return dict(row)


async def walk_global_rung(
    session, *, statement_timeout: str = DEFAULT_GLOBAL_TIMEOUT
) -> dict[str, int]:
    """Count the out-of-chunk cohort. Once per roster, never per chunk."""
    await session.execute(text(f"SET LOCAL statement_timeout = '{statement_timeout}'"))
    row = (await session.execute(text(global_rung_sql()))).mappings().first()
    if row is None:
        raise ValueError("coverage rung walk: global rung returned no summary row")
    return dict(row)


def plan_from_roster(roster: Sequence[Any], *, buckets: int):
    """The SAME partition the curve cuts, from the SAME roster read.

    Returns ``(chunks, assignment, roster_digest)``. Re-derived here rather than
    passed in so the walk cannot be handed a partition the curve never used —
    the chunk boundary is what makes the per-chunk counts additive, and a
    boundary that disagrees with the curve's is additive over the wrong sets.
    """
    from app.utils.calibration_staged_futures import generation_fingerprint, plan_units

    chunks = plan_units(roster, buckets=buckets)
    assignment = {
        int(_attr(row, "market_id")): (
            str(_attr(row, "vm_id")),
            bool(_attr(row, "is_grouped")),
        )
        for row in roster
    }
    return chunks, assignment, generation_fingerprint(roster)


def _attr(row: Any, name: str) -> Any:
    if hasattr(row, name):
        return getattr(row, name)
    mapping = getattr(row, "_mapping", None)
    if mapping is not None:
        return mapping[name]
    return row[name]


def remaining_units(state: CoverageWalkState, chunks: Iterable[Any]) -> list[Any]:
    """The chunks this walk has not counted yet, in partition order."""
    done = set(state.done_units)
    return [chunk for chunk in chunks if chunk.key not in done]


#: Chunks counted per invocation. The walk is bounded so that ONE call has a
#: knowable cost and a caller can stop at any time; the state is resumable so
#: that stopping costs nothing. Deliberately conservative — the point is never
#: to finish in one call, it is to never be the reason something else is late.
DEFAULT_MAX_UNITS = 8


async def run_bounded_walk(
    session,
    redis_client=None,
    *,
    buckets: int | None = None,
    max_units: int = DEFAULT_MAX_UNITS,
    unit_timeout: str = DEFAULT_UNIT_TIMEOUT,
    global_timeout: str = DEFAULT_GLOBAL_TIMEOUT,
) -> dict[str, Any]:
    """Count up to ``max_units`` chunks, bank the progress, publish if complete.

    The whole operable surface of this module, and the only function an operator
    or a later scheduled caller needs. It is safe to invoke at any time and from
    a cold start: it reads the roster, cuts the SAME partition the curve cuts,
    resumes whatever was banked for that roster (or says why it could not), does
    a bounded amount of work and stops.

    **It never writes anything the curve reads, and the curve never waits for
    it.** A failure here leaves the published census exactly as it was, which is
    what "gate publication continuity under incomplete coverage" means in
    practice: the curve's continuity is not something this function can affect.

    The returned dict is the report — what it resumed, why it restarted if it
    did, what it counted, and whether the roster is now fully accounted for.
    """
    # The partition size lives with the build that cuts it, and the population
    # version with the producer. Imported from their own homes rather than
    # re-declared, so the walk cannot be cutting 64 slots while the curve cuts
    # 128 — the chunk boundary is the reason per-chunk counts are additive.
    from app.tasks.calibration_main_build import STAGED_FUTURES_BUCKETS
    from app.tasks.precompute_calibration import (
        CALIBRATION_POPULATION_VERSION,
        _futures_generation_sql,
    )

    buckets = int(buckets or STAGED_FUTURES_BUCKETS)
    roster = (await session.execute(text(_futures_generation_sql()))).all()
    chunks, assignment, roster_digest = plan_from_roster(roster, buckets=buckets)

    if not chunks:
        # An empty population is a real answer, not a failure. There is nothing
        # to count and nothing to publish; saying so is more useful than a
        # census of zeros stamped against a roster with no members.
        return {
            "census": "coverage-rungs",
            "roster_digest": roster_digest,
            "markets": len(roster),
            "units_total": 0,
            "empty_population": True,
            "complete": False,
            "published": False,
        }

    stored = None
    if redis_client is not None:
        try:
            stored = redis_client.get(WORKING_KEY)
        except Exception:
            stored = None

    state, restart_reason = resume_or_restart(
        stored,
        population_version=CALIBRATION_POPULATION_VERSION,
        roster_digest=roster_digest,
        buckets=buckets,
        total_units=len(chunks),
    )

    counted: list[str] = []
    for chunk in remaining_units(state, chunks)[: max(0, int(max_units))]:
        row = await walk_one_unit(
            session,
            chunk=chunk,
            assignment=assignment,
            statement_timeout=unit_timeout,
        )
        state = absorb_unit(state, unit_key=chunk.key, row=row)
        counted.append(chunk.key)

    # The global rung last, and only once every chunk is in: it is the cohort
    # that belongs to no chunk, so counting it early would bank a rung against a
    # roster the rest of the walk may yet be told has moved.
    global_counted = False
    if state.units_remaining == 0 and not state.global_done:
        state = absorb_global(
            state, row=await walk_global_rung(session, statement_timeout=global_timeout)
        )
        global_counted = True

    published = publish(redis_client, state) if state.complete else False

    # Reported rather than swallowed. The cache write is fail-open — it must
    # never be the reason a walk fails — but a walk whose progress has silently
    # stopped being banked would redo the same units for ever and look perfectly
    # healthy doing it, which is the failure mode this whole module is resumable
    # to avoid.
    state_banked: str | None = None
    if redis_client is not None:
        try:
            if published:
                # The working copy has served its purpose. Dropping it means the
                # next call starts a fresh walk of whatever the roster is THEN,
                # rather than resuming one that is already published.
                redis_client.delete(WORKING_KEY)
                state_banked = "published_and_cleared"
            else:
                # Note the branch this also covers: a COMPLETE walk whose
                # publish failed. Banking it means the next call resumes a
                # finished walk and retries the one write that failed, instead
                # of paying for all 128 units again over a transient blip.
                redis_client.setex(
                    WORKING_KEY, WORKING_TTL_SECONDS, encode_state(state)
                )
                state_banked = "working"
        except Exception as exc:  # noqa: BLE001 — fail-open, but never silent
            state_banked = f"failed: {type(exc).__name__}"

    return {
        "census": "coverage-rungs",
        "population_version": state.population_version,
        "roster_digest": roster_digest,
        "markets": len(roster),
        "buckets": buckets,
        "units_total": state.total_units,
        "units_done": len(state.done_units),
        "units_remaining": state.units_remaining,
        "units_counted_this_call": counted,
        "global_rung_counted_this_call": global_counted,
        "global_done": state.global_done,
        "restart_reason": restart_reason,
        "complete": state.complete,
        # Only ever the counts of a COMPLETE, reconciled walk. A partial walk
        # reports its progress above and no numbers here, so nothing downstream
        # can mistake a fragment for a total.
        "counts": rung_counts_for_bridge(state),
        "published": published,
        # What happened to the resumable state: ``working`` (banked),
        # ``published_and_cleared``, ``failed: <ExcType>``, or None when there is
        # no cache at all. A caller that sees ``failed`` repeatedly is watching
        # the walk lose its memory, not doing bounded work.
        "state_banked": state_banked,
    }


async def census(session, apply: bool = False, limit: int | None = None) -> dict[str, Any]:
    """``POST /api/admin/repairs/coverage-rung-census`` — the operator entry point.

    Signature is the repairs dispatcher's (``fn(session, apply, **bounds)``), not
    this module's; ``limit`` is the per-call CHUNK budget. Like every census
    sibling in that map, ``apply`` is accepted and ignored: this never writes
    production data. Its only write is the census cache in Redis, which nothing
    on the publish path reads — so there is nothing here to roll back beyond
    ``DEL calibration:coverage_rung_census{,:working}``.

    Re-invoke until ``complete`` is true; ``units_remaining`` says how far there
    is to go and the walk resumes from where the last call stopped.
    """
    from app.tasks.redis_state import get_redis_client

    return await run_bounded_walk(
        session,
        get_redis_client(),
        max_units=int(limit) if limit else DEFAULT_MAX_UNITS,
    )
