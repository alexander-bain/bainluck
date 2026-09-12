"""T2-3 (#5060) — the ROUTE hands the SUBJECT to the filters and the scorer.

WHY THIS FILE EXISTS SEPARATELY FROM `test_search_intent_composition_5060.py`.
That file drives `parse_intent` / `rank_with_keys` / `promote_answering_rows`
directly and proves the mechanism. It cannot prove the REACH: it composes those
functions itself, so it stays green when the route stops calling them that way.
Measured, not supposed — reverting the route's

    terms = _strip_search_scaffolding(_q_identity.strip().split())

back to `q` left all 76 of those tests passing. An unguarded serving path proves
the mechanism and nothing about the reader.

So these tests drive the real endpoint and read what the ROUTE did.

**Non-vacuity, and it is not the usual kind here.** The seeded session answers
any teams SELECT with the same row whatever the WHERE clause says, so an
assertion about which rows came back could never see a filter change. The guard
that actually bites reads the COMPILED PARAMETERS of the statement the route
built: with the fix, the teams query is parameterised on "patriots" and the word
"playoffs" appears in no bound value; without it, "playoffs" is bound as a term
the team must also match, which is why the pool came back empty in production.
`TestTheSeedIsReal` fails loudly if the seed stops reaching the pool at all.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw

pytestmark = pytest.mark.asyncio


def _team_row():
    return SimpleNamespace(
        id=601,
        name="New England Patriots",
        slug="new-england-patriots",
        abbreviation="NE",
        sport_id=2,
        logo_url_small="https://example.test/ne.png",
        current_record="9-3",
        sport_key="americanfootball_nfl",
        alternate_names=["Patriots", "Pats"],
        team_rank=0.9,
    )


def _playoff_market_row():
    """The row that ANSWERS `patriots playoffs`.

    Seeded so the route-level guard below can assert a FIRST VISIBLE RESULT,
    which is what #5060's acceptance asks for. Without a market in the pool the
    only observable page is the team, and "the answer leads" is unfalsifiable.
    """
    return SimpleNamespace(
        id=9001,
        name="Patriots to Make the Playoffs",
        external_id="kxnflplayoff-ne-2026",
        market_tier=2,
        market_type="playoffs",
        category="sports",
        llm_sport_category="americanfootball_nfl",
        sport_id=2,
        volume=250_000,
        outcomes=[],
    )


def _event_row(event_id, away, home, commence_time):
    """An events-pool stand-in carrying the fields the route reads off an event.

    `commence_time` is a real aware datetime because that is what the route
    `.isoformat()`s onto the suggestion, and the time band under test reads it
    back off the suggestion — so a string here would test the wrong object.
    """
    team = lambda: SimpleNamespace(logo_url_small=None)  # noqa: E731
    return SimpleNamespace(
        id=event_id,
        home_team=team(),
        away_team=team(),
        home_team_id=None,
        away_team_id=None,
        home_team_name=home,
        away_team_name=away,
        status="scheduled",
        commence_time=commence_time,
        sport=SimpleNamespace(key="basketball_nba"),
    )


def _empty_result(futures_rows=(), event_rows=()):
    result = MagicMock()
    result.scalars.return_value.all.return_value = list(event_rows)
    result.scalars.return_value.first.return_value = None
    # The futures arm reads `.scalars().unique().all()`; every other scalars
    # caller reads `.scalars().all()`. Configured separately because a MagicMock
    # left unconfigured returns a MagicMock, not an empty list, and the futures
    # pool would then be built from a mock rather than from the seed.
    result.scalars.return_value.unique.return_value.all.return_value = list(
        futures_rows
    )
    result.scalar_one_or_none.return_value = None
    result.scalar.return_value = None
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

    def team_query_values(self) -> list[str]:
        """Bound string values of every teams SELECT the route issued."""
        out: list[str] = []
        for sql, params in self.statements:
            if " teams" in sql and "SELECT" in sql.upper():
                out.extend(
                    str(v) for v in params.values() if isinstance(v, str)
                )
        return out


@pytest.fixture
def recorder():
    return _Recorder()


def _make_seeded_db(recorder, event_rows=()):
    rows = [_team_row()]
    markets = [_playoff_market_row()]
    session = AsyncMock()
    # The route asks for events more than once — a primary pool and, when that
    # comes back thin, a fuzzy one. Answering BOTH with the same seed puts every
    # event on the page twice, which is a property of this mock and not of the
    # product: in production the fuzzy arm exists precisely because the primary
    # found little. Served once so the page under test is a page the route could
    # really build.
    served = {"events": False}

    async def _execute(stmt, *args, **kwargs):
        sql = recorder.record(stmt)
        upper = sql.upper()
        is_futures = "futures_markets" in sql and "SELECT" in upper
        is_events = " events" in sql and "SELECT" in upper and not is_futures
        events_now = ()
        if is_events and event_rows and not served["events"]:
            served["events"] = True
            events_now = event_rows
        result = _empty_result(markets if is_futures else (), events_now)
        if " teams" in sql and "SELECT" in upper:
            result.all.return_value = list(rows)
        return result

    session.execute = AsyncMock(side_effect=_execute)
    return session


@pytest.fixture
def seeded_db(recorder):
    return _make_seeded_db(recorder)


async def _client_for(session, monkeypatch):
    """The `client` fixture's body, over an arbitrary seeded session.

    Factored out so the time-band tests below can seed their own competing
    event rows without duplicating the dependency-override dance — and so they
    exercise the same app wiring as every other test in this file.
    """
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


TYPEAHEAD = "/api/events/typeahead"


class TestTheSeedIsReal:
    async def test_the_seeded_team_reaches_the_pool(self, client):
        body = (await client.get(f"{TYPEAHEAD}?q=patriots")).json()
        assert "New England Patriots" in [
            s.get("text") for s in body["suggestions"]
        ], "the seed did not reach the pool — every assertion below would be vacuous"


class TestTheFilterReceivesTheSubject:
    async def test_the_question_word_is_never_bound_as_a_team_term(
        self, client, recorder
    ):
        """THE guard for the route wiring.

        Kills: reverting `_q_identity` to `q` in the `terms` line. The multi-word
        arm ANDs every term, so a bound "playoffs" means the team must own a name
        containing it — no team does, and the pool comes back empty. This is the
        production defect, read off the statement the route actually built.
        """
        await client.get(f"{TYPEAHEAD}?q=patriots playoffs")
        values = recorder.team_query_values()
        assert values, "no teams query was issued — the guard would be vacuous"
        joined = " ".join(values).lower()
        assert "patriots" in joined, (
            f"the subject never reached the team filter; bound values were {values}"
        )
        assert "playoff" not in joined, (
            "the question word was bound as a term the team must also match — "
            f"this is the #5060 defect; bound values were {values}"
        )

    async def test_the_outcome_arm_recall_pattern_is_built_on_the_subject(
        self, client, recorder
    ):
        """The futures OUTCOME arm — `FuturesOutcome.name ILIKE pattern`.

        Found while auditing every remaining raw-`q` site on this path, not by
        the ship's own brief. No outcome on earth is named "patriots playoffs",
        so on the raw query this arm matched nothing and the dropdown silently
        lost every market a reader reaches through an OUTCOME name rather than a
        market name. Same defect class as the team filter, one arm further out.

        Kills: reverting `pattern = f"%{_q_identity}%"` to `f"%{q}%"`.
        """
        await client.get(f"{TYPEAHEAD}?q=patriots playoffs")
        bound = [
            v
            for _sql, params in recorder.statements
            for v in params.values()
            if isinstance(v, str) and v.startswith("%") and v.endswith("%")
        ]
        assert bound, "no ILIKE pattern was bound — the guard would be vacuous"
        assert "%patriots%" in [b.lower() for b in bound], (
            f"the outcome arm never received the subject; bound patterns {bound}"
        )
        assert not [b for b in bound if "playoff" in b.lower()], (
            "the outcome arm asked for an outcome literally named "
            f"'patriots playoffs'; bound patterns {bound}"
        )

    async def test_a_generic_query_binds_exactly_what_the_reader_typed(
        self, client, recorder
    ):
        """The other half of the pair: a query with no scaffold must be passed
        through untouched, or the fix has quietly become a general rewriter."""
        await client.get(f"{TYPEAHEAD}?q=patriots")
        joined = " ".join(recorder.team_query_values()).lower()
        assert "patriots" in joined


class TestTheAnswerLeadsOnThePageTheRouteServes:
    """THE reach guard for the promotion, and it was missing.

    MEASURED, not supposed (2026-09-12, on this tree): with the route's
    ``promote_answering_rows`` call disabled — `if False:` around it — all 86
    tests of the three T2-3 files stayed GREEN. The composition file drives the
    partition itself, so it proves the mechanism and can say nothing about
    whether the route still calls it; and nothing else here read slot 0. Design
    decision B is the headline half of this ship ("`Patriots playoffs` opens
    playoff qualification"), and #5060's acceptance asks for FIRST-VISIBLE-RESULT
    assertions by name. So they are made here, against the served payload.
    """

    async def test_the_seeded_market_reaches_the_page(self, client):
        """Non-vacuity, stated before the assertions that depend on it.

        If the futures seed stops reaching the pool, the two tests below pass by
        promoting nothing and asserting nothing — the silent-hole shape this
        file's header is about. This fails loudly instead.
        """
        body = (await client.get(f"{TYPEAHEAD}?q=patriots playoffs")).json()
        assert "Patriots to Make the Playoffs" in [
            s.get("text") for s in body["suggestions"]
        ], "the market seed did not reach the pool — the guards below are vacuous"

    async def test_the_requested_answer_is_the_first_visible_result(self, client):
        """Kills: removing the route's promotion call, or moving it before the
        slice where it can no longer reach the page the reader sees."""
        body = (await client.get(f"{TYPEAHEAD}?q=patriots playoffs")).json()
        texts = [s.get("text") for s in body["suggestions"]]
        assert texts[0] == "Patriots to Make the Playoffs", texts

    async def test_a_bare_name_still_leads_with_the_entity_at_the_route(
        self, client
    ):
        """Ruling 041 proper, asserted where the reader meets it.

        The control for the test above: the SAME page, the SAME seeded market,
        one word fewer. A bare name is not a question, so the entity leads and
        the market does not. Kills: promoting on every query — which would pass
        the test above for entirely the wrong reason.
        """
        body = (await client.get(f"{TYPEAHEAD}?q=patriots")).json()
        texts = [s.get("text") for s in body["suggestions"]]
        assert texts[0] == "New England Patriots", texts


class TestTheScorerReceivesTheSubject:
    """The scorer half of the wiring, read off the CALL the route made.

    MEASURED SURVIVORS (2026-09-12, on this tree): reverting either

        _ta_candidates = [(_typeahead_evidence(item, _q_identity), item) ...]
        _ta_keyed      = _s_rank_with_keys(_q_identity, _ta_candidates)

    back to `q` left every other test in this file and the composition file
    GREEN. So these two lines were unguarded, and this class is why they are not.

    WHY THIS IS A SPY AND NOT AN ORDERING ASSERTION — the honest reason, because
    a spy asserts a call rather than an outcome and that is the weaker kind of
    guard. On the served page the two wirings are indistinguishable, measured
    with `match_class` on the real evidence:

        candidate                          q="patriots"   q="patriots playoffs"
        team New England Patriots               MC0                 MC3
        market Patriots to Make the Playoffs    MC1                 MC1
        market AFC Playoff Picture              MC5                 MC3
        event  Patriots at Jets                 MC1                 MC3

    Everything degrades together, and every row that gains on the raw query
    gains by containing "playoffs" — which makes it an ANSWERING row, so the
    promotion lifts it to the front either way. There is no page of rows whose
    ORDER separates the two wirings; what separates them is the class the team
    resolved at, and neither the suggestions nor the `_evidence` echo carries a
    class. The payload genuinely cannot see this.

    So it is read the way this file already reads the filter half — off what the
    route handed its collaborator — rather than not guarded at all. Both spies
    wrap the real functions, so behaviour is unchanged and the page below is the
    page production serves.
    """

    async def test_the_scorer_and_the_evidence_both_read_the_subject(
        self, client
    ):
        import app.routes.events as events_mod
        import app.utils.search_match_class as mc_mod

        evidence_queries: list[str | None] = []
        rank_queries: list[str] = []

        real_evidence = events_mod._typeahead_evidence
        real_rank = mc_mod.rank_with_keys

        def _spy_evidence(item, q=None):
            evidence_queries.append(q)
            return real_evidence(item, q)

        def _spy_rank(query, candidates):
            rank_queries.append(query)
            return real_rank(query, candidates)

        with patch.object(events_mod, "_typeahead_evidence", _spy_evidence), \
                patch.object(mc_mod, "rank_with_keys", _spy_rank):
            await client.get(f"{TYPEAHEAD}?q=patriots playoffs")

        assert rank_queries, "the scorer was never called — the guard is vacuous"
        assert evidence_queries, "the evidence builder was never called"
        assert rank_queries == ["patriots"], (
            "the scorer was handed the reader's whole question instead of the "
            f"subject it names; got {rank_queries}"
        )
        assert set(evidence_queries) == {"patriots"}, (
            "the evidence was built against the whole question, so the team's "
            f"owned names could not resolve it; got {set(evidence_queries)}"
        )

    async def test_a_generic_query_is_handed_through_verbatim(self, client):
        """The other half of the pair: with no scaffold there is no subject to
        substitute, so the scorer must receive exactly what the reader typed.

        Kills: substituting some always-computed string, which would make the
        test above pass while quietly rewriting every generic query.
        """
        import app.utils.search_match_class as mc_mod

        rank_queries: list[str] = []
        real_rank = mc_mod.rank_with_keys

        def _spy_rank(query, candidates):
            rank_queries.append(query)
            return real_rank(query, candidates)

        with patch.object(mc_mod, "rank_with_keys", _spy_rank):
            await client.get(f"{TYPEAHEAD}?q=red sox")

        assert rank_queries == ["red sox"], rank_queries


class TestTheHubSurvivesTheQuestion:
    """A hub is an identity row, and the question word deleted it from the page.

    MEASURED, and this is a removal rather than a demotion — `_match_hub_suggestions`
    matches statically against `HUB_CONFIGS`:

        _match_hub_suggestions("tennis")       -> ['Tennis hub']
        _match_hub_suggestions("tennis today") -> []

    So before the subject substitution a reader who typed "tennis today" could
    not reach the tennis hub at all, however the rest of the page was ordered.
    Guarded here because the route line was a MUTATION SURVIVOR: reverting it to
    `q` left every other test in this file green.
    """

    async def test_a_question_does_not_cost_the_reader_the_hub(self, client):
        body = (await client.get(f"{TYPEAHEAD}?q=tennis today")).json()
        texts = [s.get("text") for s in body["suggestions"]]
        assert any("Tennis" in (t or "") for t in texts), texts

    async def test_the_bare_hub_query_is_unchanged(self, client):
        """The control: the behaviour the substitution is restoring parity with."""
        body = (await client.get(f"{TYPEAHEAD}?q=tennis")).json()
        texts = [s.get("text") for s in body["suggestions"]]
        assert any("Tennis" in (t or "") for t in texts), texts


class TestTheIntentTravels:
    async def test_an_explicit_question_reports_its_intent(self, client):
        body = (await client.get(f"{TYPEAHEAD}?q=patriots playoffs")).json()
        assert body.get("intent") == {
            "kind": "playoffs",
            "subject": "patriots",
            "threshold": None,
            "season": None,
            "negated": False,
        }

    async def test_a_threshold_and_season_survive_to_the_client(self, client):
        body = (await client.get(f"{TYPEAHEAD}?q=patriots 2025 10 wins")).json()
        intent = body.get("intent")
        assert intent is not None
        assert intent["kind"] == "win_total"
        assert intent["threshold"] == 10.0
        assert intent["season"] == 2025

    @pytest.mark.parametrize("query", ["patriots", "ai", "ipo", "red sox"])
    async def test_a_generic_query_ships_no_intent_key_at_all(self, client, query):
        """Additive and absent-by-default: `intent: null` never appears, so no
        client has to change to keep working.

        Kills: emitting the key unconditionally with a null value — which reads
        to a client as "we considered it and there was none" rather than "this
        endpoint did not answer that question".
        """
        body = (await client.get(f"{TYPEAHEAD}?q={query}")).json()
        assert "intent" not in body

    async def test_the_team_the_reader_named_is_still_on_the_page(self, client):
        """Design decision B's second half: the card identifies the team.

        Leading with the answer is only correct if identity survives beside it.
        """
        body = (await client.get(f"{TYPEAHEAD}?q=patriots playoffs")).json()
        assert "New England Patriots" in [
            s.get("text") for s in body["suggestions"]
        ]



class TestATimeQualifierConstrainsTheAnswer:
    """CERT-2735's required repair, `5060-TIME-QUALIFIERS-CONSTRAIN-THE-ANSWER`.

    The BLOCK in its own terms: `today` treated every event as an answer without
    reading `commence_time`. On production 2026-09-12 the `lakers` event rows
    were, in scorer order — Oct 22 LA Lakers, Sep 12 Mercyhurst Lakers, Sep 19
    Växjö Lakers — so promoting all three as one block led `lakers today` with a
    game five weeks out over the one being played that day. The reader's
    qualifier was read as a topic rather than as a constraint.

    Every test here is a COMPETING-ROW test and that is the point: one seeded
    row cannot fail, because with a single candidate every ordering is the same
    ordering. In each fixture the row the pre-repair code would wrongly lead
    with is seeded FIRST, so a stable partition that reads no clock leaves it on
    top and the assertion bites.
    """

    @pytest.fixture
    async def two_lakers_games(self, recorder, monkeypatch):
        """The production specimen, reduced: a future game the scorer ranks
        first, and a same-day game it ranks second."""
        now = datetime.now(timezone.utc)
        rows = [
            _event_row(7001, "Warriors", "Los Angeles Lakers", now + timedelta(days=40)),
            _event_row(7002, "Gannon", "Mercyhurst Lakers", now + timedelta(hours=3)),
        ]
        async for ac in _client_for(_make_seeded_db(recorder, rows), monkeypatch):
            yield ac

    @pytest.fixture
    async def one_future_game(self, recorder, monkeypatch):
        now = datetime.now(timezone.utc)
        rows = [
            _event_row(7201, "Warriors", "Los Angeles Lakers", now + timedelta(days=40)),
        ]
        async for ac in _client_for(_make_seeded_db(recorder, rows), monkeypatch):
            yield ac

    @pytest.fixture
    async def two_seasons(self, recorder, monkeypatch):
        now = datetime.now(timezone.utc)
        rows = [
            _event_row(7101, "Warriors", "Los Angeles Lakers", now + timedelta(days=40)),
            _event_row(7102, "Clippers", "Los Angeles Lakers", now - timedelta(days=800)),
        ]
        async for ac in _client_for(_make_seeded_db(recorder, rows), monkeypatch):
            yield ac

    async def test_the_competing_rows_reach_the_page(self, two_lakers_games):
        """Non-vacuity, first: without both events in the pool every ordering
        assertion below would be trivially satisfiable."""
        body = (await two_lakers_games.get(f"{TYPEAHEAD}?q=lakers")).json()
        ids = [s.get("event_id") for s in body["suggestions"] if s.get("type") == "event"]
        assert sorted(i for i in ids if i) == [7001, 7002], ids

    async def test_today_does_not_promote_a_future_game_over_a_same_day_game_5060(
        self, two_lakers_games
    ):
        body = (await two_lakers_games.get(f"{TYPEAHEAD}?q=lakers today")).json()
        events = [s for s in body["suggestions"] if s.get("type") == "event"]
        assert len(events) == 2, events
        assert events[0]["event_id"] == 7002, (
            "the game being played TODAY must lead a `today` question; got "
            f"{[e['event_id'] for e in events]}. A future game leading here is "
            "CERT-2735 exactly."
        )

    async def test_a_missed_time_qualifier_demotes_but_never_empties_the_page(
        self, one_future_game
    ):
        """Why this is a BAND and not a filter.

        Excluding rows that miss the qualifier would empty the page whenever
        nothing is on today — and "not an empty page" is the ship this module
        exists to deliver. With no same-day game, `lakers today` must still lead
        with a Lakers game rather than with nothing.
        """
        body = (await one_future_game.get(f"{TYPEAHEAD}?q=lakers today")).json()
        events = [s for s in body["suggestions"] if s.get("type") == "event"]
        assert [e["event_id"] for e in events] == [7201], events

    async def test_season_year_does_not_return_current_season_as_the_requested_year_5060(
        self, two_seasons
    ):
        """The BLOCK's second half: `season_year` answered no row and affected
        nothing but the echoed intent object, so a reader asking for an old
        season was shown the current one as though it were the answer.
        """
        requested = (datetime.now(timezone.utc) - timedelta(days=800)).year
        body = (await two_seasons.get(f"{TYPEAHEAD}?q=lakers {requested}")).json()
        events = [s for s in body["suggestions"] if s.get("type") == "event"]
        assert len(events) == 2, events
        assert events[0]["event_id"] == 7102, (
            f"the reader asked for {requested}; that season's game must lead, "
            f"not the current one. Got {[e['event_id'] for e in events]}."
        )
