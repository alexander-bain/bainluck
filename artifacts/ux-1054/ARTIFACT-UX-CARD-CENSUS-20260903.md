# ARTIFACT-UX-CARD-CENSUS-20260903 — every rendering of an event/market card on the web

**Queue:** ux/1054 item 3 · **Pillar:** FORMATTING · **Ship this feeds:** Fable's card-system
proposal — the one grammar every card on the product is drawn in.

**Alex, 2026-09-03 3:45pm PT:** *"we keep reinventing how to show an event card all over our
product."*

**Status: MEASUREMENT ONLY. No fixes in this pass**, per the queue. Three defects fell out of the
photography anyway; they are recorded in §4 with evidence and are **not** repaired here.

---

## 0. How this was measured, and what the count actually is

Every row below was reached two ways and both had to agree:

1. **Photographed on production** (`https://www.bainluck.com`) at **390×844** and **1440×2400**,
   `deviceScaleFactor: 2`, full-page, via `tools/shop-shot.mjs`. Shots are in
   `artifacts-ux-1054/census-<surface>-<width>.png` (local paths only — shop evidence never enters
   the repo).
2. **Traced in source** from the route file down through the dispatcher to the leaf that draws the
   markup, so a row names the file that actually renders rather than the file that imports.

**The brief's count was ~30 distinct named card components. The measured number of RENDERINGS is
40, and it is not the same set** — that gap, in both directions, is the finding:

| | |
|---|---|
| Files named `*Card*.tsx` under `frontend/components` | 32 |
| …excluded here as not-a-card (`SkeletonCard`, `EventCardShell`, `EndOfFeedCard`, 3 × `admin/*Card`) | 6 |
| **Renderings of an event/market card a reader can reach** | **40** |
| …drawn by a file named `*Card*.tsx` (24 distinct files; `FeedCard` draws two of them) | 25 |
| …drawn by something **not called a card** — rails, boards, grids, rows, tables | **15** |

So a name-based inventory **over**-counts by six and **under**-counts by fifteen:
`LeagueGameRail`, `TournamentMatches`, `TournamentResults`, `MatchupsRail`, `HubUpcomingRail`,
`GolferRow`, `MoversRibbon`, `PropDivergenceRail`, `TournamentProps`+`MatchProps`,
`LeagueMarketSection`'s three internals, `TournamentBoard`, `PlayoffGrid`,
`TournamentProgressionTable`, `TournamentBracket` and `LeagueBinaryBoard` each draw a card and
none of them is called one. **Any card-system proposal keyed on the filename misses well over a
third of the surface area.**

The duplicate-filename observation in the brief holds and is worth stating precisely:

| Name | Two files | Same job? |
|---|---|---|
| `EventCard.tsx` | `components/EventCard.tsx` · `components/discover/EventCard.tsx` | **No.** Different layouts, different data, different states. See rows G1/G2. |
| `FuturesCard.tsx` | `components/FuturesCard.tsx` · `components/discover/FuturesCard.tsx` | **No.** 428 vs 764 lines; the Discover one owns four sub-cards. Rows O1/O2. |
| `TournamentCard.tsx` | `components/TournamentCard.tsx` · `components/discover/TournamentCard.tsx` | **Partly.** 426 vs 115 lines; the Discover one is a thin card, the other carries routing law. Rows T1/T2. |

---

## 1. Kind legend

`game` · `outright/futures` · `prop ladder` · `tournament grid` · `yes/no question` · `other`

---

## 2. The census

Screenshot column gives the surface shot; where a card sits far down a tall page the y-band is
named so the crop is reproducible with `tools/crop.py`.

### GAME — two parties, one contest

