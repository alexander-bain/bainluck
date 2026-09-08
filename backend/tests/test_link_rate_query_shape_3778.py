"""#3778 follow-up: the link-rate queries must really SELECT what they claim to.

CERT-2219 granted the attachment split its token and named exactly one gap,
nonblocking, which this file closes:

    The current fake-session guards validate aggregation but supply the event
    anchor row fields themselves.

That is precisely true. `test_link_rate_attachment_split_3778._FakeSession`
takes `execute(*_args)` and throws the statement away, and its `_market()`
helper hands back a row that already carries `event_espn_id` and
`event_external_id`. So the whole attachment-split suite -- every test proving
anchored/self_minted partition correctly -- stays GREEN if someone deletes the
`.outerjoin(Event, ...)` and the two `Event.*` labelled columns from
`_compute_link_rate`'s real SQL. The aggregation is pinned; the SELECT that
feeds it is not pinned by anything.

The production consequence of that unpinned SELECT is not a wrong number, it is
worse in one direction and much worse in the other:

* Drop the labelled columns and `row.event_espn_id` raises AttributeError
  inside the hourly-cached canonical endpoint -- loud, at least.
* Change `.outerjoin` to `.join` and NOTHING raises. Every unlinked market is
  silently dropped from the result set, so `total` collapses to `linked` and
  `link_rate_pct` reads a flat, permanent **100%** -- the exact flattery #3778
  exists to remove, restored one layer down, in a metric CLAUDE.md names as
  canonical and Alex reads as health. The route's own comment warns about this
  in prose; prose is not a gate.

So these assertions are structural, made against the statement objects the
function actually hands to `execute`, not against a compiled SQL string -- a
string test on `LEFT OUTER JOIN events` would pass just as happily on a
statement that selected the anchor columns from the wrong table.

The `_rejects_*` tests are the point of the file as much as the positive ones:
a shape guard that has never been shown to FAIL has not been shown to
discriminate. They build the mutations by hand and require the same helper to
refuse them.

CERT-2226 granted the join guard above its token and named exactly one
remaining gap, nonblocking, which the second half of this file closes:

    inspect or forbid future predicates on `events` columns that could
    null-reject the left join.

An OUTER join is only half the protection. For a market with no event the
joined `events` columns are all NULL, and *any* WHERE predicate on one of them
evaluates to NULL rather than true -- so the row is filtered out. A single
`Event.espn_id.isnot(None)` added to either `.where(...)` therefore drops every
unlinked market while the join still reads `LEFT OUTER JOIN events` in the SQL
and every assertion in the first half of this file still passes. `total`
collapses onto `linked` and the published rate reads a permanent 100%: the same
#3778 flattery the join guard exists to prevent, reached by the one door that
guard does not watch. This is the standard "left join defeated by its own WHERE
clause" trap, and it is a silent one -- nothing raises, the number just gets
better.

The rule enforced is a bright line rather than an attempt to decide which event
predicates happen to be null-tolerant: **these two WHERE clauses filter the
MARKET population, so they may reference `futures_markets` and nothing else.**
The event row is joined to be *classified*, never to be filtered on. A genuine
future need for an event-side predicate has an always-safe home -- the ON clause
-- and putting it there trips the exact-onclause assertion above, which is the
intended friction: a human then edits this guard deliberately, having read why.
"""

import asyncio

import pytest
from sqlalchemy import func, or_, select
from sqlalchemy.sql import visitors
from sqlalchemy.sql.elements import ColumnClause

from app.models.models import Event, FuturesMarket
from app.routes.admin_matching import _compute_link_rate

#: The only table a link-rate WHERE clause may reference. An allowlist, not a
#: denylist of `events`: a predicate on some third table joined in later is the
#: same defect wearing a name this file has never heard of.
WHERE_CLAUSE_TABLE = "futures_markets"

#: label -> (table, column) every link-rate SELECT must carry for
#: `_classify_attachment` to be able to grade an attachment at all.
REQUIRED_ANCHOR_COLUMNS = {
    "event_espn_id": ("events", "espn_id"),
    "event_external_id": ("events", "external_id"),
}


class _CapturingSession:
    """Records each statement and returns an empty result for it.

    Empty rows are deliberate: this file asserts nothing about aggregation
    (that is the attachment-split suite's job) and everything about the shape
    of the query. With no rows, a passing test here cannot be borrowing
    correctness from fixture data the way the split suite's `_market()` does.
    """

    def __init__(self):
        self.statements = []

    async def execute(self, statement, *_args, **_kwargs):
        self.statements.append(statement)

        class _Empty:
            def all(self):
                return []

        return _Empty()


