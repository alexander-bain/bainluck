"""#6470 — a Discover card stops arriving with no caption at all.

WHAT A READER SAW, on production `/api/feed?limit=60` at 2026-09-16 04:1xZ
(release v4606 `2bd74e55`), phone width 390px: **6 of the 60 cards on page one
carried no caption of any kind** — `reason: ''`, `headline: null`,
`card_sum_reason: null`, `hook_description: null`, so both clients'
`firstMeaningful([...])` chain had nothing to print and the card showed a hole
where every neighbour showed a sentence.

    idx 24  Anthropic IPO by __?                                    Dec 31, 2026  60%
    idx 37  European country agrees to give Ukraine security …?     Dec 31         8%
    idx 43  NATO x Russia military clash by...?                     Dec 31        27%
    idx 47  Will Samuel Alito announce his retirement by...?        Jun 30, 2027  32%
    idx 50  Will Ukraine recapture Crimean territory by...?         Dec 31         6%
    idx 51  Will Russia announce a new forced mobilization by...?   Dec 31        27%

Every one is Polymarket and every one is the same shape: a deadline board whose
leading leg is a bare calendar date. They die at `_weak_outcome_label`, which
refuses "December 31" as the SUBJECT of a sentence — correctly, because the
label alone cannot say whether the market means *by* that date or *during* it.
`leader_is_ladder_rung` (#4640) never gets a say: `cumulative_outcome_ladder`
returns `None` for every one of these boards, because a date leg parses as no
cumulative threshold this codebase knows.

WHAT THIS SHIP DOES: supplies the sentence the refusal was missing, as a LEVEL
("60% chance by December 31, 2026") rather than a comparative. The missing word
comes from the VENUE — it is the preposition `#3513`'s display rule DELETES from
the title ("Anthropic IPO by __?" -> "Anthropic IPO?"), i.e. Polymarket's own
statement that its members fill a deadline slot. Read off the structure, per
notices 26/27, never guessed from the shape of the label.

🔴 WHY A LEVEL AND NOT A RANKING, AND WHY THAT IS THE WHOLE SAFETY ARGUMENT.
These boards are not all coherent. Alito's rungs, measured the same morning:

    Sep 30  0.6%   Dec 31  5.5%   Feb 28  0.6%
    Mar 31  0.2%   Jun 30 2027 31.5%   Jul 15  0.1%

which is non-monotonic in the date under ANY assignment of the missing years, so
a sentence that RANKED these legs would be printing a broken board as news — a
TRUTH defect strictly worse than the silence it replaced. A level clause names
one leg's own price and asserts nothing about any other leg, so it stays true
whatever the rest of the board is doing. `TestTheIncoherentBoardStillGetsOnlyALevel`
is that guarantee.

🔴 THE TESTS THAT MATTER MOST HERE ARE THE CONTROLS, for the reason #3513's are:
the risk is not "does it fire" but "what else does it reach". Four populations
are pinned SILENT, and each control also asserts it is silent FOR ITS OWN REASON
— flip only the gate under test and the caption appears — so none of them can
pass vacuously once some unrelated branch changes:

  * the elided word is not "by" (`on`, `at`, `through`, `as`)
  * the title elided nothing at all — the date is already printed in it
  * the leading label is not a date
  * the board is a proven cumulative ladder, where #4640's refusal still wins

Plus the default: a caller that passes no preposition gets byte-identical copy
to the day before this shipped, which is every card on the page but these.
"""

import pytest

from app.utils.feed_reasons import (
    DEADLINE_PREPOSITION,
    generate_futures_context_summary,
    generate_futures_headline,
    generate_futures_reason,
)
from app.utils.market_display_name import (
    _STRIPPABLE_PREPOSITIONS,
    clean_market_display_name,
    elided_trailing_preposition,
)

