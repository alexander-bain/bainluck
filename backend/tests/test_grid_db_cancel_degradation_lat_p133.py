"""#2303 / LAT-P133 — a Postgres statement_timeout must degrade, not 500.

`/api/playoffs/{league}` wraps its build in ``asyncio.wait_for(..., 25)`` and
#1484 made that wall degrade truthfully: labelled last-good if usable, else an
explicit 503 that says "degraded state, not an empty league". Production
measured the NFL grid returning **HTTP 500 at 20.30 s** — *below* the wall. The
database's own ``statement_timeout`` had cancelled the statement, asyncpg raised
``QueryCanceledError``, SQLAlchemy wrapped it in ``DBAPIError``, and nothing
caught it. All of #1484's work was bypassed by a door it did not know about.

What these tests pin, in order of how expensive each would be to lose:

1. **The refusal.** Only SQLSTATE 57014 is contained. A syntax error, a dead
   connection, a constraint violation and ``asyncio.CancelledError`` all still
   propagate. A widened ``except`` would answer "degraded, try later" to a query
   bug, and nobody chases a 503.
2. **The shape equivalence.** The DB-cancel path and the wall path are compared
   to EACH OTHER, not to literals written twice. Two branches that agree today
   because two assertions were copied is exactly the drift this pins against.
3. **No laundering.** #1484's rule survives the new door: an unusable last-good
   is no last-good, and neither failure may ever produce a 200 with zero teams.
"""

import asyncio
import json

import pytest
from fastapi import HTTPException
from unittest.mock import AsyncMock, MagicMock, patch

from app.routes.playoffs import (
    GRID_FAILURE_DB_CANCELED,
    GRID_FAILURE_TIMEOUT,
    _GRID_FAILURE_PHRASE,
    _serve_grid_degraded,
    get_playoff_grid_cached,
)
from app.utils.db_cancellation import (
    QUERY_CANCELED_CLASS_NAME,
    QUERY_CANCELED_SQLSTATE,
    is_query_canceled,
)


# ---------------------------------------------------------------------------
# Driver-shaped fakes. Deliberately NOT asyncpg imports: the predicate's whole
# claim is that it identifies the error without depending on the driver, and a
# test that imports asyncpg to build the input cannot observe that.
# ---------------------------------------------------------------------------
class QueryCanceledError(Exception):
    """asyncpg's real class name, with its real SQLSTATE attribute."""

    sqlstate = "57014"


class NamedOnlyQueryCanceledError(Exception):
    """A driver that classifies correctly but exposes no SQLSTATE."""


NamedOnlyQueryCanceledError.__name__ = QUERY_CANCELED_CLASS_NAME


class DriverError(Exception):
    """Any other asyncpg error — SQLSTATE supplied by the caller."""

    def __init__(self, sqlstate: str):
        super().__init__(f"driver error {sqlstate}")
        self.sqlstate = sqlstate


class Psycopg2Error(Exception):
    def __init__(self, pgcode: str):
        super().__init__(f"psycopg2 error {pgcode}")
        self.pgcode = pgcode


class DBAPIError(Exception):
    """SQLAlchemy's wrapper shape: the SQLSTATE lives on ``.orig``."""

    def __init__(self, orig: BaseException):
        super().__init__(f"(wrapped) {orig}")
        self.orig = orig


def _cancel_error() -> Exception:
    """The exact production shape: DBAPIError wrapping asyncpg's 57014."""
    return DBAPIError(QueryCanceledError("canceling statement due to statement timeout"))


def _redis_mock(values: dict):
    rc = MagicMock()
    rc.get = AsyncMock(side_effect=lambda key: values.get(key))
    rc.set = AsyncMock()
    rc.aclose = AsyncMock()
    return rc


