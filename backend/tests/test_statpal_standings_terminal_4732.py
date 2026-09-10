"""#4732 / authority/102 — NFL and MLB standings were never once populated, and
the pass that dropped them banked the same green as the pass that got everything.

WHAT WAS BROKEN, measured from production 2026-09-10 before the fix:

    GET /api/admin/task-metrics?task=statpal_standings
        last_verdict:        unverified
        last_verdict_reason: not_enforced(unknown:no_terminal_fields)
        last_result_summary: {total_teams_updated, details}     <- no terminal

    sport                  teams  standings_data  last write
    americanfootball_nfl      32               0  never          <- IN SEASON
    baseball_mlb              33               0  never          <- IN SEASON
    basketball_nba            34              33  2026-09-10 08:00Z
    icehockey_nhl             43              42  2026-09-10 08:00Z

Not an outage: an outage does not last since inception on two sports while the
two beside it write successfully the same morning. And not #4691's shape either
— all four have `sports` rows and `get_standings` is uniform.

THE CAUSE, read off the venue's own API (notice 26; all four HTTP 200):

    nfl   standings.category.league[].division[].team[]     32 teams
    mlb   standings.category.league[].division[].team[]     30 teams
    nba   standings.tournament.league[].division[].team[]   30 teams
    nhl   standings.tournament.league[].division[].team[]   32 teams

The navigator knew `tournament` and only `tournament`. One wrapper key, two
whole leagues, from the day the code was written.

WHY IT SAT FOR MONTHS, which is the part worth keeping. The task already had a
diagnostic for exactly this — `logger.info("...unexpected format, keys=...")` —
and it could never have fired usefully: it printed `standings_data.keys()`,
which is `['standings']` for all four sports alike. The one key the two broken
sports shared with the two working ones was the one the log chose to print. The
keys that discriminate are one level in.

And nothing graded the result. `total_teams_updated: 62` is a healthy-looking
number; it was the two off-season sports and neither of the two in season.

THE TWO-ARM CAUTION (#4710's lesson, applied to my own comment). While writing
this I asserted in a code comment that standings had ONE unasked arm, because
`get_standings` looked uniform. Then I measured: `GET /v2/soccer/standings` and
`GET /v1/tennis/standings` are both **HTTP 404**, so there is a second arm —
nine of the thirteen mapped keys cannot be asked at all. `test_the_unasked_arms`
below pins both, so the count in the comment cannot drift from the code again.
"""
import pytest

import app.services.statpal_api as statpal_api
from app.tasks.statpal_sync import _standings_league_node
from app.utils.task_verdict import ENFORCED_TASKS, NOT_GREEN, verdict_for

#: Module-qualified rather than imported by name, matching
#: `test_statpal_schedules_zero_yield_2907.py`: `_stub_venue` has to monkeypatch
#: attributes ON this module, so binding some names locally and reaching through
#: the module for others would leave two ways to say one thing.
NO_STANDINGS_SPORTS = statpal_api.NO_STANDINGS_SPORTS


# =============================================================================
# Fixtures shaped like the venue's real answers.
#
# Trimmed to two divisions of one team each — the subject is WHICH KEY the
# navigator walks through, and a full 32-team table proves nothing extra about
# that while making the disagreement harder to see.
# =============================================================================

def _table(wrapper: str, *team_names: str) -> dict:
    """A standings payload nested under `wrapper`, in the venue's real shape."""
    return {
        "standings": {
            "sport": "x",
            wrapper: {
                "id": "1",
                "name": "League",
                "season": "2026",
                "league": [
                    {
                        "name": "Conference",
                        "division": [
                            {"name": "Division", "team": [
                                {"name": n, "won": 3, "lost": 1, "position": 1}
                                for n in team_names
                            ]},
                        ],
                    }
                ],
            },
        }
    }


#: NFL/MLB, the two that were empty from inception.
_CATEGORY_TABLE = _table("category", "Buffalo Bills")
#: NBA/NHL, the two that always worked — the control that says the navigator is
#: not simply broken for everyone.
_TOURNAMENT_TABLE = _table("tournament", "Boston Celtics")


# =============================================================================
# 1. The navigator. The whole defect is one key name, so it gets its own unit.
# =============================================================================

