"""Queue #257 Item 1 — ONE canonical eligible population + the field-completeness invariant.

Two guarantees are covered here:

1. **One population, two serve paths cannot diverge.** The scheduled precompute
   task and the ``/api/calibration`` cold-cache fallback both compute the payload
   through the single shared ``compute_calibration_payload`` — the route delegates
   to it and the task caches its output verbatim. Previously each carried its own
   copy of the CTE chain + post-processing and they had drifted in ~11 material
   ways (missing liquidity / poly-placeholder / malformed-binary / golf-placeholder
   exclusions, a looser resolution-source filter, equal- vs n-weighted MCE), so a
   cold serve showed a different curve than the Redis serve.

2. **Field-completeness before normalization.** A mutually-exclusive / field market
   is normalized (cp / per-market sum) ONLY when its captured partition is COMPLETE
   — every eligible member survived every published per-outcome exclusion AND the
   winner is among the survivors. A PARTIAL field (a member was excluded) is dropped
   from the curve with a machine-readable reason, never normalized over survivors,
   and the candidate/published split is reported. Read-side only (gotcha #21).

The heavy CTE SQL is Postgres-only and is not executed in this harness (no test
Postgres); as with every other calibration exclusion, the tested contract is the
canonical Python mirror kept in sync with the SQL via source inspection, plus the
shared-payload equivalence at the response-dict level.
"""

import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.routes import calibration
from app.tasks import precompute_calibration
from app.tasks.precompute_calibration import (
    FIELD_COMPLETENESS_RULE_TEXT,
    compute_calibration_payload,
    field_is_complete_for_normalization,
    market_needs_mex_normalization,
)


# ---------------------------------------------------------------------------
# The canonical Python mirror of the field_completeness CTE gate.
# ---------------------------------------------------------------------------
class TestFieldCompletenessHelper:
    def test_complete_field_is_normalized(self):
        # Every eligible member survived, the winner survived, still a partition.
        assert field_is_complete_for_normalization(
            eligible_n=8, survivor_n=8, survivor_win_n=1
        ) is True

    def test_partial_field_any_member_excluded_is_not_normalized(self):
        # One eligible member was removed by a published exclusion → the survivor
        # cp sum no longer represents the whole field, so normalizing the
        # survivors would inflate them. Excluded, never normalized over survivors.
        assert field_is_complete_for_normalization(
            eligible_n=8, survivor_n=7, survivor_win_n=1
        ) is False

    def test_winner_excluded_is_not_normalized(self):
        # The winner itself was excluded (survivor_win_n == 0): normalizing the
        # remaining losers to sum 1.0 would be fiction.
        assert field_is_complete_for_normalization(
            eligible_n=8, survivor_n=7, survivor_win_n=0
        ) is False

    def test_collapsed_below_three_is_not_normalized(self):
        # Exclusions collapsed the field below a >=3 partition, even if survivors
        # == eligible (a genuinely tiny field is not a normalization target).
        assert field_is_complete_for_normalization(
            eligible_n=2, survivor_n=2, survivor_win_n=1
        ) is False

    def test_candidate_gate_is_independent_of_completeness(self):
        # market_needs_mex_normalization only decides CANDIDACY (shape/sum); the
        # completeness gate is the separate, stricter publish decision.
        assert market_needs_mex_normalization(8, 1, 4.56) is True
        # A candidate can still be a partial field and thus not published.
        assert field_is_complete_for_normalization(8, 5, 1) is False


class TestFieldCompletenessRuleText:
    def test_rule_describes_the_invariant(self):
        t = FIELD_COMPLETENESS_RULE_TEXT.lower()
        assert "complete" in t
        assert "partial" in t
        assert "survivor" in t or "survivors" in t
        assert "never mutates" in t


