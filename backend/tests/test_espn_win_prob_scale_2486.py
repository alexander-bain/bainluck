"""#2486 — ESPN's win-probability history is read in ESPN's unit, not 1/100 of it.

WHAT A READER SEES TODAY. Open any completed game whose ESPN line was backfilled
— `https://bainluck.com/events/15305465/models` is the worked specimen — and the
ESPN series is a flat line pinned to the floor of the chart while the other three
sources run across the middle of it. 118,824 rows across 989 events, 118,821 of
them (99.998%) below 2%, and ~524 more arriving every day as the backfill beat
runs at 06/12/18/00 UTC.

THE WHOLE DEFECT IS A UNIT. `ESPNAPIService.get_win_probability` read the
`/summary` `winprobability` array and did::

    "home_win_probability": point.get("homeWinPercentage", 0) / 100,

That array is a FRACTION. The scoreboard's `situation.lastPlay.probability` —
the other reader of the same field name, on a different ESPN surface — is a
PERCENTAGE, and its caller has always divided conditionally. One field name, two
units, and the summary path picked the wrong one.

THE FIXTURES ARE ESPN'S OWN NUMBERS, NOT THE AUTHOR'S. The unit IS the question
under test, so a hand-written fixture would be this file asserting its own
answer. `tests/fixtures/espn_winprobability_2486.json` is two complete
`winprobability` arrays captured verbatim from ESPN on 2026-09-16:

  * MLB 401816947, Dodgers @ Reds, 70 points, 0.0 → 0.402. Carries a genuine
    **0.0** (the home side lost) and never crosses 0.5 — a series that is
    honestly low for its whole length.
  * NFL 401872923, Saints @ Lions, 226 points, 0.3793 → **1.0**. Carries a
    genuine **1.0** (the home side won), the boundary a `> 1.0` test must not
    divide.

Between them they are the zero, the one and the genuine-low control the fix has
to survive, taken from the wire rather than invented.

THE RED-FIRST ARM is `test_the_served_series_is_espns_own_numbers_2486`: on
master it fails on the first point (0.271 served as 0.00271), and it fails
because the behaviour is wrong, not because a helper is missing.

WHAT THIS FILE DOES NOT COVER. The 118,824 rows already in the table — a writer
fix does not retract what it wrote (gotcha: "stopping a writer is not
withdrawing what it already wrote"). That is the repair half of #2486 and it is
attended, never run by a lane.
"""

import json
import math
import pathlib

import pytest

from app.services.espn_api import ESPNAPIService, _normalize_win_percentage

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
CAPTURE = json.loads((FIXTURES / "espn_winprobability_2486.json").read_text())
MLB = CAPTURE["series"]["mlb"]
NFL = CAPTURE["series"]["nfl"]


@pytest.fixture
def client():
    return ESPNAPIService()


# `_get` is monkeypatched wholesale below: the question under test is what the
# parser does with ESPN's payload, and routing it through httpx would test httpx.

# ── The unit, decided in one place ─────────────────────────────────────


class TestNormalizeWinPercentage:
    """`_normalize_win_percentage` is the only thing that knows ESPN's unit."""

    @pytest.mark.parametrize(
        "value",
        [0.499, 0.5853, 0.137, 0.271, 0.402, 0.3793, 0.0066],
    )
    def test_a_fraction_is_already_a_probability(self, value):
        """MLB 0.499, NFL 0.5853, NBA 0.137 — probed values, passed through.

        0.0066 is the genuine-low control and the reason a blanket ×100 of the
        STORED rows is the wrong repair: ESPN really does report sub-1% for the
        wrong end of a blowout, and that is a number, not a corruption.
        """
        assert _normalize_win_percentage(value) == value

    def test_zero_is_a_reading_and_survives_as_zero(self):
        """0.0 is "this side cannot win any more", not a missing value."""
        assert _normalize_win_percentage(0.0) == 0.0
        assert _normalize_win_percentage(0) == 0.0

    def test_one_is_the_boundary_and_is_never_divided(self):
        """1.0 is certainty. `> 1.0` (not `>= 1.0`) is what keeps it.

        Mutating the comparison to `>=` turns every won game's last point into
        1%, which is the original defect wearing a smaller coat.
        """
        assert _normalize_win_percentage(1.0) == 1.0
        assert _normalize_win_percentage(1) == 1.0

    @pytest.mark.parametrize(
        "value,expected",
        [(83.1, 0.831), (42.0, 0.42), (100, 1.0), (99.99, 0.9999)],
    )
    def test_a_percentage_is_divided(self, value, expected):
        """The scoreboard surface still speaks percentages; it keeps working."""
        assert _normalize_win_percentage(value) == pytest.approx(expected)

    @pytest.mark.parametrize(
        "value",
        [None, "", "abc", [], {}, -0.1, -50, 150, 1000, float("nan"), float("inf")],
    )
    def test_what_cannot_be_a_probability_is_no_reading_at_all(self, value):
        """`None` means NO READING, and both callers drop the point.

        The alternative — storing 1.5, or -0.1, or the 0.0 that a missing key
        used to default to — puts a number on the chart that no source ever
        said (gotcha #53: an unparseable answer is not an answer).
        """
        assert _normalize_win_percentage(value) is None

    def test_a_string_that_is_a_number_is_still_read(self):
        """ESPN occasionally quotes numerics; that is a format, not a refusal."""
        assert _normalize_win_percentage("0.5853") == 0.5853
        assert _normalize_win_percentage("83.1") == pytest.approx(0.831)


