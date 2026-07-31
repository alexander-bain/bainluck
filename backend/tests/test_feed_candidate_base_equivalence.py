"""Real feed/base-boundary equivalence for the Discover candidate-ID base (Queue 285).

Translates the frozen offline contracts into tests bound to the LIVE code:

* **C85 (`cold-feed-latency-authority/v1`)** — the real ``candidate_base.base_identity``
  reproduces the oracle's user-independent ``candidate_base_key`` (stable across
  page one / page two / native shapes), while the response cache key still
  fragments ``limit``/``offset`` — proving the candidate base is reused across
  pages that the response cache must keep distinct.

* **`futures_pool_equivalence`** — the extracted ``feed._compute_ordered_candidate_ids``
  produces the exact order-preserving deduped union the offline oracle
  ``ordered_candidate_ids`` specifies, so a precomputed/base-served candidate set
  is byte-for-byte the list the inline direct queries would have produced.

* The consume-side gating (base hit -> zero candidate-pool SQL; miss -> direct
  queries) is asserted against the live ``_score_futures`` source.
"""

from __future__ import annotations

import importlib.util
import inspect
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

import app.routes.feed as feed_mod
from app.utils import candidate_base as cb
from app.utils.personalization import PersonalizationContext
from scripts.evals.cold_feed_latency_authority import (
    candidate_base_key,
    load_fixture,
    response_cache_key,
)


NOW = datetime(2026, 7, 30, 12, 0, 0, tzinfo=timezone.utc)


# Load the offline equivalence oracle (independent of app code).
_EQUIV_SCRIPT = Path(__file__).parents[1] / "scripts" / "evals" / "cold_feed_equivalence.py"
_SPEC = importlib.util.spec_from_file_location("cold_feed_equivalence_boundary", _EQUIV_SCRIPT)
assert _SPEC and _SPEC.loader
_EQUIV = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _EQUIV
_SPEC.loader.exec_module(_EQUIV)


# --- C85: candidate base key vs response cache key ----------------------------
def test_real_identity_matches_c85_candidate_base_key():
    """Every C85 scenario's oracle candidate_base_key equals the live identity.

    The fixtures are all the anonymous default (all / no-static-tags), so the live
    ``base_identity(None, None)`` must equal the oracle key for each scenario —
    binding the offline contract to the shipped keying.
    """
    corpus = load_fixture()
    live_default = cb.base_identity(None, None)
    for row in corpus["scenarios"]:
        assert candidate_base_key(row) == live_default


def test_candidate_base_key_is_stable_across_pages_while_response_key_fragments():
    rows = {row["id"]: row for row in load_fixture()["scenarios"]}
    page1 = rows["web_cold_page_one"]
    page2 = rows["web_cold_page_two_reuses_base"]
    native1 = rows["native_current_first_page"]
    native2 = rows["native_current_page_two"]

    # The candidate base is REUSED across every page/limit/offset/client shape...
    live_keys = {cb.base_identity(None, None) for _ in (page1, page2, native1, native2)}
    assert live_keys == {"discover-candidates:v1:all:no-static-tags"}

    # ...but the response cache key MUST stay page-specific (limit/offset fragment).
    assert response_cache_key(page1) != response_cache_key(page2)
    assert response_cache_key(page1) != response_cache_key(native1)


def test_identity_excludes_limit_offset_user_session():
    # Structurally, base_identity only accepts (sport, static tags) — no request
    # shape can enter it. Concretely, the anon default is a fixed string that
    # carries none of the response-key fragments (limit/offset/user-id/session-id).
    key = cb.base_identity(None, None)
    assert key == "discover-candidates:v1:all:no-static-tags"
    for token in ("limit", "offset", ":20:", ":50:", ":200:", "u:1", "anon"):
        assert token not in key
    # The keying function's signature proves it: only sport + static tags.
    params = set(inspect.signature(cb.base_identity).parameters)
    assert params == {"sport_filter", "static_tag_filter"}


