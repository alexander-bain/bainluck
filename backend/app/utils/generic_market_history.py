"""#7351 — the venue's own history for an ORDINARY market chart, bound to identity.

PILLAR: TRUTH. SHIP: opening a generic Discover market shows its supported
historical observations on the phone and the web, including history our
periodic polls missed.

WHAT THIS IS. `tasks/futures_chart_series_fill` already fetches Kalshi
candlesticks and the Polymarket CLOB series and caches them — for the CONCEPT
envelope. That cache is keyed by NORMALISED OUTCOME NAME and may blend a sibling
venue's leg into the line (`find_venue_legs` + `blend_venues`). Both are right
for a tournament page and both are unsafe for a single generic question: every
binary market on the site has an outcome named "Yes", and a name is not an
identity. So the generic readers do not consume that cache. They consume THIS
representation, which is additive, versioned, and leaves the concept cache and
its readers byte-for-byte alone:

    futures:generic-history:v1:{market_id}

    {"schema": "generic-market-history", "version": "v1",
     "scale": "venue_yes_probability_raw",
     "market_id", "market_source", "market_external_id",
     "attempted_at", "built_at", "status": "ok" | "degraded" | "empty",
     "market_settled": bool,   # was the market already settled when this ran?
                               # `plan_on_demand_fill` needs it to tell an answer
                               # from an attempt that predates the settlement.
     "outcomes": {"<outcome_id>": {
         "outcome_id", "contract": {...exact venue contract...},
         "points": [[iso_ts, probability, yes_bid, yes_ask, last_price, tier], …],
         "observed_through": iso_ts }},
     "stats": {...}}

THREE BINDINGS, ALL CHECKED ON EVERY READ (`validate_payload`), because a cache
is only as honest as the reader that trusts it:

  1. THE MARKET — id, source and venue external id must equal the row asking.
  2. THE OUTCOME — the series is filed under `FuturesOutcome.id`, and the id must
     be one of THIS market's own charted outcomes. Never a name.
  3. THE CONTRACT — the exact Kalshi market ticker, or the exact Polymarket
     condition id + CLOB token, and it must still equal the outcome row's own
     `external_id`. A row re-pointed at another contract orphans its old series
     instead of inheriting it.

A series that fails any binding is REFUSED, not repaired, and the refusal is
named in the reader's `venue_history` block.

THE BOOK TRAVELS WITH THE POINT. A Kalshi candle's closing bid/ask and last
trade are cached beside the price so the readers can run the SAME canonical
support predicates they already run on our own snapshot rows
(`_drop_unsupported_snapshot_points`: #5611 / #5876 / #6532 / #6757). Those
predicates depend on the outcome's GRADE, which can change after a fill, so they
are asked at read time, of the point's own book — never baked into the cache.

EVERYTHING HERE IS PURE. No DB, no HTTP, no Redis, no clock: the I/O half is
`app/tasks/generic_market_history_fill.py`.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

SCHEMA = "generic-market-history"

#: BUMP when the payload shape changes. A reader that cannot tell v1 from v2
#: draws last week's shape from this week's code (the concept cache's own rule).
CACHE_VERSION = "v1"

#: The one scale this cache holds: the venue's raw YES probability for the exact
#: contract — the same quantity the venue's own `futures_odds_snapshots` rows
#: store. It is NOT de-vigged, NOT squeezed and NOT renormalised; a reader whose
#: printed scale differs refuses the series rather than converting it.
SCALE = "venue_yes_probability_raw"

#: Sources with a history endpoint. Anything else has no venue series to fetch
#: and its captures are all there is.
VENUE_SOURCES = ("kalshi", "polymarket")

#: A cached point may not claim to have been observed after the payload that
#: carries it was built. The slack absorbs venue/our clock skew and a candle
#: whose period closes as the fill runs.
FUTURE_SKEW = timedelta(minutes=5)

#: Suffixes a Polymarket LEG id wears on top of its condition id.
#:
#: `_side1` joined the pair in #7505: on a sole-moneyline event the venue names
#: both sides but publishes one market, so the decomposition that would have made
#: a `_yes`/`_no` pair never runs and the partner is stored beside the bare id
#: instead. Left out, `strip_polymarket_leg` returned `0x…_side1` as the CONDITION
#: id, Gamma's `by_condition` map missed it, and every companion counted as
#: `no_exact_condition` — a stored, priced, reader-visible leg whose chart could
#: never be drawn (CERT-3251 measured exactly that: `no_exact_condition: 1`).
#:
#: 🔴 NOT THE SAME LIST AS `duplicate_condition_outcomes.BINARY_LEG_SUFFIXES`,
#: and the two must not be unified. That one decides whether a suffixed leg is a
#: DUPLICATE of the bare row beside it and drops it at serve time; the companion
#: is a real second rung, so teaching it `_side1` would filter #7505 off every
#: reader surface. This list only answers "what is this leg's condition id",
#: which is the same question for all three suffixes.
POLYMARKET_LEG_SUFFIXES = ("_yes", "_no", "_side1")


def cache_key(market_id: int) -> str:
    return f"futures:generic-history:{CACHE_VERSION}:{int(market_id)}"


def durable_identity(market_id: int) -> str:
    """This market's row in ``durable_state_snapshots`` (#7807).

    🔴 THE VERSION IS DELIBERATELY NOT IN THIS STRING, and that is the one way it
    differs from :func:`cache_key`. A Redis key may carry the version because the
    old key EXPIRES: bump to v2 and every orphaned v1 key deletes itself. A
    Postgres row has no TTL, so a versioned identity would leave one dead row per
    market per bump, for ever. Sharing the identity makes a v2 write REPLACE its
    own v1 row, and the reader is protected by ``schema_version`` instead —
    ``read_snapshot(expected_version=CACHE_VERSION)`` types a not-yet-replaced v1
    row as ``wrong_version`` and refuses to serve it. Same guarantee, no orphans.
    """
    return f"generic-history:{int(market_id)}"


def claim_key(market_id: int) -> str:
    return f"futures:generic-history-claim:{CACHE_VERSION}:{int(market_id)}"


def budget_key(hour_stamp: str) -> str:
    return f"futures:generic-history-budget:{CACHE_VERSION}:{hour_stamp}"


def coarse_budget_key(hour_stamp: str) -> str:
    """The COARSE share of the hour, counted on its OWN key (#7547).

    🔴 A SECOND KEY, NOT A SECOND READING OF THE FIRST. Two caps over one counter
    reads like an accounting detail and is not: a coarse request that is REFUSED
    for exceeding the coarse share still had to touch the counter to find that
    out, and on a shared key that touch is indistinguishable from work done. The
    thin reserve then drains at the rate coarse charts are turned AWAY — fastest
    exactly when coarse traffic is heaviest — and the reader who pays is the one
    with no line at all. Separate keys make a refusal unable to reach the other
    population's budget at all, rather than merely unlikely to.
    """
    return f"futures:generic-history-budget-coarse:{CACHE_VERSION}:{hour_stamp}"


# ---------------------------------------------------------------------------
# Points
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VenuePoint:
    """One venue observation: a real instant, a real price, and its own book."""

    observed_at: datetime
    probability: float
    yes_bid: float | None = None
    yes_ask: float | None = None
    last_price: float | None = None
    tier: str = ""

    def as_row(self) -> list:
        return [
            self.observed_at.isoformat(),
            round(self.probability, 6),
            self.yes_bid,
            self.yes_ask,
            self.last_price,
            self.tier,
        ]


@dataclass
class VenueSnapshotRow:
    """A venue point wearing the columns `_drop_unsupported_snapshot_points` reads.

    Deliberately the SAME attribute names as `FuturesOddsSnapshot`, so the
    readers hand these to the canonical support filter unchanged — one price
    policy, asked of one more kind of row, rather than a second copy of it.
    """

    outcome_id: int
    captured_at: datetime
    probability: float
    bookmaker: str
    yes_bid: float | None = None
    yes_ask: float | None = None
    last_price: float | None = None
    tier: str = ""


def _finite_prob(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        p = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(p) or p < 0.0 or p > 1.0:
        return None
    return p


def _opt_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _parse_aware(raw: Any) -> datetime | None:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        stamp = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if stamp.tzinfo is None:
        # A naive stamp is ambiguous by up to a day. The fill writes aware UTC;
        # anything else did not come from the fill.
        return None
    return stamp.astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# Contracts — the exact venue instrument an outcome row IS
# ---------------------------------------------------------------------------


def strip_polymarket_leg(external_id: str) -> str:
    for suffix in POLYMARKET_LEG_SUFFIXES:
        if external_id.endswith(suffix):
            return external_id[: -len(suffix)]
    return external_id


def kalshi_contract(outcome: Any) -> dict | None:
    """The Kalshi market ticker this outcome row is, or None.

    `tasks/kalshi.py` writes `FuturesOutcome.external_id = market.ticker` under a
    `(market_id, external_id)` unique key, so one row is one ticker and its
    stored probability is that ticker's YES price (gotcha #17). The candlestick
    series for the ticker is therefore this row's own history and nobody else's.
    """
    ticker = (getattr(outcome, "external_id", None) or "").strip()
    if not ticker:
        return None
    return {"venue": "kalshi", "ticker": ticker, "outcome_external_id": ticker}


def polymarket_contract(outcome: Any, *, token_id: str, resolved_via: str) -> dict | None:
    external_id = (getattr(outcome, "external_id", None) or "").strip()
    condition_id = strip_polymarket_leg(external_id)
    if not external_id or not condition_id.startswith("0x") or not token_id:
        return None
    return {
        "venue": "polymarket",
        "condition_id": condition_id,
        "token_id": str(token_id),
        "outcome_external_id": external_id,
        "resolved_via": resolved_via,
    }


def wanted_gamma_outcome_name(outcome: Any) -> str:
    """Which of Gamma's index-aligned outcome names this ROW is the book for.

    A decomposed leg says so in its own id (`…_yes` / `…_no`) and that beats its
    display name. A bare condition id is asked by our row's own name first — the
    two-way head-to-head whose Gamma outcomes are the contenders — and
    `token_for_outcome` falls back to the Yes token for a named rung. BY NAME,
    NEVER BY POSITION: a mis-attributed token does not make a line stale, it
    makes it INVERTED (Q489).
    """
    external_id = (getattr(outcome, "external_id", None) or "").strip()
    if external_id.endswith("_no"):
        return "No"
    if external_id.endswith("_yes"):
        return "Yes"
    return (getattr(outcome, "name", None) or "").strip()


# ---------------------------------------------------------------------------
# Payload
# ---------------------------------------------------------------------------


def build_payload(
    market: Any,
    entries: dict[int, dict],
    *,
    now: datetime,
    stats: dict,
    degraded: bool,
) -> dict:
    """Assemble the cache payload. `entries` is `{outcome_id: {"contract", "points"}}`."""
    outcomes: dict[str, dict] = {}
    for outcome_id, entry in entries.items():
        points: Sequence[VenuePoint] = entry.get("points") or []
        if not points:
            continue
        outcomes[str(int(outcome_id))] = {
            "outcome_id": int(outcome_id),
            "contract": entry["contract"],
            "points": [p.as_row() for p in points],
            "observed_through": points[-1].observed_at.isoformat(),
        }
    status = "degraded" if degraded else ("ok" if outcomes else "empty")
    return {
        "schema": SCHEMA,
        "version": CACHE_VERSION,
        "scale": SCALE,
        "market_id": int(market.id),
        "market_source": market.source,
        "market_external_id": market.external_id,
        "attempted_at": now.isoformat(),
        "built_at": now.isoformat(),
        "status": status,
        "outcomes": outcomes,
        "stats": stats,
    }


def payload_built_at(payload: dict | None) -> datetime | None:
    """The instant this payload was BUILT, or None when it will not say.

    Deliberately narrower than :func:`payload_age_seconds`, which falls back to
    `attempted_at`: an attempt that wrote nothing still dates itself, and that is
    the right stamp for "may a reader ask again". It is the wrong stamp for the
    durable tier's GENERATION, which orders builds — taking an attempt's stamp
    would let a fill that produced nothing outrank the build it failed to beat.
    """
    if not isinstance(payload, dict):
        return None
    return _parse_aware(payload.get("built_at"))


def payload_age_seconds(payload: dict | None, *, now: datetime) -> float | None:
    """Seconds since the last fill ATTEMPT that wrote, or None when it will not say."""
    if not isinstance(payload, dict):
        return None
    stamp = _parse_aware(payload.get("attempted_at") or payload.get("built_at"))
    if stamp is None:
        return None
    return max(0.0, (now - stamp).total_seconds())


#: Key under `FuturesMarket.market_metadata` recording that this market has
#: produced a real venue history bank at least once.
#:
#: 🔴 WHY THIS ONE FACT LIVES IN POSTGRES AND THE BANK DOES NOT (#7736). The bank
#: is Redis-only, on an instance running `allkeys-lru` at a 100 MB cap, so it can
#: vanish with no notice — and it takes with it the only evidence it was ever
#: there. `payload_age_seconds` then answers None for two states the planner has
#: to treat OPPOSITELY: "this market never had venue history" (refuse — that is
#: #7351's own scope boundary) and "it had some and the cache evicted it"
#: (re-fetch — the recovery is otherwise lost for good). A marker kept beside the
#: thing it describes would only ever be evicted with it, which is the whole
#: reason this one is durable.
BANK_MARKER_KEY = "venue_history_bank"


def bank_marker(market: Any) -> dict | None:
    """This market's durable "it held a real bank once" stamp, or None.

    Defensive about the shape all the way down: the planner runs on a plain
    `SimpleNamespace` built in the route, so `market_metadata` may be absent,
    None, or (on a row written before this key existed) a dict without it.
    """
    metadata = getattr(market, "market_metadata", None)
    if not isinstance(metadata, dict):
        return None
    marker = metadata.get(BANK_MARKER_KEY)
    return marker if isinstance(marker, dict) else None


def market_had_bank(market: Any) -> bool:
    """True when this market is KNOWN to have produced venue history before."""
    return bank_marker(market) is not None


def payload_point_count(payload: dict | None) -> int:
    """How many venue observations this payload actually carries.

    The one predicate behind BOTH durable writes: #7736's marker and #7807's
    durable bank. An `empty` or `degraded` answer carries nothing, and neither
    write may be made on one — see :func:`build_bank_marker` for the marker's
    reasoning and `publish_durable_history` for the bank's, which is the same
    argument about a negative cache that cannot expire.
    """
    if not isinstance(payload, dict):
        return 0
    outcomes = payload.get("outcomes")
    if not isinstance(outcomes, dict):
        return 0
    return sum(
        len(entry.get("points") or [])
        for entry in outcomes.values()
        if isinstance(entry, dict)
    )


def build_bank_marker(payload: dict | None, *, now: datetime) -> dict | None:
    """The stamp to persist for `payload`, or None when it has not earned one.

    Only a payload that actually carries POINTS earns a marker. An `empty` or
    `degraded` answer is precisely the case the marker must not claim: stamping
    it would convert "the venue has nothing for this market" into a standing
    instruction to re-ask on every cold key, which is the negative cache
    (`REFRESH_AFTER_SECONDS`) spent backwards.
    """
    points = payload_point_count(payload)
    if points <= 0:
        return None
    outcomes = payload.get("outcomes") or {}
    return {
        "first_built_at": payload.get("built_at") or now.isoformat(),
        "points": int(points),
        "outcomes": len(outcomes),
    }


def _contract_matches(contract: Any, market: Any, outcome: Any) -> str | None:
    """None when the cached contract IS this outcome row's instrument; else why not."""
    if not isinstance(contract, dict):
        return "contract_missing"
    if contract.get("venue") != market.source:
        return "contract_venue_mismatch"
    external_id = (getattr(outcome, "external_id", None) or "").strip()
    if not external_id or contract.get("outcome_external_id") != external_id:
        return "contract_outcome_external_id_mismatch"
    if market.source == "kalshi":
        if contract.get("ticker") != external_id:
            return "contract_ticker_mismatch"
        return None
    if market.source == "polymarket":
        if contract.get("condition_id") != strip_polymarket_leg(external_id):
            return "contract_condition_mismatch"
        if not contract.get("token_id"):
            return "contract_token_missing"
        return None
    return "source_has_no_venue_history"


def parse_points(rows: Any, *, not_after: datetime | None) -> tuple[list[VenuePoint], str | None]:
    """Cached rows → points, or a refusal reason. ALL OR NOTHING per series.

    A series with one impossible point is not a series with one fewer point — it
    is a series something else wrote, and the rest of it is no more trustworthy
    than the point that gave it away. Refused whole.
    """
    if not isinstance(rows, list):
        return [], "points_not_a_list"
    points: list[VenuePoint] = []
    previous: datetime | None = None
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) < 2:
            return [], "point_malformed"
        stamp = _parse_aware(row[0])
        if stamp is None:
            return [], "timestamp_unparseable_or_naive"
        probability = _finite_prob(row[1])
        if probability is None:
            return [], "probability_out_of_range"
        if previous is not None and stamp <= previous:
            return [], "timestamps_not_strictly_ascending"
        if not_after is not None and stamp > not_after:
            return [], "timestamp_after_build"
        previous = stamp
        points.append(
            VenuePoint(
                observed_at=stamp,
                probability=probability,
                yes_bid=_opt_float(row[2]) if len(row) > 2 else None,
                yes_ask=_opt_float(row[3]) if len(row) > 3 else None,
                last_price=_opt_float(row[4]) if len(row) > 4 else None,
                tier=str(row[5]) if len(row) > 5 and row[5] is not None else "",
            )
        )
    return points, None


