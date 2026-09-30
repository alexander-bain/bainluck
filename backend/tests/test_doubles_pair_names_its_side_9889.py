"""#9889 — a finished doubles match names the winning pair, not "No result reported".

THE DEFECT, ON PRODUCTION 2026-09-30 17:11Z. ``/events/15320754`` (Bublik /
Shang v Cerundolo / Rinderknech) was ``suspended`` with no score, and the page
read "No result reported" and "No price". Kalshi's match market
``KXATPDOUBLES-26SEP28BUBSHACERRIN`` was resolved, with the winning leg
``Alexander Bublik / Juncheng Shang``.

``_fuzzy_team_match`` normalises the slash into one token on each side
(``alexander bublik/juncheng shang`` against ``bublik/shang``), so neither
containment nor word-subset could match, and the venue's grade was dropped.

REPLAY (production 2026-09-30, every doubles row from the last 90 days with a
positive grade and no score, 499 events): 261 recover a named winner, 0 existing
results change. The losing legs of those events' graded match markets: 219 name
the OTHER pair, **0 name the winner**, and 53 can't be resolved (trailing-initial
spellings such as ``Alvarez L``), so those stay refused.
"""

from app.utils.venue_settlement import (
    _names_a_participant,
    _pair_names_side,
    settlement_from_graded_rows,
)

HOME = "Bublik / Shang"
AWAY = "Cerundolo / Rinderknech"
MARKET = "Bublik / Shang vs Cerundolo / Rinderknech"
TICKER = "KXATPDOUBLES-26SEP28BUBSHACERRIN"
WINNER_LEG = "Alexander Bublik / Juncheng Shang"
LOSER_LEG = "Francisco Cerundolo / Arthur Rinderknech"


class TestTheSpecimen:
    def test_the_venues_winning_pair_is_named(self):
        got = settlement_from_graded_rows([(MARKET, TICKER, WINNER_LEG)], HOME, AWAY)
        assert got == {
            "venue_settled": True,
            "venue_settled_result": "Bublik / Shang wins",
        }

    def test_the_losing_leg_resolves_to_the_other_pair(self):
        assert _names_a_participant(LOSER_LEG, HOME, AWAY) == AWAY

    def test_partner_order_does_not_matter(self):
        assert _names_a_participant("Juncheng Shang / Alexander Bublik", HOME, AWAY) == HOME


class TestWhatIsStillRefused:
    def test_one_shared_partner_is_not_the_pair(self):
        # One surname in common is how two different pairs look alike.
        assert not _pair_names_side("Alexander Bublik / Andrey Golubev", HOME)
        assert _names_a_participant("Alexander Bublik / Andrey Golubev", HOME, AWAY) is None

    def test_both_partners_matching_one_of_ours_is_not_the_pair(self):
        # The two partners must match two DIFFERENT partners of ours.
        assert not _pair_names_side("Alexander Bublik / Alexander Bublik", HOME)

    def test_an_outcome_that_names_both_sides_names_neither(self):
        assert _names_a_participant(WINNER_LEG, HOME, "Shang / Bublik") is None

    def test_a_set_winner_book_on_a_doubles_match_is_not_the_match(self):
        got = settlement_from_graded_rows(
            [(f"Set 1 Winner: {MARKET}", None, WINNER_LEG)], HOME, AWAY
        )
        assert got["venue_settled"] is False

    def test_a_name_that_is_not_two_partners_is_not_a_pair(self):
        assert not _pair_names_side("Alexander Bublik", HOME)
        assert not _pair_names_side("A Bublik / J Shang / X Other", HOME)
        assert not _pair_names_side("Alexander Bublik / ", HOME)
        assert not _pair_names_side(WINNER_LEG, "Bublik")


class TestSinglesAreUnchanged:
    def test_the_6739_singles_specimen_still_names_its_winner(self):
        got = settlement_from_graded_rows(
            [("Fiona Crawley vs Naiktha Bains", None, "Fiona Crawley")],
            "Crawley",
            "Bains",
        )
        assert got["venue_settled_result"] == "Crawley wins"
