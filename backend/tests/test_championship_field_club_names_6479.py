"""The championship boards stop offering a club that does not exist (#6479).

WHAT A READER SAW, ON PRODUCTION 2026-09-16
===========================================

`https://bainluck.com` → search `Los Angeles`, and the first futures card is the
Super Bowl field, led by its favourite::

    2027 Pro Football Champion              (market 40533, KXSB-27)
        Los Angeles R        12%      <- not a club
        Buffalo               9.5%
        Baltimore             7.5%

and `New York` reaches the World Series field the same way::

    Pro Baseball Champion                   (market 275, KXMLB-26)
        Los Angeles D        <- not a club
        New York Y           <- not a club

These are the two longest-lived cards on the site — 32 and 30 rungs — reachable
from search, the sport pages, Discover, and their own detail pages, where the
WHOLE ladder renders and all ten truncated rungs show at once:
`Los Angeles R`, `Los Angeles C`, `New York G`, `New York J` (football) and
`Los Angeles D`, `Los Angeles A`, `New York Y`, `New York M`, `Chicago C`,
`Chicago WS` (baseball).

WHY #6447's TWO SHIPS COULD NOT REACH IT
========================================

#6447 completes a GAME market's sides by reading the club codes off the
market's ticker: `KXNFLGAME-26SEP20GBNYJ` carries `GB` and `NYJ`. A
championship market's ticker is `KXSB-27` — no date, no codes, no pair — so
`repair_truncated_names` correctly declines rather than guessing, and
`test_the_championship_field_is_untouched_and_that_is_recorded` pins that as
the answer of the day.

The completion is one level down and it is id-anchored: each OUTCOME carries
its own ticker, and the team code is in it. Read off production, these are the
ten rows above, by their real `futures_outcomes.external_id`.

WHAT THIS FILE HOLDS DOWN
=========================

Three things, and the third is the one that bites.

1. The engine completes exactly the truncations, from the rung's own ticker,
   and refuses everything else.
2. The two reader surfaces — the detail ladder and the search/typeahead card —
   both carry the repair, because #993's lesson is that fixing one surface of a
   pair moves a disagreement rather than ending it.
3. 🔴 **`kxsb` is not the Super Bowl.** The map entry that unlocks the football
   half is matched with `startswith`, and the bare prefix also reaches five
   Starbucks series, a Senate budget-resolution series and a Slovak basketball
   game — seven live series it would mis-sport as NFL. Every one is named below
   by its production ticker.
"""

from __future__ import annotations

import pytest

from app.utils import sport_keys as sport_keys_module
from app.utils.game_market_club_names import repair_field_outcome_name
from app.utils.kalshi_display_names import (
    repair_outcome_name_by_ticker,
    repair_truncated_names,
)
from app.utils.prediction_market_matching import (
    extract_team_code_from_outcome_ticker,
)
from app.utils.sport_keys import (
    KALSHI_FUTURES_TICKER_TO_SPORT_KEY,
    KALSHI_TICKER_TO_SPORT_KEY,
    get_sport_key_from_ticker,
    is_kalshi_game_level_ticker,
    is_kalshi_shadowed_futures_ticker,
)

NFL = "americanfootball_nfl"

#: The ten truncated rungs on the two open boards, `(outcome ticker, shipped
#: name, the club)`. Every triple is a real row read off production
#: 2026-09-16 — `futures_outcomes` joined to `futures_markets` on ids 40533
#: (`KXSB-27`) and 275 (`KXMLB-26`).
TRUNCATED_RUNGS = [
    ("KXSB-27-LAR", "Los Angeles R", "Los Angeles Rams"),
    ("KXSB-27-LAC", "Los Angeles C", "Los Angeles Chargers"),
    ("KXSB-27-NYG", "New York G", "New York Giants"),
    ("KXSB-27-NYJ", "New York J", "New York Jets"),
    ("KXMLB-26-LAD", "Los Angeles D", "Los Angeles Dodgers"),
    ("KXMLB-26-LAA", "Los Angeles A", "Los Angeles Angels"),
    ("KXMLB-26-NYY", "New York Y", "New York Yankees"),
    ("KXMLB-26-NYM", "New York M", "New York Mets"),
    ("KXMLB-26-CHC", "Chicago C", "Chicago Cubs"),
    ("KXMLB-26-CWS", "Chicago WS", "Chicago White Sox"),
]

