"""CAL-P1214 (#997, #1544) — bounded additive coverage: the rules that make it safe.

Four rules these defend, each of which has a named way of going wrong:

1. **The census must not cost the curve a single banked unit.** The whole reason
   this module exists instead of ``COVERAGE_CENSUS_ENABLED`` is that the flag is
   hashed into ``staged_unit_fingerprint()``. If the walk ever reaches the
   curve's statement, the bank is thrown away and publication freezes.
2. **One definition of a rung.** The census CTEs are re-assembled here because
   the canonical builder is flag-gated; a copy is only safe while it is proved
   identical, so the byte-equality test below is load-bearing, not decorative.
3. **A partial walk is never a total** (gotcha #53 / #51 — an empty 200 is not
   an absence).
4. **Never join today's coverage to yesterday's curve.** The reconciliation is
   a chain of three identities and every broken link must produce a REASON, not
   a number.
"""

from unittest.mock import patch

import pytest

import app.tasks.census_coverage_rungs as ccr
from app.utils.calibration_coverage_bridge import PLOTTED_RUNG, RUNG_KEYS


# ---------------------------------------------------------------------------
# 1. The census must not reach the curve's statement
# ---------------------------------------------------------------------------


def test_the_flag_that_would_wipe_the_bank_is_still_off():
    """The premise of this whole module.

    If someone flips this, the staged unit statement changes text, every
    fingerprint moves, the served bank is invalidated and the curve stops
    publishing until 128 units rebuild. This module exists so that never has to
    happen; the assertion states the premise so a flip cannot be silent.
    """
    from app.tasks.precompute_calibration import COVERAGE_CENSUS_ENABLED

    assert COVERAGE_CENSUS_ENABLED is False


def test_walking_does_not_change_the_staged_unit_fingerprint():
    """Building and using the walk's statements leaves the curve's digest alone.

    The fingerprint is read before and after the walk's SQL is assembled. It is
    the one measurement that proves "additive" in the sense that matters: the
    bank survives.
    """
    from app.utils.calibration_staged_futures import STAGED_FUTURES_SCHEMA
    from app.tasks.precompute_calibration import staged_unit_fingerprint

    before = staged_unit_fingerprint()
    ccr.chunk_rung_sql()
    ccr.global_rung_sql()
    after = staged_unit_fingerprint()

    assert before == after
    # And the coverage state is versioned separately, so a change to the rung
    # ladder can never invalidate the curve's bank.
    assert ccr.COVERAGE_RUNG_SCHEMA != STAGED_FUTURES_SCHEMA


# ---------------------------------------------------------------------------
# 2. One definition of a rung — the drift guard
# ---------------------------------------------------------------------------


def _roster_predicate():
    from app.tasks.precompute_calibration import (
        VM_ROSTER_MARKET_INFO_EXTRA,
        _roster_pushdown_predicates,
    )

    return _roster_pushdown_predicates(
        frozen_vm_roster=True, market_info_extra=VM_ROSTER_MARKET_INFO_EXTRA
    )[1]


def test_ctes_are_byte_identical_to_the_canonical_builder():
    """THE load-bearing guard: the copy is only safe while it is not a variant.

    Patching the flag on is how the canonical builder can be compared at all —
    it returns ``""`` while the flag is off, which is exactly why the assembly
    had to be restated rather than called.
    """
    import app.tasks.precompute_calibration as pc

    mine = ccr.coverage_bridge_ctes(roster_predicate=_roster_predicate())
    with patch.object(pc, "COVERAGE_CENSUS_ENABLED", True):
        canonical = pc._coverage_bridge_ctes(
            frozen=True, roster_predicate=_roster_predicate()
        )

    assert mine == canonical, "coverage CTE assembly drifted from the producer's"


def test_the_rung_predicates_are_imported_not_restated():
    """Every rung in the contract appears in the emitted CASE, by the contract's name."""
    from app.tasks.precompute_calibration import _COVERAGE_RUNG_PREDICATES

    ctes = ccr.coverage_bridge_ctes(roster_predicate=_roster_predicate())
    for key, sql in _COVERAGE_RUNG_PREDICATES:
        assert f"AS {ccr.coverage_bridge_column(key)}" in ctes
        if sql:
            assert f"WHEN {sql} THEN '{key}'" in ctes
    # The terminal rung is the ELSE, never a WHEN — it is the catch-all, and a
    # predicate for it would leave rows unclassified.
    assert f"ELSE '{_COVERAGE_RUNG_PREDICATES[-1][0]}'" in ctes


def test_column_naming_agrees_with_the_producer():
    from app.tasks.precompute_calibration import _coverage_bridge_column

    for key in RUNG_KEYS:
        assert ccr.coverage_bridge_column(key) == _coverage_bridge_column(key)


