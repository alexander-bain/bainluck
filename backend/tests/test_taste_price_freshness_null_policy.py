"""#2024 — the taste strata's price-freshness floor moves onto `price_changed_at`.

UX-P108, discharging the reader half of #2024. The writer landed in UX-P107
(`app/utils/price_change_stamp.py`, five sites, three poll tasks); this is the
first consumer, and it is the one Fable flagged as "needs a NULL policy".

── WHAT THE SWITCH BUYS ─────────────────────────────────────────────────────

`FuturesOutcome.last_updated` is bumped on EVERY poll regardless of whether the
price moved, so as a freshness signal it can only separate ABANDONED markets
(nothing writes them, so the stamp goes stale) from everything else. It cannot
see an actively-polled market whose price has sat still since May — which is
exactly the specimen #2019 was opened on, and both cards Alex marked `bad` in
that session were of that shape (111 and 63 days).

── WHY THE NULL ARM IS THE LOAD-BEARING PART ────────────────────────────────

The column is NEW. Every production row is NULL until its next price change,
and a row whose price never moves again stays NULL forever. Read as the obvious
`price_changed_at >= cutoff`, the floor excludes all of them and the labeling
queue serves NOTHING on the day it deploys — a strictly worse failure than the
staleness it fixes, and a silent one.

So NULL is UNKNOWN, never STALE (gotcha #53: an empty is not an absence). The
consequences are asserted below in BOTH directions, because a fail-open guard
that has quietly become fail-open-always is the #1958 shape:

  * a stamped-and-recent row is admitted        (the new signal works)
  * a stamped-and-stale row is REFUSED even
    when `last_updated` is fresh                (the new signal BITES — this is
                                                 the whole point of the change,
                                                 and the assertion a naive
                                                 fallback-first ordering fails)
  * an unstamped row falls back to `last_updated`  (nothing empties on deploy)

── WHAT THESE TESTS PROVE, AND WHAT THEY DO NOT ─────────────────────────────

They compile the real query and read its SQL. That proves the PREDICATE SHAPE
reaching the database — which is the thing a "simplification" back to a bare
column comparison would change, and the thing no fixture-based test in
`test_labeling_sampler_serves_renderable_2019.py` can see.

It is NOT a behavioural test against rows: there is no local Postgres in this
sandbox and these models carry JSONB, so a seeded assertion would have to run
on CI. Stated rather than implied (ruling 065: report the split, never the
flattering aggregate). The owed half is one seeded integration case.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.routes.admin_judgments import (
    _MAX_TASTE_PRICE_AGE,
    _PRICE_FRESH_STRATA,
    _labeling_stratum_query,
)

NOW = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)


def _sql(stratum: str) -> str:
    query = _labeling_stratum_query(stratum, now=NOW, limit=10)
    return str(query.compile(compile_kwargs={"literal_binds": True}))


@pytest.fixture(scope="module")
def fresh_sql() -> str:
    # Any member of the strata set; the floor is applied identically to all.
    return _sql(sorted(_PRICE_FRESH_STRATA)[0])


def test_the_strata_set_is_not_empty():
    """Anti-vacuity, first. Every assertion below is over a stratum drawn from
    this set, so an empty set would make the whole file pass over nothing."""
    assert _PRICE_FRESH_STRATA, "no price-fresh strata — this file checks nothing"


def test_the_floor_reads_price_changed_at(fresh_sql: str):
    assert "price_changed_at" in fresh_sql, (
        "the taste price-freshness floor no longer reads `price_changed_at`. "
        "`last_updated` alone cannot see an actively-polled market whose price "
        "has not moved in three months — #2019's exact specimen."
    )


def test_the_null_arm_is_present_and_falls_back(fresh_sql: str):
    """The deploy-safety property. Without this arm the queue empties on day one."""
    assert "price_changed_at IS NULL" in fresh_sql, (
        "the NULL arm is gone. `price_changed_at` is NULL on every row until its "
        "next price change, so a bare `>= cutoff` refuses the entire corpus and "
        "the labeling queue silently serves nothing. NULL is UNKNOWN, not STALE "
        "(gotcha #53)."
    )
    assert "last_updated" in fresh_sql, (
        "the fallback to `last_updated` is gone. It is what makes an unstamped "
        "row behave exactly as it does today, which is why this reader could "
        "ship before the writer's backfill exists."
    )


def test_both_stamps_are_compared_against_the_SAME_cutoff(fresh_sql: str):
    """One cutoff, two columns — never two independently-drifting horizons.

    Two literals would be two policies, and the second one would be the one
    nobody remembered to change.
    """
    cutoff = NOW - _MAX_TASTE_PRICE_AGE
    # The compiled literal keeps the date; the exact quoting is dialect-shaped,
    # so match on the date portion rather than on punctuation (ruling 063).
    stamp = cutoff.strftime("%Y-%m-%d")
    assert fresh_sql.count(stamp) >= 2, (
        f"expected both freshness comparisons against {stamp}, found "
        f"{fresh_sql.count(stamp)} — the two columns are being judged against "
        "different horizons."
    )


def test_the_fallback_is_GATED_on_null_and_not_a_bare_OR(fresh_sql: str):
    """** THE ASSERTION THAT SEPARATES A FIX FROM A NO-OP. **

    `price_changed_at >= c OR last_updated >= c` compiles, reads sensibly, and
    changes NOTHING: every row admitted today by `last_updated` is still
    admitted, so the stale-but-polled cards #2019 was opened on all survive. The
    fallback must be reachable ONLY when there is no stamp to judge.

    So the NULL test and the `last_updated` comparison must be ANDed together.
    """
    normalised = " ".join(fresh_sql.split())
    assert (
        "price_changed_at IS NULL AND" in normalised
        or "AND futures_outcomes.price_changed_at IS NULL" in normalised
    ), (
        "the `last_updated` fallback is not gated on `price_changed_at IS NULL`. "
        "An ungated OR re-admits every stale-but-polled card and makes this "
        "change a no-op that looks like a fix.\nSQL: " + normalised
    )


def test_the_floor_is_scoped_to_the_taste_strata_only():
    """`stale_fixable` exists to SURFACE stale cards so they can be fixed.

    Applying the floor there would delete the stratum's reason for existing —
    the same both-directions discipline gotcha #43 requires of every cap.
    """
    assert "stale_fixable" not in _PRICE_FRESH_STRATA
    assert "price_changed_at" not in _sql("stale_fixable")