def validate_payload(
    payload: Any, market: Any, outcomes: Iterable[Any]
) -> tuple[dict[int, list[VenuePoint]], list[dict]]:
    """`({outcome_id: points}, refusals)` for the series THIS market may serve.

    `outcomes` is the reader's own CHARTED list — already past
    `drop_duplicate_legs` and the board's drops — so a duplicate Yes/No leg the
    reader refuses cannot come back through its cached history.
    """
    refusals: list[dict] = []
    if not isinstance(payload, dict):
        return {}, [{"scope": "payload", "reason": "payload_not_a_dict"}]
    if payload.get("schema") != SCHEMA or payload.get("version") != CACHE_VERSION:
        return {}, [{"scope": "payload", "reason": "schema_or_version_mismatch"}]
    if payload.get("scale") != SCALE:
        return {}, [{"scope": "payload", "reason": "scale_mismatch"}]
    if payload.get("market_id") != market.id:
        return {}, [{"scope": "payload", "reason": "market_id_mismatch"}]
    if payload.get("market_source") != market.source:
        return {}, [{"scope": "payload", "reason": "market_source_mismatch"}]
    if payload.get("market_external_id") != market.external_id:
        return {}, [{"scope": "payload", "reason": "market_external_id_mismatch"}]
    built_at = _parse_aware(payload.get("built_at"))
    if built_at is None:
        return {}, [{"scope": "payload", "reason": "built_at_unparseable"}]
    cached = payload.get("outcomes")
    if not isinstance(cached, dict):
        return {}, [{"scope": "payload", "reason": "outcomes_not_a_dict"}]

    own = {int(o.id): o for o in outcomes}
    accepted: dict[int, list[VenuePoint]] = {}
    for key, entry in cached.items():
        try:
            outcome_id = int(key)
        except (TypeError, ValueError):
            refusals.append({"scope": "outcome", "key": str(key)[:40], "reason": "outcome_key_not_an_id"})
            continue
        if not isinstance(entry, dict) or entry.get("outcome_id") != outcome_id:
            refusals.append({"scope": "outcome", "outcome_id": outcome_id, "reason": "entry_id_disagrees_with_key"})
            continue
        outcome = own.get(outcome_id)
        if outcome is None:
            # Not an error when the reader simply is not charting this outcome;
            # it IS the control that stops another market's outcome being served.
            refusals.append({"scope": "outcome", "outcome_id": outcome_id, "reason": "not_a_charted_outcome_of_this_market"})
            continue
        why = _contract_matches(entry.get("contract"), market, outcome)
        if why:
            refusals.append({"scope": "outcome", "outcome_id": outcome_id, "reason": why})
            continue
        points, why = parse_points(entry.get("points"), not_after=built_at + FUTURE_SKEW)
        if why:
            refusals.append({"scope": "outcome", "outcome_id": outcome_id, "reason": why})
            continue
        if points:
            accepted[outcome_id] = points
    return accepted, refusals


