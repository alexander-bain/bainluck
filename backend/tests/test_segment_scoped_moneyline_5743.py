"""#5743 — an explicit "Moneyline" must also say WHICH part of the match.

THE DEFECT, AND WHY #5698 DID NOT CATCH IT. #5698 scoped the bare word
`Winner`, so `… : Set 1 Winner` and `… : 1st Half Winner` stopped classifying
`moneyline`. The identical defect walks through the door one word over:
`_MONEYLINE_WORD_RE` matched `moneyline` anywhere and `is_game_winner_market`
returned True with no branch asking which contest — so Polymarket's
`76ers vs. Celtics: 1H Moneyline`, a FIRST-HALF book, was admitted as the
speaker for the whole match. Same class as #5031 / #5273 / #5432 / #5698,
reached from the one direction those left open.

THE POPULATION, MEASURED BY EXECUTING THE SHIPPED RECOGNIZER AT THE PRODUCTION
CALL SITE over real names (2026-09-12) — after `_strip_category_prefix`, which
is the only measurement that counts, because measuring the raw function
overstates the reach of any change to it (#5660). Of the 305 distinct market
names that carry a moneyline or winner word AND any segment scope, the
recognizer classified 304 `moneyline` before this fix and 88 after: **216 names
flip, every one of them moneyline -> other** (this fix can only ever narrow),
covering **282 rows** — 280 of them Polymarket NBA first-half books, all
`resolved`, newest `commence_time` 2026-06-07. The 88 that keep their number
are genuine whole-match playoff games ("Who will win Bucks v. Suns: NBA Finals
Game 4?") and not one segment book survives.

🔴 ALL 216 FLIPS COME FROM THE COMPRESSED ARM; the ordinal arm
(`half 1` / `1st half`) matches **zero** names on this door, because the venue
writes "1H Moneyline" and never "1st Half Moneyline". It is kept as the
fail-closed margin, the posture #5660 already takes with
`_DERIVATIVE_SCOPE_RE`. Stated here so no later reader mistakes
`test_every_part_word_is_visible_to_the_moneyline_test` for evidence that the
ordinal arm is load-bearing on production data — it is a vocabulary-drift
guard, not a population claim.

🔴 THE LIVE COUNT IS 0 BECAUSE THE NBA IS OUT OF SEASON, not because the shape
is gone. These are regular-season and playoff first-half books; they return at
tip-off. The honest framing is dormant, not safe — which is the whole reason
the deadline on #5743 is the season opener rather than "whenever".

TWO THINGS THE INHERITED DIAGNOSIS GOT WRONG, both corrected by measuring:

  * #5743 recorded that `1H Winner` has zero rows ever, and concluded the
    winner door needs no compressed form. It censused `%1h winner%` and
    `%2h winner%` only. The compressed winner form DOES exist — with a Q:
    `Knicks vs. Spurs: 1Q Winner` (Polymarket), plus Kalshi's parlay
    `CBB Tournament Combo: UConn vs Michigan 1H/Winner`. So the compressed
    token is given to BOTH doors, and `TestTheCompressedFormReachesBothDoors`
    is what keeps them from drifting apart again.

  * The two doors cannot share one scope vocabulary, and the data says so
    loudly. See `TestTheMoneylineDoorSubtractsRoundAndLeg`.
"""

import pytest

from app.utils.game_market_class import (
    _COMPRESSED_SEGMENT,
    _MONEYLINE_SCOPE_WORDS,
    _MONEYLINE_WORD_RE,
    _SEGMENT_SCOPED_MONEYLINE_RE,
    _SEGMENT_SCOPED_WINNER_RE,
    _WINNER_SCOPE_WORDS,
    classify_game_market_class,
    is_bare_matchup,
    is_game_winner_market,
    outcomes_refute_game_winner,
)
from app.utils.live_blend import admissible_as_blend_speaker
from app.utils.prediction_market_matching import (
    _strip_category_prefix,
    feeds_win_prob_blend,
)


class _Market:
    """Only the attributes the code under test actually reads."""

    def __init__(self, mid, name, *, source="polymarket", external_id=None):
        self.id = mid
        self.name = name
        self.source = source
        self.external_id = external_id
        self.market_metadata = None


