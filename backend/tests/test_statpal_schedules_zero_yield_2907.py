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

import app.services.statpal_api as statpal_api
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
    return statpal_api.StatPalAPIService(api_key="test-key-not-a-real-key")


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
        assert "soccer" in statpal_api.LIVESCORES_INGESTION_DARK_SPORTS


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


def _wire_sports(monkeypatch, *sport_keys):
    """`_wire_one_sport` with more than one row, for the mixed control.

    The mixed case cannot be built from one sport by construction: it needs a
    sport that IS asked standing beside one that is not.
    """
    session = _wire_one_sport(monkeypatch, sport_key=sport_keys[0])
    from app.models.models import Sport

    for key in sport_keys[1:]:
        session.add(Sport(key=key, name=key))
    session.commit()
    return session


def _stub_venue_by_sport(monkeypatch, reason_by_statpal_sport):
    """A StatPal whose reason depends on WHICH sport is asked.

    Keyed on the StatPal identifier (`nfl`, `soccer`), not on our key, because
    that is what the pass passes to the client — and it is the reason the
    day-board sports are nine of our keys but only two of theirs.
    """
    class _Service:
        async def get_fixtures_result(self, sport, *a, **k):
            return statpal_api.StatPalFixtureFetch(
                [], reason_by_statpal_sport[sport], sport, "season-schedule"
            )

        async def get_fixtures(self, *a, **k):
            return (await self.get_fixtures_result(*a, **k)).fixtures

        async def get_live_scores(self, sport):
            return []

        async def close(self):
            pass

    monkeypatch.setattr(statpal_api, "StatPalAPIService", _Service)
    monkeypatch.setattr(statpal_api, "is_available", lambda: True)


def _stub_venue(monkeypatch, reason):
    """A StatPal whose schedule read lands on `reason` for every sport."""
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

        monkeypatch.setattr(statpal_api, "is_available", lambda: True)
        result = await _sync_statpal_schedules("quidditch_premier")

        assert result["terminal"] == "skipped"


# =============================================================================
# 6. A pass that asked NOBODY is not a pass that heard from everybody.
#
#    The gap the rest of this file left open. Sections 1-5 all reason about what
#    the VENUE said; this one is about the pass never reaching the venue at all.
#    `sports_asked` was already carried as the denominator and its docstring
#    already said this sentence — but the terminal fell through to the `else`,
#    so zero-asked landed on `complete`: the one word this whole issue exists to
#    stop a silent pass from saying.
#
#    `golf_pga` is not a hypothetical. It is in `STATPAL_SPORT_MAPPING` and it
#    has NO `sports` row in production (measured 2026-09-09 via db-query: 13 of
#    the 14 mapped keys resolve, golf_pga is the one that does not), so the
#    single-sport call skips it at `sport_not_found` before the fetch. No beat
#    passes it today — the four `sync-statpal-schedules-*` entries are
#    nba/nhl/mlb/nfl — so this is reachable through the admin trigger and
#    through any future per-sport caller, including the #4434 failover path
#    that calls `_sync_statpal_schedules(sport_key)` in-line.
# =============================================================================


def _wire_tables_without(monkeypatch, absent_key):
    """The same rail as `_wire_one_sport`, with the asked sport ABSENT.

    A different sport row is present, so the failure under test is "this sport
    has no row", not "the table is empty" — the pass must be seen to look and
    come back with nobody, rather than to have had nowhere to look.
    """
    session = _wire_one_sport(monkeypatch, sport_key="basketball_nba")
    from app.models.models import Sport

    assert (
        session.query(Sport).filter_by(key=absent_key).one_or_none() is None
    ), f"rail is wrong: {absent_key} must be absent for this test to mean anything"
    return session