# The six cards above, as (raw stored name, leading label, probability, the
# percent the card actually PRINTS for that row). Names and prices are the
# production rows, not fixtures: `futures_markets` ids 30635376, 114077, 113013,
# 131023, 113016, 59525885 read at 2026-09-16 04:1xZ.
PHOTOGRAPHED = [
    ("Anthropic IPO by __?", "December 31, 2026", 0.5989, 60),
    ("European country agrees to give Ukraine security guarantee by...? ",
     "December 31", 0.075, 8),
    ("NATO x Russia military clash by...?", "December 31", 0.265, 27),
    ("Will Samuel Alito announce his retirement by...?", "June 30, 2027", 0.315, 32),
    ("Will Ukraine recapture Crimean territory by...?", "December 31", 0.055, 6),
    ("Will Russia announce a new forced mobilization by...?", "December 31", 0.265, 27),
]

# The words that make a card reach the leader-sentence fallback at all. Taken
# from the live trace of id 30635376 (`score_anatomy.highlight_reasons`), so the
# branch these tests exercise is the branch the six cards took.
LIVE_REASONS = ["major_surprise"]


def _copy(raw_name, leader, probability, pct, *, preposition, reasons=None,
          leader_is_ladder_rung=False):
    """The three caption slots a card can fill, for one market.

    Composed exactly as `routes/feed.py` composes them: the generators receive
    the CLEANED title, and the deadline word is read off the RAW one.
    """
    shared = dict(
        market_name=clean_market_display_name(raw_name),
        highlight_reasons=list(reasons if reasons is not None else LIVE_REASONS),
        leader_name=leader,
        leader_probability=probability,
        rendered_leader_percent=pct,
        leader_is_ladder_rung=leader_is_ladder_rung,
        leader_deadline_preposition=preposition,
    )
    headline = generate_futures_headline(**shared)
    return {
        "reason": generate_futures_reason(**shared),
        "headline": headline,
        "context_summary": generate_futures_context_summary(
            headline=headline or None, **shared
        ),
    }


def _served(raw_name, leader, probability, pct, **kwargs):
    """What the clients' `firstMeaningful` chain would actually print."""
    slots = _copy(raw_name, leader, probability, pct, **kwargs)
    for key in ("context_summary", "headline", "reason"):
        if (slots[key] or "").strip():
            return slots[key].strip()
    return ""


def _live(raw_name, leader, probability, pct, **kwargs):
    """As the route calls it: the preposition comes from the raw name."""
    return _served(raw_name, leader, probability, pct,
                   preposition=elided_trailing_preposition(raw_name), **kwargs)


class TestThePhotographedCards:
    """The ship: each of the six stops printing nothing."""

    @pytest.mark.parametrize("raw,leader,prob,pct", PHOTOGRAPHED)
    def test_the_card_now_carries_a_caption(self, raw, leader, prob, pct):
        assert _live(raw, leader, prob, pct) == f"{pct}% chance by {leader}"

    @pytest.mark.parametrize("raw,leader,prob,pct", PHOTOGRAPHED)
    def test_and_printed_nothing_before_this_shipped(self, raw, leader, prob, pct):
        # The `preposition=None` arm IS the previous behaviour — the parameter
        # defaults to None, so this is the byte-for-byte before-state and not a
        # reconstruction of it.
        assert _served(raw, leader, prob, pct, preposition=None) == ""

    @pytest.mark.parametrize("raw,leader,prob,pct", PHOTOGRAPHED)
    def test_every_slot_agrees(self, raw, leader, prob, pct):
        # One sentence, whichever slot the client reads. A card whose headline
        # and caption disagreed about the same row is #4056's defect.
        slots = _copy(raw, leader, probability=prob, pct=pct,
                      preposition=elided_trailing_preposition(raw))
        assert len(set(slots.values())) == 1, slots


