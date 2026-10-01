"""#10103 (for #9483): an NFL prop keeps the athlete, team and picture of the
game it was asked about, not today's roster.

THE DEFECT CLASS. Step 10 of `_build_game_markets` gave every player prop its
side (`player_team`) and picture (`player_headshot`) by looking the name up in
TODAY's `teams.roster_players`. A finished game's page therefore follows the
player wherever he goes next: trade him after the game and the old game shows
him in the new team's colours, with whatever picture the new roster carries.

THE BRIDGE. ESPN's box for THIS game already records which team each athlete
played for, by ESPN id, with his picture. `get_event_context` now keeps that as
`box_score_player_identities`. The three box writers store it as
`box_score_data.player_identities` beside the unchanged numeric `players`, and
step 10b resolves a prop's COMPLETE subject against it. Provider identity
(`espn:athlete:<id>`, `espn:team:<id>`) rides the prop row. The roster pass stays
as the fallback for everything the bridge cannot vouch for.

FIXTURES. `espn_summary_nfl_401872660_bills_at_texans_10103.json` is SOURCE-
RETAINED: ESPN's summary for event 401872660, our 14780141, trimmed but not
edited (its `_provenance` key says what was kept). Everything marked
REPRESENTATIVE below is constructed to exercise a refusal (a second athlete with
a shared name, a post-game transfer on the roster, a swapped provider id). None
is a claim about production.

Golden: `fixtures/nfl_prop_identity_payload_10103.json` is the served prop
subset this file produces end to end. The frontend's
`__tests__/nflPropIdentityReachesTheCard10103.test.ts` feeds the same file to
`groupPlayerProps`, the card the event page renders. One file, both halves.
"""
from __future__ import annotations

import contextlib
import copy
import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw
from tests.integration.test_route_events_seeded import (
    _make_event,
    _make_event_detail_session,
    _make_futures_market,
    _make_outcome,
)

FIXTURES = Path(__file__).parent / "fixtures"
SUMMARY = json.loads(
    (FIXTURES / "espn_summary_nfl_401872660_bills_at_texans_10103.json").read_text()
)
GOLDEN_PATH = FIXTURES / "nfl_prop_identity_payload_10103.json"

EVENT_ID = 14780141          # Bills @ Texans, our row
ESPN_EVENT_ID = "401872660"  # its ESPN anchor
HOME_TEAM_ID, AWAY_TEAM_ID = 563, 538          # Houston Texans, Buffalo Bills
HOME_ESPN, AWAY_ESPN = "34", "2"               # their stored Team.espn_id
NFL = "americanfootball_nfl"

# Source-retained ids, read off the fixture (and so off ESPN).
STROUD = ("C.J. Stroud", "4432577", "34", "home")
MONTGOMERY = ("David Montgomery", "4035538", "34", "home")
ALLEN = ("Josh Allen", "3918298", "2", "away")
HEADSHOT = "https://a.espncdn.com/i/headshots/nfl/players/full/{}.png"

PASS_NAME = "Buffalo vs Houston: Passing Yards"
RUSH_NAME = "Buffalo vs Houston: Rushing Yards"
REC_NAME = "Buffalo vs Houston: Receiving Yards"


def _summary():
    return copy.deepcopy(SUMMARY)


async def _context(sport_key=NFL, summary=None):
    """The real `get_event_context` over the fixture: nothing below is hand-built."""
    from app.services.espn_api import ESPNAPIService

    svc = ESPNAPIService()
    try:
        with patch.object(svc, "_get", AsyncMock(return_value=summary or _summary())):
            return await svc.get_event_context(sport_key, ESPN_EVENT_ID)
    finally:
        await svc.close()