class TestTheNavigatorFindsTheLeagueUnderEitherWrapper:

    def test_the_tournament_wrapper_still_resolves(self):
        """The control. If this ever fails the fix broke the working sports."""
        node = _standings_league_node(_TOURNAMENT_TABLE["standings"])
        assert node is not None and "league" in node

    def test_the_category_wrapper_resolves(self):
        """#4732 itself. This is the assertion that was false in production."""
        node = _standings_league_node(_CATEGORY_TABLE["standings"])
        assert node is not None and "league" in node

    def test_a_league_at_the_top_level_resolves(self):
        inner = {"league": [{"name": "L", "division": []}]}
        assert _standings_league_node(inner) is inner

    def test_an_unknown_wrapper_name_still_resolves(self):
        """The structural fallback.

        #4732 cost two leagues because a NAME was not on a list. A third name
        must therefore not cost a third league: any child carrying `league[]` is
        the node we were looking for, whatever the vendor calls it.
        """
        inner = {"sport": "x", "grouping": {"league": [{"name": "L"}]}}
        assert _standings_league_node(inner) == {"league": [{"name": "L"}]}

    def test_a_payload_carrying_no_league_anywhere_resolves_to_nothing(self):
        """None, not `inner` — the old code's `inner.get("tournament", inner)`
        fell back to the payload itself, so `leagues` read `[]` and the caller
        could not tell "navigated and found nothing" from "did not navigate"."""
        assert _standings_league_node({"sport": "x", "note": "nothing here"}) is None

    def test_a_non_dict_resolves_to_nothing(self):
        assert _standings_league_node(["not", "a", "dict"]) is None

    def test_the_known_wrappers_are_tried_in_a_fixed_order(self):
        """Determinism, so a payload carrying both cannot flip between runs."""
        inner = {
            "category": {"league": [{"name": "wrong"}]},
            "tournament": {"league": [{"name": "right"}]},
        }
        assert _standings_league_node(inner)["league"][0]["name"] == "right"


# =============================================================================
# 2. The unasked arms — BOTH of them, pinned so the comment cannot drift.
# =============================================================================

class TestTheUnaskedArms:

    def test_the_unasked_arms(self):
        """Soccer and tennis, and nobody else.

        Measured 2026-09-10: `/v2/soccer/standings` and `/v1/tennis/standings`
        both answer HTTP 404 while the four US sports answer 200. Nine of the
        thirteen mapped keys resolve to these two StatPal identifiers.
        """
        assert NO_STANDINGS_SPORTS == frozenset({"soccer", "tennis"})

    @pytest.mark.parametrize("sport", ["soccer", "tennis"])
    @pytest.mark.asyncio
    async def test_a_sport_with_no_standings_path_is_not_asked_at_all(
        self, sport, monkeypatch
    ):
        """Not asked, not merely unanswered — no request is spent learning a
        constant, and `asked` is False so the terminal cannot count it."""
        service = statpal_api.StatPalAPIService(api_key="test-key-not-a-real-key")
        called = []

        async def _never(*a, **k):
            called.append(a)
            return {}

        monkeypatch.setattr(service, "get_standings", _never)
        fetch = await service.get_standings_result(sport)

        assert called == []
        assert fetch.reason == "no_venue_path"
        assert fetch.asked is False
        assert fetch.is_alarm is False

    @pytest.mark.asyncio
    async def test_a_dead_read_on_a_supported_sport_is_an_alarm(self, monkeypatch):
        """The other side of gotcha #53: `None` from a sport that DOES have the
        path is a failure to read, never an authoritative empty table."""
        service = statpal_api.StatPalAPIService(api_key="test-key-not-a-real-key")

        async def _dead(*a, **k):
            return None

        monkeypatch.setattr(service, "get_standings", _dead)
        fetch = await service.get_standings_result("nfl")

        assert fetch.reason == "fetch_failed"
        assert fetch.asked is True
        assert fetch.is_alarm is True

    @pytest.mark.asyncio
    async def test_an_empty_table_is_empty_not_failed(self, monkeypatch):
        service = statpal_api.StatPalAPIService(api_key="test-key-not-a-real-key")

        async def _empty(*a, **k):
            return {}

        monkeypatch.setattr(service, "get_standings", _empty)
        fetch = await service.get_standings_result("nfl")

        assert fetch.reason == "empty"
        assert fetch.is_alarm is False


