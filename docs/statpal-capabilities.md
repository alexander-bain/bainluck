# StatPal — what it can do for us, what it can't, and what to adopt
*Fable-5, Thu 2026-09-03 12:20pm PT. Judgment on top of the measured catalog `.claude/handoff/ARTIFACT-M-20260903-E.md`
(104 documented paths, live samples 18:40–19:05Z, spec `statpal.io/static/openapi/openapi-compiled.yaml` v2.0.0),
plus `-B`, `-C`, `-D` (9/2–9/3). Plan: Total Sports Access, $129/mo, 300,000 calls/day; we used 1,981 today (0.66%).
This file is the reference for the AUTHORITY lane (D50) and anyone touching `services/statpal_api.py`.*

*Committed to the repo and corrected in three places by the authority lane, Thu 2026-09-03 ~2:15pm PT
(§2 tennis reach, §4.2, §5), after probing `tennis/daily/{d}` across `d-2…d7`. It had been sitting
untracked in the shared master tree, where a file is one `git clean` from gone. Every correction is
marked **CORRECTED**; nothing else of Fable's text is altered. Evidence:
`.claude/handoff/ARTIFACT-AUTHORITY-20260903-TENNIS.md` §1.*

*Corrected again in §2 (the MLB row) and §5 by the authority lane, Fri 2026-09-04 ~7:10am PT, from
`mlb/season-schedule` and `mlb/livescores` read at 13:38Z and 13:52Z. Step 5's blocker is closed:
the cross-endpoint anchor is `livescores.oddsid` → `season-schedule.id`. Pinned in
`backend/tests/test_statpal_mlb_id_spaces.py`; evidence
`.claude/handoff/ARTIFACT-AUTHORITY-20260904-MLB-ID-SPACES.md`.*

*Corrected a third time in §2 (the MLB row) and §5 by the authority lane, Fri 2026-09-04 ~9:00am PT,
from the FULL MLB census (all 16 `livescores` rows against all 227 `season-schedule` rows, 14:28Z /
14:29Z) and from production `events`. **MLB now reads through the authority door and has an hourly
shadow stamper at :21, dark.** Two findings supersede text below: the blank-`oddsid` residue is a
publishing gap, not an identity gap (all three blanks have schedule rows); and OUR
`events.statpal_fixture_id` column already holds two StatPal id spaces at once. Payloads are pinned
as `backend/tests/fixtures/statpal_mlb_*_20260904_fullcensus.json`; guards in
`backend/tests/test_statpal_mlb_shadow_stamp.py`.*

*NOTE ON THIS FILE'S OWN HISTORY. The 9/3 commit above never reached master — it sat on the unmerged
branch `authority/002-the-tennis-schedule-cannot-serve-today` for a day while
`services/statpal_api.py`, `tasks/stamp_v1_statpal_fixtures.py` and
`tests/test_statpal_authority_nba_nhl.py` all cited it by path from master. Tracked on a branch nobody
merges is the same failure mode as untracked, one step further from view. Rescued 9/4 by the authority
lane; the original commit is cherry-picked, so Alex's authorship and message are intact.*

## 1. The contract in five lines
- Auth is an `access_key` query param; every endpoint is GET; base `statpal.io/api/v1/{sport}/…`, soccer on `/v2`.
- A malformed call is **HTTP 200 with body `invalid-request`** — never "no data". Parse for it; test for it.
- Refresh classes: livescores / live-plays / soccer live odds = 5–15 s products; `daily`, schedules, standings,
  rosters, injuries = 1–12 h products and the vendor asks for ≤10 reads/hour/endpoint. Rate-limit → backoff, 429 re-raises.
- Livescores remember ~24 h. History is ours to keep (we do); StatPal is not a backfill source.
- `user-request-count` is the meter; its response echoes the key — count only, never the body, in any artifact.

