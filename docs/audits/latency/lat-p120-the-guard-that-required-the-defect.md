# LAT-P120 — the guard that required the defect

**Cycle 92 · 2026-08-29 · `program/latency-105` · issue #2279**
**Pillar: FORMATTING. Ship: no surface in the product can print 101% from a partial payload.**

---

## The one-paragraph version

UX-P114 (#2060's sibling) moved the two whole percents a game strip prints onto the server, so
that the two sides of one question would be decided ONCE and could never sum to 101. Six surfaces
adopted the fields. All six coalesced **per side** —

```
let awayPct = odds.awayRenderedPercent ?? duelFallback[0]
let homePct = odds.homeRenderedPercent ?? duelFallback[1]
```

— which prints a served value beside a locally derived one the moment a payload carries one field
and not the other, and that is the same 101 UX-P114 shipped to close, arriving from the other
direction. #2279 named three of them. This branch fixes six, and finds three things the issue did
not name — one of which is that **UX-P114's own CI gate was asserting the defect as an acceptance
criterion**, which is why it survived on three surfaces and why running the suite could never have
found it.

---

## 🔴 Finding 1 — the contract gate REQUIRED the per-side coalesce

`frontend/__tests__/lib/renderedPercentContract.test.ts`, in the check named *"every native surface
that prints BOTH sides consumes the decision"*:

```js
// The served value PREFERRED over it, on EACH side independently — `??`
// proves it is the first choice rather than a variable computed and ignored.
for (const side of ["away", "home"] as const) {
  const field = `${side}RenderedPercent`;
  expect([rel, side, new RegExp(`${field}\\s*\\n?\\s*\\?\\?`).test(code)]).toEqual([rel, side, true]);
}
```

The shape it demanded — one `??` per side, on every surface — **is** #2279. The gate written to
protect the pair was holding the thing that breaks it in place, on three files, and it did so with
a comment explaining why. Its intent was sound ("preferred, not computed and ignored"); it
expressed that intent by prescribing a *mechanism*, and the mechanism was the bug.

This is not "a test that missed a defect". It is a test that would have **failed the fix**. Any
session that had corrected one surface would have watched CI go red and concluded the correction
was wrong.

Repaired both ways rather than deleted:

- the fallback claim now accepts `duelPercents(` as well as the inner `renderedDuelPercents(` — a
  check that names only the inner call is a check an extraction breaks while the behaviour is
  intact, which is exactly what LAT-P119 hit on `npm run contract` one file over;
- the per-side coalesce is **banned** where it was required, and the "both sides are named" half is
  kept, so the older mutation it was defending against (drop the away side, pass on the home side's
  `??`) is still killed.

**Offered as a gotcha:** *a guard can encode the defect as its acceptance criterion.* The usual
failure is a guard that is silent; this one was loud and pointed the wrong way, and loud-and-wrong
is worse, because it recruits every future session into defending it.

---

## 🔴 Finding 2 — the home-screen widget is a fourth native surface, and it was the worst of them

#2279 named `DiscoverEventCard`, `MenuBarView` and `RelatedByTagView`. Grepping for consumers of
the served fields — rather than trusting the issue's list — turned up
`BainLuckWidget/WidgetAPIClient.swift`:

```swift
homeProb: event.currentOdds?.homeRenderedPercent ?? Int((homeProbability * 100).rounded()),
awayProb: event.currentOdds?.awayRenderedPercent ?? Int((awayProbability * 100).rounded()),
```

The widget is a standalone target that cannot import `RenderedPercent.swift`, so **what reached it
from UX-P114 was the PREFERENCE and not the RULE.** Its fallback stayed the original independent
rounding on each side. With the served fields absent — the case its own struct comment says they
are optional *for*, "the widget can outlive a rollback" — the home screen printed 101 on the same
8.2 % of events UX-P114 measured. Fixing only the coalesce here would have left the dominant
failure untouched and shipped as a win.

`away = 1 - home` by construction in this file, so `renderedDuelPercents`' `[0.99, 1.01]` band test
and its divide-by-total are both **identities** on this input. What is left of the shared rule is
its entire content for this case: round the FAVOURITE once, derive the underdog as
`100 - favourite`. That is transcribed rather than imported, and the transcription is pinned to the
shared implementation row-for-row (every half-percent, plus every `duel_cases` row of
`contracts/rendered_percent.json`, re-derived the widget's way) so it cannot drift the way an
unpinned copy would. The band constants stay absent, which the contract suite already asserts.

**The target-membership question is parked, not answered.** The right long-run fix is for
`RenderedPercent.swift` to be a member of the widget target — the project uses Xcode 16
file-system-synchronized groups, and the widget target does still carry a `Sources` build phase, so
it is possible. It is a `project.pbxproj` edit and it is not made here: parked **P120-1**.

---

## 🔴 Finding 3 — the menu bar reads the served pair on a branch the pair does not describe

```swift
guard let homeProbability = event.currentOdds?.homeProbability ?? event.openingOdds?.homeProbability
```

The served percents describe `current_odds` **and nothing else**. On the `openingOdds` branch the
old code still read them, so it printed one source's rounding beside another source's probability.
It still sums to 100, so no sum guard — including the one this program has been building — could
ever see it. This is LAT-P119's M3 species, on a surface nobody had looked at: the mutant that
passes every check because the *shape* of its output is right and only the *provenance* is wrong.

`fromCurrentOdds` is now recorded at the branch that knows, before the guard that may substitute,
and the guard test asserts that ordering rather than just the flag's existence.

Same file: its third-tier fallback was `?? Int((p * 100).rounded())`, a fourth unshared copy of the
rounding reachable only when the contract rule declines to answer — and `Int(_:)` **traps** on a
non-finite `Double`. The pair rule is now the last word: if it declines, the row is dropped. The
widget takes a `.isFinite` clause for the same reason. `JSONDecoder` refuses `NaN` literals by
default so neither was reachable from the API; a trap in a widget timeline is a blank widget with
no log, and the clause costs nothing.

---

## What shipped

| surface | file | was | is |
|---|---|---|---|
| Discover card (native) | `Components/DiscoverEventCard.swift` | per side | `duelPercents` |
| Related markets row | `Components/RelatedByTagView.swift` | per side | `duelPercents` |
| macOS menu bar | `Views/MenuBarView.swift` | per side + wrong-source + trap | `duelPercents`, source-gated |
| Home-screen widget | `BainLuckWidget/WidgetAPIClient.swift` | per side + naive fallback + trap | pair, derived, `.isFinite` |
| Discover card (web) | `components/discover/EventCard.tsx` | per side | `servedDuelPercents` |
| Feed card (web) | `components/FeedCard.tsx` | per side | `servedDuelPercents` |

Two shared decisions, one per runtime, pinned to each other by test:
`duelPercents` in `ios/.../Utilities/RenderedPercent.swift` and `servedDuelPercents` in
`frontend/lib/servedDuelPercents.ts`. The web one is a NEW file rather than an addition to
`lib/renderedPercent.ts` because that file is in the ux lane's active tree.

---

## Gates

- **frontend jest 4,267 passed / 4 skipped / 4,271 total, 227 suites, EXIT 0 READ BY VALUE.**
  Baseline on the same tree with the two new files excluded: **3,559 → +712, enumerated AND
  measured** (246 + 466 = 712, exact).
- `npm run build` EXIT 0 · `npm run typecheck` EXIT 0 (**70 = baseline 70**).
- `npm run contract` **489 pass / 0 fail / exit 0 — and 489/0/exit 0 on MASTER `61dc61ac` too**,
  measured in a throwaway worktree, so the count is unchanged rather than merely green.
- **Native, and this is the gate that matters for a Swift-only ship:**
  `xcodebuild -scheme "Bain Luck" -destination platform=macOS,arch=arm64` → `** BUILD SUCCEEDED **`
  exit 0, and `-target BainLuckWidget -sdk iphonesimulator` → `** BUILD SUCCEEDED **` exit 0. Both
  needed gotcha #117's `-clonedSourcePackagesDirPath <warm store>/SourcePackages
  -disableAutomaticPackageResolution` plus #116's `-Xfrontend -disable-sandbox`.
  ⚠️ The first attempt used a DerivedData store with **5 of the 6** SPM artifacts and died on
  `exit 74`, blaming a `dl.google.com` timeout — the failure reads as "the network is down", and it
  is really "you borrowed the wrong warm store". Picking the store by artifact COUNT, not by mtime,
  fixed it. *(Offered as an amendment to gotcha #117.)*
- **Mutation battery 16/16 killed, 0 survived, 0 harness failures, exit 0**, residue verified by
  sha256 over all 8 targets at exit.
- Residue scanner **CLEAN exit 0, 191 needles, 272 broad checks, run on a COMMIT**. `--all-tracked`
  exits 1 with 5 pre-existing candidates — **identical list on master `61dc61ac`, measured**, so
  this branch adds **+0**.
- ruff clean on both changed `.py` files.
- Scoped backend: `test_startup.py` + `test_mutation_guard.py` **13 passed exit 0**, including
  `test_every_on_disk_harness_is_guarded`.
- Full backend suite: see the report — this branch has **zero `backend/app/` code**.

### ⚠️ The battery reported 11/11 and it was not a full result

An intermediate run printed `11/11 killed, 0 survived` and exit 0. Five web mutants had silently
failed to append to the table, and the run said so in the line it prints **before** the first
verdict: `11 mutants queued`. A battery that reports its denominator caught an edit that did not
apply; one that reported only its kills would have printed a clean sweep over a table missing a
third of itself. *(Memory's "a mutation must prove it applied", one level up: so must the mutation
TABLE.)*

### ⚠️ One full-suite run killed by PID on purpose

Source edits landed mid-run, so the result would have been about a tree that no longer existed.
Killed by pid (77274/77281), never `pkill -f`; the ux lane had its own `pytest tests/ -q` in the
same `ps` and it was verified ALIVE after.

---

## Parked

- **P120-1** — make `RenderedPercent.swift` a member of the `BainLuckWidget` target
  (`project.pbxproj`, `Sources` phase `A7C0…F4`) so the widget's transcription can be deleted.
  Wants a widget build to verify, which this cycle has, but it is a build-system change and not
  this ship.
- **P120-2** — fold `-104`'s `withRenderedPercents` (in `lib/eventKeyStats.ts`) onto
  `servedDuelPercents` once `program/latency-104` merges. Two web implementations of one rule is
  one too many; they cannot be merged before both are on master.
- **P120-3** — the gotcha: *a guard can require the defect.* Offered.
- **P120-4** — gotcha #117 amendment: pick the borrowed SPM store by ARTIFACT COUNT, not mtime; a
  store missing one artifact fails as a network timeout.
