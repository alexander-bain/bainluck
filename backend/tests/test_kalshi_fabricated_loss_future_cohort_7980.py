"""The future-dated cohort selector on the fabricated-loss drain (#7980).

WHAT WAS BROKEN, AND WHY IT WAS NOT A BUG IN ANY LINE OF CODE
-------------------------------------------------------------
``_WORK_SQL`` walks ``ORDER BY fm.resolution_date ASC`` inside a floor of
``NOW() - PROVABLY_PURGED_AGE_DAYS``. That floor admits every FUTURE-dated
market, and the sort puts all of them behind every past-dated row. CAL-P057
measured the consequence on 2026-08-14 — 3,913 Kalshi markets, ~48% of the
backlog, behind ~2,887 past-dated ones — wrote it into the comment above the
query, and deliberately left it: "changing the sort is a design decision for the
attended pass", because this rail's correctness rests on its sort and that sort
had already produced three separate ordering traps.

#7980 is what the stranding costs a reader. ``/futures/108335`` ("Will Zelenskyy
and Putin speak?") shows a hero of 34% above a chart that plunges to 0%, because
two legs resolving in 2029 carry ``is_winner=false`` / ``api_settlement`` and the
settled-loser freeze faithfully draws the terminal zero. Those legs are in the
stranded cohort BY CONSTRUCTION: a market that has not resolved is the only kind
that can be both falsely graded and still trading.

Measured against the shipping rail 2026-09-22, ``limit=10&min_harm=0.20``
returned 10 of 10 markets at ``unexplained_absence``, 86.0 days old — so the walk
ahead of the stranded cohort is spending its venue budget on rows the venue can
no longer answer.

WHAT THESE TESTS PIN
--------------------
The fix follows CAL-P1124 arm B: a COHORT SELECTOR, not a re-sort. So the tests
assert both halves of that claim — that the cohort reaches the statement, and
that nothing about the ordering moved — plus CAL-P1125's completion-key rule,
which the module comment predicted a third selector would have to satisfy.
"""

import time
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.tasks import repair_kalshi_fabricated_loss as rail
from app.utils.kalshi_fabricated_loss import (
    FUTURE_DATE_COHORT_SQL,
    RETENTION_BAND_SQL,
)


#: The instant the fake database's clock reads, matching the band-paging suite's
#: constant for the reason CAL-P1018 gives: the band's origin must not be
#: whatever the clock said when the statement happened to run.
_DB_NOW = datetime(2026, 9, 5, 18, 0, tzinfo=timezone.utc)


class _Session:
    """Answers the work selection and the band anchor, recording every param."""

    def __init__(self, rows, now=_DB_NOW):
        self._rows = rows
        self._now = now
        self.work_params = None

    async def execute(self, statement, params=None):
        sql = str(statement)
        if "statement_timeout" in sql:
            return SimpleNamespace(all=lambda: [])
        if sql == rail._BAND_ANCHOR_SQL:
            return SimpleNamespace(scalar_one=lambda: self._now)
        if "FROM futures_outcomes" in sql and "market_id = :mid" in sql:
            return SimpleNamespace(all=lambda: [])
        self.work_params = dict(params or {})
        return SimpleNamespace(all=lambda: list(self._rows))

    async def rollback(self):  # pragma: no cover - only on a select failure
        pass


async def _dry_run(monkeypatch, *, rows=(), future_only=None, min_harm=None, band=None):
    import app.services.kalshi_api as kalshi_api

    class _Silent:
        async def get_markets(self, *, event_ticker=None, **_):
            return [], None

        async def close(self):
            pass

    monkeypatch.setattr(kalshi_api, "KalshiAPIService", _Silent)

    async def _no_bank(plan):
        return True, "test: not banked"

    monkeypatch.setattr(rail, "_save_plan", _no_bank)

    session = _Session(list(rows))
    result = await rail._dry_run(
        session,
        40,
        None,
        None,
        None,
        time.monotonic(),
        band=band,
        min_harm=min_harm,
        future_only=future_only,
    )
    return result, session


class TestTheCohortReachesTheStatement:
    """A parser that does not reach the query is decoration."""

    @pytest.mark.asyncio
    async def test_the_flag_is_bound_to_the_work_selection(self, monkeypatch):
        _, session = await _dry_run(monkeypatch, future_only="true")
        assert session.work_params["future_only"] is True

    @pytest.mark.asyncio
    async def test_an_omitted_flag_binds_null_and_not_false(self, monkeypatch):
        """``NULL`` and ``False`` walk the same population here, but only ``NULL``
        says "not asked". The bind has to carry that distinction or the echo
        below is reporting a value the query never saw."""
        _, session = await _dry_run(monkeypatch)
        assert session.work_params["future_only"] is None

    @pytest.mark.asyncio
    async def test_explicit_false_binds_false(self, monkeypatch):
        _, session = await _dry_run(monkeypatch, future_only="false")
        assert session.work_params["future_only"] is False

    def test_the_predicate_is_in_the_work_sql(self):
        assert FUTURE_DATE_COHORT_SQL.strip() in " ".join(rail._WORK_SQL.split(" "))

    def test_the_predicate_is_null_transparent(self):
        """gotcha #53. An omitted selector must degrade to the WHOLE population;
        a bare ``= TRUE`` against a NULL bind excludes every row, and an empty
        page on this rail reads as "the cohort is drained"."""
        assert "IS NOT TRUE" in FUTURE_DATE_COHORT_SQL

    def test_the_parameter_is_cast_at_its_only_occurrence(self):
        """The ``:sport`` lesson (test_kalshi_fabricated_loss_bind_contract_pg):
        asyncpg prepares with no parameter types and the FIRST occurrence fixes
        them, so an untyped occurrence kills the prepare before a row is read."""
        assert "CAST(:future_only AS boolean)" in FUTURE_DATE_COHORT_SQL
        assert FUTURE_DATE_COHORT_SQL.count(":future_only") == 1

    def test_the_cohort_and_the_census_band_cannot_drift(self):
        """The census bands this same population as ``future_date`` on its own
        copy of the expression. If the two ever disagree, the walk and the count
        of what the walk has left to do come to mean different things."""
        assert "fm.resolution_date > NOW()" in FUTURE_DATE_COHORT_SQL
        assert "fm.resolution_date > NOW()" in RETENTION_BAND_SQL


