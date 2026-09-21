"""Guards for the ESPN clinch authority on the playoff grid (#7663).

The defect: the grid's only terminal-state input was a venue grade, so on
2026-09-21 it served Boston at 99.7% the day after ESPN recorded its clinch, and
served Minnesota and Detroit a 0.8% playoff path after ESPN had eliminated them.

The trap, which most of this file exists to pin: ESPN's ``clincher`` LETTER
means different things in different sports, and its numeric ``value`` is worse.
"""

import logging

import pytest

from app.utils.espn_clinch import (
    CLINCH_BERTH,
    CLINCH_DIVISION,
    CLINCH_OUT,
    apply_clinch_overlay,
    clinch_claim,
    parse_standings_clinch,
)
from app.utils.playoff_grid import propagate_elimination


class _Col:
    def __init__(self, key, order, depends_on=None, sequential=True):
        self.key = key
        self.order = order
        self.depends_on = depends_on
        self.sequential = sequential


#: MLB's real column shape, including the ``depends_on`` from #7076 (a wild card
#: wins the pennant without winning its division).
MLB_COLUMNS = [
    _Col("make_playoffs", 1),
    _Col("division", 2),
    _Col("pennant", 3, depends_on="make_playoffs"),
    _Col("championship", 4),
]


def _cell(prob, state="live"):
    return {
        "merged_probability": prob,
        "sources": [{"source": "kalshi", "probability": prob}],
        "trend_24h": 0.011,
        "state": state,
    }


def _team(name, **cells):
    return {"name": name, "cells": dict(cells)}


# ---------------------------------------------------------------------------
# The cross-sport table
# ---------------------------------------------------------------------------

#: Read off ESPN on 2026-09-21: MLB 2026, and the 2025 seasons of the other
#: three. ``(description, expected claim)``.
MEASURED_DESCRIPTIONS = {
    "mlb": [
        ("Clinched Division", CLINCH_DIVISION),            # code `x`
        ("Clinched Playoff Berth", CLINCH_BERTH),          # code `z`
        ("Eliminated from Playoff Contention", CLINCH_OUT),  # code `e`, value 4.0
    ],
    "nfl": [
        ("Clinched Division", CLINCH_DIVISION),            # code `z`
        ("Clinched Wild Card", CLINCH_BERTH),              # code `y`
        ("Clinched Division and Bye", CLINCH_DIVISION),    # code `*`
        ("Eliminated from Playoff Contention", CLINCH_OUT),  # code `e`, value 0.0
    ],
    "nba": [
        ("Clinched Playoff Berth", CLINCH_BERTH),          # code `x`
        ("Clinched Division", CLINCH_DIVISION),            # code `y`
        ("Clinched Conference", CLINCH_BERTH),             # code `z`
        ("Clinched Playoff - Won Play-In", CLINCH_BERTH),  # code `xp`
        ("Clinched Play-in Berth", None),                  # code `pb` — NOT in
        ("Eliminated From Playoff", CLINCH_OUT),           # code `e`, value 4.0
    ],
    "nhl": [
        ("Clinched Playoff Berth", CLINCH_BERTH),          # code `x`
        ("Clinched Division Title", CLINCH_DIVISION),      # code `y`
        ("Clinched Best Record in Conference", CLINCH_BERTH),  # code `z`
        ("Clinched Presidents' Trophy (Best Regular-Season Record)", CLINCH_BERTH),
        ("Eliminated from Playoff Contention", CLINCH_OUT),  # code `e`, value 5.0
    ],
}


@pytest.mark.parametrize(
    "league,description,expected",
    [
        (league, desc, exp)
        for league, rows in MEASURED_DESCRIPTIONS.items()
        for desc, exp in rows
    ],
)
def test_every_measured_espn_description_reads_correctly(league, description, expected):
    assert clinch_claim(description) == expected, f"{league}: {description!r}"


def test_the_same_letter_means_different_things_in_different_sports():
    """Why this is keyed on the description — a letter map is wrong twice over.

    ``x`` is a DIVISION in MLB and a BERTH in the NBA and NHL. ``z`` is a BERTH
    in MLB and a DIVISION in the NFL. Any single letter→meaning table is
    therefore wrong on at least two of the four leagues simultaneously, which is
    the whole reason this module reads prose.
    """
    x_in_mlb = clinch_claim("Clinched Division")
    x_in_nba = clinch_claim("Clinched Playoff Berth")
    assert x_in_mlb == CLINCH_DIVISION
    assert x_in_nba == CLINCH_BERTH
    assert x_in_mlb != x_in_nba

    z_in_mlb = clinch_claim("Clinched Playoff Berth")
    z_in_nfl = clinch_claim("Clinched Division")
    assert z_in_mlb == CLINCH_BERTH
    assert z_in_nfl == CLINCH_DIVISION
    assert z_in_mlb != z_in_nfl