# --- futures_pool_equivalence at the live helper boundary ---------------------
class _FakeScalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _FakeScalars(self._rows)


class _FakeDB:
    """Returns queued pool-id lists in the helper's fixed execution order."""

    def __init__(self, pool_rows):
        self._queue = list(pool_rows)
        self.executed = 0

    async def execute(self, query):
        rows = self._queue[self.executed]
        self.executed += 1
        return _FakeResult(rows)


# The eight ``db.execute`` pools, in the exact order _compute_ordered_candidate_ids
# runs them, plus the external-curator lane that runs FIRST and is concatenated
# ahead of them. This mirrors the concatenation order at the candidate-ID
# boundary (feed.py) that the offline oracle also encodes.
_LANE_ORDER = [
    "external_curator_recall",
    "sports",
    "sports_postseason",
    "sports_editorial_recall",
    "nonsports_volume",
    "nonsports_movement",
    "nonsports_enriched",
    "nonsports_editorial_recall",
    "nonsports_timely",
]


async def _run_helper(monkeypatch, lanes):
    curator_ids = lanes["external_curator_recall"]

    async def _fake_curator(db, base_filters, *, row_limit, market_limit):
        return list(curator_ids)

    monkeypatch.setattr(feed_mod, "_external_curator_recall_market_ids", _fake_curator)
    # The eight executed pools, in order (external curator is not via db.execute).
    pool_rows = [lanes[name] for name in _LANE_ORDER[1:]]
    db = _FakeDB(pool_rows)
    (
        market_ids,
        pool_counts,
        curator_ids,
    ) = await feed_mod._compute_ordered_candidate_ids(db, NOW, None, None)
    assert db.executed == 8  # exactly the eight pool queries, serially
    assert curator_ids == list(lanes["external_curator_recall"])
    return market_ids, pool_counts


def _oracle_fixture(lanes):
    """Build a futures_pool_equivalence-shaped fixture for the oracle dedup."""
    return {
        "pool_order": list(_LANE_ORDER),
        "pools": {
            name: {"rows": [{"id": i} for i in ids], "limit": len(ids)}
            for name, ids in lanes.items()
        },
    }


@pytest.mark.asyncio
async def test_helper_dedup_order_matches_offline_oracle(monkeypatch):
    # Deliberate cross-lane duplicates to exercise order-preserving dedup.
    lanes = {
        "external_curator_recall": [100, 101, 102],
        "sports": [1, 2, 100],  # 100 already seen (curator)
        "sports_postseason": [2, 3],  # 2 already seen (sports)
        "sports_editorial_recall": [3, 4],  # 3 already seen
        "nonsports_volume": [5, 101],  # 101 already seen (curator)
        "nonsports_movement": [5, 6],  # 5 already seen
        "nonsports_enriched": [7],
        "nonsports_editorial_recall": [7, 8],  # 7 already seen
        "nonsports_timely": [8, 9],  # 8 already seen
    }
    market_ids, pool_counts = await _run_helper(monkeypatch, lanes)

    oracle_ids = _EQUIV.ordered_candidate_ids(_oracle_fixture(lanes))
    assert market_ids == oracle_ids
    assert market_ids == [100, 101, 102, 1, 2, 3, 4, 5, 6, 7, 8, 9]

    # pool_counts are the RAW per-lane row counts (provenance only, never reorders).
    assert pool_counts["external_curator_recall"] == 3
    assert pool_counts["sports"] == 3
    assert pool_counts["deduped"] == 12


@pytest.mark.asyncio
async def test_helper_empty_pools_return_empty(monkeypatch):
    lanes = {name: [] for name in _LANE_ORDER}
    market_ids, pool_counts = await _run_helper(monkeypatch, lanes)
    assert market_ids == []
    assert pool_counts["deduped"] == 0