#: Rungs of the SAME two boards that are not truncated and must ship byte-for
#: byte. `A's` and `St. Louis` are the interesting ones: both carry punctuation
#: that a looser shape test would trip over, and `Kansas City` ends in a word a
#: careless parser could read as an initial.
UNTRUNCATED_RUNGS = [
    ("KXSB-27-BUF", "Buffalo"),
    ("KXSB-27-GB", "Green Bay"),
    ("KXSB-27-KC", "Kansas City"),
    ("KXSB-27-NE", "New England"),
    ("KXMLB-26-ATH", "A's"),
    ("KXMLB-26-STL", "St. Louis"),
    ("KXMLB-26-BOS", "Boston"),
    ("KXMLB-26-SF", "San Francisco"),
]

#: 🔴 THE GOLD CONTROLS. Every one of these SHIPPED NAMES matches the truncation
#: SHAPE — ends in a run of one to three capitals — and not one of them is a
#: truncated club. All four are rows served by `/api/events/search` on
#: production 2026-09-16, with their real outcome ids.
#:
#: * `Super Bowl LX` is a Roman numeral, and its ticker is the sharpest control
#:   in the file: a genuine hyphenated Kalshi OUTCOME ticker ending in a
#:   three-letter code (`-SUP`). Only the sport lookup refuses it.
#: * `Rams Basaksehir FK … SK` really is a club whose name ends in `SK`, on a
#:   card whose first word is literally `Rams`.
#: * `Option E` is a Polymarket ladder rung on a hex condition id.
LOOKALIKE_CONTROLS = [
    ("KXSPORTSEMMY-26OLSSCE-SUP", "Super Bowl LX"),
    (
        "0x304dfd5713b3e6bf973eec44efea57fd3b12766df3a39b81c23b1beed00decdf",
        "Rams Başakşehir FK 3 - 3 Gençlerbirliği SK",
    ),
    (
        "0xa9d3f4db9b3fb1f78b4c83f76a1720a30f1327a403c1f19e2506053a5b76e1f7",
        "Option E",
    ),
    (
        "0x12b236e3db41812376d2f5f7580eebcfa5f1059c3003bff9fd702f9dc28d3079",
        "Option F",
    ),
]

#: 🔴 The seven live series `kxsb` would swallow, by their production tickers,
#: with the sport each one actually is. Read off `futures_markets` 2026-09-16.
KXSB_LOOKALIKE_SERIES = [
    ("KXSBUX-27JANSTORES", "economics: Starbucks total global stores in Q1 2027"),
    ("KXSBUXCC-26OCT07", "economics: Starbucks Credit Card Spend in September"),
    ("KXSBUXA-28JANSTORES", "economics: Starbucks total global stores in 2026"),
    ("KXSBUXSAR-26OCT02", "economics: Starbucks Refresher price in September"),
    ("KXSBUXFT-26AUG08", "economics: Starbucks Foot Traffic in July"),
    ("KXSBUDGETRES-26JUN", "politics: When will the Senate pass a budget resolution?"),
    ("KXSBLGAME-26MAY291300BRALEV", "basketball: Slovan Bratislava vs BK Levicki"),
]


# ─────────────────────────────────────────────────────────────────────────────
# 1. THE ENGINE
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("ticker,shipped,club", TRUNCATED_RUNGS)
def test_every_truncated_rung_on_both_boards_is_completed_6479(ticker, shipped, club):
    """The ship, stated on the ten rows that caused it."""
    assert repair_outcome_name_by_ticker(ticker, shipped) == club


