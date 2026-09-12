"""#5688 — a time qualifier must not empty `/api/events/search`.

WHAT WENT WRONG, AND WHY IT NEEDED A SECOND FIX. T2-3 (#5060) taught the
identity-resolving steps of `/typeahead` to read the SUBJECT of a reader's
question rather than the raw string. It stopped there. `/search` — the page a
reader actually lands on, and the one the dropdown sends them to — kept handing
the raw query to every filter it owns. MEASURED on production 2026-09-12, the
same minute, before this ship::

    q=lazio           results 7   teams 1   futures 10
    q=lazio today     results 0   teams 0   futures 0
    q=red sox         results 23  teams 2   futures 10
    q=red sox today   results 0   teams 0   futures 0
    q=lazio 2026      results 0   teams 0   futures 1

Lazio had a game that very day. The reader who typed the extra word — the one
who asked most precisely — was told the game did not exist.

WHY THIS FILE DRIVES THE ROUTE, which is the whole point of it. There is already
a suite that drives `parse_intent` directly and proves the mechanism. It cannot
prove REACH: it composes the functions itself, so it stays green while the route
ignores them — and that is not a hypothetical, it is exactly how `/search` was
left dark for two days after `/typeahead` was fixed. A unit test on the parser
passes today and the page is still empty. So every assertion below goes through
`GET /api/events/search`.

**NON-VACUITY.** The seeded session answers any SELECT with the same rows
whatever the WHERE clause says, so "did the right rows come back" could never
see a filter change — the assertion would be about the mock. What bites instead
is the COMPILED PARAMETERS of the statements the route actually built: with the
fix, "today" appears in no bound value on the teams arm; without it, "today" is
bound as a term the team must ALSO match, which is precisely why the pool came
back empty in production. `TestTheSeedIsReal` fails loudly if the seed stops
reaching the page at all, so the bound-value assertions can never pass by
default.

**THE ARM-BY-ARM CLAUSE, and it is the reason this file is not three lines.**
The production measurement shows EVERY arm emptying — results, teams and
futures — not just the obvious one. Substituting the subject at the ILIKE
pattern alone would leave the teams, futures, concept and match-class arms dark
and still let someone call the ship paid. So each arm is asserted separately,
and each assertion is written so that restoring `q` at THAT site alone reddens
it. Partial substitution is the two-rules trap `/typeahead`'s own comment names.

**THE TWO HALVES.** `TestTheQualifierDoesNotEmptyThePage` and
`TestEveryIdentityArmReceivesTheSubject` cover the identity half — the page
stops emptying. `TestTheNamedDayLeads` covers the ordering half, which #5688's
acceptance asks for in the same breath ("with the same-day row first") and
without which the qualifier is merely decorative: `lazio today` would serve the
Sep 19 fixture above the Sep 12 game being played, because `status_order` ranks
`scheduled` over `completed`. That is CERT-2735's defect on this arm, so it is
guarded here rather than deferred.

The ordering half is asserted against the ORDER BY the route COMPILED rather
than against served rows, and that is not a shortcut: the events arm is
paginated, so "first" is a property of the whole ordered set that a mocked page
cannot exhibit. The clause is the artefact that decides it.

**MUTATION RECORD** — every identity site reverted to the raw `q`, one at a
time, against a committed tree. This file was WRITTEN against the survivors of
the first pass; five of them survived its first draft and three of those are
the reason `TestThePythonSideIdentitySitesReceiveTheSubject` and
`TestTheDayKeyIsBuiltInTheEasternCalendar` exist at all.

===========================  ==========  ====================================
site                         verdict     killed by
===========================  ==========  ====================================
term split                   KILLED      this file (3 tests)
FTS rank expression          KILLED      this file (2 tests)
teams filter                 KILLED      this file (2 tests)
teams rank                   KILLED      this file (2 tests)
futures prefix tsquery       KILLED      this file (2 tests)
match-class scorer, teams    KILLED      this file, after the spy was added
match-class scorer, concepts KILLED      this file, after the spy was added
day-order key removed        KILLED      this file (3 tests)
day key below `status_order` KILLED      this file
day key in UTC not Eastern   KILLED      this file, on a pinned clock
concept provenance           KILLED      `test_search_scorer_wiring.py`
trigram fuzzy arm            KILLED      `test_search_latency_contract.py`
`search_pattern` ILIKE       EQUIVALENT  nothing — the variable was DEAD, read
                                         nowhere in the backend, and is deleted
===========================  ==========  ====================================

The last row is why the sweep was worth running: the one mutant nothing killed
turned out to be unkillable, and finding that out is what removed a dead
assignment that read exactly like a live identity site.
"""

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw

pytestmark = pytest.mark.asyncio

SEARCH = "/api/events/search"


def _team_row():
    return SimpleNamespace(
        id=701,
        name="Lazio",
        slug="lazio",
        abbreviation="LAZ",
        sport_id=5,
        logo_url_small="https://example.test/lazio.png",
        current_record="2-1-0",
        sport_key="soccer_italy_serie_a",
        alternate_names=["SS Lazio", "Biancocelesti"],
        team_rank=0.9,
    )


def _futures_row():
    return SimpleNamespace(
        id=9101,
        name="Lazio to Win Serie A",
        external_id="kxseriea-laz-2026",
        market_tier=2,
        market_type="championship",
        category="sports",
        llm_sport_category="soccer_italy_serie_a",
        sport_id=5,
        volume=120_000,
        volume_24h=5_000,
        status="open",
        group_id=None,
        image_url=None,
        hook_description=None,
        event_id=None,
        close_time=None,
        updated_at=None,
        source="kalshi",
    )


def _empty_result(futures=(), events=()):
    result = MagicMock()
    result.scalars.return_value.all.return_value = list(events or futures)
    result.scalar.return_value = 0
    result.scalar_one_or_none.return_value = None
    result.fetchall.return_value = []
    result.all.return_value = []
    result.first.return_value = None
    return result


class _Recorder:
    """Every statement the route executed, with its bound values."""

    def __init__(self):
        self.statements: list[tuple[str, dict]] = []

    def record(self, stmt):
        try:
            sql = str(stmt)
        except Exception:  # noqa: BLE001
            return ""
        params: dict = {}
        try:
            params = dict(stmt.compile().params or {})
        except Exception:  # noqa: BLE001
            params = {}
        self.statements.append((sql, params))
        return sql

    def _values_where(self, predicate) -> list[str]:
        out: list[str] = []
        for sql, params in self.statements:
            if predicate(sql, sql.upper()):
                out.extend(
                    str(v) for v in params.values() if isinstance(v, str)
                )
        return out

    def team_values(self) -> list[str]:
        return self._values_where(
            lambda sql, up: " teams" in sql and "SELECT" in up
        )

    def futures_values(self) -> list[str]:
        return self._values_where(
            lambda sql, up: "futures_markets" in sql and "SELECT" in up
        )

    def event_values(self) -> list[str]:
        return self._values_where(
            lambda sql, up: " events" in sql
            and "SELECT" in up
            and "futures_markets" not in sql
        )

    def all_values(self) -> list[str]:
        return self._values_where(lambda sql, up: True)

    def event_params(self) -> list:
        """EVERY bound value of the events SELECTs, of any type.

        Separate from `event_values()` because that one keeps only strings, and
        the day key binds its literals rather than inlining them: the timezone
        name and the season year live in the parameter map, not in the SQL text.
        Asserting them against `str(stmt)` silently reads a `:param_3` and finds
        nothing (measured while writing this file).
        """
        out: list = []
        for sql, params in self.statements:
            upper = sql.upper()
            if (
                " events" in sql
                and "SELECT" in upper
                and "futures_markets" not in sql
            ):
                out.extend(params.values())
        return out

    def event_order_bys(self) -> list[str]:
        """The ORDER BY clause of every events SELECT the route built."""
        out: list[str] = []
        for sql, _params in self.statements:
            upper = sql.upper()
            if (
                " events" in sql
                and "SELECT" in upper
                and "futures_markets" not in sql
                and "ORDER BY" in upper
            ):
                out.append(sql[upper.rindex("ORDER BY"):])
        return out


@pytest.fixture
def recorder():
    return _Recorder()


def _make_seeded_db(recorder):
    teams = [_team_row()]
    markets = [_futures_row()]
    session = AsyncMock()

    async def _execute(stmt, *args, **kwargs):
        sql = recorder.record(stmt)
        upper = sql.upper()
        is_futures = "futures_markets" in sql and "SELECT" in upper
        result = _empty_result(markets if is_futures else (), ())
        if " teams" in sql and "SELECT" in upper:
            result.all.return_value = list(teams)
        return result

    session.execute = AsyncMock(side_effect=_execute)
    return session


