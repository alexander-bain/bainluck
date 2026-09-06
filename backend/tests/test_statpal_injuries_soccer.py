"""#2907 / authority/049 — soccer injuries arrive, and a dead path stops looking empty.

WHAT WAS BROKEN. `sync_statpal_injuries` has run hourly since it was written and
has never produced a row: on 2026-09-06, 0 of 2,610 events with a commence time
in the window carried `win_probability_sources -> 'statpal_injuries'`. It asked
`v2/soccer/injuries`. That path 404s. `_get` turns a 404 into None, the caller
turned None into `[]`, and `[]` is also what "nobody is hurt today" looks like
(gotcha #53) — so nothing anywhere said the fetch was dead.

WHAT THE VENUE ACTUALLY SERVES, measured 2026-09-06 (notice 26a — against the
venue's own API, by spec enumeration plus a live probe, not from our tables):

    statpal.io/static/openapi/openapi-compiled.yaml (v2.0.0, 01:44Z)
        53 sport paths. Injuries appear twice, both soccer:
          /soccer/injuries-suspensions  (v2)
          /soccer/injuries              (v1, tagged "Legacy")
        No roster or team path for any sport.

    live probe, 01:45Z, {nba,nfl,nhl,mlb} x {teams, injuries, injuries-suspensions,
    rosters, roster, players, squads, team-list} on v1
        404 on all 32, while season-schedule answered 200 seconds apart.

    v2/soccer/injuries-suspensions   200, 224,393 bytes   updated 06.09.2026 01:01:10
    v1/soccer/injuries               200, 243,340 bytes   updated 06.09.2026 01:01:10
    v2/soccer/injuries               404
    v1/soccer/injuries-suspensions   404

The version names are CROSSED, and that is the whole bug: we send soccer to v2
(`_base_url`) and appended v1's name. Both live paths carry the same data; v2's
carries the richer id set, so v2's name is the one pinned here.

THE FIXTURES. `statpal_soccer_injuries_20260906_fullcensus.json` is the whole
01:47Z payload and backs the COUNTS. `statpal_soccer_injuries_20260906.json` is
a 3-league slice chosen to cover every collapse shape and backs the SHAPE. One
fixture is never asked to back both.
"""
import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path

import httpx
import pytest

from app.services.statpal_api import (
    INJURY_BUCKET_STATUS,
    INJURY_ENDPOINTS,
    StatPalAPIService,
    _parse_injuries_suspensions,
)
from app.utils.statpal_injury_attach import Fixture, choose_fixture, team_tokens

FIXTURES = Path(__file__).parent / "fixtures"
FULL_CENSUS = FIXTURES / "statpal_soccer_injuries_20260906_fullcensus.json"
SLICE = FIXTURES / "statpal_soccer_injuries_20260906.json"

# Counted over the FULL payload at 2026-09-06 01:47Z. These are the venue's
# numbers, not a parser's opinion of them: a parser that quietly drops the
# collapsed-to-dict arm lands at ~670 and every other assertion still passes.
CENSUS_PLAYERS = 1004
CENSUS_OUT = 869
CENSUS_QUESTIONABLE = 135
CENSUS_FIXTURES_WITH_INJURIES = 146


@pytest.fixture
def service():
    return StatPalAPIService(api_key="test-key-not-a-real-key")


@pytest.fixture
def census():
    return json.loads(FULL_CENSUS.read_text())


@pytest.fixture
def slice_payload():
    return json.loads(SLICE.read_text())


# =============================================================================
# 1. The path. This is the bug.
# =============================================================================