def test_a_play_in_berth_is_not_a_playoff_berth():
    """NBA `pb` vs `xp` — one club is in, the other can still miss."""
    assert clinch_claim("Clinched Play-in Berth") is None
    assert clinch_claim("Clinched Playoff - Won Play-In") == CLINCH_BERTH


@pytest.mark.parametrize(
    "description",
    ["", "   ", None, 4.0, "Won the coin toss", "Home Field Advantage", {"a": 1}],
)
def test_an_unrecognised_description_makes_no_claim(description):
    assert clinch_claim(description) is None


# ---------------------------------------------------------------------------
# parse_standings_clinch
# ---------------------------------------------------------------------------


def _entry(team_id, description, wins=80, losses=70):
    stats = [
        {"name": "wins", "value": wins},
        {"name": "losses", "value": losses},
        # Every real ESPN standings entry carries `overall` (`type: total`), so
        # the fixture does too — it is what #7675 reads the record off.
        {"name": "overall", "type": "total", "displayValue": f"{wins}-{losses}"},
    ]
    if description is not None:
        stats.append(
            {"name": "clincher", "value": 4.0, "displayValue": "e",
             "description": description}
        )
    return {"team": {"id": team_id, "displayName": f"Team {team_id}"}, "stats": stats}


def test_parse_walks_nested_groups_and_keys_on_the_string_team_id():
    payload = {
        "children": [
            {"standings": {"entries": [_entry(2, "Clinched Playoff Berth")]}},
            {
                "children": [
                    {"standings": {"entries": [_entry(9, "Eliminated from Playoff Contention")]}}
                ]
            },
        ],
        "standings": {"entries": [_entry(15, "Clinched Division")]},
    }
    assert parse_standings_clinch(payload) == {
        "2": CLINCH_BERTH,
        "9": CLINCH_OUT,
        "15": CLINCH_DIVISION,
    }


def test_an_unplayed_season_yields_no_claims_even_if_it_carries_a_clincher():
    """ESPN's season-less body mislabels its own season, so games played is the check."""
    payload = {
        "standings": {
            "entries": [_entry(2, "Clinched Playoff Berth", wins=0, losses=0)]
        }
    }
    assert parse_standings_clinch(payload) == {}


def test_the_wrong_espn_host_answers_200_with_a_body_that_parses_to_nothing():
    """The measured silent-disable hazard behind `ESPN_STANDINGS_BASE` (gotcha #53).

    `apis/site/v2/.../standings` returns HTTP 200 and this body. It is truthy, so
    a caller reading only the status would publish "nobody has clinched" forever.
    Pinned so the empty result stays visibly empty rather than becoming a claim.
    """
    assert parse_standings_clinch(
        {"fullViewLink": {"text": "Full Standings", "href": "https://espn.com"}}
    ) == {}


@pytest.mark.parametrize("payload", [None, [], "nope", {}])
def test_parse_never_raises_on_a_shape_it_did_not_expect(payload):
    assert parse_standings_clinch(payload) == {}


# ---------------------------------------------------------------------------
# apply_clinch_overlay
# ---------------------------------------------------------------------------


def test_the_production_specimen_boston_and_the_cubs():
    """The pair no threshold can separate (#7663, production 2026-09-21 02:26Z).

    Boston at 99.7% has clinched and the Cubs at 99.5% have not. Two tenths of a
    point apart, opposite answers — so the fix must move exactly one of them.
    """
    boston = _team("Boston Red Sox", make_playoffs=_cell(0.9972), pennant=_cell(0.113))
    cubs = _team("Chicago Cubs", make_playoffs=_cell(0.995), pennant=_cell(0.092))

    written = apply_clinch_overlay(
        [("2", boston), ("16", cubs)],
        {"2": CLINCH_BERTH},  # ESPN carries no clincher for the Cubs
        MLB_COLUMNS,
    )

    assert written == 1
    assert boston["cells"]["make_playoffs"]["state"] == "won"
    assert boston["cells"]["make_playoffs"]["merged_probability"] is None
    assert boston["cells"]["make_playoffs"]["sources"] == []
    assert boston["cells"]["make_playoffs"]["trend_24h"] is None
    # Clinching a berth says nothing about the pennant.
    assert boston["cells"]["pennant"]["merged_probability"] == 0.113

    assert cubs["cells"]["make_playoffs"]["state"] == "live"
    assert cubs["cells"]["make_playoffs"]["merged_probability"] == 0.995


