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

==========================================  ========================
``source`` in {odds_api, datagolf}          ``not_applicable``
Polymarket, valid ``traded`` receipt        ``traded``
Polymarket, valid ``confirmed_zero``
receipt, ``fo.volume`` NULL or 0            ``untraded``
Polymarket, valid ``confirmed_zero``
receipt, any other ``fo.volume``            ``unknown`` (conflict)
``fo.volume > 0``                           ``traded``
``fo.volume = 0``                           ``untraded``
``fo.volume IS NULL`` + market OI > 0       ``traded_open_interest``
otherwise                                   ``unknown``
==========================================  ========================

The two receipt rows only exist when the caller passes ``market_metadata``;
without it the rule is the five scalar rows, unchanged.

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

**The Polymarket receipt (#1870's consumer half).** ``fo.volume`` is an
integer and Polymarket's traded amount is not: a condition that traded $0.25 has
no integer that is both honest and positive. Both Polymarket writers therefore
carry the fact in ``market_metadata['volume_evidence']`` and the scalar can be
NULL beside it (forward: ``tasks.polymarket.polymarket_activity_volume``;
recovery: ``polymarket_evidence.build_evidence_receipt``). Before this, the rule
read only the scalar, so a valid ``traded`` receipt beside a NULL was
``unknown`` and one beside a recovery-manufactured 0 was ``untraded`` — a market
that traded, published as one that did not.

A receipt counts only when it is VALID for one of the two provenances that
write it, and a valid receipt outranks the scalar:

* forward ``gamma:events:condition-volume`` with ``grain = condition`` —
  ``traded`` needs ``gamma_volume > 0``; ``confirmed_zero`` needs
  ``gamma_volume = 0``.
* recovery ``clob:existence+data-api:trades+gamma:events`` — ``traded`` needs
  ``gamma_volume > 0`` or ``n_trades > 0``; ``confirmed_zero`` needs
  ``n_trades = 0`` and no positive or malformed ``gamma_volume``.

Anything else — no receipt, an ``unaddressable``/``indeterminate`` verdict, an
unknown probe, a missing or non-numeric figure, a non-Polymarket row — is not
evidence in EITHER direction and the scalar rule applies exactly as before. A
malformed receipt never upgrades knowledge and never erases a scalar reading.

Conflicts are explicit. ``traded`` receipt beside scalar 0: the 0 is the
recovery rail's old ``int(0.25)`` / Gamma-0-with-trades write and the receipt
holds the evidence, so ``traded``. ``confirmed_zero`` receipt beside a positive
scalar: two readings that cannot both be true, so ``unknown`` — neither claim is
published.

The receipt is CONDITION-grain: one Polymarket condition is one
``futures_markets`` row and its total is shared by that market's legs, exactly
as the scalar copy already is. It says the condition traded; it is not a
per-outcome trade count and nothing here reports it as one.

Read-side only (gotcha #21). Nothing here mutates ``is_winner``,
``opening_probability``, ``calibration_probability`` or any resolution.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from typing import Any

from app.utils.polymarket_evidence import RECOVERY_EVIDENCE_PROBE

#: Sources with no volume concept. Excluded BY SOURCE, never by a coverage
#: heuristic — see the module docstring.
EXCLUDED_SOURCES: tuple[str, ...] = ("odds_api", "datagolf")

#: The only source whose receipts this rule reads.
RECEIPT_SOURCE = "polymarket"

#: Forward writer's receipt provenance. Restated, not imported: the owner is
#: ``app.tasks.polymarket.POLYMARKET_CONDITION_VOLUME_PROBE`` and a utils module
#: must not import the poller. ``test_calibration_trade_evidence_1530`` asserts
#: the two strings are equal, so they cannot drift apart silently.
FORWARD_EVIDENCE_PROBE = "gamma:events:condition-volume"
FORWARD_EVIDENCE_GRAIN = "condition"

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
    "untraded. For Polymarket, a validated condition-level volume receipt (the "
    "condition's total, shared by its legs — not a per-outcome trade count) "
    "outranks the integer column: a traded receipt is traded even where the "
    "integer is empty or 0, a confirmed-zero receipt is untraded, and a "
    "confirmed-zero receipt beside positive volume is unknown. A malformed or "
    "unsupported receipt is ignored. "
    "odds_api and datagolf are excluded by source (no volume concept). "
    "Measurement only: changes no probability, no curve and no resolution."
)


def _json_number(receipt: str, key: str) -> str:
    """``receipt->key`` as numeric, or NULL when it is not a JSON number.

    A ``CASE``, not ``AND``: PostgreSQL does not promise left-to-right ``AND``
    evaluation, so ``jsonb_typeof(...) = 'number' AND (...)::numeric > 0`` can
    still cast a string and abort the whole statement. ``CASE`` order is
    guaranteed.
    """
    return (
        f"(CASE WHEN jsonb_typeof({receipt}->'{key}') = 'number'"
        f" THEN ({receipt}->>'{key}')::numeric END)"
    )


def _receipt_sql(metadata: str) -> tuple[str, str]:
    """(valid-traded, valid-confirmed-zero) SQL predicates over ``metadata``.

    The SQL twin of :func:`receipt_verdict`. ``->`` on a non-object JSONB
    yields NULL rather than raising, so a malformed ``market_metadata`` or
    ``volume_evidence`` simply fails every predicate.
    """
    r = f"({metadata}->'volume_evidence')"
    gv = _json_number(r, "gamma_volume")
    nt = _json_number(r, "n_trades")
    gv_absent = f"COALESCE(jsonb_typeof({r}->'gamma_volume'), 'null') = 'null'"
    forward = (
        f"{r}->>'probe' = '{FORWARD_EVIDENCE_PROBE}'"
        f" AND {r}->>'grain' = '{FORWARD_EVIDENCE_GRAIN}'"
    )
    recovery = f"{r}->>'probe' = '{RECOVERY_EVIDENCE_PROBE}'"
    traded = (
        f"({r}->>'verdict' = 'traded' AND ("
        f"({forward} AND {gv} > 0)"
        f" OR ({recovery} AND ({gv} > 0 OR {nt} > 0))))"
    )
    zero = (
        f"({r}->>'verdict' = 'confirmed_zero' AND ("
        f"({forward} AND {gv} = 0)"
        f" OR ({recovery} AND {nt} = 0 AND ({gv_absent} OR {gv} = 0))))"
    )
    return traded, zero


def trade_evidence_sql(
    source: str = "fm.source",
    volume: str = "fo.volume",
    open_interest: str = "fm.open_interest",
    metadata: str | None = None,
) -> str:
    """The rule as a SQL ``CASE``, against caller-supplied aliases.

    Parameterised on the aliases rather than hard-coded so the census (which
    joins ``fo``/``fm`` directly) and the producer (whose population chain
    carries the market columns on ``vm``) render the SAME predicate instead of
    each writing one that looks like it.

    ``metadata`` names the ``market_metadata`` JSONB column. Omitted, the
    ``CASE`` is the scalar rule exactly as it was (portable ANSI, so the SQLite
    oracle still executes it); supplied, the Polymarket receipt clauses are
    prepended after the source exclusion and the result is PostgreSQL-only.
    """
    excluded = ", ".join(f"'{s}'" for s in EXCLUDED_SOURCES)
    receipt_clauses = ""
    if metadata is not None:
        traded, zero = _receipt_sql(metadata)
        poly = f"{source} = '{RECEIPT_SOURCE}'"
        receipt_clauses = (
            f" WHEN {poly} AND {traded} THEN 'traded'"
            f" WHEN {poly} AND {zero} AND ({volume} IS NULL OR {volume} = 0)"
            " THEN 'untraded'"
            f" WHEN {poly} AND {zero} THEN 'unknown'"
        )
    return (
        "(CASE"
        f" WHEN {source} IN ({excluded}) THEN 'not_applicable'"
        f"{receipt_clauses}"
        f" WHEN {volume} > 0 THEN 'traded'"
        f" WHEN {volume} = 0 THEN 'untraded'"
        f" WHEN {volume} IS NULL AND {open_interest} > 0 THEN 'traded_open_interest'"
        " ELSE 'unknown' END)"
    )


def _number(value: Any) -> float | None:
    """A JSON number as float, else None — ``jsonb_typeof = 'number'`` in Python.

    ``bool`` is excluded explicitly (it is an ``int`` subclass, and JSON
    ``true`` is not a number to PostgreSQL either).
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def receipt_verdict(market_metadata: Any) -> str | None:
    """``'traded'``, ``'confirmed_zero'``, or None for "not evidence".

    Validates ``market_metadata['volume_evidence']`` against the two writers
    that produce it (see the module docstring). Everything that is not a
    receipt one of those writers could have written returns None — including
    ``unaddressable``, which is a real receipt that says "cannot know".
    """
    if not isinstance(market_metadata, Mapping):
        return None
    receipt = market_metadata.get("volume_evidence")
    if not isinstance(receipt, Mapping):
        return None
    verdict = receipt.get("verdict")
    probe = receipt.get("probe")
    gv = _number(receipt.get("gamma_volume"))
    nt = _number(receipt.get("n_trades"))
    forward = (
        probe == FORWARD_EVIDENCE_PROBE
        and receipt.get("grain") == FORWARD_EVIDENCE_GRAIN
    )
    recovery = probe == RECOVERY_EVIDENCE_PROBE
    if verdict == "traded":
        if forward and gv is not None and gv > 0:
            return "traded"
        if recovery and (
            (gv is not None and gv > 0) or (nt is not None and nt > 0)
        ):
            return "traded"
        return None
    if verdict == "confirmed_zero":
        if forward and gv == 0:
            return "confirmed_zero"
        if recovery and nt == 0 and (receipt.get("gamma_volume") is None or gv == 0):
            return "confirmed_zero"
        return None
    return None


def classify(
    source: str | None,
    volume: int | None,
    open_interest: int | None,
    market_metadata: Any = None,
) -> str:
    """The rule in Python — the canonical, unit-testable twin of the SQL.

    Kept beside :func:`trade_evidence_sql` and asserted equivalent to it by
    ``test_calibration_trade_evidence_1530`` (SQLite, scalar rule) and
    ``integration/test_calibration_trade_evidence_receipt_1870_pg`` (real
    PostgreSQL JSONB, receipt rule), the same way
    ``outcome_is_calibration_liquid`` sits beside ``KALSHI_LIQUIDITY_EXISTS``.
    The pair is what lets the rule be tested without a database and still be the
    rule production runs. ``market_metadata`` defaults to None, which is the
    scalar rule unchanged.
    """
    if source in EXCLUDED_SOURCES:
        return "not_applicable"
    if source == RECEIPT_SOURCE:
        verdict = receipt_verdict(market_metadata)
        if verdict == "traded":
            return "traded"
        if verdict == "confirmed_zero":
            return "untraded" if volume is None or volume == 0 else "unknown"
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
