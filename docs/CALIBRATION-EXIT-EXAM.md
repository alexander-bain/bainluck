# CALIBRATION EXIT EXAM

**Alex's ruling, 2026-08-09.** The calibration slot rotates to Discover when all seven items
below are green **with linked proof**. Alex reads this document in one sitting; his pass is the
rotation trigger. The ruling itself is banked in `docs/PRODUCT-BRAIN.md` §*THE CALIBRATION EXIT
EXAM*.

**This document is the deliverable.** A cycle that ships code and moves no item here has not
moved the lane toward rotation. Every item states what proof it needs *before* the work starts,
so no cycle can finish and then discover its evidence was unobtainable.

---

## Scoreboard

| # | Item | Status | Blocked on |
|---|---|---|---|
| 1 | Ruling 9 shipped; published count reflects volume-proven trading, both figures named | 🟡 **RULED 2026-08-09** — definition settled, unbuilt; **tier-2 census is not hand-measurable, needs a rail** | a census rail (CAL-P024), then a healthy publish |
| 2 | Trading-activity section led by matched-bucket comparison | 🔴 not started | — (ready to stage) |
| 3 | Cricket + entertainment diagnosed to fix / exclusion / "genuinely bad" | 🟡 measured, undiagnosed | a census rail — the distinguishing query times out in `db-query` |
| 4 | Source graph redesigned — per-source panels | 🔴 not started | — (ready to stage) |
| 5 | Native calibration surface consistent with web | 🔴 unassessed | — (ready to stage, needs no prod) |
| 6 | Monitoring proven by drill — watchdog + sentinel guards observed firing | 🟢 **WATCHDOG HALF PASSED 2026-08-09** — observed firing, issue #1604 | sentinel half is plumbing #1548 |
| 7 | Backfill recovery progressing vs 786K recoverable; capture-floor re-measure ~Aug 15 | 🟡 **BASELINE ESTABLISHED 2026-08-09** — 797,871 recoverable, measured to exhaustion | a second dated measurement; ~Aug 15 |

**One item is green** (6, watchdog half). Item 7 has its first datapoint for the first time.
Items 2, 4 and 5 are unblocked and stageable today; **5 needs no production access at all.**

### The one scheduling fact that governs the exam

Items **1** and **3** change what the curve plots, so each carries a
`CALIBRATION_POPULATION_VERSION` bump. Already-staged **CAL-P019** carries a third. A bump takes
`/calibration` dark until the next successful beat.

**No bump ships until the build publishes again.** As of 2026-08-09 10:54 PT the build has still
not published since **2026-08-02 03:23:54 UTC** (age 7.59d). Until `calibration:main.generated_at`
moves, **items 1, 3 and 7 cannot be evidenced at all** — their proof is a published number.

That makes CAL-P016's convergence the critical path for most of this exam.

### CAL-P016 convergence — measured 2026-08-09 10:36–10:54 PT, window `b2e4`

The staged path is **working but not yet proven to converge**, and the distinction is exact:

| fact | value |
|---|---|
| beat | hourly at **:15**, `soft_time_limit=1500s` |
| staged beats run since deploy | **exactly one** — generation `1786292100304` = 16:15:00Z |
| that beat | `read:futures_generation` 25.7s + `read:futures_unit` 626.2s → **10 units banked**, then cancelled at 726.6s |
| per-unit cost | **~62.6 s/unit**; 128 units ⇒ ~2.2h of compute ⇒ **~13 beats** |
| cursor | `terminal=partial`, 10 committed, `population_version=q267` |
| plan | **`status: infeasible`** — `floor_ms` 1,352,317 over `floor_observations: 10` |
| floors | `[1352317, 1351773, … ×9 stale monolith TIMEOUTS, 726557]` |

**Two findings, both new.**

1. **The floor is poisoned by the old regime.** Nine of the ten banked observations are
   pre-CAL-P016 monolith *timeouts* at ~22.5 min. The planner therefore still believes `futures`
   needs 22.5 minutes and marks the plan `infeasible`. It is a rolling window of 10, so it
   self-heals — but only after ~9 more staged beats push the timeouts out. `infeasible` does not
   block banking (the beat banked 10 units anyway); it is a wrong belief, not a gate.

