"""CAL-P044 (#1530 / ruling 011) — the BEFORE half of the mandatory before/after.

Ruling 011 ships the two-tier well-traded change **only** with a
``CALIBRATION_POPULATION_VERSION`` bump **and published before/after counts per
cohort**, and ruling 024 folds it into one combined invalidation event. This
module measures the BEFORE.

WHY IT HAD TO BE TAKEN NOW, BEFORE THE FREEZE LIFTS
---------------------------------------------------
The "before" is only measurable while the old classifier is still what the page
publishes. Ruling 009's freeze lifts on the next couple of clean beats; ruling
024's event then moves the boundary in one step. **After that, the before is
unrecoverable** — not hard to get, gone, because the published population and
the tier both change in the same generation and nothing retains the prior
split. A before/after census whose "before" is reconstructed after the fact is
the "two derivations of one fact" failure this lane keeps paying for.

So this is not preparation for the work. It is the half of the work that has a
deadline, and its deadline is the freeze lifting.

WHAT IT MEASURES, AND OVER WHICH DENOMINATOR — STATED, NOT IMPLIED
------------------------------------------------------------------
The **resolved + curve-price-present + truth-eligible candidate shape**: exactly
the shape the payload's own ``truth_evidence`` census documents itself as using,
imported from ``resolution_authority`` rather than restated.

That is deliberately **not** the published ``deduped`` set. Reproducing
``deduped`` means re-running the whole population CTE chain, which is the read
that #1479 already has the hourly beat exceeding its window on; a census that
made the SLO worse to measure a transparency number would be a poor trade, and
``census_prop_threshold_cliff`` set the precedent of measuring on the candidate
shape and saying so. The published-population split rides for free inside the
producer when the combined event lands, because the population is already
materialized there — the prepared patch does exactly that.

Both numbers are wanted, and they answer different questions: this one is "what
does the source say about the rows we consider", the producer's is "what does
the source say about the rows we plot". Naming which is which is the point.

ROW-BOUNDED, NOT ID-WIDTH. Inherited from ``census_reachability`` /
``census_prop_threshold_cliff``, whose measured lesson is that outcome ids are
not uniformly dense, so a fixed id-span window is a few thousand rows in one
region and millions in another. ``LIMIT :scan`` costs about the same wherever it
lands. Do not "simplify" this into one aggregate: the unscoped join over
``futures_outcomes ⋈ futures_markets`` is the one #1527 recorded being cancelled
by the statement timeout three times.

Read-only. ``apply`` is accepted and ignored, like every other census on the
rail — the parameter exists so the caller's shape is uniform, not because there
is a write behind it.
"""

from __future__ import annotations

from sqlalchemy import text

from app.utils.calibration_trade_evidence import (
    CLASSES,
    RULE_TEXT,
    empty_counts,
    summarise,
    trade_evidence_sql,
    unrecognised_classes,
)
from app.utils.resolution_authority import CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL

CENSUS_NAME = "trade-evidence"

#: Outcome ROWS walked per call — NOT a span of ids (see the module docstring).
DEFAULT_SCAN = 500_000
MAX_SCAN = 2_000_000

#: Per-window statement timeout: fail this window fast rather than hold the
#: caller's wall open and return carrying no evidence.
_WINDOW_TIMEOUT = "20s"

#: The curve price, mirroring every other read path in the product.
_CURVE_PRICE = "COALESCE(fo.calibration_probability, fo.opening_probability)"

#: The snapshot-delta the page has been reading as "did it trade". Mirrors
#: ``precompute_calibration``'s ``price_moved`` expression exactly — the whole
#: census is a comparison against it, so a paraphrase here would compare the new
#: evidence against something the page does not actually publish.
_PRICE_MOVED = (
    "(fo.calibration_probability IS NOT NULL"
    " AND fo.calibration_probability IS DISTINCT FROM fo.opening_probability)"
)

_BOUNDS_SQL = """
    SELECT MIN(id) AS lo, MAX(id) AS hi, COUNT(*) AS n
    FROM (SELECT id FROM futures_outcomes WHERE id > :cursor
          ORDER BY id ASC LIMIT :scan) w
"""


