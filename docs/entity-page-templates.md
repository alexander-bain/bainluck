# ENTITY PAGE TEMPLATES — the tier system for auto-generated league / competition / team / player pages

status: **RATIFIED 2026-08-11 (Alex — MC pass + filing instruction)** (drafted by Fable, 2026-08-11, at Alex's request: "design the template system that makes auto-generated pages feel curated, not like broken shelves")
grounded against: the live surfaces (`app/hub/[competition]`, `app/sport/[sport]` + `/[league]` + `/team/[team]`, `app/sports/[key]`, `app/event/[domain]/[slug]`), their routes (`hub.py`, `league_futures.py`, `teams.py`, `sports.py`, `event.py`, `prop_families.py`), rulings 003/012/021/025/026, `_PROBABILITY-DOCTRINE.md`, `docs/design-system.md`, `docs/chart-design-spec.md`, and production density samples measured today (§8).
companion visual: `docs/mockups/entity-page-tiers-mock.html` (the four tiers rendered side by side).
pointer ruling: [027](rulings/027-entity-pages-render-a-declared-tier.md). This doc carries no ordering or status — the build order (§9) and the register (§10) route to the board as issues (Operating Model v4).

---

## §0 THE PROBLEM, AND THE ONE-SENTENCE THESIS

Auto-generated entity pages die one specific death: **the template is designed for the rich case, and the thin case renders the rich case's chrome with nothing in it.** A section header over one card. A tab row with one live tab. A rail that doesn't scroll. "+1 more." An empty state that says "check back later" and nothing else. Every one of those is the page apologizing for its own existence — the broken shelf. We already grow them at home: the hub page renders a section header and a count chip over a single market; `sports/[key]`'s empty state is two sentences of nothing; the team page's prop-races section hides identically on "no props exist" and "the query timed out."

The thesis that prevents all of it:

> **A Bain Luck entity page is a stack of claims the product can stand behind — never a set of shelves to fill.** Data density determines how many claims we can make; the *tier* is a pure function of countable claims; and every piece of chrome must be earned by the count it organizes. A page with two markets is not a degraded 40-market page — it is a complete two-answer page. A page with zero is not a failure state — it is the entity's true current state, said plainly, with the record we uniquely keep.

This is the availability envelope (ruling 025) promoted from a response field to a page architecture, and the probability doctrine's A3 ("the number is honest or absent") applied to layout: **chrome is honest or absent too.**

---

## §1 INHERITED DOCTRINE (binds every template decision below)

| Binding | Source | What it forces here |
|---|---|---|
| Backend declares; clients render, never infer | rulings 003, 021, 025 | The **tier is a typed backend field**. Web and iOS must not each re-derive a layout from counts — two graders, one input, shared decision. |
| `availability ∈ {fresh, stale, degraded, empty}` | ruling 025 | Entity payloads carry it; **degraded ≠ empty** gets two different renderings (§6). Per-item swallows counted in `pool_counts.dropped`. |
| The blend is the product | standing ruling; doctrine A1 | One number per question, everywhere on these pages. No per-source lines, no client-side means (§10 E9 — the champ-path mean must die). |
| Honest or absent; nothing beats unhelpful | doctrine A3; design-system | No filler sections, no empty chart frames, no fabricated series. A signature element below its data floor renders **nothing**. |
| Settled means settled | standing ruling; doctrine A4 | Settled markets never inflate the live-answer count; they feed the Record Strip (§5.3) in results grammar. |
| No smoothing; fixed 0–100 axis | chart spec P1/P4 | The Journey Line (§5.2) inherits all four chart principles unmodified. |
| No gambling enticements | standing ruling | Probabilities only; no volume-as-proof; no drama-zoom. Auto-generation multiplies surfaces, so one leak becomes N leaks — the formatter and the template are shared or nothing. |
| Registers, not runtime fuzzy matching | grid-register program (2026-07-31) | Entity → data wiring lives in agent-maintained per-entity registers, never hand-maintained page constants (`SHOWCASE_DATES`, `LEAGUE_COLORS`, `GRID_SLUG_MAP` — §10) and never render-time name matching (`findGolfTournament`). |
| Manufactured work is worse than no work | ruling 012 | An empty-handed page state is legitimate **with evidence**: `data-empty-state-name` hooks so the audit rail can prove honest-empty vs broken-blank (the `SportsEmptySlate` precedent). |

---

## §2 THE TIER SYSTEM — what density earns what layout

### The unit: an ANSWER, not a market row

Raw market counts lie in both directions. Esports holds 190 open markets of which 112 are per-map matchup noise; ten Polymarket sub-markets are one question. The resolver therefore counts **answers**:

> **answer** = a distinct live question about this entity — markets deduped by `group_id` + `canonical_market_key` — that survives the doctrine's Step 1 (a blend number we can stand behind: withholds and phantom placeholders excluded) and is **not settled** (settled items feed the record, not the answer count).

Everything below keys off four countable inputs, all computed server-side:

- `answers` — as defined above
- `sections_populated` — count of section groups holding ≥ 3 answers each
- `timeline_ok` — ≥ 1 hero-worthy market with ≥ 5 real snapshots spanning ≥ 24h (we never invent a series)
- `record_n` — resolved outcomes about this entity with a graded `is_winner` in **our** DB (survives the Kalshi purge cliff, gotcha #35 — this count is ours in a way no source can take back)

Plus two context fields: `next_event` (upcoming/live events count) and `season` (`in_season | off_season | unknown`, via `utils/season_windows.py`).

### The four tiers

| Tier | Gate (v1 thresholds) | The page is a… | Body grammar |
|---|---|---|---|
| **T3 FULL** | `answers ≥ 12` AND `sections_populated ≥ 3` | **map** | Themed section shelves, anchor nav, movers, counted caps |
| **T2 STANDARD** | `answers 4–11`, or ≥ 12 without the sections | **list** | One column, flat answer list with inline group labels — no shelf chrome |
| **T1 ANSWER** | `answers 1–3` | **answer** | Each answer full-width at full depth; zero navigation chrome |
| **T0 PRESENT** | `answers = 0` AND entity is real (identity + at least one true thing to say: `record_n ≥ 1` or `next_event` or a known season) | **statement** | §6 — identity at full fidelity, the one true sentence, the record, one live up-link |
| *(no page)* | none of the above | — | Generation gate: an entity with no identity and nothing true to say resolves to search / 404 (negative-cached, the event-concept pattern). **Never generate a page whose only content is its own URL.** |

Threshold posture (the C23 lesson — no constant scatter): all five numbers above (12, 3, 3-per-section, 4, 5-snapshots/24h) live **once**, in one module (`utils/entity_page_tiers.py`), each with its WHY, tuned against the measured tier histogram (§9 step 0 produces it), not against vibes. They are starting values; the *structure* — four tiers, count-gated, server-decided — is the ruling being asked for; the numbers are calibratable mechanics.

Two structural notes:

1. **The tier is a field on the payload** (`tier: full|standard|answer|present`), computed next to `availability`. Ruling 021 is the reason this is non-negotiable: the moment web and SwiftUI each count arrays to pick a layout, the same team renders as a map on web and an answer on iOS, and the parity bug is unfindable because both sides are "correct."
2. **Tiers are per-page-load, season-aware, and expected to move.** The Bruins are T2 in March and T0 in August. That is the system working — the page breathes with the season instead of fossilizing around its richest week.

---

## §3 SHARED ANATOMY — and how 2 markets differs structurally from 40

Every tier renders the same spine, in the same order. The tier changes the body's grammar, never the page's identity — which is precisely what makes a thin page read as *complete at its size* rather than as a starved rich page.

```
1  Up-link            breadcrumb into the hierarchy (mesh rule: an up-link must land on a
                      surface that verifiably has content — link up again until one does)
2  Identity block     name, logo/colors, ONE true status fact (record, standings, season
                      phase, or next event). NEVER degrades with data thinness.
3  Headline Answer    signature element §5.1 — the entity's one number, or its settled result
4  Journey Line       signature element §5.2 — when timeline_ok, else absent
5  BODY               the only tier-variant region (below)
6  "The record"       signature element §5.3 — any tier, whenever record_n ≥ 1
7  Adjacent context   T1/T0 only: ONE labeled shelf from the parent entity ("From MLB")
8  Provenance footer  "N markets tracked · aggregated from K sources · as of {t}"
                      + the availability state whenever it is not fresh
```

### The body at 40 answers (T3): the page is a map

Navigation chrome has real work to do, so it exists: section shelves by theme (the `league_futures` sections — series / awards / props / season stats), an anchor pill nav listing **only sections that will actually render** (the event-concept page already does this right), a movers strip when ≥ 3 real movers, per-section counted caps. Abundance needs curation as much as scarcity does — the esports hub's 112 matchup markets don't get dumped; they get capped at the section's display budget with the remainder *counted and linked*: "Showing 12 of 112 · Browse all →". A silent truncation reads as coverage (ruling 025 clause 3: a swallow that counts is detection; a swallow that doesn't is concealment). The overstuffed shelf is the broken shelf's twin.

### The body at 2 answers (T1): the page is the answer

Zero navigation chrome, because there is nothing to navigate. Both markets render **full-width at full depth** — question as the title, blend number large, 24h delta, their own Journey Lines, top outcomes, movement explanation where the attribution engine can name a cause. The two cards ARE the page. What fills the page honestly is **depth per answer instead of breadth of answers** — then the record, then one clearly-labeled shelf of parent context ("From MLB" on a thin team page; real content, labeled as belonging to the parent, never disguised as the entity's own coverage).

Banned at T1, by name: a section header over the cards ("Markets (2)" is shelf cosplay), a count chip (at two answers the count is visible; "2 markets" as a stat is an apology), tabs, rails, "+1 more", and any grid that would render a single orphaned row.

### The invariant across both

Same spine, same signature elements, same voice. A user who lands on NASCAR (1 answer, measured today) and then on MLB (35) should recognize the same product at two honest sizes — not a flagship page and a broom closet.

---

## §4 THE CHROME-EARNING GRAMMAR (the whole anti-broken-shelf rulebook)

Containers are gated, not items. Every rule is a count check the layout component enforces once, for every entity class:

| Chrome | Earns its place when | Below that |
|---|---|---|
| Tab row | ≥ 2 tabs, each ≥ 3 items | Stacked sections |
| Section header | section ≥ 2 items AND ≥ 2 sections on page | Content sits directly under the hero, unlabeled |
| Horizontal rail | ≥ 4 items | Grid / stack (a 2-card carousel is a broken carousel) |
| Grid | ≥ 3 items | Vertical stack |
| "+N more" | N ≥ 2 | Render the one extra item |
| Count chip ("35 markets") | T2+ | Absent |
| Movers strip | ≥ 3 movers above the movement floor | Absent |
| Anchor pill nav | ≥ 3 sections that will render | Absent |
| Section cap | always counted: "Showing X of Y · Browse all" | — (uncounted caps are concealment) |
| Skeleton loader | only for content that is actually coming | Never a skeleton that resolves to nothing (fail closed on empty — design-system) |

Two template laws inherited from the feed's scar tissue, now applied to every entity page:

- **Gotcha #42:** per-item try/except in every section builder — one bad market never blanks a page. And per ruling 025 clause 3, every such swallow increments `pool_counts.dropped`.
- **Gotcha #43:** caps are scoped by card type, and every cap's guard test asserts BOTH directions — the flood stays capped AND the adjacent section stays populated.

---

## §5 THE SIGNATURE ELEMENTS — what makes a page unmistakably ours

Three, chosen so that each one is something Kalshi/ESPN structurally *don't* do, each degrades honestly, and together they are the page's spine at every tier.

### 5.1 THE HEADLINE ANSWER — every page leads with one answered question

The entity's single most important live question, rendered as: **plain-language question → one blended number (JetBrains Mono, huge) → 24h delta chip**. "Win the World Series? **12%** ↑1.2 today." Per class: team = championship path tier-1 (shipped, with the futures fallback chain); league = title favorite ("Most likely champion: Dodgers · 22%"); competition = winner favorite or the next edition's headliner; player = their top live market.

This is A1 made architectural: a Bain Luck page always *answers something* above the fold — the anti-ticker-list. Kalshi's entity answer is a list of tickers; ours is a sentence with a number.

Degradation ladder: no live answer → the hero shows the entity's **last settled result in results grammar** ("2025-26: eliminated in the Conference Finals — markets had them at 31% peak") → no record either → identity block alone. The number slot is never empty and never fabricated; the label is always a question or a result, never a raw market name.

### 5.2 THE JOURNEY LINE — the season as one honest line

One line, fixed 0–100 axis, 0/50/100 ticks, no smoothing, gaps as gaps — chart spec P1–P4 verbatim. The entity's defining question over time: a team's championship probability across the season (`TeamSeasonJourney`), a league's title race (top-5 `EvolutionView`), a competition's race-to-title, a player's award race. **Settled entities freeze it as the completed journey** with the champion's line emphasized (`SettledPathChart`) — the page's memory of the season, not a stale live chart.

Why it's ours: nobody else draws "the season as one line" at the entity level, and our line is contractually honest — every kink is real (movement is the product; an ugly line files a data bug, not a smoothing PR). Four shipped components already do this in fragments; the template unifies them behind **one component contract** (props: market_id(s), domain, settled?, champion?) instead of four ad-hoc ones.

Degradation: `timeline_ok` false (fewer than 5 real points / 24h span) → **absent entirely**. No two-point "lines," no interpolated theater. The slot collapses; nothing announces the absence (A6: unmeasured is not doubted).

### 5.3 "THE RECORD" — the receipts strip

For settled questions about this entity: what the markets said, and what happened. Row grammar is the shipped settled language: *"{question} — {opening%} → Won"* / HIT / MISS chips, the upset line ("Markets gave this just 18%") where it applies, the L2-158 recents grammar on games ("We had them at 72% — won 6-2"). At `record_n ≥ 5`, one count-based summary line on top: **"14 questions settled this season · favorites hit in 9."** Counts, never percentages, below calibration-grade n (the /calibration small-n honesty, ported); at `record_n < 1` the strip is absent.

Why this is THE differentiating element: **no betting surface shows you receipts, because receipts embarrass them — our entire thesis is the public record.** It is the moat made visible on every page (the join + the forward record + the referee seat), and it is literally purge-proof: Kalshi deletes market data past ~74–86 days (gotcha #35); our graded outcomes don't go anywhere. On a T0 page the Record Strip is not a garnish — it is the *content* (§6). One tap deep-links to /calibration, the trust engine, from every entity in the product.

Label: **"The record"** (Alex, 2026-08-11 MC). That is the *section title* on entity pages; the row-level settled grammar is unchanged (✓ Won / Miss chips, "{opening%} → Won", "we had them at 72%"), and the props program's "What hit" stays where it ships today — one settled grammar, two surface titles, each in its native register.

---

## §6 HONEST-EMPTY (T0) — ruling 025 applied to a whole page

### The exact rendering (one rendering — clause 5)

1. **Identity at full fidelity.** Logo, team colors, name, record/standings. A real entity's empty page must be *visibly premium* — the moment identity degrades with data thinness, the page reads as broken rather than quiet.
2. **The one true sentence, with the WHY and the WHEN.** Season-aware via `season_windows`: *"No open markets on the Bruins right now — NHL futures usually return in September."* A named situation, not an apology. "Check back later," alone, is banned copy (it names neither).
3. **What is true right now.** Next scheduled event as a real card (with its pregame number when one exists); current standings fact.
4. **The Record Strip as the centerpiece.** *"Markets settled 14 questions about the Bruins this season"* + the graded list. An off-season entity page is a *results* page — this is what makes T0 feel curated instead of vacant, and it is content only we can serve (§5.3).
5. **One up-link with a live count:** *"NHL right now: 23 open markets →"* — the parent's actual count, so the link is a promise the destination verifiably keeps. Never link from one empty room into another (if the parent is also empty, link up again).
6. **Follow/pin affordance** — "we'll surface it when it moves" (feeds the digest, the one sanctioned notification).
7. `data-testid` + `data-empty-state-name="entity-{kind}-present"` — the browser-audit rail must be able to *prove* honest-empty vs broken-blank (the `SportsEmptySlate` precedent; ruling 012's evidence requirement).

### Degraded is not empty — the distinction the current pages conceal

Ruling 025's states answer "is this response the real thing?"; the tier answers "how much is there?". They compose, and the composition is the whole game:

- `availability: fresh` + `tier: present` → **honest-empty** (above). We checked; there is nothing; here is what's true.
- `availability: degraded` (a section query timed out, a source failed) → **NOT honest-empty.** Render the degraded state: last-good with a stale label where a mirror exists, or a quiet inline "Couldn't load markets right now — retry." A data outage must never wear the empty state's clothes.

Named violation, today: the team page's enrichment sections "degrade to their empty value" on failure by design (#1197/#1239 comments in `teams.py`), and `prop_families.py` returns an empty-families **200** on its own statement-timeout — so "the Bruins have no prop races" and "the prop-race query died" render **byte-identically**. That is ruling 025 clause 4 verbatim (a plausible substitute served without declaration) and gotcha #53's shape (an empty 200 read as an absence). The resilience behavior is right; the *undeclared* part is the defect. Same class: `hub.py` serves a 24-hour-old whole-hub snapshot as a stale fallback with no availability field at all, and `event_concept_cache` declares availability in a non-conforming vocabulary (doctrine C17). The entity envelope (§7) is where this family gets fixed wholesale.

---

## §7 THE BACKEND CONTRACT — one envelope for every entity class

`GET /api/entity/{kind}/{key}` (or the existing per-class routes upgraded in place — either way, **one shape**):

```jsonc
{
  "entity":       { "kind": "team", "key": "boston-bruins", "name": "…", /* identity, colors, logos */ },
  "availability": "fresh | stale | degraded | empty",          // ruling 025, conforming vocabulary
  "tier":         "full | standard | answer | present",        // §2 resolver — client renders, never infers
  "headline":     { "question": "…", "probability": 0.12, "delta_24h": 0.012, "market_id": 123 }
                  /* or { "settled": { … results grammar … } } or null */,
  "journey":      { "market_ids": [123], "settled": false } | null,   // present only when timeline_ok
  "sections":     { "awards": { "items": [...], "total": 8, "shown": 8, "dropped": 0 }, … },
  "record":       { "n": 14, "summary": { "settled": 14, "favorites_hit": 9 }, "items": [...] } | null,
  "next":         { /* next event brief, with pregame number when it exists */ } | null,
  "season":       { "state": "off_season", "label": "2026-27", "reopens_hint": "September" } | null,
  "parent":       { "kind": "league", "key": "nhl", "name": "NHL", "open_answers": 23 },
  "pool_counts":  { "answers": 0, "dropped": 0, "settled": 14 }
}
```

Notes that carry the doctrine: every count the page renders arrives *in* the payload (clients never derive `shown/total` by measuring arrays); `dropped` is the clause-3 counter; `parent.open_answers` is what makes the T0 up-link a kept promise; the tier and availability are the two typed decisions of rulings 021/025. Native gets all four tiers **for free** — the payload-v2 posture (display semantics server-side so all platforms heal together) is exactly this envelope. Cache policy per class follows the event-concept pattern (primary TTL + stale mirror + single-flight refresh + negative cache), with the stale serve *declared*, closing hub.py's silent version.

---

## §8 THE ENTITY CLASSES — what exists, measured today (2026-08-11, production)

| Class | Surface today | Data today | Measured density | Tier range expected |
|---|---|---|---|---|
| **League** (~30) | `sport/[sport]/[league]` — most bespoke page in the product (hand-configured colors/slugs/dates) | `league_futures` sections + grids + feed — richest per-entity data | MLB **35** (awards 8, props 27) · NBA **37** · NASCAR **1** | T3 in season → T1 (NASCAR, today) → T0 (off-season) |
| **Competition** (dozens) | Three overlapping surfaces: `hub/[competition]` (5 configs), `sports/[key]` (legacy thin list), tournament slices of the league page; `event/[domain]/[slug]` covers *instances* | hub composition (concepts + league_futures) | esports **190** (112 matchup noise → the answers-not-rows case) · MMA **7 + 10 upcoming** | T3 → T2; standing competitions between editions are the flagship T0 case |
| **Team** (thousands, incl. minor-league affiliates) | `sport/…/team/[team]` — already the most tier-aware page (self-suppressing sections, headline fallback, "What hit" rows) | `/api/teams/{slug}` + prop-families + grid | Red Sox **9 futures, 5+5 games** (in-season; champ path empty — live gap) · Jazz **30 futures, 0 upcoming** (off-season player-movement) | T2/T1 mostly; long tail (Worcester Red Sox exists in the table) is T0-or-no-page |
| **Player** (tens of thousands potential) | none — no first-class person entity; roster JSONB + name-ILIKE is the current matching | player props per event; awards/next-team futures reachable by name match | stars: 5–20 answers; everyone else: 0, forever | T1/T0 native; the generation gate matters most here |

Read of the table: the classes conveniently exercise the tiers in order — leagues prove T3→T1 on ~30 low-risk entities with existing endpoints; competitions prove consolidation + the between-editions T0; teams prove the long tail and the generation gate at thousands-scale; players are a *new entity type* before they are a new page type.

---

## §9 THE RANKED BUILD ORDER

**Step 0 — the kernel (one queue).** `utils/entity_page_tiers.py` (resolver + the thresholds, named once) + the envelope fields (`tier`, `availability`, per-section counts, `pool_counts`) + `EntityPageLayout` (the §3 spine + §4 grammar as one client component) + the three signature elements behind single contracts (§5). **Prove it by re-rendering `hub/[competition]` through it** — five configs, lowest blast radius, already the closest shape. Acceptance: MMA hub (7 → T2) and esports hub (190 → T3 with counted caps) render correctly; zero one-item shelves anywhere; `data-empty-state-name` hooks present; the **tier histogram** script exists (counts every known entity per class per tier — the instrument that tunes §2's thresholds and sizes every later step).

**Step 1 — Leagues (~30 entities).** Wire `sport/[sport]/[league]` through the kernel. The hand-maintained constants (`LEAGUE_COLORS`, `GRID_SLUG_MAP`, `SHOWCASE_DATES`) and the render-time golf fuzzy-matcher move into agent-maintained per-league registers (the grid-register ruling: Alex never hand-maintains; runtime fuzzy matching dies). Acceptance: MLB renders T3, NASCAR renders T1 (its one answer full-width, no shelf), one off-season league renders T0 with a season-aware sentence; Flow Sentinel gains the per-tier checks (a T3 page with an empty container = defect; a T0 page with chrome = defect).

**Step 2 — Competitions.** One standing-competition page per entity (The Masters, the World Cup, UFC as a promotion) on the kernel; `sports/[key]` retires into it with redirects (ratified 2026-08-11); `hub/[competition]` configs become register rows; **event concepts stay the per-instance surface** (a competition page is "The Masters" across years; the concept page is "The Masters 2026" — the competition page's upcoming rail and record strip link down into instances). Payoff concentrated here: a major is empty ~51 weeks a year, so the between-editions T0 — last edition's settled result + record + countdown + follow — is the page that makes the whole system look curated.

**Step 3 — Teams (thousands; the long tail).** Adopt the envelope on `/api/teams/{slug}` (the page already has most of the anatomy); add the Record Strip (graded data already rides the payload — `is_winner` on team futures + the L2-158 pregame numbers on recents); **declare the degraded states** (§6's named violations: prop-families timeout, enrichment-section failures); set the generation gate — a team with no events and no markets *ever* resolves to search, not to a page (Worcester Red Sox should not have a broken shelf). Acceptance: Red Sox T2 with record strip; an off-season NHL team T0; a degraded-fetch team renders the degraded state, provably distinct from T0.

**Step 4 — Players (gated, last).** Two gates before any page exists: (a) **person entities in the entity registry** (canonical id + aliases — roster-JSONB name-ILIKE is not an identity system, and player pages hang off identity); (b) **demand-driven generation** (ratified 2026-08-11): start from the search-log allowlist (the instant-answers posture: no new surfaces until evidence demands them — a player page is Phase 4's "destination" answer, so let search demand nominate the first hundred). Player pages are T1-native by design — a player is usually an answer ("Where will LeBron play? Lakers 62%"), sometimes a T2 (stars in award season), and T0 with a record the rest of the time. The tier system is what makes this class shippable at all: the 400th-ranked player's page is *designed*, not neglected.

Each step is one-to-two queue-sized units, ships with live proof at both density extremes, and updates the tier histogram so the next step is sized by measurement.

---

## §10 REGISTER — where today's surfaces violate this spec (verified in file, this session)

- **E1** `hub/[competition]/page.tsx` — sections render at length ≥ 1: a section header + count chip over a single card (§4 violation); `+{n} more` fires at n=1.
- **E2** `hub/[competition]/page.tsx` `OutcomeRow` — null probability renders a 0%-width bar (`width: ${pct ?? 0}%`): null drawn as a claim (doctrine C6 family).
- **E3** `sport/[sport]/page.tsx` — `SHOWCASE_DATES` hand-maintained date strings ("The Masters": "April 2026" — already in the past today); `LEAGUE_COLORS` raw Tailwind palette classes (token violation); `findGolfTournament` render-time fuzzy name matching (register ruling violation); every league card promises "View schedule & odds" whether or not anything exists behind it.
- **E4** `sports/[key]/page.tsx` — the anti-pattern empty state: "No upcoming events / Check back later for more games" (no why, no when, no record, no live up-link); header claims "Upcoming games with win probabilities" unconditionally.
- **E5** `sport/[sport]/[league]/page.tsx` — `GRID_SLUG_MAP` hardcoded in the page; "View full grid →" links to the page it is already on.
- **E6** `teams.py` / team page — enrichment failures degrade to empty values **undeclared** (ruling 025 clause 4): outage and absence render identically. Same class: `prop_families.py` empty-200 on statement timeout; `hub.py` serves the 24h stale snapshot with no availability field.
- **E7** `teams.py` — Red Sox (in-season) serves an empty `championship_path` and `season: null` (measured today): the headline falls back correctly but the page's numbers don't declare their season (Queue #242's own rule).
- **E8** `league_futures.py` — "effectively resolved" markets skipped on **price alone** (leader ≥ 0.97 & opened ≥ 0.85; all-outcomes <0.03/>0.97): the C16 class. Whatever Alex rules on C16 for Discover binds here identically; and either way the skip must be **counted** (clause 3), which it currently isn't.
- **E9** `teams.py::_get_championship_path` — averages probabilities across sources (a client-adjacent **mean**, a second blend algorithm): doctrine A1a / C2's sibling. The path should read the canonical blend, not roll its own.
- **E10** `event_concept_cache.py` — availability declared in non-conforming vocabulary (`live/stale_ok/unavailable`) — already registered as doctrine C17; the entity envelope adopts the ruled four-state vocabulary from day one.

---

## §11 DECISIONS — resolved by Alex, 2026-08-11 (MC)

1. **Receipts-strip label: "The record."** Section title on entity pages; row grammar and the props program's "What hit" unchanged (§5.3).
2. **T1 adjacent context: on-page shelf, labeled** ("From MLB", capped ~4) — real content, honestly attributed.
3. **`sports/[key]`: retire + redirect** into the templated league/competition pages at step 1/2.
4. **Player generation gate: search-demand allowlist** first, after person-entities land in the registry.

Still open, deliberately: **the threshold taste-check** — after step 0's tier histogram exists, a 5-minute MC pass on the §2 numbers (12 / 4 / 3-per-section) against real examples per tier. The numbers are mechanics; the histogram is what makes that pass an evidenced choice instead of a vibe.