class TestAPassThatAskedNobodyDoesNotReportSuccess:

    @pytest.fixture(autouse=True)
    def _no_pacing(self, monkeypatch):
        async def _sleep(_s):
            return None

        monkeypatch.setattr("app.tasks.statpal_sync.asyncio.sleep", _sleep)

    @pytest.mark.asyncio
    async def test_a_mapped_sport_with_no_row_is_no_work_not_complete(
        self, monkeypatch
    ):
        """The production specimen. Zero sports asked, zero rows written, and
        before this the summary said `complete` — a green row for a pass that
        did nothing, which is gotcha #53 one layer above the venue."""
        from app.tasks.statpal_sync import _sync_statpal_schedules

        _wire_tables_without(monkeypatch, "golf_pga")
        _stub_venue(monkeypatch, "ok")

        result = await _sync_statpal_schedules("golf_pga")

        assert result["sports_asked"] == 0
        assert result["terminal"] == "no_work"
        assert result["fetch_failures"] == []
        # `no_work` is authoritative UNKNOWN, exactly like `skipped`: this pass
        # is not a failure — nothing is broken upstream — but it is emphatically
        # not a success either, and the point is that it can no longer be read
        # as one.
        verdict = verdict_for("statpal_schedules", result)
        assert verdict.verdict == UNKNOWN
        assert verdict.authoritative is True

    @pytest.mark.asyncio
    async def test_the_skipped_sport_is_named_not_merely_uncounted(
        self, monkeypatch
    ):
        """A terminal that says "nothing happened" is only useful if the summary
        also says WHICH sport went unasked."""
        from app.tasks.statpal_sync import _sync_statpal_schedules

        _wire_tables_without(monkeypatch, "golf_pga")
        _stub_venue(monkeypatch, "ok")

        result = await _sync_statpal_schedules("golf_pga")

        # The per-sport diagnostics travel under `sports`, not `details` — the
        # local list is named `details` inside the pass and renamed on the way
        # out, which is worth pinning so a future reader does not go looking for
        # a key that is not there.
        assert {"sport": "golf_pga", "status": "sport_not_found"} in result["sports"]

    @pytest.mark.asyncio
    async def test_a_sport_that_was_asked_still_grades_on_what_it_heard(
        self, monkeypatch
    ):
        """The control that stops the fix over-firing, and the reason
        `sports_asked` is the denominator rather than `len(sport_keys)`.

        A sweep in which one sport is unrowed and another is genuinely dark must
        report `failed` — the unasked sport must neither dilute the failure into
        `partial` nor be counted as a venue that answered.
        """
        from app.tasks.statpal_sync import _sync_statpal_schedules

        _wire_tables_without(monkeypatch, "golf_pga")
        _stub_venue(monkeypatch, "fetch_failed")

        monkeypatch.setattr(
            "app.tasks.statpal_sync.STATPAL_SPORT_MAPPING",
            {"golf_pga": "pga", "basketball_nba": "nba"},
        )

        result = await _sync_statpal_schedules()

        assert result["sports_asked"] == 1
        assert [f["sport"] for f in result["fetch_failures"]] == ["basketball_nba"]
        assert result["terminal"] == "failed"
        assert verdict_for("statpal_schedules", result).verdict == FAILED


# =============================================================================
# 7. A sport we LOOPED OVER is not a sport we ASKED — repair
#    `2907-NO-DAY-TOKEN-IS-NOT-A-SUCCESS` (CERT-2467).
#
#    Section 6 caught the sports dropped BEFORE the fetch (`sport_not_found`).
#    It missed the ones the fetch itself declines to ask about. A day-board
#    sport is mapped, rowed, and reached — and `get_fixtures_result` hands back
#    `no_day_token` without an HTTP request, because its schedule is served one
#    calendar board at a time and this method has no offset argument.
#
#    `no_day_token` is correctly NOT an alarm (it is a permanent property of
#    StatPal's product, not an outage), and `sports_asked += 1` sat one line
#    under a result object carrying `asked` for exactly this question. So the
#    counter counted it, and the terminal called the pass `complete`.
#
#    This is the bigger half of the issue by population: NINE of the thirteen
#    mapped keys are day-board — soccer ×7, tennis ×2 — so the all-sports form
#    of this call has nine unasked sports on EVERY run, where `sport_not_found`
#    had one and now has none.
# =============================================================================


