# Canonical Identity System Migration — Full Execution Prompt

Copy everything below this line and paste it into Claude Code CLI.

---

## TASK: Migrate Bain Luck to a Canonical Identity System Using StatPal

You are performing a major architectural refactor of the Bain Luck codebase. The goal is to establish StatPal as the **canonical source of truth** for event schedules, team identity, and player identity — replacing the current fragmented system where The Odds API serves as the accidental source of truth and every other data source (ESPN, StatPal, Kalshi, Polymarket) is grafted on with bespoke fuzzy matching.

**This is a long-running task. It's okay if it takes many hours. Be thorough, not fast.**

Read `CLAUDE.md` first to understand the full project architecture.

---

## CRITICAL: FRONT-LOAD ALL PERMISSION QUESTIONS

Before writing any code, ask me ALL permission/preference questions at once. This includes:
- Any architectural decisions where there are multiple valid approaches
- Any questions about backwards compatibility tradeoffs
- Any questions about whether to keep or remove deprecated code paths
- Any unclear requirements

I want to answer all questions upfront so you can then execute autonomously for hours without needing me.

---

## CONTEXT: WHY THIS MIGRATION

Currently the system has these pain points:

1. **The Odds API is the accidental source of truth** for events, but it has known `commence_time` bugs and unreliable team names
2. **Every data source re-implements team matching** — ESPN sync has 3-signal matching, StatPal sync has its own, prediction market matching has 291 tests worth of heuristic matching, related futures has ILIKE queries
3. **StatPal fixture IDs are stuffed into a JSONB column** (`win_probability_sources["statpal_fixture_id"]`) instead of being a proper indexed column
4. **There is no team identity mapping table** — matching "Lakers" to "Los Angeles Lakers" to "LAL" to ESPN ID "13" happens ad-hoc everywhere
5. **Sport key formats differ across every system** — `americanfootball_nfl` (Odds API), `nfl` (StatPal), `football_nfl` (win prob model), `kxnbagame` (Kalshi tickers), `basketball` (LLM categories)

The user has no production users yet, so we can make breaking changes freely.

---

## WHAT TO BUILD (6 Components)

### Component 1: `team_identity_mapping` Table + Migration

Create a new database table that maps team identities across ALL sources:

```sql
CREATE TABLE team_identity_mapping (
    id SERIAL PRIMARY KEY,
    team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    source VARCHAR(30) NOT NULL,  -- 'odds_api', 'espn', 'statpal', 'kalshi', 'polymarket'
    source_id VARCHAR(200),       -- The ID in the source system (ESPN ID, StatPal team_id, etc.)
    source_name VARCHAR(300),     -- The name the source uses for this team
    source_abbreviation VARCHAR(20), -- Abbreviation in source system
    sport_key VARCHAR(50),        -- Our internal sport key
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(source, source_id, sport_key),
    UNIQUE(source, source_name, sport_key)
);
CREATE INDEX ix_team_identity_team_id ON team_identity_mapping(team_id);
CREATE INDEX ix_team_identity_source ON team_identity_mapping(source);
CREATE INDEX ix_team_identity_source_name ON team_identity_mapping(source_name);
```

Also add proper columns to the Event model (instead of JSONB hacks):
- `Event.statpal_fixture_id` — VARCHAR(100), nullable, indexed
- `Event.statpal_end_time` — TIMESTAMPTZ, nullable
- `Event.commence_time_source` — VARCHAR(20), nullable (tracks which source set the current commence_time: 'odds_api', 'espn', 'statpal')

And add to the Team model:
- `Team.statpal_team_id` — VARCHAR(100), nullable, indexed

**Alembic migration notes:**
- Chain to `down_revision = "nullable_lma_event_id"` (the current HEAD)
- Revision IDs must be ≤32 characters
- Use `op.create_table()` for the new table
- Use `op.add_column()` for new Event/Team columns
- Include a data migration step that copies `win_probability_sources["statpal_fixture_id"]` to the new `Event.statpal_fixture_id` column for existing rows
- Alembic uses synchronous psycopg2, not asyncpg

### Component 2: Canonical Sport Key Mapping Module

Create `backend/app/utils/sport_keys.py` — a SINGLE module that consolidates ALL sport key mappings:

