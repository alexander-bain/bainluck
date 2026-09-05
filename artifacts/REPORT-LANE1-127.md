# REPORT — lane1/127

**PILLAR: MATCHING · TRUTH. SHIP: the Monday Night Football game stays ONE game** — Dallas Cowboys
@ Seattle Seahawks, Dec 7, event `15304746`. Live and still a single row after **twelve** readings.

Session ran **2026-09-05 09:40Z → 10:15Z** (PT 02:40am → 03:15am; notice 24 — the Mac's clock is
EDT, PT is `date` minus 3h). Predecessor: `REPORT-LANE1-126.md`.

---

## §0 CLOCK — night three NOT due. TENTH consecutive session.

`date -u` → `Sat Sep 5 09:40:13 UTC 2026`. Night three's window opens **Sun 2026-09-06 06:40Z**:
**21.0 hours out.** §1 was not polled and no absence was reported.

118 through 127 have now all been handed a §1 in the future. I also started **18 minutes** after
126, so per the standing trap I did not re-read any dated baseline it had just taken.

**Night four (Mon 9/7) is still the first night that can close #2978.**

## §2 TWIN TEST — 13 rows. TWELFTH consecutive confirmation.

Unchanged. `15304746` still `external_id NULL` / 0 snaps; the other 12 carry both ids and 798–826
snapshots. **Not a finding** — and 126 established why: the ship's population is one.

Did not run the `sport_id <> 1` variant — the 13 did not change, which is the condition §2 attaches
it to.

## §15 PRE-CHECK — 0, ELEVENTH consecutive zero.

`contested_ids = 0` at 09:41Z. `statpal_fixture_id` duplicate census unchanged at
**mlb 5 · nba 2 · nhl 3 · nfl 0**, and `live.duplicate_ids` agrees (NFL 0 · MLB 5 · NBA 2 · NHL 3).
No `IntegrityError` hunt triggered.

## §3 GATE — read (day 1 still). One number MOVED.

Read at 09:40:55Z. NFL/NBA/NHL identical to the banked day-1 row. **MLB moved:**

| field | 124/125 banked | now |
|---|---|---|
| `identity.both` | 157 | **158** |
| `identity.ours_only` | 65 | **64** |
| `anchors.mismatch` | 22 | **23** |
| `anchors.anchored` | 135 | 135 |
| `pct` / `ours_covered_pct` | 54.70 / 70.72 | **55.05 / 71.17** |

One MLB fixture crossed from `ours_only` into `both` and **landed straight in `mismatch`, not in
`anchored`.** Arithmetic still checks: 135 + 0 + 23 + 0 = 158. One data point, not a rate.

---

# FINDINGS

## 1. Candidate 2 is CLOSED — "MLB 80 vs 135" is a NAMING COLLISION plus a legacy namespace

Four queues carried *"why is MLB's `live.anchors` 80 while `agreement.anchors.anchored` is 135"* as
the strongest open question. It is two separate things and neither is an MLB anomaly.

**(a) The two numbers measure different objects.** `agreement.anchors.anchored`
(`authority_agreement.py:585-607`) **never reads the anchor table.** It increments on
`held = r.held_id` — the `events.statpal_fixture_id` **column** — matching the fixture's ref.
`live.anchors` (`admin_providers.py:1875-1886`) reads **`event_provider_anchors`**. They coincide on
NFL (247/247), NBA (41/41) and NHL (27/27) and diverge on MLB, which reads as an MLB defect and is
not one. `denominator_is` exists on the same payload; `live.anchors` has no equivalent `_is` string,
and that absence is what cost four sessions.

**(b) MLB has a second, legacy anchor namespace that `live.anchors` cannot see.** Prefixes actually
present under `source='statpal'`:

```
americanfootball_nfl  247      tennis   225      s6   94
baseball_mlb           80      basketball_nba 41  icehockey_nhl 27
```

