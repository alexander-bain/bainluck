"""#7674 — a strike ladder whose COMPARATOR IS IN THE QUESTION is not divided either.

PILLAR: TRUTH. SHIP: a Discover card stops printing 47% for a market whose own
page prints 91%.

#7641 fixed the magnitude half of this class and #7650 the date half. This is the
third shape and the largest gap of the three. Polymarket's strike series writes
the comparator ONCE, in the question, with a blank where the leg goes:

    Google (GOOGL) closes above ___ on September 21?
        $345 .91   $350 .645   $355 .245   $360 .065   $365 .074      (61381313)

Substituting a leg into the blank gives back an ordinary "above $345" rung, so the
legs nest and their sum is not a total. MEASURED on the deployed feed 2026-09-21,
cross-read against `/api/futures/61381313`: .91 / 1.939 -> .4693, a 44.1-point
split, and the split is exactly the divisor.

═══ WHY THE QUESTION AND NOT THE LEGS, WHICH IS THE WHOLE RISK OF THIS SHIP ═══

A bare magnitude carries no direction, and guessing one is how an exclusive bucket
field becomes a fake ladder. The same weekly series ships BOTH structures, and the
legs alone cannot tell them apart:

    Will Google (GOOGL) finish week of September 21 above___?     nested
    Apple (AAPL) closes week of Sep 21 at ___?                    exclusive

`test_the_exclusive_twin_is_refused_on_legs_that_look_identical` is the control
that matters most here: it hands the grammar the nested specimen's own leg shapes
under the exclusive question and requires a refusal. If that passes only because
the real `at ___` market happens to carry RANGE legs, the ship is resting on an
accident of today's data rather than on the rule it claims.

`cumulative_outcome_ladder` is ONE predicate read by four reader-visible sites, so
the widening is opt-in (`question=None`) exactly as `dates=` is, and
`test_every_prior_ladder_is_byte_unchanged_by_the_widening` is the control that
keeps the two prior fixes' censuses true.
"""

import pytest

from app.routes.feed import (
    _feed_display_scale,
    _leader_is_ladder_rung,
    _outcomes_are_cumulative_ladder,
)
from app.utils.ladder_monotonicity import (
    cumulative_outcome_ladder,
    question_ladder_direction,
)
from app.utils.outcome_display import (
    drop_incoherent_ladder_outcomes,
    ladder_treatment_collapsed,
)


class _Outcome:
    """The two shapes `_feed_display_scale` sees — a live ORM `FuturesOutcome`
    and a rebuilt snapshot row — agree on these two attributes."""

    def __init__(self, name, probability):
        self.name = name
        self.current_probability = probability


#: `61381313` to the leg and to the price, off `futures_outcomes` 2026-09-21,
#: in the order the API serves them (NOT rung order — the grammar sorts, and a
#: test that pre-sorts would hide it if it stopped).
GOOGL_DAILY = [
    ("$345", 0.91),
    ("$350", 0.645),
    ("$355", 0.245),
    ("$365", 0.074),
    ("$360", 0.065),
]
GOOGL_DAILY_Q = "Google (GOOGL) closes above ___ on September 21?"

#: `61425459`, the 7-rung WEEKLY twin. Its sum is 4.12, so the `all_sum > 2.0`
#: arm already held it at raw — it is here to prove the fix does not move a card
#: that was already right, and that the proxy is not what we are relying on.
GOOGL_WEEKLY = [
    ("$330", 0.94), ("$335", 0.89), ("$340", 0.80), ("$345", 0.66),
    ("$350", 0.50), ("$360", 0.21), ("$365", 0.12),
]
GOOGL_WEEKLY_Q = "Will Google (GOOGL) finish week of September 21 above___?"

#: `61425453`, the EXCLUSIVE twin of the same series, legs and all.
AAPL_BUCKETS = [("$330-$335", 0.22), ("$325-$330", 0.15), ("$320-$325", 0.08)]
AAPL_BUCKETS_Q = "Apple (AAPL) closes week of Sep 21 at ___?"


def _scale(pairs, question=None):
    return _feed_display_scale([_Outcome(n, p) for n, p in pairs], question)


def _is_ladder(pairs, question=None):
    return _outcomes_are_cumulative_ladder(
        [_Outcome(n, p) for n, p in pairs], question)


# ── THE SHIP ────────────────────────────────────────────────────────────────

