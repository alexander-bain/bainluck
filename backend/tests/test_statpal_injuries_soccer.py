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
import asyncio
import json
import logging
from collections import namedtuple
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from pathlib import Path

import httpx
import pytest

#: The projected event row `_sync_statpal_injuries` selects.
_Row = namedtuple(
    "_Row",
    "id home_team_name away_team_name commence_time win_probability_sources",
)


async def _no_sleep(_seconds):
    """The task paces itself between sports; the test does not need to."""


def _all_sports_fetch(**overrides):
    """A fetch result for every StatPal sport, defaulting to `no_venue_path`.

    Only soccer has an injuries endpoint at the venue, so everything else must
    take the not-asked branch — and a test that only supplied soccer would
    KeyError, which is the point of building the map from the real mapping.
    """
    from app.services.statpal_api import StatPalInjuryFetch
    from app.utils.sport_keys import STATPAL_SPORT_MAPPING

    results = {
        sport: StatPalInjuryFetch([], "no_venue_path", sport, None)
        for sport in set(STATPAL_SPORT_MAPPING.values())
    }
    results.update(overrides)
    return results

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
        """The named control for the both-sides rule: the home team really does
        agree and the away team really does not, so weakening `and` to `or`
        fails HERE and not only in some downstream case."""
        assert choose_fixture(
            "Sydney FC", "Wigan Athletic", date(2026, 10, 16), [self.SYDNEY]
        ) is None
        # ...and the mirror, so the rule is not one-sided in the other direction.
        assert choose_fixture(
            "Bolton Wanderers", "WS Wanderers", date(2026, 10, 16), [self.SYDNEY]
        ) is None

    def test_a_shared_trailing_word_is_not_a_team(self):
        """The old rule was `key.endswith(team_lower.split()[-1])`, which made
        every club ending in "Wanderers" the same club. Token containment does
        not: neither {bolton, wanderers} nor {ws, wanderers} contains the other."""
        assert team_tokens("Bolton Wanderers") != team_tokens("WS Wanderers")
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


