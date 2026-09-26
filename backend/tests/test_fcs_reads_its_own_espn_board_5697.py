"""#5697 (FCS specimen) — an FCS game gets its score, its final and its crests from ESPN.

Production 2026-09-25: event 15317759, Harvard Crimson at Brown Bears
(`americanfootball_ncaaf_fcs`, kickoff 23:01Z) served `live` with a null score
for the whole game, then `suspended`; Brown drew a "BEA" initials placeholder
and Harvard drew its LACROSSE row's crest and 9-5 record. ESPN had the game the
whole time — event 401867806 on its FCS board, Harvard 14-10 final, both logos.

Nothing read it. The key was on neither ESPN map, so `sync_espn_live_events`
never fetched a board for it; and FCS cannot simply borrow FBS's entry, because
ESPN files both under `football/college-football` and tells them apart only by
`groups` (80 FBS, 81 FCS). Measured 2026-09-26 04:4xZ:

    ?dates=20260925             5 events, HARV @ BRWN absent
    ?groups=81&dates=20260925   2 events, HARV @ BRWN 401867806
    ?groups=81                 65 events (the FCS week)

Three things this file pins:

1. The FCS key asks ESPN for the FCS board on every call — undated, dated, from
   any pass — and FBS's calls are byte-identical to before.
2. FCS is NOT folded into FBS. It stays out of `SPORT_LEAGUE_MAP`, so
   `league_identity` keeps it a league of its own (teams, records, twin folds).
3. The FCS board ATTACHES and never CREATES: its group lists FBS home games too
   (`BUCK @ PITT`), and a create would file Pittsburgh's home game under FCS.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from app.services import espn_api
from app.utils import sport_keys
from app.utils.sport_keys import (
    ESPN_GROUP_SCOPED_BOARDS,
    ESPN_SPORT_MAPPING,
    SPORT_LEAGUE_MAP,
    league_identity,
)

FCS = "americanfootball_ncaaf_fcs"
FBS = "americanfootball_ncaaf"

FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "espn_fcs_board_entry_harvard_at_brown_401867806.json"
)


def _board_entry() -> dict:
    return json.loads(FIXTURE.read_text())


# ── 1. The key is on the maps the live pass reads, and nowhere it would fold ──


def test_fcs_is_on_the_espn_fetch_map_with_its_own_group():
    assert ESPN_SPORT_MAPPING[FCS] == "football/college-football"
    assert ESPN_GROUP_SCOPED_BOARDS[FCS] == ("football", "college-football", "81")
    # `sync_espn_live_events` gates on the copy re-exported through config.
    from app.tasks.config import ESPN_SPORT_MAPPING as TASK_MAP

    assert FCS in TASK_MAP


def test_fcs_keeps_its_own_league_identity():
    assert FCS not in SPORT_LEAGUE_MAP
    assert league_identity(FCS) == FCS
    assert league_identity(FCS) != league_identity(FBS)


def test_strawman_a_sport_league_map_entry_would_fold_fcs_into_fbs(monkeypatch):
    """Why the group-scoped map exists at all: the obvious one-line fix merges."""
    monkeypatch.setitem(
        sport_keys.SPORT_LEAGUE_MAP, FCS, ("football", "college-football")
    )
    assert league_identity(FCS) == league_identity(FBS)


# ── 2. Every scoreboard call for FCS carries groups=81 ──────────────────────


class _Recorder:
    def __init__(self, monkeypatch, body=None):
        self.urls: list[str] = []
        body = body if body is not None else {"events": []}

        async def _get(svc, url, *a, **k):
            self.urls.append(url)
            return body

        monkeypatch.setattr(espn_api.ESPNAPIService, "_get", _get)


class TestTheFcsBoardIsAskedForByGroup:
    async def _url(self, monkeypatch, sport_key, **kwargs):
        rec = _Recorder(monkeypatch)
        svc = espn_api.ESPNAPIService()
        try:
            await svc.get_scoreboard(sport_key, **kwargs)
        finally:
            await svc.close()
        assert len(rec.urls) == 1
        return rec.urls[0]

    async def test_the_undated_fcs_board_is_the_fcs_group(self, monkeypatch):
        url = await self._url(monkeypatch, FCS)
        assert url.endswith("/football/college-football/scoreboard?groups=81"), url

    async def test_the_dated_fcs_board_is_the_fcs_group(self, monkeypatch):
        """The live pass's widening and every straggler arm ask BY DATE."""
        url = await self._url(monkeypatch, FCS, date="20260925")
        assert url.endswith("/scoreboard?dates=20260925&groups=81"), url

    async def test_an_explicit_group_is_not_overridden(self, monkeypatch):
        url = await self._url(monkeypatch, FCS, groups="80")
        assert url.endswith("/scoreboard?groups=80"), url

    async def test_fbs_calls_are_byte_identical_to_before(self, monkeypatch):
        url = await self._url(monkeypatch, FBS)
        assert url.endswith("/football/college-football/scoreboard"), url
        url = await self._url(monkeypatch, FBS, date="20260925")
        assert url.endswith("/scoreboard?dates=20260925"), url

    def test_per_event_endpoints_resolve_the_shared_path(self):
        svc = espn_api.ESPNAPIService()
        assert svc._get_espn_path(FCS) == ("football", "college-football")
        assert svc._get_espn_path(FBS) == ("football", "college-football")
        assert svc._get_espn_path("not_a_sport") is None

    async def test_the_unscoped_team_list_is_refused_for_fcs(self, monkeypatch):
        """`/teams` ignores `groups`; a name matcher fed it binds any division."""
        rec = _Recorder(monkeypatch)
        svc = espn_api.ESPNAPIService()
        try:
            assert await svc.get_teams(FCS) == []
            assert rec.urls == []
            await svc.get_teams(FBS)
            assert len(rec.urls) == 1
        finally:
            await svc.close()