| # | Rendering | File | Surfaces | Shot (390 / 1440) | Shows |
|---|---|---|---|---|---|
| G1 | Discover game card | `components/discover/EventCard.tsx` | `/`, `/discover` | `census-discover-*` y≈2200 | Hero band w/ crests + live score + LIVE/TRENDING chips + dismiss ×; title `Away @ Home`; duel % pair + SignalBars + split bar; state caption; **settled adds a `Pre-match` pair** (see §3); Like/Share |
| G2 | Compact game card | `components/EventCard.tsx` | `/search`, `/sports/[key]`, `/my-stuff`, `/preferences`, and **inside `LeagueGameRail`** | `census-search-*` y≈250 | League chip; time-or-state; two parties w/ initial avatars; duel % + split bar; footnote line (`Proj 12-20`, `Opened 48/52`); broadcast (`MLB.TV`) |
| G3 | Feed game card | `components/FeedCard.tsx` → `EventFeedCard` (internal) | `/sports`, `/categories/[slug]` | `census-sports-*` | FINAL/live chip; league chip; date; team rows w/ logos and **per-team pre-match %**; score column; reason badge; `Pre-match` caption; thumbs up/down |
| G4 | League game rail | `components/LeagueGameRail.tsx` (wraps G2) | `/sport/[sport]/[league]` ×2 (Live&Upcoming, Recent Results) | `census-league-mlb-*` y≈600 | Two-up grid of G2; `settled` variant flips to result-first |
| G5 | Team game cards | `components/TeamGameCards.tsx` | `/sport/.../team/[team]` | `census-team-padres-*` | Probability-first before, result-first after; chip honesty logic lives here and nowhere else |
| G6 | Hub slate match row | `components/tournament/TournamentMatches.tsx` | `/tournaments/[slug]` | `AFTER-hub-*` | Round pills; player avatars + seeds; duel %; move chip; TBD/`in_progress` state; freshness label; broadcast; empty state (§4b) |
| G7 | Hub finished match row | `components/tournament/TournamentResults.tsx` | `/tournaments/[slug]` | `AFTER-hub-desktop-1440` y≈500 | Avatar + name + `WON`; pre-match % per player **+ source marker**; set-by-set score; retirement/walkover completion; section legend |
| G8 | Concept matchups rail | `components/event/MatchupsRail.tsx` | `/event/[domain]/[slug]` | `census-event-*` | Fight/leg rows; result-or-time; no probability pair |
| G9 | Hub upcoming rail | `components/hub/HubUpcomingRail.tsx` | `/hub/[competition]` | not shot — see §5 | Minimal upcoming list; **no probability, no state, no sources** |
| G10 | Game play card | `components/GamePlayCard.tsx` | `/events/[id]` | `census-event-*` | Single play/moment w/ sparkline |
| G11 | Resolution card | `components/discover/ResolutionCard.tsx` | `/discover` | `census-discover-*` | "This resolved" tile; outcome only |

### OUTRIGHT / FUTURES — one field, many candidates

| # | Rendering | File | Surfaces | Shot | Shows |
|---|---|---|---|---|---|
| O1 | Discover futures card | `components/discover/FuturesCard.tsx` (764 ln) | `/`, `/discover` | `census-discover-*` | Image header; question; top outcomes w/ % and movement; sources; actions; **hosts GroupCard/ComparisonCard/ThemeBundleCard** |
| O2 | Futures card | `components/FuturesCard.tsx` (428 ln) | `/search`, `/my-stuff`, `/preferences` | `census-search-*` | Image; question; leader-first outcome list; movement; sources; no actions |
| O3 | Feed futures card | `components/FeedCard.tsx` → `FuturesFeedCard` | `/sports`, `/categories/[slug]` | `census-cat-politics-*` | Third layout of the same idea; outcome list + movement + thumbs |
| O4 | Cross-source feed card | `components/CombinedFeedCard.tsx` | `/sports`, `/categories/[slug]` | `census-cat-politics-*` | Merged outcomes across venues; per-source comparison |
| O5 | Cross-source market card | `components/CombinedMarketCard.tsx` | `/futures/[id]` | `census-futures-*` — **did not render** on `/futures/86832`, see §5 | Merged outcomes across venues; per-source comparison. Source-read only |
| O6 | Award card | `components/AwardCard.tsx` | league pages via `LeagueMarketSection`, `RelatedFutures` | `census-league-mlb-*` | Award name; candidate list; movement; image |
| O7 | Series card | `components/SeriesCard.tsx` | league pages via `LeagueMarketSection` | `census-league-mlb-*` | Series matchup; two outcomes; movement |
| O8 | Search family card | `components/SearchFamilyCard.tsx` | `/search` | `census-search-*` y≈1400 | Backend-composed topical family; member rows = question · leader · % · 24h arrow |
| O9 | Golfer row | `components/golf/GolferRow.tsx` | `/categories/golf`, golf league pages | `census-cat-golf-*` | Player row; % ; movement; source label |
| O10 | Group card | `components/discover/GroupCard.tsx` | `/discover` (inside O1) | `census-discover-*` | Sibling-market cluster; sparkline |
| O11 | Movers ribbon | `components/MoversRibbon.tsx` | `/sport/[sport]/[league]` | `census-league-mlb-*` y≈600 | Team chip + "Championship" + signed move. A card in all but name |