2. **Cross-beat retention is UNOBSERVED, and it is the whole ballgame.** The ledger's
   `stages` records **`staged:cursor_invalidate`** for the one beat that has run. That is
   *expected* on the first beat — the pre-existing cursor predated the new code, and
   `input_fingerprint` hashes the SOURCE of the build functions, so a deploy necessarily
   invalidates it. But the queue's earlier "4/128 and advancing" reading was **mid-beat, not
   cross-beat**: both the 4 and the 10 belong to generation 16:15:00Z. **No second staged beat has
   yet been observed**, so nothing has yet demonstrated that a banked unit survives into the next
   beat — which is precisely what CAL-P016 changed and precisely what must hold ~13 times in a row
   for the build to publish.

**The single decisive read for this lane** is therefore the *next* beat's ledger: if `stages`
shows `staged:cursor_resume` and `committed_units` climbs 10 → ~20, CAL-P016 is converging and
the publish is ~13 beats out. If it shows `staged:cursor_invalidate` again with the count back at
~10, the build is thrashing and CAL-P016 is not done.

### ⚠️ The beat is NOT firing hourly — measured directly, and it changes the projection

The 17:15Z miss was initially written off as benign (the INT-024 dyno restart at ~17:11Z straddled
it). **Watching a second scheduled beat disproved that.** Observed continuously 16:27Z → 18:20Z:

| observation | 16:36Z | 18:20Z |
|---|---|---|
| `precompute_calibration_main.failures_24h` | 10 | **10 — unchanged** |
| ledger generation | 16:15:00Z | **16:15:00Z — unchanged** |
| cursor `committed_units` / `updated_at` | 10 @ 16:26:24Z | **10 @ 16:26:24Z — unchanged** |

**Neither the 17:15Z nor the 18:15Z beat ran.** Two consecutive misses is not a deploy artifact.
And the 24h counter corroborates it independently: **10 recorded runs in 24 hours against an
hourly schedule** is a ~40% fire rate, not a healthy one.

**Why this matters more than it looks.** Convergence needs ~13 successful staged beats *in a row*
against a cursor that survives between them. The projection "~13 beats ⇒ ~13 hours" silently
assumed hourly firing. At the observed rate it is **~32+ hours at best**, and every extra hour of
wall-clock is more roster drift for `retain_planned_units` to absorb — the drift the design
tolerates *per beat* compounds against a build that takes days rather than hours to finish.

**So there are now TWO open questions, not one, and this is the newer one:**

1. does a banked unit survive into the next beat? (unobserved — no next beat occurred)
2. **why is an hourly beat firing ~40% of the time?** (new, and it gates question 1 from ever
   being answered)

Question 2 is plausibly the more urgent: a build that cannot converge because it never gets to run
looks exactly like a build that cannot converge because its cursor thrashes, and the two have
completely different fixes. Whoever takes this must distinguish them before changing code —
`heavy` queue depth/concurrency and beat-scheduler delivery are the first places to look, not
`calibration_staged_futures.py`.

---

## 1. Ruling 9 shipped; the published count reflects volume-proven trading

**Required proof:** the deployed well-traded definition reads source volume; before/after counts
**by source**; sources with no volume concept excluded; NULL published as UNKNOWN, never
"untraded"; a bumped population version; **both figures named** in the payload.

**Status: 🟡 RULED 2026-08-09 — the definition is settled; nothing is built.**

The A/B inference is **superseded and no longer load-bearing.** Alex ruled directly, and better
than either option: *"use volume when we have it, and infer volume from multiple price moves
otherwise."* Per-row, not per-source. Full text in PRODUCT-BRAIN § RULINGS 2026-08-09(b).

The published definition is an ordered ladder, each row carrying its provenance:

1. `volume_proven` — `volume` populated; traded iff `> 0`
2. `movement_inferred` — no volume, adequate observation density, `>= N` distinct price changes
3. `unknown` — neither; **published as its own count, never folded into "untraded"**

