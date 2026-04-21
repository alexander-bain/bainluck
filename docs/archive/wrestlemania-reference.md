# WrestleMania 42 Prediction Game — Reference Patterns

Archived April 21, 2026. The WrestleMania prediction game was a throwaway feature for a single event (April 18-19, 2026). The runtime code has been removed, but these patterns are worth reusing for future event-specific pages (Super Bowl props, March Madness brackets, awards shows, etc.).

## What It Was

A fake-money prediction game where friends bet $1M virtual bankroll on WrestleMania match outcomes. Featured: per-match odds (Polymarket-sourced), pick submission with bankroll accounting, leaderboard with combinatorial win probability, and GPT-4o-mini commentary.

## Patterns Worth Reusing

### 1. Polymarket Binary Market Polling

Polled Polymarket's CLOB API directly using `token_id` per outcome. Each WrestleMania match mapped to a Polymarket condition, each outcome had a `polymarket_token_id`. The polling service hit `clob.polymarket.com/prices` with token IDs and extracted midpoint prices.

**Key insight:** Polymarket neg-risk markets return empty `outcomePrices` — must fall back to bid/ask midpoint from the CLOB API's order book endpoint.

### 2. Pick/Bankroll Accounting (Decimal Math)

Used Python's `Decimal` type throughout to avoid floating-point rounding errors in money calculations. Bankroll formula:
```
bankroll = starting - sum(all_stakes) + sum(winning_payouts)
max_possible = starting - sum(all_stakes) + sum(winning_payouts) + sum(pending_payouts)
```

Players could bet on multiple outcomes per match (one pick per outcome, not per match). Replacing a pick on the same outcome refunded the old stake first.

### 3. Combinatorial Win Probability Enumeration

Computed exact win probability for each player by enumerating all possible outcome combinations across unresolved matches:

```python
for combo in product(*match_outcomes):
    scenario_prob = product of individual outcome probabilities
    compute each player's bankroll in this scenario
    player with highest bankroll gets scenario_prob added to their win count
```

**Key gotcha found and fixed:** The enumeration used outcome probabilities from the database's static `probability` column instead of the latest odds snapshots. This made the leader show 100% when they were really ~77%. Fix: query latest `WrestlemaniaOddsSnapshot` per outcome.

### 4. LLM Commentary Generation

System prompt positioned GPT-4o-mini as a "sassy wrestling announcer." Context prompt included: current leaderboard with bankrolls + pick details, resolved match results, remaining match count. Generated 2-3 sentence commentary cached in Redis (2-min TTL) with a scrollable feed of past commentary entries.

### 5. Odds Snapshot History

Stored per-outcome probability snapshots with source and timestamp in `WrestlemaniaOddsSnapshot`. Used for sparkline charts showing how odds moved over time. Opening odds derived from earliest snapshot per outcome.

## Database Tables (Still in Postgres)

- `wrestlemania_matches` — match order, night, title, match_type, participants (JSONB), status, winner
- `wrestlemania_outcomes` — name, probability, decimal_odds, is_winner, wikipedia_image_url
- `wrestlemania_odds_snapshots` — per-outcome probability history
- `wrestlemania_players` — display_name, player_token, bankroll
- `wrestlemania_picks` — player_id, outcome_id, match_id, stake, decimal_odds_at_pick, result, payout

Tables are kept for historical queries. The Alembic migration that created them is preserved (never delete applied migrations).

## Files Removed

- `backend/app/tasks/wrestlemania.py` — Polymarket polling task
- `backend/app/routes/wrestlemania.py` — API endpoints (card, picks, leaderboard, commentary, admin)
- `backend/app/models/wrestlemania.py` — SQLAlchemy models
- `backend/app/utils/wrestlemania_scoring.py` — bankroll + win probability computation
- `backend/app/services/wrestlemania_polymarket.py` — Polymarket CLOB API client
- `frontend/components/wrestlemania/` — React components (MatchCard, PickDrawer, Leaderboard, etc.)
- `frontend/app/wrestlemania/` — Next.js page
