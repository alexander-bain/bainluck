# Phase 4: Migrate Consumers to TeamIdentityService

**Estimated time: 1.5-2 hours. Methodical one-file-at-a-time consumer migration.**

**Prerequisites: Phases 1-3 must be committed and passing all tests.**

Read `CLAUDE.md` first. Then read:
- `backend/app/services/team_identity.py` — The TeamIdentityService from Phase 2
- `backend/app/utils/sport_keys.py` — Sport key module from Phase 1

---

## TASK

Update each consumer of team matching to use `TeamIdentityService` instead of bespoke matching. Do this ONE FILE AT A TIME. Run the full test suite after each file. If any test breaks for a non-trivial reason, stop and fix before moving on.

**Key principle: The TeamIdentityService SUPPLEMENTS fuzzy matching — it doesn't replace it entirely.** Every consumer should try the service first (fast indexed lookup), then fall back to existing fuzzy matching for teams not yet in the mapping table. Over time, as the mapping table fills up, the fuzzy matching path will be hit less and less.

---

## MIGRATION ORDER (least risky → most risky)

### Consumer 1: `tasks/espn_sync.py`

**Current behavior:** Has a local `names_match()` function and 3-signal matching (ESPN ID → name → commence_time proximity) for linking ESPN team data to our Team records.

**Change:**
1. At the top of the ESPN sync function, resolve teams via `TeamIdentityService`:
```python
service = TeamIdentityService()
team = await service.resolve_team(
    session, "espn", sport_key,
    source_id=espn_team_id,       # ESPN team ID from the scoreboard
    source_name=espn_display_name, # ESPN display name
)
```
2. If `resolve_team` returns a Team, use it directly. If it returns None, fall back to the existing 3-signal matching.
3. On successful match (either path), register the identity:
```python
await service.register_team_identity(
    session, team.id, "espn", sport_key,
    source_id=str(espn_team_id),
    source_name=espn_display_name,
)
```
4. **Keep the existing `names_match()` function** as the fallback. Don't delete it.

**Run tests:**
```bash
cd backend && python -m pytest tests/test_espn_api.py tests/test_team_identity.py -v
cd backend && python -m pytest tests/ -v --tb=short -x 2>&1 | tail -30
```

---

### Consumer 2: `tasks/statpal_sync.py`

**Current behavior:** `_find_matching_event()` uses team name matching + time proximity.

**Change:**
1. In `_sync_statpal_schedules()`, before calling `_find_matching_event()`, try a direct lookup by `statpal_fixture_id`:
```python
# Primary: lookup by StatPal fixture ID (fast, exact)
if fixture.fixture_id:
    event = await session.execute(
        select(Event).where(Event.statpal_fixture_id == fixture.fixture_id)
    )
    event = event.scalar_one_or_none()

# Fallback: existing fuzzy matching
if not event:
    event = await _find_matching_event(session, Event, sport_id, fixture)
```
2. When a match is found, register team identities:
```python
if event and fixture.home_team:
    service = TeamIdentityService()
    home = await service.resolve_team(session, "statpal", our_key, source_name=fixture.home_team)
    if home:
        await service.register_team_identity(session, home.id, "statpal", our_key, source_name=fixture.home_team)
```
3. **Keep `_find_matching_event()`** as the fallback. Don't delete it.

**Run tests:**
```bash
cd backend && python -m pytest tests/test_statpal_api.py tests/test_team_identity.py -v
cd backend && python -m pytest tests/ -v --tb=short -x 2>&1 | tail -30
```

---

### Consumer 3: `tasks/sports.py` (event discovery)

**Current behavior:** Auto-creates Team records when Odds API discovers events with unknown teams.

**Change:** After auto-creating a Team, register its Odds API identity:
```python
for team_name in new_team_names:
    new_team = Team(name=team_name, sport_id=sport.id)
    session.add(new_team)
    await session.flush()  # Get the ID

    # Register Odds API identity
    service = TeamIdentityService()
    await service.register_team_identity(
        session, new_team.id, "odds_api", sport_key,
        source_name=team_name,
    )
```

Also: when the existing upsert attaches an Odds API external_id to a StatPal-created event (from Phase 3), register both team identities:
```python
if existing_event:
    # ... (existing code from Phase 3)
    # Register Odds API team names
    # Note: sport.key IS the internal format (e.g., "basketball_nba") from the Sport model
    service = TeamIdentityService()
    for name in [event_data["home_team"], event_data["away_team"]]:
        team = await service.resolve_team(session, "odds_api", sport.key, source_name=name)
        if team:
            await service.register_team_identity(session, team.id, "odds_api", sport.key, source_name=name)
```

**Run tests:**
```bash
cd backend && python -m pytest tests/ -v --tb=short -x 2>&1 | tail -30
```

---

### Consumer 4: `tasks/roster_sync.py`

**Current behavior:** Matches ESPN/MLB API teams to DB teams using abbreviation lookups and name matching.

**Change:** Before the existing matching logic, try TeamIdentityService:
```python
service = TeamIdentityService()
team = await service.resolve_team(
    session, "espn", sport_key,
    source_id=str(espn_team_id),
    source_name=espn_team_name,
)
if not team:
    # Fall back to existing abbreviation/name matching
    team = existing_matching_logic(...)
if team:
    await service.register_team_identity(session, team.id, "espn", sport_key, source_id=str(espn_team_id), source_name=espn_team_name)
```

**Run tests:**
```bash
cd backend && python -m pytest tests/ -v --tb=short -x 2>&1 | tail -30
```

---

### Consumer 5: `tasks/prediction_market_matching.py`

**This is the most complex consumer. Be careful.**

