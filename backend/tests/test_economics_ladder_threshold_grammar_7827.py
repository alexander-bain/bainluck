"""#7827: the /economics gold card priced "4,300 or above" at 8% against a book at 68.5%.

Read at 390px on production 2026-09-21 15:5xZ (`SHOT_SCROLL=8350`, docHeight
14555), in the METALS section #7809 had shipped four hours earlier:

    GOLD PRICE AT YEAR END?
    4,800 or above
    Modal bracket · 13.5%

      4,800 or above  13.5%      4,300 or above   8%
      4,400 or above   8.5%      5,400 or above   9.5%
      4,500 or above   8.5%      5,300 or above   6.5%

Two things are wrong before you know any mechanism. The rungs are out of order,
while copper and silver in the same section — same component — are in clean
price order. And the ladder is impossible: "or above" is cumulative, so
P(>=4,300) must be >= P(>=4,800), and the card had 8% over 13.5%.

THE VENUE DISAGREED BY SIXTY POINTS AND OUR OWN DB AGREED WITH THE VENUE.
Kalshi 2026-09-21 16:0xZ (`/trade-api/v2/markets?series_ticker=KXGOLDDIRY
&status=open`, 13 open rungs; prices live in the `*_dollars` fields):

    rung             venue bid/ask   venue mid   the page
    4,300 or above     0.67 / 0.70       68.5%       8.0%
    4,400 or above     0.57 / 0.60       58.5%       8.5%
    4,500 or above     0.49 / 0.51       50.0%       8.5%
    4,800 or above     0.31 / 0.37       34.0%      13.5%
    5,300 or above     0.16 / 0.19       17.5%       6.5%

`KXGOLDDIRY-26DEC31H1700-T4300` carries 23,641 open interest; this is not a
dead rung. And `futures_outcomes` held the venue's curve exactly, all thirteen
rungs — 0.665 / 0.585 / 0.500 / 0.415 / 0.365 / 0.340 / 0.205 / 0.195 / 0.185 /
0.185 / 0.175 / 0.095 / 0.110. Nothing upstream was broken. The whole defect
was in the render helper, which is why this file tests only that helper.

TWO INDEPENDENT DEFECTS, and fixing either alone still leaves a lying card:

  * THE THRESHOLD GRAMMAR HAD NO THOUSANDS SEPARATOR. `[\\d.]*` has no comma so
    it stops at one: "4,300 or above" and "4,800 or above" both parsed 4, all
    seven 4,xxx rungs tied and all six 5,xxx tied, and Python's stable sort left
    each group in DB order. That one fact produced all three symptoms — the
    scrambled draw order, a monotonicity clamp comparing the wrong neighbours,
    and differences subtracting non-adjacent thresholds. It is the same failure
    #7081 documented for the SIGN, by the same mechanism; #7081 hardened this
    regex for `-` and left the comma. Same family as #7806 / #7812.

  * THE LABEL STRIP ONLY KNEW THE PREFIX WORDING. Kalshi words this ladder as a
    suffix ("4,800 or above"), not a prefix ("Above 4,800"), so
    `label.replace("Above ", "")` was a no-op. The arithmetic below then
    converted cumulative -> discrete CORRECTLY and drew the result under the
    cumulative rung's own text. "8.5%" beside "4,400 or above" was really
    P(gold finishes between 4,400 and 4,500); the label claimed a thing that
    was 58.5%. This is the more dangerous half: with the sort fixed, the card
    would still print a bucket probability under an "or above" label.

BLAST RADIUS, measured on the open economics population before the repair
(`futures_outcomes` joined to open Kalshi markets on the economics ticker
families) rather than assumed, because this helper is shared with the CPI and
FOMC rate-path cards:

    shape                                   n      markets   verdict
    prefix "Above 3%", no comma          1,477         73     INERT
    prefix + comma "Above -25,000"          36          3     INERT
    compound "Headline: .. , Core: .."       6          1     INERT
    "More than 100,000"                      7          1     INERT
    suffix "100.01 or above" (WTI)         150          6     label only
    suffix + comma (this gold ladder)       13          1     repaired

The four INERT rows are byte-identical old-vs-new. The WTI rows change label
only — probabilities and order identical — which is the point of the anchored
suffix pattern: the CPI combo ladder says "Headline: 0.5% or above, Core: 0.3%
or above", and an unanchored strip would leave that a half-sentence.
"""

import re

import pytest

from app.routes.economics import _cumulative_to_discrete, _SUFFIX_THRESHOLD_RE


class _Outcome:
    """The two attributes the helper reads. Deliberately not a mock: a mock
    answers every attribute, which would hide a rename of either one."""

    def __init__(self, name, probability):
        self.name = name
        self.current_probability = probability


