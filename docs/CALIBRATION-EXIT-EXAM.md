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
| 1 | Ruling 9 shipped; published count reflects volume-proven trading, both figures named | 🟡 **RAIL BUILT 2026-08-09 (CAL-P027)** — the overlap census this item named as *owed before staging* exists on `program/calibration-25`; **N is still unmeasured** because the rail runs in the web dyno and has not been walked | the merge, then one walk; then a healthy publish for the bump |
| 2 | Trading-activity section led by matched-bucket comparison | 🟡 **BUILT 2026-08-09 (CAL-P025)** — shipped on `program/calibration-23`, pinned by test to the real payload | rendered proof; needs the merge + the browser rail |
| 3 | Cricket + entertainment diagnosed to fix / exclusion / "genuinely bad" | 🟡 **CRICKET DIAGNOSED 2026-08-09** — cause identified and it confirms this document's own hypothesis; the FIX is an exclusion extension, blocked behind the version bump. Entertainment still has a live rival | cricket: the publish (bump). entertainment: one walk of CAL-P027's rail |
| 4 | Source graph redesigned — per-source panels | 🟡 **BUILT 2026-08-09 (CAL-P025)** — shipped on `program/calibration-23` | rendered proof; needs the merge + the browser rail |
| 5 | Native calibration surface consistent with web | 🟢 **PASSED 2026-08-09 (CAL-P026)** — rendered on both, every headline figure identical, both banner the staleness | — |
| 6 | Monitoring proven by drill — watchdog + sentinel guards observed firing | 🟢 **WATCHDOG HALF PASSED 2026-08-09** — observed firing, issue #1604 | sentinel half is plumbing #1548 |
| 7 | Backfill recovery progressing vs 786K recoverable; capture-floor re-measure ~Aug 15 | 🟡 **BASELINE ESTABLISHED 2026-08-09** — 797,871 recoverable, measured to exhaustion | a second dated measurement; ~Aug 15 |