# ── The behaviour, through the method the backfill actually calls ──────


class TestServedSeries:
    async def _call(self, client, monkeypatch, payload, sport_key="baseball_mlb"):
        async def _fake_get(url):
            assert "summary?event=" in url
            return payload

        monkeypatch.setattr(client, "_get", _fake_get)
        return await client.get_win_probability(sport_key, "401816947")

    async def test_the_served_series_is_espns_own_numbers_2486(
        self, client, monkeypatch
    ):
        """🔴 THE RED-FIRST ARM. Point for point, what ESPN published.

        On master every one of these 70 assertions fails low by exactly 100×.
        """
        payload = {"winprobability": MLB["winprobability"]}
        series = await self._call(client, monkeypatch, payload)

        assert len(series) == MLB["points"] == 70
        for point, raw in zip(series, MLB["winprobability"]):
            assert point["home_win_probability"] == raw["homeWinPercentage"]

    async def test_the_nfl_series_keeps_its_certainty_and_its_spread(
        self, client, monkeypatch
    ):
        """0.3793 → 1.0, a series that spans the boundary in both directions."""
        payload = {"winprobability": NFL["winprobability"]}
        series = await self._call(client, monkeypatch, payload, "americanfootball_nfl")

        values = [p["home_win_probability"] for p in series]
        assert len(values) == NFL["points"] == 226
        assert min(values) == NFL["min"] == 0.3793
        assert max(values) == NFL["max"] == 1.0

    async def test_the_line_is_not_glued_to_the_floor(self, client, monkeypatch):
        """The defect's own signature, asserted as an outcome rather than a value.

        #2486's census is "118,821 of 118,824 rows below 2%". That is what a
        reader sees as a flat line on the axis floor, so the shape of the served
        series is the thing to pin: on master 70/70 MLB points and 226/226 NFL
        points land under 0.02, and on this fix 3/70 and 0/226 do — the three
        being ESPN's own late-game zeroes.
        """
        for series_fixture, sport in ((MLB, "baseball_mlb"), (NFL, "americanfootball_nfl")):
            payload = {"winprobability": series_fixture["winprobability"]}
            served = await self._call(client, monkeypatch, payload, sport)
            values = [p["home_win_probability"] for p in served]
            under_2pct = sum(1 for v in values if v < 0.02)

            assert under_2pct < len(values) * 0.5, (
                f"{sport}: {under_2pct}/{len(values)} points below 2% — that is "
                f"the 1/100 signature, not a chart"
            )
            assert max(values) > 0.02

    async def test_a_missing_percentage_is_no_reading_not_zero_percent(
        self, client, monkeypatch
    ):
        """The `, 0` default used to write "the home team cannot win".

        `point.get("homeWinPercentage", 0) / 100` turned a point ESPN published
        WITHOUT a probability into a stored 0.0 — indistinguishable on the chart
        from a genuine 0.0 at the end of a blowout. It is now `None`, and
        `_backfill_espn_win_probability` skips a `None` point (`if home_wp is
        None: continue`) rather than storing it.
        """
        payload = {
            "winprobability": [
                {"playId": "a", "homeWinPercentage": 0.62},
                {"playId": "b"},  # ESPN published no probability for this play
                {"playId": "c", "homeWinPercentage": None},
                {"playId": "d", "homeWinPercentage": 0.0},  # genuine zero
            ]
        }
        series = await self._call(client, monkeypatch, payload)

        assert [p["home_win_probability"] for p in series] == [0.62, None, None, 0.0]

    async def test_seconds_left_and_play_id_still_ride_along(
        self, client, monkeypatch
    ):
        """The backfill stamps `game_state.seconds_left` from this field."""
        payload = {
            "winprobability": [
                {"playId": "p1", "secondsLeft": 1800, "homeWinPercentage": 0.55}
            ]
        }
        series = await self._call(client, monkeypatch, payload)

        assert series == [
            {"play_id": "p1", "seconds_left": 1800, "home_win_probability": 0.55}
        ]

    async def test_an_empty_array_is_still_none_not_an_empty_series(
        self, client, monkeypatch
    ):
        """Unchanged, and load-bearing: `None` is what the caller counts as
        `api_empty`, and `[]` would be written as "this game has no points"."""
        assert await self._call(client, monkeypatch, {"winprobability": []}) is None
        assert await self._call(client, monkeypatch, {}) is None


