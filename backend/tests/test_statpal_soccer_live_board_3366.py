"""#3366 / authority/061 — soccer's live board is readable, and half the
failover map stops being structurally dark.

WHAT WAS BROKEN, AND WHO IT COST. `STATPAL_SPORT_MAPPING` has fourteen keys and
SEVEN of them are soccer. `espn_sync._read_statpal_standby` — the function that
answers "could StatPal carry this sport if ESPN went dark?" — reads the live
half through `get_live_fixtures`, which asked `soccer/livescores`. On v2 that is
a 404, `_get` turns a 404 into None, and `_require_answer` turns None into a
`StatPalUpstreamError`. So for half the map the live half of readiness could
never be anything but DARK, on every pass, forever. That is the lane's own ship
("nothing goes blank when ESPN does") failing closed on the largest sport we
carry.

WHAT THE VENUE ACTUALLY SERVES, measured 2026-09-07 (notice 26a — against the
venue's own API by spec enumeration plus a live probe, never from our tables):

    live probe with the production key, 04:22Z
        v1/soccer/livescores       200  150,595 B
        v2/soccer/livescores       404      179 B
        v1/soccer/matches/daily    404      179 B
        v2/soccer/matches/daily    200  161,653 B

    statpal.io/static/openapi/openapi-compiled.yaml (04:24Z, 16 soccer paths)
        publishes /soccer/matches/live beside /soccer/matches/daily

    live probe, 04:25Z
        v1/soccer/matches/live     404      179 B
        v2/soccer/matches/live     200  188,954 B   113 leagues, 195 matches

#3366 read the first table as a VERSION defect and proposed crossing the
versions. The second table says otherwise, and the working sibling in the same
file said it first: on v2 the injury path is not `injuries` either, it is
`injuries-suspensions` (#2907). Soccer's live board is `matches/live`. Crossing
the versions would have bought the same games under a FIFTH id vocabulary
(v1 serves `id`/`alternate_id`/`alternate_id_2`/`static_id` for what v2 calls
`main_id`/`fallback_id_1..3`, which `StatPalInjury` already names) on the
endpoint the vendor's own spec files under "Legacy".

WHY THE INGESTION DOOR STAYS SHUT. `_extract_match_items` already reaches this
envelope, so pointing `get_live_scores` at it would hand `sync_statpal_schedules`
195 rows across 113 leagues on the next beat — and hand them over WRONG, which
is measured, not feared: soccer scores live under `home.goals` (all 195 rows
parse scoreless through the shared parser) and an unplayed match carries its
KICKOFF CLOCK in `status`. Both controls are asserted below, so this file fails
if either defect is ever "fixed" into the shared parser by accident.

THE FIXTURE. `statpal_soccer_matches_live_20260907.json` is a two-league slice
of the 04:25Z board, chosen to carry every shape that matters: a finished match
with events, an unplayed match whose `goals` is the literal `"?"` and whose
status is its own kickoff clock, a row whose `main_id` is BLANK (7 of the 195
were), and a league that serves its single `match` as a bare dict.
"""
import json
from pathlib import Path

import httpx
import pytest

from app.services.statpal_api import (
    LIVE_SCORE_ENDPOINTS,
    LIVESCORES_INGESTION_DARK_SPORTS,
    StatPalAPIService,
    StatPalUpstreamError,
    _normalize_status,
)
from app.utils.sport_keys import STATPAL_SPORT_MAPPING

BOARD = Path(__file__).parent / "fixtures" / "statpal_soccer_matches_live_20260907.json"

#: Measured over the whole 04:25Z board, and the numbers this slice stands in
#: for. Named here so a future re-capture that changes them has to say so.
BOARD_LEAGUES = 113
BOARD_MATCHES = 195
BOARD_FINISHED = 23
BOARD_KICKOFF_CLOCKS = 172
BOARD_BLANK_MAIN_IDS = 7


@pytest.fixture
def service():
    return StatPalAPIService(api_key="test-key-not-a-real-key")


@pytest.fixture
def board():
    return json.loads(BOARD.read_text())


@pytest.fixture
def fixtures(service, board):
    return service._parse_soccer_live_matches(board)


def _by_home(rows, name):
    for row in rows:
        if row.home_team == name:
            return row
    raise AssertionError(f"no row for {name!r} in {[r.home_team for r in rows]}")


# =============================================================================
# 1. The path. This is the bug.
# =============================================================================

