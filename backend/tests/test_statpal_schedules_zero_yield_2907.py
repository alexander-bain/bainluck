"""#2907 (acceptance bullet 2) / authority/096 — a dark schedule feed stops
banking a success.

WHAT IS BROKEN. `sync_statpal_schedules` is the task whose whole job is #2867's
ship: every game exists on the site before a market lists it. Read from
production on 2026-09-10 04:2xZ:

    GET /api/admin/task-metrics?task=statpal_schedules
        starts_24h: 15 | successes_24h: 15 | failures_24h: 0 | terminal: None

`terminal` is **None**, and `statpal_schedules` is not in
`task_verdict.ENFORCED_TASKS` — so `verdict_for` downgrades whatever
`classify_summary` computes to a non-authoritative `unknown`. Three different
runs therefore bank the identical green row:

    1. asked, got 374 fixtures, correctly wrote 0   (today: NFL is already
       complete from ESPN/The Odds API, so 0 created is the RIGHT answer)
    2. asked, and the venue answered with nothing
    3. could not ask at all

(1) is health and (3) is an outage, and nothing anywhere distinguishes them.
This is gotcha #53 on the discovery path, and it is the same collapse
`get_injuries_result` was built to undo one endpoint over — see
`test_statpal_injuries_soccer.py`, whose shape this file deliberately mirrors.

WHY THE SOCCER PATH MAKES (3) UNREACHABLE BY ANY PROBE. `get_fixtures("soccer")`
reads `matches/daily` at offset 1 then offset 2. `_get` returns None on every
failure mode (401/429/non-200/non-JSON/complaint-body), each arm degrades to
`[]`, so a TOTAL upstream failure returns `[]` — byte-identical to "no soccer
fixtures in the next two days". The comment that sits over that code claims
`get_live_scores()` covers today, and it does not: soccer is in
`LIVESCORES_INGESTION_DARK_SPORTS = frozenset({"soccer"})`, so that call returns
`[]` by decision.

NOT RAISING, AND THAT IS THE ISSUE'S OWN RULING, not a preference of mine:
"a sync task that dies on a bad upstream day is worse than one that skips a
cycle. The right fix here is probably a loud zero-yield verdict, not a raise."
So the fetch outcome travels in the summary and the terminal, and every existing
caller of `get_fixtures` keeps its list.
"""
import httpx
import pytest
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles

from app.services.statpal_api import (
    LIVESCORES_INGESTION_DARK_SPORTS,
    StatPalAPIService,
)
from app.utils.task_verdict import ENFORCED_TASKS, FAILED, UNKNOWN, verdict_for


# `Event` carries Postgres JSONB/ARRAY columns that sqlite cannot render as DDL.
# The repo's standing shim (see `test_authority_failover_3473`), so the rail in
# section 5 can create the real tables from the real models.
@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@pytest.fixture
def service():
    return StatPalAPIService(api_key="test-key-not-a-real-key")


def _resp(status, url, *, json_body=None, text=None):
    req = httpx.Request("GET", url)
    if text is not None:
        return httpx.Response(status, text=text, request=req)
    return httpx.Response(status, json=json_body if json_body is not None else {}, request=req)


#: A 200 that is a real envelope carrying zero games. Deliberately TRUTHY: a
#: falsy `{}` would take `get_fixtures`' own `if not data` shortcut and so could
#: never tell an empty board apart from a dead one.
_EMPTY_BOARD = {"schedule": {"matches": []}}


# =============================================================================
# 1. A failed schedule read is not an empty schedule. Gotcha #53, at the client.
# =============================================================================

