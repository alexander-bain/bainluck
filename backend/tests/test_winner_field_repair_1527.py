"""CAL-P007 (#1527): the attended repair of the three-winner cohort.

Approved by Alex 2026-08-07 under attended capped-batch discipline. CAL-P006
stopped the producers; this writes the fix for what they already made.

The authority is per-LEG, which is what makes writing permissible at all under
gotcha #21 (never bulk-reset ``is_winner`` without a source that can immediately
re-resolve). Verified live against the CLOB on market 55254886::

    Will Slavia Praha beat Anderlecht?    Yes=False
    Will Anderlecht beat Slavia Praha?    Yes=True     <- the actual winner
    Will the match ... end in a draw?     Yes=False

Our DB crowned all three. There is no mapping step here that can be wrong: each
leg IS a condition_id, so the id is the identity.

Everything below is about the ways this must REFUSE to write. A repair that
guesses is worse than the corruption it replaces, because it launders a guess as
tier-3 authority.
"""

import inspect

import pytest

import app.tasks.repair_winner_field as repair_mod
from app.routes.admin_repairs import _REPAIRS
from app.tasks.repair_winner_field import (
    APPLY_MARKET_CAP,
    IMPOSSIBLE_PRICE,
    WRITE_SOURCE,
    _is_condition_id,
    decide_market,
    foreign_authority,
    yes_winner,
)
from app.utils.resolution_authority import (
    AUTHORITATIVE_SOURCES,
    is_calibration_truth_eligible,
)


def _leg(name, win, oid=None):
    return {"outcome_id": oid or abs(hash(name)) % 100000, "name": name,
            "yes_winner": win}


# ---------------------------------------------------------------------------
# Reading CLOB settlement
# ---------------------------------------------------------------------------
class TestYesWinner:
    def test_the_real_winning_leg(self):
        assert yes_winner(
            {"tokens": [{"outcome": "Yes", "winner": True},
                        {"outcome": "No", "winner": False}]}
        ) is True

    def test_the_real_losing_leg(self):
        assert yes_winner(
            {"tokens": [{"outcome": "Yes", "winner": False},
                        {"outcome": "No", "winner": True}]}
        ) is False

    def test_undecided_is_none_not_false(self):
        # The single most dangerous confusion in this module: an unresolved
        # market must never read as "this leg lost".
        assert yes_winner(
            {"tokens": [{"outcome": "Yes", "winner": None},
                        {"outcome": "No", "winner": None}]}
        ) is None

    def test_missing_market_and_missing_tokens_are_none(self):
        assert yes_winner(None) is None
        assert yes_winner({}) is None
        assert yes_winner({"tokens": []}) is None

    def test_no_yes_token_is_none(self):
        assert yes_winner({"tokens": [{"outcome": "Up", "winner": True}]}) is None

    def test_outcome_label_matching_is_forgiving_of_case_and_space(self):
        assert yes_winner({"tokens": [{"outcome": " yes ", "winner": True}]}) is True


# ---------------------------------------------------------------------------
# The decision — every branch must fail closed
# ---------------------------------------------------------------------------
class TestDecideMarket:
    def test_the_production_case_repairs_to_one_winner(self):
        d = decide_market([
            _leg("Slavia Praha", False, 205060693),
            _leg("Anderlecht", True, 205060694),
            _leg("Draw", False, 205060695),
        ])
        assert d["action"] == "repair"
        assert d["winner_outcome_id"] == 205060694
        assert d["winner_name"] == "Anderlecht"

    def test_one_unresolved_leg_blocks_the_whole_market(self):
        # Partial knowledge must not produce a partial write: if we cannot see
        # every leg, we cannot know there is exactly one winner.
        d = decide_market([
            _leg("Slavia Praha", False),
            _leg("Anderlecht", True),
            _leg("Draw", None),
        ])
        assert d["action"] == "skip"
        assert d["reason"] == "unresolved_legs"
        assert "Draw" in d["detail"]

    def test_void_fixture_is_skipped_never_forced(self):
        d = decide_market([_leg("A", False), _leg("B", False), _leg("Draw", False)])
        assert d == {"action": "skip", "reason": "no_winner_void"}

    def test_contradictory_upstream_is_refused_not_arbitrated(self):
        # If CLOB itself says two legs won, we do not get to pick one.
        d = decide_market([_leg("A", True), _leg("B", True), _leg("Draw", False)])
        assert d["action"] == "skip"
        assert d["reason"] == "multiple_clob_winners"

    def test_empty_leg_list_is_void_not_a_crash(self):
        assert decide_market([])["action"] == "skip"

    @pytest.mark.parametrize("wins", [0, 2, 3])
    def test_only_exactly_one_winner_ever_writes(self, wins):
        legs = [_leg(f"L{i}", i < wins) for i in range(3)]
        d = decide_market(legs)
        assert d["action"] == ("repair" if wins == 1 else "skip")