```python
"""Canonical sport key mapping.

Every sport key translation in the system should go through this module.
No more per-file mapping dictionaries scattered across config.py,
prediction_market_matching.py, win_probability.py, team_linking.py, etc.
"""

# The canonical internal key format (matches The Odds API since that's our
# existing primary key in the sports table and we're not changing it)
# e.g., "basketball_nba", "americanfootball_nfl", "icehockey_nhl"

def to_statpal(sport_key: str) -> str | None:
    """Convert internal sport key to StatPal API sport identifier."""

def to_espn(sport_key: str) -> str | None:
    """Convert internal sport key to ESPN API path."""

def to_win_prob_model(sport_key: str) -> str | None:
    """Convert internal sport key to win probability model key."""

def from_kalshi_ticker(ticker: str) -> str | None:
    """Extract internal sport key from Kalshi game ticker prefix."""

def from_llm_category(category: str) -> list[str]:
    """Convert LLM sport category to list of internal sport keys."""

def to_llm_category(sport_key: str) -> str | None:
    """Convert internal sport key to LLM sport category."""

def get_sport_group(sport_key: str) -> str | None:
    """Get the base sport group (basketball, football, etc.)."""
```

Then update ALL existing mapping dictionaries to import from this module:
- `backend/app/tasks/config.py` — `ESPN_SPORT_MAPPING`, `STATPAL_SPORT_MAPPING`
- `backend/app/utils/win_probability.py` — `_SPORT_KEY_ALIASES`
- `backend/app/utils/prediction_market_matching.py` — `_TICKER_TO_SPORT_PREFIX`, `_SPORT_CATEGORY_TO_KEY_PREFIX`
- `backend/app/utils/team_linking.py` — `SPORT_CATEGORY_TO_KEYS`
- `backend/app/utils/futures_categorization.py` — sport prefix matching
- `frontend/lib/sportCategories.ts` — keep frontend mappings in sync (document the canonical mapping)

**Do NOT change the internal sport key format.** Keep `basketball_nba`, `americanfootball_nfl`, etc. — changing that would break the `sports` table, 200+ tests, and The Odds API integration. The consolidation is about having ONE source of truth for all translations, not changing the format.

### Component 3: Team Identity Resolution Service

Create `backend/app/services/team_identity.py` — a single service that ALL team matching goes through:

```python
"""Canonical team identity resolution.

Replaces the ad-hoc team name matching scattered across:
- espn_sync.py (3-signal matching with name normalization)
- statpal_sync.py (_find_matching_event team matching)
- prediction_market_matching.py (fuzzy matching + ticker abbreviation parsing)
- team_linking.py (outcome-to-team matching)
- events.py related-futures (ILIKE queries)
- user.py team search (location + name matching)
"""

class TeamIdentityService:
    """Resolves team identities across all data sources."""

    async def resolve_team(
        self,
        session: AsyncSession,
        source: str,  # 'odds_api', 'espn', 'statpal', 'kalshi', 'polymarket'
        sport_key: str,
        *,
        source_id: str | None = None,
        source_name: str | None = None,
        source_abbreviation: str | None = None,
    ) -> Team | None:
        """Find our Team record for a team from any external source.

        Resolution order:
        1. Exact match on team_identity_mapping by (source, source_id, sport_key)
        2. Exact match on team_identity_mapping by (source, source_name, sport_key)
        3. Fuzzy name match on team_identity_mapping.source_name
        4. Fuzzy name match on teams.name / teams.alternate_names
        5. Return None (caller decides whether to auto-create)
        """

    async def register_team_identity(
        self,
        session: AsyncSession,
        team_id: int,
        source: str,
        sport_key: str,
        *,
        source_id: str | None = None,
        source_name: str | None = None,
        source_abbreviation: str | None = None,
    ) -> None:
        """Register a team identity mapping. Upserts on conflict."""

    async def resolve_from_kalshi_ticker(
        self,
        session: AsyncSession,
        ticker: str,
    ) -> tuple[Team | None, Team | None]:
        """Extract and resolve both teams from a Kalshi game ticker."""

    async def find_teams_for_event(
        self,
        session: AsyncSession,
        home_team_name: str,
        away_team_name: str,
        sport_key: str,
    ) -> tuple[Team | None, Team | None]:
        """Resolve home and away teams for an event."""
```

This service should use the `_normalize_name()` function (NFD decomposition, accent stripping, apostrophe unification) that currently exists in `team_linking.py` and `espn_sync.py` — consolidate into one copy in this module.