# =============================================================================
# 3. The real pass. Section 1 would pass just as well if `_sync_statpal_standings`
#    never called the navigator, and sections 1-2 would pass if it never emitted
#    a terminal — so these drive the writer itself.
# =============================================================================

def _wire_sports(monkeypatch, *sport_keys, teams=()):
    """The smallest DB rail the pass runs against: `Sport` rows, and optionally
    `Team` rows so a matched write can be observed."""
    from sqlalchemy import create_engine
    from sqlalchemy.dialects.postgresql import ARRAY, JSONB
    from sqlalchemy.ext.compiler import compiles
    from sqlalchemy.orm import Session

    @compiles(JSONB, "sqlite")
    def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
        return "JSON"

    @compiles(ARRAY, "sqlite")
    def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
        return "JSON"

    from app.models.models import Base, Event, Sport, Team, TeamIdentityMapping

    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[
            Event.__table__, Sport.__table__,
            Team.__table__, TeamIdentityMapping.__table__,
        ],
    )
    session = Session(engine, expire_on_commit=False)
    for key in sport_keys:
        session.add(Sport(key=key, name=key))
    session.commit()

    for sport_key, team_name in teams:
        sport_id = session.query(Sport).filter_by(key=sport_key).one().id
        session.add(Team(name=team_name, sport_id=sport_id))
    session.commit()

    class _AsyncShim:
        def __init__(self, s):
            self._s = s

        async def execute(self, *a, **kw):
            return self._s.execute(*a, **kw)

        async def flush(self, *a, **kw):
            return self._s.flush(*a, **kw)

        async def commit(self):
            return self._s.commit()

        async def rollback(self):
            return self._s.rollback()

        def add(self, obj):
            return self._s.add(obj)

        def __getattr__(self, name):
            return getattr(self._s, name)

    class _Ctx:
        async def __aenter__(self):
            return _AsyncShim(session)

        async def __aexit__(self, exc_type, *_):
            if exc_type:
                session.rollback()
            return False

    monkeypatch.setattr(
        "app.tasks.statpal_sync.get_task_session", lambda: _Ctx(), raising=False
    )
    return session


def _stub_venue(monkeypatch, payload_by_statpal_sport):
    """A StatPal whose standings answer depends on WHICH sport is asked.

    Keyed on the StatPal identifier (`nfl`, `soccer`) rather than our key,
    because that is what the pass passes to the client — and it is the reason
    nine of OUR keys are two of THEIRS.
    """
    class _Service:
        async def get_standings_result(self, sport, *a, **k):
            if sport in NO_STANDINGS_SPORTS:
                return statpal_api.StatPalStandingsFetch(None, "no_venue_path", sport, None)
            payload = payload_by_statpal_sport.get(sport)
            if payload is None:
                return statpal_api.StatPalStandingsFetch(None, "fetch_failed", sport, "standings")
            return statpal_api.StatPalStandingsFetch(payload, "ok", sport, "standings")

        async def get_standings(self, sport, *a, **k):
            return (await self.get_standings_result(sport)).data

        async def close(self):
            pass

    monkeypatch.setattr(statpal_api, "StatPalAPIService", _Service)
    monkeypatch.setattr(statpal_api, "is_available", lambda: True)


