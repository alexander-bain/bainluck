"""LAT-P222 — the binds for the pre-match read, and the hazard they exist to remove.

The statement they feed (:data:`PREMATCH_PRIOR_SQL`) pairs its two arrays with
``unnest(a, b)``, which pairs **by index**. Nothing downstream can notice a
misalignment: hand event A's kickoff time to event B and the response is still
well-formed, still fast, still full of numbers — they are simply the wrong
numbers, cut off at the wrong moment. That is why the derivation is ONE pass in
one function instead of two comprehensions at the call site, and why it is
tested here rather than left to the two happening to agree.

What lives in the real-Postgres sibling instead
-----------------------------------------------
``tests/integration/test_prematch_prior_lateral_equivalence_pg.py`` executes the
statement over rows that straddle kickoff and proves it returns what the JOIN it
replaced returned. It cannot cover the NULL ``commence_time`` case below —
``events.commence_time`` is NOT NULL, so no database will hold that row — and
that case is precisely the one the rewrite could have changed by accident, since
the old shape excluded it through three-valued logic rather than on purpose.
"""

import re
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.utils.prematch_reading import (
    PREDICTION_MARKET_SOURCES,
    PREMATCH_PRIOR_SQL,
    SETTLED_STATUSES,
    prematch_prior_binds,
    settled_prematch_cutoffs,
)

# A fixed instant. gotcha #44 — offset from an anchor, never branch on the clock.
_T0 = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)


def _event(event_id, status, cutoff=_T0):
    return SimpleNamespace(id=event_id, status=status, commence_time=cutoff)


def test_only_settled_events_are_asked_about():
    """A scheduled or live card prints no pre-match reading, so it costs no read."""
    ids, cutoffs = settled_prematch_cutoffs(
        [
            _event(1, "scheduled"),
            _event(2, "completed"),
            _event(3, "live"),
            _event(4, "closed"),
            _event(5, "suspended"),
        ]
    )
    assert ids == [2, 4]
    assert len(cutoffs) == 2


def test_an_event_with_no_kickoff_time_is_dropped_rather_than_bound_as_null():
    """Said out loud, because the shape this replaced said it only by accident.

    The old statement compared ``s.captured_at <= e.commence_time``. With a NULL
    kickoff that comparison is NULL, not TRUE, so the event contributed no rows.
    The rewrite must exclude it as well — passing NULL through into the array
    would still work today, and would stop working the moment somebody made the
    comparison ``IS NOT DISTINCT FROM`` or added a COALESCE.
    """
    ids, cutoffs = settled_prematch_cutoffs(
        [
            _event(1, "completed", cutoff=None),
            _event(2, "completed"),
        ]
    )
    assert ids == [2]
    assert cutoffs == [_T0]
    assert None not in cutoffs


def test_the_two_arrays_are_paired_by_position_across_a_filtered_list():
    """The alignment hazard, executed.

    Every dropped row — unsettled, or kickoff-less — must drop from BOTH arrays
    at the same index. The list below interleaves the drops so that a filter
    applied to one array and not the other cannot coincidentally line up.
    """
    events = [
        _event(10, "scheduled", _T0 + timedelta(hours=1)),
        _event(11, "completed", _T0 + timedelta(hours=2)),
        _event(12, "completed", cutoff=None),
        _event(13, "live", _T0 + timedelta(hours=4)),
        _event(14, "closed", _T0 + timedelta(hours=5)),
        _event(15, "completed", _T0 + timedelta(hours=6)),
    ]
    ids, cutoffs = settled_prematch_cutoffs(events)

    assert list(zip(ids, cutoffs)) == [
        (11, _T0 + timedelta(hours=2)),
        (14, _T0 + timedelta(hours=5)),
        (15, _T0 + timedelta(hours=6)),
    ], "each id must still be carrying its OWN kickoff time"


def test_no_settled_candidate_means_no_round_trip_at_all():
    """`None`, not an empty bind dict: a query that can only return zero rows is
    one the cold build should not spend a round trip on."""
    assert prematch_prior_binds([_event(1, "scheduled"), _event(2, "live")]) is None
    assert prematch_prior_binds([]) is None


def test_the_binds_supplied_are_exactly_the_placeholders_the_statement_takes():
    """Neither side may be renamed alone.

    A missing bind raises at execute time, in production, on the cold path — and
    every unit test of this route answers with a double that would never notice.
    """
    placeholders = set(re.findall(r":(\w+)", PREMATCH_PRIOR_SQL))
    binds = prematch_prior_binds([_event(1, "completed")])

    assert binds is not None
    assert set(binds) == placeholders == {"ids", "cutoffs", "sources"}
    assert binds["sources"] == list(PREDICTION_MARKET_SOURCES)


def test_the_statement_does_not_read_the_events_table():
    """The class, not the instance: *a bound that depends on a second table,
    evaluated inside a scan of the big one.*

    Weak on its own — the sibling gate is what proves the rows — but it is the
    only assertion that goes red the moment somebody reintroduces the join for
    convenience, which is exactly how this cost arrived the first time.
    """
    body = PREMATCH_PRIOR_SQL.lower()

    assert "events" not in body, (
        "the pre-match read has grown a second reference to `events`. That is "
        "the LAT-P222 defect: the planner cannot evaluate a bound it must fetch, "
        "so it probes `events_pkey` once per snapshot row (24,528 loops for 53 "
        "rows, measured). Pass the value from the caller instead — "
        "`_score_events` is already holding it."
    )
    assert "win_prob_snapshots" in body
    assert "join" in body and "lateral" in body, (
        "the per-event `DISTINCT ON` inside a LATERAL is what keeps this on "
        "`ix_winprob_event_source`"
    )


def test_the_kickoff_bound_is_still_in_the_statement():
    """Without it a settled market prices the winner at ~100% and every finished
    card renders its own result back as a forecast."""
    assert "s.captured_at <= t.cutoff" in PREMATCH_PRIOR_SQL


def test_settled_statuses_are_the_two_the_card_grammar_calls_settled():
    assert SETTLED_STATUSES == frozenset({"completed", "closed"})