def test_an_eliminated_club_stops_being_priced_all_the_way_down_the_ladder():
    """Minnesota, production 2026-09-21: 0.8% / 0.5% / 0.1% / 0.1% while out."""
    twins = _team(
        "Minnesota Twins",
        make_playoffs=_cell(0.0083),
        division=_cell(0.0055),
        pennant=_cell(0.0005),
        championship=_cell(0.0005),
    )

    written = apply_clinch_overlay([("9", twins)], {"9": CLINCH_OUT}, MLB_COLUMNS)
    # The overlay itself writes only the two columns ESPN speaks to...
    assert written == 2
    # ...and the existing ladder carries it the rest of the way.
    cascaded = propagate_elimination([twins], MLB_COLUMNS)
    assert cascaded == 2

    for key in ("make_playoffs", "division", "pennant", "championship"):
        cell = twins["cells"][key]
        assert cell["state"] == "eliminated", key
        assert cell["merged_probability"] is None, key
        assert cell["trend_24h"] is None, key


def test_a_division_clinch_sets_the_berth_too():
    braves = _team("Atlanta Braves", make_playoffs=_cell(0.98), division=_cell(0.99))
    assert apply_clinch_overlay([("15", braves)], {"15": CLINCH_DIVISION}, MLB_COLUMNS) == 2
    assert braves["cells"]["division"]["state"] == "won"
    assert braves["cells"]["make_playoffs"]["state"] == "won"


def test_a_berth_clinch_does_not_claim_the_division():
    """The Yankees clinched a berth and are six games out of first."""
    yankees = _team("New York Yankees", make_playoffs=_cell(0.99), division=_cell(0.017))
    assert apply_clinch_overlay([("10", yankees)], {"10": CLINCH_BERTH}, MLB_COLUMNS) == 1
    assert yankees["cells"]["make_playoffs"]["state"] == "won"
    assert yankees["cells"]["division"]["merged_probability"] == 0.017


def test_a_venue_grade_is_never_overwritten_and_a_disagreement_is_logged(caplog):
    """A settled market leg is a result; a standings badge is a badge."""
    graded = _team("Someone", make_playoffs=_cell(None, state="won"))
    with caplog.at_level(logging.WARNING, logger="app.utils.espn_clinch"):
        written = apply_clinch_overlay([("1", graded)], {"1": CLINCH_OUT}, MLB_COLUMNS)

    assert written == 0
    assert graded["cells"]["make_playoffs"]["state"] == "won"
    assert "clinch conflict" in caplog.text.lower()


def test_agreement_with_a_venue_grade_is_silent():
    agreed = _team("Someone", make_playoffs=_cell(None, state="won"))
    assert apply_clinch_overlay([("1", agreed)], {"1": CLINCH_BERTH}, MLB_COLUMNS) == 0


def test_an_absent_cell_is_not_invented():
    """Absent is not eliminated, and it is not clinched either (#6442)."""
    sparse = _team("Someone", pennant=_cell(0.02))
    assert apply_clinch_overlay([("1", sparse)], {"1": CLINCH_OUT}, MLB_COLUMNS) == 0
    assert "make_playoffs" not in sparse["cells"]


def test_a_column_the_league_does_not_have_is_not_written():
    no_division = [_Col("make_playoffs", 1), _Col("championship", 2)]
    team = _team("Someone", make_playoffs=_cell(0.4), championship=_cell(0.02))
    assert apply_clinch_overlay([("1", team)], {"1": CLINCH_DIVISION}, no_division) == 1
    assert team["cells"]["make_playoffs"]["state"] == "won"


def test_a_club_with_no_espn_id_or_no_claim_is_untouched():
    a = _team("No id", make_playoffs=_cell(0.4))
    b = _team("No claim", make_playoffs=_cell(0.4))
    assert apply_clinch_overlay([(None, a), ("77", b)], {"1": CLINCH_OUT}, MLB_COLUMNS) == 0
    assert a["cells"]["make_playoffs"]["merged_probability"] == 0.4
    assert b["cells"]["make_playoffs"]["merged_probability"] == 0.4


def test_the_overlay_is_idempotent():
    twins = _team("Minnesota Twins", make_playoffs=_cell(0.0083), division=_cell(0.0055))
    rows, claims = [("9", twins)], {"9": CLINCH_OUT}
    assert apply_clinch_overlay(rows, claims, MLB_COLUMNS) == 2
    assert apply_clinch_overlay(rows, claims, MLB_COLUMNS) == 0


def test_no_claims_means_the_grid_is_returned_exactly_as_it_arrived():
    """ESPN dark or out of season may never change what the page serves."""
    team = _team("Someone", make_playoffs=_cell(0.4), division=_cell(0.3))
    before = {k: dict(v) for k, v in team["cells"].items()}
    assert apply_clinch_overlay([("1", team)], {}, MLB_COLUMNS) == 0
    assert team["cells"] == before


# ---------------------------------------------------------------------------
# The wire: ESPNAPIService.get_standings_reading
# ---------------------------------------------------------------------------

import httpx  # noqa: E402

