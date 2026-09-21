"""#7667 — a DEADLINE ladder whose preposition is in the question is not divided either.

PILLAR: TRUTH. SHIP: a Discover card stops printing 61.7% for a market whose own
page prints 72.5%.

Fourth shape of the class #7641, #7650 and #7674 fixed. Polymarket's deadline
series writes the preposition ONCE, in the question, with a blank where the date
goes:

    Next Muse Spark (1.4+) released by...?
        September 30 .45    October 31 .725                     (60197960)

Substituting a leg into the blank gives back an ordinary "by October 31" rung —
which #7650's grammar already reads — so the legs nest, their sum is not a total,
and .725 / 1.175 printed .617. MEASURED on the deployed feed 2026-09-21 02:52Z and
reproduced by `artifacts/d357-7667/sibling-census.py`, which prices the widening at
all four sites the one predicate feeds: 0 of 102 banked feed cards move, 31 of 264
open deadline-question markets have their divisor repaired (largest 49.0 pt), 0
bars change, 0 fields collapse.

═══ WHY THE QUESTION AND NOT THE LEGS, WHICH IS THE WHOLE RISK OF THIS SHIP ═══

A bare date carries no direction, and this is the exact ambiguity #7650 stopped
short of on purpose. The SAME leg list is a nested ladder or an exclusive
partition depending only on the preposition:

    Next Muse Spark (1.4+) released by...?         nested    (60197960)
    Will gas be below $3.75 in any state on...?    exclusive (61305564)

`test_the_exclusive_twin_is_refused_on_the_specimens_own_legs` is the control that
matters most: it hands the grammar the NESTED specimen's own leg shapes under the
exclusive question and requires a refusal, so the ship cannot rest on an accident
of today's leg text. The live exclusive control is adversarial on purpose — its
question also contains `below`, a direction word, which must not bind because it
introduces no blank.
"""

import re

import pytest

