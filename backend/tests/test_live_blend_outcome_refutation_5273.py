"""#5273 (CU-1) — a market whose own outcomes refute its title cannot be the winner.

THE DEFECT THESE GUARD. Polymarket mints an event-level container whose TITLE is
the bare matchup and hangs the derivative books off it as OUTCOMES. The title
passes `is_bare_matchup`, so `classify_game_market_class` answers "moneyline",
`admissible_as_blend_speaker` admits it, and `find_moneyline_outcome` then
resolves the single competitor-shaped outcome by containment — publishing a
HANDICAP's price as the match winner.

Measured on production 2026-09-12 over the (-6h, +48h) window: of 314 Polymarket
markets the name gate admits, 88 are refuted by their own outcomes, and the
#5311 eligibility record names three of them as the LIVE speaker — US Open ATP
Tiafoe vs Shelton at 0.165 off a `Set 1 O/U 8.5` / `Set Handicap +/-1.5` basket
(Kalshi 0.01), Cal Poly vs San Jose State off `Spread -20.5 | O/U 57.5`, and
Norfolk State vs Virginia off `Spread -43.5`.

Every specimen named in this file is a real production row, not an invention.

WHAT WOULD SILENTLY UNDO THE FIX, and therefore what each class here binds:
  * reading the outcome COUNT instead of its vocabulary — the containers span
    one to twenty outcomes and overlap both legitimate arities exactly;
  * requiring a MAJORITY of derivative outcomes — `Duquesne | Spread -16.5` is
    one of two and is the whole defect;
  * dropping the word boundaries — "Thunder" contains "under";
  * fail-CLOSED on an unloaded outcome list — that retires real winners;
  * widening the test onto the Kalshi primary, whose exemption is measured.
"""

import pytest

from app.utils.game_market_class import outcomes_refute_game_winner
from app.utils.live_blend import (
    MarketOutcomes,
    admissible_as_blend_speaker,
    compute_source_home_probability,
    count_admissible_speakers,
)


class _Outcome:
    def __init__(self, name, prob=0.5, rank=None):
        self.name = name
        self.current_probability = prob
        self.current_yes_bid = None
        self.current_yes_ask = None
        self.rank = rank


class _Market:
    def __init__(self, id, source="polymarket", external_id=None, name=""):
        self.id = id
        self.source = source
        self.external_id = external_id
        self.name = name


def _pm(id, name, outcome_names, external_id=None):
    """A Polymarket row and its outcomes, as the group loop sees them."""
    return MarketOutcomes(
        market=_Market(id, "polymarket", external_id or f"0x{id:04x}", name),
        outcomes=[_Outcome(n, 0.5, rank=i) for i, n in enumerate(outcome_names)],
    )


# ── The recognizer ───────────────────────────────────────────────────────────

REFUTED = [
    # (label, outcome names) — every one a production row.
    ("two-outcome container", ["Duquesne", "Spread -16.5"]),
    ("three-outcome container", ["Spread -20.5", "O/U 57.5", "Cal Poly"]),
    ("NRFI wearing the game title", ["NRFI"]),
    ("total-runs prop", ["YRFI"]),
    ("set totals + handicap", [
        "US Open ATP: Frances Tiafoe vs Ben Shelton Set 1 O/U 8.5",
        "US Open ATP: Frances Tiafoe vs Ben Shelton Set Handicap +/-1.5",
        "Frances Tiafoe",
    ]),
    ("period winner", ["Set 2 Winner", "Ben Shelton"]),
    ("game spread", ["Game Spread +/-4.5", "Frances Tiafoe"]),
    ("total sets", ["Total Sets: O/U 3.5", "Frances Tiafoe"]),
    ("mixed college container", ["O/U 53.5", "O/U 54.5", "Spread -43.5", "Norfolk State"]),
    ("parenthesised handicap", ["Venezia FC (-1.5)", "Cagliari"]),
    ("exact scoreline", ["St. Louis City SC 2 - 2 Minnesota United FC"]),
    ("over/under pair", ["Over", "Under"]),
]