class TestTheTaskEmitsTheWriteItClaims:
    """Drives `_sync_statpal_injuries` end to end against a fake session that
    keeps the real SQLAlchemy statements, so the assertions are about the SQL
    that would reach Postgres — not about a source string and not about a fake
    that agrees by construction.
    """

    @staticmethod
    def _run(monkeypatch, *, events, fetch_by_sport):
        import app.services.statpal_api as api_module
        from app.tasks import statpal_sync

        executed = []

        class FakeResult:
            def __init__(self, rows):
                self._rows = rows

            def all(self):
                return self._rows

        class FakeSession:
            async def execute(self, statement):
                executed.append(statement)
                is_select = statement.__visit_name__ == "select"
                return FakeResult(events if is_select else [])

        @asynccontextmanager
        async def fake_session():
            yield FakeSession()

        class FakeService:
            def __init__(self, *a, **kw):
                self.asked = []

            async def get_injuries_result(self, sport):
                self.asked.append(sport)
                return fetch_by_sport[sport]

            async def close(self):
                pass

        service_holder = {}

        def make_service(*a, **kw):
            service_holder["service"] = FakeService()
            return service_holder["service"]

        monkeypatch.setattr(statpal_sync, "get_task_session", fake_session)
        monkeypatch.setattr(api_module, "StatPalAPIService", make_service)
        monkeypatch.setattr(api_module, "is_available", lambda: True)
        monkeypatch.setattr(statpal_sync.asyncio, "sleep", _no_sleep)

        summary = asyncio.run(statpal_sync._sync_statpal_injuries())
        return summary, executed, service_holder["service"]

    def test_a_matched_event_gets_a_core_update_carrying_the_players(
        self, monkeypatch, census
    ):
        """Gotcha #4: a JSONB write goes through Core `update()`. The statement
        below is the real thing — table, primary-key filter and payload."""
        from app.services.statpal_api import StatPalInjuryFetch, _parse_injuries_suspensions

        rows = _parse_injuries_suspensions(census)
        events = [
            _Row(101, "Fluminense", "Vasco da Gama", datetime(2026, 9, 6, 0, tzinfo=timezone.utc), None),
            _Row(102, "Nowhere United", "Nobody City", datetime(2026, 9, 6, 0, tzinfo=timezone.utc), None),
        ]
        summary, executed, service = self._run(
            monkeypatch,
            events=events,
            fetch_by_sport=_all_sports_fetch(
                soccer=StatPalInjuryFetch(rows, "ok", "soccer", "injuries-suspensions")
            ),
        )

        updates = [s for s in executed if s.__visit_name__ == "update"]
        assert len(updates) == 1, "only the matched event is written"
        statement = updates[0]
        assert statement.table.name == "events"

        values = dict(statement._values)
        payload = list(values.values())[0].value
        assert "win_probability_sources" in {c.name for c in values}
        assert payload["statpal_injuries"], "the write carries players, not an empty list"
        assert {p["team"] for p in payload["statpal_injuries"]} <= {"Fluminense", "Vasco"}
        assert all(p["status"] in ("Out", "Questionable") for p in payload["statpal_injuries"])
        assert payload["statpal_injuries_updated"]

        assert summary["terminal"] == "complete"
        assert summary["events_enriched"] == 1
        assert summary["total_injuries"] == len(rows)

    def test_one_fetch_per_statpal_sport(self, monkeypatch, census):
        """Seven of our keys map to `soccer`; the venue is asked once."""
        from app.services.statpal_api import StatPalInjuryFetch, _parse_injuries_suspensions
        from app.utils.sport_keys import STATPAL_SPORT_MAPPING

        rows = _parse_injuries_suspensions(census)
        _, _, service = self._run(
            monkeypatch,
            events=[],
            fetch_by_sport=_all_sports_fetch(
                soccer=StatPalInjuryFetch(rows, "ok", "soccer", "injuries-suspensions")
            ),
        )
        assert service.asked.count("soccer") == 1
        assert len([k for k, v in STATPAL_SPORT_MAPPING.items() if v == "soccer"]) > 1
        assert sorted(service.asked) == sorted(set(STATPAL_SPORT_MAPPING.values()))

    def test_a_dead_venue_path_fails_the_run_and_writes_nothing(self, monkeypatch):
        from app.services.statpal_api import StatPalInjuryFetch

        summary, executed, _ = self._run(
            monkeypatch,
            events=[],
            fetch_by_sport=_all_sports_fetch(
                soccer=StatPalInjuryFetch([], "fetch_failed", "soccer", "injuries-suspensions")
            ),
        )
        assert summary["terminal"] == "failed"
        assert summary["fetch_failures"] == [
            {"statpal_sport": "soccer", "endpoint": "injuries-suspensions"}
        ]
        assert not [s for s in executed if s.__visit_name__ == "update"]

    def test_a_sport_with_no_path_does_not_fail_the_run(self, monkeypatch):
        from app.services.statpal_api import StatPalInjuryFetch

        summary, _, _ = self._run(
            monkeypatch,
            events=[],
            fetch_by_sport=_all_sports_fetch(
                soccer=StatPalInjuryFetch([], "empty", "soccer", "injuries-suspensions")
            ),
        )
        assert summary["terminal"] == "complete"
        assert summary["fetch_failures"] == []
        reasons = {d["statpal_sport"]: d["reason"] for d in summary["sports"]}
        assert reasons["nfl"] == "no_venue_path"
        assert reasons["soccer"] == "empty"


