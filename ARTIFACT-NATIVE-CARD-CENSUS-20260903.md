# ARTIFACT — NATIVE CARD + CHART CENSUS (2026-09-03)

**Queue:** native/003 (runner-inbox `003-the-native-card-census.md`) · **Pillar:** FORMATTING
**Ship this feeds:** one card grammar and one chart grammar across desktop web, mobile web and
native — so a person meets the same card for the same kind of question everywhere.
**Epics:** cards **#2910**, charts **#2911** (filed by ux/1055). No fixes in this queue.

**Lane:** native · **Author:** native lane · **Real clock:** 4:20pm–5:35pm PT, 2026-09-03
**Device:** iPhone 17 simulator, iOS 26.5, Xcode 26.6 · **Data:** live production
(`GET /api/feed?limit=40`, `/api/golf`, `/api/events/15299428/history`,
`/api/futures/86832/probability-timeline`) captured 2026-09-03 ~4:25pm PT.

---

## 0. How the pictures were made, and what they are worth

Two rails, because neither alone photographs everything.

**Rail A — `ImageRenderer` on the real view, from one real feed payload.** A temporary
`BainLuckTests/CardCensusRenderTests.swift` decoded a live `/api/feed` page into the app's own
`FeedItem` models and rasterised **20 card views** at width 390, scale 3. These are the *shipped*
views with *today's production data* — not mockups and not previews. Environment objects
(`PinManager`, `AuthManager`, `NavigationCoordinator`) had to be injected or `EventCardView`
traps at render.

**Rail B — the running app on the simulator, via a temporary launch-argument route seed.**
`simctl` has no tap verb and `openurl` raises an undismissable SpringBoard prompt, so a temporary
`TempCensusRoute` read `-censusEvent <id>` / `-censusFutures <id>` to land the cold launch on a
detail page, and `-censusScroll <points>` applied negative top padding to bring a below-the-fold
section into frame. Nine full-screen shots.

**Both scaffolds are reverted.** `git status` is clean apart from the untracked artifact folders,
and `grep -rn "TEMP-CENSUS\|TempCensusRoute\|censusScroll\|censusEvent" ios/` returns nothing. The
two temp files are preserved as `artifacts-native-003/CardCensusRenderTests.swift.txt` and
`TempCensusRoute.swift.txt` so the rail is one `cp` away next time.

**Honest limits.** (a) Screenshots are **iPhone only** — see §5 for the iPad/Watch gap and its
cost. (b) The notification permission alert fires 5s after launch and cannot be dismissed
unattended; every Rail-B shot is taken at 4.3s after a SpringBoard respring. (c) In the
`-censusScroll` shots the nav bar overlaps the content and the leftmost ~16pt is clipped — that is
my scroll hack, not shipped behaviour, and I say so per shot.

Artifacts: `artifacts-native-003/cards/census-*.png` (20) · `artifacts-native-003/charts/*.png` (9).

---

## 1. THE CARD CENSUS — 21 card views

`discover_card` column: **contract** = the view reads `FeedFuturesData.discoverCard` (the backend's
`discover_card` block: `suggested_format`, `threshold_points`, `distribution_outcomes`) and is
*selected* by it. **feed-typed** = fed by the feed's typed payload (`FeedEventData` /
`FeedFuturesData` / `FeedTournamentData` / `FeedConceptData`) but the layout choice is the client's.
**hand-assembled** = built from loose fields or a different endpoint entirely.