def test_the_card_stops_dividing_the_strike_ladder_by_its_own_rungs():
    """The specimen, at the divisor, before and after. 0.91 not 0.4693."""
    assert _scale(GOOGL_DAILY) == pytest.approx(1.939)  # the defect
    assert _scale(GOOGL_DAILY, GOOGL_DAILY_Q) == 1.0  # the fix

    leader = GOOGL_DAILY[0][1]
    assert round(leader / _scale(GOOGL_DAILY), 4) == 0.4693
    assert round(leader / _scale(GOOGL_DAILY, GOOGL_DAILY_Q), 4) == 0.91


def test_the_split_the_reader_saw_was_exactly_the_divisor():
    """Every printed leg, not just the leader — the card had one basis wrong."""
    scale = _scale(GOOGL_DAILY)
    for _, price in GOOGL_DAILY:
        assert round(price / scale, 4) == pytest.approx(price / 1.939, abs=1e-4)


# ── THE CONTROL THAT CARRIES THE SHIP'S RISK ────────────────────────────────

def test_the_exclusive_twin_is_refused_on_legs_that_look_identical():
    """The comparator is the discriminator, not the shape of the legs.

    The real `at ___` market carries RANGE legs, which the affix rule refuses on
    its own. That refusal is a second, independent guard and it must not be what
    this test is measuring — so the legs here are the NESTED specimen's own bare
    magnitudes, moved under the exclusive question. A refusal here is a fact
    about the question and nothing else.

    Priced into the dividing band on purpose. The real bucket field sums to 0.45,
    where `_feed_display_scale` returns 1.0 for a reason that has nothing to do
    with ladders — so a refusal measured there would be unfalsifiable.
    """
    bare_under_exclusive_question = [("$330", 0.90), ("$335", 0.50), ("$340", 0.40)]
    assert _is_ladder(bare_under_exclusive_question, AAPL_BUCKETS_Q) is False
    assert _scale(bare_under_exclusive_question, AAPL_BUCKETS_Q) == pytest.approx(1.8)
    # …and the SAME legs under the nested question are not divided at all.
    assert _scale(bare_under_exclusive_question, GOOGL_DAILY_Q) == 1.0

    # …and the real market, whose range legs are refused a second way.
    assert _is_ladder(AAPL_BUCKETS, AAPL_BUCKETS_Q) is False


@pytest.mark.parametrize("question", [
    "Where does GOOGL close between ___ and ___?",   # two-sided template
    "GOOGL closes above ___ or below ___?",          # two directions
    "Apple (AAPL) closes week of Sep 21 at ___?",    # blank, no comparator
    "Will the above-average rainfall continue, closing at ___?",  # word, not the leg's
    "Google (GOOGL) closes above $345 on September 21?",  # no blank at all
    "MLB World Series Winner",                        # no blank, no comparator
    "",
    None,
])
def test_a_question_that_does_not_state_one_direction_reads_nothing(question):
    """`None`, never a guess — and the card keeps the basis it has today."""
    assert question_ladder_direction(question) is None
    assert _is_ladder(GOOGL_DAILY, question) is False


def test_the_direction_comes_from_the_word_and_is_not_inferred_from_prices():
    assert question_ladder_direction("GOOGL closes above ___?") == "dec"
    assert question_ladder_direction("GOOGL closes below ___?") == "inc"


@pytest.mark.parametrize("legs", [
    [("$345", 0.9), ("$345", 0.6)],            # duplicate rung value
    [("$345", 0.9), ("Yes", 0.6)],             # a leg the grammar cannot read
    [("$345", 0.9)],                           # a ladder of one is never a ladder
    [("$345", 0.9), ("$350-$355", 0.6)],       # one range leg disqualifies the set
])
def test_the_other_discriminators_still_do_their_work_under_a_question(legs):
    """The question may say WHICH WAY a ladder runs. It may never say a set IS one."""
    assert _is_ladder(legs, GOOGL_DAILY_Q) is False


# ── THE FOUR SITES THE ONE PREDICATE FEEDS ──────────────────────────────────

def test_both_feed_predicates_answer_this_field_the_same_way():
    """Or the card calls it a ladder for its copy and a distribution for its
    numbers — the incoherence `_leader_is_ladder_rung` is paired against."""
    dicts = [{"name": n, "probability": p} for n, p in GOOGL_DAILY]
    for question in (None, GOOGL_DAILY_Q, AAPL_BUCKETS_Q):
        assert (
            _leader_is_ladder_rung(dicts, question)
            is _is_ladder(GOOGL_DAILY, question)
        )