# --- Consume-side gating in _score_futures ------------------------------------
def test_score_futures_reads_base_before_running_pools():
    """A base hit must skip the candidate queries entirely; a miss runs them.

    Guards the live wiring: ``_score_futures`` calls ``get_candidate_base`` and
    only runs ``_compute_ordered_candidate_ids`` on the miss branch (with a
    best-effort publish), never unconditionally.
    """
    src = inspect.getsource(feed_mod._score_futures)
    assert "get_candidate_base" in src
    assert "_compute_ordered_candidate_ids" in src
    assert "publish_candidate_base" in src
    # The direct-query call is gated behind the base-miss branch, not the hit path.
    hit_idx = src.index("if _cb_base_ids is not None:")
    compute_idx = src.index("_compute_ordered_candidate_ids(")
    assert hit_idx < compute_idx, "direct queries must be under the base-miss branch"


# --- Mechanical base-hit gating: a hit runs ZERO candidate-pool SQL -----------
class _CountingDB:
    """Records every executed query so a base hit's SQL can be counted."""

    def __init__(self):
        self.executed: list = []

    async def execute(self, query):
        self.executed.append(query)
        return _FakeResult([])


class _MarketsScalars:
    def unique(self):
        return self

    def all(self):
        return []


class _MarketsResult:
    def scalars(self):
        return _MarketsScalars()


async def _score_futures_with_base(monkeypatch, base_result):
    """Run ``_score_futures`` with ``get_candidate_base`` forced to ``base_result``.

    Returns ``(db, helper_calls)`` — the counting session and how many times the
    candidate-pool builder was invoked.
    """
    from app.utils import candidate_base as cb_mod

    async def _fake_get_base(now, sport_filter, static_tag_filter, *, stages=None):
        return base_result

    monkeypatch.setattr(cb_mod, "get_candidate_base", _fake_get_base)

    helper_calls: list = []

    async def _fake_helper(db, now, sport_filter, static_tag_filter=None, **kwargs):
        helper_calls.append(True)
        return [7, 8], {"deduped": 2}, []

    monkeypatch.setattr(feed_mod, "_compute_ordered_candidate_ids", _fake_helper)

    # Keep the best-effort publish off the network in tests.
    from app.utils import request_cache as _rc_mod

    scheduled: list = []

    def _capture(coro):
        scheduled.append(coro)
        coro.close()  # never awaited in-test; avoid the un-awaited warning

    monkeypatch.setattr(_rc_mod, "schedule_background", _capture)

    db = _CountingDB()
    # The market-load query returns no rows, so _score_futures returns early —
    # after the candidate stage, which is all this test measures.
    db.execute = _make_market_load_execute(db)

    ctx = PersonalizationContext()
    result = await feed_mod._score_futures(db, NOW, None, ctx)
    assert result == []
    return db, helper_calls


def _make_market_load_execute(db):
    async def _execute(query):
        db.executed.append(query)
        return _MarketsResult()

    return _execute


@pytest.mark.asyncio
async def test_base_hit_runs_zero_candidate_pool_sql(monkeypatch):
    """Queue 286: a base hit must issue NO candidate-pool query.

    Queue 285 asserted this by reading ``_score_futures``'s source. This measures
    it: with a served base, the only SQL ``_score_futures`` issues before its
    early return is the single market-load ``SELECT``, and the pool builder is
    never called.
    """
    db, helper_calls = await _score_futures_with_base(
        monkeypatch, ([101, 102, 103], "fresh", [101])
    )

    assert helper_calls == [], "a base hit must not run the candidate-pool queries"
    assert len(db.executed) == 1, (
        "a base hit must issue exactly one query (the market load), got "
        f"{len(db.executed)}"
    )
    compiled = str(db.executed[0]).lower()
    assert "from futures_markets" in compiled


@pytest.mark.asyncio
async def test_base_miss_does_run_the_candidate_pool_builder(monkeypatch):
    """The negative control: without this, the test above would pass vacuously."""
    db, helper_calls = await _score_futures_with_base(
        monkeypatch, (None, "direct", None)
    )

    assert helper_calls == [True], "a base miss must run the candidate-pool builder"
