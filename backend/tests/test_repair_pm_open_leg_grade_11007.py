"""#11007, the stored rows: the pure decisions and the rail wiring of
``repair_pm_open_leg_grade_11007``. The SQL is graded on a real Postgres in
``tests/integration/test_repair_pm_open_leg_grade_11007_pg.py``.

PILLAR: TRUTH. SHIP: the Fed rate-cut page stops calling the still-undecided
October and December 2026 meetings Lost or the whole question Settled, while its
genuinely decided legs keep their results.

The venue is its own bytes: Gamma ``GET /events/106884``
(``tests/fixtures/polymarket_resolved_zero_legs_5343/gamma-event-106884.json``,
2026-10-12T00:49:13Z, sha256 ``5ce0eea1…c224``). Every negative is that body
with one field changed. The stored rows have production's shape, read
2026-10-13 and recorded on #11007: parent 113883 and its eight decomposed legs
``status='resolved'`` with ``resolution_date 2026-06-17``; every parent outcome
``api_settlement``; October ``is_winner=false`` at 0.0095 and December at 0.023.
The legs' own ``_yes`` / ``_no`` outcome rows are the poll writer's shape; their
grades were not part of that read, so both an ungraded and a graded version are
exercised.
"""

import copy
import hashlib
import inspect
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

import app.tasks.repair_pm_open_leg_grade_11007 as rr
from app.routes.admin_repairs import _REPAIRS

FIXTURE = (Path(__file__).resolve().parent / "fixtures"
           / "polymarket_resolved_zero_legs_5343" / "gamma-event-106884.json")
SPECIMEN_BYTES = FIXTURE.read_bytes()
SPECIMEN = json.loads(SPECIMEN_BYTES)

UTC = timezone.utc
#: The day the rail was built. Fixed, so no assertion branches on the clock.
NOW = datetime(2026, 10, 13, 17, 0, tzinfo=UTC)
STALE = datetime(2026, 6, 17, tzinfo=UTC)
BULK_WRITE = datetime(2026, 7, 21, 20, 15, 2, tzinfo=UTC)

PARENT_ID = 113883
LEG_BY_TITLE = {m["groupItemTitle"]: m for m in SPECIMEN["markets"]}
STORED_TITLES = [
    "January Meeting", "March Meeting", "April Meeting", "June Meeting",
    "July Meeting", "September 2026 Meeting",
    "October 2026 Meeting", "December 2026 Meeting",
]
OCT = LEG_BY_TITLE["October 2026 Meeting"]["conditionId"]
DEC = LEG_BY_TITLE["December 2026 Meeting"]["conditionId"]
OPEN = {OCT, DEC}
CHILD_ID = {LEG_BY_TITLE[t]["conditionId"]: 13792800 + i
            for i, t in enumerate(STORED_TITLES)}
#: Parent outcome ids, one per stored leg.
PARENT_OUTCOME = {LEG_BY_TITLE[t]["conditionId"]: 2054100 + i
                  for i, t in enumerate(STORED_TITLES)}
QUOTE = {OCT: 0.0095, DEC: 0.023}


def _parent(**kw):
    m = {"id": PARENT_ID, "source": "polymarket", "external_id": "106884",
         "group_id": "polymarket:106884", "status": "resolved",
         "settled_at": BULK_WRITE, "resolution_date": STALE, "row_version": "900"}
    m.update(kw)
    return m


def _members(**override):
    out = []
    for cid, mid in CHILD_ID.items():
        m = {"id": mid, "source": "polymarket", "external_id": cid,
             "group_id": "polymarket:106884", "status": "resolved",
             "settled_at": BULK_WRITE, "resolution_date": STALE,
             "row_version": str(mid)}
        m.update(override.get(cid, {}))
        out.append(m)
    return out


def _outcomes(child_grades=None):
    """Parent outcomes as production holds them; leg outcomes ungraded unless
    ``child_grades`` names ``{external_id: (is_winner, source)}``."""
    rows = []
    for cid, oid in PARENT_OUTCOME.items():
        rows.append({"id": oid, "market_id": PARENT_ID, "external_id": cid,
                     "name": cid[:8], "is_winner": False,
                     "resolution_source": "api_settlement", "row_version": str(oid)})
    child_grades = child_grades or {}
    for cid, mid in CHILD_ID.items():
        for i, side in enumerate(("yes", "no")):
            ext = f"{cid}_{side}"
            won, src = child_grades.get(ext, (False, None))
            rows.append({"id": mid * 10 + i, "market_id": mid, "external_id": ext,
                         "name": side.title(), "is_winner": won,
                         "resolution_source": src, "row_version": str(mid * 10 + i)})
    return rows