class TestTheEndpointIsTheOneThatAnswers:

    def test_soccer_is_the_whole_map(self):
        """Not an oversight — a measured fact about the venue. Adding a sport
        here without a live 200 behind it re-opens #2907 in the other direction."""
        assert INJURY_ENDPOINTS == {"soccer": "injuries-suspensions"}

    @pytest.mark.asyncio
    async def test_the_url_asked_is_v2_injuries_suspensions(self, service, monkeypatch):
        """Through the transport, so a change to `_base_url` or to the endpoint
        name is caught by the same test. `v2/soccer/injuries` is a 404 and
        `v1/soccer/injuries-suspensions` is a 404; only this pair answers."""
        asked = []

        async def fake_http_get(url, params=None):
            asked.append(url)
            return httpx.Response(
                200, json={"injuries_suspensions": {"league": []}},
                request=httpx.Request("GET", url),
            )

        monkeypatch.setattr(service.client, "get", fake_http_get)
        await service.get_injuries_result("soccer")
        assert asked == ["https://statpal.io/api/v2/soccer/injuries-suspensions"]

    @pytest.mark.asyncio
    async def test_an_unsupported_sport_is_never_asked(self, service, monkeypatch):
        """The four US sports have no injury path at the venue. Asking anyway
        spends quota to collect a 404 every hour, and — before this — reported
        the 404 as an empty injury list."""
        async def explode(url, params=None):  # pragma: no cover — must not run
            raise AssertionError(f"asked the venue for {url}")

        monkeypatch.setattr(service.client, "get", explode)
        for sport in ("nba", "nfl", "nhl", "mlb"):
            result = await service.get_injuries_result(sport)
            assert result.reason == "no_venue_path"
            assert result.asked is False
            assert result.is_alarm is False
            assert result.injuries == []


# =============================================================================
# 2. A failed read is not an empty roster. Gotcha #53, and #2907's own acceptance.
# =============================================================================

class TestAFailedReadIsNotAnEmptyRoster:

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status_code", [404, 401, 429, 500])
    async def test_every_dead_response_reads_as_fetch_failed(
        self, service, monkeypatch, status_code, caplog
    ):
        async def fake_http_get(url, params=None):
            return httpx.Response(status_code, json={}, request=httpx.Request("GET", url))

        monkeypatch.setattr(service.client, "get", fake_http_get)
        with caplog.at_level(logging.ERROR):
            result = await service.get_injuries_result("soccer")

        assert result.injuries == []
        assert result.reason == "fetch_failed"
        assert result.is_alarm is True
        assert "NOT an empty injury list" in caplog.text

    @pytest.mark.asyncio
    async def test_a_two_hundred_that_is_an_error_body_reads_as_fetch_failed(
        self, service, monkeypatch
    ):
        """The vendor's `invalid-request` 200. It has a body, so a caller
        checking only the status code would parse it as data."""
        async def fake_http_get(url, params=None):
            return httpx.Response(
                200, text="invalid-request", request=httpx.Request("GET", url)
            )

        monkeypatch.setattr(service.client, "get", fake_http_get)
        assert (await service.get_injuries_result("soccer")).reason == "fetch_failed"

    @pytest.mark.asyncio
    async def test_a_real_but_empty_payload_is_empty_not_failed(self, service, monkeypatch):
        """The control, and the reason `empty` is its own reason: a genuinely
        quiet hour must NOT raise an alarm, or the alarm stops meaning anything."""
        async def fake_http_get(url, params=None):
            return httpx.Response(
                200,
                json={"injuries_suspensions": {"updated": "06.09.2026 01:01:10", "league": []}},
                request=httpx.Request("GET", url),
            )

        monkeypatch.setattr(service.client, "get", fake_http_get)
        result = await service.get_injuries_result("soccer")
        assert result.reason == "empty"
        assert result.is_alarm is False

    @pytest.mark.asyncio
    async def test_the_list_wrapper_still_returns_a_list(self, service, monkeypatch, census):
        """`get_injuries` keeps its signature so no other caller changes."""
        async def fake_http_get(url, params=None):
            return httpx.Response(200, json=census, request=httpx.Request("GET", url))

        monkeypatch.setattr(service.client, "get", fake_http_get)
        assert len(await service.get_injuries("soccer")) == CENSUS_PLAYERS


