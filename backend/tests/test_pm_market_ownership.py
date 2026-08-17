"""#1912 (CAL-P065) — exactly one rail owns every Polymarket market shape.

Two halves, and the second is the one that matters.

The first half is the registry: totality, single ownership, and the orphan
check. Those are properties of a pure module and are tested as such.

The second half is a BEHAVIORAL SPECIMEN — a real never-graded market driven
end-to-end through the LIVE ``clob_resolve_drain``, asserting on the UPDATE it
actually issues. C-PMW-1's census is the reason it is written this way.
``tests/test_clob_never_graded_cohort.py`` is thirteen tests of
``inspect.getsource`` and ``inspect.signature``; the whole family runs to 42.
Those tests assert that certain STRINGS appear in certain functions, so they
survive any change that keeps the strings and breaks the behaviour, and they
fail on any change that keeps the behaviour and moves the strings. One of them
— ``test_never_graded_cohort_has_no_write_path_yet`` — spent this entire period
asserting, correctly and uselessly, that the hole was open.

So the acceptance here is a market going in and a graded row coming out. The
only fakes are the two real boundaries: the CLOB HTTP call and the asyncpg
driver. The mapper, the integrity guard, the cohort predicate, the tally, the
write decision, the bound parameters and the terminal are all the shipping
code, reached by calling the shipping function.
"""

from __future__ import annotations

import pytest

from app.tasks import clob_resolve
from app.tasks.clob_resolve import (
    _COHORT_DROPPED,
    _COHORT_NEVER_GRADED,
    _DEFAULT_WRITE_TIERS,
    _WRITE_SOURCE,
    _WRITE_SOURCE_NEVER_GRADED,
)
from app.utils.pm_market_ownership import (
    ACCOUNTED_SHAPES,
    OWNER_BY_SHAPE,
    RAIL_CLOB,
    RAIL_GAMMA,
    RAILS,
    SHAPE_CONDITION_ID,
    SHAPE_GAMMA_EVENT,
    SHAPE_GAMMA_MARKET,
    SHAPE_UNRECOGNISED,
    SHAPES,
    Handoff,
    clob_terminal,
    gamma_terminal,
    handoff_payload,
    market_shape,
    orphaned_shapes,
    owner_of,
    owner_of_shape,
    owns,
)

# ---------------------------------------------------------------------------
# The registry
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "external_id,poly_event_id,expected",
    [
        ("0xabc123", None, SHAPE_CONDITION_ID),
        ("0XABC123", None, SHAPE_CONDITION_ID),   # case is not a shape
        ("  0xabc  ", None, SHAPE_CONDITION_ID),  # nor is whitespace
        ("512345", None, SHAPE_GAMMA_MARKET),
        ("will-x-happen", None, SHAPE_GAMMA_MARKET),
        # The event id WINS over a condition-shaped external_id: that is how
        # the Gamma rail actually routes, and reversing it would re-create the
        # hole facing the other way.
        ("0xabc123", "ev-99", SHAPE_GAMMA_EVENT),
        (None, None, SHAPE_UNRECOGNISED),
        ("", None, SHAPE_UNRECOGNISED),
        ("   ", None, SHAPE_UNRECOGNISED),
        (12345, None, SHAPE_UNRECOGNISED),  # a non-str id is not a gamma id
    ],
)
def test_market_shape_is_total(external_id, poly_event_id, expected):
    assert market_shape(external_id, poly_event_id) == expected


def test_every_shape_the_classifier_can_produce_is_declared():
    """A shape missing from SHAPES is a shape no totality test iterates."""
    produced = {
        market_shape(*args)
        for args in [("0x1", None), ("9", None), ("0x1", "e"), (None, None)]
    }
    assert produced <= set(SHAPES)


