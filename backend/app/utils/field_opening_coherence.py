"""A one-winner field whose openings are not a distribution was never priced.

WHAT A READER SAW (#5539). ``/futures/12337998`` — *Women's 2027 College
Basketball Champion* — printed **OPEN 99%** against all thirty-five teams, and
the chart caption underneath read *"South Carolina down 74.4 pts from opening."*
Every entrant supposedly opened at 99% to win the championship; North Carolina
St. supposedly opened at 99% and fell to 1%. None of it happened. The stored
``opening_probability`` is 0.99 on all 35 legs, ``opening_source =
'bid_ask_midpoint'``, every leg captured in the same instant — the midpoint of
an untraded 0.98/1.00 book, which the venue quotes before anybody trades.

The harm is the comparison the row invites, not the number in isolation: two
columns headed OPEN and LATEST read as a move, and the move is the fabrication.

WHY A COHERENCE RULE AND NOT A VALUE RULE. The obvious fix — "suppress the
opening that too many legs of one market share" — was measured on production
(2026-09-12, open Kalshi markets) and is WRONG. Legs sharing an opening value
are overwhelmingly honest longshots:

    shared opening   market/value groups (>=3 legs)   legs
    0.005                     99                      1,014
    0.015                    137                        867
    0.025                    107                        616
    0.030                    107                        727
    0.035                    108                        591

19,095 legs sit in >=3-leg shared-value groups, and most are real prices on a
big field. A value rule suppresses them to reach the seeds. So the rule here is
arithmetic about the FIELD, never about any single price.

THE RULE, AND WHY EACH HALF IS LOAD-BEARING. In a mutually exclusive field of
``n >= MIN_FIELD_LEGS`` outcomes exactly one wins, so the true probabilities sum
to 1 and their mean is at most ``1/n`` — at loosest ``1/3``. Both of these must
hold before the openings are refused, and production shows each one sparing a
population the other would wrongly take (open markets, 2026-09-12):

                                          kalshi    polymarket
    refused (both conditions)            204 mk      796 mk
                                       4,638 legs  11,129 legs
    spared by the MEAN condition          76 mk       79 mk
    spared by the SUM condition           91 mk      203 mk
    odds_api, every market                 0           0

*Spared by the mean* are large honest fields: openings are captured per leg as
legs are added, so a 100-leg field assembled over months drifts past a sum of 3
while every price in it is real and tiny. *Spared by the sum* are small fields
carrying ordinary overround — a 3-leg market at a mean 0.42 sums to 1.26, which
is a vig story, not a fabrication. The boundary cases are the proof: *Oscar
Winner: Best Picture* (35 legs, sum 2.04, mean 0.058) and *How many border
encounters in Feb 2026?* (8 legs, sum 2.04, mean 0.255) are both real staggered
captures and both stay published.

:data:`FIELD_MEAN_CEILING` is DERIVED, not tuned: ``1/3`` is the largest mean any
honest field of three or more can carry, so a ceiling above it can never refuse a
field that could be a distribution at any ``n``. :data:`FIELD_SUM_CEILING` is the
measured gap — honest fields, staggered ones included, sit between 1.0 and ~2.1.

WHY IT REFUSES RATHER THAN REPAIRS, and why NULL is the honest answer: this is
:mod:`app.utils.pair_opening_coherence`'s rule at N legs instead of two, and its
reasoning transfers verbatim. Rescaling the field to sum to 1 would invent an
opening — it asserts a price nobody quoted, and afterwards it is indistinguishable
from one that was. ``calibration_probability`` falls back to
``opening_probability`` (gotcha #144 / ruling 103, a coalesce and not an
exclusion), so an invented opening becomes a published forecast we are then
graded on. A withheld opening is simply a column the page does not print.

THIS IS A SERVE-TIME RULE AND THAT IS DELIBERATE. The rows were stamped months
ago (the specimen's in February 2026), so a write guard cannot reach them —
CERT-2508's finding on the sibling rail, that a guard keyed on ``IS NULL`` cannot
see a row that is already non-null. Refusing at serve time reaches every stored
row at once and reverts in one line. The writer-side guard and the stored-row
repair are the durable follow-up and are tracked on #5539.
"""

from __future__ import annotations

from typing import Iterable, Optional

#: The smallest field this rule speaks about. Below three legs there is no
#: impossible mean to appeal to: a two-leg binary that opened 0.50/0.50 is a
#: coin flip summing to exactly 1, and production carries 31 honest ones.
MIN_FIELD_LEGS = 3

#: Highest total a one-winner field's openings may carry and still be published.
#: A coherent field sums to 1; measured honest fields reach ~2.1 through
#: overround and staggered per-leg capture. Above three times certainty there is
#: no pricing story left.
FIELD_SUM_CEILING = 3.0

#: Highest MEAN opening a one-winner field may carry and still be published.
#: The honest mean of an ``n``-leg field is ``1/n``, so ``1/3`` bounds every
#: field this rule can see. This sits above that bound, which is what keeps a
#: large honest field — whose mean is tiny however far its sum has drifted —
#: out of reach of the rule.
FIELD_MEAN_CEILING = 0.4

OK = "ok"
NOT_APPLICABLE_NOT_EXCLUSIVE = "not_applicable_not_exclusive"
NOT_APPLICABLE_FIELD_TOO_SMALL = "not_applicable_field_too_small"
REFUSED_FIELD_NOT_A_DISTRIBUTION = "refused_field_not_a_distribution"

#: Verdicts that mean "do not publish any opening in this field".
REFUSAL_VERDICTS = (REFUSED_FIELD_NOT_A_DISTRIBUTION,)


def classify_field_openings(
    openings: Iterable[Optional[float]],
    mutually_exclusive: bool,
) -> str:
    """Say whether a field's opening prices may be published, and why.

    ``openings`` is one entry per leg the surface intends to show, in any order;
    ``None`` entries are legs with no stored opening and are ignored rather than
    counted as zero — "nobody recorded an opening" is not "the opening was 0"
    (gotcha #53). The verdict is about the WHOLE field, so a caller that has
    already dropped legs from its display list should pass the list it will
    actually print: that is the set whose coherence the page is claiming.
    """
    if not mutually_exclusive:
        return NOT_APPLICABLE_NOT_EXCLUSIVE

    priced = [float(p) for p in openings if p is not None]
    if len(priced) < MIN_FIELD_LEGS:
        return NOT_APPLICABLE_FIELD_TOO_SMALL

    total = sum(priced)
    if total > FIELD_SUM_CEILING and (total / len(priced)) >= FIELD_MEAN_CEILING:
        return REFUSED_FIELD_NOT_A_DISTRIBUTION
    return OK


def field_openings_publishable(
    openings: Iterable[Optional[float]],
    mutually_exclusive: bool,
) -> bool:
    """True when this field's openings may be shown. See :func:`classify_field_openings`."""
    return classify_field_openings(openings, mutually_exclusive) not in REFUSAL_VERDICTS