def test_chunk_statement_is_chunk_scoped_and_refuses_otherwise():
    """An unscoped universe multiplies the census by the chunk count.

    Measured failure, not a hypothetical: Queue 300D Item 2 saw
    ``cb_coverage_total`` come out ~N times the real figure with the rungs badly
    skewed, because each chunk rescanned every resolved priced outcome and LEFT
    JOINed it against only its own ``normalized``/``deduped``.
    """
    sql = ccr.chunk_rung_sql()
    assert "JOIN market_info mi ON mi.market_id = fo.market_id" in sql

    with patch.object(ccr, "coverage_bridge_ctes", return_value=",no_join_here AS (SELECT 1)"):
        with pytest.raises(ValueError, match="not chunk-scoped"):
            ccr.chunk_rung_sql()


def test_chunk_statement_binds_the_same_three_roster_params_as_the_curve():
    from app.tasks.precompute_calibration import (
        VM_ROSTER_IS_GROUPED_PARAM,
        VM_ROSTER_MARKET_IDS_PARAM,
        VM_ROSTER_VM_IDS_PARAM,
    )

    sql = ccr.chunk_rung_sql()
    for param in (
        VM_ROSTER_MARKET_IDS_PARAM,
        VM_ROSTER_VM_IDS_PARAM,
        VM_ROSTER_IS_GROUPED_PARAM,
    ):
        assert f":{param}" in sql


def test_both_statements_parse_as_postgres():
    sqlglot = pytest.importorskip("sqlglot")
    sqlglot.parse_one(ccr.chunk_rung_sql(), read="postgres")
    sqlglot.parse_one(ccr.global_rung_sql(), read="postgres")


def test_the_chunk_statement_selects_only_the_summary():
    """The bucket aggregation is named but never selected, so it is planned away.

    This is what makes the second pass affordable: PostgreSQL does not execute
    an unreferenced ``WITH`` subquery.
    """
    sql = ccr.chunk_rung_sql().rstrip()
    assert sql.endswith("SELECT * FROM coverage_bridge_summary")
    # bucketed/liq_summary/published_summary belong to the curve, not here.
    assert "liq_summary AS" not in sql
    assert "published_summary AS" not in sql


# ---------------------------------------------------------------------------
# 3. A partial walk is never a total
# ---------------------------------------------------------------------------


def _row(plotted=100, total=None, terminal=7, **over):
    """A summary row where the rungs sum to the universe by construction."""
    counts = {key: 1 for key in RUNG_KEYS}
    counts[PLOTTED_RUNG] = plotted
    counts.update(over)
    row = {ccr.coverage_bridge_column(k): v for k, v in counts.items()}
    row[ccr.TOTAL_COLUMN] = sum(counts.values()) if total is None else total
    row[ccr.TERMINAL_PRICE_COLUMN] = terminal
    return row


def _state(total_units=2):
    return ccr.new_state(
        population_version="q271",
        roster_digest="digest-A",
        buckets=128,
        total_units=total_units,
    )


def test_a_fresh_state_starts_at_checked_zero_on_every_column():
    state = _state()
    assert set(state.totals) == set(ccr.ACCUMULATED_COLUMNS)
    assert all(v == 0 for v in state.totals.values())
    assert not state.complete


def test_an_incomplete_walk_publishes_nothing():
    state = ccr.absorb_unit(_state(), unit_key="128:0", row=_row())
    assert not state.complete
    assert ccr.rung_counts_for_bridge(state) is None


def test_units_done_but_global_rung_missing_is_still_incomplete():
    """``market_result_unavailable`` belongs to no chunk. Without it the
    partition is short an entire rung, and the total would be confidently wrong."""
    state = _state(total_units=1)
    state = ccr.absorb_unit(state, unit_key="128:0", row=_row())
    assert not state.complete
    assert ccr.rung_counts_for_bridge(state) is None


def test_a_complete_walk_reconciles_and_publishes():
    state = _state(total_units=1)
    state = ccr.absorb_unit(state, unit_key="128:0", row=_row(plotted=100))
    state = ccr.absorb_global(
        state,
        row={
            ccr.coverage_bridge_column("market_result_unavailable"): 4,
            ccr.TOTAL_COLUMN: 4,
            ccr.TERMINAL_PRICE_COLUMN: 1,
        },
    )
    assert state.complete
    counts = ccr.rung_counts_for_bridge(state)
    assert counts is not None
    assert counts[PLOTTED_RUNG] == 100
    # The global cohort lands on its own rung and in the total, not anywhere else.
    assert counts["market_result_unavailable"] == 1 + 4
    assert sum(counts.values()) == state.totals[ccr.TOTAL_COLUMN]


