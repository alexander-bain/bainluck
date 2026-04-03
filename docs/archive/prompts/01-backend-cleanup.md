# Prompt 1: Backend Cleanup

**Terminal:** 1 of 2 (can run simultaneously with Prompt 2)
**Estimated time:** 3-4 hours
**Risk level:** Medium (name matching changes touch many consumers)

---

## Copy this entire prompt into Claude Code CLI:

```
I need you to do a careful backend refactoring. Read docs/architecture-improvement-plan.md first for full context, then execute each step in order. Run tests after EACH step — do not proceed to the next step if tests fail.

## Step 1: Delete dead code

Delete these files:
- backend/app/services/fangraphs_api.py (stub, returns empty list, no consumers)
- backend/app/services/moneypuck_api.py (stub only)
- backend/app/utils/gei.py (duplicate/abandoned GEI implementation)
- backend/app/tasks/pulse.py (references deleted DB columns raw_gei/gei_components — will crash if called)

BEFORE deleting, grep the entire backend/ for imports of each file:
  grep -r "fangraphs_api\|from.*fangraphs" backend/ --include="*.py"
  grep -r "moneypuck_api" backend/ --include="*.py"
  grep -r "from.*utils.gei import\|from.*utils import.*gei" backend/ --include="*.py"
  grep -r "from.*tasks.pulse import\|from.*tasks import.*pulse" backend/ --include="*.py"

If any file imports from a file you're deleting, remove that import too. If it's a __init__.py re-export, remove the re-export.

Also check: does backend/app/models/models.py have a GEIPercentile alias? If so, grep for any usage of GEIPercentile. If nothing uses it, remove the alias.

After deletions, run: cd backend && python -m pytest tests/ -v
All tests must pass before proceeding.

## Step 2: Rename fangraphs source key to mlb

This is the MLB Stats API integration that was given the wrong source key name.

Files to change (search each file for "fangraphs" string):
1. backend/app/config/win_prob_sources.py — rename the dict key from "fangraphs" to "mlb". Update display_name to "MLB Model" if not already. Keep everything else the same.
2. backend/app/tasks/mlb_sync.py — change source="fangraphs" to source="mlb" everywhere
3. backend/app/routes/events.py — search for any "fangraphs" references
4. Any other backend files referencing "fangraphs" as a source key (grep for it)

Create an Alembic migration to update existing database rows:
  cd backend && alembic revision --autogenerate -m "rename_fangraphs_mlb"

In the migration upgrade():
  op.execute("UPDATE win_prob_snapshots SET source = 'mlb' WHERE source = 'fangraphs'")

In the migration downgrade():
  op.execute("UPDATE win_prob_snapshots SET source = 'fangraphs' WHERE source = 'mlb'")

IMPORTANT: Keep revision ID ≤32 characters.

For backward compatibility, add a temporary comment in win_prob_sources.py:
  # NOTE: Source was renamed from "fangraphs" to "mlb" on 2026-03-05.
  # iOS app may cache "fangraphs" key. Remove this note after April 2026.

After changes, run tests: cd backend && python -m pytest tests/ -v
Pay special attention to test_mlb_api.py and test_win_probability.py.

## Step 3: Consolidate team name matching

Create backend/app/utils/name_normalization.py with a single implementation of:
- normalize_name(name: str) -> str  — lowercase, strip diacritics (NFD), strip reserve suffixes
- names_match(name_a: str, name_b: str) -> bool  — normalized exact match, then containment, then token-overlap scoring (threshold > 0.5)

The reserve suffix regex should handle: reserves?, ii, b, u\d+, youth, academy, women, w
The token-overlap stopwords should include: the, of, fc, sc, cf, ac, as, us

Write comprehensive tests FIRST in backend/tests/test_name_normalization.py (at least 30 tests):
- "Boston Celtics" vs "Celtics" → True (containment)
- "Skarsgård" vs "Skarsgard" → True (diacritics)
- "Boston Celtics II" vs "Boston Celtics" → True (reserve suffix)
- "Air Force Falcons" vs "Atlanta Falcons" → False (token overlap 0.33)
- "South Carolina State" vs "South Carolina" → False (0.5, strict >)
- "LA Lakers" vs "Los Angeles Lakers" → ??? (test what happens, document)
- "Red Sox" vs "Boston Red Sox" → True (containment)
- "FC Barcelona" vs "Barcelona" → True (stopword + containment)
- Empty strings → False
- Same string → True
- Unicode edge cases (Chinese characters, Cyrillic)

Run the new tests: cd backend && python -m pytest tests/test_name_normalization.py -v

Then update consumers ONE AT A TIME, running full tests after each:

Consumer 1: backend/app/utils/team_linking.py
  - Import normalize_name from name_normalization
  - Replace the local _normalize_name() with the imported version
  - Run tests: python -m pytest tests/test_team_linking.py -v

Consumer 2: backend/app/services/team_identity.py
  - Import normalize_name from name_normalization
  - Replace local normalize_name()
  - Run tests: python -m pytest tests/ -v -k "team_identity"

Consumer 3: backend/app/routes/feed.py
  - Import names_match from name_normalization
  - Replace _team_name_matches() with names_match
  - IMPORTANT: feed.py has _RESERVE_SUFFIX_RE — make sure your normalize_name handles this
  - Run tests: python -m pytest tests/ -v

Consumer 4: backend/app/services/mlb_api.py
  - Import names_match from name_normalization
  - Replace _name_matches() with names_match (or adapt)
  - Run tests: python -m pytest tests/test_mlb_api.py -v

Consumer 5: backend/app/tasks/espn_sync.py
  - Import the token_overlap_score helper (expose it from name_normalization)
  - Replace _team_name_match_score with imported version
  - Run ALL tests: python -m pytest tests/ -v

After all consumers are migrated, run the FULL test suite one final time.

## Step 4: Add group_id schema to FuturesMarket

Create an Alembic migration: cd backend && alembic revision --autogenerate -m "add_group_id"

Add to FuturesMarket model in backend/app/models/models.py:
  group_id = Column(String(200), index=True, nullable=True)
  group_type = Column(String(50), nullable=True)
  group_position = Column(Integer, nullable=True)

The migration should:
  op.add_column('futures_markets', sa.Column('group_id', sa.String(200), nullable=True))
  op.add_column('futures_markets', sa.Column('group_type', sa.String(50), nullable=True))
  op.add_column('futures_markets', sa.Column('group_position', sa.Integer, nullable=True))
  op.create_index('ix_futures_markets_group_id', 'futures_markets', ['group_id'])

Run tests after.

## Step 5: Add market_type enum to FuturesMarket

Create backend/app/utils/market_classification.py with:
- MarketType enum: CHAMPIONSHIP, CONFERENCE, DIVISION, AWARD, GAME_MARKET, STAT_PROP, SEASON_STAT, OTHER
- classify_market(market_name: str, market_tier: int | None) -> MarketType function
- Port the regex patterns from frontend/components/RelatedFutures.tsx (STAT_PROP_PATTERNS, GAME_MARKET_PATTERNS, AWARD_PATTERNS, NOT_CHAMPIONSHIP_PATTERNS) into Python

Add market_type column to FuturesMarket model. Create Alembic migration: "add_market_type"

Write tests for classify_market covering the known patterns from the frontend.

Do NOT remove the frontend patterns yet — that's a separate step after we verify the backend classification matches.

Run full test suite: cd backend && python -m pytest tests/ -v

## Final check

After all 5 steps, run the complete test suite one more time:
  cd backend && python -m pytest tests/ -v

Report: which tests pass, which fail (if any), and what the total test count is.
Do NOT commit anything — I will review the changes and commit manually.
```