class TestTheRealPassEmitsTheTerminal:

    @pytest.fixture(autouse=True)
    def _no_sleep(self, monkeypatch):
        async def _sleep(*_a, **_k):
            return None

        monkeypatch.setattr("app.tasks.statpal_sync.asyncio.sleep", _sleep)

    @pytest.mark.asyncio
    async def test_the_category_sports_now_write_their_standings(self, monkeypatch):
        """THE SHIP. Before this change the same pass wrote zero NFL rows."""
        from app.models.models import Team
        from app.tasks.statpal_sync import _sync_statpal_standings

        session = _wire_sports(
            monkeypatch, "americanfootball_nfl",
            teams=[("americanfootball_nfl", "Buffalo Bills")],
        )
        _stub_venue(monkeypatch, {"nfl": _CATEGORY_TABLE})

        result = await _sync_statpal_standings("americanfootball_nfl")

        assert result["total_teams_updated"] == 1
        assert result["terminal"] == "complete"
        stored = session.query(Team).filter_by(name="Buffalo Bills").one()
        assert stored.standings_data["wins"] == 3
        assert stored.standings_data["losses"] == 1

    @pytest.mark.asyncio
    async def test_a_payload_that_parses_to_nothing_is_not_a_success(
        self, monkeypatch
    ):
        """#4732's own defect, stated as a test.

        A 200 with a shape we cannot walk is the exact production state of NFL
        and MLB for the whole life of this task, and it banked `success`.
        """
        from app.tasks.statpal_sync import _sync_statpal_standings

        _wire_sports(monkeypatch, "americanfootball_nfl")
        _stub_venue(monkeypatch, {"nfl": {"standings": {"sport": "nfl", "surprise": {}}}})

        result = await _sync_statpal_standings("americanfootball_nfl")

        assert result["terminal"] == "partial"
        assert [f["reason"] for f in result["fetch_failures"]] == ["parsed_zero_teams"]
        assert verdict_for("statpal_standings", result).verdict in NOT_GREEN

    @pytest.mark.asyncio
    async def test_a_table_that_matches_no_team_of_ours_is_not_a_success(
        self, monkeypatch
    ):
        """The sibling hole: parsing 32 teams and storing none is also a zero
        yield, and `total_teams_updated` alone cannot tell it from a good pass."""
        from app.tasks.statpal_sync import _sync_statpal_standings

        _wire_sports(monkeypatch, "americanfootball_nfl")  # no Team rows at all
        _stub_venue(monkeypatch, {"nfl": _CATEGORY_TABLE})

        result = await _sync_statpal_standings("americanfootball_nfl")

        assert result["terminal"] == "partial"
        assert [f["reason"] for f in result["fetch_failures"]] == ["matched_zero_teams"]

    @pytest.mark.asyncio
    async def test_a_dark_venue_is_failed_and_names_the_sport(self, monkeypatch):
        from app.tasks.statpal_sync import _sync_statpal_standings

        _wire_sports(monkeypatch, "americanfootball_nfl")
        _stub_venue(monkeypatch, {})  # nfl absent -> fetch_failed

        result = await _sync_statpal_standings("americanfootball_nfl")

        assert result["terminal"] == "failed"
        assert result["fetch_failures"][0]["sport"] == "americanfootball_nfl"
        assert result["fetch_failures"][0]["reason"] == "fetch_failed"
        assert verdict_for("statpal_standings", result).verdict in NOT_GREEN

    @pytest.mark.asyncio
    async def test_a_mapped_sport_with_no_row_is_named_and_grades(self, monkeypatch):
        """#4691's arm. Our own config being wrong is fixable, so it grades."""
        from app.tasks.statpal_sync import _sync_statpal_standings

        _wire_sports(monkeypatch, "basketball_nba")  # nfl mapped but not rowed
        _stub_venue(monkeypatch, {"nba": _TOURNAMENT_TABLE})

        result = await _sync_statpal_standings("americanfootball_nfl")

        assert result["sports_unasked"] == [{
            "sport": "americanfootball_nfl",
            "statpal_sport": "nfl",
            "reason": "sport_not_found",
        }]
        assert result["terminal"] == "no_work"

    @pytest.mark.asyncio
    async def test_a_pass_that_asked_nobody_says_so_rather_than_succeeding(
        self, monkeypatch
    ):
        from app.tasks.statpal_sync import _sync_statpal_standings

        _wire_sports(monkeypatch, "americanfootball_nfl")
        monkeypatch.setattr(statpal_api, "is_available", lambda: False)

        result = await _sync_statpal_standings()

        assert result["terminal"] == "skipped"

    @pytest.mark.asyncio
    async def test_an_unmapped_sport_key_is_no_work_not_complete(self, monkeypatch):
        from app.tasks.statpal_sync import _sync_statpal_standings

        _wire_sports(monkeypatch, "americanfootball_nfl")
        _stub_venue(monkeypatch, {"nfl": _CATEGORY_TABLE})

        result = await _sync_statpal_standings("quidditch_not_a_sport")

        assert result["terminal"] == "no_work"
        assert result["sports_asked"] == 0