@pytest.fixture
def seeded_db(recorder):
    return _make_seeded_db(recorder)


async def _client_for(session, monkeypatch):
    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")
    from app.main import app

    async def _mock_get_db():
        yield session

    async def _mock_get_optional_user():
        return None

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_db_rw] = _mock_get_db
    app.dependency_overrides[get_optional_user] = _mock_get_optional_user
    with patch("app.main.init_db", new_callable=AsyncMock):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
    app.dependency_overrides.clear()


@pytest.fixture
async def client(seeded_db, monkeypatch):
    async for ac in _client_for(seeded_db, monkeypatch):
        yield ac


class TestTheSeedIsReal:
    """Without these, every bound-value assertion below could pass vacuously."""

    async def test_the_seeded_team_reaches_the_page(self, client):
        body = (await client.get(f"{SEARCH}?q=lazio")).json()
        assert "Lazio" in [t.get("name") for t in body["teams"]], (
            "the seeded team did not reach the page — every assertion in this "
            "file would be vacuous"
        )

    async def test_the_route_issued_the_arms_this_file_reads(
        self, client, recorder
    ):
        await client.get(f"{SEARCH}?q=lazio")
        assert recorder.team_values(), "no teams SELECT was issued"
        assert recorder.futures_values(), "no futures SELECT was issued"
        assert recorder.event_values(), "no events SELECT was issued"


class TestTheQualifierDoesNotEmptyThePage:
    """The ship, read off the served payload rather than off a filter."""

    async def test_a_time_qualifier_still_finds_the_team(self, client):
        body = (await client.get(f"{SEARCH}?q=lazio today")).json()
        assert "Lazio" in [t.get("name") for t in body["teams"]], (
            "'lazio today' lost the team — this is #5688, the defect that "
            "served an empty page while Lazio had a game that day"
        )

    # NO PAYLOAD-LEVEL FUTURES ASSERTION HERE, and the absence is deliberate
    # rather than an oversight. MEASURED while writing this file: the seeded
    # market reaches the futures SELECT but not the served `futures` list — the
    # arm runs a dedup, a family roll-up and a formatter that read attributes a
    # `SimpleNamespace` seed does not carry, and the route's per-item guards
    # (gotcha #42) correctly swallow the difference. The count is therefore 0
    # for `lazio` AND for `lazio today` alike, so an assertion here would fail
    # for a reason that has nothing to do with the defect, and "fixing" it by
    # seeding a richer row would be asserting against my own replica of the
    # formatter. The futures arm's proof is the BOUND-PARAMETER read in
    # `TestEveryIdentityArmReceivesTheSubject` — which is the technique this
    # file's precedent adopted precisely because a mocked pool cannot see a
    # filter change — plus the production before/after in the ship's report.

    async def test_a_season_qualifier_still_finds_the_team(self, client):
        """`lazio 2026` measured 0 teams / 0 results on production too.

        A different scaffold kind (`season_year`) down the same path, so a fix
        that only ever saw the word "today" does not pass this file.
        """
        body = (await client.get(f"{SEARCH}?q=lazio 2026")).json()
        assert "Lazio" in [t.get("name") for t in body["teams"]], (
            "'lazio 2026' lost the team — the season scaffold is unhandled"
        )

    async def test_the_qualified_page_matches_the_bare_page(self, client):
        """The qualifier changes WHICH string identifies, and nothing else.

        Asserted as an equality between two served payloads rather than as a
        non-emptiness, so a future change that half-substitutes shows up here
        as a difference instead of hiding behind a page that is merely
        non-empty.
        """
        bare = (await client.get(f"{SEARCH}?q=lazio")).json()
        qualified = (await client.get(f"{SEARCH}?q=lazio today")).json()
        assert [t.get("name") for t in qualified["teams"]] == [
            t.get("name") for t in bare["teams"]
        ]
        # Both futures lists are empty under this seed (see the note above), so
        # this pair is an equality that currently compares [] to []. Kept
        # because it is the assertion that turns real the moment the seed can
        # carry a formattable market, and because an INEQUALITY here would be a
        # genuine failure today: it would mean the qualifier changed the
        # futures arm in some way the bound-value test did not catch.
        assert [f.get("name") for f in qualified["futures"]] == [
            f.get("name") for f in bare["futures"]
        ]