# ---------------------------------------------------------------------------
# The shared SQL embeds the completeness gate + candidate/published transparency.
# ---------------------------------------------------------------------------
class TestSharedQueryEmbedsCompleteness:
    def test_query_embeds_field_completeness_gate(self):
        src = (inspect.getsource(compute_calibration_payload)
               + precompute_calibration._calibration_population_ctes())
        # The completeness aggregation + the gated normalization CTE.
        assert "field_completeness AS (" in src
        assert "normalized AS (" in src
        assert "survivor_n" in src and "survivor_win_n" in src and "eligible_n" in src
        # Normalization is gated on completeness; partial fields are flagged.
        assert "is_field_incomplete" in src
        assert "fc.survivor_n = fc.eligible_n" in src
        # The divisor is the per-market cp sum (== survivor sum when complete).
        assert "ro.raw_cp / ro.mnm_cp_sum" in src

    def test_partial_fields_dropped_from_deduped(self):
        src = (inspect.getsource(compute_calibration_payload)
               + precompute_calibration._calibration_population_ctes())
        # deduped excludes incomplete fields — never normalized over survivors.
        assert "AND NOT ro.is_field_incomplete" in src

    def test_candidate_vs_published_counts_surfaced(self):
        src = (inspect.getsource(compute_calibration_payload)
               + precompute_calibration._calibration_population_ctes())
        assert "mex_candidate_markets" in src
        assert "mex_normalized_markets" in src
        assert "field_incomplete_markets" in src
        assert "field_incomplete_outcomes" in src
        assert '"field_completeness"' in src

    def test_gate_is_read_side_only(self):
        src = (inspect.getsource(compute_calibration_payload)
               + precompute_calibration._calibration_population_ctes()).lower()
        assert "update futures_outcomes" not in src
        assert "update futures_markets" not in src
        assert "delete from futures_outcomes" not in src


# ---------------------------------------------------------------------------
# ONE population: the route delegates to the shared compute; the task caches it.
# ---------------------------------------------------------------------------
class TestSingleCanonicalPopulation:
    def test_route_carries_no_population_query_of_any_kind(self):
        """Queue #257 forbade a SECOND copy of the population CTE in the route.

        Queue 300B went further and forbade the route running the population
        query at ALL — a shared implementation was still a ~22-minute statement
        an anonymous GET could start. So the old half of this assertion (the
        route must CALL the shared compute) is inverted; the rest stands.
        """
        src = inspect.getsource(calibration.public_calibration)
        # The prose explains why the build is absent; the code must not call it.
        body = src.replace("``compute_calibration_payload``", "")
        assert "compute_calibration_payload" not in body
        # And it still carries no copy of the resolved-outcome CTE chain (the
        # ~650-line duplicate that had drifted). One population, one divisor.
        assert "ranked_outcomes" not in src
        assert "mex_norm_markets" not in src
        assert "virtual_market" not in src

    def test_precompute_task_caches_shared_payload(self):
        # Queue 300M split the beat into an orchestrator (ledger + checkpoint)
        # and the build itself. The invariant this guards is unchanged: the
        # scheduled path computes the ONE shared payload and publishes it — it
        # never grows its own copy of the population.
        src = (
            inspect.getsource(precompute_calibration._precompute_calibration_main)
            + inspect.getsource(precompute_calibration._run_calibration_main_build)
        )
        assert "compute_calibration_payload" in src
        assert "_publish_calibration_main" in src
        assert "ranked_outcomes" not in src
        # Queue 272 (#1459): publication writes the canonical main key (via the
        # helper + module constant), plus the durable last-good survivor key.
        pub = inspect.getsource(precompute_calibration._publish_calibration_main)
        assert precompute_calibration._MAIN_KEY == "bainluck:calibration:main"
        assert "rc.set(" in pub
        assert "_MAIN_KEY" in pub
        assert "_MAIN_LAST_GOOD_KEY" in pub


