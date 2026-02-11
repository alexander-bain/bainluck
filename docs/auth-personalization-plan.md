# Authentication & Personalization Implementation Plan

## Overview

Add Google OAuth login, structured onboarding, and personalized event ranking to OddsTracker. The app remains fully functional without login; auth unlocks personalization.

**Auth provider:** Firebase Auth (Google Sign-In first, Apple later)
**Onboarding:** 4 structured screens, all skippable
**Personalization:** Highlight score multiplier based on user preferences

---

## Phase 1: Auth Foundation

### Backend

1. **Firebase Admin SDK initialization** (`app/services/firebase_auth.py`)
   - Initialize from `FIREBASE_SERVICE_ACCOUNT_JSON` env var (Heroku config var)
   - Fallback: `FIREBASE_PROJECT_ID` only (for dev/token verification without full credentials)
   - Skip initialization if neither is set (auth disabled, all endpoints work anonymously)

2. **Auth dependencies** (`app/dependencies/auth.py`)
   - `get_current_user(token)` — verifies Firebase ID token, returns User or 401
   - `get_optional_user(token)` — returns User if token present, None if not (for mixed endpoints)
   - Both resolve `firebase_uid` → User record in database

3. **Auth routes** (`app/routes/auth.py`)
   - `POST /api/auth/google` — verify Firebase ID token, upsert user, return profile
   - `GET /api/me` — get current user profile + preferences
   - `PATCH /api/me` — update display name
   - `DELETE /api/me` — delete account + all associated data

4. **Pin sync routes** (`app/routes/user.py`)
   - `GET /api/me/pins` — get all pinned event + futures IDs
   - `PUT /api/me/pins` — bulk upsert pins (for localStorage migration)
   - `POST /api/me/pins` — add a pin
   - `DELETE /api/me/pins/{pin_type}/{target_id}` — remove a pin

5. **Database changes**
   - New table: `user_preferences` (home_location, sport_affinities, onboarding state)
   - New table: `user_pins` (replaces localStorage for authenticated users)
   - Extend `user_favorites`: add `relationship`, `source`, `weight` columns
   - Extend `teams`: add `location` column (from ESPN's `location` field)

6. **ESPN location parsing**
   - Add `location: Optional[str]` to `ESPNTeam` dataclass
   - Parse `team.get("location")` in `_parse_team()`
   - Store on Team model during ESPN sync

### Frontend

7. **Firebase JS SDK setup** (`lib/firebase.ts`)
   - Initialize Firebase app from `NEXT_PUBLIC_FIREBASE_*` env vars
   - Export auth instance

8. **Auth hook** (`hooks/useAuth.ts`)
   - Wrap `onAuthStateChanged` for reactive auth state
   - `getIdToken()` for API calls
   - `signInWithGoogle()`, `signOut()` methods
   - Expose: `user`, `isLoading`, `isAuthenticated`

9. **Auth context** (`components/AuthProvider.tsx`)
   - Wrap app in auth context (inside AnalyticsProvider)
   - Wire `setUser(uid)` to analytics on login/logout

10. **Sign-in UI**
    - Header: subtle "Sign in" text button (not a modal by default)
    - Sign-in page (`/signin`): Google button, value proposition, skip link
    - User avatar/menu in header when authenticated (avatar, "Preferences", "Sign out")

11. **API client auth** (`lib/api.ts`)
    - Attach `Authorization: Bearer <token>` header when user is authenticated
    - New functions: `fetchUserPins()`, `syncPins()`, `addPin()`, `removePin()`

12. **Pin migration** (update `usePinnedEvents.ts` / `usePinnedFutures.ts`)
    - When user logs in: read localStorage pins → POST to backend → clear localStorage
    - When authenticated: read/write pins via API instead of localStorage
    - When not authenticated: fall back to localStorage (current behavior)

---

## Phase 2: Onboarding (future session)

### Screen 1: "Where do you follow sports?"
- Text input with city autocomplete
- City → teams lookup via `teams` table (using new `location` column)
- Metro alias mapping (~25 entries) for "New England" → "Boston" etc.
- Show local teams as toggleable chips (all on by default, user subtracts)

### Screen 2: "Any alma maters?"
- Multi-entry text field with school autocomplete (from teams table, college sports)
- "Also rooting for" free text field
- Resolve to college teams across all sports

### Screen 3: "What sports do you care about?"
- Grid of sport cards with dropdown per sport
- Options: Always (1.0), Playoffs only (0.3), Only if wild (0.1), Not interested (0.0)
- Defaults: top-4 US sports = Always, everything else = Not interested

### Screen 4: "Any rivals?" (optional)
- Team autocomplete (same as favorites)
- Stored as relationship='rival'
- Surfaced when rival is losing as favorite (upset) or has lost

### Data flow
- Raw text inputs stored in `user_preferences.onboarding_raw` (JSONB)
- Parsed preferences stored in `user_preferences.sport_affinities` (JSONB)
- Team relationships stored in `user_team_relationships` rows
- LLM fallback (GPT-4o-mini) for unresolved free-text team names

---

## Phase 3: Personalized Feed (future session)

### Personalization multiplier
Applied on top of existing `compute_highlight()` base score:

```python
final_score = base_highlight_score × relevance_multiplier
```

| Signal | Multiplier |
|--------|-----------|
| User follows team in event | 1.5x |
| Rival losing / upset brewing | 1.5x |
| Local team | 1.3x |
| Alma mater team | 1.3x |
| High-affinity sport (weight > 0.5) | 1.2x |
| Low-affinity sport (weight < 0.2) | 0.5x |
| Conditional sport + condition NOT met | 0.3x |

### "For You" section
- Replaces "Highlights" for logged-in users with preferences
- Same EventCards, different sort order based on multiplied scores
- Anonymous users see current generic Highlights
- Subtle CTA: "Personalize your feed" for anonymous users

---

## Phase 4: Apple Sign-In + Polish (future session)

- Apple Developer Service ID configuration
- Firebase Apple provider setup
- Frontend Apple Sign-In button (required by App Store if Google Sign-In is offered)
- Settings/preferences page for editing onboarding responses
- "Manage account" page (change display name, delete account)
- Change Firebase support email from personal email to support@bainluck.com (after domain setup)
- Link Firebase project to Google Analytics for cross-platform reporting (web + iOS)

---

## Database Schema Changes

### New: `user_preferences`
```sql
CREATE TABLE user_preferences (
    id SERIAL PRIMARY KEY,
    user_id INTEGER UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    home_location VARCHAR(100),
    sport_affinities JSONB DEFAULT '{}',
    onboarding_completed BOOLEAN DEFAULT false,
    onboarding_raw JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### New: `user_pins`
```sql
CREATE TABLE user_pins (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    pin_type VARCHAR(20) NOT NULL,  -- 'event' or 'future'
    target_id INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, pin_type, target_id)
);
```

### Extend: `user_favorites`
```sql
ALTER TABLE user_favorites
    ADD COLUMN relationship VARCHAR(20) DEFAULT 'follow',
    ADD COLUMN source VARCHAR(20) DEFAULT 'manual',
    ADD COLUMN weight NUMERIC(3,2) DEFAULT 1.00;