| # | Card view | File | Where it renders | What it shows | Archetype | Fed by | Shot |
|---|---|---|---|---|---|---|---|
| 1 | `NativeEventDiscoverCard` | `Components/DiscoverEventCard.swift` | Discover feed | Hero art + LIVE chip, matchup, 70/30 split bar, one reason line | **game** | feed-typed (`FeedEventData`) | `census-01` |
| 2 | `NativeFuturesDiscoverCard` | `Components/DiscoverFuturesCard.swift` | Discover feed | Category hero, one big %, question, context line, source chip | **yes/no** (binary hero) | feed-typed + `discoverCard.suggestedFormat` fallback | `census-02` |
| 3 | `NativeTournamentDiscoverCard` | `Components/DiscoverTournamentCard.swift` | Discover feed | Tour chip, venue, leader %, runner-up strip, status line | **tournament grid** | feed-typed (`FeedTournamentData`) | `census-03` |
| 4 | `NativeConceptDiscoverCard` | `Components/DiscoverConceptCard.swift` | Discover feed | LIVE/MARQUEE chips, concept name, leader + %, "N race markets" | **tournament grid** (concept) | feed-typed (`FeedConceptData`) | `census-04` |
| 5 | `HeatMapCardView` | `Components/HeatMapCardView.swift` | Discover feed | 5 threshold cells tinted by probability + "above 50% through X" | **prop ladder** (threshold) | **contract** — `suggested_format == threshold_heatmap`, ≥2 priced `threshold_points` | `census-05` |
| 6 | `DistributionCardView` | `Components/DistributionCardView.swift` | Discover feed | Ranked outcome list, bars, "+N field" row | **outright** | **contract** — `outcome_distribution`, ≥4 priced `distribution_outcomes` | `census-06` |
| 7 | `ComparisonCardView` | `Components/ComparisonCardView.swift` | Discover feed | Top-3 outcomes, bars, "Show more / N markets" | **outright** | **contract** — `cross_source_comparison` **or** `top_outcomes ≥ 4` | `census-07` |
| 8 | `EventCardView` | `Components/EventCardView.swift` | Sports tab feed | Two team rows, split bar, arrows, badge chips, opener text | **game** | feed-typed (`FeedEventData`) | `census-08` |
| 9 | `FuturesCardView` | `Components/FuturesCardView.swift` | Sports tab feed | Category, question, `#1 <outcome> N%` rows | **outright** | feed-typed (`FeedFuturesData`) | `census-09` |
| 10 | `NativeGuessCard` | `Views/DiscoverView.swift:1982` | Discover feed (guess slot) | "Higher or lower than X%?" + two buttons | **yes/no** (game mechanic) | feed-typed; two inits (`FeedFuturesData`, `FeedEventData`) | `census-10` |
| 11 | `NativeDailyChallengeCard` | `Components/DailyChallengeCard.swift` | Discover feed (top) | Challenge banner, progress ring, Play | **other** (promo) | hand-assembled (local `Int`) | `census-11` |
| 12 | `NativeResolutionDigestCard` | `Components/ResolutionCard.swift` | Discover feed | "N predictions resolved · M right" | **other** (digest) | hand-assembled (local counts) | `census-12` |
| 13 | `NativeFeedEndCard` | `Components/ResolutionCard.swift:64` | Discover feed (end) | "You're all caught up" + Refresh | **other** (terminal) | hand-assembled | `census-13` |
| 14 | `NativeGroupCard` | `Views/DiscoverView.swift:1511` (`private`) | Discover feed (bundle/theme) | Themed gradient group of N member items | **other** (bundle) | feed-typed (`FeedItem.bundle`) | *not rasterisable — `private`; see `charts/33`* |
| 15 | `LadderCardView` | `Components/LadderCardView.swift` | Event page, team page | Team header + milestone rungs with bars, clinched/eliminated states | **prop ladder** | hand-assembled (`[LadderRung]` built by the caller) | `census-14` |
| 16 | `GamePlayCardView` | `Components/GamePlayCardView.swift` | Event page (chart scrub) | Selected chart point: period · score · both probabilities | **other** (chart readout) | hand-assembled (`GamePlayPoint` from history) | `census-15` |
| 17 | `PlayerPropsCardView` | `Components/PlayerPropsCardView.swift` | Event page | Team filter, per-player cards, stat groups with threshold rungs | **prop ladder** | hand-assembled (`[GameMarketPlayerProp]` from `/markets`) | `census-16` |
| 18 | `PlayerStatCardView` | `Components/PlayerStatCardView.swift` | Event page, props surfaces | One player + one stat, ranked threshold lines | **prop ladder** | hand-assembled (`[StatPropLine]`) | `census-17` |
| 19 | `TournamentHeroCard` | `Components/TournamentHeroCard.swift` | Golf category page | Tournament name, course, dates, top-5 golfers with % | **tournament grid** | hand-assembled (`GolfTournamentData` from `/api/golf`) | `census-18` |
| 20 | `TournamentCompactRow` | `Components/TournamentCompactRow.swift` | Golf category page (list) | One-line tournament + leader % | **tournament grid** | hand-assembled (`GolfTournamentData`) | `census-19` |
| 21 | `ShareCardRenderer` | `Utilities/ShareCardRenderer.swift:364` | Share sheet (export image) | 3:4 export: hero %, name, question, `bainluck.com` | **outright / game** (two renderers) | hand-assembled (scalar args passed by the caller) | `census-20` |