@pytest.mark.parametrize("ticker,shipped", UNTRUNCATED_RUNGS)
def test_a_rung_that_is_already_a_name_is_not_rewritten_6479(ticker, shipped):
    """Correct data is never touched — the module's failure direction."""
    assert repair_outcome_name_by_ticker(ticker, shipped) is None
    assert repair_field_outcome_name(ticker, shipped) is None


@pytest.mark.parametrize("ticker,shipped", LOOKALIKE_CONTROLS)
def test_a_name_shaped_like_a_truncation_but_is_not_ships_untouched_6479(
    ticker, shipped
):
    """Shape is not evidence. Only a resolving ticker is.

    `Super Bowl LX` would become a different string under any rule that read the
    trailing capitals as an abbreviation of something.
    """
    assert repair_outcome_name_by_ticker(ticker, shipped) is None
    assert repair_field_outcome_name(ticker, shipped) is None


def test_the_shipped_text_must_agree_with_the_ticker_or_nothing_happens_6479():
    """The second signal, and the whole reason an id-anchored read is not enough.

    An id says which ROW; the club is still a LOOKUP, and a lookup can be stale
    or rotated. So the venue's own truncation has to be consistent with the
    nickname the code resolved. Pair the Rams' ticker with the Dodgers' name and
    the answer is the venue's text, not `Los Angeles Rams` and not a coin toss.
    """
    assert repair_outcome_name_by_ticker("KXSB-27-LAR", "Los Angeles R") == (
        "Los Angeles Rams"
    )
    assert repair_outcome_name_by_ticker("KXSB-27-LAR", "Los Angeles D") is None
    assert repair_outcome_name_by_ticker("KXMLB-26-CWS", "Chicago C") is None


def test_the_same_code_in_two_sports_is_two_different_clubs_6479():
    """`LAC` is the Chargers on a football board and the Clippers on a
    basketball one, and this is why the namespace is asked at all (#3672).

    If the resolver ever answered out of one shared vocabulary, one of these two
    lines would print the wrong club on a real card.
    """
    assert extract_team_code_from_outcome_ticker("KXSB-27-LAC") == ("lac", "Chargers")
    assert extract_team_code_from_outcome_ticker("KXNBA-26-LAC") == ("lac", "Clippers")
    assert repair_field_outcome_name("KXSB-27-LAC", "Los Angeles C") == (
        "Los Angeles Chargers"
    )
    assert repair_field_outcome_name("KXNBA-26-LAC", "Los Angeles C") == (
        "Los Angeles Clippers"
    )


def test_an_unregistered_series_resolves_nothing_rather_than_borrowing_6479():
    """#3672's direction, restated where this ship could reintroduce it.

    A series we hold no vocabulary for must yield NOTHING. A miss leaves the
    venue's text, which is merely short; a borrowed vocabulary mints a club.
    """
    assert get_sport_key_from_ticker("KXTOTALLYUNKNOWNSERIES") is None
    assert extract_team_code_from_outcome_ticker("KXTOTALLYUNKNOWNSERIES-26-LAR") is None
    assert repair_outcome_name_by_ticker(
        "KXTOTALLYUNKNOWNSERIES-26-LAR", "Los Angeles R"
    ) is None


def test_a_registered_sport_with_no_abbreviations_also_refuses_6479():
    """The OTHER arm, and the one a reader of the code would miss.

    "Unregistered series" is not the only way to have no vocabulary. Cricket IS
    in the futures map, so the series resolves to a sport perfectly well — and
    `_SPORT_KEY_TO_ABBREV_SUFFIX` holds no entry for it, so the namespace is
    `_unknown` and `_resolve_team_abbrev` refuses.

    Both arms must fail closed, and they fail at different steps. This test
    exists because the first version of the file above asserted cricket was
    unregistered, and it is not.
    """
    assert get_sport_key_from_ticker("KXCRICKETSERIES-26") == "cricket"
    assert extract_team_code_from_outcome_ticker("KXCRICKETSERIES-26-LAR") is None
    assert repair_outcome_name_by_ticker(
        "KXCRICKETSERIES-26-LAR", "Los Angeles R"
    ) is None