def _event(mutate=None):
    ev = copy.deepcopy(SPECIMEN)
    if mutate:
        mutate(ev)
    return ev


def _leg(ev, cid):
    return next(m for m in ev["markets"] if m["conditionId"] == cid)


def _plan(parent=None, members=None, outcomes=None, event="specimen"):
    return rr.plan_parent(
        _parent() if parent is None else parent,
        _members() if members is None else members,
        _outcomes() if outcomes is None else outcomes,
        _event() if event == "specimen" else event,
        NOW,
    )


class TestTheFixtureIsTheVenue:
    def test_the_bytes_are_the_ones_read(self):
        assert hashlib.sha256(SPECIMEN_BYTES).hexdigest() == (
            "5ce0eea19067bd1691544f8d650a501bb3a3ef3b31fd2c8f630267883068c224")

    def test_october_and_december_are_open_and_the_other_six_closed(self):
        assert SPECIMEN["closed"] is False and SPECIMEN["active"] is True
        for cid in CHILD_ID:
            assert _leg(SPECIMEN, cid)["closed"] is (cid not in OPEN)


class TestTheSpecimenPlan:
    def test_it_plans_only_the_open_legs_and_the_parent(self):
        p = _plan()
        assert p["action"] == "repair", p
        assert set(p["open_condition_ids"]) == {OCT.lower(), DEC.lower()}
        assert {w["outcome_id"] for w in p["outcome_writes"]} == {
            PARENT_OUTCOME[OCT], PARENT_OUTCOME[DEC]}
        assert {w["market_id"] for w in p["market_writes"]} == {
            PARENT_ID, CHILD_ID[OCT], CHILD_ID[DEC]}

    def test_the_parent_opens_with_the_venue_end_date(self):
        w = next(w for w in _plan()["market_writes"] if w["market_id"] == PARENT_ID)
        assert (w["status"], w["resolution_date"]) == ("resolved", STALE.isoformat())
        assert w["wrote"] == {"status": "open", "settled_at": None,
                              "resolution_date": "2028-01-29T04:59:00+00:00"}

    def test_each_open_leg_takes_its_own_venue_end_date(self):
        for cid in OPEN:
            w = next(w for w in _plan()["market_writes"] if w["market_id"] == CHILD_ID[cid])
            assert w["wrote"] == {"status": "open", "settled_at": None,
                                  "resolution_date": "2027-01-29T04:59:00+00:00"}

    def test_the_six_closed_legs_are_controls_whatever_they_hold(self):
        p = _plan()
        controls = {c["outcome_id"] for c in p["controls"]}
        closed = set(CHILD_ID) - OPEN
        assert {PARENT_OUTCOME[c] for c in closed} <= controls
        written = ({w["outcome_id"] for w in p["outcome_writes"]}
                   | {w["market_id"] for w in p["market_writes"]})
        assert not ({PARENT_OUTCOME[c] for c in closed} | {CHILD_ID[c] for c in closed}) & written

    def test_graded_leg_outcomes_on_an_open_leg_are_cleared_too(self):
        closed = next(c for c in CHILD_ID if c not in OPEN)
        grades = {f"{OCT}_yes": (False, "api_settlement"),
                  f"{OCT}_no": (True, "api_settlement"),
                  f"{closed}_no": (True, "api_settlement")}
        p = _plan(outcomes=_outcomes(grades))
        ids = {w["outcome_id"] for w in p["outcome_writes"]}
        assert {CHILD_ID[OCT] * 10, CHILD_ID[OCT] * 10 + 1} <= ids
        # A closed leg's graded child outcome is a control, never written.
        assert CHILD_ID[closed] * 10 + 1 not in ids

    def test_an_ungraded_open_leg_outcome_is_left_alone(self):
        p = _plan()
        assert CHILD_ID[OCT] * 10 not in {w["outcome_id"] for w in p["outcome_writes"]}

    def test_the_outcome_write_sets_nulls_and_nothing_else(self):
        # No winner is ever written: the one outcome statement clears both
        # fields, and its SET names nothing else.
        set_clause = rr._WRITE_OUTCOME.split("SET", 1)[1].split("WHERE", 1)[0]
        assert set_clause.split() == ["is_winner", "=", "NULL,", "resolution_source",
                                      "=", "NULL"]

    def test_already_repaired_rows_have_nothing_to_repair(self):
        members = _members(**{c: {"status": "open", "settled_at": None,
                                  "resolution_date": datetime(2027, 1, 29, 4, 59, tzinfo=UTC)}
                              for c in OPEN})
        outcomes = [dict(o, is_winner=None, resolution_source=None)
                    if o["id"] in (PARENT_OUTCOME[OCT], PARENT_OUTCOME[DEC]) else o
                    for o in _outcomes()]
        parent = _parent(status="open", settled_at=None,
                         resolution_date=datetime(2028, 1, 29, 4, 59, tzinfo=UTC))
        assert _plan(parent, members, outcomes)["reason"] == "nothing_to_repair"

    def test_an_open_parent_with_a_stale_date_still_gets_the_date(self):
        # A status-only flip leaves the parent below the recovery pass's floor.
        p = _plan(parent=_parent(status="open", settled_at=None))
        w = next(w for w in p["market_writes"] if w["market_id"] == PARENT_ID)
        assert w["wrote"]["resolution_date"] == "2028-01-29T04:59:00+00:00"