def merge_last_good(
    fresh: Sequence[VenuePoint], last_good: Sequence[VenuePoint]
) -> list[VenuePoint]:
    """Union two series of REAL observations of one contract; fresh wins a tie.

    A venue that purges (Kalshi market data goes at ~74–86 days, gotcha #35),
    errors or rate-limits answers with less than it said last time. Those older
    points were still observed; losing them to a bad afternoon would make the
    chart forget history it had already shown a reader.
    """
    by_ts: dict[datetime, VenuePoint] = {p.observed_at: p for p in last_good}
    for p in fresh:
        by_ts[p.observed_at] = p
    return [by_ts[ts] for ts in sorted(by_ts)]


# ---------------------------------------------------------------------------
# Reader-side selection
# ---------------------------------------------------------------------------


def unclaimed_instants(
    venue_times: Sequence[datetime],
    capture_times: Iterable[datetime],
    *,
    venue_tiers: Iterable[str | None] = (),
) -> set[datetime]:
    """The venue instants that say something our own captures did not.

    ONE LAYERING RULE IN THE CODEBASE: this is `futures_chart_series.layer_tiers`
    with the captures as the FIRST tier. The concept envelope layers the other
    way round (venue first, captures as last resort) because it rebuilds a whole
    blended line; the generic readers must not move a point they already serve,
    so here a capture always stands and the venue fills only the instants no
    capture claims. That is also what keeps a capture written AFTER the cache
    was built: it is a capture, and captures are never displaced.

    🔴 **A CAPTURE'S CLAIM IS SIZED BY THE TIER IT IS REFUSING, NOT BY ITS OWN
    SPACING (#7547).** `layer_tiers` defaults each tier's claim to half that
    tier's OWN median spacing, capped at 30 minutes. That default is right when
    tiers are comparable and catastrophic here, because our captures are the
    COARSE tier and the venue is the fine one. Measured on production
    2026-09-21 — 150 sampled open Kalshi futures legs, median gap taken PER
    SERIES and then across series — our capture cadence is **62.2 min**
    (p25 60.1, p75 120.2). Half of that is capped to 30 min, so every capture
    claims a 60-minute band and consecutive captures TILE WITH NO GAP: a
    minute-resolution venue tier has nowhere to land and the reader is served
    `points_served: 0` from a bank that was built, fetched and paid for. Nothing
    counts that loss — the points were never candidates, so they are not
    `unsupported_points_withheld` either.

    A capture exists here to veto a venue point that RESTATES IT, and against a
    1-minute tier that is ±30 s. So the cap handed down is the venue tier's own
    resolution rather than the default half-hour: it only ever narrows the claim
    to the grain actually being refused, and on a coarse venue tier it changes
    nothing (a 135-minute venue tier still caps at 30 min).

    🔴 **THE GRAIN IS TAKEN FROM WHAT THE FETCH DECLARED, NOT FROM THE GAPS IT
    OBSERVED.** Measuring it (:func:`claim_radius_seconds`) is wrong here for the
    same reason the 30-minute default is wrong, one layer down: **both venues emit
    a bucket only for a bucket with something to say.** A 1-minute Kalshi tier on
    a market that traded twice in two hours reports 124-minute spacing, so a
    measured radius comes back capped at the full 30 minutes — and every one of
    those sparse, real, hard-won minute observations is then refused by a capture
    20 minutes away. The bank is served empty again, by a different route, and a
    quiet market is exactly the market a venue fill exists to repair.

    So the cap is :func:`futures_chart_series.finest_declared_resolution_seconds`
    of the banked points' own tier labels, halved: `candle_calls` asked for
    `period_interval`, `clob_calls` asked for `fidelity`, and the fill stamps
    that onto each point. Halved, because a claim reaches both ways and two
    readings inside one bucket of each other are the duplicate this refuses — so
    a 1-minute tier claims ±30 s and a venue point 20 minutes from a capture
    survives, while a second reading 20 seconds away is still a duplicate.

    When NOTHING declares — a bank written before the labels existed, or the
    fill's unpaired-price fallback — the measurement is still the best available
    answer and is used unchanged. That is a narrowing of this function's reach,
    not a silent default: an undeclared grain is not evidence of a coarse one.

    The bank this reads is already compacted to
    :data:`futures_chart_series.TARGET_POINTS_PER_OUTCOME` (400) by
    `compact_by_band` before it is stored — measured on the largest production
    bank, `generic-history:108599`, whose busiest leg holds 392 points — so
    admitting minute resolution here cannot flood the serve path: the flood was
    already spent at bank time, by budget, keeping the biggest moves.
    """
    venue = sorted({ts for ts in venue_times if ts is not None})
    if not venue:
        return set()
    from app.utils.futures_chart_series import (
        MAX_CLAIM_RADIUS_SECONDS,
        claim_radius_seconds,
        finest_declared_resolution_seconds,
        layer_tiers,
    )

    captures = sorted({ts for ts in capture_times if ts is not None})
    # The values are irrelevant to the claim; the instants are what is layered.
    venue_tier = [(ts, 0.0) for ts in venue]
    declared = finest_declared_resolution_seconds(venue_tiers)
    if declared is not None:
        # NARROWS ONLY. The declared grain of the COARSE tiers is enormous — a
        # daily candle halves to twelve hours — and this cap governs what OUR
        # captures may claim, so an unclamped declaration would hand the tier of
        # last resort a twelve-hour veto and re-open the staleness
        # `MAX_CLAIM_RADIUS_SECONDS` exists to stop. The declaration may make the
        # claim finer than the default; it may never make it coarser.
        cap_s = min(declared / 2.0, float(MAX_CLAIM_RADIUS_SECONDS))
    else:
        cap_s = claim_radius_seconds(venue_tier)
    merged = layer_tiers(
        [[(ts, 0.0) for ts in captures], venue_tier],
        cap_s=cap_s,
    )
    capture_set = set(captures)
    return {ts for ts, _ in merged if ts not in capture_set}