class TestEveryIdentityArmReceivesTheSubject:
    """Arm by arm, because the production measurement shows all of them dark.

    Each test reddens if `q` is restored at THAT arm alone.
    """

    async def test_the_teams_arm_never_binds_the_question_word(
        self, client, recorder
    ):
        await client.get(f"{SEARCH}?q=lazio today")
        values = recorder.team_values()
        assert values, "no teams SELECT was issued — the guard would be vacuous"
        joined = " ".join(values).lower()
        assert "lazio" in joined, (
            f"the subject never reached the teams arm; bound values {values}"
        )
        assert "today" not in joined, (
            "the question word was bound as a term the team must also match — "
            f"this is the #5688 defect; bound values {values}"
        )

    async def test_the_futures_arm_never_binds_the_question_word(
        self, client, recorder
    ):
        await client.get(f"{SEARCH}?q=lazio today")
        values = recorder.futures_values()
        assert values, "no futures SELECT was issued"
        joined = " ".join(values).lower()
        assert "lazio" in joined, (
            f"the subject never reached the futures arm; bound {values}"
        )
        assert "today" not in joined, (
            f"the question word reached the futures arm; bound {values}"
        )

    async def test_the_events_arm_never_binds_the_question_word(
        self, client, recorder
    ):
        await client.get(f"{SEARCH}?q=lazio today")
        values = recorder.event_values()
        assert values, "no events SELECT was issued"
        joined = " ".join(values).lower()
        assert "lazio" in joined, (
            f"the subject never reached the events arm; bound {values}"
        )
        assert "today" not in joined, (
            f"the question word reached the events arm; bound {values}"
        )

    async def test_no_arm_anywhere_binds_the_question_word(
        self, client, recorder
    ):
        """The catch-all, so an arm nobody enumerated cannot stay dark.

        The three tests above name the arms the production measurement caught.
        This one fails for an arm added later that takes `q` — which is how
        `/search` itself came to be missed after `/typeahead` was fixed.
        """
        await client.get(f"{SEARCH}?q=lazio today")
        leaked = [v for v in recorder.all_values() if "today" in v.lower()]
        assert not leaked, (
            "some identity arm still binds the reader's question as a term to "
            f"match: {leaked}"
        )


class TestThePythonSideIdentitySitesReceiveTheSubject:
    """The sites a bound-parameter read structurally cannot see.

    EVERY TEST HERE EXISTS BECAUSE A MUTANT SURVIVED. The bound-value tests
    above read SQL parameters, so they are blind to anything the route decides
    in Python after the rows come back — and three identity sites live there.
    Reverting each of them to the raw query passed every other assertion in
    this file. A guard that is only checked against the fix it shipped with
    measures nothing; these were written against the surviving mutants.
    """

    async def test_the_match_class_scorer_is_handed_the_subject(
        self, client, monkeypatch
    ):
        """`rank()` DROPS rows it cannot rank, so this is a recall site.

        It is also the one the `/typeahead` comment means by "the more
        precisely the reader asked, the fewer answers existed": `lazio` lands
        the club at MC0 on an owned alias, `lazio today` at MC3 on partial
        tokens, because no club owns a name containing "today".
        """
        seen: list[str] = []
        import app.utils.search_match_class as smc

        real = smc.rank

        def _spy(query, candidates, *a, **kw):
            seen.append(query)
            return real(query, candidates, *a, **kw)

        monkeypatch.setattr(smc, "rank", _spy)
        await client.get(f"{SEARCH}?q=lazio today")

        assert seen, "the scorer was never called — this guard would be vacuous"
        assert not [s for s in seen if "today" in s.lower()], (
            "the match-class scorer was handed the reader's question word, so "
            f"it scores every row against a token nothing owns; got {seen}"
        )
        assert any("lazio" in s.lower() for s in seen), (
            f"the scorer never received the subject at all; got {seen}"
        )

    # THE CONCEPT-PROVENANCE SITE (`_c["_derived"] = not
    # _query_names_concept(...)`) IS NOT GUARDED HERE, and that is a measured
    # decision rather than a gap. It was covered by a spy in this class first;
    # the spy recorded ZERO calls for every query tried (`masters today`,
    # `oscars today`, `super bowl today`, `world cup today`, `emmys today`,
    # `lazio today`), because the concept pool is derived from matched futures
    # markets and no `SimpleNamespace` seed formats into one. A test that can
    # only ever be vacuous or red is worse than no test: it reads as coverage.
    #
    # That site IS killed, by
    # `test_search_scorer_wiring.py::test_provenance_is_per_row_not_blanket` —
    # a source scan whose needle #5688 re-aimed at the new spelling. VERIFIED
    # by mutation, not assumed: reverting the call site to the raw `q` reddens
    # exactly that test (exit 1, 1 failed). Recorded here so the next reader
    # knows where the cover lives rather than re-deriving it.

    # THE TRIGRAM "DID YOU MEAN" ARM IS NOT GUARDED HERE EITHER, same reason
    # and same measurement. It is reached only when `total_count == 0` AND the
    # query is a single term AND nothing was degraded AND no nickname arm fired
    # — a conjunction this seeded session cannot satisfy: a client with an empty
    # team pool still produced ZERO statements containing `similarity(`, so a
    # test written against it asserted nothing while appearing to pass. (The
    # first draft did exactly that, and the mutant survived it.)
    #
    # Cover lives in
    # `test_search_latency_contract.py::test_fuzzy_fallback_uses_the_indexable_similarity_operator`.
    # VERIFIED by mutation: reverting that arm to the raw `q` reddens it (exit 1,
    # 1 failed), and `typeahead_fuzzy_index_mutations` additionally reports its
    # M9 needle NOT-APPLIED, which fails the battery. Two independent signals.


