# #10346 pilot — evidence receipts (discover, Wed 10/21 06:59 PM PT / 2026-10-22T01:59:44Z; correction R1–R4 + Design revision Wed 10/21 07:35 PM PT / 2026-10-22T02:35Z)

Event 15319563, Boston Red Sox @ New York Yankees. One completed MLB game, three hand-selected supported takeaways. No ranker, no general lift claim.

## Official result (independent of our DB) — MLB Stats API, fetched 2026-10-22T01:42:27Z
- `/api/v1/schedule?gamePk=849851`: AL Wild Card Series, game 1 of 3 (gamesInSeries=3), Final, BOS 0 @ NYY 9 (`schedule-849851.txt`).
- `/api/v1/game/849851/boxscore` (`boxscore-849851.json`, sha256 5d6b850b…20d9): Schlittler 6.1 IP, 10 K, 2 H, 0 ER, 1 BB, 117 NP; Rice 5 AB, 4 H, 2 HR, 6 RBI; NYY 9 R 12 H; BOS 0 R 3 H.
- `/api/v1.1/game/849851/feed/live` (full response not committed, 802,822 B, sha256 `20fce6408363863a827bcd22284820b832c50a2126722a68e4167a8d8df75f1a`; excerpt committed as `feedlive-849851-excerpt.json` — gamePk, scheduled 2026-09-30T00:00:00Z, Boston Red Sox (111) @ New York Yankees (147), Yankee Stadium, Final 0–9 — which binds event 15319563 to gamePk 849851): first pitch 2026-09-30T00:15:26.152Z; Rice HR #1 bottom 5 (0–2) ended 01:51:35.768Z; grand slam bottom 8 (0–9) ended 03:07:20.698Z; Schlittler's 10th K ended 02:02:23.010Z; final play ended 03:16:33.590Z; decisions W Schlittler, L Tolle.
- Our stored box score (`events.box_score_data`, source espn) agrees on Rice 4 H / 2 HR / 6 RBI — used only as a cross-check, not the authority.

## Dated quotes — production `futures_odds_snapshots`, read by outcome id (3 + 1 ids, no sweep)
| outcome | question | last row before first pitch | first row after final out |
|---|---|---|---|
| 237550446 Kalshi | Cam Schlittler: 10+ strikeouts | 0.185 (bid .18 / ask .19) @ 23:52:03.774634Z | — |
| 237550483 Kalshi | Ben Rice: 2+ home runs | 0.020 (bid .00 / ask .02) @ 23:52:03.774634Z | — |
| 235705604 Kalshi | Yankees win the series (Series Winner) | 0.560 (bid .55 / ask .57) @ 23:51:28.157421Z | 0.805 (bid .79 / ask .82) @ 2026-09-30 03:55:42.969457Z |
| 237426519 Kalshi | Yankees over 7.5 runs (alternative, not shown) | 0.075 @ 23:52:03.774634Z | — |
- The next Schlittler row (00:17:53.884Z, 29.5%, bid .18 / ask .41) is AFTER first pitch and is not used as a pregame number.
- **What the cards print is the served value, not these rows** (`served-admission-excerpt.json`, from the cached `/api/events/15319563/game-markets`, sha256 in the file):
  - Schlittler 10+: `player_props` `pregame_mark` 0.185 (Kalshi 237550446). Strikeouts are outside the typed after-set; no pin instant is served, so the card's recorded time is the stored row above carrying the same 0.185.
  - Rice 2+: the typed one-number expectation `blend_mean` **0.0155**, observed 2026-09-29T23:50:23.519482Z, from Kalshi 237550483 0.02 and Polymarket 238585485 0.011 (both `pregame_pin_5509`; Polymarket 239003725 excluded `pin_after_start`). Printed as a whole percent, **2%**; the two contributors and their times sit in the card's Sources fold. Polymarket 238585485 is a contributor to that one number, not a second story. (`player_props` `pregame_mark` for the same outcome is Kalshi's 0.02, which also prints 2%.)

## Selection rationale (why these three, why this order)
1. **Schlittler 10 K** — founder-labelled preference for this game (#5105, Oct 2); a middle-range expectation that came true. Pitcher.
2. **Rice 2 HR / 6 RBI** — the offensive story (6 of 9 runs), picked for share of the result, not rarity. Hitter. Replaces "Yankees 8+ runs" (7.5%), which would retell Rice's runs.
3. **Yankees win Game 1; series 56% → 80.5%** — consequence on a different question and clock; worded "after Game 1", never "because of". Team/series.
Omitted, all still in the catalogue one tap away: every other prop (505 player props + game lines/team totals/periods/other), including Rice 1+ HR, Schlittler 4+…12+ K ladder, team totals.

## Claims refused
Any clock interval on the card ("23 min before first pitch", "39 min after the final out") — the card says "Pregame" / "After Game 1" and the recorded ballpark time; "2% chance of exactly two homers" (it is 2+); contract mechanics (bid/ask) anywhere a reader sees; a present-tense series standing ("Yankees lead 1–0" — the series has since resolved; the card says "led … after Game 1"); "the win moved the series 24 points"; anything about Game 2; an MLB win-probability leverage number for Rice's first HR (ES03's +11.5 pp is not re-verified here, so it is not shown).

