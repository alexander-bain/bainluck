"""#2199 — guards for the high-value futures price refresher.

The class this file exists to catch is not "the refresher has a bug". It is the
one that produced #2199 in the first place: **price capture for a known market
riding on a bounded discovery scan**, so that a poll reporting success can leave
the platform's most valuable markets dark for a month. The tests below pin the
four properties that keep that from coming back:

1. The selection predicate is value-floored and liveness-floored, and the guard
   endpoint asserts over the SAME set the task refreshes — a guard covering a
   different population than the fix is how a breach reads green.
2. The ordering has no fixed point. Oldest-capture-first is the intuitive choice
   and it is a trap: an unpriceable market pins the head of the queue forever.
3. The task's terminal is honest — attempted-and-wrote-nothing is `failed`.
4. The writer refuses to create identity, refuses settled outcomes, and refuses
   a null price.
"""

import re
from pathlib import Path

import pytest

from app.tasks import futures_price_refresh as fpr
from app.utils.task_verdict import ENFORCED_TASKS, classify_summary

_MODULE_SRC = Path(fpr.__file__).read_text()
_ADMIN_SRC = (
    Path(fpr.__file__).parent.parent / "routes" / "admin_source_health.py"
).read_text()


class TestSelectionPredicate:
    """The fix and its guard must cover one population, not two."""

    def test_predicate_carries_every_floor(self):
        sql = fpr._CANDIDATE_SQL.text
        assert "fm.status = 'open'" in sql
        assert "fm.market_tier = 1" in sql
        assert "fm.volume >= :volume_floor" in sql
        # Gotcha #33: settled Kalshi markets keep status='open', so `status`
        # alone is not a liveness test. The resolution-date bound is what keeps
        # the dead out of an ordering that would otherwise never release them.
        assert "resolution_date > NOW()" in sql

    def test_uses_exists_not_max_captured_at(self):
        """MAX(captured_at) over the 179M-row snapshot table times out at 10s.

        Pinned because the aggregate form is the natural thing to write, reads
        correctly, and takes the task's own selector down in production — a
        selector that times out is a refresher that never runs.
        """
        sql = fpr._CANDIDATE_SQL.text
        assert "NOT EXISTS" in sql
        assert "MAX(" not in sql.upper()

    def test_guard_endpoint_uses_the_same_predicate(self):
        """A guard over a different set than the fix cannot prove the fix worked."""
        task_sql = _normalise(fpr._CANDIDATE_SQL.text)
        for name in ("_PRICE_DARK_SQL", "_PRICE_DARK_WORST_SQL"):
            guard_sql = _normalise(_extract_sql_literal(_ADMIN_SRC, name))
            for clause in (
                "fm.status = 'open'",
                "fm.market_tier = 1",
                "fm.volume >= :volume_floor",
                "fm.resolution_date > now()",
                "not exists",
            ):
                assert clause.lower() in guard_sql, f"{name} is missing {clause!r}"
                assert clause.lower() in task_sql

    def test_guard_endpoint_reads_snapshots_not_updated_at(self):
        """`futures_markets.updated_at` is what made this class invisible.

        The discovery polls stamp `updated_at` on rows they re-read while
        capturing no price, so a freshness check built on it reads green over a
        month-dark market. Only `futures_odds_snapshots.captured_at` answers
        whether a price was actually captured.
        """
        for name in ("_PRICE_DARK_SQL", "_PRICE_DARK_WORST_SQL"):
            sql = _extract_sql_literal(_ADMIN_SRC, name)
            assert "futures_odds_snapshots" in sql
            assert "s.captured_at" in sql
            assert "updated_at" not in sql


class TestOrderingHasNoFixedPoint:
    def test_orders_by_value_not_by_staleness(self):
        """Oldest-capture-first is the trap, and it is the intuitive choice.

        A market whose book cannot be priced never gets a snapshot, so its
        last-capture stays NULL forever. Under `ORDER BY last_capture NULLS
        FIRST` it holds the head of the queue on every run, permanently starving
        everything behind it — the same starvation shape (gotcha #41) that this
        whole task exists to undo. Volume DESC has no such fixed point.
        """
        sql = fpr._CANDIDATE_SQL.text
        assert "ORDER BY fm.volume DESC" in sql
        assert "NULLS FIRST" not in sql.upper()

    def test_attempt_markers_record_attempts_not_successes(self):
        """The rotation only works if a FAILED attempt also advances the cursor.

        Marking successes would put every unpriceable market back at the front on
        the very next run, which is the fixed point again with extra steps.
        """
        assert "_mark_attempted(attempted_ids" in _MODULE_SRC
        # The ids are appended before the fetch is known to have worked.
        attempted_appends = _MODULE_SRC.count("attempted_ids.append(")
        assert attempted_appends == 2, "one append per source, before the fetch"

    def test_scan_is_wider_than_one_budget(self):
        """Without headroom, a run whose top-N were all just attempted does nothing."""
        assert "scan_limit=max(budget * 3, budget + 50)" in _MODULE_SRC.replace(
            "\n", ""
        ).replace("  ", "")