#: How much coarser than the venue's fine tier our own captures must be spaced
#: before a chart that already clears the thin gate is worth one venue request.
#:
#: DERIVED, NOT PICKED. The tier a fill would fetch is ONE MINUTE
#: (`futures_chart_series.KALSHI_FINE_INTERVAL`), so an order of magnitude
#: coarser than that is a series the fetch can visibly improve. Ten minutes
#: therefore. What that admits and refuses, on the two cadences this codebase
#: actually writes: our hourly captures sit at 60× the fine interval and are
#: firmly IN; a live-polled market's 2-minute captures sit at 2× and are firmly
#: OUT, so the markets whose lines our own polls already draw honestly never
#: spend a venue request on getting denser.
COARSE_CAPTURE_MULTIPLE = 10

#: How much of the reader's window the fine tier must be able to cover before
#: coarseness is worth acting on.
#:
#: The fine tier reaches `FINE_TIER_HOURS` back and no further, so on a long
#: window a fill improves only the newest sliver of a line the reader sees
#: compacted to ~80 points — real cost, invisible benefit. At half the window or
#: better, most of what is on screen improves. This is what keeps the trigger off
#: the long bands: 1D (24h) and 1W (168h) qualify against a 144h fine tier, 1M
#: (720h) and ALL do not.
COARSE_TRIGGER_MIN_WINDOW_COVERAGE = 0.5