# =============================================================================
# 4. The daily beat's own shape. This task's beat passes NO `sport_key`, which
#    is why the grading rule here diverges from the schedules task's — so the
#    divergence is pinned to the fact that justifies it, not left as prose.
# =============================================================================

class TestTheAllSportsPassStaysReadable:

    @pytest.fixture(autouse=True)
    def _no_sleep(self, monkeypatch):
        async def _sleep(*_a, **_k):
            return None

        monkeypatch.setattr("app.tasks.statpal_sync.asyncio.sleep", _sleep)

    def test_the_standings_beat_passes_no_sport_key(self):
        """The fact the divergence rests on.

        If somebody gives this beat an explicit `sport_key`, the all-sports form
        stops being the daily reality and the reasoning in the terminal comment
        needs re-reading. That is what this test is here to force.
        """
        from app.tasks import celery_app

        beats = [
            (name, entry) for name, entry in celery_app.conf.beat_schedule.items()
            if "statpal" in str(entry.get("task", "")) and "standings" in name
        ]
        assert beats, "no statpal standings beat found — has it been renamed?"
        for name, entry in beats:
            kwargs = entry.get("kwargs") or {}
            args = entry.get("args") or ()
            assert not kwargs.get("sport_key") and not args, (
                f"{name} now passes a sport_key; re-read the terminal rule in "
                "_sync_statpal_standings"
            )

    @pytest.mark.asyncio
    async def test_the_nine_unreachable_keys_are_reported_but_do_not_grade(
        self, monkeypatch
    ):
        """A healthy all-sports pass is `complete`, not permanently amber.

        Nine of thirteen mapped keys can never be asked. Grading them would put
        this task in `partial` on every run it will ever make, and a terminal
        that never changes cannot report the day a table goes empty.
        """
        from app.tasks.statpal_sync import _sync_statpal_standings
        from app.utils.sport_keys import STATPAL_SPORT_MAPPING

        # Every mapped key gets a row, because in production every mapped key
        # HAS one — verified 2026-09-10: 13 of 13. Wiring a subset would leave
        # the rest reading `sport_not_found` and grade this pass `partial` for a
        # reason that does not exist on the live system.
        _wire_sports(
            monkeypatch, *STATPAL_SPORT_MAPPING,
            teams=[
                ("americanfootball_nfl", "Buffalo Bills"),
                ("baseball_mlb", "Tampa Bay Rays"),
                ("basketball_nba", "Boston Celtics"),
                ("icehockey_nhl", "Buffalo Sabres"),
            ],
        )
        _stub_venue(monkeypatch, {
            # The wrapper each sport really uses, measured 2026-09-10.
            "nfl": _table("category", "Buffalo Bills"),
            "mlb": _table("category", "Tampa Bay Rays"),
            "nba": _table("tournament", "Boston Celtics"),
            "nhl": _table("tournament", "Buffalo Sabres"),
        })

        result = await _sync_statpal_standings()

        assert result["terminal"] == "complete"
        # Four asked, nine never spoken to — the live proportions.
        assert result["sports_asked"] == 4
        assert len(result["sports_unasked"]) == 9
        assert all(u["reason"] == "no_venue_path" for u in result["sports_unasked"])
        assert result["fetch_failures"] == []

    @pytest.mark.asyncio
    async def test_one_empty_table_still_shows_through_the_unreachable_nine(
        self, monkeypatch
    ):
        """The signal the ship exists for: the amber has to survive being sat
        next to nine permanently-unasked sports."""
        from app.tasks.statpal_sync import _sync_statpal_standings
        from app.utils.sport_keys import STATPAL_SPORT_MAPPING

        _wire_sports(
            monkeypatch, *STATPAL_SPORT_MAPPING,
            teams=[
                ("baseball_mlb", "Tampa Bay Rays"),
                ("basketball_nba", "Boston Celtics"),
                ("icehockey_nhl", "Buffalo Sabres"),
            ],
        )
        # NFL answers 200 with a shape nobody can walk — its exact production
        # state — while the other three are healthy.
        _stub_venue(monkeypatch, {
            "nfl": {"standings": {"sport": "nfl", "surprise": {}}},
            "mlb": _table("category", "Tampa Bay Rays"),
            "nba": _table("tournament", "Boston Celtics"),
            "nhl": _table("tournament", "Buffalo Sabres"),
        })

        result = await _sync_statpal_standings()

        assert result["terminal"] == "partial"
        assert [f["sport"] for f in result["fetch_failures"]] == [
            "americanfootball_nfl"
        ]
        # The three healthy sports still wrote — `partial` is a hole in a real
        # pass, not a red light over the whole task.
        assert result["total_teams_updated"] == 3