@pytest.mark.parametrize(
    "ticker",
    ["", None, "KXSB-27", "KXSB", "KXSB-27-", "KXSB-27-TOOLONGCODE", "KXSB-27-Z"],
)
def test_a_ticker_that_is_not_a_rung_ticker_is_refused_6479(ticker):
    """`KXSB-27` is the BOARD. A board names no team and must resolve none."""
    assert extract_team_code_from_outcome_ticker(ticker) is None
    assert repair_outcome_name_by_ticker(ticker, "Los Angeles R") is None


@pytest.mark.parametrize("shipped", ["", None, "Rams", "R", "   "])
def test_a_missing_or_cityless_name_is_refused_6479(shipped):
    """There is no city to compose onto, so there is no answer to give."""
    assert repair_outcome_name_by_ticker("KXSB-27-LAR", shipped) is None


def test_the_engine_is_pure_and_never_invents_a_name_6479():
    """Every repair is `city from the venue` + `nickname from the ticker`.

    Asserted structurally rather than by eye: the shipped city must survive
    verbatim as the head of the answer, and the answer must be strictly longer.
    """
    for ticker, shipped, club in TRUNCATED_RUNGS:
        city = shipped.rsplit(" ", 1)[0]
        assert club.startswith(city + " "), (shipped, club)
        assert len(club) > len(shipped)
        assert repair_outcome_name_by_ticker(ticker, shipped) == club


# ─────────────────────────────────────────────────────────────────────────────
# 2. THE `LA GALAXY` CLASS — why the reader half is not the engine
# ─────────────────────────────────────────────────────────────────────────────


#: Real doubling specimens, and they are MLS rather than the WNBA. `_consistent`
#: compares the truncated tail against the map value's FIRST word, so it happens
#: to refuse most city-carrying values outright — but not when the tail is
#: consistent with the CITY, which is every club whose venue truncation keeps the
#: city and drops the nickname. Enumerated across the `_mls` namespace: **62
#: shipped/ticker pairs over 29 clubs** reach the engine and double.
#:
#: `Seattle S` is the one to read: it is the natural way a fixed-width truncation
#: renders `Seattle Sounders`, and the engine alone answers `Seattle Seattle
#: Sounders`.
DOUBLING_SPECIMENS = [
    ("KXMLSCUP-26-SEA", "Seattle S", "Seattle Seattle Sounders", "Seattle Sounders"),
    ("KXMLSCUP-26-POR", "Portland P", "Portland Portland Timbers", "Portland Timbers"),
    ("KXMLSCUP-26-LAG", "LA L", "LA LA Galaxy", "LA Galaxy"),
    ("KXMLSCUP-26-ORL", "Orlando O", "Orlando Orlando City", "Orlando City"),
    ("KXMLSCUP-26-DC", "D.C. D", "D.C. D.C. United", "D.C. United"),
]


@pytest.mark.parametrize("ticker,shipped,doubled,club", DOUBLING_SPECIMENS)
def test_a_map_value_that_already_names_the_city_is_not_doubled_6479(
    ticker, shipped, doubled, club
):
    """🔴 The `LA Galaxy` class, and the whole reason the reader half exists.

    101 of the abbreviation map's values are WHOLE club names rather than bare
    nicknames — `chi_mls` is `Chicago Fire`, `sea_mls` is `Seattle Sounders`.
    The engine composes `city + nickname` and therefore says it twice.

    BOTH HALVES ARE ASSERTED, unconditionally. Pinning only the reader's answer
    would keep passing if the engine quietly stopped resolving these at all,
    which is a different bug wearing this test's green.
    """
    assert repair_outcome_name_by_ticker(ticker, shipped) == doubled
    assert repair_field_outcome_name(ticker, shipped) == club
    assert club.split()[0] in doubled.split()  # the doubling was real