class TestTheSentenceMakesNoComparativeClaim:
    """#4640 is not reopened: the clause ranks nothing."""

    FORBIDDEN = ("lead", "favorite", "favourite", "ahead", "top", "beats")

    @pytest.mark.parametrize("raw,leader,prob,pct", PHOTOGRAPHED)
    def test_no_ranking_word_reaches_the_reader(self, raw, leader, prob, pct):
        printed = _live(raw, leader, prob, pct).lower()
        assert printed
        for word in self.FORBIDDEN:
            assert word not in printed, printed


class TestTheIncoherentBoardStillGetsOnlyALevel:
    """The Alito board, whose rungs contradict containment.

    Its legs cannot all be right, and this is the case the gate is NOT allowed
    to reason about: a level clause about the row the card draws stays true on a
    broken board, which is exactly why the ship is a level.
    """

    RAW = "Will Samuel Alito announce his retirement by...?"

    def test_it_names_the_leading_rung_and_only_that_rung(self):
        printed = _live(self.RAW, "June 30, 2027", 0.315, 32)
        assert printed == "32% chance by June 30, 2027"

    @pytest.mark.parametrize("other", ["December 31", "February 28", "March 31",
                                       "September 30", "July 15"])
    def test_it_mentions_no_other_rung(self, other):
        assert other not in _live(self.RAW, "June 30, 2027", 0.315, 32)


# ---------------------------------------------------------------------------
# THE CONTROLS. Each asserts silence, then asserts that the silence is caused by
# the gate under test and not by some unrelated branch.
# ---------------------------------------------------------------------------

class TestAnElidedWordThatIsNotByStaysSilent:
    """"on"/"at"/"through"/"as" bound a POINT, not a deadline.

    "GPT-5.5 released on...?" with a December 31 leg means released ON that day;
    printing "by" would be a different and unmeasured claim. The display rule
    strips all six words; only one of them licenses this sentence.
    """

    OTHERS = [p for p in _STRIPPABLE_PREPOSITIONS if p != DEADLINE_PREPOSITION]

    def test_the_list_this_control_covers_is_not_empty(self):
        # Vacuity guard: if `_STRIPPABLE_PREPOSITIONS` is ever reduced to just
        # "by", the parametrize below silently tests nothing.
        assert self.OTHERS

    @pytest.mark.parametrize("preposition", OTHERS)
    def test_silent(self, preposition):
        raw = f"GPT-5.5 released {preposition}...?"
        assert elided_trailing_preposition(raw) == preposition
        assert _live(raw, "December 31", 0.4, 40) == ""

    @pytest.mark.parametrize("preposition", OTHERS)
    def test_and_only_the_word_is_stopping_it(self, preposition):
        raw = f"GPT-5.5 released {preposition}...?"
        assert _served(raw, "December 31", 0.4, 40,
                       preposition=DEADLINE_PREPOSITION) == "40% chance by December 31"


class TestATitleThatElidedNothingStaysSilent:
    """No blank means the venue never asked us to supply an object.

    "Which countries will join the Mecca Agreement by December 31?" already
    prints its deadline and its legs are COUNTRIES; the "by" in it governs a date
    that is written out. A rule keyed on the word rather than on the elision
    would read this title as a deadline board.
    """

    NO_BLANK = [
        "Which countries will join the Mecca Agreement by December 31?",
        "Will Trump issue Obamacare rebates before Election Day?",
        "Will China invade Taiwan by end of 2026?",
        "Which party will win the U.S. House?",
    ]

    @pytest.mark.parametrize("raw", NO_BLANK)
    def test_nothing_is_elided(self, raw):
        assert elided_trailing_preposition(raw) is None
        assert clean_market_display_name(raw) == raw

    @pytest.mark.parametrize("raw", NO_BLANK)
    def test_silent_even_when_the_leader_is_a_date(self, raw):
        assert _live(raw, "December 31", 0.4, 40) == ""

    @pytest.mark.parametrize("raw", NO_BLANK)
    def test_and_only_the_missing_elision_is_stopping_it(self, raw):
        assert _served(raw, "December 31", 0.4, 40,
                       preposition=DEADLINE_PREPOSITION) == "40% chance by December 31"