# ---------------------------------------------------------------------------
# Payload equivalence: same db → the route's fallback and the shared compute
# return byte-identical payloads (modulo the generated_at stamp). This is the
# structural proof the two serve paths cannot diverge across every exclusion
# shape, because they are literally the same code path.
# ---------------------------------------------------------------------------
def _futures_row(**kw):
    base = dict(
        bucket_idx=6, source="kalshi", category="politics", price_moved=True,
        n=5, winners=1, avg_prob=0.2, sum_prob=1.0, sum_sq_err=0.5,
        kalshi_included=120, kalshi_excluded=8, poly_placeholder_excluded=3,
        poly_included=40, poly_never_traded_total=6, poly_never_traded_in_curve=2,
        both_false_excluded=4, both_winner_excluded=1, golf_placeholder_excluded=7,
        mex_normalized_outcomes=15, mex_candidate_markets=9,
        mex_normalized_markets=6, field_incomplete_markets=3,
        field_incomplete_outcomes=21, esports_bundle_excluded=5,
        kalshi_prop_threshold_excluded=2, weather_wide_spread_excluded=1,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _roster_row(**kw):
    """One row of the Queue 300E generation read: a market and its frozen vm.

    The generation read selects exactly ``market_id, source, vm_id, is_grouped``,
    so a roster row always carries all four; ``plan_units`` refuses one that does
    not, which is what caught this fake being monolith-shaped.
    """
    base = dict(market_id=1, source="kalshi", vm_id="e:1", is_grouped=False)
    base.update(kw)
    return SimpleNamespace(**base)


class _Result:
    def __init__(self, *, rows=(), scalar=None, one=None):
        self._rows, self._scalar, self._one = list(rows), scalar, one

    def all(self):
        return self._rows

    def scalar(self):
        return self._scalar

    def one(self):
        return self._one

    def first(self):
        return self._one


class _FakeDB:
    """A fake session returning the exact 10-query sequence the shared payload runs."""

    def __init__(self):
        self._results = [
            _Result(rows=[_futures_row()]),                       # main futures
            _Result(rows=[]),                                     # events
            _Result(rows=[]),                                     # spreads
            _Result(rows=[]),                                     # totals
            _Result(scalar=1234),                                 # total_markets
            _Result(one=SimpleNamespace(
                has_closing=10, needs_closing=2, total_completed=12)),  # closing
            _Result(scalar=30),                                  # void_sql
            _Result(rows=[]),                                     # heur_sql
            _Result(scalar=11),                                  # soccer_2way_sql
            _Result(one=SimpleNamespace(lo=None, hi=None)),      # date_range
        ]

    async def execute(self, statement, params=None):
        # Queue 274: the beat arms a `SET LOCAL statement_timeout` on its session
        # before the compute; that non-result statement must not consume one of the
        # queued query results (it would shift the whole sequence by one).
        # Queue 300M adds the same exemption for the overlap advisory lock (which
        # is the one statement here that carries bind params).
        # Queue 300B adds the session-identity tag, which is the same shape of
        # problem: a non-query statement that would otherwise eat the futures row
        # and shift every subsequent assertion onto the wrong result.
        text_form = str(statement).lower()
        if (
            "statement_timeout" in text_form
            or "advisory" in text_form
            or "set_config" in text_form
        ):
            return _Result(
                scalar=True,
                one=SimpleNamespace(name="bl1/test/test/test/test", pid=4080483),
            )
        # Queue 300E switched the staged futures path ON for the scheduled build,
        # which puts ONE extra statement in front of the futures read: the
        # generation read, which resolves the whole population's virtual-question
        # assignment before any bucket is computed. It is answered here rather
        # than from the queue, for the same reason as the exemptions above —
        # consuming a queued result would shift every later assertion onto the
        # wrong one.
        #
        # A single-market roster means ``plan_units`` plans exactly ONE unit, so
        # the unit read that follows pops the same main-futures result the
        # monolith would have read, and the merge folds one chunk. That is
        # deliberate: this test's subject is payload IDENTITY between the two
        # serve paths, and identity is only meaningful if the task's real path
        # produced the payload. Multi-chunk merge equivalence is not asserted
        # here — it has its own suite
        # (``test_calibration_staged_futures.test_a_three_chunk_split_merges_back_to_the_monolith``).
        if "select market_id, source, vm_id, is_grouped" in text_form:
            return _Result(rows=[_roster_row()])
        if not self._results:
            return _Result()
        return self._results.pop(0)

    async def commit(self):
        # Queue 300M commits at each phase boundary so a checkpoint can only
        # advance behind committed work. Read-only here; nothing to do.
        return None


@pytest.fixture(autouse=True)
def _disable_sample_gate(monkeypatch):
    monkeypatch.setattr(
        precompute_calibration, "_get_min_category_outcomes", lambda *_a, **_k: 0
    )


@pytest.mark.asyncio
async def test_route_serves_the_shared_compute_payload_unaltered():
    """One payload, one shape — the route is a serving tier, not a second builder.

    Queue 300B removed the route's in-request build, so the seam this guards
    moved: the shared compute publishes, and the route must hand back exactly
    what was published. (Before 300B this called the route and let it compute
    the payload itself, which is precisely the ability that queue removed.)
    """
    import time as _time

    shared = await compute_calibration_payload(_FakeDB())
    calibration._cache = {"data": shared, "timestamp": _time.time()}

    routed = await calibration.public_calibration(db=_FakeDB())

    assert routed == shared


@pytest.mark.asyncio
async def test_payload_reports_candidate_vs_published_split():
    payload = await compute_calibration_payload(_FakeDB())
    fc = payload["mex_normalization"]["field_completeness"]
    # Candidate markets split into published (complete) + excluded (partial).
    assert fc["candidate_markets"] == 9
    assert fc["published_normalized_markets"] == 6
    assert fc["field_incomplete_excluded_markets"] == 3
    assert fc["field_incomplete_excluded_outcomes"] == 21
    assert (
        fc["published_normalized_markets"] + fc["field_incomplete_excluded_markets"]
        == fc["candidate_markets"]
    )
    assert fc["rule"] == FIELD_COMPLETENESS_RULE_TEXT


@pytest.mark.asyncio
async def test_precompute_wrapper_caches_exact_shared_payload():
    """The task caches precisely what compute_calibration_payload returns."""
    captured = {}

    class _RC:
        def set(self, key, val, ex=None):
            captured[key] = val

        def get(self, key):
            return None

    fake_db = _FakeDB()

    class _Sess:
        async def __aenter__(self):
            return fake_db

        async def __aexit__(self, *a):
            return False

    async def _durable_ok(envelope):
        return {"status": "ok", "identity": envelope.identity,
                "generation": envelope.generation}

    async def _durable_missing(*_a, **_k):
        from app.utils.durable_state import EnvelopeRead

        return EnvelopeRead(status="missing", tier="durable")

    with patch(
        "app.tasks.base.get_task_session", return_value=_Sess()
    ), patch(
        "app.tasks.redis_state.get_redis_client", return_value=_RC()
    ), patch(
        # Queue 298 made the durable write a precondition of publishing. This
        # test is about payload IDENTITY between the two serve paths, not about
        # durability, and `_FakeDB` does not model the upsert — so stub the
        # substrate and let the publish proceed.
        "app.services.durable_snapshots.publish_snapshot_standalone", _durable_ok
    ), patch(
        # Queue 300M reads the phase ledger + checkpoint before building. Those
        # reads share this test's single fake session, and an unstubbed SELECT
        # would consume two of its queued query results and shift the whole
        # sequence. "Nothing stored yet" is also the honest first-run state.
        "app.services.durable_snapshots.read_snapshot_standalone", _durable_missing
    ):
        result = await precompute_calibration._precompute_calibration_main()

    assert result["status"] == "ok"
    assert "bainluck:calibration:main" in captured
    import json
    cached = json.loads(captured["bainluck:calibration:main"])
    # The cached payload carries the field-completeness split — the same block the
    # route serves — so both serve paths publish one identical population.
    assert "field_completeness" in cached["mex_normalization"]
