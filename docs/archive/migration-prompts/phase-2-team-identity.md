# Phase 2: Team Identity Mapping Table + Service + Backfill

**Estimated time: 1-2 hours. Schema change + new service + backfill. No consumer changes yet.**

**Prerequisite: Phase 1 (sport_keys.py) must be committed.**

Read `CLAUDE.md` first. Also read the new `backend/app/utils/sport_keys.py` from Phase 1.

---

## TASK

Build the team identity infrastructure: a new `team_identity_mapping` database table, a `TeamIdentityService` that resolves teams across data sources, and a backfill task that populates the mapping table from existing data. **Do NOT change any existing consumers yet** — that's Phase 4. This phase builds and validates the infrastructure in isolation.

---

## STEP 1: Read existing team matching code

Read these files to understand current team matching patterns:
- `backend/app/models/models.py` — Team and Event models
- `backend/app/tasks/espn_sync.py` — look for `names_match`, team matching logic
- `backend/app/tasks/statpal_sync.py` — look for `_find_matching_event`, `_fixture_match_key`
- `backend/app/utils/team_linking.py` — look for `_normalize_name`, `_names_match`
- `backend/app/utils/prediction_market_matching.py` — look for `_TEAM_ABBREVIATIONS`, `extract_teams_from_ticker`
- `backend/app/tasks/prediction_market_matching.py` — look for `_score_candidates`, fuzzy matching

Note: there are multiple copies of `_normalize_name()` (NFD decomposition, accent stripping). Find all of them — they'll be consolidated into the TeamIdentityService.

---

## STEP 2: Create Alembic migration

Create `backend/alembic/versions/add_team_identity.py`:

```python
"""Add team_identity_mapping table and StatPal columns."""
revision = "add_team_identity"  # <=32 chars!
down_revision = "nullable_lma_event_id"  # Current HEAD — verify this!
```

**Verify the current HEAD first:**
```bash
ls -la backend/alembic/versions/ | tail -5
```

The migration should:

1. **Create `team_identity_mapping` table:**
```sql
CREATE TABLE team_identity_mapping (
    id SERIAL PRIMARY KEY,
    team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    source VARCHAR(30) NOT NULL,        -- 'odds_api', 'espn', 'statpal', 'kalshi', 'polymarket'
    source_id VARCHAR(200),             -- ID in the source system
    source_name VARCHAR(300),           -- Name the source uses
    source_abbreviation VARCHAR(20),    -- Abbreviation in source
    sport_key VARCHAR(50),              -- Internal sport key
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(source, source_id, sport_key) WHERE source_id IS NOT NULL,
    UNIQUE(source, source_name, sport_key) WHERE source_name IS NOT NULL
);
```
**Important:** Use partial unique indexes (WHERE ... IS NOT NULL) instead of regular UNIQUE constraints, since `source_id` and `source_name` can both be NULL (e.g., you might register a Kalshi abbreviation without knowing the source_name).

Indexes:
```sql
CREATE INDEX ix_team_identity_team_id ON team_identity_mapping(team_id);
CREATE INDEX ix_team_identity_source ON team_identity_mapping(source);
CREATE INDEX ix_team_identity_source_name ON team_identity_mapping(source_name);
CREATE INDEX ix_team_identity_sport_key ON team_identity_mapping(sport_key);
```

2. **Add columns to Event:**
- `statpal_fixture_id` — `String(100)`, nullable, indexed
- `statpal_end_time` — `DateTime(timezone=True)`, nullable
- `commence_time_source` — `String(20)`, nullable (tracks 'odds_api', 'espn', 'statpal')

3. **Add column to Team:**
- `statpal_team_id` — `String(100)`, nullable, indexed

4. **Data migration** — Copy existing JSONB data to proper columns:
```sql
UPDATE events
SET statpal_fixture_id = win_probability_sources->>'statpal_fixture_id'
WHERE win_probability_sources ? 'statpal_fixture_id';

UPDATE events
SET statpal_end_time = (win_probability_sources->>'statpal_end_time')::timestamptz
WHERE win_probability_sources ? 'statpal_end_time';
```

5. **Downgrade** — Drop the table and columns (reverse of above). Do NOT try to migrate data back into JSONB.

**Alembic uses psycopg2 (synchronous), not asyncpg.**

---

## STEP 3: Update models.py

Add columns to the Event and Team models that match the migration:

```python
# Event class:
statpal_fixture_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
statpal_end_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
commence_time_source: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

# Team class:
statpal_team_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
```

Also add the `TeamIdentityMapping` model:

```python
class TeamIdentityMapping(Base):
    """Maps team identities across external data sources."""
    __tablename__ = "team_identity_mapping"

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    source_id: Mapped[Optional[str]] = mapped_column(String(200))
    source_name: Mapped[Optional[str]] = mapped_column(String(300), index=True)
    source_abbreviation: Mapped[Optional[str]] = mapped_column(String(20))
    sport_key: Mapped[Optional[str]] = mapped_column(String(50), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    team: Mapped["Team"] = relationship()
```

---

## STEP 4: Create `backend/app/services/team_identity.py`

This is the core service. Key design principles:
- **Lookup-first, fuzzy-fallback.** Check `team_identity_mapping` by exact source_id, then exact source_name, then fall back to fuzzy matching against `teams.name` and `teams.alternate_names`.
- **Auto-register on match.** When fuzzy matching succeeds, call `register_team_identity()` so the next lookup is a fast exact match.
- **Consolidate `_normalize_name()`.** There are copies in `team_linking.py` and `espn_sync.py`. Put the canonical version here. The other files can import it from here (or keep their copy — we'll clean up imports in Phase 4).
- **Sport-scoped.** All lookups are scoped to `sport_key` to prevent "Lakers basketball" matching "Lakers esports".
- **Async.** All methods take an `AsyncSession`.

```python
"""Canonical team identity resolution.

Single service for resolving team identities across all data sources.
Replaces ad-hoc team name matching scattered across espn_sync, statpal_sync,
prediction_market_matching, team_linking, and events.py.

Resolution priority:
1. Exact match on team_identity_mapping by (source, source_id, sport_key)
2. Exact match on team_identity_mapping by (source, source_name, sport_key)
3. Fuzzy name match on team_identity_mapping.source_name (any source)
4. Fuzzy name match on teams.name / teams.alternate_names
5. Return None
"""

import unicodedata
import logging
from typing import Optional

from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from app.models import Team, TeamIdentityMapping

logger = logging.getLogger(__name__)


def normalize_name(name: str) -> str:
    """Normalize team name for matching. NFD decomposition + accent stripping + lowercase.
    Consolidates the copies in team_linking.py and espn_sync.py."""
    nfkd = unicodedata.normalize("NFD", name)
    stripped = "".join(c for c in nfkd if unicodedata.category(c) != "Mn")
    return stripped.lower().strip()


class TeamIdentityService:

    async def resolve_team(
        self,
        session: AsyncSession,
        source: str,
        sport_key: str,
        *,
        source_id: str | None = None,
        source_name: str | None = None,
        source_abbreviation: str | None = None,
    ) -> Team | None:
        """Find our Team record for a team from any external source."""
        # ... (implement the 5-step resolution described above)

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
        # Use INSERT ... ON CONFLICT DO UPDATE

    async def resolve_from_kalshi_ticker(
        self,
        session: AsyncSession,
        ticker: str,
    ) -> tuple[Team | None, Team | None]:
        """Extract and resolve both teams from a Kalshi game ticker.
        Uses extract_teams_from_ticker() from prediction_market_matching.py."""

    async def find_teams_for_event(
        self,
        session: AsyncSession,
        home_team_name: str,
        away_team_name: str,
        sport_key: str,
    ) -> tuple[Team | None, Team | None]:
        """Resolve home and away teams for an event."""

    async def get_mappings_for_team(
        self,
        session: AsyncSession,
        team_id: int,
    ) -> list[TeamIdentityMapping]:
        """Get all identity mappings for a team (admin/debug use)."""

    async def get_unmapped_teams(
        self,
        session: AsyncSession,
        sport_key: str | None = None,
    ) -> list[Team]:
        """Find teams with no identity mappings (need attention)."""
```

**Fuzzy matching implementation notes:**
- `normalize_name()` both sides before comparing
- Check containment: "Lakers" in "Los Angeles Lakers" → match
- Check last-word match: "Lakers" == last word of "Los Angeles Lakers" → match
- For short names (<4 chars), require exact match to avoid false positives
- Return the BEST match if multiple candidates exist (score by name similarity)

---

## STEP 5: Create backfill task

Create `backend/app/tasks/team_identity_backfill.py`:

```python
async def _backfill_team_identities() -> dict:
    """One-time backfill of team_identity_mapping from existing data."""
```

Backfill sources:
1. Every Team with `espn_id` → register `(source="espn", source_id=espn_id)`
2. Every Team → register `(source="odds_api", source_name=team.name)`
3. Every Team with `alternate_names` → register additional `odds_api` entries for each alternate
4. Every Team with `abbreviation` → register with `source_abbreviation`
5. Seed Kalshi abbreviation mappings from `_TEAM_ABBREVIATIONS` dict in `prediction_market_matching.py` (read the dict, loop through, look up team by name, register abbreviation)

Register the task in `tasks/__init__.py`:
```python
@celery_app.task(bind=True, name="app.tasks.backfill_team_identities")
def backfill_team_identities(self):
    from app.tasks.team_identity_backfill import _backfill_team_identities
    return run_async(_backfill_team_identities())
```

---

## STEP 6: Add admin endpoints

In `backend/app/routes/admin.py`, add:
```
GET  /api/admin/team-identity/status       — Count mappings by source, unmapped teams count
POST /api/admin/team-identity/backfill     — Trigger backfill task
GET  /api/admin/team-identity/search?q=... — Search mappings across all sources
GET  /api/admin/team-identity/team/{id}    — All mappings for a specific team
GET  /api/admin/team-identity/unmapped     — Teams with no mappings
```

Register in `routes/__init__.py` and `main.py` if needed.

---

## STEP 7: Write tests

Create `backend/tests/test_team_identity.py` (~40-50 tests):

These should be **unit tests with mocked/in-memory data**, matching the existing test patterns in the project (no live database needed):

- `normalize_name` handles accents, apostrophes, case
- `resolve_team` by source_id (exact match)
- `resolve_team` by source_name (exact match)
- `resolve_team` by source_name (fuzzy: "Lakers" → "Los Angeles Lakers")
- `resolve_team` returns None for unknown teams
- `resolve_team` respects sport_key scoping
- `register_team_identity` creates new mapping
- `register_team_identity` upserts on conflict (no crash)
- `resolve_from_kalshi_ticker` parses and resolves both teams
- Short name (<4 chars) requires exact match
- Multiple candidates: best match wins

Look at existing test files (e.g., `test_team_linking.py`, `test_prediction_market_matching.py`) for the project's test patterns.

---

## STEP 8: Run tests and verify

```bash
cd backend && python -m pytest tests/test_team_identity.py -v
cd backend && python -m pytest tests/ -v 2>&1 | tee /tmp/phase2-test-results.txt
```

All existing tests must still pass. If any break because of the new model columns, update them minimally (add `statpal_fixture_id=None` to test constructors if needed).

---

## STEP 9: Update statpal_sync.py helpers (minimal)

Update `_get_statpal_id()` and `_set_statpal_id()` in `statpal_sync.py` to use the new proper column instead of JSONB:

```python
def _get_statpal_id(event) -> Optional[str]:
    return event.statpal_fixture_id

def _set_statpal_id(event, fixture_id: str):
    event.statpal_fixture_id = fixture_id
```

Keep writing to the JSONB as well for now (belt and suspenders during migration):
```python
def _set_statpal_id(event, fixture_id: str):
    event.statpal_fixture_id = fixture_id
    # Also write to JSONB for backward compatibility during migration
    sources = event.win_probability_sources or {}
    sources["statpal_fixture_id"] = fixture_id
    event.win_probability_sources = sources
```

Same for `statpal_end_time` — write to both the new column and JSONB.

---

## STEP 10: Commit

```bash
git add backend/alembic/versions/add_team_identity.py
git add backend/app/models/models.py
git add backend/app/services/team_identity.py
git add backend/app/tasks/team_identity_backfill.py
git add backend/app/tasks/__init__.py
git add backend/app/tasks/statpal_sync.py
git add backend/app/routes/admin.py
git add backend/tests/test_team_identity.py
# Add any other modified files
git commit -m "Add team identity mapping infrastructure

New team_identity_mapping table for cross-source team resolution,
TeamIdentityService with 5-step resolution (exact ID -> exact name ->
fuzzy name -> alt names -> None), backfill task from existing data,
admin endpoints. Dedicated statpal_fixture_id/statpal_end_time/
commence_time_source columns on Event. No consumer changes yet.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

Do NOT push yet — we'll push after verifying Phase 3.

---

## WHAT NOT TO CHANGE

- Do NOT change any existing consumer code (espn_sync, prediction_market_matching, team_linking, events.py) — that's Phase 4
- Do NOT change the event discovery flow (sports.py) — that's Phase 3
- Do NOT change the frontend
- Do NOT remove existing fuzzy matching functions — the service wraps them, it doesn't replace them
- Do NOT change Pulse, highlights, odds math, or any computation modules