# =============================================================================
# 3. The parser. Counts from the census, shapes from the slice.
# =============================================================================

class TestTheCensusParses:

    def test_every_sidelined_player_in_the_payload_arrives(self, census):
        assert len(_parse_injuries_suspensions(census)) == CENSUS_PLAYERS

    def test_the_availability_split_is_the_venues(self, census):
        rows = _parse_injuries_suspensions(census)
        assert sum(1 for r in rows if r.status == "Out") == CENSUS_OUT
        assert sum(1 for r in rows if r.status == "Questionable") == CENSUS_QUESTIONABLE

    def test_every_player_is_attributable_to_a_fixture_and_a_team(self, census):
        rows = _parse_injuries_suspensions(census)
        assert all(r.player_name and r.team and r.opponent for r in rows)
        # Every row is keyable, but NOT every row via the same key: 1,002 of the
        # 1,004 carried `main_id` and one fixture (LASK v AEK Athens, 08.09)
        # published only a fallback. A keying scheme that assumed `main_id`
        # would drop that match's players with no error.
        assert all(r.fixture_main_id or r.fixture_fallback_ids for r in rows)
        assert sum(1 for r in rows if not r.fixture_main_id) == 2
        keys = {r.fixture_main_id or r.fixture_fallback_ids[0] for r in rows}
        assert len(keys) == CENSUS_FIXTURES_WITH_INJURIES

    def test_a_body_that_is_not_this_shape_is_empty_not_an_exception(self):
        for junk in ({}, {"injuries_suspensions": None}, {"data": []}, {"injuries_suspensions": []}):
            assert _parse_injuries_suspensions(junk) == []


class TestTheCollapseShapes:
    """StatPal collapses a one-element list to a bare dict, at more than one
    level. In the census payload `to_miss` was a list 204 times and a dict 63
    (`questionable`: 30 / 65) — a parser that assumes list silently loses a
    third of the players and raises on none of them. `_as_list` at every level.
    """

    def test_the_slice_carries_both_arms_of_both_buckets(self, slice_payload):
        """The fixture itself must keep covering what it was cut to cover — a
        slice that drifts to one arm makes the tests below vacuous."""
        leagues = slice_payload["injuries_suspensions"]["league"]
        seen = set()
        collapsed_match_level = False
        for league in leagues:
            matches = league["match"]
            if isinstance(matches, dict):
                collapsed_match_level = True
                matches = [matches]
            for match in matches:
                for side in ("home", "away"):
                    sidelined = match[side].get("sidelined") or {}
                    for bucket in ("to_miss", "questionable"):
                        entry = sidelined.get(bucket)
                        if isinstance(entry, dict) and entry.get("player") is not None:
                            arm = "list" if isinstance(entry["player"], list) else "dict"
                            seen.add(f"{bucket}:{arm}")
        assert seen == {
            "to_miss:list", "to_miss:dict", "questionable:list", "questionable:dict",
        }
        assert collapsed_match_level, "the slice no longer covers a collapsed league.match"

    def test_players_arrive_from_both_arms(self, slice_payload):
        rows = _parse_injuries_suspensions(slice_payload)
        assert len(rows) == 21
        assert {r.status for r in rows} == {"Out", "Questionable"}

    def test_a_match_with_nobody_sidelined_contributes_nobody(self, slice_payload):
        """`sidelined: {to_miss: null, questionable: null}` is the common case
        and must parse to zero rows, not to a row with an empty name."""
        rows = _parse_injuries_suspensions(slice_payload)
        assert all(r.player_name.strip() for r in rows)
        assert "2026101612553" not in {r.fixture_main_id for r in rows}