class TestAFailedReadIsNotAnEmptySchedule:

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status_code", [401, 404, 429, 500])
    async def test_every_dead_response_reads_as_fetch_failed(
        self, service, monkeypatch, status_code
    ):
        """Each of these already returns None from `_get` for its own reason.
        The point is that the CALLER stops turning all four into `[]`."""
        async def fake_http_get(url, params=None):
            return _resp(status_code, url)

        monkeypatch.setattr(service.client, "get", fake_http_get)
        result = await service.get_fixtures_result("nfl")

        assert result.fixtures == []
        assert result.reason == "fetch_failed"
        assert result.is_alarm is True

    @pytest.mark.asyncio
    async def test_a_two_hundred_that_is_an_error_body_reads_as_fetch_failed(
        self, service, monkeypatch
    ):
        """The vendor's `invalid-request` 200 — it has a body, so a caller
        checking only the status code parses it as data."""
        async def fake_http_get(url, params=None):
            return _resp(200, url, text="invalid-request")

        monkeypatch.setattr(service.client, "get", fake_http_get)
        assert (await service.get_fixtures_result("nfl")).reason == "fetch_failed"

    @pytest.mark.asyncio
    async def test_a_real_but_empty_board_is_empty_not_failed(self, service, monkeypatch):
        """The control, and the reason `empty` is its own reason: a genuinely
        quiet board must NOT raise an alarm, or the alarm stops meaning
        anything. This is the assertion that keeps the fix honest — it would be
        trivial to make every zero-row day look like an outage."""
        async def fake_http_get(url, params=None):
            return _resp(200, url, json_body=_EMPTY_BOARD)

        monkeypatch.setattr(service.client, "get", fake_http_get)
        result = await service.get_fixtures_result("nfl")

        assert result.fixtures == []
        assert result.reason == "empty"
        assert result.is_alarm is False

    @pytest.mark.asyncio
    async def test_a_falsy_but_real_payload_is_empty_not_failed(
        self, service, monkeypatch
    ):
        """`_get` signals failure with `None` and ONLY `None`. A 200 carrying a
        bare `{}` is a real answer meaning "nothing here", so the failure test
        has to be `is None` — `if not data` would report it as an outage.

        Added because a mutant flipping exactly that survived the first sweep:
        every other test in this class uses a truthy payload, so nothing pinned
        the distinction, and the false-alarm direction is the one this whole
        ship is trying not to introduce.
        """
        async def fake_http_get(url, params=None):
            return _resp(200, url, json_body={})

        monkeypatch.setattr(service.client, "get", fake_http_get)
        result = await service.get_fixtures_result("nfl")

        assert result.reason == "empty"
        assert result.is_alarm is False

    @pytest.mark.asyncio
    async def test_the_list_wrapper_still_returns_a_list(self, service, monkeypatch):
        """`get_fixtures` keeps its signature and its type, so none of its four
        live callers changes — `statpal_sync:253`, `admin_providers:2410` and
        the two authority reads."""
        async def fake_http_get(url, params=None):
            return _resp(200, url, json_body=_EMPTY_BOARD)

        monkeypatch.setattr(service.client, "get", fake_http_get)
        assert await service.get_fixtures("nfl") == []


# =============================================================================
# 2. Soccer reads two boards, so it has a THIRD outcome the others do not.
# =============================================================================

class TestSoccersTwoArmsReportPartialFailure:

    @staticmethod
    def _by_offset(outcomes):
        """Transport that answers each `offset` differently."""
        asked = []

        async def fake_http_get(url, params=None):
            offset = (params or {}).get("offset")
            asked.append(offset)
            status, body = outcomes[offset]
            return _resp(status, url, json_body=body)

        return fake_http_get, asked

    @pytest.mark.asyncio
    async def test_both_arms_dead_is_fetch_failed_not_an_empty_schedule(
        self, service, monkeypatch
    ):
        """The production-invisible case. Before this, a soccer day where the
        venue was entirely dark returned `[]` and the pass reported success."""
        fake, _ = self._by_offset({1: (500, None), 2: (500, None)})
        monkeypatch.setattr(service.client, "get", fake)

        result = await service.get_fixtures_result("soccer")
        assert result.fixtures == []
        assert result.reason == "fetch_failed"
        assert result.is_alarm is True

    @pytest.mark.asyncio
    async def test_one_dead_arm_is_partial_and_keeps_what_it_did_read(
        self, service, monkeypatch
    ):
        """Half a schedule is not a schedule, and it is not an outage either.
        Losing the distinction in either direction is the bug."""
        fake, _ = self._by_offset({1: (500, None), 2: (200, _EMPTY_BOARD)})
        monkeypatch.setattr(service.client, "get", fake)

        result = await service.get_fixtures_result("soccer")
        assert result.reason == "partial_fetch"
        assert result.is_alarm is True

    @pytest.mark.asyncio
    async def test_both_arms_answering_an_empty_board_is_not_an_alarm(
        self, service, monkeypatch
    ):
        fake, _ = self._by_offset({1: (200, _EMPTY_BOARD), 2: (200, _EMPTY_BOARD)})
        monkeypatch.setattr(service.client, "get", fake)

        result = await service.get_fixtures_result("soccer")
        assert result.reason == "empty"
        assert result.is_alarm is False


# =============================================================================
# 3. The offsets do not move — #3800's suggested fix, refuted and made
#    executable so the next reader cannot be misled by prose again.
# =============================================================================