### Component 4: Refactor StatPal Sync to Be Schedule-First

Modify `backend/app/tasks/statpal_sync.py` so that:

1. **Schedule sync runs BEFORE odds polling** — Change beat schedule so StatPal schedule sync runs at `:00` (currently `:40`), before event discovery at `:15`. This means StatPal can pre-create Event records with correct times.

2. **StatPal schedule sync can CREATE events** — Currently it only enriches existing events. Change it to also create Event records for fixtures that don't exist yet. These events would have `status="scheduled"`, correct `commence_time`, `statpal_fixture_id`, and `commence_time_source="statpal"`. When The Odds API later discovers the same event, it attaches odds to the existing record instead of creating a duplicate.

3. **StatPal is authoritative for commence_time** — When StatPal provides a `start_time`, it always wins over The Odds API. ESPN should NOT overwrite `commence_time` if `commence_time_source="statpal"`. Add this check to ESPN sync.

4. **Store StatPal team IDs on Team records** — When syncing schedules/rosters, populate `Team.statpal_team_id` and register in `team_identity_mapping`.

5. **Move StatPal data out of JSONB** — Injuries and plays can stay in `win_probability_sources` JSONB (they're ephemeral context data). But `statpal_fixture_id`, `statpal_end_time`, and `statpal_team_id` should use the new proper columns.

### Component 5: Refactor Consumers to Use Team Identity Service

Update these files to use `TeamIdentityService` instead of their bespoke matching:

1. **`tasks/espn_sync.py`** — Replace the local `names_match()` and 3-signal matching with `TeamIdentityService.resolve_team(source="espn", ...)`. On successful match, call `register_team_identity()` to populate the mapping table.

2. **`tasks/statpal_sync.py`** — Replace `_find_matching_event()` with lookups via `statpal_fixture_id` (primary) and `TeamIdentityService` (fallback). Register StatPal team IDs in the mapping table.

3. **`tasks/prediction_market_matching.py`** — Replace fuzzy matching in `_score_candidates()` with `TeamIdentityService` lookups. The ticker parsing (`extract_teams_from_ticker`) should feed into `resolve_from_kalshi_ticker()`. Keep the regex detection layer (prop detection, matchup extraction) — that can't be replaced by a lookup table. But the team resolution step should go through the service.

4. **`tasks/team_linking.py`** — Replace `match_outcome_to_team()` with `TeamIdentityService.resolve_team()`.

5. **`routes/events.py` related-futures** — Replace the ILIKE team name matching with joins through `team_identity_mapping` where possible, falling back to ILIKE for names not yet in the mapping.

6. **`tasks/sports.py` event discovery** — When auto-creating teams from Odds API events, register the Odds API name in `team_identity_mapping`.

7. **`tasks/roster_sync.py`** — When syncing rosters, register team identities from ESPN/StatPal.

### Component 6: Populate the Mapping Table

Create a one-time backfill task and an ongoing population strategy:

**One-time backfill (`POST /api/admin/team-identity/backfill`):**
1. For every Team with `espn_id`, create mapping `(source="espn", source_id=espn_id, source_name=espn_display_name)`
2. For every Team with `statpal_team_id`, create mapping `(source="statpal", source_id=statpal_team_id)`
3. For every Team, create mapping `(source="odds_api", source_name=team.name)`
4. For every Team with `alternate_names`, create additional `odds_api` mappings for each alternate name
5. For every Team with `abbreviation`, create mapping with `source_abbreviation`
6. Seed Kalshi abbreviation mappings from the existing `_TEAM_ABBREVIATIONS` dict in `prediction_market_matching.py`

**Ongoing population:**
- ESPN sync: registers ESPN IDs and names on every sync
- StatPal sync: registers StatPal team IDs on every sync
- Event discovery: registers Odds API names on every event creation
- Prediction market matching: registers Kalshi abbreviations when ticker parsing succeeds

---

## TESTING STRATEGY

### Before starting, run the existing test suite to establish baseline:
```bash
cd backend && python -m pytest tests/ -v --tb=short 2>&1 | tail -50
cd frontend && npx jest 2>&1 | tail -20
```

### New tests to write:

1. **`backend/tests/test_sport_keys.py`** (~30 tests)
   - Every mapping function round-trips correctly
   - `to_statpal("americanfootball_nfl") == "nfl"`
   - `to_espn("basketball_nba") == "basketball/nba"`
   - `from_kalshi_ticker("KXNBAGAME-26FEB19BOSGSW") == "basketball_nba"`
   - `from_llm_category("basketball") == ["basketball_nba", "basketball_ncaab", ...]`
   - Unknown keys return None (not crash)

2. **`backend/tests/test_team_identity.py`** (~50 tests)
   - `resolve_team` finds team by source_id
   - `resolve_team` finds team by source_name (exact)
   - `resolve_team` finds team by source_name (fuzzy — "Lakers" matches "Los Angeles Lakers")
   - `resolve_team` returns None for unknown teams
   - `register_team_identity` upserts correctly
   - `resolve_from_kalshi_ticker` parses and resolves both teams
   - Cross-source resolution: register as ESPN, resolve as Kalshi abbreviation
   - Duplicate registration doesn't crash (UNIQUE conflict handled)
   - Sport key filtering works (Lakers basketball != Lakers esports)

3. **`backend/tests/test_statpal_schedule_first.py`** (~20 tests)
   - StatPal creates events that don't exist yet
   - Odds API attaches to StatPal-created events (no duplicate)
   - `commence_time_source` is set correctly
   - ESPN doesn't overwrite StatPal commence_time
   - Event matching when StatPal creates first vs Odds API creates first

4. **Update existing tests that break:**
   - Tests that directly construct Team/Event objects may need `statpal_fixture_id`, `statpal_team_id`, `commence_time_source` columns
   - Tests that import mapping dicts from `config.py` or `prediction_market_matching.py` should be updated to import from `sport_keys.py`
   - Do NOT change test assertions for things that shouldn't change (Pulse algorithm, odds math, highlights scoring, etc.)

### After all changes, run the FULL test suite:
```bash
cd backend && python -m pytest tests/ -v 2>&1 | tee /tmp/test-results.txt
cd frontend && npx jest 2>&1 | tee /tmp/frontend-test-results.txt
```

**All existing tests must pass** (with updates for new column names/imports only). If a test breaks for a non-trivial reason, investigate — it probably means the refactor broke something real.

---

## EXECUTION ORDER

1. **Read the full codebase context** — Read CLAUDE.md, models.py, all files listed in the Components above
2. **Ask ALL permission/preference questions at once** (front-loaded)
3. **Create the Alembic migration** (Component 1) — new table + new columns + data migration
4. **Create `sport_keys.py`** (Component 2) — consolidate all mappings
5. **Create `team_identity.py`** (Component 3) — the identity resolution service
6. **Write all new tests** (test_sport_keys.py, test_team_identity.py, test_statpal_schedule_first.py)
7. **Run new tests to verify they pass**
8. **Update models.py** with new columns on Event and Team
9. **Refactor StatPal sync** (Component 4) — schedule-first, proper columns
10. **Refactor consumers one at a time** (Component 5) — espn_sync, statpal_sync, prediction_market_matching, team_linking, events.py, sports.py, roster_sync
11. **Create backfill task** (Component 6) — one-time + ongoing registration
12. **Run FULL test suite** — fix any breakages
13. **Update CLAUDE.md** with the new architecture
14. **Commit and push**

---

## FILES YOU'LL NEED TO READ

Read these before starting (in rough priority order):

- `CLAUDE.md` — Full project documentation
- `backend/app/models/models.py` — All database models
- `backend/app/tasks/statpal_sync.py` — Current StatPal integration
- `backend/app/services/statpal_api.py` — StatPal API client and response models
- `backend/app/tasks/config.py` — Sport mappings, polling intervals
- `backend/app/tasks/__init__.py` — Task wrappers and beat schedule
- `backend/app/tasks/base.py` — `get_task_session()` and `run_async()` patterns
- `backend/app/tasks/espn_sync.py` — ESPN matching to refactor
- `backend/app/tasks/prediction_market_matching.py` — PM matching to refactor
- `backend/app/utils/prediction_market_matching.py` — Detection logic (keep regex, refactor team resolution)
- `backend/app/utils/team_linking.py` — Team matching to refactor
- `backend/app/tasks/sports.py` — Event discovery (team auto-creation)
- `backend/app/tasks/roster_sync.py` — Roster sync
- `backend/app/routes/events.py` — Related futures, search, typeahead
- `backend/app/routes/feed.py` — Feed queries
- `backend/app/routes/user.py` — Team search, onboarding
- `backend/app/routes/admin.py` — Admin endpoints (add new ones for team identity)
- `backend/app/routes/__init__.py` — Router registration
- `backend/app/main.py` — Router includes
- `backend/app/utils/win_probability.py` — `_SPORT_KEY_ALIASES` to consolidate
- `backend/app/utils/futures_categorization.py` — Sport prefix matching
- `backend/alembic/versions/` — Latest migration for chaining
- `backend/tests/` — All test files (to fix breakages)
- `frontend/lib/sportCategories.ts` — Frontend sport key mappings (document sync)

---

## KEY PATTERNS TO FOLLOW

### Alembic Migration Pattern
```python
"""Add canonical identity tables and columns."""
revision = "add_canonical_identity"  # ≤32 chars!
down_revision = "nullable_lma_event_id"

def upgrade():
    # Create new table
    op.create_table("team_identity_mapping", ...)
    # Add columns
    op.add_column("events", sa.Column("statpal_fixture_id", sa.String(100), nullable=True))
    # Create indexes
    op.create_index("ix_events_statpal_fixture_id", "events", ["statpal_fixture_id"])
    # Data migration (copy from JSONB)
    op.execute("""
        UPDATE events
        SET statpal_fixture_id = win_probability_sources->>'statpal_fixture_id'
        WHERE win_probability_sources ? 'statpal_fixture_id'
    """)

def downgrade():
    op.drop_table("team_identity_mapping")
    op.drop_column("events", "statpal_fixture_id")
    # etc.
```

### Task Definition Pattern
```python
# In tasks/__init__.py:
@celery_app.task(bind=True, name="app.tasks.backfill_team_identities")
def backfill_team_identities(self):
    from app.tasks.team_identity_backfill import _backfill_team_identities
    return run_async(_backfill_team_identities())

# In tasks/team_identity_backfill.py:
async def _backfill_team_identities():
    async with get_task_session() as session:
        ...
```

### Model Column Pattern
```python
# In models.py Event class:
statpal_fixture_id = Column(String(100), nullable=True, index=True)
statpal_end_time = Column(DateTime(timezone=True), nullable=True)
commence_time_source = Column(String(20), nullable=True)

# In models.py Team class:
statpal_team_id = Column(String(100), nullable=True, index=True)
```

### Test Pattern
```python
# In tests/test_team_identity.py:
import pytest
from app.services.team_identity import TeamIdentityService

class TestTeamIdentityResolution:
    def test_resolve_by_source_id(self):
        """Exact source_id match should return the team."""
        ...

    def test_resolve_by_source_name_fuzzy(self):
        """Fuzzy name match should find 'Lakers' for 'Los Angeles Lakers'."""
        ...
```

---

## WHAT NOT TO CHANGE

- **Do NOT change the internal sport key format** (`basketball_nba`, `americanfootball_nfl`, etc.) — too many dependencies
- **Do NOT change the `Event.external_id` field** — keep Odds API IDs as the unique constraint
- **Do NOT change frontend URL patterns** — `/events/{id}` uses database ID, not external_id
- **Do NOT remove the prediction market regex detection layer** — prop detection, matchup extraction, ticker parsing are still needed for DETECTING game-level markets. Only the team RESOLUTION step should go through TeamIdentityService
- **Do NOT change the Pulse algorithm, highlights scoring, odds math, or other pure computation modules** — they don't depend on identity
- **Do NOT change the frontend TypeScript types** unless the API response shape actually changes
- **Do NOT delete the existing fuzzy matching functions** — keep them as fallback in TeamIdentityService for teams not yet in the mapping table. The mapping table supplements fuzzy matching; it doesn't replace it entirely until the table is fully populated.

---

## ADMIN ENDPOINTS TO ADD

```
GET  /api/admin/team-identity/status         — Count of mappings by source, unmapped teams
POST /api/admin/team-identity/backfill       — Trigger one-time backfill task
GET  /api/admin/team-identity/search?q=lakers — Search mappings across all sources
GET  /api/admin/team-identity/team/{id}      — All identity mappings for a specific team
GET  /api/admin/team-identity/unmapped       — Teams with no mappings (need attention)
```

---

## COMMIT AND PUSH

When everything passes:
1. Commit with a descriptive message explaining the architectural change
2. Push to branch `claude/integrate-statpal-api-eRTwo`

```bash
git push -u origin claude/integrate-statpal-api-eRTwo
```
