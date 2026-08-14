"""`debug_evidence=1` echoes what the scorer ranked on — LAT-P050.

The endpoint strips `_aliases`, `_derived` and `_outcome_names` before
responding, and it is right to: they are ranking inputs, and a 40-outcome market
would ship 40 strings per keystroke. But the offline harness projects ranking
changes by re-ranking a captured response, so the strip made the capture
unfaithful by construction — measured on v3804, the harness re-ranked
production's own output from 35/44 down to 30/44, losing five team probes whose
MC0 lived in the stripped aliases.

The echo is the seam that closes it. These tests hold three things:

1. The DEFAULT response is unchanged — no new key, no ordering change. This is
   the measured surface and two ranking reads are already owed against it.
2. The echo is the evidence that RANKED, not a rebuild. It carries the aliases
   the very same response strips, which is the whole point and also the sharpest
   possible check that it was not reconstructed from the payload.
3. The cache is isolated in BOTH directions. A debug answer must not be served
   from a normal entry (it would arrive without `_evidence` and be captured as
   low fidelity), and must never be written to one (a user typing that prefix
   would get the eval payload for the full 45s TTL).

**Non-vacuity.** The shared `client` fixture answers every query empty, so a loop
over suggestions is a loop over nothing and any assertion inside it passes
without executing anything. The session here is SEEDED (the LAT-P049 pattern),
every test asserts its bucket is non-empty first, and `TestTheSeedIsReal` fails
loudly if the seed stops reaching the pool.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw
from app.utils.search_match_class import EVIDENCE_WIRE_KEYS, evidence_from_wire

pytestmark = pytest.mark.asyncio

TEAM_ALIASES = ["Red Sox", "BoSox"]


def _team_row():
    return SimpleNamespace(
        id=501,
        name="Boston Red Sox",
        slug="boston-red-sox",
        abbreviation="BOS",
        sport_id=1,
        logo_url_small="https://example.test/bos.png",
        current_record="70-50",
        sport_key="baseball_mlb",
        alternate_names=list(TEAM_ALIASES),
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
    rows = [_team_row()]
    session = AsyncMock()

    async def _execute(stmt, *args, **kwargs):
        result = _empty_result()
        try:
            sql = str(stmt)
        except Exception:  # noqa: BLE001
            return result
        if " teams" in sql and "SELECT" in sql.upper():
            result.all.return_value = list(rows)
        return result

    session.execute = AsyncMock(side_effect=_execute)
    return session


class _FakeRedis:
    """Records reads and writes so cache isolation is asserted, not assumed."""

    def __init__(self, preload: dict | None = None):
        self.store = dict(preload or {})
        self.reads: list[str] = []
        self.writes: list[str] = []

    def get(self, key):
        self.reads.append(key)
        return self.store.get(key)

    def setex(self, key, ttl, value):
        self.writes.append(key)
        self.store[key] = value

    # trending-search calls; irrelevant here but must not explode
    def zincrby(self, *a, **k):
        return None

    def expire(self, *a, **k):
        return None


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


class TestTheSeedIsReal:
    async def test_typeahead_returns_the_seeded_team(self, seeded_client):
        body = (await seeded_client.get("/api/events/typeahead?q=red sox")).json()
        assert "Boston Red Sox" in [s.get("text") for s in body["suggestions"]], (
            "the seed did not reach the pool — every assertion below would be vacuous"
        )


class TestDefaultResponseIsUnchanged:
    async def test_no_evidence_key_by_default(self, seeded_client):
        body = (await seeded_client.get("/api/events/typeahead?q=red sox")).json()
        assert body["suggestions"], "vacuous"
        assert "_evidence" not in body

    async def test_private_keys_still_stripped_with_the_echo_on(self, seeded_client):
        """The echo must not become a back door for the strip it sits beside."""
        body = (
            await seeded_client.get("/api/events/typeahead?q=red sox&debug_evidence=1")
        ).json()
        assert body["suggestions"], "vacuous"
        for s in body["suggestions"]:
            assert "_aliases" not in s
            assert "_derived" not in s
            assert "_outcome_names" not in s

    async def test_ordering_is_identical_with_and_without_the_echo(self, seeded_client):
        plain = (await seeded_client.get("/api/events/typeahead?q=red sox")).json()
        debug = (
            await seeded_client.get("/api/events/typeahead?q=red sox&debug_evidence=1")
        ).json()
        assert plain["suggestions"], "vacuous"
        assert [s.get("text") for s in plain["suggestions"]] == [
            s.get("text") for s in debug["suggestions"]
        ], "the echo changed the ranking — it is an observer, not a participant"


class TestTheEchoIsWhatRanked:
    async def test_evidence_is_positionally_aligned(self, seeded_client):
        body = (
            await seeded_client.get("/api/events/typeahead?q=red sox&debug_evidence=1")
        ).json()
        assert body["suggestions"], "vacuous"
        assert len(body["_evidence"]) == len(body["suggestions"])
        for s, e in zip(body["suggestions"], body["_evidence"]):
            assert e["name"] == s.get("text")

    async def test_echo_carries_the_aliases_the_response_strips(self, seeded_client):
        """The sharpest available proof it was not rebuilt from the payload.

        `alternate_names` exists nowhere in the response. If the echo carries it,
        the echo came from the `Evidence` the scorer consumed.
        """
        body = (
            await seeded_client.get("/api/events/typeahead?q=red sox&debug_evidence=1")
        ).json()
        teams = [
            (s, e)
            for s, e in zip(body["suggestions"], body["_evidence"])
            if s.get("type") == "team"
        ]
        assert teams, "no team suggestion — assertion would be vacuous"
        _, ev = teams[0]
        aliases = set(evidence_from_wire(ev).aliases)
        assert set(TEAM_ALIASES) <= aliases, (
            f"echo lost the stripped aliases: {aliases}"
        )
        assert "BOS" in aliases, "the team abbreviation the route appends is missing"

    async def test_echo_has_exactly_the_wire_keys(self, seeded_client):
        body = (
            await seeded_client.get("/api/events/typeahead?q=red sox&debug_evidence=1")
        ).json()
        assert body["_evidence"], "vacuous"
        for e in body["_evidence"]:
            assert set(e) == set(EVIDENCE_WIRE_KEYS)


class TestCacheIsolation:
    """A debug answer and a normal answer are never interchangeable in a cache."""

    async def _get(self, seeded_client, url, fake):
        with patch("app.tasks.redis_state.get_redis_client", return_value=fake):
            return (await seeded_client.get(url)).json()

    async def test_debug_request_never_writes_the_cache(self, seeded_client):
        fake = _FakeRedis()
        body = await self._get(
            seeded_client, "/api/events/typeahead?q=red sox&debug_evidence=1", fake
        )
        assert "_evidence" in body, "vacuous — the echo did not happen"
        assert fake.writes == [], (
            "a debug answer was cached; a normal user typing this prefix would be "
            "served `_evidence` for the full TTL"
        )

    async def test_debug_request_never_reads_the_cache(self, seeded_client):
        """Otherwise it returns a normal entry with no echo, and the capture
        silently records low fidelity while believing it asked for high."""
        key = "bainluck:typeahead:red sox"
        fake = _FakeRedis({key: '{"suggestions": [], "query": "red sox"}'})
        body = await self._get(
            seeded_client, "/api/events/typeahead?q=red sox&debug_evidence=1", fake
        )
        assert key not in fake.reads
        assert "_evidence" in body

    async def test_normal_request_still_uses_the_cache(self, seeded_client):
        """The isolation must not have disabled caching for everyone else."""
        key = "bainluck:typeahead:red sox"
        sentinel = '{"suggestions": [{"text": "FROM CACHE"}], "query": "red sox"}'
        fake = _FakeRedis({key: sentinel})
        body = await self._get(seeded_client, "/api/events/typeahead?q=red sox", fake)
        assert body["suggestions"] == [{"text": "FROM CACHE"}]
        assert key in fake.reads
