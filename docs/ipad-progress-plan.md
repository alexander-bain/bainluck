# iPad Progress Plan (No Terminal Required)

This plan is designed for sessions where you only have browser access (no local terminal), so you can still move OddsTracker forward.

## 1) Start with Product Direction (High Leverage)

### A. Tighten your "single sentence" value proposition
Use this draft and iterate until it feels perfect:

> OddsTracker helps casual fans understand how game expectations shift in real time, without needing to understand betting lines.

Why this matters: this sentence should appear consistently in your homepage hero, App Store copy (later), social bios, and launch posts.

### B. Define your top 3 user jobs-to-be-done
Write each in this format:
- **When** I am [context],
- **I want** [goal],
- **So I can** [outcome].

Suggested initial JTBDs:
1. During a live game, quickly understand whether momentum truly changed.
2. Before a game, compare expected outcomes in plain percentages.
3. After a game, evaluate how dramatic it was (Pulse/GEI) at a glance.

### C. Pick one North Star + 3 weekly leading indicators
North Star already exists in PRD spirit (time-to-understanding). Turn that into trackable proxies:
- Event page views per active user
- Median event page dwell time
- Return rate on live-game days

---

## 2) Improve UX and Messaging from Existing Screens

Open the live site and create a note with:
- 5 moments where the UI feels "obvious"
- 5 moments where meaning is ambiguous
- 3 copy changes that reduce confusion

Focus especially on these areas:
- **Event cards** (is status and probability source immediately clear?)
- **Pulse labels** (does score meaning feel intuitive?)
- **No-update states** (do users trust why updates paused?)

Deliverable: a short "UX punch list" doc with severity labels:
- P0 = trust-breaking
- P1 = confusing
- P2 = polish

---

## 3) Turn Existing Docs into a Weekly Execution Loop

You already have rich planning docs. Convert them into one active board with this structure:

- **Now (this week)**: max 3 items
- **Next (2–4 weeks)**: max 5 items
- **Later**: everything else

Good candidates for **Now**:
1. Route-level API contract tests for highest-traffic endpoints
2. Frontend API client tests (`lib/api.ts`)
3. Event detail clarity improvements (copy + source labeling)

Keep each item "definition-of-done" friendly:
- "Done = merged PR + production check + one screenshot + one metric to watch"

---

## 4) Growth Work You Can Do Fully from iPad

### A. Set up a lightweight launch cadence
- 2 short weekly posts: one feature highlight, one live-game insight
- 1 weekly retrospective post: "What changed this week"

### B. Build a reusable content template
For each post:
1. Hook (what happened in a game)
2. Visual/screenshot
3. Insight (probability shift or Pulse explanation)
4. CTA ("Try this matchup live")

### C. Create a simple feedback pipeline
Use one form/question in your site or posts:
- "What was confusing on first use?"

Then bucket answers into:
- comprehension
- trust
- speed
- delight

---

## 5) Engineering Priorities for Your Next Coding Session

Based on current project docs and test coverage notes, the highest ROI coding tasks are:

1. **Add frontend API client tests** for auth header/error handling
2. **Add route-level tests** for `events` helper/contract behavior
3. **Add targeted component tests** (`EventCard`, `PulseBadge`, `ProbabilityBar`)
4. **Ship one UX trust fix** around probability source labeling/status clarity

This sequence improves reliability first, then user comprehension.

---

## 6) 45-Minute "No-Terminal" Sprint Template

When you only have a short iPad block, run this:

1. **10 min:** Review one core flow on production (home → sport → event)
2. **10 min:** Capture friction points as P0/P1/P2
3. **15 min:** Convert top 1 issue into a GitHub issue with acceptance criteria
4. **10 min:** Draft user-facing copy improvement for that issue

If you do this 3x/week, you’ll build a high-quality backlog without writing code.

---

## 7) Ready-to-Use Backlog Items (Copy/Paste)

### Item 1: Clarify probability source on event views
**Problem:** Users may not understand whether value shown is live consensus vs opening odds.

**Acceptance criteria:**
- Explicit label adjacent to displayed probability source
- Tooltip explaining source switching by game status
- Copy reviewed for non-bettor comprehension

### Item 2: Improve paused-update trust messaging
**Problem:** When updates pause, users may think the app is stale.

**Acceptance criteria:**
- Distinct paused reason labels (blowout, market halt, idle movement)
- "Last updated" timestamp always visible
- UX copy tested against 3 real-game scenarios

### Item 3: Pulse score interpretation aid
**Problem:** Users see score but may not map it to drama level quickly.

**Acceptance criteria:**
- Pulse bands with labels (e.g., Calm / Competitive / Chaos)
- One-line explanation near score or tooltip
- Consistent wording on cards and detail pages

---

## 8) Weekly Review Questions

At end of each week, answer:
1. What made the product easier to understand in under 10 seconds?
2. What improved user trust in live data accuracy?
3. What shipped that reduces future engineering risk?

If a task doesn’t help one of those three, de-prioritize it.
