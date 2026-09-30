"""#9193 — /politics files a primary by the office it names, a midterm question
under Congressional, and a Russia question under International.

THE READER'S VIEW (bainluck.com/politics at 390px, 2026-09-27 ~19:15Z): the
first Related Market under the 2028 presidential nominee race was "Texas Senate
primary: which counties will Paxton win?", and "How many House seats will
Independents win in the Midterms?" sat in Other while its Senate twin sat under
Congressional.

THE CAUSE: three word gaps in `_THEME_BY_NAME`. `primary` sat in the presidential
arm ahead of the congressional and governor arms; the congressional arm matched
`\\bmidterm\\b`, which the plural every venue writes fails; the international arm
had no Russia entry. Widening `midterm` alone would have filed the governor-count
questions ("…governorships after the midterms?") under Congressional, so the
governor arm reads the plural too and is tried first.

Every name below is a real open market read from production 2026-09-27. The
tickers are real too, and none of them starts with a `_THEME_BY_TICKER*` prefix,
so the theme comes from the NAME — `test_no_specimen_is_decided_by_its_ticker`
keeps it that way.
"""

from types import SimpleNamespace

import pytest

from app.routes.politics import (
    _THEME_BY_TICKER,
    _THEME_BY_TICKER_CLASSIFY_ONLY,
    _classify_theme,
    _find_chamber_control,
)


def _market(external_id: str, name: str):
    return SimpleNamespace(external_id=external_id, name=name)


_SENATE_PRIMARIES = [
    ("KXPAXTONPRIMARYCOUNTIES-26", "Texas Senate primary: which counties will Paxton win?"),
    ("KXTXSENRPRIMARYMOV-26MAR03", "Texas Senate Republican primary margin of victory?"),
    ("KXVOTEPERCENTCOOPERNC-26MAR03", "North Carolina Democratic Senate primary: Roy Cooper vote percent?"),
    ("KXPRIMARYTURNOUT-SENATETXR26", "Texas Republican Senate primary runoff: voter turnout"),
]

_GOVERNOR_PRIMARIES = [
    ("KXABBOTTGOPVOTE-26MAR03", "Texas GOP Governor primary: Greg Abbott vote percent?"),
    ("KXSDRGOVADVANCE-26JUN03", "Who will advance in the South Dakota Republican Governor primary?"),
]

_MIDTERMS = [
    ("KXIHOUSEWON-26NOV03", "How many House seats will Independents win in the Midterms?"),
    ("KXRHOUSESEATS-27", "How many House seats will Republicans hold after the Midterms?"),
    ("KXEXITPOLL-IND", "Midterms: which party wins independents?"),
]

_GOVERNOR_COUNTS = [
    # Plural governor words, beside a midterms word the governor arm must beat.
    ("872267", "Which party will hold more governorships after the midterms?"),
    ("KXRGOVCOUNT-26JUL08", "Number of Republican governors after the midterms?"),
]

_RUSSIA = [
    ("31195", "Putin out as President of Russia by...?"),
    ("166793", "Will Russia invade another country in 2026?"),
    ("KXPUTINZELMEET-29JAN01", "When will Putin and Zelenskyy meet?"),
]

# Controls: what the fix must NOT move.
_STILL_PRESIDENTIAL = [
    # A primary that names no chamber or office still falls through to presidential.
    ("KXDPRESPRIMARY-28SC", "2028 South Carolina Democratic primary winner?"),
    ("30829", "Democratic Presidential Nominee 2028"),
]
_STILL_CONGRESSIONAL = [
    # The Senate twin that was already right.
    ("KXISENATEWON-26NOV03", "How many Senate seats will Independents win in the Midterms?"),
]


@pytest.mark.parametrize("external_id, name", _SENATE_PRIMARIES)
def test_a_senate_primary_is_congressional(external_id, name):
    assert _classify_theme(_market(external_id, name)) == "congressional"


@pytest.mark.parametrize("external_id, name", _GOVERNOR_PRIMARIES)
def test_a_governor_primary_is_gubernatorial(external_id, name):
    assert _classify_theme(_market(external_id, name)) == "gubernatorial"


@pytest.mark.parametrize("external_id, name", _MIDTERMS)
def test_the_plural_midterms_is_congressional(external_id, name):
    assert _classify_theme(_market(external_id, name)) == "congressional"


@pytest.mark.parametrize("external_id, name", _GOVERNOR_COUNTS)
def test_a_governor_count_after_the_midterms_is_gubernatorial(external_id, name):
    assert _classify_theme(_market(external_id, name)) == "gubernatorial"


@pytest.mark.parametrize("external_id, name", _RUSSIA)
def test_a_russia_question_is_international(external_id, name):
    assert _classify_theme(_market(external_id, name)) == "international"


@pytest.mark.parametrize("external_id, name", _STILL_PRESIDENTIAL)
def test_a_bare_primary_and_the_nominee_race_stay_presidential(external_id, name):
    assert _classify_theme(_market(external_id, name)) == "presidential"


@pytest.mark.parametrize("external_id, name", _STILL_CONGRESSIONAL)
def test_the_senate_twin_stays_congressional(external_id, name):
    assert _classify_theme(_market(external_id, name)) == "congressional"


def test_no_specimen_is_decided_by_its_ticker():
    """If a future ticker prefix claimed one of these, the name-rule assertions
    above would pass for the wrong reason."""
    prefixes = [p for p, _ in (*_THEME_BY_TICKER, *_THEME_BY_TICKER_CLASSIFY_ONLY)]
    everything = (
        _SENATE_PRIMARIES + _GOVERNOR_PRIMARIES + _MIDTERMS + _GOVERNOR_COUNTS + _RUSSIA
        + _STILL_PRESIDENTIAL + _STILL_CONGRESSIONAL
    )
    claimed = [e for e, _ in everything if any(e.lower().startswith(p) for p in prefixes)]
    assert claimed == []


def test_a_lose_the_majority_question_now_congressional_cannot_become_the_house_card():
    """The midterms widening moves "Will Republicans lose the House majority
    before the midterms?" from Other into the Congressional pool that
    `_find_chamber_control` searches, and its name matches `_HOUSE_CONTROL_RE`
    ("house majority"). Read as a control market, its `Yes` would be printed as
    the Republicans' chance of HOLDING the House. Both production rows are
    refused structurally (stored 2026-09-27: `mutually_exclusive = false`, one
    `Yes` leg), so the House card stays `CONTROLH-2026`."""
    def _mk(id_, external_id, name, outcomes, exclusive):
        return SimpleNamespace(
            id=id_, external_id=external_id, name=name, source="kalshi",
            mutually_exclusive=exclusive,
            outcomes=[SimpleNamespace(name=n, current_probability=p) for n, p in outcomes],
        )

    house = _mk(108621, "CONTROLH-2026", "Which party will win the U.S. House?",
                [("Democratic Party", 0.9165), ("Republican Party", 0.0845)], True)
    lose_k = _mk(108677, "KXLOSEMAJORITY-27JAN01",
                 "Will Republicans lose the House majority before the midterms?",
                 [("Yes", 0.0475)], False)
    lose_p = _mk(114418, "162201", "Will Republicans lose House majority before the midterms?",
                 [("Yes", 0.013)], False)
    pool = [house, lose_k, lose_p]
    assert all(_classify_theme(m) == "congressional" for m in pool)

    assert _find_chamber_control(pool)["house"]["market_id"] == 108621
