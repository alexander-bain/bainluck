"""RED-FIRST GATE for LAT-P174 (#2143 residual) — share `futures.market_load`.

## The measurement this gate exists to hold

Production, 2026-08-31, ONE returning reader (a real `x-session-id` carrying 117
recorded Discover impressions), `/api/feed?limit=20&event_pct=0.15`, server-side
stage header — not wall clock, not a p50 over mixed cache states (ruling 127):

    x-feed-cache: miss      x-feed-elapsed-ms: 1533.04
    x-feed-shared: canonical_counts,concepts
    futures=1043.96   futures.market_load=588.48   futures.scoring_loop=433.64
    events=219.28     personalization=113.08       golf=88.19  ranking=41.78

`futures.market_load` is **38% of the whole request**, and `x-feed-shared` names
the two artifacts that were already shared while this one rebuilt.

LAT-P173 established who pays it: a returning reader misses BY CONSTRUCTION
(any recorded interaction makes `ctx != PersonalizationContext()`, forfeiting
both the LAT-P089 shared entry and the LAT-P141 page base), and 429 sessions are
in that state. The stranger gets 6-28 ms; the reader who uses the product gets
892-1,533 ms.

## Why this artifact is shareable and why it was not shared before

The rows are a pure function of the ordered candidate-ID list, which
`candidate_base.py` already computes principal-independently — the pools depend
only on `(now, sport_filter, static_tag_filter)`. Two principals a second apart
issue the identical SELECT and receive the identical rows.

`principal_independent_cache.py` says in its own docstring why it stopped short:

    "A hydrated ORM row therefore CANNOT enter this cache. ... and it is why
     `futures.market_load` (567-617ms of hydrated rows) is left on the table."

That refusal is correct and is NOT relaxed here. What changes is the carrier:
the shared artifact is a plain-data table of loaded COLUMN VALUES
(`app/utils/futures_market_snapshot.py`), and the hydrated objects are rebuilt
per request as inert snapshots. `assert_plain_data` still refuses an ORM row,
mechanically, and `test_futures_market_snapshot_lat_p174.py` proves the artifact
this route publishes passes it.

## What "red" looks like before the wiring

`test_a_second_principal_does_not_re_issue_the_market_load_select` fails with
two SELECTs instead of one. That is the ship, and it is the only assertion in
this file that can go red for the absence of the ship rather than for a
regression in something else.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw
from app.utils import futures_market_snapshot as fms

# --------------------------------------------------------------------------
# harness
# --------------------------------------------------------------------------

#: A fixed candidate base. Two IDs is enough — the claim is "one SELECT, not
#: two", and it is independent of how many rows that SELECT returns. It is NOT
#: empty on purpose: an empty candidate list makes `_score_futures` return
#: before the SELECT, which would let a broken share pass by doing nothing twice
#: (gotcha #53 — an empty result is a shape, not a fact).
_BASE_IDS = (9101, 9102)


def _fake_market(market_id: int, name: str):
    """A stand-in for one hydrated candidate row.

    Deliberately built as a `FuturesMarketSnapshot`: `to_plain` reads a row
    through `instance.__dict__`, so a snapshot presents to it exactly as a
    `load_only`-restricted ORM instance does. Using the snapshot type here keeps
    the fixture from inventing a third shape that neither production nor the
    codec ever sees.
    """
    now = datetime.now(timezone.utc)
    values = {
        "id": market_id,
        "name": name,
        "source": "polymarket",
        "external_id": f"ext-{market_id}",
        "sport_id": None,
        "category": "politics",
        "llm_sport_category": "politics",
        "market_tier": 2,
        "market_type": "claim",
        "canonical_market_key": f"canon-{market_id}",
        "group_id": None,
        "group_type": None,
        "image_url": None,
        "image_width": None,
        "image_height": None,
        "hook_description": None,
        "hook_generated_at": None,
        "hook_leader_at_generation": None,
        "market_metadata": {"polymarket_event_id": str(market_id)},
        "curation_score_adj": 0,
        "volume_24h": Decimal("1234.56"),
        "updated_at": now,
        "commence_time": now - timedelta(days=1),
        "resolution_date": now + timedelta(days=30),
        "status": "open",
        "created_at": now - timedelta(days=10),
        "llm_league": None,
        "llm_gender": None,
        "llm_level": None,
    }
    # Keyed, then ordered by `OUTCOME_COLUMNS` — the same idiom as the market
    # values above, and for the same reason. A positional literal here would
    # zip-truncate the day a column is appended (`__init__` uses `zip`), so the
    # fixture would quietly stop carrying the new column instead of failing;
    # by name, the omission is a `KeyError` that names the column.
    def _outcome_values(index: int, outcome_name: str, prob: str) -> dict:
        return {
            "id": market_id * 10 + index,
            "name": outcome_name,
            "team_id": None,
            "current_probability": Decimal(prob),
            "probability_change_24h": Decimal("0.0100"),
            "rank": index + 1,
            "rank_change_24h": 0,
            "opening_probability": Decimal(prob),
            "calibration_probability": None,
            "current_yes_bid": Decimal("0.4000"),
            "current_yes_ask": Decimal("0.4200"),
            "external_id": f"ext-{market_id}-{index}",
        }

    outcomes = [
        fms.FuturesOutcomeSnapshot(
            [_outcome_values(i, outcome_name, prob)[c] for c in fms.OUTCOME_COLUMNS]
        )
        for i, (outcome_name, prob) in enumerate(
            (("Yes", "0.610000"), ("No", "0.390000"))
        )
    ]
    return fms.FuturesMarketSnapshot(
        [values[c] for c in fms.MARKET_COLUMNS], outcomes, None
    )


def _is_hydration_select(text: str) -> bool:
    """Whether a compiled statement is the candidate hydration SELECT."""
    return "FROM futures_markets" in text and all(
        f"futures_markets.{column}" in text for column in fms.MARKET_COLUMNS
    )


@pytest.fixture(autouse=True)
def _clean_shared_cache():
    """Start and end every test with an empty process-local shared cache.

    A process-global cache that leaks between tests produces the single most
    misleading failure here: a test that passes because a PREVIOUS test warmed
    the artifact it is trying to prove gets warmed.
    """
    from app.utils.principal_independent_cache import clear_shared_builds

    clear_shared_builds()
    yield
    clear_shared_builds()


@pytest.fixture(autouse=True)
def _no_cross_worker(monkeypatch):
    """Pin the Redis tier OFF for this file.

    The claim under test is "the artifact is shared", and the process-local tier
    is sufficient to prove it. Leaving L2 live would make the assertions depend
    on whether the test environment happens to have a reachable Redis, which is
    a flake, not a signal. `test_feed_shared_build_survives_a_cold_worker.py`
    owns the cross-worker claim.
    """
    monkeypatch.setenv("FEED_SHARED_BUILD_CROSS_WORKER", "0")


@pytest.fixture
def market_load_counter(monkeypatch):
    """Count the candidate market SELECT, and the personalization build.

    The proof is a CALL COUNT, not a duration — a timing assertion on a cache is
    a flake generator. The second counter is what keeps the first honest:
    `selects == 1` alone would also be satisfied by a second request that never
    reached a cold build at all (served from the response cache, or aborted).
    `personalization == 2` is the independent witness that two real builds ran,
    so `selects == 1` can only mean sharing.
    """
    from app.routes import feed as feed_module
    from app.utils import candidate_base as candidate_base_module

    counts = {"selects": 0, "personalization": 0}
    markets = [_fake_market(mid, f"Market {mid}") for mid in _BASE_IDS]

    async def _fake_get_candidate_base(now, sport_filter, static_tag_filter, stages=None):
        return list(_BASE_IDS), "fresh", set()

    monkeypatch.setattr(
        candidate_base_module, "get_candidate_base", _fake_get_candidate_base
    )

    real_ctx = feed_module._load_personalization_context

    async def _counting_ctx(*args, **kwargs):
        counts["personalization"] += 1
        return await real_ctx(*args, **kwargs)

    monkeypatch.setattr(feed_module, "_load_personalization_context", _counting_ctx)
    return counts, markets


@pytest.fixture
async def two_principal_client(monkeypatch, market_load_counter):
    """A feed client whose DB answers the candidate market SELECT and nothing
    else, so two principals can be taken without Postgres."""
    counts, markets = market_load_counter
    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")

    from app.main import app

    session = AsyncMock()

    def _empty_result():
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        result.scalars.return_value.unique.return_value.all.return_value = []
        result.scalars.return_value.first.return_value = None
        result.scalar_one_or_none.return_value = None
        result.scalar.return_value = None
        result.fetchall.return_value = []
        result.all.return_value = []
        result.first.return_value = None
        return result

    def _markets_result():
        result = _empty_result()
        result.scalars.return_value.unique.return_value.all.return_value = list(markets)
        return result

    async def _execute(statement, *args, **kwargs):
        # Identify the candidate hydration SELECT by its LOAD SURFACE: the one
        # statement that selects every column in `MARKET_COLUMNS`. Matching on
        # call ORDER would silently start counting a different statement the
        # first time anything upstream adds a query, and matching on a loose
        # `FROM futures_markets` catches three unrelated statements in this very
        # build (a narrower candidate-pool select and the canonical-source CTE).
        # Deriving it from the module's own column tuple also means a column
        # added there keeps this matcher correct without an edit.
        text = str(statement)
        if _is_hydration_select(text):
            counts["selects"] += 1
            return _markets_result()
        return _empty_result()

    session.execute.side_effect = _execute

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


# --------------------------------------------------------------------------
# THE GATE
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_second_principal_does_not_re_issue_the_market_load_select(
    two_principal_client, market_load_counter
):
    """THE ship. Two distinct principals, two cold builds, ONE hydration SELECT."""
    counts, _ = market_load_counter

    r1 = await two_principal_client.get(
        "/api/feed?limit=5", headers={"X-Session-Id": "lat-p174-principal-A"}
    )
    after_first = counts["selects"]
    r2 = await two_principal_client.get(
        "/api/feed?limit=5", headers={"X-Session-Id": "lat-p174-principal-B"}
    )
    second_request_selects = counts["selects"] - after_first

    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200, r2.text
    # "error" is the no-Redis test environment's build path; both values admit a
    # request to the cold build, and neither means the response cache served it.
    assert r1.headers.get("X-Feed-Cache") in ("miss", "error"), dict(r1.headers)
    assert r2.headers.get("X-Feed-Cache") in ("miss", "error"), dict(r2.headers)
    assert counts["personalization"] == 2, (
        "both requests must have reached a real cold build for this test to say "
        f"anything; personalization ran {counts['personalization']} time(s)"
    )
    # The first request MUST have paid for the hydration, or the second one
    # getting it free proves nothing (gotcha #53: a zero is a shape, not a fact).
    assert after_first >= 1, (
        "the first principal never issued the hydration SELECT, so this test "
        "cannot say anything about sharing it"
    )

    # THE claim, stated as a delta rather than a total: how many passes ONE
    # request makes is an implementation detail (the #1090 broaden re-score and
    # the primary pass both reach this seam), and pinning the total would make
    # this gate re-fail for a change that has nothing to do with sharing.
    assert second_request_selects == 0, (
        "the second principal re-issued the candidate hydration SELECT "
        f"{second_request_selects} time(s) after the first principal had "
        f"already built it ({after_first} on request one); LAT-P174 is that it "
        "re-issues none"
    )

    # And within one request the passes share it too — a strictly smaller claim
    # than the one above, kept separate so a regression says which broke.
    assert after_first == 1, (
        f"one request issued the hydration SELECT {after_first} times; the "
        "passes of a single build share one candidate base and must share its "
        "rows"
    )


@pytest.mark.asyncio
async def test_the_reuse_is_named_on_the_response_so_production_can_verify_it(
    two_principal_client
):
    """A share nobody can observe is a share nobody can confirm stopped working.

    This is also the after-side instrument: `x-feed-shared` on a returning
    reader's production request is how the ship is graded, and it is
    identity-free (a fixed allowlist of fixed strings, never a key).
    """
    await two_principal_client.get(
        "/api/feed?limit=5", headers={"X-Session-Id": "lat-p174-hdr-A"}
    )
    r2 = await two_principal_client.get(
        "/api/feed?limit=5", headers={"X-Session-Id": "lat-p174-hdr-B"}
    )

    shared = r2.headers.get("X-Feed-Shared", "")
    assert "market_load" in shared.split(","), (
        f"second principal did not report reusing the hydration rows: {shared!r}"
    )


@pytest.mark.asyncio
async def test_what_is_shared_is_plain_data_and_not_an_orm_row(two_principal_client):
    """#2107 / gotcha #6, mechanically.

    The stored artifact must survive `assert_plain_data`. This is the guard that
    would go red if someone "simplified" the snapshot away and cached the
    hydrated rows directly — which is the exact defect
    `principal_independent_cache.py` refused to risk.
    """
    r1 = await two_principal_client.get(
        "/api/feed?limit=5", headers={"X-Session-Id": "lat-p174-plain-A"}
    )
    assert r1.status_code == 200

    from app.utils.principal_independent_cache import (
        assert_plain_data,
        peek_shared_build,
    )

    stored = peek_shared_build("market_load")
    assert stored is not None, "nothing was shared after the first principal built"
    assert_plain_data(stored)
    assert fms.is_snapshot_payload(stored), stored


@pytest.mark.asyncio
async def test_the_first_principal_cannot_scribble_on_the_second_principals_rows(
    two_principal_client
):
    """Copies out, at this artifact's own seam.

    The scoring pass reads these rows, and the display chain mutates the cards
    built from them in place. A cache that handed out a reference would let
    principal A's build reach principal B's rows.
    """
    await two_principal_client.get(
        "/api/feed?limit=5", headers={"X-Session-Id": "lat-p174-iso-A"}
    )

    from app.utils.principal_independent_cache import peek_shared_build

    stored = peek_shared_build("market_load")
    name_index = fms.MARKET_COLUMNS.index("name")
    assert stored["rows"][0][0][name_index] == "Market 9101", stored["rows"][0][0]

    r2 = await two_principal_client.get(
        "/api/feed?limit=5", headers={"X-Session-Id": "lat-p174-iso-B"}
    )
    assert r2.status_code == 200
    stored_after = peek_shared_build("market_load")
    assert stored_after["rows"][0][0][name_index] == "Market 9101"


@pytest.mark.asyncio
async def test_the_shared_key_carries_no_principal(two_principal_client):
    """The key must be a function of the candidate base alone.

    `assert_shared_key` already refuses a non-scalar, which structurally blocks
    smuggling a `PersonalizationContext` in. This adds the narrower claim that
    matters for THIS artifact: two principals land on the SAME key, so the
    entry count after two distinct principals is one, not two.
    """
    await two_principal_client.get(
        "/api/feed?limit=5", headers={"X-Session-Id": "lat-p174-key-A"}
    )
    await two_principal_client.get(
        "/api/feed?limit=5", headers={"X-Session-Id": "lat-p174-key-B"}
    )

    from app.utils import principal_independent_cache as pic

    entries = pic._store.get("market_load") or {}
    assert len(entries) == 1, (
        f"two principals produced {len(entries)} market_load entries; the key is "
        "not principal-independent"
    )