def _refusal(**kw):
    p = _plan(**kw)
    assert p["action"] == "skip", p
    return p["reason"]


class TestRefusedByName:
    @pytest.mark.parametrize("parent,reason", [
        (_parent(source="kalshi"), "not_polymarket"),
        (_parent(external_id="0xabc"), "not_an_event_parent"),
        (_parent(group_id="polymarket:1"), "group_mismatch"),
        (_parent(status="suspended"), "status_unexpected"),
    ])
    def test_stored_parent_refusals(self, parent, reason):
        assert _refusal(parent=parent) == reason

    def test_a_missing_parent(self):
        assert rr.plan_parent(None, [], [], _event(), NOW)["reason"] == "market_missing"

    def test_an_unexpected_group_member(self):
        members = _members() + [{"id": 1, "source": "kalshi", "external_id": "KX",
                                 "group_id": "polymarket:106884", "status": "open"}]
        assert _refusal(members=members) == "unexpected_group_member"

    def test_a_venue_404(self):
        assert _refusal(event=None) == "venue_absent"

    @pytest.mark.parametrize("body", [[], "x", 7])
    def test_an_unparseable_body(self, body):
        assert _refusal(event=body) == "venue_unparseable"

    def test_the_venue_answering_for_another_event(self):
        assert _refusal(event=_event(lambda e: e.update(id="106885"))) == \
            "event_identity_mismatch"

    @pytest.mark.parametrize("field,value,reason", [
        ("closed", True, "event_not_open_at_venue"),
        ("active", False, "event_not_open_at_venue"),
        ("archived", True, "event_not_open_at_venue"),
        ("closed", "false", "event_flags_malformed"),
        ("closed", None, "event_flags_malformed"),
        ("endDate", None, "venue_end_date_missing"),
        ("endDate", "soon", "venue_end_date_missing"),
        ("endDate", "2026-10-01T00:00:00Z", "venue_end_date_elapsed"),
    ])
    def test_event_level_answers(self, field, value, reason):
        assert _refusal(event=_event(lambda e: e.update({field: value}))) == reason

    def test_an_absent_event_flag_is_malformed(self):
        ev = _event()
        del ev["closed"]
        assert _refusal(event=ev) == "event_flags_malformed"

    @pytest.mark.parametrize("value", ["false", None, 0, "no"])
    def test_a_malformed_leg_flag_refuses_the_parent(self, value):
        ev = _event(lambda e: _leg(e, OCT).update(closed=value))
        assert _refusal(event=ev) == "leg_flag_malformed"

    def test_an_absent_leg_flag_refuses_the_parent(self):
        # The DTO parser would default this to False (open). The rail does not.
        ev = _event(lambda e: _leg(e, OCT).pop("closed"))
        assert _refusal(event=ev) == "leg_flag_malformed"

    def test_a_stored_leg_the_venue_does_not_list(self):
        ev = _event(lambda e: e.update(markets=[m for m in e["markets"]
                                                if m["conditionId"] != DEC]))
        assert _refusal(event=ev) == "stored_leg_absent_at_venue"

    def test_a_duplicated_venue_condition_id(self):
        ev = _event(lambda e: e["markets"].append(copy.deepcopy(_leg(e, OCT))))
        assert _refusal(event=ev) == "venue_duplicate_condition_ids"

    def test_an_open_leg_already_in_uma_resolution(self):
        ev = _event(lambda e: _leg(e, OCT).update(umaResolutionStatus="proposed"))
        assert _refusal(event=ev) == "leg_resolution_in_flight"

    def test_an_open_leg_past_its_own_venue_end_date(self):
        ev = _event(lambda e: _leg(e, OCT).update(endDate="2026-10-01T00:00:00Z"))
        assert _refusal(event=ev) == "venue_leg_end_date_elapsed"

    def test_another_grading_source_on_an_open_leg(self):
        outcomes = [dict(o, resolution_source="clob_field_repair")
                    if o["id"] == PARENT_OUTCOME[OCT] else o for o in _outcomes()]
        assert _refusal(outcomes=outcomes) == "unexpected_grade_source"

    @pytest.mark.parametrize("is_winner", [True, False], ids=["won", "lost"])
    def test_a_sourceless_grade_on_a_parent_outcome(self, is_winner):
        # The parent's outcomes are the rows the page reads. With no source
        # nobody can say which writer put a grade there, so the parent refuses
        # rather than clear a grade of unknown provenance.
        outcomes = [dict(o, is_winner=is_winner, resolution_source=None)
                    if o["id"] == PARENT_OUTCOME[DEC] else o for o in _outcomes()]
        assert _refusal(outcomes=outcomes) == "sourceless_grade_on_open_leg"

    def test_a_sourceless_winner_on_a_leg_outcome(self):
        p = _plan(outcomes=_outcomes({f"{DEC}_yes": (True, None)}))
        assert p["reason"] == "sourceless_grade_on_open_leg"

    def test_a_leg_outcome_at_the_column_default_is_ungraded_and_never_written(self):
        # FALSE is futures_outcomes.is_winner's server default: every leg row
        # the poll inserts holds (False, None), and no reader prints a verdict
        # without a source (web OutcomeRow, iOS OutcomeVerdict). Refusing it
        # would refuse the specimen itself; clearing it would write a row
        # whose provenance is unknown. Neither: it is left alone.
        outcomes = _outcomes()
        leg = next(o for o in outcomes if o["id"] == CHILD_ID[DEC] * 10)
        assert (leg["is_winner"], leg["resolution_source"]) == (False, None)
        p = _plan(outcomes=outcomes)
        assert p["action"] == "repair"
        assert leg["id"] not in {w["outcome_id"] for w in p["outcome_writes"]}

    def test_only_both_null_counts_as_an_ungraded_parent_outcome(self):
        outcomes = [dict(o, is_winner=None, resolution_source=None)
                    if o["id"] == PARENT_OUTCOME[DEC] else o for o in _outcomes()]
        p = _plan(outcomes=outcomes)
        assert p["action"] == "repair"
        assert PARENT_OUTCOME[DEC] not in {w["outcome_id"] for w in p["outcome_writes"]}

    def test_an_outcome_id_the_poll_never_writes(self):
        outcomes = _outcomes() + [{"id": 1, "market_id": PARENT_ID, "external_id": "Other",
                                   "name": "Other", "is_winner": None,
                                   "resolution_source": None, "row_version": "1"}]
        assert _refusal(outcomes=outcomes) == "unexpected_parent_outcome"
        outcomes = _outcomes() + [{"id": 2, "market_id": CHILD_ID[OCT],
                                   "external_id": f"{OCT}_side1", "name": "x",
                                   "is_winner": None, "resolution_source": None,
                                   "row_version": "1"}]
        assert _refusal(outcomes=outcomes) == "unexpected_child_outcome"

    def test_a_closed_venue_never_reopens_a_market_even_with_open_legs_stored(self):
        # Closed at the venue = the settle rails' job; this rail never resolves
        # and never reopens what the venue closed.
        ev = _event(lambda e: e.update(closed=True))
        assert _refusal(event=ev) == "event_not_open_at_venue"


