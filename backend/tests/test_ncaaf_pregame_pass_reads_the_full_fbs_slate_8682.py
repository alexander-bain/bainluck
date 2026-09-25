"""#8682 — the ESPN pre-game pass reads the whole FBS week, not ESPN's featured slice.

**SHIP: every FBS game shows both clubs by name, crest and record before
kickoff — Kentucky's game on 9/26 stops reading "WIL · Wildcats".** (Pillar:
MATCHING.)

Production, 2026-09-25 18:5xZ, `/events/15315931` (Kentucky Wildcats v South
Alabama) at 390px: the home tile reads `WIL / Wildcats` with no crest and no
record. `home_team_id` is NULL because no NCAAF `teams` row exists for Kentucky
(nor BYU, UConn, Arizona, Utah State, Rice, San Diego State, ~25 FCS clubs).
Before #7157/#7441 those clubs were adopted onto a namesake (Kentucky ->
Bethune-Cookman); since 9/20 that adoption is refused, so the club has to be
MINTED, and the only rail that mints before kickoff — `sync_scheduled_events` —
never saw these games. It was fed the UNDATED college-football board:

    GET football/college-football/scoreboard              18 events, no `USA @ UK`
    GET football/college-football/scoreboard?groups=80    71 events, `USA @ UK` in it

(ESPN's own API, 2026-09-25 18:5xZ.) This file pins three things: the URL the
service builds, the board the pre-game pass is handed (through the whole task),
and — so the fix is not inert — that the writer mints Kentucky against the
namesake rows production holds once the pass can see the game.

WHAT IS NOT CLAIMED: the completed games already bound to a namesake
(15301197 Kentucky v Alabama -> Bethune-Cookman, and the rest of #7441's table)
are not re-bound here; that is #7441's attended drain. The live pass's board —
and therefore what `create_events_from_unmatched_espn` creates from — is
unchanged, and a test below holds it unchanged.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.espn_api import ESPNTeam

NCAAF = "americanfootball_ncaaf"
MLB = "baseball_mlb"


# ── 1. The URL ──────────────────────────────────────────────────────────────


class TestTheScoreboardUrl:
    async def _url_for(self, monkeypatch, **kwargs):
        from app.services import espn_api

        seen: list[str] = []

        async def _get(self, url, *a, **k):
            seen.append(url)
            return {"events": []}

        monkeypatch.setattr(espn_api.ESPNAPIService, "_get", _get)
        svc = espn_api.ESPNAPIService()
        try:
            await svc.get_scoreboard(NCAAF, **kwargs)
        finally:
            await svc.close()
        assert len(seen) == 1, seen
        return seen[0]

    @pytest.mark.asyncio
    async def test_groups_is_sent(self, monkeypatch):
        url = await self._url_for(monkeypatch, groups="80")
        assert url.endswith("/football/college-football/scoreboard?groups=80"), url

    @pytest.mark.asyncio
    async def test_groups_and_date_are_both_sent(self, monkeypatch):
        url = await self._url_for(monkeypatch, date="20260926", groups="80")
        assert url.endswith("/scoreboard?dates=20260926&groups=80"), url

    @pytest.mark.asyncio
    async def test_the_undated_call_is_byte_identical_to_before(self, monkeypatch):
        """Every existing caller passes no `groups`, and must ask what it asked."""
        url = await self._url_for(monkeypatch)
        assert url.endswith("/football/college-football/scoreboard"), url
        url = await self._url_for(monkeypatch, date="20260926")
        assert url.endswith("/scoreboard?dates=20260926"), url

    def test_ncaaf_is_the_fbs_group_and_nothing_else_is_widened(self):
        from app.services.espn_api import ESPN_FULL_SLATE_GROUPS

        assert ESPN_FULL_SLATE_GROUPS == {NCAAF: "80"}


# ── 2. The board the pre-game pass is handed ────────────────────────────────


def _ee(espn_id):
    return SimpleNamespace(espn_id=espn_id)


FEATURED = [_ee("401856709")]  # a featured game (SC @ ALA is on today's 18)
FULL = [_ee("401856709"), _ee("401864576"), _ee("401861970")]  # + USA@UK, CONN@M-OH


class _Espn:
    """Answers `groups=80` with the full slate, the undated ask with the featured one."""

    def __init__(self, full=FULL, featured=FEATURED, full_raises=False):
        self.full, self.featured, self.full_raises = full, featured, full_raises
        self.calls: list[tuple] = []

    async def get_scoreboard(self, sport_key, date=None, groups=None):
        self.calls.append((sport_key, date, groups))
        if groups:
            if self.full_raises:
                raise RuntimeError("boom")
            return self.full
        return self.featured

    async def close(self):
        pass


class TestTheFullSlateFetch:
    @pytest.mark.asyncio
    async def test_only_ncaaf_is_asked_for_its_group(self):
        from app.tasks.espn_sync import _fetch_full_slate_boards

        espn, stats = _Espn(), {"errors": []}
        boards = await _fetch_full_slate_boards(espn, [MLB, NCAAF], stats)

        assert espn.calls == [(NCAAF, None, "80")]
        assert boards == {NCAAF: FULL}
        assert stats["full_slate_events"] == {NCAAF: 3}

    @pytest.mark.asyncio
    async def test_a_dark_full_slate_is_absent_not_empty(self):
        from app.tasks.espn_sync import _fetch_full_slate_boards

        stats = {"errors": []}
        boards = await _fetch_full_slate_boards(_Espn(full=None), [NCAAF], stats)
        assert boards == {}
        assert stats["full_slate_dark"] == 1

    @pytest.mark.asyncio
    async def test_a_raising_full_slate_is_absent_and_named(self):
        from app.tasks.espn_sync import _fetch_full_slate_boards

        stats = {"errors": []}
        boards = await _fetch_full_slate_boards(_Espn(full_raises=True), [NCAAF], stats)
        assert boards == {}
        assert stats["errors"] == ["espn_full_slate_americanfootball_ncaaf: boom"]

    def test_the_full_slate_wins_when_it_has_games(self):
        from app.tasks.espn_sync import scheduled_board_for

        assert scheduled_board_for(NCAAF, FEATURED, {NCAAF: FULL}) is FULL

    @pytest.mark.parametrize("boards", [{}, {NCAAF: []}], ids=["absent", "empty"])
    def test_otherwise_the_featured_board_is_kept(self, boards):
        from app.tasks.espn_sync import scheduled_board_for

        assert scheduled_board_for(NCAAF, FEATURED, boards) is FEATURED


class TestThroughTheWholeTask:
    """`_sync_espn_live_events` itself, every pass but the two boards stubbed.

    The seam that matters is which list reaches `sync_scheduled_events` and
    which reaches `_process_live_sport` — a helper that is right and never
    called is the inert shape, so the task is driven, not the helper.
    """

    def _wire(self, monkeypatch, espn):
        import app.services.espn_api as espn_api
        import app.tasks.espn_sync as espn_sync
        import app.utils.espn_helpers as helpers

        handed: dict[str, list] = {"scheduled": [], "live": []}

        class _Ctx:
            async def __aenter__(self):
                return SimpleNamespace()

            async def __aexit__(self, *exc):
                return False

        async def _noop(*a, **k):
            return None

        async def _keys(session):
            return [NCAAF], [NCAAF]

        async def _decide(*a, **k):
            return {}

        async def _scheduled(session, sport_key, espn_events, stats):
            handed["scheduled"].append((sport_key, espn_events))

        async def _live(session, sport_key, espn_events, stats, *a, **k):
            handed["live"].append((sport_key, espn_events))

        monkeypatch.setattr(espn_sync, "get_task_session", lambda: _Ctx())
        monkeypatch.setattr(espn_api, "ESPNAPIService", lambda: espn)
        monkeypatch.setattr(espn_sync, "_find_sport_keys_to_sync", _keys)
        for name in (
            "_settle_authority_stragglers",
            "_settle_deep_authority_stragglers",
            "_recover_unstarted_authority_fixtures",
            "_act_on_failovers",
        ):
            monkeypatch.setattr(espn_sync, name, _noop)
        monkeypatch.setattr(espn_sync, "_decide_failovers", _decide)
        monkeypatch.setattr(espn_sync, "_process_live_sport", _live)
        monkeypatch.setattr(helpers, "sync_scheduled_events", _scheduled)
        for name in ("fetch_completed_box_scores", "fetch_live_box_scores", "backfill_missing_scores"):
            monkeypatch.setattr(helpers, name, _noop)
        return handed

    @pytest.mark.asyncio
    async def test_the_pregame_pass_gets_the_full_fbs_week(self, monkeypatch):
        """THE WITNESS. On the parent the scheduled pass is handed FEATURED."""
        from app.tasks.espn_sync import _sync_espn_live_events

        espn = _Espn()
        handed = self._wire(monkeypatch, espn)

        stats = await _sync_espn_live_events()

        assert stats["errors"] == [], stats["errors"]
        assert handed["scheduled"] == [(NCAAF, FULL)], (
            "the pre-game pass was not handed the full FBS board, so USA @ UK "
            "and CONN @ M-OH never get their clubs before kickoff"
        )

    @pytest.mark.asyncio
    async def test_the_live_pass_board_is_unchanged(self, monkeypatch):
        """The live pass — and what it CREATES events from — still sees FEATURED."""
        from app.tasks.espn_sync import _sync_espn_live_events

        handed = self._wire(monkeypatch, _Espn())
        await _sync_espn_live_events()
        assert handed["live"] == [(NCAAF, FEATURED)]

    @pytest.mark.asyncio
    async def test_a_dark_full_slate_falls_back_to_the_featured_board(self, monkeypatch):
        from app.tasks.espn_sync import _sync_espn_live_events

        handed = self._wire(monkeypatch, _Espn(full=None))
        stats = await _sync_espn_live_events()
        assert handed["scheduled"] == [(NCAAF, FEATURED)]
        assert stats["full_slate_dark"] == 1

    @pytest.mark.asyncio
    async def test_a_dark_featured_board_still_skips_the_sport(self, monkeypatch):
        """#3473's gate is unchanged: ESPN dark on its own board means no pass."""
        from app.tasks.espn_sync import _sync_espn_live_events

        handed = self._wire(monkeypatch, _Espn(featured=None))
        await _sync_espn_live_events()
        assert handed["scheduled"] == []


