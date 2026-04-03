# Phase 1: Consolidate Sport Key Mappings

**Estimated time: 30-60 minutes. Zero schema changes. Zero behavior changes. Pure refactor.**

Read `CLAUDE.md` first to understand the full project architecture.

---

## TASK

Create `backend/app/utils/sport_keys.py` — a SINGLE module that consolidates ALL sport key translation dictionaries currently scattered across the codebase. Then update all existing files to import from this module instead of maintaining their own copies.

**This is a safe, non-breaking refactor.** The internal sport key format (`basketball_nba`, `americanfootball_nfl`, etc.) does NOT change. We're just moving all the translation dictionaries into one place.

---

## STEP 1: Audit existing mappings

Read these files and catalog every sport key mapping dictionary:

1. `backend/app/tasks/config.py` — `ESPN_SPORT_MAPPING`, `STATPAL_SPORT_MAPPING`
2. `backend/app/utils/win_probability.py` — `_SPORT_KEY_ALIASES`, `SPORT_PARAMS`
3. `backend/app/utils/prediction_market_matching.py` — `_SPORT_CATEGORY_TO_KEY_PREFIX`, Kalshi ticker prefixes (`_KALSHI_GAME_TICKER_PREFIXES`), `get_sport_prefix_from_ticker()`
4. `backend/app/utils/team_linking.py` — any `SPORT_CATEGORY_TO_KEYS` or similar
5. `backend/app/utils/futures_categorization.py` — sport prefix matching
6. `backend/app/tasks/espn_sync.py` — any local sport key references

Write down every unique mapping you find. Note which file it's in, the dict name, and a sample entry.

---

## STEP 2: Create `backend/app/utils/sport_keys.py`

Build a module with these functions:

```python
"""Canonical sport key mapping.

Every sport key translation in the system should go through this module.
The canonical internal format matches The Odds API (since that's the primary
key in the sports table): e.g., "basketball_nba", "americanfootball_nfl".
"""

# Core data: one big registry dict per target system.
# All functions below are thin lookups into these dicts.

def to_statpal(sport_key: str) -> str | None:
    """Convert internal sport key to StatPal API sport identifier.
    e.g., 'americanfootball_nfl' -> 'nfl'"""

def to_espn(sport_key: str) -> str | None:
    """Convert internal sport key to ESPN API path.
    e.g., 'basketball_nba' -> 'basketball/nba'"""

def to_win_prob_model(sport_key: str) -> str | None:
    """Convert internal sport key to win probability model key.
    e.g., 'americanfootball_nfl' -> 'football_nfl'"""

def from_kalshi_ticker(ticker: str) -> str | None:
    """Extract internal sport key from Kalshi game ticker prefix.
    e.g., 'KXNBAGAME-26FEB19BOSGSW' -> 'basketball_nba'"""

def from_llm_category(category: str) -> list[str]:
    """Convert LLM sport category to list of internal sport keys.
    e.g., 'basketball' -> ['basketball_nba', 'basketball_ncaab', 'basketball_wncaab']"""

def to_llm_category(sport_key: str) -> str | None:
    """Convert internal sport key to LLM sport category.
    e.g., 'americanfootball_nfl' -> 'football'"""

def get_sport_group(sport_key: str) -> str | None:
    """Get the base sport group. e.g., 'basketball_nba' -> 'basketball'"""

def llm_category_to_key_prefix(category: str) -> str | None:
    """Convert LLM category to sport key prefix for LIKE queries.
    e.g., 'football' -> 'americanfootball'. Used by prediction market matching."""

def kalshi_game_ticker_prefixes() -> tuple[str, ...]:
    """Return all known Kalshi game ticker prefixes. Used by detection layer."""

def win_prob_model_params() -> dict:
    """Return sport params dict for the win probability model.
    Keys are model-format sport keys (e.g., 'football_nfl')."""
```

