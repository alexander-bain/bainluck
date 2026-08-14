"""`debug_timing=1` attributes the typeahead cache-MISS cost by stage — #1866, LAT-P054.

#1866 measured a **1.16–2.29s p50 on the cache-MISS path** against a `<150ms p50`
budget this endpoint's own comments state twice. What it could not do was say
*which stage* spent it: `/search` has had `?debug_timing=1` since LAT-P002/#1494
and `/typeahead` had nothing, so every causal claim about the miss was an
inference from the outside.

One hypothesis WAS testable from outside, and LAT-P054 killed it (n=16, production
v3813): zero-result queries — which do no per-result assembly whatsoever — came in
**1.37× SLOWER** than result-bearing ones (p50 1.778s vs 1.297s), and the zero
arm's *minimum* sat above the real arm's *median*. So `_search_owned_outcome_names`
and per-result assembly are refuted as the dominant term, and the cost lives in the
match/scan stages. These marks are placed to separate exactly those.

What these tests hold:

1. The DEFAULT response is unchanged — no new key. This is the surface
   `entity_top_1` grades and a ranking read is still owed against it (#1846/`-47`).
2. The block is arithmetically coherent: `total_ms` is the sum of its stages, and
   no stage is negative or non-integral.
3. `debug_timing` is an **observer, not a participant** — identical ordering with
   and without it.
4. The cache is isolated in **both** directions, and the READ side matters for a
   reason peculiar to this flag: a cached entry carries no `debug_timing` key, so
   serving one would answer a timing request with **silence**, which reads exactly
   like a stage that cost nothing (gotcha #53). It would under-report precisely the
   miss path #1866 is about.
5. It composes with `debug_evidence` — the eval harness needs both at once, and
   `debug_evidence` is already a guaranteed miss, so the pair is the natural way to
   time the miss path without waiting out a 45s TTL.

**Non-vacuity.** The shared `client` fixture answers every query empty, so a loop
over suggestions is a loop over nothing. The session here is SEEDED (the LAT-P049
pattern) and `TestTheSeedIsReal` fails loudly if the seed stops reaching the pool.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw

pytestmark = pytest.mark.asyncio

# Stages that must exist on any non-degraded miss. Asserted as a SUBSET, not an
# equality: the fuzzy fallback and the futures-timeout label are path-dependent,
# and pinning the exact set would make an unrelated code path fail this file
# rather than its own.
REQUIRED_STAGES = {
    "setup",
    "teams_query",
    "teams_assemble",
    "events_query",
    "events_assemble",
    "futures_query",
}


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
        alternate_names=["Red Sox", "BoSox"],
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
    async def test_no_debug_timing_key_by_default(self, seeded_client):
        body = (await seeded_client.get("/api/events/typeahead?q=red sox")).json()
        assert body["suggestions"], "vacuous"
        assert "debug_timing" not in body

    async def test_ordering_is_identical_with_and_without_timings(self, seeded_client):
        plain = (await seeded_client.get("/api/events/typeahead?q=red sox")).json()
        timed = (
            await seeded_client.get("/api/events/typeahead?q=red sox&debug_timing=1")
        ).json()
        assert plain["suggestions"], "vacuous"
        assert [s.get("text") for s in plain["suggestions"]] == [
            s.get("text") for s in timed["suggestions"]
        ], "the timing block changed the ranking — it is an observer, not a participant"


class TestTheBlockIsCoherent:
    async def test_required_stages_are_present(self, seeded_client):
        body = (
            await seeded_client.get("/api/events/typeahead?q=red sox&debug_timing=1")
        ).json()
        block = body["debug_timing"]
        missing = REQUIRED_STAGES - set(block)
        assert not missing, f"stage marks vanished: {sorted(missing)}"

    async def test_total_is_the_sum_of_its_stages(self, seeded_client):
        """A total that is not the sum is a stage that was silently dropped."""
        body = (
            await seeded_client.get("/api/events/typeahead?q=red sox&debug_timing=1")
        ).json()
        block = dict(body["debug_timing"])
        total = block.pop("total_ms")
        assert block, "no stages recorded — the block is vacuous"
        assert total == sum(block.values())

    async def test_every_stage_is_a_non_negative_int(self, seeded_client):
        body = (
            await seeded_client.get("/api/events/typeahead?q=red sox&debug_timing=1")
        ).json()
        for label, value in body["debug_timing"].items():
            assert isinstance(value, int), f"{label} is {type(value).__name__}, not int"
            assert value >= 0, f"{label} is negative: {value}"


class TestComposesWithTheEvidenceEcho:
    async def test_both_flags_together(self, seeded_client):
        """The harness wants both: `debug_evidence` already forces a miss, so the
        pair times the miss path without waiting out a 45s TTL."""
        body = (
            await seeded_client.get(
                "/api/events/typeahead?q=red sox&debug_evidence=1&debug_timing=1"
            )
        ).json()
        assert body["suggestions"], "vacuous"
        assert "_evidence" in body
        assert "debug_timing" in body
        assert len(body["_evidence"]) == len(body["suggestions"])


class TestCacheIsolation:
    """A debug answer and a normal answer are never interchangeable in a cache."""

    async def _get(self, seeded_client, url, fake):
        with patch("app.tasks.redis_state.get_redis_client", return_value=fake):
            return (await seeded_client.get(url)).json()

    async def test_timing_request_never_writes_the_cache(self, seeded_client):
        fake = _FakeRedis()
        body = await self._get(
            seeded_client, "/api/events/typeahead?q=red sox&debug_timing=1", fake
        )
        assert "debug_timing" in body, "vacuous — no timing block was produced"
        assert fake.writes == [], (
            "a timing answer was cached; every normal user typing this prefix would "
            "be served per-stage server timings for the full TTL"
        )

    async def test_timing_request_never_reads_the_cache(self, seeded_client):
        """The reason is specific to this flag, and it is gotcha #53.

        A cached entry has no `debug_timing` key. Serving one would answer a
        timing request with SILENCE — which is indistinguishable from a stage
        that cost nothing — and it would do so on exactly the miss path #1866
        exists to measure.
        """
        key = "bainluck:typeahead:red sox"
        fake = _FakeRedis({key: '{"suggestions": [], "query": "red sox"}'})
        body = await self._get(
            seeded_client, "/api/events/typeahead?q=red sox&debug_timing=1", fake
        )
        assert key not in fake.reads
        assert "debug_timing" in body, (
            "a cached entry was served to a timing request — the instrument would "
            "report no stages and read as a free request"
        )

    async def test_normal_request_still_uses_the_cache(self, seeded_client):
        """The isolation must not have disabled caching for everyone else."""
        key = "bainluck:typeahead:red sox"
        sentinel = '{"suggestions": [{"text": "FROM CACHE"}], "query": "red sox"}'
        fake = _FakeRedis({key: sentinel})
        body = await self._get(seeded_client, "/api/events/typeahead?q=red sox", fake)
        assert body["suggestions"] == [{"text": "FROM CACHE"}]
        assert key in fake.reads
