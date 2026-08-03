"""The calibration coverage census + additive bridge contract (Queue 300C).

Alex's 2026-08-02 ruling: the public calibration chart's headline unit is
**published curve observations** (the ~653K rows actually plotted). The ~1.28M
**outcomes with calibration-price coverage** may appear only as a separately
labelled supporting census, joined to the plotted population by an ADDITIVE
bridge. Coverage outcomes must never be described as plotted observations, and
publishing the census must not change the curve.

This module is the frozen contract for that. It is pure — no DB, no Redis, no
clock — so both the canonical build and every test can produce the same object
from the same counts.

TWO UNITS, NEVER INTERCHANGED
-----------------------------
``futures_outcome``     — one resolved futures outcome carrying a usable
                          calibration price. This is the COVERAGE unit.
``curve_observation``   — one row plotted on the published curve. Futures
                          outcomes are only one of its populations; the
                          sportsbook curves (Odds API moneyline, spreads,
                          totals, per-bookmaker moneyline) contribute
                          observations that are not futures outcomes at all.

Because the units differ, ONE subtraction can never bridge them. There are two
reconciliations, and both are computed from directly counted members — never
inferred from a label and never derived as a residual (a residual reconciles by
construction, which is exactly how a miscount hides):

  A. coverage bridge (unit: futures_outcome)
       outcomes_with_calibration_coverage
         = futures_outcomes_plotted + Σ(exclusion rungs)

  B. observation bridge (unit: curve_observation)
       published_curve_observations
         = futures_outcomes_plotted + sportsbook_curve_legs

``futures_outcomes_plotted`` is the hinge that joins them, and it is counted
twice independently (once as the bridge's terminal rung, once by the population
CTE chain's own ``published_summary``); a divergence is a contract violation,
not a rounding difference.

MUTUAL EXCLUSIVITY IS BY PRECEDENCE, NOT BY LABEL
-------------------------------------------------
A single excluded outcome routinely trips several filters at once — an illiquid
Kalshi phantom inside a market that graded nobody is both a phantom and unknown
truth. Summing per-filter exclusion counters (the ones the payload already
publishes for transparency) therefore DOUBLE-COUNTS and can never reconcile.
:data:`BRIDGE_RUNGS` is an ORDERED partition instead: every coverage outcome is
assigned to the FIRST rung it matches, so the rungs sum to the coverage total
exactly. Reordering the tuple is a contract change — it moves outcomes between
rungs — so the order is pinned by the committed corpus.

UNKNOWN NEVER BECOMES ZERO
--------------------------
A rung that could not be measured (the census read timed out, or a served
payload predates the census) is ``None``/``"unknown"`` and forces the whole
census to ``status="incomplete"``. A rung that WAS measured and came back empty
is ``0`` with ``checked=True`` — the "checked-zero" case. The two are different
claims and the payload must be able to tell them apart.
"""

from __future__ import annotations

from typing import Any

COVERAGE_BRIDGE_SCHEMA_VERSION = "calibration-coverage-bridge/v1"

UNIT_FUTURES_OUTCOME = "futures_outcome"
UNIT_CURVE_OBSERVATION = "curve_observation"

STATUS_COMPLETE = "complete"
STATUS_INCOMPLETE = "incomplete"
STATUS_UNAVAILABLE = "unavailable"

#: The terminal rung — the coverage outcomes that DO reach the curve. It is part
#: of the partition (so the rungs sum to coverage) but it is not an exclusion.
PLOTTED_RUNG = "plotted_on_curve"

#: The ordered partition of the coverage population. FIRST MATCH WINS; the SQL
#: ``CASE`` in the canonical build walks this exact order. Each entry is
#: ``(key, rule)`` where ``rule`` is the user-facing sentence explaining why
#: those outcomes are where they are.
BRIDGE_RUNGS: tuple[tuple[str, str], ...] = (
    (
        PLOTTED_RUNG,
        "Plotted on the published curve — survived every eligibility, truth, "
        "liquidity, shape and representative rule.",
    ),
    (
        "market_result_unavailable",
        "The whole market is withheld symmetrically because its result cannot "
        "be established (DataGolf recovery residual): winners AND losers are "
        "dropped together so participation is never one-sidedly assumed.",
    ),
    (
        "truth_source_missing",
        "The outcome carries no resolution source at all, so nothing "
        "independent grades it.",
    ),
    (
        "truth_ineligible_source",
        "The outcome's winner was established by a source that is not "
        "independent of the market's own price (price-derived or guess-family), "
        "so it cannot grade its own forecast.",
    ),
    (
        "question_ungraded",
        "The virtual question this outcome belongs to graded no winner at all, "
        "so its members are unknown truth rather than confident losses.",
    ),
    (
        "malformed_or_unknown_truth",
        "The market's captured result is not a scoreable prediction: nobody "
        "graded a winner, a two-outcome partition graded zero or two, a "
        "draw-capable duel captured no draw member, or a declared field "
        "captured one member or fewer.",
    ),
    (
        "phantom_liquidity",
        "The price is a phantom, not a forecast: a Kalshi outcome that was "
        "never bid and never traded, or a Polymarket no-bid placeholder sitting "
        "in the near-0.50 band.",
    ),
    (
        "structural_artifact",
        "A measured pricing artifact rather than a genuine probability: esports "
        "match bundles, golf one-sided-ask placeholders, Kalshi player-prop "
        "threshold captures in the settlement-collapse band, and wide-spread "
        "weather midpoints.",
    ),
    (
        "field_incomplete",
        "The outcome belongs to a normalization field that lost a member to an "
        "exclusion above, so the partition no longer sums to one and is dropped "
        "whole rather than normalized over its survivors.",
    ),
    (
        "representative_not_selected",
        "The question is published, but this outcome is not the row that "
        "represents it: a non-representative binary side, a placeholder modal "
        "price, or an extreme tail in a non-partition multi pool.",
    ),
)