from app.routes.feed import (
    _feed_display_scale,
    _leader_is_ladder_rung,
    _outcomes_are_cumulative_ladder,
)
from app.utils import ladder_monotonicity
from app.utils.ladder_monotonicity import (
    DEC,
    INC,
    cumulative_outcome_ladder,
    question_ladder_date_word,
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


#: `60197960` to the leg and to the price, off `futures_outcomes` 2026-09-21, in
#: the order the API serves them (NOT rung order — the grammar sorts, and a test
#: that pre-sorts would hide it if it stopped).
MUSE_SPARK = [("October 31", 0.725), ("September 30", 0.45)]
MUSE_SPARK_Q = "Next Muse Spark (1.4+) released by...?"

#: `61305564` — the live exclusive control. Bare-date legs of the same shape, an
#: `on...?` blank, and a direction word in the question that must not bind.
GAS_BY_STATE = [("October 31", 0.18), ("September 30", 0.06),
                ("September 20", 0.0405)]
GAS_BY_STATE_Q = "Will gas be below $3.75 in any state on...?"

#: `61584627` — the shape 167 of the 261 open `by...?` markets carry: a companion
#: binary's `Yes`/`No` legs merged in with the dates.
SAUDI_AIRSPACE = [("No", 0.85), ("December 31", 0.215), ("Yes", 0.15),
                  ("October 31", 0.105), ("September 30", 0.055)]
SAUDI_AIRSPACE_Q = "Saudi airspace closed by...?"


def rows(pairs):
    return [{"name": name, "probability": prob} for name, prob in pairs]


def named(pairs):
    return [{"name": name} for name, _ in pairs]


def outcomes(pairs):
    return [_Outcome(name, prob) for name, prob in pairs]


# ── the ship ───────────────────────────────────────────────────────────────

def test_the_specimen_is_read_as_one_ascending_deadline_ladder():
    ladder = cumulative_outcome_ladder(named(MUSE_SPARK), question=MUSE_SPARK_Q)
    assert ladder is not None
    legs, direction = ladder
    assert direction == INC
    assert [row["name"] for _value, row in legs] == ["September 30", "October 31"]


def test_the_specimen_card_stops_dividing_by_the_sum_of_its_nested_legs():
    """The reader-visible ship: .725 printed as .725, not as .617."""
    assert _feed_display_scale(outcomes(MUSE_SPARK)) == pytest.approx(1.175)
    assert _feed_display_scale(outcomes(MUSE_SPARK), MUSE_SPARK_Q) == 1.0


def test_the_split_the_issue_reported_is_exactly_the_divisor():
    before = _feed_display_scale(outcomes(MUSE_SPARK))
    after = _feed_display_scale(outcomes(MUSE_SPARK), MUSE_SPARK_Q)
    assert round(0.725 / before, 3) == 0.617
    assert round(0.725 / after, 3) == 0.725


def test_the_four_letter_dot_blank_is_the_same_blank():
    """`ChatGPT Outage by....?` (60093934) writes the blank with four dots."""
    assert question_ladder_date_word("ChatGPT Outage by....?") == "by"


def test_an_underscore_blank_is_the_same_blank():
    """`NVIDIA (NVDA) all-time high by ___?` (58957126) writes it with underscores."""
    assert question_ladder_date_word("NVIDIA (NVDA) all-time high by ___?") == "by"


def test_after_is_the_one_descending_deadline_word():
    ladder = cumulative_outcome_ladder(
        named([("September 30", 0.4), ("October 31", 0.2)]),
        question="Does the ban still stand after...?")
    assert ladder is not None
    assert ladder[1] == DEC


# ── the controls: what must KEEP its divisor ───────────────────────────────

def test_the_exclusive_twin_is_refused_on_the_specimens_own_legs():
    """THE control. The nested specimen's legs, under the exclusive question.

    If this passed only because the live `on...?` markets happen to carry a
    `Yes`/`No` or a prose leg, the ship would be resting on an accident of
    today's data rather than on the rule it claims.
    """
    assert cumulative_outcome_ladder(named(MUSE_SPARK), question=GAS_BY_STATE_Q) is None


def test_the_live_exclusive_control_keeps_its_divisor_at_every_site():
    assert question_ladder_date_word(GAS_BY_STATE_Q) is None
    assert cumulative_outcome_ladder(named(GAS_BY_STATE), question=GAS_BY_STATE_Q) is None
    assert not _outcomes_are_cumulative_ladder(outcomes(GAS_BY_STATE), GAS_BY_STATE_Q)


def test_a_direction_word_that_introduces_no_blank_does_not_bind():
    """`below` sits in the live control's question and must not be read."""
    assert "below" in GAS_BY_STATE_Q
    assert question_ladder_direction(GAS_BY_STATE_Q) is None
    assert question_ladder_date_word(GAS_BY_STATE_Q) is None


def test_continues_through_is_not_a_deadline_word():
    """`US-Iran ceasefire continues through...?` (61300895) is a real shape this
    grammar deliberately does not read — its rungs run the other way, and no
    census has priced it."""
    assert question_ladder_date_word("US-Iran ceasefire continues through...?") is None


@pytest.mark.parametrize("question", [
    "Best shop nearby...?",
    "Does it happen afterwards...?",
    "Is the deal done thereby...?",
])
def test_a_deadline_word_inside_another_word_does_not_bind(question):
    assert question_ladder_date_word(question) is None


def test_two_deadline_words_refuse_rather_than_pick_one():
    assert question_ladder_date_word("Lands after...? and before...?") is None


def test_a_question_stating_both_a_comparator_and_a_deadline_is_refused():
    """The two grammars would otherwise compete for the same legs, and
    `September 30` parses as the magnitude 30 under a label — so the competition
    has a real winner and it is the wrong one."""
    both = "Does GOOGL close above ___ by...?"
    assert question_ladder_direction(both) is not None
    assert question_ladder_date_word(both) is None
    assert cumulative_outcome_ladder(named(MUSE_SPARK), question=both) is None


def test_a_merged_companion_binary_disqualifies_its_whole_market():
    """167 of the 261 open `by...?` markets carry `Yes`/`No` legs. An unreadable
    leg disqualifies the market under the all-legs rule, so they are unchanged."""
    assert question_ladder_date_word(SAUDI_AIRSPACE_Q) == "by"
    assert cumulative_outcome_ladder(
        named(SAUDI_AIRSPACE), question=SAUDI_AIRSPACE_Q) is None
    assert _feed_display_scale(
        outcomes(SAUDI_AIRSPACE), SAUDI_AIRSPACE_Q) == pytest.approx(1.375)


def test_a_prose_leg_disqualifies_its_market():
    """`No release by September 30` (59133750, 61246729) is not a bare date."""
    assert cumulative_outcome_ladder(
        named([("September 30", 0.1), ("No release by September 30", 0.5)]),
        question="Next Google Gemini Pro Model released by...?") is None


def test_a_family_mixing_a_question_read_date_with_a_leg_read_one_is_refused():
    """The affix key is namespaced `qdate:` against `date:` for exactly this."""
    assert cumulative_outcome_ladder(
        named([("September 30", 0.45), ("by October 31", 0.725)]),
        dates=True, question=MUSE_SPARK_Q) is None


def test_a_duplicate_rung_still_refuses():
    assert cumulative_outcome_ladder(
        named([("September 30", 0.4), ("Sep 30", 0.5)]),
        question=MUSE_SPARK_Q) is None


def test_one_leg_is_never_a_ladder():
    assert cumulative_outcome_ladder(
        named([("September 30", 0.45)]), question=MUSE_SPARK_Q) is None


def test_the_year_fence_still_refuses_a_quantity_shaped_leg():
    """`5000` is a quantity, not a year, and refusing it disqualifies its market."""
    assert cumulative_outcome_ladder(
        named([("5000", 0.4), ("September 30", 0.5)]),
        question=MUSE_SPARK_Q) is None


def test_a_month_with_no_day_is_pinned_to_the_ceiling_under_by():
    """`by September` is through the 30th, so it sits AFTER every dated rung in
    that month — the convention `_DATE_CEIL_WORDS` already sets for leg-read
    dates, reached here through the same shared helper."""
    ladder = cumulative_outcome_ladder(
        named([("September", 0.6), ("September 30", 0.45)]), question=MUSE_SPARK_Q)
    assert ladder is not None
    assert [row["name"] for _value, row in ladder[0]] == ["September 30", "September"]


# ── the widening is opt-in, and the prior fixes are untouched ──────────────

def test_the_widening_is_off_by_default():
    assert cumulative_outcome_ladder(named(MUSE_SPARK)) is None
    assert cumulative_outcome_ladder(named(MUSE_SPARK), dates=True) is None
    assert _feed_display_scale(outcomes(MUSE_SPARK)) == pytest.approx(1.175)


def test_every_prior_ladder_is_byte_unchanged_by_the_widening():
    """A leg that carries its own comparator or its own date is never re-read
    under the question's, so #7641's, #7650's and #7674's censuses stay true."""
    magnitude = named([("Above 175", 0.965), ("Above 200", 0.4), ("Above 225", 0.28)])
    dated = named([("Before Jan 1, 2027", 0.32), ("Before April 2027", 0.74)])

    # Each prior shape, read with and without a deadline question in play. The
    # answers must be EQUAL and must not be None — an equality between two
    # refusals would pass while proving nothing.
    for legs, dates in ((magnitude, False), (magnitude, True), (dated, True)):
        without = cumulative_outcome_ladder(legs, dates=dates)
        with_question = cumulative_outcome_ladder(
            legs, dates=dates, question=MUSE_SPARK_Q)
        assert without is not None
        assert without == with_question

    # #7674's strike ladder keeps its own reading, and its question is read by
    # the magnitude grammar rather than this one.
    strike = named([("$345", 0.91), ("$350", 0.645), ("$355", 0.245)])
    strike_q = "Google (GOOGL) closes above ___ on September 21?"
    assert question_ladder_date_word(strike_q) is None
    assert cumulative_outcome_ladder(strike, question=strike_q) is not None


def test_the_shared_date_body_did_not_drift_when_it_was_extracted():
    """`_CUMULATIVE_DATE_RE` was recomposed over `_DATE_BODY` so two grammars
    read one date. This pins it against the literal it was extracted from."""
    original = re.compile(
        r"^\s*(?P<dword>before|by|after)\s+(?:"
        r"(?P<mon>jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
        r"(?:\s+(?P<day>\d{1,2})(?!\d))?(?:,?\s*(?P<yr>\d{4}))?"
        r"|(?P<bare>\d{4})"
        r")\s*\.?\s*$", re.I)
    for text in ("before Jan 2027", "by April 2027", "after Mar 2027",
                 "by Oct 31, 2026", "before 2027", "by 5000", "September 30",
                 "by September 30.", "Before Jan 1, 2027", "by Sep 3 2026",
                 "Jan-Mar 2027", "by", "by December 31, 2029", "nearby 2027"):
        mine = ladder_monotonicity._CUMULATIVE_DATE_RE.match(text)
        theirs = original.match(text)
        assert (mine is None) == (theirs is None), text
        if mine is not None:
            assert mine.groupdict() == theirs.groupdict(), text


# ── all four sites the one predicate feeds ─────────────────────────────────

def test_the_leader_copy_stops_naming_a_nested_ladders_loosest_rung():
    """#4640: the latest deadline is the LOOSEST rung, never the favorite."""
    assert not _leader_is_ladder_rung(rows(MUSE_SPARK))
    assert _leader_is_ladder_rung(rows(MUSE_SPARK), MUSE_SPARK_Q)


def test_the_bars_a_card_draws_do_not_move():
    """Censused at 0 of 264; pinned so a later widening cannot move them quietly."""
    name_of, prob_of = (lambda o: o["name"]), (lambda o: o["probability"])
    assert (drop_incoherent_ladder_outcomes(rows(MUSE_SPARK), name_of, prob_of)
            == drop_incoherent_ladder_outcomes(
                rows(MUSE_SPARK), name_of, prob_of, MUSE_SPARK_Q))


def test_the_field_does_not_collapse():
    name_of, prob_of = (lambda o: o["name"]), (lambda o: o["probability"])
    assert (ladder_treatment_collapsed(rows(MUSE_SPARK), name_of, prob_of)
            == ladder_treatment_collapsed(
                rows(MUSE_SPARK), name_of, prob_of, MUSE_SPARK_Q))


# ── the mutation this file exists to catch ─────────────────────────────────

def test_stubbing_the_question_reader_restores_the_defect(monkeypatch):
    """The whole file in one assertion: with `question_ladder_date_word` blinded,
    the specimen is divided again. A guard that cannot fail is not a guard."""
    monkeypatch.setattr(
        ladder_monotonicity, "question_ladder_date_word", lambda _q: None)
    assert cumulative_outcome_ladder(named(MUSE_SPARK), question=MUSE_SPARK_Q) is None
    assert _feed_display_scale(
        outcomes(MUSE_SPARK), MUSE_SPARK_Q) == pytest.approx(1.175)