### PROP LADDER

| # | Rendering | File | Surfaces | Shot | Shows |
|---|---|---|---|---|---|
| P1 | Prop group card | `components/PropGroupCard.tsx` | league pages via `LeagueMarketSection` | `census-league-mlb-*` | Rungs w/ threshold + %; movement |
| P2 | Prop divergence rail | `components/PropDivergenceRail.tsx` | `/events/[id]` | `census-event-*` | THE SCRIPT vs THE DIVERGENCE; rung list; settled grading |
| P3 | Hub props | `components/tournament/TournamentProps.tsx` + `MatchProps.tsx` | `/tournaments/[slug]`, `/events/[id]` | `AFTER-hub-*` | Per-match question ladder; freshness per rung |
| P4 | Quantity group / binary row | `components/LeagueMarketSection.tsx` (internal `QuantityGroup`, `BinaryRow`, `MarketCardForSection`) | league pages | `census-league-mlb-*` | Three more inline card shapes with no component of their own |

### TOURNAMENT GRID

| # | Rendering | File | Surfaces | Shot | Shows |
|---|---|---|---|---|---|
| T1 | Tournament card | `components/TournamentCard.tsx` (426 ln) | `/sport/[sport]`, `/sport/.../[league]`, `/categories/golf`, and **inside `FeedCard`** | `census-cat-golf-*` | Field leaders; %; movement; routing law to `/event/<domain>/<slug>` |
| T2 | Discover tournament card | `components/discover/TournamentCard.tsx` (115 ln) | `/`, `/discover` | `census-discover-*` | Thin variant of T1; actions instead of routing law |
| T3 | Contender board | `components/tournament/TournamentBoard.tsx` | `/tournaments/[slug]` | `AFTER-hub-*` y≈900 | Rank; avatar; name; % ; sources count; trend sparkline; move |
| T4 | Playoff grid | `components/tournament/PlayoffGrid.tsx` | `/playoffs/[sport]`, hub | not shot — see §5 | Seed grid; per-cell probability; source count |
| T5 | Progression table | `components/TournamentProgressionTable.tsx` | `/futures/[id]`, league, `/playoffs`, golf | `census-league-mlb-*` | Championship odds table — a grid card in table clothing |
| T6 | Bracket | `components/tournament/TournamentBracket.tsx` | `/tournaments/[slug]` (Bracket tab) | not shot — see §5 | Draw tree; per-tie probability |

### YES/NO QUESTION

| # | Rendering | File | Surfaces | Shot | Shows |
|---|---|---|---|---|---|
| Y1 | League binary board | `components/LeagueBinaryBoard.tsx` | `/sport/[sport]/[league]` | `census-league-mlb-*` | One board per page (ux/1052 item 8); question rows + probability |
| Y2 | Theme bundle card | `components/discover/ThemeBundleCard.tsx` | `/`, `/discover` | `census-discover-390` y≈1800 | Topic chip; "N related"; question rows w/ movement prose + single %; Expand |
| Y3 | Comparison card | `components/discover/ComparisonCard.tsx` | `/`, `/discover` | `census-discover-*` | Two questions side by side; sources; actions |
| Y4 | Concept card | `components/discover/ConceptCard.tsx` | `/`, `/discover` | `census-discover-*` | UFC card / GP / grand tour; live + settled states |

### OTHER

| # | Rendering | File | Surfaces | Shot | Shows |
|---|---|---|---|---|---|
| X1 | Weather wild cards | `components/weather/WildCards.tsx` | `/weather` | `census-weather-*` | City tiles + sparkline |
| X2 | Guess / daily challenge | `components/discover/GuessCard.tsx`, `DailyChallengeCard.tsx` | `/discover` | `census-discover-*` | Interactive, not informational |
| X3 | Player stat card | `components/PlayerStatCard.tsx` | via `GroupedFeedRenderer` | not shot — see §5 | Player line; no probability |
| X4 | Case study card | `components/story/CaseStudyCard.tsx` | `/about` | not shot | Narrative exhibit |

