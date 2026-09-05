"""CAL-P1015 (#3257) — the drain pages to where the venue still answers.

THE DEFECT, measured against production 2026-09-05 by walking the sort with the
rail's own keyset at chosen ages (``limit=10``, which draws no 429s, so these
reads are uncontaminated — see #3262):

    age 86d -> 10 unexplained_absence,  0 answered,  0 markets writable
    age 70d -> 10 unexplained_absence,  0 answered,  0 markets writable
    age 66d ->  5 unexplained_absence,  5 answered,  4 markets writable
    age 54d ->  0 unexplained_absence, 10 answered,  4 markets writable

**The venue answers nothing at all between 70 and 86 days.** The sort is
oldest-first within the retention floor, so the drain starts there: 597 markets
of measured zero yield — ~15 pages at ``APPLY_MARKET_CAP``, ~600 venue lookups —
sit in front of the 552-market answerable at-risk tail, which is the only cohort
with a deadline. Third payout of gotcha #41 in this one ``ORDER BY``.

The instrument is a PAGING SELECTOR, not a second floor. ``?band=47-67`` names
which slice of the existing sort to walk first. It excludes nothing, changes no
verdict, and does not retune ``kalshi_retention``'s measured constants — that
module carries a 68-day counter-specimen and deliberately refused to move 74 for
it, and a floor re-measured on THIS population would destroy that record while
looking equally well-founded.

What these tests guard, in one line each:

* the two numbers are AGES and the parser refuses every way of getting that
  wrong, rather than paging somewhere the operator did not ask for;
* the band may not reach past the retention floor, because the population ends
  there and an empty page would read as "nothing to repair";
* **a banded page never reports the POPULATION exhausted** — one boolean saying a
  20-day slice was the whole thing is gotcha #53's shape one level up;
* ``apply=true`` refuses a band, because the apply selects nothing and a silent
  no-op reads like the scope of the write.

The row-level direction proof — that ``max`` is the OLDER edge — lives against
real Postgres in ``tests/integration/test_kalshi_fabricated_loss_bind_contract_pg.py``:
swapping the two binds still returns a plausible page here, so only rows can hold
it.
"""

from __future__ import annotations

import json
import pathlib
import time
from types import SimpleNamespace

import pytest

from app.tasks import repair_kalshi_fabricated_loss as rail
from app.utils.kalshi_retention import PROVABLY_PURGED_AGE_DAYS

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# The parser
# ---------------------------------------------------------------------------


class TestTheTwoNumbersAreAges:
    def test_no_band_is_none_not_a_default_range(self):
        """A default band would silently change every existing caller's page."""
        assert rail.parse_band(None) is None

    def test_the_at_risk_tail_parses_to_its_two_ages(self):
        assert rail.parse_band("47-67") == (47, 67)

    def test_whitespace_an_operator_pastes_is_tolerated(self):
        assert rail.parse_band(" 47 - 67 ") == (47, 67)

    @pytest.mark.parametrize(
        "band",
        ["", "47", "47-", "-67", "47..67", "47,67", "forty-seven", "47-67-70", "47.5-67"],
    )
    def test_anything_that_is_not_two_whole_ages_is_refused_by_name(self, band):
        """Refused, never coerced. A band read as None pages the dead head while
        the operator's scrollback says they asked for the tail."""
        with pytest.raises(rail.BandRefused) as e:
            rail.parse_band(band)
        assert e.value.refused == "BAND_UNPARSEABLE"

    def test_an_inverted_pair_is_refused_rather_than_sorted_for_the_operator(self):
        """``67-47`` reads as a range in English and would select NOTHING.

        Silently swapping it would be worse than refusing: the operator learns
        the wrong thing about which number is which, and the next band they write
        by hand — on a rail with a deadline — is a guess.
        """
        with pytest.raises(rail.BandRefused) as e:
            rail.parse_band("67-47")
        assert e.value.refused == "BAND_INVERTED"

    def test_equal_edges_are_refused_because_an_empty_band_is_not_a_selection(self):
        with pytest.raises(rail.BandRefused) as e:
            rail.parse_band("60-60")
        assert e.value.refused == "BAND_INVERTED"

    def test_a_band_past_the_retention_floor_is_refused_by_name(self):
        """The population ends at PROVABLY_PURGED_AGE_DAYS.

        A band reaching over it selects rows the work SQL never had, so it
        returns an empty page — which on this rail reads as "nothing left to
        repair". That is the exact false-completion shape #3262 just fixed one
        level down.
        """
        with pytest.raises(rail.BandRefused) as e:
            rail.parse_band(f"10-{PROVABLY_PURGED_AGE_DAYS + 1}")
        assert e.value.refused == "BAND_ABOVE_RETENTION_FLOOR"

    def test_a_band_exactly_at_the_floor_is_allowed(self):
        """The floor is inclusive in the work SQL, so the band matches it."""
        assert rail.parse_band(f"70-{PROVABLY_PURGED_AGE_DAYS}") == (
            70,
            PROVABLY_PURGED_AGE_DAYS,
        )

    def test_the_refusal_names_the_floor_it_is_defending(self):
        """An operator who cannot see WHICH number stopped them retries blind."""
        with pytest.raises(rail.BandRefused) as e:
            rail.parse_band("10-200")
        assert str(PROVABLY_PURGED_AGE_DAYS) in e.value.reason

    def test_the_floor_is_read_from_the_measurement_not_typed_here(self):
        """A band that hard-coded 86 would silently diverge if the measurement
        moved — which is the whole reason a floor was the wrong instrument."""
        import ast
        import inspect

        tree = ast.parse(inspect.getsource(rail.parse_band).lstrip())
        fn = tree.body[0]
        # The prose cites the measured 86; the CODE must not. Drop the docstring
        # and read what executes.
        body = fn.body[1:] if ast.get_docstring(fn) else fn.body
        code = "\n".join(ast.unparse(node) for node in body)

        assert "PROVABLY_PURGED_AGE_DAYS" in code
        assert "86" not in code, "the floor must not be a literal in the parser"


