"""THE SOURCE-HEALTH FRESHNESS HALF ANSWERS, AND SAYS SO WHEN IT CANNOT. #4949.

═══ WHY ═══

`/api/admin/source-health` computes each source's status from two inputs: Redis task
bookkeeping, and a per-source DB freshness count. The second one had never run.

Measured on production 2026-09-17 16:2xZ (`db-query`, not recalled):

    SELECT COUNT(*) FROM events WHERE updated_at > NOW() - INTERVAL '6 hours'
      -> {"error":"query_failed","reason":"undefined_column"}

`events` carries `created_at`, `completed_at` and `ei_computed_at` — there is no mtime.
Three of the six queries named that column, and `odds_api` is the FIRST key in
`_SOURCE_TASKS`, so its raise aborted the shared session's transaction and the three
queries that WERE valid failed behind it. Run alone in the same minute, those three
answer 6198 / 5325 / 15.

Every failure landed in `except Exception: pass`. So on production that morning:

    "overall": "healthy",  "alerts": [],  and `items_updated_6h` absent from all nine

— a source whose task keeps reporting success while writing nothing reads healthy, which
is the one failure this endpoint exists to catch. Gotcha #53, pointing the reassuring way.

═══ WHAT THESE TESTS PIN ═══

`TestEverySqlNamesColumnsThatExist` is the guard for the CLASS, and it is the only one of
these that would have caught the original defect: the bug is a column name, and a unit
test with a mocked session passes on all six dead queries. It executes nothing — it reads
the SQL against `Base.metadata`, which is the schema.

The rest pin the two behaviours that made one dead query into six:

* one SAVEPOINT per query, so a failed statement cannot poison the checks after it;
* a check that could not run is reported as `error`, never as absence and never as `ok`
  — and it degrades `overall`, because "we cannot tell" printed as `healthy` IS the bug.

═══ WHAT MUST NOT CHANGE ═══

A source is listed in `_SOURCE_FRESHNESS_QUERIES` only if it writes a timestamped row
CONTINUOUSLY. `espn` and `statpal` were dropped rather than repointed: espn writes only
while games are in play (`espn_snapshots.captured_at` read 0 rows in a quiet hour) and
statpal's livescore writes carry no stamp at all. A query that reads 0 when nothing is
wrong would turn the alarm into noise — the same defect facing the other way — so those
two report `unmeasured` WITH THE REASON instead of a number nobody can act on.
"""

import re

import pytest

from app.models.models import Base
from app.routes import admin_source_health as route


# --- the schema guard -------------------------------------------------------

_TABLE_RE = re.compile(r"\bFROM\s+([a-z_][a-z0-9_]*)", re.IGNORECASE)
#: An identifier immediately left of a comparison is a column reference. That is
#: every column in these queries (`captured_at >`, `source =`, `updated_at >`),
#: and it is exactly where the defect lived.
_COLUMN_RE = re.compile(r"\b([a-z_][a-z0-9_]*)\s*(?:>=|<=|!=|>|<|=|\bIS\b)")


class TestEverySqlNamesColumnsThatExist:
    """The defect was a column name, so the assertion is against the schema."""

    @pytest.mark.parametrize("source", sorted(route._SOURCE_FRESHNESS_QUERIES))
    def test_the_table_and_every_compared_column_are_in_the_metadata(self, source):
        sql, _window = route._SOURCE_FRESHNESS_QUERIES[source]

        tables = _TABLE_RE.findall(sql)
        assert len(tables) == 1, f"{source}: expected one FROM, got {tables}"
        table = Base.metadata.tables.get(tables[0])
        assert table is not None, (
            f"{source}: table {tables[0]!r} is not in the schema — "
            f"this query can only ever raise"
        )

        columns = _COLUMN_RE.findall(sql)
        assert columns, f"{source}: no column comparison found — the parser is blind"
        for column in columns:
            assert column in table.c, (
                f"{source}: {tables[0]}.{column} does not exist. This is #4949: "
                f"a mocked-session unit test passes on this query, production does not."
            )

    def test_the_parser_would_catch_the_original_defect(self):
        """Non-vacuity: the #4949 query must fail the check above."""
        dead = "SELECT COUNT(*) FROM events WHERE updated_at > NOW() - INTERVAL '6 hours'"
        table = Base.metadata.tables[_TABLE_RE.findall(dead)[0]]
        assert "updated_at" in _COLUMN_RE.findall(dead)
        assert "updated_at" not in table.c

    def test_a_window_is_stated_for_every_query(self):
        """`items_updated_6h` was the key name for datagolf's 12-hour window."""
        for source, (sql, window) in route._SOURCE_FRESHNESS_QUERIES.items():
            assert isinstance(window, int) and window > 0, source
            assert f"INTERVAL '{window} hours'" in sql, (
                f"{source}: the stated window and the SQL's window disagree"
            )


