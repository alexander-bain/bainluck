"""#2239 — a search we could not finish must never be recorded as a search that found nothing.

`/api/events/search` sheds stages when its 20,000 ms deadline runs out and says
which ones in `degraded`. `routes/events.py` states the contract at the payload
site, verbatim:

    A stage we could not complete must be distinguishable from a stage that
    honestly found nothing.

It is distinguishable ON THE WIRE. It was not distinguishable in the one place
that keeps a record: `_answered_result_count` summed the answer sections, and a
degraded answer whose sections are empty sums to `0` — the identical value a
genuinely empty answer writes. So `search_query_logs` held two different facts
under one number, and the only surviving trace of the #2239 incident
(`patriots`, 2026-08-14 22:16 UTC, 25 -> 0 -> 0 -> 0 -> 25) is three rows of
that ambiguous zero. Fifteen days later the mechanism still cannot be named from
them, and that is the cost being paid here.

`result_count` is nullable and NO CONSUMER READS IT — both warm-head elections
(`search_head_warmer._USER_HEAD_SQL`, `typeahead_warmer`'s 30-day head) rank by
row and session counts and never touch the column. So NULL is free to mean
exactly what it should: we do not know, because we did not finish.

The invariant this file pins is one sentence: **every non-NULL `result_count` is
a complete answer.** Not "a floor", not "what we managed" — complete. A partial
count is the same ambiguity one step to the left (is 25 the answer, or the part
of the answer we reached?), which is why a degraded answer WITH content is NULL
too rather than logging its partial total.
"""

import pytest

from app.routes import events as events_route


def _payload(*, events_total=0, n_results=0, teams=0, concepts=0,
             futures=0, families=0, degraded=None):
    """A `/search` body. Mirrors `test_search_latency_contract._payload`, plus
    `degraded` — additive and present only when a stage was cut short, exactly
    as the route builds it (`**({"degraded": degraded} if degraded else {})`).
    """
    body = {
        "query": "q",
        "teams": [{"id": i} for i in range(teams)],
        "event_concepts": [{"slug": str(i)} for i in range(concepts)],
        "results": [{"id": 1000 + i} for i in range(n_results)],
        "futures": [{"id": 2000 + i} for i in range(futures)],
        "futures_families": [{"id": 3000 + i} for i in range(families)],
        "pagination": {"page": 1, "per_page": 25, "total_results": events_total},
    }
    if degraded:
        body["degraded"] = degraded
    return body


# ---------------------------------------------------------------------------
# The class itself.
# ---------------------------------------------------------------------------


def test_a_degraded_empty_answer_is_not_recorded_as_zero():
    """THE REGRESSION THIS FILE EXISTS FOR.

    Every stage shed, nothing to show. Recording `0` here is a claim that the
    query has no results — made from a request we abandoned. It is gotcha #53
    in the log: an empty 200 is a response shape, not an absence.
    """
    shed_everything = _payload(degraded=["events", "futures", "teams"])
    assert events_route._answered_result_count(shed_everything) is None, (
        "a search that could not complete logged a count of "
        f"{events_route._answered_result_count(shed_everything)!r} — "
        "'we did not finish' is back to being indistinguishable from 'nothing matched'"
    )


def test_a_degraded_answer_with_content_is_also_unknown_not_partial():
    """A partial count is the same ambiguity one step to the left.

    25 events with the futures stage shed is not "25". It is "25 and an unknown
    number more". Writing 25 makes the column mean two things again, and the
    second meaning is invisible — which is precisely how the first version of
    this bug survived 27 queries deep (LAT-P117).
    """
    partial = _payload(events_total=25, n_results=25, degraded=["futures"])
    assert events_route._answered_result_count(partial) is None


@pytest.mark.parametrize("degraded", [
    ["events"],
    ["event_count"],
    ["futures"],
    ["did_you_mean"],
    ["events", "futures"],
])
def test_every_stage_the_route_can_shed_produces_unknown(degraded):
    """The route appends to `degraded` at five sites. Any one of them means the
    answer is incomplete; none of them is a lesser kind of incomplete."""
    assert events_route._answered_result_count(_payload(degraded=degraded)) is None


# ---------------------------------------------------------------------------
# Fails closed, in both directions.
# ---------------------------------------------------------------------------


def test_a_complete_empty_answer_still_records_a_real_zero():
    """The whole point of making degraded NULL is that zero gets its meaning
    back. If this ever returns None the fix has destroyed the signal it was
    supposed to sharpen, and the flap detector #2239 asks for is impossible."""
    assert events_route._answered_result_count(_payload()) == 0


def test_a_complete_answer_still_counts_every_section():
    """LAT-P117's invariant is untouched by this change. `stanley cup`'s real
    production shape: 0 events, 2 futures, 1 family -> 2, not 0 and not None."""
    assert events_route._answered_result_count(
        _payload(events_total=0, futures=2, families=1)
    ) == 2


@pytest.mark.parametrize("falsy", [None, [], ""])
def test_an_absent_or_empty_degraded_key_is_a_complete_answer(falsy):
    """`degraded` is additive — the route omits it entirely on a full answer.
    An empty list must read as complete, not as unknown, or every ordinary
    search starts logging NULL."""
    body = _payload(futures=3)
    body["degraded"] = falsy
    assert events_route._answered_result_count(body) == 3


def test_a_malformed_degraded_value_never_raises_into_search():
    """Instrumentation never breaks search. A non-list `degraded` is still a
    declaration that something was cut short, so it reads as unknown."""
    body = _payload(futures=3)
    body["degraded"] = "events"
    assert events_route._answered_result_count(body) is None


# ---------------------------------------------------------------------------
# The wiring. The helper being right is worthless if the recorder rounds it off.
# ---------------------------------------------------------------------------


class _Req:
    def __init__(self):
        self.headers = {}
        self.cookies = {}

    class state:
        pass


def _capture(payload):
    captured = {}
    original = events_route._dispatch_search_log
    events_route._dispatch_search_log = lambda **kw: captured.update(kw)
    try:
        events_route._record_search_query(
            payload, q="patriots", request=_Req(), current_user=None
        )
    finally:
        events_route._dispatch_search_log = original
    return captured


def test_the_recorder_dispatches_null_and_does_not_coerce_it_to_zero():
    """Pins the WIRING. `result_count` is `Optional[int]` all the way down to the
    ORM column (nullable), so nothing on this path is entitled to turn the None
    back into a 0 — which an `or 0` anywhere between here and the INSERT would.
    """
    captured = _capture(_payload(degraded=["events", "futures"]))
    assert captured.get("query") == "patriots"
    assert "result_count" in captured, "the recorder stopped dispatching a count at all"
    assert captured["result_count"] is None, (
        "the degraded answer dispatched "
        f"result_count={captured['result_count']!r} instead of None"
    )


def test_the_recorder_still_dispatches_a_real_zero_for_a_complete_empty_answer():
    """The other direction of the same wiring."""
    captured = _capture(_payload())
    assert captured["result_count"] == 0
