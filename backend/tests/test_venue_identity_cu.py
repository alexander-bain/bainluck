"""venue-identity@1 — the venue's own identity for a market, read from `group_id`."""

from app.utils.venue_identity import (
    VenueIdentity,
    kalshi_supersedes,
    same_venue_market,
    venue_identity,
)


def test_kalshi_series_and_edition_come_from_the_event_ticker():
    assert venue_identity("kalshi", "kalshi:KXNBAMVP-27") == VenueIdentity(
        venue="kalshi", event="KXNBAMVP-27", series="KXNBAMVP", edition=27, rest=""
    )
    seed = venue_identity("kalshi", "kalshi:KXNBASEED-27EAST8")
    assert (seed.series, seed.edition, seed.rest) == ("KXNBASEED", 27, "EAST8")


def test_an_implausible_token_is_a_series_id_not_an_edition():
    # Grammy tickers end in a Kalshi series id (event_awards.edition_year).
    grammy = venue_identity("kalshi", "kalshi:KXGRAMAOTY-69")
    assert grammy.series == "KXGRAMAOTY" and grammy.edition is None


def test_a_three_digit_run_is_not_read_as_an_edition():
    row = venue_identity("kalshi", "kalshi:KXFOO-270ABC")
    assert row.edition is None


def test_polymarket_carries_its_event_and_no_edition():
    assert venue_identity("polymarket", "polymarket:1196500") == VenueIdentity(
        venue="polymarket", event="1196500"
    )


def test_a_group_id_from_another_venue_is_refused():
    assert venue_identity("polymarket", "kalshi:KXNBAMVP-27") is None
    assert venue_identity("kalshi", None) is None
    assert venue_identity(None, "kalshi:KXNBAMVP-27") is None
    assert venue_identity("kalshi", "KXNBAMVP-27") is None


def test_same_venue_decides_and_cross_venue_does_not():
    a = venue_identity("kalshi", "kalshi:KXNBAMVP-26")
    b = venue_identity("kalshi", "kalshi:KXNBAMVP-27")
    p = venue_identity("polymarket", "polymarket:1196500")
    assert same_venue_market(a, a) is True
    assert same_venue_market(a, b) is False
    assert same_venue_market(a, p) is None
    assert same_venue_market(a, None) is None


def test_a_later_edition_of_the_same_series_supersedes_only_that_series():
    mvp26 = venue_identity("kalshi", "kalshi:KXNBAMVP-26")
    mvp27 = venue_identity("kalshi", "kalshi:KXNBAMVP-27")
    fin26 = venue_identity("kalshi", "kalshi:KXNBAFINMVP-26")
    assert kalshi_supersedes(mvp27, mvp26) is True
    assert kalshi_supersedes(mvp26, mvp27) is False
    assert kalshi_supersedes(mvp27, fin26) is False
    assert kalshi_supersedes(mvp27, mvp27) is False
    grammy = venue_identity("kalshi", "kalshi:KXGRAMAOTY-69")
    assert kalshi_supersedes(mvp27, grammy) is False


def test_two_players_in_a_per_player_series_are_not_editions_of_each_other():
    # Real ticker shapes: one Kalshi event per player, with the year token in front.
    chase26 = venue_identity("kalshi", "kalshi:KXNEXTTEAMNFL-26JCHASE")
    burrow27 = venue_identity("kalshi", "kalshi:KXNEXTTEAMNFL-27JBURROW")
    chase27 = venue_identity("kalshi", "kalshi:KXNEXTTEAMNFL-27JCHASE")
    assert kalshi_supersedes(burrow27, chase26) is False
    assert kalshi_supersedes(chase27, chase26) is True
    east26 = venue_identity("kalshi", "kalshi:KXNBASEED-26EAST8")
    east27 = venue_identity("kalshi", "kalshi:KXNBASEED-27EAST8")
    west26 = venue_identity("kalshi", "kalshi:KXNBASEED-26WEST8")
    assert kalshi_supersedes(east27, east26) is True
    assert kalshi_supersedes(east27, west26) is False
