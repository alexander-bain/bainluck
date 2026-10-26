"""#11157 — which raw observations of a Yes/No pair answer for one another's scale.

PILLARS: TRUTH / FORMATTING. SHIP: a market chart shows its genuine probability
move without inventing observation times or freshness.

WHY A RULE BEYOND THE EXACT INSTANT. Polymarket's CLOB `prices-history` stamps
each token at its own second: market 65678073 at fidelity=1 has Yes 461 points
and No 459 with ZERO shared instants (Live, #11157 comment 6229278103). PR
#11160 paired exact instants only, so on the venue's real shape it pairs
nothing and `/history` refuses every point.

WHERE THE RULE RUNS. ONCE, in the fill, on each leg's RAW series (after
layering and the last-good merge, before compaction), and the decision is
written into the bank as an annotation on both points (`VenuePoint.pair_at` /
`peer_at`). The reader never re-pairs: it VERIFIES the annotation (lane1's I2).
That is the point of running it here — ambiguity is a property of the raw
series, and a reader looking at compacted rows can see a sample as unique
because compaction dropped its neighbour.

WHAT A PAIR IS (lane1's invariants I4–I6, 2026-10-17 early review):
  * same tier label — one call, one fidelity; never across tiers (I5);
  * |skew| ≤ S, where S = min(`PAIR_SKEW_MAX_SECONDS`, half the declared grain,
    half of each sample's own local spacing in its leg). An undeclared grain
    gives S = 0, so it pairs only at an exact shared instant (I4);
  * one-to-one: a sample with two candidates within S pairs with neither, and a
    pair stands only when each is the other's ONLY candidate (I4/I6).

WHAT A PAIR IS NOT. It is not a claim of simultaneity, and it moves no clock:
each half keeps its own raw instant everywhere (I1). `pair_at` — the later of
the two raw instants — is KNOWLEDGE time, the first instant both values
existed, and is never written into an observation field.

S IS SET (lane1, 2026-10-17 05:55Z, on Live's E1 bodies layered as the fill
layers them): raising the 30 s ceiling to 120 s pairs 0 more points on all three
measured markets, and every unpaired point there has no peer at all. Reopen S
only when the LAYERED input shows same-tier pairs with a peer present but skew
above 30 s; any new ceiling depends only on the tier label, so the reader can
verify it, and stays <= G/4.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from datetime import datetime, timedelta
from typing import Any, Sequence

from app.utils.futures_chart_series import declared_resolution_seconds

#: Lane1's I4 ceiling on the skew between two halves of one pair. Not the grain:
#: a grain is how often the venue was asked, not how far apart two tokens' quotes
#: may sit and still describe one moment.
PAIR_SKEW_MAX_SECONDS = 30.0

#: Lane1's I7 refusal guard: an admitted pair whose two raw values disagree with
#: a complementary book by more than this is withheld and counted. It catches a
#: mixed pair across a move; it is never evidence of identity or of a clock.
#: POLYMARKET ONLY: its premise is one condition's Yes and No sharing one book.
#: A Kalshi pair is two tickers on two books, so a sum off 1.00 there is two
#: genuine prices, not a straddle (#10955 R1) — the reader never asks it of one.
PAIR_COHERENCE_EPSILON = 0.01


def pair_is_incoherent(p_a: float, p_b: float) -> bool:
    """I7: do two paired raw values disagree with one complementary book by more
    than `PAIR_COHERENCE_EPSILON`? The gap is rounded to 9 places first so float
    noise never withholds a whole-cent book: 0.795 + 0.195 is 0.99 exactly at the
    venue, but 0.010000000000000009 in binary (lane1's N4)."""
    return round(abs(float(p_a) + float(p_b) - 1.0), 9) > PAIR_COHERENCE_EPSILON

#: `(observed_at, tier_label)` — what the fill holds per point.
Observation = tuple[datetime, str]


def pair_skew_bound_seconds(tier_label: str | None) -> float:
    """S's tier half: min(ceiling, grain/2), or 0.0 when the tier declares nothing."""
    grain = declared_resolution_seconds(tier_label)
    if grain is None:
        return 0.0
    return min(PAIR_SKEW_MAX_SECONDS, grain / 2.0)


def _local_spacing(leg: Sequence[Observation]) -> list[float]:
    """Each sample's distance to its nearest neighbour in its OWN leg (inf if alone)."""
    out: list[float] = []
    for k, (ts, _tier) in enumerate(leg):
        gaps = []
        if k > 0:
            gaps.append((ts - leg[k - 1][0]).total_seconds())
        if k + 1 < len(leg):
            gaps.append((leg[k + 1][0] - ts).total_seconds())
        out.append(min(gaps) if gaps else float("inf"))
    return out


def pair_observations(
    leg_a: Sequence[Observation], leg_b: Sequence[Observation]
) -> list[tuple[int, int]]:
    """`(index_in_a, index_in_b)` for every pair the rule admits. Each leg must be
    strictly ascending (the bank's own invariant, `parse_points`)."""
    spacing_a, spacing_b = _local_spacing(leg_a), _local_spacing(leg_b)

    def bound(i: int, j: int) -> float:
        return min(
            pair_skew_bound_seconds(leg_a[i][1]),
            spacing_a[i] / 2.0,
            spacing_b[j] / 2.0,
        )

    times_b = [ts for ts, _tier in leg_b]
    reach = timedelta(seconds=PAIR_SKEW_MAX_SECONDS)
    candidates_a: dict[int, list[int]] = {}
    candidates_b: dict[int, list[int]] = {}
    for i, (ts_a, tier_a) in enumerate(leg_a):
        # S never exceeds the ceiling, so only that window can hold a candidate.
        for j in range(bisect_left(times_b, ts_a - reach), bisect_right(times_b, ts_a + reach)):
            if leg_b[j][1] != tier_a:
                continue
            if abs((ts_a - times_b[j]).total_seconds()) <= bound(i, j):
                candidates_a.setdefault(i, []).append(j)
                candidates_b.setdefault(j, []).append(i)
    return sorted(
        (i, js[0])
        for i, js in candidates_a.items()
        if len(js) == 1 and candidates_b.get(js[0]) == [i]
    )


def paired_binary_leg_ids(
    outcomes: Sequence[Any], entries: dict[int, dict], *, market: Any = None
) -> tuple[int, int] | None:
    """Return `(oid_a, oid_b)` only for an identity-admitted 2-leg mutually-exclusive binary pair.

    #11160's Polymarket identity rule, moved here from the fill so the fill and
    the reader import one copy from a module neither depends on: one 0x
    condition, two distinct tokens, exactly `{c}_yes` / `{c}_no`. `entries` maps
    outcome id to a dict carrying that outcome's `contract`.

    #10955 extends admission to 2-leg mutually-exclusive Kalshi events only when
    full-field exclusivity is proved from the stored market and contract
    representation (`_kalshi_paired_binary_leg_ids`).
    """
    if len(outcomes) != 2:
        return None
    oid_a, oid_b = int(outcomes[0].id), int(outcomes[1].id)
    if oid_a == oid_b or oid_a not in entries or oid_b not in entries:
        return None
    c_a = entries[oid_a].get("contract") or {}
    c_b = entries[oid_b].get("contract") or {}
    if c_a.get("venue") == "polymarket" and c_b.get("venue") == "polymarket":
        if market is not None and getattr(market, "source", None) != "polymarket":
            return None
        cond_id = c_a.get("condition_id")
        if (
            not isinstance(cond_id, str)
            or not cond_id.startswith("0x")
            or c_b.get("condition_id") != cond_id
        ):
            return None
        if not c_a.get("token_id") or not c_b.get("token_id") or c_a.get("token_id") == c_b.get("token_id"):
            return None
        if {c_a.get("outcome_external_id"), c_b.get("outcome_external_id")} != {
            f"{cond_id}_yes",
            f"{cond_id}_no",
        }:
            return None
        return oid_a, oid_b
    if c_a.get("venue") == "kalshi" and c_b.get("venue") == "kalshi":
        return _kalshi_paired_binary_leg_ids(
            outcomes, entries, c_a, c_b, oid_a, oid_b, market=market
        )
    return None


def _kalshi_paired_binary_leg_ids(
    outcomes: Sequence[Any],
    entries: dict[int, dict],
    c_a: dict,
    c_b: dict,
    oid_a: int,
    oid_b: int,
    *,
    market: Any = None,
) -> tuple[int, int] | None:
    """Full-field semantic identity check for a 2-leg mutually-exclusive Kalshi market (#10955).

    Shared event ticker prefix + two displayed rows is never sufficient by itself:
    Kalshi events can have >=3 sub-markets (with 1 withdrawn/unlisted), cumulative
    threshold ladders (gotcha #17), numeric range bins, participation/multi-winner
    contracts, or draw-capable 3-way boards. Numerical near-complementarity is
    never used as evidence of identity.
    """
    from app.utils.market_shape import (
        REL_COMPETITORS,
        REL_COMPLEMENTS,
        SHAPE_CLAIM,
        SHAPE_DUEL,
        classify_market_semantics,
    )

    if market is None:
        m_a = getattr(outcomes[0], "market", None)
        m_b = getattr(outcomes[1], "market", None)
        if m_a is not None and m_a is m_b:
            market = m_a
    if market is None or getattr(market, "source", None) != "kalshi":
        return None
    if getattr(market, "mutually_exclusive", None) is not True:
        return None
    if len(entries) != 2:
        return None
    market_id = getattr(market, "id", None)
    for o in outcomes:
        o_market = getattr(o, "market", None)
        if o_market is not None and o_market is not market:
            return None
        o_mid = getattr(o, "market_id", None)
        if o_mid is not None and market_id is not None and int(o_mid) != int(market_id):
            return None

    event_ticker = (getattr(market, "external_id", None) or "").strip()
    if not event_ticker:
        return None
    meta = getattr(market, "market_metadata", None)
    if not isinstance(meta, dict):
        return None
    meta_ticker = meta.get("kalshi_event_ticker")
    if meta_ticker is not None and str(meta_ticker).strip() != event_ticker:
        return None
    # `poll_kalshi_markets` writes `market_count = len(event.markets)`. Requiring
    # exact integer 2 refuses any >=3-leg event where a leg was withdrawn/unlisted.
    market_count = meta.get("market_count")
    if type(market_count) is not int or market_count != 2:
        return None

    market_outcomes = getattr(market, "outcomes", None)
    if (
        isinstance(market_outcomes, (str, bytes))
        or not isinstance(market_outcomes, Sequence)
        or len(market_outcomes) != 2
    ):
        return None
    try:
        market_oids = {int(getattr(o, "id")) for o in market_outcomes}
    except (TypeError, ValueError):
        return None
    if market_oids != {oid_a, oid_b}:
        return None

    legs: list[str] = []
    for outcome, contract in ((outcomes[0], c_a), (outcomes[1], c_b)):
        ticker = contract.get("ticker")
        if not isinstance(ticker, str) or not ticker or "-" not in ticker:
            return None
        if contract.get("outcome_external_id") != ticker:
            return None
        if (getattr(outcome, "external_id", None) or "").strip() != ticker:
            return None
        ev, leg = ticker.rsplit("-", 1)
        if ev != event_ticker or not leg:
            return None
        legs.append(leg)
    if c_a.get("ticker") == c_b.get("ticker") or legs[0] == legs[1]:
        return None

    catchall_names = {
        "field",
        "the field",
        "other",
        "others",
        "all other",
        "all others",
        "any other",
        "someone else",
    }
    names = [(getattr(o, "name", None) or "").strip() for o in outcomes]
    if any(not n or n.lower() in catchall_names for n in names):
        return None
    persisted_shape = meta.get("shape")
    if isinstance(persisted_shape, dict):
        if (
            persisted_shape.get("exhaustive") is not True
            or str(persisted_shape.get("expected_winners")).strip() != "1"
            or persisted_shape.get("outcome_relation") not in (REL_COMPETITORS, REL_COMPLEMENTS)
        ):
            return None
    source_kind = str(meta.get("source_market_kind") or meta.get("market_kind") or "")
    if any(tok in source_kind.lower() for tok in ("top", "make_cut", "qualif", "advance")):
        return None
    sem = classify_market_semantics(
        outcome_names=names,
        external_id=event_ticker,
        source="kalshi",
        source_kind=source_kind,
        mutually_exclusive=True,
        venue_leg_count=2,
    )
    if (
        sem.get("display_shape") not in (SHAPE_CLAIM, SHAPE_DUEL)
        or sem.get("exhaustive") is not True
        or sem.get("expected_winners") != 1
        or sem.get("outcome_relation") not in (REL_COMPETITORS, REL_COMPLEMENTS)
        or "draw_capable" in (sem.get("evidence") or ())
    ):
        return None
    return oid_a, oid_b