def test_the_doubling_class_is_large_enough_to_be_worth_a_guard_6479():
    """If the map ever stops holding whole club names, this file is guarding a
    hazard that no longer exists and should be told so out loud."""
    from app.utils.prediction_market_matching import _KALSHI_TEAM_ABBREVS

    whole_names = [v for v in _KALSHI_TEAM_ABBREVS.values() if " " in v]
    assert len(whole_names) > 50, len(whole_names)


def test_declining_returns_none_and_never_the_string_it_was_given_6479():
    """The CONTRACT, which today's two callers cannot tell apart from a lie.

    Both wire it as `repair_field_outcome_name(...) or o.name`, so returning the
    input instead of `None` renders identically and no route test can catch it.
    It is still wrong, and the next caller is the one that pays: the sibling
    `repair_club_names` returns a COUNT of fields rewritten, and a decline that
    reports itself as an answer makes that count a fiction.

    The sharp case is a decline that `_uncompose` reaches by REFUSING — 206 such
    pairs exist, e.g. `Hawks H` on the Hawks' own ticker, where the composed
    answer would be `Hawks Hawks` and the honest reply is "leave it alone".
    """
    assert repair_outcome_name_by_ticker("KXNBA-26-ATL", "Hawks H") == "Hawks Hawks"
    assert repair_field_outcome_name("KXNBA-26-ATL", "Hawks H") is None

    for ticker, shipped, _club in TRUNCATED_RUNGS:
        assert repair_field_outcome_name(ticker, shipped) != shipped
    for ticker, shipped in UNTRUNCATED_RUNGS + LOOKALIKE_CONTROLS:
        assert repair_field_outcome_name(ticker, shipped) is None


def test_the_code_bound_covers_every_code_in_the_map_6479():
    """The outcome-ticker regex must not be MEANER than the vocabulary.

    A bound shorter than the map is a silent false negative: the rung simply
    stays truncated and no reader can report "the thing that did not happen".
    Written `{2,4}` first, which reads right and is wrong — `steti_soc`
    (Saint-Etienne) is five characters, so exactly one live code was refused
    before it could ever reach `_resolve_team_abbrev`.

    Asserted against the map rather than against a number, so adding a longer
    abbreviation reddens here instead of quietly narrowing the repair.
    """
    from app.utils.prediction_market_matching import (
        _KALSHI_TEAM_ABBREVS,
        _OUTCOME_TEAM_CODE_RE,
    )

    codes = {key.split("_")[0] for key in _KALSHI_TEAM_ABBREVS}
    assert codes, "the vocabulary has vanished"

    # ONE code is deliberately out of reach, and it is a length question only by
    # accident: `m05_soc` (Mainz 05) is the map's only alphanumeric code, and
    # admitting digits would make `KXSB-27` — the BOARD — parse as a rung whose
    # team code is "27". Alpha-only is what keeps "a field" and "a rung of a
    # field" structurally distinct rather than distinct only because the
    # vocabulary happens not to hold "27".
    alphanumeric = sorted(c for c in codes if not c.isalpha())
    assert alphanumeric == ["m05"], alphanumeric

    refused = sorted(
        code
        for code in codes
        if code.isalpha()
        and not _OUTCOME_TEAM_CODE_RE.match(f"KXSB-27-{code.upper()}")
    )
    assert refused == [], refused

    # ...and it is still a bound, not `+`: a run past the map's longest code is
    # not a team code and must not be parsed as one.
    longest = max(len(code) for code in codes if code.isalpha())
    assert _OUTCOME_TEAM_CODE_RE.match(f"KXSB-27-{'A' * (longest + 1)}") is None