"Both figures named" = all three counts published, by source.

**Two things that make this real work rather than a predicate change:**

- **`price_moved` is not a move count.** It is `calibration_probability IS DISTINCT FROM
  opening_probability` — closed-away-from-open. A market that traded all day and returned to its
  open reads as untraded today. Tier 2 must be built fresh from `futures_odds_snapshots`
  (`outcome_id`, `probability`, `captured_at`).
- **Tier 2 is density-gated.** 3 snapshots can yield at most 2 moves however much a market traded;
  calling that untraded is gotcha #53's shape. Below the threshold: `unknown`.

**N is measured, not chosen.** On rows carrying BOTH volume and adequate snapshots, measure how
well `>= N moves` predicts `volume > 0`. That fixes N and yields a publishable precision figure.
A weak proxy is a finding to report, not a number to ship.

**Owed before staging:** the overlap census above (volume coverage by source × snapshot density ×
move counts). Read-only, one bounded rail, no ruling needed.

### The overlap census cannot be hand-measured — it needs a rail (measured 2026-08-09, window `b2e4`)

This was attempted directly and **the tier-1 half works while the tier-2 half is unreachable
through `db-query`**. Recording the measured costs so the next window does not re-derive them:

| query | window | result |
|---|---|---|
| volume coverage on the resolved priced population | 5M ids | ✅ **1.09 s** — 20,117 outcomes, 843 with `volume` (4.2%), 797 with `volume > 0` |
| population count alone, no snapshot join | 100K ids | ✅ 0.77 s |
| `LAG()` move-count over `futures_odds_snapshots` | 5M ids | ❌ statement timeout (10 s) |
| same | 500K ids | ❌ statement timeout |
| same | **100K ids** | ❌ statement timeout |
| bare `COUNT(*) FROM futures_odds_snapshots WHERE outcome_id < 100000` | 100K ids | ❌ **statement timeout** |

The last row is the decisive one: **a bare `COUNT(*)` over a 100K-id slice of
`futures_odds_snapshots` exceeds the timeout**, with `idx_fos_outcome_captured` present. Shrinking
the window does not help because the window is not the cost — the snapshot table is. This is not a
data finding and it is **not** the pre-declared PREMISE-BROKEN condition (which is about too few
rows carrying both signals); it is purely a tooling bound.

**So tier 2 is blocked on the same thing CAL-P018 was blocked on, and has the same answer:** build
it as a rail. `POST /api/admin/repairs/prop-threshold-cliff-census` exists precisely because a
population measurement that only a lucky window can run is anecdotal rather than published. The
overlap census needs the identical treatment — a bounded outcome-ROW walk returning
`(has_volume, snapshot_count, move_count)` cohorts with `next_offset`/`exhausted`.

**Early signal, one window only, do not generalise:** volume is populated on just **4.2%** of the
oldest resolved priced slice. If that rate holds across the population, tier 1 (`volume_proven`)
covers very little on its own and the ladder's weight falls almost entirely on tier 2 — which
makes measuring N *more* load-bearing, not less. One 5M-id window out of ~44 is not a population
estimate; the rail must produce the real number.

---

## 2. Trading-activity section led by the matched-bucket comparison

**Required proof:** the rendered `/calibration` section leads with the matched-bucket comparison;
the raw cross-cohort tiles are demoted or removed. Browser evidence, not source.

**Status: 🔴 not started. Unblocked — stageable today.**

**Why the current tiles mislead, measured.** The section compares moved vs not-moved as two
aggregate cohorts. Those cohorts have different predicted-probability *distributions*, so the
difference between their headline numbers is partly composition, not partly-nothing-to-do-with
trading. Split by bucket (published payload, 2026-08-02) the picture is different and much
narrower:

| bucket (pred) | moved=False err | moved=True err |
|---|---|---|
| 0 (4%) | −0.1pp | −0.7pp |
| 3 (35%) | −0.9pp | −2.7pp |
| 4 (45%) | −1.4pp | **−5.7pp** |
| 5 (53%) | −1.6pp | −1.1pp |
| 6 (65%) | +2.3pp | +1.4pp |
| 7 (74%) | +2.3pp | +2.1pp |
| 9 (95%) | +0.6pp | −1.0pp |