class TestTheLiveBoardIsTheOneThatAnswers:

    def test_soccer_is_the_whole_map(self):
        """A measured fact about the venue, not a default. Adding a sport here
        without a live 200 behind it re-opens #3366 in the other direction."""
        assert LIVE_SCORE_ENDPOINTS == {"soccer": "matches/live"}

    def test_every_other_sport_keeps_livescores(self, service):
        assert service._live_endpoint("nfl") == "livescores"
        assert service._live_endpoint("tennis") == "livescores"
        assert service._live_endpoint("soccer") == "matches/live"

    @pytest.mark.asyncio
    async def test_the_url_asked_is_v2_matches_live(self, service, monkeypatch):
        """Through the transport, so a change to `_base_url` OR to the endpoint
        name is caught by the same test. `v2/soccer/livescores` is a 404 and
        `v1/soccer/matches/live` is a 404; only this pair answers."""
        asked = []

        async def fake_http_get(url, params=None):
            asked.append(url)
            return httpx.Response(
                200, json={"live_matches": {"league": []}},
                request=httpx.Request("GET", url),
            )

        monkeypatch.setattr(service.client, "get", fake_http_get)
        await service.get_live_fixtures("soccer")
        assert asked == ["https://statpal.io/api/v2/soccer/matches/live"]

    @pytest.mark.asyncio
    async def test_the_door_parses_the_board_with_the_soccer_reader(
        self, service, monkeypatch, board
    ):
        """END TO END THROUGH THE DOOR, and not for completeness. Every parse
        assertion below this class calls `_parse_soccer_live_matches` directly,
        so all of them pass on a `get_live_fixtures` that routes soccer to the
        SHARED parser and throws the new one away — mutation testing found
        exactly that hole. This is the test that closes it: same transport, same
        payload, and the two fields the shared parser gets wrong."""
        async def fake_http_get(url, params=None):
            return httpx.Response(200, json=board, request=httpx.Request("GET", url))

        monkeypatch.setattr(service.client, "get", fake_http_get)
        rows = await service.get_live_fixtures("soccer")
        finished = _by_home(rows, "Racing Club")
        assert (finished.home_score, finished.away_score) == (1, 2)
        assert _by_home(rows, "Barracas Central").status == "scheduled"

    @pytest.mark.asyncio
    async def test_a_dead_read_raises_rather_than_reading_as_no_games(
        self, service, monkeypatch
    ):
        """The whole reason this door exists (gotcha #53). Before this change
        soccer took THIS branch on every pass — a 404 that read as an outage."""
        async def fake_http_get(url, params=None):
            return httpx.Response(404, json={}, request=httpx.Request("GET", url))

        monkeypatch.setattr(service.client, "get", fake_http_get)
        with pytest.raises(StatPalUpstreamError):
            await service.get_live_fixtures("soccer")


# =============================================================================
# 2. The ship: seven sport keys stop being dark to the ESPN standby.
# =============================================================================

class TestTheFailoverMapCanReachSoccer:

    def test_seven_of_the_fourteen_mapped_keys_are_soccer(self):
        """The size of the hole, asserted so it cannot shrink unnoticed."""
        soccer_keys = sorted(
            k for k, v in STATPAL_SPORT_MAPPING.items() if v == "soccer"
        )
        assert len(soccer_keys) == 7
        assert "soccer_epl" in soccer_keys
        assert len(STATPAL_SPORT_MAPPING) == 14

    @pytest.mark.asyncio
    async def test_every_soccer_key_reads_rows_where_it_used_to_raise(
        self, service, monkeypatch, board
    ):
        """One transport, seven keys, the read the standby actually makes."""
        async def fake_http_get(url, params=None):
            if url.endswith("/v2/soccer/matches/live"):
                return httpx.Response(
                    200, json=board, request=httpx.Request("GET", url)
                )
            return httpx.Response(404, json={}, request=httpx.Request("GET", url))

        monkeypatch.setattr(service.client, "get", fake_http_get)
        for our_key, statpal_sport in STATPAL_SPORT_MAPPING.items():
            if statpal_sport != "soccer":
                continue
            rows = await service.get_live_fixtures(statpal_sport)
            assert rows, f"{our_key} still reads an empty live board"

    def test_a_finished_row_bears_state_for_the_readiness_check(self, fixtures):
        """`live_reading_for` uses the WRITER'S predicate, so the parser has to
        satisfy the writer's, not its own idea of a useful row."""
        from app.tasks.statpal_sync import live_row_bears_state

        assert live_row_bears_state(_by_home(fixtures, "Racing Club")) is True

    def test_an_unplayed_row_does_not_bear_state(self, fixtures):
        """The other direction, and the one that matters: a scheduled match must
        not make the standby look like it is serving a game in progress
        (CERT-2047's finding, applied to a sport it had not reached)."""
        from app.tasks.statpal_sync import live_row_bears_state

        assert live_row_bears_state(_by_home(fixtures, "Barracas Central")) is False


# =============================================================================
# 3. The ingestion door stays shut, by decision and not by a 404.
# =============================================================================