class TestALeaderThatIsNotADateDoesNotGetTheClause:
    """The clause dates a bound; a label with no date in it cannot.

    Asserted as "unchanged" rather than "silent" on purpose. These labels split
    two ways under the PREVIOUS rules — "$245" and "5" are weak and printed
    nothing, "Republicans" and "Above 120" are nameable and printed "leads at
    40%" — and the ship's claim is the same for both halves: the deadline word
    in the title changes neither. A control that asserted silence would be
    asserting the wrong thing for half its own corpus, and would fail the day a
    label's weakness classification moved for an unrelated reason.
    """

    NOT_DATES = ["Yes", "No", "Above 120", "$245", "29,900 to 29,999.99",
                 "Republicans", "5", "3.5%", "December", "2026", "Q4",
                 "Before Jan 20, 2029"]

    @pytest.mark.parametrize("leader", NOT_DATES)
    def test_the_deadline_word_changes_nothing(self, leader):
        raw = "Anthropic IPO by __?"
        assert elided_trailing_preposition(raw) == DEADLINE_PREPOSITION
        assert _live(raw, leader, 0.4, 40) == _served(
            raw, leader, 0.4, 40, preposition=None)

    @pytest.mark.parametrize("leader", NOT_DATES)
    def test_and_never_dates_a_bound(self, leader):
        assert "chance by" not in _live("Anthropic IPO by __?", leader, 0.4, 40)

    def test_the_corpus_covers_both_halves_of_the_split(self):
        # Vacuity guard: if every label above became weak (or none did), the two
        # tests would still pass while exercising one behaviour.
        raw = "Anthropic IPO by __?"
        printed = {bool(_served(raw, leader, 0.4, 40, preposition=None))
                   for leader in self.NOT_DATES}
        assert printed == {True, False}

    def test_and_a_date_in_the_same_slot_speaks(self):
        assert _live("Anthropic IPO by __?", "December 31", 0.4, 40) == (
            "40% chance by December 31"
        )


class TestAProvenCumulativeLadderIsStillRefused:
    """#4640 wins where it applies: nesting is not a contest, with or without a
    preposition in front of it. Nothing on production reaches BOTH gates today —
    a date leg parses as no cumulative threshold — so this control pins the
    intersection before some later grammar creates it."""

    def test_silent(self):
        assert _live("Anthropic IPO by __?", "December 31, 2026", 0.6, 60,
                     leader_is_ladder_rung=True) == ""

    def test_and_only_the_ladder_flag_is_stopping_it(self):
        assert _live("Anthropic IPO by __?", "December 31, 2026", 0.6, 60,
                     leader_is_ladder_rung=False) == "60% chance by December 31, 2026"


class TestTheDefaultIsTheStatusQuo:
    """An uninformed caller — every one that has not been taught the parameter —
    gets the copy it got before this shipped."""

    CARDS = [
        ("MLB World Series Winner", "Los Angeles Dodgers", 0.31, 31),
        ("Anthropic IPO by __?", "December 31, 2026", 0.5989, 60),
        ("Amazon 2026 capex above ___?", "Above 120", 0.45, 45),
        ("Will EUR/USD hit __ in 2026?", "1.25", 0.22, 22),
    ]

    @pytest.mark.parametrize("raw,leader,prob,pct", CARDS)
    def test_omitting_the_parameter_matches_passing_none(self, raw, leader, prob, pct):
        shared = dict(
            market_name=clean_market_display_name(raw),
            highlight_reasons=list(LIVE_REASONS),
            leader_name=leader,
            leader_probability=prob,
            rendered_leader_percent=pct,
        )
        assert (generate_futures_reason(**shared)
                == generate_futures_reason(**shared, leader_deadline_preposition=None))
        assert (generate_futures_headline(**shared)
                == generate_futures_headline(**shared, leader_deadline_preposition=None))
        assert (
            generate_futures_context_summary(headline=None, **shared)
            == generate_futures_context_summary(
                headline=None, leader_deadline_preposition=None, **shared)
        )

    def test_a_nameable_leader_is_untouched_by_the_new_parameter(self):
        # The clause may only ever replace SILENCE. A card that already had a
        # sentence keeps exactly that sentence, deadline word or not.
        raw = "Anthropic IPO by __?"
        assert _live(raw, "Los Angeles Dodgers", 0.31, 31) == _served(
            raw, "Los Angeles Dodgers", 0.31, 31, preposition=None)


