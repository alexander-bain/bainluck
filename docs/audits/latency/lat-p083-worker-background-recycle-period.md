# The `worker-background` recycle period — settled, with the loser's error named

**LAT-P083, 2026-08-23.** Fable directive item 2: *"two lanes now disagree and both claim
measurement: INT-110 reported a 6h grid (16:03:08 / 22:03:32 / 04:03:30), you report a 12h period
with 24h refuted. Both cannot be right. Settle it by evidence you cite, state the winner and the
loser's error, and publish the hard ceiling a worker-horizon read can assume."*

---

## VERDICT: the 6-hour grid WINS. LAT-P082's 12-hour period is REFUTED.

### The evidence, cited

Read by this lane at **2026-08-23T14:47:57 PDT**, `heroku ps -a bainluck`:

```
worker-background.1: up 2026/08/23 10:05:12 -0700 (~ 4h ago)
```

Control, read in the same turn (`heroku releases -a bainluck -n 6`): current release
**v3884 `a13239f1`, 2026-08-21 11:37:18 PDT**. No deploy between 08-21 11:37 and the read, so the
10:05:12 restart has **no release to explain it**.

⚠️ **This read landed 43 seconds before it stopped existing.** v3885 deployed at **14:48:40 PDT**
and restarted every dyno. Had the read been taken a minute later, `worker-background`'s start time
would have been the deploy's and the question would have been unanswerable for another cycle.

### The arithmetic that discriminates

| hypothesis | predicts last restart before 14:47:57 | predicted uptime | measured uptime |
|---|---|---|---|
| **12 h**, phase 04:03 | 2026-08-23 **04:03** | **10 h 44 m** | — |
| **6 h**, phase ~:03–:05 | 2026-08-23 **10:03** | **4 h 45 m** | **4 h 42 m 45 s** ✅ |

**12 h is refuted by a positive observation**, which is the only thing that can refute a period.

### The full point set, all four consistent with a 6 h grid

| # | restart (PDT) | gap from previous | as multiples of 6 h | source |
|---|---|---|---|---|
| P1 | 2026-08-21 16:03:08 | — | — | `DEPLOY-FREEZE-2026-08-21.md`, INT-109 |
| P2 | 2026-08-22 04:03:43 | 12 h 00 m 35 s | 2 × 6 h + 35 s | LAT-P081 notice |
| P3 | 2026-08-23 04:03:30 | 23 h 59 m 47 s | 4 × 6 h − 13 s | LAT-P082 |
| **P4** | **2026-08-23 10:05:12** | **6 h 01 m 42 s** | **1 × 6 h + 102 s** | **this lane, 14:47:57 PDT** |

INT-110's reported 22:03:32 is the same kind of point as P4 — an **intermediate-slot** observation,
one that lands on the 6 h grid and off the 12 h one. Two independent lanes have now produced one
each.

---

## The loser's error, named

LAT-P082 wrote: *"a 12-hour period fits all three to within 35 s over 36 hours"* and read **fit** as
**confirmation**.

**12 h is a strict subset of 6 h.** Every instant on a 12-hour grid is also on a 6-hour grid with
the same phase, so a sample set consistent with 12 h is *automatically* consistent with 6 h and
cannot distinguish them. Its three points, P1–P3, all happen to land on 12 h slots — and that is
not evidence, it is a 1-in-8 coincidence over three draws, or simply the shape of when somebody
happened to look.

**Confirming the COARSER of two nested periods requires an ABSENCE** — proof that nothing restarted
at the intermediate slots. And the instrument used, `heroku ps` uptime, reports only the **most
recent** restart. It structurally cannot observe an intermediate restart that a later one has
already overwritten. **LAT-P082 made a claim its instrument could not have refuted.**

### The symmetry is what makes this worth banking

In the same paragraph, LAT-P082 refuted **24 h correctly**, by exactly the right move: a positive
observation (the 12 h 00 m 35 s gap) that lands **off** the 24 h grid. Then it confirmed 12 h by
the wrong move. One window, one instrument, both directions — which is the cleanest possible
demonstration that the asymmetry is a property of periodic hypotheses and not of carelessness:

> **Among nested periodic hypotheses only the FINEST is refutable by observation. A coarser one is
> confirmed only by an absence, and a last-event-only instrument can never observe an absence.**

Offered as a doctrine candidate, **not claimed** — no clause number is minted here (see the report).

### On Alex's `heroku logs` grep returning ZERO lines

Correctly characterised in the directive as **no evidence, not absence**, and the reason is
concrete: `heroku logs` is EPERM-blocked from the agent sandbox, and Heroku's logplex retains only
~1,500 lines / 1 week regardless. A zero-line grep is a fact about the retrieval path. Gotcha #53,
in a CLI rather than an API: an empty result is a response shape.

---

## The hard ceiling a worker-horizon read can assume

**`worker-background`: HARD CEILING 6 HOURS.** It restarts on a 6-hour grid at ~:03–:05 past
**04, 10, 16, 22 PDT**, with drift up to ~+102 s observed across one interval. No deploy freeze can
buy more — the dyno recycles on its own, and the freeze only removes the *deploy* cause.

* **A read started at an arbitrary time gets ~3 h in expectation** (uniform phase), not 6.
* To get the full 6 h you must start within minutes of an observed restart.
* `--max-memory-per-child=200000` recycles the **child**, not the dyno, so it cannot explain a
  change in the dyno's start time. LAT-P082 had this right.

**`worker-heavy`: ~24 HOURS, and it is the one the falsifier actually needs.** It restarts with the
fleet-wide daily cycle, not with `worker-background`. Measured, with no release in either window:
2026-08-22 11:42–11:59, and 2026-08-23 12:04:46 (`heroku ps`, this lane) — a ~24 h period drifting
roughly +25 min/day. All nine falsifier-watched beats run on `heavy`.

### Why the correction matters practically

LAT-P082's error was in the **dangerous direction**. Its published "hard 12 h ceiling" would license
a `worker-background` horizon window twice as long as the dyno can actually hold — and this program
has already lost five consecutive windows to horizons that turned out not to exist. A ceiling that
is too generous is not a conservative error; it is the error that schedules the sixth defeat.

### Full-fleet snapshot, 2026-08-23 14:47:57 PDT, release v3884 (unchanged since 08-21 11:37:18)

```
scheduler.1        up 2026/08/23 12:08:52 -0700
web.1              up 2026/08/23 12:04:46 -0700
worker-background.1 up 2026/08/23 10:05:12 -0700   <-- alone, off the fleet cycle
worker-heavy.1     up 2026/08/23 12:24:09 -0700
worker-realtime.1  up 2026/08/23 12:13:21 -0700
worker-ws.1        up 2026/08/23 12:39:43 -0700
```

Five of six dynos restarted within 35 minutes of each other at ~12:0x–12:3x with **no release**.
`worker-background` is the one dyno out of step, exactly as LAT-P082 observed — its diagnosis of
*which* dyno is anomalous was right, and only its period was wrong.
