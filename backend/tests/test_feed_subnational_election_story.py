"""#1885 — sub-national elections had no story key, so the cap could not see them.

The mechanism was proven by calling `_story_key` in a REPL and reading `None` for
all eleven cards of one family. These tests are that probe, kept.

Every name below is a REAL market title taken from production
(`futures_markets`, status=open, 2026-08-17) — not invented. That matters twice
over: the filed family (Taiwanese county magistrates) had already rotated out of
the live feed by the time the fix was written, and an identically-shaped one
(Brazilian state races) had replaced it. A fixture of invented titles would have
proved the regex matched the regex.
"""

from app.utils.feed_market_quality import (
    _story_key,
    _subnational_election_story_key,
)

FOREIGN = "story:foreign_local_elections"
US_STATE = "story:us_state_races"


class TestForeignSubnationalElectionsGetAFamily:
    """Direction one: the flood must become countable."""

    def test_the_filed_taiwanese_magistrate_family_is_one_key(self):
        # The eleven cards from the filed report. All eleven returned None.
        counties = [
            "Taitung",
            "Kinmen",
            "Yunlin",
            "Pingtung",
            "Nantou",
            "Miaoli",
            "Chiayi",
            "Yilan",
            "Lienchiang",
            "Penghu",
            "Hsinchu",
        ]
        keys = {
            _story_key(f"{c} County Magistrate Election Winner", "politics")
            for c in counties
        }
        assert keys == {FOREIGN}, (
            "all eleven must share ONE key — a cap counts a family, and a family "
            "of eleven distinct Nones is eleven families of one"
        )

    def test_the_brazilian_state_family_that_replaced_it(self):
        # Live on the feed page measured 2026-08-17.
        for name in [
            "Amapá Governor Election Winner",
            "Alagoas Governor Election Winner",
            "Amazonas Governor Election Winner",
            "Acre Governor Election Winner",
            "Paraná Senate Election: 1st Place",
            "Ceará gubernatorial election winner?",
        ]:
            assert _story_key(name, "politics") == FOREIGN, name

    def test_mexican_and_russian_subnational_families(self):
        # Caught for free by keying on the OFFICE rather than a place list —
        # which is the entire argument of the fix.
        assert _story_key("Aguascalientes Governor Election Winner", "politics") == FOREIGN
        assert _story_key("Belgorod Oblast Gubernatorial Election Winner", "politics") == FOREIGN
        assert _story_key("Altai Krai Parliament Election: Party Winner", "politics") == FOREIGN

    def test_brazils_federal_district_is_brazilian_not_american(self):
        # Found while measuring, not after: a `federal` token in the US-marker
        # guard filed Brasília's Distrito Federal as a US federal market.
        assert _story_key("Federal District Governor Election Winner", "politics") == FOREIGN
        assert _story_key("Federal District Senate Election: 1st Place", "politics") == FOREIGN


class TestUSStateRacesGetTheirOwnFamily:
    def test_us_state_governor_and_senate_races(self):
        for name in [
            "Alabama Governor Election Winner",
            "Alabama Senate winner?",
            "Texas Senate winner?",
            "Maine Senate winner? (Person)",
            "Alaska Governor winner? (Party)",
            "2026 Texas Senate matchup?",
        ]:
            assert _story_key(name, "politics") == US_STATE, name

    def test_us_congressional_districts(self):
        assert _story_key("AK-AL House Election Winner", "politics") == US_STATE

    def test_us_and_foreign_families_are_separate_keys(self):
        # Deliberately NOT one key: their caps are different product decisions
        # (a competitive Senate midterm is a national story; two Brazilian state
        # races are not), and one key cannot carry two caps.
        assert _story_key("Texas Senate winner?", "politics") != _story_key(
            "Amapá Governor Election Winner", "politics"
        )


class TestBothDirections:
    """Gotcha #43 — a cap's guard tests must assert BOTH directions.

    A key that swallows national elections would be a worse bug than the one it
    fixes: it would silently cap the markets people actually came for.
    """

    def test_national_presidential_elections_are_never_captured(self):
        for name in [
            "Brazil Presidential Election",
            "Argentina presidential election winner?",
            "2027 French Presidential Election: who will be on the ballot?",
            # Names a Brazilian state and is STILL a national market.
            "Brazil Presidential Election First Round: 1st Place in Acre",
        ]:
            assert _subnational_election_story_key(name) is None, name

    def test_national_legislative_elections_are_not_captured(self):
        for name in [
            "UK General Election Winner",
            "2028 Senate winner",  # no place token — federal
            "2028: Who will win the Presidency, House, and Senate?",
        ]:
            assert _subnational_election_story_key(name) is None, name

    def test_a_year_is_not_a_place(self):
        # The capitalised-place requirement is what stops "2028 Senate winner"
        # reading as a race in a country called 2028.
        assert _subnational_election_story_key("2028 Senate winner") is None
        assert _subnational_election_story_key("2026 Senate Election Winner") is None

    def test_central_bank_governors_are_not_elections(self):
        for name in [
            "Who will be the next Governor of the Bank of England?",
            "Next Federal Reserve Chair",
            "Reserve Bank of India Governor winner?",
        ]:
            assert _subnational_election_story_key(name) is None, name

    def test_existing_story_keys_are_not_re_homed(self):
        # The new arm is LAST in the cascade and only ever converts a None.
        assert _story_key("2028 Democratic Presidential Nominee", "politics") == (
            "story:us_2028_election"
        )
        assert _story_key("Will Iran close the Strait of Hormuz?", "politics") == (
            "story:middle_east_conflict"
        )
        assert _story_key("Will Russia capture Pokrovsk?", "politics") == (
            "story:russia_ukraine"
        )
        assert _story_key("New York City mayoral election winner?", "politics") == (
            "story:regional_us_elections"
        )

    def test_non_election_markets_are_untouched(self):
        for name in [
            "Will the U.S. confirm that aliens exist?",
            "Fed decision in September?",
            "Best Picture winner?",
        ]:
            assert _subnational_election_story_key(name) is None, name


class TestTheCapCanNowSeeTheFamily:
    def test_both_new_keys_have_an_explicit_cap(self):
        # A key with no entry silently inherits the generic `story_family_cap`,
        # which is how a family can have a key and still flood. Assert the dial
        # exists rather than trusting the default.
        import inspect

        from app.utils import feed_market_quality

        source = inspect.getsource(feed_market_quality)
        assert f'"{FOREIGN}": 1' in source
        assert f'"{US_STATE}": 2' in source
