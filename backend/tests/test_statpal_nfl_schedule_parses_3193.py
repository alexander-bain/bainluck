"""NFL's hourly discovery beat reads the games in its own payload (#3193).

`sync-statpal-schedules-nfl` is registered on the beat, runs hourly, and
reported success for months while creating **nothing**: `_sync_statpal_schedules`
-> `get_fixtures("nfl")` -> `_parse_fixtures` returned 0 rows on NFL's own
recorded season-schedule, which holds 17 games. MLB, NBA and NHL parsed every
game in theirs. NFL was the only failure and it was total.

Gotcha #53 is why nobody saw it: an empty result is the same shape as "no games
this hour", so a beat that discovers nothing and a beat with nothing to discover
were indistinguishable from outside.

**The gap was that no test drove the real path end to end.** The parser had
coverage; the SERVICE METHOD THE TASK CALLS did not. So these tests drive
`get_fixtures`, the exact method `_sync_statpal_schedules` calls, with only the
HTTP fetch replaced — the endpoint selection, the empty-data branch and the
parse all run as they do in production.

Scope is NFL. Tennis shows the same symptom on the same function from two
different causes, and it is deliberately NOT fixed here: `STATPAL_SPORT_MAPPING`
carries `tennis_atp`/`tennis_wta` while the tennis linker anchors under
`tennis_atp_us_open`/`tennis_wta_us_open`, and Step 1 of the registry is
sport-scoped (D55/#2879). Teaching the parser tennis before those keys are
reconciled would make every US Open match a second time, hourly, under a
non-anchoring claim. Measured and filed on #3193; the split is lane1's to rule
on because it is an identity question (D39/#2693).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.statpal_api import StatPalAPIService

FIXTURES = Path(__file__).parent / "fixtures"
NFL_SCHEDULE = FIXTURES / "statpal_nfl_season_schedule_20260903.json"

#: What the authority lane's own stamper reads out of the same capture, and what
#: the raw node count comes to. Named here so a fixture edited down to fewer
#: games is a failure rather than a quieter pass.
NFL_GAMES_IN_CAPTURE = 17


def _payload() -> dict:
    return json.loads(NFL_SCHEDULE.read_text())


def _service_serving(payload) -> tuple[StatPalAPIService, list]:
    """The real service with exactly one thing replaced: the network.

    A REAL `StatPalAPIService()`, not a subclass and not `__new__`, so the
    endpoint table, `_base_url` and every branch above the parse are the shipped
    ones. Only `_get` is swapped — the defect lived in what the task's own call
    CHAIN did with the response, and a test that starts at the parser cannot see
    an endpoint chosen wrongly or an early return above it.

    (`__init__` needs no key: it warns and carries on, which is what the repo's
    other StatPal tests rely on too.)

    Returns the service and the list its `_get` records calls into, so a test
    can assert a fetch actually happened rather than trusting an empty result.
    """
    service = StatPalAPIService()
    calls: list = []

    async def fake_get(sport, endpoint, params=None):
        calls.append((sport, endpoint, params))
        return payload

    service._get = fake_get
    return service, calls


@pytest.mark.asyncio
async def test_the_task_s_own_call_reads_every_nfl_game_in_the_real_payload():
    """`get_fixtures("nfl")` — the method the hourly beat calls — on the capture.

    The number is compared against a count of the game nodes rather than only
    against a literal, because the failure mode with teeth here is a PARTIAL
    read: NFL nests `stage -> week -> matches -> match` and each of those four
    levels collapses to a bare dict when it holds one child. A walker that
    handles the list arm alone reads Week 1's thirteen games and silently drops
    Pre Season's one.
    """
    service, calls = _service_serving(_payload())
    fixtures = await service.get_fixtures("nfl")

    assert len(fixtures) == NFL_GAMES_IN_CAPTURE, (
        f"the NFL schedule path read {len(fixtures)} of {NFL_GAMES_IN_CAPTURE} "
        "games. This is the call the hourly beat makes; whatever it cannot see, "
        "an ESPN outage hides (#2867 step 7)."
    )
    assert calls, "get_fixtures returned without fetching anything"


@pytest.mark.asyncio
async def test_every_fixture_the_beat_reads_carries_a_start_time():
    """A fixture with no clock is invisible to the creating path.

    `_sync_statpal_schedules` sends a fixture to `find_or_create_event` only
    when `fixture.start_time > now`; with no start_time it takes the PAST branch
    and enriches an existing row or skips. So a parser that reaches all 17 games
    and loses their clocks discovers exactly nothing while every count in sight
    reads healthy — the same silent zero one level down.

    NFL records carry `datetime_utc`, which `_parse_single_fixture` prefers over
    the `date`+`time` pair precisely because that pair is venue-local on some
    endpoints and UTC on others.
    """
    service, _ = _service_serving(_payload())
    fixtures = await service.get_fixtures("nfl")

    missing = [f"{f.home_team} v {f.away_team}" for f in fixtures if not f.start_time]
    assert not missing, f"parsed with no start_time, so uncreatable: {missing}"


@pytest.mark.asyncio
async def test_both_stages_reach_the_beat_not_just_the_one_served_as_a_list():
    """The one-or-many collapse, asserted where it actually bites.

    The capture holds two stages: Pre Season serves its single week's `match` as
    a bare **dict**, Regular Season's Sunday group serves thirteen as a **list**.
    Both shapes in one response is the whole difficulty, and a count alone can
    be satisfied by reading one stage twice.
    """
    service, _ = _service_serving(_payload())
    fixtures = await service.get_fixtures("nfl")

    ids = {f.fixture_id for f in fixtures}
    # The Pre Season singleton (Hall of Fame Weekend) and a Regular Season game
    # from the 13-strong Sunday list.
    assert "280493" in ids, (
        "the Pre Season game is missing — its `match` is served as a bare dict, "
        "so a walker that only handles the list arm drops it"
    )
    assert "280445" in ids, "a Regular Season game from the Sunday list is missing"
    assert len(ids) == len(fixtures), "two fixtures parsed under one id"


@pytest.mark.asyncio
async def test_no_fixture_is_the_response_envelope_wearing_a_game_s_clothes():
    """The old failure did not return empty — it returned the whole payload.

    `_extract_match_items` fell through to a catch-all that hands back
    `[data]`, so NFL's response arrived at `_parse_single_fixture` as ONE item
    and was dropped only because an envelope has no `home`. "Returned something"
    and "returned matches" are not the same thing, and a guard asserting
    emptiness here would have read false while sounding right.
    """
    service, _ = _service_serving(_payload())
    fixtures = await service.get_fixtures("nfl")

    for f in fixtures:
        assert f.home_team and f.away_team, (
            f"a fixture parsed with no teams: {f!r} — the envelope, or a node "
            "that is not a game, reached the fixture list"
        )


@pytest.mark.asyncio
async def test_an_empty_response_still_yields_nothing_rather_than_an_envelope():
    """The widened walk must not turn a dead read into phantom fixtures.

    A parser taught new shapes can start finding "games" in responses that hold
    none, which is worse than the zero it replaced: the beat would create rows
    out of an outage.
    """
    for empty in ({}, {"scores": {}}, {"scores": {"tournament": {}}}, None):
        service, _ = _service_serving(empty)
        assert await service.get_fixtures("nfl") == [], (
            f"{empty!r} produced fixtures"
        )


def test_a_missing_level_ends_the_walk_rather_than_becoming_a_none_child():
    """`_as_list`'s own contract, tested where it is decidable.

    Surfaced by mutation: making `_as_list(None)` return `[None]` changed no
    parse result, because every level of the walk guards `isinstance(x, dict)`
    and a `None` is dropped one line later. The behaviour is real and documented
    all the same, so it is asserted on the helper directly rather than left as a
    claim in a docstring that no payload can reach.

    The distinction matters for the next caller, not this one: a walker that
    trusts `_as_list` to mean "the children, if any" and skips its own isinstance
    check would iterate a phantom child on every absent level.
    """
    from app.services.statpal_api import _as_list

    assert _as_list(None) == []
    assert _as_list([]) == []
    assert _as_list({"a": 1}) == [{"a": 1}]
    assert _as_list([{"a": 1}, {"b": 2}]) == [{"a": 1}, {"b": 2}]


def test_the_other_v1_sports_are_untouched_by_the_nfl_nesting():
    """NFL's stage walk is additive — the sports that already worked still do.

    MLB, NBA and NHL parse from `tournament.match` / `tournament.week` and have
    no `stage`. Pinned because all four share one function, and the tier this
    file derives would happily report four sports capable while one of the three
    that already worked had quietly started reading fewer games.
    """
    service = StatPalAPIService()
    expected = {
        "statpal_mlb_season_schedule_20260904.json": ("mlb", 15),
        "statpal_nba_season_schedule_20260903.json": ("nba", 9),
        "statpal_nba_season_schedule_20260904.json": ("nba", 9),
        "statpal_nhl_season_schedule_20260903.json": ("nhl", 9),
        "statpal_nhl_season_schedule_20260904.json": ("nhl", 16),
    }
    for name, (sport, count) in expected.items():
        payload = json.loads((FIXTURES / name).read_text())
        parsed = service._parse_fixtures(payload, sport)
        assert len(parsed) == count, (
            f"{name}: {sport} now parses {len(parsed)}, was {count}. The NFL "
            "nesting was supposed to be additive."
        )