# ---------------------------------------------------------------------------
# Never overwrite a stronger source
# ---------------------------------------------------------------------------
class TestForeignAuthority:
    def test_api_settlement_blocks_the_repair(self):
        rows = [{"resolution_source": "api_settlement"},
                {"resolution_source": "clean_resolution"}]
        assert foreign_authority(rows) == ["api_settlement"]

    def test_our_own_source_is_not_foreign(self):
        # Idempotence: re-running over our own writes must not self-block.
        assert foreign_authority([{"resolution_source": WRITE_SOURCE}]) == []

    def test_the_corrupt_cohorts_own_source_does_not_block(self):
        # clean_resolution is tier-1 price-derived — exactly what we are here to
        # replace. If it blocked, the repair could never run at all.
        assert foreign_authority([{"resolution_source": "clean_resolution"},
                                  {"resolution_source": None}]) == []


# ---------------------------------------------------------------------------
# Routing ids to an endpoint that can accept them
# ---------------------------------------------------------------------------
class TestConditionIdGuard:
    def test_condition_ids_are_accepted(self):
        assert _is_condition_id(
            "0x982b3670c7db5d579917370017832d682a48142ff9fa71d905c30dc3c80ce889"
        )

    @pytest.mark.parametrize("bad", [None, "", "15366", "kalshi-ticker"])
    def test_non_condition_ids_are_rejected(self, bad):
        # CAL-P003's find: a 0x id sent to a numeric-id endpoint 422s, and that
        # was misread as a rate limit for months. Route by shape, up front.
        assert not _is_condition_id(bad)


# ---------------------------------------------------------------------------
# Authority registration and the cap
# ---------------------------------------------------------------------------
class TestWriteAuthorityAndCap:
    def test_source_is_registered_tier3_and_curve_eligible(self):
        # CAL-P003's lesson: sources FAIL CLOSED. An unregistered name would
        # grade the cohort and still never reach the curve — the fix would look
        # done and move nothing.
        assert WRITE_SOURCE in AUTHORITATIVE_SOURCES
        assert is_calibration_truth_eligible(WRITE_SOURCE)

    def test_source_is_distinct_so_the_cohort_is_revertible(self):
        for sibling in ("clob_authoritative", "clob_never_graded", "clob_ordinal"):
            assert WRITE_SOURCE != sibling

    def test_cap_is_a_constant_not_a_parameter(self):
        # "Capped" must not be dialled off mid-run, so the cap is deliberately
        # NOT reachable from the query string.
        assert isinstance(APPLY_MARKET_CAP, int) and 0 < APPLY_MARKET_CAP <= 200
        params = inspect.signature(repair_mod.repair).parameters
        assert "cap" not in params and "max_writes" not in params

    def test_dry_run_is_the_default(self):
        assert inspect.signature(repair_mod.repair).parameters["apply"].default is False

    def test_registered_on_the_repair_rail(self):
        assert _REPAIRS["winner-field-repair"] == (
            "app.tasks.repair_winner_field", "repair",
        )

    def test_signature_matches_the_rail_dispatcher(self):
        params = inspect.signature(repair_mod.repair).parameters
        for p in ("apply", "limit", "offset"):
            assert p in params


