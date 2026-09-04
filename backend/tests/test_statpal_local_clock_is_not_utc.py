"""CERT-842 follow-up (AUTHORITY-001-ISOLATE-SHARED-LIVE-PARSER): the fence.

## what was asked, and why the answer is the other option

CERT-842 granted authority/001 GREEN with a named follow-up, due before NFL
live play:

    the shared `contestid`/`datetime_utc` fallbacks are reachable from the
    existing live-score writer; isolate them to the dark parser or explicitly
    guard/document that adjacent path

The premise is right — they ARE reachable, `get_live_scores` -> `_parse_fixtures`
-> `_parse_single_fixture` — and the concern is right too: a dark lane that can
move a live write is not dark. But the direction is the opposite of the worry.
**Measured against production on 2026-09-03, both fallbacks are the only thing
keeping the live path correct**, and isolating them would ship a regression.

## the measurement

StatPal's `date` + `time` pair is UTC on some endpoints and VENUE-LOCAL on
others, for the SAME sport, with nothing in the pair to say which:

    /v1/mlb/season-schedule   time=16:35              no tz, no datetime_utc
    /v1/mlb/livescores        time=12:35  tz="ET"     datetime_utc=16:35
    /v1/nfl/livescores        time="6:00 PM" tz="EST" datetime_utc=23:00

Same provider, same sport, same game — Giants v Pirates on 2026-09-03 is 16:35
on `season-schedule` and 12:35 on `livescores`. **9 of 9 live MLB games and 16
of 16 live NFL games disagree with their own `datetime_utc`, each by exactly the
UTC offset.**

And `livescores` NFL carries **`contestid` on 16/16 games and `id` on 0/16** —
the same id space as the season schedule, which the capabilities doc records as
untested until 9/10 kickoff. It is tested now.

## so what isolating would actually do

Two live regressions, one of them silent:

1. **Live MLB commence_time four hours early.** Worse than a wrong number:
   `sync_statpal_schedules` pairs a live row to a scheduled row with
   `pair_verdict(fixture.start_time, live_data.start_time)` (#1945). A live row
   read four hours off does not pair, so the **live score never reaches the
   event at all** — and nothing logs a failure, because refusing to pair is the
   guard working as designed.
2. **Every live NFL fixture with a blank `fixture_id`** from 9/10 — the exact
   shape that produced 8,272 unusable rows
   (`backend/scripts/repair_statpal_fixture_id_blanks.py`).

## what this file is

The fence CERT-842's second option asks for, executable rather than a comment.
Every test below asserts the **live ingestion path** — `_parse_fixtures`, what
`get_live_scores` and `sync_statpal_schedules` actually call — still reaches
both fallbacks. They fail if someone isolates them, which is the whole point:
the follow-up's first option is a regression and the next reader should be
stopped by a red test rather than by finding this docstring.

Both directions are pinned (gotcha #43): the local-clock arm proves the value
used is the UTC one and NOT the local one, so a test that merely read "some
datetime came back" cannot pass for the wrong reason.
"""
import json
import logging
from pathlib import Path

import pytest

from app.services.statpal_api import StatPalAPIService

FIXTURES = Path(__file__).parent / "fixtures"
MLB_LIVE = FIXTURES / "statpal_mlb_livescores_20260903.json"
NFL_LIVE = FIXTURES / "statpal_nfl_livescores_20260903.json"


@pytest.fixture
def service():
    return StatPalAPIService(api_key="test-key-not-a-real-key")


@pytest.fixture
def mlb_live():
    return json.loads(MLB_LIVE.read_text())


@pytest.fixture
def nfl_live():
    return json.loads(NFL_LIVE.read_text())


def _matches(payload) -> list[dict]:
    tournament = payload["livescores"]["tournament"]
    if isinstance(tournament, dict):
        tournament = [tournament]
    return [m for t in tournament for m in t.get("match", [])]


# =============================================================================
# The pinned payloads really do carry a local clock
# =============================================================================

class TestTheFixturesShowTheConventionSplit:
    """Without this, every assertion below could pass on a payload where the
    local and UTC readings happen to coincide, and prove nothing."""

    @pytest.mark.parametrize("sport", ["mlb", "nfl"])
    def test_every_pinned_game_disagrees_with_its_own_datetime_utc(
        self, sport, mlb_live, nfl_live
    ):
        payload = mlb_live if sport == "mlb" else nfl_live
        games = _matches(payload)
        assert games, "the pinned payload has games"
        for g in games:
            pair = f"{g.get('date', '')} {g.get('time', '')}".strip()
            assert g["datetime_utc"] != pair, (
                f"{sport}: {pair!r} equals its datetime_utc, so this game cannot "
                "tell a UTC reading from a local one"
            )

    @pytest.mark.parametrize("sport", ["mlb", "nfl"])
    def test_the_local_clock_announces_itself_with_a_timezone(
        self, sport, mlb_live, nfl_live
    ):
        payload = mlb_live if sport == "mlb" else nfl_live
        assert all(g.get("timezone") for g in _matches(payload)), (
            "`timezone` beside `date`/`time` is the tell that the pair is "
            "venue-local; the warning branch keys on it"
        )

    def test_live_nfl_has_no_id_only_a_contestid(self, nfl_live):
        games = _matches(nfl_live)
        assert all(not g.get("id") for g in games)
        assert all(g.get("contestid") for g in games)