def test_a_partition_that_does_not_sum_refuses_to_publish():
    """The rungs and the universe are two reads of the same CTE. If they
    disagree the CASE stopped being a partition, and the census says nothing."""
    state = _state(total_units=1)
    # total deliberately one higher than the rungs sum to
    row = _row(plotted=100)
    row[ccr.TOTAL_COLUMN] += 1
    state = ccr.absorb_unit(state, unit_key="128:0", row=row)
    state = ccr.absorb_global(state, row={ccr.TOTAL_COLUMN: 0})
    assert state.complete
    assert ccr.rung_counts_for_bridge(state) is None


def test_absorbing_a_unit_twice_does_not_double_count():
    """The walk is resumable, so a unit whose statement committed and whose
    state write did not WILL be replayed."""
    state = _state(total_units=2)
    once = ccr.absorb_unit(state, unit_key="128:0", row=_row())
    twice = ccr.absorb_unit(once, unit_key="128:0", row=_row())
    assert once.totals == twice.totals
    assert twice.done_units == ("128:0",)


def test_absorbing_the_global_rung_twice_does_not_double_count():
    state = ccr.absorb_global(_state(), row={ccr.TOTAL_COLUMN: 9})
    again = ccr.absorb_global(state, row={ccr.TOTAL_COLUMN: 9})
    assert again.totals[ccr.TOTAL_COLUMN] == 9


def test_a_non_integer_count_raises_rather_than_being_absorbed():
    """"This statement does not measure that" and "this statement measured it
    wrong" are different claims; only the first may pass silently."""
    row = _row()
    row[ccr.TOTAL_COLUMN] = "112"
    with pytest.raises(ValueError, match="not an int"):
        ccr.absorb_unit(_state(), unit_key="128:0", row=row)


def test_a_missing_column_contributes_zero_not_an_error():
    """The global statement legitimately emits three of the thirteen columns."""
    state = ccr.absorb_global(_state(), row={ccr.TOTAL_COLUMN: 4})
    assert state.totals[ccr.TOTAL_COLUMN] == 4
    assert state.totals[ccr.coverage_bridge_column(PLOTTED_RUNG)] == 0


def test_remaining_units_skips_what_is_banked():
    class _C:
        def __init__(self, key):
            self.key = key

    chunks = [_C("128:0"), _C("128:1"), _C("128:2")]
    state = ccr.absorb_unit(_state(total_units=3), unit_key="128:1", row=_row())
    assert [c.key for c in ccr.remaining_units(state, chunks)] == ["128:0", "128:2"]


# ---------------------------------------------------------------------------
# Resume / restart — and WHICH cause reset the walk
# ---------------------------------------------------------------------------


def _resume(stored, **over):
    kwargs = {
        "population_version": "q271",
        "roster_digest": "digest-A",
        "buckets": 128,
        "total_units": 2,
    }
    kwargs.update(over)
    return ccr.resume_or_restart(stored, **kwargs)


def test_a_clean_resume_keeps_the_banked_counts():
    banked = ccr.absorb_unit(_state(), unit_key="128:0", row=_row())
    state, reason = _resume(ccr.encode_state(banked))
    assert reason is None
    assert state.done_units == ("128:0",)
    assert state.totals == dict(banked.totals)


@pytest.mark.parametrize(
    "stored,expected",
    [
        (None, ccr.REASON_ABSENT),
        ("", ccr.REASON_ABSENT),
        ("{not json", ccr.REASON_MALFORMED),
        ("[]", ccr.REASON_MALFORMED),
    ],
)
def test_absent_and_malformed_are_told_apart(stored, expected):
    state, reason = _resume(stored)
    assert reason == expected
    assert state.done_units == ()


def test_a_moved_roster_discards_the_walk():
    """The banked counts describe a population that no longer exists. Mixing
    them with the new one is the LATE_ARRIVAL error the curve's own generation
    digest exists to catch."""
    banked = ccr.absorb_unit(_state(), unit_key="128:0", row=_row())
    state, reason = _resume(ccr.encode_state(banked), roster_digest="digest-B")
    assert reason == ccr.REASON_ROSTER_MOVED
    assert state.done_units == ()
    assert all(v == 0 for v in state.totals.values())


def test_a_new_population_version_discards_the_walk():
    banked = ccr.absorb_unit(_state(), unit_key="128:0", row=_row())
    state, reason = _resume(ccr.encode_state(banked), population_version="q272")
    assert reason == ccr.REASON_POPULATION_VERSION
    assert state.done_units == ()