**Not cards, excluded on purpose:** `SkeletonCard`, `discover/EndOfFeedCard`,
`discover/DiscoverSkeletonGrid`, `EventCardShell` (a shell three cards share — the one piece of
existing card *system* in the tree), `admin/DiagnosisCard`, `admin/LabelingCard`,
`admin/SentinelsCard`.

---

## 3. What the census says, in four sentences

1. **Three kinds have six or more independent implementations each.** A game is drawn eleven
   ways, an outright eleven ways, a tournament grid six ways. None of them shares a layout
   primitive; `EventCardShell` is the only shared piece and only three renderings use it.
2. **The `discover/` fork is a whole second product.** Four of the five most-used cards exist twice
   — once for Discover and once for everything else — and the two halves disagree about the hero
   treatment, the state vocabulary, and whether actions belong on a card.
3. **The vocabulary is not shared even where the layout is.** The same fact is called `Opened
   48/52` on G2, `Pre-match †` on G3/G1, a bare grey figure on G7, and `Proj 12-20` on G2's other
   footnote — four spellings of "what was expected before".
4. **Fifteen of the forty renderings are invisible to a filename-based inventory.** See §0.

---

## 4. Three defects the photography turned up (recorded, NOT fixed here) — plus 4d, the opener-treatment count ux/1055 asked for

### 4a. The league page draws every live MLB game twice, with different numbers — REAL, verified in the API

`census-league-mlb-1440.png` y≈600 shows Royals–Marlins twice side by side: `LIVE / 69% / 31%` in
the left column and `Top 7th / 70% / 30% / Opened 53/47` in the right. Same at phone width
(`census-league-mlb-390.png` y≈900: Orioles–Red Sox as `Top 1st 43/57 Opened 48/52` and again as
`LIVE 41/59`).

**It is not a render bug and not a screenshot artifact — the API serves two `events` rows per
fixture:**

```
GET /api/leagues/baseball_mlb  →  upcoming_games: 8, distinct matchups: 5
  15293870  Miami Marlins @ Kansas City Royals  live  2026-09-03T23:40:00+00:00
  15301135  Miami Marlins @ Kansas City Royals  live  2026-09-03T23:40:00+00:00
  15293872  Tampa Bay Rays @ Texas Rangers      live  2026-09-04T00:05:00+00:00
  15301151  Tampa Bay Rays @ Texas Rangers      live  2026-09-04T00:05:00+00:00
  15301150  Athletics @ Seattle Mariners   scheduled  2026-09-04T01:40:00+00:00
  15293897  Athletics @ Seattle Mariners   scheduled  2026-09-04T01:40:00+00:00
```

Same teams, same commence time, two ids, two different blends. This is a MATCHING defect
(duplicate event rows) reaching the reader as a FORMATTING one, and it is the loudest thing on the
page. **Needs its own issue; the 15301xxx block looks like a single ingest run that created rather
than absorbed** (gotcha #32 territory — an id-less claim never absorbs, it creates, and the
id-keyed drain has not run).

### 4b. `/search` renders a market question in a party slot

`census-search-1440.png` y≈250: a `GAMES (6)` card whose two "parties" are `Yibing Wu` and
**`Carlos Alcaraz - Exact Score`**, with `No result reported` where the state goes. G2 is being
handed a market and drawing it as a fixture.

### 4c. `/search` prints two em-dashes where a probability pair goes

Same shot: the `ATP · Today 5:00 PM · Wu / Alcaraz` card shows `-` and `-` for both sides. G2 has
no "we hold no reading" treatment, so an absent pair renders as two punctuation marks.

### Not a finding — already tracked debt

`census-futures-1440.png` y≈1000 prints *"Limited price history available / **Prices** update
every 1–2 hours for this market"* on `/futures/[id]`. That is a ruling-138 violation (the word is
PROBABILITY) and it is **already recorded** as `"app/futures": ["price-family"]` in the `OWED` map
of `__tests__/components/shippedCopyBans.test.ts`. Named here only so the next reader of these
shots does not re-file it.

---

### 4d. THE OPENER TREATMENT — there were four, and there is now one (D57 corrected, ux/1055)

Alex, correcting D57 on 2026-09-03 at 4:15pm PT, asked this census to record *"which opener
treatments exist today (there should be one)"*. Measured across every surface that prints a
pre-match probability beside a settled result:

| Surface | Component | Treatment BEFORE ux/1055 |
|---|---|---|
| `/sports` and every `FeedCard` list | `components/FeedCard.tsx` | `font-mono text-[11px] tabular-nums text-text-muted` + a `Pre-match†` caption in the bottom row |
| league pages, sport categories | `components/EventCard.tsx` → `PrematchPercent` | the same class list, second copy + an inline `†` |
| Discover | `components/discover/EventCard.tsx` | `font-mono tabular-nums text-text-muted` inheriting **`text-sm`** from its strip + a conditional "from sportsbooks" tooltip |
| the tournament hub's finished list | `components/tournament/TournamentResults.tsx` | **`text-[12px] tabular-nums text-text-secondary`, no mono** — its own invention, and the surface Alex was reading |

**Four, not one.** Two agreed, one drifted by inheritance, one was written from scratch. Note that
`lib/prematchReading.ts` already opened with the sentence *"this module is the one place that
decides WHICH number that is, because three surfaces print it and a per-surface answer is how they
would drift"* — it owned the number and owned nothing about how the number looks, which is exactly
where the drift went.

**There is one now:** `PREMATCH_NUMBER_CLASS` in `lib/prematchReading.ts`, read by all four call
sites, guarded in `finishedCardPrematchPerTeam`, `hubRowNamesItsSource2747` and
`sportsFinishedRail`. The dagger, the "from sportsbooks" tooltip, the `Pre-match` caption on
`FeedCard` and both section legends are deleted — see commit `30eb368a`.

**The general lesson for epic #2910:** a shared *decision* module does not prevent visual drift.
`prematchReading` is the best-owned decision on the product and four surfaces still drew its answer
four ways. Whatever the card system turns out to be, the thing it has to own is the TREATMENT, not
just the data.

---

## 5. What this census does NOT cover, and why

- **Five renderings are typed from source, not from a photograph** — G9 `HubUpcomingRail`, O5
  `CombinedMarketCard`, T4 `PlayoffGrid`, T6 `TournamentBracket`, X3 `PlayerStatCard`. Four of
  them need a surface state today's board does not have (a competition hub with upcoming rows, a
  playoff bracket in season). O5 is the interesting one: `/futures/86832` **was** photographed at
  both widths and `CombinedMarketCard` did not appear anywhere on it, so either that market is not
  cross-sourced or the card is unreachable — **not resolved here, and not asserted either way.**
  For all five, the "what it shows" column is read off the component. **Flagged rather than
  guessed.**
- **`/my-stuff` and `/preferences` are signed-in surfaces** and `tools/look.sh` /
  `tools/shop-shot.mjs` have **no signed-in mode** — no storage state, no auth, no cookie jar.
  Their card set (`FeedCard`, `EventCard`, `FuturesCard`) is covered by other surfaces, but the
  signed-in *arrangement* of them is unphotographed. Building an authenticated LOOK rail is a real
  gap and is the same gap that blocked ux/1054 item 2's repro.
- **Native (iOS/iPadOS/macOS/watchOS) is out of scope** — the native lane runs the same census for
  its ~17 cards.
- **Share cards** (`/share/my-odds`) render a `SkeletonCard` and an image composed server-side;
  no event-card rendering of its own.

---

# 6. THE CHART CENSUS (ux/1055 item 3)

**Alex, 2026-09-03 4:15pm PT:** every chart rendering on web — screenshot, component, which
primitive it is, which series it reads, and its visible point density over the last 24h.

**Status: MEASUREMENT ONLY.** Nothing in this section is repaired here. It feeds charts epic
**#2911** the way §0–§5 feed cards epic **#2910**.

## 6.0 How this was measured — and why it is not the July census re-typed

`docs/chart_census.md` (L2-148/149/150/152, 2026-07-21/22) already inventories the chart
*implementations* and closed at **11**. That document is a source inventory: it answers "how many
renderers exist and which duplicate each other". It cannot answer either of the two questions Alex
asked here, because both are about what a reader's browser ends up holding:

1. **which primitive is on screen**, and
2. **how many points it actually draws in the last 24 hours.**

So this section measures the DOM and the payload, and treats the source inventory as a cross-check
rather than as the answer. Three instruments, all run against the ux/1055 branch build served at
`127.0.0.1:3111` with every `api.bainluck.com` call proxied to production:

