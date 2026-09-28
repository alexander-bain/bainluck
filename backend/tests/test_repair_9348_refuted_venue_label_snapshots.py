"""#9348 / #9417 — the chart rows a not-the-match Polymarket market wrote are retired.

THE DEFECT THESE GUARD. ``/events/15319905`` (Rajecki v Wang) holds a Polymarket
row written by market 62757466 ``Jingshan: Completed Match: Amelia Rajecki vs
Yuhan Wang`` — venue label ``tennis_completed_match`` — beside two rows from the
real match market 62808900 (label ``moneyline``). ``/events/15317139`` (Braga v
Sporting) draws the ``Halftime Result`` book's 0.225 between match prices of
0.27. The records below are those markets' stored ``content_understanding_v1``,
copied from production 2026-09-28, not invented.

Pure guards over the repair's own decision functions, because every real-PG
gate in this repo skips in CI. Each direction is asserted both ways: a screen
that refuses everything passes every "the novelty is planned" test.
"""

import importlib
import os
import sys

import pytest

#: Market 62757466 — the Rajecki novelty, as production stores it.
RAJECKI_NOVELTY = {
    "v": 1, "rule": "content_understanding@5273", "agreement": "contradicted",
    "venue_type": "tennis_completed_match", "semantic_type": "moneyline",
}
#: Market 62808900 — the real Rajecki v Wang match market, same event.
RAJECKI_MATCH = {
    "v": 1, "rule": "content_understanding@5273", "agreement": "corroborated",
    "venue_type": "moneyline", "semantic_type": "moneyline",
}
#: Market 62583723 — ``SC Braga vs. Sporting CP - Halftime Result`` (#9417).
BRAGA_HALFTIME = {
    "v": 1, "rule": "content_understanding@5273",
    "venue_type": "soccer_halftime_result", "semantic_type": "moneyline",
}


@pytest.fixture(scope="module")
def repair():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)
    return importlib.import_module(
        "scripts.repair_9348_refuted_venue_label_win_prob_snapshots"
    )


def _candidates(*pairs):
    """Stage-1 rows: ``(market_id, understanding)``."""
    return [{"market_id": m, "understanding": u} for m, u in pairs]


# ── the directive's three cases ──────────────────────────────────────────────


def test_the_rajecki_novelty_row_is_planned_9348(repair):
    assert repair.refuted_market_ids(_candidates((62757466, RAJECKI_NOVELTY))) == [
        "62757466"
    ]


def test_the_real_match_row_beside_it_is_kept_9348(repair):
    got = repair.refuted_market_ids(
        _candidates((62757466, RAJECKI_NOVELTY), (62808900, RAJECKI_MATCH))
    )
    assert got == ["62757466"]
    assert "62808900" not in got


def test_a_row_with_no_market_id_is_never_planned_9348(repair):
    # Stage 1 hands the predicate producers; one with no id is no evidence.
    assert repair.refuted_market_ids(_candidates((None, RAJECKI_NOVELTY))) == []
    # And the row scans cannot reach a row without the key: stage 1 requires
    # it, stage 2 and the delete match on it (NULL = ANY(...) is never true).
    assert "game_state ? 'market_id'" in repair.SQL["candidate_markets"]
    for key in ("rows_for_markets", "delete"):
        assert "game_state->>'market_id' = ANY(" in repair.SQL[key]


# ── the #9417 half and the fail-open directions ──────────────────────────────


def test_a_halftime_result_backfill_row_is_planned_9417(repair):
    assert repair.refuted_market_ids(_candidates((62583723, BRAGA_HALFTIME))) == [
        "62583723"
    ]


@pytest.mark.parametrize(
    "understanding",
    [
        None,  # a market stamped before the label existed
        {"v": 1, "semantic_type": "moneyline"},  # label absent (~21% of Gamma)
        {"v": 1, "semantic_type": "moneyline", "venue_type": ""},
        {"v": 99, "semantic_type": "x", "venue_type": "soccer_exact_score"},  # future record
    ],
)
def test_an_unlabelled_producer_is_never_planned_9348(repair, understanding):
    assert repair.refuted_market_ids(_candidates((1, understanding))) == []