# ── 3. Not inert: once the pass sees the game, the writer mints the club ─────


class _Row:
    def __init__(self, id, name, sport_id, espn_id=None, alternate_names=None):
        self.id, self.name, self.sport_id = id, name, sport_id
        self.espn_id, self.alternate_names = espn_id, alternate_names


class _Result:
    def __init__(self, rows):
        self._rows = list(rows)

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def scalars(self):
        return iter(self._rows)


class _QueryingSession:
    """Answers the statement (the #7157 fake): exact name, or ILIKE needles."""

    def __init__(self, rows):
        self.rows, self.added = list(rows), []

    async def execute(self, stmt):
        compiled = stmt.compile()
        params = compiled.params
        candidates = [r for r in self.rows if r.sport_id == params.get("sport_id_1")]
        likes = [
            v for k, v in params.items()
            if k.startswith("name_") and isinstance(v, str) and v.startswith("%")
        ]
        if likes:
            needles = [p.strip("%").lower() for p in likes]
            return _Result([r for r in candidates if any(n in r.name.lower() for n in needles)])
        exact = [
            v for k, v in params.items()
            if k.startswith("name_") and isinstance(v, str) and not v.startswith("%")
        ]
        if exact:
            return _Result([r for r in candidates if r.name == exact[0]])
        raise AssertionError(f"unrecognised query: {compiled} {params}")

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        pass


