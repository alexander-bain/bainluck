"""LAT-P113 — a brand-new install must not pay for questions with fixed answers.

## The defect these tests pin

``_load_personalization_context`` issued **seven sequential round trips** for a
principal the database has never seen. Three of them were literally
``select(...).where(False)``:

    favorites_query = select(UserFavorite).where(False)
    prefs_query     = select(UserPreference).where(False)
    pins_query      = select(UserPin).where(False)

They cannot return a row. Production's own planner agrees — EXPLAIN ANALYZE on
the deployed slug ``f0b512b8`` (2026-08-28) plans each to a bare ``Result``
node with **no table access at all**, at 0.016 / 1.225 / 0.024 ms. So they cost
approximately nothing to RUN and one full round trip each to ASK.

## Why the round-trip count is the thing worth guarding

Measured the same day, same slug, at the native first-paint shape
(``/api/feed?limit=50&event_pct=0.15``), six requests each with a fresh
``x-session-id``:

    run  x-feed-cache        total ms   personalization   cache_shared_hit
    1    shared_hit             48.75         40.36              8.35
    2    shared_hit             46.91         40.20              6.67
    3    shared_stale_hit       23.14         15.22              7.88
    4    shared_stale_hit       42.29         34.77              7.46
    5    shared_stale_hit       46.64         38.65              7.94
    6    shared_hit             30.00         21.32              8.62

``personalization`` is **66-86% of the entire request** — p50 36.7 ms of a
44.5 ms total, with the whole remainder being an ~8 ms shared-cache read.
Against that, the four REAL queries execute in 0.877 / 3.408 / 0.046 ms
server-side for an unseen principal. Server-side work is ~5 ms of a ~37 ms
stage.

**The stage is round TRIPS, not work.** That is why these tests count
statements rather than assert a duration: a wall-clock assertion in an
in-memory suite would measure the mock, and a "make it faster" test that can
pass while the seventh query comes back is not a guard.

## What is deliberately NOT changed

LAT-P089's inert-principal share still tests **structural equality** against a
default ``PersonalizationContext()`` — not a bespoke "has this session any
interactions" probe. That choice was made so a personalization field added
later is covered without anyone remembering a predicate, and nothing here
touches it. ``test_the_anonymous_context_still_equals_the_default`` pins that
the equality SURVIVES this change, because if it did not, the share would
silently stop firing and this "optimisation" would make cold opens much worse.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.utils.personalization import PersonalizationContext

_SESSION_ID = "brand-new-install-uuid-p113"

#: The three tables an anonymous principal has no rows in by construction —
#: every one of them is keyed on ``user_id`` and there is no user.
_USER_SCOPED_TABLES = ("user_favorites", "user_preferences", "user_pins")


def _counting_session(rows_by_table: dict[str, list] | None = None):
    """A DB stand-in that RECORDS every statement it is asked to execute.

    Returns ``(session, statements)`` where ``statements`` is the live list of
    compiled SQL strings, in execution order. Routing is by table name so a
    test can seed one table without teaching the mock the whole schema.
    """
    rows_by_table = rows_by_table or {}
    statements: list[str] = []

    def _result(rows: list):
        result = MagicMock()
        result.scalars.return_value.all.return_value = rows
        result.scalars.return_value.first.return_value = rows[0] if rows else None
        result.scalar_one_or_none.return_value = rows[0] if rows else None
        result.scalar.return_value = len(rows)
        result.fetchall.return_value = rows
        result.all.return_value = rows
        result.first.return_value = rows[0] if rows else None
        return result

    async def mock_execute(stmt, *args, **kwargs):
        sql = str(stmt)
        statements.append(sql)
        lowered = sql.lower()
        for table, rows in rows_by_table.items():
            if table in lowered:
                return _result(rows)
        return _result([])

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=mock_execute)
    session.rollback = AsyncMock()
    return session, statements


def _user(user_id: int = 364):
    """A stand-in for an identified principal (Alex's own id, per LAT-P089)."""
    user = MagicMock()
    user.id = user_id
    return user


async def _load(session, user, session_id=_SESSION_ID):
    from app.routes.feed import _load_personalization_context

    return await _load_personalization_context(
        session, user, session_id=session_id, config=None
    )


# --------------------------------------------------------------------------
# The count itself
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_anonymous_principal_issues_exactly_four_round_trips():
    """7 -> 4. The number is asserted exactly, not as an upper bound.

    An upper bound (``<= 7``) would stay green through the exact regression
    this exists to catch. If a legitimate new query is added, this number moves
    in a visible commit with an argument attached — which is the point.
    """
    session, statements = _counting_session()

    await _load(session, None)

    assert len(statements) == 4, (
        "an anonymous Discover open must issue exactly 4 DB round trips; "
        f"got {len(statements)}:\n" + "\n".join(f"  - {s[:120]}" for s in statements)
    )


@pytest.mark.asyncio
async def test_anonymous_principal_never_asks_the_three_user_scoped_tables():
    """The class guard: no statement may reference a table with no rows for us.

    This is the general clause and it survives deleting the specific case — it
    fails for a re-introduced ``where(False)``, for a ``where(user_id IS NULL)``
    written by someone being clever, and for any other spelling of asking a
    question whose answer is already known.
    """
    session, statements = _counting_session()

    await _load(session, None)

    joined = "\n".join(statements).lower()
    for table in _USER_SCOPED_TABLES:
        assert table not in joined, (
            f"an anonymous principal asked `{table}`, which is keyed on user_id "
            "and cannot return a row when there is no user"
        )


@pytest.mark.parametrize("principal", ["anonymous", "authenticated"])
@pytest.mark.asyncio
async def test_no_statement_is_ever_gated_on_a_constant_false(principal):
    """No statement on this loader may carry a provably-empty WHERE gate.

    🔴 This test is parametrized over BOTH principals because a mutation found
    the hole. The battery's M3 neutered the pins predicate to ``where(False)``
    *inside* the authenticated branch and every test stayed green: the mock
    routes results by table NAME, so a query with the right table and a dead
    predicate is indistinguishable from a correct one. The behavioural test
    below therefore proves less than it appears to, and no in-memory fixture
    can fix that — a mock does not evaluate SQL.

    What CAN be asserted is a property of the emitted SQL itself, and it is the
    general clause rather than the specific case: asking the database a
    question whose answer is fixed is never right here, for any principal. That
    sentence survives deleting the three queries that prompted it.
    """
    user = None if principal == "anonymous" else _user()
    session, statements = _counting_session()

    await _load(session, user)

    for sql in statements:
        collapsed = " ".join(sql.lower().split())
        assert "where false" not in collapsed, (
            f"a {principal} request executed a statement whose WHERE clause is "
            f"constant-false, so it cost a round trip to ask a fixed "
            f"question:\n  {sql[:200]}"
        )


# --------------------------------------------------------------------------
# The identified principal must NOT regress — this lane's #1 user is one
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_authenticated_principal_still_issues_all_seven():
    """Alex is the non-inert principal (LAT-P089: 139 interactions in 30 days).

    The fix must be a no-op for him — not slower, and not fewer queries either,
    because for a real user those three reads can return rows.
    """
    session, statements = _counting_session()

    await _load(session, _user())

    assert len(statements) == 7, (
        "an identified principal must still issue all 7 round trips; "
        f"got {len(statements)}"
    )

    joined = "\n".join(statements).lower()
    for table in _USER_SCOPED_TABLES:
        assert table in joined, (
            f"`{table}` was not read for an identified principal — the skip "
            "leaked out of the anonymous branch and deleted a feature"
        )


@pytest.mark.asyncio
async def test_authenticated_principal_still_loads_favorites_prefs_and_pins():
    """Behavioural, not structural: the loaded data must still arrive.

    A count test alone would pass if the three queries ran and their results
    were dropped on the floor, which is exactly the shape of a bad refactor.
    """
    favorite = MagicMock(team_id=7, relation_type="follow", weight=2.0)
    preference = MagicMock(sport_affinities={"basketball_nba": 1.0})
    pin = MagicMock(target_id=42, pin_type="event")

    session, _ = _counting_session(
        {
            "user_favorites": [favorite],
            "user_preferences": [preference],
            "user_pins": [pin],
        }
    )

    ctx = await _load(session, _user())

    assert ctx.team_relations == {7: {"follow"}}
    assert ctx.team_weights == {7: 2.0}
    assert ctx.sport_affinities == {"basketball_nba": 1.0}
    assert ctx.pinned_event_ids == {42}
    assert ctx.is_authenticated is True


# --------------------------------------------------------------------------
# LAT-P089's premise must survive this change
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_anonymous_context_still_equals_the_default():
    """If this breaks, the LAT-P089 share stops firing and cold opens get WORSE.

    The share is what turns a brand-new install's private-key miss into an ~8 ms
    read of the warmed anonymous entry. It is gated on
    ``ctx == PersonalizationContext()``. Skipping three queries must not change
    a single field of the context it returns — the queries returned nothing, so
    not running them must return the same nothing.
    """
    session, _ = _counting_session()

    ctx = await _load(session, None)

    assert ctx == PersonalizationContext(), (
        "the anonymous context is no longer structurally equal to a default "
        "one, so the LAT-P089 inert-principal share will silently stop firing"
    )


@pytest.mark.asyncio
async def test_a_principal_with_neither_user_nor_session_still_short_circuits():
    """The pre-existing fast path is untouched: zero identity, zero queries."""
    session, statements = _counting_session()

    ctx = await _load(session, None, session_id=None)

    assert statements == []
    assert ctx == PersonalizationContext()
