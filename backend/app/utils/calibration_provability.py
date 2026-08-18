"""Is a published calibration cell PROVABLE, or selected on what it measures?

Fable ruling, CAL-P067: **any published cell whose graded share is under 50%
renders NOT-PROVABLE-selection-biased, with the graded share shown.**

Why this is not a sample-size rule, since it is shaped like one and the two
have opposite remedies:

A calibration cell answers "when a source said 30%, how often did it happen?"
Answering that requires knowing what happened — a GRADE. So the rows that reach
the curve are precisely the rows that got graded, and the ungraded ones are
absent rather than sampled out. **The selection criterion IS the measured
property.** More data does not help, wider error bars do not help, and a
significance test on the graded quarter answers a question about the graded
quarter.

Nor is the missing part plausibly random. CAL-P066's census found the 226,457
never-graded Polymarket outcomes concentrated in whole market SHAPES — one
grader claimed a shape, another never did, and the shape went ungraded
wholesale. Soccer publishes on ~25% graded and table_tennis on ~11%; the
remainder is not a random remainder, so no extrapolation from the graded part is
licensed.

Hence the rendering: not a wider interval around the number, but a refusal to
present it as a measurement. The number itself is never altered — a biased
estimate is still the estimate, and quietly substituting a different one would
be its own dishonesty.

Three states, deliberately, exactly as CAL-P067's ruling-075 fix has four:

* ``provable`` — a majority of the resolved population is graded.
* ``not_provable_selection_biased`` — under half is, and the share is shown.
* ``unknown`` — the graded share was never measured. **This is not a pass.** A
  cell with no denominator has not been shown to be unbiased, and rendering it
  as provable is how the biased cells kept publishing in the first place.
  Could-not-check never renders as nothing-to-report.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional

#: A cell must be at least half graded before its curve is a measurement of the
#: population rather than of the graded subset. A half is not a tuned number and
#: should not be tuned: below it, the rows we cannot see outnumber the rows we
#: can, and no statement about the whole is supportable from the part.
MIN_GRADED_SHARE = 0.50

PROVABILITY_PROVABLE = "provable"
PROVABILITY_NOT_PROVABLE = "not_provable_selection_biased"
PROVABILITY_UNKNOWN = "unknown"


# --- The units-coherence guard (CAL-P068) ------------------------------------
#
# CAL-P067 came one line from populating this rule's census with the #1912 MC
# pack's per-category table. The numbers looked made for each other: soccer
# reads 34,619 of 138,650 = 25.0%, exactly the figure the ruling quotes.
#
# They are not the same population and not even the same UNIT — that census is
# MARKET-level and Polymarket-`0x`-only, while a published cell's ``n`` is
# OUTCOME-level and all-source. The division yields 0.7096, and measured against
# the pre-guard code it did not merely slip past the incoherence check: it
# returned **provable**. A confident PASS off two different populations, on a
# public page.
#
# The old guard only refused a ratio above 1.0, and there is no fixing that by
# widening the range, because **a ratio does not carry units**. By the time you
# hold 0.7096 the information needed to reject it is gone. The only guard that
# works is refusing to compute the ratio at all until both sides have DECLARED
# what they count — so the census is a typed value, not a mapping, and a bare
# dict is a TypeError rather than a silent assumption.
UNIT_OUTCOMES = "outcomes"
UNIT_MARKETS = "markets"
_VALID_UNITS = frozenset({UNIT_OUTCOMES, UNIT_MARKETS})

#: What a published calibration cell's ``n`` counts. Cells pool every source, so
#: a denominator scoped to one source understates the graded share of every cell
#: it touches — the same error as the unit mismatch, one axis over.
CELL_NUMERATOR_UNIT = UNIT_OUTCOMES
CELL_POPULATION = "all_sources_resolved"


@dataclass(frozen=True)
class GradedShareCensus:
    """Per-key denominators, with the two facts that make them safe to divide by.

    ``unit`` and ``population`` are required and validated at construction. That
    is the whole design: the failure this prevents is not a bad number, it is a
    number whose provenance was never stated, and a value object is the only
    place to demand it before arithmetic can happen.
    """

    by_key: Mapping[str, Any]
    unit: str
    population: str

    def __post_init__(self) -> None:
        if self.unit not in _VALID_UNITS:
            raise ValueError(
                f"GradedShareCensus.unit must be one of {sorted(_VALID_UNITS)}, "
                f"got {self.unit!r} — an undeclared or unknown unit is the state "
                "this guard exists to make unreachable"
            )
        if not self.population or not isinstance(self.population, str):
            raise ValueError(
                "GradedShareCensus.population must name the scope it counted "
                "(e.g. 'all_sources_resolved') — a denominator scoped to one "
                "source understates every all-source cell it touches"
            )

    def incoherence(self) -> Optional[str]:
        """Why this census may not be divided into a published cell, or ``None``."""
        if self.unit != CELL_NUMERATOR_UNIT:
            return (
                f"census counts {self.unit} but a published cell's n counts "
                f"{CELL_NUMERATOR_UNIT} — the ratio would be two different "
                "populations in two different units, and a plausible-looking "
                "value below 1.0 is exactly how that passes unnoticed"
            )
        if self.population != CELL_POPULATION:
            return (
                f"census population is {self.population!r} but published cells "
                f"pool {CELL_POPULATION!r} — a narrower denominator understates "
                "the graded share of every cell it touches"
            )
        return None


def _count(value: Any) -> Optional[int]:
    """A non-negative count, or ``None`` for anything that is not one."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value < 0:
        return None
    return int(value)