# ═══════════════════════════════════════════════════════════════════════════
# 1. Ingestion: the identities ESPN gave, beside an unchanged numeric box
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_the_context_keeps_each_athletes_game_identity():
    ctx = await _context()
    ids = ctx["box_score_player_identities"]
    by_name = {e["name"]: e for e in ids}
    for name, athlete_id, team_id, side in (STROUD, MONTGOMERY, ALLEN):
        assert by_name[name] == {
            "name": name,
            "athlete_id": athlete_id,
            "team_id": team_id,
            "side": side,
            "headshot": HEADSHOT.format(athlete_id),
        }
    # One entry per athlete, although each appears in several stat groups.
    assert len(ids) == len({(e["athlete_id"], e["team_id"]) for e in ids}) == 22


@pytest.mark.asyncio
async def test_STATS_SHAPE_CONTROL_the_numeric_box_is_exactly_what_it_was():
    """The new key is a sibling: `box_score` is still the name→numbers dict the
    grader and every client read, with no id, team or picture in it."""
    from app.services.espn_api import ESPNAPIService

    ctx = await _context()
    assert ctx["box_score"] == ESPNAPIService()._parse_boxscore(_summary())
    stroud = ctx["box_score"]["C.J. Stroud"]
    assert all(isinstance(v, float) for v in stroud.values())
    assert not {"athlete_id", "team_id", "headshot", "side"} & set(stroud)


@pytest.mark.asyncio
async def test_NON_NFL_CONTROL_another_sport_stores_no_identities():
    ctx = await _context(sport_key="basketball_nba")
    assert ctx["box_score_player_identities"] == []


def test_a_header_that_does_not_name_the_team_leaves_its_side_unknown():
    from app.services.espn_api import ESPNAPIService

    s = _summary()
    s["header"]["competitions"][0]["competitors"] = [
        c for c in s["header"]["competitions"][0]["competitors"] if c["homeAway"] == "home"
    ]
    ids = ESPNAPIService._parse_boxscore_player_identities(s)
    assert {e["side"] for e in ids if e["team_id"] == AWAY_ESPN} == {None}
    assert {e["side"] for e in ids if e["team_id"] == HOME_ESPN} == {"home"}


# ═══════════════════════════════════════════════════════════════════════════
# 2. Storage: all three box writers carry the sibling map
# ═══════════════════════════════════════════════════════════════════════════


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _RecordingSession:
    def __init__(self, events):
        self._events = events
        self.writes: list = []

    async def execute(self, statement, params=None):
        if params is None:
            return _FakeResult(self._events)
        self.writes.append((statement, params))
        return _FakeResult([])

    def begin_nested(self):
        return contextlib.nullcontext()


def _service(context):
    service = MagicMock()
    service.get_event_context = AsyncMock(return_value=context)
    service.close = AsyncMock()
    return service


def _box_event(status, box_score_data=None, sport_key=NFL):
    event = MagicMock()
    event.id = EVENT_ID
    event.espn_id = ESPN_EVENT_ID
    event.status = status
    event.box_score_data = box_score_data
    event.home_score, event.away_score = 27, 24
    event.sport = MagicMock()
    event.sport.key = sport_key
    return event


async def _settled_write(context, event=None):
    from app.utils import espn_helpers

    session = _RecordingSession([event or _box_event("completed")])
    with patch("app.services.espn_api.ESPNAPIService", return_value=_service(context)):
        await espn_helpers.fetch_completed_box_scores(session, {})
    assert len(session.writes) == 1
    return json.loads(session.writes[0][1]["bsd"])


async def _live_write(context):
    from app.utils import espn_helpers

    session = _RecordingSession([_box_event("live")])
    with patch("app.services.espn_api.ESPNAPIService", return_value=_service(context)):
        await espn_helpers.fetch_live_box_scores(session, {})
    assert len(session.writes) == 1
    return json.loads(session.writes[0][1]["bsd"])


async def _backfill_write(context):
    from app.tasks import espn_sync

    event = _box_event("completed")

    @asynccontextmanager
    async def _session():
        yield _RecordingSession([event])

    with patch.object(espn_sync, "get_task_session", _session), patch(
        "app.services.espn_api.ESPNAPIService", return_value=_service(context)
    ), patch("asyncio.sleep", AsyncMock()):
        stats = await espn_sync._backfill_box_scores(limit=1)
    assert stats["fetched"] == 1, stats
    return event.box_score_data


