"""#6211 — a failed DataGolf call may never be recorded as an absent tournament.

WHAT WENT WRONG
---------------
``_recover_datagolf_participation`` wrote ONE boolean,
``datagolf_recovery_residual``, from two unrelated events: DataGolf answering
"no such event", and any non-429 exception on our side. ``get_historical_results``
made it worse by folding 403 and ReadTimeout into the same ``[]`` a 404 returns.
``precompute_calibration``'s ``market_info`` drops a flagged market WHOLE, and its
comment said the residual "is expected to be ~0".

Measured on production 2026-09-15 (``artifacts-calibration-1310/``):

    resolved DataGolf markets ............ 340
    flagged residual ..................... 322  (94.7%)
    reaching market_info .................  18
    priced + truth-eligible in those ..... 36, ALL winners

published as a 36.5pp accuracy figure about a named third-party provider.

WHY THESE TESTS AND NOT MORE SOURCE SCANS
-----------------------------------------
``test_datagolf_recovery.py`` guards this function with ``inspect.getsource``
assertions, and every one of them was green throughout. A string test cannot see
which exception maps to which flag. These drive the real call paths.
"""

from __future__ import annotations

import importlib
import inspect
import json

import httpx
import pytest

from app.services.datagolf_api import DataGolfAPIService

backfill_winners = importlib.import_module("app.tasks.backfill_winners")
precompute_calibration = importlib.import_module("app.tasks.precompute_calibration")


def _response(status: int) -> httpx.Response:
    return httpx.Response(
        status, request=httpx.Request("GET", "https://feeds.datagolf.com/x")
    )


class TestAbsenceIsNotRefusalIsNotTimeout:
    """gotcha #36 / #53 on the client: ``[]`` may only ever mean 404."""

    @pytest.fixture
    def service(self, monkeypatch):
        svc = DataGolfAPIService()
        monkeypatch.setattr(svc, "api_key", "test-key", raising=False)
        return svc

    async def test_404_is_a_real_absence(self, service, monkeypatch):
        async def _get(endpoint, params=None):
            raise httpx.HTTPStatusError(
                "not found", request=_response(404).request, response=_response(404)
            )

        monkeypatch.setattr(service, "_get", _get)
        assert await service.get_historical_results(tour="pga", event_id="1") == []

    async def test_403_RAISES_rather_than_reporting_an_absence(
        self, service, monkeypatch
    ):
        """A plan/entitlement refusal says nothing about whether the event exists.

        This is the specimen: when it returned ``[]`` the caller wrote a permanent
        'this tournament never happened' flag onto the market.
        """
        async def _get(endpoint, params=None):
            raise httpx.HTTPStatusError(
                "forbidden", request=_response(403).request, response=_response(403)
            )

        monkeypatch.setattr(service, "_get", _get)
        with pytest.raises(httpx.HTTPStatusError):
            await service.get_historical_results(tour="pga", event_id="1")

    async def test_timeout_RAISES_rather_than_reporting_an_absence(
        self, service, monkeypatch
    ):
        async def _get(endpoint, params=None):
            raise httpx.ReadTimeout("slow")

        monkeypatch.setattr(service, "_get", _get)
        with pytest.raises(httpx.ReadTimeout):
            await service.get_historical_results(tour="pga", event_id="1")

    async def test_a_200_with_no_rows_is_still_an_absence(self, service, monkeypatch):
        async def _get(endpoint, params=None):
            return []

        monkeypatch.setattr(service, "_get", _get)
        assert await service.get_historical_results(tour="pga", event_id="1") == []