def test_the_live_specimens_own_dip_is_noise_and_costs_it_no_rung():
    """`$365` at .074 sits .009 ABOVE `$360` at .065 — arithmetically a reversal
    on a nested family, and deliberately NOT one here: it is inside
    `_LADDER_MONOTONE_TOLERANCE` (0.02), which exists because a rung dipping half
    a cent under its neighbour is bid/ask noise and not something a reader can
    see is impossible. So reading this field as a ladder must cost it no bar. The
    ship is the divisor; it is not a licence to start deleting rungs.
    """
    rows = [{"name": n, "probability": p} for n, p in GOOGL_DAILY]
    name_of, prob_of = (lambda o: o["name"]), (lambda o: o["probability"])

    assert drop_incoherent_ladder_outcomes(rows, name_of, prob_of) == rows
    assert drop_incoherent_ladder_outcomes(
        rows, name_of, prob_of, GOOGL_DAILY_Q) == rows
    assert ladder_treatment_collapsed(rows, name_of, prob_of, GOOGL_DAILY_Q) is False


def test_the_incoherent_rung_law_is_nonetheless_reachable_through_a_question():
    """And it has to be, or the card reads one field two ways: a ladder at the
    divisor, an unrelated set of binaries at the bars. Same legs as the specimen
    with `$360` moved to .60 — a 35-point break, far outside the noise band.
    """
    broken = [("$345", 0.91), ("$350", 0.645), ("$355", 0.245),
              ("$365", 0.074), ("$360", 0.60)]
    rows = [{"name": n, "probability": p} for n, p in broken]
    name_of, prob_of = (lambda o: o["name"]), (lambda o: o["probability"])

    assert drop_incoherent_ladder_outcomes(rows, name_of, prob_of) == rows
    kept = drop_incoherent_ladder_outcomes(rows, name_of, prob_of, GOOGL_DAILY_Q)
    assert [row["name"] for row in kept] == ["$345", "$350", "$355", "$365"]

    # Four rungs of five survive — a field, not a collapse.
    assert ladder_treatment_collapsed(rows, name_of, prob_of, GOOGL_DAILY_Q) is False


def test_a_coherent_strike_ladder_loses_no_rung():
    """The weekly twin is priced perfectly, so the law has nothing to say."""
    rows = [{"name": n, "probability": p} for n, p in GOOGL_WEEKLY]
    name_of, prob_of = (lambda o: o["name"]), (lambda o: o["probability"])
    assert drop_incoherent_ladder_outcomes(
        rows, name_of, prob_of, GOOGL_WEEKLY_Q) == rows


def test_the_already_correct_weekly_card_does_not_move():
    """Sum 4.12 was held at raw by the `> 2.0` arm and is held at raw now, but
    for the structural reason rather than the proxy."""
    assert _scale(GOOGL_WEEKLY) == 1.0
    assert _scale(GOOGL_WEEKLY, GOOGL_WEEKLY_Q) == 1.0
    assert _is_ladder(GOOGL_WEEKLY, GOOGL_WEEKLY_Q) is True


# ── THE CONTROL THAT KEEPS THE PRIOR CENSUSES TRUE ──────────────────────────

@pytest.mark.parametrize("legs,question", [
    ([("Above 175", 0.965), ("Above 150", 0.99)], GOOGL_DAILY_Q),
    ([("Before Jan 1, 2027", 0.455), ("Before Oct 1, 2026", 0.32)], GOOGL_DAILY_Q),
    ([("Los Angeles Dodgers", 0.28), ("Milwaukee Brewers", 0.13)], GOOGL_DAILY_Q),
    ([("$330-$335", 0.22), ("$325-$330", 0.15)], GOOGL_DAILY_Q),
])
def test_every_prior_ladder_is_byte_unchanged_by_the_widening(legs, question):
    """A leg that carries its OWN comparator, or its own date, or no threshold at
    all, is read exactly as it was — the question branch is tried last and cannot
    re-read a leg an earlier grammar already answered. This is the assertion that
    fails if someone later makes the question grammar reachable first.
    """
    assert _is_ladder(legs, question) is _is_ladder(legs, None)
    assert _scale(legs, question) == _scale(legs, None)


def test_a_question_read_leg_never_shares_a_family_with_a_comparator_leg():
    """Namespaced affix key. Mixing is usually one ladder written two ways, but
    "usually" is not a proof, so the set is refused rather than assumed."""
    assert _is_ladder([("Above $345", 0.9), ("$350", 0.6)], GOOGL_DAILY_Q) is False


def test_the_grammar_is_off_unless_a_caller_asks_for_it():
    """The opt-in itself, at the predicate — not at any one call site."""
    rows = [{"name": n} for n, _ in GOOGL_DAILY]
    assert cumulative_outcome_ladder(rows, dates=True) is None
    assert cumulative_outcome_ladder(rows, dates=True, question=None) is None
    assert cumulative_outcome_ladder(
        rows, dates=True, question=GOOGL_DAILY_Q) is not None