# ── The other reader of the same field name ────────────────────────────


class TestScoreboardPathUnchanged:
    """The percentage surface keeps behaving exactly as it did.

    `_parse_event` reads `situation.lastPlay.probability.homeWinPercentage`,
    which ESPN serves as a percentage, and it has always divided conditionally.
    Routing it through the shared helper must not move it.
    """

    def _event(self, prob, with_situation=True):
        competition = {
            "competitors": [
                {"homeAway": "home", "score": "50",
                 "team": {"id": "1", "displayName": "Home", "abbreviation": "HOM"}},
                {"homeAway": "away", "score": "48",
                 "team": {"id": "2", "displayName": "Away", "abbreviation": "AWY"}},
            ],
        }
        if with_situation:
            competition["situation"] = {
                "lastPlay": {"probability": {"homeWinPercentage": prob}}
            }
        return {
            "id": "401584700",
            "name": "Away at Home",
            "shortName": "AWY @ HOM",
            "date": "2026-02-15T00:30Z",
            "status": {"type": {"name": "STATUS_IN_PROGRESS", "detail": "Q3 4:32"}},
            "competitions": [competition],
        }

    def test_a_scoreboard_percentage_is_still_divided(self, client):
        event = client._parse_event(self._event(83.1))
        assert event.home_win_probability == pytest.approx(0.831)

    def test_a_scoreboard_fraction_is_still_passed_through(self, client):
        """The existing `test_live_event_win_probability` case (0.42), pinned
        here too because this is the file that owns the unit."""
        event = client._parse_event(self._event(0.42))
        assert event.home_win_probability == 0.42

    def test_a_scoreboard_nonsense_value_is_dropped(self, client):
        """New, and deliberate: 150% is not a probability and is no longer
        stored as 1.5. `None` leaves the event's previous reading alone."""
        event = client._parse_event(self._event(150))
        assert event.home_win_probability is None

    def test_no_situation_is_still_no_probability(self, client):
        event = client._parse_event(self._event(0.42, with_situation=False))
        assert event.home_win_probability is None


# ── The fixture is what it claims to be ────────────────────────────────


class TestTheCaptureIsAuthentic:
    """A fixture that drifted into hand-written numbers stops being evidence."""

    def test_both_series_are_whole_and_in_range(self):
        for key in ("mlb", "nfl"):
            series = CAPTURE["series"][key]["winprobability"]
            assert len(series) == CAPTURE["series"][key]["points"]
            values = [p["homeWinPercentage"] for p in series]
            assert all(isinstance(v, (int, float)) for v in values)
            assert all(0.0 <= v <= 1.0 for v in values), (
                f"{key}: a captured value outside [0,1] would mean ESPN changed "
                f"unit on this array, which is the premise of the whole fix"
            )
            assert not any(math.isnan(v) for v in values)

    def test_the_controls_the_docstring_claims_are_actually_present(self):
        """Zero, one and genuine-low, from the wire and not from the author."""
        mlb = [p["homeWinPercentage"] for p in MLB["winprobability"]]
        nfl = [p["homeWinPercentage"] for p in NFL["winprobability"]]
        assert 0.0 in mlb                      # the zero control
        assert 1.0 in nfl                      # the one control
        assert any(0.0 < v < 0.05 for v in mlb)  # the genuine-low control
        assert max(mlb) < 0.5 < max(nfl)       # one low series, one high

    def test_provenance_is_recorded(self):
        prov = CAPTURE["_provenance"]
        assert prov["issue"] == 2486
        assert "summary?event=" in prov["how"]
        assert prov["captured_at_utc"].startswith("2026-")