# The specimen, verbatim: the 13 rungs of KXGOLDDIRY-26DEC31H1700 with the
# probabilities `futures_outcomes` held at 16:10Z on 2026-09-21.
GOLD_LADDER = [
    ("4,300 or above", 0.665),
    ("4,400 or above", 0.585),
    ("4,500 or above", 0.500),
    ("4,600 or above", 0.415),
    ("4,700 or above", 0.365),
    ("4,800 or above", 0.340),
    ("4,900 or above", 0.205),
    ("5,000 or above", 0.195),
    ("5,100 or above", 0.185),
    ("5,200 or above", 0.185),
    ("5,300 or above", 0.175),
    ("5,400 or above", 0.095),
    ("5,500 or above", 0.110),
]


def _gold():
    return [_Outcome(n, p) for n, p in GOLD_LADDER]


def _strike(label):
    """The numeric strike a reader reads off a rendered label."""
    return float(re.sub(r"[^\d.\-]", "", label))


class TestThresholdGrammarAdmitsAThousandsSeparator:
    def test_the_drawn_rungs_are_in_strike_order(self):
        """The defect: 4,800 / 4,400 / 4,500 / 4,300 / 5,400 / 5,300."""
        brackets = _cumulative_to_discrete(_gold(), max_buckets=6)
        strikes = [_strike(label) for _, label in brackets]
        assert strikes == sorted(strikes), (
            "rungs drawn out of strike order: %s" % strikes
        )

    def test_the_helper_sorts_the_ladder_rather_than_inheriting_db_order(self):
        """The specimen SHUFFLED, which is the assertion that actually bites.

        The old helper was correct whenever the rungs happened to arrive in
        strike order — the tie in its sort key is invisible while the input is
        already sorted, because Python's sort is stable. It bit on production
        through the truncation re-sort, and it bites here through the only
        other door: `_outcomes_sorted` does not promise strike order, so the
        helper must establish it rather than inherit it. A guard fed
        pre-sorted input passes against the defect and proves nothing.
        """
        shuffled = [
            _Outcome(n, p)
            for n, p in [
                GOLD_LADDER[5],  # 4,800
                GOLD_LADDER[1],  # 4,400
                GOLD_LADDER[2],  # 4,500
                GOLD_LADDER[0],  # 4,300
                GOLD_LADDER[11],  # 5,400
                GOLD_LADDER[10],  # 5,300
            ]
        ]
        brackets = _cumulative_to_discrete(shuffled, max_buckets=13)
        strikes = [_strike(label) for _, label in brackets]

        # COUNT FIRST. Out of order, the defect does not merely scramble the
        # ladder — it annihilates it. The clamp compares each rung against the
        # wrong neighbour and flattens six cumulatives onto two values, the
        # differences round to zero, and the `>= 0.1` filter drops them: these
        # six rungs came back as two. An order-only assertion passes on that
        # wreckage, because two surviving rungs are trivially sorted.
        assert len(brackets) == len(shuffled), (
            "ladder lost rungs to the clamp: kept %d of %d — %s"
            % (len(brackets), len(shuffled), strikes)
        )
        assert strikes == sorted(strikes), (
            "helper inherited DB order instead of sorting: %s" % strikes
        )
        assert len(set(strikes)) == len(strikes), (
            "rungs in one thousand collapsed onto each other: %s" % strikes
        )

    def test_a_date_in_a_label_still_parses_its_day_not_its_year(self):
        """The separator group is exactly three digits, so "Sep 21, 2026" must
        not glue into 212026 and fling that label to the end of the ladder."""
        outcomes = [
            _Outcome("Above 1% on Sep 21, 2026", 0.9),
            _Outcome("Above 2% on Sep 21, 2026", 0.6),
            _Outcome("Above 3% on Sep 21, 2026", 0.3),
        ]
        brackets = _cumulative_to_discrete(outcomes, max_buckets=10)
        assert [p for p, _ in brackets] == [30.0, 30.0, 30.0]

    def test_a_negative_threshold_keeps_its_sign_through_the_separator(self):
        """#7081's case must survive the widening.

        This one is a REGRESSION guard, not a defect-killer: it passes against
        the pre-change helper too, because "Above -25,000" and "Above 10,000"
        parsed -25 and 10, which happen to order correctly. It is here to stop
        the widened grammar from re-breaking the sign #7081 fixed, and it is
        labelled as such so nobody reads it as evidence of this repair.
        """
        outcomes = [
            _Outcome("Above 10,000", 0.5),
            _Outcome("Above -25,000", 0.9),
            _Outcome("Above 100,000", 0.1),
        ]
        brackets = _cumulative_to_discrete(outcomes, max_buckets=10)
        assert [label for _, label in brackets] == ["-25,000", "10,000", "100,000"]