def _at_call_site(name, external_id=None):
    """Classify the way production does it, not the way the function reads.

    `_class_says_game_winner` calls the recognizer as
    `classify(_strip_category_prefix(name), external_id)`. Measuring the raw
    function overstates the reach of any change to it — the error this lane
    made on #5660 and corrected in the open.
    """
    return classify_game_market_class(_strip_category_prefix(name), external_id)


# Real rows — name, external id and source exactly as production holds them,
# 2026-09-12. The first three are the 280-row Polymarket cohort; the last two
# are the compressed WINNER form that #5743's own census missed.
SEGMENT_MONEYLINES = [
    ("76ers vs. Celtics: 1H Moneyline",
     "0x8e3e0d27ea3b2ee4a1f9f6a9c0f0f0a1b2c3d4e5", "polymarket"),
    ("Knicks vs. Spurs: 1H Moneyline",
     "0x1a2b3c4d5e6f708192a3b4c5d6e7f8091a2b3c4d", "polymarket"),
    ("Bucks vs. Nets: 1H Moneyline",
     "0x9f8e7d6c5b4a39281706f5e4d3c2b1a09f8e7d6c", "polymarket"),
    ("Knicks vs. Spurs: 1Q Winner",
     "0x2e4c6dc85a1eb1744ec7b10840c98531a45c4ae3636f3189168d4cd2bdd762cd",
     "polymarket"),
    ("CBB Tournament Combo: UConn vs Michigan 1H/Winner",
     "KXNCAAMBSGP-26APR06CONNMICH1HFT", "kalshi"),
]

# Titles that DO decide a whole contest and must keep their number. All are
# real production names; the "Round 2" entries are the four games the winner
# door's own vocabulary would have cost (see the class below).
WHOLE_MATCH_TITLES = [
    "2022 NBA Playoffs, Round 2: Who will win Celtics vs. Bucks?",
    "2022 NBA Playoffs, Round 2: Who will win Suns vs. Mavericks?",
    "Who will win Bucks v. Suns: NBA Finals Game 4?",
    "2021 World Series: Who will win Braves v. Astros Game 3 on October 29th?",
    "1860 Munich vs Kiel: Regulation Time Moneyline",
    "Game Winner",
    "Match Winner: Arsenal vs Chelsea",
]


class TestASegmentMoneylineIsNotTheMatchWinner:
    @pytest.mark.parametrize("name,ext,source", SEGMENT_MONEYLINES)
    def test_a_segment_moneyline_does_not_classify_moneyline(self, name, ext, source):
        assert _at_call_site(name, ext) != "moneyline"

    @pytest.mark.parametrize("name,ext,source", SEGMENT_MONEYLINES)
    def test_a_segment_moneyline_may_not_speak_for_the_match(self, name, ext, source):
        """The user-visible half: refused at the blend, not merely relabelled.

        🔴 ASKED PER SOURCE, BECAUSE THE DOORS ARE DIFFERENT (#5031), and a
        single assertion here would have been a fiction — this test caught the
        lane asserting one. A Kalshi PRIMARY is exempt from the class test by a
        measured exemption, so its door is the venue's ticker
        (`feeds_win_prob_blend`), which already refuses `KXNCAAMBSGP-…`. The
        Polymarket rows carry an opaque hash that says nothing, so for them the
        title is the only thing that can refuse — which is why the live harm
        here is Polymarket's 281 rows and not the Kalshi parlay.
        """
        market = _Market(1, name, source=source, external_id=ext)
        if source == "kalshi":
            assert feeds_win_prob_blend(ext) is False, (
                "the ticker rule is Kalshi's whole defence for this row"
            )
            assert admissible_as_blend_speaker(market, is_primary=False) is False
        else:
            assert admissible_as_blend_speaker(market, is_primary=True) is False

    def test_this_branch_was_the_SOLE_admitter(self):
        """🔴 Non-vacuity: prove no other guard was ever going to catch these.

        A test that only asserts the new verdict cannot tell a real fix from a
        redundant one. So this pins the three facts that made the defect
        reachable at all, each of which is still true of the row today:

          1. the moneyline word genuinely matches, so the branch IS the one
             deciding (a fix anywhere else would be inert),
          2. the bare-matchup branch below it answers False, so falling
             through would not have saved the row either,
          3. its outcomes are the two competitors' bare names, so #5273's
             outcome refutation reads no derivative label.
        """
        name = "76ers vs. Celtics: 1H Moneyline"
        assert _MONEYLINE_WORD_RE.search(name), "the branch under test is reached"
        assert is_bare_matchup(name) is False
        assert outcomes_refute_game_winner(["76ers", "Celtics"]) is False
        assert is_game_winner_market(name, None) is False

    def test_the_refusal_is_terminal_against_a_game_bearing_ticker(self):
        """🔴 The inertness trap #5698 documented, re-armed for this door.

        Kalshi's period tickers carry the substring "game"
        (`KXNBAGAME1H-…`), and the ticker branch at the bottom of
        `is_game_winner_market` answers True to anything Kalshi-shaped
        containing "game" or "winner". If this branch merely declined to
        return True and fell through, that branch would re-admit the row and
        the fix would be inert exactly where the venue is most explicit.
        """
        ticker = "KXNBAGAME1H-26SEP12PHIBOS"
        assert "game" in ticker.lower(), "the trap this test exists for"
        assert is_game_winner_market("76ers vs. Celtics: 1H Moneyline", ticker) is False