| Instrument | What it produces | Where it lives |
|---|---|---|
| **Photograph** | full-page 1440×2400 @2× per surface, sliced into readable bands | `tools/local-shot.mjs` + `tools/crop.py`; shots in `artifacts-ux-1055/charts/` (local only — shop evidence never enters the repo) |
| **DOM chart inventory** | every `<svg>` bigger than an icon, with its data-path count, max vertex count, polyline point count, rect and circle counts, and its nearest heading | `tools/chart-inventory.mjs` (tracked — §6.5) |
| **Payload density probe** | for each series a chart reads, `(total points, points with a timestamp ≥ now−24h)` | production API, direct |

**The vertex count is the honest reading of "visible point density".** A payload count is what the
server sent; a vertex count is what the line is made of after windowing, bucketing and capping.
The two differ by a lot on the event page and that gap is a finding, not noise (§6.3a).

**One rig limitation, stated up front.** The inventory aborts `**/stream` routes so a blocking
`curl` on an SSE endpoint cannot hang the browser (the same trap that ate the first photography
run). `LiveSparkline` renders only when `streamConnected` is true, so **C9 below did not render
under the instrument and its density is unmeasured** — that is a fact about the rig, not about the
product. Flagged, not guessed.

## 6.1 Primitive legend

Alex's four, applied to what the mark IS rather than to what library drew it:

- **match** — ONE question's probability over time. One hero line, optionally faint source lines.
- **race** — a FIELD of contenders over time. Many equal-weight lines, no hero.
- **outcome bars** — a distribution ACROSS outcomes at one instant. No time axis.
- **other** — everything whose x-axis is not time and not an outcome: reliability diagrams
  (predicted vs actual), geography, cartograms.

## 6.2 The census

Every row was reached by photograph AND by DOM inventory unless the "measured" column says
otherwise. `24h` is points-in-the-last-24-hours; `—` means the chart has no time axis.

### match — one question over time

| id | Component | Surface(s) | Series it reads | Measured render | 24h |
|---|---|---|---|---|---|
| **C1** | `components/OddsChart.tsx` (recharts `ComposedChart`) | `/events/[id]` "Win Probability" | `aggregate_line` (the blend, hero) + `espn_history` / `win_prob_history` / `bookmaker_history` as faint sources; `scoring_plays`, `period_markers`, `moments` as annotations | 1324×320, **3 data paths, max 150 vertices** ("Since Start" range) | blend **467**, ESPN **24** in payload — see §6.3a |
| **C2** | `components/ScoreDifferentialChart.tsx` (recharts) | `/events/[id]` "Score Differential" | score margin over time + `pm_spread_data`; **not** `score_history`, which was empty (0 rows) on the measured game | 1332×192, **1 data path, 61 vertices** | 61 drawn; the series feeding it is not traced here |
| **C8** | `components/FuturesHero.tsx` → `AmbientHistory` (inline `<path>`) | `/futures/[id]` hero, behind the numeral | the hero outcome's recent points | 1392×96, **2 paths (area + line), 44 vertices** | **6** (inherits C3's cadence) |
| **C6** | `components/Sparkline.tsx` (the shared single-market kernel) | `/politics` table (`CandidateSpark`), event leaderboard rows, `story/CaseStudyChart` line variant | per-candidate `history[{t,p}]` | politics: **14 instances at 60×18**, 10 of them 51 vertices, 4 of them 3 | **0** — see §6.3b |
| **C7** | `components/Sparkline.tsx` again, on **fabricated data** | `/weather` hero + wild cards | `sparkFrom(seed, end, 14)` in `components/weather/data.ts` | hero 96×28, 3 × wild card 80×24, 14 points each | **n/a — no point is an observation.** §6.3c |
| **C9** | `components/event/LiveSparkline.tsx` | `/events/[id]`, last 10 min | pushed `sparklinePoints` | 96×24 declared; **did not render under the instrument** (needs a live SSE connection) | unmeasured |

### race — a field over time

