# OddsTracker Game Excitement Index (GEI) - Technical Proposal

## Executive Summary

This document proposes a proprietary **Game Excitement Index (GEI)** for OddsTracker that measures how exciting a sporting event was based on odds movement data. Unlike traditional approaches that require play-by-play data, our GEI is derived entirely from betting market signals, making it applicable across all sports we track.

The final score is a **1-100 percentile ranking** computed both within-sport and cross-sport, allowing users to see "this was the 95th percentile most exciting NBA game this season" or "this was the 87th percentile most exciting game across all sports today."

---

## Research Foundation

### Luke Benz's GEI
**Formula**: `GEI = (2400/t) × Σ|pᵢ - pᵢ₋₁|`

The sum of absolute win probability changes, normalized by game length. A GEI of 5 means win probability changed by 500% total. Distribution is right-skewed (gamma-like), with mean ~3.6 and 99th percentile at 10.

**Limitation for us**: Requires play-by-play win probability at each play.

### FiveThirtyEight's NBA Excitement Index
Average change in win probability per basket, **weighted by time remaining** (late-game swings matter more). Adds bonuses for:
- Overtime periods
- Time spent with an upset brewing (weighted by upset magnitude)

**Limitation for us**: Requires basket-by-basket data.

### Academic Research (Stern 2006, Csató 2022)
- Excitement = variability in win expectancy as game progresses
- Score drift from expected values indicates unexpected developments
- Pre-game expectations from betting markets enable "expected excitement" calculation

**Opportunity for us**: We have pre-game expectations and can compare to in-game movement.

---

## Our Constraints & Opportunities

### What We DON'T Have
- Play-by-play events (touchdowns, baskets, goals)
- Exact game end time (only when odds markets close)
- In-game clock/period information
- Reason for odds movement (injury, score, momentum)

### What We DO Have
- Pre-game odds (opening lines) - **our baseline expectation**
- Time-series of odds snapshots throughout the game (~32s intervals when live)
- Multiple bookmakers (consensus reduces noise)
- Spread data (expected margin)
- Over/under data (expected total points)
- Implied scores derived from spread + total
- Final status (when markets close)

### Our Unique Advantages
1. **Pre-game baseline**: We know what was "expected" before tipoff
2. **Cross-bookmaker consensus**: Filtering noise from individual book movements
3. **Spread + Total decomposition**: We can track both "who's winning" and "how much scoring"
4. **Universal applicability**: Works for any sport with h2h/spread/totals markets

---

## Proposed OddsTracker GEI Formula

### Component 1: Win Probability Volatility (WPV) — 40% weight

The classic GEI component: how much did win probability swing during the game?

```python
def calculate_wpv(snapshots: list[OddsSnapshot]) -> float:
    """
    Sum of significant win probability changes, normalized.

    We use the CONSENSUS probability (median across bookmakers at each timestamp)
    to filter out noise from individual book movements.
    """
    if len(snapshots) < 2:
        return 0.0

    # Group snapshots by timestamp, take median probability
    consensus_probs = get_consensus_probabilities(snapshots)

    # Sum absolute changes, but only count changes > 2% (noise filter)
    total_swing = 0.0
    NOISE_THRESHOLD = 0.02  # 2% minimum swing to count

    for i in range(1, len(consensus_probs)):
        change = abs(consensus_probs[i] - consensus_probs[i-1])
        if change >= NOISE_THRESHOLD:
            total_swing += change

    # Normalize by expected game length (not actual, since we don't know exact end)
    # Use sport-specific expected durations
    return total_swing
```

**Example**: If probability went 50% → 65% → 45% → 60% → 52%, the total swing = 15 + 20 + 15 + 8 = 58%, WPV = 0.58

### Component 2: Late-Game Uncertainty (LGU) — 25% weight

Games that are close near the end are more exciting. We weight uncertainty by proximity to market close.

