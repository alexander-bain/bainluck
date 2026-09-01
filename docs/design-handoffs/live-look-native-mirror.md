# The live look — native mirror

**PILLAR: FORMATTING.**
**SHIP:** a reader watching a live game on iPhone sees the same number move, at the same
cadence, with the same honest age, as the reader watching it on the web.

**Authority:** Alex, 2026-09-01, LIVE UPDATES rulings (1)(2)(3) —
`.claude/handoff/RULINGS-BATCH-2026-08-30.md`, "Tue 2026-09-01".
**Web half:** `program/ux-177-the-live-number-looks-live` (UX-P249). Shipped first, by
directive. This document is the native half, designed alongside it rather than after it,
so the two cannot be designed twice and differently.

---

## Why this is a document and not a Swift file

Ruling 007 (native riders): native work rides a named user-visible ship. This one does —
it is the same ship on a second surface. But the SSE endpoint is the live lane's and is
in flight as of 2026-09-01, and **building the iOS transport against an unbuilt
endpoint would mean designing the wire contract twice, in two languages, from one
lane's guess.** So the web half pins the contract in code (`hooks/useLiveBlend.ts`) and
this pins the native half against that same contract, in enough detail that the Swift is
a transcription rather than a redesign.

What is deliberately NOT here: pixel specs. iOS has its own type ramp and its own
`Components/`, and re-specifying them from a web branch is how a design system grows a
second opinion of itself.

---

## The three pieces, and their web sources of truth

| piece | web | native mirror |
|---|---|---|
| decisions (throttle, age, window) | `frontend/lib/live/liveNumber.ts` | `Utilities/LiveNumber.swift` — a direct port, pure, no `Date()` inside |
| transport | `frontend/hooks/useLiveBlend.ts` | `Services/LiveBlendStream.swift` — `URLSession` bytes stream |
| render | `frontend/components/live/LiveLook.tsx` | `Components/LiveLook.swift` — `LiveNumberText`, `LivePulseLabel`, `LiveSparkline` |

### 1. The number steps. It does not tween.

The single most important line to carry across, and the one SwiftUI makes easiest to get
wrong: `.animation(.default, value: probability)` on a `Text` that renders a number will
interpolate — and the intermediate frames are probabilities no market ever quoted. On a
page whose argument is "this number is what the market thinks", that is a small lie told
sixty times an hour. The standing chart rulings say the same thing about lines: raw
segments between real observations, never a curve the data did not take.

**So: no implicit animation on the value.** The digits go straight from 61 to 67. What
animates is a ~500ms foreground-colour transition in the direction of travel:

```swift
Text("\(Int(displayed.rounded()))%")
    .monospacedDigit()
    .foregroundStyle(tint)                      // colour only
    .animation(.easeOut(duration: 0.5), value: tint)   // ⚠️ value: TINT, not the number
```

`value: tint` rather than `value: displayed` is the whole distinction. Bind it to the
number and SwiftUI animates the number.

`.monospacedDigit()` is non-negotiable — an unmonospaced digit change reflows the hero
under the reader's thumb, and on a phone that is a mis-tap.

Respect `@Environment(\.accessibilityReduceMotion)`: drop the tint transition, never the
number.

### 2. The pulse takes the age of the number ON SCREEN

The throttle can hold a value back by up to five seconds. Pass the `observedAt` of the
**painted** point, not the newest received — otherwise the chip reads "2s ago" above a
seven-second-old number, which is a fresher claim than the pixel beside it. The web
guard for this is `liveLook.test.tsx` › "THE AGE FOLLOWS THE PAINTED POINT"; the Swift
port needs its twin.

Three tones, same thresholds as web (`LIVE_AGE_LIMIT_MS`, 2 min):

* under 2s → `live`
* under 2 min → `live · 12s ago`
* over 2 min → `updates paused · 4m ago`, amber, **dot stops pulsing**

⚠️ The word **stale** is banned in reader copy (`lib/copyBans.ts`, `JARGON_BANS` — it is
our `price_state` enum). `Components/FreshnessChip`'s web twin says it; do not inherit
that.

⚠️ An open socket is not freshness. The tone is a function of the observation timestamp
and nothing else, so a stream that connects and then goes quiet reads "updates paused",
not a green dot.

### 3. The sparkline is the last ten minutes on a fixed 0–100 axis

`Components/SeriesProbabilityView.swift` already exists and is the renderer to ride, for
the same reason the web half rides the shared `Sparkline` rather than hand-rolling a
sixth one.

**Do not auto-fit the Y axis.** It is the most tempting change and the one that makes the
chart lie: a market that moved 61.2 → 61.6 would draw a dramatic climb across the full
height. The flat line is the truth, and a flat line is what a reader should see when
nothing happened. Web guard: "A FLAT WINDOW DRAWS FLAT — the axis is not auto-fitted",
paired with a non-vacuity arm proving a real move does show.

Fewer than 3 points in the window → **draw nothing**. One point is a zero-length path: an
empty box that reads "we have no data" when the truth is "nothing has changed in nine
minutes".

### 4. The illiquidity ring stays

Untouched by any of this. It answers "how much should you trust this number", the pulse
answers "how old is it", and they are different questions. Ruling (2) says the ring
stays and the correct native change here is none.

---

## Transport

```
GET /api/live/stream?events=<id>,<id>        text/event-stream

event: blend_update
data: {"event_id":123,"probability":0.614,"observed_at":"2026-09-01T18:04:11Z"}
```

`probability` is the 0–1 blend; convert to points once, at the parse boundary, exactly as
`parseBlendUpdate` does. `observed_at` is when the BLEND observed it — per ruling (3) a
source older than ~2 min is already out of the blend, so this is the age the reader is
entitled to see. **A heartbeat frame must not refresh the age**: nothing was observed.

Native uses `URLSession.bytes(for:)` and parses SSE line-wise; there is no `EventSource`
on Apple platforms. Reject strictly, and each rejection is a frame that would otherwise
put a wrong number under a green dot:

* a frame whose `event_id` is not this view's — the endpoint takes a comma list, so a
  shared connection carries siblings;
* a probability outside 0…1 or non-finite;
* an absent or unparseable `observed_at` — a point with no honest age has no place in a
  feature whose whole claim is the age.

**Live events only** (ruling 1). The subscribe call is gated by the view, not by the
service: only the view knows whether its event is in play, and that gate is the whole
difference between "push for live events" and "a socket per row in the feed". Non-live
keeps polling, unchanged.

⚠️ **Background the connection.** Tear the stream down on `scenePhase != .active` and
re-open on return. A web tab that is hidden costs a socket; a phone in a pocket costs
battery, and this is the one place the native mirror must NOT mirror the web.

---

## The one assumption, named

`blend_update.probability` is read as the **home** win probability, matching
`Event.win_probability_sources` and every other event payload. If the live lane settles
on a different side, two lines change on web (`parseBlendUpdate`, and the card's
`liveHomeProb`) and their two Swift twins. Named here so it is a lookup rather than a
rediscovery.

## Surfaces, in order

1. `Views/EventDetailView` hero — the highest-value one; a reader watching a game has
   this open.
2. The live rows in the Discover feed.
3. `BainLuckWidget/LiveGamesWidget` — **age only, no stream.** A widget cannot hold a
   socket, and its timeline refresh is measured in minutes, so the honest thing there is
   the pulse label over the last fetched number. The widget is where "updates paused"
   earns its keep.
4. `BainLuckWatch/WatchLiveView` — pulse + number, no sparkline. Ten minutes of history
   in 40mm is chrome, and ruling 4 of the chart set is minimal chrome.