def captures_are_coarse(
    capture_times_by_line: Iterable[Sequence[datetime]],
    *,
    window_hours: float | None,
    fine_tier_hours: float | None = None,
) -> bool:
    """Is this chart DENSE BUT COARSE — the state the thin gate cannot see?

    `plan_on_demand_fill`'s `chart_is_thin` asks how MANY points a window holds,
    and refuses a fill when there are plenty. #7547 is the measurement showing
    that count and resolution are different questions: `futures_markets` 40533
    served ten of ten outcomes at 97 points each across a week — comfortably past
    the thin gate — with 0–2 one-cent moves and four lines dead flat, because
    every one of those points was an HOURLY capture of a market the venue had
    published 643 one-cent moves on. A chart can be full and still be wrong about
    the week, and a gate that counts rows can never tell.

    So this asks the other question: are our own captures spaced coarsely enough
    that the fine tier would say something they cannot? Two bounds, both of which
    have to hold, because widening what a fill can SEE is widening outbound venue
    traffic on a public GET:

      * the DENSEST line's median gap is at least `COARSE_CAPTURE_MULTIPLE` ×
        the fine interval. Densest — the smallest median gap — and not the
        average, because one abandoned outcome must not make a well-captured
        market look coarse. Median and not the mean, because a single overnight
        hole would otherwise speak for a line sampled every minute around it;
      * the fine tier can cover at least `COARSE_TRIGGER_MIN_WINDOW_COVERAGE` of
        the window that was asked for.

    🪤 PER LINE, NEVER POOLED. Ten outcomes captured once an hour produce a
    MERGED stream with a six-minute median gap, which reads as fine data and is
    not: it is ten coarse lines. That is the same row-versus-line confusion the
    thin gate's own comment warns about at the call site, and pooling here would
    reproduce it exactly — with the failure pointing the safe way for the venue
    and the wrong way for the reader, so nothing would ever look broken.

    :param capture_times_by_line: one sequence of capture instants PER OUTCOME.
    :param window_hours: the window the reader asked for.
    :param fine_tier_hours: reach of the fine tier; defaults to the shipped one.
    """
    if not window_hours or window_hours <= 0:
        return False

    from app.utils.futures_chart_series import (
        FINE_TIER_HOURS,
        KALSHI_FINE_INTERVAL,
    )

    reach = FINE_TIER_HOURS if fine_tier_hours is None else fine_tier_hours
    if not reach or reach <= 0:
        return False
    if (reach / window_hours) < COARSE_TRIGGER_MIN_WINDOW_COVERAGE:
        return False

    coarse_at = KALSHI_FINE_INTERVAL * 60 * COARSE_CAPTURE_MULTIPLE
    densest: Optional[float] = None
    for times in capture_times_by_line:
        stamps = sorted({ts for ts in (times or ()) if ts is not None})
        if len(stamps) < 2:
            # One point is not a spacing. A line this sparse is the THIN gate's
            # case, and answering "coarse" for it here would let this predicate
            # quietly become a second, looser thin gate.
            continue
        gaps = sorted(
            (stamps[i + 1] - stamps[i]).total_seconds() for i in range(len(stamps) - 1)
        )
        median = gaps[len(gaps) // 2]
        if densest is None or median < densest:
            densest = median

    if densest is None:
        return False
    return densest >= coarse_at


def captures_cover_cell(
    instants: Iterable[datetime],
    *,
    cell_start: datetime,
    cell_end: datetime,
) -> bool:
    """Do our own captures already draw this chart cell, end to end?

    `/probability-timeline` keeps one median per (outcome, bucket) and refuses
    the venue's minutes in a cell our polls already fill. It used to call a cell
    filled when it held TWO capture instants — a proxy for "the two-minute live
    poll reached it". #7547 measured the proxy failing on the ordinary
    pre-kickoff cadence: 61097129 *over 9.5*, 2026-09-18T20Z, captures at 20:20
    and 20:48 and seventeen venue minutes between 20:07 and 20:55 — the web drew
    the .425 trough and the .435 peak, the phone drew one .43. Two readings do
    not fill an hour.

    So the question is COVERAGE, not count: is there any stretch of the cell —
    the head before the first capture and the tail after the last included — at
    least `COARSE_CAPTURE_MULTIPLE` × the fine interval long with no capture in
    it? That is the same line `captures_are_coarse` draws between a live-polled
    line (two minutes, firmly covered) and an hourly one (firmly not), so the
    route has one definition of "our captures are fine", not two.

    🪤 A SPACING STATISTIC IS NOT COVERAGE. The median gap between captures —
    the first rule proposed for this — reads 20:00 and 20:02 as two-minute data
    and fences the fifty-eight minutes after them. Only the widest uncovered
    stretch answers "is any of this cell unobserved".

    NEVER LOOSER THAN THE COUNT IT REPLACES. A cell with fewer than two instants
    is never covered here, whatever its width: one capture in the middle of a
    fifteen-minute in-play cell would otherwise newly FENCE venue minutes the
    route admits today. This predicate only ever releases cells the old count
    fenced; it never fences a cell the old count released.

    `cell_start`/`cell_end` are the part of the bucket the reader's window can
    see — clamp the bucket to the window's start and to `now` before calling, or
    a cell straddling the edge reads a stretch nobody could have captured as a
    hole.
    """
    from app.utils.futures_chart_series import KALSHI_FINE_INTERVAL

    stamps = sorted({ts for ts in instants if ts is not None})
    if len(stamps) < 2:
        return False
    hole_at = KALSHI_FINE_INTERVAL * 60 * COARSE_CAPTURE_MULTIPLE
    edges = [cell_start, *stamps, cell_end]
    widest = max(
        (edges[i + 1] - edges[i]).total_seconds() for i in range(len(edges) - 1)
    )
    return widest < hole_at


def as_snapshot_rows(
    outcome_id: int, bookmaker: str, points: Iterable[VenuePoint]
) -> list[VenueSnapshotRow]:
    return [
        VenueSnapshotRow(
            outcome_id=int(outcome_id),
            captured_at=p.observed_at,
            probability=p.probability,
            bookmaker=bookmaker,
            yes_bid=p.yes_bid,
            yes_ask=p.yes_ask,
            last_price=p.last_price,
            tier=p.tier,
        )
        for p in points
    ]
