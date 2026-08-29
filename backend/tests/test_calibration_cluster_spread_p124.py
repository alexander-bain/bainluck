"""CAL-P124 — guards for the cluster-spread predictor.

This instrument exists because ``calibration_cell_exact --edge-check`` reported
a **5-row** sensitivity on a cell the rail was missing by **4,709 rows**
(``polymarket/basketball``, curve ``q268``: replica 8,426 vs published 13,135).
The edge check is a MARGINAL test — it moves the chunk width and asks whether
the answer moves — and it is blind by construction to a cluster whose members
span 31,000,000 ids, because halving 1,000,000 to 500,000 shatters that cluster
exactly as thoroughly.

So the failure this file guards against is not "the number is wrong". It is
**"the number is reassuring and wrong"**, which is the same class as gotcha #53
and is why most of these tests are marked SILENT: if they break, the instrument
still prints a complete, plausible, well-formed table.

The four measured points the bands are drawn from, all on curve ``q268``:

    polymarket/cricket       7.0% wide -> -0.18% reproduction shortfall
    polymarket/soccer       14.2% wide -> -5.06%
    polymarket/baseball     32.2% wide -> -5.70%
    polymarket/basketball   93.1% wide -> -35.85%
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(name: str):
    """Load a script WITHOUT registering it in ``sys.modules``.

    CAL-P121's suite goes red when a sibling script is registered, and it is
    correct to: the fold modules mutate a shared ``DIMENSIONS`` dict on import.
    """
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ccs = _load("calibration_cluster_spread")


# --------------------------------------------------------------------------
# pct_in_wide — the arithmetic, and the one case that must NOT be a number
# --------------------------------------------------------------------------

def test_pct_in_wide_basic():
    assert ccs.pct_in_wide(1000, 500) == 50.0


def test_pct_in_wide_rounds_to_one_dp():
    assert ccs.pct_in_wide(21288, 19824) == 93.1


def test_pct_in_wide_all_wide():
    assert ccs.pct_in_wide(10, 10) == 100.0


def test_pct_in_wide_none_wide():
    assert ccs.pct_in_wide(10, 0) == 0.0


def test_pct_in_wide_no_clusters_is_none_not_zero():
    """SILENT. ``0.0`` would render as a clean bill of health for an unmeasured cell.

    "This cell has no >=3 clusters" and "this cell's clusters are all narrow"
    are different facts with the same shape, and only one of them means the
    fold can be trusted.
    """
    assert ccs.pct_in_wide(0, 0) is None


def test_pct_in_wide_rejects_negative():
    with pytest.raises(ValueError):
        ccs.pct_in_wide(-1, 0)


def test_pct_in_wide_rejects_wide_exceeding_total():
    """A subset cannot exceed its superset; if it does, the SQL changed shape."""
    with pytest.raises(ValueError):
        ccs.pct_in_wide(10, 11)


# --------------------------------------------------------------------------
# risk_band — the four measured points must land where the doc says
# --------------------------------------------------------------------------

@pytest.mark.parametrize("pct,band", [
    (7.0, "LOW"),        # cricket      -0.18%
    (14.2, "MODERATE"),  # soccer       -5.06%
    (32.2, "MODERATE"),  # baseball     -5.70%
    (93.1, "SEVERE"),    # basketball  -35.85%
])
def test_risk_band_reproduces_the_measured_points(pct, band):
    """SILENT. These four are the ONLY evidence the bands rest on.

    Move a boundary and the table still prints; what changes is that a cell the
    lane has measured stops landing in the band its measurement earned, and the
    next queue reads a reassuring word over a fold that cannot reach its cell.
    """
    assert ccs.risk_band(pct) == band


def test_risk_band_boundaries_are_half_open_upward():
    assert ccs.risk_band(9.9) == "LOW"
    assert ccs.risk_band(10.0) == "MODERATE"
    assert ccs.risk_band(34.9) == "MODERATE"
    assert ccs.risk_band(35.0) == "HIGH"
    assert ccs.risk_band(59.9) == "HIGH"
    assert ccs.risk_band(60.0) == "SEVERE"


def test_risk_band_none_is_its_own_band():
    assert ccs.risk_band(None) == "NO_CLUSTERS"


def test_risk_band_rejects_negative():
    with pytest.raises(ValueError):
        ccs.risk_band(-0.1)


def test_risk_band_is_monotone():
    """A higher share of shattered markets can never read as a safer cell."""
    order = ["LOW", "MODERATE", "HIGH", "SEVERE"]
    seen = [ccs.risk_band(p) for p in range(0, 101, 1)]
    idx = [order.index(b) for b in seen]
    assert idx == sorted(idx)


def test_every_band_has_guidance():
    """SILENT. A band with no guidance line renders as ``KeyError`` at the very end
    of a run that already spent its query budget."""
    for pct in (None, 5.0, 20.0, 45.0, 95.0):
        assert ccs.risk_band(pct) in ccs.BAND_GUIDANCE


def test_band_guidance_has_no_orphans():
    reachable = {ccs.risk_band(p) for p in [None] + list(range(0, 101))}
    assert set(ccs.BAND_GUIDANCE) == reachable


# --------------------------------------------------------------------------
# cluster_spread_sql — the predicate must keep saying what the producer says
# --------------------------------------------------------------------------

def test_grouping_gate_matches_the_producer():
    """SILENT. ``>= 3`` is ``_virtual_market_ctes``'s gate, not a tuning knob.

    Lower it and clusters that were never virtual questions enter the
    denominator, diluting ``pct_in_wide`` toward zero — the instrument would
    report a heavily shattered cell as safe.
    """
    assert ccs.GROUPING_GATE == 3
    sql = ccs.cluster_spread_sql("polymarket", "basketball", "group_id")
    assert "HAVING COUNT(*) >= 3" in sql


def test_sql_covers_both_cluster_keys():
    """``virtual_market`` tries ``g:<group_id>`` then ``e:<event_id>``; measuring
    only the first understates a cell whose grouping comes from events."""
    assert ccs.CLUSTER_KEYS == ("group_id", "event_id")


@pytest.mark.parametrize("key", ["group_id", "event_id"])
def test_sql_groups_and_filters_on_the_named_key(key):
    sql = ccs.cluster_spread_sql("polymarket", "basketball", key)
    assert f"GROUP BY {key}" in sql
    assert f"{key} IS NOT NULL" in sql
    assert f"MAX(id) - MIN(id) AS spread" in sql


def test_sql_rejects_an_unlisted_key():
    """No arbitrary column reaches the interpolation site."""
    with pytest.raises(ValueError):
        ccs.cluster_spread_sql("polymarket", "basketball", "id); DROP")


def test_sql_uses_the_same_category_coalesce_as_the_fold():
    """SILENT. ``calibration_cell_exact`` scopes on
    ``COALESCE(fm.llm_sport_category, 'uncategorized')``. A bare
    ``llm_sport_category =`` here silently drops every NULL-category market
    from the denominator and the two instruments stop describing one cell.
    """
    sql = ccs.cluster_spread_sql("polymarket", "basketball", "group_id")
    assert "COALESCE(llm_sport_category, 'uncategorized') = 'basketball'" in sql


def test_sql_escapes_quotes_in_identifiers():
    sql = ccs.cluster_spread_sql("poly'market", "bas'ketball", "group_id")
    assert "poly''market" in sql
    assert "bas''ketball" in sql


def test_sql_aggregates_server_side():
    """SILENT, and the expensive one. The per-cluster row list is 717 rows on
    basketball and 7,325 on soccer, both over the db-query 1,000-row cap, which
    truncates SILENTLY. A client-side aggregate would read a truncated cell as
    a small one."""
    sql = ccs.cluster_spread_sql("polymarket", "soccer", "group_id")
    assert sql.lstrip().upper().startswith("SELECT COUNT(*) AS CLUSTERS")
    assert "SUM(CASE WHEN spread >=" in sql


def test_sql_width_is_a_placeholder_not_a_literal():
    """The width is bound at call time so it always matches the FOLD's width."""
    sql = ccs.cluster_spread_sql("polymarket", "basketball", "group_id")
    assert "{width}" in sql
    assert "1000000" not in sql
    assert "spread >= 500000" in sql.format(width=500000)