**Critical rules:**
- The data must be EXACTLY equivalent to the existing mappings — don't add, remove, or change any entries
- Export the Kalshi ticker prefix tuple so the detection layer can still import it
- Export SPORT_PARAMS (or wrap it) so win_probability.py can still use it
- Keep `ESPN_SPORT_MAPPING` and `STATPAL_SPORT_MAPPING` as dicts exported from this module (tasks/config.py will re-export them for backward compatibility in the beat schedule)

---

## STEP 3: Update consumers

For each file that has its own mapping dict, change it to import from `sport_keys.py`. Do this one file at a time, running tests after each change.

**Update order (least to most risky):**

1. `backend/app/tasks/config.py` — Replace `ESPN_SPORT_MAPPING` and `STATPAL_SPORT_MAPPING` dict definitions with imports from `sport_keys`. Keep the variable names as re-exports so nothing downstream breaks:
   ```python
   from app.utils.sport_keys import ESPN_SPORT_MAPPING, STATPAL_SPORT_MAPPING
   ```

2. `backend/app/utils/win_probability.py` — Replace `_SPORT_KEY_ALIASES` and `SPORT_PARAMS` with imports/calls to `sport_keys`:
   ```python
   from app.utils.sport_keys import to_win_prob_model, win_prob_model_params
   SPORT_PARAMS = win_prob_model_params()
   def _normalize_sport_key(sport_key: str) -> str:
       return to_win_prob_model(sport_key) or sport_key
   ```

3. `backend/app/utils/prediction_market_matching.py` — Replace `_SPORT_CATEGORY_TO_KEY_PREFIX` with import. Replace `get_sport_prefix_from_ticker()` to use `sport_keys.from_kalshi_ticker()`. Keep `_KALSHI_GAME_TICKER_PREFIXES` as a re-import from sport_keys.

4. `backend/app/utils/team_linking.py` — If it has a sport mapping dict, replace with import.

After each file change, run:
```bash
cd backend && python -m pytest tests/ -v --tb=short -x 2>&1 | tail -30
```

Stop and investigate if any test fails for a non-trivial reason.

---

## STEP 4: Write tests for sport_keys.py

Create `backend/tests/test_sport_keys.py` (~25-30 tests):

- Round-trip tests: `to_espn` returns expected values for every mapped sport
- Round-trip tests: `to_statpal` returns expected values
- Round-trip tests: `to_win_prob_model` returns expected values
- `from_kalshi_ticker` extracts correct sport key from real ticker examples
- `from_llm_category("basketball")` returns all basketball sport keys
- `to_llm_category("basketball_nba")` returns "basketball"
- `llm_category_to_key_prefix("football")` returns "americanfootball"
- Unknown keys return `None` (not crash)
- `kalshi_game_ticker_prefixes()` returns a non-empty tuple
- `get_sport_group("americanfootball_nfl")` returns "americanfootball" (or whatever the correct group is)

---

## STEP 5: Run full test suite

```bash
cd backend && python -m pytest tests/ -v 2>&1 | tee /tmp/phase1-test-results.txt
```

**All 1613+ existing tests must pass.** The ONLY acceptable test changes are import path updates (e.g., a test that was importing `_SPORT_KEY_ALIASES` from `win_probability.py` now imports from `sport_keys.py`).

---

## STEP 6: Commit

```bash
git add backend/app/utils/sport_keys.py backend/tests/test_sport_keys.py
git add backend/app/tasks/config.py backend/app/utils/win_probability.py
git add backend/app/utils/prediction_market_matching.py backend/app/utils/team_linking.py
# Add any other modified files
git commit -m "Consolidate sport key mappings into sport_keys.py

Single source of truth for all sport key translations (Odds API <-> ESPN,
StatPal, win prob model, Kalshi tickers, LLM categories). All existing
mapping dicts now import from this module. No behavior changes.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

Do NOT push yet — we'll push after Phase 2.

---

## WHAT NOT TO CHANGE

- Do NOT change the internal sport key format
- Do NOT change any function signatures that other files depend on
- Do NOT add new sports or mappings — only consolidate existing ones
- Do NOT touch the frontend (frontend has its own TypeScript mappings that stay in sync via documentation, not imports)
- Do NOT touch models.py, Alembic, or any database schema
