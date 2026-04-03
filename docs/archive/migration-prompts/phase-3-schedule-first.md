# Phase 3: StatPal Schedule-First Event Creation

**Estimated time: 1.5-2.5 hours. This is the riskiest phase — the core behavioral change.**

**Prerequisites: Phase 1 (sport_keys.py) and Phase 2 (team identity) must be committed.**

Read `CLAUDE.md` first. Then read:
- `backend/app/tasks/sports.py` — current event discovery (how Odds API creates events)
- `backend/app/tasks/statpal_sync.py` — current StatPal sync (enrichment only, doesn't create events)
- `backend/app/tasks/odds_polling.py` — how odds get attached to events
- `backend/app/tasks/__init__.py` — beat schedule (task timing)
- `backend/app/models/models.py` — Event model (especially `external_id` unique constraint)
- `backend/app/services/team_identity.py` — TeamIdentityService from Phase 2

---

## CONTEXT: THE KEY ARCHITECTURAL CHANGE

Currently:
1. Odds API `discover_events` runs every 15 min at `:00/:15/:30/:45` → creates Event records with `external_id` (Odds API ID)
2. StatPal `sync_statpal_schedules` runs hourly at `:00` → finds existing Events, enriches them

After this phase:
1. StatPal `sync_statpal_schedules` runs hourly at `:00` → creates Event records for fixtures that don't exist yet, with `statpal_fixture_id` set, `commence_time_source="statpal"`, but `external_id=NULL`
2. Odds API `discover_events` runs every 15 min → when it finds an event, it first tries to match to an existing StatPal-created event by (sport + teams + time), and if matched, fills in `external_id` on the existing record instead of creating a duplicate

**The critical invariant: `external_id` is currently `UNIQUE NOT NULL` on events. We need to make it nullable** so StatPal-created events can exist before Odds API discovers them. This requires an Alembic migration.

---

## STEP 1: Alembic migration — make external_id nullable

Create `backend/alembic/versions/nullable_external_id.py`:

```python
"""Make Event.external_id nullable for StatPal-first event creation."""
revision = "nullable_external_id"  # <=32 chars
down_revision = "add_team_identity"  # Phase 2 migration
```

Changes:
- `ALTER TABLE events ALTER COLUMN external_id DROP NOT NULL`
- Keep the UNIQUE constraint (nullable unique is fine in PostgreSQL — multiple NULLs are allowed)
- Add a partial unique index on `statpal_fixture_id` WHERE NOT NULL for fast lookups

Update `models.py`:
```python
external_id: Mapped[Optional[str]] = mapped_column(String(100), unique=True)  # Now Optional
```

**Note:** The existing `unique=True` constraint on a nullable column means multiple rows can have NULL, but non-NULL values must be unique. This is exactly what we want — StatPal events start with NULL, Odds API fills it in later.

---

## STEP 2: Modify StatPal schedule sync to CREATE events

In `backend/app/tasks/statpal_sync.py`, modify `_sync_statpal_schedules()`:

**Current behavior (line ~107):** When `_find_matching_event()` returns `None`, it skips the fixture with `continue`.

**New behavior:** When no matching event exists, create one:

```python
if not event:
    # NEW: Create event from StatPal fixture
    event = Event(
        sport_id=sport_id,
        external_id=None,  # Will be filled by Odds API later
        home_team_name=fixture.home_team,
        away_team_name=fixture.away_team,
        commence_time=fixture.start_time,
        commence_time_source="statpal",
        statpal_fixture_id=fixture.fixture_id,
        status="scheduled",
    )
    session.add(event)
    await session.flush()  # Get the ID
    total_created += 1

    # Register team identities
    service = TeamIdentityService()
    home_team = await service.resolve_team(
        session, "statpal", our_key, source_name=fixture.home_team
    )
    away_team = await service.resolve_team(
        session, "statpal", our_key, source_name=fixture.away_team
    )
    if home_team:
        event.home_team_id = home_team.id
    if away_team:
        event.away_team_id = away_team.id
    continue  # Skip the enrichment logic below since we just created it
```

**Guard rails on event creation:**
- Only create events for sports in `STATPAL_SPORT_MAPPING` (already ensured by the loop)
- Only create if `fixture.start_time` is in the future (don't create events for past games)
- Only create if `fixture.home_team` and `fixture.away_team` are non-empty (already checked)
- Set `commence_time_source="statpal"` so other systems know where the time came from
- Log every creation clearly: `logger.info(f"StatPal: created new event for {fixture.home_team} vs {fixture.away_team} at {fixture.start_time}")`

**Also update the existing enrichment path** so it sets `commence_time_source`:

When StatPal corrects a commence_time on an existing event (the diff > 300 block), also set:
```python
event.commence_time_source = "statpal"
```

---

## STEP 3: Modify event discovery to match StatPal-created events

In `backend/app/tasks/sports.py`, modify `_discover_events()`:

**Current behavior (line ~104):** Uses `INSERT ... ON CONFLICT(external_id) DO UPDATE` to upsert events. This won't match StatPal-created events because they have `external_id=NULL`.

**New behavior:** Before the upsert, check if a StatPal-created event already exists for this matchup:

```python
for event_data in events_data:
    commence_time = datetime.fromisoformat(
        event_data["commence_time"].replace("Z", "+00:00")
    )

    # NEW: Check for existing StatPal-created event (no external_id yet)
    existing_event = await _find_statpal_event_for_odds_api(
        session, sport.id, event_data["home_team"], event_data["away_team"],
        commence_time
    )

    if existing_event:
        # Attach Odds API data to existing StatPal-created event
        existing_event.external_id = event_data["id"]
        if not existing_event.commence_time_source or existing_event.commence_time_source != "statpal":
            existing_event.commence_time = commence_time
        # Don't overwrite team names if they're already set
        event_id = existing_event.id
        logger.info(
            f"Odds API: attached to StatPal event {event_id} "
            f"({event_data['home_team']} vs {event_data['away_team']})"
        )
    else:
        # Normal upsert (existing behavior)
        stmt = insert(Event).values(
            external_id=event_data["id"],
            # ... (keep existing upsert logic unchanged)
        ).on_conflict_do_update(
            index_elements=["external_id"],
            set_={...}  # Keep existing
        ).returning(Event.id)
        result = await session.execute(stmt)
        event_id = result.scalar_one()

    total_events += 1
    # ... rest of the loop (snapshots, team creation) stays the same
```

**The matching function `_find_statpal_event_for_odds_api()`:**

```python
async def _find_statpal_event_for_odds_api(
    session, sport_id: int, home_team: str, away_team: str,
    commence_time: datetime
) -> Optional[Event]:
    """Find a StatPal-created event that matches an Odds API event.

    Only matches events that:
    1. Have no external_id (StatPal-created, not yet linked to Odds API)
    2. Are in the same sport
    3. Have matching team names (fuzzy)
    4. Are within 6 hours of the Odds API commence_time
    """
    window = timedelta(hours=6)
    result = await session.execute(
        select(Event).where(
            Event.sport_id == sport_id,
            Event.external_id.is_(None),  # Only StatPal-created events
            Event.commence_time.between(commence_time - window, commence_time + window),
        ).limit(20)
    )
    candidates = result.scalars().all()

    for candidate in candidates:
        # Both teams must match (using normalize_name from team_identity)
        from app.services.team_identity import normalize_name
        home_match = (
            normalize_name(home_team) in normalize_name(candidate.home_team_name) or
            normalize_name(candidate.home_team_name) in normalize_name(home_team) or
            normalize_name(home_team).split()[-1] == normalize_name(candidate.home_team_name).split()[-1]
        )
        away_match = (
            normalize_name(away_team) in normalize_name(candidate.away_team_name) or
            normalize_name(candidate.away_team_name) in normalize_name(away_team) or
            normalize_name(away_team).split()[-1] == normalize_name(candidate.away_team_name).split()[-1]
        )
        if home_match and away_match:
            return candidate

    return None
```

**Important edge case:** Home/away might be swapped between StatPal and Odds API. Also check the reverse:
```python
if home_match and away_match:
    return candidate
# Also check swapped home/away
home_as_away = (normalize_name(home_team) matches candidate.away_team_name)
away_as_home = (normalize_name(away_team) matches candidate.home_team_name)
if home_as_away and away_as_home:
    # Swap is fine — same game, different home/away assignment
    return candidate
```

---

## STEP 4: Protect commence_time from overwrite

In `backend/app/tasks/espn_sync.py`, find where ESPN updates `commence_time` on events. Add a guard:

```python
# Don't overwrite StatPal commence_time — it's more reliable
if event.commence_time_source == "statpal":
    pass  # Keep StatPal's time
else:
    event.commence_time = espn_commence_time
    event.commence_time_source = "espn"
```

In `backend/app/tasks/sports.py` event discovery, the existing comment says "Don't overwrite commence_time" — verify that the ON CONFLICT DO UPDATE set_ doesn't include commence_time. (Looking at the code, it correctly does NOT update commence_time on conflict. Good.)

---

## STEP 5: Adjust beat schedule timing

In `backend/app/tasks/__init__.py`, verify/adjust timing:

- `sync-statpal-schedules` should run at `:00` (currently already does — hourly at `:00`)
- `discover-events` should run at `:05` (currently every 15 min — change to `:05/:20/:35/:50` or keep as-is, just ensure it runs AFTER StatPal)

The key is that StatPal schedule sync runs before event discovery. Since StatPal is hourly at `:00` and event discovery is every 15 min, the `:00` run of event discovery might race with StatPal. Options:
- **Option A (simple):** Offset event discovery to `:05/:20/:35/:50` to give StatPal 5 min
- **Option B (no change):** Keep current timing. If they race, the worst case is one Odds API cycle creates a duplicate that gets deduped on the next cycle. Not ideal but not catastrophic.

Go with **Option A** — offset event discovery by 5 minutes. Update the beat schedule entry.

---

## STEP 6: Handle events that StatPal creates but Odds API never discovers

Some StatPal fixtures might not appear in The Odds API (minor leagues, or timing mismatches). These events will have `external_id=NULL` forever. This is fine because:

- They still appear in the feed if they meet threshold scores
- They won't have odds data (no bookmaker snapshots), so they'll score low in highlights and feed ranking
- The feed already handles events without odds data (skips them in anonymous feed)

**Add a cleanup task** (optional, can be a future improvement): mark events with `external_id=NULL` and `commence_time` > 24h in the past as `status="closed"`. But don't build this now — it's not urgent.

**Add a feed guard:** In `backend/app/routes/feed.py`, ensure events without ANY odds data (no odds_snapshots) don't surface in the anonymous feed. Check if this guard already exists (it likely does based on the CLAUDE.md note "Events without odds data skipped in feed").

---

## STEP 7: Write tests

Create `backend/tests/test_schedule_first.py` (~20-25 tests):

1. **StatPal creates event when no match exists** — fixture with no matching event → new Event with external_id=None
2. **StatPal doesn't create duplicates** — fixture matches existing event → enriches, doesn't create
3. **Odds API attaches to StatPal-created event** — `_find_statpal_event_for_odds_api` finds the right event
4. **Odds API attaches with swapped home/away** — same game, different home/away → still matches
5. **Odds API creates new event when no StatPal match** — normal upsert path still works
6. **commence_time_source is set correctly** — "statpal" when StatPal creates/corrects, "espn" when ESPN corrects, "odds_api" when Odds API creates
7. **ESPN doesn't overwrite StatPal commence_time** — event with `commence_time_source="statpal"` keeps its time
8. **StatPal doesn't create past events** — fixture with start_time in the past → skipped
9. **Matching requires both teams** — one team match is not enough
10. **Time window respects 6h boundary** — fixtures >6h apart don't match

These should be unit tests with mocked sessions, following existing test patterns.

---

## STEP 8: Run full test suite

```bash
cd backend && python -m pytest tests/ -v 2>&1 | tee /tmp/phase3-test-results.txt
```

**Critical check:** Search the test output for any failures related to:
- `external_id` being required (now it's nullable — any test that constructs Events with `external_id` must still work, but tests that assume non-null external_id on all events need review)
- Event queries that filter by `external_id IS NOT NULL` (should be fine, but check)

---

## STEP 9: Commit and push all three phases

```bash
git add -A  # Stage all Phase 3 changes
git commit -m "StatPal schedule-first event creation

StatPal sync now creates Event records for fixtures that don't exist yet.
Odds API event discovery attaches to these records when it finds a match.
Event.external_id is now nullable (StatPal events start without an Odds API ID).
commence_time_source column tracks which system set the time.
ESPN sync respects StatPal commence_time authority.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"

# Now push all three phases together
git push -u origin HEAD
```

---

## WHAT NOT TO CHANGE

- Do NOT change existing consumer code yet (prediction market matching, related futures, etc.) — Phase 4
- Do NOT change the frontend — it uses database IDs for URLs, not external_id, so nullable external_id is invisible to the frontend
- Do NOT change Pulse, highlights, odds math
- Do NOT remove the UNIQUE constraint on external_id — just make it nullable
- Do NOT change odds_polling.py (how odds snapshots are written) — snapshots are keyed by event_id (database PK), not external_id, so they work regardless

## ROLLBACK PLAN

If something goes wrong in production:
1. The Alembic migration has a downgrade path
2. StatPal event creation can be disabled by removing the `if not event: create` block
3. The Odds API upsert path is unchanged — events it creates still work exactly as before
4. The matching function in event discovery adds a new code path before the existing upsert, so removing it restores original behavior
