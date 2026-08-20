"""CAL-P076 / #2007 — the served payload dates its own inputs.

The defect, measured on production 2026-08-19T23:17Z: ``/api/calibration``
answered ``availability: fresh``, ``producer.beats_missed: 0``,
``producer.stalled: false``, ``generated_at`` two minutes old — over a futures
bank whose durable row had not been written since **17:16:31Z**, with
``staged:units_this_beat: 0`` and ``staged:units_drifted: 115`` of 127
checkable. Publishing is not freshness.

What this file pins, and why each one is here rather than being obvious:

* **The block exists on every answer** — it is stamped in ``_serve``, the ONE
  exit, so no tier can forget it. Asserted through the route, at three tiers.
* **``fresh`` is refused while drift is undisclosed.** That is ruling (b),
  literally. An unreadable disclosure is undisclosed drift, so it refuses too —
  the reassuring reading is never the default (gotcha #53).
* **A zero drift figure only counts when every banked unit was checkable.**
  CAL-P069's find: 6 units outside the counter's reach published as
  ``units_drifted: 0``.
* **``units_drifted`` is as-of ``staged_at``, not as-of the publish.** The ledger
  re-records it hourly but reads it off the frozen cursor, so a frozen bank
  freezes its own drift counter. The field says so.
* **The downgrade clears itself when the ruled fix lands.** A beat that
  re-stages drifted units sets ``units_this_beat > 0`` and ``fresh`` renders
  again — pinned, because a rule that can never be satisfied is a rule nobody
  will keep.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.availability_envelope import (
    AVAILABILITY_FRESH,
    AVAILABILITY_STALE,
)
from app.utils.calibration_staged_disclosure import (
    GAUGE_UNITS_BANKED,
    GAUGE_UNITS_DRIFT_CHECKABLE,
    GAUGE_UNITS_DRIFT_UNCHECKABLE,
    GAUGE_UNITS_DRIFTED,
    GAUGE_UNITS_THIS_BEAT,
    STAGED_FIELD,
    availability_floor,
    build_disclosure,
    unmeasured,
)

# The production reading this queue was written from, kept as a named fixture so
# the numbers in the docstring above are the numbers under test.
PROD_STAGES = {
    GAUGE_UNITS_BANKED: 128,
    GAUGE_UNITS_THIS_BEAT: 0,
    GAUGE_UNITS_DRIFTED: 115,
    GAUGE_UNITS_DRIFT_CHECKABLE: 127,
    GAUGE_UNITS_DRIFT_UNCHECKABLE: 1,
}
PROD_STAGED_AT = datetime(2026, 8, 19, 17, 16, 31, tzinfo=timezone.utc)
PROD_PUBLISHED_AT = datetime(2026, 8, 19, 23, 17, 13, tzinfo=timezone.utc)


class TestTheProductionReading:
    def test_the_frozen_bank_is_named_frozen(self):
        d = build_disclosure(
            ledger_stages=PROD_STAGES,
            staged_generated_at=PROD_STAGED_AT,
            now=PROD_PUBLISHED_AT,
        )
        assert d["measured"] is True
        assert d["frozen_over_drift"] is True
        assert d["units_drifted"] == 115
        assert d["units_banked"] == 128
        assert d["bank_advanced_this_beat"] is False

    def test_staged_at_is_the_bank_not_the_publish(self):
        """The whole point. Six hours separate them and only one was published."""
        d = build_disclosure(
            ledger_stages=PROD_STAGES,
            staged_generated_at=PROD_STAGED_AT,
            now=PROD_PUBLISHED_AT,
        )
        assert d["staged_at"] == PROD_STAGED_AT.isoformat()
        assert d["staged_age_s"] == pytest.approx(21642, abs=2)
        assert d["staged_age_s"] > 6 * 3600 - 120

    def test_drift_is_dated_to_the_bank_not_to_the_beat_that_reported_it(self):
        """``roster_drift_units`` is read off the cursor, so it ages with it.

        The ledger re-records this gauge every beat, which makes it LOOK like an
        hourly measurement. It is not: it is last hour's reading of a number the
        frozen cursor stopped updating. Real drift is ``>=`` what is published,
        and a consumer can only know that if the field is dated.
        """
        d = build_disclosure(
            ledger_stages=PROD_STAGES,
            staged_generated_at=PROD_STAGED_AT,
            now=PROD_PUBLISHED_AT,
        )
        assert d["units_drifted_as_of"] == d["staged_at"]
        assert d["units_drifted_as_of"] != PROD_PUBLISHED_AT.isoformat()

    def test_this_reading_refuses_fresh(self):
        d = build_disclosure(
            ledger_stages=PROD_STAGES,
            staged_generated_at=PROD_STAGED_AT,
            now=PROD_PUBLISHED_AT,
        )
        assert availability_floor(d) == AVAILABILITY_STALE


class TestTheRuleClearsItself:
    def test_a_beat_that_restages_drifted_units_renders_fresh_again(self):
        """Ruling (b)'s mechanism half, pinned as satisfiable.

        A rule that no achievable state can clear is a rule that gets deleted
        rather than met. Once the bounded incremental re-stage lands, a beat with
        drift re-stages some of it and the page is fresh again — with the drift
        still disclosed, because disclosure is not conditional on the verdict.
        """
        stages = {**PROD_STAGES, GAUGE_UNITS_THIS_BEAT: 9}
        d = build_disclosure(
            ledger_stages=stages, staged_generated_at=PROD_STAGED_AT, now=PROD_PUBLISHED_AT
        )
        assert d["bank_advanced_this_beat"] is True
        assert d["frozen_over_drift"] is False
        assert availability_floor(d) is None
        assert d["units_drifted"] == 115

    def test_a_quiet_population_with_full_coverage_is_fresh(self):
        stages = {
            GAUGE_UNITS_BANKED: 128,
            GAUGE_UNITS_THIS_BEAT: 0,
            GAUGE_UNITS_DRIFTED: 0,
            GAUGE_UNITS_DRIFT_CHECKABLE: 128,
            GAUGE_UNITS_DRIFT_UNCHECKABLE: 0,
        }
        d = build_disclosure(ledger_stages=stages, staged_generated_at=PROD_STAGED_AT)
        assert d["frozen_over_drift"] is False
        assert availability_floor(d) is None


class TestUnknownIsNotZero:
    def test_zero_drift_over_partial_coverage_is_not_a_clean_bill(self):
        """CAL-P069, exactly: 6 banked units outside the counter's reach
        published as ``units_drifted: 0``. A zero over an incomplete denominator
        is not a measured zero."""
        stages = {
            GAUGE_UNITS_BANKED: 119,
            GAUGE_UNITS_THIS_BEAT: 0,
            GAUGE_UNITS_DRIFTED: 0,
            GAUGE_UNITS_DRIFT_CHECKABLE: 113,
            GAUGE_UNITS_DRIFT_UNCHECKABLE: 6,
        }
        d = build_disclosure(ledger_stages=stages, staged_generated_at=PROD_STAGED_AT)
        assert d["units_drift_unknown"] == 6
        assert d["frozen_over_drift"] is True
        assert availability_floor(d) == AVAILABILITY_STALE

    def test_the_larger_of_the_two_unknown_expressions_wins(self):
        """``banked - checkable`` and the uncheckable gauge can disagree — the
        second is only written when the cursor carries a digest map at all.
        Under-reporting how much is unmeasurable manufactures a reassuring zero,
        so the larger is taken."""
        stages = {
            GAUGE_UNITS_BANKED: 128,
            GAUGE_UNITS_THIS_BEAT: 0,
            GAUGE_UNITS_DRIFTED: 0,
            GAUGE_UNITS_DRIFT_CHECKABLE: 100,
            GAUGE_UNITS_DRIFT_UNCHECKABLE: 3,
        }
        d = build_disclosure(ledger_stages=stages, staged_generated_at=PROD_STAGED_AT)
        assert d["units_drift_unknown"] == 28

    def test_an_absent_units_this_beat_is_not_read_as_advancing(self):
        """A beat that died before the recording site tells us nothing. It must
        not be read as 'the bank advanced' — the reassuring direction."""
        stages = {k: v for k, v in PROD_STAGES.items() if k != GAUGE_UNITS_THIS_BEAT}
        d = build_disclosure(ledger_stages=stages, staged_generated_at=PROD_STAGED_AT)
        assert d["bank_advanced_this_beat"] is None
        assert d["frozen_over_drift"] is True


class TestUnreadableIsRefused:
    def test_ledger_stages_of_the_wrong_shape(self):
        d = build_disclosure(ledger_stages=None, staged_generated_at=PROD_STAGED_AT)
        assert d == {"measured": False, "reason": "ledger_stages_unreadable"}
        assert availability_floor(d) == AVAILABILITY_STALE

    def test_a_convergence_reason_is_surfaced_rather_than_a_generic_absence(self):
        """CAL-P028's distinction: 'nothing banked' and 'the reader broke' must
        not collapse into one absence."""
        d = build_disclosure(
            ledger_stages={"staged:convergence_reason:read_raised": 1},
            staged_generated_at=PROD_STAGED_AT,
        )
        assert d["measured"] is False
        assert d["reason"] == "staged:convergence_reason:read_raised"

    def test_units_banked_absent_with_no_reason_says_so(self):
        d = build_disclosure(ledger_stages={}, staged_generated_at=PROD_STAGED_AT)
        assert d["reason"] == "units_banked_absent"

    def test_a_bank_with_no_timestamp_cannot_date_anything(self):
        d = build_disclosure(ledger_stages=PROD_STAGES, staged_generated_at=None)
        assert d["reason"] == "staged_at_absent"
        assert availability_floor(d) == AVAILABILITY_STALE

    def test_unmeasured_is_never_an_empty_or_zeroed_block(self):
        d = unmeasured("whatever")
        assert d["measured"] is False
        assert "units_drifted" not in d
        assert availability_floor(d) == AVAILABILITY_STALE

    def test_a_non_mapping_disclosure_refuses_fresh(self):
        assert availability_floor(None) == AVAILABILITY_STALE
        assert availability_floor("fine") == AVAILABILITY_STALE


class TestGaugeParsing:
    def test_a_jsonb_round_tripped_string_parses(self):
        stages = {**PROD_STAGES, GAUGE_UNITS_BANKED: "128", GAUGE_UNITS_DRIFTED: "115"}
        d = build_disclosure(ledger_stages=stages, staged_generated_at=PROD_STAGED_AT)
        assert d["units_banked"] == 128
        assert d["units_drifted"] == 115

    def test_a_bool_is_not_an_int(self):
        """``bool`` subclasses ``int``; ``True`` must not rate as a banked unit."""
        stages = {**PROD_STAGES, GAUGE_UNITS_BANKED: True}
        d = build_disclosure(ledger_stages=stages, staged_generated_at=PROD_STAGED_AT)
        assert d["measured"] is False

    def test_a_naive_timestamp_is_read_as_utc_not_as_local(self):
        naive = PROD_STAGED_AT.replace(tzinfo=None)
        d = build_disclosure(
            ledger_stages=PROD_STAGES, staged_generated_at=naive, now=PROD_PUBLISHED_AT
        )
        assert d["staged_at"] == PROD_STAGED_AT.isoformat()
        assert d["staged_age_s"] == pytest.approx(21642, abs=2)


class TestFloorOnlyEverWeakens:
    def test_the_floor_is_a_clamp_not_a_verdict(self):
        """``availability_floor`` returning ``None`` is 'no opinion', never
        'this is fresh'. The caller clamps with ``never_stronger``, so a payload
        already declared ``degraded`` stays ``degraded``."""
        from app.utils.availability_envelope import AVAILABILITY_DEGRADED, never_stronger

        healthy = build_disclosure(
            ledger_stages={**PROD_STAGES, GAUGE_UNITS_THIS_BEAT: 9},
            staged_generated_at=PROD_STAGED_AT,
        )
        assert availability_floor(healthy) is None
        assert (
            never_stronger(AVAILABILITY_DEGRADED, AVAILABILITY_FRESH)
            == AVAILABILITY_DEGRADED
        )


# ---------------------------------------------------------------------------
# Through the route — the block must reach the wire on every tier
# ---------------------------------------------------------------------------


def _staged_row(*, generated_at: datetime):
    from app.utils import durable_state as ds
    from app.utils.calibration_staged_futures import STAGED_FUTURES_SCHEMA

    payload = {"schema": STAGED_FUTURES_SCHEMA, "committed_units": ["a"] * 128}
    return {
        "identity": "calibration:main:staged_futures",
        "schema_version": STAGED_FUTURES_SCHEMA,
        "generation": ds.generation_for(generated_at),
        "generated_at": generated_at,
        "payload": payload,
        "checksum": ds.checksum_payload(payload),
        "complete": True,
        "source": "precompute_calibration_main",
    }


def _ledger_row(stages: dict, *, generated_at: datetime):
    from app.utils import durable_state as ds
    from app.utils.calibration_phase_ledger import PHASE_LEDGER_SCHEMA

    payload = {"stages": dict(stages), "terminal": "complete"}
    return {
        "identity": "calibration:main:phase_ledger",
        "schema_version": PHASE_LEDGER_SCHEMA,
        "generation": ds.generation_for(generated_at),
        "generated_at": generated_at,
        "payload": payload,
        "checksum": ds.checksum_payload(payload),
        "complete": True,
        "source": "precompute_calibration_main",
    }


class _RoutingDb:
    """An ``AsyncSession`` stand-in that answers BY IDENTITY.

    The existing calibration route suites use a mock that returns one row for
    every read. That was fine while the durable tier was the only database work
    the request path did; it is not fine now that two more identities are read,
    because a single-row mock hands the staged reader some other artifact's
    envelope. Routing on the bind parameter is what makes the disclosure
    testable at all.
    """

    def __init__(self, rows: dict):
        self._rows = rows
        self.identities: list[str] = []

    async def execute(self, statement, params=None):
        from unittest.mock import MagicMock

        result = MagicMock()
        identity = (params or {}).get("identity")
        if identity is not None:
            self.identities.append(identity)
        result.mappings.return_value.first.return_value = self._rows.get(identity)
        return result


@pytest.fixture(autouse=True)
def _fresh_process():
    from app.routes import calibration
    from app.utils import request_cache as rc

    calibration._cache["data"] = None
    calibration._cache["timestamp"] = 0
    calibration._staged_cache["data"] = None
    calibration._staged_cache["timestamp"] = 0.0
    rc._reset_last_good_for_tests()
    yield
    calibration._cache["data"] = None
    calibration._cache["timestamp"] = 0
    calibration._staged_cache["data"] = None
    calibration._staged_cache["timestamp"] = 0.0
    rc._reset_last_good_for_tests()


def _fake_main_payload():
    from app.tasks.precompute_calibration import CALIBRATION_POPULATION_VERSION

    stamp = (datetime.now(timezone.utc) - timedelta(minutes=3)).isoformat()
    outcomes = 1_000_000
    return {
        "buckets": [{"bucket_idx": 0, "n": outcomes, "winners": outcomes // 2}],
        "by_category": [{"category": "politics", "outcomes": outcomes}],
        "by_source": [{"source": "kalshi", "outcomes": outcomes}],
        "total_outcomes": outcomes,
        "total_markets": outcomes // 4,
        "total_winners": outcomes // 2,
        "liquidity_filter": {"applies_to": "kalshi"},
        "mex_normalization": {"applies_to": "all"},
        "truth_evidence": {"contract_ok": True},
        "population_version": CALIBRATION_POPULATION_VERSION,
        "generated_at": stamp,
    }


def _redis(monkeypatch, main_json):
    import json as _json

    from app.utils import request_cache as rc

    class _R:
        async def get(self, key):
            if key == "bainluck:calibration:main":
                return _json.dumps(main_json) if main_json is not None else None
            return None

    async def _getter():
        return _R()

    monkeypatch.setattr(rc, "get_shared_async_redis", _getter)


async def _call(db):
    from app.routes.calibration import public_calibration

    return await public_calibration(db=db)


class TestThroughTheRoute:
    @pytest.mark.asyncio
    async def test_a_frozen_bank_takes_fresh_off_a_current_publish(self, monkeypatch):
        """The exact production shape: the Redis ``main`` key is current and
        valid, so tier 2 would have said ``fresh``. The bank is six hours old."""
        _redis(monkeypatch, _fake_main_payload())
        now = datetime.now(timezone.utc)
        db = _RoutingDb(
            {
                "calibration:main:staged_futures": _staged_row(
                    generated_at=now - timedelta(hours=6)
                ),
                "calibration:main:phase_ledger": _ledger_row(
                    PROD_STAGES, generated_at=now
                ),
            }
        )
        out = await _call(db)
        assert out[STAGED_FIELD]["measured"] is True
        assert out[STAGED_FIELD]["units_drifted"] == 115
        assert out[STAGED_FIELD]["frozen_over_drift"] is True
        assert out["availability"] == AVAILABILITY_STALE

    @pytest.mark.asyncio
    async def test_an_advancing_bank_still_publishes_the_block_and_stays_fresh(
        self, monkeypatch
    ):
        _redis(monkeypatch, _fake_main_payload())
        now = datetime.now(timezone.utc)
        db = _RoutingDb(
            {
                "calibration:main:staged_futures": _staged_row(
                    generated_at=now - timedelta(minutes=4)
                ),
                "calibration:main:phase_ledger": _ledger_row(
                    {**PROD_STAGES, GAUGE_UNITS_THIS_BEAT: 9}, generated_at=now
                ),
            }
        )
        out = await _call(db)
        assert out["availability"] == AVAILABILITY_FRESH
        assert out[STAGED_FIELD]["measured"] is True
        assert out[STAGED_FIELD]["staged_age_s"] == pytest.approx(240, abs=30)

    @pytest.mark.asyncio
    async def test_an_unreadable_bank_refuses_fresh_and_names_why(self, monkeypatch):
        """Ruling (b) literally: ``fresh`` may not render while drift is
        undisclosed. A missing durable row is undisclosed drift."""
        _redis(monkeypatch, _fake_main_payload())
        db = _RoutingDb({})
        out = await _call(db)
        assert out["availability"] == AVAILABILITY_STALE
        assert out[STAGED_FIELD]["measured"] is False
        assert "staged_cursor_unreadable" in out[STAGED_FIELD]["reason"]

    @pytest.mark.asyncio
    async def test_a_dead_connection_costs_a_word_not_the_response(self, monkeypatch):
        """The disclosure is additive. It must never be able to take the page
        down — CAL-P017 is standing and this route may not go dark.

        ``read_snapshot`` types a database failure as ``unavailable`` rather than
        raising, so this lands on the same refusal path a missing row does. The
        curve is still served, whole, 200; only the word changes.
        """
        _redis(monkeypatch, _fake_main_payload())

        class _Boom:
            async def execute(self, *a, **k):
                raise RuntimeError("connection reset")

        out = await _call(_Boom())
        assert out["total_outcomes"] == 1_000_000
        assert out["availability"] == AVAILABILITY_STALE
        assert out[STAGED_FIELD]["measured"] is False
        assert out[STAGED_FIELD]["reason"] == "staged_cursor_unreadable: unavailable"

    @pytest.mark.asyncio
    async def test_a_reader_that_raises_outright_is_caught_and_named(self, monkeypatch):
        """The outer guard, exercised rather than assumed.

        ``read_snapshot`` catches the query and nothing after it, so a corrupt
        row (here: an unparseable ``generation``) raises past its own handler.
        Q297's lesson is that this must be caught AND said — a silent ``pass``
        here is how a NameError once disabled a whole tier invisibly.
        """
        _redis(monkeypatch, _fake_main_payload())
        now = datetime.now(timezone.utc)
        row = _staged_row(generated_at=now - timedelta(hours=6))
        row["generation"] = "not-a-number"
        out = await _call(_RoutingDb({"calibration:main:staged_futures": row}))
        assert out["total_outcomes"] == 1_000_000
        assert out["availability"] == AVAILABILITY_STALE
        assert out[STAGED_FIELD]["reason"].startswith("read_raised:")

    @pytest.mark.asyncio
    async def test_the_block_is_on_the_memo_tier_too(self, monkeypatch):
        """``_serve`` is the one exit, and tier 1 answers from process memory
        with no database work — so the disclosure has to be read before the
        tiers, not inside one of them."""
        _redis(monkeypatch, _fake_main_payload())
        now = datetime.now(timezone.utc)
        rows = {
            "calibration:main:staged_futures": _staged_row(
                generated_at=now - timedelta(hours=6)
            ),
            "calibration:main:phase_ledger": _ledger_row(PROD_STAGES, generated_at=now),
        }
        first = await _call(_RoutingDb(rows))
        assert first[STAGED_FIELD]["measured"] is True

        # Second call: tier 1 hits, and the staged read is inside its own TTL.
        db2 = _RoutingDb(rows)
        second = await _call(db2)
        assert second[STAGED_FIELD] == first[STAGED_FIELD]
        assert second["availability"] == AVAILABILITY_STALE
        assert db2.identities == [], "the memoised disclosure must not re-read"