SID = 760  # production's NCAAF sport id


def _ncaaf_namesakes():
    """The NCAAF rows production holds for these mascots (read 2026-09-25)."""
    return [
        _Row(17027, "Bethune-Cookman Wildcats", SID, "2065", ["Wildcats", "Bethune"]),
        _Row(19683, "Northwestern Wildcats", SID, "77", ["Wildcats", "Northwestern"]),
        _Row(15995, "Kansas State Wildcats", SID, "2306", ["Kansas St", "Wildcats"]),
        _Row(17171, "Eastern Kentucky Colonels", SID, "2198", ["Colonels", "E Kentucky"]),
        _Row(15336, "Western Kentucky Hilltoppers", SID, "98", ["Western KY", "Hilltoppers"]),
        _Row(14126, "Houston Cougars", SID, "248", ["Cougars", "Houston"]),
        _Row(15355, "Washington State Cougars", SID, "265", ["Washington St", "Cougars"]),
        _Row(15301, "Washington Huskies", SID, "264", ["Huskies", "Washington"]),
        _Row(15348, "Northern Illinois Huskies", SID, "2459", ["Huskies", "N Illinois"]),
    ]


def _payload(espn_id, mascot, abbr, school):
    return ESPNTeam(
        espn_id=espn_id, name=mascot, abbreviation=abbr,
        display_name=f"{school} {mascot}", short_name=school, nickname=school,
        primary_color=None, secondary_color=None, logo_url="https://a.espncdn.com/x.png",
        logo_url_dark=None, record="2-1", location=school,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name,payload,namesake",
    [
        ("Kentucky Wildcats", _payload("96", "Wildcats", "UK", "Kentucky"), 17027),
        ("BYU Cougars", _payload("252", "Cougars", "BYU", "BYU"), 14126),
        ("UConn Huskies", _payload("41", "Huskies", "CONN", "UConn"), 15301),
    ],
    ids=["kentucky", "byu", "uconn"],
)
@pytest.mark.parametrize("warm", [True, False], ids=["warm-cache", "cold"])
async def test_the_club_is_minted_not_lent_a_namesake(name, payload, namesake, warm):
    from app.utils.espn_helpers import upsert_team

    rows = _ncaaf_namesakes()
    session = _QueryingSession(rows)
    cache = {(r.name, SID): r for r in rows} if warm else None

    team = await upsert_team(session, name, payload, SID, team_cache=cache)

    assert team is not None
    assert getattr(team, "id", None) != namesake, f"{name} was lent its namesake's row"
    assert [t.name for t in session.added] == [name]
    assert team.espn_id == payload.espn_id
    assert team.logo_url_small == payload.logo_url
    assert team.current_record == "2-1"
