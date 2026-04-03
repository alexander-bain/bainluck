# Ranking Improvement Plan

## Current State

The feed ranking system uses hand-tuned heuristic scoring:

```
score = Σ(hardcoded_weight × binary_flag) × personalization_multiplier
```

**`compute_highlight()` weights** (in `utils/highlights.py`):
- `live=30`, `close_matchup=25`, `very_close=10`, `favorite_switched=20`
- `major_probability_swing=15`, `starting_soon_3h=15`, `starting_soon_1h=10`
- `tier_1_league=20`, `tier_2_league=10`, `tier_3=-5`, `tier_4=-45`
- `championship=25`, `playoff=15`, `exhibition=-20`
- Level 2 (time-series): `high_volatility=10`, `lead_changes=8`, `recent_momentum=10`

**Personalization multipliers** (in `utils/personalization.py`):
- Team bonuses: follow=+0.8, local=+0.3, alma_mater=+0.3, rival_losing=+0.5
- Sport affinity: high=+0.5, low=-0.3, nah=-0.6
- Pinned=+0.3, roster_player=+0.4
- Clamped to [0.3, 3.0]

### Problems

1. **No learning** — weights are guesses, not learned from user behavior
2. **No behavioral signals** — GA4 tracks clicks/dwell but data doesn't feed back into ranking
3. **No cross-user signals** — no "trending now" or "people like you watched this"
4. **Context-blind** — same weights regardless of season timing, user history, concurrent games
5. **No stakes weighting** — a 50/50 game between 0.5% championship teams ranks same as 50/50 between 25% championship teams
6. **Binary features** — `is_live` is 0 or 1, but "live in overtime" is way more interesting than "live in Q1"

---

## Phase 1: Better Features (No ML, ~1-2 days)

Improve ranking by adding richer features to the existing scoring system. No new dependencies, no ML infrastructure.

### 1a. Futures Stake Weighting

**Idea**: Games involving high-championship-probability teams are more consequential and interesting.

**Implementation**:
- In `_score_events()` (feed.py), after computing `highlight_result`, query each team's highest championship futures probability
- Add a `stakes_bonus` to the highlight score:
  ```python
  # Max championship probability between both teams
  max_champ_prob = max(home_champ_prob or 0, away_champ_prob or 0)
  if max_champ_prob >= 0.15:      # Legit contender
      stakes_bonus = 15
  elif max_champ_prob >= 0.05:    # Fringe contender
      stakes_bonus = 8
  elif max_champ_prob >= 0.01:    # Long shot but not nothing
      stakes_bonus = 3
  ```
- Cache the team→championship probability lookup per feed request (one SQL query for all teams)
- This makes a Celtics vs Nuggets regular season game rank higher than Kings vs Wizards, even if both are 50/50

**Files**: `backend/app/routes/feed.py` (add `_get_championship_probabilities()` helper, use in `_score_events()`)

### 1b. Season Context Multiplier

**Idea**: The same game matters more as the season progresses. A 50/50 NBA game in March matters more than one in October.

**Implementation**:
- Add sport-specific season calendars (rough month ranges):
  ```python
  SEASON_CALENDARS = {
      "basketball_nba": {"start": 10, "end": 4, "playoffs_start": 4},
      "americanfootball_nfl": {"start": 9, "end": 1, "playoffs_start": 1},
      "baseball_mlb": {"start": 3, "end": 10, "playoffs_start": 10},
      # etc.
  }
  ```
- Compute `season_progress` (0.0 = opening day, 1.0 = playoffs start):
  ```python
  progress = months_elapsed / season_months
  season_multiplier = 0.8 + (0.4 * progress)  # 0.8x early → 1.2x late
  ```
- Apply as a multiplier to the base highlight score for the league tier component

**Files**: `backend/app/utils/highlights.py` (add `get_season_multiplier()`, use in `compute_highlight()`)

### 1c. Richer Live Game Features

**Idea**: "Live in overtime" is dramatically more interesting than "Live in Q1". Use game clock data we already have from ESPN.