**Current behavior:** `_score_candidates()` does fuzzy team name matching against events. `extract_teams_from_ticker()` parses Kalshi ticker abbreviations. Both-teams matching gate, sport category scoring, etc.

**Change — minimal and surgical:**
1. In `_score_candidates()`, before the existing fuzzy scoring loop, try a TeamIdentityService lookup:
```python
# Try identity service first (fast indexed lookup)
service = TeamIdentityService()
if market.source == "kalshi" and is_kalshi_game_ticker(market.external_id):
    home_team, away_team = await service.resolve_from_kalshi_ticker(session, market.external_id)
    if home_team and away_team:
        # Find event with these teams
        for event in candidates:
            if (event.home_team_id == home_team.id and event.away_team_id == away_team.id) or \
               (event.home_team_id == away_team.id and event.away_team_id == home_team.id):
                return event, 100  # Perfect match via identity service
```
2. **Keep ALL existing matching logic as fallback.** The regex detection layer (prop detection, matchup extraction, ticker parsing) stays untouched. The fuzzy `_score_candidates` logic stays. The only change is adding an indexed-lookup fast path before the fuzzy path.
3. On successful match (either path), register abbreviations:
```python
# After successful ticker-based match
if matched_home_abbrev:
    await service.register_team_identity(
        session, matched_event.home_team_id, "kalshi", sport_key,
        source_abbreviation=matched_home_abbrev,
    )
```

**Do NOT refactor the detection layer** (`is_game_level_market`, `extract_matchup_from_name`, etc.). Those detect WHETHER something is a game market. The TeamIdentityService only helps with WHO the teams are.

**Run tests:**
```bash
cd backend && python -m pytest tests/test_prediction_market_matching.py -v
cd backend && python -m pytest tests/ -v --tb=short -x 2>&1 | tail -30
```

**This is the most likely place for regressions.** If any of the 291 prediction market matching tests fail for a non-trivial reason, investigate carefully. The fast path should only HELP (returning a match faster), never change the outcome of the existing logic.

---

### Consumer 6: `tasks/team_linking.py`

**Current behavior:** `match_outcome_to_team()` links FuturesOutcome names to Team records using substring matching.

**Change:** Before substring matching, check if the outcome name resolves via the identity service:
```python
service = TeamIdentityService()
# Try all sources — the outcome name might match a Kalshi name, ESPN name, etc.
team = await service.resolve_team(
    session, "odds_api", sport_key, source_name=outcome_name
)
if not team:
    # Fall back to existing substring matching
    team = existing_logic(...)
```

**Run tests:**
```bash
cd backend && python -m pytest tests/test_team_linking.py -v
cd backend && python -m pytest tests/ -v --tb=short -x 2>&1 | tail -30
```

---

### Consumer 7: `routes/events.py` related-futures

**Current behavior:** Uses ILIKE queries against FuturesOutcome.name with team name patterns.

**Change — minimal for now:** Add a supplementary query path that joins through `team_identity_mapping`:
```python
# Primary: existing ILIKE matching (still needed for outcomes not in mapping table)
# Supplementary: join through team_identity_mapping for better coverage
```

This is the lowest-priority consumer change. The ILIKE queries work well and have good coverage. The identity service mainly helps with edge cases where team names don't match across systems. **If you're running low on time, skip this one — it can be done later.**

---

## FINAL: Run full test suite

```bash
cd backend && python -m pytest tests/ -v 2>&1 | tee /tmp/phase4-test-results.txt
cd frontend && npx jest 2>&1 | tee /tmp/phase4-frontend-results.txt
```

Count the total tests. It should be >= 1613 (existing) + ~70-80 (new from Phases 1-3) + any new integration tests you added.

---

## COMMIT AND PUSH

```bash
git add -A
git commit -m "Migrate consumers to TeamIdentityService

ESPN sync, StatPal sync, event discovery, roster sync, prediction market
matching, and team linking now try TeamIdentityService (indexed lookup)
before falling back to existing fuzzy matching. Each consumer registers
new identities on successful match, building the mapping table over time.
All existing matching logic preserved as fallback.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"

git push
```

---

## WHAT NOT TO CHANGE

- Do NOT remove any existing fuzzy matching functions — they are fallbacks
- Do NOT change the prediction market DETECTION layer (regex, ticker parsing) — only the team RESOLUTION step
- Do NOT change the frontend
- Do NOT change Pulse, highlights, odds math, feed ranking
- Do NOT change the Alembic schema (that was Phase 2-3)

---

## POST-MIGRATION VERIFICATION

After deploying all 4 phases, verify the system is healthy:

```bash
# Check team identity mapping population
curl "https://api.bainluck.com/api/admin/team-identity/status?secret=any"

# Trigger a backfill to populate from existing data
curl -X POST "https://api.bainluck.com/api/admin/team-identity/backfill?secret=any"

# Check for unmapped teams
curl "https://api.bainluck.com/api/admin/team-identity/unmapped?secret=any"

# Verify StatPal schedule sync creates events
curl -X POST "https://api.bainluck.com/api/admin/statpal/sync-schedules?secret=any"

# Check Celery task dashboard for any failures
curl "https://api.bainluck.com/api/admin/celery/dashboard?secret=any"

# Verify the feed still loads
curl "https://api.bainluck.com/api/feed" | python -m json.tool | head -50
```

---

## UPDATING CLAUDE.md

After all 4 phases are deployed and verified, update CLAUDE.md to document:
1. The new `team_identity_mapping` table in the schema section
2. `sport_keys.py` in the project structure and key files
3. `TeamIdentityService` in the key files and services section
4. The schedule-first architecture (StatPal creates → Odds API attaches)
5. `commence_time_source` in the Event model description
6. New admin endpoints in the admin section
7. Update the "Development Process & Lessons Learned" section with any gotchas discovered during migration