class TestSoccerStillAsksOnlyTomorrowAndTheDayAfter:
    """A DRIFT GUARD, not a bug fix: today's behaviour is already correct and
    these pin it with the reason attached.

    #3800 proposed reading `offset=0` "for today", on the strength of the
    comment in `get_fixtures`. That comment is false in three ways (it says
    offset=0 is unsupported, it says `get_live_scores()` compensates, and it
    says "Fetch today" while setting offset=1), and the fix it invites is
    actively dangerous: `matches/daily?offset=0` is `matches/live` BYTE FOR BYTE
    (measured three times — #3800 05:08Z 2026-09-07, again 12:07Z 2026-09-09,
    and by authority/081 on #4320), so it is a board of IN-PROGRESS matches.
    Feeding those to the discovery writer creates rows: under ruling 048 a
    StatPal listing claim is not id-anchored, so it never absorbs — it CREATES,
    at ~197 rows a day, which is #3607's warning and #4520's symptom.

    So the comment gets corrected and the behaviour gets pinned here instead.
    """

    @pytest.mark.asyncio
    async def test_soccer_asks_offsets_one_and_two_and_never_zero(
        self, service, monkeypatch
    ):
        asked = []

        async def fake_http_get(url, params=None):
            asked.append((params or {}).get("offset"))
            return _resp(200, url, json_body=_EMPTY_BOARD)

        monkeypatch.setattr(service.client, "get", fake_http_get)
        await service.get_fixtures_result("soccer")

        assert asked == [1, 2], (
            "offset=0 is matches/live, not a schedule board — adding it here "
            "mints event rows for in-progress matches (ruling 048, #3607)"
        )
        assert 0 not in asked

    def test_the_compensation_the_old_comment_promised_does_not_exist(self):
        """`get_live_scores("soccer")` returns `[]` BY DECISION, so the removed
        comment's "we'll fetch today's live scores instead" was never true. If
        this constant ever loses soccer, the comment's claim becomes reachable
        and this guard should be re-read rather than deleted."""
        assert "soccer" in LIVESCORES_INGESTION_DARK_SPORTS


# =============================================================================
# 4. The pass states a terminal, and the verdict is authoritative.
# =============================================================================

class TestTheScheduleTaskCanReportADarkVenue:

    def test_statpal_schedules_is_enrolled(self):
        """Without enrolment `verdict_for` downgrades every classification to a
        non-authoritative `unknown`, so a `terminal: failed` would still be
        recorded as a bare returning invocation — the whole defect."""
        assert "statpal_schedules" in ENFORCED_TASKS

    def test_a_dark_pass_is_authoritatively_failed(self):
        summary = {
            "terminal": "failed",
            "events_created": 0,
            "events_updated": 0,
            "fetch_failures": [{"sport": "soccer_epl", "reason": "fetch_failed"}],
        }
        verdict = verdict_for("statpal_schedules", summary)
        assert verdict.verdict == FAILED
        assert verdict.authoritative is True

    def test_a_quiet_but_healthy_pass_is_not_an_alarm(self):
        """The control that stops this becoming a pager that cries wolf: 374
        fixtures fetched and 0 written is what a complete NFL season looks
        like, and it must stay green."""
        summary = {
            "terminal": "complete",
            "events_created": 0,
            "events_updated": 0,
            "total_fixtures_fetched": 374,
            "fetch_failures": [],
        }
        verdict = verdict_for("statpal_schedules", summary)
        assert verdict.verdict != FAILED

    def test_the_old_terminalless_summary_would_not_have_been_authoritative(self):
        """Pins the defect this ship removes, from the production summary shape
        read on 2026-09-10: no `terminal`, no `status`, so `_LEGACY` — an
        outage and a healthy pass were the same non-authoritative unknown."""
        legacy = {
            "events_created": 0,
            "events_updated": 0,
            "total_fixtures_fetched": 374,
            "sports": [{"sport": "americanfootball_nfl", "fixtures_fetched": 374}],
        }
        verdict = verdict_for("statpal_schedules", legacy)
        assert verdict.verdict == UNKNOWN
        assert verdict.authoritative is False


# =============================================================================
# 5. The terminal is asserted on the REAL pass, not on a summary I typed.
#
#    Group 4 proves `verdict_for` reads a terminal correctly; it would pass just
#    as well if `_sync_statpal_schedules` never emitted one. These drive the
#    writer itself. (The lesson is authority/095's: a rule that lives in one
#    place needs a test where it is USED, or a mutant survives in the gap.)
# =============================================================================