def test_a_repartition_discards_the_walk():
    """A unit banked under one bucket count means a different slot under
    another; the keys would collide while describing different markets."""
    banked = ccr.absorb_unit(_state(), unit_key="128:0", row=_row())
    state, reason = _resume(ccr.encode_state(banked), buckets=64)
    assert reason == ccr.REASON_PARTITION
    assert state.done_units == ()


def test_a_schema_bump_discards_the_walk():
    banked = ccr.absorb_unit(_state(), unit_key="128:0", row=_row())
    encoded = ccr.encode_state(banked).replace(ccr.COVERAGE_RUNG_SCHEMA, "something/v9")
    state, reason = _resume(encoded)
    assert reason == ccr.REASON_SCHEMA
    assert state.done_units == ()


def test_encode_decode_round_trips():
    banked = ccr.absorb_global(
        ccr.absorb_unit(_state(), unit_key="128:0", row=_row()),
        row={ccr.TOTAL_COLUMN: 3},
    )
    assert ccr.decode_state(ccr.encode_state(banked)) == banked


def test_decode_refuses_a_state_whose_totals_are_not_integers():
    """WELL-FORMED JSON carrying a non-int count — the case that would otherwise
    reach the accumulator and be summed. A malformed-JSON specimen proves
    nothing here: it is caught one branch earlier by ``json.loads``."""
    import json

    banked = ccr.absorb_unit(_state(), unit_key="128:0", row=_row())
    data = json.loads(ccr.encode_state(banked))
    data["totals"][ccr.TOTAL_COLUMN] = "113"
    assert json.loads(json.dumps(data))["totals"][ccr.TOTAL_COLUMN] == "113"  # still valid JSON
    assert ccr.decode_state(json.dumps(data)) is None


def test_decode_refuses_a_state_whose_totals_are_booleans():
    """``True`` is an ``int`` in Python. Without the bool guard a flag would be
    summed into a count as 1."""
    import json

    banked = ccr.absorb_unit(_state(), unit_key="128:0", row=_row())
    data = json.loads(ccr.encode_state(banked))
    data["totals"][ccr.TOTAL_COLUMN] = True
    assert ccr.decode_state(json.dumps(data)) is None


# ---------------------------------------------------------------------------
# Publish / read — fail-open, and never a number it cannot stand behind
# ---------------------------------------------------------------------------


class _FakeRedis:
    def __init__(self, value=None, raises=False):
        self.value = value
        self.raises = raises
        self.written = None

    def get(self, key):
        if self.raises:
            raise RuntimeError("redis down")
        return self.value

    def setex(self, key, ttl, value):
        if self.raises:
            raise RuntimeError("redis down")
        self.written = (key, ttl, value)
        self.value = value


def _complete_state():
    state = ccr.new_state(
        population_version="q271", roster_digest="digest-A", buckets=128, total_units=1
    )
    state = ccr.absorb_unit(state, unit_key="128:0", row=_row(plotted=100))
    return ccr.absorb_global(state, row={ccr.TOTAL_COLUMN: 0})


def test_publish_writes_only_a_complete_walk():
    redis = _FakeRedis()
    partial = ccr.absorb_unit(_state(total_units=2), unit_key="128:0", row=_row())
    assert ccr.publish(redis, partial) is False
    assert redis.written is None

    assert ccr.publish(redis, _complete_state()) is True
    key, ttl, _ = redis.written
    assert key == ccr.PUBLISHED_KEY
    assert ttl == ccr.PUBLISHED_TTL_SECONDS


def test_publish_never_raises_when_redis_is_down():
    assert ccr.publish(_FakeRedis(raises=True), _complete_state()) is False
    assert ccr.publish(None, _complete_state()) is False


def test_the_published_key_is_not_the_working_key():
    """A partial walk must never be one malformed read away from being served
    as a total."""
    assert ccr.PUBLISHED_KEY != ccr.WORKING_KEY


@pytest.mark.parametrize(
    "redis",
    [
        None,
        _FakeRedis(value=None),
        _FakeRedis(value=""),
        _FakeRedis(value="{not json"),
        _FakeRedis(value="[]"),
        _FakeRedis(raises=True),
        _FakeRedis(value='{"schema":"other/v1","counts":{},"roster_digest":"d"}'),
    ],
)
def test_read_published_fails_open_on_every_bad_input(redis):
    assert ccr.read_published(redis) is None