class TestTheMatchWinnerItselfIsUntouched:
    @pytest.mark.parametrize("name", WHOLE_MATCH_TITLES)
    def test_a_whole_match_title_still_classifies_moneyline(self, name):
        assert _at_call_site(name) == "moneyline"

    def test_the_fix_can_only_ever_narrow(self):
        """Nothing that was refused becomes admitted. The change adds one
        refusal test to one branch; it introduces no new True anywhere, and a
        rewrite that reorders the branches would red here."""
        previously_refused = [
            "Alexander Zverev vs Karen Khachanov: Set 1 Winner",
            "Counter-Strike: 1WIN vs B8 - Map 1 Winner",
            "Yankees at Dodgers: Total Runs",
            "Celtics at Warriors: Rebounds",
        ]
        for name in previously_refused:
            assert _at_call_site(name) != "moneyline", name


class TestTheLetterClassIsThreeLettersBecauseItWasMeasured:
    """🔴 The guard that reds if anyone generalises the compressed token.

    `\\d[a-z]` looks like the obvious form and is wrong. Over every production
    name carrying a moneyline or winner word, the digit-plus-letter tokens that
    occur are `1h` (281), `1q` (1) — and then four that are TEAM or TOURNAMENT
    names. Each one below is a real row that a wider letter class would retire,
    and `3M Open - Winner` is a real golf winner whose number would vanish.
    """

    @pytest.mark.parametrize(
        "name",
        [
            "3M Open - Winner",                                  # tok "3m" — a golf tournament
            "Counter-Strike: 9z vs FaZe - Match Winner",         # tok "9z" — a CS team
            "LoL: Kits Esports vs 3v Team - Match Winner",       # tok "3v" — a LoL team
            "Enhanced Games: Men's 50m Freestyle Winner",        # tok "50m" — a distance
        ],
    )
    def test_a_digit_letter_token_that_is_a_NAME_is_not_a_segment(self, name):
        assert not _SEGMENT_SCOPED_MONEYLINE_RE.search(name), name
        assert not _SEGMENT_SCOPED_WINNER_RE.search(name), name

    def test_the_three_letters_are_pinned_as_a_decision(self):
        """H, Q, P — half, quarter, period. Pinned so widening is deliberate."""
        assert _COMPRESSED_SEGMENT == r"\d{1,2}\s?[HQP]"

    @pytest.mark.parametrize("token", ["1H", "2H", "1Q", "4Q", "3P", "1 H"])
    def test_every_compressed_segment_spelling_is_seen(self, token):
        assert _SEGMENT_SCOPED_MONEYLINE_RE.search(f"A vs B: {token} Moneyline"), token