from app.services.espn_api import (  # noqa: E402
    ESPN_STANDINGS_BASE,
    ESPNAPIService,
    reset_espn_authority_state,
)


@pytest.fixture(autouse=True)
def _fresh_authority_counter():
    reset_espn_authority_state()
    yield
    reset_espn_authority_state()


def _standings_service(handler):
    """A service whose wire is a MockTransport — no test reaches the network.

    Injected at CONSTRUCTION: with proxy env vars set, httpx mounts the proxy
    ahead of a transport swapped on afterwards and the request goes out for real
    (the lesson recorded in `test_espn_authority_dark_045`).
    """
    return ESPNAPIService(
        timeout=1.0, rate_limit_delay=0.0, transport=httpx.MockTransport(handler)
    )


ONE_OF_EACH = {
    "children": [
        {
            "standings": {
                "entries": [
                    _entry(2, "Clinched Playoff Berth"),
                    _entry(9, "Eliminated from Playoff Contention"),
                    _entry(15, "Clinched Division"),
                    _entry(16, None),
                ]
            }
        }
    ]
}


async def test_get_standings_reading_reads_the_right_host_and_parses():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        return httpx.Response(200, json=ONE_OF_EACH)

    svc = _standings_service(handler)
    try:
        reading = await svc.get_standings_reading("baseball_mlb")
    finally:
        await svc.close()

    assert reading["claims"] == {"2": CLINCH_BERTH, "9": CLINCH_OUT, "15": CLINCH_DIVISION}
    # One body, both readings, one request (#7675).
    assert reading["records"] == {"2": "80-70", "9": "80-70", "15": "80-70", "16": "80-70"}
    # The `apis/v2` host, not `apis/site/v2` — the wrong one answers 200 with an
    # empty body and would disable this authority silently and permanently.
    assert seen["url"] == f"{ESPN_STANDINGS_BASE}/baseball/mlb/standings"
    assert "/apis/site/v2/" not in seen["url"]
    # No season parameter: ESPN's own body mislabels the season it is serving.
    assert "season=" not in seen["url"]


async def test_espn_dark_is_none_and_an_empty_answer_is_an_empty_dict():
    """Both arms (gotcha #53) — a guard pinning only the dark arm also passes on
    a client that returns ``None`` for everything."""
    dark = _standings_service(lambda request: httpx.Response(500))
    try:
        assert await dark.get_standings_reading("baseball_mlb") is None
    finally:
        await dark.close()

    empty = _standings_service(lambda request: httpx.Response(200, json={"children": []}))
    try:
        assert await empty.get_standings_reading("baseball_mlb") == {
            "claims": {}, "records": {}
        }
    finally:
        await empty.close()


async def test_a_sport_espn_does_not_map_makes_no_claim_and_no_request():
    called = []

    def handler(request):  # pragma: no cover — asserted not to run
        called.append(request)
        return httpx.Response(200, json=ONE_OF_EACH)

    svc = _standings_service(handler)
    try:
        assert await svc.get_standings_reading("not_a_real_sport_key") == {
            "claims": {}, "records": {}
        }
    finally:
        await svc.close()
    assert called == []


# ---------------------------------------------------------------------------
# The route helper: it may never be able to blank a grid on its own absence
# ---------------------------------------------------------------------------

from app.routes.playoffs import _espn_standings_reading  # noqa: E402


class _Config:
    slug = "mlb"
    sport_keys = ["baseball_mlb"]


class _FakeESPN:
    """Stands in for ESPNAPIService. `result` may be a value or an exception."""

    instances = []

    def __init__(self, result):
        self.result = result
        self.calls = 0
        self.closed = False

    def factory(self):
        def _make(*args, **kwargs):
            _FakeESPN.instances.append(self)
            return self
        return _make

    async def get_standings_reading(self, sport_key):
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result

    async def close(self):
        self.closed = True


class _FakeRedis:
    def __init__(self, stored=None, fail=False):
        self.stored = stored
        self.fail = fail
        self.sets = []

    async def get(self, key):
        if self.fail:
            raise RuntimeError("redis down")
        return self.stored

    async def set(self, key, value, ex=None):
        if self.fail:
            raise RuntimeError("redis down")
        self.sets.append((key, value, ex))


def _patch(monkeypatch, espn, redis):
    monkeypatch.setattr("app.services.espn_api.ESPNAPIService", espn.factory())

    # A PLAIN `def`, because the real `get_async_redis_client` is a plain `def`
    # (#7677). This double used to be `async def` — strictly more permissive
    # than production — so the suite proved something production could not do:
    # the route awaited the factory, raised `TypeError` into its own fail-open
    # `except` on every request, and the clinch cache never engaged once. A
    # double that accepts more than the real thing asserts the wrong contract.
    def _client():
        return redis

    monkeypatch.setattr("app.tasks.redis_state.get_async_redis_client", _client)