class TestTheCaptionNeverRestoresAWordTheTitleStillPrints:
    """One grammar, two readers.

    `elided_trailing_preposition` and `clean_market_display_name` are driven by
    the same `_trailing_blank_parts`, so a name whose word is reported here is
    by construction a name whose word was removed there. If the two ever came
    apart, a card would read "Anthropic IPO by?" over "60% chance by December
    31" — the word twice, governing two different things.
    """

    NAMES = [raw for raw, _, _, _ in PHOTOGRAPHED] + [
        "GPT-5.5 released on...?",
        "Amazon 2026 capex above ___?",
        "Will EUR/USD hit __ in 2026?",
        "Netflix (NFLX) closes week of Sep 14 at ___?",
        "Which countries will join the Mecca Agreement by December 31?",
        "MLB World Series Winner",
        "",
    ]

    @pytest.mark.parametrize("raw", NAMES)
    def test_a_reported_word_is_a_removed_word(self, raw):
        preposition = elided_trailing_preposition(raw)
        if preposition is None:
            return
        cleaned = clean_market_display_name(raw)
        assert cleaned != raw
        assert not cleaned.rstrip(" ?").lower().endswith(" " + preposition), cleaned

    def test_the_sample_above_actually_contains_both_verdicts(self):
        verdicts = {elided_trailing_preposition(raw) is None for raw in self.NAMES}
        assert verdicts == {True, False}


# ===========================================================================
# THE REMAINDER, measured 2026-09-16 on release v4612 `154be569` — which already
# carried #6470. Three of the six cards above were STILL blank.
# ===========================================================================