# ---------------------------------------------------------------------------
# The predicate
# ---------------------------------------------------------------------------
class TestIsQueryCanceled:
    def test_the_production_shape_is_recognised(self):
        assert is_query_canceled(_cancel_error()) is True

    def test_a_bare_driver_error_is_recognised(self):
        assert is_query_canceled(QueryCanceledError("boom")) is True

    def test_sqlstate_alone_is_enough_whatever_the_class_is_called(self):
        """Isolates the primary test. ``DriverError`` carries 57014 and is NOT
        named ``QueryCanceledError``, so only the SQLSTATE branch can match it —
        deleting that branch fails here and nowhere else."""
        assert type(DriverError(QUERY_CANCELED_SQLSTATE)).__name__ != QUERY_CANCELED_CLASS_NAME
        assert is_query_canceled(DriverError(QUERY_CANCELED_SQLSTATE)) is True
        assert is_query_canceled(DBAPIError(DriverError(QUERY_CANCELED_SQLSTATE))) is True

    def test_psycopg2_pgcode_is_recognised(self):
        assert is_query_canceled(DBAPIError(Psycopg2Error(QUERY_CANCELED_SQLSTATE))) is True

    def test_a_driver_with_no_sqlstate_is_recognised_by_class_name(self):
        """The subordinate test. A driver that names the error right but does
        not populate SQLSTATE still gets a truthful degrade."""
        assert is_query_canceled(NamedOnlyQueryCanceledError("boom")) is True
        assert is_query_canceled(DBAPIError(NamedOnlyQueryCanceledError("boom"))) is True

    def test_an_explicit_raise_from_chain_is_followed(self):
        """Raised OUTSIDE an ``except`` on purpose. Written the obvious way —
        ``raise X from inner`` inside the handler — Python sets ``__context__``
        as well, so the assertion passes even with ``__cause__`` deleted from
        the walk. The battery's M-NO-CAUSE mutant survived exactly that test on
        its first pass; the mutant was right and the guard was weak."""
        try:
            raise RuntimeError("re-shaped") from QueryCanceledError("cancelled")
        except RuntimeError as outer:
            assert outer.__context__ is None, "this test must exercise __cause__ alone"
            assert is_query_canceled(outer) is True

    def test_an_implicit_context_chain_is_followed(self):
        try:
            try:
                raise QueryCanceledError("cancelled")
            except QueryCanceledError:
                raise RuntimeError("re-raised inside except")
        except RuntimeError as outer:
            assert outer.__cause__ is None, "this test must exercise __context__"
            assert is_query_canceled(outer) is True

    # -- refusals ----------------------------------------------------------
    @pytest.mark.parametrize("sqlstate", [
        "42601",   # syntax_error — a query bug, must stay a 500
        "42703",   # undefined_column
        "23505",   # unique_violation
        "57P01",   # admin_shutdown — same SQLSTATE CLASS, different condition
        "57P02",   # crash_shutdown
        "57P03",   # cannot_connect_now
        "08006",   # connection_failure
        "53300",   # too_many_connections
        "40001",   # serialization_failure
        "22P02",   # invalid_text_representation
    ])
    def test_every_other_sqlstate_is_refused(self, sqlstate):
        """The sweep, not a sample. 57P01/57P02/57P03 are in it on purpose:
        they share SQLSTATE class 57 with query_canceled, so a predicate that
        matched on the class prefix would pass every other case here and still
        be wrong."""
        assert sqlstate != QUERY_CANCELED_SQLSTATE
        assert is_query_canceled(DBAPIError(DriverError(sqlstate))) is False
        assert is_query_canceled(DriverError(sqlstate)) is False
        assert is_query_canceled(DBAPIError(Psycopg2Error(sqlstate))) is False

    def test_a_plain_exception_is_refused(self):
        assert is_query_canceled(ValueError("nope")) is False
        assert is_query_canceled(RuntimeError("nope")) is False

    def test_asyncio_cancellation_is_refused(self):
        """Not a database event. Containing it would keep work alive that the
        event loop is tearing down."""
        assert is_query_canceled(asyncio.CancelledError()) is False

    def test_a_cancellation_carrying_a_57014_is_still_refused(self):
        """The guard that actually earns its line. asyncpg cancels the running
        statement when its task is cancelled, so a ``CancelledError`` routinely
        arrives with a real 57014 in ``__context__``. Following the chain here
        would report a client hang-up as a database timeout and answer a
        degraded 200 to a request nobody is listening to any more."""
        try:
            try:
                raise QueryCanceledError("cancelled by the client disconnect")
            except QueryCanceledError:
                raise asyncio.CancelledError()
        except asyncio.CancelledError as cancelled:
            assert isinstance(cancelled.__context__, QueryCanceledError)
            assert is_query_canceled(cancelled) is False

    def test_a_non_string_sqlstate_is_refused(self):
        """A mock or a driver returning an int must not be coerced into a
        match — ``57014 == "57014"`` is False and that is the intended read."""
        weird = DriverError("x")
        weird.sqlstate = 57014
        assert is_query_canceled(DBAPIError(weird)) is False

    def test_a_message_that_merely_mentions_the_timeout_is_refused(self):
        """Message sniffing is what this predicate replaced. A log line, a
        wrapped string, or a health-check body that quotes the phrase must not
        trip it."""
        assert is_query_canceled(
            RuntimeError("canceling statement due to statement timeout")
        ) is False

    def test_a_self_referential_context_cycle_terminates(self):
        a = RuntimeError("a")
        b = RuntimeError("b")
        a.__context__ = b
        b.__context__ = a
        assert is_query_canceled(a) is False

    def test_the_chain_walk_is_depth_bounded_and_that_is_deliberate(self):
        """Documented limit, written here rather than left to be discovered: a
        57014 buried deeper than the bound is NOT found. Real wrapping is one
        or two links; an unbounded walk on a pathological chain is worse than a
        missed degrade, because the missed degrade is still a visible 500."""
        from app.utils.db_cancellation import _MAX_CHAIN_DEPTH

        deep: BaseException = QueryCanceledError("bottom")
        for _ in range(_MAX_CHAIN_DEPTH + 2):
            deep = DBAPIError(deep)
        assert is_query_canceled(deep) is False

        shallow: BaseException = QueryCanceledError("bottom")
        for _ in range(_MAX_CHAIN_DEPTH - 1):
            shallow = DBAPIError(shallow)
        assert is_query_canceled(shallow) is True


