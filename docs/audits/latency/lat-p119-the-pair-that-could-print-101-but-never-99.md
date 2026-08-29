# LAT-P119 — the pair that could print 101 and never 99

**Cycle 91 · 2026-08-29 · `program/latency-104` · branch base `c47b25a5` (CURRENT master)**
**Pillar: FORMATTING. Ship: the event page's hero stops printing 101%.**
Issue **#2085** (p3, `area:event-details`, routed to this lane by the standing
`routes/events.py` ownership ruling, #1494).

---

## The ship, in user terms

Open an event page on a game where the blend lands on a half-percent and the hero
read **68% – 33%**. Now it reads 68% – 32%. Same on the "Opened 50 – 51" line
under it, and the same on iOS. Measured on the feed's own population 2026-08-21:
**34 of 414 (8.2%)** scheduled/live events. It could print 101; it could never
print 99 — only an exact `.5` fractional part misfires, and it rounds **both**
sides up.

---

## 🔴 The issue prescribed a fix that is already on master and does not reach the defect

#2085 names two derive sites in `routes/events.py` and prescribes serving
`{home,away}_rendered_percent` beside them. **Both are already shipped**
(`routes/events.py:6324` and `:6399` on `c47b25a5`), and the issue's claim that
"web and native already prefer a served `*_rendered_percent` on the feed path"
is true for `FeedCard` / `discover/EventCard` and **false for this page in both
clients** — before this branch, `rendered_percent` appeared nowhere in
`app/events/[id]/page.tsx` and nowhere in `EventDetailView.swift`.

That would have been an easy cycle to spend re-shipping. What the issue does not
say is that **the web hero does not read `current_odds` on the paths that
matter.** `resolveProbability` chooses from four sources:

| branch | pair | derived how | served percents? |
|---|---|---|---|
| settled | `opening_odds` | `opening_away_probability or round(1 - home, 4)` (`:6495`) | **no** |
| live, blend present | `hero_probability` / `hero_probability_away` | `round(1 - agg, 6)` (`:6425`, and again at `:11283` in a second route) | **no** |
| live, no blend | `current_odds` | `round(1 - home, 6)` | yes |
| live, history override | `history[i]` | `away ?? 1 - home` | **no** |
| scheduled | `current_odds` | `round(1 - home, 6)` | yes |

So there are **four derive sites, not two**, the issue names the two that were
already fixed, and three of the five hero branches carry no served pair at all.
A backend-only reading of #2085 closes nothing a user can see.

## 🔴 And the obvious client fix — copy `FeedCard`'s one-liner — is wrong here

`FeedCard.tsx:313` reads `data.current_odds?.away_rendered_percent ??
fallbackAwayPct` unconditionally, and its comment says why that is safe **there**:
the feed card only ever renders a pair when that pair *is* `current_odds`. Pasted
onto this page it prints `current_odds`' rounding beside the **blend's**
probability on every live game — a mismatched pair, `data-probability`
contradicting the number beside it, on the surface the "blend is the product"
ruling exists to protect. It **still sums to 100**, so it would have passed any
sum-only guard and shipped as a win.

The fix therefore decides the pair inside `resolveProbability`, at the one place
that knows which source it chose, and records that at the branch
(`fromCurrentOdds`) rather than inferring it from the values afterwards. Two
branches clear the flag explicitly — the history override (which only fires past
a **5-point** gap, so a stale served pair would be wrong by at least five) and
the chart-point fallback.

**Both served values or neither.** One served value beside a locally derived one
re-opens the same 101 from the other direction, and a partially rolled-out deploy
can carry one field and not the other.

## Why the hero pair became a component

The defect is a *rendering* one, and this fix's failure mode is being **present
and inert**: the percents computed correctly and then not printed. A guard that
only drives `resolveProbability` stays green while the JSX keeps its own
`Math.round(homeProb * 100)`. `EventHeroProbabilityPair` exists so the thing
under test is the thing on screen, and it **refuses to re-round** — a missing
percent prints an em-dash — so the fix cannot be quietly undone by a caller.

---

## Gates

| gate | result |
|---|---|
| frontend jest (CI deploy gate) | **3,607 passed / 4 skipped / 3,611 total, 227 suites — EXIT 0 READ BY VALUE** |
| baseline (same tree, two new files excluded) | 3,555 passed / 3,559 total, 225 suites |
| delta | **+52, enumerated AND measured** — `eventHeroDuelInvariant` 46 + `eventDetailHeroDuel` 6 = 52 = 3,607 − 3,555, exact |
| `npm run build` (ESLint gate) | **EXIT 0** |
| `npm run typecheck` (TS ratchet, a real deploy gate) | **EXIT 0** — 70 errors, baseline 70, real count matches |
| mutation battery | **10/10 killed, 0 survived, 0 not-applied — EXIT 0** |
| residue scan (on a COMMIT, per P117-5) | **CLEAN EXIT 0** — 165 needles / 20 targets, **888 broad checks** |
| ruff | both changed `.py` files clean; master's copy of `scan_mutation_residue.py` also clean — the new file adds **zero** findings |
| `npm run contract` (**a CI gate**, `ci.yml:531`) | **484 pass / 0 fail, EXIT 0** — and 484/0/exit 0 on **master** too, so the count is unchanged rather than merely green |
| backend, scoped | `test_mutation_guard.py` + `test_startup.py` — **13 passed, EXIT 0**, including `test_every_on_disk_harness_is_guarded` |
| backend, full | **21,211 passed / 0 failed / 124 skipped / 61 xfailed, 851.68 s — EXIT CODE 0 READ BY VALUE**; 21,211 + 124 + 61 = **21,396 = collect, exactly**, and **21,396 is master's own collect**, so **+0** — which is right: this branch adds no backend test file |