**Implementation**:
- Replace the binary `live=30` with a gradient based on game progress:
  ```python
  if is_live:
      # Base live bonus
      live_bonus = 20
      # Late-game bonus (increases as game progresses)
      if period and total_periods:
          progress = min(period / total_periods, 1.0)
          live_bonus += int(15 * progress)  # Up to +15 more in final period
      # Overtime bonus
      if period and total_periods and period > total_periods:
          live_bonus += 10  # Overtime is always exciting
  ```
- Use `event.period` and sport-specific period counts (NBA=4, NFL=4, NHL=3, soccer=2, etc.)

**Files**: `backend/app/utils/highlights.py` (modify live scoring in `compute_highlight()`)

### 1d. Velocity Features

**Idea**: Odds that are *accelerating* in change are more interesting than steady movement.

**Implementation**:
- Already have `probability_change_24h` on futures outcomes and `TimeSeriesMetrics.recent_momentum`
- Add shorter velocity windows: 1h and 6h changes
- Compute acceleration: `accel = momentum_30m - momentum_previous_30m`
- Positive acceleration (things getting MORE volatile) gets bonus

**Files**: `backend/app/utils/highlights.py` (extend `TimeSeriesMetrics`)

---

## Phase 2: Click-Through Tracking (Foundation for ML, ~1-2 days)

Before ML can learn anything, we need behavioral data. Log what users see and what they click.

### 2a. Engagement Events Table

```sql
CREATE TABLE feed_interactions (
    id SERIAL PRIMARY KEY,
    -- Who
    user_id INTEGER REFERENCES users(id),  -- NULL for anonymous
    session_id VARCHAR(64),                 -- Anonymous session tracking
    -- What
    item_type VARCHAR(20) NOT NULL,         -- 'event' or 'futures'
    item_id INTEGER NOT NULL,               -- event.id or futures_market.id
    -- Context
    feed_position INTEGER,                  -- 0-indexed position in feed
    feed_section VARCHAR(30),               -- 'live', 'upcoming', 'markets', 'pinned'
    base_score INTEGER,                     -- Score before personalization
    personalized_score INTEGER,             -- Score after personalization
    -- Action
    action VARCHAR(20) NOT NULL,            -- 'impression', 'click', 'pin', 'thumbs_up', 'thumbs_down'
    dwell_ms INTEGER,                       -- Time spent on detail page (for 'click' actions)
    -- Metadata
    sport_key VARCHAR(100),
    tags JSONB,                             -- event_tags or market_tags at time of interaction
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_feed_interactions_user ON feed_interactions(user_id, created_at DESC);
CREATE INDEX idx_feed_interactions_item ON feed_interactions(item_type, item_id);
CREATE INDEX idx_feed_interactions_action ON feed_interactions(action, created_at DESC);
```

### 2b. Frontend Instrumentation

```typescript
// Track impressions when cards enter viewport (IntersectionObserver)
// Track clicks when user navigates to detail page
// Track dwell time on return from detail page

POST /api/interactions/batch
Body: [
  { item_type: "event", item_id: 123, action: "impression", feed_position: 3, ... },
  { item_type: "event", item_id: 123, action: "click", feed_position: 3, ... },
]
```

- Batch impressions — send every 5 seconds or on page unload
- Use `IntersectionObserver` for viewport-based impression tracking
- Track dwell via `performance.now()` difference between click and return

### 2c. Backend Endpoint

```python
@router.post("/api/interactions/batch")
async def log_interactions(interactions: list[InteractionCreate], ...):
    # Bulk insert, fire-and-forget (don't block feed rendering)
    pass
```

**Data needed before Phase 3**: ~2-4 weeks of impression+click data, covering ~10K+ interactions.

**Files**:
- `backend/alembic/versions/add_feed_interactions.py` (migration)
- `backend/app/models/models.py` (FeedInteraction model)
- `backend/app/routes/feed.py` (batch interaction endpoint)
- `frontend/components/FeedCard.tsx` (impression tracking)
- `frontend/hooks/useImpressionTracking.ts` (IntersectionObserver hook)

---

## Phase 3: Learning to Rank (ML, ~1 week)

Replace hand-tuned weights with learned weights using LightGBM's `lambdarank` objective.

