"""#5698 — a bare "Winner" must say what it is the winner OF.

THE DEFECT. `_WINNER_WORD_RE` matched `\\bwinner\\b` anywhere in a market name
and `is_game_winner_market` returned True, with no branch asking WHICH contest.
So `… : Set 1 Winner`, `… : 1st Half Winner` and `… - Map 1 Winner` classified
`moneyline` — the class the blend admits as a speaker for the MATCH — and a
live set-1 price could be published as the match winner. Same defect class as
#5031 / #5273 / #5432, reached from a third direction: not the outcomes, not
the parent/child link, but the title's own words.

WHY NOTHING ELSE CAUGHT THEM. Their outcomes are the two competitors' bare
names, so `outcomes_refute_game_winner` (#5273) reads no derivative label and
does not refute. The bare-matchup branch refuses them for their qualifier, but
it sits BELOW the winner-word branch and was never reached. So this branch was
the sole admitter. Measured 2026-09-12 over every Polymarket/Kalshi market
linked to an event commencing within ±7 days: **1,397** market groups
classified `moneyline` on the word alone, **every one of them** a set, half,
quarter or map book — and **zero** legitimate match winners in that population,
because a real match winner is titled as a bare matchup or "Will X win?", not
with the word "Winner".

THE 823 KALSHI ROWS WERE NEVER THE LIVE HARM, and saying so is the honest
version of this ship: `feeds_win_prob_blend` refuses them on their TICKER
(`KXATPSETWINNER-…`, `KXNCAAF1H-…`), which is the entire reason #5031's
per-source dispatch must not be collapsed into one call. The live exposure was
the **574 Polymarket** groups across **389 events**, where the source carries no
ticker signal at all and the title was the only thing that could refuse them.
"""

import re

import pytest