#: Every rung except the terminal one. These are what the bridge ADDS to the
#: plotted count to get back to coverage.
EXCLUSION_RUNGS: tuple[str, ...] = tuple(
    key for key, _rule in BRIDGE_RUNGS if key != PLOTTED_RUNG
)

RUNG_KEYS: tuple[str, ...] = tuple(key for key, _rule in BRIDGE_RUNGS)

_RUNG_RULES: dict[str, str] = dict(BRIDGE_RUNGS)

COVERAGE_UNIT_RULE = (
    "One resolved futures outcome carrying a usable calibration price "
    "(opening probability strictly between 0 and 1, terminal calibration price "
    "preferred). This is the population calibration COVERS; it is not the "
    "population the curve PLOTS."
)

OBSERVATION_UNIT_RULE = (
    "One row plotted on the published calibration curve. Futures outcomes are "
    "one contributing population; the sportsbook curves (moneyline, spreads, "
    "totals, per-bookmaker moneyline) contribute observations that are not "
    "futures outcomes."
)


def _rung_cell(key: str, value: Any) -> dict[str, Any]:
    """One rung, with its unit, its rule, and an honest measured/unknown state."""
    known = isinstance(value, int) and not isinstance(value, bool)
    return {
        "key": key,
        "unit": UNIT_FUTURES_OUTCOME,
        "outcomes": int(value) if known else None,
        # ``checked`` is the checked-zero discriminator: True + 0 means "we
        # looked and there were none", None means "we could not look".
        "checked": known,
        "rule": _rung_rules(key),
    }


def _rung_rules(key: str) -> str:
    return _RUNG_RULES.get(key, "")


def unavailable_census(
    reason: str,
    *,
    population_version: str | None = None,
    generation: str | None = None,
) -> dict[str, Any]:
    """The census a tier emits when it genuinely has none.

    Explicitly unavailable beats silently absent: a consumer that finds no
    census key cannot tell "this build has no census" from "this build measured
    zero", and the second reading is a lie. Every count is ``None``.
    """
    return {
        "schema_version": COVERAGE_BRIDGE_SCHEMA_VERSION,
        "status": STATUS_UNAVAILABLE,
        "reason": reason,
        "population_version": population_version,
        "generation": generation,
        "units": {
            "published_curve_observations": {
                "unit": UNIT_CURVE_OBSERVATION,
                "value": None,
                "rule": OBSERVATION_UNIT_RULE,
            },
            "outcomes_with_calibration_coverage": {
                "unit": UNIT_FUTURES_OUTCOME,
                "value": None,
                "rule": COVERAGE_UNIT_RULE,
            },
        },
        "coverage_bridge": {
            "rungs": [_rung_cell(key, None) for key, _rule in BRIDGE_RUNGS],
            "reconciles": False,
            "residual": None,
        },
        "observation_bridge": {
            "futures_outcomes_plotted": None,
            "sportsbook_curve_legs": None,
            "published_curve_observations": None,
            "reconciles": False,
            "residual": None,
        },
        "invariants": {"ok": False, "violations": ["CENSUS_UNAVAILABLE"]},
    }