def test_read_published_refuses_a_census_written_under_another_schema():
    """OTHERWISE WELL-FORMED: every rung present, the roster stamped, only the
    schema wrong. A blob that is also short a rung proves nothing about the
    schema check — it is refused one branch later either way."""
    import json

    blob = json.dumps(
        {
            "schema": "calibration-coverage-rungs/v0",
            "population_version": "q271",
            "roster_digest": "digest-A",
            "counts": {key: 1 for key in RUNG_KEYS},
        }
    )
    assert ccr.read_published(_FakeRedis(value=blob)) is None
    # ... and the same blob under the current schema IS accepted, so the test
    # above is about the schema and nothing else.
    ok = json.loads(blob)
    ok["schema"] = ccr.COVERAGE_RUNG_SCHEMA
    assert ccr.read_published(_FakeRedis(value=json.dumps(ok))) is not None


def test_read_published_refuses_a_census_missing_one_rung():
    """UNKNOWN never becomes zero: a cache short of a rung is not a total."""
    import json

    counts = {key: 1 for key in RUNG_KEYS}
    counts.pop(PLOTTED_RUNG)
    blob = json.dumps(
        {
            "schema": ccr.COVERAGE_RUNG_SCHEMA,
            "population_version": "q271",
            "roster_digest": "digest-A",
            "counts": counts,
        }
    )
    assert ccr.read_published(_FakeRedis(value=blob)) is None


def test_read_published_refuses_a_census_with_no_roster_stamp():
    """Without the roster digest the reconciliation below cannot be performed,
    so the census is unusable however complete its counts look."""
    import json

    blob = json.dumps(
        {
            "schema": ccr.COVERAGE_RUNG_SCHEMA,
            "population_version": "q271",
            "counts": {key: 1 for key in RUNG_KEYS},
        }
    )
    assert ccr.read_published(_FakeRedis(value=blob)) is None


def test_publish_then_read_round_trips_the_counts_and_the_stamp():
    redis = _FakeRedis()
    state = _complete_state()
    assert ccr.publish(redis, state) is True
    out = ccr.read_published(redis)
    assert out is not None
    assert out["roster_digest"] == "digest-A"
    assert out["population_version"] == "q271"
    assert out["counts"] == ccr.rung_counts_for_bridge(state)


# ---------------------------------------------------------------------------
# 4. Never join today's coverage to yesterday's curve
# ---------------------------------------------------------------------------


def _published(digest="digest-A", version="q271"):
    return {
        "population_version": version,
        "roster_digest": digest,
        "counts": {key: 1 for key in RUNG_KEYS},
    }


def _reconcile(**over):
    kwargs = {
        "cursor_population_version": "q271",
        "cursor_roster_digest": "digest-A",
        "cursor_generation": 1789391804016,
        "payload_population_version": "q271",
        "payload_generation": 1789391804016,
    }
    kwargs.update(over)
    published = kwargs.pop("published", _published())
    return ccr.reconcile(published, **kwargs)


def test_the_happy_path_attaches_the_counts():
    counts, reason = _reconcile()
    assert reason is None
    assert counts == {key: 1 for key in RUNG_KEYS}


def test_no_published_census_is_named_as_such():
    counts, reason = _reconcile(published=None)
    assert counts is None
    assert reason == ccr.REASON_NO_CENSUS


def test_a_census_from_an_older_roster_is_refused():
    """The link this whole design exists to protect."""
    counts, reason = _reconcile(published=_published(digest="digest-OLD"))
    assert counts is None
    assert reason == ccr.REASON_CENSUS_STALE_ROSTER


def test_a_stale_payload_gets_no_census_even_when_the_census_is_current():
    """A last-good / durable / stale copy carries an older generation. Attaching
    the current census to it would describe one world with another's numbers —
    and this refusal is automatic rather than remembered at each serving tier."""
    counts, reason = _reconcile(payload_generation=1789391000000)
    assert counts is None
    assert reason == ccr.REASON_PAYLOAD_NOT_CURRENT


def test_a_payload_with_no_generation_gets_no_census():
    counts, reason = _reconcile(payload_generation=None)
    assert counts is None
    assert reason == ccr.REASON_PAYLOAD_NOT_CURRENT


def test_a_cursor_with_no_generation_cannot_vouch_for_a_payload():
    counts, reason = _reconcile(cursor_generation=None)
    assert counts is None
    assert reason == ccr.REASON_PAYLOAD_NOT_CURRENT


@pytest.mark.parametrize(
    "over",
    [
        {"payload_population_version": "q272"},
        {"cursor_population_version": "q272"},
        {"published": _published(version="q270")},
        {"payload_population_version": None},
    ],
)
def test_any_population_version_disagreement_is_refused(over):
    counts, reason = _reconcile(**over)
    assert counts is None
    assert reason == ccr.REASON_VERSION_MISMATCH


def test_an_empty_cursor_digest_cannot_vouch_for_a_census():
    counts, reason = _reconcile(cursor_roster_digest="")
    assert counts is None
    assert reason == ccr.REASON_CENSUS_STALE_ROSTER