class TestTheLabelStopsClaimingToBeCumulative:
    def test_no_drawn_label_says_or_above(self):
        """A discrete bucket probability may not wear a cumulative label."""
        brackets = _cumulative_to_discrete(_gold(), max_buckets=6)
        offenders = [label for _, label in brackets if "above" in label.lower()]
        assert offenders == [], (
            "bucket probabilities drawn under cumulative labels: %s" % offenders
        )

    def test_the_repaired_card_is_the_measured_one(self):
        """The whole card, pinned: strike order, honest labels, and the
        differences the venue's own curve implies."""
        brackets = _cumulative_to_discrete(_gold(), max_buckets=6)
        assert brackets == [
            [8.0, "4,300"],
            [8.5, "4,400"],
            [8.5, "4,500"],
            [13.5, "4,800"],
            [8.0, "5,300"],
            [9.5, "5,500"],
        ]

    def test_the_buckets_sum_to_the_loosest_rungs_own_probability(self):
        """A set of buckets above 4,300 must sum to P(>=4,300) = 66.5%.

        Fed SHUFFLED for the reason given above: summed over a pre-sorted
        input this holds against the defect too, because the differencing is
        only wrong once the order is.
        """
        shuffled = [_Outcome(n, p) for n, p in reversed(GOLD_LADDER)]
        brackets = _cumulative_to_discrete(shuffled, max_buckets=99)
        assert sum(p for p, _ in brackets) == pytest.approx(66.5, abs=0.2)

    @pytest.mark.parametrize(
        "label,expected",
        [
            ("4,800 or above", "4,800"),
            ("$100 or above", "$100"),
            ("100.01 or above", "100.01"),
            ("0.3% or above", "0.3%"),
            ("60 or more", "60"),
            ("75 or higher", "75"),
        ],
    )
    def test_the_suffix_pattern_takes_a_bare_threshold(self, label, expected):
        match = _SUFFIX_THRESHOLD_RE.match(label)
        assert match is not None, "should have matched: %r" % label
        assert match.group(1) == expected

    @pytest.mark.parametrize(
        "label",
        [
            "Headline: 0.5% or above, Core: 0.3% or above",
            "Headline: Exactly 0.3%, Core: 0.3% or above",
            "Headline: 0.2% or below, Core: 0.3% or above",
        ],
    )
    def test_the_suffix_pattern_refuses_a_compound_label(self, label):
        """Anchored on purpose. An unanchored strip would leave the CPI combo
        ladder reading "Headline: 0.5% or above, Core: 0.3%" — a half-sentence,
        and a worse lie than the one being fixed."""
        assert _SUFFIX_THRESHOLD_RE.match(label) is None


class TestTheSharedCallersDoNotMove:
    """`_cumulative_to_discrete` also draws the CPI and FOMC rate-path cards
    (1,477 outcomes across 73 open markets). Those labels are prefix-worded and
    must come through the repair byte-identical."""

    @pytest.mark.parametrize(
        "labels",
        [
            ["Above 0.1%", "Above 0.2%", "Above 0.3%", "Above 0.5%"],
            ["Above -0.4%", "Above -0.2%", "Above 0.0%", "Above 0.2%"],
            ["Above 3%", "Above 4%", "Above 9.5%"],
            ["Above $100", "Above $105", "Above $110"],
            # prefix AND a separator: the payrolls ladder, which sorted
            # correctly before only because every rung shared a group width.
            ["Above -25,000", "Above 10,000", "Above 90,000", "Above 125,000"],
            # neither wording; untouched by both arms of the repair.
            ["More than 50,000", "More than 100,000", "More than 150,000"],
        ],
    )
    def test_a_prefix_worded_ladder_keeps_its_labels_and_its_order(self, labels):
        probabilities = [0.9, 0.7, 0.5, 0.3, 0.2, 0.1][: len(labels)]
        outcomes = [_Outcome(n, p) for n, p in zip(labels, probabilities)]
        brackets = _cumulative_to_discrete(outcomes, max_buckets=10)

        # Every label is its input with only the prefix removed — the strip the
        # helper has always done — and none acquired a rewrite.
        for (_, drawn), original in zip(brackets, labels):
            assert drawn == original.replace("Above ", "").strip()

        strikes = [_strike(label) for _, label in brackets]
        assert strikes == sorted(strikes)

    def test_a_suffix_worded_ladder_changes_its_label_and_nothing_else(self):
        """The WTI ladders (150 outcomes, 6 markets) are the one shared family
        the repair reaches. Order and probabilities must be untouched."""
        labels = ["75 or above", "80 or above", "85 or above", "90 or above"]
        probabilities = [0.9, 0.7, 0.5, 0.3]
        outcomes = [_Outcome(n, p) for n, p in zip(labels, probabilities)]
        brackets = _cumulative_to_discrete(outcomes, max_buckets=10)

        assert [p for p, _ in brackets] == [20.0, 20.0, 20.0, 30.0]
        assert [label for _, label in brackets] == ["75", "80", "85", "90"]
