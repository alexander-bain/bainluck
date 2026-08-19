# RULING 096 — No statistic rescues a bad pair; a tie prints the midpoint

date: 2026-08-19
author: Fable
issues: #1986, #2000, #2001

Issued on UX-P101's blend census, which inverted the premise it was commissioned
to serve and thereby earned two separate rulings rather than the one that was
asked for.

## The census that forced the split

The question was "median or mean". The census answered a different one. Two
populations were hiding under one word:

- **The events hero.** 76 live two-source blends (the naive count said 570;
  `betting_book_count` is metadata, not a source). **Zero are equal-weight.**
  There is no tie here to break, so the degeneracy that motivated the question
  does not occur on the surface with the most traffic.
- **The futures merge.** Every live merge IS equal-weight, and there
  `median == min(values)` on 3 of 3, with `delta == −spread/2` **exactly**.

And the specimen: **AL West Winner — Houston, Kalshi 0.575 vs Polymarket 0.060.**
The blend printed 6%. A mean would print 31.75%.

## Clause 1 — the divergence gate

**A two-source pair whose spread exceeds a measured sanity threshold does not
blend.** Render the primary source's own value and flag the pair to matching as a
suspected mis-link.

A 51.5-point gap on one question is not two opinions about baseball; one of the
two readings is about a different question. The mean is not more correct than the
median there, only differently wrong — it is a number no source stated and none
will confirm. **Neither statistic rescues a bad pair**, so stop asking which one
to use and stop producing a third number from a broken input.

The threshold is **derived from the observed spread distribution, not chosen**.
Tukey's fence on the live population gives `Q3 + 1.5·IQR = 0.3946`; 0.40 is
adopted and selects an identical set of 4 events, which is the check that makes
the rounding safe rather than cosmetic.

**"Primary" means the highest EFFECTIVE weight, after decay.** The tempting
reading — highest base authority, the sportsbook — rebuilds #240: in a live
blowout it prints the stale pregame line over a game already decided. The gate
must not resurrect the defect the weighted median was introduced to fix.

Consequence, which is not a weakness: on the events hero the gate changes **zero**
of 76 displayed numbers. A two-source weighted median already returns one of the
two stated values. What the gate buys there is the flag, and an invariant — *the
rendered value is a number some source actually stated* — which holds today only
by accident and stops holding the moment clause 2 lands.

## Clause 2 — equal-weight semantics

**For a two-source EQUAL-WEIGHT merge, print the midpoint, not the lower entry.**
Scoped to `futures_source_merge`; the events aggregator's heavier-source tiebreak
is designed behaviour and stands.

The objection this overturns was a good one and is recorded rather than erased:
substituting a mean was said to fork a second aggregator, which the blend ruling
exists to prevent. What the census showed is that the scope is narrower than the
objection assumed. Where weights differ, the weighted median expresses a judgement
about authority and must be left alone. Where they are equal there is no judgement
to express — the median is just reading whichever value sorted first, and the
sort order carries no meaning. A rule that resolves every tie downward is not a
tiebreak, it is a systematic discount, and the census measured it as exactly half
the spread, every time, always down.

## Ordering

Gate first, midpoint second — and the order is load-bearing, not stylistic. The
midpoint is the first genuine MIXTURE this product prints. Introducing it without
the gate would mean averaging Kalshi's 57.5% with Polymarket's 6% and rendering
31.75% as though it were a finding.

## Standing

Consistent with *the blend is the product* — one number per question. Source
divergence remains **a data bug to fix, not a feature to show**: the gate does not
put two numbers on screen, it puts one honest number on screen and sends the
disagreement to the layer that can repair it.
