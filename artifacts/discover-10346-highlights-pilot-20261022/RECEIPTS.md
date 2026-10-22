# #10346 pilot — evidence receipts (discover, Wed 10/21 06:59 PM PT / 2026-10-22T01:59:44Z)

Event 15319563, Boston Red Sox @ New York Yankees. One completed MLB game, three hand-selected supported takeaways. No ranker, no general lift claim.

## Official result (independent of our DB) — MLB Stats API, fetched 2026-10-22T01:42:27Z
- `/api/v1/schedule?gamePk=849851`: AL Wild Card Series, game 1 of 3 (gamesInSeries=3), Final, BOS 0 @ NYY 9 (`schedule-849851.txt`).
- `/api/v1/game/849851/boxscore` (`boxscore-849851.json`, sha256 5d6b850b…20d9): Schlittler 6.1 IP, 10 K, 2 H, 0 ER, 1 BB, 117 NP; Rice 5 AB, 4 H, 2 HR, 6 RBI; NYY 9 R 12 H; BOS 0 R 3 H.
- `/api/v1.1/game/849851/feed/live` (not committed, 803 KB, sha256 20fce640…a1a): first pitch 2026-09-30T00:15:26.152Z; Rice HR #1 bottom 5 (0–2) ended 01:51:35.768Z; grand slam bottom 8 (0–9) ended 03:07:20.698Z; Schlittler's 10th K ended 02:02:23.010Z; final play ended 03:16:33.590Z; decisions W Schlittler, L Tolle.
- Our stored box score (`events.box_score_data`, source espn) agrees on Rice 4 H / 2 HR / 6 RBI — used only as a cross-check, not the authority.

## Dated quotes — production `futures_odds_snapshots`, read by outcome id (3 + 1 ids, no sweep)
| outcome | question | last row before first pitch | first row after final out |
|---|---|---|---|
| 237550446 Kalshi | Cam Schlittler: 10+ strikeouts | 0.185 (bid .18 / ask .19) @ 23:52:03.774634Z | — |
| 237550483 Kalshi | Ben Rice: 2+ home runs | 0.020 (bid .00 / ask .02) @ 23:52:03.774634Z | — |
| 235705604 Kalshi | Yankees win the series (Series Winner) | 0.560 (bid .55 / ask .57) @ 23:51:28.157421Z | 0.805 (bid .79 / ask .82) @ 2026-09-30 03:55:42.969457Z |
| 237426519 Kalshi | Yankees over 7.5 runs (alternative, not shown) | 0.075 @ 23:52:03.774634Z | — |
- The next Schlittler row (00:17:53.884Z, 29.5%, bid .18 / ask .41) is AFTER first pitch and is not used as a pregame number.
- Served `/api/events/15319563/game-markets` agrees: Schlittler 10+ `pregame_mark` 0.185. Polymarket Rice O/U 1.5 (238585485) is the same question, not a second story or source.

## Selection rationale (why these three, why this order)
1. **Schlittler 10 K** — founder-labelled preference for this game (#5105, Oct 2); a middle-range expectation that came true. Pitcher.
2. **Rice 2 HR / 6 RBI** — the offensive story (6 of 9 runs), picked for share of the result, not rarity. Hitter. Replaces "Yankees 8+ runs" (7.5%), which would retell Rice's runs.
3. **Yankees win Game 1; series 56% → 80.5%** — consequence on a different question and clock; worded "after Game 1", never "because of". Team/series.
Omitted, all still in the catalogue one tap away: every other prop (505 player props + game lines/team totals/periods/other), including Rice 1+ HR, Schlittler 4+…12+ K ladder, team totals.

## Claims refused
"18.5% at first pitch" (quote is 23 min earlier); "2% chance of exactly two homers" (it is 2+, and a no-bid midpoint — the card says so); "the win moved the series 24 points"; anything about Game 2; an MLB win-probability leverage number for Rice's first HR (ES03's +11.5 pp is not re-verified here, so it is not shown).

## Local preview (not production)
`/events/15319563?highlights=preview` on next dev, production read APIs via curl cache, streams aborted (`shoot.mjs`). `shots/census.json`: phone 390 — 3 cards in a swipe row (scrollWidth 908 / client 366); desktop 1280 — 3 equal columns, same top; tap "See every prop and market" opens the catalogue fold (open false→true) and lands it 80 px from the top at both widths; control without the parameter — 0 highlights, catalogue unchanged. Cookie banner in shots is the fresh-profile consent prompt.