def cohorts_sql() -> str:
    """The per-window aggregate, rendered from the canonical predicates.

    A function rather than a module constant so the imported trade-evidence
    ``CASE`` and truth-eligibility allowlist are interpolated once, here, beside
    the columns they read.
    """
    return f"""
    SELECT
        fm.source AS source,
        {_PRICE_MOVED} AS price_moved,
        {trade_evidence_sql()} AS trade_evidence,
        COUNT(*) AS n,
        SUM({_CURVE_PRICE}) AS sum_pred,
        SUM(CASE WHEN fo.is_winner THEN 1 ELSE 0 END) AS wins
    FROM futures_outcomes fo
    JOIN futures_markets fm ON fm.id = fo.market_id
    WHERE fo.id >= :lo AND fo.id <= :hi
      AND fm.status = 'resolved'
      AND fo.opening_probability IS NOT NULL
      AND fo.opening_probability > 0 AND fo.opening_probability < 1
      AND fo.resolution_source IN {CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL}
    GROUP BY 1, 2, 3
"""


def cohort_key(source: str, price_moved: bool | None, trade_evidence: str) -> str:
    """Stable text key for one cohort, so windows merge without tuple keys.

    Text because a merged census crosses a JSON boundary on its way back through
    the admin rail, and a tuple key would not survive it. ``price_moved`` is
    rendered through :func:`_moved_token` so the tri-state round-trips: ``null``
    is a real third value here, not a missing one.
    """
    return f"{source}|{_moved_token(price_moved)}|{trade_evidence}"


def _moved_token(price_moved: bool | None) -> str:
    if price_moved is True:
        return "moved"
    if price_moved is False:
        return "unchanged"
    return "unknown"


def merge_windows(windows: list[dict]) -> dict[str, dict]:
    """Fold per-window cohort rows into one census. Pure, so it tests without a DB.

    **Sums, never averages of averages** — each window contributes ``n``,
    ``sum_pred`` and ``wins`` and the rates are derived once at the end. A
    12-row window weighted equally with a 400,000-row one is how a measurement
    taken this way comes out wrong in the flattering direction.
    """
    merged: dict[str, dict] = {}
    for window in windows:
        for row in window.get("cohorts") or []:
            key = cohort_key(row["source"], row["price_moved"], row["trade_evidence"])
            slot = merged.setdefault(
                key,
                {
                    "source": row["source"],
                    "price_moved": row["price_moved"],
                    "trade_evidence": row["trade_evidence"],
                    "n": 0,
                    "sum_pred": 0.0,
                    "wins": 0,
                },
            )
            slot["n"] += int(row.get("n") or 0)
            slot["sum_pred"] += float(row.get("sum_pred") or 0.0)
            slot["wins"] += int(row.get("wins") or 0)
    return merged


def by_source(merged: dict[str, dict]) -> list[dict]:
    """The published shape: per source, the split and the two price_moved cohorts.

    This is what ruling 011 means by "counts per cohort". Each source reports its
    whole distribution plus the same distribution restricted to the rows the page
    currently calls "price moved" and "price unchanged", so the artifact is
    readable as a ratio rather than asserted as a headline.
    """
    per_source: dict[str, dict] = {}
    for row in merged.values():
        rec = per_source.setdefault(
            row["source"],
            {
                "counts": empty_counts(),
                "price_moved": empty_counts(),
                "price_unchanged": empty_counts(),
            },
        )
        klass, n = row["trade_evidence"], int(row["n"])
        rec["counts"][klass] = rec["counts"].get(klass, 0) + n
        if row["price_moved"] is True:
            rec["price_moved"][klass] = rec["price_moved"].get(klass, 0) + n
        elif row["price_moved"] is False:
            rec["price_unchanged"][klass] = rec["price_unchanged"].get(klass, 0) + n
        # price_moved NULL carries no claim about movement; putting it in either
        # column would invent one. It stays in ``counts`` only.

    out = [
        {
            "source": source,
            **summarise(rec["counts"]),
            "price_moved_cohort": summarise(rec["price_moved"]),
            "price_unchanged_cohort": summarise(rec["price_unchanged"]),
        }
        for source, rec in per_source.items()
    ]
    return sorted(out, key=lambda r: -r["n"])