`migration_slot: none` — no DDL, no index, no schema change.
`beat_schedule_change: FALSE` — no beat file, no Celery task, no config var.
**No backend `app/` code at all**: the two Python files are both under
`backend/scripts/evals/`.

### 🔴 M7 survived the first battery and it was a real hole in the test

"the served pair IS used when the hero really is `current_odds`" served **32/68**
for `0.325 / 0.675` — *exactly what the local rule derives* — so it passed whether
the client honoured the payload or ignored it entirely. The mutation that deletes
`fromCurrentOdds = true` from the scheduled branch walked straight through it.
Repaired by fixing the assertion, not the mutant: the served pair is now **30/70**,
a value only a read of the payload can produce, asserted beside the locally derived
32/68 that it must not be. Same species as LAT-P116's M3 — *a pin computed from
the thing it pins is not a pin*.

### 🔴 The component extraction redded a CI gate that no rendering test can see

`npm run contract` (**`ci.yml:531`** — a real CI gate) reads
`app/events/[id]/page.tsx` as **TEXT** and asserts it contains
`data-testid="event-hero-probability"`. UX-P043 / #1649 wrote that block because
the browser pack's first-ever dispatch failed 4/4 on a hero that was working
exactly as designed, and deleting the hook silently re-reds the pack against a
healthy page.

Extracting the hero pair moved that string one file away. **1 failing of 484** —
while `jest` (3,607 passing), `npm run build` and `npm run typecheck` all stayed
green, because **none of them reads source as source.** It was found by grepping
for consumers of the testid, not by any suite this lane runs by reflex.

The repair follows the hook rather than reverting the extraction — the hook still
ships to the browser, which is what the pack actually needs — and pins it in
**both** directions, because the extraction created two ways to lose it: the
component can drop the hook, or the page can stop rendering the component. It also
pins `data-probability` to the **probability**, since the rail compares it against
the Discover card that links here (UX-P003) and the one thing this cycle changed is
what the hero *prints*.

**Offered as a gotcha:** *extracting a component can red a SOURCE-READING contract.*
Three gates pass a file that has been emptied of the string a fourth gate greps it
for. The class is wider than this instance — `sectionErrorBoundary.test.tsx` and
`__tests__/ios/*` read source the same way.

### 🔴 The residue scanner was sweeping a scope that could not contain these mutants

`scan_mutation_residue.py`'s Pass B was hardcoded to `*.py`. That was the whole
truth for eleven harnesses; this is the twelfth and its targets are `.ts`, `.tsx`
and `.swift`. **Pass A** was always file-type agnostic — it reads each declared
target directly — so the load-bearing half was never at risk. **Pass B** would
have printed its usual clean line over **zero eligible files**: the
silent-narrowing failure the scanner's own docstring refuses. The globs are now
derived from the declared targets, so the next harness in a new language widens
the sweep by existing rather than by somebody remembering, and the printed scope
names what it swept (`changed .json .py .swift .ts .tsx vs origin/master`).

**Offered as a gotcha:** *a guard's SCOPE ages differently from its LOGIC. Pass A
and Pass B were written together, are printed together, and one of them silently
stopped covering the tree while the other kept working — so the composite line
stayed green and stayed wrong.*

### Inherited, not mine

`typeahead_warmer_mutations` M4 and M6 still report **DRIFT** in Pass A — LAT-P117
parked this as **P117-6**, and it reproduces here unchanged.

---

## What was measured and NOT shipped

1. **The three unfixed backend derive sites.** `hero_probability_away`
   (`routes/events.py:6425` and `:11283`) and `opening_odds.away_probability`
   (`:6495`) still ship no rendered percents. The clients now decide those pairs
   locally through the shared contract helper, which is the contract's own
   prescribed fallback and produces byte-identical answers in all three runtimes
   — so the user-visible defect is closed either way. Serving them would make the
   server authoritative for all five branches. **NOT taken here because
   `routes/events.py` already has THREE unmerged branches against it** (`-101`,
   `-102`, `-103`); a fourth would take the ordering discharge from six
   permutations to twenty-four for a change with no user-visible delta.
   **Parked P119-1**, and it should ride the cycle after the stack drains.