#: The shape every failure path returns: both readings present, both empty.
EMPTY = {"claims": {}, "records": {}}


def _reading(claims=None, records=None):
    return {"claims": dict(claims or {}), "records": dict(records or {})}


async def test_espn_dark_yields_no_reading_and_is_not_cached(monkeypatch):
    """Caching a dark read would hold the outage for a quarter hour past its end."""
    espn, redis = _FakeESPN(None), _FakeRedis()
    _patch(monkeypatch, espn, redis)

    assert await _espn_standings_reading(_Config()) == EMPTY
    assert redis.sets == []
    assert espn.closed


async def test_an_espn_that_raises_yields_no_reading_rather_than_a_500(monkeypatch):
    espn, redis = _FakeESPN(RuntimeError("boom")), _FakeRedis()
    _patch(monkeypatch, espn, redis)

    assert await _espn_standings_reading(_Config()) == EMPTY
    assert redis.sets == []


async def test_redis_being_down_does_not_stop_the_read(monkeypatch):
    espn, redis = _FakeESPN(_reading({"2": CLINCH_BERTH})), _FakeRedis(fail=True)
    _patch(monkeypatch, espn, redis)

    assert await _espn_standings_reading(_Config()) == _reading({"2": CLINCH_BERTH})


async def test_an_honest_empty_answer_is_cached_but_a_dark_one_is_not(monkeypatch):
    espn, redis = _FakeESPN(EMPTY), _FakeRedis()
    _patch(monkeypatch, espn, redis)

    assert await _espn_standings_reading(_Config()) == EMPTY
    assert [k for k, _v, _ex in redis.sets] == ["grid:standings:baseball_mlb"]


async def test_a_cached_reading_short_circuits_the_fetch(monkeypatch):
    espn = _FakeESPN(_reading({"9": CLINCH_OUT}))
    redis = _FakeRedis(stored='{"claims": {"2": "berth"}, "records": {"2": "95-60"}}')
    _patch(monkeypatch, espn, redis)

    assert await _espn_standings_reading(_Config()) == _reading(
        {"2": CLINCH_BERTH}, {"2": "95-60"}
    )
    assert espn.calls == 0


async def test_a_cache_entry_from_the_old_claims_only_shape_is_refetched(monkeypatch):
    """#7675 changed the cached VALUE's shape, so it changed the cached KEY.

    Belt and braces: even handed the old shape under the new key, the reading
    is refetched rather than read as `{"331": "out"}.get("claims")` — which
    would be a silently empty reading for the whole 900s TTL.
    """
    espn = _FakeESPN(_reading({"9": CLINCH_OUT}, {"9": "0-2-3"}))
    redis = _FakeRedis(stored='{"2": "berth"}')
    _patch(monkeypatch, espn, redis)

    assert await _espn_standings_reading(_Config()) == _reading(
        {"9": CLINCH_OUT}, {"9": "0-2-3"}
    )
    assert espn.calls == 1


async def test_a_league_with_no_sport_key_makes_no_claim_and_no_call(monkeypatch):
    espn, redis = _FakeESPN(_reading({"2": CLINCH_BERTH})), _FakeRedis()
    _patch(monkeypatch, espn, redis)

    class _Bare:
        slug = "custom"
        sport_keys = []

    assert await _espn_standings_reading(_Bare()) == EMPTY
    assert espn.calls == 0


# ---------------------------------------------------------------------------
# #7677: the shape of the Redis factory, asserted against the real thing
# ---------------------------------------------------------------------------
# The double above is only honest while production's factory really is a plain
# `def`. If someone makes `get_async_redis_client` a coroutine function, every
# test above keeps passing (a `def` double satisfies a `def` call site) while
# the route silently stops caching again — the exact failure #7677 was. So the
# contract is asserted against the real symbol, not against the double.


def test_the_redis_factory_is_not_a_coroutine_function():
    """`get_async_redis_client` is a plain `def`; the route must not await it.

    It is the CLIENT's methods that are awaitable, not the factory. Awaiting
    the factory raises `TypeError: object Redis can't be used in 'await'
    expression`, which a fail-open `except` turns into a cache that is never
    once populated and never once complained.
    """
    import inspect

    from app.tasks.redis_state import get_async_redis_client

    assert inspect.iscoroutinefunction(get_async_redis_client) is False


def test_the_route_does_not_await_the_redis_factory():
    """Read the call site itself: `await get_async_redis_client()` is the bug.

    A behavioural test cannot see this — the `except` swallows it and the
    function returns the same `{}` either way — so the source is the specimen.
    """
    import inspect

    from app.routes import playoffs

    source = inspect.getsource(playoffs._espn_standings_reading)
    assert "await get_async_redis_client()" not in source
    assert "get_async_redis_client()" in source