ADMITTED = [
    ("decomposed binary winner", ["Yes", "No"]),
    ("soccer three-way with a draw", [
        "Club Tijuana", "Draw (Club Tijuana vs. Querétaro FC)", "Querétaro FC",
    ]),
    ("two competitors", ["Boston Celtics", "Golden State Warriors"]),
    ("single competitor side", ["Los Angeles Angels"]),
    ("accented competitors", ["1. FC Köln", "SV Werder Bremen"]),
]


class TestRecognizer:
    @pytest.mark.parametrize("label,names", REFUTED, ids=[c[0] for c in REFUTED])
    def test_derivative_outcomes_refute(self, label, names):
        assert outcomes_refute_game_winner(names) is True

    @pytest.mark.parametrize("label,names", ADMITTED, ids=[c[0] for c in ADMITTED])
    def test_competitor_outcomes_do_not_refute(self, label, names):
        assert outcomes_refute_game_winner(names) is False

    def test_one_derivative_is_enough_not_a_majority(self):
        """`Duquesne | Spread -16.5` is 1-of-2 and is the whole defect.

        A majority rule reads as the safer one and keeps exactly the specimen
        the #5311 record caught speaking on production.
        """
        assert outcomes_refute_game_winner(["Duquesne", "Spread -16.5"]) is True

    @pytest.mark.parametrize(
        "team",
        ["Oklahoma City Thunder", "Vanderbilt", "Dover Athletic", "Anderson"],
    )
    def test_word_boundaries_hold_against_substrings(self, team):
        """"Thunder" contains "under"; the boundary is what stops it.

        Delete the `\\b` around the `under`/`over` alternatives and this fires,
        retiring a real winner. Same class as the "Winnipeg"/`\\bwinner\\b`
        boundary the module's own comments record.
        """
        assert outcomes_refute_game_winner([team, "Boston Celtics"]) is False

    @pytest.mark.parametrize("empty", [None, [], [None], [""]])
    def test_absent_outcomes_are_no_evidence_not_guilt(self, empty):
        """Fail OPEN. A false positive empties a card; a false negative does not.

        An unloaded outcome list must leave today's behaviour untouched.
        """
        assert outcomes_refute_game_winner(empty) is False

    def test_arity_alone_cannot_separate_the_two_families(self):
        """The count-based predicate this replaces, shown failing both ways.

        Legitimate winners come in 1, 2 and 3 outcomes; so do the containers.
        Any test that reads `len(outcomes)` either keeps `Spread -16.5` or
        takes soccer's draw down with it.
        """
        legit_three = ["Club Tijuana", "Draw (Club Tijuana vs. Querétaro FC)", "Querétaro FC"]
        broken_three = ["Spread -20.5", "O/U 57.5", "Cal Poly"]
        legit_two = ["Yes", "No"]
        broken_two = ["Duquesne", "Spread -16.5"]
        assert len(legit_three) == len(broken_three)
        assert len(legit_two) == len(broken_two)
        assert outcomes_refute_game_winner(legit_three) is False
        assert outcomes_refute_game_winner(broken_three) is True
        assert outcomes_refute_game_winner(legit_two) is False
        assert outcomes_refute_game_winner(broken_two) is True


# ── The gate ─────────────────────────────────────────────────────────────────


class TestAdmissionGate:
    def test_container_titled_as_the_match_is_refused(self):
        entry = _pm(1, "Duquesne vs. Youngstown State", ["Duquesne", "Spread -16.5"])
        assert admissible_as_blend_speaker(
            entry.market, is_primary=True, outcomes=entry.outcomes
        ) is False

    def test_the_same_row_is_admitted_on_its_title_alone(self):
        """Proves the outcomes are what did the work, not the name gate.

        If this ever starts returning False the fix has become unobservable —
        the name gate would be refusing the row and the new predicate would be
        passing vacuously.
        """
        entry = _pm(1, "Duquesne vs. Youngstown State", ["Duquesne", "Spread -16.5"])
        assert admissible_as_blend_speaker(entry.market, is_primary=True) is True

    def test_real_winner_still_admitted(self):
        entry = _pm(2, "Oklahoma vs. Michigan", ["Yes", "No"])
        assert admissible_as_blend_speaker(
            entry.market, is_primary=True, outcomes=entry.outcomes
        ) is True

    def test_default_none_leaves_existing_callers_unchanged(self):
        """`event_chart_backfill` does not load outcomes and must not acquire a gate."""
        entry = _pm(1, "Duquesne vs. Youngstown State", ["Duquesne", "Spread -16.5"])
        assert admissible_as_blend_speaker(entry.market, is_primary=False) is True

    def test_kalshi_primary_delta_is_zero(self):
        """The Kalshi primary's exemption is MEASURED (13 live UFC fights).

        The outcome test would not misfire on Kalshi's `Yes | No` pair, but
        widening a second instrument onto that exemption changes a population
        #5031 measured and this queue did not.
        """
        m = _Market(1, "kalshi", "KXUFCFIGHT-26SEP12SILDEL", "Fight Night: Silva vs Delgado")
        assert admissible_as_blend_speaker(
            m, is_primary=True, outcomes=[_Outcome("Spread -1.5"), _Outcome("O/U 2.5")]
        ) is True