**Count by archetype:** game 3 · outright 5 · prop ladder 4 · tournament grid 4 · yes/no 2 ·
other 5. **Count by feed:** contract 3 · feed-typed 8 · hand-assembled 10.

### The contract finding

Only **three** of the twenty-one card views are actually *chosen* by the backend's `discover_card`
contract — `HeatMapCardView`, `DistributionCardView`, `ComparisonCardView`. Everything else picks
its own layout from the shape of the data it happens to be handed. The selection ladder that does
exist lives in one `if / else if` chain in `DiscoverView.swift:938–1090`, and its order is
load-bearing and undocumented:

```
event → heatmap(threshold_heatmap, ≥2 priced) → distribution(outcome_distribution, ≥4 priced)
      → comparison(cross_source_comparison OR top_outcomes ≥ 4) → futures → tournament → concept
```

Consequence, measured on today's feed: the NFL Super Bowl Winner market satisfies *both* the
distribution and the comparison predicate. Distribution wins because it is earlier in the chain, and
`ComparisonCardView` — the one card whose name promises a *cross-source* comparison — can in
practice only be reached by a market that is not also a distribution. `census-06` and `census-07`
are the same market rendered by both, and neither shows a second source.

**Ten of twenty-one cards are hand-assembled.** That is the reinvention Alex named. Each one
re-derives its own idea of "a probability row": `LadderCardView` uses a labelled rung with a track,
`PlayerStatCardView` uses a rank chip + short grey track, `DistributionCardView` uses a
leader-normalised green bar, `ComparisonCardView` uses a centred mint bar, `FuturesCardView` uses no
bar at all, and `TournamentHeroCard` uses a bare right-aligned number. Six treatments of one idea.

### Opener treatments (asked by ux/1055 D57 — "there should be one")

There are **two** on native today, and they disagree:
- `EventCardView` (Sports tab): `Opened 4%/96%` — grey, bottom-right, slash-separated (`census-08`).
- Event page hero: `Opened 34% – 66%` — grey, under the verdict, en-dash separated (`charts/30`).

Nothing else labels an opener. `NativeEventDiscoverCard` shows no opener at all.

---

## 2. WHAT A PERSON ACTUALLY SEES — defects found while shooting

Ranked by how badly they read. All are on production data, today. None are fixed here; they belong
to #2910/#2911 or to their owning lane.

1. **`census-03` — the tournament card prices every golfer at 0%.** "Omega European Masters —
   **0%** Angel Ayora · 0% Chacarra · 0% Hall · 0% Lawrence", with the status line "Live — round in
   progress". A live leaderboard where the leader is 0% is worse than no card. (Adjacent to
   artifacts-native-002's golf 0% work; this is the *tournament* card, not the Discover golf card.)