class TestTheTwoStatesAreDifferentClaims:
    def test_the_keys_are_distinct(self):
        assert (
            backfill_winners.DATAGOLF_RESIDUAL_KEY
            != backfill_winners.DATAGOLF_UNVERIFIED_KEY
        )

    def test_only_the_evidenced_absence_path_writes_the_terminal_flag(self):
        """The error handler must reach for the RETRYABLE writer, not the terminal one.

        Read on the source because the two writers are one call each; the
        behavioural halves are covered above and below.
        """
        src = inspect.getsource(backfill_winners._recover_datagolf_participation)
        body = src.split('"""', 2)[-1]  # strip the docstring, which names both
        assert "_mark_datagolf_residual(" in body
        assert "_mark_datagolf_unverified(" in body
        # the terminal writer is reached exactly once, from the `not historical`
        # branch — never from the exception handler.
        assert body.count("_mark_datagolf_residual(") == 1
        before_except = body.split("except Exception as _me:")[0]
        after_except = body.split("except Exception as _me:")[1]
        assert "_mark_datagolf_residual(" in before_except
        assert "_mark_datagolf_residual(" not in after_except
        assert "_mark_datagolf_unverified(" in after_except

    def test_the_retry_budget_is_bounded(self):
        assert backfill_winners.DATAGOLF_RECOVERY_MAX_ATTEMPTS >= 1
        assert backfill_winners.DATAGOLF_RECOVERY_COOLOFF_HOURS >= 1

    def test_the_sweep_paces_retries(self):
        src = inspect.getsource(backfill_winners._recover_datagolf_participation)
        assert ":max_attempts" in src and ":cooloff_hours" in src

    def test_the_sweep_re_asks_LEGACY_flags_and_skips_only_evidenced_ones(self):
        """The 322 flags on production were written by the conflating writer.

        Treating them as evidence would entrench the defect permanently — the
        markets would never be re-asked and their losers never returned. The new
        writer always records a reason, so "flagged but reasonless" is exactly
        the legacy set, and the SELECT must key on the REASON, not the boolean.
        """
        src = inspect.getsource(backfill_winners._recover_datagolf_participation)
        assert "datagolf_recovery_residual_reason" in src, (
            "the sweep keys on the boolean, so legacy flags are never re-asked"
        )
        # Keying on the bare boolean would skip the legacy rows.
        assert "datagolf_recovery_residual')::boolean" not in src

    def test_the_clear_runs_on_the_SUCCESS_path_only(self):
        sweep = inspect.getsource(backfill_winners._recover_datagolf_participation)
        assert "_clear_datagolf_withholding(" in sweep
        assert (
            "_clear_datagolf_withholding("
            in sweep.split("except Exception as _me:")[0]
        )
        assert (
            "_clear_datagolf_withholding("
            not in sweep.split("except Exception as _me:")[1]
        )

    def test_the_sweep_counts_what_it_actually_recovered(self):
        """gotcha #53: "it returned" is not "it worked".

        A sweep that reports healthy while lifting zero withholdings has done
        nothing for the ship, and needs its own counter to say so.
        """
        src = inspect.getsource(backfill_winners._recover_datagolf_participation)
        assert '"withholding_cleared"' in src


class _FakeSession:
    """Just enough session to drive the three metadata helpers for real.

    They are the only place the two states are written, so a source scan here
    would repeat the mistake this file exists to stop: every string assertion in
    ``test_datagolf_recovery.py`` was green throughout the defect.
    """

    def __init__(self, store: dict[int, dict | None]):
        self.store = store

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, statement, params=None):
        sql = str(statement)
        params = params or {}
        if sql.strip().upper().startswith("SELECT"):
            value = self.store.get(params["mid"])
            return _Scalar(value)
        assert "UPDATE futures_markets" in sql
        self.store[params["mid"]] = json.loads(params["meta"])
        return None

    async def commit(self):
        return None


class _Scalar:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


def _factory(store):
    return lambda: _FakeSession(store)