2. **`DiscoverEventCard.swift`, `MenuBarView.swift` and `RelatedByTagView.swift`
   coalesce the served percents PER SIDE** (`?? duelFallback[0]`), which is the
   single-sided hazard M2/M9 exist to catch, on a payload that carries one field
   and not the other. Not this lane's files and not this page; the iOS guard here
   asserts the both-or-neither form specifically so the per-side pattern is not
   copied *into* this view later. **Parked P119-2**, filed.
3. **P118-1, the queue head, is BLOCKED and was not started.** It is the `origin`
   column on `search_query_logs` — pure DDL, and **ruling 080 says a lane requests
   a slot and does not take one**. It is *also* blocked on `-103` merging, since
   the header whose value the column would record ships there. Slot **REQUESTED**,
   not assumed; see `YOUR-TURN.md`.

---

---

## 🔴 The needle: THREE readings, 23 minutes, ONE unchanged slug, a 65x spread

| run | at (UTC) | cold members | surfaces | equal-weighted | raw pool | verdict |
|---|---|---|---|---|---|---|
| open | 07:27:39 | 2/7 | 2/3 | (156.5) | 237.0 ms / n=11 | **REFUSED** |
| close | 07:47:51 | 1/7 | 1/3 | (23.0) | 23.0 ms / n=5 | **REFUSED** |
| close-r2 | **07:50:39** | **4/7** | **3/3** | **1,508.0 ms** | **21.0 ms / n=9** | ✅ **PUBLISHED, exit 0** |

Slug `c47b25a5` throughout, `uptime` 5,559 → 6,953 s (no restart), this branch
unmerged and undeployed. **Nothing under measurement changed.**

**The published 1,508 ms is 75x LAT-P118's 20 ms and the entire move is
composition.** `discover_web` (**one** cold sample, **3,556 ms**) and `sports_web`
(**one** cold sample, **2,138 ms**) entered the median for the first time in four
cycles; in LAT-P116/117/118 those paths went 0/5 cold and were *absent from the
median rather than counted slow*, exactly as the harness's own docstring says. The
median of (14, 878, 2138, 3556) is 1,508.

🔴 **AND THE TWO STATISTICS DIVERGED 72x INSIDE ONE RUN.** The docstring says *"if
the two diverge between runs, the move is which surfaces missed, not speed."* Here
the demoted raw pool reads **21.0 ms** while the published headline reads
**1,508 ms** — in the *same* reading. Equal weighting gives a path that missed
**once** the same vote as a path that missed **five** times, so when the
once-missing members are the slow ones, a single sample sets the headline. That is
the mirror image of the composition problem option b was ruled in to fix, and it is
not a thing this lane can fix by editing the harness (ruling 127).

**What this means for the series, stated plainly:** the 19 / 20 / 21 ms readings of
the last three cycles were medians over pools in which *Discover open contributed
nothing*. They were not wrong, and they were not measuring what the line says they
measure. The instrument's variance across 23 minutes on one slug **exceeds every
delta the series has ever reported.**

⚠️ Directive still names **option b**; the tree's harness is **option c**
(ruling 127). **FIFTH** consecutive cycle to flag it — P116-6 → P117 → P118-5 →
P119. This is no longer a formatting quibble about which statistic is named: the
statistic in the tree can move 75x on an unchanged slug.

⚠️ **Contamination declared.** Three needle runs = **18 `search_query_logs` rows**
written by this lane's own harness (#1916). #1916's suppression channel, which is
the fix for exactly this, is unmerged on `-103` — so this cycle could declare only
what the CLIENT sent, and it sent nothing, because the header does not exist on the
deployed slug.

---

## Parked

- **P119-1** — serve rendered percents beside `hero_probability_away` and
  `opening_odds`; wants the `events.py` stack to drain first.
- **P119-2** — the three iOS surfaces that coalesce served percents per side
  (**#2279**, filed).
- **P119-3** — the residue scanner's Pass A/Pass B scope asymmetry, generalised:
  offered as a gotcha above rather than merely parked.
- **P119-4** — 🔴 **`discover_web` returned a 3,556 ms cold sample and `sports_web`
  a 2,138 ms one.** ONE sample each, so this is a *lead*, not a finding — but they
  are the largest cold feed numbers this lane has recorded and they arrived on a
  slug that has been up for two hours. A measurement-lane ask, not a build:
  re-sample the four graded feed shapes cold, with enough repeats to have a p50
  rather than a point, before anybody codes against it.
- **P119-5** — the equal-weighting-vs-cold-share interaction above. Needs a ruling
  with P116-6, not another park.

Inherited and still open: **P116-1…P116-6**, **P117-1…P117-6**, **P118-1…P118-5**.
**Five indexes and one column are now parked behind a migration slot** — that,
and not any single missing fix, is what the cold-path needle is waiting on.

---

## Rulings / gotchas

**Rulings banked: NONE** (next free **138**). **Gotchas banked: NONE**, **two offered** — the
guard-scope asymmetry, and the source-reading contract a component extraction reds.