class TestStatusIsTheBucketNotTheVendorsWord:
    """The trap this file exists to pin as much as the path does.

    The vendor's `status` is a REASON — `Knee Injury`, `Red Card`, `Inactive`,
    `Coach's decision`; 49 distinct strings over 1,004 players. Availability is
    the BUCKET. `routes/events.py` keeps only `("Out", "Doubtful")` on a
    completed game, so writing `Knee Injury` into our `status` would empty every
    completed-game injury list while looking exactly like working data.
    """

    def test_the_bucket_map_is_the_availability_vocabulary(self):
        assert INJURY_BUCKET_STATUS == {"to_miss": "Out", "questionable": "Questionable"}

    def test_a_to_miss_player_is_out_and_keeps_the_reason(self, census):
        rows = _parse_injuries_suspensions(census)
        bernier = next(r for r in rows if r.player_name == "A. Bernier")
        assert bernier.status == "Out"
        assert bernier.injury_type == "Injury"
        assert bernier.team == "Charleroi"
        assert bernier.opponent == "Royale Union SG"
        assert bernier.is_home is True

    def test_no_vendor_reason_ever_lands_in_our_status_field(self, census):
        rows = _parse_injuries_suspensions(census)
        assert {r.status for r in rows} <= set(INJURY_BUCKET_STATUS.values())
        # ...and the reasons really are the varied strings that would have
        # poisoned it, so the assertion above is not passing on an empty set.
        assert len({r.injury_type for r in rows}) > 20

    def test_the_match_date_is_not_passed_off_as_a_report_time(self, census):
        """There is no per-injury report time in this payload. Writing the
        fixture's date into `reported_at` would read as freshness we do not have."""
        rows = _parse_injuries_suspensions(census)
        assert all(r.reported_at is None for r in rows)
        assert any(r.fixture_date is not None for r in rows)


# =============================================================================
# 4. The attach rule. Both sides, or nothing.
# =============================================================================

class TestBothSidesOrNothing:
    """The code this replaces matched ONE team with
    `key.endswith(team_lower.split()[-1])`. While the fetch was 404ing that cost
    nothing, because the loop never had a row to hang. The change that makes
    rows flow is the change that would have started hanging another club's
    injured player on the wrong game, so they belong in one commit.
    """

    SYDNEY = Fixture("f1", "Sydney FC", "WS Wanderers", date(2026, 10, 16))
    BOLTON = Fixture("f2", "Bolton Wanderers", "Wigan Athletic", date(2026, 10, 16))

    def test_an_exact_pair_attaches(self):
        assert choose_fixture(
            "Sydney FC", "WS Wanderers", date(2026, 10, 16), [self.SYDNEY, self.BOLTON]
        ) == "f1"

    def test_a_qualified_naming_of_one_side_still_attaches(self):
        """"FC Twente Enschede" vs "Twente", "Caykur Rizespor" vs "Rizespor" —
        18 of the 63 production matches on 2026-09-06 were this shape."""
        twente = Fixture("f3", "Groningen", "Twente", date(2026, 9, 6))
        assert choose_fixture(
            "Groningen", "FC Twente Enschede", date(2026, 9, 6), [twente]
        ) == "f3"

    def test_one_side_agreeing_is_not_enough(self):
        """The old rule's exact failure: "Wanderers" matched "Wanderers"."""
        assert choose_fixture(
            "Bolton Wanderers", "Wigan Athletic", date(2026, 10, 16), [self.SYDNEY]
        ) is None

    def test_two_clubs_sharing_a_city_are_not_confused(self):
        derby = Fixture("f4", "Manchester United", "Arsenal", date(2026, 9, 6))
        assert choose_fixture("Manchester City", "Arsenal", date(2026, 9, 6), [derby]) is None

    def test_orientation_is_respected(self):
        """A reverse leg is a different game. 0 of 168 production events matched
        only under a swap, so accepting one buys nothing and risks a wrong game."""
        assert choose_fixture(
            "WS Wanderers", "Sydney FC", date(2026, 10, 16), [self.SYDNEY]
        ) is None

    def test_ambiguity_is_refused_not_guessed(self):
        a = Fixture("a", "Sydney FC", "WS Wanderers", None)
        b = Fixture("b", "Sydney FC", "WS Wanderers", None)
        assert choose_fixture("Sydney FC", "WS Wanderers", date(2026, 10, 16), [a, b]) is None

    def test_the_date_breaks_a_tie_and_only_a_tie(self):
        today = Fixture("today", "Sydney FC", "WS Wanderers", date(2026, 10, 16))
        later = Fixture("later", "Sydney FC", "WS Wanderers", date(2027, 2, 1))
        assert choose_fixture(
            "Sydney FC", "WS Wanderers", date(2026, 10, 16), [today, later]
        ) == "today"

    def test_an_unparsed_fixture_date_can_never_exclude_a_unique_hit(self):
        """The tiebreak is consulted only after two fixtures already matched, so
        a date the vendor served in a format we could not read costs nothing."""
        dateless = Fixture("f5", "Sydney FC", "WS Wanderers", None)
        assert choose_fixture(
            "Sydney FC", "WS Wanderers", date(2026, 10, 16), [dateless]
        ) == "f5"

    def test_a_nameless_side_matches_nothing(self):
        assert choose_fixture("", "WS Wanderers", None, [self.SYDNEY]) is None
        assert choose_fixture("Sydney FC", "   ", None, [self.SYDNEY]) is None


