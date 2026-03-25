# StatPal API Audit: Available vs. Used Endpoints

**Date:** 2026-03-25
**Source:** [StatPal Coverage Page](https://statpal.io/coverage/), [Quick Start Guide](https://statpal.io/quick-start-tutorial/), and codebase analysis

---

## Executive Summary

We pay ~$99/mo for StatPal and use it for **schedules, injuries, play-by-play, rosters, standings, and team stats**. However, we are **not using** several valuable endpoints: **livescores** (as a dedicated real-time feed), **pre-game odds**, **live match stats**, **results**, and **scoring leaders**. The biggest gap is **livescores** -- StatPal updates every 15 seconds across all 13 sports, and we should be using it as our primary live game state source instead of relying on ESPN sync + odds polling side effects.

### Key Finding: Play-by-Play Availability

From tonight's live testing and docs analysis:

| Sport | Play-by-Play? | Notes |
|-------|:---:|-------|
| NFL | Yes | "Instantaneous updates on every play in real-time" -- the gold standard |
| NBA | No | Returns HTTP 404. Docs say "minute-by-minute updates" but this appears to be livescores, not PBP |
| MLB | No | Not explicitly mentioned in docs |
| NHL | No | Not mentioned |
| Soccer | Partial | "Live in-depth match stats" (goals, cards, subs) -- not true PBP |
| PGA | Yes | "Shot-by-shot updates" |
| F1 | Yes | "Real-time updates on race positions, lap times" |

**Bottom line:** True play-by-play is NFL-only (and golf/F1 for non-team sports). Our code tries PBP for all sports but silently 404s for NBA/NHL/MLB.

---

## Sports Coverage Matrix

### Sports We Map (STATPAL_SPORT_MAPPING)

| Our Sport Key | StatPal Sport | Currently Mapped? |
|---|---|:---:|
| `americanfootball_nfl` | `nfl` | Yes |
| `basketball_nba` | `nba` | Yes |
| `baseball_mlb` | `mlb` | Yes |
| `icehockey_nhl` | `nhl` | Yes |
| `soccer_epl` | `soccer` | Yes |
| `soccer_usa_mls` | `soccer` | Yes |
| `soccer_spain_la_liga` | `soccer` | Yes |
| `soccer_germany_bundesliga` | `soccer` | Yes |
| `soccer_italy_serie_a` | `soccer` | Yes |
| `soccer_france_ligue_one` | `soccer` | Yes |
| `soccer_uefa_champs_league` | `soccer` | Yes |
| `golf_pga` | `pga` | Yes |

### StatPal Sports We Do NOT Map

| StatPal Sport | Why Not Mapped | Should We? |
|---|---|---|
| Cricket | Not in our sport coverage | Low -- unless we expand to cricket |
| Esports | Not in our sport coverage | Low |
| Formula One | Not in our sport coverage | Medium -- F1 has passionate fans |
| Handball | Not in our sport coverage | Low |
| Horse Racing | Not in our sport coverage | Low |
| Tennis | We have `tennis_atp`/`tennis_wta` in Odds API but not in StatPal mapping | **Medium** -- could add livescores |
| Volleyball | Not in our sport coverage | Low |

---

## Endpoint-by-Endpoint Audit

### 1. Season Schedule / Fixtures

| Sport | Available? | Used? | Our Endpoint | Schedule | Notes |
|-------|:---:|:---:|---|---|---|
| NFL | Yes | Yes | `season-schedule` | Hourly (min 3) | Creates events, corrects commence_time |
| NBA | Yes | Yes | `season-schedule` | Hourly (min 0) | Same |
| MLB | Yes | Yes | `season-schedule` | Hourly (min 2) | Same |
| NHL | Yes | Yes | `season-schedule` | Hourly (min 1) | Same |
| Soccer | Yes | Yes | `matches/daily` (v2) | Not scheduled individually | Fetches offset=1,2 for upcoming |
| Golf | Yes | Yes | `schedule` | Via NFL/NBA schedule tasks | Tournament schedule |

**Status:** Fully utilized. This is a core strength of our StatPal integration.

---

### 2. Livescores

| Sport | Available? | Used? | How? | Notes |
|-------|:---:|:---:|---|---|
| NFL | Yes | Partially | Called in `_sync_statpal_schedules` to update scores | Not a dedicated live feed |
| NBA | Yes | Partially | Same -- called during hourly schedule sync | **Gap: should poll every 15-30s during live games** |
| MLB | Yes | Partially | Same | Same gap |
| NHL | Yes | Partially | Same | Same gap |
| Soccer | Yes | Partially | Same | Same gap |
| Golf | Yes | Partially | Same | Leaderboard updates |
| Cricket | Yes | No | Not mapped | -- |
| Esports | Yes | No | Not mapped | -- |
| F1 | Yes | No | Not mapped | -- |
| Handball | Yes | No | Not mapped | -- |
| Horse Racing | Yes | No | Not mapped | -- |
| Tennis | Yes | No | Not mapped | Could add for ATP/WTA |
| Volleyball | Yes | No | Not mapped | -- |

**Current usage:** `get_live_scores()` is called inside `_sync_statpal_schedules()` to get live game scores, but only during the **hourly** schedule sync. This means live score data is up to 60 minutes stale.

**Gap (HIGH PRIORITY):** We should create a dedicated `sync_statpal_livescores` task that runs every **15-30 seconds** for sports with live games. StatPal livescores update every 15 seconds and include:
- Current score
- Game status (period/quarter/inning)
- Clock/time
- Venue

This would replace/supplement our current reliance on ESPN sync (60s) and odds polling side effects for game state.

**What livescores returns** (from API exploration):
```json
{
  "id": "988739",
  "date": "25.03.2026",
  "time": "19:30",
  "status": "Q3",
  "venue": "TD Garden",
  "home": {"id": "2679", "name": "Boston Celtics", "totalscore": "78", "q1": "24", "q2": "31", "q3": "23"},
  "away": {"id": "2689", "name": "Miami Heat", "totalscore": "71", "q1": "18", "q2": "28", "q3": "25"}
}
```

---

### 3. Play-by-Play / Live Plays

| Sport | Available? | Used? | Endpoint | Notes |
|-------|:---:|:---:|---|---|
| NFL | Yes | Yes | `fixtures/{id}/playbyplay` | Every 60s for live games. Works well. |
| NBA | **No** | Attempted | `fixtures/{id}/playbyplay` | **Returns 404.** Docs misleading ("minute-by-minute" = livescores) |
| MLB | **No** | Attempted | `fixtures/{id}/playbyplay` | Returns 404. We use MLB Stats API for PBP instead. |
| NHL | **No** | Attempted | `fixtures/{id}/playbyplay` | Returns 404 |
| Soccer | Partial | Attempted | `fixtures/{id}/playbyplay` | May return match events (goals/cards) not true PBP |
| Golf | Yes | Not tested | `fixtures/{id}/playbyplay` | "Shot-by-shot updates" per docs |
| F1 | Yes | No | Not mapped | Lap times, positions |

**Status:** NFL works great. NBA/MLB/NHL silently fail (404s). Our code handles this gracefully (returns empty list), but it wastes API calls.

**Recommendation (MEDIUM):** Add a `STATPAL_PBP_SPORTS` set to skip PBP calls for sports that don't support it:
```python
STATPAL_PBP_SPORTS = {"nfl", "pga"}  # Only these support play-by-play
```

---

### 4. Pre-Game Odds

| Sport | Available? | Used? | Notes |
|-------|:---:|:---:|---|
| NFL | Yes | **No** | Pre-match odds markets |
| NBA | Yes | **No** | Pre-match odds markets |
| MLB | Yes | **No** | Pre-match odds markets |
| NHL | Yes | **No** | Pre-match odds markets |
| Soccer | Yes | **No** | 80+ pre-match markets |
| Cricket | Yes | **No** | Pre-match odds |
| Esports | Yes | **No** | Pre-match odds |
| Handball | Yes | **No** | Pre-match odds |
| Horse Racing | Yes | **No** | Pre-race odds |
| Tennis | Yes | **No** | Pre-tournament odds |
| Volleyball | Yes | **No** | Pre-match odds |
| Golf | No | -- | Not available |
| F1 | No | -- | Not available |

**Status:** Completely unused. We have **no client method** for the odds endpoint.

**Gap (MEDIUM):** The StatPal odds endpoint could supplement The Odds API data:
- We're already paying for it -- zero marginal cost
- Could reduce Odds API quota consumption ($119/mo, 5M calls)
- Soccer has 80+ markets -- much richer than our current coverage
- Different bookmaker coverage may provide additional market depth

**Caution:** Need to understand what bookmakers StatPal covers vs. The Odds API to avoid duplicating the same underlying data.

---

### 5. Live Match Stats

| Sport | Available? | Used? | Notes |
|-------|:---:|:---:|---|
| Soccer | Yes | **No** | Detailed in-game stats (possession, shots, xG) |
| NFL | Partial | **No** | Basic team stats during game |
| NBA | Partial | **No** | Basic team stats during game |
| NHL | Yes | **No** | Team/league stats |
| F1 | Yes | **No** | Lap times, positions |

**Status:** Completely unused. Our API client has no method for live match stats.

**Gap (LOW-MEDIUM):** Live match stats could enrich event detail pages. Soccer xG data is particularly valuable. However, we'd need frontend work to display it.

---

### 6. Injuries

| Sport | Available? | Used? | Notes |
|-------|:---:|:---:|---|
| Soccer | Yes | Yes | Injury/suspension tracking |
| NHL | Yes | Yes | Injury updates |
| NFL | Not listed | Attempted | May not return data -- docs don't list NFL injuries |
| NBA | Not listed | Attempted | May not return data |
| MLB | Not listed | Attempted | May not return data |

**Status:** Synced hourly at :20. Stored in `win_probability_sources` JSONB as `statpal_injuries`. Used for "Why Did the Line Move?" context.

**Note:** The coverage page only lists injuries for Soccer and NHL. Our code calls injuries for all mapped sports but may get empty responses for NFL/NBA/MLB. This wastes API calls but doesn't cause errors.

---

### 7. Standings

| Sport | Available? | Used? | Schedule | Notes |
|-------|:---:|:---:|---|---|
| NFL | Yes | Yes | Daily 8:00 UTC | Parsed from nested tournament/league/division structure |
| NBA | Yes | Yes | Daily 8:00 UTC | Same |
| MLB | Yes | Yes | Daily 8:00 UTC | Same |
| NHL | Yes | Yes | Daily 8:00 UTC | Same |
| Soccer | Yes | Yes | Daily 8:00 UTC | League tables |
| Golf | Yes | Yes | Daily 8:00 UTC | FedExCup standings |
| F1 | Yes | No | Not mapped | Driver/team standings |
| Tennis | Yes | No | Not mapped | ATP/WTA rankings |

**Status:** Well-utilized for mapped sports. Stored on `Team.standings_data`.

---

### 8. Rosters

| Sport | Available? | Used? | Schedule | Notes |
|-------|:---:|:---:|---|---|
| NFL | Yes | Yes | Daily 7:30 UTC | Supplements ESPN. Only updates if ESPN roster is empty. |
| NHL | Yes | Yes | Daily 7:30 UTC | Same |
| NBA | Not listed | Attempted | Daily 7:30 UTC | May return empty -- docs don't list NBA rosters |
| MLB | Not listed | Attempted | Daily 7:30 UTC | Same |
| Soccer | Lineups only | Yes | Daily 7:30 UTC | Lineups, not full rosters |

**Status:** Working but secondary to ESPN. Only fills gaps where ESPN has no roster data.

---

### 9. Team Stats

| Sport | Available? | Used? | Schedule | Notes |
|-------|:---:|:---:|---|---|
| NFL | Yes | Yes | Weekly (Mon 9:00 UTC) | Season-level team stats |
| NHL | Yes | Yes | Weekly | Same |
| MLB | Yes | Yes | Weekly | Batting/pitching/fielding stats |
| NBA | Not listed | Attempted | Weekly | Docs don't explicitly list NBA stats |
| Soccer | Yes | Yes | Weekly | Detailed team/player stats |

**Status:** Working. Stored on `Team.season_stats`. Low frequency (weekly) is appropriate.

---

### 10. Player Stats

| Sport | Available? | Used? | Notes |
|-------|:---:|:---:|---|
| All | Yes (per API client) | **No** | Client method exists (`get_player_stats`) but no task calls it |

**Status:** API client method exists but is never called by any task. No player stats are synced.

**Gap (LOW):** Individual player stats could feed into player prop context, but we don't currently have a player prop feature that needs it.

---

### 11. Results

| Sport | Available? | Used? | Notes |
|-------|:---:|:---:|---|
| All | Yes | **No** | Historical match results endpoint |

**Status:** We get results indirectly through the schedule endpoint (finished games). No dedicated results endpoint call.

**Gap (LOW):** Not needed -- schedule sync already covers completed games.

---

### 12. Scoring Leaders

| Sport | Available? | Used? | Notes |
|-------|:---:|:---:|---|
| NFL | Likely | **No** | Not documented; endpoint path unknown |
| NBA | Likely | **No** | Same |
| MLB | Likely | **No** | Same |
| NHL | Likely | **No** | Same |

**Status:** The quick-start tutorial mentions a `/scoring-leaders/` endpoint but no sport-specific docs confirm availability. Not implemented in our API client.

**Gap (LOW):** Could be interesting for "league leaders" context on event detail pages, but low priority.

---

### 13. Video Highlights

| Sport | Available? | Used? | Notes |
|-------|:---:|:---:|---|
| Unknown | Mentioned in quick-start | **No** | Endpoint path: `/video-highlights/` |

**Status:** Mentioned in the quick-start guide endpoint list but not on the coverage page for any sport. Likely limited availability or deprecated.

**Gap (LOW):** If available, highlights could be a differentiating feature on event detail pages.

---

### 14. Head-to-Head Stats

| Sport | Available? | Used? | Notes |
|-------|:---:|:---:|---|
| Soccer | Yes | **No** | Historical H2H between two teams |

**Status:** Soccer-only. Not implemented in API client.

**Gap (LOW):** Could enrich soccer event detail pages with historical context.

---

### 15. Transfer History

| Sport | Available? | Used? | Notes |
|-------|:---:|:---:|---|
| Soccer | Yes | **No** | Player transfer records |

**Status:** Soccer-only. Not relevant for our use case.

---

### 16. Extended Schedule

| Sport | Available? | Used? | Notes |
|-------|:---:|:---:|---|
| Unknown | Mentioned in quick-start | **No** | Endpoint path: `/extended-schedule/` |

**Status:** Mentioned but unclear how it differs from `season-schedule`. May include more metadata.

**Gap (LOW):** Current schedule endpoint works fine.

---

## Priority Action Items

### HIGH Priority

| # | Action | Impact | Effort |
|---|--------|--------|--------|
| 1 | **Create dedicated livescores polling task** | Real-time game state (period, clock, score) for event detail pages. Currently 60-min stale via hourly schedule sync. StatPal updates every 15s. | Medium -- new task, reuse existing `get_live_scores()` method |
| 2 | **Gate PBP calls by sport** | Stop wasting API calls on 404s for NBA/NHL/MLB. Add `STATPAL_PBP_SPORTS = {"nfl", "pga"}` check. | Small -- 3-line change |

### MEDIUM Priority

| # | Action | Impact | Effort |
|---|--------|--------|--------|
| 3 | **Explore pre-game odds endpoint** | Could reduce Odds API quota usage (save $119/mo if sufficient). Zero marginal cost since we already pay. | Medium -- need to build client method, test data quality |
| 4 | **Add Tennis to STATPAL_SPORT_MAPPING** | Livescores + standings for ATP/WTA. We already have `tennis_atp`/`tennis_wta` in Odds API. | Small |
| 5 | **Add live match stats for soccer** | xG, possession, shots on event detail pages. Unique data we can't get elsewhere. | Medium -- client method + frontend display |

### LOW Priority

| # | Action | Impact | Effort |
|---|--------|--------|--------|
| 6 | Add F1 to mapping | Livescores + standings for a passionate fanbase | Small |
| 7 | Implement scoring leaders | League context on event detail pages | Medium |
| 8 | Implement player stats sync | Player prop context | Medium |
| 9 | Soccer H2H stats | Historical context on soccer event pages | Small-Medium |
| 10 | Explore video highlights | Could differentiate from competitors | Unknown -- need to test endpoint |

---

## API Call Budget Impact

Current StatPal usage (estimated daily calls):

| Task | Frequency | Sports | Est. Daily Calls |
|------|-----------|--------|-----------------|
| Schedule sync | Hourly x 4 sports | 4 | ~96 (4 x 24) |
| Livescores (in schedule) | Hourly x 4 sports | 4 | ~96 |
| Injuries | Hourly at :20 | ~12 | ~288 (12 x 24) |
| Live plays (PBP) | Every 60s | ~12 (but most 404) | ~720 when games live |
| Rosters | Daily | ~12 | ~24 |
| Standings | Daily | ~12 | ~12 |
| Team stats | Weekly | ~12 | ~2 |
| **Total** | | | **~1,200-1,400/day** |

StatPal allows up to 300K calls/day. We're using <0.5% of our quota.

**Adding a 30-second livescores poll** for 4 major sports would add ~11,520 calls/day (4 sports x 2,880 polls/day). Still well under 5% of quota. Plenty of room.

---

## Files Referenced

- `/Users/bain/bainluck/backend/app/services/statpal_api.py` -- API client (9 endpoints implemented)
- `/Users/bain/bainluck/backend/app/tasks/statpal_sync.py` -- Sync tasks (6 tasks: schedules, injuries, live plays, rosters, standings, team stats)
- `/Users/bain/bainluck/backend/app/tasks/__init__.py` -- Task registration and beat schedule
- `/Users/bain/bainluck/backend/app/utils/sport_keys.py` -- `STATPAL_SPORT_MAPPING` (12 sport keys mapped)
- `/Users/bain/bainluck/backend/app/tasks/config.py` -- Polling intervals