@pytest.mark.asyncio
@pytest.mark.parametrize("writer", [_settled_write, _live_write, _backfill_write])
async def test_every_box_writer_stores_the_identities_beside_the_numbers(writer):
    ctx = await _context()
    stored = await writer(ctx)
    assert stored["player_identities"] == ctx["box_score_player_identities"]
    assert stored["players"] == ctx["box_score"]
    assert stored["source"] == "espn"


@pytest.mark.asyncio
@pytest.mark.parametrize("writer", [_settled_write, _live_write, _backfill_write])
async def test_NON_NFL_CONTROL_no_writer_adds_the_key_without_identities(writer):
    ctx = await _context(sport_key="basketball_nba")
    stored = await writer(ctx)
    assert "player_identities" not in stored
    assert stored["players"] == ctx["box_score"]


@pytest.mark.asyncio
async def test_the_settled_rewrite_does_not_wipe_what_the_live_pass_stored():
    """The settled pass REPLACES the whole box every time it asks. Had it not
    carried the key, the first settled fetch after full time would erase the map
    and a finished game's page could never read it."""
    ctx = await _context()
    live_box = await _live_write(ctx)
    settled = await _settled_write(ctx, event=_box_event("completed", live_box))
    assert "live" not in settled
    assert settled["player_identities"] == live_box["player_identities"]


@pytest.mark.asyncio
async def test_an_empty_settled_answer_keeps_the_stored_identities():
    ctx = await _context()
    live_box = await _live_write(ctx)
    settled = await _settled_write(
        {"box_score": {}, "scoring_plays": [], "scores": {}},
        event=_box_event("completed", live_box),
    )
    assert settled["live"] is False
    assert settled["player_identities"] == live_box["player_identities"]


# ═══════════════════════════════════════════════════════════════════════════
# 3. The pure resolver: unique, provider-consistent, complete names only
# ═══════════════════════════════════════════════════════════════════════════


async def _stored_box():
    """The box exactly as the settled writer stores it for this game."""
    return await _settled_write(await _context())


@pytest.mark.asyncio
async def test_the_index_resolves_a_unique_name_to_its_game_identity():
    from app.routes.events import _game_player_identity_index

    index = _game_player_identity_index(await _stored_box(), HOME_ESPN, AWAY_ESPN)
    assert index["c.j. stroud"] == {
        "athlete_id": "4432577", "team_id": "34", "side": "home",
        "headshot": HEADSHOT.format("4432577"),
    }
    assert index["josh allen"]["side"] == "away"


@pytest.mark.asyncio
async def test_DUPLICATE_CONTROL_two_athletes_sharing_a_name_refuse_that_name():
    """REPRESENTATIVE: a second "Josh Allen" (ESPN id 3052587 is a real athlete
    of that name, but he did not play in this game) placed on the Texans."""
    from app.routes.events import _game_player_identity_index

    box = await _stored_box()
    box["player_identities"].append({
        "name": "Josh Allen", "athlete_id": "3052587", "team_id": "34", "side": "home",
    })
    index = _game_player_identity_index(box, HOME_ESPN, AWAY_ESPN)
    assert "josh allen" not in index
    assert "c.j. stroud" in index  # the refusal is per name


@pytest.mark.asyncio
async def test_a_malformed_twin_refuses_its_name_instead_of_being_skipped():
    from app.routes.events import _game_player_identity_index

    box = await _stored_box()
    box["player_identities"].append({"name": "Josh Allen", "athlete_id": "", "team_id": "34"})
    assert "josh allen" not in _game_player_identity_index(box, HOME_ESPN, AWAY_ESPN)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "home_espn, away_espn",
    [
        (AWAY_ESPN, HOME_ESPN),  # our home/away is ESPN's swapped
        ("99", AWAY_ESPN),       # our home team is not one ESPN boxed
        (None, AWAY_ESPN),       # we hold no provider id for a side
        (HOME_ESPN, HOME_ESPN),  # one id for both sides
    ],
)
async def test_PROVIDER_MISMATCH_CONTROL_refuses_the_whole_map(home_espn, away_espn):
    from app.routes.events import _game_player_identity_index

    assert _game_player_identity_index(await _stored_box(), home_espn, away_espn) == {}