class TestTeamTokens:

    def test_diacritics_and_legal_forms_do_not_block_a_match(self):
        assert team_tokens("Çaykur Rizespor") >= {"rizespor"}
        assert team_tokens("Örgryte IS") == team_tokens("Orgryte IS")
        assert team_tokens("FC Copenhagen") == team_tokens("Copenhagen")

    def test_a_name_that_is_only_noise_keeps_its_tokens(self):
        """Stripping to nothing would make the club match everything."""
        assert team_tokens("FC") == {"fc"}
        assert team_tokens("") == frozenset()


# =============================================================================
# 5. The task's terminal. Enrolled in ENFORCED_TASKS in this same change.
# =============================================================================

class TestTheTaskCannotReportAQuietDayForADeadEndpoint:

    def test_a_fetch_failure_is_a_failed_terminal(self):
        from app.utils.task_verdict import verdict_for

        summary = {
            "terminal": "failed",
            "total_injuries": 0,
            "events_enriched": 0,
            "fetch_failures": [{"statpal_sport": "soccer", "endpoint": "injuries-suspensions"}],
            "sports": [],
        }
        verdict = verdict_for("statpal_injuries", summary)
        assert verdict.verdict == "failed"
        assert verdict.is_green is False
        assert verdict.authoritative is True

    def test_a_real_pass_is_green(self):
        from app.utils.task_verdict import verdict_for

        summary = {
            "terminal": "complete",
            "total_injuries": CENSUS_PLAYERS,
            "events_enriched": 63,
            "fetch_failures": [],
            "sports": [{"statpal_sport": "soccer", "reason": "ok"}],
        }
        assert verdict_for("statpal_injuries", summary).is_green is True

    def test_a_sport_with_no_venue_path_is_not_a_failure(self):
        """NBA has no injuries endpoint anywhere at the venue. That is a fact
        about StatPal, not a broken run, and must not cry wolf every hour."""
        from app.utils.task_verdict import verdict_for

        summary = {
            "terminal": "complete",
            "total_injuries": 0,
            "events_enriched": 0,
            "fetch_failures": [],
            "sports": [{"statpal_sport": "nba", "reason": "no_venue_path"}],
        }
        assert verdict_for("statpal_injuries", summary).is_green is True

    def test_a_missing_key_is_not_green_either(self):
        from app.utils.task_verdict import verdict_for

        verdict = verdict_for(
            "statpal_injuries",
            {"skipped": True, "reason": "STATPAL_API_KEY not set", "terminal": "skipped"},
        )
        assert verdict.is_green is False
        assert verdict.authoritative is True

    def test_the_task_is_enrolled(self):
        """Enrolment without a terminal is a no-op, and a terminal without
        enrolment is ignored. Both halves, or neither is worth anything."""
        from app.utils.task_verdict import ENFORCED_TASKS

        assert "statpal_injuries" in ENFORCED_TASKS