2. **`charts/31` — a LIVE tennis match page shows "No probability data available"** in ~700pt of
   white, no score, no LIVE badge, and below it a **completely empty "Margin map"** whose labels
   read "Canas by 18+ / Tie / Marcos by 18+" for a tennis match. Three failures stacked on the
   surface Alex opens during a tournament.
3. **`charts/37`, `charts/38` — a settled MLB event page renders 20+ prop rows as
   `<name>: Home Runs O/U 0.5 … last quote 0%`.** A wall of zeros in monospace. `PlayerPropsCardView`
   (`census-16`) exists and renders well when it is given props — it is not the view being used
   here; the fall-through "Other Markets" list is.
4. **`census-02` — "Hantavirus pandemic in 2026?" is categorised WEATHER** and gets sun-and-cloud
   hero art. The context line says "Kalshi and Polymarket agree" while the source chip says
   POLYMARKET only.
5. **`census-05` — heat-map buckets are out of order**: `9–9.5m`, `<9m`, `9.5–10m`, `10–10.5m`,
   `10.5–11m`. `<9m` is second. And 3/3/5/7/6% render as five near-identical pale-green cells, so the
   "heat" carries no signal at all.
6. **`census-08` — a LIVE NCAAF game shows `0-0` and `Opened 4%/96%` against a current 70/30.**
   A 66-point swing with no score to explain it reads as a data bug to a fan, whether or not it is one.
7. **`census-01` / `census-08` — missing away-team logo** (generic ball watermark / blank circle) on
   the same game that has the home logo.
8. **`census-10` — the guess card asks "higher or lower than 21%?" for a market at 4%,** and prints
   the outcome name twice ("Hantavirus pandemic" as both subtitle and anchor label).
9. **`census-20` — the share card is ~55% empty white** below the question when the market has few
   priced outcomes. This is the image a user posts.
10. **`census-06` — distribution bars are leader-normalised, not 0–100.** 14% draws a full-width bar;
    8% draws ~46%. Two readings of the same track in one card set (`census-07` normalises differently).
11. **`census-09` — `FuturesCardView` prints the market name as its own top outcome**
    ("Hantavirus pandemic in 2026?" → `#1 Hantavirus pandemic 4%`) and draws no bar, though
    `ProbabilityBar` exists three files away.
12. **`census-11` — the daily challenge states progress twice** ("· 3/5" and a ring reading "3").

**The two cards that are already right** and should be the grammar the rest converge on:
`LadderCardView` (`census-14`) and `PlayerPropsCardView` (`census-16`) — labelled row, full-width
track, right-aligned number, one accent colour, terminal states drawn rather than described.

---

## 3. THE CHART CENSUS (4:15pm addendum)

Alex: native charts are "BRUTALLY bad still". Per chart, specifically what is bad.

### 3.1 `OddsChartView` — event win probability · **match** primitive
`Components/OddsChartView.swift` (1,246 lines) · shot `charts/30-event-completed-mlb.png`
(Athletics 5 – Rangers 8, completed) · fetches `/api/events/{id}/history` itself.

*Series:* one line — the blend ("Bain Luck"), on a single 0–100 axis reading HOME win probability
(L2-216). Sources are opt-in behind a control below the chart.
*Density (measured):* 328 odds points retained, **190 inside the 195-minute game window ≈ 1 point
per minute**, plus 56 ESPN in-game points. All 190 are drawn.

What is bad:
- **Over half the plot is dead.** The domain is fixed 0–100 while the series never leaves 50–100
  except two dropouts. The whole 0–50 band — ~55% of the vertical space — is empty white.
- **The line is noise, not a story.** At ~1 point/minute with no smoothing or downsampling, the
  60px-tall band the game actually occupies is a hairball. The two full-height plunges to 50% early
  and the spikes at the 7th/8th read as feed dropouts, not as swings, and nothing on the chart says
  which they are.
- **The period pills sit on top of the axis.** "1st"…"Final" render *on* the 100% gridline and the
  `100%` tick is completely covered. They are also two-toned (grey up to the 6th, green from the
  7th) with no legend for the difference.