## 2. What is TRUE per sport (measured, not advertised)
| Sport | Fixture exists BEFORE play, with an id | Same id in livescores? | State words the feed actually says | Verdict as an authority |
|---|---|---|---|---|
| Tennis | YES, **but only from tomorrow onward** — `daily/d1` (70 fixtures for 9/4, pre-play). **CORRECTED:** the reach is not `d1…d7`. Measured 9/3 19:40–20:10Z: `d-2` 34, `d-1` 49, **`d0` HTTP 500**, `d1` 70, `d2` 1, `d3`–`d7` a well-formed empty. A day token also straddles two UTC dates (`d-1` straddles three), so filter on the parsed `start_time`, never on the token. | YES 3/3 | Not Started, Set 1/2/3, Finished, Cancelled; `Interrupted` seen 9/2 | **Fit.** Missing 1 of 20 ESPN fixtures once; one game behind ESPN in 2/8 live checks. |
| NFL | YES — `season-schedule` lists Week 1's 16 games 6–11 days early, `contestid` | untested until 9/10 kickoff | Final (offseason tail) | **Fit, pending the live-id check on 9/10.** |
| MLB | YES, **but the endpoint is a ~17-day ROLLING WINDOW, not a season** — **CORRECTED 9/4:** 227 games, 2026-08-29→09-15 (NBA serves 1206 and NHL 1404, whole seasons). `id` 227/227 unique; `stats_id` unusable on 22.5% (29 blank, 22 sharing 11 values with another contest). | **CORRECTED 9/4: the anchor EXISTS and is not called `id`.** livescores `id` is indeed a third space (0/16 reach either schedule space) — but livescores **`oddsid` IS `season-schedule.id`**, 13/16 rows, all 13 dereferencing. Blank on 3/16. | Not Started, Top/Bottom Nth, Finished | **CORRECTED 9/4: "join on (teams, date)" is wrong twice over.** `date` is UTC, so it invents 22 doubleheaders that are consecutive-day series games (17.4–23.1h apart, none under 6h) and misses the one real doubleheader, whose halves straddle midnight UTC. Re-key on the local day (every park is UTC-4..-7). Even then a name key drops `St. Louis Cardinals` vs `St.Louis Cardinals`; `oddsid` does not. **Anchor on `oddsid`→`id`.** **CORRECTED AGAIN 9/4 (full census): ADOPTED — MLB is in `V1_SEASON_SCHEDULE_SPORTS` and stamps hourly at :21, dark.** The 3 blanks are a livescores publishing gap, not missing identity: all three have schedule rows, recovered by (both clubs, first pitch ±1h, unique-or-refuse) — 13/13 correct scored against the anchored rows, vs 9/13 for a day key. 2 of 3 recovered, the doubleheader nightcap refused (endpoints disagree by 3h05m). Note `St.Louis` is OUR split too (12 rows vs 7). |
| NBA / NHL | YES — 26/27 schedules already served (NBA from 10/3, NHL from 9/19), `id` + `stats_id` | unknown (no live games) | empty until season | **Fit for schedules now; state unverifiable until preseason.** |
| Soccer (v2) | YES — `matches/daily?offset` ; `static_id` is date-prefixed, plus `alternate_id`, `alternate_id_2` | uncompared; live odds use `main_id` + 3 fallback ids | FT, HT, Pen., minute numerals; no suspended/postponed seen | **Fit for long tail (83 leagues, ESPN has boards for few).** Ids are messy by StatPal's own design — match by ids-with-fallbacks. |
| Esports | `daily` unprobed; 61 live now | — | Not Started, Started, Pause, Walkover, Finished | **Already the doctrine's authority** (ESPN has 0 boards). `Pause` is the only explicit interrupted state in the whole catalog. |
| Golf | `schedule`; livescores says Final | — | Final | **Fallback only** — DataGolf stays authority (pairing/minute exactness). |
| Cricket / F1 / handball / volleyball / horse racing | schedules exist | — | cricket's "status" is free text incl. dismissal strings (`lbw b X`) | Not fronts. Cricket status is a parser trap. |

## 3. What we use today vs what the plan buys
Used (sync task): livescores (30 s), season-schedule / daily / upcoming (hourly per sport), rosters, injuries (every 20 min),
standings, team-stats, NFL live-plays. **Seven of the paths our client calls are not in the spec at all** (`/{sport}/teams`,
`/injuries`, `/fixtures/{id}`, `/fixtures/{id}/playbyplay`, `/teams/{id}/roster|stats`, `/players/{id}/stats`) — a
legacy surface the vendor has already dropped from its documentation. It answers today; nothing promises tomorrow.

Unused and on the plan:
- **Tennis `daily/{d}`** (the schedule), `tournament-list/{type}`, `tournament/{id}`, `livestats`, `standings`.
- **Odds**, every sport: `/{sport}/odds` (tennis payload is 10 MB for the US Open — Home/Away per bookmaker with stop
  flags), `/soccer/odds/live` (5 s, carries `state_name/min/sec` and `stopped/blocked/finished` flags),
  `/soccer/leagues/{id}/odds/prematch`. A third price leg and a bookmaker set, from a feed we already pay for.