class TestABoardThatCollapsedToOneLiveRung:
    """#6470's own remainder: the level clause never reached a one-leg board.

    WHAT A READER SAW, production `/api/feed?limit=60` at 2026-09-16 05:5xZ,
    with #6470 live: three of its six cards still served `reason: ''`,
    `headline: null`, `context_summary: ''`, `hook_description: null`.

        idx 34  European country agrees to give Ukraine security …?  Dec 31   8%
        idx 41  NATO x Russia military clash?                        Dec 31  27%
        idx 48  Will Ukraine recapture Crimean territory?            Dec 31   6%

    WHY THOSE THREE AND NOT THE OTHER THREE. Nothing about the boards' titles or
    their dates differs — what differs is how many rungs are still LIVE. The
    serving path drops every rung whose own deadline has passed
    (`_expired_ladder_rungs`), and on 2026-09-16 these three had exactly one
    survivor each (measured: 113013 lost `June 30`, `March 31` and
    `December 31, 2025`; 113016 and 114077 each lost `June 30`). A one-outcome
    list is what `binary_affirmative_outcome` calls a yes/no question, so all
    three generators short-circuit into `compose_binary_card_copy` — which sits
    ABOVE the level clause and has no way to reach it. Anthropic IPO, Alito and
    the Russia-mobilization board each kept two or more live rungs, stayed on the
    field path, and got their caption from #6470 as designed.

    The proof that this is the whole story, and not a story about these three
    markets: `/api/admin/discover-quality/trace/{id}` recomposes from
    `_top_outcomes_for_trace`, which does NOT drop expired rungs, and it printed
    "27% chance by December 31" for 113013 in the same minute the feed served
    "". Same market, same code, same release — the only difference is how many
    legs survived into the call.
    """

    # (raw stored name, the one surviving leg, its price, the percent the card
    # prints for it) — `futures_markets` 113013, 113016, 114077.
    COLLAPSED = [
        ("NATO x Russia military clash by...?", "December 31", 0.265, 27),
        ("Will Ukraine recapture Crimean territory by...?", "December 31", 0.055, 6),
        ("European country agrees to give Ukraine security guarantee by...? ",
         "December 31", 0.075, 8),
    ]

    @staticmethod
    def _slots(raw, leader, prob, pct, *, preposition, reasons=None,
               leader_is_ladder_rung=False, **extra):
        """As `routes/feed.py` calls it for a board with ONE live leg.

        The difference from `_copy` above — and the reason that helper's cards
        passed while production printed nothing — is `affirmative_probability`:
        a single-leg list makes it the leg's own price instead of None, which is
        the branch the three blank cards actually took.
        """
        shared = dict(
            market_name=clean_market_display_name(raw),
            highlight_reasons=list(reasons if reasons is not None else LIVE_REASONS),
            leader_name=leader,
            leader_probability=prob,
            rendered_leader_percent=pct,
            leader_is_ladder_rung=leader_is_ladder_rung,
            leader_deadline_preposition=preposition,
            affirmative_probability=prob,
            rendered_affirmative_percent=pct,
            **extra,
        )
        headline = generate_futures_headline(**shared)
        return {
            "reason": generate_futures_reason(**shared),
            "headline": headline,
            "context_summary": generate_futures_context_summary(
                headline=headline or None, **shared
            ),
        }

    @classmethod
    def _served(cls, raw, leader, prob, pct, **kwargs):
        slots = cls._slots(raw, leader, prob, pct, **kwargs)
        for key in ("context_summary", "headline", "reason"):
            if (slots[key] or "").strip():
                return slots[key].strip()
        return ""

    @classmethod
    def _live(cls, raw, leader, prob, pct, **kwargs):
        return cls._served(raw, leader, prob, pct,
                           preposition=elided_trailing_preposition(raw), **kwargs)

    @pytest.mark.parametrize("raw,leader,prob,pct", COLLAPSED)
    def test_the_card_now_carries_a_caption(self, raw, leader, prob, pct):
        assert self._live(raw, leader, prob, pct) == f"{pct}% chance by {leader}"

    @pytest.mark.parametrize("raw,leader,prob,pct", COLLAPSED)
    def test_and_printed_nothing_before_this_shipped(self, raw, leader, prob, pct):
        # `deadline_label` defaults to None, and with no elided "by" there is no
        # label to pass — so this arm IS the released behaviour, byte for byte,
        # not a reconstruction of it.
        assert self._served(raw, leader, prob, pct, preposition=None) == ""

    @pytest.mark.parametrize("raw,leader,prob,pct", COLLAPSED)
    def test_the_web_cards_own_slot_is_the_one_that_fills(self, raw, leader, prob, pct):
        # `FuturesCard.tsx` prints `context_summary`. A fix that filled only the
        # reason would pass `_served` and change nothing a reader sees.
        slots = self._slots(raw, leader, prob, pct,
                            preposition=elided_trailing_preposition(raw))
        assert slots["context_summary"] == f"{pct}% chance by {leader}"

    @pytest.mark.parametrize("raw,leader,prob,pct", COLLAPSED)
    def test_the_caption_states_no_comparative(self, raw, leader, prob, pct):
        printed = self._live(raw, leader, prob, pct).lower()
        for word in ("lead", "favorite", "favourite", "ahead", "top", "beats"):
            assert word not in printed, printed


