# Bain Luck — Product Requirements Document

*Last full revision: 2026-07-14 (Fable + Alex). Prior revision: 2026-05-15. This document is the product's voice; `docs/execution-plan-2026-07-13.md` is the current operating plan; `docs/backlog.md` is the work ledger.*

## 1. Vision & North Star

Bain Luck is a prediction market discovery platform that translates betting odds and prediction market prices into intuitive probabilities. Instead of "-150 / +130" or "0.60 CLOB price," users see "60% vs 40%." The product aggregates sportsbooks, prediction markets (Kalshi, Polymarket), and models (ESPN, stat models, MLB Stats API, DataGolf) into **one blended probability** for any event — across sports, politics, economics, entertainment, weather, technology, geopolitics, and culture.

**North Star:** The most engaging way to explore what the world thinks will happen.

The success moment is immediate: a user sees a card and thinks, "Oh, I had no idea — that's only 23% likely?" The mental model is **probability discovery**, not gambling.

**The blend is the product.** Users see one clean number per question, not a source comparison. When sources diverge, that is almost always a data-quality bug for us to fix upstream, not a feature to display. (Deliberate exceptions where comparison IS the content: category-page cross-source spotlights, playoffs source lines, My Stuff per-source dots.)

**The anti-thesis:** the incumbent way to see "what does the world think?" is a betting app that answers the question while bombarding you with enticements to gamble. Bain Luck is the clean room: the same knowledge, zero enticement. No odds formats anywhere, ever.

**Live site:** https://bainluck.com | **Sports:** /sports | **Calibration:** /calibration

---

## 2. The Reliability Bar (definition of success)

The product's owner-ratified quality bar (2026-07-13): **"fast and natural to use" means the app does what it's supposed to do.** The six failure classes that break trust, in the owner's words — the event you search for doesn't show up; it shows up twice because sources haven't merged; the adjacent markets/futures don't appear on the event page or aren't legible; content that has resolved still shows as live; or the interface is simply worse than a betting app's — so the user gives up and opens Kalshi.

**Measured success:**
- **Flow Sentinel green** — a nightly scripted sentinel runs real user flows (search → event → props → state correctness → chart density → feed quality) against production and files evidence-packed issues when they fail. A healthy night files nothing.
- **The Kalshi-free fortnight** — the owner logs 14 straight days of daily phone use in which Bain Luck answered every question he had and he never opened Kalshi.
- **No embarrassing charts** — every chart a user can open renders ≥1 point per open hour (provider-candle granularity via candlestick/CLOB backfills). Live game charts are dense by construction (32s polling).
- **Settled means settled** — one system-wide settled language: heroes show winners (not stale percentages), cards show results (not live-style chips), props show *the script, graded* (hit/miss, never 100% bars), charts show the completed journey.

---

## 3. Target Users

**Primary:** curious people who follow sports, politics, or current events casually and enjoy probability as lightweight entertainment. They want "73% chance" without understanding American odds or order books.

**What they want:** quick visual answers to "how likely is X?"; surprising discoveries; a fun way to test intuition; one trustworthy number (not homework across sources); something to say out loud to the room ("there's a 12% chance of extra innings").

**What they do NOT want:** betting advice or picks; volume/liquidity/order-book plumbing; dense pro-bettor interfaces; forced sign-up; gambling enticements of any kind.

**Auth philosophy:** no required sign-in. The logged-out experience must feel complete. Auth unlocks sync, history, and personalization — pull-based, never forced.

---

## 4. User Journeys

### First visit: Discover browser
Opens bainluck.com. Scrolls Discover. Sees "Will the Fed cut rates in September? — 62%." Plays Higher/Lower, hits a streak. Taps into a market, sees one blended probability and a movement explanation. Shares a card.

### The pre-game ritual (the props thesis)
Before a game he's watching, a fan opens the event page **for the props**. Pregame, the prop set is **the script**: what the world expects tonight — the pitcher's strikeout line, the total, the stars' props, what the game means for the playoff race, plus a fun prop worth saying out loud. During the game, prop **movement vs. the script** tells him how tonight is *different* from expectations — the win probability says who's winning; the props say *what kind of game this is*. After, the script is graded: what hit. This journey is the product's secret sauce and its formatting must be perfect on a phone.

### Instant answers
A user hears a name — a team, a golfer, a bill, a nominee — and types it into search. The right event or market is the first result, as one merged entity (never duplicates), faster than any betting app. Search is the front door to everything.

### Live second screen
During a tournament or game night, the event/concept page is the second screen: live blended win probability, a fused leaderboard (golf), bout cards (fight night), all state-correct to the minute, with a freshness signal.