# --- the runtime guards -----------------------------------------------------

_PLANTED_SECRET = "postgres://u:p4ssw0rd-do-not-publish@host/db"


class _Result:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


class _Savepoint:
    """What `AsyncSession.begin_nested()` buys: a rollback that un-poisons."""

    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if exc_type is not None:
            self._session.poisoned = False
            self._session.rollbacks += 1
        return False  # the caller's except still sees it


class _Session:
    """A session that behaves like Postgres in the one way that matters.

    A failed statement aborts the transaction, and every statement after it
    raises until something rolls back. Without a savepoint per query, one dead
    query is an outage of all the checks behind it — which is the defect.
    """

    def __init__(self, answers, *, savepoints=True):
        self.answers = answers
        self.savepoints = savepoints
        self.poisoned = False
        self.rollbacks = 0
        self.executed = []

    def begin_nested(self):
        if not self.savepoints:
            raise AssertionError("begin_nested() called with savepoints disabled")
        return _Savepoint(self)

    async def execute(self, clause):
        sql = " ".join(str(clause).split())
        self.executed.append(sql)
        if self.poisoned:
            raise RuntimeError("InFailedSqlTransactionError")
        for needle, answer in self.answers.items():
            if needle in sql:
                if isinstance(answer, Exception):
                    self.poisoned = True
                    raise answer
                return _Result(answer)
        return _Result(0)


@pytest.fixture
def wired(monkeypatch):
    """Bypass the admin gate and make every task report healthy."""
    monkeypatch.setattr(route, "_check_admin_secret", lambda *a, **k: None)

    import app.tasks.redis_state as redis_state

    monkeypatch.setattr(
        redis_state,
        "get_task_metrics",
        lambda _name: {
            "health": "healthy",
            "last_success_at": "2026-09-17T16:00:00+00:00",
            "failures_24h": 0,
            "consecutive_failures": 0,
        },
    )

    class _NoRedis:
        def get(self, _key):
            return None

    monkeypatch.setattr(redis_state, "get_redis_client", lambda: _NoRedis())


async def _call(session):
    return await route.source_health(request=None, secret="x", db=session)


_HEALTHY = {
    "odds_snapshots": 7279,
    "'kalshi'": 6198,
    "'polymarket'": 5325,
    "'datagolf'": 15,
}


class TestTheCheckActuallyRuns:
    @pytest.mark.asyncio
    async def test_every_listed_source_reports_its_count_and_window(self, wired):
        payload = await _call(_Session(dict(_HEALTHY)))

        for source in route._SOURCE_FRESHNESS_QUERIES:
            freshness = payload["sources"][source]["freshness"]
            assert freshness["status"] == "ok", source
            assert freshness["items"] > 0, source
            assert freshness["window_hours"] == route._SOURCE_FRESHNESS_QUERIES[source][1]

        assert payload["overall"] == "healthy"
        assert payload["alerts"] == []

    @pytest.mark.asyncio
    async def test_a_source_writing_nothing_is_stale_and_alerts(self, wired):
        answers = dict(_HEALTHY, **{"'kalshi'": 0})

        payload = await _call(_Session(answers))

        assert payload["sources"]["kalshi"]["status"] == "stale"
        assert payload["overall"] == "degraded"
        assert any("kalshi: stale" in a for a in payload["alerts"]), payload["alerts"]
        # The sources that DID write are untouched by their neighbour's silence.
        assert payload["sources"]["polymarket"]["status"] == "healthy"