def test_exactly_one_owner_per_shape_and_no_shape_is_unassigned_by_accident():
    """The invariant in one assertion. ``unrecognised`` is the ONLY ownerless
    shape, and it is ownerless deliberately — a row we cannot identify has no
    grader, and inventing one is how a discard becomes invisible."""
    owned = {s for s in SHAPES if owner_of_shape(s) is not None}
    assert owned == set(SHAPES) - {SHAPE_UNRECOGNISED}
    assert owner_of_shape(SHAPE_UNRECOGNISED) is None
    assert set(OWNER_BY_SHAPE.values()) <= set(RAILS)


def test_condition_ids_are_owned_by_the_clob_rail_and_gamma_ids_by_gamma():
    assert owner_of("0xdeadbeef") == RAIL_CLOB
    assert owner_of("512345") == RAIL_GAMMA
    assert owner_of("0xdeadbeef", "ev-1") == RAIL_GAMMA
    assert owns(RAIL_CLOB, "0xdeadbeef")
    assert not owns(RAIL_GAMMA, "0xdeadbeef")


def test_no_shape_is_orphaned():
    """THE #1912 GUARD.

    A shape is orphaned when it has a declared owner that does not account for
    it — which is precisely what "counted here, owned there" meant when the
    CLOB rail reported nothing about the condition_id population. This
    assertion fails on master before CAL-P065 (``('condition_id',)``) and is
    the structural statement that the hole is closed.
    """
    assert orphaned_shapes() == ()


def test_every_rail_accounts_only_for_shapes_it_actually_owns():
    """The other direction (gotcha #43): a rail must not claim a shape that is
    someone else's, or two rails both believe they have it covered."""
    for rail, shapes in ACCOUNTED_SHAPES.items():
        for shape in shapes:
            assert owner_of_shape(shape) == rail, (rail, shape)


# ---------------------------------------------------------------------------
# The handoff is a verdict
# ---------------------------------------------------------------------------


def test_a_handoff_names_its_owner_and_a_bare_count_cannot():
    payload = handoff_payload([
        Handoff(to=RAIL_CLOB, shape=SHAPE_CONDITION_ID, count=9748, reason="422"),
    ])
    assert payload["total"] == 9748
    assert payload["by_owner"] == {RAIL_CLOB: 9748}
    assert payload["orphaned"] == 0
    assert payload["items"][0]["to"] == RAIL_CLOB


def test_an_ownerless_handoff_is_reported_as_orphaned():
    payload = handoff_payload([
        Handoff(to=None, shape=SHAPE_UNRECOGNISED, count=5, reason="no id"),
    ])
    assert payload["orphaned"] == 5
    assert payload["items"][0]["orphaned"] is True


def test_gamma_run_that_gives_its_work_away_is_not_complete():
    """The measured production shape: 252 checked, 9,748 handed off, reported
    ``health: healthy`` every 6h."""
    terminal, reason = gamma_terminal(
        markets_checked=252, handed_off=9748, orphaned=0
    )
    assert terminal == "partial"
    assert "9748" in reason


def test_gamma_run_with_no_handoff_can_still_be_complete():
    """The other direction. Enrolment must not make the rail permanently red —
    a verdict that can never be green is not a verdict, it is a broken gauge."""
    terminal, _ = gamma_terminal(markets_checked=252, handed_off=0, orphaned=0)
    assert terminal == "complete"


def test_an_orphaned_handoff_is_failed_not_merely_partial():
    terminal, reason = gamma_terminal(
        markets_checked=10, handed_off=5, orphaned=5
    )
    assert terminal == "failed"
    assert "orphaned" in reason


def test_gamma_checked_zero_does_not_claim_complete():
    """Gotcha #53: "nothing to do" and "did nothing" produce the same counter
    here, and this rail has no second signal, so it must not guess the
    flattering one."""
    terminal, reason = gamma_terminal(markets_checked=0, handed_off=0, orphaned=0)
    assert terminal == "partial"
    assert reason == "checked_zero"


