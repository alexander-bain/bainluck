# LAT-P071 — T5: **PASS, 6/6**. And the re-read rule is why.

**Graded strictly against `lat-p070-t5-grading-protocol.md`, ratified by Fable (LAT-P071 ruling b):
denominator 6, `last_success_at` grading, three pre-decided causes for `mlb_schedule_coverage`.
Nothing else was consulted.**

Horizon: **2026-08-18T17:01Z → 2026-08-19T17:01Z**. Final read **2026-08-19T08:19:01Z**.
Raw: `lat-p071-t5-read.json` (07:51:11Z) and `lat-p071-t5-read-final.json` (08:19:01Z).

## The verdict

| task | queue | beat | started | **delay** | terminal | rubric |
|---|---|---|---|---|---|---|
| `mlb_schedule_coverage` | heavy | 07:05 | 07:05:02.165Z | **0.0 min** | ✅ 07:05:03.263Z (1,077 ms) | **PASS** |
| `flow_sentinel` | heavy | 07:10 | 07:10:00.061Z | **0.0 min** | ✅ 07:11:57.983Z (117,905 ms) | **PASS** |
| `grid_sentinel` | heavy | 07:25 | 07:39:01.480Z | **14.0 min** | ✅ 07:39:04.895Z (3,391 ms) | **PASS** |
| `horizon_sentinel` | heavy | 07:40 | 07:41:08.102Z | **1.1 min** | ✅ 07:41:08.471Z (349 ms) | **PASS** |
| `settled_concept_sentinel` | heavy | 07:45 | 07:50:57.197Z | **6.0 min** | ✅ 07:50:57.388Z (174 ms) | **PASS** |
| `board_sentinel` | heavy | 07:50 | 07:51:40.127Z | **1.7 min** | ✅ 07:51:57.440Z (17,284 ms) | **PASS** |
| `calibration_sentinel` | — | weekly Mon 06:20 | — | — | — | **EXCLUDED — cadence-ineligible** |

> ### **T5: 6/6 eligible PASS, with `calibration_sentinel` EXCLUDED for cadence. VERDICT: PASS.**

**Report the denominator as 6 and name the exclusion** (§6). "6/7" without the reason is a fail that
is not one: `calibration_sentinel` is weekly (next fire 2026-08-24T06:20Z, seven days outside the
horizon) and a weekly beat's counters are zero on six days in seven by construction.

**And T5's claim is confirmed in its own words: LATE, NEVER MISSING.** Every one of the six ran, and
the lateness is real and unevenly distributed — 0.0 / 0.0 / **14.0** / 1.1 / 6.0 / 1.7 minutes. On a
2-slot heavy pool that spread is contention, not fault, and T5 pre-authorised exactly it.

No release landed between 07:05Z and 08:19Z — v3857 (`f2ac1657`, 05:43:49Z) is the most recent, so
**there is no §5 confound to record**.

## 🔴 The premature read said REFUTED, and it was wrong by 29 seconds

The first read, taken at **07:51:11Z** — the protocol's own opening time plus 71 seconds — returned:

```
board_sentinel    BRANCH C = MISSING
                  last_started_at = 2026-08-18T07:50:00Z   (before the horizon opened)
T5: 5/6           VERDICT: REFUTED — MISSING: board_sentinel
```

**`board_sentinel` started at 07:51:40.126Z — twenty-nine seconds after that read.**

Reported literally, T5 would have been REFUTED and its standing remedy triggered: heavy concurrency
2 → 3, a production change, for a task that was 1.7 minutes late on a 2-slot pool. The rubric was
followed exactly and produced the wrong answer.

**The defect is in the protocol I wrote, and it is a one-line one.** §2 sets the read at 07:50Z
"because that is the last of the seven beats to fire — a read before it would score a task red for
not having run yet." The reasoning is right; the clock time is one minute too tight, because
**07:50Z is when `board_sentinel` FIRES, not when it can be expected to have STARTED** — and
separating those two things is the entire subject of this program. A protocol written to prevent
premature grading opened its window at the exact instant that guarantees it for its last member.

**The re-read rule saved it, and it was registered BEFORE looking** — 07:50 + 2 × the worst delay
across its five same-morning, same-queue siblings (2 × 14.0 min = 28 min → 08:18Z), the same
stopping-rule shape LAT-P070 used on `turbo_collapse` (1.5 × the worst measured delay). The
multiplier was fixed in writing and committed (`eac974b4`) before the second observation, so it
could not be chosen afterwards to produce a preferred verdict. That commit is the evidence, and its
timestamp is the proof of order.

### The amendment the protocol needs

> **A beat may not be graded until it has had the delay budget its own siblings measured that day.**
> Open the read at *last beat + 2 × worst same-morning sibling delay*, not at *last beat*. Better
> still, grade at the **horizon's close** — here 17:01Z — since T5's window runs that long and
> nothing is gained by asking early.

## §4 — `mlb_schedule_coverage`, graded separately against a named cause

Pre-decided causes A (counter-window artifact) / B (genuine hard kill) / C (never fired). Today's
row:

```
last_started_at 07:05:02.165Z · last_success_at 07:05:03.263Z · 1,077 ms
starts_24h 1 · successes_24h 1 · health: healthy
```

**None of A, B or C. It ran, it succeeded, and its counters agree with its stamps.** The protocol
expected A to recur ("`-63` deploys only after 17:01Z, so the T5 window necessarily runs on the
*old* census — expect the phantom, name it, do not file it"). It did not recur.

**That absence is evidence FOR the diagnosis, not against it.** LAT-P070 identified the mechanism as
a *race* between four independently-expiring counters and `WINDOW_COUNTER_TTL`. A deterministic bug
recurs every day; a race does not. Yesterday `starts` and `successes` fell on opposite sides of the
expiry (1/0, rendered `hard_kills_24h: 1`, `critical`); today they fell on the same side (1/1,
`healthy`). Same code, same cadence, opposite outcome — which is what a race looks like and what a
deterministic fault cannot look like.

**Nothing is attributed to #1609 here.** Only branch C could have been, and branch C did not occur.