class TestTheHelpersOnRealMetadata:
    async def test_a_fresh_absence_is_flagged_WITH_its_reason(self):
        store = {1: None}
        assert await backfill_winners._mark_datagolf_residual(
            _factory(store), 1, "event_not_in_index"
        ) is True
        meta = store[1]
        assert meta["datagolf_recovery_residual"] is True
        assert meta["datagolf_recovery_residual_reason"] == "event_not_in_index"
        assert meta["datagolf_recovery_residual_at"]

    async def test_a_RECONFIRMED_LEGACY_flag_gains_the_reason_it_never_had(self):
        """The 322 production rows: flagged, reasonless, and re-asked once.

        An early return on the boolean would leave them reasonless forever, so
        the sweep would re-ask them on every pass and never settle.
        """
        store = {1: {"datagolf_recovery_residual": True}}  # the legacy shape
        newly = await backfill_winners._mark_datagolf_residual(
            _factory(store), 1, "event_not_in_index"
        )
        assert newly is False, "an already-flagged market must not be counted twice"
        assert store[1]["datagolf_recovery_residual_reason"] == "event_not_in_index"

    async def test_a_failed_call_never_writes_the_terminal_flag(self):
        store = {1: None}
        first, attempts = await backfill_winners._mark_datagolf_unverified(
            _factory(store), 1, status=403, detail="HTTPStatusError 403"
        )
        assert (first, attempts) == (True, 1)
        assert "datagolf_recovery_residual" not in store[1], (
            "a refused call was recorded as an absent tournament — the defect"
        )
        assert store[1]["datagolf_recovery_unverified"]["last_status"] == 403

    async def test_attempts_accumulate_up_to_the_budget(self):
        store = {1: None}
        for expected in range(1, backfill_winners.DATAGOLF_RECOVERY_MAX_ATTEMPTS + 1):
            first, attempts = await backfill_winners._mark_datagolf_unverified(
                _factory(store), 1, status=None, detail="ReadTimeout"
            )
            assert attempts == expected
            assert first is (expected == 1)

    async def test_success_lifts_every_withholding_including_a_legacy_one(self):
        """A recovered market that keeps a stale flag is withheld forever.

        Its losers ARE restored in ``futures_outcomes`` and the curve still
        cannot see them — the defect wearing the fix's clothes.
        """
        store = {
            1: {
                "datagolf_recovery_residual": True,  # legacy, reasonless
                "datagolf_recovery_unverified": {"attempts": 3},
                "datagolf_event_id": "kept",
            }
        }
        assert await backfill_winners._clear_datagolf_withholding(_factory(store), 1)
        assert store[1] == {"datagolf_event_id": "kept"}, (
            "clearing must drop every withholding key and nothing else"
        )

    async def test_clearing_a_clean_market_reports_nothing_cleared(self):
        """gotcha #53: the counter must not inflate on markets it did not free."""
        store = {1: {"datagolf_event_id": "kept"}}
        assert await backfill_winners._clear_datagolf_withholding(
            _factory(store), 1
        ) is False


class TestPrecomputeExcludesBothSymmetrically:
    """Both states mean 'the field is not established', so both are withheld.

    Admitting an unverified market would publish its leaderboard-graded WINNERS
    while its real losers sit under ``did_not_play`` — the same censoring in the
    other direction (D112).
    """

    def test_market_info_excludes_the_terminal_residual(self):
        sql = precompute_calibration._calibration_population_ctes()
        assert "datagolf_recovery_residual" in sql

    def test_market_info_excludes_the_unverified_class_TOO(self):
        sql = precompute_calibration._calibration_population_ctes()
        assert "datagolf_recovery_unverified" in sql

    def test_the_stale_ninety_five_percent_comment_carries_its_correction(self):
        """The comment said the residual 'is expected to be ~0'. It was 94.7%.

        A wrong sentence beside a filter is how this survived: the next reader
        trusts it and stops looking. Following CAL-P150 in this file's own
        neighbourhood, the wrong sentence STAYS — quoted and marked — because it
        is the thing that hid the defect; what must be present is the measured
        correction beside it.
        """
        # Line-wrap- and comment-marker-insensitive: the claim is a SENTENCE in a
        # block comment, and pinning it to one physical line would make a reflow
        # look like a deletion.
        sql = " ".join(
            precompute_calibration._calibration_population_ctes()
            .replace("--", " ")
            .split()
        )
        assert "expected to be ~0" in sql, "the quoted claim was deleted, not corrected"
        assert "IT WAS 94.7%" in sql, "the measured correction is missing"