# ── 3. The specimen, off ESPN's own board entry ──────────────────────────────


def _specimen_board():
    svc = espn_api.ESPNAPIService()
    ee = svc._parse_event(_board_entry())
    assert ee is not None
    return ee


def test_the_board_entry_carries_the_score_the_final_and_both_crests():
    ee = _specimen_board()
    assert ee.espn_id == "401867806"
    assert ee.home_team.display_name == "Brown Bears"
    assert ee.home_team.espn_id == "225"
    assert ee.home_team.logo_url.endswith("/ncaa/500/225.png")
    assert ee.away_team.display_name == "Harvard Crimson"
    assert ee.away_team.espn_id == "108"
    # Harvard AT Brown: the home side lost, 10-14.
    assert (ee.home_score, ee.away_score) == (10, 14)
    assert ee.status in ("post", "final")


def test_our_row_pairs_with_the_fcs_board_entry():
    from app.tasks.espn_sync import espn_team_matches
    from app.utils.espn_helpers import match_event_to_espn

    class _Row(SimpleNamespace):
        def __getattr__(self, name):
            return None

    row = _Row(
        id=15317759,
        home_team_name="Brown Bears",
        away_team_name="Harvard Crimson",
        commence_time=datetime(2026, 9, 25, 23, 1, tzinfo=timezone.utc),
        status="live",
        sport=SimpleNamespace(key=FCS),
    )
    ee = _specimen_board()
    matched, how = match_event_to_espn(
        row, [ee], {ee.espn_id: ee}, set(), espn_team_matches
    )
    assert matched is ee
    assert how == "name"


