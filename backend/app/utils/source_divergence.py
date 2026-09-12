"""THE DIVERGENCE GATE — a two-source pair that cannot both be right does not blend.

Fable ruling (b), cycle 99, on UX-P101's census: *a two-source pair whose spread
exceeds a sanity threshold does NOT blend — no statistic rescues a bad pair.
Render the primary source's value alone and flag the pair to matching as a
suspected mis-link.*

The specimen the ruling was written against: **AL West Winner — Houston, Kalshi
0.575 vs Polymarket 0.060.** A 51.5-point gap on one question is not two honest
opinions about baseball. Today's blend prints 6%; a mean would print 31.75%.
Neither is more correct than the other — one of the two readings is about a
different question, and averaging a good number with a wrong one produces a
number no source ever stated and no source will ever confirm.

So the gate's job is NOT to pick a better statistic. It is to stop manufacturing
a third number out of a broken pair, and to make the breakage visible to the
layer that can actually fix it (matching).

---

## THE THRESHOLD IS MEASURED, NOT PICKED

`DIVERGENCE_SPREAD_THRESHOLD = 0.40`, derived from the observed spread
distribution of the live two-source population read 2026-08-19T04:5xZ against
deployed `962f668a` (n = 76 events, `status IN ('scheduled','live')`, keys
restricted to `SOURCE_WEIGHTS`, parsed with the shipped `parse_source_entry`):

    p10 0.0138 · p25 0.0283 · p50 0.1059 · p75 0.1748
    p90 0.2778 · p95 0.3991 · p99 0.6313 · max 0.8319 · mean 0.1362

Tukey's outlier fence on that distribution:

    Q3 + 1.5 * IQR  =  0.1748 + 1.5 * (0.1748 - 0.0283)  =  0.3946

0.40 is that fence, and the check that matters is that the rounding does not
move the answer: **the fence and 0.40 select an IDENTICAL set of 4 events** on
the observed population (spreads 0.8319, 0.5645, 0.5191, 0.4194 — the next
value down is 0.3923). The aggregation module's own weight-cap comment warns
about rounding a derived constant "up to a nicer number" without re-checking
the bound; this one was re-checked, and it is stated here so the next reader
does not have to take it on trust.

## WHY "PRIMARY" MEANS THE HIGHEST *EFFECTIVE* WEIGHT, AND WHY THAT MATTERS

The obvious reading of "the primary source" is the highest BASE authority —
`betting` at 3.0, the sportsbook. That reading is wrong, and the data says so
loudly enough that it is worth recording rather than quietly not doing.

On the same 76-event population, recency decay (#1829) flips which source
carries the blend on **40 of them**: the sportsbook is a median 33.6 h stale
against a prediction market that repolls every couple of minutes, decays to its
0.1 floor (3.0 -> 0.3), and the 0.8-weight market source carries the number.

Now put a base-weight primary into a live blowout. The sportsbook sits at its
stale pregame 65%, the live market is at 5%, the spread is 0.60, the gate fires
— and a base-weight primary prints the **stale pregame number on a game that is
already over**. That is #240 exactly: the 57%-hero contradicting the 20%-chart
on one screen, which is the defect the weighted median was introduced to fix.
A gate that resurrects it is worse than no gate.

So the gate honours decay. It selects whichever source the blend was going to
select anyway, which has a consequence worth stating plainly rather than
dressing up:

**On the events hero the gate changes ZERO of the 76 displayed numbers today.**

That is the honest result and it is the correct one. With exactly two sources a
weighted median already returns one of the two stated values — it cannot
produce a mixture — so on this surface the gate is not a number change, it is
two other things:

  1. **A flag.** Four live pairs are named as suspected mis-links, with their
     spread and both readings, for the matching layer. Three of the four are
     one class: Polymarket reading 0.07 against a sportsbook at 0.59-0.63.
  2. **An invariant that is currently free and will not stay free.** "The
     rendered value is a value some source actually stated" holds today only as
     an accident of the median. Ruling (b)'s own second half moves the futures
     merge to a MIDPOINT — a genuine mixture — and the moment a mixture is
     legal anywhere, an ungated bad pair produces an invented number. The gate
     is what makes the midpoint safe to introduce.

Where the gate DOES change numbers is the futures merge, where the pair is
equal-weight and the midpoint rule would otherwise average Kalshi's 57.5% with
Polymarket's 6%.

## SCOPE — TWO SOURCES, AND THE ONE CASE WHERE THAT IS WRONG (#5542)

Two sources only. A one-source event has no spread. Both are left alone.

The `len(keys) != 2` below is a DELIBERATE population choice, not an
implementation detail, and it is right for the case it was written for: with
three or more HEALTHY sources there is a genuine outlier to resist and the
median already resists it. Measured on the shape rather than asserted —

    betting 0.10 · kalshi 0.52 · polymarket 0.55
    widest pair 0.450 (past the 0.40 threshold) · median 0.5200

— the two sources that agree carry the number and the outlier is discarded. Had
the gate governed the WIDEST PAIR among N it would fire here and render ONE
source alone, throwing away the agreement of the other two. That is strictly
worse than blending, so **"widest pair among N" is REJECTED**, on that specimen.

### The hole: a dead arm is not an opinion, but it still counts as a source

That argument assumes the third reading is a live opinion. It is not always. A
source decayed to `HERO_MIN_STALENESS_MULTIPLIER` has been told by our own
recency rule that it is no longer describing this game — and it STILL takes the
event out of this gate's population, and STILL holds enough post-cap mass to
decide which of the two live sources is the median.

Measured on event 15304937, live at 07:07Z 2026-09-12:

    mlb 0.356 (131 min behind the freshest) · kalshi 0.99 · polymarket 0.455
    post-cap shares   mlb 0.30 · kalshi 0.35 · polymarket 0.35
    3 sources         -> median 0.4550, assess_divergence None   (SILENT)
    dead arm removed  -> gate FIRES, primary kalshi 0.99

The widest pair is 63 points — worse than the 51.5-point pair this module was
written against — and the protection is off. **The protection switches off
exactly as the data gets worse.** The dead arm's own value is never the median;
it decides WHICH source is, by position. The served hero was 0.455, the losing
side, on a game the home team had already won 6-5.

This is a KNOWN, UNFIXED hole, recorded here rather than quietly tolerated. It
is not fixed in this pass because the fix changes served heroes and its reach is
unmeasured: at 09:26Z 2026-09-12 the live population held 16 events and NONE
with three real sources, so the reach cannot be read off an overnight slate.
(`betting_book_count` is a metadata key in the same JSONB — counting it as a
source is how that census goes wrong, and did once before it was corrected.)
The measurement is parked as `M-20260912-live170`; the fix is #5542's second
half. Do not "simplify" the `!= 2` away in either direction without it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional

__all__ = [
    "DIVERGENCE_SPREAD_THRESHOLD",
    "SourceDivergence",
    "assess_divergence",
    "spread_exceeds",
]

# See the module docstring for the derivation. Tukey fence = 0.3946; 0.40
# selects the identical set on the measured population.
DIVERGENCE_SPREAD_THRESHOLD = 0.40

# Ruling (c), banked as doctrine one cycle ago and applied here on purpose: a
# spec that draws a line needs the comparison written down and a fixture ON the
# line, because `0.7 - 0.5 !== 0.2`. This threshold is the top of the SANE band,
# so a pair sitting exactly on it must blend normally — and a spread assembled
# from two decimal probabilities lands a few ULPs either side of the intended
# value at random. `0.7 - 0.3` is 0.39999999999999997 and `0.9 - 0.5` is 0.4;
# without a tolerance, whether two identically-specified pairs gate depends on
# which decimals they happened to be written with.
_BOUNDARY_EPSILON = 1e-9


def spread_exceeds(spread: float, threshold: float = DIVERGENCE_SPREAD_THRESHOLD) -> bool:
    """Is this spread past the sanity line? Exactly ON the line is NOT past it."""
    return spread > threshold + _BOUNDARY_EPSILON


@dataclass(frozen=True)
class SourceDivergence:
    """A two-source pair that disagrees past the sanity threshold.

    ``primary_source``/``primary_value`` is what to render — one source's own
    stated number, never a mixture. The rest is evidence for matching.
    """

    spread: float
    primary_source: str
    primary_value: float
    other_source: str
    other_value: float
    threshold: float = DIVERGENCE_SPREAD_THRESHOLD

    @property
    def sources(self) -> tuple[str, str]:
        return (self.primary_source, self.other_source)

    def as_evidence(self) -> dict:
        """Flat, loggable, issue-pasteable. No objects, no floats-as-repr."""
        return {
            "suspected_mislink": True,
            "spread": round(self.spread, 6),
            "threshold": self.threshold,
            "primary_source": self.primary_source,
            "primary_value": round(self.primary_value, 6),
            "other_source": self.other_source,
            "other_value": round(self.other_value, 6),
        }


def assess_divergence(
    readings: Mapping[str, float],
    weights: Mapping[str, float],
    *,
    threshold: float = DIVERGENCE_SPREAD_THRESHOLD,
    order: Optional[list[str]] = None,
) -> Optional[SourceDivergence]:
    """Return a verdict when EXACTLY two sources disagree past ``threshold``.

    ``weights`` are the EFFECTIVE weights the blend is about to use (post-decay,
    post-cap) — not the base table. See the module docstring: honouring decay is
    what keeps this gate from printing a stale pregame line over a live one.

    ``order`` is the tiebreak for a genuine weight tie, most-preferred first.
    Callers that have a display order (the futures merge anchors on the row that
    already holds the position) pass it; without one the tie falls back to the
    reading order, which is stable for a dict. A tie must resolve to SOMETHING
    deterministic — an undefined case in a gate resolves to whatever the reader
    guesses, and half will guess the other way.

    Returns ``None`` — meaning "blend normally" — for any population this gate
    does not govern: fewer or more than two sources, or a spread at or below the
    threshold.

    🔴 The "more than two" arm has a MEASURED hole: a third source decayed to the
    staleness floor is not a live opinion, but it still removes the event from
    this gate's population. See the SCOPE section of the module docstring for the
    specimen (event 15304937, 63 points apart and silent) and for why the
    obvious widening — governing the widest pair among N — is the wrong fix.
    """
    keys = list(readings.keys())
    if len(keys) != 2:
        return None

    a, b = keys
    va, vb = float(readings[a]), float(readings[b])
    spread = abs(va - vb)
    # The threshold is the top of the sane band, so a pair sitting exactly on
    # it is sane. Routed through `spread_exceeds` rather than a bare `>` for
    # the float reason given at the constant.
    if not spread_exceeds(spread, threshold):
        return None

    wa = float(weights.get(a, 0.0))
    wb = float(weights.get(b, 0.0))
    if wa > wb:
        primary, other = a, b
    elif wb > wa:
        primary, other = b, a
    else:
        ranked = order or keys
        primary = min(keys, key=lambda k: ranked.index(k) if k in ranked else len(ranked))
        other = b if primary == a else a

    return SourceDivergence(
        spread=spread,
        primary_source=primary,
        primary_value=float(readings[primary]),
        other_source=other,
        other_value=float(readings[other]),
        threshold=threshold,
    )