def graded_share(graded_n: Any, resolved_n: Any) -> Optional[float]:
    """``graded / resolved``, or ``None`` where that is not a defined fraction."""
    graded = _count(graded_n)
    resolved = _count(resolved_n)
    if graded is None or not resolved:
        return None
    return graded / resolved


def provability(graded_n: Any, resolved_n: Any) -> tuple[str, Optional[float], str]:
    """``(verdict, graded_share, why)`` for one published cell.

    ``why`` always contains the share when there is one, because the ruling
    requires the share to be SHOWN rather than merely consulted — a reader who
    sees "not provable" and no number cannot tell a 49% cell from an 11% one,
    and those warrant very different responses.
    """
    share = graded_share(graded_n, resolved_n)
    if share is None:
        return (
            PROVABILITY_UNKNOWN,
            None,
            "graded share not measured for this cell — provability is unknown, "
            "which is not the same as fine: nothing here has been shown to be "
            "free of selection bias",
        )
    if share > 1.0:
        # Two numbers from different populations. Believing the ratio would
        # publish a confident pass off mismatched inputs.
        return (
            PROVABILITY_UNKNOWN,
            None,
            f"graded count exceeds the resolved population ({graded_n} > {resolved_n}) "
            "— the two counts are incoherent, so the share is unknown",
        )
    if share < MIN_GRADED_SHARE:
        return (
            PROVABILITY_NOT_PROVABLE,
            share,
            f"only {share * 100:.1f}% of this cell's resolved outcomes are graded "
            f"({graded_n:,} of {resolved_n:,}); the curve is computed on a sample "
            "selected on the very property it measures, so it is not provable — "
            "the ungraded majority is not a random majority",
        )
    return (
        PROVABILITY_PROVABLE,
        share,
        f"{share * 100:.1f}% of this cell's resolved outcomes are graded "
        f"({graded_n:,} of {resolved_n:,})",
    )


def provability_from_share(share: Any) -> tuple[str, Optional[float], str]:
    """:func:`provability` for a caller that already holds the ratio.

    The sentinel computes graded share from its own cohort reads, so it has the
    fraction and not the pair of counts. Same three verdicts and the same
    refusal to treat an absent or incoherent share as a pass.
    """
    if isinstance(share, bool) or not isinstance(share, (int, float)):
        return (
            PROVABILITY_UNKNOWN,
            None,
            "graded share not measured for this cell — provability is unknown, "
            "which is not the same as fine",
        )
    if share < 0 or share > 1:
        return (
            PROVABILITY_UNKNOWN,
            None,
            f"graded share {share} is outside [0, 1] — incoherent, so unknown",
        )
    if share < MIN_GRADED_SHARE:
        return (
            PROVABILITY_NOT_PROVABLE,
            float(share),
            f"only {share * 100:.1f}% of this cell's resolved outcomes are graded; "
            "the curve is computed on a sample selected on the very property it "
            "measures, so neither the raw nor the published number is provable — "
            "the ungraded majority is not a random majority",
        )
    return (
        PROVABILITY_PROVABLE,
        float(share),
        f"{share * 100:.1f}% of this cell's resolved outcomes are graded",
    )


def annotate_cells(
    cells: Iterable[dict[str, Any]],
    *,
    census: Optional[GradedShareCensus] = None,
    graded_key: str = "n",
    category_key: str = "category",
) -> list[dict[str, Any]]:
    """Return copies of ``cells`` carrying ``provability`` / ``graded_share``.

    Copies rather than mutations: the payload these come from is cached and
    shared, and annotating it in place would leak one request's view into the
    next. The MCE and n are passed through untouched — this rule governs how a
    number is presented, never what it is.

    ``census`` must be a :class:`GradedShareCensus`, never a bare mapping. A
    mapping carries no unit and no population, and accepting one is precisely
    how CAL-P067's near-miss would have shipped: a market-level Polymarket-only
    table divided into an outcome-level all-source cell, returning ``provable``
    off a 0.7096 "share". A ``TypeError`` here is cheaper than that.

    An incoherent census annotates **every** cell ``unknown`` with the reason —
    the fault is in the denominator, so it poisons the whole table, not the one
    cell someone happened to check. A category simply absent from a coherent
    census also reads ``unknown``: absent a denominator the page says it cannot
    tell, rather than painting itself green.
    """
    if census is not None and not isinstance(census, GradedShareCensus):
        raise TypeError(
            "annotate_cells(census=...) requires a GradedShareCensus, not "
            f"{type(census).__name__}. A bare mapping carries no unit and no "
            "population, which is the exact shape of the CAL-P067 near-miss: "
            "market-level counts divided into outcome-level cells, passing as a "
            "share of 0.71."
        )

    incoherent = census.incoherence() if census is not None else None
    by_key: Mapping[str, Any] = census.by_key if census is not None else {}

    out: list[dict[str, Any]] = []
    for cell in cells:
        annotated = dict(cell)
        if incoherent is not None:
            annotated["provability"] = PROVABILITY_UNKNOWN
            annotated["graded_share"] = None
            annotated["provability_reason"] = (
                f"graded share NOT computed — {incoherent}. Refusing to divide is "
                "the honest answer; the ratio would have looked like one."
            )
            out.append(annotated)
            continue
        category = cell.get(category_key)
        resolved = by_key.get(category) if category is not None else None
        verdict, share, why = provability(cell.get(graded_key), resolved)
        annotated["provability"] = verdict
        annotated["graded_share"] = share
        annotated["provability_reason"] = why
        out.append(annotated)
    return out
