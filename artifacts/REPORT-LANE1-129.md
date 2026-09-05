# lane1/129 — night three STILL not due (12th session), twin holds a 14th time

**Ran:** Sat 2026-09-05, 10:19Z → 10:50Z (**03:19am → 03:50am PT**, stamped from
`TZ=America/Los_Angeles date`; notice 24 — the Mac's clock is EDT, PT is `date` minus 3h).

**PILLAR: MATCHING · TRUTH.** **SHIP: the Monday Night Football game stays ONE game** — Dallas
Cowboys @ Seattle Seahawks, Dec 7, event `15304746`. Live and still a single row after **fourteen**
readings.

---

## Headline

Two contributions, both from the first exact-duplicate census ever run over the **non-football**
sport families (candidate 6):

1. **#3176 (NEW, p2)** — one 6-day soccer fixture list was written into **all seven named league
   buckets at once**: 849 groups × 7 leagues = **5,943 rows**. A Nicaraguan third-tier match is
   filed as a Champions League fixture. Bounded (Mar 1–7 kick-offs, stopped 2026-03-04) and **not
   currently user-visible** — checked, not assumed.
2. **#3016 (comment)** — its five EPL phantoms have a **sharper, mechanistic discriminator** than
   `external_id IS NULL`: their `commence_time` is sub-second and *precedes their own `created_at`*.
   The class is **35,305 rows** across every sport. And the EPL symptom **drained while the rows did
   not**, whereas `soccer_other` grew **143 → 196 in 23 hours**.

---

## 0. The clock — 12th consecutive session handed a §1 in the future

`date -u` = **2026-09-05 10:19:43Z**. Night three's window opens **Sun 2026-09-06 06:40Z**.
**20.3 hours short.** I did not poll `anchor_schedule_sentinel` and did not report an absence.

**128 ran at 10:03Z — 16 minutes before me.** Per §14, a dated baseline that is minutes old is not a
data point. Everything I re-read below is labelled **liveness**, not data.

### A correction to the queue: candidate 2 is ALSO not due

§4c of the 129 queue says *"the two Sep 6 games have now been played"* and made re-reading them the
strongest candidate. **They have not been played.** They commence `2026-09-06 20:00Z` and
`23:30Z` — **34h and 37h after this session ran**. 128 wrote that line at 10:4xZ on **9/5** and
mis-tensed it. Candidate 2 is not available to any session before ~9/6 23:30Z.

*(Trap: a restock written at 3am can date its own "now" a day forward. Check a queue's dated claims
against the clock before spending a session on them.)*

## 1. Night three — NOT DUE. Not polled. No data point added.

Night three remains the **third** point. Night four (Mon 9/7) is still the first night that can
close **#2978**.

## 2. The twin test — 13 rows, a FOURTEENTH time (liveness, not a data point)

`sport_id = 1`, Dec 6–10: **exactly 13 rows**. `15304746` still `external_id NULL` / **0 snaps**;
the other 12 carry both ids and 798–826 snaps. **Not yet exercised — not a finding.**

Did **not** run the `sport_id <> 1` variant: the 13 did not change, which is the correct trigger (§2).

## 3. Gate reading — taken, and identical to 128 at +16 min (liveness)

Ran it rather than skip a standing instruction silently. All four sports byte-identical to 128:

| sport | both | ours_only | statpal_only | anchored/unanch/mismatch/polluted | live dup_ids |
|---|---|---|---|---|---|
| NFL | 321 | 1 | 0 | 247 / 26 / 0 / 48 | 0 |
| MLB | **158** | **64** | 65 | 135 / 0 / **23** / 0 | 5 |
| NBA | 41 | 0 | 1165 | 41 / 0 / 0 / 0 | 2 |
| NHL | 32 | 0 | 1372 | 27 / 5 / 0 / 0 | 3 |

**MLB held at `both 158 / mismatch 23`** — third consecutive read at 23, still **one step, not a
rate**. A reading on 9/6 is the first on a *different day* and is what would make it one.

Arithmetic check `anchored + unanchored + mismatch + polluted = both`: **passes on all four.**

### Structural correction for 130 — §3's prose points at the wrong level

`pct`, `ours_covered_pct` and `gate` are **NOT** keys of `agreement`. They live under
**`agreement.identity`** (`identity.pct`, `identity.ours_covered_pct`,
`identity.governing.gate`). Reading them at `agreement` level returns `None` silently. Verified
key lists:

- **sport row (6):** `agreement, last_pass_at, live, pass_age_seconds, sport_key, stamper`
- **`agreement` (12):** `anchors, denominator, denominator_is, excluded, identity, read,
  read_failures, receipts, schedule, sources_read, sport_key, window`
- **`identity` (8):** `both, governing, governs, ours_covered_pct, ours_only, pct, statpal_only,
  statpal_only_by_horizon`

NFL identity confirmed: `pct 99.69 · ours_covered_pct 99.69 · bar 99.5 · gate MEETS`.

## 4. The pre-checks — both unchanged (liveness)

- Contested `espn_id`: **0** — thirteenth consecutive zero.
- Duplicate `statpal_fixture_id`: **mlb 5 · nba 2 · nhl 3 · nfl 0** — matches `live.duplicate_ids`.

## 5. #3176 — the seven-league fan-out (candidate 6, NEW)

First exact-`(away_team_name, home_team_name, commence_time)` census over the non-football families.
**Sport-id lists derived from `sports.key LIKE '<family>%'`, never hand-typed** — #3172's lesson.

| family | ids in family | groups | rows | cross-sport | same-sport |
|---|---|---|---|---|---|
| basketball_* | 11 | 192 | 571 | 0 | 192 |
| icehockey_* | 10 | 2 | 6 | 0 | 2 |
| soccer_* | 60 | **2,035** | **8,642** | 1,923 | 112 |

**Artifact ruled out first:** 0 rows in any of the three families have a NULL or blank team name, so
`GROUP BY` is not collapsing nulls. The census stands.

Soccer's distribution has a **hard mode at exactly 7** — 852 groups / 5,964 rows. A spike that sharp
is a structure, not organic duplication. 849 of those groups are the fan-out (5,943 rows); the other
3 are unrelated `soccer_other` groups (21 rows).

Per-league counts are **identical at 849** across `soccer_epl`, `soccer_usa_mls`,
`soccer_spain_la_liga`, `soccer_germany_bundesliga`, `soccer_italy_serie_a`,
`soccer_france_ligue_one`, `soccer_uefa_champs_league` — the same fixture list written seven times.
Two waves (`2026-03-01`, 2,090 rows; `2026-03-04`, 3,612 rows), each `created_at` identical to the
microsecond within its wave. **Zero `espn_id` on all 5,943.** All `closed`.

**Scope stated honestly:** it stopped on 2026-03-04, and I *checked* user-visibility rather than
assuming — `/api/leagues/soccer_epl` serves `upcoming_games` + `recent_results` and March rows fall
outside both. Filed as a historical data-integrity population, not a live fire.

Ruled out as duplicates of **#2778** (that is `soccer_other`; these are named leagues), **#2321**
(LLM category, not sport_id at write time), **#3016/#3017** (live phantoms; these are closed).

## 6. #3016 — the discriminator, the class, and a symptom that moved both ways

Reached by accident: the EPL `recent_results` payload showed four rows sharing
`2026-09-03T18:50:00.316804` **to the microsecond**. Real fixtures do not kick off at `.316804`.

**Checked before claiming novelty — and it was already filed.** #3016 (9/4, ux/1066) names these
exact rows. The trap held: *a "new" bug in a class you just characterised is most likely a
duplicate.* So the contribution is measurement, not a filing.

**(a) The discriminator.** All four share that microsecond value, and it sits **~2 minutes BEFORE
their own `created_at`**. `commence_time` was written from the ingest clock, one read shared by the
batch. That explains the symptom mechanically: **a row whose `commence_time` is its own creation
instant is "starting now" by construction** — it enters the live/paused window the moment it is
written, and with no anchor nothing settles it out. It was not paused; it was *born* paused. Same
root shape as **#3017**, different status.

**(b) The class is 35,305 rows** (sub-second `commence_time` within 5 min of `created_at`, 2026+),
across every family. The residue that is stuck is **120 non-terminal rows**; the rest drain to
`closed`. Named-league soccer is 285 rows historically, all but five `closed` — and that five is
`soccer_epl / suspended`, i.e. exactly this issue, isolated without ever mentioning `external_id`.

**(c) The symptom moved in both directions in 23 hours:**

| surface (identical URL) | #3016, 9/4 | now, 9/5 |
|---|---|---|
| `soccer_epl&days=14` | 5 non-terminal of 25 | **0 of 20** |
| `soccer_other&days=14` | 143 of 145 | **196 of 197** (1 scheduled) |

**But all five EPL rows are still `suspended` in the DB**, ~40h after creation. They aged out of the
forward window; they were not fixed. **The page count is a window artifact and will fluctuate on its
own** — fixing the window hides this, only fixing the rows fixes it.

## 7. LOOK (D48) — `/sports/soccer_epl`, phone width

`SHOT_W=390 SHOT_H=844`, 780×9510, PIL-cropped to the top 1800px before Reading (the crop rule holds
a **sixth** session). The page opens on **`Upcoming 19`** with real fixtures and real probabilities
(Newcastle 62% / Bournemouth 38%, Brentford 74% / Sunderland 26%, Brighton 64% / Leeds 36%), each
with a `Proj 2-1` line and a broadcaster. **No `Live & Paused` block above them.** Clean, and it
corroborates §6(c) independently of the payload.

## 8. Ruled OUT — the "Cajamarca pairs" were not duplicates

Search for `Cajamarca` returned rows in suspicious near-time pairs (`19:00:45`/`19:00:41`,
`19:01:03`/`19:00:56`) that an exact-`commence_time` census cannot see. I pulled the rows: they are
**genuinely different fixtures** (`Cajamarca @ Alianza Atletico` vs `Cienciano @ FC Cajamarca`).
**Not a finding.** Checking beat banking it.

Residue worth one line: `Cajamarca` / `FC Cajamarca` / `CU Técnica de Cajamarca` are three distinct
teams whose names collide on one token — team-identity's class (#1204), not a duplicate.

## 9. What I did NOT do

- **Night three** — not due (§0). **Candidate 2** — not due; the queue was wrong (§0).
- Did not re-read §9's two FINAL-0–0 rows, §4c's suspended NCAAF rows, or the receipt bodies — all
  either 16 minutes old or gated on a date that has not arrived.
- Did not run the free cross-bucket `(teams, our_start)` twin detector: 128 ran it 16 minutes prior.

---

# QUEUE FOR lane1/130

## 0. CHECK THE CLOCK FIRST — this has caught TWELVE consecutive sessions

`date -u` and `TZ=America/Los_Angeles date` as your first command. **Night three's window opens
Sun 2026-09-06 06:40Z.** At/after it, §1 is genuinely due and is the only reading that expires.
Before it, say so in one line and move on.

**And check the DATED claims below against that clock before spending a session on one** — 129 found
128's "the two Sep 6 games have now been played" was false by 34 hours. A 3am restock can date its
own "now" a day forward.

## 1. FIRST (if due) — night three, poll TWICE

`GET /api/admin/celery/task-metrics/anchor_schedule_sentinel`, at **~06:47Z and again ~06:57Z**.
Night two started 06:48:45Z — 8m05s after its crontab minute — and at 06:47:56Z the metrics still
served the previous night's row. **A stale `last_started_at` before 06:57Z is not an absence.**
Anything `< 2026-09-06T06:40Z` is a previous night's row.

Night-two baseline and the full grading table: read `#2983#issuecomment-5550146235` first. Carried
verbatim: `complete` is a conjunction (source line 696) — **name which conjunct fired**.

| condition | verdict |
|---|---|
| `pass_open: true` **with** `resumed_from` non-null | migration path wrong — a finding |
| `resumed_from: null` **or** `restarted_from_exhausted_cursor: true` | **P1, its own issue** |
| `complete: true` on night three | investigate before celebrating |

Night three's `complete: false` **is the repair working — do not file it.** `hard_kills_24h` is
settled at 0. Do not chase the 8-minute late start. Night four (Mon 9/7) is the first night that can
close **#2978**.

## 2. SECOND — the twin test (scoped to ONE sport)

```sql
SELECT e.id, e.away_team_name, e.home_team_name, e.commence_time, e.espn_id, e.external_id,
       (SELECT count(*) FROM odds_snapshots o WHERE o.event_id = e.id) AS snaps
FROM events e WHERE e.sport_id = 1
  AND e.commence_time >= '2026-12-06' AND e.commence_time < '2026-12-10'
ORDER BY e.commence_time
```

**Baseline, confirmed FOURTEEN times: exactly 13 rows**, `15304746` `external_id NULL` / 0 snaps.

| result | verdict |
|---|---|
| 13 rows, `15304746` now has `external_id` + snaps | **durable matching worked.** Say so on #2693 |
| 13 rows, still NULL / 0 snaps | not yet exercised. **Not a finding.** Record the time, move on |
| **14 rows** | **twin reproduced in the wild.** File hard, both ids, link #2693 |

Run the `sport_id <> 1` variant **only when the 13 changes** — that is the correct trigger.
`uq_events_espn_id` cannot catch the 14-row case (partial on non-null `espn_id`). **File, don't fix** (D35).

## 3. THIRD — the gate reading. Day 2 starts 9/6.

`GET /api/admin/statpal/authority-agreement`. **Day 1 has now been read THIRTEEN times on one
calendar day (116–129).** If you run on 9/6 that is **day 2 — the first genuinely new row.**
Day 1 of 7; earliest flip Fri 2026-09-11.

**READ THE KEYS AT THE RIGHT LEVEL — 129 banked this, do not re-derive:** `pct`,
`ours_covered_pct` and `gate` are **NOT** keys of `agreement`. They are
`agreement.identity.pct`, `agreement.identity.ours_covered_pct`,
`agreement.identity.governing.gate`. Reading them on `agreement` returns `None` **silently**.

- **sport row (6):** `agreement, last_pass_at, live, pass_age_seconds, sport_key, stamper`
- **`agreement` (12):** `anchors, denominator, denominator_is, excluded, identity, read,
  read_failures, receipts, schedule, sources_read, sport_key, window`
- **`identity` (8):** `both, governing, governs, ours_covered_pct, ours_only, pct, statpal_only,
  statpal_only_by_horizon`

**Baseline, held at 128 AND 129:**

| sport | both | ours_only | statpal_only | anchored/unanch/mismatch/polluted | live dup_ids |
|---|---|---|---|---|---|
| NFL | 321 | 1 | 0 | 247 / 26 / 0 / 48 | 0 |
| MLB | **158** | **64** | 65 | 135 / 0 / **23** / 0 | 5 |
| NBA | 41 | 0 | 1165 | 41 / 0 / 0 / 0 | 2 |
| NHL | 32 | 0 | 1372 | 27 / 5 / 0 / 0 | 3 |

NFL `pct 99.69 · ours_covered_pct 99.69 · bar 99.5 · MEETS`. NBA `pct 3.40 · ours_cov 100.00 ·
MEETS`; NHL `pct 2.28 · ours_cov 100.00 · MEETS` — both score on `ours_covered_pct` alone (**D63**).
MLB is `PENDING-NO-GOVERNING-NUMBER`. **Run the arithmetic check**
`anchored + unanchored + mismatch + polluted = both` (129: all four pass).

**MLB's step went 22 → 23 → held 23 → held 23.** Still **one step, not a rate**. Two readings on
*separate days* make it one. **A 9/6 reading is the first such chance.** If `mismatch` tracks `both`
1:1, file on #3094.

**RECEIPT BUCKETS CAP AT 40** — `RECEIPT_CAP = 40`, `backend/app/utils/authority_agreement.py:86`.
NFL `polluted_column` is truly **48**, MLB `statpal_only` 65, NBA 1,165, NHL 1,372. **Never size a
repair off a list reading exactly 40.**

Banked, do not re-derive: `excluded` / `statpal_only_by_horizon` (125); NFL `statpal_placeholders 7`,
all other `excluded` 0. **You do not bank the 7 daily rows** — the measurement bus does.

## 4. #3154 — watch `live.duplicate_ids` every session

**Baseline: 10 groups — MLB 5, NBA 2, NHL 3, NFL 0** (held 127, 128, 129). A change in any is worth
a line; a rise is a finding. `MAX_ABSORPTION_SEPARATION_SECONDS = 21600`; MLB fid `1329192512`
(`15295964`/`15296101`) is a real doubleheader at **exactly 21600.00s** passing all three gates.
**Do not fix, do not move the constant, do not widen `matchup_agrees`** (D35 + needs a ruling).

## 5. The duplicate families — football CLOSED, non-football now MAPPED (129)

**Do not re-run either census.** Football (#2866 47 cross-sport / #2819+#2321 11 / #3172 3 NCAAF) is
closed. Non-football, 129:

| family | ids | groups | rows | cross-sport | same-sport |
|---|---|---|---|---|---|
| basketball_* | 11 | 192 | 571 | 0 | 192 |
| icehockey_* | 10 | 2 | 6 | 0 | 2 |
| soccer_* | 60 | 2,035 | 8,642 | 1,923 | 112 |

**0 NULL/blank team names in all three** — the `GROUP BY` artifact is ruled out.

**849 groups × 7 leagues = 5,943 rows are #3176** and are accounted for. What is **NOT** examined:

- **soccer's 1,057 groups of size 2** (2,114 rows) — the likeliest true-twin population outside MLB.
- **basketball's 192 groups**, mode at 3 (91 groups of 3, 69 of 2, 20 of 4, and 3 groups of 8).
  All same-sport. Nobody has looked at a single row.
- icehockey's 2 groups (6 rows) — trivially small, worth 2 minutes.

**These are 130's strongest lead.** Scope one family at a time; the whole-table `GROUP BY` times out.

## 6. Everything else — carried forward unchanged

§3b (candidate 2 CLOSED, `live.anchors` = TABLE vs `agreement.anchors.anchored` = COLUMN, MLB's
legacy `s6:` namespace, #2879 step 3 = DELETE 65 + UPDATE 29 and **not lane1's**), §4b/§4c (#3172's
three NCAAF twins, history splitting in opposite directions, **do not pick a survivor**), §5 (#3093's
94 groups, the LOSER holds ~2× the win-prob history, **any merge unions snapshots**), §5b (NFL
`off_by_hours 26` = 24 flex placeholders, `wrong_day` under-reports by 2), §6 (row B / #3070), §7
(MLB mismatch misfiled, authority lane's), §8 (six twin pages already shot — **do not re-shoot**),
§9 (the two FINAL-0–0 rows — **do not re-read until at least 9/6**), §10 (banked facts), §12 (filed
list), §13 (don't rebuild), §16 (pre-checks) — all as written in the 129 queue. Read
`artifacts/REPORT-LANE1-128.md` and `-127.md` for the full text.

**Pre-checks, both held at 129:** contested `espn_id` **0** (13th consecutive zero); duplicate
`statpal_fixture_id` **mlb 5 · nba 2 · nhl 3 · nfl 0**.

## 7. Filed at 129

- **#3176** (NEW, p2, `type:bug` `area:backend` `matching-symptom`) — the seven-league soccer
  fan-out, 5,943 rows. **Lane1's class, filed not fixed, unclaimed.** Bounded and not currently
  user-visible; **do not build a repair.**
- **#3016** (`#3016#issuecomment-5551172054`) — the ingest-clock `commence_time` discriminator, the
  35,305-row class, EPL drained / `soccer_other` grew 143 → 196. **Not lane1's (frontend +
  event-creation). Did not claim it.**

## 8. Candidates for 130, in order

1. **Night three, if past 06:40Z on 9/6.** Twelve sessions have been unable to take it. Only thing
   that expires.
2. **#3172's two Sep 6 games** — genuinely playable only after ~9/6 23:30Z. Did either twin settle,
   and **did the result land on the row holding the win-prob history or the other one?** First
   chance to watch the defect resolve live.
3. **Soccer's 1,057 groups of 2, and basketball's 192** (§5). Wholly unexamined; #3176 came out of
   the same census and these are what it left behind.
4. **Does MLB's `mismatch` track `both` 1:1?** (§3). A 9/6 read is the first on a different day.
5. **Did the 6 suspended NCAAF rows drain?** (129 did not check — 16 min after 128's read.)
6. **The macOS and iPad targets** — cheap ~20 min, low yield, would let #2866 drop an asterisk.

**Calendar:** NFL kickoff **Thu 9/10 — five days** (Week 1 verified clean). Earliest StatPal flip
**Fri 2026-09-11**. Night four (Mon 9/7) is the first night that can close **#2978**. **Late
December:** check the `off_by_hours` 26 → ~2 drain.

## 9. Traps — new from 129

- **A restock written at 3am can date its own "now" a day forward.** 128's "the two Sep 6 games have
  now been played" was false by 34 hours and would have burned a session. **Check a queue's dated
  claims against the clock before acting on one** — including this queue's.
- **A payload's headline numbers can live one level deeper than the prose implies, and read as
  `None` rather than erroring.** `agreement.pct` is not a key; `agreement.identity.pct` is. A
  silent `None` looks like a missing value, not a wrong path. **Enumerate at every level.**
- **A sharp mode in a group-size distribution is a structure, not organic duplication.** 852 groups
  of *exactly* 7 was one mechanism writing one list seven times. Read the distribution before the total.
- **Rule out the `GROUP BY` NULL-collapse artifact before believing any duplicate census.** NULL
  team names group together and manufacture giant fake groups. 129 checked: 0 in all three families.
- **A symptom can drain while its rows persist.** #3016's EPL count went 5 → 0 because the rows aged
  out of a forward `days=14` window, not because anything was fixed. **A count on a windowed surface
  is not a population.** Ask what the window is before reading a drop as progress.
- **Two suspicious rows seconds apart may be different fixtures sharing a name token.** The
  "Cajamarca pairs" were real distinct matches. Pull the rows before filing.
- **Search ranks by recency**, so a historical population will not surface there — absence from
  search is not absence from the database.

**Carried forward (unchanged, all still binding):** enumerate the container before trusting any
"read all N"; a census grouping by `(id, partition)` cannot see a cross-partition duplicate; a
census's IN-list can be narrower than its name; two published numbers can share a word and measure
different objects; read receipt bodies not bucket counts; a bucket at exactly the cap is a
truncation; body-first additions usually beat new filings; **a "new" bug in a class you just
characterised is the MOST likely duplicate — 129's #3016 find was already filed, and checking beat
banking it**; don't re-read a dated baseline that is minutes old (128→129 was **16 min**); a count is
not a rate without a timestamp column; the full trap list in the 129 queue §14 and
`artifacts/REPORT-LANE1-128.md`.

**Rails:** `/events/{id}` valid, `/event/{id}` not; use `www.bainluck.com`; `look.sh` at
`~/bainluck/tools/look.sh`, run with `cd /Users/bain/bainluck && …` and a 300s timeout;
**PIL-crop a tall shot before Reading it** (129's was 780×9510 — the crop rule holds a sixth
session); `SHOT_W=390 SHOT_H=844`; `/api/events/search` results under `results`;
`/api/leagues/{key}` has `upcoming_games` + `recent_results`; `/api/events?sport=…&days=N` returns a
bare list; `authority_agreement.py` is under **`app/utils/`**; `events` has `created_at` but **no
`updated_at`**; `odds_snapshots`/`win_prob_snapshots` use `captured_at`; `event_provider_anchors`
uses `first_seen_at`; db-query needs a python file and a `'rows' not in d` branch FIRST; scope any
`GROUP BY (teams, commence_time)` by sport family or it times out; run `gh` from the worktree.

Stage any cert with `tools/stage-cert.sh`. Merge gates 13 + 18 before ANY merge. D48: mystery-shop
your domain before and after any ship — **the shot comes first**. Self-restock 131 when done; leave
no window idle. Do not end with a question.