```python
def calculate_lgu(snapshots: list[OddsSnapshot], game_start: datetime, market_close: datetime) -> float:
    """
    Weighted average of how close the game was, with exponential weight toward end.

    "Closeness" = 1 - |home_prob - 0.5| * 2  (peaks at 50/50, zero at 100/0)
    """
    if not snapshots:
        return 0.0

    total_duration = (market_close - game_start).total_seconds()
    if total_duration <= 0:
        return 0.0

    weighted_closeness = 0.0
    total_weight = 0.0

    for snap in snapshots:
        if snap.captured_at < game_start:
            continue

        # How far through the game (0 = start, 1 = end)
        progress = (snap.captured_at - game_start).total_seconds() / total_duration
        progress = min(1.0, max(0.0, progress))

        # Exponential weight: e^(2*progress) gives ~7x weight at end vs start
        weight = math.exp(2 * progress)

        # Closeness: 1.0 at 50/50, 0.0 at 100/0
        prob = snap.home_win_probability or 0.5
        closeness = 1 - abs(prob - 0.5) * 2

        weighted_closeness += closeness * weight
        total_weight += weight

    return weighted_closeness / total_weight if total_weight > 0 else 0.0
```

**Example**: A game that's 70/30 for 3 quarters then becomes 52/48 in the 4th has high LGU because the close portion is weighted heavily.

### Component 3: Expectation Deviation (ED) — 20% weight

How much did the game deviate from pre-game expectations? This captures "unexpected blowouts turned close" and "expected blowouts that actually happened."

```python
def calculate_expectation_deviation(
    opening_spread: float,
    opening_total: float,
    closing_spread: float,
    closing_total: float,
    opening_prob: float,
    closing_prob: float,
) -> float:
    """
    Measure how much the game deviated from pre-game expectations.

    Components:
    1. Spread drift: |closing_spread - opening_spread|
    2. Total drift: |closing_total - opening_total|
    3. Probability flip: Did favorite change? How much did probability shift?
    """
    # Spread drift (normalized by typical spread range ~15 points)
    spread_drift = abs(closing_spread - opening_spread) / 15.0 if opening_spread else 0

    # Total drift (normalized by typical total ~200 for NBA, sport-specific)
    total_drift = abs(closing_total - opening_total) / opening_total if opening_total else 0

    # Probability shift (0-1 scale)
    prob_shift = abs(closing_prob - opening_prob)

    # Favorite flip bonus (if the favorite changed during the game)
    favorite_flipped = (opening_prob > 0.5) != (closing_prob > 0.5)
    flip_bonus = 0.3 if favorite_flipped else 0.0

    # Combined score (max 1.0 before flip bonus)
    deviation = min(1.0, spread_drift * 0.3 + total_drift * 0.3 + prob_shift * 0.4) + flip_bonus

    return min(1.0, deviation)
```

**Example**: If Lakers opened as -7 favorites (60% win prob) but ended up losing (0% win prob), the ED would be very high due to the probability shift and favorite flip.

### Component 4: Comeback Factor (CF) — 15% weight

Did a team overcome a significant deficit? This captures the narrative excitement of comebacks.

```python
def calculate_comeback_factor(snapshots: list[OddsSnapshot]) -> float:
    """
    Measure the largest comeback during the game.

    A "comeback" is when a team goes from significantly unfavored to winning.
    """
    if len(snapshots) < 2:
        return 0.0

    probs = [s.home_win_probability for s in snapshots if s.home_win_probability]
    if not probs:
        return 0.0

    # Track the largest swing in each direction
    max_home_comeback = 0.0  # Home was losing badly, then won
    max_away_comeback = 0.0  # Away was losing badly, then won

    min_home_prob = min(probs)  # Home team's worst moment
    max_home_prob = max(probs)  # Home team's best moment

    final_prob = probs[-1]

    # If home won (final prob > 0.5), comeback = how far they came from their lowest
    if final_prob > 0.5:
        # They needed to be below 50% at some point for it to be a comeback
        if min_home_prob < 0.5:
            max_home_comeback = final_prob - min_home_prob

    # If away won (final prob < 0.5), their comeback = home's best - final
    if final_prob < 0.5:
        if max_home_prob > 0.5:
            max_away_comeback = max_home_prob - final_prob

    # Normalize: a 40% swing (from 30% to 70%) is a big comeback
    comeback = max(max_home_comeback, max_away_comeback)
    return min(1.0, comeback / 0.4)  # 40% swing = max score
```

**Example**: Team goes from 25% to 65% win probability = 40% swing = CF of 1.0

---

## Combined GEI Formula

