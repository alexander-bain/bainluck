# The felt number: `screen_timing` on web and native

**Pillar: TRUTH. Ship: every screen, on every device, reports how long a stranger
waited before they saw a real card — so the slowest one can be found and fixed
without anyone holding a stopwatch.**

Staged by latency/121 (Alex, 2026-09-02: *"We're trying to make everything fast…
Latency isn't JUST about the Discover page. It's all tab loads. We need to also
make sure native, not just web, is lightning fast."*).

---

## Why a new event, when Web Vitals and three native rails already exist

Neither answers the question.

**FCP fires when the skeleton paints.** A grey placeholder grid is contentful, so
Discover posts a ~0.15 s FCP while the reader is still looking at nothing.
Measured on production 2026-09-02: FCP 128 ms, first real card 434 ms — and on
the bad runs, FCP 156 ms with *no card at any point*. A rail built on FCP reports
the totally-broken load as the fastest one on the board.

**LCP names the largest element**, which on a card surface is a hero photograph.
It is a number about imagery.

**The three native rails** (`discover_feed_first_render`,
`sports_feed_first_render`, `my_stuff_first_render`) do measure the right moment,
but each has a different parameter set, they cover three screens out of ~30, and
the Watch has no analytics at all. You cannot build a per-screen table out of
them.

So: **one event, `screen_timing`, identical on web and native.**

## The packet

| key | meaning |
|---|---|
| `surface` | bounded slug, dynamic segments masked (`events/:id`). Never an id. |
| `entry` | `cold` (document load / app launch) or `warm` (in-app transition) |
| `shell_ms` | first contentful paint / first frame |
| **`first_card_ms`** | **the needle** — first real, non-skeleton card on screen |
| `fold_ms` | last above-the-fold real card; the first screen stopped changing |
| `interactive_ms` | screen finished its critical work |
| `card_count` | real cards above the fold when it settled |
| `device_class` | `phone` · `tablet` · `desktop` · `watch` · `unknown` |
| `network_class` | coarse effective type |
| `app_build` | short build tag |
| `outcome_class` | `ok` · `empty` · `no_card` · `error` |

Two conventions that are load-bearing:

- **Every duration is milliseconds and `-1` means "not measurable / did not
  happen".** Never `0`. "Did not happen" and "happened instantly" are different
  claims and a rail that collapses them reports its worst failures as its best
  results.
- **`cold` and `warm` are never blended.** The target is written per-entry
  (<3 s cold, <1 s warm); a blended p50 cannot be compared to either.

`empty` vs `no_card` is the other distinction worth defending: *"this screen has
nothing to show"* is a product state, *"nothing appeared"* is a defect. Collapsing
them hides the defect inside a legitimate empty state.

## Web

`frontend/lib/screenTiming.ts` + `components/Analytics/ScreenTimingReporter.tsx`.

Nothing to wire per page. One MutationObserver mounted in the telemetry gate
covers all 40+ routes and any route added later. It detects a real card from the
DOM using the rule below, stops as soon as the first screen goes quiet, and is
inert for the rest of the visit.

**A real card** is an element that (a) matches the card selector, (b) carries no
`animate-pulse` skeleton on it or inside it, (c) is not inside an `aria-hidden`
placeholder subtree, (d) is at least 80×40 CSS px, and (e) has ≥12 characters of
text — using `textContent`, never `innerText`, because `innerText` forces a
layout on every pass and the instrument would become part of what it measures.

🔴 **Sampling bias, stated because it is real.** This rail emits through gtag, and
gtag.js is only loaded after a consent grant, so the field table describes
*consenting* visitors. That is the same bias Alex ruled against for Speed Insights
(LAT-P197 / D30), but the remedy there was an un-gated vendor and there is no
un-gated path to GA. The unbiased cold number comes from `tools/felt-load.mjs`
and Speed Insights; this rail is the per-surface, per-device breakdown neither of
those can give.

## Native (iPhone / iPad / Mac / Watch)

`ios/Bain Luck/Bain Luck/Services/ScreenTiming.swift`.

**Already live with no view changes:** Discover, Sports and My Stuff emit
`screen_timing` from the same first-render moments their existing rails use.
Those bridged packets report `-1` for `fold_ms`, `interactive_ms` and `shell_ms`,
because those call sites genuinely do not know them — the gap is visible rather
than filled with a plausible fabrication.

**To add a screen** — two modifiers, and the second is the only one that needs
thought:

```swift
SomeScreen()
    .screenTiming("event_detail")     // on the screen

// inside it, on the FIRST real content row:
EventHeroCard(event: event)
    .firstRealCard()

// and, on the loading state:
SkeletonRows()
    .screenTimingLoading(true)
```

🔴 **Never attach `.firstRealCard()` to a placeholder.** A skeleton wearing the
marker reports the app as instant, which is strictly worse than no rail because
it would be believed. `.screenTimingLoading(true)` is the backstop: a mark taken
while the screen has declared itself loading is ignored.

`.firstRealCard()` outside a `.screenTiming()` subtree is a silent no-op, never a
crash — it reads an optional environment value rather than an `@EnvironmentObject`,
which traps when absent.

### What is NOT covered yet

**The Watch reports nothing, and this queue did not fix that.** The measurement
core compiles for watchOS, but the Watch target has no Firebase and no
WatchConnectivity bridge, so there is no transport for a packet to leave the
device. Building that bridge is its own piece of work and is filed separately;
until it lands, every Watch row in the table is absent, and absent is not zero.

Screens other than Discover / Sports / My Stuff need the two modifiers above.
They were not added in this queue because the iOS project cannot be built in the
agent sandbox — Firebase's binary SPM targets fail to download — so a wiring
change spread across 30 view files could not have been compiled, let alone run.

## The lab rig underneath

`tools/felt-load.mjs` measures the same three moments in real headless Chromium
against production, cold and warm, with throttling. It shares the card-detection
rule with the web rail *character for character*, and a guard test
(`frontend/__tests__/lib/screenTiming.test.ts`) reds if the two drift — otherwise
a ship's "−400 ms" claim would silently change meaning.

```
node tools/felt-load.mjs discover 5 out.json          # cold
FELT_MODE=warm node tools/felt-load.mjs sports 5      # warm tab-switch
FELT_THROTTLE=slow4g FELT_CPU=4 node tools/felt-load.mjs discover 3
bash tools/felt-battery.sh /tmp/felt-YYYY-MM-DD       # the whole table
node tools/felt-table.mjs /tmp/felt-YYYY-MM-DD        # render it
```

🔴 **A run that rendered no card is INVALID, not fast.** It is excluded from the
medians and counted in its own column. Averaging it in reports the failure as an
improvement (LAT-P202: eight consecutive empty renders posted a *faster* FCP than
the healthy ones).