def test_a_json_text_record_is_read_like_a_dict_9348(repair):
    import json

    assert repair.refuted_market_ids(
        _candidates((62757466, json.dumps(RAJECKI_NOVELTY)))
    ) == ["62757466"]
    assert repair.refuted_market_ids(_candidates((5, "{not json"))) == []


def test_the_predicate_is_the_gates_own_not_a_copy_9348(repair, monkeypatch):
    """Flip the shared predicate; the repair must follow it (#1951)."""
    from app.utils import content_understanding

    monkeypatch.setattr(
        content_understanding,
        "venue_label_refutes_full_contest_winner",
        lambda market: False,
    )
    assert repair.refuted_market_ids(_candidates((62757466, RAJECKI_NOVELTY))) == []
    monkeypatch.setattr(
        content_understanding,
        "venue_label_refutes_full_contest_winner",
        lambda market: True,
    )
    assert repair.refuted_market_ids(_candidates((62808900, RAJECKI_MATCH))) == [
        "62808900"
    ]


# ── the group-cost refusal ───────────────────────────────────────────────────


def test_an_event_the_delete_would_empty_is_refused_9348(repair):
    planned = {1: [10, 11], 2: [20], 3: [30]}
    totals = [
        {"event_id": 1, "wp_total": 2, "odds_total": 0},  # nothing left → refuse
        {"event_id": 2, "wp_total": 5, "odds_total": 0},  # match rows survive
        {"event_id": 3, "wp_total": 1, "odds_total": 40},  # sportsbook line survives
    ]
    assert repair.refuse_events_that_would_go_dark(totals, planned) == {1}


# ── the D51 gates ────────────────────────────────────────────────────────────


def test_an_empty_reconciliation_never_licenses_apply_9348(repair):
    assert repair.backup_is_exact({}) is False
    assert repair.backup_is_exact({"win_prob_snapshots": 0, "stale_backup_rows": 0})
    assert not repair.backup_is_exact({"win_prob_snapshots": 0, "stale_backup_rows": 1})


@pytest.mark.parametrize("app", [None, "bainluck", "bainluck-staging"])
def test_writes_refuse_off_the_named_app_9348(repair, monkeypatch, app):
    if app is None:
        monkeypatch.delenv("HEROKU_APP_NAME", raising=False)
    else:
        monkeypatch.setenv("HEROKU_APP_NAME", app)
    assert repair.wrong_app_refusal()


def test_writes_run_on_the_named_app_9348(repair, monkeypatch):
    monkeypatch.setenv("HEROKU_APP_NAME", "bainluck-heavy")
    assert repair.wrong_app_refusal() is None


@pytest.mark.asyncio
async def test_a_write_flag_off_heavy_touches_no_session_9348(repair, monkeypatch):
    import app.tasks.base as base

    def boom():
        raise AssertionError("opened a session before the app check")

    monkeypatch.delenv("HEROKU_APP_NAME", raising=False)
    monkeypatch.setattr(base, "get_task_session", boom)
    for flags in ({"backup": True}, {"apply": True}, {"restore": True}):
        args = type("A", (), {"backup": False, "apply": False, "restore": False,
                              "limit": 0, **flags})()
        assert await repair.run(args) == 2


def test_small_plan_discriminates_drained_from_broken_9348(repair):
    floor = repair.SANITY_FLOOR
    assert not repair.explain_small_plan(floor, 0).blocks_apply
    assert not repair.explain_small_plan(10, floor).blocks_apply
    assert repair.explain_small_plan(10, 0).blocks_apply


def test_months_cover_every_day_once_9348(repair):
    from datetime import date

    windows = list(repair.months(date(2025, 11, 15), date(2026, 2, 3)))
    assert windows == [
        (date(2025, 11, 1), date(2025, 12, 1)),
        (date(2025, 12, 1), date(2026, 1, 1)),
        (date(2026, 1, 1), date(2026, 2, 1)),
        (date(2026, 2, 1), date(2026, 3, 1)),
    ]
