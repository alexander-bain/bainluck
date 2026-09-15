# native/178 — check 6 on iPad: the named record defect is cleared, and the walk found nothing unfiled

Date: 2026-09-15, 11:10 PT / 18:10Z. Lane: native. Pillars: TRUTH · FORMATTING. Check 6.
Tree: `native/178-check6-ipad-recheck` off `origin/master` `37ad9c4f8`; `ios/**` byte-identical
to `origin/master` (`git diff --stat origin/master -- ios` empty).
Binary: DerivedData `Debug-iphonesimulator`, built 2026-09-15 10:53:56 PT from this tree,
resolved by `tools/native-shoot.sh`'s own newest-wins glob (it REFUSED the 07:06 binary as
stale first, which is how I know the shots are of this tree and not the last one).
Device: **iPad Pro 11-inch (M5)**, `663CB81D-…`, iOS 26.5 — `NATIVE_SHOOT_SIM` override.

## What was open

YOUR-TURN's check 6 row carried exactly one gap, and it named the device:

> **iPhone simulator recheck passed.** Twins/Yankees records match between hero and
> Championship Path, with three production endpoint controls agreeing. Earlier
> chart/probability checks passed. **iPad was not rechecked.**

That is the whole of this session's ship. The defect is **#6230** — the event page printing
two different records for one team (hero `Twins 70-79`, Championship Path `Twins 10-18-1`),
19 of 24 sampled MLB teams disagreeing. Backend half landed (lane1b, v4551); iPhone was
rechecked by native/176. iPad was not.

## 1. #6230 on iPad — PASS, three surfaces, one number each

Specimen: `bainluck://events/15312201`, the issue's own event (Twins v Yankees).

| surface | shot | Yankees | Twins |
|---|---|---|---|
| event page **hero** | `ipad-01-hero.png` | **87-63** | **70-80** |
| **Championship Path** card, same page | `ipad-02-scroll2000.png` | **87-63** · American League | **70-80** · American League |
| **search** team row | `ipad-03-search-yankees.png` | **87-63** MLB | — |
| served payload (`/api/events/15312201`) | — | 87-63 | 70-80 |
| served payload (`/api/events/15312201/team-progression`) | — | 87-63 | 70-80 |

The two endpoints that disagreed in the issue body now agree, and the two views that
printed the disagreement now print the same number. **No W-L-D shape anywhere** — the
`10-18-1` fingerprint (a tie-bearing ~30-game record on a no-tie sport) is gone.

Server-side controls, same minute, on the issue's own three events: `15312201`, `15312655`,
`15308644` all return `70-80` / `87-63` from **both** endpoints. Three for three.

The rest of the page corroborates rather than merely not-contradicting: hero `FINAL`
`NYY 8 – MIN 3`; Game Segments innings sum `0+0+1+0+0+0+0+6+1 = 8` and
`0+0+0+0+0+0+2+1+0 = 3`; Runs map `FINAL 11 runs` with its slider dot at 11 on a 4–14+
scale; Win Probability ends at 0% on the MIN axis, i.e. the Yankees, who won.

**iPad layout itself is sound** — two-column Championship Path and Season Futures, full-width
charts, no clipped labels, no iPhone layout stretched across the width. Not the ship, but it
is what a reader would judge first and it is not a defect.

## 2. What the bounded nearby walk found — two defects, both ALREADY FILED, zero new issues

Per D48 / notice 42 I walked the adjacent reader path (search → team → event, then the
Discover landing). Both things I saw were real and both were already open. **Commented, not
re-filed** (notice 6, launch-week 49(c)).

### `FINAL 0 - 0` on the Yankees search page → **#5841** (open, p2)

Two rows on the first screen of `q=Yankees`: `Boston Red Sox vs New York Yankees 0 - 0 FINAL`
and `New York Yankees vs Baltimore Orioles 0 - 0 FINAL`. A baseball game cannot end 0-0.

