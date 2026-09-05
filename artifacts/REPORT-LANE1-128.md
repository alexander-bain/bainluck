# lane1/128 — night three still not due (11th session), twin holds a 13th time

**PILLAR: MATCHING · TRUTH. SHIP: the Monday Night Football game stays ONE game** — Dallas Cowboys
@ Seattle Seahawks, Dec 7, event `15304746`. Live and still a single row.

Session ran Sat 2026-09-05, **10:03Z → 10:45Z / 03:03–03:45am PT** (stamped from
`TZ=America/Los_Angeles date`; notice 24 — the Mac's clock is EDT, PT is `date` minus 3h).

**Headline: the football-family duplicate census was narrower than its name. Widening it to all
nine `americanfootball_*` sport ids surfaced a third duplicate population — 3 NCAAF games that
exist twice, two of them playing tomorrow, and one that finished 33 hours ago showing a fan "No
result reported" and a live countdown beside its twin's "Final · Illini WON 42–23". Filed #3172
(p1).**

---

## 0. Clock — §1 NOT due, eleventh consecutive session

`date -u` at session start: **2026-09-05 10:02:59Z**; `TZ=America/Los_Angeles date`:
**Sat Sep 5 03:02:59 PDT 2026**.

Night three's window opens **Sun 2026-09-06 06:40Z**. I was **20.6 hours short**. I did not poll
`anchor_schedule_sentinel`, and I am not reporting an absence. Sessions 118–128 have now all been
handed a §1 in the future.

127 ran at 09:40Z — **22 minutes** before me. Per §14 I ran §2/§3/§16 because they are cheap and
required, but I am not dressing a 22-minute-old re-read as a data point.

**Night four (Mon 9/7) is still the first night that can close #2978.**

## 1. §2 twin test — 13 rows, thirteenth consecutive hold

`sport_id = 1`, `commence_time` in `[2026-12-06, 2026-12-10)`: **exactly 13 rows**. `15304746`
still `external_id NULL` / **0 snaps**; the other 12 carry both ids and 798–826 snaps
(byte-identical to 127). **Not a finding** — record and move on.

The 13 did not change, so per §2 I did **not** run the `sport_id <> 1` variant. That is the
correct trigger.

## 2. §16 pre-check — 0, twelfth consecutive zero

- contested `espn_id`: **0**
- duplicate `statpal_fixture_id` census: **mlb 5 · nba 2 · nhl 3 · nfl 0** — unchanged (#3154
  baseline holds)

## 3. §3 gate reading — day 1, twelfth read; MLB did NOT move again

Payload `generated_at 2026-09-05T10:03:38Z`. Enumerated keys at every level before reading values
(top: `gate`, `generated_at`, `spec`, `sports`; `sports` is a **list** of 4; each row has 6 keys;
`agreement` has 12; `receipts` has 6 buckets).

NFL identity, identical for the twelfth time: `both 321 · statpal_only 0 · ours_only 1 ·
pct 99.69 · ours_covered_pct 99.69 · bar 99.5 · gate MEETS`. Schedule `within 293 ·
off_by_hours 26 · wrong_day 2` (explained, §5b of the queue — not re-measured).

**MLB held.** `both 158 · statpal_only 65 · ours_only 64 · anchors 135/0/**23**/0 ·
pct 55.05 / ours_covered_pct 71.17` — byte-identical to 127's 09:40Z read. So candidate 4's step
was 22 (125) → **23** (127) → **23** (128), held across 23 minutes. **Still not a rate.** Two more
readings on separate days are what would make it one.

Arithmetic check `anchored + unanchored + mismatch + polluted = both` **passes on all four sports**:
NFL 247+26+0+48=321 · MLB 135+0+23+0=158 · NBA 41+0+0+0=41 · NHL 27+5+0+0=32.

`live`: NFL `247/247/0/0` · MLB `80/80/0/5` · NBA `41/41/0/2` · NHL `27/27/0/3` — unchanged.

**§5's free cross-bucket twin detector: the same 6 MLB pairs as 127**, all in
`ours_only` × `anchor_mismatch`. NFL/NBA/NHL: **0**. No new pairs.

## 4. Candidate 3 answered — and the buckets at 40 are TRUNCATIONS

Opened NBA's and NHL's `statpal_only` for the first time. Both are 40 rows of `scheduled` future
fixtures we do not hold (NBA 7-digit ids, `2026-10-05 → 2027-03-23`; NHL 6-digit,
`2026-09-23 → 2027-04-10`). Nothing anomalous in the rows themselves.

**But the 40 is not the population.** `RECEIPT_CAP = 40`
(`backend/app/utils/authority_agreement.py:86`, applied at 650–657), and the source comment beside
it says the count is never capped, only the list. So:

| bucket | true count | receipts shown |
|---|---|---|
| NFL `polluted_column` | **48** | 40 |
| MLB `statpal_only` | 65 | 40 |
| NBA `statpal_only` | 1,165 | 40 |
| NHL `statpal_only` | 1,372 | 40 |
| NFL `schedule_disagreements` | 28 | 28 (complete) |
| MLB `anchor_mismatch` | 23 | 23 (complete) |

**A bucket sitting at exactly 40 looks like a round number and is a truncation.** 127 read NFL's
`polluted_column` as 40; the population is 48. Filed as a measurement note on
[#2963](https://github.com/alexander-bain/bainluck/issues/2963#issuecomment-5551101240) so a
repair sized off the visible list does not miss 8 rows.

Corollary for D63: NBA and NHL score `MEETS` on `ours_covered_pct` alone, and that number is
structurally incapable of registering the **386 NBA and 105 NHL StatPal fixtures that fall inside
our own span** and which we do not hold. Not a defect, but worth knowing before the number is
trusted.

## 5. THE SESSION'S FINDING — candidate 2, and the census was narrower than its name

### 5a. The football family, fully enumerated

Exact `(away_team_name, home_team_name, commence_time)` groups over **all nine**
`americanfootball_*` sport ids, `commence_time >= 2026-01-01`:

| sport-id combo | groups | rows | owner |
|---|---|---|---|
| `1` + `190411` (nfl + nfl_preseason, cross-sport) | 47 | 94 | #2866 |
| `52556` (americanfootball_other, same-sport) | 11 | 23 | #2819 / #2321 |
| **`760` (americanfootball_ncaaf, same-sport)** | **3** | **6** | **#3172 (NEW)** |

Nothing else duplicates — no NCAAF↔other cross-sport groups, zero for CFL, UFL, FCS and the two
futures keys. **The family is now closed.**

**126's "11 same-sport groups / 23 rows" is exactly the `americanfootball_other` block.** The
population did not grow overnight; 126's "NFL-family" sport-id list omitted
`americanfootball_ncaaf`. I checked this rather than banking the growth as a rate.

### 5b. The three NCAAF groups

```
14793404 / 15265624  UAB Blazers @ Illinois Fighting Illini   2026-09-04 01:00Z  (played)
14793422 / 15265651  Washington State @ Washington Huskies    2026-09-06 20:00Z  (TOMORROW)
1177062  / 15265652  Louisville Cardinals @ Ole Miss Rebels   2026-09-06 23:30Z  (TOMORROW)
```

**No id column collides.** Row A (older) has an `espn_id`; row B has **NULL** `espn_id` and a
**different** `external_id`; `statpal_fixture_id` is NULL on both. Detector reach: `uq_events_espn_id`
**0/3** · contested-`espn_id` census **0/3** · `statpal_fixture_id` census **0/3** ·
`live.duplicate_ids` **0/3** (NCAAF is not one of the four sports the gate payload covers) · an
`external_id` census **0/3**.

**Third population with §4b's structural property**, after #2866's 47 and #3093's 80.

**The creation wave is 100% duplicates.** All three B-rows were created `2026-08-20 04:05:21`, and
that day's *entire* NCAAF wave is 3 rows — 3 of 3 duplicate an existing row, 0 of 3 got an
`espn_id`. Neighbouring days: 8/11 → 12 rows / 11 with espn_id; 9/02 → 3 / 3.

**The history splits in opposite directions**, so #3093's "keep the `completed` row" survivor rule
is undefined here — two of the three games have not been played:

| group | A snaps/wps | B snaps/wps | history on |
|---|---|---|---|
| WSU @ Washington | 337 / **112** | 796 / 0 | **A** (older) |
| Louisville @ Ole Miss | 80 / 0 | 571 / **1581** | **B** (newer) |
| UAB @ Illinois | 225 / 0 | 882 / **21** | B (newer) |

Any merge must **union** snapshots. Picking a survivor loses real history in at least one direction.

### 5c. LOOK (D48) — both rows render and contradict each other

`www.bainluck.com`, `SHOT_W=390 SHOT_H=844`, PIL-cropped to the top 1700px before reading
(originals 780×4862 and 780×5612).

| page | header | hero | chart |
|---|---|---|---|
| `/events/15265624` | **Final** | Illini **WON** 42 – 23, "were 94% pregame" | full curve, Q1–Q4 markers |
| `/events/14793404` | **"No result reported"** + `Next update: 111` live countdown | live-looking **95% – 5%** | empty |

Kickoff was **Sep 3, 9:00 PM EDT — 33 hours before the reading**. The empty chart on the broken row
is *honest* (that row holds 0 win-prob snapshots — I checked, per the standing trap); the hero and
the countdown are not.

`GET /api/events/search?q=UAB%20Illinois` returns **the same game three times**: both twins plus a
third `americanfootball_other` row `15292797`.

### 5d. Scope discipline — the other suspended NCAAF rows are NOT this bug

7 NCAAF rows in `[2026-08-20, 2026-09-06)` are `suspended` with NULL scores, and the league page's
`recent_results` shows 5 of 8 that way. **Only UAB has a twin.** The other 6 kicked off 8–11h
before the reading and no NCAAF row older than that is stuck, so they read as ordinary settlement
lag. UAB is the outlier at 33h, and the reason is that its result landed on the twin. I said so in
#3172 rather than inflating the count. **Re-read next session to confirm the 6 drained.**

## 6. Filed this session

- **#3172** (NEW, p1, `type:bug` `matching-symptom` `area:backend`) — the three NCAAF twins.
- [#2866 comment](https://github.com/alexander-bain/bainluck/issues/2866#issuecomment-5551099181) —
  football family fully enumerated; 126's 11/23 identified as the `_other` block.
- [#2963 comment](https://github.com/alexander-bain/bainluck/issues/2963#issuecomment-5551101240) —
  `RECEIPT_CAP = 40`; this issue's population is 48, not the 40 visible.

Nothing fixed. **D35: matching symptoms are filed until #2693 lands.** No claim taken on #3172
(notice 6 — it is lane1's class but the lane is filing, not building).

## 7. Traps banked

- **A census's sport-id list is itself a filter, and its name can be wider than its list.**
  "NFL-family" omitted the largest football league by row count for at least three sessions. Before
  reading a census's zero, print the id list it actually ran on.
- **A bucket sitting at exactly the cap is a truncation wearing a round number.** Four of six
  receipt buckets read exactly 40 against populations of 48 / 65 / 1,165 / 1,372. Grep for the cap
  constant before sizing anything off a receipt list.
- **A survivor rule derived from settled twins is undefined for unsettled ones.** #3093's "keep the
  `completed` row" has no meaning for a game that has not kicked off, and these three split their
  history in both directions.
- **Check whether the sibling explains the symptom before attributing a population to it.** 7
  suspended NCAAF rows, 1 twin. The twin explains exactly one of them.
- **A duplicate-creation wave can be 100% duplicates and still be tiny.** The 2026-08-20 NCAAF wave
  is 3 rows; all 3 are twins. Small waves with no `espn_id` are worth a glance in every sport.
- **Both-rows-render remains the strongest evidence available** — third session running.
- **Body-first held again**: everything except #3172 was an addition to an already-filed issue.

## 8. Carried forward unchanged

Everything in the queue's §3b, §4, §4b, §5, §5b, §6–§10, §12, §13 is unchanged and was not
re-derived. Specifically **not** touched: night three (not due), the `sport_id <> 1` variant (13 did
not change), the two FINAL-0–0 rows (§9, not before 9/6), #2879 step 3 (authority lane's), the four
already-photographed twin pages, and `off_by_hours` (explained).
