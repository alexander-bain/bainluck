"""The `/search` head may only be elected by ATTESTED demand (LAT-P102, #1916).

WHAT CLASS OF BUG THIS FILE EXISTS TO CATCH: a warmer that spends real database
time making OUR OWN probe traffic fast, and reports a green pass for doing it.

#1916 blocked head selection from `search_query_logs` until a clean distribution
existed, and LAT-P090 shipped the warmer disabled rather than step over that.
LAT-P102 measured the table and found the block both resolvable and understated:

    30-day census, 2026-08-27                      rows    share
    total                                          3,851
    carrying no session_id and no user_id          3,838   99.66 %
    in the 07:09-07:12 sentinel minute               922   23.9 %   (#1916's)
    in a burst minute (>= 8 distinct q / minute)   2,858   74.2 %

`session_id` is the write-time flag #1916 asks for and it is already in the
schema — both shipping clients attach `x-session-id` to every search and no
probe in this repo does. Read through it, the attested 30-day distribution is
**13 rows / 12 sessions / 7 distinct queries**, of which exactly ONE (`red sox`)
was asked by two different sessions.

So the tests below are not about tidiness. Each one pins a clause without which
the warmer would go back to warming `masters winner`, `stanley cup` and
`world cup` — the sentinel's own gold set — and calling it demand.
"""

from __future__ import annotations

import inspect

import pytest


def test_the_head_query_filters_to_attested_rows():
    """The clause that resolves #1916. Deleting it re-contaminates the head.

    Asserted against the SQL text rather than against a live query because the
    failure this guards is a future edit that widens the filter for a good
    reason ("the head is empty, let's loosen it") — and that edit is visible in
    the text long before any environment has enough traffic to reveal it.
    """
    from app.tasks.search_head_warmer import _USER_HEAD_SQL

    normalized = " ".join(_USER_HEAD_SQL.split()).lower()
    assert "session_id is not null or user_id is not null" in normalized, (
        "the head query no longer filters to attested rows — it is electing a "
        "head from a table measured at 99.66% session-less automation, which is "
        "exactly what #1916 blocks"
    )


def test_the_head_is_ranked_and_floored_by_distinct_sessions_not_rows():
    """The anti-artifact clause. One person retyping is not a head.

    `patriots` is in the 30-day attested sample five times, all from ONE session
    inside nine seconds — more rows than any genuinely-shared query has. Ranked
    by rows it leads; floored by sessions it never appears.
    """
    from app.tasks.search_head_warmer import MIN_HEAD_SESSIONS, _USER_HEAD_SQL

    normalized = " ".join(_USER_HEAD_SQL.split()).lower()

    assert "having count(distinct" in normalized, (
        "the session floor is gone — one session retyping a word now elects a "
        "warm slot"
    )
    assert "order by sessions desc" in normalized, (
        "the head is ranked by rows again; rows count one person's retyping as "
        "demand, sessions count people"
    )
    assert MIN_HEAD_SESSIONS >= 2, (
        "MIN_HEAD_SESSIONS below 2 is not a floor — a query one person asked "
        "once would be warmed for a month"
    )


def test_resolve_head_never_falls_back_to_the_unfiltered_table():
    """The missing fallback is load-bearing, so its absence is asserted.

    The tempting kindness is "if the attested head is empty, use the whole table
    so the warmer has something to do". That reinstates #1916's block in the one
    state where it bites hardest: the attested head is empty precisely when all
    the traffic is ours.
    """
    from app.tasks import search_head_warmer

    src = inspect.getsource(search_head_warmer.resolve_head)

    assert "_head_from_user_rows" in src
    assert "_head_from_query_log" not in src, (
        "resolve_head reaches for typeahead_warmer's WHOLE-TABLE head query "
        "again — that is the unfiltered source #1916 blocks for head selection"
    )