async def test_the_crest_lands_on_the_football_row_not_the_lacrosse_one():
    """`upsert_team` resolves inside the EVENT's sport: Brown's lacrosse row
    (the only Brown with a crest on 2026-09-26) is never the one written."""
    from app.utils.espn_helpers import upsert_team

    LACROSSE_SPORT_ID, FCS_SPORT_ID = 11, 77
    lacrosse = SimpleNamespace(
        id=1428, name="Brown Bears", sport_id=LACROSSE_SPORT_ID,
        logo_url_small="https://a.espncdn.com/i/teamlogos/ncaa/500/225.png",
    )
    class _TeamRow(SimpleNamespace):
        """Every column the writer reads starts empty, as on the 116 FCS rows."""

        def __getattr__(self, name):
            return None

    football = _TeamRow(id=90001, name="Brown Bears", sport_id=FCS_SPORT_ID)
    cache = {
        ("Brown Bears", LACROSSE_SPORT_ID): lacrosse,
        ("Brown Bears", FCS_SPORT_ID): football,
    }
    ee = _specimen_board()

    class _Session:
        def add(self, obj):
            pass

        async def flush(self):
            pass

        async def execute(self, *a, **k):
            raise AssertionError("a cache hit must not reach the database")

    team = await upsert_team(_Session(), "Brown Bears", ee.home_team, FCS_SPORT_ID, cache, {})
    assert team is football
    assert football.logo_url_small and football.logo_url_small.endswith("/225.png")
    assert lacrosse.id == 1428 and lacrosse.sport_id == LACROSSE_SPORT_ID


def test_the_page_reads_the_football_row_once_it_exists():
    """Serve side (#7262's lookup): the FCS row wins on an FCS card; before this
    write there was none, and the card fell back to the lacrosse row."""
    from app.routes.events import TeamNameLookup, _team_for_event

    lacrosse = SimpleNamespace(name="Harvard Crimson", record="9-5")
    football = SimpleNamespace(name="Harvard Crimson", record="2-1")
    lax_identity = league_identity("lacrosse_ncaa")

    before = TeamNameLookup(
        {"Harvard Crimson": lacrosse},
        {"Harvard Crimson": {lax_identity: lacrosse}},
    )
    assert _team_for_event(before, "Harvard Crimson", FCS) is lacrosse  # the defect

    after = TeamNameLookup(
        {"Harvard Crimson": lacrosse},
        {"Harvard Crimson": {lax_identity: lacrosse, league_identity(FCS): football}},
    )
    assert _team_for_event(after, "Harvard Crimson", FCS) is football
    assert _team_for_event(after, "Harvard Crimson", "lacrosse_ncaa") is lacrosse


# ── 4. The FCS board attaches; it never mints a row ──────────────────────────


class TestTheGroupScopedBoardNeverCreates:
    def _board(self):
        """An FBS home game, exactly as ESPN's FCS group lists it."""
        return [SimpleNamespace(
            espn_id="401999001",
            home_team=SimpleNamespace(display_name="Pittsburgh Panthers", name="Pittsburgh"),
            away_team=SimpleNamespace(display_name="Bucknell Bison", name="Bucknell"),
            date=datetime.now(timezone.utc) + timedelta(hours=3),
            status="pre",
            home_win_probability=None,
        )]

    def _record_registry(self, monkeypatch):
        from app.services import event_registry

        calls = []

        async def _foc(session, identity):
            calls.append(identity)
            # A future sibling: the helper's own fold guard then skips every
            # write, so the control arm needs no session.
            return SimpleNamespace(
                id=1, commence_time=datetime.now(timezone.utc) + timedelta(days=2),
            ), False

        monkeypatch.setattr(event_registry, "find_or_create_event", _foc)
        return calls

    async def test_fcs_creates_nothing(self, monkeypatch):
        from app.utils.espn_helpers import create_events_from_unmatched_espn

        calls = self._record_registry(monkeypatch)
        stats: dict = {}
        await create_events_from_unmatched_espn(None, [], self._board(), FCS, stats)
        assert calls == []
        assert stats["espn_create_skipped_group_scoped"] == 1

    async def test_control_fbs_still_reaches_the_registry(self, monkeypatch):
        from app.utils.espn_helpers import create_events_from_unmatched_espn

        calls = self._record_registry(monkeypatch)
        stats: dict = {}
        await create_events_from_unmatched_espn(None, [], self._board(), FBS, stats)
        assert len(calls) == 1
        assert calls[0].sport_key == FBS
        assert "espn_create_skipped_group_scoped" not in stats