class TestTerminalIsHonest:
    """Gotcha #53 / task_verdict: "it returned" is not "it worked"."""

    def test_enrolled_in_enforced_tasks(self):
        assert "futures_price_refresh" in ENFORCED_TASKS

    @pytest.mark.parametrize(
        "stats,expected",
        [
            ({"markets_attempted": 0, "snapshots_written": 0, "budget_hit": False, "errors": []}, "no_work"),
            # The founding case: markets were fetched, nothing was written.
            ({"markets_attempted": 40, "snapshots_written": 0, "budget_hit": False, "errors": []}, "failed"),
            ({"markets_attempted": 40, "snapshots_written": 12, "budget_hit": True, "errors": []}, "partial"),
            ({"markets_attempted": 40, "snapshots_written": 12, "budget_hit": False, "errors": ["x"]}, "partial"),
            ({"markets_attempted": 40, "snapshots_written": 40, "budget_hit": False, "errors": []}, "complete"),
        ],
    )
    def test_terminal(self, stats, expected):
        assert fpr._terminal(stats) == expected

    def test_only_complete_reads_green(self):
        """Enrolment is a no-op unless the non-complete terminals block success."""
        assert classify_summary({"terminal": "complete"}).is_green
        for terminal in ("failed", "partial", "no_work"):
            verdict = classify_summary({"terminal": terminal})
            assert not verdict.is_green, terminal
            assert verdict.authoritative, terminal

    def test_empty_run_distinguishes_its_two_causes(self):
        """"Nothing was stale" and "everything stale was just attempted" are opposite.

        Gotcha #53: an empty result is a response shape, not an absence. Collapsing
        the two into one silent return is how a wedged refresher looks healthy.
        """
        assert '"complete" if not scan else "no_work"' in _MODULE_SRC


class TestWriterRefusals:
    def test_never_creates_an_outcome(self):
        """Price-only. Minting identity here would bypass categorisation and tiering."""
        assert "pg_insert(FuturesOutcome)" not in _MODULE_SRC
        assert "pg_insert(FuturesMarket)" not in _MODULE_SRC
        assert 'stats["unknown_outcomes"] += 1' in _MODULE_SRC

    def test_never_touches_a_settled_outcome(self):
        """Gotcha #21: a settled book stops quoting; re-pricing it can only corrupt."""
        assert "is_winner IS NULL" in _MODULE_SRC

    def test_never_writes_a_null_or_out_of_range_probability(self):
        assert "if prob is None or not (0 < prob < 1):" in _MODULE_SRC

    def test_reuses_the_source_price_guards_rather_than_reimplementing(self):
        """A second, subtly different price derivation is a second set of bugs.

        `_kalshi_yes_probability` carries the wide/one-sided-book refusal;
        `_resolve_market_probability` carries the placeholder gate (gotcha #19);
        `field_is_incoherent` carries #1527. This path must not be able to write a
        price the ingest path would have refused.
        """
        assert "from app.tasks.kalshi import _kalshi_yes_probability" in _MODULE_SRC
        assert "from app.tasks.polymarket import _resolve_market_probability" in _MODULE_SRC
        assert "field_is_incoherent" in _MODULE_SRC

    def test_kalshi_adapter_parses_through_the_service(self):
        """Kalshi v2 quotes prices as decimal-string dollars OR integer cents.

        `_parse_market` resolves that pair. Re-deriving it here risks writing 95
        where 0.95 belongs — a coherent-looking wrong price, which no downstream
        check would catch.
        """
        assert "service._parse_event(raw)" in _MODULE_SRC
        assert "/ 100" not in _MODULE_SRC


class TestWiring:
    def test_beat_is_registered_and_routed_to_heavy(self):
        from app.tasks import HEAVY_TASKS, celery_app

        entry = celery_app.conf.beat_schedule["refresh-stale-futures-prices-hourly"]
        assert entry["task"] == "app.tasks.refresh_stale_futures_prices"
        assert entry["options"]["queue"] == "heavy"
        # Background has ~one effective slot for ~40 beats; a 420s-budget task
        # placed there closes the queue rather than sharing it.
        assert "app.tasks.refresh_stale_futures_prices" in HEAVY_TASKS
        assert (
            celery_app.conf.task_routes["app.tasks.refresh_stale_futures_prices"]
            == {"queue": "heavy"}
        )

    def test_does_not_collide_with_the_hourly_heavy_precompute(self):
        from app.tasks import celery_app

        ours = celery_app.conf.beat_schedule["refresh-stale-futures-prices-hourly"]
        precompute = celery_app.conf.beat_schedule["precompute-calibration-main"]
        assert ours["schedule"].minute != precompute["schedule"].minute

    def test_wall_budget_sits_under_the_soft_limit(self):
        from app.tasks import celery_app

        task = celery_app.tasks["app.tasks.refresh_stale_futures_prices"]
        assert fpr._TIME_BUDGET_S < task.soft_time_limit < task.time_limit

    def test_staleness_window_matches_the_render_contract(self):
        """The producer and the renderer must not hold two definitions of stale.

        `utils/tournament_register.py::check_freshness` blocks a row from
        rendering as a confident live number past 6h (`LIVE_PRICE_STALE`,
        UX-P130). A refresher with a looser window would leave a permanent band
        where the board refuses to render a price that nothing is trying to
        refresh.

        Pinned as a bare constant rather than by reading the register: that
        module lives on the unmerged `program/ux-113` branch, and a test that
        imports across an integration boundary fails for a reason that has
        nothing to do with what it is guarding.
        """
        assert fpr.STALE_AFTER_HOURS == 6


def _extract_sql_literal(source: str, name: str) -> str:
    match = re.search(rf'^{name} = """(.*?)"""', source, re.S | re.M)
    assert match, f"{name} not found — did the constant get renamed?"
    return match.group(1)


def _normalise(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip().lower()