def test_every_refusal_reason_is_a_distinct_token():
    """A reader must be able to tell the four refusals apart; collapsing any two
    would hide which link of the chain broke."""
    reasons = {
        ccr.REASON_NO_CENSUS,
        ccr.REASON_CENSUS_STALE_ROSTER,
        ccr.REASON_PAYLOAD_NOT_CURRENT,
        ccr.REASON_VERSION_MISMATCH,
    }
    assert len(reasons) == 4


def test_the_reconciled_counts_feed_the_frozen_bridge_contract():
    """End to end on the contract: a reconciled walk produces a COMPLETE census
    through the same ``build_coverage_census`` the payload already uses."""
    from app.utils.calibration_coverage_bridge import build_coverage_census, census_is_complete

    state = _complete_state()
    counts = ccr.rung_counts_for_bridge(state)
    plotted = counts[PLOTTED_RUNG]
    census = build_coverage_census(
        rung_counts=counts,
        sportsbook_curve_legs=500,
        published_curve_observations=plotted + 500,
        published_outcomes_crosscheck=plotted,
        population_version="q271",
        generation="1789391804016",
    )
    assert census_is_complete(census)
    assert census["units"]["outcomes_with_calibration_coverage"]["value"] == sum(counts.values())


# ---------------------------------------------------------------------------
# The partition the walk cuts is the curve's own
# ---------------------------------------------------------------------------


def test_plan_from_roster_matches_the_curves_own_partition_and_digest():
    """A boundary that disagrees with the curve's is additive over the wrong sets."""
    from types import SimpleNamespace

    from app.utils.calibration_staged_futures import generation_fingerprint, plan_units

    roster = [
        SimpleNamespace(market_id=i, source="kalshi", vm_id=f"g:{i % 7}", is_grouped=False)
        for i in range(1, 40)
    ]
    chunks, assignment, digest = ccr.plan_from_roster(roster, buckets=8)

    assert [c.key for c in chunks] == [c.key for c in plan_units(roster, buckets=8)]
    assert digest == generation_fingerprint(roster)
    assert assignment[3] == ("g:3", False)


class _FakeResult:
    def __init__(self, rows=None, mapping=None):
        self._rows = rows or []
        self._mapping = mapping

    def all(self):
        return self._rows

    def mappings(self):
        return self

    def first(self):
        return self._mapping


class _FakeSession:
    """Answers the three statements the walk issues, and records the order.

    Recognises them by shape rather than by call index, so a reordering of the
    walk does not silently make the fixture answer the wrong question.
    """

    def __init__(self, roster, unit_row, global_row, fail_on_unit=None):
        self.roster = roster
        self.unit_row = unit_row
        self.global_row = global_row
        self.fail_on_unit = fail_on_unit
        self.unit_calls = 0
        self.global_calls = 0
        self.timeouts = []

    async def execute(self, statement, params=None):
        sql = str(statement)
        if sql.startswith("SET LOCAL statement_timeout"):
            self.timeouts.append(sql)
            return _FakeResult()
        # Matched on each statement's own TERMINAL select, not on a CTE name:
        # all three name ``virtual_market`` in their population chain, so a
        # loose match answers the global rung with the roster's rows.
        if "SELECT market_id, source, vm_id, is_grouped" in sql:
            return _FakeResult(rows=self.roster)
        if "SELECT * FROM coverage_bridge_summary" in sql:
            self.unit_calls += 1
            if self.fail_on_unit == self.unit_calls:
                raise RuntimeError("statement timeout")
            return _FakeResult(mapping=dict(self.unit_row))
        if "FROM coverage_universe cu" in sql and "WHERE mi.market_id IS NULL" in sql:
            self.global_calls += 1
            return _FakeResult(mapping=dict(self.global_row))
        raise AssertionError(f"unexpected statement: {sql[:120]}")


def _roster(n=16):
    from types import SimpleNamespace

    return [
        SimpleNamespace(
            market_id=i, source="kalshi", vm_id=f"g:{i}", is_grouped=False
        )
        for i in range(1, n + 1)
    ]


def _unit_row():
    counts = {key: 0 for key in RUNG_KEYS}
    counts[PLOTTED_RUNG] = 10
    counts["phantom_liquidity"] = 2
    row = {ccr.coverage_bridge_column(k): v for k, v in counts.items()}
    row[ccr.TOTAL_COLUMN] = 12
    row[ccr.TERMINAL_PRICE_COLUMN] = 3
    return row


def _global_row():
    return {
        ccr.coverage_bridge_column("market_result_unavailable"): 5,
        ccr.TOTAL_COLUMN: 5,
        ccr.TERMINAL_PRICE_COLUMN: 0,
    }