# ---------------------------------------------------------------------------
# The reason vocabulary
# ---------------------------------------------------------------------------
class TestFailureReasons:
    def test_every_declared_failure_reason_has_a_phrase(self):
        """The landmine: adding a third way to fail without giving it a phrase
        makes the 503 body say 'could not be built' with no cause, and nobody
        would notice until an operator read one."""
        declared = {GRID_FAILURE_TIMEOUT, GRID_FAILURE_DB_CANCELED}
        assert declared <= set(_GRID_FAILURE_PHRASE)
        for reason in declared:
            assert _GRID_FAILURE_PHRASE[reason].strip()

    def test_the_two_reasons_are_distinct(self):
        """Same shape, different cause. The Grid Sentinel prints
        ``degraded_reason`` verbatim; collapsing them would send an operator
        looking at the route's wall for a database problem."""
        assert GRID_FAILURE_TIMEOUT != GRID_FAILURE_DB_CANCELED

    @pytest.mark.asyncio
    async def test_an_unknown_reason_still_produces_a_503_not_a_crash(self):
        rc = _redis_mock({})
        with patch("app.tasks.redis_state.get_async_redis_client", return_value=rc):
            with pytest.raises(HTTPException) as exc:
                await _serve_grid_degraded("mlb", "k", True, "some_future_reason")
        assert exc.value.status_code == 503
        assert "degraded" in str(exc.value.detail).lower()


# ---------------------------------------------------------------------------
# The endpoint
# ---------------------------------------------------------------------------
def _raising_build(exc: BaseException):
    """A build that fails the way the real one does — during the await, inside
    ``wait_for``, not at call time."""

    async def _build(*a, **kw):
        raise exc

    return _build


GOOD = {"teams": [{"name": "Eagles"}], "columns": [{"key": "championship"}]}
JUNK = {"teams": [], "columns": [], "error": "timeout"}


