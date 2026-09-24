"""#8430 — searching a Challenger player finds the priced match, not an empty copy.

Production 2026-09-24 ~21:00Z, `/api/events/search?q=Boyer` served ONE game row,
`15317846 Tristan Boyer v Sebastian Gorzny` — market-born, no price, no markets —
and dropped both priced rows of the match for being surname-only. The rows below
are that page's candidates, transcribed from `events` (id, names, commence_time,
commence_time_source, win_probability_sources presence, sport key).

CERT-3402 BLOCKed the creator fix for leaving this reader result standing; this
file guards the reader half.
"""

import random
from datetime import datetime, timezone


class _Sport:
    def __init__(self, key):
        self.key = key


class _Row:
    def __init__(
        self,
        id,
        home,
        away,
        commence,
        sport_key,
        source,
        *,
        sources=None,
        status="suspended",
        home_score=None,
        away_score=None,
        completed_at=None,
    ):
        self.id = id
        self.home_team_name = home
        self.away_team_name = away
        self.commence_time = commence
        self.sport = _Sport(sport_key)
        self.commence_time_source = source
        self.win_probability_sources = sources
        self.status = status
        self.home_score = home_score
        self.away_score = away_score
        self.completed_at = completed_at


def _at(iso):
    return datetime.fromisoformat(iso).replace(tzinfo=timezone.utc)


PM = "polymarket_venue"
PRICE_PM = {"polymarket": {"value": 0.75}}
PRICE_KALSHI = {"kalshi": {"value": 0.99}}

D24 = _at("2026-09-24T17:00:00")
FULL = ("Tristan Boyer", "Sebastian Gorzny")
SHORT = ("Boyer", "Gorzny")

PRICED_PM = 15317904
PRICED_KALSHI = 15318254


def _boyer_page():
    empties_24 = [
        (15317844, SHORT), (15317845, SHORT), (15317846, FULL), (15317847, SHORT),
        (15317888, SHORT), (15317889, FULL), (15317891, SHORT), (15317892, SHORT),
        (15317905, FULL), (15317906, SHORT), (15317908, SHORT),
    ]
    rows = [
        _Row(i, *names, D24, "tennis_other", PM) for i, names in empties_24
    ]
    rows.append(
        _Row(15317735, *FULL, _at("2026-09-23T17:00:00"), "tennis_other", PM, sources={})
    )
    rows.append(
        _Row(PRICED_PM, *SHORT, _at("2026-09-23T17:00:00"), "tennis_other", PM,
             sources=PRICE_PM)
    )
    rows.append(
        _Row(PRICED_KALSHI, *SHORT, _at("2026-09-24T22:00:00"), "tennis_atp", "kalshi",
             sources=PRICE_KALSHI, status="scheduled")
    )
    return rows


def test_searching_boyer_serves_the_priced_rows_and_no_empty_copy():
    from app.utils.search_fixture_dedup import collapse_duplicate_fixtures

    kept, dropped = collapse_duplicate_fixtures(_boyer_page())

    assert {r.id for r in kept} == {PRICED_PM, PRICED_KALSHI}
    assert dropped == 12


def test_the_empty_full_name_row_no_longer_hides_the_priced_one():
    """Clause 1 alone, with no second empty row for clause 2 to lean on."""
    from app.utils.search_fixture_dedup import duplicate_fixture_event_ids

    ghost = _Row(15317846, *FULL, D24, "tennis_other", PM)
    priced = _Row(PRICED_PM, *SHORT, _at("2026-09-23T17:00:00"), "tennis_other", PM,
                  sources=PRICE_PM)

    assert duplicate_fixture_event_ids([ghost, priced]) == {15317846}


def test_the_result_does_not_depend_on_page_order():
    from app.utils.search_fixture_dedup import duplicate_fixture_event_ids

    expected = duplicate_fixture_event_ids(_boyer_page())
    rng = random.Random(8430)
    for _ in range(25):
        page = _boyer_page()
        rng.shuffle(page)
        assert duplicate_fixture_event_ids(page) == expected


def test_a_priced_ghost_beside_an_unpriced_tournament_row_collapses_as_before():
    """#2623's shape: the schedule row is the survivor, and clause 2 never hides it."""
    from app.utils.search_fixture_dedup import duplicate_fixture_event_ids

    tournament = _Row(1, "Aryna Sabalenka", "Polina Iatcenko", _at("2026-09-02T23:00:00"),
                      "tennis_wta_us_open", "odds_api", status="scheduled")
    ghost = _Row(2, "Sabalenka", "Iatcenko", _at("2026-09-02T20:00:00"), "tennis_wta",
                 "kalshi", sources=PRICE_KALSHI, status="scheduled")

    assert duplicate_fixture_event_ids([tournament, ghost]) == {2}