# ---------------------------------------------------------------------------
# #7675: the record beside the club's name
# ---------------------------------------------------------------------------
# The defect: in EPL matchweek 5 the grid printed Brighton `14-11-12` — a
# COMPLETED PRIOR SEASON, 37 games — beside seventeen clubs printing five.
# Every one of those clubs owns several `teams` rows sharing one `espn_id`, and
# the row `_get_team_metadata` picks by name is not the row the ESPN sync
# updates. The authority settles it.

from app.utils.espn_clinch import (  # noqa: E402
    apply_record_overlay,
    parse_standings_records,
    season_record,
)


#: Read off ESPN's `apis/v2` standings on 2026-09-21, same minute as the grids:
#: `(league, overall.displayValue, expected served record)`.
MEASURED_OVERALL = [
    ("mlb", "95-60", "95-60"),          # W-L
    ("nfl", "2-0", "2-0"),              # W-L
    ("epl", "3-1-1", "3-1-1"),          # W-D-L
    ("nhl", "2-0-0, 4 PTS", "2-0-0"),   # W-L-OTL + a POINTS SUFFIX
    ("nba", "0-0", "0-0"),              # preseason; the played gate drops it
]


@pytest.mark.parametrize("league,display_value,expected", MEASURED_OVERALL)
def test_every_measured_overall_value_reads_correctly(league, display_value, expected):
    assert season_record(display_value) == expected, f"{league}: {display_value!r}"


def test_the_nhl_points_suffix_is_cut_rather_than_printed():
    """The one league whose `overall` is not already a record.

    `2-0-0, 4 PTS` served raw would print exactly that in a column eighteen
    other rows fill with `2-0-0`. This is the reason the value is trimmed at
    all, so it is pinned on its own rather than only inside the table.
    """
    assert season_record("2-0-0, 4 PTS") == "2-0-0"
    assert "PTS" not in (season_record("2-0-0, 4 PTS") or "")


@pytest.mark.parametrize(
    "display_value",
    ["", "   ", None, 4.0, {"a": 1}, "E-10", "2-0-0 (4 PTS)", "--", "2", "1st", "-"],
)
def test_a_shape_no_league_publishes_makes_no_claim(display_value):
    """No claim beats a wrong one: the record column keeps `current_record`."""
    assert season_record(display_value) is None


def _rec_entry(team_id, overall, wins=3, losses=1, ties=1):
    return {
        "team": {"id": team_id, "displayName": f"Team {team_id}"},
        "stats": [
            {"name": "wins", "value": wins},
            {"name": "losses", "value": losses},
            {"name": "ties", "value": ties},
            {"name": "overall", "type": "total", "displayValue": overall},
        ],
    }


def test_records_parse_walks_nested_groups_and_keys_on_the_string_team_id():
    payload = {
        "children": [
            {"standings": {"entries": [_rec_entry(331, "3-1-1")]}},
            {"children": [{"standings": {"entries": [_rec_entry(349, "0-3-2")]}}]},
        ],
        "standings": {"entries": [_rec_entry(367, "0-2-3")]},
    }
    assert parse_standings_records(payload) == {
        "331": "3-1-1",
        "349": "0-3-2",
        "367": "0-2-3",
    }


def test_an_unplayed_season_yields_no_record_so_the_nba_grid_is_untouched():
    """29 of 30 NBA clubs sat at `0-0` in preseason on the measured day.

    Without the played gate every one of them would overwrite a real record
    with `0-0` the moment ESPN publishes an empty table.
    """
    payload = {
        "standings": {"entries": [_rec_entry(1, "0-0", wins=0, losses=0, ties=0)]}
    }
    assert parse_standings_records(payload) == {}


def test_an_entry_with_no_overall_stat_makes_no_record_claim():
    payload = {
        "standings": {
            "entries": [
                {
                    "team": {"id": 5, "displayName": "Team 5"},
                    "stats": [{"name": "wins", "value": 3},
                              {"name": "losses", "value": 1}],
                }
            ]
        }
    }
    assert parse_standings_records(payload) == {}


@pytest.mark.parametrize("payload", [None, [], "nope", {}])
def test_records_parse_never_raises_on_a_shape_it_did_not_expect(payload):
    assert parse_standings_records(payload) == {}


def test_the_wrong_espn_host_yields_no_records_either():
    assert parse_standings_records(
        {"fullViewLink": {"text": "Full Standings", "href": "https://espn.com"}}
    ) == {}


# --- the overlay -----------------------------------------------------------

#: The three specimens from the production LOOK, with the sibling row that held
#: the right answer all along: `(espn_id, club, served, ESPN same-minute)`.
EPL_SPECIMENS = [
    ("331", "Brighton & Hove Albion", "14-11-12", "3-1-1"),
    ("349", "Bournemouth", "12-16-7", "0-3-2"),
    ("367", "Tottenham Hotspur", "10-11-17", "0-2-3"),
]