class TestTheIngestionDoorStaysShut:

    def test_soccer_is_named_as_dark(self):
        assert LIVESCORES_INGESTION_DARK_SPORTS == frozenset({"soccer"})

    @pytest.mark.asyncio
    async def test_the_live_writer_never_asks_for_soccer(self, service, monkeypatch):
        """Not "asks and discards" — never asks. `sync_statpal_schedules` calls
        this once per OUR key, so an un-fenced read is seven 189 KB downloads a
        cycle before it is anything else."""
        async def explode(url, params=None):  # pragma: no cover — must not run
            raise AssertionError(f"asked the venue for {url}")

        monkeypatch.setattr(service.client, "get", explode)
        assert await service.get_live_scores("soccer") == []

    @pytest.mark.asyncio
    async def test_the_refusal_is_logged_by_name(self, service, monkeypatch, caplog):
        """A silent `[]` is what this whole issue was. The reason travels."""
        async def explode(url, params=None):  # pragma: no cover — must not run
            raise AssertionError("asked the venue")

        monkeypatch.setattr(service.client, "get", explode)
        with caplog.at_level("INFO"):
            await service.get_live_scores("soccer")
        assert "LIVESCORES_INGESTION_DARK_SPORTS" in caplog.text

    @pytest.mark.asyncio
    async def test_every_other_sport_still_reads_its_live_board(
        self, service, monkeypatch
    ):
        """The fence is one sport wide. A fence that shut the ingestion path for
        everyone would pass every assertion above it."""
        asked = []

        async def fake_http_get(url, params=None):
            asked.append(url)
            return httpx.Response(
                200, json={"livescores": {"tournament": {"match": []}}},
                request=httpx.Request("GET", url),
            )

        monkeypatch.setattr(service.client, "get", fake_http_get)
        for sport in ("nfl", "nba", "nhl", "mlb"):
            await service.get_live_scores(sport)
        assert asked == [
            f"https://statpal.io/api/v1/{sport}/livescores"
            for sport in ("nfl", "nba", "nhl", "mlb")
        ]


# =============================================================================
# 4. The two fields the SHARED parser reads wrong. Controls included, because a
#    test that only checks the new parser cannot tell you why it exists.
# =============================================================================

class TestScoresLiveUnderGoals:

    def test_the_finished_match_carries_its_score(self, fixtures):
        row = _by_home(fixtures, "Racing Club")
        assert (row.home_score, row.away_score) == (1, 2)
        assert row.status == "finished"

    def test_the_shared_parser_reads_the_same_row_scoreless(self, service, board):
        """THE CONTROL. `_parse_fixtures` reaches these rows — its generic
        `"league" in val` branch matches `live_matches` — so "the shared parser
        would have returned nothing anyway" is not available as a defence."""
        shared = service._parse_fixtures(board, "soccer")
        assert len(shared) == len(service._parse_soccer_live_matches(board))
        assert all(row.home_score is None for row in shared)

    def test_an_unplayed_match_reports_no_score_not_nil_nil(self, fixtures):
        """The venue serves the literal string "?" before kick-off. A reader
        that took it for 0 would print 0-0 over a game nobody has started."""
        row = _by_home(fixtures, "Barracas Central")
        assert row.home_score is None and row.away_score is None


class TestAKickoffClockIsNotAPeriod:

    def test_the_clock_row_is_scheduled_and_carries_no_period(self, fixtures):
        row = _by_home(fixtures, "Barracas Central")
        assert row.status == "scheduled"
        # `raw_status` is what the live writer copies into `event.period`.
        assert row.raw_status is None

    def test_the_shared_normaliser_passes_the_clock_through(self):
        """THE CONTROL, and the reason soccer needs its own normaliser: the
        shared map has no rule for a wall clock, so it returns one as a status."""
        assert _normalize_status("22:00") == "22:00"

    def test_the_clock_is_the_rows_own_kickoff_time(self, fixtures):
        """Why it is safe to read a clock as scheduled: on 172 of 172 rows the
        status WAS the row's own `time`. The parsed start time is that clock."""
        row = _by_home(fixtures, "Barracas Central")
        assert row.start_time is not None
        assert row.start_time.strftime("%H:%M") == "22:00"

    def test_a_clock_that_disagrees_with_the_row_is_still_scheduled_and_says_so(
        self, service, caplog
    ):
        """The invariant is measured, not guaranteed. If the venue breaks it the
        row is still not a period — but the disagreement is not swallowed."""
        with caplog.at_level("WARNING"):
            status, raw = service._normalize_soccer_status("22:00", "19:30")
        assert (status, raw) == ("scheduled", None)
        assert "19:30" in caplog.text

    @pytest.mark.parametrize("token", ["67", "90+3", "45'"])
    def test_a_minute_reads_as_live_and_carries_the_period(self, service, token):
        """INFERRED, NOT MEASURED — the 04:25Z board had no match in play, and
        the parser's docstring says so. Pinned anyway: this is the shape the
        standby's live half depends on during a match, and if the real token
        turns out to be something else it falls through to the shared map."""
        assert service._normalize_soccer_status(token, "19:30") == ("live", token)

    def test_half_time_reads_as_live(self, service):
        """The one in-play token #3366 DID measure, on 2026-09-05."""
        assert service._normalize_soccer_status("HT", "19:30") == ("live", "HT")