class TestThePlanHash:
    def _planned(self, **kw):
        p = _plan(**kw)
        return {"market_id": PARENT_ID, **p}

    def test_it_is_stable(self):
        a = rr.plan_hash_for([PARENT_ID], [self._planned()])
        assert a == rr.plan_hash_for([PARENT_ID], [self._planned()])

    def test_a_row_version_moves_it(self):
        a = rr.plan_hash_for([PARENT_ID], [self._planned()])
        b = rr.plan_hash_for([PARENT_ID], [self._planned(parent=_parent(row_version="901"))])
        assert a != b

    def test_an_outcome_row_version_moves_it(self):
        outcomes = [dict(o, row_version="x") if o["id"] == PARENT_OUTCOME[OCT] else o
                    for o in _outcomes()]
        a = rr.plan_hash_for([PARENT_ID], [self._planned()])
        assert a != rr.plan_hash_for([PARENT_ID], [self._planned(outcomes=outcomes)])

    def test_a_control_grade_moves_it(self):
        closed = next(c for c in CHILD_ID if c not in OPEN)
        outcomes = [dict(o, is_winner=True) if o["id"] == PARENT_OUTCOME[closed] else o
                    for o in _outcomes()]
        a = rr.plan_hash_for([PARENT_ID], [self._planned()])
        assert a != rr.plan_hash_for([PARENT_ID], [self._planned(outcomes=outcomes)])

    def test_a_venue_end_date_moves_it(self):
        ev = _event(lambda e: e.update(endDate="2028-02-29T04:59:00Z"))
        a = rr.plan_hash_for([PARENT_ID], [self._planned()])
        assert a != rr.plan_hash_for([PARENT_ID], [self._planned(event=ev)])

    def test_a_moving_quote_does_not(self):
        # Prices tick every second; the plan binds flags and dates, not quotes.
        ev = _event(lambda e: _leg(e, OCT).update(outcomePrices='["0.02", "0.98"]'))
        a = rr.plan_hash_for([PARENT_ID], [self._planned()])
        assert a == rr.plan_hash_for([PARENT_ID], [self._planned(event=ev)])

    def test_the_named_ids_move_it(self):
        a = rr.plan_hash_for([PARENT_ID], [self._planned()])
        assert a != rr.plan_hash_for([PARENT_ID, 1], [self._planned()])