def test_clob_run_that_wrote_nothing_against_a_backlog_is_not_complete():
    """The measured production shape: checked 300, written 0, and 25,264
    never-graded markets sitting behind it."""
    terminal, reason = clob_terminal(
        examined=300, owned_backlog=25264, written=0, cursor_reset=False
    )
    assert terminal == "partial"
    assert "25264" in reason


def test_clob_unmeasured_backlog_is_absent_never_a_clean_zero():
    """Gotcha #54. A census that timed out must not be able to produce the one
    reading — an empty backlog — that would license ``complete``."""
    terminal, reason = clob_terminal(
        examined=300, owned_backlog=None, written=10, cursor_reset=True
    )
    assert terminal == "partial"
    assert reason == "backlog_unmeasured"


def test_clob_drained_backlog_reads_complete():
    terminal, _ = clob_terminal(
        examined=40, owned_backlog=0, written=40, cursor_reset=True
    )
    assert terminal == "complete"


def test_both_rails_are_enrolled_in_the_verdict_contract():
    """Enrolment and terminals ship together or neither works: an enrolled task
    with no terminal classifies as the non-authoritative legacy unknown, whose
    ``blocks_success`` is False."""
    from app.utils.task_verdict import ENFORCED_TASKS, verdict_for

    assert RAIL_GAMMA in ENFORCED_TASKS
    assert RAIL_CLOB in ENFORCED_TASKS

    v = verdict_for(RAIL_CLOB, {"terminal": "partial", "terminal_reason": "x"})
    assert v.authoritative and v.blocks_success and not v.is_green


def test_a_summary_with_no_terminal_would_not_have_blocked_anything():
    """Pins WHY enrolment alone was insufficient, so nobody 'simplifies' the
    terminals away later and leaves the enrolment looking like the fix."""
    from app.utils.task_verdict import verdict_for

    v = verdict_for(RAIL_CLOB, {"checked": 300, "written": 0})
    assert not v.authoritative
    assert not v.blocks_success  # green, on the exact production shape


# ---------------------------------------------------------------------------
# THE BEHAVIORAL SPECIMEN — a real market through the live grader
# ---------------------------------------------------------------------------


class _Row:
    """One row as `_load_cohort` returns it."""

    def __init__(self, id, cond_id, market_name, resolution_date=None,
                 created_at=None, event_linked=False):
        self.id = id
        self.cond_id = cond_id
        self.market_name = market_name
        self.resolution_date = resolution_date
        self.created_at = created_at
        self.event_linked = event_linked


class _Result:
    def __init__(self, rows=(), scalar=None):
        self._rows = list(rows)
        self._scalar = scalar

    def all(self):
        return self._rows

    def scalar(self):
        return self._scalar


class _RecordingSession:
    """A session that RECORDS the statements the grader issues.

    Not a mock that returns whatever the test wants — it answers the grader's
    reads with a real cohort row and its real outcomes, and keeps every write
    with its bound parameters so the assertion can be made against the actual
    UPDATE. That is the difference between this and a source-string test: the
    thing under test is what the function DID.
    """

    def __init__(self, cohort_rows, outcome_rows, backlog):
        self.cohort_rows = cohort_rows
        self.outcome_rows = outcome_rows
        self.backlog = backlog
        self.writes: list[tuple[str, dict]] = []
        self.commits = 0

    async def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        if "statement_timeout" in sql:
            return _Result()
        if "count(*)" in sql.lower() and "owned" in sql.lower():
            return _Result(scalar=self.backlog)
        if sql.upper().startswith("UPDATE"):
            self.writes.append((sql, dict(params or {})))
            return _Result()
        if "FROM futures_outcomes" in sql:
            return _Result(self.outcome_rows)
        if "FROM futures_markets" in sql:
            return _Result(self.cohort_rows)
        return _Result()

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        pass


class _Outcome:
    def __init__(self, market_id, id, name, external_id):
        self.market_id = market_id
        self.id = id
        self.name = name
        self.external_id = external_id