def _captured_statements():
    session = _CapturingSession()
    asyncio.run(_compute_link_rate(session, stmt_timeout_s=None))
    assert len(session.statements) == 2, (
        f"_compute_link_rate issued {len(session.statements)} queries; this "
        "guard knows about two (Kalshi, then Polymarket). If the function grew "
        "a third data query it needs checking too -- update this guard, do not "
        "relax the count."
    )
    return session.statements


def _assert_anchor_join_shape(statement, *, label):
    """Raise AssertionError unless `statement` can grade an attachment.

    Structural, in three parts: the anchor columns are selected AND resolve to
    the `events` table; the events table is reached by an OUTER join; that join
    is on the FK the classifier assumes.
    """
    selected = statement.selected_columns

    for column_label, (table_name, column_name) in REQUIRED_ANCHOR_COLUMNS.items():
        assert column_label in selected.keys(), (
            f"{label}: the SELECT has no `{column_label}` column, so "
            "`_classify_attachment` cannot tell an ESPN-anchored event row from "
            "one this ingest minted itself. #3778's split reads it off the row."
        )
        element = selected[column_label].element
        assert (element.table.name, element.name) == (table_name, column_name), (
            f"{label}: `{column_label}` resolves to "
            f"{element.table.name}.{element.name}, not {table_name}.{column_name}. "
            "The label is right and the source is wrong, which is the one "
            "failure a compiled-SQL string check would wave through."
        )

    froms = statement.get_final_froms()
    assert len(froms) == 1, (
        f"{label}: expected exactly one FROM element (the join), got {len(froms)}. "
        "A cartesian product here would multiply the counts."
    )
    join = froms[0]

    assert getattr(join, "right", None) is not None, (
        f"{label}: the FROM is not a join at all -- the `events` table is not "
        "reached, so both anchor columns cannot be coming from where they claim."
    )
    assert join.left.name == "futures_markets" and join.right.name == "events", (
        f"{label}: the join is {join.left.name} -> {join.right.name}, expected "
        "futures_markets -> events."
    )

    # The load-bearing assertion of the whole file.
    assert join.isouter is True, (
        f"{label}: the join to `events` is an INNER join. Every unlinked market "
        "is dropped from the result set, so `total` collapses onto `linked` and "
        "the published link rate reads a permanent 100% -- #3778's flattery, "
        "restored one layer down, in the metric CLAUDE.md calls canonical."
    )
    assert join.full is False, (
        f"{label}: the join is FULL OUTER, which invents rows for events that "
        "have no market and would inflate the denominator."
    )

    onclause = str(join.onclause)
    assert onclause == "futures_markets.event_id = events.id", (
        f"{label}: the join condition is `{onclause}`, not "
        "`futures_markets.event_id = events.id`. The classifier grades the event "
        "a market is attached to; any other condition grades a different row."
    )


def _where_clause_columns(statement):
    """Every real table column referenced anywhere in `statement`'s WHERE.

    `visitors.iterate` walks the whole predicate tree, so a column buried in an
    `or_()`, an `in_()` or a `func.lower()` is found -- which matters, because
    the production Kalshi filter wraps `external_id` in exactly that way and a
    top-level-only check would be trivially evaded by one `lower()`.

    Bind parameters and literals have no `.table` and are skipped.
    """
    where = statement.whereclause
    if where is None:
        return []
    return [
        element
        for element in visitors.iterate(where)
        if isinstance(element, ColumnClause)
        and getattr(element, "table", None) is not None
    ]


def _assert_no_null_rejecting_predicate(statement, *, label):
    """Raise AssertionError unless the WHERE filters markets and only markets.

    See the module docstring: an event-side predicate silently converts the
    OUTER join back into an INNER one, and no assertion in
    `_assert_anchor_join_shape` can see it happen.
    """
    referenced = _where_clause_columns(statement)

    # Non-vacuity first. With no WHERE at all -- or one that has stopped
    # constraining the market population -- every assertion below passes
    # trivially, and a guard that cannot fail is not a guard.
    assert any(column.table.name == WHERE_CLAUSE_TABLE for column in referenced), (
        f"{label}: the WHERE clause references no `{WHERE_CLAUSE_TABLE}` column "
        "at all. Either the market filters were dropped -- which blows the "
        "denominator open -- or this guard is now passing vacuously. Both need "
        "a human."
    )

    offenders = sorted(
        {
            f"{column.table.name}.{column.name}"
            for column in referenced
            if column.table.name != WHERE_CLAUSE_TABLE
        }
    )
    assert not offenders, (
        f"{label}: the WHERE clause filters on {', '.join(offenders)}, which "
        f"is not `{WHERE_CLAUSE_TABLE}`. For a market with no event those "
        "columns are NULL, so the predicate is NULL rather than true and the "
        "row is dropped -- the OUTER join is defeated by its own WHERE clause, "
        "`total` collapses onto `linked`, and the published link rate reads a "
        "permanent 100%. That is #3778's flattery restored through the one door "
        "the join assertions do not watch, and nothing raises when it happens. "
        "If the predicate is genuinely needed, it belongs in the ON clause "
        "(where an unmatched row survives as NULLs); expect to update the "
        "exact-onclause assertion in this file by hand when you do."
    )