class TestOneDeadQueryStaysOneDeadQuery:
    """The savepoint clause. This is what turned three defects into six."""

    @pytest.mark.asyncio
    async def test_the_checks_behind_a_failure_still_answer(self, wired):
        answers = dict(_HEALTHY, **{"odds_snapshots": RuntimeError("UndefinedColumnError")})

        session = _Session(answers)
        payload = await _call(session)

        assert payload["sources"]["odds_api"]["freshness"]["status"] == "error"
        for survivor in ("kalshi", "polymarket", "datagolf"):
            freshness = payload["sources"][survivor]["freshness"]
            assert freshness["status"] == "ok", (
                f"{survivor} failed behind odds_api — the savepoint is gone and "
                f"one bad query is an outage of the whole data half again"
            )
            assert freshness["items"] > 0
        assert session.rollbacks == 1


class TestAFailedCheckIsSaidOutLoud:
    @pytest.mark.asyncio
    async def test_it_is_error_not_absence_and_not_ok(self, wired):
        answers = dict(_HEALTHY, **{"odds_snapshots": RuntimeError("UndefinedColumnError")})

        payload = await _call(_Session(answers))
        freshness = payload["sources"]["odds_api"]["freshness"]

        assert freshness["status"] == "error"
        assert freshness["error"] == "RuntimeError"
        assert "items" not in freshness, "an errored check must not report a count"

    @pytest.mark.asyncio
    async def test_a_dark_data_half_degrades_the_overall(self, wired):
        answers = dict(_HEALTHY, **{"odds_snapshots": RuntimeError("UndefinedColumnError")})

        payload = await _call(_Session(answers))

        assert payload["overall"] == "degraded", (
            "every task reported healthy and the data half did not run: "
            "'healthy' here is #4949 verbatim"
        )
        assert any("freshness check did not run" in a for a in payload["alerts"])

    @pytest.mark.asyncio
    async def test_the_class_name_is_published_and_the_message_is_not(self, wired):
        """House rule (health.py:_error_label): the class name, never the message."""
        boom = RuntimeError(f"could not connect: {_PLANTED_SECRET}")
        assert _PLANTED_SECRET in str(boom)  # the guard is not vacuous

        payload = await _call(_Session(dict(_HEALTHY, **{"odds_snapshots": boom})))

        assert _PLANTED_SECRET not in repr(payload)
        assert payload["sources"]["odds_api"]["freshness"]["error"] == "RuntimeError"


class TestUnmeasuredIsItsOwnAnswer:
    @pytest.mark.asyncio
    async def test_the_two_dropped_sources_say_so_with_a_reason(self, wired):
        payload = await _call(_Session(dict(_HEALTHY)))

        for source in ("espn", "statpal"):
            freshness = payload["sources"][source]["freshness"]
            assert freshness["status"] == "unmeasured", source
            assert freshness["reason"], f"{source}: unmeasured with no reason is absence"
            assert "items" not in freshness
            # Unmeasured is not stale: we are not counting, so we cannot accuse.
            assert payload["sources"][source]["status"] == "healthy"

    def test_no_source_is_both_measured_and_unmeasured(self):
        overlap = set(route._SOURCE_FRESHNESS_QUERIES) & set(route._FRESHNESS_UNMEASURED)
        assert not overlap, overlap

    def test_every_source_that_lost_its_query_is_accounted_for(self):
        """The three `events.updated_at` sources: one repointed, two explained."""
        for source in ("odds_api", "espn", "statpal"):
            assert (
                source in route._SOURCE_FRESHNESS_QUERIES
                or source in route._FRESHNESS_UNMEASURED
            ), f"{source} lost its freshness check silently"