class _FakeCLOB:
    """The venue boundary, and nothing else."""

    def __init__(self, by_condition):
        self.by_condition = by_condition
        self.asked: list[str] = []

    async def get_clob_market_by_condition(self, cid):
        self.asked.append(cid)
        return self.by_condition.get(cid)

    async def close(self):
        pass


#: A real never-graded specimen: a binary yes/no market whose CLOB tokens name
#: the winner unambiguously, whose question matches ours, and whose stored legs
#: are the `_yes`/`_no` pair the poller writes.
SPECIMEN_CID = "0x5ce9a1c3f0d2b7a48e6f11d0c2b9a7e4f83d5c61"
SPECIMEN_NAME = "Will Carlos Alcaraz win the 2026 Cincinnati Open final?"


def _specimen_session(backlog=25264):
    row = _Row(
        id=58_700_123,
        cond_id=SPECIMEN_CID,
        market_name=SPECIMEN_NAME,
        event_linked=False,
    )
    outcomes = [
        _Outcome(row.id, 900_001, "Yes", f"{SPECIMEN_CID}_yes"),
        _Outcome(row.id, 900_002, "No", f"{SPECIMEN_CID}_no"),
    ]
    return row, _RecordingSession([row], outcomes, backlog)


def _specimen_clob(winner="Yes"):
    return _FakeCLOB({
        SPECIMEN_CID: {
            "question": SPECIMEN_NAME,
            "tokens": [
                {"token_id": "t1", "outcome": "Yes", "winner": winner == "Yes"},
                {"token_id": "t2", "outcome": "No", "winner": winner == "No"},
            ],
        }
    })


@pytest.fixture
def live_grader(monkeypatch):
    """Bind the shipping drain to a recording session and a fake venue.

    Everything else — `_load_cohort`, `_cohort_having`, `_fetch_and_map`,
    `map_clob_to_outcome`, `_name_concordance_ok`, `_tally`, the write branch —
    is reached by calling `clob_resolve_drain` for real.
    """

    def _bind(session, clob):
        class _Ctx:
            async def __aenter__(self_inner):
                return session

            async def __aexit__(self_inner, *a):
                return False

        monkeypatch.setattr(
            "app.tasks.base.get_task_session", lambda: _Ctx(), raising=False
        )
        monkeypatch.setattr(
            "app.services.polymarket_api.PolymarketAPIService",
            lambda *a, **k: clob,
            raising=False,
        )

        class _Redis:
            def get(self, *a):
                return None

            def set(self, *a, **k):
                return True

            def delete(self, *a):
                return 1

        monkeypatch.setattr(
            "app.tasks.redis_state.get_redis_client", lambda *a, **k: _Redis(),
            raising=False,
        )

    return _bind


@pytest.mark.asyncio
async def test_specimen_a_never_graded_market_is_graded_end_to_end(live_grader):
    """THE ACCEPTANCE. A real market goes in; a graded row comes out.

    This is what the 42-test family never did. The assertion is on the UPDATE
    the shipping code issued — its table, its bound winner and loser leg ids,
    and the resolution_source that makes the cohort revertible in one
    predicate — not on any string in any function body.
    """
    row, session = _specimen_session()
    clob = _specimen_clob(winner="Yes")
    live_grader(session, clob)

    out = await clob_resolve.clob_resolve_drain(
        limit=10,
        dry_run=False,
        write_tiers=_DEFAULT_WRITE_TIERS,
        cohort=_COHORT_NEVER_GRADED,
    )

    # The venue was actually asked about THIS market.
    assert clob.asked == [SPECIMEN_CID]

    # A row was actually written, once, and committed.
    assert out["written"] == 1, out
    assert len(session.writes) == 1
    sql, params = session.writes[0]
    assert "UPDATE futures_outcomes" in sql
    assert "is_winner = (id = :win_id)" in sql
    assert params["win_id"] == 900_001   # Yes won at the venue
    assert params["lose_id"] == 900_002
    assert params["src"] == _WRITE_SOURCE
    assert session.commits == 1

    # And the run reports what it is still sitting on.
    assert out["owned_backlog"] == 25264
    assert out["terminal"] == "partial"


