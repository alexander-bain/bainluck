"""#12221 — the primitives' data floor: every open, priced market gets a shape and
an outcome set.

The first weekly grouping count (Sat Nov 7 2026) found 5,713 open markets
`unshaped` and 10,410 with outcomes `unknown`. Measured the same day over open,
PRICED markets (47,921): 2,168 unshaped and 6,567 unknown, and three rules
account for most of them. Each specimen below is a production market from that
reading.

  1. A lone "Yes" is a claim. Kalshi stores every single-market event as one
     outcome named "Yes" by design, so 954 open Kalshi binaries (plus 666
     Polymarket singles) were `unshaped`, and no open market at all was a `claim`.
  2. "N+" is Kalshi's spelling of "at least N" ("Hageman, 26+ pts": 505 rows of
     KXMIDTERMMOV alone; "7+ wins"; "Joe Burrow: 1+").
  3. A Kalshi field the venue declares not mutually exclusive ("Top 10 Ranked
     Teams", award nominations) is independent: more than one leg may win.

The rules only resolve rows v2 left unshaped or unknown; a proved verdict
never moves (last class below).
"""

from app.utils.market_shape import (
    CLASSIFIER_VERSION,
    REL_COMPETITORS,
    REL_COMPLEMENTS,
    REL_CUMULATIVE,
    REL_PARTICIPATION,
    REL_UNKNOWN,
    SHAPE_CLAIM,
    SHAPE_CONTAINER_MEMBER,
    SHAPE_FIELD,
    SHAPE_UNSHAPED,
    classify_market_semantics,
)


def sem(names, **kw):
    return classify_market_semantics(outcome_names=names, **kw)


def test_version_moves_so_the_sweep_restamps_open_rows():
    assert CLASSIFIER_VERSION == 3


class TestALoneYesIsAClaim:
    def test_a_kalshi_single_market_event(self):
        # KXNFLOT-26NOV08ARISEA "Arizona vs Seattle: Overtime", mutually_exclusive False.
        r = sem(["Yes"], source="kalshi", external_id="KXNFLOT-26NOV08ARISEA", mutually_exclusive=False)
        assert r["display_shape"] == SHAPE_CLAIM and r["side_kind"] == "yes_no"
        assert r["outcome_relation"] == REL_COMPLEMENTS
        assert "single_yes_leg" in r["evidence"]

    def test_the_set_we_hold_is_never_called_a_partition(self):
        """Read as proof that outcomes sum to 1 (calibration, feed bands, liveness)."""
        r = sem(["Yes"], source="polymarket", group_id="polymarket:1262820", mutually_exclusive=True)
        assert r["exhaustive"] is False
        assert r["expected_winners"] is None

    def test_inside_a_multi_member_group_it_is_a_container_member(self):
        r = sem(["Yes"], source="polymarket", group_id="polymarket:1", group_size=4)
        assert r["display_shape"] == SHAPE_CONTAINER_MEMBER

    def test_one_named_leg_of_a_field_stays_unshaped(self):
        # "UD Almería vs. FC Andorra", neg-risk, one of three legs stored.
        r = sem(["UD Almería"], source="polymarket", mutually_exclusive=True)
        assert r["display_shape"] == SHAPE_UNSHAPED and r["outcome_relation"] == REL_UNKNOWN
        assert sem([], source="polymarket")["outcome_relation"] == REL_UNKNOWN


class TestPlusLadders:
    def test_a_margin_ladder(self):
        names = ["Hageman, 26+ pts", "Hageman, 28+ pts", "Hageman, 30+ pts", "Hageman, 32+ pts"]
        r = sem(names, source="kalshi", external_id="KXMIDTERMMOV-WYGOV", mutually_exclusive=False)
        assert r["outcome_relation"] == REL_CUMULATIVE
        assert r["exhaustive"] is False
        assert "plus_threshold_outcomes" in r["evidence"]

    def test_wins_ladders_and_player_ladders(self):
        assert sem(["7+ wins", "8+ wins", "5+ wins", "6+ wins"])["outcome_relation"] == REL_CUMULATIVE
        assert sem(["Joe Burrow: 1+", "Michael Penix Jr.: 1+", "Joe Burrow: 2+"])["outcome_relation"] == REL_CUMULATIVE
        assert sem(["1460+", "1480+", "1500+"], source="polymarket")["outcome_relation"] == REL_CUMULATIVE
        # A majority is enough: Arsenal's "3 Trophies" top rung.
        assert sem(["1+ Trophies", "2+ Trophies", "3 Trophies"])["outcome_relation"] == REL_CUMULATIVE

    def test_a_spread_line_is_not_a_ladder(self):
        assert sem(["Chiefs +3.5", "Bills +3.5", "Jets +7"])["outcome_relation"] == REL_UNKNOWN
        assert sem(["2+2", "3+3", "4+4"])["outcome_relation"] == REL_UNKNOWN


