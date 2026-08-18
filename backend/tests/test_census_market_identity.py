"""Queue 362 — a market bound to the wrong game is not "identity certain".

THE SPECIMEN, measured in production 2026-08-17

    market   58609021  ticker KXMLBTOTAL-26AUG051940MINKC   -> the Aug 5 MIN@KC game
    event    15187509  commence 2026-08-06 23:30Z            -> the Aug 6 MIN@KC game
                       espn_id  401816420                     -> soundly, correctly Aug 6

Nothing about the EVENT is wrong. Its provider id dereferences to the game it claims
to be. So ``disputed()`` — which asks only whether the event is a re-key impostor or
misdated — waved it through, and the contamination census declared three of that
market's outcomes **adjudicable today**, proposing to grade an Aug 5 market from the
Aug 6 game's truth. Four more of its rows sat inside the "AGREES ANYWAY" exclusion,
agreeing with a score that belongs to *neither* game.

Identity before grade, a fourth time. Market identity is identity too.

WHY THE EASTERN CONVERSION IS PART OF THE PREDICATE AND NOT AN AESTHETIC

Kalshi's ticker date is the US Eastern game date. Almost every MLB night game starts
after 00:00 UTC on the following day, so comparing the ticker against the event's UTC
date manufactures a disagreement for most of the schedule — and a census that flags
most of its population is one nobody reads twice.
"""

from datetime import date, datetime, timezone

from scripts.census_settlement_contamination import (
    market_identity_disputed,
    ticker_game_date,
)

# The real rows, so the constants below are evidence and not fixtures.
AUG5_TICKER = "KXMLBTOTAL-26AUG051940MINKC"
AUG6_EVENT_COMMENCE = "2026-08-06 23:30:00+00:00"
AUG5_EVENT_COMMENCE = "2026-08-05 23:40:00+00:00"


class TestTickerGameDate:

    def test_the_specimens_ticker_reads_as_august_5(self):
        assert ticker_game_date(AUG5_TICKER) == date(2026, 8, 5)

    def test_a_ticker_without_a_time_component_still_parses(self):
        assert ticker_game_date("KXMLBGAME-26AUG05MINKC") == date(2026, 8, 5)

    def test_every_month_abbreviation_is_understood(self):
        for i, mon in enumerate(
            ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
             "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], start=1
        ):
            assert ticker_game_date(f"KXMLBGAME-26{mon}15AAABBB") == date(2026, i, 15)

    def test_an_unparseable_ticker_is_none_not_a_guess(self):
        assert ticker_game_date("KXNBACHAMP-26") is None
        assert ticker_game_date("no-date-here") is None
        assert ticker_game_date(None) is None
        assert ticker_game_date("") is None

    def test_an_impossible_date_is_none_rather_than_an_exception(self):
        """A census must not die on one malformed row."""
        assert ticker_game_date("KXMLBGAME-26FEB30AAABBB") is None
        assert ticker_game_date("KXMLBGAME-26XXX05AAABBB") is None


class TestMarketIdentityDisputed:

    def test_the_production_specimen_is_disputed(self):
        """market 58609021 on event 15187509 — the row that read 'identity certain'."""
        assert market_identity_disputed(AUG5_TICKER, AUG6_EVENT_COMMENCE) is True

    def test_the_same_market_on_its_own_game_is_not_disputed(self):
        assert market_identity_disputed(AUG5_TICKER, AUG5_EVENT_COMMENCE) is False

    def test_a_night_game_is_not_a_dispute(self):
        """19:40 ET on Aug 5 is 23:40 UTC on Aug 5 — same UTC day, still fine."""
        assert market_identity_disputed(
            "KXMLBGAME-26AUG051940MINKC", "2026-08-05 23:40:00+00:00"
        ) is False

    def test_a_late_night_game_crossing_midnight_utc_is_not_a_dispute(self):
        """22:10 ET Jul 30 = 02:10 UTC Jul 31. The UTC date differs by design.

        This is the case that would make the predicate cry wolf across most of the
        West-coast schedule if it compared UTC dates.
        """
        assert market_identity_disputed(
            "KXMLBHRR-26JUL302210SFSD", "2026-07-31 02:10:00+00:00"
        ) is False

    def test_a_naive_datetime_is_read_as_utc(self):
        assert market_identity_disputed(
            "KXMLBGAME-26AUG051940MINKC", datetime(2026, 8, 5, 23, 40)
        ) is False

    def test_a_real_datetime_object_works_as_well_as_a_string(self):
        aware = datetime(2026, 8, 6, 23, 30, tzinfo=timezone.utc)
        assert market_identity_disputed(AUG5_TICKER, aware) is True

    def test_an_unreadable_identity_is_not_reported_as_agreement(self):
        """Unknown must not be spelled the same way as fine (gotcha #53).

        It returns False — the row is not *asserted* disputed — but the reason is
        that we cannot read it, which is why the season markets are counted
        separately rather than folded into a clean bill of health.
        """
        assert market_identity_disputed(None, AUG6_EVENT_COMMENCE) is False
        assert market_identity_disputed("KXNBACHAMP-26", AUG6_EVENT_COMMENCE) is False

    def test_a_missing_commence_time_cannot_dispute_anything(self):
        assert market_identity_disputed(AUG5_TICKER, None) is False
        assert market_identity_disputed(AUG5_TICKER, "not-a-timestamp") is False

    def test_a_market_weeks_away_from_its_event_is_disputed(self):
        """The other measured class: same teams, months apart, collapsed onto one row."""
        assert market_identity_disputed(
            "KXMLBHIT-26JUN131507NYYTOR", "2026-08-14 23:15:00+00:00"
        ) is True


class TestTheCensusConsumesIt:
    """A predicate nothing calls is a document, not a gate."""

    def test_the_detail_query_selects_the_markets_own_identity(self):
        import inspect

        from scripts import census_settlement_contamination as census

        src = inspect.getsource(census.main)
        assert "fm.external_id" in src, (
            "without the ticker the census can only ask whether the EVENT is "
            "disputed, which is the hole this queue closed"
        )
        assert "ev.commence_time" in src, (
            "the predicate needs the event's own time from the DETAIL row — the "
            "findings dict never carried it, and reading it from there made the "
            "check a silent no-op"
        )

    def test_the_tier_split_calls_the_predicate(self):
        import inspect

        from scripts import census_settlement_contamination as census

        src = inspect.getsource(census.main)
        assert "market_identity_disputed(rec[9], rec[10])" in src
        assert "tier_m" in src
        assert "agrees_market_disputed" in src, (
            "the AGREES ANYWAY exclusion is where four of the specimen's seven wrong "
            "rows were hiding; it must be re-tested too"
        )