# ---------------------------------------------------------------------------
# Write shape
# ---------------------------------------------------------------------------
class TestWriteShape:
    def test_only_one_leg_can_be_crowned_by_construction(self):
        # The UPDATE sets is_winner = (id = :win_id) across the whole market, so
        # a second winner is not merely unlikely — it is unrepresentable.
        src = inspect.getsource(repair_mod)
        assert "is_winner = (id = :win_id)" in src

    def test_settlement_prices_are_written_alongside_the_winner(self):
        src = inspect.getsource(repair_mod)
        assert "current_probability = CASE WHEN id = :win_id" in src

    def test_impossible_captured_prices_are_nulled_not_invented(self):
        # CAL-P006 proved all 72 snapshots per leg were 1.0 from first ingest —
        # there was never a real price, so NULL is the honest state and any
        # "repaired" opening would be fabricated.
        src = inspect.getsource(repair_mod)
        for col in ("calibration_probability = NULL", "opening_probability = NULL",
                    "opening_captured_at = NULL", "opening_source = NULL"):
            assert col in src

    def test_only_impossible_prices_are_nulled(self):
        # A real sub-certain line on such a market must survive.
        src = inspect.getsource(repair_mod)
        assert "opening_probability >= :bar" in src
        assert IMPOSSIBLE_PRICE >= 0.99

    def test_every_write_lives_in_the_guarded_market_transaction(self):
        # The UPDATEs are module constants; only the per-market apply and the
        # restore may execute them, so no dry-run path can reach a write.
        for name in ("_WRITE_WINNER", "_NULL_OPENING", "_NULL_CP"):
            users = [fn for fn in (repair_mod.repair, repair_mod._plan_market,
                                   repair_mod._apply_market, repair_mod.restore)
                     if name in inspect.getsource(fn)]
            assert users == [repair_mod._apply_market], name
        assert "_RESTORE_MARKET" in inspect.getsource(repair_mod.restore)

    def test_the_restore_requires_the_row_version_the_write_left(self):
        # Root's hold on 9298be4a: a value-only audit cannot see a later writer
        # that left every value the same. The audit and the restore's own WHERE
        # both require the version this rail's write stamped.
        assert repair_mod._WROTE_VERSION == "fo.xmin::text = b.wrote_row_version"
        assert repair_mod._WROTE_VERSION in repair_mod._AUDIT_SQL
        assert repair_mod._WROTE_VERSION in repair_mod._RESTORE_MARKET
        assert "wrote_row_version TEXT" in repair_mod._BAK_CREATE
        assert "wrote_row_version" in repair_mod._BAK_ALTER
        # Stamped inside the market's own write transaction, after every write.
        src = inspect.getsource(repair_mod._apply_market)
        assert src.index("_BAK_VERSION") > src.index("_NULL_CP")
        assert src.index("_BAK_VERSION") < src.index("session.commit()")
        assert "wrote_row_version = NULL" in repair_mod._BAK_STAMP

    def test_scan_is_bounded_and_resumable(self):
        src = inspect.getsource(repair_mod)
        assert "SET LOCAL statement_timeout" in src
        assert "LIMIT :scan" in src
        assert "next_offset" in src

    def test_clob_errors_skip_the_market_intact(self):
        # gotcha #36: a 429 is not "no winner". The market must be retried whole,
        # not half-written.
        src = inspect.getsource(repair_mod._plan_market)
        assert '"clob_error"' in src

    def test_predicate_matches_the_census(self):
        # Repair and census must not drift on what a defect is.
        from app.tasks import census_winner_fields as census_mod
        for frag in ("COUNT(*) FILTER (WHERE o.is_winner) > 1",
                     "COUNT(*) FILTER (WHERE o.current_probability >= :bar) > 1"):
            assert frag in inspect.getsource(repair_mod)
            assert frag in inspect.getsource(census_mod)


# ---------------------------------------------------------------------------
# The guarded apply (#1527 production-apply HOLD, 2026-10-13). The SQL, locks
# and transactions are proven against real PostgreSQL in
# tests/integration/test_repair_winner_field_guarded_apply_1527_pg.py; these
# pin the pure decisions it rests on.
# ---------------------------------------------------------------------------
from app.tasks.repair_winner_field import (  # noqa: E402
    authority_refusal,
    cohort_refusal,
    leg_image,
    parse_only_ids,
    plan_hash_for,
    planned_writes,
    venue_answer,
)


def _market(**kw):
    return {"id": 55254886, "source": "polymarket", "llm_sport_category": "soccer",
            "market_type": "field", "mutually_exclusive": True, **kw}


def _row(oid, name, won=True, cp=1.0, op=1.0, cal=1.0, src="clean_resolution",
         ext=None):
    return {"id": oid, "name": name, "is_winner": won, "current_probability": cp,
            "opening_probability": op, "calibration_probability": cal,
            "resolution_source": src, "external_id": ext or f"0x{oid:064x}",
            "opening_american_odds": None, "opening_captured_at": None,
            "opening_source": None}


SPECIMEN = [_row(205060693, "Slavia Praha"), _row(205060694, "Anderlecht"),
            _row(205060695, "Draw")]