class TestAKalshiFieldDeclaredNotExclusive:
    def test_top_ten_and_nominations(self):
        r = sem(["Duke", "Arizona", "Michigan", "Iowa St.", "Houston"], source="kalshi",
                external_id="KXNCAAMBTOPAPRANK-26DEC07", mutually_exclusive=False)
        assert r["display_shape"] == SHAPE_FIELD  # display is untouched
        assert r["outcome_relation"] == REL_PARTICIPATION
        assert r["exhaustive"] is False and r["expected_winners"] is None
        assert "venue_not_mutually_exclusive" in r["evidence"]

    def test_polymarket_neg_risk_false_is_not_that_statement(self):
        """`mutually_exclusive` on a Polymarket row is `neg_risk` (#12323)."""
        r = sem(["December 31, 2026", "March 31, 2026", "June 30"], source="polymarket", mutually_exclusive=False)
        assert r["outcome_relation"] == REL_UNKNOWN

    def test_an_unknown_flag_is_not_false(self):
        assert sem(["A", "B", "C"], source="kalshi")["outcome_relation"] == REL_UNKNOWN


class TestNoProvedVerdictMoves:
    def test_a_venue_exclusive_field_with_plus_names_stays_competitors(self):
        r = sem(["1+", "2+", "3+"], source="kalshi", mutually_exclusive=True)
        assert r["outcome_relation"] == REL_COMPETITORS and r["exhaustive"] is True

    def test_two_named_sides_and_yes_no_pairs_are_unchanged(self):
        assert sem(["Panthers", "Blues"], source="kalshi", mutually_exclusive=False)["outcome_relation"] == REL_COMPETITORS
        r = sem(["Yes", "No"], source="kalshi")
        assert r["display_shape"] == SHAPE_CLAIM and r["exhaustive"] is True and r["expected_winners"] == 1

    def test_word_spelled_ladders_keep_their_v2_evidence(self):
        r = sem(["at least 3", "at least 5", "at least 7"], source="kalshi", mutually_exclusive=False)
        assert r["outcome_relation"] == REL_CUMULATIVE
        assert "cumulative_threshold_outcomes" in r["evidence"]
        assert "plus_threshold_outcomes" not in r["evidence"]


class TestTheRoundUpsThatReadTheShapeAcceptAClaim:
    """Deadline boards and yardsticks admitted `unshaped`; v3 moves those rows to `claim`.

    Both gates spelled binary as {"yes_no", "binary", "container_member", "unshaped"},
    and only the last two are shapes, so a v3 claim would have been refused as
    `non_binary_market_type:claim` and the boards would have lost their Kalshi members.
    """

    def test_the_deadline_board(self):
        from datetime import date, datetime, timezone

        # This order: the test module imports roundup_containers first, as the app does.
        from tests.test_same_deadline_board import _make_binary_market
        from app.utils.same_deadline_board import _classify_candidate

        def reason(market_type):
            market = _make_binary_market(990002, "Will it snow in Washington, DC by December 31?", 0.31,
                                         category="weather", market_type=market_type)
            return _classify_candidate(market, deadline_date=date(2026, 12, 31), deadline_phrase="by December 31",
                                       band_low=0.05, band_high=0.95,
                                       now_dt=datetime(2026, 11, 7, 20, tzinfo=timezone.utc))[1]

        assert reason("field") == "non_binary_market_type:field"  # control: the gate is live
        assert reason("claim") != "non_binary_market_type:claim"
        assert reason("claim") == reason("unshaped")

    def test_the_yardstick(self):
        from app.utils.yardstick_pair import select_yardstick_pair
        from tests.test_yardstick_pair import NOW_NOV_4, _make_binary_market

        def reasons(market_type):
            markets = [
                _make_binary_market(60104328, "Will it snow in Washington, DC by November 30?", 0.39, category="weather"),
                _make_binary_market(61321728, "Will the Fed cut rates in December?", 0.12, category="economics",
                                    market_type=market_type),
            ]
            res = select_yardstick_pair(markets, anchor_spec="polymarket:60104328",
                                        candidate_specs=["polymarket:61321728"], now=NOW_NOV_4)
            return set(getattr(res, "reasons", ()) or ())

        assert ("candidate", 61321728, "non_binary_market_type:field") in reasons("field")
        assert not any(r[-1] == "non_binary_market_type:claim" for r in reasons("claim"))


def test_suggestion_movers_skip_claims_like_the_other_yes_no_shapes():
    from app.routes.events import _SUGGESTION_MOVERS_EXCLUDED_SHAPES

    assert {"unshaped", "container_member", "claim"} <= set(_SUGGESTION_MOVERS_EXCLUDED_SHAPES)