Re-measured on **#5841's own 45-day window and predicate**, so the number is comparable and
not merely fresh: **18 rows, the same 18** — two days on, nothing aged out, nothing joined.
(60 days adds exactly one, `15181828`; outside the issue's window, so not growth.)

The contribution to that issue is a **cause cross-link nobody had made**. Its MLB half:

| id | fixture | commence → `completed_at` | named in #2480 |
|---|---|---|---|
| 14877917 | Red Sox @ Yankees 08-29 | **90 min** | ✅ |
| 15198906 | Angels @ Rangers 08-22 | **89 min** | ✅ |
| 15228871 | Pirates @ Padres 08-26 | **88 min** | ✗ (same shape) |
| 15201192/93/94/95 | four fixtures, all 08-18 | **`completed_at IS NULL`** | ✗ (different mechanism) |

Three of three datable rows sit in an 88–90 minute band. **#2480** — "a 90-minute timer closes
live games and stamps the current score as final", **p0** — already lists two of them **by id**.
So #5841 is p2 on rows a p0 owns, and neither issue referenced the other.

**That cross-link is historical, and this receipt originally stated its cause in the present
tense. Corrected — the producer is fixed and the recurrence is measured at zero.**

`b90f97fa` ("a game is not over because 90 minutes passed", 2026-09-01 10:43Z) is an **ancestor
of master**, so #2480's title and PR #2502's still-OPEN state are stale as code-presence
signals. Read on `origin/master` rather than inherited: `detect_and_close_stale_events` now
calls `get_max_duration_for_sport` **and** `game_may_still_be_running`, and its elapsed-time arm
marks a row `suspended`, not `closed` — only a StatPal end time closes one. `MIN_HOURS_BEFORE_
STALENESS_CHECK` survives as the query floor only.

Measured against production, MLB, `completed_at − commence_time` inside the 80–100 min band:

| month | finished rows | in band | avg min | `0 - 0` |
|---|---|---|---|---|
| 2026-06 | — | 60 | — | — |
| 2026-07 | — | 23 | — | — |
| 2026-08 | 370 | 25 | 181 | 3 |
| 2026-09 | 270 | **0** | 178 | **0** |

The band's last row commences **2026-09-01 01:40Z**, nine hours before the fix released, and
nothing has joined it since. The denominator is carried deliberately so the zero cannot read as
an empty population: **270 MLB rows finished in September** at a 178-minute average — a real
ballgame — and none of them is in the band or scored 0–0.

So the two halves separate: **the producer is not recurring; the 18 old rows are residual data
that no backfill has repaired**, and they are what the reader still meets on the first page of
`yank` on the build Alex is walking. The repair is a data repair, not a guard rebuild — nobody
should rebuild that guard from the old issue title.

The other four (`15201192/93/94/95`) are **not** #2480: no `completed_at` at all, so no
90-minute stamp ever happened, yet each carries an `espn_id` while `external_id IS NULL`. A
row that is `closed` with no `completed_at` refutes itself with no ground truth needed.

Checked before asserting any of it, so the class is not overstated: **soccer 0-0 finals are
real** (0-0 draws), all carry `completed_at`, and they are correctly excluded. The tennis half
is **#2772**'s and its intervals run 4–497 min — not a second instance of the 90-minute
closer. One tennis row (`15187910`) has `completed_at` **47 min BEFORE** `commence_time`; that
is **#2484**'s shared-placeholder kickoff, not the gotcha-#46 cross-event merge it resembles.
I sized that class (59 rows / 45 days, 26 of them WTA Canadian Open) and did **not** file it:
the population is dominated by the sport whose kickoffs #2484 already explains as placeholders,
so a new issue would have asserted a cause the data does not support.

### Two Brazil election cards in one iPad viewport → **#6400** (open, p1, filed 40 min earlier)

Discover's iPad two-column layout puts the pair **side by side in one screenful**:
"Brazil Presidential Election" (Resolves Oct 3, Bolsonaro **52%**, Polymarket) beside "Brazil
Presidential election winner?" (Resolves Oct 25, Bolsonaro **54%**, Kalshi).
`ipad-05-brazil-pair-one-viewport.png` (crop of `ipad-04-discover.png`, full frame kept).

#6400 has the mechanism right and I added nothing to it but geometry: its title says "one
screen apart", which is the iPhone/web framing. On iPad a reader does not have to remember the
first card to see the contradiction — the contradiction is the screenshot. Severity read, not
a new defect. Rendering is faithful on both sides, so nothing here is native's to fix.

## Scope

Both findings are served values, `area:backend`, outside native's file set — recorded and
routed, **not claimed** (notice 41, the same disposition #6230 itself was filed under). No
client-side mask was built for the 0-0: suppressing it would need a per-sport no-ties rule in
the client, and it would delete the alarm while leaving the wrong row in the database.

**No new issues filed. No app code touched. This diff is artifacts only** — and per int375's
note that is still not free (`artifacts/**` is outside the frontend allowlist, so it forces a
Heroku release), so it should ride a batch rather than be pushed alone.

## Check 6 after this session

| device | named #6230 defect | state |
|---|---|---|
| iPhone | hero vs Championship Path | ✅ native/176 |
| **iPad** | hero vs Championship Path vs search | ✅ **this session** |

The gap YOUR-TURN names for check 6 is closed. What remains on that row is the final-device
walkthrough, which is Alex's and belongs to milestone 3.