@pytest.mark.asyncio
async def test_specimen_grades_the_other_side_when_the_venue_says_so(live_grader):
    """Both directions (gotcha #43). A grader that always crowns leg 1 would
    pass the test above; it fails here."""
    row, session = _specimen_session()
    clob = _specimen_clob(winner="No")
    live_grader(session, clob)

    out = await clob_resolve.clob_resolve_drain(
        limit=10, dry_run=False, cohort=_COHORT_NEVER_GRADED
    )

    assert out["written"] == 1
    _, params = session.writes[0]
    assert params["win_id"] == 900_002
    assert params["lose_id"] == 900_001


@pytest.mark.asyncio
async def test_specimen_dry_run_writes_nothing_but_still_reports(live_grader):
    """The apply gate, exercised rather than asserted about."""
    row, session = _specimen_session()
    live_grader(session, _specimen_clob())

    out = await clob_resolve.clob_resolve_drain(
        limit=10, dry_run=True, cohort=_COHORT_NEVER_GRADED
    )

    assert session.writes == []
    assert session.commits == 0
    assert out["written"] == 0
    assert out["checked"] == 1
    assert out["resolved_direct"] == 1  # it KNEW the answer and declined to write


@pytest.mark.asyncio
async def test_specimen_integrity_guard_refuses_a_mismatched_question(live_grader):
    """The mandatory guard is real code on this path, not a comment. A CLOB
    response about a different market must not be written, even though the
    condition_id matched."""
    row, session = _specimen_session()
    clob = _FakeCLOB({
        SPECIMEN_CID: {
            "question": "Will the Federal Reserve cut rates in December 2026?",
            "tokens": [
                {"token_id": "t1", "outcome": "Yes", "winner": True},
                {"token_id": "t2", "outcome": "No", "winner": False},
            ],
        }
    })
    live_grader(session, clob)

    out = await clob_resolve.clob_resolve_drain(
        limit=10, dry_run=False, cohort=_COHORT_NEVER_GRADED
    )

    assert session.writes == []
    assert out["written"] == 0
    assert out["integrity_skipped"] == 1


@pytest.mark.asyncio
async def test_the_beat_default_still_cannot_reach_the_never_graded_cohort(
    live_grader,
):
    """The safety direction, and the reason the write path is not simply ON.

    25,264 markets is an attended apply bound to a reviewed ApplyPlan, not
    something a beat decides. The scheduled call passes no cohort, so the
    default must remain the dropped cohort — proven by driving the real
    function and reading the predicate it selected with.
    """
    row, session = _specimen_session()
    live_grader(session, _specimen_clob())

    out = await clob_resolve.clob_resolve_drain(limit=10, dry_run=True)

    assert out["cohort"] == _COHORT_DROPPED
    assert _WRITE_SOURCE_NEVER_GRADED not in str(out)


@pytest.mark.asyncio
async def test_an_unmeasured_backlog_does_not_let_the_run_claim_complete(
    live_grader,
):
    """Wire-level gotcha #54: the census failing must degrade the verdict, not
    silently produce the flattering reading."""

    row, session = _specimen_session()

    async def _boom(stmt, params=None):
        sql = " ".join(str(stmt).split())
        if "count(*)" in sql.lower() and "owned" in sql.lower():
            raise RuntimeError("canceling statement due to statement timeout")
        return await _RecordingSession.execute(session, stmt, params)

    session.execute = _boom  # type: ignore[method-assign]
    live_grader(session, _specimen_clob())

    out = await clob_resolve.clob_resolve_drain(
        limit=10, dry_run=True, cohort=_COHORT_NEVER_GRADED
    )

    assert out["owned_backlog"] is None
    assert out["owned_backlog_reason"].startswith("unmeasured:")
    assert out["terminal"] == "partial"
    assert out["terminal_reason"] == "backlog_unmeasured"
