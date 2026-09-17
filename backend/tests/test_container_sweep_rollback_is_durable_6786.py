"""The rollback for #5821 has to survive the next scheduled pass (#6786 review).

SHIP: an operator who rolls back the container-twin repair stays rolled back —
the beat does not silently re-tag the rows within the hour.

TWO GAPS, BOTH RAISED IN #6786's REVIEW, BOTH PINNED HERE
─────────────────────────────────────────────────────────
1. **The restore script alone is not a rollback.** It removes the tags; the beat
   runs `apply=True` at :27 every hour and the planner selects on the ABSENCE of
   the tag, so the next pass re-tags everything the operator just restored. The
   undo needs a durable STOP, and the rollback is a sequence: stop, verify the
   stop on the receipt, then restore.

2. **A failed read is not an absence.** The restore caught every exception while
   reading the backup table and printed "No backup table — nothing to undo" with
   a SUCCESS exit. A dropped connection, a permission error and a genuinely
   missing table were one outcome, and the operator would read the loudest
   failure as a clean no-op.

`test_a_disabled_pass_opens_no_session` is the one that matters most for (1):
the stop is worthless if it fires after the sweep has already begun writing.
"""

from __future__ import annotations

import pytest

from app.tasks.polymarket_container_twin_sweep import (
    CONTAINER_TWIN_SWEEP_DISABLED_ENV,
    run_polymarket_container_twin_sweep,
    sweep_is_disabled,
)
from app.utils.task_verdict import _TERMINAL_COMPLETE, _TERMINAL_NO_WORK
from scripts.restore_5821_container_twin_tags import is_missing_backup_table


class TestTheStopSwitch:
    def test_unset_means_running(self, monkeypatch):
        """The normal state, and what ships."""
        monkeypatch.delenv(CONTAINER_TWIN_SWEEP_DISABLED_ENV, raising=False)
        assert sweep_is_disabled() is False

    @pytest.mark.parametrize("value", ["", "   ", "\t", "\n"])
    def test_empty_or_whitespace_means_running(self, monkeypatch, value):
        """`config:set X=""` and a stray space are the same intent as unset."""
        monkeypatch.setenv(CONTAINER_TWIN_SWEEP_DISABLED_ENV, value)
        assert sweep_is_disabled() is False

    @pytest.mark.parametrize(
        "value",
        [
            "1", "true", "TRUE", "yes", "on",
            # 🔴 THE WHOLE REASON THIS IS NOT A TRUTHY SET. An operator halting a
            # live repair who fat-fingers the value must still get a stopped
            # sweep. Under a {"1","true","yes"} test each of these would leave
            # the beat running and re-tag every row the restore just cleared.
            "ture", "TRUE ", "0", "false", "no", "off", "disabled", "x",
        ],
    )
    def test_any_non_empty_value_stops_it(self, monkeypatch, value):
        monkeypatch.setenv(CONTAINER_TWIN_SWEEP_DISABLED_ENV, value)
        assert sweep_is_disabled() is True


class TestAStoodDownPass:
    @pytest.mark.asyncio
    async def test_a_disabled_pass_opens_no_session(self, monkeypatch):
        """🔴 THE STOP FIRES BEFORE THE DATABASE IS TOUCHED.

        A stop that runs after the session is open still races a rollback: the
        pass could read the window and write tags between the operator's restore
        and their verification. `get_task_session` is replaced with a detonator —
        if the sweep reaches it, this fails.
        """
        import app.tasks.base as base

        def _explode(*a, **kw):
            raise AssertionError(
                "a stood-down sweep must not open a database session at all"
            )

        monkeypatch.setattr(base, "get_task_session", _explode)
        monkeypatch.setenv(CONTAINER_TWIN_SWEEP_DISABLED_ENV, "1")

        summary = await run_polymarket_container_twin_sweep()

        assert summary["disabled"] is True
        assert summary["tagged"] == 0

    @pytest.mark.asyncio
    async def test_it_is_skipped_and_never_complete(self, monkeypatch):
        """A switched-off sweep has proved nothing and must not vouch.

        `skipped` is in the no-work vocabulary, so the receipt classifies as an
        authoritative UNKNOWN. `complete` here would let a disabled beat report
        the task healthy — the exact "a receipt cannot vouch for a pass that
        wrote nothing" finding CERT-3030 blocked this ship for.
        """
        import app.tasks.base as base

        monkeypatch.setattr(
            base, "get_task_session", lambda *a, **kw: pytest.fail("no session")
        )
        monkeypatch.setenv(CONTAINER_TWIN_SWEEP_DISABLED_ENV, "1")

        summary = await run_polymarket_container_twin_sweep()

        assert summary["terminal"] == "skipped"
        assert summary["terminal"] in _TERMINAL_NO_WORK
        assert summary["terminal"] not in _TERMINAL_COMPLETE
        assert summary["measured"] is False

    @pytest.mark.asyncio
    async def test_the_reason_names_the_variable_an_operator_must_unset(
        self, monkeypatch
    ):
        """The receipt is what the rollback procedure reads to confirm the stop.

        Its own reason, distinct from the population floor's and the fold
        refusal's — both of those are `failed` and mean something has gone
        wrong, while this means somebody chose it.
        """
        import app.tasks.base as base

        monkeypatch.setattr(
            base, "get_task_session", lambda *a, **kw: pytest.fail("no session")
        )
        monkeypatch.setenv(CONTAINER_TWIN_SWEEP_DISABLED_ENV, "1")

        summary = await run_polymarket_container_twin_sweep()

        assert CONTAINER_TWIN_SWEEP_DISABLED_ENV in summary["reason"]
        assert "stood down" in summary["reason"]
        for other in ("population floor", "refusing to write"):
            assert other not in summary["reason"]


class TestAFailedBackupReadIsNotAnAbsence:
    """Gap 2: `is_missing_backup_table` answers only for a real 42P01."""

    def test_a_real_undefined_table_is_an_absence(self):
        class _Orig(Exception):
            sqlstate = "42P01"

        class _Wrapped(Exception):
            orig = _Orig()

        assert is_missing_backup_table(_Wrapped()) is True

    def test_psycopg2_spelling_is_read_too(self):
        class _Orig(Exception):
            pgcode = "42P01"

        class _Wrapped(Exception):
            orig = _Orig()

        assert is_missing_backup_table(_Wrapped()) is True

    @pytest.mark.parametrize(
        "code,what",
        [
            ("42501", "insufficient_privilege — a permission error"),
            ("57014", "query_canceled — a statement timeout"),
            ("08006", "connection_failure — the read never landed"),
            ("42601", "syntax_error — our own SQL is broken"),
            ("53300", "too_many_connections"),
        ],
    )
    def test_every_other_failure_is_NOT_an_absence(self, code, what):
        """🔴 THE DEFECT ITSELF. Each of these printed "nothing to undo" and
        exited 0 before #6786's review, while the tags were still on the rows."""
        class _Orig(Exception):
            sqlstate = code

        class _Wrapped(Exception):
            orig = _Orig()

        assert is_missing_backup_table(_Wrapped()) is False, what

    def test_an_exception_with_no_sqlstate_is_not_an_absence(self):
        """Fail CLOSED: what we cannot positively identify as 42P01 aborts."""
        assert is_missing_backup_table(RuntimeError("something else")) is False
        assert is_missing_backup_table(KeyboardInterrupt()) is False