## Local preview (not production) — first render; see the correction section below for the current one
`/events/15319563?highlights=preview` on next dev, production read APIs via curl cache, streams aborted (`shoot.mjs`). `shots/census.json`: phone 390 — 3 cards in a swipe row (scrollWidth 908 / client 366); desktop 1280 — 3 equal columns, same top; tap "See every prop and market" opens the catalogue fold (open false→true) and lands it 80 px from the top at both widths; control without the parameter — 0 highlights, catalogue unchanged. Cookie banner in shots is the fresh-profile consent prompt.

## Correction R1–R4 + Design first-render revision (Wed 10/21 07:35 PM PT / 2026-10-22T02:35Z)
- R1: reader phases "Pregame" / "After Game 1" + recorded time in ballpark time ("Sep 29, 7:52 PM ET"); no intervals anywhere a reader sees.
- R2: Rice prints the served typed expectation (blend 0.0155 → 2%), observedAt = the admitted pin; the "no one was bidding" caveat is gone; the false "midpoint" comment is fixed (0.02 was Kalshi's stored pregame value; bid/ask stay in this file only).
- R3: series detail "Yankees led the best-of-three 1–0 after Game 1"; no series result shown.
- R4: tests pin the phases, the interval/"first pitch"/"final out"/"lead"/"bid"/"asking" bans over fixture AND render, the served literals (cross-checked against `served-admission-excerpt.json`), and the clocks against the committed feed excerpt. 11 mutants, each EXIT 1 on an assertion (`mutants-r1/SUMMARY.txt`).
- Design: no grey number panel; count marks for strikeouts (10 against the 10+ line) and home runs (two marks labelled 5th / 8th · slam, from the box-score HR note) — count marks never carry percent; each chance on one 0–100% bar with fixed label/number columns, so the series' Pregame 56% and After Game 1 80.5% share start and scale; no arithmetic delta; natural card height (`md:items-start`); peek, catalogue button and its fold unchanged.
- Shots (`shots/`, cache-only rig — no new production read, consent accepted with the ordinary Accept button): phone card heights 223/314/252, desktop 223/272/232; tap opens the catalogue fold (false→true) at 80 px; control without the parameter: 0 highlights, catalogue present.

## Design delta on c0 (successor) — Wed 10/21 08:04 PM PT / 2026-10-22T03:04Z
Design's disposition on `c0a5a708e7` (candidate-c0a5a708e7/DESIGN-DISPOSITION.md). Visual/time-format only; no new production or provider read, no change to any probability, source or basis.
- Series leads with its chance change: "Series win chance rose" · "Yankees led 1–0 after Game 1"; Pregame 56% / After Game 1 80.5% on the shared track; a visible "Recorded 29 Sep" cue (reader-local day of each observation's own instant; "29–30 Sep" for a UTC reader). The 9–0 Game 1 result moves into the series Sources fold as dated context. No series result or current chance is stated.
- Rice: "Rice homered twice" · "4 hits · 6 RBI"; the marks read "5th" / "8th · grand slam" — the grand slam is stated once, on its mark.
- One "Sources" fold on every card, at the card's foot: each shown number with its source and recorded time, every contributor where a number combines more than one (Rice: Kalshi 2% + Polymarket 1.1%, each at its own instant). A closed card carries no provider or clock rows. Phase labels stay visible.
- Times are the READER's: `formatRecordedAt` delegates to `preciseObservedAt` (the one precise-stamp formatter, #6343) plus the reader's zone name — "29 Sep, 4:52 PM PDT" (phone rig, Pacific), "29 Sep, 7:52 PM EDT" (desktop rig, Eastern). No hard-coded zone; the exact UTC instant stays in the `<time title>`. Schlittler keeps his stored-row instant (no pin served), Rice his admitted pin, the series each observation's own row — no clock borrowed.
- Phone fit: natural card heights 235/253/252 (were 223/314/252); the rail stretches and every fold sits at its card's foot, so the visible short card leaves 4 px under it (was ~100 px) and the catalogue button follows 12 px below. No clamp, truncation, fixed height or smaller type.
- Large text (root font 150%, `shots-c1/10346-phone-largetext-*`): exposed a defect the c0 fixed columns also carried — the bar collapsed and the percent overran the card. Every chance on a card now sits in ONE grid (paired bars share a track by construction); below 14rem of card width (scales with text size) the phase takes its own line above bar + number. Normal-size phone and desktop keep three columns.
- lane1b advisories on c0: A1 (ballpark ET vs viewer-local chart) is resolved by the reader-local clock above. A3: a new test pins each Rice contributor's instant (and the one number's) to the excerpt; a borrowed-clock strawman (Polymarket given Kalshi's pin) turns it red. A2 (inline whole-percent rounding vs `formatProbabilityPercent`) left as is — identical output for 0.0155, outside this visual/time delta.
- Gates on this tree: jest (pilot + sectionErrorBoundary) 36/36 EXIT 0; `npm run build` EXIT 0; `npm run typecheck` 66 vs baseline 66 EXIT 0; 28 mutants (11 carried R1, retargeted where their line moved, + 17 for this delta), each EXIT 1 on an assertion, none a compile error (`mutants-c1/SUMMARY.txt`). Rig `shoot-c1.mjs` is the r1 rig plus per-viewport timezone, Sources-open and large-text frames; cache-only (only aborted telemetry beacons missed), consent via the ordinary Accept button; catalogue tap opens the fold (false→true) at 80 px on both widths; control without the parameter: 0 highlights, 13 catalogue folds.
- Known, not changed: with a fold OPEN, the stretched siblings grow to match it (on the phone they are off-screen; on desktop the closed siblings' Sources summaries move to the foot).