class TestTheNamedDayLeads:
    """#5688's second acceptance bullet: the same-day row comes FIRST.

    Read off the ORDER BY the route COMPILED, not off the served rows, and the
    reason is the same one that makes this a SQL change in the first place: the
    events arm is paginated, so "first" is a property of the whole ordered set
    and a mocked page cannot exhibit it. The clause is the artefact that decides
    it, so the clause is what these assert.
    """

    async def test_a_named_day_becomes_the_leading_sort_key(
        self, client, recorder
    ):
        await client.get(f"{SEARCH}?q=lazio today")
        clauses = [c for c in recorder.event_order_bys() if "timezone" in c]
        assert clauses, (
            "no events ORDER BY carried a day key — 'today' is still decorative "
            "and the reader gets the same page they would for a bare name"
        )
        for clause in clauses:
            day = clause.index("timezone")
            # `status` is the tier that put a finished same-day game BELOW a
            # fixture five weeks out. The day key is only a fix if it outranks
            # it, so position — not mere presence — is what is asserted.
            assert "status" not in clause or day < clause.index("status"), (
                "the day key sorts BELOW the status tier, so a finished game "
                "played today still loses to a future fixture — this is the "
                f"CERT-2735 defect on the search arm; clause was {clause}"
            )

    async def test_the_day_key_is_eastern_not_utc(self, client, recorder):
        """A 7pm ET game is tomorrow in UTC — most of an American slate.

        A UTC comparison would rank the evening games as "not today", which is
        a wrong answer that looks right for exactly half the day.
        """
        await client.get(f"{SEARCH}?q=lazio today")
        assert [
            c for c in recorder.event_order_bys() if "timezone" in c
        ], "no day key was applied"
        assert "America/New_York" in recorder.event_params(), (
            "the day key is not in the Eastern calendar — a UTC comparison "
            "ranks every evening game as 'not today'"
        )

    async def test_a_named_season_becomes_a_sort_key(self, client, recorder):
        await client.get(f"{SEARCH}?q=lazio 2026")
        clauses = [c for c in recorder.event_order_bys() if "timezone" in c]
        assert clauses, "'lazio 2026' applied no season key"
        assert 2026 in recorder.event_params(), (
            "the season the reader named was never bound into the sort"
        )

    async def test_a_generic_query_adds_no_day_key_at_all(
        self, client, recorder
    ):
        """The no-op has to be a real no-op.

        A key that was a constant for generic queries would still be a key, and
        every plan in the system would need re-reading to prove it changed
        nothing. This asserts the common path is untouched.
        """
        await client.get(f"{SEARCH}?q=lazio")
        clauses = recorder.event_order_bys()
        assert clauses, "no events ORDER BY was built — the guard is vacuous"
        assert not [c for c in clauses if "timezone" in c], (
            "a bare name grew a day sort key it should not have; "
            f"clauses {clauses}"
        )

    async def test_a_question_with_no_day_adds_no_day_key(
        self, client, recorder
    ):
        """`playoffs` is an intent, but it names no DAY.

        Distinguishes "an intent was parsed" from "a day was named" — a fix
        that keyed off `intent is not None` would pass every other test in this
        class and fail this one.
        """
        await client.get(f"{SEARCH}?q=lazio playoffs")
        assert not [c for c in recorder.event_order_bys() if "timezone" in c], (
            "a question naming no day still added a day sort key"
        )


