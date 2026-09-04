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

**The headline count in the brief was ~30 distinct named card components. The measured number of
distinct RENDERINGS is 29, but that is not the same set**, and the difference is the finding:

| | |
|---|---|
| Files named `*Card*.tsx` under `frontend/components` | 32 |
| …of those that are admin-only, skeletons, or shells (not a card) | 6 |
| Renderings of an event/market card that a reader can reach | **29** |
| …of which are NOT in a file named `*Card*` (rails, boards, grids, rows) | **11** |

So a name-based count both **over**-counts (`SkeletonCard`, `EventCardShell`, `WildCards`,
three admin cards) and **under**-counts by eleven — `LeagueGameRail`, `LeagueBinaryBoard`,
`HubUpcomingRail`, `MatchupsRail`, `PropDivergenceRail`, `TournamentMatches`,
`TournamentResults`, `TournamentBoard`, `PlayoffGrid`, `GolferRow`, `MoversRibbon` all draw a
card and none of them is called one. **Any card-system proposal keyed on the filename will miss
a third of the surface area.**

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

1. **Three kinds have three or more independent implementations each.** A game is drawn eleven
   ways, an outright eleven ways, a tournament grid six ways. None of them shares a layout
   primitive; `EventCardShell` is the only shared piece and only three renderings use it.
2. **The `discover/` fork is a whole second product.** Four of the five most-used cards exist twice
   — once for Discover and once for everything else — and the two halves disagree about the hero
   treatment, the state vocabulary, and whether actions belong on a card.
3. **The vocabulary is not shared even where the layout is.** The same fact is called `Opened
   48/52` on G2, `Pre-match †` on G3/G1, a bare grey figure on G7, and `Proj 12-20` on G2's other
   footnote — four spellings of "what was expected before".
4. **Eleven renderings are invisible to a filename-based inventory.** See §0.

---

## 4. Three defects the photography turned up (recorded, NOT fixed here)

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