from app.utils.game_market_class import (
    _DERIVATIVE_SCOPE_RE,
    _SEGMENT_SCOPE_WORDS,
    _SEGMENT_SCOPED_WINNER_RE,
    classify_game_market_class,
    is_game_winner_market,
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
    function overstates the reach of any change to it, because the caller
    pre-processes its input — the error this lane made on #5660 and corrected
    in the open (408 vs 319).
    """
    return classify_game_market_class(_strip_category_prefix(name), external_id)


# Real rows, by name and ticker, from the ±7d linked window on 2026-09-12.
SEGMENT_WINNERS = [
    ("Alexander Zverev vs Karen Khachanov: Set 1 Winner", "KXATPSETWINNER-26SEP11ZVEKHA-1", "kalshi"),
    ("Alana Smith vs Anastasia Tikhonova: Set 2 Winner", "KXWTASETWINNER-26SEP12SMITIK-2", "kalshi"),
    ("Alabama vs Kentucky: 1st Half Winner", "KXNCAAF1H-26SEP12ALAUK", "kalshi"),
    ("Al-Ittihad vs Al-Fayha: First Half Winner", "KXSAUDIPL1H-26SEP08ITJFAY", "kalshi"),
    ("ARI Cardinals vs LA Chargers: 1st Quarter Winner", "KXNFL1Q-26SEP13ARILAC", "kalshi"),
    ("Alabama vs Kentucky: 4th Quarter Winner", "KXNCAAF4Q-26SEP12ALAUK", "kalshi"),
    ("Counter-Strike: 1WIN vs B8 - Map 1 Winner", "0x257b2ef0623447c4ed7275dc7436a492b51821", "polymarket"),
    ("Set 1 Winner: Aboian vs Martin", "0xdeadbeef", "polymarket"),
]

# Titles that DO decide the whole contest and must keep their number.
REAL_WINNERS = [
    ("Canelo Alvarez vs Christian Mbilli", None),
    ("PPA - Women's Singles: Hannah Blatt vs Polina Libo", None),
    ("US Open ATP: Alexander Zverev vs Ben Shelton", None),
    ("Match Winner: Arsenal vs Chelsea", None),
    ("Game Winner", None),
]


class TestASegmentWinnerIsNotTheMatchWinner:
    @pytest.mark.parametrize("name,ext,source", SEGMENT_WINNERS)
    def test_a_segment_winner_does_not_classify_moneyline(self, name, ext, source):
        assert _at_call_site(name, ext) != "moneyline"

    @pytest.mark.parametrize("name,ext,source", SEGMENT_WINNERS)
    def test_a_segment_winner_may_not_speak_for_its_source(self, name, ext, source):
        """The user-visible half: refused at the blend, not merely relabelled.

        🔴 ASKED PER SOURCE, BECAUSE THE DOORS ARE DIFFERENT (#5031), and a
        single assertion here would have been a fiction. A Kalshi PRIMARY is
        exempt from the class test by a measured exemption, so its door is the
        venue's ticker (`feeds_win_prob_blend`) and it was already shut — which
        is why this ship's live exposure is Polymarket's 574 and not 1,397.
        Collapsing these two branches into one call is the simplification
        #5031 forbids, and this test is shaped to red if anyone tries.
        """
        market = _Market(1, name, source=source, external_id=ext)
        if source == "kalshi":
            assert feeds_win_prob_blend(ext) is False, (
                "the ticker rule is Kalshi's whole defence for this row"
            )
            # The class test still reaches it whenever it is NOT the primary,
            # and there this fix is what refuses it.
            assert admissible_as_blend_speaker(market, is_primary=False) is False
        else:
            assert admissible_as_blend_speaker(market, is_primary=True) is False

    def test_the_refusal_is_by_NAME_and_survives_a_winner_bearing_ticker(self):
        """🔴 The non-vacuity pin, and the reason this is an early return.

        `KXATPSETWINNER-…` contains the substring "winner", so the ticker
        branch of `is_game_winner_market` answers True for it. If the segment
        test merely declined to return True and fell through, that branch would
        re-admit the row and this whole fix would be inert on every Kalshi set
        market. The refusal must therefore be terminal.
        """
        ticker = "KXATPSETWINNER-26SEP11ZVEKHA-1"
        assert "winner" in ticker.lower(), "the trap this test exists for"
        assert is_game_winner_market(
            "Alexander Zverev vs Karen Khachanov: Set 1 Winner", ticker
        ) is False

    def test_a_polymarket_segment_row_has_no_ticker_to_save_it(self):
        """Why the 574 were the live harm and the 823 were not.

        Kalshi's rows were already refused by `feeds_win_prob_blend` on their
        ticker. Polymarket's external id is an opaque hash that carries no
        signal, so before this fix nothing at all stood between a map-winner
        price and the match hero.
        """
        opaque = "0x257b2ef0623447c4ed7275dc7436a492b51821"
        assert not opaque.lower().startswith("kx")
        assert _at_call_site("Counter-Strike: 1WIN vs B8 - Map 1 Winner", opaque) != "moneyline"


class TestTheMatchWinnerItselfIsUntouched:
    @pytest.mark.parametrize("name,ext", REAL_WINNERS)
    def test_a_real_winner_still_classifies_moneyline(self, name, ext):
        assert _at_call_site(name, ext) == "moneyline"

    def test_explicit_match_wording_is_never_scope_tested(self):
        """"Game Winner" contains a segment word — and names the whole contest.

        `_MONEYLINE_WORD_RE` therefore answers first and is not scope-tested,
        or this fix would refuse the canonical phrase it exists to protect.
        """
        assert _at_call_site("Game Winner") == "moneyline"
        assert _at_call_site("Match Winner: Arsenal vs Chelsea") == "moneyline"

    def test_a_numbered_GAME_is_a_whole_match_not_a_segment(self):
        """The October case. A playoff series' "Game 3" IS the match, so `game`
        is subtracted from the winner-scope vocabulary (and only there)."""
        assert _at_call_site("Game 3 Winner: Dodgers vs Padres") == "moneyline"

    def test_a_tournament_ROUND_is_not_a_segment_because_of_stands_between(self):
        """Adjacency is what makes this safe: "Round of 16" never reads as a
        numbered segment, so a cup tie keeps its winner."""
        assert _at_call_site("Round of 16 Winner: Alcaraz vs Sinner") == "moneyline"

    def test_5660s_ship_is_not_disturbed(self):
        """A matchup behind a competition prefix still reaches the writer."""
        assert _at_call_site("PPA - Women's Singles: Hannah Blatt vs Polina Libo") == "moneyline"
        assert _at_call_site("M25 Sintra: Dino Molokova Ferreira vs Lucas Nunez") == "moneyline"


class TestOneListTwoReaders:
    """The vocabulary is single-sourced, so a word learned once is learned twice."""

    def test_the_winner_test_is_built_from_the_scope_tuple(self):
        """A segment word added to `_SEGMENT_SCOPE_WORDS` must reach the winner
        test without a second edit — the `_PREFIX_DISQUALIFIERS` principle one
        level down. Every word except the documented `game` subtraction."""
        for word in _SEGMENT_SCOPE_WORDS:
            if word == "game":
                continue
            assert _SEGMENT_SCOPED_WINNER_RE.search(f"A vs B: {word} 1 Winner"), (
                f"{word!r} is in the scope tuple but the winner test cannot see it"
            )

    def test_game_is_subtracted_from_the_winner_test_only(self):
        """Pinned as a DECISION, so removing it is a deliberate act."""
        assert "game" in _SEGMENT_SCOPE_WORDS
        assert _DERIVATIVE_SCOPE_RE.search("Game 3: Dodgers vs Padres")
        assert not _SEGMENT_SCOPED_WINNER_RE.search("Game 3 Winner: Dodgers vs Padres")

    def test_the_prefix_vocabulary_is_behaviourally_unchanged(self):
        """#5660's `_DERIVATIVE_SCOPE_RE` was refactored from a literal to a
        join over the tuple. Its pattern must still match exactly what it did,
        or that ship's fail-closed margin moved silently."""
        assert _DERIVATIVE_SCOPE_RE.pattern == (
            r"\b(?:map|period|quarter|half|frame|leg|set|game|round|inning|innings)\b"
        )
        assert _DERIVATIVE_SCOPE_RE.flags & re.IGNORECASE

    @pytest.mark.parametrize(
        "name",
        ["Set 1 Winner", "1st Half Winner", "First Half Winner",
         "4th Quarter Winner", "Map 2 Winner", "Period 2 Winner",
         "Round 5 Winner", "Frame 3 Winner"],
    )
    def test_both_ordinal_orders_are_read(self, name):
        """"Set 1" puts the number after the word; "1st Half" puts it before.
        Both are real venue spellings and both must be seen."""
        assert _SEGMENT_SCOPED_WINNER_RE.search(name), name
