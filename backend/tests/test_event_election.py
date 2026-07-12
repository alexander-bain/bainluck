"""L2-89 (B6, civic proof): election adapter pure helpers — proves the "config
drop" grammar over the real KX election ticker/name shapes (verified live
2026-07-12). The adapter's build_event is exercised via the route test
(test_route_event_concept.py)."""

from app.utils.event_election import (
    ELECTIONS,
    classify_election_market,
    clean_race_label,
    derive_election_concept,
    election_edition_year,
    is_race,
    parse_election_slug,
)


class TestParseElectionSlug:
    def test_canonical(self):
        cfg = parse_election_slug("2026-midterms")
        assert cfg is not None and cfg.slug == "2026-midterms"
        assert cfg.edition == 26

    def test_aliases_resolve(self):
        assert parse_election_slug("midterms").slug == "2026-midterms"
        assert parse_election_slug("2026").slug == "2026-midterms"
        assert parse_election_slug("midterms-2026").slug == "2026-midterms"

    def test_unknown_is_none(self):
        assert parse_election_slug("2030-midterms") is None
        assert parse_election_slug("") is None


class TestEditionYear:
    def test_ticker_year_token(self):
        assert election_edition_year("KXGOVCA-26") == 26
        assert election_edition_year("KXSENATEOHSR-26") == 26
        assert election_edition_year("kalshi:KXHOUSEWINSTATE-FLD") is None  # no year token
        assert election_edition_year("KXPRESNOMD-28") == 28  # a different edition

    def test_implausible_token(self):
        assert election_edition_year("KXSOMETHING-99") is None


class TestClassifyElectionMarket:
    def test_governor_general_race(self):
        assert classify_election_market("KXGOVCA-26", "California Governor winner?") == "governor_race"
        assert classify_election_market("KXGOVAK-26", "Alaska Governor winner? (Person)") == "governor_race"

    def test_govt_shutdown_is_novelty_not_governor(self):
        # KXGOVT... is the government (shutdown) false-friend of KXGOV (governor).
        assert classify_election_market("KXGOVTSHUTLENGTH-26FEB07", "How long will the government shutdown last?") == "novelty"

    def test_primaries_and_nominees(self):
        assert classify_election_market("KXSENATEOHSR-26", "Ohio Republican Senate nominee?") == "primary"
        assert classify_election_market("KXGOVMENOMR-26", "Maine Republican Governor nominee?") == "primary"
        assert classify_election_market("KXGOVAKPRIMARY-26", "Alaska Governor primary: who will advance?") == "primary"

    def test_house_seat_forecast(self):
        assert classify_election_market("KXHOUSEWINSTATE-FLD", "How many House seats will Democrats win in Florida?") == "seat_forecast"

    def test_novelties_excluded(self):
        assert classify_election_market("KXHOUSEPOPVOTEMARGIN-27NOV03", "2026 Midterms: House popular vote margin of victory?") == "novelty"
        assert classify_election_market("KXHOUSETURNOUT-26NOV03", "2026 Midterms: U.S. House turnout?") == "novelty"
        assert classify_election_market("KXHOUSEEXPEL-26JUN01", "How many House Representatives will be expelled before June?") == "novelty"
        assert classify_election_market("KXCONGRESSTESTIFY-27JAN", "Who will testify in front of Congress in 2026?") == "novelty"
        assert classify_election_market("KXCONGRESSTRADES-25", "Which member of Congress will have the biggest returns?") == "novelty"

    def test_leadership_contest_is_novelty(self):
        assert classify_election_market("KXSENATEDEMLEAD-28JAN01", "Who will win the next Senate Democratic Leader election?") == "novelty"

    def test_control_when_it_appears(self):
        # No such market today (honest gap), but the grammar must fold it in as the
        # marquee-eligible race when Kalshi lists one.
        assert classify_election_market("KXSENATECONTROL-26", "Which party will control the Senate?") == "control"
        assert classify_election_market("KXHOUSEMAJORITY-26", "House majority after 2026 midterms?") == "control"


class TestIsRace:
    def test_races(self):
        assert is_race("governor_race")
        assert is_race("senate_race")
        assert is_race("house_race")
        assert is_race("control")

    def test_non_races(self):
        assert not is_race("primary")
        assert not is_race("seat_forecast")
        assert not is_race("novelty")
        assert not is_race("other")


class TestCleanRaceLabel:
    def test_strips_winner_and_qmark(self):
        assert clean_race_label("California Governor winner?") == "California Governor"

    def test_strips_person_party_parenthetical(self):
        assert clean_race_label("Alaska Governor winner? (Person)") == "Alaska Governor"
        assert clean_race_label("Alaska Governor winner? (Party)") == "Alaska Governor"

    def test_empty_falls_back(self):
        assert clean_race_label("") == ""


class TestDeriveElectionConcept:
    def test_race_surfaces_concept(self):
        c = derive_election_concept("KXGOVCA-26", "California Governor winner?")
        assert c["key"] == "event:election:2026-midterms"
        assert c["domain"] == "election"
        assert c["name"] == "2026 Midterm Elections"

    def test_primary_surfaces_concept(self):
        # A 2026 primary still belongs to the 2026 election night page.
        c = derive_election_concept("KXSENATEOHSR-26", "Ohio Republican Senate nominee?")
        assert c is not None and c["key"] == "event:election:2026-midterms"

    def test_wrong_edition_is_none(self):
        # 2028 presidential nominee is a different election concept — not 2026.
        assert derive_election_concept("KXPRESNOMD-28", "2028 Democratic presidential nominee") is None

    def test_novelty_is_none(self):
        assert derive_election_concept("KXGOVTSHUTLENGTH-26FEB07", "How long will the government shutdown last?") is None
        assert derive_election_concept("KXHOUSETURNOUT-26NOV03", "U.S. House turnout?") is None

    def test_non_election_is_none(self):
        assert derive_election_concept("KXPGATOUR-THOC26", "The Open Championship Winner") is None
        assert derive_election_concept(None, None) is None


class TestElectionsConfig:
    def test_edition_is_two_digit(self):
        for cfg in ELECTIONS.values():
            assert 20 <= cfg.edition <= 45
            assert cfg.display