```

### Extend: `teams`
```sql
ALTER TABLE teams ADD COLUMN location VARCHAR(100);
```

---

## City → Teams Mapping Strategy

**Source:** ESPN's `location` field on team objects (already returned by the API we call).

ESPN splits team names into `location` + `name`:
- "Boston" + "Celtics" → `location = "Boston"`
- "Golden State" + "Warriors" → `location = "Golden State"`
- "Duke" + "Blue Devils" → `location = "Duke"`

**Metro alias mapping** (~25 static entries) groups brand names into metro areas:
```python
METRO_ALIASES = {
    "Golden State": "Bay Area",
    "New England": "Boston",
    "Brooklyn": "New York",
    "Carolina": "Charlotte",
    "Tampa Bay": "Tampa",
    # ... ~20 more
}
```

**Implementation:** Query `teams` table WHERE `location` matches user's city or metro aliases. No external API needed.

---

## Future Personalization Ideas (to add to PRD)

| Idea | Complexity | When |
|------|-----------|------|
| Rival schadenfreude labels ("Yankees losing 8-2") | Low | Phase 3 |
| Conditional sport logic (baseball in October) | Low | Phase 3 |
| Learn from clicks (implicit preference signals) | High | After GA4 data |
| Personalized push notifications | High | After iOS app |
| Personalized search result ranking | Low | After base personalization |
| "What you missed" digest (Team Insights PRD Phase 15) | Medium | After base personalization |
| Re-process onboarding when sports/sources added | Low | Ongoing |
| Personalized Pulse Hall of Fame filtering | Low | Much later |
| Sport-specific "For You" page | Medium | After feed proves out |

---

## Environment Variables Needed

### Backend (Heroku)
- `FIREBASE_PROJECT_ID` — Firebase project ID
- `FIREBASE_SERVICE_ACCOUNT_JSON` — (optional) Full service account JSON for admin operations

### Frontend (Vercel)
- `NEXT_PUBLIC_FIREBASE_API_KEY`
- `NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN`
- `NEXT_PUBLIC_FIREBASE_PROJECT_ID`