```python
def calculate_raw_gei(
    snapshots: list[OddsSnapshot],
    opening_odds: OddsSnapshot,
    game_start: datetime,
    market_close: datetime,
    sport_key: str,
) -> float:
    """
    Calculate raw Game Excitement Index (unbounded, sport-specific scale).

    This raw score will later be converted to percentile.
    """
    # Get live snapshots only (after game start)
    live_snapshots = [s for s in snapshots if s.captured_at >= game_start]

    if len(live_snapshots) < 3:
        return 0.0  # Not enough data

    # Component 1: Win Probability Volatility (40%)
    wpv = calculate_wpv(live_snapshots)

    # Component 2: Late-Game Uncertainty (25%)
    lgu = calculate_lgu(live_snapshots, game_start, market_close)

    # Component 3: Expectation Deviation (20%)
    closing = live_snapshots[-1]
    ed = calculate_expectation_deviation(
        opening_spread=opening_odds.home_spread,
        opening_total=opening_odds.over_under,
        closing_spread=closing.home_spread,
        closing_total=closing.over_under,
        opening_prob=opening_odds.home_win_probability,
        closing_prob=closing.home_win_probability,
    )

    # Component 4: Comeback Factor (15%)
    cf = calculate_comeback_factor(live_snapshots)

    # Weighted combination
    raw_gei = (
        wpv * 0.40 +
        lgu * 0.25 +
        ed * 0.20 +
        cf * 0.15
    )

    # Apply sport-specific multiplier for cross-sport comparability
    # (Some sports naturally have more volatility)
    sport_multiplier = get_sport_volatility_multiplier(sport_key)

    return raw_gei * sport_multiplier


def get_sport_volatility_multiplier(sport_key: str) -> float:
    """
    Normalize volatility across sports.

    Basketball has more scoring = more volatility.
    Baseball has less scoring = less volatility.

    These multipliers bring different sports to comparable scales.
    """
    multipliers = {
        'basketball_nba': 1.0,      # Baseline
        'basketball_ncaab': 1.0,
        'basketball_wncaab': 1.0,
        'americanfootball_nfl': 1.2,  # Fewer scores, each matters more
        'americanfootball_ncaaf': 1.2,
        'baseball_mlb': 1.5,        # Low-scoring, swings are dramatic
        'icehockey_nhl': 1.3,       # Low-scoring
        'mma_mixed_martial_arts': 0.9,  # High natural volatility
        'tennis_*': 1.1,            # Set-based scoring
    }

    for prefix, mult in multipliers.items():
        if sport_key.startswith(prefix.replace('_*', '')):
            return mult

    return 1.0  # Default
```

---

## Percentile Conversion

### Storage Strategy

```sql
-- Store raw GEI for every completed event
ALTER TABLE events ADD COLUMN raw_gei DECIMAL(6,4);
ALTER TABLE events ADD COLUMN gei_computed_at TIMESTAMP WITH TIME ZONE;

-- Percentile lookup tables (recomputed daily)
CREATE TABLE gei_percentiles (
    id SERIAL PRIMARY KEY,
    scope VARCHAR(50) NOT NULL,        -- 'global', 'basketball_nba', etc.
    percentile INTEGER NOT NULL,        -- 1-100
    raw_gei_threshold DECIMAL(6,4),     -- Raw GEI value at this percentile
    sample_size INTEGER,                -- How many events in this scope
    computed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(scope, percentile)
);
```

### Computing Percentiles

```python
async def compute_gei_percentiles(session: AsyncSession):
    """
    Recompute percentile thresholds for all scopes.

    Run daily (or after significant new data).
    """
    # Get all completed events with raw GEI
    result = await session.execute(
        select(Event.raw_gei, Sport.key)
        .join(Sport)
        .where(
            Event.status == 'completed',
            Event.raw_gei.isnot(None),
        )
    )
    events = result.all()

    if not events:
        return

    # Group by sport
    by_sport = defaultdict(list)
    all_geis = []

    for raw_gei, sport_key in events:
        by_sport[sport_key].append(raw_gei)
        all_geis.append(raw_gei)

    # Compute global percentiles
    await _store_percentiles(session, 'global', all_geis)

    # Compute per-sport percentiles
    for sport_key, geis in by_sport.items():
        if len(geis) >= 30:  # Minimum sample size
            await _store_percentiles(session, sport_key, geis)


async def _store_percentiles(session: AsyncSession, scope: str, values: list[float]):
    """Store percentile thresholds for a scope."""
    import numpy as np

    values = sorted(values)
    sample_size = len(values)

    for p in range(1, 101):
        threshold = np.percentile(values, p)

        stmt = insert(GEIPercentile).values(
            scope=scope,
            percentile=p,
            raw_gei_threshold=threshold,
            sample_size=sample_size,
        ).on_conflict_do_update(
            index_elements=['scope', 'percentile'],
            set_={
                'raw_gei_threshold': threshold,
                'sample_size': sample_size,
                'computed_at': func.now(),
            }
        )
        await session.execute(stmt)


def get_gei_percentile(raw_gei: float, scope: str, percentile_table: dict) -> int:
    """
    Convert raw GEI to percentile (1-100).

    Returns the percentile this raw GEI falls into.
    """
    thresholds = percentile_table.get(scope, percentile_table.get('global', {}))

    for p in range(100, 0, -1):
        if raw_gei >= thresholds.get(p, 0):
            return p

    return 1
```

