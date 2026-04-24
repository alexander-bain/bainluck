# Hill-Climb Guide: Semantic Matching Accuracy

How to measure and improve matching accuracy to 100%. This playbook was developed during the April 23, 2026 sprint that took event matching from "all missing" to 100% across 4 layers and 3 sports.

## The Pattern

1. **Build the measurement tool** — an audit script with a clear score per item
2. **Get a baseline** — run the audit, see the actual numbers
3. **Fix the biggest bucket** — the single category causing the most failures
4. **Re-measure** — confirm the score went up
5. **Repeat** until 100%

## The Four Layers

| Layer | What it measures | Audit command | Key files |
|-------|-----------------|---------------|-----------|
| **L1: Event Existence** | Every game exists with all sources | `--self-check` | `services/event_registry.py` |
| **L2: Market→Event** | All game markets linked to events | `--self-check` | `tasks/prediction_market_matching.py` |
| **L3: Futures Surfacing** | Season futures on event detail pages | `--self-check` | `routes/events.py` (related-futures) |
| **L4: Market Completeness** | Every market type showing per game | `--l4-deep` | `routes/events.py` (game-markets) |

### Running the audit

```bash
cd backend

# Quick 4-layer self-check for one sport
python3 scripts/audit_event_matching.py --self-check --sport baseball_mlb

# Deep L4: per-game market type coverage + Polymarket
python3 scripts/audit_event_matching.py --l4-deep --sport baseball_mlb

# All sports
for sport in baseball_mlb basketball_nba icehockey_nhl; do
  python3 scripts/audit_event_matching.py --self-check --sport $sport
done

# Grid accuracy (separate script, already at 100%)
python3 scripts/audit_grid_accuracy.py
```

### Manus ground truth (for manual verification)

Prompt: `Manus/prompts/event_matching_ground_truth.md`

Sweeps today's games on Kalshi/Polymarket, deep-audits 3 games for market completeness, checks event detail pages. Feed the JSON output to:

```bash
python3 scripts/audit_event_matching.py --ground-truth path/to/gt.json
```

## Gotchas We Encountered

### Measurement bugs (the audit itself was wrong)

- **Wrong category vocabulary**: L3 audit checked for `"championship"`, `"pennant"` etc. but `classify_market_category()` returns `"playoff_path"`, `"season_stat"`. Always verify the audit against manual API inspection.
- **Moneyline detection**: Bare matchup names ("Chicago WS vs Arizona") ARE moneylines even without "Winner?" suffix. The audit regex missed them initially.
- **Post-game API data differs from live**: Kalshi clears order book after resolution. Checking liquidity AFTER the game shows `yes_bid=None` — looks like zero liquidity, but the market was active during the game.

### Stacked bugs (each fix reveals the next blocker)

The NBA L3 gap required 5 sequential fixes:
1. Audit vocabulary → label-level regex matching
2. Make_playoffs tier regex widened (`\bmake.+(?:playoffs|postseason)`)
3. `compute_market_tier()` — name patterns checked BEFORE `game_prop` category shortcut (Kalshi mislabels season markets as `game_prop`)
4. Per-tier season market loading (100/tier) prevents one tier crowding out others
5. Audit regex for "Playoff Qualifiers" (Kalshi's alternate naming)

### Upstream vs our bug

- Kalshi creates game markets (spread, total, F5) for all games, but many have **zero liquidity** for lower-profile games. We correctly skip outcomes without pricing — not a bug.
- Polymarket only has game moneylines for NBA playoffs and major events, not regular season MLB/NHL. Not a gap to fix.
- ESPN's scoreboard API provides sparse win probability for MLB (~2 points/game). Supplemented with MLB Stats API data (51 points/game).

### Timing issues

- **Kalshi creates markets 2-3 days before games** with no pricing. Traders add pricing hours before/during the game.
- **Market backfill used `status=open`** but live game markets have `status=active` on Kalshi. This caused spread/total/F5 outcomes to never be populated. Fixed to `status=None`.
- **Matching task must run AFTER polling** to link newly-ingested markets. Poll at :15/:45, match at :05/:20/:35/:50 (every 15 min).

### Data quality issues found along the way

- **Monotonicity violation**: Kalshi's "2+", "Aaron Judge: 1+" outcomes are OVER thresholds. Code treated them as "not over" and inverted probabilities (`1-prob`), causing P(2+) < P(5+).
- **Stat leaders misclassified**: "Doubles Leader" fell through all category rules to the DB `category` fallback ("championship"). Added explicit `season_stat` patterns.

## Key Architecture Points

### How season futures surface (L3)

1. Load markets by sport with per-tier limits (100 per tier, tiers 1-4)
2. Match outcomes to team names via ILIKE patterns
3. Classify home/away by team name matching
4. `classify_market_category()` assigns display category
5. Cross-source dedup via `merge_group`

### How game markets surface (L4)

1. **Primary**: `FuturesMarket.event_id == this_event` (requires prediction market matching task to have linked them)
2. **Fallback**: Unlinked markets matching both team names + (`category == "game_prop"` OR game-level ticker prefix)
3. `is_game_prop()` detects "Team vs Team: Stat" AND "Team vs Team Winner?" formats

### Polling infrastructure

| Task | Interval | Queue | What it does |
|------|----------|-------|-------------|
| `poll_kalshi_markets` | 2h | background | Ingests ALL Kalshi events (minus crypto) |
| `poll_polymarket_markets` | 1h | background | Ingests ALL Polymarket events (minus crypto) |
| `match_prediction_markets` | 15 min | background | Links game markets to events via `event_id` |
| `poll_live_prediction_markets` | 2 min | realtime | Live price updates for linked markets |

### Admin endpoints for manual triggers

```bash
# Trigger Kalshi poll
curl -X POST "https://api.bainluck.com/api/admin/kalshi/poll?secret=<token>"

# Trigger prediction market matching
curl -X POST "https://api.bainluck.com/api/admin/prediction-markets/match?secret=<token>&limit=1000"

# Trigger tier re-backfill
curl -X POST "https://api.bainluck.com/api/admin/futures/link-teams?secret=<token>&limit=5000&use_llm=false"
```

## When to Re-Run This Playbook

- **New sport season starts** (NFL in September, NCAAF, NCAAB in November)
- **New prediction market source** added (beyond Kalshi/Polymarket)
- **New market types appear** on Kalshi/Polymarket (new prop categories)
- **Link rate drops** below targets (check `/api/admin/prediction-markets/link-rate`)
- **Grid health drops** (check `/api/playoffs/{league}`)
- After major code changes to matching/polling/classification logic

## Files Reference

| File | Purpose |
|------|---------|
| `scripts/audit_event_matching.py` | Four-layer audit (self-check + L4 deep + Manus GT) |
| `scripts/audit_grid_accuracy.py` | Championship grid structural correctness |
| `tasks/prediction_market_matching.py` | Links game markets to events |
| `tasks/kalshi.py` | Kalshi ingestion |
| `tasks/polymarket.py` | Polymarket ingestion |
| `services/kalshi_api.py` | Kalshi API client (backfill logic here) |
| `routes/events.py` | Related futures + game-markets endpoints |
| `utils/market_label_normalization.py` | Category classification + tier assignment |
| `utils/futures_categorization.py` | `is_game_prop()` + sport detection |
| `utils/sport_keys.py` | Ticker prefix maps (single source of truth) |
| `Manus/prompts/event_matching_ground_truth.md` | Manus sweep prompt |