def test_sql_counts_are_null_safe():
    """SILENT. A cell with no clusters must return zeros, not a row of NULLs
    that ``int()`` then rejects three queries into a sweep."""
    sql = ccs.cluster_spread_sql("polymarket", "basketball", "group_id")
    for agg in ("SUM(c)", "MAX(spread)", "MAX(c)"):
        assert f"COALESCE({agg}" in sql


def test_default_width_matches_the_fold():
    """SILENT. 'Wide' means 'wider than one chunk'. If this drifts from
    ``calibration_cell_exact.DEFAULT_WIDTH`` the instrument answers a question
    about a chunking nobody runs."""
    cce = SCRIPTS / "calibration_cell_exact.py"
    m = re.search(r"^DEFAULT_WIDTH\s*=\s*([0-9_]+)", cce.read_text(), re.M)
    assert m, "calibration_cell_exact.DEFAULT_WIDTH not found"
    assert ccs.DEFAULT_WIDTH == int(m.group(1).replace("_", ""))


# --------------------------------------------------------------------------
# credentials and rendering
# --------------------------------------------------------------------------

def test_missing_credentials_raise_rather_than_return_empty(monkeypatch):
    """gotcha #124: the script must not exit 2 into a caller that reads it as
    'no clusters found'."""
    monkeypatch.delenv("BAINLUCK_API", raising=False)
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    with pytest.raises(ccs.QueryFailed) as e:
        ccs.db_query("SELECT 1")
    assert "source ~/.claude/.env" in str(e.value)


def test_render_marks_a_no_cluster_cell_without_a_number():
    out = {
        "source": "kalshi", "category": "tech", "width": 1_000_000,
        "risk": "NO_CLUSTERS",
        "by_key": {"group_id": {"clusters": 0, "markets": 0, "markets_in_wide": 0,
                                "max_spread": 0, "max_size": 0,
                                "pct_in_wide": None, "risk": "NO_CLUSTERS"}},
    }
    text = ccs.render(out)
    assert "—" in text
    assert "0.0%" not in text
    assert "NO_CLUSTERS" in text


def test_render_reports_the_measured_basketball_row():
    out = {
        "source": "polymarket", "category": "basketball", "width": 1_000_000,
        "risk": "SEVERE",
        "by_key": {"group_id": {"clusters": 717, "markets": 21288,
                                "markets_in_wide": 19824, "max_spread": 30995800,
                                "max_size": 120, "pct_in_wide": 93.1,
                                "risk": "SEVERE"}},
    }
    text = ccs.render(out)
    assert "93.1%" in text
    assert "30,995,800" in text
    assert "UNMEASURED" in text