def test_a_box_that_is_not_espns_or_carries_no_map_resolves_nothing():
    from app.routes.events import _game_player_identity_index

    assert _game_player_identity_index(None, HOME_ESPN, AWAY_ESPN) == {}
    assert _game_player_identity_index({"source": "espn", "players": {}}, HOME_ESPN, AWAY_ESPN) == {}
    assert _game_player_identity_index(
        {"source": "statpal", "player_identities": [{"name": "C.J. Stroud", "athlete_id": "4432577",
                                                      "team_id": "34", "side": "home"}]},
        HOME_ESPN, AWAY_ESPN,
    ) == {}


# ═══════════════════════════════════════════════════════════════════════════
# 4. The served payload: /api/events/{id}/game-markets
# ═══════════════════════════════════════════════════════════════════════════

# REPRESENTATIVE TRANSFER: today's roster has Montgomery on the Bills with
# another picture, as it would after a post-game trade. The roster pass reads
# this; the game's own box must win.
TRANSFERRED_HEADSHOT = "https://example.invalid/roster-today/montgomery.png"
TODAYS_ROSTERS = {
    "Houston Texans": [
        {"name": "C.J. Stroud", "headshot": HEADSHOT.format("4432577")},
    ],
    "Buffalo Bills": [
        {"name": "Josh Allen", "headshot": HEADSHOT.format("3918298")},
        {"name": "David Montgomery", "headshot": TRANSFERRED_HEADSHOT},
        {"name": "Jackson Hawes", "headshot": "https://example.invalid/roster-today/hawes.png"},
    ],
}

LEGS = [
    # (market, outcome) — subjects as the venue spells them on 14780141
    (PASS_NAME, "C.J. Stroud: 225+"),
    (PASS_NAME, "Josh Allen: 250+"),
    (RUSH_NAME, "David Montgomery: 50+"),
    # MISSING-PROVIDER CONTROL: Hawes is a prop subject on 14780141 but not in
    # ESPN's box for it (measured on the served payload and the summary).
    (REC_NAME, "Jackson Hawes: 25+"),
]


def _game(box_score_data, sport_key=NFL):
    event = _make_event(
        id=EVENT_ID, home_team="Houston Texans", away_team="Buffalo Bills",
        status="completed", sport_key=sport_key, home_score=27, away_score=24,
    )
    event.llm_league = "NFL"
    event.period = None
    event.commence_time = datetime.now(timezone.utc) - timedelta(hours=6)
    event.completed_at = datetime.now(timezone.utc) - timedelta(hours=3)
    event.home_team_id, event.away_team_id = HOME_TEAM_ID, AWAY_TEAM_ID
    event.box_score_data = box_score_data

    markets, outcomes = {}, []
    for i, (mname, oname) in enumerate(LEGS):
        if mname not in markets:
            m = _make_futures_market(id=800 + len(markets), name=mname, source="kalshi",
                                     sport_category="football")
            m.external_id = f"KX-{len(markets)}-26SEP13BUFHOU"
            m.event_id, m.market_tier, m.category = EVENT_ID, 5, "game_prop"
            m.status, m.settled_at = "open", None
            markets[mname] = m
        outcomes.append(_make_outcome(id=9000 + i, market_id=markets[mname].id,
                                      name=oname, probability=0.55))
    return event, list(markets.values()), outcomes