def build_coverage_census(
    *,
    rung_counts: dict[str, int | None],
    sportsbook_curve_legs: int | None,
    published_curve_observations: int | None,
    published_outcomes_crosscheck: int | None,
    population_version: str,
    generation: str | None = None,
    with_terminal_calibration_price: int | None = None,
) -> dict[str, Any]:
    """Assemble the census from directly counted rungs.

    ``rung_counts`` maps every key in :data:`RUNG_KEYS` to its measured count,
    or to ``None`` when that rung could not be measured. Missing keys are
    treated as unmeasured (``None``) rather than zero — a key the build forgot
    to emit is exactly the case "UNKNOWN never becomes zero" exists for.

    ``published_outcomes_crosscheck`` is the population CTE chain's own count of
    the rows that reach the curve (``published_summary.published_outcomes``). It
    is computed independently of the bridge's terminal rung, so the two agreeing
    is real evidence the partition is wired to the same population; disagreeing
    is a contract violation.
    """
    cells = [_rung_cell(key, rung_counts.get(key)) for key, _rule in BRIDGE_RUNGS]
    by_key = {cell["key"]: cell for cell in cells}

    plotted = by_key[PLOTTED_RUNG]["outcomes"]
    exclusion_values = [by_key[key]["outcomes"] for key in EXCLUSION_RUNGS]
    all_known = plotted is not None and all(v is not None for v in exclusion_values)

    coverage_total = (
        plotted + sum(exclusion_values) if all_known else None  # type: ignore[operator]
    )

    violations: list[str] = []
    if not all_known:
        violations.append("RUNG_UNKNOWN")

    # Bridge A — coverage (futures_outcome). Reconciliation is trivially true by
    # construction when every rung is known, which is the point: the rungs are a
    # PARTITION of the coverage population, so the honest check is not the sum
    # but the two independent counts of the hinge below.
    coverage_reconciles = all_known
    coverage_residual = 0 if all_known else None

    # Bridge B — observations (curve_observation).
    obs_known = (
        plotted is not None
        and isinstance(sportsbook_curve_legs, int)
        and isinstance(published_curve_observations, int)
    )
    if obs_known:
        obs_residual = published_curve_observations - (plotted + sportsbook_curve_legs)  # type: ignore[operator]
        obs_reconciles = obs_residual == 0
        if not obs_reconciles:
            violations.append("OBSERVATION_BRIDGE_RESIDUAL")
    else:
        obs_residual = None
        obs_reconciles = False
        violations.append("OBSERVATION_BRIDGE_UNKNOWN")

    # The hinge, counted twice by two different code paths.
    if plotted is not None and isinstance(published_outcomes_crosscheck, int):
        if plotted != published_outcomes_crosscheck:
            violations.append("PLOTTED_HINGE_DIVERGES")
    else:
        violations.append("PLOTTED_HINGE_UNCHECKED")

    status = STATUS_COMPLETE if not violations else STATUS_INCOMPLETE

    return {
        "schema_version": COVERAGE_BRIDGE_SCHEMA_VERSION,
        "status": status,
        # Every count in this object was generated by THIS population version
        # and THIS build generation. A consumer that mixes two generations of
        # census is reading a bridge whose ends came from different worlds.
        "population_version": population_version,
        "generation": generation,
        "units": {
            "published_curve_observations": {
                "unit": UNIT_CURVE_OBSERVATION,
                "value": published_curve_observations,
                "rule": OBSERVATION_UNIT_RULE,
            },
            "outcomes_with_calibration_coverage": {
                "unit": UNIT_FUTURES_OUTCOME,
                "value": coverage_total,
                "rule": COVERAGE_UNIT_RULE,
                # A sub-split of the SAME unit, never a third headline: how many
                # covered outcomes carry a terminal calibration price rather than
                # falling back to their opening price.
                "with_terminal_calibration_price": (
                    with_terminal_calibration_price
                    if isinstance(with_terminal_calibration_price, int)
                    else None
                ),
            },
        },
        "coverage_bridge": {
            "from": "outcomes_with_calibration_coverage",
            "to": PLOTTED_RUNG,
            "unit": UNIT_FUTURES_OUTCOME,
            "rungs": cells,
            "reconciles": coverage_reconciles,
            "residual": coverage_residual,
        },
        "observation_bridge": {
            "unit": UNIT_CURVE_OBSERVATION,
            "futures_outcomes_plotted": plotted,
            "sportsbook_curve_legs": sportsbook_curve_legs
            if isinstance(sportsbook_curve_legs, int)
            else None,
            "published_curve_observations": published_curve_observations
            if isinstance(published_curve_observations, int)
            else None,
            "reconciles": obs_reconciles,
            "residual": obs_residual,
        },
        "invariants": {
            "ok": not violations,
            "violations": violations,
            "published_outcomes_crosscheck": published_outcomes_crosscheck,
        },
    }


def census_is_complete(census: Any) -> bool:
    """True only for a census that measured every rung and reconciled."""
    return (
        isinstance(census, dict)
        and census.get("schema_version") == COVERAGE_BRIDGE_SCHEMA_VERSION
        and census.get("status") == STATUS_COMPLETE
        and bool((census.get("invariants") or {}).get("ok"))
    )


def ensure_census(payload: Any, *, reason: str) -> Any:
    """Serve-side guard: a payload without a census gets an explicit unavailable one.

    Every serving tier hands out whole payloads produced by the canonical build,
    so they carry the same generated census by construction — EXCEPT a last-good
    or durable copy written before the census shipped. Leaving the key absent
    there would let a consumer read "no census" as "no exclusions", so it is
    filled in explicitly instead. Never overwrites a census that is present, and
    never touches any other field.
    """
    if not isinstance(payload, dict) or "calibration_coverage_census" in payload:
        return payload
    out = dict(payload)
    out["calibration_coverage_census"] = unavailable_census(
        reason,
        population_version=payload.get("population_version"),
    )
    return out