class TestGroupBehaviour:
    """What the user sees: a re-point, or an honest silence — never a handicap."""

    def test_group_repoints_to_the_real_winner_in_the_same_group(self):
        """25 production events do exactly this.

        The container is the LOWER id, so it is the primary and used to win.
        """
        group = [
            _pm(1, "Duquesne vs. Youngstown State", ["Duquesne", "Spread -16.5"]),
            MarketOutcomes(
                market=_Market(9, "polymarket", "0x9", "Duquesne vs. Youngstown State"),
                outcomes=[
                    _Outcome("Duquesne", 0.62, rank=0),
                    _Outcome("Youngstown State", 0.38, rank=1),
                ],
            ),
        ]
        reading = compute_source_home_probability(group, "Duquesne", "Youngstown State")
        assert reading is not None
        assert reading.market.id == 9, "the derivative container must not speak"
        assert reading.home_probability == 0.62

    def test_container_only_group_says_nothing(self):
        """57 production events. Silence is the correct answer, not a spread's price."""
        group = [
            _pm(1, "Towson vs. South Carolina", ["Spread -42.5", "O/U 55.5", "Towson"]),
            _pm(2, "Towson vs. South Carolina", ["NRFI"]),
        ]
        assert compute_source_home_probability(
            group, "Towson", "South Carolina"
        ) is None

    def test_container_only_group_counts_zero_admissible_speakers(self):
        """Zero is what makes the caller RETIRE the stored leg (#5031, #1163).

        Silence alone only freezes yesterday's wrong number on the page; this
        count is the signal that the source structurally holds no opinion.
        """
        group = [
            _pm(1, "Towson vs. South Carolina", ["Spread -42.5", "O/U 55.5", "Towson"]),
            _pm(2, "Towson vs. South Carolina", ["NRFI"]),
        ]
        assert count_admissible_speakers(group) == 0

    def test_a_real_winner_keeps_the_group_speaking(self):
        group = [
            _pm(1, "Oklahoma vs. Michigan", ["Spread -3.5", "Oklahoma"]),
            MarketOutcomes(
                market=_Market(2, "polymarket", "0x2", "Oklahoma vs. Michigan"),
                outcomes=[
                    _Outcome("Oklahoma", 0.55, rank=0),
                    _Outcome("Michigan", 0.45, rank=1),
                ],
            ),
        ]
        assert count_admissible_speakers(group) == 1

    def test_derivative_sibling_never_joins_a_devig(self):
        """A two-market group averages both halves; the refused half must not average in.

        Ungated, the mean of a real 0.60 winner and a 0.20 handicap serves 0.40
        — a composite substantiated by neither question (CERT-2646's class).
        """
        group = [
            MarketOutcomes(
                market=_Market(1, "polymarket", "0x1", "Oklahoma vs. Michigan"),
                outcomes=[
                    _Outcome("Oklahoma", 0.60, rank=0),
                    _Outcome("Michigan", 0.40, rank=1),
                ],
            ),
            _pm(2, "Oklahoma vs. Michigan", ["Oklahoma", "Spread -20.5"]),
        ]
        reading = compute_source_home_probability(group, "Oklahoma", "Michigan")
        assert reading is not None
        assert reading.devigged is False
        assert reading.home_probability == 0.60
