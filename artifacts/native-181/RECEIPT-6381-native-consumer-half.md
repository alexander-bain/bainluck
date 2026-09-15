# native/181 — #6381's native consumer half: the phone stops presenting a venue-graded match as an upcoming fixture

**Pillar TRUTH.** Ship: *a match the venue has already graded stops appearing on the phone as a
fixture that has not been played.* Product check 1 / 6 (games show the correct state; cards, pages
and charts tell a consistent story), milestone 3 (the phone experience) — the surface Alex walks in
checklist item 6, "open a recent result for your team".

Written 2026-09-15 13:2x PT (stamped from `TZ=America/Los_Angeles date`), native lane,
worktree `/Users/bain/bainluck-dev/native`, branch `native/181-6381-native-consumer-half`.

---

## 1. What a reader saw, and it is not the sentence the issue is named after

`bainluck://events/15310639` — **Liverpool FC v Fulham FC**, EPL, `tier: 1`. The venue graded
`Correct Score · Draw 0-0`, `resolution_source='api_settlement'`, on 2026-09-12.
`GET /api/events/15310639` serves `status: scheduled`, both scores `null`, no `current_odds`.

iPhone 17 Pro, built from `066ceb1fb`, shot 12:25 PT —
`artifacts/native-181/before-01-liverpool-fulham-hero.png`:

| slot | drew | true |
|---|---|---|
| badge | **nothing** (`formatCountdown` is nil for a past date, so `StatusBadge`'s scheduled arm is `EmptyView`) | the venue settled it 3.6 days earlier |
| centre | **vs** | `Draw 0-0` |
| meta | `Sep 11 at 5:00 PM` | a kick-off long gone |
| chart | `No win probability readings for this game **yet**.` | there will never be more |
| market list, one scroll down | `Correct Score · Draw 0-0 · 100%` | the grade the hero was denying |

🔴 **The phone does not print "No result reported" on this row, and that mattered for where the fix
goes.** That sentence is `EventState.suspendedLabel`, gated on `status == "suspended"`. This row is
`scheduled`, so it fell through to the pregame default and the page read as an ordinary upcoming
game. The arm that *does* print the issue's sentence is the **bigger** one — live/299 measured
**suspended 889** against the issue's own scheduled **426**, plus 8 unbacked-`live`; **1,471
events all-time, 68 of them with a score string.** One predicate, consumed by both arms, or the fix
lands on a third of its class.

🔵 **One thing native does NOT share, measured rather than assumed.**
`EventDetailView.showsRefreshCountdown(status:)` is `status == "live"` and nothing else, so no
`Next update:` ring has ever drawn over these rows on the phone. ux's countdown half (#6407) has no
native twin to build, and I said so on the issue rather than building one.

## 2. What it says now

`artifacts/native-181/after-01-liverpool-fulham-draw00.png` (13:13 PT, shipped tree):
badge **`✓ Result settled`**, centre **`Draw 0-0`**, chart line **`No win probability readings for
this game.`** — the "yet" gone for the same reason #3859 dropped it on a Final.

| frame | event | state | what it proves |
|---|---|---|---|
| `after-01-liverpool-fulham-draw00.png` | `15310639` | settled, score named | soccer's `Draw 0-0`, verbatim |
| `after-02-sabalenka-no-score.png` | `15304840` | settled, **no score** | 370 of 426 rows are graded on props alone: the word alone, no invented score |
| `after-04-brighton-long-string-bounded.png` | `15310517` | settled, long string | `Brighton & Hove Albion wins 5-0` wrapped inside the hero |
| `control-01-completed-final.png` | `15311023` | `completed` | `FINAL`, `Sion Win`, 5–2 — untouched, no second settled voice |
| `control-02-upcoming-fixture.png` | `15313111` | genuinely upcoming | `In 12h 2m`, `59% – 41%` — untouched |

Both controls are the direction that would have been expensive to get wrong: this ship must not
turn a Final into a second chip, and must not turn a real fixture into a result.

## 3. The defect my own after-shot found

🔴 **The first draft pushed the hero card off both screen edges.** On `15310517` the verdict is 31
characters; the hero's centre column is its **inflexible middle** (the two crest columns are the
`.frame(maxWidth: .infinity)` siblings), so it was granted its ideal width and the row grew past the
screen — away crest clipped left, `COV` clipped right, the date cut off.