class TestCohort:
    def test_the_specimen_is_in_the_cohort(self):
        assert cohort_refusal(_market(), SPECIMEN) is None

    @pytest.mark.parametrize("market,reason", [
        (_market(llm_sport_category="golf"), "not_soccer"),
        (_market(llm_sport_category="football"), "not_soccer"),
        (_market(llm_sport_category=None), "not_soccer"),
        (_market(source="kalshi"), "not_polymarket"),
        (_market(market_type="binary"), "not_field_or_duel"),
        (_market(mutually_exclusive=False), "not_mutually_exclusive"),
        (None, "market_missing"),
    ])
    def test_every_other_cohort_is_refused_by_name(self, market, reason):
        assert cohort_refusal(market, SPECIMEN) == reason

    def test_a_football_tie_leg_does_not_make_football_soccer(self):
        legs = [_row(1, "Chiefs"), _row(2, "Bills"), _row(3, "Tie (Draw)")]
        assert cohort_refusal(_market(llm_sport_category="football"), legs) == "not_soccer"

    def test_two_legs_and_four_legs_are_not_three_way(self):
        assert cohort_refusal(_market(), SPECIMEN[:2]) == "not_three_way"
        assert cohort_refusal(_market(), SPECIMEN + [_row(9, "Other")]) == "not_three_way"

    def test_a_three_leg_field_needs_exactly_one_draw(self):
        top_scorer = [_row(1, "Haaland"), _row(2, "Kane"), _row(3, "Mbappe")]
        assert cohort_refusal(_market(), top_scorer) == "not_one_draw_leg"
        two_draws = [_row(1, "Draw"), _row(2, "Draw no bet"), _row(3, "Home")]
        assert cohort_refusal(_market(), two_draws) == "not_one_draw_leg"

    def test_a_coherent_field_is_not_a_candidate(self):
        legs = [_row(1, "Home", True, 1.0), _row(2, "Away", False, 0.0),
                _row(3, "Draw", False, 0.0)]
        assert cohort_refusal(_market(), legs) == "coherent"
        ours = [{**leg, "resolution_source": WRITE_SOURCE} for leg in legs]
        assert cohort_refusal(_market(), ours) == "already_repaired"


class TestAuthorityRefusal:
    def test_the_corrupt_cohort_passes(self):
        assert authority_refusal(SPECIMEN) is None

    def test_an_unknown_source_is_refused(self):
        legs = [_row(1, "Home", src="mystery_grader"), *SPECIMEN[1:]]
        assert authority_refusal(legs) == ("unknown_authority", ["mystery_grader"])

    def test_a_foreign_tier3_source_is_refused(self):
        legs = [_row(1, "Home", src="api_settlement"), *SPECIMEN[1:]]
        assert authority_refusal(legs) == ("foreign_authority", ["api_settlement"])

    def test_shared_condition_ids_are_refused(self):
        legs = [_row(1, "Home", ext="0xabc"), _row(2, "Away", ext="0xABC"),
                _row(3, "Draw", ext="0xdef")]
        assert authority_refusal(legs) == ("duplicate_condition_ids", [])

    def test_a_numeric_id_is_not_clob_addressable(self):
        legs = [_row(1, "Home", ext="15366"), *SPECIMEN[1:]]
        assert authority_refusal(legs) == ("not_clob_addressable", [])


class TestVenueAnswer:
    def test_an_answer_about_another_condition_is_no_answer(self):
        body = {"condition_id": "0xother",
                "tokens": [{"outcome": "Yes", "winner": True}]}
        assert venue_answer("0xasked", body) is None
        assert venue_answer("0xOTHER", body) is True


class TestPlannedWrites:
    def test_opening_and_calibration_are_decided_separately(self):
        legs = [_row(1, "Home", op=0.41, cal=1.0), _row(2, "Away", op=None, cal=None),
                _row(3, "Draw", op=1.0, cal=0.62)]
        writes = {w["outcome_id"]: w for w in planned_writes(legs, 3)}
        assert (writes[1]["null_opening"], writes[1]["null_cp"]) == (False, True)
        assert (writes[2]["null_opening"], writes[2]["null_cp"]) == (False, False)
        assert (writes[3]["null_opening"], writes[3]["null_cp"]) == (True, False)
        assert [w["is_winner"] for w in writes.values()] == [False, False, True]
        assert [w["current_probability"] for w in writes.values()] == [0.0, 0.0, 1.0]


