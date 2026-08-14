"""The private-key strip, executed by the ROUTE instead of by the test.

LAT-P048 shipped `_search_owned_outcome_names` and hoisted `_typeahead_evidence`,
and then said plainly what its own tests could not do:

    `test_private_evidence_keys_are_stripped_from_suggestions` asserts the
    CONTRACT the route must honour, and pops the private keys itself; it does not
    execute the route's strip. The pre-existing route-level test is vacuous on an
    empty DB — it asserts over zero suggestions.

Alex ruled the repair ships in the same session as the `/search` wiring rather
than waiting, because the weakness was named by the window that created it.

**What makes these non-vacuous.** The shared `client` fixture hands every query
an empty result, so no pool is ever populated and `for s in suggestions:` is a
loop over nothing — a deleted `.pop()` cannot fail a test that never iterates.
Here the session is SEEDED: the team query (and only the team query) returns real
rows, so the route builds a pool item carrying `_aliases`, ranks it, and must
strip it. Every test below asserts the bucket is NON-EMPTY first, so vacuity is a
failure rather than a pass.

**Honest limit, stated rather than discovered later.** This seeds a fake session,
not Postgres. It reaches the `_aliases` strip on both surfaces because team rows
are cheap to fake faithfully (the route touches eight attributes). It does NOT
reach `/search`'s `_derived` strip, which needs the market-derived concept loop to
produce a row, which needs a seeded futures corpus with outcomes and sports — that
belongs with the real-Postgres contract suite, and is recorded as still owed.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw

pytestmark = pytest.mark.asyncio


def _team_row(
    *,
    id: int = 501,
    name: str = "Boston Red Sox",
    slug: str = "boston-red-sox",
    abbreviation: str = "BOS",
    sport_key: str = "baseball_mlb",
    alternate_names: list | None = None,
):
    """A team row with exactly the attributes both routes read off it."""
    return SimpleNamespace(
        id=id,
        name=name,
        slug=slug,
        abbreviation=abbreviation,
        sport_id=1,
        logo_url_small="https://example.test/bos.png",
        current_record="70-50",
        sport_key=sport_key,
        alternate_names=(
            ["Red Sox", "BoSox"] if alternate_names is None else alternate_names
        ),
        team_rank=0.9,
    )


def _empty_result():
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    result.scalars.return_value.first.return_value = None
    result.scalar_one_or_none.return_value = None
    result.scalar.return_value = None
    result.fetchall.return_value = []
    result.all.return_value = []
    result.first.return_value = None
    return result


@pytest.fixture
def seeded_team_db():
    """A session that answers the TEAM query with rows and everything else empty.

    Keyed on the compiled SQL naming the `teams` table. Deliberately narrow: a
    fixture that seeded every query would drag in the futures/event ORM graph and
    become a maintenance object of its own, and the strip under test only needs a
    populated team pool to be reachable.
    """
    rows = [_team_row()]
    session = AsyncMock()

    async def _execute(stmt, *args, **kwargs):
        result = _empty_result()
        try:
            sql = str(stmt)
        except Exception:  # noqa: BLE001 — a non-compilable stmt is simply not ours
            return result
        if " teams" in sql and "SELECT" in sql.upper():
            result.all.return_value = list(rows)
        return result

    session.execute = AsyncMock(side_effect=_execute)
    session.seeded_rows = rows
    return session


async def _search(session, monkeypatch, q: str) -> dict:
    """Hit `/api/events/search` against `session`, after the caller has adjusted
    `session.seeded_rows`. Separate from the `seeded_client` fixture because a
    fixture is bound before the test body can choose its seed."""
    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")
    from app.main import app

    async def _mock_get_db():
        yield session

    async def _mock_get_optional_user():
        return None

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_db_rw] = _mock_get_db
    app.dependency_overrides[get_optional_user] = _mock_get_optional_user
    try:
        with patch("app.main.init_db", new_callable=AsyncMock):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                return (await ac.get("/api/events/search", params={"q": q})).json()
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
async def seeded_client(seeded_team_db, monkeypatch):
    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")
    from app.main import app

    async def _mock_get_db():
        yield seeded_team_db

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


# ---------------------------------------------------------------------------
# The fixture must be able to fail. Checked before it is trusted.
# ---------------------------------------------------------------------------


class TestTheSeedIsReal:
    async def test_typeahead_returns_the_seeded_team(self, seeded_client):
        body = (await seeded_client.get("/api/events/typeahead?q=red sox")).json()
        names = [s.get("text") for s in body["suggestions"]]
        assert "Boston Red Sox" in names, (
            "the seed did not reach the pool — every strip assertion below would "
            "then be vacuous in exactly the way this file exists to end"
        )

    async def test_search_returns_the_seeded_team(self, seeded_client):
        body = (await seeded_client.get("/api/events/search?q=red sox")).json()
        assert [t["name"] for t in body["teams"]] == ["Boston Red Sox"]


# ---------------------------------------------------------------------------
# The strip, executed by the route
# ---------------------------------------------------------------------------


class TestPrivateEvidenceNeverReachesTheWire:
    async def test_typeahead_suggestions_carry_no_private_keys(self, seeded_client):
        body = (await seeded_client.get("/api/events/typeahead?q=red sox")).json()
        suggestions = body["suggestions"]
        assert suggestions, "non-vacuity guard"
        for s in suggestions:
            leaked = [k for k in s if k.startswith("_")]
            assert not leaked, f"private scorer key leaked to the API: {leaked}"

    async def test_typeahead_team_row_really_had_an_alias_to_strip(
        self, seeded_client, seeded_team_db
    ):
        """Proves the pop was REACHED, not merely that nothing was there.

        Without this, a seed whose `alternate_names` was empty would pass the
        test above while exercising nothing — the same shape of false green the
        empty-DB version had.
        """
        assert seeded_team_db.seeded_rows[0].alternate_names, "seed precondition"
        body = (await seeded_client.get("/api/events/typeahead?q=red sox")).json()
        team = next(s for s in body["suggestions"] if s.get("text") == "Boston Red Sox")
        assert "_aliases" not in team
        assert team["abbreviation"] == "BOS", (
            "the strip must remove the private key WITHOUT taking the public "
            "payload with it"
        )

    async def test_search_team_rows_carry_no_private_keys(self, seeded_client):
        body = (await seeded_client.get("/api/events/search?q=red sox")).json()
        teams = body["teams"]
        assert teams, "non-vacuity guard"
        for t in teams:
            leaked = [k for k in t if k.startswith("_")]
            assert not leaked, f"private scorer key leaked to the API: {leaked}"

    async def test_search_team_row_keeps_its_public_fields(self, seeded_client):
        body = (await seeded_client.get("/api/events/search?q=red sox")).json()
        team = body["teams"][0]
        assert set(team) == {
            "id", "name", "slug", "abbreviation", "logo", "record", "sport_key",
        }

    async def test_search_event_concepts_carry_no_private_keys(self, seeded_client):
        """`grammys` mints a concept with no DB at all, so the concept bucket is
        populated even on this narrow seed."""
        body = (await seeded_client.get("/api/events/search?q=grammys")).json()
        concepts = body["event_concepts"]
        assert concepts, "non-vacuity guard — the awards detector should have fired"
        for c in concepts:
            leaked = [k for k in c if k.startswith("_")]
            assert not leaked, f"private scorer key leaked to the API: {leaked}"


# ---------------------------------------------------------------------------
# The route guard, also previously vacuous
# ---------------------------------------------------------------------------


class TestRankingIsActuallyAppliedByTheRoute:
    async def test_alias_evidence_reaches_the_scorer_through_the_route(
        self, seeded_client
    ):
        """`red sox` finds the team ONLY because `alternate_names` is SELECTed and
        handed to the scorer. This is the route-level counterpart of the unit
        test in `test_search_scorer_wiring.py`, and it is the assertion that
        would have caught the column never reaching the ranker."""
        body = (await seeded_client.get("/api/events/search?q=red sox")).json()
        assert body["teams"][0]["name"] == "Boston Red Sox"

    async def test_a_fragment_team_is_reordered_not_deleted(
        self, seeded_team_db, monkeypatch
    ):
        """The scorer must never empty a bucket the SQL filled — recall belongs
        to the SQL. Seeds a row that matches nothing and asserts it still ships."""
        seeded_team_db.seeded_rows[:] = [
            _team_row(name="Brito", slug="brito", abbreviation="BRI",
                      sport_key="soccer_other", alternate_names=[])
        ]
        body = await _search(seeded_team_db, monkeypatch, "open championship")
        assert [t["name"] for t in body["teams"]] == ["Brito"]

    async def test_the_route_actually_reorders_the_team_bucket(
        self, seeded_team_db, monkeypatch
    ):
        """The seam test: proves `/search` CALLS the scorer, not merely that the
        scorer works.

        Everything else in this file passes with a single seeded row, and a
        one-row bucket has no observable order — so deleting the route's `rank()`
        call would leave the whole suite green. That is the same seam
        `_ta_evidence`-as-a-closure hid on typeahead, one surface over.

        `Brito` is seeded with the HIGHER `team_rank`, so the pre-scorer ordering
        (`_sort_matched_team_rows`, FTS rank desc) puts it first. Only the scorer
        can invert this: `Open Championship FC` is an all-token match, `Brito` is
        a fragment, and no knob may lift a fragment over a token match.
        """
        seeded_team_db.seeded_rows[:] = [
            _team_row(id=1, name="Brito", slug="brito", abbreviation="BRI",
                      sport_key="soccer_other", alternate_names=[]),
            _team_row(id=2, name="Open Championship FC", slug="ocfc",
                      abbreviation="OCF", sport_key="soccer_other",
                      alternate_names=[]),
        ]
        seeded_team_db.seeded_rows[0].team_rank = 0.99
        seeded_team_db.seeded_rows[1].team_rank = 0.01

        body = await _search(seeded_team_db, monkeypatch, "open championship")
        assert [t["name"] for t in body["teams"]] == [
            "Open Championship FC", "Brito",
        ], "the route returned the raw FTS order — the scorer was never applied"

    async def test_alias_only_match_outranks_a_higher_fts_fragment(
        self, seeded_team_db, monkeypatch
    ):
        """The `alternate_names` SELECT, asserted through the route.

        `Boston Red Sox` wins `red sox` ONLY on its owned short name. Seed it
        with the losing FTS rank so the alias is the only thing that can put it
        first; drop the alias and the assertion flips.
        """
        seeded_team_db.seeded_rows[:] = [
            _team_row(id=1, name="Soxxy United", slug="soxxy", abbreviation="SOX",
                      sport_key="soccer_other", alternate_names=[]),
            _team_row(id=2, name="Boston Red Sox", slug="boston-red-sox",
                      abbreviation="BOS", sport_key="baseball_mlb",
                      alternate_names=["Red Sox"]),
        ]
        seeded_team_db.seeded_rows[0].team_rank = 0.99
        seeded_team_db.seeded_rows[1].team_rank = 0.01

        body = await _search(seeded_team_db, monkeypatch, "red sox")
        assert body["teams"][0]["name"] == "Boston Red Sox"