def totals(merged: dict[str, dict]) -> dict[str, int]:
    """Class totals across every source. Always all classes, including zeros."""
    acc = empty_counts()
    for row in merged.values():
        klass = row["trade_evidence"]
        acc[klass] = acc.get(klass, 0) + int(row["n"])
    return acc


def is_complete_walk(windows: list[dict]) -> bool:
    """True only when the walk reached the end of the id space.

    A PARTIAL walk must never be published as the "before". Its counts are real
    but its denominator is not the population, and ruling 011's before/after is
    a comparison of denominators — so a partial before makes the after
    unreadable rather than merely approximate. Same shape as gotcha #53 one
    surface over: a number that arrived is not a number that is complete.
    """
    return bool(windows) and bool(windows[-1].get("exhausted"))


def build_census(windows: list[dict]) -> dict:
    """Assemble the publishable census from a completed (or partial) walk.

    Pure. ``complete`` is reported rather than assumed, and it is reported even
    when it is False — a census that only speaks when it is whole is a census
    that goes silent exactly when the caller most needs to know it is not.
    """
    merged = merge_windows(windows)
    class_totals = totals(merged)
    drift = unrecognised_classes(class_totals)
    return {
        "census": CENSUS_NAME,
        "rule": RULE_TEXT,
        "classes": list(CLASSES),
        "denominator": (
            "resolved futures outcomes with a curve price in (0,1) and a "
            "calibration-truth-eligible resolution_source — the CANDIDATE shape, "
            "not the published deduped set (see module docstring)"
        ),
        "complete": is_complete_walk(windows),
        "windows": len(windows),
        "rows_walked": sum(int(w.get("rows_walked") or 0) for w in windows),
        "measured_outcomes": sum(class_totals.get(k, 0) for k in class_totals),
        "totals": class_totals,
        "overall": summarise(class_totals),
        "by_source": by_source(merged),
        "contract_ok": not drift,
        "unrecognised_classes": drift,
    }


async def census(
    session,
    apply: bool = False,
    limit: int | None = None,
    offset: int | None = None,
) -> dict:
    """Walk one bounded outcome-row window and count the trade-evidence cohorts.

    ``limit``   outcome ROWS to walk in this call (not an id span).
    ``offset``  outcome-id cursor, exclusive. Pass the returned ``next_offset``
                to continue; omit to start at the beginning.
    ``apply``   ignored; this census never writes.
    """
    scan = min(int(limit or DEFAULT_SCAN), MAX_SCAN)
    cursor = int(offset) if offset is not None else 0

    await session.execute(text(f"SET LOCAL statement_timeout = '{_WINDOW_TIMEOUT}'"))

    bounds = (
        (await session.execute(text(_BOUNDS_SQL), {"cursor": cursor, "scan": scan}))
        .mappings()
        .first()
    )
    lo, hi, walked = bounds["lo"], bounds["hi"], int(bounds["n"] or 0)

    if not walked:
        # End of the id space. Exhausted with zero rows is a COMPLETE walk of an
        # empty tail, not a failure — the caller needs that to stop looping.
        return {
            "census": CENSUS_NAME,
            "rows_walked": 0,
            "window": None,
            "next_offset": None,
            "exhausted": True,
            "cohorts": [],
        }

    rows = (
        (await session.execute(text(cohorts_sql()), {"lo": lo, "hi": hi}))
        .mappings()
        .all()
    )

    cohorts = [
        {
            "source": row["source"],
            "price_moved": row["price_moved"],
            "trade_evidence": row["trade_evidence"],
            "n": int(row["n"] or 0),
            "sum_pred": float(row["sum_pred"] or 0.0),
            "wins": int(row["wins"] or 0),
        }
        for row in rows
    ]

    return {
        "census": CENSUS_NAME,
        "rows_walked": walked,
        "window": {"lo": lo, "hi": hi},
        "next_offset": hi,
        "exhausted": walked < scan,
        "eligible_rows_in_window": sum(c["n"] for c in cohorts),
        "cohorts": cohorts,
    }