class TestDbCancelDegradation:
    @pytest.mark.asyncio
    async def test_db_cancel_after_a_cold_start_serves_last_good_as_degraded(self):
        """Both keys cold on entry, the live build is cancelled by the
        database, and the warm beat has since published a good grid."""
        rc = MagicMock()
        rc.get = AsyncMock(side_effect=[None, None, json.dumps(GOOD)])
        rc.set = AsyncMock()
        rc.aclose = AsyncMock()

        with patch("app.tasks.redis_state.get_async_redis_client", return_value=rc), \
             patch("app.routes.playoffs.get_playoff_grid",
                   side_effect=_raising_build(_cancel_error())):
            result = await get_playoff_grid_cached("nfl", None, 10, False, MagicMock())

        assert result["degraded"] is True
        assert result["degraded_reason"] == GRID_FAILURE_DB_CANCELED
        assert result["stale"] is True
        assert result["teams"] == GOOD["teams"]

    @pytest.mark.asyncio
    async def test_db_cancel_without_last_good_raises_503_not_500(self):
        """The headline. Production returned a bare 500 here."""
        rc = _redis_mock({})
        with patch("app.tasks.redis_state.get_async_redis_client", return_value=rc), \
             patch("app.routes.playoffs.get_playoff_grid",
                   side_effect=_raising_build(_cancel_error())):
            with pytest.raises(HTTPException) as exc:
                await get_playoff_grid_cached("nfl", None, 10, False, MagicMock())

        assert exc.value.status_code == 503
        assert "degraded" in str(exc.value.detail).lower()

    @pytest.mark.asyncio
    async def test_db_cancel_never_launders_an_unusable_last_good_into_a_200(self):
        """#1484's rule, re-proved through the new door: an empty grid or a
        cached timeout envelope is not a fallback."""
        rc = MagicMock()
        rc.get = AsyncMock(side_effect=[None, json.dumps(JUNK), json.dumps(JUNK)])
        rc.set = AsyncMock()
        rc.aclose = AsyncMock()

        with patch("app.tasks.redis_state.get_async_redis_client", return_value=rc), \
             patch("app.routes.playoffs.get_playoff_grid",
                   side_effect=_raising_build(_cancel_error())):
            with pytest.raises(HTTPException) as exc:
                await get_playoff_grid_cached("nfl", None, 10, False, MagicMock())

        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_a_non_cache_eligible_request_still_degrades(self):
        """``?debug=true`` has no cache key, so there is no last-good to find —
        it must still be a 503 and never a 500."""
        rc = _redis_mock({})
        with patch("app.tasks.redis_state.get_async_redis_client", return_value=rc), \
             patch("app.routes.playoffs.get_playoff_grid",
                   side_effect=_raising_build(_cancel_error())):
            with pytest.raises(HTTPException) as exc:
                await get_playoff_grid_cached("nfl", None, 10, True, MagicMock())

        assert exc.value.status_code == 503
        assert rc.get.await_count == 0, (
            "a non-cache-eligible request must not consult Redis for last-good"
        )