### Daily return: the digest
One morning notification: the 3–5 most interesting probabilities today, personalized. (Notifications v1 is the digest ONLY — no movers spam, no streak nags.)

### Compete with friends
Challenge links, head-to-head accuracy, shared cards — social as a garnish on discovery, not a network.

---

## 5. Feature Map

### Discover Feed (`/`, default)
Ranked stream of the most interesting predictions right now. Higher/Lower game, daily challenges, streaks. LLM hooks (bounded, async) + deterministic explanations (first-page comprehension never depends on the LLM). Market-quality classifier suppresses filler and ladders; diversity caps prevent single-topic floods (scoped by card type — game events are never capped into an empty tab). Bounded personalization; soft dismiss propagation; graceful end-of-feed state. Interestingness scoring blended at capped weight.

### Search / Instant Answers
Full-text-ranked search across events, concepts, futures, and teams. The bar: the right entity, merged, first, fast. Gold-set regression protected by the Flow Sentinel.

### Sports Feed (`/sports`) & Event Pages
Live/upcoming/completed games. Event pages: blended win-probability hero + multi-source chart (prominent blend, faint sources, fixed 0–100 axis, **no smoothing — movement is the product**), market map, player props, related futures, series context, championship path. The props program (script/divergence/graded — §4) is the active build here.

### Event Concepts & Hubs
Tournament/card/ceremony pages that unify many markets into one surface: golf majors with fused live leaderboards, UFC/boxing fight cards, awards shows, elections. Slug URLs (`/event/<headliner-and-date>`), hub pages per domain, up-link mesh from every market to its concept. Powered by the entity registry + one matching engine (adapters supply grammar; the audit owns truth; the sentinel files gaps).

### Category Pages
Politics, Entertainment, Economics, Weather (+ Preferences): themed dashboards with cross-source spotlights (a deliberate comparison surface), threshold-group heatmaps, TMDB/poster enrichment.

### My Stuff
Pins, follows, prediction stats, Your Teams' Odds (one card per team, seasons labeled). Settled events render settled.

### Calibration Report (`/calibration`)
The public trust engine: honest reliability curves across 1M+ priced resolved outcomes, per-source and per-category, with per-bucket sample counts, confidence intervals, small-bucket suppression, click-through example outcomes per bucket, a corrections log, and a well-traded default with a skeptic's toggle. Categories with known capture artifacts are excluded with on-page explanations rather than silently blended. (July 2026: headline honest MCE ≈ 1.6pp; kalshi source ECE ≈ 1.0pp; weather healed 7.0 → 1.7pp by fixing OUR capture, which is the house methodology: assume our bug, never "the market was wrong.")

### Games & Social
Higher/Lower, daily challenges, friend challenges, prediction stats.

### Platforms (P7 posture)
- **iPhone app** — the primary consumption target; App Store re-submission gated on the owner's dogfood + calibration credibility.
- **Web** — full experience + the debugging/admin surface.
- **Apple Watch** — exists today; top-priority secondary surface: glanceable followed teams/events + a 3-card "cocktail banter" mini-Discover fed by the digest's selection pipeline. Complication ships when the widget target is wired.
- **iPad / macOS** — near-term parity that never feels second-class (shared SwiftUI codebase; payload-v2 keeps display semantics server-side so all platforms heal together); each gets a truly-great pass post-iPhone-bar (iPad: multi-column second screen; Mac: menu-bar glance + keyboard-first search).
- **Morning digest** — email today; push v1 = the same brief, opt-in.

### Admin (the operator's cockpit)
`/admin` opens with health tiles (green/amber/red with tracked-issue badges), a "Waiting on you" queue of genuinely-human asks, an inline eval/grading queue (Rapid mode: 25 keystrokes per 25-item gold-set batch, with undo), autopilot beat tiles, and deep pages behind each tile. The operator's judgment is spent on ship gates and taste calls — detection belongs to sentinels.

---

## 6. Data Architecture (summary; detail in `docs/architecture-reference.md`)

Sources: The Odds API (~$119/mo), Kalshi, Polymarket, ESPN, StatPal (~$99/mo), DataGolf (~$30/mo), MLB Stats API, TMDB, Pexels, OpenAI (~$10/mo), Wikipedia (person images).

Core subsystems: **Event Registry** (find-or-create cascade with structured matching incl. completed events; invariant-guarded against cross-merges); **Entity Registry + one matching engine** (canonical entities/aliases; source adapters supply grammar; shadow-mode cutovers earn production per link type); **Probability Aggregation** (weighted blend; source-agnostic resilience); **Market Grouping** (`group_id` powers dedup, cross-source, calibration); **Feed Ranking** (candidate pools + quality classifier + caps + bounded personalization + replay harness); **Quota Guard** (three-mode circuit breaker); **Backfill Autopilot** (dedicated beat-scheduled pricing/resolution tasks, budget-guarded, idempotent, with `backfill-progress` observability: per-month density, the June-gap ledger, recoverable-vs-excluded denominators).