class TestASuccessfulSnapshotReplacesTheOldOne:
    """CERT-1999's BLOCK, and it was right.

    The first cut wrote only additively. A later SUCCESSFUL pass that no longer
    listed a fixture emitted no update at all, so the old JSONB stayed — and
    `routes/events.py` reads it with no freshness check. A player who had
    recovered would go on being printed as the cause of a line move, for as long
    as the event stayed in the window, with the task returning `complete` every
    hour.

    A successful snapshot is CURRENT information, including about who is no
    longer hurt. A failed one is not information at all, and must never delete.
    """

    HOME, AWAY = "Fluminense", "Vasco da Gama"

    def _event(self, sources):
        return _Row(
            101, self.HOME, self.AWAY,
            datetime(2026, 9, 6, 0, tzinfo=timezone.utc), sources,
        )

    @staticmethod
    def _written(executed):
        """The JSONB the last update would put in the row."""
        updates = [s for s in executed if s.__visit_name__ == "update"]
        assert updates, "no update was emitted"
        return list(dict(updates[-1]._values).values())[0].value

    @staticmethod
    def _route_reads(sources):
        """The event route's own expression, `routes/events.py:12693`.

        Replicated rather than imported because it is inline in a 400-line
        handler; the guard below pins that the route still spells it this way.
        """
        return (sources or {}).get("statpal_injuries", [])

    def test_the_route_still_reads_the_key_this_test_replicates(self):
        import inspect

        from app.routes import events as events_route

        source = inspect.getsource(events_route)
        assert '(event.win_probability_sources or {}).get("statpal_injuries", [])' in source

    def test_two_successful_cycles_remove_a_recovered_player(self, monkeypatch, census):
        """Cycle 1 populates from the real payload. Cycle 2 is a valid, empty,
        SUCCESSFUL snapshot. The player must be gone from what the route reads."""
        from app.services.statpal_api import StatPalInjuryFetch, _parse_injuries_suspensions

        rows = _parse_injuries_suspensions(census)
        _, executed_one, _ = TestTheTaskEmitsTheWriteItClaims._run(
            monkeypatch,
            events=[self._event(None)],
            fetch_by_sport=_all_sports_fetch(
                soccer=StatPalInjuryFetch(rows, "ok", "soccer", "injuries-suspensions")
            ),
        )
        after_one = self._written(executed_one)
        assert self._route_reads(after_one), "cycle 1 must actually populate"
        assert any(p["team"] == "Fluminense" for p in self._route_reads(after_one))

        summary, executed_two, _ = TestTheTaskEmitsTheWriteItClaims._run(
            monkeypatch,
            events=[self._event(after_one)],
            fetch_by_sport=_all_sports_fetch(
                soccer=StatPalInjuryFetch([], "empty", "soccer", "injuries-suspensions")
            ),
        )
        after_two = self._written(executed_two)
        assert self._route_reads(after_two) == [], "the recovered players are still there"
        assert "statpal_injuries_updated" not in after_two, "a stamp with no data"
        assert summary["events_cleared"] == 1
        assert summary["terminal"] == "complete"

    def test_a_fixture_that_drops_out_of_a_populated_snapshot_is_cleared(
        self, monkeypatch, census
    ):
        """The commoner shape: the snapshot is full of OTHER games, and ours is
        simply no longer in it. That is still current information about ours."""
        from app.services.statpal_api import StatPalInjuryFetch, _parse_injuries_suspensions

        rows = _parse_injuries_suspensions(census)
        stale = {
            "statpal_injuries": [
                {"player": "Recovered Player", "team": "Nowhere", "status": "Out",
                 "type": "Knee Injury", "detail": None}
            ],
            "statpal_injuries_updated": "2026-09-05T01:00:00+00:00",
            "espn": {"probability": 0.5},
        }
        event = _Row(
            202, "Nowhere United", "Nobody City",
            datetime(2026, 9, 6, 0, tzinfo=timezone.utc), stale,
        )
        summary, executed, _ = TestTheTaskEmitsTheWriteItClaims._run(
            monkeypatch,
            events=[event],
            fetch_by_sport=_all_sports_fetch(
                soccer=StatPalInjuryFetch(rows, "ok", "soccer", "injuries-suspensions")
            ),
        )
        after = self._written(executed)
        assert self._route_reads(after) == []
        assert summary["events_cleared"] == 1
        assert summary["events_enriched"] == 0
        # everything else in the JSONB is untouched — this clears one source,
        # not the column.
        assert after["espn"] == {"probability": 0.5}

    def test_a_fetch_failure_never_deletes_what_we_already_know(self, monkeypatch):
        """The control that keeps the clear safe. A 404 hour must not wipe every
        injury list on the site — that is the destructive twin of the bug this
        repair fixes, and it is one bad upstream day away."""
        from app.services.statpal_api import StatPalInjuryFetch

        stale = {
            "statpal_injuries": [
                {"player": "Still Injured", "team": "Fluminense", "status": "Out",
                 "type": "Hip Injury", "detail": None}
            ],
            "statpal_injuries_updated": "2026-09-05T01:00:00+00:00",
        }
        summary, executed, _ = TestTheTaskEmitsTheWriteItClaims._run(
            monkeypatch,
            events=[self._event(stale)],
            fetch_by_sport=_all_sports_fetch(
                soccer=StatPalInjuryFetch([], "fetch_failed", "soccer", "injuries-suspensions")
            ),
        )
        assert not [s for s in executed if s.__visit_name__ == "update"], (
            "a failed read deleted data"
        )
        assert summary["events_cleared"] == 0
        assert summary["terminal"] == "failed"

    def test_an_event_that_never_had_injuries_is_not_rewritten(self, monkeypatch, census):
        """105 of the 168 soccer events in the window match no fixture at all.
        Clearing must not turn into 105 pointless writes an hour."""
        from app.services.statpal_api import StatPalInjuryFetch, _parse_injuries_suspensions

        rows = _parse_injuries_suspensions(census)
        summary, executed, _ = TestTheTaskEmitsTheWriteItClaims._run(
            monkeypatch,
            events=[_Row(303, "Nowhere United", "Nobody City",
                         datetime(2026, 9, 6, 0, tzinfo=timezone.utc), {"espn": {}})],
            fetch_by_sport=_all_sports_fetch(
                soccer=StatPalInjuryFetch(rows, "ok", "soccer", "injuries-suspensions")
            ),
        )
        assert not [s for s in executed if s.__visit_name__ == "update"]
        assert summary["events_cleared"] == 0

    def test_a_still_injured_player_survives_a_second_cycle(self, monkeypatch, census):
        """The other control: the repair must not clear a fixture that is STILL
        in the snapshot, or it would delete and rewrite the same list hourly and
        an intervening read would see nothing."""
        from app.services.statpal_api import StatPalInjuryFetch, _parse_injuries_suspensions

        rows = _parse_injuries_suspensions(census)
        fetch = _all_sports_fetch(
            soccer=StatPalInjuryFetch(rows, "ok", "soccer", "injuries-suspensions")
        )
        _, first, _ = TestTheTaskEmitsTheWriteItClaims._run(
            monkeypatch, events=[self._event(None)], fetch_by_sport=fetch
        )
        after_one = self._written(first)
        summary, second, _ = TestTheTaskEmitsTheWriteItClaims._run(
            monkeypatch, events=[self._event(after_one)], fetch_by_sport=fetch
        )
        after_two = self._written(second)
        assert self._route_reads(after_two)
        assert [p["player"] for p in self._route_reads(after_two)] == [
            p["player"] for p in self._route_reads(after_one)
        ]
        assert summary["events_cleared"] == 0
        assert summary["events_enriched"] == 1