### 3a. Feature Engineering

Extract features from existing data for each feed item:

**Event features** (~20 features):
| Feature | Source | Type |
|---------|--------|------|
| `is_live` | event.status | binary |
| `game_progress` | event.period / sport.total_periods | float 0-1 |
| `current_probability_closeness` | abs(0.5 - home_prob) | float 0-0.5 |
| `opening_probability_closeness` | abs(0.5 - opening_prob) | float 0-0.5 |
| `probability_swing` | abs(current - opening) | float 0-1 |
| `league_tier` | LEAGUE_TIERS[sport_key] | int 1-4 |
| `is_championship` | llm_importance == "championship" | binary |
| `is_playoff` | llm_importance == "playoff" | binary |
| `hours_until_start` | (commence_time - now).hours | float |
| `hours_since_end` | (now - end_time).hours | float |
| `ei_score` | raw_ei * 100 | float 0-100 |
| `volatility_rms` | time_series.volatility_rms | float |
| `lead_changes` | time_series.lead_changes | int |
| `recent_momentum` | time_series.recent_momentum | float |
| `max_championship_prob` | from futures | float 0-1 |
| `is_national_tv` | broadcast_info contains ESPN/FOX/etc | binary |
| `is_weekend` | commence_time day of week | binary |
| `is_primetime` | 7-11pm ET | binary |
| `source_count` | how many bookmakers have odds | int |

**Futures features** (~10 features):
| Feature | Source | Type |
|---------|--------|------|
| `market_tier` | market.market_tier | int 1-5 |
| `sport_category` | llm_sport_category (encoded) | categorical |
| `leader_probability` | top outcome probability | float |
| `top_mover_change` | biggest 24h change | float |
| `days_until_resolution` | resolution_date - now | float |
| `outcome_count` | number of outcomes | int |
| `source_count` | canonical key source count | int |
| `is_resolving_soon` | resolution_date within 7 days | binary |

**Personalization features** (~8 features):
| Feature | Source | Type |
|---------|--------|------|
| `has_followed_team` | team in user favorites | binary |
| `team_relationship_weight` | max weight from team_relations | float |
| `sport_affinity` | from sport_affinities | float 0-1 |
| `is_pinned` | user pinned this item | binary |
| `is_rival_playing` | rival team involved | binary |
| `has_roster_player` | futures about roster player | binary |

### 3b. Training Pipeline

```python
# Offline training job (run nightly or weekly)

import lightgbm as lgb

# 1. Load interactions from feed_interactions table
# 2. Join with features at time of interaction
# 3. Build training data:
#    - query_id = (user_id or session_id, timestamp_bucket)
#    - label = 1 if clicked, 0 if impression-only
#    - features = event/futures features + personalization features

train_data = lgb.Dataset(
    features_matrix,
    label=click_labels,
    group=query_group_sizes,  # Items in same feed impression
)

params = {
    "objective": "lambdarank",
    "metric": "ndcg",
    "ndcg_eval_at": [5, 10, 20],
    "num_leaves": 31,
    "learning_rate": 0.05,
    "min_data_in_leaf": 10,
}

model = lgb.train(params, train_data, num_boost_round=200)
model.save_model("ranking_model.txt")
```

### 3c. Serving

Two options, ordered by simplicity:

**Option A: Score override (simplest)**
- Load the trained model on backend startup
- In `_score_events()` and `_score_futures()`, after computing features, call `model.predict(features)` to get a learned score
- Use learned score instead of `compute_highlight().score`
- Keep `compute_highlight()` as fallback for cold-start (no model or new user)

**Option B: Hybrid scoring**
- Use learned weights but keep the additive structure:
  ```python
  # Extract feature importances from the trained model
  # Map back to highlight weight names
  # Update WEIGHTS dict with learned values
  ```
- This preserves interpretability and the existing label system

### 3d. Evaluation

Before deploying the learned model:
- Offline: Compare NDCG@10 of learned model vs current heuristic on held-out data
- A/B test: 50% of users get learned rankings, 50% get current
- Monitor: CTR (click-through rate), average position of clicked items, session depth