---

## API Response Format

### Event Detail Endpoint

```json
{
  "id": 12345,
  "home_team": "Los Angeles Lakers",
  "away_team": "Boston Celtics",
  "status": "completed",
  "excitement": {
    "raw_gei": 0.847,
    "percentile_global": 92,
    "percentile_sport": 88,
    "sport_key": "basketball_nba",
    "label": "Highly Exciting",
    "components": {
      "win_probability_volatility": 0.72,
      "late_game_uncertainty": 0.91,
      "expectation_deviation": 0.65,
      "comeback_factor": 0.45
    }
  }
}
```

### Events List (Highlights)

```json
{
  "highlights": [
    {
      "id": 12345,
      "home_team": "Lakers",
      "away_team": "Celtics",
      "gei_percentile": 92,
      "gei_label": "92nd percentile",
      "status": "completed"
    }
  ],
  "filters": {
    "scope": "basketball_nba",
    "min_percentile": 80
  }
}
```

---

## Labeling System

```python
def get_gei_label(percentile: int) -> str:
    """Human-readable excitement label."""
    if percentile >= 95:
        return "Instant Classic"
    elif percentile >= 90:
        return "Highly Exciting"
    elif percentile >= 75:
        return "Exciting"
    elif percentile >= 50:
        return "Average"
    elif percentile >= 25:
        return "Below Average"
    else:
        return "Low Excitement"
```

---

## Noise Filtering Strategies

### 1. Consensus Probability
Instead of tracking individual bookmaker movements, we use the **median** probability across all bookmakers at each timestamp. This filters out:
- Book-specific adjustments
- Liability balancing moves
- Delayed updates from slower books

### 2. Minimum Change Threshold
We only count probability swings ≥ 2%. This filters out:
- Vig adjustments
- Minor line movements
- Floating point noise

### 3. Time-Bucketing
We aggregate snapshots into 1-minute buckets for WPV calculation. This prevents:
- Over-counting rapid oscillations
- Artificial inflation from high-frequency polling

```python
def bucket_snapshots(snapshots: list, bucket_minutes: int = 1) -> list:
    """Group snapshots into time buckets, taking the last snapshot in each bucket."""
    buckets = defaultdict(list)

    for snap in snapshots:
        bucket_key = snap.captured_at.replace(second=0, microsecond=0)
        # Round down to bucket
        bucket_key = bucket_key.replace(minute=(bucket_key.minute // bucket_minutes) * bucket_minutes)
        buckets[bucket_key].append(snap)

    # Take last snapshot in each bucket
    return [max(snaps, key=lambda s: s.captured_at) for snaps in sorted(buckets.values())]
```

---

## Handling Edge Cases

### 1. Overtime Games
Overtime naturally extends the game, adding more opportunities for swings. We handle this by:
- **Not penalizing**: Don't normalize by actual game length
- **Bonus multiplier**: Games that go to overtime get a 1.15x multiplier on raw GEI

```python
def detect_overtime(game_start: datetime, market_close: datetime, sport_key: str) -> bool:
    """Detect if game likely went to overtime based on duration."""
    duration_hours = (market_close - game_start).total_seconds() / 3600

    # Expected regulation durations (hours)
    expected = {
        'basketball_nba': 2.5,
        'basketball_ncaab': 2.25,
        'americanfootball_nfl': 3.25,
        'icehockey_nhl': 2.5,
    }

    expected_hours = expected.get(sport_key, 2.5)
    return duration_hours > expected_hours * 1.15  # 15% buffer
```

### 2. Blowouts
Games where one team dominates will have:
- Low WPV (probability stays stable)
- Low LGU (never close at end)
- Potentially high ED (if unexpected)
- Low CF (no comeback)