# =============================================================================
# 5. Ids are carried, never substituted (D55) — and one of them is blank.
# =============================================================================

class TestIdsAreCarriedNeverSubstituted:

    def test_the_blank_main_id_is_emitted_blank(self, fixtures):
        """7 of the 195 rows had no `main_id`. The row is still emitted: this
        door feeds a reading keyed on the TEAM PAIR, and dropping it would
        under-report StatPal's coverage of exactly the games at risk."""
        row = _by_home(fixtures, "Londrina B")
        assert row.fixture_id == ""

    def test_no_fallback_id_is_promoted_into_the_fixture_id(self, fixtures, board):
        """#3094 is the 364-row repair that happens when one id space is written
        into another's column. The blank row's `fallback_id_3` is populated —
        and must not appear anywhere on the parsed row."""
        raw = board["live_matches"]["league"][1]["match"]
        assert raw["main_id"] == ""
        assert raw["fallback_id_3"]
        row = _by_home(fixtures, "Londrina B")
        assert raw["fallback_id_3"] not in (
            row.fixture_id, row.odds_id, row.stats_id,
        )

    def test_the_populated_row_keeps_the_venues_own_primary_key(self, fixtures):
        assert _by_home(fixtures, "Racing Club").fixture_id == "2026090711955"


# =============================================================================
# 6. Envelope shapes, and one bad row is never the board.
# =============================================================================

class TestTheEnvelope:

    def test_a_league_serving_one_match_as_a_dict_is_read(self, fixtures, board):
        """The one-item collapse StatPal does at every level of every payload."""
        assert isinstance(board["live_matches"]["league"][1]["match"], dict)
        assert _by_home(fixtures, "Londrina B") is not None

    def test_the_league_name_travels_with_the_row(self, fixtures):
        assert _by_home(fixtures, "Racing Club").league == (
            "Argentina: Liga Profesional - Clausura"
        )

    def test_every_row_in_the_slice_parses(self, fixtures):
        assert len(fixtures) == 3

    @pytest.mark.parametrize(
        "payload",
        [{}, {"live_matches": None}, {"live_matches": []}, {"livescore": {"league": []}}],
    )
    def test_a_shape_this_parser_does_not_know_is_empty_not_an_exception(
        self, service, payload
    ):
        """Including v1's `livescore` envelope — if someone routes the legacy
        board back here, it reads as empty rather than half-parsing."""
        assert service._parse_soccer_live_matches(payload) == []

    def test_a_row_of_the_wrong_shape_is_skipped_without_the_guard(
        self, service, board
    ):
        """The cheap half: a row whose `home` is not a dict has no team name, so
        the ordinary path already drops it. Kept separate from the test below so
        neither is mistaken for proving the other."""
        board["live_matches"]["league"][0]["match"].insert(0, {"home": "not a dict"})
        assert len(service._parse_soccer_live_matches(board)) == 3

    def test_one_row_that_RAISES_does_not_lose_the_board(
        self, service, board, monkeypatch
    ):
        """Gotcha #42, on a board of 195 rows across 113 leagues — and proved by
        making a row raise, because nothing in the shapes above reaches the
        try/except. Asserting only the shape case leaves the guard untested and
        a narrowed `except` passes: mutation testing found that too."""
        real = service._parse_soccer_live_match

        def explode_on_one(item, league_name):
            if isinstance(item, dict) and item.get("main_id") == "2026090711955":
                raise RuntimeError("a row the venue served in a shape we cannot read")
            return real(item, league_name)

        monkeypatch.setattr(service, "_parse_soccer_live_match", explode_on_one)
        rows = service._parse_soccer_live_matches(board)
        assert len(rows) == 2
        assert _by_home(rows, "Barracas Central") is not None

    def test_a_row_missing_a_team_name_is_dropped(self, service, board):
        """A team pair IS the key the standby matches on — half of one is not a
        row, it is a row that would silently key wrong."""
        board["live_matches"]["league"][0]["match"].append(
            {"main_id": "x", "home": {"name": "Only One"}, "away": {"name": ""}}
        )
        assert len(service._parse_soccer_live_matches(board)) == 3