Within a bucket the two are mostly within ~1–2pp of each other. The one real signal is the
**mid-band 35–50%**, where traded outcomes over-predict noticeably more than untraded ones. That
is a genuine, specific, publishable finding — and it is exactly what the cross-cohort tiles bury.

**This is the answer the section should lead with.** The work is to compute it server-side and
render it, not to discover it.

---

## 3. Cricket and entertainment — a named diagnosis each

**Required proof:** per cohort, one of — a shipped fix with before/after, a documented exclusion
carrying its published count (the standing house rule), or a demonstrated "the market is
genuinely bad here". No massive-error category left unexplained.

**Status: 🟡 measured, not diagnosed.** Both were surfaced by the 2026-08-09 09:11 PT window's
analysis of the published payload.

### polymarket cricket — wECE 9.38pp, n=3,003

Worst bucket: **pred 52% → act 81%** (n=608). Under-prediction in the mid band, which is the
opposite direction to most defects in this product and therefore unlikely to be the usual
settlement-collapse artifact.

Leading hypothesis to test first: two-outcome cricket markets where the favourite is
systematically mispriced, or a resolution-source asymmetry. **Untested.**

### kalshi entertainment — wECE 5.87pp, n=9,489

Worst bucket: **pred 95% → act 70%** (n=914). A high-band collapse — priced near-certain,
resolves 70%.

**That shape is the strongest lead in the exam.** It is the same signature as the Kalshi
prop-threshold settlement-collapse band (a settled post-game quote stamped as the line, resolving
far below its price), which the curve already excludes for player props via
`KALSHI_PROP_THRESHOLD_DEGENERATE_BAND` (>= 0.90). If entertainment is the same mechanism in a
different series family, the honest answer is a documented exclusion with its count — not a
recalibration. If it is *not*, that is a real miscalibration and more interesting.

Distinguishing them is a bounded query: for the 914 outcomes in that bucket, does the price move
before settlement, or is it a single stamped quote? **Needs a fresh prod window.**

---

## 4. Source graph redesigned — per-source panels, not overlaid lines

**Required proof:** rendered screenshot of the redesigned `/calibration` graph. Browser evidence.

**Status: 🔴 not started. Unblocked — stageable today.**

The legibility problem is quantifiable from the payload: the five sources differ by **28x in n**
(kalshi 420,594 · polymarket 191,738 · odds_api 14,960 · odds_api_totals 12,705 · odds_api_spreads
12,410) and by **3.3x in ECE** (kalshi 0.82pp · polymarket 2.72pp). Overlaid on one axis, the two
large sources dominate and the three sportsbook curves are unreadable — and the one comparison
that matters most (kalshi vs polymarket) is the hardest to see.

Per-source panels with a shared axis let a reader see both the shape and the size difference.

---

## 5. Native calibration surface consistent with web

**Required proof:** side-by-side — native surface and web `/calibration` showing the same
population version, the same generated-at, and the same headline figures. Rendered on both.

**Status: 🔴 not green — but the flagged RISK is likely a false alarm (source read, 2026-08-09).**