def test_the_kalshi_query_can_grade_an_attachment():
    _assert_anchor_join_shape(_captured_statements()[0], label="kalshi")


def test_the_polymarket_query_can_grade_an_attachment():
    _assert_anchor_join_shape(_captured_statements()[1], label="polymarket")


def test_the_guard_rejects_an_inner_join():
    """The mutation that changes no number in the split suite and breaks prod."""
    inner = (
        select(
            FuturesMarket.event_id,
            Event.espn_id.label("event_espn_id"),
            Event.external_id.label("event_external_id"),
        )
        .join(Event, FuturesMarket.event_id == Event.id)
    )
    with pytest.raises(AssertionError, match="INNER join"):
        _assert_anchor_join_shape(inner, label="control")


def test_the_guard_rejects_a_missing_anchor_column():
    without = (
        select(
            FuturesMarket.event_id,
            Event.espn_id.label("event_espn_id"),
        )
        .outerjoin(Event, FuturesMarket.event_id == Event.id)
    )
    with pytest.raises(AssertionError, match="no `event_external_id` column"):
        _assert_anchor_join_shape(without, label="control")


def test_the_guard_rejects_a_right_label_on_a_wrong_source():
    """A compiled-SQL string check would pass this one; the structural one must not.

    Both anchor labels are present and the outer join to `events` is present,
    so the SQL text contains every substring a naive guard would look for --
    but `event_espn_id` is reading `futures_markets.external_id`, so every
    market grades as anchored and the split silently reports 0 self_minted.
    """
    mislabelled = (
        select(
            FuturesMarket.event_id,
            FuturesMarket.external_id.label("event_espn_id"),
            Event.external_id.label("event_external_id"),
        )
        .outerjoin(Event, FuturesMarket.event_id == Event.id)
    )
    with pytest.raises(AssertionError, match="resolves to futures_markets.external_id"):
        _assert_anchor_join_shape(mislabelled, label="control")


def test_the_kalshi_query_filters_only_markets():
    _assert_no_null_rejecting_predicate(_captured_statements()[0], label="kalshi")


def test_the_polymarket_query_filters_only_markets():
    _assert_no_null_rejecting_predicate(_captured_statements()[1], label="polymarket")


def test_the_guard_rejects_an_event_side_predicate():
    """The mutation that passes every assertion in the first half of this file.

    `LEFT OUTER JOIN events` is still in the SQL, both anchor columns still
    resolve to `events`, the ON clause is still the FK -- and every unlinked
    market is gone, because `NULL IS NOT NULL` is not true.
    """
    null_rejecting = (
        select(
            FuturesMarket.event_id,
            Event.espn_id.label("event_espn_id"),
            Event.external_id.label("event_external_id"),
        )
        .outerjoin(Event, FuturesMarket.event_id == Event.id)
        .where(
            FuturesMarket.source == "kalshi",
            Event.espn_id.isnot(None),
        )
    )
    # It really does pass the join guard -- that is the whole point of adding
    # a second helper rather than tightening the first.
    _assert_anchor_join_shape(null_rejecting, label="control")
    with pytest.raises(AssertionError, match="events.espn_id"):
        _assert_no_null_rejecting_predicate(null_rejecting, label="control")


def test_the_guard_rejects_a_buried_event_side_predicate():
    """A top-level-only check would wave this through; the traversal must not."""
    buried = (
        select(FuturesMarket.event_id)
        .outerjoin(Event, FuturesMarket.event_id == Event.id)
        .where(
            FuturesMarket.source == "kalshi",
            or_(
                FuturesMarket.status == "open",
                func.lower(Event.sport_id).in_(["1", "2"]),
            ),
        )
    )
    with pytest.raises(AssertionError, match="events.sport_id"):
        _assert_no_null_rejecting_predicate(buried, label="control")


def test_the_guard_rejects_a_statement_with_no_market_filter():
    """Non-vacuity control: the offender check alone passes on an empty WHERE."""
    unfiltered = select(FuturesMarket.event_id).outerjoin(
        Event, FuturesMarket.event_id == Event.id
    )
    with pytest.raises(AssertionError, match="references no `futures_markets` column"):
        _assert_no_null_rejecting_predicate(unfiltered, label="control")