**Dependencies**: `lightgbm` (pip), no GPU needed, trains in seconds on this data volume

**Files**:
- `backend/app/ranking/` (new package)
  - `features.py` — feature extraction from events/futures
  - `model.py` — model loading, prediction, fallback
  - `train.py` — offline training script
- `backend/app/routes/feed.py` — integrate model scoring

---

## Phase 4: Cross-User Signals (Moderate ML, ~1 week)

### 4a. Trending Score

**Idea**: Items that many users are clicking on right now are probably interesting.

**Implementation**:
- Aggregate `feed_interactions` in rolling 1h windows
- Compute `trending_score = clicks_last_hour / impressions_last_hour` (CTR)
- Normalize by item type (events have different base CTR than futures)
- Add as a feature to the LTR model

### 4b. Collaborative Filtering (Simple)

**Idea**: "Users who follow the Lakers also tend to click on Warriors games"

**Implementation**:
- Use [Implicit](https://github.com/benfred/implicit) library (Python, MIT license)
- Build user-item matrix from `feed_interactions` (clicks only)
- Train ALS (Alternating Least Squares) model weekly
- For each user, get top-K recommended items as an additional signal
- Add `collaborative_score` as a feature in the LTR model

**Files**:
- `backend/app/ranking/trending.py` — rolling CTR computation
- `backend/app/ranking/collaborative.py` — implicit ALS training + inference

---

## Phase 5: Contextual Bandits (Advanced, future)

Replace static ranking with explore/exploit:
- 90% of the time: show the highest-ranked items (exploit)
- 10% of the time: show promising items that need more data (explore)
- Use Thompson Sampling or UCB for the exploration strategy
- Prevents filter bubbles and discovers new interesting content

**Tool**: [Vowpal Wabbit](https://vowpalwabbit.org/) contextual bandits

---

## Research References

| Resource | Relevance |
|----------|-----------|
| [LightGBM LambdaRank](https://lightgbm.readthedocs.io/en/latest/Parameters.html#objective) | Core ML ranking algorithm |
| [Metarank](https://github.com/metarank/metarank) | Open-source ranking service (alternative to building from scratch) |
| [FiveThirtyEight data](https://github.com/fivethirtyeight/data) | Elo ratings, game importance methodology |
| [Bill James Leverage Index](https://en.wikipedia.org/wiki/Leverage_Index) | Predictive excitement metric |
| [Wide & Deep (Google, 2016)](https://arxiv.org/abs/1606.07792) | Combining rules (wide) with learned features (deep) |
| [From RankNet to LambdaMART (Burges, 2010)](https://www.microsoft.com/en-us/research/publication/from-ranknet-to-lambdarank-to-lambdamart-an-overview/) | LTR theory |
| [Implicit library](https://github.com/benfred/implicit) | Collaborative filtering on implicit feedback |
| [RecBole](https://recbole.io/) | 90+ recommendation algorithms in one framework |
| [ESPN BPI methodology](https://www.espn.com/blog/statsinfo/post/_/id/123048) | Basketball Power Index |
| [nflfastR](https://www.nflfastr.com/) | NFL win probability model (already used for EI) |

---

## Implementation Priority

| Phase | Effort | Impact | Dependencies |
|-------|--------|--------|-------------|
| 1a. Futures stake weighting | 0.5 day | High | None |
| 1b. Season context | 0.5 day | Medium | None |
| 1c. Richer live features | 0.5 day | High | ESPN game clock (already have) |
| 1d. Velocity features | 0.5 day | Medium | TimeSeriesMetrics (already have) |
| 2a-c. Click-through tracking | 1-2 days | Critical (enables ML) | None |
| 3. LTR model | 1 week | Transformative | Phase 2 data (~2-4 weeks) |
| 4a. Trending | 0.5 day | High | Phase 2 |
| 4b. Collaborative filtering | 1 week | Medium-High | Phase 2 data (~4+ weeks) |
| 5. Contextual bandits | 2 weeks | High (long-term) | Phase 3 |

**Recommended order**: 1a → 1c → 2a-c → (wait for data) → 3 → 4a → 1b → 1d → 4b → 5