def test_the_typeahead_head_query_was_not_quietly_changed_too():
    """Two questions of one table, and only one of them changed.

    `typeahead_warmer._head_from_query_log` still reads the table whole, on
    purpose: its surface needs the volume and it blends with a second source.
    Sharing one query between the two would have meant silently re-sourcing the
    typeahead head as well — which is the other half of what #1916 forbids.
    """
    from app.tasks import typeahead_warmer

    src = inspect.getsource(typeahead_warmer._head_from_query_log)
    assert "session_id" not in src, (
        "the typeahead head query grew the attestation filter — that is a "
        "re-sourcing of the /typeahead head, which #1916 blocks separately and "
        "which no measurement in LAT-P102 covers"
    )


@pytest.mark.asyncio
async def test_an_empty_attested_head_is_partial_and_warms_nothing():
    """No demand is a finding, not a clean pass ("it returned" is not "it worked").

    This is the state production is in on the day LAT-P102 deploys for every
    query but one, and the warmer must be honest about it rather than reporting
    a green pass over zero items.
    """
    from app.tasks.search_head_warmer import (
        _summarize,
        full_rebuild_budget_s,
        resolve_head,
    )

    class _EmptyResult:
        def all(self):
            return []

    class _Session:
        async def execute(self, *a, **kw):
            return _EmptyResult()

        async def rollback(self):
            return None

    head, source = await resolve_head(_Session(), 8)

    assert head == []
    assert source.startswith("empty:"), (
        "an empty head must name itself as empty in the source string — a "
        "consumer must not have to infer it from len(head)"
    )
    assert "user_attested" in source

    summary = _summarize(
        head=head,
        results=[],
        source=source,
        seconds_wall=0.0,
        since_last=None,
        width=2,
        budget_s=full_rebuild_budget_s(),
    )
    assert summary["terminal"] == "partial", (
        "a warmer whose purpose is a hot head reported `complete` while the "
        "head was cold"
    )


@pytest.mark.asyncio
async def test_an_unreadable_table_yields_an_empty_head_and_never_raises():
    """A warmer never takes the app down, and never invents a head either.

    The dangerous shape here would be swallowing the error and returning a
    static floor — the pass would look identical to a real one while warming
    keys nobody asked for.
    """
    from app.tasks.search_head_warmer import _head_from_user_rows

    rolled_back = []

    class _Session:
        async def execute(self, *a, **kw):
            raise RuntimeError("relation does not exist")

        async def rollback(self):
            rolled_back.append(True)

    assert await _head_from_user_rows(_Session(), 8) == []
    assert rolled_back, (
        "the failed head read left the session's transaction poisoned — the "
        "next query on it would fail for an unrelated-looking reason"
    )


def test_the_head_query_binds_every_parameter_it_looks_like_it_binds():
    """Gotcha #45: a `:` inside a string literal can parse as a bind param.

    `'u:' || user_id` sits in this query and reads exactly like the shape that
    bit us before. Five binds is the correct count; six means `u` was captured
    and the query would fail at execute time with a missing-parameter error that
    names a parameter nobody wrote.
    """
    from sqlalchemy import text

    from app.tasks.search_head_warmer import _USER_HEAD_SQL

    assert sorted(text(_USER_HEAD_SQL)._bindparams.keys()) == [
        "days",
        "hi",
        "lim",
        "lo",
        "min_sessions",
    ]


def test_the_warmed_window_matches_the_window_the_head_is_measured_over():
    """A head measured over 30 days and warmed against a 7-day window would
    silently warm terms the measurement never saw, and vice versa. One number.
    """
    from app.tasks.search_head_warmer import HEAD_WINDOW_DAYS, _USER_HEAD_SQL

    assert HEAD_WINDOW_DAYS == 30
    assert "make_interval(days => :days)" in " ".join(_USER_HEAD_SQL.split()), (
        "the window is hardcoded in the SQL instead of reading the declared "
        "constant — the same two-places drift that made the /typeahead TTL a "
        "red test"
    )
