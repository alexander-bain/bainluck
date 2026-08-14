"""Polymarket trading-evidence classification — the gotcha #53 disambiguator.

WHY THIS MODULE EXISTS
======================

``FuturesOutcome.volume`` documents itself as ``NULL = not yet fetched,
0 = confirmed zero trading``. On the Polymarket side that contract was never
honoured: a census of resolved outcomes with ``resolution_date`` in the 45 days
to 2026-08-14 found **0 rows — 0.00%** at ``volume = 0``, against 5.08% on
Kalshi (#1870). Polymarket stored "nothing traded" and "we never asked"
identically, so every consumer reading ``volume IS NULL`` as "untraded" was
inventing a fact about the market out of a fact about our pipeline.

That is gotcha #53 — *an empty 200 is not an absence, it is a response shape* —
reproduced inside our own writer rather than at an API boundary. Polymarket
serves it in the purest form available: ``GET data-api/trades?market=<cid>``
answers **HTTP 200 with ``[]``** for a market that Polymarket cannot address at
all, byte-identically to a live market that genuinely never traded.

MEASURED 2026-08-14 (CAL-P060) — the numbers this module encodes
----------------------------------------------------------------

Probed against production condition_ids, control-first. The control is
load-bearing: the first probe attempted here
(``gamma/markets?condition_ids=<cid>``) returned ``[]`` for the old specimens
AND for a market resolved five days earlier that carries volume in our own DB.
Read without the control it looks exactly like a retention cliff. It is a
non-functional filter. Ruling 050 in miniature — a probe that cannot fail is
not a probe.

Four addressing facts, each measured, each with its control:

1. ``clob/markets/{conditionId}`` — **200 discriminates, 404 discriminates.**
   200 for specimens resolving 2023-11-03 and later; 404 for 2023-01-01 and
   earlier. This is the ONLY signal that separates purged from untraded.
2. ``data-api/trades?market={conditionId}`` — real trades, supports ``offset``.
   Returns ``200 []`` for BOTH the unaddressable and the untraded. Alone it
   proves nothing; paired with (1) it proves everything.
3. ``gamma/markets/{conditionId}`` — **422 for every input, including the
   control.** Gamma's path parameter is the NUMERIC market id, never the 0x
   condition id. Re-confirmed here, but NOT a new finding: CAL-P003 diagnosed
   this on 2026-08-07 and callers now filter 0x ids out of that path
   (``tests/test_poly_gamma_condition_id_lookup.py``). It is restated only
   because it is the reason a conditionId cannot be resolved to a volume
   directly, which is what forces route (4).
4. ``gamma/events/{polymarket_event_id}`` — **200 with per-sub-market
   ``volume`` + ``conditionId``, and no offset cap.** We already store that id
   on 107,168 Polymarket markets. This is the recovery address.

THE THREE-STATE CONTRACT IS ACTUALLY FOUR
------------------------------------------

#1870 asks for a census distinguishing three states: unfetched / confirmed-zero
/ traded. The probe found a fourth that the issue could not have anticipated,
and it is the one that matters most:

    UNADDRESSABLE — Polymarket will not serve this market at any address.

``volume`` MUST stay NULL for it. Writing 0 there would be the precise error
gotcha #53 exists to forbid: collapsing "the venue deleted this" into "the
venue says nobody traded". The receipt records *why* the NULL is permanent, so
that a NULL with a receipt and a NULL without one are never confused again.

    volume=0    + receipt          -> confirmed zero, venue said so
    volume>0    + receipt          -> traded
    volume=NULL + receipt          -> asked, unanswerable (permanent)
    volume=NULL + NO receipt       -> never asked  <- and ONLY this

IS THE BOUNDARY A CLOCK?
------------------------

Unknown from one observation, and this module refuses to guess. Kalshi's cliff
(gotcha #35) is a rolling ~74-86 days and cost three recovery rails before
anyone dated it. This boundary sits ~2.8-3.6 years back and looks structural
rather than rolling, but **a single measurement cannot distinguish a fixed
boundary from a slow one**, and the difference decides whether the backfill is
urgent. So the constant below is dated and re-measurable —
``backend/scripts/probe_polymarket_retention.py`` re-derives it and fails if it
moved. Treat a moved boundary as a P1: it means the cohort is expiring.

Consequently the sweep is ordered **oldest-first WITHIN a floor** — gotcha #41's
amended lesson (CAL-P009) applied before it can bite a third time. Oldest-first
alone would spend the whole budget on the ~999 permanently-unaddressable rows
that sort first and can never be recovered; a floor alone would leave the
oldest recoverable rows last, which is fatal if the boundary turns out to roll.
Ordering is never the whole answer — the floor is what the ordering starts on.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Measured constants. Prose is not a predicate (gotcha #35): CAL-P008 found
# three separate recovery rails that all ground purged markets because their
# authors cited an undated "~2-3 months" written in a paragraph. These are
# importable, dated, and re-derived by probe_polymarket_retention.py.
# ---------------------------------------------------------------------------

#: Date the addressability boundary below was last measured against the venue.
PM_BOUNDARY_MEASURED_ON = date(2026, 8, 14)

#: Newest specimen observed UNADDRESSABLE (clob 404). Everything at or before
#: this date is presumed unrecoverable until a re-measure says otherwise.
PM_UNADDRESSABLE_THROUGH = date(2023, 1, 1)

#: Oldest specimen observed ADDRESSABLE (clob 200). The true boundary lies in
#: the half-open interval (PM_UNADDRESSABLE_THROUGH, PM_ADDRESSABLE_FROM]. It is
#: deliberately NOT collapsed to a single day we did not measure.
PM_ADDRESSABLE_FROM = date(2023, 11, 3)

#: The sweep floor. Rows resolving at or before this are not probed by default:
#: measured unrecoverable, and they sort FIRST under oldest-first ordering, so
#: without this floor they would consume the entire budget forever.
PM_SWEEP_FLOOR = PM_UNADDRESSABLE_THROUGH

#: gamma /markets?offset= is refused with HTTP 422 above this. Measured
#: 2026-08-14: offset=2000 -> 200; offset=2050 -> 422. This is the hard ceiling
#: that makes the paging backfill structurally unable to reach the tail, and the
#: reason the recovery rail addresses events by id instead of paging markets.
GAMMA_MARKETS_MAX_OFFSET = 2000


class PMEvidence(str, Enum):
    """What the venue actually told us about a market's trading.

    Deliberately NOT a bool and NOT Optional[int]. The whole defect in #1870 is
    that two distinct facts were being stored in one nullable integer, so the
    type that replaces it has to be able to say "I asked and cannot know".
    """

    TRADED = "traded"
    CONFIRMED_ZERO = "confirmed_zero"
    UNADDRESSABLE = "unaddressable"
    #: The probe itself failed (429, 5xx, timeout). Never write a value on this
    #: — gotcha #36: a rate limit must never be indistinguishable from a fact.
    INDETERMINATE = "indeterminate"


def classify_pm_evidence(
    *,
    clob_status: Optional[int],
    trades: Optional[list],
    gamma_volume: Optional[float] = None,
) -> PMEvidence:
    """Decide what the venue said, from two independent signals.

    ``clob_status`` is the HTTP status of ``clob/markets/{conditionId}`` — the
    EXISTENCE signal. ``trades`` is the parsed body of
    ``data-api/trades?market={conditionId}`` — the ACTIVITY signal, or None if
    that call did not complete. ``gamma_volume`` is the authoritative figure
    from ``gamma/events/{id}`` when available.

    The ordering of these checks is the entire point. Existence is consulted
    BEFORE activity, because an empty activity response is uninformative until
    existence is known. Inverting them reproduces the bug.
    """
    # Existence first, always. A 404 means every activity reading below is a
    # statement about Polymarket's index, not about the market.
    if clob_status == 404:
        return PMEvidence.UNADDRESSABLE

    # Anything that is not a clean 200 is a failed probe, not a fact. Includes
    # 429 and 5xx explicitly (gotcha #36) and None (call never completed).
    if clob_status != 200:
        return PMEvidence.INDETERMINATE

    # Addressable. A positive authoritative volume settles it outright.
    if gamma_volume is not None and gamma_volume > 0:
        return PMEvidence.TRADED

    if trades is None:
        return PMEvidence.INDETERMINATE

    if len(trades) > 0:
        return PMEvidence.TRADED

    # Addressable, zero trades, and (if we had it) zero authoritative volume.
    # THIS is the row that has never once been written on the Polymarket path.
    return PMEvidence.CONFIRMED_ZERO


def volume_to_write(
    evidence: PMEvidence, gamma_volume: Optional[float] = None
) -> Optional[int]:
    """The value to store in ``futures_outcomes.volume``, or None to leave it.

    Returning None means "do not write" — it is NOT the same as writing NULL,
    and callers must not turn it into one. UNADDRESSABLE and INDETERMINATE both
    return None, for opposite reasons: the first can never be known, the second
    is not known *yet*. Only the receipt tells them apart.
    """
    if evidence is PMEvidence.CONFIRMED_ZERO:
        return 0
    if evidence is PMEvidence.TRADED and gamma_volume is not None:
        # Integer column; clamp as the existing Gamma backfill does. Magnitude
        # past 2B is irrelevant to a traded/untraded tag.
        return min(int(gamma_volume), 2_000_000_000)
    return None


def build_evidence_receipt(
    evidence: PMEvidence,
    *,
    n_trades: Optional[int] = None,
    gamma_volume: Optional[float] = None,
    fetched_at: Optional[datetime] = None,
) -> dict[str, Any]:
    """The ``market_metadata['volume_evidence']`` receipt.

    This is the ``fetched_at`` half of the fix. It lives in JSONB rather than a
    new column because CAL-P060 holds ``migration_slot: none`` — and because the
    fetch is addressed per market (one conditionId), which is exactly this
    grain. ``FuturesMarket.volume_updated_at`` was NOT reused: the Polymarket
    poller already writes it for event-level aggregate volume, and overloading a
    field with a second meaning is the defect being fixed here, not a fix.
    """
    stamped = fetched_at or datetime.now(timezone.utc)
    receipt: dict[str, Any] = {
        "verdict": evidence.value,
        "fetched_at": stamped.isoformat(),
        "probe": "clob:existence+data-api:trades+gamma:events",
        "boundary_measured_on": PM_BOUNDARY_MEASURED_ON.isoformat(),
    }
    if n_trades is not None:
        receipt["n_trades"] = n_trades
    if gamma_volume is not None:
        receipt["gamma_volume"] = gamma_volume
    if evidence is PMEvidence.UNADDRESSABLE:
        # Say it in the row. A successor reading this must not have to rederive
        # why a NULL here is permanent rather than pending.
        receipt["reason"] = (
            "clob 404 — venue cannot address this market; volume is "
            "permanently unknowable, NOT zero"
        )
    return receipt
