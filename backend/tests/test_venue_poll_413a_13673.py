"""Unit guards for #13673 / Ruling 413:A `venue_poll_30s` population SQL optimizations."""

from __future__ import annotations

import re

from app.tasks import venue_poll_30s as v


def _norm(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip()


def test_pm_props_sql_bounds_suspended_events_before_jsonb_refusal(monkeypatch):
    monkeypatch.setenv("PM_WS_PROPS_TO_POLL", "1")
    from app.tasks.polymarket_ws import _slate_event_window

    sql = v.polymarket_population_sql(open_arm=False)
    norm = _norm(sql)

    assert "e.status IN ('live', 'suspended')" not in norm
    assert (
        f"e.status = 'suspended' AND e.commence_time >= NOW() - INTERVAL '{v.SLATE_SUPERSET_PAST_HOURS} hours'"
        in norm
    )
    window_rendered = _norm(v._render(_slate_event_window()))
    pw_pos = norm.index("props_window AS MATERIALIZED")
    win_pos = norm.index(f"COALESCE({window_rendered}, FALSE)", pw_pos)
    props_pos = norm.index("props AS MATERIALIZED")
    ref_pos = norm.index(_norm(v.PM_VENUE_LABEL_REFUSAL_SQL), props_pos)
    assert pw_pos < win_pos < props_pos < ref_pos


def test_population_sql_replaces_correlated_winner_subplan_with_single_pass():
    for builder in (v.kalshi_population_sql, v.polymarket_population_sql):
        for arm in (False, True):
            sql = builder(open_arm=arm)
            assert "fo_w" not in sql
            assert "pool_outcomes AS MATERIALIZED" in sql
            assert "settled_winners AS MATERIALIZED" in sql
            assert "LEFT JOIN settled_winners sw" in sql
            assert "AND sw.fm_id IS NULL" in sql