| id | Component | Surface(s) | Series it reads | Measured render | 24h |
|---|---|---|---|---|---|
| **C3** | `components/FuturesChart.tsx` — the shared field kernel, plus 5 wrappers (`SettledPathChart`, `RaceToTitleChart`, `WinnerEvolutionChart`, `TwoSidedTimeline`, `TeamSeasonJourney`) and `EvolutionView` | `/futures/[id]` "Probability Trend"; `/categories/golf`; `/sport/[sport]/[league]` "Odds Movement"; `/event/[domain]/[slug]` | `FuturesOutcomeHistory[]` from `/api/futures/{id}/history` (or `multi-history`) | futures 1344×200 **3 paths × 42**; league 1034×300 **5 paths × 50**; golf 906×300 **8 paths × 171** | **6 per outcome** (4-hourly) — and **0** on a stale market, §6.3d |
| **C4** | `components/tournament/ContenderChart.tsx` | `/tournaments/[slug]` | board rows' `trend[{date,probability}]` (daily) | 724×160, **3 polylines × 6 points**, 3 end dots ("3 of 36 · 5d shown") | **1** |
| **C5** | `components/tournament/TrendSparkline.tsx` | `TournamentBoard` rows on the same page | the same `trend` array, one contender | 52×26, **1 polyline × 16 points** | **1** |
| **C11** | `PresEvolution`, inline in `app/politics/page.tsx` (720×200, hand-rolled) | `/politics` | candidate `history` | **did not render** in the measured DOM | unmeasured |

### outcome bars — a distribution at one instant

| id | Component | Surface(s) | Series it reads | Measured render | 24h |
|---|---|---|---|---|---|
| **C14** | `components/weather/DistributionPanel.tsx` | `/weather` city panel | `city.high.dist` — 11 temperature bins | **CSS divs, not SVG** — invisible to an svg-based inventory | — |
| **C12** | `AdvancementPath` / `RelatedFutures` `CHAMPIONSHIP PATH` | `/events/[id]` "Bigger Picture" | per-team futures probabilities (Make Playoffs / Division / Champ / World Series) | CSS divs | — |
| **C13** | `ChamberControlCard`, inline in `app/politics/page.tsx` | `/politics` | Senate/House control pair | CSS divs, diverging split bar | — |
| **C18** | `components/story/CaseStudyChart.tsx` `bars` variant | story cards | case-study rows | not reached on the photographed surfaces | — |
| **C19** | the arc gauges in the event props strip | `/events/[id]` | a single probability each | partial-ring SVG | — |

### other — x is neither time nor an outcome

| id | Component | Surface(s) | Series it reads | Measured render | 24h |
|---|---|---|---|---|---|
| **C10** | `components/CalibrationChart.tsx` | `/calibration`, `/admin/source-intelligence` | `/api/calibration` buckets: predicted midpoint vs actual, with a CI band | **6 panels at 300×230 / 330×260** (By Source) + **1 at 700×340 with 5 series and 55 circles** (By Category); 8–10 points per line | — (5-year buckets) |
| **C15** | `components/weather/MapCanvas.tsx` + the temperature-map SVG | `/weather` | 42 cities' modal high | 768×426, 7 paths (continent outlines) + per-city dots | — |
| **C20** | `SenateMap`, inline in `app/politics/page.tsx` | `/politics` | `map: Record<state, prob>` | **CSS divs** — a state-grid cartogram, red/grey/blue | — |
| **C16** | `components/DisagreementChart.tsx` | `/admin/source-intelligence` only | multi-source timeline | admin | — |
| **C17** | recharts in `app/admin/page.tsx` (5), `app/admin/analytics/page.tsx` (9), inline area in `app/admin/bug-reports/page.tsx` | admin only | ops metrics | admin | — |

## 6.3 What the measurement says

### 6.3a The event chart draws a third of what it is sent — and that is the design

The blend series carried **467 points in the last 24h** (≈ one every 3 minutes). The rendered line
has **150 vertices**. The gap is `lib/chartTimeline.ts`'s `toMinuteKey` / `fillMinuteGaps`: the
chart buckets to the minute and the "Since Start" window was 2h21m. So the densest surface we have
is drawing about one vertex per minute of elapsed game — legible, and honest, because bucketing
drops duplicates rather than inventing intermediates. **Recorded so no one later reads 150 as a
data gap.**

### 6.3b Every sparkline on `/politics` is seven days stale

`Alexandria Ocasio-Cortez`: 51 points, first `2026-08-05T03:50Z`, **last `2026-08-28T18:49Z`** —
and the same for all ten full-length sparks on the page. **Zero points in the last 24 hours**, on a
page whose whole claim is movement. The lines still render at full contrast, beside a `MoveChip`
that reports change; nothing on the page says the last vertex is a week old. **#2961**, with §6.3d.

### 6.3c `/weather`'s sparklines are generated, not observed — TRUTH pillar

