"""CAL-P018 (#1089) — measure the prop-threshold cliff, per series.

Alex's banked ruling (PRODUCT-BRAIN, 2026-08-08 (2)) says the Kalshi
prop-threshold band must be **tightened per measured cliff, per series**, as a
**versioned** methodology change, with **published per-series exclusion counts**.
All three parts are required together. This module supplies the measurement the
first and third parts stand on; CAL-P019 acts on it.

WHY A RAIL AND NOT A QUERY. The obvious way to answer "where does each series
break?" is one grouped aggregate. Measured against production 2026-08-08 and
again 2026-08-09, twelve hours apart:

    full-population scan (all resolved kalshi prop rows)   STATEMENT TIMEOUT
    single series (``external_id LIKE 'KXNHLAST-%'``)      STATEMENT TIMEOUT
    bare ``COUNT(*)`` over the resolved population         STATEMENT TIMEOUT

The ~10 s ``db-query`` timeout is a hard limit, not transient load — the two
runs agreed exactly. Only a bounded window returns. That is the same wall
``census_reachability`` (CAL-P012) and ``census_winner_fields`` hit, so this
follows their convention rather than inventing a third.

ROW-BOUNDED, NOT ID-WIDTH. Inherited verbatim from ``census_reachability``,
whose first cut got this wrong and measured the cost: outcome ids are not
uniformly dense, so a fixed id-width window is a few thousand rows in one region
and millions in another — simultaneously wasteful at one end of the table and
fatal at the other. ``LIMIT :scan`` makes every window cost about the same
wherever it lands. **Do not "simplify" this into a single aggregate.** It will
pass review, pass tests against a small fixture DB, and then time out against
production — which is exactly how this measurement came to be blocked in the
first place.

ONE DEFINITION OF EVERYTHING, ALL IMPORTED. A census whose predicate disagrees
with the curve's is worse than no census: it would justify a band change against
a population the curve does not actually plot. So the name pattern comes from
``KALSHI_PROP_THRESHOLD_NAME_RE``, the current-band verdict from
``kalshi_prop_threshold_exclude_sql``, and the series key from
``calibration_sentinel.series_family`` — every one of them the same object the
shipped code uses. CAL-P013's whole finding was that a second definition of
"excluded" is how these drift apart; this module is deliberately incapable of
holding one.

WHAT IT REPORTS, AND WHY THE LAST COLUMN MATTERS. Per
``(series, category, decile)``: how many outcomes, their summed predicted
probability, how many won, and **how many the CURRENT global bands already
exclude**. Without that last count the census answers "what is true" but not
"what would change" — and the ruling asks for exclusion counts, which is a
question about the bands, not just about the data.
"""

from __future__ import annotations

from sqlalchemy import text

from app.tasks.calibration_sentinel import series_family
from app.tasks.precompute_calibration import (
    KALSHI_PROP_THRESHOLD_NAME_RE,
    kalshi_prop_threshold_exclude_sql,
)

#: Outcome ROWS walked per call — NOT a span of ids (see the module docstring).
#: Matches ``census_reachability``'s measured-safe size; this window does strictly
#: less work per row than that one (no correlated snapshot scans).
DEFAULT_SCAN = 500_000
MAX_SCAN = 2_000_000

#: Per-window statement timeout — fail this window fast rather than hold the
#: router wall open and return an H12 carrying no evidence.
_WINDOW_TIMEOUT = "20s"

#: The curve price, mirroring every other read path.
_CURVE_PRICE = "COALESCE(fo.calibration_probability, fo.opening_probability)"

CENSUS_NAME = "prop-threshold-cliff"

#: Deciles. Ten buckets, ``LEAST(..., 9)`` so a price of exactly 1.0 lands in the
#: top bucket rather than an eleventh one nobody plots.
BAND_COUNT = 10

_BOUNDS_SQL = """
    SELECT MIN(id) AS lo, MAX(id) AS hi, COUNT(*) AS n
    FROM (SELECT id FROM futures_outcomes WHERE id > :cursor
          ORDER BY id ASC LIMIT :scan) w
"""


def _cohorts_sql() -> str:
    """The per-window aggregate, rendered from the canonical predicates.

    Built by a function rather than held as a module constant so the imported
    exclusion SQL is interpolated once, here, next to the columns it reads —
    the same shape ``precompute_calibration`` uses at its own call site.
    """
    excluded_today = kalshi_prop_threshold_exclude_sql(
        source="fm.source",
        name="fo.name",
        category="COALESCE(fm.llm_sport_category, 'unknown')",
        calibration_probability="fo.calibration_probability",
        opening_probability="fo.opening_probability",
    )
    return f"""
    SELECT
        split_part(fm.external_id, '-', 1) AS ext_prefix,
        COALESCE(fm.llm_sport_category, 'unknown') AS category,
        LEAST(FLOOR({_CURVE_PRICE} * {BAND_COUNT})::int, {BAND_COUNT - 1}) AS band,
        COUNT(*) AS n,
        SUM({_CURVE_PRICE}) AS sum_pred,
        SUM(CASE WHEN fo.is_winner THEN 1 ELSE 0 END) AS wins,
        SUM(CASE WHEN {excluded_today} THEN 1 ELSE 0 END) AS excluded_today
    FROM futures_outcomes fo
    JOIN futures_markets fm ON fm.id = fo.market_id
    WHERE fo.id >= :lo AND fo.id <= :hi
      AND fm.status = 'resolved'
      AND fm.source = 'kalshi'
      AND fo.name ~ '{KALSHI_PROP_THRESHOLD_NAME_RE}'
      AND {_CURVE_PRICE} IS NOT NULL
    GROUP BY 1, 2, 3
"""