def test_a_board_ticker_cannot_parse_as_one_of_its_own_rungs_6479():
    """The property the alpha-only code segment buys, stated on its own.

    `KXSB-27` and `KXMLB-26` end in a hyphen and a short run — exactly the shape
    of a rung — and differ from `KXSB-27-LAR` only in that the run is numeric.
    If this ever stopped holding, a whole board would start resolving to
    whichever club the year happened to look like.
    """
    from app.utils.prediction_market_matching import _OUTCOME_TEAM_CODE_RE

    for board in ("KXSB-27", "KXMLB-26", "KXNBA-26", "KXNHL-26"):
        assert _OUTCOME_TEAM_CODE_RE.match(board) is None, board
        assert extract_team_code_from_outcome_ticker(board) is None, board


@pytest.mark.parametrize(
    "shipped",
    [
        "Chicago WSXX",   # four capitals — past the truncation shape
        "Chicago ws",     # lowercase — the venue never truncates this way
        "Chicago  ",      # nothing to stand in for a nickname
    ],
)
def test_a_tail_outside_the_truncation_shape_is_refused_6479(shipped):
    """The shape gate's bound, asserted rather than assumed.

    It is a cheap PRE-FILTER, not the safety argument — `_consistent` and the
    ticker are what make a repair correct, and they would refuse most of these
    anyway. The bound still has to hold, because a widened shape is how a
    correct name starts being treated as a truncation.
    """
    assert repair_outcome_name_by_ticker("KXMLB-26-CWS", shipped) is None


@pytest.mark.parametrize("ticker,shipped,club", TRUNCATED_RUNGS)
def test_the_reader_half_agrees_with_the_engine_on_the_ten_rungs_6479(
    ticker, shipped, club
):
    assert repair_field_outcome_name(ticker, shipped) == club


# ─────────────────────────────────────────────────────────────────────────────
# 3. 🔴 THE PREFIX TRAP — `kxsb` is Starbucks and the Senate
# ─────────────────────────────────────────────────────────────────────────────


#: The OTHER open boards carrying a truncation, measured on production
#: 2026-09-16 after the two named in the issue — `(rung ticker, shipped, served)`,
#: `None` meaning the venue's text ships unchanged.
#:
#: The NBA board is repaired for free: `kxnba` was already registered, so the
#: engine reaches it with no further work and the ship's real population is 12
#: rungs, not 10. The three MLS rungs abstain, each for a DIFFERENT reason, and
#: that is why they are pinned rather than left to be rediscovered:
#:
#:   * `-LAFC` and `-NY` — no `lafc_mls` / `ny_mls` key. No vocabulary, no answer.
#:   * `-LAG` — resolves to `LA Galaxy`, and `_consistent` still refuses, because
#:     the map value's FIRST word is the city (`LA`) and the shipped tail `G`
#:     stands for the nickname. The answer is knowable and the agreement check
#:     cannot see it. A real, narrow gap; filed rather than widened here, because
#:     loosening `_consistent` is how a refusal rule stops refusing.
OTHER_OPEN_BOARDS = [
    ("KXNBA-27-LAC", "Los Angeles C", "Los Angeles Clippers"),
    ("KXNBA-27-LAL", "Los Angeles L", "Los Angeles Lakers"),
    ("KXMLSCUP-26-LAFC", "Los Angeles F", None),
    ("KXMLSCUP-26-LAG", "Los Angeles G", None),
    ("KXMLSCUP-26-NY", "New York RB", None),
]


@pytest.mark.parametrize("ticker,shipped,served", OTHER_OPEN_BOARDS)
def test_the_other_open_boards_land_where_they_were_measured_6479(
    ticker, shipped, served
):
    """Two more rungs repaired for free, three abstaining on the record.

    Asserted so the ship CLAIMS what it actually delivers (the NBA board is in
    the population and its after-check should cover it), and so the MLS
    abstentions are a documented boundary rather than an unnoticed hole.
    """
    assert repair_field_outcome_name(ticker, shipped) == served


def test_the_super_bowl_series_resolves_to_the_nfl_6479():
    """The one thing the map entry buys."""
    assert get_sport_key_from_ticker("KXSB-27") == NFL
    assert get_sport_key_from_ticker("KXSB-27-LAR") == NFL


