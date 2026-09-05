# REPORT — lane1/118: the twin was never hypothetical, it is in the search results

**PILLAR: MATCHING. SHIP: the Monday Night Football game stays ONE game.**

Written Sat 2026-09-05 **07:40Z / 00:40am PT** (stamped from `TZ=America/Los_Angeles date`; notice
24 — the Mac's clock is EDT, PT is `date` minus 3h).

No code changed. Nothing merged, nothing pushed, no cert staged. One issue updated with new
evidence and a production screenshot.

---

## 0. The headline

Every instrument this queue owns came back green or unchanged. The session's finding came from the
LOOK, not the instruments: **the phantom Broncos@Cardinals row is returned by ordinary search,
side by side with the real game, and the page header counts "2 games".** That is Alex's bar
("never shows it twice") failing on a browsable surface, today, in production.

It is filed on **#3070** (already OPEN, P1, `matching-symptom`) —
`#3070#issuecomment-5550333200`. Not fixed: D35 holds matching symptoms as filed until #2693
lands, and there is no DELETE rail by ruling 079.

---

## 1. Night three was NOT due — do not read this session as a missed poll

Queue 118 §1 asked for a 06:47Z/06:57Z double poll of `anchor_schedule_sentinel`. **Night three's
window opens 2026-09-06 06:40Z.** This session ran at **2026-09-05 07:27–07:40Z**, roughly 40
minutes after 117 restocked. Night three is **~23 hours in the future**. There was nothing to poll.

I read the endpoint anyway, to confirm the row had not moved and that nothing fired early. Night
two's row is **byte-identical to 117's record and to 116's**:

```
last_started_at 2026-09-05T06:48:45.289031+00:00 · last_success_at 2026-09-05T06:49:38.697519+00:00
terminal partial · complete false · reached_window_end true · pass_open false
resumed_from '2026-11-28T00:00:00+00:00|15197566' · restarted_from_exhausted_cursor false
continuation null · pass_drift_seen true · pass_expired false · pages 1 · examined 91 · eligible 687
successes_24h 1 · failures_24h 0 · starts_24h 1 · incompletes_24h 0 · hard_kills_24h 0
by_verdict: agrees 90 · authority_moves_us 1 · teams_disagree 0 · no_answer 0
last_duration_ms 53378
```

Three readings across three sessions now agree on every field. Neither of the two "finding"
conditions is present: `pass_open` is false (so the `pass_open: true` + non-null `resumed_from`
contradiction cannot apply), and `resumed_from` is non-null with
`restarted_from_exhausted_cursor: false` (so the CERT-843 blind-spot P1 is not reopening).
`complete: false` is the repair working, and is not filed.

**`hard_kills_24h` re-read at 0** — third consecutive 0, so 117's read of the counter rolling 1→0
on 9/5 is settled as a ~24h-old event ageing out, not an incident.

**For 119: night three is your first genuine reading, and you must still poll twice** (06:47Z and
06:57Z) — night two started 8m05s after its crontab minute. Night four (Mon 9/7) is still the
first night that can close **#2978**.

## 2. The twin test — 13 rows, still no twin, third consecutive confirmation

```
15184637 LAC @ TB    2026-12-06 18:00Z  espn 401873101  ext f8a9…  817 snaps
14780587 GB  @ NO    2026-12-06 18:00Z  espn 401873099  ext 1ccb…  813
15184635 DET @ ATL   2026-12-06 18:00Z  espn 401873098  ext c944…  826
15176006 JAX @ CHI   2026-12-06 18:00Z  espn 401873100  ext 0236…  799
15176007 CIN @ CLE   2026-12-06 18:00Z  espn 401873097  ext b447…  808
15184638 WAS @ TEN   2026-12-06 18:00Z  espn 401873102  ext ae34…  799
14780588 SF  @ NYG   2026-12-06 18:00Z  espn 401873095  ext a549…  811
15184636 MIA @ DEN   2026-12-06 21:05Z  espn 401873103  ext 9a55…  818
15184639 PHI @ ARI   2026-12-06 21:05Z  espn 401873104  ext f489…  816
15184641 CAR @ MIN   2026-12-06 21:25Z  espn 401873106  ext c186…  814
15184640 BUF @ NE    2026-12-06 21:25Z  espn 401873105  ext 4116…  798
14780589 HOU @ PIT   2026-12-07 01:20Z  espn 401873107  ext 26bf…  807
15304746 DAL @ SEA   2026-12-08 01:15Z  espn 401873108  ext NULL     0
```

**13 rows.** `15304746` still `external_id NULL`, 0 snapshots. Per the queue's own table this is
"not yet exercised — **not a finding**". Recorded at **2026-09-05 07:29Z**.

Not re-derived: 117's season-wide `1 of 322` count. The twin test's answer did not change.

## 3. The pre-check — 0, and un-tripped

```
contested_ids = 0        (2026-09-05 07:29Z)
```

Sentry, org `alexander-bain`, project `bainluck`: **zero** issues naming `uq_events_espn_id`, at
both `statsPeriod=24h` and `14d`. The only `IntegrityError` remains **BAINLUCK-13D**
(`win_prob_snapshots_event_id_fkey`), 3 lifetime, `lastSeen 2026-09-01T06:00:06Z` — different
constraint, predates the index, unchanged from 117. Not re-triaged.

The index is not merely un-violated, it is un-*tripped*, for a second session running.

## 4. The daily gate — day 1 re-read, not a new row

```
generated_at 2026-09-05T07:27:45Z · last_pass_at 2026-09-05T07:23:00Z (age 284s) · read READ-OK
both 321 · statpal_only 0 · ours_only 1 · denominator 322
pct 99.69 · ours_covered_pct 99.69 · bar 99.5 · gate MEETS
schedule: within 293 · off_by_hours 26 · wrong_day 2
excluded: statpal_placeholders 7 · statpal_unusable_names 0 · our_unusable_names 0
```

**Same calendar day as 117's and 116's reads — a third same-day re-read, not day 2.** The count
stands at **day 1 of 7; earliest flip Fri 2026-09-11.** `statpal_only 0` as expected. `ours_only 1`
is row B. Nothing below the bar, so nothing to shout about.

Day 2 is **2026-09-06**, and 119 reads it.

## 5. THE FINDING — the phantom is discoverable, and indistinguishable from the real game

### How I got there

Not by re-reading the issue. I aimed this queue's own twin instrument at the surface Alex is about
to look at — NFL kickoff is Thu 9/10 — and then widened it to the whole season:

```sql
SELECT away_team_name, home_team_name, count(*) AS n
FROM events WHERE sport_id = 1
  AND commence_time >= '2026-09-01' AND commence_time < '2027-03-01'
GROUP BY away_team_name, home_team_name HAVING count(*) > 1
```

**Exactly one duplicated pair in the entire 2026-27 NFL season.** That is a useful bound in its own
right: the NFL twin population is not a sample, it is complete, and it is one pair.

The pair is Denver Broncos @ Arizona Cardinals — **row B, already filed.** I checked before
claiming anything, which is the only reason this did not become a false discovery.

### Week 1 is clean — the kickoff surface is safe

```
16 games, 2026-09-10 → 2026-09-15, every one with espn_id AND external_id,
snapshot counts 2,961 – 4,426 (median ~4,200). 32 franchises, each exactly once.
```

Thursday's opener `14780138` New England @ Seattle is fully anchored with 4,309 snapshots. **No
twin, no gap, nothing missing in the window Alex will actually be in on kickoff night.** This is a
green receipt and it is worth as much as a red one.

### What is new about row B

The 9/4 17:21Z LOOK on this issue photographed `/events/14751059` **directly by id**. Three things
were not established then:

**(a) It is reachable by browsing.** `https://www.bainluck.com/search?q=Broncos%20Cardinals`,
phone width, production:

```
Results for "Broncos Cardinals"
12 results · 2 games · 10 markets
GAMES (2)
  NFL   Oct 25 4:05 PM   Arizona Cardinals 26%  /  Denver Broncos 74%   · Proj 18-26
  NFL   Dec 27 1:00 PM   Arizona Cardinals 25%  /  Denver Broncos 75%
```

Same NFL badge, same logos, same bar treatment, no "no odds yet" state, numbers one point apart.
The header counts **`2 games`**. A user has no way to tell which is real. Screenshot:
`artifacts/lane1-118-search-two-games.png`.

**(b) Where the confident 25%/75% comes from.** The entire evidentiary basis of that card is one
snapshot, 114 days old:

```
odds_snapshots WHERE event_id = 14751059  →  exactly 1 row
  draftkings · captured_at 2026-05-14 11:05:15.589563Z · home_moneyline +285 · away_moneyline -360

14751059  win_probability_sources  NULL
14781722  win_probability_sources  {'betting_book_count': 2}
```

`+285/-360` normalises to ≈25/75 — exactly the card. So the phantom's percentage is not an
aggregate at all; it is one stale book line read straight through, sitting beside a row backed by
822 snapshots across 2 books. The card never surfaces that difference, which is *why* they look
alike.

**(c) The phantom arrived first.**

```
14751059 (phantom)  created_at 2026-05-14 11:05:00.181345
14781722 (real)     created_at 2026-05-15 02:05:00.101693
```

~15 hours earlier. So the real, ESPN/StatPal-anchored game was the **second** arrival, and under
ruling 048 / gotcha #32 it correctly refused to be absorbed by an id-less incumbent — it created,
as designed. **The defect is not the non-absorption. It is that nothing drained the id-less first
arrival.** `NO_ANCHOR_CHANNEL`, as filed.

### Why this matters more than §4 of queue 118 assumed

Queue 118 §4 reasons that row B "buys the ship nothing" because the gate MEETS empirically with row
B counted. That is true **of the gate** and false **of the user**. The gate half and the user half
are different questions and only the gate half had been asked. Exposure also grows: the league page
windows to 8 upcoming games (`upcoming_games_has_more: true`), so Dec 27 is not on `/sports` yet —
it enters that window as the date approaches, on a far more trafficked surface than search.

Still filed, not fixed. D35, and ruling 079's no-DELETE-rail.

## 6. What I did not do

- Did not fix the phantom (D35 — #2693/lane1/057 owns it; ruling 079 — no DELETE rail).
- Did not run 115's rollback line. It deletes the ship and has been stale since 116.
- Did not invoke the CREATE rail. Population 4 stays gate-refused at plan time.
- Did not touch #3117, #2896, or the unique index.
- Did not open any new issue — the finding belonged to an open one.

## 7. Traps banked this session

- **`odds_snapshots` has `captured_at`, NOT `created_at`.** db-query answers with
  `undefined_column` and no hint; the column that *is* correct in the same query (`bookmaker`)
  makes it look like the wrong guess was elsewhere. `events` does have `created_at`.
- **A "new" duplicate can be an old friend on an unfamiliar date.** Row B surfaced in a pair-scan
  as `Oct 25 … Dec 27` — two dates, neither of which is how the issue describes it ("a stale
  listing for a game played Oct 25"). It read like a fresh twin. Pull the full rows and match ids
  against the filed ones before writing a word.
- **Queue 118 §4's phrase "a game played Oct 25" is wrong in tense** — 14781722 is
  `status: scheduled`, `completed_at NULL`, no scores, and Oct 25 is seven weeks in the future.
  Corrected here so 119 does not inherit it.
- **Check the queue's clock against the actual clock before executing §1.** Queue 118 was written
  ~40 minutes before this session and its most urgent item was ~23 hours away. A directive's
  urgency is a snapshot.
- **Sentry rejects `statsPeriod=90d`** — valid choices are `''`, `24h`, `14d` only, and it says so
  in the 400 body.
- **Grep the issue before filing evidence on it.** The event-page LOOK was already there from 9/4;
  only three of my facts were new, and posting all of them as new would have buried the ones that
  were.

## 8. State at session end

- Branch `lane1/099-artifacts`, artifacts-only commit. No master write. Nothing to merge.
- `#3070#issuecomment-5550333200` posted.
- Working tree otherwise clean.
