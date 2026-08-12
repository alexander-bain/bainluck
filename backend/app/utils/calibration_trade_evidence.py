"""Ruling 011 / #1530 — the ONE definition of "did this market actually trade".

Alex ruled on 2026-08-03 (Option A) and again in ruling 011: a market's
trading-activity tier uses **volume evidence whenever volume is present**, and
**missing volume never silently demotes a market to thin**. This module is that
rule, and it is deliberately the only place it is written down.

WHY IT LIVES HERE AND NOT IN THE PRODUCER. Two reasons, and the second is the
one that matters.

1. ``precompute_calibration.py`` is FROZEN (ruling 009) until the publish
   converges, so the producer cannot carry this today.
2. When the freeze lifts and ruling 024's combined event lands, the producer
   must **import** this predicate rather than restate it. A second definition of
   an exclusion or a tier is the exact failure C13/C14 found (the cohort sweep
   measuring rows the curve drops) and the exact failure ``census_prop_threshold_cliff``
   was written to be structurally incapable of. The census that JUSTIFIES the
   tier change and the producer that APPLIES it must not be able to disagree
   about what the tier is.

THE RULE
--------
Read in order; first match wins, and the order is the contract:

======================================  ========================
``source`` in {odds_api, datagolf}      ``not_applicable``
``fo.volume > 0``                       ``traded``
``fo.volume = 0``                       ``untraded``
``fo.volume IS NULL`` + market OI > 0   ``traded_open_interest``
otherwise                               ``unknown``
======================================  ========================

**NULL IS UNKNOWN, NEVER UNTRADED.** This is the whole ruling. Measured live on
2026-08-12 over resolved outcomes in a 30-day window, Polymarket is 95.2% NULL on
``volume`` with **four** explicit zeros in thirty days — so reading "not > 0" as
untraded would publish 95% of Polymarket as never-traded and make the number
worse than the artifact it replaces. Absence of volume in the row we hold is a
fact about our capture, not about the market (gotcha #53: an empty reading is a
response shape, not an absence).

**The open-interest backup is its own class, not folded into ``traded``.** Alex
named ``open_interest`` as the backup and it is a large one — 79.2% of Kalshi's
NULL-volume resolved outcomes sit in a market reporting OI > 0, which takes
Kalshi's unknown share from 31.9% to roughly 6.6%. But open interest is
**market-level**, so it proves the market traded, not that this leg did. A
weaker claim has to be visible as a weaker claim, or the strength of the
evidence stops being auditable the moment the two are summed.

**Excluded sources are named, not inferred.** ``odds_api`` and ``datagolf`` have
no volume concept at all (datagolf is 100% NULL and has ``calibration ==
opening`` by construction; odds_api futures resolve nothing). They classify as
``not_applicable`` BEFORE any volume clause is read, so an excluded row can never
be reported as ``unknown`` — which would read as "we might find out later" about
a column that does not exist for it.

Read-side only (gotcha #21). Nothing here mutates ``is_winner``,
``opening_probability``, ``calibration_probability`` or any resolution.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

#: Sources with no volume concept. Excluded BY SOURCE, never by a coverage
#: heuristic — see the module docstring.
EXCLUDED_SOURCES: tuple[str, ...] = ("odds_api", "datagolf")

#: The partition, in report order.
CLASSES: tuple[str, ...] = (
    "traded",
    "traded_open_interest",
    "untraded",
    "unknown",
    "not_applicable",
)

#: Evidence OF a trade. ``traded_open_interest`` counts here (Alex named it the
#: backup) while staying separately reportable above.
TRADED_CLASSES: tuple[str, ...] = ("traded", "traded_open_interest")

#: Evidence EITHER WAY — the honest denominator. "61.7% of Kalshi's
#: price-unchanged outcomes traded" is a ratio over the whole cohort and
#: understates the artifact; "91.5% of the EVIDENCED ones traded" is the claim
#: the data actually supports, because the unknown rows say nothing in either
#: direction and must not be counted as if they said "untraded".
EVIDENCED_CLASSES: tuple[str, ...] = ("traded", "traded_open_interest", "untraded")

RULE_TEXT = (
    "Trading evidence read from the source's own volume, not from our polling "
    "cadence. traded = the outcome reports volume > 0; traded_open_interest = no "
    "outcome volume but the market reports open interest > 0 (market-level, so it "
    "proves the market traded, not this leg); untraded = the outcome explicitly "
    "reports volume = 0; unknown = no volume figure at all — NEVER counted as "
    "untraded. odds_api and datagolf are excluded by source (no volume concept). "
    "Measurement only: changes no probability, no curve and no resolution."
)


def trade_evidence_sql(
    source: str = "fm.source",
    volume: str = "fo.volume",
    open_interest: str = "fm.open_interest",
) -> str:
    """The rule as a SQL ``CASE``, against caller-supplied aliases.

    Parameterised on the aliases rather than hard-coded so the census (which
    joins ``fo``/``fm`` directly) and the producer (whose population chain
    carries the market columns on ``vm``) render the SAME predicate instead of
    each writing one that looks like it.
    """
    excluded = ", ".join(f"'{s}'" for s in EXCLUDED_SOURCES)
    return (
        "(CASE"
        f" WHEN {source} IN ({excluded}) THEN 'not_applicable'"
        f" WHEN {volume} > 0 THEN 'traded'"
        f" WHEN {volume} = 0 THEN 'untraded'"
        f" WHEN {volume} IS NULL AND {open_interest} > 0 THEN 'traded_open_interest'"
        " ELSE 'unknown' END)"
    )


def classify(source: str | None, volume: int | None, open_interest: int | None) -> str:
    """The rule in Python — the canonical, unit-testable twin of the SQL.

    Kept beside :func:`trade_evidence_sql` and asserted equivalent to it by
    ``test_calibration_trade_evidence_1530``, the same way
    ``outcome_is_calibration_liquid`` sits beside ``KALSHI_LIQUIDITY_EXISTS``.
    The pair is what lets the rule be tested without a database and still be the
    rule production runs.
    """
    if source in EXCLUDED_SOURCES:
        return "not_applicable"
    if volume is not None:
        if volume > 0:
            return "traded"
        if volume == 0:
            return "untraded"
        # A negative volume is not evidence of anything; fall through to unknown
        # rather than inventing a reading for a value that should not exist.
        return "unknown"
    if open_interest is not None and open_interest > 0:
        return "traded_open_interest"
    return "unknown"


def empty_counts() -> dict[str, int]:
    """A zeroed count for every class.

    Every class is always present, including the zeros. A census that omits its
    empty cohorts reports "nothing to say here" and "we did not look" with the
    same silence — which is the shape ``task_verdict`` exists to refuse.
    """
    return dict.fromkeys(CLASSES, 0)


def summarise(counts: Mapping[str, int]) -> dict:
    """One cohort's counts, plus the three derived figures worth publishing.

    ``traded_share_of_evidenced_pct`` is the headline: of the rows that carry
    evidence either way, how many traded. ``evidence_coverage_pct`` is the
    caveat that keeps it honest — a 100% traded share over 4% coverage is not the
    same claim as one over 68%, and publishing the first without the second is
    how a ratio becomes a lie that survives review.

    Both are ``None``, never ``0.0``, when there is nothing to divide by: a
    source with no evidence at all must read as "we cannot say", never as
    "0% traded".
    """
    total = sum(int(counts.get(k, 0)) for k in CLASSES)
    traded = sum(int(counts.get(k, 0)) for k in TRADED_CLASSES)
    evidenced = sum(int(counts.get(k, 0)) for k in EVIDENCED_CLASSES)
    return {
        "n": total,
        **{k: int(counts.get(k, 0)) for k in CLASSES},
        "evidenced_n": evidenced,
        "traded_share_of_evidenced_pct": (
            round(traded / evidenced * 100, 1) if evidenced else None
        ),
        "evidence_coverage_pct": round(evidenced / total * 100, 1) if total else None,
    }


def unrecognised_classes(counts: Iterable[str]) -> list[str]:
    """Class names the contract does not know about.

    The ``CASE`` is a partition, so a name outside :data:`CLASSES` means the SQL
    and this module have drifted. It is reported by name and turns the census's
    ``contract_ok`` red, rather than being folded into ``unknown`` — a drifted
    class quietly absorbed into the catch-all is indistinguishable from real
    missing data, which is the one reading this whole module exists to prevent.
    """
    return sorted(set(counts) - set(CLASSES))