@pytest.mark.parametrize("ticker,subject", KXSB_LOOKALIKE_SERIES)
def test_no_starbucks_or_senate_series_becomes_a_football_market_6479(ticker, subject):
    """🔴 THE KEEPER.

    Both maps are matched with `startswith`, so a bare `kxsb` key would reach
    every ticker below and call it the NFL — five Starbucks series, the Senate's
    budget resolution and a Slovak basketball game. That is #3672's failure mode
    arriving from a key that is too SHORT rather than a default that is too
    generous, and longest-prefix-wins cannot save it: a coffee chain has no
    sport key to register as the longer match.

    The registered key therefore terminates at the separator Kalshi uses to end
    a series name (`kxsb-`). This test is what makes that hyphen load-bearing
    rather than incidental — delete it from the key and seven live series turn
    into football.
    """
    assert get_sport_key_from_ticker(ticker) != NFL, subject


def test_the_hyphen_in_the_key_is_what_holds_the_lookalikes_out_6479(monkeypatch):
    """The counterfactual, run rather than asserted in prose.

    Swap `kxsb-` for the bare `kxsb` a reader of the map would naturally write,
    and count what changes sport. Nothing else in the file can prove the key is
    shaped the way it is ON PURPOSE.
    """
    swapped = {
        key: value
        for key, value in KALSHI_FUTURES_TICKER_TO_SPORT_KEY.items()
        if key != "kxsb-"
    }
    swapped["kxsb"] = NFL
    monkeypatch.setattr(
        sport_keys_module, "KALSHI_FUTURES_TICKER_TO_SPORT_KEY", swapped
    )

    mis_sported = [
        ticker
        for ticker, _subject in KXSB_LOOKALIKE_SERIES
        if sport_keys_module.get_sport_key_from_ticker(ticker) == NFL
    ]
    assert len(mis_sported) == len(KXSB_LOOKALIKE_SERIES), (
        "the bare prefix must reach ALL seven, or this file is guarding a "
        "hazard that no longer exists"
    )


def test_the_new_key_swallows_nothing_and_is_swallowed_by_nothing_6479():
    """The #6262 property, asked of this key.

    Both directions: a key that swallows a longer registered series silently
    re-sports it, and a key that IS swallowed never fires at all.
    """
    prefix = "kxsb-"
    assert prefix in KALSHI_FUTURES_TICKER_TO_SPORT_KEY
    for mapping in (KALSHI_TICKER_TO_SPORT_KEY, KALSHI_FUTURES_TICKER_TO_SPORT_KEY):
        assert [k for k in mapping if prefix.startswith(k) and k != prefix] == []
        assert [k for k in mapping if k.startswith(prefix) and k != prefix] == []


def test_the_new_key_moves_no_anchor_and_makes_nothing_game_level_6479():
    """It buys a NAMESPACE, not a classification.

    The anchor channel must still record the Super Bowl board as a `market`.
    A futures board anchored as a `game` can absorb one of its own fixtures
    (CERT-409), which is a matching defect and would be a far larger thing than
    the display repair this key exists for.
    """
    from app.utils.provider_anchor_keys import kalshi_anchor_key

    for ticker in ("KXSB-27", "KXSB-27-LAR"):
        assert is_kalshi_game_level_ticker(ticker) is False
        assert is_kalshi_shadowed_futures_ticker(ticker) is False
        anchor = kalshi_anchor_key(ticker=ticker)
        assert anchor is not None
        assert anchor.id_kind == "market", ticker
        assert anchor.source_id == ticker


def test_the_board_ticker_still_defeats_the_game_pair_parser_6479():
    """#6447's recorded answer is unchanged, and that is the whole reason this
    ship exists as a separate parse rather than a widening of that one.

    `KXSB-27` carries no pair. Registering its sport must not accidentally make
    the pair parser start guessing at a board.
    """
    assert repair_truncated_names(
        "KXSB-27", ["Los Angeles R", "Buffalo", "Baltimore"]
    ) == {}