`s6:` is the pre-D55 digit-count namespace (#2879). `live.anchors` binds
`like_prefix = 'baseball_mlb:%'`, so it reports **80** while the table holds **174** MLB StatPal
game anchors.

**Filed on #2879** (`#2879#issuecomment-5550979208`). Not fixed — step 3 is the authority lane's
under D50; lane1's half (step 2) is already merged as `8e9d816c`.

## 2. #2879's step 3 is NOT a blanket re-key — 65 of 94 rows would collide

The cutover is clean and visible in `first_seen_at`:

| namespace | anchors | earliest | latest |
|---|---|---|---|
| `s6` | **94** | 2026-08-28 05:03:51Z | **2026-09-04 00:02:21Z** |
| `baseball_mlb` | **80** | **2026-09-04 18:23:14Z** | 2026-09-05 03:02:32Z |

No overlap — the legacy space stopped taking writes before `8e9d816c` deployed and the qualified
space started after. Step 2 works exactly as designed.

What a blanket `UPDATE source_id = 'baseball_mlb:' || split_part(source_id,':',2)` hits:

| bucket | rows |
|---|---|
| already superseded on the **same event** (unique-key violation) | **65** |
| collides with a **different event** | **0** |
| clean re-key | **29** |

`65 + 0 + 29 = 94`. **Step 3 is a DELETE of 65 and an UPDATE of 29.** The zero is load-bearing: no
cross-space twin exists, so step 3 needs no merge decision — it is cleanup, not repair. All 29 clean
rows still have the column matching (29/29, 0 empty).

Two figures corrected on the issue: the population is **94**, not the 91 in the body and the D55
ruling comment, and the id range now reaches **364941** (the `354xxx-355xxx` comment was already
stale at 364938). Also predicted there: **`live.anchors` for MLB will jump 80 → 109 when step 3
lands** — not a regression.

## 3. #3093's population is ~1.8× bigger than filed, and the LOSER holds most of the history

Candidate 3 (the receipt bodies, never opened by any session) paid out immediately. Cross-checking
receipts within each sport on `(teams, our_start)` surfaced **6 MLB pairs sitting in two buckets of
one payload** — `ours_only` holding the `closed`/`suspended` row and `anchor_mismatch` holding its
`completed` twin.

That class is **already #3093** (52 pairs in-window, the 6-digit vs `1329…` split, the receipts
cross-check, the two-space non-absorption — all of it). **Body-first rule now seven-for-seven.**
What is additive:

**Season-wide census.** `(away, home, commence_time)` over `baseball_mlb`, `commence_time >=
2026-01-01`: **94 groups / 188 rows.** By id-space signature:

| signature | groups |
|---|---|
| one 6-digit **and** one `1329…` | **80** |
| two 6-digit / two `1329…` / neither | **0 / 0 / 0** |
| exactly one row carries a fixture id | 14 |

Zero counter-examples in either direction. **No twin pair in this population shares an id space**,
which is exactly why §15's census reports `mlb 5` and sees none of the 80.

**The repair cannot be "keep the `completed` row and DELETE the other."**

| row class | rows | win_prob snapshots |
|---|---|---|
| 6-digit (`ours_only`, `closed`/`suspended` — the loser) | 94 | **25,834** |
| `1329…` (`anchor_mismatch`, `completed` — the winner) | 80 | **13,321** |
| no fixture id | 14 | 0 |

The row that loses on every other criterion carries **roughly twice** the win-probability history.
Combined with §7's already-recorded observation that the loser's chart domain sits *inside* the
winner's, the two point at opposite survivors: **whichever row is kept, the snapshots must be
unioned rather than chosen.**

**The anchor channel cannot drain this class either.** `15295439` is anchored `statpal / s6:362160`
and `15303442` is anchored `odds_api / e5841b22…` — different `source`, so `(source, source_id,
id_kind)` never collides. This is a **cross-provider** twin and the channel is a per-provider drain.

Filed: `#3093#issuecomment-5550996752`.

## 4. LOOK (D48) — a settled game printing the WRONG SCORE, and it is not #2800's symptom

Shot both rows of the pair at 390×844. The `completed` twin `/events/15303442` renders
**perfectly**: `Final`, `Dodgers WON`, `were 70% pregame`, 5–3, inning markers `B3 / T6 / T9 / F`,
five sources.

The `suspended` twin `/events/15295439` contradicts itself on one screen:

```
No result reported · last score 5-3                    Sep 4, 2026 · 10:10 PM EDT
Dodgers          99 % – 1 %  Aggregate          Nationals
   5                                                 1
Next update: 111
```

| source | Nationals score |
|---|---|
| `GET /api/events/15295439` → `away_score` | **3** |
| the hero's own chip, `last score 5-3` | **3** |
| the hero's big number | **1** |

`home_score` (5) renders correctly, so it is the away slot specifically, and the value printed
equals the away aggregate percentage one line above. **#2800 owns the suspended hero** — but its own
worked example renders its scores *correctly* (`Angels 3 … Yankees 6`) beside the bad 1%–99%, so a
wrong score is a new symptom on that component, not the filed one. Also new there: a live
`Next update: 111` countdown on a game that ended ~5h earlier, and a chart running to **3:37 AM**
against the twin's **12:50 AM**.

Filed: `#2800#issuecomment-5551019386`, with a note that p2 may deserve a re-read now that a score
is in scope. Left to the owner (notice 6).