class TestIds:
    def test_exact_ids(self):
        assert rr.parse_only_ids(None) is None
        assert rr.parse_only_ids("113883, 113883") == [113883]
        for bad in ("", "x", "1,,2", ",".join(str(i) for i in range(rr.APPLY_PARENT_CAP + 1))):
            with pytest.raises(ValueError):
                rr.parse_only_ids(bad)


class TestTheRestoreState:
    @pytest.mark.parametrize("rows,state", [
        ([{"still_written": True, "at_prior": False}] * 3, "written"),
        ([{"still_written": False, "at_prior": True}] * 3, "restored"),
        ([{"still_written": True, "at_prior": False},
          {"still_written": False, "at_prior": False}], "moved"),
        ([{"still_written": True, "at_prior": False},
          {"still_written": False, "at_prior": True}], "moved"),
        ([], "moved"),
    ])
    def test_a_parent_restores_only_whole(self, rows, state):
        assert rr.group_state(rows) == state


class TestWiring:
    def test_both_names_are_registered(self):
        assert _REPAIRS["pm-open-leg-false-grade"] == (
            "app.tasks.repair_pm_open_leg_grade_11007", "repair")
        assert _REPAIRS["pm-open-leg-false-grade-restore"] == (
            "app.tasks.repair_pm_open_leg_grade_11007", "restore")

    def test_dry_run_is_the_default(self):
        for fn in (rr.repair, rr.restore):
            assert inspect.signature(fn).parameters["apply"].default is False

    def test_never_on_a_beat(self):
        import app.tasks as tasks_pkg
        src = Path(tasks_pkg.__file__).read_text()
        assert "repair_pm_open_leg_grade_11007" not in src

    def test_every_write_repeats_its_row_version(self):
        # The version must be a bare conjunct of a WHERE with no OR in it: a
        # substring check passes ``(xmin::text = :ver OR true)``. Under the
        # FOR UPDATE lock no real writer can reach that gap, which is why no
        # Postgres case can see it; this is the only test that can.
        for sql, conjunct in ((rr._WRITE_MARKET, "xmin::text = :ver"),
                              (rr._WRITE_OUTCOME, "xmin::text = :ver"),
                              (rr._RESTORE_MARKETS, "fm.xmin::text = b.wrote_row_version"),
                              (rr._RESTORE_OUTCOMES, "fo.xmin::text = b.wrote_row_version")):
            where = " ".join(sql.split("WHERE", 1)[1].split())
            assert " or " not in f" {where.lower()} " and "(" not in where.replace("CAST(", "")
            assert conjunct in [c.strip() for c in where.split(" AND ")]

    def test_the_only_cleared_source_is_the_grader_that_wrote_it(self):
        assert rr.CLEARABLE_SOURCE == "api_settlement"
        assert "resolution_source = :clearable" in rr._WRITE_OUTCOME