def test_the_three_prior_season_records_are_corrected():
    rows = [(eid, {"name": name, "record": served}) for eid, name, served, _ in EPL_SPECIMENS]
    records = {eid: espn for eid, _n, _s, espn in EPL_SPECIMENS}

    assert apply_record_overlay(rows, records) == 3
    assert [row["record"] for _eid, row in rows] == ["3-1-1", "0-3-2", "0-2-3"]


def test_a_corrected_record_implies_the_matchweek_the_other_clubs_are_playing():
    """The reader's actual complaint: 37 games in a 5-game season.

    Asserting the VALUE alone would pass on any string; what made this a defect
    is the game count, so the game count is what is asserted.
    """
    rows = [("331", {"name": "Brighton & Hove Albion", "record": "14-11-12"})]
    assert sum(int(p) for p in rows[0][1]["record"].split("-")) == 37

    apply_record_overlay(rows, {"331": "3-1-1"})
    assert sum(int(p) for p in rows[0][1]["record"].split("-")) == 5


def test_a_club_with_no_espn_id_keeps_what_it_had():
    """Hull City and Coventry City have `espn_id IS NULL` (#7676).

    ESPN has records for both, but the join is on the id and never on a name,
    so they are left exactly as found rather than matched by text.
    """
    rows = [(None, {"name": "Hull City", "record": None}),
            ("", {"name": "Coventry City", "record": "1-0-4"})]

    assert apply_record_overlay(rows, {"306": "2-2-1", "388": "1-0-4"}) == 0
    assert rows[0][1]["record"] is None
    assert rows[1][1]["record"] == "1-0-4"


def test_a_club_espn_makes_no_claim_about_keeps_what_it_had():
    rows = [("999", {"name": "Someone", "record": "7-7"})]
    assert apply_record_overlay(rows, {"331": "3-1-1"}) == 0
    assert rows[0][1]["record"] == "7-7"


def test_an_already_correct_record_is_not_counted_as_a_correction():
    """30 of 30 MLB rows were already identical on the measured day.

    If those counted, the log line would report 30 corrections per rebuild on a
    league where nothing changed, and the count would stop meaning anything.
    """
    rows = [("30", {"name": "Tampa Bay Rays", "record": "95-60"})]
    assert apply_record_overlay(rows, {"30": "95-60"}) == 0
    assert rows[0][1]["record"] == "95-60"


def test_an_empty_authority_changes_nothing():
    rows = [(eid, {"name": name, "record": served}) for eid, name, served, _ in EPL_SPECIMENS]
    before = [row["record"] for _e, row in rows]

    assert apply_record_overlay(rows, {}) == 0
    assert [row["record"] for _e, row in rows] == before


def test_an_empty_espn_id_never_joins_an_empty_keyed_authority_entry():
    """The falsy-`espn_id` guard, on the only input that can reach it.

    `parse_standings_records` only skips an entry whose id is `None`, so an
    ESPN entry carrying `"id": ""` becomes the key `""`. A club whose own
    `espn_id` is `""` would then join it — two rows with no identity matching
    each other and the club taking a stranger's record. `str(None)` is
    `"None"`, so a NULL id cannot reach this; the empty string is the specimen
    that can, and without the guard this test takes `9-9-9`.
    """
    rows = [("", {"name": "Coventry City", "record": "1-0-4"})]

    assert apply_record_overlay(rows, {"": "9-9-9"}) == 0
    assert rows[0][1]["record"] == "1-0-4"


# ---------------------------------------------------------------------------
# #7675: a PRESEASON table is not an authority on anything
# ---------------------------------------------------------------------------
# The same trap as the clinch letter, one field over: the standings node's
# `seasonType` is an INTEGER whose meaning is per-sport. `1` is Preseason in
# the NHL and the NBA, and is the whole live Premier League season in England.

from app.utils.espn_clinch import is_preseason_standings  # noqa: E402


def _body(season_type, types, entries=()):
    return {
        "standings": {"seasonType": season_type, "entries": list(entries)},
        "seasons": [{"year": 2027, "types": types}],
    }


#: Read off ESPN on 2026-09-21: `(league, seasonType, types, is preseason)`.
MEASURED_SEASON_TYPES = [
    ("nhl", 1, [{"id": "1", "name": "Preseason", "abbreviation": "pre"},
                {"id": "2", "name": "Regular Season", "abbreviation": "reg"}], True),
    ("nba", 1, [{"id": "1", "name": "Preseason", "abbreviation": "pre"},
                {"id": "2", "name": "Regular Season", "abbreviation": "reg"}], True),
    ("mlb", 2, [{"id": "1", "name": "Spring Training", "abbreviation": "pre"},
                {"id": "2", "name": "Regular Season", "abbreviation": "reg"}], False),
    ("nfl", 2, [{"id": "1", "name": "Preseason", "abbreviation": "pre"},
                {"id": "2", "name": "Regular Season", "abbreviation": "reg"}], False),
    ("epl", 1, [{"id": "1", "name": "2026-27 English Premier League",
                 "abbreviation": "2026-27 English Premier League"}], False),
]