class TestTheSortDidNotMove:
    """CAL-P057 declined to re-sort, and this change accepts that judgment. The
    keyset names a POSITION in an order, so a re-sort would invalidate every
    banked cursor — these assertions are what make "selector, not re-sort" a
    checked claim instead of a sentence in a commit message."""

    def test_the_two_order_by_clauses_are_unchanged(self):
        assert "ORDER BY fm.resolution_date ASC, fm.id ASC" in rail._WORK_SQL
        assert "ORDER BY s.resolution_date ASC, s.id ASC" in rail._WORK_SQL

    def test_the_cohort_is_a_where_predicate_and_not_part_of_the_sort(self):
        """It has to sit in the inner WHERE, ahead of the inner ORDER BY — the
        same place ``?band=`` and ``?sport=`` sit."""
        work = rail._WORK_SQL
        assert work.index(":future_only") < work.index(
            "ORDER BY fm.resolution_date ASC"
        )


class TestTheParserRefusesRatherThanGuessing:
    @pytest.mark.parametrize("word,expected", list(rail._FUTURE_ONLY_WORDS.items()))
    def test_the_accepted_spellings(self, word, expected):
        assert rail.parse_future_only(word) is expected
        assert rail.parse_future_only(word.upper()) is expected

    def test_omitted_is_none_and_not_false(self):
        assert rail.parse_future_only(None) is None

    @pytest.mark.parametrize("bad", ["ture", "t", "", "  ", "on", "1.0", "future"])
    def test_an_unknown_value_is_refused_by_name(self, bad):
        """The two readings of this flag differ by the entire population. A typo
        read as false runs the DEFAULT walk — the one whose first page was 10 of
        10 unrepairable rows — while the operator's scrollback says they targeted
        the future-dated cohort, and they would then read that page as evidence
        the cohort was empty."""
        with pytest.raises(rail.BandRefused) as e:
            rail.parse_future_only(bad)
        assert e.value.refused == "FUTURE_ONLY_UNPARSEABLE"

    @pytest.mark.asyncio
    async def test_a_refusal_stops_the_run_and_never_selects(self, monkeypatch):
        result, session = await _dry_run(monkeypatch, future_only="ture")
        assert result["measured"] is False
        assert result["refused"] == "FUTURE_ONLY_UNPARSEABLE"
        assert session.work_params is None, "a refused run must select nothing"


class TestTheApplyRefusesTheCohort:
    @pytest.mark.asyncio
    async def test_future_only_on_apply_is_refused_by_name(self, monkeypatch):
        """An apply executes the reviewed plan BY LEG ID and selects nothing, so
        a cohort here narrows nothing while appearing to — and this is the most
        reassuring of the three to read in scrollback, because the cohort it
        names is the one whose rows are still answerable."""
        result = await rail.repair(
            _Session([]), apply=True, plan_hash="deadbeef", future_only="true"
        )
        assert result["refused"] == "FUTURE_ONLY_ON_APPLY"
        assert result["presented_future_only"] == "true"


class TestTheCompletionKeysScopeToTheCohort:
    """CAL-P1125 (CERT-2705) fixed exactly this for ``?min_harm=`` and wrote that
    "a third selector is one list entry, not another silent re-run of this bug."
    This is the third selector, so the whole matrix is asserted — a fix that made
    the new flag honest while breaking a pair would be the same bug again."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "band,min_harm,future_only,scope,population_exhausted",
        [
            (None, None, None, "population", True),
            (None, None, "true", "future_only", False),
            (None, 0.9, "true", "min_harm+future_only", False),
            ("47-67", None, "true", "band+future_only", False),
            ("47-67", 0.9, "true", "band+min_harm+future_only", False),
            # The one that must NOT narrow: an explicit false walks the whole
            # population, so a page that empties under it has genuinely
            # exhausted that population and must be allowed to say so.
            (None, None, "false", "population", True),
        ],
    )
    async def test_an_empty_page_scopes_its_claim(
        self, monkeypatch, band, min_harm, future_only, scope, population_exhausted
    ):
        result, _ = await _dry_run(
            monkeypatch, rows=[], band=band, min_harm=min_harm, future_only=future_only
        )
        label = f"band={band!r} min_harm={min_harm!r} future_only={future_only!r}"
        assert result["exhausted"] is True, label
        assert result["exhausted_scope"] == scope, label
        assert result["population_exhausted"] is population_exhausted, label

        # The payload must not deny itself: `future_only_means` promises that
        # exhaustion under the cohort says nothing about the rows beneath it.
        if result["window"]["future_only_means"] is not None:
            assert result["population_exhausted"] is False, label

    @pytest.mark.asyncio
    async def test_the_cohort_is_echoed_parsed(self, monkeypatch):
        """An operator reading their own string back learns nothing about
        whether it took effect (#3257's rule for ``?band=``)."""
        result, _ = await _dry_run(monkeypatch, future_only="yes")
        assert result["window"]["future_only"] is True
        assert result["window"]["future_only_means"] is not None

        result, _ = await _dry_run(monkeypatch)
        assert result["window"]["future_only"] is None
        assert result["window"]["future_only_means"] is None