## 5. NFL's `off_by_hours 26` is 24 flex-schedule placeholders, and `wrong_day` under-reports by 2

Also from the never-opened receipts:

| `delta_hours` | rows | our `commence_time` |
|---|---|---|
| **exactly 5.0** | **24** | **exactly 05:00Z** (midnight EST) |
| 25.0 / 24.0 | 2 | 00:00Z |

Against the events table, `05:00Z` holds exactly 24 NFL rows all season and **every one is dated
2026-12-27 → 2027-01-10 — Weeks 17 and 18**, whose kickoffs the NFL flexes late. Neither side's data
is wrong; both are placeholders.

**Dated prediction:** `off_by_hours` should fall 26 → ~2 on its own as those times are announced in
late December. Not draining by early January is a finding; draining early means something moved the
rows, also worth knowing.

**`wrong_day` under-reports.** `wrong_day_is` is *"more than 1 day, 4:48:00 apart"* = 28.8h, so the
25.0h and 24.0h rows are a full day wrong and counted as `off_by_hours`. **4 NFL rows are ≥24h off;
`wrong_day` shows 2.** This matters directly to §8/#2869, which watches `wrong_day` 2 → 0 as the
drain signal — two rows in that population cannot move that number at all.

NHL has the same artifact at a different offset: its 5 `off_by_hours` are 18.5–22.0h with
`commence_time` at exactly `04:00Z` (midnight EDT), all dated 2026-10-01/02, the opening days. MLB's
schedule side is `158 / 0 / 0` and has none of it, because its kickoffs are published.

Filed: `#2869#issuecomment-5551027405`.

## 6. Confirmed in passing, not re-filed

- NFL's 48 `polluted_column` rows are **#2963's** population — receipts hold
  `column_holds: "statpal_live_Cincinnati Bengals_Chicago Bears"`. Already filed p1.
- MLB's 23 `anchor_mismatch` receipts all hold `1329…` values, confirming §6 / **#3094**.
- **#2737 is a disjoint population** — its 54 twins were found via *contested* `espn_id` (both rows
  had one; name-variant mismatches; only 8 MLB). The contested census is 0 today, so none of my 94
  groups are its.

---

# TRAPS FOR 128

- **Two numbers can share a word and measure different objects.** `live.anchors` (table) vs
  `agreement.anchors.anchored` (column). Four queues treated the gap as an MLB defect. Before
  reasoning from a discrepancy between two published metrics, **read both definitions in source** —
  a payload that documents `denominator_is` but not `anchors_is` is telling you where to look.
- **A migration's step-N sizing goes stale the moment step N−1 deploys.** #2879 reasoned correctly
  in advance that the new key would not collide with the old rows on *write* — and that is exactly
  what made the *re-key* collide, on 69% of the population, one day later. **Re-measure a planned
  repair against the state the previous step created.**
- **Check the id-space signature of a duplicate population before choosing a survivor.** Here the
  loser holds 2× the win-prob history. "Which row is right" and "which row has the data" are
  different questions and they had opposite answers.
- **Read the receipt bodies, not the bucket counts.** Three of this session's five findings came out
  of the same never-opened `receipts` object — the twins, the flex placeholders, the `wrong_day`
  threshold. Prior sessions banked the counts for a week.
- **A cross-bucket collision inside one payload is free evidence.** Six twin pairs were sitting in
  two buckets of a JSON object nobody cross-checked.
- **A bucket threshold can be wider than its name.** `wrong_day` at 28.8h hides 24h errors.
- **A same-shot self-contradiction is the strongest evidence there is.** The suspended page's chip
  and its hero disagreed about the same score, on one screen, with the API as tiebreak.
- **Body-first is now seven-for-seven** (#2879, #2737, #3093, #2800, #2958, #2963, #3094). Every
  single thing that looked new this session was already filed somewhere; the value was in the
  *measurement added to it*, never in the discovery.

Carry forward all of 126's traps, and: `information_schema.columns` is a cheap, reliable way to
learn a table's shape before writing a query against it — `event_provider_anchors` has
`first_seen_at`, not `created_at`.

---

# WHAT IS STILL UNREAD

1. **Night three** (Sun 9/6 06:40Z) — eleven sessions have been unable to take it.
2. **The 11 SAME-sport NFL-family duplicate groups** (§4b, 23 rows) — counted by 126, never opened.
   Unlike the 47, some may be visible to an id-space census.
3. **The remaining receipt buckets** — MLB `statpal_only`/`ours_only` (40 each) were read only for
   the cross-check; NBA/NHL `statpal_only` (40 each) not read at all.
4. **The macOS and iPad targets** — would let #2866 drop its asterisk.