Quality machinery: four-layer matching audit (L1 existence, L2 market→event, L3 futures surfacing, L4 completeness — target 100%); grid accuracy; feed-quality audit (boring-rate@20 = 0, explanation-coverage 20/20); **Flow Sentinel** (nightly user-flow regression w/ auto-filed evidence packs); **Calibration Sentinel** (cohort mining → auto-filed issues); the dogfood loop (owner phone sessions → evidence-packed P0s, often same-day fixed).

---

## 7. Metrics

**North Star:** daily active users engaging with predictions (a guess, a detail-page open, or a challenge completion).

**Engagement:** guesses/session (3+), challenge completion, streak retention, card CTR, share rate, weekly return, digest open rate (when push ships).

**Reliability & data quality (July 2026 values):**
- Flow Sentinel: green nights (target: file-nothing ≥ 6/7)
- Matching: L1–L4 at 100% on audit; duplicate events: 0 (sentinel-guarded)
- Calibration: honest MCE ≈ 1.6pp; every source ≤ ~2.6pp; corrections logged publicly
- Backfill SLA: ≥95% of post-Jul-2 resolved outcomes priced, vs the *recoverable* denominator; per-source density (≥15 pts poly/DataGolf; cadence-honest bar for Kalshi)
- No-embarrassing-charts: % of user-visible charts ≥1 pt/open-hour (candlestick scoreboard)
- The Kalshi-free fortnight: 0/14 days logged (starts when the phone build stabilizes)

---

## 8. Product Principles

1. **Probability-first, visual-first** — percentages and charts, never odds formats.
2. **The blend is the product** — one number per question; divergence is our bug to fix, not the user's puzzle to solve.
3. **Movement is the product** — no chart smoothing, ever; fixed 0–100 axis; a jagged line that's true beats a smooth one that lies. Movement explanations ship only when the *cause* is explainable.
4. **Discovery-first** — surface what users didn't know to look for.
5. **No gambling language, no enticements** — no volume, no liquidity, no "best bets." Ever.
6. **Settled means settled** — resolved things look resolved everywhere, immediately.
7. **Assume our bug** — a miscalibrated curve or diverging source is our capture/linkage/grading error until exhaustively proven otherwise.
8. **Detection by machines, judgment by humans** — sentinels find and file; the owner's eyeball is the ship gate, never the smoke detector.
9. **Transparency builds the brand** — public calibration, public corrections, source attribution.
10. **Respect attention** — one good notification a day beats ten mediocre ones; no forced auth.

---

## 9. Non-Goals

Bain Luck is **NOT**: a sportsbook or betting interface; a trading platform; a pick-selling service; a stats terminal for professionals; a social network. It displays information, never transactions. Betting markets are an *input* for computing probabilities — never a call to action.

---

## 10. Tech Stack

| Component | Technology | Hosting |
|-----------|------------|---------|
| Backend API | FastAPI (Python 3.11+), 7,000+ tests | Heroku |
| Database | PostgreSQL | Heroku Postgres |
| Task Queue | Celery + Redis (realtime + background workers) | Heroku Redis |
| Web | Next.js 14 | Vercel |
| iOS / iPadOS / macOS / watchOS | SwiftUI shared codebase (~142 Swift files incl. watch + widget targets) | TestFlight / direct |
| Auth | Firebase Auth (Google + Apple) | Google Cloud |
| Analytics / Errors | GA4 + Firebase / Sentry | — |
| LLM | GPT-4o-mini (bounded enrichment + advisory evals) | OpenAI |

CI on every push: backend pytest + frontend build (ESLint gate), serialized Heroku deploy. Ops runs on a three-lane queue protocol with atomic claims, drive-mode, and headless cranks (`.claude/handoff/README.md`).

---

## 11. Reference Docs

| Document | Purpose |
|----------|---------|
| `docs/execution-plan-2026-07-13.md` | Current operating plan, programs P1–P7, Opus handoff |
| `docs/architecture-reference.md` | System design detail |
| `docs/backlog.md` | Strategic work ledger |
| `docs/feature-reference.md` / `completed-features.md` | Feature detail / shipped log |
| `docs/gotchas-reference.md` | The full hard-won gotcha catalog |
| `docs/design-system.md` | Visual language incl. the settled-state system |
| `docs/hill-climb-guide.md` / `quality-audit.md` | Measurement playbooks |
| `docs/strategy-instant-answers.md` | The search program |
