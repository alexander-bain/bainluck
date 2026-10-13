"""#1527, the status half: the pure decisions and the rail wiring of
``repair_settled_status_1527``. The SQL is graded on a real Postgres in
``tests/integration/test_repair_settled_status_1527_pg.py``.

PILLAR: TRUTH. SHIP: after a soccer fixture is settled, its market no longer
appears live while its one real winner remains visible.
"""

import inspect
import json

import pytest

import app.tasks.repair_settled_status_1527 as rs
from app.routes.admin_repairs import _REPAIRS
from app.utils.resolved_write_gate import ALLOWED_REASONS, classify_resolved_write


def _market(**kw):
    m = {"id": 55254886, "source": "polymarket", "llm_sport_category": "soccer",
         "market_type": "field", "mutually_exclusive": True, "status": "open",
         "settled_at": None, "market_metadata": None, "row_version": "100"}
    m.update(kw)
    return m


def _legs(winners=(False, True, False), probs=(0.0, 1.0, 0.0),
          sources=("clob_field_repair",) * 3, names=("Slavia Praha", "Anderlecht", "Draw")):
    return [{"id": 205060693 + i, "name": n, "external_id": f"0x{205060693 + i:064x}",
             "is_winner": w, "current_probability": p, "resolution_source": s,
             "row_version": str(200 + i)}
            for i, (n, w, p, s) in enumerate(zip(names, winners, probs, sources))]


def _venue(closed=(True, True, True), won=(False, True, False)):
    return [{"outcome_id": 205060693 + i, "condition_id": f"0x{205060693 + i:064x}",
             "closed": c, "yes_winner": w} for i, (c, w) in enumerate(zip(closed, won))]


class TestCohort:
    def test_the_specimen_after_the_outcome_rail_is_in_scope(self):
        assert rs.status_cohort_refusal(_market(), _legs()) is None

    @pytest.mark.parametrize("market,reason", [
        (None, "market_missing"),
        (_market(source="kalshi"), "not_polymarket"),
        (_market(llm_sport_category="golf"), "not_soccer"),
        (_market(market_type="claim"), "not_field_or_duel"),
        (_market(mutually_exclusive=False), "not_mutually_exclusive"),
        (_market(market_metadata=["x"]), "metadata_not_an_object"),
        (_market(market_metadata='"text"'), "metadata_not_an_object"),
        (_market(status="resolved"), "already_settled"),
        (_market(status="withdrawn"), "not_open"),
    ])
    def test_market_refusals(self, market, reason):
        assert rs.status_cohort_refusal(market, _legs()) == reason

    @pytest.mark.parametrize("meta", [None, "null", '{"a": 1}', {"a": 1}])
    def test_both_nulls_and_an_object_are_mergeable(self, meta):
        assert rs.status_cohort_refusal(_market(market_metadata=meta), _legs()) is None

    @pytest.mark.parametrize("legs,reason", [
        (_legs()[:2], "not_three_way"),
        (_legs(names=("Home", "Away", "Tie")), "not_one_draw_leg"),
        (_legs(winners=(True, True, True), probs=(1.0, 1.0, 1.0)), "field_incoherent"),
        (_legs(winners=(False, False, False), probs=(1.0, 1.0, 0.0)), "field_incoherent"),
        (_legs(winners=(None, True, None)), "field_ungraded"),
        (_legs(winners=(False, False, False)), "field_ungraded"),
        (_legs(probs=(0.06, 1.0, 0.0)), "field_prices_unsettled"),
        (_legs(probs=(0.0, 0.94, 0.0)), "field_prices_unsettled"),
        (_legs(probs=(None, 1.0, 0.0)), "field_prices_unsettled"),
        (_legs(probs=(0.0, None, 0.0)), "field_prices_unsettled"),
    ])
    def test_field_refusals(self, legs, reason):
        assert rs.status_cohort_refusal(_market(), legs) == reason

    @pytest.mark.parametrize("probs", [(0.003, 1.0, 0.003), (0.05, 0.95, 0.0),
                                       (0.0, 0.997, 0.0)])
    def test_a_settled_field_the_poll_re_priced_is_still_settled(self, probs):
        # The poll re-prices a settled loser to the venue's last trade (0.003 in
        # the re-ingest gate). The grade says who won; the bands keep it coherent.
        assert rs.status_cohort_refusal(_market(), _legs(probs=probs)) is None

    def test_the_bands_are_the_coherence_bar_and_its_complement(self):
        assert rs.SETTLED_LOSER_MAX == 0.05

    def test_unknown_authority_and_venue_identity(self):
        unknown = _legs(sources=("mystery_grader", "api_settlement", "api_settlement"))
        assert rs.leg_authority_refusal(unknown)[0] == "unknown_authority"
        bare = _legs()
        bare[0]["external_id"] = "12345"
        assert rs.leg_authority_refusal(bare)[0] == "not_clob_addressable"
        dup = _legs()
        dup[2]["external_id"] = "0x" + dup[1]["external_id"][2:].upper()
        assert rs.leg_authority_refusal(dup)[0] == "duplicate_condition_ids"
        assert rs.leg_authority_refusal(_legs()) is None

    def test_a_sourceless_loss_is_unknown_authority(self):
        # `is_winner` defaults to false: a false with no source may be a leg
        # nobody graded (CAL-P1004R), so it is never settlement evidence.
        legs = _legs(sources=("clob_field_repair", "clob_field_repair", None))
        assert rs.leg_authority_refusal(legs) == ("unknown_authority", [None])