# =============================================================================
# The fence: the LIVE ingestion path still reaches both fallbacks
# =============================================================================

class TestTheLivePathKeepsReach:

    def test_live_mlb_start_times_are_the_utc_reading_not_the_local_one(
        self, service, mlb_live
    ):
        """`_parse_fixtures` is what `get_live_scores` calls. If a later change
        isolates `datetime_utc` to the authority parser, every live MLB game
        lands four hours early and stops pairing with its scheduled row."""
        fixtures = service._parse_fixtures(mlb_live, "mlb")
        games = _matches(mlb_live)
        assert len(fixtures) == len(games)

        for f, raw in zip(fixtures, games):
            utc = raw["datetime_utc"]  # "03.09.2026 16:35"
            local = f"{raw['date']} {raw['time']}"  # "3.09.2026 12:35"
            assert f.start_time.strftime("%d.%m.%Y %H:%M") == utc
            # ...and explicitly NOT the local clock, so this cannot pass by
            # accident on a payload where the two coincide.
            assert f.start_time.strftime("%-d.%m.%Y %H:%M") != local

    def test_live_nfl_start_times_are_the_utc_reading(self, service, nfl_live):
        """NFL's pair is worse than shifted — `time` is "6:00 PM", which does
        not parse at all. Without `datetime_utc` these have no start time."""
        fixtures = service._parse_fixtures(nfl_live, "nfl")
        games = _matches(nfl_live)
        assert all(f.start_time for f in fixtures), "none may be left timeless"
        for f, raw in zip(fixtures, games):
            assert f.start_time.strftime("%d.%m.%Y %H:%M") == raw["datetime_utc"]

    def test_live_nfl_fixtures_are_anchorable_by_contestid(self, service, nfl_live):
        """The other half of the follow-up. Isolate this and every live NFL
        fixture carries '' from 9/10 — 8,272 rows once did."""
        fixtures = service._parse_fixtures(nfl_live, "nfl")
        games = _matches(nfl_live)
        assert all(f.fixture_id for f in fixtures)
        assert [f.fixture_id for f in fixtures] == [g["contestid"] for g in games]

    def test_live_mlb_still_prefers_its_own_id_over_a_contestid(
        self, service, mlb_live
    ):
        """The fallback is a fallback. MLB livescores serves `id`, and that is
        what must be used — a fallback that overtakes the primary key would
        re-key every live MLB row into a different id space."""
        fixtures = service._parse_fixtures(mlb_live, "mlb")
        games = _matches(mlb_live)
        assert [f.fixture_id for f in fixtures] == [g["id"] for g in games]


# =============================================================================
# The remaining hole, made loud instead of silent
# =============================================================================

class TestALocalClockWithNoConversionIsAnnounced:

    def _item(self, **over):
        item = {
            "id": "999",
            "date": "03.09.2026",
            "time": "12:35",
            "status": "Not Started",
            "home": {"id": "1", "name": "Pirates"},
            "away": {"id": "2", "name": "Giants"},
        }
        item.update(over)
        return item

    def test_a_timezone_with_no_datetime_utc_warns(self, service, caplog):
        """The shape nothing can fix at read time: the pair is declared local
        and the field that would convert it is absent. It is still parsed —
        refusing would drop the game — but it is no longer silent."""
        with caplog.at_level(logging.WARNING):
            f = service._parse_single_fixture(self._item(timezone="ET"))
        assert f.start_time is not None, "the game is not dropped"
        assert "venue-local clock as UTC" in caplog.text
        assert "'ET'" in caplog.text

    def test_no_timezone_means_the_pair_is_utc_and_says_nothing(
        self, service, caplog
    ):
        """The control, and the common case. `season-schedule` carries neither
        `timezone` nor `datetime_utc` and its pair IS UTC (MLB's 16:35 matches
        livescores' datetime_utc to the minute). A warning here would fire on
        every scheduled game in the system."""
        with caplog.at_level(logging.WARNING):
            f = service._parse_single_fixture(self._item())
        assert f.start_time.strftime("%H:%M") == "12:35"
        assert "venue-local" not in caplog.text

    def test_a_timezone_alongside_datetime_utc_says_nothing(self, service, caplog):
        """The other control: the live endpoints declare a timezone AND ship the
        conversion, so they are handled, not merely detected. If this warned,
        every live game on every sport would log one every two minutes."""
        with caplog.at_level(logging.WARNING):
            f = service._parse_single_fixture(
                self._item(timezone="ET", datetime_utc="03.09.2026 16:35")
            )
        assert f.start_time.strftime("%H:%M") == "16:35"
        assert "venue-local" not in caplog.text
