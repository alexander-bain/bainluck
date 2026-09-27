"""#9199 — the /politics Senate map colours each state by its own Senate race.

THE READER'S VIEW (production, /politics at 390px, 2026-09-27 ~19:56Z): the
"Senate races by state" map painted Illinois R-likely (1.0% D) while the
Illinois seat is Stratton (D) 98%, painted Mississippi D-likely (89.7%) while
Hyde-Smith (R) is 91%, painted Maryland 7% D off "Maryland State Senate
District 2 winner?", coloured 14 states that have no 2026 race off their
"(2028)" seats, and left Rhode Island, Delaware, New Mexico and West Virginia —
all on the 2026 ballot — grey.

THE CAUSE, three parts: (1) `_build_senate_map` kept the FIRST congressional
market whose name contained a state, in heap order; (2) `_extract_dem_prob`
fell back to `_detect_party`'s substring surname allowlists ("Barry Moore", R,
reads D off "moore"); (3) the `is_resolved` price test dropped any seat with a
leg at 99%.

Counterfactual over all 622 open senate-named politics markets on 2026-09-27:
46 states → 35, exactly the 35 seats up in 2026.

WHAT WOULD MAKE THIS FILE VACUOUS: a builder that returns `{}` passes every
"is not on the map" assertion. `TestTheRealSeatStillPaints` is the control —
every specimen state must still appear, with its seat market's number.
"""

import random
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.routes.politics import _build_senate_map, _senate_seat


def _o(name, p):
    return SimpleNamespace(name=name, current_probability=p)


def _m(name, outcomes, external_id="", resolution=None):
    return SimpleNamespace(
        name=name,
        external_id=external_id,
        resolution_date=resolution,
        outcomes=[_o(n, p) for n, p in outcomes],
    )


_JAN_2027 = datetime(2027, 1, 4, 15, tzinfo=timezone.utc)
_NOV_2026 = datetime(2026, 11, 3, tzinfo=timezone.utc)
_JAN_2029 = datetime(2029, 1, 4, 15, tzinfo=timezone.utc)

# Production rows, 2026-09-27 (names, tickers and prices as stored).
IL_SEAT_POLY = _m(
    "Illinois Senate Election Winner",
    [("Juliana Stratton (D)", 0.979), ("Don Tracy (R)", 0.024)],
    "57646",
    _NOV_2026,
)
IL_2028 = _m(
    "Illinois Senate winner? (2028)",
    [("Democratic party", 0.945), ("Republican party", 0.055)],
    "SENATEIL-28",
    _JAN_2029,
)
MS_SEAT_POLY = _m(
    "Mississippi Senate Election Winner",
    [("Cindy Hyde-Smith (R)", 0.915), ("Scott Colom (D)", 0.085)],
    "57678",
    _NOV_2026,
)
# Kalshi names candidates without a party: "scott" is on the R allowlist.
MS_SEAT_KALSHI = _m(
    "Mississippi Senate winner?",
    [("Cindy Hyde-Smith", 0.904), ("Scott Colom", 0.103)],
    "SENATEMS-26",
    _JAN_2027,
)
# "moore" is on the D allowlist; Barry Moore is the Alabama Republican.
AL_SEAT_KALSHI = _m(
    "Alabama Senate winner?",
    [("Barry Moore", 0.971), ("Everett Wess", 0.038)],
    "SENATEAL-26",
    _JAN_2027,
)
AL_SEAT_POLY = _m(
    "Alabama Senate Election Winner",
    [("Barry Moore (R)", 0.966), ("Everett Wess (D)", 0.022)],
    "57637",
    _NOV_2026,
)
MD_STATE_LEG = _m(
    "Maryland State Senate District 2 winner?",
    [("Paul Corderman (R)", 0.93), ("Eric Van Buren", 0.03)],
    "KXMDSD2-26",
    _JAN_2027,
)
MD_2028 = _m(
    "Maryland Senate winner? (2028)",
    [("Democratic party", 0.918), ("Republican party", 0.088)],
    "SENATEMD-28",
    _JAN_2029,
)
WA_2028 = _m(
    "Washington Senate winner? (2028)",
    [("Democratic party", 0.938), ("Republican party", 0.055)],
    "SENATEWA-28",
    _JAN_2029,
)
AK_2028 = _m(
    "Alaska Senate winner? (2028)",
    [("Republican party", 0.745), ("Democratic party", 0.255)],
    "SENATEAK-28",
    _JAN_2029,
)
AK_SEAT_KALSHI = _m(
    "Alaska Senate winner?",
    [("Democratic party", 0.705), ("Republican party", 0.295)],
    "SENATEAK-26",
    _JAN_2027,
)
RI_SEAT_KALSHI = _m(
    "Rhode Island Senate winner?",
    [("Democratic party", 0.99), ("Republican party", 0.0105)],
    "SENATERI-26",
    _JAN_2027,
)
# Kalshi files Kentucky's 2026 seat under an LA ticker.
KY_SEAT_KALSHI = _m(
    "Kentucky Senate winner?",
    [("Andy Barr", 0.951), ("Charles Booker", 0.051)],
    "SENATELA-26",
    _JAN_2027,
)
TX_COUNTIES = _m(
    "Texas Senate primary: which counties will Paxton win?",
    [("Harris", 0.06), ("Denton", 0.035)],
    "KXPAXTONPRIMARYCOUNTIES-26",
    _JAN_2027,
)
TX_STATE_SENATE = _m(
    "Texas State Senate winner?",
    [("Republican party", 0.92), ("Democratic party", 0.09)],
    "KXSTATELEG-TXSENA26",
    _JAN_2027,
)
TX_COMBO = _m(
    "Maine-Texas Senate Combo",
    [("James Talarico and Troy Jackson", 0.455)],
    "KXMETXCOMBO-26NOV",
    _JAN_2027,
)
TX_SEAT_POLY = _m(
    "Texas Senate Election Winner",
    [("James Talarico (D)", 0.605), ("Ken Paxton (R)", 0.395)],
    "57672",
    _NOV_2026,
)