- **Soccer-only enrichment** (v2): `live-storylines`, `team-lineups`, `weather-forecast`, `predictions`, `head-to-head`,
  `images`, `injuries-suspensions`. The site's "storylines, predictions, lineups, weather" bullets are SOCCER. They do
  not exist for tennis, NFL, MLB, NBA, NHL. Do not plan event-page copy on them outside soccer.
- `daily/{d}` for MLB/NBA/NHL/esports; `league-stats`, `player-stats` (defined in our client, never invoked).
- 15-second livescores (we poll at 30 s) and the whole meter (0.66% used).

## 4. Adopt, in this order (each is a named ship, each rides an issue)
1. **Get off the undocumented paths** (authority lane, step 1b; rides "nothing goes blank"): rosters →
   `/rosters/{abbr}`, injuries → `/injuries/{abbr}`, team stats → `/team-stats/{abbr}`, play-by-play → `/live-plays`,
   drop `get_game_detail`/`get_player_stats` until a documented path exists. Small, testable, removes a silent-vanish risk.
2. **Tennis `daily` as the fixture source for the hub — for TOMORROW onward only** (authority step 4 + ux/1047's
   slate). **CORRECTED 9/3:** `daily` is *not* the day's order of play. There is no `d0`, and it fails as an
   **HTTP 500** — not a 404, not `invalid-request` — so today's play is unobtainable from this endpoint. `d1`
   carries tomorrow (70 fixtures for 9/4); `d2` had 1; `d3`–`d7` are a well-formed empty because the draw does not
   exist yet. Only `livescores` knows today's matches, and only once a match is at or near the ball. **So `daily`
   alone cannot fill the hole that empties the tennis slate in the morning** — build the slate from tonight's `d1`
   read, held over into tomorrow, and treat `livescores` as the same-day corrector. Two further contract facts
   before anyone builds on it: doubles outnumber singles better than 2:1 on `d1` (48 v 22), so an agreement
   denominator that does not split them reports a large phantom gap; and StatPal stamps **15:00 UTC as a session
   placeholder** on 66 of 70 unplayed fixtures, backfilling the true minute only after the match — so StatPal
   tennis is an **existence** authority, never a **time** authority. ESPN stays the state authority for tennis
   until the ledger says otherwise.
