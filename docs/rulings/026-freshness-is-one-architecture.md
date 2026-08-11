# RULING 026 — Freshness is one architecture, not five mechanisms

date: 2026-08-11
author: Alex
via: Fable, ratified
issues: #1698 · #1474 · #1008 · #683 · #506 · #134
relates: ruling 025 (the availability envelope — becomes plank 3's law), ruling 003 (availability is a typed decision clients render, never derive), ruling 004 (one SLO per program — freshness state is an input to those verdicts, never a competitor), rulings 009/024 (the calibration freeze that forced the reference serve path into existence)

> **Staleness is handled once, by one architecture, with four planks:**
>
> **1. Every user-facing surface declares a freshness SLO** — the maximum content age it may
> serve, per lifecycle phase, in one code registry. No registry entry, no ship.
> **2. Every producer has a heartbeat** — last-success plus a yield verdict. "It returned" is
> not "it worked."
> **3. Every serve path declares its state** — ruling 025's vocabulary, one envelope, content
> age included. Clients render the declared state and never infer one.
> **4. Detection latency is derived, never asserted** — every SLO has a detector whose
> worst-case time-to-alert is computed from the cadences in code. No finite derived TTA means
> the surface is UNMONITORED, and the cockpit says so.

## The five mechanisms become one

| Mechanism today | Under this ruling |
|---|---|
| **Availability envelope** (ruling 025, ratified 08-10, unimplemented in `feed.py`) | Plank 3's law and its only vocabulary: `{fresh, stale, degraded, empty}` |
| **SWR mirror module** (`utils/event_concept_cache.py` — 2 routes use it; everyone else hand-rolls a `primary` + `:stale` pair) | Plank 3's reference mechanics: content age baked into stored bytes, the serve decision stamped on the way out, the mirror a first-class serve path |
| **Serve-stale-with-declaration on calibration** (`routes/calibration.py` + `calibrationContract.ts`) | Plank 3's reference client contract, and plank 1's first conforming surface. Its deepest principle generalizes: **a disclosed age is what makes an age bound relaxable** (CAL-P017 lifted only the age ceiling, only because the age is in the payload) |
| **Truthful `/api/health` rework** | Plank 2's aggregation surface: health endpoints read real heartbeats. Today `/health/ready` reads five `last_poll:*` keys **nothing writes** — permanently null, and never flips `all_ok` (`routes/health.py:118-129`) |
| **Per-signal time-to-alert** | Plank 4, born here. No issue tracks it; today the concept exists as prose claims and a hand-written autopilot list covering **2 of 125 beats** (`admin_cockpit.py:155-175`) |

Also subsumed, found in the audit: `task_verdict` + `schedule_adherence` (plank 2's vocabulary),
`season_windows` (plank 1's dormant ≠ stale), the watchdogs and sentinels (plank 4's detectors),
`external_curator_freshness` (already four-state — the one util that got it right, and its header
names the whole failure class: *"a mechanism that is perfectly healthy while the signal behind it
is gone, and nothing says so"*), `golf_base` provenance (plank 3, promoted from HTTP header to
body), the `market_staleness`/`hook_staleness` silent gates (plank 3's counted swallows), and the
client state modules (`gridCellState`, `conceptLoadingState`, `calibrationContract`) as plank 3
renderings.

## The four planks, precisely

**1 — The freshness SLO registry.** One pure-data module (the `sport_keys.py` pattern: imports
nothing) mapping every user-facing surface to (a) max servable content age per lifecycle phase —
live, active, dormant (via `season_windows`), settled — and (b) a **settlement-transition bound**:
the maximum time something resolved upstream may render as open. *Settled means settled* gets a
number. SLOs may be slack — weather at 6h is honest. **The defect is never slowness; it is an
undeclared bound.** CI asserts coverage the way `test_tasks_wiring.py` asserts the beat schedule:
an unregistered user-facing route fails. Per ruling 004 this is not a second program SLO — it is
the "is the number current" input that 004's named failure says none of seven rails measured.

**2 — The heartbeat.** A heartbeat is (a) last-success stamped through the tracked rail and (b) a
yield verdict in the `task_verdict` vocabulary — because #683 proved a run that returns is not a
run that worked, and gotcha #53 proved an empty 200 is a shape, not an absence. Every beat entry
routes through `_tracked_run` (today ~29 call `run_async()` bare and are invisible to every ops
read — including `merge_duplicate_events` and `mark_resolved_futures`, which guard two of the six
named failure classes). Verdict enforcement inverts: from a 5-task allowlist
(`task_verdict.py:205-215`) to default-on with named exemptions for every producer feeding a
registered surface. Producers write the freshness keys that health reads — no surface may read a
key nothing writes.

**3 — The declared serve.** Ruling 025's envelope is the only vocabulary. The three live dialects
converge on it: the cache-envelope's `{live, stale_ok, unavailable}` (concepts/hubs), calibration's
`{stale, unavailable}`, playoffs' `{stale, degraded}`. The feed's nine-value `cache.status` stays
metrics plumbing — clause 2 of 025 stands; no mapping. Every declaration carries `as_of` (content
age, stamped into the stored bytes the way the mirror does it) and `reason`. Client-invented
thresholds are ruling-003 violations to repatriate: the 30-minute "Closed" that changes the
consensus number (`BookmakerTable.tsx:69-90`), the 8-hour lifecycle rule maintained independently
in `feedFreshness.ts` and `DiscoverView.swift`, the 5-minute chip constant (`FreshnessChip.tsx:11`).
And silent gating counts (025 clause 3, generalized): a market dropped for title staleness, a hook
silently swapped, a recall lane failing closed — each increments a served counter. **A swallow that
counts is detection; a swallow that doesn't is concealment.**

**4 — Derived detection latency.** For every registry entry, code — reading the same beat schedule
CI reads — computes worst-case time-to-alert: producer cadence + detector window + detector cadence
+ delivery hop. Prose TTA claims are banned for the reason gotcha #35 banned prose retention
ranges: **a predicate cannot consume prose** (CAL-P008: three rails cited the gotcha; all three
still ground purged markets). A delivery hop that can silently no-op is not an alert path:
`logger.warning` is not an alert (the Tier-1 coverage-drop and link-rate alarms reach no human and
self-silence at the next UTC day boundary); a Sentry event below the volume rules is not an alert
(a once-daily staleness signal can never trip a >100-in-24h rule); a GitHub filing without a token
is not an alert (the cockpit's own fallback list carries #1055). And `green_unverified` must file:
a check that keeps timing out is a check that never alarms (#1474) — under this plank that state
renders UNMONITORED, not green.

## WHY — the same discovery, made five times

Each mechanism was built after an incident where **substitution or silence was indistinguishable
from health**: #1698 (the feed served zero futures cards against 16,861 eligible rows, reproducing
every draw); #683 (500 fetched / 500 empty / 0 created, recorded GREEN every 6h for ten weeks);
the grid freshness self-check timing out and reporting confident green — twice, by two different
paths (LAT-P017, then #1474); `/health/ready` reporting nothing while looking like it reports
nothing-is-wrong; the quota guard narrowing polling to conserve quota while every frozen pregame
number renders as live. Five mechanisms is not five solutions. It is one lesson re-learned per
boundary. This ruling states the lesson once at each boundary — producer, store, serve, client,
monitor — so the next surface inherits the architecture instead of rediscovering the incident.

## Boundaries

- **Slack is allowed; silence is not.** No SLO is the defect, not a slow one.
- **The blend is the product — unchanged.** Freshness state describes our pipeline's serve. It
  never re-opens source-divergence UI.
- **One verdict per surface** (ruling 004). The registry and every rail here are inputs; cockpit
  and scoreboard keep one answer per surface.
- **Not a process layer.** Every clause traces to a named failure already on the books. No new
  meeting, doc, or lane.
- **Visible-payoff compliance.** Conformance ships surface-by-surface *with* its rendering — the
  "as of" chip, the dated stale banner, the honest terminal are product, and users see them. The
  registry/CI/heartbeat sweep is plumbing under the cap.

## Acceptance — absolute, checkable by enumeration

1. A user-facing route without a registry entry **fails CI**.
2. A beat entry that does not route through the tracked rail **fails CI**.
3. **No 200 serves non-fresh or substitute content without a declared state and `as_of`** —
   025's acceptance, inherited and widened to every route.
4. Every registry entry shows a **derived** TTA on the cockpit or renders **UNMONITORED**. Docs
   cite the derivation, never a number typed by hand.