POOL = [
    IL_2028,
    IL_SEAT_POLY,
    MS_SEAT_KALSHI,
    MS_SEAT_POLY,
    AL_SEAT_KALSHI,
    AL_SEAT_POLY,
    MD_STATE_LEG,
    MD_2028,
    WA_2028,
    AK_2028,
    AK_SEAT_KALSHI,
    RI_SEAT_KALSHI,
    KY_SEAT_KALSHI,
    TX_COUNTIES,
    TX_STATE_SENATE,
    TX_COMBO,
    TX_SEAT_POLY,
]


class TestTheRealSeatStillPaints:
    """The control: every specimen's own 2026 seat is on the map, at its number."""

    def test_each_state_takes_its_seat_markets_number(self):
        got = _build_senate_map(POOL)
        assert got["IL"] == 97.9
        assert got["MS"] == 8.5
        assert got["AL"] == 2.2
        assert got["AK"] == 70.5
        assert got["TX"] == 60.5

    def test_a_ninety_nine_percent_seat_is_painted_not_dropped(self):
        assert _build_senate_map(POOL)["RI"] == 99.0

    def test_the_legacy_integration_shape_still_reads(self):
        m = _m(
            "Who wins Ohio Senate race 2026?",
            [("Tim Ryan (D)", 0.45), ("JD Vance (R)", 0.55)],
            "kxsenate26-oh",
        )
        assert _build_senate_map([m]) == {"OH": 45.0}


class TestOnlyTheSeatQuestionCounts:
    def test_a_state_legislature_seat_never_colours_the_state(self):
        assert "MD" not in _build_senate_map([MD_STATE_LEG, AK_SEAT_KALSHI])

    @pytest.mark.parametrize("m", [TX_COUNTIES, TX_STATE_SENATE, TX_COMBO])
    def test_county_state_senate_and_combo_questions_are_not_seats(self, m):
        assert _senate_seat(m) is None

    def test_the_state_comes_from_the_name_not_the_ticker(self):
        assert _senate_seat(KY_SEAT_KALSHI) == ("KY", 2026)


class TestOnlyTheNearestCycle:
    def test_a_2028_seat_leaves_the_map_while_2026_seats_exist(self):
        got = _build_senate_map(POOL)
        assert "WA" not in got and "MD" not in got

    def test_a_2028_seat_does_not_blend_into_the_2026_number(self):
        assert _build_senate_map([AK_2028, AK_SEAT_KALSHI]) == {"AK": 70.5}

    def test_once_the_near_cycle_is_gone_the_next_one_is_shown(self):
        assert _build_senate_map([WA_2028, MD_2028]) == {"MD": 91.8, "WA": 93.8}


class TestAPartyIsTakenOnlyFromTheVenuesWord:
    def test_an_allowlisted_surname_is_not_a_party(self):
        # Alone, the Kalshi rows name no party: no claim, no colour.
        assert _build_senate_map([AL_SEAT_KALSHI, MS_SEAT_KALSHI]) == {}

    def test_order_never_changes_the_map(self):
        want = _build_senate_map(POOL)
        rng = random.Random(9199)
        for _ in range(20):
            shuffled = POOL[:]
            rng.shuffle(shuffled)
            assert _build_senate_map(shuffled) == want