class TestVenue:
    def test_a_closed_answer_for_the_asked_id(self):
        cid = "0xabc"
        body = {"condition_id": cid, "closed": True,
                "tokens": [{"outcome": "Yes", "winner": True}]}
        assert rs.venue_leg(cid, body) == {"condition_id": cid, "closed": True,
                                           "yes_winner": True}

    def test_a_body_naming_another_id_is_no_testimony(self):
        body = {"condition_id": "0xother", "closed": True,
                "tokens": [{"outcome": "Yes", "winner": True}]}
        assert rs.venue_leg("0xabc", body) == {"condition_id": "0xabc", "closed": None,
                                               "yes_winner": None}

    @pytest.mark.parametrize("closed", [None, "true", 1])
    def test_closed_must_be_the_boolean_true(self, closed):
        body = {"condition_id": "0xabc", "closed": closed,
                "tokens": [{"outcome": "Yes", "winner": True}]}
        assert rs.venue_leg("0xabc", body)["closed"] is None

    def test_a_missing_market_reads_unknown(self):
        assert rs.venue_leg("0xabc", None) == {"condition_id": "0xabc", "closed": None,
                                               "yes_winner": None}

    @pytest.mark.parametrize("venue,reason", [
        (_venue(closed=(True, False, True)), "venue_not_closed"),
        (_venue(closed=(True, None, True)), "venue_not_closed"),
        (_venue(won=(False, None, False)), "unresolved_legs"),
        (_venue(won=(False, False, False)), "no_winner_void"),
        (_venue(won=(True, True, False)), "multiple_clob_winners"),
        (_venue(won=(True, False, False)), "venue_disagrees_with_stored_winner"),
    ])
    def test_every_venue_refusal(self, venue, reason):
        assert rs.decide_status(_legs(), venue)["reason"] == reason

    def test_settle_only_on_a_closed_agreeing_winner(self):
        assert rs.decide_status(_legs(), _venue()) == {
            "action": "settle", "winner_outcome_id": 205060694, "winner_name": "Anderlecht"}