**Two items are green** (5, and 6's watchdog half). Item 7 has its first datapoint. Items **2 and
4 are built** (CAL-P025) and wait only on being merged and photographed. **Item 1's rail is built**
(CAL-P027) and item **3's cricket half is diagnosed**.

**Nothing on this exam is now unblocked and unstarted.** Every remaining item waits on the publish
converging (1, 3, 7), on a merge plus a capture (2, 4), on elapsed time (7), or on another lane
(6's sentinel half, #1548). That is a different state from every previous cycle, and it means the
lane's throughput is no longer the binding constraint — **`calibration:main` publishing again is**,
which is CAL-P024's payoff and is sitting unmerged in the Integrator's queue.

**Updated 2026-08-09 by CAL-P027 — and the state CHANGED mid-queue, in the good direction.** Both
readings are kept, because the second one is only interpretable against the first.

At **21:39 PT** the publish was **8.05 days** stale (a sixth consecutive rising reading) and
CAL-P024 was *still unmerged*, confirmed by content rather than by a handoff file: `origin/master`
carried `COVERAGE_CENSUS_ENABLED = True`, the exact line CAL-P024 flips.

At **22:45 PT**, while this queue was in its gates, **CAL-P024 merged and deployed** — master
`ff627a39` (as CAL-P024a/b/c against #1479), `/api/health` reports `ff627a39`, and
`COVERAGE_CENSUS_ENABLED = False` is live. **So ruling 009's baseline has now landed and the
~13-beat convergence count can start for the first time.** A unit should cost ~62.6 s again rather
than ~632 s.

**What that does and does not mean.** It does not make the publish fresh — as of this writing
`generated_at` is still `2026-08-02T03:23:54Z`, and it stays that way until the build actually walks
128 units. **The lane's one product-visible SLO — `/api/calibration` serving a payload under 24h old
— is still RED**, and the next window's first job is to read whether `staged:cursor_resume` appears
with `committed_units` climbing, and whether `staged:beats_to_publish` (new in CAL-P024) names a
finite number. Ruling 009 lifts on two recorded observations, not on this merge.

**The freeze is still on.** Its lift condition is a fresh post-CAL-P024 publish *plus* ~13 clean
beats, recorded. Nothing above satisfies either half yet.

Three of the seven items still reduce to one sentence: **merge the queue.** Items 2 and 4 need the
merge plus a photograph; item 1 needs the merge plus one walk of the rail below. Item 3's cricket
fix now needs only the publish to converge. The lane has run out of work that does not route
through the Integrator or through the beat — which is the correct place for it to run out, and
worth saying plainly rather than letting a fifth diagnostic rail be invented to fill the time.

### Why items 2 and 4 were taken while the build is dark — the reason generalises

Every other unblocked item on this exam is waiting for `/api/calibration` to publish again, and
CAL-P020's report already named the pattern that creates: **deploying is not publishing.** Three
shipped read-side improvements (CAL-P011's reachability tier, CAL-P012's purged count, CAL-P014's
denominator) each recorded a payoff "owed post-deploy" that could not arrive, because a payload
change is invisible until a build succeeds.

Items 2 and 4 are the two items that escape that, and it is a property of the data rather than of
the work: **both are computable from the payload that is already published.** `buckets` is a
1,606-row array carrying `source`, `category`, `bucket_idx`, `price_moved`, `n`, `winners` and
`sum_prob` on every row, so the matched comparison and the per-source panels are re-groupings of
bytes production has already served since 2026-08-02. No backend change, no population-version
bump, no publish, and — the part that matters most right now — **no edit to
`precompute_calibration.py`**, whose hashed functions reset the staged cursor on every touch.

That last point is a lane-wide constraint CAL-P024's rate-mismatch finding implies and nobody had
written down: the build needs ~13 consecutive uninterrupted beats to converge, and the file has
taken ~1.8 commits/day for two weeks. **Until the curve publishes, work that touches the
precompute is work that prevents it from publishing.** Items 2 and 4 were the right work partly
because they are the right work, and partly because they are off that critical path.

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

### ✅ THE DECISIVE READ WAS TAKEN — 2026-08-09 19:11–19:18Z, window `4a9d`. It is the second answer.

The section above set the test. **The build is thrashing, and the cause is this lane's own last
merge.**

**First, a correction to the section below it.** Window b2e4 stopped watching at **18:20Z**; the
18:15Z beat committed its first unit at **18:22:22Z** and wrote its ledger at **18:27:03Z**. So the
beat it concluded had never fired had in fact fired, two minutes after it looked away. The "~40%
fire rate" therefore rests on one confirmed miss (17:15Z, straddling the INT-024 restart) and one
mis-read. It is not established. Acting on it — `heavy` queue depth was the recommended first
place to look, and reads **0** — would have been a cycle spent on a phantom.

| question | answer |
|---|---|
| did a second staged beat run? | ✅ **yes** — generation `1786299300221` = 18:15:00Z |
| did the banked unit survive? | ❌ **NO** — `staged:cursor_invalidate` again; `committed_units` **10 → 1** |
| why? | **`input_fingerprint` moved.** CAL-P020 edited `_main_futures_sql` and `_calibration_population_ctes` — two of the four functions `_main_input_fingerprint` hashes by `inspect.getsource`. INT-024 deployed it ~17:11Z. |
| per-unit cost | 16:15Z, census OFF: **62.6 s/unit**. 18:15Z, census ON: **632 s/unit**. |

**CAL-P020 flipped `COVERAGE_CENSUS_ENABLED = True` and made every unit ~10x more expensive.** At
62.6 s/unit the 128-unit build is ~2.2 h ≈ 13 beats. At 632 s/unit it is **~22.5 h of compute**
against a ~687 s usable window per beat — **~117 more beats**, over five days of unbroken hourly
beats.

It cannot get five days. **`precompute_calibration.py` took 25 commits in the 14 days to
2026-08-09 (~1.8/day)**, and any one touching a hashed function resets the cursor to zero. **The
build's convergence time now exceeds the lane's own edit interval by an order of magnitude.** That
is a rate mismatch, not a cursor bug: CAL-P016's per-unit retention works exactly as designed and
cannot help while a unit costs ten minutes.

**Say the shape of this plainly, because it is the second occurrence.** CAL-P020 exists because
CAL-P016 had made the census unbuildable; it fixed that by making the curve unpublishable. Two
correct decisions composing into a dark surface — the same pair of switches, eight days apart,
each guarded by a rule that correctly said "do not touch the other thing".

**Fixed in CAL-P024** (`program/calibration-22`): the switch goes back off on the measured budget,
with the numbers written beside it; the switch joins the fingerprint (flipping it changed the
statement but *not* the digest, so units built under two different statements were mutually
resumable); the ledger names *which* of five causes reset the cursor; and every beat now records
`staged:beats_to_publish`, so "slow" and "never" stop looking alike.

**Still genuinely open — do not treat as answered:** the 19:15Z beat produced no ledger and no
cursor write for 23+ minutes (watched to 19:38Z), against 12 minutes for 18:15Z. So beats *are*
intermittently missing; the rate is unmeasured and the cause unknown. `heavy` queue depth is 0 and
`background` is **442** (documented threshold: 50) — the latter is an ops finding, not this lane's.

### ⚠️ Superseded — the original "beat is NOT firing hourly" reading

Kept for the record; corrected above. Observed 16:27Z → 18:20Z:

| observation | 16:36Z | 18:20Z |
|---|---|---|
| `precompute_calibration_main.failures_24h` | 10 | **10 — unchanged** |
| ledger generation | 16:15:00Z | **16:15:00Z — unchanged** |
| cursor `committed_units` / `updated_at` | 10 @ 16:26:24Z | **10 @ 16:26:24Z — unchanged** |

Read as "neither the 17:15Z nor the 18:15Z beat ran". The 18:15Z half is now known to be a
two-minute-early read. **The lesson is worth more than the datum: this lane's projections have twice
turned on a snapshot taken just before the thing it was waiting for.** A negative observation about
a periodic process needs a margin past the full period, and should say what margin it used.

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

### ✅ RAIL BUILT — CAL-P027, 2026-08-09, `program/calibration-25`

`backend/app/tasks/census_overlap_trading.py`, registered as `overlap-trading-census` on the repair
rail. Bounded outcome-row walk, `next_offset`/`exhausted`, never writes. Per
`(source, category, volume_state, density band, move band)` it returns outcome counts, snapshot
rows, observations and distinct price moves; `precision_for_threshold()` then scores `>= N moves`
as a predictor of `volume > 0` on the overlap population. 95 tests, 12 mutations.

**Why this was the one item-1 move available.** Ruling 011 is staged as ruling 009's freeze-lift
successor *specifically so no days are lost when the freeze lifts* — but it cannot execute without
N, and N is measured, not chosen. Had the rail not existed when the freeze lifted, the lane would
have started the measurement on that day, which is the exact outcome that staging was meant to
prevent. The rail is off the frozen file entirely (it imports the truth allowlist from
`app/utils/resolution_authority.py`, its real home, not from `precompute_calibration.py`).

**Three design findings that would each have produced a plausible, publishable, wrong N.** Recorded
because the failure mode here is not a crash, it is a number that looks fine:

1. **Snapshots are per-bookmaker.** Ordering an outcome's snapshots by `captured_at` across books
   and counting changes fabricates a move at every cross-book quote difference. Counted
   `PARTITION BY (outcome_id, bookmaker)`, folded across books with **`MAX`, not `SUM`** — ruling
   011's own "strongest evidence available"; summing multiplies a market's evidence by its book
   count. (Mitigating, measured: `odds_api` holds **12** futures markets against polymarket's
   553,876 and kalshi's 191,114, so the multi-book case is rare — but rare is not absent.)
2. **DataGolf dedups at write time; nobody else does.** It increments `reading_count` on a repeated
   reading. So `COUNT(*)` is not observation density: an outcome with one row and fifty readings is
   not sparse — we looked fifty times and it never moved, which is *evidence of no trading*, the
   opposite of the unknown ruling 011 forbids reading as thinness. Density is `SUM(reading_count)`.
3. **`volume = 0` did not occur once** across three sampled windows (8,509 / 2,759 / 2,560 eligible
   outcomes) — every row carrying volume carried `volume > 0`. If that holds at population scale it
   is a finding about **ruling 011 itself**: tier 1 never classifies anything as *untraded*, only as
   proven-traded or unknown, and the ladder's entire negative side rests on tier 2. The rail counts
   the three states separately so this is published rather than assumed.

**Volume coverage is not one number** — 14.2% (recent 550K ids) · 4.5% (mid) · 4.2% (old tail, from
the row above). The exam's own "one window is not a population estimate" caveat is upheld, and the
spread is already visible at n=3.

**N IS STILL UNMEASURED, and that is the honest state.** The rail runs in the web dyno, so its first
walk is owed post-merge — the same shape as CAL-P018, whose rail shipped in one cycle and was walked
in the next. `precision_for_threshold` returns `supported: False` with a reason rather than a number
when the overlap is too thin or the threshold splits a band; per this item's pre-declared
PREMISE-BROKEN handling, that outcome returns N to Alex as a real choice. **Do not let a later
window read a refusal as a zero.**

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

**This is the answer the section should lead with.** The work is to compute it and render it, not
to discover it.

### ✅ BUILT — CAL-P025, 2026-08-09, `program/calibration-23`

**Correction to this item's own staging note, worth stating because it changed the plan.** The
line above said "compute it server-side". That is wrong, and wrong in a way that would have been
costly: server-side means editing `precompute_calibration.py`, which resets the staged cursor
(CAL-P024) and would have pushed the publish further away in order to render a section about
honesty. The whole comparison is derivable **client-side from the published payload**, because
every bucket row already carries `bucket_idx`, `price_moved`, `n`, `winners` and `sum_prob`.

What shipped:

- `compareMatchedBuckets()` in `frontend/lib/calibrationMath.ts` — the matched roll-up, living
  beside `describeActivityComparison`, whose own comment diagnosed the composition problem
  ("C111 [P2] showed this aggregate is composition sensitive") and then correctly declined to act
  on it. This is that diagnosis treated.
- The `/calibration` trading section now **leads** with the per-bucket table; the two cross-cohort
  ECE tiles are **demoted to supporting detail under "The overall split"**, not deleted — they
  are still the honest aggregate, they were just never the headline.
- New rail hooks: `calibration-matched-buckets`, `calibration-matched-sentence`,
  `calibration-matched-row` (with `data-comparable` and `data-gap-pp` per row),
  `calibration-matched-unavailable`.

**The finding is now pinned by test against the frozen production payload**
(`__tests__/lib/calibrationMatchedBuckets.test.ts`, 23 tests), so a regression changes a number in
CI rather than quietly on the page: bucket 4 = **−5.7pp moved vs −1.4pp unchanged, a 4.3pp gap on
75,583 outcomes**, and **9 of 10 matched buckets land within 2pp of each other**. The partition
reconciles exactly — 349,310 moved + 263,022 unchanged + 40,075 not-applicable = 652,407.

Three rules the tests enforce, each proven non-vacuous by mutation:

1. **An absent side is a dash, never 0.0pp.** A bucket only one cohort reaches has no gap; showing
   "0.0" would manufacture an agreement out of missing data — gotcha #53's shape, in a table cell.
2. **Thin sides are shown but cannot carry the finding.** A 40-outcome bucket with a huge gap must
   not become the headline; the floor is the same 1,000 the curve fades dots at, and a test now
   pins the two to the same constant so the caption cannot drift from the behaviour.
3. **The sentence never claims a cause.** Same rule the aggregate comparison already holds itself
   to, asserted by regex.

**Still owed for GREEN: the rendered screenshot.** The required proof is browser evidence, and
local Chromium does not launch in an agent sandbox (confirmed again this window). The remote
`browser-audit.yml` rail grades **production**, which does not carry this branch, so the evidence
is genuinely obtainable only after the merge deploys.

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

### Free evidence nobody had collected — the `price_moved` split (CAL-P026, 2026-08-09 14:10 PT)

The published payload already carries `price_moved` on every bucket row, so the high-band cohort
can be split **without any new query at all**. Splitting kalshi entertainment's bucket 9:

| cohort | n | predicted | actual | error |
|---|---|---|---|---|
| `price_moved = true` | **816** | 95.1% | **67.5%** | **−27.5pp** |
| `price_moved = false` | 98 | 94.9% | 86.7% | −8.1pp |

**The collapse lives almost entirely on the MOVED side**, and the unchanged side is ~3.4x better
calibrated. That is consistent with the settlement-collapse mechanism rather than against it: a
settled post-game quote stamped as the closing line *is* a price that moved away from its opening,
so `price_moved` reads TRUE. (Stated explicitly because the intuition runs the other way — "a
single stamped quote" sounds like it should read as unchanged, and this window initially misread
it that way before checking what `price_moved` actually compares.)

It is **suggestive, not conclusive.** `price_moved` is `calibration_probability IS DISTINCT FROM
opening_probability` — it says a price moved, never *when*. The decisive question is whether the
close was captured after settlement, which needs snapshot timestamps and therefore still needs the
rail. What this does buy: a cheap, published discriminator that a future exclusion can be measured
against, and a reason to expect the answer to be an exclusion with a count rather than a
recalibration.

### polymarket cricket is ONE bucket, not a broad miscalibration

Same split, same payload. Cricket's 9.38pp/n=3,003 is concentrated, not diffuse:

| bucket | n | predicted | actual | error |
|---|---|---|---|---|
| b3 (34%) | **1,435** (48% of the cohort) | 33.6% | 33.7% | **+0.1pp** — well calibrated |
| b5 (52%) | 608 | 51.6% | 80.6% | **+29.0pp** |
| b2 (25%) | 263 | 25.6% | 9.5% | **−16.1pp** |

Nearly half the cohort sits in a well-calibrated bucket; the error mass is b5 (+29pp) with a
smaller opposite-signed b2 (−16pp). **Both directions appear on moved AND unchanged rows alike**
(b5: +30.7pp moved / +28.2pp unchanged), so unlike entertainment this one is *not* an artifact of
the closing-price capture — a defect that shows up equally regardless of whether the price moved
is a property of the population, not of the quote.

The bidirectional mid-band shape — a ~25% leg resolving ~10% and a ~52% leg resolving ~80% — is
what a **3-outcome market read as if it were 2-outcome** looks like: cricket carries draws /
ties / no-results, and a field whose third leg is systematically over-priced makes the other two
under-priced by the mirror amount. That is a concrete, falsifiable hypothesis and it is the first
one this exam has had for cricket. ~~**Untested**~~ — **TESTED AND CONFIRMED**, see below.

### ✅ CRICKET DIAGNOSED — 2026-08-09, window `7b21`; recorded here 2026-08-09 by CAL-P027

**The hypothesis directly above was right, and the confirming measurement already existed.** It was
taken by the window that exported the codex diagnosis bundle and, until now, lived only in
`.claude/handoff/CAL-DIAGNOSIS-BUNDLE-READY.md`. **Alex reads this document, not the handoff
directory** — so a confirmed diagnosis was sitting one directory away from the exam that calls it
untested. Recording it is the point of this entry; the measurement is not CAL-P027's.

| finding | figure |
|---|---|
| multi-winner 3-outcome cricket markets carrying a draw member | **0** of 556 markets (1,668 outcomes) |
| coherently-graded cricket markets carrying a draw member | **7,025** of 7,700 |
| independent questions behind the cohort (`vm_id` clusters) | 4,283 behind 15,812 outcomes (~3.7×) |

Draw-member capture predicts coherent grading almost perfectly. The cricket cohort reaching the
curve is precisely the set of markets **whose third leg we never captured** — so the field is
scored as if it were two-outcome, which is the shape the payload split predicted from the other
end. Both halves agree, and they were derived independently.

**Why they reach the curve at all:** the multi-winner exclusion (`nonexclusive_bundle_markets`) is
**census-only outside esports** — it counts these markets, it does not drop them.

**Verdict: `exclusion`, not `fix` and not "genuinely bad".** Per gotcha #21 this is read-side —
extend the exclusion, never re-grade a resolved population. Per the standing house rule the
extension ships **with its published count**.

**BLOCKED, and on the one thing everything else is blocked on:** an exclusion change alters what the
curve plots, so it carries a `CALIBRATION_POPULATION_VERSION` bump, which takes `/calibration` dark
until the next successful beat. No bump until the build publishes. This is diagnosis-complete and
fix-blocked, which is a different state from undiagnosed and should not be read as the same one.

⚠️ **Two caveats that will change conclusions if skipped**, from the bundle's own README: the
extract is **95.8% complete** (6,058 of 6,387 markets; one id window timed out even when split), and
the per-cell counts are the **RAW cohort, not the published cell** — cricket poly b5 is 1,947 raw
against 415 published, 48.9% vs 79.3% winrate. The published exclusions are strongly selective, so
the design effects transfer as an order-of-magnitude correction, not an exact one. **The published
count owed by the house rule must be computed on the published population, not from these rows.**

### Entertainment — still TWO live rivals, and CAL-P027's rail is what separates them

Unchanged in substance: the structural half is evidenced, the timing half is not. Zero of the 1,107
bucket-9 rows are mex-normalized (`win_count` is 0 or 6–11, never 1), and the specimens are Kalshi
cumulative scalar-range ladders — market `6549959` carries **21 numeric bands each priced 0.99**
with `win_count = 0`, i.e. gotcha #17 surviving into `calibration_probability`.

**What is still not testable, and must not be reported as settled:** whether the close was captured
*after* settlement. There is no settlement timestamp in the schema — `resolution_date` is a
*scheduled* date — and quote chronology lives in `futures_odds_snapshots`, which the bundle did not
export.

**CAL-P027's rail supplies the discriminator without needing a settlement timestamp.** Its density
bands separate a single captured quote (`density_band = "1"`) from a long observation history, per
`(source, category)`. A near-certain price with **one** captured quote is the stamped-settlement
signature; a near-certain price with a long move history is not. That is a proxy — it narrows the
rival, it does not close it — and one walk of `overlap-trading-census` scoped to
`kalshi × entertainment` answers it.

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

### ✅ BUILT — CAL-P025, 2026-08-09, `program/calibration-23`

The "All" tab of the By Source section is now small multiples: one panel per source, each drawn by
`CalibrationChart`, which fixes both axes at 0–100% **structurally** — so the shared axis is not a
convention anyone has to maintain. Selecting a source tab still gives the full-width chart, since
that is the view the per-bucket drill-in belongs to; the drill-in also works from any panel.

**The non-obvious half, and the reason this went through a tested function rather than inline JSX:
small multiples equalise panel AREA, which erases exactly the size difference the overlay conveyed
by accident.** A 12,410-outcome curve and a 420,594-outcome curve get identical frames and read as
equally authoritative. So `buildSourcePanels()` gives every panel its own **n, share of the curve,
and ECE**, and the panels are ordered largest-first.

#### Ruling 003 caught this mid-build, and it was right to

The panel ECE was first written as a client-side derivation from the same buckets. **Ruling 003
("clients format, never adjudicate", banked 2026-08-09 while this queue was being built) names
that exact thing as a failure**: *"dual ECE derivations — the same calibration number computed
twice, in two languages, which guarantees they drift."* The panels now render the server's
published `by_source[].ece` and print **nothing** where the payload published none, rather than
backfilling a client number into the gap.

**The drift is not hypothetical — it is already live on the payload production is serving:**

| source | published `by_source` | client-derived from the same buckets |
|---|---|---|
| kalshi | 0.8pp | 0.8pp |
| polymarket | 2.7pp | 2.7pp |
| odds_api | 1.4pp | 1.4pp |
| odds_api_totals | 1.1pp | 1.1pp |
| **odds_api_spreads** | **0.7pp** | **0.6pp** |

Four of five agree, which is precisely how a dual derivation survives review — it looks fine until
it doesn't, on one source, at one moment. Pinned by test.

**A pre-existing instance this surfaced, reported not fixed.** The *Source Comparison* table above
the panels still derives `srcECE` / `srcMCE` / `srcBrier` client-side, so on today's payload it is
showing **0.6pp for odds_api_spreads while `by_source` says 0.67pp**. That is the same violation,
older and wider (MCE and Brier are not published per source at all, so it cannot simply be
rewired). Fixing it means publishing those as typed backend decisions — which means editing the
precompute, which is frozen until the curve publishes. **Named here as owed, deliberately out of
this branch's scope.**

Pinned by test on the frozen payload: the five panels in order (kalshi 420,594 · polymarket
191,738 · odds_api 14,960 · odds_api_totals 12,705 · odds_api_spreads 12,410), reconciling to
652,407; shares summing to 1; the 28x span asserted directly; and kalshi's ECE below polymarket's
by more than 2x. A source with no outcomes is **dropped rather than drawn as an empty frame** —
an empty panel asserts "we measured this and found nothing", which is not what missing means.

New rail hooks: `calibration-source-panels`, and per panel `calibration-source-panel` carrying
`data-source`, `data-panel-n`, `data-panel-ece`.

**Still owed for GREEN: the rendered screenshot**, for the same reason as item 2 — the proof is
visual, and the rail that can take it grades production.

---

## 5. Native calibration surface consistent with web

**Required proof:** side-by-side — native surface and web `/calibration` showing the same
population version, the same generated-at, and the same headline figures. Rendered on both.

**Status: 🟢 PASSED 2026-08-09 (CAL-P026) — rendered on both surfaces, figures identical.**

### The proof

Both surfaces rendered against **the same production response** — `generated_at
2026-08-02T03:23:54.886392+00:00`, `population_version q267`. That is not a coincidence of timing:
production has been serving that one payload since 2026-08-02 (Item 0 of every window this week
re-confirms it), so a capture of web today and a render of the frozen 2026-08-02 fixture natively
are the same bytes, not two nearby snapshots.

| figure | web (browser rail) | native (`ImageRenderer`) |
|---|---|---|
| cohort / hero population | **389,385** | **389,385** |
| never-moved excluded | **263,022** | **263,022** |
| full population | **652,407** | **652,407** |
| markets | 534,269 | 534,269 |
| ECE · MCE | 1.5pp · 1.4pp | 1.5pp · 1.4pp |
| Brier | 0.165 | 0.165 |
| date range | Aug 2021–Aug 2026 | Aug 2021–Aug 2026 |
| stale banner | ✅ "Showing the last complete snapshot." | ✅ same sentence |

- **web** — `browser-audit.yml` run
  [31336823181](https://github.com/alexander-bain/bainluck/actions/runs/31336823181), pack
  `calibration`, `result: pass`, requested == observed frontend SHA
  `2a9f42b50fae93c33559cb680865967b04281c03`, backend `2a9f42b5`. Artifacts
  `calibration.anonymous.{desktop,mobile}.terminal.png`.
- **native** — `CalibrationParityTests.testProductionPayloadRendersTheStaleSurfaceForSideBySideEvidence`,
  which rasterises the real `CalibrationSurfaceView` from `CalibrationProdFixture` and prints its
  own parity line: `population=q267 contract=matched cache=stale
  generated=2026-08-02T03:23:54.886392+00:00 cohort_n=389385 full_n=652407 reconciles=true`.

**The flagged honesty risk is confirmed a FALSE ALARM, now with a picture rather than a source
read.** Native banners the stale payload in the same words web does.

### The one difference, and why it is not a defect

Web renders *"built Aug 2, 3:23 AM (8 days ago)"*; native renders *"built Aug 1, 8:27 PM (24h
ago)"*. Both are correct and neither disagrees about the instant:

- the **clock time** differs because both use a locale formatter and the two renderers sat in
  different zones (the CI runner in UTC, the simulator in PDT). `2026-08-02T03:23:54Z` *is*
  Aug 1, 8:23 PM PDT.
- the **age** differs because the native fixture is frozen with the `age_s` the server sent on the
  day it was captured (86,461 s ≈ 24 h), while web read today's envelope (~8 d).

This is exactly why the parity hooks publish the **raw ISO instant** rather than the formatted
string — a comparison of display text would have failed here on a timezone and passed on a wrong
number. Web's hook made the same choice; native's now matches it.

### What CAL-P026 had to build before the proof was possible

The exam predicted this item would be *"confirming correct behaviour, not finding a live bug"*.
On the honesty question that was right. But the item could not be *evidenced*, and the reason was
structural rather than cosmetic:

1. **Native never rendered the population version.** `CalibrationViewModel` decoded it,
   adjudicated it against `compatiblePopulationVersions`, and exposed `populationVersion` — and
   the View referenced 45 view-model properties, *not including that one*.
2. **Native had ZERO `accessibilityIdentifier`s on the entire surface**, while web publishes
   `data-population-version`, `data-cache-status`, `data-contract-state`, `data-generated-at`,
   `data-cohort-n`, `data-full-n` and the partition counts, with
   `calibrationAuditHooks.test.tsx` failing CI if one is dropped.

So the side-by-side could only ever have been a person comparing two screenshots — a check
performed once, on the day somebody cares, and drifting silently afterwards. **Web's own source
had already named this**, in the comment above its population-count hook: *"a native surface
reading the other one diverges silently. Both are published here as data so the parity check reads
numbers, not text."* The data was published for a consumer that did not exist.

CAL-P026 built it: `CalibrationViewModel.Parity` (one descriptor, read by both the hooks and the
tests, so there is no second derivation to drift — ruling 003), matching
`accessibilityIdentifier`s named with web's own testids, nine `CalibrationParityTests` pinning the
figures against the frozen production payload, and a three-test **cross-language** contract gate
(`frontend/e2e/contract/calibrationSurfaceParity.contract.test.js`) that fails when a native hook
is renamed away from web's testid or when the two fixtures stop describing the same response.

**So item 5 does not just pass — it stays passed.** A future divergence is a red CI run, not a
thing somebody notices in a screenshot months later.

### The one caveat worth stating

The native figures come from a **frozen fixture**, not a live device fetch, so this proves the two
surfaces AGREE ON A PAYLOAD rather than that native's networking is healthy. That is the right
scope — the exam asks whether the two surfaces describe the same data the same way — and the live
fetch path is covered separately by `CalibrationAvailabilityTests`. It is named here so nobody
reads more into the picture than it shows.

---

### Superseded — the pre-CAL-P026 assessment, kept for the record

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
| 2026-08-09 13:07 | cae1 | `/api/calibration` **200 in 0.97s**, `cache.status="stale"`, `age_s=664868` (**7.70 d**) — publish still `2026-08-02T03:23:54Z`, census still `payload_predates_census`. Age is climbing monotonically (7.53 → 7.59 → 7.70 d across three windows today) exactly as CAL-P024 projected | items 1/3/7 blocked |
| 2026-08-09 13:07 | cae1 | deployed `30d10863` (INT-027); `git cherry` shows CAL-P024's three commits still outstanding ⇒ production still runs the census ON at ~632 s/unit | CAL-P024 |
| 2026-08-09 13:12 | cae1 | matched-bucket table **re-derived live from `/api/calibration`** and reproduces this document's 2026-08-02 figures to 0.1pp (b3 −0.9/−2.7 · b4 −1.4/−5.7 · b5 −1.6/−1.1) ⇒ items 2 and 4 need no publish | item 2 |
| 2026-08-09 13:40 | cae1 | **items 2 and 4 BUILT** — `compareMatchedBuckets` + `buildSourcePanels`; frontend suite **1,843 passed / 0 failed** (was 1,832), build clean, typecheck 84 = baseline. 7 mutations confirm every load-bearing rule | items 2, 4 |
| 2026-08-09 13:45 | cae1 | local Chromium **fails to launch** in the agent sandbox (`playwright-core` → "Target page, context or browser has been closed"), re-confirming that rendered evidence needs the remote rail against a deployed build | items 2, 4, 5 |
| 2026-08-09 14:05 | cae1 | **live dual-ECE drift**, published `by_source` vs client derivation on the same buckets: 4 of 5 sources agree at display precision, **`odds_api_spreads` 0.7pp published vs 0.6pp derived**. Panels rewired to render the published value (ruling 003); the pre-existing Source Comparison table still derives and is reported as owed | item 4 |

| 2026-08-09 14:06 | 8f3d | `/api/calibration` **200 in 0.66s**, `cache.status="stale"`, `age_s=668487` (**7.74 d**) — publish still `2026-08-02T03:23:54Z`, census still `payload_predates_census`. Fourth rising reading today (7.53 → 7.59 → 7.70 → 7.74 d) | items 1/3/7 blocked |
| 2026-08-09 14:10 | 8f3d | **kalshi entertainment b9 split by `price_moved`**: moved n=816 pred 95.1% act 67.5% (−27.5pp) vs unchanged n=98 pred 94.9% act 86.7% (−8.1pp) — collapse is on the MOVED side, consistent with settlement-collapse | item 3 |
| 2026-08-09 14:10 | 8f3d | **polymarket cricket is one bucket**: b3 n=1,435 (+0.1pp, well calibrated) · b5 n=608 (+29.0pp) · b2 n=263 (−16.1pp); b5's error is equal on moved and unchanged ⇒ population defect, not capture artifact | item 3 |
| 2026-08-09 14:11 | 8f3d | **the native gate RUNS in a program worktree** — `xcodebuild` fails resolving Firebase/gRPC binary artifacts (`dl.google.com` egress blocked), but `-clonedSourcePackagesDirPath <existing DerivedData>/SourcePackages -disableAutomaticPackageResolution` reuses the cached artifacts: `** BUILD SUCCEEDED **` | gotcha, below |
| 2026-08-09 14:22 | 8f3d | native suite **530 passed / 0 failed** (was 521); contract suite **311 / 0** (was 308); both new gates non-vacuous by mutation | item 5 |
| 2026-08-09 14:26 | 8f3d | **item 5 side-by-side PASSED** — browser-audit run [31336823181](https://github.com/alexander-bain/bainluck/actions/runs/31336823181) `result: pass`, frontend SHA requested == observed `2a9f42b5`; native `ImageRenderer` render of the same payload. 389,385 · 263,022 · 652,407 · ECE 1.5pp · MCE 1.4pp · Brier 0.165 identical on both; both banner staleness | item 5 |

| 2026-08-09 15:10 | 7b21 | **cricket identified** — every multi-winner 3-outcome cricket market has `draw_member_count = 0` (1,668 outcomes / 556 markets); coherently-graded ones carry a draw member 7,025 of 7,700. Reaches the curve because `nonexclusive_bundle_markets` is census-only outside esports. Extract 95.8% complete; per-cell counts are RAW not published | item 3 (recorded here by CAL-P027) |
| 2026-08-09 21:39 | e5b2 | `/api/calibration` **200 in 0.62s**, `cache.status="stale"`, `age_s=695807` (**8.05 d**) — publish still `2026-08-02T03:23:54Z`, census still `payload_predates_census`. **Sixth** rising reading (7.53 → 7.59 → 7.70 → 7.74 → 7.76 → 8.05) | items 1/3/7 blocked |
| 2026-08-09 21:41 | e5b2 | deployed `f78b8a6d` == `origin/master`, single-valued (the 7b21 two-dyno skew has cleared). **CAL-P024 still unmerged, verified by CONTENT** — `origin/master` still reads `COVERAGE_CENSUS_ENABLED = True` ⇒ production still builds at ~632 s/unit and ruling 009's baseline has not landed | CAL-P024 |
| 2026-08-09 21:45 | e5b2 | `futures_outcomes` = **3,237,030 rows across a 218,050,432-wide id space**; the bare `COUNT(*)` took **9.93 s against a 10 s timeout**. An 8M-id window at the dense head TIMED OUT; a 550K-id window returned in 0.47 s ⇒ row-bounded windows, re-confirmed | item 1 |
| 2026-08-09 21:50 | e5b2 | volume coverage is **not one number**: 14.2% (recent 550K ids, n=8,509) · 4.5% (mid, n=2,759) · 4.2% (old tail, from 10:52 above). **`volume = 0` did not occur once** in any window — every volume-bearing row was `> 0` | item 1 |
| 2026-08-09 21:52 | e5b2 | futures market population by source: polymarket **553,876** · kalshi **191,114** · datagolf 300 · **odds_api 12** ⇒ the multi-bookmaker case is rare, but DataGolf's write-time `reading_count` dedup means `COUNT(*)` is not observation density | item 1 |
| 2026-08-09 22:30 | e5b2 | **item 1's rail BUILT** — `census_overlap_trading.py` + `overlap-trading-census`; full backend **12,154 passed / 0 failed** (was 11,785), ruff clean, **12 mutations** each caught. N still UNMEASURED: first walk owed post-merge | item 1 |
| 2026-08-09 22:45 | e5b2 | **CAL-P024 MERGED AND DEPLOYED mid-queue** — master `ff627a39` (CAL-P024a/b/c, #1479), `/api/health` = `ff627a39`, and `COVERAGE_CENSUS_ENABLED = False` confirmed by content on `origin/master`. Supersedes the 21:41 reading in this log. **Ruling 009's baseline has landed; the ~13-beat count can start.** Publish still `2026-08-02T03:23:54Z` — the SLO stays RED until the build walks 128 units | ruling 009; SLO |
| 2026-08-09 22:47 | e5b2 | `git merge-tree origin/master program/calibration-25` = **clean**, no conflict, despite master's CAL-P024 also editing this document — its edits land in the convergence section, between this queue's | CAL-P027 hand-off |

## A gotcha this window measured — the native gate is NOT unavailable in a program worktree

Gotcha #50 covers the SwiftUI `#Preview` macro-sandbox failure and its
`-Xfrontend -disable-sandbox` fix. There is a **second, different** blocker that hits any
*fresh* worktree, and it looks like a hard wall:

```
failed downloading 'https://dl.google.com/firebase/ios/bin/grpc/1.69.1/rc0/grpc.zip'
  which is required by binary target 'grpc': downloadError("The request timed out.")   ×11
```

The git-based SPM packages are cached (`~/Library/Caches/org.swift.swiftpm/repositories`), but the
**binary** targets are zips fetched from `dl.google.com`, and that egress is blocked. A program
worktree at a new path gets a new DerivedData hash, so it re-resolves from scratch and dies here —
which reads as "iOS cannot be gated from this lane".

It can. The artifacts are already extracted under an existing DerivedData:

```
xcodebuild -scheme "Bain Luck" -destination 'generic/platform=iOS Simulator' \
  -clonedSourcePackagesDirPath ~/Library/Developer/Xcode/DerivedData/Bain_Luck-<hash>/SourcePackages \
  -disableAutomaticPackageResolution \
  OTHER_SWIFT_FLAGS='$(inherited) -Xfrontend -disable-sandbox' build
```

Both flags are needed: the first points at the cached artifacts, the second stops SPM trying to
re-resolve anyway. **Do not delete the SPM cache to "start clean"** — gotcha #50's existing warning
applies with double force here, since the artifacts cannot be re-downloaded at all.

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
