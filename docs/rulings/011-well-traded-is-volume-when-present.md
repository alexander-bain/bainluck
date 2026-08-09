# RULING 011 — Well-traded means volume evidence WHEN PRESENT

date: 2026-08-09
author: Alex
via: Fable, ratified
issues: #1544 · #683
supersedes: nothing — this RESOLVES RULINGS-NEEDED item 9 (option A)

**DO NOT REMOVE (CI-guarded).**

> A market's trading-activity tier uses **volume evidence whenever volume is present in ANY
> retained snapshot.** **Missing volume data never silently demotes a market to thin.**
>
> Ships **ONLY** with a `CALIBRATION_POPULATION_VERSION` bump **and published before/after counts
> per cohort.**

> **Numbering note:** handed over as "ruling 010", which was already taken by the Sentry ruling
> banked earlier the same day. Renumbered to 011 per `docs/rulings/README.md` — the later ruling
> moves, never the earlier one. Neither had been pushed, so nothing downstream is disturbed.

## Named failures

- **Public `<400K` undercount.** The published well-traded count was materially low, because
  markets with real trading were being counted as thin.
- **The thin > thick accuracy inversion.** Thin markets appeared to be BETTER calibrated than
  thick ones — which is not a finding about markets, it is an artifact of the classifier. Genuinely
  well-traded markets whose volume field was absent from the snapshot we happened to read fell into
  the thin bucket and dragged its accuracy *up*.

That second one is the load-bearing failure, and it is worth naming precisely: **the bug did not
just make a number wrong, it made a number LIE IN AN INTERESTING DIRECTION.** An inversion invites
a story — "maybe thin markets are sharper" — and a plausible story about your own artifact is far
more expensive than an obviously broken number, which someone would simply have fixed.

## Why "when present in ANY retained snapshot"

Absence of volume in the snapshot we read is a fact about **our capture**, not about the market.
Kalshi's retention cliff purges market data at ≥74 and <86 days (gotcha #35), snapshots are sparse
for illiquid series, and a single read is a sample. Treating a gap as evidence of thinness is the
exact error gotcha #53 names: **inferring a fact from the emptier reading.** An empty field is a
response shape, not an absence of trading.

So the tier looks across every retained snapshot and takes the strongest evidence available. If no
snapshot anywhere carries volume, the market is **UNKNOWN — never "untraded".** That distinction is
the whole ruling; collapsing unknown into thin is precisely what produced both named failures.

## Why the two shipping conditions are not ceremony

**The version bump** is mandatory because this changes what the published curve plots. Without a
`CALIBRATION_POPULATION_VERSION` bump, a cached artifact built under the old classifier serves
alongside new ones and the page silently mixes two populations. That is not a cosmetic risk: it
makes the curve unfalsifiable.

**The before/after counts per cohort** are mandatory because a reclassification that publishes only
its "after" is indistinguishable from a data change. The pair is what lets a reader see the size of
the correction — and if the undercount was as large as suspected, the correction is the headline,
not a footnote.

## Sequencing — and the interlock with ruling 009

The bump takes `/calibration` **dark until the next successful beat**, so it cannot ship while the
build is not publishing. That is exactly the condition ruling 009 froze
`precompute_calibration.py` to establish.

**This ruling runs the moment ruling 009's freeze lifts** (fresh publish post-CAL-P024 plus ~13
clean beats). It is staged NOW as the freeze-lift successor queue so **zero days are lost** between
the freeze lifting and this landing — the lift condition being met is the trigger to execute an
already-written queue, not the trigger to start writing one.

The two rulings are one mechanism: 009 makes the pipeline capable of publishing, 011 is the first
thing worth publishing through it.