class TestASportWeLoopedOverIsNotASportWeAsked:

    @pytest.fixture(autouse=True)
    def _no_pacing(self, monkeypatch):
        async def _sleep(_s):
            return None

        monkeypatch.setattr("app.tasks.statpal_sync.asyncio.sleep", _sleep)

    @pytest.mark.asyncio
    async def test_mapped_day_board_pass_that_asks_nobody_cannot_complete(
        self, monkeypatch
    ):
        """The repair's named test. Every sport mapped, rowed, reached — and
        none of them asked, because all of them are day-board.

        `sports_asked` has to read 0 and not 2. The sports were looped over and
        the loop is not the question; a schedule sync that made no schedule
        request banked a green row, which is gotcha #53 wearing its third face
        in this one task.
        """
        from app.tasks.statpal_sync import _sync_statpal_schedules

        _wire_sports(monkeypatch, "soccer_epl", "tennis_atp")
        monkeypatch.setattr(
            "app.tasks.statpal_sync.STATPAL_SPORT_MAPPING",
            {"soccer_epl": "soccer", "tennis_atp": "tennis"},
        )
        _stub_venue_by_sport(
            monkeypatch, {"soccer": "no_day_token", "tennis": "no_day_token"}
        )

        result = await _sync_statpal_schedules()

        assert result["sports_asked"] == 0
        assert result["terminal"] == "no_work"
        # Not an alarm, and must not be laundered into one: `no_day_token` is
        # StatPal's product, not StatPal being down.
        assert result["fetch_failures"] == []

        # Named, not merely uncounted.
        assert sorted(u["sport"] for u in result["sports_unasked"]) == [
            "soccer_epl",
            "tennis_atp",
        ]
        assert {u["reason"] for u in result["sports_unasked"]} == {"no_day_token"}

        verdict = verdict_for("statpal_schedules", result)
        assert verdict.verdict == UNKNOWN
        assert verdict.authoritative is True

    @pytest.mark.asyncio
    async def test_a_mixed_pass_is_partial_not_complete(self, monkeypatch):
        """The mixed control, and the one that decides the repair's shape.

        Four sports read and nine never spoken to is a real pass — not `failed`,
        not `no_work` — but it is not `complete` either, because `complete` says
        the sync covered the sports it names. Here NFL answers and soccer is
        never asked.

        Both arms are asserted. A repair that made every mixed pass `no_work`
        would pass the test above and throw away the four sports that DID read,
        so the NFL side is checked as read, not merely as present.
        """
        from app.tasks.statpal_sync import _sync_statpal_schedules

        _wire_sports(monkeypatch, "americanfootball_nfl", "soccer_epl")
        monkeypatch.setattr(
            "app.tasks.statpal_sync.STATPAL_SPORT_MAPPING",
            {"americanfootball_nfl": "nfl", "soccer_epl": "soccer"},
        )
        _stub_venue_by_sport(monkeypatch, {"nfl": "ok", "soccer": "no_day_token"})

        result = await _sync_statpal_schedules()

        assert result["sports_asked"] == 1
        assert result["terminal"] == "partial"
        assert result["fetch_failures"] == []
        assert [u["sport"] for u in result["sports_unasked"]] == ["soccer_epl"]

    @pytest.mark.asyncio
    async def test_an_all_asked_pass_is_still_complete(self, monkeypatch):
        """The over-fire control.

        `partial` on any unasked sport is only correct if a pass with NO unasked
        sports still reads green. Without this, widening the gate to fire on
        every pass would satisfy both tests above and take the terminal's one
        success value out of use — the same failure the `374 fetched, 0 created`
        note in the task guards against.
        """
        from app.tasks.statpal_sync import _sync_statpal_schedules

        _wire_sports(monkeypatch, "americanfootball_nfl", "basketball_nba")
        monkeypatch.setattr(
            "app.tasks.statpal_sync.STATPAL_SPORT_MAPPING",
            {"americanfootball_nfl": "nfl", "basketball_nba": "nba"},
        )
        _stub_venue_by_sport(monkeypatch, {"nfl": "ok", "nba": "empty"})

        result = await _sync_statpal_schedules()

        assert result["sports_asked"] == 2
        assert result["sports_unasked"] == []
        assert result["terminal"] == "complete"