def _planned(legs=SPECIMEN, venue=(False, True, False), win=205060694):
    return [{
        "market": {"market_id": 55254886, "source": "polymarket",
                   "llm_sport_category": "soccer", "market_type": "field",
                   "mutually_exclusive": True},
        "legs": [leg_image(r) for r in legs],
        "venue": [{"outcome_id": r["id"], "condition_id": r["external_id"],
                   "yes_winner": v} for r, v in zip(legs, venue)],
        "winner_outcome_id": win,
        "writes": planned_writes(legs, win),
        "row_versions": {r["id"]: "100" for r in legs},
    }]


class TestPlanHash:
    BASE = plan_hash_for([55254886], _planned())

    @pytest.mark.parametrize("field,value", [
        ("is_winner", False), ("current_probability", 0.0),
        ("resolution_source", "api_settlement"), ("opening_probability", 0.5),
        ("calibration_probability", None), ("external_id", "0xdifferent"),
        ("name", "Draw (renamed)"), ("opening_source", "first_snapshot"),
    ])
    def test_every_stored_value_is_in_the_address(self, field, value):
        legs = [{**SPECIMEN[0], field: value}, *SPECIMEN[1:]]
        assert plan_hash_for([55254886], _planned(legs)) != self.BASE

    def test_the_venue_verdict_and_the_named_ids_are_in_the_address(self):
        assert plan_hash_for([55254886], _planned(
            venue=(True, False, False), win=205060693)) != self.BASE
        assert plan_hash_for([55254886, 1], _planned()) != self.BASE

    def test_a_row_version_is_in_the_address(self):
        # Root's hold on 9298be4a: a same-value write between the dry run and
        # the apply moves only the row version. If the version were outside the
        # address, the reviewed hash would authorize a row nobody reviewed.
        for oid in _planned()[0]["row_versions"]:
            moved = _planned()
            moved[0]["row_versions"] = {**moved[0]["row_versions"], oid: "999"}
            assert plan_hash_for([55254886], moved) != self.BASE, oid

    def test_a_touch_stamp_alone_is_not(self):
        # Nothing can move last_updated without moving xmin, which is in the
        # address; the stamp itself would only add a second spelling of it.
        moved = _planned()
        moved[0]["prior_last_updated"] = {205060693: "2026-10-13T00:00:00"}
        assert plan_hash_for([55254886], moved) == self.BASE

    def test_numeric_spelling_does_not_move_the_address(self):
        from decimal import Decimal
        legs = [{**r, "current_probability": Decimal("1.000000")} for r in SPECIMEN]
        assert plan_hash_for([55254886], _planned(legs)) == self.BASE


class TestExactIdGate:
    @pytest.mark.parametrize("bad", ["", " ", "1,,2", "a,b", "55254886;1"])
    def test_malformed_lists_raise(self, bad):
        with pytest.raises(ValueError):
            parse_only_ids(bad)

    def test_over_the_cap_raises_and_the_cap_passes(self):
        parse_only_ids(",".join(str(i) for i in range(1, APPLY_MARKET_CAP + 1)))
        with pytest.raises(ValueError):
            parse_only_ids(",".join(str(i) for i in range(1, APPLY_MARKET_CAP + 2)))

    def test_parsed_ids_are_sorted_and_unique(self):
        assert parse_only_ids("3, 1,3") == [1, 3]

    class _NoSession:
        def __getattr__(self, name):
            raise AssertionError(f"session.{name} used before the gate refused")

    @pytest.mark.parametrize("kw,terminal", [
        ({}, "refused_no_exact_ids"),
        ({"plan_hash": "0" * 32}, "refused_no_exact_ids"),
        ({"only_ids": "55254886"}, "refused_no_plan_hash"),
        ({"only_ids": "", "plan_hash": "0" * 32}, "refused_bad_only_ids"),
    ])
    async def test_apply_is_refused_before_any_read(self, kw, terminal):
        out = await repair_mod.repair(self._NoSession(), apply=True, **kw)
        assert out["terminal"] == terminal and out["repaired"] == 0

    def test_the_rail_declares_the_exact_plan_params(self):
        params = inspect.signature(repair_mod.repair).parameters
        assert "only_ids" in params and "plan_hash" in params

    def test_the_restore_is_registered_and_dry_run_by_default(self):
        assert _REPAIRS["winner-field-repair-restore"] == (
            "app.tasks.repair_winner_field", "restore",
        )
        assert inspect.signature(repair_mod.restore).parameters["apply"].default is False