- **The rotated team names collide with the axis.** "RANGERS" (top-left, vertical) overlaps the
  clipped `100%`; "ATHLETICS" (bottom-left) sits against `0%` and the legend.
- **The settle is drawn as a spike.** The final move to 100% is a single vertical stroke at the
  right edge, indistinguishable from a data glitch. "Settled means settled" is not honoured here.
- **Three x-labels for a three-hour game** (6:05 / 7:05 / 8:05 PM), no date, no "start"/"final" anchor.
- *Interaction:* an `All` / `Since Start` segmented control and a scrub that feeds
  `GamePlayCardView`. Neither is discoverable from the chart itself; there is no affordance.

### 3.2 `ScoreDifferentialChartView` — projected vs actual margin · **match** primitive
`Components/ScoreDifferentialChartView.swift` · shot `charts/37-event-mlb-scorediff-marketmap.png`.

*Series:* two — dashed orange "Projected Spread", solid teal step "Actual Score Diff".
*Density:* the same 190-point in-window odds series plus the score steps.

What is bad — **this is the best chart on native** and still:
- **The y-domain clips the data.** Ticks are −5 / 0 / +5 and the teal step reaches +8; the line runs
  above the top of the labelled range with no tick to read it against.
- **The rotated team names overlap again** — "RANGERS" over the y-axis, "ATHLETICS" over the legend row.
- **Period pills clipped at the top** (the "1st" pill is half-height).
- What it gets right, and the others don't: two named series, a real legend in words, a step line for
  a step quantity, and a zero reference. This is the template.

### 3.3 `MarketMapView` — "Margin map" · **outcome bars** primitive
`Components/MarketMapView.swift` (684 lines) · shot `charts/31-event-live-tennis.png`.

*Series:* spread/total market outcomes placed on a horizontal value axis.

What is bad:
- **It renders completely empty on a live tennis match** — a flat grey pill with no marks at all.
- **The labels are nonsense for the sport**: "Canas by 18+ / Tie / Marcos by 18+". Tennis has no
  margin of 18 and no tie.
- **The centre labels collide**: "0" and "Tie" are drawn on top of each other.
- It occupies a full card of vertical space to say nothing.

### 3.4 `EvolutionChartView` — futures race · **race** primitive
`Components/EvolutionChartView.swift` (750 lines) · shot `charts/34-futures-evolution-chart.png`
(NFL Super Bowl Winner) · fetches `/api/futures/{id}/probability-timeline` itself.

*Series:* up to 10 outcomes (`Top 5 / Top 10 / Top 20` chips) over `Season / 7d / 24h / Today`.
*Density (measured):* `bucket_seconds = 3600` requested over 168h, but the API returns **42 timeline
buckets ≈ one point every 4 hours**, for 11 outcomes.

What is bad:
- **The leader is drawn off the top of the labelled axis.** Ticks stop at 15%; the Rams line (14%)
  is drawn above the 15% gridline with nothing to read it against, and there is no 20% tick.
- **Nine of ten lines are stacked inside a 4-point band** (4%–8%) in near-identical blues, with no
  in-chart labels and no legend in frame. You cannot tell the Bills from the Ravens.
- **Everything below 4% is empty** — the 0–4% band is ~30% of the plot with nothing in it.
- **The lines are staircases, not curves.** Measured cause: the values are implied probabilities from
  integer decimal odds — 0.166667 (1/6), 0.090909 (1/11), 0.076923 (1/13) — so at 4-hour buckets each
  series snaps between a handful of discrete levels. Rendered with `.linear` interpolation this looks
  like a broken data feed.
- **"Field" (45%) is not drawn.** The visible lines sum to ~55% of the market and the chart never
  says so, which is why every line looks flat and small.
- **The x-axis truncates its last label** to `S…` for Sep 3.
- The range chips wrap their own text ("Sea / son", "24 / h") independent of my scroll hack.