class TestPlanAddress:
    def _planned(self, **kw):
        p = {"market_id": 55254886, "market": rs.market_image(_market()),
             "legs": [rs.leg_image(leg) for leg in _legs()], "venue": _venue(),
             "winner_outcome_id": 205060694, "market_row_version": "100",
             "leg_row_versions": {str(leg["id"]): leg["row_version"] for leg in _legs()}}
        p.update(kw)
        return p

    def test_stable(self):
        assert rs.plan_hash_for([55254886], [self._planned()]) == rs.plan_hash_for(
            [55254886], [self._planned()])

    @pytest.mark.parametrize("change", [
        {"market_row_version": "101"},
        {"leg_row_versions": {"205060693": "999", "205060694": "201", "205060695": "202"}},
        {"winner_outcome_id": 205060695},
        {"venue": _venue(won=(False, False, True))},
        {"market": rs.market_image(_market(settled_at="2025-01-01T00:00:00+00:00"))},
        {"market": rs.market_image(_market(market_metadata={"k": 1}))},
    ], ids=["market-version", "leg-version", "winner", "venue", "settled_at", "metadata"])
    def test_every_bound_input_moves_the_address(self, change):
        assert rs.plan_hash_for([55254886], [self._planned()]) != rs.plan_hash_for(
            [55254886], [self._planned(**change)])

    def test_the_named_ids_are_in_the_address(self):
        assert rs.plan_hash_for([55254886], []) != rs.plan_hash_for([55254886, 1], [])

    def test_json_null_and_sql_null_metadata_address_alike(self):
        assert rs.market_image(_market(market_metadata=None)) == rs.market_image(
            _market(market_metadata="null"))


class TestTheWrite:
    def test_the_stamp_is_a_permitted_winner_proof(self):
        stamp = json.loads(rs.write_stamp("abc"))["resolution_gate"]
        assert stamp["proof_kind"] == "winner" and stamp["task"] == rs.TASK
        assert stamp["plan_hash"] == "abc"
        assert classify_resolved_write(has_winner_proof=True).permitted
        assert "reason" not in stamp and not (set(stamp.values()) & ALLOWED_REASONS)

    def test_resolved_is_the_repository_settled_status(self):
        assert rs.SETTLED_STATUS == "resolved" and rs.OPEN_STATUS == "open"

    def test_the_update_repeats_its_preconditions(self):
        sql = " ".join(rs._WRITE_STATUS.split())
        assert "WHERE id = :mid AND status = :open AND xmin::text = :ver" in sql
        assert "jsonb_typeof(market_metadata) = 'null'" in sql
        assert "settled_at = COALESCE(settled_at, NOW())" in sql
        assert "futures_outcomes" not in rs._WRITE_STATUS

    def test_the_restore_requires_the_version_its_write_left(self):
        assert "fm.xmin::text = b.wrote_row_version" in rs._RESTORE_MARKET
        assert "fm.xmin::text = b.wrote_row_version" in rs._AUDIT_SQL

    def test_the_market_row_is_locked_for_update_and_the_legs_for_share(self):
        assert rs._MARKET_LOCK_SQL.rstrip().endswith("FOR UPDATE")
        assert rs._LEGS_LOCK_SQL.rstrip().endswith("FOR SHARE")


class TestRail:
    def test_registered_on_the_repair_rail(self):
        assert _REPAIRS["settled-status-repair"] == (
            "app.tasks.repair_settled_status_1527", "repair")
        assert _REPAIRS["settled-status-repair-restore"] == (
            "app.tasks.repair_settled_status_1527", "restore")

    def test_dry_run_by_default_and_only_dispatcher_params(self):
        params = inspect.signature(rs.repair).parameters
        assert list(params) == ["session", "apply", "only_ids", "plan_hash"]
        assert params["apply"].default is False
        restore = inspect.signature(rs.restore).parameters
        assert list(restore) == ["session", "apply", "plan_hash"]
        assert restore["apply"].default is False

    def test_never_wired_to_a_beat(self):
        from app.tasks import celery_app

        tasks = {str(v.get("task")) for v in (celery_app.conf.beat_schedule or {}).values()}
        assert not any("settled_status" in t for t in tasks)

    @pytest.mark.asyncio
    async def test_no_exact_ids_refuses_before_any_read(self):
        class NoSession:
            async def execute(self, *a, **k):
                raise AssertionError("read before the exact-id gate")

        assert (await rs.repair(NoSession()))["terminal"] == "refused_no_exact_ids"
        assert (await rs.repair(NoSession(), apply=True, only_ids="55254886"))[
            "terminal"] == "refused_no_plan_hash"