3. **Livescores at 15 s during live tennis** (live lane, Lisa's US Open, rides #2766 family): vendor cadence is
   15 s; we read at 30 s. Budget impact: +2,880 calls/day per sport at the fastest — noise against 300,000.
4. **NFL shadow stamping** (authority step 2): `contestid` from `season-schedule` beside ESPN's id; verify the
   livescores id space at 9/10 kickoff before anything flips. **Three corrections from the first hand-run
   agreement reading** (`artifacts/authority-001/NFL-AGREEMENT-20260903.md`), all measured 9/3:
   **(a) match on identity; compare kickoff as an attribute, never as a key.** A `(teams, kickoff ±1h)` join drops
   29 of 272 real matchups — the 24 whose Week 16–18 times are not set yet, *and the 5 stamped with the wrong
   date*, which are the rows the whole program exists to surface. **(b) Publish the five buckets, not one blended
   ratio:** agrees-within-1h 243, same-day-different-time 24, **wrong-week 5**, missing-from-us 0,
   unknown-to-StatPal 0. One number would have read 89.3% and buried the five findings inside 24 non-findings.
   Identity agreement is 100%; scheduling agreement is 98.2% and those 5 rows are the whole gap. **(c) Exclude
   StatPal's 53 TBD playoff placeholders from the denominator** — we correctly do not create those rows, so
   counting them as absences makes the bar unreachable by design. For tennis, omit the time bucket entirely
   rather than scoring it (§5). ~~**Blocked on #2879** — the anchor namespace is chosen by counting digits, and NFL
   `contestid`s are 6-digit like MLB's ids, so a stamp today would land in MLB's bucket and, on conflict, write
   no anchor at all, silently.~~ **UNBLOCKED — #2879 shipped under D55.** `statpal_anchor_key` now takes the sport
   from the caller and `statpal_id_space` maps `sports.key` through (every `tennis*` collapses to `tennis`, which
   is the one non-1:1 case). MLB stamps `baseball_mlb:<id>`, NFL `americanfootball_nfl:<contestid>`; the 6-digit
   collision cannot happen. Verified before MLB was routed, 9/4.
5. **Soccer live state from `odds/live`** (later): `state_name/min/sec` + `stopped/blocked` flags are the vendor's
   match state, not a price — an explicit "suspended" signal for soccer the doctrine can rank at rung 1 or 3 after
   measurement. Not a price signal; D27 stands.
6. **Sportsbook odds via StatPal** (later, needs a compare against The Odds API on coverage, latency and cost):
   payloads are large (10 MB tennis) — fetch per tournament on a schedule, never per page view.
7. **Soccer enrichment** only if soccer becomes a front (Discover CTR). Park.

## 5. What is NOT possible, so nobody plans on it
- ~~No cross-endpoint stable id for MLB (three id spaces), and NBA/NHL are untested; join by (teams, date) until proven.~~
  **CORRECTED 9/4 — THERE IS ONE, AND THE (teams, date) FALLBACK IS UNSAFE.** The three id spaces are real and
  `livescores.id` reaches neither schedule space (0/16) — but `livescores.oddsid` is `season-schedule.id` on 13/16
  live rows, all 13 dereferencing. Blank on 3/16, ~~one of them the second half of the slate's only doubleheader~~.
  Do NOT fall back to (teams, calendar date): `season-schedule.date` is UTC, which flags 22 consecutive-day series
  pairs as doubleheaders and hides the single real one across midnight. Re-key on the local day, and prefer the
  anchor — the name key also drops `St. Louis Cardinals` against the schedule's `St.Louis Cardinals`.
  **CORRECTED AGAIN 9/4 from the FULL census — the struck clause described 1 of the 3 blanks, not all three.**
  The other two are ordinary single games; every one of the three HAS a schedule row, so the residue is a
  livescores *publishing* gap, not an identity gap. Recovery is (both clubs via `normalize_team`, first pitch
  within ±1h, unique-or-refuse), scored 13/13 correct on the anchored rows against 9/13 for any day key. And do
  not merely re-key the day rule: measured, it does not flag the doubleheader, it **fuses** it — game 2 resolves
  onto schedule row `354453`, which game 1 already holds by its own `oddsid`.
  *(That struck sentence is why `test_statpal_mlb_shadow_stamp.py` exists: its count came from the census and
  its story from a reduced 6-row fixture in which the doubleheader IS the only blank. A reduced fixture may back
  a count or a characterisation, never both.)*
- **NEW 9/4 — OUR OWN COLUMN ALREADY HOLDS TWO STATPAL ID SPACES, and nothing was reading it as a problem.**
  `_parse_single_fixture` takes `fixture_id` from `id`, and `id` means different things on the two endpoints, so
  `sync-statpal-schedules-mlb` (hourly) and `sync-statpal-livescores` (every 30s) write different spaces into
  `events.statpal_fixture_id` for the same sport. Measured over the 17-day window: of 222 distinct MLB values,
  **130 dereference to `season-schedule.id`, 0 to `stats_id`, and 92 to neither**. Reported as
  `FOREIGN_ID_SPACE`, never overwritten — the repair is a data write owing a backup and a restore line (D51),
  and this count is how it gets sized. Membership is tested by DEREFERENCE, never digit count (D55): the two
  spaces are both 10 digits, both `1329…`, with overlapping ranges and no value in common.
  NBA/NHL are no longer untested: `id` anchors both, `stats_id` is 1404/1404 on NHL (with 3 colliding pairs) and
  0/1206 on NBA. **`time` is UTC on season-schedule and ET on livescores** — same field name, two bases.
- No backfill: ~24 h livescore memory. No injuries/lineups/weather outside soccer. No documented team/fixture-detail
  endpoints (the ones we call are legacy). No in-play odds yet outside soccer live (the site says "coming 2026").
- No NBA/NHL live state until preseason; no NFL live-id verification until 9/10.
- **CORRECTED 9/3 — no tennis order of play for TODAY.** `tennis/daily/d0` is an HTTP 500; the schedule endpoint
  starts at tomorrow. Nothing may plan on `daily` answering "what is on court now". Absence and error at least
  arrive differently here (gotcha #53): `d5`/`d7` return HTTP 200 with a `scores` envelope and no matches, which
  is cleanly distinguishable from `d0`'s 500 — so a caller can tell "nothing scheduled" from "endpoint broken".
- **No tennis kickoff time before the match is played.** 15:00 UTC on 66 of 70 unplayed `d1` fixtures is a session
  placeholder, not a start time. Never let StatPal write a tennis kickoff, and never score tennis time agreement
  pre-play — measured naively it reads 8/19 and means nothing but two placeholders failing to coincide.
- `10 reads/hour` on non-live endpoints is the vendor's ask, not a hard limit we have measured — treat it as the limit.

## 6. Cost and load
1,981 calls today = 0.66% of the plan. Everything in §4 fits inside 10% of it. Nothing here scales with our users:
every StatPal call is a scheduled task (M-20260903-C: zero in-request StatPal calls in public routes).