# =============================================================================
# 6. The end-to-end shape: a census payload, real production team names.
# =============================================================================

class TestAgainstProductionNames:
    """The 63 events that attached on 2026-09-06 are the ship. Six of them are
    pinned by name here — three exact pairs, three that needed containment —
    so a normaliser change that quietly halves the attach rate is caught.
    """

    PAIRS = [
        ("Fluminense", "Vasco da Gama"),
        ("Groningen", "FC Twente Enschede"),
        ("Çaykur Rizespor", "Alanyaspor"),
        ("Hamburger SV", "FSV Mainz 05"),
        ("Alavés", "CA Osasuna"),
        ("ADO Den Haag", "Fortuna Sittard"),
    ]

    @pytest.mark.parametrize("home,away", PAIRS)
    def test_a_production_event_finds_exactly_one_fixture(self, census, home, away):
        rows = _parse_injuries_suspensions(census)
        fixtures = {}
        for row in rows:
            if row.fixture_main_id in fixtures:
                continue
            h, a = (row.team, row.opponent) if row.is_home else (row.opponent, row.team)
            fixtures[row.fixture_main_id] = Fixture(
                row.fixture_main_id, h, a,
                row.fixture_date.date() if row.fixture_date else None,
            )
        chosen = choose_fixture(home, away, None, list(fixtures.values()))
        assert chosen is not None, f"{home} vs {away} no longer attaches"
        assert any(r.fixture_main_id == chosen for r in rows)

    def test_the_whole_census_produces_no_ambiguous_pair(self, census):
        """0 ambiguous over 168 production events x 146 fixtures on 2026-09-06.
        Two fixtures with the same two clubs would mean the pair rule alone
        cannot decide, and the date tiebreak would be carrying the load."""
        rows = _parse_injuries_suspensions(census)
        seen = {}
        for row in rows:
            h, a = (row.team, row.opponent) if row.is_home else (row.opponent, row.team)
            key = (team_tokens(h), team_tokens(a), row.fixture_date)
            seen.setdefault(key, set()).add(row.fixture_main_id)
        collisions = {k: v for k, v in seen.items() if len(v) > 1}
        assert not collisions, f"same pair, same day, two fixtures: {collisions}"


def test_the_window_the_task_attaches_over_is_still_the_documented_one():
    """A guard on the shape of the ship rather than on a number: injuries are a
    1h product and the attach window is -6h..+2d. If that window moves, the
    census counts above stop describing what production will do."""
    import inspect

    from app.tasks import statpal_sync

    source = inspect.getsource(statpal_sync._sync_statpal_injuries)
    assert "timedelta(hours=6)" in source
    assert "timedelta(days=2)" in source
    # and the write must stay a Core update — gotcha #4.
    assert "update(Event)" in source
    assert "event.win_probability_sources =" not in source


def test_one_fetch_per_statpal_sport_not_one_per_league_key():
    """Seven of our sport keys map to `soccer`. The loop this replaces asked the
    venue for the same 224 KB payload seven times an hour and attributed each
    copy to one league."""
    import inspect

    from app.tasks import statpal_sync
    from app.utils.sport_keys import STATPAL_SPORT_MAPPING

    soccer_keys = [k for k, v in STATPAL_SPORT_MAPPING.items() if v == "soccer"]
    assert len(soccer_keys) > 1, "the dedupe is only meaningful while keys collide"

    source = inspect.getsource(statpal_sync._sync_statpal_injuries)
    assert "dict.fromkeys(STATPAL_SPORT_MAPPING.values())" in source
    assert "get_injuries_result" in source