async def test_a_bounded_walk_stops_at_its_unit_budget_and_banks_progress():
    roster = _roster(16)
    session = _FakeSession(roster, _unit_row(), _global_row())
    redis = _FakeRedis()

    report = await ccr.run_bounded_walk(session, redis, buckets=8, max_units=3)

    assert report["units_counted_this_call"] and len(report["units_counted_this_call"]) == 3
    assert report["complete"] is False
    assert report["published"] is False
    assert report["counts"] is None, "a partial walk reports no numbers"
    assert session.global_calls == 0, "the global rung waits for every chunk"
    # Progress is banked under the WORKING key, never the published one.
    assert redis.written is not None and redis.written[0] == ccr.WORKING_KEY


async def test_successive_calls_resume_and_finally_publish():
    roster = _roster(16)
    session = _FakeSession(roster, _unit_row(), _global_row())
    redis = _FakeRedis()

    reports = []
    for _ in range(6):
        reports.append(await ccr.run_bounded_walk(session, redis, buckets=8, max_units=3))
        if reports[-1]["complete"]:
            break

    final = reports[-1]
    assert final["complete"] is True
    assert final["published"] is True
    assert final["restart_reason"] is None, "each call resumed rather than restarting"
    assert session.global_calls == 1, "the global rung is counted exactly once"
    # Every chunk counted exactly once across the whole resumed walk.
    assert session.unit_calls == final["units_total"]
    counted = [k for r in reports for k in r["units_counted_this_call"]]
    assert len(counted) == len(set(counted)) == final["units_total"]


async def test_a_completed_walk_publishes_counts_that_reconcile():
    roster = _roster(8)
    session = _FakeSession(roster, _unit_row(), _global_row())
    redis = _FakeRedis()

    report = await ccr.run_bounded_walk(session, redis, buckets=4, max_units=100)

    assert report["complete"] and report["published"]
    counts = report["counts"]
    units = report["units_total"]
    assert counts[PLOTTED_RUNG] == 10 * units
    assert counts["phantom_liquidity"] == 2 * units
    assert counts["market_result_unavailable"] == 5
    assert sum(counts.values()) == 12 * units + 5

    # The published copy is readable and stamped with the roster it walked.
    published = ccr.read_published(redis)
    assert published["counts"] == counts
    assert published["roster_digest"] == report["roster_digest"]


async def test_a_roster_that_moves_mid_walk_discards_the_partial_counts():
    """The banked counts describe a population that no longer exists."""
    session = _FakeSession(_roster(16), _unit_row(), _global_row())
    redis = _FakeRedis()
    first = await ccr.run_bounded_walk(session, redis, buckets=8, max_units=2)
    assert first["units_done"] == 2

    moved = _FakeSession(_roster(20), _unit_row(), _global_row())
    second = await ccr.run_bounded_walk(moved, redis, buckets=8, max_units=2)

    assert second["restart_reason"] == ccr.REASON_ROSTER_MOVED
    assert second["roster_digest"] != first["roster_digest"]
    assert second["units_done"] == 2, "counted afresh, not added to the old total"


async def test_the_walk_never_touches_the_published_key_until_it_is_complete():
    session = _FakeSession(_roster(16), _unit_row(), _global_row())

    class _Guard(_FakeRedis):
        def setex(self, key, ttl, value):
            assert key != ccr.PUBLISHED_KEY, "a partial walk published a total"
            return super().setex(key, ttl, value)

    await ccr.run_bounded_walk(session, _Guard(), buckets=8, max_units=2)


async def test_a_failing_unit_leaves_the_earlier_units_banked():
    """The walk is resumable precisely so a slow or failing unit costs one unit."""
    session = _FakeSession(_roster(16), _unit_row(), _global_row(), fail_on_unit=3)
    redis = _FakeRedis()

    with pytest.raises(RuntimeError, match="statement timeout"):
        await ccr.run_bounded_walk(session, redis, buckets=8, max_units=5)

    # Nothing was banked by the raising call, so the next call redoes those
    # units — correct, because a unit is banked only after its row is in hand.
    session2 = _FakeSession(_roster(16), _unit_row(), _global_row())
    report = await ccr.run_bounded_walk(session2, redis, buckets=8, max_units=100)
    assert report["complete"] and report["published"]
    assert report["counts"][PLOTTED_RUNG] == 10 * report["units_total"]


