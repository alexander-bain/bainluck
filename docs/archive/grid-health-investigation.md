# Grid Health Investigation — April 20, 2026

## Root Cause: THREE stacked issues

### Issue 1: Play-In Markets in Conference Column (FIXED)
- Kalshi "Teams to Make the Eastern Conference Play-In Tournament" matched the conference column regex because it contains "Eastern Conference"
- **Fix deployed**: play-in markets now route to make_playoffs column via early pattern check

### Issue 2: Polymarket Outcome Probabilities Stored as 0% (ACTIVE BUG)
- `futures_outcomes.current_probability` = 0 for ALL Polymarket championship/conference market outcomes
- The Polymarket API returns correct probabilities (Celtics 42.1% for Eastern Conference Champion)
- But the poller is not writing `current_probability` correctly for neg-risk multi-outcome markets
- This means the grid has no real probability data from Polymarket for NBA/NHL/MLB
- **Affected markets**: 2026 NBA Champion (id=112887), NBA Eastern Conference Champion (id=112908), NBA Western Conference Champion (id=112909), 2026 NHL Stanley Cup Champion (id=112886), MLB World Series Champion 2026 (id=114584)
- **Root cause**: Likely in `backend/app/tasks/polymarket.py` — need to check how neg-risk outcomes have their probabilities extracted and written

### Issue 3: Monotonicity Enforcement with Bad Data
- With play-in (2%) in make_playoffs and garbage data in conference/championship, monotonicity caps everything to the lowest column
- Once Issues 1 and 2 are fixed, monotonicity will work correctly

## Market Inventory for Big 4

### NBA
| Column | Source | Market Name | Market ID | Status |
|--------|--------|------------|-----------|--------|
| championship | odds_api | NBA Championship Winner | 2 | ✅ Working |
| championship | polymarket | 2026 NBA Champion | 112887 | ❌ Outcomes = 0% |
| championship | kalshi | Pro Basketball Champion | 350 | ✅ Working |
| conference | polymarket | NBA Eastern Conference Champion | 112908 | ❌ Outcomes = 0% |
| conference | polymarket | NBA Western Conference Champion | 112909 | ❌ Outcomes = 0% |
| conference | kalshi | Eastern Conference Champion | 348 | ✅ Working (42.5% Celtics) |
| make_playoffs | kalshi | Pro Basketball Playoff Qualifiers | 432 | ✅ Working |
| make_playoffs | kalshi | Teams to Make Eastern/Western Conference Play-In Tournament | 110410/110409 | ⚠️ Fixed routing |

### NHL
| Column | Source | Market Name | Market ID | Status |
|--------|--------|------------|-----------|--------|
| championship | polymarket | 2026 NHL Stanley Cup Champion | 112886 | ❌ Outcomes = 0% |
| championship | odds_api | (via sport_key) | ? | Needs check |

### MLB
| Column | Source | Market Name | Market ID | Status |
|--------|--------|------------|-----------|--------|
| championship | odds_api | MLB World Series Winner | 1 | ✅ Working |
| championship | polymarket | MLB World Series Champion 2026 | 114584 | ❌ Outcomes = 0% |

## Next Steps
1. **Fix Polymarket probability extraction** for neg-risk multi-outcome markets in `tasks/polymarket.py`
2. **Backfill probabilities** for affected markets by re-polling from Polymarket API
3. **Validate** grid health score improves to 90+ after fix
4. **Build comprehensive matching_overrides** table for edge cases