class TestTheCollapsedBoardsPercentIsTheHerosOwn:
    """The number in the caption is the AFFIRMATIVE's, never the leader basis.

    The two bases are the same row on a one-leg board, so a composer that took a
    pre-rendered clause built from `rendered_leader_percent` would agree today
    and be wrong the first time they diverge. Feeding a deliberately different
    leader percent proves which one the sentence is built from.
    """

    RAW = "NATO x Russia military clash by...?"

    def test_the_sentence_follows_the_affirmative_percent(self):
        slots = TestABoardThatCollapsedToOneLiveRung._slots(
            self.RAW, "December 31", 0.265, 27,
            preposition="by",
        )
        assert slots["context_summary"] == "27% chance by December 31"

    def test_a_divergent_leader_percent_does_not_move_the_caption(self):
        shared = dict(
            market_name=clean_market_display_name(self.RAW),
            highlight_reasons=list(LIVE_REASONS),
            leader_name="December 31",
            leader_probability=0.265,
            # The card's hero prints 27; only the leader basis is perturbed.
            rendered_leader_percent=99,
            leader_deadline_preposition="by",
            affirmative_probability=0.265,
            rendered_affirmative_percent=27,
        )
        assert generate_futures_headline(**shared) == "27% chance by December 31"


class TestTheCollapsedBoardControls:
    """What the new arm must NOT reach. Each control asserts silence AND that the
    silence is its own gate's doing — flip only that gate and the caption
    appears — so none can pass vacuously when an unrelated branch changes."""

    def _served(self, *a, **kw):
        return TestABoardThatCollapsedToOneLiveRung._served(*a, **kw)

    def test_a_genuine_yes_no_pair_has_no_date_to_be_a_bound_on(self):
        # "Yes" is not a calendar label, so there is no level clause to print
        # and the #4056 terminal still owns this card.
        raw = "Will China invade Taiwan by...?"
        assert self._served(raw, "Yes", 0.04, 4, preposition="by") == ""
        # ...and the gate really is the LABEL: swap in a date and it speaks.
        assert self._served(raw, "December 31", 0.04, 4,
                            preposition="by") == "4% chance by December 31"

    def test_a_proven_cumulative_ladder_is_still_refused(self):
        # #4640's refusal outranks the clause on the binary path exactly as it
        # does on the field path.
        raw = "Fed cuts rates by...?"
        assert self._served(raw, "December 31", 0.4, 40, preposition="by",
                            leader_is_ladder_rung=True) == ""
        assert self._served(raw, "December 31", 0.4, 40, preposition="by",
                            leader_is_ladder_rung=False) == "40% chance by December 31"

    @pytest.mark.parametrize("word", ["on", "at", "through", "as"])
    def test_an_elided_word_that_is_not_by_stays_silent(self, word):
        raw = "GPT-5.5 released on...?"
        assert self._served(raw, "December 31", 0.4, 40, preposition=word) == ""
        assert self._served(raw, "December 31", 0.4, 40,
                            preposition="by") == "40% chance by December 31"

    def test_a_market_past_its_resolution_stays_silent(self):
        # `stale_past_resolution` returns above every arm in the composer, and
        # must keep doing so: a dead market saying "40% chance by December 31"
        # would be a truth defect, not a caption.
        raw = "NATO x Russia military clash by...?"
        assert self._served(raw, "December 31", 0.4, 40, preposition="by",
                            reasons=["stale_past_resolution"]) == ""
        assert self._served(raw, "December 31", 0.4, 40, preposition="by",
                            reasons=["major_surprise"]) == "40% chance by December 31"

    def test_a_live_signal_still_outranks_the_deadline(self):
        # The deadline is the LAST rung before silence, never a promotion over a
        # sentence about this morning. A board that moved today says so.
        raw = "NATO x Russia military clash by...?"
        assert self._served(
            raw, "December 31", 0.265, 27, preposition="by",
            reasons=["major_movement_24h"], top_mover_change=0.06,
        ) == "Up 6 points today — now 27% chance"

    def test_a_card_that_is_resolving_this_week_still_says_so(self):
        raw = "NATO x Russia military clash by...?"
        printed = self._served(raw, "December 31", 0.265, 27, preposition="by",
                               reasons=["resolving_soon_7d"])
        assert "resolving within a week" in printed
        assert "by December 31" not in printed