async def test_a_complete_walk_whose_publish_fails_is_banked_and_retried():
    """A transient write failure must not cost 128 units of work.

    The retry also proves the resumed state is not re-counted: the global rung
    is counted once across both calls, not once per call.
    """

    class _PublishFails(_FakeRedis):
        def __init__(self):
            super().__init__()
            self.allow_publish = False

        def setex(self, key, ttl, value):
            if key == ccr.PUBLISHED_KEY and not self.allow_publish:
                raise RuntimeError("redis down")
            return super().setex(key, ttl, value)

    redis = _PublishFails()
    session = _FakeSession(_roster(8), _unit_row(), _global_row())
    first = await ccr.run_bounded_walk(session, redis, buckets=4, max_units=100)
    assert first["complete"] is True and first["published"] is False
    assert redis.written[0] == ccr.WORKING_KEY, "the finished walk was banked"

    redis.allow_publish = True
    retry = await ccr.run_bounded_walk(session, redis, buckets=4, max_units=100)
    assert retry["published"] is True
    assert retry["restart_reason"] is None
    assert retry["units_counted_this_call"] == [], "nothing was re-counted"
    assert session.global_calls == 1, "the global rung was not counted twice"
    assert retry["counts"] == first["counts"]


async def test_an_empty_population_publishes_nothing_and_says_so():
    session = _FakeSession([], _unit_row(), _global_row())
    report = await ccr.run_bounded_walk(session, _FakeRedis(), buckets=8)
    assert report["empty_population"] is True
    assert report["published"] is False
    assert report["complete"] is False


async def test_the_walk_runs_with_no_redis_at_all():
    """No cache is a degraded mode, not a crash: the counting still happens and
    the report still says what it found."""
    session = _FakeSession(_roster(8), _unit_row(), _global_row())
    report = await ccr.run_bounded_walk(session, None, buckets=4, max_units=100)
    assert report["complete"] is True
    assert report["published"] is False
    assert report["counts"] is not None


async def test_every_statement_is_bounded_by_its_own_timeout():
    session = _FakeSession(_roster(8), _unit_row(), _global_row())
    await ccr.run_bounded_walk(session, _FakeRedis(), buckets=4, max_units=100)
    assert any(ccr.DEFAULT_UNIT_TIMEOUT in t for t in session.timeouts)
    assert any(ccr.DEFAULT_GLOBAL_TIMEOUT in t for t in session.timeouts)


async def test_the_walk_uses_the_curves_partition_size_by_default():
    from app.tasks.calibration_main_build import STAGED_FUTURES_BUCKETS

    session = _FakeSession(_roster(4), _unit_row(), _global_row())
    report = await ccr.run_bounded_walk(session, _FakeRedis(), max_units=0)
    assert report["buckets"] == STAGED_FUTURES_BUCKETS


def test_the_repairs_map_points_at_this_module_with_the_dispatchers_signature():
    """The dispatcher calls ``fn(session, apply, **bounds)`` and filters the
    bounds by signature. A census whose second positional is not ``apply``
    would silently receive ``apply`` as something else."""
    import inspect

    from app.routes.admin_repairs import _REPAIRS

    module_path, fn_name = _REPAIRS["coverage-rung-census"]
    assert (module_path, fn_name) == ("app.tasks.census_coverage_rungs", "census")

    params = list(inspect.signature(ccr.census).parameters)
    assert params[:2] == ["session", "apply"]
    assert "limit" in params


async def test_the_admin_entry_point_ignores_apply_and_never_writes_data():
    """``apply`` is accepted and ignored, like every census sibling in the map."""
    session = _FakeSession(_roster(8), _unit_row(), _global_row())
    redis = _FakeRedis()

    with patch("app.tasks.redis_state.get_redis_client", return_value=redis):
        dry = await ccr.census(session, apply=False, limit=100)
        wet_session = _FakeSession(_roster(8), _unit_row(), _global_row())
        wet = await ccr.census(wet_session, apply=True, limit=100)

    assert dry["counts"] == wet["counts"], "apply=true did something different"


async def test_the_admin_entry_point_passes_limit_through_as_the_chunk_budget():
    session = _FakeSession(_roster(16), _unit_row(), _global_row())
    with patch("app.tasks.redis_state.get_redis_client", return_value=_FakeRedis()):
        report = await ccr.census(session, limit=2)
    assert len(report["units_counted_this_call"]) == 2
    assert report["complete"] is False


def test_plan_from_roster_reads_driver_rows_as_well_as_objects():
    """The roster arrives as SQLAlchemy Rows in production and as plain objects
    in tests; both must yield the same assignment."""

    class _Row:
        def __init__(self, **kw):
            self._mapping = kw

    roster = [_Row(market_id=5, source="kalshi", vm_id="g:1", is_grouped=True)]
    _chunks, assignment, _digest = ccr.plan_from_roster(roster, buckets=4)
    assert assignment[5] == ("g:1", True)