class TestTheMoneylineDoorSubtractsRoundAndLeg:
    """🔴 Why the two doors CANNOT share one vocabulary, measured both ways.

    #5743 asked for one shared segment tuple. The data refuses it. A "Winner"
    with a numbered round on it is a tournament-stage market — all 44 such
    names in the corpus are elections ("Brazil Presidential Election First
    Round Winner"), none is a match, so the winner door loses nothing by
    refusing them. The explicit MATCH phrases are the opposite: the venue uses
    them to say "this whole contest, which happens to sit in round 2".

    Scope-testing the moneyline door with `_WINNER_SCOPE_WORDS` was measured
    against the real corpus and costs FIVE real games — the four
    "2022 NBA Playoffs, Round 2: Who will win …" titles and the FIDE chess
    round. The part-only set costs zero and still catches all 214 names.
    """

    def test_round_and_leg_are_subtracted_from_the_moneyline_door_only(self):
        for word in ("round", "leg"):
            assert word in _WINNER_SCOPE_WORDS, word
            assert word not in _MONEYLINE_SCOPE_WORDS, word

    @pytest.mark.parametrize(
        "name",
        ["2022 NBA Playoffs, Round 2: Who will win Celtics vs. Bucks?",
         "2022 NBA Playoffs, Round 2: Who will win Grizzlies vs. Warriors?",
         "2022 NBA Playoffs, Round 2: Who will win Heat vs. 76ers?",
         "2022 NBA Playoffs, Round 2: Who will win Suns vs. Mavericks?"],
    )
    def test_the_four_games_the_wider_set_would_have_cost(self, name):
        """The measurement, as an assertion. Each of these is a whole match,
        and each is refused by `_WINNER_SCOPE_WORDS` and kept by this door's."""
        assert _at_call_site(name) == "moneyline"

    def test_the_election_round_is_still_refused_and_that_is_correct(self):
        """The other side of the subtraction: a "first round winner" election
        is not a game market at all, so the winner door refusing it costs
        nothing — which is what makes the two vocabularies safe to differ."""
        assert is_game_winner_market(
            "Brazil Presidential Election First Round Winner"
        ) is False

    def test_a_numbered_GAME_is_a_whole_match_at_this_door_too(self):
        """`game` was already subtracted for #5698; the moneyline door inherits
        the subtraction rather than re-deciding it."""
        assert "game" not in _MONEYLINE_SCOPE_WORDS
        assert is_game_winner_market("Who will win Bucks v. Suns: NBA Finals Game 4?")


class TestTheCompressedFormReachesBothDoors:
    """One token, two readers — the drift this ship exists to prevent.

    #5698 built `_SEGMENT_SCOPED_WINNER_RE` from the shared scope tuple so a
    word learned once is learned twice. The compressed token is the same
    principle for the other spelling: it was added in one place and both doors
    read it, so the next venue spelling cannot be fixed on one door only —
    which is precisely how #5743 came to exist.
    """

    @pytest.mark.parametrize("suffix", ["Moneyline", "Winner"])
    def test_the_compressed_token_is_read_at_both_doors(self, suffix):
        assert is_game_winner_market(f"Knicks vs. Spurs: 1H {suffix}") is False

    def test_every_part_word_is_visible_to_the_moneyline_test(self):
        """A segment word added to the tuple must reach this door without a
        second edit — the `_PREFIX_DISQUALIFIERS` principle one level down."""
        for word in _MONEYLINE_SCOPE_WORDS:
            assert _SEGMENT_SCOPED_MONEYLINE_RE.search(f"A vs B: {word} 1 Moneyline"), (
                f"{word!r} is in the moneyline scope tuple but the test cannot see it"
            )

    def test_5698s_shipped_refusals_are_unchanged(self):
        """The winner door gained an alternative; it must not have lost one."""
        for name in ("Set 1 Winner: Aboian vs Martin", "Alabama vs Kentucky: 1st Half Winner",
                     "ARI Cardinals vs LA Chargers: 1st Quarter Winner",
                     "Counter-Strike: 1WIN vs B8 - Map 1 Winner"):
            assert _SEGMENT_SCOPED_WINNER_RE.search(name), name
        assert not _SEGMENT_SCOPED_WINNER_RE.search("Game 3 Winner: Dodgers vs Padres")
        assert not _SEGMENT_SCOPED_WINNER_RE.search("Round of 16 Winner: Alcaraz vs Sinner")