def _with_teams(session, *, home_espn=HOME_ESPN, away_espn=AWAY_ESPN, seen=None):
    """Answer the two `teams` reads step 10 makes; everything else as before."""
    inner = session.execute.side_effect

    async def execute(stmt, *a, **kw):
        sql = str(stmt).lower()
        if "teams.espn_id" in sql:
            if seen is not None:
                seen.append(sql)
            r = MagicMock()
            r.all.return_value = [(HOME_TEAM_ID, home_espn), (AWAY_TEAM_ID, away_espn)]
            return r
        if "teams.roster_players" in sql and "jsonb" not in sql:
            r = MagicMock()
            r.all.return_value = list(TODAYS_ROSTERS.items())
            return r
        return await inner(stmt, *a, **kw)

    session.execute = AsyncMock(side_effect=execute)
    return session


async def _served(box_score_data, *, sport_key=NFL, seen=None, **teams):
    from app.main import app
    from app.routes.events import _game_markets_cache

    _game_markets_cache.clear()
    event, futures, outcomes = _game(box_score_data, sport_key)
    session = _with_teams(
        _make_event_detail_session(event=event, futures=futures, outcomes=outcomes),
        seen=seen, **teams,
    )

    async def _db():
        yield session

    async def _nobody():
        return None

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_db_rw] = _db
    app.dependency_overrides[get_optional_user] = _nobody
    try:
        with patch("app.main.init_db", new_callable=AsyncMock):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get(f"/api/events/{EVENT_ID}/game-markets")
    finally:
        app.dependency_overrides.clear()
        _game_markets_cache.clear()
    assert resp.status_code == 200, resp.text
    body = resp.json()
    return {row["outcome_name"]: row for row in body.get("player_props") or []}, body


_IDENTITY_KEYS = ("player_entity_key", "player_team_entity_key")


@pytest.mark.asyncio
async def test_THE_SHIP_ingestion_to_served_prop_keeps_the_games_own_team_and_picture():
    """Bills @ Texans end to end: real context → settled writer → stored box →
    game-markets. Montgomery played for Houston in this game. Today's roster
    (REPRESENTATIVE transfer) says Buffalo, and the page must still say Houston."""
    props, body = await _served(await _stored_box())
    assert set(props) == {o for _, o in LEGS}, sorted(props)

    for outcome, (name, athlete_id, team_id, side) in (
        ("C.J. Stroud: 225+", STROUD),
        ("Josh Allen: 250+", ALLEN),
        ("David Montgomery: 50+", MONTGOMERY),
    ):
        row = props[outcome]
        assert row["player_team"] == side, (outcome, row)
        assert row["player_headshot"] == HEADSHOT.format(athlete_id)
        assert row["player_entity_key"] == f"espn:athlete:{athlete_id}"
        assert row["player_team_entity_key"] == f"espn:team:{team_id}"

    # TRANSFER CONTROL, stated directly: the roster's side and picture lost.
    assert props["David Montgomery: 50+"]["player_team"] == "home"
    assert props["David Montgomery: 50+"]["player_headshot"] != TRANSFERRED_HEADSHOT

    # Prices, names and ids are not the bridge's to touch.
    for row in props.values():
        assert row["over_probability"] == 0.55

    golden = [
        {k: props[o].get(k) for k in (
            "market_name", "outcome_name", "threshold", "over_probability",
            "player_team", "player_headshot", *_IDENTITY_KEYS)}
        for _, o in LEGS
    ]
    assert golden == json.loads(GOLDEN_PATH.read_text())["player_props"]
    assert json.loads(GOLDEN_PATH.read_text())["home_team"] == body["home_team"]


@pytest.mark.asyncio
async def test_MISSING_PROVIDER_CONTROL_a_subject_not_in_the_box_falls_back_with_no_identity():
    props, _ = await _served(await _stored_box())
    hawes = props["Jackson Hawes: 25+"]
    assert hawes["player_team"] == "away"  # the roster pass, unchanged
    assert not set(_IDENTITY_KEYS) & set(hawes)


@pytest.mark.asyncio
async def test_DUPLICATE_CONTROL_on_the_page_a_shared_name_keeps_the_roster_answer():
    box = await _stored_box()
    box["player_identities"].append({  # REPRESENTATIVE, see the index test
        "name": "Josh Allen", "athlete_id": "3052587", "team_id": "34", "side": "home",
    })
    props, _ = await _served(box)
    allen = props["Josh Allen: 250+"]
    assert allen["player_team"] == "away"
    assert not set(_IDENTITY_KEYS) & set(allen)
    assert props["C.J. Stroud: 225+"]["player_entity_key"] == "espn:athlete:4432577"