```
export function sparkFrom(seed: number, end: number, n = 14): number[] {
  let s = seed;
  const rng = () => { s = (s * 9301 + 49297) % 233280; return s / 233280; };
  ...
}
```
`components/weather/data.ts:163`. `WeatherHero` calls it as `sparkFrom(idx * 7 + 3, current.prob)`
and `WildCards` as `sparkFrom(i * 137 + 42, card.prob)`. It is a seeded pseudo-random walk that
ENDS at the real current probability and invents the thirteen points before it. Four of these are
on `/weather` right now at 1440 (one hero, three wild cards), drawn in the same shared `Sparkline`
component that draws the real ones on `/politics` and the event leaderboard — so a reader has no
way to tell them apart, and neither does a grep. **This is the single most serious thing in this
census.** It is not repaired here — **filed as #2960**, which leaves the delete-vs-serve-real-history
decision to #2911.

### 6.3d A chart with no recent point looks exactly like a chart with one

`/api/futures/16630403` ("Hantavirus pandemic in 2026?") returns **419 history points, 0 of them in
the last 24 hours**. `FuturesChart` draws all 419 on a time axis whose right edge is now, so the
line simply runs flat to the present. Nothing declares the last real reading. Compare C3's healthy
case, 6 points per outcome per day. **Filed with §6.3b as #2961** — one defect, two instances: a
chart is honest about every point it draws and silent about the gap between its last point and the
right edge of its own axis.

### 6.3e Discover and /sports draw no charts at all

The DOM inventory found **zero** chart SVGs on `/discover` and **zero** on `/sports`. The brief
listed "card sparklines" as a class to census; the honest answer is that **no Discover or feed card
carries one** — `FeedCard`, `EventCard`, `discover/EventCard`, `FuturesCard` and
`discover/FuturesCard` contain icon paths only. The only card-level charts on the product are the
tournament board's `TrendSparkline` (C5) and the event leaderboard's `Sparkline` (C6).

### 6.3f Six primitives, and only two of them are shared

`match` and `race` ride two shared kernels (`OddsChart`/`Sparkline`, `FuturesChart`). Every
`outcome bars` rendering is a **private CSS-div implementation** — five of them, no shared
component, and none of them visible to an SVG-based audit. Three of the four `other` renderings are
also private. **A chart system keyed on the SVG renderers would miss eight of the twenty
renderings**, which is the same shape of gap §0 found for cards (a name-based card inventory missed
fifteen).

### 6.3g The July census is stale in one specific place

`docs/chart_census.md`'s L2-150 update records that the `FuturesHero` inline `<path>` was replaced
by the shared `Sparkline`. It is back: `AmbientHistory` at `components/FuturesHero.tsx:224` is a
hand-rolled area + line, added afterwards as "L2-161, Hero C". Implementation count is **12, not
11**, and `PresEvolution` (C11) makes **13** — it was never in either census.

## 6.4 What this section does NOT cover

- **`PresEvolution` (C11) and `LiveSparkline` (C9) are typed from source.** Neither rendered under
  the instrument — C9 by a known rig limitation (no SSE), C11 for a reason not diagnosed here.
- **Native charts are out of scope**, as with the card census.
- **`CaseStudyChart` (C18)** was not reached on any photographed surface.
- **No chart was measured at phone width.** Every reading here is 1440. The card census photographs
  both; this one does not, and a chart's point density at 390 is a different number wherever a
  responsive width feeds the geometry.

## 6.5 The instrument, so this is repeatable

`tools/chart-inventory.mjs` walks every `<svg>` on a page, discards anything under 40×12 (icons),
and reports per chart: nearest heading, box, whether it is inside a `.recharts-wrapper`, the count
of `<path>`s with ≥3 `M/L/H/V` commands, the maximum vertex count among them, the polyline count
and their maximum point count, and the `<rect>`/`<circle>` counts. It reads a rendered page, not a
component tree, which is why it can see that `/sports` has no chart and that `/weather`'s
distribution histogram is not an SVG at all.

It is TRACKED rather than left in `/tmp`, for the two reasons this repo already has rules about: a
rig that lives on one laptop is lost work (CLAUDE.md, on the lane runners), and `/tmp` scratch
paths collide across lanes. Usage:

```
node tools/chart-inventory.mjs http://127.0.0.1:3111/tournaments/us-open
```

It expects a branch build served locally and proxies every `api.bainluck.com` call to production
through `curl`, exactly as `tools/local-shot.mjs` does — including that rail's SSE guard, without
which the event page hangs the browser forever.