class TestTheCapCannotSilenceOneTeam:
    """A shared cap over two unequal populations empties the smaller one first.

    Ten per event, both teams in one list. In the 2026-09-06 payload 22 of 146
    fixtures carried more than ten sidelined players and 4 of them would have
    shown ONLY ONE SIDE in vendor order. The reader attributes a move to the
    team that FELL, so such a game could never explain an away-side drop however
    many away players were hurt — the data would be there and unusable.
    """

    @staticmethod
    def _inj(name, home):
        from app.services.statpal_api import StatPalInjury

        return StatPalInjury(
            player_id="1", player_name=name, team="H" if home else "A",
            status="Out", is_home=home,
        )

    def test_a_lopsided_fixture_still_shows_both_teams_inside_the_cap(self):
        from app.tasks.statpal_sync import _interleave_sides

        rows = [self._inj(f"h{i}", True) for i in range(14)]
        rows += [self._inj(f"a{i}", False) for i in range(3)]
        capped = _interleave_sides(rows)[:10]
        assert [r.player_name for r in capped[:6]] == ["h0", "a0", "h1", "a1", "h2", "a2"]
        assert {r.is_home for r in capped} == {True, False}

    def test_vendor_order_would_have_silenced_the_away_side(self):
        """The control: without the interleave this is a one-sided list, which
        is what makes the assertion above worth making."""
        rows = [self._inj(f"h{i}", True) for i in range(14)]
        rows += [self._inj(f"a{i}", False) for i in range(3)]
        assert {r.is_home for r in rows[:10]} == {True}

    def test_nothing_is_dropped_and_order_within_a_side_is_kept(self):
        from app.tasks.statpal_sync import _interleave_sides

        rows = [self._inj("h0", True), self._inj("a0", False), self._inj("h1", True)]
        out = _interleave_sides(rows)
        assert len(out) == len(rows)
        assert [r.player_name for r in out if r.is_home] == ["h0", "h1"]

    def test_a_one_sided_fixture_is_unchanged(self):
        from app.tasks.statpal_sync import _interleave_sides

        rows = [self._inj(f"h{i}", True) for i in range(4)]
        assert [r.player_name for r in _interleave_sides(rows)] == ["h0", "h1", "h2", "h3"]


def test_the_window_the_task_attaches_over_is_still_the_documented_one():
    """The one thing above that is genuinely a source fact rather than a
    behaviour: injuries are a 1h product and the attach window is -6h..+2d, and
    the production census (168 events) was taken over exactly that window. If it
    moves, the numbers in this file stop describing what production will do.

    Everything else this file could have asserted by reading source — the Core
    update (gotcha #4), the per-sport dedupe — is asserted against the emitted
    SQL in `TestTheTaskEmitsTheWriteItClaims` instead. A substring guard passes
    or fails on formatting; that one fails on behaviour.
    """
    import inspect

    from app.tasks import statpal_sync

    source = inspect.getsource(statpal_sync._sync_statpal_injuries)
    assert "timedelta(hours=6)" in source
    assert "timedelta(days=2)" in source