# ---------------------------------------------------------------------------
# A driver for the SHIPPING `_dry_run`, so the response assertions below are
# about the rail and not about a model of it. Same rig as #3262's guard.
# ---------------------------------------------------------------------------


def _work_row(order: int, ticker: str, age_days: float):
    from datetime import datetime, timedelta, timezone

    return SimpleNamespace(
        market_id=9_600_000 - order,
        event_ticker=ticker,
        mutex=True,
        sport="soccer",
        our_status="open",
        resolution_date=datetime(2026, 7, 1, tzinfo=timezone.utc)
        + timedelta(days=order),
        age_days=age_days,
    )


class _Session:
    """Answers `_WORK_SQL` and `_legs`, and records the params it was given."""

    def __init__(self, rows, legs_by_market):
        self._rows = rows
        self._legs = legs_by_market
        self.work_params: dict | None = None

    async def execute(self, statement, params=None):
        sql = str(statement)
        if "statement_timeout" in sql:
            return SimpleNamespace(all=lambda: [])
        if "FROM futures_outcomes" in sql and "market_id = :mid" in sql:
            legs = self._legs.get(params["mid"], [])
            return SimpleNamespace(all=lambda: legs)
        self.work_params = dict(params or {})
        return SimpleNamespace(all=lambda: list(self._rows))

    async def rollback(self):  # pragma: no cover - only on a select failure
        pass


async def _dry_run(monkeypatch, *, rows, band=None, limit=40, cursor=None):
    """Run the shipping `_dry_run` against a venue that answers nothing."""
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

    session = _Session(rows, {})
    after_date, after_id = cursor if cursor else (None, None)
    result = await rail._dry_run(
        session, limit, after_id, after_date, None, time.monotonic(), band=band
    )
    return result, session


class TestTheBandReachesTheQuery:
    @pytest.mark.asyncio
    async def test_the_two_ages_are_bound_to_the_work_selection(self, monkeypatch):
        """The parse is worthless if it does not reach the statement."""
        result, session = await _dry_run(
            monkeypatch, rows=[_work_row(0, "KX-A", 60.0)], band="47-67"
        )

        assert result["window"]["band"] == {
            "min_age_days": 47,
            "max_age_days": 67,
            "walks": "oldest-first inside the band, from the max edge",
        }
        assert session.work_params["band_min_age"] == 47
        assert session.work_params["band_max_age"] == 67

    @pytest.mark.asyncio
    async def test_no_band_binds_two_nulls_not_a_range(self, monkeypatch):
        """The no-band path is what every existing caller takes."""
        result, session = await _dry_run(
            monkeypatch, rows=[_work_row(0, "KX-A", 60.0)], band=None
        )

        assert result["window"]["band"] is None
        assert session.work_params["band_min_age"] is None
        assert session.work_params["band_max_age"] is None

    @pytest.mark.asyncio
    async def test_a_refused_band_never_reaches_the_database(self, monkeypatch):
        """A refusal that still ran the query would have paged the dead head and
        then told the operator it refused."""
        result, session = await _dry_run(
            monkeypatch, rows=[_work_row(0, "KX-A", 60.0)], band="67-47"
        )

        assert result["measured"] is False
        assert result["refused"] == "BAND_INVERTED"
        assert result["presented_band"] == "67-47"
        assert session.work_params is None, "the work selection must not have run"

    @pytest.mark.asyncio
    async def test_the_band_is_echoed_parsed_rather_than_as_presented(
        self, monkeypatch
    ):
        """Reading your own string back proves nothing about whether it took."""
        result, _ = await _dry_run(
            monkeypatch, rows=[_work_row(0, "KX-A", 60.0)], band=" 47 - 67 "
        )

        assert result["window"]["band"]["min_age_days"] == 47