class TestTheDayKeyIsBuiltInTheEasternCalendar:
    """The day key's SEMANTICS, on a pinned clock. Reach is proven elsewhere.

    The route-level tests prove the key is built and leads; they cannot prove
    it is built in the right CALENDAR, because for twenty hours of every day
    the UTC date and the Eastern date agree — a mutation swapping one for the
    other survives whenever the suite happens to run outside 00:00-04:00 UTC,
    which is a guard that passes for reasons having nothing to do with the
    code. So the calendar is asserted here, against instants chosen to
    straddle, exactly where the clock can be pinned instead of observed
    (gotcha #44: an anchor that branches on the clock is not an anchor).
    """

    @pytest.mark.parametrize(
        "utc_instant,eastern_day",
        [
            # 9pm ET on the 12th is already the 13th in UTC. This is the
            # evening slate — most of an American sports day — and a UTC key
            # ranks every one of those games as "not today".
            (datetime(2026, 9, 13, 1, 0, tzinfo=timezone.utc), date(2026, 9, 12)),
            # Mid-afternoon ET, where the two calendars agree. Included so the
            # pair shows the key tracks Eastern rather than merely differing
            # from UTC.
            (datetime(2026, 9, 12, 18, 0, tzinfo=timezone.utc), date(2026, 9, 12)),
            # Just after Eastern midnight: a new day in both, one hour apart.
            (datetime(2026, 9, 13, 5, 0, tzinfo=timezone.utc), date(2026, 9, 13)),
        ],
    )
    async def test_the_day_bound_is_the_eastern_date(
        self, utc_instant, eastern_day
    ):
        from app.routes.events import _intent_day_order_key
        from app.utils.search_intent import parse_intent

        key = _intent_day_order_key(parse_intent("lazio today"), utc_instant)
        assert key is not None, "'lazio today' built no day key"
        bound = [
            v
            for v in key.compile().params.values()
            if isinstance(v, date) and not isinstance(v, datetime)
        ]
        assert bound == [eastern_day], (
            f"at {utc_instant.isoformat()} the key compares against {bound}, "
            f"but the reader's Eastern day is {eastern_day}"
        )

    async def test_a_query_naming_no_day_builds_no_key(self):
        from app.routes.events import _intent_day_order_key
        from app.utils.search_intent import parse_intent

        now = datetime(2026, 9, 12, 18, 0, tzinfo=timezone.utc)
        for query in ("lazio", "lazio playoffs", "patriots 10 wins"):
            assert _intent_day_order_key(parse_intent(query), now) is None, (
                f"{query!r} grew a day key it should not have"
            )


class TestTheReaderSeesWhatTheyTyped:
    """`_q_identity` identifies, `q` echoes — the echo half of the same rule.

    A fix that substituted everywhere would be a different bug: the page would
    tell the reader it had searched for something they did not type.
    """

    async def test_the_response_echoes_the_raw_query(self, client):
        body = (await client.get(f"{SEARCH}?q=lazio today")).json()
        assert body["query"] == "lazio today", (
            "the page echoed the SUBJECT back to the reader instead of what "
            "they typed"
        )

    async def test_a_generic_query_is_handed_through_verbatim(
        self, client, recorder
    ):
        """The overwhelmingly common case must reach the filters unchanged.

        `parse_intent` returns None for a generic query, so this asserts the
        no-op path really is one — a scaffold grammar that started eating
        ordinary words would be caught here and nowhere else in this file.
        """
        await client.get(f"{SEARCH}?q=lazio")
        values = recorder.team_values()
        assert values, "no teams SELECT was issued"
        assert "lazio" in " ".join(values).lower()