def test_an_empty_schedule_row_is_never_hidden_by_a_priced_sibling():
    from app.utils.search_fixture_dedup import duplicate_fixture_event_ids

    schedule = _Row(1, *FULL, D24, "tennis_atp", "odds_api", status="scheduled")
    priced = _Row(2, *FULL, D24, "tennis_atp", "kalshi", sources=PRICE_KALSHI,
                  status="scheduled")

    assert 1 not in duplicate_fixture_event_ids([schedule, priced])


def test_a_market_born_row_carrying_any_truth_is_not_an_empty_copy():
    from app.utils.search_fixture_dedup import duplicate_fixture_event_ids

    priced = _Row(2, *SHORT, D24, "tennis_other", PM, sources=PRICE_PM)
    for truth in (
        {"home_score": 1},
        {"away_score": 0},
        {"completed_at": _at("2026-09-24T19:00:00")},
    ):
        row = _Row(1, *SHORT, D24, "tennis_other", PM, **truth)
        assert 1 not in duplicate_fixture_event_ids([row, priced]), truth


def test_an_empty_copy_with_no_priced_sibling_still_renders():
    from app.utils.search_fixture_dedup import duplicate_fixture_event_ids

    a = _Row(1, *SHORT, D24, "tennis_other", PM)
    b = _Row(2, *SHORT, D24, "tennis_other", PM, sources={})

    assert duplicate_fixture_event_ids([a, b]) == set()


def test_a_priced_row_outside_the_window_does_not_hide_the_empty_copy():
    from app.utils.search_fixture_dedup import duplicate_fixture_event_ids

    empty = _Row(1, *SHORT, D24, "tennis_other", PM)
    later = _Row(2, *SHORT, _at("2026-09-27T17:00:00"), "tennis_other", PM,
                 sources=PRICE_PM)

    assert duplicate_fixture_event_ids([empty, later]) == set()


def test_a_namesake_is_never_the_priced_sibling():
    """Same surnames, so same group — but a different player's priced match."""
    from app.utils.search_fixture_dedup import duplicate_fixture_event_ids

    empty = _Row(1, "Tristan Boyer", "Sebastian Gorzny", D24, "tennis_other", PM)
    priced = _Row(2, "Mark Boyer", "Sebastian Gorzny", D24, "tennis_other", PM,
                  sources=PRICE_PM)

    assert 1 not in duplicate_fixture_event_ids([empty, priced])


def test_a_priced_row_the_page_already_hid_does_not_hide_the_empty_copy():
    """Clause 2 reads the dominance pass's SURVIVORS.

    The Final hides the priced ghost 30h later (it has the result); the empty
    copy sits 60h after the Final, outside its window, and 30h after the hidden
    priced row. That hidden row is not on the page, so it is no reason to take
    the empty copy off it either.
    """
    from app.utils.search_fixture_dedup import duplicate_fixture_event_ids

    final = _Row(1, *FULL, _at("2026-09-20T12:00:00"), "tennis_atp", "odds_api",
                 status="completed", home_score=2, away_score=0,
                 completed_at=_at("2026-09-20T14:00:00"))
    priced = _Row(2, *SHORT, _at("2026-09-21T18:00:00"), "tennis_atp", "kalshi",
                  sources=PRICE_KALSHI)
    empty = _Row(3, *FULL, _at("2026-09-23T00:00:00"), "tennis_other", PM)

    assert duplicate_fixture_event_ids([final, priced, empty]) == {2}


def test_a_swapped_orientation_priced_row_still_replaces_the_empty_copy():
    from app.utils.search_fixture_dedup import duplicate_fixture_event_ids

    empty = _Row(1, "Tristan Boyer", "Sebastian Gorzny", D24, "tennis_other", PM)
    priced = _Row(2, "Gorzny", "Boyer", D24, "tennis_other", PM, sources=PRICE_PM)

    assert duplicate_fixture_event_ids([empty, priced]) == {1}


def test_the_market_born_set_matches_the_drain_verdicts():
    from app.services.anchor_channel import MARKET_BORN_COMMENCE_SOURCES as drain
    from app.utils.search_fixture_dedup import MARKET_BORN_COMMENCE_SOURCES as search

    assert search == drain