def _wire_one_sport(monkeypatch, sport_key="americanfootball_nfl"):
    """The smallest DB rail the pass will run against: one `Sport` row.

    This file's subject is the TERMINAL, not row writing — #4307 and #2963 own
    that and have the full twin rail. The tables exist only so the loop reaches
    its return statement.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

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
    session.add(Sport(key=sport_key, name=sport_key))
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


def _stub_venue(monkeypatch, reason):
    """A StatPal whose schedule read lands on `reason` for every sport."""
    import app.services.statpal_api as statpal_api

    class _Service:
        async def get_fixtures_result(self, sport, *a, **k):
            return statpal_api.StatPalFixtureFetch(
                [], reason, sport, "season-schedule"
            )

        async def get_fixtures(self, *a, **k):
            return (await self.get_fixtures_result(*a, **k)).fixtures

        async def get_live_scores(self, sport):
            return []

        async def close(self):
            pass

    monkeypatch.setattr(statpal_api, "StatPalAPIService", _Service)
    monkeypatch.setattr(statpal_api, "is_available", lambda: True)


class TestTheRealPassEmitsTheTerminal:

    @pytest.fixture(autouse=True)
    def _no_pacing(self, monkeypatch):
        async def _sleep(_s):
            return None

        monkeypatch.setattr("app.tasks.statpal_sync.asyncio.sleep", _sleep)

    @pytest.mark.asyncio
    async def test_a_dark_venue_is_failed_and_names_the_sport(self, monkeypatch):
        """The production-invisible case, end to end. Before this, this exact
        pass returned a summary with no terminal and banked a success."""
        from app.tasks.statpal_sync import _sync_statpal_schedules

        _wire_one_sport(monkeypatch)
        _stub_venue(monkeypatch, "fetch_failed")

        result = await _sync_statpal_schedules("americanfootball_nfl")

        assert result["terminal"] == "failed"
        assert [f["sport"] for f in result["fetch_failures"]] == [
            "americanfootball_nfl"
        ]
        verdict = verdict_for("statpal_schedules", result)
        assert verdict.verdict == FAILED
        assert verdict.authoritative is True

    @pytest.mark.asyncio
    async def test_a_quiet_venue_is_complete_and_names_nobody(self, monkeypatch):
        """The control, and the one that stops this being a pager that cries
        wolf: an empty board is a fact about the day, not an outage."""
        from app.tasks.statpal_sync import _sync_statpal_schedules

        _wire_one_sport(monkeypatch)
        _stub_venue(monkeypatch, "empty")

        result = await _sync_statpal_schedules("americanfootball_nfl")

        assert result["terminal"] == "complete"
        assert result["fetch_failures"] == []
        assert verdict_for("statpal_schedules", result).verdict != FAILED

    @pytest.mark.asyncio
    async def test_a_partial_read_is_partial_not_failed(self, monkeypatch):
        """Soccer's two-board case arriving at the writer. `partial_fetch` is an
        alarm, but it is NOT the total outage — a pass that read half a
        schedule still wrote from it."""
        from app.tasks.statpal_sync import _sync_statpal_schedules

        _wire_one_sport(monkeypatch)
        _stub_venue(monkeypatch, "partial_fetch")

        result = await _sync_statpal_schedules("americanfootball_nfl")

        # The ONLY sport asked alarmed, and the terminal is still `partial` —
        # `failed` is reserved for a venue that could not be read at all. This
        # assertion is the reason the distinction exists: an earlier draft
        # counted any alarm towards `failed` and reported a half-read soccer
        # board as a total outage.
        assert result["terminal"] == "partial"
        assert result["fetch_failures"][0]["reason"] == "partial_fetch"
        verdict = verdict_for("statpal_schedules", result)
        assert verdict.verdict != FAILED
        assert verdict.authoritative is True

    @pytest.mark.asyncio
    async def test_a_pass_that_never_ran_says_so_rather_than_succeeding(
        self, monkeypatch
    ):
        """No API key: a deliberate no-op. `skipped` is authoritative `unknown`
        — it must not read as a completed pass, and must not read as failure."""
        import app.services.statpal_api as statpal_api

        from app.tasks.statpal_sync import _sync_statpal_schedules

        monkeypatch.setattr(statpal_api, "is_available", lambda: False)
        result = await _sync_statpal_schedules("americanfootball_nfl")

        assert result["terminal"] == "skipped"
        verdict = verdict_for("statpal_schedules", result)
        assert verdict.verdict == UNKNOWN
        assert verdict.authoritative is True

    @pytest.mark.asyncio
    async def test_an_unmapped_sport_key_is_skipped_not_complete(self, monkeypatch):
        from app.tasks.statpal_sync import _sync_statpal_schedules

        import app.services.statpal_api as statpal_api

        monkeypatch.setattr(statpal_api, "is_available", lambda: True)
        result = await _sync_statpal_schedules("quidditch_premier")

        assert result["terminal"] == "skipped"