@pytest.mark.asyncio
async def test_PROVIDER_MISMATCH_CONTROL_on_the_page_every_prop_is_the_roster_answer():
    props, _ = await _served(await _stored_box(), home_espn=AWAY_ESPN, away_espn=HOME_ESPN)
    assert props["David Montgomery: 50+"]["player_team"] == "away"
    assert props["David Montgomery: 50+"]["player_headshot"] == TRANSFERRED_HEADSHOT
    for row in props.values():
        assert not set(_IDENTITY_KEYS) & set(row)


@pytest.mark.asyncio
async def test_PREGAME_CONTROL_no_box_means_the_roster_pass_alone_and_no_extra_read():
    seen: list = []
    props, _ = await _served(None, seen=seen)
    assert seen == []
    assert props["David Montgomery: 50+"]["player_team"] == "away"
    for row in props.values():
        assert not set(_IDENTITY_KEYS) & set(row)


@pytest.mark.asyncio
async def test_A_BOX_STORED_BEFORE_THIS_CHANGE_is_read_exactly_as_before():
    """Every NFL box already in the table has `players` and no map. It must cost
    no extra query and keep the roster answer."""
    box = await _stored_box()
    del box["player_identities"]
    seen: list = []
    props, _ = await _served(box, seen=seen)
    assert seen == []
    assert props["David Montgomery: 50+"]["player_team"] == "away"
    for row in props.values():
        assert not set(_IDENTITY_KEYS) & set(row)


@pytest.mark.asyncio
async def test_NON_NFL_CONTROL_a_box_map_on_another_sport_is_not_read():
    seen: list = []
    props, _ = await _served(await _stored_box(), sport_key="americanfootball_ncaaf", seen=seen)
    assert seen == []
    for row in props.values():
        assert not set(_IDENTITY_KEYS) & set(row)


@pytest.mark.asyncio
async def test_a_failed_team_read_costs_the_bridge_not_the_page():
    box = await _stored_box()

    def _boom(*a, **kw):
        raise RuntimeError("identity index failed")

    with patch("app.routes.events._game_player_identity_index", _boom):
        props, _ = await _served(box)
    assert props["David Montgomery: 50+"]["player_team"] == "away"
    for row in props.values():
        assert not set(_IDENTITY_KEYS) & set(row)


# ═══════════════════════════════════════════════════════════════════════════
# 5. Existing clients: the served box score does not grow the new key
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_EXISTING_CLIENT_CONTROL_the_served_box_score_does_not_carry_the_map():
    """`player_identities` is a stored sibling for the prop reader. `GET
    /api/events/{id}` serves `box_score_data` through an allowlist (`players` +
    the line score), so no existing web or iOS client is sent a new key."""
    from app.main import app
    from app.routes.events import _event_detail_cache, _game_markets_cache

    box = await _stored_box()
    assert box["player_identities"]
    event, futures, outcomes = _game(box)
    session = _make_event_detail_session(event=event, futures=futures, outcomes=outcomes)

    async def _db():
        yield session

    async def _nobody():
        return None

    _event_detail_cache.clear()
    _game_markets_cache.clear()
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_db_rw] = _db
    app.dependency_overrides[get_optional_user] = _nobody
    try:
        with patch("app.main.init_db", new_callable=AsyncMock):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get(f"/api/events/{EVENT_ID}")
    finally:
        app.dependency_overrides.clear()
        _event_detail_cache.clear()
        _game_markets_cache.clear()
    assert resp.status_code == 200, resp.text
    served = resp.json()["box_score_data"]
    assert served["players"] == box["players"]
    assert "player_identities" not in served
    assert set(served) <= {"players", "home_period_scores", "away_period_scores"}