class TestTheRefusal:
    """The load-bearing half. Containment that cannot say no is a catch-all."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("err", [
        DBAPIError(DriverError("42601")),        # syntax error in our own SQL
        DBAPIError(DriverError("42703")),        # undefined column
        DBAPIError(DriverError("08006")),        # connection failure
        DBAPIError(DriverError("53300")),        # too many connections
        DriverError("57P01"),                    # admin shutdown, same class 57
        ValueError("a plain bug in the builder"),
        KeyError("league config"),
    ])
    async def test_a_real_error_still_propagates(self, err):
        rc = _redis_mock({})
        with patch("app.tasks.redis_state.get_async_redis_client", return_value=rc), \
             patch("app.routes.playoffs.get_playoff_grid",
                   side_effect=_raising_build(err)):
            with pytest.raises(type(err)):
                await get_playoff_grid_cached("nfl", None, 10, False, MagicMock())

    @pytest.mark.asyncio
    async def test_a_real_error_is_never_converted_to_an_http_error(self):
        """Stated separately from the propagation test because the failure mode
        it guards is specific: a 503 (or worse, a 200 with a stale grid) about a
        query bug hides the bug behind a retry banner."""
        # Both keys cold on entry — so the request really does build — but a
        # perfectly good last-good is sitting there by the time it fails. The
        # containment must NOT reach for it.
        rc = MagicMock()
        rc.get = AsyncMock(side_effect=[None, None, json.dumps(GOOD)])
        rc.set = AsyncMock()
        rc.aclose = AsyncMock()
        with patch("app.tasks.redis_state.get_async_redis_client", return_value=rc), \
             patch("app.routes.playoffs.get_playoff_grid",
                   side_effect=_raising_build(DBAPIError(DriverError("42601")))):
            with pytest.raises(DBAPIError):
                await get_playoff_grid_cached("nfl", None, 10, False, MagicMock())
        assert rc.get.await_count == 2, (
            "the refusal must not consult the last-good key at all"
        )

    @pytest.mark.asyncio
    async def test_asyncio_cancellation_propagates(self):
        rc = _redis_mock({})
        with patch("app.tasks.redis_state.get_async_redis_client", return_value=rc), \
             patch("app.routes.playoffs.get_playoff_grid",
                   side_effect=_raising_build(asyncio.CancelledError())):
            with pytest.raises(asyncio.CancelledError):
                await get_playoff_grid_cached("nfl", None, 10, False, MagicMock())


class TestShapeEquivalence:
    """The two failures are indistinguishable to a user, so they must be
    indistinguishable to a consumer. Asserted by comparing the two paths to
    EACH OTHER — two copied literal assertions would drift together silently."""

    async def _run(self, exc, stale_values):
        rc = MagicMock()
        rc.get = AsyncMock(side_effect=stale_values)
        rc.set = AsyncMock()
        rc.aclose = AsyncMock()
        with patch("app.tasks.redis_state.get_async_redis_client", return_value=rc), \
             patch("app.routes.playoffs.get_playoff_grid",
                   side_effect=_raising_build(exc)):
            return await get_playoff_grid_cached("nfl", None, 10, False, MagicMock())

    @pytest.mark.asyncio
    async def test_the_served_payloads_have_identical_keys(self):
        cold = [None, None, json.dumps(GOOD)]
        wall = await self._run(asyncio.TimeoutError(), list(cold))
        cancel = await self._run(_cancel_error(), list(cold))

        assert set(wall) == set(cancel)
        assert wall["degraded"] is cancel["degraded"] is True
        assert wall["stale"] is cancel["stale"] is True
        assert wall["teams"] == cancel["teams"]
        # The one field that SHOULD differ, and the only one.
        differing = {k for k in wall if wall[k] != cancel[k]}
        assert differing == {"degraded_reason", "stale_reason"}

    @pytest.mark.asyncio
    async def test_both_empty_handed_paths_raise_the_same_status(self):
        empty = [None, None, None]
        statuses = []
        for exc in (asyncio.TimeoutError(), _cancel_error()):
            with pytest.raises(HTTPException) as caught:
                await self._run(exc, list(empty))
            statuses.append(caught.value.status_code)
            assert "degraded state, not an empty league" in str(caught.value.detail)
        assert statuses[0] == statuses[1] == 503


class TestHealthyPathUnmoved:
    """Adjacent direction (gotcha #43): the new ``except`` must not change any
    request that succeeds."""

    @pytest.mark.asyncio
    async def test_a_fresh_hit_is_untouched(self):
        rc = _redis_mock({"bainluck:category:playoffs:nba": json.dumps(GOOD)})
        with patch("app.tasks.redis_state.get_async_redis_client", return_value=rc):
            result = await get_playoff_grid_cached("nba", None, 10, False, MagicMock())
        assert result == GOOD
        assert "degraded" not in result

    @pytest.mark.asyncio
    async def test_a_successful_build_still_writes_both_cache_keys(self):
        rc = _redis_mock({})
        built = {"teams": [{"name": "Astros"}], "columns": []}

        async def _build(*a, **kw):
            return built

        with patch("app.tasks.redis_state.get_async_redis_client", return_value=rc), \
             patch("app.routes.playoffs.get_playoff_grid", side_effect=_build):
            result = await get_playoff_grid_cached("mlb", None, 10, False, MagicMock())

        assert result == built
        written = {call.args[0] for call in rc.set.await_args_list}
        assert written == {
            "bainluck:category:playoffs:mlb",
            "bainluck:category:playoffs:mlb:stale",
        }
