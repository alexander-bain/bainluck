"""#6564 — the Gamma winner rail's cursor must be observable, not just logged.

The alert behind #6564 says "backfill may be stalled". It is not stalled:
`backfill_winners` p95 is 105.9s and `backfill_polymarket_winners` 158.6s
against an 840s soft limit, and five consecutive readers over five days
checked exactly that, found both tasks alive, and stopped. Meanwhile
Polymarket `needs_backfill` climbed to 275,808 against Kalshi's 427, and
coverage slid 98.9% -> 94.7%.

The reason the real defect survived those five days is that **liveness was the
only observable property**. The rail selects `fm.id > :last_id ... LIMIT 10000`
and holds its cursor at `min(deferred) - 1`, where a row the run never reached
counts as deferred — so a 158s run that cannot contact Gamma for 10,000 markets
advances the cursor by only what it actually completed, a few hundred rows,
while ~8-10k legs arrive per day. That arithmetic is entirely invisible from
outside: the single emission is a dyno log line on `worker-background`, which
ages out within hours, and nothing under `app/routes/` reads
`bainluck:pm_winner_backfill_offset`.

So this is the unblocker, not the fix. It does not change what the rail grades
or in what order — that is a separate, reviewed change, and building it on an
unmeasured cursor value is the mistake the issue has been repeating. It makes
the cursor's PROGRESS falsifiable so that the fix and its after-check can be.

These tests execute the real functions against recording doubles rather than
reading their source (gotcha #152), except for the one structural assertion
that no second call site can drift — which is a claim about the module's shape
and cannot be made any other way.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from app.tasks.backfill_winners import (
    _POLY_API_RUN_RECEIPT_KEY,
    _POLY_API_RUN_RECEIPT_TTL,
    _bank_poly_api_run,
    _log_poly_api_run,
    _poly_api_run_receipt,
)


def _full_stats(**over):
    """A stats dict shaped like the one the rail actually carries at its exit."""
    stats = {
        "markets_checked": 0,
        "winners_set": 0,
        "losers_set": 0,
        "prices_synced": 0,
        "api_miss": 0,
        "no_match": 0,
        "not_settled": 0,
        "errors": [],
        "champions_minted": 0,
        "champion_mint": {},
        "selected": 0,
        "completed": 0,
        "deferred": 0,
        "cursor_op": "noop",
        "cursor_value": None,
        "cursor_held": False,
    }
    stats.update(over)
    return stats


class TestReceiptShape:
    def test_the_6564_specimen_reports_a_cursor_that_barely_moved(self):
        """The whole point: a page of 10,000 that completed 312 rows.

        `cursor_advanced_by` is the number the log line never gave a reader —
        `selected` alone reads like a healthy 10k page, and `cursor_value`
        alone is a bare id that means nothing without its predecessor.
        """
        receipt = _poly_api_run_receipt(
            _full_stats(
                selected=10_000,
                completed=312,
                deferred=9_688,
                cursor_op="set",
                cursor_value=1_000_311,
                cursor_held=True,
                markets_checked=312,
            ),
            last_max_id=1_000_000,
        )

        assert receipt["cursor_before"] == 1_000_000
        assert receipt["cursor_after"] == 1_000_311
        assert receipt["cursor_advanced_by"] == 311
        assert receipt["cursor_held"] is True
        assert receipt["selected"] == 10_000
        assert receipt["completed"] == 312
        assert receipt["deferred"] == 9_688
        # A reader must be able to reach "the page did not drain" from the
        # receipt alone, without re-deriving it from the log.
        assert receipt["deferred"] > receipt["completed"]

    def test_a_drained_page_reports_the_wrap_without_a_bogus_delta(self):
        """`delete` means wraparound to the oldest id — there is no "after"."""
        receipt = _poly_api_run_receipt(
            _full_stats(
                selected=40,
                completed=40,
                deferred=0,
                cursor_op="delete",
                cursor_value=None,
                cursor_held=False,
            ),
            last_max_id=1_000_000,
        )

        assert receipt["cursor_op"] == "delete"
        assert receipt["cursor_after"] is None
        # Not 0, and not -1_000_000: an absent cursor has no distance from the
        # previous one, and inventing a number here would publish a wraparound
        # as a catastrophic rewind.
        assert receipt["cursor_advanced_by"] is None
        assert receipt["cursor_held"] is False

    def test_a_failed_cursor_write_is_published_as_failed(self):
        receipt = _poly_api_run_receipt(
            _full_stats(
                selected=500,
                completed=10,
                deferred=490,
                cursor_op="failed",
                cursor_value=None,
                cursor_held=True,
                errors=["cursor: boom"],
            ),
            last_max_id=42,
        )

        assert receipt["cursor_op"] == "failed"
        assert receipt["cursor_advanced_by"] is None
        assert receipt["errors"] == 1

    def test_a_targeted_run_is_distinguishable_from_a_stalled_sweep(self):
        """#6110: a targeted repair freezes the cursor on purpose.

        Without `targeted` on the receipt, `cursor_op: skipped_targeted` beside
        an unmoved cursor is indistinguishable from the defect this surface
        exists to expose.
        """
        receipt = _poly_api_run_receipt(
            _full_stats(
                selected=3,
                completed=3,
                cursor_op="skipped_targeted",
                cursor_value=None,
                targeted=3,
            ),
            last_max_id=0,
        )

        assert receipt["cursor_op"] == "skipped_targeted"
        assert receipt["targeted"] == 3

    def test_the_receipt_never_publishes_a_field_it_cannot_know(self):
        """Both call sites bank BEFORE `_finish` stamps the terminal fields.

        Publishing `terminal`/`terminal_reason` here would publish a key that
        is unconditionally None — a surface that looks like it answers "did the
        run finish cleanly" and never does.
        """
        receipt = _poly_api_run_receipt(_full_stats(), last_max_id=0)

        assert "terminal" not in receipt
        assert "terminal_reason" not in receipt
        assert receipt["ran_at"]

    def test_the_receipt_is_json_serialisable(self):
        """It is banked as JSON; a non-serialisable field would be silently
        swallowed by the best-effort guard and the surface would stay empty."""
        receipt = _poly_api_run_receipt(
            _full_stats(cursor_op="set", cursor_value=7, cursor_held=True),
            last_max_id=1,
        )
        assert json.loads(json.dumps(receipt))["cursor_after"] == 7


class TestBanking:
    def test_the_receipt_is_written_under_the_cursor_key_s_own_ttl(self):
        rc = MagicMock()
        with patch("app.tasks.redis_state.get_redis_client", return_value=rc):
            _bank_poly_api_run(
                _full_stats(cursor_op="set", cursor_value=99, selected=5, completed=5),
                last_max_id=10,
            )

        rc.setex.assert_called_once()
        key, ttl, payload = rc.setex.call_args[0]
        assert key == _POLY_API_RUN_RECEIPT_KEY
        # Expiring together with the cursor it describes: a receipt that
        # outlived it would explain a value that is no longer there.
        assert ttl == _POLY_API_RUN_RECEIPT_TTL == 86400 * 7
        assert json.loads(payload)["cursor_after"] == 99

    def test_a_dead_redis_does_not_fail_a_run_that_graded_its_markets(self):
        rc = MagicMock()
        rc.setex.side_effect = RuntimeError("connection reset")
        with patch("app.tasks.redis_state.get_redis_client", return_value=rc):
            _bank_poly_api_run(_full_stats(), last_max_id=0)  # must not raise

    def test_an_unreachable_redis_client_does_not_fail_the_run(self):
        with patch(
            "app.tasks.redis_state.get_redis_client",
            side_effect=RuntimeError("no redis"),
        ):
            _bank_poly_api_run(_full_stats(), last_max_id=0)  # must not raise


class TestSingleCallSite:
    def test_logging_the_run_also_banks_it(self):
        """The two must not be separable: an exit that logged but did not bank
        is a run that is invisible to the admin surface exactly when someone
        is looking for it."""
        rc = MagicMock()
        with patch("app.tasks.redis_state.get_redis_client", return_value=rc):
            _log_poly_api_run(
                _full_stats(cursor_op="set", cursor_value=5, selected=1, completed=1),
                last_max_id=4,
            )

        rc.setex.assert_called_once()
        assert json.loads(rc.setex.call_args[0][2])["cursor_advanced_by"] == 1

    def test_no_exit_carries_its_own_copy_of_the_bank_call(self):
        """#6110's drift guard, extended to the receipt.

        The rail has two exits (a targeted run returns before the cursor
        decision). Both reach the receipt through `_log_poly_api_run`; a second
        direct call site is how the two would come to disagree. Source-shaped
        on purpose — this is a claim about the module's shape.
        """
        import inspect

        from app.tasks import backfill_winners

        src = inspect.getsource(backfill_winners)
        # The definition reads `(stats: dict, last_max_id)`, so this pattern
        # matches invocations only.
        assert src.count("_bank_poly_api_run(stats, last_max_id)") == 1


class TestAdminSurface:
    """The cursor has to be readable by a person, which was the actual gap:
    nothing under `app/routes/` read the offset key at all."""

    @pytest.mark.asyncio
    async def test_the_tile_publishes_the_live_cursor_and_the_last_run(self):
        from app.routes import admin_data_quality

        receipt = _poly_api_run_receipt(
            _full_stats(
                selected=10_000, completed=312, deferred=9_688,
                cursor_op="set", cursor_value=1_000_311, cursor_held=True,
            ),
            last_max_id=1_000_000,
        )
        store = {
            "bainluck:pm_winner_backfill_offset": b"1000311",
            _POLY_API_RUN_RECEIPT_KEY: json.dumps(receipt),
        }
        rc = MagicMock()
        rc.get.side_effect = lambda k: store.get(k)
        rc.llen.return_value = 0

        with patch("app.tasks.redis_state.get_redis_client", return_value=rc), \
             patch.object(admin_data_quality, "_check_admin_secret", return_value=None):
            result = await admin_data_quality.backfill_progress(
                request=MagicMock(), secret="x", bust=False
            )

        tile = result["gamma_cursor"]
        assert "gamma_cursor" in result["tiles"]
        assert tile["live"] == 1_000_311
        assert tile["live_present"] is True
        assert tile["last_run"]["cursor_advanced_by"] == 311
        assert tile["last_run"]["deferred"] == 9_688

    @pytest.mark.asyncio
    async def test_an_absent_cursor_reads_as_a_wrap_not_an_error(self):
        """The rail DELETES the key to wrap back to the oldest row, so absence
        is a legitimate state meaning "resumes at 0" — not a failure, and not
        the same as a rail that never ran."""
        from app.routes import admin_data_quality

        rc = MagicMock()
        rc.get.side_effect = lambda k: None
        rc.llen.return_value = 0

        with patch("app.tasks.redis_state.get_redis_client", return_value=rc), \
             patch.object(admin_data_quality, "_check_admin_secret", return_value=None):
            result = await admin_data_quality.backfill_progress(
                request=MagicMock(), secret="x", bust=False
            )

        tile = result["gamma_cursor"]
        assert "error" not in tile
        assert tile["live"] is None
        assert tile["live_present"] is False
        assert tile["last_run"] is None
        assert "detail" in tile