def cohort_key(series: str, category: str, band: int) -> str:
    """Stable text key for one cohort, so windows merge without tuple keys.

    Text because a merged census crosses a JSON boundary on its way back through
    the admin rail, and a tuple key would not survive it.
    """
    return f"{series}|{category}|{band}"


def merge_windows(windows: list[dict]) -> dict[str, dict]:
    """Fold per-window cohort rows into one census.

    Pure, so the arithmetic is testable without a database.

    **Sums, never averages of averages.** Each window contributes ``n``,
    ``sum_pred`` and ``wins``; predicted and actual rates are derived at the very
    end by :func:`with_rates`. Averaging each window's mean and then averaging
    those means weights a 12-row window equally with a 400,000-row one, which is
    how a cliff measured this way would come out wrong in exactly the direction
    that makes a band look safer than it is.
    """
    merged: dict[str, dict] = {}
    for window in windows:
        for row in window.get("cohorts") or []:
            key = cohort_key(row["series"], row["category"], int(row["band"]))
            slot = merged.setdefault(
                key,
                {
                    "series": row["series"],
                    "category": row["category"],
                    "band": int(row["band"]),
                    "n": 0,
                    "sum_pred": 0.0,
                    "wins": 0,
                    "excluded_today": 0,
                },
            )
            slot["n"] += int(row.get("n") or 0)
            slot["sum_pred"] += float(row.get("sum_pred") or 0.0)
            slot["wins"] += int(row.get("wins") or 0)
            slot["excluded_today"] += int(row.get("excluded_today") or 0)
    return merged


def with_rates(merged: dict[str, dict]) -> list[dict]:
    """Derive predicted/actual rates once, at the end, from the summed totals.

    A cohort with no rows cannot have a rate; it reports ``None`` rather than 0.0
    — an unmeasured rate and a measured zero are different claims, and the whole
    point of this census is to decide a band from them.
    """
    out = []
    for row in merged.values():
        n = int(row["n"])
        item = dict(row)
        item["predicted"] = (row["sum_pred"] / n) if n else None
        item["actual"] = (row["wins"] / n) if n else None
        item["gap"] = (
            item["actual"] - item["predicted"]
            if item["actual"] is not None and item["predicted"] is not None
            else None
        )
        out.append(item)
    return sorted(out, key=lambda r: (r["series"], r["category"], r["band"]))


def is_complete_walk(windows: list[dict]) -> bool:
    """True only when the walk reached the end of the id space.

    A PARTIAL walk must never be published as a cliff. Its counts are real but
    its denominator is not the population, and a band tightened against 60% of
    the rows is a guess wearing a measurement's clothing — the same
    "an empty 200 is not an absence" error (gotcha #53) one surface over.
    """
    return bool(windows) and bool(windows[-1].get("exhausted"))


async def census(
    session,
    apply: bool = False,
    limit: int | None = None,
    offset: int | None = None,
) -> dict:
    """Walk one bounded outcome-row window and count the prop-threshold cohorts.

    ``limit``   outcome ROWS to walk in this call (not an id span).
    ``offset``  outcome-id cursor, exclusive. Pass the returned ``next_offset``
                to continue; omit to start at the beginning.
    ``apply``   ignored; this census never writes.
    """
    scan = min(int(limit or DEFAULT_SCAN), MAX_SCAN)
    cursor = int(offset) if offset is not None else 0

    await session.execute(text(f"SET LOCAL statement_timeout = '{_WINDOW_TIMEOUT}'"))

    bounds = (
        await session.execute(text(_BOUNDS_SQL), {"cursor": cursor, "scan": scan})
    ).mappings().first()

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
        await session.execute(text(_cohorts_sql()), {"lo": lo, "hi": hi})
    ).mappings().all()

    cohorts = [
        {
            # series_family() folds the season suffix, so KXNBA2026 and KXNBA2025
            # are ONE series. Applied here in Python rather than re-implemented in
            # SQL, because it is the sentinel's canonical definition and a second
            # copy would drift the moment either changed.
            "series": series_family(row["ext_prefix"]),
            "category": row["category"],
            "band": int(row["band"]),
            "n": int(row["n"] or 0),
            "sum_pred": float(row["sum_pred"] or 0.0),
            "wins": int(row["wins"] or 0),
            "excluded_today": int(row["excluded_today"] or 0),
        }
        for row in rows
    ]

    return {
        "census": CENSUS_NAME,
        "rows_walked": walked,
        "window": {"lo": lo, "hi": hi},
        "next_offset": hi,
        "exhausted": walked < scan,
        "prop_rows_in_window": sum(c["n"] for c in cohorts),
        "cohorts": cohorts,
    }