@pytest.mark.parametrize("league,season_type,types,expected", MEASURED_SEASON_TYPES)
def test_every_measured_season_type_reads_correctly(league, season_type, types, expected):
    assert is_preseason_standings(_body(season_type, types)) is expected, league


def test_season_type_1_is_preseason_in_the_nhl_and_the_live_table_in_england():
    """Why the id is resolved through the body's own table instead of compared.

    Both bodies say `seasonType: 1`. One is the NHL's exhibition schedule, the
    other is the Premier League in matchweek 5. Any numeric test serves NHL
    preseason records or drops the EPL rows this ship exists to fix — the exact
    shape of the letter trap that `clinch_claim` exists to avoid.
    """
    nhl = _body(1, [{"id": "1", "name": "Preseason", "abbreviation": "pre"}])
    epl = _body(1, [{"id": "1", "name": "2026-27 English Premier League",
                     "abbreviation": "2026-27 English Premier League"}])

    assert is_preseason_standings(nhl) is True
    assert is_preseason_standings(epl) is False


def test_mlbs_preseason_is_named_spring_training_not_preseason():
    """The NAME differs by sport, so one spelling is not enough.

    A gate keyed only on the word "preseason" reads MLB's Spring Training table
    as a regular season — and a spring-training record (`10-18-1`) is the
    documented defect in `_get_team_metadata`.
    """
    body = _body(1, [{"id": "1", "name": "Spring Training", "abbreviation": "pre"}])
    assert is_preseason_standings(body) is True


def test_a_preseason_name_is_caught_even_when_the_abbreviation_is_not_pre():
    """The name backstop, for a sport whose abbreviation we have not measured."""
    body = _body(1, [{"id": "1", "name": "Exhibition", "abbreviation": "exh"}])
    assert is_preseason_standings(body) is True


def test_the_pre_abbreviation_is_caught_even_when_the_name_is_unrecognised():
    """The other half of the pair — the case ONLY the abbreviation can catch.

    Both measured names ("Preseason", "Spring Training") are in the name list,
    so the abbreviation branch is unreachable through them and would be dead
    code justified by a comment. A league that calls its warm-up competition
    something we have never read, while still abbreviating it `pre`, is the
    specimen that makes the branch load-bearing.
    """
    body = _body(1, [{"id": "1", "name": "Torneo de Verano", "abbreviation": "pre"}])
    assert is_preseason_standings(body) is True


@pytest.mark.parametrize(
    "payload",
    [
        None, [], "nope", {},
        {"standings": {"seasonType": 1}, "seasons": []},
        {"standings": {"seasonType": 1}, "seasons": [{"types": []}]},
        {"standings": {"seasonType": 9}, "seasons": [{"types": [{"id": "1",
         "name": "Preseason", "abbreviation": "pre"}]}]},
        {"seasons": [{"types": [{"id": "1", "name": "Preseason",
         "abbreviation": "pre"}]}]},
    ],
)
def test_an_unresolvable_season_type_fails_open(payload):
    """Losing the authority on a body we merely could not label costs more.

    Every one of these proceeds to the reading rather than refusing it.
    """
    assert is_preseason_standings(payload) is False


async def test_a_preseason_body_yields_no_reading_at_all(monkeypatch):
    """Both readings, not just the record: nobody clinches in the preseason."""
    body = _body(
        1,
        [{"id": "1", "name": "Preseason", "abbreviation": "pre"}],
        entries=[_entry(2, "Clinched Playoff Berth")],
    )
    svc = _standings_service(lambda request: httpx.Response(200, json=body))
    try:
        assert await svc.get_standings_reading("icehockey_nhl") == {
            "claims": {}, "records": {}
        }
    finally:
        await svc.close()


async def test_a_regular_season_body_with_the_same_entries_does_yield_a_reading():
    """The control: identical entries, season type 2, and the reading lands.

    Without this the preseason test above would pass on a client that returned
    nothing for everything.
    """
    body = _body(
        2,
        [{"id": "1", "name": "Preseason", "abbreviation": "pre"},
         {"id": "2", "name": "Regular Season", "abbreviation": "reg"}],
        entries=[_entry(2, "Clinched Playoff Berth")],
    )
    svc = _standings_service(lambda request: httpx.Response(200, json=body))
    try:
        reading = await svc.get_standings_reading("icehockey_nhl")
    finally:
        await svc.close()

    assert reading["claims"] == {"2": CLINCH_BERTH}
    assert reading["records"] == {"2": "80-70"}