This is correct behavior—blowouts are typically not exciting unless unexpected.

### 3. Insufficient Data
If we have fewer than 3 live snapshots, we cannot compute GEI. These events get `null` for GEI.

### 4. Market Closures
Sometimes markets close early (technical issues, delayed games). We use the last known snapshot as "closing" and note reduced confidence.

---

## Implementation Phases

### Phase 1: Core Calculation (Week 1)
- [ ] Implement `calculate_raw_gei()` and all component functions
- [ ] Add `raw_gei` column to events table
- [ ] Create Celery task to compute GEI for completed events
- [ ] Backfill GEI for historical completed events

### Phase 2: Percentile System (Week 2)
- [ ] Create `gei_percentiles` table
- [ ] Implement daily percentile recomputation
- [ ] Add percentile lookup to event API responses
- [ ] Add sport-specific percentiles

### Phase 3: API & Frontend (Week 3)
- [ ] Add `excitement` object to event detail endpoint
- [ ] Add `gei_percentile` to events list endpoint
- [ ] Create "Highlights" section showing top-percentile events
- [ ] Add GEI badge/label to event cards

### Phase 4: Refinement (Week 4+)
- [ ] Tune component weights based on user feedback
- [ ] Tune sport multipliers based on data
- [ ] Add "Expected Excitement" for upcoming games (based on spread)
- [ ] A/B test different labeling schemes

---

## Pre-Game "Expected Excitement"

For upcoming games, we can predict expected excitement based on:

```python
def calculate_expected_excitement(
    home_prob: float,
    over_under: float,
    sport_key: str,
) -> float:
    """
    Predict how exciting a game is likely to be BEFORE it starts.

    Based on:
    1. Closeness of matchup (spreads near 0)
    2. Expected scoring (higher totals = more action)
    3. Historical volatility of teams/matchup (future enhancement)
    """
    # Closeness factor: peaks at 50/50
    closeness = 1 - abs(home_prob - 0.5) * 2

    # Scoring factor: normalized by sport average
    sport_avg_totals = {
        'basketball_nba': 225,
        'basketball_ncaab': 145,
        'americanfootball_nfl': 45,
        'baseball_mlb': 8.5,
        'icehockey_nhl': 6,
    }
    avg_total = sport_avg_totals.get(sport_key, 100)
    scoring_factor = min(1.0, over_under / avg_total) if over_under else 0.5

    # Combine: closeness matters more
    expected = closeness * 0.7 + scoring_factor * 0.3

    return expected
```

This can be used to:
- Rank upcoming games by "potential excitement"
- Help users discover close matchups
- Power a "Games to Watch" feature

---

## Success Metrics

### Validation Metrics
- **Correlation with manual ratings**: Survey users on game excitement, compare to GEI
- **Correlation with social buzz**: Do high-GEI games get more Twitter mentions?
- **Face validity**: Do "Instant Classic" games match consensus exciting games?

### Product Metrics
- **Highlights engagement**: Do users click on high-GEI games more?
- **Return visits**: Do users come back to check GEI after games?
- **Time on page**: Do high-GEI event pages get more engagement?

---

## Open Questions

1. **Component weights**: The 40/25/20/15 split is a starting hypothesis. Should we tune based on user feedback?

2. **Sport multipliers**: Should we derive these from data rather than setting manually?

3. **Minimum sample size**: What's the minimum number of games needed for reliable per-sport percentiles?

4. **Recency weighting**: Should recent games count more in percentile calculations?

5. **Team-specific factors**: Should rivalry games or playoff games get bonuses?

---

## References

- [Luke Benz - Game Excitement Index](https://lukebenz.com/post/gei/) - Original GEI methodology for college basketball
- [FiveThirtyEight - NBA Excitement Index](https://fivethirtyeight.com/features/the-nba-excitement-index/) - Time-weighted win probability approach
- [Yale Sports Analytics - GEI Part II](https://sports.sites.yale.edu/game-excitement-index-part-ii) - Extended GEI analysis
- [Stern 2006 - Football Excitement](https://www.stat.berkeley.edu/~aldous/157/Papers/excitement.pdf) - Academic foundation for expected vs actual excitement
- [InPredictable](https://www.inpredictable.com/2015/02/new-nba-features-at-fivethirtyeight.html) - Mike Beuoy's original NBA win probability work