class TestABandedPageIsNeverAFinishedDrain:
    """The completion claim. This is the class guard, and it is gotcha #53."""

    @pytest.mark.asyncio
    async def test_a_short_banded_page_does_not_report_the_population_exhausted(
        self, monkeypatch
    ):
        """One row against a window of 40: the BAND is out of rows, and the
        population is not, and the response must not conflate them."""
        result, _ = await _dry_run(
            monkeypatch, rows=[_work_row(0, "KX-A", 60.0)], band="47-67", limit=40
        )

        assert result["exhausted"] is True, "the band itself did run out"
        assert result["exhausted_scope"] == "band"
        assert result["population_exhausted"] is False
        assert "EXCLUDED nothing" in result["band_note"]

    @pytest.mark.asyncio
    async def test_an_unbanded_short_page_still_reports_the_population_exhausted(
        self, monkeypatch
    ):
        """The pre-band meaning must survive intact for the callers that had it."""
        result, _ = await _dry_run(
            monkeypatch, rows=[_work_row(0, "KX-A", 60.0)], band=None, limit=40
        )

        assert result["exhausted"] is True
        assert result["exhausted_scope"] == "population"
        assert result["population_exhausted"] is True
        assert result["band_note"] is None

    @pytest.mark.asyncio
    async def test_a_full_banded_page_is_exhausted_in_neither_sense(
        self, monkeypatch
    ):
        rows = [_work_row(i, f"KX-{i}", 60.0) for i in range(3)]

        result, _ = await _dry_run(monkeypatch, rows=rows, band="47-67", limit=3)

        assert result["exhausted"] is False
        assert result["population_exhausted"] is False

    @pytest.mark.asyncio
    async def test_population_exhausted_can_never_be_true_under_a_band(
        self, monkeypatch
    ):
        """Whatever the page did, a band cannot prove anything about the rows
        outside it. Asserted over both page shapes so a future edit cannot make
        one branch honest and the other not."""
        for rows, limit in (
            ([_work_row(0, "KX-A", 60.0)], 40),
            ([_work_row(i, f"KX-{i}", 60.0) for i in range(3)], 3),
            ([], 40),
        ):
            result, _ = await _dry_run(
                monkeypatch, rows=rows, band="47-67", limit=limit
            )
            assert result["population_exhausted"] is False

    @pytest.mark.asyncio
    async def test_the_band_travels_into_the_plan_context(self, monkeypatch):
        """The plan is what an apply executes and what an auditor reads back; a
        plan that cannot say which slice produced it is not a record."""
        result, _ = await _dry_run(
            monkeypatch, rows=[_work_row(0, "KX-A", 60.0)], band="47-67"
        )

        assert result["plan_artifact"]["context"]["band"] == "47-67"


class TestTheApplyRefusesABand:
    @pytest.mark.asyncio
    async def test_apply_with_a_band_is_refused_by_name(self):
        """The apply re-selects nothing — it writes the leg ids the plan named.

        Accepting a band here would narrow nothing while appearing to, and the
        operator's record of the write would claim a scope it never had.
        """
        result = await rail.repair(
            None, apply=True, band="47-67", plan_hash="deadbeef"
        )

        assert result["measured"] is False
        assert result["refused"] == "BAND_ON_APPLY"
        assert result["presented_band"] == "47-67"

    @pytest.mark.asyncio
    async def test_the_refusal_fires_before_the_plan_is_even_loaded(self, monkeypatch):
        """Passing `None` as the session above already proves it, but hold it
        explicitly: a refusal that ran after a plan load would have taken the
        apply's obligation-ledger path on the way."""
        loaded = []

        async def _spy():
            loaded.append(True)
            return None, "spied"

        monkeypatch.setattr(rail, "_load_plan", _spy)

        await rail.repair(None, apply=True, band="47-67", plan_hash="deadbeef")

        assert loaded == [], "the plan must not be read on a refused band"


class TestTheRouteForwardsIt:
    def test_the_dispatcher_offers_band_to_repairs_that_declare_it(self):
        """Signature-gated forwarding: the param is useless if the dispatcher
        does not pass it, and this rail is the one that declares it."""
        import inspect

        from app.routes import admin_repairs

        assert "band" in inspect.signature(admin_repairs.run_repair).parameters
        assert '("band", band)' in inspect.getsource(admin_repairs.run_repair)
        assert "band" in inspect.signature(rail.repair).parameters

    def test_the_catalog_entry_documents_the_parameter(self):
        """`Accepts ?…` is the operator-facing contract for this rail, and an
        undocumented selector on an ATTENDED-ONLY rail is one nobody will use."""
        import inspect

        from app.routes import admin_repairs

        src = inspect.getsource(admin_repairs)
        entry = src[: src.index('"kalshi-fabricated-loss": (')]
        tail = entry[entry.rindex("CAL-P1014") :]
        assert "band=" in tail