**The specific fear was:** web renders the stale-tier banner (`data-cache-status`, "as of <time>
(N ago)"); if native does not, then during the current outage **native is showing a week-old curve
as current** — a "settled means settled"-class honesty failure on a second surface.

**In source, native already handles it:**

- `ViewModels/CalibrationViewModel.swift` — `isStale` (`data?.cache?.isStale == true`);
  `staleBannerDetail`, which *deliberately* falls back to the payload's own `generated_at` and then
  to a bare "earlier", so a stale payload whose envelope omits the date still banners rather than
  silently dropping it; `ageS` formatting; and a `populationVersionState` carrying an explicit
  `.mismatched` case.
- `Views/CalibrationView.swift:107` renders `staleBanner; refreshFailureBanner;
  partialDataBanner`, under the comment *"A stale curve is fine; a stale curve presented as live
  is not."*

**This does not make item 5 green.** The required proof is rendered side-by-side evidence that
native and web show the same population version, the same generated-at and the same headline
figures — that still needs the `xcodebuild` gate (gotcha #50) and a screenshot. But whoever takes
it should expect to be **confirming correct behaviour, not finding a live bug**, and budget
accordingly. The item is cheap and needs **no production credentials**, so it can run in any
window, including a tainted one.

Native gate: the canonical `xcodebuild` invocation, with `OTHER_SWIFT_FLAGS='$(inherited)
-Xfrontend -disable-sandbox'` (gotcha #50).

---

## 6. Monitoring proven by drill — observed firing, not merely merged

**Required proof:** the publish-age watchdog observed producing an alert with the failing phase
attached; the sentinel guards observed executing. Linked run output, not a merge SHA.

**Status: 🟢 WATCHDOG HALF PASSED — observed firing in production, 2026-08-09.**

**The drill was caught while the conditions were still live**, which was the time-sensitive part.
The check fired on its own, unprompted, against a genuinely broken publish.

**Proof — GitHub issue [#1604](https://github.com/alexander-bain/bainluck/issues/1604)**, filed
`2026-08-09T16:46:39Z` (09:46 PT), the FIRST live firing of the check:

| what Alex asked for | what production did |
|---|---|
| fires when a publish stops working | ✅ value **181.36 hours** against threshold `2` (`lte`) — 90x over |
| within ~2 hours | ✅ deployed ~08:47 PT, fired 09:46 PT, on its own schedule |
| auto-files a **P1** | ✅ labels `priority:p1`, `needs-agent`, `alert-intake` |
| **names the failing phase** | ⚠️ **partly** — see the gap below |
| doesn't spam | ✅ exactly one issue; the 24h Redis dedup held across ~12 runs |

The body's Evidence block named `terminal: cancelled`, `published: false`, **`phase: futures`**,
`phase_status: cancelled`, `duration_ms: 726557`, plus the four downstream phases as `pending`.

**The gap, and it is a real one.** CAL-P017 promised the issue would say *"phase futures, stage
`read:futures_population`"*. Production printed **`detail: ''`** and no stage at all, because:

- a phase **cancelled** by the build's own budget writes no `detail` (only a phase that dies on a
  statement timeout does — and since CAL-P016 the failure mode changed from timeout to
  cancellation, so the detail field went quiet exactly when the fix landed); and
- **the stage breakdown was never in `phases[]` to be read.** `record_stage` accumulates into a
  **top-level `stages` map**, so no query over `phases[]` could ever have named a stage.

Fixed in **CAL-P023**: the `context_query` now UNIONs the top-level `stages` map, ordered by cost.
On today's ledger that turns the alert from *"futures was cancelled"* into *"it spent 626s in
`read:futures_unit` and hit `staged:cursor_invalidate`"* — and that cursor line is the one that
distinguishes a build that is merely slow from one that is not converging.

**Verdict: the monitoring works.** It caught a real outage unprompted and routed it correctly;
the diagnosis was one level shallower than promised and is now deeper than promised.

The sentinel-guards half is **plumbing lane #1548** (ALEX-DECISIONS 2026-08-08 §4), routed there
by CAL-P017 Item 3 and explicitly out of this lane. The exam needs its evidence; the calibration
lane does not produce it.

---

## 7. Backfill recovery measurably progressing vs the 786K recoverable cohort

**Required proof:** two dated measurements of the recoverable cohort showing it shrinking, plus
the capture-floor re-measure on ~2026-08-15.

**Status: 🟡 BASELINE ESTABLISHED 2026-08-09 — the first datapoint now exists.**

### Baseline — reachability census walked to EXHAUSTION, 2026-08-09 10:47 PT, window `b2e4`

`POST /api/admin/repairs/reachability-census`, 7 calls, `exhausted: true`, `partition_ok: true`,
`partition_residual: 0`, `purge_horizon_days: 86`. Read-only rail; nothing was written.

| tier | outcomes | share |
|---|---|---|
| priced, in coverage | 1,672,620 | 58.58% |
| provably purged upstream (past the 86d horizon) | 384,820 | 13.48% |
| **unpriced but RECOVERABLE** | **797,871** | **27.94%** |
| unpriced, unknown age | 2 | ~0% |
| **total resolved outcomes** | **2,855,313** | 100% |

The four tiers sum to the population **exactly** (`partition_residual: 0`), so this is a
partition, not a sample — the census accounts for every resolved outcome it walked.

**This replaces "786K" with a measured number: 797,871.** That is the denominator item 7 must be
shown shrinking against. It also sets the honest ceiling on recovery: **13.48% of the resolved
population is provably gone** (gotcha #35's retention cliff) and can never be recovered by any
rail — so the achievable target is the 797,871, not the 2.86M.

**What item 7 still needs: a SECOND dated measurement.** "Measurably progressing" is a
derivative, and one point has no slope. The rail is cheap (7 calls, ~3 min) and re-runnable by
anyone, so the next window should simply re-run it and record the delta.

Two things gate actual recovery:

- **The largest recoverable prize needs a ruling.** 273,438 resolved Polymarket outcomes across
  ~133,576 markets carry no `resolution_source` at all, and **90.1% already have a calibration
  price**. CAL-P003 found both root causes (a candidate predicate that excluded the whole class —
  `bool_or` over all-NULL is NULL, never TRUE — and a Gamma **422** on `0x…` condition_ids
  misread as a rate limit, tripping the circuit breaker every run). **Nothing has been written;
  it needs Alex's authorisation before any recovery write.**
- **The capture-floor re-measure (#1586) waits on elapsed time**, ~2026-08-15 by Alex's date.

**AUTHORISED 2026-08-09 — bounded pilot.** Alex ruled: grade a capped batch (~5K outcomes),
attended, then **measure the effect on the published Polymarket curve and report before going
further**. Rationale: a full run could more than double the Polymarket curve (191,738 today), and
Polymarket is the worst-calibrated source — that is measured on 5K, not discovered on 246K.

The pilot must report: before/after ECE by bucket, the cleanly-resolvable vs ambiguous split
(sample says ~64.3% clean), and the disposition of the ~36% that do not resolve cleanly.

**First action, and it needs no ruling:** run the reachability census to exhaustion and publish
the baseline. It is a read-only rail that is already deployed, and without it there is no first
datapoint for "measurably progressing" to be measured against.

---

## Evidence log

Every claim above traces to a dated measurement. Add rows; never edit one.

| date (PT) | window | measurement | where |
|---|---|---|---|
| 2026-08-09 09:11 | c3f7 | `/api/calibration` 200 in 0.56s, `cache.status="stale"`, `reason="durable_over_age"`, `age_s=650830` | CAL-P020 report |
| 2026-08-09 09:11 | c3f7 | deployed `b4aa0039`; `calibration:main` last published 2026-08-02T03:23:54Z | CAL-P020 report |
| 2026-08-09 09:20 | c3f7 | staged cursor advancing — 4/128 units, `terminal=partial`, gen `5030f8f5` | CAL-P020 report |
| 2026-08-09 09:11 | c3f7 | per-source ECE: kalshi 0.82 · polymarket 2.72 · odds_api 1.35 · totals 1.10 · spreads 0.67 | payload `by_source` |
| 2026-08-09 09:35 | c3f7 | cohort ranking by error mass; cricket 9.38pp/n=3,003; entertainment 5.87pp/n=9,489 | items 3, 4 above |
| 2026-08-09 09:35 | c3f7 | matched-bucket `price_moved` split | item 2 above |
| 2026-08-09 10:36 | b2e4 | deployed `75dfee56` (INT-024); `prop-threshold-cliff-census` now live in `/api/admin/repairs` — CAL-P018's rail is deployed, unblocking CAL-P019 Item 0 | `/api/health`, `/api/admin/repairs` |
| 2026-08-09 10:36 | b2e4 | `/api/calibration` **200 in 0.98s**, `cache.status="stale"`, `age_s=655929` (7.59d) — CAL-P017's dated tier still carrying the page | payload `cache` |
| 2026-08-09 10:36 | b2e4 | publish still `2026-08-02T03:23:54Z`; census `status: "unavailable"`, `reason: "payload_predates_census"` | payload |
| 2026-08-09 10:40 | b2e4 | **watchdog drill PASSED** — issue #1604 filed 09:46 PT, value 181.36h vs threshold 2, P1 + `alert-intake`, one issue only; phase named, `detail` EMPTY, no stage | item 6; [#1604](https://github.com/alexander-bain/bainluck/issues/1604) |
| 2026-08-09 10:44 | b2e4 | ledger: `terminal=cancelled`, `plan.status=infeasible`, `floor_ms=1352317` over 10 observations (9 stale monolith timeouts + 1 staged run) | item "CAL-P016 convergence" |
| 2026-08-09 10:46 | b2e4 | ledger `stages`: `read:futures_unit` 626,242ms · `read:futures_generation` 25,752ms · **`staged:cursor_invalidate`** — one staged beat only, cross-beat retention UNOBSERVED | ibid. |
| 2026-08-09 10:47 | b2e4 | **reachability census to EXHAUSTION** — 7 calls, `partition_ok`, residual 0: 2,855,313 resolved · 1,672,620 priced · 384,820 purged · **797,871 recoverable** | item 7 |
| 2026-08-09 10:52 | b2e4 | volume coverage, 5M-id window: 20,117 resolved priced · 843 with `volume` (4.2%) · 797 `>0` | item 1 |
| 2026-08-09 10:52 | b2e4 | move-count over `futures_odds_snapshots` times out at 5M / 500K / **100K** ids; bare `COUNT(*)` on a 100K-id slice ALSO times out ⇒ tier 2 needs a rail | item 1 |
| 2026-08-09 10:53 | b2e4 | winner-field-coherence dry run, first 50K markets: 811 defects (`incoherent_field` 701 · `multi_winner` 142); politics 606 total but only **8** multi_winner | specimens above |
| 2026-08-09 11:15 | b2e4 | native DOES implement the stale banner in source (`isStale`, `staleBannerDetail`, `populationVersionState.mismatched`) — item 5's flagged honesty risk is likely a FALSE ALARM; rendered proof still owed | item 5 |
| 2026-08-09 11:20 | b2e4 | **the beat is NOT firing hourly** — watched 16:27Z→18:20Z: `failures_24h` stuck at 10, ledger generation stuck at 16:15:00Z, cursor stuck at 10 units @ 16:26:24Z. NEITHER the 17:15Z nor the 18:15Z beat ran | CAL-P016 convergence |

## Open questions for Alex

**All three are ANSWERED as of 2026-08-09** (PRODUCT-BRAIN § RULINGS 2026-08-09(b)):

1. ~~Ruling 9 = Option A?~~ → **Ruled directly**, and more precisely than A: the volume /
   hardened-movement / unknown ladder. The inference is retired, not confirmed.
2. ~~Polymarket recovery write?~~ → **Bounded pilot first** (~5K, attended, curve impact reported
   before going further).
3. ~~Three-winner scope?~~ → **Pause; 10 eyeballed specimens per category first.** Plus the lane's
   own correction: the 1,885 multi-winner extension was already granted on 2026-08-08, and the
   3,585 figure mixes in `incoherent_field` (bad PRICES), which the winner rail cannot fix at all.
   **→ SPECIMENS DELIVERED 2026-08-09, below. Alex's call is now unblocked.**

---

## Specimens for Alex — the winner-field defects (#1527), 2026-08-09 window `b2e4`

`POST /api/admin/repairs/winner-field-coherence?limit=200000`, **dry run, nothing written.**
First 50,000 markets walked (`next_offset` 5,990,949 — this is a leading slice, not the
population): **811 defect markets**, `incoherent_field` 701 · `multi_winner` 142.

### The split Alex's politics concern turns on

| category | ALL defects | of which `multi_winner` |
|---|---|---|
| **politics** | **606** | **8** |
| basketball | 54 | 51 |
| entertainment | 31 | 16 |
| soccer | 24 | 10 |
| tennis | 20 | 20 |
| economics | 15 | 12 |
| golf | 8 | 8 |

**Politics is 75% of all defects and 5.6% of the actionable ones.** The 606 politics rows are
almost entirely `incoherent_field` — bad *prices* — which the winner rail cannot fix and does not
touch. Only **8** politics markets are `multi_winner`. The rail additionally fails closed (it
writes only where the CLOB returns exactly one winner), so politics is protected twice over.

### Specimens — genuine single-winner markets carrying multiple winners

`legs` = outcomes, `win` = outcomes flagged `is_winner`, `sum` = field probability sum.

**basketball** (51) — 3-leg first-half markets with 2 winners; prices sane, winners wrong:
| mkt | legs | win | sum | name |
|---|---|---|---|---|
| 949075 | 3 | 2 | 1.985 | New Mexico vs Nevada: First Half Winner |
| 949109 | 3 | 2 | 1.54 | Auburn vs Oklahoma: First Half Winner |
| 949199 | 3 | 2 | 1.60 | Marquette vs Georgetown: First Half Winner |
| 1193982 | 3 | 2 | 1.90 | Florida vs Texas: First Half Winner |
| 460 | 68 | 3 | 3.65 | Women's Championship: South Carolina vs UCLA |

**politics** (8) — large fields where ~all legs are flagged winner AND priced ~1.0:
| mkt | legs | win | sum | name |
|---|---|---|---|---|
| 112920 | 26 | 21 | 21.0025 | Next Prime Minister of Hungary |
| 114000 | 37 | 28 | 28.0105 | Assam Legislative Assembly Election Winner |
| 114010 | 37 | 28 | 28.0045 | Kerala Legislative Assembly Election Winner |
| 5973861 | 14 | 13 | 13.00 | Next President of Benin |

**tennis** (20) · **entertainment** (16) · **economics** (12) · **golf** (8):
| mkt | legs | win | sum | name |
|---|---|---|---|---|
| 114033 | 61 | 28 | 28.04 | 2026 Men's Australian Open Winner |
| 2954775 | 4 | 4 | 2.00 | Zizou Bergs vs Tommy Paul: Exact Match Score |
| 113177 | 37 | 28 | 28.009 | Most popular boy name 2025 |
| 3649032 | 15 | 15 | 7.425 | Top Global Song on Spotify on Mar 10, 2026? |
| 1460213 | 30 | 2 | 3.00 | S&P price range on Feb 26, 2026 at 4pm EST? |
| 2622557 | 40 | 40 | 19.80 | Steel price on Mar 31, 2026 at 5pm EDT? |
| 110593 | 147 | 55 | 51.385 | Kenya Open End Of Round 1 Leader |

### The finding worth Alex's attention: these are TWO different bugs

- **Signature A — "the whole field got graded true."** `winners ≈ field_sum` to two decimals
  (21/21.0025 · 28/28.0105 · 13/13.00 · 40/19.80's cousins). Every flagged leg is *also* priced
  ~1.0, so both the winner flag and the price were mass-set. Dominates politics, entertainment
  and the big tennis/golf fields.
- **Signature B — "one extra winner on a sane field."** 3 legs, 2 winners, `sum` ≈ 1.5–2.0. The
  prices are believable; only the winner flags are wrong. Dominates basketball/soccer first-half
  and the small tennis markets.

**These plausibly need different fixes**, and the ladder currently treats them as one cohort.
Signature B is the clean case for CLOB re-resolution. Signature A markets are *also* carrying
impossible prices, so re-resolving the winner alone leaves a field summing to 21.0.

**Alex's decision is now unblocked.** Nothing has been written; the rail remains paused.

Nothing is currently blocked on Alex. Every remaining item is blocked on a fresh production window,
on the publish converging, or on elapsed time.

### The one thing that would change this

If N turns out unmeasurable — i.e. too few rows carry BOTH volume and adequate snapshot density to
validate the proxy — then tier 2 has no empirical basis and item 1 comes back with a real choice
(ship tier 1 + unknown only, or keep the old bar). Flagged now so it is not a surprise later.