**`.frame(maxWidth: .infinity)` did NOT fix it** — observed on the simulator at 12:59 PT with that
modifier and `lineLimit(3)` in place, one line, same overflow. An infinite maximum asks the row for
MORE width, never less. The fix is a finite cap (`EventDetailView.verdictSlotWidth = 150`) plus
`layoutPriority(-1)`, and the guard asserts the cap is **finite** precisely so a later tidy-up that
"makes it consistent with its siblings" cannot reintroduce it. The intermediate overflow frame is
kept as `during-03-brighton-overflow-first-draft.png` (that one is from the pre-cap build; the
`.infinity` frame between them was overwritten by the next shot and is recorded here, not filed).

## 4. Two instrument findings, recorded so nobody re-pays

1. ⚠️ **`tools/native-walk.sh` does not install the app.** It terminates and launches. So a tree you
   have just rebuilt is photographed only if something else installed it — and **two of my shots
   were of the previous binary while looking entirely plausible**, including one I first read as
   "the width fix did not work". `tools/native-shoot.sh` refuses a stale binary (it did so for
   native/178 the same day); `native-walk.sh` has no such check. Working route:
   `xcrun simctl install <dev> <BUILT_PRODUCTS_DIR>/Bain\ Luck.app` after every build, and read the
   installed binary's mtime. Not fixed here — tooling, off this ship's path, one owner per fix.
2. ⚠️ **A build that fails still installs the last good product if you sequence with `;`.** One
   cycle compiled `error: result builder attribute 'ViewBuilder' can only be applied to a property
   if it defines a getter` (I had inserted a `static let` between `@ViewBuilder` and its function),
   printed `BUILD EXIT: 65`, and the shot that followed was of the stale app. Gotcha #54 in its
   smallest form: **65 is a result, and the step after it has to be gated on the value.**

## 5. A clock leak in my own test, caught by the mutation baseline

The mutation run's BASELINE came back **19 tests, 1 failure** — before any mutant. The failing case
was `testTheYetSurvivesWhereItIsStillTrue`: `OddsChartView.noReadingsLine` took no `now`, so a test
built on fixed anchors (gotcha #44) was silently asking the REAL clock, and the anchor's "future"
date is in the past today. The fix is in the function, not the test: `now: Date = Date()` is
injected, the view keeps the default, and the case is deterministic. A mutation baseline is how that
was found — running mutants without first reading the baseline would have scored it as a kill.

## 6. Gates

| gate | result |
|---|---|
| macOS build (`native-gates.sh`) | PASS |
| `BainLuckTests` | `Executed 2417 tests, with 0 failures (0 unexpected)` |
| recompile proof | all 6 changed Swift files compiled by the gated build |
| `frontend/__tests__/ios/eventStatusSingleSource` | 40 passed / 0 failed |
| `npm run build` (ESLint gate) | exit 0 |
| `npm run typecheck` (TS gate) | exit 0 — 70 errors, baseline 70 |

**Mutation — 6 planted, 6 killed.** Four source-scan mutants (CI compiles no Swift, so the wiring is
only provable by reading the source): badge arm moved below the suspended arm → red; the page stops
handing the flag to the scheduled arm → red; the cap reverted to `.infinity` → red; a `split` on the
venue string → red (2 tests). Two Swift predicate mutants: the `isFinished` guard removed → 4
failures; the clock dropped → 3 failures (baseline 1, the clock leak above).

## 7. Scope held, and what is deliberately not in it

- **Detail page only.** The producer serves `venue_settled` on `/api/events/{id}` and nowhere else,
  so Discover cards, search rows and team schedules **cannot** see it and are unchanged. Said out
  loud rather than implied: a card for one of these 1,471 events still reads as it did.
- **No status, no write.** `status`, the scores and `started_without_result` are untouched —
  #3211's rail depends on that predicate, and narrowing it un-rescues 171 US Open rows.
- **The clock gates it** (#4021): a graded market on a fixture that has not kicked off does not
  settle the page. A mis-attached market (#2693) is the one way the key can be wrong and this is the
  cheap guard against publishing it.
- 🔍 **Recorded, not filed:** the market list one scroll below still renders the graded outcome as
  `Draw 0-0 · 100%` with its siblings at `0%` — a price where a verdict belongs. That is the native
  sibling of ux's #4788 render rule, it is not introduced here, and I did not file a third issue for
  it before checking whether one is already open; it is noted on #6381 instead.
- ⚠️ The iOS notification permission alert lands over the lower half of every frame here. Known and
  already recorded by native/176 (it fires ~4.7 s after the feed draws, on a first launch);
  `-suppress_notification_prompt` is passed and still loses about a third of the time. Every claim
  above is read off the hero and the chart line, both above the alert.
