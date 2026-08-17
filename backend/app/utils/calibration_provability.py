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

from typing import Any, Iterable, Optional

#: A cell must be at least half graded before its curve is a measurement of the
#: population rather than of the graded subset. A half is not a tuned number and
#: should not be tuned: below it, the rows we cannot see outnumber the rows we
#: can, and no statement about the whole is supportable from the part.
MIN_GRADED_SHARE = 0.50

PROVABILITY_PROVABLE = "provable"
PROVABILITY_NOT_PROVABLE = "not_provable_selection_biased"
PROVABILITY_UNKNOWN = "unknown"


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
    resolved_by_category: Optional[dict[str, Any]] = None,
    graded_key: str = "n",
    category_key: str = "category",
) -> list[dict[str, Any]]:
    """Return copies of ``cells`` carrying ``provability`` / ``graded_share``.

    Copies rather than mutations: the payload these come from is cached and
    shared, and annotating it in place would leak one request's view into the
    next. The MCE and n are passed through untouched — this rule governs how a
    number is presented, never what it is.

    A category absent from ``resolved_by_category`` annotates ``unknown``, which
    with no census loaded is every cell. That is the intended reading: absent a
    denominator the page must say it cannot tell, not paint itself green.
    """
    resolved_by_category = resolved_by_category or {}
    out: list[dict[str, Any]] = []
    for cell in cells:
        annotated = dict(cell)
        category = cell.get(category_key)
        resolved = resolved_by_category.get(category) if category is not None else None
        verdict, share, why = provability(cell.get(graded_key), resolved)
        annotated["provability"] = verdict
        annotated["graded_share"] = share
        annotated["provability_reason"] = why
        out.append(annotated)
    return out
