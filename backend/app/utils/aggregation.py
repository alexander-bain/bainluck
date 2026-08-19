"""
Multi-source probability aggregation engine.

Combines sportsbook consensus, prediction markets (Kalshi, Polymarket),
and statistical models (ESPN, Bain Luck Model) into a single "Bain Luck"
aggregate probability.

Algorithm: Weighted median with staleness decay and a per-source weight cap.
NO smoothing — see below.

A weighted median is outlier-resistant only under two conditions the plain
algorithm does not enforce, and #1829 is what it cost to learn that:

  1. No single source may hold enough weight to straddle the midpoint alone.
     `betting` held 42% and did exactly that, so the "median" returned the
     sportsbook's number verbatim. `MAX_SOURCE_WEIGHT_SHARE` enforces it now.
  2. A source that stopped reporting must lose influence. All three of this
     module's aggregation paths now decay stale readings — the two time-series
     paths by absolute age, the point-in-time hero by age RELATIVE to the
     freshest source on the same event.

This docstring used to claim "weighted median with staleness decay" while the
point-in-time hero — the function behind every card and every header —
implemented only the first half. The names differ by one letter
(`compute_aggregate_probability` vs `compute_aggregated_probability`), which is
how it went unnoticed. Read the constants block below before changing weights.

Source weights reflect depth and reliability:
  - Sportsbook consensus (3.0): Deep liquidity, 5-15 bookmakers
  - ESPN model (1.5): Play-by-play responsive, proprietary
  - Bain Luck Model (1.0): Statistical, principled, but simple
  - Kalshi (0.8): Regulated prediction market, thinner liquidity
  - Polymarket (0.8): Largest prediction market, good liquidity
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from app.utils.source_divergence import (
    SourceDivergence,
    assess_divergence,
)


# Base weights per source — higher = more influence on the aggregate
SOURCE_WEIGHTS: dict[str, float] = {
    "final_result": 5.0,   # Resolved game outcome from score (always correct)
    "betting": 3.0,        # Sportsbook consensus (5-15 books)
    "espn": 1.5,           # ESPN proprietary model
    "stat_model": 1.0,     # Bain Luck statistical model
    "kalshi": 0.8,         # Kalshi prediction market
    "polymarket": 0.8,     # Polymarket prediction market
    "mlb": 0.8,            # MLB Model (MLB Stats API)
}

# Staleness parameters (in seconds)
STALENESS_GRACE_PERIOD = 120   # 2 min: no penalty
STALENESS_DECAY_WINDOW = 180   # Next 3 min: linear decay to 0
MAX_STALENESS = STALENESS_GRACE_PERIOD + STALENESS_DECAY_WINDOW  # 5 min: fully stale

# ── #1829: RECENCY DECAY + WEIGHT CAP (Alex ruling 2026-08-13) ───────────────
#
# The specimen. Red Sox @ Blue Jays, event 15192596, top of the 9th, Toronto
# trailing 0-5 (final 0-7). The header read **87 - 13** while the chart's blend
# line sat at ~0. `win_probability_sources` held, home = Blue Jays:
#
#     mlb 0.001 (w 0.8) · espn 0.008 (w 1.5) · stat_model 0.001 (w 1.0)
#     betting 0.1347 (w 3.0) · kalshi 0.565 (w 0.8)
#
# Sorted, the cumulative weight crosses the 3.55 midpoint INSIDE betting's own
# 3.0 mass, so the weighted median returned `0.1347` verbatim. #240 Item 1
# switched this function mean -> median precisely to stop a stale sportsbook
# dragging the hero; it did not stop it, it made the hero EQUAL to it.
#
# Two independent faults, and Alex ruled both:
#
#   1. RECENCY. `betting` was ~17-20 minutes stale at that moment and nothing
#      could express it. Measured from `odds_snapshots`: every bookmaker had
#      PULLED the moneyline by 21:08 UTC (the game was out of reach), so
#      `_process_event_odds` collected an empty `all_home_probs` and simply
#      stopped rewriting the key — the last write was an unweighted mean over
#      the one book still quoting. mlb/espn/stat_model were seconds fresh and
#      all three said ~0. They were out-voted by a frozen number.
#
#   2. SHARE. `betting` alone held 42% of total weight (3.0 / 7.1). A weighted
#      median is outlier-resistant only when no single source can straddle the
#      midpoint by itself. This one could.
#
# THE DECAY IS RELATIVE, NOT ABSOLUTE, and that is the whole safety argument.
# Each source is aged against the FRESHEST stamped source on the same event,
# never against the wall clock. Consequences, all of them load-bearing:
#
#   - An event whose sources are ALL an hour old is unchanged. Uniform age is
#     not staleness; it is the polling cadence. Only DISAGREEMENT in age is.
#   - There is no clock in the computation at all, so gotcha #44 cannot apply:
#     no anchor to drift, no test that reads differently at 4pm.
#   - The freshest source always has multiplier 1.0, so the weights can never
#     all collapse to zero and the blend can never become undefined.
#
# MONOTONE. An entry with no `updated_at` keeps FULL weight, so an event whose
# JSONB has not yet been re-written by a stamping writer computes bit-for-bit
# what it computes today. The decay half is therefore inert until the writers
# deploy and re-poll; the cap half is live immediately. Said plainly because
# the two halves have different blast radii and only one is measurable before
# the deploy.
HERO_RELATIVE_GRACE_SECONDS = 600.0      # 10 min of age difference: no penalty
HERO_RELATIVE_DECAY_SECONDS = 1800.0     # next 30 min: linear decay to the floor
HERO_MIN_STALENESS_MULTIPLIER = 0.1      # a floor, not zero — see below

# The floor exists so decay DEMOTES a source instead of deleting it. A source
# at 10% of its base weight cannot carry a median, but it still breaks ties and
# still shows up in the envelope check — and "we stopped hearing from Kalshi"
# is not the same claim as "Kalshi does not exist".

MAX_SOURCE_WEIGHT_SHARE = 0.35           # no single source may exceed this share
MIN_SOURCES_FOR_WEIGHT_CAP = 3

# WHY 0.35, DERIVED FROM THE SPECIMEN RATHER THAN PICKED. On event 15192596 the
# sources below `betting` carry a cumulative 3.3 and the four non-betting
# sources carry 4.1, so `betting` stops straddling the midpoint exactly when
#
#     3.3 >= (4.1 + B) / 2   ->   B <= 2.5   ->   share <= 2.5/6.6 = 0.379
#
# A cap of 0.40 therefore does NOT fix Alex's header — it leaves the hero at
# 0.1347 — which is worth knowing before anyone "rounds it up to a nicer
# number". 0.35 clears the bound with margin and sits just above the 1/3 that
# uniform weighting would give three sources.

# WHY THE CAP IS GATED ON THREE SOURCES, measured rather than chosen. With two
# sources a weighted median just returns whichever side holds half the weight,
# so ANY cap below 0.5 hands every two-source event to the lighter source. On
# 2026-08-13 that population was 95 scheduled + 125 recently-completed + 6 live
# events, virtually all of them `betting` + one model: capping there would flip
# hundreds of heroes away from the sportsbook with no evidence that the model
# is better, which is a different product decision than the one Alex ruled.
# With two sources there is no outlier to resist — there is a disagreement, and
# the weight table IS the tiebreak. The cap is what makes a MEDIAN honest, and
# a median needs three points before the word means anything.

# `final_result` is the graded outcome, not a forecast. It is exempt from both
# mechanisms: it cannot go stale, and capping its share would let live-market
# noise out-vote the actual result on a settled game — the exact inversion
# "settled means settled" forbids.
_UNCAPPED_SOURCES = frozenset({"final_result"})

# NO SMOOTHING (standing ruling #4, UX-P003). The blend line the chart draws used
# to run an α=0.3 exponential moving average over the per-bucket weighted median.
# That is smoothing, and smoothing HIDES real movement — the thing the chart exists
# to show. It also silently de-synced the surfaces: because the EMA lags, the last
# point of `aggregate_line` (the chart's live edge, and the web hero's live source)
# drifted away from `compute_aggregate_probability()` (the Discover card and the
# backend `hero_probability`), so one game showed two different numbers on two
# screens. Measured on production 2026-08-05 (live MLB): Giants @ Rangers card 60%
# vs chart 78%, of which +14.5 pts was attributable to the EMA alone.
#
# Staleness decay below is deliberately KEPT: that is source *weighting* (how much
# a reading counts), not smoothing (blurring the output over time).


@dataclass
class TimestampedProb:
    """A probability reading at a point in time."""
    timestamp: datetime
    home_probability: float


@dataclass
class SourceReading:
    """Latest reading from a single source, with weight."""
    source: str
    probability: float
    weight: float
    stale_seconds: float


def _staleness_weight(stale_seconds: float) -> float:
    """
    Compute weight multiplier based on staleness.

    0-2 min: 1.0 (full weight)
    2-5 min: linear decay from 1.0 to 0.0
    5+ min:  0.0 (fully dropped)
    """
    if stale_seconds <= STALENESS_GRACE_PERIOD:
        return 1.0
    elif stale_seconds >= MAX_STALENESS:
        return 0.0
    else:
        elapsed_past_grace = stale_seconds - STALENESS_GRACE_PERIOD
        return max(0.0, 1.0 - elapsed_past_grace / STALENESS_DECAY_WINDOW)


def _coerce_timestamp(raw: Any) -> Optional[datetime]:
    """Read an ``updated_at`` out of a JSONB source entry, or give up quietly.

    Anything unparseable returns ``None``, which means "no timestamp", which
    means "full weight" — the monotone default. A malformed stamp must never
    raise and must never be worse for the reader than no stamp at all.
    """
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def parse_source_entry(raw: Any) -> tuple[Optional[float], Optional[datetime]]:
    """Split a ``win_probability_sources`` entry into (value, updated_at).

    The column holds BOTH shapes and always has (gotcha behind #1000): a bare
    float from the older writers, or ``{"value": x, "updated_at": "..."}`` from
    the stamping ones. Every reader of this column has to handle both; this is
    the one place that decides how.
    """
    if isinstance(raw, bool):
        return None, None
    if isinstance(raw, (int, float)):
        return float(raw), None
    if isinstance(raw, dict):
        value = raw.get("value")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None, None
        return float(value), _coerce_timestamp(raw.get("updated_at"))
    return None, None


def stamp_source_reading(
    sources: Optional[dict],
    source: str,
    value: float,
    now: Optional[datetime] = None,
) -> dict:
    """Write one source into ``win_probability_sources`` WITH its write time.

    Returns a new dict — callers pass the result straight into a Core
    ``update()`` (gotcha #4: ORM attribute assignment on this JSONB silently
    fails). Every other key is copied through untouched, in whatever shape it
    already had; this never rewrites a sibling.

    This is the writer half of #1829, and it is the ONLY thing that makes the
    hero's recency decay do anything. A source that does not come through here
    keeps full weight forever — correct as a default, and invisible as a bug,
    so if you add a seventh writer of this column, add it here too.
    """
    updated = dict(sources or {})
    stamp = now or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)

    # MERGE into an existing dict entry, never replace it. Entries in this
    # column carry sibling keys that nothing here knows about — the seeded
    # event fixture holds `{"value": x, "home_probability": x}`, and
    # `_apply_final_pm_win_prob`'s own suite pins a `weight` key as preserved.
    # The first draft assigned a fresh two-key dict and silently dropped all of
    # them. A writer whose job is to ADD a field must not be a writer that
    # deletes fields it does not recognise.
    existing = updated.get(source)
    entry = dict(existing) if isinstance(existing, dict) else {}
    entry["value"] = value
    entry["updated_at"] = stamp.isoformat()
    updated[source] = entry
    return updated


def wps_numeric_sql(source: str, column: str = "win_probability_sources") -> str:
    """SQL that reads one source's numeric probability out of the JSONB.

    The Python side has ``parse_source_entry``; this is the same decision for
    the SQL side, and it exists because the naive form is both obvious and
    wrong::

        (win_probability_sources->>'betting')::float

    ``->>`` on an OBJECT member returns the object's JSON *text*, and casting
    ``{"value": 0.1347, ...}`` to float raises — so a query written that way
    does not degrade, it dies, and a nearby ``IS NOT NULL`` guard does not save
    it. This mirrors the CASE that ``source_intelligence._BETTING_CTE`` already
    proved in production.

    ``source`` is interpolated, so it must be a literal from
    ``SOURCE_WEIGHTS`` — never user input. Enforced, not merely asked for.
    """
    if source not in SOURCE_WEIGHTS:
        raise ValueError(f"unknown win-prob source for SQL interpolation: {source!r}")
    return (
        f"CASE "
        f"WHEN jsonb_typeof({column}->'{source}') = 'number' "
        f"THEN ({column}->>'{source}')::float "
        f"WHEN jsonb_typeof({column}->'{source}') = 'object' "
        f"THEN ({column}->'{source}'->>'value')::float "
        f"END"
    )


def _relative_staleness_multiplier(relative_age_seconds: float) -> float:
    """Weight multiplier for a reading that is `relative_age` older than the
    freshest reading on the same event.

    0-10 min behind:   1.0
    10-40 min behind:  linear from 1.0 down to the floor
    40+ min behind:    the floor
    """
    if relative_age_seconds <= HERO_RELATIVE_GRACE_SECONDS:
        return 1.0
    past_grace = relative_age_seconds - HERO_RELATIVE_GRACE_SECONDS
    if past_grace >= HERO_RELATIVE_DECAY_SECONDS:
        return HERO_MIN_STALENESS_MULTIPLIER
    decayed = 1.0 - (past_grace / HERO_RELATIVE_DECAY_SECONDS)
    return max(HERO_MIN_STALENESS_MULTIPLIER, decayed)


def cap_weight_shares(
    weights: list[float],
    exempt: Optional[list[bool]] = None,
) -> list[float]:
    """Scale down any source holding more than ``MAX_SOURCE_WEIGHT_SHARE``.

    Below ``MIN_SOURCES_FOR_WEIGHT_CAP`` contributors this is the identity
    function — see the constant's note for why that gate is not a fudge.

    SOLVED, NOT ITERATED, and the first draft of this function is why that is
    written down. Capping the largest source lowers the TOTAL, which RAISES
    every other source's share — so "cap the biggest, repeat" oscillates toward
    the answer geometrically and needs ~30 passes to land. The draft bounded the
    loop at ``len(weights) + 2``, which is plenty for the common one-source-over
    case and silently insufficient the moment two sources are over: it returned
    weights whose largest share was 0.58 against a 0.35 cap, and returned them
    without complaint. That shape is not exotic — plain ``betting`` + ``espn`` +
    one market reaches it on the SECOND pass, because capping betting is what
    pushes espn over.

    The closed form. Sort the non-exempt weights descending and suppose the top
    ``k`` end up capped at a common value ``x`` while the rest keep theirs::

        T = k*x + tail + exempt          x = c*T
        =>  x = c * (tail + exempt) / (1 - c*k)

    ``k`` is the smallest value for which ``x`` lands between the k-th weight
    (which must actually be reduced) and the (k+1)-th (which must not need to
    be). At most ``floor(1/c)`` sources can exceed the cap at once — three
    sources cannot each hold 35% — so the search is short and always succeeds.
    """
    capped = [float(w) for w in weights]
    if exempt is None:
        exempt = [False] * len(capped)
    if sum(1 for w in capped if w > 0) < MIN_SOURCES_FOR_WEIGHT_CAP:
        return capped

    cappable = [i for i in range(len(capped)) if not exempt[i] and capped[i] > 0]
    if not cappable:
        return capped
    exempt_mass = sum(capped[i] for i in range(len(capped)) if i not in set(cappable))

    order = sorted(cappable, key=lambda i: capped[i], reverse=True)
    vals = [capped[i] for i in order]
    c = MAX_SOURCE_WEIGHT_SHARE

    # `k` runs to len(vals) INCLUSIVE — capping EVERY cappable source is a real
    # solution, and it is the only one when the exempt mass is what the cap has
    # to be taken against. A 20k-case fuzz found this: with one cappable source
    # and two exempt ones the loop simply never tried k=1 and returned the
    # weights untouched, cap violated, quietly.
    for k in range(len(vals) + 1):
        if c * k >= 1.0:
            break  # unreachable at c < 1/2 with the ordering guarantee above
        x = c * (sum(vals[k:]) + exempt_mass) / (1.0 - c * k)
        reduces_the_capped = k == 0 or x <= vals[k - 1] + 1e-12
        spares_the_rest = k >= len(vals) or x >= vals[k] - 1e-12
        if reduces_the_capped and spares_the_rest:
            for j in range(k):
                capped[order[j]] = x
            return capped
    return capped


def _weighted_median(values: list[float], weights: list[float]) -> float:
    """
    Compute weighted median.

    Sort values, accumulate weights, find the value at the 50th percentile
    of cumulative weight.
    """
    if not values:
        raise ValueError("Cannot compute weighted median of empty list")
    if len(values) == 1:
        return values[0]

    # Sort by value
    paired = sorted(zip(values, weights), key=lambda x: x[0])
    total_weight = sum(w for _, w in paired)
    if total_weight <= 0:
        # All weights are zero, fall back to simple median
        vals = [v for v, _ in paired]
        mid = len(vals) // 2
        return vals[mid]

    half = total_weight / 2.0
    cumulative = 0.0
    for value, weight in paired:
        cumulative += weight
        if cumulative >= half:
            return value

    # Shouldn't reach here, but return last value as fallback
    return paired[-1][0]


def compute_aggregated_probability(
    sources: dict[str, list[TimestampedProb]],
    bucket_seconds: int = 30,
    custom_weights: Optional[dict[str, float]] = None,
) -> list[TimestampedProb]:
    """
    Aggregate multiple probability sources into a single time series.

    For each time bucket:
    1. Find the latest reading from each source (carry-forward up to 5 min)
    2. Apply staleness-based weight decay
    3. Compute weighted median across all active sources

    No smoothing is applied (standing ruling #4) — each bucket is the honest
    weighted median of what the sources actually said in that bucket.

    Args:
        sources: Dict mapping source key → list of timestamped probabilities
        bucket_seconds: Time bucket size in seconds (default 30s)
        custom_weights: Override default source weights

    Returns:
        Aggregated time series of probabilities
    """
    weights = custom_weights or SOURCE_WEIGHTS

    if not sources:
        return []

    # Collect all timestamps across all sources to define bucket boundaries
    all_timestamps: set[float] = set()
    for source_points in sources.values():
        for point in source_points:
            ts = point.timestamp.timestamp()
            bucket_key = int(ts // bucket_seconds) * bucket_seconds
            all_timestamps.add(bucket_key)

    if not all_timestamps:
        return []

    sorted_buckets = sorted(all_timestamps)

    # Build per-source sorted lists for efficient carry-forward lookup
    source_sorted: dict[str, list[TimestampedProb]] = {}
    for source_key, points in sources.items():
        source_sorted[source_key] = sorted(points, key=lambda p: p.timestamp)

    # For each bucket, find latest reading per source
    aggregated: list[TimestampedProb] = []

    for bucket_ts in sorted_buckets:
        bucket_time = datetime.fromtimestamp(bucket_ts, tz=None)
        # Use timezone from the first source's first point
        for pts in sources.values():
            if pts:
                bucket_time = datetime.fromtimestamp(
                    bucket_ts, tz=pts[0].timestamp.tzinfo
                )
                break

        readings: list[SourceReading] = []

        for source_key, points in source_sorted.items():
            base_weight = weights.get(source_key, 0.5)  # Default weight for unknown sources

            # Find latest reading at or before this bucket
            latest: Optional[TimestampedProb] = None
            for point in points:
                if point.timestamp.timestamp() <= bucket_ts + bucket_seconds:
                    latest = point
                else:
                    break

            if latest is None:
                continue

            # Calculate staleness
            stale_seconds = bucket_ts - latest.timestamp.timestamp()
            if stale_seconds < 0:
                stale_seconds = 0

            # Apply staleness decay
            stale_mult = _staleness_weight(stale_seconds)
            effective_weight = base_weight * stale_mult

            if effective_weight > 0:
                readings.append(SourceReading(
                    source=source_key,
                    probability=latest.home_probability,
                    weight=effective_weight,
                    stale_seconds=stale_seconds,
                ))

        if not readings:
            continue

        # Compute weighted median. The #1829 share cap applies HERE TOO, and
        # that is deliberate: the hero and this series answer the same question,
        # so a cap on one and not the other is exactly the two-verdicts-for-one-
        # rule shape that produced the 87-13-header-vs-~0-chart contradiction in
        # the first place. This path already decays by absolute age (it has real
        # per-bucket timestamps), so it needs the cap and not the relative rule.
        values = [r.probability for r in readings]
        wts = cap_weight_shares(
            [r.weight for r in readings],
            exempt=[r.source in _UNCAPPED_SOURCES for r in readings],
        )
        raw_aggregate = _weighted_median(values, wts)

        # No smoothing (ruling #4): emit the bucket's honest weighted median.
        aggregated.append(TimestampedProb(
            timestamp=bucket_time,
            home_probability=round(raw_aggregate, 6),
        ))

    return aggregated


def compute_current_aggregate(
    source_readings: dict[str, tuple[float, datetime]],
    now: datetime,
    custom_weights: Optional[dict[str, float]] = None,
) -> Optional[float]:
    """
    Compute a single aggregate probability from current source readings.

    Simpler version of the full time-series aggregation, for use in
    real-time event serialization.

    Args:
        source_readings: Dict mapping source key → (probability, last_updated)
        now: Current time
        custom_weights: Override default source weights

    Returns:
        Aggregated probability (0-1) or None if no valid readings
    """
    weights = custom_weights or SOURCE_WEIGHTS

    values: list[float] = []
    wts: list[float] = []
    keys: list[str] = []

    for source_key, (probability, updated_at) in source_readings.items():
        base_weight = weights.get(source_key, 0.5)
        stale_seconds = (now - updated_at).total_seconds()

        stale_mult = _staleness_weight(max(0, stale_seconds))
        effective_weight = base_weight * stale_mult

        if effective_weight > 0:
            values.append(probability)
            wts.append(effective_weight)
            keys.append(source_key)

    if not values:
        return None

    # Same #1829 share cap as the other two blend paths — one rule, one verdict.
    wts = cap_weight_shares(wts, exempt=[k in _UNCAPPED_SOURCES for k in keys])
    return round(_weighted_median(values, wts), 6)


_EXCLUDE_WHEN_COMPLETED = {"kalshi", "polymarket"}


def effective_source_weights(
    event, event_status: Optional[str] = None
) -> tuple[list[str], list[float], list[float]]:
    """The readings and the weights the hero is ABOUT to use — decayed and capped.

    Extracted so the divergence gate and the flag that reports it read the same
    numbers the value is computed from. A detector that recomputes its own
    weights is a detector that can disagree with the thing it is watching.

    Returns ``(keys, values, weights)``, index-aligned; ``([], [], [])`` when
    tier 1 has nothing.
    """
    status = event_status or getattr(event, "status", None)
    is_finished = status in ("completed", "closed")

    wps = getattr(event, "win_probability_sources", None) or {}
    prob_readings: dict[str, float] = {}
    stamps: dict[str, datetime] = {}
    for k, v in wps.items():
        if k not in SOURCE_WEIGHTS:
            continue
        if is_finished and k in _EXCLUDE_WHEN_COMPLETED:
            continue
        value, updated_at = parse_source_entry(v)
        if value is None:
            continue
        prob_readings[k] = value
        if updated_at is not None:
            stamps[k] = updated_at

    if not prob_readings:
        return [], [], []

    values = list(prob_readings.values())
    keys = list(prob_readings.keys())
    weights = [SOURCE_WEIGHTS.get(src, 0.5) for src in keys]

    # Relative recency. The reference is the freshest stamp on the event,
    # never the wall clock: uniform age is cadence, not staleness, and a
    # clock-free rule cannot drift (gotcha #44).
    decay_stamps = {k: t for k, t in stamps.items() if k not in _UNCAPPED_SOURCES}
    if decay_stamps:
        freshest = max(decay_stamps.values())
        for i, src in enumerate(keys):
            stamp = decay_stamps.get(src)
            if stamp is None:
                continue  # unstamped keeps full weight — the monotone default
            relative_age = (freshest - stamp).total_seconds()
            if relative_age <= 0:
                continue
            weights[i] *= _relative_staleness_multiplier(relative_age)

    weights = cap_weight_shares(
        weights, exempt=[src in _UNCAPPED_SOURCES for src in keys]
    )
    return keys, values, weights


def assess_event_divergence(
    event, event_status: Optional[str] = None
) -> Optional[SourceDivergence]:
    """The flag half of the divergence gate (ruling (b)) — read-only.

    Returns a verdict when this event's hero rests on exactly two sources that
    disagree past `DIVERGENCE_SPREAD_THRESHOLD`. This is the hook a sentinel or
    an audit reads to route the pair to matching as a suspected mis-link; the
    aggregator itself only needs the value.

    On the live population read 2026-08-19 this fires on 4 of 76 two-source
    events; three of the four are one class (Polymarket at 0.07 against a
    sportsbook at 0.59-0.63).
    """
    keys, values, weights = effective_source_weights(event, event_status)
    if not keys:
        return None
    return assess_divergence(dict(zip(keys, values)), dict(zip(keys, weights)))


def compute_aggregate_probability(event, event_status: Optional[str] = None) -> Optional[float]:
    """Compute aggregate home win probability from all available sources.

    Uses SOURCE_WEIGHTS to produce a weighted average of all available
    probability readings on the event model.  Falls back through three
    tiers of decreasing richness.

    When event_status is "completed" or "closed", prediction market sources
    (Kalshi, Polymarket) are excluded — their prices go stale post-final
    and drag the aggregate away from the resolved sportsbook/ESPN values.

    Works on any object with win_probability_sources, espn_win_prob_home,
    and opening_home_probability attributes (typically an Event model).
    """
    # Tier 1: win_probability_sources JSONB (live games — multiple sources).
    # Readings, decay and cap all live in `effective_source_weights` so the
    # divergence gate below cannot drift from the value it is gating.
    keys, values, weights = effective_source_weights(event, event_status)

    if keys:
        # Weighted MEDIAN (not mean) — the same outlier-resistant method the
        # time-series blend (compute_aggregated_probability → the chart's
        # aggregate_line) uses. This is the module's stated design (see the
        # docstring): a single stale/lagged source cannot drag the aggregate.
        #
        # A weighted MEAN here let a stale sportsbook "betting" reading (weight
        # 3.0) that had not caught up to the live game state pull the hero toward
        # the pre-game number (~57%) while the chart's median-based blend line
        # read the live value (~20%) on the same screen — the 57%-hero vs
        # 20%-chart contradiction (#240 Item 1). Using the median here makes the
        # point-in-time hero match the chart's blend line: one number per
        # question.
        #
        # #1829 adds the two halves the median was always missing: RECENCY
        # DECAY (a source aged against the freshest stamped source on this same
        # event) and a SHARE CAP (no single source may straddle the midpoint by
        # itself). See the constants block for the specimen and the reasoning.
        # Both are no-ops on the shapes that dominate today — an event with no
        # stamps decays nothing, an event with fewer than three sources caps
        # nothing — so this is additive to a hero, not a replacement for one.
        #
        # THE DIVERGENCE GATE (ruling (b), cycle 99). Two sources 40+ points
        # apart cannot both be describing this game, so we render one source's
        # own number rather than let a statistic arbitrate a broken pair. See
        # `utils/source_divergence.py` for the measured threshold and for why
        # "primary" is the highest EFFECTIVE weight — a base-weight primary
        # would print the stale pregame line over a live blowout, which is #240
        # rebuilt. On the 2026-08-19 population this changes 0 of 76 displayed
        # heroes and flags 4; the value it protects is the invariant that a
        # rendered probability is always a number some source actually stated.
        divergence = assess_divergence(
            dict(zip(keys, values)), dict(zip(keys, weights))
        )
        if divergence is not None:
            return round(divergence.primary_value, 6)

        if any(w > 0 for w in weights):
            return round(_weighted_median(values, weights), 6)

    # Tier 2: ESPN win probability (live games, single source)
    espn_prob = getattr(event, "espn_win_prob_home", None)
    if espn_prob is not None:
        return round(float(espn_prob), 6)

    # Tier 3: Opening probability (Odds API sportsbook consensus)
    opening_prob = getattr(event, "opening_home_probability", None)
    if opening_prob is not None:
        return round(float(opening_prob), 6)

    return None