# =============================================================================
# 5. Enrollment. A terminal nobody reads is not a terminal (this file's own trap:
#    either half alone is worthless).
# =============================================================================

class TestTheTerminalIsActuallyRead:

    def test_statpal_standings_is_enrolled(self):
        assert "statpal_standings" in ENFORCED_TASKS

    def test_the_old_summary_is_still_not_authoritative_after_enrollment(self):
        """The production shape before this change, graded — and the deploy-day
        question it answers.

        `total_teams_updated: 62` with NFL and MLB at zero, and `verdict_for`
        could say nothing about it, which is why it ran for months.

        The part worth pinning is that ENROLLING the task does not change that.
        A summary with no terminal fields classifies non-authoritative UNKNOWN
        *inside* `ENFORCED_TASKS` too, so between this deploying and the first
        08:00Z run — when the cached summary is still the old shape — no surface
        turns a new red. Only the reason string moves, from
        `not_enforced(unknown:no_terminal_fields)` to `no_terminal_fields`.
        """
        old = {
            "total_teams_updated": 62,
            "details": [
                {"sport": "americanfootball_nfl", "teams_in_standings": 0,
                 "teams_updated": 0},
                {"sport": "basketball_nba", "teams_in_standings": 30,
                 "teams_updated": 30},
                {"sport": "baseball_mlb", "teams_in_standings": 0,
                 "teams_updated": 0},
                {"sport": "icehockey_nhl", "teams_in_standings": 32,
                 "teams_updated": 32},
            ],
        }
        verdict = verdict_for("statpal_standings", old)
        assert verdict.verdict in NOT_GREEN
        assert verdict.reason == "no_terminal_fields"
        assert verdict.authoritative is False

    def test_the_same_pass_under_the_new_contract_is_amber(self):
        """The same day's work, now gradeable: two sports read, two empty."""
        now = {
            "terminal": "partial",
            "fetch_failures": [
                {"sport": "americanfootball_nfl", "statpal_sport": "nfl",
                 "reason": "parsed_zero_teams", "endpoint": "standings"},
                {"sport": "baseball_mlb", "statpal_sport": "mlb",
                 "reason": "parsed_zero_teams", "endpoint": "standings"},
            ],
            "sports_asked": 4,
            "sports_unasked": [],
            "total_teams_updated": 62,
            "details": [],
        }
        verdict = verdict_for("statpal_standings", now)
        assert verdict.verdict in NOT_GREEN
        assert verdict.authoritative is True


# =============================================================================
# 6. The diagnostic that could not have caught this.
# =============================================================================

class TestTheZeroYieldLogNamesTheKeysThatDiffer:

    @pytest.fixture(autouse=True)
    def _no_sleep(self, monkeypatch):
        async def _sleep(*_a, **_k):
            return None

        monkeypatch.setattr("app.tasks.statpal_sync.asyncio.sleep", _sleep)

    @pytest.mark.asyncio
    async def test_the_log_prints_the_inner_keys_not_just_the_outer_one(
        self, monkeypatch, caplog
    ):
        """The old line printed `['standings']` — identical for the two broken
        sports and the two working ones. The discriminating keys are one level
        in, and printing them is the difference between a diagnostic and a
        decoration."""
        from app.tasks.statpal_sync import _sync_statpal_standings

        _wire_sports(monkeypatch, "americanfootball_nfl")
        _stub_venue(monkeypatch, {
            "nfl": {"standings": {"sport": "nfl", "category": {"unexpected": 1}}}
        })

        with caplog.at_level("WARNING"):
            await _sync_statpal_standings("americanfootball_nfl")

        logged = "\n".join(r.getMessage() for r in caplog.records)
        assert "category" in logged, (
            "the zero-yield log must name the keys that differ between a sport "
            f"that parses and one that does not; got: {logged!r}"
        )
