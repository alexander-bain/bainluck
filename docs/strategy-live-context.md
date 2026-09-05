> **RATIFIED AS A RECORD, not as a plan (Fable-5, 2026-09-05).** This is a 2026-08-11 proposal
> preserved for the decisions it carries — Alex's 2026-08-11 rulings and the catcher's-son test.
> Its code survey and line numbers are from 2026-08-11 and are stale; verify anything before
> building on it. **No lane builds from this document without a new queue that names its own
> pillar and ship** (QUEUE LAW + THE RIDER RULE, `CLAUDE.md`).
>
> Landed on master from `rescue/orphan-wip-2026-08-19` (commit `7ac3ae3a`, rescued per gotcha #52),
> where it had sat as the branch's only unique file for 25 days. Body below is unchanged from that
> commit, including its own `status: PROPOSAL` line and its self-named ratification path.

# STRATEGY — LIVE CONTEXT: the feed reworks itself around liveness

**status: PROPOSAL** (Fable, 2026-08-11) — seeded at repo root per the underscore convention; on ratification → `docs/strategy-live-context.md`.
**decisions 2026-08-11 (Alex, MC):** slice 1 routes **issue-first** (seed: `_ISSUE-LIVE-CONTEXT-SLICE-1.md` — connector writes 403'd, a lane runs the `gh` line) · **I4 deliberately left unruled** — guard tests assert current marquee-always-top behavior, no ruling file banked · **PLE calendar slate rides M6's queue.**
**scope:** where live props surface · how relevance decays · interaction with the `[marquee] + [≤3 games] + [remainder]` composition · the catcher's-son test · ranked mechanisms with the smallest shippable slice named.
**relates:** #1588 (P1 truth violation — the named failure of this gap) · #1629 (props bucket empty on live games) · #1244 (live-page dogfood, waiting on Alex) · #1102 (context-free grouped strip) · ruling 2026-08-08(d)(1) tonight's-games lead · (d)(3) truth violations outrank polish · ruling 016 (story-card arc owns new card types) · ruling 025 (availability envelope) · Queue 325 (search scorer, in flight) · P3 props-are-the-story.

---

## 0. Thesis

**Liveness is a STATE on props and a PREFERENCE inside existing feed slices — never a new card type, never a new slice, never a price format.**

When a game is live, its props are at peak relevance and perishable. Today the system knows events are live (status, EI, period + clock, live win-prob, the tonight's-games lead) but **props have no concept of time at all**: a first-inning prop quotes 52% "No" in the third inning (#1588), the props section on a live game is sorted by threshold value, and the feed's game cards carry zero props. The design below adds one shared clock and lets every surface read it.

---

## 1. What exists today (build on it, not beside it)

**Events already have liveness, end to end.** `Event.status`, `period` + `game_clock` (models.py:173, ESPN enrichment), live-first ordering in the feed event pool, the live noise-filter exemption (feed.py:1022), EventCard's live treatment (border, pulsing badge showing period/clock, inline score, probability chip), search ordering live-first (events.py:1661) with `EVENT_LIVENESS_LEVELS` (live > soon > this-week) already ratified as T5 in the search scorer spec, and 2-minute live polling for linked prediction markets.

**The composition is already ruled and shipped.** Ruling 2026-08-08(d)(1) via `_pin_marquee_items` + `lead_with_tonights_games` (feed.py:2200–2230): **[calendar-flagged in-progress marquee concepts, + a ≤36h what-hit hold] + [≤3 tonight's games — live first by rank, then soonest within 4h, team-media required] + [the Discover mix]**. Both passes are pure stable bounded reorders that touch no score, drop nothing, and return the input unchanged on error (the #1091/#42/#43 shape). This is the pattern every mechanism below must copy.

**Props have the bones but no clock.** `game-markets` (events.py:5099) already classifies `period_markets` (half_*/quarter_* types), already serves the `props_script` contract (#195: `pregame_mark` / `current` / `graded_result` — THE SCRIPT, live, WHAT HIT), and already caches live responses at a 30s TTL. But grading only happens when `event_is_finished`, nothing expires a segment prop mid-game, and nothing orders props by what is alive. `_estimate_game_pace` (events.py:5001) already parses period + clock into `fraction_elapsed` per sport — the progress engine the prop clock needs, currently private to the pace widget (extract-on-touch, ruling 005).

**The named failures this design answers:** #1588 (a settled in-game prop stating something false with a confident number — ruled to lead the queue), #1629 (PlayerPropsDashboard renders on none of 4 measured live games — the anchor surface is starving), #1102 (props surfaced context-free by global pooling), and Kalshi's live experience being the reason Alex still opens it during games (failure class 6).

---

## 2. The catcher's-son test (canonical definition)

Dexter is thirteen, catches, steals bases, and watches WWE. **The test: Dexter opens the app in the middle of a WWE premium live event.** He passes zero navigation and has zero betting literacy. The app passes if, in one screen:

1. **The event finds him.** Top of feed, live-marked. He does not search, scroll, or know the word "futures".
2. **The number is the now.** The headline probability is the current state of the match — moving — not the pregame line, not a stale snapshot. (If the data is stale, it says so or steps down — honest-or-absent, never confidently wrong.)
3. **Everything shown is still undecided.** Anything decided renders as a **result** (✓/✗, winner named), never as an open probability. A prop about a finished match is a story, not a prediction. (#1588 is the anti-pattern.)
4. **It reads at thirteen.** Plain questions and percentages: "Match goes 20+ minutes — 42%." No −150, no "O/U 19.5", no dollar framing. The word "odds" is fine; price formats are not.
5. **The story continues.** What's next on the card is visible — the reason to stay is on the screen.

**The 10-second question:** can Dexter answer *"who's winning, and what's about to happen?"* in ten seconds? That is the whole test.

**Why WWE, and not a Sunday NBA game:** WWE is deliberately the hard case. No Odds API coverage, no ESPN clock, no box score — prediction-market-only, with liveness knowable only from the calendar and from the markets themselves moving. If live context only works where a data feed hands us `period` and `game_clock`, we built a stick-and-ball feature. If it works for WWE, the system's liveness is real. (It also generalizes: Oliver mid-Patriots-game and Lisa mid-royal-announcement are the same test with easier data.)

**Where the test stands today — failed at step 1, honestly:** WWE exists only as a `domain: wwe` calendar entry (WrestleMania 43, `archetype: card`, "No adapter yet"), the recurring PLE slate (SummerSlam, Royal Rumble, Survivor Series) is not in `majors_calendar.yaml` at all, and the search gold registry records that the query "wwe" **currently ranks The Emmys first**. The seeded WrestleMania card (per-match probabilities, storylines, lock times) proves the shape works; it has never run against live ingestion. The test is therefore also the acceptance test for mechanism M6.

The pre-game ritual test (P3) is Alex before the game; the catcher's-son test is Dexter during it. THE SCRIPT already has its test; this is THE DIVERGENCE's.

---

## 3. The prop clock: scope taxonomy + decay

**Decay is game-state-indexed, never wall-clock.** "A prop about the 1st quarter is dead by the 3rd" understates it: it is dead at the *end of the 1st*. The clock that matters is ours — `period` + `game_clock` where a source gives them, the liveness ladder (§M6) where none does.

### Scope classes (deterministic, from name + market_type — no LLM)

| Scope | Examples | Alive until | Then |
|---|---|---|---|
| **game** | winner, total runs, match winner | final | graded |
| **segment(n)** | "run in the 1st inning", half/quarter totals | end of segment n, by OUR clock | **expired** the moment the segment passes; graded when authority confirms |
| **occurrence** | first TD scorer, anytime HR, "will there be OT" | the occurrence, or final | graded at occurrence |
| **threshold** | player 25+ pts, pitcher 6+ Ks | final — except a **monotone counter that has crossed its line** may grade "hit" early from the box score (2 hits is 2 hits); the "under" side never grades early | graded |
| **match(n)** | match n on a card (WWE, UFC, award n of a ceremony) | that match's lock/settle signal | graded; the card's "current match" pointer advances |

`period_markets` classification already half-does this (half_/quarter_ market types); the classifier extends it with a name regex for inning/quarter/half/period/first-X. Ships with a labeled fixture set, not vibes.

### The state machine

`pregame → live_open → { settled_hit | settled_miss | scope_expired }`

Two principles keep it doctrine-clean:

- **Expiry is ours; settlement is the authority's.** We may move a prop out of the live rail because *our* game state says its window passed. We may never mark it hit/miss from price (A4 — price never decides), and we may never leave it quoting an open number because Kalshi's status still says "open" (gotcha #33 means upstream status LAGS mid-game — waiting on it is how #1588 happened).
- **Two exits, both stories — never garbage.** Settled → WHAT HIT, graded in real time (✓/✗ + actual). Expired-but-ungraded → **"ended — grading"** with no probability shown (honest-or-absent). The state where a dead prop shows a live number does not exist by construction.

### Ordering within LIVE, and freshness

Live-open props order by **divergence from script** (|current − pregame_mark|, both fields already in the props_script contract), tiebreak by 10-minute movement from live snapshots. Both are *measured* quantities. No suspense/leverage formula in v1 — the Discover exit exam's Annex A is the standing lesson that an uncalibrated scorer must not get a purpose-built stage; a leverage model can audition later against labels.

Freshness is orthogonal to scope: live polling is 2-minute cadence, so a linked market whose last snapshot is >10 min old **on a live event** leaves the live rail and declares itself (ruling 025 vocabulary; muted per the 80/60 confidence treatment). A stale number on a live surface is the cardinal sin — the gate is at surfacing, not card-state.

---

## 4. Where live props appear — the surfaces, ranked

**S1 — Event page (the anchor).** The user already chose this game; depth belongs here. Live mode = props reordered by the clock: **LIVE NOW** (open, by divergence) → **STILL TO COME** (scope not yet reached — the remaining script) → **DONE** (graded compact, updating in real time, not waiting for final). This *is* THE DIVERGENCE view Alex named. Zero feed risk, fixes the standing P1, and it's where the pre-game ritual continues into the game.

**S2 — Feed, in-card only.** The ≤3 tonight's-games cards (and live cards on /sports and My Stuff) gain **one line** under the probability bar: the top live prop by divergence — *"8+ total runs — 74%, up 12 since first pitch"*. The card gets richer; the deck does not get longer. Data path: the 2-minute live poll precomputes `top_live_prop` per event into Redis; the feed reads a key, never a join. Card degrades to today's card when the key is absent (per-item guard, #42).

**S3 — Search, context not ranking.** Ranking is already handled: T5 liveness levels are in the ratified scorer spec and Queue 325's lane owns `events.py` — this program does not touch ranking. The addition is **consumption**: when the top hit is live, the result card carries the live probability + period + top live prop, so search answers "who's winning" without a click (Instant Answers' bar: faster than Kalshi). Sequenced strictly after 325 lands. One spec question routed to that lane, not solved here: concepts need a liveness level too, or "wwe" during a PLE still ranks the Emmys first.

**S4 — Watch glance (noted, not scoped).** The cocktail-banter mini-feed is the natural fourth surface; it inherits S2's precomputed key for free. P7, post-iPhone-bar.

**Rejected: standalone live-prop cards in the remainder.** A live game spawning 5 prop cards is the golf-flood failure with a live badge; caps fight it forever, in-card carriage kills it by construction. Also: ruling 016 gives new-card-type decisions to the story-card arc — a "live moment" card, if ever, is a story card told from the live angle, and belongs to that arc.

---

## 5. Composition interaction: five invariants

The composition rule survives liveness untouched. Liveness **reorders within slices and enriches cards; it never changes the slice arithmetic.**

- **I1 — The shape is fixed.** `[marquee pins] + [≤3 games] + [remainder]`, exactly as shipped. No live rail, no fourth slice, MAX_LEAD stays 3.
- **I2 — Within the games slice, the clock orders.** Live first (by rank), then soonest-to-start — already `_lead_sort_key`. A game that goes final exits the slice on the next build — already `_is_eligible`. New work here is only guard tests asserting BOTH directions (#43: the flood stays capped AND the adjacent surface stays populated).
- **I3 — Props never occupy slots.** They ride inside event/concept cards (S2). This is the invariant that makes live props flood-proof forever.
- **I4 — Marquee precedence is unchanged.** An in-progress marquee concept keeps the very top; a live game outranks it never — the World Cup final over a Tuesday Padres game, always. *(Ruling-shaped: recommend ratifying current behavior — see §8.)*
- **I5 — Settled means settled, at card grain.** Final ⇒ the card converts to result form (winner + "3 of 5 props hit"), the marquee what-hit hold already models this for concepts. A live-enriched card never shows its prop line after final.

Degradation is symmetric: zero live games → today's feed, identical (the lead pass no-ops). Eighteen live games → still three, diversity intact, the rest on /sports where the scoreboard belongs.

---

## 6. The ranked mechanism list

Ranked by user-visible payoff per unit cost, dependency-ordered. Sizing: one queue session each unless noted.

| # | Mechanism | What ships | Payoff | Cost/risk |
|---|---|---|---|---|
| **M1** | **The Prop Clock** — `utils/prop_live_state.py`: scope classifier (deterministic regex + market_type) + game-progress extraction from `_estimate_game_pace` + the state machine of §3 | The shared truth every surface reads | Enabler; invisible alone — **ships inside M2, never solo** (visible-payoff rule) | Low. Pure logic, fixture-tested |
| **M2** | **Event-page live mode** (S1) — `game-markets` annotates `props_script` + `period_markets` with `live_state`; PropsSection orders LIVE → STILL TO COME → DONE; expired/settled props drop their open number | Kills #1588 **by construction**; THE DIVERGENCE becomes real; the anchor surface earns live nights | **Highest.** Ruling (d)(3) already puts this class first | Low. One endpoint + one component; 30s cache already right |
| **M3** | **In-card live prop on feed game cards** (S2) — poll precomputes `top_live_prop`; EventCard renders one probability-first line | The feed *feels* live without changing shape; reach for users who never open event pages | High | Low-medium. Redis key + card line; degrade path per #42 |
| **M4** | **Composition guard tests** — I1–I5 asserted in tests; I4 stays deliberately unruled (Alex 2026-08-11), so tests pin current marquee-always-top behavior without a ruling file | The rule survives every future live feature; two-direction tests end the #1091 class here | Medium (insurance) | Trivial. Tests only |
| **M5** | **Search live context** (S3) — live hit carries prob + period + top prop; concept-liveness question routed to the search lane | Instant Answers on live nights; "cena" answers mid-match | Medium-high | Medium. **Blocked on Queue 325**; shared-file coordination |
| **M6** | **The liveness ladder, rung 3 — sourceless events** (the Dexter gate): calendar window (+ PLE slate added to `majors_calendar.yaml`) + market-evidence liveness (price velocity / lock-settle transitions from the 2-min poll) + the card archetype adapter reading match(n) scopes | The catcher's-son test becomes passable; every clock-less domain (WWE, ceremonies, election nights) inherits it | High, and the differentiator — Kalshi shows a list; we show *the card, live* | **Highest risk.** A false LIVE badge is a class-5 trust failure: market-evidence alone gets "moving now" framing, never the pulsing LIVE badge — that requires calendar confirmation. 1–2 sessions |
| **M7** | **Live hygiene rail** — Flow Sentinel check (any scope-expired prop rendering an open number on a live surface = REAL defect), `live-props coverage@live` audit metric with our-bug vs upstream split | The regression never comes back; coverage gap becomes measurable (#1629's class gets a number) | Medium | Trivial as riders on M2/M3 (ruling 007 style), not a standalone queue |

**Parked, with reasons:** live push notifications (notifications v1 = morning digest, Alex's explicit pick); leverage/suspense scoring (no uncalibrated model gets a stage — Annex A); LLM anything in the live path (bounded async only); standalone prop cards (rejected outright, §4).

**Dependency note:** #1629 (Polymarket props never reach the typed bucket) starves M2/M3 of inventory on real nights — it is not part of this design but should ship in the same arc, or the live rail orders an empty list.

### 6.1 The smallest shippable slice — named

> **"The Prop Clock + event-page live mode" = M1 + M2, event page only.**
> Extract game progress from `_estimate_game_pace`; classify scope for the prop types the endpoint already serves; annotate `live_state`; reorder PropsSection; expired/settled props lose their open probability and gain a graded/ended label, mid-game.
> **Explicitly out:** feed, search, WWE, movement-sort polish (scope-ordering alone is the truth fix; divergence-sort can be v1.1).
> **Acceptance:** the #1588 fixture (first-inning prop, third inning) renders "ended/graded", never 52%; a segment prop is never in LIVE after its segment; healthy siblings survive a poison prop (#42); guard tests both directions.
> One queue session, visible on the next live Tier-1 night, closes a standing P1 that ruling (d)(3) already ordered to the front. Every later mechanism reads the state this slice creates.

---

## 7. Verification

Guard tests ride each slice (both directions, always). The Flow Sentinel gains one REAL-defect class: *scope-expired or settled prop surfaced with an open probability on a live page* — the #1588 class auto-files with evidence instead of waiting for Alex's eyeball (sentinels-over-eyeball, standing). The audit gains `live-props coverage@live` (of feed-surfaced live Tier-1 events, % showing ≥1 live prop; our-bug vs upstream-gap split per the hill-climb philosophy) and `expired-live rate` with a target of **zero, ever**. First measurement: next Tier-1 live night after the slice lands, browser-verified (Fable's Chrome, liberally).

---

## 8. Ruling-shaped calls — status after Alex's 2026-08-11 pass

1. **I4 precedence — DELIBERATELY UNRULED (Alex, 2026-08-11).** Guard tests assert the current behavior (live marquee concept keeps the very top; no EI override for games) so it cannot drift silently, but no ruling file is banked and the question stays open for a future batch.
2. **In-card prop density:** one line per game card vs. two when divergence is extreme — still open, and it is a layout call → decided on the visual mock (delivered in chat 2026-08-11), not in prose.
3. **PLE slate into `majors_calendar.yaml` — DECIDED (Alex, 2026-08-11): rides M6's queue** as its step 0. SummerSlam/Rumble/Survivor Series (+ recurring award shows) enter the calendar in the same change that builds the ladder, so the horizon sentinel starts warning T-30 with an adapter on the way.

## 9. Sequencing

Slice 1 (M1+M2) is independent and next-eligible — routed **issue-first** per Alex (2026-08-11): seed at `_ISSUE-LIVE-CONTEXT-SLICE-1.md`, filed under `program:events` through normal board triage. M3+M4 follow as one small queue. M5 waits on Queue 325. M6 is its own arc after the card adapter question is scoped (it is the P5 event-concepts program wearing a live jersey — coordinate, don't duplicate). Ruling 016's story-card arc is untouched by all of this: no new card types are introduced anywhere above.

*The blend is the product; live props show one number. Probability-first everywhere; no price formats anywhere. Settled means settled — now with the clock to prove it mid-game.*
