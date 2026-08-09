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
| 1 | Ruling 9 shipped; published count reflects volume-proven trading, both figures named | 🟡 **RULED 2026-08-09** — definition settled, unbuilt | healthy publish (version bump) |
| 2 | Trading-activity section led by matched-bucket comparison | 🔴 not started | — (ready to stage) |
| 3 | Cricket + entertainment diagnosed to fix / exclusion / "genuinely bad" | 🟡 measured, undiagnosed | fresh prod window |
| 4 | Source graph redesigned — per-source panels | 🔴 not started | — (ready to stage) |
| 5 | Native calibration surface consistent with web | 🔴 unassessed | — (ready to stage) |
| 6 | Monitoring proven by drill — watchdog + sentinel guards observed firing | 🟡 watchdog deployed today | a fresh window to observe; sentinel half is plumbing #1548 |
| 7 | Backfill recovery progressing vs 786K recoverable; capture-floor re-measure ~Aug 15 | 🟡 **PILOT AUTHORISED 2026-08-09** | a fresh prod window; ~Aug 15 |

**Nothing is green.** Two items (2, 4) are unblocked and stageable today.

### The one scheduling fact that governs the exam

Items **1** and **3** change what the curve plots, so each carries a
`CALIBRATION_POPULATION_VERSION` bump. Already-staged **CAL-P019** carries a third. A bump takes
`/calibration` dark until the next successful beat.

**No bump ships until the build publishes again.** As of 2026-08-09 09:20 PT the build has not
published since **2026-08-02 03:23:54 UTC**; CAL-P016's staged path went live at ~08:47 PT and is
banking units (4 of 128, `terminal=partial`). Until `calibration:main.generated_at` moves,
**items 1, 3 and 7 cannot be evidenced at all** — their proof is a published number.

That makes CAL-P016's convergence the critical path for most of this exam.

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

**Status: 🔴 unassessed.** The iPad/macOS sidebar carries a Calibration entry point
(`CLAUDE.md`, native code organisation). Nobody has checked what it renders since the payload
gained `cache.status`, `provenance`, the coverage census, and the dated-tier banner.

**Specific risk worth checking first:** the web page renders the stale-tier banner
(`data-cache-status`, "as of <time> (N ago)"). If native does not, then during the current outage
**native is showing a week-old curve as current** while web discloses it — a "settled means
settled"-class honesty failure on a second surface. This is the highest-value single check in the
exam and it is cheap.

Native gate: the canonical `xcodebuild` invocation, with `OTHER_SWIFT_FLAGS='$(inherited)
-Xfrontend -disable-sandbox'` (gotcha #50).

---

## 6. Monitoring proven by drill — observed firing, not merely merged

**Required proof:** the publish-age watchdog observed producing an alert with the failing phase
attached; the sentinel guards observed executing. Linked run output, not a merge SHA.

**Status: 🟡 half deployed today, neither observed.**

**The watchdog half is live and the drill conditions are already true.** CAL-P017 Item 1 added
`calibration_publish_age` to `data_quality_watchdog.CHECKS` (P1, `lte` 2 hours, MISSING coalesces
to a large age so it fails rather than passes), plus a `context_query` that reads
`calibration:main:phase_ledger` so the issue body names the failing phase. It deployed in
`b4aa0039` at ~08:47 PT.

The publish is **7.53 days** stale right now — 90x over the 2-hour threshold. So the check should
be failing on its next run and filing a P1 whose body names *phase futures, stage
`read:futures_population`, statement timeout*. **Nobody has looked.** This is a free drill: the
condition exists, no one needs to break anything to create it, and it expires the moment CAL-P016
converges and the publish goes fresh.

→ **This is the single most time-sensitive item in the exam.** Observe it before the publish
recovers, or the drill has to be manufactured later.

The sentinel-guards half is **plumbing lane #1548** (ALEX-DECISIONS 2026-08-08 §4), routed there
by CAL-P017 Item 3 and explicitly out of this lane. The exam needs its evidence; the calibration
lane does not produce it.

---

## 7. Backfill recovery measurably progressing vs the 786K recoverable cohort

**Required proof:** two dated measurements of the recoverable cohort showing it shrinking, plus
the capture-floor re-measure on ~2026-08-15.

**Status: 🔴 not started.**

The cohort is named and counted (CAL-P011 tier contract, CAL-P012 bounded census rail
`/api/admin/repairs/reachability-census`), but **the census has never been run to exhaustion in
production**, so there is no first datapoint to progress *from*. Nothing can be shown shrinking
until a baseline exists.

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

## Open questions for Alex

**All three are ANSWERED as of 2026-08-09** (PRODUCT-BRAIN § RULINGS 2026-08-09(b)):

1. ~~Ruling 9 = Option A?~~ → **Ruled directly**, and more precisely than A: the volume /
   hardened-movement / unknown ladder. The inference is retired, not confirmed.
2. ~~Polymarket recovery write?~~ → **Bounded pilot first** (~5K, attended, curve impact reported
   before going further).
3. ~~Three-winner scope?~~ → **Pause; 10 eyeballed specimens per category first.** Plus the lane's
   own correction: the 1,885 multi-winner extension was already granted on 2026-08-08, and the
   3,585 figure mixes in `incoherent_field` (bad PRICES), which the winner rail cannot fix at all.

Nothing is currently blocked on Alex. Every remaining item is blocked on a fresh production window,
on the publish converging, or on elapsed time.

### The one thing that would change this

If N turns out unmeasurable — i.e. too few rows carry BOTH volume and adequate snapshot density to
validate the proxy — then tier 2 has no empirical basis and item 1 comes back with a real choice
(ship tier 1 + unknown only, or keep the old bar). Flagged now so it is not a surprise later.