### 3.5 `ChampionshipPathView` — season ladder · **outcome bars** primitive
`Components/ChampionshipPathView.swift` · shot `charts/35-event-mlb-below-chart.png`.

*Series:* three progression stages per team (Make Playoffs / Division / World Series).

What is bad:
- **The bars are invisible.** 3%, 1%, <1%, 43%, 26%, 1% all render as an identical ~2px hairline tick.
  The bar carries no information; only the number does. Compare `LadderCardView` (`census-14`), which
  draws the same idea correctly, in the same app.

### 3.6 Futures participants table — **outcome bars** primitive (not a chart, reads as one)
`Views/FuturesDetailView.swift` (`outcomesSection`) · shot `charts/36-futures-outcomes-table.png`.

- **The `Prob` column is too narrow and wraps every value onto two lines** — "14" then "%".
- The inline sparkline-bars are ~40px stubs that do not encode the value legibly.
- The `24h` column reads `+0.0%` for 8 of 10 rows: true, and useless as drawn.

### 3.7 Card sparklines / signal bars
`Components/SignalBarsView.swift`, `LiquidityMarkView.swift`, `ProbabilityBar.swift` — visible in
`census-01`, `census-02`, `census-05`, `census-06`.

- The three-bar confidence glyph appears on Discover cards **with no label and no legend anywhere**;
  it is a chart with no axis. On `census-02` it renders as two grey bars and one filled, on
  `census-01` as three green bars, with nothing to say what changed.

### 3.8 Charts NOT photographed and why
`TournamentChartView` (`Components/TournamentChartView.swift`, golf tournament page),
`TotalPointsSpectrumView`, `SeriesProbabilityView` (playoff-series pages only), `MarketMapView`'s
populated state, and the Watch/Widget mini-charts. All are reachable only from a page state that did
not exist on today's board or below a fold I had already spent two builds reaching. Each costs one
more `-censusScroll` shot on a build that already has the rail.

---

## 4. THE ONE-PARAGRAPH ANSWER TO ALEX'S QUESTION

Native has **21 card views for 6 archetypes** and **8 chart renderers for 4 primitives**, and the
backend's `discover_card` contract selects only 3 of the 21. The duplication is not in the shells —
those are broadly consistent — it is in the **probability row**: six different ways to draw "a name,
a bar and a percent", two different openers, and a confidence glyph with no legend. A cross-platform
card system should standardise that row first (label · full-width track · right-aligned value · one
accent · drawn terminal state — i.e. what `LadderCardView` already does), then the six archetype
shells on top of it, and let the backend name the archetype instead of the client inferring it from
an ordered predicate chain. On charts, three of the four primitives share one defect: **a fixed or
mis-fitted domain that leaves 30–55% of the plot empty while the data is crushed into a band**, and
two share a second: **axis furniture drawn on top of the axis labels**.

---

## 5. GAPS, STATED

- **iPad and Watch were not photographed.** Rail A renders at a fixed width, so an iPad shot is one
  extra `shoot(width: 834, …)` line per card (~2 min of test time, no new build); Rail B on iPad
  needs a second simulator boot. The Watch app has **no card views in common with iPhone** — it has
  its own `WatchHomeView` / `WatchLiveView` / `WatchGuessView` / `WatchMarquee`, four surfaces, none
  of which reuses any of the 21 above. That is itself a census finding: the Watch is a separate card
  vocabulary, not a narrow one.
- `NativeGroupCard` (bundle/theme) is `private` in `DiscoverView.swift` and cannot be rasterised from
  the test bundle; it is visible in `charts/33-discover-feed.png` only as the top of the feed.
- No issues were filed by this queue (census only). Recommended filings under #2910: items 1, 2, 3,
  5, 6, 11 of §2. Under #2911: §3.1's empty-domain + period-pill collision, §3.3's empty margin map,
  §3.4's off-axis leader and hidden Field, §3.5's invisible bars.
